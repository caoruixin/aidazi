"""Universal-skill-mounting §2 (archive/2026-07-06) — signed signal sources: campaign
milestone_signals authority (digest + signoff binding + central freshness) and the
derive_milestone_context projection onto the effective charter.

Phase-1 test matrix (design §5 / Codex R3 NB1):
  * digest determinism + presence-keying (empty array still opts in);
  * stamp_signoff binds the digest top-level AND into the authenticated snapshot,
    OMITTING both for signal-free plans (byte-identical signoff);
  * f1_required triggers on milestone_signals field presence;
  * signed_scope_H BYTE-STABILITY: signals never enter H;
  * signoff_status staleness matrix incl. the strip-both regression (NB1);
  * signoff_snapshot_authentic both-or-neither digest consistency;
  * Campaign ingress fail-closed for signed plans with digest mismatch;
  * derive_milestone_context union projection + provenance (absent ⇒ byte-identical).
"""
import copy
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))                       # orchestrator/
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))     # engine-kit/

import campaign as cp  # noqa: E402


def _clock():
    n = {"i": 0}

    def clock():
        n["i"] += 1
        return f"2026-07-06T00:{n['i']:02d}:00Z"
    return clock


def _fake_run_unit(script):
    def run_unit(subsprint_id, *, milestone_id=None, subsprint_sequence=None,
                 resume=False, functional_acceptance=None, repo_dir=None):
        return dict(script.get(subsprint_id, {"final_state": "done", "spawn_count": 0}))
    return run_unit


_CHARTER = {"tooling": {"acceptance": {"functional": {"mode": "static"}}}}


def _milestone(mid, seq, **kw):
    return {"id": mid, "objective": f"objective {mid}",
            "subsprint_sequence": list(seq), **kw}


def _plan(milestones, **kw):
    return {"campaign_id": kw.pop("campaign_id", "camp-sig"),
            "goal": "deliver the thing",
            "signed_by_human": kw.pop("signed_by_human", True),
            "milestones": milestones, **kw}


def _signed(plan, charter=_CHARTER):
    return cp.stamp_signoff(plan, charter, signer="human",
                            signed_at="2026-07-06T00:00:00Z", charter_ref="charter.yaml")


class MilestoneSignalsDigestTests(unittest.TestCase):

    def test_none_when_no_milestone_carries_the_field(self):
        plan = _plan([_milestone("m1", ["s1"])])
        self.assertIsNone(cp.milestone_signals_digest(plan))

    def test_presence_keyed_empty_array_still_digests(self):
        plan = _plan([_milestone("m1", ["s1"], milestone_signals=[])])
        self.assertIsNotNone(cp.milestone_signals_digest(plan))

    def test_deterministic_and_order_insensitive_within_a_milestone(self):
        a = _plan([_milestone("m1", ["s1"], milestone_signals=["ui", "a11y"])])
        b = _plan([_milestone("m1", ["s1"], milestone_signals=["a11y", "ui"])])
        self.assertEqual(cp.milestone_signals_digest(a), cp.milestone_signals_digest(b))

    def test_changes_when_any_milestone_signals_change(self):
        base = _plan([_milestone("m1", ["s1"], milestone_signals=["ui"]),
                      _milestone("m2", ["s2"])])
        edited = copy.deepcopy(base)
        edited["milestones"][1]["milestone_signals"] = ["a11y"]
        self.assertNotEqual(cp.milestone_signals_digest(base),
                            cp.milestone_signals_digest(edited))


class StampSignoffBindingTests(unittest.TestCase):

    def test_signal_bearing_plan_binds_digest_in_both_places(self):
        plan = _signed(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"])]))
        so = plan["signoff"]
        self.assertEqual(so["milestone_signals_digest"],
                         cp.milestone_signals_digest(plan))
        self.assertEqual(so["scope_envelope"]["milestone_signals_digest"],
                         so["milestone_signals_digest"])

    def test_signal_free_plan_signoff_is_byte_identical(self):
        plan = _signed(_plan([_milestone("m1", ["s1"])]))
        so = plan["signoff"]
        self.assertNotIn("milestone_signals_digest", so)
        self.assertNotIn("milestone_signals_digest", so["scope_envelope"])


class F1RequiredTests(unittest.TestCase):

    def test_milestone_signals_presence_activates_f1(self):
        self.assertTrue(cp.f1_required(
            _plan([_milestone("m1", ["s1"], milestone_signals=["ui"])],
                  signed_by_human=False)))
        # presence-keyed: an explicit empty array still opts in
        self.assertTrue(cp.f1_required(
            _plan([_milestone("m1", ["s1"], milestone_signals=[])],
                  signed_by_human=False)))

    def test_legacy_plan_stays_inactive(self):
        self.assertFalse(cp.f1_required(
            _plan([_milestone("m1", ["s1"])], signed_by_human=False)))


class SignedScopeHashStabilityTests(unittest.TestCase):

    def test_milestone_signals_never_enter_H(self):
        without = _plan([_milestone("m1", ["s1"])])
        with_sig = _plan([_milestone("m1", ["s1"], milestone_signals=["ui", "a11y"])])
        self.assertEqual(
            cp.compute_signed_scope_hash(without, _CHARTER, charter_ref="charter.yaml"),
            cp.compute_signed_scope_hash(with_sig, _CHARTER, charter_ref="charter.yaml"))


class SignoffStatusFreshnessTests(unittest.TestCase):

    def _fresh_signed(self):
        return _signed(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"]),
                              _milestone("m2", ["s2"])]))

    def test_fresh_signed_reads_signed(self):
        self.assertEqual(cp.signoff_status(self._fresh_signed(), _CHARTER), "signed")

    def test_post_sign_signal_edit_reads_stale(self):
        plan = self._fresh_signed()
        plan["milestones"][0]["milestone_signals"] = ["ui", "frontend"]
        self.assertEqual(cp.signoff_status(plan, _CHARTER), "stale")

    def test_post_sign_signal_addition_on_another_milestone_reads_stale(self):
        plan = self._fresh_signed()
        plan["milestones"][1]["milestone_signals"] = ["design"]
        self.assertEqual(cp.signoff_status(plan, _CHARTER), "stale")

    def test_strip_signals_only_reads_stale(self):
        plan = self._fresh_signed()
        del plan["milestones"][0]["milestone_signals"]
        self.assertEqual(cp.signoff_status(plan, _CHARTER), "stale")

    def test_strip_both_signals_and_top_level_digest_reads_stale(self):
        # Codex R3 NB1 — the naive tamper strips what it can see (the plan field + the
        # top-level digest); the AUTHENTICATED-SNAPSHOT copy survives and flips freshness.
        plan = self._fresh_signed()
        del plan["milestones"][0]["milestone_signals"]
        del plan["signoff"]["milestone_signals_digest"]
        self.assertEqual(cp.signoff_status(plan, _CHARTER), "stale")

    def test_unsigned_signal_bearing_plan_reads_unsigned(self):
        plan = _plan([_milestone("m1", ["s1"], milestone_signals=["ui"])],
                     signed_by_human=False)
        self.assertEqual(cp.signoff_status(plan, _CHARTER), "unsigned")

    def test_legacy_signal_free_signed_plan_unchanged(self):
        plan = _signed(_plan([_milestone("m1", ["s1"])]))
        self.assertEqual(cp.signoff_status(plan, _CHARTER), "signed")


class SnapshotAuthenticityTests(unittest.TestCase):

    def test_authentic_after_stamp(self):
        self.assertTrue(cp.signoff_snapshot_authentic(
            _signed(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"])]))))

    def test_tampered_top_level_digest_not_authentic(self):
        plan = _signed(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"])]))
        plan["signoff"]["milestone_signals_digest"] = "0" * 64
        self.assertFalse(cp.signoff_snapshot_authentic(plan))

    def test_one_sided_digest_not_authentic(self):
        plan = _signed(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"])]))
        del plan["signoff"]["scope_envelope"]["milestone_signals_digest"]
        self.assertFalse(cp.signoff_snapshot_authentic(plan))

    def test_pre_feature_snapshot_still_authentic(self):
        self.assertTrue(cp.signoff_snapshot_authentic(
            _signed(_plan([_milestone("m1", ["s1"])]))))


class CampaignIngressTests(unittest.TestCase):

    def _campaign(self, plan):
        with tempfile.TemporaryDirectory() as d:
            return cp.Campaign(plan, d, _fake_run_unit({}), clock=_clock())

    def test_signed_plan_with_stripped_digest_fails_ingress(self):
        plan = _signed(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"])]))
        del plan["signoff"]["milestone_signals_digest"]
        with self.assertRaisesRegex(ValueError, "milestone_signals"):
            self._campaign(plan)

    def test_signed_plan_with_mutated_signals_fails_ingress(self):
        plan = _signed(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"])]))
        plan["milestones"][0]["milestone_signals"] = ["a11y"]
        with self.assertRaisesRegex(ValueError, "milestone_signals"):
            self._campaign(plan)

    def test_fresh_signed_and_unsigned_plans_pass_ingress(self):
        self._campaign(_signed(_plan(
            [_milestone("m1", ["s1"], milestone_signals=["ui"])])))
        # the sign flow must stay usable: unsigned signal-bearing plans construct
        # (real runs are blocked downstream by the freshness gates)
        self._campaign(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"])],
                             signed_by_human=False))


class DeriveMilestoneContextProjectionTests(unittest.TestCase):

    def _derive(self, charter, signals):
        return cp.derive_milestone_context(
            charter, "m1", ["s1"], campaign_id="camp-sig", plan_fingerprint="ph",
            milestone_signals=signals)

    def test_union_projection_sorted_deduped(self):
        charter = {"autonomy": {"approved_scope": {"task_signals": ["ui", "design"]}},
                   **_CHARTER}
        derived, prov = self._derive(charter, ["a11y", "ui"])
        self.assertEqual(derived["autonomy"]["approved_scope"]["task_signals"],
                         ["a11y", "design", "ui"])
        self.assertEqual(prov["task_signals"], {
            "effective": ["a11y", "design", "ui"],
            "charter_scope": ["design", "ui"],
            "milestone_signals": ["a11y", "ui"],
        })

    def test_milestone_signals_alone(self):
        derived, prov = self._derive(dict(_CHARTER), ["interaction"])
        self.assertEqual(derived["autonomy"]["approved_scope"]["task_signals"],
                         ["interaction"])
        self.assertEqual(prov["task_signals"]["charter_scope"], [])

    def test_absent_everywhere_is_byte_identical(self):
        derived, prov = self._derive(dict(_CHARTER), None)
        self.assertNotIn("task_signals", derived["autonomy"]["approved_scope"])
        self.assertNotIn("task_signals", prov)


if __name__ == "__main__":
    unittest.main()
