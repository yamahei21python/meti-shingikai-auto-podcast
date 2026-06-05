import os
import sqlite3
import sys
from pathlib import Path

# Add parent path to import shared configuration
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared import DB_PATH, logger, setup_logging

setup_logging()

segment_map = {
    "safety_security": "安全・安心",
    "sankoshin": "産業構造審議会",
    "mono_info_service": "ものづくり/情報/流通・サービス",
    "external_economy": "対外経済",
    "enecho": "総合資源エネルギー調査会",
    "energy_environment": "エネルギー・環境",
    "economy": "経済産業",
    "hoankyogikai": "中央鉱山保安協議会",
    "kagakubusshitsu": "化学物質審議会",
    "shokeishin": "消費経済審議会",
    "keiryogyoseishin": "計量行政審議会",
}

def backfill():
    if not DB_PATH.exists():
        print(f"DB not found at: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Get METI items with empty category2
    cursor.execute("""
        SELECT id, url 
        FROM council_updates 
        WHERE category1 = 'METI' AND (category2 IS NULL OR category2 = '')
    """)
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} items with empty category2.")
    
    updated_count = 0
    skipped_count = 0
    
    for item_id, url in rows:
        if "/shingikai/" not in url:
            skipped_count += 1
            continue
            
        try:
            segment = url.split("/shingikai/")[1].split("/")[0]
            category2 = segment_map.get(segment)
            
            if category2:
                cursor.execute("""
                    UPDATE council_updates 
                    SET category2 = ? 
                    WHERE id = ?
                """, (category2, item_id))
                updated_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"Error parsing URL {url}: {e}")
            skipped_count += 1

    conn.commit()
    conn.close()
    
    print(f"Backfill Complete. Updated: {updated_count}, Skipped: {skipped_count}")

if __name__ == "__main__":
    backfill()
