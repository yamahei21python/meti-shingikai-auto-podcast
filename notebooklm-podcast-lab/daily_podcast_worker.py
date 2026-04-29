"""
Daily Podcast Worker - Process pending items and generate podcasts.

Usage:
    python daily_podcast_worker.py
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

# Add parent to path
sys.path.insert(0, ".")

from shared import (
    PODCASTS_DIR,
    MAX_PROCESS_PER_RUN,
    DAILY_GENERATION_LIMIT,
    AUDIO_TIMEOUT_SECONDS,
    POLL_INTERVAL_SECONDS,
    init_auth,
    get_pending_items,
    update_status,
    run_notebooklm,
    wait_for_task,
    sanitize_filename,
    format_date_yyyymmdd,
    get_remaining_quota,
    increment_daily_quota,
    logger,
    setup_logging,
)

setup_logging()


def generate_summary_report(notebook_id: str, target_path: str) -> bool:
    """
    Generate and download detailed summary report.

    Mirrors generate_audio() from generate_podcast_from_article.py:
    - 3 retry attempts on start with quota/rate-limit detection
    - AUDIO_TIMEOUT_SECONDS wait (same as MP3)
    - POLL_INTERVAL_SECONDS polling (same as MP3)
    - 60s metadata propagation wait (same as MP3)

    Args:
        notebook_id: Notebook identifier
        target_path: Output path for summary

    Returns:
        True if successful
    """
    logger.info(f"Generating summary report for: {notebook_id}")
    prompt = """
あなたは日本のエネルギー政策に詳しい専門アナリストです。以下の資料を分析し、エネルギー業界関係者向けの「カスタムレポート」を作成してください。

【絶対的な出力形式】
冒頭の # から始まる以下の4セクション構成のみ。表紙・前置き・「Answer:」等は一切不要。余計なセクション(キーワード解説・注釈・区切り線等)は追加禁止。

# カスタムレポート

### 1. ポッドキャスト解説ガイド（内容のポイント）
1段落の導入文で始め、その後以下の箇条書きで3〜5ポイントを列挙:
* **太字の見出し**
    解説文（複数行可）。見出しと同じ行に書かない。
* **太字の見出し**
    解説文...

### 2. 主要な議題
* **論点の名称**
    解説文...
* **論点の名称**
    解説文...

### 3. 決定事項
1.  **決定事項の名称**
     解説文...
2.  **決定事項の名称**
     解説文...

### 4. 今後のタイムライン
1.  **スケジュール項目**
     解説文...
2.  **スケジュール項目**
     解説文...

【フォーマット厳守事項】
- 箇条書きは `* **太字見出し**` のみ使用。ハイフン(`-`)やコロン(`:`)は使わない。
- 見出しと本文は別行。同一行に書かない。
- 各セクション最低3ポイント記述。
- キーワード解説・専門用語集・区切り線(`---`)は追加しない。
    """.strip()

    normalized_prompt = " ".join(prompt.split())

    # === Generate report (with retry, mirrors generate_audio pattern) ===
    task_id = None
    max_start_attempts = 3
    for attempt in range(max_start_attempts):
        logger.info(f"Starting report generation (Attempt {attempt + 1}/{max_start_attempts})...")
        gen_res = run_notebooklm(
            [
                "generate",
                "report",
                normalized_prompt,
                "-n",
                notebook_id,
                "--language",
                "ja",
                "--json",
            ]
        )

        if gen_res.returncode == 0:
            try:
                gen_data = json.loads(gen_res.stdout)
                task_id = gen_data.get("task_id")
            except Exception as e:
                logger.error(f"Failed to parse report task ID: {e}")

            if task_id:
                logger.info(f"Report generation started. Task ID: {task_id}")
                break

        # Smart error detection for rate limits and quotas (mirrors generate_audio)
        error_msg = gen_res.stderr or gen_res.stdout or "unknown"
        error_lower = error_msg.lower()
        is_quota_error = (
            "rate limited" in error_lower
            or "quota" in error_lower
            or "create_artifact failed" in error_lower
            or ("rpc" in error_lower and "failed" in error_lower)
        )
        if is_quota_error:
            logger.error(f"CRITICAL: NotebookLM quota/API error detected: {error_msg.strip()}")
            logger.error("Aborting retries to protect account safety.")
            return False

        logger.warning(
            f"Report generation start failed (Attempt {attempt + 1}): {error_msg.strip()}"
        )
        if attempt < max_start_attempts - 1:
            time.sleep(30)

    if not task_id:
        logger.error("Failed to start report generation after all attempts")
        return False

    # === Wait for completion (mirrors audio: AUDIO_TIMEOUT_SECONDS, POLL_INTERVAL_SECONDS) ===
    logger.info(
        f"Waiting for completion (timeout: {AUDIO_TIMEOUT_SECONDS}s, poll: {POLL_INTERVAL_SECONDS}s)..."
    )
    success = wait_for_task(
        task_id,
        notebook_id=notebook_id,
        timeout_seconds=AUDIO_TIMEOUT_SECONDS,
        poll_interval=POLL_INTERVAL_SECONDS,
    )

    if not success:
        logger.warning(
            "Report generation polling timed out. "
            "Proceeding to download attempt with retry logic..."
        )
    else:
        logger.info("Report generation completed successfully")

    # Wait for metadata/URL propagation before download
    logger.info("Waiting 60s for metadata/URL propagation...")
    time.sleep(60)

    # === Download with retry logic ===
    max_report_retries = 5
    for attempt in range(1, max_report_retries + 1):
        logger.info(f"Report download attempt {attempt}/{max_report_retries}...")
        dl_res = run_notebooklm(
            ["download", "report", target_path, "-n", notebook_id, "--latest", "--force"]
        )

        if dl_res.returncode == 0:
            if os.path.exists(target_path):
                file_size = os.path.getsize(target_path)
                if file_size > 512:
                    logger.info(f"SUCCESS: Report downloaded. Size: {file_size} bytes")
                    logger.info(f"Summary saved to: {target_path}")
                    return True
                else:
                    logger.error(
                        f"Report download failed: File size too small ({file_size} bytes)"
                    )
            else:
                logger.error("Report download reported success but file not found")
        else:
            logger.error(f"Report download failed: {dl_res.stderr}")

        if attempt < max_report_retries:
            wait_time = 30 * attempt
            logger.info(f"Waiting {wait_time}s before next attempt...")
            time.sleep(wait_time)

    logger.error(f"All {max_report_retries} report download attempts failed")
    return False


def process_single_item(item: tuple) -> bool:
    """
    Process a single pending item.

    Args:
        item: Database row (id, title, url, date, pdf_urls)

    Returns:
        True if both MP3 and MD succeeded
    """
    item_id, title, url, date_str, pdf_urls_json = item
    logger.info(f"Processing: {title} ({date_str})")

    try:
        # Prepare filenames
        formatted_date = format_date_yyyymmdd(date_str)
        sanitized_title = sanitize_filename(title)
        notebook_name = f"{formatted_date}_{sanitized_title}"
        # Use item_id in temp names to avoid collisions if multiple articles on same day
        output_temp = f"temp_{formatted_date}_{item_id}.mp3"
        md_temp = f"temp_{formatted_date}_{item_id}_summary.md"

        # === Step 1: Generate Podcast MP3 ===
        python_bin = sys.executable
        cmd = [
            python_bin,
            "generate_podcast_from_article.py",
            "--url",
            url,
            "--output",
            output_temp,
            "--name",
            notebook_name,
        ]
        if pdf_urls_json:
            cmd.extend(["--pdfs", pdf_urls_json])

        logger.info(f"Executing: {' '.join(cmd)}")
        mp3_res = subprocess.run(cmd, capture_output=True, text=True)
        if mp3_res.stdout:
            print(mp3_res.stdout)
        if mp3_res.returncode != 0:
            print(f"ERROR: {mp3_res.stderr}")

        mp3_success = False
        notebook_identifier = notebook_name

        if mp3_res.returncode == 0 and os.path.exists(output_temp):
            mp3_success = True
            # Capture real notebook ID from output
            for line in mp3_res.stdout.splitlines():
                if line.startswith("NOTEBOOK_ID="):
                    notebook_identifier = line.split("=", 1)[1].strip()
                    break

        # === Step 2: Generate Summary MD (Only if MP3 succeeded) ===
        md_success = False
        if mp3_success:
            md_success = generate_summary_report(
                notebook_id=notebook_identifier, target_path=md_temp
            )

        # === Step 3: Finalize or Rollback ===
        final_dir = str(PODCASTS_DIR)
        if not os.path.exists(final_dir):
            os.makedirs(final_dir)

        final_mp3_path = os.path.join(final_dir, f"{formatted_date}_{sanitized_title}.mp3")
        final_mp3_name = f"{formatted_date}_{sanitized_title}.mp3"
        final_md_path = os.path.join(
            final_dir, f"{formatted_date}_{sanitized_title}_summary.md"
        )

        if mp3_success and md_success:
            # Atomic move using shutil (safer for cross-filesystem moves)
            if os.path.exists(final_mp3_path):
                os.remove(final_mp3_path)
            shutil.move(output_temp, final_mp3_path)

            if os.path.exists(final_md_path):
                os.remove(final_md_path)
            shutil.move(md_temp, final_md_path)

            # Save metadata JSON
            meta_path = final_mp3_path.rsplit(".", 1)[0] + ".json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"original_url": url, "title": title}, f, ensure_ascii=False, indent=2
                )

            logger.info("COMPLETE: Both MP3 and MD saved with metadata")
            update_status(item_id, "done", r2_filename=final_mp3_name)
            increment_daily_quota()

            # Output for workflow
            print(f"PODCAST_ASSET_PATH={final_mp3_path}")
            print(f"ORIGINAL_URL={url}")

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        md_success = False

    # === Cleanup Notebook (always run) ===
    logger.info(f"Cleaning up Notebook: {notebook_identifier}")
    run_notebooklm(["delete", "-n", notebook_identifier, "-y"])

    if mp3_success and md_success:
        return True
    else:
        # Failed: Cleanup temp files
        logger.warning(f"FAILED: mp3={mp3_success}, md={md_success}")
        if os.path.exists(output_temp):
            os.remove(output_temp)
        if os.path.exists(md_temp):
            os.remove(md_temp)
        return False


def main():
    """Main worker entry point."""
    print(
        f"=== Daily Podcast Worker Start (Limit: {MAX_PROCESS_PER_RUN}): {datetime.now()} ==="
    )

    # Change to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Initialize auth
    init_auth()

    # Check daily quota before doing anything
    remaining = get_remaining_quota(DAILY_GENERATION_LIMIT)
    if remaining <= 0:
        logger.warning(
            f"Daily generation quota exhausted ({DAILY_GENERATION_LIMIT}/{DAILY_GENERATION_LIMIT}). Skipping all items."
        )
        print("\n=== Worker Finished. Processed: 0 items (quota exhausted) ===")
        return
    logger.info(f"Daily quota remaining: {remaining}/{DAILY_GENERATION_LIMIT}")

    # Get pending items (capped by remaining quota)
    effective_limit = min(MAX_PROCESS_PER_RUN, remaining)
    items = get_pending_items(limit=effective_limit)

    if not items:
        logger.info("No pending items in queue")
        return

    # Process items
    processed_count = 0
    for i, item in enumerate(items):
        # Re-check quota before each item (another worker might have consumed it)
        remaining = get_remaining_quota(DAILY_GENERATION_LIMIT)
        if remaining <= 0:
            logger.warning("Daily quota exhausted mid-run. Skipping remaining items.")
            break

        # Wait between items to avoid WAF rate limiting (METI blocks rapid sequential access)
        if i > 0:
            wait_sec = 120
            logger.info(f"Waiting {wait_sec}s between items (WAF mitigation)...")
            time.sleep(wait_sec)

        if process_single_item(item):
            processed_count += 1

    print(f"\n=== Worker Finished. Processed: {processed_count} items ===")


if __name__ == "__main__":
    main()
