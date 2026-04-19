"""Utility functions for Energy Audio system."""

import re
from datetime import datetime
from typing import Optional


def sanitize_filename(text: str) -> str:
    """
    Remove invalid characters from filename and limit length.

    Args:
        text: Input text

    Returns:
        Sanitized filename string
    """
    text = re.sub(r'[\\/:*?"<>|／]', "", text)
    text = text.replace(" ", "_").replace("　", "_")
    return text[:200]


def format_date_yyyymmdd(date_str: str) -> str:
    """
    Convert 'YYYY-MM-DD' to 'YYYYMMDD'.

    Args:
        date_str: Date string in various formats

    Returns:
        Formatted date string (YYYYMMDD)
    """
    try:
        if date_str and "-" in date_str:
            return date_str.replace("-", "")
        nums = re.findall(r"\d+", date_str)
        if len(nums) >= 3:
            return f"{int(nums[0]):04d}{int(nums[1]):02d}{int(nums[2]):02d}"
    except Exception:
        pass
    return datetime.now().strftime("%Y%m%d")


def normalize_date(date_str: Optional[str]) -> Optional[str]:
    """
    Normalize Japanese date format to ISO.

    Args:
        date_str: Date string like '2026年4月10日'

    Returns:
        Normalized date string like '2026-04-10'
    """
    if not date_str:
        return None

    # 2026年4月10日 -> 2026-04-10
    match = re.search(r"(\d{4})[年.](\d{1,2})[月.](\d{1,2})", date_str)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    return date_str


def format_timestamp() -> str:
    """Get current timestamp string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
