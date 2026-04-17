#!/usr/bin/env python3
"""Create an end-user release zip for cmake-ctl.

This script is GitHub Actions friendly:
- Optionally builds the proxy artifact first.
- Stages runtime files for end users.
- Produces a versioned zip in dist/.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def detect_platform_tag() -> str:
    if sys.platform.startswith("win"):
        return "windows-x64"
    if sys.platform == "darwin":
        return "macos-x64"
    return "linux-x64"


def infer_version(explicit: str | None) -> str:
    if explicit:
        return explicit
    for env_name in ("RELEASE_VERSION", "GITHUB_REF_NAME", "GITHUB_SHA"):
        value = os.environ.get(env_name)
        if value:
            return value.replace("/", "-")
    return "dev"


def run_build(repo_root: Path) -> None:
    if os.name == "nt":
        command = ["cmd", "/c", str(repo_root / "build.bat")]
    else:
        command = ["bash", str(repo_root / "build.sh")]

    result = subprocess.run(command, cwd=repo_root, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Build failed with exit code {result.returncode}")


def require_proxy_binary(repo_root: Path) -> Path:
    candidates = [
        repo_root / "bin" / "cmake.exe",
        repo_root / "bin" / "cmake",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    expected = ", ".join(str(p) for p in candidates)
    raise SystemExit(f"Proxy binary not found. Expected one of: {expected}")


def write_cli_launchers(stage_root: Path) -> None:
    bin_dir = stage_root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    bat_path = bin_dir / "cmake-ctl.bat"
    bat_path.write_text(
        "@echo off\n"
        "setlocal\n"
        "set SCRIPT_DIR=%~dp0\n"
        "set ROOT_DIR=%SCRIPT_DIR%..\n"
        "set PYTHONPATH=%ROOT_DIR%\\python;%PYTHONPATH%\n"
        "python -m cmake-ctl.cli %*\n",
        encoding="utf-8",
    )

    sh_path = bin_dir / "cmake-ctl"
    sh_path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "SCRIPT_DIR=\"$( cd \"$( dirname \"${BASH_SOURCE[0]}\" )\" && pwd )\"\n"
        "ROOT_DIR=\"$SCRIPT_DIR/..\"\n"
        "export PYTHONPATH=\"$ROOT_DIR/python:${PYTHONPATH:-}\"\n"
        "exec python -m cmake-ctl.cli \"$@\"\n",
        encoding="utf-8",
    )
    sh_path.chmod(0o755)


def stage_release_files(repo_root: Path, stage_root: Path, proxy_binary: Path) -> None:
    (stage_root / "bin").mkdir(parents=True, exist_ok=True)
    (stage_root / "python").mkdir(parents=True, exist_ok=True)

    shutil.copy2(proxy_binary, stage_root / "bin" / proxy_binary.name)

    package_src = repo_root / "cmake-ctl" / "src" / "cmake-ctl"
    if not package_src.exists():
        raise SystemExit(f"Python package path missing: {package_src}")
    shutil.copytree(
        package_src,
        stage_root / "python" / "cmake-ctl",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    for file_name in ("README.md", "INSTALLATION.md"):
        src = repo_root / file_name
        if src.exists():
            shutil.copy2(src, stage_root / file_name)

    # Setup scripts
    for script_name in ("setup.ps1", "setup.sh"):
        src = repo_root / script_name
        if src.exists():
            dest = stage_root / script_name
            shutil.copy2(src, dest)
            if script_name.endswith(".sh"):
                dest.chmod(0o755)

    notes_path = stage_root / "USAGE.txt"
    notes_path.write_text(
        "cmake-ctl release package\n"
        "\n"
        "Quick setup (recommended):\n"
        "Windows PowerShell:\n"
        "  .\\setup.ps1              # add bin\\ to PATH\n"
        "  .\\setup.ps1 -VSCode      # also configure VSCode cmake path\n"
        "  .\\setup.ps1 -Uninstall   # undo changes\n"
        "\n"
        "Linux/macOS:\n"
        "  ./setup.sh               # add bin/ to PATH\n"
        "  ./setup.sh --vscode      # also configure VSCode cmake path\n"
        "  ./setup.sh --uninstall   # undo changes\n"
        "\n"
        "Manual setup:\n"
        "Windows:\n"
        "  set PATH=%CD%\\bin;%PATH%\n"
        "  bin\\cmake-ctl.bat list\n"
        "\n"
        "Linux/macOS:\n"
        "  export PATH=\"$PWD/bin:$PATH\"\n"
        "  bin/cmake-ctl list\n"
        "\n"
        "Contents:\n"
        "- bin/cmake(.exe): cmake proxy executable\n"
        "- python/cmake-ctl: Python CLI package source\n"
        "- bin/cmake-ctl(.bat): helper launchers\n"
        "- setup.ps1: Windows setup script\n"
        "- setup.sh: Linux/macOS setup script\n",
        encoding="utf-8",
    )

    write_cli_launchers(stage_root)


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_dir():
                continue
            zf.write(path, arcname=path.relative_to(source_dir).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an end-user release zip")
    parser.add_argument("--version", help="Release version label (default: env or dev)")
    parser.add_argument("--platform", help="Platform label (default: auto)")
    parser.add_argument("--out-dir", default="dist", help="Output directory for zip")
    parser.add_argument("--skip-build", action="store_true", help="Do not run build step")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    version = infer_version(args.version)
    platform = args.platform or detect_platform_tag()
    package_name = f"cmake-ctl-{version}-{platform}"

    if not args.skip_build:
        run_build(repo_root)

    proxy_binary = require_proxy_binary(repo_root)

    with tempfile.TemporaryDirectory(prefix="cmake-ctl-release-") as tmp_dir:
        stage_root = Path(tmp_dir) / package_name
        stage_root.mkdir(parents=True, exist_ok=True)
        stage_release_files(repo_root, stage_root, proxy_binary)

        zip_path = repo_root / args.out_dir / f"{package_name}.zip"
        zip_directory(stage_root, zip_path)
        print(f"Created release zip: {zip_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
