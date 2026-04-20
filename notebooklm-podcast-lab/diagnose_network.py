
import sys
import os
import random
import time
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent))

from shared import NetworkClient, logger, setup_logging

# Initialize logging for stdout
setup_logging()

def diagnose():
    # 1. 直接接続（プロキシなし）のテスト
    print("\n=== Test 1: Direct Connection (No Proxy) ===")
    client_direct = NetworkClient(use_proxy=False)
    
    url = "https://www.meti.go.jp/shingikai/index.html"
    res1 = client_direct.fetch(url)
    if res1:
        print(f"Direct Access SUCCESS! Status: {res1.status_code}")
        # セッションCookieがセットされているか確認
        if res1.cookies:
            print(f"Cookies obtained: {list(res1.cookies.keys())}")
    else:
        print("Direct Access FAILED (403 or Error)")

    time.sleep(2)

    # 2. プロキシ経由のテスト
    print("\n=== Test 2: Proxy Connection (SOCKS5) ===")
    client_proxy = NetworkClient(use_proxy=True)
    try:
        # プロキシ接続エラーで時間を取られないよう retries を一時的に 0 に
        res2 = client_proxy.fetch(url, retries=0) 
        if res2:
            print(f"Proxy Access SUCCESS! Status: {res2.status_code}")
        else:
            print("Proxy Access FAILED (403 or Error)")
    except Exception as e:
        print(f"Proxy Connection Error (Likely WARP not running): {e}")

if __name__ == "__main__":
    diagnose()
