"""scope_report — read-only scope-coverage projection for a Campaign (Phase 0).

The campaign runner surfaces only ``milestone_index/milestones_total`` at close
(run_loop.print_campaign_result) — a bare progress fraction. It never answers the
question an adopter actually asks after a few milestones:

    "Of the backlog I signed, what is DELIVERED, what is still PENDING, and what
     was ADDED mid-flight?"

This module answers that from EXISTING artifacts only: the signed campaign-plan
(the declared backlog — schemas/campaign-plan.schema.json) and the persisted
campaign-state (what the Driver actually ran — schemas/campaign-state.schema.json),
plus an OPTIONAL frozen ``scope-baseline.json`` that makes the original-vs-current
delta exact.

It is a PURE projection: no clock, no LLM, no network, deterministic. It reads
only — it touches NO governed artifact (no charter, no schema, no constitution),
adds NO checkpoint, raises NO new authority. The campaign-result wiring in
run_loop guards it so a reporting bug can never break a run. This is the Phase-0
increment of the scope-ledger gap (investigation 2026-06-22); a requirement-
granular PRD ledger (covers_req_ids, Acceptance write-back) is a later phase.

THE BASELINE is this tool's OWN artifact, NOT engine-load-bearing: the campaign
plan mutates in place (a deliver_followup insertion edits subsprint_sequence —
campaign.py:656), so "what was added" is only knowable against a snapshot frozen
at sign-off. Freeze it ONCE, right after campaign_plan_signoff:

    scope_report.py --plan <plan.json> --freeze-baseline --campaign-home <home>

Later report runs auto-read ``<home>/scope-baseline.json``. WITHOUT a baseline,
delivered/pending/drift are still exact — only added/removed-milestone detection
is unavailable, and the report SAYS SO rather than guessing.

CLI:
    scope_report.py --plan <plan.json> --campaign-home <home>            # report
    scope_report.py --plan <plan.json> --state <state.json>              # explicit state
    scope_report.py --plan <plan.json> --freeze-baseline --out <path>    # freeze once
    scope_report.py --plan <plan.json> --campaign-home <home> --json     # full JSON
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

# A unit's persisted status (schemas/campaign-state.schema.json units[].status enum)
# projected onto a coverage class. "done" is the only DELIVERED state; everything
# dispatched-but-not-done is its own visible state; absent ⇒ not_started.
_UNIT_STATUS_TO_COVERAGE = {
    "done": "delivered",
    "in_progress": "in_progress",
    "halted": "halted",
    "failed": "failed",
    "pending": "not_started",
}
_DELIVERED = "delivered"
_IN_PROGRESS = "in_progress"
_NOT_STARTED = "not_started"

BASELINE_FILENAME = "scope-baseline.json"


def _pct(num: int, den: int) -> int:
    """Integer percent (0-100); 0 when the denominator is 0 (a valid plan always
    has >=1 milestone — minItems:1 — but the sub-sprint total can legitimately be
    0 before any decompose, so this stays total-safe)."""
    return round(100 * num / den) if den else 0


# --------------------------------------------------------------------------- #
# Baseline (this tool's own snapshot artifact — see module docstring).
# --------------------------------------------------------------------------- #
def freeze_baseline(plan: dict) -> dict:
    """The original-scope snapshot: each milestone's id + subsprint_sequence at
    freeze time. Ids drive the delta; objective is copied for a readable diff."""
    return {
        "campaign_id": plan.get("campaign_id"),
        "goal": plan.get("goal"),
        "milestones": [
            {"id": m.get("id"),
             "objective": m.get("objective"),
             "subsprint_sequence": list(m.get("subsprint_sequence") or [])}
            for m in (plan.get("milestones") or [])
        ],
    }


def baseline_path_for(home: str) -> str:
    return os.path.join(home, BASELINE_FILENAME)


def load_baseline(home: Optional[str]) -> Optional[dict]:
    """Read ``<home>/scope-baseline.json`` if present; None otherwise (the delta is
    then unavailable — reported honestly, never guessed). Never raises."""
    if not home:
        return None
    path = baseline_path_for(home)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Coverage projection (pure).
# --------------------------------------------------------------------------- #
def _milestone_status(milestone_index: int, cursor_milestone_index: int,
                      started: bool) -> str:
    """Backlog position -> coverage class. The campaign advances milestone_index
    ONLY on Acceptance-accept (campaign.py advance_milestone) and reaches len()
    only when the run is ``done`` (state validator campaign.py: "done only at the
    exhausted boundary"), so: ``mi < cursor`` ⟺ DELIVERED, ``mi == cursor`` ⟺ the
    one in-flight milestone, ``mi > cursor`` ⟺ never reached. ``started`` guards the
    cursor milestone: with NO persisted state (cursor defaults to 0) nothing is
    in-flight — the whole backlog is not_started."""
    if milestone_index < cursor_milestone_index:
        return _DELIVERED
    if started and milestone_index == cursor_milestone_index:
        return _IN_PROGRESS
    return _NOT_STARTED


def compute_coverage(plan: dict, state: Optional[dict],
                     baseline: Optional[dict] = None) -> dict:
    """Project ``(plan, state[, baseline])`` -> a structured coverage report.

    ``state`` is the persisted campaign-state dict (CampaignState.to_dict() shape);
    None (no run yet) ⇒ everything not_started. ``baseline`` is a freeze_baseline()
    snapshot; None ⇒ added/removed-milestone delta omitted (baseline_available
    False). Deterministic — safe to call from the runtime result path."""
    # Project over the SAME order the campaign runner executes (topological over
    # depends_on) — the cursor's milestone_index advances in that order, so raw
    # plan order would mis-map delivered/in_progress for a reordered plan. A
    # malformed plan (dup/cycle/unknown dep) never ran, so fall back to raw order.
    raw_milestones = list(plan.get("milestones") or [])
    try:
        from campaign import topological_order as _topo
        milestones = _topo(raw_milestones)
    except Exception:
        milestones = raw_milestones
    state = state or {}
    cursor_mi = (state.get("cursor") or {}).get("milestone_index", 0)
    campaign_status = state.get("status")
    started = campaign_status is not None   # a real persisted state has a status
    units = [u for u in (state.get("units") or []) if isinstance(u, dict)]

    # Exact original-vs-current delta is only possible against a frozen baseline.
    base_by_id = ({m.get("id"): m for m in (baseline.get("milestones") or [])}
                  if baseline else None)

    ms_reports: List[dict] = []
    drift_all: List[dict] = []
    ss_total = ss_delivered = 0

    for mi, milestone in enumerate(milestones):
        mid = milestone.get("id")
        plan_seq = list(milestone.get("subsprint_sequence") or [])
        plan_seq_set = set(plan_seq)
        ms_units = [u for u in units if u.get("milestone_id") == mid]
        # Last record wins (a re-dispatched/resumed sub-sprint appends a fresh unit).
        unit_by_ss = {u.get("subsprint_id"): u for u in ms_units}

        ss_reports = []
        for ss in plan_seq:
            unit = unit_by_ss.get(ss)
            ss_status = (_UNIT_STATUS_TO_COVERAGE.get(unit.get("status"), _NOT_STARTED)
                         if unit else _NOT_STARTED)
            ss_reports.append({"id": ss, "status": ss_status})
            ss_total += 1
            if ss_status == _DELIVERED:
                ss_delivered += 1

        # Dispatched but absent from the plan's CURRENT sequence — an honest drift
        # signal (a plan edited out from under the runner, or a mismatched id).
        drift = [{"milestone_id": mid, "subsprint_id": u.get("subsprint_id"),
                  "status": _UNIT_STATUS_TO_COVERAGE.get(u.get("status"), u.get("status"))}
                 for u in ms_units if u.get("subsprint_id") not in plan_seq_set]
        drift_all.extend(drift)

        record = {"id": mid, "objective": milestone.get("objective"),
                  "status": _milestone_status(mi, cursor_mi, started),
                  "subsprints": ss_reports,
                  "drift_dispatched_not_in_plan": drift}
        if base_by_id is not None:
            base = base_by_id.get(mid)
            base_seq_list = list((base or {}).get("subsprint_sequence") or [])
            base_seq = set(base_seq_list)
            record["added"] = base is None
            record["added_subsprints"] = (list(plan_seq) if base is None
                                          else [s for s in plan_seq if s not in base_seq])
            # iterate the baseline LIST (not the set) for deterministic order
            record["removed_subsprints"] = ([] if base is None
                                            else [s for s in base_seq_list if s not in plan_seq_set])
        ms_reports.append(record)

    # Drift also covers units whose milestone was REMOVED from the current plan
    # entirely (the per-milestone loop above only sees milestones still present);
    # "dispatched-but-not-in-plan" must be exact even without a baseline.
    current_ids = {m.get("id") for m in milestones}
    for u in units:
        if u.get("milestone_id") not in current_ids:
            drift_all.append({
                "milestone_id": u.get("milestone_id"),
                "subsprint_id": u.get("subsprint_id"),
                "status": _UNIT_STATUS_TO_COVERAGE.get(u.get("status"), u.get("status")),
            })

    delivered = sum(1 for r in ms_reports if r["status"] == _DELIVERED)
    in_progress = sum(1 for r in ms_reports if r["status"] == _IN_PROGRESS)
    not_started = sum(1 for r in ms_reports if r["status"] == _NOT_STARTED)

    added_ms: List[str] = []
    removed_ms: List[str] = []
    if base_by_id is not None:
        plan_ids = {m.get("id") for m in milestones}
        added_ms = [m.get("id") for m in milestones if m.get("id") not in base_by_id]
        removed_ms = [bid for bid in base_by_id if bid not in plan_ids]

    # The "continue?" menu (feeds the 1c continuation decision): every milestone
    # not yet delivered, with its still-open sub-sprints.
    remaining = [{"id": r["id"], "objective": r["objective"], "status": r["status"],
                  "open_subsprints": [s["id"] for s in r["subsprints"]
                                      if s["status"] != _DELIVERED]}
                 for r in ms_reports if r["status"] != _DELIVERED]

    return {
        "campaign_id": plan.get("campaign_id"),
        "goal": plan.get("goal"),
        "campaign_status": campaign_status,
        "baseline_available": base_by_id is not None,
        "totals": {
            "milestones": len(milestones),
            "milestones_delivered": delivered,
            "milestones_in_progress": in_progress,
            "milestones_not_started": not_started,
            "subsprints": ss_total,
            "subsprints_delivered": ss_delivered,
        },
        "pct": {
            "milestones_delivered": _pct(delivered, len(milestones)),
            "subsprints_delivered": _pct(ss_delivered, ss_total),
        },
        "added_milestones": added_ms,
        "removed_milestones": removed_ms,
        "drift": drift_all,
        "milestones": ms_reports,
        "remaining": remaining,
    }


# --------------------------------------------------------------------------- #
# Rendering.
# --------------------------------------------------------------------------- #
def summary_line(report: dict) -> dict:
    """The compact, STABLE machine subset emitted as ``SCOPE_COVERAGE=`` (a parse
    contract parallel to ``CAMPAIGN_STATUS=``, never folded into it)."""
    totals = report["totals"]
    return {
        "campaign_id": report.get("campaign_id"),
        "campaign_status": report.get("campaign_status"),
        "baseline_available": report.get("baseline_available"),
        "milestones_total": totals["milestones"],
        "milestones_delivered": totals["milestones_delivered"],
        "milestones_in_progress": totals["milestones_in_progress"],
        "milestones_not_started": totals["milestones_not_started"],
        "subsprints_total": totals["subsprints"],
        "subsprints_delivered": totals["subsprints_delivered"],
        "pct_milestones_delivered": report["pct"]["milestones_delivered"],
        "pct_subsprints_delivered": report["pct"]["subsprints_delivered"],
        "added_milestones": report.get("added_milestones") or [],
        "removed_milestones": report.get("removed_milestones") or [],
        "remaining_milestones": [r["id"] for r in (report.get("remaining") or [])],
    }


def render_text(report: dict) -> str:
    """A compact, scannable human block."""
    totals = report["totals"]
    pct = report["pct"]
    lines = ["--- scope coverage (signed backlog vs delivered) ---",
             f"goal           : {report.get('goal')}",
             (f"milestones     : {totals['milestones_delivered']}/{totals['milestones']} "
              f"delivered ({pct['milestones_delivered']}%)  "
              f"in_progress={totals['milestones_in_progress']} "
              f"not_started={totals['milestones_not_started']}")]
    if totals["subsprints"]:
        lines.append(f"sub-sprints    : {totals['subsprints_delivered']}/"
                     f"{totals['subsprints']} delivered ({pct['subsprints_delivered']}%)")
    if not report.get("baseline_available"):
        lines.append("baseline       : NOT frozen — added/removed-milestone delta "
                     "unavailable (run --freeze-baseline at campaign start)")
    else:
        added = report.get("added_milestones") or []
        removed = report.get("removed_milestones") or []
        lines.append(f"vs baseline    : added={added or '-'}  removed={removed or '-'}")
    drift = report.get("drift") or []
    if drift:
        lines.append(f"DRIFT          : {len(drift)} dispatched unit(s) not in the "
                     "current plan sequence")
    remaining = report.get("remaining") or []
    if remaining:
        lines.append("remaining (continue menu):")
        for r in remaining:
            open_ss = r.get("open_subsprints") or []
            suffix = f"  open: {', '.join(open_ss)}" if open_ss else ""
            lines.append(f"  - [{r['status']}] {r['id']}: {r.get('objective')}{suffix}")
    else:
        lines.append("remaining      : none — signed backlog fully delivered")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scope_report",
        description="Read-only scope-coverage report for a Campaign (Phase 0).")
    parser.add_argument("--plan", required=True, help="path to campaign-plan.json")
    parser.add_argument("--state", default=None,
                        help="path to campaign-state.json "
                             "(default: <campaign-home>/campaign-state.json)")
    parser.add_argument("--campaign-home", default=None,
                        help="campaign home dir (holds campaign-state.json + "
                             "scope-baseline.json)")
    parser.add_argument("--baseline", default=None,
                        help="path to a frozen scope-baseline.json "
                             "(default: auto from --campaign-home if present)")
    parser.add_argument("--freeze-baseline", action="store_true",
                        help="write the plan's scope snapshot as the frozen baseline "
                             "and exit (run ONCE right after campaign_plan_signoff)")
    parser.add_argument("--out", default=None,
                        help="output path for --freeze-baseline "
                             "(default: <campaign-home>/scope-baseline.json)")
    parser.add_argument("--json", action="store_true",
                        help="emit the full report as JSON instead of the text block")
    args = parser.parse_args(argv)

    try:
        plan = _read_json(args.plan)
    except (OSError, ValueError) as exc:
        print(f"scope_report: cannot read --plan: {exc}", file=sys.stderr)
        return 2

    if args.freeze_baseline:
        out = args.out or (baseline_path_for(args.campaign_home)
                           if args.campaign_home else None)
        if not out:
            print("scope_report: --freeze-baseline needs --out or --campaign-home",
                  file=sys.stderr)
            return 2
        parent = os.path.dirname(os.path.abspath(out))
        os.makedirs(parent, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(freeze_baseline(plan), fh, indent=2, sort_keys=True)
        print(f"scope_report: froze baseline -> {out}")
        return 0

    state_path = args.state or (os.path.join(args.campaign_home, "campaign-state.json")
                                if args.campaign_home else None)
    state = None
    if state_path and os.path.isfile(state_path):
        try:
            state = _read_json(state_path)
        except (OSError, ValueError) as exc:
            print(f"scope_report: cannot read state {state_path!r}: {exc}",
                  file=sys.stderr)
            return 2

    baseline = None
    if args.baseline:
        try:
            baseline = _read_json(args.baseline)
        except (OSError, ValueError) as exc:
            print(f"scope_report: cannot read --baseline: {exc}", file=sys.stderr)
            return 2
    elif args.campaign_home:
        baseline = load_baseline(args.campaign_home)

    report = compute_coverage(plan, state, baseline=baseline)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
        print("SCOPE_COVERAGE=" + json.dumps(summary_line(report), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
