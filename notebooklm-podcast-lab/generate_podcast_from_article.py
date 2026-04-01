import os
import sys
import argparse
import subprocess
import time
import json
from datetime import datetime
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

# Configurations
# Use system 'uv' in GitHub Actions, local path otherwise
UV_PATH = "uv" if os.getenv("GITHUB_ACTIONS") else "/Users/kohei/.local/bin/uv"
BASE_URL = "https://www.meti.go.jp"
OUTPUT_MP3 = "podcast_summary.mp3"

def run_notebooklm(args):
    """Run notebooklm command using uv run"""
    cmd = [UV_PATH, "run", "notebooklm"] + args
    print(f"[*] Executing: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)

def fetch_with_playwright_lite(url, max_attempts=3):
    """Fetch URL using Playwright (fallback mode if PDF list not provided)."""
    for attempt in range(max_attempts):
        try:
            print(f"[*] Fetching article with Playwright (attempt {attempt+1}, lite mode): {url}")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,js}", lambda route: route.abort())
                response = page.goto(url, wait_until="commit", timeout=60000)
                
                if response and response.status == 200:
                    time.sleep(1) 
                    content = page.content()
                    browser.close()
                    from bs4 import BeautifulSoup
                    return BeautifulSoup(content, 'html.parser')
                else:
                    status = response.status if response else "No response"
                    print(f"[!] Received status {status} for {url}")
                    browser.close()
        except Exception as e:
            print(f"[!] Attempt {attempt+1} failed: {e}")
            if attempt < max_attempts - 1:
                time.sleep(10)
    return None

def extract_pdf_urls(page_url, soup):
    """Extract all PDF links from a METI article page."""
    print(f"[*] Extracting PDF links from soup...")
    links = soup.find_all('a', href=True)
    pdf_urls = []
    for link in links:
        href = link.get('href')
        if href and (href.lower().endswith('.pdf') or '/pdf/' in href.lower()):
            abs_url = urljoin(page_url, href)
            pdf_urls.append(abs_url)
    return list(dict.fromkeys(pdf_urls))

def main():
    parser = argparse.ArgumentParser(description="Generate a podcast from PDF links.")
    parser.add_argument("--url", help="URL of the METI article page (context only)")
    parser.add_argument("--pdfs", help="JSON string of PDF URLs to process directly")
    parser.add_argument("--name", help="Name of the Notebook")
    parser.add_argument("--output", default=OUTPUT_MP3, help="Output filename for the MP3")
    args = parser.parse_args()

    pdf_urls = []
    if args.pdfs:
        # Step 0: Use provided PDF list directly (Robust for Cloud)
        print("[*] Using provided PDF URL list (direct mode).")
        pdf_urls = json.loads(args.pdfs)
    elif args.url:
        # Fallback: Scrape if not provided (Local mode)
        soup = fetch_with_playwright_lite(args.url)
        if soup:
            pdf_urls = extract_pdf_urls(args.url, soup)
    
    if not pdf_urls:
        print("[!] No PDF links found on the page or provided.")
        sys.exit(1)

    print(f"[+] Found {len(pdf_urls)} PDF documents.")

    # 1. Setup Notebook Title
    notebook_name = args.name or f"METI_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 2. Create Notebook
    print(f"[*] Creating notebook: {notebook_name}")
    res = run_notebooklm(["create", notebook_name])
    
    notebook_id = None
    try:
        if ":" in res.stdout:
            parts = res.stdout.split(":")[1].split("-")
            notebook_id = parts[0].strip()
        else:
            notebook_id = res.stdout.split()[-1].strip()
        
        if not notebook_id or len(notebook_id) < 10: 
            raise ValueError("Invalid ID format")
        print(f"[+] Notebook created ID: {notebook_id}")
    except Exception as e:
        print(f"[!] Error creating/parsing notebook: {res.stdout}")
        sys.exit(1)

    # 3. Select Notebook
    run_notebooklm(["use", notebook_id])

    # 4. Add Sources
    for url in pdf_urls:
        print(f"[*] Adding source: {url}")
        run_notebooklm(["source", "add", url])
    
    print("[*] Waiting for sources to process (30s)...")
    time.sleep(30)

    # 5. Generate Podcast Audio
    prompt = """
この審議会資料（PDF）の全内容を技術面・政策面から統合・分析し、日本のエネルギー業界で働く従業員の方々の「知識アップ」に資するポッドキャスト音声を作成してください。
今日の世界的なエネルギー情勢の中で、この会議で議論された技術開発の進展、法規制や基準の改正、現場レベルでの対応が必要なリスク、および今後の具体的スケジュールを多角的に要約・解説してください。
"""
    
    print(f"[*] Generating podcast audio with analyst prompt...")
    gen_res = run_notebooklm(["generate", "audio", prompt, "--wait"])
    
    if gen_res.returncode != 0:
        print(f"[!] Audio generation issue: {gen_res.stderr}")
        sys.exit(1)
    
    # 6. Download
    final_output = "podcast_summary.mp3"
    print(f"[*] Attempting to download podcast to: {final_output}")
    dl_res = run_notebooklm(["download", "audio", final_output])
    
    if dl_res.returncode == 0:
        if os.path.exists(final_output):
            print(f"\n[🎉 SUCCESS] Podcast summary saved to: {os.path.abspath(final_output)}")
            if args.output != final_output:
                if os.path.exists(args.output):
                    os.remove(args.output)
                os.rename(final_output, args.output)
                print(f"[*] Renamed to display requested: {args.output}")
        else:
            print("[!] Download reported success but file not found.")
            sys.exit(1)
    else:
        print(f"[!] Download failed: {dl_res.stderr}")
        sys.exit(1)

if __name__ == "__main__":
    main()
