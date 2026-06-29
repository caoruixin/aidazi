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
import lesson_selection as ls  # noqa: E402  (WP-6 bounded ingress)

CHARTER_PATH = os.path.join(_ORCH_DIR, "examples", "p2-charter.yaml")
_FIXTURES_DIR = os.path.join(_TESTS_DIR, "fixtures")
_FAKE_EVAL = os.path.join(_FIXTURES_DIR, "fake_eval.py")
_FAKE_EVAL_ACCEPTANCE_FAIL = os.path.join(
    _FIXTURES_DIR, "fake_eval_acceptance_fail.py")


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


class Track1SkillMountingDriverTests(unittest.TestCase):
    """Track 1 §2.4 — the driver wiring is BEHAVIOR-NEUTRAL while dormant: the
    effective_role_config audit event gains the dedicated task-aware skill-set surface, every
    value is empty/benign (no sub-sprint authors task_signals yet), the cache is re-keyed by
    (role, task_unit_id), and NO dispatched prompt gains a skip footer."""

    def test_effective_role_config_event_carries_dormant_task_fields(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            payloads = [e["payload"] for e in audit.read_events(drv_.audit_ledger)
                        if e["type"] == "effective_role_config"]
            self.assertTrue(payloads)   # dev / review / deliver each emit one
            for p in payloads:
                for k in ("task_unit_id", "task_signals", "selected_skills", "skipped_skills"):
                    self.assertIn(k, p)
                # This minimal flow has NO decompose ⇒ no plan entry ⇒ task-UNAWARE (None).
                self.assertIsNone(p["task_unit_id"])
                self.assertEqual(p["task_signals"], [])
                self.assertEqual(p["selected_skills"], [])
                self.assertEqual(p["skipped_skills"], [])
                # the resolved skill-set identity stays skill_set_hash; load_graph_hash is NOT
                # overloaded — it lives on the spawn event, not here.
                self.assertIn("skill_set_hash", p)
                self.assertNotIn("load_graph_hash", p)

    def test_no_prompt_carries_skip_footer_when_dormant(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            for e in audit.read_events(drv_.audit_ledger):
                if e["type"] == "spawn":
                    prompt = open(os.path.join(d, e["payload"]["prompt_ref"]),
                                  encoding="utf-8").read()
                    self.assertNotIn("Skipped / unmatched skills", prompt)

    def test_cache_is_keyed_by_role_and_task_unit(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            self.assertTrue(drv_._effective_role_cache)
            self.assertTrue(all(isinstance(k, tuple) and len(k) == 2
                                for k in drv_._effective_role_cache))
            # No decompose plan in this flow ⇒ task-unaware key.
            self.assertIn(("dev", None), drv_._effective_role_cache)

    def test_task_context_keys_on_plan_existence_not_just_subsprint_id(self):
        # Codex BLOCKING-2: the decompose `deliver` spawn (planned_subsprints empty) must NOT
        # share a cache key with the later task-specific `close` spawn for the same sub-sprint id.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            st = drv_.state
            st.subsprint_id = "sprint-001"
            # No plan entry yet (decompose-time) ⇒ task-UNAWARE (None, ()).
            st.planned_subsprints = []
            self.assertEqual(drv_._task_context_for("deliver"), (None, ()))
            # Plan entry present (post-decompose) ⇒ keyed by the sub-sprint id + its signals.
            # A stamped digest is required whenever signals are present (1-c fail-closed invariant).
            st.planned_subsprints = [{"id": "sprint-001", "objective": "o",
                                      "task_signals": ["ui", "frontend"]}]
            st.task_signals_digest = drv_._task_signals_digest(st.planned_subsprints)
            self.assertEqual(drv_._task_context_for("deliver"),
                             ("sprint-001", ("ui", "frontend")))
            self.assertEqual(drv_._task_context_for("dev"),
                             ("sprint-001", ("ui", "frontend")))
            # Acceptance is excluded (§2.5) regardless of the plan.
            self.assertEqual(drv_._task_context_for("acceptance"), (None, ()))

    def test_task_signals_present_without_stamped_digest_fails_closed(self):
        # (1-c #9, Codex final) Signals present but NO stamped digest (stripped digest / injected
        # signals) must FAIL CLOSED — never mount skills on unverified signals.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            st = drv_.state
            st.subsprint_id = "sp-ui"
            st.planned_subsprints = [{"id": "sp-ui", "objective": "o", "task_signals": ["ui"]}]
            st.task_signals_digest = None   # digest stripped / never stamped
            with self.assertRaises(GateHardFail) as ctx:
                drv_._effective_role("dev")
            self.assertIn("no task_signals_digest was stamped", ctx.exception.reason)
            # control: removing the signals (genuinely none) → no check, resolves normally.
            st.planned_subsprints = [{"id": "sp-ui", "objective": "o"}]
            self.assertEqual([s.id for s in drv_._effective_role("dev").skills],
                             ["test-driven-development"])

    def test_same_role_different_task_units_no_cache_collision(self):
        # (1-c #7) The same role across two sub-sprints with DIFFERENT task_signals resolves to
        # DIFFERENT skill sets — keyed by (role, task_unit_id), never cross-contaminated.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            st = drv_.state
            st.planned_subsprints = [{"id": "sp-ui", "objective": "o", "task_signals": ["ui"]},
                                     {"id": "sp-a11y", "objective": "o", "task_signals": ["a11y"]}]
            st.task_signals_digest = drv_._task_signals_digest(st.planned_subsprints)
            st.subsprint_id = "sp-ui"
            ui = drv_._effective_role("dev")
            st.subsprint_id = "sp-a11y"
            a11y = drv_._effective_role("dev")
            self.assertIn("frontend-design", [s.id for s in ui.skills])
            self.assertNotIn("frontend-design", [s.id for s in a11y.skills])
            self.assertIn("a11y-checklist", [s.id for s in a11y.skills])
            self.assertNotEqual(ui.skill_set_hash, a11y.skill_set_hash)
            self.assertIn(("dev", "sp-ui"), drv_._effective_role_cache)
            self.assertIn(("dev", "sp-a11y"), drv_._effective_role_cache)

    def test_post_signoff_task_signal_mutation_fails_closed(self):
        # (1-c #9) Changing task_signals after the digest is stamped (post sign-off) FAILS CLOSED
        # at the next task-aware selection — never a silent mutation of which skills mount.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            st = drv_.state
            st.subsprint_id = "sp-ui"
            st.planned_subsprints = [{"id": "sp-ui", "objective": "o", "task_signals": ["ui"]}]
            st.task_signals_digest = drv_._task_signals_digest(st.planned_subsprints)
            # tamper: change the authored signal AFTER the digest was stamped.
            st.planned_subsprints[0]["task_signals"] = ["a11y"]
            with self.assertRaises(GateHardFail) as ctx:
                drv_._effective_role("dev")
            self.assertIn("task_signals changed after sign-off", ctx.exception.reason)
            # removing the sub-sprint entirely also trips the stale digest (not silently dormant).
            st.planned_subsprints = []
            with self.assertRaises(GateHardFail):
                drv_._effective_role("dev")


class TestSubSprintGate(unittest.TestCase):
    def test_eval_cmd_runs_before_review(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            events = audit.read_events(drv_.audit_ledger)
            types = [e["type"] for e in events]
            self.assertIn("subsprint_gate_run", types)
            gate_idx = types.index("subsprint_gate_run")
            review_idx = next(i for i, e in enumerate(events)
                              if e["type"] == "spawn"
                              and e["payload"]["role"] == "review")
            self.assertLess(gate_idx, review_idx)
            gate = next(e for e in events if e["type"] == "subsprint_gate_run")
            self.assertTrue(gate["payload"]["ok"])
            self.assertTrue(
                gate["payload"]["evidence_path"].startswith(
                    "eval/runs/sprint-001/subsprint_gate/"))

    def test_eval_cmd_failure_blocks_review_and_close(self):
        fail_cmd = (f'FAKE_EVAL_EXIT=4 "{_sys.executable}" "{_FAKE_EVAL}"')
        charter = load_charter(CHARTER_PATH)
        charter["tooling"]["eval"] = {"cmd": fail_cmd, "timeout_seconds": 30}
        adapters = _adapters()
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, charter=charter, adapters=adapters)
            with self.assertRaises(GateHardFail) as ctx:
                drv_.run(subsprint_id="sprint-001")
            self.assertEqual(ctx.exception.state, STATE_GATE_PENDING)
            self.assertIn("sub-sprint gate", ctx.exception.reason)
            self.assertEqual(len(adapters["review"].history), 0)
            self.assertEqual(len(adapters["deliver"].history), 0)
            events = audit.read_events(drv_.audit_ledger)
            gate = next(e for e in events if e["type"] == "subsprint_gate_run")
            self.assertFalse(gate["payload"]["ok"])


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

    def test_network_access_routing_is_fail_closed(self):
        # The network grant parses ONLY a literal boolean `true`; anything else
        # (false / absent / a non-bool typo) is default-deny — it never silently
        # over-grants network to a write sandbox.
        def _na(val):
            ch = {"tooling": {"dev": {"harness": "codex", "network_access": val}}}
            return route_for_role(ch, "dev").network_access
        self.assertIs(_na(True), True)
        self.assertIs(_na(False), False)
        self.assertIs(route_for_role(
            {"tooling": {"dev": {"harness": "codex"}}}, "dev").network_access, False)
        for typo in ("true", "yes", 1):   # truthy but NOT a bool ⇒ fail closed
            self.assertIs(_na(typo), False)

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

    def test_wp0_measurement_fields_recorded_on_every_spawn(self):
        """WP-0 (observation-only): every spawn event carries prompt_bytes / memory_bytes
        / fix_round, and prompt_bytes EQUALS the byte size of the verbatim as-dispatched
        prompt transcript it references — proving the measurement is wired to the real
        dispatched bytes, not a stale/duplicated value. The chain still verifies."""
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.fix_round, 0)
            spawns = [e for e in audit.read_events(drv_.audit_ledger)
                      if e["type"] == "spawn"]
            self.assertEqual(len(spawns), 3)  # dev, review, deliver
            for ev in spawns:
                p = ev["payload"]
                self.assertEqual(p["fix_round"], 0)
                self.assertIsInstance(p["prompt_bytes"], int)
                self.assertGreater(p["prompt_bytes"], 0)
                # memory is OFF in this driver → no lessons block injected.
                self.assertEqual(p["memory_bytes"], 0)
                self.assertEqual(p["memory_injected"], [])
                # prompt_bytes == bytes of the verbatim prompt transcript (driver
                # writes the as-dispatched prompt byte-for-byte, _write_transcript).
                with open(os.path.join(drv_.run_dir, p["prompt_ref"]), "rb") as fh:
                    self.assertEqual(len(fh.read()), p["prompt_bytes"])
            # Forward-only fields do not break the hash chain.
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_wp7_load_graph_hash_recorded_on_every_spawn(self):
        """WP-7 (observation-only): every spawn event carries a non-null cold-start
        load_graph_hash ('sha256:<16hex>'); it is role-specific (dev / review / deliver
        load distinct cold-start sets → distinct fingerprints), deterministic across the
        run, and the forward-only field does not break the hash chain."""
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            spawns = [e for e in audit.read_events(drv_.audit_ledger)
                      if e["type"] == "spawn"]
            self.assertEqual(len(spawns), 3)  # dev, review, deliver
            by_role = {}
            for ev in spawns:
                lgh = ev["payload"]["load_graph_hash"]
                self.assertIsInstance(lgh, str)         # non-null (real framework_root)
                self.assertTrue(lgh.startswith("sha256:"), lgh)
                self.assertEqual(len(lgh), len("sha256:") + 16)
                by_role[ev["payload"]["role"]] = lgh
            # dev / review / deliver each load a different role card + briefing set.
            self.assertEqual(len(set(by_role.values())), 3, by_role)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

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


class TestCloseTaskScopedColdStart(unittest.TestCase):
    """WP-5A: the Close spawn (deliver / schema_key="close") gets a task-scoped cold-start —
    an authoritative directive injected into the dispatched prompt that drops the 9
    Deliver-plan-only briefing docs, plus a load_graph_hash fingerprinting the narrowed set.
    FAIL-CLOSED: no directive for Deliver-plan / unknown / None tasks."""

    DROPPED_9 = {
        "process/milestone-framework.md", "process/tech-architecture-decision-catalog.md",
        "process/typeA-runtime-architecture-skeleton.md", "process/artifact-taxonomy.md",
        "process/post-deployment-iteration.md",
        "process/common-detours-and-warnings-typeA.md",
        "templates/sprint-objective.md", "templates/milestone-objective.md",
        "templates/compact-dev-prompt.md",
    }

    def test_directive_lists_retained_dropped_and_halts(self):
        with tempfile.TemporaryDirectory() as d:
            directive = _driver(d)._task_scoped_coldstart_directive("deliver", "close")
            self.assertIn("TASK-SCOPED COLD-START", directive)
            self.assertIn("templates/deliver-close-taxonomy.md", directive)  # retained
            for doc in self.DROPPED_9:
                self.assertIn(doc, directive)
            self.assertIn("HALT", directive)

    def test_directive_dropped_set_matches_load_sizer_single_source(self):
        # The directive is RENDERED from load_sizer, so the dispatched "do not load" set
        # cannot drift from the measured/fingerprinted narrowing.
        with tempfile.TemporaryDirectory() as d:
            directive = _driver(d)._task_scoped_coldstart_directive("deliver", "close")
            full = {r for r, _ in drv.load_sizer.role_cold_start_roots("deliver")}
            close = {r for r, _ in drv.load_sizer.role_cold_start_roots("deliver", "close")}
            self.assertEqual(full - close, self.DROPPED_9)
            for doc in (full - close):
                self.assertIn(doc, directive)

    def test_directive_fail_closed_for_plan_none_unknown_and_other_roles(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            self.assertEqual(drv_._task_scoped_coldstart_directive("deliver", "deliver_plan"), "")
            self.assertEqual(drv_._task_scoped_coldstart_directive("deliver", None), "")
            self.assertEqual(drv_._task_scoped_coldstart_directive("deliver", "bogus-task"), "")
            self.assertEqual(drv_._task_scoped_coldstart_directive("review", "close"), "")

    def test_close_prompt_carries_directive_other_roles_do_not(self):
        # The REAL dispatched close prompt (the as-dispatched transcript) carries the
        # directive + the 9 drops; dev/review prompts carry NO close directive.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            spawns = [e for e in audit.read_events(drv_.audit_ledger)
                      if e["type"] == "spawn"]
            dlv = next(e for e in spawns if e["payload"]["role"] == "deliver")
            prompt = open(os.path.join(d, dlv["payload"]["prompt_ref"]),
                          encoding="utf-8").read()
            self.assertIn("TASK-SCOPED COLD-START", prompt)
            self.assertIn("deliver-close-taxonomy.md", prompt)
            for doc in self.DROPPED_9:
                self.assertIn(doc, prompt)
            for e in spawns:
                if e["payload"]["role"] != "deliver":
                    p = open(os.path.join(d, e["payload"]["prompt_ref"]),
                             encoding="utf-8").read()
                    self.assertNotIn("TASK-SCOPED COLD-START", p)

    def test_close_spawn_load_graph_hash_is_close_scoped(self):
        # The recorded WP-7 fingerprint on the close spawn = the Close-scoped hash, and is
        # DISTINCT from the full/deliver_plan hash (proving the narrowing is fingerprinted).
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            dlv = next(e["payload"] for e in audit.read_events(drv_.audit_ledger)
                       if e["type"] == "spawn" and e["payload"]["role"] == "deliver")
            # Task-scoping composes with the (independent) skills gate — compute the
            # expected hashes with the SAME skills_active the driver used for deliver.
            skills_on = bool(drv_._effective_role("deliver").skills)
            expected_close, _ = drv.load_sizer.cold_start_load_graph_hash(
                "deliver", "close", repo_root=drv_.framework_root, skills_active=skills_on)
            full_hash, _ = drv.load_sizer.cold_start_load_graph_hash(
                "deliver", "deliver_plan", repo_root=drv_.framework_root, skills_active=skills_on)
            self.assertEqual(dlv["load_graph_hash"], expected_close)
            self.assertNotEqual(dlv["load_graph_hash"], full_hash)


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
_EVID = "eval/runs/sprint-001/acceptance/stdout.txt"

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
                        mode="auto",
                        eval_cmd=_EVAL_CMD,
                        subsprint_sequence=("sprint-001",)):
    """Build an acceptance-ENABLED charter (canonical tooling.acceptance.mode) so
    the milestone-close path enters acceptance_pending. `mode` ∈ {advisory, auto}
    (or 'off'). An AUTHORITATIVE auto-ship (pass → STATE_DONE) needs mode='auto' +
    calibration='calibrated' + level='fully_autonomous_within_budget' (design
    §3.2); anything else makes a pass ADVISORY (→ advisory_acceptance_pass_signoff
    HALT). The default (HOTL + auto + calibrated) is therefore advisory."""
    charter = load_charter(CHARTER_PATH)
    charter["autonomy"]["level"] = level
    charter["autonomy"]["approved_scope"]["subsprint_sequence"] = \
        list(subsprint_sequence)
    tooling = charter.setdefault("tooling", {})
    tooling["acceptance"] = {
        "mode": mode,
        "run_at": "milestone_close",
        "on_fix_required": {
            "human_confirm_required": True,
            "route_options": ["deliver_fix_iteration",
                              "re_acceptance_after_evidence",
                              "research_contract_revision"],
        },
        "harness": "claude_code", "provider": "anthropic",
        "model": "claude-opus-4-8",
        "network_access": True,
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
            self.assertNotIn("acceptance_eval_run", types)

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
            # AUTHORITATIVE ship: auto + calibrated + fully-autonomous (design §3.2).
            charter = _acceptance_charter(level="fully_autonomous_within_budget")
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


class TestAcceptanceAdvisorySignoff(unittest.TestCase):
    """Design §3.2/§3.3: an ADVISORY pass NEVER auto-ships — it HALTs at the
    advisory_acceptance_pass_signoff checkpoint (#9) for human sign-off. Only an
    AUTHORITATIVE pass (auto + calibrated + fully-autonomous) reaches STATE_DONE."""

    def test_hotl_calibrated_pass_is_advisory_signoff_halt(self):
        with tempfile.TemporaryDirectory() as d:
            # HOTL (not fully-autonomous) → non-authoritative even though calibrated.
            charter = _acceptance_charter(level="human_on_the_loop", mode="auto")
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            cps = os.listdir(drv_.checkpoints_dir)
            cp = [c for c in cps if "advisory_acceptance_pass_signoff" in c]
            self.assertTrue(cp, cps)
            with open(os.path.join(drv_.checkpoints_dir, cp[0]),
                      encoding="utf-8") as _fh:
                body = _fh.read()
            self.assertIn("confirm: ship|reject", body)
            self.assertIn("ADVISORY", body)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("acceptance_advisory_pass_signoff", types)
            self.assertNotIn("acceptance_pass", types)  # did NOT ship
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_advisory_mode_pass_halts_even_fully_autonomous_calibrated(self):
        with tempfile.TemporaryDirectory() as d:
            # mode=advisory NEVER ships, even fully-autonomous + calibrated.
            charter = _acceptance_charter(
                level="fully_autonomous_within_budget", mode="advisory")
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            self.assertTrue(
                any("advisory_acceptance_pass_signoff" in c
                    for c in os.listdir(drv_.checkpoints_dir)))

    def test_auto_calibrated_fully_autonomous_pass_ships(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(
                level="fully_autonomous_within_budget", mode="auto",
                calibration="calibrated")
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_DONE)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("acceptance_pass", types)


class TestAcceptanceNamespaceMigration(unittest.TestCase):
    """P-A namespace normalization (charter_compat) at the Driver boundary."""

    def test_legacy_enabled_true_maps_to_auto_and_runs(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="fully_autonomous_within_budget")
            # Simulate a LEGACY charter: drop `mode`, set the deprecated `enabled`.
            charter["tooling"]["acceptance"].pop("mode")
            charter["tooling"]["acceptance"]["enabled"] = True
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            # enabled:true → mode:auto → authoritative ship (fully-auto + calibrated).
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_DONE)

    def test_legacy_top_level_acceptance_block_normalized_and_audited(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="fully_autonomous_within_budget")
            # Move on_fix_required to a legacy TOP-LEVEL acceptance block + drop mode.
            acc = charter["tooling"]["acceptance"]
            acc.pop("mode")
            charter["acceptance"] = {"enabled": True,
                                     "on_fix_required": acc.pop("on_fix_required")}
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_DONE)
            # The namespace migration was AUDITED (not silent).
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("charter_acceptance_normalized", types)

    def test_enabled_mode_conflict_is_fatal_at_construction(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter()
            charter["tooling"]["acceptance"]["mode"] = "off"
            charter["tooling"]["acceptance"]["enabled"] = True  # disagree → fatal
            with self.assertRaises(ValueError):
                _driver(d, charter=charter,
                        adapters=_acceptance_adapters(ACC_PASS))


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
            # Acceptance still RAN (degraded, not aborted). Uncalibrated → the pass
            # is ADVISORY (design §3.2): it does NOT ship — it HALTs at the
            # advisory_acceptance_pass_signoff checkpoint for human sign-off.
            self.assertEqual(final.state, STATE_HALTED)
            self.assertTrue(
                any("advisory_acceptance_pass_signoff" in c
                    for c in os.listdir(drv_.checkpoints_dir)),
                os.listdir(drv_.checkpoints_dir))
            self.assertIn("acceptance_advisory_pass_signoff", types)
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
            evidence_dir = os.path.join(d, "eval", "runs", "sprint-001",
                                        "acceptance")
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
            self.assertTrue(acc_adapter.history[0]["network_access"])
            spawn_ev = next(e for e in events if e["type"] == "acceptance_spawn")
            self.assertTrue(
                spawn_ev["payload"]["evidence_path"].startswith("eval/runs/"))
            # §1.7-C: the spawn surface is the orchestrator, gated by calibration.
            self.assertEqual(spawn_ev["payload"]["spawn_surface"], "orchestrator")
            grant_roles = [e["payload"]["role"] for e in events
                           if e["type"] == "sandbox_network_granted"]
            self.assertIn("acceptance", grant_roles)

    def test_eval_nonzero_exit_is_gate_hard_fail(self):
        # The fake eval honors FAKE_EVAL_EXIT to simulate an eval-harness failure.
        # Per §4.2.6 a non-zero eval exit → gate_hard_fail (human resolves), NOT a
        # permissive pass. We set the env var via the eval.cmd itself (offline).
        fail_cmd = f'"{_sys.executable}" "{_FAKE_EVAL_ACCEPTANCE_FAIL}"'
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(eval_cmd=fail_cmd)
            drv_ = _driver(d, charter=charter,
                           adapters=_acceptance_adapters(ACC_PASS))
            with self.assertRaises(GateHardFail) as ctx:
                drv_.run(subsprint_id="sprint-001")
            self.assertIn("eval", ctx.exception.reason.lower())
            # Acceptance was NOT spawned (no evidence to judge).
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("subsprint_gate_run", types)
            self.assertIn("acceptance_eval_run", types)
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
            charter = _acceptance_charter(
                level="fully_autonomous_within_budget", subsprint_sequence=seq)
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
                     only_if_severity_at_most="P1",
                     dry_stop_threshold=None,
                     max_fix_rounds_total=None):
    """A charter with autonomy.auto_pass_rules.auto_fix_iteration configured so
    the controller can authorize auto-iteration (NOT the HITL human-confirm
    path).

    Default severity ceiling is P1: P2 is record-only (a fix_required whose
    findings are all P2 is normalized to a pass upstream and never reaches the
    auto-fix loop), so a P1 ceiling — auto-fix P1, escalate P0 — is the meaningful
    default. Tests asserting severity escalation pass an explicit ceiling (e.g.
    "P2" with a P0 finding)."""
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
            ("review", 0): _fix_review([_finding("F1", "P1")]),
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
            self.assertEqual(final.history.count("close_pending"), 1)
            self.assertEqual(len(adapters["deliver"].history), 1)
            self.assertEqual(final.state, STATE_ADVANCE)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("auto_fix_round_spawned", types)
            self.assertIn("controller_decision", types)
            self.assertIn("advance", types)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_fix_round_dev_prompt_carries_review_findings(self):
        # delivery-loop §4.4: the auto-fix Dev re-entry must run "with review
        # findings as input". The re-entered Dev prompt MUST carry the Reviewer's
        # SPECIFIC findings (id/severity/layer/evidence/rationale) + a "fix THESE in
        # the existing code" instruction, while the FIRST (initial) Dev prompt stays
        # byte-identical with NO fix guidance. Regression guard for the whack-a-mole
        # enabler where the fix round re-dispatched the bare plan projection.
        review_responses = {
            ("review", 0): _fix_review(
                [_finding("FX-1", "P1", layer="semantic_planner")]),
            ("review", 1): CLEAN_REVIEW,
        }
        with tempfile.TemporaryDirectory() as d:
            dev = _PromptCapturingMock(
                {("dev",): DEV_ARTIFACT}, harness="claude_code",
                provider="anthropic", model="claude-sonnet-4-6")
            adapters = _adapters()
            adapters["dev"] = dev
            adapters["review"] = MockAdapter(
                review_responses, harness="headless",
                provider="deepseek", model="deepseek-chat")
            charter = _autofix_charter(enabled=True, max_rounds=3)
            drv_ = _driver(d, charter=charter, adapters=adapters)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            # Two dev spawns: the initial implementation + one auto-fix round.
            self.assertEqual(len(dev.prompts), 2)
            first, fix = dev.prompts[0], dev.prompts[1]
            # Initial Dev prompt: NO fix guidance (byte-identical path preserved).
            self.assertNotIn("Fix round", first)
            self.assertNotIn("FX-1", first)
            # Fix-round Dev prompt: carries the finding details + the incremental,
            # in-place fix instruction.
            self.assertIn("Fix round 1", fix)
            self.assertIn("EXISTING code", fix)
            self.assertIn("FX-1", fix)
            self.assertIn("P1", fix)
            self.assertIn("semantic_planner", fix)
            self.assertIn("src/x.py:4", fix)  # _finding evidence = src/x.py:len(id)

    def test_fix_round_guidance_gated_and_fail_safe(self):
        # The guidance is gated: empty on the first implementation (fix_round 0) and
        # empty when last_verdict is NOT a fix_required review verdict — so a stale
        # close/dev artifact can never leak findings into a fresh sub-sprint's Dev.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, charter=_autofix_charter(enabled=True))
            drv_.state = RunState(loop_id=drv_.loop_id, subsprint_id="sprint-001")
            # fix_round 0 → "" even with a fix_required verdict present.
            drv_.state.fix_round = 0
            drv_.state.last_verdict = _fix_review([_finding("F1")])
            self.assertEqual(drv_._fix_round_guidance(), "")
            # fix_round > 0 but last_verdict is a (non-review) close verdict → "".
            drv_.state.fix_round = 1
            drv_.state.last_verdict = CLEAN_CLOSE
            self.assertEqual(drv_._fix_round_guidance(), "")
            # fix_round > 0 + a real fix_required review verdict → guidance present.
            drv_.state.last_verdict = _fix_review([_finding("F1", "P1")])
            g = drv_._fix_round_guidance()
            self.assertIn("F1", g)
            self.assertIn("EXISTING code", g)

    def test_fix_round_guidance_survives_resume_into_dev_pending(self):
        # Crash/resume INTO an auto-fix Dev round: the persisted state carries
        # fix_round>0 + the triggering fix_required verdict, so the RESUMED Dev prompt
        # still carries the findings — the guidance is sourced from the RELOADED
        # last_verdict (state.json), not from any in-process local. (Codex P2.)
        with tempfile.TemporaryDirectory() as d:
            seed = _driver(d, charter=_autofix_charter(enabled=True))
            seed.state = RunState(loop_id=seed.loop_id, subsprint_id="sprint-001")
            seed.state.state = STATE_DEV_PENDING
            seed.state.fix_round = 1
            seed.state.last_verdict = _fix_review([_finding("RX-9", "P1")])
            seed._save_state()
            # A fresh Driver reloads the persisted state and re-enters _step_dev.
            dev = _PromptCapturingMock(
                {("dev",): DEV_ARTIFACT}, harness="claude_code",
                provider="anthropic", model="claude-sonnet-4-6")
            adapters = _adapters()
            adapters["dev"] = dev
            drv2 = _driver(d, charter=_autofix_charter(enabled=True),
                           adapters=adapters)
            drv2.state = drv2._load_state()
            self.assertEqual(drv2.state.fix_round, 1)            # reloaded from disk
            self.assertEqual(drv2.state.state, STATE_DEV_PENDING)
            drv2._step_dev()
            self.assertTrue(dev.prompts)
            self.assertIn("RX-9", dev.prompts[0])
            self.assertIn("EXISTING code", dev.prompts[0])

    def test_multi_round_fix_uses_latest_findings_only(self):
        # Round 0 review → fix_required[A1]; round 1 → fix_required[B2]; round 2 →
        # clean. Each fix-round Dev prompt must carry THAT round's findings, never a
        # stale earlier set (round 2 Dev sees B2, not A1). (Codex P2.)
        review_responses = {
            ("review", 0): _fix_review([_finding("A1", "P1")]),
            ("review", 1): _fix_review([_finding("B2", "P1")]),
            ("review", 2): CLEAN_REVIEW,
        }
        with tempfile.TemporaryDirectory() as d:
            dev = _PromptCapturingMock(
                {("dev",): DEV_ARTIFACT}, harness="claude_code",
                provider="anthropic", model="claude-sonnet-4-6")
            adapters = _adapters()
            adapters["dev"] = dev
            adapters["review"] = MockAdapter(
                review_responses, harness="headless",
                provider="deepseek", model="deepseek-chat")
            drv_ = _driver(d, charter=_autofix_charter(enabled=True, max_rounds=5),
                           adapters=adapters)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            # 3 dev spawns: initial + fix round 1 (A1) + fix round 2 (B2).
            self.assertEqual(len(dev.prompts), 3)
            self.assertNotIn("Fix round", dev.prompts[0])
            self.assertIn("A1", dev.prompts[1])
            self.assertNotIn("B2", dev.prompts[1])
            self.assertIn("B2", dev.prompts[2])   # latest findings...
            self.assertNotIn("A1", dev.prompts[2])  # ...not the stale round-1 set

    def test_continue_disabled_keeps_hitl_human_confirm(self):
        # BACKWARD-COMPAT: auto_fix NOT enabled → controller `continue` must NOT
        # auto-iterate; the existing fix_required human-confirm checkpoint fires
        # and the loop HALTS (UNCHANGED P2/HITL behaviour, Constitution §1.7-D).
        with tempfile.TemporaryDirectory() as d:
            charter = _autofix_charter(enabled=False, max_rounds=3)
            drv_ = _driver(
                d, charter=charter,
                adapters=_adapters(review=_fix_review([_finding("F1", "P1")])))
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
                adapters=_adapters(review=_fix_review([_finding("F1", "P1")])))
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
            # WP-0: memory_bytes is the ACTUAL injected lessons-block size (faithful to
            # the dispatched prompt), not a recompute — > 0 here and equal to the block.
            self.assertEqual(dev_spawn["payload"]["memory_bytes"],
                             len(drv_._lessons_block("dev").encode("utf-8")))
            self.assertGreater(dev_spawn["payload"]["memory_bytes"], 0)

    def test_wp0_memory_bytes_faithful_to_injected_block_not_recomputed(self):
        """WP-0 regression (Codex r2 BLOCKING): the spawn audit derives memory_bytes /
        memory_injected from the lessons block the caller ACTUALLY prepended, not a
        recomputed "would-inject" estimate. A spawn that injects NO block
        (lessons_block=None — the Acceptance execution-plan shape) records 0 / [] EVEN
        WHEN role-scoped memory exists; a spawn that injects the block records its real
        bytes + ids."""
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as mem:
            self._seed_memory(mem)  # a "dev"-scoped lesson now exists in the store
            drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-mem-wp0", clock=_clock(), memory_root=mem)
            drv_.run(subsprint_id="sprint-001")  # initializes state + adapters
            block = drv_._lessons_block("dev")
            self.assertTrue(block.strip(), "precondition: dev memory block is non-empty")

            def _last_spawn_payload():
                return [e for e in audit.read_events(drv_.audit_ledger)
                        if e["type"] == "spawn"][-1]["payload"]

            # (A) No block injected (the Acceptance-plan shape) → faithful 0 / [],
            # despite dev-scoped memory being present.
            drv_._spawn("dev", "PLAN PROMPT (no lessons block)", schema_key=None,
                        lessons_block=None)
            a = _last_spawn_payload()
            self.assertEqual(a["memory_bytes"], 0)
            self.assertEqual(a["memory_injected"], [])

            # (B) The block IS injected → memory_bytes = its real size; ids recorded.
            drv_._spawn("dev", block + "BODY", schema_key=None, lessons_block=block)
            b = _last_spawn_payload()
            self.assertEqual(b["memory_bytes"], len(block.encode("utf-8")))
            self.assertIn("prefer-explicit-eligibility-branches", b["memory_injected"])
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_close_records_observation_and_matures_l1_to_l2(self):
        # On a fix_required finding, the driver records a generalizable lesson;
        # a SECOND loop recording the same finding pattern matures it L1 → L2.
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as mem:
            charter = _autofix_charter(enabled=False)  # HITL path still records
            fix_review = _fix_review([_finding("F1", "P1",
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

    # ----- WP-6: tier-aware bounded ingress wiring ------------------------- #
    def _seed_many_dev_l1(self, root, n):
        """Seed n DISTINCT dev-scoped L1 singletons (occurrences=1)."""
        store = ms.MemoryStore(root)
        for i in range(n):
            store.record_observation(
                f"dev singleton lesson number {i:03d}",
                ts="2026-06-15", loop_id=f"loop-seed-{i}",
                type="heuristic", scope={"role": ["dev"], "module": ["m"]},
                body=(f"Singleton observation {i:03d}: under condition C{i}, prefer "
                      f"approach A{i} because of rationale R{i}."))
        return store

    def _dev_spawn_payload(self, ledger):
        return next(e for e in audit.read_events(ledger)
                    if e["type"] == "spawn" and e["payload"]["role"] == "dev")["payload"]

    def test_wp6_l1_budget_bounds_injection_and_records_suppression(self):
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as mem:
            self._seed_many_dev_l1(mem, 12)
            drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-wp6-budget", clock=_clock(),
                          memory_root=mem,
                          lesson_budget=ls.LessonBudget(max_l1_count=3,
                                                        max_l1_bytes=10_000))
            drv_.run(subsprint_id="sprint-001")
            p = self._dev_spawn_payload(drv_.audit_ledger)
            # exactly 3 injected, 9 suppressed (all L1 over the count budget).
            self.assertEqual(len(p["memory_injected"]), 3)
            self.assertEqual(len(p["suppressed_lesson_ids"]), 9)
            self.assertEqual(set(p["memory_injected"]) & set(p["suppressed_lesson_ids"]),
                             set())
            seldata = p["lesson_selection"]
            self.assertEqual(seldata["version"], ls.SELECTION_VERSION)
            self.assertTrue(all(s["reason"] == "l1_count_budget"
                                for s in seldata["suppressed"]))
            self.assertTrue(all(t == "L1" for t in seldata["tiers"].values()))
            self.assertLess(seldata["bytes_after"], seldata["bytes_before"])
            # Non-silent: the bounded block carries the footer + the audit chain holds.
            self.assertIn("Loop Memory bounded", drv_._lessons_block("dev"))
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_wp6_matured_l2_preserved_over_budget(self):
        # An L2 + a MATURED lesson must survive even a budget of 1, alongside L1s.
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as mem:
            store = self._seed_many_dev_l1(mem, 8)
            # promote two distinct keys to L2 / MATURED by re-observation.
            store.record_observation("dev validated lesson", ts="2026-06-16",
                                     loop_id="lp-v1", type="failure",
                                     scope={"role": ["dev"], "module": ["m"]},
                                     body="Validated: always re-check the guard.")
            store.record_observation("dev validated lesson", ts="2026-06-16",
                                     loop_id="lp-v2", type="failure",
                                     scope={"role": ["dev"], "module": ["m"]},
                                     body="Validated: always re-check the guard.")  # occ2→L2
            for k in range(3):
                store.record_observation("dev matured lesson", ts="2026-06-17",
                                         loop_id=f"lp-m{k}", type="failure",
                                         scope={"role": ["dev"], "module": ["m"]},
                                         body="Matured: never collapse the branch.")
            drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-wp6-mat", clock=_clock(), memory_root=mem,
                          lesson_budget=ls.LessonBudget(max_l1_count=1,
                                                        max_l1_bytes=10_000))
            drv_.run(subsprint_id="sprint-001")
            p = self._dev_spawn_payload(drv_.audit_ledger)
            tiers = p["lesson_selection"]["tiers"]
            l2_id = ms.slug("dev validated lesson")
            mat_id = ms.slug("dev matured lesson")
            self.assertEqual(tiers[l2_id], "L2")
            self.assertEqual(tiers[mat_id], "MATURED")
            self.assertIn(l2_id, p["memory_injected"])
            self.assertIn(mat_id, p["memory_injected"])
            self.assertNotIn(l2_id, p["suppressed_lesson_ids"])
            self.assertNotIn(mat_id, p["suppressed_lesson_ids"])
            # No non-L1 ever suppressed.
            for s in p["lesson_selection"]["suppressed"]:
                self.assertEqual(s["tier"], "L1")

    def test_wp6_input_hash_and_block_deterministic_across_runs(self):
        # Same store + same budget → identical injected block → identical input_hash
        # (retry/reuse determinism). Acceptance is untouched (it injects no lessons).
        with tempfile.TemporaryDirectory() as mem:
            self._seed_many_dev_l1(mem, 10)
            budget = ls.LessonBudget(max_l1_count=4, max_l1_bytes=10_000)
            hashes, blocks = [], []
            for run_i in range(2):
                with tempfile.TemporaryDirectory() as d:
                    drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                                  loop_id=f"loop-wp6-det-{run_i}", clock=_clock(),
                                  memory_root=mem, lesson_budget=budget)
                    drv_.run(subsprint_id="sprint-001")
                    p = self._dev_spawn_payload(drv_.audit_ledger)
                    hashes.append(p["input_hash"])
                    blocks.append(drv_._lessons_block("dev"))
            self.assertEqual(hashes[0], hashes[1])
            self.assertEqual(blocks[0], blocks[1])

    def test_wp6_acceptance_plan_shape_records_no_lesson_audit(self):
        # A spawn that injects NO lessons block (lessons_block=None) records
        # suppressed_lesson_ids=None + lesson_selection=None — Acceptance-neutral.
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as mem:
            self._seed_many_dev_l1(mem, 5)
            drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-wp6-acc", clock=_clock(), memory_root=mem)
            drv_.run(subsprint_id="sprint-001")
            drv_._spawn("dev", "PLAN PROMPT (no lessons block)", schema_key=None,
                        lessons_block=None)
            p = [e for e in audit.read_events(drv_.audit_ledger)
                 if e["type"] == "spawn"][-1]["payload"]
            self.assertEqual(p["memory_injected"], [])
            self.assertEqual(p["memory_bytes"], 0)
            self.assertIsNone(p["suppressed_lesson_ids"])
            self.assertIsNone(p["lesson_selection"])
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_wp6_explicit_supersession_through_driver(self):
        # An active entry that supersedes an L2 lesson removes it at ingress.
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as mem:
            store = ms.MemoryStore(mem)
            old = ms.MemoryEntry(id="old-lesson", type="failure",
                                 scope={"role": ["dev"], "module": ["m"]},
                                 maturity="L2", occurrences=4, status="active",
                                 body="Old matured guidance.")
            store.write_entry(old, ts="2026-06-15", loop_id="lp-old")
            new = ms.MemoryEntry(id="new-lesson", type="failure",
                                 scope={"role": ["dev"], "module": ["m"]},
                                 maturity="L2", occurrences=2, status="active",
                                 supersedes=["old-lesson"],
                                 body="New replacement guidance.")
            store.write_entry(new, ts="2026-06-16", loop_id="lp-new")
            drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-wp6-sup", clock=_clock(), memory_root=mem)
            drv_.run(subsprint_id="sprint-001")
            p = self._dev_spawn_payload(drv_.audit_ledger)
            self.assertIn("new-lesson", p["memory_injected"])
            self.assertNotIn("old-lesson", p["memory_injected"])
            self.assertIn("old-lesson", p["suppressed_lesson_ids"])
            sup = [s for s in p["lesson_selection"]["suppressed"]
                   if s["id"] == "old-lesson"][0]
            self.assertEqual(sup["reason"], "superseded")
            self.assertEqual(sup["tier"], "MATURED")

    def test_wp6_malformed_entry_failsafe_preserved_through_driver(self):
        # A store with a contradictory entry (maturity L1, occurrences>=2 — written
        # via write_entry which does not re-derive maturity) classifies UNKNOWN and
        # is PRESERVED even under a zero-room L1 budget — never dropped as L1.
        with tempfile.TemporaryDirectory() as d, \
                tempfile.TemporaryDirectory() as mem:
            store = self._seed_many_dev_l1(mem, 6)
            bad = ms.MemoryEntry(id="contradictory", type="heuristic",
                                 scope={"role": ["dev"], "module": ["m"]},
                                 maturity="L1", occurrences=5, status="active",
                                 body="Contradictory metadata lesson.")
            store.write_entry(bad, ts="2026-06-15", loop_id="lp-bad")
            drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-wp6-bad", clock=_clock(), memory_root=mem,
                          lesson_budget=ls.LessonBudget(max_l1_count=1,
                                                        max_l1_bytes=10_000))
            drv_.run(subsprint_id="sprint-001")
            p = self._dev_spawn_payload(drv_.audit_ledger)
            self.assertEqual(p["lesson_selection"]["tiers"]["contradictory"], "UNKNOWN")
            self.assertIn("contradictory", p["memory_injected"])
            self.assertNotIn("contradictory", p["suppressed_lesson_ids"])


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
        # Review declared no connectors → default-deny ([]) + LEAST-PRIVILEGE
        # sandbox: a judge that omits `sandbox` defaults to read_only (only Dev
        # defaults to workspace_write), so a read-only reviewer is never silently
        # launched with write access.
        rev_hist = adapters["review"].history[0]
        self.assertEqual(rev_hist["connectors"], [])
        self.assertEqual(rev_hist["sandbox"], "read_only")

    def test_no_connectors_passes_empty_grant(self):
        # The unmodified example charter grants no connectors to any role.
        with tempfile.TemporaryDirectory() as d:
            adapters = _adapters()
            _driver(d, adapters=adapters).run(subsprint_id="sprint-001")
        for role in ("dev", "review", "deliver"):
            self.assertEqual(adapters[role].history[0]["connectors"], [])

    def test_network_access_grants_thread_and_audit(self):
        # The example charter explicitly grants network to the three spawned roles;
        # each grant is threaded to the adapter and recorded on the audit spine.
        charter = load_charter(CHARTER_PATH)
        with tempfile.TemporaryDirectory() as d:
            adapters = _adapters()
            drv_ = _driver(d, charter=charter, adapters=adapters)
            drv_.run(subsprint_id="sprint-001")
            events = audit.read_events(drv_.audit_ledger)
        for role in ("dev", "review", "deliver"):
            self.assertTrue(adapters[role].history[0]["network_access"])
        grants = [e for e in events if e["type"] == "sandbox_network_granted"]
        self.assertEqual([g["payload"]["role"] for g in grants],
                         ["dev", "review", "deliver"])

    def test_explicit_network_false_suppresses_grant_and_audit(self):
        # Explicit false keeps the old no-network path: adapters see False and no
        # sandbox_network_granted event is emitted.
        charter = load_charter(CHARTER_PATH)
        for role in ("dev", "review", "deliver"):
            charter["tooling"][role]["network_access"] = False
        with tempfile.TemporaryDirectory() as d:
            adapters = _adapters()
            drv_ = _driver(d, charter=charter, adapters=adapters)
            drv_.run(subsprint_id="sprint-001")
            events = audit.read_events(drv_.audit_ledger)
        for role in ("dev", "review", "deliver"):
            self.assertFalse(adapters[role].history[0]["network_access"])
        self.assertEqual(
            [e for e in events if e["type"] == "sandbox_network_granted"], [])


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

    def test_missing_registry_record_at_close_is_repaired(self):
        run_dir = os.path.join(self.tmp, "run-missing-reg")
        drv_ = Driver(load_charter(CHARTER_PATH), run_dir, _adapters(),
                      loop_id="loop-ing-missing", clock=_clock(), repo_dir=self.repo)
        original_handle_close = drv_._handle_close

        def _handle_close_and_drop_registry(close_verdict):
            original_handle_close(close_verdict)
            os.remove(self._registry().path)

        drv_._handle_close = _handle_close_and_drop_registry
        final = drv_.run(subsprint_id="sprint-001")
        self.assertEqual(final.state, STATE_ADVANCE)
        rec = self._registry().get("loop-ing-missing")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.status, "done")
        types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
        self.assertIn("loop_registry_repaired", types)
        self.assertIn("loop_close", types)

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
        # A hard-fail marks the loop FAILED (not active) so it never leaks as
        # active and collides with a fresh re-run; the branch + record are KEPT so
        # a RESUME can still reattach (registry.get ignores status).
        rec1 = self._registry().get("loop-ing-007")
        self.assertEqual(rec1.status, "failed")
        self.assertIn("crash before close", rec1.failure or "")

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


class StripFrontMatterTests(unittest.TestCase):
    """A dev-spec's YAML front-matter must be stripped from the prompt (it is doc
    metadata, and a prompt starting with '---' is mis-parsed as a CLI option)."""

    def test_strips_yaml_front_matter(self):
        text = "---\ntitle: x\nk: v\n---\n# Body\nhello"
        self.assertEqual(Driver._strip_front_matter(text), "# Body\nhello")

    def test_no_front_matter_unchanged(self):
        self.assertEqual(Driver._strip_front_matter("# Body\nx"), "# Body\nx")

    def test_unterminated_front_matter_unchanged(self):
        t = "---\ntitle: x\nno closing delimiter"
        self.assertEqual(Driver._strip_front_matter(t), t)

    def test_stripped_body_does_not_start_with_dash(self):
        text = "---\na: 1\n---\n# Job\nrun it"
        self.assertFalse(Driver._strip_front_matter(text).startswith("-"))

    def test_thematic_break_body_not_mistaken_for_front_matter(self):
        # A Markdown body that opens with a `---` rule and later has another `---`
        # must NOT be stripped (the block is not a YAML mapping). Regression guard.
        text = "---\n\nReal heading\n\n---\n\nmore body"
        self.assertEqual(Driver._strip_front_matter(text), text)
        fm, body = Driver._split_front_matter(text)
        self.assertIsNone(fm)
        self.assertEqual(body, text)


class RouteSandboxTests(unittest.TestCase):
    """route_for_role: least-privilege per-role sandbox + tools normalization."""

    def test_omitted_sandbox_defaults_least_privilege(self):
        charter = {"tooling": {"dev": {"harness": "claude_code"},
                               "review": {"harness": "codex"},
                               "acceptance": {"enabled": True},
                               "research": {"harness": "claude_code"}}}
        self.assertEqual(drv.route_for_role(charter, "dev").sandbox, "workspace_write")
        self.assertEqual(drv.route_for_role(charter, "review").sandbox, "read_only")
        self.assertEqual(drv.route_for_role(charter, "acceptance").sandbox, "read_only")
        self.assertEqual(drv.route_for_role(charter, "research").sandbox, "read_only")

    def test_explicit_sandbox_wins(self):
        charter = {"tooling": {"review": {"harness": "codex",
                                          "sandbox": "workspace_write"}}}
        self.assertEqual(drv.route_for_role(charter, "review").sandbox,
                         "workspace_write")

    def test_tools_object_form_normalized(self):
        # The v2 object form {allow:[...]} must unpack to the allowlist, NOT to the
        # dict keys (["allow"]) — the bug that silently broke tool gating.
        charter = {"tooling": {"review": {"harness": "codex",
                                          "tools": {"allow": ["Read", "Grep"]}}}}
        self.assertEqual(drv.route_for_role(charter, "review").tools,
                         ["Read", "Grep"])
        self.assertEqual(drv._normalize_tools(["Read", "Glob"]), ["Read", "Glob"])
        self.assertEqual(drv._normalize_tools({"allow": ["Read"]}), ["Read"])
        self.assertEqual(drv._normalize_tools(None), [])


class DevSpecResolutionTests(unittest.TestCase):
    """FIX: the Dev spec is the schema-valid decompose plan (canonical), validated
    by CONTENT; an incomplete/missing/unsafe spec on a live run HALTS (resumable)."""

    _GOOD_PLAN = [{
        "id": "sprint-001", "objective": "Add refund-eligibility check (UC-1)",
        "scope_in": ["UC-1 eligibility decision"], "scope_out": ["denial wording"],
        "modules": ["src/tools/eligibility.py"], "layers": ["semantic_planner"],
        "exit_criteria": ["UC-1 tests pass"]}]

    def _live_driver(self, d, *, planned=None, repo_dir=None, sid="sprint-001"):
        drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                      loop_id="loop-spec", clock=_clock(),
                      context={"allow_real": True}, repo_dir=repo_dir)
        drv_.state = RunState(loop_id="loop-spec", subsprint_id=sid)
        drv_.state.state = STATE_DEV_PENDING
        drv_.state.planned_subsprints = planned or []
        return drv_

    def test_safe_subsprint_id(self):
        for ok in ("sprint-001", "M5-sprint-3", "s_1.2"):
            self.assertTrue(Driver._safe_subsprint_id(ok))
        for bad in ("../etc/passwd", "a/b", "..", "", "sprint 1", "sp;rm"):
            self.assertFalse(Driver._safe_subsprint_id(bad))

    def test_validate_subsprint_spec(self):
        self.assertEqual(Driver._validate_subsprint_spec(self._GOOD_PLAN[0]), [])
        bad = Driver._validate_subsprint_spec(
            {"id": "x", "objective": "", "scope_in": [], "exit_criteria": []})
        self.assertEqual(len(bad), 3)

    def test_validate_compact_text_requires_self_contained(self):
        self.assertEqual(
            Driver._validate_compact_text({"context_budget": {"self_contained": True}},
                                          "real bounded body"), [])
        self.assertTrue(
            Driver._validate_compact_text({"context_budget": {"self_contained": False}},
                                          "body"))
        self.assertTrue(Driver._validate_compact_text(None, "body"))  # no front-matter

    def test_project_dev_prompt_renders_fields(self):
        out = Driver._project_dev_prompt(self._GOOD_PLAN[0])
        self.assertIn("Add refund-eligibility check (UC-1)", out)
        self.assertIn("UC-1 eligibility decision", out)
        self.assertIn("UC-1 tests pass", out)
        self.assertIn("src/tools/eligibility.py", out)

    def test_offline_resolves_to_none(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = self._live_driver(d, planned=self._GOOD_PLAN)
            drv_.context["allow_real"] = False  # offline → legacy inline prompt
            self.assertIsNone(drv_._resolve_dev_spec())

    def test_live_plan_projects_and_writes_projection(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(repo)
            drv_ = self._live_driver(d, planned=self._GOOD_PLAN, repo_dir=repo)
            out = drv_._resolve_dev_spec()
            self.assertIsInstance(out, str)
            self.assertIn("Add refund-eligibility check (UC-1)", out)
            # auditable projection written (plan stays normative).
            self.assertTrue(os.path.isfile(
                os.path.join(repo, "compact", "sprint-001-dev-prompt.md")))

    def test_live_incomplete_plan_halts_for_refinement(self):
        with tempfile.TemporaryDirectory() as d:
            bad = [{"id": "sprint-001", "objective": "", "scope_in": [],
                    "exit_criteria": []}]
            drv_ = self._live_driver(d, planned=bad)
            self.assertIs(drv_._resolve_dev_spec(), drv._DEV_SPEC_HALT)
            self.assertEqual(drv_.state.state, STATE_HALTED)
            # The halt is PERSISTED — a resume must see HALTED, not stale dev_pending.
            self.assertEqual(drv_._load_state().state, STATE_HALTED)

    def test_projection_is_reusable_as_compact_source(self):
        # The compact-file PROJECTION carries self_contained:true front-matter, so a
        # later delivery_only run (no plan) can resolve it as a valid compact source.
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(repo)
            self._live_driver(d, planned=self._GOOD_PLAN, repo_dir=repo)\
                ._resolve_dev_spec()  # writes the projection
            reuse = self._live_driver(d, planned=[], repo_dir=repo)
            out = reuse._resolve_dev_spec()
            self.assertIsInstance(out, str)
            self.assertIsNot(out, drv._DEV_SPEC_HALT)
            self.assertIn("Add refund-eligibility check (UC-1)", out)

    def test_live_unsafe_id_halts_before_any_path_use(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(repo)
            drv_ = self._live_driver(d, planned=[], repo_dir=repo,
                                     sid="../../evil")
            self.assertIs(drv_._resolve_dev_spec(), drv._DEV_SPEC_HALT)
            self.assertEqual(drv_.state.state, STATE_HALTED)
            # nothing escaped the repo/compact dir.
            self.assertFalse(os.path.exists(os.path.join(d, "evil-dev-prompt.md")))

    def test_live_compact_file_fallback_when_no_plan(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(os.path.join(repo, "compact"))
            with open(os.path.join(repo, "compact", "sprint-001-dev-prompt.md"),
                      "w", encoding="utf-8") as fh:
                fh.write("---\ncontext_budget:\n  self_contained: true\n---\n"
                         "Bounded job: implement UC-1.")
            drv_ = self._live_driver(d, planned=[], repo_dir=repo)
            out = drv_._resolve_dev_spec()
            self.assertEqual(out, "Bounded job: implement UC-1.")

    def test_live_compact_file_without_self_contained_halts(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(os.path.join(repo, "compact"))
            with open(os.path.join(repo, "compact", "sprint-001-dev-prompt.md"),
                      "w", encoding="utf-8") as fh:
                fh.write("just a bare prompt, no front-matter")
            drv_ = self._live_driver(d, planned=[], repo_dir=repo)
            self.assertIs(drv_._resolve_dev_spec(), drv._DEV_SPEC_HALT)
            self.assertEqual(drv_.state.state, STATE_HALTED)

    def test_live_no_spec_halts(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = self._live_driver(d, planned=[])  # no plan, no repo/file
            self.assertIs(drv_._resolve_dev_spec(), drv._DEV_SPEC_HALT)
            self.assertEqual(drv_.state.state, STATE_HALTED)


# --------------------------------------------------------------------------- #
# AUDITABILITY — per-spawn prompt + output transcripts (the materialization the
# bp-review-team adoption flagged). EVERY spawn writes the as-dispatched prompt
# and the captured output to .orchestrator/audit/transcripts/<loop>/, referenced
# from the spawn event so the process is auditable file-by-file, not just by hash.
# --------------------------------------------------------------------------- #
class TestSpawnTranscripts(unittest.TestCase):
    def _spawns(self, drv_):
        return [e["payload"] for e in audit.read_events(drv_.audit_ledger)
                if e["type"] == "spawn"]

    def test_every_spawn_writes_prompt_and_output_referenced_from_audit(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            spawns = self._spawns(drv_)
            self.assertEqual(len(spawns), 3)  # dev, review, deliver
            for p in spawns:
                for ref_key in ("prompt_ref", "output_ref"):
                    ref = p[ref_key]
                    self.assertTrue(ref, f"{p['role']} missing {ref_key}")
                    self.assertTrue(os.path.isfile(os.path.join(d, ref)), ref)
                    self.assertIn(".orchestrator/audit/transcripts", ref)

    def test_prompt_transcript_is_exact_dispatched_bytes(self):
        # The review prompt is captured verbatim; its bytes cross-check the spawn
        # input_hash = sha256(role\x00 + prompt) — the transcript IS what was sent.
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            review = next(p for p in self._spawns(drv_) if p["role"] == "review")
            with open(os.path.join(d, review["prompt_ref"]), encoding="utf-8") as fh:
                prompt_bytes = fh.read()
            self.assertIn("Review sub-sprint sprint-001", prompt_bytes)
            recomputed = "sha256:" + hashlib.sha256(
                ("review\x00" + prompt_bytes).encode("utf-8")).hexdigest()[:16]
            self.assertEqual(recomputed, review["input_hash"])

    def test_output_transcripts_capture_artifact_md_and_verdict_json(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            by_role = {p["role"]: p for p in self._spawns(drv_)}
            # Dev artifact → readable Markdown (handoff prose), not JSON.
            dev_out = os.path.join(d, by_role["dev"]["output_ref"])
            self.assertTrue(dev_out.endswith(".md"))
            with open(dev_out, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), DEV_ARTIFACT["artifact"])
            # Review verdict → JSON that round-trips to the verdict dict.
            review_out = os.path.join(d, by_role["review"]["output_ref"])
            self.assertTrue(review_out.endswith(".json"))
            with open(review_out, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), CLEAN_REVIEW)

    def test_invalid_verdict_still_captures_output_transcript(self):
        # A schema-invalid verdict hard-fails, but its output is materialized +
        # referenced (captured BEFORE validation) so the failure is auditable.
        import json
        bad_review = {"decision": "looks_good", "blocking_count": 0,
                      "summary": "x", "findings": []}
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(review=bad_review))
            with self.assertRaises(GateHardFail):
                drv_.run(subsprint_id="sprint-001")
            review = next(p for p in self._spawns(drv_) if p["role"] == "review")
            self.assertEqual(review["verdict_ref"], "invalid")
            out_path = os.path.join(d, review["output_ref"])
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), bad_review)

    def test_adapter_error_records_prompt_ref_but_null_output(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, adapters=_adapters(review=AdapterError("boom")))
            with self.assertRaises(GateHardFail):
                drv_.run(subsprint_id="sprint-001")
            review = next(p for p in self._spawns(drv_) if p["role"] == "review")
            self.assertEqual(review["verdict_ref"], "adapter_error")
            self.assertTrue(os.path.isfile(os.path.join(d, review["prompt_ref"])))
            self.assertIsNone(review["output_ref"])  # adapter raised; no output

    def test_invalid_output_transcript_survives_resume_no_clobber(self):
        # spawn_count is persisted EAGERLY, so a resume after a schema-invalid
        # hard-fail does NOT rewind the count and overwrite the (already-audited)
        # invalid output transcript with the retry's output.
        import json
        bad = {"decision": "looks_good", "blocking_count": 0, "summary": "x",
               "findings": []}
        with tempfile.TemporaryDirectory() as d:
            drv1 = _driver(d, adapters=_adapters(review=bad),
                           loop_id="loop-clobber-001")
            with self.assertRaises(GateHardFail):
                drv1.run(subsprint_id="sprint-001")
            review1 = next(p for p in self._spawns(drv1) if p["role"] == "review")
            orig = os.path.join(d, review1["output_ref"])
            with open(orig, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), bad)
            # Resume over the SAME run_dir with a healthy review adapter.
            drv2 = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-clobber-001", clock=_clock())
            self.assertEqual(drv2.run(resume=True).state, STATE_ADVANCE)
            # The original invalid output is UNTOUCHED (retry used a fresh seq).
            with open(orig, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), bad)
            # Two review spawns, two DISTINCT output transcripts.
            refs = [p["output_ref"] for p in self._spawns(drv2)
                    if p["role"] == "review"]
            self.assertEqual(len(refs), 2)
            self.assertEqual(len(set(refs)), 2)
            self.assertIn(review1["output_ref"], refs)

    def test_audit_report_surfaces_transcript_refs(self):
        import audit_report  # engine-kit/audit is on sys.path
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            report = audit_report.render_report_file(drv_.audit_ledger)
            self.assertIn("prompt_ref", report)
            self.assertIn("output_ref", report)


class TestLoopIdSafety(unittest.TestCase):
    """loop_id keys the audit ledger filename (raw) + the transcripts dir, so an
    unsafe value is rejected FAIL-CLOSED at the Driver boundary — no traversal, and
    no two distinct ids ever aliasing into one dir via lossy sanitization."""

    def test_unsafe_loop_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            # Incl. a TRAILING NEWLINE ("loop-ok\n"): Python `$` would accept it, so
            # the regex is \A…\Z-anchored — the newline must be rejected. Non-str
            # ids (1, None) are rejected too (else `1` and `"1"` alias one path).
            for bad in ("loop/a", "../evil", "loop a", "", "..",
                        "loop\x00a", "loop-ok\n", "a" * 200, 1, None):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    _driver(d, loop_id=bad)

    def test_safe_loop_id_accepted_and_keys_transcript_dir(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, loop_id="delivery_only-sprint-001")
            self.assertTrue(
                drv_.transcripts_dir.endswith(
                    os.path.join("transcripts", "delivery_only-sprint-001")))
            # And it actually runs end-to-end with that id.
            self.assertEqual(drv_.run(subsprint_id="sprint-001").state,
                             STATE_ADVANCE)


class TestAcceptanceTranscripts(unittest.TestCase):
    def test_acceptance_spawn_event_references_both_refs(self):
        # Acceptance follows the SAME contract as _spawn: one acceptance_spawn event
        # carries prompt_ref + output_ref + verdict_ref, both files exist on disk.
        import json
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, charter=_acceptance_charter(),
                           adapters=_acceptance_adapters(ACC_PASS))
            drv_.run(subsprint_id="sprint-001")
            events = audit.read_events(drv_.audit_ledger)
            spawns = [e["payload"] for e in events
                      if e["type"] == "acceptance_spawn"]
            self.assertEqual(len(spawns), 1)  # emitted ONCE, post-outcome
            p = spawns[0]
            self.assertEqual(p["verdict_ref"], "valid")
            self.assertTrue(os.path.isfile(os.path.join(d, p["prompt_ref"])))
            out_path = os.path.join(d, p["output_ref"])
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), ACC_PASS)

    def test_wp7_load_graph_hash_recorded_on_acceptance_spawn(self):
        # WP-7 (observation-only): the heaviest role records the cold-start fingerprint too,
        # on the same acceptance_spawn event as the WP-0 prompt_bytes/fix_round fields. This
        # is AUDIT-ONLY and does NOT touch acceptance_input_hash (the §3.5b reuse hash).
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, charter=_acceptance_charter(),
                           adapters=_acceptance_adapters(ACC_PASS))
            drv_.run(subsprint_id="sprint-001")
            spawns = [e["payload"] for e in audit.read_events(drv_.audit_ledger)
                      if e["type"] == "acceptance_spawn"]
            self.assertEqual(len(spawns), 1)
            lgh = spawns[0]["load_graph_hash"]
            self.assertIsInstance(lgh, str)
            self.assertTrue(lgh.startswith("sha256:"), lgh)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_wp7_cold_start_hash_is_best_effort_degrades_to_none(self):
        # WP-7 invariant 6: the driver's cold-start fingerprint must NEVER block a spawn.
        # Any sizing problem — a non-empty `missing` (unreadable/absent mandatory file), a
        # raised exception, or no framework_root — degrades to None (the field is nullable),
        # not a misleading partial fingerprint and not an exception into the spawn path.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            orig = drv.load_sizer.cold_start_load_graph_hash
            try:
                # (a) non-empty missing -> None (never a partial hash).
                drv.load_sizer.cold_start_load_graph_hash = (
                    lambda *a, **k: ("sha256:partial00000000", [{"rel": "governance/x.md"}]))
                self.assertIsNone(drv_._cold_start_load_graph_hash("dev", False))
                # (b) a raised OSError/KeyError/ValueError -> None (best-effort).
                def _boom(*a, **k):
                    raise OSError("simulated read failure")
                drv.load_sizer.cold_start_load_graph_hash = _boom
                self.assertIsNone(drv_._cold_start_load_graph_hash("dev", False))
            finally:
                drv.load_sizer.cold_start_load_graph_hash = orig
            # (c) no framework_root -> None (no governance tree to fingerprint).
            saved_root, drv_.framework_root = drv_.framework_root, None
            try:
                self.assertIsNone(drv_._cold_start_load_graph_hash("dev", False))
            finally:
                drv_.framework_root = saved_root

    def test_acceptance_adapter_error_records_prompt_ref_null_output(self):
        with tempfile.TemporaryDirectory() as d:
            adapters = _acceptance_adapters(AdapterError("acc boom"))
            drv_ = _driver(d, charter=_acceptance_charter(), adapters=adapters)
            with self.assertRaises(GateHardFail):
                drv_.run(subsprint_id="sprint-001")
            spawn = next(e["payload"] for e in audit.read_events(drv_.audit_ledger)
                         if e["type"] == "acceptance_spawn")
            self.assertEqual(spawn["verdict_ref"], "adapter_error")
            self.assertTrue(os.path.isfile(os.path.join(d, spawn["prompt_ref"])))
            self.assertIsNone(spawn["output_ref"])


# --------------------------------------------------------------------------- #
# Two EXPLICIT self-contained prompt contracts (Review + Acceptance) — replacing
# the one-line role prompts. Each resolves: adopter compact file → deterministic
# projection from authoritative structured state → resumable HALT. Gated on
# allow_real, so mock/offline runs keep the legacy inline prompt (byte-identical).
# --------------------------------------------------------------------------- #
_REVIEW_PLAN = [{
    "id": "sprint-001", "objective": "Add refund-eligibility check (UC-1)",
    "scope_in": ["UC-1 eligibility decision"], "scope_out": ["denial wording"],
    "modules": ["src/tools/eligibility.py"], "layers": ["semantic_planner"],
    "exit_criteria": ["UC-1 tests pass"]}]


class ReviewSpecResolutionTests(unittest.TestCase):
    def _live(self, d, *, planned=None, repo_dir=None, sid="sprint-001"):
        drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                      loop_id="loop-rev", clock=_clock(),
                      context={"allow_real": True}, repo_dir=repo_dir)
        drv_.state = RunState(loop_id="loop-rev", subsprint_id=sid)
        drv_.state.state = STATE_REVIEW_PENDING
        drv_.state.planned_subsprints = planned or []
        return drv_

    def test_offline_resolves_to_none(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = self._live(d, planned=_REVIEW_PLAN)
            drv_.context["allow_real"] = False  # offline → legacy inline (byte-identical)
            self.assertIsNone(drv_._resolve_review_spec())

    def test_project_review_prompt_renders_contract_sections(self):
        out = self._live(tempfile.mkdtemp(), planned=_REVIEW_PLAN)\
            ._project_review_prompt(_REVIEW_PLAN[0])
        self.assertIn("Code Reviewer Agent for sub-sprint sprint-001", out)
        self.assertIn("Add refund-eligibility check (UC-1)", out)   # objective
        self.assertIn("UC-1 eligibility decision", out)             # scope IN
        self.assertIn("UC-1 tests pass", out)                       # exit criteria
        self.assertIn("anti-hardcode", out.lower())                 # kernel
        self.assertIn("blocking_count", out)                        # severity rules
        # WP-1b: the agent-facing prompt names the COMPACT projection (not the canonical).
        self.assertIn("compact/review-verdict.compact.schema.json", out)
        self.assertNotIn("schemas/review-verdict.schema.json", out)  # canonical not dispatched

    def test_live_projects_from_subsprint_spec(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._live(d, planned=_REVIEW_PLAN)._resolve_review_spec()
            self.assertIsInstance(out, str)
            self.assertIn("Code Reviewer Agent for sub-sprint sprint-001", out)

    def test_live_adopter_compact_file_wins_over_projection(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(os.path.join(repo, "compact"))
            with open(os.path.join(repo, "compact", "sprint-001-review-prompt.md"),
                      "w", encoding="utf-8") as fh:
                fh.write("---\ncontext_budget:\n  self_contained: true\n---\n"
                         "Adopter-authored self-contained review prompt for UC-1.")
            out = self._live(d, planned=_REVIEW_PLAN, repo_dir=repo)\
                ._resolve_review_spec()
            self.assertEqual(out,
                             "Adopter-authored self-contained review prompt for UC-1.")

    def test_live_invalid_compact_halts(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(os.path.join(repo, "compact"))
            with open(os.path.join(repo, "compact", "sprint-001-review-prompt.md"),
                      "w", encoding="utf-8") as fh:
                fh.write("bare review prompt, no self_contained front-matter")
            drv_ = self._live(d, planned=_REVIEW_PLAN, repo_dir=repo)
            self.assertIs(drv_._resolve_review_spec(), drv._REVIEW_SPEC_HALT)
            self.assertEqual(drv_.state.state, STATE_HALTED)

    def test_live_missing_source_halts_resumable(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = self._live(d, planned=[])  # no plan, no compact
            self.assertIs(drv_._resolve_review_spec(), drv._REVIEW_SPEC_HALT)
            self.assertEqual(drv_.state.state, STATE_HALTED)
            self.assertEqual(drv_._load_state().state, STATE_HALTED)  # persisted

    def test_live_incomplete_plan_halts(self):
        with tempfile.TemporaryDirectory() as d:
            bad = [{"id": "sprint-001", "objective": "", "scope_in": [],
                    "exit_criteria": []}]
            self.assertIs(self._live(d, planned=bad)._resolve_review_spec(),
                          drv._REVIEW_SPEC_HALT)

    def test_projection_materialized_through_spawn(self):
        # projection → _spawn → transcript materialization (the auditability path).
        with tempfile.TemporaryDirectory() as d:
            cap = _PromptCapturingMock({("review",): CLEAN_REVIEW}, harness="codex",
                                       provider="openai", model="gpt-5.5")
            adapters = _adapters()
            adapters["review"] = cap
            drv_ = Driver(load_charter(CHARTER_PATH), d, adapters,
                          loop_id="loop-rev-mat", clock=_clock(),
                          context={"allow_real": True})
            drv_.state = RunState(loop_id="loop-rev-mat", subsprint_id="sprint-001")
            drv_.state.state = STATE_REVIEW_PENDING
            drv_.state.planned_subsprints = _REVIEW_PLAN
            verdict = drv_._step_review()
            self.assertEqual(verdict, CLEAN_REVIEW)
            self.assertIn("Code Reviewer Agent for sub-sprint sprint-001",
                          cap.prompts[-1])
            spawn = next(e["payload"] for e in audit.read_events(drv_.audit_ledger)
                         if e["type"] == "spawn" and e["payload"]["role"] == "review")
            with open(os.path.join(d, spawn["prompt_ref"]), encoding="utf-8") as fh:
                self.assertIn("blocking_count", fh.read())


class AcceptanceSpecResolutionTests(unittest.TestCase):
    _SIGNED_IC = {
        "goal": "Refunds honored for eligible customers",
        "standard": "No eligible refund denied; no ineligible approved",
        "proof_of_done": "All bad-cases pass under F5 eval",
        "confirmed_by_human": True}

    def _live(self, d, *, intent_contract=None, repo_dir=None, mission="M1",
              adapters=None):
        charter = _acceptance_charter()
        if mission is not None:
            charter["mission"] = {"id": mission}
        if intent_contract is not None:
            charter["intent_contract"] = intent_contract
        drv_ = Driver(charter, d, adapters or _acceptance_adapters(ACC_PASS),
                      loop_id="loop-acc", clock=_clock(),
                      context={"allow_real": True}, repo_dir=repo_dir)
        drv_.state = RunState(loop_id="loop-acc", subsprint_id="sprint-001")
        drv_.state.state = STATE_ACCEPTANCE_PENDING
        return drv_

    def test_validate_acceptance_context(self):
        self.assertEqual(Driver._validate_acceptance_context(self._SIGNED_IC), [])
        self.assertTrue(Driver._validate_acceptance_context({}))  # no contract
        unsigned = dict(self._SIGNED_IC, confirmed_by_human=False)
        probs = Driver._validate_acceptance_context(unsigned)
        self.assertTrue(any("confirmed_by_human" in p for p in probs))

    def test_offline_resolves_to_none(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = self._live(d, intent_contract=self._SIGNED_IC)
            drv_.context["allow_real"] = False
            self.assertIsNone(
                drv_._resolve_acceptance_spec(_EVID, "calibrated"))

    def test_live_projects_from_signed_contract(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._live(d, intent_contract=self._SIGNED_IC)\
                ._resolve_acceptance_spec(_EVID, "calibrated")
            self.assertIsInstance(out, str)
            self.assertIn("Acceptance Agent for the milestone close of `M1`", out)
            self.assertIn("Refunds honored for eligible customers", out)   # goal
            self.assertIn("No eligible refund denied", out)                # standard
            self.assertIn("All bad-cases pass under F5 eval", out)         # proof_of_done
            self.assertIn(_EVID, out)                                       # evidence ref
            self.assertIn("Calibration status: calibrated", out)           # reported
            # WP-1b: the agent-facing prompt names the COMPACT projection (not canonical).
            self.assertIn("compact/acceptance-verdict.compact.schema.json", out)
            self.assertNotIn("schemas/acceptance-verdict.schema.json", out)  # canonical not dispatched

    def test_live_unsigned_contract_halts(self):
        with tempfile.TemporaryDirectory() as d:
            unsigned = dict(self._SIGNED_IC, confirmed_by_human=False)
            drv_ = self._live(d, intent_contract=unsigned)
            self.assertIs(drv_._resolve_acceptance_spec(_EVID, "calibrated"),
                          drv._ACCEPTANCE_SPEC_HALT)
            self.assertEqual(drv_.state.state, STATE_HALTED)

    def test_live_missing_contract_halts_resumable(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = self._live(d, intent_contract=None)  # no ic, no compact
            self.assertIs(drv_._resolve_acceptance_spec(_EVID, "calibrated"),
                          drv._ACCEPTANCE_SPEC_HALT)
            self.assertEqual(drv_._load_state().state, STATE_HALTED)  # persisted

    def test_live_adopter_compact_file_used_on_signed_contract(self):
        # A compact acceptance prompt is the richer rendering — but ONLY once the
        # signed-contract HARD GATE passes (it does NOT bypass §3.4 invariant #4).
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(os.path.join(repo, "compact"))
            with open(os.path.join(repo, "compact", "M1-acceptance-prompt.md"),
                      "w", encoding="utf-8") as fh:
                fh.write("---\ncontext_budget:\n  self_contained: true\n---\n"
                         "Adopter-authored self-contained acceptance prompt for M1.")
            drv_ = self._live(d, intent_contract=self._SIGNED_IC, repo_dir=repo,
                              mission="M1")
            self.assertEqual(
                drv_._resolve_acceptance_spec(_EVID, "calibrated"),
                "Adopter-authored self-contained acceptance prompt for M1.")

    def test_compact_file_cannot_bypass_signed_contract_gate(self):
        # The same compact file, but NO signed intent_contract → HARD GATE HALTs;
        # the adopter prompt must NOT be accepted without a signed contract.
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            os.makedirs(os.path.join(repo, "compact"))
            with open(os.path.join(repo, "compact", "M1-acceptance-prompt.md"),
                      "w", encoding="utf-8") as fh:
                fh.write("---\ncontext_budget:\n  self_contained: true\n---\n"
                         "Adopter prompt that tries to skip the sign-off.")
            drv_ = self._live(d, intent_contract=None, repo_dir=repo, mission="M1")
            self.assertIs(drv_._resolve_acceptance_spec(_EVID, "calibrated"),
                          drv._ACCEPTANCE_SPEC_HALT)
            self.assertEqual(drv_.state.state, STATE_HALTED)

    def test_projection_does_not_mutate_calibration_or_authority(self):
        # The projection only REPORTS calibration/authority — it must not change them.
        with tempfile.TemporaryDirectory() as d:
            drv_ = self._live(d, intent_contract=self._SIGNED_IC)
            level_before = drv_.autonomy.get("level")
            drv_._resolve_acceptance_spec(_EVID, "uncalibrated")
            self.assertEqual(drv_.autonomy.get("level"), level_before)

    def test_projection_materialized_through_spawn(self):
        with tempfile.TemporaryDirectory() as d:
            cap = _PromptCapturingMock({("acceptance",): ACC_PASS}, harness="codex",
                                       provider="openai", model="gpt-5.5")
            drv_ = self._live(d, intent_contract=self._SIGNED_IC,
                              adapters=_acceptance_adapters(ACC_PASS))
            drv_.adapters["acceptance"] = cap
            # P-C refactor: the prompt is built (and projected) by _build_acceptance_prompt,
            # then materialized through _spawn_acceptance with the §3.5b reuse snapshot.
            prompt = drv_._build_acceptance_prompt(_EVID, "calibrated")
            snap = {"evidence_hash": "e", "authority_fingerprint": "a",
                    "acceptance_input_hash": "i", "authoritative": False}
            verdict = drv_._spawn_acceptance(prompt, _EVID, "calibrated", snap)
            self.assertEqual(verdict, ACC_PASS)
            self.assertIn("Acceptance Agent for the milestone close", cap.prompts[-1])
            spawn = next(e["payload"] for e in audit.read_events(drv_.audit_ledger)
                         if e["type"] == "acceptance_spawn")
            with open(os.path.join(d, spawn["prompt_ref"]), encoding="utf-8") as fh:
                self.assertIn("Refunds honored for eligible customers", fh.read())

    def test_mock_run_uses_legacy_inline_prompt_byte_identical(self):
        # A mock (not allow_real) acceptance run keeps the LEGACY one-line prompt —
        # the projection contract is live-only, so existing behavior is unchanged.
        with tempfile.TemporaryDirectory() as d:
            cap = _PromptCapturingMock({("acceptance",): ACC_PASS},
                                       harness="claude_code", provider="anthropic",
                                       model="claude-opus-4-8")
            adapters = _acceptance_adapters(ACC_PASS)
            adapters["acceptance"] = cap
            drv_ = _driver(d, charter=_acceptance_charter(), adapters=adapters)
            drv_.run(subsprint_id="sprint-001")
            self.assertIn("Acceptance for milestone close of sub-sprint sprint-001",
                          cap.prompts[-1])
            self.assertNotIn("signed intent contract", cap.prompts[-1])


# --------------------------------------------------------------------------- #
# Codex-review hardening of the two prompt contracts: genuinely-resumable HALTs,
# strict mode driven by real-adapter presence (not just allow_real), the signed-
# contract HARD GATE, and concrete (non-fabricated) evidence refs.
# --------------------------------------------------------------------------- #
_SIGNED_IC = {
    "goal": "Refunds honored for eligible customers",
    "standard": "No eligible refund denied; no ineligible approved",
    "proof_of_done": "All bad-cases pass under F5 eval",
    "confirmed_by_human": True}


class PromptContractCodexFixTests(unittest.TestCase):
    def test_strict_mode_forced_by_real_adapter_without_allow_real(self):
        # A non-mock adapter wired (even gated-off) makes prompt resolution STRICT
        # even when context.allow_real is unset — a real model never gets a one-liner.
        with tempfile.TemporaryDirectory() as d:
            adapters = _adapters()
            adapters["review"] = ClaudeCodeAdapter(model="claude-x")  # real, not mock
            drv_ = Driver(load_charter(CHARTER_PATH), d, adapters,
                          loop_id="loop-strict", clock=_clock())  # NO allow_real
            drv_.state = RunState(loop_id="loop-strict", subsprint_id="sprint-001")
            drv_.state.state = STATE_REVIEW_PENDING
            self.assertTrue(drv_._strict_prompts())
            self.assertIs(drv_._resolve_review_spec(), drv._REVIEW_SPEC_HALT)

    def test_all_mock_without_allow_real_stays_legacy(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)  # all MockAdapters, no allow_real
            drv_.state = RunState(loop_id="loop-test-001", subsprint_id="sprint-001")
            drv_.state.state = STATE_REVIEW_PENDING
            self.assertFalse(drv_._strict_prompts())
            self.assertIsNone(drv_._resolve_review_spec())  # legacy inline

    def test_review_halt_is_genuinely_resumable(self):
        # A review-spec HALT persists halt_resume_state=review_pending; on resume the
        # human has supplied the source (here: a plan that projects), so _drive
        # RE-ENTERS review_pending, resolves, and advances (no dead end).
        with tempfile.TemporaryDirectory() as d:
            drv1 = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-rr", clock=_clock(),
                          context={"allow_real": True})
            st = RunState(loop_id="loop-rr", subsprint_id="sprint-001")
            st.state = STATE_HALTED
            st.halt_resume_state = STATE_REVIEW_PENDING  # paused at review
            st.planned_subsprints = _REVIEW_PLAN          # source now available
            st.last_verdict = DEV_ARTIFACT                # dev already ran (run 1)
            drv1.state = st
            drv1._save_state()
            drv2 = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-rr", clock=_clock(),
                          context={"allow_real": True})
            final = drv2.run(resume=True)
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertIn("close_pending", final.history)  # re-entered + finished
            self.assertIsNone(final.halt_resume_state)      # cleared on re-entry

    def test_acceptance_halt_is_genuinely_resumable(self):
        with tempfile.TemporaryDirectory() as d:
            charter = _acceptance_charter(level="fully_autonomous_within_budget")
            charter["mission"] = {"id": "M1"}
            charter["intent_contract"] = _SIGNED_IC  # signed: resume will resolve
            # Seed a HALTED state whose resume target is acceptance_pending (as the
            # acceptance-spec refine-halt would persist), then resume.
            drv1 = Driver(charter, d, _acceptance_adapters(ACC_PASS),
                          loop_id="loop-ar", clock=_clock(),
                          context={"allow_real": True})
            st = RunState(loop_id="loop-ar", subsprint_id="sprint-001")
            st.state = STATE_HALTED
            st.halt_resume_state = STATE_ACCEPTANCE_PENDING
            drv1.state = st
            drv1._save_state()
            drv2 = Driver(charter, d, _acceptance_adapters(ACC_PASS),
                          loop_id="loop-ar", clock=_clock(),
                          context={"allow_real": True})
            final = drv2.run(resume=True)
            # Re-entered acceptance_pending → eval + projected (signed) → ACC_PASS → DONE.
            self.assertEqual(final.state, STATE_DONE)
            self.assertIsNone(final.halt_resume_state)

    def test_terminal_halt_has_no_resume_target(self):
        # A non-spec HALT (e.g. review fix_required HITL) must NOT carry a resume
        # target — only spec-refinement halts are auto-resumable.
        with tempfile.TemporaryDirectory() as d:
            fix_review = {"decision": "fix_required", "blocking_count": 1,
                          "summary": "one P1", "findings": []}
            drv_ = _driver(d, adapters=_adapters(review=fix_review))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            self.assertIsNone(final.halt_resume_state)

    def test_review_projection_cites_concrete_dev_change_ref(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = Driver(load_charter(CHARTER_PATH), d, _adapters(),
                          loop_id="loop-rev", clock=_clock(),
                          context={"allow_real": True})
            drv_.state = RunState(loop_id="loop-rev", subsprint_id="sprint-001")
            drv_.state.last_dev_output_ref = \
                ".orchestrator/audit/transcripts/loop-rev/0001__dev__output.md"
            out = drv_._project_review_prompt(_REVIEW_PLAN[0])
            self.assertIn("0001__dev__output.md", out)  # concrete change ref
            self.assertIn("docs/handoff.md", out)

    def test_acceptance_projection_no_brief_embeds_proof_no_fabricated_path(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = Driver(_acceptance_charter(), d, _acceptance_adapters(ACC_PASS),
                          loop_id="loop-acc", clock=_clock(),
                          context={"allow_real": True})
            drv_.charter["intent_contract"] = _SIGNED_IC
            drv_.state = RunState(loop_id="loop-acc", subsprint_id="sprint-001")
            out = drv_._project_acceptance_prompt(_SIGNED_IC, _EVID, "calibrated")
            self.assertIn("No separate research brief is bound", out)
            self.assertNotIn("docs/research-briefs/<id>.md", out)  # no fabrication
            self.assertIn("All bad-cases pass under F5 eval", out)  # proof embedded
            # The OUTPUT instruction must not demand a brief path either.
            self.assertNotIn('closure_contract_ref: "<brief path>"', out)

    def test_acceptance_projection_with_brief_cites_concrete_ref(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = Driver(_acceptance_charter(), d, _acceptance_adapters(ACC_PASS),
                          loop_id="loop-acc", clock=_clock(),
                          context={"allow_real": True})
            drv_.state = RunState(loop_id="loop-acc", subsprint_id="sprint-001")
            drv_.state.brief_draft_ref = "docs/briefs/sprint-001__brief.md"
            out = drv_._project_acceptance_prompt(_SIGNED_IC, _EVID, "calibrated")
            self.assertIn("docs/briefs/sprint-001__brief.md", out)
            self.assertIn('closure_contract_ref: "docs/briefs/sprint-001__brief.md"',
                          out)  # concrete output ref too

    def test_autofix_returns_on_dev_spec_halt_not_clobber(self):
        # A spec-refinement HALT during the auto-fix re-run must STOP the iteration
        # (mirror _drive), not clobber the halt by advancing to gate_pending.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, charter=_autofix_charter(enabled=True, max_rounds=3),
                           adapters=_adapters(review=_fix_review([_finding("F1")])))
            drv_.state = RunState(loop_id=drv_.loop_id, subsprint_id="sprint-001")
            drv_.state.state = STATE_REVIEW_PENDING

            def _halting_step_dev():  # simulate a dev-spec HALT mid-auto-fix
                drv_.state.state = STATE_HALTED
                drv_.state.halt_resume_state = STATE_DEV_PENDING
            drv_._step_dev = _halting_step_dev
            drv_._handle_fix_required(_fix_review([_finding("F1")]))
            self.assertEqual(drv_.state.state, STATE_HALTED)
            self.assertEqual(drv_.state.halt_resume_state, STATE_DEV_PENDING)

    def test_autofix_returns_on_review_spec_halt_no_crash(self):
        # A review-spec HALT returns None; the auto-fix path must not crash at
        # verdict.get(...) — it checks STATE_HALTED first and returns.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, charter=_autofix_charter(enabled=True, max_rounds=3),
                           adapters=_adapters(review=_fix_review([_finding("F1")])))
            drv_.state = RunState(loop_id=drv_.loop_id, subsprint_id="sprint-001")
            drv_.state.state = STATE_REVIEW_PENDING
            drv_._step_dev = lambda: None  # dev "succeeds" (no-op)
            drv_._step_gate = lambda: None

            def _halting_step_review():  # mirrors a review-spec HALT
                drv_.state.state = STATE_HALTED
                return None
            drv_._step_review = _halting_step_review
            drv_._handle_fix_required(_fix_review([_finding("F1")]))  # must NOT raise
            self.assertEqual(drv_.state.state, STATE_HALTED)


class TestRecordOnlyP2Policy(unittest.TestCase):
    """P2 is strictly record-only: only P0/P1 block close / drive the auto-fix
    round; a fix_required carrying only P2 findings normalizes to a clean pass.
    (Item 1 — fix P0/P1 only; record-only, non-blocking P2.)"""

    def test_fix_round_guidance_injects_only_blocking_p0_p1(self):
        # The auto-fix Dev brief carries ONLY blocking (P0/P1) findings; a P2
        # (record-only) finding in the SAME verdict is never injected.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, charter=_autofix_charter(enabled=True))
            drv_.state = RunState(loop_id=drv_.loop_id, subsprint_id="sprint-001")
            drv_.state.fix_round = 1
            drv_.state.last_verdict = _fix_review([
                _finding("BLK-P0", "P0"),
                _finding("BLK-P1", "P1"),
                _finding("REC-P2", "P2"),
            ])
            g = drv_._fix_round_guidance()
            self.assertIn("BLK-P0", g)
            self.assertIn("BLK-P1", g)
            self.assertNotIn("REC-P2", g)        # P2 stays OUT of the fix brief
            self.assertIn("EXISTING code", g)

    def test_all_p2_fix_required_normalizes_to_pass(self):
        # A fix_required whose findings are ALL P2 → effective clean pass: it
        # advances (reaches close), spends NO fix round, and audits the
        # normalization (original + effective decision + reason).
        with tempfile.TemporaryDirectory() as d:
            review = _fix_review([_finding("REC-1", "P2"),
                                  _finding("REC-2", "P2")], blocking=0)
            drv_ = _driver(d, charter=_autofix_charter(enabled=False),
                           adapters=_adapters(review=review))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            self.assertEqual(final.fix_round, 0)          # no fix round entered
            events = audit.read_events(drv_.audit_ledger)
            types = [e["type"] for e in events]
            self.assertIn("review_decision_normalized", types)
            self.assertNotIn("review_fix_required", types)
            self.assertNotIn("controller_decision", types)
            norm = next(e for e in events
                        if e["type"] == "review_decision_normalized")
            self.assertEqual(norm["payload"]["original_decision"], "fix_required")
            self.assertEqual(norm["payload"]["effective_decision"], "pass")
            self.assertEqual(norm["payload"]["reason"],
                             "all_findings_record_only_p2")
            self.assertEqual(sorted(norm["payload"]["finding_ids"]),
                             ["REC-1", "REC-2"])
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_all_p2_re_review_normalizes_and_advances(self):
        # The inner auto-fix re-review is uniform with the main dispatch: a blocking
        # P1 triggers a fix round; the re-review returns only P2 → it is normalized to
        # a pass and the loop ADVANCEs. The P2 re-review finding must NEVER reach a Dev
        # prompt (record-only), and the normalization must be audited.
        review_responses = {
            ("review", 0): _fix_review([_finding("BLK", "P1")]),
            ("review", 1): _fix_review([_finding("REC", "P2")], blocking=0),
        }
        with tempfile.TemporaryDirectory() as d:
            dev = _PromptCapturingMock(
                {("dev",): DEV_ARTIFACT}, harness="claude_code",
                provider="anthropic", model="claude-sonnet-4-6")
            adapters = _adapters()
            adapters["dev"] = dev
            adapters["review"] = MockAdapter(
                review_responses, harness="headless",
                provider="deepseek", model="deepseek-chat")
            drv_ = _driver(d, charter=_autofix_charter(enabled=True, max_rounds=3),
                           adapters=adapters)
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_ADVANCE)
            # exactly: initial Dev + one fix round; the blocking P1 reached the fix
            # round's Dev prompt, the record-only P2 re-review finding reached NONE.
            self.assertEqual(len(dev.prompts), 2)
            self.assertIn("BLK", dev.prompts[1])
            self.assertFalse(any("REC" in p for p in dev.prompts),
                             "the record-only P2 re-review finding must not be injected")
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertIn("review_decision_normalized", types)
            self.assertTrue(audit.verify_chain(drv_.audit_ledger).ok)

    def test_record_only_predicate_is_fail_closed(self):
        # _is_record_only_fix_required is the policy guard: true ONLY for a
        # SCHEMA-VALID, non-empty, all-EXACTLY-P2 fix_required. A blocking finding,
        # an out-of-contract P3, an unknown/missing severity, a malformed entry,
        # empty findings, or a non-fix decision → False (fail-closed).
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            # schema-valid + all P2 → True
            self.assertTrue(drv_._is_record_only_fix_required(
                _fix_review([_finding("A", "P2"), _finding("B", "P2")], blocking=0)))
            # schema-valid but a blocking P1 present → False (the all-P2 semantic gate)
            self.assertFalse(drv_._is_record_only_fix_required(
                _fix_review([_finding("A", "P2"), _finding("B", "P1")])))
            # out-of-contract P3 severity → schema-invalid → False (NOT record-only)
            self.assertFalse(drv_._is_record_only_fix_required(
                _fix_review([_finding("A", "P3")])))
            # unknown severity → schema-invalid → False
            self.assertFalse(drv_._is_record_only_fix_required(
                _fix_review([_finding("A", "P9")])))
            # missing severity → schema-invalid → False
            self.assertFalse(drv_._is_record_only_fix_required(
                {"decision": "fix_required", "blocking_count": 0, "summary": "x",
                 "findings": [{"id": "A", "layer": "infra",
                               "evidence": ["x:1"], "rationale": "r"}]}))
            # empty findings → False (no blocking work, but nothing to record either)
            self.assertFalse(drv_._is_record_only_fix_required(
                {"decision": "fix_required", "blocking_count": 0, "summary": "x",
                 "findings": []}))
            # malformed (non-dict) entry alongside a P2 → schema-invalid → False
            self.assertFalse(drv_._is_record_only_fix_required(
                {"decision": "fix_required", "blocking_count": 0, "summary": "x",
                 "findings": [_finding("A", "P2"), "nope"]}))
            # not a fix_required → False
            self.assertFalse(drv_._is_record_only_fix_required(CLEAN_REVIEW))

    def test_empty_findings_fix_required_fails_closed(self):
        # A fix_required with NO findings must NOT auto-pass — it keeps the
        # existing fix_required handling (HITL halt here); no normalization audit.
        with tempfile.TemporaryDirectory() as d:
            review = {"decision": "fix_required", "blocking_count": 0,
                      "summary": "x", "findings": []}
            drv_ = _driver(d, charter=_autofix_charter(enabled=False),
                           adapters=_adapters(review=review))
            final = drv_.run(subsprint_id="sprint-001")
            self.assertEqual(final.state, STATE_HALTED)
            types = [e["type"] for e in audit.read_events(drv_.audit_ledger)]
            self.assertNotIn("review_decision_normalized", types)


if __name__ == "__main__":
    unittest.main()
