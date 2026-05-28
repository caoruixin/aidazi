#!/usr/bin/env python3
"""trace.jsonl emitter for aidazi dev / review sessions.

Per `framework/governance/context_briefing.md`, each session SHOULD
emit a structured trace.jsonl to:

    docs/sprints/sprint-NNN/trace.jsonl   (dev)
    docs/milestones/M<N>/trace.jsonl      (review)

Trace records are append-only JSON lines. The agent calls the
functions in this module to record key decisions and events.

Usage from an agent's Python tool:

    from trace_emitter import (
        open_trace, log_decision, log_blocker, close_trace,
    )

    t = open_trace(
        role="dev",
        sprint_id="sprint-054",
        prompt_artifact_path="compact/sprint-054-dev-prompt.md",
    )
    log_decision(t, "read_file", path="server/src/.../runtime.py",
                 reason="Step 1 anchor")
    log_decision(t, "alternative_chosen",
                 alternatives=["A", "B"], chosen="B",
                 reason="B preserves §1.7 anti-hardcode discipline")
    log_blocker(t, "hard_fence_breach_attempt",
                fence="No edits to skill_state per scope #2",
                resolution="reverted change; surfaced finding in handoff §10")
    close_trace(t, verdict_summary="all scope items done; eval baseline preserved")

The trace file is NEVER edited after close. Treat as
`sprint-archive` tier per `framework/governance/doc_governance.md`.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TraceHandle:
    """Open trace.jsonl handle. Pass to log_* functions."""

    path: Path
    role: str
    sprint_id: str
    prompt_artifact_path: str
    prompt_artifact_hash: str = ""
    session_started_at: str = ""
    closed: bool = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file_hash(path: Path) -> str:
    """Compute a short content hash for the prompt artifact."""
    import hashlib

    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _emit(handle: TraceHandle, event: dict[str, Any]) -> None:
    if handle.closed:
        raise RuntimeError(f"trace.jsonl at {handle.path} already closed")
    event = {"timestamp": _now_iso(), **event}
    handle.path.parent.mkdir(parents=True, exist_ok=True)
    with handle.path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def open_trace(
    role: str,
    sprint_id: str,
    prompt_artifact_path: str,
    trace_path: str | None = None,
) -> TraceHandle:
    """Open a new trace.jsonl for a session.

    Args:
        role: 'dev' | 'review' | 'research' | 'deliver'
        sprint_id: e.g. 'sprint-054' or 'M5'
        prompt_artifact_path: relative path to the compact prompt that
            spawned this session (or activation template for
            deliver/research).
        trace_path: optional override; default derived from role +
            sprint_id.
    """
    if trace_path is None:
        if role in {"dev"}:
            default = Path("docs/sprints") / sprint_id / "trace.jsonl"
        elif role in {"review"}:
            default = Path("docs/milestones") / sprint_id / "trace.jsonl"
        else:
            default = Path("docs/diagnostics/traces") / f"{role}-{sprint_id}.jsonl"
        path = default
    else:
        path = Path(trace_path)

    artifact_path = Path(prompt_artifact_path)
    handle = TraceHandle(
        path=path,
        role=role,
        sprint_id=sprint_id,
        prompt_artifact_path=prompt_artifact_path,
        prompt_artifact_hash=_file_hash(artifact_path),
        session_started_at=_now_iso(),
    )
    _emit(
        handle,
        {
            "event": "session_start",
            "role": role,
            "sprint_id": sprint_id,
            "prompt_artifact_path": prompt_artifact_path,
            "prompt_artifact_hash": handle.prompt_artifact_hash,
            "pid": os.getpid(),
            "python_version": sys.version.split()[0],
        },
    )
    return handle


def log_decision(handle: TraceHandle, decision_type: str, **fields: Any) -> None:
    """Log a key decision the agent made.

    Common decision_type values:
        - 'read_file' (path, reason)
        - 'tool_call' (tool, args, result_summary)
        - 'alternative_chosen' (alternatives, chosen, reason)
        - 'context_pack_invoked' (task_summary)
        - 'file_modified' (path, intent)
    """
    _emit(handle, {"event": "decision", "type": decision_type, **fields})


def log_blocker(handle: TraceHandle, blocker_type: str, **fields: Any) -> None:
    """Log a blocker / STOP-and-surface event.

    Common blocker_type values:
        - 'hard_fence_breach_attempt' (fence, resolution)
        - 'stop_and_surface' (reason, what_was_surfaced)
        - 'error' (error_class, message)
    """
    _emit(handle, {"event": "blocker", "type": blocker_type, **fields})


def log_observation(handle: TraceHandle, what: str, **fields: Any) -> None:
    """Log a free-form observation (not a decision, not a blocker).

    Use sparingly. Most things should be 'decision' or 'blocker'.
    """
    _emit(handle, {"event": "observation", "what": what, **fields})


def close_trace(handle: TraceHandle, verdict_summary: str = "") -> None:
    """Close the trace.jsonl session.

    Args:
        verdict_summary: optional one-line summary of session outcome.
    """
    if handle.closed:
        return
    _emit(
        handle,
        {
            "event": "session_end",
            "verdict_summary": verdict_summary,
            "duration_seconds": int(
                (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(handle.session_started_at)
                ).total_seconds()
            ),
        },
    )
    handle.closed = True
