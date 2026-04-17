from __future__ import annotations

import os
from pathlib import Path


def _default_home() -> Path:
    env_home = os.environ.get("CMAKE_CTL_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    return (Path.home() / ".cmake-ctl").resolve()


HOME_DIR = _default_home()
CONFIG_PATH = HOME_DIR / "config.json"
SESSIONS_PATH = HOME_DIR / "sessions.json"
VERSIONS_DIR = HOME_DIR / "versions"
EVENTS_LOG_PATH = HOME_DIR / "events.log"
EVENTS_DEAD_LETTER_PATH = HOME_DIR / "events.deadletter.log"
PROJECTS_DB_PATH = HOME_DIR / "projects.db"
PROCESSED_EVENTS_PATH = HOME_DIR / "processed-events.txt"
DOWNLOADS_DIR = HOME_DIR / "downloads"


def ensure_layout() -> None:
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
