"""Offline, deterministic tests for the ``codex`` adapter (P4 piece 3).

NO LLM, NO network, NO real Codex CLI. The real subprocess path is GATED and is
NEVER run here: with the gate unset, ``spawn`` raises ``AdapterError`` before any
process is launched; the gate-ordering test sets the gate but points the adapter
at a bogus, non-existent binary so it fails AT exec (OSError), proving the gate
is the only thing that was stopping I/O — without requiring a real codex install.

Run standalone:
    python -m unittest engine_kit.adapters.tests.test_codex   # (path-dependent)
or, from this dir's sys.path shim, simply:
    python /Users/.../engine-kit/adapters/tests/test_codex.py
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
    MockAdapter,
    ClaudeCodeAdapter,
    HeadlessAdapter,
    CodexAdapter,
    ADAPTER_REGISTRY,
    resolve_adapter_class,
)

_ALLOW_ENV = "AIDAZI_ALLOW_REAL_ADAPTER"
_SCHEMA = {"type": "object"}


class CodexGateTests(unittest.TestCase):
    """The real subprocess path is gated; unset gate => AdapterError, zero I/O."""

    def setUp(self):
        # Ensure the gate env var is unset for these tests regardless of host env.
        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop(_ALLOW_ENV, None)

    def tearDown(self):
        self._env_patch.stop()

    def test_gated_off_raises_adaptererror(self):
        """With the gate unset, spawn raises AdapterError naming the gate."""
        adapter = CodexAdapter()  # allow_subprocess defaults False
        with self.assertRaises(AdapterError) as ctx:
            adapter.spawn("dev", "do the thing", [], _SCHEMA)
        msg = str(ctx.exception)
        self.assertIn("gated off", msg)
        self.assertEqual(ctx.exception.role, "dev")

    def test_gated_off_attempts_no_subprocess(self):
        """Prove ZERO I/O: subprocess.run must NOT be called when gated off."""
        adapter = CodexAdapter()
        with mock.patch("adapters.codex.subprocess.run") as run_mock:
            with self.assertRaises(AdapterError):
                adapter.spawn("dev", "prompt", ["Read"], _SCHEMA)
        run_mock.assert_not_called()

    def test_provider_is_openai(self):
        """Codex <-> OpenAI: provider defaults to 'openai'."""
        self.assertEqual(CodexAdapter().provider, "openai")
        self.assertEqual(CodexAdapter().describe()["provider"], "openai")
        self.assertEqual(CodexAdapter().describe()["harness"], "codex")


class CodexGateOrderingTests(unittest.TestCase):
    """Gate set + bogus binary => reaches subprocess, fails AT exec (OSError).

    This proves the gate is the ONLY thing stopping I/O in the gated-off tests:
    once the gate is open the code path proceeds to subprocess.run, and the ONLY
    reason it fails now is that the (deliberately non-existent) binary cannot be
    executed. No real codex install is required or contacted.
    """

    def test_gate_open_reaches_exec_and_fails_on_bogus_binary(self):
        bogus = "aidazi-nonexistent-codex-binary-do-not-install-7f3a9c"
        # Open the gate via the constructor flag (no env mutation needed).
        adapter = CodexAdapter(binary=bogus, allow_subprocess=True)
        # Sanity: the gate is open.
        self.assertTrue(adapter._enabled())
        with self.assertRaises(AdapterError) as ctx:
            adapter.spawn("dev", "prompt", [], _SCHEMA)
        msg = str(ctx.exception)
        # The failure is the EXEC failing (OSError surfaced as AdapterError),
        # not the gate. It names the bogus binary.
        self.assertIn("failed to run", msg)
        self.assertIn(bogus, msg)

    def test_gate_open_via_env_reaches_exec(self):
        """Same proof, but opening the gate via the env var instead of the flag."""
        bogus = "aidazi-nonexistent-codex-binary-env-path-2b1d"
        adapter = CodexAdapter(binary=bogus)  # allow_subprocess False
        with mock.patch.dict(os.environ, {_ALLOW_ENV: "1"}):
            self.assertTrue(adapter._enabled())
            with self.assertRaises(AdapterError) as ctx:
                adapter.spawn("dev", "prompt", [], _SCHEMA)
        self.assertIn("failed to run", str(ctx.exception))


class CodexArgvTests(unittest.TestCase):
    """Pure, no-I/O checks on the assembled argv (the documented CLI form)."""

    def test_argv_is_codex_exec_json(self):
        adapter = CodexAdapter(model="o4-mini", cwd="/work")
        argv = adapter._build_argv("hello prompt", ["Read", "Write"])
        # Documented non-interactive form: `codex exec --json ... <prompt>`.
        self.assertEqual(argv[0], "codex")
        self.assertEqual(argv[1], "exec")
        self.assertIn("--json", argv)
        self.assertIn("--model", argv)
        self.assertIn("o4-mini", argv)
        self.assertIn("--sandbox", argv)
        self.assertIn("read-only", argv)
        self.assertIn("-C", argv)
        self.assertIn("/work", argv)
        # Prompt is the final positional arg.
        self.assertEqual(argv[-1], "hello prompt")


class CodexVerdictParseTests(unittest.TestCase):
    """The JSONL final-message parser is pure (no I/O) — exercise it directly."""

    def test_parses_final_agent_message_jsonl(self):
        stdout = "\n".join([
            '{"type":"thread.started","thread_id":"abc"}',
            '{"type":"agent_message","message":"{\\"status\\":\\"draft\\"}"}',
        ])
        verdict = CodexAdapter._extract_verdict(stdout, "dev")
        self.assertEqual(verdict, {"status": "draft"})

    def test_parses_item_completed_shape(self):
        stdout = "\n".join([
            'banner line that is not json',
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"{\\"ok\\":true}"}}',
        ])
        verdict = CodexAdapter._extract_verdict(stdout, "review")
        self.assertEqual(verdict, {"ok": True})

    def test_last_message_wins(self):
        stdout = "\n".join([
            '{"type":"agent_message","message":"{\\"n\\":1}"}',
            '{"type":"agent_message","message":"{\\"n\\":2}"}',
        ])
        self.assertEqual(
            CodexAdapter._extract_verdict(stdout, "dev"), {"n": 2}
        )

    def test_no_message_raises(self):
        with self.assertRaises(AdapterError):
            CodexAdapter._extract_verdict('{"type":"thread.started"}', "dev")

    def test_non_json_final_message_raises(self):
        stdout = '{"type":"agent_message","message":"not json at all"}'
        with self.assertRaises(AdapterError):
            CodexAdapter._extract_verdict(stdout, "dev")

    def test_non_object_verdict_raises(self):
        stdout = '{"type":"agent_message","message":"[1, 2, 3]"}'
        with self.assertRaises(AdapterError):
            CodexAdapter._extract_verdict(stdout, "dev")


class RegistryTests(unittest.TestCase):
    """The registry resolves codex AND the pre-existing harnesses are intact."""

    def test_registry_resolves_codex(self):
        self.assertIs(ADAPTER_REGISTRY["codex"], CodexAdapter)
        self.assertIs(resolve_adapter_class("codex"), CodexAdapter)
        self.assertTrue(issubclass(CodexAdapter, Adapter))

    def test_existing_harnesses_unchanged(self):
        self.assertIs(resolve_adapter_class("mock"), MockAdapter)
        self.assertIs(resolve_adapter_class("claude_code"), ClaudeCodeAdapter)
        self.assertIs(resolve_adapter_class("headless"), HeadlessAdapter)

    def test_all_four_harnesses_present(self):
        self.assertEqual(
            set(ADAPTER_REGISTRY),
            {"mock", "claude_code", "headless", "codex"},
        )

    def test_unknown_harness_still_raises_typed_error(self):
        with self.assertRaises(AdapterError):
            resolve_adapter_class("nope", role="dev")


if __name__ == "__main__":
    unittest.main(verbosity=2)
