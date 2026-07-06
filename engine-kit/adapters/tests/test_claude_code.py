"""Offline, deterministic tests for the ``claude_code`` adapter.

NO LLM, NO network in the default suite: the real subprocess path is GATED and is
never run unless ``AIDAZI_ALLOW_REAL_ADAPTER=1``. The gated-off tests prove zero
I/O; the argv + permission-mode tests are pure; the gate-ordering test points at a
bogus binary so it fails AT exec without a real claude install.

One OPT-IN integration test (``ClaudeWriteCapabilityIntegrationTests``) runs the
REAL ``claude`` CLI in a throwaway temp git repo to prove a ``workspace_write``
session can actually write a file — the regression behind the Dev-step hard-fail
(headless writes were permission-DENIED without ``--permission-mode acceptEdits``).
It is SKIPPED unless ``AIDAZI_ALLOW_REAL_ADAPTER=1``.

Run standalone:
    python /Users/.../engine-kit/adapters/tests/test_claude_code.py
"""

import json
import os
import subprocess
import sys
import tempfile
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
    ClaudeCodeAdapter,
    ADAPTER_REGISTRY,
    resolve_adapter_class,
)
from adapters.claude_code import ToolLeaseProbe  # noqa: E402

_ALLOW_ENV = "AIDAZI_ALLOW_REAL_ADAPTER"
_SCHEMA = {"type": "object"}


def _arg_after(argv, flag):
    for i, tok in enumerate(argv):
        if tok == flag:
            return argv[i + 1]
    raise AssertionError(f"{flag!r} not in {argv}")


class ClaudeGateTests(unittest.TestCase):
    """Gate unset => AdapterError, zero I/O."""

    def setUp(self):
        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop(_ALLOW_ENV, None)

    def tearDown(self):
        self._env_patch.stop()

    def test_gated_off_raises(self):
        with self.assertRaises(AdapterError) as ctx:
            ClaudeCodeAdapter().spawn("dev", "do it", [], _SCHEMA)
        self.assertIn("gated off", str(ctx.exception))
        self.assertEqual(ctx.exception.role, "dev")

    def test_gated_off_no_subprocess(self):
        with mock.patch("adapters.claude_code.run_with_monitor") as run_mock:
            with self.assertRaises(AdapterError):
                ClaudeCodeAdapter().spawn("dev", "p", ["Write"], _SCHEMA)
        run_mock.assert_not_called()

    def test_provider_is_anthropic(self):
        self.assertEqual(ClaudeCodeAdapter().provider, "anthropic")
        self.assertEqual(ClaudeCodeAdapter().describe()["harness"], "claude_code")


class ClaudePermissionModeTests(unittest.TestCase):
    """The sandbox → --permission-mode mapping is deterministic + fails closed."""

    def test_workspace_write_maps_to_acceptEdits(self):
        a = ClaudeCodeAdapter()
        self.assertEqual(a._permission_mode_for("workspace_write", "dev"),
                         "acceptEdits")

    def test_read_only_maps_to_default(self):
        a = ClaudeCodeAdapter()
        self.assertEqual(a._permission_mode_for("read_only", "acceptance"),
                         "default")

    def test_unsupported_sandbox_fails_closed(self):
        a = ClaudeCodeAdapter()
        for bad in ("danger-full-access", "bypassPermissions", "", "yolo"):
            with self.assertRaises(AdapterError) as ctx:
                a._permission_mode_for(bad, "dev")
            self.assertIn("unsupported sandbox", str(ctx.exception))
            self.assertEqual(ctx.exception.role, "dev")

    def test_bypass_not_reachable_from_any_sandbox(self):
        # bypassPermissions must never be produced from a normal sandbox value.
        a = ClaudeCodeAdapter()
        self.assertNotIn("bypassPermissions",
                         a._PERMISSION_MODE_BY_SANDBOX.values())


class ClaudeArgvTests(unittest.TestCase):
    """Pure, no-I/O checks on the assembled argv."""

    def test_argv_shape(self):
        a = ClaudeCodeAdapter(model="claude-sonnet-4-6", reasoning_effort="high")
        argv = a._build_argv(["Read"], permission_mode="acceptEdits")
        self.assertEqual(argv[0], "claude")
        self.assertEqual(argv[1], "-p")
        # The prompt is passed on STDIN, never as an argv token (no dash-injection).
        self.assertNotIn("hello", argv)
        self.assertEqual(_arg_after(argv, "--output-format"), "stream-json")
        self.assertIn("--verbose", argv)
        self.assertEqual(_arg_after(argv, "--model"), "claude-sonnet-4-6")
        self.assertEqual(_arg_after(argv, "--effort"), "high")
        self.assertEqual(_arg_after(argv, "--permission-mode"), "acceptEdits")
        self.assertEqual(_arg_after(argv, "--allowed-tools"), "Read")

    def test_argv_omits_permission_mode_when_none(self):
        a = ClaudeCodeAdapter(model="m")
        self.assertNotIn("--permission-mode", a._build_argv([]))


class ClaudeSpawnSandboxTests(unittest.TestCase):
    """spawn() resolves the permission mode from sandbox + fails closed early."""

    def test_spawn_threads_acceptEdits_into_argv(self):
        a = ClaudeCodeAdapter(model="m", allow_subprocess=True)
        captured = {}

        def _fake_run(argv, **kw):
            captured["argv"] = argv
            captured["kw"] = kw
            raise OSError("stop after capture")

        with mock.patch("adapters.claude_code.run_with_monitor",
                        side_effect=_fake_run):
            with self.assertRaises(AdapterError):
                a.spawn("dev", "p", [], _SCHEMA, sandbox="workspace_write")
        self.assertEqual(_arg_after(captured["argv"], "--permission-mode"),
                         "acceptEdits")
        # The prompt rides on STDIN (subprocess input=), not argv.
        self.assertEqual(captured["kw"].get("input"), "p")
        self.assertNotIn("p", captured["argv"])

    def test_dash_leading_prompt_rides_stdin_not_argv(self):
        """A prompt whose first line starts with ``--`` must NOT reach argv — the
        front-matter / dash-injection regression. It rides on stdin instead."""
        a = ClaudeCodeAdapter(model="m", allow_subprocess=True)
        captured = {}

        def _fake_run(argv, **kw):
            captured["argv"] = argv
            captured["kw"] = kw
            return subprocess.CompletedProcess(
                argv, 0, stdout='{"result": "ok"}', stderr="")

        dash_prompt = "--output-format evil\nrest of the dev prompt"
        with mock.patch("adapters.claude_code.run_with_monitor",
                        side_effect=_fake_run):
            a.spawn("dev", dash_prompt, [], {}, sandbox="workspace_write")
        self.assertEqual(captured["kw"].get("input"), dash_prompt)
        self.assertNotIn(dash_prompt, captured["argv"])
        self.assertNotIn("--output-format evil", captured["argv"])

    def test_spawn_fails_closed_before_subprocess_on_bad_sandbox(self):
        a = ClaudeCodeAdapter(model="m", allow_subprocess=True)  # gate OPEN
        with mock.patch("adapters.claude_code.run_with_monitor") as run_mock:
            with self.assertRaises(AdapterError) as ctx:
                a.spawn("dev", "p", [], _SCHEMA, sandbox="danger-full-access")
        run_mock.assert_not_called()
        self.assertIn("unsupported sandbox", str(ctx.exception))


class ClaudeVerdictParseTests(unittest.TestCase):
    """The --output-format json envelope parser is pure."""

    def test_result_string_is_parsed_as_verdict(self):
        envelope = '{"result": "{\\"decision\\": \\"pass\\"}"}'
        self.assertEqual(
            ClaudeCodeAdapter._extract_verdict(envelope, "review"),
            {"decision": "pass"})

    def test_result_dict_passthrough(self):
        envelope = '{"result": {"ok": true}}'
        self.assertEqual(
            ClaudeCodeAdapter._extract_verdict(envelope, "dev"), {"ok": True})

    def test_non_json_raises(self):
        with self.assertRaises(AdapterError):
            ClaudeCodeAdapter._extract_verdict("not json", "dev")

    def test_verdict_tolerates_json_code_fence(self):
        envelope = json.dumps({"result": "```json\n{\"decision\": \"pass\"}\n```"})
        self.assertEqual(
            ClaudeCodeAdapter._extract_verdict(envelope, "review"),
            {"decision": "pass"})

    def test_verdict_tolerates_surrounding_prose(self):
        envelope = json.dumps(
            {"result": "Here is the verdict:\n{\"verdict\": \"A\"}\nThanks."})
        self.assertEqual(
            ClaudeCodeAdapter._extract_verdict(envelope, "deliver"),
            {"verdict": "A"})

    def test_verdict_non_object_raises(self):
        envelope = json.dumps({"result": "totally not json at all"})
        with self.assertRaises(AdapterError):
            ClaudeCodeAdapter._extract_verdict(envelope, "review")


class ClaudeArtifactSpawnTests(unittest.TestCase):
    """An ARTIFACT spawn (no verdict schema, e.g. dev/research) returns the prose
    result WITHOUT requiring JSON — the regression that hard-failed the Dev step
    after it had already written all the code."""

    def test_extract_artifact_wraps_prose(self):
        envelope = json.dumps({"result": "Implemented the modules; handoff below."})
        self.assertEqual(
            ClaudeCodeAdapter._extract_artifact(envelope, "dev"),
            {"artifact": "Implemented the modules; handoff below."})

    def test_spawn_with_empty_schema_returns_artifact(self):
        a = ClaudeCodeAdapter(model="m", allow_subprocess=True)
        prose = "wrote src/loop/controller.py + tests; see docs/handoff.md"
        envelope = json.dumps({"result": prose})

        def _fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, stdout=envelope, stderr="")

        with mock.patch("adapters.claude_code.run_with_monitor",
                        side_effect=_fake_run):
            out = a.spawn("dev", "p", [], {}, sandbox="workspace_write")  # {} schema
        self.assertEqual(out.result, {"artifact": prose})
        # §3/D2 envelope: the stream parsed cleanly (zero Read events) → observed + [].
        self.assertEqual(out.telemetry.observability, "observed")
        self.assertEqual(out.telemetry.read_paths, [])
        self.assertIsNone(out.telemetry.raw_stream)   # AIDAZI_KEEP_RAW_STREAM unset


class RegistryTests(unittest.TestCase):
    def test_registry_resolves_claude_code(self):
        self.assertIs(ADAPTER_REGISTRY["claude_code"], ClaudeCodeAdapter)
        self.assertIs(resolve_adapter_class("claude_code"), ClaudeCodeAdapter)
        self.assertTrue(issubclass(ClaudeCodeAdapter, Adapter))


@unittest.skipUnless(os.environ.get(_ALLOW_ENV) == "1",
                     "real claude write-capability test (opt-in via "
                     "AIDAZI_ALLOW_REAL_ADAPTER=1)")
class ClaudeWriteCapabilityIntegrationTests(unittest.TestCase):
    """REAL claude in a throwaway git repo: a workspace_write session must write.

    This is the regression behind the Dev-step hard-fail — without the
    acceptEdits mapping the headless write is permission-denied and the session
    never produces a file. Skipped unless the real-adapter gate is set.
    """

    def test_workspace_write_session_writes_a_file(self):
        d = tempfile.mkdtemp(prefix="claude-cc-integ-")
        subprocess.run(["git", "init", "-q"], cwd=d,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        a = ClaudeCodeAdapter(model="claude-sonnet-4-6",
                              allow_subprocess=True, cwd=d, timeout_seconds=120)
        prompt = ('Create a file named SENTINEL.txt whose exact contents are the '
                  'two characters: ok\n'
                  'Then respond with ONLY this JSON as your final message: '
                  '{"wrote": true}')
        try:
            verdict = a.spawn("dev", prompt, [], _SCHEMA,
                              sandbox="workspace_write")
            self.assertIsInstance(verdict, dict)
        except AdapterError:
            pass  # verdict-shape is secondary; the write below is the assertion
        self.assertTrue(os.path.exists(os.path.join(d, "SENTINEL.txt")),
                        "workspace_write session did not write SENTINEL.txt")


def _stream(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


class ClaudeStreamParseTests(unittest.TestCase):
    """P2: _final_result_from_stream parses a stream-json transcript."""

    def test_terminal_result_extracted(self):
        s = _stream(
            {"type": "system", "subtype": "init"},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "hi"}]}},
            {"type": "result", "subtype": "success",
             "result": "the answer", "is_error": False})
        self.assertEqual(
            ClaudeCodeAdapter._final_result_from_stream(s, "dev"), "the answer")

    def test_is_error_raises(self):
        s = _stream({"type": "result", "subtype": "error_during_execution",
                     "is_error": True})
        with self.assertRaises(AdapterError):
            ClaudeCodeAdapter._final_result_from_stream(s, "dev")

    def test_error_subtype_raises(self):
        s = _stream({"type": "result", "subtype": "error_max_turns",
                     "is_error": False})
        with self.assertRaises(AdapterError):
            ClaudeCodeAdapter._final_result_from_stream(s, "dev")

    def test_no_terminal_event_raises(self):
        s = _stream({"type": "system", "subtype": "init"},
                    {"type": "assistant", "message": {"content": [
                        {"type": "text", "text": "x"}]}})
        with self.assertRaises(AdapterError):
            ClaudeCodeAdapter._final_result_from_stream(s, "dev")

    def test_trailing_truncation_fragment_tolerated(self):
        s = _stream({"type": "result", "subtype": "success",
                     "result": "ok", "is_error": False}) + '{"type":"partial'
        self.assertEqual(
            ClaudeCodeAdapter._final_result_from_stream(s, "dev"), "ok")

    def test_midstream_garbage_raises(self):
        s = "this is not json\n" + _stream(
            {"type": "result", "subtype": "success", "result": "x",
             "is_error": False})
        with self.assertRaises(AdapterError):
            ClaudeCodeAdapter._final_result_from_stream(s, "dev")

    def test_single_envelope_backcompat(self):
        self.assertEqual(
            ClaudeCodeAdapter._final_result_from_stream(
                json.dumps({"result": "legacy"}), "review"), "legacy")

    def test_single_nonterminal_event_raises(self):
        # A truncated one-line stream carrying a NON-terminal event must NOT be
        # accepted as success (back-compat was too permissive — Code-B1).
        for evt in (
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Bash"}]}},
            {"type": "system", "subtype": "init"},
        ):
            with self.assertRaises(AdapterError):
                ClaudeCodeAdapter._final_result_from_stream(
                    json.dumps(evt) + "\n", "dev")

    def test_artifact_and_verdict_via_stream(self):
        art = _stream({"type": "result", "subtype": "success",
                       "result": "impl + handoff", "is_error": False})
        self.assertEqual(ClaudeCodeAdapter._extract_artifact(art, "dev"),
                         {"artifact": "impl + handoff"})
        ver = _stream({"type": "result", "subtype": "success",
                       "result": "{\"decision\": \"pass\"}", "is_error": False})
        self.assertEqual(ClaudeCodeAdapter._extract_verdict(ver, "review"),
                         {"decision": "pass"})


class ToolLeaseProbeTests(unittest.TestCase):
    """P2-L: the active-tool lease opens/closes strictly on stream-json events."""

    @staticmethod
    def _tu(tid="t1"):
        return json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tid, "name": "Bash"}]}})

    @staticmethod
    def _tr(tid="t1", err=False):
        return json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "is_error": err}]}})

    def test_open_then_close(self):
        p = ToolLeaseProbe()
        self.assertFalse(p.active())
        p.observe(self._tu())
        self.assertTrue(p.active())
        p.observe(self._tr())
        self.assertFalse(p.active())

    def test_error_result_still_closes(self):
        p = ToolLeaseProbe()
        p.observe(self._tu())
        p.observe(self._tr(err=True))
        self.assertFalse(p.active())

    def test_unknown_id_result_is_noop(self):
        p = ToolLeaseProbe()
        p.observe(self._tu("t1"))
        p.observe(self._tr("SOMETHING_ELSE"))
        self.assertTrue(p.active())          # t1 still open

    def test_malformed_line_never_opens(self):
        p = ToolLeaseProbe()
        p.observe("not json")
        p.observe("{ broken")
        p.observe("")
        self.assertFalse(p.active())
        p.observe(self._tu())
        p.observe("garbage")                 # does not close/extend
        self.assertTrue(p.active())

    def test_terminal_result_clears_all(self):
        p = ToolLeaseProbe()
        p.observe(self._tu("a"))
        p.observe(self._tu("b"))
        self.assertTrue(p.active())
        p.observe(json.dumps({"type": "result", "subtype": "success",
                              "result": "x", "is_error": False}))
        self.assertFalse(p.active())

    def test_parallel_tools_close_independently(self):
        p = ToolLeaseProbe()
        p.observe(self._tu("a"))
        p.observe(self._tu("b"))
        p.observe(self._tr("a"))
        self.assertTrue(p.active())          # b still open
        p.observe(self._tr("b"))
        self.assertFalse(p.active())

    def test_non_tool_events_ignored(self):
        p = ToolLeaseProbe()
        p.observe(json.dumps({"type": "system", "subtype": "init"}))
        p.observe(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "hi"}]}}))
        self.assertFalse(p.active())


if __name__ == "__main__":
    unittest.main(verbosity=2)
