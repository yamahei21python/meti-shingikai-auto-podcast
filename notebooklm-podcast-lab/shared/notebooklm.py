"""NotebookLM helper functions for Energy Audio system."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Optional

from .config import (
    AUDIO_TIMEOUT_SECONDS,
    NOTEBOOKLM_AUTH_JSON,
    NOTEBOOKLM_LANGUAGE,
    NOTEBOOKLM_VENV_PATH,
    get_venv_python,
    is_github_actions,
)
from .logging import get_logger

logger = get_logger("notebooklm")


def init_auth() -> None:
    """Initialize NotebookLM auth file if secret provided in ENV."""
    if not NOTEBOOKLM_AUTH_JSON:
        return

    home = os.path.expanduser("~")
    auth_dir = os.path.join(home, ".notebooklm")
    auth_path = os.path.join(auth_dir, "auth.json")

    if os.path.exists(auth_path):
        return

    logger.info(f"Initializing NotebookLM auth at {auth_path}")
    if not os.path.exists(auth_dir):
        os.makedirs(auth_dir)

    with open(auth_path, "w", encoding="utf-8") as f:
        f.write(NOTEBOOKLM_AUTH_JSON)
    logger.info("[+] Auth file created")

    # Set language to Japanese
    run_notebooklm(["language", "set", NOTEBOOKLM_LANGUAGE])


def run_notebooklm(
    args: list[str], capture: bool = True
) -> subprocess.CompletedProcess:
    """
    Execute notebooklm command.

    Args:
        args: Command arguments
        capture: Capture output (default: True)

    Returns:
        CompletedProcess instance
    """
    # Try venv first, fallback to uv
    venv_notebooklm = str(NOTEBOOKLM_VENV_PATH)
    python_bin = get_venv_python()

    if os.path.exists(venv_notebooklm) and python_bin:
        cmd = [python_bin, venv_notebooklm] + args
    elif shutil.which("uv"):
        cmd = ["uv", "run", "notebooklm"] + args
    else:
        cmd = ["notebooklm"] + args

    logger.debug(f"Executing: {' '.join(cmd)}")

    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


def wait_for_task(
    task_id: str,
    notebook_id: Optional[str] = None,
    timeout_seconds: int = AUDIO_TIMEOUT_SECONDS,
    poll_interval: int = 60,
) -> bool:
    """
    Wait for task completion by polling status.

    Args:
        task_id: Task ID to monitor
        notebook_id: Optional notebook identifier
        timeout_seconds: Maximum wait time
        poll_interval: Polling interval in seconds

    Returns:
        True if task succeeded, False otherwise
    """
    start_time = time.time()
    logger.info(f"Monitoring task: {task_id} (timeout: {timeout_seconds}s)")

    while time.time() - start_time < timeout_seconds:
        status_args = ["artifact", "poll", task_id]
        if notebook_id:
            status_args.extend(["-n", notebook_id])

        res = run_notebooklm(status_args)

        if res.returncode == 0:
            status_out = res.stdout.strip()
            logger.debug(f"Status: {status_out}")

            status_upper = status_out.upper()
            if (
                "STATUS='SUCCEEDED'" in status_upper
                or "STATUS='COMPLETED'" in status_upper
            ):
                logger.info("Task completed successfully")
                return True
            if "STATUS='FAILED'" in status_upper or "STATUS='ERROR'" in status_upper:
                logger.error(f"Task failed: {status_out}")
                return False

        time.sleep(poll_interval)

    logger.warning(f"Monitoring timed out after {timeout_seconds}s")
    return False


def parse_notebook_id(output: str) -> Optional[str]:
    """
    Parse notebook ID from command output.

    Args:
        output: Command stdout output

    Returns:
        Notebook ID if found, None otherwise
    """
    # UUID pattern
    match = re.search(
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        output,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    # Fallback: last token
    parts = output.strip().split()
    if parts:
        return parts[-1]

    return None


def parse_task_id(output: str) -> Optional[str]:
    """
    Parse task ID from generate command output.

    Args:
        output: Command stdout output

    Returns:
        Task ID if found, None otherwise
    """
    match = re.search(
        r"(?:Task: )?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        output,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


# Backwards compatibility aliases
def get_pending_items(*args, **kwargs):
    """Deprecated: Use db.get_pending_items() instead."""
    from .db import get_pending_items as _get_pending

    return _get_pending(*args, **kwargs)


def update_status(*args, **kwargs):
    """Deprecated: Use db.update_status() instead."""
    from .db import update_status as _update

    return _update(*args, **kwargs)
