import sqlite3
import subprocess
import os
import sys
import re
import time
from datetime import datetime

# --- 設定 ---
DB_PATH = "../councils.db"
MAX_PROCESS_PER_RUN = 1 # 1回の実行で処理する最大件数

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

def sanitize_filename(text):
    """Remove invalid characters and limit length."""
    text = re.sub(r'[\\/:*?"<>|／]', '', text)
    text = text.replace(' ', '_').replace('　', '_')
    return text[:200]

def get_pending_items(limit=2):
    """Get pending items to process."""
    if not os.path.exists(DB_PATH):
        print(f"[!] Database not found at {DB_PATH}")
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, url, date, pdf_urls 
        FROM council_updates 
        WHERE podcast_status = 'pending' 
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
    
    # Generate
    gen_res = run_notebooklm(["generate", "report", normalized_prompt, "-n", notebook_id, "--wait"])
    if gen_res.returncode != 0:
        print(f"    [!] Report generation failed: {gen_res.stderr}")
        return False

    # Download
    dl_res = run_notebooklm(["download", "report", target_path, "-n", notebook_id, "--latest", "--force"])
    if dl_res.returncode == 0:
        print(f"    [🎉 SUCCESS] Detailed summary saved to: {target_path}")
        return True
    return False

def process_single_item(item):
    """Process a single item from DB."""
    item_id, title, url, date_str, pdf_urls_json = item
    print(f"\n>>> Processing Item: {title} ({date_str})")
    
    formatted_date = format_date_yyyymmdd(date_str)
    notebook_name = sanitize_filename(f"{formatted_date}_{title}")
    output_filename = "temp_podcast.mp3"
    
    # Execute Generator
    python_bin = sys.executable
    cmd = [
        python_bin, "generate_podcast_from_article.py",
        "--url", url,
        "--output", output_filename,
        "--name", notebook_name
    ]
    if pdf_urls_json:
        cmd.extend(["--pdfs", pdf_urls_json])
    
    print(f"[*] Executing Generator: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    
    if result.returncode == 0:
        # Capture Notebook ID
        captured_id = None
        for line in result.stdout.splitlines():
            if line.startswith("NOTEBOOK_ID="):
                captured_id = line.split("=", 1)[1].strip()
                break
        
        notebook_identifier = captured_id if captured_id else notebook_name
        
        # Move MP3
        display_name = f"{formatted_date}_{sanitize_filename(title)}.mp3"
        target_dir = "../podcasts"
        if not os.path.exists(target_dir): os.makedirs(target_dir)
        target_path = os.path.join(target_dir, display_name)
        
        if os.path.exists(output_filename):
            if os.path.exists(target_path): os.remove(target_path)
            os.rename(output_filename, target_path)
            print(f"[+] Podcast saved to: {target_path}")
            
            # Generate Summary
            summary_filename = f"{formatted_date}_{sanitize_filename(title)}_summary.md"
            summary_path = os.path.join(target_dir, summary_filename)
            generate_summary_report(notebook_id=notebook_identifier, target_path=summary_path)
            
            # --- NEW: Immediate Cleanup of Notebook ---
            print(f"[*] Deleting NotebookLM Notebook: {notebook_identifier}")
            del_res = run_notebooklm(["delete", "-n", notebook_identifier, "-y"])
            if del_res.returncode == 0:
                print(f"[+] Successfully deleted notebook: {notebook_identifier}")
            else:
                print(f"[!] Failed to delete notebook: {del_res.stderr}")
            
            print(f"PODCAST_ASSET_PATH={target_path}")
            print(f"ORIGINAL_URL={url}")
            
            update_status(item_id, 'done')
            return True
    else:
        print(f"[!] Error during generation: {result.stderr}")
        update_status(item_id, 'failed')
        return False

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
