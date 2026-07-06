"""Offline, deterministic tests for the ``kimi`` adapter (Kimi Code agentic CLI).

NO LLM, NO network in the default suite: the real subprocess path is GATED and is
never run unless ``AIDAZI_ALLOW_REAL_ADAPTER=1``. One OPT-IN integration test
(``KimiWriteCapabilityIntegrationTests``) runs the real ``kimi`` CLI to prove it
writes a file headlessly; it is SKIPPED unless the gate is set.
"""

import json
import os
import subprocess
import sys
import unittest
from unittest import mock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ADAPTERS_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ADAPTERS_DIR)
if _ENGINE_KIT_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_KIT_DIR)

from adapters import (  # noqa: E402
    Adapter, AdapterError, MockAdapter, KimiAdapter,
    ADAPTER_REGISTRY, resolve_adapter_class,
)

_ALLOW_ENV = "AIDAZI_ALLOW_REAL_ADAPTER"
_SCHEMA = {"type": "object"}
_GRANT = [{"id": "gh", "kind": "mcp", "server": "gh-mcp@v1.0.0",
           "scopes": ["read"], "tools": ["search_issues"]}]


class KimiGateTests(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(_ALLOW_ENV, None)

    def tearDown(self):
        self._env.stop()

    def test_gated_off_raises(self):
        with self.assertRaises(AdapterError) as ctx:
            KimiAdapter().spawn("dev", "p", [], {})
        self.assertIn("gated off", str(ctx.exception))
        self.assertEqual(ctx.exception.role, "dev")

    def test_gated_off_no_subprocess(self):
        with mock.patch("adapters.kimi.run_with_monitor") as run_mock:
            with self.assertRaises(AdapterError):
                KimiAdapter().spawn("dev", "p", [], {})
        run_mock.assert_not_called()

    def test_provider_is_moonshot(self):
        self.assertEqual(KimiAdapter().provider, "moonshot")
        self.assertEqual(KimiAdapter().describe()["harness"], "kimi")


class KimiArgvTests(unittest.TestCase):
    def test_argv_is_kimi_prompt_text(self):
        a = KimiAdapter(model="kimi-code/kimi-for-coding", binary="kimi")
        argv = a._build_argv("hello", ["Read"])
        # Prompt rides the ATTACHED long-option form (immune to dash-injection),
        # NOT a separate `-p <prompt>` token.
        self.assertEqual(argv[:4], ["kimi", "--prompt=hello", "--output-format", "text"])
        self.assertNotIn("-p", argv)
        self.assertNotIn("hello", argv)  # only ever attached, never standalone
        self.assertIn("-m", argv)
        self.assertIn("kimi-code/kimi-for-coding", argv)

    def test_binary_defaults_to_install_path_when_not_on_path(self):
        with mock.patch("adapters.kimi.shutil.which", return_value=None):
            a = KimiAdapter()
        self.assertTrue(a.binary.endswith("/.kimi-code/bin/kimi"))

    def test_no_model_omits_flag(self):
        self.assertNotIn("-m", KimiAdapter(binary="kimi")._build_argv("p", []))


class KimiCleanTextTests(unittest.TestCase):
    def test_strips_bullet_prefix(self):
        self.assertEqual(KimiAdapter._clean_text("• done\n\n"), "done")
        self.assertEqual(KimiAdapter._clean_text("• line1\n• line2"), "line1\nline2")
        self.assertEqual(KimiAdapter._clean_text("no bullet"), "no bullet")


class KimiSpawnTests(unittest.TestCase):
    """Artifact vs verdict + the JSON output contract (subprocess mocked)."""

    def _run_with(self, stdout, role, schema, *, capture=None):
        a = KimiAdapter(model="m", allow_subprocess=True)

        def _fake_run(argv, **kw):
            if capture is not None:
                capture["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

        with mock.patch("adapters.kimi.run_with_monitor", side_effect=_fake_run):
            res = a.spawn(role, "p", [], schema)
        # §3/D2 envelope: kimi exposes no structured read events → honest
        # unobservable default; callers assert on the unwrapped result.
        self.assertEqual(res.telemetry.observability, "unobservable")
        self.assertIsNone(res.telemetry.read_paths)
        return res.result

    def test_artifact_spawn_returns_cleaned_text(self):
        out = self._run_with("• wrote src/foo.py and tests; see docs/handoff.md",
                             "dev", {})  # empty schema → artifact
        self.assertEqual(out, {"artifact": "wrote src/foo.py and tests; see docs/handoff.md"})

    def test_verdict_spawn_parses_json(self):
        out = self._run_with('• {"decision": "pass"}', "review", _SCHEMA)
        self.assertEqual(out, {"decision": "pass"})

    def test_verdict_tolerates_fence_and_prose(self):
        out = self._run_with("Here:\n```json\n{\"verdict\":\"A\"}\n```", "deliver", _SCHEMA)
        self.assertEqual(out, {"verdict": "A"})

    def test_verdict_non_json_raises(self):
        with self.assertRaises(AdapterError):
            self._run_with("• no json here", "review", _SCHEMA)

    def test_output_contract_appended_only_for_verdict(self):
        cap = {}
        self._run_with("• {}", "review", _SCHEMA, capture=cap)
        # prompt is the attached --prompt=<...> token (argv[1]).
        self.assertIn("OUTPUT CONTRACT", cap["argv"][1])
        cap2 = {}
        self._run_with("• ok", "dev", {}, capture=cap2)
        self.assertNotIn("OUTPUT CONTRACT", cap2["argv"][1])

    def test_nonzero_exit_raises(self):
        a = KimiAdapter(model="m", allow_subprocess=True)

        def _fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr="boom")

        with mock.patch("adapters.kimi.run_with_monitor", side_effect=_fake_run):
            with self.assertRaises(AdapterError) as ctx:
                a.spawn("dev", "p", [], {})
        self.assertIn("exited 2", str(ctx.exception))

    def test_granted_connector_fails_closed(self):
        a = KimiAdapter(model="m", allow_subprocess=True)
        with mock.patch("adapters.kimi.run_with_monitor") as run_mock:
            with self.assertRaises(AdapterError) as ctx:
                a.spawn("dev", "p", [], {}, connectors=_GRANT)
        run_mock.assert_not_called()
        self.assertIn("Failing closed", str(ctx.exception))


class KimiRegistryTests(unittest.TestCase):
    def test_registry_resolves_kimi(self):
        self.assertIs(ADAPTER_REGISTRY["kimi"], KimiAdapter)
        self.assertIs(resolve_adapter_class("kimi"), KimiAdapter)
        self.assertTrue(issubclass(KimiAdapter, Adapter))

    def test_existing_harnesses_intact(self):
        self.assertIs(resolve_adapter_class("mock"), MockAdapter)


@unittest.skipUnless(os.environ.get(_ALLOW_ENV) == "1",
                     "real kimi write-capability test (opt-in via "
                     "AIDAZI_ALLOW_REAL_ADAPTER=1)")
class KimiWriteCapabilityIntegrationTests(unittest.TestCase):
    def test_workspace_write_session_writes_a_file(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="kimi-integ-")
        subprocess.run(["git", "init", "-q"], cwd=d,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        a = KimiAdapter(model="kimi-code/kimi-for-coding",
                        allow_subprocess=True, cwd=d, timeout_seconds=180)
        a.spawn("dev",
                "Create SENTINEL.txt with exact contents: ok. Then reply done.",
                [], {})  # artifact spawn
        self.assertTrue(os.path.exists(os.path.join(d, "SENTINEL.txt")),
                        "kimi -p session did not write SENTINEL.txt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
