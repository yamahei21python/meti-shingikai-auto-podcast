#!/bin/bash

# --- METI Podcast Sync Helper ---
# このスクリプトは、お手元で審議会情報をスキャンし、GitHub Actionsへ連携するためのものです。

set -e

echo "[*] Starting METI Shingikai Scraper..."
# スクレイピングの実行 (uv がインストールされている前提)
uv run python3 scrape_meti_shingikai.py

# DBの更新があるか確認
if git status --porcelain meti_shingikai.db | grep -q 'M'; then
    echo "[+] Database updated. Syncing with GitHub..."
    git add meti_shingikai.db
    git commit -m "Update METI Council status (Local scan: $(date '+%Y-%m-%d %H:%M:%S'))"
    git push
    echo ""
    echo "[🎉 SUCCESS] Sync complete!"
    echo "GitHub Actions will start the Podcast generation shortly."
    echo "Check progress at: https://github.com/yamahei21python/meti-shingikai-auto-podcast/actions"
else
    echo "[*] No new pending items found. Everything is up to date."
fi
