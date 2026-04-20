from __future__ import annotations

import hashlib
import json
import platform
import shutil
import tarfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from .paths import DOWNLOADS_DIR, VERSIONS_DIR, ensure_layout


class InstallError(RuntimeError):
    pass


def construct_release_url(version: str) -> str:
    """Construct the default GitHub release asset URL for a CMake version."""
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64", "x64"}:
        arch = "x86_64"
    elif machine in {"arm64", "aarch64"}:
        arch = "aarch64"
    else:
        arch = machine or "x86_64"

    if platform.system().lower().startswith("win"):
        file_name = f"cmake-{version}-windows-{arch}.zip"
    elif platform.system().lower() == "darwin":
        # Kitware publishes universal builds for macOS.
        file_name = f"cmake-{version}-macos-universal.tar.gz"
    else:
        file_name = f"cmake-{version}-linux-{arch}.tar.gz"

    return f"https://github.com/Kitware/CMake/releases/download/v{version}/{file_name}"


def verify_checksum(file_path: Path, expected_sha256: str) -> bool:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected_sha256.lower()


def load_manifest(manifest_path: Path) -> dict:
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def install_version(
    version: str,
    artifact_url: str | None = None,
    manifest_path: Path | None = None,
    expected_sha256: str | None = None,
    activate: bool = True,
    status_callback: Callable[[str, str], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    """Install cmake version from URL, with optional checksum verification."""
    ensure_layout()
    if status_callback:
        status_callback("init", f"Preparing install for CMake {version}")

    if artifact_url is None:
        artifact_url = construct_release_url(version)
    if status_callback:
        status_callback("resolve-url", f"Using URL: {artifact_url}")

    file_name = f"cmake-{version}.pkg"

    if manifest_path is not None:
        manifest = load_manifest(manifest_path)
        if version not in manifest:
            raise InstallError(f"Version {version} not found in manifest")

        expected_sha256 = manifest[version]["sha256"]
        file_name = manifest[version].get("file_name", file_name)
    else:
        parsed = urlparse(artifact_url)
        path_name = Path(parsed.path).name
        if path_name:
            file_name = path_name

    dl_target = DOWNLOADS_DIR / file_name

    def _reporthook(block_count: int, block_size: int, total_size: int) -> None:
        if progress_callback is None:
            return
        downloaded = block_count * block_size
        if total_size > 0:
            downloaded = min(downloaded, total_size)
        progress_callback(downloaded, total_size)

    try:
        if status_callback:
            status_callback("download", f"Downloading to {dl_target}")
        urllib.request.urlretrieve(artifact_url, dl_target, reporthook=_reporthook)
    except urllib.error.URLError as exc:
        if status_callback:
            status_callback("error", f"Download failed: {exc}")
        raise InstallError(f"Network download failed: {exc}") from exc

    if expected_sha256 is not None:
        if status_callback:
            status_callback("verify", "Verifying SHA256 checksum")
        if not verify_checksum(dl_target, expected_sha256):
            dl_target.unlink(missing_ok=True)
            if status_callback:
                status_callback("error", "Checksum verification failed")
            raise InstallError("Checksum verification failed; installation aborted")
        if status_callback:
            status_callback("verify", "Checksum verification passed")

    target = _extract_and_install(version, dl_target, activate=activate, status_callback=status_callback)
    if status_callback:
        status_callback("done", f"Installed at {target}")
    return target


def install_from_archive(
    version: str,
    archive_path: Path | str,
    activate: bool = True,
    status_callback: Callable[[str, str], None] | None = None,
) -> Path:
    """Install cmake version from a local archive file (ZIP, TAR.GZ, etc)."""
    ensure_layout()
    archive_path = Path(archive_path)
    
    if not archive_path.exists():
        raise InstallError(f"Archive file not found: {archive_path}")
    
    if status_callback:
        status_callback("archive", f"Using local archive: {archive_path}")
    target = _extract_and_install(version, archive_path, activate=activate, status_callback=status_callback)
    if status_callback:
        status_callback("done", f"Installed at {target}")
    return target


def _extract_and_install(
    version: str,
    archive_path: Path,
    activate: bool = True,
    status_callback: Callable[[str, str], None] | None = None,
) -> Path:
    """Extract archive and install to versions directory."""
    version_dir_tmp = VERSIONS_DIR / f".{version}.tmp"
    version_dir = VERSIONS_DIR / version

    if status_callback:
        status_callback("extract", f"Preparing extraction for version {version}")
    
    # Clean up any existing temp directory
    if version_dir_tmp.exists():
        _remove_tree(version_dir_tmp)
    version_dir_tmp.mkdir(parents=True, exist_ok=True)
    
    try:
        # Handle ZIP files
        if archive_path.suffix.lower() == ".zip":
            if status_callback:
                status_callback("extract", "Extracting ZIP archive")
            with zipfile.ZipFile(archive_path, "r") as zf:
                _safe_extract_zip(zf, version_dir_tmp)
        # Handle other archives with shutil
        else:
            if status_callback:
                status_callback("extract", "Extracting archive")
            _safe_extract_archive(archive_path, version_dir_tmp)
    except Exception as exc:
        _remove_tree(version_dir_tmp)
        if status_callback:
            status_callback("error", f"Extraction failed: {exc}")
        raise InstallError(f"Failed to extract archive: {exc}") from exc
    
    # If extraction created a single root folder, flatten it
    contents = list(version_dir_tmp.iterdir())
    if len(contents) == 1 and contents[0].is_dir():
        # Move the contents of the single folder up one level
        inner_dir = contents[0]
        for item in inner_dir.iterdir():
            item.replace(version_dir_tmp / item.name)
        inner_dir.rmdir()
    
    # Atomically replace existing version
    if version_dir.exists():
        if status_callback:
            status_callback("activate", "Replacing existing version directory")
        _remove_tree(version_dir)
    version_dir_tmp.replace(version_dir)
    
    if activate:
        if status_callback:
            status_callback("activate", "Writing ACTIVE marker")
        (version_dir / "ACTIVE").write_text("1\n", encoding="utf-8")
    
    return version_dir


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            child.rmdir()
    path.rmdir()


def _is_within_directory(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_extract_zip(zf: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in zf.infolist():
        member_path = (destination / member.filename).resolve()
        if not _is_within_directory(member_path, root):
            raise InstallError(f"Unsafe archive entry: {member.filename}")
    zf.extractall(destination)


def _safe_extract_archive(archive_path: Path, destination: Path) -> None:
    suffixes = [s.lower() for s in archive_path.suffixes]
    if any(s in {".tar", ".tgz", ".tbz", ".tbz2", ".txz", ".gz", ".bz2", ".xz"} for s in suffixes):
        with tarfile.open(archive_path) as tf:
            root = destination.resolve()
            for member in tf.getmembers():
                member_path = (destination / member.name).resolve()
                if not _is_within_directory(member_path, root):
                    raise InstallError(f"Unsafe archive entry: {member.name}")
            tf.extractall(destination)
        return
    shutil.unpack_archive(archive_path, destination)
