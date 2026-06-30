"""Campaign-tier milestone git isolation + merge gate (stdlib unittest; real git)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
_SCHED_DIR = os.path.join(_ENGINE_KIT_DIR, "scheduling")
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _SCHED_DIR, os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402
import loop_ingress as li  # noqa: E402


def _clock():
    n = {"i": 0}

    def tick() -> str:
        n["i"] += 1
        return f"2026-06-24T00:{n['i'] // 60:02d}:{n['i'] % 60:02d}Z"
    return tick


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, check=True)


def _make_repo(root):
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    with open(os.path.join(repo, "README"), "w") as fh:
        fh.write("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _plan_two_ms(**kw):
    return {
        "campaign_id": kw.pop("campaign_id", "camp-iso"),
        "goal": "two milestones",
        "signed_by_human": True,
        "trunk_branch": "main",
        "milestone_isolation": {
            "default_strategy": "new_branch",
            "merge_prompt_at_close": True,
            **(kw.pop("milestone_isolation", {}) or {}),
        },
        "milestones": [
            {"id": "m1", "objective": "first",
             "subsprint_sequence": ["s1"]},
            {"id": "m2", "objective": "second",
             "subsprint_sequence": ["s2"]},
        ],
        **kw,
    }


class TestMilestoneIsolationGit(unittest.TestCase):
    def test_milestone_new_branch_and_merge_now(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _make_repo(d)
            calls = []

            def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                         resume=False, functional_acceptance=None, repo_dir=None):
                calls.append({"subsprint_id": subsprint_id, "milestone_id": milestone_id,
                              "repo_dir": repo_dir})
                wt = repo_dir or repo
                with open(os.path.join(wt, "m1.txt"), "w") as fh:
                    fh.write("m1 work\n")
                _git(wt, "add", "m1.txt")
                _git(wt, "commit", "-q", "-m", "m1 work")
                return {"final_state": "done", "spawn_count": 1, "loop_id": "u1"}

            plan = _plan_two_ms(milestones=[
                {"id": "m1", "objective": "first",
                 "subsprint_sequence": ["s1"]},
            ])
            camp_dir = os.path.join(d, "camp")
            camp = cp.Campaign(plan, camp_dir, run_unit, clock=_clock(), repo_dir=repo)
            st = camp.run()
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "milestone_merge")
            self.assertTrue(st.pending_milestone_advance)
            self.assertIsNotNone(st.milestone_context)
            branch = st.milestone_context["branch"]
            self.assertTrue(branch.startswith("milestone/"))

            cpt = st.pause_checkpoint
            decision = {
                "campaign_id": "camp-iso",
                "milestone_id": "m1",
                "pause_reason": "milestone_merge",
                "checkpoint": os.path.basename(cpt),
                "choice": "merge_now",
            }
            dec_path = os.path.join(d, "decision.json")
            with open(dec_path, "w") as fh:
                json.dump(decision, fh)

            import run_loop as rl  # noqa: E402
            resolver = rl.make_campaign_decision_resolver(
                "camp-iso", dec_path, camp_dir)
            st2 = cp.Campaign(plan, camp_dir, run_unit, clock=_clock(),
                              repo_dir=repo).run(resume=True, decision_resolver=resolver)
            self.assertEqual(st2.status, cp.STATUS_DONE)
            self.assertEqual(st2.milestone_index, 1)
            # merge landed on main
            out = _git(repo, "log", "--oneline", "-n", "3").stdout
            self.assertIn("merge", out.lower())
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["repo_dir"], repo)

    def test_keep_branch_skips_merge(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _make_repo(d)

            def run_unit(subsprint_id, **kw):
                return {"final_state": "done", "spawn_count": 0, "loop_id": "u1"}

            plan = _plan_two_ms(milestones=[
                {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
            ])
            camp_dir = os.path.join(d, "camp")
            camp = cp.Campaign(plan, camp_dir, run_unit, clock=_clock(), repo_dir=repo)
            st = camp.run()
            self.assertEqual(st.pause_reason, "milestone_merge")
            decision = {
                "campaign_id": "camp-iso",
                "milestone_id": "m1",
                "pause_reason": "milestone_merge",
                "checkpoint": os.path.basename(st.pause_checkpoint),
                "choice": "keep_branch",
            }
            dec_path = os.path.join(d, "decision.json")
            with open(dec_path, "w") as fh:
                json.dump(decision, fh)
            import run_loop as rl
            resolver = rl.make_campaign_decision_resolver(
                "camp-iso", dec_path, camp_dir)
            st2 = cp.Campaign(plan, camp_dir, run_unit, clock=_clock(),
                              repo_dir=repo).run(resume=True, decision_resolver=resolver)
            self.assertEqual(st2.status, cp.STATUS_DONE)
            # main should still be at init only (one commit)
            count = _git(repo, "rev-list", "--count", "main").stdout.strip()
            self.assertEqual(count, "1")


class TestMilestoneMergeFreshnessGate(unittest.TestCase):
    """Track-2 T2-A B5: the milestone_merge gate is freshness-checked BEFORE the irreversible
    merge — a post-sign edit blocks for re-sign while preserving the gate; re-signing the
    edited plan resumes the ORIGINAL merge."""

    _CHARTER = {"tooling": {"acceptance": {"functional": {"mode": "static"}}}}

    def _signed_iso_plan(self):
        plan = {
            "campaign_id": "camp-iso-f1", "goal": "iso f1", "trunk_branch": "main",
            "milestone_isolation": {"default_strategy": "new_branch",
                                    "merge_prompt_at_close": True},
            "milestones": [{"id": "m1", "objective": "first",
                            "subsprint_sequence": ["s1"], "covers_req_ids": ["REQ-1"]}],
        }
        return cp.stamp_signoff(plan, self._CHARTER, signed_at="t")

    def _run_unit(self, repo):
        def run_unit(subsprint_id, **kw):
            wt = kw.get("repo_dir") or repo
            with open(os.path.join(wt, "m1.txt"), "w") as fh:
                fh.write("m1 work\n")
            _git(wt, "add", "m1.txt")
            _git(wt, "commit", "-q", "-m", "m1 work")
            return {"final_state": "done", "spawn_count": 1, "loop_id": "u1"}
        return run_unit

    def test_merge_blocks_on_stale_then_resigns(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _make_repo(d)
            run_unit = self._run_unit(repo)
            signed = self._signed_iso_plan()
            camp_dir = os.path.join(d, "camp")
            st = cp.Campaign(signed, camp_dir, run_unit, clock=_clock(),
                             repo_dir=repo, charter=self._CHARTER).run()
            self.assertEqual(st.pause_reason, "milestone_merge")
            cpt = os.path.basename(st.pause_checkpoint)

            import run_loop as rl  # noqa: E402
            dec = {"campaign_id": "camp-iso-f1", "milestone_id": "m1",
                   "pause_reason": "milestone_merge", "checkpoint": cpt,
                   "choice": "merge_now"}
            dec_path = os.path.join(d, "decision.json")
            with open(dec_path, "w") as fh:
                json.dump(dec, fh)
            resolver = rl.make_campaign_decision_resolver(
                "camp-iso-f1", dec_path, camp_dir)

            # Edit the plan AFTER signoff → stale; merge_now must BLOCK (no merge).
            stale = json.loads(json.dumps(signed))
            stale["milestones"][0]["objective"] = "EDITED AFTER SIGNOFF"
            blocked = cp.Campaign(stale, camp_dir, run_unit, clock=_clock(),
                                  repo_dir=repo, charter=self._CHARTER).run(
                                      resume=True, decision_resolver=resolver)
            self.assertEqual(blocked.pause_reason, "campaign_plan_signoff")
            self.assertEqual(blocked.freshness_block["original_pause_reason"],
                             "milestone_merge")
            # main is untouched — the irreversible merge never ran.
            self.assertEqual(
                _git(repo, "rev-list", "--count", "main").stdout.strip(), "1")

            # Re-sign the edited plan → resume → the ORIGINAL merge gate executes → done.
            resigned = cp.stamp_signoff(stale, self._CHARTER, signed_at="t2")
            done = cp.Campaign(resigned, camp_dir, run_unit, clock=_clock(),
                               repo_dir=repo, charter=self._CHARTER).run(
                                   resume=True, decision_resolver=resolver)
            self.assertEqual(done.status, cp.STATUS_DONE)
            self.assertEqual(done.milestone_index, 1)
            self.assertIsNone(done.freshness_block)
            self.assertIn(
                "merge", _git(repo, "log", "--oneline", "-n", "3").stdout.lower())


class TestLoopIngressMerge(unittest.TestCase):
    def test_merge_into_trunk_no_ff(self):
        with tempfile.TemporaryDirectory() as root:
            repo = _make_repo(root)
            handle = li.setup_context(
                li.STRATEGY_NEW_BRANCH, repo_dir=repo, loop_id="m1",
                base_ref="main", branch_name="milestone/test/m1")
            with open(os.path.join(repo, "feat.txt"), "w") as fh:
                fh.write("x\n")
            _git(repo, "add", "feat.txt")
            _git(repo, "commit", "-q", "-m", "feat")
            li.merge_into_trunk(handle, "main")
            log = _git(repo, "log", "--oneline").stdout
            self.assertIn("merge", log.lower())


if __name__ == "__main__":
    unittest.main()
