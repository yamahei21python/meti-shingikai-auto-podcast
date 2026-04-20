"""
Utility to fix DB status for incorrectly skipped items.
Resets 'skipped' METI items with target categories back to 'pending'.
"""

import sqlite3
import os
import sys

# Add current dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import DB_PATH, TARGET_CATS_METI, logger

def fix_skipped_items():
    """Reset skipped items that should have been pending."""
    logger.info(f"Connecting to: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Find items that are 'skipped' but belong to target categories
    # We check category2 matches TARGET_CATS_METI
    placeholders = ", ".join(["?"] * len(TARGET_CATS_METI))
    
    query = f"""
        UPDATE council_updates 
        SET podcast_status = 'pending'
        WHERE podcast_status = 'skipped'
        AND category1 = 'METI'
        AND category2 IN ({placeholders})
    """
    
    cursor.execute(query, TARGET_CATS_METI)
    affected = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    logger.info(f"Fixed {affected} items. Status reset to 'pending'.")

if __name__ == "__main__":
    fix_skipped_items()
