"""Maintained, offline E2E tests for the P-C browser-E2E acceptance gate (design §8).

These drive the REAL Driver (MockAdapter judge) through the browser-E2E stage against
the deterministic LocalHttpExecutor + the stdlib fixture app — NO billed LLM, NO
internet, NO real browser. They prove the fail-closed machinery end-to-end: evidence
capture + commit, the audit anchor, the §3.2 consistency gate (a captured failure can
never become PASS), the §3.5a/b commit/resume idempotency, the M3 advisory→human gate,
and the §6a Dev self-smoke gate. The Playwright path is never exercised here (§7/§10).
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling"),
           os.path.join(_ENGINE_KIT_DIR, "validators")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
import driver as D  # noqa: E402
from adapters import MockAdapter  # noqa: E402
from test_driver import (  # noqa: E402  (reuse the real charter + MockAdapters + driver)
    _acceptance_charter, _acceptance_adapters, _driver)

_FIX = os.path.join(_TESTS_DIR, "fixtures", "e2e_app", "__main__.py")

# Full journey covering 6 criteria; the fixture's MODE makes a specific criterion fail.
_JOURNEY = [{
    "id": "submit-and-verify",
    "steps": [
        {"action": "navigate", "id": "open", "url": "/",
         "criterion_id": "C1_form_loads", "critical": True},
        {"action": "assert_selector", "selector": "#submit-btn",
         "criterion_id": "C1_form_loads", "critical": True},
        {"action": "fill", "selector": "#name-input", "value": "Rex",
         "criterion_id": "C2_submit_persists", "critical": True},
        {"action": "click", "id": "submit", "selector": "#submit-btn",
         "submit_url": "/submit", "form": {"name": "Rex"},
         "criterion_id": "C2_submit_persists", "critical": True},
        {"action": "assert_text", "text": "Saved", "selector": "#result-value",
         "criterion_id": "C3_result_renders", "critical": True},
        {"action": "assert_state", "key": "name", "expected": "Rex",
         "criterion_id": "C4_backend_state", "critical": True},
        {"action": "navigate", "id": "api", "url": "/api/data",
         "criterion_id": "C5_api_ok", "critical": True},
        {"action": "assert_request_ok", "url": "/api/data",
         "criterion_id": "C5_api_ok", "critical": True},
        {"action": "assert_no_console_error",
         "criterion_id": "C6_no_console_error", "critical": True},
    ],
}]
_CRITERIA = [
    {"criterion_id": "C1_form_loads", "criterion": "form loads", "critical": True},
    {"criterion_id": "C2_submit_persists", "criterion": "submit lands on result", "critical": True},
    {"criterion_id": "C3_result_renders", "criterion": "result shows saved", "critical": True},
    {"criterion_id": "C4_backend_state", "criterion": "backend persisted", "critical": True},
    {"criterion_id": "C5_api_ok", "criterion": "api ok", "critical": True},
    {"criterion_id": "C6_no_console_error", "criterion": "no console errors", "critical": True},
]
_CHECKLIST = {"checklist_id": "fc-1", "signed_by_human": True, "criteria": _CRITERIA}


def _e2e_contract(mode="normal"):
    return {
        "executor_kind": "local_http",
        "app_start_cmd": [sys.executable, _FIX, "--port", "{port}",
                          "--store", "{store}", "--mode", "{mode}"],
        "readiness": {"url": "/__health", "timeout_seconds": 10},
        "base_url": "http://127.0.0.1", "shutdown": {"process_owned": True},
        "allowed_origins": ["http://127.0.0.1"], "mode": mode, "journeys": _JOURNEY,
    }


def _browser_charter(*, level="human_on_the_loop", mode="advisory", e2e_mode="normal"):
    charter = _acceptance_charter(level=level, mode=mode)
    charter["tooling"]["acceptance"]["functional"] = {
        "mode": "browser_e2e", "checklist_path": "checklist.json"}
    charter["tooling"]["e2e"] = _e2e_contract(e2e_mode)
    return charter


def _prep(run_dir, *, self_smoke=True, checklist=_CHECKLIST):
    """Write the per-run inputs Dev/Research produce into the run dir."""
    os.makedirs(os.path.join(run_dir, "docs"), exist_ok=True)
    with open(os.path.join(run_dir, "checklist.json"), "w") as fh:
        json.dump(checklist, fh)
    if self_smoke:
        with open(os.path.join(run_dir, "docs", "self-smoke.json"), "w") as fh:
            json.dump({"command": "python -m app && curl /", "result": "200 OK"}, fh)


def _browser_judge(run_dir, *, milestone_verdict="pass", mutate=None):
    """A callable acceptance mock that, at spawn time, reads the COMMITTED manifest from
    the prompt's evidence prefix and builds a verdict whose functional_evidence_refs cite
    REAL artifacts (so the driver's §3.2 ref-binding has something to bind). `mutate(v)`
    can corrupt the verdict to exercise the integrity gates."""
    def _mk(role, prompt, schema):
        prefix = re.search(r"\.orchestrator/audit/browser/[^\s`]+/r[0-9a-f]+",
                           prompt).group(0)
        manifest = json.load(open(os.path.join(run_dir, prefix, "manifest.json")))
        by_name = {a["name"]: a["sha256"] for a in manifest["artifacts"]}
        cr = by_name["checklist-results.json"]
        cases = [{
            "case_id": c["criterion_id"], "criterion_id": c["criterion_id"],
            "criterion": c["criterion"], "verdict": "pass",
            "rationale": "observed the criterion held in the captured evidence",
            "functional_evidence_refs": [{
                "kind": "checklist",
                "path": f"{prefix}/checklist-results.json", "sha256": cr}],
        } for c in _CRITERIA]
        v = {"milestone_verdict": milestone_verdict, "acceptance_class": "browser_e2e",
             "cases": cases,
             "suggested_route": "n/a" if milestone_verdict == "pass"
             else "deliver_fix_iteration"}
        if milestone_verdict == "fix_required":
            v["failure_briefs"] = [{"title": "defect", "contract_clause_violated": "C3",
                                    "proposed_scope": "fix the render", "severity": "P1"}]
        if mutate:
            v = mutate(v)
        return v
    return _mk


def _adapters(run_dir, judge=None, **jk):
    adapters = _acceptance_adapters({})
    adapters["acceptance"] = MockAdapter(
        {("acceptance",): judge or _browser_judge(run_dir, **jk)},
        harness="claude_code", provider="anthropic", model="claude-opus-4-8")
    return adapters


def _types(ledger):
    return [e["type"] for e in audit.read_events(ledger)]


def _checkpoints(run_dir):
    cps = []
    cdir = os.path.join(run_dir, "docs", "checkpoints")
    if os.path.isdir(cdir):
        for fn in os.listdir(cdir):
            parts = fn.split("__")
            if len(parts) >= 2:
                cps.append(parts[1])
    return cps


class HappyPath(unittest.TestCase):
    def test_browser_e2e_pass_commits_evidence_and_halts_for_signoff(self):
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            drv = _driver(d, charter=_browser_charter(), adapters=_adapters(d))
            final = drv.run(subsprint_id="sprint-001")
            t = _types(drv.audit_ledger)
            # evidence committed exactly once + anchored; acceptance ran once; M3 advisory.
            self.assertEqual(t.count("browser_e2e_evidence"), 1)
            self.assertEqual(t.count("acceptance_spawn"), 1)
            self.assertEqual(final.state, D.STATE_HALTED)
            self.assertIn("advisory_acceptance_pass_signoff", _checkpoints(d))
            self.assertNotEqual(final.state, D.STATE_DONE, "M3 advisory must NOT auto-ship")
            # evidence layout + artifacts referenced from the audit chain.
            run_dir = os.path.join(d, ".orchestrator", "audit", "browser")
            loop = os.listdir(run_dir)[0]
            rid = os.listdir(os.path.join(run_dir, loop))[0]
            evid = os.path.join(run_dir, loop, rid)
            for f in ("manifest.json", "checklist-results.json", "console.json",
                      "network.json", "app-start.log", "app-stop.log"):
                self.assertTrue(os.path.isfile(os.path.join(evid, f)), f)
            self.assertTrue(os.path.isdir(os.path.join(evid, "screenshots")))
            ev = next(e for e in audit.read_events(drv.audit_ledger)
                      if e["type"] == "browser_e2e_evidence")
            self.assertEqual(ev["payload"]["run_id"], final.e2e_run_id)
            self.assertEqual(ev["payload"]["manifest_sha256"], final.e2e_manifest_hash)


class HybridAcceptanceOwnedExecution(unittest.TestCase):
    def _hybrid_charter(self, *, cleanup_exit=0):
        charter = _browser_charter()
        charter["tooling"]["acceptance"]["functional"].update({
            "interaction_mode": "hybrid",
            "target_environment": "local",
            "browser": {
                "allowed_origins": ["http://127.0.0.1"],
                "allowed_actions": [
                    "navigate", "click", "fill", "select", "upload",
                    "download", "screenshot", "read_console", "read_network",
                ],
            },
        })
        charter["tooling"]["e2e"]["lifecycle_operations"] = [
            {
                "id": "seed-user", "phase": "setup",
                "command": [sys.executable, "-c",
                            "open(r'{store}.setup','w').write('ok')"],
                "environments": ["local"], "side_effect": "test_data",
            },
            {
                "id": "cleanup-user", "phase": "cleanup",
                "command": [sys.executable, "-c",
                            f"import sys; sys.exit({cleanup_exit})"],
                "environments": ["local"], "side_effect": "test_data",
                "failure_policy": "record",
            },
        ]
        return charter

    @staticmethod
    def _hybrid_adapters(run_dir):
        adapters = _acceptance_adapters({})
        plan = {
            "interaction_mode": "hybrid",
            "setup_operations": ["seed-user"],
            "journeys": [],
            "cleanup_operations": ["cleanup-user"],
            "rationale": "run signed journeys plus lifecycle preparation",
        }
        adapters["acceptance"] = MockAdapter(
            {
                ("acceptance", 0): plan,
                ("acceptance",): _browser_judge(run_dir),
            },
            harness="claude_code", provider="anthropic",
            model="claude-opus-4-8",
        )
        return adapters

    def test_hybrid_acceptance_plans_setup_and_cleanup_then_judges(self):
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            adapters = self._hybrid_adapters(d)
            drv = _driver(
                d, charter=self._hybrid_charter(), adapters=adapters)
            final = drv.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, D.STATE_HALTED)
            self.assertEqual(len(adapters["acceptance"].history), 2)
            self.assertIn("advisory_acceptance_pass_signoff", _checkpoints(d))
            base = os.path.join(d, ".orchestrator", "audit", "browser")
            loop = os.listdir(base)[0]
            rid = os.listdir(os.path.join(base, loop))[0]
            evid = os.path.join(base, loop, rid)
            for rel in (
                "acceptance-execution-plan.json",
                "lifecycle/setup-seed-user.log",
                "lifecycle/cleanup-cleanup-user.log",
                "cleanup-status.json",
            ):
                self.assertTrue(os.path.isfile(os.path.join(evid, rel)), rel)
            with open(os.path.join(evid, "cleanup-status.json"),
                      encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["status"], "clean")

    def test_cleanup_failure_preserves_verdict_but_halts_shipping(self):
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            adapters = self._hybrid_adapters(d)
            drv = _driver(
                d, charter=self._hybrid_charter(cleanup_exit=3),
                adapters=adapters)
            final = drv.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, D.STATE_HALTED)
            self.assertIn("acceptance_cleanup_required", _checkpoints(d))
            self.assertNotIn(
                "advisory_acceptance_pass_signoff", _checkpoints(d))


class CapturedDefectsNeverPass(unittest.TestCase):
    """§3.2: a captured product defect (the executor observed a critical fail) can NEVER
    become a milestone PASS — even when the judge naively returns pass, the driver's
    consistency gate coerces it to needs_human (surface_approve)."""

    def _defect(self, e2e_mode, failed_criterion):
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            drv = _driver(d, charter=_browser_charter(e2e_mode=e2e_mode),
                          adapters=_adapters(d, milestone_verdict="pass"))
            final = drv.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, D.STATE_HALTED)
            self.assertIn("acceptance_surface_approve", _checkpoints(d),
                          f"{e2e_mode} pass must be coerced to needs_human")
            self.assertNotIn("advisory_acceptance_pass_signoff", _checkpoints(d))
            # the executor CAPTURED the failure for the right criterion.
            base = os.path.join(d, ".orchestrator", "audit", "browser")
            loop = os.listdir(base)[0]
            rid = os.listdir(os.path.join(base, loop))[0]
            rows = json.load(open(os.path.join(base, loop, rid, "checklist-results.json")))
            byid = {r["criterion_id"]: r["executor_status"] for r in rows}
            self.assertEqual(byid[failed_criterion], "fail", byid)

    def test_render_defect_detected(self):
        self._defect("render_defect", "C3_result_renders")

    def test_state_mismatch_detected(self):
        self._defect("state_mismatch", "C4_backend_state")

    def test_console_error_persisted_and_blocks(self):
        self._defect("console_error", "C6_no_console_error")

    def test_failed_network_persisted_and_blocks(self):
        self._defect("net_fail", "C5_api_ok")


class IntegrityGates(unittest.TestCase):
    def test_verdict_class_mismatch_hard_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            def drop_class(v):
                v.pop("acceptance_class", None)  # static-shaped verdict on a browser run
                for c in v["cases"]:
                    c.pop("functional_evidence_refs", None)
                    c["evidence_path"] = "eval/runs/x/stdout.txt"
                return v
            drv = _driver(d, charter=_browser_charter(),
                          adapters=_adapters(d, mutate=drop_class))
            # a driver-level gate_hard_fail RAISES (the campaign catches it → paused
            # unit; a standalone loop surfaces it). The checkpoint is written first.
            with self.assertRaises(D.GateHardFail):
                drv.run(subsprint_id="sprint-001")
            self.assertIn("gate_hard_fail", _checkpoints(d))

    def test_fake_evidence_ref_hard_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            def fake_ref(v):
                for c in v["cases"]:
                    c["functional_evidence_refs"][0]["sha256"] = "0" * 64  # wrong hash
                return v
            drv = _driver(d, charter=_browser_charter(),
                          adapters=_adapters(d, mutate=fake_ref))
            with self.assertRaises(D.GateHardFail):
                drv.run(subsprint_id="sprint-001")
            self.assertIn("gate_hard_fail", _checkpoints(d))

    def test_coverage_gap_routes_needs_human(self):
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            def drop_case(v):
                v["cases"] = v["cases"][:-1]  # omit one signed criterion
                return v
            drv = _driver(d, charter=_browser_charter(),
                          adapters=_adapters(d, mutate=drop_case))
            final = drv.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, D.STATE_HALTED)
            self.assertIn("acceptance_surface_approve", _checkpoints(d))

    def test_missing_dev_self_smoke_halts(self):
        with tempfile.TemporaryDirectory() as d:
            _prep(d, self_smoke=False)  # Dev omitted the attestation
            drv = _driver(d, charter=_browser_charter(), adapters=_adapters(d))
            with self.assertRaises(D.GateHardFail):
                drv.run(subsprint_id="sprint-001")
            self.assertIn("gate_hard_fail", _checkpoints(d))
            # the executor never ran (no evidence) — the gate is BEFORE capture.
            self.assertEqual(_types(drv.audit_ledger).count("browser_e2e_evidence"), 0)


class ResumeIdempotency(unittest.TestCase):
    """§3.5a/b: resume never duplicates a committed browser run or re-rolls a committed
    verdict; an edit to evidence/authority/criteria between produce and resume re-spawns."""

    def _run_to_signoff(self, d, charter=None):
        _prep(d)
        drv = _driver(d, charter=charter or _browser_charter(), adapters=_adapters(d))
        final = drv.run(subsprint_id="sprint-001")
        self.assertEqual(final.state, D.STATE_HALTED)
        return drv

    def _set_state(self, d, **fields):
        path = os.path.join(d, ".orchestrator", "state.json")
        st = json.load(open(path))
        st.update(fields)
        with open(path, "w") as fh:
            json.dump(st, fh)

    def test_resume_after_halt_is_a_noop(self):
        with tempfile.TemporaryDirectory() as d:
            drv = self._run_to_signoff(d)
            before = _types(drv.audit_ledger)
            drv2 = _driver(d, charter=_browser_charter(), adapters=_adapters(d))
            drv2.run(resume=True)  # STATE_HALTED short-circuits
            after = _types(drv2.audit_ledger)
            self.assertEqual(after.count("browser_e2e_evidence"),
                             before.count("browser_e2e_evidence"))
            self.assertEqual(after.count("acceptance_spawn"),
                             before.count("acceptance_spawn"))

    def test_crash_before_routing_reuses_same_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            drv = self._run_to_signoff(d)
            n_spawn = _types(drv.audit_ledger).count("acceptance_spawn")
            n_evid = _types(drv.audit_ledger).count("browser_e2e_evidence")
            # Simulate a crash AFTER the verdict was produced+persisted but BEFORE routing:
            # the verdict + snapshot are already in state; rewind state to acceptance_pending.
            self._set_state(d, state="acceptance_pending")
            drv2 = _driver(d, charter=_browser_charter(), adapters=_adapters(d))
            final = drv2.run(resume=True)
            t = _types(drv2.audit_ledger)
            self.assertIn("acceptance_reuse", t)
            self.assertEqual(t.count("acceptance_spawn"), n_spawn, "must NOT re-spawn")
            self.assertEqual(t.count("browser_e2e_evidence"), n_evid, "must NOT re-run executor")
            self.assertEqual(final.state, D.STATE_HALTED)

    def test_stale_authoritative_browser_snapshot_does_not_auto_ship_on_resume(self):
        # Codex impl r3 BLOCKING: a persisted browser snapshot with authoritative:true whose
        # three reuse hashes still match must NOT be reused to auto-ship on resume — the
        # reuse condition also binds the authority DECISION. The charter here is the
        # authority-ELIGIBLE combo (auto + fully_autonomous + a self-declared M3 calibration),
        # so ONLY the §10 M3-advisory guard makes the FRESH decision False; a stale 'true'
        # must therefore re-spawn and stay ADVISORY (never STATE_DONE).
        charter = _browser_charter(level="fully_autonomous_within_budget", mode="auto")
        charter["tooling"]["acceptance"]["functional"]["judge_calibration_m3"] = {
            "status": "calibrated"}
        with tempfile.TemporaryDirectory() as d:
            drv = self._run_to_signoff(d, charter=charter)
            n_spawn = _types(drv.audit_ledger).count("acceptance_spawn")
            path = os.path.join(d, ".orchestrator", "state.json")
            st = json.load(open(path))
            self.assertFalse(st["acceptance_snapshot"]["authoritative"],
                             "the M3 guard must freeze authoritative False at production")
            # simulate a STALE authoritative basis: flip true, keep the 3 hashes intact.
            st["acceptance_snapshot"]["authoritative"] = True
            st["state"] = "acceptance_pending"
            with open(path, "w") as fh:
                json.dump(st, fh)
            drv2 = _driver(d, charter=charter, adapters=_adapters(d))
            final = drv2.run(resume=True)
            t = _types(drv2.audit_ledger)
            self.assertNotIn("acceptance_reuse", t,
                             "a stale authoritative snapshot must NOT be reused")
            self.assertEqual(t.count("acceptance_spawn"), n_spawn + 1, "must re-spawn")
            self.assertNotEqual(final.state, D.STATE_DONE,
                                "M3 must not auto-ship even via a stale reused snapshot")
            self.assertEqual(final.state, D.STATE_HALTED)
            self.assertIn("advisory_acceptance_pass_signoff", _checkpoints(d))

    def test_criteria_edit_between_produce_and_resume_respawns(self):
        with tempfile.TemporaryDirectory() as d:
            drv = self._run_to_signoff(d)
            n_spawn = _types(drv.audit_ledger).count("acceptance_spawn")
            self._set_state(d, state="acceptance_pending")
            # Edit a signed criterion's TEXT (ids unchanged → coverage still holds) — this
            # changes the resolver-graph hash, so the §3.5b reuse is INVALIDATED.
            edited = json.loads(json.dumps(_CHECKLIST))
            edited["criteria"][0]["criterion"] = "form loads (REVISED contract)"
            with open(os.path.join(d, "checklist.json"), "w") as fh:
                json.dump(edited, fh)
            drv2 = _driver(d, charter=_browser_charter(), adapters=_adapters(d))
            drv2.run(resume=True)
            t = _types(drv2.audit_ledger)
            self.assertNotIn("acceptance_reuse", t)
            self.assertEqual(t.count("acceptance_spawn"), n_spawn + 1, "must re-spawn")

    def test_missing_ledger_event_is_not_committed(self):
        # §3.5a: a final dir present but with NO matching browser_e2e_evidence event is
        # NOT committed → the reconcile re-runs (no skip on unanchored evidence).
        with tempfile.TemporaryDirectory() as d:
            import e2e_stage as es
            _prep(d)
            drv = _driver(d, charter=_browser_charter(), adapters=_adapters(d))
            drv.run(subsprint_id="sprint-001")
            base = os.path.join(d, ".orchestrator", "audit", "browser")
            loop = os.listdir(base)[0]
            rid = os.listdir(os.path.join(base, loop))[0]
            final = os.path.join(base, loop, rid)
            m = json.load(open(os.path.join(final, "manifest.json")))
            events = audit.read_events(drv.audit_ledger)
            # the committed dir IS anchored (the event exists) — sanity.
            self.assertTrue(es.evidence_event_present(
                events, rid, m["artifact_manifest_hash"]))
            # but a DIFFERENT run_id is not anchored, so reconcile would re-run it.
            self.assertFalse(es.evidence_event_present(
                events, "rdeadbeef", m["artifact_manifest_hash"]))


def _clock():
    n = {"i": 0}

    def tick():
        n["i"] += 1
        return f"2026-06-21T{n['i'] // 3600:02d}:{(n['i'] // 60) % 60:02d}:{n['i'] % 60:02d}Z"
    return tick


def _campaign_judge(units_dir):
    """One acceptance mock for the whole campaign: a browser verdict (bound to the unit's
    committed manifest) when the prompt carries a browser evidence prefix, else the static
    ACC_PASS. The unit run_dir is units_dir/<loop_id> and the prefix carries <loop_id>."""
    from test_driver import ACC_PASS

    def _mk(role, prompt, schema):
        m = re.search(r"\.orchestrator/audit/browser/([^\s/`]+)/(r[0-9a-f]+)", prompt)
        if not m:
            return dict(ACC_PASS)  # static milestone
        prefix, loop = m.group(0), m.group(1)
        manifest = json.load(open(os.path.join(units_dir, loop, prefix, "manifest.json")))
        cr = {a["name"]: a["sha256"] for a in manifest["artifacts"]}["checklist-results.json"]
        cases = [{"case_id": c["criterion_id"], "criterion_id": c["criterion_id"],
                  "criterion": c["criterion"], "verdict": "pass",
                  "rationale": "held in captured evidence",
                  "functional_evidence_refs": [{"kind": "checklist",
                                                "path": f"{prefix}/checklist-results.json",
                                                "sha256": cr}]} for c in _CRITERIA]
        return {"milestone_verdict": "pass", "acceptance_class": "browser_e2e",
                "cases": cases, "suggested_route": "n/a"}
    return _mk


class CampaignPerMilestone(unittest.TestCase):
    """Scenario 11: in a campaign the browser-E2E gate fires ONLY at the milestone that
    declares functional_acceptance=browser_e2e; the other milestone closes statically."""

    def test_browser_stage_fires_only_at_the_user_facing_milestone(self):
        import campaign as cp
        import run_loop as RL
        _SHIP = lambda reason, cp_path: {"choice": "ship"}  # noqa: E731

        def wrapped_run_loop(charter, *, run_dir, **kw):
            # Dev/Research per-unit inputs the browser milestone needs (harmless for the
            # static one). checklist_path is relative → resolved to THIS unit's run_dir.
            os.makedirs(os.path.join(run_dir, "docs"), exist_ok=True)
            with open(os.path.join(run_dir, "checklist.json"), "w") as fh:
                json.dump(_CHECKLIST, fh)
            with open(os.path.join(run_dir, "docs", "self-smoke.json"), "w") as fh:
                json.dump({"command": "smoke", "result": "ok"}, fh)
            return RL.run_loop(charter, run_dir=run_dir, **kw)

        with tempfile.TemporaryDirectory() as d:
            units = os.path.join(d, "units")
            charter = _acceptance_charter(level="human_on_the_loop", mode="advisory",
                                          subsprint_sequence=("sprint-001", "sprint-002"))
            # Shared charter carries the e2e mechanics + the checklist path, but NO
            # charter-level functional mode — the PLAN selects browser_e2e per milestone.
            charter["tooling"]["acceptance"]["functional"] = {"checklist_path": "checklist.json"}
            charter["tooling"]["e2e"] = _e2e_contract("normal")
            adapters = _acceptance_adapters({})
            adapters["acceptance"] = MockAdapter(
                {("acceptance",): _campaign_judge(units)}, harness="claude_code",
                provider="anthropic", model="claude-opus-4-8")
            clk = _clock()
            plan = {"campaign_id": "c1", "goal": "x", "signed_by_human": True, "milestones": [
                {"id": "m1", "objective": "static close", "subsprint_sequence": ["sprint-001"]},
                {"id": "m2", "objective": "user-facing close", "subsprint_sequence": ["sprint-002"],
                 "functional_acceptance": "browser_e2e"}]}
            run_unit = cp.make_run_unit(charter, units, "c1", clock=clk, plan=plan,
                                        adapters=adapters, run_loop_fn=wrapped_run_loop)
            camp = os.path.join(d, "camp")

            # m1 (static) → advisory signoff, NO browser evidence.
            st1 = cp.run_campaign(plan, camp, run_unit, clock=clk)
            self.assertEqual(st1.pause_reason, "advisory_acceptance_pass_signoff")
            m1 = st1.units[0]
            m1_types = _types_dir(os.path.join(units, m1["loop_id"]))
            self.assertNotIn("browser_e2e_evidence", m1_types, "m1 is static — no browser run")
            self.assertIn("acceptance_spawn", m1_types)

            # sign m1 → m2 (browser_e2e) → advisory signoff, WITH browser evidence.
            st2 = cp.run_campaign(plan, camp, run_unit, clock=clk, resume=True,
                                  decision_resolver=_SHIP)
            self.assertEqual(st2.pause_reason, "advisory_acceptance_pass_signoff")
            self.assertEqual(st2.milestone_index, 1)
            m2 = [u for u in st2.units if u["milestone_id"] == "m2"][0]
            m2_types = _types_dir(os.path.join(units, m2["loop_id"]))
            self.assertEqual(m2_types.count("browser_e2e_evidence"), 1,
                             "m2 declares browser_e2e — exactly one browser run")
            # provenance records the per-milestone projection + source.
            prov = json.load(open(os.path.join(units, m2["loop_id"], "derived-context.json")))
            self.assertEqual(prov["functional_acceptance"], {"mode": "browser_e2e", "source": "milestone"})

            # sign m2 → campaign DONE.
            st3 = cp.run_campaign(plan, camp, run_unit, clock=clk, resume=True,
                                  decision_resolver=_SHIP)
            self.assertEqual(st3.status, cp.STATUS_DONE)


def _types_dir(unit_dir):
    out = []
    for root, _dirs, fnames in os.walk(unit_dir):
        for fn in fnames:
            if fn.endswith(".jsonl"):
                out += [e["type"] for e in audit.read_events(os.path.join(root, fn))]
    return out


class M3NeverAuthoritativeInV1(unittest.TestCase):
    """Codex impl r2 BLOCKING-2: even with the authority-eligible combo (mode=auto +
    autonomy=fully_autonomous_within_budget) AND a charter that SELF-DECLARES
    judge_calibration_m3.status=calibrated, a browser_e2e (M3) pass must NOT auto-ship in
    v1 — it stays ADVISORY and HALTs for human sign-off (no validated M3 record exists).
    The guard is scoped to browser_e2e; static (M1) authority is byte-identical to P-A."""

    def test_self_declared_m3_calibration_cannot_auto_ship(self):
        with tempfile.TemporaryDirectory() as d:
            _prep(d)
            charter = _browser_charter(level="fully_autonomous_within_budget", mode="auto")
            # an adopter self-declaring M3 calibration with NO backing record/validation:
            charter["tooling"]["acceptance"]["functional"]["judge_calibration_m3"] = {
                "status": "calibrated"}
            drv = _driver(d, charter=charter, adapters=_adapters(d))
            # the authority recompute is False for browser_e2e regardless of the declared
            # M3 calibration (enforced by construction, before any run).
            self.assertFalse(drv._acceptance_authoritative(),
                             "M3 must never be authoritative in v1")
            final = drv.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, D.STATE_HALTED)
            self.assertNotEqual(
                final.state, D.STATE_DONE,
                "a self-declared M3 calibration must NOT auto-ship a browser pass")
            self.assertIn("advisory_acceptance_pass_signoff", _checkpoints(d))

    def test_static_m1_authority_is_byte_identical(self):
        # The guard is scoped to browser_e2e: a static (M1) charter with the SAME
        # authority-eligible combo (auto + fully_autonomous + M1 calibrated) stays
        # AUTHORITATIVE — P-A behavior is untouched by the M3 guard.
        charter = _acceptance_charter(level="fully_autonomous_within_budget",
                                      mode="auto", calibration="calibrated")
        with tempfile.TemporaryDirectory() as d:
            drv = _driver(d, charter=charter, adapters=_acceptance_adapters())
            self.assertEqual(drv._acceptance_class(), "static")
            self.assertTrue(drv._acceptance_authoritative(),
                            "static M1 authority must be byte-identical to P-A")


class ResolverGraphAdopterRoot(unittest.TestCase):
    """Codex impl r2 BLOCKING-3: the §3.5b resolver graph binds the ADOPTER cold-start
    docs from self.repo_dir (the adopter repo), NOT run_dir (the /tmp artifact dir) — so an
    edit to the real AGENTS.md / docs/current/adoption-state.md invalidates §3.5b reuse. A
    decoy under run_dir (the old wrong root) must NOT be what binds."""

    def test_adopter_cold_start_bound_from_repo_dir_and_edit_invalidates_reuse(self):
        import e2e_stage as es
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as d:
            _prep(d)
            # the ADOPTER repo (repo_dir) holds the cold-start docs the role card requires.
            with open(os.path.join(repo, "AGENTS.md"), "w") as fh:
                fh.write("# adopter cold start\n")
            os.makedirs(os.path.join(repo, "docs", "current"))
            adoption = os.path.join(repo, "docs", "current", "adoption-state.md")
            with open(adoption, "w") as fh:
                fh.write("phase: M1\n")
            # a DECOY under run_dir (the OLD wrong root) must NOT be what binds.
            with open(os.path.join(d, "AGENTS.md"), "w") as fh:
                fh.write("# DECOY (run_dir, must be ignored)\n")

            drv = D.Driver(_browser_charter(), d, _acceptance_adapters(),
                           loop_id="loop-b3", clock=_clock(), repo_dir=repo)
            drv.state = D.RunState(loop_id=drv.loop_id, subsprint_id="sprint-001")

            graph1, _missing = drv._acceptance_resolver_graph("eval/runs/x/out.txt", None)
            purposes = {g["purpose"] for g in graph1}
            self.assertIn("adopter_cold_start", purposes,
                          "adopter AGENTS.md (repo_dir) must be in the resolver graph")
            self.assertIn("adopter_ledger", purposes,
                          "adopter docs/current ledgers (repo_dir) must be bound")
            # the bound AGENTS.md is the ADOPTER one (repo_dir), not the run_dir decoy.
            ag = next(g for g in graph1 if g["purpose"] == "adopter_cold_start")
            self.assertEqual(ag["sha256"],
                             es.sha256_file(os.path.join(repo, "AGENTS.md")))
            self.assertNotEqual(
                ag["sha256"], es.sha256_file(os.path.join(d, "AGENTS.md")),
                "the run_dir decoy must NOT be what the resolver bound")

            h1 = es.acceptance_input_hash("PROMPT", graph1)
            # editing the adopter cold-start ledger must invalidate §3.5b reuse.
            with open(adoption, "w") as fh:
                fh.write("phase: M1 (REVISED)\n")
            graph2, _ = drv._acceptance_resolver_graph("eval/runs/x/out.txt", None)
            h2 = es.acceptance_input_hash("PROMPT", graph2)
            self.assertNotEqual(h1, h2,
                                "an adopter cold-start edit must change the input hash")

    def test_framework_role_session_governance_is_bound_explicitly(self):
        import e2e_stage as es
        with tempfile.TemporaryDirectory() as fw, tempfile.TemporaryDirectory() as d:
            _prep(d)
            for rel, body in (
                ("AGENTS.md", "# framework control plane entry\n"),
                ("schemas/compact/acceptance-verdict.compact.schema.json", "{}\n"),
                ("role-cards/acceptance-agent.md", "# acceptance role\n"),
                ("governance/constitution.md", "# constitution v1\n"),
                ("governance/doc_governance.md", "# doc governance\n"),
                ("governance/context_briefing.md", "# context briefing\n"),
            ):
                path = os.path.join(fw, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as fh:
                    fh.write(body)

            drv = D.Driver(
                _browser_charter(),
                d,
                _acceptance_adapters(),
                loop_id="loop-governance",
                clock=_clock(),
                verdict_schemas=D.load_verdict_schemas(),
            )
            drv.state = D.RunState(loop_id=drv.loop_id, subsprint_id="sprint-001")

            orig = D._find_schemas_dir
            D._find_schemas_dir = lambda start=D._ENGINE_KIT_DIR: os.path.join(
                fw, "schemas")
            try:
                graph1, _missing = drv._acceptance_resolver_graph(
                    "eval/runs/x/out.txt", None)
                purposes = {g["purpose"] for g in graph1}
                self.assertIn("framework_role_session_governance", purposes)
                bound_paths = {g["path"] for g in graph1}
                self.assertIn("governance/constitution.md", bound_paths)
                self.assertIn("governance/doc_governance.md", bound_paths)
                self.assertIn("governance/context_briefing.md", bound_paths)

                h1 = es.acceptance_input_hash("PROMPT", graph1)
                with open(os.path.join(fw, "governance", "constitution.md"), "w") as fh:
                    fh.write("# constitution v2\n")
                graph2, _ = drv._acceptance_resolver_graph(
                    "eval/runs/x/out.txt", None)
                h2 = es.acceptance_input_hash("PROMPT", graph2)
            finally:
                D._find_schemas_dir = orig
            self.assertNotEqual(
                h1, h2,
                "a role-session governance edit must change the acceptance input hash",
            )

    def test_acceptance_binds_compact_verdict_projection_not_canonical(self):
        # WP-1b (§E LOAD-CLOSURE): the Acceptance judge READS the compact verdict projection
        # (the agent-facing loaders point there), so the §3.5b resolver binds
        # schemas/compact/acceptance-verdict.compact.schema.json — NOT the verbose canonical
        # (which is the Python validator's input, not an agent input). An edit to the bound
        # projection must change the acceptance input hash (fail-closed re-spawn).
        import e2e_stage as es
        with tempfile.TemporaryDirectory() as fw, tempfile.TemporaryDirectory() as d:
            _prep(d)
            for rel, body in (
                ("AGENTS.md", "# fw control plane\n"),
                ("schemas/compact/acceptance-verdict.compact.schema.json",
                 '{"x-canonical-sha256":"v1"}\n'),
                ("schemas/acceptance-verdict.schema.json",
                 "# verbose canonical (validator only)\n"),
                ("role-cards/acceptance-agent.md", "# acceptance role\n"),
                ("governance/constitution.md", "# constitution\n"),
                ("governance/doc_governance.md", "# doc governance\n"),
                ("governance/context_briefing.md", "# context briefing\n"),
            ):
                path = os.path.join(fw, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as fh:
                    fh.write(body)

            drv = D.Driver(_browser_charter(), d, _acceptance_adapters(),
                           loop_id="loop-compact-verdict", clock=_clock(),
                           verdict_schemas=D.load_verdict_schemas())
            drv.state = D.RunState(loop_id=drv.loop_id, subsprint_id="sprint-001")

            orig = D._find_schemas_dir
            D._find_schemas_dir = lambda start=D._ENGINE_KIT_DIR: os.path.join(fw, "schemas")
            try:
                graph1, _ = drv._acceptance_resolver_graph("eval/runs/x/out.txt", None)
                bound = {g["path"] for g in graph1}
                self.assertIn("schemas/compact/acceptance-verdict.compact.schema.json", bound)
                self.assertNotIn("schemas/acceptance-verdict.schema.json", bound)  # canonical NOT bound
                self.assertIn("verdict_schema", {g["purpose"] for g in graph1})
                h1 = es.acceptance_input_hash("PROMPT", graph1)
                with open(os.path.join(fw, "schemas", "compact",
                                       "acceptance-verdict.compact.schema.json"), "w") as fh:
                    fh.write('{"x-canonical-sha256":"v2"}\n')   # the agent-read input changed
                graph2, _ = drv._acceptance_resolver_graph("eval/runs/x/out.txt", None)
                h2 = es.acceptance_input_hash("PROMPT", graph2)
            finally:
                D._find_schemas_dir = orig
            self.assertNotEqual(
                h1, h2,
                "editing the bound compact verdict projection must change the input hash")


# A schema-VALID but browser-shaped verdict (acceptance_class browser_e2e + functional
# refs, NO evidence_path) — proves a STATIC run rejects a class-mismatched verdict.
_BROWSER_SHAPED_VERDICT = {
    "milestone_verdict": "pass", "acceptance_class": "browser_e2e",
    "cases": [{"case_id": "c1", "criterion": "x", "criterion_id": "c1",
               "verdict": "pass", "rationale": "ok",
               "functional_evidence_refs": [{
                   "kind": "manifest",
                   "path": ".orchestrator/audit/browser/loop/r0/manifest.json",
                   "sha256": "0" * 64}]}],
    "suggested_route": "n/a"}


class StaticRunRejectsBrowserShapedVerdict(unittest.TestCase):
    """Codex impl r4 BLOCKING: a STATIC (M1) run must fail-closed on a verdict that claims
    acceptance_class browser_e2e — the branch-correct schema accepts it WITHOUT
    evidence_path, so the browser consistency gate (browser active class only) is skipped
    and an authoritative M1 'pass' could auto-ship a class-mismatched verdict. The driver
    enforces the SYMMETRIC class match for BOTH active classes → gate_hard_fail."""

    def test_static_auto_run_browser_shaped_verdict_hard_fails(self):
        # M1 authoritative-eligible (auto + fully_autonomous + calibrated): without the
        # static-side guard a browser-shaped 'pass' would reach STATE_DONE.
        charter = _acceptance_charter(level="fully_autonomous_within_budget",
                                      mode="auto", calibration="calibrated")
        with tempfile.TemporaryDirectory() as d:
            drv = _driver(d, charter=charter,
                          adapters=_acceptance_adapters(_BROWSER_SHAPED_VERDICT))
            with self.assertRaises(D.GateHardFail):
                drv.run(subsprint_id="sprint-001")
            self.assertIn("gate_hard_fail", _checkpoints(d))
            self.assertNotEqual(drv.state.state, D.STATE_DONE,
                                "a class-mismatched static verdict must NOT auto-ship")

    def test_reuse_path_also_rejects_browser_shaped_static_verdict(self):
        # The class guard also protects the §3.5b REUSE path: a persisted static run whose
        # last_verdict is a browser class must gate_hard_fail on resume — whether the resume
        # reuses the tampered verdict OR re-spawns (the resume judge also returns a browser
        # class), the driver rejects the class mismatch rather than routing it.
        charter = _acceptance_charter(level="human_on_the_loop", mode="advisory",
                                      calibration="calibrated")
        with tempfile.TemporaryDirectory() as d:
            drv = _driver(d, charter=charter, adapters=_acceptance_adapters())
            self.assertEqual(drv.run(subsprint_id="sprint-001").state, D.STATE_HALTED)
            path = os.path.join(d, ".orchestrator", "state.json")
            st = json.load(open(path))
            st["last_verdict"] = _BROWSER_SHAPED_VERDICT       # tamper to a browser class
            st["state"] = "acceptance_pending"
            with open(path, "w") as fh:
                json.dump(st, fh)
            drv2 = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(_BROWSER_SHAPED_VERDICT))
            with self.assertRaises(D.GateHardFail):
                drv2.run(resume=True)
            self.assertIn("gate_hard_fail", _checkpoints(d))


if __name__ == "__main__":
    unittest.main()
