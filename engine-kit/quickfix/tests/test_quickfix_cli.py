"""Quick-Fix CLI tests — stable exit codes + fail-closed behavior (req 7)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import _helpers as H  # noqa: E402

from quickfix import cli  # noqa: E402

FR = H.FRAMEWORK_ROOT


class CliExitCodes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qf-cli-")
        self.repo = H.make_repo(os.path.join(self.tmp, "repo"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _supported_registry(self):
        p = os.path.join(self.tmp, "reg.yaml")
        with open(p, "w") as f:
            f.write("version: 1\nharnesses:\n  claude_code:\n    status: supported\n")
        return p

    def test_unsupported_harness_exit_11(self):
        reqp = H.write_request(self.repo, harness="claude_code")
        code = cli.main(["--request", reqp, "--repo-dir", self.repo, "--framework-root", FR])
        self.assertEqual(code, cli.EXIT_UNSUPPORTED)
        # fail-closed: no worktree, repo clean
        self.assertNotIn("quickfix/", H.git(self.repo, "worktree", "list"))
        self.assertTrue(H.git(self.repo, "status", "--porcelain").strip() == "")

    def test_invalid_request_exit_2(self):
        reqp = H.write_request(self.repo)
        obj = json.load(open(reqp)); obj["human_activation"] = False
        json.dump(obj, open(reqp, "w"))
        code = cli.main(["--request", reqp, "--repo-dir", self.repo, "--framework-root", FR])
        self.assertEqual(code, cli.EXIT_INVALID)

    def test_dirty_tree_exit_3(self):
        # supported harness so we get PAST the support gate to the clean-tree gate
        H.write(self.repo, "untracked.txt", "dirty\n")
        reqp = H.write_request(self.repo, harness="claude_code")
        code = cli.main(["--request", reqp, "--repo-dir", self.repo,
                         "--registry", self._supported_registry(), "--framework-root", FR])
        self.assertEqual(code, cli.EXIT_DIRTY)

    def test_missing_request_exit_2(self):
        code = cli.main(["--request", os.path.join(self.tmp, "nope.json"),
                         "--repo-dir", self.repo, "--framework-root", FR])
        self.assertEqual(code, cli.EXIT_INVALID)


if __name__ == "__main__":
    unittest.main()
