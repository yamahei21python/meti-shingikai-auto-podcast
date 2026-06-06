import sqlite3
import sys
import os
from datetime import datetime, timedelta, timezone
import math

# Add project root to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import DB_PATH

def main(dry_run=True):
    if dry_run:
        print("=== DRY RUN MODE: No changes will be written to DB ===")
    else:
        print("=== LIVE RUN MODE: DB will be updated ===")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all done items sorted by original date descending, then id descending
    # (Matches original feed ordering logic)
    cursor.execute("""
        SELECT id, title, podcast_date, date, r2_filename
        FROM council_updates
        WHERE podcast_status = 'done'
        ORDER BY date DESC, id DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    
    print(f"Found {len(rows)} done episodes.")

    # Target date configuration
    # Defaults to today's date in JST. Can be overridden with a specific date (e.g. datetime(2026, 6, 5)).
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).replace(hour=0, minute=0, second=0, microsecond=0)

    updates = []
    for i, item in enumerate(rows):
        days_to_subtract = math.floor(i / 2)
        new_date = today - timedelta(days=days_to_subtract)
        new_date_str = new_date.strftime("%Y-%m-%d")

        # Extract time from original podcast_date or fallback to standard time format
        orig_date_str = item.get("podcast_date") or ""
        orig_time = "12:00:00"  # fallback
        
        if orig_date_str:
            # Format could be YYYY-MM-DD HH:MM:SS or ISO-8601
            parts = orig_date_str.split(" ")
            if len(parts) >= 2:
                orig_time = parts[1]
            else:
                if "T" in orig_date_str:
                    # e.g., 2026-04-10T18:58:15.000Z or similar
                    orig_time = orig_date_str.split("T")[1].split("+")[0].split(".")[0].split("Z")[0]

        # Combine new date and original time
        new_podcast_date = f"{new_date_str} {orig_time}"

        print(f"[{i:02d}] Title: {item['title'][:40]}...")
        print(f"     Original: {orig_date_str}  ->  New: {new_podcast_date}")
        
        updates.append((new_podcast_date, item["id"]))

    if not dry_run:
        for new_date_str, item_id in updates:
            cursor.execute("""
                UPDATE council_updates
                SET podcast_date = ?
                WHERE id = ?
            """, (new_date_str, item_id))
        conn.commit()
        print("DB update successfully committed!")
    
    conn.close()

if __name__ == "__main__":
    dry = True
    if len(sys.argv) > 1 and sys.argv[1] == "--live":
        dry = False
    main(dry_run=dry)
