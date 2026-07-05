"""§6b — Dev self-smoke autonomy (Phase-4).

The self-smoke absence path must NEVER be a routine human halt:
  * PRIMARY  — external_test_runner SUBSUMES the structural gate (the managed run + provenance is
    the attestation).
  * FALLBACK — the in-process playwright class with a SIGNED e2e_remediation budget gets a bounded
    AUTONOMOUS Dev re-dispatch (author docs/self-smoke.json), contained + budgeted; exhausted /
    out-of-envelope / containment-unavailable → HALT (an authority pause, not routine).
  * OTHERWISE — local_http, or playwright without a signed budget, keeps the §6a structural gate.

Run: cd engine-kit && python3.12 -m pytest orchestrator/tests/test_e2e_self_smoke.py -q
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling"),
           os.path.join(_ENGINE_KIT_DIR, "validators")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
import driver as D  # noqa: E402
from test_e2e_acceptance import _browser_charter, _clock, _acceptance_adapters  # noqa: E402
from test_e2e_remediation import _ext_rem_charter, _drv  # noqa: E402


def _playwright_rem_charter(*, enabled=True, max_rounds=2, level="human_on_the_loop",
                            modules=("app",)):
    """A browser_e2e IN-PROCESS playwright charter with a §1.7-G remediation budget."""
    ch = _ext_rem_charter(enabled=enabled, max_rounds=max_rounds, level=level, modules=modules)
    ch["tooling"]["e2e"] = {
        "executor_kind": "playwright",
        "readiness": {"url": "/", "timeout_seconds": 30},
        "base_url": "http://127.0.0.1", "allowed_origins": ["http://127.0.0.1"],
        "journeys": [{"id": "happy", "steps": [{"action": "navigate", "url": "/"}]}],
    }
    return ch


def _local_http_charter():
    return _browser_charter(level="human_on_the_loop")   # executor_kind: local_http


def _author_smoke(run_dir):
    os.makedirs(os.path.join(run_dir, "docs"), exist_ok=True)
    with open(os.path.join(run_dir, "docs", "self-smoke.json"), "w") as fh:
        json.dump({"command": "npx playwright test", "result": "3 passed"}, fh)


def _types(drv):
    return [e["type"] for e in audit.read_events(drv.audit_ledger)] \
        if os.path.isfile(drv.audit_ledger) else []


# --------------------------------------------------------------------------- #
# PRIMARY — external_test_runner subsumes the self-smoke gate.
# --------------------------------------------------------------------------- #
class SubsumptionTests(unittest.TestCase):
    def test_external_test_runner_subsumes_no_self_smoke_no_halt(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())               # executor_kind external_test_runner
            # NO docs/self-smoke.json authored — must NOT hard-fail (subsumed).
            drv._ensure_dev_self_smoke()
            self.assertIn("dev_self_smoke_subsumed", _types(drv))
            # the structural presence check never ran (no dev_self_smoke_present).
            self.assertNotIn("dev_self_smoke_present", _types(drv))

    def test_external_test_runner_subsumes_even_when_a_stale_file_exists(self):
        with tempfile.TemporaryDirectory() as d:
            _author_smoke(d)   # even a present file is ignored — the managed run is the attestation
            drv = _drv(d, _ext_rem_charter())
            drv._ensure_dev_self_smoke()
            self.assertIn("dev_self_smoke_subsumed", _types(drv))


# --------------------------------------------------------------------------- #
# OTHERWISE — legacy structural gate preserved (byte-identical to §6a).
# --------------------------------------------------------------------------- #
class LegacyStructuralGateTests(unittest.TestCase):
    def test_local_http_missing_self_smoke_still_hard_fails(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _local_http_charter())
            with self.assertRaises(D.GateHardFail):
                drv._ensure_dev_self_smoke()

    def test_local_http_present_self_smoke_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _author_smoke(d)
            drv = _drv(d, _local_http_charter())
            drv._ensure_dev_self_smoke()
            self.assertIn("dev_self_smoke_present", _types(drv))

    def test_playwright_without_signed_budget_hard_fails(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter(enabled=False))
            with self.assertRaises(D.GateHardFail):
                drv._ensure_dev_self_smoke()


# --------------------------------------------------------------------------- #
# FALLBACK — bounded autonomous Dev re-dispatch (playwright + signed budget).
# --------------------------------------------------------------------------- #
class AutonomousRedispatchTests(unittest.TestCase):
    def test_redispatch_authors_self_smoke_then_succeeds(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter(max_rounds=2))

            def _dev():                                    # Dev authors the attestation
                _author_smoke(d)
            with mock.patch.object(drv, "_step_dev", side_effect=_dev), \
                 mock.patch.object(drv, "_step_gate"), \
                 mock.patch.object(drv, "_e2e_observed_diff_available", return_value=True), \
                 mock.patch.object(drv, "_e2e_changed_files", return_value=set()):
                drv._ensure_dev_self_smoke()               # no raise
            self.assertIn("dev_self_smoke_redispatch", _types(drv))
            self.assertIn("dev_self_smoke_present", _types(drv))
            self.assertEqual(drv.state.e2e_selfsmoke_round, 1)   # exactly ONE bounded round

    def test_recovered_redispatch_writes_no_gate_hard_fail(self):
        # the RECOVERABLE path must NOT emit a gate_hard_fail checkpoint/event (that would make
        # autonomous recovery look like a routine human halt).
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter(max_rounds=2))

            def _dev():
                _author_smoke(d)
            with mock.patch.object(drv, "_step_dev", side_effect=_dev), \
                 mock.patch.object(drv, "_step_gate"), \
                 mock.patch.object(drv, "_e2e_observed_diff_available", return_value=True), \
                 mock.patch.object(drv, "_e2e_changed_files", return_value=set()):
                drv._ensure_dev_self_smoke()
            self.assertNotIn("gate_hard_fail", _types(drv))

    def test_budget_exhausted_halts(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter(max_rounds=1))
            with mock.patch.object(drv, "_step_dev"), \
                 mock.patch.object(drv, "_step_gate"), \
                 mock.patch.object(drv, "_e2e_observed_diff_available", return_value=True), \
                 mock.patch.object(drv, "_e2e_changed_files", return_value=set()):
                # Dev never authors the file → round 1 runs, round 2 hits the cap → HALT.
                with self.assertRaises(D.GateHardFail) as cm:
                    drv._ensure_dev_self_smoke()
            self.assertIn("budget exhausted", str(cm.exception))
            self.assertEqual(drv.state.e2e_selfsmoke_round, 1)   # one round ran, then capped

    def test_containment_unavailable_halts_not_redispatch(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter(max_rounds=2))
            # observed-diff gate unavailable ⇒ never dispatch an uncontained fix → HALT.
            with mock.patch.object(drv, "_e2e_observed_diff_available", return_value=False), \
                 mock.patch.object(drv, "_step_dev") as sd:
                with self.assertRaises(D.GateHardFail) as cm:
                    drv._ensure_dev_self_smoke()
                sd.assert_not_called()
            self.assertIn("containment gate is unavailable", str(cm.exception))

    def test_out_of_envelope_diff_halts(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter(max_rounds=2))

            def _dev():
                _author_smoke(d)
            with mock.patch.object(drv, "_step_dev", side_effect=_dev), \
                 mock.patch.object(drv, "_step_gate"), \
                 mock.patch.object(drv, "_e2e_observed_diff_available", return_value=True), \
                 mock.patch.object(drv, "_e2e_changed_files", return_value={"secrets/prod.env"}), \
                 mock.patch.object(drv, "_e2e_selfsmoke_out_of_envelope",
                                   return_value=["secrets/prod.env"]):
                with self.assertRaises(D.GateHardFail) as cm:
                    drv._ensure_dev_self_smoke()
            self.assertIn("out-of-envelope", str(cm.exception))

    def test_diff_gate_unavailable_after_fix_halts(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter(max_rounds=2))

            def _dev():
                _author_smoke(d)
            with mock.patch.object(drv, "_step_dev", side_effect=_dev), \
                 mock.patch.object(drv, "_step_gate"), \
                 mock.patch.object(drv, "_e2e_observed_diff_available", return_value=True), \
                 mock.patch.object(drv, "_e2e_changed_files", return_value=None):
                with self.assertRaises(D.GateHardFail) as cm:
                    drv._ensure_dev_self_smoke()
            self.assertIn("became unavailable", str(cm.exception))

    def test_dev_spec_refine_halt_mid_round_propagates(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter(max_rounds=2))

            def _dev():
                drv.state.state = D.STATE_HALTED       # dev-spec refine paused mid re-dispatch
            with mock.patch.object(drv, "_step_dev", side_effect=_dev), \
                 mock.patch.object(drv, "_step_gate") as sg, \
                 mock.patch.object(drv, "_e2e_observed_diff_available", return_value=True), \
                 mock.patch.object(drv, "_e2e_changed_files", return_value=set()):
                drv._ensure_dev_self_smoke()            # returns (no raise) with STATE_HALTED
                sg.assert_not_called()                  # halted before the gate
            self.assertEqual(drv.state.state, D.STATE_HALTED)


# --------------------------------------------------------------------------- #
# Containment helpers (real observed-diff whitelist) + RunState round-trip.
# --------------------------------------------------------------------------- #
class ContainmentHelperTests(unittest.TestCase):
    def test_selfsmoke_whitelist_allows_only_the_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter(modules=("app",)))
            drv.context_handle = mock.Mock(work_dir=d)
            # run_dir == work_dir ⇒ the artifact is docs/self-smoke.json.
            self.assertEqual(drv._e2e_selfsmoke_rel_path(), "docs/self-smoke.json")
            # in-scope + the artifact ⇒ in-envelope; an out-of-scope path ⇒ flagged.
            changed = {"app/main.py", "docs/self-smoke.json", "other/x.py"}
            self.assertEqual(drv._e2e_selfsmoke_out_of_envelope(changed), ["other/x.py"])

    def test_selfsmoke_rel_path_none_without_work_dir(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _playwright_rem_charter())
            drv.context_handle = None
            self.assertIsNone(drv._e2e_selfsmoke_rel_path())


class RunStateRoundTripTests(unittest.TestCase):
    def test_selfsmoke_round_emitted_only_when_nonzero(self):
        st = D.RunState(loop_id="l", subsprint_id="s")
        self.assertNotIn("e2e_selfsmoke_round", st.to_dict())   # byte-identical for pre-P4
        st.e2e_selfsmoke_round = 2
        self.assertEqual(st.to_dict()["e2e_selfsmoke_round"], 2)
        self.assertEqual(D.RunState.from_dict(st.to_dict()).e2e_selfsmoke_round, 2)


if __name__ == "__main__":
    unittest.main()
