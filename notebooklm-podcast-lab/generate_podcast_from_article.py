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
# Use system 'uv' by default, fallback to known local path
UV_PATH = "uv"
if not os.getenv("GITHUB_ACTIONS"):
    # Check if 'uv' is in PATH, if not use specific local path
    import shutil
    if not shutil.which("uv"):
        UV_PATH = "/Users/kohei/.local/bin/uv"
BASE_URL = "https://www.meti.go.jp"
OUTPUT_MP3 = "podcast_summary.mp3"

def run_notebooklm(args):
    """Run notebooklm command using direct path if available, or uv run as fallback."""
    # Try to find the exact path for notebooklm in the local .venv
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_bin_path = os.path.join(base_dir, ".venv", "bin", "notebooklm")
    python_bin = sys.executable # Use current python
    
    if os.path.exists(venv_bin_path):
        # Using [python, script_path] to bypass broken shebangs
        cmd = [python_bin, venv_bin_path] + args
    else:
        # Fallback to uv run if uv is available, or just 'notebooklm'
        import shutil
        if shutil.which("uv"):
            cmd = ["uv", "run", "notebooklm"] + args
        else:
            cmd = ["notebooklm"] + args
        
    print(f"[*] Executing: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)

def wait_for_task(task_id, notebook_identifier=None, timeout_seconds=5400, poll_interval=60):
    """Wait for a task to complete by polling status."""
    start_time = time.time()
    print(f"[*] Starting monitoring for task: {task_id} (Timeout: {timeout_seconds}s)")
    
    while time.time() - start_time < timeout_seconds:
        status_args = ["artifact", "poll", task_id]
        if notebook_identifier:
            status_args.extend(["-n", notebook_identifier])
        
        res = run_notebooklm(status_args)
        if res.returncode == 0:
            try:
                # Expecting output like: "Status: RUNNING, Progress: 45%" or similar
                status_out = res.stdout.strip()
                print(f"    [STATUS] {status_out}")
                
                status_upper = status_out.upper()
                if "STATUS='SUCCEEDED'" in status_upper or "STATUS='COMPLETED'" in status_upper:
                    print("[+] Task completed successfully.")
                    return True
                if "STATUS='FAILED'" in status_upper or "STATUS='ERROR'" in status_upper:
                    print(f"[!] Task failed according to status: {status_out}")
                    return False
            except Exception as e:
                print(f"    [!] Warning: Failed to parse status output: {e}")
        else:
            print(f"    [!] Status check command failed (code {res.returncode})")

        time.sleep(poll_interval)
    
    print(f"[!] Monitoring timed out after {timeout_seconds}s")
    return False

def fetch_with_playwright_lite(url, max_attempts=3):
    """Fetch URL using Playwright with adaptive wait and longer timeout."""
    for attempt in range(max_attempts):
        try:
            # Stage 1-2: Be patient, wait for DOM
            # Stage 3: Grab whatever is available
            wait_condition = "domcontentloaded" if attempt < 2 else "commit"
            timeout = 120000 # 120 seconds
            
            print(f"[*] Fetching article with Playwright (attempt {attempt+1}/{max_attempts}, mode: {wait_condition}): {url}")
            with sync_playwright() as p:
                # Use WARP SOCKS5 proxy if available (required for METI on GitHub Actions)
                browser = p.chromium.launch(
                    headless=True,
                    proxy={"server": "socks5://127.0.0.1:40000"}
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    locale="ja-JP"
                )
                page = context.new_page()
                # Do not block JS for now as METI might rely on it for some items
                page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())
                
                response = page.goto(url, wait_until=wait_condition, timeout=timeout)
                
                if response and response.status == 200:
                    time.sleep(2) # Extra buffer for dynamic content
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
                wait_time = 15 * (attempt + 1)
                print(f"[*] Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
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

    # 2. Create Notebook (with retries)
    notebook_id = None
    max_nb_attempts = 3
    for attempt in range(max_nb_attempts):
        print(f"[*] Creating notebook: {notebook_name} (Attempt {attempt+1}/{max_nb_attempts})")
        res = run_notebooklm(["create", notebook_name])
        
        if res.returncode == 0:
            try:
                import re
                match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', res.stdout, re.IGNORECASE)
                if match:
                    notebook_id = match.group(1)
                else:
                    parts = res.stdout.strip().split()
                    if parts:
                        notebook_id = parts[-1]
                
                if notebook_id and len(notebook_id) >= 10:
                    print(f"[+] Notebook created ID: {notebook_id}")
                    print(f"NOTEBOOK_ID={notebook_id}")
                    break
            except Exception as e:
                print(f"[!] Error parsing notebook ID: {e}")
        
        print(f"[!] Failed to create or parse notebook ID (Attempt {attempt+1})")
        if attempt < max_nb_attempts - 1:
            time.sleep(10)
    
    if not notebook_id:
        print("[!] Exhausted all attempts to create notebook. Exiting.")
        sys.exit(1)

    # 3. Select Notebook
    run_notebooklm(["use", notebook_id])

    # 4. Add Sources (with retries per URL)
    for url in pdf_urls:
        max_src_attempts = 3
        success = False
        for attempt in range(max_src_attempts):
            print(f"[*] Adding source: {url} (Attempt {attempt+1}/{max_src_attempts})")
            res = run_notebooklm(["source", "add", url])
            if res.returncode == 0:
                success = True
                break
            print(f"[!] Source add failed for {url}")
            if attempt < max_src_attempts - 1:
                time.sleep(15)
        
        if not success:
            print(f"[!] CRITICAL: Source add failed for {url}. Aborting generation to prevent incomplete podcast.")
            sys.exit(1)
    
    print("[*] Waiting for sources to process (30s)...")
    time.sleep(30)

    # 5. Generate Podcast Audio (with retries for initiation)
    # Use the provided name to anchor the start of the podcast
    title_context = args.name if args.name else "今回の資料"
    prompt = f"""
資料の内容の解析、および解説・対話はすべて日本語で行ってください。

まず最初に、資料のタイトル『{title_context}』をはっきりと明示して、すぐに本題の解析に入ってください。
前置きや一般的な背景説明は最小限に留め、資料の内容に直接関わる核心部分から解説を開始してください。

この審議会資料（PDF）の全内容を技術面・政策面から統合・分析し、日本のエネルギー業界で働く従業員の方々の「知識アップ」に資するポッドキャスト音声を作成してください。
今日の世界的なエネルギー情勢の中で、この会議で議論された技術開発の進展、法規制や基準の改正、現場レベルでの対応が必要なリスク、および今後の具体的スケジュールを多角的に要約・解説してください。
"""
    
    normalized_prompt = " ".join(prompt.strip().split())
    
    task_id = None
    max_gen_attempts = 3
    for attempt in range(max_gen_attempts):
        print(f"[*] Generating podcast audio (Attempt {attempt+1}/{max_gen_attempts})...")
        gen_res = run_notebooklm(["generate", "audio", normalized_prompt, "--language", "ja", "--no-wait"])
        
        if gen_res.returncode == 0:
            import re
            task_match = re.search(r'(?:Task: )?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', gen_res.stdout, re.IGNORECASE)
            if task_match:
                task_id = task_match.group(1)
                print(f"[+] Audio generation started. Task ID: {task_id}")
                break
        
        print(f"[!] Audio generation start failed (Attempt {attempt+1})")
        if attempt < max_gen_attempts - 1:
            time.sleep(20)
            
    if not task_id:
        print("[!] Exhausted all attempts to start audio generation.")
        sys.exit(1)
    print(f"[*] Waiting for completion (Extended timeout: 5400s)...")
    
    # Wait for completion using monitoring loop
    success = wait_for_task(task_id, notebook_identifier=notebook_id, timeout_seconds=5400)
    
    if not success:
        print(f"[!] Audio generation failed or timed out.")
        # Attempt fail-safe download anyway after a small buffer
        print(f"[*] Waiting for an additional 300s buffer before attempting fail-safe download...")
        time.sleep(300)
    else:
        print("[+] Audio generation completed successfully.")

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
