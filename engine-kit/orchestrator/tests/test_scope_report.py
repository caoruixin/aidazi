"""Tests for scope_report (Phase-0 scope-coverage projection). stdlib unittest;
offline + pure (no Driver, no adapters, no clock). Mirrors test_campaign.py's
path bootstrap."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)                    # orchestrator/
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)              # engine-kit/
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import scope_report as sr  # noqa: E402


def _plan(milestones, **kw):
    return {"campaign_id": kw.pop("campaign_id", "camp-1"),
            "goal": kw.pop("goal", "deliver the thing"),
            "signed_by_human": True, "milestones": milestones, **kw}


def _ms(mid, seq, objective=None):
    return {"id": mid, "objective": objective or f"objective {mid}",
            "subsprint_sequence": list(seq)}


def _state(milestone_index, units, status="running", subsprint_index=0):
    """A campaign-state dict in CampaignState.to_dict() shape."""
    return {"campaign_id": "camp-1", "status": status,
            "pause_reason": None, "pause_checkpoint": None,
            "cursor": {"milestone_index": milestone_index,
                       "subsprint_index": subsprint_index},
            "spent": {"subsprints_run": len(units), "total_spawns": 0,
                      "wall_clock_minutes": 0.0},
            "units": units, "followup_baseline_seq": None}


def _unit(mid, ss, status="done"):
    return {"milestone_id": mid, "subsprint_id": ss, "status": status,
            "final_state": None, "loop_id": None,
            "pause_reason": None, "checkpoint_path": None}


_THREE = [_ms("m1", ["s1", "s2"]), _ms("m2", ["s3"]), _ms("m3", ["s4"])]


class TestNoState(unittest.TestCase):
    def test_none_state_all_not_started(self):
        rep = sr.compute_coverage(_plan(_THREE), None)
        t = rep["totals"]
        self.assertEqual(t["milestones"], 3)
        self.assertEqual(t["milestones_delivered"], 0)
        self.assertEqual(t["milestones_not_started"], 3)
        self.assertEqual(t["subsprints"], 4)
        self.assertEqual(t["subsprints_delivered"], 0)
        self.assertEqual(rep["pct"]["milestones_delivered"], 0)
        self.assertEqual([r["id"] for r in rep["remaining"]], ["m1", "m2", "m3"])
        self.assertFalse(rep["baseline_available"])


class TestPartialDelivery(unittest.TestCase):
    def setUp(self):
        # cursor past m1 ⇒ m1 delivered (accepted); m2 in-flight; m3 untouched.
        self.rep = sr.compute_coverage(
            _plan(_THREE),
            _state(1, [_unit("m1", "s1"), _unit("m1", "s2")], status="paused"))

    def test_milestone_rollup(self):
        t = self.rep["totals"]
        self.assertEqual(t["milestones_delivered"], 1)
        self.assertEqual(t["milestones_in_progress"], 1)
        self.assertEqual(t["milestones_not_started"], 1)
        self.assertEqual(self.rep["pct"]["milestones_delivered"], 33)

    def test_subsprint_rollup(self):
        t = self.rep["totals"]
        self.assertEqual(t["subsprints_delivered"], 2)   # s1, s2
        self.assertEqual(t["subsprints"], 4)
        self.assertEqual(self.rep["pct"]["subsprints_delivered"], 50)

    def test_per_milestone_status(self):
        by_id = {r["id"]: r for r in self.rep["milestones"]}
        self.assertEqual(by_id["m1"]["status"], "delivered")
        self.assertEqual(by_id["m2"]["status"], "in_progress")
        self.assertEqual(by_id["m3"]["status"], "not_started")
        self.assertEqual([s["status"] for s in by_id["m1"]["subsprints"]],
                         ["delivered", "delivered"])

    def test_remaining_is_continue_menu(self):
        rem = {r["id"]: r for r in self.rep["remaining"]}
        self.assertEqual(set(rem), {"m2", "m3"})
        self.assertEqual(rem["m2"]["open_subsprints"], ["s3"])
        self.assertEqual(rem["m3"]["open_subsprints"], ["s4"])


class TestFullyDone(unittest.TestCase):
    def test_done_all_delivered_remaining_empty(self):
        units = [_unit("m1", "s1"), _unit("m1", "s2"),
                 _unit("m2", "s3"), _unit("m3", "s4")]
        rep = sr.compute_coverage(_plan(_THREE), _state(3, units, status="done"))
        t = rep["totals"]
        self.assertEqual(t["milestones_delivered"], 3)
        self.assertEqual(rep["pct"]["milestones_delivered"], 100)
        self.assertEqual(rep["pct"]["subsprints_delivered"], 100)
        self.assertEqual(rep["remaining"], [])


class TestHaltedSubsprintNotDelivered(unittest.TestCase):
    def test_halted_unit_is_open(self):
        rep = sr.compute_coverage(
            _plan([_ms("m1", ["s1", "s2"])]),
            _state(0, [_unit("m1", "s1"), _unit("m1", "s2", status="halted")]))
        by_id = {r["id"]: r for r in rep["milestones"]}
        statuses = {s["id"]: s["status"] for s in by_id["m1"]["subsprints"]}
        self.assertEqual(statuses, {"s1": "delivered", "s2": "halted"})
        self.assertEqual(rep["totals"]["subsprints_delivered"], 1)
        self.assertEqual(rep["remaining"][0]["open_subsprints"], ["s2"])


class TestBaselineDelta(unittest.TestCase):
    def setUp(self):
        # original backlog: m1 (s1) + mX (sx). current: m1 (s1,s2) + m3 (s4).
        original = _plan([_ms("m1", ["s1"]), _ms("mX", ["sx"])])
        self.baseline = sr.freeze_baseline(original)
        self.current = _plan([_ms("m1", ["s1", "s2"]), _ms("m3", ["s4"])])
        self.rep = sr.compute_coverage(self.current, None, baseline=self.baseline)

    def test_added_and_removed_milestones(self):
        self.assertTrue(self.rep["baseline_available"])
        self.assertEqual(self.rep["added_milestones"], ["m3"])
        self.assertEqual(self.rep["removed_milestones"], ["mX"])

    def test_per_milestone_subsprint_delta(self):
        by_id = {r["id"]: r for r in self.rep["milestones"]}
        self.assertFalse(by_id["m1"]["added"])
        self.assertEqual(by_id["m1"]["added_subsprints"], ["s2"])
        self.assertEqual(by_id["m1"]["removed_subsprints"], [])
        self.assertTrue(by_id["m3"]["added"])
        self.assertEqual(by_id["m3"]["added_subsprints"], ["s4"])

    def test_no_baseline_omits_delta(self):
        rep = sr.compute_coverage(self.current, None, baseline=None)
        self.assertFalse(rep["baseline_available"])
        self.assertEqual(rep["added_milestones"], [])
        self.assertEqual(rep["removed_milestones"], [])
        self.assertNotIn("added", rep["milestones"][0])


class TestDrift(unittest.TestCase):
    def test_dispatched_subsprint_absent_from_plan_is_drift(self):
        rep = sr.compute_coverage(
            _plan([_ms("m1", ["s1"])]),
            _state(0, [_unit("m1", "ghost")]))
        self.assertEqual(len(rep["drift"]), 1)
        self.assertEqual(rep["drift"][0]["subsprint_id"], "ghost")
        # the in-plan s1 still reads not_started (it was never dispatched).
        self.assertEqual(rep["milestones"][0]["subsprints"][0]["status"], "not_started")


class TestBaselineRoundTrip(unittest.TestCase):
    def test_freeze_load_roundtrip_and_missing(self):
        with tempfile.TemporaryDirectory() as home:
            plan = _plan(_THREE)
            with open(sr.baseline_path_for(home), "w", encoding="utf-8") as fh:
                json.dump(sr.freeze_baseline(plan), fh)
            loaded = sr.load_baseline(home)
            self.assertEqual([m["id"] for m in loaded["milestones"]],
                             ["m1", "m2", "m3"])
        # absent dir / None ⇒ None, never raises.
        self.assertIsNone(sr.load_baseline(home))   # dir now gone
        self.assertIsNone(sr.load_baseline(None))


class TestSummaryLine(unittest.TestCase):
    def test_machine_subset_keys_and_values(self):
        rep = sr.compute_coverage(
            _plan(_THREE),
            _state(1, [_unit("m1", "s1"), _unit("m1", "s2")], status="paused"))
        line = sr.summary_line(rep)
        for k in ("campaign_id", "campaign_status", "baseline_available",
                  "milestones_total", "milestones_delivered",
                  "pct_milestones_delivered", "remaining_milestones"):
            self.assertIn(k, line)
        self.assertEqual(line["milestones_total"], 3)
        self.assertEqual(line["milestones_delivered"], 1)
        self.assertEqual(line["remaining_milestones"], ["m2", "m3"])
        # JSON-serializable with stable ordering (the SCOPE_COVERAGE= contract).
        self.assertIsInstance(json.dumps(line, sort_keys=True), str)


class TestRenderText(unittest.TestCase):
    def test_render_partial_has_markers(self):
        rep = sr.compute_coverage(_plan(_THREE), _state(1, [_unit("m1", "s1")]))
        out = sr.render_text(rep)
        self.assertIn("scope coverage", out)
        self.assertIn("remaining (continue menu)", out)
        self.assertIn("NOT frozen", out)   # no baseline supplied

    def test_render_done_says_fully_delivered(self):
        units = [_unit("m1", "s1"), _unit("m1", "s2"),
                 _unit("m2", "s3"), _unit("m3", "s4")]
        rep = sr.compute_coverage(_plan(_THREE), _state(3, units, status="done"))
        self.assertIn("fully delivered", sr.render_text(rep))


class TestToDictContract(unittest.TestCase):
    """Lock the contract the run_loop wiring depends on: a real CampaignState's
    to_dict() feeds compute_coverage cleanly."""
    def test_real_campaign_state_to_dict(self):
        import campaign as cp
        st = cp.CampaignState(campaign_id="camp-1", status="paused",
                              milestone_index=1)
        st.units = [_unit("m1", "s1"), _unit("m1", "s2")]
        rep = sr.compute_coverage(_plan(_THREE), st.to_dict())
        self.assertEqual(rep["totals"]["milestones_delivered"], 1)
        self.assertEqual(rep["campaign_status"], "paused")


class TestCli(unittest.TestCase):
    def _write(self, path, obj):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)

    def test_freeze_then_report(self):
        with tempfile.TemporaryDirectory() as home:
            plan_path = os.path.join(home, "plan.json")
            self._write(plan_path, _plan(_THREE))
            # freeze
            rc = sr.main(["--plan", plan_path, "--freeze-baseline",
                          "--campaign-home", home])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(sr.baseline_path_for(home)))
            # report (no state file ⇒ all not_started; baseline auto-loaded)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = sr.main(["--plan", plan_path, "--campaign-home", home])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("SCOPE_COVERAGE=", out)
            machine = json.loads(out.split("SCOPE_COVERAGE=", 1)[1].splitlines()[0])
            self.assertTrue(machine["baseline_available"])
            self.assertEqual(machine["milestones_total"], 3)

    def test_report_reads_state_from_home(self):
        with tempfile.TemporaryDirectory() as home:
            plan_path = os.path.join(home, "plan.json")
            self._write(plan_path, _plan(_THREE))
            self._write(os.path.join(home, "campaign-state.json"),
                        _state(1, [_unit("m1", "s1"), _unit("m1", "s2")],
                               status="paused"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = sr.main(["--plan", plan_path, "--campaign-home", home, "--json"])
            self.assertEqual(rc, 0)
            rep = json.loads(buf.getvalue())
            self.assertEqual(rep["totals"]["milestones_delivered"], 1)

    def test_missing_plan_returns_2(self):
        rc = sr.main(["--plan", "/no/such/plan.json"])
        self.assertEqual(rc, 2)

    def test_freeze_without_home_or_out_returns_2(self):
        with tempfile.TemporaryDirectory() as home:
            plan_path = os.path.join(home, "plan.json")
            self._write(plan_path, _plan(_THREE))
            rc = sr.main(["--plan", plan_path, "--freeze-baseline"])
            self.assertEqual(rc, 2)


class TestTopologicalOrderProjection(unittest.TestCase):
    """Regression: the cursor advances in the runner's TOPOLOGICAL order, so the
    projection must too — raw declared order mis-maps a reordered plan."""

    def test_cursor_maps_to_topological_not_declared_order(self):
        # DECLARED order [m2, m1], but m2 depends_on m1 ⇒ runner executes [m1, m2].
        # cursor=1 ⇒ m1 (topo-first) delivered, m2 in-flight. Raw order would
        # wrongly mark m2 delivered and m1 in_progress.
        m2 = {"id": "m2", "objective": "o2", "subsprint_sequence": ["s2"],
              "depends_on": ["m1"]}
        plan = _plan([m2, _ms("m1", ["s1"])])
        rep = sr.compute_coverage(
            plan, _state(1, [_unit("m1", "s1")], status="paused"))
        by_id = {r["id"]: r for r in rep["milestones"]}
        self.assertEqual(by_id["m1"]["status"], "delivered")
        self.assertEqual(by_id["m2"]["status"], "in_progress")


class TestRemovedMilestoneDrift(unittest.TestCase):
    """Regression: a unit dispatched for a milestone later REMOVED from the plan
    must still surface as drift (exact even without a baseline)."""

    def test_unit_for_removed_milestone_appears_in_drift(self):
        plan = _plan([_ms("m1", ["s1"])])  # m9 is gone from the current plan
        units = [_unit("m1", "s1"), _unit("m9", "s99")]
        rep = sr.compute_coverage(plan, _state(1, units, status="paused"))
        drift = {(d["milestone_id"], d["subsprint_id"]) for d in rep["drift"]}
        self.assertIn(("m9", "s99"), drift)
        self.assertNotIn(("m1", "s1"), drift)   # in-plan, delivered — not drift


import campaign as cp  # noqa: E402  (F1 stamp/hash helpers reused by the REQ tests)

_STATIC_CHARTER = {"tooling": {"acceptance": {"functional": {"mode": "static"}}}}


def _ledger(items):
    return {"version": "v1", "requirements": [
        {"id": i, "statement": f"req {i}", "source": {"channel": "prd"},
         "customer_disposition": d} for (i, d) in items]}


def _covplan(milestones, **kw):
    """A plan with covers_req_ids per milestone: milestones = [(mid, [reqs], seq?)]."""
    ms = []
    for entry in milestones:
        mid, reqs = entry[0], entry[1]
        seq = entry[2] if len(entry) > 2 else [f"{mid}-s1"]
        ms.append({"id": mid, "objective": f"o {mid}",
                   "covers_req_ids": list(reqs), "subsprint_sequence": seq})
    return _plan(ms, **kw)


def _outcome(mid, terminal):
    return {"milestone_id": mid, "terminal": terminal}


def _reqstate(milestone_index, outcomes, status="running", units=None):
    st = _state(milestone_index, units or [], status=status)
    st["milestone_outcomes"] = outcomes
    return st


class TestRequirementProjectionDelivery(unittest.TestCase):
    """Derived delivery_status from each milestone's TERMINAL outcome (design §3.5.1)."""

    def setUp(self):
        self.plan = cp.stamp_signoff(
            _covplan([("m1", ["REQ-1"]), ("m2", ["REQ-2"]), ("m3", ["REQ-3"])]),
            _STATIC_CHARTER, signed_at="t", charter_ref="ch")
        self.led = _ledger([("REQ-1", "accepted"), ("REQ-2", "accepted"),
                            ("REQ-3", "accepted")])

    def test_delivered_requires_acceptance_pass(self):
        state = _reqstate(2, [_outcome("m1", "acceptance_pass_authoritative"),
                              _outcome("m2", "acceptance_pass_advisory_ship")])
        rep = sr.compute_requirement_coverage(self.plan, state, self.led,
                                              charter=_STATIC_CHARTER)
        d = {r["id"]: r["delivery_status"] for r in rep["requirements"]}
        self.assertEqual(d["REQ-1"], "delivered")
        self.assertEqual(d["REQ-2"], "delivered")
        self.assertEqual(d["REQ-3"], "in_progress")   # m3 is the cursor, no outcome yet
        self.assertEqual(rep["totals"]["delivered"], 2)

    def test_all_waived_reasons(self):
        state = _reqstate(3, [_outcome("m1", "fix_required_ship"),
                              _outcome("m2", "surface_approve_ship"),
                              _outcome("m3", "acceptance_off")], status="done")
        rep = sr.compute_requirement_coverage(self.plan, state, self.led,
                                              charter=_STATIC_CHARTER)
        by = {r["id"]: r for r in rep["requirements"]}
        self.assertEqual((by["REQ-1"]["delivery_status"], by["REQ-1"]["delivery_reason"]),
                         ("waived", "fix_required_ship"))
        self.assertEqual((by["REQ-2"]["delivery_status"], by["REQ-2"]["delivery_reason"]),
                         ("waived", "surface_approve"))
        self.assertEqual((by["REQ-3"]["delivery_status"], by["REQ-3"]["delivery_reason"]),
                         ("waived", "acceptance_off"))
        self.assertEqual(rep["totals"]["waived"], 3)

    def test_out_of_scope_advance_waived(self):
        state = _reqstate(1, [_outcome("m1", "out_of_scope_advance")])
        rep = sr.compute_requirement_coverage(self.plan, state, self.led,
                                              charter=_STATIC_CHARTER)
        by = {r["id"]: r for r in rep["requirements"]}
        self.assertEqual((by["REQ-1"]["delivery_status"], by["REQ-1"]["delivery_reason"]),
                         ("waived", "out_of_scope_advance"))

    def test_not_shipped_is_not_delivered(self):
        state = _reqstate(0, [_outcome("m1", "not_shipped")], status="ended")
        rep = sr.compute_requirement_coverage(self.plan, state, self.led,
                                              charter=_STATIC_CHARTER)
        by = {r["id"]: r for r in rep["requirements"]}
        self.assertNotEqual(by["REQ-1"]["delivery_status"], "delivered")


class TestRequirementUncoveredAndDrift(unittest.TestCase):
    def test_uncovered_is_the_prd_gap(self):
        led = _ledger([("REQ-1", "accepted"), ("REQ-2", "accepted"),  # REQ-2 in no ms
                       ("REQ-3", "dropped")])                          # validly retired
        # Direct-stamp (bypasses the --sign-plan gate) with the SAME ledger coverage uses
        # — production's single-ledger invariant: covered_req_surfaces binds identically at
        # sign + recompute → fresh, not false-stale.
        plan = cp.stamp_signoff(_covplan([("m1", ["REQ-1"])]), _STATIC_CHARTER,
                                signed_at="t", ledger=led)
        rep = sr.compute_requirement_coverage(plan, _reqstate(0, []), led,
                                              charter=_STATIC_CHARTER)
        self.assertEqual(rep["uncovered_requirements"], ["REQ-2"])    # not REQ-3 (dropped)

    def test_covers_unknown_req_is_drift(self):
        plan = cp.stamp_signoff(_covplan([("m1", ["REQ-1", "REQ-9"])]), _STATIC_CHARTER,
                                signed_at="t")
        led = _ledger([("REQ-1", "accepted")])   # REQ-9 not in the ledger
        rep = sr.compute_requirement_coverage(plan, _reqstate(0, []), led,
                                              charter=_STATIC_CHARTER)
        self.assertEqual(rep["coverage_drift"],
                         [{"milestone_id": "m1", "unknown_req_id": "REQ-9"}])


class TestInvalidSignedDisposition(unittest.TestCase):
    """A retiring disposition on FRESH-signed scope is a conflict and is NOT retired
    (G2/F2) — it stays in the continue menu until a re-sign reconciles it."""

    def test_dropped_on_fresh_signed_is_kept(self):
        led = _ledger([("REQ-1", "dropped")])    # dropped but bound to fresh-signed m1
        # Direct-stamp with the ledger (bypasses the --sign-plan gate; mirrors the
        # single-ledger invariant), else the ledger-aware recompute here reads a false 'stale'.
        plan = cp.stamp_signoff(_covplan([("m1", ["REQ-1"])]), _STATIC_CHARTER,
                                signed_at="t", ledger=led)
        rep = sr.compute_requirement_coverage(plan, _reqstate(0, []), led,
                                              charter=_STATIC_CHARTER)
        self.assertEqual(rep["invalid_signed_disposition"], ["REQ-1"])
        by = {r["id"]: r for r in rep["requirements"]}
        self.assertEqual(by["REQ-1"]["conflict"], "invalid_signed_disposition")
        self.assertTrue(by["REQ-1"]["signed_bound"])
        # KEPT in the continue menu (not silently retired).
        self.assertIn("REQ-1", [r["id"] for r in rep["remaining"]])


class TestStaleSignoffKeepsPriorCoverage(unittest.TestCase):
    """When the live hash diverges from the signed snapshot, scope_report emits a
    stale_signoff conflict and renders the STORED snapshot's prior signed coverage so a
    ledger retirement is never shown as settled (G4)."""

    def test_stale_after_edit_preserves_prior_signed_coverage(self):
        signed = cp.stamp_signoff(
            _covplan([("m1", ["REQ-1"]), ("m2", ["REQ-2"])]),
            _STATIC_CHARTER, signed_at="t")
        # Edit a milestone AFTER signing → live hash diverges → stale.
        stale_plan = json.loads(json.dumps(signed))
        stale_plan["milestones"][1]["objective"] = "EDITED AFTER SIGNOFF"
        self.assertEqual(cp.signoff_status(stale_plan, _STATIC_CHARTER), "stale")
        led = _ledger([("REQ-1", "accepted"), ("REQ-2", "dropped")])  # try to retire REQ-2
        rep = sr.compute_requirement_coverage(stale_plan, _reqstate(0, []), led,
                                              charter=_STATIC_CHARTER)
        self.assertEqual(rep["signoff_status"], "stale")
        self.assertIsNotNone(rep["stale_signoff"])
        # Prior signed coverage is reconstructable from the stored snapshot.
        self.assertEqual(rep["stale_signoff"]["prior_signed_coverage"],
                         {"m1": ["REQ-1"], "m2": ["REQ-2"]})
        self.assertNotEqual(rep["stale_signoff"]["stored_hash"],
                            rep["stale_signoff"]["live_hash"])
        # REQ-2's ledger retirement is NOT settled while stale (it was prior-signed) —
        # it stays visible (uncovered/remaining), never silently dropped.
        self.assertIn("REQ-2", rep["uncovered_requirements"])
        self.assertIn("REQ-2", [r["id"] for r in rep["remaining"]])


class TestBlockedSignoffProtectsCoverage(unittest.TestCase):
    """Codex R-P2a #1/#2: while a plan is BLOCKED pending re-sign (pre-F1 OR a stale
    signoff with an UNVERIFIABLE snapshot), a ledger disposition must NOT silently retire
    its covered REQs, and a tampered snapshot must NOT be trusted for prior coverage."""

    def test_pre_f1_signed_coverage_not_silently_retired(self):
        # covers_req_ids present (opts into F1) + a bare top-level signed_by_human, NO
        # signoff block ⇒ pre_f1: the runner re-pauses, so scope_report must protect it.
        plan = _covplan([("m1", ["REQ-1"])])
        plan["signed_by_human"] = True
        self.assertEqual(cp.signoff_status(plan, _STATIC_CHARTER), "pre_f1")
        led = _ledger([("REQ-1", "dropped")])    # try to retire a pre-F1-signed REQ
        rep = sr.compute_requirement_coverage(plan, _reqstate(0, []), led,
                                              charter=_STATIC_CHARTER)
        by = {r["id"]: r for r in rep["requirements"]}
        self.assertTrue(by["REQ-1"]["signed_bound"])
        self.assertEqual(by["REQ-1"]["conflict"], "stale_signoff")
        self.assertIn("REQ-1", rep["uncovered_requirements"])      # NOT validly retired
        self.assertIn("REQ-1", [r["id"] for r in rep["remaining"]])
        self.assertEqual(rep["stale_signoff"]["status"], "pre_f1")

    def test_tampered_stale_snapshot_fails_closed(self):
        signed = cp.stamp_signoff(
            _covplan([("m1", ["REQ-1"]), ("m2", ["REQ-2"])]), _STATIC_CHARTER, signed_at="t")
        stale_plan = json.loads(json.dumps(signed))
        stale_plan["milestones"][0]["objective"] = "EDITED → stale"   # live diverges ⇒ stale
        # TAMPER the stored snapshot to drop REQ-2's prior coverage, leaving the stored
        # signed_scope_hash untouched — the attack the authenticity check must catch.
        stale_plan["signoff"]["scope_envelope"]["milestones"][1]["covers_req_ids"] = []
        self.assertEqual(cp.signoff_status(stale_plan, _STATIC_CHARTER), "stale")
        self.assertFalse(cp.signoff_snapshot_authentic(stale_plan))
        led = _ledger([("REQ-1", "accepted"), ("REQ-2", "dropped")])  # try to retire REQ-2
        rep = sr.compute_requirement_coverage(stale_plan, _reqstate(0, []), led,
                                              charter=_STATIC_CHARTER)
        self.assertFalse(rep["stale_signoff"]["snapshot_authentic"])
        self.assertEqual(rep["stale_signoff"]["prior_signed_coverage"], {})  # withheld
        # Fail-closed: REQ-2 (still in the LIVE covers) is protected, NOT silently retired.
        by = {r["id"]: r for r in rep["requirements"]}
        self.assertTrue(by["REQ-2"]["signed_bound"])
        self.assertIn("REQ-2", rep["uncovered_requirements"])
        self.assertIn("REQ-2", [r["id"] for r in rep["remaining"]])


class TestRequirementSummaryAndCli(unittest.TestCase):
    def test_summary_line_machine_subset(self):
        plan = cp.stamp_signoff(_covplan([("m1", ["REQ-1"])]), _STATIC_CHARTER,
                                signed_at="t")
        led = _ledger([("REQ-1", "accepted"), ("REQ-2", "accepted")])
        rep = sr.compute_requirement_coverage(plan, _reqstate(0, []), led,
                                              charter=_STATIC_CHARTER)
        line = sr.requirement_summary_line(rep)
        for k in ("campaign_id", "ledger_present", "signoff_status",
                  "requirements_total", "delivered", "waived", "uncovered",
                  "uncovered_requirements", "stale_signoff", "remaining_requirements"):
            self.assertIn(k, line)
        self.assertEqual(line["requirements_total"], 2)
        self.assertIsInstance(json.dumps(line, sort_keys=True), str)

    def _write(self, path, obj):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)

    def test_cli_emits_requirement_coverage_only_with_ledger(self):
        with tempfile.TemporaryDirectory() as home:
            plan = cp.stamp_signoff(_covplan([("m1", ["REQ-1"])]), _STATIC_CHARTER,
                                    signed_at="t")
            plan_path = os.path.join(home, "plan.json")
            led_path = os.path.join(home, "ledger.json")
            self._write(plan_path, plan)
            self._write(led_path, _ledger([("REQ-1", "accepted")]))
            # WITHOUT --requirement-ledger: no REQUIREMENT_COVERAGE= (byte-identical).
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = sr.main(["--plan", plan_path, "--campaign-home", home])
            self.assertEqual(rc, 0)
            self.assertIn("SCOPE_COVERAGE=", buf.getvalue())
            self.assertNotIn("REQUIREMENT_COVERAGE=", buf.getvalue())
            # WITH a valid ledger: REQUIREMENT_COVERAGE= present.
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = sr.main(["--plan", plan_path, "--campaign-home", home,
                              "--requirement-ledger", led_path])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("REQUIREMENT_COVERAGE=", out)
            machine = json.loads(
                out.split("REQUIREMENT_COVERAGE=", 1)[1].splitlines()[0])
            self.assertTrue(machine["ledger_present"])
            self.assertEqual(machine["requirements_total"], 1)

    def test_cli_invalid_ledger_returns_2(self):
        with tempfile.TemporaryDirectory() as home:
            plan = cp.stamp_signoff(_covplan([("m1", ["REQ-1"])]), _STATIC_CHARTER,
                                    signed_at="t")
            plan_path = os.path.join(home, "plan.json")
            led_path = os.path.join(home, "ledger.json")
            self._write(plan_path, plan)
            self._write(led_path, {"version": "v1", "requirements": [{"id": "BAD"}]})
            rc = sr.main(["--plan", plan_path, "--campaign-home", home,
                          "--requirement-ledger", led_path])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
