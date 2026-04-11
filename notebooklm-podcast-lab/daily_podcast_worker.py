import sqlite3
import subprocess
import os
import sys
import re
import time
import json
from datetime import datetime

# --- 設定 ---
DB_PATH = "../councils.db"
MAX_PROCESS_PER_RUN = 2 # 1回の実行で処理する最大件数

def init_notebooklm_auth():
    """Ensure notebooklm auth file exists if secret is provided in ENV."""
    auth_json = os.getenv("NOTEBOOKLM_AUTH_JSON")
    if not auth_json:
        return
        
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
    
    # Ensure language is set to Japanese globally for this account
    print("[*] Setting NotebookLM language to Japanese (ja)...")
    run_notebooklm(["language", "set", "ja"])

def sanitize_filename(text):
    """Remove invalid characters and limit length."""
    text = re.sub(r'[\\/:*?"<>|／]', '', text)
    text = text.replace(' ', '_').replace('　', '_')
    return text[:200]

def get_pending_items(limit=2):
    """Get pending items to process, filtered by target categories."""
    if not os.path.exists(DB_PATH):
        print(f"[!] Database not found at {DB_PATH}")
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 対象カテゴリ: OCCTO全件, METI(総合資源エネルギー調査会, エネルギー・環境)
    cursor.execute("""
        SELECT id, title, url, date, pdf_urls 
        FROM council_updates 
        WHERE podcast_status = 'pending' 
        AND (
            category1 = 'OCCTO' OR 
            (category1 = 'METI' AND category2 IN ('エネルギー・環境', '総合資源エネルギー調査会'))
        )
        ORDER BY date ASC, id ASC 
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

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
    """Convert 'YYYY-MM-DD' to 'YYYYMMDD'."""
    try:
        if date_str and '-' in date_str:
            return date_str.replace('-', '')
        nums = re.findall(r'\d+', date_str)
        if len(nums) >= 3:
            return f"{int(nums[0]):04d}{int(nums[1]):02d}{int(nums[2]):02d}"
    except Exception:
        pass
    return datetime.now().strftime('%Y%m%d')

def run_notebooklm(args):
    """Run notebooklm command."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_bin_path = os.path.join(base_dir, ".venv", "bin", "notebooklm")
    python_bin = os.path.join(base_dir, ".venv", "bin", "python3")
    
    if os.path.exists(venv_bin_path) and os.path.exists(python_bin):
        cmd = [python_bin, venv_bin_path] + args
    else:
        cmd = ["uv", "run", "notebooklm"] + args
        
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
        
        # Use run_notebooklm directly to check status
        cmd = run_notebooklm(status_args)
        if cmd.returncode == 0:
            status_out = cmd.stdout.strip()
            print(f"    [STATUS] {status_out}")
            
            status_upper = status_out.upper()
            if "STATUS='SUCCEEDED'" in status_upper or "STATUS='COMPLETED'" in status_upper:
                print("    [+] Task completed successfully.")
                return True
            if "STATUS='FAILED'" in status_upper or "STATUS='ERROR'" in status_upper:
                print(f"    [!] Task failed according to status: {status_out}")
                return False
        else:
            print(f"    [!] Status check command failed (code {cmd.returncode})")

        time.sleep(poll_interval)
    
    print(f"    [!] Monitoring timed out after {timeout_seconds}s")
    return False

def generate_summary_report(notebook_id, target_path):
    """Generate and download a detailed summary report."""
    print(f"[*] Generating detailed summary report for: {notebook_id}...")
    prompt = """
資料の内容を徹底的に分析し、日本のエネルギー業界関係者が実務で活用できる詳細な「カスタムレポート」を日本語で作成してください。
構成は必ず以下の4つのセクションとし、各セクションで少なくとも3〜5つの核心的なポイントを詳細（1つにつき数十文字〜百文字程度）に記述してください。

# [資料タイトル] カスタムレポート

### 1. ポッドキャスト解説ガイド（内容のポイント）
- 議論の背景、技術的・政策的意義、現場への影響などを、専門用語を適切に使いながら深く掘り下げて解説してください。各ポイントには太字の小見出しを付けてください。

### 2. 主要な議題
- この会議で焦点となった論点、対立軸、または検討された新しい枠組みなどを具体的に抽出してください。

### 3. 決定事項
- 合意に至った内容、承認された方針、策定された基準などを、可能な限り具体的数値（％、金額、目標値、容量など）を含めて記述してください。

### 4. 今後のタイムライン
- 制度の施行時期、パブリックコメントの予定、次回の検討会など、スケジュールに関する情報を日付と共にリストアップしてください。

「Answer:」などの余計な前置きは一切含めず、冒頭の # 見出しから始まる純粋なマークダウンのみを出力してください。
    """
    normalized_prompt = " ".join(prompt.strip().split())
    
    # Generate (JSON mode to get task_id)
    gen_res = run_notebooklm(["generate", "report", normalized_prompt, "-n", notebook_id, "--language", "ja", "--json"])
    if gen_res.returncode != 0:
        print(f"    [!] Report generation start failed: {gen_res.stderr}")
        return False

    try:
        gen_data = json.loads(gen_res.stdout)
        task_id = gen_data.get("task_id")
    except Exception as e:
        print(f"    [!] Failed to parse report task ID: {e}")
        return False

    if not task_id:
        print(f"    [!] No task_id returned in JSON: {gen_res.stdout}")
        return False

    # Wait for completion using monitoring loop (Extended timeout: 90 minutes)
    success = wait_for_task(task_id, notebook_identifier=notebook_id, timeout_seconds=5400)
    
    if not success:
        print(f"    [!] Report generation failed or timed out.")
        print(f"    [*] Waiting for 300s buffer before fail-safe download attempt...")
        time.sleep(300)

    # Download
    dl_res = run_notebooklm(["download", "report", target_path, "-n", notebook_id, "--latest", "--force"])
    if dl_res.returncode == 0:
        print(f"    [🎉 SUCCESS] Detailed summary saved to: {target_path}")
        return True
    
    print(f"    [!] Final report download failed: {dl_res.stderr}")
    return False

def process_single_item(item):
    """Process a single item from DB."""
    item_id, title, url, date_str, pdf_urls_json = item
    print(f"\n>>> Processing Item: {title} ({date_str})")
    
    formatted_date = format_date_yyyymmdd(date_str)
    sanitized_title = sanitize_filename(title)
    notebook_name = f"{formatted_date}_{sanitized_title}"
    output_temp = f"temp_{formatted_date}.mp3"
    
    # --- STEP 1: Generate Podcast MP3 ---
    python_bin = sys.executable
    cmd = [
        python_bin, "generate_podcast_from_article.py",
        "--url", url,
        "--output", output_temp,
        "--name", notebook_name
    ]
    if pdf_urls_json:
        cmd.extend(["--pdfs", pdf_urls_json])
    
    print(f"[*] Executing Generator: {' '.join(cmd)}")
    mp3_res = subprocess.run(cmd, capture_output=True, text=True)
    print(mp3_res.stdout)
    
    mp3_success = False
    notebook_identifier = notebook_name
    
    if mp3_res.returncode == 0 and os.path.exists(output_temp):
        mp3_success = True
        # Try to capture real notebook ID if possible
        for line in mp3_res.stdout.splitlines():
            if line.startswith("NOTEBOOK_ID="):
                notebook_identifier = line.split("=", 1)[1].strip()
                break
    
    # --- STEP 2: Generate Summary MD (Only if MP3 succeeded) ---
    md_success = False
    md_temp = f"temp_{formatted_date}_summary.md"
    
    if mp3_success:
        md_success = generate_summary_report(notebook_id=notebook_identifier, target_path=md_temp)
    
    # --- STEP 3: Finalize or Rollback ---
    final_dir = "../podcasts"
    if not os.path.exists(final_dir): os.makedirs(final_dir)
    
    final_mp3_path = os.path.join(final_dir, f"{formatted_date}_{sanitized_title}.mp3")
    final_md_path = os.path.join(final_dir, f"{formatted_date}_{sanitized_title}_summary.md")
    
    if mp3_success and md_success:
        # Atomic Move
        if os.path.exists(final_mp3_path): os.remove(final_mp3_path)
        os.rename(output_temp, final_mp3_path)
        
        if os.path.exists(final_md_path): os.remove(final_md_path)
        os.rename(md_temp, final_md_path)
        
        # Save metadata JSON for RSS generator (Original Link)
        meta_path = final_mp3_path.rsplit(".", 1)[0] + ".json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"original_url": url, "title": title}, f, ensure_ascii=False, indent=2)
            
        print(f"[+] COMPLETE SUCCESS: Both MP3 and MD saved with metadata.")
        update_status(item_id, 'done')
        
        # Success details for workflow
        print(f"PODCAST_ASSET_PATH={final_mp3_path}")
        print(f"ORIGINAL_URL={url}")
        
        result_status = True
    else:
        # Failed: Cleanup temp files
        print(f"[!] FAILED: mp3={mp3_success}, md={md_success}. Keeping status as pending for retry.")
        if os.path.exists(output_temp): os.remove(output_temp)
        if os.path.exists(md_temp): os.remove(md_temp)
        result_status = False

    # --- STEP 4: Cleanup Notebook (Always) ---
    print(f"[*] Cleaning up Notebook: {notebook_identifier}")
    run_notebooklm(["delete", "-n", notebook_identifier, "-y"])
    
    return result_status

def main():
    print(f"=== Daily Podcast Worker Start (Limit: {MAX_PROCESS_PER_RUN}): {datetime.now()} ===")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    init_notebooklm_auth()

    items = get_pending_items(limit=MAX_PROCESS_PER_RUN)
    if not items:
        print("[*] No pending items in the queue.")
        return

    processed_count = 0
    for item in items:
        if process_single_item(item):
            processed_count += 1
        
    print(f"\n=== Worker Finished. Processed: {processed_count} items ===")

if __name__ == "__main__":
    main()
