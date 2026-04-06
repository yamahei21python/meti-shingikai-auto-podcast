# Energy Intelligence Podcast Pipeline 🎙️

経済産業省 (METI) および電力広域的運営推進機関 (OCCTO) の最新会議資料を AI が読み解き、プロフェッショナル向けポッドキャストとして毎日自動配信するシステムです。

## 🚀 主な特徴

- **完全自動同期**: 毎日 09:00 (JST) に最新の審議会資料を自動スキャンしてデータベースを更新。
- **NotebookLM 連携**: Google の NotebookLM を活用し、高度な文脈解析に基づいたポッドキャスト音声と要約を作成。
- **1日最大2件の配信**: リソースと配信頻度を最適化するため、1日あたりの新規生成を2件に制限。
- **ハイブリッド・ストレージ**:
  - **Cloudflare R2**: 音声ファイルを高速・低コストで配信。
  - **GitHub**: 会議データベース、サマリー、ポッドキャストフィード (RSS) を管理。
- **自動クリーンアップ**: 生成完了後、NotebookLM 上の Notebook を即座に削除してリソースを最適化。

## 🏗️ システムアーキテクチャ

1.  **データ取得**: GitHub Actions が Cloudflare WARP 経由で METI/OCCTO をスクレイピング。
2.  **インテリジェンス生成**: NotebookLM が審議会資料 (PDF) から Deep Dive 音声を生成。
3.  **配信準備**:
    - 音声 (.mp3) を Cloudflare R2 へアップロード。
    - サマリー (.md) と RSS (podcast.xml) を GitHub へコミット。
4.  **配信**: 各種ポッドキャストアプリが `podcast.xml` を通じて最新情報を取得。

## 📂 ディレクトリ構造

- `.github/workflows/`: 自動更新スケジュールを定義したワークフローファイル。
- `notebooklm-podcast-lab/`: 
  - `daily_podcast_worker.py`: ポッドキャスト生成のメインロジック（2件制限・自動削除機能）。
  - `upload_and_rss.py`: R2 アップロードと RSS ファイルの自動更新。
- `podcasts/`: 会議内容の要約 (Markdown) を保存。
- `councils.db`: 会議情報と、ポッドキャスト生成済みかどうかのステータスを管理。
- `podcast.xml`: ポッドキャスト配信用 RSS フィード。

## ⚙️ セットアップ (GitHub Secrets)

リポジトリを正常に動作させるには、以下の Secrets を GitHub のリポジトリ設定に登録する必要があります。

- `NOTEBOOKLM_AUTH_JSON`: NotebookLM の認証用 JSON データ。
- `R2_ACCESS_KEY_ID`: Cloudflare R2 のアクセスキー。
- `R2_SECRET_ACCESS_KEY`: Cloudflare R2 のシークレットキー。
- `R2_ENDPOINT`: R2 の S3 互換エンドポイント URL。
- `R2_BUCKET_NAME`: 保存先のバケット名。
- `R2_PUBLIC_URL`: 公開配信用のカスタムドメインまたは R2 URL。

## 📅 運用スケジュール

- **毎日 00:00 (UTC) / 09:00 (JST)**: GitHub Actions が自動起動。
- 会議資料の同期と、未処理の会議（最大2件）に対するポッドキャスト化が自動的に実行されます。

## 📄 ライセンス
このプロジェクトのコードは、個人的な情報収集の自動化を目的としています。情報の正確性については、常に公式サイトの一次資料を優先してください。
