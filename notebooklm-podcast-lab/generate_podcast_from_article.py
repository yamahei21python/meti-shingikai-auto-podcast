"""
Generate Podcast from PDF links using NotebookLM.

Usage:
    python generate_podcast_from_article.py --url "https://..."
    python generate_podcast_from_article.py --pdfs '["url1", "url2"]' --name "Custom Name"
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import bs4
import curl_requests
from bs4 import BeautifulSoup

# Add parent to path
sys.path.insert(0, ".")

from shared import (
    METI_URL,
    SOCKS5_PROXY,
    init_auth,
    run_notebooklm,
    parse_notebook_id,
    parse_task_id,
    wait_for_task,
    logger,
    is_github_actions,
)

# === Configuration ===
OUTPUT_MP3 = "podcast_summary.mp3"
BASE_URL = "https://www.meti.go.jp"


def fetch_article_page(url: str) -> BeautifulSoup | None:
    """
    Fetch article page using curl-cffi.

    Args:
        url: Article URL

    Returns:
        BeautifulSoup object or None on failure
    """
    proxies = None
    if is_github_actions() or os.path.exists("/usr/bin/warp-cli"):
        proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}

    # === IMPORTANT: Header Matching Strategy ===
    # curl-cffiの 'impersonate' で指定したブラウザバージョン（ここではchrome120）と、
    # 'headers' 内の User-Agent および Client Hints (sec-ch-*) は必ず一致させる必要があります。
    # 
    # [理由] TLSフィンガープリント（通信の癖）と自己申告（UA）が矛盾すると、 WAFによってボットと判定され
    # METIサイトから 403 Forbidden を返されます。そのため、UAのランダム化は行わないでください。
    # ===========================================
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    for attempt in range(3):
        try:
            logger.info(f"Fetching article (attempt {attempt + 1}/3): {url}")
            response = curl_requests.get(
                url,
                impersonate="chrome120",
                timeout=30,
                proxies=proxies,
                headers=headers,
            )

            if response.status_code == 200:
                return BeautifulSoup(response.content, "html.parser")

            logger.warning(f"Status {response.status_code} for {url}")
            if response.status_code == 403:
                logger.warning("403 Forbidden - METI security blocking")

        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")

        if attempt < 2:
            wait_time = 15 * (attempt + 1)
            logger.info(f"Waiting {wait_time}s before retry...")
            time.sleep(wait_time)

    return None


def extract_pdf_urls(page_url: str, soup: BeautifulSoup) -> list[str]:
    """
    Extract PDF links from article page.

    Args:
        page_url: Original page URL
        soup: BeautifulSoup object

    Returns:
        List of absolute PDF URLs
    """
    logger.info("Extracting PDF links...")
    links = soup.find_all("a", href=True)
    pdf_urls = []

    for link in links:
        href = link.get("href")
        if href and (href.lower().endswith(".pdf") or "/pdf/" in href.lower()):
            abs_url = urljoin(page_url, href)
            pdf_urls.append(abs_url)

    # Deduplicate while preserving order
    return list(dict.fromkeys(pdf_urls))


def create_notebook(name: str, max_attempts: int = 3) -> str | None:
    """
    Create a new NotebookLM notebook.

    Args:
        name: Notebook name
        max_attempts: Maximum retry attempts

    Returns:
        Notebook ID or None on failure
    """
    for attempt in range(max_attempts):
        logger.info(f"Creating notebook: {name} (Attempt {attempt + 1}/{max_attempts})")
        res = run_notebooklm(["create", name])

        if res.returncode == 0:
            notebook_id = parse_notebook_id(res.stdout)
            if notebook_id and len(notebook_id) >= 10:
                logger.info(f"Notebook created: {notebook_id}")
                print(f"NOTEBOOK_ID={notebook_id}")
                return notebook_id

        logger.warning(f"Failed to create notebook (Attempt {attempt + 1})")
        if attempt < max_attempts - 1:
            time.sleep(10)

    return None


def add_source(url: str, max_attempts: int = 3) -> bool:
    """
    Add source URL to notebook.

    Args:
        url: PDF URL to add
        max_attempts: Maximum retry attempts

    Returns:
        True if successful
    """
    for attempt in range(max_attempts):
        logger.info(f"Adding source: {url} (Attempt {attempt + 1}/{max_attempts})")
        res = run_notebooklm(["source", "add", url])

        if res.returncode == 0:
            return True

        logger.warning(f"Source add failed for {url}")
        if attempt < max_attempts - 1:
            time.sleep(15)

    return False


def generate_audio(prompt: str, max_attempts: int = 3) -> str | None:
    """
    Start audio generation task.

    Args:
        prompt: Generation prompt
        max_attempts: Maximum retry attempts

    Returns:
        Task ID or None on failure
    """
    normalized_prompt = " ".join(prompt.strip().split())

    for attempt in range(max_attempts):
        logger.info(f"Generating audio (Attempt {attempt + 1}/{max_attempts})...")
        res = run_notebooklm(
            ["generate", "audio", normalized_prompt, "--language", "ja", "--no-wait"]
        )

        if res.returncode == 0:
            task_id = parse_task_id(res.stdout)
            if task_id:
                logger.info(f"Audio generation started. Task ID: {task_id}")
                return task_id

        logger.warning(f"Audio generation start failed (Attempt {attempt + 1})")
        if attempt < max_attempts - 1:
            time.sleep(20)

    return None


def download_audio(output_filename: str) -> bool:
    """
    Download generated audio file.

    Args:
        output_filename: Output file path

    Returns:
        True if successful
    """
    logger.info(f"Downloading audio to: {output_filename}")
    res = run_notebooklm(["download", "audio", output_filename])

    if res.returncode == 0:
        if os.path.exists(output_filename):
            logger.info(f"Podcast saved to: {os.path.abspath(output_filename)}")
            return True
        else:
            logger.error("Download reported success but file not found")
    else:
        logger.error(f"Download failed: {res.stderr}")

    return False


def build_prompt(title_context: str) -> str:
    """
    Build generation prompt for podcast.

    Args:
        title_context: Title context for the podcast

    Returns:
        Formatted prompt string
    """
    return f"""
資料の内容の解析、および解説・対話はすべて日本語で行ってください。

まず最初に、資料のタイトル『{title_context}』をはっきりと明示して、すぐに本題の解析に入ってください。
前置きや一般的な背景説明は最小限に留め、資料の内容に直接関わる核心部分から解説を開始してください。

この審議会資料（PDF）の全内容を技術面・政策面から統合・分析し、日本のエネルギー業界で働く従業員の方々の「知識アップ」に資するポッドキャスト音声を作成してください。
今日の世界的なエネルギー情勢の中で、この会議で議論された技術開発の進展、法規制や基準の改正、現場レベルでの対応が必要なリスク、および今後の具体的スケジュールを多角的に要約・解説してください。
""".strip()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate a podcast from PDF links.")
    parser.add_argument("--url", help="URL of the METI article page")
    parser.add_argument("--pdfs", help="JSON string of PDF URLs")
    parser.add_argument("--name", help="Name of the Notebook")
    parser.add_argument("--output", default=OUTPUT_MP3, help="Output filename for MP3")
    args = parser.parse_args()

    # Initialize auth
    init_auth()

    # Step 0: Get PDF URLs
    pdf_urls = []

    if args.pdfs:
        logger.info("Using provided PDF URL list (direct mode)")
        pdf_urls = json.loads(args.pdfs)
    elif args.url:
        soup = fetch_article_page(args.url)
        if soup:
            pdf_urls = extract_pdf_urls(args.url, soup)

    if not pdf_urls:
        logger.error("No PDF links found")
        sys.exit(1)

    logger.info(f"Found {len(pdf_urls)} PDF documents")

    # Step 1: Setup Notebook
    notebook_name = (
        args.name or f"METI_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    notebook_id = create_notebook(notebook_name)

    if not notebook_id:
        logger.error("Failed to create notebook")
        sys.exit(1)

    # Step 2: Select Notebook
    run_notebooklm(["use", notebook_id])

    # Step 3: Add Sources
    for url in pdf_urls:
        if not add_source(url):
            logger.error(f"Failed to add source: {url}. Aborting.")
            sys.exit(1)

    logger.info("Waiting for sources to process (30s)...")
    time.sleep(30)

    # Step 4: Generate Audio
    title_context = args.name or "今回の資料"
    prompt = build_prompt(title_context)

    task_id = generate_audio(prompt)
    if not task_id:
        logger.error("Failed to start audio generation")
        sys.exit(1)

    logger.info("Waiting for completion (timeout: 5400s)...")
    success = wait_for_task(task_id, notebook_identifier=notebook_id)

    if not success:
        logger.warning("Audio generation failed or timed out. Waiting 300s buffer...")
        time.sleep(300)
    else:
        logger.info("Audio generation completed successfully")

    # Step 5: Download
    final_output = "podcast_summary.mp3"
    if not download_audio(final_output):
        sys.exit(1)

    # Rename to requested output if different
    if args.output != final_output:
        if os.path.exists(args.output):
            os.remove(args.output)
        os.rename(final_output, args.output)
        logger.info(f"Renamed to: {args.output}")


if __name__ == "__main__":
    main()
