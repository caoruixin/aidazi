"""Opt-in real-browser canary for the production Playwright executor.

Run explicitly:
  AIDAZI_RUN_REAL_PLAYWRIGHT=1 AIDAZI_E2E_PLAYWRIGHT=1 \
    python -m unittest engine-kit.orchestrator.tests.test_playwright_canary -v

The test uses an installed Chrome executable when provided via
``AIDAZI_CHROME_EXECUTABLE`` so CI/dev machines need not download a browser.
"""
import os
import sys
import tempfile
import unittest

_THIS = os.path.dirname(os.path.abspath(__file__))
_ORCH = os.path.dirname(_THIS)
_FIX = os.path.join(_THIS, "fixtures", "e2e_app", "__main__.py")
if _ORCH not in sys.path:
    sys.path.insert(0, _ORCH)

import e2e_executor as ex  # noqa: E402


@unittest.skipUnless(
    os.environ.get("AIDAZI_RUN_REAL_PLAYWRIGHT") == "1",
    "real Playwright canary is opt-in",
)
class RealPlaywrightCanary(unittest.TestCase):
    def test_real_chromium_drives_fixture_and_captures_pixels(self):
        with tempfile.TemporaryDirectory() as d:
            port = self._free_port()
            store = os.path.join(d, "store.json")
            evidence = os.path.join(d, "evidence")
            base = f"http://127.0.0.1:{port}"
            browser = {"headless": True}
            executable = os.environ.get("AIDAZI_CHROME_EXECUTABLE")
            if executable:
                browser["executable_path"] = executable
            contract = {
                "executor_kind": "playwright",
                "target_environment": "local",
                "app_start_cmd": [
                    sys.executable, _FIX, "--port", str(port),
                    "--store", store, "--mode", "normal",
                ],
                "readiness": {"url": "/__health", "timeout_seconds": 15},
                "base_url": base,
                "allowed_origins": [base],
                "shutdown": {"process_owned": True},
                "browser": browser,
                "journeys": [{
                    "id": "real-browser",
                    "steps": [
                        {"action": "navigate", "url": "/",
                         "criterion_id": "C1", "critical": True},
                        {"action": "assert_selector", "selector": "#submit-btn",
                         "criterion_id": "C1", "critical": True},
                        {"action": "fill", "selector": "#name-input",
                         "value": "Rex", "criterion_id": "C2", "critical": True},
                        {"action": "click", "selector": "#submit-btn",
                         "criterion_id": "C2", "critical": True},
                        {"action": "assert_text", "selector": "#result-value",
                         "text": "Saved", "criterion_id": "C2", "critical": True},
                    ],
                }],
            }
            checklist = {"criteria": [
                {"criterion_id": "C1", "criterion": "form loads"},
                {"criterion_id": "C2", "criterion": "submission works"},
            ]}
            result = ex.PlaywrightExecutor().run(
                contract, checklist, evidence, env={})
            self.assertEqual(
                {c.criterion_id: c.executor_status for c in result.criteria},
                {"C1": "pass", "C2": "pass"},
            )
            self.assertTrue(any(
                path.endswith(".png") for path in result.artifacts))

    @staticmethod
    def _free_port():
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        return port


if __name__ == "__main__":
    unittest.main()
