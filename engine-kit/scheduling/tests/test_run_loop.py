#!/usr/bin/env python3
"""Offline, deterministic tests for the scheduling entrypoint (plan §4.4 / P5-B).

stdlib unittest; mock adapters; injected deterministic clock; temp run dir. No
network, no subprocess. Run as a script (do NOT discover the package — siblings
may be mid-edit):

    cd engine-kit && python scheduling/tests/test_run_loop.py

Covers:
  - a clean dry-run reaches advance with mock adapters + a verifying audit chain;
  - artifacts land under the temp run dir, NOT the repo;
  - --mode is recorded in the loop_start audit context;
  - allow_real=False NEVER constructs a real adapter (all MockAdapter);
  - a non-clean verdict yields a non-zero exit / ok=False.
"""

import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHED_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_SCHED_DIR)
for _p in (_SCHED_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
from adapters import MockAdapter  # noqa: E402
from driver import load_charter  # noqa: E402
import run_loop as rl  # noqa: E402

_CHARTER_PATH = os.path.join(_ENGINE_KIT_DIR, "orchestrator", "examples", "p2-charter.yaml")
_REPO_ROOT = os.path.dirname(_ENGINE_KIT_DIR)


def _clock():
    seq = {"n": 0}

    def _now():
        seq["n"] += 1
        return f"2026-06-16T00:{seq['n']:02d}:00Z"

    return _now


class TestRunLoop(unittest.TestCase):
    def setUp(self):
        self.charter = load_charter(_CHARTER_PATH)

    def test_clean_dry_run_advances_and_audits(self):
        with tempfile.TemporaryDirectory() as d:
            info = rl.run_loop(
                self.charter, run_dir=d, loop_id="sched-001",
                subsprint_id="sprint-001", clock=_clock(),
                mode=rl.MODE_OVERNIGHT_AUTOLOOP)
            self.assertEqual(info["final_state"], "advance")
            self.assertTrue(info["clean"])
            self.assertTrue(info["audit_verifies"])
            self.assertTrue(info["ok"])
            self.assertEqual(info["mode"], rl.MODE_OVERNIGHT_AUTOLOOP)

    def test_artifacts_go_to_run_dir_not_repo(self):
        with tempfile.TemporaryDirectory() as d:
            info = rl.run_loop(
                self.charter, run_dir=d, loop_id="sched-002",
                subsprint_id="sprint-001", clock=_clock())
            # The ledger is under the temp run dir, never the repo.
            self.assertTrue(info["audit_ledger"].startswith(os.path.abspath(d)))
            self.assertFalse(info["audit_ledger"].startswith(_REPO_ROOT + os.sep + "engine-kit"))
            self.assertTrue(os.path.isdir(os.path.join(d, ".orchestrator")))

    def test_mode_recorded_in_audit_context(self):
        with tempfile.TemporaryDirectory() as d:
            rl.run_loop(self.charter, run_dir=d, loop_id="sched-003",
                        subsprint_id="sprint-001", clock=_clock(),
                        mode=rl.MODE_MILESTONE_DELIVERY)
            ledger = audit.audit_path("sched-003", os.path.join(d, ".orchestrator", "audit"))
            starts = [e for e in audit.read_events(ledger) if e["type"] == "loop_start"]
            self.assertEqual(len(starts), 1)
            self.assertEqual(starts[0]["payload"]["context"]["schedule_mode"],
                             rl.MODE_MILESTONE_DELIVERY)

    def test_build_adapters_mock_by_default(self):
        adapters = rl.build_adapters(self.charter, allow_real=False)
        self.assertTrue(adapters)
        for role, a in adapters.items():
            self.assertIsInstance(a, MockAdapter, f"{role} should be a MockAdapter")

    def test_build_adapters_real_constructs_real_classes(self):
        # allow_real builds real adapter classes (NOT mocks). They remain gated
        # (no I/O) — we only assert the class, never spawn.
        adapters = rl.build_adapters(self.charter, allow_real=True)
        # p2-charter routes dev→claude_code, review→headless.
        self.assertEqual(adapters["dev"].harness, "claude_code")
        self.assertEqual(adapters["review"].harness, "headless")
        self.assertNotIsInstance(adapters["dev"], MockAdapter)

    def test_non_clean_verdict_is_not_ok(self):
        # Inject a fix_required review → loop halts → ok=False / non-clean.
        adapters = {
            "dev": MockAdapter({("dev",): {"artifact": "x"}}, harness="claude_code"),
            "review": MockAdapter(
                {("review",): {"decision": "fix_required", "blocking_count": 1,
                               "summary": "one P1", "findings": []}},
                harness="headless"),
            "deliver": MockAdapter({("deliver",): rl._DRY_CLOSE}, harness="claude_code"),
        }
        with tempfile.TemporaryDirectory() as d:
            info = rl.run_loop(
                self.charter, run_dir=d, loop_id="sched-004",
                subsprint_id="sprint-001", clock=_clock(), adapters=adapters)
            self.assertFalse(info["clean"])
            self.assertFalse(info["ok"])

    def test_main_exit_code_clean(self):
        with tempfile.TemporaryDirectory() as d:
            rc = rl.main(["--charter", _CHARTER_PATH, "--run-dir", d,
                          "--mode", rl.MODE_OVERNIGHT_AUTOLOOP,
                          "--loop-id", "sched-main-1"])
            self.assertEqual(rc, 0)

    # --- .env.local loader (provider credentials by file, not by hand) --------- #

    def test_load_local_env_loads_without_override(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, ".env.local"), "w", encoding="utf-8") as fh:
                fh.write("# a comment line — ignored\n")
                fh.write("AIDAZI_TEST_NEWKEY=newval\n")
                fh.write('AIDAZI_TEST_QUOTED="q val"\n')
                fh.write("export AIDAZI_TEST_EXPORTED=expval\n")
                fh.write("AIDAZI_TEST_PRESET=fromfile\n")
            os.environ["AIDAZI_TEST_PRESET"] = "exported"  # export must win
            for k in ("AIDAZI_TEST_NEWKEY", "AIDAZI_TEST_QUOTED",
                      "AIDAZI_TEST_EXPORTED", "AIDAZI_TEST_PRESET"):
                self.addCleanup(os.environ.pop, k, None)
            loaded = rl.load_local_env(root=d)
            self.assertEqual(loaded, [os.path.join(d, ".env.local")])
            self.assertEqual(os.environ["AIDAZI_TEST_NEWKEY"], "newval")
            self.assertEqual(os.environ["AIDAZI_TEST_QUOTED"], "q val")     # quotes stripped
            self.assertEqual(os.environ["AIDAZI_TEST_EXPORTED"], "expval")  # export prefix stripped
            self.assertEqual(os.environ["AIDAZI_TEST_PRESET"], "exported")  # NOT overridden

    def test_load_local_env_missing_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rl.load_local_env(root=d), [])

    # --- base_url from endpoint_env (Facet A) ---------------------------------- #

    def test_endpoint_env_resolves_base_url(self):
        os.environ["AIDAZI_TEST_BASEURL"] = "https://example.test/v1"
        self.addCleanup(os.environ.pop, "AIDAZI_TEST_BASEURL", None)
        charter = {"tooling": {"review": {
            "harness": "headless", "provider": "deepseek",
            "model": "deepseek-v4-pro", "endpoint_env": "AIDAZI_TEST_BASEURL",
            "api_key_env": "AIDAZI_TEST_KEY", "tools": ["Read", "Grep", "Glob"]}}}
        adapters = rl.build_adapters(charter, allow_real=True)
        self.assertEqual(adapters["review"].base_url, "https://example.test/v1")
        self.assertEqual(adapters["review"].api_key_env, "AIDAZI_TEST_KEY")

    def test_literal_endpoint_wins_over_endpoint_env(self):
        os.environ["AIDAZI_TEST_BASEURL"] = "https://from-env.test/v1"
        self.addCleanup(os.environ.pop, "AIDAZI_TEST_BASEURL", None)
        charter = {"tooling": {"review": {
            "harness": "headless", "provider": "deepseek",
            "model": "deepseek-v4-pro", "endpoint": "https://literal.test/v1",
            "endpoint_env": "AIDAZI_TEST_BASEURL", "tools": ["Read", "Grep", "Glob"]}}}
        adapters = rl.build_adapters(charter, allow_real=True)
        self.assertEqual(adapters["review"].base_url, "https://literal.test/v1")

    def test_timeout_seconds_applied_to_real_adapter(self):
        charter = {"tooling": {"dev": {
            "harness": "claude_code", "provider": "anthropic",
            "model": "claude-sonnet-4-6", "sandbox": "workspace_write",
            "timeout_seconds": 1800}}}
        adapters = rl.build_adapters(charter, allow_real=True)
        self.assertEqual(adapters["dev"].timeout_seconds, 1800)

    def test_invalid_timeout_seconds_rejected_loudly(self):
        # A present-but-invalid value must NOT silently fall back to 600 (bool is
        # rejected even though it is an int subclass; strings/floats/<1 too).
        for bad in ("1800", True, 0, -5, 1.5):
            charter = {"tooling": {"dev": {
                "harness": "claude_code", "provider": "anthropic",
                "model": "m", "timeout_seconds": bad}}}
            with self.assertRaises(ValueError):
                rl.build_adapters(charter, allow_real=True)

    def test_advisory_validate_charter_never_raises(self):
        # The advisory schema summary is NON-RAISING: a junk charter yields a summary
        # string (or None if the validator is unavailable), never an exception.
        out = rl.advisory_validate_charter({"tooling": {"dev": {"sandbox": "x"}}})
        self.assertTrue(out is None or isinstance(out, str))


_TEMPLATE_CHARTER = os.path.join(_ENGINE_KIT_DIR, "..", "templates",
                                 "mission-charter.yaml")
_WARN_CHARTER = os.path.join(_ENGINE_KIT_DIR, "validators", "tests", "fixtures",
                             "warn-calibration-skills.yaml")


class CharterEnforcementTests(unittest.TestCase):
    """--allow-real runs ENFORCE the charter schema: errors BLOCK before any adapter
    is built; warnings stay visible + non-blocking; a clean charter proceeds."""

    def test_clean_charter_does_not_block(self):
        rl.enforce_charter_for_real_run(load_charter(_TEMPLATE_CHARTER))  # no raise

    def test_warnings_only_does_not_block(self):
        # The warn fixture validates ok=True with a warning — warnings ≠ errors.
        rl.enforce_charter_for_real_run(load_charter(_WARN_CHARTER))  # no raise

    def test_invalid_charter_raises_before_adapters(self):
        with self.assertRaises(rl.CharterValidationError):
            rl.enforce_charter_for_real_run(load_charter(_CHARTER_PATH))  # p2: 6 errors

    def test_run_loop_blocks_invalid_charter_before_building_adapters(self):
        # run_loop must raise at the enforcement gate, BEFORE build_adapters.
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(rl.CharterValidationError):
                rl.run_loop(load_charter(_CHARTER_PATH), run_dir=d,
                            loop_id="block-1", subsprint_id="sprint-001",
                            clock=lambda: "2026-06-19T00:00:00Z", allow_real=True)

    def test_main_blocks_real_run_on_invalid_charter_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            rc = rl.main(["--charter", _CHARTER_PATH, "--allow-real",
                          "--run-dir", d, "--loop-id", "block-main-1"])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
