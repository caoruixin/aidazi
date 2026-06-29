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
            # scope-coverage wiring: m1 in-flight (not yet accepted) ⇒ 0/2 delivered.
            cov1 = r1["scope_coverage"]
            self.assertEqual((cov1["milestones_delivered"], cov1["milestones_total"]),
                             (0, 2))
            self.assertFalse(cov1["baseline_available"])
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
            # scope-coverage wiring: backlog exhausted ⇒ 2/2 delivered, nothing left.
            cov3 = r3["scope_coverage"]
            self.assertEqual(cov3["milestones_delivered"], 2)
            self.assertEqual(cov3["pct_milestones_delivered"], 100)
            self.assertEqual(cov3["remaining_milestones"], [])

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

    def test_cleanup_gate_waiver_fields_accepted(self):
        # acceptance_cleanup_required: a COMPLETE residue waiver (the fields
        # campaign.interpret_dispatch needs to ship known residue) MUST pass the
        # decision schema — else accept_residue_and_ship is dead-on-arrival at the
        # file-based resolver (additionalProperties:false). retry_cleanup|abort carry no
        # waiver fields. (Waiver COMPLETENESS is enforced by interpret_dispatch, not the
        # schema — so a bare accept_residue_and_ship is schema-valid but fail-closes to
        # a Deliver follow-up at dispatch, never ships.)
        base = {"campaign_id": "c", "pause_reason": "acceptance_cleanup_required",
                "checkpoint": self._CPT}
        self._valid({**base, "choice": "retry_cleanup"})
        self._valid({**base, "choice": "abort"})
        self._valid({**base, "choice": "accept_residue_and_ship",
                     "residue": ["leftover-db"], "rationale": "non-blocking",
                     "evidence": "evidence.json", "waiver_id": "WV-1"})
        self._valid({**base, "choice": "accept_residue_and_ship",
                     "residue": ["leftover-db"], "rationale": "non-blocking",
                     "evidence": "evidence.json", "waiver": True})
        self._invalid({**base, "confirm": "no"})   # confirm on a choice gate (else-clause)

    def test_waiver_fields_scoped_to_cleanup_ship_choice(self):
        # Concern A: the residue-waiver fields are ONLY valid with
        # choice:accept_residue_and_ship; an UNRELATED gate (or even the cleanup gate's
        # retry_cleanup) carrying them is schema-REJECTED, so other gates stay strict
        # (defense-in-depth at the ingress; the runtime ignores them elsewhere anyway).
        self._valid({"campaign_id": "c",
                     "pause_reason": "acceptance_cleanup_required",
                     "checkpoint": self._CPT, "choice": "accept_residue_and_ship",
                     "residue": ["r"], "rationale": "x", "evidence": "e",
                     "waiver_id": "w"})
        for fld, val in (("residue", ["r"]), ("rationale", "x"), ("evidence", "e"),
                         ("waiver", True), ("waiver_id", "w")):
            # advisory sign-off (choice:ship) must NOT accept any waiver field.
            self._invalid({"campaign_id": "c",
                           "pause_reason": "advisory_acceptance_pass_signoff",
                           "checkpoint": self._CPT, "choice": "ship", fld: val})
        # the cleanup gate's retry_cleanup (not accept_residue_and_ship) rejects them too.
        self._invalid({"campaign_id": "c",
                       "pause_reason": "acceptance_cleanup_required",
                       "checkpoint": self._CPT, "choice": "retry_cleanup",
                       "residue": ["r"]})


class TestFileResolverResidueWaiver(unittest.TestCase):
    """Blocking 1 (end-to-end): the FILE-based decision_resolver must pass the residue-
    waiver fields THROUGH to campaign.interpret_dispatch — else a complete waiver
    authored in campaign-decision.json is silently stripped at the resolver and
    accept_residue_and_ship can NEVER ship on the real CLI (dead-on-arrival).

    Drives campaign.run_campaign with a fake run_unit that halts at
    acceptance_cleanup_required (carrying a schema-shaped checkpoint basename so the
    resolver's identity binding resolves the live unit) + the REAL
    rl.make_campaign_decision_resolver reading a real decision file."""

    _CPT_BASENAME = "20260101-000000__acceptance_cleanup_required__s1.md"

    def _events(self, ledger, type_):
        return [e for e in audit.read_events(ledger) if e["type"] == type_]

    def _run_unit(self, script):
        def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                     resume=False, functional_acceptance=None, repo_dir=None):
            return dict(script[subsprint_id])
        return run_unit

    def _setup_cleanup_pause(self, home):
        cpt = os.path.join(home, "docs", "checkpoints", self._CPT_BASENAME)
        os.makedirs(os.path.dirname(cpt), exist_ok=True)
        with open(cpt, "w", encoding="utf-8") as fh:
            fh.write("---\ncheckpoint_id: acceptance_cleanup_required\n---\n")
        script = {"s1": {"final_state": "halted", "spawn_count": 1,
                         "pause_reason": "acceptance_cleanup_required",
                         "checkpoint_path": cpt},
                  "s2": {"final_state": "done", "spawn_count": 1}}
        plan = _plan("cliWaiver", [
            {"id": "m1", "objective": "a", "subsprint_sequence": ["s1"]},
            {"id": "m2", "objective": "b", "subsprint_sequence": ["s2"]}], signed=True)
        st = cp.run_campaign(plan, home, self._run_unit(script), clock=_clock())
        self.assertEqual(st.pause_reason, "acceptance_cleanup_required")
        return plan, script, cpt

    def _resolve_and_run(self, home, plan, script, cpt, **extra):
        decision = {"campaign_id": "cliWaiver", "milestone_id": "m1",
                    "subsprint_id": "s1", "pause_reason": "acceptance_cleanup_required",
                    "checkpoint": os.path.basename(cpt),
                    "choice": "accept_residue_and_ship",
                    "residue": ["leftover-db"], "rationale": "non-blocking",
                    "evidence": "docs/evidence/cleanup-status.json", **extra}
        dec_path = os.path.join(home, "dec.json")
        with open(dec_path, "w", encoding="utf-8") as fh:
            json.dump(decision, fh)
        resolver = rl.make_campaign_decision_resolver("cliWaiver", dec_path, home)
        camp = cp.Campaign(plan, home, self._run_unit(script), clock=_clock())
        st = camp.run(resume=True, decision_resolver=resolver)
        return camp, st

    def test_complete_waiver_file_survives_resolver_and_ships(self):
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "home")
            plan, script, cpt = self._setup_cleanup_pause(home)
            camp, st = self._resolve_and_run(home, plan, script, cpt, waiver_id="WV-1")
            # WITHOUT the resolver pass-through fix the waiver fields would be stripped →
            # interpret_dispatch fail-closes to deliver_followup_required (no ship). With
            # the fix the complete waiver reaches interpret_dispatch → ships → DONE.
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(st.milestone_index, 2)
            waived = self._events(camp.audit_ledger,
                                  "campaign_acceptance_residue_waived")
            self.assertEqual(len(waived), 1)
            self.assertEqual(waived[0]["payload"]["waiver_id"], "WV-1")
            self.assertEqual(waived[0]["payload"]["residue"], ["leftover-db"])

    def test_boolean_marker_waiver_file_survives_resolver_and_ships(self):
        # Blocking 1 + 2 via the file path: the boolean marker (waiver:true, no
        # waiver_id) also survives the resolver and ships, recording the marker.
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "home")
            plan, script, cpt = self._setup_cleanup_pause(home)
            camp, st = self._resolve_and_run(home, plan, script, cpt, waiver=True)
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(st.milestone_index, 2)
            waived = self._events(camp.audit_ledger,
                                  "campaign_acceptance_residue_waived")
            self.assertEqual(len(waived), 1)
            self.assertIs(waived[0]["payload"]["waiver"], True)
            self.assertIsNone(waived[0]["payload"]["waiver_id"])


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


class TestScopeCoverageWiring(unittest.TestCase):
    """Phase-0 scope-coverage is a GUARDED, ADDITIVE reporting nicety: it must
    never break a run, and the CAMPAIGN_STATUS= parse contract stays byte-stable."""

    _STATUS_KEYS = {
        "campaign_id", "status", "pause_reason", "pause_checkpoint",
        "pause_milestone_id", "pause_subsprint_id", "pause_loop_id",
        "milestone_index", "milestones_total", "subsprints_run",
        "total_spawns", "exit_code"}

    def _paused_result(self, d):
        charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
        plan = _plan("cliCov", [{"id": "m1", "objective": "x",
                                 "subsprint_sequence": ["sprint-001"]}])
        return rl.run_campaign_entry(
            plan, charter, clock=_clock(),
            campaign_run_dir=os.path.join(d, "h"),
            adapters=_acceptance_adapters(ACC_PASS))

    def test_status_keyset_locked_and_scope_coverage_additive(self):
        with tempfile.TemporaryDirectory() as d:
            r = self._paused_result(d)
            self.assertIsNotNone(r["scope_coverage"])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rl.print_campaign_result(r)
            out = buf.getvalue()
            # CAMPAIGN_STATUS= key set is locked (additive line must not leak in)
            self.assertEqual(set(_parse_campaign_status(out)), self._STATUS_KEYS)
            cov = [ln for ln in out.splitlines() if ln.startswith("SCOPE_COVERAGE=")]
            self.assertEqual(len(cov), 1, "exactly one additive SCOPE_COVERAGE= line")
            json.loads(cov[0][len("SCOPE_COVERAGE="):])  # valid JSON

    def test_scope_report_failure_degrades_to_none_and_suppresses_line(self):
        import scope_report
        orig = scope_report.compute_coverage

        def _boom(*a, **k):
            raise RuntimeError("scope_report bug")

        scope_report.compute_coverage = _boom
        try:
            with tempfile.TemporaryDirectory() as d:
                r = self._paused_result(d)
                # the campaign run still completes; coverage degraded to None
                self.assertEqual(r["status"], "paused")
                self.assertIsNone(r["scope_coverage"])
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rl.print_campaign_result(r)
                out = buf.getvalue()
                _parse_campaign_status(out)            # CAMPAIGN_STATUS still emitted
                self.assertNotIn("SCOPE_COVERAGE=", out)  # additive line suppressed
        finally:
            scope_report.compute_coverage = orig


def _ledger(items):
    return {"version": "v1", "requirements": [
        {"id": i, "statement": f"req {i}", "source": {"channel": "prd"},
         "customer_disposition": d} for (i, d) in items]}


class TestRequirementCoverageWiring(unittest.TestCase):
    """Δ-19: the production --campaign path loads+validates the wired ledger, computes
    the requirement projection, and emits REQUIREMENT_COVERAGE= ONLY when a valid ledger
    is present (CAMPAIGN_STATUS= / SCOPE_COVERAGE= stay byte-identical)."""

    def _charter_with_ledger(self, ledger_abspath):
        charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
        charter["requirements"] = {"ledger_path": ledger_abspath}
        return charter

    def test_no_ledger_is_byte_identical(self):
        # No ledger wired ⇒ no requirement_coverage, no REQUIREMENT_COVERAGE= line.
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            plan = _plan("reqA", [{"id": "m1", "objective": "x",
                                   "subsprint_sequence": ["sprint-001"]}])
            r = rl.run_campaign_entry(plan, charter, clock=_clock(),
                                      campaign_run_dir=os.path.join(d, "h"),
                                      adapters=_acceptance_adapters(ACC_PASS))
            self.assertIsNone(r.get("requirement_coverage"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rl.print_campaign_result(r)
            out = buf.getvalue()
            self.assertIn("CAMPAIGN_STATUS=", out)
            self.assertNotIn("REQUIREMENT_COVERAGE=", out)

    def test_valid_ledger_emits_requirement_coverage_and_derives_delivery(self):
        with tempfile.TemporaryDirectory() as d:
            led_path = os.path.join(d, "requirements-ledger.json")
            with open(led_path, "w", encoding="utf-8") as fh:
                json.dump(_ledger([("REQ-1", "accepted"), ("REQ-2", "accepted")]), fh)
            charter = self._charter_with_ledger(led_path)
            adapters = _acceptance_adapters(ACC_PASS)
            clk = _clock()
            home = os.path.join(d, "home")
            # 1 milestone covering REQ-1; REQ-2 is in no milestone (a PRD gap). F1
            # active (covers_req_ids) ⇒ stamp the signed snapshot so the runner proceeds.
            plan = _plan("reqB", [{"id": "m1", "objective": "first",
                                   "covers_req_ids": ["REQ-1"],
                                   "subsprint_sequence": ["sprint-001"]}])
            signed = cp.stamp_signoff(plan, charter, signed_at="2026", charter_ref="ch")

            r1 = rl.run_campaign_entry(signed, charter, clock=clk,
                                       campaign_run_dir=home, adapters=adapters)
            self.assertEqual(r1["pause_reason"], "advisory_acceptance_pass_signoff")
            rc1 = r1["requirement_coverage"]
            self.assertIsNotNone(rc1)
            self.assertEqual(rc1["signoff_status"], "signed")
            self.assertEqual(rc1["requirements_total"], 2)
            self.assertEqual(rc1["uncovered_requirements"], ["REQ-2"])  # REQ-2 PRD gap
            self.assertEqual(rc1["delivered"], 0)                       # m1 in-flight
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rl.print_campaign_result(r1)
            self.assertIn("REQUIREMENT_COVERAGE=", buf.getvalue())

            dec = _write_decision(os.path.join(d, "dec.json"), r1, choice="ship")
            r2 = rl.run_campaign_entry(signed, charter, clock=clk,
                                       campaign_run_dir=home, resume=True,
                                       decision_path=dec, adapters=adapters)
            self.assertEqual(r2["status"], "done")
            rc2 = r2["requirement_coverage"]
            # REQ-1 DELIVERED via the milestone's terminal Acceptance ship (derived).
            self.assertEqual(rc2["delivered"], 1)
            self.assertEqual(rc2["uncovered_requirements"], ["REQ-2"])
            self.assertEqual(r2["milestone_outcomes"][0]["terminal"],
                             "acceptance_pass_advisory_ship")


class TestSignPlanCli(unittest.TestCase):
    """Δ-19 F1 --sign-plan: the re-sign action stamps the signed resolved-scope snapshot
    into the plan file so the runner then honors campaign_plan_signoff."""

    def test_sign_plan_stamps_then_status_is_signed(self):
        with tempfile.TemporaryDirectory() as d:
            plan_path = os.path.join(d, "plan.json")
            plan = _plan("signcli", [{"id": "m1", "objective": "x",
                                      "covers_req_ids": ["REQ-1"],
                                      "subsprint_sequence": ["sprint-001"]}],
                         signed=True)  # bare flag → pre_f1 until --sign-plan stamps it
            with open(plan_path, "w", encoding="utf-8") as fh:
                json.dump(plan, fh)
            charter = rl.load_charter(_EXAMPLE_CHARTER)
            self.assertEqual(cp.signoff_status(plan, charter), "pre_f1")
            rc = rl.main(["--charter", _EXAMPLE_CHARTER, "--campaign", plan_path,
                          "--sign-plan"])
            self.assertEqual(rc, 0)
            with open(plan_path, encoding="utf-8") as fh:
                stamped = json.load(fh)
            self.assertIn("signoff", stamped)
            self.assertTrue(stamped["signoff"]["signed_by_human"])
            self.assertEqual(cp.signoff_status(stamped, charter), "signed")
            # the stamped plan still validates against the formal schema.
            cp._validate_or_raise(stamped, "campaign-plan.schema.json", "plan")


class TestSamplePlanCoversReqIds(unittest.TestCase):
    def test_example_plan_covers_req_ids_validate(self):
        with open(_SAMPLE_PLAN, encoding="utf-8") as fh:
            plan = json.load(fh)
        cp._validate_or_raise(plan, "campaign-plan.schema.json", "plan")
        covers = [c for m in plan["milestones"] for c in (m.get("covers_req_ids") or [])]
        self.assertTrue(covers, "the example plan should demonstrate covers_req_ids")
        # at-most-one covering milestone per REQ (no cross-milestone duplicates).
        self.assertEqual(len(covers), len(set(covers)))


if __name__ == "__main__":
    unittest.main()
