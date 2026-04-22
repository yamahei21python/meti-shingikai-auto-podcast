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
from typing import Optional

import bs4
from bs4 import BeautifulSoup

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import (
    METI_URL,
    PODCASTS_DIR,
    SOCKS5_PROXY,
    NetworkClient,
    format_date_yyyymmdd,
    init_auth,
    run_notebooklm,
    parse_notebook_id,
    parse_task_id,
    wait_for_task,
    logger,
    is_github_actions,
    sanitize_filename,
    setup_logging,
)

setup_logging()

# === Configuration ===
OUTPUT_MP3 = "podcast_summary.mp3"
BASE_URL = "https://www.meti.go.jp"


def fetch_article_page(client: NetworkClient, url: str) -> Optional[BeautifulSoup]:
    """
    Fetch article page and parse with BeautifulSoup.
    Uses shared NetworkClient for session reuse.
    """
    return client.fetch_soup(url)


def download_pdf_locally(client: NetworkClient, url: str, temp_dir: Path) -> Optional[Path]:
    """
    Download PDF file to a local temporary directory.
    """
    filename = sanitize_filename(url.split("/")[-1])
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    
    local_path = temp_dir / filename
    logger.info(f"Downloading PDF: {url} -> {local_path}")
    
    res = client.fetch(url)
    if res and res.status_code == 200:
        with open(local_path, "wb") as f:
            f.write(res.content)
        return local_path
    
    logger.error(f"Failed to download PDF: {url}")
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


def add_source(source_path_or_url: str, max_attempts: int = 3) -> bool:
    """
    Add source (PDF path or URL) to notebook.
    """
    for attempt in range(max_attempts):
        logger.info(f"Adding source: {source_path_or_url} (Attempt {attempt + 1}/{max_attempts})")
        res = run_notebooklm(["source", "add", source_path_or_url])

        if res.returncode == 0:
            return True

        logger.warning(f"Source add failed for {source_path_or_url}")
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

        logger.warning(f"Audio generation start failed (Attempt {attempt + 1}): {res.stderr.strip() if res.stderr else 'unknown'}")
        if attempt < max_attempts - 1:
            time.sleep(30)

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

    # Initialize Network Client
    client = NetworkClient()
    
    try:
        # Step 0: Get PDF URLs
        pdf_urls = []

        if args.pdfs:
            logger.info("Using provided PDF URL list (direct mode)")
            pdf_urls = json.loads(args.pdfs)
        elif args.url:
            soup = fetch_article_page(client, args.url)
            if soup:
                pdf_urls = extract_pdf_urls(args.url, soup)

        if not pdf_urls:
            logger.error("No PDF links found")
            sys.exit(1)

        logger.info(f"Found {len(pdf_urls)} PDF documents")

        # Step 1: Download PDFs to temp directory
        temp_dir = Path("temp_pdfs")
        temp_dir.mkdir(exist_ok=True)
        local_pdfs = []
        
        for url in pdf_urls:
            local_path = download_pdf_locally(client, url, temp_dir)
            if local_path:
                local_pdfs.append(str(local_path))
        
        if not local_pdfs:
            logger.error("Failed to download any PDF documents")
            sys.exit(1)

        # Step 2: Setup Notebook
        notebook_name = (
            args.name or f"METI_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        notebook_id = create_notebook(notebook_name)

        if not notebook_id:
            logger.error("Failed to create notebook")
            sys.exit(1)

        # Step 3: Select Notebook
        run_notebooklm(["use", notebook_id])

        # Step 4: Add Sources (Local Files)
        for pdf_path in local_pdfs:
            if not add_source(pdf_path):
                logger.error(f"Failed to add source: {pdf_path}. Aborting.")
                sys.exit(1)

        # Wait for all sources to finish processing (poll notebook status)
        logger.info("Waiting for sources to be ready...")
        max_source_wait = 600  # 10 minutes max
        poll_start = time.time()
        while time.time() - poll_start < max_source_wait:
            time.sleep(20)
            status_res = run_notebooklm(["artifact", "list", "-n", notebook_id])
            if status_res.returncode == 0 and status_res.stdout.strip():
                # Any output means sources are processed
                break
            logger.info("Sources still processing...")
    finally:
        # Cleanup and close
        client.close()
        
        # Cleanup temp PDFs
        if 'temp_dir' in locals() and temp_dir.exists():
            logger.info("Cleaning up temporary PDF files...")
            for f in temp_dir.glob("*.pdf"):
                try:
                    f.unlink()
                except Exception:
                    pass
            try:
                temp_dir.rmdir()
            except Exception:
                pass

    # Step 4: Generate Audio
    title_context = args.name or "今回の資料"
    prompt = build_prompt(title_context)

    task_id = generate_audio(prompt)
    if not task_id:
        logger.error("Failed to start audio generation")
        sys.exit(1)

    logger.info("Waiting for completion (timeout: 5400s)...")
    success = wait_for_task(task_id, notebook_id=notebook_id)

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
