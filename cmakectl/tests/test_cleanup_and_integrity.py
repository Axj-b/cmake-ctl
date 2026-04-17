from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from test_helpers import isolated_home


class CleanupAndIntegrityTests(unittest.TestCase):
    def test_cleanup_dry_run_and_safety_and_pinned(self):
        from cmakectl.cleaner import CleanupPlan, execute_cleanup, plan_cleanup

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            build = root / "build"
            build.mkdir()
            f = build / "a.bin"
            f.write_bytes(b"abc")

            plan = plan_cleanup(root, build)
            self.assertGreater(plan.bytes_reclaimable, 0)

            dry = execute_cleanup(plan, root, pinned=False, dry_run=True)
            self.assertEqual(dry["deleted"], 0)
            self.assertTrue(build.exists())

            skipped = execute_cleanup(plan, root, pinned=True, dry_run=False)
            self.assertTrue(skipped["skipped_pinned"])

            archive = root / "archive"
            executed = execute_cleanup(plan, root, pinned=False, dry_run=False, archive_dir=archive)
            self.assertTrue(executed["archived"])
            self.assertTrue(any(p.name.startswith("cleanup-manifest-") for p in archive.glob("*.json")))

            outside_dir = root.parent / "outside-danger"
            outside_dir.mkdir(exist_ok=True)
            unsafe = CleanupPlan(targets=[outside_dir], bytes_reclaimable=0)
            with self.assertRaises(ValueError):
                execute_cleanup(unsafe, root, pinned=False, dry_run=False)

    def test_installer_checksum_and_atomic_activation(self):
        with isolated_home() as home:
            from cmakectl.installer import InstallError, install_version
            from cmakectl.paths import VERSIONS_DIR

            payload = b"hello-cmake"
            src = home / "artifact.bin"
            src.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            bad_digest = "0" * 64

            manifest = home / "manifest.json"
            manifest.write_text(
                "{\n"
                "  \"3.30.0\": {\"sha256\": \"" + digest + "\", \"file_name\": \"artifact.bin\"},\n"
                "  \"9.9.9\": {\"sha256\": \"" + bad_digest + "\", \"file_name\": \"artifact.bin\"}\n"
                "}\n",
                encoding="utf-8",
            )

            target = install_version("3.30.0", src.as_uri(), manifest)
            self.assertTrue((target / "ACTIVE").exists())

            with self.assertRaises(InstallError):
                install_version("9.9.9", src.as_uri(), manifest)
            self.assertFalse((VERSIONS_DIR / "9.9.9").exists())


if __name__ == "__main__":
    unittest.main()
