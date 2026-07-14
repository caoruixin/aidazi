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


class AcceptanceNamespaceValidateCharterTests(unittest.TestCase):
    """charter_compat normalization integrated through validate_charter (P-A §1.4)."""

    def test_enabled_only_validates_clean_and_silent(self):
        charter = cv.load_charter(_fixture("valid-charter.yaml"))
        acc = charter["tooling"]["acceptance"]
        acc.pop("mode", None)
        acc["enabled"] = True  # legacy enabled-only → silent map to mode
        report = cv.validate_charter(charter, cv.load_schema())
        self.assertTrue(report.ok, report.render())
        self.assertNotIn("acceptance_namespace", report.rules_fired)
        self.assertEqual(acc["mode"], "auto")

    def test_enabled_mode_conflict_is_validation_error(self):
        charter = cv.load_charter(_fixture("valid-charter.yaml"))
        acc = charter["tooling"]["acceptance"]
        acc["enabled"] = True
        acc["mode"] = "off"  # disagree → conflict
        report = cv.validate_charter(charter, cv.load_schema())
        self.assertFalse(report.ok)
        self.assertIn("acceptance_namespace", {e.rule for e in report.errors})

    def test_mode_only_validates_clean(self):
        charter = cv.load_charter(_fixture("valid-charter.yaml"))
        acc = charter["tooling"]["acceptance"]
        acc.pop("enabled", None)
        acc["mode"] = "advisory"
        report = cv.validate_charter(charter, cv.load_schema())
        self.assertTrue(report.ok, report.render())
        self.assertNotIn("acceptance_namespace", report.rules_fired)

    def test_both_present_agree_warns_only(self):
        charter = cv.load_charter(_fixture("valid-charter.yaml"))
        acc = charter["tooling"]["acceptance"]
        acc["enabled"] = True
        acc["mode"] = "auto"
        report = cv.validate_charter(charter, cv.load_schema())
        self.assertTrue(report.ok, report.render())
        self.assertIn("acceptance_namespace", report.rules_fired)
        self.assertEqual(report.errors, [])

    def test_top_level_block_migrated_with_warning(self):
        charter = cv.load_charter(_fixture("valid-charter.yaml"))
        acc = charter["tooling"]["acceptance"]
        acc.pop("mode", None)
        acc["enabled"] = True
        charter["acceptance"] = {"on_fix_required": acc.pop("on_fix_required")}
        report = cv.validate_charter(charter, cv.load_schema())
        self.assertTrue(report.ok, report.render())
        self.assertNotIn("acceptance", charter)              # moved under tooling
        self.assertIn("acceptance_namespace", report.rules_fired)  # warned

    def test_malformed_canonical_acceptance_not_hidden(self):
        charter = cv.load_charter(_fixture("valid-charter.yaml"))
        charter["tooling"]["acceptance"] = "garbage"
        charter["acceptance"] = {"enabled": True}
        report = cv.validate_charter(charter, cv.load_schema())
        self.assertFalse(report.ok)
        self.assertIn("acceptance_namespace", {e.rule for e in report.errors})


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


class GapFollowupBoundTests(unittest.TestCase):
    """Δ-19 / Constitution §1.7-F §A.3 STATIC gap-followup guard — the build-time sibling
    of campaign.py:_gap_followup_bounds. Mirrors AdaptiveInsertBoundTests: each test asserts
    pass/fail AND the exact rule, so swapping one evasion shape for another is caught."""

    # --- end-to-end through validate_file + Overrides(campaign_plan_path=...) ---
    def test_unbounded_gap_followup_fails(self):
        report = cv.validate_file(
            _fixture("valid-charter.yaml"),
            overrides=cv.Overrides(
                campaign_plan_path=_fixture("invalid-gap-followup-unbounded.yaml")))
        self.assertFalse(report.ok)
        self.assertIn("gap_followup_bound", report.rules_fired)

    def test_no_progress_gt_one_fails(self):
        report = cv.validate_file(
            _fixture("valid-charter.yaml"),
            overrides=cv.Overrides(
                campaign_plan_path=_fixture("invalid-gap-followup-no-progress.yaml")))
        self.assertFalse(report.ok)
        self.assertIn("gap_followup_no_progress_pin", report.rules_fired)

    def test_valid_gap_followup_passes(self):
        report = cv.validate_file(
            _fixture("valid-charter.yaml"),
            overrides=cv.Overrides(
                campaign_plan_path=_fixture("valid-campaign-plan-gap-followup.yaml")))
        self.assertTrue(report.ok, msg=report.render())
        self.assertNotIn("gap_followup_bound", report.rules_fired)
        self.assertNotIn("gap_followup_no_progress_pin", report.rules_fired)

    def test_no_campaign_plan_is_noop(self):
        # The charter-only production path never touches the new check.
        report = cv.validate_file(_fixture("valid-charter.yaml"))
        self.assertTrue(report.ok, msg=report.render())
        self.assertNotIn("gap_followup_bound", report.rules_fired)
        self.assertNotIn("gap_followup_no_progress_pin", report.rules_fired)

    # --- direct unit calls on the pure function (mirrors test_p0a_checks_noop_*) ---
    def test_none_campaign_plan_is_noop(self):
        report = cv.Report()
        cv._check_gap_followup_bounds(None, report)
        self.assertTrue(report.ok)
        self.assertEqual(report.rules_fired, set())

    def test_absent_block_is_legitimate(self):
        # No gap_followup block ⇒ the runtime applies conservative engine defaults; the
        # static guard MUST stay silent (absence is the legitimate non-bypass).
        report = cv.Report()
        cv._check_gap_followup_bounds({"schema_version": "1"}, report)
        self.assertTrue(report.ok)
        self.assertEqual(report.rules_fired, set())

    def test_missing_max_subsprints_fails(self):
        report = cv.Report()
        cv._check_gap_followup_bounds(
            {"gap_followup": {"max_no_progress_rounds": 1}}, report)
        self.assertFalse(report.ok)
        self.assertIn("gap_followup_bound", report.rules_fired)

    def test_missing_no_progress_fails(self):
        report = cv.Report()
        cv._check_gap_followup_bounds({"gap_followup": {"max_subsprints": 3}}, report)
        self.assertFalse(report.ok)
        self.assertIn("gap_followup_no_progress_pin", report.rules_fired)

    def test_no_progress_two_fails(self):
        report = cv.Report()
        cv._check_gap_followup_bounds(
            {"gap_followup": {"max_subsprints": 3, "max_no_progress_rounds": 2}}, report)
        self.assertFalse(report.ok)
        self.assertIn("gap_followup_no_progress_pin", report.rules_fired)

    def test_both_bounds_pinned_one_passes(self):
        report = cv.Report()
        cv._check_gap_followup_bounds(
            {"gap_followup": {"max_subsprints": 3, "max_no_progress_rounds": 1}}, report)
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual(report.rules_fired, set())

    def test_non_dict_gap_followup_is_structural_not_semantic(self):
        # A non-object gap_followup is the campaign-plan schema's structural rejection; the
        # semantic guard adds nothing (stays silent rather than double-reporting).
        report = cv.Report()
        cv._check_gap_followup_bounds({"gap_followup": [1, 2]}, report)
        self.assertTrue(report.ok)
        self.assertEqual(report.rules_fired, set())

    def test_gap_followup_does_not_disable_fix_required(self):
        # §3.5 / §A.3: the gap-followup guard must NOT widen scope or weaken the quality
        # fix_required→human-confirm path. That path is still enforced on the charter
        # regardless of any campaign-plan gap_followup block.
        charter = cv.load_charter(_fixture("valid-charter.yaml"))
        charter["tooling"]["acceptance"]["on_fix_required"]["human_confirm_required"] = False
        report = cv.validate_charter(charter)
        self.assertFalse(report.ok)
        self.assertIn("human_confirm_required", report.rules_fired)

    def test_missing_campaign_plan_path_reports_load_error(self):
        # A supplied-but-unreadable campaign plan fails closed (clear error), it does not
        # silently skip the gap_followup cross-check.
        report = cv.validate_file(
            _fixture("valid-charter.yaml"),
            overrides=cv.Overrides(
                campaign_plan_path=_fixture("does-not-exist-campaign-plan.json")))
        self.assertFalse(report.ok)
        self.assertIn("campaign_plan_load", report.rules_fired)

    # --- structural layer: validate_campaign_plan runs campaign-plan.schema.json so the
    #     CLI / Overrides path catches type/shape evasions the pure semantic check cannot ---
    def _plan(self, **gf):
        p = {"campaign_id": "c1", "goal": "g",
             "milestones": [{"id": "m1", "objective": "o"}]}
        if gf:
            p["gap_followup"] = gf
        return p

    def test_validate_campaign_plan_clean(self):
        report = cv.Report()
        cv.validate_campaign_plan(self._plan(max_subsprints=3, max_no_progress_rounds=1),
                                  report)
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual(report.rules_fired, set())

    def test_non_object_gap_followup_is_structural(self):
        report = cv.Report()
        plan = self._plan()
        plan["gap_followup"] = []  # schema: gap_followup.type=object
        cv.validate_campaign_plan(plan, report)
        self.assertFalse(report.ok)
        self.assertIn("campaign_plan_structural", report.rules_fired)

    def test_zero_max_subsprints_is_structural(self):
        report = cv.Report()
        cv.validate_campaign_plan(self._plan(max_subsprints=0, max_no_progress_rounds=1),
                                  report)
        self.assertFalse(report.ok)
        self.assertIn("campaign_plan_structural", report.rules_fired)  # schema minimum:1

    def test_bool_no_progress_rejected_by_pin(self):
        # True == 1 in Python, but the strict-int semantic pin (and the integer schema type)
        # reject the masquerade.
        report = cv.Report()
        cv.validate_campaign_plan(self._plan(max_subsprints=3, max_no_progress_rounds=True),
                                  report)
        self.assertFalse(report.ok)
        self.assertIn("gap_followup_no_progress_pin", report.rules_fired)

    def test_malformed_plan_shape_is_structural(self):
        report = cv.Report()
        cv.validate_campaign_plan({"goal": "missing campaign_id and milestones"}, report)
        self.assertFalse(report.ok)
        self.assertIn("campaign_plan_structural", report.rules_fired)

    def test_scalar_root_is_structural(self):
        # A scalar root ("not a plan") must FAIL the schema (is not of type 'object'), not
        # silently pass because _check_gap_followup_bounds no-ops on a non-dict (R2 false-PASS).
        report = cv.Report()
        cv.validate_campaign_plan("not a plan", report)
        self.assertFalse(report.ok)
        self.assertIn("campaign_plan_structural", report.rules_fired)

    def test_none_root_is_structural(self):
        report = cv.Report()
        cv.validate_campaign_plan(None, report)
        self.assertFalse(report.ok)
        self.assertIn("campaign_plan_structural", report.rules_fired)

    def test_scalar_campaign_plan_fixture_fails_via_overrides(self):
        report = cv.validate_file(
            _fixture("valid-charter.yaml"),
            overrides=cv.Overrides(
                campaign_plan_path=_fixture("invalid-campaign-plan-scalar.yaml")))
        self.assertFalse(report.ok)
        self.assertIn("campaign_plan_structural", report.rules_fired)

    def test_blank_campaign_plan_fixture_fails_via_overrides(self):
        # A comment-only file loads as None (no parse error) — it must be validated (structural
        # failure), not skipped as "nothing supplied".
        report = cv.validate_file(
            _fixture("valid-charter.yaml"),
            overrides=cv.Overrides(
                campaign_plan_path=_fixture("empty-campaign-plan.yaml")))
        self.assertFalse(report.ok)
        self.assertIn("campaign_plan_structural", report.rules_fired)

    # --- pure-function hardened pin (no schema): bool / float cannot masquerade as 1 ---
    def test_pure_pin_rejects_bool(self):
        report = cv.Report()
        cv._check_gap_followup_bounds(
            {"gap_followup": {"max_subsprints": 3, "max_no_progress_rounds": True}}, report)
        self.assertFalse(report.ok)
        self.assertIn("gap_followup_no_progress_pin", report.rules_fired)

    def test_pure_pin_rejects_float(self):
        report = cv.Report()
        cv._check_gap_followup_bounds(
            {"gap_followup": {"max_subsprints": 3, "max_no_progress_rounds": 1.0}}, report)
        self.assertFalse(report.ok)
        self.assertIn("gap_followup_no_progress_pin", report.rules_fired)


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
                "eval": {"cmd": 'cd "$EVAL_REPO_DIR" && true', "timeout_seconds": 1},
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
        cv._check_network_access(charter, report)  # no grant ⇒ stays silent
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_network_access_grant_passes_cleanly(self):
        # Network grants are shipped defaults for the five LLM roles; the runtime
        # audits routed grants, while validation stays clean.
        charter = self._base()
        charter["tooling"]["dev"]["sandbox"] = "workspace_write"
        charter["tooling"]["dev"]["network_access"] = True
        report = cv.validate_charter(charter)
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [], msg=report.render())

    def test_network_access_on_read_only_role_passes_cleanly(self):
        # review defaults read_only; the adapter/sandbox decides whether the grant
        # has an effect, so the validator does not treat the declaration as a bug.
        charter = self._base()
        charter["tooling"]["review"]["network_access"] = True
        report = cv.validate_charter(charter)
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual(report.warnings, [], msg=report.render())

    def test_no_network_access_is_silent(self):
        charter = self._base()
        charter["tooling"]["dev"]["network_access"] = False
        report = cv.validate_charter(charter)
        self.assertTrue(report.ok, msg=report.render())
        self.assertNotIn("network_access_granted", report.rules_fired)
        self.assertNotIn("network_on_read_only_role", report.rules_fired)


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
                "eval": {"cmd": 'cd "$EVAL_REPO_DIR" && true', "timeout_seconds": 1},
                "acceptance": {
                    "enabled": False,
                    "harness": "headless",
                    "provider": "deepseek",
                    "model": "deepseek-v4-pro",
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
                "eval": {"cmd": 'cd "$EVAL_REPO_DIR" && true', "timeout_seconds": 1},
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


def _facet_a_charter() -> dict:
    """A full charter with VALID v2 Facet-A bindings (mirrors the template), for
    capability-gate tests that mutate ONE role to trigger a specific rule. The
    unmutated charter validates clean."""
    return {
        "mission": {"id": "m", "goal": "g"},
        "autonomy": {"level": "human_in_the_loop",
                     "approved_scope": {"subsprint_sequence": ["s1"],
                                        "layers_allowed": ["l1"],
                                        "modules_in_scope": ["m1"]},
                     "auto_pass_rules": {}},
        "budget": {"max_fix_rounds_total": 1, "max_wall_clock_minutes": 1},
        "tooling": {
            "research": {"agent_kind": "claude_code", "harness": "claude_code",
                         "provider": "anthropic", "model": "claude-opus-4-8",
                         "capability_ref": "anthropic-opus-judge"},
            "deliver": {"agent_kind": "claude_code", "harness": "claude_code",
                        "provider": "anthropic", "model": "claude-opus-4-8",
                        "capability_ref": "anthropic-opus-judge"},
            "dev": {"agent_kind": "claude_code", "harness": "claude_code",
                    "provider": "anthropic", "model": "claude-sonnet-4-6",
                    "capability_ref": "anthropic-sonnet-dev",
                    "sandbox": "workspace_write"},
            "review": {"agent_kind": "codex", "harness": "codex",
                       "provider": "openai", "model": "gpt-5.5",
                       "capability_ref": "openai-gpt5-codex",
                       "tools": ["Read", "Grep", "Glob"]},
            "eval": {"cmd": 'cd "$EVAL_REPO_DIR" && true', "timeout_seconds": 1},
            "acceptance": {"enabled": False, "agent_kind": "claude_code",
                           "harness": "claude_code", "provider": "anthropic",
                           "model": "claude-opus-4-8",
                           "capability_ref": "anthropic-opus-judge",
                           "tools": ["Read", "Grep", "Glob"],
                           "on_fix_required": {"human_confirm_required": True,
                                               "route_options": ["deliver_fix_iteration"]}},
        },
    }


class CapabilityGateTripleTests(unittest.TestCase):
    """The STRENGTHENED capability gate validates the role's (harness, provider,
    model) AGAINST the referenced capability profile — a capability_ref is no longer
    decorative. (Hardening from the Codex gpt-5.5 review of the dev→Kimi rebind.)"""

    def test_base_facet_a_charter_is_clean(self):
        report = cv.validate_charter(_facet_a_charter())
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual(report.warnings, [], msg=report.render())

    def test_model_mismatch_vs_capability_ref_errors(self):
        c = _facet_a_charter()
        c["tooling"]["dev"]["model"] = "totally-wrong-model"  # ref says claude-sonnet-4-6
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("capability_ref_model_mismatch", report.rules_fired)

    def test_provider_mismatch_vs_capability_ref_errors(self):
        c = _facet_a_charter()
        # headless harness ⇒ no provider-lock, so ONLY the ref provider mismatch fires.
        c["tooling"]["review"].update(harness="headless", provider="anthropic")
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("capability_ref_provider_mismatch", report.rules_fired)

    def test_harness_not_in_compat_errors(self):
        c = _facet_a_charter()
        # moonshot-kimi-code is harness_compat:[kimi]; driving it via headless is invalid.
        c["tooling"]["deliver"].update(
            harness="headless", provider="moonshot",
            model="kimi-code/kimi-for-coding", capability_ref="moonshot-kimi-code")
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("harness_not_compatible", report.rules_fired)

    def test_acceptance_non_calibratable_model_errors(self):
        c = _facet_a_charter()
        # deepseek-weak-api is calibratable:false — forbidden for the Acceptance judge.
        c["tooling"]["acceptance"].update(
            harness="headless", provider="deepseek", model="deepseek-weak",
            capability_ref="deepseek-weak-api")
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("acceptance_needs_calibratable", report.rules_fired)

    def test_dev_non_tool_use_model_errors(self):
        # No SHIPPED profile is tool_use:false, so use the edge fixture registry.
        c = _facet_a_charter()
        c["tooling"]["dev"].update(
            provider="anthropic", model="edge-no-tooluse-model",
            capability_ref="edge-no-tooluse")
        report = cv.Report()
        cv._check_capability_gate(
            c, report, model_registry_path=_fixture("model-registry-edge.yaml"))
        rules = {i.rule for i in report.errors}
        self.assertIn("dev_needs_tool_use", rules)

    def test_unknown_capability_ref_errors_no_silent_fallback(self):
        # A present-but-unresolved capability_ref ERRORS — it must NOT silently fall
        # back to a provider/model match (else a typo'd ref validates decoratively).
        c = _facet_a_charter()
        c["tooling"]["review"]["capability_ref"] = "openai-gpt5-typo"  # provider/model still match openai-gpt5-codex
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("capability_ref_unknown", report.rules_fired)

    def test_capability_ref_without_explicit_model_errors(self):
        # A v2 binding with an omitted model is underspecified — the runtime routes
        # "" (no hydration from the ref), so it must fail closed.
        c = _facet_a_charter()
        del c["tooling"]["dev"]["model"]  # keep capability_ref: anthropic-sonnet-dev
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("facet_a_underspecified", report.rules_fired)

    def test_no_provider_bare_model_facet_a_errors(self):
        # A v2 binding (harness present) with NO provider and no capability_ref
        # validates as underspecified — the runtime would route provider="".
        c = _facet_a_charter()
        del c["tooling"]["review"]["provider"]
        del c["tooling"]["review"]["capability_ref"]   # bare model, no ref
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("facet_a_underspecified", report.rules_fired)

    def test_empty_string_harness_falls_back_to_agent_kind(self):
        # The runtime routes `harness or agent_kind` (TRUTHY) — an empty-string
        # harness falls through to agent_kind. The validator must use the SAME
        # resolution, so harness:"" + agent_kind:codex is validated as codex (here
        # provider-locked to openai, so an anthropic provider trips the lock).
        c = _facet_a_charter()
        c["tooling"]["review"].update(harness="", agent_kind="codex",
                                      provider="anthropic")
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("harness_provider_mismatch", report.rules_fired)

    def test_harness_compat_missing_in_profile_errors(self):
        # A resolved profile with NO harness_compat list cannot be verified — fail
        # closed (a custom profile must not be able to disable the compat gate).
        c = _facet_a_charter()
        c["tooling"]["deliver"].update(
            harness="claude_code", provider="anthropic",
            model="edge-no-compat-model", capability_ref="edge-no-harness-compat")
        report = cv.Report()
        cv._check_capability_gate(
            c, report, model_registry_path=_fixture("model-registry-edge.yaml"))
        self.assertIn("harness_compat_missing", {i.rule for i in report.errors})

    def test_omitted_harness_uses_agent_kind_for_compat(self):
        # The runtime routes on `harness or agent_kind`; the gate must check the SAME
        # effective harness. A role that OMITS harness but sets a compat-incompatible
        # agent_kind must still trip harness_not_compatible (not silently bypass it).
        c = _facet_a_charter()
        c["tooling"]["deliver"].pop("harness", None)
        c["tooling"]["deliver"].update(
            agent_kind="headless", provider="moonshot",
            model="kimi-code/kimi-for-coding", capability_ref="moonshot-kimi-code")
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("harness_not_compatible", report.rules_fired)

    def test_dev_omitted_harness_noncoding_agent_kind_errors(self):
        # Dev that omits harness but uses a non-coding agent_kind (headless) must
        # still trip dev_needs_coding_agent (effective harness = agent_kind).
        c = _facet_a_charter()
        c["tooling"]["dev"].pop("harness", None)
        c["tooling"]["dev"]["agent_kind"] = "headless"
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("dev_needs_coding_agent", report.rules_fired)


class ReviewAcceptanceSharedModelTests(unittest.TestCase):
    """Review and Acceptance MAY share a model: independence is by role/perspective/
    timing (engineering-per-sub-sprint vs customer-at-milestone), NOT model diversity.
    An ENABLED Acceptance with the SAME binding as Review validates clean — no warning."""

    def test_identical_enabled_review_acceptance_is_clean(self):
        c = _facet_a_charter()
        c["tooling"]["acceptance"].update(
            enabled=True, harness="codex", provider="openai", model="gpt-5.5",
            capability_ref="openai-gpt5-codex")  # == review, on purpose
        report = cv.validate_charter(c)
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual(report.warnings, [], msg=report.render())


class ProductionAgenticAcceptanceTests(unittest.TestCase):
    @staticmethod
    def _production_charter():
        c = _facet_a_charter()
        acc = c["tooling"]["acceptance"]
        acc.pop("enabled", None)
        acc.update({
            "mode": "advisory",
            "sandbox": "read_only",
            "functional": {
                "mode": "browser_e2e",
                "interaction_mode": "hybrid",
                "target_environment": "production",
                "checklist_path": "docs/acceptance/checklist.json",
                "browser": {
                    "allowed_origins": ["https://app.example.com"],
                    "allowed_actions": [
                        "navigate", "click", "fill", "screenshot",
                        "read_console", "read_network",
                    ],
                },
                "production": {
                    "side_effect_policy": "explicit_allow",
                    "allowed_side_effects": ["acceptance_test_data"],
                    "denied_side_effects": ["payment"],
                },
            },
        })
        c["tooling"]["e2e"] = {
            "executor_kind": "playwright",
            "target_environment": "production",
            "readiness": {"url": "/", "timeout_seconds": 30},
            "base_url": "https://app.example.com",
            "allowed_origins": ["https://app.example.com"],
            "journeys": [{"id": "baseline", "steps": [
                {"action": "navigate", "url": "/"},
            ]}],
            "lifecycle_operations": [
                {"id": "seed", "phase": "setup", "command": ["seed"],
                 "environments": ["production"],
                 "side_effect": "acceptance_test_data"},
                {"id": "cleanup", "phase": "cleanup", "command": ["cleanup"],
                 "environments": ["production"],
                 "side_effect": "acceptance_test_data"},
            ],
        }
        return c

    def test_explicitly_authorized_production_hybrid_is_valid(self):
        report = cv.validate_charter(self._production_charter())
        self.assertTrue(report.ok, msg=report.render())

    def test_production_setup_without_cleanup_fails(self):
        c = self._production_charter()
        c["tooling"]["e2e"]["lifecycle_operations"].pop()
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("production_cleanup_missing", report.rules_fired)

    def test_hybrid_acceptance_cannot_write_repository(self):
        c = self._production_charter()
        c["tooling"]["acceptance"]["sandbox"] = "workspace_write"
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("acceptance_repository_write_forbidden", report.rules_fired)


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


class Track1TaskSelectableSkillTests(unittest.TestCase):
    """Track 1 §2.3 / Codex BLOCKING-3 — a catalog skill carrying a `signals` tag is
    TASK-SELECTABLE (select_skills_for_task can mount it on any non-acceptance role), so it must
    get the SAME tool-whitelist / pin / integrity discipline as a default binding even when no
    role binds it. A skill WITHOUT `signals` is never task-selected, so it is NOT validated unless
    bound (dormancy)."""

    # A single read-only dev role with defaults DISABLED, so the ONLY bindings come from the
    # task-selectable (signal-tagged) catalog universe — isolating the check under test.
    def _charter(self):
        return {"tooling": {"dev": {
            "agent_kind": "claude_code", "harness": "claude_code",
            "tools": ["Read", "Grep", "Glob"],
            "skills": {"mode": "disable"}}}}

    def _catalog_path(self, tmp, skills_yaml: str) -> str:
        p = os.path.join(tmp, "registry.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("catalog_version: 1\nrole_defaults:\n  dev: [base]\nskills:\n"
                     "  base:\n    title: base\n    source: {repo: local}\n"
                     "    license: aidazi\n    provenance: authored\n    status: active\n"
                     + skills_yaml)
        return p

    def _rules(self, skills_yaml: str) -> set:
        report = cv.Report()
        with tempfile.TemporaryDirectory(prefix="cv-track1-") as tmp:
            cv._check_skill_integrity(
                self._charter(), report,
                skill_catalog_path=self._catalog_path(tmp, skills_yaml),
                repo_root=cv._REPO_ROOT)
        return {i.rule for i in report.errors}

    def test_signal_tagged_skill_exceeding_whitelist_is_flagged(self):
        # ui-write-skill is signal-tagged AND needs Write → exceeds the read-only dev whitelist,
        # so it is flagged even though no role binds it (it is task-selectable).
        rules = self._rules(
            "  ui-write-skill:\n    title: ui\n    source: {repo: local}\n"
            "    license: aidazi\n    provenance: authored\n    status: active\n"
            "    signals: [ui]\n    tool_requirements: [Write]\n")
        self.assertIn("skill_tool_whitelist", rules)

    def test_signal_tagged_readonly_skill_is_clean(self):
        # Read-only-safe signal-tagged skill ([] tool_requirements) → no whitelist violation.
        rules = self._rules(
            "  ui-readonly-skill:\n    title: ui\n    source: {repo: local}\n"
            "    license: aidazi\n    provenance: authored\n    status: active\n"
            "    signals: [ui]\n    tool_requirements: []\n")
        self.assertNotIn("skill_tool_whitelist", rules)

    def test_untagged_skill_is_not_task_selected(self):
        # Same overbroad tool_requirements but NO `signals` → not task-selectable → not validated
        # (dormancy: the machinery only enforces the universe a sub-sprint could actually mount).
        rules = self._rules(
            "  plain-write-skill:\n    title: plain\n    source: {repo: local}\n"
            "    license: aidazi\n    provenance: authored\n    status: active\n"
            "    tool_requirements: [Write]\n")
        self.assertNotIn("skill_tool_whitelist", rules)


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
            # Phase-3 halt_conditions / notifications — gated on the new fields.
            "halt_condition_id_collision", "halt_condition_id_override",
            "halt_condition_duplicate_id", "halt_condition_unknown_metric",
            "halt_condition_op_mismatch", "halt_condition_value_type",
            "halt_conditions_shape", "notifications_shape",
            "notifications_argv0_blank", "notifications_inert",
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


class HaltConditionsTests(unittest.TestCase):
    """Phase-3 autonomy.halt_conditions (design §3.6). Default-OFF NO-OP + the
    tighten-only closed-set / collision ERRORs."""

    def _base(self) -> dict:
        return SemanticUnitTests._base(self)

    def test_absent_is_noop(self):
        report = cv.validate_charter(self._base())
        self.assertTrue(report.ok, msg=report.render())
        self.assertNotIn("halt_conditions_shape", report.rules_fired)

    def test_empty_list_is_noop(self):
        c = self._base()
        c["autonomy"]["halt_conditions"] = []
        report = cv.validate_charter(c)
        self.assertTrue(report.ok, msg=report.render())

    def test_valid_conditions_pass(self):
        c = self._base()
        c["autonomy"]["halt_conditions"] = [
            {"id": "hot-milestone",
             "when": {"metric": "milestone_id", "op": "in", "value": ["M-auth"]}},
            {"id": "gate_e2e", "note": "personally gate user-facing",
             "when": {"metric": "milestone_functional_acceptance", "op": "==",
                      "value": "browser_e2e"}},
            {"id": "not_s3",
             "when": {"metric": "subsprint_id", "op": "not_in", "value": ["s3"]}},
        ]
        report = cv.validate_charter(c)
        self.assertTrue(report.ok, msg=report.render())

    def test_id_collision_with_mandatory_checkpoint_fails(self):
        c = self._base()
        c["autonomy"]["halt_conditions"] = [
            {"id": "gate_hard_fail",
             "when": {"metric": "milestone_id", "op": "==", "value": "x"}}]
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("halt_condition_id_collision", report.rules_fired)

    def test_id_collision_with_campaign_checkpoint_fails(self):
        # R1 NB-2: collision vs a CAMPAIGN-tier checkpoint kind (campaign.KNOWN_CHECKPOINTS),
        # not just the 9 MANDATORY ones — proves the lazy campaign import feeds the guard.
        c = self._base()
        c["autonomy"]["halt_conditions"] = [
            {"id": "milestone_merge",
             "when": {"metric": "milestone_id", "op": "==", "value": "x"}}]
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("halt_condition_id_collision", report.rules_fired)

    def test_id_collision_with_new_kind_fails(self):
        # non-vacuous BECAUSE the id regex allows underscores (R0 N-2).
        c = self._base()
        c["autonomy"]["halt_conditions"] = [
            {"id": "halt_condition_met",
             "when": {"metric": "milestone_id", "op": "==", "value": "x"}}]
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("halt_condition_id_collision", report.rules_fired)

    def test_id_override_substring_fails(self):
        c = self._base()
        c["autonomy"]["halt_conditions"] = [
            {"id": "bypass-gate",
             "when": {"metric": "milestone_id", "op": "==", "value": "x"}}]
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("halt_condition_id_override", report.rules_fired)

    def test_duplicate_id_fails(self):
        c = self._base()
        c["autonomy"]["halt_conditions"] = [
            {"id": "dup", "when": {"metric": "milestone_id", "op": "==", "value": "a"}},
            {"id": "dup", "when": {"metric": "milestone_id", "op": "==", "value": "b"}}]
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("halt_condition_duplicate_id", report.rules_fired)

    def test_unknown_metric_fails(self):
        c = self._base()
        # bypass the schema enum by asserting the semantic layer also catches it:
        # (the schema layer ALSO rejects, defense-in-depth — both fire.)
        c["autonomy"]["halt_conditions"] = [
            {"id": "big", "when": {"metric": "files_changed", "op": "==", "value": "x"}}]
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("halt_condition_unknown_metric", report.rules_fired)

    def test_value_type_mismatch_fails(self):
        c = self._base()
        c["autonomy"]["halt_conditions"] = [
            {"id": "e2e", "when": {"metric": "milestone_functional_acceptance",
                                   "op": "==", "value": "not_a_class"}}]
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("halt_condition_value_type", report.rules_fired)

    def test_in_requires_array_fails(self):
        c = self._base()
        c["autonomy"]["halt_conditions"] = [
            {"id": "hot", "when": {"metric": "milestone_id", "op": "in", "value": "M-auth"}}]
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("halt_condition_value_type", report.rules_fired)


class NotificationsTests(unittest.TestCase):
    """Phase-3 notifications.on_pause (design §4). Default-OFF NO-OP + semantics."""

    def _base(self) -> dict:
        return SemanticUnitTests._base(self)

    def test_absent_is_noop(self):
        report = cv.validate_charter(self._base())
        self.assertTrue(report.ok, msg=report.render())

    def test_valid_notifier_passes(self):
        c = self._base()
        c["notifications"] = {"on_pause": ["/bin/notify.sh", "--json"], "timeout_seconds": 10}
        report = cv.validate_charter(c)
        self.assertTrue(report.ok, msg=report.render())

    def test_inert_block_warns_only(self):
        c = self._base()
        c["notifications"] = {"timeout_seconds": 5}
        report = cv.validate_charter(c)
        self.assertTrue(report.ok, msg=report.render())  # WARN, not ERROR
        self.assertIn("notifications_inert", {i.rule for i in report.warnings})

    def test_blank_argv0_fails(self):
        c = self._base()
        c["notifications"] = {"on_pause": ["   "]}
        report = cv.validate_charter(c)
        self.assertFalse(report.ok)
        self.assertIn("notifications_argv0_blank", report.rules_fired)


class EvalCwdAnchorTests(unittest.TestCase):
    """ADVISORY eval_cmd_cwd_anchor WARN: eval.cmd runs with CWD = the per-gate
    artifacts dir, so a cmd naming neither $EVAL_REPO_DIR nor $EVAL_RUN_DIR is
    very likely assuming a repo CWD it will not get (the tankbattle 2026-07-14
    first-eval-gate failure; Phase-1 canary hit the same trap). Never an ERROR."""

    def _base(self) -> dict:
        return SemanticUnitTests._base(self)

    def test_unanchored_cmd_warns_only(self):
        c = self._base()
        c["tooling"]["eval"]["cmd"] = "npm test && npx playwright test"
        report = cv.validate_charter(c)
        self.assertTrue(report.ok, msg=report.render())  # WARN, not ERROR
        self.assertIn("eval_cmd_cwd_anchor", {i.rule for i in report.warnings})

    def test_repo_dir_anchor_is_silent(self):
        c = self._base()
        c["tooling"]["eval"]["cmd"] = 'cd "$EVAL_REPO_DIR" && npm test'
        report = cv.validate_charter(c)
        self.assertTrue(report.ok, msg=report.render())
        self.assertNotIn("eval_cmd_cwd_anchor", {i.rule for i in report.warnings})

    def test_run_dir_reference_is_silent(self):
        # A cmd inspecting the artifacts dir itself knows the CWD contract.
        c = self._base()
        c["tooling"]["eval"]["cmd"] = 'test -s "$EVAL_RUN_DIR/evidence.json"'
        report = cv.validate_charter(c)
        self.assertTrue(report.ok, msg=report.render())
        self.assertNotIn("eval_cmd_cwd_anchor", {i.rule for i in report.warnings})

    def test_no_eval_cmd_is_noop(self):
        c = self._base()
        del c["tooling"]["eval"]
        report = cv.validate_charter(c)
        self.assertNotIn("eval_cmd_cwd_anchor", {i.rule for i in report.warnings})


class ModelIsHarnessNameTests(unittest.TestCase):
    """A harness name is never a model id: deterministic ERROR at preflight
    (the airplat 2026-07-07 'Cannot use this model: cursor-agent' failure)."""

    @staticmethod
    def _charter_with_dev(model, *, harness="cursor", provider="anysphere"):
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
                "dev": {"agent_kind": harness, "harness": harness,
                        "provider": provider, "model": model},
                "review": {"agent_kind": "codex"},
                "eval": {"cmd": 'cd "$EVAL_REPO_DIR" && true', "timeout_seconds": 1},
                "acceptance": {
                    "enabled": False,
                    "on_fix_required": {
                        "human_confirm_required": True,
                        "route_options": ["deliver_fix_iteration"],
                    },
                },
            },
        }

    def test_cursor_agent_as_model_errors(self):
        report = cv.validate_charter(self._charter_with_dev("cursor-agent"))
        self.assertFalse(report.ok)
        self.assertIn("model_is_harness_name", report.rules_fired)
        # NOT downgraded to the unknown-model WARN — the check fires first.
        self.assertNotIn("model_unknown", report.rules_fired)

    def test_every_harness_name_errors(self):
        for bad in sorted(cv._HARNESS_NAME_MODEL_DENYLIST):
            report = cv.validate_charter(self._charter_with_dev(bad))
            self.assertIn("model_is_harness_name", report.rules_fired, bad)

    def test_check_is_case_insensitive(self):
        report = cv.validate_charter(self._charter_with_dev("Cursor-Agent"))
        self.assertIn("model_is_harness_name", report.rules_fired)

    def test_auto_is_a_real_model_value(self):
        # 'auto' = the cursor CLI's account-default routing id; with the fixed
        # registry (cursor-agent-dev.model: auto) it resolves cleanly.
        report = cv.validate_charter(self._charter_with_dev("auto"))
        self.assertNotIn("model_is_harness_name", report.rules_fired)
        self.assertTrue(report.ok, msg=report.render())

    def test_concrete_model_id_passes_the_check(self):
        report = cv.validate_charter(
            self._charter_with_dev("sonnet-4-thinking"))
        self.assertNotIn("model_is_harness_name", report.rules_fired)

    def test_legacy_charter_untouched(self):
        # v2-gating preserved: a LEGACY role (agent_kind only, no harness/
        # provider/capability_ref) never reaches the capability gate, even with
        # a harness-name model. (charter_validator.py:971 guard.)
        charter = self._charter_with_dev("x")
        charter["tooling"]["dev"] = {"agent_kind": "cursor",
                                     "model": "cursor-agent"}
        report = cv.validate_charter(charter)
        self.assertNotIn("model_is_harness_name", report.rules_fired)

    def test_denylist_covers_registry_and_binaries(self):
        # The static denylist must stay a superset of the live harness registry
        # + known binary names + the cursor adapter's own defense-in-depth set,
        # so a future harness addition cannot silently reopen the hole.
        engine_kit_dir = os.path.dirname(_VALIDATORS_DIR)
        if engine_kit_dir not in sys.path:
            sys.path.insert(0, engine_kit_dir)
        from adapters import ADAPTER_REGISTRY
        from adapters.cursor import _HARNESS_NAME_MODELS
        expected = (set(ADAPTER_REGISTRY) | {"cursor-agent", "claude", "aider"}
                    | set(_HARNESS_NAME_MODELS))
        self.assertTrue(
            expected <= set(cv._HARNESS_NAME_MODEL_DENYLIST),
            msg=f"denylist missing: {expected - set(cv._HARNESS_NAME_MODEL_DENYLIST)}")


class CursorRegistryProfileTests(unittest.TestCase):
    """The shipped registry no longer carries the harness-name placeholder that
    caused the live failure (root-cause fix)."""

    def test_cursor_profile_model_is_auto(self):
        registry = cv.load_model_registry(None)
        rec = registry["models"]["cursor-agent-dev"]
        self.assertEqual(rec["model"], "auto")
        self.assertNotIn(rec["model"], cv._HARNESS_NAME_MODEL_DENYLIST)

    def test_no_registry_profile_uses_a_harness_name_model(self):
        registry = cv.load_model_registry(None)
        for pid, rec in (registry.get("models") or {}).items():
            self.assertNotIn(
                str(rec.get("model", "")).strip().lower(),
                cv._HARNESS_NAME_MODEL_DENYLIST,
                msg=f"registry profile {pid} ships a harness-name model")


if __name__ == "__main__":
    unittest.main(verbosity=2)
