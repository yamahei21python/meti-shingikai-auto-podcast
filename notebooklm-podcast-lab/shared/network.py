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
    Robust HTTP client using a persistent curl-cffi Session to impersonate browsers.
    Maintains cookies and TLS session across requests to bypass WAF.
    """
    
    # Browser impersonation profiles in order of preference
    # Updated: older profiles (firefox133, safari17_0) blocked by METI WAF
    BROWSER_PROFILES = ["firefox135", "safari18_0", "chrome133a"]
    
    def __init__(self, use_proxy: bool = True, initial_profile: str = "firefox135"):
        self.use_proxy = use_proxy
        proxy_url = SOCKS5_PROXY.strip() if SOCKS5_PROXY else None
        self.proxies = {"http": proxy_url, "https": proxy_url} if (use_proxy and proxy_url) else None
        
        # Initialize persistent session with Firefox 135 (latest fingerprint)
        # Note: METI WAF blocks older profiles (firefox133, safari17_0) on GHA.
        # Fallback chain: firefox135 -> safari18_0 -> chrome133a
        self.current_profile = initial_profile
        self.session = requests.Session(
            impersonate=self.current_profile,
            proxies=self.proxies
        )
        
        # Standard browser headers (Minimal to let impersonation work)
        self.session.headers.update({
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        })
        
        self.last_url = None

    def fetch(self, url: str, headers: Optional[Dict[str, str]] = None, retries: int = 3, timeout: int = 30) -> Optional[Any]:
        """
        Fetch URL using persistent session with fallback browser profiles.
        Updates Referer automatically.
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

                logger.info(f"Fetching (attempt {attempt + 1}/{retries}): {url} (profile: {self.current_profile})")
                
                response = self.session.get(
                    url,
                    timeout=timeout,
                    headers=request_headers,
                    proxies=self.proxies
                )
                
                if response.status_code == 200:
                    self.last_url = url
                    return response
                
                logger.warning(f"Status {response.status_code} for {url} (Attempt {attempt+1})")
                if response.status_code == 403:
                    logger.error("403 Forbidden detected. Session might be flagged.")
                    # Fallback to alternative browser profile
                    self._switch_browser_profile()
                
            except Exception as e:
                logger.error(f"Network error on {url} (Attempt {attempt+1}): {e}")
                # Fallback on network errors too
                self._switch_browser_profile()

            if attempt < retries - 1:
                wait_time = 10 * (attempt + 1)
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        return None
    
    def _switch_browser_profile(self):
        """Switch to the next browser profile in the fallback list."""
        current_index = self.BROWSER_PROFILES.index(self.current_profile)
        next_index = (current_index + 1) % len(self.BROWSER_PROFILES)
        self.current_profile = self.BROWSER_PROFILES[next_index]
        
        # Recreate session with new profile
        self.session.close()
        self.session = requests.Session(
            impersonate=self.current_profile,
            proxies=self.proxies
        )
        self.session.headers.update({
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        })
        
        logger.info(f"Switched to browser profile: {self.current_profile}")

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
