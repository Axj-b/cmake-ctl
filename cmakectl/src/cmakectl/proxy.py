from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from .config_store import load_config
from .events import Event, append_event
from .paths import VERSIONS_DIR, ensure_layout
from .resolver import resolve_version
from .source_discovery import discover_source_dir
from .session_store import current_session_id

RECURSION_ENV = "CMAKECTL_PROXY_ACTIVE"


class ProxyError(RuntimeError):
    pass


def resolve_cmake_executable(project_path: Path, argv: list[str], explicit_version: str | None = None) -> tuple[Path, str, str]:
    ensure_layout()
    source_dir = discover_source_dir(argv, cwd=project_path)
    result = resolve_version(source_dir, explicit_override=explicit_version, session_id=current_session_id())
    cmake_candidate = (VERSIONS_DIR / result.version / "bin" / _cmake_name()).resolve()
    if not cmake_candidate.exists():
        raise ProxyError(
            f"Resolved version {result.version} but executable not found at {cmake_candidate}. Install it first."
        )

    current_exec = Path(__file__).resolve()
    if cmake_candidate == current_exec:
        raise ProxyError("Proxy recursion detected: target executable resolves to proxy itself")

    return cmake_candidate, result.version, result.source


def run_proxy(argv: list[str], project_path: Path | None = None, explicit_version: str | None = None) -> int:
    if os.environ.get(RECURSION_ENV) == "1":
        raise ProxyError("Proxy recursion guard triggered")

    proj = (project_path or Path.cwd()).resolve()
    cmake_exec, version, source = resolve_cmake_executable(proj, argv, explicit_version=explicit_version)

    append_event(
        Event(
            event_id=str(uuid.uuid4()),
            event_type="cmake_invocation",
            payload={
                "project_path": proj.as_posix(),
                "argv": argv,
                "resolved_version": version,
                "source": source,
            },
        )
    )

    env = os.environ.copy()
    env[RECURSION_ENV] = "1"
    completed = subprocess.run([str(cmake_exec), *argv], env=env, check=False)
    return int(completed.returncode)


def _cmake_name() -> str:
    return "cmake.exe" if os.name == "nt" else "cmake"
