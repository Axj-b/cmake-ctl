from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cleaner import execute_cleanup, plan_cleanup
from .config_store import load_config, save_config
from .database import list_projects, set_pinned
from .events import process_events
from .installer import InstallError, construct_release_url, install_version, install_from_archive
from .project_tracker import process_event
from .proxy import run_proxy
from .resolver import (
    latest_installed_version,
    reconcile_project_path,
    resolve_version,
    set_global_version,
    set_project_version,
)
from .source_discovery import discover_source_dir
from .session_store import SessionStore, current_session_id
from .tui import run_tui
from .vscode_setup import apply_vscode_settings, remove_vscode_settings

_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
_MAGENTA = "\033[95m"
_CYAN = "\033[96m"
_WHITE = "\033[97m"


def _colorize(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cmake-ctl")
    sub = parser.add_subparsers(dest="command", required=True)

    use_parser = sub.add_parser("use", help="Set global/project/session version")
    use_parser.add_argument("version", help="CMake version")
    use_parser.add_argument("--project", default=None, help="Project path")
    use_parser.add_argument("--session", action="store_true", help="Set session-only override")

    resolve_parser = sub.add_parser("resolve", help="Resolve active version for a project")
    resolve_parser.add_argument("--project", default=".", help="Project path")
    resolve_parser.add_argument("cmake_args", nargs="*", help="Optional cmake args for source discovery")

    install_parser = sub.add_parser("install", help="Install a version (URL optional; defaults to GitHub release asset)")
    install_parser.add_argument("version", help="Version to install")
    install_parser.add_argument("--url", help="Artifact URL; if omitted, URL is auto-constructed from version")
    install_parser.add_argument("--manifest", help="Optional manifest JSON path for checksum validation")
    install_parser.add_argument("--sha256", help="Optional SHA256 checksum for direct validation")

    install_archive_parser = sub.add_parser("install-archive", help="Install version from local archive (ZIP/TAR)")
    install_archive_parser.add_argument("version", help="Version to install as")
    install_archive_parser.add_argument("--archive", required=True, help="Path to archive file (ZIP, TAR.GZ, etc)")

    sub.add_parser("list", help="List installed versions")

    uninstall_parser = sub.add_parser("uninstall", help="Remove an installed cmake version")
    uninstall_parser.add_argument("version", nargs="?", help="Version to remove (interactive if omitted)")
    uninstall_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    sub.add_parser("clear-downloads", help="Delete all cached download archives")

    events_parser = sub.add_parser("events", help="Process proxy event queue")
    events_parser.add_argument("--process", action="store_true", help="Process queued events")

    projects_parser = sub.add_parser("projects", help="List tracked projects")
    projects_parser.add_argument("--pin", help="Pin project key")
    projects_parser.add_argument("--unpin", help="Unpin project key")

    clean_parser = sub.add_parser("clean", help="Safe cleanup")
    clean_parser.add_argument("--project", default=".", help="Project root")
    clean_parser.add_argument("--build-dir", help="Build directory")
    clean_parser.add_argument("--archive-dir", help="Write archive manifest before deletion")
    clean_parser.add_argument("--execute", action="store_true", help="Perform deletion (default is preview)")
    clean_parser.add_argument("--pinned", action="store_true", help="Treat project as pinned and skip")

    proxy_parser = sub.add_parser("proxy-run", help="Run cmake via proxy pass-through")
    proxy_parser.add_argument("cmake_args", nargs=argparse.REMAINDER, help="Arguments passed through to cmake")

    show_parser = sub.add_parser("show-config", help="Print current config")
    show_parser.add_argument("--json", action="store_true", help="Print raw JSON-like dict")

    sub.add_parser("tui", help="Launch interactive terminal UI")

    setup_vscode_parser = sub.add_parser("setup-vscode", help="Write cmake.cmakePath into VSCode user settings.json")
    setup_vscode_parser.add_argument("--settings", default=None, help="Path to settings.json (auto-detected if omitted)")
    setup_vscode_parser.add_argument("--remove", action="store_true", help="Remove cmake.cmakePath from VSCode settings")

    mode_parser = sub.add_parser("identity-mode", help="Get or set identity mode")
    mode_parser.add_argument("mode", nargs="?", choices=["id-file-first", "path-only"], help="Identity mode")

    return parser


def _cmd_use(version: str, project: str | None, session_only: bool) -> int:
    project_path = Path(project or ".")
    config = load_config()

    if session_only:
        session_id = current_session_id()
        sessions = SessionStore.load()
        identity = resolve_version(project_path, session_id=None, config=config, sessions=sessions).project_identity
        sessions.set_override(session_id, identity.key, version)
        sessions.save()
        print(f"Session override set: {version} for {identity.key}")
        return 0

    if project is not None:
        _, identity = set_project_version(version, project_path, config=config)
        print(f"Project version set: {version} for {identity.key}")
        return 0

    set_global_version(version, config=config)
    print(
        "Global version updated. Already-open terminals will use this version on the next cmake invocation."
    )
    return 0


def _cmd_resolve(project: str, cmake_args: list[str]) -> int:
    project_path = Path(project)
    config = load_config()
    source_path = discover_source_dir(cmake_args, cwd=project_path)
    updated = reconcile_project_path(project_path, config=config)
    if updated:
        print("Project path metadata reconciled for moved project.")

    result = resolve_version(source_path, session_id=current_session_id(), config=config)
    print(f"version={result.version}")
    print(f"source={result.source}")
    print(f"project_key={result.project_identity.key}")
    print(f"source_dir={source_path.as_posix()}")
    return 0


def _cmd_install(version: str, artifact_url: str | None, manifest: str | None, sha256: str | None) -> int:
    if not artifact_url:
        artifact_url = construct_release_url(version)
        print(f"auto-url: {artifact_url}")

    try:
        target = install_version(
            version,
            artifact_url,
            manifest_path=Path(manifest) if manifest else None,
            expected_sha256=sha256,
        )
    except InstallError as exc:
        print(f"install error: {exc}")
        return 1

    if not manifest and not sha256:
        print("warning: installed without checksum verification")

    print(f"installed: {target.as_posix()}")
    return 0


def _cmd_install_archive(version: str, archive: str) -> int:
    try:
        target = install_from_archive(version, archive)
    except InstallError as exc:
        print(f"install error: {exc}")
        return 1
    print(f"installed: {target.as_posix()}")
    return 0


def _cmd_list() -> int:
    versions_dir = Path(load_config().to_dict().get("versions_dir", ""))
    _ = versions_dir  # Keep config parsing stable; actual listing comes from resolver helper.
    versions: list[str] = []
    from .paths import VERSIONS_DIR

    if VERSIONS_DIR.exists():
        versions = sorted([p.name for p in VERSIONS_DIR.iterdir() if p.is_dir()])

    if not versions:
        print("No versions installed")
        return 0
    for v in versions:
        marker = "*" if latest_installed_version() == v else " "
        print(f"{marker} {v}")
    return 0


def _cmd_events(process_flag: bool) -> int:
    if not process_flag:
        print("Use --process to process queued events")
        return 0

    metrics = process_events(process_event)
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


def _cmd_projects(pin: str | None, unpin: str | None) -> int:
    if pin:
        set_pinned(pin, True)
    if unpin:
        set_pinned(unpin, False)

    # Keep project list fresh when user has run cmake through proxy recently.
    process_events(process_event)

    rows = list_projects()
    if not rows:
        print("No tracked projects")
        return 0

    print(_colorize(f"\n  {len(rows)} tracked project(s)", _BOLD + _WHITE))
    for i, r in enumerate(rows, 1):
        pin_mark = _colorize("● pinned", _GREEN) if r["pinned"] else _colorize("○ unpinned", _YELLOW)
        generator = r.get("generator") or ""

        print()
        print(f"  {_colorize(str(i) + '.', _BOLD + _WHITE)} {_colorize(r['project_key'], _BOLD + _CYAN)}")
        print(f"  {_colorize('•', _WHITE)} path      : {_colorize(r['path'], _BLUE)}")
        print(f"  {_colorize('•', _WHITE)} cmake     : {_colorize(r['cmake_version'], _MAGENTA)}")
        if generator:
            print(f"  {_colorize('•', _WHITE)} generator : {_colorize(generator, _WHITE)}")
        print(f"  {_colorize('•', _WHITE)} status    : {pin_mark}")
    return 0


def _cmd_clean(
    project: str,
    build_dir: str | None,
    archive_dir: str | None,
    execute: bool,
    pinned: bool,
) -> int:
    root = Path(project)
    plan = plan_cleanup(root, Path(build_dir) if build_dir else None)
    dry_run = not execute
    result = execute_cleanup(
        plan,
        root,
        pinned=pinned,
        dry_run=dry_run,
        archive_dir=Path(archive_dir) if archive_dir else None,
    )
    print(f"targets={len(plan.targets)}")
    print(f"bytes={plan.bytes_reclaimable}")
    print(f"deleted={result['deleted']}")
    print(f"skipped_pinned={result['skipped_pinned']}")
    print(f"archived={result['archived']}")
    return 0


def _cmd_proxy_run(cmake_args: list[str]) -> int:
    args = cmake_args[:] if cmake_args else []
    if args and args[0] == "--":
        args = args[1:]
    return run_proxy(args, project_path=Path.cwd())


def _cmd_show_config(raw: bool) -> int:
    config = load_config()
    if raw:
        print(config.to_dict())
        return 0

    print(f"global_version: {config.global_version or '<unset>'}")
    print(f"identity_mode: {config.identity_mode}")
    print(f"project_versions: {len(config.project_versions)}")
    return 0


def _cmd_setup_vscode(settings: str | None, remove: bool) -> int:
    from pathlib import Path as _Path
    settings_path = _Path(settings) if settings else None
    try:
        if remove:
            result_path = remove_vscode_settings(settings_path)
            if result_path:
                print(f"Removed cmake.cmakePath from {result_path}")
            else:
                print("cmake.cmakePath was not set or settings file not found")
        else:
            result_path, proxy = apply_vscode_settings(settings_path)
            print(f"cmake.cmakePath = {proxy}")
            print(f"Written to: {result_path}")
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    return 0


def _cmd_uninstall(version: str | None, yes: bool) -> int:
    from .paths import VERSIONS_DIR
    from .resolver import is_installed_version

    if not version:
        versions = sorted([p.name for p in VERSIONS_DIR.iterdir() if p.is_dir()]) if VERSIONS_DIR.exists() else []
        if not versions:
            print("No versions installed")
            return 0
        print("Installed versions:")
        for v in versions:
            print(f"  {v}")
        version = input("Version to remove: ").strip()
        if not version:
            print("Aborted")
            return 0

    if not is_installed_version(version):
        print(f"Version not installed: {version}")
        return 1

    target = VERSIONS_DIR / version
    if not yes:
        confirm = input(f"Remove {target}? [y/N]: ").strip().lower()
        if confirm not in {"y", "yes"}:
            print("Aborted")
            return 0

    import shutil
    shutil.rmtree(target)
    print(f"Removed: {version}")

    # Clear from global config if it was the active version
    config = load_config()
    if config.global_version == version:
        config.global_version = None
        save_config(config)
        print("Cleared global_version (was set to the removed version)")
    return 0


def _cmd_clear_downloads() -> int:
    from .paths import DOWNLOADS_DIR
    import shutil
    if not DOWNLOADS_DIR.exists() or not any(DOWNLOADS_DIR.iterdir()):
        print("Downloads folder is already empty")
        return 0
    files = list(DOWNLOADS_DIR.iterdir())
    total = sum(f.stat().st_size for f in files if f.is_file())
    print(f"{len(files)} file(s), {total / (1024*1024):.1f} MB")
    confirm = input("Delete all downloads? [y/N]: ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("Aborted")
        return 0
    shutil.rmtree(DOWNLOADS_DIR)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloads folder cleared")
    return 0


def _cmd_identity_mode(mode: str | None) -> int:
    config = load_config()
    if mode is None:
        print(config.identity_mode)
        return 0

    config.identity_mode = mode
    save_config(config)
    print(f"identity_mode set to: {mode}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "use":
        return _cmd_use(args.version, args.project, args.session)
    if args.command == "resolve":
        return _cmd_resolve(args.project, args.cmake_args)
    if args.command == "install":
        return _cmd_install(args.version, args.url, args.manifest, args.sha256)
    if args.command == "install-archive":
        return _cmd_install_archive(args.version, args.archive)
    if args.command == "list":
        return _cmd_list()
    if args.command == "events":
        return _cmd_events(args.process)
    if args.command == "projects":
        return _cmd_projects(args.pin, args.unpin)
    if args.command == "clean":
        return _cmd_clean(args.project, args.build_dir, args.archive_dir, args.execute, args.pinned)
    if args.command == "proxy-run":
        return _cmd_proxy_run(args.cmake_args)
    if args.command == "show-config":
        return _cmd_show_config(args.json)
    if args.command == "identity-mode":
        return _cmd_identity_mode(args.mode)
    if args.command == "uninstall":
        return _cmd_uninstall(args.version, args.yes)
    if args.command == "clear-downloads":
        return _cmd_clear_downloads()
    if args.command == "tui":
        return run_tui()
    if args.command == "setup-vscode":
        return _cmd_setup_vscode(args.settings, args.remove)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
