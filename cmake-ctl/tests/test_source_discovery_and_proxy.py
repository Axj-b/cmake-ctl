from __future__ import annotations

import os
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest import mock

from test_helpers import isolated_home


class SourceDiscoveryAndProxyTests(unittest.TestCase):
    def test_discover_source_dir_supports_S_and_preset_and_build_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            build = root / "build"
            src.mkdir()
            build.mkdir()
            (src / "CMakeLists.txt").write_text("project(a)\n", encoding="utf-8")
            (build / "CMakeCache.txt").write_text(
                f"CMAKE_HOME_DIRECTORY:INTERNAL={src.as_posix()}\n", encoding="utf-8"
            )
            (src / "CMakePresets.json").write_text(
                '{"version":4,"configurePresets":[{"name":"dev","sourceDir":"."}]}'
            )

            discover_source_dir = import_module("cmake-ctl.source_discovery").discover_source_dir

            self.assertEqual(discover_source_dir(["-S", str(src)], cwd=root), src.resolve())
            self.assertEqual(discover_source_dir(["--preset", "dev"], cwd=src), src.resolve())
            self.assertEqual(discover_source_dir([], cwd=build), src.resolve())

    def test_proxy_uses_absolute_managed_path_and_recursion_guard(self):
        with isolated_home():
            config_mod = import_module("cmake-ctl.config_store")
            paths_mod = import_module("cmake-ctl.paths")
            proxy_mod = import_module("cmake-ctl.proxy")

            Config = config_mod.Config
            save_config = config_mod.save_config
            VERSIONS_DIR = paths_mod.VERSIONS_DIR
            RECURSION_ENV = proxy_mod.RECURSION_ENV
            ProxyError = proxy_mod.ProxyError
            resolve_cmake_executable = proxy_mod.resolve_cmake_executable
            run_proxy = proxy_mod.run_proxy

            ver = "3.28.1"
            exe_dir = VERSIONS_DIR / ver / "bin"
            exe_dir.mkdir(parents=True, exist_ok=True)
            cmake_bin = exe_dir / ("cmake.exe" if os.name == "nt" else "cmake")
            cmake_bin.write_text("stub", encoding="utf-8")

            save_config(Config(global_version=ver, identity_mode="path-only"))

            with tempfile.TemporaryDirectory() as td:
                proj = Path(td)
                (proj / "CMakeLists.txt").write_text("project(z)\n", encoding="utf-8")
                resolved, version, source = resolve_cmake_executable(proj, [])
                self.assertTrue(resolved.is_absolute())
                self.assertEqual(version, ver)

                with mock.patch.object(proxy_mod.subprocess, "run") as run_mock:
                    run_mock.return_value.returncode = 7
                    rc = run_proxy(["--version"], project_path=proj)
                    self.assertEqual(rc, 7)
                    args = run_mock.call_args.args[0]
                    self.assertEqual(Path(args[0]).resolve(), cmake_bin.resolve())

                os.environ[RECURSION_ENV] = "1"
                try:
                    with self.assertRaises(ProxyError):
                        run_proxy(["--version"], project_path=proj)
                finally:
                    os.environ.pop(RECURSION_ENV, None)


if __name__ == "__main__":
    unittest.main()
