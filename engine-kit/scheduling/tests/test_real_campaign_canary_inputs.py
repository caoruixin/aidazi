"""OFFLINE companion to the real campaign canary (always on in the suite).

The env-gated real canary (test_real_campaign_canary.py) is skipped in normal
runs, so THIS test keeps its inputs honest continuously: the shipped charter
validates CLEAN against the full charter validator (itself a Phase-1
deliverable — proving a real-runnable, schema-valid charter exists), the plan
passes the formal campaign-plan schema, and every compact prompt satisfies the
driver's strict-prompt content bar (R0 B-4). NO subprocess, NO network.
"""
import json
import os
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHED_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_SCHED_DIR)
_REPO_ROOT = os.path.dirname(_ENGINE_KIT_DIR)
for _p in (_SCHED_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator"),
           os.path.join(_ENGINE_KIT_DIR, "validators")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402
import charter_validator as cv  # noqa: E402
from driver import Driver  # noqa: E402
from run_loop import load_charter  # noqa: E402

_CANARY = os.path.join(_REPO_ROOT, "examples", "real-campaign-canary")
_CHARTER = os.path.join(_CANARY, "charter.yaml")
_PLAN = os.path.join(_CANARY, "campaign-plan.json")
_COMPACT = os.path.join(_CANARY, "workspace", "compact")


class CanaryCharterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.charter = load_charter(_CHARTER)

    def test_charter_validates_clean(self):
        report = cv.validate_charter(self.charter)
        self.assertTrue(report.ok, msg=report.render())

    def test_intent_contract_meets_the_acceptance_hard_gate(self):
        # Acceptance judges ONLY against the signed intent contract; the driver
        # HALTs on a missing/unsigned one (R0 B-4). Pin the exact fields.
        ic = self.charter["intent_contract"]
        for field in ("goal", "standard", "proof_of_done"):
            self.assertTrue(str(ic.get(field, "")).strip(), field)
        self.assertIs(ic["confirmed_by_human"], True)

    def test_advisory_pause_shape(self):
        # mode:auto + calibrated + human_ON_the_loop ⇒ every milestone pass is
        # ADVISORY (advisory_acceptance_pass_signoff pause — the gate the real
        # canary exercises). fully_autonomous would auto-ship and never pause.
        self.assertEqual(self.charter["autonomy"]["level"], "human_on_the_loop")
        acc = self.charter["tooling"]["acceptance"]
        self.assertEqual(acc["mode"], "auto")
        self.assertEqual(acc["judge_calibration"]["status"], "calibrated")

    def test_all_routed_roles_are_claude_code(self):
        for role in ("research", "deliver", "dev", "review", "acceptance"):
            cfg = self.charter["tooling"][role]
            self.assertEqual(cfg["harness"], "claude_code", role)
            self.assertEqual(cfg["provider"], "anthropic", role)


class CanaryPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_PLAN, encoding="utf-8") as fh:
            cls.plan = json.load(fh)

    def test_plan_validates_against_schema(self):
        cp._validate_or_raise(self.plan, "campaign-plan.schema.json", "plan")

    def test_two_milestones_with_dependency(self):
        ms = self.plan["milestones"]
        self.assertEqual([m["id"] for m in ms], ["m1-hello", "m2-append"])
        self.assertEqual(ms[1]["depends_on"], ["m1-hello"])
        # unsigned as shipped — the canary's FIRST step is --sign-plan
        self.assertFalse(self.plan["signed_by_human"])


class CanaryCompactPromptTests(unittest.TestCase):
    """Every shipped compact prompt passes the driver's OWN strict-prompt
    content validation (the exact code path a live run resolves through)."""

    def _validate(self, name):
        path = os.path.join(_COMPACT, name)
        with open(path, encoding="utf-8") as fh:
            front, body = Driver._split_front_matter(fh.read())
        problems = Driver._validate_compact_text(front, body)
        self.assertEqual(problems, [], msg=f"{name}: {problems}")

    def test_all_four_compact_prompts_are_self_contained(self):
        for sid in ("sprint-m1", "sprint-m2"):
            for kind in ("dev-prompt", "review-prompt"):
                self._validate(f"{sid}-{kind}.md")

    def test_compact_ids_match_the_plan_sequences(self):
        with open(_PLAN, encoding="utf-8") as fh:
            plan = json.load(fh)
        sids = [s for m in plan["milestones"] for s in m["subsprint_sequence"]]
        for sid in sids:
            for kind in ("dev-prompt", "review-prompt"):
                self.assertTrue(
                    os.path.isfile(os.path.join(_COMPACT, f"{sid}-{kind}.md")),
                    f"missing compact/{sid}-{kind}.md for a planned sub-sprint")


if __name__ == "__main__":
    unittest.main(verbosity=2)
