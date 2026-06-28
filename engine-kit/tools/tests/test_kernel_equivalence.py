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


@unittest.skipIf(yaml is None, "PyYAML not installed")
class KernelCoverageTests(_RepoBuilderMixin):
    """WP-2: check_kernel_coverage proves the constitution-core kernel carries every constitution
    inventory row — completeness (a), no-dangling (b), resolution (c)."""

    def _cov_repo(self, kernel_text, cov_rows, source_rows, *, write_kernel=True):
        inv_files = {
            "01-src.yaml": source_rows,
            "_kernel_coverage.yaml": {
                "kernel": "governance/constitution-core.md",
                "source_files": ["01-src.yaml"],
                "rows": cov_rows,
            },
        }
        extra = ({"governance/constitution-core.md": kernel_text.encode("utf-8")}
                 if write_kernel else None)
        return self._make_repo(inv_files=inv_files, extra_files=extra)

    def test_real_kernel_coverage_is_100pct(self):
        # The real constitution-core draft carries all 65 constitution rows.
        result = ke.check_kernel_coverage()
        self.assertTrue(result["ok"], msg=str(result.get("errors")))
        self.assertEqual(result["stats"]["coverage_pct"], 100.0)
        self.assertEqual(result["stats"]["total"], 65)

    def test_complete_map_passes(self):
        root = self._cov_repo(
            "Clause A forbids hardcode. Clause B requires a fresh session.",
            {"r-a": "forbids hardcode", "r-b": "requires a fresh session"},
            [_good_row("r-a"), _good_row("r-b")])
        result = ke.check_kernel_coverage(repo_root=root)
        self.assertTrue(result["ok"], msg=str(result["errors"]))
        self.assertEqual(result["stats"]["covered"], 2)

    def test_missing_phrase_in_kernel_is_caught(self):
        root = self._cov_repo(
            "Clause A forbids hardcode.",   # B's phrase is NOT in the kernel
            {"r-a": "forbids hardcode", "r-b": "requires a fresh session"},
            [_good_row("r-a"), _good_row("r-b")])
        result = ke.check_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertIn("r-b", result["stats"]["missing_phrase"])

    def test_uncovered_inventory_row_is_caught(self):
        root = self._cov_repo(
            "Clause A forbids hardcode. Clause B requires a fresh session.",
            {"r-a": "forbids hardcode"},    # r-b exists in inventory but is unmapped
            [_good_row("r-a"), _good_row("r-b")])
        result = ke.check_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertIn("r-b", result["stats"]["uncovered_rows"])

    def test_dangling_map_id_is_caught(self):
        root = self._cov_repo(
            "Clause A forbids hardcode.",
            {"r-a": "forbids hardcode", "r-ghost": "x"},   # ghost not in inventory
            [_good_row("r-a")])
        result = ke.check_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertIn("r-ghost", result["stats"]["dangling"])

    def test_normalization_ignores_wrap_and_markdown(self):
        # The phrase matches across a line-wrap AND through `code`/**bold** decoration.
        root = self._cov_repo(
            "the agent carries `no more`\n  **context** than necessary, always.",
            {"r-a": "no more context than necessary"},
            [_good_row("r-a")])
        result = ke.check_kernel_coverage(repo_root=root)
        self.assertTrue(result["ok"], msg=str(result["errors"]))

    def test_absent_kernel_reports_clearly(self):
        root = self._cov_repo("unused", {"r-a": "x"}, [_good_row("r-a")],
                              write_kernel=False)
        result = ke.check_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("not found" in e for e in result["errors"]))

    def test_multi_phrase_requires_every_subpart(self):
        # A LIST value requires ALL phrases — a multi-subpart constraint cannot pass on one
        # fragment while a mandatory subpart is dropped (Codex WP-2 B5). Here the network
        # boundary is missing from the kernel, so the row fails.
        subparts = ["workspace_write sandbox", "MUST NOT git push",
                    "network per charter.tooling.dev.network_access"]
        root = self._cov_repo(
            "Dev runs in a workspace_write sandbox; MUST NOT git push.",
            {"r-dev": subparts}, [_good_row("r-dev")])
        result = ke.check_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertIn("r-dev", result["stats"]["missing_phrase"])
        # With every subpart present, it passes.
        root2 = self._cov_repo(
            "Dev runs in a workspace_write sandbox with network per "
            "charter.tooling.dev.network_access; MUST NOT git push.",
            {"r-dev": subparts}, [_good_row("r-dev")])
        self.assertTrue(ke.check_kernel_coverage(repo_root=root2)["ok"])

    def test_front_matter_and_deferred_sections_excluded(self):
        # A phrase present ONLY in the YAML front-matter or the trailing "Deferred …" section
        # does NOT resolve — matching is over the normative clause body only.
        kernel = (
            "---\ntitle: x\nmarker_in_frontmatter here\n---\n\n"
            "## §1 body\n- the real clause text here.\n\n"
            "## Deferred to the canonical\n- marker_only_in_deferred appears here.\n")
        root = self._cov_repo(
            kernel,
            {"r-fm": "marker_in_frontmatter", "r-real": "the real clause text",
             "r-def": "marker_only_in_deferred"},
            [_good_row("r-fm"), _good_row("r-real"), _good_row("r-def")])
        result = ke.check_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertIn("r-fm", result["stats"]["missing_phrase"])   # front-matter excluded
        self.assertIn("r-def", result["stats"]["missing_phrase"])  # deferred tail excluded
        self.assertNotIn("r-real", result["stats"]["missing_phrase"])  # body resolves


@unittest.skipIf(yaml is None, "PyYAML not installed")
class AuthoringKernelCoverageTests(_RepoBuilderMixin):
    """WP-3: check_authoring_kernel_coverage proves the authoring-kernel carries every
    doc-governance inventory row (03-doc-governance.yaml); and the merged --authoring-kernel-
    coverage CLI fails closed when the inventory/source-hash gate fails (a stale canonical
    governance/doc_governance.md ⇒ stale kernel). The generic completeness / no-dangling /
    resolution / normalization / multi-phrase logic is shared with KernelCoverageTests via
    ``_kernel_coverage_for`` and is not re-asserted here."""

    def test_real_authoring_kernel_coverage_is_100pct(self):
        # The real authoring-kernel draft carries all 41 doc-governance rows, non-vacuously
        # (compound rows list a phrase per mandatory subpart — see _authoring_kernel_coverage.yaml).
        result = ke.check_authoring_kernel_coverage()
        self.assertTrue(result["ok"], msg=str(result.get("errors")))
        self.assertEqual(result["stats"]["coverage_pct"], 100.0)
        self.assertEqual(result["stats"]["total"], 41)
        self.assertEqual(result["stats"]["missing_phrase"], [])
        self.assertEqual(result["stats"]["uncovered_rows"], [])
        self.assertEqual(result["stats"]["dangling"], [])

    def test_merged_authoring_coverage_on_real_tree_passes(self):
        merged = ke._merged_coverage(str(ke.REPO_ROOT_DEFAULT),
                                     ke.check_authoring_kernel_coverage)
        self.assertTrue(merged["ok"], msg=str(merged.get("errors")))

    def test_merged_fails_closed_when_source_hash_gate_fails(self):
        # The merged CLI ANDs the inventory/source-hash gate with coverage: a stale canonical
        # (check() not ok) fails the kernel even if every phrase still resolves — a changed
        # canonical means re-review + regenerate, never silent reuse (Codex fidelity gate).
        orig_check = ke.check
        ke.check = lambda repo_root=None: {
            "ok": False,
            "errors": ["source governance/doc_governance.md changed (inventory stale) — "
                       "re-review + regenerate affected kernel"],
            "warnings": [], "stats": {},
        }
        try:
            merged = ke._merged_coverage(str(ke.REPO_ROOT_DEFAULT),
                                         ke.check_authoring_kernel_coverage)
        finally:
            ke.check = orig_check
        self.assertFalse(merged["ok"])
        self.assertTrue(any(e.startswith("[inventory/source-hash gate]")
                            for e in merged["errors"]), msg=str(merged["errors"]))


@unittest.skipIf(yaml is None, "PyYAML not installed")
class AcceptanceKernelCoverageTests(_RepoBuilderMixin):
    """WP-4: check_acceptance_kernel_coverage proves the acceptance-kernel carries every
    Acceptance-verdict-affecting constraint anchored in the two whole-file reads WP-4B retires
    (process/delivery-loop.md + process/role-skill-model.md), with a per-row disposition —
    completeness over the anchored+role-tagged scope; kernel-clause phrases resolve; bound-elsewhere
    matches the inventory enforcement (and a none-judgment row may NOT be bound-elsewhere)."""

    DL = "process/delivery-loop.md §4.2.4"
    RC = "role-cards/acceptance-agent.md §2"

    def _acc_cov_repo(self, kernel_text, closure_rows, source_rows,
                      supplemental_rows=None, supplemental_src=None, symbols=("_spawn",)):
        inv_files = {
            "05-delivery-loop.yaml": source_rows,
            "_acceptance_kernel_coverage.yaml": {
                "kernel": "governance/acceptance-kernel.md",
                "role": "acceptance",
                "inlined_files": ["process/delivery-loop.md", "process/role-skill-model.md"],
                "inventory_files": ["05-delivery-loop.yaml"],
                "closure_rows": closure_rows,
                "supplemental_rows": supplemental_rows or {},
            },
        }
        if supplemental_src is not None:
            inv_files["07-roles.yaml"] = supplemental_src
        # A stub engine-kit source so bound-elsewhere `driver:`/`validator:` symbols RESOLVE in the
        # corpus (the real resolution check, hermetically) — a symbol NOT listed here will not resolve.
        stub = "\n".join(f"def {s}(): ..." for s in symbols).encode("utf-8")
        extra = {"governance/acceptance-kernel.md": kernel_text.encode("utf-8"),
                 "engine-kit/orchestrator/_stub.py": stub}
        return self._make_repo(inv_files=inv_files, extra_files=extra)

    def test_real_acceptance_kernel_coverage_is_complete(self):
        # The real acceptance-kernel draft classifies all 44 Acceptance-anchored delivery-loop +
        # role-skill rows and carries every kernel-clause phrase + the 6-gap supplemental phrases.
        result = ke.check_acceptance_kernel_coverage()
        self.assertTrue(result["ok"], msg=str(result.get("errors")))
        st = result["stats"]
        self.assertEqual(st["closure_scope"], 44)
        self.assertEqual(st["closure_mapped"], 44)
        self.assertEqual(st["kernel_clause"] + st["bound_elsewhere"], 44)
        self.assertGreater(st["supplemental"], 0)

    def test_merged_acceptance_coverage_on_real_tree_passes(self):
        merged = ke._merged_coverage(str(ke.REPO_ROOT_DEFAULT),
                                     ke.check_acceptance_kernel_coverage)
        self.assertTrue(merged["ok"], msg=str(merged.get("errors")))

    def test_complete_classification_passes(self):
        root = self._acc_cov_repo(
            "Clause A: you cannot run scripts. Clause B is orchestrator wiring.",
            {"dl-a": {"disposition": "kernel-clause", "phrase": "you cannot run scripts"},
             "dl-b": {"disposition": "bound-elsewhere", "enforced_by": "driver:_spawn"}},
            [_good_row("dl-a", anchor=self.DL, roles=["acceptance"]),
             _good_row("dl-b", anchor=self.DL, enforcement="driver:_spawn", roles=["acceptance"])])
        result = ke.check_acceptance_kernel_coverage(repo_root=root)
        self.assertTrue(result["ok"], msg=str(result["errors"]))

    def test_uncovered_scoped_row_is_caught(self):
        # dl-b is anchored in an inlined file + role acceptance but unmapped → completeness fails.
        root = self._acc_cov_repo(
            "Clause A: you cannot run scripts.",
            {"dl-a": {"disposition": "kernel-clause", "phrase": "you cannot run scripts"}},
            [_good_row("dl-a", anchor=self.DL, roles=["acceptance"]),
             _good_row("dl-b", anchor=self.DL, roles=["acceptance"])])
        result = ke.check_acceptance_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("uncovered Acceptance constraint" in e and "dl-b" in e
                            for e in result["errors"]), msg=str(result["errors"]))

    def test_out_of_scope_row_not_required(self):
        # A delivery-loop row NOT tagged acceptance (or not anchored in an inlined file) is out of
        # scope — it need not be classified.
        root = self._acc_cov_repo(
            "Clause A: you cannot run scripts.",
            {"dl-a": {"disposition": "kernel-clause", "phrase": "you cannot run scripts"}},
            [_good_row("dl-a", anchor=self.DL, roles=["acceptance"]),
             _good_row("dl-rev", anchor=self.DL, roles=["review"]),
             _good_row("dl-other", anchor="process/other.md §1", roles=["acceptance"])])
        result = ke.check_acceptance_kernel_coverage(repo_root=root)
        self.assertTrue(result["ok"], msg=str(result["errors"]))

    def test_dangling_closure_row_is_caught(self):
        root = self._acc_cov_repo(
            "Clause A: you cannot run scripts.",
            {"dl-a": {"disposition": "kernel-clause", "phrase": "you cannot run scripts"},
             "dl-ghost": {"disposition": "kernel-clause", "phrase": "x"}},
            [_good_row("dl-a", anchor=self.DL, roles=["acceptance"])])
        result = ke.check_acceptance_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("not a scoped Acceptance constraint" in e and "dl-ghost" in e
                            for e in result["errors"]), msg=str(result["errors"]))

    def test_kernel_clause_missing_phrase_is_caught(self):
        root = self._acc_cov_repo(
            "Clause A present.",   # the mapped phrase is NOT in the kernel
            {"dl-a": {"disposition": "kernel-clause", "phrase": "this phrase is absent"}},
            [_good_row("dl-a", anchor=self.DL, roles=["acceptance"])])
        result = ke.check_acceptance_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing clause" in e and "dl-a" in e for e in result["errors"]))

    def test_none_judgment_row_cannot_be_bound_elsewhere(self):
        # The airtight rule: a row with no programmatic backstop (none-judgment) MUST be carried by
        # the kernel — it cannot be excused as bound-elsewhere.
        root = self._acc_cov_repo(
            "Clause A present.",
            {"dl-a": {"disposition": "bound-elsewhere", "enforced_by": "none-judgment"}},
            [_good_row("dl-a", anchor=self.DL, enforcement="none-judgment", roles=["acceptance"])])
        result = ke.check_acceptance_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("none-judgment" in e and "MUST be kernel-clause" in e
                            for e in result["errors"]), msg=str(result["errors"]))

    def test_bound_elsewhere_symbol_must_match_inventory(self):
        # bound-elsewhere cannot claim an enforcement the inventory does not record (no faking a
        # backstop to drop a constraint).
        root = self._acc_cov_repo(
            "Clause A present.",
            {"dl-a": {"disposition": "bound-elsewhere", "enforced_by": "driver:_made_up"}},
            [_good_row("dl-a", anchor=self.DL, enforcement="driver:_spawn", roles=["acceptance"])])
        result = ke.check_acceptance_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("enforced_by" in e and "!= inventory" in e for e in result["errors"]))

    def test_bound_elsewhere_unresolved_symbol_is_caught(self):
        # The airtight half of bound-elsewhere: enforced_by matches the inventory, but the symbol does
        # NOT exist in the engine-kit corpus — a fabricated backstop cannot excuse a constraint from
        # the kernel (the base inventory gate only WARNS on this; here it is a hard error).
        root = self._acc_cov_repo(
            "Clause A present.",
            {"dl-a": {"disposition": "bound-elsewhere", "enforced_by": "driver:_ghost_symbol"}},
            [_good_row("dl-a", anchor=self.DL, enforcement="driver:_ghost_symbol",
                       roles=["acceptance"])],
            symbols=("_spawn",))   # _ghost_symbol is NOT in the stub corpus
        result = ke.check_acceptance_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("does not resolve" in e and "dl-a" in e for e in result["errors"]),
                        msg=str(result["errors"]))

    def test_bound_elsewhere_substring_of_real_symbol_is_caught(self):
        # Codex R6-B1: a fabricated symbol that is a SUBSTRING of a real one (no own def-site) must
        # NOT resolve — the check requires `def <sym>(`, not a bare substring. Stub defines `_spawn`;
        # the fabricated `_spaw` is a substring of it but has no `def _spaw(`.
        root = self._acc_cov_repo(
            "Clause A present.",
            {"dl-a": {"disposition": "bound-elsewhere", "enforced_by": "driver:_spaw"}},
            [_good_row("dl-a", anchor=self.DL, enforcement="driver:_spaw", roles=["acceptance"])],
            symbols=("_spawn",))
        result = ke.check_acceptance_kernel_coverage(repo_root=root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("does not resolve" in e and "dl-a" in e for e in result["errors"]),
                        msg=str(result["errors"]))

    def test_supplemental_phrase_and_id_validity(self):
        # A supplemental row must be a real acceptance inventory id AND its phrase must resolve.
        src = [_good_row("dl-a", anchor=self.DL, roles=["acceptance"])]
        sup_src = [_good_row("rc-g7", anchor=self.RC, roles=["acceptance"])]
        closure = {"dl-a": {"disposition": "kernel-clause", "phrase": "you cannot run scripts"}}
        # phrase present → ok
        ok_root = self._acc_cov_repo(
            "Clause A: you cannot run scripts. Symmetry check before judging.",
            closure, src, supplemental_rows={"rc-g7": "Symmetry check before judging"},
            supplemental_src=sup_src)
        self.assertTrue(ke.check_acceptance_kernel_coverage(repo_root=ok_root)["ok"])
        # phrase absent → caught
        bad_root = self._acc_cov_repo(
            "Clause A: you cannot run scripts.",
            closure, src, supplemental_rows={"rc-g7": "this gap text is absent"},
            supplemental_src=sup_src)
        bad = ke.check_acceptance_kernel_coverage(repo_root=bad_root)
        self.assertFalse(bad["ok"])
        self.assertTrue(any("supplemental rc-g7" in e for e in bad["errors"]))
        # unknown supplemental id → caught
        ghost_root = self._acc_cov_repo(
            "Clause A: you cannot run scripts. Symmetry check before judging.",
            closure, src, supplemental_rows={"rc-ghost": "Symmetry check before judging"},
            supplemental_src=sup_src)
        ghost = ke.check_acceptance_kernel_coverage(repo_root=ghost_root)
        self.assertFalse(ghost["ok"])
        self.assertTrue(any("unknown inventory id: rc-ghost" in e for e in ghost["errors"]))

    def test_merged_fails_closed_when_source_hash_gate_fails(self):
        orig_check = ke.check
        ke.check = lambda repo_root=None: {
            "ok": False, "errors": ["source process/delivery-loop.md changed (inventory stale)"],
            "warnings": [], "stats": {}}
        try:
            merged = ke._merged_coverage(str(ke.REPO_ROOT_DEFAULT),
                                         ke.check_acceptance_kernel_coverage)
        finally:
            ke.check = orig_check
        self.assertFalse(merged["ok"])
        self.assertTrue(any(e.startswith("[inventory/source-hash gate]") for e in merged["errors"]))


if __name__ == "__main__":
    unittest.main()
