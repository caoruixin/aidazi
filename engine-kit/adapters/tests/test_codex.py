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
        argv = adapter._build_argv(["Read", "Write"])
        # Documented non-interactive form: `codex exec --json ...`. The PROMPT is
        # passed on STDIN (subprocess input=), NEVER as a positional argv token.
        self.assertEqual(argv[0], "codex")
        self.assertEqual(argv[1], "exec")
        self.assertIn("--json", argv)
        self.assertIn("--model", argv)
        self.assertIn("o4-mini", argv)
        self.assertIn("--sandbox", argv)
        self.assertIn("read-only", argv)
        self.assertIn("-C", argv)
        self.assertIn("/work", argv)
        # No prompt anywhere in argv (it rides on stdin).
        self.assertNotIn("hello prompt", argv)

    def test_argv_includes_output_last_message_when_path_given(self):
        # `-o <file>` is appended when a last-message path is supplied.
        adapter = CodexAdapter(model="m")
        argv = adapter._build_argv([], last_message_path="/tmp/x/last.txt")
        self.assertIn("-o", argv)
        self.assertIn("/tmp/x/last.txt", argv)
        # No path supplied ⇒ no `-o` (e.g. the pure argv-shape test above).
        self.assertNotIn("-o", CodexAdapter(model="m")._build_argv([]))

    def test_argv_skip_git_repo_check_is_opt_in(self):
        on = CodexAdapter(model="m", skip_git_repo_check=True)._build_argv([])
        self.assertIn("--skip-git-repo-check", on)
        off = CodexAdapter(model="m")._build_argv([])
        self.assertNotIn("--skip-git-repo-check", off)


def _arg_after(argv, flags):
    """Return the argv token following the first of ``flags`` (e.g. after -o)."""
    for i, tok in enumerate(argv):
        if tok in flags:
            return argv[i + 1]
    raise AssertionError(f"none of {flags} found in {argv}")


_GRANT = [{"id": "gh", "kind": "mcp", "server": "gh-mcp@v1.0.0",
           "scopes": ["read"], "tools": ["search_issues"]}]


class CodexConnectorsSandboxTests(unittest.TestCase):
    """Facet C wiring on the codex adapter (P4 integration follow-up):
    sandbox maps aidazi→codex-native; a granted connector FAILS CLOSED (codex
    exec has no confirmed per-call injection form — never silently drop)."""

    def test_codex_sandbox_mapping(self):
        a = CodexAdapter(sandbox="read-only")  # codex-native ctor default
        self.assertEqual(a._codex_sandbox("read_only"), "read-only")
        self.assertEqual(a._codex_sandbox("workspace_write"), "workspace-write")
        self.assertEqual(a._codex_sandbox(None), "read-only")  # ctor default
        # A codex-native value still maps (a caller may set it directly).
        self.assertEqual(a._codex_sandbox("workspace-write"), "workspace-write")

    def test_codex_sandbox_fails_closed_on_unknown(self):
        # A routed/charter value that is NOT a known sandbox FAILS CLOSED rather
        # than being forwarded to `codex --sandbox` (danger-full-access guard).
        a = CodexAdapter(sandbox="read-only")
        for bad in ("danger-full-access", "yolo", ""):
            with self.assertRaises(AdapterError) as ctx:
                a._codex_sandbox(bad, "review")
            self.assertIn("unsupported sandbox", str(ctx.exception))
            self.assertEqual(ctx.exception.role, "review")

    def test_build_argv_sandbox_override(self):
        a = CodexAdapter(model="m")  # ctor sandbox default "read-only"
        argv = a._build_argv([], sandbox="workspace-write")
        self.assertIn("--sandbox", argv)
        self.assertIn("workspace-write", argv)
        self.assertNotIn("read-only", argv)

    def test_spawn_maps_aidazi_sandbox_into_argv(self):
        a = CodexAdapter(model="m", allow_subprocess=True, binary="codex")
        captured = {}

        def _fake_run(argv, **kw):
            captured["argv"] = argv
            raise OSError("stop after capture")  # bail; we only want the argv

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            with self.assertRaises(AdapterError):
                a.spawn("dev", "p", [], _SCHEMA, sandbox="workspace_write")
        self.assertIn("workspace-write", captured["argv"])

    def test_granted_connector_fails_closed_before_subprocess(self):
        a = CodexAdapter(model="m", allow_subprocess=True)  # gate OPEN
        with mock.patch("adapters.codex.subprocess.run") as run_mock:
            with self.assertRaises(AdapterError) as ctx:
                a.spawn("dev", "p", [], _SCHEMA, connectors=_GRANT)
        # Fail-closed: it raised BEFORE any subprocess, and says so.
        run_mock.assert_not_called()
        self.assertIn("Failing closed", str(ctx.exception))
        self.assertEqual(ctx.exception.role, "dev")

    def test_no_connectors_reaches_exec_unchanged(self):
        # No connectors (default-deny) ⇒ the fail-closed guard is a no-op and the
        # spawn proceeds to exec exactly as before (bogus binary ⇒ exec fails).
        bogus = "aidazi-nonexistent-codex-binary-conn-3e8b"
        a = CodexAdapter(binary=bogus, allow_subprocess=True)
        with self.assertRaises(AdapterError) as ctx:
            a.spawn("dev", "p", [], _SCHEMA, connectors=None)
        self.assertIn("failed to run", str(ctx.exception))


class CodexNetworkAccessTests(unittest.TestCase):
    """The opt-in network grant (tooling.<role>.network_access) maps to codex's
    `-c sandbox_workspace_write.network_access=true` config override — ONLY for a
    workspace-write sandbox, and ONLY when explicitly granted (default OFF, so the
    Dev=no-network invariant holds unless an adopter opts in)."""

    _NET_OVERRIDE = "sandbox_workspace_write.network_access=true"

    def test_off_by_default_no_override(self):
        argv = CodexAdapter(model="m")._build_argv([], sandbox="workspace-write")
        self.assertNotIn(self._NET_OVERRIDE, argv)
        self.assertNotIn("-c", argv)

    def test_grant_emits_config_override_for_workspace_write(self):
        argv = CodexAdapter(model="m")._build_argv(
            [], sandbox="workspace-write", network_access=True)
        # codex form: ... -c sandbox_workspace_write.network_access=true
        self.assertIn("-c", argv)
        self.assertEqual(argv[argv.index("-c") + 1], self._NET_OVERRIDE)

    def test_grant_is_fail_closed_on_non_bool(self):
        # The ENFORCEMENT LAYER fails closed: only a literal bool True grants. A
        # truthy non-bool (the string "false"/"yes"/"true", or 1) must NOT emit the
        # override — the adapter never trusts an upstream caller to have sanitized
        # the value. (Adversarial finding from the Codex gpt-5.5 review.)
        a = CodexAdapter(model="m")
        for val in ("false", "yes", "true", 1, 0, None):
            argv = a._build_argv([], sandbox="workspace-write", network_access=val)
            self.assertNotIn(self._NET_OVERRIDE, argv,
                             msg=f"network_access={val!r} must NOT grant network")
        # Only a literal True grants.
        self.assertIn(self._NET_OVERRIDE, a._build_argv(
            [], sandbox="workspace-write", network_access=True))

    def test_grant_is_no_op_on_read_only(self):
        # The config key is namespaced to workspace_write; a grant on a read-only
        # sandbox is a NO-OP (read-only never gets network anyway).
        argv = CodexAdapter(model="m")._build_argv(
            [], sandbox="read-only", network_access=True)
        self.assertNotIn(self._NET_OVERRIDE, argv)
        self.assertNotIn("-c", argv)

    def test_spawn_threads_network_access_into_argv(self):
        a = CodexAdapter(model="m", allow_subprocess=True)
        captured = {}

        def _fake_run(argv, **kw):
            captured["argv"] = argv
            raise OSError("stop after capture")  # bail; we only want the argv

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            with self.assertRaises(AdapterError):
                a.spawn("dev", "p", [], _SCHEMA, sandbox="workspace_write",
                        network_access=True)
        self.assertEqual(
            captured["argv"][captured["argv"].index("-c") + 1], self._NET_OVERRIDE)

    def test_spawn_default_no_network_override(self):
        # Default spawn (no network_access kwarg) never emits the override.
        a = CodexAdapter(model="m", allow_subprocess=True)
        captured = {}

        def _fake_run(argv, **kw):
            captured["argv"] = argv
            raise OSError("stop after capture")

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            with self.assertRaises(AdapterError):
                a.spawn("dev", "p", [], _SCHEMA, sandbox="workspace_write")
        self.assertNotIn(self._NET_OVERRIDE, captured["argv"])


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


class CodexOutputFilePrimaryTests(unittest.TestCase):
    """The verdict is read from the `-o` output file (version-stable primary),
    falling back to the JSONL stdout stream only when the file is empty/missing.

    Still NO real codex: subprocess.run is mocked to emulate codex writing (or
    not writing) the last-message file. This is what makes the final-message
    event ``type`` non-load-bearing — the TODO(human) the module used to carry.
    """

    def test_spawn_prefers_output_last_message_file(self):
        a = CodexAdapter(model="m", allow_subprocess=True, binary="codex")

        def _fake_run(argv, **kw):
            # Emulate codex writing its final message to the `-o` path.
            path = _arg_after(argv, ("-o", "--output-last-message"))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"status": "draft"}')
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            verdict = a.spawn("dev", "p", [], _SCHEMA)
        self.assertEqual(verdict, {"status": "draft"})

    def test_spawn_falls_back_to_jsonl_when_output_file_empty(self):
        a = CodexAdapter(model="m", allow_subprocess=True, binary="codex")
        jsonl = '{"type":"agent_message","message":"{\\"ok\\":true}"}'

        def _fake_run(argv, **kw):
            # Leave the `-o` file UNWRITTEN ⇒ spawn must fall back to stdout JSONL.
            return subprocess.CompletedProcess(argv, 0, stdout=jsonl, stderr="")

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            verdict = a.spawn("dev", "p", [], _SCHEMA)
        self.assertEqual(verdict, {"ok": True})

    def test_spawn_nonzero_exit_raises_before_reading_file(self):
        a = CodexAdapter(model="m", allow_subprocess=True, binary="codex")

        def _fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr="boom")

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            with self.assertRaises(AdapterError) as ctx:
                a.spawn("dev", "p", [], _SCHEMA)
        self.assertIn("exited 2", str(ctx.exception))


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

    def test_all_harnesses_present(self):
        self.assertEqual(
            set(ADAPTER_REGISTRY),
            {"mock", "claude_code", "headless", "codex", "kimi"},
        )

    def test_unknown_harness_still_raises_typed_error(self):
        with self.assertRaises(AdapterError):
            resolve_adapter_class("nope", role="dev")


class CodexVerdictRobustnessTests(unittest.TestCase):
    """Tolerant verdict parsing + scan-all-messages + the JSON-only output
    contract — hardening the verdict path against codex's final-message variance
    (an intermittent empty/non-JSON final message broke review)."""

    def test_tolerates_json_code_fence(self):
        stdout = ('{"type":"agent_message","message":'
                  '"```json\\n{\\"decision\\":\\"pass\\"}\\n```"}')
        self.assertEqual(CodexAdapter._extract_verdict(stdout, "review"),
                         {"decision": "pass"})

    def test_scans_back_when_final_message_is_prose(self):
        stdout = "\n".join([
            '{"type":"agent_message","message":"{\\"decision\\":\\"fix_required\\"}"}',
            '{"type":"agent_message","message":"Done — ping me if you need more."}',
        ])
        self.assertEqual(CodexAdapter._extract_verdict(stdout, "review"),
                         {"decision": "fix_required"})

    def test_parse_verdict_text_tolerates_prose(self):
        self.assertEqual(
            CodexAdapter._parse_verdict_text("Here:\n{\"verdict\":\"A\"}\nthx",
                                             "deliver"),
            {"verdict": "A"})

    def test_spawn_appends_output_contract_when_schema_given(self):
        a = CodexAdapter(model="m", allow_subprocess=True)
        captured = {}

        def _fake_run(argv, **kw):
            captured["prompt"] = kw.get("input")  # prompt rides on STDIN now
            raise OSError("stop after capture")

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            with self.assertRaises(AdapterError):
                a.spawn("review", "Review it.", [], {"type": "object"})
        self.assertIn("OUTPUT CONTRACT", captured["prompt"])

    def test_spawn_no_contract_when_no_schema(self):
        a = CodexAdapter(model="m", allow_subprocess=True)
        captured = {}

        def _fake_run(argv, **kw):
            captured["prompt"] = kw.get("input")  # prompt rides on STDIN now
            raise OSError("stop")

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            with self.assertRaises(AdapterError):
                a.spawn("dev", "Do it.", [], {})  # empty schema → no contract
        self.assertNotIn("OUTPUT CONTRACT", captured["prompt"])

    def test_artifact_spawn_returns_prose_not_json_verdict(self):
        # A no-schema (Dev/Research) spawn returns the final message as an artifact,
        # NOT a parsed JSON verdict — a prose handoff must not hard-fail (parity with
        # claude_code / kimi). The -o file is unwritten under mock, so it falls back
        # to the last agent message in the JSONL stream.
        a = CodexAdapter(model="m", allow_subprocess=True)
        stdout = ('{"type":"agent_message","message":"Implemented the module; '
                  'handoff written to docs/handoff.md."}')

        def _fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            out = a.spawn("dev", "Do it.", [], {})  # empty schema → artifact
        self.assertEqual(
            out, {"artifact": "Implemented the module; handoff written to docs/handoff.md."})


class CodexFailClosedTests(unittest.TestCase):
    """The VERDICT path FAILS CLOSED: a candidate is accepted only if it parses to a
    JSON object AND conforms to the role schema; otherwise AdapterError. Never prose,
    partial JSON, or an arbitrary final event."""

    _STRICT = {"type": "object", "required": ["decision"],
               "properties": {"decision": {"type": "string"}}}

    def test_verdict_conforms(self):
        c = CodexAdapter._verdict_conforms
        self.assertTrue(c({"decision": "pass"}, self._STRICT))
        self.assertFalse(c({"note": "x"}, self._STRICT))     # missing required
        self.assertFalse(c({"decision": 5}, self._STRICT))   # wrong type
        self.assertFalse(c("not a dict", self._STRICT))
        self.assertTrue(c({"anything": 1}, None))            # no schema → a dict suffices
        self.assertFalse(c("prose", None))

    def test_extract_verdict_returns_conforming(self):
        stdout = "\n".join([
            '{"type":"agent_message","message":"{\\"decision\\":\\"pass\\"}"}',
            '{"type":"agent_message","message":"Done — anything else?"}',
        ])
        self.assertEqual(
            CodexAdapter._extract_verdict(stdout, "review", self._STRICT),
            {"decision": "pass"})

    def test_extract_verdict_rejects_nonconforming_json(self):
        # a non-conforming JSON object (missing required) + closing prose ⇒ no
        # conforming verdict ⇒ AdapterError (not the arbitrary JSON object).
        stdout = "\n".join([
            '{"type":"agent_message","message":"{\\"note\\":\\"not a verdict\\"}"}',
            '{"type":"agent_message","message":"All done."}',
        ])
        with self.assertRaises(AdapterError):
            CodexAdapter._extract_verdict(stdout, "review", self._STRICT)

    def test_extract_verdict_prose_only_raises(self):
        stdout = '{"type":"agent_message","message":"just prose, no json at all"}'
        with self.assertRaises(AdapterError):
            CodexAdapter._extract_verdict(stdout, "review", self._STRICT)

    def test_spawn_fails_closed_when_no_conforming_verdict(self):
        # schema present, -o file empty under mock, stdout is prose → AdapterError.
        a = CodexAdapter(model="m", allow_subprocess=True)
        stdout = '{"type":"agent_message","message":"I could not produce a verdict."}'

        def _fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

        with mock.patch("adapters.codex.subprocess.run", side_effect=_fake_run):
            with self.assertRaises(AdapterError):
                a.spawn("review", "Review it.", [], self._STRICT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
