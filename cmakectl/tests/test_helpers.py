from __future__ import annotations

import importlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

MODULES = [
    "cmake_ctl.paths",
    "cmake_ctl.config_store",
    "cmake_ctl.identity",
    "cmake_ctl.session_store",
    "cmake_ctl.resolver",
    "cmake_ctl.events",
    "cmake_ctl.database",
    "cmake_ctl.cleaner",
    "cmake_ctl.installer",
    "cmake_ctl.proxy",
    "cmake_ctl.source_discovery",
]


@contextmanager
def isolated_home():
    with tempfile.TemporaryDirectory() as td:
        old = os.environ.get("CMAKE_CTL_HOME")
        os.environ["CMAKE_CTL_HOME"] = td
        for m in MODULES:
            importlib.import_module(m)
            importlib.reload(importlib.import_module(m))
        try:
            yield Path(td)
        finally:
            if old is None:
                os.environ.pop("CMAKE_CTL_HOME", None)
            else:
                os.environ["CMAKE_CTL_HOME"] = old
            for m in MODULES:
                importlib.reload(importlib.import_module(m))
