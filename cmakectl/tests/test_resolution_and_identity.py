from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_helpers import isolated_home


class ResolutionAndIdentityTests(unittest.TestCase):
    def test_resolution_precedence_session_over_project_file_global(self):
        with isolated_home() as home:
            from cmake_ctl.config_store import Config, save_config
            from cmake_ctl.identity import ensure_project_id, resolve_project_identity
            from cmake_ctl.paths import VERSIONS_DIR
            from cmake_ctl.resolver import resolve_version
            from cmake_ctl.session_store import SessionStore

            for v in ["3.25.0", "3.26.0", "3.27.0", "3.28.0"]:
                (VERSIONS_DIR / v).mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory() as td:
                proj = Path(td)
                (proj / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")
                (proj / ".cmake-version").write_text("3.26.0\n", encoding="utf-8")

                pid = ensure_project_id(proj)
                identity = resolve_project_identity(proj, "id-file-first", create_if_missing=False)
                cfg = Config(global_version="3.25.0", identity_mode="id-file-first")
                cfg.project_versions[identity.key] = "3.27.0"
                cfg.project_paths[pid] = proj.as_posix()
                save_config(cfg)

                sessions = SessionStore.load()
                sessions.set_override("s1", identity.key, "3.28.0")
                sessions.save()

                resolved = resolve_version(proj, session_id="s1")
                self.assertEqual(resolved.version, "3.28.0")
                self.assertEqual(resolved.source, "session")

    def test_project_move_reconciles_path_in_id_file_first_mode(self):
        with isolated_home() as home:
            from cmake_ctl.config_store import Config, load_config, save_config
            from cmake_ctl.identity import ensure_project_id, resolve_project_identity
            from cmake_ctl.paths import VERSIONS_DIR
            from cmake_ctl.resolver import reconcile_project_path, set_project_version

            (VERSIONS_DIR / "3.29.0").mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory() as td:
                old = Path(td) / "old"
                new = Path(td) / "new"
                old.mkdir(parents=True, exist_ok=True)
                (old / "CMakeLists.txt").write_text("project(x)\n", encoding="utf-8")
                pid = ensure_project_id(old)

                cfg = Config(global_version="3.29.0", identity_mode="id-file-first")
                save_config(cfg)
                set_project_version("3.29.0", old)

                new.mkdir(parents=True, exist_ok=True)
                (old / ".cmake-ctl").rename(new / ".cmake-ctl")
                (old / "CMakeLists.txt").rename(new / "CMakeLists.txt")

                changed = reconcile_project_path(new)
                self.assertTrue(changed)
                cfg2 = load_config()
                self.assertEqual(cfg2.project_paths[pid], new.resolve().as_posix())

    def test_global_switch_applies_on_next_invocation(self):
        with isolated_home():
            from cmake_ctl.config_store import Config, save_config
            from cmake_ctl.paths import VERSIONS_DIR
            from cmake_ctl.resolver import resolve_version

            (VERSIONS_DIR / "3.28.0").mkdir(parents=True, exist_ok=True)
            (VERSIONS_DIR / "3.29.0").mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory() as td:
                proj = Path(td)
                (proj / "CMakeLists.txt").write_text("project(g)\n", encoding="utf-8")

                save_config(Config(global_version="3.28.0", identity_mode="path-only"))
                first = resolve_version(proj)
                self.assertEqual(first.version, "3.28.0")

                save_config(Config(global_version="3.29.0", identity_mode="path-only"))
                second = resolve_version(proj)
                self.assertEqual(second.version, "3.29.0")

    def test_missing_managed_version_fails_actionably(self):
        with isolated_home():
            from cmake_ctl.config_store import Config, save_config
            from cmake_ctl.resolver import resolve_version

            with tempfile.TemporaryDirectory() as td:
                proj = Path(td)
                (proj / "CMakeLists.txt").write_text("project(y)\n", encoding="utf-8")
                save_config(Config(global_version="9.9.9", identity_mode="path-only"))
                with self.assertRaises(RuntimeError) as ctx:
                    resolve_version(proj)
                self.assertIn("not installed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
