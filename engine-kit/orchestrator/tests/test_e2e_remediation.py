"""§1.7-G — autonomous browser_e2e remediation lane (Phase 3).

Covers the DETERMINISTIC facts-only trigger + partition (§5.1), enablement gating (§5/§14),
the signed round budget cap (§5.3), per-round run_id + FULL cache invalidation incl. the A2
nonce (§5.4), in-envelope containment incl. the observed-diff fail-closed escape hatch (§5.2),
and the bounded remediation loop's control flow (success / regression / no-progress /
budget-exhaustion / out-of-envelope-diff HALTs), all fail-closed and never reaching the #9
ship gate autonomously.

The real external_test_runner execution + real-clock provenance PASS is the Phase-5 canary;
here the loop's decision logic is exercised deterministically with a scripted failing-set.

Run: cd engine-kit && python3.12 -m pytest orchestrator/tests/test_e2e_remediation.py -q
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import driver as D  # noqa: E402
import loop_ingress as li  # noqa: E402
from test_e2e_acceptance import (  # noqa: E402
    _browser_charter, _prep, _clock, _acceptance_adapters)


def _ext_rem_charter(*, enabled=True, max_rounds=2, level="human_on_the_loop",
                     modules=("app",), layers=("api",), max_no_progress=None):
    """A browser_e2e external_test_runner charter with a §1.7-G remediation budget +
    an approved_scope module/layer envelope."""
    ch = _browser_charter(level=level)
    ch["tooling"]["e2e"] = {
        "executor_kind": "external_test_runner", "spec_path": "e2e/x.spec.ts",
        "readiness": {"url": "/", "timeout_seconds": 30},
        "base_url": "http://localhost:4173", "allowed_origins": ["http://localhost:4173"],
    }
    ch["autonomy"]["approved_scope"]["modules_in_scope"] = list(modules)
    ch["autonomy"]["approved_scope"]["layers_allowed"] = list(layers)
    if enabled or max_rounds is not None:
        er = {"enabled": enabled}
        if max_rounds is not None:
            er["max_rounds"] = max_rounds
        if max_no_progress is not None:
            er["max_no_progress_rounds"] = max_no_progress
        ch["autonomy"]["e2e_remediation"] = er
    return ch


def _drv(run_dir, charter):
    drv = D.Driver(charter, run_dir, _acceptance_adapters(),
                   loop_id="loop-g", clock=_clock(), context={})
    drv.state = D.RunState(loop_id=drv.loop_id, subsprint_id="sprint-001")
    return drv


def _write_results(drv, run_id, rows):
    final = drv._e2e_final_dir(run_id)
    os.makedirs(final, exist_ok=True)
    with open(os.path.join(final, "checklist-results.json"), "w") as fh:
        json.dump(rows, fh)


# --------------------------------------------------------------------------- #
# §5.1 — deterministic facts-only trigger + total partition.
# --------------------------------------------------------------------------- #
class TriggerPartitionTests(unittest.TestCase):
    def test_only_mapped_fail_or_error_are_failing(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            rid = drv._e2e_run_id()
            _write_results(drv, rid, [
                {"criterion_id": "C1", "executor_status": "pass"},
                {"criterion_id": "C2", "executor_status": "fail"},
                {"criterion_id": "C3", "executor_status": "error"},
                {"criterion_id": "C4", "executor_status": "skipped"},
                # an 'unmapped' row would never publish (pre-publication HALT) — excluded even
                # if it somehow carried fail:
                {"criterion_id": "C5", "executor_status": "fail",
                 "mapping_state": "unmapped"},
            ])
            # mapped fail|error only; skipped→§3.5, pass→pass, unmapped never here.
            self.assertEqual(drv._e2e_failing_criteria(rid), ["C2", "C3"])

    def test_all_pass_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            rid = drv._e2e_run_id()
            _write_results(drv, rid, [{"criterion_id": "C1", "executor_status": "pass"}])
            self.assertEqual(drv._e2e_failing_criteria(rid), [])


# --------------------------------------------------------------------------- #
# §5/§14 — enablement gating.
# --------------------------------------------------------------------------- #
class EnablementTests(unittest.TestCase):
    def test_enabled_requires_budget_and_hotl(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(_drv(d, _ext_rem_charter())._e2e_remediation_enabled())

    def test_disabled_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            ch = _ext_rem_charter()
            ch["autonomy"].pop("e2e_remediation", None)
            self.assertFalse(_drv(d, ch)._e2e_remediation_enabled())

    def test_disabled_when_off(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(
                _drv(d, _ext_rem_charter(enabled=False))._e2e_remediation_enabled())

    def test_disabled_at_human_in_the_loop(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(
                _drv(d, _ext_rem_charter(level="human_in_the_loop"))
                ._e2e_remediation_enabled())

    def test_disabled_without_max_rounds(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(
                _drv(d, _ext_rem_charter(max_rounds=None))._e2e_remediation_enabled())


# --------------------------------------------------------------------------- #
# §5.3 — signed round budget cap on the DISTINCT counter.
# --------------------------------------------------------------------------- #
class BudgetCapTests(unittest.TestCase):
    def test_over_cap_raises_budget_exceeded(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(max_rounds=2))
            drv.state.e2e_remediation_round = 3
            with self.assertRaises(D.BudgetExceeded) as cm:
                drv._check_budget()
            self.assertIn("e2e_remediation_round", str(cm.exception))

    def test_at_or_under_cap_ok(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(max_rounds=2))
            drv.state.e2e_remediation_round = 2
            drv._check_budget()  # no raise

    def test_absent_budget_never_caps(self):
        with tempfile.TemporaryDirectory() as d:
            ch = _ext_rem_charter()
            ch["autonomy"].pop("e2e_remediation", None)
            drv = _drv(d, ch)
            drv.state.e2e_remediation_round = 99
            drv._check_budget()  # no e2e cap configured ⇒ no raise


# --------------------------------------------------------------------------- #
# §5.4 — per-round run_id + FULL cache invalidation incl. the A2 nonce.
# --------------------------------------------------------------------------- #
class RunIdAndCacheTests(unittest.TestCase):
    def test_round0_runid_byte_identical_to_pre_p3(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            import hashlib
            expect = "r" + hashlib.sha256(
                (drv.loop_id + "\x00" + "sprint-001").encode()).hexdigest()[:16]
            self.assertEqual(drv._e2e_run_id(), expect)

    def test_round_n_runid_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            r0 = drv._e2e_run_id()
            drv._invalidate_e2e_round_cache()
            drv.state.e2e_remediation_round = 1
            r1 = drv._e2e_run_id()
            self.assertNotEqual(r0, r1)
            self.assertTrue(r1.startswith("r"))

    def test_cache_invalidation_clears_all_incl_nonce(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            drv.state.e2e_run_id = "rX"
            drv.state.e2e_evidence_ref = "e"
            drv.state.e2e_manifest_hash = "h"
            drv.state.e2e_invocation_nonce = "nX"
            drv.state.acceptance_evidence_hash = "ah"
            drv.state.acceptance_snapshot = {"x": 1}
            drv.state.last_verdict = {"milestone_verdict": "pass"}
            drv._invalidate_e2e_round_cache()
            for f in ("e2e_run_id", "e2e_evidence_ref", "e2e_manifest_hash",
                      "e2e_invocation_nonce", "acceptance_evidence_hash",
                      "acceptance_snapshot", "last_verdict"):
                self.assertIsNone(getattr(drv.state, f), f)


# --------------------------------------------------------------------------- #
# §5.2 — in-envelope containment + observed-diff fail-closed escape hatch.
# --------------------------------------------------------------------------- #
class ContainmentTests(unittest.TestCase):
    def _briefs(self, **over):
        b = {"criterion_id": "C2", "req_id": "REQ-A", "module": "app", "layer": "api"}
        b.update(over)
        return [b]

    def test_gate_unavailable_when_no_workdir(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())  # no context_handle ⇒ no work dir
            ok, reason = drv._e2e_remediation_containment(self._briefs())
            self.assertFalse(ok)
            self.assertEqual(reason, "observed_diff_gate_unavailable")

    def test_gate_unavailable_when_no_modules(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(modules=()))
            drv._e2e_changed_files = lambda: set()  # a git work dir exists
            ok, reason = drv._e2e_remediation_containment(self._briefs())
            self.assertFalse(ok)
            self.assertEqual(reason, "observed_diff_gate_unavailable")

    def test_in_envelope_passes(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            drv._e2e_changed_files = lambda: set()
            ok, reason = drv._e2e_remediation_containment(self._briefs())
            self.assertTrue(ok, reason)

    def test_missing_req_id_is_uncontainable(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            drv._e2e_changed_files = lambda: set()
            ok, reason = drv._e2e_remediation_containment(self._briefs(req_id=None))
            self.assertFalse(ok)
            self.assertIn("req_id", reason)

    def test_module_out_of_envelope(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            drv._e2e_changed_files = lambda: set()
            ok, reason = drv._e2e_remediation_containment(self._briefs(module="other"))
            self.assertFalse(ok)
            self.assertIn("out of", reason)

    def test_diff_out_of_envelope_detection(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(modules=("app", "svc")))
            self.assertEqual(drv._e2e_diff_out_of_envelope(
                {"app/x.py", "svc/y.ts", "other/z.py"}), ["other/z.py"])
            self.assertEqual(drv._e2e_diff_out_of_envelope({"app/x.py"}), [])


class ChangedFilesGitTests(unittest.TestCase):
    def test_changed_files_reads_working_tree(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(os.path.join(repo, "app"))
            for args in (["init", "-q"], ["config", "user.email", "t@t"],
                         ["config", "user.name", "t"]):
                subprocess.run(["git", "-C", repo, *args], check=True,
                               capture_output=True)
            open(os.path.join(repo, "app", "a.py"), "w").write("x=1\n")
            drv = _drv(d, _ext_rem_charter())
            drv.context_handle = li.ContextHandle(
                work_dir=repo, branch="main", strategy=li.STRATEGY_CURRENT_BRANCH,
                repo_dir=repo, created=False, base_ref=None)
            self.assertEqual(drv._e2e_changed_files(), {"app/a.py"})
            self.assertTrue(drv._e2e_observed_diff_available())


# --------------------------------------------------------------------------- #
# §5.2/§5.3 — the bounded remediation loop control flow.
# --------------------------------------------------------------------------- #
def _script_lane(drv, seq, *, containment=(True, "in_envelope"),
                 changed_post=None):
    """Scripted drive of _run_e2e_remediation_lane. seq[i] = failing list at round i;
    a rerun (_commit_e2e) advances the index. Returns (proceed, dev_calls)."""
    idx = {"i": 0}
    dev = {"n": 0}
    drv._e2e_failing_criteria = lambda run_id: list(seq[min(idx["i"], len(seq) - 1)])

    def _commit():
        idx["i"] = min(idx["i"] + 1, len(seq) - 1)
        return {"artifacts": []}
    drv._commit_e2e = _commit
    drv._step_dev = lambda: dev.__setitem__("n", dev["n"] + 1)
    drv._step_gate = lambda: None
    drv._build_e2e_failure_briefs = lambda f, r, m: [
        {"criterion_id": c, "req_id": "REQ-A", "module": "app"} for c in f]
    drv._e2e_remediation_containment = lambda briefs: containment
    cc = {"n": 0}

    def _changed():
        cc["n"] += 1
        return (changed_post if changed_post is not None else set()) \
            if cc["n"] % 2 == 0 else set()
    drv._e2e_changed_files = _changed
    proceed = drv._run_e2e_remediation_lane({"artifacts": []}, drv._e2e_run_id())
    return proceed, dev["n"]


class LaneControlFlowTests(unittest.TestCase):
    def test_all_pass_proceeds_no_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            proceed, dev = _script_lane(drv, [[]])
            self.assertTrue(proceed)
            self.assertEqual(dev, 0)
            self.assertEqual(drv.state.e2e_remediation_round, 0)
            self.assertEqual(drv.state.failing_criteria_by_round, [])  # no pollution

    def test_disabled_routes_to_human_no_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(enabled=False))
            proceed, dev = _script_lane(drv, [["C2"]])
            self.assertTrue(proceed)  # fall through to §3.5 via Acceptance
            self.assertEqual(dev, 0)
            self.assertEqual(drv.state.failing_criteria_by_round, [])  # no pollution

    def test_success_remediates_then_proceeds(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(max_rounds=3))
            proceed, dev = _script_lane(drv, [["C2", "C3"], ["C2"], []])
            self.assertTrue(proceed)
            self.assertEqual(dev, 2)                       # two fix dispatches
            self.assertEqual(drv.state.e2e_remediation_round, 2)
            self.assertNotEqual(drv.state.state, D.STATE_HALTED)

    def test_regression_halts(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(max_rounds=3))
            proceed, _ = _script_lane(drv, [["C2"], ["C2", "C3"]])
            self.assertFalse(proceed)
            self.assertEqual(drv.state.state, D.STATE_HALTED)

    def test_no_progress_halts(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(max_rounds=3))
            proceed, _ = _script_lane(drv, [["C2"], ["C2"]])
            self.assertFalse(proceed)
            self.assertEqual(drv.state.state, D.STATE_HALTED)

    def test_budget_exhaustion_halts(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(max_rounds=1))
            # progress each round, but the cap is 1 → after 1 dispatch, HALT.
            proceed, dev = _script_lane(drv, [["C2", "C3"], ["C2"], ["C2"]])
            self.assertFalse(proceed)
            self.assertEqual(drv.state.state, D.STATE_HALTED)
            self.assertEqual(dev, 1)

    def test_containment_unavailable_fails_closed_to_human(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            proceed, dev = _script_lane(
                drv, [["C2"]],
                containment=(False, "observed_diff_gate_unavailable"))
            self.assertTrue(proceed)                       # → §3.5 via Acceptance
            self.assertEqual(dev, 0)                       # never dispatched an uncontained fix
            self.assertNotEqual(drv.state.state, D.STATE_HALTED)

    def test_out_of_envelope_containment_halts(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter())
            proceed, dev = _script_lane(
                drv, [["C2"]], containment=(False, "criterion 'C2' module 'x' is out of scope"))
            self.assertFalse(proceed)
            self.assertEqual(dev, 0)
            self.assertEqual(drv.state.state, D.STATE_HALTED)

    def test_out_of_envelope_diff_halts_after_fix(self):
        with tempfile.TemporaryDirectory() as d:
            drv = _drv(d, _ext_rem_charter(modules=("app",)))
            # containment passes, but the Dev fix touched an out-of-envelope file.
            proceed, dev = _script_lane(
                drv, [["C2"], []], changed_post={"other/leak.py"})
            self.assertFalse(proceed)
            self.assertEqual(dev, 1)                       # fix ran, then the diff check halted
            self.assertEqual(drv.state.state, D.STATE_HALTED)


if __name__ == "__main__":
    unittest.main()
