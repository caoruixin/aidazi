"""Quick-Fix CLI tests — stable exit codes, fail-closed gates (req 7), and the full
adapter-driven launch path exercised hermetically against the fake harness."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import _helpers as H  # noqa: E402

from quickfix import cli  # noqa: E402

FR = H.FRAMEWORK_ROOT


class CliExitCodes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qf-cli-")
        self.repo = H.make_repo(os.path.join(self.tmp, "repo"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _supported_registry(self, harness="claude_code"):
        p = os.path.join(self.tmp, f"reg-{harness}.yaml")
        with open(p, "w") as f:
            f.write(f"version: 1\nharnesses:\n  {harness}:\n    status: supported\n")
        return p

    def _records(self):
        rp = os.path.join(self.repo, ".orchestrator", "quickfix", "records.jsonl")
        return ([json.loads(x) for x in open(rp).read().splitlines() if x.strip()]
                if os.path.isfile(rp) else [])

    def test_unsupported_harness_exit_11(self):
        # kimi_code is unsupported in the shipped registry -> fail closed, hermetic.
        reqp = H.write_request(self.repo, harness="kimi_code")
        code = cli.main(["--request", reqp, "--repo-dir", self.repo, "--framework-root", FR])
        self.assertEqual(code, cli.EXIT_UNSUPPORTED)
        self.assertNotIn("quickfix/", H.git(self.repo, "worktree", "list"))
        self.assertEqual(H.git(self.repo, "status", "--porcelain").strip(), "")

    def test_experimental_harness_is_not_launchable_exit_11(self):
        # codex is `experimental` in the shipped registry -> the strict gate refuses it
        # BEFORE any adapter subprocess (no codex launch in this unit test).
        reqp = H.write_request(self.repo, harness="codex")
        code = cli.main(["--request", reqp, "--repo-dir", self.repo, "--framework-root", FR])
        self.assertEqual(code, cli.EXIT_UNSUPPORTED)
        self.assertNotIn("quickfix/", H.git(self.repo, "worktree", "list"))

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

    def test_no_launch_prepares_then_tears_down_no_record(self):
        reqp = H.write_request(self.repo, harness="claude_code", allowed_globs=("src/app.py",))
        adapter = H.FakeHarnessAdapter(binary=H.make_fake_harness(os.path.join(self.tmp, "fk")))
        with mock.patch.object(cli, "build_adapter", return_value=adapter):
            code = cli.main(["--request", reqp, "--repo-dir", self.repo, "--no-launch",
                             "--registry", self._supported_registry(), "--framework-root", FR])
        self.assertEqual(code, cli.EXIT_OK)
        self.assertNotIn("quickfix/", H.git(self.repo, "worktree", "list"))
        self.assertEqual(self._records(), [])  # nothing ran, nothing recorded

    def test_full_launch_completes_records_and_writes_evidence(self):
        # End-to-end through the CLI with the fake harness standing in for a real adapter:
        # prepare -> preflight -> run_edit(edit src/app.py) -> guard/verify/commit -> record.
        fake = H.make_fake_harness(os.path.join(self.tmp, "fake-harness"))
        adapter = H.FakeHarnessAdapter(binary=fake, target="src/app.py")
        reqp = H.write_request(self.repo, harness="claude_code", allowed_globs=("src/app.py",))
        with mock.patch.object(cli, "build_adapter", return_value=adapter):
            code = cli.main(["--request", reqp, "--repo-dir", self.repo,
                             "--registry", self._supported_registry(), "--framework-root", FR])
        self.assertEqual(code, cli.EXIT_OK)
        # result lives ONLY on a quickfix/<id> branch; the adopter tree is untouched (no
        # auto cherry-pick); a `completed` record + launch evidence were persisted.
        self.assertIn("quickfix/", H.git(self.repo, "branch", "--list", "quickfix/*"))
        self.assertEqual(H.git(self.repo, "status", "--porcelain").strip(), "")
        recs = self._records()
        self.assertEqual(recs[-1]["outcome"], "completed")
        ev = os.path.join(self.repo, ".orchestrator", "quickfix", "evidence",
                          recs[-1]["request_id"], "edit-evidence.json")
        self.assertTrue(os.path.isfile(ev))
        self.assertEqual(json.load(open(ev))["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
