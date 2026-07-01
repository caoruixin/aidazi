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


class RequirementLedgerSchema(unittest.TestCase):
    """Δ-19 (Phase 2-alpha): the NEW requirement-ledger schema is metaschema-valid and
    its machine constraints accept a well-formed ledger + reject the documented
    violations (Customer-disposition enum, REQ-id pattern, additionalProperties:false,
    NO writable covers[] / stored delivery_status)."""

    SCH = "requirement-ledger.schema.json"

    def test_metaschema_valid(self):
        Draft202012Validator.check_schema(_schema(self.SCH))

    def test_valid_sample(self):
        ok = {"version": "v1", "requirements": [
            {"id": "REQ-001", "statement": "Sign in with email + password.",
             "source": {"channel": "prd", "ref": "prd.md#auth"},
             "customer_disposition": "accepted",
             "history": [{"at": "2026-06-29T00:00:00Z", "disposition": "accepted",
                          "by": "customer"}]},
            {"id": "REQ-002", "statement": "Export CSV.",
             "gap_type": "unmet_existing", "relates_to_req_ids": ["REQ-001"],
             "elaboration": ["brief-007#clause-2"], "supersedes": "REQ-000",
             "source": {"channel": "requirement_point"},
             "customer_disposition": "deferred"}]}
        self.assertEqual(_errs(self.SCH, ok), [])

    def test_empty_ledger_valid(self):
        self.assertEqual(_errs(self.SCH, {"version": "v1", "requirements": []}), [])

    def test_shipped_fixture_validates(self):
        fx = os.path.abspath(os.path.join(
            _THIS, "..", "..", "orchestrator", "tests", "fixtures",
            "requirements-ledger.sample.json"))
        with open(fx, encoding="utf-8") as fh:
            self.assertEqual(_errs(self.SCH, json.load(fh)), [])

    def test_ow_auto_example_template_validates(self):
        # OW-AUTO Phase 2: the seeded onboarding template (default new-adopter artifact)
        # must validate — a broken template would mislead every new adopter.
        tmpl = os.path.abspath(os.path.join(
            _THIS, "..", "..", "..", "templates", "requirements-ledger.example.json"))
        with open(tmpl, encoding="utf-8") as fh:
            self.assertEqual(_errs(self.SCH, json.load(fh)), [])

    def test_machine_constraints_reject_violations(self):
        base = {"version": "v1", "requirements": [
            {"id": "REQ-1", "statement": "x", "source": {"channel": "prd"},
             "customer_disposition": "accepted"}]}
        self.assertEqual(_errs(self.SCH, base), [])
        bad_id = json.loads(json.dumps(base))
        bad_id["requirements"][0]["id"] = "R-1"               # not REQ-patterned
        self.assertTrue(_errs(self.SCH, bad_id))
        bad_disp = json.loads(json.dumps(base))
        bad_disp["requirements"][0]["customer_disposition"] = "in_progress"  # lifecycle, not disposition
        self.assertTrue(_errs(self.SCH, bad_disp))
        bad_channel = json.loads(json.dumps(base))
        bad_channel["requirements"][0]["source"]["channel"] = "telepathy"    # enum
        self.assertTrue(_errs(self.SCH, bad_channel))
        no_disp = json.loads(json.dumps(base))
        del no_disp["requirements"][0]["customer_disposition"]               # required
        self.assertTrue(_errs(self.SCH, no_disp))
        # NO writable coverage / NO stored delivery_status (those are derived, §3.4/§3.5).
        covers = json.loads(json.dumps(base))
        covers["requirements"][0]["covers"] = ["m1"]                         # additionalProperties:false
        self.assertTrue(_errs(self.SCH, covers))
        delivery = json.loads(json.dumps(base))
        delivery["requirements"][0]["delivery_status"] = "delivered"         # additionalProperties:false
        self.assertTrue(_errs(self.SCH, delivery))
        bad_version = json.loads(json.dumps(base))
        bad_version["version"] = "v2"                                        # const v1
        self.assertTrue(_errs(self.SCH, bad_version))

    def test_ow_auto_advisory_fields_optional_and_enumerated(self):
        # OW-AUTO: the advisory authoring signals are additive-optional. A ledger that
        # OMITS them is valid (legacy byte-identical) and one that carries them is valid;
        # out-of-enum values are rejected.
        base = {"version": "v1", "requirements": [
            {"id": "REQ-1", "statement": "x", "source": {"channel": "prd"},
             "customer_disposition": "pending", "surface": "user_facing"}]}
        self.assertEqual(_errs(self.SCH, base), [])                          # omitted ⇒ valid
        with_fields = json.loads(json.dumps(base))
        with_fields["requirements"][0]["surface_status"] = "proposed"
        with_fields["requirements"][0]["surface_confidence"] = "low"
        self.assertEqual(_errs(self.SCH, with_fields), [])                   # present ⇒ valid
        confirmed = json.loads(json.dumps(with_fields))
        confirmed["requirements"][0]["surface_status"] = "confirmed"
        confirmed["requirements"][0]["surface_confidence"] = "high"
        self.assertEqual(_errs(self.SCH, confirmed), [])
        bad_status = json.loads(json.dumps(with_fields))
        bad_status["requirements"][0]["surface_status"] = "accepted"         # not in enum
        self.assertTrue(_errs(self.SCH, bad_status))
        bad_conf = json.loads(json.dumps(with_fields))
        bad_conf["requirements"][0]["surface_confidence"] = "medium"         # not in enum
        self.assertTrue(_errs(self.SCH, bad_conf))


class CampaignPlanSignoffSchema(unittest.TestCase):
    """Δ-19 F1: the campaign-plan `signoff` block is OPTIONAL (pre-F1 plans still
    validate) but, IF signed_by_human:true, the COMPLETE snapshot is required."""

    SCH = "campaign-plan.schema.json"

    def _plan(self, **kw):
        p = {"campaign_id": "c1", "goal": "g",
             "milestones": [{"id": "m1", "objective": "o"}]}
        p.update(kw)
        return p

    def test_pre_f1_plan_still_validates(self):
        self.assertEqual(_errs(self.SCH, self._plan(signed_by_human=True)), [])

    def test_covers_req_ids_optional_and_patterned(self):
        ok = self._plan(milestones=[{"id": "m1", "objective": "o",
                                     "covers_req_ids": ["REQ-001", "REQ-002"]}])
        self.assertEqual(_errs(self.SCH, ok), [])
        bad = self._plan(milestones=[{"id": "m1", "objective": "o",
                                      "covers_req_ids": ["BAD-1"]}])
        self.assertTrue(_errs(self.SCH, bad))
        dup = self._plan(milestones=[{"id": "m1", "objective": "o",
                                      "covers_req_ids": ["REQ-1", "REQ-1"]}])
        self.assertTrue(_errs(self.SCH, dup))  # uniqueItems within the array

    def test_partial_signoff_block_is_fail_closed(self):
        # signed_by_human:true but missing the snapshot fields → rejected (NB3).
        partial = self._plan(signoff={"signed_by_human": True})
        self.assertTrue(_errs(self.SCH, partial))

    def test_complete_signoff_block_validates(self):
        full = self._plan(signoff={
            "signed_by_human": True, "signer": "human", "signed_at": "2026",
            "charter_ref": "ch", "charter_hash": "h",
            "scope_envelope": {"goal": "g", "milestones": [
                {"id": "m1", "objective": "o", "covers_req_ids": [],
                 "subsprint_sequence": [], "depends_on": [],
                 "resolved_functional_acceptance": {"mode": "static", "source": "default"},
                 "acceptance_bar": None}]},
            "signed_scope_hash": "abc"})
        self.assertEqual(_errs(self.SCH, full), [])


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
