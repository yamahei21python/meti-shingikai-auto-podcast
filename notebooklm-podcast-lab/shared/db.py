"""Database helper functions for Energy Audio system."""

import sqlite3
from datetime import datetime
from typing import Optional

from .config import DB_PATH, MAX_CATEGORIES, TARGET_CATS_METI
from .logging import get_logger

logger = get_logger("db")


def init_db(conn: Optional[sqlite3.Connection] = None) -> sqlite3.Connection:
    """
    Initialize database with schema.

    Args:
        conn: Optional existing connection

    Returns:
        Database connection
    """
    if conn is None:
        conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()
    cat_cols_def = ", ".join([f"category{i + 1} TEXT" for i in range(MAX_CATEGORIES)])

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS council_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            title TEXT,
            url TEXT UNIQUE,
            {cat_cols_def},
            podcast_status TEXT DEFAULT 'pending',
            pdf_urls TEXT,
            podcast_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    return conn


def is_url_in_db(conn: sqlite3.Connection, url: str) -> bool:
    """
    Check if URL already exists in database.

    Args:
        conn: Database connection
        url: URL to check

    Returns:
        True if URL exists
    """
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM council_updates WHERE url = ?", (url,))
    return cursor.fetchone() is not None


def save_updates(conn: sqlite3.Connection, updates: list[dict]) -> int:
    """
    Save updates to database.

    Args:
        conn: Database connection
        updates: List of update dictionaries

    Returns:
        Number of new items added
    """
    cursor = conn.cursor()
    new_count = 0

    for item in updates:
        try:
            # Determine status based on categories
            category1 = item["categories"][0] if len(item["categories"]) > 0 else None
            category2 = item["categories"][1] if len(item["categories"]) > 1 else None

            status = "skipped"
            if category1 == "OCCTO":
                status = "pending"
            elif category1 == "METI" and category2 in TARGET_CATS_METI:
                status = "pending"

            # Build insert query
            placeholders = ", ".join(["?"] * (MAX_CATEGORIES + 4))
            cat_list = (item["categories"] + [None] * MAX_CATEGORIES)[:MAX_CATEGORIES]
            params = [item["date"], item["title"], item["url"], status] + cat_list
            col_names = ", ".join([f"category{i + 1}" for i in range(MAX_CATEGORIES)])

            cursor.execute(
                f"""
                INSERT OR IGNORE INTO council_updates (date, title, url, podcast_status, {col_names})
                VALUES ({placeholders})
            """,
                params,
            )

            if cursor.rowcount > 0:
                new_count += 1

        except Exception as e:
            logger.error(f"DB insert error: {e}")

    conn.commit()
    return new_count


def get_pending_items(limit: int = 2) -> list[tuple]:
    """
    Get pending items to process.

    Args:
        limit: Maximum number of items to return

    Returns:
        List of (id, title, url, date, pdf_urls) tuples
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, title, url, date, pdf_urls 
        FROM council_updates 
        WHERE podcast_status = 'pending' 
        AND (
            category1 = 'OCCTO' OR 
            (category1 = 'METI' AND category2 IN (?, ?))
        )
        ORDER BY date ASC, id ASC 
        LIMIT ?
    """,
        (*TARGET_CATS_METI, limit),
    )

    rows = cursor.fetchall()
    conn.close()
    return rows


def update_status(item_id: int, status: str) -> None:
    """
    Update item status in database.

    Args:
        item_id: Database item ID
        status: New status (e.g., 'pending', 'done', 'skipped')
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        """
        UPDATE council_updates 
        SET podcast_status = ?, podcast_date = ? 
        WHERE id = ?
    """,
        (status, now, item_id),
    )

    conn.commit()
    conn.close()


def get_db_path() -> str:
    """Get database path."""
    return str(DB_PATH)
