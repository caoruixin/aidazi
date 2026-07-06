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


class EngineRestampSignalInterplayTests(unittest.TestCase):
    """Track-2 TD6 × universal-skill-mounting: a legitimate ENGINE-AUTHORED
    deliver_followup insertion on a SIGNAL-BEARING plan must still rescue to 'signed'
    (the Track-2 invariant — normal autonomous runtime evolution never requires a
    re-sign), with BOTH digest copies surviving the envelope reconstruction."""

    def test_td6_rescue_preserves_signal_digest_and_reads_signed(self):
        plan = _signed(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"])]))
        grown = copy.deepcopy(plan)
        grown["milestones"][0]["subsprint_sequence"] = ["s1", "s1b"]
        # raw drift: the insertion alone reads 'stale' (hash mismatch), NOT digest-stale
        self.assertEqual(cp.signoff_status(grown, _CHARTER), "stale")
        pinned = cp.compute_signed_scope_hash(grown, _CHARTER,
                                              charter_ref="charter.yaml")
        restamp = {"signed_scope_hash": pinned,
                   "deltas": [{"milestone_id": "m1", "subsprint_id": "s1b",
                               "at_index": 1}]}
        rescued = cp.apply_engine_restamp_to_plan(grown, _CHARTER, restamp)
        self.assertEqual(cp.signoff_status(rescued, _CHARTER), "signed")
        so = rescued["signoff"]
        self.assertEqual(so["milestone_signals_digest"],
                         cp.milestone_signals_digest(rescued))
        self.assertEqual(so["scope_envelope"]["milestone_signals_digest"],
                         so["milestone_signals_digest"])
        self.assertTrue(cp.signoff_snapshot_authentic(rescued))

    def test_td6_rescue_still_refuses_a_signal_edit(self):
        # growth + a signal mutation is NOT a pure authorized insertion: the digest check
        # keeps the rescued plan 'stale' (the rescue never launders a signal change).
        plan = _signed(_plan([_milestone("m1", ["s1"], milestone_signals=["ui"])]))
        grown = copy.deepcopy(plan)
        grown["milestones"][0]["subsprint_sequence"] = ["s1", "s1b"]
        grown["milestones"][0]["milestone_signals"] = ["a11y"]     # tamper
        pinned = cp.compute_signed_scope_hash(grown, _CHARTER,
                                              charter_ref="charter.yaml")
        restamp = {"signed_scope_hash": pinned,
                   "deltas": [{"milestone_id": "m1", "subsprint_id": "s1b",
                               "at_index": 1}]}
        rescued = cp.apply_engine_restamp_to_plan(grown, _CHARTER, restamp)
        self.assertEqual(cp.signoff_status(rescued, _CHARTER), "stale")


class ResolverCompatFilterTests(unittest.TestCase):
    """Universal-skill-mounting §2 — the runtime role/harness compatibility filter for
    SIGNAL-SELECTED candidates (defense-in-depth; the static validator stays the
    fail-closed authority)."""

    def setUp(self):
        import effective_role_config as erc
        self.erc = erc
        # A minimal catalog: one signal-tagged skill resolvable from a temp dir.
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        skill_dir = os.path.join(self.tmp.name, "skills", "sig-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: sig-skill\ndescription: d\n---\nbody\n")
        self.catalog = {
            "role_defaults": {},
            "skills": {},
            "authored": {"sig-skill": {
                "source": {"repo": "local", "path": "skills/sig-skill"},
                "signals": ["ui"],
                "harness_compat": ["claude_code"],
                "tool_requirements": ["Read"],
            }},
        }

    def _resolve(self, charter_tooling):
        return self.erc.resolve_role_config(
            {"tooling": charter_tooling}, "dev", task_signals=("ui",),
            framework_root=self.tmp.name, adopter_root=self.tmp.name,
            catalog=self.catalog)

    def test_compatible_role_mounts_the_signal_skill(self):
        cfg = self._resolve({"dev": {"agent_kind": "claude_code",
                                     "tools": ["Read", "Edit"]}})
        self.assertEqual([s.id for s in cfg.skills], ["sig-skill"])
        self.assertEqual(list(cfg.selected_skills), ["sig-skill"])
        self.assertEqual(list(cfg.skipped_skills), [])

    def test_harness_incompatible_candidate_is_recorded_skip(self):
        cfg = self._resolve({"dev": {"agent_kind": "codex",
                                     "tools": ["Read", "Edit"]}})
        self.assertEqual(cfg.skills, ())
        self.assertEqual(cfg.selected_skills, ())
        self.assertEqual(len(cfg.skipped_skills), 1)
        skip = cfg.skipped_skills[0]
        self.assertEqual(skip["id"], "sig-skill")
        self.assertEqual(skip["kind"], "incompatible")
        self.assertIn("harness", skip["reason"])
        # non-silent: the footer names it
        self.assertIn("sig-skill", self.erc.skill_skip_footer(cfg))
        self.assertIn("incompatible", self.erc.skill_skip_footer(cfg))

    def test_tool_requirements_exceeding_whitelist_is_recorded_skip(self):
        cfg = self._resolve({"dev": {"agent_kind": "claude_code",
                                     "tools": ["Edit"]}})
        self.assertEqual(cfg.skills, ())
        self.assertEqual(cfg.skipped_skills[0]["kind"], "incompatible")
        self.assertIn("tool_requirements", cfg.skipped_skills[0]["reason"])

    def test_undeclared_whitelist_or_harness_does_not_block(self):
        # Defense-in-depth only: an omitted charter declaration defers to the static
        # validator — the runtime filter never manufactures a skip from absence.
        cfg = self._resolve({"dev": {}})
        self.assertEqual([s.id for s in cfg.skills], ["sig-skill"])

    def test_skill_set_hash_unaffected_by_a_skip(self):
        mounted = self._resolve({"dev": {"agent_kind": "claude_code"}})
        skipped = self._resolve({"dev": {"agent_kind": "codex"}})
        empty = self.erc.resolve_role_config(
            {"tooling": {"dev": {"agent_kind": "codex"}}}, "dev",
            framework_root=self.tmp.name, catalog=self.catalog)
        self.assertNotEqual(mounted.skill_set_hash, skipped.skill_set_hash)
        self.assertEqual(skipped.skill_set_hash, empty.skill_set_hash)


class MissionSignalProfileValidatorTests(unittest.TestCase):

    def _validate(self, charter):
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(_HERE)), "validators"))
        import charter_validator as cv
        report = cv.Report()
        cv._check_mission_signal_profile(charter, report)
        return report

    def test_absent_field_is_noop(self):
        report = self._validate({"autonomy": {"approved_scope": {}}})
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_out_of_vocab_signal_errors(self):
        report = self._validate({"autonomy": {"approved_scope": {
            "task_signals": ["ui", "banana"]}}})
        self.assertFalse(report.ok)
        self.assertIn("banana", report.errors[0].message)

    def test_valid_but_catalog_inert_signal_warns(self):
        # every vocab word is valid; whether it matches a catalog skill depends on the
        # live registry — 'ui' matches today, so a clean profile yields no findings.
        report = self._validate({"autonomy": {"approved_scope": {
            "task_signals": ["ui"]}}})
        self.assertTrue(report.ok)


if __name__ == "__main__":
    unittest.main()
