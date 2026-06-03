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
      - dl list with class 'date_sp' containing dt and dd elements
    """
    updates = []

    # Map URL path segment to category name
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

    dls = soup.find_all("dl", class_="date_sp")
    for dl in dls:
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")

        for dt, dd in zip(dts, dds):
            # Find date in dt
            date_text = dt.get_text(strip=True)
            date_match = re.search(r"(\d{4})[年./](\d{1,2})[月./](\d{1,2})", date_text)
            if not date_match:
                continue

            date_str = normalize_date(f"{date_match.group(1)}年{date_match.group(2)}月{date_match.group(3)}日")

            # Find link and title in dd
            link = dd.find("a", href=True)
            if not link:
                continue

            href = link.get("href", "")
            if not href:
                continue

            abs_url = urljoin(METI_URL, href)
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Determine category from URL segment
            category2 = None
            if "/shingikai/" in abs_url:
                try:
                    segment = abs_url.split("/shingikai/")[1].split("/")[0]
                    category2 = segment_map.get(segment)
                except Exception as e:
                    logger.error(f"Error parsing category from URL {abs_url}: {e}")

            categories = ["METI"]
            if category2:
                categories.append(category2)

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
    Parse OCCTO homepage for recent committee updates.

    Expected structure:
      - News list with class 'linklist-news' containing items of class 'linklist-news__item'
    """
    updates = []

    items = soup.find_all("li", class_="linklist-news__item")
    for item in items:
        # Check category
        cat_tag = item.find("div", class_="linklist-news__cats")
        if not cat_tag or "委員会" not in cat_tag.get_text():
            continue

        # Get date
        date_tag = item.find("span", class_="linklist-news__date")
        if not date_tag:
            continue

        spans = date_tag.find_all("span")
        if len(spans) >= 2:
            year = spans[0].get_text(strip=True)
            month_day = spans[1].get_text(strip=True)
            if "." in month_day:
                month, day = month_day.split(".")
                date_str = normalize_date(f"{year}年{month}月{day}日")
            else:
                date_str = normalize_date(f"{year}年{month_day}")
        else:
            date_str = normalize_date(date_tag.get_text(strip=True))

        # Get link
        link = item.find("a", href=True)
        if not link:
            continue

        href = link.get("href", "")
        if not href:
            continue

        abs_url = urljoin(OCCTO_URL, href)

        # Get title
        title_tag = item.find("span", class_="linklist-news__txt")
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title:
            title = link.get_text(strip=True)

        # Get committee name as subcategory
        type_tag = item.find("span", class_="linklist-news__type")
        committee = type_tag.get_text(strip=True) if type_tag else "OCCTO"

        updates.append(
            CouncilUpdate(
                date=date_str or "",
                title=title,
                url=abs_url,
                categories=["OCCTO", committee],
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
