"""Track 1 Phase 1-a — task-aware dynamic skill mounting (machinery) tests.

The machinery is ADDITIVE + BEHAVIOR-NEUTRAL until (a) skills carry `signals` tags and
(b) a sub-sprint carries `task_signals`. These tests prove each §2 piece works WHEN driven
(via a synthetic signal-tagged catalog / temp framework root) AND stays dormant / byte-identical
when not — including the Codex R-T1 B1 requirement that the budget path sizes the RESOLVED
selected SKILL.md bodies, so `context_budget_report.py --strict` can catch task-skill body growth.

Stdlib unittest + jsonschema (a repo hard dependency); no LLM, no network, no spawn.
"""

import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
_REPO_ROOT = os.path.dirname(_ENGINE_KIT_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "validators")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import effective_role_config as erc  # noqa: E402
import load_sizer as ls  # noqa: E402
import context_budget_report as cbr  # noqa: E402

from jsonschema import Draft202012Validator  # noqa: E402

_SCHEMAS = os.path.join(_REPO_ROOT, "schemas")


def _load_schema(name: str) -> dict:
    with open(os.path.join(_SCHEMAS, name), encoding="utf-8") as fh:
        return json.load(fh)


def _write(root: str, rel: str, content: str) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _synthetic_catalog() -> dict:
    """A catalog (registry.yaml shape) whose skills carry §2.1 `signals` tags."""
    def entry(signals):
        return {"title": "t", "source": {"repo": "local"}, "license": "aidazi",
                "status": "active", "signals": list(signals)}
    return {
        "catalog_version": 1,
        "role_defaults": {"dev": ["base-skill"], "acceptance": ["acc-skill"]},
        "skills": {
            "base-skill": entry([]),
            "ui-skill": entry(["ui", "frontend"]),
            "acc-skill": entry([]),
            "ghost-skill": entry(["ui"]),   # catalog-declared but NO dir on disk → §2.2 skip
        },
    }


def _make_framework_root(tmp: str) -> str:
    """A minimal framework root: registry.yaml + the on-disk skill bodies (NOT ghost-skill).
    ui-skill is DELIBERATELY larger than base-skill so a task-selected mount is visibly bigger."""
    import yaml
    cat = _synthetic_catalog()
    _write(tmp, os.path.join("skills", "registry.yaml"), yaml.safe_dump(cat))
    _write(tmp, os.path.join("skills", "vendored", "base-skill", "SKILL.md"),
           "---\nname: base-skill\n---\n" + ("b" * 400))
    _write(tmp, os.path.join("skills", "vendored", "ui-skill", "SKILL.md"),
           "---\nname: ui-skill\n---\n" + ("u" * 4000))
    _write(tmp, os.path.join("skills", "vendored", "acc-skill", "SKILL.md"),
           "---\nname: acc-skill\n---\n" + ("a" * 800))
    return tmp


# --------------------------------------------------------------------------- #
# §2.2 — optional bindings + skip-if-absent (against the REAL framework root)
# --------------------------------------------------------------------------- #
class SkipIfAbsentTests(unittest.TestCase):
    def test_optional_unresolvable_binding_is_skipped_not_raised(self):
        charter = {"tooling": {"dev": {"skills": {"mode": "extend", "items": [
            {"id": "does-not-exist-xyz", "optional": True}]}}}}
        cfg = erc.resolve_role_config(charter, "dev")
        # The default skill resolves; the optional missing one is SKIPPED, not fatal.
        self.assertEqual([s.id for s in cfg.skills], ["test-driven-development"])
        self.assertEqual(len(cfg.skipped_skills), 1)
        self.assertEqual(cfg.skipped_skills[0]["id"], "does-not-exist-xyz")
        self.assertTrue(cfg.skipped_skills[0]["optional"])
        self.assertTrue(cfg.skipped_skills[0]["reason"])

    def test_required_unresolvable_binding_still_hard_fails(self):
        charter = {"tooling": {"dev": {"skills": {"mode": "extend", "items": [
            {"id": "does-not-exist-xyz"}]}}}}   # no optional ⇒ REQUIRED
        with self.assertRaises(erc.EffectiveConfigError):
            erc.resolve_role_config(charter, "dev")

    def test_skip_does_not_change_skill_set_hash(self):
        base = erc.resolve_role_config({"tooling": {"dev": {}}}, "dev")
        with_skip = erc.resolve_role_config({"tooling": {"dev": {"skills": {
            "mode": "extend", "items": [{"id": "nope", "optional": True}]}}}}, "dev")
        # skip is observation-only — the resolved identity (skills only) is byte-identical.
        self.assertEqual(base.skill_set_hash, with_skip.skill_set_hash)

    def test_skill_skip_footer_empty_without_skips_and_named_with(self):
        clean = erc.resolve_role_config({"tooling": {"dev": {}}}, "dev")
        self.assertEqual(erc.skill_skip_footer(clean), "")
        skipped = erc.resolve_role_config({"tooling": {"dev": {"skills": {
            "mode": "extend", "items": [{"id": "nope", "optional": True}]}}}}, "dev")
        footer = erc.skill_skip_footer(skipped)
        self.assertIn("Skipped / unmatched skills", footer)
        self.assertIn("nope", footer)


# --------------------------------------------------------------------------- #
# §2.3 — select_skills_for_task (pure) + resolve_role_config task extension
# --------------------------------------------------------------------------- #
class SelectSkillsForTaskTests(unittest.TestCase):
    def setUp(self):
        self.cat = _synthetic_catalog()

    def test_signal_match_selects_tagged_catalog_skills(self):
        self.assertEqual(erc.select_skills_for_task("dev", ["ui"], self.cat),
                         ["ghost-skill", "ui-skill"])  # sorted by id; both carry `ui`

    def test_no_or_empty_signals_select_nothing(self):
        self.assertEqual(erc.select_skills_for_task("dev", [], self.cat), [])
        self.assertEqual(erc.select_skills_for_task("dev", (), self.cat), [])
        self.assertEqual(erc.select_skills_for_task("dev", ["nomatch"], self.cat), [])

    def test_acceptance_is_excluded(self):
        # §2.5 — acceptance never task-selects (would thrash §3.6 calibration).
        self.assertEqual(erc.select_skills_for_task("acceptance", ["ui"], self.cat), [])

    def test_canonical_review_alias_selects(self):
        self.assertEqual(erc.select_skills_for_task("review", ["frontend"], self.cat),
                         ["ui-skill"])


class TaskExtensionResolveTests(unittest.TestCase):
    def test_dev_task_signals_mount_extra_skill_optionally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_framework_root(tmp)
            base = erc.resolve_role_config({}, "dev", framework_root=root)
            self.assertEqual([s.id for s in base.skills], ["base-skill"])
            ext = erc.resolve_role_config({}, "dev", task_signals=["ui"], framework_root=root)
            # ui-skill resolves on disk → mounted; ghost-skill is catalog-declared but absent →
            # dropped via the §2.2 skip (NOT a hard fail, because selection feeds OPTIONAL bindings).
            self.assertEqual([s.id for s in ext.skills], ["base-skill", "ui-skill"])
            self.assertEqual(list(ext.selected_skills), ["ghost-skill", "ui-skill"])
            self.assertEqual([s["id"] for s in ext.skipped_skills], ["ghost-skill"])
            self.assertNotEqual(base.skill_set_hash, ext.skill_set_hash)

    def test_acceptance_task_signals_do_not_extend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_framework_root(tmp)
            base = erc.resolve_role_config({}, "acceptance", framework_root=root)
            ext = erc.resolve_role_config({}, "acceptance", task_signals=["ui"], framework_root=root)
            self.assertEqual([s.id for s in ext.skills], [s.id for s in base.skills])
            self.assertEqual(base.skill_set_hash, ext.skill_set_hash)   # §2.5 byte-identical
            self.assertEqual(ext.selected_skills, ())


# --------------------------------------------------------------------------- #
# §2.4 budget — load_sizer sizes the RESOLVED selected SKILL.md bodies (Codex R-T1 B1)
# --------------------------------------------------------------------------- #
class SkillBodyBudgetTests(unittest.TestCase):
    def test_size_role_skills_sizes_default_bodies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_framework_root(tmp)
            r = ls.size_role_skills("dev", repo_root=root)
            self.assertEqual(r["skill_ids"], ["base-skill"])
            self.assertGreater(r["total_bytes"], 400)   # the base-skill SKILL.md body
            self.assertEqual(r["missing"], [])

    def test_task_signal_set_is_larger_than_default(self):
        # The Codex B1 point: toggling skills_active sizes NO body; THIS path sizes the
        # selected bodies, so a task-signal set that mounts ui-skill is visibly bigger →
        # `--strict` would catch the growth once a per-signal baseline row exists.
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_framework_root(tmp)
            default = ls.size_role_skills("dev", repo_root=root)["total_bytes"]
            with_ui = ls.size_role_skills("dev", task_signals=["ui"], repo_root=root)["total_bytes"]
            self.assertGreater(with_ui, default)
            self.assertGreaterEqual(with_ui - default, 4000)   # ~the ui-skill body

    def test_acceptance_skill_budget_ignores_task_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_framework_root(tmp)
            d = ls.size_role_skills("acceptance", repo_root=root)["total_bytes"]
            s = ls.size_role_skills("acceptance", task_signals=["ui"], repo_root=root)["total_bytes"]
            self.assertEqual(d, s)

    def test_budget_entry_skills_kind_sizes_via_size_role_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_framework_root(tmp)
            default = cbr._size_entry(
                {"key": "skills:dev", "role": "dev", "task_kind": None,
                 "kind": "skills", "task_signals": []}, root)
            per_signal = cbr._size_entry(
                {"key": "skills:dev:ui", "role": "dev", "task_kind": None,
                 "kind": "skills", "task_signals": ["ui"]}, root)
            self.assertGreater(per_signal["total_bytes"], default["total_bytes"])

    def test_real_default_skill_rows_present_and_ok(self):
        # The committed baseline carries a positive per-role default skill-body row for every role,
        # and the live tree matches it (drift 0) — the Phase 1-a tracked-budget deliverable.
        result = cbr.check()
        for role in ("research", "deliver", "dev", "review", "acceptance"):
            row = next(r for r in result["rows"] if r["key"] == f"skills:{role}")
            self.assertEqual(row["kind"], "skills")
            self.assertGreater(row["current_bytes"], 0)
            self.assertEqual(row["status"], cbr.STATUS_OK)


# --------------------------------------------------------------------------- #
# §2.1 / §2.2 / §2.3 — additive schema fields validate (and existing docs still do)
# --------------------------------------------------------------------------- #
class SchemaAdditiveTests(unittest.TestCase):
    def test_skill_catalog_signals_accepted(self):
        schema = _load_schema("skill-catalog.schema.json")
        doc = {"catalog_version": 1, "role_defaults": {"dev": ["x"]},
               "skills": {"x": {"title": "t", "source": {"repo": "local"},
                                "license": "aidazi", "status": "active",
                                "signals": ["ui", "frontend"]}}}
        Draft202012Validator(schema).validate(doc)

    def test_skill_binding_optional_accepted(self):
        schema = _load_schema("skill-binding.schema.json")
        Draft202012Validator(schema).validate({"id": "x", "optional": True})

    def test_sprint_stanza_task_signals_accepted_and_optional(self):
        schema = _load_schema("sprint_stanza.schema.json")
        base = {"sprint_id": "s1", "scope_in": ["a"], "layers": ["infra"],
                "exit_criteria": ["c"]}
        Draft202012Validator(schema).validate(base)              # absent ⇒ still valid
        Draft202012Validator(schema).validate({**base, "task_signals": ["ui"]})

    def test_deliver_plan_verdict_sub_sprints_accept_task_signals(self):
        # Codex BLOCKING-1: task_signals must live on the DRIVER-CONSUMED decompose verdict
        # (→ planned_subsprints), whose sub_sprints items are additionalProperties:false.
        schema = _load_schema("deliver-plan-verdict.schema.json")
        ss = {"id": "s1", "objective": "o", "scope_in": [], "scope_out": [],
              "modules": [], "layers": [], "exit_criteria": []}
        Draft202012Validator(schema).validate({"sub_sprints": [ss]})            # absent ⇒ valid
        Draft202012Validator(schema).validate(
            {"sub_sprints": [{**ss, "task_signals": ["ui", "frontend"]}]})

    def test_sprint_stanza_rejects_unknown_field(self):
        schema = _load_schema("sprint_stanza.schema.json")
        with self.assertRaises(Exception):
            Draft202012Validator(schema).validate(
                {"sprint_id": "s1", "scope_in": ["a"], "layers": ["infra"],
                 "exit_criteria": ["c"], "bogus_field": 1})

    def test_compact_mission_charter_mirrors_optional(self):
        schema = _load_schema(os.path.join("compact", "mission-charter.compact.schema.json"))
        sb = schema["$defs"]["skill_binding"]["properties"]
        self.assertIn("optional", sb)


class Track1cActivationTests(unittest.TestCase):
    """Track 1 Phase 1-c — deterministic task-scoped selection over the REAL vendored core-4 UI
    skills. Covers the user's 10 acceptance points (driver-level cache-collision + plan-mutation
    cases live in test_driver.py)."""

    # (1) no signals → behavior-neutral: dev resolves only its default; no UI skill mounts.
    def test_no_signals_is_behavior_neutral(self):
        base = erc.resolve_role_config({}, "dev")
        ext = erc.resolve_role_config({}, "dev", task_signals=[])
        self.assertEqual([s.id for s in base.skills], ["test-driven-development"])
        self.assertEqual(base.skill_set_hash, ext.skill_set_hash)
        self.assertEqual(ext.selected_skills, ())

    # (2) one signal → only its matching skill(s) load — NOT all four (no blanket load-all).
    def test_one_signal_loads_only_its_matching_skills(self):
        cfg = erc.resolve_role_config({}, "dev", task_signals=["ui"])
        # `ui` matches only frontend-design (after the no-blanket retag).
        self.assertEqual(list(cfg.selected_skills), ["frontend-design"])
        self.assertEqual([s.id for s in cfg.skills],
                         ["test-driven-development", "frontend-design"])
        # a different single signal matching exactly one skill:
        cfg2 = erc.resolve_role_config({}, "dev", task_signals=["interaction"])
        self.assertEqual(list(cfg2.selected_skills), ["web-interface-guidelines"])

    # (3) multiple signals → deterministic minimal union, no duplicates.
    def test_multiple_signals_deterministic_union_no_dupes(self):
        a = erc.resolve_role_config({}, "dev", task_signals=["design", "frontend"])
        b = erc.resolve_role_config({}, "dev", task_signals=["frontend", "design"])
        self.assertEqual(list(a.selected_skills), list(b.selected_skills))  # order-independent
        self.assertEqual(list(a.selected_skills),
                         ["front-end-design-checklist", "frontend-design",
                          "web-interface-guidelines"])  # union of design+frontend, deduped
        self.assertEqual(len(a.selected_skills), len(set(a.selected_skills)))
        # no single signal pulls all four — the maximal single-signal set is < 4.
        for sig in erc.TASK_SIGNAL_VOCAB:
            self.assertLess(len(erc.resolve_role_config({}, "dev", task_signals=[sig]).selected_skills), 4)

    # (4) unknown signal → validation failure (the closed-vocab enum). Covered structurally by
    # SignalVocabularyTests.test_unknown_task_signal_fails_schema_validation; assert the selector
    # treats an out-of-vocab signal as a no-match (never a silent fall-back to all skills).
    def test_unknown_signal_matches_nothing_and_is_surfaced(self):
        cfg = erc.resolve_role_config({}, "dev", task_signals=["nonsense-signal"])
        self.assertEqual(cfg.selected_skills, ())
        self.assertEqual(list(cfg.unmatched_signals), ["nonsense-signal"])
        self.assertEqual([s.id for s in cfg.skills], ["test-driven-development"])
        self.assertIn("nonsense-signal", erc.skill_skip_footer(cfg))

    # (5) optional missing skill (catalog-declared, absent on disk) → audited skip, not fatal.
    def test_optional_missing_selected_skill_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_framework_root(tmp)   # ghost-skill is signal-tagged but has no dir
            cfg = erc.resolve_role_config({}, "dev", task_signals=["ui"], framework_root=root)
            self.assertIn("ui-skill", [s.id for s in cfg.skills])
            self.assertEqual([s["id"] for s in cfg.skipped_skills], ["ghost-skill"])

    # (6) required missing skill → hard failure (selection never masks a required misconfig).
    def test_required_missing_skill_hard_fails(self):
        charter = {"tooling": {"dev": {"skills": {"mode": "extend", "items": [
            {"id": "does-not-exist-required"}]}}}}
        with self.assertRaises(erc.EffectiveConfigError):
            erc.resolve_role_config(charter, "dev", task_signals=["ui"])

    # (8) Acceptance never receives task-selected skills (byte-identical regardless of signals).
    def test_acceptance_never_task_selected(self):
        base = erc.resolve_role_config({}, "acceptance")
        for sigs in (["a11y"], ["ui", "design", "frontend", "a11y"]):
            ext = erc.resolve_role_config({}, "acceptance", task_signals=sigs)
            self.assertEqual([s.id for s in ext.skills], [s.id for s in base.skills])
            self.assertEqual(ext.skill_set_hash, base.skill_set_hash)
            self.assertEqual(ext.selected_skills, ())

    # (10) runtime context carries the COMPACT SKILL.md body only — never the large retained upstream.
    def test_runtime_body_is_compact_skill_md_only(self):
        cfg = erc.resolve_role_config({}, "dev", task_signals=["a11y"])
        block = erc.skill_prompt_block(cfg)
        self.assertIn("a11y-checklist", block)
        # the prompt block points at SKILL.md, NOT the retained upstream-checklists.json (33 KB).
        self.assertIn("SKILL.md", block)
        self.assertNotIn("upstream-checklists.json", block)
        self.assertNotIn("upstream-README.md", block)
        # each selected UI skill's loaded body (SKILL.md) is compact (< 9 KB).
        for s in cfg.skills:
            if s.id in ("a11y-checklist", "web-interface-guidelines"):
                self.assertLess(os.path.getsize(os.path.join(s.path, "SKILL.md")), 9000)


class SignalVocabularyTests(unittest.TestCase):
    """Track 1 1-c — the CLOSED controlled vocabulary is a single source of truth
    (effective_role_config.TASK_SIGNAL_VOCAB); all FIVE schema signal enums equal it (the three
    Track-1 schemas + the two SIGNED signal-source schemas from the universal-skill-mounting
    design, archive/2026-07-06: charter mission profile + campaign-plan milestone_signals), and
    every registered skill's `signals` tags are a subset of it (drift guard — unknown signal
    fails)."""

    def _enum(self, schema_path, *path):
        node = _load_schema(schema_path)
        for p in path:
            node = node[p]
        return node["items"]["enum"]

    def test_schema_enums_match_canonical_vocab(self):
        vocab = sorted(erc.TASK_SIGNAL_VOCAB)
        self.assertEqual(sorted(self._enum(
            "skill-catalog.schema.json", "$defs", "skill_entry", "properties", "signals")), vocab)
        self.assertEqual(sorted(self._enum(
            "deliver-plan-verdict.schema.json", "properties", "sub_sprints", "items",
            "properties", "task_signals")), vocab)
        self.assertEqual(sorted(self._enum(
            "sprint_stanza.schema.json", "properties", "task_signals")), vocab)
        self.assertEqual(sorted(self._enum(
            "mission-charter.schema.json", "properties", "autonomy", "properties",
            "approved_scope", "properties", "task_signals")), vocab)
        self.assertEqual(sorted(self._enum(
            "campaign-plan.schema.json", "properties", "milestones", "items",
            "properties", "milestone_signals")), vocab)

    def test_registry_signal_tags_are_subset_of_vocab(self):
        import yaml
        reg = yaml.safe_load(open(os.path.join(_REPO_ROOT, "skills", "registry.yaml"),
                                   encoding="utf-8"))
        vocab = set(erc.TASK_SIGNAL_VOCAB)
        tagged = 0
        for section in ("skills", "authored"):
            for sid, e in (reg.get(section) or {}).items():
                sig = e.get("signals")
                if sig:
                    tagged += 1
                    self.assertTrue(set(sig) <= vocab, f"{sid} has out-of-vocab signals: {sig}")
        self.assertGreaterEqual(tagged, 4)   # the vendored core-4 UI skills are signal-tagged

    def test_unknown_task_signal_fails_schema_validation(self):
        schema = _load_schema("deliver-plan-verdict.schema.json")
        ss = {"id": "s1", "objective": "o", "scope_in": [], "scope_out": [],
              "modules": [], "layers": [], "exit_criteria": []}
        with self.assertRaises(Exception):
            Draft202012Validator(schema).validate(
                {"sub_sprints": [{**ss, "task_signals": ["totally-unknown-signal"]}]})


if __name__ == "__main__":
    unittest.main()
