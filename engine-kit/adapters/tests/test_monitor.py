"""Unit tests for the lightweight adapter subprocess monitor.

No real agent CLI is launched here. Small Python snippets stand in for child
processes so the stuck/restart behavior is deterministic and quick.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ADAPTERS_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ADAPTERS_DIR)
if _ENGINE_KIT_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_KIT_DIR)

from adapters.monitor import (  # noqa: E402
    AgentStuckError,
    MonitorConfig,
    _cpu_seconds,
    _effective_cpu_seconds,
    _group_cpu_seconds,
    _parse_ps_time,
    run_with_monitor,
)
from adapters.claude_code import ToolLeaseProbe  # noqa: E402


def _cfg(root):
    return MonitorConfig(
        no_output_seconds=0.15,
        idle_cpu_seconds=0.15,
        max_stuck_seconds=0.3,
        max_restarts=1,
        poll_interval=0.05,
        diagnostics_root=root,
    )


class MonitorTests(unittest.TestCase):
    def test_normal_completion_returns_completed_process_and_closes_stdin(self):
        proc = run_with_monitor(
            [sys.executable, "-c", "import sys; print(sys.stdin.read())"],
            input="hello",
            capture_output=True,
            text=True,
            timeout=5,
            role="review",
            harness="codex",
            monitor_config=MonitorConfig(poll_interval=0.05),
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "hello")

    def test_stuck_first_attempt_is_restarted_and_recovered(self):
        d = tempfile.mkdtemp(prefix="aidazi-monitor-test-")
        counter = os.path.join(d, "count.txt")
        script = textwrap.dedent(
            f"""
            import os, time
            path = {counter!r}
            try:
                n = int(open(path).read())
            except Exception:
                n = 0
            open(path, "w").write(str(n + 1))
            if n == 0:
                time.sleep(10)
            else:
                print("ok")
            """
        )
        proc = run_with_monitor(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
            role="review",
            harness="codex",
            monitor_config=_cfg(os.path.join(d, "diag")),
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "ok")
        self.assertIn("recovered from stuck", proc.stderr)
        with open(counter, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "2")
        self.assertTrue(os.listdir(os.path.join(d, "diag")))

    def test_repeated_stuck_raises_and_records_reason(self):
        d = tempfile.mkdtemp(prefix="aidazi-monitor-test-")
        diag = os.path.join(d, "diag")
        with self.assertRaises(AgentStuckError):
            run_with_monitor(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                capture_output=True,
                text=True,
                timeout=5,
                role="acceptance",
                harness="claude_code",
                monitor_config=_cfg(diag),
            )
        entries = os.listdir(diag)
        self.assertGreaterEqual(len(entries), 2)
        latest = os.path.join(diag, sorted(entries)[-1], "reason.json")
        with open(latest, encoding="utf-8") as fh:
            reason = json.load(fh)
        self.assertIn(reason["reason"], ("no_output_cpu_idle", "no_output_no_cpu_sample"))
        self.assertEqual(reason["attempt"], 2)


class ParsePsTimeTests(unittest.TestCase):
    """P1-a: _parse_ps_time handles macOS fractional AND Linux integer formats.

    The macOS regression: the old int(part) raised ValueError on the ``.ss``
    fraction, so _cpu_seconds returned None on every poll (blind CPU liveness).
    """

    def test_macos_fractional_formats(self):
        cases = {
            "0.04": 0.04, "05.62": 5.62,
            "0:05.62": 5.62, "12:05.62": 725.62,
            "1:02:03.50": 3723.50, "2-01:02:03.50": 176523.50,
            "133:46.93": 133 * 60 + 46.93,   # minutes may exceed 60 on macOS
        }
        for raw, expected in cases.items():
            self.assertAlmostEqual(_parse_ps_time(raw), expected, places=3,
                                   msg=f"{raw!r}")

    def test_linux_integer_formats(self):
        self.assertEqual(_parse_ps_time("03:01"), 181.0)
        self.assertEqual(_parse_ps_time("01:02:03"), 3723.0)
        self.assertEqual(_parse_ps_time("3-01:02:03"), 262923.0)

    def test_invalid_returns_none(self):
        for bad in ("", "   ", "garbage", "1:2:3:4", None):
            self.assertIsNone(_parse_ps_time(bad), msg=f"{bad!r}")

    def test_live_cpu_seconds_is_a_positive_float_on_this_host(self):
        # The exact regression: on macOS this used to be None (blind watchdog).
        v = _cpu_seconds(os.getpid())
        self.assertIsInstance(v, float)
        self.assertGreaterEqual(v, 0.0)


class GroupCpuTests(unittest.TestCase):
    """P1-b: _group_cpu_seconds sums the process group; _effective falls back."""

    def test_group_sum_over_matching_pgid(self):
        fake = "  501   0:05.00\n  501   1:00.00\n  999   9:00.00\n  501 bad\n"
        with mock.patch("adapters.monitor.subprocess.run",
                        return_value=mock.Mock(returncode=0, stdout=fake)):
            self.assertAlmostEqual(_group_cpu_seconds(501), 65.0, places=3)

    def test_group_none_when_no_row_matches(self):
        with mock.patch("adapters.monitor.subprocess.run",
                        return_value=mock.Mock(returncode=0, stdout="  1   0:01.00\n")):
            self.assertIsNone(_group_cpu_seconds(424242))

    def test_group_none_on_ps_failure(self):
        with mock.patch("adapters.monitor.subprocess.run",
                        return_value=mock.Mock(returncode=1, stdout="")):
            self.assertIsNone(_group_cpu_seconds(1))

    def test_effective_prefers_group_then_falls_back(self):
        with mock.patch("adapters.monitor._group_cpu_seconds", return_value=9.9):
            self.assertEqual(_effective_cpu_seconds(os.getpid()), 9.9)
        with mock.patch("adapters.monitor._group_cpu_seconds", return_value=None), \
                mock.patch("adapters.monitor._cpu_seconds", return_value=4.2):
            self.assertEqual(_effective_cpu_seconds(os.getpid()), 4.2)

    def test_group_exceeds_parent_when_child_busy(self):
        # NON-VACUOUS proof of P1-b: an IDLE parent whose CHILD (same PGID) burns
        # CPU. Parent-only sampling would read ~0 (idle); group sampling rises.
        src = ("import subprocess,sys,time\n"
               "c=subprocess.Popen([sys.executable,'-c','\\nwhile True: pass'])\n"
               "try:\n    time.sleep(5)\nfinally:\n    c.kill()\n")
        proc = subprocess.Popen([sys.executable, "-c", src], preexec_fn=os.setsid)
        try:
            time.sleep(1.3)
            pgid = os.getpgid(proc.pid)
            parent_only = _cpu_seconds(proc.pid) or 0.0
            group = _group_cpu_seconds(pgid) or 0.0
            self.assertLess(parent_only, 0.5)             # idle parent
            self.assertGreater(group, parent_only + 0.2)  # busy child counts
        finally:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
            proc.wait(timeout=5)


class LivenessLeaseIntegrationTests(unittest.TestCase):
    """End-to-end watchdog mechanics via real synthetic children (no LLM).

    Each proves a specific acceptance criterion deterministically.
    """

    @staticmethod
    def _cfg(no=1.0, idle=1.0, mx=1.5, restarts=0, poll=0.05, root=None):
        return MonitorConfig(
            no_output_seconds=no, idle_cpu_seconds=idle, max_stuck_seconds=mx,
            max_restarts=restarts, poll_interval=poll,
            diagnostics_root=root or tempfile.mkdtemp(prefix="aidazi-live-diag-"))

    @staticmethod
    def _emit_then_sleep(lines_and_sleeps):
        parts = ["import sys,time"]
        for ln, sl in lines_and_sleeps:
            if ln is not None:
                parts.append("sys.stdout.write(%r + '\\n'); sys.stdout.flush()" % ln)
            parts.append("time.sleep(%r)" % sl)
        return "\n".join(parts) + "\n"

    @staticmethod
    def _tool_use(tid="t1"):
        return json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tid, "name": "Bash"}]}})

    @staticmethod
    def _tool_result(tid="t1", err=False):
        return json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "is_error": err}]}})

    def _run(self, src, *, timeout=10, cfg=None, factory=None):
        return run_with_monitor(
            [sys.executable, "-c", src], capture_output=True, text=True,
            timeout=timeout, monitor_config=cfg or self._cfg(),
            liveness_probe_factory=factory)

    # ---- AC-5-O: output-liveness ----
    def test_output_liveness_not_killed(self):
        src = ("import sys,time\nend=time.time()+2.2\n"
               "while time.time()<end:\n"
               "    sys.stdout.write('tick\\n'); sys.stdout.flush(); time.sleep(0.2)\n")
        self.assertEqual(self._run(src).returncode, 0)

    # ---- AC-5-C: group-CPU-liveness (idle parent + busy child) ----
    def test_group_cpu_liveness_not_killed(self):
        src = ("import subprocess,sys,time\n"
               "c=subprocess.Popen([sys.executable,'-c','\\nwhile True: pass'])\n"
               "try:\n    time.sleep(2.2)\nfinally:\n    c.kill()\n")
        self.assertEqual(self._run(src).returncode, 0)

    # ---- AC-6: genuine stuck (no output, no CPU, no lease) is killed ----
    def test_genuine_stuck_killed(self):
        with self.assertRaises(AgentStuckError):
            self._run("import time; time.sleep(30)")

    # ---- AC-6b: hard timeout is the ceiling for a CPU-busy (semantic) hang ----
    def test_hard_timeout_ceiling_cpu_busy(self):
        cfg = self._cfg(no=100, idle=100, mx=100)  # silence watchdog cannot fire
        with self.assertRaises(subprocess.TimeoutExpired):
            self._run("\nwhile True: pass\n", timeout=1.0, cfg=cfg)

    # ---- AC-10: lease suppresses the silence-kill; releases on tool_result ----
    def test_lease_keeps_open_tool_alive(self):
        src = self._emit_then_sleep([(self._tool_use(), 1.8)])  # silent>window
        self.assertEqual(self._run(src, factory=ToolLeaseProbe).returncode, 0)

    def test_without_lease_same_silence_is_killed(self):  # non-vacuity control
        src = self._emit_then_sleep([(self._tool_use(), 3.0)])
        with self.assertRaises(AgentStuckError):
            self._run(src)  # no factory => the single line then silence => killed

    def test_lease_held_past_window_then_released_and_killed(self):
        # ONE end-to-end case (Code-NB1): tool_use -> silence PAST the window
        # (lease holds) -> tool_result (release) -> silence past the window ->
        # killed by the silence watchdog.
        src = self._emit_then_sleep([
            (self._tool_use(), 1.8), (self._tool_result(), 3.0)])
        with self.assertRaises(AgentStuckError):
            self._run(src, factory=ToolLeaseProbe)

    # ---- AC-11a: a hung (never-closing) lease is bounded by the hard timeout,
    #      with NO restart (timeout does not retry) ----
    def test_hung_lease_hard_timeout_no_retry(self):
        created = []

        def factory():
            p = ToolLeaseProbe()
            created.append(p)
            return p

        src = self._emit_then_sleep([(self._tool_use(), 30)])
        with self.assertRaises(subprocess.TimeoutExpired):
            self._run(src, timeout=1.0, cfg=self._cfg(restarts=1), factory=factory)
        self.assertEqual(len(created), 1)  # timeout path does not restart

    # ---- AC-11b: the restart path uses a FRESH probe (no orphan lease) ----
    def test_restart_uses_fresh_probe(self):
        created = []

        def factory():
            p = ToolLeaseProbe()
            created.append(p)
            return p

        with self.assertRaises(AgentStuckError):
            self._run("import time; time.sleep(30)",
                      cfg=self._cfg(restarts=1), factory=factory)
        self.assertEqual(len(created), 2)            # one per attempt
        self.assertIsNot(created[0], created[1])     # distinct instances
        self.assertFalse(created[0].active())        # no orphan lease
        self.assertFalse(created[1].active())


class RedactOversizeArgvTests(unittest.TestCase):
    """Stuck diagnostics never persist an oversize argv token (a prompt riding
    argv — the kimi harness); short tokens stay verbatim for actionability."""

    def test_short_tokens_verbatim(self):
        from adapters.monitor import _redact_oversize
        for tok in ("kimi", "--output-format", "stream-json", "-m", "x" * 2048):
            self.assertEqual(_redact_oversize(tok), tok)

    def test_oversize_token_redacted_to_sha256(self):
        import hashlib
        from adapters.monitor import _redact_oversize
        prompt = "--prompt=" + ("governance context " * 200)  # > 2048 bytes
        red = _redact_oversize(prompt)
        self.assertNotIn("governance context", red)
        self.assertIn(f"len={len(prompt)}", red)
        self.assertIn(hashlib.sha256(prompt.encode()).hexdigest(), red)

    def test_diagnostic_argv_file_redacts_prompt(self):
        import hashlib  # noqa: F401 - parity with the unit above
        from adapters.monitor import _record_diagnostic
        d = tempfile.mkdtemp(prefix="mon-diag-")
        prompt = "--prompt=" + ("SECRET governance body " * 200)
        _record_diagnostic(
            MonitorConfig(diagnostics_root=d), None, "dev", "kimi", 1,
            ["kimi", prompt, "--output-format", "stream-json"], None, 12345,
            {"reason": "test"}, [], [])
        sub = os.path.join(d, os.listdir(d)[0])
        with open(os.path.join(sub, "argv.txt"), encoding="utf-8") as fh:
            argv_txt = fh.read()
        self.assertNotIn("SECRET governance body", argv_txt)
        self.assertIn("sha256:", argv_txt)
        self.assertIn("kimi", argv_txt)        # short tokens stay actionable
        self.assertIn("stream-json", argv_txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
