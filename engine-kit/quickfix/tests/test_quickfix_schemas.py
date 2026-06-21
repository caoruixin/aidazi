"""Quick-Fix Commit 1 schema guards.

The request/record/protected-surfaces schemas are valid meta-schemas, the shipped
example + the canonical policy validate, and the fail-closed negatives (bad
human_activation, absolute / `..` / negation / `~` globs, missing scope, malformed
verification, outcome/result mismatch, overlay subtraction) are rejected. There is no
auto-discovery of schemas, so these tests are the wiring contract. Normative source:
process/quickfix-lane.md (spec wins on any conflict).
"""
import json
import os
import unittest

import yaml
from jsonschema import Draft202012Validator

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_THIS, "..", "..", ".."))
_SCHEMAS = os.path.join(_ROOT, "schemas")

REQUEST = "quickfix-request.schema.json"
RECORD = "quickfix-record.schema.json"
SURFACES = "quickfix-protected-surfaces.schema.json"
SURFACES_OVERLAY = "quickfix-protected-surfaces.overlay.schema.json"


def _schema(name):
    with open(os.path.join(_SCHEMAS, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _errs(name, obj):
    return [e.message for e in Draft202012Validator(_schema(name)).iter_errors(obj)]


def _valid_request():
    return {
        "request_id": "fix-x-001",
        "created_by": "rex",
        "human_activation": True,
        "harness": "claude_code",
        "task_summary": "Restore the agreed inclusive bound in paginate().",
        "allowed_globs": ["src/pagination.py", "tests/test_pagination.py"],
        "eligibility_attestation": {
            "non_behavioral_or_restores_agreed_behavior": True,
            "no_new_product_semantics_or_design_choice": True,
            "no_protected_surface": True,
            "targeted_verification_available": True,
            "within_approved_scope": True,
        },
        "targeted_verification": {"argv": ["python", "-m", "pytest", "-q"], "cwd": "."},
    }


class SchemasValid(unittest.TestCase):
    def test_metaschemas(self):
        for n in (REQUEST, RECORD, SURFACES, SURFACES_OVERLAY):
            Draft202012Validator.check_schema(_schema(n))


class RequestSchema(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(_errs(REQUEST, _valid_request()), [])

    def test_shipped_example_validates(self):
        with open(os.path.join(_ROOT, "templates", "quickfix-request.example.json")) as fh:
            ex = json.load(fh)
        self.assertEqual(_errs(REQUEST, ex), [])

    def test_human_activation_must_be_true(self):
        r = _valid_request(); r["human_activation"] = False
        self.assertTrue(_errs(REQUEST, r))
        r2 = _valid_request(); del r2["human_activation"]
        self.assertTrue(_errs(REQUEST, r2))

    def test_allowed_globs_required_nonempty(self):
        r = _valid_request(); r["allowed_globs"] = []
        self.assertTrue(_errs(REQUEST, r))
        r2 = _valid_request(); del r2["allowed_globs"]
        self.assertTrue(_errs(REQUEST, r2))

    def test_allowed_globs_reject_absolute_dotdot_negation_tilde(self):
        for bad in ("/etc/passwd", "../secrets", "src/../x", "!src/x", "~/x", "src/~x"):
            r = _valid_request(); r["allowed_globs"] = [bad]
            self.assertTrue(_errs(REQUEST, r), f"should reject glob {bad!r}")

    def test_allowed_globs_reject_glob_metachar_traversal_bypasses(self):
        # Char classes / brace expansion must not be able to smuggle '..' or '/'.
        for bad in ("src/[.][.]/secret", "{../secret,src/x}", "src/{../secret,ok}",
                    "[/]etc/passwd", "src/[/]x"):
            r = _valid_request(); r["allowed_globs"] = [bad]
            self.assertTrue(_errs(REQUEST, r), f"should reject metachar bypass {bad!r}")

    def test_allowed_globs_accept_globstar(self):
        r = _valid_request(); r["allowed_globs"] = ["src/**", "docs/*.md", "a/b?.py"]
        self.assertEqual(_errs(REQUEST, r), [])

    def test_additional_properties_rejected(self):
        r = _valid_request(); r["surprise"] = 1
        self.assertTrue(_errs(REQUEST, r))

    def test_task_summary_min_length(self):
        r = _valid_request(); r["task_summary"] = "tidy"
        self.assertTrue(_errs(REQUEST, r))

    def test_verification_argv_nonempty(self):
        r = _valid_request(); r["targeted_verification"] = {"argv": []}
        self.assertTrue(_errs(REQUEST, r))

    def test_verification_cwd_reject_escape(self):
        for bad in ("/abs", "../up", "a/../b", "~/x"):
            r = _valid_request(); r["targeted_verification"] = {"argv": ["x"], "cwd": bad}
            self.assertTrue(_errs(REQUEST, r), f"should reject cwd {bad!r}")

    def test_eligibility_attestation_all_true_required(self):
        r = _valid_request(); r["eligibility_attestation"]["no_protected_surface"] = False
        self.assertTrue(_errs(REQUEST, r))
        r2 = _valid_request(); del r2["eligibility_attestation"]["within_approved_scope"]
        self.assertTrue(_errs(REQUEST, r2))


class RecordSchema(unittest.TestCase):
    def _completed(self):
        return {
            "request_id": "fix-x-001", "harness": "claude_code", "outcome": "completed",
            "baseline_sha": "abc1234", "ts": "2026-06-21T00:00:00Z",
            "result": {
                "branch": "quickfix/fix-x-001", "commit_sha": "def5678",
                "stat": " 1 file changed, 1 insertion(+)",
                "verification": {"argv": ["pytest"], "exit_code": 0, "ok": True},
            },
        }

    def _escalated(self):
        return {
            "request_id": "fix-x-001", "harness": "claude_code", "outcome": "escalated",
            "baseline_sha": "abc1234", "ts": "2026-06-21T00:00:00Z",
            "result": {
                "escalation_reason": "protected_surface_hit",
                "handoff_path": "/tmp/quickfix/handoff.md",
                "patch_path": "/tmp/quickfix/work.patch",
                "patch_hash": "deadbeef",
                "diff_summary": " 1 file changed",
            },
        }

    def test_completed_valid(self):
        self.assertEqual(_errs(RECORD, self._completed()), [])

    def test_escalated_valid(self):
        self.assertEqual(_errs(RECORD, self._escalated()), [])

    def test_completed_requires_commit_and_verification(self):
        r = self._completed(); del r["result"]["commit_sha"]
        self.assertTrue(_errs(RECORD, r))
        r2 = self._completed(); del r2["result"]["verification"]
        self.assertTrue(_errs(RECORD, r2))

    def test_completed_branch_must_be_quickfix(self):
        r = self._completed(); r["result"]["branch"] = "main"
        self.assertTrue(_errs(RECORD, r))

    def test_completed_verification_must_be_ok(self):
        r = self._completed(); r["result"]["verification"]["ok"] = False
        r["result"]["verification"]["exit_code"] = 1
        self.assertTrue(_errs(RECORD, r))

    def test_escalated_requires_handoff_patch_hash_and_diff(self):
        for field in ("handoff_path", "patch_path", "patch_hash", "diff_summary"):
            r = self._escalated(); del r["result"][field]
            self.assertTrue(_errs(RECORD, r), f"escalated must require {field}")

    def test_completed_with_escalation_only_result_fails(self):
        r = {
            "request_id": "fix-x-001", "harness": "claude_code", "outcome": "completed",
            "baseline_sha": "abc1234", "ts": "t",
            "result": {"escalation_reason": "x", "handoff_path": "y", "patch_path": "z"},
        }
        self.assertTrue(_errs(RECORD, r))

    def test_bad_baseline_sha_rejected(self):
        r = self._completed(); r["baseline_sha"] = "NOTHEX"
        self.assertTrue(_errs(RECORD, r))


class ProtectedSurfacesSchema(unittest.TestCase):
    def test_baseline_policy_file_validates(self):
        with open(os.path.join(_ROOT, "governance",
                               "quickfix-protected-surfaces.policy.yaml")) as fh:
            pol = yaml.safe_load(fh)
        self.assertEqual(_errs(SURFACES, pol), [])

    def test_baseline_rejects_additional_surfaces(self):
        # A baseline cannot masquerade as an overlay.
        bad = {"version": 1,
               "mandatory_surfaces": [{"id": "x", "globs": ["a/**"], "reason": "r"}],
               "additional_surfaces": [{"id": "y", "globs": ["b/**"], "reason": "r"}]}
        self.assertTrue(_errs(SURFACES, bad))

    def test_overlay_additional_only_validates(self):
        ov = {"version": 1, "additional_surfaces": [
            {"id": "app_secrets", "globs": ["config/app/**"], "reason": "adopter secrets"}]}
        self.assertEqual(_errs(SURFACES_OVERLAY, ov), [])

    def test_overlay_rejects_mandatory_surfaces_fail_closed(self):
        # The KEY fail-closed property: an overlay that tries to redefine baseline
        # surfaces is REJECTED, not silently ignored.
        bad = {"version": 1,
               "mandatory_surfaces": [{"id": "x", "globs": ["a/**"], "reason": "r"}]}
        self.assertTrue(_errs(SURFACES_OVERLAY, bad))
        both = {"version": 1,
                "mandatory_surfaces": [{"id": "x", "globs": ["a/**"], "reason": "r"}],
                "additional_surfaces": [{"id": "y", "globs": ["b/**"], "reason": "r"}]}
        self.assertTrue(_errs(SURFACES_OVERLAY, both))

    def test_overlay_cannot_express_removal(self):
        for bad_key in ("remove_surfaces", "exclude", "override_surfaces"):
            ov = {"version": 1, "additional_surfaces": [
                      {"id": "y", "globs": ["b/**"], "reason": "r"}],
                  bad_key: ["governance"]}
            self.assertTrue(_errs(SURFACES_OVERLAY, ov), f"{bad_key} must be rejected")

    def test_surface_requires_reason(self):
        bad = {"version": 1, "mandatory_surfaces": [{"id": "x", "globs": ["a/**"]}]}
        self.assertTrue(_errs(SURFACES, bad))

    def test_surface_glob_rejects_absolute_dotdot_and_metachar(self):
        for g in ("/abs/**", "../x", "src/[.][.]/x", "{../x,y}", "[/]etc"):
            bad = {"version": 1, "mandatory_surfaces": [{"id": "x", "globs": [g], "reason": "r"}]}
            self.assertTrue(_errs(SURFACES, bad), f"glob {g!r} must be rejected")

    def test_empty_surface_lists_rejected(self):
        self.assertTrue(_errs(SURFACES, {"version": 1, "mandatory_surfaces": []}))
        self.assertTrue(_errs(SURFACES_OVERLAY, {"version": 1, "additional_surfaces": []}))

    def test_version_must_be_1(self):
        self.assertTrue(_errs(SURFACES, {"version": 2,
                        "mandatory_surfaces": [{"id": "x", "globs": ["a/**"], "reason": "r"}]}))


if __name__ == "__main__":
    unittest.main()
