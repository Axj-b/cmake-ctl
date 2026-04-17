from __future__ import annotations

import json
from pathlib import Path

from .cleaner import execute_cleanup, plan_cleanup
from .config_store import load_config, save_config
from .database import list_projects, set_pinned
from .events import process_events
from .installer import InstallError, install_from_archive, install_version
from .project_tracker import process_event
from .proxy import run_proxy
from .resolver import latest_installed_version, reconcile_project_path, resolve_version, set_global_version, set_project_version
from .session_store import SessionStore, current_session_id
from .source_discovery import discover_source_dir


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


def _show_header() -> None:
    config = load_config()
    print("cmake-ctl TUI")
    print(f"cwd: {Path.cwd().as_posix()}")
    print(f"global_version: {config.global_version or '<unset>'}")
    print(f"identity_mode: {config.identity_mode}")


def _menu() -> None:
    print("\nMain Menu")
    print(" 1) Resolve active version")
    print(" 2) Set version (global/project/session)")
    print(" 3) Install from URL")
    print(" 4) Install from local archive")
    print(" 5) List installed versions")
    print(" 6) Process queued events")
    print(" 7) Projects (list/pin/unpin)")
    print(" 8) Clean build artifacts")
    print(" 9) Proxy run cmake args")
    print("10) Show config")
    print("11) Identity mode (get/set)")
    print("12) Exit")


def _action_resolve() -> None:
    project = _ask("Project path", ".")
    raw_args = _ask("Optional cmake args (space-separated)", "")
    cmake_args = raw_args.split() if raw_args else []

    config = load_config()
    project_path = Path(project)
    source_path = discover_source_dir(cmake_args, cwd=project_path)
    updated = reconcile_project_path(project_path, config=config)
    if updated:
        print("Project path metadata reconciled for moved project.")

    result = resolve_version(source_path, session_id=current_session_id(), config=config)
    print(f"version={result.version}")
    print(f"source={result.source}")
    print(f"project_key={result.project_identity.key}")
    print(f"source_dir={source_path.as_posix()}")


def _action_use() -> None:
    version = _ask("Version to set")
    if not version:
        print("No version entered.")
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
        print(f"Session override set: {version} for {identity.key}")
        return

    if mode == "project":
        project = _ask("Project path", ".")
        _, identity = set_project_version(version, Path(project), config=config)
        print(f"Project version set: {version} for {identity.key}")
        return

    set_global_version(version, config=config)
    print("Global version updated. Already-open terminals will use this version on the next cmake invocation.")


def _action_install_url() -> None:
    version = _ask("Version to install")
    url = _ask("Artifact URL")
    manifest = _ask("Manifest path (optional)", "")
    sha256 = _ask("SHA256 (optional)", "")
    if not version or not url:
        print("Version and URL are required.")
        return

    try:
        target = install_version(
            version,
            url,
            manifest_path=Path(manifest) if manifest else None,
            expected_sha256=sha256 or None,
        )
    except InstallError as exc:
        print(f"install error: {exc}")
        return

    if not manifest and not sha256:
        print("warning: installed without checksum verification")
    print(f"installed: {target.as_posix()}")


def _action_install_archive() -> None:
    version = _ask("Version to install as")
    archive = _ask("Archive path")
    if not version or not archive:
        print("Version and archive path are required.")
        return

    try:
        target = install_from_archive(version, archive)
    except InstallError as exc:
        print(f"install error: {exc}")
        return

    print(f"installed: {target.as_posix()}")


def _action_list_versions() -> None:
    from .paths import VERSIONS_DIR

    if not VERSIONS_DIR.exists():
        print("No versions installed")
        return

    versions = sorted([p.name for p in VERSIONS_DIR.iterdir() if p.is_dir()])
    if not versions:
        print("No versions installed")
        return

    active = latest_installed_version()
    for version in versions:
        marker = "*" if active == version else " "
        print(f"{marker} {version}")


def _action_events() -> None:
    metrics = process_events(process_event)
    print(json.dumps(metrics, indent=2, sort_keys=True))


def _action_projects() -> None:
    sub_action = _ask("projects action: list/pin/unpin", "list").lower()
    if sub_action == "pin":
        key = _ask("Project key to pin")
        if key:
            set_pinned(key, True)
    elif sub_action == "unpin":
        key = _ask("Project key to unpin")
        if key:
            set_pinned(key, False)

    rows = list_projects()
    if not rows:
        print("No tracked projects")
        return

    for row in rows:
        pin_mark = "pinned" if row["pinned"] else "unpinned"
        print(f"{row['project_key']} {row['cmake_version']} {pin_mark} {row['path']}")


def _action_clean() -> None:
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
    print(f"targets={len(plan.targets)}")
    print(f"bytes={plan.bytes_reclaimable}")
    print(f"deleted={result['deleted']}")
    print(f"skipped_pinned={result['skipped_pinned']}")
    print(f"archived={result['archived']}")


def _action_proxy_run() -> None:
    raw = _ask("cmake args to pass through (space-separated)", "")
    args = raw.split() if raw else []
    exit_code = run_proxy(args, project_path=Path.cwd())
    print(f"proxy exit code: {exit_code}")


def _action_show_config() -> None:
    raw = _ask_yes_no("Show raw config dict", default=False)
    config = load_config()
    if raw:
        print(config.to_dict())
        return
    print(f"global_version: {config.global_version or '<unset>'}")
    print(f"identity_mode: {config.identity_mode}")
    print(f"project_versions: {len(config.project_versions)}")


def _action_identity_mode() -> None:
    config = load_config()
    print(f"current identity_mode: {config.identity_mode}")
    mode = _ask("Set new mode (id-file-first/path-only, blank to keep)", "")
    if not mode:
        return
    if mode not in {"id-file-first", "path-only"}:
        print("Invalid identity mode.")
        return
    config.identity_mode = mode
    save_config(config)
    print(f"identity_mode set to: {mode}")


def run_tui() -> int:
    while True:
        _show_header()
        _menu()
        choice = input("Select an option: ").strip()

        if choice == "1":
            _action_resolve()
        elif choice == "2":
            _action_use()
        elif choice == "3":
            _action_install_url()
        elif choice == "4":
            _action_install_archive()
        elif choice == "5":
            _action_list_versions()
        elif choice == "6":
            _action_events()
        elif choice == "7":
            _action_projects()
        elif choice == "8":
            _action_clean()
        elif choice == "9":
            _action_proxy_run()
        elif choice == "10":
            _action_show_config()
        elif choice == "11":
            _action_identity_mode()
        elif choice == "12":
            return 0
        else:
            print("Unknown option.")
