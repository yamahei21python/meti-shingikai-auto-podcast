# NotebookLM keepalive (ene / Energy Audio)

GitHub Actions の Secret `NOTEBOOKLM_AUTH_JSON` が腐らないようにするための
常駐システム一式。Muse の VM 上で動く。

## なぜ必要か

Google の `__Secure-1PSIDTS` cookie はサーバー側でローテーションされ、
保存した storage_state のスナップショットは「ローテーション結果を書き戻す」
運用をしないと有効窓の外に出て失効する（2026-09-29 に実際に失効し、
Daily ワークフローが約1ヶ月止まった）。GHA は毎回スナップショットを
使い捨てるので、外部でチェーンを生かし続けて Secret を追随させる。

## 構成

| 部品 | 役割 | 間隔 |
|---|---|---|
| `refresh.sh` (systemd: nblm-refresh) | `notebooklm auth refresh` で PSIDTS ローテーションを引き出し、VM のマスターコピー `~/.notebooklm-kenta/profiles/default/storage_state.json` に保存 | 20分毎 |
| `sync_secret.py` (systemd: nblm-secret-sync) | マスターコピーの sha256 が前回同期時と変わっていれば、repo の Actions 公開鍵で暗号化して Secret `NOTEBOOKLM_AUTH_JSON` を PUT（PAT は custom.github-cli コネクタ経由） | 1時間毎 |

- マスターコピーは VM 側の1つだけ。**Mac 側コピーを refresh すると
  チェーンが枝分かれするので禁止。**
- `storage_state.json` 自体は認証情報なので **絶対にコミットしない**。
  このフォルダに入っているのはスクリプトとユニット定義だけ。

## VM 側の罠（refresh.sh で対処済み）

1. ランタイム既定の `NO_PROXY` に裸の IPv6 (`::1,[::1],fd8b:...`) が
   含まれ、httpx の URLPattern 解析が `Invalid port: ':1]'` で落ちる
   → `NO_PROXY=localhost,127.0.0.1` にサニタイズする。
2. systemd サービスにはシェルのプロキシ環境変数が渡らない
   → `HTTP(S)_PROXY=http://hatch-egress-proxy:3128` を明示する
   （VM 内からは認証なし CONNECT 可、直接 egress は不可）。

## 復旧手順（VM が入れ替わった場合）

1. このフォルダを VM に持ってきて `bash install.sh`
   （venv・systemd ユニット・タイマーを復元する）。
2. 認証の種が無い場合は Mac で再ログインが要る（人間の操作）:
   `NOTEBOOKLM_HOME=~/.notebooklm-kenta notebooklm login --browser chrome`
   で kenta.sato.muse@gmail.com でサインイン →
   `~/.notebooklm-kenta/profiles/default/storage_state.json` を
   VM の同パスへコピーし `chmod 600`。
3. `systemctl start nblm-refresh.service nblm-secret-sync.service` を
   手動で1回回し、`~/nblm-vm/refresh.log` の `exit=0 ok refreshed` と
   Secret の `updated_at` 更新を確認。
4. 仕上げに Test NotebookLM Authentication ワークフローを dispatch
   して success を確認する。

## 履歴

- 2026-10-26: 構築・検証完了。アカウントは Muse 専用の
  kenta.sato.muse@gmail.com（パスワード変更や全セッションログアウトを
  すると即死するのでしないこと）。
