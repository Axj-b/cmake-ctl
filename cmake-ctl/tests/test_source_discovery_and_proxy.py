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

    def test_native_proxy_invokes_tool_and_honors_recursion_guard(self):
        with isolated_home():
            native_proxy_mod = import_module("cmake-ctl.native_proxy")

            RECURSION_ENV = native_proxy_mod.RECURSION_ENV
            ProxyError = native_proxy_mod.ProxyError
            run_native_proxy = native_proxy_mod.run_native_proxy

            with tempfile.TemporaryDirectory() as td:
                proj = Path(td)
                (proj / "CMakeLists.txt").write_text("project(z)\n", encoding="utf-8")

                with mock.patch.object(native_proxy_mod, "_resolve_proxy_binary") as resolve_mock:
                    cmake_bin = proj / ("cmake.exe" if os.name == "nt" else "cmake")
                    cmake_bin.write_text("stub", encoding="utf-8")
                    resolve_mock.return_value = cmake_bin
                    with mock.patch.object(native_proxy_mod.subprocess, "run") as run_mock:
                        run_mock.return_value.returncode = 7
                        rc = run_native_proxy(["--version"], project_path=proj, tool_name="cmake")
                        self.assertEqual(rc, 7)
                        args = run_mock.call_args.args[0]
                        self.assertEqual(Path(args[0]).resolve(), cmake_bin.resolve())

                with mock.patch.object(native_proxy_mod, "_resolve_proxy_binary") as resolve_mock:
                    ctest_bin = proj / ("ctest.exe" if os.name == "nt" else "ctest")
                    ctest_bin.write_text("stub", encoding="utf-8")
                    resolve_mock.return_value = ctest_bin
                    with mock.patch.object(native_proxy_mod.subprocess, "run") as run_mock:
                        run_mock.return_value.returncode = 0
                        rc = run_native_proxy(["--version"], project_path=proj, tool_name="ctest")
                        self.assertEqual(rc, 0)
                        args = run_mock.call_args.args[0]
                        self.assertEqual(Path(args[0]).resolve(), ctest_bin.resolve())

                with mock.patch.object(native_proxy_mod, "_resolve_proxy_binary") as resolve_mock:
                    cmake_bin = proj / ("cmake.exe" if os.name == "nt" else "cmake")
                    cmake_bin.write_text("stub", encoding="utf-8")
                    resolve_mock.return_value = cmake_bin
                    with mock.patch.object(native_proxy_mod.subprocess, "run") as run_mock:
                        run_mock.return_value.returncode = 7
                        rc = run_native_proxy(["--version"], project_path=proj, tool_name="cmake")
                        self.assertEqual(rc, 7)

                os.environ[RECURSION_ENV] = "1"
                try:
                    with self.assertRaises(ProxyError):
                        run_native_proxy(["--version"], project_path=proj, tool_name="cmake")
                finally:
                    os.environ.pop(RECURSION_ENV, None)


if __name__ == "__main__":
    unittest.main()
