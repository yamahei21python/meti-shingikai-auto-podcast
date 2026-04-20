"""
Sync Production - Fetch METI/OCCTO updates and save to DB.

Usage:
    python sync_all_production.py
"""

import sys
from datetime import datetime
from urllib.parse import urljoin

import bs4
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Add parent to path for shared modules
sys.path.insert(0, ".")

from shared import (
    METI_URL,
    OCCTO_URL,
    SOCKS5_PROXY,
    NetworkClient,
    init_db,
    is_url_in_db,
    save_updates,
    normalize_date,
    logger,
)


# === Configuration ===
MAX_CATEGORIES = 10


def fetch_meti_updates(client: NetworkClient) -> list[dict]:
    """
    Fetch latest updates from METI website.
    Uses persistent NetworkClient for session reuse.
    """
    logger.info(f"Fetching METI: {METI_URL}")
    soup = client.fetch_soup(METI_URL)
    if not soup:
        return []

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


def fetch_meti_categories(client: NetworkClient, url: str) -> list[str]:
    """
    Fetch categories from individual METI page via breadcrumb.
    Uses persistent NetworkClient for session reuse.
    """
    try:
        soup = client.fetch_soup(url, headers={"Referer": METI_URL})
        if not soup:
            return ["METI"]

        # Breadcrumb (通常 <div class="pan"> または <div id="breadcrumb">)
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
    logger.info(f"=== Sync Pipeline Start: {datetime.now()} ===")

    # Initialize DB
    conn = init_db()
    
    # Initialize shared network client for persistent session
    client = NetworkClient()

    try:
        # 1. METI Updates
        logger.info("Syncing METI...")
        meti_data = fetch_meti_updates(client)
        logger.info(f"METI: Found {len(meti_data)} items")
        
        processed_meti = []
        for item in meti_data:
            if not is_url_in_db(conn, item["url"]):
                logger.info(f"Fetching categories: {item['title'][:40]}...")
                item["categories"] = fetch_meti_categories(client, item["url"])
                # No extra sleep here as NetworkClient has internal jitter
            processed_meti.append(item)
            
        if processed_meti:
            save_updates(conn, processed_meti)
            logger.info(f"Saved {len(processed_meti)} METI updates to DB.")

        # 2. OCCTO Updates
        logger.info("Syncing OCCTO...")
        occto_data = fetch_occto_updates() # OCCTO uses Playwright, keep as is
        if occto_data:
            save_updates(conn, occto_data)
            logger.info(f"Saved {len(occto_data)} OCCTO updates to DB.")

    finally:
        client.close()
        conn.close()
        logger.info(f"=== Sync Pipeline Finished ===")

if __name__ == "__main__":
    main()
