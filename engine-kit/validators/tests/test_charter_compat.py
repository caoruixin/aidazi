"""Unit tests for charter_compat — acceptance namespace + mode normalization (P-A).

Design: archive/2026-06-20-autonomous-delivery-design.md §1.4. These exercise the
pure normalizer directly (no fixture dependency), including the malformed-input
cases that MUST NOT be silently overwritten (Codex P-A review, blocking #1).
"""
import os
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_KIT_DIR = os.path.dirname(os.path.dirname(_TESTS_DIR))  # engine-kit/
if _ENGINE_KIT_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_KIT_DIR)

import charter_compat as cc  # noqa: E402


def _acc(charter):
    return charter["tooling"]["acceptance"]


class NormalizeAcceptanceTests(unittest.TestCase):
    def test_absent_is_off_and_noop(self):
        ch = {"tooling": {}}
        self.assertEqual(cc.normalize_acceptance(ch), ([], []))
        self.assertEqual(cc.acceptance_mode(ch), "off")

    def test_enabled_true_maps_to_auto_silently(self):
        ch = {"tooling": {"acceptance": {"enabled": True}}}
        warn, err = cc.normalize_acceptance(ch)
        self.assertEqual(err, [])
        self.assertEqual(warn, [])  # enabled-only is SILENT (common existing shape)
        self.assertEqual(_acc(ch)["mode"], "auto")

    def test_enabled_false_maps_to_off_silently(self):
        ch = {"tooling": {"acceptance": {"enabled": False}}}
        cc.normalize_acceptance(ch)
        self.assertEqual(cc.acceptance_mode(ch), "off")

    def test_mode_only_untouched(self):
        ch = {"tooling": {"acceptance": {"mode": "advisory"}}}
        self.assertEqual(cc.normalize_acceptance(ch), ([], []))
        self.assertEqual(cc.acceptance_mode(ch), "advisory")

    def test_both_present_agree_warns_only(self):
        ch = {"tooling": {"acceptance": {"enabled": True, "mode": "auto"}}}
        warn, err = cc.normalize_acceptance(ch)
        self.assertEqual(err, [])
        self.assertTrue(any("enabled_deprecated" in m for m in warn))

    def test_both_present_conflict_is_error(self):
        ch = {"tooling": {"acceptance": {"enabled": True, "mode": "off"}}}
        warn, err = cc.normalize_acceptance(ch)
        self.assertTrue(err)

    def test_invalid_mode_is_error(self):
        ch = {"tooling": {"acceptance": {"mode": "bogus"}}}
        warn, err = cc.normalize_acceptance(ch)
        self.assertTrue(err)

    def test_top_level_block_moved_under_tooling_with_warning(self):
        ch = {"tooling": {"acceptance": {"harness": "x"}},
              "acceptance": {"enabled": True, "run_at": "milestone_close"}}
        warn, err = cc.normalize_acceptance(ch)
        self.assertEqual(err, [])
        self.assertNotIn("acceptance", ch)              # moved
        self.assertEqual(_acc(ch)["mode"], "auto")
        self.assertEqual(_acc(ch)["run_at"], "milestone_close")
        self.assertTrue(any("charter_namespace_deprecated" in m for m in warn))

    def test_top_level_move_value_conflict_is_error(self):
        ch = {"tooling": {"acceptance": {"run_at": "release_cut"}},
              "acceptance": {"run_at": "milestone_close"}}  # disagree
        warn, err = cc.normalize_acceptance(ch)
        self.assertTrue(any("conflicts" in m for m in err))

    # --- Blocking #1: malformed canonical input MUST NOT be overwritten/hidden. --
    def test_malformed_tooling_not_overwritten(self):
        ch = {"tooling": "garbage", "acceptance": {"enabled": True}}
        warn, err = cc.normalize_acceptance(ch)
        self.assertTrue(err)
        self.assertEqual(ch["tooling"], "garbage")      # untouched, not hidden

    def test_malformed_tooling_acceptance_not_overwritten(self):
        ch = {"tooling": {"acceptance": "garbage"}, "acceptance": {"enabled": True}}
        warn, err = cc.normalize_acceptance(ch)
        self.assertTrue(err)
        self.assertEqual(ch["tooling"]["acceptance"], "garbage")  # untouched

    def test_malformed_tooling_no_toplevel_is_safe_noop(self):
        # Malformed canonical `tooling` with NO top-level block must NOT raise
        # (Codex re-confirm) — normalize returns cleanly; acceptance_mode → off;
        # schema validation reports the structural error.
        ch = {"tooling": "garbage"}
        self.assertEqual(cc.normalize_acceptance(ch), ([], []))
        self.assertEqual(cc.acceptance_mode(ch), "off")
        self.assertEqual(ch["tooling"], "garbage")  # untouched

    def test_non_dict_charter_is_noop(self):
        self.assertEqual(cc.normalize_acceptance("not-a-charter"), ([], []))
        self.assertEqual(cc.acceptance_mode("not-a-charter"), "off")


if __name__ == "__main__":
    unittest.main()
