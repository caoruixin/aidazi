#!/usr/bin/env python3
"""audit_report — deterministic (no-LLM) reconstruction of a loop's audit ledger.

Reads a ``.orchestrator/audit/<loop_id>.jsonl`` hash-chained ledger (written by
audit_log.py) and renders a human-readable Markdown timeline
(``audit/<loop_id>-report.md`` style), closing gap G4 from the plan (§4.5): the
scattered machine artifacts get one end-to-end, human-readable reconstruction.
No LLM — the report is a pure, deterministic projection of the ledger events.

The report includes:
  * A header with the loop_id, event count, and the chain-integrity verdict
    (re-uses audit_log.verify_events — a tampered ledger is reported as such,
    not silently rendered as if intact).
  * A timeline table: seq · ts · type · a compact one-line payload summary.
  * A per-spawn execution-context section for each event whose payload carries
    the spawn fields (role / harness / provider / model / skill_pins / … —
    plan §4.5 G3), so the reconstruction shows what ran each step.

Determinism contract: pure function over the ledger file. No network, no LLM, no
clock/random. Same ledger ⇒ same report bytes.

CLI:
    python audit_report.py <loop_id.jsonl>           # print to stdout
    python audit_report.py <loop_id.jsonl> -o out.md # also write to a file
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import audit_log  # noqa: E402

# Payload keys that mark an event as a "spawn" (execution-context) event.
_SPAWN_MARKER_KEYS = ("role", "model", "harness")


def _is_spawn_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and any(k in payload for k in _SPAWN_MARKER_KEYS)


def _md_escape(text: str) -> str:
    """Escape the Markdown table delimiter so a payload value can't break a row."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def _payload_summary(payload: Any) -> str:
    """A compact one-line summary of a payload for the timeline table."""
    if _is_spawn_payload(payload):
        role = payload.get("role", "?")
        model = payload.get("model", "?")
        provider = payload.get("provider")
        provider_s = f"{provider}/" if provider else ""
        return f"spawn: {role} via {provider_s}{model}"
    if isinstance(payload, dict):
        if not payload:
            return "{}"
        # Stable order: sort keys; cap length so the table stays readable.
        parts = [f"{k}={payload[k]!r}" for k in sorted(payload)]
        joined = ", ".join(parts)
        return joined if len(joined) <= 80 else joined[:77] + "..."
    return repr(payload)


def render_report(events: list[dict], loop_id: Optional[str] = None) -> str:
    """Render the Markdown report for a list of ledger events (pure)."""
    if loop_id is None and events:
        loop_id = events[0].get("loop_id", "<unknown>")
    loop_id = loop_id or "<unknown>"

    chain = audit_log.verify_events(events)
    integrity = (
        "intact"
        if chain.ok
        else f"BROKEN at seq {chain.bad_seq} ({chain.reason})"
    )

    lines: list[str] = []
    lines.append(f"# Audit reconstruction — loop `{loop_id}`")
    lines.append("")
    lines.append(f"- Events: {len(events)}")
    lines.append(f"- Chain integrity: {integrity}")
    if events:
        lines.append(f"- First ts: {events[0].get('ts')}")
        lines.append(f"- Last ts: {events[-1].get('ts')}")
    lines.append("")
    lines.append("## Timeline")
    lines.append("")
    lines.append("| seq | ts | type | summary |")
    lines.append("|---|---|---|---|")
    for ev in events:
        lines.append(
            f"| {ev.get('seq')} "
            f"| {_md_escape(ev.get('ts', ''))} "
            f"| {_md_escape(ev.get('type', ''))} "
            f"| {_md_escape(_payload_summary(ev.get('payload')))} |"
        )
    lines.append("")

    # Per-spawn execution-context detail (plan §4.5 G3).
    spawns = [ev for ev in events if _is_spawn_payload(ev.get("payload"))]
    if spawns:
        lines.append("## Spawn execution context")
        lines.append("")
        for ev in spawns:
            p = ev["payload"]
            lines.append(f"### seq {ev.get('seq')} — {p.get('role', '?')}")
            lines.append("")
            for field in audit_log.SPAWN_PAYLOAD_FIELDS:
                if field in p:
                    value = p[field]
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value) if value else "(none)"
                    lines.append(f"- {field}: {value}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_corruption(path: str, corruption: "audit_log.LedgerCorruption") -> str:
    """Render an integrity-failure report for an unparseable ledger, rather than
    crashing on a raw JSONDecodeError. The reconstruction must not pretend the
    ledger is intact when it cannot even be read."""
    loop_id = os.path.splitext(os.path.basename(path))[0] or "<unknown>"
    return (
        f"# Audit reconstruction — loop `{loop_id}`\n"
        f"\n"
        f"- Events: 0\n"
        f"- Chain integrity: CORRUPT (unparseable line "
        f"{corruption.line_no}: {corruption.reason})\n"
    )


def render_report_file(path: str) -> str:
    """Read a ledger file and render its Markdown report.

    If the ledger is corrupt/truncated (a non-JSON line), render an
    integrity-failure report instead of letting the parse error escape."""
    try:
        events = audit_log.read_events(path)
    except audit_log.LedgerCorruption as exc:
        return _render_corruption(path, exc)
    return render_report(events)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic (no-LLM) Markdown reconstruction of an audit ledger.",
    )
    parser.add_argument("ledger", help="path to <loop_id>.jsonl")
    parser.add_argument(
        "-o", "--out", default=None, help="also write the report to this path"
    )
    args = parser.parse_args(argv)

    if not os.path.isfile(args.ledger):
        sys.stderr.write(f"audit_report: ledger not found: {args.ledger}\n")
        return 2

    # A corrupt/truncated ledger is an integrity failure: render the failure
    # report (no traceback) but exit non-zero so callers/CI notice.
    corrupt = False
    try:
        audit_log.read_events(args.ledger)
    except audit_log.LedgerCorruption:
        corrupt = True

    report = render_report_file(args.ledger)
    sys.stdout.write(report)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
    return 1 if corrupt else 0


if __name__ == "__main__":
    sys.exit(main())
