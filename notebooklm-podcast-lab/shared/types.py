"""Shared type definitions for Energy Audio system."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CouncilUpdate:
    """経産省・OCCTO更新情報のデータクラス."""

    date: str
    title: str
    url: str
    categories: list[str]
    podcast_status: str = "pending"
    pdf_urls: Optional[str] = None
    podcast_date: Optional[str] = None
    id: Optional[int] = None


@dataclass
class PodcastItem:
    """ポッドキャストアイテムのデータクラス."""

    title: str
    description: Optional[str]
    url: str
    original_link: Optional[str]
    size: int
    mtime: float


@dataclass
class TaskStatus:
    """NotebookLMタスクの状態."""

    task_id: str
    notebook_id: Optional[str]
    status: str  # RUNNING, SUCCEEDED, FAILED
    progress: Optional[int] = None


@dataclass
class NotebookLMConfig:
    """NotebookLMの設定."""

    auth_json_path: str
    language: str = "ja"
    venv_bin_path: Optional[str] = None
    python_bin: Optional[str] = None
