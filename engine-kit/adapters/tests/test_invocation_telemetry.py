"""Universal-skill-mounting §3/D2 — invocation-scoped consumption telemetry at the
ADAPTER boundary: the SpawnResult envelope, the claude_code stream-json read parse
(the proven WP-3 pattern), attempt binding, the raw-stream canary flag, and the
non-contamination-by-construction properties (no adapter instance state ever holds
read evidence)."""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))   # engine-kit/

from adapters import (InvocationTelemetry, MockAdapter,  # noqa: E402
                      SpawnResult)
from adapters.claude_code import (ClaudeCodeAdapter,  # noqa: E402
                                  parse_read_paths)


def _stream(*events):
    return "\n".join(json.dumps(e) for e in events)


def _read_event(path):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": path}}]}}


_TERMINAL = {"type": "result", "result": "done", "is_error": False}


class ParseReadPathsTests(unittest.TestCase):

    def test_extracts_read_file_paths_in_order(self):
        s = _stream(_read_event("/a/SKILL.md"), _read_event("/b/notes.md"),
                    _TERMINAL)
        self.assertEqual(parse_read_paths(s), ["/a/SKILL.md", "/b/notes.md"])

    def test_skips_junk_lines_and_non_read_tools(self):
        s = "\n".join([
            "not-json-at-all",
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}),
            json.dumps(_read_event("/x/SKILL.md")),
            json.dumps(_TERMINAL),
        ])
        self.assertEqual(parse_read_paths(s), ["/x/SKILL.md"])

    def test_empty_or_readless_stream_is_empty_list(self):
        self.assertEqual(parse_read_paths(""), [])
        self.assertEqual(parse_read_paths(_stream(_TERMINAL)), [])


class ClaudeCodeTelemetryTests(unittest.TestCase):

    def _spawn(self, stdout, *, attempt=None, env=None):
        a = ClaudeCodeAdapter(model="m", allow_subprocess=True)

        def _fake_run(argv, **kw):
            proc = subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")
            if attempt is not None:
                proc.aidazi_attempt = attempt
            return proc

        patches = [mock.patch("adapters.claude_code.run_with_monitor",
                              side_effect=_fake_run)]
        if env is not None:
            patches.append(mock.patch.dict(os.environ, env))
        with patches[0]:
            if len(patches) > 1:
                with patches[1]:
                    return a.spawn("dev", "p", [], {})
            return a.spawn("dev", "p", [], {})

    def test_observed_with_read_paths(self):
        res = self._spawn(_stream(_read_event("/s/tdd/SKILL.md"), _TERMINAL))
        self.assertIsInstance(res, SpawnResult)
        self.assertEqual(res.telemetry.observability, "observed")
        self.assertEqual(res.telemetry.read_paths, ["/s/tdd/SKILL.md"])
        self.assertEqual(res.telemetry.terminal_attempt, 1)
        self.assertEqual(res.telemetry.terminal_status, "ok")

    def test_terminal_attempt_binds_the_monitor_attempt_index(self):
        res = self._spawn(_stream(_TERMINAL), attempt=2)
        self.assertEqual(res.telemetry.terminal_attempt, 2)

    def test_parse_failure_is_parse_error_never_zero_reads(self):
        with mock.patch("adapters.claude_code.parse_read_paths",
                        side_effect=RuntimeError("boom")):
            res = self._spawn(_stream(_TERMINAL))
        self.assertEqual(res.telemetry.observability, "parse_error")
        self.assertIsNone(res.telemetry.read_paths)

    def test_raw_stream_kept_only_under_env_flag(self):
        s = _stream(_TERMINAL)
        off = self._spawn(s)
        self.assertIsNone(off.telemetry.raw_stream)
        on = self._spawn(s, env={"AIDAZI_KEEP_RAW_STREAM": "1"})
        self.assertEqual(on.telemetry.raw_stream, s)

    def test_no_instance_state_holds_read_evidence(self):
        # Non-contamination BY CONSTRUCTION: two spawns on ONE adapter instance
        # yield distinct envelopes, and the instance grows no attribute holding
        # read evidence between calls.
        a = ClaudeCodeAdapter(model="m", allow_subprocess=True)
        attrs_before = set(a.__dict__)
        outs = []
        for path in ("/one/SKILL.md", "/two/SKILL.md"):
            stdout = _stream(_read_event(path), _TERMINAL)

            def _fake_run(argv, _s=stdout, **kw):
                return subprocess.CompletedProcess(argv, 0, stdout=_s, stderr="")

            with mock.patch("adapters.claude_code.run_with_monitor",
                            side_effect=_fake_run):
                outs.append(a.spawn("dev", "p", [], {}))
        self.assertEqual(outs[0].telemetry.read_paths, ["/one/SKILL.md"])
        self.assertEqual(outs[1].telemetry.read_paths, ["/two/SKILL.md"])
        self.assertEqual(set(a.__dict__), attrs_before)

    def test_interleaved_instances_stay_isolated(self):
        a, b = (ClaudeCodeAdapter(model="m", allow_subprocess=True) for _ in "ab")
        streams = {"a": _stream(_read_event("/a/SKILL.md"), _TERMINAL),
                   "b": _stream(_read_event("/b/SKILL.md"), _TERMINAL)}

        def run_on(adapter, key):
            def _fake_run(argv, **kw):
                return subprocess.CompletedProcess(argv, 0, stdout=streams[key],
                                                   stderr="")
            with mock.patch("adapters.claude_code.run_with_monitor",
                            side_effect=_fake_run):
                return adapter.spawn("dev", "p", [], {})

        ra1 = run_on(a, "a")
        rb1 = run_on(b, "b")
        ra2 = run_on(a, "a")
        self.assertEqual(ra1.telemetry.read_paths, ["/a/SKILL.md"])
        self.assertEqual(rb1.telemetry.read_paths, ["/b/SKILL.md"])
        self.assertEqual(ra2.telemetry.read_paths, ["/a/SKILL.md"])


class MonitorAttemptStampTests(unittest.TestCase):

    def test_run_with_monitor_stamps_terminal_attempt_index(self):
        # §3/D2 (Codex P2-gate NB2): assert the REAL monitor sets aidazi_attempt
        # (not a faked attribute) on a clean offline run.
        from adapters.monitor import MonitorConfig, run_with_monitor
        proc = run_with_monitor(
            [sys.executable, "-c", "print('ok')"],
            capture_output=True, text=True, timeout=10,
            role="dev", harness="test",
            monitor_config=MonitorConfig(poll_interval=0.05))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.aidazi_attempt, 1)


class EnvelopeBoundaryTests(unittest.TestCase):

    def test_mock_adapter_returns_unobservable_envelope(self):
        a = MockAdapter({("dev",): {"artifact": "x"}})
        res = a.spawn("dev", "p", [], {})
        self.assertIsInstance(res, SpawnResult)
        self.assertEqual(res.result, {"artifact": "x"})
        self.assertEqual(res.telemetry, InvocationTelemetry())
        self.assertEqual(res.telemetry.observability, "unobservable")

    def test_spawn_impl_returning_spawnresult_passes_through(self):
        canned = SpawnResult(result={"ok": True},
                             telemetry=InvocationTelemetry(
                                 observability="observed", read_paths=["/x"]))
        a = MockAdapter({("dev",): {"ignored": True}})
        with mock.patch.object(a, "_spawn_impl", return_value=canned):
            res = a.spawn("dev", "p", [], {})
        self.assertIs(res, canned)


if __name__ == "__main__":
    unittest.main()
