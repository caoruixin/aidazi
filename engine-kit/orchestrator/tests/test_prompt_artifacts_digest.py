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


if __name__ == "__main__":
    unittest.main()
