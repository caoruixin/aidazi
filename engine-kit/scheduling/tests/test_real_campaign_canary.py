"""ENV-GATED real campaign canary — the first end-to-end real-adapter proof.

Drives the PRODUCTION ``run_loop.py --campaign`` CLI contract with REAL
claude_code spawns (Dev / Review / Deliver / Acceptance) over a scratch copy of
``examples/real-campaign-canary/``: sign → run → advisory pause (m1) → ship
decision → resume → advisory pause (m2) → ship → done (rc 0/10/10/0).

DOUBLE GATE (billed real agent turns; user rule — every real-CLI activity is
env-gated): the whole module skips unless ``AIDAZI_E2E_REAL_CAMPAIGN=1`` AND
the ``claude`` CLI is on PATH. ``AIDAZI_ALLOW_REAL_ADAPTER=1`` is exported
into the CHILD CLI environment only — never into this test process.

Assertions are FLOW-invariants only (exit codes, pause reasons, workspace file
bytes, audit-event counts, no agent-stuck diagnostics); model prose is never
asserted. Any refinement halt before advisory_acceptance_pass_signoff is a
canary FAILURE (R0 B-4), surfaced by the pause_reason assertion.
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

_GATE = "AIDAZI_E2E_REAL_CAMPAIGN"
_RUN_LOOP = os.path.join(_SCHED_DIR, "run_loop.py")
_CANARY = os.path.join(_REPO_ROOT, "examples", "real-campaign-canary")
_STEP_TIMEOUT = 2400  # hard bound per CLI step (a unit = up to 4 real spawns)


def _skip_reason():
    if os.environ.get(_GATE) != "1":
        return (f"real campaign canary (billed claude_code spawns) — opt in "
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
class RealCampaignCanaryTests(unittest.TestCase):
    """One ordered scenario — the 4-step CLI contract over real spawns."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="real-campaign-canary-")
        cls.ws = os.path.join(cls.tmp, "workspace")
        shutil.copytree(os.path.join(_CANARY, "workspace"), cls.ws)
        subprocess.run(["git", "init", "-q"], cwd=cls.ws, check=True)
        subprocess.run(["git", "add", "-A"], cwd=cls.ws, check=True)
        subprocess.run(
            ["git", "-c", "user.name=canary", "-c", "user.email=c@localhost",
             "commit", "-qm", "canary seed"], cwd=cls.ws, check=True)
        cls.charter = os.path.join(cls.tmp, "charter.yaml")
        cls.plan = os.path.join(cls.tmp, "campaign-plan.json")
        shutil.copy(os.path.join(_CANARY, "charter.yaml"), cls.charter)
        shutil.copy(os.path.join(_CANARY, "campaign-plan.json"), cls.plan)
        cls.home = os.path.join(cls.tmp, "campaign-home")

    def _cli(self, *args):
        env = dict(os.environ)
        env["AIDAZI_ALLOW_REAL_ADAPTER"] = "1"  # child env ONLY
        proc = subprocess.run(
            [sys.executable, _RUN_LOOP, "--charter", self.charter, *args],
            cwd=self.ws, env=env, capture_output=True, text=True,
            timeout=_STEP_TIMEOUT)
        print(f"\n--- CLI rc={proc.returncode} args={args[:3]}... ---")
        for line in proc.stdout.splitlines():
            if line.startswith("CAMPAIGN_STATUS=") or "sign-plan" in line:
                print(line[:400])
        return proc

    def _campaign_args(self, *extra):
        return ("--campaign", self.plan, "--campaign-run-dir", self.home,
                "--repo-dir", self.ws, "--allow-real", *extra)

    def _hello(self):
        path = os.path.join(self.ws, "notes", "hello.md")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def _decision(self, status, path, **fields):
        cpt = status.get("pause_checkpoint")
        dec = {"campaign_id": status.get("campaign_id"),
               "pause_reason": status.get("pause_reason"),
               "checkpoint": os.path.basename(cpt) if cpt else None}
        if status.get("pause_milestone_id"):
            dec["milestone_id"] = status["pause_milestone_id"]
        if status.get("pause_subsprint_id"):
            dec["subsprint_id"] = status["pause_subsprint_id"]
        dec.update(fields)
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

    def test_full_real_contract(self):
        # ---- step 1: F1 sign the plan ------------------------------------ #
        p1 = self._cli("--campaign", self.plan, "--sign-plan",
                       "--repo-dir", self.ws)
        self.assertEqual(p1.returncode, 0, p1.stdout + p1.stderr)
        with open(self.plan, encoding="utf-8") as fh:
            self.assertIn("signoff", json.load(fh))

        # ---- step 2: REAL run → advisory pause at m1 --------------------- #
        p2 = self._cli(*self._campaign_args())
        self.assertEqual(p2.returncode, 10, p2.stdout[-4000:] + p2.stderr[-4000:])
        s2 = _parse_status(p2.stdout)
        # R0 B-4: ANY earlier refinement halt is a canary FAILURE — this
        # assertion is the enforcement.
        self.assertEqual(s2["pause_reason"], "advisory_acceptance_pass_signoff")
        self.assertEqual(s2.get("pause_milestone_id"), "m1-hello")
        self.assertEqual(self._hello(), "HELLO-CANARY-M1\n",
                         "real Dev did not deliver the exact m1 sentinel")

        # ---- step 3: ship m1 → run m2 → advisory pause at m2 ------------- #
        dec1 = self._decision(s2, os.path.join(self.tmp, "dec1.json"),
                              choice="ship", note="canary m1 verified")
        p3 = self._cli(*self._campaign_args(
            "--resume", "--decision", dec1))
        self.assertEqual(p3.returncode, 10, p3.stdout[-4000:] + p3.stderr[-4000:])
        s3 = _parse_status(p3.stdout)
        self.assertEqual(s3["pause_reason"], "advisory_acceptance_pass_signoff")
        self.assertEqual(s3.get("pause_milestone_id"), "m2-append")
        self.assertEqual(self._hello(), "HELLO-CANARY-M1\nHELLO-CANARY-M2\n",
                         "real Dev did not deliver the exact m2 append")

        # ---- step 4: ship m2 → campaign done ------------------------------ #
        dec2 = self._decision(s3, os.path.join(self.tmp, "dec2.json"),
                              choice="ship", note="canary m2 verified")
        p4 = self._cli(*self._campaign_args(
            "--resume", "--decision", dec2))
        self.assertEqual(p4.returncode, 0, p4.stdout[-4000:] + p4.stderr[-4000:])
        s4 = _parse_status(p4.stdout)
        self.assertEqual(s4["status"], "done")
        self.assertEqual(s4["milestone_index"], 2)
        self.assertEqual(s4["milestones_total"], 2)
        # scope_coverage is a DEGRADABLE reporting nicety (may be absent from
        # the printed status line) — assert it only when present.
        cov = s4.get("scope_coverage")
        if cov:
            self.assertEqual(cov["milestones_delivered"], 2)

        # ---- flow invariants over the whole run --------------------------- #
        types = self._unit_event_types()
        self.assertEqual(types.count("acceptance_start"), 2,
                         "exactly one Acceptance per milestone")
        # No watchdog false-kill anywhere: the stream-lease probes are what
        # this canary proves in anger.
        diag = os.path.join(self.ws, ".orchestrator", "diagnostics",
                            "agent-stuck")
        self.assertFalse(
            os.path.isdir(diag) and os.listdir(diag),
            f"agent-stuck diagnostics recorded: {diag}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
