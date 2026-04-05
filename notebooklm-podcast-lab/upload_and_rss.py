import os
import boto3
import argparse
from botocore.config import Config
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import hashlib
from dotenv import load_dotenv
import xml.etree.ElementTree as ET

# Load configuration
load_dotenv()

R2_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET = os.getenv("R2_SECRET_ACCESS_KEY")
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_BUCKET = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")

PODCAST_TITLE = os.getenv("PODCAST_TITLE", "Energy Audio | METI AI Podcast")
PODCAST_DESCRIPTION = os.getenv("PODCAST_DESCRIPTION", "経済産業省のエネルギー政策審議会をAIで読み解く、エネルギードメイン特化型ポッドキャスト")
PODCAST_LINK = os.getenv("PODCAST_LINK", "https://energy-audio.vercel.app/")
RSS_FILENAME = os.getenv("RSS_FILENAME", "podcast.xml")

# Local directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PODCASTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "podcasts")
RSS_OUT_PATH = os.path.join(os.path.dirname(BASE_DIR), RSS_FILENAME)

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ID,
        aws_secret_access_key=R2_SECRET,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )

def upload_file_if_missing(client, local_path, bucket, key):
    try:
        client.head_object(Bucket=bucket, Key=key)
        print(f"[-] File already exists in R2: {key}")
        return True
    except:
        print(f"[*] Uploading to R2: {key}...", flush=True)
        try:
            with open(local_path, "rb") as f:
                client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType="audio/mpeg"
                )
            print(f"[+] Upload complete: {key}", flush=True)
            return True
        except Exception as e:
            print(f"[!] Error uploading {key}: {e}", flush=True)
            return False

def load_existing_items(xml_path):
    """Parse existing items from podcast.xml to preserve history."""
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
            size = int(enclosure.get("length")) if enclosure is not None and enclosure.get("length") else 0
            
            # Use original pubDate if possible
            try:
                # RFC 2822: 'Sat, 04 Apr 2026 10:14:00 +0000'
                mtime = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z").timestamp()
            except:
                mtime = datetime.now().timestamp()
                
            items.append({
                "title": title,
                "description": description,
                "url": url,
                "size": size,
                "mtime": mtime
            })
    except Exception as e:
        print(f"[!] Warning: Failed to parse existing RSS: {e}")
    
    return items

def generate_rss(files_info):
    fg = FeedGenerator()
    fg.load_extension('podcast')
    
    fg.title(PODCAST_TITLE)
    fg.description(PODCAST_DESCRIPTION)
    fg.link(href=PODCAST_LINK)
    fg.language('ja')
    fg.podcast.itunes_author(os.getenv("PODCAST_AUTHOR", "Kohei"))
    fg.podcast.itunes_image(url=f"{PODCAST_LINK.rstrip('/')}/cover.png")
    fg.podcast.itunes_explicit('no')
    fg.podcast.itunes_category('News')

    # Deduplicate by URL and sort by date descending
    seen_urls = set()
    unique_files = []
    # Sort entries by mtime first so when we deduplicate we keep the latest if duplicates exist
    sorted_all = sorted(files_info, key=lambda x: x['mtime'], reverse=True)
    
    for info in sorted_all:
        if info['url'] not in seen_urls:
            unique_files.append(info)
            seen_urls.add(info['url'])

    for info in unique_files:
        fe = fg.add_entry()
        fe.id(info['url'])
        fe.title(info['title'])
        fe.description(info['description'] or info['title'])
        fe.link(href=info['url'])
        fe.pubDate(datetime.fromtimestamp(info['mtime'], tz=timezone.utc))
        fe.enclosure(info['url'], str(info['size']), 'audio/mpeg')
        fe.podcast.itunes_explicit('no')
        fe.podcast.itunes_summary(info['description'] or info['title'])

    fg.rss_file(RSS_OUT_PATH, pretty=True)
    print(f"[+] RSS Feed updated at: {RSS_OUT_PATH} ({len(unique_files)} items total)")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Path to a single MP3 file to add")
    args = parser.parse_args()

    if not all([R2_ID, R2_SECRET, R2_ENDPOINT, R2_BUCKET]):
        print("[!] Error: Cloudflare R2 credentials not found in environment.")
        return

    s3 = get_s3_client()
    
    # 1. Load history
    files_info = load_existing_items(RSS_OUT_PATH)
    print(f"[*] Loaded {len(files_info)} existing items from {RSS_FILENAME}")

    # 2. Process new file(s)
    to_process = []
    if args.file:
        if os.path.exists(args.file):
            to_process.append(os.path.basename(args.file))
        else:
            print(f"[!] Error: Specified file not found: {args.file}")
    else:
        # Fallback to scanning directory (local mode)
        print(f"[*] No specific file provided. Scanning directory: {PODCASTS_DIR}")
        if os.path.exists(PODCASTS_DIR):
            to_process = [f for f in os.listdir(PODCASTS_DIR) if f.lower().endswith(".mp3")]

    for filename in to_process:
        try:
            local_path = os.path.join(PODCASTS_DIR, filename)
            # If the file was passed directly and is not in PODCASTS_DIR, use specified path
            if args.file and filename == os.path.basename(args.file) and not os.path.exists(local_path):
                local_path = args.file

            stat = os.stat(local_path)
            r2_key = f"podcasts/{filename}"
            upload_file_if_missing(s3, local_path, R2_BUCKET, r2_key)
            
            public_url = f"{R2_PUBLIC_URL.rstrip('/')}/{r2_key}"
            base_name = filename.rsplit(".", 1)[0]
            
            description = None
            summary_filename = f"{base_name}_summary.md"
            summary_path = os.path.join(os.path.dirname(local_path), summary_filename)
            if os.path.exists(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    description = f.read()
            
            files_info.append({
                "title": base_name,
                "description": description,
                "url": public_url,
                "size": stat.st_size,
                "mtime": stat.st_mtime
            })
            print(f"[+] Added new item: {base_name}")
        except Exception as e:
            print(f"[!] Error processing {filename}: {e}")

    # 3. Generate RSS
    if files_info:
        generate_rss(files_info)
    else:
        print("[-] No items found to process.")

if __name__ == "__main__":
    main()
