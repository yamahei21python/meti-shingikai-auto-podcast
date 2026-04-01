import os
import sys
import argparse
import requests
from bs4 import BeautifulSoup
import subprocess
import time
from datetime import datetime

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

def extract_pdf_urls(page_url):
    """Extract all PDF links from a METI article page."""
    print(f"[*] Extracting PDF links from: {page_url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(page_url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except Exception as e:
        print(f"[!] Error fetching article page: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    # Look for any link that looks like a PDF
    links = soup.find_all('a', href=True)
    pdf_urls = []

    for link in links:
        href = link.get('href')
        # Check for .pdf extension or 'pdf' in the text/href as a fallback
        if href and (href.lower().endswith('.pdf') or '/pdf/' in href.lower()):
            if href.startswith('/'):
                abs_url = BASE_URL + href
            elif href.startswith('http'):
                abs_url = href
            else:
                # Relative to current page
                abs_url = page_url.rsplit('/', 1)[0] + '/' + href
            pdf_urls.append(abs_url)

    # Unique
    return list(dict.fromkeys(pdf_urls))

def main():
    parser = argparse.ArgumentParser(description="Generate a podcast from PDF links in a METI article.")
    parser.add_argument("--url", required=True, help="URL of the METI article page")
    parser.add_argument("--name", help="Name of the Notebook (default: random date based)")
    parser.add_argument("--output", default=OUTPUT_MP3, help="Output filename for the MP3")
    args = parser.parse_args()

    # 1. Extract PDFs
    pdf_urls = extract_pdf_urls(args.url)
    if not pdf_urls:
        print("[!] No PDF links found on the page.")
        return

    print(f"[+] Found {len(pdf_urls)} PDF documents.")

    # 2. Setup Notebook Title
    notebook_name = args.name or f"METI_Report_Summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 3. Create Notebook
    print(f"[*] Creating notebook: {notebook_name}")
    res = run_notebooklm(["create", notebook_name])
    if res.returncode != 0:
        print(f"[!] Error creating notebook: {res.stderr}")
        return
    
    try:
        # Expected output: "Created notebook: <ID> - <Name>"
        # Handle cases where the output might vary
        if ":" in res.stdout:
            parts = res.stdout.split(":")[1].split("-")
            notebook_id = parts[0].strip()
        else:
            # Fallback for different CLI output versions
            notebook_id = res.stdout.split()[-1].strip()
        
        if not notebook_id:
            raise ValueError("Empty ID")
            
        print(f"[+] Notebook created ID: {notebook_id}")
    except Exception as e:
        print(f"[!] Could not parse notebook ID from: {res.stdout}")
        print(f"[!] Stderr: {res.stderr}")
        return

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
    
    # 7. Download
    print(f"[*] Attempting to download podcast to: {args.output}")
    dl_res = run_notebooklm(["download", "audio", args.output])
    
    if dl_res.returncode == 0:
        print(f"\n[🎉 SUCCESS] Podcast summary saved to: {os.path.abspath(args.output)}")
        # GitHub Actions用にファイル名を出力
        print(f"EXPORT_FILENAME={args.output}")
    else:
        print(f"[!] Download failed: {dl_res.stderr}")

if __name__ == "__main__":
    main()
