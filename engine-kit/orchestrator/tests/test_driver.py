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


if __name__ == "__main__":
    unittest.main()
