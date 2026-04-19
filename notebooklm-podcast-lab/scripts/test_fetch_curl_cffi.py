"""
Test script - Verify curl-cffi fetch functionality.

Usage:
    python test_fetch_curl_cffi.py
"""

import os
import sys
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests


URL = "https://www.meti.go.jp/shingikai/enecho/shoene_shinene/suiso_seisaku/015.html"
SOCKS5_PROXY = os.getenv("SOCKS5_PROXY", "socks5://127.0.0.1:40000")


def test_fetch_with_curl_cffi():
    """Test fetch with curl-cffi."""
    print(f"[*] Testing fetch: {URL}")

    if os.getenv("GITHUB_ACTIONS"):
        print(f"[*] Using proxy: {SOCKS5_PROXY}")
        proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}
    else:
        print("[*] Running locally, proxy skipped")
        proxies = None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }

    try:
        response = curl_requests.get(
            URL, impersonate="chrome120", timeout=30, proxies=proxies, headers=headers
        )

        print(f"[+] Status: {response.status_code}")

        if response.status_code == 200:
            print("[+] Successfully fetched!")
            soup = BeautifulSoup(response.content, "html.parser")

            # Check PDF links
            pdf_links = []
            for link in soup.find_all("a", href=True):
                href = link.get("href")
                if href and (href.lower().endswith(".pdf") or "/pdf/" in href.lower()):
                    pdf_links.append(urljoin(URL, href))

            unique_pdfs = list(dict.fromkeys(pdf_links))
            print(f"[+] Found {len(unique_pdfs)} PDF links:")
            for pdf in unique_pdfs[:5]:
                print(f"  - {pdf}")
        else:
            print(f"[!] Failed: {response.text[:200]}")
            sys.exit(1)

    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_fetch_with_curl_cffi()
