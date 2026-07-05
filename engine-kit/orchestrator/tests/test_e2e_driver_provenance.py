"""A2: driver-level wiring tests for the real-execution provenance path — the
framework-owned nonce, the driver-owned in-flight marker location, the dry-run routing
refusal, real-vs-mock detection, and the pre-spawn provenance-gate call.

The full external_test_runner execution + provenance-PASS path (where the runner's real
wall-clock must fall inside the driver window) is proven by the Phase-5 aidazi-owned
canary — a deterministic fake-clock unit test cannot exercise that time coupling. Here we
cover the wiring/guards that ARE deterministically testable.

Run: cd engine-kit && python3.12 -m pytest orchestrator/tests/test_e2e_driver_provenance.py -q
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import driver as D  # noqa: E402
import e2e_stage  # noqa: E402
from adapters import MockAdapter  # noqa: E402
from test_e2e_acceptance import (  # noqa: E402
    _browser_charter, _prep, _clock, _acceptance_adapters)


def _ext_charter():
    ch = _browser_charter()
    ch["tooling"]["e2e"] = {
        "executor_kind": "external_test_runner", "spec_path": "e2e/x.spec.ts",
        "readiness": {"url": "/", "timeout_seconds": 30},
        "base_url": "http://localhost:4173",
        "allowed_origins": ["http://localhost:4173"],
    }
    return ch


def _drv(run_dir, charter, *, context=None, adapters=None):
    drv = D.Driver(charter, run_dir, adapters or _acceptance_adapters(),
                   loop_id="loop-a2", clock=_clock(), context=context or {})
    drv.state = D.RunState(loop_id=drv.loop_id, subsprint_id="sprint-001")
    return drv


class DryRunRoutingRefusalTests(unittest.TestCase):
    """local_http (dry-run) cannot produce a REAL browser_e2e acceptance verdict."""

    def test_real_run_with_local_http_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            drv = _drv(d, _browser_charter(), context={"allow_real": True})
            with self.assertRaises(D.GateHardFail) as cm:
                drv._commit_e2e()
            self.assertIn("dry-run", str(cm.exception))

    def test_mock_run_with_local_http_is_exempt(self):
        # mock acceptance + no allow_real ⇒ NOT a real run ⇒ refusal must not fire
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            drv = _drv(d, _browser_charter())
            self.assertFalse(drv._e2e_requires_real_execution())


class RealExecutionDetectionTests(unittest.TestCase):

    def test_allow_real_flag_forces_real(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _browser_charter(), context={"allow_real": True})
            self.assertTrue(drv._e2e_requires_real_execution())

    def test_all_mock_adapters_is_not_real(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _browser_charter())
            self.assertIsInstance(drv.adapters.get("acceptance"), MockAdapter)
            self.assertFalse(drv._e2e_requires_real_execution())

    def test_non_mock_acceptance_adapter_is_real(self):
        class _Realish:  # a non-Mock adapter stands in for a real acceptance backend
            pass
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _browser_charter(), adapters={"acceptance": _Realish()})
            self.assertTrue(drv._e2e_requires_real_execution())


class FrameworkOwnedNonceAndMarkerTests(unittest.TestCase):

    def test_nonce_is_framework_owned_stable_and_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_charter())
            n1 = drv._e2e_invocation_nonce()
            self.assertTrue(n1.startswith("n") and len(n1) >= 16)
            self.assertEqual(n1, drv._e2e_invocation_nonce())          # stable
            self.assertEqual(n1, drv.state.e2e_invocation_nonce)       # lives in RunState
            # persisted to disk (an adopter evidence dir cannot set this)
            reloaded = D.RunState.from_dict(drv.state.to_dict())
            self.assertEqual(reloaded.e2e_invocation_nonce, n1)

    def test_marker_is_outside_the_hashed_final_dir(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_charter())
            run_id = drv._e2e_run_id()
            marker = os.path.realpath(drv._e2e_marker_path(run_id))
            final = os.path.realpath(drv._e2e_final_dir(run_id))
            # the marker must NOT be under the final evidence dir (else no-strays trips)
            self.assertFalse(marker.startswith(final + os.sep))
            self.assertIn(".e2e-inflight", marker)


class ProvenanceGateWiringTests(unittest.TestCase):
    """The pre-spawn gate delegates to e2e_stage.verify_execution_provenance with the
    FRAMEWORK-OWNED state nonce, and gate_hard_fails on any reason."""

    def test_gate_uses_state_nonce_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_charter())
            drv.state.e2e_invocation_nonce = "n-framework-owned-nonce"
            with mock.patch.object(e2e_stage, "verify_execution_provenance",
                                   return_value="stale/replayed") as vp:
                with self.assertRaises(D.GateHardFail) as cm:
                    drv._verify_execution_provenance("r0", os.path.join(d, "nope"), [])
            self.assertIn("provenance gate", str(cm.exception))
            self.assertEqual(vp.call_args.kwargs["expected_nonce"],
                             "n-framework-owned-nonce")

    def test_gate_passes_when_verifier_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_charter())
            drv.state.e2e_invocation_nonce = "n-framework-owned-nonce"
            with mock.patch.object(e2e_stage, "verify_execution_provenance",
                                   return_value=None):
                drv._verify_execution_provenance("r0", os.path.join(d, "nope"), [])  # no raise

    def test_gate_is_noop_for_non_provenance_kind(self):
        # local_http never triggers the provenance gate (no-op, no verifier call)
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _browser_charter())
            with mock.patch.object(e2e_stage, "verify_execution_provenance") as vp:
                drv._verify_execution_provenance("r0", os.path.join(d, "nope"), [])
            vp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
