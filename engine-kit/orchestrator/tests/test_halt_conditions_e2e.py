"""Phase-3 halt-conditions — campaign-level E2E (design §3.4/§3.5). Offline +
deterministic (a fake run_unit, no Driver/adapters). Drives cp.run_campaign directly
(the notifier lives one layer up in run_campaign_entry — see test_run_loop_campaign).

Covers: canary (a) pre-set halt with the right checkpoint + facts (two-pause cascade,
nonce seq, per-condition ack, declaration order, identity-bound refusal, abort);
byte-identical-when-absent; and the ack lifecycle under drift / crash / engine_restamp
(the corner the R0.3–R0.6 gate rounds drilled)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402
import run_loop as rl  # noqa: E402


def _clock():
    n = {"i": 0}

    def tick():
        n["i"] += 1
        return f"2026-06-20T00:{n['i'] // 60:02d}:{n['i'] % 60:02d}Z"
    return tick


def _run_unit(final_by_milestone):
    def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                 resume=False, functional_acceptance=None, repo_dir=None):
        return {"final_state": final_by_milestone.get(milestone_id, "advance"),
                "spawn_count": 1, "loop_id": f"L-{subsprint_id}"}
    return run_unit


def _plan(milestones):
    return {"campaign_id": "camp-1", "goal": "g", "signed_by_human": True,
            "milestones": milestones}


def _charter(conditions):
    return {"autonomy": {"halt_conditions": conditions}}


_TWO_MS = [{"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
           {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"],
            "functional_acceptance": "browser_e2e"}]
_FINAL = {"m2": "done"}   # m1 advances, m2 done


def _decision(d, *, condition_id, checkpoint, choice="proceed", milestone_id="m2",
              **extra):
    dec = {"campaign_id": "camp-1", "pause_reason": "halt_condition_met",
           "checkpoint": checkpoint, "milestone_id": milestone_id,
           "condition_id": condition_id, "choice": choice}
    dec.update(extra)
    path = os.path.join(d, "dec.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(dec, fh)
    return path


def _resume(plan, charter, d, decision_path, clk):
    return cp.run_campaign(
        plan, d, _run_unit(_FINAL), clock=clk, charter=charter, resume=True,
        decision_resolver=rl.make_campaign_decision_resolver("camp-1", decision_path, d))


class CanaryA_TwoPauseCascade(unittest.TestCase):
    def test_two_conditions_pause_in_order_then_dispatch(self):
        conditions = [
            {"id": "hot-milestone",
             "when": {"metric": "milestone_id", "op": "in", "value": ["m2"]}},
            {"id": "gate-e2e",
             "when": {"metric": "milestone_functional_acceptance", "op": "==",
                      "value": "browser_e2e"}}]
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            plan, charter = _plan(_TWO_MS), _charter(conditions)
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter)
            # (a) first pause: declaration-order → hot-milestone, nonce r1, facts recorded.
            self.assertEqual(st.pause_reason, "halt_condition_met")
            self.assertTrue(st.pause_checkpoint.endswith("__halt_condition_met__r1.md"))
            self.assertEqual(st.halt_condition_pending["condition_id"], "hot-milestone")
            self.assertEqual(st.halt_condition_pending["facts"], {"milestone_id": "m2"})
            ck1 = os.path.basename(st.pause_checkpoint)

            # proceed hot-milestone → SECOND pause: gate-e2e, nonce r2 (distinct), provisional
            # carries hot-milestone's key.
            st = _resume(plan, charter, d,
                         _decision(d, condition_id="hot-milestone", checkpoint=ck1), clk)
            self.assertEqual(st.pause_reason, "halt_condition_met")
            self.assertTrue(st.pause_checkpoint.endswith("__halt_condition_met__r2.md"))
            self.assertEqual(st.halt_condition_pending["condition_id"], "gate-e2e")
            self.assertEqual(st.halt_condition_pending["facts"],
                             {"milestone_functional_acceptance": "browser_e2e"})
            self.assertEqual(len(st.halt_condition_provisional), 1)
            ck2 = os.path.basename(st.pause_checkpoint)

            # proceed gate-e2e → both committed permanent, cascade cleared, campaign done.
            st = _resume(plan, charter, d,
                         _decision(d, condition_id="gate-e2e", checkpoint=ck2), clk)
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(len(st.halt_condition_acks), 2)
            self.assertEqual(st.halt_condition_provisional, [])
            self.assertIsNone(st.halt_condition_pending)

    def test_wrong_condition_id_is_refused(self):
        conditions = [{"id": "hot-milestone",
                       "when": {"metric": "milestone_id", "op": "in", "value": ["m2"]}}]
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            plan, charter = _plan(_TWO_MS), _charter(conditions)
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter)
            ck = os.path.basename(st.pause_checkpoint)
            # wrong condition_id → resolver refuses → re-pause.
            st = _resume(plan, charter, d,
                         _decision(d, condition_id="not-a-real-condition", checkpoint=ck),
                         clk)
            self.assertEqual(st.pause_reason, "halt_condition_met")

    def test_subsprint_id_in_decision_is_refused(self):
        conditions = [{"id": "hot-milestone",
                       "when": {"metric": "milestone_id", "op": "in", "value": ["m2"]}}]
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            plan, charter = _plan(_TWO_MS), _charter(conditions)
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter)
            ck = os.path.basename(st.pause_checkpoint)
            path = _decision(d, condition_id="hot-milestone", checkpoint=ck,
                             subsprint_id="s2")  # forbidden for this gate
            st = _resume(plan, charter, d, path, clk)
            self.assertEqual(st.pause_reason, "halt_condition_met")

    def test_abort_ends_campaign_and_clears_overlay(self):
        conditions = [{"id": "hot-milestone",
                       "when": {"metric": "milestone_id", "op": "in", "value": ["m2"]}}]
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            plan, charter = _plan(_TWO_MS), _charter(conditions)
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter)
            ck = os.path.basename(st.pause_checkpoint)
            st = _resume(plan, charter, d,
                         _decision(d, condition_id="hot-milestone", checkpoint=ck,
                                   choice="abort"), clk)
            self.assertEqual(st.status, cp.STATUS_ENDED)
            self.assertIsNone(st.halt_condition_pending)
            self.assertEqual(st.halt_condition_provisional, [])


class CanaryB_ByteIdentical(unittest.TestCase):
    def test_no_conditions_is_byte_identical(self):
        # Same scripted plan, run with an EMPTY halt_conditions charter vs NO charter block:
        # identical exit status, and NO halt-condition fields ever serialized.
        def run(charter):
            with tempfile.TemporaryDirectory() as d:
                st = cp.run_campaign(_plan(_TWO_MS), d, _run_unit(_FINAL),
                                     clock=_clock(), charter=charter)
                with open(os.path.join(d, "campaign-state.json"), encoding="utf-8") as fh:
                    state = json.load(fh)
                return st.status, state

        s_absent, st_absent = run({"autonomy": {}})
        s_empty, st_empty = run({"autonomy": {"halt_conditions": []}})
        self.assertEqual(s_absent, cp.STATUS_DONE)
        self.assertEqual(s_absent, s_empty)
        for state in (st_absent, st_empty):
            for k in ("halt_condition_acks", "halt_condition_provisional",
                      "halt_condition_pending", "halt_condition_seq"):
                self.assertNotIn(k, state, f"{k} leaked into serialized state when absent")


class AckLifecycle(unittest.TestCase):
    """The corner the R0.3–R0.6 gate rounds drilled: drift / crash / engine_restamp."""

    def _one_condition_plan(self):
        return (_plan(_TWO_MS),
                _charter([{"id": "hot-milestone",
                           "when": {"metric": "milestone_id", "op": "in",
                                    "value": ["m2"]}}]))

    def test_drift_before_proceed_re_arms_whole_cascade(self):
        # Halt at epoch H0; RE-SIGN to H1 before the resume → the redispatch EP-pre flushes
        # the provisional cascade and the condition re-arms with a FRESH nonce (design §3.4
        # [R0.6 B-1]). Simulated via a controlled _live_signed_scope_hash.
        plan, charter = self._one_condition_plan()
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            with mock.patch.object(cp.Campaign, "_live_signed_scope_hash",
                                   return_value="H0"):
                st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter)
                ck1 = os.path.basename(st.pause_checkpoint)
                self.assertEqual(st.halt_condition_pending["signed_scope_hash"], "H0")
            # Re-sign to a NEW epoch, then proceed the (now stale-epoch) decision.
            with mock.patch.object(cp.Campaign, "_live_signed_scope_hash",
                                   return_value="H1"):
                st = _resume(plan, charter, d,
                             _decision(d, condition_id="hot-milestone", checkpoint=ck1), clk)
            # Re-armed: a NEW halt (fresh nonce), provisional flushed, no permanent ack.
            self.assertEqual(st.pause_reason, "halt_condition_met")
            self.assertNotEqual(os.path.basename(st.pause_checkpoint), ck1)
            self.assertEqual(st.halt_condition_acks, [])
            self.assertEqual(st.halt_condition_pending["signed_scope_hash"], "H1")

    def test_milestone_scoped_ack_fires_once_per_milestone(self):
        # A milestone_id condition on a 2-sub-sprint milestone halts + commits at the FIRST
        # sub-sprint; the SECOND sub-sprint's EP-pre (same milestone) is SKIPPED via the
        # committed permanent ack — a milestone gate is a once-per-milestone act, and the
        # commit persists across sub-sprints. (The provisional/pending epoch logic never
        # touches a permanent ack — hash-independence is structural, design §3.4 [R0.3/R0.5
        # B-3]; the drift test above exercises the provisional flush.)
        plan = _plan([{"id": "m1", "objective": "a",
                       "subsprint_sequence": ["s1", "s2"]}])
        charter = _charter([{"id": "watch-m1",
                             "when": {"metric": "milestone_id", "op": "==",
                                      "value": "m1"}}])
        run_unit = _run_unit({})  # both sub-sprints advance; milestone completes after s2
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            with mock.patch.object(cp.Campaign, "_live_signed_scope_hash",
                                   return_value="H0"):
                st = cp.run_campaign(plan, d, run_unit, clock=clk, charter=charter)
                ck = os.path.basename(st.pause_checkpoint)
                self.assertEqual(st.halt_condition_pending["condition_id"], "watch-m1")
                # Proceed (same epoch) → s1 commits the ack, s2 is skipped (once-per-milestone).
                st = cp.run_campaign(
                    plan, d, run_unit, clock=clk, charter=charter, resume=True,
                    decision_resolver=rl.make_campaign_decision_resolver(
                        "camp-1", _decision(d, condition_id="watch-m1", checkpoint=ck,
                                            milestone_id="m1"), d))
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(len(st.halt_condition_acks), 1)   # fired ONCE, not per sub-sprint
            self.assertEqual(st.subsprints_run, 2)             # both sub-sprints ran

    def test_crash_replay_after_proceed_is_idempotent(self):
        # After proceed persists the provisional ack (state still PAUSED), a crash → reload
        # → replay re-binds the same decision idempotently and completes (design §3.5 [R0.4
        # B-1]/[R0.3 B-2]).
        plan, charter = self._one_condition_plan()
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter)
            ck = os.path.basename(st.pause_checkpoint)
            dec = _decision(d, condition_id="hot-milestone", checkpoint=ck)
            resolver = rl.make_campaign_decision_resolver("camp-1", dec, d)
            # First resume completes the campaign.
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter,
                                 resume=True, decision_resolver=resolver)
            self.assertEqual(st.status, cp.STATUS_DONE)
            # Idempotent replay: resuming the DONE state with the same decision is a no-op.
            st2 = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter,
                                  resume=True, decision_resolver=resolver)
            self.assertEqual(st2.status, cp.STATUS_DONE)
            self.assertEqual(len(st2.halt_condition_acks), 1)


class AckLifecycleVariants(unittest.TestCase):
    """The remaining design §6 ack-lifecycle variants (R2 B-2)."""

    _TWO_COND = [
        {"id": "hot-milestone",
         "when": {"metric": "milestone_id", "op": "in", "value": ["m2"]}},
        {"id": "gate-e2e",
         "when": {"metric": "milestone_functional_acceptance", "op": "==",
                  "value": "browser_e2e"}}]

    def _resolver(self, d, cid, ck, choice="proceed", mid="m2"):
        return rl.make_campaign_decision_resolver(
            "camp-1", _decision(d, condition_id=cid, checkpoint=ck, choice=choice,
                                milestone_id=mid), d)

    def test_multi_drift_re_arms_the_whole_cascade(self):
        # Two conditions provisional (hot proceeded → gate-e2e pending); a re-sign before the
        # SECOND proceed flushes BOTH and re-arms from the top in the new epoch [R0.5 B-1].
        plan, charter = _plan(_TWO_MS), _charter(self._TWO_COND)
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            with mock.patch.object(cp.Campaign, "_live_signed_scope_hash",
                                   return_value="H0"):
                st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter)
                ck1 = os.path.basename(st.pause_checkpoint)
                st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter,
                                     resume=True,
                                     decision_resolver=self._resolver(d, "hot-milestone", ck1))
                self.assertEqual(st.halt_condition_pending["condition_id"], "gate-e2e")
                ck2 = os.path.basename(st.pause_checkpoint)
            # Re-sign to a NEW epoch, then proceed gate-e2e → flush [hot, gate-e2e] + re-arm.
            with mock.patch.object(cp.Campaign, "_live_signed_scope_hash",
                                   return_value="H1"):
                st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter,
                                     resume=True,
                                     decision_resolver=self._resolver(d, "gate-e2e", ck2))
            # hot-milestone re-fired from scratch (whole cascade re-presented), acks empty.
            self.assertEqual(st.pause_reason, "halt_condition_met")
            self.assertEqual(st.halt_condition_pending["condition_id"], "hot-milestone")
            self.assertEqual(st.halt_condition_acks, [])

    def test_stale_earlier_nonce_is_refused_at_the_next_pause(self):
        # After proceeding r1 (hot) → the pause is r2 (gate-e2e). The OLD r1 decision must NOT
        # bind at the r2 pause (nonce rolled) — the gate re-pauses at r2.
        plan, charter = _plan(_TWO_MS), _charter(self._TWO_COND)
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter)
            ck1 = os.path.basename(st.pause_checkpoint)
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter,
                                 resume=True,
                                 decision_resolver=self._resolver(d, "hot-milestone", ck1))
            self.assertTrue(st.pause_checkpoint.endswith("__r2.md"))
            # Replay the STALE r1 decision (wrong nonce for the live r2 pause) → refused.
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter,
                                 resume=True,
                                 decision_resolver=self._resolver(d, "hot-milestone", ck1))
            self.assertEqual(st.pause_reason, "halt_condition_met")
            self.assertTrue(st.pause_checkpoint.endswith("__r2.md"))   # still parked at r2

    def test_changed_when_under_same_id_re_fires(self):
        # digest-change (design §6 vii): the ack key carries condition_digest, so a changed
        # `when` under a reused id has a NEW key ⇒ the earlier provisional ack cannot suppress
        # it. (Non-F1 plan ⇒ a charter change on resume is authority-fresh.)
        charter1 = _charter([{"id": "watch",
                              "when": {"metric": "milestone_id", "op": "in",
                                       "value": ["m2"]}}])
        charter2 = _charter([{"id": "watch",   # SAME id, DIFFERENT predicate ⇒ new digest
                              "when": {"metric": "milestone_id", "op": "in",
                                       "value": ["m2", "m3"]}}])
        plan = _plan(_TWO_MS)
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter1)
            ck = os.path.basename(st.pause_checkpoint)
            # Proceed under charter2: the resolved provisional ack (digest of when1) does NOT
            # match watch's key under when2 ⇒ watch RE-FIRES.
            st = cp.run_campaign(plan, d, _run_unit(_FINAL), clock=clk, charter=charter2,
                                 resume=True,
                                 decision_resolver=self._resolver(d, "watch", ck))
            self.assertEqual(st.pause_reason, "halt_condition_met")
            self.assertEqual(st.halt_condition_pending["condition_id"], "watch")

    def test_crash_after_proceed_save_replays_idempotently(self):
        # TRUE crash-after-proceed-save: hand-craft the post-proceed PAUSED state (provisional
        # ack written, resolved=true, still PAUSED) — the exact durable state proceed._save
        # leaves — then resume with the same decision → re-binds idempotently and completes.
        plan = _plan([{"id": "m2", "objective": "b", "subsprint_sequence": ["s2"],
                       "functional_acceptance": "browser_e2e"}])
        charter = _charter([{"id": "hot",
                             "when": {"metric": "milestone_id", "op": "in",
                                      "value": ["m2"]}}])
        run_unit = _run_unit({"m2": "done"})
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            st = cp.run_campaign(plan, d, run_unit, clock=clk, charter=charter)
            ck = os.path.basename(st.pause_checkpoint)
            state_path = os.path.join(d, "campaign-state.json")
            with open(state_path, encoding="utf-8") as fh:
                state = json.load(fh)
            # Simulate the proceed _save that crashed before the redispatch recorded progress:
            pend = state["halt_condition_pending"]
            pend["resolved"] = True
            state["halt_condition_provisional"] = [pend["ack_key"]]
            with open(state_path, "w", encoding="utf-8") as fh:
                json.dump(state, fh)
            # Replay: same decision re-binds (pending present, nonce matches) → dispatch → done.
            st = cp.run_campaign(plan, d, run_unit, clock=clk, charter=charter, resume=True,
                                 decision_resolver=rl.make_campaign_decision_resolver(
                                     "camp-1",
                                     _decision(d, condition_id="hot", checkpoint=ck), d))
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(len(st.halt_condition_acks), 1)

    def test_freshness_block_then_resign_re_arms(self):
        # freshness-block path (design §6 ii): proceed while the plan is stale → EP-pre blocks
        # for re-sign (campaign_plan_signoff, overlay preserves the halt_condition_met gate);
        # after re-sign to a NEW epoch, the overlay restores the gate and the halt-time epoch
        # mismatch flushes + re-arms.
        plan = _plan([{"id": "m2", "objective": "b", "subsprint_sequence": ["s2"],
                       "functional_acceptance": "browser_e2e"}])
        charter = _charter([{"id": "hot",
                             "when": {"metric": "milestone_id", "op": "in",
                                      "value": ["m2"]}}])
        run_unit = _run_unit({"m2": "done"})
        with tempfile.TemporaryDirectory() as d:
            clk = _clock()
            with mock.patch.object(cp.Campaign, "_live_signed_scope_hash",
                                   return_value="H0"):
                st = cp.run_campaign(plan, d, run_unit, clock=clk, charter=charter)
                ck = os.path.basename(st.pause_checkpoint)
            resolver = rl.make_campaign_decision_resolver(
                "camp-1", _decision(d, condition_id="hot", checkpoint=ck), d)
            # Proceed while STALE (authority not fresh) → block for re-sign.
            with mock.patch.object(cp.Campaign, "_authority_fresh", return_value=False), \
                    mock.patch.object(cp.Campaign, "_live_signed_scope_hash",
                                      return_value="H1"):
                st = cp.run_campaign(plan, d, run_unit, clock=clk, charter=charter,
                                     resume=True, decision_resolver=resolver)
                self.assertEqual(st.pause_reason, "campaign_plan_signoff")   # blocked for re-sign
                self.assertIsNotNone(st.freshness_block)
            # Re-signed (fresh) at the NEW epoch H1: the overlay restores halt_condition_met and
            # the halt-time epoch (H0) mismatch flushes + re-arms hot.
            with mock.patch.object(cp.Campaign, "_authority_fresh", return_value=True), \
                    mock.patch.object(cp.Campaign, "_signoff_status", return_value="signed"), \
                    mock.patch.object(cp.Campaign, "_live_signed_scope_hash",
                                      return_value="H1"):
                st = cp.run_campaign(plan, d, run_unit, clock=clk, charter=charter,
                                     resume=True, decision_resolver=resolver)
            self.assertEqual(st.pause_reason, "halt_condition_met")
            self.assertEqual(st.halt_condition_acks, [])
            self.assertEqual(st.halt_condition_pending["signed_scope_hash"], "H1")


class ByteIdenticalGolden(unittest.TestCase):
    """True byte-level comparison (R2 B-2), not just absent-field checks."""

    def _run_state_bytes(self, charter):
        with tempfile.TemporaryDirectory() as d:
            cp.run_campaign(_plan(_TWO_MS), d, _run_unit(_FINAL), clock=_clock(),
                            charter=charter)
            with open(os.path.join(d, "campaign-state.json"), "rb") as fh:
                return fh.read()

    def test_two_no_condition_runs_are_byte_identical(self):
        # Deterministic clock + mock run_unit ⇒ reproducible bytes; the golden.
        golden = self._run_state_bytes({"autonomy": {}})
        self.assertEqual(golden, self._run_state_bytes({"autonomy": {}}))

    def test_never_matching_condition_is_byte_identical_to_no_conditions(self):
        # A declared-but-never-matching condition perturbs NOTHING (no halt, no state field).
        golden = self._run_state_bytes({"autonomy": {}})
        never = _charter([{"id": "never",
                           "when": {"metric": "milestone_id", "op": "in",
                                    "value": ["does-not-exist"]}}])
        self.assertEqual(golden, self._run_state_bytes(never))


if __name__ == "__main__":
    unittest.main()
