import sqlite3
import subprocess
import os
import sys
import re
from datetime import datetime

# --- 設定 ---
DB_PATH = "../meti_shingikai.db"
PROJECT_DIR = "/Users/kohei/Myproject/ene/notebooklm-podcast-lab"

def sanitize_filename(text):
    """ファイル名に使えない文字を除去し、長さを制限する。"""
    # 記号を除去
    text = re.sub(r'[\\/:*?"<>|]', '', text)
    # スペースをアンダースコアに
    text = text.replace(' ', '_')
    # 長さ制限
    return text[:50]

def get_latest_pending():
    """最新の待機中アイテムを1件取得する。"""
    if not os.path.exists(DB_PATH):
        print(f"[!] Database not found at {DB_PATH}")
        return None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 日付(date文字列)が新しい順に1件取得
    # 文字列比較なので書式に依存するが、METIの形式（2026年3月...）ならある程度機能する
    cursor.execute("""
        SELECT id, title, url, date 
        FROM council_updates 
        WHERE podcast_status = 'pending' 
        ORDER BY date DESC, id DESC 
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row

def update_status(item_id, status, filename=None):
    """DBのステータスを更新する。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if filename:
        cursor.execute("""
            UPDATE council_updates 
            SET podcast_status = ?, podcast_date = ? 
            WHERE id = ?
        """, (status, now, item_id))
    else:
        cursor.execute("""
            UPDATE council_updates 
            SET podcast_status = ?, podcast_date = ? 
            WHERE id = ?
        """, (status, now, item_id))
        
    conn.commit()
    conn.close()

def main():
    print(f"=== Daily Podcast Worker Start: {datetime.now()} ===")
    
    item = get_latest_pending()
    if not item:
        print("[*] No pending items in the queue.")
        return

    item_id, title, url, date_str = item
    print(f"[*] Processing: {title} ({url})")
    
    # 出力ファイル名の生成 (例: 20260402_第48回_原子力小委員会.mp3)
    # date_str から数字のみ抽出を試みる
    clean_date = re.sub(r'\D', '', date_str) or datetime.now().strftime('%Y%m%d')
    safe_title = sanitize_filename(title)
    output_filename = f"Podcast_{clean_date}_{safe_title}.mp3"
    
    # 音声生成スクリプトの呼び出し
    cmd = [
        "python3", "generate_podcast_from_article.py",
        "--url", url,
        "--output", output_filename
    ]
    
    print(f"[*] Executing: {' '.join(cmd)}")
    try:
        # 実行
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        
        if result.returncode == 0:
            print(f"[🎉] Successfully generated podcast: {output_filename}")
            update_status(item_id, 'completed', output_filename)
            # GitHub Actions向けに、生成されたファイル名を最後に1行だけ出力する
            # ワークフロー側でこれをキャプチャして Release にアップロードする
            print(f"PODCAST_ASSET_PATH={output_filename}")
        else:
            print(f"[!] Error during podcast generation:\n{result.stderr}")
            # エラー時は 'failed' にして、明日以降に再試行されるのを防ぐ（手動介入を促す）
            # またはそのまま 'pending' にしておけば翌日再挑戦される
            update_status(item_id, 'failed')
            
    except Exception as e:
        print(f"[!] Worker exception: {e}")

if __name__ == "__main__":
    # カレントディレクトリをスクリプトの場所に移動（パス解決のため）
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
