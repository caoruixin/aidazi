"""Load + validate a quickfix-request (fail-closed).

A missing file, malformed JSON, a schema violation, `human_activation` not exactly true,
an empty `allowed_globs`, or a glob outside the safe subset all raise ``RequestError`` and
the lane is NOT entered. `human_activation` is an attestation only — the real activation
is the human running the launcher (process/quickfix-lane.md §2).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

from jsonschema import Draft202012Validator

from .errors import GlobError, RequestError
from .globmatch import Glob, compile_globs


@dataclass(frozen=True)
class Verification:
    argv: List[str]
    cwd: str = "."


@dataclass
class Request:
    request_id: str
    created_by: str
    harness: str
    task_summary: str
    allowed_globs: List[Glob]               # compiled
    allowed_glob_patterns: List[str]        # raw strings (for the record/audit)
    verification: Verification
    base_ref: Optional[str]
    raw: dict = field(repr=False, default_factory=dict)


def load_request(request_path: str, schema_path: str) -> Request:
    if not os.path.isfile(request_path):
        raise RequestError(f"quickfix-request not found: {request_path}")
    try:
        with open(request_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise RequestError(f"quickfix-request is not valid JSON ({request_path}): {exc}") from exc

    if not os.path.isfile(schema_path):
        raise RequestError(f"request schema not found: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    errs = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    if errs:
        raise RequestError(
            f"quickfix-request failed schema validation: "
            + "; ".join(e.message for e in errs[:5])
        )

    # Schema guarantees the shape; defensively recompile the globs (fail-closed) so the
    # guard and the request share ONE matcher implementation.
    try:
        compiled = compile_globs(data["allowed_globs"])
    except GlobError as exc:
        raise RequestError(f"allowed_globs rejected by matcher: {exc}") from exc

    tv = data["targeted_verification"]
    verification = Verification(argv=list(tv["argv"]), cwd=tv.get("cwd", "."))

    return Request(
        request_id=data["request_id"],
        created_by=data["created_by"],
        harness=data["harness"],
        task_summary=data["task_summary"],
        allowed_globs=compiled,
        allowed_glob_patterns=list(data["allowed_globs"]),
        verification=verification,
        base_ref=data.get("base_ref"),
        raw=data,
    )
