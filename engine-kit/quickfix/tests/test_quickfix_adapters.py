"""Quick-Fix harness adapter tests (Commit 3) — contract, fail-closed gates, and the
shared launch lifecycle (success / timeout+killpg / non-zero exit) driven against a FAKE
harness binary (quickfix.tests._helpers). No real claude/codex/kimi is ever launched here
(offline + deterministic); the real-harness proof is the recorded E2E
(archive/2026-06-22-quickfix-claude-code-e2e-evidence.md)."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import _helpers as H  # noqa: E402  (sets sys.path to engine-kit + ships the fake harness)

from quickfix import bundle as bundle_mod  # noqa: E402
from quickfix.adapters import (ADAPTER_REGISTRY, build_adapter,  # noqa: E402
                               resolve_adapter_class)
from quickfix.adapters.base import (HarnessAdapterError, HarnessCapability,  # noqa: E402
                                    LaunchSpec)
from quickfix.errors import EscalationRequired  # noqa: E402


def _spec(bundle_dir, worktree_dir):
    return LaunchSpec(
        request_id="r-fake", task_summary="restore the agreed paginate() behavior",
        bundle_dir=bundle_dir, worktree_dir=worktree_dir,
        allowed_glob_patterns=["src/app.py"],
        memory_file=os.path.join(bundle_dir, "CLAUDE.md"),
        request_file=os.path.join(bundle_dir, "request.json"),
        lane_file=os.path.join(bundle_dir, "quickfix-lane.md"),
        kernel_file=os.path.join(bundle_dir, "anti-hardcode-kernel.md"))


class _FakeBinaryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qf-adapter-")
        self.bundle = os.path.join(self.tmp, "bundle"); os.makedirs(self.bundle)
        self.worktree = os.path.join(self.tmp, "worktree"); os.makedirs(self.worktree)
        self.evidence = os.path.join(self.tmp, "evidence")
        self.fake = H.make_fake_harness(os.path.join(self.tmp, "fake-harness"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _evidence_json(self):
        with open(os.path.join(self.evidence, "edit-evidence.json")) as fh:
            return json.load(fh)


class RegistryAndCapability(unittest.TestCase):
    def test_registry_has_the_three_harnesses(self):
        self.assertEqual(sorted(ADAPTER_REGISTRY), ["claude_code", "codex", "kimi_code"])

    def test_unknown_harness_fails_closed(self):
        with self.assertRaises(HarnessAdapterError):
            resolve_adapter_class("does_not_exist")

    def test_claude_and_codex_declare_isolation_kimi_does_not(self):
        self.assertTrue(build_adapter("claude_code").capability().cold_start_isolation)
        self.assertTrue(build_adapter("codex").capability().cold_start_isolation)
        self.assertFalse(build_adapter("kimi_code").capability().cold_start_isolation)

    def test_kimi_preflight_fails_closed_without_a_subprocess(self):
        # capability is checked first, so this never probes a binary.
        with self.assertRaises(HarnessAdapterError):
            build_adapter("kimi_code").preflight()

    def test_memory_filename_agrees_with_bundle_map(self):
        # bundle.py's harness->filename map MUST match each adapter's MEMORY_FILENAME.
        for h, cls in ADAPTER_REGISTRY.items():
            self.assertEqual(bundle_mod.memory_filename_for(h), cls.MEMORY_FILENAME,
                             f"bundle/adapter memory-filename drift for {h}")


class Argv(unittest.TestCase):
    def setUp(self):
        self.spec = _spec("/bundle", "/work/tree")

    def test_claude_grants_only_worktree_and_excludes_bash(self):
        argv = build_adapter("claude_code").build_argv(self.spec, "claude", prompt="P")
        self.assertIn("-p", argv)
        self.assertEqual(argv[argv.index("--add-dir") + 1], "/work/tree")
        tools = argv[argv.index("--allowed-tools") + 1]
        self.assertNotIn("Bash", tools)
        self.assertNotIn("P", argv, "stdin-delivered prompt must NOT be an argv token")

    def test_codex_uses_bundle_cwd_and_worktree_grant(self):
        argv = build_adapter("codex").build_argv(self.spec, "codex", prompt="P")
        self.assertEqual(argv[:3], ["codex", "exec", "--json"])
        self.assertEqual(argv[argv.index("-C") + 1], "/bundle")
        self.assertEqual(argv[argv.index("--add-dir") + 1], "/work/tree")
        self.assertIn("--skip-git-repo-check", argv)
        self.assertIn("workspace-write", argv)

    def test_kimi_prompt_is_attached_not_a_bare_token(self):
        # a malicious-looking prompt must only ever appear ATTACHED to --prompt=, never as
        # a bare argv token a leading dash could turn into a flag.
        argv = build_adapter("kimi_code").build_argv(self.spec, "kimi", prompt="--dangerous")
        self.assertTrue(any(a == "--prompt=--dangerous" for a in argv))
        self.assertNotIn("--dangerous", argv)

    def test_prompt_points_edits_at_the_worktree_and_forbids_commit(self):
        prompt = build_adapter("claude_code").build_prompt(self.spec)
        self.assertIn("/work/tree", prompt)
        self.assertIn("src/app.py", prompt)
        self.assertIn("commit", prompt.lower())


class VersionGate(unittest.TestCase):
    def test_parses_each_real_version_string_shape(self):
        a = build_adapter("claude_code")
        self.assertEqual(a.parse_version("2.1.170 (Claude Code)"), (2, 1, 170))
        self.assertEqual(a.parse_version("codex-cli 0.134.0"), (0, 134, 0))
        self.assertEqual(a.parse_version("0.18.0"), (0, 18, 0))

    def test_below_min_version_fails_closed(self):
        a = build_adapter("claude_code")  # MIN_VERSION (2,0,0)
        with self.assertRaises(HarnessAdapterError):
            a.assert_supported_version("1.9.9 (Claude Code)")
        self.assertEqual(a.assert_supported_version("2.0.0"), (2, 0, 0))

    def test_unparseable_version_fails_closed(self):
        with self.assertRaises(HarnessAdapterError):
            build_adapter("claude_code").parse_version("no version here")


class Discovery(unittest.TestCase):
    def test_missing_binary_fails_closed(self):
        a = build_adapter("claude_code", binary="definitely-not-a-real-binary-xyz")
        with self.assertRaises(HarnessAdapterError):
            a.discover_executable()

    def test_absolute_path_must_be_executable(self):
        tmp = tempfile.mkdtemp(prefix="qf-disc-")
        try:
            p = os.path.join(tmp, "tool")
            with open(p, "w") as fh:
                fh.write("#!/bin/sh\n")
            a = build_adapter("claude_code", binary=p)
            with self.assertRaises(HarnessAdapterError):  # not executable yet
                a.discover_executable()
            os.chmod(p, 0o755)
            self.assertEqual(a.discover_executable(), p)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class LaunchLifecycle(_FakeBinaryBase):
    def test_success_edits_worktree_and_records_evidence(self):
        adapter = H.FakeHarnessAdapter(behavior="edit", binary=self.fake, record_prompt=True)
        ev = adapter.run_edit(_spec(self.bundle, self.worktree), evidence_dir=self.evidence)
        # the harness edited the WORKTREE, received the prompt on stdin, and exited clean
        self.assertIn("paginate", open(os.path.join(self.worktree, "target.txt")).read())
        got_prompt = open(os.path.join(self.worktree, "received_prompt.txt")).read()
        self.assertIn("restore the agreed paginate()", got_prompt)
        self.assertEqual(ev.exit_code, 0)
        self.assertFalse(ev.timed_out)
        self.assertEqual(ev.granted_dirs, [self.worktree])
        self.assertFalse(ev.cold_start["repo_governance_chain_auto_loaded"])
        # evidence persisted + stdout captured
        disk = self._evidence_json()
        self.assertEqual(disk["exit_code"], 0)
        self.assertTrue(os.path.isfile(disk["stdout_path"]))
        self.assertIn("edited", open(disk["stdout_path"]).read())

    def test_nonzero_exit_escalates_and_preserves_evidence(self):
        adapter = H.FakeHarnessAdapter(behavior="fail", binary=self.fake)
        with self.assertRaises(EscalationRequired) as cm:
            adapter.run_edit(_spec(self.bundle, self.worktree), evidence_dir=self.evidence)
        self.assertEqual(cm.exception.reason, EscalationRequired.HARNESS_LAUNCH_FAILURE)
        self.assertEqual(self._evidence_json()["exit_code"], 3)  # evidence written before raise

    def test_timeout_kills_group_and_escalates(self):
        adapter = H.FakeHarnessAdapter(behavior="sleep", binary=self.fake, timeout_s=1)
        start = time.monotonic()
        with self.assertRaises(EscalationRequired) as cm:
            adapter.run_edit(_spec(self.bundle, self.worktree), evidence_dir=self.evidence)
        elapsed = time.monotonic() - start
        self.assertEqual(cm.exception.reason, EscalationRequired.HARNESS_LAUNCH_FAILURE)
        self.assertLess(elapsed, 20, "timeout must fire ~1s, not wait out the 30s sleep")
        self.assertTrue(self._evidence_json()["timed_out"])

    def test_capability_without_isolation_refuses_before_launch(self):
        class NoIso(H.FakeHarnessAdapter):
            def capability(self):
                return HarnessCapability(
                    headless=True, alternate_cwd=False, worktree_write_grant=False,
                    cold_start_isolation=False, isolation_mechanism="none")
        with self.assertRaises(EscalationRequired) as cm:
            NoIso(binary=self.fake).run_edit(_spec(self.bundle, self.worktree),
                                             evidence_dir=self.evidence)
        self.assertEqual(cm.exception.reason, EscalationRequired.HARNESS_LAUNCH_FAILURE)
        # refused BEFORE launch: no worktree edit happened
        self.assertFalse(os.path.exists(os.path.join(self.worktree, "target.txt")))

    def test_build_env_passes_parent_env_without_adding_secrets(self):
        env = H.FakeHarnessAdapter(binary=self.fake).build_env()
        self.assertEqual(env.get("PATH"), os.environ.get("PATH"))


class VersionProbeProcess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qf-probe-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tool(self, body):
        p = os.path.join(self.tmp, "ver-tool")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(f"#!{sys.executable}\nimport sys, time, os\n{body}\n")
        os.chmod(p, 0o755)
        return p

    def test_nonzero_version_exit_fails_closed_even_with_semver(self):
        # A broken CLI that PRINTS a version but exits non-zero must NOT pass the gate.
        tool = self._tool("sys.stdout.write('tool 9.9.9\\n'); sys.exit(2)")
        with self.assertRaises(HarnessAdapterError):
            H.FakeHarnessAdapter(binary=tool).probe_version(tool)

    def test_version_probe_timeout_fails_closed_and_is_bounded(self):
        # A hung `--version` is killed (process group) and fails closed quickly.
        tool = self._tool("time.sleep(30)")
        adapter = H.FakeHarnessAdapter(binary=tool, version_probe_timeout_s=1)
        start = time.monotonic()
        with self.assertRaises(HarnessAdapterError):
            adapter.probe_version(tool)
        self.assertLess(time.monotonic() - start, 15, "probe timeout must not wait out 30s")

    def test_clean_version_passes(self):
        tool = self._tool("sys.stdout.write('tool 2.3.4\\n'); sys.exit(0)")
        self.assertIn("2.3.4", H.FakeHarnessAdapter(binary=tool).probe_version(tool))


if __name__ == "__main__":
    unittest.main()
