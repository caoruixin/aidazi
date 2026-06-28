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

import os
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
    def test_argv_uses_print_and_json(self):
        adapter = CursorAdapter(model="gpt-5")
        argv = adapter._build_argv(sandbox_flags=["--force"])
        self.assertEqual(argv[0], "cursor-agent")
        self.assertIn("-p", argv)
        self.assertIn("--output-format", argv)
        self.assertIn("json", argv)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
