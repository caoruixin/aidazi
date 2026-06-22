#!/usr/bin/env python3
"""Production-path tests for the `--campaign` entrypoint (Item 2 — continuous
multi-milestone delivery wired into run_loop.py).

These drive the REAL path run_campaign_entry -> campaign.make_run_unit ->
scheduling.run_loop -> the REAL Driver (offline, MockAdapters), exercising:
  - the full human-gate chain: unsigned plan -> campaign_plan_signoff pause ->
    sign -> --resume -> per-milestone Acceptance pauses -> ship -> DONE;
  - resume does NOT re-dispatch a completed unit nor double-count its Acceptance;
  - the file-based decision_resolver IDENTITY BINDING (campaign_id + pause_reason
    + checkpoint) fail-closed rejects a stale/mismatched decision;
  - STABLE exit codes (done=0 / paused=10 / invalid=2) + the machine-readable
    CAMPAIGN_STATUS line via main();
  - the shipped sample plan validates against the formal schema.

Run as a script: cd engine-kit && python3.12 scheduling/tests/test_run_loop_campaign.py
"""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHED_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_SCHED_DIR)
_REPO_ROOT = os.path.dirname(_ENGINE_KIT_DIR)
for _p in (_SCHED_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator", "tests"),
           os.path.join(_ENGINE_KIT_DIR, "validators")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
import campaign as cp  # noqa: E402
import run_loop as rl  # noqa: E402
from test_driver import (  # noqa: E402  (reuse the REAL acceptance charter + mocks)
    _acceptance_charter, _acceptance_adapters, ACC_PASS, ACC_FIX)

_EXAMPLE_CHARTER = os.path.join(_ENGINE_KIT_DIR, "orchestrator", "examples",
                                "p2-charter.yaml")
_SAMPLE_PLAN = os.path.join(_REPO_ROOT, "templates", "campaign-plan.example.json")


def _clock():
    """Deterministic ISO clock that rolls cleanly for thousands of ticks (a real
    two-milestone Driver run emits many audit events)."""
    n = {"i": 0}

    def tick() -> str:
        n["i"] += 1
        return f"2026-06-21T{n['i'] // 3600:02d}:{(n['i'] // 60) % 60:02d}:{n['i'] % 60:02d}Z"
    return tick


def _plan(cid, milestones, *, signed=False):
    return {"campaign_id": cid, "goal": "deliver the whole thing",
            "signed_by_human": signed, "milestones": milestones}


def _expected_loop_id(campaign_id, milestone_id, subsprint_id):
    digest = hashlib.sha256(
        f"{campaign_id}\x00{milestone_id}\x00{subsprint_id}".encode()).hexdigest()
    return "u" + digest[:24]


def _driver_event_types(unit_dir):
    types = []
    for root, _dirs, fnames in os.walk(unit_dir):
        for fn in fnames:
            if fn.endswith(".jsonl"):
                types += [e["type"] for e in audit.read_events(os.path.join(root, fn))]
    return types


def _decision_for(result, **fields):
    """An IDENTITY-BOUND decision dict for the live pause described by `result`
    (campaign_id + milestone_id + subsprint_id + checkpoint basename + pause_reason),
    overlaid with `fields` (the gate payload, e.g. choice="ship" or confirm="no";
    or a forged identity field to test a MISMATCH)."""
    cpt = result.get("pause_checkpoint")
    dec = {"campaign_id": result.get("campaign_id"),
           "pause_reason": result.get("pause_reason"),
           "checkpoint": os.path.basename(cpt) if cpt else None}
    if result.get("pause_milestone_id"):
        dec["milestone_id"] = result["pause_milestone_id"]
    if result.get("pause_subsprint_id"):
        dec["subsprint_id"] = result["pause_subsprint_id"]
    dec.update(fields)
    return dec


def _write_decision(path, result, **fields):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_decision_for(result, **fields), fh)
    return path


def _parse_campaign_status(stdout: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith("CAMPAIGN_STATUS="):
            return json.loads(line[len("CAMPAIGN_STATUS="):])
    raise AssertionError("no CAMPAIGN_STATUS line in output:\n" + stdout)


class TestSamplePlan(unittest.TestCase):
    def test_shipped_sample_plan_validates_against_schema(self):
        # Constraint: the sample campaign-plan.json passes the FORMAL validator.
        with open(_SAMPLE_PLAN, encoding="utf-8") as fh:
            plan = json.load(fh)
        cp._validate_or_raise(plan, "campaign-plan.schema.json", "plan")  # raises if invalid


class TestCampaignEntry(unittest.TestCase):
    """run_campaign_entry — the production CLI helper (mock adapters injected)."""

    def _entry(self, plan, charter, home, adapters, clk, *,
               resume=False, decision_path=None):
        return rl.run_campaign_entry(
            plan, charter, clock=clk, campaign_run_dir=home,
            resume=resume, decision_path=decision_path, adapters=adapters)

    def test_unsigned_plan_pauses_at_signoff(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            plan = _plan("cliA", [{"id": "m1", "objective": "x",
                                   "subsprint_sequence": ["sprint-001"]}])
            r = self._entry(plan, charter, os.path.join(d, "h"),
                            _acceptance_adapters(ACC_PASS), _clock())
            self.assertEqual(r["status"], "paused")
            self.assertEqual(r["pause_reason"], "campaign_plan_signoff")
            self.assertEqual(r["exit_code"], rl.CAMPAIGN_EXIT_PAUSED)
            self.assertEqual(r["milestone_index"], 0)

    def test_full_chain_per_milestone_acceptance_to_done(self):
        # unsigned -> signoff -> sign+resume -> m1 Acceptance -> ship -> m2
        # Acceptance -> ship -> DONE; resume never re-runs m1 or dup-counts its gate.
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(
                level="human_on_the_loop", mode="auto",
                subsprint_sequence=("sprint-001", "sprint-002"))
            adapters = _acceptance_adapters(ACC_PASS)
            clk = _clock()
            home = os.path.join(d, "home")
            units = os.path.join(home, "units")
            plan = _plan("cliB", [
                {"id": "m1", "objective": "first", "subsprint_sequence": ["sprint-001"]},
                {"id": "m2", "objective": "second", "subsprint_sequence": ["sprint-002"]}])

            r0 = self._entry(plan, charter, home, adapters, clk)
            self.assertEqual((r0["status"], r0["pause_reason"]),
                             ("paused", "campaign_plan_signoff"))

            plan["signed_by_human"] = True
            r1 = self._entry(plan, charter, home, adapters, clk, resume=True)
            self.assertEqual(r1["pause_reason"], "advisory_acceptance_pass_signoff")
            self.assertEqual(r1["milestone_index"], 0)
            self.assertEqual(len(os.listdir(units)), 1, "only m1 has run")
            m1_loop = _expected_loop_id("cliB", "m1", "sprint-001")
            self.assertIn("acceptance_start",
                          _driver_event_types(os.path.join(units, m1_loop)))

            dec1 = _write_decision(os.path.join(d, "dec1.json"), r1, choice="ship")
            r2 = self._entry(plan, charter, home, adapters, clk,
                             resume=True, decision_path=dec1)
            self.assertEqual(r2["pause_reason"], "advisory_acceptance_pass_signoff")
            self.assertEqual(r2["milestone_index"], 1, "advanced to m2")
            self.assertEqual(len(os.listdir(units)), 2, "m1 not re-dispatched")
            self.assertEqual(
                _driver_event_types(os.path.join(units, m1_loop)).count("acceptance_start"),
                1, "m1 Acceptance must not be duplicated on resume")

            dec2 = _write_decision(os.path.join(d, "dec2.json"), r2, choice="ship")
            r3 = self._entry(plan, charter, home, adapters, clk,
                             resume=True, decision_path=dec2)
            self.assertEqual(r3["status"], "done")
            self.assertEqual(r3["exit_code"], rl.CAMPAIGN_EXIT_DONE)
            self.assertEqual(r3["milestone_index"], 2)

    def test_decision_identity_binding_rejects_mismatch(self):
        # At the m1 Acceptance pause, a decision is REFUSED fail-closed unless EVERY
        # identity field matches the live paused unit — wrong pause_reason, checkpoint,
        # campaign_id, MILESTONE, or sub-sprint each stays paused (never advances).
        # The milestone/sub-sprint binding closes the stale-prior-milestone replay gap:
        # a colliding checkpoint basename can't resolve another unit's gate. Only the
        # fully-bound decision advances.
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            adapters = _acceptance_adapters(ACC_PASS)
            clk = _clock()
            home = os.path.join(d, "home")
            plan = _plan("cliC", [{"id": "m1", "objective": "x",
                                   "subsprint_sequence": ["sprint-001"]}],
                         signed=True)
            paused = self._entry(plan, charter, home, adapters, clk)  # m1 Acc pause
            self.assertEqual(paused["pause_reason"], "advisory_acceptance_pass_signoff")
            self.assertEqual(paused["pause_milestone_id"], "m1")
            self.assertEqual(paused["pause_subsprint_id"], "sprint-001")

            # a pattern-VALID but wrong checkpoint basename — isolates the binding
            # check from the schema's filename-pattern check.
            wrong_cpt = "20200101-000000__advisory_acceptance_pass_signoff__sprint-001.md"
            forgeries = {
                "b_reason.json": dict(pause_reason="gate_hard_fail"),
                "b_checkpoint.json": dict(checkpoint=wrong_cpt),
                "b_campaign.json": dict(campaign_id="otherCampaign"),
                "b_milestone.json": dict(milestone_id="wrongMilestone"),
                "b_subsprint.json": dict(subsprint_id="sprint-999"),
            }
            for name, override in forgeries.items():
                bd = _write_decision(os.path.join(d, name), paused,
                                     choice="ship", **override)
                rj = self._entry(plan, charter, home, adapters, clk,
                                 resume=True, decision_path=bd)
                self.assertEqual(rj["status"], "paused", f"{name} must NOT resolve")
                self.assertEqual(rj["milestone_index"], 0, f"{name} must not advance")

            good = _write_decision(os.path.join(d, "ok.json"), paused, choice="ship")
            rok = self._entry(plan, charter, home, adapters, clk,
                              resume=True, decision_path=good)
            self.assertEqual(rok["status"], "done")
            self.assertEqual(rok["milestone_index"], 1)

    def test_acceptance_fix_required_confirm_no_ships_advisory(self):
        # ACC_FIX -> m1 Acceptance returns fix_required -> acceptance_fix_required
        # pause. The decision uses `confirm` (NOT `choice`): confirm:no ships the
        # advisory (ADVANCE_MILESTONE) -> single milestone -> DONE.
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            adapters = _acceptance_adapters(ACC_FIX)
            clk = _clock()
            home = os.path.join(d, "home")
            plan = _plan("cliFixNo", [{"id": "m1", "objective": "x",
                                       "subsprint_sequence": ["sprint-001"]}],
                         signed=True)
            r0 = self._entry(plan, charter, home, adapters, clk)
            self.assertEqual(r0["pause_reason"], "acceptance_fix_required")
            dec = _write_decision(os.path.join(d, "fix.json"), r0, confirm="no")
            r1 = self._entry(plan, charter, home, adapters, clk,
                             resume=True, decision_path=dec)
            self.assertEqual(r1["status"], "done")
            self.assertEqual(r1["milestone_index"], 1)

    def test_acceptance_fix_required_confirm_yes_routes_followup(self):
        # confirm:yes (+ route) routes a Deliver fix follow-up ->
        # deliver_followup_required pause (NOT a ship).
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            adapters = _acceptance_adapters(ACC_FIX)
            clk = _clock()
            home = os.path.join(d, "home")
            plan = _plan("cliFixYes", [{"id": "m1", "objective": "x",
                                        "subsprint_sequence": ["sprint-001"]}],
                         signed=True)
            r0 = self._entry(plan, charter, home, adapters, clk)
            self.assertEqual(r0["pause_reason"], "acceptance_fix_required")
            dec = _write_decision(os.path.join(d, "fix.json"), r0,
                                  confirm="yes", route="deliver_fix_iteration")
            r1 = self._entry(plan, charter, home, adapters, clk,
                             resume=True, decision_path=dec)
            self.assertEqual(r1["status"], "paused")
            self.assertEqual(r1["pause_reason"], "deliver_followup_required")

    def test_checkpoint_empty_string_rejected_fail_closed(self):
        # A decision with checkpoint:"" is schema-invalid (not a checkpoint filename)
        # -> resolver returns None -> the gate stays paused (strict; no falsy coercion
        # of "" to a checkpoint-less match).
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            adapters = _acceptance_adapters(ACC_PASS)
            clk = _clock()
            home = os.path.join(d, "home")
            plan = _plan("cliCpt", [{"id": "m1", "objective": "x",
                                     "subsprint_sequence": ["sprint-001"]}],
                         signed=True)
            r0 = self._entry(plan, charter, home, adapters, clk)
            self.assertEqual(r0["pause_reason"], "advisory_acceptance_pass_signoff")
            bad = _write_decision(os.path.join(d, "empty.json"), r0,
                                  choice="ship", checkpoint="")
            rj = self._entry(plan, charter, home, adapters, clk,
                             resume=True, decision_path=bad)
            self.assertEqual(rj["status"], "paused")
            self.assertEqual(rj["milestone_index"], 0)

    def test_invalid_plan_exits_invalid_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            bad_plan = {"campaign_id": "x", "goal": "g"}  # missing required milestones
            r = rl.run_campaign_entry(
                bad_plan, charter, clock=_clock(),
                campaign_run_dir=os.path.join(d, "h"),
                adapters=_acceptance_adapters(ACC_PASS))
            self.assertEqual(r["status"], "invalid")
            self.assertEqual(r["exit_code"], rl.CAMPAIGN_EXIT_INVALID)

    def test_checkpoint_pause_with_unresolvable_unit_fails_closed(self):
        # A checkpoint-bearing pause whose live unit cannot be resolved from
        # campaign-state.json (tampered/missing checkpoint_path) FAILS CLOSED — the
        # milestone/sub-sprint binding is NOT silently skipped (a missed lookup is not
        # treated as a legitimately checkpoint-less pause).
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            adapters = _acceptance_adapters(ACC_PASS)
            clk = _clock()
            home = os.path.join(d, "home")
            plan = _plan("cliMiss", [{"id": "m1", "objective": "x",
                                      "subsprint_sequence": ["sprint-001"]}],
                         signed=True)
            r0 = self._entry(plan, charter, home, adapters, clk)
            self.assertEqual(r0["pause_reason"], "advisory_acceptance_pass_signoff")
            # a CORRECT, fully-bound decision ...
            dec = _write_decision(os.path.join(d, "ok.json"), r0, choice="ship")
            # ... but break the unit lookup: move every unit's checkpoint_path in
            # campaign-state.json so NONE matches the live pause_checkpoint (which is
            # left intact, so the basename check still passes — isolating the lookup).
            state_path = os.path.join(home, "campaign-state.json")
            with open(state_path, encoding="utf-8") as fh:
                state = json.load(fh)
            for u in state.get("units", []):
                if u.get("checkpoint_path"):
                    u["checkpoint_path"] = u["checkpoint_path"] + ".moved"
            with open(state_path, "w", encoding="utf-8") as fh:
                json.dump(state, fh)
            rj = self._entry(plan, charter, home, adapters, clk,
                             resume=True, decision_path=dec)
            self.assertEqual(rj["status"], "paused",
                             "an unresolvable unit must not resolve the gate")
            self.assertEqual(rj["milestone_index"], 0)

    def test_campaign_threads_memory_root_to_per_milestone_driver(self):
        # The --campaign entrypoint threads memory_root through make_run_unit -> run_loop
        # -> the per-milestone Driver. m1 is dispatched (paused at its Acceptance gate),
        # so its Driver built a MemoryStore at the threaded root → entries/ exists.
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            plan = _plan("cliMem", [{"id": "m1", "objective": "x",
                                     "subsprint_sequence": ["sprint-001"]}], signed=True)
            mem = os.path.join(d, "mem")
            r = rl.run_campaign_entry(
                plan, charter, clock=_clock(), campaign_run_dir=os.path.join(d, "home"),
                adapters=_acceptance_adapters(ACC_PASS), memory_root=mem)
            self.assertEqual(r["pause_reason"], "advisory_acceptance_pass_signoff")
            self.assertTrue(
                os.path.isdir(os.path.join(mem, "entries")),
                "campaign must thread memory_root to the per-milestone Driver")

    def test_campaign_without_memory_root_builds_no_store(self):
        # byte-identical regression: no memory_root ⇒ the Driver never builds a store.
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            plan = _plan("cliNoMem", [{"id": "m1", "objective": "x",
                                       "subsprint_sequence": ["sprint-001"]}], signed=True)
            mem = os.path.join(d, "mem")  # a path we do NOT pass
            r = rl.run_campaign_entry(
                plan, charter, clock=_clock(), campaign_run_dir=os.path.join(d, "home"),
                adapters=_acceptance_adapters(ACC_PASS))  # no memory_root
            self.assertEqual(r["pause_reason"], "advisory_acceptance_pass_signoff")
            self.assertFalse(os.path.exists(mem),
                             "no memory_root ⇒ no Loop Memory store (OFF)")


class TestDecisionSchema(unittest.TestCase):
    """Gate-specific decision payload (schemas/campaign-decision.schema.json):
    acceptance_fix_required uses confirm(+route) and forbids choice; every other gate
    uses choice and forbids confirm/route; campaign_budget_exhausted's choice is
    restricted to raise_cap|abort (an ambiguous decision is schema-rejected ->
    re-pauses, never silently aborts)."""

    _CPT = "20260101-000000__x__sprint-001.md"

    def _valid(self, dec):
        cp._validate_or_raise(dec, "campaign-decision.schema.json", "decision")

    def _invalid(self, dec):
        with self.assertRaises(ValueError):
            cp._validate_or_raise(dec, "campaign-decision.schema.json", "decision")

    def test_choice_gate_requires_choice_forbids_confirm_route(self):
        base = {"campaign_id": "c",
                "pause_reason": "advisory_acceptance_pass_signoff",
                "checkpoint": self._CPT}
        self._valid({**base, "choice": "ship"})
        self._invalid({**base, "confirm": "no"})                 # confirm on a choice gate
        self._invalid({**base, "choice": "ship", "route": "x"})  # route on a choice gate
        self._invalid(base)                                       # neither choice nor confirm

    def test_acceptance_fix_required_requires_confirm_forbids_choice(self):
        base = {"campaign_id": "c", "pause_reason": "acceptance_fix_required",
                "checkpoint": self._CPT}
        self._valid({**base, "confirm": "no"})
        self._valid({**base, "confirm": "yes", "route": "deliver_fix_iteration"})
        self._invalid({**base, "choice": "ship"})                # choice on the confirm gate
        self._invalid(base)                                       # missing confirm

    def test_budget_gate_choice_enum_enforced(self):
        base = {"campaign_id": "c", "pause_reason": "campaign_budget_exhausted",
                "checkpoint": None}
        self._valid({**base, "choice": "raise_cap"})
        self._valid({**base, "choice": "abort"})
        self._invalid({**base, "choice": "ship"})                # not raise_cap|abort
        self._invalid({**base, "confirm": "no"})                 # confirm on the budget gate

    def test_empty_checkpoint_rejected(self):
        self._invalid({"campaign_id": "c", "pause_reason": "gate_hard_fail",
                       "checkpoint": "", "choice": "re_run"})


class TestCampaignMainCLI(unittest.TestCase):
    """main(['--campaign', ...]) — exit codes + the machine-readable status line."""

    def test_main_signoff_paused_then_signed_resume_done(self):
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "home")
            planfile = os.path.join(d, "plan.json")
            plan = _plan("cliMain", [
                {"id": "m1", "objective": "a",
                 "subsprint_sequence": ["sprint-001", "sprint-002"]},
                {"id": "m2", "objective": "b", "subsprint_sequence": ["sprint-003"]}])
            with open(planfile, "w", encoding="utf-8") as fh:
                json.dump(plan, fh)
            argv = ["--campaign", planfile, "--charter", _EXAMPLE_CHARTER,
                    "--campaign-run-dir", home]

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = rl.main(argv)
            self.assertEqual(code, rl.CAMPAIGN_EXIT_PAUSED)
            m = _parse_campaign_status(buf.getvalue())
            self.assertEqual(m["status"], "paused")
            self.assertEqual(m["pause_reason"], "campaign_plan_signoff")
            self.assertEqual(m["exit_code"], rl.CAMPAIGN_EXIT_PAUSED)

            plan["signed_by_human"] = True
            with open(planfile, "w", encoding="utf-8") as fh:
                json.dump(plan, fh)
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                code2 = rl.main(argv + ["--resume"])
            self.assertEqual(code2, rl.CAMPAIGN_EXIT_DONE)
            m2 = _parse_campaign_status(buf2.getvalue())
            self.assertEqual(m2["status"], "done")
            self.assertEqual(m2["milestone_index"], 2)
            self.assertEqual(m2["milestones_total"], 2)

    def test_main_unreadable_plan_exits_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = rl.main(["--campaign", os.path.join(d, "nope.json"),
                                "--charter", _EXAMPLE_CHARTER])
            self.assertEqual(code, rl.CAMPAIGN_EXIT_INVALID)
            self.assertEqual(_parse_campaign_status(buf.getvalue())["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
