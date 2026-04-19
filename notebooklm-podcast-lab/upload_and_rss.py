"""
Upload to R2 and generate RSS feed.

Usage:
    python upload_and_rss.py --file path/to/file.mp3
    python upload_and_rss.py --source_url "https://..."
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import boto3
import xml.etree.ElementTree as ET
from botocore.config import Config
from dotenv import load_dotenv
from feedgen.feed import FeedGenerator

# Add parent to path
sys.path.insert(0, ".")

from shared import (
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_ENDPOINT,
    R2_BUCKET_NAME,
    R2_PUBLIC_URL,
    PODCAST_TITLE,
    PODCAST_DESCRIPTION,
    PODCAST_LINK,
    PODCAST_AUTHOR,
    PODCASTS_DIR,
    RSS_OUTPUT_PATH,
    logger,
)

load_dotenv()


def get_s3_client():
    """Get R2 S3 client."""
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_file_if_missing(client, local_path: str, bucket: str, key: str) -> bool:
    """
    Upload file to R2 if not exists.

    Args:
        client: S3 client
        local_path: Local file path
        bucket: R2 bucket name
        key: R2 object key

    Returns:
        True if upload successful or file exists
    """
    try:
        client.head_object(Bucket=bucket, Key=key)
        logger.info(f"File already exists in R2: {key}")
        return True
    except:
        logger.info(f"Uploading to R2: {key}...")
        try:
            with open(local_path, "rb") as f:
                client.put_object(
                    Bucket=bucket, Key=key, Body=f, ContentType="audio/mpeg"
                )
            logger.info(f"Upload complete: {key}")
            return True
        except Exception as e:
            logger.error(f"Error uploading {key}: {e}")
            return False


def load_existing_items(xml_path: str) -> list[dict]:
    """
    Parse existing items from podcast.xml.

    Args:
        xml_path: Path to RSS XML file

    Returns:
        List of item dictionaries
    """
    items = []
    if not os.path.exists(xml_path):
        return items

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        channel = root.find("channel")
        if channel is None:
            return items

        for item in channel.findall("item"):
            title = item.findtext("title")
            link = item.findtext("link")
            description = item.findtext("description")
            pub_date_str = item.findtext("pubDate")

            enclosure = item.find("enclosure")
            url = enclosure.get("url") if enclosure is not None else link
            size = (
                int(enclosure.get("length"))
                if enclosure is not None and enclosure.get("length")
                else 0
            )

            try:
                mtime = datetime.strptime(
                    pub_date_str, "%a, %d %b %Y %H:%M:%S %z"
                ).timestamp()
            except:
                mtime = datetime.now().timestamp()

            items.append(
                {
                    "title": title,
                    "description": description,
                    "url": url,
                    "original_link": link,
                    "size": size,
                    "mtime": mtime,
                }
            )
    except Exception as e:
        logger.warning(f"Failed to parse existing RSS: {e}")

    return items


def generate_rss(files_info: list[dict]) -> None:
    """
    Generate RSS feed file.

    Args:
        files_info: List of file info dictionaries
    """
    fg = FeedGenerator()
    fg.load_extension("podcast")

    fg.title(PODCAST_TITLE)
    fg.description(PODCAST_DESCRIPTION)
    fg.link(href=PODCAST_LINK)
    fg.language("ja")
    fg.podcast.itunes_author(PODCAST_AUTHOR)
    fg.podcast.itunes_image(f"{PODCAST_LINK.rstrip('/')}/cover.png")
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_category("News")

    # Deduplicate by URL, sort by date descending
    seen_urls = set()
    unique_files = []
    sorted_all = sorted(files_info, key=lambda x: x["mtime"], reverse=True)

    for info in sorted_all:
        if info["url"] not in seen_urls:
            unique_files.append(info)
            seen_urls.add(info["url"])

    for info in unique_files:
        fe = fg.add_entry()
        fe.id(info["url"])
        fe.title(info["title"])
        fe.description(info["description"] or info["title"])
        fe.link(href=info.get("original_link") or info["url"])
        fe.pubDate(datetime.fromtimestamp(info["mtime"], tz=timezone.utc))
        fe.enclosure(info["url"], str(info["size"]), "audio/mpeg")
        fe.podcast.itunes_explicit("no")
        fe.podcast.itunes_summary(info["description"] or info["title"])

    fg.rss_file(str(RSS_OUTPUT_PATH), pretty=True)
    logger.info(f"RSS Feed updated: {RSS_OUTPUT_PATH} ({len(unique_files)} items)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Path to a single MP3 file to add")
    parser.add_argument("--source_url", help="Original source URL for the meeting")
    args = parser.parse_args()

    # Check credentials
    if not all([R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, R2_BUCKET_NAME]):
        logger.error("R2 credentials not found in environment")
        return

    s3 = get_s3_client()

    # Load existing items
    files_info = load_existing_items(str(RSS_OUTPUT_PATH))
    logger.info(f"Loaded {len(files_info)} existing items")

    # Process new files
    to_process = []
    if args.file:
        if os.path.exists(args.file):
            to_process.append(os.path.basename(args.file))
        else:
            logger.error(f"File not found: {args.file}")
    else:
        logger.info(f"Scanning directory: {PODCASTS_DIR}")
        if os.path.exists(PODCASTS_DIR):
            to_process = [
                f for f in os.listdir(PODCASTS_DIR) if f.lower().endswith(".mp3")
            ]

    for filename in to_process:
        try:
            local_path = os.path.join(str(PODCASTS_DIR), filename)
            if (
                args.file
                and filename == os.path.basename(args.file)
                and not os.path.exists(local_path)
            ):
                local_path = args.file

            stat = os.stat(local_path)
            r2_key = f"podcasts/{filename}"
            upload_file_if_missing(s3, local_path, R2_BUCKET_NAME, r2_key)

            public_url = f"{R2_PUBLIC_URL.rstrip('/')}/{r2_key}"
            base_name = filename.rsplit(".", 1)[0]

            # Load metadata (original link)
            original_link = args.source_url
            meta_filename = f"{base_name}.json"
            meta_path = os.path.join(os.path.dirname(local_path), meta_filename)
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)
                        original_link = meta_data.get("original_url")
                except Exception as e:
                    logger.warning(f"Failed to read metadata: {e}")

            # Load summary markdown
            description = None
            summary_filename = f"{base_name}_summary.md"
            summary_path = os.path.join(os.path.dirname(local_path), summary_filename)
            if os.path.exists(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    description = f.read()

            files_info.append(
                {
                    "title": base_name,
                    "description": description,
                    "url": public_url,
                    "original_link": original_link,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
            )
            logger.info(f"Added new item: {base_name}")

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")

    # Generate RSS
    if files_info:
        generate_rss(files_info)
    else:
        logger.info("No items found to process")


if __name__ == "__main__":
    main()
