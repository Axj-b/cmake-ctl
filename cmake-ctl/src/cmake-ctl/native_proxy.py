from __future__ import annotations

import os
import subprocess
from pathlib import Path


RECURSION_ENV = "CMAKE_CTL_PROXY_ACTIVE"
LEGACY_RECURSION_ENV = "CMAKE_CTL_PROXY_ACTIVE_LEGACY"


class ProxyError(RuntimeError):
    pass


def run_native_proxy(argv: list[str], project_path: Path | None = None, tool_name: str = "cmake") -> int:
    if os.environ.get(RECURSION_ENV) == "1" or os.environ.get(LEGACY_RECURSION_ENV) == "1":
        raise ProxyError("Proxy recursion guard triggered")

    proj = (project_path or Path.cwd()).resolve()
    binary = _resolve_proxy_binary(tool_name)
    _check_no_recursion(binary)

    env = os.environ.copy()
    env[RECURSION_ENV] = "1"
    env[LEGACY_RECURSION_ENV] = "1"
    completed = subprocess.run([str(binary), *argv], cwd=str(proj), env=env, check=False)
    return int(completed.returncode)


def _resolve_proxy_binary(tool_name: str) -> Path:
    root = Path(__file__).resolve().parents[3]
    bin_dir = root / "bin"
    names = [tool_name]
    if os.name == "nt":
        names = [f"{tool_name}.exe", tool_name]
    for name in names:
        candidate = bin_dir / name
        if candidate.exists():
            return candidate.resolve()
    raise ProxyError(
        f"Native proxy binary not found for '{tool_name}' in {bin_dir}. "
        f"Run build.bat/build.sh first."
    )


def _check_no_recursion(target_exec: Path) -> None:
    current_exec = Path(__file__).resolve()
    if target_exec == current_exec:
        raise ProxyError("Proxy recursion detected: target executable resolves to Python module")
