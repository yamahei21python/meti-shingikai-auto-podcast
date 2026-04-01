import os
import sys
import argparse
import subprocess
import time
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

def fetch_with_playwright(url, max_attempts=3):
    """Fetch URL using Playwright with retries."""
    for attempt in range(max_attempts):
        try:
            print(f"[*] Fetching with Playwright (attempt {attempt+1}): {url}")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                # Set a realistic user agent
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                # Wait for network idle to ensure page is loaded
                response = page.goto(url, wait_until="networkidle", timeout=60000)
                
                if response and response.status == 200:
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
                time.sleep(5)
    return None

def extract_pdf_urls(page_url, soup):
    """Extract all PDF links from a METI article page."""
    print(f"[*] Extracting PDF links from soup...")
    # Look for any link that looks like a PDF
    links = soup.find_all('a', href=True)
    pdf_urls = []

    for link in links:
        href = link.get('href')
        # Check for .pdf extension or 'pdf' in the text/href as a fallback
        if href and (href.lower().endswith('.pdf') or '/pdf/' in href.lower()):
            abs_url = urljoin(page_url, href)
            pdf_urls.append(abs_url)

    # Unique
    return list(dict.fromkeys(pdf_urls))

def main():
    parser = argparse.ArgumentParser(description="Generate a podcast from PDF links in a METI article.")
    parser.add_argument("--url", required=True, help="URL of the METI article page")
    parser.add_argument("--name", help="Name of the Notebook (default: random date based)")
    parser.add_argument("--output", default=OUTPUT_MP3, help="Output filename for the MP3")
    args = parser.parse_args()

    soup = fetch_with_playwright(args.url)
    if not soup:
        print("[!] Could not fetch article page with Playwright.")
        sys.exit(1)

    # 1. Extract PDFs
    pdf_urls = extract_pdf_urls(args.url, soup)
    if not pdf_urls:
        print("[!] No PDF links found on the page.")
        sys.exit(1)

    print(f"[+] Found {len(pdf_urls)} PDF documents.")

    # 2. Setup Notebook Title
    notebook_name = args.name or f"METI_Report_Summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 3. Create Notebook
    print(f"[*] Creating notebook: {notebook_name}")
    res = run_notebooklm(["create", notebook_name])
    
    notebook_id = None
    try:
        # Expected output: "Created notebook: <ID> - <Name>"
        if ":" in res.stdout:
            parts = res.stdout.split(":")[1].split("-")
            notebook_id = parts[0].strip()
        else:
            notebook_id = res.stdout.split()[-1].strip()
        
        if not notebook_id or len(notebook_id) < 10: # Basic validation
            raise ValueError("Invalid ID format")
            
        print(f"[+] Notebook created ID: {notebook_id}")
    except Exception as e:
        print(f"[!] Error creating/parsing notebook: {res.stdout}")
        print(f"[!] Stderr: {res.stderr}")
        sys.exit(1)

    # 4. Select Notebook
    run_notebooklm(["use", notebook_id])

    # 5. Add Sources
    for url in pdf_urls:
        print(f"[*] Adding source: {url}")
        run_notebooklm(["source", "add", url])
    
    print("[*] Waiting for sources to process (30s)...")
    time.sleep(30)

    # 6. Generate Podcast Audio
    prompt = """
この審議会資料（PDF）の全内容を統合・分析してください。
投資家や政策担当者が聴くべきポッドキャスト形式で、今日の世界情勢を踏まえた日本の産業・エネルギー政策の重要性と、この会議で議論された具体的なリスクおよび今後の方向性を日本語で詳しく要約して解説してください。
"""
    
    print(f"[*] Generating podcast audio with analyst prompt...")
    gen_res = run_notebooklm(["generate", "audio", prompt, "--wait"])
    
    if gen_res.returncode != 0:
        print(f"[!] Audio generation issue: {gen_res.stderr}")
        sys.exit(1)
    
    # 7. Download
    # Ensure simpler filename for upload reliability
    final_output = "podcast_summary.mp3"
    print(f"[*] Attempting to download podcast to: {final_output}")
    dl_res = run_notebooklm(["download", "audio", final_output])
    
    if dl_res.returncode == 0:
        if os.path.exists(final_output):
            print(f"\n[🎉 SUCCESS] Podcast summary saved to: {os.path.abspath(final_output)}")
            # Rename if needed by user but for now keep it simple for Actions
            if args.output != final_output:
                os.rename(final_output, args.output)
                print(f"[*] Renamed to user requested: {args.output}")
        else:
            print("[!] Download reported success but file not found.")
            sys.exit(1)
    else:
        print(f"[!] Download failed: {dl_res.stderr}")
        sys.exit(1)

if __name__ == "__main__":
    main()
