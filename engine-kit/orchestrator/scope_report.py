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
# Δ-19 requirement projection (design §3.5/§3.6) — joins
# (ledger, signed campaign-plan covers_req_ids, campaign-state milestone_outcomes).
#
# Stays PURE / read-only / deterministic (a function of plan+state+ledger+charter):
# delivery_status is DERIVED from each milestone's TERMINAL outcome (never the cursor),
# customer_disposition is read straight from the ledger, conflicts + uncovered are
# reported (never silently reconciled). The ONLY engine surface is reporting.
# --------------------------------------------------------------------------- #
# Customer dispositions that RETIRE a REQ from the open views — but only when the REQ
# is NOT bound to (fresh-)signed scope (§3.3/§3.6).
_RETIRING_DISPOSITIONS = frozenset({"dropped", "skipped", "deferred", "modified"})
# milestone_outcomes terminal → derived per-REQ delivery_status (design §3.5.1).
_DELIVERED_TERMINALS = frozenset({"acceptance_pass_authoritative",
                                  "acceptance_pass_advisory_ship"})
# waived terminals → the reason rendered beside the REQ.
_WAIVED_TERMINALS = {
    "fix_required_ship": "fix_required_ship",
    "surface_approve_ship": "surface_approve",
    "acceptance_off": "acceptance_off",
    "out_of_scope_advance": "out_of_scope_advance",
}


def _signoff_status_and_hash(plan: dict, charter: Optional[dict]):
    """(status, live_hash) for the plan's F1 signoff, via the campaign module (lazy
    import — same contract as topological_order below). Never raises: a missing campaign
    module / bad input degrades to ('unsigned', None)."""
    try:
        import campaign as _cp
        status = _cp.signoff_status(plan, charter)
        signoff = plan.get("signoff") or {}
        live = _cp.compute_signed_scope_hash(
            plan, charter or {}, charter_ref=signoff.get("charter_ref")) \
            if isinstance(signoff, dict) and signoff.get("signed_by_human") else None
        return status, live
    except Exception:
        return ("signed" if plan.get("signed_by_human") else "unsigned"), None


def _snapshot_authentic(plan: dict) -> bool:
    """Whether the plan's stored signoff snapshot verifies against its OWN signed_scope_hash
    (via the campaign module; fail-closed False on any error or missing snapshot). scope_report
    trusts the stored prior-coverage snapshot ONLY when this is True (Codex R-P2a #2)."""
    try:
        import campaign as _cp
        return bool(_cp.signoff_snapshot_authentic(plan))
    except Exception:
        return False


def compute_requirement_coverage(plan: dict, state: Optional[dict], ledger: dict,
                                 charter: Optional[dict] = None) -> dict:
    """Project ``(ledger, signed plan covers_req_ids, state milestone_outcomes)`` → a
    structured per-REQ coverage report (design §3.6). Pure + deterministic."""
    state = state or {}
    ledger = ledger or {}
    reqs = [r for r in (ledger.get("requirements") or []) if isinstance(r, dict)]
    req_ids = {r.get("id") for r in reqs}

    # LIVE covers map (req → milestone) from the current plan; drift = a covers entry
    # naming a REQ absent from the ledger (asymmetry, reported read-only — §3.4).
    live_covers: dict = {}
    coverage_drift: List[dict] = []
    for m in (plan.get("milestones") or []):
        mid = m.get("id")
        for rid in (m.get("covers_req_ids") or []):
            live_covers[rid] = mid
            if rid not in req_ids:
                coverage_drift.append({"milestone_id": mid, "unknown_req_id": rid})

    outcomes = {o.get("milestone_id"): o
                for o in (state.get("milestone_outcomes") or [])
                if isinstance(o, dict) and o.get("milestone_id")}

    # Topological index (the runner's execution order) for the in_progress/not_started
    # fallback when a covered milestone has no recorded terminal outcome yet.
    raw_milestones = list(plan.get("milestones") or [])
    try:
        from campaign import topological_order as _topo
        index_of = {m.get("id"): i for i, m in enumerate(_topo(raw_milestones))}
    except Exception:
        index_of = {m.get("id"): i for i, m in enumerate(raw_milestones)}
    cursor_mi = (state.get("cursor") or {}).get("milestone_index", 0)
    started = state.get("status") is not None

    status, live_hash = _signoff_status_and_hash(plan, charter)
    fresh_signed = status == "signed"
    stale = status == "stale"
    blocked = status in ("stale", "pre_f1")   # signed-intent, but blocked pending re-sign
    fresh_signed_covers = dict(live_covers) if fresh_signed else {}

    # PRIOR signed coverage — reconstructed from the STORED snapshot (G4) so a stale
    # signoff still shows what WAS signed. TRUST the snapshot ONLY when it is
    # self-consistent with its OWN signed_scope_hash (Codex R-P2a #2: an unverified
    # snapshot could be edited to drop coverage); otherwise fail closed (below).
    snapshot_authentic = _snapshot_authentic(plan)
    signoff = plan.get("signoff") if isinstance(plan.get("signoff"), dict) else {}
    snapshot = (signoff or {}).get("scope_envelope") or {}
    prior_signed_covers: dict = {}
    if snapshot_authentic:
        for m in (snapshot.get("milestones") or []):
            for rid in (m.get("covers_req_ids") or []):
                prior_signed_covers[rid] = m.get("id")

    # A REQ whose ledger retirement is NOT settled because it is bound to signed scope.
    # fresh-signed always; while BLOCKED pending re-sign protect the blocked coverage so a
    # disposition can't silently retire a REQ the runner is re-pausing on (Codex R-P2a #1):
    #   - stale + authentic snapshot ⇒ the prior signed snapshot's covers;
    #   - stale + UNVERIFIABLE snapshot ⇒ fail closed: protect the LIVE covers too;
    #   - pre_f1 (no snapshot yet) ⇒ protect the LIVE covers (signed-intent, blocked).
    signed_bound = set(fresh_signed_covers)
    if status == "stale":
        signed_bound |= set(prior_signed_covers)
        if not snapshot_authentic:
            signed_bound |= set(live_covers)
    elif status == "pre_f1":
        signed_bound |= set(live_covers)

    def _delivery_status(rid):
        mid = live_covers.get(rid)
        if mid is None:
            return "not_covered", None, None
        term = (outcomes.get(mid) or {}).get("terminal")
        if term in _DELIVERED_TERMINALS:
            return "delivered", None, mid
        if term in _WAIVED_TERMINALS:
            return "waived", _WAIVED_TERMINALS[term], mid
        # No delivered/waived terminal recorded ⇒ NOT delivered (never read 'delivered'
        # off the cursor — design §3.5). Sub-classify by cursor position only.
        mi = index_of.get(mid)
        if started and mi is not None and mi <= cursor_mi:
            return "in_progress", None, mid
        return "not_started", None, mid

    requirements: List[dict] = []
    uncovered: List[str] = []
    invalid_signed: List[str] = []
    remaining: List[dict] = []
    delivered_n = waived_n = 0
    for r in reqs:
        rid = r.get("id")
        disp = r.get("customer_disposition")
        dstatus, dreason, covered_by = _delivery_status(rid)
        retiring = disp in _RETIRING_DISPOSITIONS
        validly_retired = retiring and rid not in signed_bound
        conflict = None
        if retiring and rid in fresh_signed_covers:
            # G2/F2: a retiring disposition on FRESH-signed scope is a conflict; the REQ
            # is KEPT in the open views until a re-sign reconciles it.
            conflict = "invalid_signed_disposition"
            invalid_signed.append(rid)
        elif retiring and blocked and rid in signed_bound:
            # blocked pending re-sign (stale snapshot OR pre-F1, OR a fail-closed
            # unverifiable snapshot): the retirement is NOT settled.
            conflict = "stale_signoff"
        item = {"id": rid, "statement": r.get("statement"),
                "customer_disposition": disp, "delivery_status": dstatus,
                "covered_by": covered_by, "signed_bound": rid in signed_bound,
                "conflict": conflict}
        if dreason:
            item["delivery_reason"] = dreason
        requirements.append(item)
        if dstatus == "delivered":
            delivered_n += 1
        elif dstatus == "waived":
            waived_n += 1
        # uncovered = in NO fresh-signed milestone AND not validly retired (the true gap).
        if rid not in fresh_signed_covers and not validly_retired:
            uncovered.append(rid)
        # continue menu = not delivered/waived AND not validly retired.
        if dstatus not in ("delivered", "waived") and not validly_retired:
            remaining.append({"id": rid, "statement": r.get("statement"),
                              "delivery_status": dstatus, "customer_disposition": disp})

    stale_block = None
    if blocked:
        def _cov_map(milestones):
            out = {}
            for m in (milestones or []):
                cov = list(m.get("covers_req_ids") or [])
                if cov:
                    out[m.get("id")] = cov
            return out
        # Emitted for any BLOCKED-pending-re-sign signoff (stale OR pre-F1). The prior
        # snapshot coverage is shown ONLY when the snapshot verified against its hash;
        # otherwise it is withheld (fail-closed) and the live coverage is what's protected.
        stale_block = {
            "status": status,                       # "stale" | "pre_f1"
            "stored_hash": (signoff or {}).get("signed_scope_hash"),
            "live_hash": live_hash,
            "snapshot_authentic": snapshot_authentic,
            "prior_signed_coverage": (_cov_map(snapshot.get("milestones"))
                                      if snapshot_authentic else {}),
            "live_coverage": _cov_map(plan.get("milestones")),
        }

    return {
        "campaign_id": plan.get("campaign_id"),
        "goal": plan.get("goal"),
        "ledger_present": True,
        "signoff_status": status,
        "requirements": requirements,
        "uncovered_requirements": uncovered,
        "invalid_signed_disposition": invalid_signed,
        "stale_signoff": stale_block,
        "coverage_drift": coverage_drift,
        "remaining": remaining,
        "totals": {
            "requirements": len(reqs),
            "delivered": delivered_n,
            "waived": waived_n,
            "uncovered": len(uncovered),
            "remaining": len(remaining),
        },
    }


def build_gap_report(coverage_report: dict) -> dict:
    """Δ-19 Phase 2-β — the ADVISORY completeness gap_report (schemas/gap-report.schema.json),
    a PURE projection of ``compute_requirement_coverage`` (coverage/ledger FACTS).

    The gap = requirement ids bound to FRESH-signed ``covers_req_ids`` (signoff_status ==
    'signed') whose §3.5.1-derived ``delivery_status`` is not yet delivered/waived
    (i.e. not_started / in_progress). When the plan is NOT fresh-signed (stale / pre_f1 /
    unsigned) there are no fresh-signed covers, so the in-envelope ``gap`` is EMPTY and the
    blocked-pending-re-sign state is carried only by ``signoff_status`` (the gap is the
    fresh-signed-but-undelivered set, never the blocked coverage — design §3.3.1 / §1.7-F).

    Generated ONLY from the coverage facts — NEVER from the Acceptance verdict's pass/fail
    clause semantics: this SOURCE separation is the completeness<->quality SEAL the gated
    §1.7-F path relies on. Deterministic (sorted output); the caller validates it against
    the schema and attaches it as an advisory artifact (nothing acts on it automatically)."""
    signoff = coverage_report.get("signoff_status")
    reqs = coverage_report.get("requirements") or []
    gap: List[dict] = []
    if signoff == "signed":
        for r in reqs:
            # When fresh-signed, live covers == fresh-signed covers, so a non-null
            # covered_by IS the fresh-signed covering milestone (compute_requirement_coverage).
            if r.get("covered_by") and r.get("delivery_status") in (_NOT_STARTED,
                                                                     _IN_PROGRESS):
                gap.append({"req_id": r.get("id"),
                            "delivery_status": r.get("delivery_status"),
                            "covered_by": r.get("covered_by")})
    gap.sort(key=lambda g: g.get("req_id") or "")
    t = coverage_report.get("totals") or {}
    return {
        "campaign_id": coverage_report.get("campaign_id"),
        "goal": coverage_report.get("goal"),
        "source": "requirement_coverage",
        "advisory": True,
        "ledger_present": True,
        "signoff_status": signoff,
        "gap": gap,
        "uncovered_requirements": sorted(
            coverage_report.get("uncovered_requirements") or []),
        "totals": {
            "requirements": t.get("requirements", 0),
            "delivered": t.get("delivered", 0),
            "waived": t.get("waived", 0),
            "gap": len(gap),
            "uncovered": t.get("uncovered", 0),
        },
    }


def requirement_summary_line(report: dict) -> dict:
    """The compact, STABLE machine subset emitted as ``REQUIREMENT_COVERAGE=`` — a parse
    contract parallel to SCOPE_COVERAGE=, emitted ONLY when a valid ledger is present."""
    t = report["totals"]
    return {
        "campaign_id": report.get("campaign_id"),
        "ledger_present": True,
        "signoff_status": report.get("signoff_status"),
        "requirements_total": t["requirements"],
        "delivered": t["delivered"],
        "waived": t["waived"],
        "uncovered": t["uncovered"],
        "uncovered_requirements": list(report.get("uncovered_requirements") or []),
        "invalid_signed_disposition": list(report.get("invalid_signed_disposition") or []),
        "stale_signoff": report.get("stale_signoff") is not None,
        "remaining_requirements": [r["id"] for r in (report.get("remaining") or [])],
    }


def render_requirements(report: dict) -> str:
    """A compact, scannable human block for the requirement projection."""
    t = report["totals"]
    lines = ["--- requirement coverage (PRD requirements vs delivered) ---",
             f"goal           : {report.get('goal')}",
             f"signoff        : {report.get('signoff_status')}",
             (f"requirements   : {t['delivered']}/{t['requirements']} delivered  "
              f"waived={t['waived']}  uncovered={t['uncovered']}")]
    if report.get("stale_signoff"):
        lines.append("STALE SIGNOFF   : stored signed_scope_hash != live hash — re-sign "
                     "required (prior signed coverage shown below, NOT settled)")
        prior = (report["stale_signoff"].get("prior_signed_coverage") or {})
        if prior:
            lines.append(f"  prior signed : {json.dumps(prior, sort_keys=True)}")
    inv = report.get("invalid_signed_disposition") or []
    if inv:
        lines.append(f"CONFLICT        : invalid_signed_disposition on {inv} "
                     "(retiring disposition on fresh-signed scope — kept open)")
    drift = report.get("coverage_drift") or []
    if drift:
        lines.append(f"DRIFT           : {len(drift)} covers_req_ids entr(y/ies) name a "
                     "REQ absent from the ledger")
    uncovered = report.get("uncovered_requirements") or []
    if uncovered:
        lines.append(f"uncovered (PRD gap): {uncovered}")
    remaining = report.get("remaining") or []
    if remaining:
        lines.append("remaining (continue menu):")
        for r in remaining:
            lines.append(f"  - [{r['delivery_status']}/{r.get('customer_disposition')}] "
                         f"{r['id']}: {r.get('statement')}")
    else:
        lines.append("remaining      : none — every requirement delivered/waived/retired")
    return "\n".join(lines)


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
    parser.add_argument("--requirement-ledger", default=None,
                        help="path to the requirement ledger (requirement-ledger.schema."
                             "json) — adds the Δ-19 per-REQ projection + REQUIREMENT_"
                             "COVERAGE= (emitted ONLY when a valid ledger is present)")
    parser.add_argument("--charter", default=None,
                        help="path to the campaign charter (YAML) — used to recompute the "
                             "live signed-scope hash for the stale-signoff check; "
                             "optional (absent ⇒ best-effort)")
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

    # Δ-19 requirement projection — ONLY when a (valid) ledger is supplied; otherwise the
    # output is byte-identical to today (SCOPE_COVERAGE= unchanged).
    req_report = None
    if args.requirement_ledger:
        try:
            ledger = _read_json(args.requirement_ledger)
        except (OSError, ValueError) as exc:
            print(f"scope_report: cannot read --requirement-ledger: {exc}",
                  file=sys.stderr)
            return 2
        # Fail-closed: an invalid ledger is not projected (and is not emitted).
        try:
            import campaign as _cp
            _cp._validate_or_raise(ledger, "requirement-ledger.schema.json", "ledger")
        except Exception as exc:  # noqa: BLE001 - schema/validator issue
            print(f"scope_report: invalid --requirement-ledger: {exc}", file=sys.stderr)
            return 2
        charter = None
        if args.charter:
            try:
                import driver as _drv
                charter = _drv.load_charter(args.charter)
            except Exception:  # noqa: BLE001 - charter optional for the projection
                charter = None
        req_report = compute_requirement_coverage(plan, state, ledger, charter=charter)

    if args.json:
        out = report
        if req_report is not None:
            out = {"scope": report, "requirement_coverage": req_report}
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        print(render_text(report))
        print("SCOPE_COVERAGE=" + json.dumps(summary_line(report), sort_keys=True))
        if req_report is not None:
            print(render_requirements(req_report))
            print("REQUIREMENT_COVERAGE="
                  + json.dumps(requirement_summary_line(req_report), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
