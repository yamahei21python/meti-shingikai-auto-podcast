"""Test curl-cffi network connectivity for METI/OCCTO scraping."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import NetworkClient, METI_URL, OCCTO_URL, logger, setup_logging

setup_logging()

USE_PROXY = os.getenv("USE_PROXY", "true").lower() in ("true", "1", "yes")


def main():
    use_proxy = USE_PROXY
    logger.info(f"Proxy mode: {use_proxy}")

    client = NetworkClient(use_proxy=use_proxy)

    try:
        # Test METI
        logger.info(f"Fetching METI: {METI_URL}")
        soup = client.fetch_soup(METI_URL)
        if soup:
            title = soup.title.string if soup.title else "N/A"
            logger.info(f"[OK] METI title: {title}")
        else:
            logger.error("[FAIL] METI fetch returned None")
            sys.exit(1)

        # Test OCCTO
        logger.info(f"Fetching OCCTO: {OCCTO_URL}")
        soup2 = client.fetch_soup(OCCTO_URL)
        if soup2:
            title2 = soup2.title.string if soup2.title else "N/A"
            logger.info(f"[OK] OCCTO title: {title2}")
        else:
            logger.error("[FAIL] OCCTO fetch returned None")
            sys.exit(1)

        logger.info("All tests passed.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
