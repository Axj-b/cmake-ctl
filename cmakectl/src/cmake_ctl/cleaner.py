from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SAFE_DIR_NAMES = {"bin", "obj", "packages", "build", "CMakeFiles"}


@dataclass
class CleanupPlan:
    targets: list[Path]
    bytes_reclaimable: int


def discover_cleanup_targets(project_root: Path, build_dir: Path | None = None) -> list[Path]:
    root = project_root.expanduser().resolve()
    candidates: list[Path] = []

    if build_dir is not None:
        bd = build_dir.expanduser().resolve()
        if _is_within_root(bd, root):
            candidates.append(bd)

    for name in SAFE_DIR_NAMES:
        p = root / name
        if p.exists() and p.is_dir():
            candidates.append(p)

    seen = set()
    unique: list[Path] = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        unique.append(c)
    return unique


def plan_cleanup(project_root: Path, build_dir: Path | None = None) -> CleanupPlan:
    targets = discover_cleanup_targets(project_root, build_dir)
    total = sum(_path_size(t) for t in targets)
    return CleanupPlan(targets=targets, bytes_reclaimable=total)


def execute_cleanup(
    plan: CleanupPlan,
    project_root: Path,
    pinned: bool = False,
    dry_run: bool = True,
    archive_dir: Path | None = None,
) -> dict:
    root = project_root.expanduser().resolve()
    if pinned:
        return {"deleted": 0, "bytes": 0, "skipped_pinned": True}

    deleted = 0
    deleted_bytes = 0
    manifest_entries: list[dict] = []

    for target in plan.targets:
        resolved = target.expanduser().resolve()
        if not _is_within_root(resolved, root):
            raise ValueError(f"Unsafe cleanup target outside project root: {resolved}")

        size = _path_size(resolved)
        manifest_entries.append({"path": resolved.as_posix(), "bytes": size})
        deleted_bytes += size

    if not dry_run and archive_dir is not None:
        _write_archive_manifest(archive_dir, root, manifest_entries)

    for target in plan.targets:
        if not dry_run:
            _delete_path(target.expanduser().resolve())
            deleted += 1

    return {
        "deleted": deleted if not dry_run else 0,
        "bytes": deleted_bytes,
        "skipped_pinned": False,
        "archived": bool(archive_dir is not None and not dry_run),
    }


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _delete_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_file():
        path.unlink()
        return
    for child in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            child.rmdir()
    path.rmdir()


def _write_archive_manifest(archive_dir: Path, project_root: Path, entries: list[dict]) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = archive_dir / f"cleanup-manifest-{ts}.json"
    payload = {
        "project_root": project_root.as_posix(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
