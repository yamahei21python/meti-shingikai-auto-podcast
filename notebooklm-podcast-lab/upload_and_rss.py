"""
Upload podcast MP3s to Cloudflare R2 and regenerate RSS feed.

Reads DB for completed items + local podcasts/ directory,
uploads MP3s to R2, and generates podcast.xml using feedgen.

Usage:
    python upload_and_rss.py
"""

import os
import re
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
    format_date_yyyymmdd,
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


def _normalize_for_compare(text: str) -> str:
    """Normalize spaces/underscores for title comparison."""
    return text.replace("_", " ").replace("　", " ").strip()


def extract_date_and_title(stem: str, db_items: list[dict]) -> tuple[str, dict | None]:
    """
    Extract date prefix from stem and match against DB title.

    Args:
        stem: MP3 filename without extension (e.g. "20260216_第116回_...")
        db_items: List of DB dicts with 'title' key

    Returns:
        (display_title, matched_db_item or None)
        display_title includes date prefix if found in stem
    """
    date_prefix = ""
    bare_title = stem

    m = re.match(r"^(\d{8})_(.+)$", stem)
    if m:
        date_prefix = m.group(1) + "_"
        bare_title = m.group(2)

    # Compare normalized forms (space/underscore unified)
    normalized_stem = _normalize_for_compare(bare_title)
    for item in db_items:
        if normalized_stem == _normalize_for_compare(item["title"]):
            return date_prefix + item["title"], item

    return stem, None


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
        SELECT title, url, podcast_date, date, r2_filename
        FROM council_updates
        WHERE podcast_status = 'done'
        ORDER BY podcast_date DESC
    """
    )

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _ensure_tz_aware(dt):
    """Normalize pub_date to timezone-aware datetime.

    Accepts: datetime (naive or aware), ISO string, or None.
    """
    if dt is None:
        return datetime.now(timezone.utc)
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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
    fg.podcast.itunes_image(f"{PODCAST_LINK}cover.png")
    fg.podcast.itunes_explicit("no")

    for item in podcast_items:
        fe = fg.add_entry()
        fe.id(item["url"])
        fe.title(item["title"])
        fe.enclosure(item["url"], str(item.get("size", 0)), "audio/mpeg")

        # Set description from summary.md (feedgen skips empty strings)
        description_text = item.get("description", "") or "No summary available."
        fe.description(description_text)

        if item.get("pub_date"):
            fe.published(_ensure_tz_aware(item["pub_date"]))

    return fg.rss_str(pretty=True).decode("utf-8")


def main():
    logger.info("=== R2 Upload & RSS Generation Start ===")

    s3 = get_r2_client()
    if not s3:
        logger.warning("R2 client not available. Skipping uploads but proceeding to RSS generation.")

    # Collect local MP3 files (ignored by git, so must have been generated this run)
    mp3_files = sorted(PODCASTS_DIR.glob("*.mp3")) if PODCASTS_DIR.exists() else []
    if not mp3_files:
        logger.info("No MP3 files found in podcasts/")
        mp3_files = []

    # Build item list from DB for title matching
    db_items = get_done_items_from_db()

    # Fallback publication date (used only when DB has no podcast_date)
    fallback_now = datetime.now(timezone.utc)

    # Upload MP3s to R2
    podcast_entries = []
    for mp3_path in mp3_files:
        stem = mp3_path.stem
        remote_key = f"podcasts/{mp3_path.name}"
        r2_url = f"{R2_PUBLIC_URL}/{remote_key}" if R2_PUBLIC_URL else ""

        # Upload
        if s3 and R2_BUCKET_NAME:
            upload_to_r2(s3, mp3_path, remote_key)

        # Match stem against DB title (handles date prefix + space/underscore diff)
        display_title, matched_db = extract_date_and_title(stem, db_items)

        # Find matching summary
        md_path = mp3_path.with_name(f"{stem}_summary.md")
        description = read_summary_md(md_path)
        original_url = matched_db["url"] if matched_db else ""

        # Get file size
        size = mp3_path.stat().st_size

        # Use actual podcast_date from DB, fallback to current time
        pub_date = matched_db.get("podcast_date") if matched_db else fallback_now

        entry = {
            "title": display_title,
            "url": r2_url,
            "description": description,
            "size": size,
            "pub_date": pub_date,
            "original_url": original_url,
        }
        podcast_entries.append(entry)

    # Also include already-uploaded items from DB that don't have local MP3s
    # Scan podcasts/ for matching summary.md files by title substring match
    summary_files = (
        list(PODCASTS_DIR.glob("*_summary.md")) if PODCASTS_DIR.exists() else []
    )

    for item in db_items:
        title = item["title"]
        # Skip if already added from local MP3
        if not any(_normalize_for_compare(e["title"]) == _normalize_for_compare(title) for e in podcast_entries):
            # Date prefix for display: use council date (from DB `date` column)
            council_date = item.get("date", "") or ""
            date_prefix = ""
            if council_date:
                date_prefix = format_date_yyyymmdd(council_date[:10]) + "_"
            display_title = date_prefix + title

            # R2 URL: r2_filename from DB if available, else construct from council date
            r2_filename = item.get("r2_filename") or ""
            if r2_filename:
                r2_url = f"{R2_PUBLIC_URL}/podcasts/{r2_filename}" if R2_PUBLIC_URL else ""
            else:
                sanitized = title.replace(" ", "_").replace("　", "_")
                r2_url = f"{R2_PUBLIC_URL}/podcasts/{date_prefix}{sanitized}.mp3" if R2_PUBLIC_URL else ""

            # Try to find matching summary.md by title substring
            normalized_title = title.replace(" ", "_").replace("　", "_")
            description = ""
            for md_path in summary_files:
                if normalized_title in md_path.stem:
                    description = read_summary_md(md_path)
                    break

            podcast_entries.append(
                {
                    "title": display_title,
                    "url": r2_url,
                    "description": description,
                    "size": 0,
                    "pub_date": item.get("podcast_date") or fallback_now,
                    "original_url": item.get("url", ""),
                }
            )

    # Sort by title descending (to maintain order by the date in the title)
    podcast_entries.sort(key=lambda x: x.get("title", ""), reverse=True)

    # Generate RSS
    rss_xml = build_rss_feed(podcast_entries)

    # Write to file
    RSS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RSS_OUTPUT_PATH.write_text(rss_xml, encoding="utf-8")
    logger.info(f"RSS feed written to: {RSS_OUTPUT_PATH} ({len(podcast_entries)} items)")

    logger.info("=== Upload & RSS Complete ===")


if __name__ == "__main__":
    main()
