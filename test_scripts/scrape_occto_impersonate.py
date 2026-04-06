import sqlite3
import sys
import json
from datetime import datetime
import os
import time
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from curl_cffi import requests

# --- 設定 / Configuration ---
TARGET_URL = "https://www.occto.or.jp/iinkai/"
BASE_URL = "https://www.occto.or.jp"
DB_NAME = "test_scripts/test_occto_impersonate.db"
MAX_CATEGORIES = 10

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    category_cols = ", ".join([f"category{i+1} TEXT" for i in range(MAX_CATEGORIES)])
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS council_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            title TEXT,
            url TEXT UNIQUE,
            {category_cols},
            podcast_status TEXT DEFAULT 'pending',
            pdf_urls TEXT,
            podcast_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

def fetch_page_impersonate(url, max_attempts=3):
    """Fetch URL using curl-cffi (impersonate chrome120) with WARP Proxy."""
    proxies = {
        "http": "socks5://127.0.0.1:40000",
        "https": "socks5://127.0.0.1:40000"
    }
    
    for attempt in range(max_attempts):
        try:
            print(f"[*] Fetching OCCTO with curl-cffi + WARP (attempt {attempt+1}): {url}")
            # Chrome 120 impersonation
            response = requests.get(url, impersonate="chrome120", timeout=60, proxies=proxies)
            
            if response.status_code == 200:
                print(f"  [+] Success: Received {len(response.content)} bytes.")
                return BeautifulSoup(response.content, 'html.parser')
            else:
                print(f"  [!] Received status {response.status_code} for {url}")
        except Exception as e:
            print(f"  [!] Error on attempt {attempt+1}: {type(e).__name__}: {e}")
        
        if attempt < max_attempts - 1:
            time.sleep(5)
    return None

def scrape_occto_updates():
    soup = fetch_page_impersonate(TARGET_URL)
    if not soup:
        print("[!] Failed to fetch OCCTO index page.")
        return []

    # OCCTO's index uses 'a.linklist-cms02__link'
    blocks = soup.find_all('a', class_='linklist-cms02__link')
    print(f"[*] Found {len(blocks)} candidate blocks in HTML.")
    
    updates = []
    for block in blocks:
        try:
            # Date: <span>開催日：2026.03.31</span>
            date_tag = block.find('span', string=re.compile(r'開催日：'))
            date_str = date_tag.get_text(strip=True).replace('開催日：', '') if date_tag else ""
            
            # Committee Name
            spans = block.find_all('span')
            committee_name = spans[1].get_text(strip=True) if len(spans) > 1 else "Unknown"
            
            # Title
            title_tag = block.find('p')
            title = title_tag.get_text(strip=True) if title_tag else "No Title"
            
            url = urljoin(TARGET_URL, block.get('href'))
            
            updates.append({
                "date": date_str,
                "committee": committee_name,
                "title": title,
                "url": url
            })
        except Exception as e:
            print(f"  [!] Error parsing block: {e}")
            continue
            
    return updates

def main():
    print("\n" + "="*50)
    print("  OCCTO Scraper - Impersonate + WARP Test")
    print("="*50)
    
    init_db()
    updates = scrape_occto_updates()
    
    if not updates:
        print("[!] No OCCTO updates found. It might require JavaScript rendering or IP is still blocked.")
        return

    print(f"Summary: Successfully parsed {len(updates)} OCCTO items.")
    for i, item in enumerate(updates[:3]):
         print(f"  [{i+1}] {item['date']} | {item['committee']} | {item['title']}")
    
    print("\n[🎉 SUCCESS] OCCTO test complete!")

if __name__ == "__main__":
    main()
