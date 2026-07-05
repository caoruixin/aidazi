"""Phase-4 native-E2E framework capability contract (design §2/§13).

The contract is machine-readable + CODE-ANCHORED (identity not doc text); the preflight check is
DETERMINISTIC + FAIL-CLOSED (missing/under-versioned requirement or a broken contract REFUSES;
absent requirement is dormant).

Run: cd engine-kit && python3.12 -m pytest tools/tests/test_framework_capabilities.py -q
"""
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT = os.path.dirname(_TOOLS_DIR)
_REPO = os.path.dirname(_ENGINE_KIT)
if _ENGINE_KIT not in sys.path:
    sys.path.insert(0, _ENGINE_KIT)

import framework_capabilities as fc  # noqa: E402

try:
    from jsonschema.validators import Draft202012Validator
    _HAVE_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    _HAVE_JSONSCHEMA = False

_EXPECTED_CAPS = {
    "native_managed_external_e2e", "framework_owned_e2e_provenance",
    "autonomous_e2e_remediation", "codex_adapter_liveness",
}


class ContractIntegrityTests(unittest.TestCase):
    def test_contract_loads_and_declares_the_four_capabilities(self):
        provided = fc.provided_capabilities()
        self.assertTrue(_EXPECTED_CAPS.issubset(set(provided)))

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_contract_is_schema_valid(self):
        contract = fc.load_contract()
        schema = json.load(open(os.path.join(_REPO, "schemas",
                                             "framework-capabilities.schema.json")))
        Draft202012Validator(schema).validate(contract)

    def test_every_capability_is_code_anchored(self):
        # Identity is anchored to CODE (design §12.5): every code_anchor resolves to a real symbol.
        self.assertEqual(fc.anchor_violations(), [])

    def test_a_broken_anchor_is_detected(self):
        contract = {"capabilities": [
            {"id": "x", "version": "1.0", "code_anchor": "engine-kit/nope.py:Ghost"}]}
        viols = fc.anchor_violations(contract, root=_REPO)
        self.assertTrue(any(v["id"] == "x" for v in viols))


class PreflightViolationTests(unittest.TestCase):
    def _contract(self):
        return {"framework_version": "4.1.0", "capabilities": [
            {"id": "native_managed_external_e2e", "version": "1.0",
             "code_anchor": "a:b"}]}

    def test_dormant_when_charter_declares_none(self):
        self.assertEqual(fc.required_capability_violations({}, self._contract()), [])
        self.assertEqual(
            fc.required_capability_violations({"required_framework_capabilities": []},
                                              self._contract()), [])

    def test_satisfied_capability_no_violation(self):
        ch = {"required_framework_capabilities": [
            {"id": "native_managed_external_e2e", "min_version": "1.0"}]}
        self.assertEqual(fc.required_capability_violations(ch, self._contract()), [])

    def test_missing_capability_flagged(self):
        ch = {"required_framework_capabilities": [{"id": "ghost_cap"}]}
        v = fc.required_capability_violations(ch, self._contract())
        self.assertEqual([x["kind"] for x in v], ["missing"])

    def test_under_version_flagged(self):
        ch = {"required_framework_capabilities": [
            {"id": "native_managed_external_e2e", "min_version": "9.0"}]}
        v = fc.required_capability_violations(ch, self._contract())
        self.assertEqual(v[0]["kind"], "under_version")
        self.assertEqual(v[0]["provided_version"], "1.0")

    def test_malformed_entry_flagged(self):
        ch = {"required_framework_capabilities": [{"min_version": "1.0"}]}   # no id
        v = fc.required_capability_violations(ch, self._contract())
        self.assertEqual(v[0]["kind"], "malformed")

    def test_refusal_names_capability_version_and_action(self):
        ch = {"required_framework_capabilities": [{"id": "ghost_cap", "min_version": "2.0"}]}
        v = fc.required_capability_violations(ch, self._contract())
        msg = fc.render_capability_refusal(v, action="refusing the real run")
        self.assertIn("ghost_cap", msg)
        self.assertIn("4.1.0", msg)            # deployed framework version
        self.assertIn("UPGRADE", msg)          # the upgrade/migration action


class FailClosedTests(unittest.TestCase):
    def test_missing_contract_raises_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "governance"))     # dir exists, contract file absent
            with self.assertRaises(fc.CapabilityContractError):
                fc.load_contract(root=d)

    def test_malformed_contract_raises_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "governance"))
            with open(os.path.join(d, "governance", "framework-capabilities.json"), "w") as fh:
                fh.write("{ not json")
            with self.assertRaises(fc.CapabilityContractError):
                fc.load_contract(root=d)

    def test_required_check_fails_closed_on_broken_contract(self):
        # A charter that DECLARES a requirement + an unreadable contract ⇒ raise (never []).
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "governance"))
            ch = {"required_framework_capabilities": [{"id": "x"}]}
            with self.assertRaises(fc.CapabilityContractError):
                fc.required_capability_violations(ch, root=d)


if __name__ == "__main__":
    unittest.main()
