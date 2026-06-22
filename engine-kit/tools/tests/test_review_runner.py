"""Unit tests for the bounded headless review runner (stdlib unittest; no real codex).

Every test drives a SYNTHETIC child (``python -c ...``) so the safety wrapper is exercised
hermetically and fast. The child programs stand in for ``codex exec`` / a Kimi CLI.
"""

import os
import sys
import tempfile
import time
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_TESTS_DIR)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import review_runner as rr  # noqa: E402

PY = sys.executable


def _child(script: str) -> list:
    return [PY, "-c", script]


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False


class StdinClosingTests(unittest.TestCase):
    def test_stdin_prompt_is_delivered_then_eof(self):
        # Child reads ALL of stdin then exits. If stdin were left open it would hang -> timeout.
        rec = rr.run_once(
            _child("import sys; d=sys.stdin.read(); print('got', len(d)); sys.stdout.flush()"),
            prompt="hello", prompt_delivery="stdin", hard_timeout_s=10,
        )
        self.assertEqual(rec.outcome, rr.SUCCESS, msg=rec.note)
        self.assertFalse(rec.timed_out)
        self.assertIn("got 5", getattr(rec, "_stdout", ""))

    def test_devnull_stdin_gives_immediate_eof(self):
        rec = rr.run_once(
            _child("import sys; d=sys.stdin.read(); print('got', len(d)); sys.stdout.flush()"),
            prompt=None, prompt_delivery="none", hard_timeout_s=10,
        )
        self.assertEqual(rec.outcome, rr.SUCCESS, msg=rec.note)
        self.assertIn("got 0", getattr(rec, "_stdout", ""))


class ExitCodeTests(unittest.TestCase):
    def test_success(self):
        rec = rr.run_once(_child("print('ok')"), prompt_delivery="none", hard_timeout_s=10)
        self.assertEqual(rec.outcome, rr.SUCCESS)
        self.assertEqual(rec.exit_code, 0)

    def test_nonzero_exit(self):
        rec = rr.run_once(_child("import sys; sys.exit(7)"),
                          prompt_delivery="none", hard_timeout_s=10)
        self.assertEqual(rec.outcome, rr.NONZERO_EXIT)
        self.assertEqual(rec.exit_code, 7)
        self.assertFalse(rec.timed_out)

    def test_launch_error_on_missing_binary(self):
        rec = rr.run_once(["/nonexistent/definitely-not-a-binary-xyz"],
                          prompt_delivery="none", hard_timeout_s=5)
        self.assertEqual(rec.outcome, rr.LAUNCH_ERROR)
        self.assertIsNone(rec.exit_code)


class CaptureTests(unittest.TestCase):
    def test_stdout_and_stderr_captured(self):
        rec = rr.run_once(
            _child("import sys; print('to-out'); print('to-err', file=sys.stderr)"),
            prompt_delivery="none", hard_timeout_s=10,
        )
        self.assertIn("to-out", getattr(rec, "_stdout", ""))
        self.assertIn("to-err", getattr(rec, "_stderr", ""))
        self.assertGreater(rec.stdout_bytes, 0)
        self.assertGreater(rec.stderr_bytes, 0)


class HardTimeoutTests(unittest.TestCase):
    def test_hard_timeout_kills(self):
        start = time.monotonic()
        rec = rr.run_once(_child("import time; time.sleep(30)"),
                          prompt_delivery="none", hard_timeout_s=1.0)
        elapsed = time.monotonic() - start
        self.assertEqual(rec.outcome, rr.TIMEOUT)
        self.assertTrue(rec.timed_out)
        self.assertLess(elapsed, 10, msg="hard timeout must bound wall-clock")

    def test_process_group_is_killed(self):
        # Child writes a grandchild PID then both sleep; the timeout must kill the WHOLE group.
        pidfile = tempfile.NamedTemporaryFile("w", suffix=".pid", delete=False)
        pidfile.close()
        self.addCleanup(lambda: os.path.exists(pidfile.name) and os.unlink(pidfile.name))
        script = (
            "import subprocess, time, sys;"
            f"p=subprocess.Popen([{PY!r}, '-c', 'import time; time.sleep(60)']);"
            f"open({pidfile.name!r}, 'w').write(str(p.pid));"
            "sys.stdout.write('spawned\\n'); sys.stdout.flush();"
            "time.sleep(60)"
        )
        rec = rr.run_once(_child(script), prompt_delivery="none", hard_timeout_s=1.5)
        self.assertTrue(rec.timed_out)
        # Give the OS a beat to reap the killed group, then assert the grandchild is gone.
        time.sleep(0.5)
        with open(pidfile.name) as fh:
            grandchild_pid = int(fh.read().strip())
        self.assertFalse(_pid_alive(grandchild_pid),
                         msg=f"grandchild {grandchild_pid} survived the group kill")


class GrandchildLeakTests(unittest.TestCase):
    def test_grandchild_holding_pipes_after_leader_exit_is_reaped(self):
        # Leader spawns a grandchild that INHERITS the stdout pipe, then exits 0 immediately.
        # Without a saved-pgid group kill, the reader would block on the still-open pipe and the
        # grandchild would leak. The runner must reap the whole group and return promptly.
        pidfile = tempfile.NamedTemporaryFile("w", suffix=".pid", delete=False)
        pidfile.close()
        self.addCleanup(lambda: os.path.exists(pidfile.name) and os.unlink(pidfile.name))
        script = (
            "import subprocess, sys;"
            f"p=subprocess.Popen([{PY!r}, '-c', 'import time; time.sleep(60)']);"  # inherits fd1
            f"open({pidfile.name!r}, 'w').write(str(p.pid));"
            "sys.stdout.write('leader-exit\\n'); sys.stdout.flush();"
            "sys.exit(0)"
        )
        start = time.monotonic()
        rec = rr.run_once(_child(script), prompt_delivery="none", hard_timeout_s=30)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 15, msg="leader-exit with a pipe-holding grandchild must not hang")
        time.sleep(0.5)
        with open(pidfile.name) as fh:
            grandchild_pid = int(fh.read().strip())
        self.assertFalse(_pid_alive(grandchild_pid),
                         msg=f"grandchild {grandchild_pid} leaked after leader exit")


class BlockedStdinWriteTests(unittest.TestCase):
    def test_large_prompt_to_non_reading_child_still_times_out(self):
        # A large prompt to a child that never drains stdin would block write() past the pipe
        # buffer. The hard timeout MUST still fire (the write runs in a daemon thread).
        big = "x" * 500_000  # well past a 64 KiB pipe buffer
        start = time.monotonic()
        rec = rr.run_once(_child("import time; time.sleep(30)"),
                          prompt=big, prompt_delivery="stdin", hard_timeout_s=2.0)
        elapsed = time.monotonic() - start
        self.assertTrue(rec.timed_out)
        self.assertLess(elapsed, 12, msg="a blocked stdin write must not defeat the hard timeout")

    def test_blocked_write_closes_stdin_no_resource_warning(self):
        # The daemon writer must close stdin even when write() raises on the kill, so no
        # unclosed-pipe ResourceWarning leaks (closed in a finally).
        import gc
        import warnings
        big = "x" * 500_000
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            rec = rr.run_once(_child("import time; time.sleep(30)"),
                              prompt=big, prompt_delivery="stdin", hard_timeout_s=1.5)
            time.sleep(0.3)  # let the daemon writer unblock + close after the kill
            gc.collect()
        self.assertTrue(rec.timed_out)


class SplitCommandTests(unittest.TestCase):
    def test_double_dash_in_command_kept_without_allow_alternative(self):
        runner, cmd, alt = rr._split_command(
            ["--timeout", "5", "--", "cmd", "arg", "--", "x"])
        self.assertEqual(runner, ["--timeout", "5"])
        self.assertEqual(cmd, ["cmd", "arg", "--", "x"])  # the command's own `--` is preserved
        self.assertEqual(alt, [])

    def test_second_dash_is_alternative_only_with_flag(self):
        runner, cmd, alt = rr._split_command(
            ["--allow-alternative", "--", "cmd", "--", "altcmd"])
        self.assertEqual(cmd, ["cmd"])
        self.assertEqual(alt, ["altcmd"])


class IdenticalAlternativeTests(unittest.TestCase):
    def test_run_bounded_rejects_identical_alternative(self):
        argv = _child("import sys; sys.exit(1)")
        with self.assertRaises(ValueError):
            rr.run_bounded(argv, prompt_delivery="none", hard_timeout_s=5,
                           attempts=2, alternative_argv=list(argv))

    def test_cli_rejects_identical_alternative(self):
        with self.assertRaises(SystemExit):
            rr.main(["--timeout", "5", "--no-stdin", "--allow-alternative",
                     "--", PY, "-c", "import sys;sys.exit(1)",
                     "--", PY, "-c", "import sys;sys.exit(1)"])


class InactivityWarningTests(unittest.TestCase):
    def test_inactivity_warns_but_does_not_kill(self):
        # Emit one line, go quiet past the inactivity window, then exit cleanly under the
        # hard timeout. Expect a warning recorded, NOT a kill.
        rec = rr.run_once(
            _child("import time,sys; print('event'); sys.stdout.flush(); time.sleep(0.8)"),
            prompt_delivery="none", hard_timeout_s=5.0, inactivity_warn_s=0.3,
        )
        self.assertEqual(rec.outcome, rr.SUCCESS, msg=rec.note)
        self.assertFalse(rec.timed_out)
        self.assertGreaterEqual(rec.inactivity_warnings, 1)


class BoundedRetryTests(unittest.TestCase):
    def test_two_attempts_then_failed(self):
        result = rr.run_bounded(
            _child("import time; time.sleep(30)"), prompt_delivery="none",
            hard_timeout_s=0.8, attempts=2,
        )
        self.assertEqual(len(result.attempts), 2)
        self.assertTrue(all(a.outcome == rr.TIMEOUT for a in result.attempts))
        self.assertEqual(result.status, rr.STATUS_FAILED)

    def test_attempts_capped_at_two(self):
        result = rr.run_bounded(
            _child("import sys; sys.exit(1)"), prompt_delivery="none",
            hard_timeout_s=5, attempts=5,  # asks for 5
        )
        self.assertEqual(len(result.attempts), rr.MAX_ATTEMPTS_CAP)  # capped

    def test_first_failure_is_recorded_not_hidden(self):
        result = rr.run_bounded(
            _child("import os,sys; sys.exit(0 if os.path.exists('/no/such') else 1)"),
            prompt_delivery="none", hard_timeout_s=5, attempts=2,
        )
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(result.attempts[0].attempt, 1)
        self.assertEqual(result.attempts[0].outcome, rr.NONZERO_EXIT)

    def test_stops_at_first_success(self):
        result = rr.run_bounded(_child("print('ok')"), prompt_delivery="none",
                                hard_timeout_s=5, attempts=2)
        self.assertEqual(result.status, rr.STATUS_SUCCESS)
        self.assertEqual(len(result.attempts), 1)  # did not run a second time


class MandatoryGateTests(unittest.TestCase):
    def test_mandatory_failure_is_stop_and_surface_not_skipped(self):
        result = rr.run_bounded(
            _child("import sys; sys.exit(2)"), prompt_delivery="none",
            hard_timeout_s=5, attempts=2, mandatory=True,
        )
        self.assertEqual(result.status, rr.STATUS_STOP_AND_SURFACE)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.attempts), 2)

    def test_alternative_used_only_when_allowed_and_recorded(self):
        result = rr.run_bounded(
            _child("import sys; sys.exit(1)"), prompt_delivery="none",
            hard_timeout_s=5, attempts=2, mandatory=True,
            alternative_argv=_child("print('alt-verdict')"),
        )
        self.assertEqual(result.status, rr.STATUS_SUBSTITUTED)
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.substituted_with)
        self.assertIn("alt-verdict", result.stdout)
        # primary attempts + one alternative attempt all recorded
        self.assertEqual(len(result.attempts), 3)


class CliTests(unittest.TestCase):
    def test_cli_success_exit_zero(self):
        rc = rr.main(["--timeout", "10", "--no-stdin", "--", PY, "-c", "print('hi')"])
        self.assertEqual(rc, 0)

    def test_cli_mandatory_failure_exits_three(self):
        rc = rr.main(["--timeout", "5", "--no-stdin", "--mandatory", "--attempts", "2",
                      "--", PY, "-c", "import sys; sys.exit(1)"])
        self.assertEqual(rc, 3)  # stop_and_surface, distinct from generic failure

    def test_cli_nonmandatory_failure_exits_one(self):
        rc = rr.main(["--timeout", "5", "--no-stdin", "--",
                      PY, "-c", "import sys; sys.exit(1)"])
        self.assertEqual(rc, 1)

    def test_cli_prompt_file_delivered_on_stdin(self):
        pf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        pf.write("PROMPTBODY")
        pf.close()
        self.addCleanup(os.unlink, pf.name)
        cap = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(cap, ignore_errors=True))
        rc = rr.main(["--timeout", "10", "--prompt-file", pf.name, "--capture-dir", cap,
                      "--", PY, "-c",
                      "import sys; d=sys.stdin.read(); print('len', len(d)); sys.stdout.flush()"])
        self.assertEqual(rc, 0)
        with open(os.path.join(cap, "stdout.txt")) as fh:
            self.assertIn("len 10", fh.read())
        self.assertTrue(os.path.exists(os.path.join(cap, "attempts.json")))

    def test_cli_double_dash_without_flag_is_part_of_command(self):
        # Without --allow-alternative, a second `--` is NOT an alternative separator — the whole
        # tail is the command (which here just runs and exits 1), not a usage error.
        rc = rr.main(["--timeout", "5", "--no-stdin", "--", PY, "-c", "import sys;sys.exit(1)",
                      "--", "extra-arg"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
