"""Unit tests for charter_validator (stdlib unittest; no extra deps).

Each test asserts pass/fail AND that the right rule fired, so a future change
that swaps one violation for another is caught.
"""

import os
import shutil
import sys
import tempfile
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

    def test_p0a_checks_noop_without_new_fields(self):
        # BACKWARD-COMPAT: the P-0a checks are now implemented, but on a legacy
        # charter (agent_kind only — no harness/provider/connectors/skills) they
        # MUST stay silent. A charter that doesn't use the new fields validates
        # exactly as before.
        report = cv.Report()
        charter = self._base()
        cv._check_connector_grants(charter, report)
        cv._check_capability_gate(charter, report)
        cv._check_skill_integrity(charter, report)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])


# --------------------------------------------------------------------------- #
# P-0a checks — Facet A (capability gate), B (skill integrity), C (connectors).
# Each test asserts the SPECIFIC rule fired. Override paths point tests at
# fixture catalogs so the live skills/ + (absent) connectors/ are never touched.
# --------------------------------------------------------------------------- #
_SKILL_CATALOG = _fixture("skill-catalog-with-reqs.yaml")
_CONNECTOR_CATALOG = _fixture("connectors-registry.yaml")


class P0aCleanNewFieldsTests(unittest.TestCase):
    """A charter USING the new fields (valid triples / vendored+pinned+in-whitelist
    skill / read-scope connector on a read-only role) PASSES."""

    def test_clean_v2_newfields_passes(self):
        report = cv.validate_file(_fixture("valid-v2-newfields.yaml"))
        self.assertTrue(report.ok, msg=f"expected PASS; report:\n{report.render()}")
        self.assertEqual(report.errors, [])

    def test_clean_v2_with_connector_catalog_is_fully_clean(self):
        # With the connector catalog supplied, even the 'catalog absent' WARN is
        # gone — zero errors, zero warnings.
        ov = cv.Overrides(connector_catalog_path=_CONNECTOR_CATALOG)
        report = cv.validate_file(_fixture("valid-v2-newfields.yaml"), overrides=ov)
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [], msg=report.render())


class CapabilityGateTests(unittest.TestCase):
    def test_harness_provider_mismatch_fails(self):
        report = cv.validate_file(_fixture("invalid-harness-provider-mismatch.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("harness_provider_mismatch", report.rules_fired)

    def test_dev_on_headless_fails(self):
        report = cv.validate_file(_fixture("invalid-dev-on-headless.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("dev_needs_coding_agent", report.rules_fired)

    def test_verdict_role_submedium_model_fails(self):
        report = cv.validate_file(_fixture("invalid-verdict-submedium-model.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("structured_output_floor", report.rules_fired)

    def test_judgment_role_medium_model_warns_high_recommended(self):
        # acceptance (judgment role) on a structured_output_tier=medium model:
        # meets the floor (PASS) but WARNs that 'high' is the recommended target.
        charter = {
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
                    "harness": "headless",
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "capability_ref": "deepseek-chat-api",  # structured_output_tier: medium
                    "on_fix_required": {
                        "human_confirm_required": True,
                        "route_options": ["deliver_fix_iteration"],
                    },
                },
            },
        }
        report = cv.validate_charter(charter)
        self.assertTrue(report.ok, msg=report.render())  # WARN, not ERROR
        self.assertIn("structured_output_recommended_high", report.rules_fired)
        self.assertTrue(any(
            w.rule == "structured_output_recommended_high" for w in report.warnings))

    def test_unknown_model_warns(self):
        charter = {
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
                "research": {
                    "agent_kind": "headless",
                    "harness": "headless",
                    "provider": "moonshot",
                    "model": "some-unlisted-model",  # not in the registry
                },
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
        report = cv.validate_charter(charter)
        self.assertTrue(report.ok, msg=report.render())  # WARN, not ERROR
        self.assertIn("model_unknown", report.rules_fired)


class SkillIntegrityTests(unittest.TestCase):
    def test_unpinned_skill_source_fails(self):
        report = cv.validate_file(_fixture("invalid-skill-unpinned.yaml"))
        self.assertFalse(report.ok)
        self.assertIn("skill_unpinned", report.rules_fired)

    def test_skill_tool_requirements_exceed_whitelist_fails(self):
        ov = cv.Overrides(skill_catalog_path=_SKILL_CATALOG)
        report = cv.validate_file(
            _fixture("invalid-skill-whitelist-exceeded.yaml"), overrides=ov)
        self.assertFalse(report.ok)
        self.assertIn("skill_tool_whitelist", report.rules_fired)

    def test_tampered_vendored_skill_fails_integrity(self):
        # Build a throwaway repo: copy schemas/, skills/, engine-kit/skill-vendor/
        # into a tempdir, TAMPER a vendored file, then run the integrity check
        # against that repo_root. The live skills/ tree is never modified.
        sv = cv._import_skill_vendor()
        self.assertIsNotNone(sv, "skill_vendor must be importable")
        src_root = cv._REPO_ROOT
        self.assertIsNotNone(src_root)
        with tempfile.TemporaryDirectory(prefix="cv-tamper-") as tmp:
            for sub in ("schemas", "skills"):
                shutil.copytree(os.path.join(src_root, sub), os.path.join(tmp, sub))
            os.makedirs(os.path.join(tmp, "engine-kit", "skill-vendor"))
            shutil.copy2(
                os.path.join(src_root, "engine-kit", "skill-vendor", "skill_vendor.py"),
                os.path.join(tmp, "engine-kit", "skill-vendor", "skill_vendor.py"),
            )
            # Tamper one byte of a vendored skill file.
            target = os.path.join(
                tmp, "skills", "vendored", "code-review-excellence", "SKILL.md")
            with open(target, "a", encoding="utf-8") as fh:
                fh.write("\n<!-- tamper -->\n")

            charter = cv.load_charter(_fixture("invalid-skill-integrity-tampered.yaml"))
            report = cv.Report()
            cv._check_skill_integrity(charter, report, repo_root=tmp, skill_vendor=sv)
        rules = {i.rule for i in report.errors}
        self.assertIn("skill_integrity", rules,
                      msg="\n".join(i.render() for i in report.errors))

    def test_vendored_skill_clean_passes_integrity(self):
        # The same vendored skill, UNtampered, passes integrity against the live
        # repo (sanity: the check is not a false-positive generator).
        charter = cv.load_charter(_fixture("invalid-skill-integrity-tampered.yaml"))
        report = cv.Report()
        cv._check_skill_integrity(charter, report)
        rules = {i.rule for i in report.errors}
        self.assertNotIn("skill_integrity", rules,
                         msg="\n".join(i.render() for i in report.errors))


class ConnectorGrantTests(unittest.TestCase):
    def test_write_scope_connector_on_readonly_role_fails(self):
        ov = cv.Overrides(connector_catalog_path=_CONNECTOR_CATALOG)
        report = cv.validate_file(
            _fixture("invalid-connector-write-on-readonly.yaml"), overrides=ov)
        self.assertFalse(report.ok)
        self.assertIn("connector_scope_sandbox", report.rules_fired)

    def test_bound_skill_needs_ungranted_connector_fails(self):
        ov = cv.Overrides(
            skill_catalog_path=_SKILL_CATALOG,
            connector_catalog_path=_CONNECTOR_CATALOG,
        )
        report = cv.validate_file(
            _fixture("invalid-connector-grant-insufficient.yaml"), overrides=ov)
        self.assertFalse(report.ok)
        self.assertIn("connector_grant_insufficient", report.rules_fired)

    def test_no_connectors_block_is_noop_default_deny(self):
        # A role with no connectors block and no skill connector-requirements is a
        # NO-OP for the connector check (default-deny holds silently).
        charter = cv.load_charter(_fixture("valid-charter.yaml"))
        report = cv.Report()
        cv._check_connector_grants(charter, report)
        self.assertEqual(report.errors, [])
        self.assertEqual(
            [w for w in report.warnings if w.rule.startswith("connector_")], [])


class BackwardCompatTests(unittest.TestCase):
    """The legacy fixtures (no new fields) validate EXACTLY as before — the new
    checks must not change their pass/fail verdicts."""

    def test_legacy_valid_charter_still_passes_clean(self):
        report = cv.validate_file(_fixture("valid-charter.yaml"))
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [], msg=report.render())

    def test_legacy_warn_calibration_still_warns_only(self):
        # This legacy fixture binds a BARE-STRING skill not in the catalog/lock;
        # the new skill-integrity check must leave it untouched (no skill_*
        # errors) — only the pre-existing calibration WARN.
        report = cv.validate_file(_fixture("warn-calibration-skills.yaml"))
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual(report.errors, [])
        self.assertEqual(report.rules_fired, {"calibration_skills_corollary"})

    def test_legacy_invalid_fixtures_still_fail_same_rules(self):
        # Each pre-existing invalid fixture still fails on its original rule and
        # gains no NEW-check errors (the new checks are gated on new fields).
        cases = {
            "invalid-checkpoint-emptied.yaml": "checkpoint_emptied",
            "invalid-checkpoint-disabled.yaml": "checkpoint_disabled",
            "invalid-checkpoint-overridden.yaml": "checkpoint_overridden",
            "invalid-human-confirm-false.yaml": "human_confirm_required",
            "invalid-empty-route-options.yaml": "route_options_nonempty",
            "invalid-adaptive-insert-unbounded.yaml": "adaptive_insert_bound",
        }
        new_rules = {
            "harness_provider_mismatch", "dev_needs_coding_agent",
            "structured_output_floor", "skill_unpinned", "skill_integrity",
            "skill_tool_whitelist", "connector_scope_sandbox",
            "connector_grant_insufficient", "connector_binding_invalid",
        }
        for fixture, expected_rule in cases.items():
            with self.subTest(fixture=fixture):
                report = cv.validate_file(_fixture(fixture))
                self.assertFalse(report.ok)
                self.assertIn(expected_rule, report.rules_fired)
                self.assertEqual(
                    report.rules_fired & new_rules, set(),
                    msg=f"{fixture} unexpectedly tripped a NEW check: "
                        f"{report.rules_fired & new_rules}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
