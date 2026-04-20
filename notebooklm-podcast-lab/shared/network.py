"""
Shared Network Client - Robust HTTP requests for METI/OCCTO scraping.
"""

import time
import os
from typing import Optional, Dict, Any
from curl_cffi import requests
from bs4 import BeautifulSoup
from .logging import get_logger
from .config import SOCKS5_PROXY

logger = get_logger("network")

class NetworkClient:
    """
    Robust HTTP client using curl-cffi to impersonate Chrome.
    Centralizes headers and TLS fingerprint configuration.
    """
    
    def __init__(self, use_proxy: bool = True):
        self.use_proxy = use_proxy
        self.proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY} if use_proxy else None
        
        # Chrome 120 (Windows) compliant headers
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    def fetch(self, url: str, headers: Optional[Dict[str, str]] = None, retries: int = 3, timeout: int = 30) -> Optional[Any]:
        """
        Fetch URL with retries and impersonation using curl-cffi Session.
        """
        request_headers = self.default_headers.copy()
        if headers:
            request_headers.update(headers)

        for attempt in range(retries):
            try:
                logger.info(f"Fetching (attempt {attempt + 1}/{retries}): {url}")
                
                # Use Session for explicit impersonation support
                with requests.Session(impersonate="chrome120") as s:
                    response = s.get(
                        url,
                        timeout=timeout,
                        proxies=self.proxies,
                        headers=request_headers,
                    )
                
                if response.status_code == 200:
                    return response
                
                logger.warning(f"Status {response.status_code} for {url} (Attempt {attempt+1})")
                if response.status_code == 403:
                    logger.error("403 Forbidden detected. METI security is blocking.")
                
            except Exception as e:
                logger.error(f"Network error on {url} (Attempt {attempt+1}): {e}")

            if attempt < retries - 1:
                wait_time = 15 * (attempt + 1)
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        return None

    def fetch_soup(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[BeautifulSoup]:
        """Fetch URL and return BeautifulSoup object."""
        response = self.fetch(url, headers=headers)
        if response:
            return BeautifulSoup(response.content, "html.parser")
        return None

def is_github_actions() -> bool:
    """Check if running in GitHub Actions."""
    return os.getenv("GITHUB_ACTIONS") == "true"
