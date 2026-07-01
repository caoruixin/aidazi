"""OW-AUTO — acceptance auto-proposal & init experience (design
`archive/2026-07-01-acceptance-auto-proposal-and-init-experience-design.md`, §7 tests).

Phase 1 (proposal wiring) mandatory tests:
  (b) mandatory_e2e_violations / signoff_status ignore the advisory fields;
  (c) the ADVISORY-FLIP INVARIANT — flipping surface_confidence / surface_status leaves
      signed_scope_hash, signoff_status, and the requirement-context sidecar projection
      (⇒ acceptance_input_hash / gap_report) BYTE-IDENTICAL, while flipping the `surface`
      VALUE still flips signed_scope_hash → 'stale';
  (d) requirement_context_ledger_projection() drops the advisory fields;
  (e) the customer_disposition `pending`-sentinel authority carve-out (§4.1).

The end-to-end driver proof of the acceptance_input_hash / gap_report byte-identity lives in
test_gap_report.py::TestAdvisoryFlipInputHash (it reuses the acceptance driver harness).
stdlib unittest; offline (no Driver, no adapters)."""
import copy
import glob
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)                       # orchestrator/
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)                  # engine-kit/
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402

_CHARTER = {"autonomy": {"level": "human_on_the_loop"}}


def _ledger(status="proposed", confidence="high", surface="user_facing"):
    """A ledger whose lone covered REQ carries the ADVISORY fields + a `surface` VALUE."""
    return {"version": "v1", "requirements": [
        {"id": "REQ-1", "statement": "user signs in", "source": {"channel": "prd"},
         "customer_disposition": "accepted", "surface": surface,
         "surface_status": status, "surface_confidence": confidence},
        {"id": "REQ-2", "statement": "backend dedup", "source": {"channel": "prd"},
         "customer_disposition": "accepted", "surface": "non_user_facing",
         "surface_status": "confirmed", "surface_confidence": "high"}]}


def _plan():
    # m1 covers a user_facing REQ ⇒ browser_e2e (self-consistent, signs); m2 non_user_facing.
    return {"campaign_id": "camp-ow-auto", "goal": "ship it", "milestones": [
        {"id": "m1", "objective": "auth", "subsprint_sequence": ["s1"],
         "covers_req_ids": ["REQ-1"], "functional_acceptance": "browser_e2e"},
        {"id": "m2", "objective": "dedup", "subsprint_sequence": ["s2"],
         "covers_req_ids": ["REQ-2"]}]}


def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


class TestSidecarProjection(unittest.TestCase):
    """(d) requirement_context_ledger_projection() strips ONLY the advisory fields."""

    def test_drops_advisory_keeps_everything_else(self):
        proj = cp.requirement_context_ledger_projection(_ledger())
        for r in proj["requirements"]:
            self.assertNotIn("surface_status", r)
            self.assertNotIn("surface_confidence", r)
            # `surface` (a genuine gap-report input) + the identity fields survive.
            self.assertIn("surface", r)
            self.assertIn("id", r)
            self.assertIn("statement", r)
            self.assertIn("customer_disposition", r)
        self.assertEqual(proj["version"], "v1")

    def test_idempotent_and_absent_fields_noop(self):
        once = cp.requirement_context_ledger_projection(_ledger())
        twice = cp.requirement_context_ledger_projection(once)
        self.assertEqual(_canon(once), _canon(twice))
        # A legacy ledger (no advisory fields) projects to itself, byte-identical.
        legacy = {"version": "v1", "requirements": [
            {"id": "REQ-9", "statement": "x", "source": {"channel": "prd"},
             "customer_disposition": "pending"}]}
        self.assertEqual(_canon(cp.requirement_context_ledger_projection(legacy)),
                         _canon(legacy))

    def test_tolerant_of_malformed(self):
        self.assertIsNone(cp.requirement_context_ledger_projection(None))
        self.assertEqual(cp.requirement_context_ledger_projection({"version": "v1"}),
                         {"version": "v1"})
        # a non-dict requirement passes through untouched
        weird = {"version": "v1", "requirements": ["not-a-dict", 3]}
        self.assertEqual(cp.requirement_context_ledger_projection(weird), weird)


class TestAdvisoryFlipInvariant(unittest.TestCase):
    """(b)+(c) Flipping the advisory fields changes NO verdict-affecting output; flipping the
    `surface` VALUE still flips the signed hash → 'stale'."""

    def _sign(self, ledger):
        return cp.stamp_signoff(copy.deepcopy(_plan()), _CHARTER,
                                signed_at="t", ledger=ledger)

    def test_signed_scope_hash_stable_under_advisory_flip(self):
        base = self._sign(_ledger(status="proposed", confidence="high"))
        adv = self._sign(_ledger(status="confirmed", confidence="low"))
        self.assertEqual(base["signoff"]["signed_scope_hash"],
                         adv["signoff"]["signed_scope_hash"])       # byte-identical
        # flipping the surface VALUE DOES change the signed hash.
        surf = self._sign(_ledger(surface="non_user_facing"))
        self.assertNotEqual(base["signoff"]["signed_scope_hash"],
                            surf["signoff"]["signed_scope_hash"])

    def test_signoff_status_fresh_under_advisory_flip_stale_under_surface_flip(self):
        signed = self._sign(_ledger(status="proposed", confidence="high"))
        # advisory flip in the LIVE ledger ⇒ still fresh (no re-sign).
        self.assertEqual(
            cp.signoff_status(signed, _CHARTER,
                              _ledger(status="confirmed", confidence="low")), "signed")
        # surface VALUE flip ⇒ stale (must re-sign) — the OW-M3 tamper basis.
        self.assertEqual(
            cp.signoff_status(signed, _CHARTER, _ledger(surface="non_user_facing")),
            "stale")

    def test_mandatory_e2e_gate_ignores_advisory_fields(self):
        plan = _plan()
        base = cp.mandatory_e2e_violations(plan, _CHARTER, _ledger("proposed", "high"))
        adv = cp.mandatory_e2e_violations(plan, _CHARTER, _ledger("confirmed", "low"))
        self.assertEqual(base, [])
        self.assertEqual(base, adv)

    def test_sidecar_projection_bytes_stable_under_advisory_flip(self):
        # The requirement-context sidecar is the ONLY ledger-derived input to BOTH
        # acceptance_input_hash and the gap_report. Its projected bytes are identical under
        # an advisory flip and DIFFER under a surface-VALUE flip.
        base = _canon(cp.requirement_context_ledger_projection(_ledger("proposed", "high")))
        adv = _canon(cp.requirement_context_ledger_projection(_ledger("confirmed", "low")))
        surf = _canon(cp.requirement_context_ledger_projection(
            _ledger(surface="non_user_facing")))
        self.assertEqual(base, adv)
        self.assertNotEqual(base, surf)


class TestCustomerDispositionAuthority(unittest.TestCase):
    """(e) §4.1 carve-out: an agent/engine may seed `pending` on a NEW item ONLY; it may
    NEVER author a decided value on a new item and NEVER transition an existing one."""

    def test_new_item_only_pending_is_agent_allowed(self):
        self.assertTrue(cp.agent_seeded_disposition_allowed("pending", None))
        for decided in ("accepted", "deferred", "skipped", "dropped", "modified"):
            self.assertFalse(cp.agent_seeded_disposition_allowed(decided, None),
                             f"agent must not seed decided {decided!r} on a new item")

    def test_no_agent_transition_out_of_pending_or_between_decided(self):
        self.assertFalse(cp.agent_seeded_disposition_allowed("accepted", "pending"))
        self.assertFalse(cp.agent_seeded_disposition_allowed("deferred", "accepted"))
        self.assertFalse(cp.agent_seeded_disposition_allowed("pending", "accepted"))

    def test_unchanged_value_is_a_noop_and_allowed(self):
        # Leaving an existing value untouched is not a write ⇒ allowed.
        self.assertTrue(cp.agent_seeded_disposition_allowed("accepted", "accepted"))
        self.assertTrue(cp.agent_seeded_disposition_allowed("pending", "pending"))


class TestCampaignWriterProjection(unittest.TestCase):
    """(d) WIRING guard: the campaign requirement-context WRITER (make_run_unit → run_unit)
    calls requirement_context_ledger_projection, so a wired ledger carrying advisory fields
    produces a STRIPPED sidecar. If the projection line is dropped, the raw advisory fields
    reach the sidecar → acceptance_input_hash churns on an advisory flip. This test fails
    closed on that regression."""

    def test_writer_strips_advisory_fields_from_sidecar(self):
        with tempfile.TemporaryDirectory() as root:
            units_dir = os.path.join(root, "units")
            os.makedirs(units_dir)
            ledger_path = os.path.join(root, "ledger.json")
            raw = _ledger(status="proposed", confidence="low")   # advisory fields PRESENT
            with open(ledger_path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh)
            plan = {"campaign_id": "camp-w", "goal": "g", "milestones": [
                {"id": "m1", "objective": "o", "subsprint_sequence": ["s1"],
                 "covers_req_ids": ["REQ-1"]}]}

            def _stub_run_loop(charter, **kw):               # never touches the ledger
                return {"final_state": "done", "spawn_count": 0}

            ru = cp.make_run_unit({"autonomy": {"level": "human_on_the_loop"}},
                                  units_dir, "camp-w", clock=lambda: "t", plan=plan,
                                  run_loop_fn=_stub_run_loop, ledger_path=ledger_path)
            ru("s1", milestone_id="m1")                      # no sequence ⇒ direct dispatch

            sidecars = glob.glob(os.path.join(units_dir, "*", "requirement-context.json"))
            self.assertEqual(len(sidecars), 1)
            with open(sidecars[0], encoding="utf-8") as fh:
                sc = json.load(fh)
            for r in sc["ledger"]["requirements"]:
                self.assertNotIn("surface_status", r)
                self.assertNotIn("surface_confidence", r)
                self.assertIn("surface", r)                  # a genuine gap-report input stays
            # the SOURCE ledger on disk is untouched (the projection is write-time only).
            with open(ledger_path, encoding="utf-8") as fh:
                self.assertIn("surface_status", json.load(fh)["requirements"][0])


if __name__ == "__main__":
    unittest.main()
