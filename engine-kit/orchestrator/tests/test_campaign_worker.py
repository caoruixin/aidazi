"""Phase-4 (parallel campaign runner) — Cluster 2 tests: the WORKER.

Covers the additive `run_unit(requirement_context=...)` kwarg (worker mode writes the
coordinator-produced sidecar verbatim and SKIPS the self-read; serial byte-identical when
absent), the worker-input contract + clock policy + run_loop resolution, the N=1 fold-identity
canary (one worker folds identically to the serial runner, in-process), and the
parent-flock-before-fork launcher (a spawned child inherits the OFD lock — design §5.5, the
POSIX fd-inheritance proof). stdlib unittest; offline; POSIX (flock/subprocess)."""
import json
import os
import sys
import tempfile
import time
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_TESTS_DIR, _ORCH_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign  # noqa: E402
import campaign_worker as cw  # noqa: E402
from _worker_canary_support import run_loop as DOUBLE  # noqa: E402

CID = "camp-1"
CHARTER = {"charter_id": "ch", "goal": "g"}
PLAN = {"campaign_id": CID, "goal": "g"}
CLOCK_FIXED = {"kind": "fixed", "value": "2026-07-11T00:00:00Z"}


def _write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
class TestRunUnitRequirementContext(unittest.TestCase):
    """The additive run_unit `requirement_context` kwarg (design §5.2)."""

    def _ru(self, tmp, *, ledger=True):
        units = os.path.join(tmp, "units")
        os.makedirs(units, exist_ok=True)
        lp = None
        if ledger:
            lp = os.path.join(tmp, "ledger.json")
            _write_json(lp, {"requirements": [
                {"id": "R1", "surface": "x", "surface_status": "proposed"}]})
        # dirname(units) is where the serial self-read looks for campaign-state.json.
        _write_json(os.path.join(tmp, "campaign-state.json"),
                    {"status": "SELF", "cursor": {"milestone_index": 0, "subsprint_index": 0},
                     "milestone_outcomes": []})
        ru = campaign.make_run_unit(CHARTER, units, CID, clock=lambda: "T",
                                    plan=PLAN, run_loop_fn=DOUBLE, ledger_path=lp)
        return ru, units

    def test_worker_mode_writes_verbatim_and_skips_selfread(self):
        tmp = tempfile.mkdtemp()
        ru, units = self._ru(tmp)
        ctx = {"plan": PLAN, "ledger": {"given": 1},
               "campaign_state": {"status": "GIVEN"}, "charter": CHARTER}
        res = ru("s1", milestone_id="m1", requirement_context=ctx)
        got = _read_json(os.path.join(units, res["loop_id"], "requirement-context.json"))
        self.assertEqual(got, ctx)                       # verbatim
        self.assertEqual(got["campaign_state"]["status"], "GIVEN")  # NOT "SELF" (skipped)

    def test_serial_mode_selfreads_when_no_requirement_context(self):
        tmp = tempfile.mkdtemp()
        ru, units = self._ru(tmp)
        res = ru("s1", milestone_id="m1")                # no requirement_context
        got = _read_json(os.path.join(units, res["loop_id"], "requirement-context.json"))
        self.assertEqual(got["campaign_state"]["status"], "SELF")  # from the state file
        self.assertEqual(set(got), {"plan", "ledger", "campaign_state", "charter"})
        # advisory field stripped by the projection
        self.assertEqual(got["ledger"]["requirements"], [{"id": "R1", "surface": "x"}])

    def test_serial_byte_identity_no_ledger_no_sidecar(self):
        # requirement_context=None + no ledger ⇒ NO sidecar (byte-identical to pre-Phase-4).
        tmp = tempfile.mkdtemp()
        ru, units = self._ru(tmp, ledger=False)
        res = ru("s1", milestone_id="m1")
        self.assertFalse(os.path.exists(
            os.path.join(units, res["loop_id"], "requirement-context.json")))


class TestWorkerHelpers(unittest.TestCase):
    """Clock policy, run_loop resolution, worker-input contract (design §5.1)."""

    def test_clock_from_policy(self):
        self.assertEqual(cw._clock_from_policy({"kind": "fixed", "value": "T"})(), "T")
        self.assertTrue(cw._clock_from_policy({"kind": "wallclock"})().endswith("Z"))
        self.assertTrue(cw._clock_from_policy(None)())   # default = wallclock
        with self.assertRaises(ValueError):
            cw._clock_from_policy({"kind": "nope"})
        with self.assertRaises(ValueError):
            cw._clock_from_policy({"kind": "fixed"})     # missing value

    def test_resolve_run_loop(self):
        self.assertTrue(callable(cw._resolve_run_loop("_worker_canary_support:run_loop")))
        with self.assertRaises(ValueError):
            cw._resolve_run_loop("nocolon")
        with self.assertRaises(ValueError):
            cw._resolve_run_loop("_worker_canary_support:does_not_exist")

    def _full_dispatch(self, **over):
        d = {"subsprint_id": "s1", "milestone_id": "m1", "subsprint_sequence": ["s1"]}
        d.update(over)
        return d

    def _bwi(self, **over):
        kw = dict(campaign_id=CID, units_dir="u", charter=CHARTER, plan=PLAN,
                  clock=CLOCK_FIXED, dispatch_epoch="H", attempt_nonce=1,
                  requirement_context={"a": 1}, dispatch=self._full_dispatch())
        kw.update(over)
        return cw.build_worker_input(**kw)

    def test_build_worker_input_accepts_full_contract(self):
        wi = self._bwi(attempt_nonce=7)
        for k in ("campaign_id", "units_dir", "charter", "plan", "ledger_path",
                  "run_loop_kwargs", "run_loop_entrypoint", "clock", "extra_sys_path",
                  "requirement_context", "dispatch", "attempt_nonce", "dispatch_epoch"):
            self.assertIn(k, wi)
        self.assertEqual(wi["attempt_nonce"], 7)
        self.assertEqual(wi["clock"], CLOCK_FIXED)
        self.assertEqual(wi["dispatch_epoch"], "H")

    def test_build_worker_input_fail_closed(self):
        # Codex C2 B-1: incomplete worker-input must be rejected at BUILD time.
        with self.assertRaises(ValueError):        # empty dispatch
            cw.build_worker_input(campaign_id=CID, units_dir="u", charter=CHARTER,
                                  dispatch={}, attempt_nonce=1)
        with self.assertRaises(ValueError):        # missing subsprint_sequence
            self._bwi(dispatch={"subsprint_id": "s1", "milestone_id": "m1"})
        with self.assertRaises(ValueError):        # subsprint_sequence lacks subsprint_id
            self._bwi(dispatch=self._full_dispatch(subsprint_sequence=["other"]))
        with self.assertRaises(ValueError):        # missing milestone_id
            self._bwi(dispatch={"subsprint_id": "s1", "subsprint_sequence": ["s1"]})
        with self.assertRaises(ValueError):        # non-int attempt_nonce
            self._bwi(attempt_nonce="1")
        with self.assertRaises(ValueError):        # missing dispatch_epoch
            self._bwi(dispatch_epoch=None)
        with self.assertRaises(ValueError):        # ledger-wired but no requirement_context
            self._bwi(ledger_path="/tmp/ledger.json", requirement_context=None)
        # A genuinely NON-ledger worker (no ledger_path) may carry requirement_context=None.
        self.assertIsNone(self._bwi(ledger_path=None,
                                    requirement_context=None)["requirement_context"])

    def test_worker_lock_held_false_without_lock_file(self):
        self.assertFalse(cw.worker_lock_held(tempfile.mkdtemp()))

    def test_worker_lock_held_true_while_locked(self):
        import fcntl
        d = tempfile.mkdtemp()
        fd = os.open(cw.lock_path(d), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self.assertTrue(cw.worker_lock_held(d))    # a held lock ⇒ probe reports held
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.assertFalse(cw.worker_lock_held(d))       # released ⇒ not held


class TestWorkerFoldIdentity(unittest.TestCase):
    """N=1 canary: one worker folds IDENTICALLY to the serial runner (design §13)."""

    def test_worker_folds_identically_to_serial(self):
        tmp = tempfile.mkdtemp()
        # --- SERIAL: run one sub-sprint via make_run_unit; it self-reads the sidecar. ---
        serial_home = os.path.join(tmp, "serial")
        serial_units = os.path.join(serial_home, "units")
        os.makedirs(serial_units, exist_ok=True)
        ledger_path = os.path.join(serial_home, "ledger.json")
        _write_json(ledger_path, {"requirements": [
            {"id": "R1", "surface": "x", "surface_status": "proposed"}]})
        _write_json(os.path.join(serial_home, "campaign-state.json"),
                    {"status": "running",
                     "cursor": {"milestone_index": 0, "subsprint_index": 0},
                     "milestone_outcomes": []})
        ru = campaign.make_run_unit(
            CHARTER, serial_units, CID, clock=cw._clock_from_policy(CLOCK_FIXED),
            plan=PLAN, run_loop_fn=DOUBLE, ledger_path=ledger_path)
        # Full dispatch contract: subsprint_sequence pins loop_mode=delivery_only + derivation.
        serial = ru("s1", milestone_id="m1", subsprint_sequence=["s1"])
        serial_sidecar = os.path.join(
            serial_units, serial["loop_id"], "requirement-context.json")
        with open(serial_sidecar, "rb") as fh:
            serial_bytes = fh.read()

        # --- WORKER: hand it EXACTLY the coordinator sidecar (== serial's self-read bytes). ---
        worker_dir = os.path.join(tmp, "worker")
        worker_units = os.path.join(worker_dir, "units")
        wi = cw.build_worker_input(
            campaign_id=CID, units_dir=worker_units, charter=CHARTER, plan=PLAN,
            ledger_path=ledger_path,                      # present but IGNORED in worker mode
            requirement_context=json.loads(serial_bytes), clock=CLOCK_FIXED,
            run_loop_entrypoint="_worker_canary_support:run_loop",
            extra_sys_path=[_TESTS_DIR],
            dispatch={"subsprint_id": "s1", "milestone_id": "m1",
                      "subsprint_sequence": ["s1"]},
            attempt_nonce=1, dispatch_epoch="H0")
        cw.write_worker_input(worker_dir, wi)
        out = cw.run_worker(worker_dir)
        worker = out["result"]

        # loop_id is (campaign, milestone, subsprint)-derived ⇒ identical; result identical.
        self.assertEqual(worker["loop_id"], serial["loop_id"])
        self.assertEqual(worker["final_state"], serial["final_state"])
        self.assertEqual(worker["spawn_count"], serial["spawn_count"])
        self.assertEqual(worker["pause_reason"], serial["pause_reason"])
        self.assertEqual(worker["checkpoint_path"], serial["checkpoint_path"])
        # BYTE-identity of the sidecar (Codex C2 B-4: compare raw bytes, not parsed dicts).
        worker_sidecar = os.path.join(
            worker_units, worker["loop_id"], "requirement-context.json")
        with open(worker_sidecar, "rb") as fh:
            worker_bytes = fh.read()
        self.assertEqual(worker_bytes, serial_bytes)
        # the per-milestone derived-context sidecar is ALSO byte-identical (deterministic).
        with open(os.path.join(serial_units, serial["loop_id"],
                               "derived-context.json"), "rb") as fh:
            s_dc = fh.read()
        with open(os.path.join(worker_units, worker["loop_id"],
                               "derived-context.json"), "rb") as fh:
            w_dc = fh.read()
        self.assertEqual(w_dc, s_dc)
        # attempt-scoped result + worker-owned lease exist; the result echoes the fold key.
        self.assertTrue(os.path.exists(cw.result_path(worker_dir, 1)))
        self.assertTrue(os.path.exists(cw.lease_path(worker_dir, 1)))
        self.assertEqual(out["attempt_nonce"], 1)
        self.assertEqual(out["dispatch_epoch"], "H0")
        lease = _read_json(cw.lease_path(worker_dir, 1))
        self.assertEqual(lease["phase"], "done")
        self.assertEqual(lease["pid"], os.getpid())      # in-process run_worker

    def test_worker_mode_ignores_campaign_state_file(self):
        # A POISONED campaign-state.json where the self-read WOULD look must NOT leak into the
        # worker's sidecar — worker mode writes the SUPPLIED requirement_context verbatim.
        tmp = tempfile.mkdtemp()
        worker_dir = os.path.join(tmp, "worker")
        worker_units = os.path.join(worker_dir, "units")
        os.makedirs(worker_units, exist_ok=True)
        _write_json(os.path.join(worker_dir, "campaign-state.json"),
                    {"status": "POISON", "cursor": {}, "milestone_outcomes": [{"x": 1}]})
        supplied = {"plan": PLAN, "ledger": {"requirements": []},
                    "campaign_state": {"status": "clean"}, "charter": CHARTER}
        wi = cw.build_worker_input(
            campaign_id=CID, units_dir=worker_units, charter=CHARTER, plan=PLAN,
            requirement_context=supplied, clock=CLOCK_FIXED, dispatch_epoch="H",
            run_loop_entrypoint="_worker_canary_support:run_loop",
            extra_sys_path=[_TESTS_DIR],
            dispatch={"subsprint_id": "s1", "milestone_id": "m1",
                      "subsprint_sequence": ["s1"]}, attempt_nonce=1)
        cw.write_worker_input(worker_dir, wi)
        out = cw.run_worker(worker_dir)
        got = _read_json(os.path.join(
            worker_units, out["result"]["loop_id"], "requirement-context.json"))
        self.assertEqual(got, supplied)
        self.assertEqual(got["campaign_state"]["status"], "clean")   # never "POISON"


class TestWorkerLauncher(unittest.TestCase):
    """Parent-flock-before-fork launcher: the child INHERITS the OFD lock (design §5.5)."""

    def test_launch_worker_child_inherits_lock_and_writes_result(self):
        tmp = tempfile.mkdtemp()
        worker_dir = os.path.join(tmp, "wk")
        worker_units = os.path.join(worker_dir, "units")
        sentinel = os.path.join(tmp, "go")
        ctx = {"plan": PLAN, "ledger": {"requirements": []},
               "campaign_state": {"status": "s"}, "charter": CHARTER}
        wi = cw.build_worker_input(
            campaign_id=CID, units_dir=worker_units, charter=CHARTER, plan=PLAN,
            requirement_context=ctx, clock=CLOCK_FIXED, dispatch_epoch="H",
            run_loop_entrypoint="_worker_canary_support:run_loop_blocking",
            extra_sys_path=[_TESTS_DIR],
            dispatch={"subsprint_id": "s1", "milestone_id": "m1",
                      "subsprint_sequence": ["s1"]}, attempt_nonce=1)
        cw.write_worker_input(worker_dir, wi)

        self.assertFalse(cw.worker_lock_held(worker_dir))   # no worker yet
        proc = cw.launch_worker(
            worker_dir, extra_env={"AIDAZI_WORKER_CANARY_SENTINEL": sentinel})
        try:
            # The child must hold the inherited flock WHILE it blocks (proves pass_fds/OFD share).
            held = False
            for _ in range(1500):
                if cw.worker_lock_held(worker_dir):
                    held = True
                    break
                time.sleep(0.01)
            self.assertTrue(held, "spawned worker never held the inherited flock")
            self.assertFalse(os.path.exists(cw.result_path(worker_dir, 1)))  # still blocked
            open(sentinel, "w").close()                     # release the worker
            self.assertEqual(proc.wait(timeout=30), 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
        self.assertFalse(cw.worker_lock_held(worker_dir))   # lock released on child exit
        out = _read_json(cw.result_path(worker_dir, 1))
        self.assertEqual(out["result"]["final_state"], "advance")
        self.assertEqual(out["attempt_nonce"], 1)
        self.assertTrue(os.path.exists(cw.lease_path(worker_dir, 1)))
        lease = _read_json(cw.lease_path(worker_dir, 1))
        self.assertNotEqual(lease["pid"], os.getpid())      # a DIFFERENT (child) process

    def test_worker_exception_writes_error_result_echoing_identity(self):
        # A worker whose run_loop RAISES must write an OBSERVABLE error result that echoes the
        # SAME fold identity as a success result (Codex C2 B-2), and exit non-zero.
        tmp = tempfile.mkdtemp()
        worker_dir = os.path.join(tmp, "wk")
        worker_units = os.path.join(worker_dir, "units")
        ctx = {"plan": PLAN, "ledger": {"requirements": []},
               "campaign_state": {"status": "s"}, "charter": CHARTER}
        wi = cw.build_worker_input(
            campaign_id=CID, units_dir=worker_units, charter=CHARTER, plan=PLAN,
            requirement_context=ctx, clock=CLOCK_FIXED, dispatch_epoch="H7",
            run_loop_entrypoint="_worker_canary_support:run_loop_raises",
            extra_sys_path=[_TESTS_DIR],
            dispatch={"subsprint_id": "s1", "milestone_id": "m1",
                      "subsprint_sequence": ["s1"]}, attempt_nonce=3)
        cw.write_worker_input(worker_dir, wi)
        proc = cw.launch_worker(worker_dir)
        self.assertEqual(proc.wait(timeout=30), 1)          # non-zero exit
        out = _read_json(cw.result_path(worker_dir, 3))
        self.assertIsNone(out["result"])
        self.assertIn("error", out)
        self.assertEqual(out["attempt_nonce"], 3)
        self.assertEqual(out["milestone_id"], "m1")
        self.assertEqual(out["subsprint_id"], "s1")
        self.assertEqual(out["dispatch_epoch"], "H7")       # full fold identity echoed
        self.assertFalse(cw.worker_lock_held(worker_dir))   # lock released on exit


if __name__ == "__main__":
    unittest.main()
