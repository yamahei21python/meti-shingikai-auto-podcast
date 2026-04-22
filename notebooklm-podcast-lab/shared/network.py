"""
Shared Network Client - Robust HTTP requests for METI/OCCTO scraping.
Version 2.0 (Stateful Session)
"""

import time
import os
import random
from typing import Optional, Dict, Any
from curl_cffi import requests
from bs4 import BeautifulSoup
from .logging import get_logger
from .config import SOCKS5_PROXY

logger = get_logger("network")

class NetworkClient:
    """
    Robust HTTP client using a persistent curl-cffi Session to impersonate Chrome.
    Maintains cookies and TLS session across requests to bypass WAF.
    """
    
    def __init__(self, use_proxy: bool = True):
        self.use_proxy = use_proxy
        self.proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY} if use_proxy else None
        
        # Initialize persistent session
        # Note: METI WAF blocks Chrome TLS fingerprints on GHA (US IPs).
        # Safari and Firefox fingerprints pass through.
        self.session = requests.Session(
            impersonate="safari17_0",
            proxies=self.proxies
        )
        
        # Standard browser headers (Minimal to let impersonation work)
        self.session.headers.update({
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        })
        
        self.last_url = None

    def fetch(self, url: str, headers: Optional[Dict[str, str]] = None, retries: int = 3, timeout: int = 30) -> Optional[Any]:
        """
        Fetch URL using persistent session. Updates Referer automatically.
        """
        request_headers = headers or {}
        
        # Auto-set Referer if moving within the same domain
        if self.last_url and "meti.go.jp" in url and "meti.go.jp" in self.last_url:
            if "Referer" not in request_headers:
                request_headers["Referer"] = self.last_url

        for attempt in range(retries):
            try:
                # Human-like jitter (1-3 seconds)
                if attempt > 0 or self.last_url:
                    wait = random.uniform(1.0, 3.0)
                    time.sleep(wait)

                logger.info(f"Fetching (attempt {attempt + 1}/{retries}): {url}")
                
                response = self.session.get(
                    url,
                    timeout=timeout,
                    headers=request_headers,
                )
                
                if response.status_code == 200:
                    self.last_url = url
                    return response
                
                logger.warning(f"Status {response.status_code} for {url} (Attempt {attempt+1})")
                if response.status_code == 403:
                    logger.error("403 Forbidden detected. Session might be flagged.")
                
            except Exception as e:
                logger.error(f"Network error on {url} (Attempt {attempt+1}): {e}")

            if attempt < retries - 1:
                wait_time = 10 * (attempt + 1)
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        return None

    def fetch_soup(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[BeautifulSoup]:
        """Fetch URL and return BeautifulSoup object."""
        response = self.fetch(url, headers=headers)
        if response:
            return BeautifulSoup(response.content, "html.parser")
        return None

    def close(self):
        """Close the session."""
        self.session.close()

def is_github_actions() -> bool:
    """Check if running in GitHub Actions."""
    return os.getenv("GITHUB_ACTIONS") == "true"
