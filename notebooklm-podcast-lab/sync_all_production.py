"""
Sync Production - Fetch METI/OCCTO updates and save to DB.

Usage:
    python sync_all_production.py
"""

import sys
from datetime import datetime
from urllib.parse import urljoin

import bs4
import requests as curl_requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Add parent to path for shared modules
sys.path.insert(0, ".")

from shared import (
    METI_URL,
    OCCTO_URL,
    SOCKS5_PROXY,
    init_db,
    is_url_in_db,
    save_updates,
    normalize_date,
    logger,
)


# === Configuration ===
MAX_CATEGORIES = 10


def fetch_meti_updates() -> list[dict]:
    """
    Fetch latest updates from METI website.

    Returns:
        List of update dictionaries with date, title, url, categories
    """
    logger.info(f"Fetching METI: {METI_URL}")
    proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}
    
    # Chrome 120 compliant headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.google.com/",
    }

    try:
        response = curl_requests.get(
            METI_URL,
            impersonate="chrome120",
            timeout=60,
            proxies=proxies,
            headers=headers,
        )

        if response.status_code != 200:
            logger.warning(f"METI returned status: {response.status_code}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        content_area = (
            soup.find("div", id="main_contents")
            or soup.find("div", id="contents")
            or soup
        )
        dl_list = content_area.find("dl")
        if not dl_list:
            return []

        updates = []
        dt_tags = dl_list.find_all("dt")
        dd_tags = dl_list.find_all("dd")

        for dt, dd in zip(dt_tags, dd_tags):
            date_str = dt.get_text(strip=True)
            link_tag = dd.find("a")
            if not link_tag:
                continue

            updates.append(
                {
                    "date": normalize_date(date_str),
                    "title": link_tag.get_text(strip=True),
                    "url": urljoin(METI_URL, link_tag.get("href")),
                    "categories": ["METI"],
                }
            )

        return updates

    except Exception as e:
        logger.error(f"METI fetch error: {e}")
        return []


def fetch_meti_categories(url: str) -> list[str]:
    """
    Fetch categories from individual METI page via breadcrumb.

    Args:
        url: Individual article URL

    Returns:
        List of category strings
    """
    proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}
    try:
        # Chrome 120 compliant headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": METI_URL,
        }
        response = curl_requests.get(
            url, impersonate="chrome120", timeout=30, proxies=proxies, headers=headers
        )

        if response.status_code != 200:
            return ["METI"]

        soup = BeautifulSoup(response.content, "html.parser")
        breadcrumb = soup.find("div", class_="pan") or soup.find("div", id="breadcrumb")

        if not breadcrumb:
            title = soup.title.string if soup.title else "No Title"
            logger.warning(f"Breadcrumb not found. Title: {title}")
            return ["METI"]

        # Extract category text from breadcrumb
        items = []
        for li in breadcrumb.find_all(["li", "a"]):
            text = li.get_text(strip=True)
            if text and text not in items:
                items.append(text)

        # Filter out common non-category items
        exclude = ["ホーム", "審議会・研究会", "HOME", "审议会・研究会"]
        categories = ["METI"]
        for item in items:
            if item and item not in exclude and item not in categories:
                categories.append(item)

        # Remove last item (current page title)
        if len(categories) > 2:
            categories.pop()

        if len(categories) > 1:
            logger.info(f"Categories: {'>'.join(categories)}")

        return categories

    except Exception as e:
        logger.error(f"Category fetch error ({url}): {e}")
        return ["METI"]


def fetch_occto_updates() -> list[dict]:
    """
    Fetch latest updates from OCCTO website using Playwright.

    Returns:
        List of update dictionaries
    """
    logger.info(f"Fetching OCCTO: {OCCTO_URL}")
    updates = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, proxy={"server": SOCKS5_PROXY})
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            )
            page = context.new_page()
            page.goto(OCCTO_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("a.linklist-cms02__link", timeout=30000)

            soup = BeautifulSoup(page.content(), "html.parser")
            blocks = soup.find_all("a", class_="linklist-cms02__link")

            import re

            for block in blocks:
                date_tag = block.find("span", string=re.compile(r"開催日："))
                date_raw = (
                    date_tag.get_text(strip=True).replace("開催日：", "")
                    if date_tag
                    else ""
                )
                spans = block.find_all("span")
                committee = (
                    spans[1].get_text(strip=True) if len(spans) > 1 else "Unknown"
                )
                title_tag = block.find("p")

                updates.append(
                    {
                        "date": normalize_date(date_raw),
                        "title": title_tag.get_text(strip=True)
                        if title_tag
                        else "No Title",
                        "url": urljoin(OCCTO_URL, block.get("href")),
                        "categories": ["OCCTO", committee],
                    }
                )

            browser.close()

        except Exception as e:
            logger.error(f"OCCTO fetch error: {e}")

    return updates


def main():
    """Main sync pipeline."""
    print(f"\n=== Sync Pipeline Start: {datetime.now()} ===")

    # Initialize DB
    conn = init_db()

    # 1. Fetch METI
    meti_data = fetch_meti_updates()
    logger.info(f"METI: Found {len(meti_data)} items")

    # Check new items for categories
    processed_meti = []
    logger.info("Checking for new METI items...")

    for item in meti_data:
        if not is_url_in_db(conn, item["url"]):
            logger.info(f"Fetching categories: {item['title'][:40]}...")
            item["categories"] = fetch_meti_categories(item["url"])
            import time

            time.sleep(1)  # Rate limiting
        processed_meti.append(item)

    # 2. Fetch OCCTO
    occto_data = fetch_occto_updates()
    logger.info(f"OCCTO: Found {len(occto_data)} items")

    # 3. Save to DB
    all_data = processed_meti + occto_data
    added = save_updates(conn, all_data)
    logger.info(f"Added {added} new items to DB")

    conn.close()
    print("=== Sync Pipeline Finished ===\n")


if __name__ == "__main__":
    main()
