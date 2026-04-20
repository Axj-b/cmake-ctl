from __future__ import annotations

import json
from pathlib import Path


def discover_source_dir(argv: list[str], cwd: Path | None = None) -> Path:
    base = (cwd or Path.cwd()).resolve()

    source_arg = _find_option(argv, "-S", "--source")
    if source_arg:
        return (base / source_arg).resolve() if not Path(source_arg).is_absolute() else Path(source_arg).resolve()

    preset_name = _find_option(argv, "--preset")
    if preset_name:
        preset_source = _resolve_preset_source(base, preset_name)
        if preset_source is not None:
            return preset_source

    # Positional source path: cmake [options] <path>
    # e.g. cmake .. or cmake -G "Ninja" /path/to/src
    positional = _find_positional_source(argv)
    if positional:
        candidate = (base / positional).resolve() if not Path(positional).is_absolute() else Path(positional).resolve()
        if candidate.is_dir():
            return candidate

    if _looks_like_build_dir(base):
        cache_source = _source_from_cache(base)
        if cache_source is not None:
            return cache_source
        parent = _find_project_root(base.parent)
        if parent is not None:
            return parent

    root = _find_project_root(base)
    return root or base


def _find_option(argv: list[str], *names: str) -> str | None:
    for i, token in enumerate(argv):
        if token in names and i + 1 < len(argv):
            return argv[i + 1]
        for name in names:
            if token.startswith(name + "="):
                return token.split("=", 1)[1]
    return None


# Options that take a value argument (so their value is not a positional source).
_OPTIONS_WITH_VALUE = {
    "-G", "--generator",
    "-T", "--toolset",
    "-A", "--platform",
    "-D", "-U",
    "-C",
    "-S", "--source",
    "-B", "--build",
    "--preset",
    "--install-prefix",
    "--toolchain",
    "--project-file",
    "--trace-source",
    "--log-level",
    "--log-context",
    "-P",
    "--graphviz",
    "--system-information",
    "--loglevel",
    "-W",
}


def _find_positional_source(argv: list[str]) -> str | None:
    """Return the last bare positional argument that looks like a source path."""
    if any(flag in argv for flag in ("--build", "--install", "--open")):
        return None

    skip_next = False
    last_positional: str | None = None
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token in _OPTIONS_WITH_VALUE:
            skip_next = True
            continue
        # Inline -Dname=val, -Uname, etc.
        if token.startswith("-"):
            continue
        # This token is positional — treat it as the source path candidate.
        last_positional = token
    return last_positional


def _resolve_preset_source(cwd: Path, preset_name: str) -> Path | None:
    root = _find_project_root(cwd)
    if root is None:
        return None

    presets_file = root / "CMakePresets.json"
    if not presets_file.exists():
        return None

    try:
        presets = json.loads(presets_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    for preset in presets.get("configurePresets", []):
        if preset.get("name") == preset_name:
            src = preset.get("sourceDir")
            if src:
                return (root / src).resolve() if not Path(src).is_absolute() else Path(src).resolve()
            return root
    return None


def _looks_like_build_dir(path: Path) -> bool:
    names = {"build", "out"}
    if path.name.lower() in names:
        return True
    return (path / "CMakeCache.txt").exists() or (path / "CMakeFiles").is_dir()


def _source_from_cache(build_dir: Path) -> Path | None:
    cache = build_dir / "CMakeCache.txt"
    if not cache.exists():
        return None
    for line in cache.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("CMAKE_HOME_DIRECTORY") and "=" in line:
            source = line.split("=", 1)[1].strip()
            if source:
                p = Path(source)
                return p.resolve() if p.exists() else None
    return None


def _find_project_root(start: Path) -> Path | None:
    current = start
    while True:
        if (current / "CMakeLists.txt").exists() or (current / "CMakePresets.json").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent
