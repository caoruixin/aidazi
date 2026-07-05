"""Phase-4 native-E2E capability contract — run_loop preflight enforcement (design §2/§13).

Two ingress points refuse DETERMINISTICALLY + FAIL-CLOSED when the charter pins a framework
capability the deployed aidazi does not provide: the real-run gate (enforce_*_for_real_run) and
the --sign-plan CLI. Absent a requirement ⇒ dormant (legacy-safe).

Run: cd engine-kit && python3.12 -m pytest scheduling/tests/test_capability_preflight.py -q
"""
import io
import contextlib
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHED_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_SCHED_DIR)
for _p in (_SCHED_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator", "tests"),
           os.path.join(_ENGINE_KIT_DIR, "validators")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import run_loop as rl  # noqa: E402
from test_driver import _acceptance_charter  # noqa: E402


def _plan(cid, milestones, *, signed=False):
    return {"campaign_id": cid, "goal": "deliver the whole thing",
            "signed_by_human": signed, "milestones": milestones}


class RealRunGateTests(unittest.TestCase):
    def test_dormant_when_no_capability_pinned(self):
        rl.enforce_required_capabilities_for_real_run({})   # no raise

    def test_satisfied_capability_passes(self):
        ch = {"required_framework_capabilities": [
            {"id": "native_managed_external_e2e", "min_version": "1.0"}]}
        rl.enforce_required_capabilities_for_real_run(ch)   # no raise

    def test_missing_capability_refuses(self):
        ch = {"required_framework_capabilities": [{"id": "ghost_cap"}]}
        with self.assertRaises(rl.CharterValidationError) as cm:
            rl.enforce_required_capabilities_for_real_run(ch)
        self.assertIn("ghost_cap", str(cm.exception))

    def test_under_version_refuses(self):
        ch = {"required_framework_capabilities": [
            {"id": "autonomous_e2e_remediation", "min_version": "99.0"}]}
        with self.assertRaises(rl.CharterValidationError):
            rl.enforce_required_capabilities_for_real_run(ch)


class SignPlanGateTests(unittest.TestCase):
    def _write(self, d, charter, plan):
        cp_path = os.path.join(d, "charter.json")
        pp_path = os.path.join(d, "plan.json")
        with open(cp_path, "w", encoding="utf-8") as fh:
            json.dump(charter, fh)
        with open(pp_path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        return cp_path, pp_path

    def test_sign_plan_refuses_missing_capability(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            charter["required_framework_capabilities"] = [{"id": "ghost_cap"}]
            plan = _plan("caprefuse", [{"id": "m1", "objective": "x",
                                        "subsprint_sequence": ["sprint-001"]}], signed=True)
            cp_path, pp_path = self._write(d, charter, plan)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = rl.main(["--charter", cp_path, "--campaign", pp_path,
                              "--sign-plan", "--repo-dir", d])
            self.assertEqual(rc, 2)
            self.assertIn("ghost_cap", buf.getvalue())
            with open(pp_path, encoding="utf-8") as fh:
                self.assertNotIn("signoff", json.load(fh))   # NOT stamped

    def test_sign_plan_signs_when_capability_satisfied(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            charter["required_framework_capabilities"] = [
                {"id": "native_managed_external_e2e", "min_version": "1.0"}]
            plan = _plan("capok", [{"id": "m1", "objective": "x",
                                    "subsprint_sequence": ["sprint-001"]}], signed=True)
            cp_path, pp_path = self._write(d, charter, plan)
            rc = rl.main(["--charter", cp_path, "--campaign", pp_path,
                          "--sign-plan", "--repo-dir", d])
            self.assertEqual(rc, 0)
            with open(pp_path, encoding="utf-8") as fh:
                self.assertIn("signoff", json.load(fh))      # stamped


if __name__ == "__main__":
    unittest.main()
