#!/usr/bin/env python3
"""Create an uncompressed end-user release folder for cmake-ctl.

This script mirrors the staging process used by create_release_zip.py but writes
directly to an output directory instead of creating a zip archive.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from create_release_zip import (
    detect_platform_tag,
    infer_version,
    require_proxy_binary,
    run_build_or_reuse_existing,
    stage_release_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an end-user release folder")
    parser.add_argument("--version", help="Release version label (default: env or dev)")
    parser.add_argument("--platform", help="Platform label (default: auto)")
    parser.add_argument("--out-dir", default="dist", help="Output directory for staged release folder")
    parser.add_argument("--skip-build", action="store_true", help="Do not run build step")
    parser.add_argument("--force", action="store_true", help="Overwrite existing staged folder if it exists")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    version = infer_version(args.version)
    platform = args.platform or detect_platform_tag()
    package_name = f"cmake-ctl-{version}-{platform}"

    if not args.skip_build:
        run_build_or_reuse_existing(repo_root)

    proxy_binary = require_proxy_binary(repo_root)

    out_dir = repo_root / args.out_dir
    stage_root = out_dir / package_name
    if stage_root.exists():
        if not args.force:
            raise SystemExit(
                f"Staged folder already exists: {stage_root}. "
                "Use --force to overwrite it."
            )
        shutil.rmtree(stage_root)

    stage_root.mkdir(parents=True, exist_ok=True)
    stage_release_files(repo_root, stage_root, proxy_binary)

    print(f"Created release folder: {stage_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
