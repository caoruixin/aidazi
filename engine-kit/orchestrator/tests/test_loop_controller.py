#!/usr/bin/env python3
"""Tests for loop_controller — the deterministic Loop Controller (P3).

stdlib unittest only; pure + deterministic (no clock, no random, no IO). Run
this file directly (do NOT discover the dir — siblings may be mid-edit):

    python -m unittest engine-kit/orchestrator/tests/test_loop_controller.py -v

Covers: every predicate in isolation, the precedence ordering between them,
dry-stop firing at exactly K (and not before), max-rounds boundary, severity
escalate, and a full multi-round advancing sequence ending in halt(converged).
"""

import os
import sys
import unittest

# Make the orchestrator package dir importable regardless of cwd (tests/ is a
# child of orchestrator/, which holds loop_controller.py).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_THIS_DIR)
if _ORCH_DIR not in sys.path:
    sys.path.insert(0, _ORCH_DIR)

import loop_controller as lc  # noqa: E402
from loop_controller import (  # noqa: E402
    LoopState,
    Decision,
    decide,
    severity_rank,
    severity_worse_than_ceiling,
    ACTION_ADVANCE,
    ACTION_CONTINUE,
    ACTION_HALT,
    ACTION_ESCALATE,
    REASON_CLEAN_PASS,
    REASON_BUDGET,
    REASON_MAX_ROUNDS,
    REASON_SEVERITY,
    REASON_CONVERGED_DRY,
    REASON_CONTINUE,
)


def _assert_decision(testcase, dec, action, reason):
    testcase.assertIsInstance(dec, Decision)
    testcase.assertEqual(dec.action, action, f"action; detail={dec.detail!r}")
    testcase.assertEqual(dec.reason, reason, f"reason; detail={dec.detail!r}")


# --------------------------------------------------------------------------- #
# Severity helpers.
# --------------------------------------------------------------------------- #
class TestSeverityHelpers(unittest.TestCase):
    def test_rank_order_p0_worst(self):
        self.assertEqual(severity_rank("P0"), 0)
        self.assertEqual(severity_rank("P3"), 3)
        self.assertLess(severity_rank("P0"), severity_rank("P2"))

    def test_rank_case_insensitive_and_unknown(self):
        self.assertEqual(severity_rank("p1"), 1)
        self.assertIsNone(severity_rank("nope"))
        self.assertIsNone(severity_rank(None))

    def test_worse_than_ceiling(self):
        # P0 is worse than a P2 ceiling.
        self.assertTrue(severity_worse_than_ceiling("P0", "P2"))
        # P2 is NOT worse than a P2 ceiling (equal is allowed).
        self.assertFalse(severity_worse_than_ceiling("P2", "P2"))
        # P3 is less severe than a P1 ceiling.
        self.assertFalse(severity_worse_than_ceiling("P3", "P1"))

    def test_worse_than_ceiling_missing_labels(self):
        self.assertFalse(severity_worse_than_ceiling(None, "P2"))
        self.assertFalse(severity_worse_than_ceiling("P0", None))
        self.assertFalse(severity_worse_than_ceiling("???", "P2"))


# --------------------------------------------------------------------------- #
# Each predicate in isolation (build a state that triggers ONLY that branch).
# --------------------------------------------------------------------------- #
class TestPredicatesInIsolation(unittest.TestCase):
    def test_clean_pass_advances(self):
        st = LoopState(last_verdict="pass")
        _assert_decision(self, decide(st), ACTION_ADVANCE, REASON_CLEAN_PASS)

    def test_clean_pass_custom_verdict_set(self):
        st = LoopState(last_verdict="A", clean_verdicts=frozenset({"pass", "A"}))
        _assert_decision(self, decide(st), ACTION_ADVANCE, REASON_CLEAN_PASS)

    def test_budget_exhausted_halts(self):
        st = LoopState(last_verdict="fix_required", budget_spent=10.0, budget_cap=10.0)
        _assert_decision(self, decide(st), ACTION_HALT, REASON_BUDGET)

    def test_max_rounds_exceeded_halts(self):
        # max=2 permits 2 rounds; fix_round=3 trips it.
        st = LoopState(last_verdict="fix_required", fix_round=3, max_fix_rounds=2)
        _assert_decision(self, decide(st), ACTION_HALT, REASON_MAX_ROUNDS)

    def test_severity_over_ceiling_escalates(self):
        st = LoopState(
            last_verdict="fix_required",
            findings_this_round=1,
            worst_severity="P0",
            severity_ceiling="P2",
        )
        _assert_decision(self, decide(st), ACTION_ESCALATE, REASON_SEVERITY)

    def test_converged_dry_halts(self):
        st = LoopState(
            last_verdict="fix_required",
            findings_this_round=0,
            rounds_since_new_finding=3,
            dry_stop_threshold=3,
        )
        _assert_decision(self, decide(st), ACTION_HALT, REASON_CONVERGED_DRY)

    def test_default_continues(self):
        # fix_required, plenty of budget/rounds, severity under ceiling, not dry.
        st = LoopState(
            last_verdict="fix_required",
            fix_round=1,
            max_fix_rounds=5,
            findings_this_round=2,
            new_finding_keys=("f1", "f2"),
            rounds_since_new_finding=0,
            dry_stop_threshold=3,
            budget_spent=1.0,
            budget_cap=100.0,
            worst_severity="P2",
            severity_ceiling="P1",
        )
        _assert_decision(self, decide(st), ACTION_CONTINUE, REASON_CONTINUE)


# --------------------------------------------------------------------------- #
# Disabled-guard behaviour (None caps / thresholds must not fire).
# --------------------------------------------------------------------------- #
class TestDisabledGuards(unittest.TestCase):
    def test_budget_cap_none_disables(self):
        st = LoopState(last_verdict="fix_required", budget_spent=1e9, budget_cap=None)
        _assert_decision(self, decide(st), ACTION_CONTINUE, REASON_CONTINUE)

    def test_max_rounds_none_disables(self):
        st = LoopState(last_verdict="fix_required", fix_round=999, max_fix_rounds=None)
        _assert_decision(self, decide(st), ACTION_CONTINUE, REASON_CONTINUE)

    def test_severity_ceiling_none_disables(self):
        st = LoopState(last_verdict="fix_required", worst_severity="P0",
                       severity_ceiling=None)
        _assert_decision(self, decide(st), ACTION_CONTINUE, REASON_CONTINUE)

    def test_dry_threshold_none_disables(self):
        st = LoopState(last_verdict="fix_required", findings_this_round=0,
                       rounds_since_new_finding=99, dry_stop_threshold=None)
        _assert_decision(self, decide(st), ACTION_CONTINUE, REASON_CONTINUE)

    def test_dry_threshold_zero_disables(self):
        st = LoopState(last_verdict="fix_required", rounds_since_new_finding=5,
                       dry_stop_threshold=0)
        _assert_decision(self, decide(st), ACTION_CONTINUE, REASON_CONTINUE)


# --------------------------------------------------------------------------- #
# Precedence between predicates (build states triggering MULTIPLE; assert which
# wins per the documented order).
# --------------------------------------------------------------------------- #
class TestPrecedence(unittest.TestCase):
    def test_clean_pass_beats_everything(self):
        # All other guards would trip, but pass short-circuits to advance.
        st = LoopState(
            last_verdict="pass",
            fix_round=99, max_fix_rounds=2,
            budget_spent=100.0, budget_cap=10.0,
            worst_severity="P0", severity_ceiling="P2",
            rounds_since_new_finding=9, dry_stop_threshold=3,
        )
        _assert_decision(self, decide(st), ACTION_ADVANCE, REASON_CLEAN_PASS)

    def test_budget_beats_continue(self):
        st = LoopState(last_verdict="fix_required", budget_spent=10.0, budget_cap=10.0,
                       findings_this_round=3, fix_round=1, max_fix_rounds=9)
        _assert_decision(self, decide(st), ACTION_HALT, REASON_BUDGET)

    def test_budget_beats_max_rounds(self):
        # Both budget and max_rounds tripped; budget is checked first.
        st = LoopState(last_verdict="fix_required",
                       budget_spent=10.0, budget_cap=10.0,
                       fix_round=5, max_fix_rounds=2)
        _assert_decision(self, decide(st), ACTION_HALT, REASON_BUDGET)

    def test_budget_beats_severity(self):
        st = LoopState(last_verdict="fix_required",
                       budget_spent=10.0, budget_cap=10.0,
                       worst_severity="P0", severity_ceiling="P2")
        _assert_decision(self, decide(st), ACTION_HALT, REASON_BUDGET)

    def test_max_rounds_beats_severity(self):
        # max_rounds (hard stop) outranks severity escalate.
        st = LoopState(last_verdict="fix_required",
                       fix_round=5, max_fix_rounds=2,
                       worst_severity="P0", severity_ceiling="P2")
        _assert_decision(self, decide(st), ACTION_HALT, REASON_MAX_ROUNDS)

    def test_severity_beats_dry_and_continue(self):
        # Severity escalate outranks a converged-dry halt.
        st = LoopState(last_verdict="fix_required",
                       worst_severity="P0", severity_ceiling="P2",
                       rounds_since_new_finding=3, dry_stop_threshold=3)
        _assert_decision(self, decide(st), ACTION_ESCALATE, REASON_SEVERITY)

    def test_dry_beats_continue(self):
        st = LoopState(last_verdict="fix_required",
                       findings_this_round=0,
                       rounds_since_new_finding=2, dry_stop_threshold=2,
                       fix_round=1, max_fix_rounds=9,
                       budget_spent=1.0, budget_cap=100.0)
        _assert_decision(self, decide(st), ACTION_HALT, REASON_CONVERGED_DRY)


# --------------------------------------------------------------------------- #
# Boundary values for each numeric guard.
# --------------------------------------------------------------------------- #
class TestBoundaries(unittest.TestCase):
    def test_budget_below_at_above_cap(self):
        below = LoopState(last_verdict="fix_required", budget_spent=9.99, budget_cap=10.0)
        _assert_decision(self, decide(below), ACTION_CONTINUE, REASON_CONTINUE)
        at = LoopState(last_verdict="fix_required", budget_spent=10.0, budget_cap=10.0)
        _assert_decision(self, decide(at), ACTION_HALT, REASON_BUDGET)  # >= fires
        above = LoopState(last_verdict="fix_required", budget_spent=10.01, budget_cap=10.0)
        _assert_decision(self, decide(above), ACTION_HALT, REASON_BUDGET)

    def test_max_rounds_boundary_uses_strict_gt(self):
        # max=2: round 2 still continues (within bound), round 3 halts.
        eq = LoopState(last_verdict="fix_required", fix_round=2, max_fix_rounds=2)
        _assert_decision(self, decide(eq), ACTION_CONTINUE, REASON_CONTINUE)
        over = LoopState(last_verdict="fix_required", fix_round=3, max_fix_rounds=2)
        _assert_decision(self, decide(over), ACTION_HALT, REASON_MAX_ROUNDS)

    def test_severity_equal_ceiling_not_escalated(self):
        # worst == ceiling is allowed (auto-fix at or below the ceiling).
        eq = LoopState(last_verdict="fix_required", findings_this_round=1,
                       worst_severity="P2", severity_ceiling="P2",
                       fix_round=1, max_fix_rounds=9)
        _assert_decision(self, decide(eq), ACTION_CONTINUE, REASON_CONTINUE)


# --------------------------------------------------------------------------- #
# Dry-stop fires after EXACTLY K clean rounds and not before.
# --------------------------------------------------------------------------- #
class TestDryStopExactlyK(unittest.TestCase):
    def test_dry_stop_fires_at_exactly_k(self):
        K = 3
        # K-1 dry rounds: not yet converged → continue.
        for n in range(0, K):
            st = LoopState(last_verdict="fix_required", findings_this_round=0,
                           rounds_since_new_finding=n, dry_stop_threshold=K)
            dec = decide(st)
            self.assertEqual(
                dec.action, ACTION_CONTINUE,
                f"rounds_since_new_finding={n} (<K={K}) should continue, got {dec.action}",
            )
        # At K and beyond: converged → halt.
        for n in (K, K + 1, K + 5):
            st = LoopState(last_verdict="fix_required", findings_this_round=0,
                           rounds_since_new_finding=n, dry_stop_threshold=K)
            dec = decide(st)
            _assert_decision(self, dec, ACTION_HALT, REASON_CONVERGED_DRY)

    def test_dry_round_detected_via_new_keys(self):
        # Empty new_finding_keys == dry even if findings_this_round > 0
        # (those findings were all repeats — caller already deduped).
        st = LoopState(last_verdict="fix_required",
                       findings_this_round=5, new_finding_keys=(),
                       rounds_since_new_finding=2, dry_stop_threshold=2)
        _assert_decision(self, decide(st), ACTION_HALT, REASON_CONVERGED_DRY)

    def test_new_keys_present_is_progress(self):
        # New keys present → is_dry_round False (caller would reset the K-counter).
        st = LoopState(last_verdict="fix_required",
                       findings_this_round=1, new_finding_keys=("nf",))
        self.assertFalse(st.is_dry_round())


# --------------------------------------------------------------------------- #
# Decision convenience API.
# --------------------------------------------------------------------------- #
class TestDecisionApi(unittest.TestCase):
    def test_is_terminal(self):
        self.assertTrue(decide(LoopState(last_verdict="pass")).is_terminal)
        cont = decide(LoopState(last_verdict="fix_required", findings_this_round=2))
        self.assertFalse(cont.is_terminal)

    def test_determinism_same_state_same_decision(self):
        st = LoopState(last_verdict="fix_required", fix_round=2, max_fix_rounds=5,
                       findings_this_round=1, worst_severity="P2",
                       severity_ceiling="P1", budget_spent=3.0, budget_cap=50.0,
                       rounds_since_new_finding=1, dry_stop_threshold=3)
        d1, d2 = decide(st), decide(st)
        self.assertEqual((d1.action, d1.reason, d1.detail),
                         (d2.action, d2.reason, d2.detail))


# --------------------------------------------------------------------------- #
# A full multi-round sequence: continue → … → halt(converged).
# Simulates the caller maintaining the K-counter across rounds.
# --------------------------------------------------------------------------- #
class TestMultiRoundSequence(unittest.TestCase):
    def _run_sequence(self, rounds, *, max_fix_rounds, dry_K, budget_cap):
        """rounds: list of new-finding-key sets per round (the round's NEW
        findings). Returns the list of (round_index, Decision) the controller
        produced, stopping at the first terminal decision — exactly how the
        driver would drive it."""
        trace = []
        rounds_since_new = 0
        budget_spent = 0.0
        for i, new_keys in enumerate(rounds, start=1):
            budget_spent += 1.0  # 1 unit per round
            # Caller's K-counter discipline: reset on progress, +1 on a dry round.
            if len(new_keys) == 0:
                rounds_since_new += 1
            else:
                rounds_since_new = 0
            st = LoopState(
                last_verdict="fix_required",
                fix_round=i,
                max_fix_rounds=max_fix_rounds,
                findings_this_round=len(new_keys),
                new_finding_keys=tuple(new_keys),
                rounds_since_new_finding=rounds_since_new,
                dry_stop_threshold=dry_K,
                budget_spent=budget_spent,
                budget_cap=budget_cap,
            )
            dec = decide(st)
            trace.append((i, dec))
            if dec.is_terminal:
                break
        return trace

    def test_converges_after_continues(self):
        # Rounds: real progress, real progress, then 2 dry rounds (K=2) → halt.
        rounds = [{"a", "b"}, {"c"}, set(), set(), {"never-reached"}]
        trace = self._run_sequence(rounds, max_fix_rounds=10, dry_K=2, budget_cap=100.0)
        actions = [d.action for _, d in trace]
        reasons = [d.reason for _, d in trace]
        # Round1: continue, Round2: continue, Round3: dry#1 continue, Round4: dry#2 halt.
        self.assertEqual(actions, [ACTION_CONTINUE, ACTION_CONTINUE,
                                   ACTION_CONTINUE, ACTION_HALT])
        self.assertEqual(reasons[-1], REASON_CONVERGED_DRY)
        self.assertEqual(len(trace), 4)  # stops at first terminal (round 4)

    def test_sequence_hits_max_rounds_before_convergence(self):
        # Never goes dry; max_fix_rounds=2 → round 3 halts on max_rounds.
        rounds = [{"a"}, {"b"}, {"c"}, {"d"}]
        trace = self._run_sequence(rounds, max_fix_rounds=2, dry_K=3, budget_cap=100.0)
        actions = [d.action for _, d in trace]
        self.assertEqual(actions, [ACTION_CONTINUE, ACTION_CONTINUE, ACTION_HALT])
        self.assertEqual(trace[-1][1].reason, REASON_MAX_ROUNDS)

    def test_sequence_hits_budget(self):
        rounds = [{"a"}, {"b"}, {"c"}]
        trace = self._run_sequence(rounds, max_fix_rounds=10, dry_K=5, budget_cap=2.0)
        # Round1 spend=1 continue; Round2 spend=2 >= cap → halt(budget).
        self.assertEqual([d.action for _, d in trace], [ACTION_CONTINUE, ACTION_HALT])
        self.assertEqual(trace[-1][1].reason, REASON_BUDGET)


if __name__ == "__main__":
    unittest.main(verbosity=2)
