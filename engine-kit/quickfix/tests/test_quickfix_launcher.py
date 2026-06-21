"""Quick-Fix launcher tests: completed/escalation flows, fault injection (req 1),
baseline binding (req 2), commit-time consistency (req 5), harness fail-closed (req 7)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import _helpers as H  # noqa: E402

from quickfix import launcher, paths, worktree  # noqa: E402
from quickfix.errors import HarnessUnsupportedError  # noqa: E402
from quickfix.guard import GuardResult  # noqa: E402

FR = H.FRAMEWORK_ROOT
TS = "2026-06-21T00:00:00Z"


def _edit(rel, content):
    def fn(work_dir):
        H.write(work_dir, rel, content)
    return fn


class LauncherBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qf-launch-")
        self.repo = H.make_repo(os.path.join(self.tmp, "repo"))
        self.n = 0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prepare(self, allowed=("src/app.py",), argv=("python3", "-c", "import sys;sys.exit(0)"),
                 harness="claude_code", registry=None):
        self.n += 1
        reqp = H.write_request(self.repo, request_id=f"r{self.n:03d}",
                               allowed_globs=allowed, argv=argv, harness=harness)
        return launcher.prepare(
            reqp, self.repo,
            registry_path=registry if registry is not None else H.supported_registry(harness),
            worktree_root=os.path.join(self.tmp, f"wt{self.n}"),
            bundle_root=os.path.join(self.tmp, f"bn{self.n}"),
            framework_root=FR)

    def _records(self):
        rp = os.path.join(self.repo, ".orchestrator", "quickfix", "records.jsonl")
        if not os.path.isfile(rp):
            return []
        return [json.loads(x) for x in open(rp).read().splitlines() if x.strip()]

    def _repo_clean(self):
        return H.git(self.repo, "status", "--porcelain").strip() == ""

    def _branches(self):
        return H.git(self.repo, "branch", "--list", "quickfix/*")


class CompletedFlow(LauncherBase):
    def test_completed(self):
        ctx = self._prepare()
        res = launcher.run(ctx, _edit("src/app.py", "def paginate(n):\n    return [n]\n"), ts=TS)
        self.assertEqual(res.outcome, "completed")
        self.assertTrue(res.branch.startswith("quickfix/"))
        # original repo untouched + HEAD unmoved; result branch kept for cherry-pick
        self.assertTrue(self._repo_clean())
        self.assertIn(res.branch.split("/", 1)[1], self._branches())
        recs = self._records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["outcome"], "completed")
        # result commit parent == baseline
        parent = H.git(self.repo, "rev-parse", f"{res.commit_sha}^").strip()
        self.assertEqual(parent, ctx.worktree.baseline_sha)


class EscalationFlows(LauncherBase):
    def _assert_escalated(self, res, reason):
        self.assertEqual(res.outcome, "escalated")
        self.assertEqual(res.reason, reason)
        self.assertTrue(os.path.isfile(res.patch_path), "patch must be preserved")
        self.assertTrue(os.path.isfile(res.handoff_path), "handoff must be preserved")
        self.assertTrue(self._repo_clean(), "original repo must stay clean")
        self.assertEqual([r["outcome"] for r in self._records()], ["escalated"])
        self.assertEqual(self._branches().strip(), "", "escalation must not leave a branch")

    def test_out_of_scope(self):
        ctx = self._prepare(allowed=("src/app.py",))
        res = launcher.run(ctx, _edit("src/other.py", "x=1\n"), ts=TS)
        self._assert_escalated(res, "scope_expansion")

    def test_protected_surface(self):
        ctx = self._prepare(allowed=("schemas/**",))  # human attests no_protected; guard catches
        res = launcher.run(ctx, _edit("schemas/x.json", "{}\n"), ts=TS)
        self._assert_escalated(res, "protected_surface_hit")

    def test_verification_failure_preserves_patch(self):
        ctx = self._prepare(argv=("python3", "-c", "import sys;sys.exit(1)"))
        res = launcher.run(ctx, _edit("src/app.py", "def paginate(n):\n    return [n]\n"), ts=TS)
        self._assert_escalated(res, "verification_failure")
        # the in-scope edit is preserved in the patch
        self.assertIn("paginate", open(res.patch_path).read())

    def test_symlink_escalates(self):
        ctx = self._prepare(allowed=("src/**",))

        def make_symlink(work_dir):
            os.symlink("app.py", os.path.join(work_dir, "src", "link.py"))
        res = launcher.run(ctx, make_symlink, ts=TS)
        self._assert_escalated(res, "symlink_or_gitlink_change")

    def test_edit_fn_raises_is_fail_closed(self):
        ctx = self._prepare()

        def boom(work_dir):
            H.write(work_dir, "src/app.py", "partial\n")
            raise RuntimeError("harness blew up")
        res = launcher.run(ctx, boom, ts=TS)
        self.assertEqual(res.outcome, "escalated")
        self.assertTrue(self._repo_clean())
        self.assertEqual([r["outcome"] for r in self._records()], ["escalated"])


class FaultInjection(LauncherBase):
    def test_commit_failure_never_records_completed(self):
        ctx = self._prepare()
        real = launcher.run_git

        def flaky(repo_dir, args, **kw):
            if args and args[0] == "commit":
                raise launcher.QuickfixError("injected commit failure")
            return real(repo_dir, args, **kw)
        with mock.patch.object(launcher, "run_git", side_effect=flaky):
            res = launcher.run(ctx, _edit("src/app.py", "def p():\n    return 1\n"), ts=TS)
        self.assertEqual(res.outcome, "escalated")
        self.assertTrue(self._repo_clean())
        self.assertNotIn("completed", [r["outcome"] for r in self._records()])
        # the unique work is still preserved
        self.assertIn("def p()", open(res.patch_path).read())

    def test_completed_record_write_failure_escalates(self):
        ctx = self._prepare()
        real = launcher.record_append

        def flaky(record, path, schema):
            if record.get("outcome") == "completed":
                raise launcher.QuickfixError("injected record failure")
            return real(record, path, schema)
        with mock.patch.object(launcher, "record_append", side_effect=flaky):
            res = launcher.run(ctx, _edit("src/app.py", "def p():\n    return 1\n"), ts=TS)
        self.assertEqual(res.outcome, "escalated")
        self.assertNotIn("completed", [r["outcome"] for r in self._records()])

    def test_prepare_cleans_up_worktree_on_later_failure(self):
        # inject a bundle failure -> prepare must tear down the worktree it created
        with mock.patch("quickfix.launcher.bundle_mod.materialize",
                        side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._prepare()
        # no leftover worktree registered in the repo, repo still clean
        self.assertNotIn("quickfix/", H.git(self.repo, "worktree", "list"))
        self.assertTrue(self._repo_clean())

    def test_preserve_failure_keeps_worktree_no_patch_loss(self):
        # If patch staging fails during escalation, the worktree must be KEPT (work not lost).
        ctx = self._prepare(allowed=("src/app.py",))
        wd = ctx.worktree.work_dir
        real = launcher.run_git

        def flaky(repo_dir, args, **kw):
            if args and args[0] == "add":
                raise launcher.QuickfixError("injected add failure")
            return real(repo_dir, args, **kw)
        with mock.patch.object(launcher, "run_git", side_effect=flaky):
            with self.assertRaises(launcher.QuickfixError):
                # out-of-scope edit -> escalation -> preserve add fails -> worktree kept
                launcher.run(ctx, _edit("src/other.py", "x\n"), ts=TS)
        self.assertTrue(os.path.isdir(wd), "worktree must be kept when patch can't be saved")
        self.assertTrue(self._repo_clean())
        launcher.wt_mod.teardown(ctx.worktree, keep_branch=False)  # manual cleanup


class OriginalRepoPollution(LauncherBase):
    def test_verification_polluting_original_repo_is_detected(self):
        pollute = os.path.join(self.repo, "pollute.txt").replace("\\", "/")
        code = f"open(r'{pollute}', 'w').write('x')"
        ctx = self._prepare(allowed=("src/app.py",), argv=("python3", "-c", code))
        res = launcher.run(ctx, _edit("src/app.py", "def p():\n    return 1\n"), ts=TS)
        self.assertEqual(res.outcome, "escalated")
        self.assertEqual(res.reason, "original_repo_polluted")
        self.assertNotIn("completed", [r["outcome"] for r in self._records()])


class CommitTimeModeCheck(LauncherBase):
    def test_consistency_catches_committed_symlink_when_guard_bypassed(self):
        # Force the guard to pass on a symlink; the commit-time MODE re-derivation must catch it.
        from quickfix.guard import GuardResult
        ctx = self._prepare(allowed=("src/**",))

        def make_symlink(work_dir):
            os.symlink("app.py", os.path.join(work_dir, "src", "ln.py"))
        with mock.patch("quickfix.launcher.guard_mod.check",
                        return_value=GuardResult(touched=["src/ln.py"])):
            res = launcher.run(ctx, make_symlink, ts=TS)
        self.assertEqual(res.outcome, "escalated")
        self.assertEqual(res.reason, "symlink_or_gitlink_change")
        self.assertNotIn("completed", [r["outcome"] for r in self._records()])

    def test_consistency_catches_committed_symlink_delete_when_guard_bypassed(self):
        # Deleting an existing symlink is src=120000 -> dst=000000; a dst-only mode check
        # would miss it. The consistency check must catch BOTH sides.
        from quickfix.guard import GuardResult
        os.symlink("app.py", os.path.join(self.repo, "src", "existing_link.py"))
        H.commit_all(self.repo, "add a symlink to baseline")
        ctx = self._prepare(allowed=("src/**",))

        def delete_symlink(work_dir):
            os.remove(os.path.join(work_dir, "src", "existing_link.py"))
        with mock.patch("quickfix.launcher.guard_mod.check",
                        return_value=GuardResult(touched=["src/existing_link.py"])):
            res = launcher.run(ctx, delete_symlink, ts=TS)
        self.assertEqual(res.outcome, "escalated")
        self.assertEqual(res.reason, "symlink_or_gitlink_change")
        self.assertNotIn("completed", [r["outcome"] for r in self._records()])


class BaseRef(LauncherBase):
    def test_base_ref_honored_parents_on_requested_baseline(self):
        b0 = H.git(self.repo, "rev-parse", "HEAD").strip()
        H.write(self.repo, "src/app.py", "moved\n")
        H.commit_all(self.repo, "advance past b0")
        reqp = H.write_request(self.repo, request_id="r-baseref", allowed_globs=("src/app.py",))
        obj = json.load(open(reqp)); obj["base_ref"] = b0; json.dump(obj, open(reqp, "w"))
        ctx = launcher.prepare(reqp, self.repo, registry_path=H.supported_registry(),
                               worktree_root=os.path.join(self.tmp, "wtbr"),
                               bundle_root=os.path.join(self.tmp, "bnbr"), framework_root=FR)
        self.assertEqual(ctx.worktree.baseline_sha, b0)
        res = launcher.run(ctx, _edit("src/app.py", "def p():\n    return 3\n"), ts=TS)
        self.assertEqual(res.outcome, "completed")
        parent = H.git(self.repo, "rev-parse", f"{res.commit_sha}^").strip()
        self.assertEqual(parent, b0)  # parented on base_ref, NOT the advanced HEAD


class ConsistencyCheck(LauncherBase):
    def test_commit_time_check_catches_guard_bypass(self):
        # Force the guard to (wrongly) pass on an out-of-scope edit; the independent
        # commit-time consistency check (req 5) must still catch it and escalate.
        ctx = self._prepare(allowed=("src/app.py",))
        fake_ok = GuardResult(touched=["src/other.py"])  # ok==True (no violations recorded)
        self.assertTrue(fake_ok.ok)
        with mock.patch("quickfix.launcher.guard_mod.check", return_value=fake_ok):
            res = launcher.run(ctx, _edit("src/other.py", "x=1\n"), ts=TS)
        self.assertEqual(res.outcome, "escalated")
        self.assertEqual(res.reason, "scope_expansion")
        self.assertNotIn("completed", [r["outcome"] for r in self._records()])


class BaselineBinding(LauncherBase):
    def test_state_binds_to_baseline_not_moving_main(self):
        ctx = self._prepare()
        baseline = ctx.worktree.baseline_sha
        # advance the MAIN repo HEAD AFTER prepare
        H.write(self.repo, "unrelated.txt", "moved on\n")
        H.commit_all(self.repo, "advance main")
        new_main = H.git(self.repo, "rev-parse", "HEAD").strip()
        self.assertNotEqual(new_main, baseline)
        # the lane still operates from the baseline worktree
        res = launcher.run(ctx, _edit("src/app.py", "def p():\n    return 2\n"), ts=TS)
        self.assertEqual(res.outcome, "completed")
        parent = H.git(self.repo, "rev-parse", f"{res.commit_sha}^").strip()
        self.assertEqual(parent, baseline)         # parented on baseline, NOT moved main
        self.assertNotEqual(parent, new_main)


class HarnessFailClosed(LauncherBase):
    def test_unsupported_harness_fails_closed_no_sideeffects(self):
        # shipped registry (registry_path=None default) marks all harnesses unsupported
        reqp = H.write_request(self.repo, request_id="r-unsup", harness="claude_code")
        with self.assertRaises(HarnessUnsupportedError):
            launcher.prepare(reqp, self.repo, registry_path=paths.harness_support_path(FR),
                             worktree_root=os.path.join(self.tmp, "wtx"),
                             bundle_root=os.path.join(self.tmp, "bnx"), framework_root=FR)
        # no worktree, repo clean, no records
        self.assertNotIn("quickfix/", H.git(self.repo, "worktree", "list"))
        self.assertTrue(self._repo_clean())
        self.assertEqual(self._records(), [])

    def test_shipped_registry_is_all_unsupported(self):
        import yaml
        data = yaml.safe_load(open(paths.harness_support_path(FR)))
        statuses = {h: e.get("status") for h, e in data["harnesses"].items()}
        self.assertTrue(statuses, "registry must list harnesses")
        self.assertTrue(all(s == "unsupported" for s in statuses.values()),
                        f"Commit 2 ships all-unsupported; got {statuses}")


if __name__ == "__main__":
    unittest.main()
