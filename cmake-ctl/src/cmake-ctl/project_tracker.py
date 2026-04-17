from __future__ import annotations

from pathlib import Path

from .database import ProjectRecord, upsert_project
from .events import Event


def _is_configure_like(argv: list[str]) -> bool:
    # Track configure/generate style invocations that define project context.
    if not argv:
        return True
    # Explicit non-configure modes.
    if "--build" in argv or "--install" in argv or "--open" in argv:
        return False
    # Explicit configure flags.
    if ("-S" in argv) or ("-B" in argv) or ("--preset" in argv):
        return True
    # Positional source/build path: cmake . or cmake /path/to/src
    positional = [a for a in argv if not a.startswith("-")]
    return len(positional) > 0


def _resolve_project_path(payload: dict) -> Path:
    raw_project = str(payload.get("project_path", "")).strip()
    raw_source = str(payload.get("source_dir", "")).strip()
    raw_cwd = str(payload.get("cwd", "")).strip()

    basis = raw_project or raw_source or raw_cwd or "."
    p = Path(basis)
    if p.is_absolute():
        return p.resolve()

    base = Path(raw_cwd).resolve() if raw_cwd else Path.cwd().resolve()
    return (base / p).resolve()


def process_event(event: Event) -> None:
    if event.event_type != "cmake_invocation":
        return

    payload = event.payload
    argv = payload.get("argv")
    argv_list = [str(a) for a in argv] if isinstance(argv, list) else []
    if not _is_configure_like(argv_list):
        return

    project_path = _resolve_project_path(payload)
    resolved_version = str(payload.get("resolved_version", "")).strip() or "unknown"
    generator = payload.get("generator")
    key = str(payload.get("project_key") or f"path:{project_path.as_posix()}")

    upsert_project(
        ProjectRecord(
            project_key=key,
            path=project_path.as_posix(),
            cmake_version=resolved_version,
            generator=str(generator) if generator else None,
        )
    )
