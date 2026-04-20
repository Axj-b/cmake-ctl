from __future__ import annotations

import importlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

MODULES = [
    "cmake-ctl.paths",
    "cmake-ctl.config_store",
    "cmake-ctl.identity",
    "cmake-ctl.session_store",
    "cmake-ctl.resolver",
    "cmake-ctl.events",
    "cmake-ctl.database",
    "cmake-ctl.cleaner",
    "cmake-ctl.installer",
    "cmake-ctl.native_proxy",
    "cmake-ctl.source_discovery",
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
