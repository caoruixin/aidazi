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

# A safe campaign_id — SAME discipline as the Driver's loop_id (letters/digits then
# ._- only; no path separators, no leading dot). It is interpolated into the audit
# ledger FILENAME, so it is validated FAIL-CLOSED at construction (Codex P-B impl
# blocking #1; mirrors driver.py _SAFE_LOOP_ID_RE).
_SAFE_CAMPAIGN_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
# The Driver checkpoint filename shape (<ts>__<checkpoint_id>__<scope>.md) — used to
# filter the checkpoints dir so a stray .md can't mask the real pause reason.
_CHECKPOINT_FILE_RE = re.compile(r"\A\d{8}-\d{6}__[A-Za-z0-9_]+__.+\.md\Z")

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
    followup_baseline_seq: Optional[List[str]] = None  # subsprint_sequence snapshot at a deliver_followup pause

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
            followup_baseline_seq=d.get("followup_baseline_seq"))


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
        for m in self.milestones:
            seq = m.get("subsprint_sequence") or []
            dupes = sorted({s for s in seq if seq.count(s) > 1})
            if dupes:
                # The id-novelty follow-up check (§ resume) AND the per-unit loop_id
                # hashing key on (campaign, milestone, subsprint) — both REQUIRE
                # sub-sprint ids unique within a milestone (Codex inc-2 round-4).
                raise ValueError(
                    f"milestone {m['id']!r} has duplicate sub-sprint id(s): {dupes}")
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

    def _repause(self, reason: str, why: str) -> str:
        self._pause(reason, self.state.pause_checkpoint, "campaign_repause",
                    {"why": why})
        return "paused"

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
            return ("proceed" if self.plan.get("signed_by_human")
                    else self._repause(reason, "still_unsigned"))
        if reason == "milestone_decompose_required":
            ms = self.milestones[self.state.milestone_index]
            return ("proceed" if ms.get("subsprint_sequence")
                    else self._repause(reason, "still_undecomposed"))
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
        self._audit("campaign_resume_dispatch",
                    {"pause_reason": reason, "action": action,
                     "choice": decision.get("choice") or decision.get("confirm")})
        if action == ACT_ADVANCE_SUBSPRINT:
            self.state.subsprint_index += 1   # this sub-sprint accepted → next in milestone
            return "proceed"
        if action == ACT_ADVANCE_MILESTONE:
            self.state.milestone_index += 1   # milestone accepted → next milestone
            self.state.subsprint_index = 0
            return "proceed"
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
                        functional_acceptance=milestone.get("functional_acceptance"))
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
                 resume: bool = False, decision_resolver=None) -> CampaignState:
    """Convenience entry point — construct a Campaign and run it."""
    return Campaign(plan, run_dir, run_unit, clock=clock,
                    audit_dir=audit_dir).run(resume=resume,
                                             decision_resolver=decision_resolver)


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
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()


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

    charter_mode = (((charter.get("tooling") or {}).get("acceptance") or {})
                    .get("functional") or {}).get("mode")
    if functional_acceptance is not None:
        fmode, fsource = functional_acceptance, "milestone"
    elif charter_mode is not None:
        fmode, fsource = charter_mode, "charter"
    else:
        fmode, fsource = "static", "default"
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
                 resume=False, functional_acceptance=None):
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

        cps_dir = os.path.join(unit_run_dir, "docs", "checkpoints")
        try:
            summary = run_loop_fn(unit_charter, run_dir=unit_run_dir, loop_id=loop_id,
                                  subsprint_id=subsprint_id, clock=clock,
                                  resume=resume, **call_kwargs)
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
