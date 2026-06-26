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


if __name__ == "__main__":
    unittest.main(verbosity=2)
