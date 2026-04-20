"""Shared utilities for Energy Audio system."""

from .config import (
    # Base Paths
    PROJECT_ROOT,
    PODCASTS_DIR,
    DB_PATH,
    RSS_OUTPUT_PATH,
    # URLs
    METI_URL,
    OCCTO_URL,
    # Proxy / Network
    SOCKS5_PROXY,
    # Worker Settings
    MAX_PROCESS_PER_RUN,
    MAX_CATEGORIES,
    TARGET_CATS_METI,
    # R2 Credentials
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_ENDPOINT,
    R2_BUCKET_NAME,
    R2_PUBLIC_URL,
    # Podcast Metadata
    PODCAST_TITLE,
    PODCAST_DESCRIPTION,
    PODCAST_LINK,
    PODCAST_AUTHOR,
    RSS_FILENAME,
    # Helpers
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
from .network import NetworkClient
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
    "PROJECT_ROOT",
    "PODCASTS_DIR",
    "DB_PATH",
    "RSS_OUTPUT_PATH",
    "METI_URL",
    "OCCTO_URL",
    "SOCKS5_PROXY",
    "MAX_PROCESS_PER_RUN",
    "MAX_CATEGORIES",
    "TARGET_CATS_METI",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT",
    "R2_BUCKET_NAME",
    "R2_PUBLIC_URL",
    "PODCAST_TITLE",
    "PODCAST_DESCRIPTION",
    "PODCAST_LINK",
    "PODCAST_AUTHOR",
    "RSS_FILENAME",
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
    "NetworkClient",
]
