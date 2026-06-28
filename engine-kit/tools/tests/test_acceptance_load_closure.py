"""Tests for the WP-4 Acceptance LOAD-CLOSURE harness (stdlib unittest).

Three-layer proof (engine-kit/tools/acceptance_load_closure.py):
  (a) manifest well-formedness, (b) bidirectional parser drift-guard, (c) live cross-check.
Plus: the WP-4A unwired state is asserted EXPLICITLY — closure_state reports the exact pending set
(GREEN known-pending test), while the STRICT closure assertion is an expectedFailure until WP-4B.
No runtime is mutated to force green.
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
_ENGINE_KIT = os.path.dirname(_TOOLS_DIR)
_ORCH_DIR = os.path.join(_ENGINE_KIT, "orchestrator")
# _ENGINE_KIT + engine-kit/audit so `import e2e_stage` resolves its `audit_log` dependency
# (`import audit_log` / `from audit import audit_log`) when this file is run standalone, not only
# under `pytest engine-kit` where the rootdir is already on the path.
for _p in (_TOOLS_DIR, _ORCH_DIR, _ENGINE_KIT, os.path.join(_ENGINE_KIT, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

import acceptance_load_closure as alc  # noqa: E402

REPO = alc.REPO_ROOT_DEFAULT


# Minimal source-file fixtures the layer-(b) parser reads (the real files are large; the parser
# only needs the §1 / §11 / §6 section shapes).
_ROLE_CARD_TMPL = """# Acceptance Agent

## §1 Cold-start activation
{steps}

## §2 next
body

## §11 Role skills
Per `process/role-skill-model.md` (load it if `charter.tooling.acceptance.skills` is non-empty):
- stuff

End of Acceptance Agent role card.
"""

_CTX_TMPL = """## §6 Δ-18 Delivery Loop trigger

Load `{dl}` when ANY of these is true for your session:

- The adopter's charter exists at `<adopter>/charter.yaml`.
- Your role is Acceptance Agent AND `tooling.acceptance.mode` != off.

## §7 next
"""


_CTX_FULL_TMPL = """## §2 Briefing

### §2.5 Acceptance Agent

For producing `docs/acceptance-reports/<scope>-acceptance-report.md`.

- `aidazi/role-cards/acceptance-agent.md` — your activation prompt.
- `aidazi/templates/compact-acceptance-prompt.md` — output template + judging discipline.
- Adopter inputs: dev evidence (trace artifacts per `process/delivery-loop.md` §4.2.6).
{s25_extra}
Tool whitelist: Read, Grep, Glob.

### §2.6 Deliver Agent

body

## §6 Δ-18 Delivery Loop trigger

Load `{dl}` when ANY of these is true for your session:

- The task involves resolving a MANDATORY_CHECKPOINT.
{carveout}{s6_extra}

## §7 next
"""

_CARVEOUT_LINE = ("\n**Acceptance Agent EXCEPTION:** an Acceptance verdict session does NOT load "
                  "`process/delivery-loop.md` — projected INLINE via the acceptance-kernel (see "
                  "`role-cards/acceptance-agent.md` §1).\n")


@unittest.skipIf(yaml is None, "PyYAML not installed")
class _SrcRepoMixin(unittest.TestCase):
    def _src_repo(self, *, step_paths, dl="process/delivery-loop.md"):
        root = Path(tempfile.mkdtemp(prefix="acc_closure_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "role-cards").mkdir(parents=True)
        (root / "governance").mkdir(parents=True)
        steps = "\n".join(f"{i}. Load `{p}`." for i, p in enumerate(step_paths, 1))
        (root / "role-cards" / "acceptance-agent.md").write_text(
            _ROLE_CARD_TMPL.format(steps=steps), encoding="utf-8")
        (root / "governance" / "context_briefing.md").write_text(
            _CTX_TMPL.format(dl=dl), encoding="utf-8")
        return root

    def _src_repo_full(self, *, step_paths=("aidazi/process/delivery-loop.md",),
                       s25_extra="", s6_extra="", carveout=True, dl="process/delivery-loop.md"):
        """A richer fixture whose context_briefing.md carries BOTH a §2.5 Acceptance per-role briefing
        list AND a §6 delivery-loop trigger with the WP-4B Acceptance carve-out — so the §2.5 / §6
        non-vacuity of the drift-guard can be exercised."""
        root = self._src_repo(step_paths=list(step_paths), dl=dl)
        (root / "governance" / "context_briefing.md").write_text(
            _CTX_FULL_TMPL.format(dl=dl, s25_extra=s25_extra, s6_extra=s6_extra,
                                  carveout=_CARVEOUT_LINE if carveout else ""), encoding="utf-8")
        return root


@unittest.skipIf(yaml is None, "PyYAML not installed")
class RealTreeTests(unittest.TestCase):
    """The shipped manifest + harness on the real tree."""

    def test_layers_pass_for_already_true_dispositions(self):
        # Layers (a)+(b)+(c) pass: every NON-pending entry's disposition holds on this tree.
        res = alc.check_all(REPO)
        self.assertTrue(res["ok"], msg=str(res["errors"]))

    def test_bidirectional_set_equality_on_real_tree(self):
        manifest = alc.load_manifest(REPO)
        self.assertEqual(alc.check_bidirectional(manifest, REPO), [])

    def test_resolver_binds_the_governance_chain(self):
        bound = alc.resolver_bound_rels(REPO)
        for rel in ("governance/constitution-core.md", "governance/constitution.md",
                    "governance/authoring-kernel.md", "governance/doc_governance.md",
                    "governance/context_briefing.md", "role-cards/acceptance-agent.md",
                    "schemas/compact/acceptance-verdict.compact.schema.json", "AGENTS.md",
                    "docs/codex-findings.md"):
            self.assertIn(rel, bound, msg=f"{rel} not bound in _acceptance_resolver_graph")


@unittest.skipIf(yaml is None, "PyYAML not installed")
class ClosureStateTests(unittest.TestCase):
    """WP-4B WIRED: the Acceptance LOAD-CLOSURE invariant now HOLDS — every Acceptance-reachable load
    is inlined (kernel embedded in the projected prompt) / resolver-bound / HALT-routed, with no
    unbound verdict-affecting read and no pending transition."""

    def test_strict_closure_holds(self):
        cs = alc.closure_state(REPO)
        self.assertTrue(cs["closed"], msg=f"unexpected pending: {cs['pending']}")
        self.assertTrue(cs["kernel_embedded"])
        self.assertEqual(cs["pending"], [])

    def test_retired_files_are_inlined_not_unbound(self):
        # The two retired whole-file reads: their load triggers are GONE (negated / §6 carve-out) and
        # they are correctly NOT resolver-bound (their content is inlined into the embedded kernel, so
        # there is nothing to bind). This is the proof they are not unbound on-demand reads.
        cs = alc.closure_state(REPO)
        for f in alc.RETIRED_FILES:
            self.assertFalse(cs["retired_files"][f]["trigger_live"],
                             msg=f"{f} load trigger should be retired")
            self.assertFalse(cs["retired_files"][f]["resolver_bound"],
                             msg=f"{f} is INLINED, so it should NOT be resolver-bound")


@unittest.skipIf(yaml is None, "PyYAML not installed")
class BidirectionalGuardTests(_SrcRepoMixin):
    """Layer (b): the manifest's parse-token set must equal the parser's, both directions."""

    def test_new_unclassified_load_instruction_is_caught(self):
        # An injected "Load `process/injected.md`" in §1 that the manifest does not declare → caught.
        root = self._src_repo(step_paths=["aidazi/process/delivery-loop.md", "process/injected.md"])
        manifest = {"entries": [
            {"source": "x", "region": "acceptance_cold_start",
             "parse_token": "aidazi/process/delivery-loop.md", "disposition": "INLINED",
             "target": "process/delivery-loop.md", "evidence": "e"},
            {"source": "rs", "region": "acceptance_role_skill",
             "parse_token": "process/role-skill-model.md", "disposition": "INLINED",
             "target": "process/role-skill-model.md", "evidence": "e"},
            {"source": "dl6", "region": "context_briefing_delivery_loop",
             "parse_token": "process/delivery-loop.md", "disposition": "INLINED",
             "target": "process/delivery-loop.md", "evidence": "e"},
        ]}
        errs = alc.check_bidirectional(manifest, root)
        self.assertTrue(any("process/injected.md" in e and "NOT in the manifest" in e for e in errs),
                        msg=str(errs))

    def test_load_instruction_outside_section1_is_caught(self):
        # Codex R8-B1: a "Load `<path>`" added ELSEWHERE in the role card (not §1/§11) must be caught
        # by the catch-all scan (region acceptance_role_card_other), so check_bidirectional fails.
        root = self._src_repo(step_paths=["aidazi/process/delivery-loop.md"])
        rc = root / "role-cards" / "acceptance-agent.md"
        text = rc.read_text(encoding="utf-8").replace(
            "## §2 next\nbody",
            "## §2 next\nbody\n- Load `process/sneaked-in.md` for some reason.")
        rc.write_text(text, encoding="utf-8")
        parsed = alc.parse_reachable_loads(root)
        self.assertIn(("acceptance_role_card_other", "process/sneaked-in.md"), parsed)
        # A manifest without it → bidirectional guard fails.
        manifest = {"entries": [
            {"source": "x", "region": "acceptance_cold_start",
             "parse_token": "aidazi/process/delivery-loop.md", "disposition": "INLINED",
             "target": "process/delivery-loop.md", "evidence": "e"},
            {"source": "rs", "region": "acceptance_role_skill",
             "parse_token": "process/role-skill-model.md", "disposition": "INLINED",
             "target": "process/role-skill-model.md", "evidence": "e"},
            {"source": "dl6", "region": "context_briefing_delivery_loop",
             "parse_token": "process/delivery-loop.md", "disposition": "INLINED",
             "target": "process/delivery-loop.md", "evidence": "e"}]}
        errs = alc.check_bidirectional(manifest, root)
        self.assertTrue(any("process/sneaked-in.md" in e and "NOT in the manifest" in e for e in errs),
                        msg=str(errs))

    def test_new_positive_load_in_s25_is_caught(self):
        # Codex WP-4B-R1 BLOCKING: a NON-bullet-leading positive "Load `X`" added to context_briefing
        # §2.5 must be caught (the §2.5 parser previously only saw bullet-leading backtick paths, so a
        # new positive load escaped the drift-guard).
        root = self._src_repo_full(
            s25_extra="Load `process/new-s25-positive.md` as an extra Acceptance input.\n")
        parsed = alc.parse_reachable_loads(root)
        self.assertIn(("context_briefing_acceptance_role", "process/new-s25-positive.md"), parsed)
        # A manifest that does not declare it → bidirectional guard fails on the new token.
        errs = alc.check_bidirectional({"entries": []}, root)
        self.assertTrue(
            any("process/new-s25-positive.md" in e and "NOT in the manifest" in e for e in errs),
            msg=str(errs))

    def test_new_positive_load_in_s6_is_caught_despite_carveout(self):
        # Codex WP-4B-R1 BLOCKING: the §6 Acceptance carve-out must suppress ONLY the carved token
        # (process/delivery-loop.md), NOT the whole section — a genuinely NEW positive "Load `Y`" in
        # §6 must STILL be caught even with the carve-out present.
        root = self._src_repo_full(
            carveout=True,
            s6_extra="Load `process/new-s6-positive.md` for a brand-new reason.\n")
        parsed = alc.parse_reachable_loads(root)
        self.assertIn(("context_briefing_delivery_loop", "process/new-s6-positive.md"), parsed)
        # the carved delivery-loop token is correctly NOT routed to Acceptance
        self.assertNotIn(("context_briefing_delivery_loop", "process/delivery-loop.md"), parsed)
        errs = alc.check_bidirectional({"entries": []}, root)
        self.assertTrue(
            any("process/new-s6-positive.md" in e and "NOT in the manifest" in e for e in errs),
            msg=str(errs))

    def test_positive_load_mentioning_retired_word_is_still_caught(self):
        # Codex WP-4B-R2 BLOCKING: negation is tied to negative-load SYNTAX, not a bare "retired"
        # word — a POSITIVE "Load `X` ... retired ..." line must NOT be mistaken for a negated load
        # and must still reach check_bidirectional.
        root = self._src_repo_full(
            s6_extra="Load `process/new-s6-retiredword.md` for retired-source compatibility.\n",
            s25_extra="Load `process/new-s25-retiredword.md` (the legacy reader is retired).\n")
        parsed = alc.parse_reachable_loads(root)
        self.assertIn(("context_briefing_delivery_loop", "process/new-s6-retiredword.md"), parsed)
        self.assertIn(("context_briefing_acceptance_role", "process/new-s25-retiredword.md"), parsed)
        errs = alc.check_bidirectional({"entries": []}, root)
        for tok in ("process/new-s6-retiredword.md", "process/new-s25-retiredword.md"):
            self.assertTrue(any(tok in e and "NOT in the manifest" in e for e in errs), msg=str(errs))

    def test_is_negated_load_requires_negative_syntax_not_just_retired_word(self):
        # Unit-level proof of the R2 fix: negative-load SYNTAX is negation; a bare "retired" mention
        # on an otherwise-positive load line is NOT.
        self.assertTrue(alc._is_negated_load("Do NOT load `x.md`"))
        self.assertTrue(alc._is_negated_load("an Acceptance session does NOT load `x.md`"))
        self.assertTrue(alc._is_negated_load("- never load `x.md` here"))
        self.assertTrue(alc._is_negated_load("you must not load `x.md`"))
        self.assertFalse(alc._is_negated_load("Load `x.md` for retired-source compatibility."))
        self.assertFalse(alc._is_negated_load("Load `x.md` (the old reader was retired)."))

    def test_token_load_polarity_is_per_token(self):
        # Codex WP-4B-R3: negation is PER-TOKEN, not whole-line. A mixed line classifies each token by
        # its nearest governing 'load' keyword, in either order.
        self.assertEqual(
            alc._token_load_polarity("Load `process/new.md`; do NOT load `process/delivery-loop.md`"),
            {"process/new.md": "positive", "process/delivery-loop.md": "negative"})
        self.assertEqual(
            alc._token_load_polarity("do NOT load `process/delivery-loop.md`; Load `process/new2.md`"),
            {"process/delivery-loop.md": "negative", "process/new2.md": "positive"})
        # a bullet-leading path / a prose §-citation has no governing 'load' keyword -> None
        self.assertEqual(alc._token_load_polarity("- `aidazi/x.md` — desc"), {"aidazi/x.md": None})
        self.assertEqual(alc._token_load_polarity("see `process/y.md` §4.2.6"), {"process/y.md": None})

    def test_mixed_positive_and_negative_load_in_s25_surfaces_positive(self):
        # Codex WP-4B-R3 BLOCKING: a §2.5 line with BOTH a positive and a negative load must still
        # surface the positive one (whole-line suppression would drop it).
        root = self._src_repo_full(
            s25_extra="Load `process/new-s25-mixed.md`; do NOT load `process/delivery-loop.md`.\n")
        parsed = alc.parse_reachable_loads(root)
        self.assertIn(("context_briefing_acceptance_role", "process/new-s25-mixed.md"), parsed)
        errs = alc.check_bidirectional({"entries": []}, root)
        self.assertTrue(
            any("process/new-s25-mixed.md" in e and "NOT in the manifest" in e for e in errs),
            msg=str(errs))

    def test_mixed_positive_and_negative_load_in_s6_surfaces_positive(self):
        # Codex WP-4B-R3 BLOCKING: a §6 line carrying BOTH a new positive load AND the delivery-loop
        # carve-out must surface the positive one; delivery-loop.md stays carved.
        root = self._src_repo_full(
            carveout=True,
            s6_extra="Load `process/new-s6-mixed.md`; do NOT load `process/delivery-loop.md`.\n")
        parsed = alc.parse_reachable_loads(root)
        self.assertIn(("context_briefing_delivery_loop", "process/new-s6-mixed.md"), parsed)
        self.assertNotIn(("context_briefing_delivery_loop", "process/delivery-loop.md"), parsed)
        errs = alc.check_bidirectional({"entries": []}, root)
        self.assertTrue(
            any("process/new-s6-mixed.md" in e and "NOT in the manifest" in e for e in errs),
            msg=str(errs))

    def test_s6_carveout_is_a_real_per_token_suppression(self):
        # Non-vacuity of the carve-out itself: WITH the Acceptance carve-out, delivery-loop.md is NOT
        # an Acceptance-reachable §6 load; WITHOUT it, the §6 trigger header IS caught (proving the
        # suppression is real and token-specific, not a blanket section drop).
        with_carve = alc.parse_reachable_loads(self._src_repo_full(carveout=True))
        without_carve = alc.parse_reachable_loads(self._src_repo_full(carveout=False))
        key = ("context_briefing_delivery_loop", "process/delivery-loop.md")
        self.assertNotIn(key, with_carve)
        self.assertIn(key, without_carve)

    def test_stale_manifest_entry_is_caught(self):
        # The manifest declares a parse_token the parser no longer finds → caught.
        root = self._src_repo(step_paths=["aidazi/process/delivery-loop.md"])
        manifest = {"entries": [
            {"source": "x", "region": "acceptance_cold_start",
             "parse_token": "aidazi/process/delivery-loop.md", "disposition": "INLINED",
             "target": "process/delivery-loop.md", "evidence": "e"},
            {"source": "rs", "region": "acceptance_role_skill",
             "parse_token": "process/role-skill-model.md", "disposition": "INLINED",
             "target": "process/role-skill-model.md", "evidence": "e"},
            {"source": "dl6", "region": "context_briefing_delivery_loop",
             "parse_token": "process/delivery-loop.md", "disposition": "INLINED",
             "target": "process/delivery-loop.md", "evidence": "e"},
            {"source": "ghost", "region": "acceptance_cold_start",
             "parse_token": "process/ghost.md", "disposition": "RESOLVER_BOUND",
             "target": "process/ghost.md", "evidence": "e"},
        ]}
        errs = alc.check_bidirectional(manifest, root)
        self.assertTrue(any("process/ghost.md" in e and "stale" in e for e in errs), msg=str(errs))


@unittest.skipIf(yaml is None, "PyYAML not installed")
class CrossCheckAndWellformednessTests(unittest.TestCase):
    """Layers (a)+(c) against the real resolver."""

    def test_resolver_bound_target_not_in_resolver_is_caught(self):
        manifest = {"entries": [
            {"source": "fake", "region": None, "parse_token": None, "disposition": "RESOLVER_BOUND",
             "target": "governance/not-bound-anywhere.md", "evidence": "e"}]}
        errs = alc.check_live_crosscheck(manifest, REPO)
        self.assertTrue(any("not-bound-anywhere.md" in e and "NOT bound" in e for e in errs))

    def test_resolver_bound_rels_excludes_join_fragments(self):
        # Codex R6-B2: an os.path.join ARG fragment (e.g. "acceptance-agent.md", "governance") must
        # NOT count as a bound rel — only the joined path + explicit "rel": "<literal>" fields do.
        bound = alc.resolver_bound_rels(REPO)
        self.assertIn("role-cards/acceptance-agent.md", bound)      # the real joined rel
        self.assertNotIn("acceptance-agent.md", bound)              # a bare join fragment
        self.assertNotIn("governance", bound)
        self.assertNotIn("role-cards", bound)

    def test_bogus_resolver_bound_literal_target_is_caught(self):
        manifest = {"entries": [
            {"source": "frag", "region": None, "parse_token": None, "disposition": "RESOLVER_BOUND",
             "target": "acceptance-agent.md", "evidence": "e"}]}
        errs = alc.check_live_crosscheck(manifest, REPO)
        self.assertTrue(any("acceptance-agent.md" in e and "NOT bound" in e for e in errs), msg=str(errs))

    def test_bogus_data_purpose_is_caught(self):
        # Codex R6-B2: a data:<purpose> must name an ACTUAL "purpose" tag, not a substring of the body.
        for bogus in ("data:path", "data:mandatory"):
            manifest = {"entries": [
                {"source": bogus, "region": None, "parse_token": None,
                 "disposition": "RESOLVER_BOUND", "target": bogus, "evidence": "e"}]}
            errs = alc.check_live_crosscheck(manifest, REPO)
            self.assertTrue(any("not an actual" in e for e in errs), msg=f"{bogus}: {errs}")
        # A real purpose passes.
        ok = {"entries": [
            {"source": "real", "region": None, "parse_token": None, "disposition": "RESOLVER_BOUND",
             "target": "data:f5_evidence", "evidence": "e"}]}
        self.assertEqual(alc.check_live_crosscheck(ok, REPO), [])

    def test_pending_entry_is_skipped_by_crosscheck(self):
        # A pending_wp4b RESOLVER_BOUND target whose binding is not yet applied must NOT error in
        # the cross-check (it is tracked by closure_state instead).
        manifest = {"entries": [
            {"source": "pend", "region": None, "parse_token": None, "disposition": "RESOLVER_BOUND",
             "target": "governance/not-bound-anywhere.md", "evidence": "e",
             "status": "pending_wp4b"}]}
        self.assertEqual(alc.check_live_crosscheck(manifest, REPO), [])

    def test_manifest_wellformedness_catches_defects(self):
        bad = {"entries": [
            {"source": "a", "disposition": "BOGUS", "evidence": "e"},
            {"source": "b", "disposition": "RESOLVER_BOUND"},                       # no evidence
            {"source": "c", "disposition": "INLINED", "evidence": "e"},             # no target
            {"source": "d", "region": "r", "parse_token": "t", "disposition": "HALT_ROUTED",
             "evidence": "e"},
            {"source": "e", "region": "r", "parse_token": "t", "disposition": "HALT_ROUTED",
             "evidence": "e"},                                                       # dup parse_token
        ]}
        errs = alc.check_manifest_wellformed(bad)
        joined = " ".join(errs)
        self.assertIn("invalid disposition", joined)
        self.assertIn("missing 'evidence'", joined)
        self.assertIn("INLINED requires a 'target'", joined)
        self.assertIn("duplicate parse_token", joined)

    def test_halt_routed_sentinel_exists(self):
        # The HALT route is real: the sentinel + the refine-halt method exist in the driver.
        driver = (REPO / "engine-kit" / "orchestrator" / "driver.py").read_text(encoding="utf-8")
        self.assertIn("_ACCEPTANCE_SPEC_HALT = object()", driver)
        self.assertIn("def _acceptance_spec_refine_halt", driver)
        self.assertIn("return _ACCEPTANCE_SPEC_HALT", driver)

    def test_halt_routed_crosscheck_is_non_vacuous(self):
        # The strengthened HALT cross-check proves WIRING, not just that a string exists: a manifest
        # naming a non-existent HALT method must FAIL (so a broken/unwired route cannot pass).
        manifest = {"entries": [
            {"source": "broken-halt", "region": None, "parse_token": None,
             "disposition": "HALT_ROUTED", "target": "_no_such_halt_method", "evidence": "e"}]}
        errs = alc.check_live_crosscheck(manifest, REPO)
        self.assertTrue(any("not defined in driver.py" in e for e in errs), msg=str(errs))
        # The real target passes (defined, returns the sentinel, invoked by _resolve_acceptance_spec).
        real = {"entries": [
            {"source": "real-halt", "region": None, "parse_token": None,
             "disposition": "HALT_ROUTED", "target": "_acceptance_spec_refine_halt", "evidence": "e"}]}
        self.assertEqual(alc.check_live_crosscheck(real, REPO), [])

    def test_manifest_enumerates_criteria_and_evidence_loads(self):
        # Completeness: the verdict-affecting closure_contract + F5 evidence loads (role card §1
        # steps 7-8) are enumerated and RESOLVER_BOUND, so deleting their resolver bindings would
        # fail the gate (R4 BLOCKING-1).
        manifest = alc.load_manifest(REPO)
        targets = {e.get("target") for e in manifest["entries"]}
        self.assertIn("data:closure_contract", targets)
        self.assertIn("data:f5_evidence", targets)            # static (M1) class
        self.assertIn("data:functional_checklist", targets)   # browser_e2e (M3) — Codex R7-B1
        self.assertIn("data:evidence_manifest", targets)      # browser_e2e (M3) — Codex R7-B1
        # All resolve in the live resolver (no errors from the cross-check for these entries).
        self.assertEqual(alc.check_live_crosscheck(manifest, REPO), [])


@unittest.skipIf(yaml is None, "PyYAML not installed")
class ResolverHashBindingTests(unittest.TestCase):
    """Layer (c) mechanism: a content change to a RESOLVER_BOUND file moves acceptance_input_hash."""

    def test_content_change_moves_acceptance_input_hash(self):
        import e2e_stage
        tmp = Path(tempfile.mkdtemp(prefix="acc_hash_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        f = tmp / "governance" / "constitution-core.md"
        f.parent.mkdir(parents=True)
        entries = [{"path": str(f), "rel": "governance/constitution-core.md",
                    "purpose": "framework_role_session_governance"}]
        f.write_text("kernel v1", encoding="utf-8")
        g1, _ = e2e_stage.resolve_load_graph(entries, repo_root=str(tmp))
        h1 = e2e_stage.acceptance_input_hash("PROMPT", g1)
        f.write_text("kernel v2 — a meaning-changing edit", encoding="utf-8")
        g2, _ = e2e_stage.resolve_load_graph(entries, repo_root=str(tmp))
        h2 = e2e_stage.acceptance_input_hash("PROMPT", g2)
        self.assertNotEqual(h1, h2, "a content change to a resolver-bound file must move the hash")


@unittest.skipIf(yaml is None, "PyYAML not installed")
class KernelGapContentTests(unittest.TestCase):
    """The acceptance-kernel carries the six judge-instruction gaps + F5 + calibration content
    (spot-checks beyond the coverage gate, asserting the judge-facing phrasing is present)."""

    @classmethod
    def setUpClass(cls):
        # Normalize the same way the coverage gate's _normalize_for_match does (collapse whitespace +
        # strip `code`/**bold**) so spot-check fragments match regardless of line-wrap / decoration.
        import re
        raw = (REPO / "governance" / "acceptance-kernel.md").read_text(encoding="utf-8")
        cls.body = re.sub(r"\s+", " ", re.sub(r"[`*]", "", raw)).strip()

    def _has(self, *frags):
        for frag in frags:
            self.assertIn(frag, self.body, msg=f"acceptance-kernel.md missing: {frag!r}")

    def test_six_gaps_present(self):
        self._has(
            "Research–Acceptance contract symmetry check",                       # G7
            "verdict is pass ONLY if delivered behavior matches the positive shape",  # G18
            "you MUST write the acceptance report",                              # G21
            "suggest the route fitting the failure shape",                       # G22
            "Set needs_human on a spawn-isolation breach",                       # G23
            "Calibration identity is")                                           # G13

    def test_f5_and_calibration_present(self):
        self._has(
            "runs the eval harness and feeds you only artifact PATHS",           # F5
            "MUST NOT claim pass/fail from CODE INSPECTION alone",               # anti-pattern 5
            "auto-degrade autonomy to human_on_the_loop",                        # calibration degrade
            "auto-ships ONLY when AUTHORITATIVE")                                # authority split

    def test_refinement_halt_rule_present(self):
        self._has(
            "Insufficiency is NEVER an unbound read",
            "You do NOT fall back to reading")

    def test_six_gaps_each_have_supplemental_coverage(self):
        # Codex R6 non-blocking: strengthen the "six gaps are inlined" proof — assert the coverage
        # map's supplemental set carries a representative row for EACH of the six judge-instruction
        # gaps, so dropping a whole gap from the kernel projection fails the gate (not just `>0`).
        import yaml as _yaml
        cov = _yaml.safe_load(
            (REPO / "engine-kit" / "tools" / "constraint-inventory"
             / "_acceptance_kernel_coverage.yaml").read_text(encoding="utf-8"))
        sup = set(cov.get("supplemental_rows") or {})
        gaps = {
            "G7 symmetry": "rc-acc-symmetry-before-judging",
            "G18 verdict tree": "rc-acc-verdict-decision-tree",
            "G21 fix_required flow": "rc-acc-fixrequired-write-checkpoint",
            "G22 suggested_route": "rc-acc-suggested-route-fit-or-needs-human",
            "G23 needs_human": "rc-acc-needs-human-triggers",
            "G13 calibration drift": "rc-acc-calibration-identity-invalidation",
        }
        for label, rid in gaps.items():
            self.assertIn(rid, sup, msg=f"supplemental set missing representative row for {label}")


if __name__ == "__main__":
    unittest.main()
