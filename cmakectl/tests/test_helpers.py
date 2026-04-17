from __future__ import annotations

import importlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

MODULES = [
    "cmakectl.paths",
    "cmakectl.config_store",
    "cmakectl.identity",
    "cmakectl.session_store",
    "cmakectl.resolver",
    "cmakectl.events",
    "cmakectl.database",
    "cmakectl.cleaner",
    "cmakectl.installer",
    "cmakectl.proxy",
    "cmakectl.source_discovery",
]


@contextmanager
def isolated_home():
    with tempfile.TemporaryDirectory() as td:
        old = os.environ.get("CMAKECTL_HOME")
        os.environ["CMAKECTL_HOME"] = td
        for m in MODULES:
            importlib.import_module(m)
            importlib.reload(importlib.import_module(m))
        try:
            yield Path(td)
        finally:
            if old is None:
                os.environ.pop("CMAKECTL_HOME", None)
            else:
                os.environ["CMAKECTL_HOME"] = old
            for m in MODULES:
                importlib.reload(importlib.import_module(m))
