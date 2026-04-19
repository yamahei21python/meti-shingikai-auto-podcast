"""Logging設定 for Energy Audio system."""

import logging
import sys
from typing import Optional


# Log format
LOG_FORMAT = "[%(asctime)s] %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int = logging.INFO, log_file: Optional[str] = None, verbose: bool = False
) -> logging.Logger:
    """
    Setup logging with console and optional file output.

    Args:
        level: Logging level (default: INFO)
        log_file: Optional file path for file logging
        verbose: Enable DEBUG level if True

    Returns:
        Configured logger instance
    """
    if verbose:
        level = logging.DEBUG

    logger = logging.getLogger("energy_audio")
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(file_handler)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get logger instance.

    Args:
        name: Logger name (default: "energy_audio")

    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"energy_audio.{name}")
    return logging.getLogger("energy_audio")


# Default logger
logger = get_logger()
