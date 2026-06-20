"""Production-path (REAL Driver) integration tests for the Campaign loop (P-B).

Unlike test_campaign.py (which injects a FAKE run_unit — no Driver, no adapters),
these drive the REAL production path

    campaign.make_run_unit → scheduling.run_loop → the REAL Driver  (MockAdapters)

offline. They cover what the fake-run_unit unit tests cannot: that the Driver
ACTUALLY fires its milestone-close Acceptance gate, and that the campaign
halts/resumes around it across multiple milestones.

Promoted from the former engine-kit/verify_campaign_e2e.py smoke artifact. The
two-milestone scenario is turned into a REGRESSION for the per-milestone Acceptance
fix (campaign.derive_milestone_context / make_run_unit `plan=`): with a single
shared charter, only the campaign-terminal sub-sprint fired Acceptance, so non-final
milestones advanced with NO acceptance gate. Now each milestone's FINAL sub-sprint
closes through its own Acceptance gate.
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)                       # orchestrator/
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)                  # engine-kit/
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling"),
           os.path.join(_ENGINE_KIT_DIR, "validators")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402
import audit_log as audit  # noqa: E402
from test_driver import (  # noqa: E402  (reuse the REAL charter + MockAdapters)
    _acceptance_charter, _acceptance_adapters, ACC_PASS, ACC_INVALID_CODE_ONLY)

_SHIP = lambda reason, cp_path: {"choice": "ship"}  # noqa: E731  (human signs the advisory pass)


def _clock():
    """Deterministic minute-rolling ISO-8601 clock (rolls cleanly for thousands of
    ticks — a full two-milestone real-Driver run emits far more audit events than
    test_driver._clock's 59-second ceiling allows)."""
    n = {"i": 0}

    def tick() -> str:
        n["i"] += 1
        return f"2026-06-20T{n['i'] // 3600:02d}:{(n['i'] // 60) % 60:02d}:{n['i'] % 60:02d}Z"
    return tick


def _plan(cid, milestones, signed=True):
    return {"campaign_id": cid, "goal": "deliver the thing",
            "signed_by_human": signed, "milestones": milestones}


def _expected_loop_id(campaign_id, milestone_id, subsprint_id):
    """Mirror make_run_unit's loop_id derivation so a test can name a unit's dir
    WITHOUT having dispatched it (to prove a later milestone has NOT run yet)."""
    digest = hashlib.sha256(
        f"{campaign_id}\x00{milestone_id}\x00{subsprint_id}".encode()).hexdigest()
    return "u" + digest[:24]


def _driver_event_types(unit_dir):
    """Every audit event type across the unit's REAL Driver ledger(s) under
    `unit_dir` — the ground-truth evidence of what the Driver actually did."""
    types = []
    for root, _dirs, fnames in os.walk(unit_dir):
        for fn in fnames:
            if fn.endswith(".jsonl"):
                types += [e["type"] for e in audit.read_events(os.path.join(root, fn))]
    return types


def _campaign_ledger_ok(camp_dir):
    audit_dir = os.path.join(camp_dir, "audit")
    ledger = os.path.join(audit_dir, os.listdir(audit_dir)[0])
    return audit.verify_chain(ledger).ok


class TestCampaignE2ESingleMilestone(unittest.TestCase):
    """Scenario A — one milestone, advisory Acceptance: real Driver runs Acceptance
    → campaign PAUSES at advisory_acceptance_pass_signoff → sign(ship) → DONE."""

    def test_advisory_acceptance_halt_then_ship_to_done(self):
        with tempfile.TemporaryDirectory() as d:
            # HOTL + auto + calibrated → acceptance is ADVISORY (not authoritative) →
            # a pass HALTS for human sign-off (P-A authority matrix).
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            adapters = _acceptance_adapters(ACC_PASS)
            clk = _clock()
            units, camp = os.path.join(d, "units"), os.path.join(d, "camp")
            plan = _plan("e2eA", [{"id": "m1", "objective": "deliver",
                                   "subsprint_sequence": ["sprint-001"]}])
            run_unit = cp.make_run_unit(charter, units, "e2eA", clock=clk,
                                        plan=plan, adapters=adapters)

            st = cp.run_campaign(plan, camp, run_unit, clock=clk)
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "advisory_acceptance_pass_signoff")
            self.assertTrue(st.units and st.units[0].get("loop_id"))
            # the campaign points at a REAL checkpoint file the Driver wrote.
            self.assertTrue(st.pause_checkpoint and os.path.isfile(st.pause_checkpoint))
            # the REAL Driver actually ran Acceptance for the milestone.
            m1_dir = os.path.join(units, st.units[0]["loop_id"])
            self.assertIn("acceptance_start", _driver_event_types(m1_dir))

            # resume(ship) → milestone accepted → campaign DONE.
            st2 = cp.run_campaign(plan, camp, run_unit, clock=clk,
                                  resume=True, decision_resolver=_SHIP)
            self.assertEqual(st2.status, cp.STATUS_DONE)

            # idempotency: a second resume after DONE is a no-op (no double-advance).
            st3 = cp.run_campaign(plan, camp, run_unit, clock=clk,
                                  resume=True, decision_resolver=_SHIP)
            self.assertEqual(st3.status, cp.STATUS_DONE)
            self.assertEqual(st3.milestone_index, st2.milestone_index)
            self.assertTrue(_campaign_ledger_ok(camp))


class TestCampaignE2EPerMilestoneAcceptance(unittest.TestCase):
    """REGRESSION (the P-B fix) — every milestone closes through its OWN Acceptance
    gate, even with a single shared charter whose campaign-wide terminal sub-sprint
    is sprint-002 (the exact shape that previously skipped Acceptance for m1):

        M1 exec → M1 Acceptance pause → sign/resume
        → M2 exec → M2 Acceptance pause → sign/resume → campaign DONE
    """

    def test_two_milestones_each_gated_by_their_own_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            # Shared charter whose campaign-wide terminal would be sprint-002 — before
            # the fix, m1/sprint-001 was NON-terminal → the Driver returned 'advance'
            # with NO Acceptance and the campaign walked straight on to m2.
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto",
                                          subsprint_sequence=("sprint-001", "sprint-002"))
            adapters = _acceptance_adapters(ACC_PASS)
            clk = _clock()
            units, camp = os.path.join(d, "units"), os.path.join(d, "camp")
            plan = _plan("e2eB", [
                {"id": "m1", "objective": "first", "subsprint_sequence": ["sprint-001"]},
                {"id": "m2", "objective": "second", "subsprint_sequence": ["sprint-002"]}])
            run_unit = cp.make_run_unit(charter, units, "e2eB", clock=clk,
                                        plan=plan, adapters=adapters)

            # ---- M1 execution → M1 Acceptance pause ----------------------------- #
            st1 = cp.run_campaign(plan, camp, run_unit, clock=clk)
            self.assertEqual(st1.status, cp.STATUS_PAUSED)
            self.assertEqual(
                st1.pause_reason, "advisory_acceptance_pass_signoff",
                "REGRESSION: m1 must close through its OWN Acceptance gate")
            self.assertEqual(st1.milestone_index, 0, "still on m1 (not advanced)")
            self.assertEqual(len(st1.units), 1, "only m1/sprint-001 has run")
            m1_unit = st1.units[0]
            self.assertEqual(m1_unit["milestone_id"], "m1")
            m1_dir = os.path.join(units, m1_unit["loop_id"])
            self.assertIn("acceptance_start", _driver_event_types(m1_dir),
                          "the REAL Driver ran Acceptance at m1's terminal sub-sprint")

            # M2 cannot start before M1 Acceptance is resolved — exactly one unit dir
            # exists (m1's), so m2's Driver never ran.
            self.assertEqual(sorted(os.listdir(units)), [m1_unit["loop_id"]],
                             "M2 must not run before M1 Acceptance is signed")
            self.assertFalse(
                os.path.isdir(os.path.join(units,
                                           _expected_loop_id("e2eB", "m2", "sprint-002"))))

            # Provenance: the derived context records the source hashes and is NOT a
            # re-signed charter (preserve provenance + hashes; no forged signature).
            prov = json.load(open(os.path.join(m1_dir, "derived-context.json")))
            self.assertEqual(prov["kind"], "per_milestone_execution_context")
            self.assertEqual(prov["milestone_id"], "m1")
            self.assertEqual(prov["subsprint_sequence"], ["sprint-001"])
            self.assertFalse(prov["customer_signed"])
            self.assertEqual(len(prov["derived_from"]["charter_sha256"]), 64)
            self.assertEqual(len(prov["derived_from"]["campaign_plan_sha256"]), 64)

            # ---- sign/resume → M2 execution → M2 Acceptance pause --------------- #
            st2 = cp.run_campaign(plan, camp, run_unit, clock=clk,
                                  resume=True, decision_resolver=_SHIP)
            self.assertEqual(st2.status, cp.STATUS_PAUSED)
            self.assertEqual(st2.pause_reason, "advisory_acceptance_pass_signoff")
            self.assertEqual(st2.milestone_index, 1, "now on m2")

            # resume did NOT repeat m1 or duplicate its Acceptance.
            m1_units = [u for u in st2.units if u["milestone_id"] == "m1"]
            self.assertEqual(len(m1_units), 1, "m1 must not be re-run on resume")
            self.assertEqual(
                _driver_event_types(m1_dir).count("acceptance_start"), 1,
                "m1 Acceptance must not be duplicated by the resume")

            m2_unit = [u for u in st2.units if u["milestone_id"] == "m2"][0]
            m2_dir = os.path.join(units, m2_unit["loop_id"])
            self.assertIn("acceptance_start", _driver_event_types(m2_dir),
                          "m2 also closes through its own Acceptance gate")

            # each milestone has DISTINCT prompt/output/checkpoint/audit references.
            self.assertNotEqual(m1_unit["loop_id"], m2_unit["loop_id"])
            self.assertNotEqual(m1_dir, m2_dir)
            self.assertTrue(os.path.isdir(os.path.join(m1_dir, "docs", "checkpoints")))
            self.assertTrue(os.path.isdir(os.path.join(m2_dir, "docs", "checkpoints")))
            m2_prov = json.load(open(os.path.join(m2_dir, "derived-context.json")))
            self.assertEqual(m2_prov["milestone_id"], "m2")
            self.assertEqual(m2_prov["subsprint_sequence"], ["sprint-002"])

            # ---- sign/resume → campaign DONE (only after the FINAL gate) -------- #
            st3 = cp.run_campaign(plan, camp, run_unit, clock=clk,
                                  resume=True, decision_resolver=_SHIP)
            self.assertEqual(st3.status, cp.STATUS_DONE,
                             "DONE occurs only after the final milestone's gate")
            self.assertEqual(st3.milestone_index, 2, "both milestones complete")
            self.assertTrue(_campaign_ledger_ok(camp))


class TestCampaignE2EMultiSubsprintMilestone(unittest.TestCase):
    """A milestone with >1 sub-sprint (delivery_only): the NON-terminal sub-sprint
    advances with NO Acceptance (mid-milestone), and ONLY the milestone's terminal
    sub-sprint fires the Acceptance gate (Codex P-B review #1/#2 — the >1-sub-sprint
    case the single-sub-sprint regression did not prove)."""

    def test_acceptance_fires_only_at_the_milestone_terminal_subsprint(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto",
                                          subsprint_sequence=("sprint-001", "sprint-002"))
            adapters = _acceptance_adapters(ACC_PASS)
            clk = _clock()
            units, camp = os.path.join(d, "units"), os.path.join(d, "camp")
            plan = _plan("e2eC", [{"id": "m1", "objective": "two-step",
                                   "subsprint_sequence": ["sprint-001", "sprint-002"]}])
            run_unit = cp.make_run_unit(charter, units, "e2eC", clock=clk,
                                        plan=plan, adapters=adapters)

            st = cp.run_campaign(plan, camp, run_unit, clock=clk)
            # The first sub-sprint advanced; the campaign paused at the SECOND
            # (terminal) sub-sprint's Acceptance gate.
            self.assertEqual(st.status, cp.STATUS_PAUSED)
            self.assertEqual(st.pause_reason, "advisory_acceptance_pass_signoff")
            self.assertEqual(len(st.units), 2)
            s1, s2 = st.units[0], st.units[1]
            self.assertEqual((s1["subsprint_id"], s1["final_state"]),
                             ("sprint-001", "advance"))
            self.assertEqual(s2["subsprint_id"], "sprint-002")
            # The NON-terminal sub-sprint ran NO Acceptance; the terminal one did.
            self.assertNotIn("acceptance_start",
                             _driver_event_types(os.path.join(units, s1["loop_id"])),
                             "a mid-milestone sub-sprint must NOT trigger Acceptance")
            self.assertIn("acceptance_start",
                          _driver_event_types(os.path.join(units, s2["loop_id"])),
                          "the milestone's terminal sub-sprint MUST trigger Acceptance")
            # Both units derived the SAME (whole-milestone) sequence — terminality is a
            # position within it, so distinct refs but one shared sequence projection.
            for u in (s1, s2):
                prov = json.load(open(os.path.join(units, u["loop_id"],
                                                   "derived-context.json")))
                self.assertEqual(prov["subsprint_sequence"], ["sprint-001", "sprint-002"])
            self.assertNotEqual(s1["loop_id"], s2["loop_id"])

            # sign → milestone accepted → campaign DONE (single milestone).
            st2 = cp.run_campaign(plan, camp, run_unit, clock=clk,
                                  resume=True, decision_resolver=_SHIP)
            self.assertEqual(st2.status, cp.STATUS_DONE)


class TestCampaignE2EFailClosed(unittest.TestCase):
    """Scenario D — a real Driver GateHardFail PAUSES the campaign without advancing
    (not a crash, not a false DONE), and the next milestone never runs."""

    def test_gate_hard_fail_pauses_without_advancing(self):
        with tempfile.TemporaryDirectory() as d:
            # An acceptance verdict citing a CODE path (not eval/runs/...) is
            # schema-invalid → the REAL Driver raises GateHardFail at m1's close.
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            adapters = _acceptance_adapters(ACC_INVALID_CODE_ONLY)
            clk = _clock()
            units, camp = os.path.join(d, "units"), os.path.join(d, "camp")
            plan = _plan("e2eD", [
                {"id": "m1", "objective": "x", "subsprint_sequence": ["sprint-001"]},
                {"id": "m2", "objective": "y", "subsprint_sequence": ["sprint-002"]}])
            run_unit = cp.make_run_unit(charter, units, "e2eD", clock=clk,
                                        plan=plan, adapters=adapters)

            st = cp.run_campaign(plan, camp, run_unit, clock=clk)  # MUST NOT raise
            self.assertEqual(st.status, cp.STATUS_PAUSED, "not a crash, not a DONE")
            self.assertEqual(st.pause_reason, "gate_hard_fail")
            self.assertEqual(st.milestone_index, 0, "did NOT advance past the failure")
            self.assertEqual(sorted(os.listdir(units)), [st.units[0]["loop_id"]],
                             "m2 never ran")


if __name__ == "__main__":
    unittest.main()
