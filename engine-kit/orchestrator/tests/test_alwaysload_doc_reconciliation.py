"""Deferred WP-3 follow-up — repository-wide always-load -> kernel-trio doc reconciliation gate.

After WP-2 (constitution-core) + WP-3 (authoring-kernel), the per-spawn cold-start always-load
set is the KERNEL TRIO -- ``governance/constitution-core.md`` + ``governance/authoring-kernel.md``
+ ``governance/context_briefing.md``. The full ``governance/constitution.md`` and
``governance/doc_governance.md`` are ON-DEMAND CANONICAL (the kernels carry the proactive
constraints at cold-start; the canonical wins on any disagreement and loads on-demand). Any
CURRENT, load-bearing, adopter-facing doc that still teaches the OLD model -- the FULL canonical
is "always-loaded" / "@-included" at cold-start -- is a latent canonical contradiction.

This gate scans EVERY tracked Markdown doc in the repo and FAILS if a line ASSERTS the full
canonical (``constitution.md`` / ``doc_governance.md``) is always-load / @-included WITHOUT
marking it on-demand. It is the regression backstop for the one-time reconciliation sweep.

The detector is deliberately precise (low false-positive). A line is a VIOLATION iff it is NOT
exempted AND matches one of two rules:
  * Rule A (assertion form): it carries an ALWAYS-LOAD / @-INCLUDE assertion token (EN or ZH) AND
    references the full canonical -- either by FILENAME (``constitution.md`` / ``doc_governance.md``,
    not a ``§`` section citation) or by the bare token ``constitution`` / ``doc_governance``.
  * Rule B (old-chain enumeration): it presents the obsolete governance CHAIN -- BOTH full
    canonicals (``constitution`` AND ``doc_governance``) named together in a cold-start / governance-
    chain / always-load context, with NEITHER kernel (``constitution-core`` / ``authoring-kernel``)
    named. This catches the "Governance chain (Constitution, doc_governance, context_briefing) ...
    cold-start" table/prose form, which carries no literal "always-load" lexeme so Rule A misses it.
    Requiring BOTH canonicals + a context token + no-kernel is what keeps it off cross-references
    ("source-of-truth lives in doc_governance.md ... cold-start discipline lives in context_briefing")
    and size-budget rows ("constitution highest; doc_governance + context_briefing ~20").
  * Rule C (glob chain): it calls the ``governance/*`` WILDCARD (which lumps the full canonicals in
    with the kernels) the role-session / cold-start / always-load chain. This catches the
    "framework governance chain (`aidazi/governance/*`) ... required role-session chain" form, where
    the canonical is referenced by glob rather than by name. A load-context token keeps it off plain
    enumerations of the directory ("All `governance/*` docs.").

Boundary (intentional, to bound false-positives): a SINGLE-canonical bare "cold-start" mention with
no always-load lexeme is treated as a cross-reference, not a load directive, and is NOT flagged here
(a blanket "constitution.md + cold-start" rule false-positives on cross-references and kernel self-
descriptions). The EXECUTABLE cold-start load regions -- role-card step-1, ``context_briefing.md``
§1.2 / §3, root ``AGENTS.md`` §2 -- are POSITIVELY asserted to name the kernel trio (canonical only
on-demand) by ``test_coldstart_consistency.py``; that is the precise backstop for a single-canonical
cold-start regression in a load-bearing region. This gate is the broad prose/enumeration/glob net.

ALLOWED (per the reconciliation contract; NOT violations) -- the four carve-outs the follow-up names:
  * canonical CITATIONS -- ``constitution.md §1.4`` (a section ref the kernel also carries): the
    ``(?! *§)`` lookahead exempts these (they are pointers, not bulk cold-start loads);
  * explicit ON-DEMAND triggers -- any line that says ``on-demand`` (EN) or ``按需`` (ZH);
  * HISTORICAL / FROZEN text -- ``archive/**`` (frozen history) and ``compact/**`` (frozen,
    dated, doc_category:intermediate handoff context-packs that DESCRIBE the old state);
  * SOURCE-OF-TRUTH / self-projection declarations -- the always-load KERNEL files
    (``constitution-core.md``, ``authoring-kernel.md``) legitimately describe THEMSELVES as
    always-load and name the canonical in their ``derived_from`` / ``source_of_truth`` contract;
    bare-token matches inside those two files are exempt (a FILENAME assertion without on-demand is
    still caught even there, so a regression "constitution.md is always-load" cannot hide).

Scope boundary (documented limitation): the detector keys on the canonical NAME. Purely
self-referential prose ("this document is always-loaded") with no canonical name is reconciled by
the one-time sweep and guarded positively by the cold-start structural checks in
``test_coldstart_consistency.py`` (which assert the executable cold-start regions name the kernel
trio). A line that says always-load of one doc and on-demand of another on the SAME line is
exempted (line-level ``on-demand`` carve-out) -- acceptable because the precise cold-start
instructions are covered by the structural gate; this gate is the broad prose backstop.
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

# Frozen / historical trees: not current docs -- never rewritten (the follow-up's allow-list).
_SKIP_DIRS = {".git", "archive", ".specstory", ".runs", "node_modules", "__pycache__", "compact"}
# The always-load projection kernels: they legitimately self-describe as always-load and carry the
# source-hash-gated derived_from / source_of_truth contract that names the canonical by token.
_KERNEL_SELF_PROJECTION = {"governance/constitution-core.md", "governance/authoring-kernel.md"}

# Always-load / @-include ASSERTION tokens (English + the adopter-facing zh-CN README's phrasings).
_ASSERT_EN = ("always-load", "always loaded", "always load", "@-includ", "@includ")
_ASSERT_ZH = ("始终加载", "总是加载", "常驻加载")
# Rule B context tokens: a cold-start / governance-chain LOAD context (superset of the assertion
# tokens; the broader "cold-start" / "governance chain" forms are safe ONLY under Rule B's
# both-canonicals + no-kernel guard, which keeps them off cross-references and size-budget rows).
_CHAIN_CTX_EN = _ASSERT_EN + ("cold-start", "cold start", "governance chain",
                              "role-session chain", "role session chain")
_CHAIN_CTX_ZH = _ASSERT_ZH + ("冷启动", "治理链")
# Full canonical referenced as a LOAD (not a "<file>.md §X" section CITATION -- the lookahead exempts
# citations). "constitution.md" is NOT a substring of "constitution-core.md", so the kernel filename
# never trips this.
_CANON_FILE = re.compile(r"(?:constitution|doc_governance)\.md(?! *§)", re.IGNORECASE)
# Bare canonical token; (?!-core) keeps "constitution-core" (the kernel) from matching "constitution".
# Case-insensitive so a "The Constitution is always-loaded" regression cannot hide behind a capital C.
_CANON_BARE = re.compile(r"\bconstitution(?!-core)|\bdoc_governance\b", re.IGNORECASE)
# Rule B parts: the two full canonicals (bare) and the kernels (whose presence => the NEW model).
_CONST_BARE = re.compile(r"\bconstitution(?!-core)", re.IGNORECASE)
_DOCG_BARE = re.compile(r"\bdoc_governance\b", re.IGNORECASE)
_KERNEL_NAMED = re.compile(r"constitution-core|authoring-kernel", re.IGNORECASE)
# Rule C: the governance/* WILDCARD (lumps the full canonicals in with the kernels).
_GOV_GLOB = re.compile(r"governance/\*")


def alwaysload_violation_kind(rel_path: str, line: str):
    """Return 'FILENAME' / 'bare' if ``line`` teaches the obsolete always-load-canonical model,
    else None. ``rel_path`` is the repo-relative POSIX path (used only for the kernel carve-out)."""
    low = line.lower()
    if "on-demand" in low or "按需" in line:  # explicit on-demand trigger -> allowed (both rules)
        return None
    # Rule A -- always-load / @-include assertion + a full-canonical reference.
    if any(t in low for t in _ASSERT_EN) or any(t in line for t in _ASSERT_ZH):
        if _CANON_FILE.search(line):  # named full canonical as a load -> caught even inside kernels
            return "FILENAME"
        if _CANON_BARE.search(line) and rel_path not in _KERNEL_SELF_PROJECTION:
            return "bare"
    # Rule B -- obsolete chain enumeration: BOTH full canonicals in a cold-start/chain context with
    # NEITHER kernel named (a kernel on the line => the corrected model, so it is not a violation).
    if (_CONST_BARE.search(line) and _DOCG_BARE.search(line)
            and not _KERNEL_NAMED.search(line)
            and (any(t in low for t in _CHAIN_CTX_EN) or any(t in line for t in _CHAIN_CTX_ZH))):
        return "old-chain"
    # Rule C -- the governance/* glob called the role-session / cold-start / always-load chain.
    if (_GOV_GLOB.search(line)
            and (any(t in low for t in _CHAIN_CTX_EN) or any(t in line for t in _CHAIN_CTX_ZH))):
        return "glob-chain"
    return None


def _iter_markdown(repo):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, f), repo).replace(os.sep, "/")
                yield rel, os.path.join(root, f)


class AlwaysLoadDocReconciliationTests(unittest.TestCase):
    def test_no_current_doc_teaches_full_canonical_as_always_load(self):
        offenders = []
        for rel, abspath in _iter_markdown(REPO):
            with open(abspath, encoding="utf-8") as fh:
                for n, line in enumerate(fh.read().splitlines(), 1):
                    kind = alwaysload_violation_kind(rel, line)
                    if kind:
                        offenders.append(f"{rel}:{n}: [{kind}] {line.strip()}")
        self.assertEqual(
            offenders, [],
            "current/load-bearing docs still teach the obsolete model (the full canonical "
            "constitution.md / doc_governance.md is always-load / @-included at cold-start). "
            "Use the kernel trio; name the full canonical only as on-demand:\n" + "\n".join(offenders))

    # ---- non-vacuity: the detector MUST flag the obsolete model and MUST allow the four carve-outs ----
    def test_detector_flags_obsolete_model_lines(self):
        bad = [
            "- `governance/constitution.md` — the always-loaded core.",          # filename + always-load
            "1. Load governance/doc_governance.md at cold-start (always-load).",  # filename, numbered
            "- **A Constitution** — this file; forbidden list. Always loaded.",   # bare + always loaded
            "The constitution is inherited via @-include from AGENTS.md.",        # bare + @-include
            "4. `governance/constitution.md` —— 始终加载的核心。",                # filename + zh always-load
            # Rule B: obsolete chain enumeration (no "always-load" lexeme; both canonicals, no kernel)
            "| Governance chain (Constitution, doc_governance, context_briefing) | — | role-session cold-start |",
            # Rule C: the governance/* glob called the required role-session chain
            "The framework governance chain (`aidazi/governance/*`) remains the required role-session chain.",
        ]
        for line in bad:
            self.assertIsNotNone(alwaysload_violation_kind("docs/x.md", line),
                                 f"detector failed to flag an obsolete-model line: {line!r}")

    def test_detector_allows_reconciled_and_carveout_lines(self):
        ok = [
            # on-demand carve-out (EN + ZH)
            "constitution-core.md (always-load); full constitution.md loads on-demand.",
            "始终加载内核;完整规范 constitution.md 按需加载。",
            # canonical CITATION carve-out (section ref, not a bulk load)
            "Boundary invariants live in `governance/constitution.md` §3.4 (always referenced).",
            # kernel SELF-PROJECTION carve-out: bare token + always-load inside the kernel file
            ("governance/constitution-core.md",
             "title: aidazi Constitution — Core (always-load derived projection)"),
            # legitimate current usage: kernel trio / adopter-side ledger named always-load (no canonical)
            "explicit role sessions load the always-load governance kernel trio and their role card.",
            "| `docs/action_bank.md` | Deliver Agent | always-load | per sprint close |",
            # Rule B must NOT fire on a cold-start CROSS-REFERENCE (only one canonical as a set member)
            "Source-of-truth lives in `doc_governance.md`. Cold-start discipline lives in context_briefing.",
            # Rule B must NOT fire on a SIZE-BUDGET row (both canonicals named, but not a load context)
            "| `governance/` | 20-60 KB; constitution highest; doc_governance + context_briefing ~20 |",
            # Rule B must NOT fire when a kernel IS named (the corrected chain) even at cold-start
            "Cold-start chain: constitution-core + authoring-kernel + context_briefing (constitution/doc_governance later).",
            # Rule C must NOT fire on a plain directory enumeration (no load-context token)
            "- All `governance/*` docs.",
        ]
        for item in ok:
            rel, line = item if isinstance(item, tuple) else ("docs/x.md", item)
            self.assertIsNone(alwaysload_violation_kind(rel, line),
                              f"detector wrongly flagged an allowed line: {line!r}")

    def test_kernel_filename_assertion_caught_even_inside_kernel(self):
        # The kernel self-projection carve-out is bare-token ONLY: a FILENAME assertion of the full
        # canonical as always-load (without on-demand) must still be caught inside a kernel file, so
        # a regression "constitution.md is always-load" cannot hide behind the carve-out.
        self.assertEqual(
            alwaysload_violation_kind(
                "governance/constitution-core.md",
                "the full constitution.md is always-load at cold-start"),
            "FILENAME")


if __name__ == "__main__":
    unittest.main()
