"""Phase-5 REAL managed external_test_runner canary (design §9 non-regression canaries).

Exercises the REAL env-gated path (``AIDAZI_E2E_EXTERNAL_RUNNER=1``) end-to-end through the NORMAL
driver route: managed app start -> real Node/Playwright runner (REAL chromium) -> framework-owned
provenance -> criterion evaluation -> §1.7-G autonomous remediation -> full authoritative rerun ->
re-judge -> the #9 HUMAN ship gate.

Discipline (Phase-5 boundaries): NO executor internals are called directly; NO manifest is injected
to PASS a gate; NO authoritative provenance is mocked (run-provenance.json is framework-generated
from the REAL subprocess and verified fail-closed); the loop is not bypassed (the real
`_run_e2e_evidence` -> `_commit_e2e` -> `_run_e2e_remediation_lane` -> `_run_acceptance` route runs).
The two DETERMINISTIC seams a canary must supply — the Dev "fix" (an in-envelope file edit standing
in for a Dev agent's code change) and the Acceptance judge (reads the REAL committed evidence) — are
the only simulated pieces; every authoritative decision (execution, provenance, criterion mapping,
containment, budget, rerun, the #9 gate) is real framework code.

SKIPPED unless ``AIDAZI_E2E_EXTERNAL_RUNNER=1`` AND a usable node + cached-playwright toolchain whose
chromium build is installed — it never runs in offline CI.

Run: AIDAZI_E2E_EXTERNAL_RUNNER=1 python3.12 -m pytest orchestrator/tests/test_e2e_real_canary.py -q
"""
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
_REPO = os.path.dirname(_ENGINE_KIT_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling"),
           os.path.join(_ENGINE_KIT_DIR, "validators")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
import campaign as cp  # noqa: E402
import driver as D  # noqa: E402
import loop_ingress as li  # noqa: E402
from adapters import MockAdapter  # noqa: E402
from test_driver import _acceptance_charter, _acceptance_adapters  # noqa: E402
from test_e2e_acceptance import _checkpoints  # noqa: E402  (run_dir/docs/checkpoints reader)

_CANARY_SRC = os.path.join(_REPO, "examples", "native-e2e-canary")
_BROWSER_CACHE = os.path.expanduser("~/Library/Caches/ms-playwright")


# --------------------------------------------------------------------------- #
# Toolchain resolution — find a cached `playwright` whose chromium build is installed.
# --------------------------------------------------------------------------- #
def _installed_chromium_revs() -> set:
    revs = set()
    if os.path.isdir(_BROWSER_CACHE):
        for name in os.listdir(_BROWSER_CACHE):
            if name.startswith("chromium-"):
                revs.add(name.split("-", 1)[1])
    return revs


def resolve_playwright() -> "dict | None":
    """A cached ``playwright`` (+ playwright-core) whose chromium revision is installed, so a REAL
    headless launch works offline. None ⇒ the canary skips."""
    if not shutil.which("node"):
        return None
    installed = _installed_chromium_revs()
    for pw in sorted(glob.glob(os.path.expanduser(
            "~/.npm/_npx/*/node_modules/playwright"))):
        core = os.path.join(os.path.dirname(pw), "playwright-core")
        bj = os.path.join(core, "browsers.json")
        if not os.path.isfile(bj):
            continue
        try:
            with open(bj, encoding="utf-8") as fh:
                browsers = json.load(fh).get("browsers", [])
        except (OSError, ValueError):
            continue
        rev = next((b.get("revision") for b in browsers
                    if b.get("name") == "chromium"), None)
        if rev and str(rev) in installed:
            return {"playwright": pw, "playwright_core": core}
    return None


_PLAYWRIGHT = resolve_playwright()


def _skip_reason() -> "str | None":
    if os.environ.get("AIDAZI_E2E_EXTERNAL_RUNNER") != "1":
        return "canary is env-gated (set AIDAZI_E2E_EXTERNAL_RUNNER=1)"
    if _PLAYWRIGHT is None:
        return "no cached playwright with an installed chromium build"
    return None


def _iso_clock():
    """Microsecond-precision UTC ISO clock (matches the executor's wall_clock so the driver
    e2e_start/end window brackets the real runner wall-clock — the freshness gate is exercised for
    real, not defeated by second-precision truncation)."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


_CRITERIA = [
    {"criterion_id": "home_loads", "criterion": "home page loads", "critical": True,
     "req_id": "REQ-1", "module": "app", "layer": "ui"},
    {"criterion_id": "result_ok", "criterion": "result page shows OK", "critical": True,
     "req_id": "REQ-1", "module": "app", "layer": "ui"},
]


@unittest.skipIf(_skip_reason(), _skip_reason() or "")
class RealCanary(unittest.TestCase):
    """The design §9 canaries over the REAL managed external_test_runner path."""

    # ---- workspace: an aidazi-owned scratch fixture adopter (git repo + real app + runner) ---- #
    def _workspace(self, tmp, *, fixed: bool, max_rounds: int = 2,
                   enabled: bool = True, extra_criteria=None, criterion_map_full=True):
        run_dir = tmp
        repo = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(repo, "app"))
        os.makedirs(os.path.join(repo, "e2e"))
        shutil.copy(os.path.join(_CANARY_SRC, "app", "server.py"),
                    os.path.join(repo, "app", "server.py"))
        shutil.copy(os.path.join(_CANARY_SRC, "e2e", "runner.cjs"),
                    os.path.join(repo, "e2e", "runner.cjs"))
        # node_modules symlinks so the runner resolves `require('playwright')` OFFLINE.
        nm = os.path.join(repo, "node_modules")
        os.makedirs(nm)
        os.symlink(_PLAYWRIGHT["playwright"], os.path.join(nm, "playwright"))
        os.symlink(_PLAYWRIGHT["playwright_core"], os.path.join(nm, "playwright-core"))
        # keep evidence + browser artifacts OUT of the observed diff (only app/ is in-envelope).
        with open(os.path.join(repo, ".gitignore"), "w", encoding="utf-8") as fh:
            fh.write("node_modules/\ntest-results/\n*.log\n.orchestrator/\n")
        if fixed:
            with open(os.path.join(repo, "app", "fixed.flag"), "w", encoding="utf-8") as fh:
                fh.write("fixed\n")
        for args in (["init", "-q"], ["config", "user.email", "c@c"],
                     ["config", "user.name", "canary"], ["add", "-A"],
                     ["commit", "-qm", "base"]):
            subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)

        criteria = list(_CRITERIA) + list(extra_criteria or [])
        charter = self._charter(repo, max_rounds, enabled, criteria, criterion_map_full)
        checklist = {"checklist_id": "canary-fc", "signed_by_human": True, "criteria": criteria}
        with open(os.path.join(run_dir, "checklist.json"), "w", encoding="utf-8") as fh:
            json.dump(checklist, fh)
        self._write_contexts(run_dir, charter)
        drv = D.Driver(charter, run_dir, self._adapters(run_dir),
                       loop_id="loop-canary", clock=_iso_clock,
                       context={"allow_real": True})
        drv.state = D.RunState(loop_id="loop-canary", subsprint_id="sprint-001")
        drv.context_handle = li.ContextHandle(
            work_dir=repo, branch="main", strategy=li.STRATEGY_CURRENT_BRANCH,
            repo_dir=repo, created=False, base_ref=None)
        return drv, repo, run_dir

    def _charter(self, repo, max_rounds, enabled, criteria, criterion_map_full):
        ch = _acceptance_charter(level="human_on_the_loop", mode="advisory")
        # a SIGNED intent contract so the Acceptance prompt resolves + the judge runs to the #9 gate.
        ch["intent_contract"] = {
            "goal": "user loads the page and sees OK",
            "standard": "the home + result pages render OK on the happy path",
            "proof_of_done": "browser_e2e criteria home_loads + result_ok pass on real evidence",
            "confirmed_by_human": True}
        ch["autonomy"]["approved_scope"]["modules_in_scope"] = ["app", "e2e"]
        ch["autonomy"]["approved_scope"]["layers_allowed"] = ["ui"]
        if enabled:
            ch["autonomy"]["e2e_remediation"] = {
                "enabled": True, "max_rounds": max_rounds, "max_no_progress_rounds": 1}
        cmap = {f"@crit:{c['criterion_id']}": c["criterion_id"] for c in criteria} \
            if criterion_map_full else {}
        ch["tooling"]["e2e"] = {
            "executor_kind": "external_test_runner",
            "runner_argv": ["node", "e2e/runner.cjs"],
            "spec_path": "e2e/runner.cjs",
            "criterion_map": cmap,
            "app_start_cmd": [sys.executable, "app/server.py", "--port", "{port}",
                              "--flag", "app/fixed.flag"],
            "readiness": {"url": "/__health", "timeout_seconds": 20},
            "base_url": "http://127.0.0.1", "allowed_origins": ["http://127.0.0.1"],
            "shutdown": {"process_owned": True},
            "cwd": repo,
            "timeouts": {"total_seconds": 120},
        }
        ch["tooling"]["acceptance"]["functional"] = {
            "mode": "browser_e2e", "interaction_mode": "deterministic",
            "checklist_path": "checklist.json"}
        return ch

    def _write_contexts(self, run_dir, charter):
        """The per-unit campaign provenance the §1.7-G containment reads: an AUTHENTIC signed plan
        snapshot (stamp_signoff — NOT mocked) + the unique milestone_id sidecar."""
        plan = {"campaign_id": "canary", "goal": "canary",
                "milestones": [{"id": "m1", "objective": "ship the page",
                                "subsprint_sequence": ["sprint-001"],
                                "covers_req_ids": ["REQ-1"]}]}
        signed = cp.stamp_signoff(plan, charter, charter_ref="charter.json")
        with open(os.path.join(run_dir, "requirement-context.json"), "w", encoding="utf-8") as fh:
            json.dump({"plan": signed}, fh)
        with open(os.path.join(run_dir, "derived-context.json"), "w", encoding="utf-8") as fh:
            json.dump({"kind": "per_milestone_execution_context", "milestone_id": "m1"}, fh)

    # ---- deterministic seams: Dev fix (in-envelope) + Acceptance judge (real evidence) -------- #
    def _adapters(self, run_dir):
        adapters = _acceptance_adapters()
        adapters["acceptance"] = MockAdapter(
            {("acceptance",): self._judge(run_dir)},
            harness="claude_code", provider="anthropic", model="claude-opus-4-8")
        return adapters

    def _judge(self, run_dir):
        """A judge that reads the REAL committed manifest + checklist-results.json and returns a
        verdict citing the REAL, hashed evidence (never fabricates a pass out of thin air)."""
        import re

        def _mk(role, prompt, schema):
            prefix = re.search(r"\.orchestrator/audit/browser/[^\s`]+/r[0-9a-f]+",
                               prompt).group(0)
            manifest = json.load(open(os.path.join(run_dir, prefix, "manifest.json")))
            by_name = {a["name"]: a["sha256"] for a in manifest["artifacts"]}
            cr = by_name["checklist-results.json"]
            rows = json.load(open(os.path.join(run_dir, prefix, "checklist-results.json")))
            cases = [{
                "case_id": r["criterion_id"], "criterion_id": r["criterion_id"],
                "criterion": r.get("criterion") or r["criterion_id"], "verdict": "pass",
                "rationale": "observed the criterion pass in the captured evidence",
                "functional_evidence_refs": [{
                    "kind": "checklist", "path": f"{prefix}/checklist-results.json",
                    "sha256": cr}],
            } for r in rows]
            return {"milestone_verdict": "pass", "acceptance_class": "browser_e2e",
                    "cases": cases, "suggested_route": "n/a"}
        return _mk

    def _dev_fix(self, drv, repo):
        """Patch the Dev-spawn seam so a §1.7-G remediation round writes the IN-ENVELOPE fix
        (app/fixed.flag) — the deterministic stand-in for a Dev agent's code change. Only the lane
        calls _step_dev on this entry, so this fires only during autonomous remediation."""
        def _fix():
            with open(os.path.join(repo, "app", "fixed.flag"), "w", encoding="utf-8") as fh:
                fh.write("fixed by §1.7-G\n")
        drv._step_dev = _fix
        drv._step_gate = lambda: None

    def _drive_e2e(self, drv):
        """Drive the REAL milestone-close E2E route (the driver's STATE_E2E_PENDING entry:
        _run_e2e_evidence -> real _commit_e2e -> real §1.7-G lane -> real _run_acceptance -> #9).
        A #9 advisory-ship or #8 integrity halt manifests as STATE_HALTED (captured; never
        auto-ships)."""
        try:
            drv._run_e2e_evidence()
        except D.GateHardFail:
            pass
        return drv.state

    def _events(self, drv):
        return [e["type"] for e in audit.read_events(drv.audit_ledger)] \
            if os.path.isfile(drv.audit_ledger) else []

    def _final_manifest(self, drv):
        rid = drv._e2e_run_id()
        return json.load(open(os.path.join(drv._e2e_final_dir(rid), "manifest.json")))

    # ------------------------------------------------------------------ canaries #
    def test_1_real_managed_happy_path(self):
        """Real app start -> real chromium runner -> real provenance verified -> pass -> #9 HUMAN
        ship gate (never auto-ships). A concrete real-browser artifact (trace.zip / screenshot) is
        in the committed manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            drv, repo, run_dir = self._workspace(tmp, fixed=True)
            final = self._drive_e2e(drv)
            self.assertEqual(final.state, D.STATE_HALTED)            # #9 advisory ship halt
            evs = self._events(drv)
            self.assertIn("dev_self_smoke_subsumed", evs)           # §6b subsumed (no manual gate)
            self.assertIn("acceptance_pending", drv.state.history)
            # real provenance verified (never a reject) + a concrete real-browser artifact committed.
            self.assertNotIn("e2e_reconcile_provenance_reject", evs)
            names = [a["name"] for a in self._final_manifest(drv)["artifacts"]]
            self.assertTrue(any(n.endswith((".zip", ".png")) for n in names), names)
            self.assertIn("run-provenance.json", names)
            # the framework verified the REAL execution window (start/end events on the Spine).
            self.assertIn(D.e2e_stage.E2E_START_EVENT_TYPE, evs)
            self.assertIn(D.e2e_stage.E2E_END_EVENT_TYPE, evs)
            self.assertEqual(drv.state.e2e_remediation_round, 0)    # no remediation on happy path
            # the full real chain completed to the HUMAN ship gate (judged pass, not auto-shipped).
            self.assertIn("advisory_acceptance_pass_signoff", _checkpoints(run_dir))

    def test_2_deterministic_fail_then_autonomous_remediation(self):
        """result_ok fails on the first REAL run (BROKEN page); §1.7-G autonomously fixes in
        envelope, RE-RUNS the real managed runner, the criterion now passes on fresh real evidence,
        re-judge -> #9. Fully autonomous (no human command / evidence hauling / manual resume)."""
        with tempfile.TemporaryDirectory() as tmp:
            drv, repo, run_dir = self._workspace(tmp, fixed=False, max_rounds=2)
            self._dev_fix(drv, repo)
            final = self._drive_e2e(drv)
            self.assertEqual(final.state, D.STATE_HALTED)           # ends at the #9 human gate
            evs = self._events(drv)
            self.assertIn("e2e_remediation_round_dispatch", evs)    # autonomous remediation ran
            self.assertIn("e2e_remediation_resolved", evs)          # remediated to all-pass
            self.assertGreaterEqual(drv.state.e2e_remediation_round, 1)
            # the fix flag was written (in-envelope) + the app now serves the fixed page.
            self.assertTrue(os.path.isfile(os.path.join(repo, "app", "fixed.flag")))
            # re-judge on the fresh rerun reached the HUMAN ship gate (remediated pass, autonomous).
            self.assertIn("advisory_acceptance_pass_signoff", _checkpoints(run_dir))
            self.assertNotIn("e2e_reconcile_provenance_reject", evs)  # every round: real provenance

    def test_3_dry_run_and_tampered_evidence_rejected(self):
        """Fail-closed evidence gates on the REAL path: (a) a local_http DRY-RUN manifest cannot
        route to a browser_e2e verdict; (b) a TAMPERED (hand-authored) run-provenance is not
        trusted — the framework re-runs rather than accepting it."""
        # (a) dry-run cannot route
        with tempfile.TemporaryDirectory() as tmp:
            drv, repo, run_dir = self._workspace(tmp, fixed=True)
            drv.charter["tooling"]["e2e"] = {
                "executor_kind": "local_http", "readiness": {"url": "/", "timeout_seconds": 5},
                "base_url": "http://127.0.0.1", "allowed_origins": ["http://127.0.0.1"],
                "journeys": [{"id": "j", "steps": [{"action": "navigate", "url": "/"}]}]}
            drv.state.state = D.STATE_E2E_PENDING
            with self.assertRaises(D.GateHardFail) as cm:
                drv._commit_e2e()
            self.assertIn("dry-run", str(cm.exception))
        # (b) tampered provenance ⇒ not trusted (re-run; the bogus nonce never routes)
        with tempfile.TemporaryDirectory() as tmp:
            drv, repo, run_dir = self._workspace(tmp, fixed=True)
            drv.state.state = D.STATE_E2E_PENDING
            drv._commit_e2e()                                   # a real committed run
            rid = drv._e2e_run_id()
            prov_path = os.path.join(drv._e2e_final_dir(rid), "run-provenance.json")
            prov = json.load(open(prov_path))
            prov["invocation_nonce"] = "hand-authored-bogus-nonce"   # tamper
            with open(prov_path, "w", encoding="utf-8") as fh:
                json.dump(prov, fh)
            # clear the cache so the driver RE-RECONCILES the (now tampered) committed dir.
            drv.state.e2e_evidence_ref = None
            drv.state.e2e_manifest_hash = None
            drv._commit_e2e()                                   # must NOT trust the tampered dir
            after = json.load(open(prov_path))
            self.assertNotEqual(after.get("invocation_nonce"), "hand-authored-bogus-nonce")

    def test_4_unmapped_criterion_and_runner_contract_fault(self):
        """A signed criterion with NO mapped test ⇒ pre-publication runner-contract HALT; a runner
        that cannot run ⇒ fail-closed gate_hard_fail (never a fake pass)."""
        # unmapped criterion (the runner produces no test for it)
        with tempfile.TemporaryDirectory() as tmp:
            drv, repo, run_dir = self._workspace(tmp, fixed=True, extra_criteria=[
                {"criterion_id": "never_tested", "criterion": "has no bound test",
                 "critical": True, "req_id": "REQ-1", "module": "app", "layer": "ui"}])
            drv.state.state = D.STATE_E2E_PENDING
            with self.assertRaises(D.GateHardFail) as cm:
                drv._commit_e2e()
            self.assertIn("unmapped", str(cm.exception))
            self.assertIn("never_tested", str(cm.exception))
        # runner-contract fault (missing runner script ⇒ no report ⇒ fail-closed)
        with tempfile.TemporaryDirectory() as tmp:
            drv, repo, run_dir = self._workspace(tmp, fixed=True)
            drv.charter["tooling"]["e2e"]["runner_argv"] = ["node", "e2e/does-not-exist.cjs"]
            drv.state.state = D.STATE_E2E_PENDING
            with self.assertRaises(D.GateHardFail):
                drv._commit_e2e()

    def test_5_no_progress_halt_never_ships(self):
        """A §1.7-G round whose Dev fix makes NO progress (the failing set does not strictly shrink)
        HALTs + escalates fail-closed — it never loops and never reaches the #9 ship gate
        autonomously."""
        with tempfile.TemporaryDirectory() as tmp:
            drv, repo, run_dir = self._workspace(tmp, fixed=False, max_rounds=3)
            drv._step_dev = lambda: None                        # a Dev "fix" that changes nothing
            drv._step_gate = lambda: None
            final = self._drive_e2e(drv)
            evs = self._events(drv)
            self.assertIn("e2e_remediation_halt", evs)
            self.assertEqual(final.state, D.STATE_HALTED)
            # NEVER shipped autonomously: no acceptance verdict routed past the halt.
            self.assertNotIn("acceptance_pending", drv.state.history)

    def test_6_crash_resume_is_idempotent(self):
        """After a committed real run, a crash BEFORE routing resumes deterministically: the
        reconcile trusts the framework-owned committed evidence (matching nonce + Spine events) and
        does NOT re-execute the runner — no duplicate run."""
        with tempfile.TemporaryDirectory() as tmp:
            drv, repo, run_dir = self._workspace(tmp, fixed=True)
            drv.state.state = D.STATE_E2E_PENDING
            drv._commit_e2e()                                   # first real run (commits + events)
            rid = drv._e2e_run_id()
            prov1 = json.load(open(os.path.join(drv._e2e_final_dir(rid), "run-provenance.json")))
            start_events_1 = self._events(drv).count(D.e2e_stage.E2E_START_EVENT_TYPE)
            # simulate a crash after commit / before routing: drop the in-memory cache, resume.
            drv.state.e2e_evidence_ref = None
            drv.state.e2e_manifest_hash = None
            drv._commit_e2e()                                   # reconcile — must NOT re-run
            prov2 = json.load(open(os.path.join(drv._e2e_final_dir(rid), "run-provenance.json")))
            start_events_2 = self._events(drv).count(D.e2e_stage.E2E_START_EVENT_TYPE)
            self.assertEqual(prov1["invocation_nonce"], prov2["invocation_nonce"])  # same evidence
            self.assertEqual(prov1["pid"], prov2["pid"])        # NOT a fresh subprocess
            self.assertEqual(start_events_1, start_events_2)    # no duplicate e2e_start

    def test_7_final_ship_is_human_authorized(self):
        """A PASSING browser_e2e verdict does NOT auto-ship: it halts at the #9
        advisory_acceptance_pass_signoff human gate (M3 stays advisory)."""
        with tempfile.TemporaryDirectory() as tmp:
            drv, repo, run_dir = self._workspace(tmp, fixed=True)
            final = self._drive_e2e(drv)
            self.assertEqual(final.state, D.STATE_HALTED)       # NOT STATE_DONE (never auto-ships)
            self.assertNotEqual(final.state, D.STATE_DONE)
            # the #9 advisory_acceptance_pass_signoff checkpoint fires ONLY on a PASS verdict — its
            # presence proves the pass was HUMAN-gated (never auto-shipped).
            self.assertIn("advisory_acceptance_pass_signoff", _checkpoints(run_dir))
            self.assertIn("acceptance_pending", drv.state.history)  # judged, then gated


if __name__ == "__main__":
    unittest.main()
