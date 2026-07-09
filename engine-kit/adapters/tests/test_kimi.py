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
from adapters.kimi import KimiStreamProbe  # noqa: E402

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
    def test_argv_is_kimi_prompt_stream_json(self):
        a = KimiAdapter(model="kimi-code/kimi-for-coding", binary="kimi")
        argv = a._build_argv("hello", ["Read"])
        # Prompt rides the ATTACHED long-option form (immune to dash-injection),
        # NOT a separate `-p <prompt>` token. stream-json, NOT text: the event
        # stream keeps output-liveness fresh + feeds the lease probe.
        self.assertEqual(argv[:4],
                         ["kimi", "--prompt=hello", "--output-format", "stream-json"])
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
            return a.spawn(role, "p", [], schema)

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


class KimiStreamProbeTests(unittest.TestCase):
    """Probe battery (mirrors the codex/cursor batteries) — the event grammar
    comes from a REAL captured stream, Kimi Code 0.18.0
    (archive/2026-07-09-cursor-kimi-stream-captures/kimi-stream.jsonl)."""

    @staticmethod
    def _tool_call(cid="tool_1"):
        return json.dumps({"role": "assistant", "tool_calls": [
            {"type": "function", "id": cid,
             "function": {"name": "Write", "arguments": "{}"}}]})

    @staticmethod
    def _tool_result(cid="tool_1"):
        return json.dumps({"role": "tool", "tool_call_id": cid, "content": "ok"})

    @staticmethod
    def _meta():
        return json.dumps({"role": "meta", "type": "session.resume_hint",
                           "session_id": "s1", "content": "..."})

    def test_first_event_opens_session_lease(self):
        # No explicit session-start event exists — the FIRST well-formed
        # known-role event opens the session sentinel (one kimi -p process IS
        # one turn), covering silent reasoning between events.
        p = KimiStreamProbe()
        self.assertFalse(p.active())
        p.observe(json.dumps({"role": "assistant", "content": "thinking..."}))
        self.assertTrue(p.active())
        p.observe(self._meta())
        self.assertFalse(p.active())           # terminal trailer clears all

    def test_tool_open_then_close_session_still_held(self):
        p = KimiStreamProbe()
        p.observe(self._tool_call("t1"))
        self.assertTrue(p.active())            # silent tool window
        p.observe(self._tool_result("t1"))
        self.assertTrue(p.active())            # session sentinel still held
        p.observe(self._meta())
        self.assertFalse(p.active())

    def test_parallel_tool_calls_close_independently(self):
        p = KimiStreamProbe()
        p.observe(json.dumps({"role": "assistant", "tool_calls": [
            {"id": "t1", "function": {"name": "Read"}},
            {"id": "t2", "function": {"name": "Read"}}]}))
        p.observe(self._tool_result("t1"))
        p.observe(self._tool_result("t2"))
        p.observe(self._meta())
        self.assertFalse(p.active())

    def test_unknown_tool_result_is_noop(self):
        p = KimiStreamProbe()
        p.observe(self._tool_call("t1"))
        p.observe(self._tool_result("SOMETHING_ELSE"))
        self.assertTrue(p.active())            # t1 (+ session) still open

    def test_unknown_session_meta_variant_clears(self):
        # Any session.* meta clears — failing toward LESS suppression.
        p = KimiStreamProbe()
        p.observe(self._tool_call("t1"))
        p.observe(json.dumps({"role": "meta", "type": "session.closed"}))
        self.assertFalse(p.active())

    def test_non_session_meta_is_noop(self):
        p = KimiStreamProbe()
        p.observe(self._tool_call("t1"))
        p.observe(json.dumps({"role": "meta", "type": "usage.report"}))
        self.assertTrue(p.active())

    def test_malformed_never_opens(self):
        p = KimiStreamProbe()
        p.observe("not json")
        p.observe("{ broken")
        p.observe("")
        p.observe(json.dumps([1, 2]))
        p.observe(json.dumps({"role": 42}))
        p.observe(json.dumps({"role": "wizard"}))  # unknown role
        self.assertFalse(p.active())
        p.observe(self._tool_call("t1"))
        p.observe("garbage")                   # does not close/extend
        self.assertTrue(p.active())

    def test_tool_call_without_id_still_opens_session(self):
        p = KimiStreamProbe()
        p.observe(json.dumps({"role": "assistant", "tool_calls": [
            {"function": {"name": "Write"}}]}))
        self.assertTrue(p.active())            # session sentinel
        p.observe(self._meta())
        self.assertFalse(p.active())


class KimiProbeWiringTests(unittest.TestCase):
    """The adapter actually passes the probe factory into the monitor."""

    def test_spawn_wires_liveness_probe_factory(self):
        a = KimiAdapter(model="m", allow_subprocess=True)
        captured = {}
        stream = "\n".join([
            json.dumps({"role": "assistant", "content": '{"ok": true}'}),
            json.dumps({"role": "meta", "type": "session.resume_hint"}),
        ])

        def _fake_run(argv, **kw):
            captured.update(kw)
            return subprocess.CompletedProcess(argv, 0, stdout=stream, stderr="")

        with mock.patch("adapters.kimi.run_with_monitor", side_effect=_fake_run):
            verdict = a.spawn("review", "p", [], _SCHEMA)
        self.assertIs(captured.get("liveness_probe_factory"), KimiStreamProbe)
        self.assertEqual(verdict, {"ok": True})


class KimiStreamExtractionTests(unittest.TestCase):
    """stream-json final-response extraction (pure, offline; capture-shaped)."""

    def test_last_assistant_content_wins(self):
        out = "\n".join([
            json.dumps({"role": "assistant", "tool_calls": [
                {"id": "t1", "function": {"name": "Write", "arguments": "{}"}}]}),
            json.dumps({"role": "tool", "tool_call_id": "t1",
                        "content": "Wrote 12 bytes"}),
            json.dumps({"role": "assistant", "content": "intermediate note"}),
            json.dumps({"role": "assistant", "content": "DONE"}),
            json.dumps({"role": "meta", "type": "session.resume_hint"}),
        ])
        self.assertEqual(KimiAdapter._final_response_from_stream(out), "DONE")

    def test_content_block_list_tolerated(self):
        out = json.dumps({"role": "assistant", "content": [
            {"type": "text", "text": "part a"}, {"type": "text", "text": "part b"}]})
        self.assertEqual(
            KimiAdapter._final_response_from_stream(out), "part a\npart b")

    def test_tool_events_are_not_a_response(self):
        # tool_calls / tool events carry no response text; with no assistant
        # content the raw stdout falls through the legacy _clean_text path.
        out = json.dumps({"role": "tool", "tool_call_id": "t1", "content": "ok"})
        self.assertEqual(KimiAdapter._final_response_from_stream(out), out)

    def test_text_mode_backcompat_via_clean_text(self):
        # A CLI-build skew back to text-mode output still yields the message.
        self.assertEqual(
            KimiAdapter._final_response_from_stream("• done\n\n"), "done")

    def test_verdict_parses_from_stream(self):
        out = "\n".join([
            json.dumps({"role": "assistant",
                        "content": '{"verdict": "pass", "blocking_count": 0}'}),
            json.dumps({"role": "meta", "type": "session.resume_hint"}),
        ])
        text = KimiAdapter._final_response_from_stream(out)
        self.assertEqual(KimiAdapter._parse_verdict_text(text, "review"),
                         {"verdict": "pass", "blocking_count": 0})


_CAPTURE = os.path.join(
    os.path.dirname(_ENGINE_KIT_DIR), "archive",
    "2026-07-09-cursor-kimi-stream-captures", "kimi-stream.jsonl")


@unittest.skipUnless(
    os.path.exists(_CAPTURE),
    "archived real capture not present (vendored adopter copies of engine-kit "
    "ship without archive/; the framework repo always runs this)")
class KimiRealCapturePinTests(unittest.TestCase):
    """Pin the probe + extraction against the ARCHIVED REAL stream (Kimi Code
    0.18.0) — not synthetic shapes."""

    @classmethod
    def setUpClass(cls):
        with open(_CAPTURE, encoding="utf-8") as fh:
            cls.lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        cls.stdout = "\n".join(cls.lines)

    def test_probe_over_real_stream(self):
        p = KimiStreamProbe()
        p.observe(self.lines[0])               # first event (tool_calls)
        self.assertTrue(p.active())            # session sentinel opened
        for ln in self.lines[1:-1]:
            p.observe(ln)
        self.assertTrue(p.active())            # still leased before trailer
        p.observe(self.lines[-1])              # session.resume_hint meta
        self.assertFalse(p.active())           # trailer cleared ALL leases

    def test_extraction_yields_final_assistant_content(self):
        events = [json.loads(ln) for ln in self.lines]
        finals = [e["content"] for e in events
                  if e.get("role") == "assistant"
                  and isinstance(e.get("content"), str) and e["content"].strip()]
        self.assertTrue(finals)
        self.assertEqual(
            KimiAdapter._final_response_from_stream(self.stdout), finals[-1])

    def test_real_stream_has_the_expected_grammar(self):
        roles = {json.loads(ln).get("role") for ln in self.lines}
        self.assertLessEqual({"assistant", "tool", "meta"}, roles)
        trailer = json.loads(self.lines[-1])
        self.assertEqual(trailer.get("role"), "meta")
        self.assertTrue(str(trailer.get("type", "")).startswith("session."))


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
