from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config_store import Config, load_config, save_config
from .identity import ProjectIdentity, resolve_project_identity
from .paths import VERSIONS_DIR, ensure_layout
from .session_store import SessionStore


@dataclass
class ResolutionResult:
    version: str
    source: str
    project_identity: ProjectIdentity


def _read_dot_cmake_version(project_path: Path) -> str | None:
    marker = project_path / ".cmake-version"
    if not marker.exists():
        return None
    value = marker.read_text(encoding="utf-8").strip()
    return value or None


def _parse_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def latest_installed_version() -> str | None:
    ensure_layout()
    if not VERSIONS_DIR.exists():
        return None
    versions = [p.name for p in VERSIONS_DIR.iterdir() if p.is_dir()]
    if not versions:
        return None
    return sorted(versions, key=_parse_version, reverse=True)[0]


def is_installed_version(version: str) -> bool:
    return (VERSIONS_DIR / version).is_dir()


def resolve_version(
    project_path: Path,
    explicit_override: str | None = None,
    session_id: str | None = None,
    config: Config | None = None,
    sessions: SessionStore | None = None,
) -> ResolutionResult:
    cfg = config or load_config()
    sess = sessions or SessionStore.load()
    identity = resolve_project_identity(project_path, cfg.identity_mode, create_if_missing=False)

    candidates: list[tuple[str, str]] = []
    if explicit_override:
        candidates.append((explicit_override, "explicit"))

    if session_id:
        session_version = sess.get_override(session_id, identity.key)
        if session_version:
            candidates.append((session_version, "session"))

    project_persistent = cfg.project_versions.get(identity.key)
    if project_persistent:
        candidates.append((project_persistent, "project"))

    file_version = _read_dot_cmake_version(identity.canonical_path)
    if file_version:
        candidates.append((file_version, "file"))

    if cfg.global_version:
        candidates.append((cfg.global_version, "global"))

    latest = latest_installed_version()
    if latest:
        candidates.append((latest, "latest"))

    if not candidates:
        raise RuntimeError("No CMake version could be resolved. Install one with: cmakectl install <version>")

    for version, source in candidates:
        if is_installed_version(version):
            return ResolutionResult(version=version, source=source, project_identity=identity)

    preferred, preferred_source = candidates[0]
    raise RuntimeError(
        f"Resolved {preferred_source} version '{preferred}', but it is not installed in managed versions. "
        f"Install it with: cmakectl install {preferred} --url <artifact-url> --manifest <manifest.json>"
    )


def set_global_version(version: str, config: Config | None = None) -> Config:
    cfg = config or load_config()
    cfg.global_version = version
    save_config(cfg)
    return cfg


def set_project_version(version: str, project_path: Path, config: Config | None = None) -> tuple[Config, ProjectIdentity]:
    cfg = config or load_config()
    identity = resolve_project_identity(project_path, cfg.identity_mode, create_if_missing=True)
    cfg.project_versions[identity.key] = version
    if identity.project_id:
        cfg.project_paths[identity.project_id] = identity.canonical_path.as_posix()
    save_config(cfg)
    return cfg, identity


def reconcile_project_path(project_path: Path, config: Config | None = None) -> bool:
    cfg = config or load_config()
    identity = resolve_project_identity(project_path, cfg.identity_mode, create_if_missing=False)
    if not identity.project_id:
        return False

    current = cfg.project_paths.get(identity.project_id)
    candidate = identity.canonical_path.as_posix()
    if current == candidate:
        return False

    cfg.project_paths[identity.project_id] = candidate
    save_config(cfg)
    return True
