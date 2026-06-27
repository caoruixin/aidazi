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
           "browser-evidence-manifest.schema.json", "acceptance-calibration-record.schema.json",
           "acceptance-execution-plan.schema.json"]

    def test_all_new_schemas_are_valid_metaschema(self):
        for name in self.NEW:
            Draft202012Validator.check_schema(_schema(name))

    def test_executor_contract_sample(self):
        ok = {"executor_kind": "local_http", "app_start_cmd": ["app", "--port", "{port}"],
              "readiness": {"url": "/__health", "timeout_seconds": 5},
              "base_url": "http://127.0.0.1", "allowed_origins": ["http://127.0.0.1"],
              "journeys": [{"id": "j", "steps": [{"action": "navigate", "url": "/"}]}]}
        self.assertEqual(_errs("executor-contract.schema.json", ok), [])
        # Production HTTPS origins are valid when explicit; non-HTTP origins are not.
        production = {**ok, "app_start_cmd": None,
                      "base_url": "https://app.example.com",
                      "allowed_origins": ["https://app.example.com"],
                      "target_environment": "production"}
        production.pop("app_start_cmd")
        self.assertEqual(_errs("executor-contract.schema.json", production), [])
        bad = {**ok, "allowed_origins": ["ftp://example.com"]}
        self.assertTrue(_errs("executor-contract.schema.json", bad))

    def test_acceptance_execution_plan_sample(self):
        ok = {
            "interaction_mode": "hybrid",
            "setup_operations": ["seed-user"],
            "journeys": [{"id": "explore", "steps": [
                {"action": "navigate", "url": "/"},
                {"action": "screenshot"}
            ]}],
            "cleanup_operations": ["delete-user"],
        }
        self.assertEqual(_errs("acceptance-execution-plan.schema.json", ok), [])

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


class CompactProjectionEquivalence(unittest.TestCase):
    """WP-1b (context/token optimization): each agent-loaded compact projection
    (schemas/compact/<name>.compact.schema.json) validates a corpus of probe instances
    IDENTICALLY to its canonical schema — the behavioural proof that stripping the
    annotation keywords changed NO assertion (the agent reads the smaller projection; the
    Python validator keeps loading the verbose canonical)."""

    def _compact(self, name):
        with open(os.path.join(_SCHEMAS, "compact", f"{name}.compact.schema.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def _assert_parity(self, name, instances):
        cv = Draft202012Validator(_schema(f"{name}.schema.json"))
        pv = Draft202012Validator(self._compact(name))
        for inst in instances:
            canon_errs = sorted(e.message for e in cv.iter_errors(inst))
            compact_errs = sorted(e.message for e in pv.iter_errors(inst))
            self.assertEqual(canon_errs, compact_errs,
                             f"{name}: validation diverged for instance {inst!r}")

    def test_review_verdict_parity(self):
        self._assert_parity("review-verdict", [
            {},
            {"decision": "pass", "blocking_count": 0, "summary": "ok", "findings": []},
            {"decision": "not-a-decision", "blocking_count": 0, "summary": "x",
             "findings": []},
            {"blocking_count": -1},
        ])

    def test_acceptance_verdict_parity(self):
        valid_static = {"milestone_verdict": "pass", "suggested_route": "n/a",
                        "cases": [{"case_id": "c", "criterion": "x",
                                   "evidence_path": "eval/runs/s/stdout.txt",
                                   "verdict": "pass", "rationale": "r"}]}
        code_path = json.loads(json.dumps(valid_static))
        code_path["cases"][0]["evidence_path"] = "src/x.py"      # non-eval path → rejected
        fix_required = {"milestone_verdict": "fix_required",
                        "suggested_route": "deliver_fix_iteration",
                        "cases": [{"case_id": "c", "criterion": "x",
                                   "evidence_path": "eval/runs/s/o", "verdict": "fail",
                                   "rationale": "r"}]}
        self._assert_parity("acceptance-verdict",
                            [{}, valid_static, code_path, fix_required])

    def test_mission_charter_parity(self):
        self._assert_parity("mission-charter", [
            {},
            {"schema_version": "1.0"},
            {"mission": {}, "autonomy": {"level": "not-a-level"}},
        ])


_ANNOTATION_KEYS = {"title", "description", "$comment", "examples"}


def _has_annotation(node):
    """True if any Draft-2020-12 annotation keyword survives anywhere in the schema."""
    if isinstance(node, dict):
        if _ANNOTATION_KEYS & node.keys():
            return True
        return any(_has_annotation(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_annotation(x) for x in node)
    return False


class ResearchBriefSchemaSlim(unittest.TestCase):
    """WP-1a (context/token optimization): research-brief.schema.json was slimmed IN
    PLACE — annotation keys (title/description/$comment/examples) stripped, ALL machine
    keys preserved. Agent-only reader: no Python validator, not in any resolver graph →
    audit-neutral. These guards prove the slim is COMPLETE and validation semantics are
    UNCHANGED (the machine constraints still accept a well-formed brief and reject every
    violation), so the technique is safe to reuse on coupled schemas (WP-1b)."""

    SCH = "research-brief.schema.json"

    def _ok(self):
        return {
            "brief_id": "RB-001",
            "input_path": "path_1_customer_ask",
            "customer_signed": True,
            "closure_contract": {
                "positive_shape": "Returns a grounded answer with citations.",
                "anti_pattern": "Fabricates a refund amount not in the policy.",
                "anchor_phrases": ["per your policy", "I can't verify that"],
            },
            "scope_in": ["refund eligibility Q&A"],
            "scope_out": ["payment processing"],
            "anti_goal": "Not building a general chatbot.",
            "kpi": [{"name": "accuracy", "target": ">=0.9", "measurement": "bad-case suite"}],
        }

    def test_metaschema_valid(self):
        Draft202012Validator.check_schema(_schema(self.SCH))

    def test_no_annotation_keys_remain(self):
        self.assertFalse(_has_annotation(_schema(self.SCH)),
                         "slim incomplete: an annotation keyword survived")

    def test_well_formed_brief_validates(self):
        self.assertEqual(_errs(self.SCH, self._ok()), [])

    def test_machine_constraints_still_reject_violations(self):
        # Each case exercises a PRESERVED machine key — proving validation semantics are
        # unchanged after stripping annotations.
        miss = self._ok(); del miss["closure_contract"]                 # required
        self.assertTrue(_errs(self.SCH, miss))
        bad_enum = self._ok(); bad_enum["input_path"] = "path_3_nope"   # enum
        self.assertTrue(_errs(self.SCH, bad_enum))
        extra = self._ok(); extra["unexpected"] = 1                     # additionalProperties (top)
        self.assertTrue(_errs(self.SCH, extra))
        nested = self._ok(); nested["closure_contract"]["x"] = 1        # additionalProperties (nested)
        self.assertTrue(_errs(self.SCH, nested))
        anchors = self._ok(); anchors["closure_contract"]["anchor_phrases"] = []  # minItems
        self.assertTrue(_errs(self.SCH, anchors))
        scope = self._ok(); scope["scope_in"] = []                      # minItems
        self.assertTrue(_errs(self.SCH, scope))
        kpi = self._ok(); kpi["kpi"] = [{"name": "x"}]                  # nested required
        self.assertTrue(_errs(self.SCH, kpi))
        typ = self._ok(); typ["customer_signed"] = "yes"               # type
        self.assertTrue(_errs(self.SCH, typ))


if __name__ == "__main__":
    unittest.main()
