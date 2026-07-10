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

    # Disjoint-lock milestones so capacity/budget (not locks) is the binding constraint here;
    # the lock-serialization behaviour has its own tests below.
    _DISJOINT = [_ms("m1", ["s1"], module_locks=["a"]),
                 _ms("m2", ["s2"], module_locks=["b"]),
                 _ms("m3", ["s3"], module_locks=["c"])]

    def test_admit_respects_max_concurrent(self):
        ready = ["m1", "m2", "m3"]
        self.assertEqual(
            cp.parallel_admit(ready, {}, milestones=self._DISJOINT, max_concurrent=2,
                              subsprints_run=0, max_subsprints=None), ["m1", "m2"])
        # one already in flight (disjoint lock) ⇒ only one more slot.
        ms = self._DISJOINT + [_ms("mX", ["sx"], module_locks=["x"])]
        rt = {"mX": {"phase": "running",
                     "inflight": {"attempt_nonce": 1, "subsprint_id": "sx"}}}
        self.assertEqual(
            cp.parallel_admit(ready, rt, milestones=ms, max_concurrent=2,
                              subsprints_run=0, max_subsprints=None), ["m1"])

    def test_admit_respects_signed_max_subsprints(self):
        # spent 1, 0 in flight, cap 2 ⇒ only 1 more may be admitted.
        self.assertEqual(
            cp.parallel_admit(["m1", "m2", "m3"], {}, milestones=self._DISJOINT,
                              max_concurrent=5, subsprints_run=1, max_subsprints=2), ["m1"])

    def test_admit_serializes_lockless_ready_milestones(self):
        # Two LOCKLESS ready milestones must NOT co-admit (empty locks conflict with everything,
        # design §4 / Codex R1 B-2) — only the first is admitted this batch.
        ms = [_ms("m1", ["s1"]), _ms("m2", ["s2"])]
        self.assertEqual(
            cp.parallel_admit(["m1", "m2"], {}, milestones=ms, max_concurrent=2,
                              subsprints_run=0, max_subsprints=None), ["m1"])

    def test_admit_serializes_overlapping_locks(self):
        # Two ready milestones both locking 'a' must NOT co-admit (Codex R1 B-2).
        ms = [_ms("m1", ["s1"], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["a", "b"])]
        self.assertEqual(
            cp.parallel_admit(["m1", "m2"], {}, milestones=ms, max_concurrent=2,
                              subsprints_run=0, max_subsprints=None), ["m1"])

    def test_admit_co_admits_disjoint_locks(self):
        ms = [_ms("m1", ["s1"], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["b"])]
        self.assertEqual(
            cp.parallel_admit(["m1", "m2"], {}, milestones=ms, max_concurrent=2,
                              subsprints_run=0, max_subsprints=None), ["m1", "m2"])

    def test_admit_lockless_candidate_blocked_when_a_lock_is_reserved(self):
        # A lockless candidate cannot co-run once a locked milestone is admitted first.
        ms = [_ms("m1", ["s1"], module_locks=["a"]), _ms("m2", ["s2"])]  # m2 lockless
        self.assertEqual(
            cp.parallel_admit(["m1", "m2"], {}, milestones=ms, max_concurrent=2,
                              subsprints_run=0, max_subsprints=None), ["m1"])

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

    # ----- Codex R1 B-3: running milestone needs a COMPLETE inflight record ------------- #
    def test_rejects_running_with_empty_inflight(self):
        s = self._valid_state()
        s["milestone_runtime"]["m2"]["inflight"] = {}
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_running_inflight_missing_subsprint_id(self):
        s = self._valid_state()
        s["milestone_runtime"]["m2"]["inflight"] = {"attempt_nonce": 1}
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_running_without_current_attempt_nonce(self):
        s = self._valid_state()
        s["milestone_runtime"]["m2"].pop("current_attempt_nonce")
        s["milestone_runtime"]["m2"]["inflight"].pop("attempt_nonce", None)
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    # ----- Codex R1 B-4: a present-empty milestone_runtime is corrupted parallel state -- #
    def test_rejects_empty_milestone_runtime_map(self):
        s = self._valid_state()
        s["milestone_runtime"] = {}
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_empty_milestone_runtime_present_routes_to_parallel_and_fails(self):
        # This state would PASS the serial validator (cursor (0,0), no units); the PRESENT-but-
        # empty milestone_runtime must route it to the parallel validator, which fails closed.
        camp = self._camp()
        s = {"campaign_id": "camp-1", "status": "running",
             "cursor": {"milestone_index": 0, "subsprint_index": 0},
             "spent": {"subsprints_run": 0, "total_spawns": 0, "wall_clock_minutes": 0},
             "units": [], "milestone_runtime": {}}
        # Sanity: identical state WITHOUT the key validates as serial (no raise).
        camp._check_state_consistency({k: v for k, v in s.items()
                                       if k != "milestone_runtime"})
        with self.assertRaises(ValueError):
            camp._check_state_consistency(s)

    # ----- Codex R1 B-5: top-level singletons mirror the OLDEST outstanding pause -------- #
    def _paused_state(self):
        # m1 paused (oldest = topo index 0), m2 running; top-level singleton mirrors m1's pause.
        return {
            "campaign_id": "camp-1", "status": "paused",
            "cursor": {"milestone_index": 0, "subsprint_index": 0},
            "spent": {"subsprints_run": 0, "total_spawns": 0, "wall_clock_minutes": 0},
            "units": [],
            "pause_reason": "gate_hard_fail", "pause_checkpoint": "/cp/m1",
            "milestone_runtime": {
                "m1": {"phase": "paused", "subsprint_index": 0, "current_attempt_nonce": 0,
                       "pause_reason": "gate_hard_fail", "pause_checkpoint": "/cp/m1",
                       "folded": []},
                "m2": {"phase": "running", "subsprint_index": 0, "current_attempt_nonce": 1,
                       "inflight": {"attempt_nonce": 1, "subsprint_id": "s2"}, "folded": []},
            },
        }

    def test_paused_mirror_match_passes(self):
        self._camp()._check_parallel_state_consistency(self._paused_state())

    def test_rejects_missing_pause_mirror(self):
        s = self._paused_state()
        s["pause_reason"] = None
        s["pause_checkpoint"] = None
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_wrong_pause_mirror(self):
        s = self._paused_state()
        s["pause_reason"] = "completeness_gap_review"
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    # ----- Codex R1 B-5 round-2: top-level status ↔ milestone-phase coherence ------------ #
    def test_rejects_paused_status_with_no_paused_milestone_and_nonglobal_reason(self):
        # status 'paused' + a milestone-scoped pause_reason but NO milestone paused = stale gate.
        s = self._valid_state()  # m1 done, m2 running — none paused
        s["status"] = "paused"
        s["pause_reason"] = "gate_hard_fail"
        s["pause_checkpoint"] = "/cp/stale"
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_accepts_global_pause_with_no_paused_milestone(self):
        # A coordinator-global pause (campaign_plan_signoff) WITH its checkpoint is legitimate
        # even with no per-milestone pause (F1 re-sign at genesis; milestones still 'ready').
        s = {
            "campaign_id": "camp-1", "status": "paused",
            "cursor": {"milestone_index": 0, "subsprint_index": 0},
            "spent": {"subsprints_run": 0, "total_spawns": 0, "wall_clock_minutes": 0},
            "units": [],
            "pause_reason": "campaign_plan_signoff", "pause_checkpoint": "/cp/signoff",
            "milestone_runtime": {
                "m1": {"phase": "ready", "subsprint_index": 0, "current_attempt_nonce": 0,
                       "folded": []},
                "m2": {"phase": "ready", "subsprint_index": 0, "current_attempt_nonce": 0,
                       "folded": []},
            },
        }
        self._camp()._check_parallel_state_consistency(s)

    def test_rejects_global_pause_without_checkpoint(self):
        s = self._valid_state()
        s["status"] = "paused"
        s["pause_reason"] = "campaign_plan_signoff"
        s["pause_checkpoint"] = None
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_done_status_with_running_milestone(self):
        # status 'done' while a milestone is still running is incoherent (Codex R1 B-5 round-2).
        s = self._valid_state()  # m1 done, m2 running
        s["status"] = "done"
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_accepts_done_status_when_all_terminal(self):
        s = {
            "campaign_id": "camp-1", "status": "done",
            "cursor": {"milestone_index": 0, "subsprint_index": 0},
            "spent": {"subsprints_run": 2, "total_spawns": 0, "wall_clock_minutes": 0},
            "units": [
                {"milestone_id": "m1", "subsprint_id": "s1", "status": "done",
                 "loop_id": "u1", "attempt_nonce": 1},
                {"milestone_id": "m2", "subsprint_id": "s2", "status": "done",
                 "loop_id": "u2", "attempt_nonce": 1},
            ],
            "milestone_runtime": {
                "m1": {"phase": "merged", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "folded": [["u1", 1]]},
                # a LEAF (nothing depends on it) may terminate at 'done'-unmerged (design §7.1).
                "m2": {"phase": "done", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "folded": [["u2", 1]]},
            },
        }
        self._camp()._check_parallel_state_consistency(s)

    def test_rejects_done_status_when_dependency_target_unmerged(self):
        # m1 is a dependency-target (m2 depends_on it) ⇒ it must be 'merged', not 'done', for done.
        ms = [_ms("m1", ["s1"]), _ms("m2", ["s2"], depends_on=["m1"])]
        plan = _plan(ms, max_concurrent=2)
        d = tempfile.mkdtemp()
        camp = cp.Campaign(plan, d, _fake_run_unit(), clock=_clock())
        s = {
            "campaign_id": "camp-1", "status": "done",
            "cursor": {"milestone_index": 0, "subsprint_index": 0},
            "spent": {"subsprints_run": 2, "total_spawns": 0, "wall_clock_minutes": 0},
            "units": [
                {"milestone_id": "m1", "subsprint_id": "s1", "status": "done",
                 "loop_id": "u1", "attempt_nonce": 1},
                {"milestone_id": "m2", "subsprint_id": "s2", "status": "done",
                 "loop_id": "u2", "attempt_nonce": 1},
            ],
            "milestone_runtime": {
                "m1": {"phase": "done", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "folded": [["u1", 1]]},
                "m2": {"phase": "merged", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "folded": [["u2", 1]]},
            },
        }
        with self.assertRaises(ValueError):
            camp._check_parallel_state_consistency(s)

    # ----- Codex R1 B-5 round-3: 'done' + completeness_gap_review require QUIESCENCE ----- #
    def test_rejects_done_status_with_lingering_inflight(self):
        # Every phase terminal, but a record still carries an in-flight sub-sprint ⇒ not quiescent.
        s = {
            "campaign_id": "camp-1", "status": "done",
            "cursor": {"milestone_index": 0, "subsprint_index": 0},
            "spent": {"subsprints_run": 2, "total_spawns": 0, "wall_clock_minutes": 0},
            "units": [
                {"milestone_id": "m1", "subsprint_id": "s1", "status": "done",
                 "loop_id": "u1", "attempt_nonce": 1},
                {"milestone_id": "m2", "subsprint_id": "s2", "status": "done",
                 "loop_id": "u2", "attempt_nonce": 1},
            ],
            "milestone_runtime": {
                "m1": {"phase": "merged", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "folded": [["u1", 1]]},
                "m2": {"phase": "done", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "inflight": {"attempt_nonce": 1, "subsprint_id": "s2b"},
                       "folded": [["u2", 1]]},
            },
        }
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_rejects_gap_review_when_not_quiescent(self):
        # completeness_gap_review fires only at backlog exhaustion; a running milestone ⇒ reject.
        s = self._valid_state()  # m1 done, m2 running
        s["status"] = "paused"
        s["pause_reason"] = "completeness_gap_review"
        s["pause_checkpoint"] = "/cp/gap"
        with self.assertRaises(ValueError):
            self._camp()._check_parallel_state_consistency(s)

    def test_accepts_gap_review_when_quiescent(self):
        s = {
            "campaign_id": "camp-1", "status": "paused",
            "cursor": {"milestone_index": 0, "subsprint_index": 0},
            "spent": {"subsprints_run": 2, "total_spawns": 0, "wall_clock_minutes": 0},
            "units": [
                {"milestone_id": "m1", "subsprint_id": "s1", "status": "done",
                 "loop_id": "u1", "attempt_nonce": 1},
                {"milestone_id": "m2", "subsprint_id": "s2", "status": "done",
                 "loop_id": "u2", "attempt_nonce": 1},
            ],
            "pause_reason": "completeness_gap_review", "pause_checkpoint": "/cp/gap",
            "milestone_runtime": {
                "m1": {"phase": "merged", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "folded": [["u1", 1]]},
                "m2": {"phase": "done", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "folded": [["u2", 1]]},
            },
        }
        self._camp()._check_parallel_state_consistency(s)


class TestPhase4StateSchema(unittest.TestCase):
    """The campaign-state schema must be valid Draft 2020-12 AND actually validate a parallel
    state carrying `folded` fold-keys (Codex R1 B-1: the legacy tuple-form `items: [...]` made
    the schema invalid and crashed _load's Draft202012Validator before semantic validation)."""

    def test_state_schema_is_valid_draft202012(self):
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(
            cp._campaign_schema("campaign-state.schema.json"))

    def test_parallel_state_with_folded_validates(self):
        state = {
            "campaign_id": "camp-1", "status": "running",
            "cursor": {"milestone_index": 0, "subsprint_index": 0},
            "spent": {"subsprints_run": 1, "total_spawns": 0, "wall_clock_minutes": 0},
            "units": [{"milestone_id": "m1", "subsprint_id": "s1", "status": "done",
                       "loop_id": "u_m1s1", "attempt_nonce": 1}],
            "milestone_runtime": {
                "m1": {"phase": "done", "subsprint_index": 1, "current_attempt_nonce": 1,
                       "folded": [["u_m1s1", 1]]},
                "m2": {"phase": "running", "subsprint_index": 0, "current_attempt_nonce": 2,
                       "inflight": {"attempt_nonce": 2, "subsprint_id": "s2"}, "folded": []},
            },
        }
        cp._validate_or_raise(state, "campaign-state.schema.json", "state")  # must NOT raise

    def test_schema_rejects_inflight_missing_required_fields(self):
        # A present (non-null) inflight MUST carry attempt_nonce + subsprint_id (Codex R1 B-3).
        state = {
            "campaign_id": "camp-1", "status": "running",
            "cursor": {"milestone_index": 0, "subsprint_index": 0},
            "spent": {"subsprints_run": 0, "total_spawns": 0, "wall_clock_minutes": 0},
            "units": [],
            "milestone_runtime": {"m1": {"phase": "running", "inflight": {}}},
        }
        with self.assertRaises(ValueError):
            cp._validate_or_raise(state, "campaign-state.schema.json", "state")


if __name__ == "__main__":
    unittest.main()
