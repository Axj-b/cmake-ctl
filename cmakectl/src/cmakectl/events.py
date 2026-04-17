from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .paths import (
    EVENTS_DEAD_LETTER_PATH,
    EVENTS_LOG_PATH,
    PROCESSED_EVENTS_PATH,
    ensure_layout,
)

EVENT_SCHEMA_VERSION = 1


@dataclass
class Event:
    event_id: str
    event_type: str
    payload: dict
    schema_version: int = EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": self.payload,
        }


def append_event(event: Event, log_path: Path | None = None) -> None:
    ensure_layout()
    target = log_path or EVENTS_LOG_PATH
    line = json.dumps(event.to_dict(), separators=(",", ":")) + "\n"
    fd = os.open(str(target), os.O_APPEND | os.O_CREAT | os.O_WRONLY)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def process_events(
    handler,
    log_path: Path | None = None,
    dead_letter_path: Path | None = None,
    seen_event_ids: set[str] | None = None,
    processed_ids_path: Path | None = None,
) -> dict[str, int]:
    ensure_layout()
    target = log_path or EVENTS_LOG_PATH
    dead = dead_letter_path or EVENTS_DEAD_LETTER_PATH
    seen_path = processed_ids_path or PROCESSED_EVENTS_PATH
    seen = seen_event_ids if seen_event_ids is not None else _load_seen(seen_path)

    if not target.exists():
        return {"processed": 0, "skipped": 0, "invalid": 0}

    processed = 0
    skipped = 0
    invalid = 0

    lines = target.read_text(encoding="utf-8").splitlines()
    remaining: list[str] = []

    for line in lines:
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
            event_id = str(doc["event_id"])
            schema_version = int(doc["schema_version"])
            event_type = str(doc["event_type"])
            payload = dict(doc["payload"])
        except Exception:
            invalid += 1
            _append_dead_letter(dead, line)
            continue

        if schema_version != EVENT_SCHEMA_VERSION:
            invalid += 1
            _append_dead_letter(dead, line)
            continue

        if event_id in seen:
            skipped += 1
            continue

        handler(Event(event_id=event_id, event_type=event_type, payload=payload, schema_version=schema_version))
        seen.add(event_id)
        processed += 1

    # Compaction: clear processed file after successful pass.
    target.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
    _store_seen(seen_path, seen)
    return {"processed": processed, "skipped": skipped, "invalid": invalid}


def rotate_event_log(max_bytes: int = 2_000_000, log_path: Path | None = None) -> Path | None:
    ensure_layout()
    target = log_path or EVENTS_LOG_PATH
    if not target.exists() or target.stat().st_size <= max_bytes:
        return None
    rotated = target.with_suffix(target.suffix + ".1")
    if rotated.exists():
        rotated.unlink()
    target.replace(rotated)
    target.write_text("", encoding="utf-8")
    return rotated


def _append_dead_letter(path: Path, line: str) -> None:
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY)
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def _load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    values = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    return values


def _store_seen(path: Path, seen: set[str]) -> None:
    path.write_text("\n".join(sorted(seen)) + ("\n" if seen else ""), encoding="utf-8")
