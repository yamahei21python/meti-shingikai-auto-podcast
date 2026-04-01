import sqlite3
import sys
import json
from datetime import datetime
import os
import time
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

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
                pdf_urls TEXT,
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
        
        # Migration: pdf_urls
        if "pdf_urls" not in columns:
            cursor.execute("ALTER TABLE council_updates ADD COLUMN pdf_urls TEXT")

        # Migration: podcast_status
        if "podcast_status" not in columns:
            cursor.execute("ALTER TABLE council_updates ADD COLUMN podcast_status TEXT DEFAULT 'skipped'")
        if "podcast_date" not in columns:
            cursor.execute("ALTER TABLE council_updates ADD COLUMN podcast_date TIMESTAMP")
    
    conn.commit()
    return conn

def fetch_with_playwright(url, max_attempts=3):
    """Fetch URL using Playwright (optimized for local execution)."""
    for attempt in range(max_attempts):
        try:
            print(f"[*] Fetching (attempt {attempt+1}): {url}")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                response = page.goto(url, wait_until="networkidle", timeout=60000)
                
                if response and response.status == 200:
                    content = page.content()
                    browser.close()
                    return BeautifulSoup(content, 'html.parser')
                else:
                    status = response.status if response else "No response"
                    print(f"[!] Received status {status} for {url}")
                    browser.close()
        except Exception as e:
            print(f"[!] Attempt {attempt+1} failed: {e}")
            if attempt < max_attempts - 1:
                time.sleep(5)
    return None

def extract_pdf_urls(page_url, soup):
    """Extract all PDF links from a METI article page."""
    links = soup.find_all('a', href=True)
    pdf_urls = []
    for link in links:
        href = link.get('href')
        if href and (href.lower().endswith('.pdf') or '/pdf/' in href.lower()):
            abs_url = urljoin(page_url, href)
            pdf_urls.append(abs_url)
    return list(dict.fromkeys(pdf_urls))

def get_breadcrumb_list(url, soup):
    """Extract breadcrumbs from article page soup."""
    try:
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
    except Exception as e:
        print(f"  Error parsing categories for {url}: {e}")
    return []

def scrape_updates():
    soup = fetch_with_playwright(TARGET_URL)
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

def process_and_save(conn, updates):
    cursor = conn.cursor()
    new_count = 0
    skipped_count = 0
    
    for item in updates:
        cursor.execute("SELECT id, category1, podcast_status, pdf_urls FROM council_updates WHERE url = ?", (item['url'],))
        existing = cursor.fetchone()
        
        # すでにカテゴリかつPDFリンク取得済み かつ podcast_statusが設定済みならスキップ
        if existing and existing[1] and existing[3] and existing[2] != 'skipped_placeholder':
            skipped_count += 1
            continue
            
        print(f"  Processing category and PDFs for: {item['title']}...")
        article_soup = fetch_with_playwright(item['url'])
        if not article_soup:
            print(f"  [!] Failed to reach article: {item['url']}")
            continue

        cat_list = get_breadcrumb_list(item['url'], article_soup)
        pdf_urls = extract_pdf_urls(item['url'], article_soup)
        
        padded_cats = (cat_list + [None] * MAX_CATEGORIES)[:MAX_CATEGORIES]
        status = 'pending' if cat_list and cat_list[0] in PODCAST_TARGET_CATEGORIES else 'skipped'
        
        pdf_urls_json = json.dumps(pdf_urls, ensure_ascii=False)

        if existing:
            update_sql = ", ".join([f"category{i+1} = ?" for i in range(MAX_CATEGORIES)])
            params = padded_cats + [status, pdf_urls_json, existing[0]]
            cursor.execute(f"UPDATE council_updates SET {update_sql}, podcast_status = ?, pdf_urls = ? WHERE id = ?", params)
            new_count += 1
        else:
            placeholders = ", ".join(["?"] * (MAX_CATEGORIES + 5))
            col_names = ", ".join([f"category{i+1}" for i in range(MAX_CATEGORIES)])
            params = [item['date'], item['title'], item['url'], status, pdf_urls_json] + padded_cats
            cursor.execute(f'''
                INSERT INTO council_updates (date, title, url, podcast_status, pdf_urls, {col_names})
                VALUES ({placeholders})
            ''', params)
            new_count += 1
        conn.commit()
    
    print(f"Summary: Processed {len(updates)} items. {new_count} items updated/added, {skipped_count} items skipped.")
    return new_count

def main():
    conn = init_db()
    updates = scrape_updates()
    
    if not updates:
        print("[!] No new updates found. Exiting.")
        conn.close()
        sys.exit(0)

    new_count = process_and_save(conn, updates)
    
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM council_updates WHERE podcast_status = 'pending'")
    pending_count = cursor.fetchone()[0]
    print(f"Podcast Queue Status: {pending_count} items pending.")
    
    conn.close()
    
    if new_count > 0:
        print("\n" + "="*50)
        print("  DB HAS BEEN UPDATED!")
        print("  Please run the following to sync with GitHub:")
        print("  git add meti_shingikai.db && git commit -m 'Update DB' && git push")
        print("="*50)

if __name__ == "__main__":
    main()
