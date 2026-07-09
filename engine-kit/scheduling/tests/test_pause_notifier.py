"""Phase-3 push-not-poll notifier (pause_notifier.py, design §4.2). Offline; drives a
real bounded subprocess. Verifies: default-OFF no-op, fires with env injection, FAIL-SAFE
(exit!=0 / timeout / missing binary never raise), and REDACTED secret-free audit."""
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHED_DIR = os.path.dirname(_TESTS_DIR)
if _SCHED_DIR not in sys.path:
    sys.path.insert(0, _SCHED_DIR)

import pause_notifier as pn  # noqa: E402


def _recorder():
    events = []
    return events, (lambda t, p: events.append((t, p)))


_CTX = {"campaign_id": "camp-1", "reason": "halt_condition_met",
        "checkpoint": "20260620-000005__halt_condition_met__r1.md",
        "milestone_id": "m2", "subsprint_id": "s2"}


class DefaultOff(unittest.TestCase):
    def test_absent_block_is_noop(self):
        events, emit = _recorder()
        self.assertIsNone(pn.notify_on_pause({}, _CTX, emit))
        self.assertIsNone(pn.notify_on_pause({"notifications": {}}, _CTX, emit))
        self.assertEqual(events, [])


class Fires(unittest.TestCase):
    def test_fires_with_env_injection_and_audits(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.txt")
            charter = {"notifications": {"on_pause": [
                "/bin/sh", "-c", f'printf "%s" "$AIDAZI_PAUSE_REASON" > "{out}"']}}
            events, emit = _recorder()
            payload = pn.notify_on_pause(charter, _CTX, emit)
            # subprocess saw the injected env var:
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "halt_condition_met")
            self.assertEqual(payload["exit_code"], 0)
            self.assertFalse(payload["timed_out"])
            # exactly one audit event, REDACTED:
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][0], "campaign_pause_notified")
            p = events[0][1]
            self.assertEqual(p["argv0"], "sh")            # basename only
            self.assertEqual(p["argc"], 3)
            self.assertEqual(len(p["argv_sha256"]), 64)
            self.assertEqual(p["pause_reason"], "halt_condition_met")
            self.assertEqual(p["checkpoint"], _CTX["checkpoint"])
            # NO full argv / env / output body in the audit payload:
            blob = repr(p)
            self.assertNotIn(out, blob)                   # the command string never leaks
            self.assertNotIn("AIDAZI_PAUSE", blob)


class FailSafe(unittest.TestCase):
    def test_nonzero_exit_never_raises(self):
        charter = {"notifications": {"on_pause": ["/bin/sh", "-c", "exit 7"]}}
        events, emit = _recorder()
        payload = pn.notify_on_pause(charter, _CTX, emit)   # must not raise
        self.assertEqual(payload["exit_code"], 7)
        self.assertFalse(payload["timed_out"])
        self.assertEqual(len(events), 1)

    def test_timeout_never_raises(self):
        charter = {"notifications": {"on_pause": ["/bin/sh", "-c", "sleep 30"],
                                     "timeout_seconds": 1}}
        events, emit = _recorder()
        payload = pn.notify_on_pause(charter, _CTX, emit)   # must not raise
        self.assertTrue(payload["timed_out"])
        self.assertIsNone(payload["exit_code"])
        self.assertEqual(len(events), 1)

    def test_missing_binary_never_raises(self):
        charter = {"notifications": {"on_pause": [
            "/nonexistent/aidazi-notify-xyz"]}}
        events, emit = _recorder()
        payload = pn.notify_on_pause(charter, _CTX, emit)   # must not raise
        self.assertIn("error", payload)
        self.assertEqual(len(events), 1)

    def test_audit_failure_never_raises(self):
        charter = {"notifications": {"on_pause": ["/bin/sh", "-c", "exit 0"]}}

        def boom(_t, _p):
            raise RuntimeError("audit ledger unavailable")
        # a broken audit sink must NOT propagate out of the notifier:
        self.assertIsNotNone(pn.notify_on_pause(charter, _CTX, boom))


class TimeoutClamp(unittest.TestCase):
    def test_timeout_is_bounded(self):
        self.assertEqual(pn._bounded_timeout(10), 10)
        self.assertEqual(pn._bounded_timeout(999), 60)     # clamped to max
        self.assertEqual(pn._bounded_timeout(0), 1)        # clamped to min
        self.assertEqual(pn._bounded_timeout("bad"), 10)   # default


if __name__ == "__main__":
    unittest.main()
