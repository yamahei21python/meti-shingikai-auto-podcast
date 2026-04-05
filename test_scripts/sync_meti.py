import subprocess
import os
import sys
from datetime import datetime

# パス設定 (隔離環境用)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
SCRAPER_PATH = os.path.join(BASE_DIR, "scrape_meti_shingikai.py")
TEST_DB = os.path.join(BASE_DIR, "test_councils.db")

def run_command(command, cwd=ROOT_DIR):
    """コマンドを実行し、結果を返す補助関数"""
    try:
        print(f"[*] Executing: {' '.join(command)}")
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        return result
    except Exception as e:
        print(f"[!] Critical error executing command: {e}")
        sys.exit(1)

def main():
    print("\n" + "="*50)
    print("  METI Podcast Sync Helper (Python Test Version)")
    print("="*50)
    
    # 1. 隔離フォルダ内のスクレイパーを実行
    # 注: このスクレイパーは内部で test_scripts/test_councils.db を参照するように書き換え済み
    print(f"[*] Running scraper: {os.path.basename(SCRAPER_PATH)}")
    run_result = run_command(["uv", "run", "python3", SCRAPER_PATH])
    
    if run_result.stdout:
        print(run_result.stdout)
    if run_result.stderr:
        print(f"[LOG] {run_result.stderr}")

    # 2. テスト用DBの更新があるか確認 (Gitステータスで検知)
    # 相対パスを取得してgit statusに渡す
    rel_db_path = os.path.relpath(TEST_DB, ROOT_DIR)
    status_result = run_command(["git", "status", "--porcelain", rel_db_path])
    
    # 'M' (修正) または '??' (新規ファイル) があれば更新ありとみなす
    if "M" in status_result.stdout or "??" in status_result.stdout:
        print(f"[+] Database updated ({rel_db_path}).")
        print("[*] Simulating Git operations (No actual production changes)...")
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_msg = f"Update METI Council status (Local scan: {now})"
        
        print("-" * 30)
        print(f"  [SIMULATION] git add {rel_db_path}")
        print(f"  [SIMULATION] git commit -m '{commit_msg}'")
        print(f"  [SIMULATION] git push")
        print("-" * 30)
        
        print("\n[🎉 SUCCESS] Sync simulation complete!")
        print("Root environment remains untouched.")
    else:
        print(f"[*] No new items detected in {rel_db_path}. Everything is up to date.")

if __name__ == "__main__":
    main()
