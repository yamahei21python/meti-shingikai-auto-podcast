import bs4
from curl_cffi import requests as curl_requests
import sys

# 一つの詳細ページをターゲットにする
url = "https://www.meti.go.jp/shingikai/safety_security/kankyo_shinsa/chinetsu/2026_001.html"
SOCKS5_PROXY = "socks5://127.0.0.1:40000"
proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}

print(f"[*] Fetching: {url}")
try:
    response = curl_requests.get(url, impersonate="chrome120", timeout=30, proxies=proxies)
    print(f"[*] Status: {response.status_code}")
    print(f"[*] Response Length: {len(response.content)}")
    
    soup = bs4.BeautifulSoup(response.content, "html.parser")
    
    # 全てのIDをリストアップして確認
    ids = [tag.get('id') for tag in soup.find_all(id=True)]
    print(f"[*] Found IDs: {ids[:50]}")
    
    # breadcrumbという文字列が含まれるタグを探す
    b_tags = soup.find_all(string=lambda s: "breadcrumb" in s.lower())
    print(f"[*] Tags containing 'breadcrumb' in string: {len(b_tags)}")
    
    # breadcrumbというIDのタグを直接探す
    breadcrumb = soup.find(id="breadcrumb")
    if breadcrumb:
        print("[+] Found #breadcrumb!")
        print(breadcrumb.prettify()[:1000])
    else:
        print("[!] #breadcrumb NOT found.")
        # 代わりのナビゲーションを探す
        pan = soup.find(id="pan") or soup.find(class_="pan") or soup.find(id="topicpath")
        if pan:
            print(f"[+] Found alternative: {pan.name} (id={pan.get('id')}, class={pan.get('class')})")
            print(pan.prettify()[:1000])
        else:
            print("[!] No obvious breadcrumb container found.")
            # <body>の内容を一部出力
            print(soup.body.get_text()[:500] if soup.body else "No Body")

except Exception as e:
    print(f"[!] Error: {e}")
