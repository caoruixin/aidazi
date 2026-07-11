"""Phase-4 (parallel campaign runner) — Cluster 3 tests: the coordinator _drive_parallel.

The coordinator launches REAL isolated worker subprocesses (campaign_worker) that run a
deterministic test-double run_loop. The OFFLINE canary (repo_dir=None ⇒ no git worktrees, no
merge gate) exercises the concurrent dispatch/fold/scheduler/budget/termination core: two
disjoint-lock milestones run concurrently to done, each unit folded exactly once, budget
accounted, and the campaign reaches DONE. stdlib unittest; POSIX (subprocess/flock)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_TESTS_DIR, _ORCH_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402

CHARTER = {"charter_id": "ch", "goal": "g"}
CLOCK_FIXED = {"kind": "fixed", "value": "2026-07-11T00:00:00Z"}


def _clock():
    n = {"i": 0}

    def tick():
        n["i"] += 1
        return f"2026-07-11T00:{n['i'] // 60:02d}:{n['i'] % 60:02d}Z"
    return tick


def _ms(mid, seq, **kw):
    m = {"id": mid, "objective": "o", "subsprint_sequence": list(seq)}
    m.update(kw)
    return m


def _parallel_plan(milestones, *, max_concurrent=2, max_subsprints=None):
    budget = {"max_concurrent": max_concurrent}
    if max_subsprints is not None:
        budget["max_subsprints"] = max_subsprints
    return {"campaign_id": "camp-1", "goal": "g", "milestones": milestones,
            "budget": budget,
            "milestone_isolation": {"default_strategy": "new_worktree",
                                    "merge_prompt_at_close": True}}


def _dummy_run_unit(*a, **k):
    return {"final_state": "advance", "spawn_count": 0, "loop_id": "x"}


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, check=True).stdout


def _make_repo(root):
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Coordinator Test")
    _git(repo, "config", "commit.gpgsign", "false")
    with open(os.path.join(repo, "file.txt"), "w", encoding="utf-8") as fh:
        fh.write("original\n")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


class TestParallelCoordinatorOffline(unittest.TestCase):
    def _run(self, plan, *, worker_entrypoint="run_loop"):
        signed = cp.stamp_signoff(plan, CHARTER)
        self.assertEqual(cp.signoff_status(signed, CHARTER), "signed")
        d = tempfile.mkdtemp()
        camp = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=None, ledger_path=None)
        camp.worker_exec = {
            "run_loop_entrypoint": f"_worker_canary_support:{worker_entrypoint}",
            "extra_sys_path": [_TESTS_DIR], "clock_policy": CLOCK_FIXED}
        return camp, camp.run(), d

    def test_two_disjoint_milestones_run_to_done(self):
        ms = [_ms("m1", ["s1"], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["b"])]
        camp, st, d = self._run(_parallel_plan(ms))
        self.assertEqual(st.status, "done")
        # Both milestones reached a terminal phase (leaf done-unmerged: no repo ⇒ no merge gate).
        rt = st.milestone_runtime
        self.assertEqual(rt["m1"]["phase"], "done")
        self.assertEqual(rt["m2"]["phase"], "done")
        # Exactly one unit folded per milestone; budget accounted once each.
        self.assertEqual(st.subsprints_run, 2)
        self.assertEqual(len(st.units), 2)
        folded = sorted(u["milestone_id"] for u in st.units)
        self.assertEqual(folded, ["m1", "m2"])
        # Each unit carries its attempt_nonce (the fold key) and a milestone_outcome recorded.
        self.assertTrue(all(u.get("attempt_nonce") == 1 for u in st.units))
        self.assertEqual(sorted(o["milestone_id"] for o in st.milestone_outcomes),
                         ["m1", "m2"])
        # No in-flight workers remain.
        self.assertEqual(sum(1 for r in rt.values() if r.get("inflight")), 0)

    def test_multi_subsprint_milestone_folds_each_subsprint(self):
        ms = [_ms("m1", ["s1", "s2"], module_locks=["a"]),
              _ms("m2", ["t1"], module_locks=["b"])]
        camp, st, d = self._run(_parallel_plan(ms))
        self.assertEqual(st.status, "done")
        self.assertEqual(st.subsprints_run, 3)          # 2 + 1
        self.assertEqual(len(st.units), 3)
        self.assertEqual(st.milestone_runtime["m1"]["subsprint_index"], 2)

    def test_signed_max_subsprints_never_exceeded(self):
        # cap=2 across two milestones ⇒ both single-sub-sprint units fit exactly.
        ms = [_ms("m1", ["s1"], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["b"])]
        camp, st, d = self._run(_parallel_plan(ms, max_subsprints=2))
        self.assertEqual(st.status, "done")
        self.assertEqual(st.subsprints_run, 2)

    def test_empty_subsprint_sequence_pauses_at_decompose_no_livelock(self):
        # Codex C3 B-1: an empty-sequence milestone is 'ready' but has nothing to dispatch —
        # it must PAUSE at milestone_decompose_required (like serial), NOT livelock; the other
        # milestone still runs to done concurrently.
        ms = [_ms("m1", [], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["b"])]
        camp, st, d = self._run(_parallel_plan(ms))
        self.assertEqual(st.status, "paused")
        rt = st.milestone_runtime
        self.assertEqual(rt["m1"]["phase"], "paused")
        self.assertEqual(rt["m1"]["pause_reason"], "milestone_decompose_required")
        self.assertEqual(rt["m2"]["phase"], "done")           # no livelock — m2 completed
        self.assertEqual(st.pause_reason, "milestone_decompose_required")  # mirror

    def test_fold_with_stale_plan_blocks_atomically(self):
        # Codex C3 B-2/B-3: a fold that finds the plan STALE folds the unit AND parks the WHOLE
        # campaign for a re-sign in ONE save (no crash window with an unblocked stale fold), and
        # the resulting global-overlay state validates.
        import campaign_worker as cw
        ms = [_ms("m1", ["s1"], module_locks=["a"])]
        signed = cp.stamp_signoff(_parallel_plan(ms), CHARTER)
        d = tempfile.mkdtemp()
        camp = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=None, ledger_path=None)
        camp._worker_mod = cw
        camp._worker_procs = {}
        camp._base_wall = 0.0
        camp._invocation_start = camp.clock()
        camp._init_milestone_runtime()
        r = camp.state.milestone_runtime["m1"]
        r["current_attempt_nonce"] = 1
        r["phase"] = "running"
        r["inflight"] = {"attempt_nonce": 1, "loop_id": "u1", "subsprint_id": "s1",
                         "work_dir": None,
                         "dispatch_epoch": camp._live_signed_scope_hash(),
                         "dispatch_freshness_slice": camp._dispatch_freshness_slice(ms[0])}
        wdir = camp._worker_dir("m1")
        camp._worker_procs["m1"] = {"proc": None, "worker_dir": wdir,
                                    "units_dir": os.path.join(wdir, "units"),
                                    "attempt_nonce": 1}
        cw._atomic_write_json(cw.result_path(wdir, 1), {
            "attempt_nonce": 1, "milestone_id": "m1", "subsprint_id": "s1",
            "dispatch_epoch": r["inflight"]["dispatch_epoch"],
            "result": {"final_state": "advance", "spawn_count": 1, "loop_id": "u1",
                       "pause_reason": None, "checkpoint_path": None}})
        # Post-dispatch tamper: the plan goes stale WHILE the unit ran.
        camp.plan["signoff"]["signed_by_human"] = False
        camp._fold_ready("m1")

        self.assertEqual(camp.state.status, "paused")
        self.assertEqual(camp.state.pause_reason, "campaign_plan_signoff")
        self.assertIsNotNone(camp.state.freshness_block)          # durable re-sign overlay
        self.assertEqual(len(camp.state.units), 1)                # the unit WAS folded
        self.assertEqual(camp.state.subsprints_run, 1)            # accounted
        self.assertIsNone(camp.state.milestone_runtime["m1"]["inflight"])  # inflight cleared
        # The global-overlay state validates (Codex C3 B-3 accepts the null-checkpoint block).
        cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(), charter=CHARTER,
                    repo_dir=None, ledger_path=None)._check_state_consistency(
                        camp.state.to_dict())

    def test_epoch_drift_holds_milestone(self):
        # Codex C3 B-5: a slice-different-but-signed fold records epoch_drift AND parks the
        # milestone — it must NOT stay 'ready' for its next sub-sprint or become terminal.
        import campaign_worker as cw
        ms = [_ms("m1", ["s1", "s2"], module_locks=["a"])]   # 2 sub-sprints: 'advance' would continue
        signed = cp.stamp_signoff(_parallel_plan(ms), CHARTER)
        d = tempfile.mkdtemp()
        camp = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=None, ledger_path=None)
        camp._worker_mod = cw
        camp._worker_procs = {}
        camp._base_wall = 0.0
        camp._invocation_start = camp.clock()
        camp._init_milestone_runtime()
        r = camp.state.milestone_runtime["m1"]
        r["current_attempt_nonce"] = 1
        r["phase"] = "running"
        epoch0 = camp._live_signed_scope_hash()
        tampered_slice = json.loads(json.dumps(camp._dispatch_freshness_slice(ms[0])))
        tampered_slice["wrapper"]["goal"] = "DIFFERENT"      # slice differs from the live slice
        r["inflight"] = {"attempt_nonce": 1, "loop_id": "u1", "subsprint_id": "s1",
                         "work_dir": None,
                         "dispatch_epoch": "STALE_" + str(epoch0),   # != live epoch
                         "dispatch_freshness_slice": tampered_slice}
        wdir = camp._worker_dir("m1")
        camp._worker_procs["m1"] = {"proc": None, "worker_dir": wdir,
                                    "units_dir": os.path.join(wdir, "units"),
                                    "attempt_nonce": 1}
        cw._atomic_write_json(cw.result_path(wdir, 1), {
            "attempt_nonce": 1, "milestone_id": "m1", "subsprint_id": "s1",
            "dispatch_epoch": r["inflight"]["dispatch_epoch"],
            "result": {"final_state": "advance", "spawn_count": 1, "loop_id": "u1",
                       "pause_reason": None, "checkpoint_path": None}})
        camp._fold_ready("m1")

        r = camp.state.milestone_runtime["m1"]
        self.assertIsNotNone(r.get("epoch_drift"))            # durable gate recorded
        self.assertEqual(r["phase"], "paused")                # HELD — not 'ready' for s2
        self.assertEqual(r["pause_reason"], "epoch_drift")
        self.assertEqual(len(camp.state.units), 1)            # the unit WAS folded (authorized)
        # not re-admitted, and the campaign is NOT all-terminal (cannot reach DONE this run).
        self.assertNotIn("m1", cp.parallel_ready_set(
            camp.milestones, camp.state.milestone_runtime))
        self.assertIsNotNone(
            camp._parallel_first_nonterminal(camp.state.milestone_runtime))
        camp._check_state_consistency(camp.state.to_dict())   # round-trips clean

    def test_epoch_drift_overrides_completion_merge_gate(self):
        # Codex C3 B-7: a slice-different-but-signed COMPLETION that opens the merge gate must be
        # HELD at epoch_drift, NOT left actively paused at milestone_merge (else stale scope could
        # merge on resume without re-validation). The displaced merge checkpoint is preserved.
        import campaign_worker as cw
        rd = tempfile.mkdtemp()
        ms = [_ms("m1", ["s1"], module_locks=["a"])]   # single sub-sprint ⇒ 'advance' completes
        signed = cp.stamp_signoff(_parallel_plan(ms), CHARTER)
        d = os.path.join(rd, "run")
        camp = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=rd, ledger_path=None)   # ingress ENABLED
        camp._worker_mod = cw
        camp._worker_procs = {}
        camp._base_wall = 0.0
        camp._invocation_start = camp.clock()
        camp._init_milestone_runtime()
        r = camp.state.milestone_runtime["m1"]
        r["current_attempt_nonce"] = 1
        r["phase"] = "running"
        # a milestone context (branch != trunk) so the completion opens the merge gate.
        r["context"] = {"milestone_id": "m1", "strategy": "new_worktree",
                        "branch": "milestone/camp-1/m1", "work_dir": rd, "worktree": rd,
                        "base_ref": "main", "repo_dir": rd}
        tampered = json.loads(json.dumps(camp._dispatch_freshness_slice(ms[0])))
        tampered["wrapper"]["goal"] = "DIFFERENT"
        epoch0 = camp._live_signed_scope_hash()
        r["inflight"] = {"attempt_nonce": 1, "loop_id": "u1", "subsprint_id": "s1",
                         "work_dir": rd, "dispatch_epoch": "STALE_" + str(epoch0),
                         "dispatch_freshness_slice": tampered}
        wdir = camp._worker_dir("m1")
        camp._worker_procs["m1"] = {"proc": None, "worker_dir": wdir,
                                    "units_dir": os.path.join(wdir, "units"),
                                    "attempt_nonce": 1}
        cw._atomic_write_json(cw.result_path(wdir, 1), {
            "attempt_nonce": 1, "milestone_id": "m1", "subsprint_id": "s1",
            "dispatch_epoch": r["inflight"]["dispatch_epoch"],
            "result": {"final_state": "advance", "spawn_count": 1, "loop_id": "u1",
                       "pause_reason": None, "checkpoint_path": None}})
        camp._fold_ready("m1")

        r = camp.state.milestone_runtime["m1"]
        self.assertEqual(r["phase"], "paused")
        self.assertEqual(r["pause_reason"], "epoch_drift")    # NOT milestone_merge
        self.assertIn("displaced_merge_checkpoint", r["epoch_drift"])  # preserved for C4
        self.assertIsNotNone(r["epoch_drift"]["displaced_merge_checkpoint"])
        camp._check_state_consistency(camp.state.to_dict())

    def _crash_camp(self, ms):
        import campaign_worker as cw
        signed = cp.stamp_signoff(_parallel_plan(ms), CHARTER)
        d = tempfile.mkdtemp()
        camp = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=None, ledger_path=None)
        camp._worker_mod = cw
        camp._worker_procs = {}
        camp._base_wall = 0.0
        camp._invocation_start = camp.clock()
        camp._init_milestone_runtime()
        return camp, cw

    def test_crash_recover_fences_dead_worker(self):
        # §5.5: a durable inflight with NO result + NO live flock ⇒ dead worker ⇒ fence + bump
        # nonce + re-dispatch (a stale lower-nonce result can never mask the fresh attempt).
        ms = [_ms("m1", ["s1"], module_locks=["a"])]
        camp, cw = self._crash_camp(ms)
        r = camp.state.milestone_runtime["m1"]
        r["current_attempt_nonce"] = 1
        r["phase"] = "running"
        r["inflight"] = {"attempt_nonce": 1, "loop_id": "u1", "subsprint_id": "s1",
                         "work_dir": None, "dispatch_epoch": "H",
                         "dispatch_freshness_slice": {}}
        camp._crash_recover_parallel()
        r = camp.state.milestone_runtime["m1"]
        self.assertIsNone(r["inflight"])
        self.assertEqual(r["current_attempt_nonce"], 2)      # bumped
        self.assertEqual(r["phase"], "ready")                # re-dispatchable

    def test_crash_recover_folds_completed_result(self):
        # §5.5: a durable inflight whose live-attempt result already landed ⇒ FOLD it on recovery.
        ms = [_ms("m1", ["s1"], module_locks=["a"])]
        camp, cw = self._crash_camp(ms)
        r = camp.state.milestone_runtime["m1"]
        r["current_attempt_nonce"] = 1
        r["phase"] = "running"
        r["inflight"] = {"attempt_nonce": 1, "loop_id": "u1", "subsprint_id": "s1",
                         "work_dir": None,
                         "dispatch_epoch": camp._live_signed_scope_hash(),
                         "dispatch_freshness_slice": camp._dispatch_freshness_slice(ms[0])}
        wdir = camp._worker_dir("m1")
        cw._atomic_write_json(cw.result_path(wdir, 1), {
            "attempt_nonce": 1, "milestone_id": "m1", "subsprint_id": "s1",
            "dispatch_epoch": r["inflight"]["dispatch_epoch"],
            "result": {"final_state": "advance", "spawn_count": 1, "loop_id": "u1",
                       "pause_reason": None, "checkpoint_path": None}})
        camp._crash_recover_parallel()
        r = camp.state.milestone_runtime["m1"]
        self.assertIsNone(r["inflight"])                     # folded
        self.assertEqual(r["phase"], "done")                 # single sub-sprint → complete
        self.assertEqual(len(camp.state.units), 1)

    def test_budget_resume_requires_decision_raise_cap_or_abort(self):
        # Codex R3 B-9: parallel campaign_budget_exhausted is serial-equivalent — it REQUIRES a
        # decision (no decision ⇒ re-pause), raise_cap re-reads the signed budget + proceeds,
        # abort ends.
        ms = [_ms("m1", ["s1"], module_locks=["a"])]
        signed = cp.stamp_signoff(_parallel_plan(ms, max_subsprints=1), CHARTER)
        d = tempfile.mkdtemp()
        camp = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=None, ledger_path=None)
        import campaign_worker as cw
        camp._worker_mod = cw
        camp._worker_procs = {}
        camp._base_wall = 0.0
        camp._invocation_start = camp.clock()
        camp._init_milestone_runtime()

        def _budget(status="paused"):
            camp.state.status = status
            camp.state.pause_reason = "campaign_budget_exhausted"
            camp.state.pause_checkpoint = None

        _budget()
        self.assertEqual(camp._handle_resume_parallel(None), "paused")   # no decision → re-pause
        _budget()
        self.assertEqual(
            camp._handle_resume_parallel(lambda r, c: {"choice": "raise_cap"}), "proceed")
        _budget()
        self.assertEqual(
            camp._handle_resume_parallel(lambda r, c: {"choice": "abort"}), "ended")
        self.assertEqual(camp.state.status, "ended")

    def test_budget_raise_cap_requires_resign_when_stale(self):
        # Codex R3 B-9: a raise_cap that raises the (H-bound) budget WITHOUT re-signing is STALE ⇒
        # block for re-sign, and the freshness_block preserves the original budget gate.
        ms = [_ms("m1", ["s1"], module_locks=["a"])]
        signed = cp.stamp_signoff(_parallel_plan(ms, max_subsprints=1), CHARTER)
        d = tempfile.mkdtemp()
        camp = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=None, ledger_path=None)
        import campaign_worker as cw
        camp._worker_mod = cw
        camp._worker_procs = {}
        camp._base_wall = 0.0
        camp._invocation_start = camp.clock()
        camp._init_milestone_runtime()
        camp.state.status = "paused"
        camp.state.pause_reason = "campaign_budget_exhausted"
        camp.plan["budget"]["max_subsprints"] = 5   # raised IN-MEMORY (H now stale, not re-signed)
        out = camp._handle_resume_parallel(lambda r, c: {"choice": "raise_cap"})
        self.assertEqual(out, "paused")
        self.assertEqual(camp.state.pause_reason, "campaign_plan_signoff")   # blocked for re-sign
        self.assertEqual((camp.state.freshness_block or {}).get("original_pause_reason"),
                         "campaign_budget_exhausted")

    def test_halt_resume_adds_provisional_then_commits_at_fold(self):
        # Codex R3 B-8: proceed adds the ack PROVISIONALLY (not permanent); the fold commit
        # promotes it → GLOBAL permanent.
        ms = [_ms("m1", ["s1"], module_locks=["a"])]
        camp, _cw = self._crash_camp(ms)
        r = camp.state.milestone_runtime["m1"]
        r["phase"] = "paused"
        r["pause_reason"] = "halt_condition_met"
        r["halt_condition_pending"] = {"ack_key": ["c1", "dig", "m1"], "condition_id": "c1",
                                       "signed_scope_hash": camp._live_signed_scope_hash()}
        out = camp._resolve_halt_parallel("m1", r, {"milestone_id": "m1", "choice": "proceed"})
        self.assertEqual(out, "proceed")
        self.assertEqual(r["halt_condition_provisional"], [["c1", "dig", "m1"]])  # PROVISIONAL
        self.assertEqual(camp.state.halt_condition_acks, [])                      # NOT permanent
        self.assertEqual(r["phase"], "ready")                                    # re-dispatch
        camp._halt_commit_cascade_parallel(r)                                    # (at fold)
        self.assertIn(["c1", "dig", "m1"], camp.state.halt_condition_acks)       # promoted
        self.assertEqual(r["halt_condition_provisional"], [])

    def test_halt_epoch_rearm_flushes_stale_provisional(self):
        # Codex R3 B-8: a re-sign between halt and proceed re-arms the cascade — a stale-epoch
        # provisional ack is FLUSHED so it cannot suppress a condition in the new epoch.
        ms = [_ms("m1", ["s1"], module_locks=["a"])]
        camp, _cw = self._crash_camp(ms)
        r = camp.state.milestone_runtime["m1"]
        r["halt_condition_provisional"] = [["c1", "dig", "m1"]]
        r["halt_condition_pending"] = {"signed_scope_hash": "STALE_EPOCH",
                                       "milestone_id": "m1", "condition_id": "c1"}
        camp._halt_epoch_recheck_parallel(r)     # live epoch != STALE_EPOCH ⇒ flush
        self.assertEqual(r["halt_condition_provisional"], [])
        self.assertIsNone(r["halt_condition_pending"])

    def test_deliver_followup_resume_advances_on_insertion(self):
        # Codex R3 B-5: a milestone parked at deliver_followup_required with an inserted sub-sprint
        # at subsprint_index+1 (not in the paused-time baseline) advances (fresh-signed plan).
        ms = [_ms("m1", ["s1", "s1-gapfix-1"], module_locks=["a"])]
        signed = cp.stamp_signoff(_parallel_plan(ms), CHARTER)
        d = tempfile.mkdtemp()
        camp = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=None, ledger_path=None)
        import campaign_worker as cw
        camp._worker_mod = cw
        camp._worker_procs = {}
        camp._base_wall = 0.0
        camp._invocation_start = camp.clock()
        camp._init_milestone_runtime()
        r = camp.state.milestone_runtime["m1"]
        r["phase"] = "paused"
        r["pause_reason"] = "deliver_followup_required"
        r["subsprint_index"] = 0
        r["followup_baseline_seq"] = ["s1"]   # baseline BEFORE the insertion
        camp.state.status = "paused"
        camp.state.pause_reason = "deliver_followup_required"
        out = camp._handle_resume_parallel(None)   # plan-edit resolved (no decision file)
        self.assertEqual(out, "proceed")
        self.assertEqual(r["subsprint_index"], 1)     # advanced to the inserted follow-up
        self.assertEqual(r["phase"], "ready")
        self.assertIsNone(r["followup_baseline_seq"])

    def test_budget_exhausted_state_validates(self):
        # Codex C3 B-6: campaign_budget_exhausted is a validator-accepted coordinator-global
        # null-checkpoint pause (may coexist with a done milestone).
        camp, _st, _d = self._run(_parallel_plan(
            [_ms("m1", ["s1"], module_locks=["a"])]))   # any signed camp for the validator
        s = {"campaign_id": "camp-1", "status": "paused",
             "cursor": {"milestone_index": 0, "subsprint_index": 0},
             "spent": {"subsprints_run": 1, "total_spawns": 0, "wall_clock_minutes": 0},
             "units": [{"milestone_id": "m1", "subsprint_id": "s1", "status": "done",
                        "loop_id": "u1", "attempt_nonce": 1}],
             "pause_reason": "campaign_budget_exhausted", "pause_checkpoint": None,
             "milestone_runtime": {
                 "m1": {"phase": "done", "subsprint_index": 1, "current_attempt_nonce": 1,
                        "folded": [["u1", 1]]}}}
        camp._check_parallel_state_consistency(s)   # accepted (null-checkpoint global drain)

    def test_dependency_stall_repauses_dep_target_at_merge(self):
        # Codex C3 B-6: a dep-target at 'done'-unmerged (offline, no merge gate) with a blocked
        # dependent re-pauses the dep-target at milestone_merge (per-milestone, no new kind), and
        # the resulting state validates.
        ms = [_ms("m1", ["s1"], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["b"], depends_on=["m1"])]
        camp, st, d = self._run(_parallel_plan(ms))
        self.assertEqual(st.status, "paused")
        rt = st.milestone_runtime
        self.assertEqual(rt["m1"]["phase"], "paused")
        self.assertEqual(rt["m1"]["pause_reason"], "milestone_merge")   # re-paused to unblock m2
        self.assertEqual(rt["m2"]["phase"], "ready")                    # never ran (blocked)
        self.assertEqual(st.pause_reason, "milestone_merge")            # mirror
        cp.Campaign(cp.stamp_signoff(_parallel_plan(ms), CHARTER), d, _dummy_run_unit,
                    clock=_clock(), charter=CHARTER, repo_dir=None,
                    ledger_path=None)._check_state_consistency(st.to_dict())


class TestParallelCoordinatorGit(unittest.TestCase):
    """N=2 disjoint-lock canary in REAL git worktrees (design §7): two milestones run
    concurrently in their own worktrees, each pausing at the milestone_merge human gate
    (§1.7-D — the engine never auto-merges; merge EXECUTION on resume is Cluster 4)."""

    def test_two_milestones_pause_at_milestone_merge(self):
        root = tempfile.mkdtemp()
        repo = _make_repo(root)
        ms = [_ms("m1", ["s1"], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["b"])]
        signed = cp.stamp_signoff(_parallel_plan(ms), CHARTER)
        d = os.path.join(root, "run")
        camp = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=repo, ledger_path=None)
        camp.worker_exec = {"run_loop_entrypoint": "_worker_canary_support:run_loop",
                            "extra_sys_path": [_TESTS_DIR], "clock_policy": CLOCK_FIXED}
        st = camp.run()

        # Parked at the human merge gate(s): status PAUSED, both milestones paused at
        # milestone_merge, the top-level mirror = the OLDEST (topological) paused milestone.
        self.assertEqual(st.status, "paused")
        rt = st.milestone_runtime
        self.assertEqual(rt["m1"]["phase"], "paused")
        self.assertEqual(rt["m2"]["phase"], "paused")
        self.assertEqual(rt["m1"]["pause_reason"], "milestone_merge")
        self.assertEqual(rt["m2"]["pause_reason"], "milestone_merge")
        self.assertEqual(st.pause_reason, "milestone_merge")     # mirror
        # Both ran concurrently to done: 2 units folded, both milestone_outcomes stamped, each
        # milestone got its own isolated branch.
        self.assertEqual(st.subsprints_run, 2)
        self.assertEqual(len(st.units), 2)
        self.assertEqual(sorted(o["milestone_id"] for o in st.milestone_outcomes),
                         ["m1", "m2"])
        branches = _git(repo, "branch", "--list")
        self.assertIn("milestone/camp-1/m1", branches)
        self.assertIn("milestone/camp-1/m2", branches)
        # Neither branch is merged into trunk yet (merge is the human-gated Cluster-4 step).
        self.assertEqual(sum(1 for r in rt.values() if r.get("inflight")), 0)
        # The parallel state validates against its own consistency gate (round-trips clean).
        cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(), charter=CHARTER,
                    repo_dir=repo, ledger_path=None)._check_state_consistency(st.to_dict())

    def test_resume_merges_both_to_done(self):
        # Cluster 4: continue the N=2 canary — resume merge_now for each parked milestone_merge
        # (one --resume per parked pause, §6.3) → both milestones merged → campaign DONE.
        root = tempfile.mkdtemp()
        repo = _make_repo(root)
        ms = [_ms("m1", ["s1"], module_locks=["a"]),
              _ms("m2", ["s2"], module_locks=["b"])]
        signed = cp.stamp_signoff(_parallel_plan(ms), CHARTER)
        d = os.path.join(root, "run")

        def _mk():
            c = cp.Campaign(signed, d, _dummy_run_unit, clock=_clock(),
                            charter=CHARTER, repo_dir=repo, ledger_path=None)
            c.worker_exec = {"run_loop_entrypoint": "_worker_canary_support:run_loop",
                             "extra_sys_path": [_TESTS_DIR], "clock_policy": CLOCK_FIXED}
            return c

        st = _mk().run()
        self.assertEqual(st.status, "paused")            # both parked at milestone_merge

        def _resolver(mid):
            return lambda reason, checkpoint: {"milestone_id": mid, "choice": "merge_now"}

        st2 = _mk().run(resume=True, decision_resolver=_resolver("m1"))
        self.assertEqual(st2.milestone_runtime["m1"]["phase"], "merged")
        self.assertEqual(st2.status, "paused")           # m2 still parked
        st3 = _mk().run(resume=True, decision_resolver=_resolver("m2"))
        self.assertEqual(st3.status, "done")
        self.assertEqual(st3.milestone_runtime["m1"]["phase"], "merged")
        self.assertEqual(st3.milestone_runtime["m2"]["phase"], "merged")

    def test_resume_epoch_drift_restores_displaced_merge_gate(self):
        # Cluster 4: resolving an epoch_drift hold that had displaced a merge gate RESTORES the
        # milestone_merge gate (the human still merges the re-validated milestone).
        rd = tempfile.mkdtemp()
        ms = [_ms("m1", ["s1"], module_locks=["a"])]
        signed = cp.stamp_signoff(_parallel_plan(ms), CHARTER)
        camp = cp.Campaign(signed, os.path.join(rd, "run"), _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=rd, ledger_path=None)
        # The drift clears ONLY when the live slice re-aligns with the DISPATCH slice (Codex R3
        # B-4). Store the current live slice as the dispatch slice so the re-check passes.
        aligned_slice = camp._dispatch_freshness_slice(ms[0])
        camp.state.milestone_runtime["m1"] = {
            "phase": "paused", "subsprint_index": 1, "current_attempt_nonce": 1,
            "folded": [["u1", 1]], "pause_reason": "epoch_drift", "pause_checkpoint": None,
            "epoch_drift": {"dispatch_freshness_slice": aligned_slice,
                            "displaced_merge_checkpoint": "/cp/m1.md",
                            "displaced_pending_milestone_advance": True}}
        r = camp.state.milestone_runtime["m1"]
        out = camp._resolve_epoch_drift_parallel(
            "m1", r, {"milestone_id": "m1", "choice": "revalidate"})
        self.assertEqual(out, "proceed")
        self.assertIsNone(r["epoch_drift"])                       # gate cleared (slice re-aligned)
        self.assertEqual(r["phase"], "paused")                    # merge gate RESTORED
        self.assertEqual(r["pause_reason"], "milestone_merge")
        self.assertEqual(r["pause_checkpoint"], "/cp/m1.md")

    def test_epoch_drift_resume_repauses_when_still_drifted(self):
        # Codex R3 B-4: if the live slice does NOT re-align with the dispatch slice, the drift
        # HOLDS (re-pause) — a signed/proceed decision alone never clears it.
        rd = tempfile.mkdtemp()
        ms = [_ms("m1", ["s1"], module_locks=["a"])]
        signed = cp.stamp_signoff(_parallel_plan(ms), CHARTER)
        camp = cp.Campaign(signed, os.path.join(rd, "run"), _dummy_run_unit, clock=_clock(),
                           charter=CHARTER, repo_dir=rd, ledger_path=None)
        stale_slice = json.loads(json.dumps(camp._dispatch_freshness_slice(ms[0])))
        stale_slice["wrapper"]["goal"] = "STILL DIFFERENT"        # != live slice
        camp.state.milestone_runtime["m1"] = {
            "phase": "paused", "subsprint_index": 1, "current_attempt_nonce": 1,
            "folded": [["u1", 1]], "pause_reason": "epoch_drift", "pause_checkpoint": None,
            "epoch_drift": {"dispatch_freshness_slice": stale_slice,
                            "displaced_merge_checkpoint": "/cp/m1.md"}}
        r = camp.state.milestone_runtime["m1"]
        out = camp._resolve_epoch_drift_parallel(
            "m1", r, {"milestone_id": "m1", "choice": "revalidate"})
        self.assertEqual(out, "paused")
        self.assertIsNotNone(r["epoch_drift"])                    # HELD — not cleared


class TestParallelResolver(unittest.TestCase):
    """The REAL file-based decision resolver is parallel-aware (Codex R3 B-3): it binds against
    milestone_runtime[decision.milestone_id] and PRESERVES milestone_id so _handle_resume_parallel
    can select the right parked milestone (not the top-level mirror)."""

    _CP1 = "/cp/20260711-000000__milestone_merge__m1.md"
    _CP2 = "/cp/20260711-000001__milestone_merge__m2.md"

    def _home_with_two_merge_pauses(self):
        home = tempfile.mkdtemp()
        with open(os.path.join(home, "campaign-state.json"), "w", encoding="utf-8") as fh:
            json.dump({"campaign_id": "camp-1", "status": "paused",
                       "cursor": {"milestone_index": 0, "subsprint_index": 0},
                       "spent": {"subsprints_run": 2, "total_spawns": 0,
                                 "wall_clock_minutes": 0}, "units": [],
                       "pause_reason": "milestone_merge", "pause_checkpoint": self._CP1,
                       "milestone_runtime": {
                           "m1": {"phase": "paused", "pause_reason": "milestone_merge",
                                  "pause_checkpoint": self._CP1},
                           "m2": {"phase": "paused", "pause_reason": "milestone_merge",
                                  "pause_checkpoint": self._CP2}}}, fh)
        return home

    def test_resolver_binds_target_milestone_and_preserves_id(self):
        import run_loop as rl
        home = self._home_with_two_merge_pauses()
        dec = os.path.join(home, "dec.json")
        with open(dec, "w", encoding="utf-8") as fh:
            json.dump({"campaign_id": "camp-1", "pause_reason": "milestone_merge",
                       "checkpoint": os.path.basename(self._CP2), "milestone_id": "m2",
                       "choice": "merge_now"}, fh)
        resolver = rl.make_campaign_decision_resolver("camp-1", dec, home)
        # The top-level mirror is m1, but the decision targets m2 — the parallel resolver binds
        # m2 (validated against its runtime entry) and PRESERVES milestone_id.
        self.assertEqual(resolver("milestone_merge", self._CP1),
                         {"milestone_id": "m2", "choice": "merge_now"})

    def test_resolver_refuses_unknown_or_unpaused_milestone(self):
        import run_loop as rl
        home = self._home_with_two_merge_pauses()
        dec = os.path.join(home, "dec.json")
        with open(dec, "w", encoding="utf-8") as fh:
            json.dump({"campaign_id": "camp-1", "pause_reason": "milestone_merge",
                       "checkpoint": os.path.basename(self._CP2), "milestone_id": "ghost",
                       "choice": "merge_now"}, fh)
        resolver = rl.make_campaign_decision_resolver("camp-1", dec, home)
        self.assertIsNone(resolver("milestone_merge", self._CP1))


class TestParallelReporting(unittest.TestCase):
    """run_loop phase-derived output + pauses[] (design §3.2.1/§6.3), additive to
    CAMPAIGN_STATUS=."""

    def _print(self, result):
        import io
        import contextlib
        import run_loop as rl
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rl.print_campaign_result(result)
        return buf.getvalue()

    def _parallel_result(self):
        return {
            "campaign_id": "camp-1", "campaign_home": "/tmp/x", "status": "paused",
            "pause_reason": "milestone_merge", "pause_checkpoint": "/cp/m1.md",
            "milestone_index": 0, "milestones_total": 2, "milestones_complete": 0,
            "subsprints_run": 2, "total_spawns": 0, "exit_code": 10,
            "milestones": [{"milestone_id": "m1", "phase": "paused",
                            "pause_reason": "milestone_merge", "pause_checkpoint": "/cp/m1.md"},
                           {"milestone_id": "m2", "phase": "paused",
                            "pause_reason": "milestone_merge", "pause_checkpoint": "/cp/m2.md"}],
            "pauses": [{"milestone_id": "m1", "subsprint_id": None,
                        "pause_reason": "milestone_merge", "checkpoint": "m1.md",
                        "condition_id": None, "loop_id": None},
                       {"milestone_id": "m2", "subsprint_id": None,
                        "pause_reason": "milestone_merge", "checkpoint": "m2.md",
                        "condition_id": None, "loop_id": None}],
        }

    def test_phase_derived_progress_and_all_pauses(self):
        out = self._print(self._parallel_result())
        self.assertIn("phase-derived", out)                 # not the (0,0) mirror
        self.assertIn("legacy mirror", out)
        self.assertIn("m1=paused", out)
        self.assertIn("parked pauses  : 2", out)             # BOTH pauses surfaced (§6.3)
        self.assertIn("CAMPAIGN_STATUS=", out)               # stable contract preserved
        self.assertIn("CAMPAIGN_MILESTONES=", out)           # additive parallel contract
        machine = [ln for ln in out.splitlines()
                   if ln.startswith("CAMPAIGN_MILESTONES=")][0]
        parsed = json.loads(machine.split("=", 1)[1])
        self.assertEqual(len(parsed["pauses"]), 2)
        self.assertEqual(parsed["milestones_complete"], 0)

    def test_serial_result_output_unchanged(self):
        # A serial result (no 'milestones' key) keeps the cursor line + no parallel contract.
        serial = {"campaign_id": "c", "campaign_home": "/tmp/y", "status": "done",
                  "milestone_index": 2, "milestones_total": 2, "subsprints_run": 3,
                  "total_spawns": 1, "exit_code": 0}
        out = self._print(serial)
        self.assertIn("milestones     : 2/2 complete", out)
        self.assertNotIn("phase-derived", out)
        self.assertNotIn("CAMPAIGN_MILESTONES=", out)


if __name__ == "__main__":
    unittest.main()
