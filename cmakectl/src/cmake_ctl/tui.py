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
from .project_tracker import process_event
from .proxy import run_proxy
from .resolver import (
    reconcile_project_path,
    resolve_version,
    set_global_version,
    set_project_version,
)
from .session_store import SessionStore, current_session_id
from .source_discovery import discover_source_dir


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
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else (default or "")


def _ask_yes_no(prompt: str, default: bool = False) -> bool:
    default_token = "Y/n" if default else "y/N"
    value = input(f"{prompt} ({default_token}): ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def _render(state: UiState) -> None:
    _clear_screen()
    cols, rows = shutil.get_terminal_size((120, 40))
    sep = "-" * cols

    config = load_config()
    print("cmake-ctl TUI")
    print(f"cwd: {Path.cwd().as_posix()}")
    print(f"status: {state.status}")
    print(f"last command: {state.last_command}")
    print(f"global_version: {config.global_version or '<unset>'} | identity_mode: {config.identity_mode}")
    print(sep)
    print("Commands: /resolve /use /install /install-archive /list /events /projects /clean /proxy-run /show-config /identity-mode /help /exit /q")
    print(sep)
    print("Output")

    output_height = max(8, rows - 11)
    visible = state.logs[-output_height:]
    for line in visible:
        print(line[:cols])


def _menu_help(state: UiState) -> None:
    _log(state, "Available commands:")
    _log(state, "  /resolve")
    _log(state, "  /use")
    _log(state, "  /install")
    _log(state, "  /install-archive")
    _log(state, "  /list")
    _log(state, "  /events")
    _log(state, "  /projects")
    _log(state, "  /clean")
    _log(state, "  /proxy-run")
    _log(state, "  /show-config")
    _log(state, "  /identity-mode")
    _log(state, "  /exit or /q")


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
        print("cmake-ctl TUI - version selector")
        print("Use Up/Down to select, Enter to set global version, q or Esc to cancel")
        print("")
        for idx, version in enumerate(versions):
            pointer = ">" if idx == cursor else " "
            marker = "*" if version == current else " "
            print(f"{pointer} {marker} {version}")

        key = _read_key()
        if key == "UP":
            cursor = (cursor - 1) % len(versions)
        elif key == "DOWN":
            cursor = (cursor + 1) % len(versions)
        elif key == "ENTER":
            return versions[cursor]
        elif key in {"ESC", "q", "Q"}:
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
        _log(state, "Project path metadata reconciled for moved project.")

    result = resolve_version(source_path, session_id=current_session_id(), config=config)
    _log(state, f"version={result.version}")
    _log(state, f"source={result.source}")
    _log(state, f"project_key={result.project_identity.key}")
    _log(state, f"source_dir={source_path.as_posix()}")


def _action_use(state: UiState) -> None:
    version = _ask("Version to set")
    if not version:
        _log(state, "No version entered.")
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
        _log(state, f"Session override set: {version} for {identity.key}")
        return

    if mode == "project":
        project = _ask("Project path", ".")
        _, identity = set_project_version(version, Path(project), config=config)
        _log(state, f"Project version set: {version} for {identity.key}")
        return

    set_global_version(version, config=config)
    _log(state, "Global version updated. Already-open terminals will use this version on the next cmake invocation.")


def _action_install_url(state: UiState) -> None:
    version = _ask("Version to install")
    url = _ask("Artifact URL (optional; auto-constructed when empty)", "")
    manifest = _ask("Manifest path (optional)", "")
    sha256 = _ask("SHA256 (optional)", "")
    if not version:
        _log(state, "Version is required.")
        return

    if not url:
        url = construct_release_url(version)
        _log(state, f"auto-url: {url}")

    last_percent = -1

    def _status(step: str, detail: str) -> None:
        _set_status(state, f"{step}")
        _log(state, f"[{step}] {detail}")
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
        _log(state, f"[download] {pct}% ({downloaded}/{total} bytes)")
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
        _log(state, f"install error: {exc}")
        return

    if not manifest and not sha256:
        _log(state, "warning: installed without checksum verification")
    _log(state, f"installed: {target.as_posix()}")
    _set_status(state, "done")


def _action_install_archive(state: UiState) -> None:
    version = _ask("Version to install as")
    archive = _ask("Archive path")
    if not version or not archive:
        _log(state, "Version and archive path are required.")
        return

    def _status(step: str, detail: str) -> None:
        _set_status(state, step)
        _log(state, f"[{step}] {detail}")
        _render(state)

    try:
        target = install_from_archive(version, archive, status_callback=_status)
    except InstallError as exc:
        _set_status(state, "error")
        _log(state, f"install error: {exc}")
        return

    _log(state, f"installed: {target.as_posix()}")
    _set_status(state, "done")


def _action_list_versions(state: UiState) -> None:
    from .paths import VERSIONS_DIR

    if not VERSIONS_DIR.exists():
        _log(state, "No versions installed")
        return

    versions = sorted([p.name for p in VERSIONS_DIR.iterdir() if p.is_dir()])
    if not versions:
        _log(state, "No versions installed")
        return

    current = load_config().global_version
    selected = _select_version_with_arrows(state, versions, current)
    _render(state)
    if not selected:
        _log(state, "Version selection canceled")
        return

    set_global_version(selected)
    _log(state, f"Selected and set global version: {selected}")


def _action_events(state: UiState) -> None:
    metrics = process_events(process_event)
    _log(state, json.dumps(metrics, indent=2, sort_keys=True))


def _action_projects(state: UiState) -> None:
    sub_action = _ask("projects action: list/pin/unpin", "list").lower()
    if sub_action == "pin":
        key = _ask("Project key to pin")
        if key:
            set_pinned(key, True)
            _log(state, f"Pinned: {key}")
    elif sub_action == "unpin":
        key = _ask("Project key to unpin")
        if key:
            set_pinned(key, False)
            _log(state, f"Unpinned: {key}")

    rows = list_projects()
    if not rows:
        _log(state, "No tracked projects")
        return

    for row in rows:
        pin_mark = "pinned" if row["pinned"] else "unpinned"
        _log(state, f"{row['project_key']} {row['cmake_version']} {pin_mark} {row['path']}")


def _action_clean(state: UiState) -> None:
    project = _ask("Project root", ".")
    build_dir = _ask("Build directory (optional)", "")
    archive_dir = _ask("Archive manifest directory (optional)", "")
    pinned = _ask_yes_no("Treat project as pinned", default=False)
    execute = _ask_yes_no("Execute deletion (if No: preview only)", default=False)

    plan = plan_cleanup(Path(project), Path(build_dir) if build_dir else None)
    result = execute_cleanup(
        plan,
        Path(project),
        pinned=pinned,
        dry_run=not execute,
        archive_dir=Path(archive_dir) if archive_dir else None,
    )
    _log(state, f"targets={len(plan.targets)}")
    _log(state, f"bytes={plan.bytes_reclaimable}")
    _log(state, f"deleted={result['deleted']}")
    _log(state, f"skipped_pinned={result['skipped_pinned']}")
    _log(state, f"archived={result['archived']}")


def _action_proxy_run(state: UiState) -> None:
    raw = _ask("cmake args to pass through (space-separated)", "")
    args = raw.split() if raw else []
    exit_code = run_proxy(args, project_path=Path.cwd())
    _log(state, f"proxy exit code: {exit_code}")


def _action_show_config(state: UiState) -> None:
    raw = _ask_yes_no("Show raw config dict", default=False)
    config = load_config()
    if raw:
        _log(state, config.to_dict())
        return
    _log(state, f"global_version: {config.global_version or '<unset>'}")
    _log(state, f"identity_mode: {config.identity_mode}")
    _log(state, f"project_versions: {len(config.project_versions)}")


def _action_identity_mode(state: UiState) -> None:
    config = load_config()
    _log(state, f"current identity_mode: {config.identity_mode}")
    mode = _ask("Set new mode (id-file-first/path-only, blank to keep)", "")
    if not mode:
        return
    if mode not in {"id-file-first", "path-only"}:
        _log(state, "Invalid identity mode.")
        return
    config.identity_mode = mode
    save_config(config)
    _log(state, f"identity_mode set to: {mode}")


def run_tui() -> int:
    state = UiState()
    commands = {
        "resolve": _action_resolve,
        "use": _action_use,
        "install": _action_install_url,
        "install-archive": _action_install_archive,
        "list": _action_list_versions,
        "events": _action_events,
        "projects": _action_projects,
        "clean": _action_clean,
        "proxy-run": _action_proxy_run,
        "show-config": _action_show_config,
        "identity-mode": _action_identity_mode,
    }

    _log(state, "Welcome to cmake-ctl. Type /help for commands.")

    while True:
        _render(state)
        raw = input("\ncommand> ").strip()
        if not raw:
            continue

        token = raw.split()[0].strip().lower()
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
            _log(state, "Unknown command. Use /help to see available commands.")
            continue

        _set_status(state, "running")
        try:
            action(state)
            if state.status == "running":
                _set_status(state, "idle")
        except Exception as exc:  # pragma: no cover - interactive safety net
            _set_status(state, "error")
            _log(state, f"Unhandled error: {exc}")
