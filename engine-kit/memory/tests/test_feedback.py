#!/usr/bin/env python3
"""Unit tests for feedback — Loop Memory feedback engine (plan §4.4; m-memory §5).

stdlib unittest; deterministic; offline; temp dirs. Run as a script (do NOT
discover the package — siblings may be mid-edit):

    cd engine-kit && python memory/tests/test_feedback.py

Covers:
  - only matured (L2) + active entries are proposed (L1 / retired excluded);
  - each m-memory §5 path (2–5) fires on a representative entry with the right
    gate/target;
  - PROPOSE-ONLY: propose() + render_report() mutate NOTHING on disk;
  - deterministic ordering: identical input → identical output twice;
  - an Acceptance skill_edit sets recalibration_required;
  - a calibration-note charter_tuning keeps (provider, model);
  - aggregation: many entries → one proposal per (path, target);
  - every serialized proposal validates against memory-feedback.schema.json;
  - the registry loader maps roles → bound skills.
"""

import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_MEMORY_DIR = os.path.dirname(_TESTS_DIR)
if _MEMORY_DIR not in sys.path:
    sys.path.insert(0, _MEMORY_DIR)

import memory_store as ms  # noqa: E402
import feedback as fb  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

FIXED_TS = "2026-06-16"
LOOP = "loop-fb-test"

# A deterministic role→skill map (avoids depending on the on-disk registry).
ROLE_SKILLS = {
    "research": ["brainstorming"],
    "dev": ["test-driven-development"],
    "code_reviewer": ["code-review-excellence"],
    "acceptance": ["advanced-evaluation"],
}


def _find_schema_path() -> str:
    cur = _MEMORY_DIR
    while True:
        cand = os.path.join(cur, "schemas", "memory-feedback.schema.json")
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            raise FileNotFoundError("memory-feedback.schema.json not found")
        cur = parent


def _entry(id, type, *, scope, maturity="L2", status="active",
           provider=None, model=None, occurrences=2, body="generalizable lesson"):
    return ms.MemoryEntry(
        id=id, type=type, scope=scope, maturity=maturity, status=status,
        provider=provider, model=model, occurrences=occurrences,
        source_loops=[LOOP], body=body,
    )


class TestEligibility(unittest.TestCase):
    def test_only_l2_active_proposed(self):
        entries = [
            _entry("e-l1", "pattern", scope={"layer": ["prompt_projection"]},
                   maturity="L1"),                      # L1 → excluded
            _entry("e-retired", "pattern", scope={"layer": ["prompt_projection"]},
                   status="retired"),                   # retired → excluded
            _entry("e-ok", "pattern", scope={"layer": ["prompt_projection"]}),
        ]
        props = fb.propose(entries, role_skill_map=ROLE_SKILLS)
        ids = {sid for p in props for sid in p.source_entry_ids}
        self.assertEqual(ids, {"e-ok"})
        self.assertTrue(all(p.maturity == "L2" for p in props))


class TestPaths(unittest.TestCase):
    def test_autoloop_candidate(self):
        e = _entry("a1", "pattern", scope={"layer": ["semantic_planner"]})
        props = fb.propose([e], role_skill_map=ROLE_SKILLS)
        self.assertEqual(len(props), 1)
        p = props[0]
        self.assertEqual(p.path, fb.PATH_AUTOLOOP_CANDIDATE)
        self.assertEqual(p.target, "semantic_planner")
        self.assertEqual(p.gate, fb.GATE_HUMAN_APPROVAL)

    def test_autoloop_only_type_a_layers(self):
        # A pattern at a NON-type-A layer (e.g. infra) is not an Auto Loop input.
        e = _entry("a2", "pattern", scope={"layer": ["infra"]})
        props = fb.propose([e], role_skill_map=ROLE_SKILLS)
        self.assertEqual([p.path for p in props], [])

    def test_skill_edit_role_mapped(self):
        e = _entry("s1", "failure", scope={"role": ["dev"]})
        props = fb.propose([e], role_skill_map=ROLE_SKILLS)
        self.assertEqual(len(props), 1)
        p = props[0]
        self.assertEqual(p.path, fb.PATH_SKILL_EDIT)
        self.assertEqual(p.target, "test-driven-development")
        self.assertFalse(p.recalibration_required)

    def test_skill_edit_unmapped_role_emits_nothing(self):
        # A role with no default-bound skill yields no skill_edit.
        e = _entry("s2", "failure", scope={"role": ["engine"]})
        props = fb.propose([e], role_skill_map=ROLE_SKILLS)
        self.assertEqual([p for p in props if p.path == fb.PATH_SKILL_EDIT], [])

    def test_acceptance_skill_edit_sets_recalibration(self):
        e = _entry("s3", "heuristic", scope={"role": ["acceptance"]})
        props = fb.propose([e], role_skill_map=ROLE_SKILLS)
        skill = [p for p in props if p.path == fb.PATH_SKILL_EDIT]
        self.assertEqual(len(skill), 1)
        self.assertEqual(skill[0].target, "advanced-evaluation")
        self.assertTrue(skill[0].recalibration_required)
        self.assertIn("recalibrat", skill[0].rationale.lower())

    def test_charter_tuning_keeps_provider_model(self):
        e = _entry("c1", "calibration-note", scope={"role": ["acceptance"]},
                   provider="anthropic", model="claude-opus-4-8")
        props = fb.propose([e], role_skill_map=ROLE_SKILLS)
        ct = [p for p in props if p.path == fb.PATH_CHARTER_TUNING]
        self.assertEqual(len(ct), 1)
        self.assertEqual(ct[0].target, "tooling.acceptance.judge_calibration")
        self.assertEqual(ct[0].provider, "anthropic")
        self.assertEqual(ct[0].model, "claude-opus-4-8")
        self.assertEqual(ct[0].gate, fb.GATE_HUMAN_APPROVAL)

    def test_fold_back_layer(self):
        e = _entry("f1", "pattern", scope={"layer": ["human_review_required"]})
        props = fb.propose([e], role_skill_map=ROLE_SKILLS)
        fbk = [p for p in props if p.path == fb.PATH_FOLD_BACK]
        self.assertEqual(len(fbk), 1)
        self.assertEqual(fbk[0].target, "human_review_required")
        self.assertEqual(fbk[0].gate, fb.GATE_FOLD_BACK)

    def test_calibration_note_at_judge_layer_feeds_two_paths(self):
        # A calibration-note scoped to the judge_calibration layer feeds BOTH
        # charter_tuning (from type) and fold_back (from layer) — documented.
        e = _entry("c2", "calibration-note",
                   scope={"role": ["acceptance"], "layer": ["judge_calibration"]},
                   provider="openai", model="gpt-x")
        paths = {p.path for p in fb.propose([e], role_skill_map=ROLE_SKILLS)}
        self.assertIn(fb.PATH_CHARTER_TUNING, paths)
        self.assertIn(fb.PATH_FOLD_BACK, paths)


class TestAggregationAndOrder(unittest.TestCase):
    def test_aggregation_one_proposal_per_target(self):
        e1 = _entry("d1", "failure", scope={"role": ["dev"]})
        e2 = _entry("d2", "detour", scope={"role": ["dev"]})
        props = fb.propose([e1, e2], role_skill_map=ROLE_SKILLS)
        skill = [p for p in props if p.path == fb.PATH_SKILL_EDIT]
        self.assertEqual(len(skill), 1)  # one proposal for the dev skill
        self.assertEqual(skill[0].source_entry_ids, ["d1", "d2"])  # both cited, sorted

    def test_deterministic_order(self):
        entries = [
            _entry("z", "pattern", scope={"layer": ["prompt_projection"]}),
            _entry("a", "failure", scope={"role": ["dev"]}),
            _entry("m", "pattern", scope={"layer": ["product_policy"]}),
        ]
        first = [p.to_dict() for p in fb.propose(entries, role_skill_map=ROLE_SKILLS)]
        second = [p.to_dict() for p in fb.propose(entries, role_skill_map=ROLE_SKILLS)]
        self.assertEqual(first, second)
        # sorted by (path, target, source ids)
        keys = [(p["path"], p["target"]) for p in first]
        self.assertEqual(keys, sorted(keys))


class TestProposeOnly(unittest.TestCase):
    def test_propose_and_report_mutate_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            store = ms.MemoryStore(d)
            store.record_observation(
                "dev: guard the handoff", ts=FIXED_TS, loop_id=LOOP,
                type="failure", scope={"role": ["dev"]},
                body="When the dev handoff omits a guard, reviews recur; add the "
                     "guard before handoff.")
            store.record_observation(
                "dev: guard the handoff", ts=FIXED_TS, loop_id="loop-2",
                type="failure", scope={"role": ["dev"]},
                body="When the dev handoff omits a guard, reviews recur; add the "
                     "guard before handoff.")  # 2nd obs → occurrences=2 → L2

            def _snapshot():
                snap = {}
                for root, _dirs, files in os.walk(d):
                    for f in files:
                        p = os.path.join(root, f)
                        st = os.stat(p)
                        snap[p] = (st.st_size, st.st_mtime_ns)
                return snap

            before = _snapshot()
            props = fb.propose(store, role_skill_map=ROLE_SKILLS)
            report = fb.render_report(props, ts=FIXED_TS)
            after = _snapshot()
            self.assertEqual(before, after)            # NOTHING changed on disk
            self.assertTrue(any(p.path == fb.PATH_SKILL_EDIT for p in props))
            self.assertIn("PROPOSE-ONLY", report)


class TestSchema(unittest.TestCase):
    def test_every_proposal_validates(self):
        validator = Draft202012Validator(_load_schema())
        entries = [
            _entry("p1", "pattern", scope={"layer": ["prompt_projection"]}),
            _entry("p2", "failure", scope={"role": ["acceptance"]}),
            _entry("p3", "calibration-note", scope={"role": ["acceptance"]},
                   provider="anthropic", model="claude-opus-4-8"),
            _entry("p4", "pattern", scope={"layer": ["product_policy"]}),
        ]
        props = fb.propose(entries, role_skill_map=ROLE_SKILLS)
        self.assertTrue(props)
        for p in props:
            errors = sorted(validator.iter_errors(p.to_dict()),
                            key=lambda e: list(e.absolute_path))
            self.assertEqual(errors, [], f"{p.to_dict()} -> {errors}")

    def test_array_form_validates(self):
        validator = Draft202012Validator(_load_schema())
        e = _entry("p1", "pattern", scope={"layer": ["prompt_projection"]})
        arr = [p.to_dict() for p in fb.propose([e], role_skill_map=ROLE_SKILLS)]
        self.assertEqual(list(validator.iter_errors(arr)), [])


class TestRegistryLoader(unittest.TestCase):
    def test_loads_real_registry(self):
        m = fb.load_role_skill_map()
        # The on-disk skills/registry.yaml role_defaults (decision log).
        self.assertEqual(m.get("dev"), ["test-driven-development"])
        self.assertEqual(m.get("acceptance"), ["advanced-evaluation"])

    def test_propose_uses_registry_when_map_omitted(self):
        e = _entry("r1", "failure", scope={"role": ["dev"]})
        props = fb.propose([e])  # no role_skill_map → loads registry
        skill = [p for p in props if p.path == fb.PATH_SKILL_EDIT]
        self.assertEqual(len(skill), 1)
        self.assertEqual(skill[0].target, "test-driven-development")


class TestEmpty(unittest.TestCase):
    def test_no_entries_no_proposals(self):
        props = fb.propose([], role_skill_map=ROLE_SKILLS)
        self.assertEqual(props, [])
        report = fb.render_report(props, ts=FIXED_TS)
        self.assertIn("No matured", report)


def _load_schema():
    import json
    with open(_find_schema_path(), "r", encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    unittest.main(verbosity=2)
