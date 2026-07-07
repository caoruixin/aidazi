"""Universal-skill-mounting §4/D3 — run_loop preflight enforcement wiring.

The skills integrity/drift preflight refuses a REAL run DETERMINISTICALLY +
FAIL-CLOSED at both ingress points (campaign ``run_campaign_entry`` + single-loop
``run_loop``), BEFORE any adapter is built; the row-3 gitlink-drift override is
honored ONLY when explicit AND audit-recorded (the event lands on the run's own
hash chain, carrying both commits). Mock/dry runs never invoke the gate.

Run: cd engine-kit && python3.12 -m pytest scheduling/tests/test_skills_preflight_gate.py -q
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHED_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_SCHED_DIR)
for _p in (_SCHED_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator", "tests"),
           os.path.join(_ENGINE_KIT_DIR, "validators"),
           os.path.join(_ENGINE_KIT_DIR, "skill-vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
import run_loop as rl  # noqa: E402
import skills_preflight as sp  # noqa: E402
from test_driver import _acceptance_charter  # noqa: E402
from test_skills_preflight import _mk_framework, _git  # noqa: E402

_GIT = shutil.which("git")
_CLOCK = lambda: "2026-07-06T00:00:00Z"  # noqa: E731 — deterministic test clock


def _tampered_framework(base):
    root = _mk_framework(os.path.join(base, "fw"))
    with open(os.path.join(root, "skills", "vendored", "tdd-mini", "SKILL.md"),
              "a", encoding="utf-8") as fh:
        fh.write("tampered\n")
    return root


def _drifted_submodule(base):
    """A superproject pinning the valid framework fixture as a submodule, whose
    working tree then advanced past the recorded gitlink (the AirPlat class)."""
    fw_src = os.path.join(base, "fw-src")
    os.makedirs(fw_src)
    _mk_framework(fw_src)
    _git(["init", "-q", "-b", "main"], fw_src)
    _git(["add", "-A"], fw_src)
    _git(["commit", "-q", "-m", "framework"], fw_src)
    super_ = os.path.join(base, "adopter")
    os.makedirs(super_)
    _git(["init", "-q", "-b", "main"], super_)
    _git(["-c", "protocol.file.allow=always", "submodule", "add", "-q",
          fw_src, "framework"], super_)
    _git(["commit", "-q", "-m", "pin framework"], super_)
    sub = os.path.join(super_, "framework")
    recorded = _git(["rev-parse", "HEAD"], sub).stdout.strip()
    _git(["commit", "-q", "--allow-empty", "-m", "drift"], sub)
    actual = _git(["rev-parse", "HEAD"], sub).stdout.strip()
    return sub, recorded, actual


def _patch_framework_root(path):
    """Route the preflight's default framework discovery at ``path`` (the wrapper
    passes framework_root=None, so the checker calls find_framework_root())."""
    return mock.patch.object(sp.effective_roles, "find_framework_root",
                             return_value=path)


class WrapperTests(unittest.TestCase):
    def test_clean_real_repo_passes(self):
        # End-to-end honest pass: THIS repo's own vendored skill surface verifies.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rl.enforce_skills_preflight_for_real_run(
                {"tooling": {"dev": {"harness": "mock"}}})

    def test_hard_fail_maps_to_charter_validation_error(self):
        with tempfile.TemporaryDirectory() as d, \
                _patch_framework_root(_tampered_framework(d)):
            with self.assertRaises(rl.CharterValidationError) as cm:
                rl.enforce_skills_preflight_for_real_run({})
        self.assertIn("lock_mismatch", str(cm.exception))

    def test_module_unavailable_fails_closed(self):
        # NEVER dormant: an unavailable checker refuses the real run outright.
        with mock.patch.dict(sys.modules, {"skills_preflight": None}):
            with self.assertRaises(rl.CharterValidationError) as cm:
                rl.enforce_skills_preflight_for_real_run({})
        self.assertIn("unavailable", str(cm.exception))

    def test_warn_findings_print_nonsilently(self):
        warn = sp.Finding(row=4, severity=sp.SEVERITY_WARN,
                          code="pin_behind_upstream", message="behind (test)")
        report = sp.PreflightReport(findings=[warn])
        with mock.patch.object(sp, "enforce_for_real_run", return_value=report):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rl.enforce_skills_preflight_for_real_run({})
        self.assertIn("pin_behind_upstream", buf.getvalue())
        self.assertIn("WARN", buf.getvalue())


@unittest.skipUnless(_GIT, "git binary unavailable")
class AuditedOverrideTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sub, self.recorded, self.actual = _drifted_submodule(self._tmp.name)
        self.ledger = os.path.join(self._tmp.name, "audit", "loop-x.jsonl")

    def _call(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), _patch_framework_root(self.sub):
            rl.enforce_skills_preflight_for_real_run(
                {}, audit_loop_id="loop-x", audit_ledger_path=self.ledger,
                clock=_CLOCK, **kw)
        return buf.getvalue()

    def test_drift_refused_without_override(self):
        with self.assertRaises(rl.CharterValidationError) as cm:
            self._call()
        self.assertIn("gitlink", str(cm.exception))
        self.assertFalse(os.path.exists(self.ledger))   # nothing emitted

    def test_override_without_audit_destination_refused(self):
        with _patch_framework_root(self.sub):
            with self.assertRaises(rl.CharterValidationError) as cm:
                rl.enforce_skills_preflight_for_real_run(
                    {}, allow_gitlink_drift=True)   # no ledger/loop_id/clock
        self.assertIn("cannot be audited", str(cm.exception))
        self.assertFalse(os.path.exists(self.ledger))

    def test_audited_override_emits_chained_event_with_both_commits(self):
        out = self._call(allow_gitlink_drift=True)
        self.assertIn("OVERRIDDEN (audited)", out)
        events = audit.read_events(self.ledger)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["type"], sp.GITLINK_OVERRIDE_EVENT)
        self.assertEqual(ev["loop_id"], "loop-x")
        self.assertEqual(ev["payload"]["recorded_gitlink"], self.recorded)
        self.assertEqual(ev["payload"]["working_tree_commit"], self.actual)
        self.assertEqual(ev["payload"]["override"], "allow_gitlink_drift")
        self.assertTrue(audit.verify_chain(self.ledger).ok)
        # The run's own ledger CONTINUES the chain after the preflight event —
        # exactly what the Driver/campaign appends do next.
        audit.append_event("loop-x", "loop_start", {}, ts=_CLOCK(),
                           path=self.ledger)
        result = audit.verify_chain(self.ledger)
        self.assertTrue(result.ok)
        self.assertEqual(result.count, 2)

    def test_env_var_is_the_explicit_override_too(self):
        with mock.patch.dict(os.environ, {sp.GITLINK_OVERRIDE_ENV: "1"}):
            out = self._call()      # allow_gitlink_drift NOT passed
        self.assertIn("OVERRIDDEN (audited)", out)
        self.assertTrue(audit.verify_chain(self.ledger).ok)


class CampaignEntryGateTests(unittest.TestCase):
    def test_tampered_skills_map_to_invalid_exit(self):
        with tempfile.TemporaryDirectory() as d, \
                _patch_framework_root(_tampered_framework(d)):
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            plan = {"campaign_id": "skillfail", "goal": "x",
                    "signed_by_human": True,
                    "milestones": [{"id": "m1", "objective": "x",
                                    "subsprint_sequence": ["sprint-001"]}]}
            result = rl.run_campaign_entry(
                plan, charter, clock=_CLOCK, allow_real=True, repo_dir=d,
                campaign_run_dir=os.path.join(d, "home"))
        self.assertEqual(result["exit_code"], rl.CAMPAIGN_EXIT_INVALID)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("skills preflight", result["error"])

    def test_mock_dry_run_never_invokes_the_gate(self):
        # allow_real=False (adapters injected) ⇒ the gate must not run at all,
        # even against a tampered tree — mock dry-runs stay byte-identical.
        with tempfile.TemporaryDirectory() as d, \
                _patch_framework_root(_tampered_framework(d)), \
                mock.patch.object(rl, "enforce_skills_preflight_for_real_run",
                                  side_effect=AssertionError("gate ran")) :
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            plan = {"campaign_id": "mockskip", "goal": "x",
                    "signed_by_human": False,
                    "milestones": [{"id": "m1", "objective": "x",
                                    "subsprint_sequence": ["sprint-001"]}]}
            # Unsigned plan pauses at the signoff gate — what matters here is that
            # the preflight mock was never called (no AssertionError).
            result = rl.run_campaign_entry(
                plan, charter, clock=_CLOCK, allow_real=False, adapters={},
                repo_dir=d, campaign_run_dir=os.path.join(d, "home"))
        self.assertNotEqual(result.get("exit_code"), rl.CAMPAIGN_EXIT_ERROR)


class SingleLoopGateTests(unittest.TestCase):
    def test_run_loop_refuses_before_any_adapter_build(self):
        # Isolate THIS gate: no-op the (earlier) charter-schema gate so the test
        # charter fixture's schema leniency can't mask the skills refusal, and trap
        # build_adapters so reaching an adapter build fails the test outright.
        with tempfile.TemporaryDirectory() as d, \
                _patch_framework_root(_tampered_framework(d)), \
                mock.patch.object(rl, "enforce_charter_for_real_run",
                                  return_value=None), \
                mock.patch.object(rl, "build_adapters",
                                  side_effect=AssertionError(
                                      "adapter build reached")):
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            with self.assertRaises(rl.CharterValidationError) as cm:
                rl.run_loop(charter, run_dir=os.path.join(d, "run"),
                            loop_id="lp1", subsprint_id="sprint-001",
                            clock=_CLOCK, allow_real=True)
        self.assertIn("lock_mismatch", str(cm.exception))

    def test_main_maps_refusal_to_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            charter_path = os.path.join(d, "charter.json")
            with open(charter_path, "w", encoding="utf-8") as fh:
                json.dump({"tooling": {"dev": {"harness": "mock"}}}, fh)
            with mock.patch.object(
                    rl, "run_loop",
                    side_effect=rl.CharterValidationError(
                        "skills preflight FAILED (test)")):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = rl.main(["--charter", charter_path,
                                  "--run-dir", os.path.join(d, "run")])
        self.assertEqual(rc, 2)
        self.assertIn("REAL RUN ABORTED", buf.getvalue())
        self.assertIn("skills preflight FAILED (test)", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
