"""OW-M3 — requirement-driven mandatory browser-E2E acceptance (design
`archive/2026-06-30-ow-m3-mandatory-e2e-spec.md`, test plan §7).

The sign-off gate derives each milestone's REQUIRED acceptance class from the OW-2 ledger
`surface` classification of the requirements it covers, binds that basis into the signed
hash (B1), and refuses to sign a plan that would accept a user_facing requirement on
static (M1) evidence — while staying byte-identical to pre-OW-M3 when no ledger is wired.
stdlib unittest; offline (no Driver, no adapters)."""
import copy
import os
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)                       # orchestrator/
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)                  # engine-kit/
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "scheduling")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402

# A charter whose functional acceptance defaults to 'static' (source='default' when a
# milestone declares nothing). browser_e2e is engaged per-milestone via functional_acceptance.
_CHARTER = {"autonomy": {"level": "human_on_the_loop"}}


def _ledger(reqs):
    """reqs: [(id, surface_or_None)]. surface omitted entirely when None (unclassified)."""
    out = []
    for rid, surface in reqs:
        entry = {"id": rid, "statement": f"stmt {rid}",
                 "source": {"channel": "prd"}, "customer_disposition": "accepted"}
        if surface is not None:
            entry["surface"] = surface
        out.append(entry)
    return {"version": "v1", "requirements": out}


def _ms(mid, covers, functional_acceptance=None, seq=None):
    m = {"id": mid, "objective": f"o {mid}", "covers_req_ids": list(covers),
         "subsprint_sequence": list(seq or ["s1"])}
    if functional_acceptance is not None:
        m["functional_acceptance"] = functional_acceptance
    return m


def _plan(milestones, **extra):
    return {"campaign_id": "camp-ow", "goal": "deliver the thing",
            "milestones": milestones, **extra}


class TestMandatoryE2EGate(unittest.TestCase):
    """mandatory_e2e_violations — the pure sign-off / preflight gate (§3.1–§3.2)."""

    def test_user_facing_static_is_refused(self):
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"])])                 # inherits static default
        v = cp.mandatory_e2e_violations(plan, _CHARTER, led)
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["kind"], "downgrade")
        self.assertEqual(v[0]["milestone_id"], "m1")
        self.assertEqual(v[0]["req_ids"], ["REQ-1"])
        self.assertEqual(v[0]["resolved_mode"], "static")

    def test_user_facing_browser_e2e_signs(self):
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"], functional_acceptance="browser_e2e")])
        self.assertEqual(cp.mandatory_e2e_violations(plan, _CHARTER, led), [])

    def test_non_user_facing_static_signs(self):
        # Generality guard: a backend milestone is NOT forced onto browser_e2e.
        led = _ledger([("REQ-1", "non_user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"])])
        self.assertEqual(cp.mandatory_e2e_violations(plan, _CHARTER, led), [])

    def test_unclassified_req_is_refused(self):
        led = _ledger([("REQ-1", None)])                     # in ledger, no surface
        plan = _plan([_ms("m1", ["REQ-1"], functional_acceptance="browser_e2e")])
        v = cp.mandatory_e2e_violations(plan, _CHARTER, led)
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["kind"], "unclassified")
        self.assertEqual(v[0]["req_ids"], ["REQ-1"])

    def test_unknown_req_is_refused(self):
        led = _ledger([("REQ-1", "user_facing")])            # REQ-9 absent from ledger
        plan = _plan([_ms("m1", ["REQ-1", "REQ-9"],
                          functional_acceptance="browser_e2e")])
        v = cp.mandatory_e2e_violations(plan, _CHARTER, led)
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["kind"], "unclassified")
        self.assertEqual(v[0]["req_ids"], ["REQ-9"])

    def test_charter_default_browser_e2e_satisfies(self):
        # user_facing + charter-level browser_e2e default (no per-milestone value) ⇒ signs.
        charter = {"tooling": {"acceptance": {"functional": {"mode": "browser_e2e"}}}}
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"])])
        self.assertEqual(cp.mandatory_e2e_violations(plan, charter, led), [])

    def test_mixed_milestones_report_only_the_offender(self):
        led = _ledger([("REQ-1", "user_facing"), ("REQ-2", "non_user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"]),                  # user_facing + static → bad
                      _ms("m2", ["REQ-2"])])                 # backend + static → fine
        v = cp.mandatory_e2e_violations(plan, _CHARTER, led)
        self.assertEqual([x["milestone_id"] for x in v], ["m1"])

    def test_dormant_no_ledger_returns_empty(self):
        # No ledger ⇒ inert even for a user_facing-SHAPED plan (the mandate cannot bite
        # without the machine-readable OW-2 signal).
        plan = _plan([_ms("m1", ["REQ-1"])])
        self.assertEqual(cp.mandatory_e2e_violations(plan, _CHARTER, None), [])
        self.assertEqual(cp.mandatory_e2e_violations(plan, _CHARTER, {}), [])

    def test_absent_covers_req_ids_is_dormant(self):
        # A milestone with NO covers_req_ids never trips the mandate (N2).
        m = {"id": "m1", "objective": "o", "subsprint_sequence": ["s1"]}
        led = _ledger([("REQ-1", "user_facing")])
        self.assertEqual(cp.mandatory_e2e_violations(_plan([m]), _CHARTER, led), [])

    def test_empty_covers_req_ids_signs_vacuously(self):
        # An explicit covers_req_ids:[] activates F1 but references NO req ⇒ no mandate.
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", [])])
        self.assertEqual(cp.mandatory_e2e_violations(plan, _CHARTER, led), [])


class TestRefusalMessage(unittest.TestCase):
    """§3.2 / §8 friction guard: the refusal must emit the two actionable resolutions."""

    def test_downgrade_message_offers_both_resolutions(self):
        v = [{"milestone_id": "m1", "kind": "downgrade", "req_ids": ["REQ-1"],
              "resolved_mode": "static"}]
        msg = cp.render_mandatory_e2e_refusal(v, action="refusing to sign the plan")
        self.assertIn("browser_e2e", msg)
        self.assertIn("reclassify", msg.lower())
        self.assertIn("re-sign", msg.lower())
        self.assertIn("REQ-1", msg)

    def test_unclassified_message_names_the_reqs(self):
        v = [{"milestone_id": "m2", "kind": "unclassified", "req_ids": ["REQ-9"]}]
        msg = cp.render_mandatory_e2e_refusal(v, action="refusing the real run")
        self.assertIn("REQ-9", msg)
        self.assertIn("ledger", msg.lower())


class TestB1SurfaceBinding(unittest.TestCase):
    """B1: the covered-REQ surface basis is bound into the signed envelope + hash, so a
    post-sign surface flip is detectable as 'stale'."""

    def test_surfaces_bound_into_envelope(self):
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"], functional_acceptance="browser_e2e")])
        signed = cp.stamp_signoff(plan, _CHARTER, signed_at="t", ledger=led)
        env_ms = signed["signoff"]["scope_envelope"]["milestones"][0]
        self.assertEqual(env_ms["covered_req_surfaces"], {"REQ-1": "user_facing"})
        self.assertEqual(cp.signoff_status(signed, _CHARTER, led), "signed")

    def test_surface_flip_post_sign_is_stale(self):
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"], functional_acceptance="browser_e2e")])
        signed = cp.stamp_signoff(plan, _CHARTER, signed_at="t", ledger=led)
        self.assertEqual(cp.signoff_status(signed, _CHARTER, led), "signed")
        flipped = _ledger([("REQ-1", "non_user_facing")])    # Customer reclassifies
        self.assertEqual(cp.signoff_status(signed, _CHARTER, flipped), "stale")

    def test_ledger_removed_at_recompute_reuses_stored_basis(self):
        # Resilience: a transiently-unreadable ledger must NOT spuriously invalidate a
        # signed plan — the recompute reuses the STORED covered_req_surfaces basis.
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"], functional_acceptance="browser_e2e")])
        signed = cp.stamp_signoff(plan, _CHARTER, signed_at="t", ledger=led)
        self.assertEqual(cp.signoff_status(signed, _CHARTER, None), "signed")


class TestDormancyByteIdentical(unittest.TestCase):
    """Additivity: with no ledger, the signed hash + envelope are byte-identical to
    pre-OW-M3 (no covered_req_surfaces key)."""

    def test_no_ledger_hash_identical_and_field_absent(self):
        plan = _plan([_ms("m1", ["REQ-1"])])
        no_led = cp.stamp_signoff(copy.deepcopy(plan), _CHARTER, signed_at="t")
        explicit_none = cp.stamp_signoff(copy.deepcopy(plan), _CHARTER, signed_at="t",
                                         ledger=None)
        self.assertEqual(no_led["signoff"]["signed_scope_hash"],
                         explicit_none["signoff"]["signed_scope_hash"])
        env_ms = no_led["signoff"]["scope_envelope"]["milestones"][0]
        self.assertNotIn("covered_req_surfaces", env_ms)
        self.assertEqual(cp.signoff_status(no_led, _CHARTER), "signed")

    def test_introducing_a_ledger_changes_the_hash(self):
        # Opting into a ledger IS a signed-basis change ⇒ a plan signed without one reads
        # 'stale' once a ledger is present (must re-sign) — fail-closed, intentional.
        plan = _plan([_ms("m1", ["REQ-1"])])
        no_led = cp.stamp_signoff(plan, _CHARTER, signed_at="t")
        led = _ledger([("REQ-1", "non_user_facing")])
        self.assertEqual(cp.signoff_status(no_led, _CHARTER, led), "stale")


class TestReclassifyAndResign(unittest.TestCase):
    """Seal ②: reclassification is Customer-only and binds by re-signing."""

    def test_reclassify_then_downgrade_and_resign_signs(self):
        # Signed user_facing + browser_e2e; Customer reclassifies to non_user_facing and
        # downgrades the milestone to static, then re-signs ⇒ no violation, fresh.
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"], functional_acceptance="browser_e2e")])
        signed = cp.stamp_signoff(plan, _CHARTER, signed_at="t", ledger=led)
        self.assertEqual(cp.mandatory_e2e_violations(signed, _CHARTER, led), [])
        # Customer reclassifies + downgrades:
        led2 = _ledger([("REQ-1", "non_user_facing")])
        plan2 = _plan([_ms("m1", ["REQ-1"])])                # now static is allowed
        self.assertEqual(cp.mandatory_e2e_violations(plan2, _CHARTER, led2), [])
        resigned = cp.stamp_signoff(plan2, _CHARTER, signed_at="t2", ledger=led2)
        self.assertEqual(cp.signoff_status(resigned, _CHARTER, led2), "signed")


class TestRunLoopPreflightGate(unittest.TestCase):
    """The runner allow_real preflight half of the gate (D4)."""

    def test_enforce_raises_on_downgrade(self):
        import run_loop as rl
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"])])                 # user_facing + static
        with self.assertRaises(rl.CharterValidationError):
            rl.enforce_mandatory_e2e_for_real_run(plan, _CHARTER, led)

    def test_enforce_noop_when_clean(self):
        import run_loop as rl
        led = _ledger([("REQ-1", "user_facing")])
        plan = _plan([_ms("m1", ["REQ-1"], functional_acceptance="browser_e2e")])
        rl.enforce_mandatory_e2e_for_real_run(plan, _CHARTER, led)  # no raise

    def test_enforce_dormant_without_ledger(self):
        import run_loop as rl
        plan = _plan([_ms("m1", ["REQ-1"])])
        rl.enforce_mandatory_e2e_for_real_run(plan, _CHARTER, None)  # no raise


if __name__ == "__main__":
    unittest.main()
