from __future__ import annotations

from pathlib import Path

from .database import ProjectRecord, upsert_project
from .events import Event


def process_event(event: Event) -> None:
    if event.event_type != "cmake_invocation":
        return
    payload = event.payload
    project_path = str(payload.get("project_path", ""))
    resolved_version = str(payload.get("resolved_version", ""))
    generator = payload.get("generator")
    key = str(payload.get("project_key", f"path:{Path(project_path).as_posix()}"))

    upsert_project(
        ProjectRecord(
            project_key=key,
            path=project_path,
            cmake_version=resolved_version,
            generator=str(generator) if generator else None,
        )
    )
