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
    def run_unit(subsprint_id, *, milestone_id=None, resume=False):
        return dict(script[subsprint_id])
    return run_unit


def _seq_run_unit(seqs, record=None):
    """`seqs` maps subsprint_id → LIST of summaries consumed one per call (so a
    re-dispatch/resume returns the next one). `record` (if given) logs each call's
    (subsprint_id, resume) so a test can assert Mechanism-A resume=True."""
    counters: dict = {}
    def run_unit(subsprint_id, *, milestone_id=None, resume=False):
        i = counters.get(subsprint_id, 0)
        counters[subsprint_id] = i + 1
        if record is not None:
            record.append({"subsprint_id": subsprint_id, "resume": resume})
        lst = seqs[subsprint_id]
        return dict(lst[min(i, len(lst) - 1)])
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

    def test_duplicate_subsprint_ids_within_milestone_raise(self):
        # Uniqueness within a milestone is required by the follow-up id-novelty check
        # + per-unit loop_id keying (Codex inc-2 round-4).
        import tempfile as _tf
        with _tf.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s1"]}])
            with self.assertRaises(ValueError):
                cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())


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


class TestCampaignResume(unittest.TestCase):
    """Resume decision-execution (increment 2) — Mechanism A driver-resume vs
    Mechanism B campaign-dispatch (advance / redispatch / followup / end)."""

    def _resolver(self, mapping):
        return lambda reason, cp: mapping.get(reason)

    def test_advisory_signoff_ship_advances_to_next_milestone(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([
                {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "advisory_acceptance_pass_signoff"},
                      "s2": {"final_state": "done", "spawn_count": 1}}
            paused = cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            self.assertEqual(paused.pause_reason, "advisory_acceptance_pass_signoff")
            resumed = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"advisory_acceptance_pass_signoff": {"choice": "ship"}}))
            self.assertEqual(resumed.status, cp.STATUS_DONE)   # advanced m1→m2→done
            self.assertEqual(resumed.milestone_index, 2)

    def test_driver_resume_redispatches_with_resume_true(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            rec = []
            seqs = {"s1": [
                {"final_state": "halted", "spawn_count": 1,
                 "pause_reason": "dev_spec_refinement"},
                {"final_state": "done", "spawn_count": 1}]}
            ru = _seq_run_unit(seqs, rec)   # ONE instance — its counter persists across calls
            cp.run_campaign(plan, d, ru, clock=_clock())
            self.assertEqual(rec[0]["resume"], False)
            resumed = cp.run_campaign(
                plan, d, ru, clock=_clock(), resume=True,
                decision_resolver=self._resolver({"dev_spec_refinement": {"choice": "x"}}))
            # The SECOND dispatch (resume) re-entered the Driver with resume=True.
            self.assertEqual(rec[-1]["resume"], True)
            self.assertEqual(resumed.status, cp.STATUS_DONE)

    def test_abort_decision_ends_campaign(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "scope_deviation"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver({"scope_deviation": {"choice": "abandon"}}))
            self.assertEqual(resumed.status, cp.STATUS_ENDED)

    def test_no_resolver_repauses(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock(),
                                      resume=True, decision_resolver=None)
            self.assertEqual(resumed.status, cp.STATUS_PAUSED)
            self.assertEqual(resumed.pause_reason, "acceptance_fix_required")

    def test_deliver_followup_route_surfaces(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"acceptance_fix_required": {"confirm": "yes",
                                                 "route": "deliver_fix_iteration"}}))
            self.assertEqual(resumed.status, cp.STATUS_PAUSED)
            self.assertEqual(resumed.pause_reason, "deliver_followup_required")

    def test_plan_signoff_resume_when_now_signed(self):
        with tempfile.TemporaryDirectory() as d:
            unsigned = _plan([{"id": "m1", "objective": "a",
                               "subsprint_sequence": ["s1"]}], signed_by_human=False)
            script = {"s1": {"final_state": "done", "spawn_count": 1}}
            paused = cp.run_campaign(unsigned, d, _fake_run_unit(script), clock=_clock())
            self.assertEqual(paused.pause_reason, "campaign_plan_signoff")
            signed = dict(unsigned, signed_by_human=True)
            resumed = cp.run_campaign(signed, d, _fake_run_unit(script),
                                      clock=_clock(), resume=True)
            self.assertEqual(resumed.status, cp.STATUS_DONE)

    def test_review_out_of_scope_accept_advances_subsprint_not_milestone(self):
        # review runs per sub-sprint; accept_and_advance must dispatch s2 (NOT skip
        # to the next milestone). s2 then pauses with a DISTINCT reason → proof it ran.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s2"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "review_out_of_scope"},
                      "s2": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"review_out_of_scope": {"choice": "accept_and_advance"}}))
            self.assertEqual(resumed.status, cp.STATUS_PAUSED)
            self.assertEqual(resumed.pause_reason, "acceptance_fix_required")  # s2 ran

    def test_deliver_followup_inserted_then_resumed(self):
        with tempfile.TemporaryDirectory() as d:
            ms = {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}
            plan = _plan([ms])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required"},
                      "s2": {"final_state": "done", "spawn_count": 1}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            paused = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"acceptance_fix_required": {"confirm": "yes",
                                                 "route": "deliver_fix_iteration"}}))
            self.assertEqual(paused.pause_reason, "deliver_followup_required")
            # Deliver inserts the follow-up sub-sprint s2 at cursor+1; resume dispatches it.
            ms["subsprint_sequence"] = ["s1", "s2"]
            resumed = cp.run_campaign(plan, d, _fake_run_unit(script),
                                      clock=_clock(), resume=True)
            self.assertEqual(resumed.status, cp.STATUS_DONE)

    def test_deliver_followup_no_insertion_repauses_even_with_next_item(self):
        # Original sequence ALREADY has s2; routing s1 to deliver_followup must NOT
        # dispatch the pre-existing s2 — it re-pauses until Deliver inserts a follow-up
        # (the sequence-grew check, Codex inc-2 #3 PARTIAL fix).
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s2"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required"},
                      "s2": {"final_state": "done", "spawn_count": 1}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            paused = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"acceptance_fix_required": {"confirm": "yes",
                                                 "route": "deliver_fix_iteration"}}))
            self.assertEqual(paused.pause_reason, "deliver_followup_required")
            # Resume WITHOUT inserting anything → re-pause (does NOT dispatch s2).
            again = cp.run_campaign(plan, d, _fake_run_unit(script),
                                    clock=_clock(), resume=True)
            self.assertEqual(again.status, cp.STATUS_PAUSED)
            self.assertEqual(again.pause_reason, "deliver_followup_required")

    def test_deliver_followup_append_elsewhere_repauses(self):
        # Deliver APPENDS the fix at the END (not at cursor+1) → cursor+1 is still the
        # pre-existing s2, not the new follow-up → must re-pause (Codex inc-2 #3 final:
        # prove inserted-at-cursor+1, not merely sequence-grew).
        with tempfile.TemporaryDirectory() as d:
            ms = {"id": "m1", "objective": "a", "subsprint_sequence": ["s1", "s2"]}
            plan = _plan([ms])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required"},
                      "s2": {"final_state": "done", "spawn_count": 1},
                      "s_fix": {"final_state": "done", "spawn_count": 1}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                            decision_resolver=self._resolver(
                                {"acceptance_fix_required": {"confirm": "yes",
                                                             "route": "deliver_fix_iteration"}}))
            ms["subsprint_sequence"] = ["s1", "s2", "s_fix"]   # appended at END (wrong place)
            again = cp.run_campaign(plan, d, _fake_run_unit(script),
                                    clock=_clock(), resume=True)
            self.assertEqual(again.status, cp.STATUS_PAUSED)   # did NOT dispatch pre-existing s2
            self.assertEqual(again.pause_reason, "deliver_followup_required")

    def test_deliver_followup_insert_at_cursor_in_multi_sequence(self):
        # Deliver INSERTS the fix at cursor+1 in a multi-item sequence → dispatched.
        with tempfile.TemporaryDirectory() as d:
            ms = {"id": "m1", "objective": "a", "subsprint_sequence": ["s1", "s2"]}
            plan = _plan([ms])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required"},
                      "s_fix": {"final_state": "advance", "spawn_count": 1},
                      "s2": {"final_state": "done", "spawn_count": 1}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                            decision_resolver=self._resolver(
                                {"acceptance_fix_required": {"confirm": "yes",
                                                             "route": "deliver_fix_iteration"}}))
            ms["subsprint_sequence"] = ["s1", "s_fix", "s2"]   # inserted at cursor+1
            resumed = cp.run_campaign(plan, d, _fake_run_unit(script),
                                      clock=_clock(), resume=True)
            # dispatch s_fix (advance) → s2 (done) → milestone done → campaign done.
            self.assertEqual(resumed.status, cp.STATUS_DONE)

    def test_running_state_resume_continues_without_repause(self):
        # A persisted RUNNING state (crash recovery) must CONTINUE from the cursor,
        # not be re-interpreted as a pause (Codex inc-2 blocking #4).
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            done = {"s1": {"final_state": "done", "spawn_count": 1}}
            camp = cp.Campaign(plan, d, _fake_run_unit(done), clock=_clock())
            camp.state.status = cp.STATUS_RUNNING   # seed a clean mid-flight state
            camp.state.pause_reason = None
            camp._save()
            resumed = cp.Campaign(plan, d, _fake_run_unit(done),
                                  clock=_clock()).run(resume=True)
            self.assertEqual(resumed.status, cp.STATUS_DONE)


class TestProductionRunUnit(unittest.TestCase):
    """make_run_unit — the production wrapper around run_loop (increment 2)."""

    def test_advance_summary(self):
        with tempfile.TemporaryDirectory() as d:
            def fake(charter, *, run_dir, loop_id, subsprint_id, clock, **kw):
                return {"final_state": "advance", "spawn_count": 2}
            ru = cp.make_run_unit({}, d, "camp-1", clock=_clock(), run_loop_fn=fake)
            out = ru("s1", milestone_id="m1")
            self.assertEqual(out["final_state"], "advance")
            self.assertIsNone(out["pause_reason"])
            self.assertTrue(out["loop_id"].startswith("u"))    # hashed, collision-free, bounded
            self.assertEqual(out["loop_id"], ru("s1", milestone_id="m1")["loop_id"])  # deterministic
            self.assertNotEqual(out["loop_id"], ru("s1", milestone_id="m2")["loop_id"])  # per-tuple
            self.assertEqual(out["spawn_count"], 2)

    def test_resume_propagates_to_run_loop(self):
        with tempfile.TemporaryDirectory() as d:
            seen = {}
            def fake(charter, *, run_dir, loop_id, subsprint_id, clock, resume=False, **kw):
                seen["resume"] = resume
                return {"final_state": "advance", "spawn_count": 0}
            ru = cp.make_run_unit({}, d, "camp-1", clock=_clock(), run_loop_fn=fake)
            ru("s1", milestone_id="m1", resume=True)
            self.assertTrue(seen["resume"])   # Mechanism-A resume reaches run_loop → Driver

    def test_unsafe_id_component_raises_before_makedirs(self):
        with tempfile.TemporaryDirectory() as d:
            ru = cp.make_run_unit({}, d, "camp-1", clock=_clock(),
                                  run_loop_fn=lambda *a, **k: {"final_state": "advance",
                                                              "spawn_count": 0})
            with self.assertRaises(ValueError):
                ru("../evil", milestone_id="m1")

    def test_halt_derives_pause_reason_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            def fake(charter, *, run_dir, loop_id, subsprint_id, clock, **kw):
                cps = os.path.join(run_dir, "docs", "checkpoints")
                os.makedirs(cps, exist_ok=True)
                open(os.path.join(
                    cps, "20260620-000001__acceptance_fix_required__s1.md"), "w").close()
                return {"final_state": "halted", "spawn_count": 1}
            ru = cp.make_run_unit({}, d, "camp-1", clock=_clock(), run_loop_fn=fake)
            out = ru("s1", milestone_id="m1")
            self.assertEqual(out["final_state"], "halted")
            self.assertEqual(out["pause_reason"], "acceptance_fix_required")

    def test_gate_hard_fail_becomes_paused_unit_not_crash(self):
        import driver as drv  # noqa: E402
        with tempfile.TemporaryDirectory() as d:
            def fake(charter, *, run_dir, loop_id, subsprint_id, clock, **kw):
                raise drv.GateHardFail("boom", state="gate_pending")
            ru = cp.make_run_unit({}, d, "camp-1", clock=_clock(), run_loop_fn=fake)
            out = ru("s1", milestone_id="m1")     # MUST NOT raise
            self.assertEqual(out["final_state"], "halted")
            self.assertEqual(out["pause_reason"], "gate_hard_fail")


if __name__ == "__main__":
    unittest.main()
