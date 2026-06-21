"""Quick-Fix guard tests over REAL git worktrees — full change-type coverage."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import _helpers as H  # noqa: E402

from quickfix import guard, paths, policy, worktree  # noqa: E402
from quickfix.globmatch import compile_globs  # noqa: E402

FR = H.FRAMEWORK_ROOT


class GuardCoverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qf-guard-")
        self.repo = H.make_repo(os.path.join(self.tmp, "repo"))
        # a protected-looking file in baseline so deletes/edits to it can be tested
        H.write(self.repo, "schemas/thing.schema.json", "{}\n")
        H.commit_all(self.repo, "add schema")
        self.baseline = worktree.capture_baseline(self.repo)
        self.wt = worktree.create(self.repo, "g1", self.baseline,
                                  root=os.path.join(self.tmp, "wt"))
        self.protected = policy.load_protected(
            paths.policy_path(FR), paths.baseline_schema_path(FR))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _check(self, allowed):
        return guard.check(self.wt.work_dir, self.baseline,
                           compile_globs(allowed), self.protected)

    def _w(self, rel, content):
        return H.write(self.wt.work_dir, rel, content)

    def test_in_scope_edit_ok(self):
        self._w("src/app.py", "def paginate(n):\n    return list(range(n + 1))\n")
        r = self._check(["src/**"])
        self.assertTrue(r.ok, r.detail())
        self.assertIn("src/app.py", r.touched)

    def test_out_of_scope(self):
        self._w("src/app.py", "x\n")
        self._w("other/y.py", "y\n")
        r = self._check(["src/**"])
        self.assertFalse(r.ok)
        self.assertIn("other/y.py", r.out_of_scope)

    def test_protected_surface_hit(self):
        self._w("schemas/thing.schema.json", "{\"changed\": true}\n")
        r = self._check(["schemas/**"])  # in scope, but schemas is PROTECTED
        self.assertFalse(r.ok)
        self.assertTrue(any(sid == "contract_schemas" for _, sid in r.protected_hits))

    def _rename(self, src, dst):
        os.makedirs(os.path.dirname(os.path.join(self.wt.work_dir, dst)), exist_ok=True)
        os.rename(os.path.join(self.wt.work_dir, src), os.path.join(self.wt.work_dir, dst))
        H.git(self.wt.work_dir, "add", "-A")  # git records the rename (or delete+add)

    def test_rename_both_paths_checked(self):
        # rename src/app.py -> other/app.py; with only other/** in scope the OLD path is OOS
        self._rename("src/app.py", "other/app.py")
        r = self._check(["other/**"])
        self.assertFalse(r.ok)
        self.assertIn("src/app.py", r.out_of_scope)         # rename SOURCE out of scope

    def test_rename_both_in_scope_ok(self):
        self._rename("src/app.py", "other/app.py")
        r = self._check(["src/**", "other/**"])
        self.assertTrue(r.ok, r.detail())

    def test_delete_protected_flags(self):
        H.git(self.wt.work_dir, "rm", "-q", "schemas/thing.schema.json")
        r = self._check(["schemas/**"])
        self.assertFalse(r.ok)
        self.assertTrue(r.protected_hits)

    def test_file_mode_change_touched_in_scope_ok(self):
        os.chmod(os.path.join(self.wt.work_dir, "src/app.py"), 0o755)
        r = self._check(["src/**"])
        self.assertIn("src/app.py", r.touched)
        self.assertTrue(r.ok, r.detail())

    def test_symlink_escalates(self):
        os.symlink("app.py", os.path.join(self.wt.work_dir, "src", "link.py"))
        r = self._check(["src/**"])  # in scope, but a symlink -> escalation
        self.assertFalse(r.ok)
        self.assertTrue(any(k == "symlink" for k, _ in r.symlink_or_gitlink))

    def test_gitlink_escalates(self):
        # a staged submodule/gitlink (mode 160000)
        sub = os.path.join(self.tmp, "sub")
        H.make_repo(sub)
        dest = os.path.join(self.wt.work_dir, "vendored")
        import shutil
        shutil.copytree(sub, dest)
        H.git(self.wt.work_dir, "add", "vendored")
        r = self._check(["vendored", "vendored/**"])
        self.assertFalse(r.ok)
        self.assertTrue(any(k == "gitlink" for k, _ in r.symlink_or_gitlink), r.symlink_or_gitlink)

    def test_untracked_in_scope_ok(self):
        self._w("src/new_helper.py", "def h():\n    return 1\n")
        r = self._check(["src/**"])
        self.assertTrue(r.ok, r.detail())
        self.assertIn("src/new_helper.py", r.touched)

    def test_gitignored_noise_excluded(self):
        self._w("src/app.py", "x\n")
        self._w("__pycache__/app.cpython-312.pyc", "bytecode")  # gitignored
        r = self._check(["src/**"])
        self.assertTrue(r.ok, r.detail())
        self.assertNotIn("__pycache__/app.cpython-312.pyc", r.touched)

    def test_untracked_nested_repo_escalates(self):
        # an UNTRACKED nested git repo (would become a gitlink once staged) must escalate
        import shutil
        sub = H.make_repo(os.path.join(self.tmp, "sub2"))
        shutil.copytree(sub, os.path.join(self.wt.work_dir, "nested"))
        r = self._check(["nested", "nested/**"])  # in scope, but it's a nested repo
        self.assertFalse(r.ok)
        self.assertTrue(any(k == "gitlink" for k, _ in r.symlink_or_gitlink), r.symlink_or_gitlink)

    def test_unknown_porcelain_record_fails_closed(self):
        from unittest import mock
        from quickfix import guard as G
        from quickfix.errors import QuickfixError

        def fake(repo, args):
            if args and args[0] == "rev-list":
                return "0\n"
            if args and args[0] == "status":
                return "x some-weird-record\0"  # unknown porcelain v2 kind
            return ""
        with mock.patch.object(G, "git_out", side_effect=fake):
            with self.assertRaises(QuickfixError):
                G.check(self.wt.work_dir, self.baseline, [], self.protected)

    def test_unexpected_commit_ahead_escalates(self):
        self._w("src/app.py", "x\n")
        H.git(self.wt.work_dir, "add", "-A")
        H.git(self.wt.work_dir, "commit", "-q", "-m", "sneaky", "--no-verify")
        r = self._check(["src/**"])
        self.assertFalse(r.ok)
        self.assertEqual(r.unexpected_commits, 1)


if __name__ == "__main__":
    unittest.main()
