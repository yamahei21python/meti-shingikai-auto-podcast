
import sys
import os
import time
import argparse
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import (
    logger, 
    setup_logging, 
    run_notebooklm, 
    parse_task_id, 
    wait_for_task,
    AUDIO_TIMEOUT_SECONDS
)

setup_logging()

def run_phase_3(notebook_id: str):
    logger.info(f"=== Phase 3: Audio Generation & Download ===")
    logger.info(f"Using Notebook ID: {notebook_id}")

    # 1. Start Audio Generation
    prompt = """
    資料の内容の解析、および解説・対話はすべて日本語で行ってください。
    日本のエネルギー業界関係者向けのポッドキャスト音声を作成してください。
    """.strip()
    
    # Prompt normalization
    normalized_prompt = " ".join(prompt.split())

    logger.info("Step 1: Starting audio generation...")
    # Using --no-wait to handle polling manually for better visibility
    res_gen = run_notebooklm(["generate", "audio", normalized_prompt, "-n", notebook_id, "--language", "ja", "--no-wait"])
    
    if res_gen.returncode != 0:
        logger.error(f"Failed to start generation: {res_gen.stderr}")
        return

    task_id = parse_task_id(res_gen.stdout)
    if not task_id:
        logger.error(f"Could not parse task ID. Output was: {res_gen.stdout}")
        return
    
    logger.info(f"Audio generation task started. Task ID: {task_id}")

    # 2. Wait for completion with polling
    logger.info("Step 2: Polling for completion...")
    # wait_for_task already has polling logic. 
    # We'll use it but with a slightly shorter poll interval for testing.
    success = wait_for_task(task_id, notebook_id=notebook_id, poll_interval=30)
    
    if not success:
        logger.error("Audio generation failed or timed out.")
        return

    # 3. Post-success buffer
    # Sometimes the API reports success but the file isn't immediately downloadable.
    logger.info("Step 3: Waiting 30s buffer for file availability...")
    time.sleep(30)

    # 4. Verify artifact presence
    logger.info("Step 4: Verifying artifact list...")
    res_list = run_notebooklm(["artifact", "list", "-n", notebook_id])
    print("--- Current Artifacts ---")
    print(res_list.stdout)
    print("-------------------------")

    if "Audio" not in res_list.stdout:
        logger.warning("Audio artifact not found in list despite task success. Retrying list in 30s...")
        time.sleep(30)
        res_list = run_notebooklm(["artifact", "list", "-n", notebook_id])
        print(res_list.stdout)

    # 5. Download Audio
    output_path = f"test_result_{notebook_id[:8]}.mp3"
    logger.info(f"Step 5: Downloading latest audio to {output_path}...")
    
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        # Use --latest and --force to be sure
        res_dl = run_notebooklm(["download", "audio", output_path, "-n", notebook_id, "--latest", "--force"])
        
        if res_dl.returncode == 0:
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                if file_size > 1024: # Expecting more than 1KB
                    logger.info(f"SUCCESS: Audio downloaded on attempt {attempt}. Size: {file_size} bytes.")
                    logger.info(f"File path: {os.path.abspath(output_path)}")
                    return
                else:
                    logger.error(f"Download FAILED (Attempt {attempt}): File exists but size is suspicious ({file_size} bytes).")
            else:
                logger.error(f"Download FAILED (Attempt {attempt}): Command reported success but file not found.")
        else:
            logger.error(f"Download FAILED (Attempt {attempt}): {res_dl.stderr}")
        
        if attempt < max_retries:
            wait_time = 30 * attempt # Linear backoff: 30, 60, 90, 120s
            logger.info(f"Waiting {wait_time}s before next download attempt...")
            time.sleep(wait_time)
        else:
            logger.error("All download attempts failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Notebook ID to process")
    args = parser.parse_args()
    
    run_phase_3(args.id)
