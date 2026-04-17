from __future__ import annotations

import hashlib
import json
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from .paths import DOWNLOADS_DIR, VERSIONS_DIR, ensure_layout


class InstallError(RuntimeError):
    pass


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
    artifact_url: str,
    manifest_path: Path | None = None,
    expected_sha256: str | None = None,
    activate: bool = True,
) -> Path:
    """Install cmake version from URL, with optional checksum verification."""
    ensure_layout()
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
    try:
        urllib.request.urlretrieve(artifact_url, dl_target)
    except urllib.error.URLError as exc:
        raise InstallError(f"Network download failed: {exc}") from exc

    if expected_sha256 is not None:
        if not verify_checksum(dl_target, expected_sha256):
            dl_target.unlink(missing_ok=True)
            raise InstallError("Checksum verification failed; installation aborted")

    return _extract_and_install(version, dl_target, activate=activate)


def install_from_archive(version: str, archive_path: Path | str, activate: bool = True) -> Path:
    """Install cmake version from a local archive file (ZIP, TAR.GZ, etc)."""
    ensure_layout()
    archive_path = Path(archive_path)
    
    if not archive_path.exists():
        raise InstallError(f"Archive file not found: {archive_path}")
    
    return _extract_and_install(version, archive_path, activate=activate)


def _extract_and_install(version: str, archive_path: Path, activate: bool = True) -> Path:
    """Extract archive and install to versions directory."""
    version_dir_tmp = VERSIONS_DIR / f".{version}.tmp"
    version_dir = VERSIONS_DIR / version
    
    # Clean up any existing temp directory
    if version_dir_tmp.exists():
        _remove_tree(version_dir_tmp)
    version_dir_tmp.mkdir(parents=True, exist_ok=True)
    
    try:
        # Handle ZIP files
        if archive_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(version_dir_tmp)
        # Handle other archives with shutil
        else:
            shutil.unpack_archive(archive_path, version_dir_tmp)
    except Exception as exc:
        _remove_tree(version_dir_tmp)
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
        _remove_tree(version_dir)
    version_dir_tmp.replace(version_dir)
    
    if activate:
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
