"""WP-3 closure item 2 — cold-start governance LOAD-SET CONSISTENCY gate.

Forbids the WP-2 §5.1 drift class: the byte sizer / WP-7 ``load_graph_hash`` treating the
kernel trio (constitution-core + authoring-kernel + context_briefing) as the cold-start
governance load, while a role-card or context_briefing PROSE instruction still tells the agent
to load the full canonical ``constitution.md`` / ``doc_governance.md`` at cold-start. A drift
there means the audit fingerprint and the byte baseline disagree with what an agent literally
reads — exactly the gap the WP-2 behavioral canary found in the role cards.

Asserts FOUR sources agree on the always-load governance trio, with the full canonical named
ONLY as on-demand:
  (1) ``load_sizer.GOVERNANCE_TRIO``                       — the sizer's set;
  (2) ``load_sizer.role_cold_start_roots(role)`` governance prefix — this is the SINGLE source
      used by BOTH the WP-0 byte sizer (``size_role``) AND the WP-7 audit fingerprint
      (``cold_start_load_graph_hash``), so (1)==(2) ties the byte baseline and the hash input
      together by construction;
  (3) each role card's cold-start step-1 Load instruction prose;
  (4) ``governance/context_briefing.md`` §1.2 cold-start steps.

Note on token disambiguation: ``"constitution.md"`` is NOT a substring of
``"constitution-core.md"`` (the latter reads ``constitution-core.md``), so a plain substring
test cleanly separates the full canonical from the kernel.
"""
import os
import re
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCH = os.path.dirname(_HERE)
if _ORCH not in sys.path:
    sys.path.insert(0, _ORCH)
import load_sizer as ls  # noqa: E402

REPO = ls.REPO_ROOT_DEFAULT
KERNEL_TRIO = ["constitution-core.md", "authoring-kernel.md", "context_briefing.md"]
CANONICAL_FULL = ["constitution.md", "doc_governance.md"]  # must appear ONLY as on-demand
ROLE_CARDS = {
    "dev": "role-cards/dev-agent.md",
    "review": "role-cards/code-reviewer-agent.md",
    "acceptance": "role-cards/acceptance-agent.md",
    "deliver": "role-cards/deliver-agent.md",
    "research": "role-cards/research-agent.md",
}

# Denylist scan: any file carrying a cold-start / load_list instruction. A list-item or numbered
# step that names a FULL canonical (constitution.md / doc_governance.md) without "on-demand" is a
# drift. ("constitution.md" is not a substring of "constitution-core.md", so the kernels never
# trip this.) Covers the compact-prompt templates + example adopter + guide that round-2 review
# found still loading the full canonical.
LOAD_BEARING_COLD_START_FILES = [
    "AGENTS.md",
    "examples/minimal-greenfield/AGENTS.md",
    "governance/context_briefing.md",
    "role-cards/dev-agent.md", "role-cards/code-reviewer-agent.md",
    "role-cards/acceptance-agent.md", "role-cards/deliver-agent.md", "role-cards/research-agent.md",
    "templates/compact-dev-prompt.md", "templates/compact-review-prompt.md",
    "templates/compact-acceptance-prompt.md", "templates/compact-codex-rebuttal-prompt.md",
    "docs/greenfield-guide.md",
]
# A full-canonical basename used as a LOAD (not a "<file>.md §X" section CITATION — citations
# point to a specific section the kernel also carries, so they are references / on-demand pointers,
# not bulk cold-start loads). The negative lookahead exempts citations.
_CANON_LOAD = re.compile(r"(?:constitution|doc_governance)\.md(?! *§)")
# A cold-start LOAD shape: a markdown/YAML list item, a numbered step, OR a prose load-chain
# (arrow `→` between paths, e.g. the example adopter's "this file → constitution.md → ..."). The
# arrow clause closes the gap where a prose cold-start order escaped a list-only scan.
_LOAD_SHAPE = re.compile(r"^\s*(?:[-*]\s|\d+\.\s)|→")


def _read(rel: str) -> str:
    with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
        return fh.read()


class ColdStartConsistencyTests(unittest.TestCase):
    # ---- (1)+(2): sizer trio == WP-7 hash input trio == the KERNEL trio (not canonical) ----
    def test_governance_trio_is_the_kernel_trio(self):
        self.assertEqual([os.path.basename(r) for r, _ in ls.GOVERNANCE_TRIO], KERNEL_TRIO)
        for r, _ in ls.GOVERNANCE_TRIO:
            self.assertNotIn(os.path.basename(r), CANONICAL_FULL)

    def test_every_role_cold_start_roots_lead_with_kernel_trio(self):
        # role_cold_start_roots is the SINGLE source for BOTH size_role (the byte baseline) and
        # cold_start_load_graph_hash (the WP-7 audit fingerprint); asserting its governance prefix
        # is the kernel trio ties (1) and (2) together — neither the bytes nor the hash can see a
        # canonical doc the prose no longer loads.
        for role in ls.ROLES:
            roots = ls.role_cold_start_roots(role)
            govs = [os.path.basename(r) for r, p in roots if p == "governance"]
            self.assertEqual(govs, KERNEL_TRIO, f"{role}: governance roots drifted from kernel trio")
            for r, _p in roots:
                self.assertNotIn(os.path.basename(r), CANONICAL_FULL,
                                 f"{role}: cold-start must NOT load full canonical {r}")

    # ---- (3): role-card cold-start PROSE names the kernel trio; canonical only on-demand ----
    def test_role_card_cold_start_prose_matches_kernel_trio(self):
        for role, rel in ROLE_CARDS.items():
            text = _read(rel)
            lines = [l for l in text.splitlines()
                     if re.match(r"\s*1\.\s*Load", l) and "constitution-core.md" in l]
            self.assertEqual(len(lines), 1,
                             f"{rel}: expected exactly one cold-start step-1 Load line naming "
                             f"constitution-core.md, found {len(lines)}")
            line = lines[0]
            for k in KERNEL_TRIO:
                self.assertIn(k, line, f"{rel} step-1 missing kernel {k}")
            for c in CANONICAL_FULL:
                if c in line:
                    self.assertIn("on-demand", line.lower(),
                                  f"{rel} step-1 names full {c} but not as on-demand: {line!r}")

    # ---- (4): EVERY cold-start prose region names the kernel trio; canonical only on-demand ----
    def _assert_region_kernel_trio(self, region: str, label: str):
        self.assertNotEqual(region.strip(), "", f"{label}: region not found / empty")
        for k in KERNEL_TRIO:
            self.assertIn(k, region, f"{label}: missing kernel {k}")
        for line in region.splitlines():
            for c in CANONICAL_FULL:
                if c in line:
                    self.assertIn("on-demand", line.lower(),
                                  f"{label}: names full {c} not as on-demand: {line!r}")

    @staticmethod
    def _section(text: str, start_marker: str, end_prefix: str = "\n## ") -> str:
        start = text.find(start_marker)
        if start < 0:
            return ""
        end = text.find(end_prefix, start + len(start_marker))
        return text[start: end if end > -1 else len(text)]

    def test_context_briefing_s12_cold_start_matches_kernel_trio(self):
        text = _read("governance/context_briefing.md")
        self._assert_region_kernel_trio(self._section(text, "### §1.2"),
                                        "context_briefing §1.2 cold-start order")

    def test_context_briefing_context_pack_matches_kernel_trio(self):
        # §3 Context Pack Prompt is a SECOND cold-start load instruction (the paste-able skeleton).
        text = _read("governance/context_briefing.md")
        self._assert_region_kernel_trio(self._section(text, "## §3 Context Pack Prompt"),
                                        "context_briefing §3 Context Pack Prompt")

    def test_root_agents_md_governance_chain_matches_kernel_trio(self):
        # The framework root AGENTS.md §2 is the role/Control-Plane governance-chain load list and is
        # itself part of role cold-start (context_briefing §1.2 step 4) + resolver-bound — so it must
        # name the kernel trio, never the full canonical at cold-start.
        text = _read("AGENTS.md")
        self._assert_region_kernel_trio(self._section(text, "## §2 Framework governance chain"),
                                        "AGENTS.md §2 governance chain")

    # ---- denylist: no load-bearing file loads a FULL canonical at cold-start ----
    def test_no_loadbearing_file_loads_full_canonical_at_cold_start(self):
        offenders = []
        for rel in LOAD_BEARING_COLD_START_FILES:
            for n, line in enumerate(_read(rel).splitlines(), 1):
                if (_LOAD_SHAPE.search(line) and _CANON_LOAD.search(line)
                        and "on-demand" not in line.lower()):
                    offenders.append(f"{rel}:{n}: {line.strip()}")
        self.assertEqual(offenders, [],
                         "cold-start/load_list still loads a full canonical (use the kernel trio; "
                         "name the full canonical only as on-demand):\n" + "\n".join(offenders))

    # ---- cross-check: the prose trio and the structural trio are the SAME set ----
    def test_prose_and_structural_trio_are_identical(self):
        structural = set(KERNEL_TRIO)
        self.assertEqual(set(os.path.basename(r) for r, _ in ls.GOVERNANCE_TRIO), structural)
        # every role card step-1 line carries exactly the structural trio basenames
        for role, rel in ROLE_CARDS.items():
            line = next(l for l in _read(rel).splitlines()
                        if re.match(r"\s*1\.\s*Load", l) and "constitution-core.md" in l)
            present = {b for b in structural if b in line}
            self.assertEqual(present, structural, f"{rel}: step-1 trio {present} != {structural}")


if __name__ == "__main__":
    unittest.main()
