"""Phase-4 (parallel campaign runner) — Cluster 1 tests: config + state model + scheduler.
NO execution change is exercised here (the coordinator lands in Cluster 3); these cover the
additive schema/config, the milestone_runtime state model + additivity, the parallel
_check_state_consistency invariants, and the PURE scheduler functions. stdlib unittest; offline."""
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402


def _clock():
    n = {"i": 0}

    def tick() -> str:
        n["i"] += 1
        return f"2026-07-10T00:{n['i'] // 60:02d}:{n['i'] % 60:02d}Z"
    return tick


def _fake_run_unit(script=None):
    def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                 resume=False, functional_acceptance=None, repo_dir=None, **kw):
        return dict((script or {}).get(subsprint_id, {"final_state": "done", "spawn_count": 0}))
    return run_unit


def _ms(mid, seq, **kw):
    m = {"id": mid, "objective": "o", "subsprint_sequence": list(seq)}
    m.update(kw)
    return m


def _plan(milestones, *, max_concurrent=None, isolation="new_worktree",
          merge_prompt_at_close=True, **kw):
    plan = {"campaign_id": kw.pop("campaign_id", "camp-1"), "goal": "g",
            "signed_by_human": kw.pop("signed_by_human", True), "milestones": milestones}
    budget = dict(kw.pop("budget", {}))
    if max_concurrent is not None:
        budget["max_concurrent"] = max_concurrent
    if budget:
        plan["budget"] = budget
    if isolation is not None:
        plan["milestone_isolation"] = {"default_strategy": isolation,
                                       "merge_prompt_at_close": merge_prompt_at_close}
    plan.update(kw)
    return plan


# --------------------------------------------------------------------------- #
class TestPhase4Config(unittest.TestCase):
    """max_concurrent: f1_required activator + conditional H emission (design §10)."""

    def test_f1_required_activated_by_max_concurrent_gt1(self):
        self.assertTrue(cp.f1_required(_plan([_ms("m1", ["s1"])], max_concurrent=2)))

    def test_f1_required_unchanged_for_serial_max_concurrent(self):
        # absent OR ==1 leaves f1_required byte-identical to a legacy plan (value-checked).
        legacy = {"campaign_id": "c", "goal": "g", "signed_by_human": True,
                  "milestones": [{"id": "m1", "objective": "o", "subsprint_sequence": ["s1"]}]}
        self.assertFalse(cp.f1_required(legacy))
        self.assertFalse(cp.f1_required({**legacy, "budget": {"max_concurrent": 1}}))

    def test_resolve_authority_omits_max_concurrent_when_absent_or_1(self):
        base = cp._resolve_plan_authority(_plan([_ms("m1", ["s1"])], isolation=None))
        one = cp._resolve_plan_authority(_plan([_ms("m1", ["s1"])], max_concurrent=1,
                                               isolation=None))
        self.assertNotIn("max_concurrent", base["budget"])
        self.assertNotIn("max_concurrent", one["budget"])
        self.assertEqual(base["budget"], one["budget"])  # byte-identical

    def test_resolve_authority_emits_max_concurrent_when_gt1(self):
        auth = cp._resolve_plan_authority(_plan([_ms("m1", ["s1"])], max_concurrent=3,
                                                isolation=None))
        self.assertEqual(auth["budget"]["max_concurrent"], 3)

    def test_signed_hash_byte_identical_for_absent_vs_1_but_differs_for_gt1(self):
        p_absent = _plan([_ms("m1", ["s1"])], isolation=None)
        p_one = _plan([_ms("m1", ["s1"])], max_concurrent=1, isolation=None)
        p_two = _plan([_ms("m1", ["s1"])], max_concurrent=2, isolation=None)
        h_absent = cp.compute_signed_scope_hash(p_absent, None)
        h_one = cp.compute_signed_scope_hash(p_one, None)
        h_two = cp.compute_signed_scope_hash(p_two, None)
        self.assertEqual(h_absent, h_one)      # no forced re-sign for serial max_concurrent:1
        self.assertNotEqual(h_absent, h_two)   # a parallel plan's authority flips H


class TestPhase4Eligibility(unittest.TestCase):
    """Ingress fail-closed gate: parallel ⇒ all new_worktree + merge gate on (design §7.1)."""

    def _construct(self, plan):
        d = tempfile.mkdtemp()
        return cp.Campaign(plan, d, _fake_run_unit(), clock=_clock())

    def test_parallel_plan_rejects_non_worktree_isolation(self):
        with self.assertRaises(ValueError):
            self._construct(_plan([_ms("m1", ["s1"])], max_concurrent=2,
                                  isolation="current_branch"))

    def test_parallel_plan_rejects_merge_prompt_disabled(self):
        with self.assertRaises(ValueError):
            self._construct(_plan([_ms("m1", ["s1"])], max_concurrent=2,
                                  isolation="new_worktree", merge_prompt_at_close=False))

    def test_parallel_plan_accepts_new_worktree(self):
        camp = self._construct(_plan([_ms("m1", ["s1"]), _ms("m2", ["s2"])], max_concurrent=2))
        self.assertEqual(len(camp.milestones), 2)

    def test_serial_plan_unaffected_by_gate(self):
        # A serial plan with default (current_branch) isolation must still construct.
        camp = self._construct(_plan([_ms("m1", ["s1"])], isolation="current_branch"))
        self.assertEqual(len(camp.milestones), 1)


class TestPhase4StateModel(unittest.TestCase):
    """milestone_runtime additivity + round-trip (design §3.1/§3.5)."""

    def test_serial_state_omits_milestone_runtime(self):
        st = cp.CampaignState(campaign_id="c")
        self.assertNotIn("milestone_runtime", st.to_dict())

    def test_milestone_runtime_round_trips(self):
        rt = {"m1": {"phase": "running", "subsprint_index": 0,
                     "current_attempt_nonce": 1,
                     "inflight": {"attempt_nonce": 1, "subsprint_id": "s1"}, "folded": []}}
        st = cp.CampaignState(campaign_id="c", milestone_runtime=rt)
        d = st.to_dict()
        self.assertEqual(d["milestone_runtime"], rt)
        self.assertEqual(cp.CampaignState.from_dict(d).milestone_runtime, rt)


class TestPhase4Scheduler(unittest.TestCase):
    """Pure scheduler functions (design §4/§7.2)."""

    def test_ready_set_blocks_on_unmerged_dependency(self):
        ms = [_ms("m1", ["s1"], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["b"], depends_on=["m1"])]
        # m1 not merged ⇒ m2 not ready (only m1 is ready).
        self.assertEqual(cp.parallel_ready_set(ms, {}), ["m1"])
        # m1 merged ⇒ m2 ready.
        self.assertEqual(cp.parallel_ready_set(ms, {"m1": {"phase": "merged"}}), ["m2"])

    def test_ready_set_lock_disjointness_and_empty_lock_conservatism(self):
        ms = [_ms("m1", ["s1"], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["b"]),
              _ms("m3", ["s3"], module_locks=["a"])]
        # m1 running (locks {a}); m2 (locks {b}) is disjoint ⇒ ready; m3 (locks {a}) overlaps ⇒ not.
        rt = {"m1": {"phase": "running", "inflight": {"attempt_nonce": 1, "subsprint_id": "s1"}}}
        self.assertEqual(cp.parallel_ready_set(ms, rt), ["m2"])
        # A LOCKLESS milestone conflicts with everything while something runs.
        ms2 = [_ms("m1", ["s1"], module_locks=["a"]), _ms("m2", ["s2"])]  # m2 no locks
        self.assertEqual(cp.parallel_ready_set(ms2, rt), [])
        # A LOCKLESS RUNNING milestone blocks all others.
        rt_lockless = {"m1": {"phase": "running",
                              "inflight": {"attempt_nonce": 1, "subsprint_id": "s1"}}}
        ms3 = [_ms("m1", ["s1"]), _ms("m2", ["s2"], module_locks=["b"])]
        self.assertEqual(cp.parallel_ready_set(ms3, rt_lockless), [])

    def test_ready_set_excludes_inflight_and_terminal(self):
        ms = [_ms("m1", ["s1"], module_locks=["a"]), _ms("m2", ["s2"], module_locks=["b"]),
              _ms("m3", ["s3"], module_locks=["c"])]
        rt = {"m1": {"phase": "running", "inflight": {"attempt_nonce": 1, "subsprint_id": "s1"}},
              "m2": {"phase": "merged"}}
        self.assertEqual(cp.parallel_ready_set(ms, rt), ["m3"])

    def test_admit_respects_max_concurrent(self):
        ready = ["m1", "m2", "m3"]
        self.assertEqual(
            cp.parallel_admit(ready, {}, max_concurrent=2, subsprints_run=0,
                              max_subsprints=None), ["m1", "m2"])
        # one already in flight ⇒ only one more slot.
        rt = {"mX": {"inflight": {"attempt_nonce": 1, "subsprint_id": "s"}}}
        self.assertEqual(
            cp.parallel_admit(ready, rt, max_concurrent=2, subsprints_run=0,
                              max_subsprints=None), ["m1"])

    def test_admit_respects_signed_max_subsprints(self):
        # spent 1, 0 in flight, cap 2 ⇒ only 1 more may be admitted.
        self.assertEqual(
            cp.parallel_admit(["m1", "m2", "m3"], {}, max_concurrent=5, subsprints_run=1,
                              max_subsprints=2), ["m1"])

    def test_merge_order_fifo_vs_human_order(self):
        ms = [_ms("m1", ["s1"]), _ms("m2", ["s2"]), _ms("m3", ["s3"])]
        done = ["m3", "m1", "m2"]  # completion order
        self.assertEqual(cp.parallel_merge_order(done, ms, "fifo"), ["m3", "m1", "m2"])
        self.assertEqual(cp.parallel_merge_order(done, ms, None), ["m3", "m1", "m2"])
        self.assertEqual(cp.parallel_merge_order(done, ms, "human_order"), ["m1", "m2", "m3"])


class TestPhase4StateConsistency(unittest.TestCase):
    """_check_parallel_state_consistency fail-closed invariants (design §3.3)."""

    def _camp(self, n=2, max_concurrent=2, max_subsprints=None):
        ms = [_ms(f"m{i}", [f"s{i}"]) for i in range(1, n + 1)]
        budget = {"max_subsprints": max_subsprints} if max_subsprints else {}
        plan = _plan(ms, max_concurrent=max_concurrent, budget=budget)
        d = tempfile.mkdtemp()
        return cp.Campaign(plan, d, _fake_run_unit(), clock=_clock())

    def _valid_state(self):
        # m1 done (s1 folded), m2 running (s2 in flight).
        return {
            "campaign_id": "camp-1", "status": "running",
            "cursor": {"milestone_index": 0, "subsprint_index": 0},
            "spent": {"subsprints_run": 1, "total_spawns": 0, "wall_clock_minutes": 0},
            "units": [{"milestone_id": "m1", "subsprint_id": "s1", "status": "done",
                       "loop_id": "u_m1s1", "attempt_nonce": 1}],
            "milestone_runtime": {
                "m1": {"phase": "done", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "folded": [["u_m1s1", 1]]},
                "m2": {"phase": "running", "subsprint_index": 0, "current_attempt_nonce": 1,
                       "inflight": {"attempt_nonce": 1, "subsprint_id": "s2"}, "folded": []},
            },
        }

    def test_valid_parallel_state_passes(self):
        self._camp()._check_parallel_state_consistency(self._valid_state())

    def test_rejects_unknown_milestone(self):
        s = self._valid_state()
        s["milestone_runtime"]["ghost"] = {"phase": "ready"}
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_subsprint_index_out_of_range(self):
        s = self._valid_state()
        s["milestone_runtime"]["m2"]["subsprint_index"] = 5
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_running_without_inflight(self):
        s = self._valid_state()
        s["milestone_runtime"]["m2"].pop("inflight")
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_inflight_nonce_mismatch(self):
        s = self._valid_state()
        s["milestone_runtime"]["m2"]["inflight"]["attempt_nonce"] = 9
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_fold_key_without_matching_unit(self):
        s = self._valid_state()
        s["milestone_runtime"]["m1"]["folded"] = [["u_nomatch", 1]]
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_over_max_concurrent(self):
        camp = self._camp(n=3, max_concurrent=2)
        s = {"campaign_id": "camp-1", "status": "running",
             "cursor": {"milestone_index": 0, "subsprint_index": 0},
             "spent": {"subsprints_run": 0, "total_spawns": 0, "wall_clock_minutes": 0},
             "units": [],
             "milestone_runtime": {f"m{i}": {
                 "phase": "running", "subsprint_index": 0, "current_attempt_nonce": 1,
                 "inflight": {"attempt_nonce": 1, "subsprint_id": f"s{i}"}, "folded": []}
                 for i in range(1, 4)}}
        with self.assertRaises(ValueError):
            camp._check_parallel_state_consistency(s)

    def test_rejects_over_max_subsprints(self):
        camp = self._camp(n=2, max_concurrent=2, max_subsprints=1)
        s = {"campaign_id": "camp-1", "status": "running",
             "cursor": {"milestone_index": 0, "subsprint_index": 0},
             "spent": {"subsprints_run": 0, "total_spawns": 0, "wall_clock_minutes": 0},
             "units": [],
             "milestone_runtime": {f"m{i}": {
                 "phase": "running", "subsprint_index": 0, "current_attempt_nonce": 1,
                 "inflight": {"attempt_nonce": 1, "subsprint_id": f"s{i}"}, "folded": []}
                 for i in range(1, 3)}}
        with self.assertRaises(ValueError):
            camp._check_parallel_state_consistency(s)

    def test_rejects_subsprints_run_ne_unit_count(self):
        s = self._valid_state()
        s["spent"]["subsprints_run"] = 5
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_nonzero_cursor_mirror(self):
        s = self._valid_state()
        s["cursor"]["milestone_index"] = 1
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)


if __name__ == "__main__":
    unittest.main()
