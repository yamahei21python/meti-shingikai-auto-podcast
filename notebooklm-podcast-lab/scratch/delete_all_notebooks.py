
import sys
import json
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import run_notebooklm, logger, setup_logging

setup_logging()

def delete_all_notebooks():
    logger.info("Listing all notebooks for deletion...")
    res = run_notebooklm(["list", "--json"])
    if res.returncode != 0:
        logger.error("Failed to list notebooks")
        return
    
    try:
        data = json.loads(res.stdout)
        notebooks = data.get("notebooks", [])
        ids = [nb.get("id") for nb in notebooks if nb.get("id")]
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        return
    
    if not ids:
        logger.info("No notebooks found to delete.")
        return
    
    logger.info(f"Found {len(ids)} notebooks. Deleting...")
    for nb_id in ids:
        logger.info(f"Deleting notebook: {nb_id}")
        # Use -y to bypass confirmation
        res_del = run_notebooklm(["delete", "-n", nb_id, "-y"])
        if res_del.returncode == 0:
            logger.info(f"Successfully deleted {nb_id}")
        else:
            logger.error(f"Failed to delete {nb_id}: {res_del.stderr}")

if __name__ == "__main__":
    delete_all_notebooks()
