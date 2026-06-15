#!/usr/bin/env python3
"""memory_store — Loop Memory substrate over a directory of md files (plan §4.4).

Implements the Loop Memory from the v2 plan (archive
2026-06-15-v2-loop-engine-plan.md §4.4): cross-loop institutional experience
persisted as **md files** — read at ingress, written at close — that powers
self-evolution. It is NOT a third loop and NOT a storage service: storage is
just files. A MemoryStore owns one directory:

    <root>/
      index.md            ← regenerated deterministically; loaded at ingress
      entries/<id>.md      ← one entry per file: YAML front-matter + md body

Each entry's front-matter conforms to schemas/memory-entry.schema.json
(``type: failure|heuristic|pattern|calibration-note|detour``,
``scope:{module/role/layer}``, ``maturity:L1|L2``, ``occurrences``, ``status``,
``source_loops``, ``[[links]]``). Selection (ingress) is a deterministic
tag/scope match (module/role); no LLM, no clock, no randomness in this core.

LIFECYCLE (plan §4.4):
    ingress  →  select(scope)            inject relevant L*-entries per role
    during   →  (driver captures L1 candidates)
    close    →  write_entry / record_observation
                record_observation dedups by a stable ``key``: if an entry with
                that key exists, bump ``occurrences`` + append the new
                ``source_loop`` (no duplicate file); maturity promotes
                **L1 → L2 when occurrences ≥ 2 OR human-flagged** (Δ-9 OBS
                triage L1/L2 — m-autoloop.md §5).

DETERMINISM / TESTABILITY: ``ts`` (date string) and ``loop_id`` are INJECTED by
the caller on every mutating call. This core never reads the wall clock, never
generates uuids, never calls random. The entry ``id`` is caller-supplied (or
derived deterministically from a caller-supplied ``key``). The index and
selection both use a stable total order, so identical inputs always produce
byte-identical output.

ANTI-GAMING GUARD (HARD — Constitution §1.7 / plan §4.4 / m-autoloop.md §3):
    Loop Memory stores GENERALIZABLE heuristics, NOT case-specific input→output
    encodings (that is the "encoding raw eval phrases" forbidden item). Every
    write runs ``guard_entry`` which REJECTS an entry that looks like an
    input→output memorization (a forbidden-style check). Storing such an entry
    would let the agent "pass" by recall instead of by generalizing — exactly
    the gaming m-autoloop.md §3 / §4 exist to prevent. The guard is intentionally
    simple but always-on; it raises ``AntiGamingViolation`` and the write fails.

This module is STANDALONE: it is not yet wired into the driver. The future
integration step calls ``select(scope)`` at ingress and ``record_observation`` /
``write_entry`` at close.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only when dep missing
    raise SystemExit(
        "memory_store: pyyaml is required (pip install pyyaml jsonschema)\n"
    )


# --------------------------------------------------------------------------- #
# Constants / contract                                                        #
# --------------------------------------------------------------------------- #

ENTRY_TYPES = ("failure", "heuristic", "pattern", "calibration-note", "detour")
MATURITY_L1 = "L1"
MATURITY_L2 = "L2"
STATUS_ACTIVE = "active"

# Front-matter is delimited by a leading and a trailing "---" line.
_FM_DELIM = "---"

# Order in which front-matter keys are serialized, so files are byte-stable.
# Keys not listed are appended afterwards in sorted order.
_FM_KEY_ORDER = (
    "id",
    "type",
    "scope",
    "maturity",
    "occurrences",
    "status",
    "provider",
    "model",
    "source_loops",
    "links",
    "created",
    "last_reviewed",
)


class MemoryError(Exception):
    """Base error for the memory store."""


class AntiGamingViolation(MemoryError):
    """An entry was rejected by the anti-gaming guard (§1.7 forbidden item).

    Raised when an entry looks like a case-specific input→output encoding rather
    than a generalizable heuristic. The write is refused.
    """


# --------------------------------------------------------------------------- #
# Entry model                                                                 #
# --------------------------------------------------------------------------- #


@dataclass
class MemoryEntry:
    """One Loop Memory entry: front-matter fields + a markdown body.

    ``key`` is the in-memory dedup handle used by ``record_observation`` — it is
    NOT serialized into the front-matter (the schema forbids unknown keys); it is
    recovered from the on-disk ``id`` (which equals ``slug(key)`` for keyed
    entries). ``human_flagged`` is likewise a runtime promotion signal, not
    persisted, consumed only by the maturity rule.
    """

    id: str
    type: str
    scope: Dict[str, List[str]]
    maturity: str = MATURITY_L1
    occurrences: int = 1
    status: str = STATUS_ACTIVE
    provider: Optional[str] = None
    model: Optional[str] = None
    source_loops: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    created: Optional[str] = None
    last_reviewed: Optional[str] = None
    body: str = ""
    # Runtime-only (never serialized to front-matter):
    key: Optional[str] = None
    human_flagged: bool = False

    def front_matter(self) -> Dict[str, Any]:
        """The schema-validatable front-matter dict (runtime-only fields dropped)."""
        fm: Dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "scope": _clean_scope(self.scope),
            "maturity": self.maturity,
            "occurrences": self.occurrences,
            "status": self.status,
        }
        if self.provider is not None:
            fm["provider"] = self.provider
        if self.model is not None:
            fm["model"] = self.model
        if self.source_loops:
            fm["source_loops"] = list(self.source_loops)
        if self.links:
            fm["links"] = list(self.links)
        if self.created is not None:
            fm["created"] = self.created
        if self.last_reviewed is not None:
            fm["last_reviewed"] = self.last_reviewed
        return fm


def _clean_scope(scope: Dict[str, Any]) -> Dict[str, Any]:
    """Drop empty scope arrays so the schema's minProperties:1 stays meaningful."""
    out: Dict[str, Any] = {}
    for k in ("module", "role", "layer"):
        v = scope.get(k)
        if v:
            out[k] = list(v)
    return out


# --------------------------------------------------------------------------- #
# Anti-gaming guard                                                           #
# --------------------------------------------------------------------------- #

# Phrases that betray a case-specific input→output memorization rather than a
# generalizable heuristic. This is the operational expression of Constitution
# §1.7's "encoding raw eval phrases" forbidden item (plan §4.4 HARD;
# m-autoloop.md §3 anti-gaming list / §4 reward-signal discipline). The list is
# deliberately small + documented; it is the GUARD HOOK the spec calls for —
# additions are framework-level (route via fold-back), not silent.
_FORBIDDEN_PATTERNS: Tuple[re.Pattern, ...] = (
    # explicit "when input X, answer/output Y" encodings
    re.compile(r"\bwhen\s+(?:the\s+)?input\b.*\b(?:output|answer|respond|return)\b", re.I | re.S),
    re.compile(r"\bif\s+(?:the\s+)?(?:prompt|input|question)\b.*\b(?:then\s+)?(?:output|answer|reply|return)\b", re.I | re.S),
    # literal eval-phrase / expected-answer memorization
    re.compile(r"\bmemoriz(?:e|ed|ing)\b", re.I),
    re.compile(r"\bexpected[\s_-]?(?:answer|output)\b\s*[:=]", re.I),
    re.compile(r"\beval[\s_-]?phrase\b", re.I),
    re.compile(r"\bhard[\s_-]?code\b.*\b(?:answer|output|response|case)\b", re.I | re.S),
    # explicit input→output arrow mapping (e.g. "input -> output")
    re.compile(r"\binput\b\s*(?:->|=>|→)\s*\b(?:output|answer)\b", re.I),
    # ---- natural-language case→answer encodings (P3 review: lexical-only guard
    #      missed these verified bypasses; broaden WITHOUT over-rejecting role /
    #      heuristic guidance — every pattern is anchored on a QUOTED literal,
    #      an explicit case index, or a verbatim/answer-key cue) ---------------- #
    # "when the user says/asks '…', respond/say/reply/answer '…'": a quoted
    #   stimulus mapped to a quoted canned reply. Requires BOTH the user-utterance
    #   verb and a response verb so generic "when X, prefer Y" heuristics pass.
    re.compile(
        r"\bwhen\s+(?:the\s+)?(?:user|customer|prompt|question)\b"
        r".{0,80}?\b(?:say|says|ask|asks|asked)\b"
        r".*?\b(?:respond|reply|say|answer|return|output)\b\s*(?:with\s+)?['\"]",
        re.I | re.S,
    ),
    # "the answer for/to … is '…'" / "the correct answer is '…'": an answer-key
    #   assertion. Anchored on answer(+optional correct/right) + a quoted value.
    re.compile(
        r"\b(?:the\s+)?(?:correct\s+|right\s+|expected\s+|gold\s+)?answer\b"
        r"\s+(?:for|to|is|=|:)\b.*?['\"]",
        re.I | re.S,
    ),
    # "for the question '…' the correct answer is '…'": quoted-question →
    #   (correct/right/expected/gold) answer.
    re.compile(
        r"\bfor\s+(?:the\s+)?(?:question|case|prompt|input)\b\s*['\"].*?"
        r"\b(?:correct|right|expected|gold)\s+(?:answer|output|response)\b",
        re.I | re.S,
    ),
    # "test case N expects …" / "case N expects …" / "test N expects …": a
    #   numbered/identified eval case mapped to an expected value.
    re.compile(
        r"\b(?:test\s+)?case[\s_-]*\w*\d\w*\b.*?\bexpect(?:s|ed)?\b",
        re.I | re.S,
    ),
    re.compile(r"\btest[\s_-]*\d+\b.*?\bexpect(?:s|ed)?\b", re.I | re.S),
    # "respond with R verbatim" / "say/reply/output … verbatim" / "… verbatim to
    #   pass": reciting a canned string word-for-word is memorization, not a
    #   generalizable rule.
    re.compile(
        r"\b(?:respond|reply|say|answer|output|return|repeat)\b.*?\bverbatim\b",
        re.I | re.S,
    ),
    re.compile(r"\bverbatim\b.*?\bto\s+pass\b", re.I | re.S),
    # "case_X -> 'value'" / "case N -> 'value'" / "<case> -> '<value>'": an
    #   arrow-mapping from a case token to a quoted literal value.
    re.compile(
        r"\bcase[\s_-]*\w*\b\s*(?:->|=>|→|:)\s*['\"]",
        re.I,
    ),
    # "remember: <case> -> '<value>'" / "remember that case … is '…'": an
    #   explicit instruction to memorize a specific case→value mapping.
    re.compile(
        r"\bremember\b\s*[:,]?\s*.*?\bcase\b.*?(?:->|=>|→|\bis\b|:).*?['\"]",
        re.I | re.S,
    ),
)


def guard_entry(entry: MemoryEntry) -> None:
    """Reject an entry that looks like a case-specific input→output encoding.

    Anti-gaming guard hook (HARD). Inspects the body + the front-matter text for
    forbidden input→output memorization patterns. Raises ``AntiGamingViolation``
    on a hit; returns ``None`` if the entry reads as a generalizable heuristic.

    Constraint (documented, also enforced): an entry's body MUST describe a
    GENERALIZABLE lesson ("under condition C, prefer approach A because R") — NOT
    a lookup table from a specific input to its expected output. The latter lets
    the agent pass an eval by recall instead of by problem-solving, which is the
    §1.7 forbidden item and the m-autoloop.md §3/§4 gaming pattern.
    """
    haystack = "\n".join(
        [
            entry.body or "",
            str(entry.scope),
            " ".join(entry.links or []),
        ]
    )
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(haystack):
            raise AntiGamingViolation(
                "entry rejected: body looks like a case-specific input→output "
                "encoding (Constitution §1.7 forbidden item; plan §4.4). Store a "
                "GENERALIZABLE heuristic, not a memorized answer. matched "
                f"pattern: {pat.pattern!r}"
            )


# --------------------------------------------------------------------------- #
# Front-matter (de)serialization                                              #
# --------------------------------------------------------------------------- #


def _ordered_fm(fm: Dict[str, Any]) -> Dict[str, Any]:
    """Return fm with keys in the stable serialization order."""
    ordered: Dict[str, Any] = {}
    for k in _FM_KEY_ORDER:
        if k in fm:
            ordered[k] = fm[k]
    for k in sorted(fm):
        if k not in ordered:
            ordered[k] = fm[k]
    return ordered


def render_entry(entry: MemoryEntry) -> str:
    """Serialize an entry to its on-disk md text (front-matter + body).

    Deterministic: ``yaml.safe_dump`` with ``sort_keys=False`` over a pre-ordered
    dict, so the output is byte-stable for a given entry.
    """
    fm = _ordered_fm(entry.front_matter())
    buf = io.StringIO()
    buf.write(_FM_DELIM + "\n")
    yaml.safe_dump(fm, buf, sort_keys=False, default_flow_style=False, allow_unicode=True)
    buf.write(_FM_DELIM + "\n")
    body = entry.body or ""
    if body and not body.startswith("\n"):
        buf.write("\n")
    buf.write(body)
    if body and not body.endswith("\n"):
        buf.write("\n")
    return buf.getvalue()


def parse_entry(text: str) -> MemoryEntry:
    """Parse on-disk md text back into a MemoryEntry (front-matter + body)."""
    if not text.startswith(_FM_DELIM):
        raise MemoryError("entry has no leading front-matter delimiter")
    # Split: "---\n<fm>\n---\n<body>"
    rest = text[len(_FM_DELIM):].lstrip("\n")
    end = rest.find("\n" + _FM_DELIM)
    if end == -1:
        raise MemoryError("entry has no closing front-matter delimiter")
    fm_text = rest[:end]
    body = rest[end + len("\n" + _FM_DELIM):]
    body = body.lstrip("\n")
    fm = yaml.safe_load(fm_text) or {}
    scope = fm.get("scope") or {}
    entry = MemoryEntry(
        id=fm["id"],
        type=fm["type"],
        scope={k: list(v) for k, v in scope.items()},
        maturity=fm.get("maturity", MATURITY_L1),
        occurrences=int(fm.get("occurrences", 1)),
        status=fm.get("status", STATUS_ACTIVE),
        provider=fm.get("provider"),
        model=fm.get("model"),
        source_loops=list(fm.get("source_loops", [])),
        links=list(fm.get("links", [])),
        created=fm.get("created"),
        last_reviewed=fm.get("last_reviewed"),
        body=body,
        key=fm["id"],  # on-disk id is the dedup handle for keyed entries
    )
    return entry


# --------------------------------------------------------------------------- #
# id / slug helpers (deterministic — no uuid)                                 #
# --------------------------------------------------------------------------- #

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(key: str) -> str:
    """Deterministically derive a filesystem-safe entry id from a stable key.

    No randomness, no uuid: ``slug("research: stale brief")`` is always
    ``"research-stale-brief"``. This is what makes ``record_observation`` able to
    find the same entry across loops from the same ``key``.
    """
    s = _SLUG_RE.sub("-", key.strip().lower()).strip("-")
    return s or "entry"


# --------------------------------------------------------------------------- #
# MemoryStore                                                                 #
# --------------------------------------------------------------------------- #


class MemoryStore:
    """A Loop Memory store over a directory of md files (plan §4.4).

    Construct with the store root directory. ``entries/`` holds one md file per
    entry; ``index.md`` is regenerated deterministically on every mutation and is
    what the driver loads at ingress.
    """

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.entries_dir = os.path.join(self.root, "entries")
        self.index_path = os.path.join(self.root, "index.md")
        os.makedirs(self.entries_dir, exist_ok=True)

    # -- paths ------------------------------------------------------------- #

    def _entry_path(self, entry_id: str) -> str:
        return os.path.join(self.entries_dir, f"{entry_id}.md")

    # -- read -------------------------------------------------------------- #

    def load_all(self) -> List[MemoryEntry]:
        """Load every entry, sorted by id (stable total order)."""
        out: List[MemoryEntry] = []
        if not os.path.isdir(self.entries_dir):
            return out
        for name in sorted(os.listdir(self.entries_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(self.entries_dir, name)
            with open(path, "r", encoding="utf-8") as fh:
                out.append(parse_entry(fh.read()))
        out.sort(key=lambda e: e.id)
        return out

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Load a single entry by id, or None if it does not exist."""
        path = self._entry_path(entry_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return parse_entry(fh.read())

    def load_index(self) -> str:
        """Return the rendered ``index.md`` text (the ingress-loaded artifact)."""
        if not os.path.exists(self.index_path):
            return self._render_index([])
        with open(self.index_path, "r", encoding="utf-8") as fh:
            return fh.read()

    # -- write ------------------------------------------------------------- #

    def write_entry(self, entry: MemoryEntry, *, ts: str, loop_id: str) -> MemoryEntry:
        """Create a new entry on disk (close-time).

        Injects ``ts`` (date string) as ``created`` / ``last_reviewed`` when the
        entry does not already carry them, and threads ``loop_id`` into
        ``source_loops``. Runs the anti-gaming guard BEFORE writing — a rejected
        entry never touches the disk. Regenerates ``index.md``.

        Raises ``MemoryError`` if an entry with the same id already exists (use
        ``record_observation`` to dedup/bump an existing one).
        """
        entry = self._validate_shape(entry)
        path = self._entry_path(entry.id)
        if os.path.exists(path):
            raise MemoryError(
                f"entry {entry.id!r} already exists; use record_observation to bump it"
            )

        if loop_id and loop_id not in entry.source_loops:
            entry = replace(entry, source_loops=[*entry.source_loops, loop_id])
        if entry.created is None:
            entry = replace(entry, created=ts)
        if entry.last_reviewed is None:
            entry = replace(entry, last_reviewed=ts)

        guard_entry(entry)  # HARD anti-gaming gate — may raise AntiGamingViolation

        self._atomic_write(path, render_entry(entry))
        self._regenerate_index()
        return entry

    def record_observation(
        self,
        key: str,
        *,
        ts: str,
        loop_id: str,
        type: str = "heuristic",
        scope: Optional[Dict[str, List[str]]] = None,
        body: str = "",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        links: Optional[Sequence[str]] = None,
        human_flagged: bool = False,
    ) -> MemoryEntry:
        """Record an observation, deduplicating by ``key`` (close-time).

        The entry id is ``slug(key)``. If no entry with that id exists, create an
        L1 candidate (occurrences=1). If it exists, this is a REPEAT observation
        of the same lesson: bump ``occurrences`` and append ``loop_id`` to
        ``source_loops`` — WITHOUT creating a duplicate file. Maturity promotes
        **L1 → L2 when occurrences ≥ 2 OR ``human_flagged``** (Δ-9 OBS triage;
        m-autoloop.md §5). Anti-gaming guard runs on the resulting entry.

        Returns the resulting (created-or-updated) entry.
        """
        entry_id = slug(key)
        existing = self.get(entry_id)

        if existing is None:
            entry = MemoryEntry(
                id=entry_id,
                type=type,
                scope=scope or {},
                maturity=MATURITY_L1,
                occurrences=1,
                status=STATUS_ACTIVE,
                provider=provider,
                model=model,
                source_loops=[loop_id] if loop_id else [],
                links=list(links or []),
                created=ts,
                last_reviewed=ts,
                body=body,
                key=key,
                human_flagged=human_flagged,
            )
            entry = self._validate_shape(entry)
            entry = self._apply_maturity(entry)
            guard_entry(entry)
            self._atomic_write(self._entry_path(entry.id), render_entry(entry))
            self._regenerate_index()
            return entry

        # Repeat observation → bump, dedup source_loops, refresh last_reviewed.
        occurrences = existing.occurrences + 1
        source_loops = list(existing.source_loops)
        if loop_id and loop_id not in source_loops:
            source_loops.append(loop_id)
        updated = replace(
            existing,
            occurrences=occurrences,
            source_loops=source_loops,
            last_reviewed=ts,
            human_flagged=existing.human_flagged or human_flagged,
        )
        updated = self._apply_maturity(updated)
        guard_entry(updated)
        self._atomic_write(self._entry_path(updated.id), render_entry(updated))
        self._regenerate_index()
        return updated

    # -- selection (ingress) ---------------------------------------------- #

    def select(self, scope: Dict[str, Sequence[str]]) -> List[MemoryEntry]:
        """Return active entries whose scope matches ``scope`` (ingress).

        Deterministic tag/scope match: an entry matches when, for at least one
        scope dimension present in BOTH the query and the entry, the query value
        set and the entry value set intersect (module/role/layer). Retired and
        superseded entries are excluded. Results are sorted by a stable total
        order: maturity (L2 before L1), then descending occurrences, then id —
        so the most-confirmed, most-recurrent lessons inject first, and ties
        break on id for byte-stability. No LLM, no clock.
        """
        wanted = {k: set(v) for k, v in scope.items() if v}
        out: List[MemoryEntry] = []
        for entry in self.load_all():
            if entry.status != STATUS_ACTIVE:
                continue
            if self._scope_matches(entry.scope, wanted):
                out.append(entry)
        out.sort(key=lambda e: (0 if e.maturity == MATURITY_L2 else 1, -e.occurrences, e.id))
        return out

    @staticmethod
    def _scope_matches(entry_scope: Dict[str, List[str]], wanted: Dict[str, set]) -> bool:
        if not wanted:
            return True
        for dim, want_set in wanted.items():
            have = set(entry_scope.get(dim, []))
            if have & want_set:
                return True
        return False

    # -- internals --------------------------------------------------------- #

    @staticmethod
    def _apply_maturity(entry: MemoryEntry) -> MemoryEntry:
        """Promote L1 → L2 when occurrences ≥ 2 OR human-flagged (never demote)."""
        if entry.maturity == MATURITY_L2:
            return entry
        if entry.occurrences >= 2 or entry.human_flagged:
            return replace(entry, maturity=MATURITY_L2)
        return entry

    @staticmethod
    def _validate_shape(entry: MemoryEntry) -> MemoryEntry:
        """Cheap structural checks mirroring the schema's required/enum fields.

        Full JSON-Schema validation against schemas/memory-entry.schema.json is
        the test's job (and the future validator's); this keeps the core honest
        without importing jsonschema as a hard runtime dep.
        """
        if not entry.id:
            raise MemoryError("entry.id is required")
        if entry.type not in ENTRY_TYPES:
            raise MemoryError(f"entry.type {entry.type!r} not in {ENTRY_TYPES}")
        if entry.maturity not in (MATURITY_L1, MATURITY_L2):
            raise MemoryError(f"entry.maturity {entry.maturity!r} invalid")
        if entry.occurrences < 1:
            raise MemoryError("entry.occurrences must be >= 1")
        if not _clean_scope(entry.scope):
            raise MemoryError("entry.scope must name at least one of module/role/layer")
        if entry.type == "calibration-note" and not (entry.provider and entry.model):
            raise MemoryError(
                "calibration-note MUST be tagged by (provider, model) (plan §4.4 / §3.6)"
            )
        return entry

    @staticmethod
    def _atomic_write(path: str, text: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)

    def _regenerate_index(self) -> None:
        self._atomic_write(self.index_path, self._render_index(self.load_all()))

    @staticmethod
    def _render_index(entries: List[MemoryEntry]) -> str:
        """Render a deterministic index.md listing all entries (sorted by id)."""
        lines: List[str] = []
        lines.append("# Loop Memory index")
        lines.append("")
        lines.append(
            "Cross-loop experience (plan §4.4). Loaded at ingress; regenerated "
            "deterministically at close. Storage is just md files."
        )
        lines.append("")
        lines.append(f"entries: {len(entries)}")
        lines.append("")
        lines.append("| id | type | maturity | occ | status | scope |")
        lines.append("|---|---|---|---|---|---|")
        for e in sorted(entries, key=lambda x: x.id):
            scope_bits = []
            for dim in ("module", "role", "layer"):
                vals = e.scope.get(dim)
                if vals:
                    scope_bits.append(f"{dim}={'/'.join(vals)}")
            scope_repr = "; ".join(scope_bits)
            lines.append(
                f"| [[{e.id}]] | {e.type} | {e.maturity} | {e.occurrences} | "
                f"{e.status} | {scope_repr} |"
            )
        lines.append("")
        return "\n".join(lines)
