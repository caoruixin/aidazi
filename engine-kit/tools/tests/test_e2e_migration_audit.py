"""Phase-4 existing-adopter native-E2E migration audit (design §13 legacy compat).

Proves: READ-ONLY (no silent mutation of authoritative state); detects native-E2E gaps for
USER-FACING milestones; legacy NON-user-facing milestones stay valid and are NEVER forced into
browser E2E; a clean native adopter has no gaps.

Run: cd engine-kit && python3.12 -m pytest tools/tests/test_e2e_migration_audit.py -q
"""
import copy
import json
import os
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_TESTS_DIR)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import e2e_migration_audit as a  # noqa: E402

_LEDGER = {"requirements": [
    {"id": "REQ-001", "surface": "user_facing"},
    {"id": "REQ-050", "surface": "non_user_facing"},
]}


def _charter(executor_kind="local_http", mode="browser_e2e", remediation=False, cap_pin=False):
    ch = {"tooling": {"e2e": {"executor_kind": executor_kind},
                      "acceptance": {"functional": {"mode": mode}}},
          "autonomy": {}}
    if remediation:
        ch["autonomy"]["e2e_remediation"] = {"enabled": True, "max_rounds": 3}
    if cap_pin:
        ch["required_framework_capabilities"] = [{"id": "native_managed_external_e2e"}]
    return ch


_PLAN = {"milestones": [
    {"id": "M1", "covers_req_ids": ["REQ-001"]},   # user-facing
    {"id": "M9", "covers_req_ids": ["REQ-050"]},   # legacy non-user-facing
]}


class GapDetectionTests(unittest.TestCase):
    def test_dry_run_executor_is_a_blocking_gap(self):
        au = a.audit_adopter(charter=_charter("local_http"), plan=_PLAN, ledger=_LEDGER)
        kinds = [(g["milestone_id"], g["kind"]) for g in au["blocking_gaps"]]
        self.assertIn(("M1", "dry_run_executor"), kinds)
        self.assertTrue(au["authorization_required"])

    def test_missing_tooling_e2e_is_a_blocking_gap(self):
        ch = {"tooling": {"acceptance": {"functional": {"mode": "browser_e2e"}}}, "autonomy": {}}
        au = a.audit_adopter(charter=ch, plan=_PLAN, ledger=_LEDGER)
        self.assertTrue(any(g["kind"] == "missing_tooling_e2e" for g in au["blocking_gaps"]))

    def test_user_facing_not_browser_e2e_is_a_blocking_gap(self):
        au = a.audit_adopter(charter=_charter(mode="static"), plan=_PLAN, ledger=_LEDGER)
        self.assertTrue(
            any(g["kind"] == "user_facing_not_browser_e2e" for g in au["blocking_gaps"]))

    def test_no_remediation_and_no_cap_pin_are_advisory(self):
        au = a.audit_adopter(charter=_charter("external_test_runner"), plan=_PLAN, ledger=_LEDGER)
        kinds = {g["kind"] for g in au["advisory_opportunities"]}
        self.assertIn("no_signed_remediation_budget", kinds)
        self.assertIn("no_capability_pin", kinds)
        # advisory, not blocking — a real-execution executor with no budget is legacy-safe.
        self.assertEqual(au["blocking_gaps"], [])


class LegacySafetyTests(unittest.TestCase):
    def test_non_user_facing_milestone_never_flagged(self):
        au = a.audit_adopter(charter=_charter("local_http"), plan=_PLAN, ledger=_LEDGER)
        flagged = [g["milestone_id"]
                   for g in au["blocking_gaps"] + au["advisory_opportunities"]]
        self.assertNotIn("M9", flagged)   # legacy non-user-facing not forced into browser E2E

    def test_clean_native_adopter_has_no_findings(self):
        ch = _charter("external_test_runner", remediation=True, cap_pin=True)
        au = a.audit_adopter(charter=ch, plan={"milestones": [
            {"id": "M1", "covers_req_ids": ["REQ-001"]}]}, ledger=_LEDGER)
        self.assertEqual(au["blocking_gaps"], [])
        self.assertEqual(au["advisory_opportunities"], [])
        self.assertFalse(au["authorization_required"])

    def test_unknowable_surface_not_flagged(self):
        # a covered rid with no valid ledger classification ⇒ OW-M3 owns it, not this audit.
        au = a.audit_adopter(charter=_charter("local_http"),
                             plan={"milestones": [{"id": "MX", "covers_req_ids": ["REQ-unknown"]}]},
                             ledger=_LEDGER)
        self.assertEqual(au["blocking_gaps"], [])


class NoSilentMutationTests(unittest.TestCase):
    def test_audit_never_mutates_inputs(self):
        ch, plan, led = _charter("local_http"), copy.deepcopy(_PLAN), copy.deepcopy(_LEDGER)
        before = json.dumps([ch, plan, led], sort_keys=True)
        a.audit_adopter(charter=ch, plan=plan, ledger=led)
        self.assertEqual(json.dumps([ch, plan, led], sort_keys=True), before)
        self.assertTrue(a.audit_is_read_only(charter=ch, plan=plan, ledger=led))

    def test_no_mutation_flag_and_immutable_list_present(self):
        au = a.audit_adopter(charter=_charter("local_http"), plan=_PLAN, ledger=_LEDGER)
        self.assertTrue(au["no_mutation_performed"])
        for item in ("campaign plans", "signed charters", "requirement ledgers",
                     "Acceptance reports", "E2E configuration", "aidazi pins"):
            self.assertIn(item, au["immutable_on_upgrade"])

    def test_render_marks_read_only(self):
        au = a.audit_adopter(charter=_charter("local_http"), plan=_PLAN, ledger=_LEDGER)
        self.assertIn("READ-ONLY", a.render_audit(au))


if __name__ == "__main__":
    unittest.main()
