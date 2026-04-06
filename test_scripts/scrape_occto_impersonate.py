import sqlite3
import sys
import json
from datetime import datetime
import os
import time
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

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

def scrape_occto_with_playwright_proxy():
    """Scrape OCCTO index using Playwright via WARP SOCKS5 Proxy."""
    updates = []
    
    # WARP SOCKS5 プロキシの設定
    proxy_server = "socks5://127.0.0.1:40000"
    
    with sync_playwright() as p:
        print(f"[*] Launching Playwright via WARP Proxy ({proxy_server}) to fetch OCCTO: {TARGET_URL}")
        try:
            # プロキシ設定を伴うブラウザ起動
            browser = p.chromium.launch(headless=True, proxy={"server": proxy_server})
            context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
            page = context.new_page()
            
            # ページ移動
            print(f"[*] Navigating to {TARGET_URL}...")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            # JS描画を待機（linklist-cms02__link クラスを持つ要素が出るまで）
            print("[*] Waiting for meeting blocks to render...")
            page.wait_for_selector("a.linklist-cms02__link", timeout=30000)
            
            content = page.content()
            print(f"  [+] Success: Received {len(content)} bytes of rendered HTML.")
            
            soup = BeautifulSoup(content, 'html.parser')
            blocks = soup.find_all('a', class_='linklist-cms02__link')
            print(f"[*] Found {len(blocks)} rendered items.")
            
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
            
            browser.close()
        except Exception as e:
            print(f"  [!] Playwright error: {type(e).__name__}: {e}")
            
    return updates

def main():
    print("\n" + "="*50)
    print("  OCCTO Scraper - Playwright + WARP Proxy Test")
    print("="*50)
    
    init_db()
    updates = scrape_occto_with_playwright_proxy()
    
    if not updates:
        print("[!] No OCCTO updates found. Either the site format changed or proxy is not working properly.")
        return

    print(f"Summary: Successfully parsed {len(updates)} OCCTO items.")
    for i, item in enumerate(updates[:3]):
         print(f"  [{i+1}] {item['date']} | {item['committee']} | {item['title']}")
    
    print("\n[🎉 SUCCESS] OCCTO Playwright test complete!")

if __name__ == "__main__":
    main()
