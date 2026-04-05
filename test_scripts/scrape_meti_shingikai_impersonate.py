import sqlite3
import sys
import json
from datetime import datetime
import os
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from curl_cffi import requests

# --- 設定 / Configuration ---
TARGET_URL = "https://www.meti.go.jp/shingikai/index.html"
BASE_URL = "https://www.meti.go.jp"
DB_NAME = "test_scripts/test_councils_impersonate.db" # テスト用DB名を分離
MAX_CATEGORIES = 10

# Podcast対象カテゴリ
PODCAST_TARGET_CATEGORIES = ["総合資源エネルギー調査会", "エネルギー・環境"]

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 既存のテーブル構造を確認
    cursor.execute("PRAGMA table_info(council_updates)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if not columns:
        # 新規作成
        category_cols = ", ".join([f"category{i+1} TEXT" for i in range(MAX_CATEGORIES)])
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS council_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                title TEXT,
                url TEXT UNIQUE,
                {category_cols},
                podcast_status TEXT DEFAULT 'skipped',
                pdf_urls TEXT,
                podcast_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    conn.commit()
    return conn

def fetch_page_impersonate(url, max_attempts=3):
    """Fetch URL using curl-cffi (impersonate chrome120)."""
    for attempt in range(max_attempts):
        try:
            print(f"[*] Fetching with curl-cffi (Chrome 120) (attempt {attempt+1}): {url}")
            # Chrome 120 の指紋とヘッダーを完全に偽装
            response = requests.get(url, impersonate="chrome120", timeout=60)
            
            if response.status_code == 200:
                print(f"  [+] Success: Received {len(response.content)} bytes.")
                return BeautifulSoup(response.content, 'html.parser')
            else:
                print(f"  [!] Received status {response.status_code} for {url}")
        except Exception as e:
            print(f"  [!] impersonate error on attempt {attempt+1}: {type(e).__name__}: {e}")
        
        if attempt < max_attempts - 1:
            time.sleep(5)
    return None

def normalize_date(date_str):
    import re
    if not date_str:
        return None
    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return date_str

def scrape_updates():
    soup = fetch_page_impersonate(TARGET_URL)
    if not soup:
        print("[!] Failed to fetch index page after retries.")
        return []

    content_area = soup.find('div', id='main_contents') or soup.find('div', id='contents') or soup
    dl_list = content_area.find('dl')
    
    if not dl_list:
        print("[!] No dl list found in index.")
        return []

    dt_tags = dl_list.find_all('dt')
    dd_tags = dl_list.find_all('dd')

    updates = []
    for dt, dd in zip(dt_tags, dd_tags):
        date_str = dt.get_text(strip=True)
        link_tag = dd.find('a')
        if not link_tag: continue
        title = link_tag.get_text(strip=True)
        relative_url = link_tag.get('href')
        
        abs_url = urljoin(TARGET_URL, relative_url)
        updates.append({"date": date_str, "title": title, "url": abs_url})
    
    return updates

def main():
    print("\n" + "="*50)
    print("  METI Scraper - Impersonate Chrome 120 Mode")
    print("="*50)
    
    conn = init_db()
    updates = scrape_updates()
    
    if not updates:
        print("[!] No updates found or site blocked. End of test.")
        conn.close()
        return

    print(f"Summary: Successfully parsed {len(updates)} items.")
    for i, item in enumerate(updates[:3]):
         print(f"  [{i+1}] {item['date']} - {item['title']}")
    
    print("\n[🎉 SUCCESS] curl-cffi test complete!")
    conn.close()

if __name__ == "__main__":
    main()
