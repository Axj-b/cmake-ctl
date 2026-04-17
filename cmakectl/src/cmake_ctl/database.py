from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .paths import PROJECTS_DB_PATH, ensure_layout

_WRITE_LOCK = threading.Lock()


@dataclass
class ProjectRecord:
    project_key: str
    path: str
    cmake_version: str
    generator: str | None = None


def connect_db(db_path: Path | None = None) -> sqlite3.Connection:
    ensure_layout()
    path = db_path or PROJECTS_DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=1000;")
    return conn


@contextmanager
def managed_connection(db_path: Path | None = None):
    conn = connect_db(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with managed_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    apply_migrations(db_path)


def apply_migrations(db_path: Path | None = None) -> None:
    with managed_connection(db_path) as conn:
        versions = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        if 1 not in versions:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_key TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    cmake_version TEXT NOT NULL,
                    generator TEXT,
                    configure_count INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("INSERT INTO schema_migrations(version) VALUES (1)")


def rollback_last_migration(db_path: Path | None = None) -> int | None:
    with managed_connection(db_path) as conn:
        row = conn.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
        if row is None:
            return None
        version = int(row[0])
        if version == 1:
            conn.execute("DROP TABLE IF EXISTS projects")
        conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
        return version


def with_write_retry(operation, retries: int = 5, base_sleep: float = 0.02):
    last_exc = None
    for attempt in range(retries):
        try:
            with _WRITE_LOCK:
                return operation()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
            last_exc = exc
            time.sleep(base_sleep * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("write retry failed without captured exception")


def upsert_project(record: ProjectRecord, db_path: Path | None = None) -> None:
    init_db(db_path)

    def _op():
        with managed_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO projects(project_key, path, cmake_version, generator, configure_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(project_key) DO UPDATE SET
                    path=excluded.path,
                    cmake_version=excluded.cmake_version,
                    generator=excluded.generator,
                    configure_count=projects.configure_count + 1,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (record.project_key, record.path, record.cmake_version, record.generator),
            )

    with_write_retry(_op)


def list_projects(db_path: Path | None = None) -> list[dict]:
    init_db(db_path)
    with managed_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT project_key, path, cmake_version, generator, configure_count, pinned FROM projects ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {
            "project_key": r[0],
            "path": r[1],
            "cmake_version": r[2],
            "generator": r[3],
            "configure_count": r[4],
            "pinned": bool(r[5]),
        }
        for r in rows
    ]


def set_pinned(project_key: str, pinned: bool, db_path: Path | None = None) -> None:
    init_db(db_path)

    def _op():
        with managed_connection(db_path) as conn:
            conn.execute("UPDATE projects SET pinned=? WHERE project_key=?", (1 if pinned else 0, project_key))

    with_write_retry(_op)
