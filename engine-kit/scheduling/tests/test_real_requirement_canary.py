"""ENV-GATED real requirement-chain canary — Phase-2's end-to-end real proof.

Drives the PRODUCTION ``run_loop.py --requirement`` CLI contract with REAL
claude_code spawns over a scratch git repo seeded from
``examples/real-requirement-canary/``:

  requirement file → rc 10 at gate-1 (real Research drafted + materialized the
  brief) → identity-bound decision-file sign → --resume rc 0: real two-stage
  Deliver decompose, plan EMITTED with filled subsprint_sequences + generated
  compact prompts + sidecar → --sign-plan rc 0 (prompt_artifacts_digest bound)
  → the real campaign: FIRST pause is advisory_acceptance_pass_signoff (any
  earlier pause = canary FAILURE), ship per milestone → done.

DOUBLE GATE (billed real agent turns; standing user rule — every real-CLI
activity is env-gated): the module skips unless ``AIDAZI_E2E_REAL_REQUIREMENT=1``
AND the ``claude`` CLI is on PATH. ``AIDAZI_ALLOW_REAL_ADAPTER=1`` is exported
into the CHILD CLI environment only — never into this test process.

Assertions are FLOW-invariants only (exit codes, pause reasons, file bytes,
audit-event counts, no agent-stuck diagnostics); model prose is never asserted.
The milestone COUNT is model-decided (the requirement nudges 2) — the ship loop
is dynamic and every pause must be the advisory sign-off.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHED_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_SCHED_DIR)
_REPO_ROOT = os.path.dirname(_ENGINE_KIT_DIR)
for _p in (_SCHED_DIR, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402

_GATE = "AIDAZI_E2E_REAL_REQUIREMENT"
_RUN_LOOP = os.path.join(_SCHED_DIR, "run_loop.py")
_CANARY = os.path.join(_REPO_ROOT, "examples", "real-requirement-canary")
_CID = "real-requirement-canary"
_STEP_TIMEOUT = 2400


def _skip_reason():
    if os.environ.get(_GATE) != "1":
        return (f"real requirement canary (billed claude_code spawns) — opt in "
                f"with {_GATE}=1")
    if not shutil.which("claude"):
        return "claude CLI not on PATH"
    return None


def _parse_status(stdout: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith("CAMPAIGN_STATUS="):
            return json.loads(line[len("CAMPAIGN_STATUS="):])
    raise AssertionError("no CAMPAIGN_STATUS line in output:\n" + stdout[-4000:])


@unittest.skipUnless(_skip_reason() is None, _skip_reason() or "")
class RealRequirementCanaryTests(unittest.TestCase):
    """One ordered scenario — requirement file to delivered campaign."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="real-requirement-canary-")
        cls.ws = os.path.join(cls.tmp, "workspace")
        shutil.copytree(os.path.join(_CANARY, "workspace"), cls.ws)
        cls._git("init", "-q")
        cls._git("add", "-A")
        cls._git("-c", "user.name=canary", "-c", "user.email=c@localhost",
                 "commit", "-qm", "canary seed", "--allow-empty")
        cls.charter = os.path.join(cls.tmp, "charter.yaml")
        shutil.copy(os.path.join(_CANARY, "charter.yaml"), cls.charter)
        cls.requirement = os.path.join(cls.tmp, "requirement.md")
        shutil.copy(os.path.join(_CANARY, "requirement.md"), cls.requirement)
        cls.plan = os.path.join(cls.tmp, "campaign-plan.json")
        # The bootstrap run dir MUST live INSIDE the workspace (the default
        # <repo>/.runs/... derivation): the real claude_code agents' sandbox
        # restricts reads to the session working directory (= the repo), so the
        # brief + requirement snapshot are unreadable anywhere else — round 3
        # proved a sibling tmp dir makes the Stage-1 Deliver blind. Unit-diff
        # hygiene is covered by the review prompts' engine-artifact exclusion
        # (`.runs/` is named there) + the pre-campaign commit below.
        cls.boot = os.path.join(cls.ws, ".runs", f"campaign-bootstrap-{_CID}")
        cls.home = os.path.join(cls.tmp, "campaign-home")

    @classmethod
    def _git(cls, *args):
        subprocess.run(["git", "-C", cls.ws, *args], check=True,
                       capture_output=True)

    def _cli(self, *args):
        env = dict(os.environ)
        env["AIDAZI_ALLOW_REAL_ADAPTER"] = "1"  # child env ONLY
        proc = subprocess.run(
            [sys.executable, _RUN_LOOP, "--charter", self.charter, *args],
            cwd=self.ws, env=env, capture_output=True, text=True,
            timeout=_STEP_TIMEOUT)
        print(f"\n--- CLI rc={proc.returncode} args={args[:2]}... ---")
        for line in proc.stdout.splitlines():
            if (line.startswith(("CAMPAIGN_STATUS=", "campaign bootstrap",
                                 "--sign-plan", "=== campaign"))
                    or "PAUSED" in line):
                print(line[:400])
        return proc

    def _requirement_args(self, *extra):
        # NO --run-dir override: the default <repo>/.runs/campaign-bootstrap-<cid>
        # keeps the brief + requirement snapshot inside the agents' readable root.
        return ("--requirement", self.requirement, "--campaign-out", self.plan,
                "--campaign-id", _CID,
                "--repo-dir", self.ws, "--allow-real", *extra)

    def _campaign_args(self, *extra):
        return ("--campaign", self.plan, "--campaign-run-dir", self.home,
                "--repo-dir", self.ws, "--allow-real", *extra)

    def _hello(self):
        path = os.path.join(self.ws, "notes", "hello.md")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def _ship(self, status, path):
        cpt = status.get("pause_checkpoint")
        dec = {"campaign_id": status.get("campaign_id"),
               "pause_reason": status.get("pause_reason"),
               "checkpoint": os.path.basename(cpt) if cpt else None,
               "choice": "ship", "note": "requirement canary verified"}
        if status.get("pause_milestone_id"):
            dec["milestone_id"] = status["pause_milestone_id"]
        if status.get("pause_subsprint_id"):
            dec["subsprint_id"] = status["pause_subsprint_id"]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(dec, fh)
        return path

    def _unit_event_types(self):
        types = []
        units = os.path.join(self.home, "units")
        if not os.path.isdir(units):
            return types
        for root, _dirs, fnames in os.walk(units):
            for fn in fnames:
                if fn.endswith(".jsonl"):
                    types += [e["type"]
                              for e in audit.read_events(os.path.join(root, fn))]
        return types

    def test_full_real_requirement_chain(self):
        # ---- step 1: requirement in → REAL research → gate-1 halt rc 10 --- #
        p1 = self._cli(*self._requirement_args())
        self.assertEqual(p1.returncode, 10, p1.stdout[-4000:] + p1.stderr[-4000:])
        cp_dir = os.path.join(self.boot, "docs", "checkpoints")
        live = sorted(f for f in os.listdir(cp_dir)
                      if "__customer_gate1_signoff__" in f)
        self.assertTrue(live, "no gate-1 checkpoint written")
        briefs = os.path.join(self.boot, "docs", "briefs")
        self.assertTrue(os.path.isdir(briefs) and os.listdir(briefs),
                        "the REAL research brief was not materialized")

        # ---- step 2: identity-bound sign → resume → plan EMITTED rc 0 ----- #
        dec_g1 = os.path.join(self.tmp, "gate1-decision.json")
        with open(dec_g1, "w", encoding="utf-8") as fh:
            json.dump({"campaign_id": _CID,
                       "pause_reason": "customer_gate1_signoff",
                       "checkpoint": live[-1], "choice": "sign",
                       "note": "canary author signs the brief + envelope"}, fh)
        p2 = self._cli(*self._requirement_args("--resume",
                                               "--decision", dec_g1))
        self.assertEqual(p2.returncode, 0, p2.stdout[-4000:] + p2.stderr[-4000:])
        with open(self.plan, encoding="utf-8") as fh:
            plan = json.load(fh)
        self.assertTrue(plan["milestones"])
        for m in plan["milestones"]:
            self.assertTrue(m.get("subsprint_sequence"),
                            f"milestone {m['id']} has no sub-sprints [R0 B-1]")
            for sid in m["subsprint_sequence"]:
                for kind in ("dev", "review"):
                    path = os.path.join(self.ws, "compact",
                                        f"{sid}-{kind}-prompt.md")
                    self.assertTrue(os.path.isfile(path),
                                    f"generated compact missing: {path}")
        self.assertTrue(os.path.isfile(
            self.plan + ".decompose-verdict.json"))
        # Commit the generated compacts so unit diffs carry ONLY Dev's work.
        self._git("add", "-A")
        self._git("-c", "user.name=canary", "-c", "user.email=c@localhost",
                  "commit", "-qm", "bootstrap-generated compact prompts")

        # ---- step 3: F1 sign — the digest binds the generated prompts ---- #
        p3 = self._cli("--campaign", self.plan, "--repo-dir", self.ws,
                       "--sign-plan")
        self.assertEqual(p3.returncode, 0, p3.stdout + p3.stderr)
        with open(self.plan, encoding="utf-8") as fh:
            signed = json.load(fh)
        self.assertIn("signoff", signed)
        self.assertIn("prompt_artifacts_digest", signed["signoff"])

        # ---- step 4+: the REAL campaign — advisory pauses ONLY ------------ #
        milestones_total = len(signed["milestones"])
        p = self._cli(*self._campaign_args())
        ships = 0
        while p.returncode == 10 and ships <= milestones_total + 1:
            s = _parse_status(p.stdout)
            # THE Phase-2 proof: the ONLY pause a clean requirement-start run
            # ever hits is the per-milestone advisory sign-off.
            self.assertEqual(
                s["pause_reason"], "advisory_acceptance_pass_signoff",
                f"non-advisory pause {s['pause_reason']!r}:\n"
                + p.stdout[-4000:])
            ships += 1
            dec = self._ship(s, os.path.join(self.tmp, f"ship-{ships}.json"))
            p = self._cli(*self._campaign_args("--resume", "--decision", dec))
        self.assertEqual(p.returncode, 0, p.stdout[-4000:] + p.stderr[-4000:])
        s_final = _parse_status(p.stdout)
        self.assertEqual(s_final["status"], "done")
        self.assertEqual(s_final["milestones_total"], milestones_total)
        self.assertEqual(ships, milestones_total,
                         "one advisory ship per milestone")

        # ---- the delivered artifact is byte-exact to the REQUIREMENT ------ #
        hello = self._hello()
        self.assertIsNotNone(hello, "notes/hello.md was not delivered")
        self.assertEqual([ln for ln in hello.splitlines() if ln.strip()],
                         ["HELLO-REQ-M1", "HELLO-REQ-M2"])

        # ---- flow invariants over the whole run --------------------------- #
        types = self._unit_event_types()
        self.assertEqual(types.count("acceptance_start"), milestones_total,
                         "exactly one Acceptance per milestone")
        diag = os.path.join(self.ws, ".orchestrator", "diagnostics",
                            "agent-stuck")
        self.assertFalse(
            os.path.isdir(diag) and os.listdir(diag),
            f"agent-stuck diagnostics recorded: {diag}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
