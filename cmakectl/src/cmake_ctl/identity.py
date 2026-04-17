from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

PROJECT_ID_REL_PATH = Path(".cmake-ctl") / "project-id"


@dataclass
class ProjectIdentity:
    key: str
    project_id: str | None
    canonical_path: Path


def _canonical(path: Path) -> Path:
    return path.expanduser().resolve()


def _project_id_path(project_path: Path) -> Path:
    return project_path / PROJECT_ID_REL_PATH


def read_project_id(project_path: Path) -> str | None:
    id_path = _project_id_path(project_path)
    if not id_path.exists():
        return None
    value = id_path.read_text(encoding="utf-8").strip()
    return value or None


def ensure_project_id(project_path: Path) -> str:
    project_path = _canonical(project_path)
    id_path = _project_id_path(project_path)
    id_path.parent.mkdir(parents=True, exist_ok=True)
    project_id = read_project_id(project_path)
    if project_id:
        return project_id
    project_id = str(uuid.uuid4())
    id_path.write_text(project_id + "\n", encoding="utf-8")
    return project_id


def resolve_project_identity(project_path: Path, mode: str, create_if_missing: bool = False) -> ProjectIdentity:
    project_path = _canonical(project_path)

    if mode == "path-only":
        return ProjectIdentity(key=f"path:{project_path.as_posix()}", project_id=None, canonical_path=project_path)

    if mode != "id-file-first":
        raise ValueError(f"Unsupported identity mode: {mode}")

    project_id = ensure_project_id(project_path) if create_if_missing else read_project_id(project_path)
    if project_id:
        return ProjectIdentity(key=f"id:{project_id}", project_id=project_id, canonical_path=project_path)

    return ProjectIdentity(key=f"path:{project_path.as_posix()}", project_id=None, canonical_path=project_path)
