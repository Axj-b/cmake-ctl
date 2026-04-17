from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_helpers import isolated_home


class EventsAndDatabaseTests(unittest.TestCase):
    def test_event_processing_is_idempotent_and_dead_letters_invalid(self):
        with isolated_home() as home:
            from cmake_ctl.events import Event, append_event, process_events

            log = home / "events.log"
            dead = home / "dead.log"
            seen = home / "seen.txt"
            handled: list[str] = []

            append_event(Event(event_id="e1", event_type="x", payload={"a": 1}), log_path=log)
            append_event(Event(event_id="e2", event_type="x", payload={"a": 2}), log_path=log)
            with log.open("a", encoding="utf-8") as f:
                f.write("{bad json}\n")

            first = process_events(lambda e: handled.append(e.event_id), log_path=log, dead_letter_path=dead, processed_ids_path=seen)
            self.assertEqual(first["processed"], 2)
            self.assertEqual(first["invalid"], 1)
            self.assertIn("e1", handled)

            # Requeue same events; should be skipped due to persisted processed IDs.
            append_event(Event(event_id="e1", event_type="x", payload={"a": 1}), log_path=log)
            second = process_events(lambda e: handled.append(e.event_id), log_path=log, dead_letter_path=dead, processed_ids_path=seen)
            self.assertEqual(second["processed"], 0)
            self.assertGreaterEqual(second["skipped"], 1)
            self.assertTrue(dead.exists())

    def test_db_wal_migration_retry_and_rollback(self):
        with isolated_home() as home:
            from cmake_ctl.database import (
                ProjectRecord,
                init_db,
                list_projects,
                managed_connection,
                rollback_last_migration,
                upsert_project,
                with_write_retry,
            )

            init_db()
            with managed_connection() as conn:
                mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
                self.assertEqual(mode.lower(), "wal")

            upsert_project(ProjectRecord(project_key="p1", path="/tmp/p1", cmake_version="3.28.1"))
            rows = list_projects()
            self.assertEqual(len(rows), 1)

            call_count = {"n": 0}

            def flaky():
                import sqlite3

                call_count["n"] += 1
                if call_count["n"] < 3:
                    raise sqlite3.OperationalError("database is locked")
                return "ok"

            self.assertEqual(with_write_retry(flaky, retries=5), "ok")
            self.assertEqual(call_count["n"], 3)

            rolled = rollback_last_migration()
            self.assertEqual(rolled, 1)


if __name__ == "__main__":
    unittest.main()
