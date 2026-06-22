#!/usr/bin/env python3
"""loop_controller — the deterministic Loop Controller (P3, standalone).

The **Loop Controller** is the "loop iteration" concept of the v2 loop engine
(archive/2026-06-15-v2-loop-engine-plan.md §2 glossary): it owns
*loop-until-condition / convergence / dry-stop / budget* termination semantics.
It answers exactly one question per iteration:

    given the state of a fix loop after a verdict, do we ADVANCE, CONTINUE
    (another fix round), HALT (terminate), or ESCALATE (needs a human)?

It is a **pure, deterministic, no-LLM, no-IO function over a state object**. It
has no clock, no randomness, no filesystem, no network. Severity dedup / finding
identity is the CALLER's responsibility — this module consumes plain counts and
finding keys (it never inspects finding bodies).

NORMATIVE SOURCE
----------------
- archive/2026-06-15-v2-loop-engine-plan.md — glossary "Loop Controller"; §4
  (R5 termination predicates: convergence, dry-stop, budget); §4.3 (Loop
  Ingress↔Controller pairing — Ingress starts the loop, Controller bounds it).
- process/delivery-loop.md §4.4 (auto-fix iteration bounds: `max_rounds`,
  `only_if_findings_severity_at_most`) + §4.2.2 budget
  (`max_api_usd` / `max_fix_rounds_total` / `max_wall_clock_minutes`).

This is an engine-kit reference *implementation*; on any conflict with the spec
the spec wins and this file is the bug.

API CONTRACT (what the driver will call in the integration step)
----------------------------------------------------------------
``decide(state: LoopState) -> Decision``

The driver, after parsing a review/close verdict, builds a ``LoopState`` from
the data it already tracks (``RunState.fix_round``, ``charter.budget.*``, the
verdict's ``decision`` / ``worst_severity`` / findings) and asks the controller
what to do next, instead of hard-coding the "P2 MVP: always halt to a human"
branch in ``driver._handle_fix_required``. The controller NEVER performs the
action — it only names it + a machine-readable reason code; the driver/adapters
still own all side effects (spawning a fix round, writing checkpoints, emitting
audit events).

PRECEDENCE (documented, total, deterministic) — first match wins:
  1. clean_pass        → advance  (CLEAN_PASS)
  2. budget_exhausted  → halt     (BUDGET)              spent >= cap
  3. max_rounds        → halt     (MAX_ROUNDS)          fix_round > max
  4. severity ceiling  → escalate (SEVERITY)            worst worse than ceiling
  5. dry-stop/converge → halt     (CONVERGED_DRY)       K consecutive clean rounds
  6. otherwise         → continue (CONTINUE)            another fix round permitted

Rationale for this order:
  - A clean pass means there is nothing left to fix, so it short-circuits every
    "we are still looping" guard (a clean pass beats everything).
  - Resource guards (budget, then max-rounds) are hard, non-negotiable stops and
    take priority over any semantic routing so a runaway loop always terminates.
  - Severity escalation is a routing decision (human needed) and only matters
    while we are otherwise still allowed to loop, so it sits below the hard stops.
  - Dry-stop is the "we are making no progress" convergence stop; it is the last
    terminating guard before defaulting to another round.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


# --------------------------------------------------------------------------- #
# Actions + machine-readable reason codes.
# --------------------------------------------------------------------------- #
# Actions the controller can return (mirror the plan's four outcomes).
ACTION_ADVANCE = "advance"        # clean pass — leave the fix loop, move forward
ACTION_CONTINUE = "continue"      # another fix round is permitted
ACTION_HALT = "halt"              # terminate the loop (resource / convergence)
ACTION_ESCALATE = "escalate"      # needs a human / checkpoint before continuing

# Reason codes (stable strings — safe to log, branch on, and audit).
REASON_CLEAN_PASS = "clean_pass"        # advance
REASON_BUDGET = "budget"                # halt
REASON_MAX_ROUNDS = "max_rounds"        # halt
REASON_SEVERITY = "severity"            # escalate
REASON_CONVERGED_DRY = "converged_dry"  # halt
REASON_CONTINUE = "continue"            # continue


# --------------------------------------------------------------------------- #
# Severity ordering. P0 is the WORST (most severe), P3 the least.
# Matches delivery-loop §4.4 `only_if_findings_severity_at_most` (the ceiling is
# the LEAST-severe level still allowed to auto-fix) and the verdict shapes'
# `worst_severity` (§4.2.7). Lower rank == worse.
# --------------------------------------------------------------------------- #
SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def severity_rank(sev: Optional[str]) -> Optional[int]:
    """Return the numeric rank for a severity label, or None if unknown/absent.

    Lower == worse (P0 -> 0). Unknown / None severities return None so the
    caller can decide; the controller treats an unknown worst_severity as
    "no severity signal" (does not escalate on it)."""
    if sev is None:
        return None
    return SEVERITY_RANK.get(str(sev).upper())


def severity_worse_than_ceiling(worst: Optional[str], ceiling: Optional[str]) -> bool:
    """True iff ``worst`` is strictly more severe than ``ceiling``.

    Both are P-labels; lower rank == worse, so "worse than" means a strictly
    smaller rank. If either label is absent/unknown, there is no actionable
    severity signal and this returns False (no escalation)."""
    w = severity_rank(worst)
    c = severity_rank(ceiling)
    if w is None or c is None:
        return False
    return w < c


# --------------------------------------------------------------------------- #
# The state object the controller decides over.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LoopState:
    """Immutable snapshot of a fix loop at one decision point.

    The caller (driver) builds this from the data it already tracks; the
    controller never mutates it (frozen) and reads only these fields.

    Fields
    ------
    last_verdict:
        The routing decision from the most recent review/close verdict, e.g.
        ``"pass"`` / ``"fix_required"`` / ``"out_of_scope_review"``. A clean
        pass is signalled by ``last_verdict in CLEAN_VERDICTS`` (default
        ``{"pass"}``); see ``clean_verdicts``. This is the ONLY field that can
        produce ``advance``.
    fix_round:
        How many fix rounds have been spent so far (driver ``RunState.fix_round``;
        0 before the first fix). Compared to ``max_fix_rounds``.
    max_fix_rounds:
        The cap from ``charter.budget.max_fix_rounds_total`` /
        ``auto_fix_iteration.max_rounds`` (§4.2.2 / §4.4). ``fix_round > max``
        halts. ``None`` disables the round cap.
    findings_this_round:
        Count of findings the just-finished round produced. 0 == a clean round
        (no findings) and feeds dry-stop. (Identity-level dedup is the caller's
        job — see ``new_finding_keys``.)
    new_finding_keys:
        Optional set/sequence of finding identities that are NEW vs prior rounds.
        If provided it is authoritative for "did this round make progress?"
        (empty == no new findings == a dry round). If ``None`` the controller
        falls back to ``findings_this_round == 0`` to detect a dry round.
    rounds_since_new_finding:
        K-counter the CALLER maintains: consecutive rounds with no NEW finding.
        This is the dry-stop accumulator. When it reaches ``dry_stop_threshold``
        the loop has converged. (The controller reads it; the caller increments
        it — typically: reset to 0 on a round with new findings, +1 otherwise.)
    dry_stop_threshold:
        K — number of consecutive no-new-finding rounds that means "converged".
        ``None`` or a value < 1 disables dry-stop. The stop fires when
        ``rounds_since_new_finding >= dry_stop_threshold``.
    budget_spent / budget_cap:
        Generic resource counters (e.g. API USD per §4.2.2 ``max_api_usd``, or
        wall-clock minutes). ``budget_spent >= budget_cap`` halts. ``budget_cap``
        of ``None`` disables the budget guard. Units are the caller's choice;
        the controller only compares the two numbers.
    worst_severity / severity_ceiling:
        ``worst_severity`` is the most-severe finding label this round
        (verdict ``worst_severity``, §4.2.7). ``severity_ceiling`` is the
        least-severe level still permitted to auto-fix
        (``only_if_findings_severity_at_most``, §4.4). If ``worst_severity`` is
        strictly worse than the ceiling the controller escalates to a human.
        Either being ``None`` disables the severity check.
    clean_verdicts:
        The set of ``last_verdict`` strings that count as a clean pass.
        Defaults to ``{"pass"}``. (Lets an adopter treat additional verdict
        strings as clean without changing this module.)
    """

    last_verdict: Optional[str] = None
    fix_round: int = 0
    max_fix_rounds: Optional[int] = None
    findings_this_round: int = 0
    new_finding_keys: Optional[Sequence[str]] = None
    rounds_since_new_finding: int = 0
    dry_stop_threshold: Optional[int] = None
    budget_spent: float = 0.0
    budget_cap: Optional[float] = None
    worst_severity: Optional[str] = None
    severity_ceiling: Optional[str] = None
    clean_verdicts: frozenset = frozenset({"pass"})

    # --- derived predicates (pure helpers; no side effects) ---------------- #
    def is_clean_pass(self) -> bool:
        """A clean pass = the verdict says pass. Findings are irrelevant here:
        the verdict, not a finding count, is the authority on pass/fix."""
        return self.last_verdict in self.clean_verdicts

    def is_budget_exhausted(self) -> bool:
        """spent >= cap (cap None disables)."""
        return self.budget_cap is not None and self.budget_spent >= self.budget_cap

    def is_max_rounds_exceeded(self) -> bool:
        """fix_round > max (max None disables). ``>`` not ``>=`` so a charter of
        max_rounds=N permits exactly N fix rounds (round N+1 trips it), matching
        driver._check_budget's ``fix_round > max_fix``."""
        return self.max_fix_rounds is not None and self.fix_round > self.max_fix_rounds

    def is_over_severity_ceiling(self) -> bool:
        """worst_severity strictly worse than the ceiling (both must be known)."""
        return severity_worse_than_ceiling(self.worst_severity, self.severity_ceiling)

    def is_dry_round(self) -> bool:
        """Did the most recent round add NO new findings? Uses explicit new-key
        identities if the caller supplied them, else falls back to a zero count."""
        if self.new_finding_keys is not None:
            return len(self.new_finding_keys) == 0
        return self.findings_this_round == 0

    def is_converged_dry(self) -> bool:
        """K consecutive no-new-finding rounds reached (threshold None/<1
        disables). Uses the caller-maintained ``rounds_since_new_finding``."""
        if self.dry_stop_threshold is None or self.dry_stop_threshold < 1:
            return False
        return self.rounds_since_new_finding >= self.dry_stop_threshold


# --------------------------------------------------------------------------- #
# The decision the controller returns.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Decision:
    """The controller's verdict for one iteration.

    action:  one of ACTION_ADVANCE / ACTION_CONTINUE / ACTION_HALT / ACTION_ESCALATE.
    reason:  a stable machine-readable reason code (REASON_* above).
    detail:  optional human-readable one-liner (NOT machine-parsed) for logs /
             checkpoint context. Deterministic given the state.
    """

    action: str
    reason: str
    detail: str = ""

    # Convenience predicates for callers (avoid string compares at call sites).
    @property
    def is_terminal(self) -> bool:
        """True if the loop should stop iterating (advance / halt / escalate).
        Only ``continue`` is non-terminal."""
        return self.action != ACTION_CONTINUE


# --------------------------------------------------------------------------- #
# The one public function.
# --------------------------------------------------------------------------- #
def decide(state: LoopState) -> Decision:
    """Decide whether the fix loop advances / continues / halts / escalates.

    Pure + deterministic: same ``state`` -> same ``Decision``, always. No clock,
    no randomness, no IO. Evaluates the predicates in the documented precedence
    (first match wins); see the module docstring for the ordering rationale.
    """
    # 1. Clean pass beats everything — nothing left to fix.
    if state.is_clean_pass():
        return Decision(
            ACTION_ADVANCE, REASON_CLEAN_PASS,
            f"clean pass (verdict={state.last_verdict!r})",
        )

    # 2. Budget exhausted — hard stop (resource guard).
    if state.is_budget_exhausted():
        return Decision(
            ACTION_HALT, REASON_BUDGET,
            f"budget exhausted ({state.budget_spent} >= cap {state.budget_cap})",
        )

    # 3. Max fix rounds exceeded — hard stop (anti ping-pong, §4.4).
    if state.is_max_rounds_exceeded():
        return Decision(
            ACTION_HALT, REASON_MAX_ROUNDS,
            f"fix_round {state.fix_round} exceeds max {state.max_fix_rounds}",
        )

    # 4. Severity over the auto-fix ceiling — needs a human (§4.4).
    if state.is_over_severity_ceiling():
        return Decision(
            ACTION_ESCALATE, REASON_SEVERITY,
            f"worst severity {state.worst_severity} worse than ceiling "
            f"{state.severity_ceiling}",
        )

    # 5. Dry-stop / convergence — K consecutive no-new-finding rounds.
    if state.is_converged_dry():
        return Decision(
            ACTION_HALT, REASON_CONVERGED_DRY,
            f"converged: {state.rounds_since_new_finding} consecutive rounds with "
            f"no new finding (K={state.dry_stop_threshold})",
        )

    # 6. Otherwise another fix round is permitted.
    return Decision(
        ACTION_CONTINUE, REASON_CONTINUE,
        f"fix round permitted (fix_round={state.fix_round}, "
        f"findings_this_round={state.findings_this_round})",
    )


__all__ = [
    "LoopState",
    "Decision",
    "decide",
    "severity_rank",
    "severity_worse_than_ceiling",
    "SEVERITY_RANK",
    "ACTION_ADVANCE",
    "ACTION_CONTINUE",
    "ACTION_HALT",
    "ACTION_ESCALATE",
    "REASON_CLEAN_PASS",
    "REASON_BUDGET",
    "REASON_MAX_ROUNDS",
    "REASON_SEVERITY",
    "REASON_CONVERGED_DRY",
    "REASON_CONTINUE",
]
