"""Unit tests for lesson_selection (WP-6 tier-aware bounded Loop-Memory ingress).

Deterministic, stdlib unittest. Covers the WP-6 classification + selection
contract (archive/2026-06-28-wp6-lessons-tiering-decision.md):

  - classify() tiers (PROMOTED / MATURED / L2 / L1 / UNKNOWN) from durable fields;
  - only L1 is budget-bounded (count + byte); L2 / MATURED / PROMOTED / UNKNOWN
    are preserved over any budget;
  - explicit supersession (the only removal of a non-L1 lesson) + dedup;
  - PROMOTED renders a compact reference, not full prose;
  - suppression is complete + reason-correct + never silent (footer + audit);
  - byte/token before/after accounting; empty set; legacy entries; determinism;
  - malformed metadata fails safe (preserved as UNKNOWN, never dropped as L1).
"""

import os
import sys
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_MEMORY_DIR = os.path.dirname(_TESTS_DIR)
if _MEMORY_DIR not in sys.path:
    sys.path.insert(0, _MEMORY_DIR)

import memory_store as ms  # noqa: E402
import lesson_selection as ls  # noqa: E402


def _entry(eid, *, maturity="L1", occ=1, status="active", body=None,
           promoted_to=None, supersedes=None, type="failure"):
    """Construct a MemoryEntry with full control over the durable fields."""
    return ms.MemoryEntry(
        id=eid,
        type=type,
        scope={"role": ["dev"]},
        maturity=maturity,
        occurrences=occ,
        status=status,
        promoted_to=list(promoted_to or []),
        supersedes=list(supersedes or []),
        body=body if body is not None else f"Body of {eid}: prefer X over Y because Z.",
    )


def _canonical(entries):
    """Sort like MemoryStore.select: L2-before-L1, then -occurrences, then id."""
    return sorted(entries, key=lambda e: (0 if e.maturity == ms.MATURITY_L2 else 1,
                                          -e.occurrences, e.id))


class TestClassify(unittest.TestCase):
    def test_tier_mapping_from_durable_fields(self):
        self.assertEqual(ls.classify(_entry("a", maturity="L1", occ=1)), ls.TIER_L1)
        self.assertEqual(ls.classify(_entry("b", maturity="L2", occ=2)), ls.TIER_L2)
        self.assertEqual(ls.classify(_entry("c", maturity="L2", occ=3)), ls.TIER_MATURED)
        self.assertEqual(ls.classify(_entry("d", maturity="L2", occ=9)), ls.TIER_MATURED)
        self.assertEqual(
            ls.classify(_entry("e", promoted_to=["test:test_foo"])), ls.TIER_PROMOTED)
        # promotion wins over maturity (even an L1 with a promotion is PROMOTED).
        self.assertEqual(
            ls.classify(_entry("f", maturity="L1", occ=1,
                               promoted_to=["kernel:constitution-core"])),
            ls.TIER_PROMOTED)

    def test_malformed_or_contradictory_is_unknown(self):
        # bad maturity
        self.assertEqual(ls.classify(_entry("a", maturity="L9")), ls.TIER_UNKNOWN)
        # occurrences < 1
        self.assertEqual(ls.classify(_entry("b", occ=0)), ls.TIER_UNKNOWN)
        # contradictory: maturity L1 but occurrences >= 2
        self.assertEqual(ls.classify(_entry("c", maturity="L1", occ=4)), ls.TIER_UNKNOWN)
        # missing id
        self.assertEqual(ls.classify(_entry("", maturity="L1", occ=1)), ls.TIER_UNKNOWN)
        # empty promoted_to (whitespace) is NOT a promotion
        self.assertEqual(
            ls.classify(_entry("d", maturity="L1", occ=1, promoted_to=["  "])),
            ls.TIER_L1)


class TestBudget(unittest.TestCase):
    def test_l1_count_cap(self):
        cands = _canonical([_entry(f"l1-{i:02d}") for i in range(20)])
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=5, max_l1_bytes=10_000))
        self.assertEqual(len(sel.selected_ids), 5)
        self.assertEqual(len(sel.suppressed), 15)
        self.assertTrue(all(s["reason"] == ls.REASON_L1_COUNT for s in sel.suppressed))
        # The kept 5 are the canonical-order-first (deterministic).
        self.assertEqual(sel.selected_ids, [f"l1-{i:02d}" for i in range(5)])

    def test_l1_byte_cap(self):
        # Each line is ~ len("- [L1] " + body) + newline. Distinct bodies of EQUAL
        # length (distinct prefix avoids dedup) so the byte cap binds before count.
        cands = _canonical([_entry(f"l1-{i:02d}",
                                   body=f"{i:03d}" + "x" * 197) for i in range(20)])
        line_bytes = len(("- [L1] " + "0" * 200 + "\n").encode("utf-8"))
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=99,
                                          max_l1_bytes=line_bytes * 3 + 10))
        self.assertEqual(len(sel.selected_ids), 3)
        self.assertTrue(
            all(s["reason"] == ls.REASON_L1_TOKEN for s in sel.suppressed))

    def test_l2_and_matured_preserved_over_budget(self):
        # 10 L2 + 10 MATURED + 30 L1, with a tiny L1 budget. Every non-L1 survives.
        l2 = [_entry(f"l2-{i:02d}", maturity="L2", occ=2) for i in range(10)]
        matured = [_entry(f"mat-{i:02d}", maturity="L2", occ=5) for i in range(10)]
        l1 = [_entry(f"l1-{i:02d}") for i in range(30)]
        cands = _canonical(l2 + matured + l1)
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=2, max_l1_bytes=10_000))
        # all 20 non-L1 preserved + only 2 L1
        self.assertEqual(len(sel.selected_ids), 22)
        for e in l2 + matured:
            self.assertIn(e.id, sel.selected_ids)
            self.assertNotIn(e.id, sel.suppressed_ids)
        # no non-L1 ever appears in suppressed
        for s in sel.suppressed:
            self.assertEqual(s["tier"], ls.TIER_L1)

    def test_unknown_failsafe_preserved_over_budget(self):
        unknown = [_entry(f"u-{i}", maturity="L1", occ=7) for i in range(5)]  # contradictory
        l1 = [_entry(f"l1-{i}") for i in range(20)]
        cands = _canonical(unknown + l1)
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=1, max_l1_bytes=10_000))
        for e in unknown:
            self.assertEqual(sel.tiers[e.id], ls.TIER_UNKNOWN)
            self.assertIn(e.id, sel.selected_ids)        # preserved
            self.assertNotIn(e.id, sel.suppressed_ids)   # never dropped
        # only L1 was budgeted
        self.assertTrue(all(s["tier"] == ls.TIER_L1 for s in sel.suppressed))

    def test_zero_budget_disables_a_bound(self):
        cands = _canonical([_entry(f"l1-{i}") for i in range(10)])
        # count cap disabled (0) but byte cap huge → all kept
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=0, max_l1_bytes=10_000))
        self.assertEqual(len(sel.selected_ids), 10)


class TestSupersessionAndDedup(unittest.TestCase):
    def test_explicit_supersession_removes_any_tier(self):
        a = _entry("old-matured", maturity="L2", occ=9)   # MATURED
        b = _entry("new", maturity="L2", occ=2, supersedes=["old-matured"])
        cands = _canonical([a, b])
        sel = ls.select_for_injection(cands, superseded_ids={"old-matured"})
        self.assertIn("new", sel.selected_ids)
        self.assertNotIn("old-matured", sel.selected_ids)
        self.assertIn({"id": "old-matured", "reason": ls.REASON_SUPERSEDED,
                       "tier": ls.TIER_MATURED}, sel.suppressed)

    def test_nonactive_status_suppressed_as_superseded(self):
        a = _entry("retired-one", status="retired")
        b = _entry("active-one")
        sel = ls.select_for_injection(_canonical([a, b]))
        self.assertNotIn("retired-one", sel.selected_ids)
        self.assertEqual(
            [s for s in sel.suppressed if s["id"] == "retired-one"][0]["reason"],
            ls.REASON_SUPERSEDED)

    def test_duplicate_elimination_byte_identical_line(self):
        # Two entries that render the IDENTICAL line (same tier + same body) are true
        # duplicates: the canonical-order-earlier one is kept, the later suppressed.
        shared = "Prefer explicit branches over a catch-all."
        a = _entry("dup-a", maturity="L2", occ=4, body=shared)
        b = _entry("dup-b", maturity="L2", occ=4, body=shared)
        sel = ls.select_for_injection(_canonical([a, b]))
        self.assertEqual(sel.selected_ids.count("dup-a") + sel.selected_ids.count("dup-b"), 1)
        self.assertEqual(len(sel.suppressed), 1)
        self.assertEqual(sel.suppressed[0]["reason"], ls.REASON_DUPLICATE)

    def test_cross_tier_same_body_not_deduped(self):
        # BLOCKING-1: an L2 and an L1 sharing a body string render DIFFERENT lines
        # (`- [L2] X` vs `- [L1] X`) → NOT duplicates → the L1 is NOT dropped as a
        # duplicate (it stays, subject only to the L1 budget).
        shared = "Validate the nullable FK before the write."
        l2 = _entry("v-l2", maturity="L2", occ=4, body=shared)
        l1 = _entry("v-l1", maturity="L1", occ=1, body=shared)
        sel = ls.select_for_injection(
            _canonical([l2, l1]), budget=ls.LessonBudget(max_l1_count=5, max_l1_bytes=10_000))
        self.assertIn("v-l2", sel.selected_ids)
        self.assertIn("v-l1", sel.selected_ids)
        self.assertEqual(sel.suppressed, [])

    def test_promoted_not_lost_to_dedup_when_body_shared(self):
        # BLOCKING-1: a PROMOTED entry sharing a body string with an earlier L2 must
        # NOT be dropped as a duplicate (its compact ref renders differently).
        shared = "Make the dispatch commit idempotent."
        l2 = _entry("shared-l2", maturity="L2", occ=4, body=shared)
        promoted = _entry("shared-promoted", maturity="L2", occ=4,
                          promoted_to=["test:test_idempotent"], body=shared)
        sel = ls.select_for_injection(_canonical([l2, promoted]))
        self.assertIn("shared-l2", sel.selected_ids)
        self.assertIn("shared-promoted", sel.selected_ids)
        self.assertEqual(sel.representations["shared-promoted"], "compact")
        self.assertEqual(sel.suppressed, [])

    def test_empty_body_identical_lines_dedup(self):
        # Two empty-body same-tier entries render the identical line → the second is a
        # (lossless) byte-identical duplicate.
        a = _entry("e1", body="")
        b = _entry("e2", body="")
        sel = ls.select_for_injection(_canonical([a, b]))
        self.assertEqual(len(sel.selected_ids), 1)
        self.assertEqual(sel.suppressed[0]["reason"], ls.REASON_DUPLICATE)


class TestPromotedCompact(unittest.TestCase):
    def test_promoted_renders_compact_reference(self):
        e = _entry("p1", maturity="L2", occ=5,
                   promoted_to=["test:test_eligibility", "kernel:constitution-core§1.7"],
                   body="When implementing eligibility, enumerate each refund branch.")
        sel = ls.select_for_injection([e])
        self.assertEqual(sel.tiers["p1"], ls.TIER_PROMOTED)
        self.assertEqual(sel.representations["p1"], "compact")
        self.assertIn("p1", sel.selected_ids)
        self.assertIn("[PROMOTED]", sel.block)
        self.assertIn("test:test_eligibility", sel.block)
        self.assertIn("kernel:constitution-core§1.7", sel.block)
        # Compact ref is smaller than the full-prose render would be for long bodies.
        full = ls.render_line(e, "full")
        compact = ls.render_line(e, "compact")
        self.assertNotEqual(full, compact)

    def test_promoted_not_budget_dropped(self):
        promoted = [_entry(f"p-{i}", maturity="L1", occ=1,
                           promoted_to=[f"validator:v{i}"]) for i in range(5)]
        l1 = [_entry(f"l1-{i}") for i in range(10)]
        sel = ls.select_for_injection(
            _canonical(promoted + l1),
            budget=ls.LessonBudget(max_l1_count=1, max_l1_bytes=10_000))
        for e in promoted:
            self.assertIn(e.id, sel.selected_ids)
            self.assertEqual(sel.representations[e.id], "compact")


class TestAuditAndAccounting(unittest.TestCase):
    def test_suppressed_id_completeness_and_partition(self):
        cands = _canonical([_entry(f"l1-{i:02d}") for i in range(20)])
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=6, max_l1_bytes=10_000))
        # every candidate is either selected or suppressed — exactly once (no loss).
        all_ids = {e.id for e in cands}
        self.assertEqual(set(sel.selected_ids) | set(sel.suppressed_ids), all_ids)
        self.assertEqual(set(sel.selected_ids) & set(sel.suppressed_ids), set())
        self.assertEqual(len(sel.selected_ids) + len(sel.suppressed_ids), len(all_ids))

    def test_byte_token_accounting(self):
        cands = _canonical([_entry(f"l1-{i:02d}", body="y" * 100) for i in range(30)])
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=4, max_l1_bytes=10_000))
        self.assertEqual(sel.bytes_after, len(sel.block.encode("utf-8")))
        self.assertLess(sel.bytes_after, sel.bytes_before)
        self.assertEqual(sel.tokens_before, sel.bytes_before // 4)
        self.assertEqual(sel.tokens_after, sel.bytes_after // 4)
        # audit_dict mirrors the dataclass.
        ad = sel.audit_dict()
        self.assertEqual(ad["selected"], sel.selected_ids)
        self.assertEqual(ad["bytes_after"], sel.bytes_after)
        self.assertEqual(ad["version"], ls.SELECTION_VERSION)

    def test_suppression_is_not_silent_footer(self):
        cands = _canonical([_entry(f"l1-{i:02d}") for i in range(20)])
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=3, max_l1_bytes=10_000))
        self.assertIn("Loop Memory bounded", sel.block)
        self.assertIn("suppressed_lesson_ids", sel.block)

    def test_no_footer_when_nothing_suppressed(self):
        cands = _canonical([_entry(f"l1-{i}") for i in range(3)])
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=10, max_l1_bytes=10_000))
        self.assertNotIn("Loop Memory bounded", sel.block)
        self.assertEqual(sel.suppressed, [])


class TestEdgeCasesAndDeterminism(unittest.TestCase):
    def test_empty_lesson_set(self):
        sel = ls.select_for_injection([])
        self.assertEqual(sel.block, "")
        self.assertEqual(sel.selected_ids, [])
        self.assertEqual(sel.suppressed, [])
        self.assertEqual(sel.bytes_before, 0)
        self.assertEqual(sel.bytes_after, 0)

    def test_all_suppressed_still_renders_footer(self):
        # NON-BLOCKING-1: when EVERY candidate is suppressed (here: a tiny byte budget
        # drops all L1s), the block is not silent — it carries the header + footer.
        cands = _canonical([_entry(f"l1-{i}", body="z" * 300) for i in range(5)])
        sel = ls.select_for_injection(
            cands, budget=ls.LessonBudget(max_l1_count=99, max_l1_bytes=1))
        self.assertEqual(sel.selected_ids, [])
        self.assertEqual(len(sel.suppressed), 5)
        self.assertIn("Loop Memory bounded", sel.block)
        self.assertNotEqual(sel.block, "")
        self.assertGreater(sel.bytes_after, 0)

    def test_under_budget_block_is_byte_identical_to_legacy_render(self):
        # The legacy driver._lessons_block render, reproduced here.
        cands = _canonical([
            _entry("a", maturity="L2", occ=3, body="Heuristic A."),
            _entry("b", maturity="L1", occ=1, body="Heuristic B."),
        ])
        legacy_lines = ["## Relevant prior lessons (Loop Memory)",
                        "(generalizable heuristics from earlier loops — not rules to "
                        "memorize; apply judgement)"]
        for e in cands:
            first = (e.body or "").strip().splitlines()[0].strip()
            legacy_lines.append(f"- [{e.maturity}] {first}")
        legacy_block = "\n".join(legacy_lines) + "\n\n"
        sel = ls.select_for_injection(cands)
        self.assertEqual(sel.block, legacy_block)

    def test_determinism_repeated_calls_identical(self):
        cands = _canonical([_entry(f"l1-{i:02d}") for i in range(25)])
        a = ls.select_for_injection(cands, budget=ls.LessonBudget(max_l1_count=7))
        b = ls.select_for_injection(cands, budget=ls.LessonBudget(max_l1_count=7))
        self.assertEqual(a.block, b.block)
        self.assertEqual(a.selected_ids, b.selected_ids)
        self.assertEqual(a.suppressed, b.suppressed)
        self.assertEqual(a.audit_dict(), b.audit_dict())

    def test_legacy_entry_without_new_fields_classifies_normally(self):
        # An entry constructed WITHOUT promoted_to/supersedes (defaults) behaves.
        e = ms.MemoryEntry(id="legacy", type="heuristic", scope={"role": ["dev"]},
                           maturity="L2", occurrences=2, status="active",
                           body="Legacy heuristic.")
        self.assertEqual(e.promoted_to, [])
        self.assertEqual(e.supersedes, [])
        sel = ls.select_for_injection([e])
        self.assertEqual(sel.tiers["legacy"], ls.TIER_L2)
        self.assertIn("legacy", sel.selected_ids)


if __name__ == "__main__":
    unittest.main()
