#!/usr/bin/env python3
"""lesson_selection — WP-6 tier-aware, bounded Loop-Memory ingress selection.

The Loop-Memory substrate (memory_store.py) can accumulate an unbounded number of
lessons; the ingress channel (driver._lessons_block) injects EVERY scope-matched
active entry on EVERY spawn of a role, with no count or byte ceiling (the role
scope dimension matches across all modules/loops, so a long-lived project injects
thousands of tokens of singleton observations per spawn — see
archive/2026-06-28-wp6-lessons-tiering-decision.md §1.5).

This module bounds that channel WITHOUT losing any validated or constraint-bearing
lesson. It is a PURE, DETERMINISTIC function of the entries + a budget: no LLM, no
clock, no randomness, no dependence on prompt wording. Given identical inputs it
produces a byte-identical block and identical audit metadata.

TIERS (classify(); precedence first-match-wins; durable fields only):
  UNKNOWN   malformed / contradictory metadata        -> fail-safe: PRESERVED
  PROMOTED  promoted_to non-empty (folded into a       -> COMPACT reference
            test/validator/kernel/governance/contract)
  MATURED   maturity==L2 AND occurrences>=3            -> PRESERVED
  L2        maturity==L2 (occurrences 2 / human-flag)  -> PRESERVED
  L1        maturity==L1 AND occurrences==1 (singleton)-> the ONLY budgeted tier

SAFETY (the contract): only L1 may be dropped by a count/byte budget. L2 / MATURED
are removed ONLY by EXPLICIT supersession. PROMOTED is compacted, never dropped.
UNKNOWN fails safe (preserved, never treated as L1). Every suppression is recorded
(suppressed ids + reason + tier) AND noted in the block footer — never silent.

The only classification boundary that decides whether a lesson is DROPPED is
L1-vs-not-L1, so any ambiguity routes to a preserving tier and cannot lose a
lesson. The MATURED/L2 split is reporting only (both preserved).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

try:  # standalone-importable, like memory_store
    from memory_store import MemoryEntry, MATURITY_L1, MATURITY_L2, STATUS_ACTIVE
except ImportError:  # pragma: no cover - alternate import path
    from .memory_store import (  # type: ignore
        MemoryEntry, MATURITY_L1, MATURITY_L2, STATUS_ACTIVE,
    )


# --------------------------------------------------------------------------- #
# Contract constants                                                          #
# --------------------------------------------------------------------------- #

TIER_PROMOTED = "PROMOTED"
TIER_MATURED = "MATURED"
TIER_L2 = "L2"
TIER_L1 = "L1"
TIER_UNKNOWN = "UNKNOWN"

# Tiers that are NEVER dropped by a budget (only L1 is budgeted).
PRESERVED_TIERS = (TIER_PROMOTED, TIER_MATURED, TIER_L2, TIER_UNKNOWN)

# maturity==L2 promotes to MATURED at this many independent loop observations.
MATURED_MIN_OCCURRENCES = 3

# Suppression reasons (the auditable taxonomy).
REASON_SUPERSEDED = "superseded"
REASON_DUPLICATE = "duplicate"
REASON_L1_COUNT = "l1_count_budget"
REASON_L1_TOKEN = "l1_token_budget"
# Not a suppression — the representation reason recorded for a compacted PROMOTED
# entry (its full prose is replaced by the pointer, but the entry IS injected).
REASON_PROMOTED_COMPACT = "promoted_compact_reference"

# Selection-algorithm version (bumped if ordering/tiering semantics change), so the
# audit records which selection contract produced a block.
SELECTION_VERSION = "wp6.1"

# 4 bytes ≈ 1 token, consistent with load_sizer's static sizing.
_BYTES_PER_TOKEN = 4

# Block header — MUST match driver._lessons_block's legacy header verbatim so that
# an under-budget, no-suppression, no-promoted, no-dup store renders a BYTE-IDENTICAL
# block (preserving the WP-0 memory_bytes faithfulness invariant + existing tests).
_HEADER = [
    "## Relevant prior lessons (Loop Memory)",
    "(generalizable heuristics from earlier loops — not rules to "
    "memorize; apply judgement)",
]


def _tok(n_bytes: int) -> int:
    return n_bytes // _BYTES_PER_TOKEN


# --------------------------------------------------------------------------- #
# Budget                                                                      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LessonBudget:
    """Bound applied to the L1 (singleton) tier ONLY (the contract: only L1 may be
    constrained). ``max_l1_count`` caps how many L1 lessons inject; ``max_l1_bytes``
    caps their cumulative rendered bytes. A non-positive value disables that bound.
    Non-L1 tiers are never counted against, nor dropped by, this budget."""

    max_l1_count: int = 8
    max_l1_bytes: int = 4096


DEFAULT_BUDGET = LessonBudget()


# --------------------------------------------------------------------------- #
# Classification (pure)                                                        #
# --------------------------------------------------------------------------- #


def _well_formed(entry: MemoryEntry) -> bool:
    """Cheap structural sanity for safe classification. Anything off → UNKNOWN
    (fail-safe preserve), never silently treated as a disposable L1."""
    if not getattr(entry, "id", None):
        return False
    if entry.maturity not in (MATURITY_L1, MATURITY_L2):
        return False
    occ = entry.occurrences
    if not isinstance(occ, int) or isinstance(occ, bool) or occ < 1:
        return False
    if entry.status not in ("active", "superseded", "retired"):
        return False
    return True


def _has_promotion(entry: MemoryEntry) -> bool:
    refs = getattr(entry, "promoted_to", None) or []
    return any(isinstance(r, str) and r.strip() for r in refs)


def classify(entry: MemoryEntry) -> str:
    """Map a lesson to its tier (pure; durable fields only; precedence per module
    docstring). Fail-safe: malformed/contradictory → UNKNOWN (preserved)."""
    if not _well_formed(entry):
        return TIER_UNKNOWN
    if _has_promotion(entry):
        return TIER_PROMOTED
    if entry.maturity == MATURITY_L2:
        if entry.occurrences >= MATURED_MIN_OCCURRENCES:
            return TIER_MATURED
        return TIER_L2
    # maturity == L1
    if entry.occurrences == 1:
        return TIER_L1
    # L1 with occurrences>=2 is contradictory (legacy/corrupt) → fail-safe.
    return TIER_UNKNOWN


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #

# A PROMOTED compact reference caps its gloss so it is strictly a pointer, never
# re-injected full historical prose.
_PROMOTED_GLOSS_MAX = 80


def _first_body_line(entry: MemoryEntry) -> str:
    body = (entry.body or "").strip().splitlines()
    return body[0].strip() if body else ""


def _compact_refs(entry: MemoryEntry) -> str:
    refs = [r.strip() for r in (getattr(entry, "promoted_to", None) or [])
            if isinstance(r, str) and r.strip()]
    return ", ".join(refs)


def render_line(entry: MemoryEntry, representation: str) -> str:
    """One injected bullet. ``full`` = legacy ``- [<maturity>] <first body line>``
    (byte-identical to the pre-WP-6 render). ``compact`` (PROMOTED) = a pointer to
    the durable mechanism the lesson is encoded in, with a capped gloss."""
    if representation == "compact":
        gloss = _first_body_line(entry)
        if len(gloss) > _PROMOTED_GLOSS_MAX:
            gloss = gloss[:_PROMOTED_GLOSS_MAX].rstrip() + "…"
        refs = _compact_refs(entry)
        return f"- [PROMOTED] (encoded in: {refs}) {gloss}".rstrip()
    return f"- [{entry.maturity}] {_first_body_line(entry)}"


def _footer(suppressed_count: int) -> str:
    return (f"_(Loop Memory bounded: {suppressed_count} lower-priority prior "
            f"lesson(s) suppressed to limit context; full record in the spawn "
            f"audit suppressed_lesson_ids.)_")


def _render_block(bullets: List[str], suppressed_count: int) -> str:
    """Assemble header + bullets (+ a non-silent footer when anything was
    suppressed). Byte-identical to the legacy block when no suppression occurred.

    When EVERY candidate was suppressed (no bullets) but suppressions DID happen,
    emit a header + footer block anyway so suppression is never silent in-prompt
    (WP-6 NON-BLOCKING-1 fix). A truly empty candidate set renders ""."""
    if not bullets:
        if suppressed_count > 0:
            return "\n".join(list(_HEADER) + [_footer(suppressed_count)]) + "\n\n"
        return ""
    lines = list(_HEADER) + list(bullets)
    if suppressed_count > 0:
        lines.append(_footer(suppressed_count))
    return "\n".join(lines) + "\n\n"


# --------------------------------------------------------------------------- #
# Selection result                                                             #
# --------------------------------------------------------------------------- #


@dataclass
class LessonSelection:
    """The deterministic outcome of bounding the ingress block.

    ``block``          rendered injection text ("" when nothing selected).
    ``selected_ids``   ids actually injected (full or compact), in injection order.
    ``suppressed``     [{"id","reason","tier"}] for every dropped entry (det. order).
    ``tiers``          id -> tier for ALL candidates (selected + suppressed).
    ``representations``id -> "full"|"compact" for selected entries.
    ``bytes_before``   bytes of the UNBOUNDED legacy block (all candidates, full).
    ``bytes_after``    bytes of the bounded block.
    """

    block: str
    selected_ids: List[str]
    suppressed: List[Dict[str, str]]
    tiers: Dict[str, str]
    representations: Dict[str, str]
    bytes_before: int
    bytes_after: int
    version: str = SELECTION_VERSION

    @property
    def suppressed_ids(self) -> List[str]:
        return [s["id"] for s in self.suppressed]

    @property
    def tokens_before(self) -> int:
        return _tok(self.bytes_before)

    @property
    def tokens_after(self) -> int:
        return _tok(self.bytes_after)

    def audit_dict(self) -> Dict[str, Any]:
        """The spawn-audit ``lesson_selection`` object (json-serializable)."""
        return {
            "version": self.version,
            "selected": list(self.selected_ids),
            "suppressed": [dict(s) for s in self.suppressed],
            "tiers": dict(self.tiers),
            "representations": dict(self.representations),
            "bytes_before": self.bytes_before,
            "bytes_after": self.bytes_after,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
        }


# --------------------------------------------------------------------------- #
# The deterministic selection pass                                            #
# --------------------------------------------------------------------------- #


def select_for_injection(
    candidates: Sequence[MemoryEntry],
    *,
    superseded_ids: Optional[Set[str]] = None,
    budget: LessonBudget = DEFAULT_BUDGET,
) -> LessonSelection:
    """Bound the ingress block deterministically.

    ``candidates`` MUST already be scope-selected and in the store's canonical total
    order (MemoryStore.select: L2-before-L1, then -occurrences, then id). This single
    pass preserves that order for BOTH selection and rendering, so the agent-facing
    ordering is the existing one and an under-budget store renders byte-identically.

    ``superseded_ids`` = the global set of ids explicitly superseded by an active
    entry (MemoryStore.superseded_ids()); each is suppressed (reason ``superseded``)
    regardless of tier — the only sanctioned removal of an L2/MATURED lesson.

    Pass order per candidate: supersession → dedup → PROMOTED (compact, unbudgeted)
    → non-L1 (full, unbudgeted) → L1 (full, budgeted by count then bytes). Suppression
    is recorded, never silent.
    """
    superseded_ids = set(superseded_ids or set())

    selected_ids: List[str] = []
    bullets: List[str] = []
    suppressed: List[Dict[str, str]] = []
    tiers: Dict[str, str] = {}
    representations: Dict[str, str] = {}
    # Dedup keys on the EXACT line that WOULD be injected (representation included),
    # and only against lines ALREADY injected. Suppressing a byte-identical repeat of
    # an already-injected line is LOSSLESS for ANY tier (the agent's context is
    # unchanged), so dedup can never lose information — and a non-L1 / PROMOTED entry
    # whose rendered line merely SHARES a body string with an earlier entry (but
    # renders differently, e.g. an L2 vs a PROMOTED compact ref) is NOT a duplicate
    # and is kept (WP-6 BLOCKING-1 fix).
    seen_lines: set = set()

    l1_count = 0
    l1_bytes = 0

    # bytes_before = the pre-WP-6 unbounded block (every candidate, full render).
    before_bullets = [render_line(e, "full") for e in candidates]
    bytes_before = len(_render_block(before_bullets, 0).encode("utf-8"))

    def _suppress(entry: MemoryEntry, reason: str, tier: str) -> None:
        suppressed.append({"id": entry.id, "reason": reason, "tier": tier})

    def _inject(entry: MemoryEntry, representation: str, line: str) -> None:
        bullets.append(line)
        selected_ids.append(entry.id)
        representations[entry.id] = representation
        seen_lines.add(line)

    for entry in candidates:
        tier = classify(entry)
        tiers[entry.id] = tier

        # (0) Defensive: a non-active entry that slipped through is a supersession-
        # class removal (select() normally pre-filters these).
        if entry.status != STATUS_ACTIVE:
            _suppress(entry, REASON_SUPERSEDED, tier)
            continue

        # (1) Explicit supersession — removes ANY tier (the sanctioned path).
        if entry.id in superseded_ids:
            _suppress(entry, REASON_SUPERSEDED, tier)
            continue

        # Determine the representation + the EXACT line this entry would inject.
        representation = "compact" if tier == TIER_PROMOTED else "full"
        line = render_line(entry, representation)

        # (2) Dedup on the exact injected line (byte-identical → lossless redundancy,
        # safe for any tier; cross-tier same-body lines render differently → kept).
        if line in seen_lines:
            _suppress(entry, REASON_DUPLICATE, tier)
            continue

        # (3) PROMOTED → compact reference, never budgeted, never dropped.
        # (4) Other non-L1 preserved tiers (MATURED / L2 / UNKNOWN) → full, unbudgeted.
        if tier != TIER_L1:
            _inject(entry, representation, line)
            continue

        # (5) L1 singleton → the ONLY budgeted tier (count then bytes).
        line_bytes = len((line + "\n").encode("utf-8"))
        if budget.max_l1_count > 0 and l1_count >= budget.max_l1_count:
            _suppress(entry, REASON_L1_COUNT, tier)
            continue
        if budget.max_l1_bytes > 0 and (l1_bytes + line_bytes) > budget.max_l1_bytes:
            _suppress(entry, REASON_L1_TOKEN, tier)
            continue
        _inject(entry, "full", line)
        l1_count += 1
        l1_bytes += line_bytes

    block = _render_block(bullets, len(suppressed))
    bytes_after = len(block.encode("utf-8"))

    return LessonSelection(
        block=block,
        selected_ids=selected_ids,
        suppressed=suppressed,
        tiers=tiers,
        representations=representations,
        bytes_before=bytes_before,
        bytes_after=bytes_after,
    )
