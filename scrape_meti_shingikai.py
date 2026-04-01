import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime
import os
import time

# --- 設定 / Configuration ---
TARGET_URL = "https://www.meti.go.jp/shingikai/index.html"
BASE_URL = "https://www.meti.go.jp"
DB_NAME = "meti_shingikai.db"
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
                podcast_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        # Migration: category1〜10
        for i in range(1, MAX_CATEGORIES + 1):
            col_name = f"category{i}"
            if col_name not in columns:
                cursor.execute(f"ALTER TABLE council_updates ADD COLUMN {col_name} TEXT")
        
        # Migration: podcast_status
        if "podcast_status" not in columns:
            print("Migrating database: Adding 'podcast_status' column...")
            cursor.execute("ALTER TABLE council_updates ADD COLUMN podcast_status TEXT DEFAULT 'skipped'")
        if "podcast_date" not in columns:
            cursor.execute("ALTER TABLE council_updates ADD COLUMN podcast_date TIMESTAMP")
    
    conn.commit()
    return conn

def get_breadcrumb_list(url, headers):
    try:
        time.sleep(0.3)
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        breadcrumb_div = soup.find('div', class_='pan')
        if breadcrumb_div:
            items = breadcrumb_div.find_all('li')
            texts = [item.get_text(strip=True) for item in items]
            
            if not texts:
                links = breadcrumb_div.find_all('a')
                texts = [link.get_text(strip=True) for link in links]

            ignore_keywords = ["ホーム", "審議会・研究会"]
            filtered = [t for t in texts if t not in ignore_keywords]
            
            if len(filtered) > 1:
                return filtered[:-1]
            elif len(filtered) == 1:
                return filtered
            else:
                return []
                
    except Exception as e:
        print(f"  Error fetching categories for {url}: {e}")
        return None
    return []

def scrape_updates():
    print(f"Fetching index from {TARGET_URL}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except Exception as e:
        print(f"Error fetching index page: {e}")
        return [], {}

    soup = BeautifulSoup(response.text, 'html.parser')
    content_area = soup.find('div', id='main_contents') or soup.find('div', id='contents') or soup
    dl_list = content_area.find('dl')
    
    if not dl_list:
        return [], {}

    dt_tags = dl_list.find_all('dt')
    dd_tags = dl_list.find_all('dd')

    updates = []
    for dt, dd in zip(dt_tags, dd_tags):
        date_str = dt.get_text(strip=True)
        link_tag = dd.find('a')
        if not link_tag: continue
        title = link_tag.get_text(strip=True)
        relative_url = link_tag.get('href')
        abs_url = BASE_URL + relative_url if relative_url.startswith('/') else (relative_url if relative_url.startswith('http') else TARGET_URL.rsplit('/', 1)[0] + '/' + relative_url)
        updates.append({"date": date_str, "title": title, "url": abs_url})
    
    return updates, headers

def process_and_save(conn, updates, headers):
    cursor = conn.cursor()
    new_count = 0
    skipped_count = 0
    
    for item in updates:
        cursor.execute("SELECT id, category1, podcast_status FROM council_updates WHERE url = ?", (item['url'],))
        existing = cursor.fetchone()
        
        # すでにカテゴリ取得済み かつ podcast_statusが設定済みならスキップ
        if existing and existing[1] and existing[2] != 'skipped_placeholder':
            skipped_count += 1
            continue
            
        print(f"  Processing category and queue for: {item['title']}...")
        cat_list = get_breadcrumb_list(item['url'], headers)
        if cat_list is None: continue

        # 10要素のリストに調整
        padded_cats = (cat_list + [None] * MAX_CATEGORIES)[:MAX_CATEGORIES]
        
        # Podcast対象か判定
        status = 'pending' if cat_list and cat_list[0] in PODCAST_TARGET_CATEGORIES else 'skipped'
        
        if existing:
            update_sql = ", ".join([f"category{i+1} = ?" for i in range(MAX_CATEGORIES)])
            params = padded_cats + [status, existing[0]]
            cursor.execute(f"UPDATE council_updates SET {update_sql}, podcast_status = ? WHERE id = ?", params)
            new_count += 1
        else:
            placeholders = ", ".join(["?"] * (MAX_CATEGORIES + 4))
            col_names = ", ".join([f"category{i+1}" for i in range(MAX_CATEGORIES)])
            params = [item['date'], item['title'], item['url'], status] + padded_cats
            cursor.execute(f'''
                INSERT INTO council_updates (date, title, url, podcast_status, {col_names})
                VALUES ({placeholders})
            ''', params)
            new_count += 1
        conn.commit()
    
    print(f"Summary: Processed {len(updates)} items. {new_count} items updated/added, {skipped_count} items skipped.")
    return new_count

def main():
    conn = init_db()
    updates, headers = scrape_updates()
    if not updates:
        conn.close()
        return

    new_count = process_and_save(conn, updates, headers)
    
    # 待機中のキュー情報を表示
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM council_updates WHERE podcast_status = 'pending'")
    pending_count = cursor.fetchone()[0]
    print(f"Podcast Queue Status: {pending_count} items pending.")

    conn.close()

if __name__ == "__main__":
    main()
