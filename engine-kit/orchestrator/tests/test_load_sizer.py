"""WP-0 (context/token-optimization measurement baseline) — deterministic tests.

Covers the three observation-only mechanisms WP-0 adds:
  1. resolve_load_graph now reports per-file ``bytes`` (the cold-start size).
  2. acceptance_input_hash EXCLUDES ``bytes`` → byte-identical to its pre-WP-0
     value (the §3.5b reuse fingerprint is unchanged; old ledgers still match).
  3. load_sizer sums each role's cold-start bytes WITHOUT a spawn.
All stdlib unittest; no LLM, no network.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_ORCH_DIR)
for _p in (_ORCH_DIR, _ENGINE_KIT_DIR, _TESTS_DIR,
           os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import e2e_stage as es  # noqa: E402
import load_sizer as ls  # noqa: E402


def _write(root: str, rel: str, content: bytes) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


class ResolveLoadGraphBytesTests(unittest.TestCase):
    """resolve_load_graph reports each file's byte size; the sum is the real
    (deduplicated, include-followed) closure size."""

    def test_each_file_entry_carries_its_byte_size(self):
        with tempfile.TemporaryDirectory() as root:
            _write(root, "governance/a.md", b"a" * 100)
            _write(root, "governance/b.md", b"b" * 250)
            entries = [
                {"path": os.path.join(root, "governance/a.md"), "rel": "governance/a.md",
                 "purpose": "governance"},
                {"path": os.path.join(root, "governance/b.md"), "rel": "governance/b.md",
                 "purpose": "governance"},
            ]
            graph, missing = es.resolve_load_graph(entries, repo_root=root)
            self.assertEqual(missing, [])
            by_rel = {g["path"]: g for g in graph}
            self.assertEqual(by_rel["governance/a.md"]["bytes"], 100)
            self.assertEqual(by_rel["governance/b.md"]["bytes"], 250)
            self.assertEqual(sum(g["bytes"] for g in graph), 350)

    def test_transitive_include_bytes_counted_once(self):
        # a.md @-includes b.md (relative to a.md's dir); both are sized, deduped.
        with tempfile.TemporaryDirectory() as root:
            _write(root, "governance/b.md", b"b" * 80)
            a_content = b"@b.md\n" + b"a" * 60
            _write(root, "governance/a.md", a_content)
            entries = [{"path": os.path.join(root, "governance/a.md"),
                        "rel": "governance/a.md", "purpose": "governance"}]
            graph, _ = es.resolve_load_graph(entries, repo_root=root)
            self.assertEqual(len(graph), 2)  # a.md + its @-included b.md
            self.assertEqual(sum(g["bytes"] for g in graph), len(a_content) + 80)

    def test_unreadable_mandatory_root_reported_missing(self):
        # A MANDATORY root that EXISTS (passes isfile) but cannot be OPENED must be reported
        # in `missing` (fail-closed), not silently dropped into a partial graph — honoring
        # resolve_load_graph's contract ("missing = mandatory roots absent OR UNREADABLE")
        # on which the WP-7 cold-start fingerprint relies (invariant 6).
        with tempfile.TemporaryDirectory() as root:
            _write(root, "g/ok.md", b"o" * 50)             # readable
            bad = os.path.join(root, "g/locked.md")
            _write(root, "g/locked.md", b"x" * 10)         # exists -> passes isfile()
            real_open = open
            def fake_open(p, *a, **k):
                if os.path.realpath(str(p)) == os.path.realpath(bad):
                    raise PermissionError("simulated unreadable")
                return real_open(p, *a, **k)
            entries = [
                {"path": os.path.join(root, "g/ok.md"), "rel": "g/ok.md",
                 "purpose": "governance", "mandatory": True},
                {"path": bad, "rel": "g/locked.md", "purpose": "governance",
                 "mandatory": True},
            ]
            with mock.patch("builtins.open", side_effect=fake_open):
                graph, missing = es.resolve_load_graph(entries, repo_root=root)
            self.assertEqual([g["path"] for g in graph], ["g/ok.md"])   # readable resolved
            self.assertEqual([m["rel"] for m in missing], ["g/locked.md"])  # unreadable->missing

    def test_unreadable_non_mandatory_include_stays_best_effort(self):
        # An @-include (mandatory False) that fails to open is NOT a contract violation —
        # it stays best-effort (dropped, NOT reported missing). Only mandatory roots gate.
        with tempfile.TemporaryDirectory() as root:
            inc = os.path.join(root, "g/inc.md")
            _write(root, "g/inc.md", b"i" * 20)
            _write(root, "g/a.md", b"@inc.md\n" + b"a" * 20)
            real_open = open
            def fake_open(p, *a, **k):
                if os.path.realpath(str(p)) == os.path.realpath(inc):
                    raise PermissionError("simulated unreadable include")
                return real_open(p, *a, **k)
            entries = [{"path": os.path.join(root, "g/a.md"), "rel": "g/a.md",
                        "purpose": "governance", "mandatory": True}]
            with mock.patch("builtins.open", side_effect=fake_open):
                graph, missing = es.resolve_load_graph(entries, repo_root=root)
            self.assertEqual(missing, [])                  # include failure does NOT gate
            self.assertEqual([g["path"] for g in graph], ["g/a.md"])


class AcceptanceInputHashNeutralityTests(unittest.TestCase):
    """The observational ``bytes`` field MUST NOT enter acceptance_input_hash — the
    §3.5b reuse fingerprint stays byte-identical to its pre-WP-0 value."""

    def test_hash_ignores_bytes_field(self):
        with tempfile.TemporaryDirectory() as root:
            _write(root, "g/constitution.md", b"c" * 500)
            entries = [{"path": os.path.join(root, "g/constitution.md"),
                        "rel": "g/constitution.md", "purpose": "governance"}]
            graph, _ = es.resolve_load_graph(entries, repo_root=root)
            self.assertIn("bytes", graph[0])  # WP-0 added it
            # The pre-WP-0 graph shape = the same entries WITHOUT bytes.
            legacy = [{k: v for k, v in g.items() if k != "bytes"} for g in graph]
            self.assertNotIn("bytes", legacy[0])
            h_new = es.acceptance_input_hash("PROMPT", graph)
            h_legacy = es.acceptance_input_hash("PROMPT", legacy)
            self.assertEqual(h_new, h_legacy,
                             "acceptance_input_hash must be identical with/without bytes")

    def test_hash_ignores_bytes_with_inline_entries(self):
        # _acceptance_resolver_graph mixes an INLINE entry (tooling.e2e) with file
        # entries. Inline entries never carry `bytes`, so the exclusion must be a no-op
        # for them and identical for the mixed graph (the real Acceptance shape).
        with tempfile.TemporaryDirectory() as root:
            _write(root, "g/role-card.md", b"r" * 300)
            entries = [
                {"path": "tooling.e2e", "purpose": "executor_contract",
                 "inline": {"app_start_cmd": ["run", "--port", "{port}"]}},
                {"path": os.path.join(root, "g/role-card.md"), "rel": "g/role-card.md",
                 "purpose": "role_card"},
            ]
            graph, _ = es.resolve_load_graph(entries, repo_root=root)
            self.assertEqual(sum(1 for g in graph if "bytes" in g), 1)  # only the file
            self.assertTrue(any(g["purpose"] == "executor_contract" and "bytes" not in g
                                for g in graph))  # inline carries no bytes
            legacy = [{k: v for k, v in g.items() if k != "bytes"} for g in graph]
            self.assertEqual(es.acceptance_input_hash("P", graph),
                             es.acceptance_input_hash("P", legacy))

    def test_hash_still_tracks_content(self):
        # Sanity: excluding bytes does not make the hash blind to content (sha256).
        with tempfile.TemporaryDirectory() as root:
            _write(root, "g/x.md", b"one")
            e = [{"path": os.path.join(root, "g/x.md"), "rel": "g/x.md",
                  "purpose": "governance"}]
            g1, _ = es.resolve_load_graph(e, repo_root=root)
            h1 = es.acceptance_input_hash("P", g1)
            _write(root, "g/x.md", b"two-different-content")
            g2, _ = es.resolve_load_graph(e, repo_root=root)
            h2 = es.acceptance_input_hash("P", g2)
            self.assertNotEqual(h1, h2, "a content change must still change the hash")


class LoadSizerTests(unittest.TestCase):
    """load_sizer sums cold-start bytes statically (no spawn)."""

    def test_size_load_set_on_fixture(self):
        with tempfile.TemporaryDirectory() as root:
            _write(root, "governance/constitution.md", b"x" * 1000)
            _write(root, "role-cards/dev-agent.md", b"y" * 400)
            roots = [("governance/constitution.md", "governance"),
                     ("role-cards/dev-agent.md", "role_card")]
            out = ls.size_load_set(roots, repo_root=root)
            self.assertEqual(out["total_bytes"], 1400)
            self.assertEqual(out["est_tokens"], 1400 // ls.BYTES_PER_TOKEN_EST)
            self.assertEqual(out["by_purpose"], {"governance": 1000, "role_card": 400})
            self.assertEqual(out["missing"], [])

    def test_missing_root_is_reported_not_crash(self):
        with tempfile.TemporaryDirectory() as root:
            _write(root, "governance/constitution.md", b"x" * 10)
            roots = [("governance/constitution.md", "governance"),
                     ("role-cards/absent.md", "role_card")]
            out = ls.size_load_set(roots, repo_root=root)
            self.assertEqual(out["total_bytes"], 10)
            self.assertEqual(out["missing"], ["role-cards/absent.md"])

    def test_size_all_roles_on_real_framework_root(self):
        # The real checkout: every role's framework cold-start set must fully resolve (no
        # drift), and every role re-pays the SAME governance floor (§1.2 steps 1-3).
        sizes = ls.size_all_roles(repo_root=ls.REPO_ROOT_DEFAULT)
        self.assertEqual(set(sizes), set(ls.ROLES))
        floors = set()
        for role, s in sizes.items():
            self.assertEqual(s["missing"], [],
                             f"{role} cold-start has a missing/renamed doc: {s['missing']}")
            self.assertGreater(s["total_bytes"], 0)
            self.assertEqual(s["est_tokens"], s["total_bytes"] // ls.BYTES_PER_TOKEN_EST)
            # Default: adopter-static is NOT measured (declared None, not silently 0), and
            # total == framework. The run-dynamic members are enumerated, never dropped.
            self.assertIsNone(s["adopter_bytes"])
            self.assertEqual(s["total_bytes"], s["framework_bytes"])
            self.assertTrue(s["dynamic_unsized"],
                            f"{role} must DECLARE its run-dynamic cold-start members")
            floors.add(s["by_purpose"]["governance"])
        self.assertEqual(len(floors), 1,
                         "the governance floor must be identical across roles")

    def test_adopter_root_adds_adopter_static_set(self):
        # context_briefing.md §1.2 steps 4-5: with an adopter root, AGENTS.md +
        # docs/current/adoption-state.md are sized and added to total; an absent adopter
        # member surfaces in `missing` (reported, not silently dropped).
        with tempfile.TemporaryDirectory() as fw, tempfile.TemporaryDirectory() as adp:
            for rel, _purpose in ls.GOVERNANCE_TRIO + ls.ROLE_COLD_START["dev"]:
                _write(fw, rel, b"f" * 100)            # 6 framework files × 100 = 600
            _write(adp, "AGENTS.md", b"a" * 500)
            _write(adp, "docs/current/adoption-state.md", b"s" * 250)
            s = ls.size_role("dev", repo_root=fw, adopter_root=adp)
            self.assertEqual(s["framework_bytes"], 600)
            self.assertEqual(s["adopter_bytes"], 750)
            self.assertEqual(s["total_bytes"], 1350)
            self.assertEqual(s["est_tokens"], 1350 // ls.BYTES_PER_TOKEN_EST)
            self.assertEqual(s["missing"], [])

    def test_absent_adopter_member_reported_not_dropped(self):
        with tempfile.TemporaryDirectory() as fw, tempfile.TemporaryDirectory() as adp:
            for rel, _purpose in ls.GOVERNANCE_TRIO + ls.ROLE_COLD_START["dev"]:
                _write(fw, rel, b"f" * 100)
            _write(adp, "AGENTS.md", b"a" * 500)       # adoption-state.md absent
            s = ls.size_role("dev", repo_root=fw, adopter_root=adp)
            self.assertEqual(s["adopter_bytes"], 500)
            self.assertIn("(adopter) docs/current/adoption-state.md", s["missing"])

    def test_unknown_role_raises(self):
        with self.assertRaises(KeyError):
            ls.size_role("not-a-role", repo_root=ls.REPO_ROOT_DEFAULT)


class ColdStartLoadGraphHashTests(unittest.TestCase):
    """WP-7: ``role_cold_start_roots`` is the single source of truth for a role's cold-start
    set (with ``process/role-skill-model.md`` gated by ``skills_active``); and
    ``cold_start_load_graph_hash`` fingerprints it and CHANGES iff a cold-start doc's content
    changes — the audit-only mechanism that records which governance/kernel VERSION an
    otherwise prompt-only-input_hash spawn loaded."""

    def _stub(self, root: str, role: str, *, skills_active: bool = False,
              override: dict = None) -> None:
        """Materialize every file in ``role``'s cold-start set with distinct content (so
        each is independently fingerprinted). ``override`` replaces a specific rel's bytes."""
        override = override or {}
        for rel, _purpose in ls.role_cold_start_roots(role, skills_active=skills_active):
            _write(root, rel, override.get(rel, (rel + " v1\n").encode("utf-8")))

    # --- roots: the conditional source is gated by skills_active ------------------ #
    def test_roots_skills_off_excludes_role_skill_model(self):
        roots = ls.role_cold_start_roots("dev")
        self.assertNotIn(ls.ROLE_SKILL_MODEL, roots)
        self.assertIn(("governance/constitution-core.md", "governance"), roots)  # WP-2: kernel at cold-start
        self.assertIn(("governance/authoring-kernel.md", "governance"), roots)  # WP-3: kernel at cold-start
        self.assertNotIn(("governance/doc_governance.md", "governance"), roots)  # WP-3: canonical is on-demand
        self.assertIn(("role-cards/dev-agent.md", "role_card"), roots)

    def test_roots_skills_on_appends_role_skill_model_once(self):
        off = ls.role_cold_start_roots("dev")
        on = ls.role_cold_start_roots("dev", skills_active=True)
        self.assertEqual(on, off + [ls.ROLE_SKILL_MODEL])

    def test_roots_unknown_role_raises(self):
        with self.assertRaises(KeyError):
            ls.role_cold_start_roots("nope")

    # --- hash shape, determinism, missing-file drift ------------------------------ #
    def test_hash_shape_and_complete(self):
        with tempfile.TemporaryDirectory() as root:
            self._stub(root, "dev")
            h, missing = ls.cold_start_load_graph_hash("dev", repo_root=root)
            self.assertEqual(missing, [])
            self.assertTrue(h.startswith("sha256:"), h)
            self.assertEqual(len(h), len("sha256:") + 16)  # same shape as input_hash

    def test_hash_deterministic_when_nothing_changes(self):
        with tempfile.TemporaryDirectory() as root:
            self._stub(root, "dev")
            h1, _ = ls.cold_start_load_graph_hash("dev", repo_root=root)
            h2, _ = ls.cold_start_load_graph_hash("dev", repo_root=root)
            self.assertEqual(h1, h2)

    def test_missing_mandatory_file_surfaces_as_drift(self):
        with tempfile.TemporaryDirectory() as root:
            for rel, _p in ls.GOVERNANCE_TRIO:      # role card + briefing absent
                _write(root, rel, b"x")
            _h, missing = ls.cold_start_load_graph_hash("dev", repo_root=root)
            self.assertTrue(missing)                # the driver maps this to None

    def test_unreadable_cold_start_file_surfaces_as_missing(self):
        # Invariant 6 (the Codex-flagged case): a cold-start doc that EXISTS but cannot be
        # READ must NOT yield a confident partial fingerprint — it surfaces in `missing` so
        # the driver records None instead of a misleading hash over an incomplete set.
        with tempfile.TemporaryDirectory() as root:
            self._stub(root, "dev")
            locked = os.path.realpath(os.path.join(root, "governance/constitution-core.md"))
            real_open = open
            def fake_open(p, *a, **k):
                if os.path.realpath(str(p)) == locked:
                    raise PermissionError("simulated unreadable")
                return real_open(p, *a, **k)
            with mock.patch("builtins.open", side_effect=fake_open):
                _h, missing = ls.cold_start_load_graph_hash("dev", repo_root=root)
            # size_load_set maps missing entries to their rel STRINGS.
            self.assertIn("governance/constitution-core.md", missing)

    # --- THE WP-7 acceptance criterion: hash changes when a cold-start doc changes - #
    def test_hash_changes_when_a_cold_start_doc_changes(self):
        with tempfile.TemporaryDirectory() as root:
            self._stub(root, "dev")
            h1, _ = ls.cold_start_load_graph_hash("dev", repo_root=root)
            _write(root, "governance/constitution-core.md", b"MUTATED kernel content\n")
            h2, _ = ls.cold_start_load_graph_hash("dev", repo_root=root)
            self.assertNotEqual(h1, h2)

    def test_hash_is_role_specific(self):
        # Two roles with overlapping governance still fingerprint distinctly (the role
        # card differs AND the role label is part of the basis).
        with tempfile.TemporaryDirectory() as root:
            self._stub(root, "dev")
            self._stub(root, "review")
            h_dev, _ = ls.cold_start_load_graph_hash("dev", repo_root=root)
            h_rev, _ = ls.cold_start_load_graph_hash("review", repo_root=root)
            self.assertNotEqual(h_dev, h_rev)

    # --- the conditional source is correctly GATED -------------------------------- #
    def test_conditional_source_changes_fingerprint_only_when_active(self):
        with tempfile.TemporaryDirectory() as root:
            self._stub(root, "dev", skills_active=True)   # writes role-skill-model.md too
            h_off, m_off = ls.cold_start_load_graph_hash("dev", repo_root=root)
            h_on, m_on = ls.cold_start_load_graph_hash(
                "dev", repo_root=root, skills_active=True)
            self.assertEqual(m_off, [])
            self.assertEqual(m_on, [])
            self.assertNotEqual(h_off, h_on)              # the extra source shifts the hash
            # Mutating the conditional source moves the skills-ON hash but NOT the
            # skills-OFF hash (which never includes it) — proving correct gating.
            _write(root, "process/role-skill-model.md", b"MUTATED boundary constraints\n")
            h_on2, _ = ls.cold_start_load_graph_hash(
                "dev", repo_root=root, skills_active=True)
            h_off2, _ = ls.cold_start_load_graph_hash("dev", repo_root=root)
            self.assertNotEqual(h_on, h_on2)
            self.assertEqual(h_off, h_off2)

    def test_size_role_skills_active_counts_conditional_source(self):
        # The refactor keeps the skills-off default unchanged AND lets the sizer count the
        # conditional source when asked (real repo has process/role-skill-model.md).
        s_off = ls.size_role("dev")
        s_on = ls.size_role("dev", skills_active=True)
        self.assertGreater(s_on["framework_bytes"], s_off["framework_bytes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
