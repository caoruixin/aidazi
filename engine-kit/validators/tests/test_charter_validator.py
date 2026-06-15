"""Unit tests for charter_validator (stdlib unittest; no extra deps).

Each test asserts pass/fail AND that the right rule fired, so a future change
that swaps one violation for another is caught.
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

import charter_validator as cv  # noqa: E402

FIXTURES = os.path.join(_TESTS_DIR, "fixtures")


def _fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)


class ValidCharterTests(unittest.TestCase):
    def test_valid_charter_passes(self):
        report = cv.validate_file(_fixture("valid-charter.yaml"))
        self.assertTrue(
            report.ok,
            msg=f"expected valid charter to pass; errors:\n{report.render()}",
        )
        self.assertEqual(report.errors, [])

    def test_valid_charter_has_no_warnings(self):
        report = cv.validate_file(_fixture("valid-charter.yaml"))
        self.assertEqual(
            report.warnings, [], msg=f"unexpected warnings:\n{report.render()}"
        )


class CheckpointBypassTests(unittest.TestCase):
    def test_emptied_checkpoint_fails(self):
        report = cv.validate_file(_fixture("invalid-checkpoint-emptied.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("checkpoint_emptied", report.rules_fired)

    def test_disabled_checkpoint_fails(self):
        report = cv.validate_file(_fixture("invalid-checkpoint-disabled.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("checkpoint_disabled", report.rules_fired)

    def test_overridden_checkpoint_fails(self):
        report = cv.validate_file(_fixture("invalid-checkpoint-overridden.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("checkpoint_overridden", report.rules_fired)


class AcceptanceOnFixRequiredTests(unittest.TestCase):
    def test_human_confirm_false_fails(self):
        report = cv.validate_file(_fixture("invalid-human-confirm-false.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("human_confirm_required", report.rules_fired)

    def test_empty_route_options_fails(self):
        report = cv.validate_file(_fixture("invalid-empty-route-options.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("route_options_nonempty", report.rules_fired)


class CalibrationCorollaryTests(unittest.TestCase):
    def test_skills_while_calibrated_warns_but_passes(self):
        report = cv.validate_file(_fixture("warn-calibration-skills.yaml"))
        self.assertTrue(
            report.ok,
            msg=f"warning must not fail the charter; report:\n{report.render()}",
        )
        self.assertIn("calibration_skills_corollary", report.rules_fired)
        # It is a warning, not an error.
        self.assertEqual(report.errors, [])
        self.assertTrue(any(w.rule == "calibration_skills_corollary" for w in report.warnings))


class AdaptiveInsertBoundTests(unittest.TestCase):
    def test_enabled_without_bound_fails(self):
        report = cv.validate_file(_fixture("invalid-adaptive-insert-unbounded.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("adaptive_insert_bound", report.rules_fired)


class SemanticUnitTests(unittest.TestCase):
    """Direct calls to validate_charter to isolate semantic rules from the
    schema's own structural rejections (which also fire for some fixtures)."""

    def _base(self) -> dict:
        # A minimal-but-structurally-valid charter built in-memory.
        return {
            "mission": {"id": "m", "goal": "g"},
            "autonomy": {
                "level": "human_in_the_loop",
                "approved_scope": {
                    "subsprint_sequence": ["s1"],
                    "layers_allowed": ["l1"],
                    "modules_in_scope": ["m1"],
                },
                "auto_pass_rules": {},
            },
            "budget": {"max_fix_rounds_total": 1, "max_wall_clock_minutes": 1},
            "tooling": {
                "research": {"agent_kind": "claude_code"},
                "deliver": {"agent_kind": "claude_code"},
                "dev": {"agent_kind": "claude_code"},
                "review": {"agent_kind": "codex"},
                "eval": {"cmd": "true", "timeout_seconds": 1},
                "acceptance": {
                    "enabled": False,
                    "on_fix_required": {
                        "human_confirm_required": True,
                        "route_options": ["deliver_fix_iteration"],
                    },
                },
            },
        }

    def test_base_is_clean(self):
        report = cv.validate_charter(self._base())
        self.assertTrue(report.ok, msg=report.render())

    def test_override_key_anywhere_fails(self):
        charter = self._base()
        # Bury an auto-confirm key deep in the tree.
        charter["tooling"]["acceptance"]["on_fix_required"]["auto_confirm_if_clean"] = True
        report = cv.validate_charter(charter)
        self.assertFalse(report.ok)
        self.assertIn("checkpoint_overridden", report.rules_fired)

    def test_adaptive_insert_bound_present_ok(self):
        charter = self._base()
        charter["autonomy"]["auto_pass_rules"]["adaptive_insert"] = {
            "enabled": True,
            "max_inserted_subsprints": 2,
        }
        report = cv.validate_charter(charter)
        self.assertTrue(report.ok, msg=report.render())

    def test_p0a_extension_points_are_noops(self):
        # The P-0a extension hooks must not raise and must not emit issues yet.
        report = cv.Report()
        charter = self._base()
        cv._check_connector_grants(charter, report)
        cv._check_capability_gate(charter, report)
        cv._check_skill_integrity(charter, report)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
