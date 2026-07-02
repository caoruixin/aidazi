#!/usr/bin/env python3
"""Offline, no-LLM tests for the CONNECTOR layer (Facet C; plan §4.1, §7 P4).

Covers the P4-piece-2 task list:
  - translate a 2-connector grant → correct claude_code (.mcp.json servers +
    allowed-tools) and headless (function list) output;
  - scoping to a `tools` subset works;
  - default-deny: empty/None connectors → empty config;
  - discovery.propose on a temp repo with a .mcp.json → right candidates marked
    `proposed` (and NO mutation / NO grant);
  - a write/network-scope connector is FLAGGED when translated for a read-only
    context (defensive note; hard enforcement is charter_validator's);
  - adapter backward-compat: spawning with NO connectors == prior behavior
    (no native config emitted).

Pure/deterministic: no network, no subprocess, no clock, no env secrets.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

# Put engine-kit/ on sys.path so `import connectors` + `import adapters` resolve
# exactly as they do for the orchestrator tests (no engine-kit package).
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_CONNECTORS_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_CONNECTORS_DIR)
if _ENGINE_KIT_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_KIT_DIR)

import connectors  # noqa: E402
from connectors import translate, propose, is_empty, flag_scope_violations  # noqa: E402
from adapters import ClaudeCodeAdapter, HeadlessAdapter, AdapterError  # noqa: E402


# A representative 2-connector grant (charter tooling.<role>.connectors[] shape).
TWO_CONNECTORS = [
    {
        "id": "github",
        "kind": "mcp",
        "server": "github-mcp@v1.2.0",
        "tools": ["search_issues", "get_pull_request"],   # NARROWED subset
        "scopes": ["read", "network"],
        "secrets": ["GITHUB_TOKEN"],
        "provenance": "vendor",
    },
    {
        "id": "weather",
        "kind": "http_api",
        "server": "https://api.weather.example/v1",
        # no `tools` → whole connector
        "scopes": ["network"],
        "secrets": ["WEATHER_API_KEY"],
        "provenance": "community",
    },
]


class TranslateClaudeCodeTests(unittest.TestCase):
    def test_two_connectors_mcp_servers_and_allowed_tools(self):
        cfg = translate(TWO_CONNECTORS, "claude_code")
        # MCP server def for the mcp connector, none for the http_api one.
        servers = cfg["mcp_config"]["mcpServers"]
        self.assertIn("github", servers)
        self.assertNotIn("weather", servers)
        self.assertEqual(servers["github"]["command"], "github-mcp@v1.2.0")
        # secret is a NAME placeholder, never a value.
        self.assertEqual(servers["github"]["env"], {"GITHUB_TOKEN": "${GITHUB_TOKEN}"})
        self.assertNotIn("ghp_", json.dumps(cfg))  # no value leaked
        # allowed-tools: github narrowed to its 2 tools, weather as a bare grant.
        self.assertIn("mcp__github__search_issues", cfg["allowed_tools"])
        self.assertIn("mcp__github__get_pull_request", cfg["allowed_tools"])
        self.assertIn("weather", cfg["allowed_tools"])
        # the narrowed github grant must NOT include a whole-server mcp__github.
        self.assertNotIn("mcp__github", cfg["allowed_tools"])

    def test_whole_server_when_no_tools_subset(self):
        grant = [{"id": "db", "kind": "mcp", "server": "db-mcp@1.0",
                  "scopes": ["read"]}]
        cfg = translate(grant, "claude_code")
        self.assertEqual(cfg["allowed_tools"], ["mcp__db"])  # whole server


class TranslateHeadlessTests(unittest.TestCase):
    def test_two_connectors_function_list(self):
        cfg = translate(TWO_CONNECTORS, "headless")
        names = [f["function"]["name"] for f in cfg["tools"]]
        # github narrowed → one function per tool; weather → one function.
        self.assertIn("github__search_issues", names)
        self.assertIn("github__get_pull_request", names)
        self.assertIn("weather", names)
        self.assertEqual(len(cfg["tools"]), 3)
        # every entry is an OpenAI function-calling schema entry.
        for f in cfg["tools"]:
            self.assertEqual(f["type"], "function")
            self.assertIn("name", f["function"])
            self.assertEqual(f["function"]["parameters"]["type"], "object")
        # secret NAMES surface in the description, never a value.
        self.assertNotIn("WEATHER_API_KEY=", json.dumps(cfg))
        self.assertTrue(any("GITHUB_TOKEN" in json.dumps(f) for f in cfg["tools"]))


class TranslateCodexTests(unittest.TestCase):
    def test_codex_tool_config_form(self):
        cfg = translate(TWO_CONNECTORS, "codex")
        names = [t["name"] for t in cfg["tools"]]
        self.assertIn("github__search_issues", names)
        self.assertIn("weather", names)
        gh = next(t for t in cfg["tools"] if t["name"] == "github__search_issues")
        self.assertEqual(gh["scopes"], ["read", "network"])
        self.assertEqual(gh["secrets"], ["GITHUB_TOKEN"])   # by-name only


class DefaultDenyTests(unittest.TestCase):
    def test_empty_and_none_are_empty_config(self):
        for harness in ("claude_code", "headless", "codex"):
            for grant in (None, [], [None]):
                cfg = translate(grant, harness)
                self.assertTrue(is_empty(cfg),
                                f"{harness} {grant!r} should be empty: {cfg}")

    def test_claude_code_empty_shape(self):
        cfg = translate(None, "claude_code")
        self.assertEqual(cfg["allowed_tools"], [])
        self.assertNotIn("mcp_config", cfg)  # no servers => key omitted

    def test_headless_empty_shape(self):
        cfg = translate([], "headless")
        self.assertEqual(cfg["tools"], [])

    def test_unsupported_harness_raises(self):
        with self.assertRaises(ValueError):
            translate(TWO_CONNECTORS, "nonsense_harness")


class DefensiveScopeNoteTests(unittest.TestCase):
    """A write/network connector translated for a read_only context is FLAGGED.

    This is a DEFENSIVE note only — the hard gate is charter_validator's. We
    assert the note fires (and does NOT drop the grant) and that it is silent for
    a workspace_write context.
    """

    def test_network_scope_flagged_for_read_only(self):
        cfg = translate(TWO_CONNECTORS, "headless", sandbox="read_only")
        self.assertTrue(cfg["_warnings"], "expected a defensive over-scope note")
        joined = " ".join(cfg["_warnings"])
        self.assertIn("github", joined)
        self.assertIn("weather", joined)
        # the grant itself is NOT dropped — translation still produced functions.
        self.assertEqual(len(cfg["tools"]), 3)

    def test_no_note_for_workspace_write(self):
        cfg = translate(TWO_CONNECTORS, "headless", sandbox="workspace_write")
        self.assertEqual(cfg["_warnings"], [])

    def test_read_scope_only_not_flagged_even_read_only(self):
        grant = [{"id": "docs", "kind": "mcp", "server": "docs@1",
                  "scopes": ["read"]}]
        self.assertEqual(flag_scope_violations(grant, sandbox="read_only"), [])


class DiscoveryProposeTests(unittest.TestCase):
    def _write_mcp_json(self, root: str) -> str:
        path = os.path.join(root, ".mcp.json")
        content = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github@1.0.0"],
                    "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
                },
                "filesystem": {
                    "command": "mcp-server-filesystem",
                    "args": ["/data"],
                },
            }
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(content, fh)
        return path

    def test_propose_returns_proposed_candidates_with_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            mcp_path = self._write_mcp_json(d)
            before = os.path.getsize(mcp_path)
            before_mtime = os.path.getmtime(mcp_path)

            cands = propose(d)

            ids = {c["id"] for c in cands}
            self.assertEqual(ids, {"github", "filesystem"})
            for c in cands:
                # PROPOSE-ONLY: every candidate is marked proposed, default-deny.
                self.assertEqual(c["status"], "proposed")
                self.assertEqual(c["proposed_scopes"], [])   # NOT granted
                self.assertEqual(c["kind"], "mcp")
                self.assertEqual(c["provenance"]["source_file"], ".mcp.json")
                self.assertTrue(
                    c["provenance"]["source_key"].startswith("mcpServers."))
                self.assertEqual(
                    c["provenance"]["discovered_by"],
                    "connectors.discovery.propose")
            gh = next(c for c in cands if c["id"] == "github")
            # secret recovered by NAME only.
            self.assertEqual(gh["secrets"], ["GITHUB_TOKEN"])
            self.assertIn("server-github@1.0.0", gh["server"])
            self.assertTrue(gh["pinned"])  # has @pin
            fs = next(c for c in cands if c["id"] == "filesystem")
            self.assertFalse(fs["pinned"])  # no @pin → human must pin

            # NO MUTATION: file unchanged on disk (size + mtime), no new files.
            self.assertEqual(os.path.getsize(mcp_path), before)
            self.assertEqual(os.path.getmtime(mcp_path), before_mtime)
            self.assertEqual(sorted(os.listdir(d)), [".mcp.json"])

    def test_propose_skips_noise_dirs_and_handles_nested(self):
        with tempfile.TemporaryDirectory() as d:
            # a node_modules .mcp.json must be ignored.
            nm = os.path.join(d, "node_modules", "pkg")
            os.makedirs(nm)
            with open(os.path.join(nm, ".mcp.json"), "w") as fh:
                json.dump({"mcpServers": {"noise": {"command": "x"}}}, fh)
            # a real one in a sub-package must be found.
            sub = os.path.join(d, "packages", "api")
            os.makedirs(sub)
            with open(os.path.join(sub, ".mcp.json"), "w") as fh:
                json.dump({"mcpServers": {"real": {"command": "y@1"}}}, fh)

            cands = propose(d)
            ids = {c["id"] for c in cands}
            self.assertEqual(ids, {"real"})

    def test_propose_malformed_file_yields_no_candidates(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, ".mcp.json"), "w") as fh:
                fh.write("{ this is not valid json ")
            self.assertEqual(propose(d), [])

    def test_propose_missing_dir_is_empty(self):
        self.assertEqual(propose("/no/such/dir/anywhere"), [])

    def test_propose_does_not_grant(self):
        """Candidates carry no authorization fields a runtime could act on."""
        with tempfile.TemporaryDirectory() as d:
            self._write_mcp_json(d)
            for c in propose(d):
                self.assertNotIn("scopes", c)        # no granted scopes
                self.assertEqual(c["proposed_scopes"], [])
                self.assertEqual(c["status"], "proposed")


class AdapterBackwardCompatTests(unittest.TestCase):
    """Spawning with NO connectors == prior behavior (no native config emitted).

    The adapters' real I/O is gated OFF in tests; we exercise the translation/
    argv/payload build paths directly, which is where connector wiring lives.
    """

    def test_claude_code_no_connectors_argv_unchanged(self):
        a = ClaudeCodeAdapter(model="claude-x")
        # translate_connectors with none → empty (no native config).
        self.assertEqual(a.translate_connectors(None), {})
        self.assertEqual(a.translate_connectors([]), {})
        # argv with no extras is exactly the pre-connector argv (the prompt rides
        # on STDIN now, so it is NOT an argv token).
        base_argv = a._build_argv(["Read", "Grep"])
        self.assertEqual(
            base_argv,
            ["claude", "-p", "--output-format", "stream-json", "--verbose",
             "--model", "claude-x", "--allowed-tools", "Read,Grep"],
        )
        self.assertNotIn("--mcp-config", base_argv)

    def test_claude_code_spawn_gated_off_with_no_connectors(self):
        a = ClaudeCodeAdapter(model="claude-x")  # allow_subprocess defaults False
        with self.assertRaises(AdapterError):
            a.spawn("dev", "p", ["Read"], {})              # no connectors
        with self.assertRaises(AdapterError):
            a.spawn("dev", "p", ["Read"], {}, connectors=TWO_CONNECTORS)

    def test_claude_code_argv_extends_only_with_connectors(self):
        a = ClaudeCodeAdapter(model="claude-x")
        cfg = a.translate_connectors(TWO_CONNECTORS)
        argv = a._build_argv(
            ["Read"],
            extra_allowed_tools=cfg["allowed_tools"],
            mcp_config_path="/tmp/x.json")
        joined = ",".join(argv)
        self.assertIn("mcp__github__search_issues", joined)
        self.assertIn("--mcp-config", argv)
        self.assertIn("Read", joined)  # original tool retained

    def test_headless_no_connectors_payload_unchanged(self):
        a = HeadlessAdapter(base_url="https://api.example/v1", model="m")
        self.assertEqual(a.translate_connectors(None), {})
        payload = a._build_payload("PROMPT", {})
        self.assertNotIn("tools", payload)  # no function list when none granted
        self.assertEqual(payload["model"], "m")
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_headless_payload_gets_tools_only_with_connectors(self):
        a = HeadlessAdapter(base_url="https://api.example/v1", model="m")
        cfg = a.translate_connectors(TWO_CONNECTORS)
        payload = a._build_payload("P", {}, functions=cfg["tools"])
        self.assertIn("tools", payload)
        self.assertEqual(len(payload["tools"]), 3)

    def test_headless_spawn_gated_off(self):
        a = HeadlessAdapter(base_url="https://api.example/v1", model="m")
        with self.assertRaises(AdapterError):
            a.spawn("acceptance", "p", [], {})  # no connectors, gated off


if __name__ == "__main__":
    unittest.main()
