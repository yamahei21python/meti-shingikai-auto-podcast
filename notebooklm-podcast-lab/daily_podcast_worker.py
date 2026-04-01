import sqlite3
import subprocess
import os
import sys
import re
from datetime import datetime

# --- 設定 ---
DB_PATH = "../meti_shingikai.db"

def sanitize_filename(text):
    """Remove invalid characters and limit length."""
    text = re.sub(r'[\\/:*?"<>|]', '', text)
    text = text.replace(' ', '_')
    return text[:60]

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

def main():
    print(f"=== Daily Podcast Worker Start: {datetime.now()} ===")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    item = get_oldest_pending()
    if not item:
        print("[*] No pending items in the queue.")
        return

    item_id, title, url, date_str, pdf_urls_json = item
    print(f"[*] Found pending item: {title} ({url})")
    
    # Use simpler filename for cloud stability
    output_filename = "podcast_summary.mp3"
    
    # Pass PDF URLs directly to bypass cloud-side scraping
    cmd = [
        "uv", "run", "python3", "generate_podcast_from_article.py",
        "--url", url,
        "--output", output_filename
    ]
    if pdf_urls_json:
        cmd.extend(["--pdfs", pdf_urls_json])
    
    print(f"[*] Executing Generator (Direct PDF mode): {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        
        if result.returncode == 0:
            print(f"[🎉] Successfully generated podcast: {output_filename}")
            update_status(item_id, 'done')
            
            clean_date = re.sub(r'\D', '', date_str) or datetime.now().strftime('%Y%m%d')
            display_name = f"Podcast_{clean_date}_{sanitize_filename(title)}.mp3"
            print(f"PODCAST_ASSET_PATH={display_name}")
        else:
            print(f"[!] Error during podcast generation:\n{result.stderr}")
            update_status(item_id, 'failed')
            sys.exit(1)
            
    except Exception as e:
        print(f"[!] Worker exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
