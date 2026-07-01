"""Track-2 AUTONOMY NON-REGRESSION verification (the Track-2 invariant).

The Track-2 freshness / signed-input hardening MUST be behavior-neutral for a normal
autonomous loop: only a POST-SIGNOFF edit to an authority-bearing SIGNED field may pause
(fail-closed, for re-sign). Normal runtime state changes — cursor advance, unit-ledger
growth, gap_followup_state, the engine-authored deliver_followup insertion (an AUTHORIZED
runtime delta the engine re-stamps), gap-remediation dispatch, milestone_outcomes, and the
recomputed gap report — must NEVER flip the plan to 'stale' nor raise a freshness_block.

This module RUNS real multi-invocation campaigns covering dispatch, deliver_followup
re-stamp, gap remediation, and resume / crash-recovery, and asserts on EVERY observed state
+ the whole audit ledger:
  * the loop completes autonomously (STATUS_DONE) with NO human re-sign / manual step;
  * `freshness_block` is NEVER set;
  * NO `campaign_plan_signoff` pause occurs mid-loop;
  * NO `campaign_freshness_block` audit event is emitted.
It then reproduces the ORIGINAL attack (post-signoff gap_followup.max_subsprints 1→2) to
confirm ONLY that authority escalation fails closed — with NO new remediation dispatch —
while the byte-identical loop WITHOUT the edit completes autonomously.

Invariant: normal autonomous loop is behavior-equivalent; only post-signoff authority
escalation pauses.
"""
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402
import audit_log as audit  # noqa: E402

_STATIC_CHARTER = {"tooling": {"acceptance": {"functional": {"mode": "static"}}}}
# human_on_the_loop ⇒ the §1.7-F gap-followup AUTO-dispatches an in-envelope remediation
# with NO human pause (a genuinely autonomous loop).
_ONL_CHARTER = {"autonomy": {"level": "human_on_the_loop"},
                "tooling": {"acceptance": {"functional": {"mode": "static"}}}}


def _clock():
    n = {"i": 0}

    def tick() -> str:
        n["i"] += 1
        return f"2026-07-01T00:{n['i'] // 60:02d}:{n['i'] % 60:02d}Z"
    return tick


def _covms(mid, seq, reqs):
    return {"id": mid, "objective": f"o {mid}", "subsprint_sequence": list(seq),
            "covers_req_ids": list(reqs)}


def _signed(milestones, charter, **extra):
    plan = {"campaign_id": "camp-auto", "goal": "autonomy invariant",
            "signed_by_human": True, "milestones": milestones, **extra}
    return cp.stamp_signoff(plan, charter, signed_at="t")


def _ledger(reqs):
    return {"version": "v1", "requirements": [
        {"id": r, "statement": f"stmt {r}", "source": {"channel": "prd"},
         "customer_disposition": "accepted"} for r in reqs]}


def _fresh(pf):
    """A fresh deep copy — models the prod per-invocation plan-file load (run_loop.py
    json.loads), so an in-memory engine re-stamp never carries across invocations."""
    return json.loads(json.dumps(pf))


def _run_unit(script, record=None):
    """subsprint_id → summary; records each call so a test can assert dispatch happened
    (and, in the attack, that a would-be escalated round was NEVER dispatched)."""
    def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                 resume=False, functional_acceptance=None, repo_dir=None,
                 covered_req_ids=None, gap_followup_spec=None, **_kw):
        if record is not None:
            record.append({"subsprint_id": subsprint_id, "resume": resume,
                           "covered_req_ids": covered_req_ids})
        return dict(script[subsprint_id])
    return run_unit


def _fix_route():
    return lambda reason, cpt: (
        {"confirm": "yes", "route": "deliver_fix_iteration"}
        if reason == "acceptance_fix_required" else None)


class Track2AutonomyInvariant(unittest.TestCase):
    """Every scenario collects EVERY returned CampaignState and asserts the Track-2
    invariant against the persisted states + the campaign audit ledger."""

    def _audit_ledger(self, home):
        return audit.audit_path("camp-auto", os.path.join(home, "audit"))

    def _assert_invariant(self, states, home, *, final_status=cp.STATUS_DONE,
                          require_restamp=False):
        # (1) NO state ever carries a freshness_block (the durable re-sign overlay).
        for i, st in enumerate(states):
            self.assertIsNone(getattr(st, "freshness_block", None),
                              f"state[{i}] raised a freshness_block: {st.freshness_block}")
        # (2) NO mid-loop campaign_plan_signoff pause (the re-sign gate).
        for i, st in enumerate(states):
            self.assertNotEqual(st.pause_reason, "campaign_plan_signoff",
                                f"state[{i}] paused for re-sign unexpectedly")
        # (3) the audit ledger emitted NO freshness-block event.
        events = audit.read_events(self._audit_ledger(home))
        kinds = [e.get("type") for e in events]
        self.assertNotIn("campaign_freshness_block", kinds,
                         "a campaign_freshness_block event was emitted for a normal loop")
        # (4) autonomous terminal outcome (no human re-sign / manual recovery step used).
        self.assertEqual(states[-1].status, final_status)
        # (5) any persisted state.json is schema-valid (the overlay/re-stamp fields are
        #     additive + round-trip cleanly).
        state_path = os.path.join(home, "campaign-state.json")
        if os.path.isfile(state_path):
            with open(state_path, encoding="utf-8") as fh:
                cp._validate_or_raise(json.load(fh), "campaign-state.schema.json", "state")
        if require_restamp:
            self.assertIsNotNone(states[-1].engine_restamp,
                                 "the authorized deliver_followup delta was not re-stamped")

    # ----- Scenario A: the normal autonomous loop is behavior-equivalent ----- #
    def test_dispatch_followup_restamp_resume_is_transparent(self):
        # DISPATCH + FOLLOW-UP (engine deliver_followup re-stamp — an AUTHORIZED runtime
        # delta that GROWS subsprint_sequence, which is inside the signed hash) + RESUME.
        # The grown sequence must be absorbed by the re-stamp with ZERO freshness_block.
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "camp")
            pf = _signed([_covms("m1", ["s1", "s2"], ["REQ-1"])], _STATIC_CHARTER)
            script = {"s1": {"final_state": "advance", "spawn_count": 1},
                      "s2": {"final_state": "halted", "spawn_count": 1,
                             "pause_reason": "acceptance_fix_required"},
                      "s_fix": {"final_state": "done", "spawn_count": 1}}
            states = []
            states.append(cp.run_campaign(_fresh(pf), home, _run_unit(script),
                                          clock=_clock(), charter=_STATIC_CHARTER))
            self.assertEqual(states[-1].pause_reason, "acceptance_fix_required")
            states.append(cp.run_campaign(_fresh(pf), home, _run_unit(script),
                                          clock=_clock(), charter=_STATIC_CHARTER,
                                          resume=True, decision_resolver=_fix_route()))
            self.assertEqual(states[-1].pause_reason, "deliver_followup_required")
            # Deliver inserts the follow-up at cursor+1 in the PLAN FILE (signoff untouched).
            pf["milestones"][0]["subsprint_sequence"] = ["s1", "s2", "s_fix"]
            states.append(cp.run_campaign(_fresh(pf), home, _run_unit(script),
                                          clock=_clock(), charter=_STATIC_CHARTER,
                                          resume=True))
            self._assert_invariant(states, home, require_restamp=True)

    def test_crash_recovery_of_signed_plan_is_transparent(self):
        # RESUME / CRASH-RECOVERY: a STATUS_RUNNING recovery whose cursor points at a
        # not-yet-recorded unit re-dispatches and completes — the unconditional per-dispatch
        # gate is a NO-OP for the (unchanged) signed plan.
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "camp")
            pf = _signed([_covms("m1", ["s1", "s2"], ["REQ-1"])], _STATIC_CHARTER)
            # Prime a crashed RUNNING state: s1 recorded+advanced, cursor at s2 (never run).
            seed = cp.Campaign(_fresh(pf), home, _run_unit({}), clock=_clock(),
                               charter=_STATIC_CHARTER)
            seed.state.status = cp.STATUS_RUNNING
            seed.state.subsprint_index = 1
            seed.state.units = [{"milestone_id": "m1", "subsprint_id": "s1",
                                 "status": "done", "final_state": "advance"}]
            seed._save()
            script = {"s2": {"final_state": "done", "spawn_count": 1}}
            st = cp.run_campaign(_fresh(pf), home, _run_unit(script), clock=_clock(),
                                 charter=_STATIC_CHARTER, resume=True)
            self._assert_invariant([st], home)

    def test_gap_remediation_autoloop_is_transparent(self):
        # GAP REMEDIATION: a human_on_the_loop campaign resumes into a §1.7-F completeness
        # gap and AUTO-dispatches an in-envelope remediation round to DONE — no pause, no
        # re-sign. The remediation is a RUNTIME delta (it never edits the signed plan), so
        # the plan stays 'signed' throughout.
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "camp")
            ledger_path = os.path.join(d, "ledger.json")
            with open(ledger_path, "w", encoding="utf-8") as fh:
                json.dump(_ledger(["REQ-1"]), fh)
            pf = _signed([_covms("m1", ["s1"], ["REQ-1"])], _ONL_CHARTER)
            ru = _run_unit({"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}})
            # Seed a real mid-loop RUNNING state at backlog-exhausted with an in-envelope gap
            # (m1's covers signed but not yet delivered) — the idiomatic resume-into-gap state.
            seed = cp.Campaign(_fresh(pf), home, ru, clock=_clock(),
                               charter=_ONL_CHARTER, ledger_path=ledger_path)
            seed.state.milestone_index = len(seed.milestones)
            seed.state.units = [{"milestone_id": "m1", "subsprint_id": "s1",
                                 "status": "done", "final_state": "advance"}]
            seed.state.status = cp.STATUS_RUNNING
            seed._save()
            st = cp.Campaign(_fresh(pf), home, ru, clock=_clock(), charter=_ONL_CHARTER,
                             ledger_path=ledger_path).run(resume=True)
            self._assert_invariant([st], home)
            # Proof the remediation actually ran autonomously (not a no-op finish).
            self.assertEqual(st.gap_followup_state["rounds_by_milestone"]["m1"], 1)
            self.assertEqual(cp.signoff_status(_fresh(pf), _ONL_CHARTER), "signed")

    # ----- Scenario B: ONLY a post-signoff authority escalation fails closed ----- #
    def _seed_gap_after_round1(self, home, ledger_path, pf, ru):
        """A RUNNING state seeded AFTER remediation round 1, with the gap still open — so
        the NEXT _gap_followup_round would attempt round 2 (bounded by max_subsprints)."""
        c = cp.Campaign(_fresh(pf), home, ru, clock=_clock(), charter=_ONL_CHARTER,
                        ledger_path=ledger_path)
        c.state.milestone_index = len(c.milestones)
        c.state.units = [{"milestone_id": "m1", "subsprint_id": "s1",
                          "status": "done", "final_state": "advance"}]
        c.state.status = cp.STATUS_RUNNING
        c.state.gap_followup_state = {"rounds_by_milestone": {"m1": 1},
                                      "gap_set_history": [["REQ-1", "REQ-2"]],
                                      "no_progress_rounds": 0, "remediations": []}
        c._save()
        return c

    def test_original_attack_max_subsprints_escalation_fails_closed(self):
        # ORIGINAL ATTACK REPRODUCTION: sign with gap_followup.max_subsprints:1; a second
        # remediation round is genuinely needed. Bumping max_subsprints 1→2 POST-SIGNOFF
        # (the authority escalation) must fail closed — gap_followup is now inside the signed
        # hash, so the edit reads 'stale' and the gap-followup re-pauses for re-sign WITHOUT
        # dispatching the escalated round. A control WITHOUT the edit is byte-behaviorally the
        # normal (bounded) autonomous path.
        with tempfile.TemporaryDirectory() as d:
            ledger_path = os.path.join(d, "ledger.json")
            with open(ledger_path, "w", encoding="utf-8") as fh:
                json.dump(_ledger(["REQ-1", "REQ-2"]), fh)
            ms = [_covms("m1", ["s1"], ["REQ-1", "REQ-2"])]

            # --- ATTACK: max_subsprints 1→2 after signoff (no re-sign) → stale → blocked. ---
            attack_home = os.path.join(d, "attack")
            pf = _signed(ms, _ONL_CHARTER, gap_followup={"max_subsprints": 1,
                                                         "max_no_progress_rounds": 1})
            rec = []
            ru = _run_unit({"m1-gapfix-2": {"final_state": "done", "spawn_count": 1}}, rec)
            self._seed_gap_after_round1(attack_home, ledger_path, pf, ru)
            escalated = _fresh(pf)
            escalated["gap_followup"] = {"max_subsprints": 2, "max_no_progress_rounds": 1}
            self.assertEqual(cp.signoff_status(escalated, _ONL_CHARTER), "stale")
            blocked = cp.Campaign(escalated, attack_home, ru, clock=_clock(),
                                  charter=_ONL_CHARTER,
                                  ledger_path=ledger_path).run(resume=True)
            self.assertEqual(blocked.status, cp.STATUS_PAUSED)          # fail-closed
            self.assertEqual(blocked.pause_reason, cp.GAP_REVIEW_CHECKPOINT)
            self.assertEqual(rec, [])                                  # NO new dispatch
            self.assertIsNone(blocked.freshness_block)  # the boundary block uses the §1.7-F
            #                                             completeness gate, not the overlay
            # The escalation is caught by the Track-2 FRESHNESS path (not_fresh_signed) —
            # a stale signed plan at the gap-followup, NOT a silent finish, NOT a new round.
            attack_blocked = [e.get("payload") or {} for e in audit.read_events(
                audit.audit_path("camp-auto", os.path.join(attack_home, "audit")))
                if e.get("type") == "campaign_gap_followup_blocked"]
            self.assertTrue(any(p.get("reason") == "not_fresh_signed"
                                for p in attack_blocked))

            # --- CONTROL: NO authority edit → the signed bound (max_subsprints:1) governs
            #     autonomously; a would-be second round is refused by the SIGNED bound
            #     (max_subsprints_exceeded → needs_human), NOT by any re-sign / freshness
            #     gate, and STILL dispatches nothing new. This is the pre-Track-2 behavior. ---
            ctl_home = os.path.join(d, "control")
            rec2 = []
            ru2 = _run_unit({"m1-gapfix-2": {"final_state": "done", "spawn_count": 1}}, rec2)
            self._seed_gap_after_round1(ctl_home, ledger_path, pf, ru2)
            ctl = cp.Campaign(_fresh(pf), ctl_home, ru2, clock=_clock(),
                              charter=_ONL_CHARTER,
                              ledger_path=ledger_path).run(resume=True)
            self.assertEqual(ctl.status, cp.STATUS_PAUSED)
            self.assertEqual(ctl.pause_reason, cp.GAP_REVIEW_CHECKPOINT)
            self.assertEqual(rec2, [])                                 # no new dispatch
            self.assertIsNone(ctl.freshness_block)                     # NO freshness path
            ctl_blocked = [e.get("payload") or {} for e in audit.read_events(
                audit.audit_path("camp-auto", os.path.join(ctl_home, "audit")))
                if e.get("type") == "campaign_gap_followup_blocked"]
            # The unedited loop halts on the SIGNED bound — never the freshness path.
            self.assertTrue(any("max_subsprints_exceeded" in (p.get("reason") or "")
                                for p in ctl_blocked))
            self.assertFalse(any(p.get("reason") == "not_fresh_signed"
                                 for p in ctl_blocked))

    def test_signed_higher_bound_is_honored_autonomously(self):
        # The freshness gate blocks the post-signoff ESCALATION (a stale edit), NOT the value:
        # a plan SIGNED with max_subsprints:2 is fresh-signed and its gap-followup dispatches +
        # completes autonomously with no pause. (Proof the fix does not over-block a
        # legitimately-signed higher bound.)
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "camp")
            ledger_path = os.path.join(d, "ledger.json")
            with open(ledger_path, "w", encoding="utf-8") as fh:
                json.dump(_ledger(["REQ-1"]), fh)
            pf = _signed([_covms("m1", ["s1"], ["REQ-1"])], _ONL_CHARTER,
                         gap_followup={"max_subsprints": 2, "max_no_progress_rounds": 1})
            self.assertEqual(cp.signoff_status(_fresh(pf), _ONL_CHARTER), "signed")
            rec = []
            ru = _run_unit({"m1-gapfix-1": {"final_state": "done", "spawn_count": 1}}, rec)
            seed = cp.Campaign(_fresh(pf), home, ru, clock=_clock(), charter=_ONL_CHARTER,
                               ledger_path=ledger_path)
            seed.state.milestone_index = len(seed.milestones)
            seed.state.units = [{"milestone_id": "m1", "subsprint_id": "s1",
                                 "status": "done", "final_state": "advance"}]
            seed.state.status = cp.STATUS_RUNNING
            seed._save()
            st = cp.Campaign(_fresh(pf), home, ru, clock=_clock(), charter=_ONL_CHARTER,
                             ledger_path=ledger_path).run(resume=True)
            self.assertEqual([r["subsprint_id"] for r in rec], ["m1-gapfix-1"])  # dispatched
            self._assert_invariant([st], home)


if __name__ == "__main__":
    unittest.main()
