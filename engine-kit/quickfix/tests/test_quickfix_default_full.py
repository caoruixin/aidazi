"""Quick-Fix Commit 1 Default-Full regression (load-graph equivalence).

Proves the STANDARD startup path is unchanged by the Quick-Fix lane: the Full cold-start
load graph is the @-include closure of the consumer AGENTS.md template, and that closure
is still EXACTLY {AGENTS.md + the three always-load governance docs}. If the Quick-Fix
work (or anything) injected an @-include or grew the cold-start chain, this fails. The
lane spec itself is on-demand and must never appear in the closure.

This is the deterministic load-graph snapshot the revised plan (refinement 7) requires —
it checks the GRAPH, not content hashes, so it stays green when unrelated doc text
changes and only trips when the startup path actually changes.
"""
import os
import re
import unittest

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_THIS, "..", "..", ".."))

EXPECTED_COLDSTART_CLOSURE = {
    "AGENTS.md",
    "governance/constitution.md",
    "governance/doc_governance.md",
    "governance/context_briefing.md",
}


def _resolve(at_path):
    """Resolve an @-include target to a repo-relative path, or None if it does not
    resolve in the framework repo. AGENTS.md uses the vendored '@aidazi/...' prefix; in
    the framework repo the files live at the root, so a leading 'aidazi/' maps to root.
    Adopter placeholders ('@<adopter>/...') do not resolve here and are skipped."""
    if at_path.startswith("<"):
        return None
    rel = at_path[len("aidazi/"):] if at_path.startswith("aidazi/") else at_path
    return rel if os.path.isfile(os.path.join(_ROOT, rel)) else None


def _closure(start_rel):
    seen, stack, out = set(), [start_rel], set()
    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        seen.add(rel)
        out.add(rel)
        full = os.path.join(_ROOT, rel)
        if not os.path.isfile(full):
            continue
        with open(full, "r", encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^@(\S+)", line)
                if not m:
                    continue
                r = _resolve(m.group(1))
                if r:
                    stack.append(r)
    return out


class DefaultFullLoadGraph(unittest.TestCase):
    def test_coldstart_closure_is_exactly_the_governance_chain(self):
        self.assertEqual(_closure("AGENTS.md"), EXPECTED_COLDSTART_CLOSURE)

    def test_quickfix_lane_not_in_coldstart_closure(self):
        self.assertNotIn("process/quickfix-lane.md", _closure("AGENTS.md"))

    def test_quickfix_lane_is_on_demand(self):
        with open(os.path.join(_ROOT, "process", "quickfix-lane.md"), "r",
                  encoding="utf-8") as fh:
            head = fh.read(1400)
        self.assertIn("load_discipline: on-demand", head)


if __name__ == "__main__":
    unittest.main()
