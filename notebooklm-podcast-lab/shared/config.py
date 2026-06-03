"""Configuration集中管理 for Energy Audio system."""

import os
from pathlib import Path
from typing import Optional


# === Project Base ===
PROJECT_ROOT = Path(__file__).parent.parent
PODCASTS_DIR = PROJECT_ROOT.parent / "podcasts"
DB_PATH = PROJECT_ROOT.parent / "councils.db"

# === METI/OCCTO URLs ===
METI_URL = "https://www.meti.go.jp/shingikai/index.html"
OCCTO_URL = "https://www.occto.or.jp/"

# === Proxy ===
SOCKS5_PROXY = os.getenv("SOCKS5_PROXY", "")

# === Database ===
MAX_CATEGORIES = 10

# === Target Categories for Podcast ===
TARGET_CATS_METI = ["エネルギー・環境", "総合資源エネルギー調査会"]

# === NotebookLM ===
NOTEBOOKLM_AUTH_JSON = os.getenv("NOTEBOOKLM_AUTH_JSON")
NOTEBOOKLM_LANGUAGE = "ja"
NOTEBOOKLM_VENV_PATH = PROJECT_ROOT / ".venv" / "bin" / "notebooklm"
NOTEBOOKLM_PYTHON_PATH = PROJECT_ROOT / ".venv" / "bin" / "python3"

# === Audio Generation ===
AUDIO_TIMEOUT_SECONDS = 5400
POLL_INTERVAL_SECONDS = 30

# === Worker ===
MAX_PROCESS_PER_RUN = 3
DAILY_GENERATION_LIMIT = 3  # NotebookLM free plan: 3 audio overviews/day

# === R2 Cloud (Cloudflare) ===
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")

# === Podcast RSS ===
PODCAST_TITLE = os.getenv("PODCAST_TITLE", "Energy Audio | METI AI Podcast")
PODCAST_DESCRIPTION = os.getenv(
    "PODCAST_DESCRIPTION",
    "経済産業省のエネルギー政策審議会をAIで読み解く、エネルギードメイン特化型ポッドキャスト",
)
PODCAST_LINK = os.getenv("PODCAST_LINK", "https://energy-audio.vercel.app/")
PODCAST_AUTHOR = os.getenv("PODCAST_AUTHOR", "Kohei")
RSS_FILENAME = os.getenv("RSS_FILENAME", "podcast.xml")
RSS_OUTPUT_PATH = PROJECT_ROOT.parent / RSS_FILENAME


def get_venv_python() -> Optional[str]:
    """Get Python path from venv if exists."""
    if NOTEBOOKLM_PYTHON_PATH.exists():
        return str(NOTEBOOKLM_PYTHON_PATH)
    return None


def is_github_actions() -> bool:
    """Check if running on GitHub Actions."""
    return os.getenv("GITHUB_ACTIONS") is not None
