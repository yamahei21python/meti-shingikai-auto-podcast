import sys
import os
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Config
URL = "https://www.meti.go.jp/shingikai/enecho/shoene_shinene/suiso_seisaku/015.html"
SOCKS5_PROXY = "socks5://127.0.0.1:40000"

def test_fetch_with_curl_cffi():
    print(f"[*] Testing fetch with curl-cffi: {URL}")
    
    # Pre-check proxy: use if specified or if on GHA (unless USE_PROXY=false)
    use_proxy_env = os.getenv("USE_PROXY", "").lower()
    
    if use_proxy_env == "false":
        print("[*] Proxy explicitly disabled via USE_PROXY=false")
        proxies = None
    elif use_proxy_env == "true" or os.getenv("GITHUB_ACTIONS"):
        print(f"[*] Using proxy: {SOCKS5_PROXY}")
        proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}
    else:
        print("[*] Running locally, proxy skipped unless USE_PROXY=true.")
        proxies = None

    headers = {
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

    try:
        # Impersonate chrome120
        response = curl_requests.get(
            URL, 
            impersonate="chrome120", 
            timeout=30, 
            proxies=proxies, 
            headers=headers
        )
        
        print(f"[+] Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("[+] Successfully fetched the page!")
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Check for PDF links
            pdf_links = []
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if href and (href.lower().endswith('.pdf') or '/pdf/' in href.lower()):
                    pdf_links.append(urljoin(URL, href))
            
            unique_pdfs = list(dict.fromkeys(pdf_links))
            print(f"[+] Found {len(unique_pdfs)} PDF links:")
            for pdf in unique_pdfs[:5]: # Show first 5
                print(f"  - {pdf}")
        else:
            print(f"[!] Failed to fetch. Content snippet: {response.text[:200]}")
            sys.exit(1)

    except Exception as e:
        print(f"[!] Error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_fetch_with_curl_cffi()
