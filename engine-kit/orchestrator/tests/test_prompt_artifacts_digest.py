#!/usr/bin/env python3
"""Phase-2 §3.5 [R0.3 B-2] — prompt_artifacts_digest: binding the generated
compact Dev/Review prompt files into campaign_plan_signoff, mirroring the
shipped milestone_signals_digest pattern (Commit B′ of
archive/2026-07-09-phase2-requirement-chain-design.md).

Covers: dormancy in BOTH directions (no repo/files ⇒ key omitted; digest-less
legacy plan stays 'signed' even when files exist at verify time), stamp binds
both copies, post-sign edit/deletion ⇒ 'stale', unresolvable repo_dir on a
digest-bearing plan ⇒ 'stale' (fail-closed), copy mismatch ⇒ 'stale' +
snapshot NOT-authentic, and the TD6 verify-then-carry-forward rule [R0.4 B-1]:
an engine restamp preserves both copies VERBATIM, keeps unchanged prompts
'signed', and can NEVER bless a post-sign prompt edit.
"""
import copy
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import campaign as cp  # noqa: E402

CHARTER = {"mission": {"id": "M-test"}}
PLAN = {"campaign_id": "c1", "goal": "g", "milestones": [
    {"id": "m1", "objective": "o1", "subsprint_sequence": ["s1", "s2"]},
]}


def _mk_repo(td, sids=("s1", "s2"), kinds=("dev", "review")):
    repo = os.path.join(td, "repo")
    os.makedirs(os.path.join(repo, "compact"), exist_ok=True)
    for sid in sids:
        for kind in kinds:
            with open(os.path.join(repo, "compact",
                                   f"{sid}-{kind}-prompt.md"), "w") as fh:
                fh.write(f"---\ncontext_budget:\n  self_contained: true\n---\n"
                         f"{kind} prompt for {sid}\n")
    # A real (tiny) git repo: campaign runs with repo_dir invoke Loop Ingress.
    import subprocess
    subprocess.run(["git", "-C", repo, "init", "-q"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", repo, "-c", "user.name=t",
                    "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                    "-m", "init"], check=True, capture_output=True)
    return repo


def _sign(plan, repo=None):
    return cp.stamp_signoff(plan, CHARTER, signed_at="2026-07-09T00:00:00Z",
                            charter_ref="charter.yaml", repo_dir=repo)


class TestDigestDormancy(unittest.TestCase):
    def test_none_without_repo_or_files(self):
        self.assertIsNone(cp.prompt_artifacts_digest(PLAN, None))
        self.assertIsNone(cp.prompt_artifacts_digest(PLAN, "/nonexistent"))
        with tempfile.TemporaryDirectory() as td:
            empty = os.path.join(td, "repo")
            os.makedirs(os.path.join(empty, "compact"))
            self.assertIsNone(cp.prompt_artifacts_digest(PLAN, empty))

    def test_stamp_omits_key_when_dormant(self):
        signed = _sign(PLAN, repo=None)
        self.assertNotIn("prompt_artifacts_digest", signed["signoff"])
        self.assertNotIn("prompt_artifacts_digest",
                         signed["signoff"]["scope_envelope"])
        # Legacy signing behavior is byte-identical: the plan reads 'signed'
        # regardless of repo_dir at verify time.
        self.assertEqual(cp.signoff_status(signed, CHARTER, None), "signed")

    def test_digestless_legacy_plan_stays_signed_even_with_files(self):
        signed = _sign(PLAN, repo=None)  # signed WITHOUT a digest
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)  # files exist at VERIFY time
            self.assertEqual(
                cp.signoff_status(signed, CHARTER, None, repo_dir=repo),
                "signed")


class TestDigestBindingAndStaleness(unittest.TestCase):
    def test_stamp_binds_both_copies_and_reads_signed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)
            signed = _sign(PLAN, repo=repo)
            pad = signed["signoff"].get("prompt_artifacts_digest")
            self.assertIsNotNone(pad)
            self.assertEqual(
                signed["signoff"]["scope_envelope"]["prompt_artifacts_digest"],
                pad)
            self.assertTrue(cp.signoff_snapshot_authentic(signed))
            self.assertEqual(
                cp.signoff_status(signed, CHARTER, None, repo_dir=repo),
                "signed")

    def test_post_sign_edit_stale_and_resign_clears(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)
            signed = _sign(PLAN, repo=repo)
            target = os.path.join(repo, "compact", "s1-dev-prompt.md")
            with open(target, "a") as fh:
                fh.write("POST-SIGN EDIT\n")
            self.assertEqual(
                cp.signoff_status(signed, CHARTER, None, repo_dir=repo),
                "stale")
            resigned = _sign(signed, repo=repo)  # human re-signs over the edit
            self.assertEqual(
                cp.signoff_status(resigned, CHARTER, None, repo_dir=repo),
                "signed")

    def test_bound_file_deletion_stale(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)
            signed = _sign(PLAN, repo=repo)
            os.remove(os.path.join(repo, "compact", "s2-review-prompt.md"))
            self.assertEqual(
                cp.signoff_status(signed, CHARTER, None, repo_dir=repo),
                "stale")

    def test_unresolvable_repo_on_digest_bearing_plan_stale(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)
            signed = _sign(PLAN, repo=repo)
            # No repo_dir at verify time ⇒ live recompute None ≠ stored ⇒ stale
            # (fail-closed; the actionable fix is passing --repo-dir).
            self.assertEqual(cp.signoff_status(signed, CHARTER, None), "stale")

    def test_copy_mismatch_stale_and_snapshot_not_authentic(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)
            signed = _sign(PLAN, repo=repo)
            stripped = copy.deepcopy(signed)
            del stripped["signoff"]["prompt_artifacts_digest"]  # naive strip
            self.assertEqual(
                cp.signoff_status(stripped, CHARTER, None, repo_dir=repo),
                "stale")
            self.assertFalse(cp.signoff_snapshot_authentic(stripped))


class TestRestampCarryForward(unittest.TestCase):
    def _grown(self, signed, repo):
        """Simulate the TD6 deliver_followup epoch: a gapfix sid inserted into
        the LIVE plan + the pinned engine_restamp reconstructed from the STORED
        envelope + the delta (exactly what the runner records)."""
        grown = copy.deepcopy(signed)
        grown["milestones"][0]["subsprint_sequence"].append("gapfix-1")
        delta = {"milestone_id": "m1", "subsprint_id": "gapfix-1",
                 "at_index": 2}
        estar = cp._reconstruct_authorized_envelope(
            grown["signoff"]["scope_envelope"], [delta])
        pinned = cp._hash_from_envelope(grown, CHARTER, grown["signoff"],
                                        estar)
        return grown, {"signed_scope_hash": pinned, "deltas": [delta]}

    def test_restamp_preserves_digest_and_stays_signed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)
            signed = _sign(PLAN, repo=repo)
            pad = signed["signoff"]["prompt_artifacts_digest"]
            grown, restamp = self._grown(signed, repo)
            # The grown plan is H-stale on its own (the insertion) …
            self.assertEqual(
                cp.signoff_status(grown, CHARTER, None, repo_dir=repo),
                "stale")
            out = cp.apply_engine_restamp_to_plan(grown, CHARTER, restamp,
                                                  None, repo_dir=repo)
            # … the authorized restamp rescues it AND carries BOTH digest
            # copies VERBATIM [R0.4 B-1] (gapfix sids have no compact files, so
            # the carried digest stays live-accurate).
            self.assertEqual(out["signoff"]["prompt_artifacts_digest"], pad)
            self.assertEqual(
                out["signoff"]["scope_envelope"]["prompt_artifacts_digest"],
                pad)
            self.assertEqual(
                cp.signoff_status(out, CHARTER, None, repo_dir=repo), "signed")

    def test_restamp_never_blesses_a_post_sign_edit(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)
            signed = _sign(PLAN, repo=repo)
            grown, restamp = self._grown(signed, repo)
            with open(os.path.join(repo, "compact", "s1-dev-prompt.md"),
                      "a") as fh:
                fh.write("POST-SIGN EDIT\n")
            self.assertEqual(
                cp.signoff_status(grown, CHARTER, None, repo_dir=repo),
                "stale")
            out = cp.apply_engine_restamp_to_plan(grown, CHARTER, restamp,
                                                  None, repo_dir=repo)
            # The restamp may rescue the H epoch, but the prompt-artifact
            # staleness PERSISTS at every freshness consumer — the edit is
            # never blessed; a human must re-sign over it.
            self.assertEqual(
                cp.signoff_status(out, CHARTER, None, repo_dir=repo), "stale")


def _clock():
    n = {"i": 0}

    def clock():
        n["i"] += 1
        return f"2026-07-09T00:{n['i']:02d}:00Z"
    return clock


class LiveCampaignFollowupDigestTests(unittest.TestCase):
    """[R2 B-2] the LIVE TD6 path (`Campaign._restamp_followup_epoch`, not the
    pure helper) on a DIGEST-BEARING campaign: dispatch → acceptance_fix_required
    → deliver_followup insertion → resume must stay autonomous ('signed' via the
    engine re-stamp, ZERO campaign_plan_signoff pause) with the prompt-artifact
    digest surviving the envelope rebuild — and a paired prompt EDIT must be
    refused (block for the human re-sign), never laundered."""

    LIVE_PLAN = {"campaign_id": "camp-pad", "goal": "deliver the thing",
                 "signed_by_human": True, "milestones": [
                     {"id": "m1", "objective": "objective m1",
                      "subsprint_sequence": ["s1", "s2"]}]}
    SCRIPT = {"s1": {"final_state": "advance", "spawn_count": 1},
              "s2": {"final_state": "halted", "spawn_count": 1,
                     "pause_reason": "acceptance_fix_required"},
              "s_fix": {"final_state": "done", "spawn_count": 1}}

    @staticmethod
    def _run_unit(subsprint_id, **_kw):
        return dict(LiveCampaignFollowupDigestTests.SCRIPT[subsprint_id])

    @staticmethod
    def _fix_route(reason, cpt):
        return ({"confirm": "yes", "route": "deliver_fix_iteration"}
                if reason == "acceptance_fix_required" else None)

    def _drive_to_followup(self, td, repo):
        plan = cp.stamp_signoff(copy.deepcopy(self.LIVE_PLAN), CHARTER,
                                signed_at="2026-07-09T00:00:00Z",
                                charter_ref="charter.yaml", repo_dir=repo)
        self.assertIn("prompt_artifacts_digest", plan["signoff"])
        home = os.path.join(td, "camp")

        def fresh(p):
            import json as _json
            return _json.loads(_json.dumps(p))

        st = cp.run_campaign(fresh(plan), home, self._run_unit,
                             clock=_clock(), charter=CHARTER, repo_dir=repo)
        self.assertEqual(st.pause_reason, "acceptance_fix_required")
        st = cp.run_campaign(fresh(plan), home, self._run_unit,
                             clock=_clock(), charter=CHARTER, repo_dir=repo,
                             resume=True, decision_resolver=self._fix_route)
        self.assertEqual(st.pause_reason, "deliver_followup_required")
        # Deliver inserts the follow-up in the PLAN FILE (signoff untouched).
        plan["milestones"][0]["subsprint_sequence"] = ["s1", "s2", "s_fix"]
        return plan, home, fresh

    def test_live_followup_restamp_survives_digest_and_stays_signed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)
            plan, home, fresh = self._drive_to_followup(td, repo)
            st = cp.run_campaign(fresh(plan), home, self._run_unit,
                                 clock=_clock(), charter=CHARTER,
                                 repo_dir=repo, resume=True)
            self.assertEqual(st.status, cp.STATUS_DONE)
            self.assertNotEqual(st.pause_reason, "campaign_plan_signoff")
            self.assertIsNotNone(st.engine_restamp)

    def test_live_followup_paired_with_prompt_edit_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _mk_repo(td)
            plan, home, fresh = self._drive_to_followup(td, repo)
            with open(os.path.join(repo, "compact", "s1-dev-prompt.md"),
                      "a") as fh:
                fh.write("POST-SIGN EDIT\n")
            st = cp.run_campaign(fresh(plan), home, self._run_unit,
                                 clock=_clock(), charter=CHARTER,
                                 repo_dir=repo, resume=True)
            # [R2.2 NB-2] the epoch is NOT advanced over an edited prompt: the
            # campaign specifically PAUSES FOR RE-SIGN (never finishes, never
            # records the follow-up as an engine-restamped epoch).
            self.assertNotEqual(st.status, cp.STATUS_DONE)
            self.assertEqual(st.pause_reason, "campaign_plan_signoff")
            self.assertIsNone(st.engine_restamp)


if __name__ == "__main__":
    unittest.main()
