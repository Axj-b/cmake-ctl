from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _vscode_settings_candidates() -> list[Path]:
    candidates: list[Path] = []

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates += [
                Path(appdata) / "Code" / "User" / "settings.json",
                Path(appdata) / "Code - Insiders" / "User" / "settings.json",
            ]
        # Scoop layout: vscode exe lives in …\scoop\apps\vscode\<ver>\,
        # settings live in …\scoop\apps\vscode\<ver>\data\user-data\User\settings.json
        import shutil
        code_exe = shutil.which("code")
        if code_exe:
            scoop_data = Path(code_exe).parent.parent / "data" / "user-data" / "User" / "settings.json"
            candidates.insert(0, scoop_data)
    else:
        home = Path.home()
        candidates += [
            home / ".config" / "Code" / "User" / "settings.json",
            home / ".config" / "Code - Insiders" / "User" / "settings.json",
            home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
        ]

    return candidates


def find_vscode_settings() -> Path | None:
    """Return the first existing VSCode user settings.json, or None."""
    for p in _vscode_settings_candidates():
        if p.exists():
            return p
    return None


def _proxy_exe_path() -> str:
    """Absolute forward-slash path to this installation's cmake proxy."""
    here = Path(__file__).resolve()
    # Package lives at <install>/cmake-ctl/src/cmake-ctl/; bin is at <install>/bin/
    # Walk up until we find a bin/cmake.exe sibling
    for parent in [here.parent, here.parent.parent, here.parent.parent.parent,
                   here.parent.parent.parent.parent]:
        candidate_win = parent / "bin" / "cmake.exe"
        candidate_unix = parent / "bin" / "cmake"
        for c in (candidate_win, candidate_unix):
            if c.exists():
                return c.as_posix()
    # Fallback: best-guess relative to where the package is installed
    install_root = here.parent.parent.parent.parent
    return (install_root / "bin" / "cmake.exe").as_posix()


def apply_vscode_settings(settings_path: Path | None = None) -> tuple[Path, str]:
    """
    Write cmake.cmakePath into a VSCode settings.json.

    Returns (resolved_path, proxy_path_written).
    Raises FileNotFoundError if no settings file can be determined.
    """
    if settings_path is None:
        settings_path = find_vscode_settings()

    if settings_path is None:
        # No existing file found – create at default location
        candidates = _vscode_settings_candidates()
        if not candidates:
            raise FileNotFoundError("Could not locate VSCode user settings directory.")
        settings_path = candidates[0]
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text("{}", encoding="utf-8")

    proxy_path = _proxy_exe_path()

    raw = settings_path.read_text(encoding="utf-8").strip() or "{}"
    try:
        settings: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse {settings_path}: {exc}") from exc

    settings["cmake.cmakePath"] = proxy_path
    settings_path.write_text(
        json.dumps(settings, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    return settings_path, proxy_path


def remove_vscode_settings(settings_path: Path | None = None) -> Path | None:
    """Remove cmake.cmakePath from VSCode settings.json. Returns path or None if not found."""
    if settings_path is None:
        settings_path = find_vscode_settings()
    if settings_path is None or not settings_path.exists():
        return None

    raw = settings_path.read_text(encoding="utf-8").strip() or "{}"
    try:
        settings: dict = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if "cmake.cmakePath" in settings:
        del settings["cmake.cmakePath"]
        settings_path.write_text(
            json.dumps(settings, indent=4, ensure_ascii=False), encoding="utf-8"
        )
    return settings_path
