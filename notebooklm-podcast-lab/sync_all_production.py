"""
Production scraper for METI & OCCTO council updates.

Scrapes both sites, saves new items to SQLite DB.

Usage:
    python sync_all_production.py
"""

import os
import re
import sys
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import (
    METI_URL,
    OCCTO_URL,
    CouncilUpdate,
    NetworkClient,
    init_db,
    is_url_in_db,
    logger,
    normalize_date,
    save_updates,
    setup_logging,
)

setup_logging()


def parse_meti_updates(soup: BeautifulSoup) -> list[CouncilUpdate]:
    """
    Parse METI審議会 index page for recent updates.

    Expected structure:
      - Articles with date + title + link
      - Each article may belong to a category (審議会名)
    """
    updates = []

    # METI 審議会 page structure: list items with date and link
    items = soup.select("li, tr, dd, div")

    current_category = None

    for el in items:
        # Detect category headers (審議会名)
        header = el.find(["h2", "h3", "h4", "dt", "th"])
        if header:
            text = header.get_text(strip=True)
            if any(kw in text for kw in ["審議会", "委員会", "小委員会", "分科会", "作業部会"]):
                current_category = text
                continue

        # Find date + link pattern
        date_match = re.search(r"(\d{4})[年./](\d{1,2})[月./](\d{1,2})", el.get_text())
        if not date_match:
            continue

        link = el.find("a", href=True)
        if not link:
            continue

        href = link.get("href", "")
        if not href:
            continue

        abs_url = urljoin(METI_URL, href)
        title = link.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        date_str = normalize_date(f"{date_match.group(1)}年{date_match.group(2)}月{date_match.group(3)}日")

        categories = ["METI"]
        if current_category:
            categories.append(current_category)

        updates.append(
            CouncilUpdate(
                date=date_str or "",
                title=title,
                url=abs_url,
                categories=categories,
            )
        )

    return updates


def parse_occto_updates(soup: BeautifulSoup) -> list[CouncilUpdate]:
    """
    Parse OCCTO委員会 page for recent updates.

    Expected structure:
      - Committee sections with meeting links and dates
    """
    updates = []

    # Look for links with dates on OCCTO page
    links = soup.find_all("a", href=True)

    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # Must have a date
        date_match = re.search(r"(\d{4})[年./](\d{1,2})[月./](\d{1,2})", text)
        if not date_match:
            continue

        # Only process committee-related links
        if not any(kw in text for kw in ["委員会", "会議", "開催", "資料"]):
            continue

        if "occto.or.jp" not in href:
            abs_url = urljoin(OCCTO_URL, href)
        else:
            abs_url = href

        title = text.strip()
        date_str = normalize_date(f"{date_match.group(1)}年{date_match.group(2)}月{date_match.group(3)}日")

        updates.append(
            CouncilUpdate(
                date=date_str or "",
                title=title,
                url=abs_url,
                categories=["OCCTO"],
            )
        )

    return updates


def deduplicate(updates: list[CouncilUpdate]) -> list[CouncilUpdate]:
    """Remove duplicates by URL."""
    seen = set()
    result = []
    for u in updates:
        if u.url not in seen:
            seen.add(u.url)
            result.append(u)
    return result


def main():
    logger.info(f"=== Sync Production Start: {datetime.now()} ===")

    client = NetworkClient()
    conn = init_db()

    try:
        all_updates: list[CouncilUpdate] = []

        # === Scrape METI ===
        logger.info(f"Fetching METI: {METI_URL}")
        meti_soup = client.fetch_soup(METI_URL)
        if meti_soup:
            meti_items = parse_meti_updates(meti_soup)
            logger.info(f"METI: found {len(meti_items)} items")
            all_updates.extend(meti_items)
        else:
            logger.error("METI fetch failed")

        # === Scrape OCCTO ===
        logger.info(f"Fetching OCCTO: {OCCTO_URL}")
        occto_soup = client.fetch_soup(OCCTO_URL)
        if occto_soup:
            occto_items = parse_occto_updates(occto_soup)
            logger.info(f"OCCTO: found {len(occto_items)} items")
            all_updates.extend(occto_items)
        else:
            logger.error("OCCTO fetch failed")

        # === Deduplicate & Filter ===
        all_updates = deduplicate(all_updates)

        # Filter out already-known URLs
        new_items = [u for u in all_updates if not is_url_in_db(conn, u.url)]

        logger.info(f"Total: {len(all_updates)}, New: {len(new_items)}")

        # === Save to DB ===
        if new_items:
            count = save_updates(
                conn,
                [
                    {
                        "date": u.date,
                        "title": u.title,
                        "url": u.url,
                        "categories": u.categories,
                    }
                    for u in new_items
                ],
            )
            logger.info(f"Saved {count} new items to DB")
        else:
            logger.info("No new items to save")

    finally:
        client.close()
        conn.close()

    logger.info("=== Sync Complete ===")


if __name__ == "__main__":
    main()
