import os
import sqlite3
import sys
from pathlib import Path

# Add parent path to import shared configuration
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared import DB_PATH, setup_logging

setup_logging()

def show_failed_items():
    if not DB_PATH.exists():
        print(f"DB not found at: {DB_PATH}")
        return []

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, retry_count, date 
        FROM council_updates 
        WHERE podcast_status = 'failed'
    """)
    rows = cursor.fetchall()
    
    if not rows:
        print("No failed podcast episodes in the database.")
        conn.close()
        return []
        
    print(f"=== Failed Podcast Episodes ({len(rows)} items) ===")
    for row in rows:
        print(f"ID {row[0]}: {row[1]} ({row[3]}) - Attempted {row[2]} times")
        
    conn.close()
    return rows

def reset_all_failed():
    failed_items = show_failed_items()
    if not failed_items:
        return

    # Non-interactive fallback or normal prompt
    try:
        ans = input("\nDo you want to reset all these failed items back to 'pending'? (y/n): ").strip().lower()
    except EOFError:
        print("\nNon-interactive session. Skipping reset. Run with --yes flag to reset.")
        return

    if ans != 'y':
        print("Canceled.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE council_updates 
        SET podcast_status = 'pending', retry_count = 0 
        WHERE podcast_status = 'failed'
    """)
    updated_count = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"\nReset Complete. {updated_count} items have been moved back to 'pending'.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Manage failed podcast episodes.")
    parser.add_argument("--list", action="store_true", help="List failed items without resetting")
    parser.add_argument("--yes", action="store_true", help="Reset all failed items without prompt")
    args = parser.parse_args()

    if args.list:
        show_failed_items()
    elif args.yes:
        if not DB_PATH.exists():
            print(f"DB not found at: {DB_PATH}")
            sys.exit(1)
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("UPDATE council_updates SET podcast_status = 'pending', retry_count = 0 WHERE podcast_status = 'failed'")
        count = cursor.rowcount
        conn.commit()
        conn.close()
        print(f"Reset {count} failed items to pending.")
    else:
        # Prompt by default
        reset_all_failed()
