from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import CONFIG_PATH, ensure_layout


DEFAULT_IDENTITY_MODE = "id-file-first"


@dataclass
class Config:
    global_version: str | None = None
    identity_mode: str = DEFAULT_IDENTITY_MODE
    project_versions: dict[str, str] = field(default_factory=dict)
    project_paths: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        return cls(
            global_version=data.get("global_version"),
            identity_mode=data.get("identity_mode", DEFAULT_IDENTITY_MODE),
            project_versions=dict(data.get("project_versions", {})),
            project_paths=dict(data.get("project_paths", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_version": self.global_version,
            "identity_mode": self.identity_mode,
            "project_versions": self.project_versions,
            "project_paths": self.project_paths,
        }


def load_config() -> Config:
    ensure_layout()
    if not CONFIG_PATH.exists():
        return Config()
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return Config.from_dict(json.load(f))


def save_config(config: Config) -> None:
    ensure_layout()
    tmp_path = Path(str(CONFIG_PATH) + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, sort_keys=True)
    tmp_path.replace(CONFIG_PATH)
