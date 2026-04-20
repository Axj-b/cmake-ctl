from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .cleaner import execute_cleanup, plan_cleanup
from .config_store import load_config, save_config
from .database import list_projects, set_pinned
from .events import process_events
from .installer import InstallError, construct_release_url, install_from_archive, install_version
from .native_proxy import run_native_proxy
from .project_tracker import process_event
from .resolver import (
    reconcile_project_path,
    resolve_version,
    set_global_version,
    set_project_version,
)
from .session_store import SessionStore, current_session_id
from .source_discovery import discover_source_dir
from .vscode_setup import apply_vscode_settings, find_vscode_settings, remove_vscode_settings

# ANSI color codes
_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
_MAGENTA = "\033[95m"
_CYAN = "\033[96m"
_WHITE = "\033[97m"


def _colorize(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}"


@dataclass
class UiState:
    status: str = "idle"
    last_command: str = "-"
    logs: list[str] = field(default_factory=list)
    max_logs: int = 200


def _clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _log(state: UiState, message: str) -> None:
    for line in str(message).splitlines() or [""]:
        state.logs.append(line)
    if len(state.logs) > state.max_logs:
        state.logs = state.logs[-state.max_logs :]


def _set_status(state: UiState, status: str) -> None:
    state.status = status


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{_colorize(str(default), _CYAN)}]" if default is not None else ""
    value = input(_colorize(f"{prompt}", _MAGENTA) + suffix + ": ").strip()
    return value if value else (default or "")


def _ask_yes_no(prompt: str, default: bool = False) -> bool:
    default_token = "Y/n" if default else "y/N"
    value = input(_colorize(f"{prompt}", _MAGENTA) + f" ({_colorize(default_token, _CYAN)}): ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def _render(state: UiState) -> None:
    _clear_screen()
    cols, rows = shutil.get_terminal_size((120, 40))
    sep = _colorize("-" * cols, _CYAN)

    config = load_config()
    print(_colorize("cmake-ctl TUI", _BOLD + _BLUE))
    print(f"cwd: {_colorize(Path.cwd().as_posix(), _GREEN)}")
    status_color = _RED if state.status == "error" else (_GREEN if state.status == "done" else _YELLOW)
    print(f"status: {_colorize(state.status, status_color)}")
    print(f"last command: {_colorize(state.last_command, _MAGENTA)}")
    global_ver = config.global_version or _colorize("<unset>", _RED)
    print(f"global_version: {_colorize(global_ver, _CYAN)} | identity_mode: {_colorize(config.identity_mode, _CYAN)}")
    print(sep)
    print(_colorize("Commands:", _BOLD + _WHITE) + " /resolve /use /install /install-archive /list /uninstall /clear-downloads /events /projects /clean /proxy-run /show-config /setup-vscode /identity-mode /help /exit /q")
    print(sep)
    print(_colorize("Output", _BOLD + _WHITE))

    output_height = max(8, rows - 11)
    visible = state.logs[-output_height:]
    for line in visible:
        print(line[:cols])


def _menu_help(state: UiState) -> None:
    _log(state, _colorize("Available commands:", _BOLD + _CYAN))
    _log(state, _colorize("  /resolve", _GREEN))
    _log(state, _colorize("  /use", _GREEN))
    _log(state, _colorize("  /install", _GREEN))
    _log(state, _colorize("  /install-archive", _GREEN))
    _log(state, _colorize("  /list", _GREEN))
    _log(state, _colorize("  /uninstall", _GREEN))
    _log(state, _colorize("  /clear-downloads", _GREEN))
    _log(state, _colorize("  /events", _GREEN))
    _log(state, _colorize("  /projects", _GREEN))
    _log(state, _colorize("  /clean", _GREEN))
    _log(state, _colorize("  /proxy-run", _GREEN))
    _log(state, _colorize("  /show-config", _GREEN))
    _log(state, _colorize("  /identity-mode", _GREEN))
    _log(state, _colorize("  /setup-vscode", _GREEN))
    _log(state, _colorize("  /exit or /q", _RED))


def _read_key() -> str:
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getch()
        if ch in {b"\x00", b"\xe0"}:
            ch2 = msvcrt.getch()
            if ch2 == b"H":
                return "UP"
            if ch2 == b"P":
                return "DOWN"
            return "SPECIAL"
        if ch in {b"\r", b"\n"}:
            return "ENTER"
        if ch == b"\x1b":
            return "ESC"
        try:
            return ch.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            ch3 = sys.stdin.read(1)
            if ch2 == "[" and ch3 == "A":
                return "UP"
            if ch2 == "[" and ch3 == "B":
                return "DOWN"
            return "ESC"
        if ch in {"\r", "\n"}:
            return "ENTER"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _select_version_with_arrows(state: UiState, versions: list[str], current: str | None) -> str | None:
    if not versions:
        return None

    cursor = 0
    if current and current in versions:
        cursor = versions.index(current)

    while True:
        _clear_screen()
        print(_colorize("cmake-ctl TUI - version selector", _BOLD + _BLUE))
        print(_colorize("Up/Down: navigate  |  Enter: set as global  |  d: delete  |  q/Esc: cancel", _YELLOW))
        print("")
        for idx, version in enumerate(versions):
            pointer = ">" if idx == cursor else " "
            marker = _colorize("*", _GREEN) if version == current else " "
            line = f"{pointer} {marker} {version}"
            if idx == cursor:
                line = _colorize(line, _GREEN + _BOLD)
            print(line)

        key = _read_key()
        if key == "UP":
            cursor = (cursor - 1) % len(versions)
        elif key == "DOWN":
            cursor = (cursor + 1) % len(versions)
        elif key == "ENTER":
            return versions[cursor]
        elif key in {"d", "D"}:
            return f"__DELETE__{versions[cursor]}"
        elif key in {"ESC", "q", "Q"}:
            return None


def _select_cleanup_targets_with_arrows(targets: list[Path]) -> list[Path]:
    if not targets:
        return []

    selected = [False] * len(targets)
    cursor = 0

    while True:
        _clear_screen()
        print(_colorize("cmake-ctl TUI - cleanup target selector", _BOLD + _BLUE))
        print(_colorize("Use Up/Down to navigate, Space to toggle selection, Enter to confirm, q or Esc to cancel", _YELLOW))
        
        # Calculate sizes for display
        target_sizes = []
        for t in targets:
            from .cleaner import _path_size
            size = _path_size(t)
            size_mb = size / (1024 * 1024)
            target_sizes.append((t, size, size_mb))
        
        print("")
        total_selected_bytes = 0
        for idx, (target, size, size_mb) in enumerate(target_sizes):
            pointer = ">" if idx == cursor else " "
            checkbox = "[x]" if selected[idx] else "[ ]"
            line = f"{pointer} {checkbox} {target.as_posix()} ({size_mb:.1f} MB)"
            
            if idx == cursor:
                line = _colorize(line, _GREEN + _BOLD)
            elif selected[idx]:
                line = _colorize(line, _GREEN)
            
            if selected[idx]:
                total_selected_bytes += size
            
            print(line)
        
        print("")
        total_selected_mb = total_selected_bytes / (1024 * 1024)
        print(_colorize(f"Total selected: {total_selected_mb:.1f} MB", _CYAN))

        key = _read_key()
        if key == "UP":
            cursor = (cursor - 1) % len(targets)
        elif key == "DOWN":
            cursor = (cursor + 1) % len(targets)
        elif key == " ":
            selected[cursor] = not selected[cursor]
        elif key == "ENTER":
            return [targets[i] for i in range(len(targets)) if selected[i]]
        elif key in {"ESC", "q", "Q"}:
            return []


def _select_project_with_arrows(state: UiState) -> Path | None:
    """Interactive selector for tracked projects."""
    rows = list_projects()
    if not rows:
        _log(state, _colorize("No tracked projects found. Use /projects to see tracked projects.", _YELLOW))
        return None
    
    cursor = 0
    
    while True:
        _clear_screen()
        print(_colorize("cmake-ctl TUI - project selector", _BOLD + _BLUE))
        print(_colorize("Use Up/Down to navigate, Enter to select, q or Esc to cancel", _YELLOW))
        print("")
        
        for idx, row in enumerate(rows):
            pointer = ">" if idx == cursor else " "
            pin_mark = _colorize("[pinned]", _GREEN) if row["pinned"] else _colorize("[unpinned]", _YELLOW)
            line = f"{pointer} {pin_mark} {_colorize(row['project_key'], _CYAN)} - {_colorize(row['path'], _BLUE)}"
            
            if idx == cursor:
                line = _colorize(line, _GREEN + _BOLD)
            
            print(line)
        
        key = _read_key()
        if key == "UP":
            cursor = (cursor - 1) % len(rows)
        elif key == "DOWN":
            cursor = (cursor + 1) % len(rows)
        elif key == "ENTER":
            selected_path = rows[cursor]["path"]
            _log(state, _colorize(f"Selected project: {selected_path}", _GREEN))
            return Path(selected_path)
        elif key in {"ESC", "q", "Q"}:
            _log(state, _colorize("Project selection cancelled", _YELLOW))
            return None



def _action_resolve(state: UiState) -> None:
    project = _ask("Project path", ".")
    raw_args = _ask("Optional cmake args (space-separated)", "")
    cmake_args = raw_args.split() if raw_args else []

    config = load_config()
    project_path = Path(project)
    source_path = discover_source_dir(cmake_args, cwd=project_path)
    updated = reconcile_project_path(project_path, config=config)
    if updated:
        _log(state, _colorize("Project path metadata reconciled for moved project.", _GREEN))

    result = resolve_version(source_path, session_id=current_session_id(), config=config)
    _log(state, f"version={_colorize(result.version, _CYAN)}")
    _log(state, f"source={_colorize(result.source, _MAGENTA)}")
    _log(state, f"project_key={_colorize(result.project_identity.key, _GREEN)}")
    _log(state, f"source_dir={_colorize(source_path.as_posix(), _CYAN)}")


def _action_use(state: UiState) -> None:
    version = _ask("Version to set")
    if not version:
        _log(state, _colorize("No version entered.", _RED))
        return

    mode = _ask("Mode: global/project/session", "global").lower()
    config = load_config()

    if mode == "session":
        project = _ask("Project path", ".")
        session_id = current_session_id()
        sessions = SessionStore.load()
        identity = resolve_version(Path(project), session_id=None, config=config, sessions=sessions).project_identity
        sessions.set_override(session_id, identity.key, version)
        sessions.save()
        _log(state, _colorize(f"Session override set: {version} for {identity.key}", _GREEN))
        return

    if mode == "project":
        project = _ask("Project path", ".")
        _, identity = set_project_version(version, Path(project), config=config)
        _log(state, _colorize(f"Project version set: {version} for {identity.key}", _GREEN))
        return

    set_global_version(version, config=config)
    _log(state, _colorize("Global version updated. Already-open terminals will use this version on the next cmake invocation.", _GREEN))


def _action_install_url(state: UiState) -> None:
    version = _ask("Version to install")
    url = _ask("Artifact URL (optional; auto-constructed when empty)", "")
    manifest = _ask("Manifest path (optional)", "")
    sha256 = _ask("SHA256 (optional)", "")
    if not version:
        _log(state, _colorize("Version is required.", _RED))
        return

    if not url:
        url = construct_release_url(version)
        _log(state, _colorize(f"auto-url: {url}", _CYAN))

    last_percent = -1

    def _status(step: str, detail: str) -> None:
        _set_status(state, f"{step}")
        _log(state, _colorize(f"[{step}]", _BLUE) + f" {detail}")
        _render(state)

    def _progress(downloaded: int, total: int) -> None:
        nonlocal last_percent
        if total <= 0:
            return
        pct = int((downloaded / total) * 100)
        if pct == last_percent:
            return
        if pct < 100 and pct % 5 != 0:
            return
        last_percent = pct
        _set_status(state, f"download {pct}%")
        pct_color = _RED if pct < 30 else (_YELLOW if pct < 70 else _GREEN)
        _log(state, _colorize(f"[download]", _BLUE) + f" {_colorize(str(pct) + '%', pct_color)} ({downloaded}/{total} bytes)")
        _render(state)

    try:
        target = install_version(
            version,
            url,
            manifest_path=Path(manifest) if manifest else None,
            expected_sha256=sha256 or None,
            status_callback=_status,
            progress_callback=_progress,
        )
    except InstallError as exc:
        _set_status(state, "error")
        _log(state, _colorize(f"install error: {exc}", _RED))
        return

    if not manifest and not sha256:
        _log(state, _colorize("warning: installed without checksum verification", _YELLOW))
    _log(state, _colorize(f"installed: {target.as_posix()}", _GREEN))
    _set_status(state, "done")


def _action_install_archive(state: UiState) -> None:
    version = _ask("Version to install as")
    archive = _ask("Archive path")
    if not version or not archive:
        _log(state, _colorize("Version and archive path are required.", _RED))
        return

    def _status(step: str, detail: str) -> None:
        _set_status(state, step)
        _log(state, _colorize(f"[{step}]", _BLUE) + f" {detail}")
        _render(state)

    try:
        target = install_from_archive(version, archive, status_callback=_status)
    except InstallError as exc:
        _set_status(state, "error")
        _log(state, _colorize(f"install error: {exc}", _RED))
        return

    _log(state, _colorize(f"installed: {target.as_posix()}", _GREEN))
    _set_status(state, "done")


def _action_list_versions(state: UiState) -> None:
    from .paths import VERSIONS_DIR
    import shutil as _shutil

    if not VERSIONS_DIR.exists():
        _log(state, _colorize("No versions installed", _YELLOW))
        return

    versions = sorted([p.name for p in VERSIONS_DIR.iterdir() if p.is_dir()])
    if not versions:
        _log(state, _colorize("No versions installed", _YELLOW))
        return

    current = load_config().global_version
    selected = _select_version_with_arrows(state, versions, current)
    _render(state)
    if not selected:
        _log(state, _colorize("Version selection canceled", _YELLOW))
        return

    if selected.startswith("__DELETE__"):
        version_to_delete = selected[len("__DELETE__"):]
        confirm = _ask_yes_no(f"Delete version {version_to_delete}?", default=False)
        if not confirm:
            _log(state, _colorize("Deletion cancelled", _YELLOW))
            return
        _shutil.rmtree(VERSIONS_DIR / version_to_delete)
        _log(state, _colorize(f"Removed version: {version_to_delete}", _GREEN))
        config = load_config()
        if config.global_version == version_to_delete:
            config.global_version = None
            save_config(config)
            _log(state, _colorize("Cleared global_version (was set to the removed version)", _YELLOW))
        return

    set_global_version(selected)
    _log(state, _colorize(f"Selected and set global version: {selected}", _GREEN))


def _action_uninstall(state: UiState) -> None:
    from .paths import VERSIONS_DIR
    from .resolver import is_installed_version
    import shutil as _shutil

    if not VERSIONS_DIR.exists():
        _log(state, _colorize("No versions installed", _YELLOW))
        return

    versions = sorted([p.name for p in VERSIONS_DIR.iterdir() if p.is_dir()])
    if not versions:
        _log(state, _colorize("No versions installed", _YELLOW))
        return

    current = load_config().global_version
    # Show selector — pressing Enter picks for deletion immediately
    _clear_screen()
    print(_colorize("cmake-ctl TUI - uninstall version", _BOLD + _BLUE))
    print(_colorize("Up/Down: navigate  |  Enter: delete selected  |  q/Esc: cancel", _YELLOW))
    cursor = 0
    if current and current in versions:
        cursor = versions.index(current)

    while True:
        _clear_screen()
        print(_colorize("cmake-ctl TUI - uninstall version", _BOLD + _BLUE))
        print(_colorize("Up/Down: navigate  |  Enter: delete selected  |  q/Esc: cancel", _YELLOW))
        print("")
        for idx, version in enumerate(versions):
            pointer = ">" if idx == cursor else " "
            marker = _colorize("*", _GREEN) if version == current else " "
            line = f"{pointer} {marker} {version}"
            if idx == cursor:
                line = _colorize(line, _RED + _BOLD)
            print(line)

        key = _read_key()
        if key == "UP":
            cursor = (cursor - 1) % len(versions)
        elif key == "DOWN":
            cursor = (cursor + 1) % len(versions)
        elif key == "ENTER":
            version_to_delete = versions[cursor]
            _render(state)
            confirm = _ask_yes_no(_colorize(f"Delete version {version_to_delete}?", _RED), default=False)
            if not confirm:
                _log(state, _colorize("Deletion cancelled", _YELLOW))
                return
            _shutil.rmtree(VERSIONS_DIR / version_to_delete)
            _log(state, _colorize(f"Removed version: {version_to_delete}", _GREEN))
            config = load_config()
            if config.global_version == version_to_delete:
                config.global_version = None
                save_config(config)
                _log(state, _colorize("Cleared global_version (was set to the removed version)", _YELLOW))
            return
        elif key in {"ESC", "q", "Q"}:
            _log(state, _colorize("Uninstall cancelled", _YELLOW))
            return


def _action_clear_downloads(state: UiState) -> None:
    from .paths import DOWNLOADS_DIR
    import shutil as _shutil

    if not DOWNLOADS_DIR.exists() or not any(DOWNLOADS_DIR.iterdir()):
        _log(state, _colorize("Downloads folder is already empty", _YELLOW))
        return

    files = list(DOWNLOADS_DIR.iterdir())
    total = sum(f.stat().st_size for f in files if f.is_file())
    _log(state, _colorize(f"{len(files)} file(s)  {total / (1024*1024):.1f} MB in {DOWNLOADS_DIR}", _CYAN))
    confirm = _ask_yes_no("Delete all downloads?", default=False)
    if not confirm:
        _log(state, _colorize("Cancelled", _YELLOW))
        return
    _shutil.rmtree(DOWNLOADS_DIR)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _log(state, _colorize("Downloads folder cleared", _GREEN))


def _action_events(state: UiState) -> None:
    metrics = process_events(process_event)
    _log(state, _colorize("Event processing metrics:", _CYAN))
    _log(state, json.dumps(metrics, indent=2, sort_keys=True))


def _action_projects(state: UiState) -> None:
    def _resolve_key_from_id_or_key(token: str, rows: list[dict]) -> str:
        value = token.strip()
        if not value:
            raise ValueError("Project ID/key is required")
        if value.isdigit():
            idx = int(value)
            if 1 <= idx <= len(rows):
                return str(rows[idx - 1]["project_key"])
        return value

    sub_action = _ask("projects action: list/pin/unpin", "list").lower()
    rows = list_projects()

    if sub_action == "pin":
        token = _ask("Project ID or key to pin")
        if token:
            try:
                key = _resolve_key_from_id_or_key(token, rows)
            except ValueError as exc:
                _log(state, _colorize(f"error: {exc}", _RED))
                return
            set_pinned(key, True)
            _log(state, _colorize(f"Pinned: {key}", _GREEN))
            rows = list_projects()
    elif sub_action == "unpin":
        token = _ask("Project ID or key to unpin")
        if token:
            try:
                key = _resolve_key_from_id_or_key(token, rows)
            except ValueError as exc:
                _log(state, _colorize(f"error: {exc}", _RED))
                return
            set_pinned(key, False)
            _log(state, _colorize(f"Unpinned: {key}", _YELLOW))
            rows = list_projects()

    if not rows:
        _log(state, _colorize("No tracked projects", _YELLOW))
        return

    _log(state, _colorize(f"\n  {len(rows)} tracked project(s)", _BOLD + _WHITE))
    for i, row in enumerate(rows, 1):
        pin_mark = _colorize("● pinned", _GREEN) if row["pinned"] else _colorize("○ unpinned", _YELLOW)
        gen = row.get("generator") or ""
        gen_str = f"  {_colorize('•', _WHITE)} generator : {_colorize(gen, _WHITE)}" if gen else ""
        _log(state, "")
        _log(state, f"  {_colorize(str(i) + '.', _BOLD + _WHITE)} {_colorize(row['project_key'], _BOLD + _CYAN)}")
        _log(state, f"  {_colorize('•', _WHITE)} id        : {_colorize(str(i), _WHITE)}")
        _log(state, f"  {_colorize('•', _WHITE)} project key: {_colorize(row['project_key'], _CYAN)}")
        _log(state, f"  {_colorize('•', _WHITE)} path      : {_colorize(row['path'], _BLUE)}")
        _log(state, f"  {_colorize('•', _WHITE)} cmake     : {_colorize(row['cmake_version'], _MAGENTA)}")
        if gen_str:
            _log(state, gen_str)
        _log(state, f"  {_colorize('•', _WHITE)} status    : {pin_mark}")


def _action_projects_with_args(state: UiState, args: list[str]) -> bool:
    """Handle inline projects subcommands; returns True when handled."""
    if not args:
        return False

    rows = list_projects()

    def _resolve_key_from_id_or_key(token: str) -> str:
        value = token.strip()
        if not value:
            raise ValueError("Project ID/key is required")
        if value.isdigit():
            idx = int(value)
            if 1 <= idx <= len(rows):
                return str(rows[idx - 1]["project_key"])
        return value

    cmd = args[0].lower()
    try:
        if cmd == "pin" and len(args) >= 2:
            key = _resolve_key_from_id_or_key(args[1])
            set_pinned(key, True)
            _log(state, _colorize(f"Pinned: {key}", _GREEN))
            _action_projects(state)
            return True
        if cmd == "unpin" and len(args) >= 2:
            key = _resolve_key_from_id_or_key(args[1])
            set_pinned(key, False)
            _log(state, _colorize(f"Unpinned: {key}", _YELLOW))
            _action_projects(state)
            return True
        if cmd == "remove" and len(args) >= 2:
            key = _resolve_key_from_id_or_key(args[1])
            from .database import remove_project
            removed = remove_project(key)
            if removed:
                _log(state, _colorize(f"Removed tracked project: {key}", _GREEN))
            else:
                _log(state, _colorize(f"No tracked project found for: {args[1]}", _YELLOW))
            _action_projects(state)
            return True
        if cmd == "prune-missing":
            from .database import prune_missing_projects
            removed = prune_missing_projects()
            _log(state, _colorize(f"Pruned missing project entries: {removed}", _GREEN if removed else _YELLOW))
            _action_projects(state)
            return True
    except ValueError as exc:
        _log(state, _colorize(f"error: {exc}", _RED))
        return True

    return False


def _action_clean(state: UiState) -> None:
    # First, offer choice between tracked projects or custom path
    choice = _ask("Select from: (1) tracked projects, (2) custom path", "1").strip()
    
    project_path = None
    if choice == "1":
        # Interactive project selection from tracked projects
        project_path = _select_project_with_arrows(state)
        _render(state)
        if not project_path:
            return
    else:
        # Custom path entry
        custom_path = _ask("Project root", ".")
        project_path = Path(custom_path)
    
    build_dir = _ask("Build directory (optional, auto-discover if empty)", "")
    archive_dir = _ask("Archive manifest directory (optional)", "")
    pinned = _ask_yes_no("Treat project as pinned", default=False)
    
    plan = plan_cleanup(project_path, Path(build_dir) if build_dir else None)
    
    if not plan.targets:
        _log(state, _colorize("No cleanup targets found", _YELLOW))
        return
    
    # Interactive target selection
    selected_targets = _select_cleanup_targets_with_arrows(plan.targets)
    _render(state)
    
    if not selected_targets:
        _log(state, _colorize("Cleanup cancelled - no targets selected", _YELLOW))
        return
    
    # Calculate size of selected targets only
    from .cleaner import _path_size
    selected_bytes = sum(_path_size(t) for t in selected_targets)
    
    _log(state, _colorize(f"Selected {len(selected_targets)} target(s) - {selected_bytes / (1024*1024):.1f} MB", _CYAN))
    execute = _ask_yes_no("Execute deletion (if No: preview only)", default=False)
    
    # Execute cleanup with selected targets only
    from .cleaner import CleanupPlan
    selected_plan = CleanupPlan(targets=selected_targets, bytes_reclaimable=selected_bytes)
    
    result = execute_cleanup(
        selected_plan,
        project_path,
        pinned=pinned,
        dry_run=not execute,
        archive_dir=Path(archive_dir) if archive_dir else None,
    )
    
    deleted_color = _GREEN if result['deleted'] > 0 else _YELLOW
    _log(state, f"targets={len(selected_plan.targets)}")
    _log(state, f"bytes={selected_plan.bytes_reclaimable}")
    _log(state, _colorize(f"deleted={result['deleted']}", deleted_color))
    _log(state, f"skipped_pinned={result['skipped_pinned']}")
    _log(state, f"archived={result['archived']}")


def _action_proxy_run(state: UiState) -> None:
    raw = _ask("cmake args to pass through (space-separated)", "")
    args = raw.split() if raw else []
    exit_code = run_native_proxy(args, project_path=Path.cwd(), tool_name="cmake")
    exit_color = _GREEN if exit_code == 0 else _RED
    _log(state, _colorize(f"proxy exit code: {exit_code}", exit_color))


def _action_show_config(state: UiState) -> None:
    raw = _ask_yes_no("Show raw config dict", default=False)
    config = load_config()
    if raw:
        _log(state, _colorize("Raw config:", _CYAN))
        _log(state, str(config.to_dict()))
        return
    _log(state, f"global_version: {_colorize(config.global_version or '<unset>', _MAGENTA)}")
    _log(state, f"identity_mode: {_colorize(config.identity_mode, _CYAN)}")
    _log(state, f"project_versions: {_colorize(str(len(config.project_versions)), _BLUE)}")


def _action_identity_mode(state: UiState) -> None:
    config = load_config()
    _log(state, f"current identity_mode: {_colorize(config.identity_mode, _CYAN)}")
    mode = _ask("Set new mode (id-file-first/path-only, blank to keep)", "")
    if not mode:
        return
    if mode not in {"id-file-first", "path-only"}:
        _log(state, _colorize("Invalid identity mode.", _RED))
        return
    config.identity_mode = mode
    save_config(config)
    _log(state, _colorize(f"identity_mode set to: {mode}", _GREEN))


def _action_setup_vscode(state: UiState) -> None:
    detected = find_vscode_settings()
    _log(state, f"Detected settings: {_colorize(str(detected) if detected else '<not found>', _CYAN)}")
    custom = _ask("Custom settings.json path (blank to use detected)", "")
    settings_path = Path(custom) if custom else None
    remove = _ask_yes_no("Remove cmake.cmakePath instead of setting it", default=False)
    try:
        if remove:
            result = remove_vscode_settings(settings_path)
            if result:
                _log(state, _colorize(f"Removed cmake.cmakePath from {result}", _GREEN))
            else:
                _log(state, _colorize("cmake.cmakePath was not set or settings file not found", _YELLOW))
        else:
            result_path, proxy = apply_vscode_settings(settings_path)
            _log(state, _colorize(f"cmake.cmakePath = {proxy}", _GREEN))
            _log(state, _colorize(f"Written to: {result_path}", _GREEN))
    except (FileNotFoundError, ValueError) as exc:
        _log(state, _colorize(f"error: {exc}", _RED))


def run_tui() -> int:
    state = UiState()
    commands = {
        "resolve": _action_resolve,
        "use": _action_use,
        "install": _action_install_url,
        "install-archive": _action_install_archive,
        "list": _action_list_versions,
        "uninstall": _action_uninstall,
        "clear-downloads": _action_clear_downloads,
        "events": _action_events,
        "projects": _action_projects,
        "clean": _action_clean,
        "proxy-run": _action_proxy_run,
        "show-config": _action_show_config,
        "identity-mode": _action_identity_mode,
        "setup-vscode": _action_setup_vscode,
    }

    _log(state, _colorize("Welcome to cmake-ctl. Type /help for commands.", _GREEN + _BOLD))

    while True:
        _render(state)
        raw = input(_colorize("\ncommand> ", _YELLOW)).strip()
        if not raw:
            continue

        parts = raw.split()
        token = parts[0].strip().lower()
        cmd_args = parts[1:]
        if token.startswith("/"):
            token = token[1:]

        state.last_command = f"/{token}"

        if token in {"exit", "q", "quit"}:
            return 0
        if token in {"help", "h"}:
            _menu_help(state)
            continue

        action = commands.get(token)
        if action is None:
            _log(state, _colorize("Unknown command. Use /help to see available commands.", _RED))
            continue

        if token == "projects" and _action_projects_with_args(state, cmd_args):
            continue

        _set_status(state, "running")
        try:
            action(state)
            if state.status == "running":
                _set_status(state, "idle")
        except Exception as exc:  # pragma: no cover - interactive safety net
            _set_status(state, "error")
            _log(state, f"Unhandled error: {exc}")
