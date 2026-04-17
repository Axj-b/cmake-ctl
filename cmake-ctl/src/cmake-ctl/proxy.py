from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from .config_store import load_config
from .events import Event, append_event
from .project_tracker import process_event as _track_event
from .paths import VERSIONS_DIR, ensure_layout
from .resolver import resolve_version
from .source_discovery import discover_source_dir
from .session_store import current_session_id

RECURSION_ENV = "CMAKE_CTL_PROXY_ACTIVE"
LEGACY_RECURSION_ENV = "CMAKE_CTL_PROXY_ACTIVE"


class ProxyError(RuntimeError):
    pass


def resolve_cmake_executable(project_path: Path, argv: list[str], explicit_version: str | None = None) -> tuple[Path, str, str]:
    ensure_layout()
    source_dir = discover_source_dir(argv, cwd=project_path)
    result = resolve_version(source_dir, explicit_override=explicit_version, session_id=current_session_id())

    cmake_candidate = _find_cmake_in_version(result.version)
    if cmake_candidate is not None:
        _check_no_recursion(cmake_candidate)
        return cmake_candidate, result.version, result.source

    # Resolved version directory exists but binary is missing — walk remaining
    # installed versions (global → latest) and use the first working one.
    config = load_config()
    fallback_order: list[tuple[str, str]] = []
    if config.global_version and config.global_version != result.version:
        fallback_order.append((config.global_version, "global-fallback"))
    from .resolver import latest_installed_version, is_installed_version
    latest = latest_installed_version()
    if latest and latest != result.version:
        fallback_order.append((latest, "latest-fallback"))

    for fb_version, fb_source in fallback_order:
        if not is_installed_version(fb_version):
            continue
        fb_candidate = _find_cmake_in_version(fb_version)
        if fb_candidate is not None:
            import warnings
            warnings.warn(
                f"cmake-ctl: version '{result.version}' binary not found; "
                f"falling back to '{fb_version}' ({fb_source})",
                stacklevel=2,
            )
            _check_no_recursion(fb_candidate)
            return fb_candidate, fb_version, fb_source

    raise ProxyError(
        f"Resolved version '{result.version}' but executable not found at "
        f"{VERSIONS_DIR / result.version}. Install it first with: cmake-ctl install {result.version}"
    )


def run_proxy(argv: list[str], project_path: Path | None = None, explicit_version: str | None = None) -> int:
    if os.environ.get(RECURSION_ENV) == "1" or os.environ.get(LEGACY_RECURSION_ENV) == "1":
        raise ProxyError("Proxy recursion guard triggered")

    proj = (project_path or Path.cwd()).resolve()
    cmake_exec, version, source = resolve_cmake_executable(proj, argv, explicit_version=explicit_version)

    source_dir = discover_source_dir(argv, cwd=proj)

    event = Event(
        event_id=str(uuid.uuid4()),
        event_type="cmake_invocation",
        payload={
            "project_path": source_dir.resolve().as_posix(),
            "source_dir": source_dir.resolve().as_posix(),
            "build_dir": proj.as_posix(),
            "cwd": proj.as_posix(),
            "argv": argv,
            "resolved_version": version,
            "source": source,
        },
    )
    append_event(event)
    # Auto-process immediately so projects.db is always up-to-date.
    try:
        _track_event(event)
    except Exception:
        pass  # Never let tracking failure abort the actual cmake invocation.

    env = os.environ.copy()
    env[RECURSION_ENV] = "1"
    env[LEGACY_RECURSION_ENV] = "1"
    completed = subprocess.run([str(cmake_exec), *argv], env=env, check=False)
    return int(completed.returncode)


def _cmake_name() -> str:
    return "cmake.exe" if os.name == "nt" else "cmake"


def _find_cmake_in_version(version: str) -> Path | None:
    """Return the resolved cmake binary path for a managed version, or None if not found."""
    bin_dir = VERSIONS_DIR / version / "bin"
    for name in ("cmake.exe", "cmake"):
        candidate = bin_dir / name
        if candidate.exists():
            try:
                return candidate.resolve()
            except OSError:
                return candidate
    return None


def _check_no_recursion(cmake_candidate: Path) -> None:
    current_exec = Path(__file__).resolve()
    if cmake_candidate == current_exec:
        raise ProxyError("Proxy recursion detected: target executable resolves to proxy itself")
