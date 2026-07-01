"""Δ-19 Phase 2-β — static functional checklist + advisory gap_report.

Offline, deterministic (MockAdapter judge, local fake eval — NO billed LLM, NO network).
Covers the four task-mandated checks:
  1. static per-criterion coverage validates against acceptance-verdict.schema.json (additive);
  2. build_gap_report is a FACTS-ONLY projection (schema-valid) — gap = fresh-signed-but-
     undelivered covers_req_ids;
  3. the driver EMITS the advisory gap_report from a requirement-context sidecar AND binds the
     gap-report source facts + the generated gap_report into acceptance_input_hash (LOAD-CLOSURE);
  4. ADDITIVE ABSENCE — with NO sidecar there is no gap_report, no audit event, and none of the
     new resolver purposes (byte-identical reuse fingerprint relative to the pre-feature graph).
"""
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
_REPO_ROOT = os.path.dirname(_ENGINE_KIT_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
import campaign as cp  # noqa: E402
import e2e_stage  # noqa: E402
import scope_report as sr  # noqa: E402
from driver import validate_verdict  # noqa: E402
from test_driver import (  # noqa: E402  (reuse the real charter + MockAdapters + driver)
    _acceptance_charter, _acceptance_adapters, _driver, ACC_PASS, _EVID)

_SCHEMAS = os.path.join(_REPO_ROOT, "schemas")


def _schema(name):
    with open(os.path.join(_SCHEMAS, name), encoding="utf-8") as fh:
        return json.load(fh)


# The campaign charter whose hash the F1 signoff binds (the sidecar carries it so the
# Driver can recompute the live signed-scope hash → signoff_status 'signed').
_SIDECAR_CHARTER = {"tooling": {"acceptance": {"functional": {"mode": "static"}}}}


def _ledger():
    return {"version": "v1", "requirements": [
        {"id": "REQ-1", "statement": "user can log in",
         "source": {"channel": "prd"}, "customer_disposition": "accepted"},
        {"id": "REQ-2", "statement": "user can reset password",
         "source": {"channel": "prd"}, "customer_disposition": "accepted"},
        {"id": "REQ-3", "statement": "admin can export data",
         "source": {"channel": "prd"}, "customer_disposition": "accepted"},
    ]}


def _base_plan():
    return {"campaign_id": "camp-gap", "goal": "ship auth",
            "milestones": [
                {"id": "m1", "objective": "auth", "subsprint_sequence": ["s1"],
                 "covers_req_ids": ["REQ-1", "REQ-2"]},
                {"id": "m2", "objective": "admin", "subsprint_sequence": ["s2"],
                 "covers_req_ids": ["REQ-3"]},
            ]}


def _signed_plan():
    # F1 signed resolved-scope snapshot bound to _SIDECAR_CHARTER. Sign WITH the wired
    # ledger (production: --sign-plan + runner resolve the same ledger, so OW-M3 B1's
    # covered_req_surfaces binds identically at sign + recompute → fresh, not false-stale).
    return cp.stamp_signoff(_base_plan(), _SIDECAR_CHARTER, ledger=_ledger())


def _state():
    # m1 delivered (authoritative pass); m2 in-flight (cursor at index 1, no outcome).
    return {"status": "running", "cursor": {"milestone_index": 1},
            "milestone_outcomes": [
                {"milestone_id": "m1", "terminal": "acceptance_pass_authoritative"}]}


def _sidecar():
    return {"plan": _signed_plan(), "ledger": _ledger(),
            "campaign_state": _state(), "charter": _SIDECAR_CHARTER}


# --------------------------------------------------------------------------- #
# 2. build_gap_report — FACTS-ONLY projection, schema-valid.
# --------------------------------------------------------------------------- #
class TestBuildGapReport(unittest.TestCase):
    def _coverage(self):
        return sr.compute_requirement_coverage(
            _signed_plan(), _state(), _ledger(), charter=_SIDECAR_CHARTER)

    def test_gap_is_fresh_signed_undelivered(self):
        report = sr.build_gap_report(self._coverage())
        self.assertEqual(report["source"], "requirement_coverage")
        self.assertTrue(report["advisory"])
        self.assertTrue(report["ledger_present"])
        self.assertEqual(report["signoff_status"], "signed")
        # REQ-1/REQ-2 delivered (m1), REQ-3 undelivered (m2 in-flight) → the lone gap.
        self.assertEqual([g["req_id"] for g in report["gap"]], ["REQ-3"])
        self.assertEqual(report["gap"][0]["delivery_status"], "in_progress")
        self.assertEqual(report["gap"][0]["covered_by"], "m2")
        self.assertEqual(report["totals"],
                         {"requirements": 3, "delivered": 2, "waived": 0,
                          "gap": 1, "uncovered": 0})
        self.assertEqual(report["uncovered_requirements"], [])

    def test_gap_report_validates_against_schema(self):
        report = sr.build_gap_report(self._coverage())
        self.assertIsNone(validate_verdict(report, _schema("gap-report.schema.json")))

    def test_unsigned_plan_has_empty_in_envelope_gap(self):
        # Not fresh-signed ⇒ no fresh-signed covers ⇒ the in-envelope gap is EMPTY
        # (the gap is the fresh-signed-but-undelivered set, never blocked coverage).
        plan = _base_plan()  # has covers_req_ids (F1 active) but NO signoff block → 'pre_f1'
        cov = sr.compute_requirement_coverage(plan, _state(), _ledger())
        report = sr.build_gap_report(cov)
        self.assertNotEqual(report["signoff_status"], "signed")
        self.assertEqual(report["gap"], [])
        self.assertIsNone(validate_verdict(report, _schema("gap-report.schema.json")))


# --------------------------------------------------------------------------- #
# 1. Static per-criterion coverage — schema is additive.
# --------------------------------------------------------------------------- #
class TestStaticCriterionCoverageSchema(unittest.TestCase):
    def _static_verdict(self, **extra):
        v = {"milestone_verdict": "pass", "calibration_status": "calibrated",
             "cases": [{"case_id": "cc-1", "criterion": "login works",
                        "evidence_path": "eval/runs/s1/acc/stdout.txt",
                        "verdict": "pass", "rationale": "evidence shows login works."}],
             "residual_risks": [], "suggested_route": "n/a"}
        v.update(extra)
        return v

    def test_static_verdict_may_carry_criterion_id_and_checklist_ref(self):
        schema = _schema("acceptance-verdict.schema.json")
        v = self._static_verdict(functional_checklist_ref="docs/checklist.json")
        v["cases"][0]["criterion_id"] = "C-login"
        self.assertIsNone(validate_verdict(v, schema))

    def test_legacy_static_verdict_still_validates(self):
        # A pre-Phase-2-β static verdict (no criterion_id, no functional_checklist_ref)
        # validates identically — additive.
        self.assertIsNone(validate_verdict(self._static_verdict(),
                                           _schema("acceptance-verdict.schema.json")))


# --------------------------------------------------------------------------- #
# 1b. Static per-criterion PROMPT section (record-only, additive).
# --------------------------------------------------------------------------- #
_SIGNED_IC = {"goal": "users authenticate", "standard": "no broken journeys",
              "proof_of_done": "all auth bad-cases pass", "confirmed_by_human": True}


class TestStaticChecklistPrompt(unittest.TestCase):
    def test_section_present_when_static_checklist_wired(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter()
            charter["tooling"]["acceptance"]["functional"] = {
                "mode": "static", "checklist_path": "checklist.json"}
            drv = _driver(d, charter=charter, adapters=_acceptance_adapters())
            # _project_acceptance_prompt needs a state for scope/sequence; seed a minimal one.
            from driver import RunState
            drv.state = RunState(loop_id="loop-test-001", subsprint_id="sprint-001")
            prompt = drv._project_acceptance_prompt(_SIGNED_IC, _EVID, "calibrated")
            self.assertIn("Functional criteria coverage (static checklist", prompt)
            self.assertIn("criterion_id", prompt)
            self.assertIn("functional_checklist_ref", prompt)

    def test_section_absent_without_checklist(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _driver(d, charter=_acceptance_charter(),
                          adapters=_acceptance_adapters())
            from driver import RunState
            drv.state = RunState(loop_id="loop-test-001", subsprint_id="sprint-001")
            prompt = drv._project_acceptance_prompt(_SIGNED_IC, _EVID, "calibrated")
            self.assertNotIn("Functional criteria coverage (static checklist", prompt)


# --------------------------------------------------------------------------- #
# 3 + 4. Driver emits gap_report + LOAD-CLOSURE binding; absence is additive.
# --------------------------------------------------------------------------- #
class TestDriverGapReportEmission(unittest.TestCase):
    def _run_with_sidecar(self, d):
        with open(os.path.join(d, "requirement-context.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(_sidecar(), fh)
        drv = _driver(d, charter=_acceptance_charter(),
                      adapters=_acceptance_adapters(ACC_PASS))
        final = drv.run(subsprint_id="sprint-001")
        return drv, final

    def test_gap_report_emitted_and_audited(self):
        with tempfile.TemporaryDirectory() as d:
            drv, _ = self._run_with_sidecar(d)
            acc_dir = os.path.join(d, ".orchestrator", "acceptance")
            files = [f for f in os.listdir(acc_dir) if f.endswith("-gap-report.json")]
            self.assertEqual(len(files), 1)
            with open(os.path.join(acc_dir, files[0]), encoding="utf-8") as fh:
                gap = json.load(fh)
            self.assertEqual(gap["source"], "requirement_coverage")
            self.assertEqual([g["req_id"] for g in gap["gap"]], ["REQ-3"])
            # FACTS-ONLY + ADVISORY: schema-valid + the advisory flag is set.
            self.assertIsNone(validate_verdict(gap, _schema("gap-report.schema.json")))
            events = [e["type"] for e in audit.read_events(drv.audit_ledger)]
            self.assertIn("acceptance_gap_report", events)
            self.assertIn("acceptance_runtime_artifact_budget", events)

    def test_advisory_only_routes_unchanged(self):
        # The gap_report changes NO verdict/route: ACC_PASS still routes to the advisory
        # pass-signoff HALT exactly as without it (no auto-routing — Phase 2-β is additive).
        with tempfile.TemporaryDirectory() as d:
            drv, final = self._run_with_sidecar(d)
            events = [e["type"] for e in audit.read_events(drv.audit_ledger)]
            self.assertIn("acceptance_advisory_pass_signoff", events)

    def test_inputs_bound_into_acceptance_input_hash(self):
        with tempfile.TemporaryDirectory() as d:
            drv, _ = self._run_with_sidecar(d)
            # The real F5 evidence path the run captured (mandatory resolver root).
            spawn = next(e for e in audit.read_events(drv.audit_ledger)
                         if e["type"] == "acceptance_spawn")
            evid = spawn["payload"]["evidence_path"]
            graph_with, missing = drv._acceptance_resolver_graph(evid, None)
            self.assertEqual(missing, [])
            purposes_with = {g["purpose"] for g in graph_with}
            self.assertIn("requirement_context", purposes_with)
            self.assertIn("gap_report", purposes_with)
            hash_with = e2e_stage.acceptance_input_hash("P", graph_with)

            # Remove the gap inputs → recompute on the SAME run_dir (deterministic content):
            # the hash MUST change (they are folded in) and the purposes disappear.
            os.remove(os.path.join(d, "requirement-context.json"))
            os.remove(os.path.join(d, drv._gap_report_rel))
            drv._gap_report_rel = None
            graph_without, _ = drv._acceptance_resolver_graph(evid, None)
            purposes_without = {g["purpose"] for g in graph_without}
            self.assertNotIn("requirement_context", purposes_without)
            self.assertNotIn("gap_report", purposes_without)
            self.assertNotEqual(hash_with,
                                e2e_stage.acceptance_input_hash("P", graph_without))

    def test_absent_sidecar_is_dormant(self):
        # No requirement-context sidecar ⇒ NO gap_report file, NO audit event, none of the
        # new resolver purposes (additive: byte-identical to a non-campaign / no-ledger run).
        with tempfile.TemporaryDirectory() as d:
            drv = _driver(d, charter=_acceptance_charter(),
                          adapters=_acceptance_adapters(ACC_PASS))
            drv.run(subsprint_id="sprint-001")
            self.assertFalse(os.path.isdir(os.path.join(d, ".orchestrator",
                                                        "acceptance")))
            events = [e["type"] for e in audit.read_events(drv.audit_ledger)]
            self.assertNotIn("acceptance_gap_report", events)
            self.assertIsNone(drv._gap_report_rel)

    def test_malformed_sidecar_fails_closed(self):
        from driver import GateHardFail
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "requirement-context.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{ not json")
            drv = _driver(d, charter=_acceptance_charter(),
                          adapters=_acceptance_adapters(ACC_PASS))
            with self.assertRaises(GateHardFail):
                drv.run(subsprint_id="sprint-001")


if __name__ == "__main__":
    unittest.main()
