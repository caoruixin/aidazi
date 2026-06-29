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
    milestone_context: Optional[dict] = None   # active milestone git isolation (campaign-tier ingress)
    pending_milestone_advance: bool = False    # milestone DONE; cursor not advanced (at merge gate)
    # Δ-19 F3 (design §3.5.1): one TERMINAL close outcome per milestone, stamped at
    # close so scope_report can DERIVE delivery_status deterministically (delivered vs
    # waived-with-reason) — never inferred from cursor position. Additive; absent ⇒
    # today's behavior (a legacy state simply has no outcomes to project).
    milestone_outcomes: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
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
            milestone_context=d.get("milestone_context"),
            pending_milestone_advance=bool(d.get("pending_milestone_advance", False)),
            milestone_outcomes=list(d.get("milestone_outcomes") or []))


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
        if ledger_path and os.path.isfile(ledger_path):
            try:
                with open(ledger_path, encoding="utf-8") as fh:
                    led = json.load(fh)
            except OSError as exc:
                raise ValueError(f"campaign requirement ledger unreadable: {exc}")
            _validate_or_raise(led, "requirement-ledger.schema.json", "ledger")
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
            # The done/exhausted boundary. A PAUSED campaign is paused INSIDE a
            # milestone, so it can never sit here; the runner resets subsprint_index
            # to 0 before the cursor reaches this boundary.
            if status == STATUS_PAUSED:
                raise ValueError(
                    "campaign state is paused but the cursor is at the backlog end "
                    f"({n_ms}) — a paused campaign pauses inside a milestone "
                    "(fail-closed)")
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
        return signoff_status(self.plan, self.charter)

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
            return "proceed" if status == "signed" else self._repause(reason, status)
        if reason == "milestone_decompose_required":
            ms = self.milestones[self.state.milestone_index]
            return ("proceed" if ms.get("subsprint_sequence")
                    else self._repause(reason, "still_undecomposed"))
        if reason == "milestone_merge":
            decision = (decision_resolver(reason, self.state.pause_checkpoint)
                        if decision_resolver is not None else None)
            if not decision:
                return self._repause(reason, "decision_pending")
            choice = decision.get("choice")
            if choice == "abort":
                self._end("milestone_merge_aborted")
                return "ended"
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
            # Mechanism A: the Driver re-enters the paused state on the next dispatch.
            self._pending_driver_resume = True
            self._audit("campaign_resume_driver", {"pause_reason": reason})
            return "proceed"

        # Mechanism B + campaign-level dispatch.
        if reason == "campaign_budget_exhausted":
            if decision.get("choice") == "raise_cap":
                self.budget = self.plan.get("budget") or {}  # human raised the cap
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
        if resume and self._load():
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

        # backlog exhausted.
        self.state.status = STATUS_DONE
        self._audit("campaign_done",
                    {"subsprints_run": self.state.subsprints_run,
                     "total_spawns": self.state.total_spawns})
        self._save()
        return self.state


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


def _envelope_milestone(charter: Optional[dict], milestone: dict) -> dict:
    """One milestone's RESOLVED scope-envelope entry (design §3.3.1): the scope-bearing
    fields + the RESOLVED acceptance {mode,source} (not the literal, possibly-absent
    functional_acceptance). Absent arrays normalize to [] so absent-vs-empty doesn't
    churn the hash; acceptance_bar is the string or null."""
    mode, source = resolve_functional_acceptance(
        charter, milestone.get("functional_acceptance"))
    return {
        "id": milestone.get("id"),
        "objective": milestone.get("objective"),
        "covers_req_ids": list(milestone.get("covers_req_ids") or []),
        "subsprint_sequence": list(milestone.get("subsprint_sequence") or []),
        "depends_on": list(milestone.get("depends_on") or []),
        "resolved_functional_acceptance": {"mode": mode, "source": source},
        "acceptance_bar": milestone.get("acceptance_bar"),
    }


def compute_scope_envelope(plan: dict, charter: Optional[dict]) -> dict:
    """The STORED signed scope-envelope snapshot {goal, milestones:[…]} (design §3.3.1,
    G4: stored not just hashed, so prior signed coverage is reconstructable for
    stale-signoff rendering). Milestones are in the plan's DECLARED order (reordering
    is a scope change → a new hash → stale)."""
    return {
        "goal": plan.get("goal"),
        "milestones": [_envelope_milestone(charter, m)
                       for m in (plan.get("milestones") or [])],
    }


def _signed_scope_H(plan: dict, charter: Optional[dict], *,
                    charter_ref: Optional[str], charter_hash: str) -> dict:
    """The EXACT hash-input object H (design §3.3.1): goal/charter_hash live INSIDE H
    (not concatenated alongside the envelope), so the input is unambiguous."""
    return {
        "version": "v1",
        "campaign_id": plan.get("campaign_id"),
        "goal": plan.get("goal"),
        "charter_ref": charter_ref,
        "charter_hash": charter_hash,
        "milestones": [_envelope_milestone(charter, m)
                       for m in (plan.get("milestones") or [])],
    }


def compute_signed_scope_hash(plan: dict, charter: Optional[dict], *,
                              charter_ref: Optional[str] = None,
                              charter_hash: Optional[str] = None) -> str:
    """signed_scope_hash = sha256(canonical_json(H)) per design §3.3.1. charter_hash
    defaults to the canonical hash of `charter` (the LIVE charter when the runner
    recomputes; the sign-time charter when stamping)."""
    ch = charter or {}
    if charter_hash is None:
        charter_hash = _canonical_sha256(ch)
    H = _signed_scope_H(plan, ch, charter_ref=charter_ref, charter_hash=charter_hash)
    return hashlib.sha256(_canonical_json(H).encode("utf-8")).hexdigest()


def stamp_signoff(plan: dict, charter: Optional[dict], *, signer: str = "human",
                  signed_at: str = "", charter_ref: str = "") -> dict:
    """Return a DEEP COPY of `plan` with a freshly-stamped `signoff` block — the F1
    "sign" action (the human can't hand-compute the hash). Used by the --sign-plan CLI
    and tests. Re-running it after a scope edit RE-STAMPS the snapshot (a new signature
    epoch)."""
    out = copy.deepcopy(plan)
    ch = charter or {}
    charter_hash = _canonical_sha256(ch)
    out["signoff"] = {
        "signed_by_human": True,
        "signer": signer,
        "signed_at": signed_at,
        "charter_ref": charter_ref,
        "charter_hash": charter_hash,
        "scope_envelope": compute_scope_envelope(out, ch),
        "signed_scope_hash": compute_signed_scope_hash(
            out, ch, charter_ref=charter_ref, charter_hash=charter_hash),
    }
    return out


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
    }
    recomputed = hashlib.sha256(_canonical_json(H).encode("utf-8")).hexdigest()
    return recomputed == stored


def signoff_status(plan: Optional[dict], charter: Optional[dict] = None) -> str:
    """campaign_plan_signoff status: 'signed' | 'stale' | 'pre_f1' | 'unsigned'
    (design §3.3.1). When F1 is inactive this is the legacy bare-`signed_by_human`
    check. When active: a `signoff` block with signed_by_human:true is 'signed' ⟺ its
    stored signed_scope_hash == the live recomputed hash, else 'stale'; a bare top-level
    signed_by_human with no signoff block is 'pre_f1' (one re-sign); else 'unsigned'.
    Legacy precedence: when a signoff block exists it is authoritative and the bare flag
    is ignored."""
    plan = plan or {}
    if not f1_required(plan):
        return "signed" if plan.get("signed_by_human") else "unsigned"
    signoff = plan.get("signoff")
    if isinstance(signoff, dict) and signoff.get("signed_by_human") is True:
        live = compute_signed_scope_hash(
            plan, charter or {}, charter_ref=signoff.get("charter_ref"))
        return "signed" if signoff.get("signed_scope_hash") == live else "stale"
    if plan.get("signed_by_human") is True:
        return "pre_f1"
    return "unsigned"


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
                 resume=False, functional_acceptance=None, repo_dir=None):
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
        try:
            summary = run_loop_fn(unit_charter, run_dir=unit_run_dir, loop_id=loop_id,
                                  subsprint_id=subsprint_id, clock=clock,
                                  resume=resume, repo_dir=effective_repo, **call_kwargs)
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
