#!/usr/bin/env python3
"""Tests for loop_ingress — Loop Ingress (P4 piece 1, standalone).

stdlib unittest only. The pure decision tests have NO IO; the git-touching tests
build a THROWAWAY git repo under a tempdir, offline + deterministic (a fixed
injected ts, a fixed loop_id). Run this file directly (do NOT discover the dir —
siblings may be mid-edit):

    python -m unittest engine-kit/orchestrator/tests/test_loop_ingress.py -v

Covers:
  * decide_strategy: clean tree + no active loop → current_branch;
    dirty_tree (in force list) → recommends isolation; loop already active on
    branch → recommends isolation; honors an explicit default_strategy;
    force condition present but NOT in force_isolation_when → no escalation.
  * setup_context: new_branch actually switches the branch; new_worktree
    creates a separate working dir on its own branch AND an edit there does NOT
    change the main checkout's copy (proves isolation); current_branch stays put.
  * LoopRegistry: register + active_loops + is_loop_active_on_branch + mark_done
    (+ idempotent re-register, corrupt-file error).
  * cleanup: removes an unchanged worktree (remove_if_unchanged); keeps a
    changed one; keeps a new_branch; noop for current_branch.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Make the orchestrator package dir importable regardless of cwd.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_THIS_DIR)
if _ORCH_DIR not in sys.path:
    sys.path.insert(0, _ORCH_DIR)

import loop_ingress as li  # noqa: E402
from loop_ingress import (  # noqa: E402
    decide_strategy,
    setup_context,
    cleanup,
    is_dirty_tree,
    current_branch,
    LoopRegistry,
    LoopRecord,
    ContextHandle,
    StrategyDecision,
    RegistryError,
    StrategyError,
    STRATEGY_CURRENT_BRANCH,
    STRATEGY_NEW_BRANCH,
    STRATEGY_NEW_WORKTREE,
    FORCE_LOOP_ACTIVE_ON_BRANCH,
    FORCE_DIRTY_TREE,
    CLEANUP_REMOVE_IF_UNCHANGED,
    CLEANUP_REMOVE_IF_MERGED,
    CLEANUP_KEEP,
    STATUS_ACTIVE,
    STATUS_DONE,
)

FIXED_TS = "2026-06-16T00:00:00Z"
FIXED_TS_2 = "2026-06-16T01:00:00Z"


def _git(repo_dir, *args):
    """Run a git command in repo_dir (test helper; offline)."""
    return subprocess.run(
        ["git", "-C", repo_dir, *args],
        capture_output=True, text=True, check=True,
    ).stdout


def _make_repo(root):
    """Create a throwaway git repo with one commit on a 'main' branch. Offline:
    no remote, no fetch. Returns the repo dir."""
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    # Deterministic identity + no GPG (offline, reproducible).
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Loop Ingress Test")
    _git(repo, "config", "commit.gpgsign", "false")
    with open(os.path.join(repo, "file.txt"), "w", encoding="utf-8") as fh:
        fh.write("original\n")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


# --------------------------------------------------------------------------- #
# PURE decision logic — decide_strategy (no IO).
# --------------------------------------------------------------------------- #
class TestDecideStrategy(unittest.TestCase):
    FORCE_BOTH = {"force_isolation_when": [FORCE_LOOP_ACTIVE_ON_BRANCH, FORCE_DIRTY_TREE]}

    def test_clean_tree_no_active_loop_is_current_branch(self):
        dec = decide_strategy(
            self.FORCE_BOTH, dirty_tree=False, active_loops=[],
            target_branch="main")
        self.assertIsInstance(dec, StrategyDecision)
        self.assertEqual(dec.strategy, STRATEGY_CURRENT_BRANCH)
        self.assertEqual(dec.recommendation, STRATEGY_CURRENT_BRANCH)
        self.assertFalse(dec.escalated)
        self.assertEqual(dec.triggers, ())
        self.assertIn("default", dec.reason)

    def test_dirty_tree_in_force_list_recommends_new_branch(self):
        dec = decide_strategy(
            self.FORCE_BOTH, dirty_tree=True, active_loops=[],
            target_branch="main")
        self.assertEqual(dec.strategy, STRATEGY_CURRENT_BRANCH)  # baseline default
        self.assertEqual(dec.recommendation, STRATEGY_NEW_BRANCH)  # escalated
        self.assertTrue(dec.escalated)
        self.assertIn(FORCE_DIRTY_TREE, dec.triggers)
        self.assertIn("dirty", dec.reason)

    def test_loop_active_on_branch_recommends_new_worktree(self):
        active = [LoopRecord(
            loop_id="other", strategy=STRATEGY_NEW_BRANCH, branch="main",
            worktree=None, status=STATUS_ACTIVE, registered_at=FIXED_TS)]
        dec = decide_strategy(
            self.FORCE_BOTH, dirty_tree=False, active_loops=active,
            target_branch="main")
        self.assertEqual(dec.recommendation, STRATEGY_NEW_WORKTREE)
        self.assertTrue(dec.escalated)
        self.assertIn(FORCE_LOOP_ACTIVE_ON_BRANCH, dec.triggers)

    def test_both_conditions_worktree_dominates(self):
        active = [{"loop_id": "x", "branch": "main"}]  # dict record form
        dec = decide_strategy(
            self.FORCE_BOTH, dirty_tree=True, active_loops=active,
            target_branch="main")
        # loop-on-branch ⇒ worktree dominates the dirty ⇒ new_branch escalation.
        self.assertEqual(dec.recommendation, STRATEGY_NEW_WORKTREE)
        self.assertEqual(set(dec.triggers),
                         {FORCE_LOOP_ACTIVE_ON_BRANCH, FORCE_DIRTY_TREE})

    def test_active_loop_on_different_branch_does_not_trigger(self):
        active = [{"loop_id": "x", "branch": "feature-y"}]
        dec = decide_strategy(
            self.FORCE_BOTH, dirty_tree=False, active_loops=active,
            target_branch="main")
        self.assertFalse(dec.escalated)
        self.assertEqual(dec.recommendation, STRATEGY_CURRENT_BRANCH)

    def test_condition_not_in_force_list_does_not_escalate(self):
        # dirty_tree holds but force_isolation_when is empty ⇒ no escalation.
        dec = decide_strategy(
            {"force_isolation_when": []}, dirty_tree=True, active_loops=[],
            target_branch="main")
        self.assertFalse(dec.escalated)
        self.assertEqual(dec.recommendation, STRATEGY_CURRENT_BRANCH)
        self.assertEqual(dec.triggers, ())

    def test_only_dirty_in_force_list_loop_active_ignored(self):
        active = [{"loop_id": "x", "branch": "main"}]
        # Only dirty_tree is enabled; loop-active condition is NOT forced.
        dec = decide_strategy(
            {"force_isolation_when": [FORCE_DIRTY_TREE]},
            dirty_tree=False, active_loops=active, target_branch="main")
        self.assertFalse(dec.escalated)  # loop-active not in force list

    def test_honors_explicit_default_strategy(self):
        dec = decide_strategy(
            {"default_strategy": STRATEGY_NEW_WORKTREE,
             "force_isolation_when": [FORCE_DIRTY_TREE]},
            dirty_tree=False, active_loops=[], target_branch="main")
        self.assertEqual(dec.strategy, STRATEGY_NEW_WORKTREE)
        self.assertEqual(dec.recommendation, STRATEGY_NEW_WORKTREE)
        self.assertFalse(dec.escalated)

    def test_default_never_downgraded_by_lower_trigger(self):
        # Default already new_worktree; a dirty trigger must NOT downgrade it to
        # new_branch.
        dec = decide_strategy(
            {"default_strategy": STRATEGY_NEW_WORKTREE,
             "force_isolation_when": [FORCE_DIRTY_TREE]},
            dirty_tree=True, active_loops=[], target_branch="main")
        self.assertEqual(dec.recommendation, STRATEGY_NEW_WORKTREE)
        # It "triggered" but did not escalate (default already dominated).
        self.assertIn(FORCE_DIRTY_TREE, dec.triggers)
        self.assertFalse(dec.escalated)

    def test_none_cfg_is_all_defaults(self):
        dec = decide_strategy(None, dirty_tree=True, active_loops=[],
                              target_branch="main")
        # No force_isolation_when ⇒ even a dirty tree does not escalate.
        self.assertEqual(dec.recommendation, STRATEGY_CURRENT_BRANCH)
        self.assertFalse(dec.escalated)

    def test_no_target_branch_disables_loop_active_condition(self):
        active = [{"loop_id": "x", "branch": "main"}]
        dec = decide_strategy(
            self.FORCE_BOTH, dirty_tree=False, active_loops=active,
            target_branch=None)
        # No branch to compare ⇒ loop_active_on_branch cannot fire.
        self.assertFalse(dec.escalated)

    def test_invalid_default_strategy_raises(self):
        with self.assertRaises(StrategyError):
            decide_strategy({"default_strategy": "bogus"},
                            dirty_tree=False, active_loops=[])


# --------------------------------------------------------------------------- #
# GIT side effects — setup_context + cleanup (throwaway repo).
# --------------------------------------------------------------------------- #
class TestSetupContextGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aidazi-ingress-")
        self.repo = _make_repo(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_current_branch_stays_put(self):
        before = current_branch(self.repo)
        handle = setup_context(
            STRATEGY_CURRENT_BRANCH, repo_dir=self.repo, loop_id="L1")
        self.assertEqual(handle.strategy, STRATEGY_CURRENT_BRANCH)
        self.assertEqual(handle.work_dir, os.path.abspath(self.repo))
        self.assertEqual(handle.branch, before)
        self.assertFalse(handle.created)
        # No new branch created; HEAD unchanged.
        self.assertEqual(current_branch(self.repo), before)

    def test_new_branch_switches_branch(self):
        before = current_branch(self.repo)
        handle = setup_context(
            STRATEGY_NEW_BRANCH, repo_dir=self.repo, loop_id="L2",
            branch_name="loop/L2")
        self.assertEqual(handle.strategy, STRATEGY_NEW_BRANCH)
        self.assertEqual(handle.branch, "loop/L2")
        self.assertTrue(handle.created)
        # The repo's HEAD is now ON the new branch (it actually switched).
        self.assertEqual(current_branch(self.repo), "loop/L2")
        self.assertNotEqual(current_branch(self.repo), before)
        # Same working directory (new_branch is in-place).
        self.assertEqual(handle.work_dir, os.path.abspath(self.repo))

    def test_new_worktree_is_isolated_from_main_checkout(self):
        wt_root = os.path.join(self.tmp, "worktrees")
        handle = setup_context(
            STRATEGY_NEW_WORKTREE, repo_dir=self.repo, loop_id="L3",
            branch_name="loop/L3", worktree_root=wt_root)
        self.assertEqual(handle.strategy, STRATEGY_NEW_WORKTREE)
        self.assertTrue(handle.created)
        # The worktree is a SEPARATE directory from the main checkout.
        self.assertNotEqual(handle.work_dir, os.path.abspath(self.repo))
        self.assertTrue(os.path.isdir(handle.work_dir))
        # It is on its own branch...
        self.assertEqual(current_branch(handle.work_dir), "loop/L3")
        # ...while the MAIN checkout is still on main.
        self.assertEqual(current_branch(self.repo), "main")

        # *** PROVE ISOLATION ***: edit file.txt INSIDE the worktree.
        wt_file = os.path.join(handle.work_dir, "file.txt")
        main_file = os.path.join(self.repo, "file.txt")
        with open(wt_file, "w", encoding="utf-8") as fh:
            fh.write("EDITED IN WORKTREE\n")
        # The main checkout's copy is UNCHANGED.
        with open(main_file, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "original\n")
        with open(wt_file, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "EDITED IN WORKTREE\n")

    def test_setup_context_unknown_strategy_raises(self):
        with self.assertRaises(StrategyError):
            setup_context("bogus", repo_dir=self.repo, loop_id="L4")


# --------------------------------------------------------------------------- #
# cleanup — worktree disposition.
# --------------------------------------------------------------------------- #
class TestCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aidazi-ingress-clean-")
        self.repo = _make_repo(self.tmp)
        self.wt_root = os.path.join(self.tmp, "worktrees")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _worktree(self, loop_id, branch):
        return setup_context(
            STRATEGY_NEW_WORKTREE, repo_dir=self.repo, loop_id=loop_id,
            branch_name=branch, worktree_root=self.wt_root)

    def test_removes_unchanged_worktree(self):
        handle = self._worktree("LC1", "loop/LC1")
        self.assertTrue(os.path.isdir(handle.work_dir))
        action = cleanup(handle, cleanup_policy=CLEANUP_REMOVE_IF_UNCHANGED,
                         merged=False, changed=False)
        self.assertEqual(action, "removed")
        self.assertFalse(os.path.isdir(handle.work_dir))

    def test_keeps_changed_worktree(self):
        handle = self._worktree("LC2", "loop/LC2")
        # Make a change so `changed=True`.
        with open(os.path.join(handle.work_dir, "file.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("changed in worktree\n")
        action = cleanup(handle, cleanup_policy=CLEANUP_REMOVE_IF_UNCHANGED,
                         merged=False, changed=True)
        self.assertEqual(action, "kept")
        self.assertTrue(os.path.isdir(handle.work_dir))

    def test_removes_merged_worktree(self):
        handle = self._worktree("LC3", "loop/LC3")
        action = cleanup(handle, cleanup_policy=CLEANUP_REMOVE_IF_MERGED,
                         merged=True, changed=False)
        self.assertEqual(action, "removed")
        self.assertFalse(os.path.isdir(handle.work_dir))

    def test_keep_policy_keeps_worktree(self):
        handle = self._worktree("LC4", "loop/LC4")
        action = cleanup(handle, cleanup_policy=CLEANUP_KEEP,
                         merged=True, changed=False)
        self.assertEqual(action, "kept")
        self.assertTrue(os.path.isdir(handle.work_dir))

    def test_new_branch_is_kept_for_pr(self):
        handle = setup_context(
            STRATEGY_NEW_BRANCH, repo_dir=self.repo, loop_id="LC5",
            branch_name="loop/LC5")
        action = cleanup(handle, cleanup_policy=CLEANUP_REMOVE_IF_MERGED,
                         merged=True, changed=False)
        self.assertEqual(action, "kept")

    def test_current_branch_cleanup_is_noop(self):
        handle = setup_context(
            STRATEGY_CURRENT_BRANCH, repo_dir=self.repo, loop_id="LC6")
        action = cleanup(handle, cleanup_policy=CLEANUP_REMOVE_IF_UNCHANGED,
                         merged=True, changed=False)
        self.assertEqual(action, "noop")


# --------------------------------------------------------------------------- #
# LoopRegistry — register / active_loops / is_loop_active_on_branch / mark_done.
# --------------------------------------------------------------------------- #
class TestLoopRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aidazi-ingress-reg-")
        self.orch = os.path.join(self.tmp, ".orchestrator")
        self.reg = LoopRegistry(self.orch)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_register_and_active_loops(self):
        self.assertEqual(self.reg.active_loops(), [])
        self.reg.register("L1", STRATEGY_NEW_BRANCH, "loop/L1", None, ts=FIXED_TS)
        self.reg.register("L2", STRATEGY_NEW_WORKTREE, "loop/L2",
                          "/wt/L2", ts=FIXED_TS)
        active = self.reg.active_loops()
        self.assertEqual([r.loop_id for r in active], ["L1", "L2"])  # insertion order
        self.assertTrue(os.path.isfile(self.reg.path))
        # Persisted: a fresh registry over the same dir reads them back.
        reg2 = LoopRegistry(self.orch)
        self.assertEqual([r.loop_id for r in reg2.active_loops()], ["L1", "L2"])

    def test_is_loop_active_on_branch(self):
        self.reg.register("L1", STRATEGY_NEW_BRANCH, "feature-x", None, ts=FIXED_TS)
        self.assertTrue(self.reg.is_loop_active_on_branch("feature-x"))
        self.assertFalse(self.reg.is_loop_active_on_branch("main"))

    def test_mark_done_removes_from_active(self):
        self.reg.register("L1", STRATEGY_NEW_BRANCH, "feature-x", None, ts=FIXED_TS)
        self.assertTrue(self.reg.is_loop_active_on_branch("feature-x"))
        rec = self.reg.mark_done("L1", ts=FIXED_TS_2)
        self.assertEqual(rec.status, STATUS_DONE)
        self.assertEqual(rec.done_at, FIXED_TS_2)
        # No longer active ⇒ no longer a collision on the branch.
        self.assertEqual(self.reg.active_loops(), [])
        self.assertFalse(self.reg.is_loop_active_on_branch("feature-x"))
        # The record is still in all_loops (history preserved).
        self.assertEqual([r.loop_id for r in self.reg.all_loops()], ["L1"])

    def test_mark_done_unknown_raises(self):
        with self.assertRaises(KeyError):
            self.reg.mark_done("nope", ts=FIXED_TS)

    def test_register_is_idempotent_on_same_loop_id(self):
        self.reg.register("L1", STRATEGY_NEW_BRANCH, "b1", None, ts=FIXED_TS)
        # Re-register updates in place (no duplicate); registered_at preserved.
        self.reg.register("L1", STRATEGY_NEW_WORKTREE, "b2", "/wt", ts=FIXED_TS_2)
        all_recs = self.reg.all_loops()
        self.assertEqual(len(all_recs), 1)
        self.assertEqual(all_recs[0].branch, "b2")
        self.assertEqual(all_recs[0].strategy, STRATEGY_NEW_WORKTREE)
        self.assertEqual(all_recs[0].registered_at, FIXED_TS)  # original ts kept

    def test_decide_strategy_consumes_registry_active_loops(self):
        # End-to-end: the registry's active_loops feed decide_strategy.
        self.reg.register("other", STRATEGY_NEW_BRANCH, "main", None, ts=FIXED_TS)
        dec = decide_strategy(
            {"force_isolation_when": [FORCE_LOOP_ACTIVE_ON_BRANCH]},
            dirty_tree=False, active_loops=self.reg.active_loops(),
            target_branch="main")
        self.assertTrue(dec.escalated)
        self.assertEqual(dec.recommendation, STRATEGY_NEW_WORKTREE)

    def test_corrupt_registry_raises_clean_error(self):
        os.makedirs(self.orch, exist_ok=True)
        with open(self.reg.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        with self.assertRaises(RegistryError):
            self.reg.active_loops()


if __name__ == "__main__":
    unittest.main(verbosity=2)
