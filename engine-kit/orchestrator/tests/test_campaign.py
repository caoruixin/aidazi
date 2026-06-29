"""Tests for the Campaign loop (P-B; design §5). stdlib unittest; offline (a fake
`run_unit` — no Driver, no adapters)."""
import ast
import json
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
    """`script` maps subsprint_id → summary dict (final_state, spawn_count, …).
    Accepts (ignores) the `subsprint_sequence` the campaign passes for per-milestone
    derivation — the fake bypasses the real Driver, so it needs no charter projection."""
    def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                 resume=False, functional_acceptance=None, repo_dir=None):
        return dict(script[subsprint_id])
    return run_unit


def _seq_run_unit(seqs, record=None):
    """`seqs` maps subsprint_id → LIST of summaries consumed one per call (so a
    re-dispatch/resume returns the next one). `record` (if given) logs each call's
    (subsprint_id, resume, subsprint_sequence) so a test can assert Mechanism-A
    resume=True and that the campaign passes the milestone's live sequence."""
    counters: dict = {}
    def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                 resume=False, functional_acceptance=None, repo_dir=None):
        i = counters.get(subsprint_id, 0)
        counters[subsprint_id] = i + 1
        if record is not None:
            record.append({"subsprint_id": subsprint_id, "resume": resume,
                           "subsprint_sequence": subsprint_sequence})
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

    def test_milestone_merge_dispatch(self):
        self.assertEqual(cp.interpret_dispatch("milestone_merge",
                                               {"choice": "merge_now"}),
                         cp.ACT_ADVANCE_MILESTONE)
        self.assertEqual(cp.interpret_dispatch("milestone_merge",
                                               {"choice": "abort"}), cp.ACT_END)

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


class TestAcceptanceCleanupRequired(unittest.TestCase):
    """acceptance_cleanup_required: Acceptance PASSED but a selected cleanup operation
    failed, so the Driver HALTS shipping (driver.py ~4106). It is a STATE_HALTED
    Human-decision DISPATCH checkpoint — NOT driver-resume, NOT auto-advancing.

      * retry_cleanup           -> ACT_REDISPATCH_FRESH: re-run the SAME unit FRESH, so
                                   it must RE-SATISFY Acceptance closure (re-run accept).
      * accept_residue_and_ship -> ships ONLY on a COMPLETE, audited waiver
                                   (residue + rationale + evidence + a waiver marker);
                                   an incomplete waiver FAILS CLOSED (surface, no ship).
      * abort                   -> ACT_END.
      * unknown / missing       -> fail-closed surface (ACT_DELIVER_FOLLOWUP)."""

    def _resolver(self, mapping):
        return lambda reason, checkpoint: mapping.get(reason)

    def _events(self, ledger, type_):
        return [e for e in audit.read_events(ledger) if e["type"] == type_]

    # ---- classification ------------------------------------------------- #
    def test_classified_as_dispatch_checkpoint(self):
        self.assertIn("acceptance_cleanup_required", cp.DISPATCH_CHECKPOINTS)
        self.assertEqual(cp.classify_checkpoint("acceptance_cleanup_required"),
                         cp.RESUME_DISPATCH)

    # ---- interpret_dispatch (pure) -------------------------------------- #
    def test_retry_cleanup_maps_to_redispatch_fresh(self):
        self.assertEqual(
            cp.interpret_dispatch("acceptance_cleanup_required",
                                  {"choice": "retry_cleanup"}),
            cp.ACT_REDISPATCH_FRESH)

    def test_abort_maps_to_end(self):
        self.assertEqual(
            cp.interpret_dispatch("acceptance_cleanup_required", {"choice": "abort"}),
            cp.ACT_END)

    def test_accept_residue_with_complete_waiver_advances(self):
        base = {"choice": "accept_residue_and_ship", "residue": ["leftover-db"],
                "rationale": "non-blocking", "evidence": "evidence.json"}
        # waiver_id OR waiver:true are both valid waiver markers.
        self.assertEqual(
            cp.interpret_dispatch("acceptance_cleanup_required",
                                  {**base, "waiver_id": "WV-1"}),
            cp.ACT_ADVANCE_MILESTONE)
        self.assertEqual(
            cp.interpret_dispatch("acceptance_cleanup_required",
                                  {**base, "waiver": True}),
            cp.ACT_ADVANCE_MILESTONE)

    def test_accept_residue_without_waiver_fails_closed(self):
        # a bare choice (no waiver fields) MUST NOT ship.
        self.assertEqual(
            cp.interpret_dispatch("acceptance_cleanup_required",
                                  {"choice": "accept_residue_and_ship"}),
            cp.ACT_DELIVER_FOLLOWUP)

    def test_accept_residue_partial_waiver_fails_closed(self):
        # each missing component (evidence; rationale; the waiver marker) fail-closes.
        for partial in (
                {"residue": ["r"], "rationale": "x", "waiver_id": "w"},     # no evidence
                {"residue": ["r"], "evidence": "e", "waiver_id": "w"},      # no rationale
                {"residue": ["r"], "rationale": "x", "evidence": "e"}):     # no marker
            self.assertEqual(
                cp.interpret_dispatch("acceptance_cleanup_required",
                                      {"choice": "accept_residue_and_ship", **partial}),
                cp.ACT_DELIVER_FOLLOWUP, partial)

    def test_unknown_choice_fails_closed(self):
        self.assertEqual(
            cp.interpret_dispatch("acceptance_cleanup_required", {"choice": "mystery"}),
            cp.ACT_DELIVER_FOLLOWUP)

    def test_missing_choice_fails_closed(self):
        self.assertEqual(cp.interpret_dispatch("acceptance_cleanup_required", {}),
                         cp.ACT_DELIVER_FOLLOWUP)
        self.assertEqual(cp.interpret_dispatch("acceptance_cleanup_required", None),
                         cp.ACT_DELIVER_FOLLOWUP)

    def test_residue_waiver_helper(self):
        complete = {"residue": ["r"], "rationale": "x", "evidence": "e",
                    "waiver_id": "w"}
        # the normalized payload records BOTH marker forms (waiver bool + waiver_id) so a
        # `waiver: true` marker is never lost (Codex blocking 2). waiver_id-only ⇒
        # waiver:False; the boolean marker (no waiver_id) ⇒ waiver:True, waiver_id:None.
        self.assertEqual(
            cp.residue_waiver(complete),
            {"residue": ["r"], "rationale": "x", "evidence": "e",
             "waiver": False, "waiver_id": "w"})
        self.assertEqual(
            cp.residue_waiver({"residue": ["r"], "rationale": "x", "evidence": "e",
                               "waiver": True}),
            {"residue": ["r"], "rationale": "x", "evidence": "e",
             "waiver": True, "waiver_id": None})
        self.assertIsNone(cp.residue_waiver({**complete, "evidence": ""}))   # blank field
        self.assertIsNone(cp.residue_waiver({"residue": ["r"], "rationale": "x",
                                             "evidence": "e"}))               # no marker
        self.assertIsNone(cp.residue_waiver(None))
        # shape sanity (Codex concern B): a truthy-but-MALFORMED field fails closed —
        # residue must be a NON-EMPTY list of NON-EMPTY strings; rationale a string.
        self.assertIsNone(cp.residue_waiver({**complete, "residue": "r"}))   # bare string
        self.assertIsNone(cp.residue_waiver({**complete, "residue": []}))    # empty list
        self.assertIsNone(cp.residue_waiver({**complete, "residue": [""]}))  # blank item
        self.assertIsNone(cp.residue_waiver({**complete, "rationale": 5}))   # non-string

    # ---- full run() flow ------------------------------------------------ #
    def test_run_retry_cleanup_reruns_acceptance_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            rec = []
            ru = _seq_run_unit({"s1": [
                {"final_state": "halted", "spawn_count": 1,
                 "pause_reason": "acceptance_cleanup_required"},
                {"final_state": "done", "spawn_count": 1}]}, rec)
            cp.run_campaign(plan, d, ru, clock=_clock())
            self.assertEqual(rec[0]["resume"], False)
            resumed = cp.run_campaign(
                plan, d, ru, clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"acceptance_cleanup_required": {"choice": "retry_cleanup"}}))
            self.assertEqual(resumed.status, cp.STATUS_DONE)
            # Re-dispatched the SAME unit FRESH (resume=False): a fresh run re-runs the
            # whole sub-sprint incl. Acceptance closure — NOT a driver-resume that would
            # skip back into the halt.
            self.assertEqual(len(rec), 2)
            self.assertEqual(rec[-1]["subsprint_id"], "s1")
            self.assertFalse(rec[-1]["resume"])

    def test_run_retry_cleanup_re_requires_acceptance_can_re_halt(self):
        # cleanup fails AGAIN -> the re-dispatched unit re-halts at the SAME gate: proof
        # the unit stays NOT-closed until Acceptance closure is re-satisfied.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            ru = _seq_run_unit({"s1": [
                {"final_state": "halted", "spawn_count": 1,
                 "pause_reason": "acceptance_cleanup_required"},
                {"final_state": "halted", "spawn_count": 1,
                 "pause_reason": "acceptance_cleanup_required"}]})
            cp.run_campaign(plan, d, ru, clock=_clock())
            again = cp.run_campaign(
                plan, d, ru, clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"acceptance_cleanup_required": {"choice": "retry_cleanup"}}))
            self.assertEqual(again.status, cp.STATUS_PAUSED)
            self.assertEqual(again.pause_reason, "acceptance_cleanup_required")

    def test_run_accept_residue_with_waiver_advances_and_audits(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([
                {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_cleanup_required"},
                      "s2": {"final_state": "done", "spawn_count": 1}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            waiver = {"choice": "accept_residue_and_ship",
                      "residue": ["browser-profile-dir"],
                      "rationale": "residue is a non-blocking dev artifact",
                      "evidence": "docs/evidence/cleanup-status.json",
                      "waiver_id": "WV-7"}
            camp = cp.Campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = camp.run(resume=True, decision_resolver=self._resolver(
                {"acceptance_cleanup_required": waiver}))
            self.assertEqual(resumed.status, cp.STATUS_DONE)
            self.assertEqual(resumed.milestone_index, 2)   # advanced m1 -> m2 -> done
            waived = self._events(camp.audit_ledger,
                                  "campaign_acceptance_residue_waived")
            self.assertEqual(len(waived), 1)               # audited exactly once
            p = waived[0]["payload"]
            self.assertEqual(p["residue"], ["browser-profile-dir"])
            self.assertEqual(p["rationale"], "residue is a non-blocking dev artifact")
            self.assertEqual(p["evidence"], "docs/evidence/cleanup-status.json")
            self.assertEqual(p["waiver_id"], "WV-7")
            self.assertTrue(audit.verify_chain(camp.audit_ledger).ok)

    def test_run_accept_residue_without_waiver_does_not_ship(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([
                {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_cleanup_required"},
                      "s2": {"final_state": "done", "spawn_count": 1}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            camp = cp.Campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = camp.run(resume=True, decision_resolver=self._resolver(
                {"acceptance_cleanup_required": {"choice": "accept_residue_and_ship"}}))
            # fail-closed: NO ship — surfaces a Deliver follow-up; milestone NOT advanced.
            self.assertEqual(resumed.status, cp.STATUS_PAUSED)
            self.assertEqual(resumed.pause_reason, "deliver_followup_required")
            self.assertEqual(resumed.milestone_index, 0)
            self.assertEqual(self._events(camp.audit_ledger,
                                          "campaign_acceptance_residue_waived"), [])

    def test_run_abort_ends_campaign(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_cleanup_required"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"acceptance_cleanup_required": {"choice": "abort"}}))
            self.assertEqual(resumed.status, cp.STATUS_ENDED)

    def test_run_unknown_choice_surfaces(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_cleanup_required"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"acceptance_cleanup_required": {"choice": "huh"}}))
            self.assertEqual(resumed.status, cp.STATUS_PAUSED)
            self.assertEqual(resumed.pause_reason, "deliver_followup_required")

    def test_run_no_decision_repauses(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_cleanup_required"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock(),
                                      resume=True, decision_resolver=None)
            self.assertEqual(resumed.status, cp.STATUS_PAUSED)
            self.assertEqual(resumed.pause_reason, "acceptance_cleanup_required")

    def test_run_waiver_ship_is_idempotent_on_replay(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([
                {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_cleanup_required"},
                      "s2": {"final_state": "done", "spawn_count": 1}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            waiver = {"choice": "accept_residue_and_ship", "residue": ["r"],
                      "rationale": "ok", "evidence": "e.json", "waiver_id": "WV-9"}
            resolver = self._resolver({"acceptance_cleanup_required": waiver})
            first = cp.Campaign(plan, d, _fake_run_unit(script),
                                clock=_clock()).run(resume=True, decision_resolver=resolver)
            self.assertEqual(first.status, cp.STATUS_DONE)
            self.assertEqual(first.milestone_index, 2)
            # Re-apply the SAME resolved decision: a no-op (DONE short-circuits) — NO
            # double-advance and NO double-audit.
            camp2 = cp.Campaign(plan, d, _fake_run_unit(script), clock=_clock())
            second = camp2.run(resume=True, decision_resolver=resolver)
            self.assertEqual(second.status, cp.STATUS_DONE)
            self.assertEqual(second.milestone_index, 2)
            self.assertEqual(
                len(self._events(camp2.audit_ledger,
                                 "campaign_acceptance_residue_waived")), 1)
            self.assertTrue(audit.verify_chain(camp2.audit_ledger).ok)

    def test_run_accept_residue_with_boolean_marker_ships_and_audits_marker(self):
        # Blocking 2: a complete waiver using the BOOLEAN marker (waiver:true, NO
        # waiver_id) ships AND the audit records the marker form (waiver:true) — not an
        # un-attributable waiver_id:None with the marker dropped.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([
                {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_cleanup_required"},
                      "s2": {"final_state": "done", "spawn_count": 1}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            waiver = {"choice": "accept_residue_and_ship",
                      "residue": ["browser-profile-dir"], "rationale": "non-blocking",
                      "evidence": "docs/evidence/cleanup-status.json", "waiver": True}
            camp = cp.Campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = camp.run(resume=True, decision_resolver=self._resolver(
                {"acceptance_cleanup_required": waiver}))
            self.assertEqual(resumed.status, cp.STATUS_DONE)
            self.assertEqual(resumed.milestone_index, 2)
            waived = self._events(camp.audit_ledger,
                                  "campaign_acceptance_residue_waived")
            self.assertEqual(len(waived), 1)
            p = waived[0]["payload"]
            self.assertIs(p["waiver"], True)         # the boolean marker is recorded
            self.assertIsNone(p["waiver_id"])        # no waiver_id was authored
            self.assertEqual(p["residue"], ["browser-profile-dir"])
            self.assertTrue(audit.verify_chain(camp.audit_ledger).ok)

    def test_run_partial_waiver_each_missing_field_does_not_ship(self):
        # Fail-closed: a partial waiver missing ANY one component (residue, rationale,
        # evidence, or the marker — here waiver_id is the only marker) does NOT ship — it
        # surfaces a Deliver follow-up, never advances, and writes NO waiver audit.
        complete = {"choice": "accept_residue_and_ship", "residue": ["r"],
                    "rationale": "ok", "evidence": "e.json", "waiver_id": "WV-1"}
        for drop in ("residue", "rationale", "evidence", "waiver_id"):
            with tempfile.TemporaryDirectory() as d:
                plan = _plan([
                    {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                    {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
                script = {"s1": {"final_state": "halted", "spawn_count": 1,
                                 "pause_reason": "acceptance_cleanup_required"},
                          "s2": {"final_state": "done", "spawn_count": 1}}
                cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
                partial = {k: v for k, v in complete.items() if k != drop}
                camp = cp.Campaign(plan, d, _fake_run_unit(script), clock=_clock())
                resumed = camp.run(resume=True, decision_resolver=self._resolver(
                    {"acceptance_cleanup_required": partial}))
                self.assertEqual(resumed.status, cp.STATUS_PAUSED, drop)
                self.assertEqual(resumed.pause_reason, "deliver_followup_required", drop)
                self.assertEqual(resumed.milestone_index, 0, drop)
                self.assertEqual(self._events(camp.audit_ledger,
                                              "campaign_acceptance_residue_waived"),
                                 [], drop)

    def test_run_malformed_truthy_residue_does_not_ship(self):
        # Concern B (run level): a truthy-but-MALFORMED residue (a bare string, not a
        # list) fails the shape gate and does NOT ship — the programmatic resolver path
        # is not schema-pre-validated, so residue_waiver is the fail-closed guard.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([
                {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_cleanup_required"},
                      "s2": {"final_state": "done", "spawn_count": 1}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            bad = {"choice": "accept_residue_and_ship", "residue": "leftover",
                   "rationale": "ok", "evidence": "e.json", "waiver_id": "WV-1"}
            camp = cp.Campaign(plan, d, _fake_run_unit(script), clock=_clock())
            resumed = camp.run(resume=True, decision_resolver=self._resolver(
                {"acceptance_cleanup_required": bad}))
            self.assertEqual(resumed.status, cp.STATUS_PAUSED)
            self.assertEqual(resumed.pause_reason, "deliver_followup_required")
            self.assertEqual(resumed.milestone_index, 0)
            self.assertEqual(self._events(camp.audit_ledger,
                                          "campaign_acceptance_residue_waived"), [])

    def test_waiver_ship_crash_after_audit_before_save_is_idempotent(self):
        # Blocking 3: a crash AFTER _handle_resume emitted the dispatch + waiver audits
        # and durably advanced the cursor (the §3.5c barrier), but BEFORE the next
        # milestone records a terminal state, must REPLAY idempotently — NO double-advance
        # and NO second waiver audit. The crash is simulated by raising from the m2
        # dispatch (which runs right after the barrier+audits), then replaying.
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()   # shared so the cross-resume ledger stays monotonic
            plan = _plan([
                {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            calls = {"s2": 0}

            def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                         resume=False, functional_acceptance=None, repo_dir=None):
                if subsprint_id == "s1":
                    return {"final_state": "halted", "spawn_count": 1,
                            "pause_reason": "acceptance_cleanup_required"}
                calls["s2"] += 1
                if calls["s2"] == 1:
                    raise RuntimeError("simulated crash after barrier + audits")
                return {"final_state": "done", "spawn_count": 1}

            cp.run_campaign(plan, d, run_unit, clock=clk)   # → m1 cleanup pause
            waiver = {"choice": "accept_residue_and_ship", "residue": ["r"],
                      "rationale": "ok", "evidence": "e.json", "waiver_id": "WV-3"}
            resolver = self._resolver({"acceptance_cleanup_required": waiver})

            # resume → ships m1 (barrier advances to m2 + emits the waiver audit), then the
            # m2 dispatch raises: the barrier state + audits are already durable on disk.
            with self.assertRaises(RuntimeError):
                cp.Campaign(plan, d, run_unit, clock=clk).run(
                    resume=True, decision_resolver=resolver)
            with open(os.path.join(d, "campaign-state.json")) as fh:
                mid = json.load(fh)
            self.assertEqual(mid["status"], cp.STATUS_RUNNING)         # barrier landed
            self.assertEqual(mid["cursor"]["milestone_index"], 1)     # advanced once
            self.assertIsNone(mid["pause_reason"])                    # pause cleared
            ledger = os.path.join(d, "audit", os.listdir(os.path.join(d, "audit"))[0])
            self.assertEqual(
                len(self._events(ledger, "campaign_acceptance_residue_waived")), 1)

            # replay → STATUS_RUNNING crash-recovery re-dispatches m2 (NOT _handle_resume)
            # → DONE. No double-advance (milestone_index 2, not 3); NO second waiver audit.
            camp2 = cp.Campaign(plan, d, run_unit, clock=clk)
            final = camp2.run(resume=True)
            self.assertEqual(final.status, cp.STATUS_DONE)
            self.assertEqual(final.milestone_index, 2)
            self.assertEqual(
                len(self._events(camp2.audit_ledger,
                                 "campaign_acceptance_residue_waived")), 1)
            self.assertTrue(audit.verify_chain(camp2.audit_ledger).ok)


class TestCampaignCrashRecovery(unittest.TestCase):
    """§3.5c STATUS_RUNNING crash recovery (design §3.5c; Codex impl-review MAJOR-2).
    Two branches: (1) the cursor unit was ALREADY run + accounted + appended (a crash
    between the pause-branch save and the _pause finalize) → REPLAY from the recorded
    final_state, with NO run_unit re-dispatch and NO double-account; (2) the cursor
    unit was NOT yet recorded (a crash mid-run) → re-dispatch run_unit with resume=True
    and account EXACTLY once."""

    def test_already_recorded_unit_replays_no_redispatch_no_double_account(self):
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()   # shared so the cross-resume audit ledger stays monotonic
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s2"]}])
            # s1 advances; s2 HALTS at an advisory sign-off → s2 is recorded + accounted,
            # then the campaign pauses (subsprints_run=2, total_spawns=2+3=5).
            script = {"s1": {"final_state": "advance", "spawn_count": 2, "loop_id": "l1"},
                      "s2": {"final_state": "halted", "spawn_count": 3, "loop_id": "l2",
                             "pause_reason": "advisory_acceptance_pass_signoff",
                             "checkpoint_path": "docs/checkpoints/s2.md"}}
            paused = cp.run_campaign(plan, d, _fake_run_unit(script), clock=clk)
            self.assertEqual(paused.status, cp.STATUS_PAUSED)
            self.assertEqual(paused.pause_reason, "advisory_acceptance_pass_signoff")
            self.assertEqual((paused.subsprints_run, paused.total_spawns), (2, 5))
            # The recorded cursor unit (s2) now carries the pause_reason + checkpoint_path
            # the replay re-pauses from (the MAJOR-2 fix persists them into the record).
            rec = paused.units[-1]
            self.assertEqual(rec["subsprint_id"], "s2")
            self.assertEqual(rec["pause_reason"], "advisory_acceptance_pass_signoff")
            self.assertEqual(rec["checkpoint_path"], "docs/checkpoints/s2.md")

            # Rewind the PERSISTED state into the crash window: the pause-branch _save()
            # wrote status=RUNNING + the recorded s2 unit, but the _pause finalize (which
            # sets STATUS_PAUSED) never landed before the crash.
            sp = os.path.join(d, "campaign-state.json")
            with open(sp) as fh:
                st = json.load(fh)
            st["status"] = cp.STATUS_RUNNING
            st["pause_reason"] = None
            st["pause_checkpoint"] = None
            with open(sp, "w") as fh:
                json.dump(st, fh)

            # Resume with a TRIPWIRE run_unit: it records every dispatch and would return
            # an ADVANCING summary if called — so a re-dispatch would visibly advance the
            # cursor + grow the accounting instead of re-pausing.
            calls = []
            def tripwire(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                         resume=False, functional_acceptance=None):
                calls.append(subsprint_id)
                return {"final_state": "advance", "spawn_count": 99,
                        "loop_id": "REDISPATCH"}
            resumed = cp.run_campaign(plan, d, tripwire, clock=clk, resume=True)

            # (1) NO re-dispatch — run_unit was never called during the replay.
            self.assertEqual(calls, [], "the recorded cursor unit must NOT be re-dispatched")
            # (2) Replayed from the recorded final_state → re-paused at the SAME reason +
            #     checkpoint, re-derived from the unit record (NOT from a re-run).
            self.assertEqual(resumed.status, cp.STATUS_PAUSED)
            self.assertEqual(resumed.pause_reason, "advisory_acceptance_pass_signoff")
            self.assertEqual(resumed.pause_checkpoint, "docs/checkpoints/s2.md")
            # (3) NO double-account and NO duplicate append.
            self.assertEqual((resumed.subsprints_run, resumed.total_spawns), (2, 5))
            self.assertEqual([u["subsprint_id"] for u in resumed.units], ["s1", "s2"])
            # (4) the append-only ledger still verifies after the replay re-emit.
            ledger = os.path.join(d, "audit", os.listdir(os.path.join(d, "audit"))[0])
            self.assertTrue(audit.verify_chain(ledger).ok)

    def test_in_flight_unit_not_yet_recorded_redispatches_with_resume_true(self):
        # The §3.5c "else" branch: a crash BEFORE the cursor unit was recorded → the unit
        # is re-dispatched with resume=True (idempotent Driver re-entry) and accounted
        # EXACTLY once (no fresh restart, no double-count).
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            rec = []
            seqs = {"s1": [{"final_state": "done", "spawn_count": 4, "loop_id": "l1"}]}
            # Seed a mid-flight RUNNING state with NOTHING recorded yet (the crash window
            # before the unit's branch save).
            seed = cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())
            seed.state.status = cp.STATUS_RUNNING
            seed.state.pause_reason = None
            seed._save()
            resumed = cp.Campaign(plan, d, _seq_run_unit(seqs, rec),
                                  clock=_clock()).run(resume=True)
            self.assertEqual(resumed.status, cp.STATUS_DONE)
            self.assertEqual(rec[-1]["resume"], True,
                             "an unrecorded in-flight unit re-dispatches with resume=True")
            self.assertEqual((resumed.subsprints_run, resumed.total_spawns), (1, 4),
                             "accounted exactly once")
            self.assertEqual([u["subsprint_id"] for u in resumed.units], ["s1"])

    def test_persisted_state_with_halted_unit_validates_against_schema(self):
        # Runtime↔schema sync: the persisted campaign-state.json — INCLUDING a halted
        # unit's §3.5c pause_reason + checkpoint_path — must conform to
        # schemas/campaign-state.schema.json (units.items is additionalProperties:false,
        # so a persisted field the schema doesn't declare would diverge fail-closed).
        from jsonschema import Draft202012Validator
        schema_path = os.path.abspath(
            os.path.join(_ENGINE_KIT_DIR, os.pardir, "schemas",
                         "campaign-state.schema.json"))
        with open(schema_path, encoding="utf-8") as fh:
            schema = json.load(fh)
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s2"]}])
            script = {"s1": {"final_state": "advance", "spawn_count": 2, "loop_id": "l1"},
                      "s2": {"final_state": "halted", "spawn_count": 3, "loop_id": "l2",
                             "pause_reason": "advisory_acceptance_pass_signoff",
                             "checkpoint_path": "docs/checkpoints/s2.md"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            with open(os.path.join(d, "campaign-state.json"), encoding="utf-8") as fh:
                persisted = json.load(fh)
            halted = [u for u in persisted["units"] if u["status"] == "halted"]
            self.assertTrue(
                halted and halted[-1].get("pause_reason")
                and halted[-1].get("checkpoint_path"),
                "the halted unit must carry the §3.5c replay fields")
            errs = [e.message
                    for e in Draft202012Validator(schema).iter_errors(persisted)]
            self.assertEqual(errs, [], f"persisted state diverges from schema: {errs}")


class TestCampaignFailClosedIngress(unittest.TestCase):
    """Fail-closed campaign-tier I/O: the plan (admitted at construction) and the
    persisted state (admitted on resume) are validated against their JSON schemas
    BEFORE they drive the outer loop — a malformed plan or a corrupted state.json
    raises rather than silently degrading (delivery-loop §4.2.7 discipline)."""

    def test_malformed_plan_missing_goal_rejected_at_construction(self):
        with tempfile.TemporaryDirectory() as d:
            bad = {"campaign_id": "camp-1",
                   "milestones": [{"id": "m1", "objective": "a"}]}  # no `goal`
            with self.assertRaises(ValueError) as ctx:
                cp.Campaign(bad, d, _fake_run_unit({}), clock=_clock())
            self.assertIn("schema validation", str(ctx.exception))

    def test_plan_with_unknown_top_level_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            bad = _plan([{"id": "m1", "objective": "a"}])
            bad["surprise"] = True  # plan root is additionalProperties:false
            with self.assertRaises(ValueError):
                cp.Campaign(bad, d, _fake_run_unit({}), clock=_clock())

    def test_milestone_missing_objective_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            bad = _plan([{"id": "m1"}])  # a milestone requires id + objective
            with self.assertRaises(ValueError):
                cp.Campaign(bad, d, _fake_run_unit({}), clock=_clock())

    def test_corrupted_persisted_state_rejected_on_resume(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}])
            cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())._save()
            sp = os.path.join(d, "campaign-state.json")
            with open(sp) as fh:
                st = json.load(fh)
            st["status"] = "bogus"  # not in the status enum
            with open(sp, "w") as fh:
                json.dump(st, fh)
            with self.assertRaises(ValueError) as ctx:
                cp.Campaign(plan, d, _fake_run_unit({}),
                            clock=_clock()).run(resume=True)
            self.assertIn("schema validation", str(ctx.exception))

    def test_state_for_different_campaign_rejected_on_resume(self):
        # A schema-valid state whose campaign_id belongs to ANOTHER campaign must not
        # drive THIS plan (state↔plan binding, like the Driver's loop_id binding).
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}], campaign_id="camp-A")
            cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())._save()
            sp = os.path.join(d, "campaign-state.json")
            with open(sp) as fh:
                st = json.load(fh)
            st["campaign_id"] = "camp-B"  # schema-valid id, but a different campaign
            with open(sp, "w") as fh:
                json.dump(st, fh)
            with self.assertRaises(ValueError) as ctx:
                cp.Campaign(plan, d, _fake_run_unit({}),
                            clock=_clock()).run(resume=True)
            self.assertIn("does not match", str(ctx.exception))

    def test_out_of_range_cursor_rejected_on_resume(self):
        # A schema-valid cursor that points PAST the backlog must be rejected rather
        # than silently completing the campaign (the Codex-flagged silent-done bug):
        # `while milestone_index < len(milestones)` would otherwise fall through.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}])
            cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())._save()
            sp = os.path.join(d, "campaign-state.json")
            with open(sp) as fh:
                st = json.load(fh)
            st["status"] = "running"
            st["cursor"]["milestone_index"] = 5  # the plan has 1 milestone
            with open(sp, "w") as fh:
                json.dump(st, fh)
            with self.assertRaises(ValueError) as ctx:
                cp.Campaign(plan, d, _fake_run_unit({}),
                            clock=_clock()).run(resume=True)
            self.assertIn("out-of-range", str(ctx.exception))

    def test_boundary_cursor_without_units_rejected_on_resume(self):
        # The Codex-flagged hole: a boundary cursor (subsprint_index == len(seq)) with
        # NO completed units behind it would fall through the inner loop and skip the
        # milestone. The cursor must be backed by the unit ledger.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s2"]}])
            cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())._save()
            sp = os.path.join(d, "campaign-state.json")
            with open(sp) as fh:
                st = json.load(fh)
            st["status"] = "running"
            st["cursor"]["subsprint_index"] = 2  # == len(seq), but units is empty
            with open(sp, "w") as fh:
                json.dump(st, fh)
            with self.assertRaises(ValueError) as ctx:
                cp.Campaign(plan, d, _fake_run_unit({}),
                            clock=_clock()).run(resume=True)
            self.assertIn("cursor/ledger", str(ctx.exception))

    def test_paused_at_backlog_end_rejected_on_resume(self):
        # A paused campaign pauses INSIDE a milestone — it can never sit at the
        # backlog end. A tampered paused/done-boundary state is rejected.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}])
            cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())._save()
            sp = os.path.join(d, "campaign-state.json")
            with open(sp) as fh:
                st = json.load(fh)
            st["status"] = "paused"
            st["cursor"]["milestone_index"] = 1  # == len(milestones)
            st["cursor"]["subsprint_index"] = 0
            # m1 has a recorded unit (so the prefix check passes) — isolate the
            # paused-at-backlog-end rejection.
            st["units"] = [{"milestone_id": "m1", "subsprint_id": "s1",
                            "status": "done", "final_state": "advance"}]
            with open(sp, "w") as fh:
                json.dump(st, fh)
            with self.assertRaises(ValueError) as ctx:
                cp.Campaign(plan, d, _fake_run_unit({}),
                            clock=_clock()).run(resume=True)
            self.assertIn("backlog end", str(ctx.exception))

    def test_cursor_skipping_incomplete_prefix_milestone_rejected(self):
        # mi points at milestone 2 but milestone 1 has NO completion evidence in the
        # ledger → resuming there would silently skip milestone 1's work.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                          {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())._save()
            sp = os.path.join(d, "campaign-state.json")
            with open(sp) as fh:
                st = json.load(fh)
            st["status"] = "running"
            st["cursor"]["milestone_index"] = 1  # jump to m2 with no m1 units
            with open(sp, "w") as fh:
                json.dump(st, fh)
            with self.assertRaises(ValueError) as ctx:
                cp.Campaign(plan, d, _fake_run_unit({}),
                            clock=_clock()).run(resume=True)
            self.assertIn("skips milestone", str(ctx.exception))

    def test_done_status_without_full_backlog_evidence_rejected(self):
        # status=done but the cursor has not reached the backlog end (no completion
        # evidence) → run(resume) would otherwise return immediately, skipping work.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}])
            cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())._save()
            sp = os.path.join(d, "campaign-state.json")
            with open(sp) as fh:
                st = json.load(fh)
            st["status"] = "done"  # claims done at mi=0, units empty
            with open(sp, "w") as fh:
                json.dump(st, fh)
            with self.assertRaises(ValueError) as ctx:
                cp.Campaign(plan, d, _fake_run_unit({}),
                            clock=_clock()).run(resume=True)
            self.assertIn("'done'", str(ctx.exception))

    def test_legit_multi_milestone_resume_is_not_false_rejected(self):
        # A genuine resume across a completed milestone: m1 fully advanced (cursor at
        # m2). The prefix check must ACCEPT it (m1 is complete in the ledger).
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                          {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            camp = cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())
            camp.state.status = cp.STATUS_RUNNING
            camp.state.milestone_index = 1            # m1 done, now on m2
            camp.state.subsprint_index = 0
            camp.state.units = [{"milestone_id": "m1", "subsprint_id": "s1",
                                 "status": "done", "final_state": "advance"}]
            camp._save()
            done = {"s2": {"final_state": "done", "spawn_count": 1}}
            resumed = cp.Campaign(plan, d, _fake_run_unit(done),
                                  clock=_clock()).run(resume=True)
            self.assertEqual(resumed.status, cp.STATUS_DONE)

    def test_legit_advance_boundary_with_units_resumes(self):
        # The == len boundary IS legal when backed by advanced units (the crash window
        # after the last sub-sprint advanced, before the milestone-reset save): it must
        # NOT be rejected — it resumes by falling through to the next milestone/done.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}])
            camp = cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())
            camp.state.status = cp.STATUS_RUNNING
            camp.state.subsprint_index = 1  # == len(seq), backed by one advanced unit
            camp.state.units = [{"milestone_id": "m1", "subsprint_id": "s1",
                                 "status": "done", "final_state": "advance"}]
            camp._save()
            resumed = cp.Campaign(plan, d, _fake_run_unit({}),
                                  clock=_clock()).run(resume=True)
            self.assertEqual(resumed.status, cp.STATUS_DONE)

    def test_cursor_past_halted_unit_not_false_rejected(self):
        # A human-resolved ACT_ADVANCE_SUBSPRINT (e.g. an accepted review_out_of_scope)
        # advances the cursor PAST a HALTED unit whose final_state is NOT 'advance'. The
        # current-milestone presence check must ACCEPT it (presence, not final_state) —
        # a strict advanced-count equality would false-reject this legitimate resume.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1", "s2"]}])
            camp = cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())
            camp.state.status = cp.STATUS_RUNNING
            camp.state.subsprint_index = 1            # advanced PAST s1 ...
            camp.state.units = [{"milestone_id": "m1", "subsprint_id": "s1",
                                 "status": "halted",
                                 "final_state": "review_out_of_scope"}]  # ... a HALT
            camp._save()
            done = {"s2": {"final_state": "done", "spawn_count": 1}}
            resumed = cp.Campaign(plan, d, _fake_run_unit(done),
                                  clock=_clock()).run(resume=True)
            self.assertEqual(resumed.status, cp.STATUS_DONE)

    def test_valid_plan_round_trips_through_the_gate(self):
        # The gate admits a well-formed plan and round-trips its own saved state.
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a",
                           "subsprint_sequence": ["s1"]}])
            done = {"s1": {"final_state": "done", "spawn_count": 1}}
            final = cp.run_campaign(plan, d, _fake_run_unit(done), clock=_clock())
            self.assertEqual(final.status, cp.STATUS_DONE)


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

    def test_passed_sequence_drives_derivation_and_sidecar(self):
        """The Driver sees the campaign-PASSED milestone sequence (live), NOT the
        charter's original — and a provenance sidecar is written (Codex review #3)."""
        with tempfile.TemporaryDirectory() as d:
            captured = {}
            def fake(charter, *, run_dir, loop_id, subsprint_id, clock, **kw):
                captured["seq"] = (((charter.get("autonomy") or {})
                                    .get("approved_scope") or {}).get("subsprint_sequence"))
                captured["run_dir"] = run_dir
                return {"final_state": "advance", "spawn_count": 0}
            plan = _plan([{"id": "m1", "objective": "x",
                           "subsprint_sequence": ["s1", "s2"]}])
            charter = {"autonomy": {"approved_scope": {"subsprint_sequence": ["ORIG"]}}}
            ru = cp.make_run_unit(charter, d, "camp-1", clock=_clock(),
                                  plan=plan, run_loop_fn=fake)
            ru("s1", milestone_id="m1", subsprint_sequence=["s1", "s2"])
            self.assertEqual(captured["seq"], ["s1", "s2"])    # live, not "ORIG"
            prov = json.load(open(os.path.join(captured["run_dir"],
                                               "derived-context.json")))
            self.assertEqual(prov["subsprint_sequence"], ["s1", "s2"])
            self.assertFalse(prov["customer_signed"])
            self.assertEqual(len(prov["derived_from"]["charter_sha256"]), 64)
            self.assertEqual(len(prov["derived_from"]["campaign_plan_sha256"]), 64)

    def test_dispatched_subsprint_must_be_in_sequence_fail_closed(self):
        """A sub-sprint not in the milestone's sequence can't anchor terminality →
        fail closed (never derive against a sequence this unit isn't part of)."""
        with tempfile.TemporaryDirectory() as d:
            ru = cp.make_run_unit(
                {}, d, "camp-1", clock=_clock(),
                run_loop_fn=lambda *a, **k: {"final_state": "advance", "spawn_count": 0})
            with self.assertRaises(ValueError):
                ru("s9", milestone_id="m1", subsprint_sequence=["s1", "s2"])

    def test_full_chain_guided_loop_mode_is_rejected(self):
        """make_run_unit refuses an explicit non-delivery_only loop_mode: the
        supplied-sequence terminality anchoring is unsound under guided's seq[0]
        bootstrap reset; that per-milestone-decompose mode is deferred (Codex review
        #1; design §6)."""
        with tempfile.TemporaryDirectory() as d:
            for bad in ("full_chain_guided", "some_other_mode"):
                with self.assertRaises(ValueError):
                    cp.make_run_unit({}, d, "camp-1", clock=_clock(),
                                     run_loop_fn=lambda *a, **k: {}, loop_mode=bad)

    def test_derivation_pins_delivery_only_over_a_guided_charter(self):
        """Closes the round-2 falsy-loop_mode hole: a charter carrying
        autonomy.loop_mode=full_chain_guided + an explicit FALSY loop_mode (which the
        construction guard lets pass) must STILL run delivery_only when deriving — the
        derived dispatch pins it, and the Driver ctor loop_mode arg wins over the
        charter (Codex P-B review round-2)."""
        with tempfile.TemporaryDirectory() as d:
            seen = {}
            def fake(charter, *, run_dir, loop_id, subsprint_id, clock,
                     loop_mode=None, **kw):
                seen["loop_mode"] = loop_mode
                return {"final_state": "advance", "spawn_count": 0}
            charter = {"autonomy": {"loop_mode": "full_chain_guided",
                                    "approved_scope": {"subsprint_sequence": ["x"]}}}
            ru = cp.make_run_unit(charter, d, "camp-1", clock=_clock(),
                                  run_loop_fn=fake, loop_mode=None)  # explicit falsy
            ru("s1", milestone_id="m1", subsprint_sequence=["s1"])
            self.assertEqual(seen["loop_mode"], "delivery_only")


class TestDeriveMilestoneContext(unittest.TestCase):
    """derive_milestone_context — the pure per-milestone projection (Codex review)."""

    def _charter(self):
        return {"autonomy": {"level": "human_on_the_loop",
                             "approved_scope": {"subsprint_sequence": ["WHOLE"],
                                                "modules_in_scope": ["a.py"]}},
                "tooling": {"acceptance": {"mode": "auto"}}}

    def test_projects_sequence_without_mutating_source_or_resigning(self):
        charter = self._charter()
        derived, prov = cp.derive_milestone_context(
            charter, "m1", ["s1", "s2"], campaign_id="c1", plan_fingerprint="f" * 64)
        # overrides ONLY the sequence; the source charter is untouched (deep copy).
        self.assertEqual(
            derived["autonomy"]["approved_scope"]["subsprint_sequence"], ["s1", "s2"])
        self.assertEqual(
            charter["autonomy"]["approved_scope"]["subsprint_sequence"], ["WHOLE"])
        # other charter content carried through unchanged.
        self.assertEqual(derived["tooling"], charter["tooling"])
        self.assertEqual(
            derived["autonomy"]["approved_scope"]["modules_in_scope"], ["a.py"])
        # adds NO top-level charter fields (root schema is additionalProperties:false).
        self.assertEqual(set(derived) - set(charter), set())
        # provenance: hashes the SOURCE charter (not the mutated copy); not re-signed.
        self.assertEqual(prov["derived_from"]["charter_sha256"],
                         cp._canonical_sha256(charter))
        self.assertEqual(prov["derived_from"]["campaign_plan_sha256"], "f" * 64)
        self.assertEqual(prov["milestone_id"], "m1")
        self.assertEqual(prov["kind"], "per_milestone_execution_context")
        self.assertFalse(prov["customer_signed"])

    def test_deterministic(self):
        charter = self._charter()
        d1, p1 = cp.derive_milestone_context(charter, "m1", ["s1"],
                                             campaign_id="c1", plan_fingerprint="x")
        d2, p2 = cp.derive_milestone_context(charter, "m1", ["s1"],
                                             campaign_id="c1", plan_fingerprint="x")
        self.assertEqual(d1, d2)
        self.assertEqual(p1, p2)


_STATIC_CHARTER = {"tooling": {"acceptance": {"functional": {"mode": "static"}}}}


def _covms(mid, seq, reqs):
    return {"id": mid, "objective": f"o {mid}", "subsprint_sequence": list(seq),
            "covers_req_ids": list(reqs)}


class TestF1HashSpec(unittest.TestCase):
    """Δ-19 F1 (design §3.3.1): the EXACT signed_scope_hash spec — sha256 over canonical
    JSON of H = {version:'v1', campaign_id, goal, charter_ref, charter_hash, milestones:
    [{id,objective,covers_req_ids,subsprint_sequence,depends_on,
    resolved_functional_acceptance:{mode,source},acceptance_bar}]}; canonical = sorted
    keys, no insignificant whitespace, UTF-8, absent arrays → []."""

    def test_hash_matches_the_exact_spec_object(self):
        import hashlib
        plan = _plan([_covms("m1", ["s1"], ["REQ-1"])], signed_by_human=False)
        H = {"version": "v1", "campaign_id": "camp-1", "goal": "deliver the thing",
             "charter_ref": "ch", "charter_hash": cp._canonical_sha256(_STATIC_CHARTER),
             "milestones": [{"id": "m1", "objective": "o m1",
                             "covers_req_ids": ["REQ-1"], "subsprint_sequence": ["s1"],
                             "depends_on": [],
                             "resolved_functional_acceptance":
                                 {"mode": "static", "source": "charter"},
                             "acceptance_bar": None}]}
        expected = hashlib.sha256(
            json.dumps(H, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")).hexdigest()
        self.assertEqual(
            cp.compute_signed_scope_hash(plan, _STATIC_CHARTER, charter_ref="ch"),
            expected)

    def test_absent_arrays_normalize_to_empty(self):
        # A milestone with no covers/subsprint/depends hashes identically whether the
        # fields are absent or explicitly [].
        bare = _plan([{"id": "m1", "objective": "o m1"}], signed_by_human=False)
        empty = _plan([{"id": "m1", "objective": "o m1", "covers_req_ids": [],
                        "subsprint_sequence": [], "depends_on": []}],
                      signed_by_human=False)
        self.assertEqual(cp.compute_signed_scope_hash(bare, _STATIC_CHARTER),
                         cp.compute_signed_scope_hash(empty, _STATIC_CHARTER))

    def test_scope_edit_changes_the_hash(self):
        a = _plan([_covms("m1", ["s1"], ["REQ-1"])])
        b = _plan([_covms("m1", ["s1"], ["REQ-2"])])   # covers_req_ids changed
        self.assertNotEqual(cp.compute_signed_scope_hash(a, _STATIC_CHARTER),
                            cp.compute_signed_scope_hash(b, _STATIC_CHARTER))


class TestF1SignoffStatus(unittest.TestCase):
    def test_legacy_plan_is_byte_identical(self):
        # No signoff block, no covers_req_ids ⇒ F1 inactive ⇒ legacy bare flag.
        self.assertEqual(cp.signoff_status(
            _plan([{"id": "m1", "objective": "a"}], signed_by_human=True)), "signed")
        self.assertEqual(cp.signoff_status(
            _plan([{"id": "m1", "objective": "a"}], signed_by_human=False)), "unsigned")

    def test_fresh_signed(self):
        signed = cp.stamp_signoff(_plan([_covms("m1", ["s1"], ["REQ-1"])]),
                                  _STATIC_CHARTER, signed_at="t")
        self.assertEqual(cp.signoff_status(signed, _STATIC_CHARTER), "signed")

    def test_edit_after_signoff_is_stale(self):
        signed = cp.stamp_signoff(_plan([_covms("m1", ["s1"], ["REQ-1"])]),
                                  _STATIC_CHARTER, signed_at="t")
        stale = json.loads(json.dumps(signed))
        stale["milestones"][0]["objective"] = "EDITED AFTER SIGNOFF"
        self.assertEqual(cp.signoff_status(stale, _STATIC_CHARTER), "stale")

    def test_pre_f1_bare_flag_with_covers_needs_resign(self):
        # covers_req_ids ⇒ F1 active; bare signed_by_human + no signoff block ⇒ pre_f1.
        plan = _plan([_covms("m1", ["s1"], ["REQ-1"])], signed_by_human=True)
        self.assertEqual(cp.signoff_status(plan, _STATIC_CHARTER), "pre_f1")

    def test_g1_charter_default_flip_is_stale(self):
        # The milestone has NO explicit functional_acceptance ⇒ it inherits the charter
        # default. Flipping that default flips the RESOLVED mode in the envelope ⇒ stale.
        plan = _plan([_covms("m1", ["s1"], ["REQ-1"])])
        signed = cp.stamp_signoff(plan, _STATIC_CHARTER, signed_at="t")
        self.assertEqual(cp.signoff_status(signed, _STATIC_CHARTER), "signed")
        flipped = {"tooling": {"acceptance": {"functional": {"mode": "browser_e2e"}}}}
        self.assertEqual(cp.signoff_status(signed, flipped), "stale")

    def test_empty_covers_array_opts_into_f1(self):
        # Codex R-P2a NB-1: an explicit covers_req_ids:[] is PRESENCE ⇒ F1 active (a
        # non-empty/truthiness test would silently downgrade it to legacy byte-identical).
        plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"],
                       "covers_req_ids": []}], signed_by_human=True)
        self.assertTrue(cp.f1_required(plan))
        self.assertEqual(cp.signoff_status(plan, _STATIC_CHARTER), "pre_f1")

    def test_snapshot_authenticity_catches_tamper(self):
        # Codex R-P2a #2: the stored snapshot must verify against its OWN signed_scope_hash.
        signed = cp.stamp_signoff(_plan([_covms("m1", ["s1"], ["REQ-1"])]),
                                  _STATIC_CHARTER, signed_at="t")
        self.assertTrue(cp.signoff_snapshot_authentic(signed))
        tampered = json.loads(json.dumps(signed))
        # Edit the STORED snapshot (drop coverage) but leave signed_scope_hash untouched.
        tampered["signoff"]["scope_envelope"]["milestones"][0]["covers_req_ids"] = []
        self.assertFalse(cp.signoff_snapshot_authentic(tampered))


class TestF1RunnerIntegration(unittest.TestCase):
    def _ru_done(self):
        return _fake_run_unit({"s1": {"final_state": "done", "spawn_count": 1}})

    def test_fresh_signed_plan_runs(self):
        with tempfile.TemporaryDirectory() as d:
            signed = cp.stamp_signoff(_plan([_covms("m1", ["s1"], ["REQ-1"])]),
                                      _STATIC_CHARTER, signed_at="t")
            st = cp.run_campaign(signed, d, self._ru_done(), clock=_clock(),
                                 charter=_STATIC_CHARTER)
            self.assertEqual(st.status, cp.STATUS_DONE)

    def test_pre_f1_plan_repauses_at_signoff(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([_covms("m1", ["s1"], ["REQ-1"])], signed_by_human=True)
            st = cp.run_campaign(plan, d, self._ru_done(), clock=_clock(),
                                 charter=_STATIC_CHARTER)
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "campaign_plan_signoff")
            self.assertEqual(st.subsprints_run, 0)  # nothing dispatched pre-resign

    def test_stale_plan_repauses_then_resign_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            signed = cp.stamp_signoff(_plan([_covms("m1", ["s1"], ["REQ-1"])]),
                                      _STATIC_CHARTER, signed_at="t")
            stale = json.loads(json.dumps(signed))
            stale["milestones"][0]["objective"] = "EDITED"
            st = cp.run_campaign(stale, d, self._ru_done(), clock=_clock(),
                                 charter=_STATIC_CHARTER)
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "campaign_plan_signoff")
            # Re-sign (re-stamp the snapshot for the EDITED scope) then resume → runs.
            resigned = cp.stamp_signoff(stale, _STATIC_CHARTER, signed_at="t2")
            resumed = cp.run_campaign(resigned, d, self._ru_done(), clock=_clock(),
                                      resume=True, charter=_STATIC_CHARTER)
            self.assertEqual(resumed.status, cp.STATUS_DONE)

    def test_cross_milestone_duplicate_req_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([_covms("m1", ["s1"], ["REQ-1"]),
                          _covms("m2", ["s2"], ["REQ-1"])], signed_by_human=True)
            with self.assertRaises(ValueError) as ctx:
                cp.Campaign(plan, d, self._ru_done(), clock=_clock(),
                            charter=_STATIC_CHARTER)
            self.assertIn("more than one milestone", str(ctx.exception))


class TestLedgerValidationFailClosed(unittest.TestCase):
    def test_invalid_ledger_raises(self):
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "ledger.json")
            with open(led, "w", encoding="utf-8") as fh:
                json.dump({"version": "v1", "requirements": [{"id": "BAD"}]}, fh)
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            with self.assertRaises(ValueError):
                cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock(),
                            ledger_path=led)

    def test_valid_ledger_loads(self):
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "ledger.json")
            with open(led, "w", encoding="utf-8") as fh:
                json.dump({"version": "v1", "requirements": [
                    {"id": "REQ-1", "statement": "x", "source": {"channel": "prd"},
                     "customer_disposition": "accepted"}]}, fh)
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            c = cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock(),
                            ledger_path=led)
            self.assertIsNotNone(c.ledger)


class TestF3MilestoneOutcomes(unittest.TestCase):
    """Δ-19 F3 (design §3.5.1): every terminal-close path stamps the right
    milestone_outcomes[].terminal so scope_report can derive delivery_status."""

    def _terminal(self, st, mid="m1"):
        for o in st.milestone_outcomes:
            if o.get("milestone_id") == mid:
                return o.get("terminal")
        return None

    def _resolver(self, mapping):
        return lambda reason, cp_: mapping.get(reason)

    def test_done_is_acceptance_pass_authoritative(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            st = cp.run_campaign(plan, d, _fake_run_unit(
                {"s1": {"final_state": "done", "spawn_count": 1}}), clock=_clock())
            self.assertEqual(self._terminal(st), "acceptance_pass_authoritative")

    def test_terminal_advance_is_acceptance_off(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            st = cp.run_campaign(plan, d, _fake_run_unit(
                {"s1": {"final_state": "advance", "spawn_count": 1}}), clock=_clock())
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(self._terminal(st), "acceptance_off")

    def test_advisory_ship_is_advisory_pass(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "advisory_acceptance_pass_signoff"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            st = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"advisory_acceptance_pass_signoff": {"choice": "ship"}}))
            self.assertEqual(self._terminal(st), "acceptance_pass_advisory_ship")

    def test_fix_required_confirm_no_is_fix_required_ship(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            st = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"acceptance_fix_required": {"confirm": "no"}}))
            self.assertEqual(self._terminal(st), "fix_required_ship")

    def test_surface_approve_ship(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_surface_approve"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            st = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"acceptance_surface_approve": {"choice": "approve_ship"}}))
            self.assertEqual(self._terminal(st), "surface_approve_ship")

    def test_terminal_review_out_of_scope_accept_is_waived(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            script = {"s1": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "review_out_of_scope"}}
            cp.run_campaign(plan, d, _fake_run_unit(script), clock=_clock())
            st = cp.run_campaign(
                plan, d, _fake_run_unit(script), clock=_clock(), resume=True,
                decision_resolver=self._resolver(
                    {"review_out_of_scope": {"choice": "accept_and_advance"}}))
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(self._terminal(st), "out_of_scope_advance")

    def test_outcomes_persist_and_validate_against_schema(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
                          {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}])
            st = cp.run_campaign(plan, d, _fake_run_unit(
                {"s1": {"final_state": "advance", "spawn_count": 1},
                 "s2": {"final_state": "done", "spawn_count": 1}}), clock=_clock())
            # Re-read the persisted state and schema-validate it (milestone_outcomes is
            # part of the campaign-state contract now).
            with open(os.path.join(d, "campaign-state.json"), encoding="utf-8") as fh:
                persisted = json.load(fh)
            cp._validate_or_raise(persisted, "campaign-state.schema.json", "state")
            terms = {o["milestone_id"]: o["terminal"]
                     for o in persisted["milestone_outcomes"]}
            self.assertEqual(terms, {"m1": "acceptance_off",
                                     "m2": "acceptance_pass_authoritative"})


# --------------------------------------------------------------------------- #
# Track 2 Phase 2-γ / Constitution §1.7-F — pre-authorized in-envelope completeness
# remediation (gap-driven follow-up). The gap-followup engine is a DORMANT, fail-closed
# completeness safety net: it fires ONLY when a requirement ledger is wired, the plan is
# fresh-signed, and the POST-close gap_report (scope_report.build_gap_report, source-
# sealed) is non-empty. Because the happy-path inner loop closes every milestone
# delivered/waived (both EXCLUDED from the gap), the trigger state is constructed directly
# (a covered milestone with no delivered/waived terminal ⇒ its covers stay in_progress ⇒
# in the gap) — exactly the condition the safety net guards.
# --------------------------------------------------------------------------- #
_GF_CHARTER_ONL = {"autonomy": {"level": "human_on_the_loop"},
                   "tooling": {"acceptance": {"functional": {"mode": "static"}}}}
_GF_CHARTER_ITL = {"autonomy": {"level": "human_in_the_loop"},
                   "tooling": {"acceptance": {"functional": {"mode": "static"}}}}


def _ledger(reqs):
    return {"version": "v1", "requirements": [
        {"id": r, "statement": f"stmt {r}", "source": {"channel": "prd"},
         "customer_disposition": "accepted"} for r in reqs]}


def _gap_fake_run_unit(script, record=None):
    """A fake run_unit that ACCEPTS the §1.7-F covered_req_ids kwarg the gap-followup
    dispatch passes (the pre-Phase-2-γ fakes do not — they are never reached without a
    ledger). Records each call so a test can assert the in-envelope covered_req_ids and the
    grown per-milestone sequence."""
    def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                 resume=False, functional_acceptance=None, repo_dir=None,
                 covered_req_ids=None, gap_followup_spec=None, **_kw):
        if record is not None:
            record.append({"subsprint_id": subsprint_id, "milestone_id": milestone_id,
                           "covered_req_ids": covered_req_ids, "resume": resume,
                           "gap_followup_spec": gap_followup_spec,
                           "subsprint_sequence": list(subsprint_sequence or [])})
        return dict(script[subsprint_id])
    return run_unit


def _gap_campaign(tmp, charter, *, milestones=None, ledger_reqs=("REQ-1",),
                  run_unit=None, outcomes=None, gap_followup=None, budget=None,
                  gap_state=None):
    """Construct a Campaign and SEED it to backlog-exhausted WITH an in-envelope gap: the
    covered milestone has no delivered/waived terminal, so scope_report keeps its covers
    in_progress (in the gap). Returns the Campaign, ready for _gap_followup_round (the run()
    prelude attrs are primed)."""
    home = os.path.join(tmp, "camp")
    ledger_path = os.path.join(tmp, "ledger.json")
    with open(ledger_path, "w", encoding="utf-8") as fh:
        json.dump(_ledger(ledger_reqs), fh)
    ms = milestones if milestones is not None else [_covms("m1", ["s1"], ["REQ-1"])]
    extra = {}
    if gap_followup is not None:
        extra["gap_followup"] = gap_followup
    if budget is not None:
        extra["budget"] = budget
    plan = cp.stamp_signoff(_plan(ms, **extra), charter, signed_at="t")
    c = cp.Campaign(plan, home, run_unit or _gap_fake_run_unit({}), clock=_clock(),
                    charter=charter, ledger_path=ledger_path)
    c.state.milestone_index = len(c.milestones)
    c.state.units = [{"milestone_id": m["id"], "subsprint_id": s, "status": "done",
                      "final_state": "advance"}
                     for m in c.milestones for s in (m.get("subsprint_sequence") or [])]
    c.state.milestone_outcomes = list(outcomes or [])
    if gap_state is not None:
        c.state.gap_followup_state = dict(gap_state)
    c.state.status = cp.STATUS_RUNNING
    # Prime the run() prelude attrs so _gap_followup_round can be driven directly.
    c._base_wall = 0.0
    c._invocation_start = c.clock()
    c._gap_review_decision = None
    c._crash_recovery = False
    return c


class TestGapReviewCheckpointPlumbing(unittest.TestCase):
    """completeness_gap_review is the ONE §1.7-F gate the campaign emits (Mechanism B)."""

    def test_in_campaign_and_known_sets(self):
        self.assertIn("completeness_gap_review", cp.CAMPAIGN_CHECKPOINTS)
        self.assertIn("completeness_gap_review", cp.KNOWN_CHECKPOINTS)

    def test_classified_dispatch(self):
        self.assertEqual(cp.classify_checkpoint("completeness_gap_review"),
                         cp.RESUME_DISPATCH)

    def test_sets_stay_disjoint(self):
        sets = [cp.DRIVER_RESUME_CHECKPOINTS, cp.DISPATCH_CHECKPOINTS,
                cp.CAMPAIGN_CHECKPOINTS, cp.NON_PAUSE_CHECKPOINTS]
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                self.assertEqual(sets[i] & sets[j], frozenset())

    def test_interpret_adjust_scope(self):
        f = cp.interpret_dispatch
        self.assertEqual(f("completeness_gap_review", {"choice": "remediate"}),
                         cp.ACT_GAP_REMEDIATE)
        self.assertEqual(f("completeness_gap_review", {"choice": "accept_gap"}),
                         cp.ACT_GAP_ACCEPT)
        self.assertEqual(f("completeness_gap_review", {"choice": "abort"}), cp.ACT_END)
        # fail-closed: a bare/unknown choice never auto-remediates.
        self.assertEqual(f("completeness_gap_review", {"choice": "??"}),
                         cp.ACT_DELIVER_FOLLOWUP)
        self.assertEqual(f("completeness_gap_review", {}), cp.ACT_DELIVER_FOLLOWUP)


class TestGapFollowupDormant(unittest.TestCase):
    """No ledger ⇒ the engine is byte-identical to today (the campaign just finishes)."""

    def test_no_ledger_no_gap_followup(self):
        with tempfile.TemporaryDirectory() as d:
            plan = _plan([{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]}])
            st = cp.run_campaign(plan, d, _fake_run_unit(
                {"s1": {"final_state": "done", "spawn_count": 1}}), clock=_clock())
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(st.gap_followup_state, {})

    def test_fresh_signed_but_no_gap_finishes(self):
        # A ledger + fresh-signed plan whose milestone DELIVERED its covers ⇒ no gap.
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(
                d, _GF_CHARTER_ONL,
                outcomes=[{"milestone_id": "m1",
                           "terminal": "acceptance_pass_authoritative"}])
            self.assertEqual(c._gap_followup_round(None), cp.GAP_DONE)


class TestGapFollowupEligibilitySeal(unittest.TestCase):
    """§1.7-F clause 0 — the completeness↔quality SEAL (gap from facts only)."""

    def test_gap_from_facts_is_eligible(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)
            eligible, gap, reason = c._gap_followup_eligible(c._build_gap_report())
            self.assertTrue(eligible)
            self.assertEqual(reason, "eligible")
            self.assertEqual([g["req_id"] for g in gap], ["REQ-1"])

    def test_quality_fault_terminal_is_ineligible(self):
        # A milestone whose covers are in the gap BUT carries a human-waiver terminal is
        # INELIGIBLE for no-confirm gap-followup (defense-in-depth — it routes to a human).
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(
                d, _GF_CHARTER_ONL,
                outcomes=[{"milestone_id": "m1", "terminal": "fix_required_ship"}])
            # fix_required_ship ⇒ scope_report marks REQ-1 'waived' ⇒ NOT in the gap.
            # Force the seal's own check by feeding a crafted gap report.
            rep = {"signoff_status": "signed",
                   "gap": [{"req_id": "REQ-1", "delivery_status": "in_progress",
                            "covered_by": "m1"}]}
            eligible, _gap, reason = c._gap_followup_eligible(rep)
            self.assertFalse(eligible)
            self.assertEqual(reason, "quality_fault:m1")

    def test_ambiguous_gap_is_ineligible(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)
            rep = {"signoff_status": "signed",
                   "gap": [{"req_id": "REQ-9", "delivery_status": "in_progress",
                            "covered_by": "ghost"}]}
            eligible, _gap, reason = c._gap_followup_eligible(rep)
            self.assertFalse(eligible)
            self.assertTrue(reason.startswith("ambiguous_gap"))

    def test_not_fresh_signed_has_no_in_envelope_gap(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)
            eligible, _gap, reason = c._gap_followup_eligible(
                {"signoff_status": "stale", "gap": []})
            self.assertFalse(eligible)
            self.assertEqual(reason, "not_fresh_signed")


class TestReqIdEnvelopeCheck(unittest.TestCase):
    """§1.7-F clause 1 — the deterministic req_id-envelope check (DISTINCT from the
    module/layer post_gate1_scope_expansion guard)."""

    def test_in_envelope_passes(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)
            ok, why = c._req_id_envelope_check(c.milestones[0], ["REQ-1"])
            self.assertTrue(ok)
            self.assertEqual(why, "in_envelope")

    def test_out_of_envelope_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)
            ok, why = c._req_id_envelope_check(c.milestones[0], ["REQ-1", "REQ-999"])
            self.assertFalse(ok)
            self.assertIn("out_of_envelope", why)

    def test_empty_claim_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)
            ok, why = c._req_id_envelope_check(c.milestones[0], [])
            self.assertFalse(ok)
            self.assertEqual(why, "empty_covered_req_ids")

    def test_unverifiable_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)
            # Tamper the stored snapshot so it no longer verifies against its own hash.
            c.plan["signoff"]["scope_envelope"]["milestones"][0]["covers_req_ids"] = []
            ok, why = c._req_id_envelope_check(c.milestones[0], ["REQ-1"])
            self.assertFalse(ok)
            self.assertEqual(why, "envelope_unverifiable")


class TestGapFollowupBounds(unittest.TestCase):
    """§1.7-F clause 2 — runtime bounds (per-milestone counter, proper-subset progress,
    absent-budget effective-cap)."""

    def test_max_subsprints_per_milestone(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL,
                              gap_followup={"max_subsprints": 2},
                              gap_state={"rounds_by_milestone": {"m1": 2}})
            ok, why, _np = c._gap_followup_bounds(c.milestones[0], {"REQ-1"})
            self.assertFalse(ok)
            self.assertIn("max_subsprints_exceeded", why)

    def test_proper_subset_progress(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL,
                              gap_state={"gap_set_history": [["REQ-1", "REQ-2"]]})
            # A strictly smaller gap ⇒ progress (no_progress resets to 0).
            ok, _why, npg = c._gap_followup_bounds(c.milestones[0], {"REQ-1"})
            self.assertTrue(ok)
            self.assertEqual(npg, 0)

    def test_non_shrinking_round_is_no_progress_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(
                d, _GF_CHARTER_ONL,
                gap_followup={"max_no_progress_rounds": 1},
                gap_state={"gap_set_history": [["REQ-1"]], "no_progress_rounds": 0})
            ok, why, _np = c._gap_followup_bounds(c.milestones[0], {"REQ-1"})
            self.assertFalse(ok)
            self.assertIn("no_progress_exceeded", why)

    def test_gap_regression_halts(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL,
                              gap_state={"gap_set_history": [["REQ-1"]]})
            # A gap that GAINED a req_id (not in the prior set) is an immediate regression.
            ok, why, _np = c._gap_followup_bounds(c.milestones[0], {"REQ-1", "REQ-2"})
            self.assertFalse(ok)
            self.assertIn("gap_regression", why)

    def test_absent_budget_effective_cap(self):
        # No campaign budget + charter.budget.max_fix_rounds_total=2; spread 2 rounds over
        # 2 milestones (each below max_subsprints) ⇒ the TOTAL effective-cap fires.
        with tempfile.TemporaryDirectory() as d:
            charter = dict(_GF_CHARTER_ONL, budget={"max_fix_rounds_total": 2,
                                                    "max_wall_clock_minutes": 99})
            c = _gap_campaign(
                d, charter,
                milestones=[_covms("m1", ["s1"], ["REQ-1"]),
                            _covms("m2", ["s2"], ["REQ-2"])],
                ledger_reqs=("REQ-1", "REQ-2"),
                gap_state={"rounds_by_milestone": {"m1": 1, "m2": 1}})
            self.assertTrue(c._campaign_budget_absent())
            self.assertEqual(c._gap_effective_cap(), 2)
            ok, why, _np = c._gap_followup_bounds(c.milestones[0], {"REQ-1", "REQ-2"})
            self.assertFalse(ok)
            self.assertIn("effective_cap_exceeded", why)

    def test_present_budget_disables_effective_cap(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL, budget={"max_subsprints": 50},
                              gap_state={"rounds_by_milestone": {"m1": 1}})
            self.assertFalse(c._campaign_budget_absent())
            ok, _why, _np = c._gap_followup_bounds(c.milestones[0], {"REQ-1"})
            self.assertTrue(ok)

    def test_present_campaign_budget_exhausted_halts(self):
        # §1.7-F clause 2 "campaign budget not exhausted": a PRESENT budget already at its
        # cap blocks a further gap-followup round (the dispatch bypasses the inner loop's
        # between-units check, so the bound is enforced in _gap_followup_bounds).
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL, budget={"max_subsprints": 3})
            c.state.subsprints_run = 3
            ok, why, _np = c._gap_followup_bounds(c.milestones[0], {"REQ-1"})
            self.assertFalse(ok)
            self.assertIn("campaign_budget_exhausted", why)


class TestGapFollowupAutonomy(unittest.TestCase):
    """§1.7-F autonomy routing: human_on_the_loop+ auto-dispatches; human_in_the_loop
    routes a completeness gap_report to needs_human (the completeness_gap_review pause)."""

    def test_human_on_the_loop_auto_dispatches_and_closes(self):
        with tempfile.TemporaryDirectory() as d:
            rec = []
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}}, record=rec)
            c = _gap_campaign(d, _GF_CHARTER_ONL, run_unit=ru)
            self.assertEqual(c._gap_followup_round(None), cp.GAP_CONTINUE)
            # The remediation carried the in-envelope covered_req_ids + the grown sequence.
            self.assertEqual(rec[0]["covered_req_ids"], ["REQ-1"])
            self.assertEqual(rec[0]["subsprint_id"], "m1-gapfix-1")
            self.assertIn("m1-gapfix-1", rec[0]["subsprint_sequence"])
            # The milestone terminal was RE-STAMPED delivered + the round counter persisted.
            self.assertEqual(c._milestone_terminal("m1"),
                             "acceptance_pass_authoritative")
            self.assertEqual(c.state.gap_followup_state["rounds_by_milestone"]["m1"], 1)
            self.assertEqual(c.state.gap_followup_state["remediations"][0]["covered_req_ids"],
                             ["REQ-1"])
            # The next round sees no gap (REQ-1 delivered) ⇒ finish.
            c._gap_review_decision = None
            c._crash_recovery = False
            self.assertEqual(c._gap_followup_round(None), cp.GAP_DONE)

    def test_multi_milestone_gap_remediates_all(self):
        # REGRESSION: a remediation must NOT mutate the signed plan's subsprint_sequence —
        # doing so flips signoff_status to 'stale', and the NEXT round's build_gap_report
        # (not fresh-signed ⇒ empty gap) would SILENTLY DROP the rest of the gap. Both
        # milestones must be remediated and the plan must stay 'signed' throughout.
        with tempfile.TemporaryDirectory() as d:
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "done", "spawn_count": 1},
                 "m2-gapfix-1": {"final_state": "done", "spawn_count": 1}})
            c = _gap_campaign(
                d, _GF_CHARTER_ONL,
                milestones=[_covms("m1", ["s1"], ["REQ-1"]),
                            _covms("m2", ["s2"], ["REQ-2"])],
                ledger_reqs=("REQ-1", "REQ-2"), run_unit=ru)
            outcomes = []
            for _ in range(5):   # bounded drive of the OUTER loop
                o = c._gap_followup_round(None)
                outcomes.append(o)
                c._gap_review_decision = None
                c._crash_recovery = False
                if o != cp.GAP_CONTINUE:
                    break
            self.assertEqual(outcomes, [cp.GAP_CONTINUE, cp.GAP_CONTINUE, cp.GAP_DONE])
            self.assertEqual(c._milestone_terminal("m1"),
                             "acceptance_pass_authoritative")
            self.assertEqual(c._milestone_terminal("m2"),
                             "acceptance_pass_authoritative")
            # the signed plan was never mutated ⇒ still fresh-signed.
            self.assertEqual(cp.signoff_status(c.plan, _GF_CHARTER_ONL), "signed")
            self.assertEqual(c.plan["milestones"][0]["subsprint_sequence"], ["s1"])

    def test_advance_remediation_waives_and_shrinks_gap(self):
        # An acceptance-off remediation (final_state advance) re-stamps acceptance_off
        # (waived) ⇒ the milestone STILL leaves the gap (the set strictly shrinks).
        with tempfile.TemporaryDirectory() as d:
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "advance", "spawn_count": 1}})
            c = _gap_campaign(d, _GF_CHARTER_ONL, run_unit=ru)
            self.assertEqual(c._gap_followup_round(None), cp.GAP_CONTINUE)
            self.assertEqual(c._milestone_terminal("m1"), "acceptance_off")

    def test_human_in_the_loop_pauses_for_review(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ITL)
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertEqual(c.state.status, cp.STATUS_PAUSED)
            self.assertEqual(c.state.pause_reason, "completeness_gap_review")

    def test_human_in_the_loop_remediate_decision_dispatches(self):
        with tempfile.TemporaryDirectory() as d:
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}})
            c = _gap_campaign(d, _GF_CHARTER_ITL, run_unit=ru)
            c._gap_review_decision = {"choice": "remediate"}
            self.assertEqual(c._gap_followup_round(None), cp.GAP_CONTINUE)
            self.assertEqual(c._milestone_terminal("m1"),
                             "acceptance_pass_authoritative")

    def test_accept_gap_decision_finishes(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ITL)
            c._gap_review_decision = {"choice": "accept_gap"}
            self.assertEqual(c._gap_followup_round(None), cp.GAP_DONE)

    def test_abort_decision_ends(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ITL)
            c._gap_review_decision = {"choice": "abort"}
            self.assertEqual(c._gap_followup_round(None), cp.GAP_ENDED)
            self.assertEqual(c.state.status, cp.STATUS_ENDED)


class TestGapFollowupFailClosed(unittest.TestCase):
    """§1.7-F clause 3 — every gate failure HALTs and escalates to needs_human."""

    def test_out_of_envelope_target_halts(self):
        # The ledger covers REQ-1 but the SIGNED snapshot's covers were tampered to drop it
        # ⇒ the req_id-envelope check cannot prove containment ⇒ HALT.
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)
            c.plan["signoff"]["scope_envelope"]["milestones"][0]["covers_req_ids"] = []
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertEqual(c.state.pause_reason, "completeness_gap_review")

    def test_bound_exceeded_halts(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL,
                              gap_followup={"max_subsprints": 1},
                              gap_state={"rounds_by_milestone": {"m1": 1}})
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertEqual(c.state.pause_reason, "completeness_gap_review")

    def test_halted_remediation_escalates(self):
        with tempfile.TemporaryDirectory() as d:
            ru = _gap_fake_run_unit({"m1-gapfix-1": {
                "final_state": "halted", "spawn_count": 1,
                "pause_reason": "gate_hard_fail", "checkpoint_path": "/cp.md"}})
            c = _gap_campaign(d, _GF_CHARTER_ONL, run_unit=ru)
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertEqual(c.state.pause_reason, "completeness_gap_review")
            # The round was counted + the halted unit recorded (with its checkpoint).
            self.assertEqual(c.state.gap_followup_state["rounds_by_milestone"]["m1"], 1)
            self.assertEqual(c.state.units[-1]["status"], "halted")
            self.assertEqual(c.state.units[-1]["pause_reason"], "gate_hard_fail")


class TestGapFollowupRunIntegration(unittest.TestCase):
    """The run() OUTER loop: a seeded mid-gap-followup RUNNING state resumes, the engine
    auto-dispatches the remediation, the gap closes, and the campaign reaches DONE — the
    whole loop, persisted + schema-valid."""

    def test_outer_loop_drives_to_done(self):
        with tempfile.TemporaryDirectory() as d:
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}})
            c = _gap_campaign(d, _GF_CHARTER_ONL, run_unit=ru)
            c._save()   # persist the seeded mid-gap-followup RUNNING state
            st = c.run(resume=True)
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(c._milestone_terminal("m1"),
                             "acceptance_pass_authoritative")
            with open(os.path.join(d, "camp", "campaign-state.json"),
                      encoding="utf-8") as fh:
                persisted = json.load(fh)
            cp._validate_or_raise(persisted, "campaign-state.schema.json", "state")
            self.assertEqual(
                persisted["gap_followup_state"]["rounds_by_milestone"]["m1"], 1)

    def test_human_in_the_loop_pause_then_resume_to_done(self):
        with tempfile.TemporaryDirectory() as d:
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}})
            c = _gap_campaign(d, _GF_CHARTER_ITL, run_unit=ru)
            c._save()
            paused = c.run(resume=True)
            self.assertEqual(paused.status, cp.STATUS_PAUSED)
            self.assertEqual(paused.pause_reason, "completeness_gap_review")
            # The paused-at-backlog-end state must itself be schema-valid + reloadable.
            with open(os.path.join(d, "camp", "campaign-state.json"),
                      encoding="utf-8") as fh:
                cp._validate_or_raise(json.load(fh), "campaign-state.schema.json", "s")
            done = c.run(resume=True,
                         decision_resolver=lambda r, cpt: {"choice": "remediate"})
            self.assertEqual(done.status, cp.STATUS_DONE)


class TestGapFollowupR2Hardening(unittest.TestCase):
    """Codex R1 BLOCKING fixes."""

    def test_b1_gap_projection_failure_halts_not_finishes(self):
        # A wired-ledger gap projection that FAILS must HALT to needs_human (clause 3),
        # not silently finish the campaign.
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)

            def _boom():
                raise RuntimeError("ledger projection broke")
            c._build_gap_report = _boom
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertEqual(c.state.pause_reason, "completeness_gap_review")

    def test_b2_gapfix_dispatch_uses_resume_false(self):
        with tempfile.TemporaryDirectory() as d:
            rec = []
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}}, record=rec)
            c = _gap_campaign(d, _GF_CHARTER_ONL, run_unit=ru)
            c._gap_followup_round(None)
            self.assertFalse(rec[0]["resume"])   # never resume=True (no Driver state to resume)
            self.assertEqual(rec[0]["gap_followup_spec"]["covered_req_ids"], ["REQ-1"])

    def test_b2_completed_round_not_redispatched_on_recompute(self):
        # Crash-idempotency: a round whose atomic save persisted the re-stamp leaves the
        # milestone OUT of the recomputed gap → it is never re-dispatched.
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(
                d, _GF_CHARTER_ONL,
                outcomes=[{"milestone_id": "m1",
                           "terminal": "acceptance_pass_authoritative"}],
                gap_state={"rounds_by_milestone": {"m1": 1},
                           "gap_set_history": [["REQ-1"]],
                           "remediations": [{"milestone_id": "m1",
                                             "subsprint_id": "m1-gapfix-1",
                                             "covered_req_ids": ["REQ-1"], "round": 1}]})
            self.assertEqual(c._gap_followup_round(None), cp.GAP_DONE)

    def test_b3_pause_writes_distinct_nonce_checkpoints(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ITL)
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            cpt1 = c.state.pause_checkpoint
            self.assertTrue(cpt1 and os.path.isfile(cpt1))
            self.assertIn("completeness_gap_review", os.path.basename(cpt1))
            self.assertEqual(c.state.gap_followup_state["gap_review_seq"], 1)
            c._gap_review_decision = None
            c._crash_recovery = False
            c._gap_followup_round(None)
            cpt2 = c.state.pause_checkpoint
            self.assertNotEqual(os.path.basename(cpt1), os.path.basename(cpt2))
            self.assertEqual(c.state.gap_followup_state["gap_review_seq"], 2)

    def test_b5_remediation_id_collision_halts(self):
        with tempfile.TemporaryDirectory() as d:
            # a signed sub-sprint already named m1-gapfix-1 ⇒ round-1's id collides.
            c = _gap_campaign(d, _GF_CHARTER_ONL,
                              milestones=[_covms("m1", ["s1", "m1-gapfix-1"], ["REQ-1"])])
            rid, why = c._safe_remediation_id(c.milestones[0], 1)
            self.assertIsNone(rid)
            self.assertEqual(why, "collides_with_signed_subsprint")
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertEqual(c.state.pause_reason, "completeness_gap_review")

    def test_b5_remediation_id_length_overflow_halts(self):
        with tempfile.TemporaryDirectory() as d:
            long_mid = "m" + "x" * 126   # 127 chars (legal id); + "-gapfix-1" overflows 128
            c = _gap_campaign(d, _GF_CHARTER_ONL,
                              milestones=[_covms(long_mid, ["s1"], ["REQ-1"])])
            rid, why = c._safe_remediation_id(c.milestones[0], 1)
            self.assertIsNone(rid)
            self.assertEqual(why, "id_overflow_or_unsafe")

    def test_n2_empty_gap_state_omitted_from_persisted_state(self):
        # A campaign that never enters gap-followup persists a byte-identical state.json.
        st = cp.CampaignState(campaign_id="c1")
        self.assertNotIn("gap_followup_state", st.to_dict())
        cp._validate_or_raise(st.to_dict(), "campaign-state.schema.json", "state")

    def test_r2b2_pending_marker_cleared_on_clean_round(self):
        with tempfile.TemporaryDirectory() as d:
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}})
            c = _gap_campaign(d, _GF_CHARTER_ONL, run_unit=ru)
            self.assertEqual(c._gap_followup_round(None), cp.GAP_CONTINUE)
            self.assertNotIn("pending_remediation", c.state.gap_followup_state)

    def _valid_marker(self, c, **over):
        m = {"milestone_id": "m1", "remediation_id": "m1-gapfix-1", "round": 1,
             "covered_req_ids": ["REQ-1"], "gap_set": ["REQ-1"], "no_progress": 0,
             "scope_hash": c._live_signed_scope_hash()}
        m.update(over)
        c.state.gap_followup_state["pending_remediation"] = m
        return c

    def test_r2b2_crash_recovery_completes_inflight_once(self):
        # A persisted pending_remediation (the atomic round-save never landed) is COMPLETED
        # by re-entering the SAME gapfix with resume=True — recorded ONCE, no double-run.
        with tempfile.TemporaryDirectory() as d:
            rec = []
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}}, record=rec)
            c = self._valid_marker(_gap_campaign(d, _GF_CHARTER_ONL, run_unit=ru))
            self.assertEqual(c._gap_followup_round(None), cp.GAP_CONTINUE)
            self.assertEqual(len(rec), 1)        # dispatched EXACTLY once (no double-run)
            self.assertTrue(rec[0]["resume"])    # re-entered the in-flight Driver
            self.assertEqual(c._milestone_terminal("m1"),
                             "acceptance_pass_authoritative")
            self.assertNotIn("pending_remediation", c.state.gap_followup_state)
            self.assertEqual(c.state.gap_followup_state["rounds_by_milestone"]["m1"], 1)

    def test_r2b2_orphan_pending_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(
                d, _GF_CHARTER_ONL,
                gap_state={"pending_remediation": {
                    "milestone_id": "ghost", "remediation_id": "ghost-gapfix-1",
                    "round": 1, "covered_req_ids": ["REQ-1"], "gap_set": ["REQ-1"],
                    "no_progress": 0}})
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertNotIn("pending_remediation", c.state.gap_followup_state)

    def test_r2b3_null_checkpoint_boundary_rejected(self):
        # A bug-written paused-at-end state with completeness_gap_review + NULL checkpoint is
        # fail-closed at resume ingress, so it can never bind a checkpoint:null decision and
        # bypass the nonce.
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ITL)
            c.state.status = cp.STATUS_PAUSED
            c.state.pause_reason = "completeness_gap_review"
            c.state.pause_checkpoint = None
            c._save()
            cp._validate_or_raise(c.state.to_dict(),    # schema-valid (null checkpoint allowed)
                                  "campaign-state.schema.json", "state")
            with self.assertRaises(ValueError):
                c.run(resume=True)                       # ...but consistency-rejected

    def test_r3b1_pending_completed_even_without_ledger(self):
        # The pending check runs BEFORE the no-ledger exit, so a marker is never stranded at
        # STATUS_DONE if the ledger became unreadable on resume (the marker is self-contained).
        with tempfile.TemporaryDirectory() as d:
            rec = []
            ru = _gap_fake_run_unit(
                {"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}}, record=rec)
            c = self._valid_marker(_gap_campaign(d, _GF_CHARTER_ONL, run_unit=ru))
            c.ledger = None                              # ledger unavailable on resume
            self.assertEqual(c._gap_followup_round(None), cp.GAP_CONTINUE)
            self.assertEqual(len(rec), 1)
            self.assertNotIn("pending_remediation", c.state.gap_followup_state)

    def test_r3nb1_malformed_marker_fails_closed(self):
        # A marker with a non-canonical remediation id (corrupt/tampered state) is refused
        # before bypassing the gates, rather than dispatching an ambiguous remediation.
        with tempfile.TemporaryDirectory() as d:
            c = self._valid_marker(_gap_campaign(d, _GF_CHARTER_ONL),
                                   remediation_id="WRONG-ID")
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertNotIn("pending_remediation", c.state.gap_followup_state)

    def test_r3nb1_empty_covered_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._valid_marker(_gap_campaign(d, _GF_CHARTER_ONL),
                                   covered_req_ids=[], gap_set=[])
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertNotIn("pending_remediation", c.state.gap_followup_state)

    def test_r4b1_scope_epoch_mismatch_fails_closed(self):
        # A marker authorized under a DIFFERENT signed scope epoch (plan edited/re-signed
        # between dispatch and resume) is refused — never auto-runs out-of-epoch work.
        with tempfile.TemporaryDirectory() as d:
            c = self._valid_marker(_gap_campaign(d, _GF_CHARTER_ONL),
                                   scope_hash="0" * 64)   # stale/foreign epoch hash
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertNotIn("pending_remediation", c.state.gap_followup_state)

    def test_r4nb1_empty_marker_fails_closed(self):
        # A bug-written empty {} marker is PRESENT-but-malformed → fail-closed, not ignored.
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL)
            c.state.gap_followup_state["pending_remediation"] = {}
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertNotIn("pending_remediation", c.state.gap_followup_state)

    def test_r5b1_pending_under_unsigned_plan_fails_closed(self):
        # A signed_by_human flip after dispatch does NOT change the scope_hash, so the
        # pending path must independently re-check signoff_status — never complete work
        # under a no-longer-signed plan.
        with tempfile.TemporaryDirectory() as d:
            c = self._valid_marker(_gap_campaign(d, _GF_CHARTER_ONL))
            c.plan["signoff"]["signed_by_human"] = False    # un-sign WITHOUT a scope change
            c.plan["signed_by_human"] = False
            self.assertNotEqual(c._signoff_status(), "signed")
            self.assertEqual(c._gap_followup_round(None), cp.GAP_PAUSED)
            self.assertNotIn("pending_remediation", c.state.gap_followup_state)

    def test_r5b2_first_non_shrinking_round_halts_by_default(self):
        # §1.7-F clause 2/3: a non-shrinking round HALTs on the FIRST occurrence (the default
        # max_no_progress_rounds is 1 — proper-subset required, not retry-up-to-N).
        with tempfile.TemporaryDirectory() as d:
            c = _gap_campaign(d, _GF_CHARTER_ONL,
                              gap_state={"gap_set_history": [["REQ-1"]],
                                         "no_progress_rounds": 0})
            self.assertEqual(c._gap_followup_cfg()["max_no_progress_rounds"], 1)
            ok, why, _np = c._gap_followup_bounds(c.milestones[0], {"REQ-1"})  # unchanged gap
            self.assertFalse(ok)
            self.assertIn("no_progress_exceeded", why)


class TestGapFollowupStateRoundTrip(unittest.TestCase):
    def test_gap_followup_state_persists_and_reloads(self):
        gfs = {"rounds_by_milestone": {"m1": 2}, "gap_set_history": [["REQ-1"]],
               "no_progress_rounds": 1,
               "remediations": [{"milestone_id": "m1", "subsprint_id": "m1-gapfix-1",
                                 "covered_req_ids": ["REQ-1"], "round": 1}]}
        st = cp.CampaignState(campaign_id="c1", gap_followup_state=gfs)
        back = cp.CampaignState.from_dict(st.to_dict())
        self.assertEqual(back.gap_followup_state, gfs)
        cp._validate_or_raise(st.to_dict(), "campaign-state.schema.json", "state")


if __name__ == "__main__":
    unittest.main()
