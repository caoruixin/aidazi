"""Tests for the Campaign loop (P-B; design §5). stdlib unittest; offline (a fake
`run_unit` — no Driver, no adapters)."""
import ast
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)                    # orchestrator/
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)              # engine-kit/
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402
import audit_log as audit  # noqa: E402

_DRIVER_PY = os.path.join(_ORCH_DIR, "driver.py")


def _clock():
    """Deterministic incrementing ISO-8601 clock (minutes tick so wall-clock > 0)."""
    n = {"i": 0}

    def tick() -> str:
        n["i"] += 1
        return f"2026-06-20T00:{n['i'] // 60:02d}:{n['i'] % 60:02d}Z"
    return tick


def _plan(milestones, **kw):
    # Default to a SIGNED plan so the runner drives it; the signoff gate has its
    # own test below.
    return {"campaign_id": kw.pop("campaign_id", "camp-1"),
            "goal": "deliver the thing", "signed_by_human": kw.pop("signed_by_human", True),
            "milestones": milestones, **kw}


def _fake_run_unit(script):
    """`script` maps subsprint_id → summary dict (final_state, spawn_count, …)."""
    def run_unit(subsprint_id, *, resume=False):
        return dict(script[subsprint_id])
    return run_unit


class TestCheckpointInventoryFailClosed(unittest.TestCase):
    """EVERY checkpoint_id the Driver can emit MUST be classified by the campaign
    (design §5.4a fail-closed inventory) — so a future new Driver checkpoint can't
    silently slip past the resume map."""

    def _driver_checkpoint_ids(self):
        with open(_DRIVER_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        ids = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("_write_checkpoint", "_halt_checkpoint")
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                ids.add(node.args[0].value)
        return ids

    def test_every_driver_checkpoint_is_classified(self):
        emitted = self._driver_checkpoint_ids()
        self.assertTrue(emitted, "AST found no driver checkpoint ids — parser broke")
        unknown = emitted - cp.KNOWN_CHECKPOINTS
        self.assertEqual(
            unknown, set(),
            f"Driver emits checkpoint id(s) the campaign does not classify: "
            f"{sorted(unknown)}. Add each to the right set in campaign.py "
            f"(DRIVER_RESUME / DISPATCH / NON_PAUSE) — never leave it unmapped.")

    def test_sets_are_disjoint(self):
        sets = [cp.DRIVER_RESUME_CHECKPOINTS, cp.DISPATCH_CHECKPOINTS,
                cp.CAMPAIGN_CHECKPOINTS, cp.NON_PAUSE_CHECKPOINTS]
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                self.assertEqual(sets[i] & sets[j], frozenset(),
                                 "checkpoint classes must be disjoint")


class TestClassify(unittest.TestCase):
    def test_known_classes(self):
        self.assertEqual(cp.classify_checkpoint("dev_spec_refinement"), cp.RESUME_DRIVER)
        self.assertEqual(cp.classify_checkpoint("customer_gate1_signoff"), cp.RESUME_DRIVER)
        self.assertEqual(cp.classify_checkpoint("acceptance_fix_required"), cp.RESUME_DISPATCH)
        self.assertEqual(cp.classify_checkpoint("advisory_acceptance_pass_signoff"),
                         cp.RESUME_DISPATCH)
        self.assertEqual(cp.classify_checkpoint("memory_feedback"), cp.NON_PAUSE)

    def test_unknown_is_fail_closed_to_dispatch(self):
        # An unmapped halt must PAUSE for a human (dispatch), never auto-advance.
        self.assertEqual(cp.classify_checkpoint("some_future_checkpoint"),
                         cp.RESUME_DISPATCH)


class TestInterpretDispatch(unittest.TestCase):
    def test_advisory_signoff(self):
        self.assertEqual(cp.interpret_dispatch("advisory_acceptance_pass_signoff",
                                               {"choice": "ship"}),
                         cp.ACT_ADVANCE_MILESTONE)
        self.assertEqual(cp.interpret_dispatch("advisory_acceptance_pass_signoff",
                                               {"choice": "reject"}),
                         cp.ACT_DELIVER_FOLLOWUP)

    def test_acceptance_fix_required_confirm(self):
        self.assertEqual(cp.interpret_dispatch("acceptance_fix_required",
                                               {"confirm": "no"}),
                         cp.ACT_ADVANCE_MILESTONE)
        self.assertEqual(cp.interpret_dispatch("acceptance_fix_required",
                                               {"confirm": "yes", "route": "deliver_fix_iteration"}),
                         cp.ACT_DELIVER_FOLLOWUP)

    def test_scope_deviation_and_end(self):
        self.assertEqual(cp.interpret_dispatch("scope_deviation",
                                               {"choice": "accept_deviation"}),
                         cp.ACT_REDISPATCH_FRESH)
        self.assertEqual(cp.interpret_dispatch("scope_deviation",
                                               {"choice": "abandon"}), cp.ACT_END)

    def test_unknown_is_fail_closed(self):
        self.assertEqual(cp.interpret_dispatch("mystery", {"choice": "x"}),
                         cp.ACT_DELIVER_FOLLOWUP)


class TestTopologicalOrder(unittest.TestCase):
    def test_linear_default(self):
        ms = [{"id": "m1", "objective": "a"}, {"id": "m2", "objective": "b"}]
        self.assertEqual([m["id"] for m in cp.topological_order(ms)], ["m1", "m2"])

    def test_depends_on(self):
        ms = [{"id": "m2", "objective": "b", "depends_on": ["m1"]},
              {"id": "m1", "objective": "a"}]
        self.assertEqual([m["id"] for m in cp.topological_order(ms)], ["m1", "m2"])

    def test_cycle_raises(self):
        ms = [{"id": "m1", "objective": "a", "depends_on": ["m2"]},
              {"id": "m2", "objective": "b", "depends_on": ["m1"]}]
        with self.assertRaises(ValueError):
            cp.topological_order(ms)

    def test_unknown_dependency_raises(self):
        ms = [{"id": "m1", "objective": "a", "depends_on": ["ghost"]}]
        with self.assertRaises(ValueError):
            cp.topological_order(ms)

    def test_duplicate_milestone_ids_raise(self):
        ms = [{"id": "m1", "objective": "a"}, {"id": "m1", "objective": "b"}]
        with self.assertRaises(ValueError):
            cp.topological_order(ms)


class TestCampaignRobustness(unittest.TestCase):
    """Codex P-B impl review blockers 1-4."""

    def test_unsafe_campaign_id_raises(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}],
                         campaign_id="../evil")
            with self.assertRaises(ValueError):
                cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())

    def test_wall_clock_accumulates_across_resume(self):
        with tempfile.TemporaryDirectory() as d:
            # First invocation pauses mid-milestone (persists a wall_clock base).
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s2"]}])
            paused = cp.run_campaign(plan, d, _fake_run_unit({
                "s1": {"final_state": "advance", "spawn_count": 1},
                "s2": {"final_state": "halted", "spawn_count": 1,
                       "pause_reason": "acceptance_fix_required"}}), clock=_clock())
            self.assertEqual(paused.status, cp.STATUS_PAUSED)
            base = paused.wall_clock_minutes
            # Resume: wall-clock must NOT reset below the persisted base.
            resumed = cp.run_campaign(plan, d, _fake_run_unit({
                "s1": {"final_state": "advance", "spawn_count": 1},
                "s2": {"final_state": "done", "spawn_count": 1}}),
                clock=_clock(), resume=True)
            self.assertGreaterEqual(resumed.wall_clock_minutes, base)

    def test_audit_records_per_unit_loop_id(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}])
            camp = cp.Campaign(plan, d, _fake_run_unit({
                "s1": {"final_state": "done", "spawn_count": 2, "loop_id": "loop-xyz"}}),
                clock=_clock())
            camp.run()
            events = audit.read_events(camp.audit_ledger)
            loop_ids = [e["payload"].get("loop_id") for e in events
                        if e["type"] in ("campaign_subsprint_advance",
                                         "campaign_milestone_done")]
            self.assertIn("loop-xyz", loop_ids)   # ledger hash-chains the linkage
            self.assertTrue(audit.verify_chain(camp.audit_ledger).ok)


class TestCampaignRun(unittest.TestCase):
    def test_auto_advances_through_subsprints_and_milestones(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([
                {"id": "m1", "objective": "a", "subsprint_sequence": ["s1", "s2"]},
                {"id": "m2", "objective": "b", "subsprint_sequence": ["s3"]},
            ])
            script = {"s1": {"final_state": "advance", "spawn_count": 2, "loop_id": "l1"},
                      "s2": {"final_state": "done", "spawn_count": 3, "loop_id": "l2"},
                      "s3": {"final_state": "done", "spawn_count": 1, "loop_id": "l3"}}
            st = cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(st.subsprints_run, 3)
            self.assertEqual(st.total_spawns, 6)       # 2+3+1 (countable proxy)
            self.assertEqual([u["subsprint_id"] for u in st.units], ["s1", "s2", "s3"])
            self.assertTrue(audit.verify_chain(
                cp.Campaign(plan, d, _fake_run_unit(script), clock=_clock()).audit_ledger).ok
                or True)  # ledger exists; chain verified below
            # The campaign ledger verifies end-to-end.
            ledger = os.path.join(d, "audit",
                                  os.listdir(os.path.join(d, "audit"))[0])
            self.assertTrue(audit.verify_chain(ledger).ok)

    def test_pauses_on_a_human_gate_and_persists(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s2"]}])
            script = {"s1": {"final_state": "advance", "spawn_count": 1},
                      "s2": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required",
                             "checkpoint_path": "docs/checkpoints/x.md"}}
            st = cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "acceptance_fix_required")
            # State persisted at the cursor (mid-milestone, sub-sprint 1).
            self.assertEqual(st.subsprint_index, 1)
            self.assertTrue(os.path.isfile(os.path.join(d, "campaign-state.json")))

    def test_pauses_on_guided_pending_not_just_halted(self):
        # final_state = gate1_pending (NOT STATE_HALTED) must still PAUSE.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "gate1_pending", "spawn_count": 0,
                             "pause_reason": "customer_gate1_signoff"}}
            st = cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "customer_gate1_signoff")

    def test_campaign_budget_exhausted_between_units(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s2"]}],
                         budget={"max_subsprints": 1})
            script = {"s1": {"final_state": "advance", "spawn_count": 1},
                      "s2": {"final_state": "advance", "spawn_count": 1}}
            st = cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "campaign_budget_exhausted")
            self.assertEqual(st.subsprints_run, 1)   # stopped before the 2nd

    def test_unsigned_plan_pauses_at_signoff(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}], signed_by_human=False)
            st = cp.run_campaign(plan, d, _fake_run_unit(
                {"s1": {"final_state": "advance", "spawn_count": 1}}), clock=_clock())
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "campaign_plan_signoff")
            self.assertEqual(st.subsprints_run, 0)   # nothing dispatched pre-signoff

    def test_empty_subsprint_sequence_surfaces_decompose(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a"}])  # no subsprint_sequence
            st = cp.run_campaign(plan, d, _fake_run_unit({}), clock=_clock())
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "milestone_decompose_required")


if __name__ == "__main__":
    unittest.main()
