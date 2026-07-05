"""Phase-4 onboarding runnable native-E2E config proposal generator (design §7 / R5).

Proves: a generated proposal is COMPLETE + runnable (executor-contract valid) + leak-free; an
INCOMPLETE proposal is rejected (never a skeleton); a literal secret is rejected (NAMED refs only);
advisory fields; repo inspection drives confidence.

Run: cd engine-kit && python3.12 -m pytest tools/tests/test_e2e_config_proposal.py -q
"""
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_TESTS_DIR)
_REPO = os.path.dirname(os.path.dirname(_TOOLS_DIR))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import e2e_config_proposal as p  # noqa: E402

try:
    from jsonschema.validators import Draft202012Validator
    _HAVE_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    _HAVE_JSONSCHEMA = False

_CRITERIA = [
    {"criterion_id": "shows_welcome", "criterion": "welcome banner", "critical": True,
     "req_id": "REQ-001", "module": "frontend/app"},
    {"criterion_id": "submits_form", "criterion": "form submits", "req_id": "REQ-001"},
]


def _proposal(**kw):
    kw.setdefault("criteria", _CRITERIA)
    kw.setdefault("milestone_id", "M1")
    kw.setdefault("covers_req_ids", ["REQ-001"])
    kw.setdefault("secret_refs", [{"name": "T_USER", "ref": "env:T_USER", "purpose": "login"}])
    return p.generate_proposal(**kw)


class CompletenessTests(unittest.TestCase):
    def test_generated_proposal_is_complete_and_leak_free(self):
        prop = _proposal()
        self.assertEqual(p.proposal_completeness_violations(prop), [])
        self.assertEqual(p.secret_leak_violations(prop), [])
        self.assertEqual(p.validate_proposal(prop), [])

    def test_all_R5_elements_present(self):
        prop = _proposal()
        for dotted, _name in p.REQUIRED_ELEMENTS:
            self.assertIsNotNone(p._get(prop, dotted), dotted)

    def test_incomplete_missing_runner_backend_rejected(self):
        prop = _proposal()
        del prop["tooling"]["e2e"]["runner_argv"]
        viols = p.proposal_completeness_violations(prop)
        self.assertTrue(any("runner" in v["element"] for v in viols))

    def test_empty_remediation_budget_rejected(self):
        prop = _proposal()
        prop["autonomy"]["e2e_remediation"] = {}
        viols = p.proposal_completeness_violations(prop)
        self.assertTrue(any("remediation" in v["element"] for v in viols))

    def test_unmapped_criterion_is_a_completeness_violation(self):
        # every signed criterion must have a bound test (else pre-publication contract HALT).
        prop = _proposal()
        prop["tooling"]["e2e"]["criterion_map"] = {"@crit:shows_welcome": "shows_welcome"}
        viols = p.proposal_completeness_violations(prop)
        self.assertTrue(any("criterion_map" in v["path"] for v in viols))

    def test_bad_surface_rejected(self):
        prop = _proposal(surface="banana")
        viols = p.proposal_completeness_violations(prop)
        self.assertTrue(any(v["path"] == "milestone_binding.surface" for v in viols))

    def test_render_refusal_is_actionable(self):
        prop = _proposal()
        del prop["tooling"]["e2e"]["spec_path"]
        msg = p.render_completeness_refusal(p.proposal_completeness_violations(prop))
        self.assertIn("skeleton", msg)


class SchemaGuardrailTests(unittest.TestCase):
    """Codex P4 R1 blocker 2: validate_proposal SCHEMA-validates, so a hand-authored/tampered
    proposal is rejected even where the completeness/leak heuristics don't fire."""

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_validate_rejects_extra_secret_ref_field(self):
        prop = _proposal()
        prop["secret_refs"] = [{"name": "T", "ref": "env:T", "leaked": "abc123"}]  # extra field
        self.assertTrue(p.validate_proposal(prop))          # rejected (additionalProperties:false)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_validate_rejects_missing_secret_refs_block(self):
        prop = _proposal()
        del prop["secret_refs"]
        self.assertTrue(p.validate_proposal(prop))          # rejected (required top-level block)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_validate_rejects_non_env_secret_ref(self):
        prop = _proposal()
        prop["secret_refs"] = [{"name": "T", "ref": "literalvalue"}]
        self.assertTrue(p.validate_proposal(prop))          # rejected (ref pattern + leak guard)

    def test_schema_violations_fail_closed_shape(self):
        # schema_violations returns a list (never raises); a valid proposal ⇒ [].
        self.assertEqual(p.schema_violations(_proposal()), [])


class SecretLeakTests(unittest.TestCase):
    def test_named_env_ref_is_clean(self):
        prop = _proposal(secret_refs=[{"name": "PW", "ref": "env:PW"}])
        self.assertEqual(p.secret_leak_violations(prop), [])

    def test_literal_ref_is_a_leak(self):
        prop = _proposal(secret_refs=[{"name": "PW", "ref": "hunter2"}])
        v = p.secret_leak_violations(prop)
        self.assertTrue(any("NAMED reference" in x["reason"] for x in v))

    def test_secret_bearing_key_with_literal_is_a_leak(self):
        prop = _proposal()
        prop["tooling"]["e2e"]["browser"] = {"password": "literalpw"}
        v = p.secret_leak_violations(prop)
        self.assertTrue(v)

    def test_named_ref_helpers(self):
        self.assertTrue(p.is_named_secret_ref("env:FOO"))
        self.assertTrue(p.is_named_secret_ref("file:/run/secrets/x"))
        self.assertFalse(p.is_named_secret_ref("plainvalue"))

    def test_generate_drops_literal_under_non_hinted_field(self):
        # Codex P4 R1 blocker 2: a literal under a NON-hinted secret_refs field is NOT emitted.
        prop = _proposal(secret_refs=[
            {"name": "T", "ref": "env:T", "note": "the real password is abc123", "value": "abc"}])
        emitted = prop["secret_refs"][0]
        self.assertEqual(set(emitted), {"name", "ref"})       # note/value stripped at emission
        self.assertEqual(p.secret_leak_violations(prop), [])
        self.assertEqual(p.validate_proposal(prop), [])

    def test_normalize_drops_entries_without_name_or_ref(self):
        self.assertEqual(p._normalize_secret_refs([{"ref": "env:X"}, {"name": "Y"}]), [])
        self.assertEqual(p._normalize_secret_refs([{"name": "Z", "ref": "env:Z", "x": 1}]),
                         [{"name": "Z", "ref": "env:Z"}])


class AdvisoryAndRunnableTests(unittest.TestCase):
    def test_advisory_status_and_confidence(self):
        prop = _proposal(status="proposed")
        self.assertEqual(prop["proposal_status"], "proposed")
        self.assertIn(prop["proposal_confidence"], ("high", "low"))

    def test_confidence_high_when_discovered(self):
        facts = {"spec_path": "e2e/x.spec.ts", "app_start_cmd": ["npm", "run", "dev"],
                 "found": {"spec_path": True, "app_start_cmd": True}}
        self.assertEqual(_proposal(repo_facts=facts)["proposal_confidence"], "high")

    def test_confidence_low_on_defaults(self):
        self.assertEqual(_proposal(repo_facts=None)["proposal_confidence"], "low")

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_generated_tooling_e2e_is_executor_contract_valid(self):
        prop = _proposal()
        ec = json.load(open(os.path.join(_REPO, "schemas", "executor-contract.schema.json")))
        Draft202012Validator(ec).validate(prop["tooling"]["e2e"])

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not installed")
    def test_proposal_is_schema_valid(self):
        prop = _proposal()
        sch = json.load(open(os.path.join(_REPO, "schemas",
                                          "e2e-config-proposal.schema.json")))
        Draft202012Validator(sch).validate(prop)

    def test_criterion_map_covers_every_signed_criterion(self):
        prop = _proposal()
        mapped = set(prop["tooling"]["e2e"]["criterion_map"].values())
        self.assertEqual(mapped, {"shows_welcome", "submits_form"})


class CredentialHaltTests(unittest.TestCase):
    def test_unresolved_env_credential_is_an_r4d_halt(self):
        refs = [{"name": "T_USER", "ref": "env:PHASE4_TEST_USER_ABSENT", "purpose": "login"}]
        unresolved = p.unresolved_secret_refs(refs, env={})
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["env_var"], "PHASE4_TEST_USER_ABSENT")
        msg = p.render_credential_halt(unresolved)
        self.assertIn("PHASE4_TEST_USER_ABSENT", msg)
        self.assertIn("R4-d", msg)

    def test_resolved_credential_no_halt(self):
        refs = [{"name": "T_USER", "ref": "env:PHASE4_USER"}]
        self.assertEqual(p.unresolved_secret_refs(refs, env={"PHASE4_USER": "ada"}), [])

    def test_empty_env_value_is_unresolved(self):
        refs = [{"name": "T", "ref": "env:X"}]
        self.assertEqual(len(p.unresolved_secret_refs(refs, env={"X": ""})), 1)

    def test_non_env_refs_are_not_checked_here(self):
        # file:/vault: are resolved by the adopter's secret backend, not this gate.
        refs = [{"name": "T", "ref": "file:/run/secrets/x"}]
        self.assertEqual(p.unresolved_secret_refs(refs, env={}), [])


class InspectRepoTests(unittest.TestCase):
    def test_inspect_discovers_spec_and_dev_script(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "frontend", "e2e"))
            open(os.path.join(d, "frontend", "e2e", "acc.spec.ts"), "w").close()
            with open(os.path.join(d, "package.json"), "w") as fh:
                json.dump({"scripts": {"dev": "vite"}}, fh)
            facts = p.inspect_repo(d)
            self.assertEqual(facts["spec_path"], "frontend/e2e/acc.spec.ts")
            self.assertEqual(facts["app_start_cmd"], ["npm", "run", "dev"])
            self.assertTrue(facts["found"]["spec_path"])

    def test_inspect_missing_dir_is_empty(self):
        self.assertEqual(p.inspect_repo("/nonexistent/xyz")["found"], {})


if __name__ == "__main__":
    unittest.main()
