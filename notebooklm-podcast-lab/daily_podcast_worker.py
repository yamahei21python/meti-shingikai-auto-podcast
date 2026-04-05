import sqlite3
import subprocess
import os
import sys
import re
import time
from datetime import datetime

# --- 設定 ---
DB_PATH = "../councils.db"

def init_notebooklm_auth():
    """Ensure notebooklm auth file exists if secret is provided in ENV."""
    auth_json = os.getenv("NOTEBOOKLM_AUTH_JSON")
    if not auth_json:
        return
        
    # The default location for notebooklm-py auth is ~/.notebooklm/auth.json
    home = os.path.expanduser("~")
    auth_dir = os.path.join(home, ".notebooklm")
    auth_path = os.path.join(auth_dir, "auth.json")
    
    if os.path.exists(auth_path):
        return

    print(f"[*] Initializing NotebookLM auth at {auth_path}...")
    if not os.path.exists(auth_dir):
        os.makedirs(auth_dir)
    
    with open(auth_path, "w", encoding="utf-8") as f:
        f.write(auth_json)
    print("[+] Auth file created successfully.")

def sanitize_filename(text):
    """Remove invalid characters and limit length."""
    text = re.sub(r'[\\/:*?"<>|／]', '', text)
    text = text.replace(' ', '_').replace('　', '_')
    return text[:200]

def get_oldest_pending():
    """Get the oldest pending item with PDF URLs."""
    if not os.path.exists(DB_PATH):
        print(f"[!] Database not found at {DB_PATH}")
        return None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Process oldest first (FIFO)
    cursor.execute("""
        SELECT id, title, url, date, pdf_urls 
        FROM council_updates 
        WHERE podcast_status = 'pending' 
        ORDER BY date ASC, id ASC 
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row

def update_status(item_id, status):
    """Update item status in DB."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute("""
        UPDATE council_updates 
        SET podcast_status = ?, podcast_date = ? 
        WHERE id = ?
    """, (status, now, item_id))
        
    conn.commit()
    conn.close()

def format_date_yyyymmdd(date_str):
    """Convert 'YYYY-MM-DD' or Japanese date string to 'YYYYMMDD'."""
    try:
        # If already YYYY-MM-DD
        if '-' in date_str:
            return date_str.replace('-', '')
        
        # Fallback for old formats (should not happen with new DB but just in case)
        nums = re.findall(r'\d+', date_str)
        if len(nums) >= 3:
            year, month, day = nums[0], nums[1], nums[2]
            return f"{int(year):04d}{int(month):02d}{int(day):02d}"
    except Exception:
        pass
    # Fallback to current date if parsing fails
    return datetime.now().strftime('%Y%m%d')

def main():
    print(f"=== Daily Podcast Worker Start: {datetime.now()} ===")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # --- GitHub Actions / Cloud Environment Hardening ---
    init_notebooklm_auth()

    item = get_oldest_pending()
    if not item:
        print("[*] No pending items in the queue.")
        return

    item_id, title, url, date_str, pdf_urls_json = item
    print(f"[*] Found pending item: {title} ({url})")
    
    # Use simpler filename for cloud stability
    output_filename = "podcast_summary.mp3"
    
    # 20260306_Title format as requested
    formatted_date = format_date_yyyymmdd(date_str)
    
    # Construct a descriptive notebook name
    notebook_name_raw = f"{formatted_date}_{title}"
    notebook_name = sanitize_filename(notebook_name_raw)
    
    # Use current python executable to ensure environment consistency
    python_bin = sys.executable

    # Pass PDF URLs directly to bypass cloud-side scraping
    cmd = [
        python_bin, "generate_podcast_from_article.py",
        "--url", url,
        "--output", output_filename,
        "--name", notebook_name
    ]
    if pdf_urls_json:
        cmd.extend(["--pdfs", pdf_urls_json])
    
    print(f"[*] Executing Generator (Direct PDF mode): {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        
        if result.returncode == 0:
            update_status(item_id, 'done')
            
            # --- Capture NOTEBOOK_ID from stdout ---
            captured_id = None
            for line in result.stdout.splitlines():
                if line.startswith("NOTEBOOK_ID="):
                    captured_id = line.split("=", 1)[1].strip()
                    break
            
            # Fallback to notebook_name (title) if UUID not captured
            notebook_identifier = captured_id if captured_id else notebook_name
            if captured_id:
                print(f"[+] Captured Notebook UUID: {captured_id}")
            else:
                print(f"[!] Warning: Could not capture Notebook UUID. Falling back to title: {notebook_name}")
            
            # Format filename as requested: 20260306_Title.mp3
            display_name = f"{formatted_date}_{sanitize_filename(title)}.mp3"
            
            # Local file management: move to podcasts/ directory
            target_dir = "../podcasts"
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            
            target_path = os.path.join(target_dir, display_name)
            if os.path.exists(output_filename):
                if os.path.exists(target_path):
                    os.remove(target_path)
                os.rename(output_filename, target_path)
                print(f"\n[🎉 SUCCESS] Podcast saved locally to: {os.path.abspath(target_path)}")
                # IMPORTANT for GitHub Actions: Output the relative path to be captured
                print(f"PODCAST_ASSET_PATH={target_path}")
                
                # --- NEW: Generate Text Summary ---
                summary_filename = f"{formatted_date}_{sanitize_filename(title)}_summary.md"
                summary_path = os.path.join(target_dir, summary_filename)
                generate_summary_report(notebook_id=notebook_identifier, target_path=summary_path)
            else:
                print(f"[!] Warning: {output_filename} not found after successful generation.")
            
            # --- Cleanup Old Notebooks ---
            cleanup_old_notebooks(days=7)
            
        else:
            print(f"[!] Error during podcast generation.")
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            update_status(item_id, 'failed')
            sys.exit(1)
            
    except Exception as e:
        print(f"[!] Worker exception: {e}")
        sys.exit(1)

def run_notebooklm(args):
    """Run notebooklm command using direct path if available, or uv run as fallback."""
    # Try to find the exact path for notebooklm in the local .venv
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_bin_path = os.path.join(base_dir, ".venv", "bin", "notebooklm")
    python_bin = os.path.join(base_dir, ".venv", "bin", "python3")
    
    if os.path.exists(venv_bin_path) and os.path.exists(python_bin):
        # Using [python, script_path] to bypass broken shebangs
        cmd = [python_bin, venv_bin_path] + args
    else:
        # Fallback to uv run
        cmd = ["uv", "run", "notebooklm"] + args
        
    print(f"[*] Executing: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)

def generate_summary_report(notebook_id, target_path):
    """Generate a detailed summary report (Agenda, Decisions, Timeline, Guide) using NotebookLM."""
    print(f"[*] Generating detailed summary report for: {notebook_id}...")
    
    # Custom instructions to extract specific business points
    prompt = """
以下の項目を日本語の箇条書きで詳細に抽出したレポートを作成してください。

構成順序:
1. ### **ポッドキャスト解説ガイド（内容のポイント）**
2. ### **主要な議題**
3. ### **決定事項**
4. ### **今後のタイムライン**

出力ルール（重要）:
- 「Answer:」という文字列や、冒頭の挨拶（「今回の資料から抽出します」など）は一切含めないでください。
- 末尾の結びの言葉（「希望があればお知らせください」など）も一切含めないでください。
- 生成されたマークダウンの「見出し」と「本文」のみを直接出力してください。
- 各セクションの内容はビジネス向けの丁寧な日本語で、箇条書きを活用して詳細に記載してください。
    """
    normalized_prompt = " ".join(prompt.strip().split())
    
    # Generation start
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            print(f"  Attempt {attempt+1}: Generating custom report...")
            # Generate the report with custom instructions
            gen_res = run_notebooklm(["generate", "report", normalized_prompt, "-n", notebook_id, "--wait"])
            
            if gen_res.returncode != 0:
                print(f"    [!] Report generation failed: {gen_res.stderr}")
                if attempt < max_retries:
                    print("    Retrying in 30s...")
                    time.sleep(30)
                    continue
                return

            # Download the report
            dl_res = run_notebooklm(["download", "report", target_path, "-n", notebook_id, "--latest", "--force"])
            if dl_res.returncode == 0:
                print(f"    [🎉 SUCCESS] Detailed summary saved to: {target_path}")
                return
            else:
                print(f"    [!] Failed to download report: {dl_res.stderr}")
                
        except Exception as e:
            print(f"    [!] Error during attempt {attempt+1}: {e}")
            if attempt < max_retries:
                time.sleep(30)

def cleanup_old_notebooks(days=7):
    """Delete notebooks older than 'days' based on their creation date."""
    print(f"[*] Starting NotebookLM cleanup (older than {days} days)...")
    try:
        import json
        from datetime import timedelta
        
        # 1. List notebooks in JSON format
        result = run_notebooklm(["list", "--json"])
        if result.returncode != 0:
            print(f"[!] Cleanup: Failed to list notebooks.\n{result.stderr}")
            return
        
        json_data = json.loads(result.stdout)
        notebooks = json_data.get('notebooks', [])
        now = datetime.now()
        threshold = now - timedelta(days=days)
        
        deleted_count = 0
        for nb in notebooks:
            # Format is usually: 2026-04-02T13:25:32
            created_at_str = nb.get('created_at')
            if not created_at_str:
                continue
                
            try:
                # Handle potentially varying ISO formats
                created_at = datetime.fromisoformat(created_at_str.split('.')[0])
                if created_at < threshold:
                    nb_id = nb.get('id')
                    nb_title = nb.get('title', 'Untitled')
                    print(f"  Cleaning up old notebook: {nb_title} (ID: {nb_id}, Created: {created_at})")
                    
                    del_res = run_notebooklm(["delete", "-n", nb_id, "-y"])
                    if del_res.returncode == 0:
                        deleted_count += 1
                    else:
                        print(f"    [!] Failed to delete {nb_id}: {del_res.stderr}")
            except Exception as ex:
                print(f"    [!] Error processing notebook {nb.get('id')}: {ex}")
        
        print(f"[*] Cleanup finished. {deleted_count} notebooks deleted.")
        
    except Exception as e:
        print(f"[!] Unexpected error during cleanup: {e}")

if __name__ == "__main__":
    main()
