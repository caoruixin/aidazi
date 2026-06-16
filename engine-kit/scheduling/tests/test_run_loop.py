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


if __name__ == "__main__":
    unittest.main(verbosity=2)
