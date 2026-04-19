# 報告書：経済産業省（METI）サイトへのアクセス制限（403 Forbidden）に関する現状と対策案

## 1. 問題の概要
GitHub Actions上で実行しているポッドキャスト生成パイプラインにおいて、経済産業省（METI）のWebサイトからアクセスを拒否され、資料（PDF）の取得に失敗する事象が発生しています。

- **発生事象**: HTTP 403 Forbidden
- **発生環境**: GitHub Actions (ubuntu-latest)
- **現在の対策**: 
    - `curl-cffi` によるブラウザフィンガープリントの偽装（Chrome 120 impersonation）
    - `Cloudflare WARP` によるプロキシ経由のIP秘匿
- **結果**: 対策を講じているにもかかわらず、セキュリティフィルターによってボット判定され、アクセスが遮断されている。

## 2. ログの内容
GitHub Actionsの実行ログから、以下の失敗パターンが確認されています。

```text
[*] Fetching article with curl-cffi (attempt 1/3): https://www.meti.go.jp/shingikai/enecho/.../007.html
[!] Received status 403 for https://www.meti.go.jp/shingikai/enecho/.../007.html
[!] 403 Forbidden detected. METI security is blocking the request.
[*] Waiting 15s before retry...
... (3回試行するもすべて403)
[!] No PDF links found on the page or provided.
[!] FAILED: mp3=False, md=False. Keeping status as pending for retry.
```

## 3. 関連コード
問題箇所に関連する主要なコードは以下の通りです。

### 3.1. フェッチロジック (`notebooklm-podcast-lab/generate_podcast_from_article.py`)
`curl-cffi` を使用してChromeを偽装している箇所です。

```python
def fetch_article_page(url: str) -> BeautifulSoup | None:
    proxies = None
    if is_github_actions() or os.path.exists("/usr/bin/warp-cli"):
        proxies = {"http": SOCKS5_PROXY, "https": SOCKS5_PROXY}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }

    for attempt in range(3):
        try:
            response = curl_requests.get(
                url,
                impersonate="chrome120",
                timeout=30,
                proxies=proxies,
                headers=headers,
            )
            if response.status_code == 200:
                return BeautifulSoup(response.content, "html.parser")
            # ... 403時のリトライ処理 ...
```

### 3.2. ワークフロー設定 (`.github/workflows/daily_sync_all.yml`)
Cloudflare WARPをプロキシモードで起動している箇所です。

```yaml
      - name: Install Cloudflare WARP
        run: |
          # ... インストール処理 ...
      - name: Connect WARP (Proxy Mode)
        run: |
          warp-cli --accept-tos registration new
          warp-cli --accept-tos mode proxy
          warp-cli --accept-tos connect
          sleep 5
```

## 4. 原因の考察
現在、以下の要因が推測されます。

1. **Cloudflare IP帯域のブロッキング**: 
   経産省のファイアウォール（WAF）が、Cloudflare WARPの出口IPアドレス帯域全体を「リスクが高い」として遮断している可能性がある。
2. **TLSフィンガープリントの不一致**: 
   `curl-cffi` の `impersonate="chrome120"` を使用しているが、特定のJA3フィンガープリントやHTTP/2の設定が、実際のChromeの挙動と微妙に異なり、検知されている可能性がある。
3. **ヘッダー情報の不足**: 
   `User-Agent` は設定しているが、最近のブラウザが送信する `Sec-Fetch-*` などのモダンなヘッダーが欠落しているため、不自然なリクエストとみなされている。

## 5. 解決策の提案

### 案A: ヘッダー情報の最新化（厳密一致） (推奨)
`curl-cffi` の `impersonate="chrome120"` と完全に整合性が取れるよう、Chrome 120 固有のヘッダーおよびモダンな Client Hints (`sec-ch-*`) を追加します。
※フィンガープリント（通信の癖）と `User-Agent` が矛盾すると、WAFによって即座にブロックされるため、ランダム化は行わず厳密に一致させます。

```python
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
```

### 案B: プロキシ構成の見直し
Cloudflare WARPを無効化し、GitHub ActionsのネイティブIPで試行するか、あるいは別の日本のレジデンシャルプロキシを検討する。
※経産省は海外IPを厳しく制限している場合があるため、WARPの出口が海外（香港など）になっていると403になりやすい。

### 案C: アクセス間隔（ジッター）の導入
リクエスト間にランダムな待機時間（2〜10秒）を入れ、機械的なアクセスパターンを崩す。

### 案D: Playwright (Headless Chrome) への差し戻し + ステルスプラグイン
`curl-cffi` ではなく、実際のブラウザエンジンを動かすPlaywrightを使用し、`playwright-stealth` などのライブラリを組み合わせてJS実行まで含めた完全な模倣を行う。
