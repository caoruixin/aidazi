"""Unit tests for memory_store (stdlib unittest; deterministic; temp dir).

Covers the plan §4.4 contract:
  - write_entry creates entries/<id>.md whose front-matter VALIDATES against
    schemas/memory-entry.schema.json (loaded via jsonschema; dates stringified
    before validation);
  - record_observation twice on the same key → occurrences=2 and maturity flips
    L1 → L2 (Δ-9 OBS triage; m-autoloop.md §5);
  - select(scope) returns only matching entries in a stable order;
  - index.md reflects the entries; dedup does not create a duplicate file;
  - the anti-gaming guard REJECTS a case-specific input→output entry.

No clock, no randomness: every mutating call is given an injected ts + loop_id.
"""

import datetime
import json
import os
import sys
import tempfile
import unittest

# Make memory_store importable whether tests run via discover from repo root or
# from inside engine-kit/memory/tests.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_MEMORY_DIR = os.path.dirname(_TESTS_DIR)
if _MEMORY_DIR not in sys.path:
    sys.path.insert(0, _MEMORY_DIR)

import memory_store as ms  # noqa: E402

from jsonschema import Draft202012Validator  # noqa: E402


def _find_schema_path() -> str:
    """Walk up from this file to find schemas/memory-entry.schema.json."""
    cur = _MEMORY_DIR
    while True:
        cand = os.path.join(cur, "schemas", "memory-entry.schema.json")
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            raise FileNotFoundError("schemas/memory-entry.schema.json not found")
        cur = parent


SCHEMA_PATH = _find_schema_path()
with open(SCHEMA_PATH, "r", encoding="utf-8") as _fh:
    SCHEMA = json.load(_fh)
VALIDATOR = Draft202012Validator(SCHEMA)


def _stringify_dates(obj):
    """Recursively stringify date/datetime so jsonschema format:date sees strings.

    yaml.safe_load turns an ISO date into a datetime.date; the schema declares
    those fields ``type: string``. Stringify before validating so we validate the
    on-disk semantics, not pyyaml's Python typing.
    """
    if isinstance(obj, dict):
        return {k: _stringify_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_dates(v) for v in obj]
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj


def _validate(front_matter) -> None:
    VALIDATOR.validate(_stringify_dates(front_matter))


class WriteEntryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.store = ms.MemoryStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_entry_creates_file_and_validates_against_schema(self):
        entry = ms.MemoryEntry(
            id="research-stale-brief",
            type="heuristic",
            scope={"role": ["research"], "module": ["m-research"]},
            body="When a brief's sources are older than the milestone, re-pull "
            "before planning — stale inputs propagate to every downstream role.",
        )
        written = self.store.write_entry(entry, ts="2026-06-15", loop_id="wf_aaa")

        path = os.path.join(self.root, "entries", "research-stale-brief.md")
        self.assertTrue(os.path.exists(path), "entry md file should exist")

        # Round-trip the on-disk file and validate its FRONT-MATTER against the
        # normative schema (dates stringified first).
        on_disk = self.store.get("research-stale-brief")
        self.assertIsNotNone(on_disk)
        _validate(on_disk.front_matter())

        # Injected ts threaded into created/last_reviewed; loop_id into source_loops.
        self.assertEqual(written.created, "2026-06-15")
        self.assertEqual(written.last_reviewed, "2026-06-15")
        self.assertEqual(written.source_loops, ["wf_aaa"])
        self.assertEqual(written.maturity, ms.MATURITY_L1)
        self.assertEqual(written.occurrences, 1)

    def test_calibration_note_requires_provider_model_and_validates(self):
        entry = ms.MemoryEntry(
            id="calib-anthropic-opus-verbose-judge",
            type="calibration-note",
            scope={"role": ["acceptance"], "layer": ["judge_calibration"]},
            provider="anthropic",
            model="claude-opus-4-8",
            body="This judge tends to over-credit verbose answers; weight concision.",
        )
        written = self.store.write_entry(entry, ts="2026-06-15", loop_id="wf_cal")
        _validate(written.front_matter())
        self.assertEqual(written.provider, "anthropic")
        self.assertEqual(written.model, "claude-opus-4-8")

        # Missing (provider, model) must be refused (plan §4.4 / §3.6).
        bad = ms.MemoryEntry(
            id="calib-missing-tags",
            type="calibration-note",
            scope={"role": ["acceptance"]},
            body="some note",
        )
        with self.assertRaises(ms.MemoryError):
            self.store.write_entry(bad, ts="2026-06-15", loop_id="wf_x")

    def test_duplicate_id_write_is_rejected(self):
        entry = ms.MemoryEntry(
            id="dup", type="pattern", scope={"module": ["m"]}, body="x"
        )
        self.store.write_entry(entry, ts="2026-06-15", loop_id="wf_1")
        with self.assertRaises(ms.MemoryError):
            self.store.write_entry(entry, ts="2026-06-15", loop_id="wf_2")


class MaturityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ms.MemoryStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_observation_twice_bumps_occurrences_and_promotes_L1_to_L2(self):
        key = "deliver: missing closure proof"
        first = self.store.record_observation(
            key,
            ts="2026-06-15",
            loop_id="wf_111",
            type="failure",
            scope={"role": ["deliver"]},
            body="Closing without an explicit proof-of-done lets gaps slip.",
        )
        self.assertEqual(first.occurrences, 1)
        self.assertEqual(first.maturity, ms.MATURITY_L1)
        self.assertEqual(first.source_loops, ["wf_111"])

        # Same key, a DIFFERENT loop → repeat observation.
        second = self.store.record_observation(
            key, ts="2026-06-16", loop_id="wf_222", scope={"role": ["deliver"]}
        )
        self.assertEqual(second.occurrences, 2)
        self.assertEqual(second.maturity, ms.MATURITY_L2)  # L1 → L2 at n>=2
        self.assertEqual(second.source_loops, ["wf_111", "wf_222"])
        self.assertEqual(second.last_reviewed, "2026-06-16")

        # Dedup: exactly ONE file for the key.
        entries_dir = os.path.join(self.store.root, "entries")
        files = [f for f in os.listdir(entries_dir) if f.endswith(".md")]
        self.assertEqual(files, [ms.slug(key) + ".md"])

        # Validates against the schema post-promotion.
        _validate(self.store.get(ms.slug(key)).front_matter())

    def test_human_flag_promotes_to_L2_at_single_occurrence(self):
        entry = self.store.record_observation(
            "engine: race in checkpoint resolver",
            ts="2026-06-15",
            loop_id="wf_h",
            scope={"role": ["engine"]},
            human_flagged=True,
        )
        self.assertEqual(entry.occurrences, 1)
        self.assertEqual(entry.maturity, ms.MATURITY_L2)

    def test_repeat_observation_does_not_duplicate_source_loop(self):
        key = "pattern: retry budget"
        self.store.record_observation(
            key, ts="2026-06-15", loop_id="wf_same", scope={"module": ["m"]}
        )
        again = self.store.record_observation(
            key, ts="2026-06-16", loop_id="wf_same", scope={"module": ["m"]}
        )
        # occurrences still bumps, but the same loop_id is not appended twice.
        self.assertEqual(again.occurrences, 2)
        self.assertEqual(again.source_loops, ["wf_same"])


class SelectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ms.MemoryStore(self._tmp.name)
        # Seed a deterministic fixture set.
        self.store.write_entry(
            ms.MemoryEntry(id="r1", type="heuristic", scope={"role": ["research"]}, body="a"),
            ts="2026-06-15", loop_id="wf_a",
        )
        self.store.write_entry(
            ms.MemoryEntry(id="d1", type="failure", scope={"role": ["deliver"]}, body="b"),
            ts="2026-06-15", loop_id="wf_b",
        )
        # Two research entries to test ordering (one L2/high-occ, one L1).
        self.store.record_observation(
            "research: dup-source rule", ts="2026-06-15", loop_id="wf_c",
            scope={"role": ["research"]},
        )
        self.store.record_observation(
            "research: dup-source rule", ts="2026-06-16", loop_id="wf_d",
            scope={"role": ["research"]},
        )
        # A retired entry must be excluded from selection.
        self.store.write_entry(
            ms.MemoryEntry(
                id="r-retired", type="heuristic", scope={"role": ["research"]},
                status="retired", body="old",
            ),
            ts="2026-06-15", loop_id="wf_e",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_select_returns_only_matching_active_entries(self):
        got = self.store.select({"role": ["research"]})
        ids = [e.id for e in got]
        # d1 (deliver) excluded; r-retired excluded; only active research entries.
        self.assertNotIn("d1", ids)
        self.assertNotIn("r-retired", ids)
        self.assertEqual(set(ids), {"r1", "research-dup-source-rule"})

    def test_select_order_is_stable_l2_then_occurrences_then_id(self):
        got = self.store.select({"role": ["research"]})
        ids = [e.id for e in got]
        # research-dup-source-rule is L2 (occ=2) → sorts before r1 (L1, occ=1).
        self.assertEqual(ids, ["research-dup-source-rule", "r1"])
        # Re-running yields the identical order (determinism).
        self.assertEqual([e.id for e in self.store.select({"role": ["research"]})], ids)

    def test_select_non_matching_scope_returns_empty(self):
        self.assertEqual(self.store.select({"role": ["dev"]}), [])

    def test_select_matches_on_module_dimension(self):
        self.store.write_entry(
            ms.MemoryEntry(id="m1", type="pattern", scope={"module": ["m-trace"]}, body="z"),
            ts="2026-06-15", loop_id="wf_m",
        )
        got = self.store.select({"module": ["m-trace"]})
        self.assertEqual([e.id for e in got], ["m1"])


class IndexTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ms.MemoryStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_index_reflects_entries_and_is_regenerated(self):
        self.store.write_entry(
            ms.MemoryEntry(id="i1", type="heuristic", scope={"role": ["dev"]}, body="x"),
            ts="2026-06-15", loop_id="wf_1",
        )
        idx = self.store.load_index()
        self.assertIn("entries: 1", idx)
        self.assertIn("[[i1]]", idx)

        self.store.write_entry(
            ms.MemoryEntry(id="i2", type="pattern", scope={"role": ["dev"]}, body="y"),
            ts="2026-06-15", loop_id="wf_2",
        )
        idx2 = self.store.load_index()
        self.assertIn("entries: 2", idx2)
        self.assertIn("[[i1]]", idx2)
        self.assertIn("[[i2]]", idx2)
        # Deterministic: re-rendering the same entry set is byte-identical.
        self.assertEqual(self.store.load_index(), idx2)

    def test_index_is_byte_stable_across_loads(self):
        self.store.write_entry(
            ms.MemoryEntry(id="b", type="heuristic", scope={"role": ["dev"]}, body="x"),
            ts="2026-06-15", loop_id="wf_1",
        )
        self.store.write_entry(
            ms.MemoryEntry(id="a", type="heuristic", scope={"role": ["dev"]}, body="x"),
            ts="2026-06-15", loop_id="wf_2",
        )
        idx = self.store.load_index()
        # Sorted by id regardless of insertion order: 'a' row precedes 'b' row.
        self.assertLess(idx.index("[[a]]"), idx.index("[[b]]"))


class AntiGamingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ms.MemoryStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_guard_rejects_case_specific_input_output_entry(self):
        bad = ms.MemoryEntry(
            id="gamed",
            type="heuristic",
            scope={"role": ["dev"]},
            body="When the input is 'What is 2+2?' then output '4'. "
            "Memorize this expected answer for the eval case.",
        )
        with self.assertRaises(ms.AntiGamingViolation):
            self.store.write_entry(bad, ts="2026-06-15", loop_id="wf_bad")
        # And nothing was written to disk.
        self.assertIsNone(self.store.get("gamed"))

    def test_guard_rejects_input_arrow_output_mapping(self):
        bad = ms.MemoryEntry(
            id="gamed2",
            type="pattern",
            scope={"role": ["dev"]},
            body="input -> output mapping: case_42 yields the gold answer.",
        )
        with self.assertRaises(ms.AntiGamingViolation):
            ms.guard_entry(bad)

    def test_guard_allows_generalizable_heuristic(self):
        good = ms.MemoryEntry(
            id="generalizable",
            type="heuristic",
            scope={"role": ["dev"]},
            body="Prefer idempotent writes when a step may be retried; it removes "
            "a whole class of partial-write defects regardless of the case.",
        )
        # Should not raise, and should write cleanly.
        ms.guard_entry(good)
        written = self.store.write_entry(good, ts="2026-06-15", loop_id="wf_ok")
        self.assertEqual(written.id, "generalizable")

    # ---- P3 review: natural-language case→answer encodings (verified bypasses
    #      of the original lexical-only guard) MUST now be rejected ------------- #
    # Each string maps a specific stimulus/case to a specific canned answer — the
    # §1.7 forbidden "encode raw eval phrases" gaming, just phrased in NL.
    _NL_BYPASSES = (
        "When the user says 'what is 2+2?', respond '4'.",
        "When the user asks 'what is the capital of France?', reply 'Paris'.",
        "The answer for case 3 is '42'.",
        "The correct answer is 'yes, eligible'.",
        "For the question 'is the refund allowed?' the correct answer is 'no'.",
        "Test case 4 expects the output 'ELIGIBLE'.",
        "Case 7 expects 'partial'.",
        "Respond with 'APPROVED' verbatim.",
        "Reply 'declined' verbatim to pass the eval.",
        "case_42 -> 'gold answer'",
        "case 12 -> 'escalate'",
        "remember: case_9 -> 'refund'",
        "remember that case 5 is 'denied'.",
    )

    def test_guard_rejects_natural_language_case_to_answer_encodings(self):
        for body in self._NL_BYPASSES:
            entry = ms.MemoryEntry(
                id="nl-bypass", type="heuristic", scope={"role": ["dev"]},
                body=body,
            )
            with self.assertRaises(ms.AntiGamingViolation, msg=body):
                ms.guard_entry(entry)

    # ---- Precision: legitimate generalizable / role / heuristic guidance MUST
    #      still pass (no over-rejection) -------------------------------------- #
    _LEGIT_HEURISTICS = (
        # The three the P3 review named explicitly:
        "Prefer reading the full closure_contract before judging.",
        "When a research brief lacks anchor phrases, push back before sign-off.",
        "Dev should watch the test fail before writing impl.",
        # Plus more that brush near the trigger words but stay generalizable:
        "When the customer's intent is ambiguous between booking and "
        "cancellation, widen the slot prompt to discriminate.",
        "Acceptance should ask for execution evidence, not code inspection, "
        "before signing off.",
        "Answer questions by reasoning from the contract, not from memory.",
        "When reviewing, prefer a small diff and ask for the failing case first.",
    )

    def test_guard_allows_legitimate_heuristics_precision(self):
        for body in self._LEGIT_HEURISTICS:
            entry = ms.MemoryEntry(
                id="legit", type="heuristic", scope={"role": ["dev"]}, body=body,
            )
            # Must NOT raise — these are generalizable, not case→answer lookups.
            ms.guard_entry(entry)
        # And one writes cleanly end-to-end (guard runs inside write_entry).
        clean = ms.MemoryEntry(
            id="legit-write", type="heuristic", scope={"role": ["research"]},
            body=self._LEGIT_HEURISTICS[1],
        )
        written = self.store.write_entry(clean, ts="2026-06-15", loop_id="wf_legit")
        self.assertEqual(written.id, "legit-write")


class WP6FieldsTests(unittest.TestCase):
    """WP-6 additive fields: promoted_to / supersedes round-trip + superseded_ids()."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ms.MemoryStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_promoted_to_and_supersedes_round_trip_and_validate(self):
        e = ms.MemoryEntry(
            id="promoted-and-supersedes", type="failure",
            scope={"role": ["dev"]}, maturity="L2", occurrences=3, status="active",
            promoted_to=["test:test_foo", "kernel:constitution-core§1.7"],
            supersedes=["older-lesson-1", "older-lesson-2"],
            body="Matured + promoted lesson.")
        written = self.store.write_entry(e, ts="2026-06-15", loop_id="wf_wp6")
        # front-matter VALIDATES against the (extended) schema.
        _validate(written.front_matter())
        # and on-disk text round-trips the new fields.
        back = self.store.get("promoted-and-supersedes")
        self.assertEqual(back.promoted_to,
                         ["test:test_foo", "kernel:constitution-core§1.7"])
        self.assertEqual(back.supersedes, ["older-lesson-1", "older-lesson-2"])

    def test_legacy_entry_without_new_fields_parses_empty(self):
        # An entry written WITHOUT the new fields omits them on disk (byte-stable)
        # and parses back with empty lists (backward compatible).
        e = ms.MemoryEntry(id="legacy", type="heuristic", scope={"role": ["dev"]},
                           body="Legacy lesson.")
        self.store.write_entry(e, ts="2026-06-15", loop_id="wf_legacy")
        with open(self.store._entry_path("legacy"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("promoted_to", text)
        self.assertNotIn("supersedes", text)
        back = self.store.get("legacy")
        self.assertEqual(back.promoted_to, [])
        self.assertEqual(back.supersedes, [])

    def test_malformed_occurrences_coerced_to_sentinel_not_silently_int(self):
        # WP-6 BLOCKING-2: parse must NOT silently coerce a malformed occurrences
        # (bool / float / numeric-string / non-coercible) into a clean int 1 — that
        # would let it classify as a droppable L1. It is normalized to the sentinel 0
        # (below the schema minimum) so it fails safe to UNKNOWN at ingress, and a
        # single bad file never crashes load_all/select.
        for bad in ("true", "1.2", '"1"', "not-a-number", "0", "-3"):
            path = os.path.join(self.store.entries_dir, "bad.md")
            text = ("---\n"
                    f"id: bad\ntype: heuristic\nscope:\n  role: [dev]\n"
                    f"maturity: L1\noccurrences: {bad}\nstatus: active\n"
                    "---\n\nBody.\n")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            e = self.store.get("bad")
            self.assertEqual(e.occurrences, 0, f"malformed {bad!r} must coerce to 0")
            # load_all / select must not crash on the malformed file.
            self.assertEqual(self.store.select({"role": ["dev"]})[0].occurrences, 0)
            os.remove(path)

    def test_genuine_int_occurrences_preserved(self):
        path = os.path.join(self.store.entries_dir, "good.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("---\nid: good\ntype: heuristic\nscope:\n  role: [dev]\n"
                     "maturity: L2\noccurrences: 4\nstatus: active\n---\n\nBody.\n")
        self.assertEqual(self.store.get("good").occurrences, 4)

    def test_superseded_ids_unions_active_supersedes_only(self):
        active = ms.MemoryEntry(id="superseder", type="failure",
                                scope={"role": ["dev"]}, maturity="L2",
                                occurrences=2, status="active",
                                supersedes=["a", "b"], body="Active superseder.")
        # a RETIRED entry's supersedes must NOT confer supersession.
        retired = ms.MemoryEntry(id="retired-superseder", type="failure",
                                 scope={"role": ["dev"]}, maturity="L2",
                                 occurrences=2, status="retired",
                                 supersedes=["c"], body="Retired superseder.")
        self.store.write_entry(active, ts="2026-06-15", loop_id="wf_a")
        self.store.write_entry(retired, ts="2026-06-15", loop_id="wf_r")
        self.assertEqual(self.store.superseded_ids(), {"a", "b"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
