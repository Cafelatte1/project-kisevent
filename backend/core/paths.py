"""앱 데이터·로그·DB 경로. OS별 기본값과 환경변수 오버라이드."""

import os
from pathlib import Path

import platformdirs

APP_NAME = "kisevent"

# Windows %LOCALAPPDATA%\kisevent, macOS ~/Library/Application Support/kisevent
APP_DIR = Path(
    os.environ.get("KISEVENT_APP_DIR") or platformdirs.user_data_dir(APP_NAME, appauthor=False)
)
LOG_DIR = Path(os.environ.get("KISEVENT_LOG_DIR") or APP_DIR / "logs")
DATA_DIR = Path(
    os.environ.get("KISEVENT_DATA_DIR") or Path(__file__).resolve().parents[2] / "data"
)
DB_PATH = DATA_DIR / "events.db"
IMAGE_DIR = DATA_DIR / "images"


def ensure_dirs() -> None:
    for directory in (LOG_DIR, DATA_DIR, IMAGE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
