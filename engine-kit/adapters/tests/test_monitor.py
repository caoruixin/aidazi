"""Unit tests for the lightweight adapter subprocess monitor.

No real agent CLI is launched here. Small Python snippets stand in for child
processes so the stuck/restart behavior is deterministic and quick.
"""

import json
import os
import sys
import tempfile
import textwrap
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ADAPTERS_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ADAPTERS_DIR)
if _ENGINE_KIT_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_KIT_DIR)

from adapters.monitor import (  # noqa: E402
    AgentStuckError,
    MonitorConfig,
    run_with_monitor,
)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
