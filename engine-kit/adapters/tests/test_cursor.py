"""Offline, deterministic tests for the ``cursor`` adapter.

NO LLM, NO network, NO real cursor-agent CLI. The real subprocess path is GATED
and is NEVER run here: with the gate unset, ``spawn`` raises ``AdapterError``
before any process is launched; the gate-ordering test sets the gate but points
the adapter at a bogus, non-existent binary so it fails AT exec (OSError),
proving the gate is the only thing that was stopping I/O — without requiring a
real cursor-agent install. Like the other CLI adapters, real I/O goes through
``run_with_monitor`` (adapters/monitor.py), so the no-I/O tests mock THAT symbol.

Run standalone:
    python /Users/.../engine-kit/adapters/tests/test_cursor.py
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
    Adapter,
    AdapterError,
    CursorAdapter,
    ADAPTER_REGISTRY,
    resolve_adapter_class,
)
from adapters.cursor import CursorStreamProbe  # noqa: E402

_ALLOW_ENV = "AIDAZI_ALLOW_REAL_ADAPTER"
_SCHEMA = {"type": "object"}


class CursorGateTests(unittest.TestCase):
    """The real subprocess path is gated; unset gate => AdapterError, zero I/O."""

    def setUp(self):
        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop(_ALLOW_ENV, None)

    def tearDown(self):
        self._env_patch.stop()

    def test_gated_off_raises_adaptererror(self):
        adapter = CursorAdapter()  # allow_subprocess defaults False
        with self.assertRaises(AdapterError) as ctx:
            adapter.spawn("dev", "do the thing", [], _SCHEMA)
        self.assertIn("gated off", str(ctx.exception))
        self.assertEqual(ctx.exception.role, "dev")

    def test_gated_off_attempts_no_subprocess(self):
        adapter = CursorAdapter()
        with mock.patch("adapters.cursor.run_with_monitor") as run_mock:
            with self.assertRaises(AdapterError):
                adapter.spawn("dev", "prompt", ["Read"], _SCHEMA)
        run_mock.assert_not_called()

    def test_provider_is_anysphere(self):
        """Cursor harness vendor is Anysphere; provider defaults to 'anysphere'."""
        self.assertEqual(CursorAdapter().provider, "anysphere")
        self.assertEqual(CursorAdapter().describe()["provider"], "anysphere")
        self.assertEqual(CursorAdapter().describe()["harness"], "cursor")


class CursorRegistryTests(unittest.TestCase):
    def test_registry_resolves_cursor(self):
        self.assertIs(ADAPTER_REGISTRY["cursor"], CursorAdapter)
        self.assertIs(resolve_adapter_class("cursor"), CursorAdapter)
        self.assertTrue(issubclass(CursorAdapter, Adapter))


class CursorGateOrderingTests(unittest.TestCase):
    """Gate set + bogus binary => reaches subprocess, fails AT exec (OSError).

    Proves the gate is the ONLY thing stopping I/O in the gated-off tests: once
    the gate is open the code path proceeds to run_with_monitor → Popen, and the
    ONLY reason it fails now is the (deliberately non-existent) binary.
    """

    def test_gate_open_reaches_exec_and_fails_on_bogus_binary(self):
        bogus = "aidazi-nonexistent-cursor-binary-do-not-install-7f3a9c"
        adapter = CursorAdapter(binary=bogus, allow_subprocess=True)
        self.assertTrue(adapter._enabled())
        with self.assertRaises(AdapterError) as ctx:
            adapter.spawn("dev", "prompt", [], {}, sandbox="workspace_write")
        msg = str(ctx.exception)
        self.assertIn("failed to run", msg)
        self.assertIn(bogus, msg)


class CursorSandboxTests(unittest.TestCase):
    """Sandbox → flag mapping is deterministic and fails closed."""

    def test_unsupported_sandbox_fails_closed(self):
        # Gate OPEN (so the sandbox check, not the gate, is what fires) but never
        # reaches a subprocess because the sandbox is rejected first.
        adapter = CursorAdapter(allow_subprocess=True, binary="bogus")
        with mock.patch("adapters.cursor.run_with_monitor") as run_mock:
            with self.assertRaises(AdapterError) as ctx:
                adapter.spawn("dev", "x", [], _SCHEMA, sandbox="danger")
        self.assertIn("unsupported sandbox", str(ctx.exception))
        run_mock.assert_not_called()  # failed BEFORE any I/O

    def test_workspace_write_maps_to_force(self):
        adapter = CursorAdapter(model="sonnet-4-thinking")
        flags = adapter._sandbox_flags("workspace_write", "dev")
        self.assertIn("--force", flags)
        self.assertIn("--trust", flags)

    def test_read_only_maps_to_ask_mode_no_force(self):
        adapter = CursorAdapter()
        flags = adapter._sandbox_flags("read_only", "review")
        self.assertIn("--mode", flags)
        self.assertIn("ask", flags)
        self.assertNotIn("--force", flags)
        self.assertNotIn("--yolo", flags)  # run-everything never reachable

    def test_yolo_never_reachable(self):
        adapter = CursorAdapter()
        for sb in ("workspace_write", "read_only"):
            self.assertNotIn("--yolo", adapter._sandbox_flags(sb, "dev"))


class CursorArgvTests(unittest.TestCase):
    def test_argv_uses_print_and_stream_json(self):
        adapter = CursorAdapter(model="gpt-5")
        argv = adapter._build_argv(sandbox_flags=["--force"])
        self.assertEqual(argv[0], "cursor-agent")
        self.assertIn("-p", argv)
        self.assertIn("--output-format", argv)
        # stream-json, NOT the former single-envelope json: the incremental
        # stream is what keeps output-liveness fresh + feeds the lease probe.
        self.assertIn("stream-json", argv)
        self.assertNotIn("json", [t for t in argv if t != "stream-json"])
        self.assertIn("--model", argv)
        self.assertIn("gpt-5", argv)
        self.assertIn("--force", argv)

    def test_argv_omits_model_when_unset(self):
        adapter = CursorAdapter()  # no model => account default
        argv = adapter._build_argv(sandbox_flags=[])
        self.assertNotIn("--model", argv)


class CursorEnvelopeParsingTests(unittest.TestCase):
    """The --output-format json envelope + verdict coercion (pure, offline)."""

    def test_result_key_with_fenced_json(self):
        out = '{"result": "```json\\n{\\"verdict\\": \\"pass\\", \\"blocking_count\\": 0}\\n```"}'
        text = CursorAdapter._envelope_result_text(out, "review")
        self.assertEqual(
            CursorAdapter._coerce_json_object(text),
            {"verdict": "pass", "blocking_count": 0},
        )

    def test_bare_string_envelope(self):
        out = '"{\\"verdict\\":\\"pass\\"}"'
        text = CursorAdapter._envelope_result_text(out, "review")
        self.assertEqual(CursorAdapter._coerce_json_object(text), {"verdict": "pass"})

    def test_nested_message_content(self):
        out = '{"message": {"content": "hello artifact"}}'
        self.assertEqual(
            CursorAdapter._envelope_result_text(out, "dev"), "hello artifact")

    def test_non_json_stdout_returned_verbatim(self):
        self.assertEqual(
            CursorAdapter._envelope_result_text("just some prose", "dev"),
            "just some prose",
        )

    def test_unrecognized_object_handed_back_whole(self):
        out = '{"foo": 1, "bar": {"verdict": "fix_required"}}'
        text = CursorAdapter._envelope_result_text(out, "review")
        # coercer still finds the OUTER object — nothing is silently dropped.
        self.assertIsInstance(CursorAdapter._coerce_json_object(text), dict)

    def test_empty_stdout_raises(self):
        with self.assertRaises(AdapterError) as ctx:
            CursorAdapter._envelope_result_text("   ", "dev")
        self.assertIn("empty", str(ctx.exception))

    def test_coerce_returns_none_when_no_object(self):
        self.assertIsNone(CursorAdapter._coerce_json_object("no json here"))


class CursorStreamProbeTests(unittest.TestCase):
    """Probe battery (mirrors test_codex.py CodexStreamProbeTests) — the event
    grammar comes from a REAL captured stream, build 2026.06.24
    (archive/2026-07-09-cursor-kimi-stream-captures/cursor-stream.jsonl)."""

    @staticmethod
    def _init():
        return json.dumps(
            {"type": "system", "subtype": "init", "session_id": "s1"})

    @staticmethod
    def _tool(subtype="started", call_id="tool_1", **extra):
        ev = {"type": "tool_call", "subtype": subtype, "call_id": call_id}
        ev.update(extra)
        return json.dumps(ev)

    @staticmethod
    def _result():
        return json.dumps(
            {"type": "result", "subtype": "success", "result": "DONE"})

    def test_session_lease_covers_initial_latency(self):
        # system/init opens the session lease BEFORE any tool call — the
        # dangerous "waiting on first model token" silent window.
        p = CursorStreamProbe()
        self.assertFalse(p.active())
        p.observe(self._init())
        self.assertTrue(p.active())
        p.observe(self._tool("started", "t1"))
        p.observe(self._tool("completed", "t1"))
        self.assertTrue(p.active())            # session lease still held mid-turn
        p.observe(self._result())
        self.assertFalse(p.active())           # terminal clears all

    def test_tool_open_then_close(self):
        p = CursorStreamProbe()
        p.observe(self._tool("started", "t1"))
        self.assertTrue(p.active())            # silent tool window
        p.observe(self._tool("completed", "t1"))
        self.assertFalse(p.active())

    def test_errored_tool_completed_still_closes(self):
        # Observed in the capture: a failed read arrives as subtype "completed"
        # with an error result — it must still close the lease.
        p = CursorStreamProbe()
        p.observe(self._tool("started", "t1"))
        p.observe(self._tool(
            "completed", "t1",
            tool_call={"readToolCall": {"result": {"error": {
                "errorMessage": "File not found"}}}}))
        self.assertFalse(p.active())

    def test_unknown_terminal_subtype_closes_toward_less_suppression(self):
        # A future "failed"/"canceled" subtype closes the item lease — failing
        # toward LESS silence-kill suppression, never more.
        p = CursorStreamProbe()
        p.observe(self._tool("started", "t1"))
        p.observe(self._tool("canceled", "t1"))
        self.assertFalse(p.active())

    def test_parallel_tools_close_independently(self):
        p = CursorStreamProbe()
        p.observe(self._tool("started", "t1"))
        p.observe(self._tool("started", "t2"))
        p.observe(self._tool("completed", "t1"))
        self.assertTrue(p.active())            # t2 still open
        p.observe(self._tool("completed", "t2"))
        self.assertFalse(p.active())

    def test_terminal_result_clears_all(self):
        p = CursorStreamProbe()
        p.observe(self._init())
        p.observe(self._tool("started", "t1"))
        p.observe(self._tool("started", "t2"))
        self.assertTrue(p.active())
        p.observe(self._result())
        self.assertFalse(p.active())           # session + both items cleared

    def test_unknown_call_id_close_is_noop(self):
        p = CursorStreamProbe()
        p.observe(self._tool("started", "t1"))
        p.observe(self._tool("completed", "SOMETHING_ELSE"))
        self.assertTrue(p.active())            # t1 still open

    def test_started_without_call_id_falls_back_to_session(self):
        p = CursorStreamProbe()
        p.observe(json.dumps({"type": "tool_call", "subtype": "started"}))
        self.assertTrue(p.active())
        p.observe(self._result())
        self.assertFalse(p.active())

    def test_malformed_never_opens(self):
        p = CursorStreamProbe()
        p.observe("not json")
        p.observe("{ broken")
        p.observe("")
        self.assertFalse(p.active())
        p.observe(self._tool("started", "t1"))
        p.observe("garbage")                   # does not close/extend
        self.assertTrue(p.active())

    def test_non_dict_and_non_string_type_ignored(self):
        p = CursorStreamProbe()
        p.observe(json.dumps([1, 2, 3]))
        p.observe(json.dumps({"type": 123}))
        p.observe(json.dumps({"no_type": "x"}))
        self.assertFalse(p.active())

    def test_message_events_do_not_open(self):
        # user/assistant message events are output (they refresh liveness via
        # the stream itself); they are NOT leases.
        p = CursorStreamProbe()
        p.observe(json.dumps({"type": "user", "message": {"role": "user"}}))
        p.observe(json.dumps({"type": "assistant",
                              "message": {"role": "assistant"}}))
        self.assertFalse(p.active())


class CursorProbeWiringTests(unittest.TestCase):
    """The adapter actually passes the probe factory into the monitor."""

    def setUp(self):
        os.environ.pop(_ALLOW_ENV, None)

    def test_spawn_wires_liveness_probe_factory(self):
        a = CursorAdapter(model="auto", allow_subprocess=True)
        captured = {}
        stream = "\n".join([
            json.dumps({"type": "system", "subtype": "init"}),
            json.dumps({"type": "assistant", "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": '{"ok": true}'}]}}),
            json.dumps({"type": "result", "subtype": "success",
                        "result": '{"ok": true}'}),
        ])

        def _fake_run(argv, **kw):
            captured.update(kw)
            return subprocess.CompletedProcess(argv, 0, stdout=stream, stderr="")

        with mock.patch("adapters.cursor.run_with_monitor",
                        side_effect=_fake_run):
            verdict = a.spawn("review", "Review it.", [], _SCHEMA)
        self.assertIs(captured.get("liveness_probe_factory"), CursorStreamProbe)
        self.assertEqual(verdict, {"ok": True})


class CursorStreamExtractionTests(unittest.TestCase):
    """stream-json final-text extraction (pure, offline; capture-shaped)."""

    def _stream(self, *events):
        return "\n".join(json.dumps(e) for e in events)

    def test_result_event_wins(self):
        # Byte-parity with the former json single envelope: the terminal result
        # event's aggregated text is the primary source.
        out = self._stream(
            {"type": "system", "subtype": "init"},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "working on it\n"}]}},
            {"type": "tool_call", "subtype": "started", "call_id": "t1"},
            {"type": "tool_call", "subtype": "completed", "call_id": "t1"},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "DONE"}]}},
            {"type": "result", "subtype": "success",
             "result": "working on it\nDONE"},
        )
        self.assertEqual(
            CursorAdapter._final_result_text_from_stream(out, "dev"),
            "working on it\nDONE")

    def test_truncated_stream_salvages_assistant_texts(self):
        # Killed process ⇒ no terminal result event: concatenated assistant
        # texts still end with the final message (best-effort salvage).
        out = self._stream(
            {"type": "system", "subtype": "init"},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "part one"}]}},
            {"type": "assistant", "message": {"role": "assistant",
                                              "content": "part two"}},
        )
        self.assertEqual(
            CursorAdapter._final_result_text_from_stream(out, "dev"),
            "part one\npart two")

    def test_verdict_coerces_from_result_event(self):
        out = self._stream(
            {"type": "result", "subtype": "success",
             "result": '```json\n{"verdict": "pass", "blocking_count": 0}\n```'})
        text = CursorAdapter._final_result_text_from_stream(out, "review")
        self.assertEqual(CursorAdapter._coerce_json_object(text),
                         {"verdict": "pass", "blocking_count": 0})

    def test_single_envelope_backcompat(self):
        # A CLI-build skew back to json-style single-envelope output still
        # yields the message via the tolerant envelope walk.
        out = '{"result": "hello artifact"}'
        self.assertEqual(
            CursorAdapter._final_result_text_from_stream(out, "dev"),
            "hello artifact")

    def test_prose_stdout_returned_verbatim(self):
        self.assertEqual(
            CursorAdapter._final_result_text_from_stream("just prose", "dev"),
            "just prose")

    def test_events_without_text_return_raw(self):
        out = self._stream(
            {"type": "system", "subtype": "init"},
            {"type": "tool_call", "subtype": "started", "call_id": "t1"},
        )
        self.assertEqual(
            CursorAdapter._final_result_text_from_stream(out, "dev"),
            out.strip())

    def test_empty_stdout_raises(self):
        with self.assertRaises(AdapterError):
            CursorAdapter._final_result_text_from_stream("   ", "dev")


_CAPTURE = os.path.join(
    os.path.dirname(_ENGINE_KIT_DIR), "archive",
    "2026-07-09-cursor-kimi-stream-captures", "cursor-stream.jsonl")


@unittest.skipUnless(
    os.path.exists(_CAPTURE),
    "archived real capture not present (vendored adopter copies of engine-kit "
    "ship without archive/; the framework repo always runs this)")
class CursorRealCapturePinTests(unittest.TestCase):
    """Pin the probe + extraction against the ARCHIVED REAL stream (build
    2026.06.24) — not synthetic shapes — so a grammar drift in the capture
    contract is caught here first."""

    @classmethod
    def setUpClass(cls):
        with open(_CAPTURE, encoding="utf-8") as fh:
            cls.lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        cls.stdout = "\n".join(cls.lines)

    def test_probe_over_real_stream(self):
        p = CursorStreamProbe()
        p.observe(self.lines[0])               # system/init
        self.assertTrue(p.active())            # session lease opened
        for ln in self.lines[1:-1]:
            p.observe(ln)
        self.assertTrue(p.active())            # still leased before terminal
        p.observe(self.lines[-1])              # result event
        self.assertFalse(p.active())           # terminal cleared ALL leases

    def test_extraction_matches_result_event(self):
        events = [json.loads(ln) for ln in self.lines]
        terminal = [e for e in events if e.get("type") == "result"]
        self.assertEqual(len(terminal), 1)
        self.assertEqual(
            CursorAdapter._final_result_text_from_stream(self.stdout, "dev"),
            terminal[0]["result"])

    def test_real_stream_has_the_expected_grammar(self):
        types = {json.loads(ln).get("type") for ln in self.lines}
        # The grammar the probe is built on: init, tool_call pairs, terminal.
        self.assertLessEqual({"system", "tool_call", "assistant", "result"},
                             types)


class CursorModelDenylistTests(unittest.TestCase):
    """Harness-name-as-model fails closed BEFORE any I/O (defense-in-depth;
    the charter validator is the primary preflight gate)."""

    def test_harness_name_model_rejected_before_io(self):
        adapter = CursorAdapter(model="cursor-agent", allow_subprocess=True)
        with mock.patch("adapters.cursor.run_with_monitor") as run_mock:
            with self.assertRaises(AdapterError) as ctx:
                adapter.spawn("dev", "x", [], _SCHEMA)
        msg = str(ctx.exception)
        self.assertIn("HARNESS name", msg)
        self.assertIn("auto", msg)             # the message names the fix
        run_mock.assert_not_called()           # failed BEFORE any I/O

    def test_denylist_is_case_insensitive(self):
        adapter = CursorAdapter(model="Cursor-Agent", allow_subprocess=True)
        with mock.patch("adapters.cursor.run_with_monitor") as run_mock:
            with self.assertRaises(AdapterError):
                adapter.spawn("dev", "x", [], _SCHEMA)
        run_mock.assert_not_called()

    def test_auto_and_real_ids_pass_the_check(self):
        # 'auto' (the CLI's account-default id) and a concrete model id proceed
        # past the model check — proven by failing LATER, at exec, on a bogus
        # binary (the gate-ordering pattern).
        for model in ("auto", "gpt-5.3-codex-low"):
            adapter = CursorAdapter(
                model=model, allow_subprocess=True,
                binary="aidazi-nonexistent-cursor-binary-7f3a9c")
            with self.assertRaises(AdapterError) as ctx:
                adapter.spawn("dev", "x", [], _SCHEMA)
            self.assertIn("failed to run", str(ctx.exception), model)


if __name__ == "__main__":
    unittest.main(verbosity=2)
