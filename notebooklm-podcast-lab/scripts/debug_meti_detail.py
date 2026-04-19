"""
Debug script - Analyze METI article page structure.

Usage:
    python debug_meti_detail.py [url]
"""

import sys
import os

# Use curl-cffi
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup


SOCKS5_PROXY = os.getenv("SOCKS5_PROXY", "socks5://127.0.0.1:40000")
DEFAULT_URL = "https://www.meti.go.jp/shingikai/safety_security/kankyo_shinsa/chinetsu/2026_001.html"


def analyze_page(url: str):
    """Analyze METI article page structure."""
    proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}

    print(f"[*] Fetching: {url}")

    try:
        response = curl_requests.get(
            url, impersonate="chrome120", timeout=30, proxies=proxies
        )
        print(f"[*] Status: {response.status_code}")
        print(f"[*] Response Length: {len(response.content)}")

        soup = BeautifulSoup(response.content, "html.parser")

        # List all IDs
        ids = [tag.get("id") for tag in soup.find_all(id=True)]
        print(f"[*] Found IDs: {ids[:50]}")

        # Search for breadcrumb
        b_tags = soup.find_all(string=lambda s: "breadcrumb" in s.lower())
        print(f"[*] Tags containing 'breadcrumb': {len(b_tags)}")

        breadcrumb = soup.find(id="breadcrumb")
        if breadcrumb:
            print("[+] Found #breadcrumb!")
            print(breadcrumb.prettify()[:1000])
        else:
            print("[!] #breadcrumb NOT found")
            # Alternatives
            pan = (
                soup.find(id="pan")
                or soup.find(class_="pan")
                or soup.find(id="topicpath")
            )
            if pan:
                print(
                    f"[+] Found: {pan.name} (id={pan.get('id')}, class={pan.get('class')})"
                )
                print(pan.prettify()[:1000])
            else:
                print("[!] No breadcrumb container found")
                if soup.body:
                    print(soup.body.get_text()[:500])

    except Exception as e:
        print(f"[!] Error: {e}")


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    analyze_page(url)


if __name__ == "__main__":
    main()
