import sqlite3
import sys
import json
import os
import time
import re
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from playwright.sync_api import sync_playwright

# --- Configuration ---
DB_NAME = "councils.db"
METI_URL = "https://www.meti.go.jp/shingikai/index.html"
OCCTO_URL = "https://www.occto.or.jp/iinkai/"
SOCKS5_PROXY = "socks5://127.0.0.1:40000"
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

def is_url_in_db(conn, url):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM council_updates WHERE url = ?", (url,))
    return cursor.fetchone() is not None

def normalize_date(date_str):
    if not date_str: return None
    # 2026年4月10日 -> 2026-04-10
    match = re.search(r'(\d{4})[年.](\d{1,2})[月.](\d{1,2})', date_str)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return date_str

# --- METI Scraper ---
def fetch_meti_updates():
    print(f"[*] Fetching METI via curl-cffi + WARP: {METI_URL}")
    proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}
    headers = {
        "Referer": "https://www.google.com/",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    try:
        response = curl_requests.get(METI_URL, impersonate="chrome120", timeout=60, proxies=proxies, headers=headers)
        if response.status_code != 200:
            print(f"  [!] METI Error: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        content_area = soup.find('div', id='main_contents') or soup.find('div', id='contents') or soup
        dl_list = content_area.find('dl')
        if not dl_list: return []

        updates = []
        dt_tags = dl_list.find_all('dt')
        dd_tags = dl_list.find_all('dd')
        for dt, dd in zip(dt_tags, dd_tags):
            date_str = dt.get_text(strip=True)
            link_tag = dd.find('a')
            if not link_tag: continue
            updates.append({
                "date": normalize_date(date_str),
                "title": link_tag.get_text(strip=True),
                "url": urljoin(METI_URL, link_tag.get('href')),
                "categories": ["METI"]
            })
        return updates
    except Exception as e:
        print(f"  [!] METI Exception: {e}")
        return []

def fetch_meti_categories(url):
    """個別ページを訪問してパンくずリストからカテゴリを抽出する"""
    proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}
    try:
        # ヘッダーを最小限にし、impersonateに任せる。Refererを追加。
        headers = {"Referer": METI_URL}
        response = curl_requests.get(url, impersonate="chrome120", timeout=30, proxies=proxies, headers=headers)
        if response.status_code != 200:
            return ["METI"]
        
        soup = BeautifulSoup(response.content, 'html.parser')
        # 経産省のパンくずリストは通常 <div class="pan"> または <div id="breadcrumb">
        breadcrumb = soup.find('div', class_='pan') or soup.find('div', id='breadcrumb')
        if not breadcrumb:
            title = soup.title.string if soup.title else "No Title"
            print(f"      [!] Breadcrumb not found on {url}. Title: {title}")
            # デバッグ用にHTMLの一部（メインコンテンツ付近）を確認
            return ["METI"]
        
        # パンくずリストの各階層テキストを取得
        items = []
        for li in breadcrumb.find_all(['li', 'a']):
            text = li.get_text(strip=True)
            if text and text not in items:
                items.append(text)
        
        # 「ホーム」「審議会・研究会」および英語の「HOME」は除外
        exclude = ["ホーム", "審議会・研究会", "HOME", "审议会・研究会"]
        categories = ["METI"]
        for item in items:
            if item and item not in exclude and item not in categories:
                categories.append(item)
        
        # パンくずの最後（現在のタイトル）はカテゴリとして冗長なので除外
        if len(categories) > 2:
            categories.pop()
            
        if len(categories) > 1:
            print(f"      [✓] Categories: {'>'.join(categories)}")
            
        return categories
    except Exception as e:
        print(f"  [!] METI Category Error ({url}): {e}")
        return ["METI"]

# --- OCCTO Scraper ---
def fetch_occto_updates():
    print(f"[*] Fetching OCCTO via Playwright + WARP: {OCCTO_URL}")
    updates = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, proxy={"server": SOCKS5_PROXY})
            context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
            page = context.new_page()
            page.goto(OCCTO_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("a.linklist-cms02__link", timeout=30000)
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            blocks = soup.find_all('a', class_='linklist-cms02__link')
            for block in blocks:
                date_tag = block.find('span', string=re.compile(r'開催日：'))
                date_raw = date_tag.get_text(strip=True).replace('開催日：', '') if date_tag else ""
                spans = block.find_all('span')
                committee = spans[1].get_text(strip=True) if len(spans) > 1 else "Unknown"
                title_tag = block.find('p')
                updates.append({
                    "date": normalize_date(date_raw),
                    "title": title_tag.get_text(strip=True) if title_tag else "No Title",
                    "url": urljoin(OCCTO_URL, block.get('href')),
                    "categories": ["OCCTO", committee]
                })
            browser.close()
        except Exception as e:
            print(f"  [!] OCCTO Exception: {e}")
    return updates

# --- Data Saver ---
def save_to_db(conn, updates):
    cursor = conn.cursor()
    new_count = 0
    # ポッドキャスト対象の定義
    target_cats_meti = ['エネルギー・環境', '総合資源エネルギー調査会']
    
    for item in updates:
        try:
            # カテゴリに基づいてステータスを決定
            category1 = item['categories'][0] if len(item['categories']) > 0 else None
            category2 = item['categories'][1] if len(item['categories']) > 1 else None
            
            status = 'skipped'
            if category1 == 'OCCTO':
                status = 'pending'
            elif category1 == 'METI' and category2 in target_cats_meti:
                status = 'pending'
                
            placeholders = ", ".join(["?"] * (MAX_CATEGORIES + 4))
            cat_list = (item['categories'] + [None] * MAX_CATEGORIES)[:MAX_CATEGORIES]
            params = [item['date'], item['title'], item['url'], status] + cat_list
            col_names = ", ".join([f"category{i+1}" for i in range(MAX_CATEGORIES)])
            
            cursor.execute(f'''
                INSERT OR IGNORE INTO council_updates (date, title, url, podcast_status, {col_names})
                VALUES ({placeholders})
            ''', params)
            if cursor.rowcount > 0:
                new_count += 1
        except Exception as e:
            print(f"  [!] DB Error: {e}")
    conn.commit()
    return new_count

def main():
    print(f"\n=== Sync Pipeline Start: {datetime.now()} ===")
    conn = init_db()
    
    # 1. METI
    meti_data = fetch_meti_updates()
    print(f"  [+] METI: Found {len(meti_data)} items.")
    
    # 新規アイテムのみ詳細を取得
    processed_meti = []
    print("  [*] Checking for new METI items to fetch categories...")
    for item in meti_data:
        if not is_url_in_db(conn, item['url']):
            print(f"    [+] Fetching categories for: {item['title'][:40]}...")
            item['categories'] = fetch_meti_categories(item['url'])
            time.sleep(1) # サーバー負荷軽減
        processed_meti.append(item)
    
    # 2. OCCTO
    occto_data = fetch_occto_updates()
    print(f"  [+] OCCTO: Found {len(occto_data)} items.")
    
    # 3. Save
    all_data = processed_meti + occto_data
    added = save_to_db(conn, all_data)
    print(f"  [🎉] Summary: Added {added} new items to DB.")
    
    conn.close()
    print("=== Sync Pipeline Finished ===\n")

if __name__ == "__main__":
    main()
