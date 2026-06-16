#!/usr/bin/env python3
"""feedback — Loop Memory self-evolution feedback engine (plan §4.4; m-memory §5).

The Loop Memory SUBSTRATE (engine-kit/memory/memory_store.py) persists cross-loop
lessons and matures them L1→L2. This module is the FEEDBACK stage that runs AFTER
close: it reads the matured (L2) entries and emits structured PROPOSALS for the
four load-bearing self-evolution paths the spec defines (m-memory.md §5):

    | # | path                | what it proposes                          | gate          |
    |---|---------------------|-------------------------------------------|---------------|
    | 2 | skill_edit          | edit a vendored skill bound to a role     | human_approval|
    | 3 | charter_tuning      | tune a charter default (e.g. calibration) | human_approval|
    | 4 | autoloop_candidate  | a Type-A Auto Loop experiment input (Δ-9) | human_approval|
    | 5 | fold_back           | a framework-level lesson → fold-back       | fold_back     |

(Path 1 — "role context" — is the only auto/safe path and is already handled at
INGRESS by the driver injecting lessons into role prompts; it is NOT a load-
bearing change, so it is not part of this engine. m-memory §5.)

HARD INVARIANTS (these are the point; violating one is a bug — m-memory §1.2/§5,
Constitution §1.7-D):

  * PROPOSE-ONLY. This engine NEVER edits a skill, charter, prompt, or any file,
    and never mutates the store. ``propose`` is a pure read; ``render_report``
    returns text. Every proposal carries an explicit human ``gate``. "Memory
    informs; it does not decide."
  * L2-ONLY for load-bearing paths. Only matured (``maturity == L2``) AND
    ``status == active`` entries feed paths 2–5 (m-memory §4.4/§5). L1 candidates
    and superseded/retired entries are never proposed.
  * DETERMINISM. No wall clock, no randomness, no uuid. Classification is a pure
    function of entry fields (``type``, ``scope.layer/role``, ``provider/model``).
    Output is a stable total order (path, then target, then source ids), so
    identical input ⇒ byte-identical output. ``render_report`` takes an INJECTED
    ``ts`` (like memory_store's write path) — it never reads the clock itself.
  * CALIBRATION TAGGING. A charter_tuning proposal derived from a
    ``calibration-note`` keeps its ``(provider, model)`` (calibration is per-
    (provider,model); m-memory §6.2, Constitution §3.6).
  * ACCEPTANCE-SKILL RECALIBRATION. A skill_edit proposal touching the Acceptance
    role's skill sets ``recalibration_required = True`` (changing the Acceptance
    skill invalidates ``calibrated``; m-memory §5 row 2, Constitution §3.6).

NORMATIVE SOURCE: modules/m-memory.md §5 (the five paths + their gates). On any
conflict the spec wins and this file is the bug (plan §1 conflict rule). This is
a STANDALONE module — wiring it into the driver's close is a separate step
(mirrors the loop_controller / loop_ingress standalone-then-wire pattern).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only when dep missing
    raise SystemExit("feedback: pyyaml is required (pip install pyyaml)\n")

# Reuse the substrate's entry model + maturity/status constants (single source).
from memory_store import (  # noqa: E402
    MATURITY_L2,
    STATUS_ACTIVE,
    MemoryEntry,
    MemoryStore,
)


# --------------------------------------------------------------------------- #
# Contract constants                                                          #
# --------------------------------------------------------------------------- #

PATH_SKILL_EDIT = "skill_edit"
PATH_CHARTER_TUNING = "charter_tuning"
PATH_AUTOLOOP_CANDIDATE = "autoloop_candidate"
PATH_FOLD_BACK = "fold_back"
FEEDBACK_PATHS = (
    PATH_SKILL_EDIT,
    PATH_CHARTER_TUNING,
    PATH_AUTOLOOP_CANDIDATE,
    PATH_FOLD_BACK,
)

GATE_HUMAN_APPROVAL = "human_approval"   # Auto Loop §3.3 — human approves the change
GATE_FOLD_BACK = "fold_back"             # Constitution §8 — fold-back deliberation
GATES = (GATE_HUMAN_APPROVAL, GATE_FOLD_BACK)

# Auto Loop is Type A (the product agent improving ITSELF). The Δ-9 fix layers
# that represent Type-A self-improvement surface are prompt_projection +
# semantic_planner (m-memory §3.2 layer enum; m-autoloop §5 reads L2 patterns at
# these layers). An L2 pattern/heuristic here is an Auto Loop experiment input.
TYPE_A_LAYERS = ("prompt_projection", "semantic_planner")
AUTOLOOP_TYPES = ("pattern", "heuristic")

# Δ-9 layers that are framework-level concerns → fold-back (Constitution §8).
FOLD_BACK_LAYERS = ("human_review_required", "judge_calibration", "product_policy")

# A skill_edit is suggested by a recurring problem with how a role works.
SKILL_EDIT_TYPES = ("failure", "heuristic", "detour")

# The Acceptance role's skill is calibration-coupled (swapping it invalidates
# `calibrated`; skills/registry.yaml warns on this; Constitution §3.6).
ACCEPTANCE_ROLE = "acceptance"


# --------------------------------------------------------------------------- #
# Proposal model                                                              #
# --------------------------------------------------------------------------- #


@dataclass
class FeedbackProposal:
    """One propose-only self-evolution suggestion (m-memory §5).

    A proposal is a RECOMMENDATION the human reviews; it changes nothing on its
    own. ``source_entry_ids`` cite the L2 Loop-Memory entries that motivate it,
    threading the suggestion back to the auditable record. ``provider``/``model``
    are set only for a charter_tuning derived from a calibration-note (and only
    when all contributing notes agree).
    """

    path: str
    target: str
    source_entry_ids: List[str]
    rationale: str
    gate: str
    recalibration_required: bool = False
    maturity: str = MATURITY_L2
    provider: Optional[str] = None
    model: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "path": self.path,
            "target": self.target,
            "source_entry_ids": list(self.source_entry_ids),
            "rationale": self.rationale,
            "gate": self.gate,
            "recalibration_required": self.recalibration_required,
            "maturity": self.maturity,
        }
        if self.provider is not None:
            d["provider"] = self.provider
        if self.model is not None:
            d["model"] = self.model
        return d


# --------------------------------------------------------------------------- #
# role → bound-skill map (skills/registry.yaml role_defaults)                  #
# --------------------------------------------------------------------------- #


def _find_repo_file(relpath: str, start: Optional[str] = None) -> Optional[str]:
    """Walk up from ``start`` (default: this file's dir) to find ``relpath``.

    Mirrors driver._find_schemas_dir: locates a repo-rooted file regardless of
    the caller's cwd. Returns the absolute path or None.
    """
    cur = start or os.path.dirname(os.path.abspath(__file__))
    while True:
        cand = os.path.join(cur, relpath)
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load_role_skill_map() -> Dict[str, List[str]]:
    """Return ``{role: [skill_id, ...]}`` from skills/registry.yaml role_defaults.

    Default-bound skills per role drive skill_edit targeting. If the registry is
    absent/unreadable, returns ``{}`` — and skill_edit proposals are simply not
    emitted (never crash; default-deny in spirit). Pure read; no clock.
    """
    path = _find_repo_file(os.path.join("skills", "registry.yaml"))
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):  # pragma: no cover - defensive
        return {}
    defaults = (data or {}).get("role_defaults") or {}
    out: Dict[str, List[str]] = {}
    for role, skills in defaults.items():
        if isinstance(skills, str):
            out[str(role)] = [skills]
        elif isinstance(skills, (list, tuple)):
            out[str(role)] = [str(s) for s in skills]
    return out


# --------------------------------------------------------------------------- #
# Classification (pure) — entry → list of (path, target, recal, prov, model)   #
# --------------------------------------------------------------------------- #


def _eligible(entries: Iterable[MemoryEntry]) -> List[MemoryEntry]:
    """Only matured (L2), active entries feed load-bearing paths (m-memory §4.4)."""
    return [
        e for e in entries
        if e.maturity == MATURITY_L2 and e.status == STATUS_ACTIVE
    ]


def _entry_signals(
    entry: MemoryEntry, role_skill_map: Dict[str, List[str]]
) -> List[Tuple[str, str, bool, Optional[str], Optional[str]]]:
    """Return the (path, target, recalibration_required, provider, model) signals
    a single L2 entry contributes. Pure; deterministic order.

    An entry MAY contribute to several paths (e.g. a judge_calibration-layer
    calibration-note feeds BOTH charter_tuning and fold_back). Documented per
    m-memory §5.
    """
    scope = entry.scope or {}
    layers = set(scope.get("layer") or [])
    roles = set(scope.get("role") or [])
    out: List[Tuple[str, str, bool, Optional[str], Optional[str]]] = []

    # Path 4 — Auto Loop (Type A) candidate: a pattern/heuristic at a Type-A
    # self-improvement layer (prompt_projection / semantic_planner). Δ-9 hookup.
    if entry.type in AUTOLOOP_TYPES:
        for layer in sorted(layers & set(TYPE_A_LAYERS)):
            out.append((PATH_AUTOLOOP_CANDIDATE, layer, False, None, None))

    # Path 2 — skill-edit suggestion: a recurring problem with a role whose
    # default skill could be improved. Acceptance ⇒ recalibration_required.
    if entry.type in SKILL_EDIT_TYPES:
        for role in sorted(roles):
            for skill in role_skill_map.get(role, []):
                out.append((PATH_SKILL_EDIT, skill, role == ACCEPTANCE_ROLE,
                            None, None))

    # Path 3 — charter default tuning: a calibration-note suggests tuning the
    # judge calibration for the (provider, model) it observed. Conservative: only
    # calibration-notes drive charter_tuning (the clearest threshold signal);
    # broadening to other binding tweaks is itself a fold-back decision.
    if entry.type == "calibration-note":
        target_roles = sorted(roles) or [ACCEPTANCE_ROLE]  # calibration ⇒ judge
        for role in target_roles:
            out.append((PATH_CHARTER_TUNING,
                        f"tooling.{role}.judge_calibration",
                        False, entry.provider, entry.model))

    # Path 5 — fold-back: a framework-level concern (human_review_required /
    # judge_calibration / product_policy layer).
    for layer in sorted(layers & set(FOLD_BACK_LAYERS)):
        out.append((PATH_FOLD_BACK, layer, False, None, None))

    return out


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def propose(
    store_or_entries: Union[MemoryStore, Sequence[MemoryEntry]],
    *,
    role_skill_map: Optional[Dict[str, List[str]]] = None,
) -> List[FeedbackProposal]:
    """Generate propose-only self-evolution proposals from L2 Loop-Memory entries.

    Accepts a ``MemoryStore`` (entries are read via ``load_all``) or an explicit
    list of ``MemoryEntry``. Pure: it reads only; it NEVER writes the store or any
    file. ``role_skill_map`` (role → bound skills) drives skill_edit targeting; if
    omitted it is loaded from skills/registry.yaml (absent ⇒ no skill_edit).

    Proposals are aggregated by (path, target): all L2 entries that motivate the
    same suggestion are merged into ONE proposal citing every source id, so the
    human sees one suggestion per skill / charter key / layer. Returns a list in
    a stable total order: (path, target, source ids).
    """
    if isinstance(store_or_entries, MemoryStore):
        entries: List[MemoryEntry] = store_or_entries.load_all()
    else:
        entries = list(store_or_entries)
    if role_skill_map is None:
        role_skill_map = load_role_skill_map()

    # Aggregate by (path, target). Accumulate source ids, recalibration flag, and
    # the set of (provider, model) pairs seen (for charter_tuning calibration).
    @dataclass
    class _Acc:
        source_ids: List[str] = field(default_factory=list)
        recal: bool = False
        prov_model: set = field(default_factory=set)

    buckets: Dict[Tuple[str, str], _Acc] = {}
    for entry in _eligible(entries):
        for path, target, recal, prov, model in _entry_signals(entry, role_skill_map):
            acc = buckets.setdefault((path, target), _Acc())
            if entry.id not in acc.source_ids:
                acc.source_ids.append(entry.id)
            acc.recal = acc.recal or recal
            if prov is not None or model is not None:
                acc.prov_model.add((prov, model))

    proposals: List[FeedbackProposal] = []
    for (path, target), acc in buckets.items():
        source_ids = sorted(set(acc.source_ids))
        gate = GATE_FOLD_BACK if path == PATH_FOLD_BACK else GATE_HUMAN_APPROVAL
        # (provider, model) is attached only when all contributing calibration
        # notes agree on a single pair (else it is ambiguous → leave unset).
        provider = model = None
        if len(acc.prov_model) == 1:
            provider, model = next(iter(acc.prov_model))
        proposals.append(FeedbackProposal(
            path=path,
            target=target,
            source_entry_ids=source_ids,
            rationale=_rationale(path, target, source_ids, acc.recal),
            gate=gate,
            recalibration_required=acc.recal,
            provider=provider,
            model=model,
        ))

    proposals.sort(key=lambda p: (p.path, p.target, tuple(p.source_entry_ids)))
    return proposals


def _rationale(path: str, target: str, source_ids: Sequence[str],
               recal: bool) -> str:
    """A deterministic, human-readable rationale (no clock; no entry bodies, to
    avoid re-stating case-specific text — the human reads the cited entries)."""
    n = len(source_ids)
    base = (f"{n} matured (L2) Loop-Memory lesson(s) {list(source_ids)} motivate "
            f"a `{path}` suggestion for `{target}`. PROPOSE-ONLY: a human must "
            f"approve before any change (m-memory §5).")
    if recal:
        base += (" NOTE: this touches the Acceptance skill — applying it "
                 "invalidates judge calibration (Constitution §3.6); recalibrate "
                 "before re-enabling autonomous Acceptance.")
    return base


def render_report(proposals: Sequence[FeedbackProposal], *, ts: str) -> str:
    """Render a deterministic markdown feedback report (the propose-only artifact
    a human reviews). ``ts`` is INJECTED (no clock here). Grouped by path; stable
    order. Returns the report text; writing it is the caller's choice."""
    lines: List[str] = []
    lines.append("# Loop Memory feedback proposals (PROPOSE-ONLY)")
    lines.append("")
    lines.append(f"generated_at: {ts}")
    lines.append(
        "Each item is a SUGGESTION derived from matured (L2) cross-loop lessons "
        "(m-memory §5). Nothing here is applied automatically — a human approves "
        "each change (load-bearing edits fold back per Constitution §1.7-D)."
    )
    lines.append("")
    lines.append(f"proposals: {len(proposals)}")
    lines.append("")
    if not proposals:
        lines.append("_No matured (L2) lessons motivate a feedback proposal._")
        lines.append("")
        return "\n".join(lines)
    for path in FEEDBACK_PATHS:
        group = [p for p in proposals if p.path == path]
        if not group:
            continue
        lines.append(f"## {path}")
        lines.append("")
        for p in group:
            tag = " ⚠ recalibration_required" if p.recalibration_required else ""
            pm = (f" (provider={p.provider}, model={p.model})"
                  if (p.provider or p.model) else "")
            srcs = ", ".join(f"[[{sid}]]" for sid in p.source_entry_ids)
            lines.append(f"- **{p.target}**{pm}{tag} — gate: `{p.gate}`")
            lines.append(f"  - sources: {srcs}")
            lines.append(f"  - {p.rationale}")
        lines.append("")
    return "\n".join(lines)
