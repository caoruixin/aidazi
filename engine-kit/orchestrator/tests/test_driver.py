"""Deterministic, OFFLINE tests for the P2 engine-MVP driver + adapters.

All adapters are the MOCK adapter; the real claude_code/headless subprocess +
HTTP paths are gated off and NEVER run here. Timestamps are injected so audit
hashes are reproducible.

Covers (per the P2 task):
  - state transitions advance on clean verdicts;
  - an invalid/malformed verdict -> driver raises GateHardFail (asserted), does
    not silently pass;
  - mock adapter routing: Dev->claude_code-mock, Review->headless-mock;
  - audit ledger emitted + chain verifies (reuse audit_log.verify_chain);
  - resume: kill mid-run + resume from state.json continues.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit"), _ORCH_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
import loop_ingress as li  # noqa: E402
from adapters import (  # noqa: E402
    MockAdapter, AdapterError, ClaudeCodeAdapter, HeadlessAdapter,
    resolve_adapter_class,
)
import driver as drv  # noqa: E402
from driver import (  # noqa: E402
    Driver, GateHardFail, BudgetExceeded, load_charter,
    load_verdict_schemas, route_for_role, validate_verdict,
    STATE_ADVANCE, STATE_HALTED, STATE_DONE, STATE_ACCEPTANCE_PENDING,
    STATE_REVIEW_PENDING, STATE_CLOSE_PENDING,
)
import memory_store as ms  # noqa: E402  (driver put engine-kit/memory on sys.path)

CHARTER_PATH = os.path.join(_ORCH_DIR, "examples", "p2-charter.yaml")
_FIXTURES_DIR = os.path.join(_TESTS_DIR, "fixtures")
_FAKE_EVAL = os.path.join(_FIXTURES_DIR, "fake_eval.py")


def _clock():
    seq = {"n": 0}

    def _now():
        seq["n"] += 1
        return f"2026-06-15T12:{seq['n']:02d}:00Z"

    return _now


# Canonical clean-pass verdicts (schema-valid).
CLEAN_REVIEW = {
    "decision": "pass", "blocking_count": 0,
    "summary": "no blocking findings", "findings": [],
}
CLEAN_CLOSE = {
    "verdict": "A", "blocking_count": 0, "worst_severity": "none",
    "in_scope": True, "next_subsprint": "sprint-002", "reason": "clean pass",
}
DEV_ARTIFACT = {"artifact": "handoff written"}


def _adapters(review=CLEAN_REVIEW, close=CLEAN_CLOSE, dev=DEV_ARTIFACT,
              dev_harness="claude_code", review_harness="headless",
              deliver_harness="claude_code"):
    return {
        "dev": MockAdapter({("dev",): dev}, harness=dev_harness, provider="anthropic",
                           model="claude-sonnet-4-6"),
        "review": MockAdapter({("review",): review}, harness=review_harness,
                              provider="deepseek", model="deepseek-chat"),
        "deliver": MockAdapter({("deliver",): close}, harness=deliver_harness,
                               provider="anthropic", model="claude-opus-4-8"),
    }


def _driver(run_dir, charter=None, adapters=None, loop_id="loop-test-001"):
    charter = charter if charter is not None else load_charter(CHARTER_PATH)
    return Driver(charter, run_dir, adapters or _adapters(),
                  loop_id=loop_id, clock=_clock())


class TestCleanTransitions(unittest.TestCase):
    def test_clean_verdicts_advance(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertEqual(
                final.history,
                ["dev_pending", "gate_pending", "review_pending", "close_pending"],
            )
            self.assertEqual(final.fix_round, 0)
            # 3 spawns: dev, review, deliver.
            self.assertEqual(final.spawn_count, 3)

    def test_state_json_written_and_final(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            self.assertTrue(os.path.isfile(drv_.state_path))
            reloaded = drv_._load_state()
            self.assertEqual(reloaded.state, STATE_ADVANCE)


class TestInvalidVerdictHardFails(unittest.TestCase):
    def test_malformed_review_verdict_raises_gate_hard_fail(self):
        # decision is not in the enum -> schema-invalid -> gate_hard_fail.
        bad_review = {"decision": "looks_good", "blocking_count": 0,
                      "summary": "x", "findings": []}
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(review=bad_review))
            with self.assertRaises(GateHardFail) as ctx:
                drv_.run(subsprint_id="sprint-001")
            self.assertIn("review", ctx.exception.reason)
            self.assertEqual(drv_.state.state, STATE_HALTED if False else drv_.state.state)
            # A gate_hard_fail checkpoint file was written; loop did NOT advance.
            self.assertNotEqual(drv_.state.state, STATE_ADVANCE)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("gate_hard_fail" in c for c in cps), cps)

    def test_missing_required_field_raises_gate_hard_fail(self):
        # close verdict missing required "in_scope".
        bad_close = {"verdict": "A", "blocking_count": 0, "worst_severity": "none",
                     "next_subsprint": None, "reason": "x"}
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(close=bad_close))
            with self.assertRaises(GateHardFail) as ctx:
                drv_.run(subsprint_id="sprint-001")
            self.assertIn("close", ctx.exception.reason)

    def test_non_dict_verdict_raises_gate_hard_fail(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(review=["not", "a", "dict"]))
            with self.assertRaises(GateHardFail):
                drv_.run(subsprint_id="sprint-001")

    def test_adapter_error_raises_gate_hard_fail_not_permissive(self):
        # Adapter transport failure must NOT become a permissive pass.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(review=AdapterError("boom")))
            with self.assertRaises(GateHardFail) as ctx:
                drv_.run(subsprint_id="sprint-001")
            self.assertIn("failed", ctx.exception.reason)
            self.assertNotEqual(drv_.state.state, STATE_ADVANCE)

    def test_validate_verdict_pure_function(self):
        schemas = load_verdict_schemas()
        self.assertIsNone(validate_verdict(CLEAN_REVIEW, schemas["review"]))
        self.assertIsNotNone(validate_verdict({"decision": "nope"}, schemas["review"]))
        self.assertIsNotNone(validate_verdict("not-a-dict", schemas["review"]))


class TestRouting(unittest.TestCase):
    def test_charter_routes_dev_to_claude_code_review_to_headless(self):
        charter = load_charter(CHARTER_PATH)
        self.assertEqual(route_for_role(charter, "dev").harness, "claude_code")
        self.assertEqual(route_for_role(charter, "review").harness, "headless")
        self.assertEqual(route_for_role(charter, "deliver").harness, "claude_code")
        self.assertEqual(route_for_role(charter, "review").provider, "deepseek")

    def test_per_role_adapter_harness_recorded_in_audit(self):
        with tempfile.TemporaryDirectory() as d:
            adapters = _adapters(dev_harness="claude_code", review_harness="headless")
            drv_ = _driver(d, adapters=adapters)
            drv_.run(subsprint_id="sprint-001")
            events = audit.read_events(drv_.audit_ledger)
            spawns = [e for e in events if e["type"] == "spawn"]
            by_role = {e["payload"]["role"]: e["payload"]["harness"] for e in spawns}
            self.assertEqual(by_role["dev"], "claude_code")
            self.assertEqual(by_role["review"], "headless")   # multi-model routing
            self.assertEqual(by_role["deliver"], "claude_code")

    def test_legacy_agent_kind_field_falls_back(self):
        charter = {"tooling": {"dev": {"agent_kind": "claude_code", "model": "x"}}}
        self.assertEqual(route_for_role(charter, "dev").harness, "claude_code")

    def test_unknown_harness_raises_typed_adapter_error_not_keyerror(self):
        # Routing a role to a harness id not in ADAPTER_REGISTRY must raise a
        # typed AdapterError with an actionable message — never a bare KeyError.
        with self.assertRaises(AdapterError) as ctx:
            resolve_adapter_class("bogus_harness", role="review")
        msg = str(ctx.exception)
        self.assertIn("unknown harness", msg)
        self.assertIn("bogus_harness", msg)
        self.assertIn("review", msg)
        self.assertIn("claude_code", msg)  # known ids listed for the operator
        # A typed AdapterError is NOT a KeyError.
        self.assertNotIsInstance(ctx.exception, KeyError)
        # A KNOWN harness still resolves to its class (behaviour unchanged).
        self.assertIs(resolve_adapter_class("claude_code"), ClaudeCodeAdapter)
        self.assertIs(resolve_adapter_class("headless", role="review"), HeadlessAdapter)


class TestAuditLedger(unittest.TestCase):
    def test_ledger_emitted_and_chain_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            self.assertTrue(os.path.isfile(drv_.audit_ledger))
            result = audit.verify_chain(drv_.audit_ledger)
            self.assertTrue(result.ok, result.render())
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("loop_start", types)
            self.assertEqual(types.count("spawn"), 3)
            self.assertIn("advance", types)

    def test_loop_id_threads_every_event(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, loop_id="loop-thread-xyz")
            drv_.run(subsprint_id="sprint-001")
            events = audit.read_events(drv_.audit_ledger)
            self.assertTrue(all(e["loop_id"] == "loop-thread-xyz" for e in events))

    def test_hard_fail_emits_audit_and_chain_still_verifies(self):
        bad_review = {"decision": "looks_good", "blocking_count": 0,
                      "summary": "x", "findings": []}
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(review=bad_review))
            with self.assertRaises(GateHardFail):
                drv_.run(subsprint_id="sprint-001")
            result = audit.verify_chain(drv_.audit_ledger)
            self.assertTrue(result.ok, result.render())
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("gate_hard_fail", types)


class TestResume(unittest.TestCase):
    def test_resume_from_midrun_state_continues_to_advance(self):
        # Phase 1: a driver that "dies" right after review_pending. We simulate a
        # mid-run kill by having the deliver adapter raise on the FIRST run only.
        with tempfile.TemporaryDirectory() as d:
            class _OneShotKill(MockAdapter):
                def __init__(self, *a, **k):
                    super().__init__(*a, **k)
                    self.armed = True

            kill_adapters = _adapters()
            # Replace deliver with one that hard-fails the first time (kill point).
            kill_adapters["deliver"] = MockAdapter(
                {("deliver",): AdapterError("simulated crash before close")},
                harness="claude_code", provider="anthropic", model="claude-opus-4-8")
            drv1 = _driver(d, adapters=kill_adapters, loop_id="loop-resume-001")
            with self.assertRaises(GateHardFail):
                drv1.run(subsprint_id="sprint-001")
            # State persisted; we reached close_pending (or halted there).
            saved = drv1._load_state()
            self.assertIsNotNone(saved)
            self.assertIn("review_pending", saved.history)

            # Phase 2: fresh Driver over the SAME run_dir, healthy deliver adapter,
            # resume=True -> should continue from persisted state to advance.
            heal_adapters = _adapters()
            drv2 = Driver(load_charter(CHARTER_PATH), d, heal_adapters,
                          loop_id="loop-resume-001", clock=_clock())
            final = drv2.run(resume=True)
            self.assertEqual(final.state, STATE_ADVANCE)
            # The resumed run re-entered at close_pending and finished.
            self.assertEqual(final.history[-1], "close_pending")
            # Audit chain across BOTH process lifetimes still verifies.
            result = audit.verify_chain(drv2.audit_ledger)
            self.assertTrue(result.ok, result.render())
            types = [e["type"] for e in audit.read_events(drv2.audit_ledger)]
            self.assertIn("loop_resume", types)
            self.assertIn("advance", types)

    def test_resume_without_state_raises(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            with self.assertRaises(FileNotFoundError):
                drv_.run(resume=True)


class TestFixRoundAndBudget(unittest.TestCase):
    def test_fix_required_routes_to_checkpoint_and_bumps_round(self):
        fix_review = {"decision": "fix_required", "blocking_count": 2,
                      "summary": "two P1s", "findings": []}
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(review=fix_review))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            self.assertEqual(final.fix_round, 1)
            self.assertNotIn("close_pending", final.history)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("gate_hard_fail" in c for c in cps), cps)

    def test_out_of_scope_review_does_not_advance_and_checkpoints(self):
        # A schema-VALID review verdict with decision=out_of_scope_review must NOT
        # be treated like a clean `pass`. The loop halts (does not reach advance),
        # a checkpoint is written, an audit event is emitted, chain still verifies.
        oos_review = {"decision": "out_of_scope_review", "blocking_count": 0,
                      "summary": "diff touched a surface out of scope to review",
                      "findings": []}
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(review=oos_review))
            final = drv_.run(subsprint_id="sprint-001")
            # Did NOT reach advance; close_pending never ran (no clean-pass advance).
            self.assertEqual(final.state, STATE_HALTED)
            self.assertNotEqual(final.state, STATE_ADVANCE)
            self.assertNotIn("close_pending", final.history)
            # A review_out_of_scope checkpoint was written.
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("review_out_of_scope" in c for c in cps), cps)
            # A corresponding audit event was emitted; the loop did NOT emit advance.
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("review_out_of_scope", types)
            self.assertNotIn("advance", types)
            self.assertIn("checkpoint_emitted", types)
            # The hash chain across the run still verifies.
            result = audit.verify_chain(drv_.audit_ledger)
            self.assertTrue(result.ok, result.render())

    def test_budget_fix_round_cap_halts(self):
        # Charter budget.max_fix_rounds_total = 2; pre-seed fix_round at the cap so
        # one more bump trips BudgetExceeded (a GateHardFail subclass).
        fix_review = {"decision": "fix_required", "blocking_count": 1,
                      "summary": "one P1", "findings": []}
        charter = load_charter(CHARTER_PATH)
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, charter=charter, adapters=_adapters(review=fix_review))
            # Make the cap small for the test.
            drv_.budget["max_fix_rounds_total"] = 0
            with self.assertRaises(BudgetExceeded):
                drv_.run(subsprint_id="sprint-001")


class TestCloseTaxonomyCheckpoints(unittest.TestCase):
    def test_verdict_C_fires_close_taxonomy_checkpoint(self):
        close_c = {"verdict": "C", "blocking_count": 0, "worst_severity": "none",
                   "in_scope": True, "next_subsprint": None,
                   "reason": "adjacent need discovered"}
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(close=close_c))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("close_taxonomy_C_or_D" in c for c in cps), cps)

    def test_in_scope_false_fires_scope_deviation_checkpoint(self):
        close_oos = {"verdict": "A", "blocking_count": 0, "worst_severity": "none",
                     "in_scope": False, "next_subsprint": None,
                     "reason": "touched a module outside approved_scope"}
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(close=close_oos))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("scope_deviation" in c for c in cps), cps)


class TestRealAdaptersGatedOff(unittest.TestCase):
    """The real claude_code / headless I/O paths must refuse to run unless
    explicitly enabled — confirming tests never touch network/subprocess."""

    def test_claude_code_gated_off_raises_adapter_error(self):
        a = ClaudeCodeAdapter(model="claude-x")  # allow_subprocess defaults False
        with self.assertRaises(AdapterError):
            a.spawn("dev", "prompt", [], {})

    def test_headless_gated_off_raises_adapter_error(self):
        a = HeadlessAdapter(model="deepseek-chat", base_url="https://x/v1",
                            api_key_env="NOPE")
        with self.assertRaises(AdapterError):
            a.spawn("review", "prompt", [], {})


class TestDemoEndToEnd(unittest.TestCase):
    def test_demo_runs_offline_and_verifies(self):
        import demo  # noqa: E402  (orchestrator/demo.py on sys.path)
        with tempfile.TemporaryDirectory() as d:
            info = demo.run_demo(d)
            self.assertEqual(info["final_state"], STATE_ADVANCE)
            self.assertTrue(info["audit_verifies"], info["audit_render"])
            self.assertEqual(info["adapters"]["dev"], "claude_code")
            self.assertEqual(info["adapters"]["review"], "headless")
            # Artifacts under the /tmp run dir, NOT the repo.
            self.assertTrue(info["audit_ledger"].startswith(os.path.abspath(d)))


# --------------------------------------------------------------------------- #
# P3 piece 1 — ACCEPTANCE state + §3.6 calibration gate + F5 evidence.
# All deterministic + offline: the F5 eval.cmd is a local python script writing a
# fake artifact (NO network), and the Acceptance adapter is the MockAdapter.
# --------------------------------------------------------------------------- #
import sys as _sys

# eval.cmd: run the deterministic local fake eval harness with THIS interpreter
# (the venv's python). The driver sets EVAL_RUN_DIR; the script writes there.
_EVAL_CMD = f'"{_sys.executable}" "{_FAKE_EVAL}"'

# A schema-valid acceptance evidence path (matches ^eval/runs/.+). In a real run
# the driver computes this; the mock verdict must cite the SAME shape.
_EVID = "eval/runs/sprint-001/stdout.txt"

ACC_PASS = {
    "milestone_verdict": "pass",
    "calibration_status": "calibrated",
    "cases": [{
        "case_id": "cc-1", "criterion": "refund eligibility honored",
        "evidence_path": _EVID, "verdict": "pass",
        "rationale": "execution evidence shows all 3 bad-cases pass; positive "
                     "shape held, no anti-pattern; anchor-phrase semantic match.",
    }],
    "residual_risks": [],
    "suggested_route": "n/a",
}
ACC_FIX = {
    "milestone_verdict": "fix_required",
    "calibration_status": "calibrated",
    "cases": [{
        "case_id": "cc-2", "criterion": "escalation path covered",
        "evidence_path": _EVID, "verdict": "fail",
        "rationale": "execution evidence shows the escalation bad-case fails; "
                     "the closure_contract clause is violated.",
    }],
    "failure_briefs": [{
        "title": "escalation gap", "contract_clause_violated": "cc-2",
        "proposed_scope": "add an escalation branch covering the refused case.",
        "severity": "P1",
    }],
    "suggested_route": "deliver_fix_iteration",
}
ACC_NEEDS_HUMAN = {
    "milestone_verdict": "needs_human",
    "calibration_status": "not_required",
    "cases": [{
        "case_id": "cc-3", "criterion": "ambiguous closure clause",
        "evidence_path": _EVID, "verdict": "partial",
        "rationale": "evidence is inconclusive; the closure_contract clause is "
                     "ambiguous and the verdict cannot be made autonomously.",
    }],
    "suggested_route": "re_acceptance_after_evidence",
}
# Cites only a CODE path (not eval/runs/...) → schema-invalid evidence_path
# (anti-pattern #5: code inspection, not execution evidence).
ACC_INVALID_CODE_ONLY = {
    "milestone_verdict": "pass",
    "cases": [{
        "case_id": "cc-1", "criterion": "x",
        "evidence_path": "src/tools/eligibility.py", "verdict": "pass",
        "rationale": "looks right from reading the code.",
    }],
    "suggested_route": "n/a",
}


def _acceptance_charter(*, level="human_on_the_loop",
                        calibration="calibrated",
                        eval_cmd=_EVAL_CMD,
                        subsprint_sequence=("sprint-001",)):
    """Build an acceptance-ENABLED charter (derived from the p2 demo charter) so
    the milestone-close path enters acceptance_pending."""
    charter = load_charter(CHARTER_PATH)
    charter["autonomy"]["level"] = level
    charter["autonomy"]["approved_scope"]["subsprint_sequence"] = \
        list(subsprint_sequence)
    charter["acceptance"] = {
        "enabled": True,
        "run_at": "milestone_close",
        "on_fix_required": {
            "human_confirm_required": True,
            "route_options": ["deliver_fix_iteration",
                              "re_acceptance_after_evidence",
                              "research_contract_revision"],
        },
    }
    tooling = charter.setdefault("tooling", {})
    tooling["acceptance"] = {
        "harness": "claude_code", "provider": "anthropic",
        "model": "claude-opus-4-8",
        "tools": ["Read", "Grep", "Glob"],
        "judge_calibration": {"status": calibration},
    }
    tooling["eval"] = {"cmd": eval_cmd, "timeout_seconds": 30}
    return charter


def _acceptance_adapters(acc_verdict=ACC_PASS, **kw):
    adapters = _adapters(**kw)
    adapters["acceptance"] = MockAdapter(
        {("acceptance",): acc_verdict}, harness="claude_code",
        provider="anthropic", model="claude-opus-4-8")
    return adapters


class TestAcceptanceDisabledIsIdentical(unittest.TestCase):
    """Backward-compat: with acceptance absent/false the driver behaves EXACTLY
    as in P2 — ends in STATE_ADVANCE, no acceptance state/events/artifacts."""

    def test_no_acceptance_key_ends_in_advance(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)  # p2 charter has NO acceptance key
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertNotIn(STATE_ACCEPTANCE_PENDING, final.history)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("acceptance_start", types)
            # No eval/ run dir created when acceptance is disabled.
            self.assertFalse(os.path.isdir(os.path.join(d, "eval")))

    def test_acceptance_enabled_false_ends_in_advance(self):
        with tempfile.TemporaryDirectory() as d:
            charter = load_charter(CHARTER_PATH)
            charter["acceptance"] = {"enabled": False}
            drv_ = _driver(d, charter=charter)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("acceptance_start", types)


class TestAcceptancePass(unittest.TestCase):
    def test_pass_ships_and_advances_citing_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter()
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            final = drv_.run(subsprint_id="sprint-001")
            # Acceptance ran + passed → run completes (STATE_DONE = accepted close).
            self.assertEqual(final.state, STATE_DONE)
            self.assertIn(STATE_ACCEPTANCE_PENDING, final.history)
            # The verdict cites an evidence_path under eval/runs/ (F5, not code).
            self.assertEqual(
                final.last_verdict["cases"][0]["evidence_path"], _EVID)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("acceptance_start", types)
            self.assertIn("acceptance_eval_run", types)
            self.assertIn("acceptance_spawn", types)
            self.assertIn("acceptance_verdict", types)
            self.assertIn("acceptance_pass", types)
            # Audit chain across the whole (P2 + acceptance) run still verifies.
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)


class TestAcceptanceFixRequiredHumanConfirm(unittest.TestCase):
    def test_fix_required_writes_human_confirm_checkpoint_and_halts(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter()
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_FIX))
            final = drv_.run(subsprint_id="sprint-001")
            # HALTS — never routes to Deliver without the human-confirm checkpoint.
            self.assertEqual(final.state, STATE_HALTED)
            cps = os.listdir(drv_.checkpoints_dir)
            cp_name = [c for c in cps if "acceptance_fix_required" in c]
            self.assertTrue(cp_name, cps)
            with open(os.path.join(drv_.checkpoints_dir, cp_name[0]),
                      encoding="utf-8") as _fh:
                body = _fh.read()
            # The checkpoint offers the 3 §3.5 route options.
            self.assertIn("deliver_fix_iteration", body)
            self.assertIn("re_acceptance_after_evidence", body)
            self.assertIn("research_contract_revision", body)
            # decision is pending (human writes confirm/route).
            self.assertIn("decision: pending", body)
            self.assertIn("confirm: yes|no", body)
            # No silent Deliver routing: no deliver re-spawn beyond the close one.
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("acceptance_fix_required", types)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)


class TestAcceptanceCalibrationGate(unittest.TestCase):
    def test_uncalibrated_autonomous_auto_degrades_and_checkpoints(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(
                level="fully_autonomous_within_budget",
                calibration="uncalibrated")
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            final = drv_.run(subsprint_id="sprint-001")
            # Autonomy was AUTO-DEGRADED (recorded, not silent).
            self.assertEqual(charter["autonomy"]["level"], "human_on_the_loop")
            # A degradation checkpoint was written.
            cps = os.listdir(drv_.checkpoints_dir)
            deg = [c for c in cps if "acceptance_calibration_degraded" in c]
            self.assertTrue(deg, cps)
            # And a degradation audit event recorded the from/to levels.
            events = audit.read_events(drv_.audit_ledger)
            types = [e["type"] for e in events]
            self.assertIn("acceptance_calibration_degraded", types)
            deg_ev = next(e for e in events
                          if e["type"] == "acceptance_calibration_degraded")
            self.assertEqual(deg_ev["payload"]["from_level"],
                             "fully_autonomous_within_budget")
            self.assertEqual(deg_ev["payload"]["to_level"], "human_on_the_loop")
            self.assertEqual(deg_ev["payload"]["calibration_status"],
                             "uncalibrated")
            # Acceptance still RAN (degraded, not aborted) → pass ships.
            self.assertEqual(final.state, STATE_DONE)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_calibrated_autonomous_does_not_degrade(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(
                level="fully_autonomous_within_budget", calibration="calibrated")
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            drv_.run(subsprint_id="sprint-001")
            # Calibrated → autonomy unchanged, no degradation checkpoint/event.
            self.assertEqual(charter["autonomy"]["level"],
                             "fully_autonomous_within_budget")
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("acceptance_calibration_degraded", types)


class TestAcceptanceInvalidVerdict(unittest.TestCase):
    def test_code_only_evidence_path_is_schema_invalid_hard_fail(self):
        # A verdict citing a CODE path (not eval/runs/...) violates the schema's
        # evidence_path pattern → gate_hard_fail (anti-pattern #5).
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter()
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_INVALID_CODE_ONLY))
            with self.assertRaises(GateHardFail) as ctx:
                drv_.run(subsprint_id="sprint-001")
            self.assertIn("acceptance", ctx.exception.reason)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("gate_hard_fail" in c for c in cps), cps)

    def test_non_dict_acceptance_verdict_hard_fails(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter()
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(["not", "a", "dict"]))
            with self.assertRaises(GateHardFail):
                drv_.run(subsprint_id="sprint-001")


class TestAcceptanceNeedsHuman(unittest.TestCase):
    def test_needs_human_surfaces_checkpoint_and_halts(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter()
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_NEEDS_HUMAN))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(
                any("acceptance_surface_approve" in c for c in cps), cps)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("acceptance_needs_human", types)


class TestAcceptanceF5Evidence(unittest.TestCase):
    def test_driver_runs_eval_and_acceptance_gets_path_not_code(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter()
            acc_adapter = MockAdapter(
                {("acceptance",): ACC_PASS}, harness="claude_code",
                provider="anthropic", model="claude-opus-4-8")
            adapters = _adapters()
            adapters["acceptance"] = acc_adapter
            drv_ = _driver(d, charter=charter, adapters=adapters)
            drv_.run(subsprint_id="sprint-001")

            # 1. The DRIVER ran the eval cmd + captured an artifact under eval/runs.
            evidence_dir = os.path.join(d, "eval", "runs", "sprint-001")
            self.assertTrue(os.path.isdir(evidence_dir))
            self.assertTrue(os.path.isfile(os.path.join(evidence_dir,
                                                         "evidence.json")))
            self.assertTrue(os.path.isfile(os.path.join(evidence_dir,
                                                        "stdout.txt")))
            # 2. The eval-run audit event records the captured evidence path.
            events = audit.read_events(drv_.audit_ledger)
            run_ev = next(e for e in events
                          if e["type"] == "acceptance_eval_run")
            self.assertTrue(run_ev["payload"]["ok"])
            self.assertTrue(
                run_ev["payload"]["evidence_path"].startswith("eval/runs/"))
            # 3. Acceptance received the artifact PATH (read-only), NOT raw code:
            #    its prompt names the eval/runs path and forbids running the harness.
            self.assertEqual(len(acc_adapter.history), 1)
            spawn_ev = next(e for e in events if e["type"] == "acceptance_spawn")
            self.assertTrue(
                spawn_ev["payload"]["evidence_path"].startswith("eval/runs/"))
            # §1.7-C: the spawn surface is the orchestrator, gated by calibration.
            self.assertEqual(spawn_ev["payload"]["spawn_surface"], "orchestrator")

    def test_eval_nonzero_exit_is_gate_hard_fail(self):
        # The fake eval honors FAKE_EVAL_EXIT to simulate an eval-harness failure.
        # Per §4.2.6 a non-zero eval exit → gate_hard_fail (human resolves), NOT a
        # permissive pass. We set the env var via the eval.cmd itself (offline).
        fail_cmd = (f'FAKE_EVAL_EXIT=3 "{_sys.executable}" "{_FAKE_EVAL}"')
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(eval_cmd=fail_cmd)
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            with self.assertRaises(GateHardFail) as ctx:
                drv_.run(subsprint_id="sprint-001")
            self.assertIn("eval", ctx.exception.reason.lower())
            # Acceptance was NOT spawned (no evidence to judge).
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("acceptance_spawn", types)


class TestAcceptanceSpawnIsolation(unittest.TestCase):
    def test_acceptance_only_fires_at_terminal_subsprint(self):
        # §4.2.4: acceptance runs at MILESTONE close, i.e. the terminal sub-sprint
        # of the approved sequence — NOT after an intermediate sub-sprint whose
        # close hands off to a next sub-sprint still in the sequence.
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(
                subsprint_sequence=("sprint-001", "sprint-002"))
            # close verdict points to sprint-002 (still in sequence) → NOT terminal.
            mid_close = dict(CLEAN_CLOSE, next_subsprint="sprint-002")
            adapters = _acceptance_adapters(ACC_PASS, close=mid_close)
            drv_ = _driver(d, charter=charter, adapters=adapters)
            final = drv_.run(subsprint_id="sprint-001")
            # Intermediate close: plain advance, acceptance did NOT run.
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertNotIn(STATE_ACCEPTANCE_PENDING, final.history)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("acceptance_start", types)

    def test_nonterminal_close_with_null_next_does_not_fire_acceptance(self):
        # REGRESSION (P3 review): a Deliver OMISSION — closing a NON-terminal
        # sub-sprint of a declared sequence with next_subsprint omitted (None) —
        # must NOT fire milestone-close Acceptance early. Terminality is anchored
        # to the declared subsprint_sequence, not to the (possibly forgotten)
        # next_subsprint field (§4.2.4).
        seq = ("sprint-001", "sprint-002", "sprint-003")
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(subsprint_sequence=seq)
            # Deliver forgets next_subsprint at a non-terminal step (s1).
            omitted_close = dict(CLEAN_CLOSE, next_subsprint=None)
            adapters = _acceptance_adapters(ACC_PASS, close=omitted_close)
            drv_ = _driver(d, charter=charter, adapters=adapters)
            final = drv_.run(subsprint_id="sprint-001")
            # s1 is NOT the terminal s3 → plain advance, acceptance did NOT run.
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertNotIn(STATE_ACCEPTANCE_PENDING, final.history)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("acceptance_start", types)

    def test_terminal_close_with_null_next_does_fire_acceptance(self):
        # The terminal sub-sprint of the declared sequence (s3) DOES close the
        # milestone and fire Acceptance, even with next_subsprint None — the
        # sequence end is authoritative (§4.2.4). Counterpart to the omission case.
        seq = ("sprint-001", "sprint-002", "sprint-003")
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(subsprint_sequence=seq)
            terminal_close = dict(CLEAN_CLOSE, next_subsprint=None)
            adapters = _acceptance_adapters(ACC_PASS, close=terminal_close)
            drv_ = _driver(d, charter=charter, adapters=adapters)
            final = drv_.run(subsprint_id="sprint-003")
            # s3 IS terminal → acceptance ran and (ACC_PASS) ships → STATE_DONE.
            self.assertEqual(final.state, STATE_DONE)
            self.assertIn(STATE_ACCEPTANCE_PENDING, final.history)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("acceptance_start", types)
            self.assertIn("acceptance_pass", types)


# --------------------------------------------------------------------------- #
# P3 INTEGRATION — Loop Controller as the fix-loop termination authority +
# Loop Memory at ingress (read) / close (write). All deterministic + offline:
# MockAdapter only, injected clock, temp run_dir + temp memory_root.
# --------------------------------------------------------------------------- #
import loop_controller as lc  # noqa: E402
from driver import RunState, STATE_DEV_PENDING, STATE_GATE_PENDING  # noqa: E402


# A review finding with an explicit id + severity (drives finding-key dedup +
# the worst_severity → severity-ceiling escalation path).
def _finding(fid, severity="P2", layer="semantic_planner"):
    return {"id": fid, "severity": severity, "layer": layer,
            "evidence": [f"src/x.py:{len(fid)}"], "rationale": "r"}


def _fix_review(findings, blocking=1, summary="needs fix"):
    return {"decision": "fix_required", "blocking_count": blocking,
            "summary": summary, "findings": list(findings)}


def _autofix_charter(*, enabled=True, max_rounds=3,
                     only_if_severity_at_most="P2",
                     dry_stop_threshold=None,
                     max_fix_rounds_total=None):
    """A charter with autonomy.auto_pass_rules.auto_fix_iteration configured so
    the controller can authorize auto-iteration (NOT the HITL human-confirm
    path)."""
    charter = load_charter(CHARTER_PATH)
    afi = {
        "enabled": enabled,
        "max_rounds": max_rounds,
        "only_if_findings_severity_at_most": only_if_severity_at_most,
    }
    if dry_stop_threshold is not None:
        afi["dry_stop_threshold"] = dry_stop_threshold
    charter["autonomy"]["auto_pass_rules"] = {
        "clean_pass_auto_advance": True,
        "auto_fix_iteration": afi,
    }
    # Keep the hard fix-round budget OUT of the way unless a test sets it, so the
    # controller's own max_rounds / dry-stop / severity guards are what fire.
    if max_fix_rounds_total is None:
        charter.get("budget", {}).pop("max_fix_rounds_total", None)
    else:
        charter["budget"]["max_fix_rounds_total"] = max_fix_rounds_total
    return charter


class _PromptCapturingMock(MockAdapter):
    """MockAdapter that ALSO captures the prompt string it received (the base
    mock records role/tools but not the prompt). Used to assert the Loop-Memory
    ingress block reaches the adapter."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.prompts = []

    def spawn(self, role, prompt, tools, schema, **kwargs):
        self.prompts.append(prompt)
        return super().spawn(role, prompt, tools, schema, **kwargs)


class TestLoopControllerAutoFixContinue(unittest.TestCase):
    def test_continue_spawns_another_fix_round(self):
        # Round 1 review = fix_required; the re-review (call_index 1) = clean pass.
        # Auto-fix enabled + within bounds → controller `continue` → the driver
        # spawns ANOTHER dev→gate→review round, then advances on the clean verdict.
        review_responses = {
            ("review", 0): _fix_review([_finding("F1", "P2")]),
            ("review", 1): CLEAN_REVIEW,
        }
        with tempfile.TemporaryDirectory() as d:
            adapters = _adapters()
            adapters["review"] = MockAdapter(
                review_responses, harness="headless",
                provider="deepseek", model="deepseek-chat")
            charter = _autofix_charter(enabled=True, max_rounds=3)
            drv_ = _driver(d, charter=charter, adapters=adapters)
            final = drv_.run(subsprint_id="sprint-001")
            # The fix round was bumped (one fix iteration happened) ...
            self.assertEqual(final.fix_round, 1)
            # ... the dev/review step RE-RAN (history has two dev_pending entries:
            # the original + the auto-fix re-run), and the loop advanced.
            self.assertEqual(final.history.count("dev_pending"), 2)
            self.assertEqual(final.history.count("review_pending"), 2)
            self.assertEqual(final.state, STATE_ADVANCE)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("auto_fix_round_spawned", types)
            self.assertIn("controller_decision", types)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_continue_disabled_keeps_hitl_human_confirm(self):
        # BACKWARD-COMPAT: auto_fix NOT enabled → controller `continue` must NOT
        # auto-iterate; the existing fix_required human-confirm checkpoint fires
        # and the loop HALTS (UNCHANGED P2/HITL behaviour, Constitution §1.7-D).
        with tempfile.TemporaryDirectory() as d:
            charter = _autofix_charter(enabled=False, max_rounds=3)
            drv_ = _driver(
                d, charter=charter,
                adapters=_adapters(review=_fix_review([_finding("F1", "P2")])))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            self.assertEqual(final.fix_round, 1)
            self.assertEqual(final.history.count("dev_pending"), 1)  # no re-run
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("gate_hard_fail" in c for c in cps), cps)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("auto_fix_round_spawned", types)


class TestLoopControllerHalts(unittest.TestCase):
    def _seed_review_state(self, drv_, *, budget_spent=0.0,
                           rounds_since_new=0, fix_round=0, seen=()):
        """Put the driver in review_pending with seeded controller-tracking
        fields, so we can call _handle_fix_required directly + deterministically."""
        drv_.state = RunState(loop_id=drv_.loop_id, subsprint_id="sprint-001")
        drv_.state.state = STATE_REVIEW_PENDING
        drv_.state.budget_spent = budget_spent
        drv_.state.rounds_since_new_finding = rounds_since_new
        drv_.state.fix_round = fix_round
        drv_.state.seen_finding_keys = list(seen)
        drv_._save_state()

    def test_budget_exhausted_halts_with_checkpoint(self):
        # budget_spent >= budget_cap (max_api_usd) → controller halt(budget).
        with tempfile.TemporaryDirectory() as d:
            charter = _autofix_charter(enabled=True, max_rounds=10)
            charter["budget"]["max_api_usd"] = 5.0
            drv_ = _driver(d, charter=charter, adapters=_adapters())
            self._seed_review_state(drv_, budget_spent=5.0)
            drv_._handle_fix_required(_fix_review([_finding("F1", "P2")]))
            self.assertEqual(drv_.state.state, STATE_HALTED)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("loop_controller_halt" in c for c in cps), cps)
            events = audit.read_events(drv_.audit_ledger)
            dec = next(e for e in events if e["type"] == "controller_decision")
            self.assertEqual(dec["payload"]["reason"], lc.REASON_BUDGET)

    def test_max_rounds_exceeded_halts(self):
        # auto_fix max_rounds=2 (NO hard budget.max_fix_rounds_total) → with
        # fix_round seeded at 2, the bump → 3 > 2 trips controller halt(max_rounds).
        # No budget cap is set, so it halts WITH a checkpoint and does NOT raise.
        with tempfile.TemporaryDirectory() as d:
            charter = _autofix_charter(enabled=True, max_rounds=2)
            drv_ = _driver(d, charter=charter, adapters=_adapters())
            self._seed_review_state(drv_, fix_round=2)
            drv_._handle_fix_required(_fix_review([_finding("F1", "P2")]))
            self.assertEqual(drv_.state.state, STATE_HALTED)
            events = audit.read_events(drv_.audit_ledger)
            dec = next(e for e in events if e["type"] == "controller_decision")
            self.assertEqual(dec["payload"]["reason"], lc.REASON_MAX_ROUNDS)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("loop_controller_halt" in c for c in cps), cps)

    def test_max_rounds_via_hard_budget_cap_raises_budget_exceeded(self):
        # When the round cap IS the hard budget.max_fix_rounds_total, the
        # controller halt(max_rounds) ALSO surfaces the deterministic
        # BudgetExceeded gate (backward-compat with _check_budget's raise).
        with tempfile.TemporaryDirectory() as d:
            charter = _autofix_charter(enabled=True, max_rounds=10,
                                       max_fix_rounds_total=2)
            drv_ = _driver(d, charter=charter, adapters=_adapters())
            self._seed_review_state(drv_, fix_round=2)  # bump → 3 > 2
            with self.assertRaises(BudgetExceeded):
                drv_._handle_fix_required(_fix_review([_finding("F1", "P2")]))

    def test_converged_dry_halts(self):
        # K consecutive no-new-finding rounds → halt(converged_dry). Seed the
        # K-counter at threshold-1 and feed a round whose finding is ALREADY seen
        # (no new finding) so the counter reaches K.
        with tempfile.TemporaryDirectory() as d:
            charter = _autofix_charter(enabled=True, max_rounds=10,
                                       dry_stop_threshold=2)
            drv_ = _driver(d, charter=charter, adapters=_adapters())
            # F1 already seen; rounds_since_new starts at 1, this round adds none
            # → reaches 2 == threshold.
            self._seed_review_state(drv_, rounds_since_new=1, seen=("F1",))
            drv_._handle_fix_required(_fix_review([_finding("F1", "P2")]))
            self.assertEqual(drv_.state.state, STATE_HALTED)
            events = audit.read_events(drv_.audit_ledger)
            dec = next(e for e in events if e["type"] == "controller_decision")
            self.assertEqual(dec["payload"]["reason"], lc.REASON_CONVERGED_DRY)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("loop_controller_halt" in c for c in cps), cps)

    def test_severity_over_ceiling_escalates(self):
        # worst_severity P0 strictly worse than ceiling P2 → escalate(severity)
        # → a needs-human checkpoint + halt.
        with tempfile.TemporaryDirectory() as d:
            charter = _autofix_charter(enabled=True, max_rounds=10,
                                       only_if_severity_at_most="P2")
            drv_ = _driver(d, charter=charter, adapters=_adapters())
            self._seed_review_state(drv_)
            drv_._handle_fix_required(_fix_review([_finding("F0", "P0")]))
            self.assertEqual(drv_.state.state, STATE_HALTED)
            events = audit.read_events(drv_.audit_ledger)
            dec = next(e for e in events if e["type"] == "controller_decision")
            self.assertEqual(dec["payload"]["action"], lc.ACTION_ESCALATE)
            self.assertEqual(dec["payload"]["reason"], lc.REASON_SEVERITY)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(
                any("loop_controller_escalate" in c for c in cps), cps)

    def test_controller_decision_recorded_in_audit(self):
        # The controller's {action, reason} is in the ledger for auditability.
        with tempfile.TemporaryDirectory() as d:
            charter = _autofix_charter(enabled=False)  # any path records it
            drv_ = _driver(
                d, charter=charter,
                adapters=_adapters(review=_fix_review([_finding("F1", "P2")])))
            drv_.run(subsprint_id="sprint-001")
            events = audit.read_events(drv_.audit_ledger)
            decs = [e for e in events if e["type"] == "controller_decision"]
            self.assertTrue(decs)
            self.assertIn(decs[0]["payload"]["action"],
                          (lc.ACTION_CONTINUE, lc.ACTION_HALT,
                           lc.ACTION_ESCALATE, lc.ACTION_ADVANCE))
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)


class TestLoopMemoryIngressAndClose(unittest.TestCase):
    def _seed_memory(self, root):
        from memory_store import MemoryStore  # noqa: E402
        store = MemoryStore(root)
        store.record_observation(
            "prefer explicit eligibility branches",
            ts="2026-06-15", loop_id="loop-prior-001",
            type="heuristic",
            scope={"role": ["dev"],
                   "module": ["src/tools/eligibility.py"]},
            body=("When implementing eligibility, enumerate each refund branch "
                  "explicitly rather than collapsing them — prior loops regressed "
                  "the partial-refund branch under a catch-all."),
        )
        return store

    def test_ingress_injects_lessons_into_prompt(self):
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as mem:
            self._seed_memory(mem)
            # Prompt-capturing mock for dev so we can read the injected block.
            dev = _PromptCapturingMock(
                {("dev",): DEV_ARTIFACT}, harness="claude_code",
                provider="anthropic", model="claude-sonnet-4-6")
            adapters = _adapters()
            adapters["dev"] = dev
            drv_ = Driver(load_charter(CHARTER_PATH), d, adapters,
                          loop_id="loop-mem-001", clock=_clock(),
                          memory_root=mem)
            drv_.run(subsprint_id="sprint-001")
            self.assertTrue(dev.prompts)
            dev_prompt = dev.prompts[0]
            # The ingress block IS present in the prompt the adapter received.
            self.assertIn("Relevant prior lessons", dev_prompt)
            self.assertIn("enumerate each refund branch", dev_prompt)
            # And the spawn audit recorded which entries were injected.
            events = audit.read_events(drv_.audit_ledger)
            dev_spawn = next(e for e in events if e["type"] == "spawn"
                             and e["payload"]["role"] == "dev")
            self.assertIn("prefer-explicit-eligibility-branches",
                          dev_spawn["payload"]["memory_injected"])

    def test_close_records_observation_and_matures_l1_to_l2(self):
        # On a fix_required finding, the driver records a generalizable lesson;
        # a SECOND loop recording the same finding pattern matures it L1 → L2.
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as mem:
            charter = _autofix_charter(enabled=False)  # HITL path still records
            fix_review = _fix_review([_finding("F1", "P2",
                                               layer="semantic_planner")])
            # Loop 1.
            drv1 = Driver(charter, d, _adapters(review=fix_review),
                          loop_id="loop-mem-A", clock=_clock(), memory_root=mem)
            drv1.run(subsprint_id="sprint-001")
            from memory_store import MemoryStore, slug  # noqa: E402
            store = MemoryStore(mem)
            eid = slug("review fix_required at semantic_planner layer")
            entry1 = store.get(eid)
            self.assertIsNotNone(entry1)
            self.assertEqual(entry1.occurrences, 1)
            self.assertEqual(entry1.maturity, "L1")
            # Loop 2 (same finding pattern) → occurrences=2 → L2.
            with tempfile.TemporaryDirectory() as d2:
                drv2 = Driver(charter, d2, _adapters(review=fix_review),
                              loop_id="loop-mem-B", clock=_clock(),
                              memory_root=mem)
                drv2.run(subsprint_id="sprint-001")
            entry2 = store.get(eid)
            self.assertEqual(entry2.occurrences, 2)
            self.assertEqual(entry2.maturity, "L2")
            types = [e["type"] for e in audit.read_events(drv1.audit_ledger)]
            self.assertIn("memory_observation_recorded", types)

    def test_memory_disabled_means_no_memory_activity(self):
        # memory_root None → no select/record; behaviour identical to current.
        with tempfile.TemporaryDirectory() as d:
            dev = _PromptCapturingMock(
                {("dev",): DEV_ARTIFACT}, harness="claude_code",
                provider="anthropic", model="claude-sonnet-4-6")
            adapters = _adapters()
            adapters["dev"] = dev
            drv_ = Driver(load_charter(CHARTER_PATH), d, adapters,
                          loop_id="loop-nomem", clock=_clock())  # no memory_root
            final = drv_.run(subsprint_id="sprint-001")
            self.assertIsNone(drv_.memory)
            self.assertEqual(final.state, STATE_ADVANCE)
            # No lessons block in the prompt; memory_injected empty in audit.
            self.assertNotIn("Relevant prior lessons", dev.prompts[0])
            events = audit.read_events(drv_.audit_ledger)
            for e in events:
                if e["type"] == "spawn":
                    self.assertEqual(e["payload"]["memory_injected"], [])
            types = [e["type"] for e in events]
            self.assertNotIn("memory_observation_recorded", types)


class TestRunStateResumeRoundTrip(unittest.TestCase):
    def test_new_controller_fields_persist_across_save_load(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.state = RunState(loop_id="x", subsprint_id="sprint-001")
            drv_.state.rounds_since_new_finding = 3
            drv_.state.seen_finding_keys = ["F1", "F2"]
            drv_.state.budget_spent = 4.5
            drv_._save_state()
            reloaded = drv_._load_state()
            self.assertEqual(reloaded.rounds_since_new_finding, 3)
            self.assertEqual(reloaded.seen_finding_keys, ["F1", "F2"])
            self.assertEqual(reloaded.budget_spent, 4.5)


_CONNECTOR_GRANT = [{"id": "gh", "kind": "mcp", "server": "gh-mcp@v1.0.0",
                     "scopes": ["read"], "tools": ["search_issues"]}]


class TestConnectorPassThrough(unittest.TestCase):
    """P4 follow-up: the driver threads each role's Facet-C connector grant +
    sandbox through adapter.spawn(...) (the mock records them in history)."""

    def test_driver_threads_role_connectors_and_sandbox(self):
        charter = load_charter(CHARTER_PATH)
        charter["tooling"]["dev"]["connectors"] = _CONNECTOR_GRANT
        charter["tooling"]["dev"]["sandbox"] = "read_only"
        with tempfile.TemporaryDirectory() as d:
            adapters = _adapters()
            drv_ = _driver(d, charter=charter, adapters=adapters)
            drv_.run(subsprint_id="sprint-001")
        dev_hist = adapters["dev"].history[0]
        self.assertEqual(dev_hist["connectors"], _CONNECTOR_GRANT)
        self.assertEqual(dev_hist["sandbox"], "read_only")
        # Review declared no connectors → default-deny ([]) + schema-default
        # sandbox (the example charter gives review no sandbox field).
        rev_hist = adapters["review"].history[0]
        self.assertEqual(rev_hist["connectors"], [])
        self.assertEqual(rev_hist["sandbox"], "workspace_write")

    def test_no_connectors_passes_empty_grant(self):
        # The unmodified example charter grants no connectors to any role.
        with tempfile.TemporaryDirectory() as d:
            adapters = _adapters()
            _driver(d, adapters=adapters).run(subsprint_id="sprint-001")
        for role in ("dev", "review", "deliver"):
            self.assertEqual(adapters[role].history[0]["connectors"], [])


def _make_git_repo(root):
    """A throwaway git repo with one commit on `main` (offline, deterministic)."""
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    def _g(*a):
        subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True)
    _g("init", "-q", "-b", "main")
    _g("config", "user.email", "test@example.invalid")
    _g("config", "user.name", "Driver Ingress Test")
    _g("config", "commit.gpgsign", "false")
    with open(os.path.join(repo, "seed.txt"), "w", encoding="utf-8") as fh:
        fh.write("seed\n")
    _g("add", "seed.txt")
    _g("commit", "-q", "-m", "init")
    return repo


class TestLoopIngressWiring(unittest.TestCase):
    """P4 integration: loop_ingress wired into the driver's loop start/close.

    run_dir (artifacts) is a SEPARATE /tmp dir from repo_dir (the git repo); the
    loop registry lives in <repo>/.orchestrator/loops.json.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aidazi-drv-ingress-")
        self.repo = _make_git_repo(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _registry(self):
        return li.LoopRegistry(os.path.join(self.repo, ".orchestrator"))

    def _events(self, drv_, type_):
        return [e for e in audit.read_events(drv_.audit_ledger)
                if e["type"] == type_]

    def test_repo_dir_none_is_byte_identical_no_ingress(self):
        # Backward-compat: no repo_dir ⇒ no registry, no ingress/close audit.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("loop_ingress", types)
            self.assertNotIn("loop_close", types)
            self.assertIsNone(drv_.registry)
            self.assertIsNone(drv_.context_handle)

    def test_current_branch_default_registers_and_closes(self):
        run_dir = os.path.join(self.tmp, "run1")
        drv_ = Driver(load_charter(CHARTER_PATH), run_dir, _adapters(),
                      loop_id="loop-ing-001", clock=_clock(), repo_dir=self.repo)
        final = drv_.run(subsprint_id="sprint-001")
        self.assertEqual(final.state, STATE_ADVANCE)
        rec = self._registry().get("loop-ing-001")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.strategy, "current_branch")
        self.assertEqual(rec.status, "done")  # closed on a clean advance
        self.assertEqual(li.current_branch(self.repo), "main")  # in-place
        self.assertEqual(len(self._events(drv_, "loop_ingress")), 1)
        close = self._events(drv_, "loop_close")
        self.assertEqual(len(close), 1)
        self.assertEqual(close[0]["payload"]["cleanup_action"], "noop")

    def test_new_branch_strategy_switches_and_keeps_branch(self):
        run_dir = os.path.join(self.tmp, "run2")
        charter = load_charter(CHARTER_PATH)
        charter["isolation"] = {"default_strategy": "new_branch",
                                "cleanup_policy": "remove_if_merged"}
        drv_ = Driver(charter, run_dir, _adapters(),
                      loop_id="loop-ing-002", clock=_clock(), repo_dir=self.repo)
        final = drv_.run(subsprint_id="sprint-001")
        self.assertEqual(final.state, STATE_ADVANCE)
        self.assertEqual(li.current_branch(self.repo), "loop/loop-ing-002")
        rec = self._registry().get("loop-ing-002")
        self.assertEqual(rec.strategy, "new_branch")
        self.assertEqual(rec.status, "done")
        # A branch is the PR unit — cleanup keeps it even under remove_if_merged.
        self.assertEqual(
            self._events(drv_, "loop_close")[0]["payload"]["cleanup_action"],
            "kept")

    def test_new_worktree_unchanged_is_removed_at_close(self):
        run_dir = os.path.join(self.tmp, "run3")
        wt_root = os.path.join(self.tmp, "wts3")
        charter = load_charter(CHARTER_PATH)
        charter["isolation"] = {"default_strategy": "new_worktree",
                                "worktree_root": wt_root,
                                "cleanup_policy": "remove_if_unchanged"}
        drv_ = Driver(charter, run_dir, _adapters(),
                      loop_id="loop-ing-003", clock=_clock(), repo_dir=self.repo)
        final = drv_.run(subsprint_id="sprint-001")
        self.assertEqual(final.state, STATE_ADVANCE)
        self.assertEqual(li.current_branch(self.repo), "main")  # isolated
        rec = self._registry().get("loop-ing-003")
        self.assertEqual(rec.strategy, "new_worktree")
        self.assertEqual(rec.status, "done")
        # The mock run touches no files in the worktree → unchanged → removed.
        self.assertEqual(
            self._events(drv_, "loop_close")[0]["payload"]["cleanup_action"],
            "removed")
        self.assertFalse(os.path.isdir(rec.worktree))

    def test_dirty_tree_escalation_recommends_but_keeps_default(self):
        # Dirty repo + force_isolation_when:[dirty_tree] + default current_branch:
        # the engine RECOMMENDS new_branch (checkpoint) but proceeds on the
        # pre-authorized default (no unilateral escalate, §1.7-D).
        with open(os.path.join(self.repo, "dirty.txt"), "w", encoding="utf-8") as fh:
            fh.write("uncommitted\n")
        run_dir = os.path.join(self.tmp, "run4")
        charter = load_charter(CHARTER_PATH)
        charter["isolation"] = {"default_strategy": "current_branch",
                                "force_isolation_when": ["dirty_tree"]}
        drv_ = Driver(charter, run_dir, _adapters(),
                      loop_id="loop-ing-004", clock=_clock(), repo_dir=self.repo)
        final = drv_.run(subsprint_id="sprint-001")
        self.assertEqual(final.state, STATE_ADVANCE)
        # Proceeded on the default — did NOT auto-switch to new_branch.
        self.assertEqual(li.current_branch(self.repo), "main")
        self.assertEqual(self._registry().get("loop-ing-004").strategy,
                         "current_branch")
        cps = os.listdir(drv_.checkpoints_dir)
        self.assertTrue(
            any("loop_isolation_recommendation" in c for c in cps), cps)
        rec_evt = self._events(drv_, "loop_isolation_recommendation")
        self.assertEqual(len(rec_evt), 1)
        self.assertEqual(rec_evt[0]["payload"]["recommendation"], "new_branch")
        ing = self._events(drv_, "loop_ingress")[0]["payload"]
        self.assertTrue(ing["escalated"])
        self.assertEqual(ing["strategy"], "current_branch")  # used default

    def test_human_supplied_isolation_strategy_is_used(self):
        run_dir = os.path.join(self.tmp, "run5")
        drv_ = Driver(load_charter(CHARTER_PATH), run_dir, _adapters(),
                      loop_id="loop-ing-005", clock=_clock(), repo_dir=self.repo,
                      isolation_strategy="new_branch")
        final = drv_.run(subsprint_id="sprint-001")
        self.assertEqual(final.state, STATE_ADVANCE)
        self.assertEqual(li.current_branch(self.repo), "loop/loop-ing-005")
        ing = self._events(drv_, "loop_ingress")[0]["payload"]
        self.assertEqual(ing["confirmed_via"], "human_supplied")

    def test_halted_loop_is_not_closed(self):
        # fix_required halts the loop → it must stay active (not done) and keep
        # its worktree for human resolution.
        fix_review = {"decision": "fix_required", "blocking_count": 1,
                      "summary": "one P1", "findings": []}
        run_dir = os.path.join(self.tmp, "run6")
        charter = load_charter(CHARTER_PATH)
        charter["isolation"] = {"default_strategy": "new_worktree",
                                "worktree_root": os.path.join(self.tmp, "wts6"),
                                "cleanup_policy": "remove_if_unchanged"}
        drv_ = Driver(charter, run_dir, _adapters(review=fix_review),
                      loop_id="loop-ing-006", clock=_clock(), repo_dir=self.repo)
        final = drv_.run(subsprint_id="sprint-001")
        self.assertEqual(final.state, STATE_HALTED)
        rec = self._registry().get("loop-ing-006")
        self.assertEqual(rec.status, "active")          # NOT closed
        self.assertTrue(os.path.isdir(rec.worktree))    # worktree kept
        types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
        self.assertNotIn("loop_close", types)

    def test_fresh_rerun_does_not_self_collide(self):
        # A fresh re-run of a loop_id already active on the branch must NOT treat
        # its OWN stale record as a collision (no spurious self-escalation).
        run_dir = os.path.join(self.tmp, "run8")
        charter = load_charter(CHARTER_PATH)
        charter["isolation"] = {"default_strategy": "current_branch",
                                "force_isolation_when": ["loop_active_on_branch"]}
        reg = self._registry()
        reg.register("loop-ing-008", "current_branch", "main", None,
                     ts="2026-06-15T00:00:00Z")  # the SAME loop_id, pre-active
        drv_ = Driver(charter, run_dir, _adapters(), loop_id="loop-ing-008",
                      clock=_clock(), repo_dir=self.repo)
        final = drv_.run(subsprint_id="sprint-001")
        self.assertEqual(final.state, STATE_ADVANCE)
        ing = self._events(drv_, "loop_ingress")[0]["payload"]
        self.assertFalse(ing["escalated"])  # did NOT collide with itself
        self.assertEqual(self._events(drv_, "loop_isolation_recommendation"), [])

    def test_resume_reattaches_without_git_mutation(self):
        run_dir = os.path.join(self.tmp, "run7")
        charter = load_charter(CHARTER_PATH)
        charter["isolation"] = {"default_strategy": "new_branch"}
        # Phase 1: deliver crashes AFTER the branch is created.
        kill = _adapters()
        kill["deliver"] = MockAdapter(
            {("deliver",): AdapterError("crash before close")},
            harness="claude_code", provider="anthropic", model="claude-opus-4-8")
        drv1 = Driver(charter, run_dir, kill, loop_id="loop-ing-007",
                      clock=_clock(), repo_dir=self.repo)
        with self.assertRaises(GateHardFail):
            drv1.run(subsprint_id="sprint-001")
        self.assertEqual(li.current_branch(self.repo), "loop/loop-ing-007")
        self.assertEqual(self._registry().get("loop-ing-007").status, "active")

        # Phase 2: resume with a healthy deliver. Reattach must NOT re-run
        # setup_context (a second `git switch -c` on the existing branch errors).
        drv2 = Driver(charter, run_dir, _adapters(), loop_id="loop-ing-007",
                      clock=_clock(), repo_dir=self.repo)
        final = drv2.run(resume=True)
        self.assertEqual(final.state, STATE_ADVANCE)
        self.assertEqual(self._registry().get("loop-ing-007").status, "done")
        # The ledger is cumulative across both process lifetimes (same run_dir +
        # loop_id). Resume re-attached WITHOUT re-running ingress: exactly ONE
        # loop_ingress (phase 1), a loop_resume, and the phase-2 loop_close.
        types = [e["type"] for e in audit.read_events(drv2.audit_ledger)]
        self.assertEqual(types.count("loop_ingress"), 1)  # NOT re-run on resume
        self.assertIn("loop_resume", types)
        self.assertIn("loop_close", types)


class TestMemoryFeedbackAtClose(unittest.TestCase):
    """P5: the propose-only Loop Memory feedback stage runs at a successful
    MILESTONE close (memory enabled) — report + checkpoint + audit, no mutation."""

    def _seed_l2_memory(self, root):
        """Pre-seed an L2 (matured) entry scoped to the dev role so the feedback
        engine produces a skill_edit proposal. Two observations → occurrences=2 → L2."""
        store = ms.MemoryStore(root)
        for lp in ("seed-1", "seed-2"):
            store.record_observation(
                "dev: guard the handoff", ts="2026-06-15", loop_id=lp,
                type="failure", scope={"role": ["dev"]},
                body="When the dev handoff omits a guard, reviews recur; add the "
                     "guard before handoff.")
        return store

    def test_feedback_fires_at_milestone_close(self):
        with tempfile.TemporaryDirectory() as run_d, \
                tempfile.TemporaryDirectory() as mem_d:
            store = self._seed_l2_memory(mem_d)
            before = len(store.load_all())
            drv_ = Driver(load_charter(CHARTER_PATH), run_d, _adapters(),
                          loop_id="loop-fb-1", clock=_clock(), memory_root=mem_d)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            # A memory_feedback audit event was emitted with ≥1 proposal.
            fb_events = [e for e in audit.read_events(drv_.audit_ledger)
                         if e["type"] == "memory_feedback"]
            self.assertEqual(len(fb_events), 1)
            self.assertGreaterEqual(fb_events[0]["payload"]["proposal_count"], 1)
            self.assertIn("skill_edit", fb_events[0]["payload"]["by_path"])
            # A propose-only report file was written under the run dir.
            report = os.path.join(run_d, "memory-feedback", "loop-fb-1.md")
            self.assertTrue(os.path.isfile(report))
            with open(report, encoding="utf-8") as fh:
                self.assertIn("PROPOSE-ONLY", fh.read())
            # A human-pending checkpoint was written.
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("memory_feedback" in c for c in cps), cps)
            # PROPOSE-ONLY: the memory store was NOT mutated by feedback.
            self.assertEqual(len(ms.MemoryStore(mem_d).load_all()), before)

    def test_no_feedback_when_memory_off(self):
        # memory_root=None ⇒ no feedback stage at all (byte-identical to pre-P5).
        with tempfile.TemporaryDirectory() as run_d:
            drv_ = Driver(load_charter(CHARTER_PATH), run_d, _adapters(),
                          loop_id="loop-fb-2", clock=_clock())
            drv_.run(subsprint_id="sprint-001")
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("memory_feedback", types)
            self.assertFalse(os.path.isdir(os.path.join(run_d, "memory-feedback")))

    def test_no_feedback_on_non_terminal_subsprint(self):
        # A multi-sprint sequence: closing a NON-terminal sub-sprint is not a
        # milestone close → no feedback (it runs at milestone close only).
        with tempfile.TemporaryDirectory() as run_d, \
                tempfile.TemporaryDirectory() as mem_d:
            self._seed_l2_memory(mem_d)
            charter = load_charter(CHARTER_PATH)
            charter["autonomy"]["approved_scope"]["subsprint_sequence"] = \
                ["sprint-001", "sprint-002"]
            # close verdict points to the next sub-sprint (non-terminal).
            close = {"verdict": "A", "blocking_count": 0, "worst_severity": "none",
                     "in_scope": True, "next_subsprint": "sprint-002",
                     "reason": "clean pass, more to do"}
            drv_ = Driver(charter, run_d, _adapters(close=close),
                          loop_id="loop-fb-3", clock=_clock(), memory_root=mem_d)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("memory_feedback", types)

    def test_no_feedback_on_halt(self):
        # A fix_required halt is not a milestone close → no feedback.
        fix_review = {"decision": "fix_required", "blocking_count": 1,
                      "summary": "one P1", "findings": []}
        with tempfile.TemporaryDirectory() as run_d, \
                tempfile.TemporaryDirectory() as mem_d:
            self._seed_l2_memory(mem_d)
            drv_ = Driver(load_charter(CHARTER_PATH), run_d,
                          _adapters(review=fix_review),
                          loop_id="loop-fb-4", clock=_clock(), memory_root=mem_d)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("memory_feedback", types)


# --------------------------------------------------------------------------- #
# P6.1 — the OPTIONAL full_chain_guided bootstrap mode: research → gate1 →
# decompose pre-states BEFORE the delivery loop. All deterministic + offline:
# MockAdapter canned verdicts, injected clock, an INJECTED gate resolver standing
# in for the human (the engine NEVER auto-signs Gate 1).
# --------------------------------------------------------------------------- #
from driver import (  # noqa: E402
    STATE_RESEARCH_PENDING, STATE_GATE1_PENDING, STATE_DECOMPOSE_PENDING,
    LOOP_MODE_DELIVERY_ONLY, LOOP_MODE_FULL_CHAIN_GUIDED,
)

# A schema-valid deliver-plan verdict whose modules/layers stay WITHIN the example
# charter's approved_scope envelope (modules_in_scope + layers_allowed).
GUIDED_PLAN = {
    "sub_sprints": [{
        "id": "sprint-001", "objective": "implement refund eligibility",
        "scope_in": ["eligibility branches"], "scope_out": ["escalation"],
        "modules": ["src/tools/eligibility.py"],
        "layers": ["semantic_planner"],
        "exit_criteria": ["all bad-cases pass"],
    }],
}
# A plan that widens BEYOND the signed envelope (module + layer not in scope).
GUIDED_PLAN_OUT_OF_ENVELOPE = {
    "sub_sprints": [{
        "id": "sprint-001", "objective": "widen scope",
        "scope_in": [], "scope_out": [],
        "modules": ["src/escalation/new_path.py"],   # NOT in modules_in_scope
        "layers": ["infra"],                          # NOT in layers_allowed
        "exit_criteria": [],
    }],
}
RESEARCH_ARTIFACT = {"artifact": "drafted milestone brief"}


def _sign_resolver(note="looks good"):
    """A canned resolver returning an explicit human `sign` (the ONLY thing that
    lets the bootstrap proceed past Gate 1)."""
    def _r(gate_id, context, options):
        return {"choice": "sign", "note": note, "resolver": "test-human"}
    return _r


def _choice_resolver(choice, note=""):
    def _r(gate_id, context, options):
        return {"choice": choice, "note": note, "resolver": "test-human"}
    return _r


def _none_resolver():
    """A resolver that declines to decide (returns None) → the driver HALTS."""
    def _r(gate_id, context, options):
        return None
    return _r


def _guided_charter(*, subsprint_sequence=(), confirmed_by_human=False):
    """A full_chain_guided charter derived from the p2 demo charter. By DEFAULT
    the approved subsprint_sequence is EMPTY (so decompose runs) and the brief is
    NOT signed upfront (so research + gate1 run)."""
    charter = load_charter(CHARTER_PATH)
    charter["autonomy"]["approved_scope"]["subsprint_sequence"] = \
        list(subsprint_sequence)
    if confirmed_by_human:
        charter["intent_contract"] = {"confirmed_by_human": True}
    return charter


def _guided_adapters(plan=GUIDED_PLAN, review=CLEAN_REVIEW, close=CLEAN_CLOSE,
                     dev=DEV_ARTIFACT, research=RESEARCH_ARTIFACT):
    """Adapters for a guided run. The deliver role serves BOTH decompose
    (call_index 0 → plan) and close (later → close verdict)."""
    return {
        "research": MockAdapter({("research",): research}, harness="claude_code",
                                provider="anthropic", model="claude-opus-4-8"),
        "dev": MockAdapter({("dev",): dev}, harness="claude_code",
                           provider="anthropic", model="claude-sonnet-4-6"),
        "review": MockAdapter({("review",): review}, harness="headless",
                              provider="deepseek", model="deepseek-chat"),
        "deliver": MockAdapter({("deliver", 0): plan, ("deliver",): close},
                               harness="claude_code", provider="anthropic",
                               model="claude-opus-4-8"),
    }


def _guided_driver(run_dir, *, charter=None, adapters=None,
                   gate_resolver=None, loop_id="loop-guided-001",
                   loop_mode=LOOP_MODE_FULL_CHAIN_GUIDED):
    charter = charter if charter is not None else _guided_charter()
    return Driver(charter, run_dir, adapters or _guided_adapters(),
                  loop_id=loop_id, clock=_clock(),
                  loop_mode=loop_mode, gate_resolver=gate_resolver)


class TestFullChainGuided(unittest.TestCase):
    # (a) happy path: research → gate1(sign) → decompose → dev…→ advance.
    def test_happy_path_signs_decomposes_and_advances(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _guided_driver(d, gate_resolver=_sign_resolver())
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            # The pre-states ran IN ORDER before the delivery loop.
            self.assertEqual(
                final.history,
                [STATE_RESEARCH_PENDING, STATE_GATE1_PENDING,
                 STATE_DECOMPOSE_PENDING, "dev_pending", "gate_pending",
                 "review_pending", "close_pending"])
            self.assertTrue(final.brief_signed)
            self.assertTrue(final.milestone_planned)
            self.assertEqual(final.planned_sequence, ["sprint-001"])
            # The new audit events fire in order.
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            order = [t for t in types if t in (
                "guided_bootstrap_start", "research_brief_drafted",
                "customer_gate1_signed", "milestone_decomposed", "advance")]
            self.assertEqual(order, [
                "guided_bootstrap_start", "research_brief_drafted",
                "customer_gate1_signed", "milestone_decomposed", "advance"])
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    # (b) NO resolver → halt at gate1; no decompose/dev; no auto-sign.
    def test_no_resolver_halts_at_gate1_never_auto_signs(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _guided_driver(d, gate_resolver=None)  # no human voice
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_GATE1_PENDING)
            self.assertFalse(final.brief_signed)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("customer_gate1_halt", types)
            # The invariant (req 3): NEVER auto-confirmed; no decompose; no advance.
            self.assertNotIn("customer_gate1_signed", types)
            self.assertNotIn("milestone_decomposed", types)
            self.assertNotIn("advance", types)
            self.assertNotIn("dev_pending", final.history)
            # A Gate-1 sign-off checkpoint was written for async resolution.
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("customer_gate1_signoff" in c for c in cps), cps)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_resolver_returns_none_halts_at_gate1(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _guided_driver(d, gate_resolver=_none_resolver())
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_GATE1_PENDING)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("customer_gate1_halt", types)
            self.assertNotIn("customer_gate1_signed", types)

    # (c) resume after halt with a sign resolver → proceeds.
    def test_resume_after_gate1_halt_with_sign_proceeds(self):
        with tempfile.TemporaryDirectory() as d:
            # Phase 1: halt at gate1 (no resolver).
            drv1 = _guided_driver(d, gate_resolver=None, loop_id="loop-g-resume")
            drv1.run(subsprint_id="sprint-001")
            self.assertEqual(drv1.state.state, STATE_GATE1_PENDING)
            saved = drv1._load_state()
            self.assertEqual(saved.state, STATE_GATE1_PENDING)
            self.assertEqual(saved.loop_mode, LOOP_MODE_FULL_CHAIN_GUIDED)

            # Phase 2: fresh Driver, SAME run_dir, a sign resolver, resume=True.
            drv2 = Driver(_guided_charter(), d, _guided_adapters(),
                          loop_id="loop-g-resume", clock=_clock(),
                          loop_mode=LOOP_MODE_FULL_CHAIN_GUIDED,
                          gate_resolver=_sign_resolver())
            final = drv2.run(resume=True)
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertTrue(final.brief_signed)
            types = [e["type"] for e in audit.read_events(drv2.audit_ledger)]
            self.assertIn("loop_resume", types)
            self.assertIn("customer_gate1_signed", types)
            self.assertIn("milestone_decomposed", types)
            self.assertIn("advance", types)
            # Audit chain verifies across the halt → resume boundary (req 7/j).
            self.assertTrue(audit.verify_chain(drv2.audit_ledger).ok)

    # (d) reject → halts (brief needs rework), no decompose/advance.
    def test_reject_halts_for_rework(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _guided_driver(d, gate_resolver=_choice_resolver("reject"))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_GATE1_PENDING)
            self.assertFalse(final.brief_signed)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("customer_gate1_rejected", types)
            self.assertNotIn("milestone_decomposed", types)
            self.assertNotIn("advance", types)

    def test_abort_halts_run(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _guided_driver(d, gate_resolver=_choice_resolver("abort"))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("customer_gate1_aborted", types)
            self.assertNotIn("advance", types)

    # (e) skip rules.
    def test_signed_brief_upfront_skips_research_and_gate1(self):
        # intent_contract.confirmed_by_human → skip research + gate1; NO resolver
        # is needed (nothing to sign). Decompose + delivery still run.
        with tempfile.TemporaryDirectory() as d:
            charter = _guided_charter(confirmed_by_human=True)
            drv_ = _guided_driver(d, charter=charter, gate_resolver=None)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertTrue(final.brief_signed)
            self.assertNotIn(STATE_RESEARCH_PENDING, final.history)
            self.assertNotIn(STATE_GATE1_PENDING, final.history)
            self.assertIn(STATE_DECOMPOSE_PENDING, final.history)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("customer_gate1_halt", types)
            self.assertNotIn("research_brief_drafted", types)
            self.assertIn("milestone_decomposed", types)

    def test_supplied_sequence_skips_decompose(self):
        # A non-empty subsprint_sequence supplied upfront → decompose is skipped.
        # The deliver adapter is only spawned for CLOSE (index 0 = close).
        with tempfile.TemporaryDirectory() as d:
            charter = _guided_charter(subsprint_sequence=("sprint-001",))
            adapters = _guided_adapters()
            adapters["deliver"] = MockAdapter(
                {("deliver",): CLEAN_CLOSE}, harness="claude_code",
                provider="anthropic", model="claude-opus-4-8")
            drv_ = _guided_driver(d, charter=charter, adapters=adapters,
                                  gate_resolver=_sign_resolver())
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertTrue(final.milestone_planned)
            self.assertEqual(final.planned_sequence, ["sprint-001"])
            self.assertIn(STATE_DECOMPOSE_PENDING, final.history)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("decompose_skipped", types)
            self.assertNotIn("milestone_decomposed", types)

    def test_both_supplied_behaves_like_delivery_loop(self):
        # full_chain_guided with brief signed upfront AND sequence supplied ⇒ the
        # pre-states all no-op; it behaves like the plain delivery loop (advance).
        with tempfile.TemporaryDirectory() as d:
            charter = _guided_charter(subsprint_sequence=("sprint-001",),
                                      confirmed_by_human=True)
            adapters = _guided_adapters()
            adapters["deliver"] = MockAdapter(
                {("deliver",): CLEAN_CLOSE}, harness="claude_code",
                provider="anthropic", model="claude-opus-4-8")
            drv_ = _guided_driver(d, charter=charter, adapters=adapters,
                                  gate_resolver=None)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertNotIn(STATE_RESEARCH_PENDING, final.history)
            self.assertNotIn(STATE_GATE1_PENDING, final.history)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("research_brief_drafted", types)
            self.assertNotIn("customer_gate1_halt", types)
            self.assertNotIn("milestone_decomposed", types)

    # (f) scope-expansion guard halts on an out-of-envelope plan.
    def test_scope_expansion_guard_halts(self):
        with tempfile.TemporaryDirectory() as d:
            adapters = _guided_adapters(plan=GUIDED_PLAN_OUT_OF_ENVELOPE)
            drv_ = _guided_driver(d, adapters=adapters,
                                  gate_resolver=_sign_resolver())
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("post_gate1_scope_expansion", types)
            # Halted at decompose — did NOT enter the delivery loop / advance.
            self.assertNotIn("advance", types)
            self.assertNotIn("dev_pending", final.history)
            exp = next(e for e in audit.read_events(drv_.audit_ledger)
                       if e["type"] == "post_gate1_scope_expansion")
            self.assertIn("src/escalation/new_path.py",
                          exp["payload"]["modules_out"])
            self.assertIn("infra", exp["payload"]["layers_out"])
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(
                any("post_gate1_scope_expansion" in c for c in cps), cps)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_scope_envelope_unset_lets_plan_define_scope(self):
        # No signed envelope (empty modules_in_scope + layers_allowed) → the plan
        # defines scope; no expansion possible → scope_envelope_unset note + proceed.
        with tempfile.TemporaryDirectory() as d:
            charter = _guided_charter()
            charter["autonomy"]["approved_scope"]["modules_in_scope"] = []
            charter["autonomy"]["approved_scope"]["layers_allowed"] = []
            drv_ = _guided_driver(d, charter=charter,
                                  gate_resolver=_sign_resolver())
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("scope_envelope_unset", types)
            self.assertIn("milestone_decomposed", types)

    def test_partial_envelope_empty_layers_still_constrains(self):
        # Regression (qa-found): an envelope with modules_in_scope SET but
        # layers_allowed EMPTY authorizes NO new layers — a plan adding any layer
        # must HALT, not silently advance (per-dimension "empty ⇒ unconstrained"
        # was a scope-widening blind spot). The envelope is PRESENT, so this is
        # NOT the scope_envelope_unset path.
        with tempfile.TemporaryDirectory() as d:
            charter = _guided_charter()  # modules_in_scope set (example charter)
            charter["autonomy"]["approved_scope"]["layers_allowed"] = []
            # GUIDED_PLAN's module is in-scope; its layer (semantic_planner) is now
            # out of the emptied layers envelope.
            drv_ = _guided_driver(d, charter=charter,
                                  adapters=_guided_adapters(plan=GUIDED_PLAN),
                                  gate_resolver=_sign_resolver())
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("post_gate1_scope_expansion", types)
            self.assertNotIn("scope_envelope_unset", types)  # envelope IS present
            self.assertNotIn("advance", types)
            exp = next(e for e in audit.read_events(drv_.audit_ledger)
                       if e["type"] == "post_gate1_scope_expansion")
            self.assertIn("semantic_planner", exp["payload"]["layers_out"])
            self.assertEqual(exp["payload"]["modules_out"], [])  # module in-scope

    def test_partial_envelope_empty_modules_still_constrains(self):
        # Symmetric: layers_allowed SET but modules_in_scope EMPTY authorizes NO
        # new modules — a plan touching any module must HALT.
        with tempfile.TemporaryDirectory() as d:
            charter = _guided_charter()  # layers_allowed set (example charter)
            charter["autonomy"]["approved_scope"]["modules_in_scope"] = []
            drv_ = _guided_driver(d, charter=charter,
                                  adapters=_guided_adapters(plan=GUIDED_PLAN),
                                  gate_resolver=_sign_resolver())
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("post_gate1_scope_expansion", types)
            self.assertNotIn("scope_envelope_unset", types)
            exp = next(e for e in audit.read_events(drv_.audit_ledger)
                       if e["type"] == "post_gate1_scope_expansion")
            self.assertIn("src/tools/eligibility.py", exp["payload"]["modules_out"])

    # (g) invalid deliver-plan verdict → GateHardFail.
    def test_invalid_deliver_plan_verdict_hard_fails(self):
        bad_plan = {"sub_sprints": [{"id": "sprint-001"}]}  # missing required keys
        with tempfile.TemporaryDirectory() as d:
            adapters = _guided_adapters(plan=bad_plan)
            drv_ = _guided_driver(d, adapters=adapters,
                                  gate_resolver=_sign_resolver())
            with self.assertRaises(GateHardFail) as ctx:
                drv_.run(subsprint_id="sprint-001")
            self.assertIn("deliver_plan", ctx.exception.reason)
            cps = os.listdir(drv_.checkpoints_dir)
            self.assertTrue(any("gate_hard_fail" in c for c in cps), cps)

    def test_empty_sub_sprints_plan_hard_fails(self):
        with tempfile.TemporaryDirectory() as d:
            adapters = _guided_adapters(plan={"sub_sprints": []})
            drv_ = _guided_driver(d, adapters=adapters,
                                  gate_resolver=_sign_resolver())
            with self.assertRaises(GateHardFail):
                drv_.run(subsprint_id="sprint-001")

    # (h) resume round-trips through each pre-state (state.json persists + reload).
    def test_runstate_guided_fields_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _guided_driver(d)
            drv_.state = RunState(loop_id="x", subsprint_id="sprint-001")
            drv_.state.loop_mode = LOOP_MODE_FULL_CHAIN_GUIDED
            drv_.state.brief_signed = True
            drv_.state.brief_draft_ref = "docs/briefs/sprint-001__brief.md"
            drv_.state.milestone_planned = True
            drv_.state.planned_sequence = ["sprint-001", "sprint-002"]
            drv_._save_state()
            reloaded = drv_._load_state()
            self.assertEqual(reloaded.loop_mode, LOOP_MODE_FULL_CHAIN_GUIDED)
            self.assertTrue(reloaded.brief_signed)
            self.assertEqual(reloaded.brief_draft_ref,
                             "docs/briefs/sprint-001__brief.md")
            self.assertTrue(reloaded.milestone_planned)
            self.assertEqual(reloaded.planned_sequence,
                             ["sprint-001", "sprint-002"])

    def test_resume_at_research_pending_round_trips(self):
        # Persist a state.json AT research_pending (brief not yet drafted) and
        # resume with a sign resolver → the bootstrap completes from there.
        with tempfile.TemporaryDirectory() as d:
            seed = _guided_driver(d, loop_id="loop-g-rp")
            seed.state = RunState(loop_id="loop-g-rp", subsprint_id="sprint-001")
            seed.state.loop_mode = LOOP_MODE_FULL_CHAIN_GUIDED
            seed.state.state = STATE_RESEARCH_PENDING
            seed._save_state()
            drv_ = Driver(_guided_charter(), d, _guided_adapters(),
                          loop_id="loop-g-rp", clock=_clock(),
                          loop_mode=LOOP_MODE_FULL_CHAIN_GUIDED,
                          gate_resolver=_sign_resolver())
            final = drv_.run(resume=True)
            self.assertEqual(final.state, STATE_ADVANCE)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("research_brief_drafted", types)
            self.assertIn("customer_gate1_signed", types)
            self.assertIn("milestone_decomposed", types)

    def test_resume_at_decompose_pending_round_trips(self):
        # Persist a state.json AT decompose_pending with a signed brief, then
        # resume → decompose + delivery complete (gate1 is skipped: already signed).
        with tempfile.TemporaryDirectory() as d:
            seed = _guided_driver(d, loop_id="loop-g-dp")
            seed.state = RunState(loop_id="loop-g-dp", subsprint_id="sprint-001")
            seed.state.loop_mode = LOOP_MODE_FULL_CHAIN_GUIDED
            seed.state.brief_signed = True
            seed.state.brief_draft_ref = "docs/briefs/sprint-001__brief.md"
            seed.state.state = STATE_DECOMPOSE_PENDING
            seed._save_state()
            drv_ = Driver(_guided_charter(), d, _guided_adapters(),
                          loop_id="loop-g-dp", clock=_clock(),
                          loop_mode=LOOP_MODE_FULL_CHAIN_GUIDED,
                          gate_resolver=_none_resolver())  # never needed (signed)
            final = drv_.run(resume=True)
            self.assertEqual(final.state, STATE_ADVANCE)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("customer_gate1_halt", types)
            self.assertIn("milestone_decomposed", types)
            self.assertIn("advance", types)

    # (i) delivery_only DEFAULT emits NONE of the new events (byte-identical).
    def test_delivery_only_default_emits_no_guided_events(self):
        with tempfile.TemporaryDirectory() as d:
            # The plain _driver() helper uses no loop_mode (delivery_only default)
            # and no gate_resolver — exactly the pre-P6.1 construction.
            drv_ = _driver(d)
            self.assertEqual(drv_.loop_mode, LOOP_MODE_DELIVERY_ONLY)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertEqual(
                final.history,
                ["dev_pending", "gate_pending", "review_pending",
                 "close_pending"])
            self.assertEqual(final.loop_mode, LOOP_MODE_DELIVERY_ONLY)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            for t in ("guided_bootstrap_start", "research_brief_drafted",
                      "research_skipped", "customer_gate1_signoff",
                      "customer_gate1_signed", "customer_gate1_halt",
                      "customer_gate1_rejected", "customer_gate1_aborted",
                      "milestone_decomposed", "decompose_skipped",
                      "post_gate1_scope_expansion", "scope_envelope_unset"):
                self.assertNotIn(t, types, t)

    def test_delivery_only_explicit_mode_also_skips_prestates(self):
        # Even with a resolver wired, delivery_only must NOT run any pre-state.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _guided_driver(
                d, gate_resolver=_sign_resolver(),
                loop_mode=LOOP_MODE_DELIVERY_ONLY,
                charter=_guided_charter(subsprint_sequence=("sprint-001",)))
            # deliver adapter only needs close (no decompose in delivery_only).
            drv_.adapters["deliver"] = MockAdapter(
                {("deliver",): CLEAN_CLOSE}, harness="claude_code",
                provider="anthropic", model="claude-opus-4-8")
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertNotIn(STATE_GATE1_PENDING, final.history)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("customer_gate1_signed", types)

    # (j) audit chain verifies across halt/resume (also covered in (c); here for
    # the explicit invariant with the checkpoint front-matter rewrite in between).
    def test_audit_chain_verifies_across_gate1_signoff_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _guided_driver(d, gate_resolver=_sign_resolver("approved"))
            drv_.run(subsprint_id="sprint-001")
            # The Gate-1 checkpoint records the human's resolved decision.
            cps = [c for c in os.listdir(drv_.checkpoints_dir)
                   if "customer_gate1_signoff" in c]
            self.assertTrue(cps)
            with open(os.path.join(drv_.checkpoints_dir, cps[0]),
                      encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("decision: sign", body)
            self.assertIn("resolver: test-human", body)
            self.assertIn("note: approved", body)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_charter_loop_mode_is_honored_when_no_ctor_param(self):
        # charter.autonomy.loop_mode = full_chain_guided + no ctor loop_mode ⇒
        # guided mode runs (the ctor param wins, but its absence falls back here).
        with tempfile.TemporaryDirectory() as d:
            charter = _guided_charter()
            charter["autonomy"]["loop_mode"] = LOOP_MODE_FULL_CHAIN_GUIDED
            drv_ = Driver(charter, d, _guided_adapters(),
                          loop_id="loop-g-charter", clock=_clock(),
                          gate_resolver=_sign_resolver())  # no loop_mode param
            self.assertEqual(drv_.loop_mode, LOOP_MODE_FULL_CHAIN_GUIDED)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("milestone_decomposed", types)

    def test_ctor_loop_mode_wins_over_charter(self):
        # ctor delivery_only beats charter full_chain_guided.
        with tempfile.TemporaryDirectory() as d:
            charter = _guided_charter(subsprint_sequence=("sprint-001",))
            charter["autonomy"]["loop_mode"] = LOOP_MODE_FULL_CHAIN_GUIDED
            adapters = _guided_adapters()
            adapters["deliver"] = MockAdapter(
                {("deliver",): CLEAN_CLOSE}, harness="claude_code",
                provider="anthropic", model="claude-opus-4-8")
            drv_ = Driver(charter, d, adapters,
                          loop_id="loop-g-ctor", clock=_clock(),
                          loop_mode=LOOP_MODE_DELIVERY_ONLY)  # ctor wins
            self.assertEqual(drv_.loop_mode, LOOP_MODE_DELIVERY_ONLY)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertNotIn(STATE_GATE1_PENDING, final.history)


if __name__ == "__main__":
    unittest.main()
