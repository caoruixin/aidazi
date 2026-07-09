"""OFFLINE companion to the real requirement canary (always on in the suite).

The env-gated real canary (test_real_requirement_canary.py) is skipped in
normal runs, so THIS test keeps its inputs honest continuously: the shipped
charter validates CLEAN against the full charter validator, satisfies the
Phase-2 entry preflights (0a signed intent contract via the acceptance hard
gate's own validator; 0b non-empty CLOSED-ENUM envelope — a free-form layer
name would make every real decompose out-of-envelope), and the requirement
file names the byte-exact sentinels the eval gate enforces. NO subprocess,
NO network.
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

import charter_validator as cv  # noqa: E402
from driver import Driver, route_for_role  # noqa: E402
from run_loop import load_charter  # noqa: E402

_CANARY = os.path.join(_REPO_ROOT, "examples", "real-requirement-canary")


class RequirementCanaryInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.charter = load_charter(os.path.join(_CANARY, "charter.yaml"))
        with open(os.path.join(_CANARY, "requirement.md"),
                  encoding="utf-8") as fh:
            cls.requirement = fh.read()

    def test_charter_validates_clean(self):
        report = cv.validate_charter(self.charter)
        self.assertFalse(list(getattr(report, "errors", []) or []),
                         getattr(report, "errors", None))

    def test_preflight_0a_intent_contract_meets_the_acceptance_hard_gate(self):
        problems = Driver._validate_acceptance_context(
            self.charter.get("intent_contract") or {})
        self.assertEqual(problems, [])

    def test_preflight_0b_envelope_nonempty_and_layers_in_closed_enum(self):
        scope = self.charter["autonomy"]["approved_scope"]
        self.assertTrue(scope.get("modules_in_scope"))
        self.assertTrue(scope.get("layers_allowed"))
        with open(os.path.join(_REPO_ROOT, "schemas",
                               "deliver-plan-verdict.schema.json"),
                  encoding="utf-8") as fh:
            enum = set(json.load(fh)["properties"]["sub_sprints"]["items"]
                       ["properties"]["layers"]["items"]["enum"])
        self.assertTrue(set(scope["layers_allowed"]) <= enum,
                        f"layers_allowed {scope['layers_allowed']} must be a "
                        f"subset of the closed Δ-9 enum — the decompose "
                        f"verdicts are schema-bound to it and the envelope "
                        f"guard compares verbatim")

    def test_all_routed_roles_are_claude_code(self):
        for role in ("research", "deliver", "dev", "review", "acceptance"):
            r = route_for_role(self.charter, role)
            self.assertEqual(r.harness, "claude_code", role)

    def test_requirement_names_the_exact_sentinels(self):
        self.assertIn("HELLO-REQ-M1", self.requirement)
        self.assertIn("HELLO-REQ-M2", self.requirement)
        # …and the eval gate enforces the SAME first sentinel.
        self.assertIn("HELLO-REQ-M1",
                      self.charter["tooling"]["eval"]["cmd"])


if __name__ == "__main__":
    unittest.main()
