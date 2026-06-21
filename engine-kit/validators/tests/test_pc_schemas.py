"""P-C schema guards: the four new config/contract schemas load + validate sample data,
and the acceptance-verdict branch-correct conditional keeps static verdicts byte-identical
while requiring the browser-E2E fields. There is no auto-discovery of schemas, so these
tests are the wiring contract — a new/renamed schema field must keep them green."""
import json
import os
import unittest

from jsonschema import Draft202012Validator

_THIS = os.path.dirname(os.path.abspath(__file__))
_SCHEMAS = os.path.abspath(os.path.join(_THIS, "..", "..", "..", "schemas"))


def _schema(name):
    with open(os.path.join(_SCHEMAS, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _errs(name, obj):
    return [e.message for e in Draft202012Validator(_schema(name)).iter_errors(obj)]


class NewSchemasLoad(unittest.TestCase):
    NEW = ["executor-contract.schema.json", "functional-checklist.schema.json",
           "browser-evidence-manifest.schema.json", "acceptance-calibration-record.schema.json"]

    def test_all_new_schemas_are_valid_metaschema(self):
        for name in self.NEW:
            Draft202012Validator.check_schema(_schema(name))

    def test_executor_contract_sample(self):
        ok = {"executor_kind": "local_http", "app_start_cmd": ["app", "--port", "{port}"],
              "readiness": {"url": "/__health", "timeout_seconds": 5},
              "base_url": "http://127.0.0.1", "allowed_origins": ["http://127.0.0.1"],
              "journeys": [{"id": "j", "steps": [{"action": "navigate", "url": "/"}]}]}
        self.assertEqual(_errs("executor-contract.schema.json", ok), [])
        # remote origin is rejected (local-only, fail-closed).
        bad = {**ok, "allowed_origins": ["https://example.com"]}
        self.assertTrue(_errs("executor-contract.schema.json", bad))

    def test_functional_checklist_sample(self):
        ok = {"checklist_id": "fc", "criteria": [{"criterion_id": "C1", "criterion": "x"}]}
        self.assertEqual(_errs("functional-checklist.schema.json", ok), [])
        self.assertTrue(_errs("functional-checklist.schema.json", {"checklist_id": "fc", "criteria": []}))

    def test_manifest_sample(self):
        ok = {"run_id": "r1", "app_start_cmd": "app", "base_url": "http://127.0.0.1",
              "exit_code": 0, "artifacts": [{"name": "console.json", "path": "console.json",
              "sha256": "a" * 64}], "artifact_manifest_hash": "b" * 64}
        self.assertEqual(_errs("browser-evidence-manifest.schema.json", ok), [])
        bad = {**ok, "artifact_manifest_hash": "tooshort"}
        self.assertTrue(_errs("browser-evidence-manifest.schema.json", bad))

    def test_calibration_record_sample(self):
        ok = {"record_id": "m3-1", "acceptance_class": "browser_e2e", "role": "acceptance",
              "harness": "claude_code", "provider": "anthropic", "model": "x",
              "status": "uncalibrated"}
        self.assertEqual(_errs("acceptance-calibration-record.schema.json", ok), [])


class AcceptanceVerdictBranches(unittest.TestCase):
    SCH = "acceptance-verdict.schema.json"

    def test_static_verdict_byte_compatible(self):
        v = {"milestone_verdict": "pass", "suggested_route": "n/a",
             "cases": [{"case_id": "c", "criterion": "x",
                        "evidence_path": "eval/runs/s/stdout.txt", "verdict": "pass",
                        "rationale": "r"}]}
        self.assertEqual(_errs(self.SCH, v), [])

    def test_static_code_path_rejected(self):
        v = {"milestone_verdict": "pass", "suggested_route": "n/a",
             "cases": [{"case_id": "c", "criterion": "x", "evidence_path": "src/x.py",
                        "verdict": "pass", "rationale": "r"}]}
        self.assertTrue(_errs(self.SCH, v))

    def test_browser_requires_criterion_id_and_refs(self):
        good = {"milestone_verdict": "pass", "acceptance_class": "browser_e2e",
                "suggested_route": "n/a", "cases": [{"case_id": "c", "criterion_id": "C1",
                "criterion": "x", "verdict": "pass", "rationale": "r",
                "functional_evidence_refs": [{"kind": "manifest",
                "path": ".orchestrator/audit/browser/u/r/manifest.json", "sha256": "a" * 64}]}]}
        self.assertEqual(_errs(self.SCH, good), [])
        # missing refs → rejected
        bad = json.loads(json.dumps(good))
        del bad["cases"][0]["functional_evidence_refs"]
        self.assertTrue(_errs(self.SCH, bad))
        # ref outside the browser evidence dir → rejected
        bad2 = json.loads(json.dumps(good))
        bad2["cases"][0]["functional_evidence_refs"][0]["path"] = "eval/runs/x"
        self.assertTrue(_errs(self.SCH, bad2))

    def test_fix_required_requires_failure_briefs(self):
        v = {"milestone_verdict": "fix_required", "suggested_route": "deliver_fix_iteration",
             "cases": [{"case_id": "c", "criterion": "x",
                        "evidence_path": "eval/runs/s/o", "verdict": "fail", "rationale": "r"}]}
        self.assertTrue(_errs(self.SCH, v))


if __name__ == "__main__":
    unittest.main()
