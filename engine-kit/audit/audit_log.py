#!/usr/bin/env python3
"""audit_log — append-only, hash-chained per-loop event ledger (Audit Spine).

Implements the Loop Audit Spine from the plan (archive
2026-06-15-v2-loop-engine-plan.md §4.5): a tamper-evident, append-only event
ledger that threads one ``loop_id`` through charter → brief → checkpoint →
spawn → trace → verdict → close, so a loop can be reconstructed and "reviewed
later" against a record it cannot silently rewrite (gaps G2/G3/G6). The
Constitution names trace + eval/audit contract runtime-owned (§1.4).

Ledger location: ``.orchestrator/audit/<loop_id>.jsonl`` (one JSON event per
line). Each event line is:

    {loop_id, seq, ts, type, payload, prev_hash, hash}

HASH CHAIN:
    canonical_json(obj) = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    hash = sha256( prev_hash + canonical_json(event_without_hash_field) ).hexdigest()
    first event prev_hash = "0" * 64
Because each event commits to ``prev_hash`` (and thus, transitively, to every
prior event), altering any byte of any event breaks the chain from that seq on;
``verify_chain`` returns the first bad seq.

DETERMINISM / TESTABILITY: ``ts`` is INJECTABLE — the pure append/hash path never
reads the clock. ``append_event`` requires the caller to pass ``ts`` (and the
orchestrator supplies a real one). This keeps the hash a pure function of its
inputs, so tests are reproducible.

CLI:
    python audit_log.py verify <loop_id.jsonl>
        exit 0  ⇒ chain intact
        exit !0 ⇒ broken/tampered link; prints the first offending seq
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Optional

GENESIS_PREV_HASH = "0" * 64


class LedgerCorruption(Exception):
    """A ledger line could not be parsed as JSON (truncated/corrupted file).

    Carries the 1-based line number and the parse reason. For a tamper-evident
    tool this is itself an integrity failure: it must surface as a clean,
    reported error (non-zero exit) — never a raw JSONDecodeError traceback.
    """

    def __init__(self, line_no: int, reason: str):
        self.line_no = line_no
        self.reason = reason
        super().__init__(f"unparseable line {line_no}: {reason}")

# Fields that make up the hashed event body, in addition to the chain fields.
# The hash is computed over the whole event MINUS the "hash" field itself.
_HASH_FIELD = "hash"

# The execution-context payload shape carried by a per-spawn event (plan §4.5 G3
# — extends the orchestrator's calls/ record). Listed here as documentation +
# for the convenience constructor below; the ledger itself stores whatever
# payload dict it is given (audit is a generic event log).
SPAWN_PAYLOAD_FIELDS: tuple[str, ...] = (
    "role",
    "harness",
    "provider",
    "model",
    "skill_pins",        # list[str]
    "memory_injected",   # list[str]
    "input_hash",
    "verdict_ref",
    "prompt_ref",        # run-dir-relative path to the as-dispatched prompt transcript
    "output_ref",        # run-dir-relative path to the captured model-output transcript
    "run_mode",
    "tokens",
    "cost",
    # WP-0 (context/token-optimization measurement baseline) — observation-only
    # per-spawn volume fields. APPEND-ONLY: never remove or reorder a property while
    # ledgers carrying it exist — the audit-event $defs/spawn_payload is
    # additionalProperties:false, so dropping a field would orphan historical
    # payloads (deprecate, don't delete). All three are nullable for back-compat.
    "prompt_bytes",      # len(as-dispatched prompt, utf-8 bytes)
    "memory_bytes",      # bytes of the Loop-Memory lessons block injected for the role
    "fix_round",         # fix-round index at dispatch (the fix-round cost multiplier)
    # WP-7 (context/token-optimization) — per-spawn cold-start fingerprint. Same
    # APPEND-ONLY / nullable / deprecate-don't-delete rule as the WP-0 fields above.
    "load_graph_hash",   # content fingerprint of the role's cold-start governance/kernel
                         # load set (load_sizer.cold_start_load_graph_hash). AUDIT-ONLY —
                         # records which governance/kernel VERSION an otherwise audit-neutral
                         # (prompt-only input_hash) Dev/Review/Close/Research spawn loaded;
                         # NOT the Acceptance §3.5b reuse hash (design spec §E).
)


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace. The hash basis."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_hash(event_without_hash: dict, prev_hash: str) -> str:
    """hash = sha256( prev_hash + canonical_json(event_without_hash) )."""
    basis = prev_hash + canonical_json(event_without_hash)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def make_event(
    loop_id: str,
    seq: int,
    ts: str,
    type: str,
    payload: Any,
    prev_hash: str,
) -> dict:
    """Build a fully-formed, hash-stamped event (pure; no I/O, no clock).

    The event-without-hash is assembled first (loop_id, seq, ts, type, payload,
    prev_hash), then ``hash`` is computed over it and appended. Returned dict is
    JSON-serializable and ready to be written as one ledger line.
    """
    body = {
        "loop_id": loop_id,
        "seq": seq,
        "ts": ts,
        "type": type,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    event = dict(body)
    event[_HASH_FIELD] = compute_hash(body, prev_hash)
    return event


def make_spawn_payload(
    *,
    role: str,
    harness: str,
    provider: str,
    model: str,
    skill_pins: Optional[list[str]] = None,
    memory_injected: Optional[list[str]] = None,
    input_hash: Optional[str] = None,
    verdict_ref: Optional[str] = None,
    prompt_ref: Optional[str] = None,
    output_ref: Optional[str] = None,
    run_mode: Optional[str] = None,
    tokens: Optional[int] = None,
    cost: Optional[float] = None,
    prompt_bytes: Optional[int] = None,
    memory_bytes: Optional[int] = None,
    fix_round: Optional[int] = None,
    load_graph_hash: Optional[str] = None,
) -> dict:
    """Convenience constructor for the per-spawn execution-context payload
    (plan §4.5 G3). Returns a plain dict; the ledger stores it verbatim.

    ``prompt_ref`` / ``output_ref`` anchor the EXECUTION RECORD: run-dir-relative
    paths to the as-dispatched prompt and the captured model output transcripts
    the orchestrator materializes per spawn (driver._write_transcript). They make
    every prompt and every output auditable from the ledger — not just a hash —
    while ``input_hash`` stays the tamper-evidence anchor over the prompt bytes.
    Both default to None so a caller that does not materialize transcripts (or an
    older ledger) is byte-identical to before.

    ``prompt_bytes`` / ``memory_bytes`` / ``fix_round`` are WP-0 observation-only
    measurement fields (the context/token-optimization baseline). All default to
    None so an older callsite need not pass them and an existing on-disk ledger
    (written without these keys) still verifies unchanged; they record the
    as-dispatched prompt size, the injected Loop-Memory lessons-block size, and the
    fix-round index, so per-spawn token volume becomes auditable.

    ``load_graph_hash`` (WP-7) is the same kind of nullable, forward-only field: a
    content fingerprint of the role's cold-start governance/kernel load set, so which
    governance VERSION a spawn loaded is ledger-recorded even for the roles whose
    ``input_hash`` is prompt-only. AUDIT-ONLY — not the Acceptance reuse hash."""
    return {
        "role": role,
        "harness": harness,
        "provider": provider,
        "model": model,
        "skill_pins": list(skill_pins or []),
        "memory_injected": list(memory_injected or []),
        "input_hash": input_hash,
        "verdict_ref": verdict_ref,
        "prompt_ref": prompt_ref,
        "output_ref": output_ref,
        "run_mode": run_mode,
        "tokens": tokens,
        "cost": cost,
        "prompt_bytes": prompt_bytes,
        "memory_bytes": memory_bytes,
        "fix_round": fix_round,
        "load_graph_hash": load_graph_hash,
    }


# --------------------------------------------------------------------------- #
# Ledger I/O.
# --------------------------------------------------------------------------- #
def read_events(path: str) -> list[dict]:
    """Read all events from a .jsonl ledger (in file order). Blank lines skipped.

    A line that is not valid JSON (a truncated/corrupted ledger) is treated as
    ledger corruption: ``LedgerCorruption`` is raised with the 1-based line
    number and reason, rather than letting a raw ``JSONDecodeError`` escape.
    Valid ledgers parse byte-identically to before.
    """
    events: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise LedgerCorruption(line_no, str(exc)) from exc
    return events


def last_event(path: str) -> Optional[dict]:
    """The last event in a ledger, or None if the ledger is empty/absent."""
    if not os.path.isfile(path):
        return None
    events = read_events(path)
    return events[-1] if events else None


def audit_path(loop_id: str, audit_dir: Optional[str] = None) -> str:
    """Resolve the ledger path for a loop_id. Default dir: .orchestrator/audit/
    under the current working directory (the adopter repo)."""
    base = audit_dir or os.path.join(".orchestrator", "audit")
    return os.path.join(base, f"{loop_id}.jsonl")


def append_event(
    loop_id: str,
    type: str,
    payload: Any,
    *,
    ts: str,
    audit_dir: Optional[str] = None,
    path: Optional[str] = None,
) -> dict:
    """Append one event to the loop's ledger and return it.

    The next ``seq`` and ``prev_hash`` are derived from the current tail of the
    ledger (seq 0 / GENESIS_PREV_HASH if empty). ``ts`` is REQUIRED and injected
    by the caller — the pure hash path never reads the clock. The ledger file is
    created (with parent dirs) on first append.
    """
    target = path or audit_path(loop_id, audit_dir)
    tail = last_event(target) if os.path.isfile(target) else None
    if tail is None:
        seq = 0
        prev_hash = GENESIS_PREV_HASH
    else:
        seq = int(tail["seq"]) + 1
        prev_hash = tail[_HASH_FIELD]

    event = make_event(loop_id, seq, ts, type, payload, prev_hash)

    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(canonical_json(event) + "\n")
    return event


# --------------------------------------------------------------------------- #
# Verification.
# --------------------------------------------------------------------------- #
class ChainResult:
    """Result of verifying a hash-chained ledger.

    ok                : True iff the whole chain is intact.
    bad_seq           : the first offending seq (None if ok).
    reason            : human-readable reason for the break (None if ok).
    count             : number of events checked.
    corrupt_line      : 1-based line number of an unparseable ledger line
                        (None unless the ledger could not be read as JSON).
    """

    def __init__(
        self,
        ok: bool,
        bad_seq: Optional[int],
        reason: Optional[str],
        count: int,
        corrupt_line: Optional[int] = None,
    ):
        self.ok = ok
        self.bad_seq = bad_seq
        self.reason = reason
        self.count = count
        self.corrupt_line = corrupt_line

    def render(self) -> str:
        if self.ok:
            return f"audit_log: chain intact ({self.count} event(s))."
        if self.corrupt_line is not None:
            return (
                f"audit_log: ledger CORRUPT — unparseable line "
                f"{self.corrupt_line}: {self.reason}"
            )
        return (
            f"audit_log: chain BROKEN at seq {self.bad_seq} "
            f"({self.count} event(s) read): {self.reason}"
        )


def verify_events(events: list[dict]) -> ChainResult:
    """Verify an in-memory list of events. Returns the first bad seq, if any.

    For each event the recomputed hash (over the event minus its ``hash`` field,
    chained to the running prev_hash) must equal the stored ``hash``; and each
    event's stored ``prev_hash`` must equal the prior event's ``hash`` (genesis
    for the first); and ``seq`` must increase by 1 from 0. Any deviation returns
    the offending seq.
    """
    expected_prev = GENESIS_PREV_HASH
    for i, event in enumerate(events):
        seq = event.get("seq")
        if seq != i:
            return ChainResult(False, seq if isinstance(seq, int) else i,
                               f"out-of-order seq (expected {i}, got {seq!r})", len(events))
        if event.get("prev_hash") != expected_prev:
            return ChainResult(False, i,
                               f"prev_hash mismatch (expected {expected_prev}, "
                               f"got {event.get('prev_hash')!r})", len(events))
        stored = event.get(_HASH_FIELD)
        body = {k: v for k, v in event.items() if k != _HASH_FIELD}
        recomputed = compute_hash(body, event.get("prev_hash", ""))
        if stored != recomputed:
            return ChainResult(False, i,
                               "hash mismatch (event body tampered)", len(events))
        expected_prev = stored
    return ChainResult(True, None, None, len(events))


def verify_chain(path: str) -> ChainResult:
    """Read a ledger file and verify its hash chain. Returns a ChainResult whose
    ``bad_seq`` is the first broken/tampered seq (None if intact).

    A corrupted/truncated ledger (a line that is not valid JSON) is reported as
    an integrity failure (``corrupt_line`` set, ``ok=False``) rather than
    crashing — a damaged ledger is itself a tamper signal for this tool."""
    try:
        events = read_events(path)
    except LedgerCorruption as exc:
        return ChainResult(False, None, exc.reason, 0, corrupt_line=exc.line_no)
    return verify_events(events)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append-only, hash-chained per-loop audit ledger (Audit Spine).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser("verify", help="verify a ledger's hash chain")
    p_verify.add_argument("ledger", help="path to <loop_id>.jsonl")

    args = parser.parse_args(argv)

    if args.cmd == "verify":
        if not os.path.isfile(args.ledger):
            sys.stderr.write(f"audit_log: ledger not found: {args.ledger}\n")
            return 2
        result = verify_chain(args.ledger)
        print(result.render())
        return 0 if result.ok else 1

    return 2  # pragma: no cover - argparse enforces a subcommand


if __name__ == "__main__":
    sys.exit(main())
