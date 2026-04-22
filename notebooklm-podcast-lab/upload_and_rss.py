"""
Upload podcast MP3s to Cloudflare R2 and regenerate RSS feed.

Reads DB for completed items + local podcasts/ directory,
uploads MP3s to R2, and generates podcast.xml using feedgen.

Usage:
    python upload_and_rss.py
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import boto3
from feedgen.feed import FeedGenerator

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import (
    DB_PATH,
    PODCASTS_DIR,
    R2_ACCESS_KEY_ID,
    R2_BUCKET_NAME,
    R2_ENDPOINT,
    R2_PUBLIC_URL,
    R2_SECRET_ACCESS_KEY,
    RSS_OUTPUT_PATH,
    PODCAST_AUTHOR,
    PODCAST_DESCRIPTION,
    PODCAST_LINK,
    PODCAST_TITLE,
    logger,
    setup_logging,
)

setup_logging()


def get_r2_client():
    """Create S3-compatible R2 client."""
    if not all([R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
        logger.error("R2 credentials not configured (check env vars)")
        return None

    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def upload_to_r2(s3_client, local_path: Path, remote_key: str) -> bool:
    """
    Upload a file to R2.

    Args:
        s3_client: boto3 S3 client
        local_path: Local file path
        remote_key: R2 object key

    Returns:
        True if upload succeeded
    """
    try:
        s3_client.upload_file(
            str(local_path),
            R2_BUCKET_NAME,
            remote_key,
            ExtraArgs={"ContentType": "audio/mpeg", "CacheControl": "public, max-age=86400"},
        )
        logger.info(f"Uploaded: {remote_key}")
        return True
    except Exception as e:
        logger.error(f"R2 upload failed for {remote_key}: {e}")
        return False


def read_summary_md(md_path: Path) -> str:
    """Read summary markdown content."""
    if not md_path.exists():
        return ""
    return md_path.read_text(encoding="utf-8")


def get_done_items_from_db() -> list[dict]:
    """
    Get completed podcast items from DB with their original URLs.
    """
    if not DB_PATH.exists():
        logger.warning(f"DB not found: {DB_PATH}")
        return []

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT title, url, podcast_date
        FROM council_updates
        WHERE podcast_status = 'done'
        ORDER BY podcast_date DESC
    """
    )

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def build_rss_feed(podcast_items: list[dict]) -> str:
    """
    Generate RSS feed XML using feedgen.

    Args:
        podcast_items: List of dicts with keys:
            - title: Episode title
            - url: R2 public URL for MP3
            - description: Summary text (optional)
            - size: File size in bytes
            - pub_date: Publication datetime (optional)

    Returns:
        RSS XML string
    """
    fg = FeedGenerator()
    fg.load_extension("podcast")

    fg.title(PODCAST_TITLE)
    fg.link(href=PODCAST_LINK, rel="alternate")
    fg.description(PODCAST_DESCRIPTION)
    fg.language("ja")
    fg.podcast.itunes_author(PODCAST_AUTHOR)
    fg.podcast.itunes_category("News")
    fg.podcast.itunes_image(href=f"{PODCAST_LINK}cover.png")
    fg.podcast.itunes_explicit("no")

    for item in podcast_items:
        fe = fg.add_entry()
        fe.id(item["url"])
        fe.title(item["title"])
        fe.enclosure(item["url"], str(item.get("size", 0)), "audio/mpeg")

        if item.get("description"):
            fe.description(item["description"])

        if item.get("pub_date"):
            fe.published(item["pub_date"])

    return fg.rss_str(pretty=True).decode("utf-8")


def main():
    logger.info("=== R2 Upload & RSS Generation Start ===")

    s3 = get_r2_client()
    if not s3:
        logger.error("Cannot proceed without R2 client")
        return

    # Collect local MP3 files (ignored by git, so must have been generated this run)
    mp3_files = sorted(PODCASTS_DIR.glob("*.mp3")) if PODCASTS_DIR.exists() else []
    if not mp3_files:
        logger.info("No MP3 files found in podcasts/")
        mp3_files = []

    # Build item map from DB (title -> original_url)
    db_items = get_done_items_from_db()
    url_by_title = {item["title"]: item["url"] for item in db_items}

    # Upload MP3s to R2
    podcast_entries = []
    for mp3_path in mp3_files:
        stem = mp3_path.stem
        remote_key = f"podcasts/{mp3_path.name}"
        r2_url = f"{R2_PUBLIC_URL}/{remote_key}" if R2_PUBLIC_URL else ""

        # Upload
        if s3 and R2_BUCKET_NAME:
            upload_to_r2(s3, mp3_path, remote_key)

        # Find matching summary
        md_path = mp3_path.with_name(f"{stem}_summary.md")
        description = read_summary_md(md_path)
        original_url = url_by_title.get(stem, "")

        # Get file size and mtime
        size = mp3_path.stat().st_size
        mtime = datetime.fromtimestamp(mp3_path.stat().st_mtime, tz=timezone.utc)

        entry = {
            "title": stem,
            "url": r2_url,
            "description": description,
            "size": size,
            "pub_date": mtime,
            "original_url": original_url,
        }
        podcast_entries.append(entry)

    # Also include already-uploaded items from DB that don't have local MP3s
    for item in db_items:
        title = item["title"]
        if not any(e["title"] == title for e in podcast_entries):
            # Construct R2 URL from title pattern
            r2_url = f"{R2_PUBLIC_URL}/podcasts/{title}.mp3" if R2_PUBLIC_URL else ""
            podcast_entries.append(
                {
                    "title": title,
                    "url": r2_url,
                    "description": "",
                    "size": 0,
                    "pub_date": None,
                    "original_url": item.get("url", ""),
                }
            )

    # Sort by pub_date descending (newest first)
    podcast_entries.sort(key=lambda x: x.get("pub_date") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # Generate RSS
    rss_xml = build_rss_feed(podcast_entries)

    # Write to file
    RSS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RSS_OUTPUT_PATH.write_text(rss_xml, encoding="utf-8")
    logger.info(f"RSS feed written to: {RSS_OUTPUT_PATH} ({len(podcast_entries)} items)")

    logger.info("=== Upload & RSS Complete ===")


if __name__ == "__main__":
    main()
