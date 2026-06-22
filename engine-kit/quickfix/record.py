"""Append-only Quick-Fix record log (.orchestrator/quickfix/records.jsonl).

An append-only PROTOCOL for observability/audit — NOT a tamper-proof ledger (no hash
chain) and NEVER an activation credential. Each outcome is one JSON line, validated
against schemas/quickfix-record.schema.json, appended under an EXCLUSIVE file lock in a
single atomic write (O_APPEND + flock). Reads tolerate a corrupt/partial trailing line
(e.g. from an abnormal exit) by skipping it rather than failing.
"""
from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass
from typing import List, Tuple

from jsonschema import Draft202012Validator

from .errors import RecordError


def default_records_path(repo_dir: str) -> str:
    return os.path.join(repo_dir, ".orchestrator", "quickfix", "records.jsonl")


def _validate(record: dict, schema_path: str) -> None:
    if not os.path.isfile(schema_path):
        raise RecordError(f"record schema not found: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    errs = sorted(Draft202012Validator(schema).iter_errors(record), key=lambda e: list(e.path))
    if errs:
        raise RecordError("record failed schema validation: "
                          + "; ".join(e.message for e in errs[:5]))


def append(record: dict, records_path: str, schema_path: str) -> None:
    """Validate + append one record line under an exclusive lock (atomic single write)."""
    _validate(record, schema_path)
    line = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
    os.makedirs(os.path.dirname(records_path), exist_ok=True)
    # O_APPEND so the write lands at EOF; flock so concurrent writers serialize and each
    # line is written whole (one os.write under the lock).
    fd = os.open(records_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            data = line.encode("utf-8")
            view = memoryview(data)
            written = 0
            while written < len(data):  # handle short writes — never leave a partial line
                n = os.write(fd, view[written:])
                if n <= 0:
                    raise RecordError(f"short write to {records_path} "
                                      f"({written}/{len(data)} bytes)")
                written += n
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@dataclass
class RecordsRead:
    records: List[dict]
    corrupt_lines: List[str]


def read(records_path: str) -> RecordsRead:
    """Read all valid records; collect (do not raise on) corrupt/partial lines."""
    if not os.path.isfile(records_path):
        return RecordsRead([], [])
    records: List[dict] = []
    corrupt: List[str] = []
    with open(records_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                corrupt.append(line)
                continue
            if isinstance(obj, dict):
                records.append(obj)
            else:
                corrupt.append(line)
    return RecordsRead(records, corrupt)
