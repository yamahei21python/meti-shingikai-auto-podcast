
import sys
import os
import argparse
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import logger, setup_logging, run_notebooklm

setup_logging()

def test_download(notebook_id: str):
    logger.info(f"Testing download for Notebook ID: {notebook_id}")
    
    # 1. List artifacts to see if audio exists
    logger.info("Listing artifacts...")
    res_list = run_notebooklm(["artifact", "list", "-n", notebook_id])
    if res_list.returncode == 0:
        print("--- Artifact List ---")
        print(res_list.stdout)
    else:
        logger.error(f"Failed to list artifacts: {res_list.stderr}")

    # 2. Try to download audio
    output_mp3 = "download_practice.mp3"
    logger.info(f"Attempting to download latest audio to {output_mp3}...")
    
    # Try with --latest and --force
    res_dl = run_notebooklm(["download", "audio", output_mp3, "-n", notebook_id, "--latest", "--force"])
    
    if res_dl.returncode == 0:
        logger.info(f"SUCCESS: Audio downloaded to {output_mp3}")
        if os.path.exists(output_mp3):
            size = os.path.getsize(output_mp3)
            logger.info(f"File size: {size} bytes")
    else:
        logger.error(f"Download FAILED: {res_dl.stderr}")
        print("--- stderr output ---")
        print(res_dl.stderr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Notebook ID")
    args = parser.parse_args()
    
    test_download(args.id)
