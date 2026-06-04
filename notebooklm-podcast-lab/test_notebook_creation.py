"""
Test NotebookLM Authentication and Notebook Creation.
This script is used in diagnostic workflows to verify that credentials are valid.
"""

import sys
import os
from pathlib import Path

# Add script directory to path to import shared module
script_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(script_dir))

from shared import run_notebooklm, parse_notebook_id, logger, setup_logging, init_auth

setup_logging()

def test_notebook_creation():
    logger.info("Initializing authentication...")
    init_auth()

    test_name = "Workflow_Auth_Test_Temp"
    logger.info(f"Testing notebook creation: {test_name}")
    
    res = run_notebooklm(["create", test_name])
    if res.returncode != 0:
        logger.error(f"Failed to create notebook. Return code: {res.returncode}")
        logger.error(f"Stdout: {res.stdout.strip() if res.stdout else ''}")
        logger.error(f"Stderr: {res.stderr.strip() if res.stderr else ''}")
        sys.exit(1)
        
    notebook_id = parse_notebook_id(res.stdout)
    if not notebook_id or len(notebook_id) < 10:
        logger.error(f"Failed to parse notebook ID from output: {res.stdout}")
        sys.exit(1)
        
    logger.info(f"Successfully created notebook: {notebook_id}. Cleaning up...")
    
    # Delete the created notebook
    res_del = run_notebooklm(["delete", "-n", notebook_id, "-y"])
    if res_del.returncode != 0:
        logger.warning(f"Failed to delete test notebook {notebook_id}: {res_del.stderr.strip() if res_del.stderr else ''}")
    else:
        logger.info(f"Successfully cleaned up test notebook: {notebook_id}")
        
    logger.info("Authentication test passed successfully!")

if __name__ == "__main__":
    test_notebook_creation()
