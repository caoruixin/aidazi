#!/usr/bin/env python3
"""Phase-2 requirement-driven chain — production-path tests for the
`--requirement` entrypoint (design archive/2026-07-09-phase2-requirement-chain-
design.md §2-§4, Commit B).

These drive the REAL path run_requirement_entry -> Driver.run_campaign_bootstrap
(offline MockAdapters via build_adapters' campaign_bootstrap canned verdicts),
exercising: preflights 0a/0c, the gate-1 halt -> identity-bound decision-file
sign -> resume -> plan emission with FILLED subsprint_sequence [R0 B-1], compact
prompt materialization + collision refusal, the emitted plan signing clean
(signoff_status 'signed') and running under the MOCK campaign runner with ZERO
milestone_decompose_required pauses, plus pure-function coverage of the
projection (OW-AUTO browser_e2e forcing) and the early sign-stack.

Run as a script: cd engine-kit && python3.12 scheduling/tests/test_run_loop_requirement.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHED_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_SCHED_DIR)
for _p in (_SCHED_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator"),
           os.path.join(_ENGINE_KIT_DIR, "orchestrator", "tests"),
           os.path.join(_ENGINE_KIT_DIR, "validators")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import yaml  # noqa: E402
import campaign as cp  # noqa: E402
import run_loop as rl  # noqa: E402
from driver import load_charter  # noqa: E402
from test_driver import CHARTER_PATH, _sign_resolver  # noqa: E402

REQUIREMENT_TEXT = "# REQ\nDetermine refund eligibility end-to-end.\n"


def _charter_dict():
    """The p2 demo charter + a SIGNED intent contract (preflight 0a) — the
    envelope (modules/layers) is already non-empty in the demo charter."""
    charter = load_charter(CHARTER_PATH)
    charter["intent_contract"] = {
        "goal": "refund eligibility works",
        "standard": "demo bad-cases all pass",
        "proof_of_done": "eval output shows every bad-case passing",
        "confirmed_by_human": True,
    }
    charter["autonomy"]["approved_scope"]["subsprint_sequence"] = []
    return charter


class _Env:
    """One disposable bootstrap environment: repo dir + requirement file +
    charter yaml + output path."""

    def __init__(self, td, charter=None):
        self.repo = os.path.join(td, "repo")
        os.makedirs(os.path.join(self.repo, "compact"), exist_ok=True)
        # A real (tiny) git repo: the campaign runner's Loop Ingress reads HEAD.
        import subprocess
        for cmd in (["git", "init", "-q"],
                    ["git", "-c", "user.name=t", "-c", "user.email=t@t",
                     "commit", "-q", "--allow-empty", "-m", "init"]):
            subprocess.run(["git", "-C", self.repo, *cmd[1:]] if cmd[0] == "git"
                           else cmd, check=True, capture_output=True)
        self.requirement = os.path.join(td, "req-refund.md")
        with open(self.requirement, "w", encoding="utf-8") as fh:
            fh.write(REQUIREMENT_TEXT)
        self.charter_path = os.path.join(td, "charter.yaml")
        with open(self.charter_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(charter or _charter_dict(), fh, allow_unicode=True)
        self.out = os.path.join(td, "campaign-plan.json")
        self.run_dir = os.path.join(td, "bootstrap-run")

    def entry_kwargs(self, **over):
        kw = dict(requirement_path=self.requirement,
                  charter_path=self.charter_path, repo_dir=self.repo,
                  campaign_out=self.out, run_dir=self.run_dir)
        kw.update(over)
        return kw

    def main_args(self, *extra):
        return ["--charter", self.charter_path, "--requirement",
                self.requirement, "--repo-dir", self.repo,
                "--campaign-out", self.out, "--run-dir", self.run_dir,
                *extra]


def _run_entry(env, **over):
    charter = load_charter(env.charter_path)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rl.run_requirement_entry(charter, **env.entry_kwargs(**over))
    return rc, buf.getvalue()


def _run_main(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rl.main(args)
    return rc, buf.getvalue()


class TestPreflights(unittest.TestCase):
    def test_missing_repo_dir_rc2(self):
        with tempfile.TemporaryDirectory() as td:
            env = _Env(td)
            rc, out = _run_entry(env, repo_dir=None)
            self.assertEqual(rc, 2)
            self.assertIn("--repo-dir is REQUIRED", out)

    def test_missing_campaign_out_rc2(self):
        with tempfile.TemporaryDirectory() as td:
            env = _Env(td)
            rc, out = _run_entry(env, campaign_out=None)
            self.assertEqual(rc, 2)
            self.assertIn("--campaign-out is REQUIRED", out)

    def test_unsigned_intent_contract_rc2(self):
        with tempfile.TemporaryDirectory() as td:
            charter = _charter_dict()
            charter["intent_contract"]["confirmed_by_human"] = False
            env = _Env(td, charter=charter)
            rc, out = _run_entry(env)
            self.assertEqual(rc, 2)
            self.assertIn("intent_contract", out)
            self.assertIn("confirmed_by_human", out)

    def test_requirement_and_campaign_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            env = _Env(td)
            rc, out = _run_main(env.main_args("--campaign", env.out))
            self.assertEqual(rc, 2)
            self.assertIn("mutually exclusive", out)

    def test_broken_ledger_rc2(self):
        with tempfile.TemporaryDirectory() as td:
            env = _Env(td)
            os.makedirs(os.path.join(env.repo, "docs"), exist_ok=True)
            with open(os.path.join(env.repo, "docs",
                                   "requirements-ledger.json"), "w") as fh:
                fh.write("{not json")
            rc, out = _run_entry(env)
            self.assertEqual(rc, 2)
            self.assertIn("REFUSED", out)


class TestRequirementChain(unittest.TestCase):
    def test_gate1_halt_then_decision_sign_resume_emits_plan(self):
        with tempfile.TemporaryDirectory() as td:
            env = _Env(td)
            # Run 1 (non-interactive, no decision): halts at gate-1, rc 10.
            rc, out = _run_main(env.main_args())
            self.assertEqual(rc, 10)
            self.assertIn("PAUSED", out)
            self.assertFalse(os.path.exists(env.out))
            cp_dir = os.path.join(env.run_dir, "docs", "checkpoints")
            live = sorted(f for f in os.listdir(cp_dir)
                          if "__customer_gate1_signoff__" in f)
            self.assertTrue(live)
            # Identity-bound decision file [R0 N-4][R0.2 N-1]: WRONG campaign_id
            # is refused (still rc 10, no sign) …
            decision = os.path.join(td, "decision.json")
            with open(decision, "w", encoding="utf-8") as fh:
                json.dump({"campaign_id": "someone-else",
                           "pause_reason": "customer_gate1_signoff",
                           "checkpoint": live[-1], "choice": "sign"}, fh)
            rc, out = _run_main(env.main_args("--resume",
                                              "--decision", decision))
            self.assertEqual(rc, 10)
            self.assertIn("REFUSED", out)
            self.assertFalse(os.path.exists(env.out))
            # … the CORRECT binding signs; resume completes and emits.
            with open(decision, "w", encoding="utf-8") as fh:
                json.dump({"campaign_id": "req-refund",
                           "pause_reason": "customer_gate1_signoff",
                           "checkpoint": live[-1], "choice": "sign"}, fh)
            rc, out = _run_main(env.main_args("--resume",
                                              "--decision", decision))
            self.assertEqual(rc, 0, out)
            self.assertIn("plan emitted", out)
            self.assertIn(f"--repo-dir {env.repo}", out)  # [R0.3 B-1]
            plan = json.load(open(env.out, encoding="utf-8"))
            self.assertEqual(plan["campaign_id"], "req-refund")
            # [R0 B-1] every milestone ships a FILLED subsprint_sequence.
            for m in plan["milestones"]:
                self.assertTrue(m["subsprint_sequence"])
            # Sidecar + compact files exist; compacts are valid compact sources.
            self.assertTrue(os.path.exists(
                env.out + ".decompose-verdict.json"))
            dev = os.path.join(env.repo, "compact", "m1-s1-dev-prompt.md")
            rev = os.path.join(env.repo, "compact", "m1-s1-review-prompt.md")
            for p in (dev, rev):
                text = open(p, encoding="utf-8").read()
                self.assertTrue(text.startswith("---"))
                self.assertIn("self_contained: true", text)
            self.assertIn("dry-run sub-sprint", open(dev, encoding="utf-8").read())

    def test_emitted_plan_signs_clean_and_runs_without_decompose_pause(self):
        with tempfile.TemporaryDirectory() as td:
            env = _Env(td)
            rc, out = _run_entry(env, gate_resolver=_sign_resolver())
            self.assertEqual(rc, 0, out)
            # (1) the emitted plan SIGNS clean ('never show an unsignable plan').
            rc, out = _run_main(["--charter", env.charter_path,
                                 "--campaign", env.out,
                                 "--repo-dir", env.repo, "--sign-plan"])
            self.assertEqual(rc, 0, out)
            signed = json.load(open(env.out, encoding="utf-8"))
            charter = load_charter(env.charter_path)
            self.assertEqual(cp.signoff_status(signed, charter, None), "signed")
            # (2) [R0 B-1 regression] the SIGNED plan runs under the MOCK
            # campaign runner with ZERO milestone_decompose_required pauses.
            home = os.path.join(td, "campaign-home")
            rc, out = _run_main(["--charter", env.charter_path,
                                 "--campaign", env.out,
                                 "--campaign-run-dir", home,
                                 "--repo-dir", env.repo, "--resume"])
            self.assertNotIn("milestone_decompose_required", out)
            state = json.load(open(os.path.join(home, "campaign-state.json"),
                                   encoding="utf-8"))
            self.assertNotEqual(state.get("pause_reason"),
                                "milestone_decompose_required")

    def test_compact_collision_refuses_and_emits_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            env = _Env(td)
            pre = os.path.join(env.repo, "compact", "m1-s1-dev-prompt.md")
            with open(pre, "w", encoding="utf-8") as fh:
                fh.write("adopter-authored — must never be overwritten")
            rc, out = _run_entry(env, gate_resolver=_sign_resolver())
            self.assertEqual(rc, 10)
            self.assertIn("already exists", out)
            self.assertFalse(os.path.exists(env.out))
            self.assertEqual(
                open(pre, encoding="utf-8").read(),
                "adopter-authored — must never be overwritten")
            cp_dir = os.path.join(env.run_dir, "docs", "checkpoints")
            self.assertTrue(any("campaign_decompose_refusal" in f
                                for f in os.listdir(cp_dir)))


class TestProjectionAndSignStack(unittest.TestCase):
    STAGE1 = {"goal": "g", "milestones": [
        {"id": "m1", "objective": "o1", "acceptance_bar": "b1",
         "modules": ["src"], "layers": ["infra"],
         "covers_req_ids": ["REQ-1"]},
        {"id": "m2", "objective": "o2", "acceptance_bar": "b2",
         "modules": ["src"], "layers": ["infra"], "depends_on": ["m1"]},
    ]}
    STAGE2 = {"m1": {"sub_sprints": [{"id": "m1-s1"}]},
              "m2": {"sub_sprints": [{"id": "m2-s1"}, {"id": "m2-s2"}]}}

    def test_projection_fills_sequences_and_forces_browser_e2e(self):
        ledger = {"version": "v1", "requirements": [
            {"id": "REQ-1", "surface": "user_facing"}]}
        plan = rl._project_campaign_plan(self.STAGE1, self.STAGE2, "cid",
                                         ledger)
        self.assertEqual(plan["milestones"][0]["subsprint_sequence"],
                         ["m1-s1"])
        self.assertEqual(plan["milestones"][1]["subsprint_sequence"],
                         ["m2-s1", "m2-s2"])
        # OW-AUTO: user_facing coverage forces browser_e2e (PR#7 semantics).
        self.assertEqual(plan["milestones"][0]["functional_acceptance"],
                         "browser_e2e")
        self.assertNotIn("functional_acceptance", plan["milestones"][1])
        self.assertEqual(plan["milestones"][1]["depends_on"], ["m1"])

    def test_sign_stack_catches_duplicate_rids_and_cycles(self):
        charter = _charter_dict()
        plan = {"campaign_id": "cid", "goal": "g",
                "delivery_mode": "campaign", "milestones": [
                    {"id": "m1", "objective": "o",
                     "covers_req_ids": ["REQ-1"],
                     "subsprint_sequence": ["s1"], "depends_on": ["m2"]},
                    {"id": "m2", "objective": "o",
                     "covers_req_ids": ["REQ-1"],
                     "subsprint_sequence": ["s2"], "depends_on": ["m1"]}]}
        reasons = rl._bootstrap_plan_violations(plan, charter, None)
        joined = "\n".join(reasons)
        self.assertIn("REQ-1", joined)          # cross-milestone dup claim
        self.assertIn("DAG invalid", joined)    # m1 <-> m2 cycle

    def test_sign_stack_ow_m3_unclassified_refuses(self):
        charter = _charter_dict()
        ledger = {"version": "v1", "requirements": [{"id": "REQ-9"}]}
        plan = {"campaign_id": "cid", "goal": "g",
                "delivery_mode": "campaign", "milestones": [
                    {"id": "m1", "objective": "o",
                     "covers_req_ids": ["REQ-9"],
                     "subsprint_sequence": ["s1"]}]}
        reasons = rl._bootstrap_plan_violations(plan, charter, ledger)
        self.assertTrue(any("OW-M3" in r or "browser-E2E" in r
                            for r in reasons), reasons)


if __name__ == "__main__":
    unittest.main()
