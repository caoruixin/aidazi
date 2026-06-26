"""Tests for the WP-EQ constraint-equivalence gate (stdlib unittest).

Test (1) runs the REAL inventory through ``check()``. Every other test is
hermetic: it builds a throwaway repo_root (temp dir) with a synthetic inventory
+ manifest so the individual gates can be exercised in isolation. The
source-coverage audit (REQUIRED_ANCHORS) is patched to an empty / single-source
map for the hermetic cases so unrelated coverage errors don't mask the gate
under test.
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_TESTS_DIR)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

import kernel_equivalence as ke  # noqa: E402


def _good_row(rid, anchor="governance/constitution.md §1.3",
              enforcement="none-judgment", roles=None):
    return {
        "id": rid,
        "anchor": anchor,
        "statement": "Some imperative sentence.",
        "roles": list(roles) if roles else ["dev"],
        "condition": "always",
        "current_enforcement": enforcement,
    }


@unittest.skipIf(yaml is None, "PyYAML not installed")
class _RepoBuilderMixin(unittest.TestCase):
    """Helper to materialise a temp repo_root for hermetic check() runs."""

    def _make_repo(self, inv_files, *, manifest_sources=None,
                   extra_files=None, write_manifest=True):
        root = Path(tempfile.mkdtemp(prefix="wpeq_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        inv = root / "engine-kit" / "tools" / "constraint-inventory"
        inv.mkdir(parents=True)
        for rel, content in (extra_files or {}).items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        for name, rows in inv_files.items():
            (inv / name).write_text(
                yaml.safe_dump(rows, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        if write_manifest:
            if manifest_sources is None:
                (root / "SRC.md").write_bytes(b"src")
                manifest_sources = [
                    {"path": "SRC.md", "sha256": hashlib.sha256(b"src").hexdigest()}
                ]
            (inv / "_sources.yaml").write_text(
                yaml.safe_dump({"version": 1, "sources": manifest_sources},
                               sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        return root

    def _patch_required_anchors(self, value):
        original = ke.REQUIRED_ANCHORS
        ke.REQUIRED_ANCHORS = value
        self.addCleanup(lambda: setattr(ke, "REQUIRED_ANCHORS", original))
        # Hermetic repos use synthetic filenames, so the real per-file row-count
        # floors don't apply — zero them out unless a test sets its own.
        self._patch_min_rows({})
        # Hermetic anchors/manifests are synthetic; disable the anchor-shape check
        # unless a test opts in.
        self._patch_anchor_shape(False)

    def _patch_min_rows(self, value):
        original = ke.EXPECTED_MIN_ROWS
        ke.EXPECTED_MIN_ROWS = value
        self.addCleanup(lambda: setattr(ke, "EXPECTED_MIN_ROWS", original))

    def _patch_anchor_shape(self, enabled):
        original = ke.ENABLE_ANCHOR_SHAPE_CHECK
        ke.ENABLE_ANCHOR_SHAPE_CHECK = enabled
        self.addCleanup(lambda: setattr(ke, "ENABLE_ANCHOR_SHAPE_CHECK", original))


@unittest.skipIf(yaml is None, "PyYAML not installed")
class RealInventoryTests(unittest.TestCase):
    """Test (1): the real, shipped inventory must pass cleanly."""

    def test_real_inventory_check_is_ok(self):
        result = ke.check()
        self.assertEqual(result["errors"], [], msg=f"unexpected errors: {result['errors']}")
        self.assertTrue(result["ok"])
        self.assertGreater(result["stats"]["total_rows"], 0)
        # none-judgment stats are reported.
        self.assertIn("none_judgment_count", result["stats"])
        self.assertIn("none_judgment_pct", result["stats"])


class WellformednessTests(_RepoBuilderMixin):
    """Test (2): missing key / bad role / bad current_enforcement are caught."""

    def setUp(self):
        # Isolate the well-formedness gate from the coverage audit.
        self._patch_required_anchors({})

    def test_good_inventory_passes(self):
        root = self._make_repo({"01-x.yaml": [_good_row("a-1"), _good_row("a-2")]})
        result = ke.check(repo_root=root)
        self.assertEqual(result["errors"], [], msg=str(result["errors"]))
        self.assertTrue(result["ok"])

    def test_missing_key_detected(self):
        bad = _good_row("a-1")
        del bad["roles"]
        root = self._make_repo({"01-x.yaml": [bad]})
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing required key" in e for e in result["errors"]),
                        msg=str(result["errors"]))

    def test_bad_role_detected(self):
        root = self._make_repo({"01-x.yaml": [_good_row("a-1", roles=["wizard"])]})
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("not in allowed set" in e for e in result["errors"]),
                        msg=str(result["errors"]))

    def test_bad_current_enforcement_detected(self):
        root = self._make_repo(
            {"01-x.yaml": [_good_row("a-1", enforcement="enforced-by-vibes")]})
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("does not match enforcement pattern" in e for e in result["errors"]),
                        msg=str(result["errors"]))


class SourceHashTests(_RepoBuilderMixin):
    """Test (3): a manifest hash that no longer matches the source is flagged."""

    def setUp(self):
        self._patch_required_anchors({})

    def test_stale_source_detected(self):
        root = self._make_repo(
            {"01-x.yaml": [_good_row("a-1")]},
            extra_files={"GOV.md": b"the real bytes"},
            manifest_sources=[{"path": "GOV.md", "sha256": "0" * 64}],
        )
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("changed (inventory stale)" in e for e in result["errors"]),
            msg=str(result["errors"]),
        )

    def test_missing_source_detected(self):
        root = self._make_repo(
            {"01-x.yaml": [_good_row("a-1")]},
            manifest_sources=[{"path": "NOPE.md", "sha256": "0" * 64}],
        )
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("NOPE.md missing" in e for e in result["errors"]),
                        msg=str(result["errors"]))


class CoverageAuditTests(_RepoBuilderMixin):
    """Test (4): a required source anchor that no row covers is an error."""

    def setUp(self):
        # Audit only the delivery-loop §4.2.8 family so the case is isolated.
        self._patch_required_anchors(
            {"process/delivery-loop.md": ["§4.2.8 #%d" % i for i in range(1, 15)]}
        )

    def test_missing_anchor_detected(self):
        # Cover #1..#14 EXCEPT #7.
        rows = [
            _good_row("dl-%d" % i, anchor="process/delivery-loop.md §4.2.8 #%d" % i)
            for i in range(1, 15) if i != 7
        ]
        root = self._make_repo({"05-delivery-loop.yaml": rows})
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertIn(
            "uncovered source anchor §4.2.8 #7 in process/delivery-loop.md",
            result["errors"],
        )
        # A covered anchor must NOT be reported uncovered.
        self.assertFalse(any("§4.2.8 #6 in" in e for e in result["errors"]),
                         msg=str(result["errors"]))

    def test_substring_collision_not_satisfied(self):
        # EXACT matching: providing only #10..#14 must NOT satisfy required #1..#4
        # (the naive `tok in anchor` substring check would have wrongly passed #1).
        rows = [
            _good_row("dl-%d" % i, anchor="process/delivery-loop.md §4.2.8 #%d" % i)
            for i in range(10, 15)
        ]
        root = self._make_repo({"05-delivery-loop.yaml": rows})
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertIn(
            "uncovered source anchor §4.2.8 #1 in process/delivery-loop.md",
            result["errors"], msg=str(result["errors"]))
        # #10..#14 are covered, so they must NOT be flagged.
        self.assertFalse(any("§4.2.8 #14 in" in e for e in result["errors"]),
                         msg=str(result["errors"]))


class DuplicateIdTests(_RepoBuilderMixin):
    """Test (5): the same id in two files is a duplicate error."""

    def setUp(self):
        self._patch_required_anchors({})

    def test_duplicate_id_detected(self):
        root = self._make_repo({
            "01-a.yaml": [_good_row("shared-id")],
            "02-b.yaml": [_good_row("shared-id")],
        })
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("duplicate id 'shared-id'" in e for e in result["errors"]),
                        msg=str(result["errors"]))


class RowCountFloorTests(_RepoBuilderMixin):
    """Test (6): a per-file row-count below its floor is caught (anti-bulk-deletion)."""

    def setUp(self):
        self._patch_required_anchors({})  # also zeroes EXPECTED_MIN_ROWS
        self._patch_min_rows({"01-x.yaml": 3})  # this test's own floor

    def test_below_floor_detected(self):
        root = self._make_repo({"01-x.yaml": [_good_row("a-1"), _good_row("a-2")]})
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("< expected floor 3" in e for e in result["errors"]),
                        msg=str(result["errors"]))

    def test_at_floor_passes(self):
        root = self._make_repo(
            {"01-x.yaml": [_good_row("a-1"), _good_row("a-2"), _good_row("a-3")]})
        result = ke.check(repo_root=root)
        self.assertEqual(result["errors"], [], msg=str(result["errors"]))
        self.assertTrue(result["ok"])

    def test_missing_expected_file_detected(self):
        root = self._make_repo({"02-y.yaml": [_good_row("b-1")]})  # 01-x.yaml absent
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("expected inventory file 01-x.yaml is missing" in e
                            for e in result["errors"]), msg=str(result["errors"]))


class AnchorShapeTests(_RepoBuilderMixin):
    """Test (7): an anchor not starting with a manifest source path / missing ' §'."""

    def setUp(self):
        self._patch_required_anchors({})  # disables anchor-shape...
        self._patch_anchor_shape(True)    # ...then re-enable it for this class

    def test_bad_anchor_detected(self):
        rows = [_good_row("a-1", anchor="not-a-source placeholder")]  # no source, no ' §'
        root = self._make_repo(
            {"01-x.yaml": rows},
            extra_files={"GOV.md": b"src"},
            manifest_sources=[{"path": "GOV.md",
                               "sha256": hashlib.sha256(b"src").hexdigest()}],
        )
        result = ke.check(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("must start with a manifest source path" in e
                            for e in result["errors"]), msg=str(result["errors"]))

    def test_good_anchor_passes(self):
        rows = [_good_row("a-1", anchor="GOV.md §1.2")]
        root = self._make_repo(
            {"01-x.yaml": rows},
            extra_files={"GOV.md": b"src"},
            manifest_sources=[{"path": "GOV.md",
                               "sha256": hashlib.sha256(b"src").hexdigest()}],
        )
        result = ke.check(repo_root=root)
        self.assertEqual(result["errors"], [], msg=str(result["errors"]))


if __name__ == "__main__":
    unittest.main()
