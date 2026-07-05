"""A2: unit tests for the fail-closed execution-provenance gate
(e2e_stage.verify_execution_provenance) — the real-execution class's defense against
hand-authored / stale / dry-run / inconsistent evidence reaching Acceptance.

Pure + offline: no driver, no subprocess. Run:
  cd engine-kit && python3.12 -m pytest orchestrator/tests/test_e2e_provenance.py -q
"""
import copy
import json
import os
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
_REPO = os.path.dirname(_ENGINE_KIT_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import e2e_stage  # noqa: E402

_PROV_SCHEMA = json.load(
    open(os.path.join(_REPO, "schemas", "run-provenance.schema.json")))

_NONCE = "nonce-abcdefgh1234"


_RUN_ID = "r0"
_W0 = "2026-07-05T07:59:00+00:00"   # driver e2e_start_ts (Audit-Spine event authority)
_W1 = "2026-07-05T08:06:00+00:00"   # driver e2e_end_ts


def _good():
    """A fully-valid real-execution evidence set (verify → None). The manifest window
    EQUALS the Audit-Spine event timestamps, and the real wall-clock falls inside it."""
    prov = {
        "executor_kind": "external_test_runner",
        "argv": ["npx", "playwright", "test", "e2e/x.spec.ts", "--reporter=json"],
        "cwd": "/app", "pid": 4321, "exit_code": 0,
        "wall_clock_start": "2026-07-05T08:00:00+00:00",
        "wall_clock_end": "2026-07-05T08:05:00+00:00",
        "duration_seconds": 300.0, "tool_version": "1.0", "host": "ci",
        "spec_sha256": "a" * 64, "invocation_nonce": _NONCE,
    }
    manifest = {
        "run_id": _RUN_ID, "app_start_cmd": "", "base_url": "", "exit_code": 0,
        "artifacts": [{"name": "test-results/a/trace.zip",
                       "path": "test-results/a/trace.zip", "sha256": "b" * 64}],
        "artifact_manifest_hash": "c" * 64,
        "provenance": {"invocation_nonce": _NONCE, "e2e_start_ts": _W0, "e2e_end_ts": _W1},
    }
    events = [
        {"type": "browser_e2e_start", "payload": {
            "invocation_nonce": _NONCE, "run_id": _RUN_ID, "e2e_start_ts": _W0}},
        {"type": "browser_e2e_end", "payload": {
            "invocation_nonce": _NONCE, "run_id": _RUN_ID, "e2e_end_ts": _W1}},
    ]
    checklist = [{"criterion_id": "A", "executor_status": "pass", "mapping_state": "mapped"}]
    return dict(manifest=manifest, provenance=prov, checklist_results=checklist,
                events=events, expected_nonce=_NONCE, expected_run_id=_RUN_ID,
                audit_chain_ok=True, provenance_schema=_PROV_SCHEMA)


def _verify(**over):
    kw = _good()
    kw.update(over)
    return e2e_stage.verify_execution_provenance(**kw)


class VerifyExecutionProvenanceTests(unittest.TestCase):

    def test_happy_path_passes(self):
        self.assertIsNone(_verify())

    def test_short_or_missing_nonce_fails(self):
        self.assertIn("nonce", _verify(expected_nonce="short") or "")
        self.assertIn("nonce", _verify(expected_nonce="") or "")

    def test_missing_or_invalid_provenance_fails(self):
        self.assertIn("run-provenance", _verify(provenance=None) or "")
        bad = _good()["provenance"]; bad.pop("wall_clock_start")
        self.assertIn("schema-invalid", _verify(provenance=bad) or "")

    def test_provenance_nonce_mismatch_fails(self):
        p = _good()["provenance"]; p["invocation_nonce"] = "different-nonce-xxxx"
        self.assertIn("adopter/stale", _verify(provenance=p) or "")

    def test_manifest_nonce_mismatch_fails(self):
        m = copy.deepcopy(_good()["manifest"])
        m["provenance"]["invocation_nonce"] = "different-nonce-xxxx"
        self.assertIn("manifest.provenance", _verify(manifest=m) or "")

    def test_missing_paired_events_fails(self):
        only_start = [{"type": "browser_e2e_start", "payload": {
            "invocation_nonce": _NONCE, "run_id": _RUN_ID, "e2e_start_ts": _W0}}]
        self.assertIn("not anchored", _verify(events=only_start) or "")
        # events carrying a DIFFERENT nonce must not anchor the window
        wrong = [{"type": "browser_e2e_start", "payload": {
                    "invocation_nonce": "other-nonce-xx", "run_id": _RUN_ID,
                    "e2e_start_ts": _W0}},
                 {"type": "browser_e2e_end", "payload": {
                    "invocation_nonce": "other-nonce-xx", "run_id": _RUN_ID,
                    "e2e_end_ts": _W1}}]
        self.assertIn("not anchored", _verify(events=wrong) or "")

    def test_broken_audit_chain_fails(self):
        self.assertIn("chain", _verify(audit_chain_ok=False) or "")

    def test_wall_clock_outside_window_fails(self):
        p = _good()["provenance"]
        p["wall_clock_start"] = "2026-07-05T07:00:00+00:00"  # before e2e_start_ts
        self.assertIn("window", _verify(provenance=p) or "")

    def test_no_concrete_artifact_fails(self):
        # a plain text file under test-results/ (or the checklist) is NOT a real-browser
        # artifact — only trace .zip / screenshot / video count.
        m = copy.deepcopy(_good()["manifest"])
        m["artifacts"] = [{"name": "test-results/log.txt",
                           "path": "test-results/log.txt", "sha256": "d" * 64}]
        self.assertIn("concrete real-browser artifact", _verify(manifest=m) or "")

    def test_run_id_mismatch_fails(self):
        # events carry a different run_id than the driver-owned expected run_id
        self.assertIn("not anchored", _verify(expected_run_id="r-different") or "")

    def test_manifest_window_must_be_spine_anchored(self):
        # manifest defines its OWN window with no matching Audit-Spine event → rejected
        m = copy.deepcopy(_good()["manifest"])
        m["provenance"]["e2e_end_ts"] = "2026-07-05T09:00:00+00:00"
        self.assertIn("not anchored", _verify(manifest=m) or "")

    def test_crash_resume_duplicate_events_ok(self):
        # a resumed re-run appends a SECOND start/end pair (same nonce+run_id); the committed
        # manifest carries the LATEST window — verify must still pass (anchor on the latest,
        # not the first/old event).
        kw = _good()
        old = [
            {"type": "browser_e2e_start", "payload": {
                "invocation_nonce": _NONCE, "run_id": _RUN_ID,
                "e2e_start_ts": "2026-07-05T06:00:00+00:00"}},
            {"type": "browser_e2e_end", "payload": {
                "invocation_nonce": _NONCE, "run_id": _RUN_ID,
                "e2e_end_ts": "2026-07-05T06:30:00+00:00"}},
        ]
        kw["events"] = old + kw["events"]     # old (crashed) pair BEFORE the latest pair
        self.assertIsNone(e2e_stage.verify_execution_provenance(**kw))

    def test_null_exit_code_fails(self):
        # a null exit code is incomplete real-subprocess provenance — fails closed (caught
        # at schema validation now that the schema requires a concrete integer).
        p = _good()["provenance"]; p["exit_code"] = None
        reason = _verify(provenance=p)
        self.assertTrue(reason)
        self.assertIn("integer", reason)

    def test_exit_report_disagreement_fails(self):
        # tests failed but runner exited 0
        cl = [{"executor_status": "fail", "mapping_state": "mapped"}]
        p = _good()["provenance"]; p["exit_code"] = 0
        self.assertIn("disagreement", _verify(checklist_results=cl, provenance=p) or "")
        # nothing failed but runner exited non-zero
        p2 = _good()["provenance"]; p2["exit_code"] = 1
        self.assertIn("disagreement", _verify(provenance=p2) or "")

    def test_unmapped_criterion_fails(self):
        # realistic: no test ran for the criterion, so the runner exits 0 (nothing failed)
        # yet the signed criterion is unmapped → must fail closed.
        cl = [{"executor_status": "skipped", "mapping_state": "unmapped"}]
        self.assertIn("unmapped", _verify(checklist_results=cl) or "")


if __name__ == "__main__":
    unittest.main()
