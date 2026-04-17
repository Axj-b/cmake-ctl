from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import hashlib

from .paths import (
    EVENTS_DEAD_LETTER_PATH,
    EVENTS_LOG_PATH,
    HOME_DIR,
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
    legacy_target = HOME_DIR / "events" / "cmake_invocations.ndjson"
    dead = dead_letter_path or EVENTS_DEAD_LETTER_PATH
    seen_path = processed_ids_path or PROCESSED_EVENTS_PATH
    seen = seen_event_ids if seen_event_ids is not None else _load_seen(seen_path)

    input_logs = [p for p in [target, legacy_target] if p.exists()]
    if not input_logs:
        return {"processed": 0, "skipped": 0, "invalid": 0}

    processed = 0
    skipped = 0
    invalid = 0

    for source in input_logs:
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines:
            raw_line = line.lstrip("\ufeff")
            if not raw_line.strip():
                continue
            try:
                doc = json.loads(raw_line)
            except Exception:
                # Try to recover known malformed C++ proxy lines with unescaped backslashes.
                recovered = _recover_legacy_cpp_line(raw_line)
                if recovered is None:
                    invalid += 1
                    _append_dead_letter(dead, raw_line)
                    continue
                doc = recovered

            try:
                event_id, schema_version, event_type, payload = _normalize_event_doc(doc, raw_line)
            except Exception:
                invalid += 1
                _append_dead_letter(dead, raw_line)
                continue

            if schema_version != EVENT_SCHEMA_VERSION:
                invalid += 1
                _append_dead_letter(dead, raw_line)
                continue

            if event_id in seen:
                skipped += 1
                continue

            handler(Event(event_id=event_id, event_type=event_type, payload=payload, schema_version=schema_version))
            seen.add(event_id)
            processed += 1

    # Compaction: clear processed files after successful pass.
    for source in input_logs:
        source.write_text("", encoding="utf-8")
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


def _normalize_event_doc(doc: dict, raw_line: str) -> tuple[str, int, str, dict]:
    # Canonical schema from Python proxy.
    if {"event_id", "schema_version", "event_type", "payload"}.issubset(doc.keys()):
        event_id = str(doc["event_id"])
        schema_version = int(doc["schema_version"])
        event_type = str(doc["event_type"])
        payload = dict(doc["payload"])
        return event_id, schema_version, event_type, payload

    # Legacy C++ proxy schema.
    # Example: {"event":"cmake_invocation","timestamp":"...","source_dir":"...","build_dir":"...","args":"..."}
    if "event" in doc and "source_dir" in doc:
        event_type = str(doc.get("event", "cmake_invocation"))
        source_dir = str(doc.get("source_dir", ""))
        build_dir = str(doc.get("build_dir", ""))
        args_field = doc.get("args", "")
        if isinstance(args_field, list):
            argv = [str(a) for a in args_field]
        else:
            argv = str(args_field).split() if str(args_field).strip() else []

        stable = f"{doc.get('timestamp','')}|{source_dir}|{build_dir}|{' '.join(argv)}"
        event_id = "legacy-" + hashlib.sha1(stable.encode("utf-8")).hexdigest()
        payload = {
            "project_path": source_dir,
            "source_dir": source_dir,
            "build_dir": build_dir,
            "cwd": source_dir,
            "argv": argv,
            "resolved_version": "",
            "source": "legacy-proxy",
        }
        return event_id, EVENT_SCHEMA_VERSION, event_type, payload

    raise ValueError("Unsupported event schema")


def _recover_legacy_cpp_line(raw_line: str) -> dict | None:
    # Legacy C++ proxy line format (not strict JSON-safe on Windows paths):
    # {"event":"cmake_invocation","timestamp":"...","source_dir":"C:\...","build_dir":"C:\...","args":"..."}
    if '"event":"cmake_invocation"' not in raw_line:
        return None

    def _extract(key: str) -> str:
        token = f'"{key}":"'
        start = raw_line.find(token)
        if start < 0:
            return ""
        start += len(token)
        end = raw_line.find('","', start)
        if end < 0:
            # last field before object end
            end = raw_line.find('"}', start)
        if end < 0:
            return ""
        return raw_line[start:end]

    timestamp = _extract("timestamp")
    source_dir = _extract("source_dir")
    build_dir = _extract("build_dir")
    args = _extract("args")
    if not source_dir:
        return None

    return {
        "event": "cmake_invocation",
        "timestamp": timestamp,
        "source_dir": source_dir,
        "build_dir": build_dir,
        "args": args,
    }
