from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import SESSIONS_PATH, ensure_layout


@dataclass
class SessionStore:
    data: dict[str, dict[str, str]]

    @classmethod
    def load(cls) -> "SessionStore":
        ensure_layout()
        if not SESSIONS_PATH.exists():
            return cls(data={})
        with SESSIONS_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return cls(data={})
        cleaned: dict[str, dict[str, str]] = {}
        for session_id, overrides in raw.items():
            if isinstance(session_id, str) and isinstance(overrides, dict):
                cleaned[session_id] = {str(k): str(v) for k, v in overrides.items()}
        return cls(data=cleaned)

    def save(self) -> None:
        ensure_layout()
        tmp = Path(str(SESSIONS_PATH) + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, sort_keys=True)
        tmp.replace(SESSIONS_PATH)

    def set_override(self, session_id: str, project_key: str, version: str) -> None:
        self.data.setdefault(session_id, {})[project_key] = version

    def get_override(self, session_id: str, project_key: str) -> str | None:
        return self.data.get(session_id, {}).get(project_key)


def current_session_id() -> str:
    # Allow explicit opt-in deterministic session grouping per shell.
    env_session = os.environ.get("CMAKE_CTL_SESSION_ID") or os.environ.get("CMAKE_CTL_SESSION_ID")
    if env_session:
        return env_session
    return f"pid:{os.getppid()}"
