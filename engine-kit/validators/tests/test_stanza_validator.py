"""Unit tests for stanza_validator (stdlib unittest; no extra deps beyond the
validator's own jsonschema + pyyaml runtime deps).

Each test asserts pass/fail AND the offending path/message, so a future schema
change that swaps one rejection for another is caught.
"""

import os
import sys
import unittest

# Make the validator importable whether tests are run via discover from the repo
# root or from inside engine-kit/validators/tests.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_VALIDATORS_DIR = os.path.dirname(_TESTS_DIR)
if _VALIDATORS_DIR not in sys.path:
    sys.path.insert(0, _VALIDATORS_DIR)

import stanza_validator as sv  # noqa: E402

FIXTURES = os.path.join(_TESTS_DIR, "fixtures")


def _fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)


class ValidStanzaTests(unittest.TestCase):
    def test_valid_bare_stanza_passes(self):
        report = sv.validate_file(_fixture("valid-stanza.yaml"))
        self.assertTrue(
            report.ok, msg=f"expected valid stanza to pass; report:\n{report.render()}"
        )
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_valid_wrapped_stanza_passes(self):
        # A sprint-objective doc carrying sprint_stanza: ... is unwrapped first.
        report = sv.validate_file(_fixture("valid-stanza-wrapped.json"))
        self.assertTrue(
            report.ok, msg=f"expected wrapped stanza to pass; report:\n{report.render()}"
        )


class InvalidStanzaTests(unittest.TestCase):
    def test_missing_required_field_fails(self):
        report = sv.validate_file(_fixture("invalid-stanza-missing-field.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("structural", report.rules_fired)
        # The message must name the missing required property.
        self.assertTrue(
            any("exit_criteria" in e.message and "required" in e.message for e in report.errors),
            msg=report.render(),
        )

    def test_wrong_type_fails(self):
        report = sv.validate_file(_fixture("invalid-stanza-wrong-type.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("structural", report.rules_fired)
        # scope_in is a string where an array is required.
        self.assertTrue(
            any(e.path == "scope_in" and "array" in e.message for e in report.errors),
            msg=report.render(),
        )
        # layers[1] is out of the schema enum.
        self.assertTrue(
            any(e.path == "layers.1" and "made_up_layer" in e.message for e in report.errors),
            msg=report.render(),
        )


class ParseAndLoadErrorTests(unittest.TestCase):
    def test_missing_file_reports_cleanly(self):
        report = sv.validate_file(_fixture("does-not-exist.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("stanza_load", report.rules_fired)


class UnwrapUnitTests(unittest.TestCase):
    def test_unwrap_passthrough_for_bare_stanza(self):
        bare = {"sprint_id": "s", "scope_in": ["x"]}
        self.assertIs(sv._unwrap_stanza(bare), bare)

    def test_unwrap_extracts_nested_stanza(self):
        doc = {"title": "doc", "sprint_stanza": {"sprint_id": "s"}}
        self.assertEqual(sv._unwrap_stanza(doc), {"sprint_id": "s"})

    def test_additional_property_rejected(self):
        # schema declares additionalProperties: false — a stray key must fail.
        report = sv.validate_stanza(
            {
                "sprint_id": "s",
                "scope_in": ["x"],
                "layers": ["infra"],
                "exit_criteria": ["c"],
                "bogus_extra": True,
            }
        )
        self.assertFalse(report.ok)
        self.assertIn("structural", report.rules_fired)


if __name__ == "__main__":
    unittest.main(verbosity=2)
