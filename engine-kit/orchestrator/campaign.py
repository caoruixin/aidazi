#!/usr/bin/env python3
"""campaign — the outer multi-milestone Campaign loop (P-B; design §5).

The Campaign tier is a HIGHER deterministic outer loop over the single-sub-sprint
Driver (delivery-loop §4.1): given an ordered milestone backlog (a *campaign plan*),
it auto-dispatches each sub-sprint and milestone through the UNCHANGED Driver and
HALTS only at human-authority gates — turning "stops and asks after every milestone"
into "drives to the goal, pausing only where human authority is required."

It is still the **Delivery Loop (Concept 2)**, one tier up — NOT the Auto Loop
(Constitution §1.7-E / §3.7). The Driver is not modified.

Design: archive/2026-06-20-autonomous-delivery-design.md §5 / §5.4a.

KEY runtime facts this module is built on (verified against driver.py):
  * A Driver run returns a `final_state`; the campaign ADVANCES only on `advance`
    (sub-sprint clean) or `done` (milestone accepted). EVERYTHING ELSE → PAUSE —
    including the guided pending states (`gate1_pending`, …), not just `STATE_HALTED`.
  * `Driver.run(resume=True)` re-enters ONLY states that set `halt_resume_state`
    (the 3 spec-refinement halts) OR the guided pending states; an ordinary
    human-gate `STATE_HALTED` short-circuits on resume (driver.py:2100). So resume
    uses TWO mechanisms — A (driver-resume) and B (campaign interprets + dispatches).
  * `$` cost is unavailable (no adapter reports it); the campaign budget uses the
    COUNTABLE proxies the Driver already surfaces (`run_loop` summary `spawn_count`).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # orchestrator/
_ENGINE_KIT_DIR = os.path.dirname(_THIS_DIR)                    # engine-kit/
_AUDIT_DIR = os.path.join(_ENGINE_KIT_DIR, "audit")
for _p in (_THIS_DIR, _ENGINE_KIT_DIR, _AUDIT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import audit_log as audit  # noqa: E402  (engine-kit/audit/audit_log.py — REUSE)
import loop_ingress as li  # noqa: E402  (milestone-tier git isolation + merge)

# A safe campaign_id — SAME discipline as the Driver's loop_id (letters/digits then
# ._- only; no path separators, no leading dot). It is interpolated into the audit
# ledger FILENAME, so it is validated FAIL-CLOSED at construction (Codex P-B impl
# blocking #1; mirrors driver.py _SAFE_LOOP_ID_RE).
_SAFE_CAMPAIGN_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
# The Driver checkpoint filename shape (<ts>__<checkpoint_id>__<scope>.md) — used to
# filter the checkpoints dir so a stray .md can't mask the real pause reason.
_CHECKPOINT_FILE_RE = re.compile(r"\A\d{8}-\d{6}__[A-Za-z0-9_]+__.+\.md\Z")

# --------------------------------------------------------------------------- #
# Fail-closed campaign-tier I/O validation (delivery-loop §4.2.7 discipline, one
# tier up). The campaign plan (admitted at construction) and the persisted campaign
# state (admitted on resume) are the campaign's two ingress boundaries; both are
# validated against their authored JSON schemas BEFORE they drive the outer loop, so
# a malformed plan or a corrupted/tampered state.json can never silently advance the
# milestone backlog. Mirrors the Driver's verdict-admission gate (driver._spawn →
# gate_hard_fail on a schema-invalid verdict), and the §3.5c sync guard already
# asserted statically by test_persisted_state_with_halted_unit_validates_against_schema.
_SCHEMA_CACHE: Dict[str, dict] = {}


def _find_schemas_dir(start: str = _ENGINE_KIT_DIR) -> Optional[str]:
    """Walk UP from ``start`` to the nearest ``schemas/`` dir (same discipline as
    driver._find_schemas_dir — robust to an adopter's vendored layout)."""
    cur = start
    while True:
        cand = os.path.join(cur, "schemas")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _campaign_schema(filename: str) -> dict:
    """Load (+ cache) a campaign schema by filename. Raises FileNotFoundError when
    the schemas/ dir or the file is absent — fail-closed: an unvalidatable campaign
    must NOT run rather than run un-checked."""
    if filename not in _SCHEMA_CACHE:
        base = _find_schemas_dir()
        if not base:
            raise FileNotFoundError(
                "schemas/ directory not found for campaign schema validation")
        with open(os.path.join(base, filename), encoding="utf-8") as fh:
            _SCHEMA_CACHE[filename] = json.load(fh)
    return _SCHEMA_CACHE[filename]


def _validate_or_raise(obj: Any, filename: str, what: str) -> None:
    """Fail-closed schema gate: validate ``obj`` against the named campaign schema
    and raise ValueError on the FIRST error. ``jsonschema`` is a declared kit
    dependency (the Driver/e2e_stage hard-require it); imported lazily so importing
    this module for its dataclasses alone does not require it."""
    from jsonschema import Draft202012Validator  # kit dependency (driver/e2e_stage)
    for err in Draft202012Validator(_campaign_schema(filename)).iter_errors(obj):
        raise ValueError(
            f"campaign {what} failed schema validation ({filename}): {err.message}")

# --------------------------------------------------------------------------- #
# Resume classes (design §5.4a) — how the campaign resumes after a pause.
# --------------------------------------------------------------------------- #
RESUME_DRIVER = "driver_resume"        # Mechanism A: Driver.run(resume=True) re-enters
RESUME_DISPATCH = "campaign_dispatch"  # Mechanism B: campaign interprets decision + dispatches
NON_PAUSE = "non_pause"                # never leaves the loop paused awaiting a human

# Mechanism A — gates the Driver itself re-enters on resume=True (halt_resume_state
# for the 3 spec-refinements; gate1 stays in the guided pre-state `gate1_pending`).
DRIVER_RESUME_CHECKPOINTS: frozenset = frozenset({
    "dev_spec_refinement",
    "review_spec_refinement",
    "acceptance_spec_refinement",
    "customer_gate1_signoff",
})
# Mechanism B — ordinary STATE_HALTED human gates: resume=True would no-op
# (driver.py:2100), so the campaign reads the resolved decision and dispatches the
# next unit / advances / ends.
DISPATCH_CHECKPOINTS: frozenset = frozenset({
    "post_gate1_scope_expansion",
    "scope_deviation",
    "close_taxonomy_C_or_D",
    "review_out_of_scope",
    "gate_hard_fail",
    "loop_controller_halt",
    "loop_controller_escalate",
    "acceptance_fix_required",
    "acceptance_cleanup_required",
    "acceptance_surface_approve",
    "advisory_acceptance_pass_signoff",
})
# Campaign-level gates the campaign itself emits (also Mechanism B).
CAMPAIGN_CHECKPOINTS: frozenset = frozenset({
    "campaign_plan_signoff",
    "campaign_budget_exhausted",
    "milestone_merge",
    # Track 2 Phase 2-γ / §1.7-F: the completeness-gap gate the campaign emits under
    # autonomy.level human_in_the_loop (a completeness gap_report routes to needs_human;
    # auto-dispatch is permitted only under human_on_the_loop or higher). Resolved Mechanism-B
    # via the adjust_scope decision shape (remediate|accept_gap|abort).
    "completeness_gap_review",
})
# Non-pause checkpoints — emitted by the Driver but auto-resolved / informational;
# they never leave the loop paused awaiting a human (design §5.4a).
NON_PAUSE_CHECKPOINTS: frozenset = frozenset({
    "acceptance_calibration_degraded",   # auto-resolved (resolver: orchestrator)
    "memory_feedback",                   # post-success, propose-only
    "loop_isolation_recommendation",     # ingress; proceeds on the default strategy
})

# The union of everything the campaign explicitly KNOWS about. The fail-closed
# inventory test (test_campaign.py) asserts every checkpoint_id the Driver can
# emit is in this set — so a future new Driver checkpoint can't silently slip past
# the campaign (it would force a human to classify it).
KNOWN_CHECKPOINTS: frozenset = (
    DRIVER_RESUME_CHECKPOINTS | DISPATCH_CHECKPOINTS | CAMPAIGN_CHECKPOINTS
    | NON_PAUSE_CHECKPOINTS
)


def classify_checkpoint(checkpoint_id: str) -> str:
    """Map a checkpoint_id to its resume class. An UNKNOWN id is fail-closed to
    RESUME_DISPATCH — an unmapped halt PAUSES for a human (never auto-advances)."""
    if checkpoint_id in DRIVER_RESUME_CHECKPOINTS:
        return RESUME_DRIVER
    if checkpoint_id in NON_PAUSE_CHECKPOINTS:
        return NON_PAUSE
    # DISPATCH_CHECKPOINTS, CAMPAIGN_CHECKPOINTS, and anything UNKNOWN → dispatch
    # (fail-closed: an unknown halt is treated as a human gate, never skipped).
    return RESUME_DISPATCH


# --------------------------------------------------------------------------- #
# Mechanism B — interpret a resolved checkpoint decision into a campaign action.
# Option labels are the ACTUAL labels the Driver writes (verified against driver.py;
# design §5.4a). When unsure, FAIL CLOSED to ACT_DELIVER_FOLLOWUP (surface, never
# auto-advance).
# --------------------------------------------------------------------------- #
ACT_ADVANCE_MILESTONE = "advance_milestone"   # milestone accepted → next milestone
ACT_ADVANCE_SUBSPRINT = "advance_subsprint"   # this sub-sprint done → next sub-sprint in THIS milestone
ACT_REDISPATCH_FRESH = "redispatch_fresh"     # blocker removed → re-run SAME unit fresh
ACT_DELIVER_FOLLOWUP = "deliver_followup"     # a new unit must be authored by Deliver → surface
ACT_END = "end"                               # abort → campaign ends
# Track 2 Phase 2-γ / §1.7-F: the human's adjust_scope decision at completeness_gap_review.
ACT_GAP_REMEDIATE = "gap_remediate"           # authorize ONE bounded in-envelope remediation round
ACT_GAP_ACCEPT = "gap_accept"                 # accept the incomplete signed scope → finish (no remediation)

# (pause_reason, choice) → action. `choice` is the human's checkpoint decision.
_DISPATCH_TABLE: Dict[str, Dict[Any, str]] = {
    "advisory_acceptance_pass_signoff": {
        "ship": ACT_ADVANCE_MILESTONE, "reject": ACT_DELIVER_FOLLOWUP},
    "acceptance_surface_approve": {
        "approve_ship": ACT_ADVANCE_MILESTONE,
        "route_to_deliver_fix": ACT_DELIVER_FOLLOWUP, "abort": ACT_END},
    "acceptance_cleanup_required": {
        # Acceptance PASSED but cleanup failed (browser-E2E residue); the Driver
        # HALTED (driver.py ~4106). retry_cleanup re-runs the SAME unit fresh so it
        # must RE-SATISFY Acceptance closure; abort ends. accept_residue_and_ship is
        # NOT listed here on purpose — it ships KNOWN residue, so it is gated on a
        # COMPLETE waiver in interpret_dispatch's special-case branch below (a bare
        # choice must NOT auto-ship). A missing/unknown choice falls through to the
        # table's ACT_DELIVER_FOLLOWUP default (fail-closed).
        "retry_cleanup": ACT_REDISPATCH_FRESH, "abort": ACT_END},
    "review_out_of_scope": {
        # review runs per SUB-SPRINT (mid-milestone) — accepting it advances the
        # sub-sprint, NOT the whole milestone (Codex inc-2 blocking #2).
        "accept_and_advance": ACT_ADVANCE_SUBSPRINT,
        "open_followup_subsprint": ACT_DELIVER_FOLLOWUP, "abort": ACT_END},
    "scope_deviation": {
        "accept_deviation": ACT_REDISPATCH_FRESH,
        "reject_deviation": ACT_DELIVER_FOLLOWUP, "abandon": ACT_END},
    "gate_hard_fail": {
        "re_run": ACT_REDISPATCH_FRESH,
        "accept_failure_and_route": ACT_DELIVER_FOLLOWUP,
        "deliver_fix_iteration": ACT_DELIVER_FOLLOWUP, "abort": ACT_END},
    "loop_controller_halt": {
        "re_run": ACT_REDISPATCH_FRESH, "review_outcome": ACT_DELIVER_FOLLOWUP,
        "abort": ACT_END},
    "loop_controller_escalate": {
        "review_and_route": ACT_DELIVER_FOLLOWUP,
        "accept_failure_and_route": ACT_DELIVER_FOLLOWUP, "abort": ACT_END},
    "close_taxonomy_C_or_D": {
        "resolve": ACT_DELIVER_FOLLOWUP, "abort": ACT_END},
    "post_gate1_scope_expansion": {
        "widen_approved_scope": ACT_DELIVER_FOLLOWUP,
        "narrow_plan": ACT_DELIVER_FOLLOWUP, "abort": ACT_END},
    "campaign_budget_exhausted": {
        "raise_cap": ACT_REDISPATCH_FRESH, "abort": ACT_END},
    "completeness_gap_review": {
        # §1.7-F adjust_scope: remediate authorizes ONE bounded, in-envelope remediation
        # round (the SAME deterministic seal/req_id-envelope/bounds gates as the auto path);
        # accept_gap finishes WITH the gap (no remediation); abort ends. A bare/unknown choice
        # fail-closes to ACT_DELIVER_FOLLOWUP (surface, never auto-remediate).
        "remediate": ACT_GAP_REMEDIATE,
        "accept_gap": ACT_GAP_ACCEPT,
        "abort": ACT_END},
    "milestone_merge": {
        "merge_now": ACT_ADVANCE_MILESTONE,
        "open_pr": ACT_ADVANCE_MILESTONE,
        "keep_branch": ACT_ADVANCE_MILESTONE,
        "abort": ACT_END},
}


# acceptance_cleanup_required → accept_residue_and_ship is a WAIVER, not a normal
# "continue": Acceptance PASSED but cleanup failed, so shipping leaves KNOWN residue.
# It is admissible ONLY on an explicit, auditable human waiver — ALL of `residue`,
# `rationale`, `evidence` plus a waiver marker (`waiver: true` OR a `waiver_id`).
# An incomplete/malformed waiver FAILS CLOSED (surface, do not ship). This mirrors the
# acceptance_fix_required special-case (which inspects decision fields, not a bare
# choice). The completeness + shape gate is `residue_waiver()` below.


def _nonempty_str(v: Any) -> bool:
    """A non-empty string — the documented shape for rationale / evidence / waiver_id
    and for each residue item (campaign-decision.schema.json)."""
    return isinstance(v, str) and bool(v)


def residue_waiver(decision: Optional[dict]) -> Optional[dict]:
    """Return the NORMALIZED waiver payload IFF `decision` carries a COMPLETE residue
    waiver; else None (fail-closed: an incomplete/malformed waiver is NOT a waiver and
    must NOT ship known residue).

    COMPLETE = residue (a NON-EMPTY list of non-empty strings) + rationale + evidence
    (non-empty strings) + a waiver MARKER (`waiver: true` OR a non-empty `waiver_id`),
    matching the documented campaign-decision.schema.json shapes. The shape checks are
    defense-in-depth for a PROGRAMMATIC decision_resolver — the file-based resolver
    already schema-validates — so a truthy-but-MALFORMED field (e.g. a non-string
    residue) FAILS CLOSED rather than shipping garbled/unattributable residue (Codex
    concern B).

    The returned payload records BOTH waiver-marker forms — `waiver` (bool: True when
    the boolean marker was used) AND `waiver_id` — so the campaign_acceptance_residue_
    waived audit attributes the waiver no matter which marker the human authored (Codex
    blocking 2: a `waiver: true` marker must NOT be dropped, recording `waiver_id: None`
    and omitting the marker → an un-attributable waiver)."""
    decision = decision or {}
    residue = decision.get("residue")
    rationale = decision.get("rationale")
    evidence = decision.get("evidence")
    waiver = decision.get("waiver")
    waiver_id = decision.get("waiver_id")
    if not (isinstance(residue, list) and residue
            and all(_nonempty_str(r) for r in residue)):
        return None
    if not (_nonempty_str(rationale) and _nonempty_str(evidence)):
        return None
    if not ((waiver is True) or _nonempty_str(waiver_id)):
        return None
    return {"residue": residue, "rationale": rationale, "evidence": evidence,
            "waiver": bool(waiver), "waiver_id": waiver_id}


def interpret_dispatch(pause_reason: str, decision: Optional[dict]) -> str:
    """Mechanism B: map a resolved checkpoint decision to a campaign action.
    Fail-closed: an unrecognized (reason, choice) → ACT_DELIVER_FOLLOWUP (surface
    for a human / Deliver; never auto-advance past it)."""
    decision = decision or {}
    # acceptance_fix_required carries `confirm: yes|no` (+ route) rather than a
    # single `choice` (Constitution §3.5).
    if pause_reason == "acceptance_fix_required":
        confirm = decision.get("confirm")
        if confirm in ("no", False):
            return ACT_ADVANCE_MILESTONE          # ship advisory; assume residual risk
        return ACT_DELIVER_FOLLOWUP               # confirm:yes + route → new unit
    # acceptance_cleanup_required: accept_residue_and_ship is gated on a COMPLETE
    # waiver (inspects decision fields, like acceptance_fix_required). retry_cleanup /
    # abort go through the table; a bare/incomplete ship → fail-closed surface.
    if pause_reason == "acceptance_cleanup_required":
        choice = decision.get("choice")
        if choice == "accept_residue_and_ship":
            return (ACT_ADVANCE_MILESTONE if residue_waiver(decision)
                    else ACT_DELIVER_FOLLOWUP)    # fail-closed: no waiver → do NOT ship
        return _DISPATCH_TABLE.get(pause_reason, {}).get(choice, ACT_DELIVER_FOLLOWUP)
    choice = decision.get("choice") or decision.get("confirm")
    return _DISPATCH_TABLE.get(pause_reason, {}).get(choice, ACT_DELIVER_FOLLOWUP)


# --------------------------------------------------------------------------- #
# Campaign state (persisted; resumable — the campaign analogue of driver state.json).
# --------------------------------------------------------------------------- #
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_DONE = "done"
STATUS_ENDED = "ended"


@dataclass
class CampaignState:
    campaign_id: str
    status: str = STATUS_RUNNING
    pause_reason: Optional[str] = None
    pause_checkpoint: Optional[str] = None
    milestone_index: int = 0
    subsprint_index: int = 0
    subsprints_run: int = 0
    total_spawns: int = 0
    wall_clock_minutes: float = 0.0
    units: List[dict] = field(default_factory=list)
    followup_baseline_seq: Optional[List[str]] = None  # subsprint_sequence snapshot at a deliver_followup pause
    # Track-2 T2-A/B4: the DURABLE freshness-block overlay. When a mid-run universal F1
    # freshness gate (_authority_fresh) finds the signed plan went STALE, the campaign
    # BLOCKS for re-sign as pause_reason='campaign_plan_signoff' WHILE preserving the
    # ORIGINAL gate here, so a post-re-sign resume returns to that gate. Persisted (NOT an
    # in-memory flag) so a crash mid-block never loses the original gate. Absent/None ⇒ no
    # block active (byte-identical to today).
    freshness_block: Optional[dict] = None
    # Track-2 T2-A/TD6: the engine-authored deliver_followup re-stamp record. The ONE
    # legitimate mid-campaign plan mutation (a follow-up sub-sprint inserted at cursor+1)
    # grows subsprint_sequence (inside the signed hash H), which would read 'stale'. The
    # engine advances the SINGLE signed epoch by pinning the authorized signed_scope_hash
    # here (+ append-only provenance) — NEVER writing the plan file (re-authorization needs
    # a human signoff artifact). Each invocation deterministically RE-APPLIES it to the
    # in-memory signoff (_reapply_engine_restamp) iff the live hash still equals the pinned
    # hash, so all freshness consumers agree (no divergence). Absent/None ⇒ no re-stamp.
    engine_restamp: Optional[dict] = None
    milestone_context: Optional[dict] = None   # active milestone git isolation (campaign-tier ingress)
    pending_milestone_advance: bool = False    # milestone DONE; cursor not advanced (at merge gate)
    # Δ-19 F3 (design §3.5.1): one TERMINAL close outcome per milestone, stamped at
    # close so scope_report can DERIVE delivery_status deterministically (delivered vs
    # waived-with-reason) — never inferred from cursor position. Additive; absent ⇒
    # today's behavior (a legacy state simply has no outcomes to project).
    milestone_outcomes: List[dict] = field(default_factory=list)
    # Track 2 Phase 2-γ / §1.7-F clause 2-3: persisted RUNTIME state for the pre-authorized
    # in-envelope completeness-remediation auto-route (campaign:_gap_followup_round). The
    # per-milestone counter, the gap-set history (for the proper-subset progress check), the
    # consecutive no-progress counter, and the audit of generated remediation stanzas. These
    # are the bounds the static charter validator CANNOT enforce (the gap-set is only knowable
    # at runtime). Additive; absent ⇒ no gap-followup has run (byte-identical to today).
    gap_followup_state: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "campaign_id": self.campaign_id,
            "status": self.status,
            "pause_reason": self.pause_reason,
            "pause_checkpoint": self.pause_checkpoint,
            "cursor": {"milestone_index": self.milestone_index,
                       "subsprint_index": self.subsprint_index},
            "spent": {"subsprints_run": self.subsprints_run,
                      "total_spawns": self.total_spawns,
                      "wall_clock_minutes": self.wall_clock_minutes},
            "units": self.units,
            "followup_baseline_seq": self.followup_baseline_seq,
            "milestone_context": self.milestone_context,
            "pending_milestone_advance": self.pending_milestone_advance,
            "milestone_outcomes": self.milestone_outcomes,
        }
        # §1.7-F: emit gap_followup_state ONLY when a gap-followup has run, so a campaign
        # that never enters the gap-followup path persists a byte-identical state.json
        # (Codex R1 NB-2). Absent ⇒ from_dict defaults it to {}.
        if self.gap_followup_state:
            d["gap_followup_state"] = self.gap_followup_state
        # Track-2: the freshness overlay + the engine re-stamp are emitted ONLY when
        # active, so a campaign that never blocks for re-sign / never inserts a
        # deliver_followup persists a byte-identical state.json (additivity).
        if self.freshness_block:
            d["freshness_block"] = self.freshness_block
        if self.engine_restamp:
            d["engine_restamp"] = self.engine_restamp
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CampaignState":
        cur = d.get("cursor") or {}
        spent = d.get("spent") or {}
        return cls(
            campaign_id=d["campaign_id"], status=d.get("status", STATUS_RUNNING),
            pause_reason=d.get("pause_reason"),
            pause_checkpoint=d.get("pause_checkpoint"),
            milestone_index=cur.get("milestone_index", 0),
            subsprint_index=cur.get("subsprint_index", 0),
            subsprints_run=spent.get("subsprints_run", 0),
            total_spawns=spent.get("total_spawns", 0),
            wall_clock_minutes=spent.get("wall_clock_minutes", 0.0),
            units=list(d.get("units") or []),
            followup_baseline_seq=d.get("followup_baseline_seq"),
            freshness_block=d.get("freshness_block"),
            engine_restamp=d.get("engine_restamp"),
            milestone_context=d.get("milestone_context"),
            pending_milestone_advance=bool(d.get("pending_milestone_advance", False)),
            milestone_outcomes=list(d.get("milestone_outcomes") or []),
            gap_followup_state=dict(d.get("gap_followup_state") or {}))


# --------------------------------------------------------------------------- #
# Plan helpers.
# --------------------------------------------------------------------------- #
def topological_order(milestones: List[dict]) -> List[dict]:
    """Deterministic topological order over `depends_on` (default: backlog order).
    Raises ValueError on a DUPLICATE id, an unknown dependency, or a cycle
    (fail-closed; a future parallel runner consumes the same DAG)."""
    ids = [m["id"] for m in milestones]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        # A dict-by-id would silently drop earlier duplicates (Codex P-B impl
        # blocking #4) — reject instead.
        raise ValueError(f"campaign plan has duplicate milestone id(s): {dupes}")
    by_id = {m["id"]: m for m in milestones}
    order: List[dict] = []
    visited: Dict[str, int] = {}  # 0=visiting, 1=done

    def visit(mid: str, stack: tuple) -> None:
        if visited.get(mid) == 1:
            return
        if visited.get(mid) == 0:
            raise ValueError(f"campaign plan has a dependency cycle at {mid!r}")
        if mid not in by_id:
            raise ValueError(f"campaign plan depends_on unknown milestone {mid!r}")
        visited[mid] = 0
        for dep in by_id[mid].get("depends_on") or []:
            visit(dep, stack + (mid,))
        visited[mid] = 1
        order.append(by_id[mid])

    for m in milestones:  # iterate in declared order for determinism
        visit(m["id"], ())
    return order


def _iso_minutes(start_iso: str, now_iso: str) -> float:
    """Whole-minutes elapsed between two ISO-8601 stamps (best-effort; 0.0 on a
    parse failure — wall-clock is a soft cap, never a correctness gate)."""
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        return max(0.0, (now - start).total_seconds() / 60.0)
    except (ValueError, AttributeError):
        return 0.0


# --------------------------------------------------------------------------- #
# The Campaign runner.
# --------------------------------------------------------------------------- #
# A `run_unit` callable drives ONE sub-sprint through the Driver and returns a
# summary dict: {final_state, spawn_count, pause_reason?, loop_id?}. The campaign
# calls it as `run_unit(subsprint_id, milestone_id=, subsprint_sequence=, resume=)`
# — passing the milestone's LIVE sequence so the production wrapper can derive a
# per-milestone execution context (per-milestone Acceptance). Production wires a thin
# wrapper around scheduling.run_loop (which already returns final_state + spawn_count)
# that also derives pause_reason from the latest checkpoint file; tests inject a
# deterministic fake. This dependency injection mirrors the Driver's injected clock /
# adapters / gate_resolver.
RunUnit = Callable[..., dict]

_ADVANCE_STATES = frozenset({"advance"})
_MILESTONE_DONE_STATES = frozenset({"done"})

# Δ-19 F3 (design §3.5.1): map a RESUME-dispatch milestone-advance (a human ship
# decision at an Acceptance gate) to its terminal-close enum (campaign-state
# milestone_outcomes[].terminal). delivered ⟸ acceptance_pass_*; waived ⟸ the rest.
# acceptance_cleanup_required (accept_residue_and_ship) is reached only AFTER an
# Acceptance PASS that needed a human ship-signoff (the residue waiver) — exactly the
# advisory-pass+ship-signoff shape — so it maps to acceptance_pass_advisory_ship
# (delivered: "delivered requires a recorded Acceptance pass + any required signoff").
_RESUME_ADVANCE_TERMINAL: Dict[str, str] = {
    "advisory_acceptance_pass_signoff": "acceptance_pass_advisory_ship",
    "acceptance_fix_required": "fix_required_ship",
    "acceptance_surface_approve": "surface_approve_ship",
    "acceptance_cleanup_required": "acceptance_pass_advisory_ship",
}

# --------------------------------------------------------------------------- #
# Track 2 Phase 2-γ / Constitution §1.7-F — pre-authorized in-envelope completeness
# remediation (gap-driven follow-up). The dispositions the dedicated, fail-closed
# gap-followup engine (_gap_followup_round) returns to run()'s OUTER loop.
# --------------------------------------------------------------------------- #
GAP_DONE = "gap_done"          # no in-envelope gap (or no ledger / human-accepted) → STATUS_DONE. A STALE/pre-F1 plan does NOT finish here — it re-pauses for re-sign (T2-A B3).
GAP_CONTINUE = "gap_continue"  # a bounded remediation round was dispatched + completed → re-check the gap
GAP_PAUSED = "gap_paused"      # HALTED + escalated to needs_human (the campaign is paused; run() returns it)
GAP_ENDED = "gap_ended"        # the human aborted at completeness_gap_review

# The completeness gate the campaign emits for §1.7-F. ONE checkpoint carries BOTH the
# human_in_the_loop pre-dispatch review AND every clause-3 fail-closed escalation
# (distinguished by the audit/extra `gap_status`); both are resolved by the SAME
# adjust_scope decision (remediate|accept_gap|abort).
GAP_REVIEW_CHECKPOINT = "completeness_gap_review"

# Schema defaults (campaign-plan.schema.json gap_followup) — mirrored so an ABSENT
# gap_followup block uses conservative engine defaults, never an unbounded value.
GAP_FOLLOWUP_DEFAULT_MAX_SUBSPRINTS = 3
# §1.7-F clause 2/3: the gap req_id-set MUST be a strict PROPER SUBSET of the prior round;
# a non-shrinking round HALTs (it is not "retried up to N" — Codex R5 B2). So the default
# halt-threshold is 1 — the FIRST non-shrinking round escalates to needs_human. The
# charter_validator (Step 4) rejects a higher (non-shrink-tolerating) value as a §1.7-D
# evasion.
GAP_FOLLOWUP_DEFAULT_MAX_NO_PROGRESS = 1
# §1.7-F clause 2: when the campaign plan declares NO countable budget AND the charter
# declares no budget.max_fix_rounds_total, the gap-followup dimension still gets a
# conservative TOTAL-rounds effective-cap — it does NOT inherit today's unbounded default.
GAP_FOLLOWUP_DEFAULT_EFFECTIVE_CAP = 3

# §1.7-F: no-confirm auto-dispatch is permitted ONLY under human_on_the_loop or higher.
# human_in_the_loop routes a completeness gap_report to needs_human (the
# completeness_gap_review pause); the charter default (absent) is human_in_the_loop.
_AUTO_GAP_DISPATCH_LEVELS = frozenset({
    "human_on_the_loop", "fully_autonomous_within_budget"})

# Milestone terminal outcomes that record a QUALITY fault or a HUMAN ship/scope waiver —
# INELIGIBLE for no-confirm completeness gap-followup (§1.7-F clause 0: any quality fault
# routes to human-confirm as today). Defense-in-depth: build_gap_report already EXCLUDES
# every waived terminal from the gap (the gap is not_started/in_progress only), so a gap
# milestone never carries one of these — but if a bug/tamper put one in the gap, the
# eligibility seal FAILS CLOSED rather than auto-overriding a recorded human decision.
_QUALITY_FAULT_TERMINALS = frozenset({
    "fix_required_ship", "surface_approve_ship", "out_of_scope_advance"})


class Campaign:
    """Deterministic outer loop over a campaign plan. Pure except for the injected
    `run_unit` (the only non-determinism) + filesystem state/audit."""

    def __init__(self, plan: dict, run_dir: str, run_unit: RunUnit, *,
                 clock: Callable[[], str], audit_dir: Optional[str] = None,
                 repo_dir: Optional[str] = None,
                 charter: Optional[dict] = None,
                 ledger_path: Optional[str] = None):
        self.plan = plan
        self.run_dir = run_dir
        self.run_unit = run_unit
        self.clock = clock
        # Δ-19 F1/G1: the resolved campaign charter is needed to recompute the LIVE
        # signed scope-envelope (the resolved functional-acceptance {mode,source}
        # inherits the charter default when the milestone is silent — design §3.3.1).
        # OPTIONAL; absent ⇒ the F1 integrity check (only active when the plan opts in
        # via a `signoff` block or any covers_req_ids) can't verify and fails closed.
        self.charter = charter
        self.repo_dir = os.path.abspath(repo_dir) if repo_dir else None
        # Fail-closed plan ingress: validate the WHOLE plan against
        # schemas/campaign-plan.schema.json BEFORE any field access or dispatch, so a
        # malformed backlog cannot enter the outer loop. The schema pins the
        # campaign_id/goal/milestones shapes; the semantic checks below (path-safe id,
        # topological cycle, per-milestone sub-sprint uniqueness) cover what the schema
        # cannot express. A KeyError on plan["campaign_id"] below is now unreachable —
        # the schema's required:["campaign_id",…] rejects it first with a clear message.
        _validate_or_raise(plan, "campaign-plan.schema.json", "plan")
        self.campaign_id = plan["campaign_id"]
        if not _SAFE_CAMPAIGN_ID_RE.match(self.campaign_id or ""):
            raise ValueError(
                f"unsafe campaign_id {self.campaign_id!r}: must match "
                f"{_SAFE_CAMPAIGN_ID_RE.pattern} — it is interpolated into the audit "
                f"ledger path (fail-closed, like the Driver's loop_id guard)")
        self.milestones = topological_order(plan.get("milestones") or [])
        for m in self.milestones:
            seq = m.get("subsprint_sequence") or []
            dupes = sorted({s for s in seq if seq.count(s) > 1})
            if dupes:
                # The id-novelty follow-up check (§ resume) AND the per-unit loop_id
                # hashing key on (campaign, milestone, subsprint) — both REQUIRE
                # sub-sprint ids unique within a milestone (Codex inc-2 round-4).
                raise ValueError(
                    f"milestone {m['id']!r} has duplicate sub-sprint id(s): {dupes}")
        # Δ-19 §3.4 cross-milestone coverage validator (JSON Schema enforces uniqueness
        # only WITHIN a milestone's covers_req_ids array; the at-most-one-covering-
        # milestone-per-REQ rule is a cross-array constraint it cannot express). A REQ
        # named by two milestones is fail-closed at construction. Additive: a plan with
        # no covers_req_ids never trips it (byte-identical to today).
        _covering: Dict[str, str] = {}
        for m in self.milestones:
            for rid in (m.get("covers_req_ids") or []):
                prior = _covering.get(rid)
                if prior is not None:
                    raise ValueError(
                        f"requirement {rid!r} is covered by more than one milestone "
                        f"({prior!r} and {m['id']!r}) — Phase-1 enforces at-most-one "
                        f"covering milestone per REQ (Δ-19 §3.4)")
                _covering[rid] = m["id"]
        # Δ-19 §3.5/§5.4: validate the requirement ledger when one is wired (fail-closed
        # ingress, mirroring the plan/state gates). Load + schema-validate ONLY; the
        # engine NEVER writes the ledger back (delivery_status is a derived projection).
        self.ledger_path = ledger_path
        self.ledger: Optional[dict] = None
        # ABSENT vs PRESENT-BUT-BROKEN (Codex R2): lexists (not isfile) so a configured
        # path that is a directory / broken symlink / unreadable is PRESENT ⇒ fail closed,
        # not silently dormant. Only a path with no entry at all stays dormant (additive).
        if ledger_path and os.path.lexists(ledger_path):
            try:
                with open(ledger_path, encoding="utf-8") as fh:
                    led = json.load(fh)
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"campaign requirement ledger present but unreadable/malformed: {exc}")
            _validate_or_raise(led, "requirement-ledger.schema.json", "ledger")
            # OW-M3: a duplicate requirement id is an ambiguous surface classification the
            # JSON Schema cannot catch — fail closed so the {rid: surface} basis is
            # unambiguous for the mandate + the signed hash.
            dups = duplicate_requirement_ids(led)
            if dups:
                raise ValueError(
                    f"campaign requirement ledger has duplicate requirement id(s): {dups}")
            self.ledger = led
        self.budget = plan.get("budget") or {}
        iso = plan.get("milestone_isolation") or {}
        # Legacy top-level isolation_strategy (shared|worktree) → map when milestone_isolation absent.
        legacy = plan.get("isolation_strategy")
        default_iso = iso.get("default_strategy")
        if not default_iso and legacy == "worktree":
            default_iso = li.STRATEGY_NEW_WORKTREE
        elif not default_iso and legacy == "shared":
            default_iso = li.STRATEGY_CURRENT_BRANCH
        self._milestone_isolation = {
            "default_strategy": default_iso or li.STRATEGY_CURRENT_BRANCH,
            "branch_name_template": iso.get("branch_name_template")
                or "milestone/{campaign_id}/{milestone_id}",
            "worktree_root": iso.get("worktree_root"),
            "merge_prompt_at_close": iso.get("merge_prompt_at_close", True),
            "cleanup_policy": iso.get("cleanup_policy") or li.CLEANUP_KEEP,
        }
        self._trunk_branch = plan.get("trunk_branch") or "main"
        os.makedirs(run_dir, exist_ok=True)
        self.state_path = os.path.join(run_dir, "campaign-state.json")
        self.audit_ledger = audit.audit_path(
            self.campaign_id, audit_dir or os.path.join(run_dir, "audit"))
        self.state = CampaignState(campaign_id=self.campaign_id)
        # Wall-clock spend ACCUMULATES across resume (Codex P-B impl blocking #2):
        # _base_wall = total persisted from prior invocations; we add only this
        # invocation's active delta from _invocation_start.
        self._base_wall: float = 0.0
        self._invocation_start: Optional[str] = None

    # ----- persistence + audit ------------------------------------------- #
    def _save(self) -> None:
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(self.state.to_dict(), fh, indent=2, sort_keys=True)

    def _audit(self, type_: str, payload: dict) -> None:
        audit.append_event(self.campaign_id, type_, payload,
                            ts=self.clock(), path=self.audit_ledger)

    def _load(self) -> bool:
        if not os.path.isfile(self.state_path):
            return False
        with open(self.state_path, encoding="utf-8") as fh:
            data = json.load(fh)
        # Fail-closed resume ingress, TWO layers:
        #  (1) STRUCTURAL — the persisted state must match campaign-state.schema.json
        #      (the runtime enforcement of the runtime↔schema sync that
        #      test_persisted_state_with_halted_unit_validates_against_schema asserts).
        _validate_or_raise(data, "campaign-state.schema.json", "state")
        #  (2) SEMANTIC — a schema-VALID state can still be wrong FOR THIS plan: a state
        #      file from a DIFFERENT campaign, or a cursor that points PAST the backlog
        #      (which would silently skip the `while milestone_index < len(milestones)`
        #      loop and mark the campaign done without running it). Bind the state to
        #      this campaign + plan before it can drive the loop.
        self._check_state_consistency(data)
        self.state = CampaignState.from_dict(data)
        return True

    def _has_unit(self, units: list, milestone_id: str,
                  subsprint_id: Optional[str] = None) -> bool:
        """Did the runner record ANY unit for a milestone (or, when ``subsprint_id`` is
        given, that specific sub-sprint within it)? The runner appends a unit for every
        sub-sprint it dispatches, so anything the cursor has moved PAST must have ≥1
        unit. Presence ONLY — never the unit's final_state: the cursor legitimately
        advances past a HALTED unit (an acceptance-gated milestone keeps a
        final_state='halted' terminal unit after it ships; a human-resolved
        ACT_ADVANCE_SUBSPRINT advances past an accepted review_out_of_scope halt; a
        deliver_followup jump advances past the halted origin). Reading completion from
        final_state would false-reject all three (verified)."""
        return any(
            isinstance(u, dict) and u.get("milestone_id") == milestone_id
            and (subsprint_id is None or u.get("subsprint_id") == subsprint_id)
            for u in units)

    def _check_state_consistency(self, data: dict) -> None:
        """Fail-closed semantic gate on a resumed state (post-schema). Binds the
        persisted state to THIS campaign + plan AND requires the WHOLE state (cursor +
        status + unit ledger) to be a configuration the runner could actually have
        PERSISTED — so a schema-valid but tampered/bug-written state cannot silently
        skip the backlog or jump to done.

        Invariants enforced (each verified to hold at every `_save()` the runner emits,
        INCLUDING the advisory-acceptance resume flow):
          * `campaign_id` matches the plan.
          * the cursor is in range (`0 <= milestone_index <= len(milestones)`,
            `subsprint_index <= len(seq)`).
          * PREFIX: every milestone the cursor has moved PAST has ≥1 recorded unit —
            you cannot have advanced past a milestone that never ran (closes the
            silent-skip hole). This deliberately checks PRESENCE, not advance/done
            final_state, because an acceptance-gated milestone keeps a 'halted'
            terminal unit after it ships (verified) — asserting completion would
            false-reject that legitimate flow.
          * CURRENT milestone: `subsprint_index` equals its advanced-unit count (the
            cursor is lock-step with the ledger). The `== len(seq)` boundary is the
            legitimate crash window between an advance `_save()` and the milestone reset.
          * STATUS: `done` only at the exhausted boundary (`milestone_index == len`);
            `paused` only INSIDE a milestone (never at a completed boundary — a pause
            lands on a halted sub-sprint, `subsprint_index < len(seq)`, or an
            empty-sequence decompose pause). `ended` (abort) may sit mid-backlog."""
        sid = data.get("campaign_id")
        if sid != self.campaign_id:
            raise ValueError(
                f"campaign state campaign_id {sid!r} does not match the plan's "
                f"{self.campaign_id!r} — refusing to resume a different campaign's "
                f"state against this plan (fail-closed)")
        status = data.get("status")
        cur = data.get("cursor") or {}
        mi = cur.get("milestone_index", 0)
        si = cur.get("subsprint_index", 0)
        units = data.get("units") or []
        n_ms = len(self.milestones)
        if mi > n_ms:
            raise ValueError(
                f"campaign state cursor.milestone_index {mi} exceeds the plan's "
                f"{n_ms} milestone(s) — out-of-range cursor (fail-closed)")
        # PREFIX: a milestone the cursor moved past must have ≥1 recorded unit — else
        # resuming at `mi` silently skips earlier work that never ran (the silent-skip
        # hole). Presence-only by design (see the docstring's acceptance-flow note).
        for j in range(mi):
            if not self._has_unit(units, self.milestones[j]["id"]):
                raise ValueError(
                    f"campaign state cursor.milestone_index {mi} skips milestone "
                    f"{self.milestones[j]['id']!r} which has NO recorded unit — would "
                    f"silently skip unrun work (fail-closed)")
        # STATUS_DONE only at the exhausted boundary (the prefix check then guarantees
        # every milestone ran). STATUS_ENDED (abort) is exempt — it may be mid-backlog.
        if status == STATUS_DONE and mi != n_ms:
            raise ValueError(
                f"campaign state status is 'done' but the cursor.milestone_index {mi} "
                f"has not reached the backlog end ({n_ms}) — not a reachable done "
                f"state (fail-closed)")
        if mi == n_ms:
            # The done/exhausted boundary. A PAUSED campaign is normally paused INSIDE a
            # milestone, so it cannot sit here — EXCEPT the Track 2 Phase 2-γ / §1.7-F
            # gap-followup gate, which by design fires AT backlog-exhausted (the cursor
            # stays at (len, 0); remediation is dispatched directly, never via the cursor).
            # So a completeness_gap_review pause at this boundary is the ONE legitimate
            # paused-at-end state — AND only with its per-pause NONCE checkpoint: a null
            # pause_checkpoint here is a corrupted/bug-written state that would let the
            # resolver bind a checkpoint:null decision and bypass the nonce, so it is
            # fail-closed (Codex R2 B3).
            if status == STATUS_PAUSED and (
                    data.get("pause_reason") != GAP_REVIEW_CHECKPOINT
                    or not data.get("pause_checkpoint")):
                raise ValueError(
                    "campaign state is paused but the cursor is at the backlog end "
                    f"({n_ms}) — a paused campaign pauses inside a milestone, except a "
                    "completeness_gap_review pause WITH its nonce checkpoint (fail-closed)")
            if si != 0:
                raise ValueError(
                    f"campaign state cursor at the backlog end ({n_ms}) has "
                    f"subsprint_index {si}, not 0 — not a reachable cursor (fail-closed)")
            return
        # mi < n_ms — the current (in-progress) milestone.
        ms = self.milestones[mi]
        seq = list(ms.get("subsprint_sequence") or [])
        if si > len(seq):
            raise ValueError(
                f"campaign state cursor.subsprint_index {si} exceeds milestone "
                f"{ms['id']!r}'s {len(seq)} sub-sprint(s) — out-of-range cursor "
                f"(fail-closed)")
        # Each sub-sprint the cursor has PASSED within the current milestone must have
        # ≥1 recorded unit — presence, NOT final_state (same rationale as the prefix
        # check). The cursor legitimately advances past a HALTED unit on a human-resolved
        # ACT_ADVANCE_SUBSPRINT (an accepted review_out_of_scope) or a deliver_followup
        # insertion (campaign.py run-loop), neither of which is final_state='advance'.
        # This still rejects a boundary cursor (subsprint_index == len(seq)) with no
        # units behind it, without false-rejecting those non-'advance' advances.
        for k in range(si):
            if not self._has_unit(units, ms["id"], seq[k]):
                raise ValueError(
                    f"campaign state cursor.subsprint_index {si} for milestone "
                    f"{ms['id']!r} passed sub-sprint {seq[k]!r} which has NO recorded "
                    f"unit — inconsistent cursor/ledger (fail-closed)")
        # A PAUSE lands on a HALTED sub-sprint (subsprint_index < len(seq)), or on an
        # empty-sequence decompose pause — never at a COMPLETED non-empty boundary.
        if status == STATUS_PAUSED and seq and si >= len(seq):
            raise ValueError(
                f"campaign state is paused at milestone {ms['id']!r}'s completed "
                f"boundary (subsprint_index {si} == {len(seq)}) — a pause lands on a "
                f"halted sub-sprint inside the sequence (fail-closed)")

    # ----- budget (countable proxies; design §5.4a) ---------------------- #
    def _over_budget(self) -> Optional[str]:
        b = self.budget
        if b.get("max_subsprints") and self.state.subsprints_run >= b["max_subsprints"]:
            return "max_subsprints"
        if b.get("max_total_spawns") and self.state.total_spawns >= b["max_total_spawns"]:
            return "max_total_spawns"
        if (b.get("max_wall_clock_minutes")
                and self.state.wall_clock_minutes >= b["max_wall_clock_minutes"]):
            return "max_wall_clock_minutes"
        return None

    def _pause(self, reason: str, checkpoint: Optional[str], audit_type: str,
               extra: Optional[dict] = None) -> CampaignState:
        self.state.status = STATUS_PAUSED
        self.state.pause_reason = reason
        self.state.pause_checkpoint = checkpoint
        self._audit(audit_type, {"pause_reason": reason,
                                 "checkpoint": checkpoint, **(extra or {})})
        self._save()
        return self.state

    def _end(self, reason: str) -> CampaignState:
        self.state.status = STATUS_ENDED
        self.state.pause_reason = reason
        self._audit("campaign_ended", {"reason": reason})
        self._save()
        return self.state

    def _repause(self, reason: str, why: str) -> str:
        self._pause(reason, self.state.pause_checkpoint, "campaign_repause",
                    {"why": why})
        return "paused"

    # ----- milestone-tier git isolation (campaign Loop Ingress) ------------- #
    def _milestone_isolation_cfg(self) -> dict:
        return self._milestone_isolation

    def _resolve_milestone_strategy(self, milestone: dict) -> str:
        """Per-milestone isolation strategy (inherit → plan default)."""
        raw = milestone.get("isolation_strategy") or "inherit"
        if raw == "inherit":
            return self._milestone_isolation["default_strategy"]
        return raw

    def _milestone_ingress_enabled(self) -> bool:
        return self.repo_dir is not None

    def _ensure_milestone_context(self, milestone: dict) -> None:
        """At the START of a milestone: set up git isolation once (campaign-tier).

        Sub-sprint Driver ingress stays on current_branch inside the milestone
        work_dir — the milestone branch/worktree already exists."""
        if not self._milestone_ingress_enabled():
            return
        mid = milestone["id"]
        if (self.state.milestone_context
                and self.state.milestone_context.get("milestone_id") == mid):
            return  # already set up (resume mid-milestone)
        strategy = self._resolve_milestone_strategy(milestone)
        branch_name = li.render_branch_name(
            self._milestone_isolation["branch_name_template"],
            campaign_id=self.campaign_id, milestone_id=mid)
        base = self._trunk_branch
        handle = li.setup_context(
            strategy, repo_dir=self.repo_dir, loop_id=mid,
            base_ref=base, worktree_root=self._milestone_isolation.get("worktree_root"),
            branch_name=branch_name)
        self.state.milestone_context = {
            "milestone_id": mid,
            "strategy": handle.strategy,
            "branch": handle.branch,
            "work_dir": handle.work_dir,
            "worktree": (handle.work_dir if handle.strategy == li.STRATEGY_NEW_WORKTREE
                         else None),
            "base_ref": handle.base_ref,
            "repo_dir": handle.repo_dir,
        }
        self._audit("campaign_milestone_ingress", {
            "milestone_id": mid, "strategy": handle.strategy,
            "branch": handle.branch,
            "work_dir": handle.work_dir, "base_ref": handle.base_ref})

    def _milestone_work_dir(self) -> Optional[str]:
        """The directory sub-sprints run in (worktree or repo root)."""
        ctx = self.state.milestone_context
        if ctx:
            return ctx.get("work_dir") or self.repo_dir
        return self.repo_dir

    def _milestone_context_handle(self) -> Optional[li.ContextHandle]:
        ctx = self.state.milestone_context
        if not ctx:
            return None
        return li.ContextHandle(
            work_dir=ctx["work_dir"],
            branch=ctx["branch"],
            strategy=ctx["strategy"],
            repo_dir=ctx["repo_dir"],
            created=(ctx["strategy"] != li.STRATEGY_CURRENT_BRANCH),
            base_ref=ctx.get("base_ref"))

    def _needs_milestone_merge_gate(self, milestone: dict) -> bool:
        if not self._milestone_ingress_enabled():
            return False
        if not self._milestone_isolation.get("merge_prompt_at_close", True):
            return False
        handle = self._milestone_context_handle()
        if handle is None or not handle.created:
            return False
        if handle.branch == self._trunk_branch:
            return False
        return True

    def _write_milestone_merge_checkpoint(self, milestone: dict) -> str:
        """Write a campaign-tier merge gate file; return its path."""
        handle = self._milestone_context_handle()
        assert handle is not None
        mid = milestone["id"]
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(self.clock().replace("Z", "+00:00"))
            stamp = dt.strftime("%Y%m%d-%H%M%S")
        except (ValueError, AttributeError):
            stamp = "00000000-000000"
        fname = f"{stamp}__milestone_merge__{mid}.md"
        cps_dir = os.path.join(self.run_dir, "docs", "checkpoints")
        os.makedirs(cps_dir, exist_ok=True)
        path = os.path.join(cps_dir, fname)
        trunk = self._trunk_branch
        merge_cmd = (f"git -C {handle.repo_dir} switch {trunk} && "
                     f"git -C {handle.repo_dir} merge --no-ff -m "
                     f"'aidazi: merge {handle.branch}' {handle.branch}")
        pr_hint = (f"gh pr create --base {trunk} --head {handle.branch} "
                   f"--title 'Milestone {mid}'")
        body = (
            f"---\n"
            f"checkpoint_id: milestone_merge\n"
            f"scope: {mid}\n"
            f"emitted_at: {self.clock()}\n"
            f"decision: pending\n"
            f"resolved_at: null\n"
            f"resolver: null\n"
            f"---\n\n"
            f"# Context\n"
            f"Milestone `{mid}` is accepted. Its isolated branch `{handle.branch}` "
            f"(strategy `{handle.strategy}`) is ready to integrate into "
            f"`{trunk}`.\n\n"
            f"Per Constitution §1.7-D the engine does NOT auto-merge — choose an "
            f"option below and author a campaign-decision.json, then `--resume`.\n\n"
            f"# Suggested commands\n"
            f"- merge (manual): `{merge_cmd}`\n"
            f"- open PR: `{pr_hint}`\n\n"
            f"# Options\n"
            f"- merge_now — engine executes a protected local `git merge --no-ff` "
            f"(aborts on conflict; never force)\n"
            f"- open_pr — advance without merging (you open a PR manually)\n"
            f"- keep_branch — advance; leave the branch for later\n"
            f"- abort — end the campaign\n"
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def _pause_milestone_merge(self, milestone: dict) -> "CampaignState":
        path = self._write_milestone_merge_checkpoint(milestone)
        self.state.pending_milestone_advance = True
        return self._pause("milestone_merge", path, "campaign_milestone_merge",
                           {"milestone_id": milestone["id"],
                            "branch": (self.state.milestone_context or {}).get("branch"),
                            "trunk": self._trunk_branch})

    def _execute_milestone_merge(self) -> str:
        """Protected local --no-ff merge after human merge_now. Returns audit action."""
        handle = self._milestone_context_handle()
        if handle is None or not handle.created:
            return "noop"
        action = li.merge_into_trunk(
            handle, self._trunk_branch,
            merge_message=f"aidazi: merge milestone {self.state.milestone_context.get('milestone_id')}")
        cleanup_policy = self._milestone_isolation.get("cleanup_policy")
        if handle.strategy == li.STRATEGY_NEW_WORKTREE:
            li.cleanup(handle, cleanup_policy=cleanup_policy,
                       merged=(action == "merged"), changed=True)
        return action

    def _advance_milestone_cursor(self, *, save: bool = True) -> None:
        """Move to the next milestone; tear down milestone_context. ``save=False`` lets a
        caller fold the advance into a LATER single durable save (the §3.5c
        crash-idempotency barrier in the dispatch-resume path), so the cursor advance and
        the pause-clear land atomically in ONE _save()."""
        self.state.milestone_index += 1
        self.state.subsprint_index = 0
        self.state.milestone_context = None
        self.state.pending_milestone_advance = False
        if save:
            self._save()

    def _commit_dispatch_resolution(self) -> None:
        """§3.5c crash-idempotency BARRIER for a resolved Mechanism-B dispatch that
        ADVANCES the cursor: clear the pause (→ STATUS_RUNNING) and persist the advanced
        cursor DURABLY in ONE _save(), BEFORE the side-effecting resume audits.

        After this save the state is STATUS_RUNNING, so a crash in the audit window
        replays through the STATUS_RUNNING crash-recovery path (run() → _crash_recovery),
        which NEVER re-interprets the (now-cleared) pause — the cursor cannot
        double-advance and the resume/waiver audits cannot double-emit. A crash BEFORE
        this save replays from the still-PAUSED state and re-applies the resolution
        cleanly (the audits had not been emitted yet). The only residue is that a crash
        between this save and the audits LOSES (never duplicates) those informational
        audits — strictly safer than the double-advance/double-audit it replaces."""
        self.state.status = STATUS_RUNNING
        self.state.pause_reason = None
        self.state.pause_checkpoint = None
        self._save()

    # ----- Δ-19 F1/G1 signed-scope integrity (design §3.3.1) -------------- #
    def _signoff_status(self) -> str:
        """The campaign_plan_signoff status of self.plan: one of
        'signed' | 'stale' | 'pre_f1' | 'unsigned'.

        F1 (the signed resolved-scope snapshot integrity check) is ACTIVE only when the
        plan OPTS IN — it carries a `signoff` block OR any milestone declares
        covers_req_ids (both are NEW fields, so a legacy plan stays byte-identical). When
        F1 is inactive this collapses to today's bare-`signed_by_human` check. When
        active, 'signed' requires the stored signed_scope_hash to MATCH the live
        recomputed hash; a post-signoff edit (or a charter-default flip — G1) ⇒ 'stale';
        a bare top-level signed_by_human with no signoff block ⇒ 'pre_f1' (one re-sign)."""
        return signoff_status(self.plan, self.charter, self.ledger)

    # ----- Track-2 T2-A universal F1 freshness gate (design §2.1) --------- #
    def _authority_fresh(self) -> bool:
        """The T2-A universal precondition: True when the plan is NOT F1-active (legacy —
        byte-identical to today) OR its signed scope is FRESH (signoff_status == 'signed').
        It is READ-ONLY — every act-on-signed-scope site calls it BEFORE an irreversible
        action and converts a would-be proceed into a durable re-sign block (B5).

        TD6: a legitimate engine-authored deliver_followup insertion is reflected by
        _reapply_engine_restamp (run once per invocation, mutating the in-memory signoff to
        the authorized epoch), so by the time any gate calls this a legitimately-grown plan
        already reads 'signed' — no parallel/divergent hash. Any OTHER post-sign edit reads
        'stale'/'pre_f1'/'unsigned' ⇒ not fresh ⇒ block."""
        if not f1_required(self.plan):
            return True
        return self._signoff_status() == "signed"

    def _drift_field_hint(self) -> Optional[str]:
        """Best-effort label of WHICH hash-bound field class drifted, for the re-sign
        message (TD5: name the newly hash-bound field class). Compares the live resolved
        envelope against the stored signed snapshot. Never a gate — any failure ⇒ None."""
        try:
            signoff = self.plan.get("signoff") or {}
            stored = signoff.get("scope_envelope")
            if not isinstance(stored, dict):
                return None
            live = compute_scope_envelope(self.plan, self.charter, self.ledger)
            if _canonical_json(stored.get("authority")) != _canonical_json(
                    live.get("authority")):
                return "authority(budget/gap_followup/trunk_branch/milestone_isolation)"
            if _canonical_json(stored.get("goal")) != _canonical_json(live.get("goal")):
                return "goal"
            if _canonical_json(stored.get("milestones")) != _canonical_json(
                    live.get("milestones")):
                return ("milestones(scope/acceptance/subsprint_sequence/covers_req_ids/"
                        "covered_req_surfaces)")
            return "charter_or_signature"
        except Exception:  # noqa: BLE001 — a hint, never a gate
            return None

    def _block_for_resign(self, original_reason: Optional[str]) -> str:
        """B4 — BLOCK for re-sign while PRESERVING the original gate in a DURABLE overlay.
        Set self.state.freshness_block (if not already active) to the ORIGINAL
        pause_reason/checkpoint, then re-pause as 'campaign_plan_signoff'. On a post-re-sign
        resume the campaign_plan_signoff branch consumes the overlay and re-dispatches the
        ORIGINAL gate (mechanism-A resume / deliver_followup / milestone_merge /
        decision-bound checkpoints), so the mid-run drift never erases the original gate.
        Returns 'paused'. The overlay capture reads self.state.pause_checkpoint BEFORE
        _pause overwrites it, so the original checkpoint is preserved verbatim."""
        if self.state.freshness_block is None:
            self.state.freshness_block = {
                "original_pause_reason": original_reason,
                "original_pause_checkpoint": self.state.pause_checkpoint,
            }
        self._pause("campaign_plan_signoff", None, "campaign_freshness_block",
                    {"signoff_status": self._signoff_status(),
                     "original_pause_reason":
                         self.state.freshness_block.get("original_pause_reason"),
                     "drift": self._drift_field_hint()})
        return "paused"

    def _consume_freshness_block(self) -> Optional[str]:
        """Restore the ORIGINAL gate captured by _block_for_resign and clear the overlay.
        Returns the restored original_pause_reason (None ⇒ a mid-drive block had no gate to
        restore → the caller just re-dispatches the cursor). NO _save() here — a crash
        before the restored gate's own durable barrier/pause re-saves replays from the
        still-persisted campaign_plan_signoff + overlay (re-validates freshness, re-consumes,
        re-dispatches), which is strictly safer than persisting a transient half-state."""
        fb = self.state.freshness_block or {}
        self.state.pause_reason = fb.get("original_pause_reason")
        self.state.pause_checkpoint = fb.get("original_pause_checkpoint")
        self.state.freshness_block = None
        return self.state.pause_reason

    # ----- Track-2 TD6 engine-authored deliver_followup re-stamp ---------- #
    def _reapply_engine_restamp(self) -> None:
        """TD6 cross-invocation determinism: align self.plan's signoff with the authorized
        engine epoch (E* = the plan-file signed envelope + the append-only deltas pinned in
        campaign state) so the WHOLE invocation's freshness consumers (_signoff_status,
        scope_report via _build_gap_report, _live_signed_scope_hash, _f1_envelope) see ONE
        epoch — no divergence. The reconstruction itself is the SHARED, pure
        apply_engine_restamp_to_plan (also used by scope_report, so EXTERNAL reporting agrees
        — Codex R2 B2). Called once, early in run() after _load().

        Codex R2 B1 — a genuine HUMAN re-sign of the (already-grown) plan supersedes the
        engine epoch: the plan-file signoff now reads 'signed' on its own and already folds
        in the prior engine deltas, so the recorded engine_restamp is OBSOLETE. Replaying its
        deltas onto the human-re-signed envelope would double-apply them and falsely block a
        later legitimate follow-up. Detect it (raw signoff already 'signed') and DROP the
        stale engine_restamp; the plan is genuinely fresh-signed and a future follow-up starts
        a clean delta chain from the new human baseline."""
        if not f1_required(self.plan):
            return
        if not self.state.engine_restamp:
            return
        if self._signoff_status() == "signed":
            self.state.engine_restamp = None   # human re-sign supersedes the engine epoch
            return
        self.plan = apply_engine_restamp_to_plan(
            self.plan, self.charter, self.state.engine_restamp, self.ledger)

    @staticmethod
    def _entry_equal_except_seq(a: dict, b: dict) -> bool:
        """Two scope-envelope milestone entries equal in EVERY field except
        subsprint_sequence (canonical compare)."""
        ax = {k: v for k, v in a.items() if k != "subsprint_sequence"}
        bx = {k: v for k, v in b.items() if k != "subsprint_sequence"}
        return _canonical_json(ax) == _canonical_json(bx)

    @staticmethod
    def _is_single_insertion(old_seq: list, new_seq: list, idx: int,
                             baseline: set) -> bool:
        """new_seq is old_seq with EXACTLY one NEW id inserted at position idx: length grew
        by one, the inserted id is not a baseline (pre-existing) id, and removing it leaves
        old_seq byte-identical (prefix + suffix unchanged)."""
        if len(new_seq) != len(old_seq) + 1:
            return False
        if idx < 0 or idx >= len(new_seq):
            return False
        if new_seq[idx] in baseline:
            return False  # not a NEWLY authored follow-up (Codex inc-2 #3 spirit)
        return new_seq[:idx] + new_seq[idx + 1:] == old_seq

    def _is_authorized_followup_insertion(self, stored_env: dict, live_env: dict,
                                          inserted_index: int) -> bool:
        """The TD6 exact-diff guard. True IFF live_env differs from the CURRENT signed
        envelope (stored_env) by EXACTLY one subsprint id inserted into the CURRENT
        milestone's subsprint_sequence at inserted_index, with:
          * goal + the resolved authority block byte-identical;
          * the same milestone COUNT and every OTHER milestone byte-identical;
          * the current milestone identical in every field except subsprint_sequence;
          * that subsprint_sequence == stored + one NEW id (not a baseline id) at cursor+1,
            prefix + suffix unchanged.
        Any other shape — a reorder, a multi-item or non-cursor+1 edit, a prompt-id swap, a
        covers/acceptance/authority change, or a Customer change PAIRED with an insertion —
        fails the 'no other delta' clause ⇒ False ⇒ the re-stamp refuses ⇒ stays stale."""
        if not isinstance(stored_env, dict) or not isinstance(live_env, dict):
            return False
        if _canonical_json(stored_env.get("goal")) != _canonical_json(
                live_env.get("goal")):
            return False
        if _canonical_json(stored_env.get("authority")) != _canonical_json(
                live_env.get("authority")):
            return False
        stored_ms = stored_env.get("milestones") or []
        live_ms = live_env.get("milestones") or []
        if len(stored_ms) != len(live_ms):
            return False  # a milestone added/removed is NOT a follow-up insertion
        # Identify the executing milestone by ID, not by numeric position (Codex R1 NB-1):
        # self.milestones is in TOPOLOGICAL order while the envelope is in DECLARED order, so
        # state.milestone_index is not a valid index into the envelope when depends_on
        # reorders the backlog. The envelope is declared-order in BOTH stored + live, so a
        # positional id mismatch means the declared order itself changed ⇒ refuse.
        cur_id = self.milestones[self.state.milestone_index].get("id")
        baseline = set(self.state.followup_baseline_seq or [])
        for sm, lm in zip(stored_ms, live_ms):
            if sm.get("id") != lm.get("id"):
                return False  # a declared-order reorder is a scope change, not an insertion
            if sm.get("id") == cur_id:
                if not self._entry_equal_except_seq(sm, lm):
                    return False
                if not self._is_single_insertion(
                        list(sm.get("subsprint_sequence") or []),
                        list(lm.get("subsprint_sequence") or []),
                        inserted_index, baseline):
                    return False
            elif _canonical_json(sm) != _canonical_json(lm):
                return False
        return True

    def _restamp_followup_epoch(self, inserted_index: int) -> bool:
        """TD6: advance the SINGLE signed epoch for the ONE legitimate engine-authored delta
        — the deliver_followup insertion at cursor+1. Runs the exact-diff guard against the
        CURRENT signed envelope; on success it (atomically, in one logical advance) mutates
        the IN-MEMORY signoff to the live (grown) envelope + recomputed hash so all consumers
        read 'signed' this invocation, AND pins the authorized hash + append-only provenance
        to CAMPAIGN STATE (never the plan file). Returns True on a clean re-stamp, False (→
        block) on any other delta. NOT a human re-sign — signed_by_human/signer untouched.

        Idempotent under crash replay: the provenance is recomputed deterministically (a lost
        in-memory mutation is re-derived; an already-reapplied epoch makes _authority_fresh
        True so this is not re-entered — see the deliver_followup_required resume branch)."""
        if not signoff_snapshot_authentic(self.plan):
            return False  # cannot trust the stored signed envelope → fail closed
        signoff = self.plan["signoff"]
        # Codex R1 B2 — the re-stamp may advance the epoch ONLY for the authorized insertion;
        # it must NEVER launder a separate authority change. (a) the snapshot must be a
        # genuine HUMAN signature (a flipped/removed signed_by_human is a re-authorization,
        # not an engine delta); (b) the charter must be byte-identical to the signed snapshot
        # (a charter edit changes charter_hash INSIDE H but need not show in the envelope, so
        # the envelope diff alone would miss it) — either ⇒ refuse ⇒ block for human re-sign.
        if signoff.get("signed_by_human") is not True:
            return False
        if _canonical_sha256(self.charter or {}) != signoff.get("charter_hash"):
            return False
        stored_env = signoff.get("scope_envelope")
        live_env = compute_scope_envelope(self.plan, self.charter, self.ledger)
        if not self._is_authorized_followup_insertion(
                stored_env, live_env, inserted_index):
            return False
        new_hash = self._live_signed_scope_hash()
        if not new_hash:
            return False
        ms = self.milestones[self.state.milestone_index]
        seq = ms.get("subsprint_sequence") or []
        inserted_id = seq[inserted_index] if 0 <= inserted_index < len(seq) else None
        prior = self.state.engine_restamp or {"restamp_version": 0, "deltas": []}
        version = int(prior.get("restamp_version", 0)) + 1
        prior_hash = signoff.get("signed_scope_hash")
        delta = {"milestone_id": ms.get("id"), "subsprint_id": inserted_id,
                 "at_index": inserted_index,
                 "authorizing_checkpoint": self.state.pause_checkpoint,
                 "prior_signed_scope_hash": prior_hash,
                 "new_signed_scope_hash": new_hash, "restamp_version": version}
        # Atomic advance (in-memory signoff + pinned state record together):
        self.state.engine_restamp = {
            "signed_scope_hash": new_hash, "restamp_version": version,
            "deltas": list(prior.get("deltas") or []) + [delta]}
        signoff["scope_envelope"] = live_env
        signoff["signed_scope_hash"] = new_hash
        self._audit("campaign_followup_epoch_restamp",
                    {"milestone_id": ms.get("id"), "subsprint_id": inserted_id,
                     "at_index": inserted_index, "restamp_version": version,
                     "prior_signed_scope_hash": prior_hash,
                     "new_signed_scope_hash": new_hash})
        return True

    # ----- Δ-19 F3 terminal-outcome stamping (design §3.5.1) ------------- #
    def _stamp_milestone_outcome(self, milestone_id: str, terminal: str, *,
                                 pause_reason: Optional[str] = None,
                                 decision_ref: Optional[str] = None) -> None:
        """Record ONE terminal-close outcome per milestone (idempotent — a §3.5c crash
        replay re-runs the close branch, so a second stamp for the same milestone is a
        no-op). scope_report DERIVES delivery_status from these; the engine never writes
        the ledger."""
        for o in self.state.milestone_outcomes:
            if isinstance(o, dict) and o.get("milestone_id") == milestone_id:
                return
        entry: dict = {"milestone_id": milestone_id, "terminal": terminal}
        if pause_reason:
            entry["pause_reason"] = pause_reason
        if decision_ref:
            entry["decision_ref"] = decision_ref
        self.state.milestone_outcomes.append(entry)

    def _derive_inner_loop_terminal(self, milestone: dict):
        """Terminal close enum for a milestone that completed via the INNER dispatch loop
        (not a resume ship), read from its LAST recorded unit (design §3.5.1):
          * a terminal review_out_of_scope accept (the halted unit is last, advanced via
            ACT_ADVANCE_SUBSPRINT, no new unit) ⇒ out_of_scope_advance (waived);
          * final_state 'done' (an authoritative Acceptance pass auto-shipped) ⇒
            acceptance_pass_authoritative (delivered);
          * a terminal clean 'advance' (no milestone-close Acceptance gate ran —
            acceptance mode off; driver.py:3007) ⇒ acceptance_off (waived).
        Returns (terminal, pause_reason, decision_ref)."""
        mid = milestone["id"]
        last = None
        for u in reversed(self.state.units):
            if isinstance(u, dict) and u.get("milestone_id") == mid:
                last = u
                break
        if last is None:
            return "not_shipped", None, None
        pr = last.get("pause_reason")
        cpt = last.get("checkpoint_path")
        if last.get("status") == "halted" and pr == "review_out_of_scope":
            return "out_of_scope_advance", pr, cpt
        fs = last.get("final_state")
        if fs in _MILESTONE_DONE_STATES:
            return "acceptance_pass_authoritative", pr, cpt
        if fs in _ADVANCE_STATES:
            return "acceptance_off", pr, cpt
        return "not_shipped", pr, cpt

    def _complete_milestone(self, milestone: dict) -> Optional["CampaignState"]:
        """After a milestone is accepted: stamp its terminal outcome (F3), then the
        optional merge gate, then advance cursor.

        Returns a paused CampaignState when the merge gate fires; else None."""
        terminal, pr, ref = self._derive_inner_loop_terminal(milestone)
        self._stamp_milestone_outcome(milestone["id"], terminal,
                                      pause_reason=pr, decision_ref=ref)
        if self._needs_milestone_merge_gate(milestone):
            return self._pause_milestone_merge(milestone)
        self._advance_milestone_cursor()
        return None

    # ----- Track 2 Phase 2-γ / §1.7-F gap-followup engine ----------------- #
    # The pre-authorized, in-envelope completeness-remediation auto-route. This is a NEW
    # auto-author/auto-dispatch capability (the campaign core otherwise deliberately
    # SURFACES sub-sprint authoring at milestone_decompose_required), so it is built
    # FAIL-CLOSED: it dispatches ONLY when every deterministic gate passes — the clause-0
    # completeness↔quality SEAL, the clause-1 req_id-envelope PROOF, and the clause-2
    # RUNTIME bounds — and on ANY failure it HALTs and escalates to needs_human (clause 3),
    # never a silent stop and never a loop. It is DORMANT unless a requirement ledger is
    # wired AND the plan is fresh-signed AND the post-close gap_report is non-empty (then
    # byte-identical to today). The §3.4 diagram invariant: this path is audited (NOT
    # silent) and is completeness, NOT quality, routing.

    def _autonomy_level(self) -> str:
        """The charter-declared autonomy level (default human_in_the_loop). §1.7-F permits
        no-confirm gap-followup auto-dispatch ONLY under human_on_the_loop or higher; an
        absent charter ⇒ the most conservative level."""
        return ((self.charter or {}).get("autonomy") or {}).get(
            "level", "human_in_the_loop")

    def _gap_followup_cfg(self) -> dict:
        """Resolved per-milestone gap-followup bounds (campaign-plan gap_followup + the
        schema defaults). An ABSENT block ⇒ conservative engine defaults — never
        unbounded (§1.7-F clause 2)."""
        gf = self.plan.get("gap_followup") or {}
        return {
            "max_subsprints": gf.get("max_subsprints",
                                     GAP_FOLLOWUP_DEFAULT_MAX_SUBSPRINTS),
            "max_no_progress_rounds": gf.get("max_no_progress_rounds",
                                             GAP_FOLLOWUP_DEFAULT_MAX_NO_PROGRESS),
        }

    def _campaign_budget_absent(self) -> bool:
        """True when the campaign plan declares NO countable budget dimension (today
        unbounded at runtime). §1.7-F clause 2: such a plan still gets a conservative
        effective-cap on the gap-followup dimension, never the unbounded default."""
        b = self.budget or {}
        return not any(b.get(k) for k in
                       ("max_subsprints", "max_total_spawns", "max_wall_clock_minutes"))

    def _gap_effective_cap(self) -> int:
        """The TOTAL-rounds effective-cap for the gap-followup dimension when the campaign
        budget is ABSENT: charter.budget.max_fix_rounds_total when set, else a conservative
        engine default (§1.7-F clause 2 — never unbounded)."""
        mfr = ((self.charter or {}).get("budget") or {}).get("max_fix_rounds_total")
        if isinstance(mfr, int) and mfr > 0:
            return mfr
        return GAP_FOLLOWUP_DEFAULT_EFFECTIVE_CAP

    def _gap_state(self) -> dict:
        """The persisted gap_followup_state, initialized in place (campaign-state.schema
        gap_followup_state shape)."""
        gfs = self.state.gap_followup_state
        gfs.setdefault("rounds_by_milestone", {})
        gfs.setdefault("gap_set_history", [])
        gfs.setdefault("no_progress_rounds", 0)
        gfs.setdefault("remediations", [])
        return gfs

    def _milestone_terminal(self, mid) -> Optional[str]:
        """The recorded terminal outcome for a milestone (F3), or None."""
        for o in self.state.milestone_outcomes:
            if isinstance(o, dict) and o.get("milestone_id") == mid:
                return o.get("terminal")
        return None

    def _build_gap_report(self) -> Optional[dict]:
        """The POST-close completeness gap_report — from coverage/ledger FACTS ONLY
        (scope_report.build_gap_report; the clause-0 SOURCE seal), computed off the LIVE
        post-close state (status + cursor + milestone_outcomes), the signed plan + F1
        envelope, the ledger, and the charter. Returns None when NO ledger is wired (the
        engine is dormant). RAISES when a wired-ledger projection fails — the caller
        fail-closes to needs_human (Codex R1 B1: an unavailable/ambiguous gap source on a
        wired+signed plan must HALT, not silently finish — §1.7-F clause 3). It is NEVER
        swallowed into a 'no gap' (that would silently mark the campaign done)."""
        if not self.ledger:
            return None
        import scope_report as _scope
        coverage = _scope.compute_requirement_coverage(
            self.plan, self.state.to_dict(), self.ledger, charter=self.charter)
        return _scope.build_gap_report(coverage)

    def _gap_followup_eligible(self, gap_report):
        """§1.7-F clause 0 — the completeness↔quality SEAL. Returns
        (eligible, gap_items, reason). gap_items is the source-sealed gap from
        build_gap_report (coverage facts only, NEVER Acceptance failure semantics).

        INELIGIBLE when: no gap (nothing to complete → finish); not fresh-signed (a stale/
        pre-F1 plan → the caller RE-PAUSES for re-sign, T2-A B3 — never finishes); a gap
        item names no covering milestone or one absent from the plan (ambiguous → HALT); OR
        a covering milestone carries a QUALITY-fault / human-waiver terminal (→ HALT; it
        routes to human-confirm exactly as today, the auto path is forbidden). The last is
        defense-in-depth — build_gap_report already excludes every waived terminal, so a gap
        milestone never carries one, but a bug/tamper that put one in the gap fails closed
        rather than auto-overriding a recorded human ship/scope decision."""
        if not gap_report or gap_report.get("signoff_status") != "signed":
            return False, [], "not_fresh_signed"
        gap_items = [g for g in (gap_report.get("gap") or []) if isinstance(g, dict)]
        if not gap_items:
            return False, [], "no_gap"
        plan_ids = {m.get("id") for m in self.milestones}
        for g in gap_items:
            mid = g.get("covered_by")
            if not mid or mid not in plan_ids:
                return False, gap_items, f"ambiguous_gap:{g.get('req_id')}"
            if self._milestone_terminal(mid) in _QUALITY_FAULT_TERMINALS:
                return False, gap_items, f"quality_fault:{mid}"
        return True, gap_items, "eligible"

    def _f1_envelope(self):
        """(envelope_req_ids, covers_by_milestone) from the AUTHENTIC F1 signed snapshot,
        or (None, None) when the snapshot does not verify against its OWN signed_scope_hash
        (fail-closed: an unverifiable envelope cannot PROVE containment — Codex R-P2a #2).
        envelope_req_ids = every signed covers_req_id; covers_by_milestone maps milestone_id
        → its signed covers set."""
        if not signoff_snapshot_authentic(self.plan):
            return None, None
        snapshot = (self.plan.get("signoff") or {}).get("scope_envelope") or {}
        envelope: set = set()
        by_ms: dict = {}
        for m in (snapshot.get("milestones") or []):
            cov = set(m.get("covers_req_ids") or [])
            by_ms[m.get("id")] = cov
            envelope |= cov
        return envelope, by_ms

    def _live_signed_scope_hash(self) -> Optional[str]:
        """The LIVE F1 signed_scope_hash of the plan (the same value signoff_status compares
        the stored hash against). Used to bind a pending_remediation marker to the EXACT
        signed scope epoch it was authorized under (Codex R4 B1): any plan/charter edit
        between marker persistence and resume changes this hash, so the marker is refused.
        None on any failure (then the bind check fails closed)."""
        signoff = self.plan.get("signoff") or {}
        try:
            return compute_signed_scope_hash(
                self.plan, self.charter or {}, charter_ref=signoff.get("charter_ref"),
                ledger=self.ledger)
        except Exception:  # noqa: BLE001 — None → the resume bind check fails closed
            return None

    def _select_gap_target(self, gap_items):
        """Pick the remediation round's target = the FIRST undelivered in-envelope milestone
        (topological/declared order) that owns a gap req_id. Returns
        (milestone, milestone_index, covered_req_ids) — covered_req_ids is the SORTED set of
        THIS milestone's gap req_ids (its undelivered signed covers; milestone-granular per
        the locked decision). (None, None, None) defensively when no gap item maps to a plan
        milestone (the eligibility seal already rejects that)."""
        by_ms: dict = {}
        for g in gap_items:
            by_ms.setdefault(g.get("covered_by"), set()).add(g.get("req_id"))
        for i, m in enumerate(self.milestones):
            if m["id"] in by_ms:
                return m, i, sorted(r for r in by_ms[m["id"]] if r)
        return None, None, None

    def _req_id_envelope_check(self, milestone, covered_req_ids):
        """§1.7-F clause 1 — the deterministic req_id-envelope check, DISTINCT from
        driver._scope_expansion_guard (modules/layers only, which would NOT catch
        same-module new scope). Proves
        covered_req_ids ⊆ (F1 signed snapshot ∩ this milestone's signed covers_req_ids).
        Returns (ok, reason). FAILS CLOSED on an unverifiable envelope, an empty claim, or
        ANY covered_req_id outside the intersection (out-of-envelope → HALT for a human)."""
        envelope, by_ms = self._f1_envelope()
        if envelope is None:
            return False, "envelope_unverifiable"
        if not covered_req_ids:
            return False, "empty_covered_req_ids"
        allowed = envelope & (by_ms.get(milestone["id"]) or set())
        out = sorted(c for c in covered_req_ids if c not in allowed)
        if out:
            return False, f"out_of_envelope:{out}"
        return True, "in_envelope"

    def _gap_followup_bounds(self, milestone, gap_now):
        """§1.7-F clause 2 — RUNTIME bounds. gap_now is the CURRENT remaining gap
        req_id-set. Returns (ok, reason, next_no_progress):
          * the per-milestone counter is below gap_followup.max_subsprints;
          * when the campaign budget is ABSENT, the TOTAL gap-followup rounds are below the
            effective-cap (never the unbounded default);
          * the gap is a strict PROPER SUBSET of the prior round (proper-subset, NOT
            identical-hash → catches A/B churn). A gap that GREW (a req_id not in the prior
            set) is an immediate regression HALT; a gap that merely did not shrink is a
            no-progress round, bounded by max_no_progress_rounds.
        Read-only — the caller persists next_no_progress only on a clean dispatch."""
        cfg = self._gap_followup_cfg()
        gfs = self._gap_state()
        no_progress = gfs["no_progress_rounds"]
        rounds = gfs["rounds_by_milestone"].get(milestone["id"], 0)
        if rounds >= cfg["max_subsprints"]:
            return False, f"max_subsprints_exceeded:{milestone['id']}:{rounds}", no_progress
        if self._campaign_budget_absent():
            total = sum(gfs["rounds_by_milestone"].values())
            cap = self._gap_effective_cap()
            if total >= cap:
                return False, f"effective_cap_exceeded:{total}>={cap}", no_progress
        else:
            # §1.7-F clause 2: "the campaign budget is not exhausted". The gap-followup
            # dispatches OUTSIDE the inner loop's between-units _over_budget check, so the
            # PRESENT campaign budget is enforced here too (the effective-cap covers the
            # ABSENT-budget case above). A remediation that would exceed the signed
            # campaign budget HALTs to needs_human, never silently overspends.
            over = self._over_budget()
            if over:
                return False, f"campaign_budget_exhausted:{over}", no_progress
        history = gfs["gap_set_history"]
        if history:
            prior = set(history[-1])
            grew = gap_now - prior
            if grew:
                return False, f"gap_regression:{sorted(grew)}", no_progress
            if gap_now == prior:
                no_progress += 1
                if no_progress >= cfg["max_no_progress_rounds"]:
                    return False, f"no_progress_exceeded:{no_progress}", no_progress
            else:  # strict proper subset (strictly smaller, no new ids) → progress
                no_progress = 0
        return True, "bounded", no_progress

    def _restamp_milestone_outcome(self, mid, terminal, *, pause_reason=None,
                                   decision_ref=None) -> None:
        """§1.7-F: REPLACE a milestone's terminal outcome after a gap-followup remediation
        re-delivers it (the idempotent _stamp_milestone_outcome would SKIP an existing
        entry). Drops any prior entry for the milestone, then stamps the new one — so the
        gap recomputation reflects the remediation (the basis of crash-idempotency)."""
        self.state.milestone_outcomes = [
            o for o in self.state.milestone_outcomes
            if not (isinstance(o, dict) and o.get("milestone_id") == mid)]
        self._stamp_milestone_outcome(mid, terminal, pause_reason=pause_reason,
                                      decision_ref=decision_ref)

    def _write_gap_review_checkpoint(self, gap_status, gap_items, milestone_id) -> str:
        """Write a campaign-tier completeness_gap_review checkpoint with a per-pause NONCE
        in its filename (Codex R1 B3) — a monotonic gap_review_seq + the clock stamp — so
        each pause has a UNIQUE basename. The file-based decision resolver binds on that
        basename, so a stale `remediate` file (an earlier round's nonce) is REFUSED and
        cannot replay across rounds (the "ONE bounded round" semantics). Mirrors
        _write_milestone_merge_checkpoint."""
        gfs = self._gap_state()
        seq = int(gfs.get("gap_review_seq", 0)) + 1
        gfs["gap_review_seq"] = seq
        try:
            dt = datetime.fromisoformat(self.clock().replace("Z", "+00:00"))
            stamp = dt.strftime("%Y%m%d-%H%M%S")
        except (ValueError, AttributeError):
            stamp = "00000000-000000"
        fname = f"{stamp}__completeness_gap_review__r{seq}.md"
        cps_dir = os.path.join(self.run_dir, "docs", "checkpoints")
        os.makedirs(cps_dir, exist_ok=True)
        path = os.path.join(cps_dir, fname)
        gap_ids = [g.get("req_id") for g in (gap_items or [])]
        body = (
            f"---\n"
            f"checkpoint_id: completeness_gap_review\n"
            f"scope: {milestone_id or 'campaign'}\n"
            f"emitted_at: {self.clock()}\n"
            f"gap_status: {gap_status}\n"
            f"decision: pending\n"
            f"resolved_at: null\n"
            f"resolver: null\n"
            f"---\n\n"
            f"# Context\n"
            f"Constitution §1.7-F completeness gap (human-signed, in-envelope, "
            f"signed-but-undelivered scope): {gap_ids}.\nStatus: `{gap_status}`.\n\n"
            f"Under `human_in_the_loop` a completeness gap_report routes to needs_human; a "
            f"clause-3 fail-closed escalation lands here too. §1.7-F grants NO authority to "
            f"ship or widen scope. Author a campaign-decision.json with THIS checkpoint "
            f"basename + an adjust_scope choice, then `--resume --decision <file>`.\n\n"
            f"# Options (adjust_scope)\n"
            f"- remediate — authorize ONE bounded, in-envelope remediation round (the SAME "
            f"deterministic seal/req_id-envelope/bounds gates as the auto path)\n"
            f"- accept_gap — accept the incomplete signed scope and finish (no remediation)\n"
            f"- abort — end the campaign\n"
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def _pause_gap_review(self, gap_status, gap_items, *, milestone_id=None,
                          remediation_checkpoint=None) -> "CampaignState":
        """Pause at the ONE §1.7-F completeness gate (completeness_gap_review) — it carries
        BOTH the human_in_the_loop pre-dispatch review AND every clause-3 fail-closed
        escalation (the audit `gap_status` distinguishes them; the same adjust_scope
        decision — remediate|accept_gap|abort — resolves both). Audited, never silent
        (§3.4 diagram invariant).

        It is a CAMPAIGN-tier gate: the file-based resolver special-cases it (bind by
        campaign_id + pause_reason + the per-pause checkpoint NONCE basename, NO unit lookup,
        NO subsprint_id). The nonce prevents a stale `remediate` file from replaying across
        rounds (Codex R1 B3). A halted remediation's underlying Driver checkpoint is recorded
        in `extra` + the halted unit (inspectable), never as the campaign pause_checkpoint."""
        extra = {"gap_status": gap_status,
                 "gap": [g.get("req_id") for g in (gap_items or [])],
                 "autonomy": self._autonomy_level()}
        if milestone_id:
            extra["milestone_id"] = milestone_id
        if remediation_checkpoint:
            extra["remediation_checkpoint"] = remediation_checkpoint
        path = self._write_gap_review_checkpoint(gap_status, gap_items, milestone_id)
        return self._pause(GAP_REVIEW_CHECKPOINT, path,
                           "campaign_gap_followup_pause", extra)

    def _safe_remediation_id(self, milestone, round_n):
        """Generate the round's gapfix sub-sprint id FAIL-CLOSED (Codex R1 B5). Returns
        (id, None) when safe, or (None, reason) when it would OVERFLOW the path-safe length
        cap (a 127-char milestone id + suffix would otherwise raise in make_run_unit instead
        of pausing) or COLLIDE with a signed sub-sprint id / a prior recorded unit (a reused
        (campaign, milestone, subsprint) loop_id). _SAFE_CAMPAIGN_ID_RE is the SAME gate
        make_run_unit enforces on each id component."""
        rid = f"{milestone['id']}-gapfix-{round_n}"
        if not _SAFE_CAMPAIGN_ID_RE.match(rid):
            return None, "id_overflow_or_unsafe"
        if rid in set(milestone.get("subsprint_sequence") or []):
            return None, "collides_with_signed_subsprint"
        recorded = {u.get("subsprint_id") for u in self.state.units
                    if isinstance(u, dict) and u.get("milestone_id") == milestone["id"]}
        if rid in recorded:
            return None, "collides_with_recorded_unit"
        return rid, None

    def _gap_remediation_spec(self, milestone, covered_req_ids) -> dict:
        """The CONTENT-complete Dev work contract for the gapfix (Codex R1 B4): objective +
        scope_in (from the ledger requirement statements) + exit_criteria, all bounded to
        the in-envelope covered_req_ids. make_run_unit renders it into the Driver-resolved
        compact/<id>-dev-prompt.md, so Deliver addresses EXACTLY the signed-but-undelivered
        requirements — the req_id proof is BOUND into the work contract, never a bare run,
        never scope expansion."""
        reqs = {r.get("id"): r for r in (self.ledger or {}).get("requirements", [])
                if isinstance(r, dict)}
        scope_in = [f"{rid}: {((reqs.get(rid) or {}).get('statement') or rid)}"
                    for rid in covered_req_ids]
        joined = ", ".join(covered_req_ids)
        return {
            "covered_req_ids": list(covered_req_ids),
            "objective": (f"Constitution §1.7-F in-envelope completeness remediation for "
                          f"milestone {milestone['id']}: deliver the human-signed "
                          f"requirements signed into this milestone's covers_req_ids that "
                          f"are not yet delivered ({joined})."),
            "scope_in": scope_in,
            "exit_criteria": [f"{rid} delivered and verifiable at the milestone-close "
                              f"Acceptance gate" for rid in covered_req_ids],
        }

    def _dispatch_gap_remediation(self, milestone, remediation_id, covered_req_ids, *,
                                  resume) -> dict:
        """Run ONE generated remediation sub-sprint for `milestone` through the SAME
        injected run_unit, so per-milestone Acceptance anchors at this (now-terminal)
        sub-sprint. Passes a GROWN sequence (the milestone's signed subsprint_sequence +
        remediation_id) so the per-milestone projection includes the remediation, but does
        NOT MUTATE the signed plan — a remediation COMPLETES already-signed scope, it is NOT
        a scope edit, so the F1 signed envelope (which hashes subsprint_sequence) must stay
        intact; mutating it would flip signoff_status to 'stale' and silently drop the rest
        of a multi-milestone gap. Passes the gap_followup_spec (the §1.7-F in-envelope work
        contract, bound into the Driver's Dev prompt) + covered_req_ids. `resume` is True
        ONLY on a crash-recovery completion of an in-flight round (re-enter the Driver: a
        COMPLETED one returns its outcome with no re-run; an un-started one re-runs fresh via
        run_unit's FileNotFoundError fallback — Codex R2 B2). Accounts the spend exactly like
        the inner loop. Returns the run_unit summary."""
        mid = milestone["id"]
        grown_seq = list(milestone.get("subsprint_sequence") or []) + [remediation_id]
        spec = self._gap_remediation_spec(milestone, covered_req_ids)
        summary = self.run_unit(
            remediation_id, milestone_id=mid, subsprint_sequence=grown_seq,
            resume=resume, functional_acceptance=milestone.get("functional_acceptance"),
            repo_dir=self._milestone_work_dir(),
            covered_req_ids=list(covered_req_ids), gap_followup_spec=spec)
        self.state.subsprints_run += 1
        self.state.total_spawns += int(summary.get("spawn_count") or 0)
        self.state.wall_clock_minutes = (
            self._base_wall + _iso_minutes(self._invocation_start, self.clock()))
        return summary

    def _run_remediation(self, milestone, remediation_id, covered_req_ids, round_n,
                         gap_set, next_no_progress, *, resume) -> str:
        """Dispatch ONE gapfix and ATOMICALLY record the round — counter + gap-set history +
        no_progress + stanza + unit + terminal re-stamp AND clear the pending_remediation
        marker, in ONE _save. So a crash replay recomputes the gap from the persisted
        re-stamp (no double-dispatch), and the in-flight marker is cleared exactly when the
        round becomes durable (Codex R2 B2). Returns GAP_CONTINUE (clean) or GAP_PAUSED
        (halted → escalate to needs_human). Shared by the live path and crash-recovery."""
        gap_items = [{"req_id": r} for r in sorted(gap_set)]
        self._audit("campaign_gap_followup_dispatch",
                    {"milestone_id": milestone["id"], "subsprint_id": remediation_id,
                     "covered_req_ids": covered_req_ids, "round": round_n, "resume": resume})
        summary = self._dispatch_gap_remediation(
            milestone, remediation_id, covered_req_ids, resume=resume)
        final_state = summary.get("final_state")
        unit = {"milestone_id": milestone["id"], "subsprint_id": remediation_id,
                "status": "done", "final_state": final_state,
                "loop_id": summary.get("loop_id")}
        gfs = self._gap_state()
        gfs["rounds_by_milestone"][milestone["id"]] = round_n
        gfs["gap_set_history"].append(sorted(gap_set))
        gfs["no_progress_rounds"] = next_no_progress
        gfs["remediations"].append(
            {"milestone_id": milestone["id"], "subsprint_id": remediation_id,
             "covered_req_ids": covered_req_ids, "round": round_n})
        gfs.pop("pending_remediation", None)   # the round is now durably recorded

        if final_state in _ADVANCE_STATES or final_state in _MILESTONE_DONE_STATES:
            # The remediation completed. Re-stamp the milestone's terminal so the gap
            # recomputation reflects it: done → delivered; advance (acceptance mode off) →
            # acceptance_off/waived — EITHER WAY the milestone leaves the gap, so the set
            # strictly shrinks (proper-subset progress holds; termination guaranteed).
            terminal = ("acceptance_pass_authoritative"
                        if final_state in _MILESTONE_DONE_STATES else "acceptance_off")
            self.state.units.append(unit)
            self._restamp_milestone_outcome(
                milestone["id"], terminal, pause_reason=summary.get("pause_reason"),
                decision_ref=summary.get("checkpoint_path"))
            self._save()
            self._audit("campaign_gap_followup_round_done",
                        {"milestone_id": milestone["id"], "subsprint_id": remediation_id,
                         "terminal": terminal, "round": round_n})
            return GAP_CONTINUE

        # The remediation HALTED at a gate → HALT and escalate to needs_human (clause 3).
        reason_cp = summary.get("pause_reason") or final_state or "unknown_halt"
        unit["status"] = "halted"
        unit["pause_reason"] = reason_cp
        unit["checkpoint_path"] = summary.get("checkpoint_path")
        self.state.units.append(unit)
        self._audit("campaign_gap_followup_blocked",
                    {"reason": f"remediation_halted:{reason_cp}",
                     "milestone_id": milestone["id"], "subsprint_id": remediation_id})
        self._pause_gap_review(f"remediation_halted:{reason_cp}", gap_items,
                               milestone_id=milestone["id"],
                               remediation_checkpoint=summary.get("checkpoint_path"))
        return GAP_PAUSED

    def _complete_pending_remediation(self, pending) -> str:
        """Crash-recovery: an in-flight gapfix dispatch was persisted (pending_remediation)
        but the atomic round-save did not land. RE-ENTER that exact remediation via
        resume=True — a Driver that COMPLETED returns its recorded outcome without re-running
        (no double-run / no spend undercount — Codex R2 B2); an un-started one re-runs once
        (run_unit's resume downgrade). Bypasses the autonomy gating + bounds (they already
        passed before the crash).

        VALIDATES the marker before bypassing those gates — RE-PROVING every live gate the
        normal path proves, so resume cannot complete work the current plan no longer
        authorizes: (a) SHAPE (Codex R3 NB-1) — a malformed marker (milestone vanished, empty
        covered_req_ids, non-canonical/colliding id, bad round, or an empty {}); (b) SIGNED
        (Codex R5 B1) — the plan MUST still be fresh-signed (signoff_status=='signed'), so a
        signed_by_human flip after dispatch — which does NOT change the scope_hash — fails
        closed; (c) SCOPE EPOCH (Codex R4 B1) — the marker's signed scope_hash MUST still
        match the live one, so a plan/charter edit/re-sign refuses the stale marker; (d)
        ENVELOPE (clause 1 re-proof) — covered_req_ids MUST still be ⊆ (F1 snapshot ∩ the
        milestone's signed covers). ANY failure fails closed to needs_human."""
        pending = pending or {}
        mid = pending.get("milestone_id")
        rid = pending.get("remediation_id")
        cov = [c for c in (pending.get("covered_req_ids") or []) if isinstance(c, str)]
        round_n = pending.get("round")
        milestone = next((m for m in self.milestones if m["id"] == mid), None)
        why = None
        if not (milestone is not None and isinstance(rid, str)
                and isinstance(round_n, int) and round_n >= 1 and cov
                and rid == f"{mid}-gapfix-{round_n}"
                and bool(_SAFE_CAMPAIGN_ID_RE.match(rid))):
            why = "malformed"
        elif self._signoff_status() != "signed":
            # the plan was unsigned/stale/re-signed since dispatch (a signed_by_human flip
            # does NOT change the scope_hash) → never complete work under a no-longer-signed
            # plan (Codex R5 B1; mirrors the normal path's fresh-signed gate).
            why = "not_signed"
        elif (not pending.get("scope_hash")
              or pending.get("scope_hash") != self._live_signed_scope_hash()):
            # plan/charter edited or re-signed since dispatch, OR the epoch is unverifiable
            # (a None hash either side) → fail-closed rather than re-run on an unproven epoch.
            why = "scope_epoch_changed"
        else:
            ok, env_why = self._req_id_envelope_check(milestone, cov)
            if not ok:
                why = f"out_of_envelope:{env_why}"
        if why is not None:
            self.state.gap_followup_state.pop("pending_remediation", None)
            self._audit("campaign_gap_followup_blocked",
                        {"reason": f"pending_remediation_{why}", "milestone_id": mid})
            self._pause_gap_review(f"pending_remediation:{why}", [], milestone_id=mid)
            return GAP_PAUSED
        return self._run_remediation(
            milestone, rid, cov, round_n, set(pending.get("gap_set") or []),
            int(pending.get("no_progress") or 0), resume=True)

    def _gap_followup_round(self, decision_resolver) -> str:
        """The dedicated, FAIL-CLOSED §1.7-F engine — called by run() at backlog-exhausted.
        The cursor stays at (len, 0); remediation is dispatched DIRECTLY here (never via the
        milestone cursor), so the battle-tested inner loop is untouched and already-done
        milestones are never re-run. Returns GAP_DONE / GAP_CONTINUE / GAP_PAUSED /
        GAP_ENDED.

        Sequence: consume any human adjust_scope decision (one-shot, stashed by
        _handle_resume); compute the post-close gap_report (coverage facts only — clause 0
        source seal); apply the eligibility SEAL (clause 0); route by autonomy
        (human_in_the_loop → pause at completeness_gap_review; human_on_the_loop+ → auto);
        on the dispatch path PROVE the generated remediation in the F1 req_id-envelope
        (clause 1) and the runtime bounds (clause 2), then dispatch ONE bounded remediation
        round. ANY gate failure HALTs and escalates to needs_human (clause 3)."""
        review_decision = self._gap_review_decision
        self._gap_review_decision = None
        self._crash_recovery = False   # consumed; the pending_remediation marker (below) is
                                       # the durable crash-recovery signal, not this flag.

        # Crash-recovery FIRST — BEFORE the dormant/no-ledger exit (Codex R3 B1): an in-flight
        # remediation whose atomic round-save never landed must be COMPLETED (re-enter its
        # Driver via resume=True) so a marker can never strand the campaign at STATUS_DONE
        # with the round unrecorded + spend undercounted (a STATUS_DONE replay short-circuits,
        # so the marker would never clear). The marker carries everything _run_remediation
        # needs (it does NOT depend on the ledger), so this is correct even if the ledger
        # became unreadable on resume.
        pending = self.state.gap_followup_state.get("pending_remediation")
        if pending is not None:   # an empty {} marker is PRESENT-but-malformed → fail-closed
            return self._complete_pending_remediation(pending)   #   (Codex R4 NB-1), not ignored
        if not self.ledger:
            return GAP_DONE   # DORMANT — no requirement ledger wired (byte-identical to today)
        try:
            gap_report = self._build_gap_report()
        except Exception as exc:  # noqa: BLE001 — clause 3 fail-closed (Codex R1 B1)
            # A wired-ledger gap projection that fails is an ambiguous/unknowable gap →
            # HALT to needs_human, never silently finish the campaign.
            self._audit("campaign_gap_followup_blocked",
                        {"reason": "gap_report_unavailable",
                         "error": f"{type(exc).__name__}: {exc}"})
            self._pause_gap_review("ineligible:gap_report_unavailable", [])
            return GAP_PAUSED
        eligible, gap_items, reason = self._gap_followup_eligible(gap_report)
        if not eligible:
            if reason == "no_gap":
                return GAP_DONE   # nothing to complete → finish
            if reason == "not_fresh_signed":
                # T2-A B3 (the fix): a STALE/pre-F1 plan at backlog exhaustion must NOT
                # silently finish (the pre-T2-A bug collapsed this into GAP_DONE → run() →
                # STATUS_DONE). RE-PAUSE for re-sign instead. The cursor is at the backlog
                # boundary, where _check_state_consistency permits ONLY a completeness_gap_-
                # review pause (with its nonce checkpoint) — so this re-pauses at that gate
                # (gap_status names the cause); the human re-signs the plan and resumes with
                # an adjust_scope decision to proceed. (The durable freshness overlay is for
                # MID-milestone gates, which can pause as campaign_plan_signoff; the boundary
                # cannot.) gap_items is [] here — eligibility yields no trustworthy gap.
                self._audit("campaign_gap_followup_blocked", {"reason": reason})
                self._pause_gap_review("not_fresh_signed", gap_items)
                return GAP_PAUSED
            # ambiguous gap or a quality-fault milestone in the gap → fail-closed (clause 3).
            self._audit("campaign_gap_followup_blocked", {"reason": reason})
            self._pause_gap_review(f"ineligible:{reason}", gap_items)
            return GAP_PAUSED

        # An in-envelope completeness gap exists. Decide whether to act on it.
        if review_decision is not None:
            action = interpret_dispatch(GAP_REVIEW_CHECKPOINT, review_decision)
            if action == ACT_GAP_ACCEPT:
                self._audit("campaign_gap_followup_accepted",
                            {"gap": [g.get("req_id") for g in gap_items]})
                return GAP_DONE
            if action == ACT_END:
                self._end("gap_followup_aborted")
                return GAP_ENDED
            if action != ACT_GAP_REMEDIATE:
                # fail-closed: an unrecognized adjust_scope choice surfaces, never acts.
                self._pause_gap_review("ambiguous_decision", gap_items)
                return GAP_PAUSED
            # ACT_GAP_REMEDIATE → the human authorized THIS round → fall through to dispatch.
        elif self._autonomy_level() not in _AUTO_GAP_DISPATCH_LEVELS:
            # human_in_the_loop: a completeness gap_report routes to needs_human.
            self._audit("campaign_gap_followup_review",
                        {"gap": [g.get("req_id") for g in gap_items],
                         "autonomy": self._autonomy_level()})
            self._pause_gap_review("human_in_the_loop", gap_items)
            return GAP_PAUSED
        # else human_on_the_loop+ with no pending review → auto-dispatch (no pause).

        # ----- dispatch path: clause 1, clause 2, then ONE bounded remediation round ---- #
        milestone, _idx, covered_req_ids = self._select_gap_target(gap_items)
        if milestone is None:                       # defensive (eligibility already checked)
            self._pause_gap_review("no_target", gap_items)
            return GAP_PAUSED
        ok, why = self._req_id_envelope_check(milestone, covered_req_ids)
        if not ok:
            self._audit("campaign_gap_followup_blocked",
                        {"reason": why, "milestone_id": milestone["id"],
                         "covered_req_ids": covered_req_ids})
            self._pause_gap_review(f"envelope:{why}", gap_items,
                                   milestone_id=milestone["id"])
            return GAP_PAUSED
        gap_now = {g.get("req_id") for g in gap_items if g.get("req_id")}
        ok, why, next_no_progress = self._gap_followup_bounds(milestone, gap_now)
        if not ok:
            self._audit("campaign_gap_followup_blocked",
                        {"reason": why, "milestone_id": milestone["id"]})
            self._pause_gap_review(f"bounds:{why}", gap_items,
                                   milestone_id=milestone["id"])
            return GAP_PAUSED

        gfs = self._gap_state()
        round_n = gfs["rounds_by_milestone"].get(milestone["id"], 0) + 1
        remediation_id, id_why = self._safe_remediation_id(milestone, round_n)
        if remediation_id is None:
            # §1.7-F clause 3 (Codex R1 B5): a generated id that COLLIDES with a signed
            # sub-sprint id or OVERFLOWS the loop_id length cap HALTs to needs_human — it
            # never crashes make_run_unit nor reuses a (campaign, milestone, subsprint)
            # loop_id.
            self._audit("campaign_gap_followup_blocked",
                        {"reason": f"unsafe_remediation_id:{id_why}",
                         "milestone_id": milestone["id"]})
            self._pause_gap_review(f"unsafe_id:{id_why}", gap_items,
                                   milestone_id=milestone["id"])
            return GAP_PAUSED
        # Persist the IN-FLIGHT marker + DURABLY clear the pause (→ RUNNING) BEFORE the
        # side-effecting dispatch (Codex R2 B2 + R1 B2(b)). The marker captures everything
        # the atomic round-save needs, so a crash after the gapfix Driver runs but before
        # that save replays through STATUS_RUNNING crash-recovery → _complete_pending_-
        # remediation RE-ENTERS this exact gapfix (resume=True; a completed Driver returns
        # its outcome with no re-run) — never a double-dispatch, never a re-consumed paused
        # decision.
        gfs["pending_remediation"] = {
            "milestone_id": milestone["id"], "remediation_id": remediation_id,
            "round": round_n, "covered_req_ids": covered_req_ids,
            "gap_set": sorted(gap_now), "no_progress": next_no_progress,
            # Bind the marker to the signed scope epoch it was authorized under (Codex R4 B1):
            # a plan/charter edit between this save and a crash-resume changes the live hash,
            # so _complete_pending_remediation refuses the stale marker.
            "scope_hash": self._live_signed_scope_hash()}
        self._save()
        return self._run_remediation(milestone, remediation_id, covered_req_ids,
                                     round_n, gap_now, next_no_progress, resume=False)

    # ----- resume decision-execution (design §5.4a; increment 2) ---------- #
    def _handle_resume(self, decision_resolver) -> str:
        """Act on a resolved pause BEFORE re-entering the loop. Returns
        'proceed' | 'paused' | 'ended'. Mechanism A (driver-resumable) arms the next
        dispatch with resume=True; Mechanism B interprets the human decision into a
        campaign action (advance-milestone / redispatch-fresh / deliver-followup /
        end)."""
        reason = self.state.pause_reason

        # Campaign-tier re-checks that depend on UPDATED PLAN state (not a decision):
        if reason == "campaign_plan_signoff":
            # Δ-19 F1: honor only a FRESH-signed plan (stored hash == live hash). A
            # stale/pre-F1/unsigned plan re-pauses (the `why` carries the status so the
            # CLI distinguishes "stale-signed / blocked pending re-sign" from "unsigned").
            status = self._signoff_status()
            if status != "signed":
                return self._repause(reason, status)
            # B4 — a DURABLE freshness-block overlay means a mid-run gate blocked here for
            # re-sign while preserving its ORIGINAL gate. Now fresh-signed: consume the
            # overlay and RE-DISPATCH that original gate so the campaign resumes exactly
            # where it blocked (the gate's decision file/nonce is unchanged). A mid-drive
            # block (no original gate) just proceeds and re-dispatches the cursor.
            if self.state.freshness_block is not None:
                orig = self._consume_freshness_block()
                if not orig or orig == "campaign_plan_signoff":
                    return "proceed"
                return self._handle_resume(decision_resolver)
            return "proceed"
        if reason == "milestone_decompose_required":
            ms = self.milestones[self.state.milestone_index]
            return ("proceed" if ms.get("subsprint_sequence")
                    else self._repause(reason, "still_undecomposed"))
        if reason == GAP_REVIEW_CHECKPOINT:
            # Track 2 Phase 2-γ / §1.7-F: the completeness gate (human_in_the_loop review OR
            # a clause-3 fail-closed escalation). STASH the human's adjust_scope decision so
            # the OUTER-loop engine (_gap_followup_round) consumes it once — its
            # remediate/accept_gap/abort handling is the SAME for the auto and human paths.
            # No decision ⇒ re-pause (the gap is unresolved).
            decision = (decision_resolver(reason, self.state.pause_checkpoint)
                        if decision_resolver is not None else None)
            if not decision:
                return self._repause(reason, "decision_pending")
            self._gap_review_decision = decision
            self._audit("campaign_resume_dispatch",
                        {"pause_reason": reason, "choice": decision.get("choice")})
            return "proceed"
        if reason == "milestone_merge":
            decision = (decision_resolver(reason, self.state.pause_checkpoint)
                        if decision_resolver is not None else None)
            if not decision:
                return self._repause(reason, "decision_pending")
            choice = decision.get("choice")
            if choice == "abort":
                self._end("milestone_merge_aborted")
                return "ended"
            # T2-A B5: before the IRREVERSIBLE merge + cursor advance, the signed plan
            # (whose trunk_branch / milestone_isolation now bind into H) must be fresh-
            # signed. A post-sign merge-target / merge-gate / cleanup edit ⇒ stale ⇒ block
            # for re-sign (the overlay preserves THIS milestone_merge gate). Read-only,
            # OUTSIDE the §3.5c barrier — it can only convert a would-be advance into a
            # durable block, never half-merge/half-advance.
            if not self._authority_fresh():
                return self._block_for_resign(reason)
            # Capture the milestone id + run any (irreversible) merge BEFORE the cursor
            # advance nulls milestone_context.
            mid = (self.state.milestone_context or {}).get("milestone_id")
            merge_action = (self._execute_milestone_merge()
                            if choice == "merge_now" else None)
            # §3.5c crash-idempotency barrier: fold the cursor advance + the pause-clear
            # into ONE durable save BEFORE the audits, so a crash in the audit window
            # replays through STATUS_RUNNING crash-recovery (no re-interpret → no
            # double-advance / double-merge-advance), not from a PAUSED advanced cursor.
            self._advance_milestone_cursor(save=False)
            self._commit_dispatch_resolution()
            if merge_action is not None:
                self._audit("campaign_milestone_merged", {
                    "milestone_id": mid,
                    "action": merge_action, "trunk": self._trunk_branch})
            self._audit("campaign_resume_dispatch",
                        {"pause_reason": reason,
                         "action": "advance_after_merge", "choice": choice})
            return "proceed"
        if reason == "deliver_followup_required":
            # The manual follow-up contract (Codex inc-2 #3): Deliver INSERTS the
            # follow-up sub-sprint at cursor+1. A genuine insertion is detected iff the
            # sequence GREW past the length recorded when we paused — so a pre-existing
            # next sub-sprint is NOT mistaken for an insertion (and not auto-dispatched).
            ms = self.milestones[self.state.milestone_index]
            seq = ms.get("subsprint_sequence") or []
            baseline = self.state.followup_baseline_seq or []
            nxt = self.state.subsprint_index + 1
            # Advance ONLY if the item at cursor+1 is a NEWLY inserted follow-up — an
            # id NOT in the snapshot taken at pause time. So neither a pre-existing next
            # sub-sprint NOR an append-elsewhere is mistaken for the insertion (Codex
            # inc-2 #3: prove "inserted at cursor+1", not just "the sequence grew").
            if nxt < len(seq) and seq[nxt] not in baseline:
                # TD6 (R3 nit #2): the legitimate insertion GREW subsprint_sequence (inside
                # H), so the live plan now reads 'stale'. Run the engine re-stamp as a
                # SPECIAL PRE-FRESHNESS step (a generic freshness gate ahead of it would
                # over-pause this legitimate path). The exact-diff guard re-stamps the SINGLE
                # epoch ONLY when the live↔signed delta is EXACTLY this one cursor+1
                # insertion; any other delta REFUSES ⇒ stays stale ⇒ block for re-sign. On a
                # crash replay where _reapply_engine_restamp already re-applied the pinned
                # epoch, the plan already reads 'signed' (so the re-stamp is not re-entered).
                if f1_required(self.plan) and not self._authority_fresh():
                    if not self._restamp_followup_epoch(nxt):
                        return self._block_for_resign(reason)
                    # Defense (Codex R1 B2): the re-stamp must ACHIEVE fresh-signed — if the
                    # plan still does not read 'signed' (some residual authority drift the
                    # guard did not absorb), block rather than dispatch.
                    if not self._authority_fresh():
                        return self._block_for_resign(reason)
                self.state.subsprint_index = nxt
                self.state.followup_baseline_seq = None
                self._audit("campaign_resume_dispatch",
                            {"pause_reason": reason, "action": "advance_to_followup",
                             "followup": seq[nxt]})
                return "proceed"
            return self._repause(reason, "awaiting_deliver_followup")

        # Otherwise consult the human's resolved decision for the checkpoint.
        decision = (decision_resolver(reason, self.state.pause_checkpoint)
                    if decision_resolver is not None else None)
        if not decision:
            return self._repause(reason, "decision_pending")

        if classify_checkpoint(reason) == RESUME_DRIVER:
            # T2-A: arming a Mechanism-A driver resume re-enters the paused Driver and
            # dispatches on signed scope → the plan must be fresh-signed first. A post-sign
            # edit ⇒ stale ⇒ block for re-sign (the overlay preserves THIS decision-bound
            # checkpoint so the driver resume re-arms after re-sign).
            if not self._authority_fresh():
                return self._block_for_resign(reason)
            # Mechanism A: the Driver re-enters the paused state on the next dispatch.
            self._pending_driver_resume = True
            self._audit("campaign_resume_driver", {"pause_reason": reason})
            return "proceed"

        # Mechanism B + campaign-level dispatch.
        if reason == "campaign_budget_exhausted":
            if decision.get("choice") == "raise_cap":
                # Track-2 T2-B N3: budget.* is now inside the signed hash H, so a raised
                # cap is a SIGNED scope change — the human must RE-SIGN the raised budget,
                # not bump it in memory. On an F1-active plan, re-read the live budget and
                # gate it through the universal freshness check: a fresh re-sign (the
                # raised plan was re-stamped) proceeds; an in-memory/unsigned raise stays
                # stale and re-pauses for re-sign (durable overlay preserves this gate).
                # Non-F1 plans keep the legacy in-memory bump (byte-identical).
                self.budget = self.plan.get("budget") or {}  # re-read the (raised) budget
                if not self._authority_fresh():
                    return self._block_for_resign(reason)
                self._audit("campaign_resume_dispatch",
                            {"pause_reason": reason, "action": "raise_cap"})
                return "proceed"
            self._end("campaign_budget_aborted")
            return "ended"

        action = interpret_dispatch(reason, decision)
        dispatch_audit = {"pause_reason": reason, "action": action,
                          "choice": decision.get("choice") or decision.get("confirm")}
        # acceptance_cleanup_required → accept_residue_and_ship ships KNOWN residue: when
        # interpret_dispatch admitted it (a COMPLETE waiver → ACT_ADVANCE_MILESTONE) a
        # DEDICATED audit makes the waiver always attributable — recording BOTH marker
        # forms (`waiver` bool AND `waiver_id`) so a `waiver: true` marker is never lost
        # (Codex blocking 2). An incomplete waiver never reaches here (it fails closed to
        # ACT_DELIVER_FOLLOWUP and surfaces). Computed now but EMITTED after the §3.5c
        # barrier below, with the dispatch audit (Codex blocking 3).
        waiver_audit = None
        if (reason == "acceptance_cleanup_required"
                and action == ACT_ADVANCE_MILESTONE):
            waiver = residue_waiver(decision) or {}
            waiver_audit = {"residue": waiver.get("residue"),
                            "rationale": waiver.get("rationale"),
                            "evidence": waiver.get("evidence"),
                            "waiver": waiver.get("waiver"),
                            "waiver_id": waiver.get("waiver_id")}

        # CURSOR-ADVANCING outcomes: advance the cursor, then DURABLY clear the pause —
        # the §3.5c crash-idempotency barrier (_commit_dispatch_resolution) — BEFORE the
        # resume audits. A crash in the audit window then replays through STATUS_RUNNING
        # crash-recovery (which never re-interprets the cleared pause), so neither the
        # cursor nor the waiver audit can double (Codex blocking 3). acceptance_surface_
        # approve (approve_ship) and review_out_of_scope (accept_and_advance) flow through
        # here too, so the WHOLE advancing dispatch path is crash-idempotent, consistently
        # with the milestone_merge advance above.
        if action in (ACT_ADVANCE_SUBSPRINT, ACT_ADVANCE_MILESTONE):
            # T2-A B5: a cursor-advancing ship acts on signed scope — gate it BEFORE
            # stamping the terminal outcome / advancing the cursor / clearing the pause (the
            # §3.5c barrier). A post-sign edit ⇒ stale ⇒ block for re-sign (the overlay
            # preserves THIS acceptance gate). Read-only, OUTSIDE the barrier — it can only
            # convert a would-be advance into a durable block, never strand a half-cursor.
            if not self._authority_fresh():
                return self._block_for_resign(reason)
            if action == ACT_ADVANCE_SUBSPRINT:
                self.state.subsprint_index += 1   # this sub-sprint accepted → next in milestone
            else:                                 # ACT_ADVANCE_MILESTONE
                # Δ-19 F3: a human ship decision at an Acceptance gate CLOSES this
                # milestone — stamp its terminal outcome (delivered vs waived-with-reason)
                # from (pause_reason, decision) BEFORE the cursor advances. This path does
                # NOT go through _complete_milestone, so it stamps here.
                closing = self.milestones[self.state.milestone_index]["id"]
                self._stamp_milestone_outcome(
                    closing, _RESUME_ADVANCE_TERMINAL.get(reason, "not_shipped"),
                    pause_reason=reason, decision_ref=self.state.pause_checkpoint)
                self.state.milestone_index += 1   # milestone accepted → next milestone
                self.state.subsprint_index = 0
            self._commit_dispatch_resolution()    # barrier: clear pause → RUNNING + save
            self._audit("campaign_resume_dispatch", dispatch_audit)
            if waiver_audit is not None:
                self._audit("campaign_acceptance_residue_waived", waiver_audit)
            return "proceed"

        # T2-A: re-dispatching the SAME unit fresh acts on signed scope → it must be fresh-
        # signed. Gate BEFORE the dispatch audit (Codex R1 NB-2) so a stale block does not
        # leave a durable "redispatch selected" audit it never honored. END/FOLLOWUP do not
        # act on signed scope here (END terminates; FOLLOWUP parks for Deliver and its real
        # dispatch is the freshness-gated deliver_followup_required path), so they keep the
        # audit. The cursor is unchanged, so the block only converts a would-be re-dispatch
        # into a durable pause (the overlay preserves THIS gate).
        if action == ACT_REDISPATCH_FRESH and not self._authority_fresh():
            return self._block_for_resign(reason)
        # NON-advancing outcomes keep their existing durable-state semantics (each already
        # crash-idempotent): REDISPATCH_FRESH leaves the cursor + the PAUSED state intact
        # until the fresh re-dispatch records progress; END / FOLLOWUP persist a
        # terminal/parked state via _end/_pause that a replay short-circuits (ENDED) or
        # routes through the dedicated deliver_followup branch — never re-interpreting
        # this dispatch.
        self._audit("campaign_resume_dispatch", dispatch_audit)
        if action == ACT_REDISPATCH_FRESH:
            return "proceed"                  # re-dispatch the SAME unit fresh (cursor unchanged)
        if action == ACT_END:
            self._end("resolved_abort")
            return "ended"
        # ACT_DELIVER_FOLLOWUP — a new unit must be authored by Deliver; surface it.
        # Record the sequence length NOW so resume can tell a genuine insertion (len
        # grew) from a pre-existing next sub-sprint (Codex inc-2 #3).
        self.state.followup_baseline_seq = list(
            self.milestones[self.state.milestone_index].get("subsprint_sequence") or [])
        self._pause("deliver_followup_required", self.state.pause_checkpoint,
                    "campaign_deliver_followup_required", {"for_reason": reason})
        return "paused"

    # ----- the loop ------------------------------------------------------ #
    def run(self, *, resume: bool = False, decision_resolver=None) -> CampaignState:
        """Drive the backlog from the cursor. Returns the (terminal-or-paused)
        CampaignState. Pauses persist + return so a human can resolve + resume.

        `decision_resolver(pause_reason, checkpoint_path) -> Optional[dict]` is the
        human's voice on resume for Mechanism-B gates (injected, like the Driver's
        gate_resolver); None / a None return ⇒ the pause stays (re-pause)."""
        self._pending_driver_resume = False
        self._crash_recovery = False  # §3.5c: set True only on STATUS_RUNNING recovery
        self._gap_review_decision = None  # §1.7-F: a human adjust_scope decision, consumed once
        if resume and self._load():
            # TD6: deterministically RE-APPLY any engine-authored deliver_followup re-stamp
            # to the in-memory signoff BEFORE any freshness consumer runs, so a legitimately-
            # grown plan reads 'signed' this whole invocation (no plan-file write-back; the
            # pinned epoch hash is the cross-invocation proof). A no-op when no re-stamp is
            # recorded or the live plan no longer matches the pinned epoch (then it stays
            # stale and is blocked).
            self._reapply_engine_restamp()
            self._audit("campaign_resume",
                        {"from_status": self.state.status,
                         "pause_reason": self.state.pause_reason})
            if self.state.status in (STATUS_DONE, STATUS_ENDED):
                return self.state
            if self.state.status == STATUS_PAUSED:
                outcome = self._handle_resume(decision_resolver)
                if outcome in ("paused", "ended"):
                    return self.state
                # proceed → clear the pause; drive from the (possibly advanced) cursor.
                self.state.status = STATUS_RUNNING
                self.state.pause_reason = None
                self.state.pause_checkpoint = None
            elif self.state.status == STATUS_RUNNING:
                # STATUS_RUNNING on load → crash recovery: continue from the persisted
                # cursor WITHOUT re-interpreting a (non-existent) pause (Codex inc-2
                # blocking #4). §3.5c: arm the one-shot reconcile so the first cursor unit
                # re-dispatches with resume=True (idempotent Driver re-entry) and is not
                # double-accounted / double-appended if it already ran before the crash.
                self._crash_recovery = True
        else:
            self._audit("campaign_start",
                        {"campaign_id": self.campaign_id,
                         "goal": self.plan.get("goal"),
                         "milestones": [m["id"] for m in self.milestones]})
            status = self._signoff_status()
            if status != "signed":
                # The campaign plan (the milestone backlog) MUST be Customer-signed
                # before the runner drives it — the campaign-tier human gate
                # `campaign_plan_signoff` (design §5.1; 以终为始). Enforced HERE at the
                # campaign tier (NOT the charter validator — that validates charters,
                # not campaign plans). Δ-19 F1: when the plan opts into the signed
                # resolved-scope snapshot (a `signoff` block or any covers_req_ids),
                # signed ⟺ stored hash == live hash; a stale/pre-F1 plan re-pauses for a
                # re-sign (NOT treated as plain "unsigned"). Resume once re-signed.
                return self._pause("campaign_plan_signoff", None,
                                   "campaign_plan_signoff",
                                   {"goal": self.plan.get("goal"),
                                    "signoff_status": status})
        # Accumulate wall-clock across resume: base = persisted total; we add only
        # THIS invocation's active delta (excludes human-wait while paused), so
        # max_wall_clock_minutes can't be evaded by pause/resume.
        self._base_wall = self.state.wall_clock_minutes
        self._invocation_start = self.clock()

        while True:
            paused = self._drive_milestones()
            if paused is not None:
                return paused
            # Backlog exhausted → Track 2 Phase 2-γ / §1.7-F gap-followup decision. This
            # OUTER loop is the ONLY structural change Phase 2-γ makes to run(): the cursor
            # stays at (len, 0) and any remediation is dispatched DIRECTLY inside
            # _gap_followup_round (never via the milestone cursor), so the inner milestone
            # loop is untouched and already-completed milestones are never re-run.
            outcome = self._gap_followup_round(decision_resolver)
            if outcome == GAP_CONTINUE:
                continue            # a bounded in-envelope remediation round ran; re-check
            if outcome in (GAP_PAUSED, GAP_ENDED):
                return self.state   # needs_human / human review / abort — already persisted
            break                   # GAP_DONE → finish the campaign

        # backlog exhausted + gap-followup complete.
        self.state.status = STATUS_DONE
        self._audit("campaign_done",
                    {"subsprints_run": self.state.subsprints_run,
                     "total_spawns": self.state.total_spawns})
        self._save()
        return self.state

    def _drive_milestones(self) -> Optional["CampaignState"]:
        """Drive the milestone backlog from the cursor (the inner loop, UNCHANGED from the
        pre-Phase-2-γ campaign). Returns a PAUSED/ENDED CampaignState to halt run(), or None
        when the backlog is exhausted (→ run()'s §1.7-F gap-followup decision)."""
        while self.state.milestone_index < len(self.milestones):
            milestone = self.milestones[self.state.milestone_index]
            seq = list(milestone.get("subsprint_sequence") or [])
            if not seq:
                # No pre-authored sub-sprints: the per-milestone decompose
                # (full_chain_guided) is a Deliver step — surface it (this core
                # does not auto-author sub-sprints).
                return self._pause(
                    "milestone_decompose_required",
                    None, "campaign_milestone_decompose_required",
                    {"milestone_id": milestone["id"]})

            if not self.state.pending_milestone_advance:
                self._ensure_milestone_context(milestone)

            while self.state.subsprint_index < len(seq):
                # Countable budget cap, checked BETWEEN units (design §5.4a).
                over = self._over_budget()
                if over:
                    return self._pause("campaign_budget_exhausted", None,
                                       "campaign_budget_exhausted", {"dimension": over})

                subsprint_id = seq[self.state.subsprint_index]
                # §3.5c crash-recovery reconcile (Codex round-2 BLOCKING-1 / MAJOR-1 +
                # impl-review MAJOR-2): on a STATUS_RUNNING recovery the cursor unit may
                # already have RUN + been ACCOUNTED + appended (a crash between the
                # pause-branch `_save()` at the bottom of this body and the STATUS_PAUSED
                # save inside `_pause`). Detect it — the last recorded unit matches the
                # cursor — and REPLAY the advance/done/pause branch from that unit's
                # RECORDED `final_state` WITHOUT re-dispatching run_unit (no fresh re-run of
                # the whole unit, no duplicate browser execution / Acceptance) and WITHOUT
                # re-accounting / re-appending. The pause branch persists `pause_reason` +
                # `checkpoint_path` INTO the unit record, so a halted replay re-pauses with
                # no re-run. `crash_recover` is one-shot (only the first cursor unit); an
                # in-flight unit NOT yet recorded instead re-dispatches with resume=True so
                # the Driver re-enters its persisted state idempotently, accounted once.
                crash_recover = self._crash_recovery
                self._crash_recovery = False
                already = bool(
                    crash_recover and self.state.units
                    and self.state.units[-1].get("milestone_id") == milestone["id"]
                    and self.state.units[-1].get("subsprint_id") == subsprint_id)
                if already:
                    # REPLAY from the recorded unit — do NOT call run_unit, do NOT account.
                    self._pending_driver_resume = False
                    summary = dict(self.state.units[-1])
                    final_state = summary.get("final_state")
                else:
                    resume_this = self._pending_driver_resume or crash_recover
                    self._pending_driver_resume = False
                    # T2-A B5: before dispatching this unit, the signed plan must still be
                    # fresh-signed (a dispatch reads LIVE functional_acceptance/seq). A stale
                    # edit ⇒ block for re-sign BEFORE the irreversible run_unit. This gate is
                    # UNCONDITIONAL — a STATUS_RUNNING crash-recovery re-dispatch (Codex R1 B1)
                    # may point at a not-yet-recorded next unit after a §3.5c-barrier cursor
                    # advance, and a Mechanism-A driver resume re-dispatches a cursor unit
                    # too, so neither may dispatch stale signed scope. A fresh-signed plan
                    # passes unchanged (a Mechanism-A resume already validated freshness at
                    # its resume site, so this is a no-op pass); only a genuinely stale plan
                    # blocks (mid-drive block: no original gate ⇒ re-dispatch the cursor after
                    # re-sign). Read-only, OUTSIDE the §3.5c barrier — never strands a cursor.
                    if not self._authority_fresh():
                        self._block_for_resign(self.state.pause_reason)
                        return self.state
                    # Pass THIS milestone's LIVE sequence + its functional_acceptance so the
                    # production run_unit derives a per-milestone execution context whose
                    # terminal sub-sprint anchors Acceptance (design §5) and whose acceptance
                    # class (static | browser_e2e) is projected per milestone (P-C). `seq` is
                    # re-read each milestone, so a governed deliver_followup insertion is
                    # reflected (Codex review #3).
                    summary = self.run_unit(
                        subsprint_id, milestone_id=milestone["id"],
                        subsprint_sequence=seq, resume=resume_this,
                        functional_acceptance=milestone.get("functional_acceptance"),
                        repo_dir=self._milestone_work_dir())
                    final_state = summary.get("final_state")
                    self.state.subsprints_run += 1
                    self.state.total_spawns += int(summary.get("spawn_count") or 0)
                    self.state.wall_clock_minutes = (
                        self._base_wall
                        + _iso_minutes(self._invocation_start, self.clock()))
                unit = {"milestone_id": milestone["id"], "subsprint_id": subsprint_id,
                        "status": "done", "final_state": final_state,
                        "loop_id": summary.get("loop_id")}

                if final_state in _ADVANCE_STATES:
                    unit["status"] = "done"
                    if not already:
                        self.state.units.append(unit)
                    self.state.subsprint_index += 1
                    self._audit("campaign_subsprint_advance",
                                {"milestone_id": milestone["id"],
                                 "subsprint_id": subsprint_id,
                                 "loop_id": summary.get("loop_id"),
                                 "final_state": final_state,
                                 "spawn_count": int(summary.get("spawn_count") or 0),
                                 "subsprints_run": self.state.subsprints_run,
                                 "total_spawns": self.state.total_spawns})
                    self._save()
                    continue
                if final_state in _MILESTONE_DONE_STATES:
                    unit["status"] = "done"
                    if not already:
                        self.state.units.append(unit)
                    self._audit("campaign_milestone_done",
                                {"milestone_id": milestone["id"],
                                 "subsprint_id": subsprint_id,
                                 "loop_id": summary.get("loop_id"),
                                 "final_state": final_state})
                    break  # milestone accepted → advance milestone
                # ANY other final_state → PAUSE (covers STATE_HALTED + the guided
                # pending states; design §5.4a pause detection).
                reason = summary.get("pause_reason") or final_state or "unknown_halt"
                unit["status"] = "halted"
                # Persist the pause reason + checkpoint INTO the unit record so a §3.5c
                # crash-recovery REPLAY (already) can re-pause WITHOUT re-running the unit.
                unit["pause_reason"] = reason
                unit["checkpoint_path"] = summary.get("checkpoint_path")
                if not already:
                    self.state.units.append(unit)
                self._save()
                return self._pause(
                    reason, summary.get("checkpoint_path"),
                    "campaign_pause",
                    {"milestone_id": milestone["id"], "subsprint_id": subsprint_id,
                     "loop_id": summary.get("loop_id"), "final_state": final_state,
                     "resume_class": classify_checkpoint(reason)})

            # milestone complete → optional merge gate → advance cursor.
            paused = self._complete_milestone(milestone)
            if paused is not None:
                return paused

        # backlog exhausted → run()'s outer loop handles the §1.7-F gap-followup decision.
        return None


def run_campaign(plan: dict, run_dir: str, run_unit: RunUnit, *,
                 clock: Callable[[], str], audit_dir: Optional[str] = None,
                 resume: bool = False, decision_resolver=None,
                 repo_dir: Optional[str] = None,
                 charter: Optional[dict] = None,
                 ledger_path: Optional[str] = None) -> CampaignState:
    """Convenience entry point — construct a Campaign and run it."""
    return Campaign(plan, run_dir, run_unit, clock=clock,
                    audit_dir=audit_dir, repo_dir=repo_dir, charter=charter,
                    ledger_path=ledger_path).run(
                        resume=resume, decision_resolver=decision_resolver)


# --------------------------------------------------------------------------- #
# Production run_unit — drive ONE sub-sprint via scheduling.run_loop (increment 2).
# --------------------------------------------------------------------------- #
def latest_checkpoint(checkpoints_dir: str):
    """(checkpoint_id, path) of the most-recent checkpoint file, or (None, None).
    The Driver names checkpoints `<ts>__<checkpoint_id>__<scope>.md` (ts is
    lexically sortable), written under `<run_dir>/docs/checkpoints/`."""
    if not os.path.isdir(checkpoints_dir):
        return None, None
    files = sorted(f for f in os.listdir(checkpoints_dir)
                   if _CHECKPOINT_FILE_RE.match(f))   # ignore stray .md (Codex inc-2 #6)
    if not files:
        return None, None
    latest = files[-1]
    parts = latest[:-3].split("__")
    cid = parts[1] if len(parts) >= 2 else None
    return cid, os.path.join(checkpoints_dir, latest)


# --------------------------------------------------------------------------- #
# Per-milestone execution context (the multi-milestone Acceptance fix).
#
# The Driver fires the milestone-close Acceptance gate ONLY at the TERMINAL
# sub-sprint of charter.autonomy.approved_scope.subsprint_sequence
# (driver._milestone_complete). With ONE shared charter across a whole campaign,
# only the campaign's LAST sub-sprint is terminal — so non-final milestones close
# with NO Acceptance gate, violating design §5 (Acceptance at EVERY milestone close).
#
# Fix: before dispatching a milestone's sub-sprint, PROJECT the canonical charter
# onto that milestone — a deterministic copy whose approved_scope.subsprint_sequence
# is THAT milestone's sequence (taken from the Customer-signed campaign plan). The
# milestone's final sub-sprint is then terminal, so Acceptance fires per milestone.
# The projection is an orchestrator-DERIVED execution context, NOT a re-signed
# charter: its provenance records customer_signed:false + the source hashes, and it
# adds no charter fields (the root charter schema is additionalProperties:false, so
# a real-run schema enforcement would reject a provenance key ON the charter — it is
# recorded as a per-unit `derived-context.json` sidecar instead).
# --------------------------------------------------------------------------- #
def _canonical_sha256(obj: Any) -> str:
    """SHA-256 over a canonical (sorted-key) JSON encoding — a stable content
    fingerprint independent of dict ordering, for the derivation provenance."""
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Δ-19 F1/G1 — the signed RESOLVED-scope SNAPSHOT + hash (design §3.3.1).
#
# This gives campaign_plan_signoff INTEGRITY: a plan cannot be edited after signoff
# (remove a milestone, change a future covers_req_ids, or flip an inheriting
# milestone's resolved acceptance via a charter-default change) while staying
# "signed". The runner recomputes the LIVE resolved envelope + hash at load and
# honors `signed` ONLY when the stored signed_scope_hash matches. It adds NO new
# checkpoint id (B5) — it tightens the EXISTING campaign_plan_signoff gate.
# --------------------------------------------------------------------------- #
def _canonical_json(obj: Any) -> str:
    """Canonical JSON for hashing/fingerprints: UTF-8, sorted keys, no insignificant
    whitespace (design §3.3.1)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def render_gapfix_dev_prompt(spec: dict, subsprint_id: str,
                             milestone_id: Optional[str]) -> str:
    """Track 2 Phase 2-γ / §1.7-F clause 1 (Codex R1 B4): render the generated remediation's
    in-envelope work contract into a SELF-CONTAINED compact Dev prompt the Driver resolves
    (driver._load_compact_file → compact/<id>-dev-prompt.md). The front-matter
    context_budget.self_contained:true + the objective/scope_in/exit_criteria satisfy
    driver._validate_compact_text, so on a LIVE run Deliver addresses EXACTLY the
    covered_req_ids — the req_id proof is BOUND into the contract, never a bare/unbounded
    run, never scope expansion."""
    cov = list(spec.get("covered_req_ids") or [])
    lines = [
        "---", "context_budget:", "  self_contained: true", "---",
        f"You are activating as the Dev Agent for gap-followup sub-sprint {subsprint_id} "
        f"(milestone {milestone_id}).", "",
        "This is a Constitution §1.7-F PRE-AUTHORIZED in-envelope completeness remediation: "
        "deliver the human-signed requirements below that were signed into this milestone's "
        "covers_req_ids but are NOT yet delivered. IN-ENVELOPE COMPLETION ONLY — do NOT "
        "widen scope beyond these requirement ids (§1.7-F forbids scope expansion); if you "
        "cannot satisfy them without new scope, HALT for human review.", "",
        "Cold-start the role-session governance chain + role-cards/dev-agent.md.", "",
        f"Objective:\n  {spec.get('objective', '')}", "",
        "Covered requirement ids (the ONLY in-envelope scope):",
    ]
    lines += [f"  - {rid}" for rid in cov] or ["  - (none)"]
    lines += ["", "Scope IN (deliverables):"]
    lines += [f"  - {s}" for s in (spec.get("scope_in") or [])]
    lines += ["", "Exit criteria (close conditions):"]
    lines += [f"  - {e}" for e in (spec.get("exit_criteria") or [])]
    return "\n".join(lines) + "\n"


def resolve_functional_acceptance(charter: Optional[dict],
                                  functional_acceptance: Optional[str]):
    """The RESOLVED per-milestone acceptance class (mode, source) — the SAME precedence
    derive_milestone_context applies: an explicit milestone value (incl. 'static')
    OVERRIDES (source='milestone'); absent INHERITS the charter
    tooling.acceptance.functional.mode (source='charter'); else ('static','default')."""
    charter_mode = ((((charter or {}).get("tooling") or {}).get("acceptance") or {})
                    .get("functional") or {}).get("mode")
    if functional_acceptance is not None:
        return functional_acceptance, "milestone"
    if charter_mode is not None:
        return charter_mode, "charter"
    return "static", "default"


_VALID_SURFACES = frozenset({"user_facing", "non_user_facing"})


def duplicate_requirement_ids(ledger: Optional[dict]) -> list:
    """The requirement ids that appear MORE THAN ONCE in the ledger — a malformed input
    contract (an AMBIGUOUS surface classification). Empty for a well-formed/absent ledger.
    OW-M3 rejects a ledger with duplicates (the sign-off gate refuses; the runner + strict
    sign/preflight loaders fail closed) so the {rid: surface} basis is unambiguous for BOTH
    the gate and the signed hash — closing the 'first duplicate says user_facing, last says
    non_user_facing' bypass."""
    seen, dups = set(), []
    for r in (ledger or {}).get("requirements") or []:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        if rid is None:
            continue
        if rid in seen and rid not in dups:
            dups.append(rid)
        seen.add(rid)
    return dups


def _ledger_surface(ledger: Optional[dict], rid: str) -> Optional[str]:
    """OW-M3 / B1: the `surface` classification of requirement `rid` in the wired
    requirement ledger, or None when no ledger is wired, `rid` is absent from it, or the
    requirement carries no surface. LAST occurrence wins — IDENTICAL to the id→req map the
    sign-off gate builds ({r['id']: r for ...}), so the gate decision and the hash-bound
    covered_req_surfaces can never disagree on a (rejected) duplicate id. Deterministic — a
    post-sign surface flip/removal changes this value, so the covered_req_surfaces map bound
    into H changes and the plan goes 'stale' (the tamper-detection basis of the mandate)."""
    surface = None
    for r in (ledger or {}).get("requirements") or []:
        if isinstance(r, dict) and r.get("id") == rid:
            surface = r.get("surface")
    return surface


def _covered_req_surfaces(milestone: dict, ledger: Optional[dict]) -> Optional[dict]:
    """OW-M3 / B1: the {rid: surface} basis that justifies THIS milestone's required
    acceptance class, bound into the signed envelope + H. Returns None — so the key is
    OMITTED from the envelope entry, byte-identical to pre-OW-M3 — when no ledger is
    wired OR the milestone covers no requirement; a legacy/dormant plan therefore hashes
    EXACTLY as today (additivity). Otherwise the map is over the milestone's
    covers_req_ids (canonical JSON sorts keys, so declared order is irrelevant). Sign-time
    and live freshness recompute both read the SAME (effective) ledger, so the field's
    presence never diverges (design §5.1 N1). `ledger` is the EFFECTIVE ledger from
    _effective_surfaces_ledger — the live one, or a stored-basis reconstruction."""
    if not ledger:
        return None
    covered = list(milestone.get("covers_req_ids") or [])
    if not covered:
        return None
    return {rid: _ledger_surface(ledger, rid) for rid in covered}


def _effective_surfaces_ledger(plan: Optional[dict],
                               ledger: Optional[dict]) -> Optional[dict]:
    """OW-M3: the ledger the covered_req_surfaces recompute uses. The LIVE ledger when
    available (so a post-sign surface flip flips the hash ⇒ 'stale'). When the live
    ledger is ABSENT/unreadable but the plan was SIGNED WITH covered_req_surfaces,
    reconstruct a minimal {id, surface} ledger from the STORED signed envelope so a
    transiently-unavailable ledger does NOT spuriously invalidate a signed plan —
    preserving Track-2's 'ledger-unreadable-on-resume / self-contained marker' resilience
    (a flip you cannot read cannot be detected, but the last SIGNED classification is
    honored — fail-safe). Returns None (⇒ dormant, field omitted) only when there is
    neither a live ledger nor a stored surface basis. NB: this is for the FRESHNESS
    recompute only; the sign-off / preflight GATE (mandatory_e2e_violations) always reads
    the raw live ledger."""
    if ledger:
        return ledger
    signoff = (plan or {}).get("signoff")
    env = signoff.get("scope_envelope") if isinstance(signoff, dict) else None
    if not isinstance(env, dict):
        return None
    surfaces: dict = {}
    for m in env.get("milestones") or []:
        for rid, s in (m.get("covered_req_surfaces") or {}).items():
            surfaces[rid] = s
    if not surfaces:
        return None
    return {"requirements": [{"id": rid, "surface": s}
                             for rid, s in surfaces.items()]}


def _envelope_milestone(charter: Optional[dict], milestone: dict,
                        ledger: Optional[dict] = None) -> dict:
    """One milestone's RESOLVED scope-envelope entry (design §3.3.1): the scope-bearing
    fields + the RESOLVED acceptance {mode,source} (not the literal, possibly-absent
    functional_acceptance). Absent arrays normalize to [] so absent-vs-empty doesn't
    churn the hash; acceptance_bar is the string or null. Track-2 T2-B: the per-milestone
    isolation_strategy (legacy/per-milestone branch-vs-worktree authority) joins the
    entry so a post-sign per-milestone strategy edit flips the hash (resolved to the
    same precedence the runner reads — absent ⇒ 'inherit'). OW-M3 B1: when a requirement
    ledger is wired AND this milestone covers requirements, the {rid: surface} basis is
    bound in as covered_req_surfaces (absent otherwise ⇒ byte-identical to pre-OW-M3)."""
    mode, source = resolve_functional_acceptance(
        charter, milestone.get("functional_acceptance"))
    entry = {
        "id": milestone.get("id"),
        "objective": milestone.get("objective"),
        "covers_req_ids": list(milestone.get("covers_req_ids") or []),
        "subsprint_sequence": list(milestone.get("subsprint_sequence") or []),
        "depends_on": list(milestone.get("depends_on") or []),
        "resolved_functional_acceptance": {"mode": mode, "source": source},
        "acceptance_bar": milestone.get("acceptance_bar"),
        # Track-2 T2-B: per-milestone isolation strategy (branch vs worktree); 'inherit'
        # when absent (the same default _resolve_milestone_strategy reads).
        "isolation_strategy": milestone.get("isolation_strategy") or "inherit",
    }
    surfaces = _covered_req_surfaces(milestone, ledger)
    if surfaces is not None:
        entry["covered_req_surfaces"] = surfaces
    return entry


def _resolve_plan_authority(plan: dict) -> dict:
    """Track-2 T2-B: the RESOLVED top-level authority block bound into the signed hash H
    (and stored in the scope_envelope). It mirrors the EXACT resolution the runner's
    constructor applies (Campaign.__init__: budget, milestone_isolation/legacy
    isolation_strategy, trunk_branch, gap_followup) so a post-sign edit that changes the
    effective authority — auto-remediation extent, non-progress tolerance, the campaign
    budget caps, the merge target/gate, worktree/branch placement or cleanup — flips the
    hash and the plan goes 'stale' until re-signed. Read-sites (campaign.py): budget.* —
    _over_budget; gap_followup.* — _gap_followup_cfg; trunk_branch + milestone_isolation.*
    — _ensure_milestone_context / _needs_milestone_merge_gate / _execute_milestone_merge.

    Values are NORMALIZED to the resolved form (defaults filled, legacy isolation_strategy
    folded into default_strategy) so absent-vs-explicit-default does not churn the hash and
    so the live re-read (which resolves the same way) compares equal byte-for-byte.

    Additivity: this is ONLY ever inside H/scope_envelope, which signoff_status reads ONLY
    when f1_required(plan) — a legacy non-F1 plan never reaches this (byte-identical)."""
    budget = plan.get("budget") or {}
    iso = plan.get("milestone_isolation") or {}
    legacy = plan.get("isolation_strategy")
    default_iso = iso.get("default_strategy")
    if not default_iso and legacy == "worktree":
        default_iso = li.STRATEGY_NEW_WORKTREE
    elif not default_iso and legacy == "shared":
        default_iso = li.STRATEGY_CURRENT_BRANCH
    gf = plan.get("gap_followup") or {}
    return {
        "budget": {
            "max_subsprints": budget.get("max_subsprints"),
            "max_total_spawns": budget.get("max_total_spawns"),
            "max_wall_clock_minutes": budget.get("max_wall_clock_minutes"),
        },
        "gap_followup": {
            "max_subsprints": gf.get("max_subsprints",
                                     GAP_FOLLOWUP_DEFAULT_MAX_SUBSPRINTS),
            "max_no_progress_rounds": gf.get("max_no_progress_rounds",
                                             GAP_FOLLOWUP_DEFAULT_MAX_NO_PROGRESS),
        },
        "trunk_branch": plan.get("trunk_branch") or "main",
        "milestone_isolation": {
            "default_strategy": default_iso or li.STRATEGY_CURRENT_BRANCH,
            "branch_name_template": iso.get("branch_name_template")
                or "milestone/{campaign_id}/{milestone_id}",
            "worktree_root": iso.get("worktree_root"),
            "merge_prompt_at_close": iso.get("merge_prompt_at_close", True),
            "cleanup_policy": iso.get("cleanup_policy") or li.CLEANUP_KEEP,
        },
    }


def compute_scope_envelope(plan: dict, charter: Optional[dict],
                           ledger: Optional[dict] = None) -> dict:
    """The STORED signed scope-envelope snapshot {goal, milestones:[…], authority}
    (design §3.3.1, G4: stored not just hashed, so prior signed coverage is
    reconstructable for stale-signoff rendering). Milestones are in the plan's DECLARED
    order (reordering is a scope change → a new hash → stale). Track-2 T2-B: the resolved
    top-level `authority` block (budget/gap_followup/trunk_branch/milestone_isolation) is
    stored alongside so signoff_snapshot_authentic reconstructs the SAME H from the stored
    envelope (lockstep). OW-M3 B1: `ledger` (the LIVE requirement ledger) binds each
    covering milestone's covered_req_surfaces basis; absent ⇒ pre-OW-M3-identical."""
    ledger = _effective_surfaces_ledger(plan, ledger)
    return {
        "goal": plan.get("goal"),
        "milestones": [_envelope_milestone(charter, m, ledger)
                       for m in (plan.get("milestones") or [])],
        "authority": _resolve_plan_authority(plan),
    }


def _signed_scope_H(plan: dict, charter: Optional[dict], *,
                    charter_ref: Optional[str], charter_hash: str,
                    ledger: Optional[dict] = None) -> dict:
    """The EXACT hash-input object H (design §3.3.1): goal/charter_hash live INSIDE H
    (not concatenated alongside the envelope), so the input is unambiguous. Track-2 T2-B:
    H carries the resolved top-level `authority` block, so every authority-bearing plan
    field (budget/gap_followup/trunk_branch/milestone_isolation/per-milestone
    isolation_strategy) is inside the SINGLE signed hash. OW-M3 B1: each covering
    milestone's covered_req_surfaces (from the LIVE `ledger`) is inside H too, so a
    post-sign surface flip flips the hash."""
    return {
        "version": "v1",
        "campaign_id": plan.get("campaign_id"),
        "goal": plan.get("goal"),
        "charter_ref": charter_ref,
        "charter_hash": charter_hash,
        "milestones": [_envelope_milestone(charter, m, ledger)
                       for m in (plan.get("milestones") or [])],
        "authority": _resolve_plan_authority(plan),
    }


def compute_signed_scope_hash(plan: dict, charter: Optional[dict], *,
                              charter_ref: Optional[str] = None,
                              charter_hash: Optional[str] = None,
                              ledger: Optional[dict] = None) -> str:
    """signed_scope_hash = sha256(canonical_json(H)) per design §3.3.1. charter_hash
    defaults to the canonical hash of `charter` (the LIVE charter when the runner
    recomputes; the sign-time charter when stamping). OW-M3 B1: pass the LIVE `ledger`
    so covered_req_surfaces enters H identically at sign time and at freshness recompute
    (design §5.1 N1); absent ⇒ pre-OW-M3-identical."""
    ch = charter or {}
    if charter_hash is None:
        charter_hash = _canonical_sha256(ch)
    ledger = _effective_surfaces_ledger(plan, ledger)
    H = _signed_scope_H(plan, ch, charter_ref=charter_ref, charter_hash=charter_hash,
                        ledger=ledger)
    return hashlib.sha256(_canonical_json(H).encode("utf-8")).hexdigest()


def stamp_signoff(plan: dict, charter: Optional[dict], *, signer: str = "human",
                  signed_at: str = "", charter_ref: str = "",
                  ledger: Optional[dict] = None) -> dict:
    """Return a DEEP COPY of `plan` with a freshly-stamped `signoff` block — the F1
    "sign" action (the human can't hand-compute the hash). Used by the --sign-plan CLI
    and tests. Re-running it after a scope edit RE-STAMPS the snapshot (a new signature
    epoch). OW-M3 B1: the LIVE `ledger` binds covered_req_surfaces into both the stored
    envelope and the signed hash, so a later surface flip is detected as drift."""
    out = copy.deepcopy(plan)
    ch = charter or {}
    charter_hash = _canonical_sha256(ch)
    out["signoff"] = {
        "signed_by_human": True,
        "signer": signer,
        "signed_at": signed_at,
        "charter_ref": charter_ref,
        "charter_hash": charter_hash,
        "scope_envelope": compute_scope_envelope(out, ch, ledger),
        "signed_scope_hash": compute_signed_scope_hash(
            out, ch, charter_ref=charter_ref, charter_hash=charter_hash, ledger=ledger),
    }
    return out


def mandatory_e2e_violations(plan: Optional[dict], charter: Optional[dict],
                             ledger: Optional[dict]) -> list:
    """OW-M3 sign-off gate (design §3.1–§3.2): the list of milestones whose declared
    coverage would accept a user-facing requirement on non-browser-E2E evidence, or that
    reference a requirement the ledger does not classify. Empty ⇒ the plan may be signed
    / run.

    DORMANT (returns []) when no requirement ledger is wired — the mandate is inert until
    the OW-2 input contract exists (byte-identical to pre-OW-M3). For each milestone
    DECLARING a non-empty covers_req_ids:
      • 'unclassified' — a covered rid is absent from the ledger, carries no VALID
        `surface` (∈ {user_facing, non_user_facing} — an out-of-enum value like 'banana'
        is NOT trusted as non-user-facing), or is AMBIGUOUS (duplicated in the ledger with
        conflicting classifications). (D2: refuse; conservative-default rejected.) Reported
        alone (the milestone's user-facing-ness is unknowable until every covered rid is
        unambiguously classified).
      • 'downgrade'    — the milestone is user-facing (ANY covered rid.surface ==
        'user_facing') yet its RESOLVED functional acceptance mode != 'browser_e2e'.
    A milestone with an ABSENT covers_req_ids field never trips this (dormant; N2)."""
    if not ledger:
        return []
    reqs = {r.get("id"): r for r in (ledger.get("requirements") or [])
            if isinstance(r, dict)}
    dups = set(duplicate_requirement_ids(ledger))
    out = []
    for m in (plan or {}).get("milestones") or []:
        covered = list(m.get("covers_req_ids") or [])
        if not covered:
            continue
        # Refuse a covered rid that is absent, out-of-enum, or ambiguously duplicated —
        # any of these means the surface basis is not trustworthy for this milestone.
        unknown = [rid for rid in covered
                   if rid in dups or rid not in reqs
                   or reqs[rid].get("surface") not in _VALID_SURFACES]
        if unknown:
            out.append({"milestone_id": m.get("id"), "kind": "unclassified",
                        "req_ids": unknown})
            continue
        user_facing = [rid for rid in covered
                       if reqs[rid].get("surface") == "user_facing"]
        if user_facing:
            mode, source = resolve_functional_acceptance(
                charter, m.get("functional_acceptance"))
            if mode != "browser_e2e":
                out.append({"milestone_id": m.get("id"), "kind": "downgrade",
                            "req_ids": user_facing, "resolved_mode": mode,
                            "resolved_source": source})
    return out


def render_mandatory_e2e_refusal(violations: list, *, action: str) -> str:
    """The actionable refusal message (design §3.2, §8 friction guard): for every
    violation, the two — and ONLY two — resolutions, so adopters never bypass via the
    no-ledger path. `action` is a short verb phrase for the header (e.g. 'refusing to
    sign the plan')."""
    lines = [f"OW-M3 mandatory browser-E2E acceptance — {action}:"]
    for v in violations:
        mid = v.get("milestone_id")
        rids = ", ".join(v.get("req_ids") or [])
        if v.get("kind") == "unclassified":
            lines.append(
                f"  - milestone {mid!r}: covers requirement id(s) [{rids}] that are "
                f"absent from the requirement ledger, have no valid `surface` "
                f"classification (∈ user_facing | non_user_facing), or are ambiguously "
                f"classified (duplicate ledger id). Ensure exactly one ledger entry with a "
                f"valid surface per id, then re-sign.")
        else:  # downgrade
            mode = v.get("resolved_mode")
            lines.append(
                f"  - milestone {mid!r}: covers user_facing requirement(s) [{rids}] but "
                f"its resolved functional acceptance is {mode!r} (must be 'browser_e2e'). "
                f"Resolve by EITHER (1) set this milestone's functional_acceptance: "
                f"\"browser_e2e\"; OR (2) (Customer) reclassify the requirement's surface "
                f"to 'non_user_facing' in the ledger and re-sign.")
    return "\n".join(lines)


def f1_required(plan: Optional[dict]) -> bool:
    """Whether the F1 integrity check is ACTIVE for this plan. F1 is OPT-IN — triggered
    by a `signoff` block OR any milestone DECLARING a covers_req_ids field. Both are NEW
    fields, so a legacy plan never triggers it (additivity: byte-identical to today).
    Keyed on field PRESENCE (not truthiness) so an explicit covers_req_ids:[] — a
    deliberate "this milestone covers nothing" — still opts the plan into integrity
    (Codex R-P2a NB-1: a non-empty test would silently downgrade an empty-array plan)."""
    plan = plan or {}
    if isinstance(plan.get("signoff"), dict):
        return True
    return any(isinstance(m, dict) and "covers_req_ids" in m
               for m in (plan.get("milestones") or []))


def signoff_snapshot_authentic(plan: Optional[dict]) -> bool:
    """Whether the STORED signoff snapshot is SELF-CONSISTENT with its own
    signed_scope_hash — i.e. recomputing the hash from the stored scope_envelope (NOT
    the live plan) reproduces the stored signed_scope_hash. This guards against a
    TAMPERED snapshot (scope_envelope edited while signed_scope_hash is left untouched):
    scope_report must NOT trust an unverified snapshot for prior-coverage reconstruction
    (Codex R-P2a blocking #2 / design §3.3.1 G4). Returns False when there is no complete
    snapshot to verify (caller then fails closed). The stored scope_envelope.milestones
    are already in _envelope_milestone shape (compute_scope_envelope), so they slot
    straight into H; canonical JSON sorts keys, so storage order is irrelevant."""
    plan = plan or {}
    signoff = plan.get("signoff")
    if not isinstance(signoff, dict):
        return False
    snapshot = signoff.get("scope_envelope")
    stored = signoff.get("signed_scope_hash")
    if not isinstance(snapshot, dict) or not stored:
        return False
    H = {
        "version": "v1",
        "campaign_id": plan.get("campaign_id"),
        "goal": snapshot.get("goal"),
        "charter_ref": signoff.get("charter_ref"),
        "charter_hash": signoff.get("charter_hash"),
        "milestones": list(snapshot.get("milestones") or []),
        # Track-2 T2-B lockstep: reconstruct the SAME H from the STORED envelope's
        # authority block (compute_scope_envelope stores it). A snapshot from before
        # T2-B has no `authority` key — its stored signed_scope_hash was computed
        # without one, so reconstructing without it reproduces that hash and the older
        # snapshot still verifies (the live signoff_status independently flips it to
        # 'stale' once authority enters H, forcing the one-time re-sign — TD5).
        **({"authority": snapshot["authority"]}
           if isinstance(snapshot.get("authority"), dict) else {}),
    }
    recomputed = hashlib.sha256(_canonical_json(H).encode("utf-8")).hexdigest()
    return recomputed == stored


def signoff_status(plan: Optional[dict], charter: Optional[dict] = None,
                   ledger: Optional[dict] = None) -> str:
    """campaign_plan_signoff status: 'signed' | 'stale' | 'pre_f1' | 'unsigned'
    (design §3.3.1). When F1 is inactive this is the legacy bare-`signed_by_human`
    check. When active: a `signoff` block with signed_by_human:true is 'signed' ⟺ its
    stored signed_scope_hash == the live recomputed hash, else 'stale'; a bare top-level
    signed_by_human with no signoff block is 'pre_f1' (one re-sign); else 'unsigned'.
    Legacy precedence: when a signoff block exists it is authoritative and the bare flag
    is ignored. OW-M3 B1: pass the LIVE `ledger` so the recompute binds the SAME
    covered_req_surfaces the sign-time hash did — a post-sign surface flip ⇒ 'stale'
    (design §5.1 N1). A ledger MUST be supplied wherever it was at sign time, else the
    field's presence diverges and the plan reads falsely 'stale'."""
    plan = plan or {}
    if not f1_required(plan):
        return "signed" if plan.get("signed_by_human") else "unsigned"
    signoff = plan.get("signoff")
    if isinstance(signoff, dict) and signoff.get("signed_by_human") is True:
        live = compute_signed_scope_hash(
            plan, charter or {}, charter_ref=signoff.get("charter_ref"), ledger=ledger)
        return "signed" if signoff.get("signed_scope_hash") == live else "stale"
    if plan.get("signed_by_human") is True:
        return "pre_f1"
    return "unsigned"


# --------------------------------------------------------------------------- #
# Track-2 TD6 — the engine-authored deliver_followup re-stamp, reconstructed
# deterministically from CANONICAL SIGNED INPUTS (the plan-file signed envelope +
# the append-only authorized deltas pinned in campaign state). These are module-level
# + PURE so EVERY freshness consumer — the Campaign runner AND scope_report (external
# requirement-coverage reporting) — agrees on ONE epoch (no divergence; Codex R2 B2).
# --------------------------------------------------------------------------- #
def _reconstruct_authorized_envelope(e0: dict, deltas: list) -> Optional[dict]:
    """The authorized epoch envelope E* = the ORIGINAL signed envelope (e0, from the plan
    file — never written back) + each append-only authorized insertion (subsprint_id at
    at_index in the named milestone's subsprint_sequence), applied in chronological order.
    None if any delta does not apply cleanly (caller leaves the plan stale → fail-closed)."""
    env = copy.deepcopy(e0)
    by_id = {m.get("id"): m for m in (env.get("milestones") or [])}
    for d in (deltas or []):
        m = by_id.get(d.get("milestone_id"))
        sid, idx = d.get("subsprint_id"), d.get("at_index")
        if m is None or sid is None or not isinstance(idx, int):
            return None
        seq = list(m.get("subsprint_sequence") or [])
        if idx < 0 or idx > len(seq):
            return None
        seq.insert(idx, sid)
        m["subsprint_sequence"] = seq
    return env


def _hash_from_envelope(plan: dict, charter: Optional[dict],
                        signoff: dict, envelope: dict) -> str:
    """sha256(canonical_json(H)) for a RECONSTRUCTED scope-envelope — H is built from the
    envelope (goal/milestones/authority) + the plan/charter wrapper IDENTICALLY to
    compute_signed_scope_hash, using the LIVE charter_hash (so it matches a hash the runner
    pinned via _live_signed_scope_hash)."""
    H = {"version": "v1", "campaign_id": plan.get("campaign_id"),
         "goal": envelope.get("goal"),
         "charter_ref": signoff.get("charter_ref"),
         "charter_hash": _canonical_sha256(charter or {}),
         "milestones": list(envelope.get("milestones") or [])}
    if isinstance(envelope.get("authority"), dict):
        H["authority"] = envelope["authority"]
    return hashlib.sha256(_canonical_json(H).encode("utf-8")).hexdigest()


def apply_engine_restamp_to_plan(plan: Optional[dict], charter: Optional[dict],
                                 engine_restamp: Optional[dict],
                                 ledger: Optional[dict] = None) -> dict:
    """Return `plan` with its signoff aligned to the authorized engine epoch (E* = the
    plan-file signed envelope + the append-only deltas pinned in `engine_restamp`) IFF that
    reconstruction reproduces the pinned signed_scope_hash; otherwise `plan` unchanged. PURE
    — never mutates the input (returns a shallow copy with a re-stamped signoff when it
    applies). This is the SINGLE source of TD6 epoch truth shared by the Campaign runner and
    scope_report, so the runner and external reporting never diverge (Codex R2 B2).

    A plan that already reads 'signed' on its own (a human re-sign of the grown plan, or an
    F1-inactive plan) is returned unchanged — the engine epoch is only consulted to RESCUE a
    'stale' plan whose sole drift is the authorized follow-up insertion(s)."""
    plan = plan or {}
    if not f1_required(plan):
        return plan
    if signoff_status(plan, charter, ledger) == "signed":
        return plan   # genuinely / human re-signed → the engine epoch is moot
    restamp = engine_restamp or {}
    pinned = restamp.get("signed_scope_hash")
    deltas = restamp.get("deltas") or []
    if not pinned or not deltas:
        return plan
    signoff = plan.get("signoff")
    if not isinstance(signoff, dict) or not signoff_snapshot_authentic(plan):
        return plan   # no/again-untrustworthy original signed envelope → stays stale
    estar = _reconstruct_authorized_envelope(signoff.get("scope_envelope") or {}, deltas)
    if estar is None:
        return plan
    if _hash_from_envelope(plan, charter, signoff, estar) != pinned:
        return plan   # E* does not reproduce the pinned epoch (tamper / further edit) → stale
    out = dict(plan)
    out_signoff = dict(signoff)
    out_signoff["scope_envelope"] = estar
    out_signoff["signed_scope_hash"] = pinned   # signed_by_human/signer UNTOUCHED
    out["signoff"] = out_signoff
    return out


def derive_milestone_context(charter: dict, milestone_id: str,
                             subsprint_sequence: List[str], *,
                             campaign_id: Optional[str],
                             plan_fingerprint: Optional[str],
                             functional_acceptance: Optional[str] = None):
    """Project `charter` onto ONE milestone. Returns (derived_charter, provenance).

    `derived_charter` is a DEEP COPY whose autonomy.approved_scope.subsprint_sequence
    is THIS milestone's sequence, so the Driver anchors terminality — and therefore
    its milestone-close Acceptance gate — to this milestone's FINAL sub-sprint
    (driver._milestone_complete), not the campaign's last sub-sprint.

    P-C: the per-milestone `functional_acceptance` (from the campaign plan's milestone)
    is projected into the derived charter's tooling.acceptance.functional.mode so ONLY
    the milestones declaring it run the browser-E2E evidence gate. PRECEDENCE (Codex
    round-2 MAJOR-2, no schema default): an EXPLICIT milestone value (incl. 'static')
    OVERRIDES; absent INHERITS the charter-level functional.mode; else 'static'. The
    resolved {mode, source} is recorded in the provenance sidecar.

    `provenance` is returned SEPARATELY (recorded as a sidecar by the caller): it
    preserves the source hashes (charter + signed plan) so the derivation is
    reproducible/auditable, and is explicitly NOT a new Customer signature."""
    derived = copy.deepcopy(charter)
    scope = derived.setdefault("autonomy", {}).setdefault("approved_scope", {})
    scope["subsprint_sequence"] = list(subsprint_sequence)

    # Same resolution the F1 signed envelope records (design §3.3.1 / §3.7).
    fmode, fsource = resolve_functional_acceptance(charter, functional_acceptance)
    # Materialize the resolved mode onto the derived charter so the Driver's
    # _acceptance_class() reads it per milestone. Only touch the functional block when a
    # decision is needed (browser_e2e engages the gate; an explicit static neutralizes a
    # charter-level browser_e2e for THIS milestone).
    if fmode == "browser_e2e":
        derived.setdefault("tooling", {}).setdefault("acceptance", {}) \
            .setdefault("functional", {})["mode"] = "browser_e2e"
    else:
        fnl = (((derived.get("tooling") or {}).get("acceptance") or {})
               .get("functional"))
        if isinstance(fnl, dict):
            fnl["mode"] = "static"

    provenance = {
        "kind": "per_milestone_execution_context",
        "campaign_id": campaign_id,
        "milestone_id": milestone_id,
        "subsprint_sequence": list(subsprint_sequence),
        "functional_acceptance": {"mode": fmode, "source": fsource},
        "derived_from": {
            "charter_sha256": _canonical_sha256(charter),
            "campaign_plan_sha256": plan_fingerprint,
        },
        # A deterministic orchestrator projection — NOT a re-signed charter. The
        # Customer signature lives on the campaign plan (plan.signed_by_human), one
        # tier up; deriving an execution context grants no new signing authority.
        "customer_signed": False,
    }
    return derived, provenance


def make_run_unit(charter: dict, units_dir: str, campaign_id: str, *,
                  clock: Callable[[], str], plan: Optional[dict] = None,
                  run_loop_fn: Optional[Callable] = None,
                  ledger_path: Optional[str] = None,
                  **run_loop_kwargs) -> RunUnit:
    """Build a PRODUCTION run_unit that drives ONE sub-sprint via
    `scheduling.run_loop` and returns the campaign summary
    `{final_state, spawn_count, loop_id, pause_reason, checkpoint_path}`.

    Each unit gets its OWN run_dir (`units_dir/<loop_id>`, keyed by
    `(campaign, milestone, subsprint)` so repeated sub-sprint ids across milestones
    don't collide). A `GateHardFail` — which `run_loop` RAISES — is converted into a
    paused unit so the campaign HALTS rather than crashing (Codex P-B seam note);
    `BudgetExceeded` is a `GateHardFail` subclass so it is caught too. For any
    non-advance/done state, `pause_reason` is the latest checkpoint's id.

    PER-MILESTONE Acceptance (the multi-milestone fix): the campaign passes THIS
    milestone's LIVE sub-sprint sequence (`subsprint_sequence=`) on every dispatch;
    when present, the unit runs through a per-milestone execution context DERIVED from
    the canonical charter + that sequence (see `derive_milestone_context`) — its
    approved_scope.subsprint_sequence is the milestone's sequence, so the Driver fires
    its milestone-close Acceptance gate at every milestone's FINAL sub-sprint, not only
    the campaign's last (design §5). The sequence is taken LIVE from the campaign (NOT
    snapshotted here), so a governed mid-campaign edit — a `deliver_followup` insertion
    into the milestone's sequence — is reflected at dispatch (Codex P-B review #3). The
    derived context is recorded with its source hashes (a per-unit
    `derived-context.json` sidecar) and is NEVER a re-signed charter. The campaign's own
    pause-on-non-advance loop then withholds the next milestone until this milestone's
    Acceptance/human gate is resolved — the derivation only ensures the gate EXISTS.

    `plan` (optional) supplies the signed-campaign-plan hash for that provenance record;
    its `campaign_id` must match. A MULTI-MILESTONE campaign MUST be driven with the
    campaign passing `subsprint_sequence` (which `run_campaign` does) — otherwise every
    milestone shares one charter and only the campaign's LAST sub-sprint is gated (the
    very bug this fixes; Codex P-B review #4). Absent `subsprint_sequence` ⇒ the shared
    charter is used as-is (single-charter usage, byte-identical to pre-fix)."""
    if run_loop_fn is None:
        import run_loop as _rl  # engine-kit/scheduling/run_loop.py (lazy — heavy deps)
        run_loop_fn = _rl.run_loop
    import driver as _drv       # GateHardFail (+ BudgetExceeded subclass)
    gate_hard_fail = _drv.GateHardFail

    # FAIL-CLOSED (Codex P-B review #1): the per-milestone projection anchors the
    # Acceptance gate via a SUPPLIED approved_scope.subsprint_sequence. That is sound in
    # the campaign's delivery_only mode (the Driver runs exactly the dispatched
    # sub-sprint), but full_chain_guided's bootstrap RESETS the run to seq[0]
    # (driver._drive_guided_prestates), which would mis-anchor terminality and could
    # skip a milestone's gate. So (a) reject ANY explicit non-delivery_only loop_mode
    # here, and (b) PIN loop_mode=delivery_only on the derived dispatch below. Together
    # these close the hole the literal-only check left open (Codex round-2): a falsy
    # explicit loop_mode would otherwise let the Driver fall back to a guided
    # `charter.autonomy.loop_mode`. (full_chain_guided per-milestone decompose is
    # deferred — design §6.)
    requested_mode = run_loop_kwargs.get("loop_mode")
    if requested_mode and str(requested_mode) != _drv.LOOP_MODE_DELIVERY_ONLY:
        raise ValueError(
            "per-milestone Acceptance derivation supports delivery_only only; refusing "
            f"loop_mode={requested_mode!r} (full_chain_guided per-milestone decompose "
            "is deferred — design §6)")

    # The signed-plan provenance reference (optional). The correctness-critical
    # per-milestone SEQUENCE arrives LIVE from the campaign per dispatch (below), so
    # this hash is only a reference to the signed plan, never the source of the
    # sequence — a governed mid-campaign sequence edit can't desync it.
    plan_fingerprint = _canonical_sha256(plan) if plan is not None else None
    if plan is not None and plan.get("campaign_id") not in (None, campaign_id):
        raise ValueError(
            f"plan campaign_id {plan.get('campaign_id')!r} != campaign_id "
            f"{campaign_id!r} — refusing to derive contexts from a mismatched plan")

    def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                 resume=False, functional_acceptance=None, repo_dir=None,
                 covered_req_ids=None, gap_followup_spec=None):
        # Validate id components BEFORE building any path (fail-closed; never makedirs
        # an unsafe path), then build a COLLISION-FREE, bounded loop_id by hashing the
        # (campaign, milestone, subsprint) tuple — a raw '-' join is ambiguous when ids
        # contain '-' and may exceed the Driver's loop_id length cap (Codex inc-2 #5).
        # The readable (milestone, subsprint) ↔ loop_id mapping lives in campaign-state.
        for part in (milestone_id, subsprint_id):
            if part is not None and not _SAFE_CAMPAIGN_ID_RE.match(str(part)):
                raise ValueError(
                    f"unsafe id component {part!r} for the unit run_dir/loop_id")
        digest = hashlib.sha256(
            f"{campaign_id}\x00{milestone_id}\x00{subsprint_id}".encode()).hexdigest()
        loop_id = "u" + digest[:24]
        unit_run_dir = os.path.join(units_dir, loop_id)
        os.makedirs(unit_run_dir, exist_ok=True)

        # Project the canonical charter onto THIS milestone using the campaign's LIVE
        # sequence so the Driver fires its Acceptance gate at this milestone's terminal
        # sub-sprint (design §5). Fail-closed: the dispatched sub-sprint MUST belong to
        # the sequence the gate is anchored to — else terminality would be computed
        # against a sequence this unit isn't part of.
        unit_charter = charter
        call_kwargs = run_loop_kwargs
        if subsprint_sequence:
            seq = list(subsprint_sequence)
            if subsprint_id not in seq:
                raise ValueError(
                    f"sub-sprint {subsprint_id!r} not in milestone {milestone_id!r}'s "
                    f"sequence {seq} — cannot anchor its Acceptance gate (fail-closed)")
            unit_charter, provenance = derive_milestone_context(
                charter, milestone_id, seq,
                campaign_id=campaign_id, plan_fingerprint=plan_fingerprint,
                functional_acceptance=functional_acceptance)
            with open(os.path.join(unit_run_dir, "derived-context.json"),
                      "w", encoding="utf-8") as fh:
                json.dump(provenance, fh, indent=2, sort_keys=True)
            # Track 2 Phase 2-γ / §1.7-F clause 1: when the campaign auto-dispatches a
            # GENERATED remediation sub-sprint it passes the in-envelope covered_req_ids it
            # already PROVED ⊆ (F1 snapshot ∩ the milestone's signed covers) — record it as a
            # Deliver-readable sidecar so Deliver addresses exactly the in-envelope gap (NEVER
            # scope expansion). Additive: absent on every normal dispatch.
            if covered_req_ids:
                with open(os.path.join(unit_run_dir, "gap-followup-stanza.json"),
                          "w", encoding="utf-8") as fh:
                    json.dump({"sprint_id": subsprint_id, "milestone_id": milestone_id,
                               "covered_req_ids": list(covered_req_ids)},
                              fh, indent=2, sort_keys=True)
            # Codex R1 B4: BIND the in-envelope covered_req_ids into the EXECUTABLE work
            # contract — render the generated spec as the Driver-resolved compact Dev prompt
            # (compact/<id>-dev-prompt.md under the work repo), so on a LIVE run Deliver
            # builds exactly the signed-but-undelivered requirements instead of halting on a
            # missing spec. Best-effort: a write failure leaves the gapfix to the Driver's
            # own missing-spec refinement HALT (still fail-closed, never a bare run). Needs a
            # repo (delivery dir); absent ⇒ offline/mock, where strict-prompt resolution is
            # off and the contract is moot.
            _gf_repo = repo_dir or run_loop_kwargs.get("repo_dir")
            if gap_followup_spec and _gf_repo:
                try:
                    _cdir = os.path.join(_gf_repo, "compact")
                    os.makedirs(_cdir, exist_ok=True)
                    with open(os.path.join(_cdir, f"{subsprint_id}-dev-prompt.md"),
                              "w", encoding="utf-8") as fh:
                        fh.write(render_gapfix_dev_prompt(
                            gap_followup_spec, subsprint_id, milestone_id))
                except OSError:
                    pass
            # PIN delivery_only on the derived dispatch: the Driver ctor's loop_mode
            # arg WINS over charter.autonomy.loop_mode (driver.py ~621), so this
            # neutralizes any full_chain_guided the SOURCE charter carries even when
            # the caller passed a falsy loop_mode — the round-2 hole. The construction
            # guard already rejected an explicit truthy non-delivery_only mode.
            call_kwargs = {**run_loop_kwargs,
                           "loop_mode": _drv.LOOP_MODE_DELIVERY_ONLY}

        # Δ-19 Phase 2-β: write the per-unit requirement-context sidecar (the gap-report
        # SOURCE FACTS) so the Driver's milestone-close Acceptance can emit the ADVISORY
        # gap_report AND bind these verdict-affecting inputs into acceptance_input_hash
        # (LOAD-CLOSURE). Carries the signed plan (with its F1 scope_envelope snapshot), the
        # requirement ledger, the CANONICAL charter (for the live F1 signed-scope-hash
        # recompute — the Driver only holds the per-milestone DERIVED charter), and a MINIMAL
        # PRE-DISPATCH SNAPSHOT of campaign-state (status + cursor + milestone_outcomes; the
        # only gap-relevant fields compute_requirement_coverage reads — so the bound hash never
        # churns on volatile spend counters). This is the state AS OF dispatch, NOT post-close:
        # the advisory gap_report (Phase 2-β) is computed from this snapshot, which is hash-safe
        # and acceptable for an ADVISORY artifact. NOTE for Phase 2-γ: once the gap DRIVES work
        # (auto-followup), it MUST reflect the just-closed milestone's outcome — re-snapshot the
        # state post-close (and re-bind into acceptance_input_hash) there, do not reuse this
        # pre-dispatch snapshot. Written ONLY when a requirement ledger is wired; absent ⇒ the
        # gap_report stays dormant (byte-identical to today). Best-effort: a sidecar failure
        # never breaks a dispatch (the gap_report stays dormant), but it IS recorded (below) so a
        # wired-ledger failure is observable rather than silent (Codex R-P2b NB-1).
        if plan is not None and ledger_path and os.path.isfile(ledger_path):
            try:
                with open(ledger_path, encoding="utf-8") as fh:
                    _ledger = json.load(fh)
                _state_proj = None
                _state_file = os.path.join(
                    os.path.dirname(os.path.abspath(units_dir)), "campaign-state.json")
                if os.path.isfile(_state_file):
                    with open(_state_file, encoding="utf-8") as fh:
                        _st = json.load(fh)
                    _state_proj = {"status": _st.get("status"),
                                   "cursor": _st.get("cursor") or {},
                                   "milestone_outcomes": _st.get("milestone_outcomes") or []}
                with open(os.path.join(unit_run_dir, "requirement-context.json"),
                          "w", encoding="utf-8") as fh:
                    json.dump({"plan": plan, "ledger": _ledger,
                               "campaign_state": _state_proj, "charter": charter},
                              fh, indent=2, sort_keys=True)
            except (OSError, ValueError) as _exc:
                # Best-effort, but NON-SILENT: a wired ledger that fails to produce the sidecar
                # leaves the gap_report dormant — record it so the failure is observable.
                try:
                    with open(os.path.join(unit_run_dir, "requirement-context.error"),
                              "w", encoding="utf-8") as fh:
                        fh.write(f"requirement-context sidecar not written (gap_report dormant "
                                 f"for this unit): {type(_exc).__name__}: {_exc}\n")
                except OSError:
                    pass

        cps_dir = os.path.join(unit_run_dir, "docs", "checkpoints")
        effective_repo = repo_dir or run_loop_kwargs.get("repo_dir")
        # §1.7-F gap-followup crash-recovery (Codex R2 B2 / R3 B2): the campaign re-enters an
        # in-flight gapfix with resume=True, but a gapfix that crashed BEFORE its first Driver
        # save has no state.json to resume — run it FRESH. Scoped to a gap-followup dispatch
        # (it alone carries covered_req_ids) so the inner loop's resume semantics are
        # UNCHANGED, and a PRECISE state.json probe (the Driver persists to
        # <run_dir>/.orchestrator/state.json) — NOT a broad `except FileNotFoundError` — so a
        # FileNotFoundError from INSIDE a resumed Driver (missing schema / corrupt dependency)
        # still PROPAGATES fail-closed, never silently re-runs (which could duplicate side
        # effects).
        effective_resume = resume
        if (resume and covered_req_ids and not os.path.isfile(
                os.path.join(unit_run_dir, ".orchestrator", "state.json"))):
            effective_resume = False
        try:
            summary = run_loop_fn(unit_charter, run_dir=unit_run_dir, loop_id=loop_id,
                                  subsprint_id=subsprint_id, clock=clock,
                                  resume=effective_resume, repo_dir=effective_repo,
                                  **call_kwargs)
        except gate_hard_fail as exc:
            cid, cpath = latest_checkpoint(cps_dir)
            return {"final_state": "halted", "spawn_count": 0, "loop_id": loop_id,
                    "pause_reason": cid or "gate_hard_fail",
                    "checkpoint_path": getattr(exc, "checkpoint_path", "") or cpath}
        final_state = summary.get("final_state")
        pause_reason, checkpoint_path = None, None
        if final_state not in ("advance", "done"):
            cid, checkpoint_path = latest_checkpoint(cps_dir)
            pause_reason = cid or final_state
        return {"final_state": final_state,
                "spawn_count": int(summary.get("spawn_count") or 0),
                "loop_id": loop_id, "pause_reason": pause_reason,
                "checkpoint_path": checkpoint_path}
    return run_unit
