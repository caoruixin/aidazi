"""Standalone OFFLINE test for the browser-E2E executor tier (P-C increment I2).

De-risks I2 in ISOLATION — no driver, no campaign, no schemas (those are wired in
later increments). It exercises the REAL ``LocalHttpExecutor`` against the REAL
deterministic fixture app (a genuine ``python -m e2e_app`` subprocess) over stdlib HTTP,
in temp dirs, fully offline. The fixture's five modes let one executor-contract +
functional-checklist pair drive both the happy path and each captured-defect path, so
the test proves the fail-closed CORE:

  - a captured assertion failure (render defect / state mismatch / console error /
    failed critical request) is an OBSERVATION — ``executor_status="fail"`` with full
    evidence, ``exit_code`` STAYS 0 — NOT a raised exception;
  - a true runtime failure (app won't start / readiness timeout) RAISES
    ``ExecutorRuntimeError`` (the driver maps it to gate_hard_fail).

Run: ``cd engine-kit && python3.12 -m pytest orchestrator/tests/test_e2e_executor.py -q``.
"""
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)                       # orchestrator/
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)                  # engine-kit/
_FIXTURES_DIR = os.path.join(_TESTS_DIR, "fixtures")          # …/tests/fixtures
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR, _FIXTURES_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import e2e_executor as ex  # noqa: E402

# The python interpreter that launches the fixture subprocess (this same one).
_PY = sys.executable or "python3"
# Absolute path to the fixture package's __main__ (run by file path so the child does
# not depend on PYTHONPATH; the __main__ shim puts its own dir on sys.path).
_E2E_APP_MAIN = os.path.join(_FIXTURES_DIR, "e2e_app", "__main__.py")


# ---------------------------------------------------------------------------- #
# A deterministic example executor-contract + functional-checklist. These are the
# SHAPES the driver integration (I3/I4) will project. One pair drives every mode;
# the fixture's --mode flips the product behavior under test.
#
#   executor-contract:
#     executor_kind, app_start_cmd, readiness{url,timeout_seconds}, base_url,
#     shutdown{process_owned}, allowed_origins[],
#     journeys[{id, steps[]}]   where each step is
#       {action, ...per-action fields..., criterion_id, critical}
#       actions: navigate|fill|click|assert_text|assert_selector|assert_state|
#                assert_no_console_error|assert_request_ok
#   functional-checklist:
#     {criteria: [{criterion_id, criterion}]}
# ---------------------------------------------------------------------------- #
def make_contract(base_url: str, *, app_start_cmd, mode: str, store: str,
                  readiness_url: str = "/__health", readiness_timeout: float = 10.0,
                  allowed_origins=None) -> dict:
    return {
        "executor_kind": "local_http",
        "app_start_cmd": app_start_cmd,
        "readiness": {"url": readiness_url, "timeout_seconds": readiness_timeout},
        "base_url": base_url,
        "shutdown": {"process_owned": True},
        "allowed_origins": allowed_origins if allowed_origins is not None else [base_url],
        # carried to the child env by the executor (PORT/STORE/MODE):
        "store": store,
        "mode": mode,
        "journeys": [{
            "id": "submit-and-verify",
            "steps": [
                {"action": "navigate", "id": "open-form", "url": "/",
                 "criterion_id": "C1_form_loads", "critical": True},
                {"action": "assert_selector", "selector": "#submit-btn",
                 "criterion_id": "C1_form_loads", "critical": True},
                {"action": "fill", "selector": "#name-input", "value": "Rex",
                 "criterion_id": "C2_submit_persists", "critical": True},
                {"action": "click", "id": "submit", "selector": "#submit-btn",
                 "submit_url": "/submit", "form": {"name": "Rex"},
                 "criterion_id": "C2_submit_persists", "critical": True},
                {"action": "assert_text", "text": "Saved", "selector": "#result-value",
                 "criterion_id": "C3_result_renders", "critical": True},
                {"action": "assert_selector", "selector": "#result-value",
                 "criterion_id": "C3_result_renders", "critical": True},
                {"action": "assert_state", "key": "name", "expected": "Rex",
                 "criterion_id": "C4_backend_state", "critical": True},
                {"action": "navigate", "id": "open-api", "url": "/api/data",
                 "criterion_id": "C5_api_ok", "critical": True},
                {"action": "assert_request_ok", "url": "/api/data",
                 "criterion_id": "C5_api_ok", "critical": True},
                {"action": "assert_no_console_error",
                 "criterion_id": "C6_no_console_error", "critical": True},
            ],
        }],
    }


CHECKLIST = {
    "criteria": [
        {"criterion_id": "C1_form_loads", "criterion": "the form page loads with a submit control"},
        {"criterion_id": "C2_submit_persists", "criterion": "submitting the form lands on the result page"},
        {"criterion_id": "C3_result_renders", "criterion": "the result page shows the saved value"},
        {"criterion_id": "C4_backend_state", "criterion": "the backend persisted the submitted value"},
        {"criterion_id": "C5_api_ok", "criterion": "the result sub-resource returns OK"},
        {"criterion_id": "C6_no_console_error", "criterion": "no console errors during the journey"},
    ],
}


def _status_by_id(result) -> dict:
    return {c.criterion_id: c.executor_status for c in result.criteria}


class _ExecutorCase(unittest.TestCase):
    """Shared harness: run LocalHttpExecutor against the fixture in a given mode, in a
    fresh temp evidence/store dir, and hand back the ExecutorResult + evidence_dir."""

    def _run(self, mode: str, *, app_start_cmd=None, readiness_url="/__health",
             readiness_timeout=10.0, allowed_origins=None, base_port=0,
             contract_fn=make_contract, checklist=CHECKLIST):
        d = tempfile.mkdtemp(prefix=f"e2e_{mode}_")
        self.addCleanup(self._rmtree, d)
        store = os.path.join(d, "store.json")
        evidence_dir = os.path.join(d, "evidence")
        # port 0 → OS-assigned; the fixture binds it and the executor must be told the
        # real port. We bind a probe socket to get a free port deterministically, close
        # it, then hand that port to both the child (via argv) and the contract base_url.
        port = base_port or self._free_port()
        base_url = f"http://127.0.0.1:{port}"
        if app_start_cmd is None:
            app_start_cmd = [_PY, _E2E_APP_MAIN, "--port", str(port),
                             "--store", store, "--mode", mode]
        contract = contract_fn(
            base_url, app_start_cmd=app_start_cmd, mode=mode, store=store,
            readiness_url=readiness_url, readiness_timeout=readiness_timeout,
            allowed_origins=allowed_origins)
        executor = ex.LocalHttpExecutor()
        result = executor.run(contract, checklist, evidence_dir, env={})
        return result, evidence_dir

    @staticmethod
    def _free_port() -> int:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    @staticmethod
    def _rmtree(path):
        import shutil
        shutil.rmtree(path, ignore_errors=True)


class TestNormalMode(_ExecutorCase):
    """(a) normal → all criteria 'pass', exit_code 0, all artifacts written."""

    def test_happy_path_all_pass_and_artifacts_written(self):
        result, evidence_dir = self._run("normal")
        self.assertEqual(result.exit_code, 0)
        statuses = _status_by_id(result)
        self.assertEqual(
            statuses,
            {"C1_form_loads": "pass", "C2_submit_persists": "pass",
             "C3_result_renders": "pass", "C4_backend_state": "pass",
             "C5_api_ok": "pass", "C6_no_console_error": "pass"},
            f"all criteria should observe 'pass' in normal mode; got {statuses}")
        # every criterion carries at least one evidence ref.
        for c in result.criteria:
            self.assertTrue(c.evidence_refs, f"{c.criterion_id} has no evidence_refs")

        # the executor wrote the raw capture artifacts (relpaths) + start/stop logs …
        self.assertEqual(result.app_start_log, "app-start.log")
        self.assertEqual(result.app_stop_log, "app-stop.log")
        arts = set(result.artifacts)
        for required in ("executor-config.json", "console.json", "network.json",
                         "backend-state-refs.json", "app-start.log", "app-stop.log"):
            self.assertIn(required, arts, f"missing artifact {required}")
        self.assertTrue(any(a.startswith("screenshots/") for a in arts),
                        "no screenshot snapshot was written")
        # … and it did NOT write the driver-owned files.
        self.assertNotIn("manifest.json", arts)
        self.assertNotIn("checklist-results.json", arts)

        # every listed artifact actually exists on disk under evidence_dir, and the
        # `artifacts` list is exactly the set the driver will hash (no stray files).
        on_disk = set()
        for root, _dirs, files in os.walk(evidence_dir):
            for fn in files:
                on_disk.add(os.path.relpath(os.path.join(root, fn), evidence_dir))
        self.assertEqual(arts, on_disk,
                         "ExecutorResult.artifacts must match exactly the files on disk")

        # the captures have the expected deterministic content.
        net = json.load(open(os.path.join(evidence_dir, "network.json")))
        self.assertTrue(any(r["url"].startswith("/submit") and r["method"] == "POST"
                            for r in net))
        self.assertTrue(all(r["status"] < 500 for r in net))
        state = json.load(open(os.path.join(evidence_dir, "backend-state-refs.json")))
        self.assertEqual(state.get("name"), "Rex")
        console = json.load(open(os.path.join(evidence_dir, "console.json")))
        self.assertFalse([m for m in console if m.get("level") == "error"])


class TestRenderDefect(_ExecutorCase):
    """(b) render_defect → the result-render criterion 'fail', exit_code 0 (captured)."""

    def test_render_defect_is_captured_not_raised(self):
        result, _ = self._run("render_defect")
        self.assertEqual(result.exit_code, 0, "a captured defect must NOT change exit_code")
        statuses = _status_by_id(result)
        self.assertEqual(statuses["C3_result_renders"], "fail",
                         "the missing #result-value must be observed as 'fail'")
        # the defect is localized: backend state + network + console are still fine.
        self.assertEqual(statuses["C4_backend_state"], "pass")
        self.assertEqual(statuses["C5_api_ok"], "pass")
        self.assertEqual(statuses["C6_no_console_error"], "pass")


class TestStateMismatch(_ExecutorCase):
    """(c) state_mismatch → the assert_state criterion 'fail' (UI says saved, backend not)."""

    def test_state_mismatch_is_captured(self):
        result, evidence_dir = self._run("state_mismatch")
        self.assertEqual(result.exit_code, 0)
        statuses = _status_by_id(result)
        self.assertEqual(statuses["C4_backend_state"], "fail",
                         "backend did not persist → assert_state must 'fail'")
        state = json.load(open(os.path.join(evidence_dir, "backend-state-refs.json")))
        self.assertNotEqual(state.get("name"), "Rex",
                            "the fixture must not have persisted in state_mismatch mode")


class TestConsoleError(_ExecutorCase):
    """(d) console_error → assert_no_console_error 'fail' + console.json has the error."""

    def test_console_error_is_captured(self):
        result, evidence_dir = self._run("console_error")
        self.assertEqual(result.exit_code, 0)
        statuses = _status_by_id(result)
        self.assertEqual(statuses["C6_no_console_error"], "fail")
        console = json.load(open(os.path.join(evidence_dir, "console.json")))
        errors = [m for m in console if m.get("level") == "error"]
        self.assertTrue(errors, "console.json must record the error entry")


class TestNetFail(_ExecutorCase):
    """(e) net_fail → assert_request_ok 'fail' + network.json records the 500."""

    def test_failed_request_is_captured(self):
        result, evidence_dir = self._run("net_fail")
        self.assertEqual(result.exit_code, 0)
        statuses = _status_by_id(result)
        self.assertEqual(statuses["C5_api_ok"], "fail")
        net = json.load(open(os.path.join(evidence_dir, "network.json")))
        bad = [r for r in net if r["url"].startswith("/api/data") and r["status"] >= 500]
        self.assertTrue(bad, "network.json must record the /api/data 500")


class TestRuntimeFailures(_ExecutorCase):
    """(f) bad app_start_cmd → ExecutorRuntimeError; (g) readiness timeout → same."""

    def test_app_wont_start_raises_runtime_error(self):
        # A command that exits non-zero immediately (cannot serve) → app won't start.
        bad_cmd = [_PY, "-c", "import sys; sys.exit(7)"]
        with self.assertRaises(ex.ExecutorRuntimeError):
            self._run("normal", app_start_cmd=bad_cmd, readiness_timeout=3.0)

    def test_readiness_timeout_raises_runtime_error(self):
        # A command that runs but never opens the port → readiness never returns 200.
        # `select` blocks forever with no fds → a live process that is never ready.
        idle_cmd = [_PY, "-c",
                    "import select; select.select([], [], [])"]
        with self.assertRaises(ex.ExecutorRuntimeError):
            self._run("normal", app_start_cmd=idle_cmd, readiness_timeout=1.0)


class TestOriginContainment(_ExecutorCase):
    """A navigate outside allowed_origins is a runtime failure (containment boundary)."""

    def test_navigation_outside_allowed_origins_raises(self):
        # An absolute URL whose origin is not allowed must raise BEFORE any I/O to it.
        executor = ex.LocalHttpExecutor()
        with self.assertRaises(ex.ExecutorRuntimeError):
            executor._enforce_origin("http://evil.example.com/x",
                                     "http://127.0.0.1:9", ["http://127.0.0.1:9"])
        # a relative URL is always in-policy (same origin as base_url).
        executor._enforce_origin("/result", "http://127.0.0.1:9",
                                 ["http://127.0.0.1:9"])  # must not raise


class TestCriterionAggregationMonotonic(_ExecutorCase):
    """Codex impl r2 BLOCKING-1: a criterion record shared by several steps with the same
    criterion_id is folded MONOTONICALLY — a captured non-pass is sticky, so a later
    passing step can NEVER erase it (else a real product defect could silently PASS past
    the §3.2 consistency gate, which keys on executor_status)."""

    def test_record_unit_later_pass_cannot_erase_a_captured_fail(self):
        # The pure aggregation invariant (deterministic, no subprocess).
        r = ex.CriterionResult("C", "crit", "", "", [], "skipped")
        ex.LocalHttpExecutor._record(r, "pass", action="navigate", observed="HTTP 200",
                                     refs=["screenshots/s1.txt"])
        self.assertEqual(r.executor_status, "pass")          # first observation lands
        ex.LocalHttpExecutor._record(r, "fail", action="assert_text",
                                     observed="NOT found", refs=["screenshots/s2.txt"])
        self.assertEqual(r.executor_status, "fail")
        # a LATER passing step for the SAME criterion must NOT downgrade fail → pass.
        ex.LocalHttpExecutor._record(r, "pass", action="assert_selector",
                                     observed="present", refs=["screenshots/s3.txt"])
        self.assertEqual(r.executor_status, "fail",
                         "a later pass silently erased a captured fail (fail-closed break)")
        self.assertEqual(r.observed_result, "NOT found",
                         "the failure's description must survive a later pass")
        self.assertEqual(
            r.evidence_refs,
            ["screenshots/s1.txt", "screenshots/s2.txt", "screenshots/s3.txt"],
            "every step's evidence must merge, including the failing one")
        # error outranks fail; a later fail cannot pull it back down.
        ex.LocalHttpExecutor._record(r, "error", action="x", observed="machinery faulted")
        self.assertEqual(r.executor_status, "error")
        ex.LocalHttpExecutor._record(r, "fail", action="y", observed="defect")
        self.assertEqual(r.executor_status, "error")

    def test_journey_fail_then_pass_same_criterion_stays_fail(self):
        # Integration through the REAL journey runner: one criterion whose steps are
        # navigate(pass) → assert_selector(absent → fail) → assert_selector(present → pass)
        # must end 'fail' (the captured defect cannot be erased by the trailing pass).
        def contract_fn(base_url, *, app_start_cmd, mode, store, readiness_url,
                        readiness_timeout, allowed_origins):
            return {
                "executor_kind": "local_http", "app_start_cmd": app_start_cmd,
                "readiness": {"url": readiness_url, "timeout_seconds": readiness_timeout},
                "base_url": base_url, "shutdown": {"process_owned": True},
                "allowed_origins": allowed_origins or [base_url],
                "store": store, "mode": mode,
                "journeys": [{"id": "agg", "steps": [
                    {"action": "navigate", "id": "open", "url": "/",
                     "criterion_id": "C_agg", "critical": True},
                    {"action": "assert_selector", "selector": "#definitely-not-here",
                     "criterion_id": "C_agg", "critical": True},
                    {"action": "assert_selector", "selector": "#submit-btn",
                     "criterion_id": "C_agg", "critical": True},
                ]}]}
        checklist = {"criteria": [{"criterion_id": "C_agg",
                                   "criterion": "aggregation stickiness"}]}
        result, _ = self._run("normal", contract_fn=contract_fn, checklist=checklist)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            _status_by_id(result)["C_agg"], "fail",
            "a trailing passing assert must NOT erase the captured fail")


class TestFactoryAndGate(unittest.TestCase):
    """make_executor mapping + the PlaywrightExecutor env/import gate."""

    def test_factory_local_http(self):
        self.assertIsInstance(ex.make_executor("local_http"), ex.LocalHttpExecutor)

    def test_factory_unknown_raises_value_error(self):
        with self.assertRaises(ValueError):
            ex.make_executor("no_such_kind")

    def test_playwright_is_gated_unavailable(self):
        # Default offline CI: the gate is OFF → constructing+running raises Unavailable,
        # never touches a browser, never reaches the network.
        old = os.environ.pop("AIDAZI_E2E_PLAYWRIGHT", None)
        try:
            pw = ex.make_executor("playwright")
            self.assertIsInstance(pw, ex.PlaywrightExecutor)
            with self.assertRaises(ex.ExecutorUnavailable):
                pw.run({}, {"criteria": []}, tempfile.mkdtemp(), {})
        finally:
            if old is not None:
                os.environ["AIDAZI_E2E_PLAYWRIGHT"] = old


if __name__ == "__main__":
    unittest.main()
