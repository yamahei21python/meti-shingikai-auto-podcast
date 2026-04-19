"""Shared utilities for Energy Audio system."""

from .config import (
    DB_PATH,
    METI_URL,
    OCCTO_URL,
    SOCKS5_PROXY,
    TARGET_CATS_METI,
    get_venv_python,
    is_github_actions,
)
from .db import (
    get_pending_items,
    init_db,
    is_url_in_db,
    save_updates,
    update_status,
)
from .logging import get_logger, logger, setup_logging
from .notebooklm import (
    init_auth,
    parse_notebook_id,
    parse_task_id,
    run_notebooklm,
    wait_for_task,
)
from .types import CouncilUpdate, PodcastItem, TaskStatus
from .utils import (
    format_date_yyyymmdd,
    format_timestamp,
    normalize_date,
    sanitize_filename,
)

__all__ = [
    # config
    "DB_PATH",
    "METI_URL",
    "OCCTO_URL",
    "SOCKS5_PROXY",
    "TARGET_CATS_METI",
    "get_venv_python",
    "is_github_actions",
    # db
    "init_db",
    "is_url_in_db",
    "save_updates",
    "get_pending_items",
    "update_status",
    # logging
    "setup_logging",
    "get_logger",
    "logger",
    # notebooklm
    "init_auth",
    "run_notebooklm",
    "wait_for_task",
    "parse_notebook_id",
    "parse_task_id",
    # types
    "CouncilUpdate",
    "PodcastItem",
    "TaskStatus",
    # utils
    "sanitize_filename",
    "format_date_yyyymmdd",
    "normalize_date",
    "format_timestamp",
]
