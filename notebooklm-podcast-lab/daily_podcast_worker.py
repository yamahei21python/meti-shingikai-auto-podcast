"""
Daily Podcast Worker - Process pending items and generate podcasts.

Usage:
    python daily_podcast_worker.py
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime

# Add parent to path
sys.path.insert(0, ".")

from shared import (
    PODCASTS_DIR,
    MAX_PROCESS_PER_RUN,
    init_auth,
    get_pending_items,
    update_status,
    run_notebooklm,
    wait_for_task,
    sanitize_filename,
    format_date_yyyymmdd,
    logger,
)


def generate_summary_report(notebook_id: str, target_path: str) -> bool:
    """
    Generate and download detailed summary report.

    Args:
        notebook_id: Notebook identifier
        target_path: Output path for summary

    Returns:
        True if successful
    """
    logger.info(f"Generating summary report for: {notebook_id}")
    prompt = """
資料の内容を徹底的に分析し、日本のエネルギー業界関係者が実務で活用できる詳細な「カスタムレポート」を日本語で作成してください。
構成は必ず以下の4つのセクションとし、各セクションで少なくとも3〜5つの核心的なポイントを詳細に記述してください。

# [資料タイトル] カスタムレポート

### 1. ポッドキャスト解説ガイド（内容のポイント）
- 議論の背景、技術的・政策的意義、現場への影響などを解説

### 2. 主要な議題
- 焦点となった論点、対立軸、新しい枠組み

### 3. 決定事項
- 合意に至った内容、承認された方針、策定された基準

### 4. 今後のタイムライン
- 制度の施行時期、パブリックコメントの予定

「Answer:」などの前置きは一切含めず、冒頭の # 見出しから始まるマークダウンのみを出力してください。
    """.strip()

    normalized_prompt = " ".join(prompt.split())

    # Generate report (JSON mode to get task_id)
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

    if gen_res.returncode != 0:
        logger.error(f"Report generation start failed: {gen_res.stderr}")
        return False

    try:
        gen_data = json.loads(gen_res.stdout)
        task_id = gen_data.get("task_id")
    except Exception as e:
        logger.error(f"Failed to parse report task ID: {e}")
        return False

    if not task_id:
        logger.error(f"No task_id in JSON: {gen_res.stdout}")
        return False

    # Wait for completion
    success = wait_for_task(task_id, notebook_identifier=notebook_id)

    if not success:
        logger.warning("Report generation failed. Waiting 300s buffer...")
        time.sleep(300)

    # Download
    dl_res = run_notebooklm(
        ["download", "report", target_path, "-n", notebook_id, "--latest", "--force"]
    )

    if dl_res.returncode == 0:
        logger.info(f"Summary saved to: {target_path}")
        return True

    logger.error(f"Report download failed: {dl_res.stderr}")
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

    # Prepare filenames
    formatted_date = format_date_yyyymmdd(date_str)
    sanitized_title = sanitize_filename(title)
    notebook_name = f"{formatted_date}_{sanitized_title}"
    output_temp = f"temp_{formatted_date}.mp3"
    md_temp = f"temp_{formatted_date}_summary.md"

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
    final_md_path = os.path.join(
        final_dir, f"{formatted_date}_{sanitized_title}_summary.md"
    )

    if mp3_success and md_success:
        # Atomic move
        if os.path.exists(final_mp3_path):
            os.remove(final_mp3_path)
        os.rename(output_temp, final_mp3_path)

        if os.path.exists(final_md_path):
            os.remove(final_md_path)
        os.rename(md_temp, final_md_path)

        # Save metadata JSON
        meta_path = final_mp3_path.rsplit(".", 1)[0] + ".json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {"original_url": url, "title": title}, f, ensure_ascii=False, indent=2
            )

        logger.info("COMPLETE: Both MP3 and MD saved with metadata")
        update_status(item_id, "done")

        # Output for workflow
        print(f"PODCAST_ASSET_PATH={final_mp3_path}")
        print(f"ORIGINAL_URL={url}")

        return True
    else:
        # Failed: Cleanup temp files
        logger.warning(f"FAILED: mp3={mp3_success}, md={md_success}")
        if os.path.exists(output_temp):
            os.remove(output_temp)
        if os.path.exists(md_temp):
            os.remove(md_temp)
        return False

    # === Step 4: Cleanup Notebook ===
    logger.info(f"Cleaning up Notebook: {notebook_identifier}")
    run_notebooklm(["delete", "-n", notebook_identifier, "-y"])


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

    # Get pending items
    items = get_pending_items(limit=MAX_PROCESS_PER_RUN)

    if not items:
        logger.info("No pending items in queue")
        return

    # Process items
    processed_count = 0
    for item in items:
        if process_single_item(item):
            processed_count += 1

    print(f"\n=== Worker Finished. Processed: {processed_count} items ===")


if __name__ == "__main__":
    main()
