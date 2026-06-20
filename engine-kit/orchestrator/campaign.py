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

# A safe campaign_id — SAME discipline as the Driver's loop_id (letters/digits then
# ._- only; no path separators, no leading dot). It is interpolated into the audit
# ledger FILENAME, so it is validated FAIL-CLOSED at construction (Codex P-B impl
# blocking #1; mirrors driver.py _SAFE_LOOP_ID_RE).
_SAFE_CAMPAIGN_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

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
    "acceptance_surface_approve",
    "advisory_acceptance_pass_signoff",
})
# Campaign-level gates the campaign itself emits (also Mechanism B).
CAMPAIGN_CHECKPOINTS: frozenset = frozenset({
    "campaign_plan_signoff",
    "campaign_budget_exhausted",
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
    "review_out_of_scope": {
        "accept_and_advance": ACT_ADVANCE_MILESTONE,
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
}


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
            units=list(d.get("units") or []))


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
# summary dict: {final_state, spawn_count, pause_reason?, loop_id?}. Production
# wires a thin wrapper around scheduling.run_loop (which already returns
# final_state + spawn_count) that also derives pause_reason from the latest
# checkpoint file; tests inject a deterministic fake. This dependency injection
# mirrors the Driver's injected clock / adapters / gate_resolver.
RunUnit = Callable[..., dict]

_ADVANCE_STATES = frozenset({"advance"})
_MILESTONE_DONE_STATES = frozenset({"done"})


class Campaign:
    """Deterministic outer loop over a campaign plan. Pure except for the injected
    `run_unit` (the only non-determinism) + filesystem state/audit."""

    def __init__(self, plan: dict, run_dir: str, run_unit: RunUnit, *,
                 clock: Callable[[], str], audit_dir: Optional[str] = None):
        self.plan = plan
        self.run_dir = run_dir
        self.run_unit = run_unit
        self.clock = clock
        self.campaign_id = plan["campaign_id"]
        if not _SAFE_CAMPAIGN_ID_RE.match(self.campaign_id or ""):
            raise ValueError(
                f"unsafe campaign_id {self.campaign_id!r}: must match "
                f"{_SAFE_CAMPAIGN_ID_RE.pattern} — it is interpolated into the audit "
                f"ledger path (fail-closed, like the Driver's loop_id guard)")
        self.milestones = topological_order(plan.get("milestones") or [])
        self.budget = plan.get("budget") or {}
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
            self.state = CampaignState.from_dict(json.load(fh))
        return True

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

    # ----- the loop ------------------------------------------------------ #
    def run(self, *, resume: bool = False) -> CampaignState:
        """Drive the backlog from the cursor. Returns the (terminal-or-paused)
        CampaignState. Pauses persist + return so a human can resolve + resume."""
        if resume and self._load():
            self._audit("campaign_resume",
                        {"from_status": self.state.status,
                         "pause_reason": self.state.pause_reason})
            if self.state.status in (STATUS_DONE, STATUS_ENDED):
                return self.state
            self.state.status = STATUS_RUNNING
            # (Decision routing for a resolved pause is the next increment; the
            # injected run_unit receives resume=True for Mechanism-A reasons.)
        else:
            self._audit("campaign_start",
                        {"campaign_id": self.campaign_id,
                         "goal": self.plan.get("goal"),
                         "milestones": [m["id"] for m in self.milestones]})
            if not self.plan.get("signed_by_human"):
                # The campaign plan (the milestone backlog) MUST be Customer-signed
                # before the runner drives it — the campaign-tier human gate
                # `campaign_plan_signoff` (design §5.1; 以终为始). Enforced HERE at the
                # campaign tier (NOT the charter validator — that validates charters,
                # not campaign plans). Resume once `signed_by_human: true` is set.
                return self._pause("campaign_plan_signoff", None,
                                   "campaign_plan_signoff",
                                   {"goal": self.plan.get("goal")})
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

            while self.state.subsprint_index < len(seq):
                # Countable budget cap, checked BETWEEN units (design §5.4a).
                over = self._over_budget()
                if over:
                    return self._pause("campaign_budget_exhausted", None,
                                       "campaign_budget_exhausted", {"dimension": over})

                subsprint_id = seq[self.state.subsprint_index]
                summary = self.run_unit(subsprint_id, resume=False)
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
                self.state.units.append(unit)
                self._save()
                return self._pause(
                    reason, summary.get("checkpoint_path"),
                    "campaign_pause",
                    {"milestone_id": milestone["id"], "subsprint_id": subsprint_id,
                     "loop_id": summary.get("loop_id"), "final_state": final_state,
                     "resume_class": classify_checkpoint(reason)})

            # milestone complete → advance to the next, reset the sub-sprint cursor.
            self.state.milestone_index += 1
            self.state.subsprint_index = 0
            self._save()

        # backlog exhausted.
        self.state.status = STATUS_DONE
        self._audit("campaign_done",
                    {"subsprints_run": self.state.subsprints_run,
                     "total_spawns": self.state.total_spawns})
        self._save()
        return self.state


def run_campaign(plan: dict, run_dir: str, run_unit: RunUnit, *,
                 clock: Callable[[], str], audit_dir: Optional[str] = None,
                 resume: bool = False) -> CampaignState:
    """Convenience entry point — construct a Campaign and run it."""
    return Campaign(plan, run_dir, run_unit, clock=clock,
                    audit_dir=audit_dir).run(resume=resume)
