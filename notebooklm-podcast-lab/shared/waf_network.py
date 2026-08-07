"""
WAF対応Network Client - METI (AWS WAF) PDF取得専用.
curl-cffiではなく rnet(Chrome136 impersonate) + awswafトークンソルバーを使用.

フロー:
1. rnetで直接GET (WAFが緩い場合: 200 PDF直接取得)
2. 202 challenge時: neiii/aws-waf-solver でトークン解決 (0.6s)
3. トークンCookie付きで再GET
"""

import asyncio
import os
import re
import sys
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Add awswaf_solver to path
_AWSWAF_DIR = Path(__file__).parent.parent / "awswaf_solver"
if str(_AWSWAF_DIR) not in sys.path:
    sys.path.insert(0, str(_AWSWAF_DIR))

from .logging import get_logger

logger = get_logger("waf_network")

# Default UA (neiii solver default, Chrome 144)
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
)


class WafResponse:
    """Minimal response wrapper compatible with curl_cffi response usage."""

    def __init__(self, status_code, content: bytes, headers: Dict[str, Any] = None):
        # rnet 2.x returns builtins.StatusCode enum (str() -> "200"); normalize to int
        try:
            self.status_code = int(status_code)
        except (TypeError, ValueError):
            self.status_code = int(str(status_code))
        self.content = content
        self.headers = headers or {}
        self._text: Optional[str] = None

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = self.content.decode("utf-8", "ignore")
        return self._text


def _solve_token(url: str, ua: str = DEFAULT_UA) -> Optional[str]:
    """Solve AWS WAF token via neiii/aws-waf-solver."""
    from waf.solver import solve

    try:
        result, _client = asyncio.run(solve(url, ua))
        token = result.get("token")
        if token:
            logger.info(f"WAF token solved: len={len(token)}")
            return token
        logger.error("WAF solver returned no token")
    except RuntimeError as e:
        # challenge URL not found => likely direct success
        logger.info(f"WAF solver skipped ({e})")
    except Exception as e:
        logger.error(f"WAF solver failed: {e}")
    return None


class WafNetworkClient:
    """
    WAF-aware network client for METI PDF downloads.
    Maintains rnet session + aws-waf-token across requests.
    """

    def __init__(self, ua: str = DEFAULT_UA, use_proxy: bool = False):
        self.ua = ua
        self.use_proxy = use_proxy
        self.token: Optional[str] = None
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from waf.solver import _make_client
            self._client = _make_client(ua=self.ua)
        return self._client

    def _fetch_raw(self, url: str, timeout: int = 60) -> WafResponse:
        """Single GET with rnet, no token. Returns WafResponse."""
        from waf.solver import _nav_headers

        client = self._ensure_client()
        async def _get():
            resp = await client.get(
                url,
                headers=_nav_headers(url, self.ua),
                timeout=timeout,
                cookies={"aws-waf-token": self.token} if self.token else None,
            )
            body = await resp.bytes()
            # HeaderMap keys/values are bytes on rnet 2.x -> decode
            hdrs = {}
            if resp.headers:
                for k, v in resp.headers.items():
                    hk = k.decode() if isinstance(k, bytes) else k
                    hv = v.decode() if isinstance(v, bytes) else v
                    hdrs[hk] = hv
            return WafResponse(resp.status_code, body, hdrs)
        return asyncio.run(_get())

    def fetch(self, url: str, headers: Optional[Dict[str, str]] = None,
              retries: int = 3, timeout: int = 60) -> Optional[WafResponse]:
        """
        Fetch URL with WAF handling.
        Retry chain: direct -> solve token -> retry with token.
        """
        attempt = 0
        while attempt < retries:
            attempt += 1
            try:
                resp = self._fetch_raw(url, timeout=timeout)
                logger.info(f"GET {url}: status={resp.status_code} size={len(resp.content)}")

                # PDF success
                if resp.status_code == 200 and resp.content[:5] == b"%PDF-":
                    return resp

                # WAF challenge (202) or 403
                waf_action = resp.headers.get("x-amzn-waf-action", "")
                is_challenge = resp.status_code == 202 or "challenge" in waf_action
                if is_challenge and not self.token:
                    logger.info("WAF challenge detected. Solving token...")
                    token = _solve_token(url, self.ua)
                    if token:
                        self.token = token
                        # save token for reuse across calls
                        _cache_token(token)
                        continue  # retry with token

                # WAF 403 with token => token may be stale, re-solve
                if resp.status_code == 403 and self.token and "challenge.js" in resp.text:
                    logger.info("Token rejected. Re-solving...")
                    self.token = None
                    continue

                # True 404 or other status => return as-is
                return resp

            except Exception as e:
                logger.error(f"Network error on {url} (attempt {attempt}): {e}")

            if attempt < retries:
                time.sleep(10 * attempt)

        return None

    def fetch_soup(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[Any]:
        """Fetch URL and return BeautifulSoup object (for HTML pages)."""
        from bs4 import BeautifulSoup
        resp = self.fetch(url, headers=headers)
        if resp and resp.status_code == 200:
            return BeautifulSoup(resp.content, "html.parser")
        return None

    def download_pdf(self, url: str, dest: Path) -> bool:
        """Download PDF to local path. Returns True on success."""
        resp = self.fetch(url, timeout=120)
        if resp and resp.content[:5] == b"%PDF-":
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            logger.info(f"PDF saved: {dest} ({len(resp.content)} bytes)")
            return True
        logger.error(f"Failed to download PDF: {url}")
        return False

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


# === Token persistence (optional cache file) ===
_TOKEN_CACHE = Path.home() / ".cache" / "meti_awswaf_token.txt"


def _cache_token(token: str):
    try:
        _TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE.write_text(token)
    except Exception:
        pass


def load_cached_token() -> Optional[str]:
    """Load cached token if fresh (< 4 days)."""
    try:
        if _TOKEN_CACHE.exists():
            mtime = _TOKEN_CACHE.stat().st_mtime
            if time.time() - mtime < 4 * 86400:
                return _TOKEN_CACHE.read_text().strip()
    except Exception:
        pass
    return None
