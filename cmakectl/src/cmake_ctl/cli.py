from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cleaner import execute_cleanup, plan_cleanup
from .config_store import load_config, save_config
from .database import list_projects, set_pinned
from .events import process_events
from .installer import InstallError, install_version, install_from_archive
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

    install_parser = sub.add_parser("install", help="Install a version from URL")
    install_parser.add_argument("version", help="Version to install")
    install_parser.add_argument("--url", required=True, help="Artifact URL")
    install_parser.add_argument("--manifest", help="Optional manifest JSON path for checksum validation")
    install_parser.add_argument("--sha256", help="Optional SHA256 checksum for direct validation")

    install_archive_parser = sub.add_parser("install-archive", help="Install version from local archive (ZIP/TAR)")
    install_archive_parser.add_argument("version", help="Version to install as")
    install_archive_parser.add_argument("--archive", required=True, help="Path to archive file (ZIP, TAR.GZ, etc)")

    sub.add_parser("list", help="List installed versions")

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


def _cmd_install(version: str, artifact_url: str, manifest: str | None, sha256: str | None) -> int:
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

    rows = list_projects()
    if not rows:
        print("No tracked projects")
        return 0

    for r in rows:
        pin_mark = "pinned" if r["pinned"] else "unpinned"
        print(f"{r['project_key']} {r['cmake_version']} {pin_mark} {r['path']}")
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
    if args.command == "tui":
        return run_tui()

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
