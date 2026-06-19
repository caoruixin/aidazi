#!/usr/bin/env python3
"""driver — the standalone deterministic Delivery-Loop outer loop (P2 MVP).

This is the framework-owned deterministic kernel from ADR-0001: a standalone
Python state machine that drives non-deterministic LLM work done by per-harness
adapters. NO LLM lives in the driver. It owns, and only owns, the deterministic
slice:

  - the state machine  idle → dev_pending → gate_pending → review_pending →
    close_pending → advance  (process/delivery-loop.md §4.2.4; P2 = no Acceptance);
  - per-role adapter selection from a plain-YAML charter's
    tooling.<role>.{harness,provider,model}  (plan §5 field shapes);
  - JSON-schema verdict validation against the EXISTING schemas/ verdict shapes
    (delivery-loop §4.2.7) — an invalid verdict is a gate_hard_fail, NEVER a
    permissive default;
  - the checkpoint inbox (docs/checkpoints/<ts>__<id>__<scope>.md, §4.2.3 shape);
  - the fix-round counter bounded by charter.budget.max_fix_rounds_total (§4.4);
  - a budget guard (spawn-count / fix-round caps);
  - resume from .orchestrator/state.json (§4.5);
  - Audit Spine event emission threading one loop_id (engine-kit/audit/audit_log).

NORMATIVE SOURCE: process/delivery-loop.md §4.2 (state machine, verdict parsing,
filesystem layout, fix-round bounds, resume) + docs/adr/ADR-0001-engine-substrate.md
(substrate + the spawn/verdict contract). This file is an engine-kit reference
*implementation*; on any conflict the spec wins and this file is the bug.

DETERMINISM: the driver itself is pure deterministic control flow. The only
non-determinism (timestamps for checkpoint filenames + audit ts) is injected via
a ``clock`` callable so tests are reproducible. All semantic judgment lives in
the adapters' verdicts.

Run artifacts (state.json, checkpoints/, audit/) are written under a RUN DIR the
caller supplies — for the demo + tests this is a temp dir under /tmp, never the
repo and never examples/minimal-greenfield.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

# Sentinel returned by _resolve_dev_spec when a LIVE run cannot resolve a complete,
# scope-valid Dev spec: the engine has written a refinement checkpoint + set
# STATE_HALTED, and the dev step must NOT proceed to the model spawn.
_DEV_SPEC_HALT = object()

# A safe sub-sprint id: letters/digits then letters/digits/dot/underscore/hyphen.
# Used to gate ANY interpolation of an id into a filesystem path (no `..`, no `/`).
# Anchored with \A…\Z (NOT ^…$): Python's `$` also matches just BEFORE a trailing
# newline, so `^…$` would accept e.g. "sprint-001\n" — \Z matches ONLY the absolute
# end of string, closing that hole.
_SAFE_SUBSPRINT_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")

# A safe loop_id: same character discipline as a sub-sprint id (letters/digits then
# ._- only — no path separators, no leading dot, so no `..`), with a more generous
# length cap (loop_ids may carry a mode + subsprint + timestamp). The loop_id flows
# into BOTH the audit ledger FILENAME (audit_path, interpolated RAW) and the per-loop
# transcripts dir, so it is validated FAIL-CLOSED at the Driver boundary — this is the
# single guard that prevents ledger-path traversal AND the lossy-sanitization
# collision where distinct ids (e.g. `loop/a` and `loop_a`) would map to one dir.
_SAFE_LOOP_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

try:
    import yaml
except ImportError:  # pragma: no cover - import guard
    sys.stderr.write("driver: PyYAML is required (pip install pyyaml)\n")
    raise

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - import guard
    sys.stderr.write("driver: jsonschema is required (pip install jsonschema)\n")
    raise

# --------------------------------------------------------------------------- #
# Import the Audit Spine (engine-kit/audit/audit_log.py) — REUSE, do not copy.
# Import the adapters package (sibling of orchestrator/ under engine-kit/).
# We add engine-kit/ to sys.path so both `audit.audit_log` and `adapters` resolve
# regardless of the caller's cwd.
# --------------------------------------------------------------------------- #
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # engine-kit/orchestrator/
_ENGINE_KIT_DIR = os.path.dirname(_THIS_DIR)           # engine-kit/
_AUDIT_DIR = os.path.join(_ENGINE_KIT_DIR, "audit")
# _THIS_DIR is included so the sibling orchestrator modules (loop_controller,
# loop_ingress) resolve as bare imports regardless of the caller's cwd.
for _p in (_THIS_DIR, _ENGINE_KIT_DIR, _AUDIT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402  (engine-kit/audit/audit_log.py)
from adapters import ADAPTER_REGISTRY, Adapter, AdapterError  # noqa: E402

# P3 INTEGRATION 1 — the standalone Loop Controller (engine-kit/orchestrator/
# loop_controller.py) is the fix-loop termination AUTHORITY. The driver builds a
# LoopState from RunState + charter + the verdict and asks decide() what to do;
# it owns the side effects (spawn / checkpoint / audit). Imported read-only.
import loop_controller as lc  # noqa: E402

# P4 INTEGRATION — Loop Ingress (engine-kit/orchestrator/loop_ingress.py) is the
# git-isolation + loop-registry layer. Like the controller it is a standalone
# module: the PURE decision (decide_strategy) plus git SIDE EFFECTS
# (setup_context / cleanup) and a JSON loop registry. The driver owns the wiring
# (decide → recommend → setup → register at start; mark_done → cleanup at close)
# and is byte-identical to pre-P4 when no repo_dir is supplied (ingress off).
import loop_ingress as li  # noqa: E402

# P3 INTEGRATION 2 — Loop Memory (engine-kit/memory/memory_store.py) is OPTIONAL.
# It is imported lazily/guarded so the driver has NO hard dependency on it: a
# Driver built without a memory_root never touches the store (behaviour is then
# byte-identical to before this integration). The memory/ dir is a sibling of
# orchestrator/ under engine-kit/, so put it on sys.path next to audit/.
_MEMORY_DIR = os.path.join(_ENGINE_KIT_DIR, "memory")
if _MEMORY_DIR not in sys.path:
    sys.path.insert(0, _MEMORY_DIR)
try:
    from memory_store import MemoryStore  # noqa: E402
    from memory_store import MemoryError as _MemoryError  # noqa: E402
except Exception:  # pragma: no cover - memory is optional; absence must not break
    MemoryStore = None  # type: ignore
    _MemoryError = Exception  # type: ignore

# P5 — the Loop Memory FEEDBACK engine (engine-kit/memory/feedback.py). Optional,
# read-only, PROPOSE-ONLY: at a successful milestone close (memory enabled) it
# reads matured (L2) entries and emits self-evolution PROPOSALS (m-memory §5) for
# the human to approve — it NEVER applies a change. Guarded import like memory.
try:
    import feedback as _feedback  # noqa: E402  (engine-kit/memory/feedback.py)
except Exception:  # pragma: no cover - optional; absence must not break the loop
    _feedback = None  # type: ignore


# --------------------------------------------------------------------------- #
# States + a typed control-flow error for the gate_hard_fail MANDATORY_CHECKPOINT.
# --------------------------------------------------------------------------- #
STATE_IDLE = "idle"
STATE_DEV_PENDING = "dev_pending"
STATE_GATE_PENDING = "gate_pending"
STATE_REVIEW_PENDING = "review_pending"
STATE_CLOSE_PENDING = "close_pending"
STATE_ACCEPTANCE_PENDING = "acceptance_pending"  # P3 piece 1 (delivery-loop §4.2.4)
STATE_ADVANCE = "advance"
STATE_DONE = "done"
STATE_HALTED = "halted"

# P6.1 — OPTIONAL full_chain_guided bootstrap PRE-states (delivery-loop §4.2.4 —
# guided pre-states). These run BEFORE the existing dev_pending flow and ONLY in
# loop_mode == "full_chain_guided"; in the DEFAULT delivery_only mode none of them
# run and the run() path is byte-identical to before P6.1. Like
# acceptance_pending they are OUT-OF-BAND (NOT in LOOP_ORDER) and handled
# explicitly in _drive() so resume re-enters at the persisted pre-state.
STATE_RESEARCH_PENDING = "research_pending"      # draft the milestone brief (artifact)
STATE_GATE1_PENDING = "gate1_pending"            # customer Gate-1 sign-off (injected resolver)
STATE_DECOMPOSE_PENDING = "decompose_pending"    # decompose into the sub-sprint plan

# Loop-mode values. delivery_only is the DEFAULT and MUST stay byte-identical.
LOOP_MODE_DELIVERY_ONLY = "delivery_only"
LOOP_MODE_FULL_CHAIN_GUIDED = "full_chain_guided"

# The out-of-band guided pre-states, in the order the bootstrap drives them. Kept
# separate from LOOP_ORDER on purpose (they are not part of the per-sub-sprint
# linear loop) — see _drive_guided_prestates().
GUIDED_PRESTATE_ORDER = [
    STATE_RESEARCH_PENDING,
    STATE_GATE1_PENDING,
    STATE_DECOMPOSE_PENDING,
]

# Linear MVP order (no Acceptance state — that is P3). The Acceptance state is
# NOT in this linear order: per delivery-loop §4.2.4 it fires AFTER the milestone
# completes (the terminal clean-pass advance of the sub-sprint sequence), gated on
# charter.acceptance.enabled, so the close→advance path remains byte-identical when
# acceptance is disabled (backward-compat).
LOOP_ORDER = [
    STATE_DEV_PENDING,
    STATE_GATE_PENDING,
    STATE_REVIEW_PENDING,
    STATE_CLOSE_PENDING,
]


class GateHardFail(Exception):
    """A deterministic gate failed and auto-fix was not eligible — the
    ``gate_hard_fail`` MANDATORY_CHECKPOINT (process/delivery-loop.md §4.2.3 #8).

    The driver writes a checkpoint file + emits an audit event before raising.
    Carries the triggering ``reason`` and the offending ``state``.
    """

    def __init__(self, reason: str, *, state: str = "", checkpoint_path: str = ""):
        self.reason = reason
        self.state = state
        self.checkpoint_path = checkpoint_path
        super().__init__(reason)


class BudgetExceeded(GateHardFail):
    """Budget guard tripped (spawn-count / fix-round cap). Subclass of
    GateHardFail so callers that catch the hard-fail also catch budget halts;
    surfaced as a gate_hard_fail checkpoint per §4.4."""


# --------------------------------------------------------------------------- #
# Schema loading. We validate ONLY the two P2 verdicts the driver parses:
#   review-verdict + deliver-close-verdict (delivery-loop §4.2.7).
# Located by walking up from engine-kit/ to find schemas/ (engine-kit sits next
# to schemas/). We READ them; we never touch / extend them (parallel-safe).
# --------------------------------------------------------------------------- #
def _find_schemas_dir(start: str = _ENGINE_KIT_DIR) -> Optional[str]:
    cur = start
    while True:
        cand = os.path.join(cur, "schemas")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load_verdict_schemas(schemas_dir: Optional[str] = None) -> dict[str, dict]:
    """Return {role_or_fn: schema} for the verdicts the driver parses.

    review + close are the P2 verdicts; acceptance is the P3-piece-1 verdict
    (schemas/acceptance-verdict.schema.json, delivery-loop §4.2.7). The acceptance
    schema is loaded unconditionally (read-only) but only USED when the charter
    enables acceptance — so a charter without acceptance is unaffected."""
    base = schemas_dir or _find_schemas_dir()
    if not base:
        raise FileNotFoundError(
            "schemas/ directory not found at or above engine-kit/"
        )
    out: dict[str, dict] = {}
    for key, fname in (
        ("review", "review-verdict.schema.json"),
        ("close", "deliver-close-verdict.schema.json"),
        ("acceptance", "acceptance-verdict.schema.json"),
        # P6.1 — the milestone-decomposition verdict for full_chain_guided. Loaded
        # unconditionally (read-only) but only USED in loop_mode full_chain_guided
        # (the decompose_pending pre-state), so existing delivery_only charters are
        # unaffected, exactly like the acceptance schema above.
        ("deliver_plan", "deliver-plan-verdict.schema.json"),
    ):
        path = os.path.join(base, fname)
        with open(path, "r", encoding="utf-8") as fh:
            out[key] = json.load(fh)
    return out


def validate_verdict(verdict: Any, schema: dict) -> Optional[str]:
    """Return None if ``verdict`` validates against ``schema``, else a one-line
    error string (the first schema error). Pure; no clock/network/LLM."""
    if not isinstance(verdict, dict):
        return f"verdict is not a JSON object (got {type(verdict).__name__})"
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(verdict), key=lambda e: list(e.absolute_path))
    if not errors:
        return None
    e = errors[0]
    loc = ".".join(str(p) for p in e.absolute_path) or "<root>"
    return f"{loc}: {e.message}"


# --------------------------------------------------------------------------- #
# Charter loading (LENIENT plain YAML — NOT validated against the schema, which
# is being extended concurrently; stay decoupled per the P2 scope note).
# --------------------------------------------------------------------------- #
@dataclass
class RoleRouting:
    role: str
    harness: str
    provider: str
    model: str
    tools: list[str] = field(default_factory=list)
    # Facet C (Role Configuration Contract): the role's abstract connector grant
    # (each entry ~ connector-binding.schema.json) + the role's sandbox. Threaded
    # into adapter.spawn(...) so the adapter can translate them to harness-native
    # config. DEFAULT-DENY: an absent `connectors` is an empty list (no grant).
    connectors: list = field(default_factory=list)
    sandbox: str = "workspace_write"
    # EXPLICIT opt-in network grant for a write sandbox (default-deny). The
    # framework invariant is Dev = NO network (delivery-loop §4.2.7); an adopter
    # that genuinely needs a Dev to `pip`/`npm` install sets
    # tooling.<role>.network_access: true. The codex adapter then un-blocks the
    # OS-sandbox network; the driver AUDITS it as a deliberate escalation and the
    # charter validator WARNS. Off ⇒ byte-identical to the no-network default.
    network_access: bool = False


def load_charter(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("charter root must be a mapping/object")
    return data


# LEAST-PRIVILEGE per-role sandbox default. ONLY the Dev edits files, so only Dev
# defaults to ``workspace_write``; every judgment/planning role (review, acceptance,
# research, deliver) and any unknown role defaults to ``read_only``. A role that
# truly needs to write sets ``sandbox: workspace_write`` EXPLICITLY in the charter.
# (Before: every omitted sandbox defaulted to workspace_write, so a codex-backed
# read-only reviewer could be launched with write access — the charter is loaded
# leniently, so the schema's per-role default is never applied at runtime.)
_DEFAULT_SANDBOX_BY_ROLE = {"dev": "workspace_write"}


def _normalize_tools(raw: Any) -> list[str]:
    """Normalize a role ``tools`` value to a flat allowlist of names.

    The schema permits BOTH the legacy array form (``[Read, Grep, Glob]``) AND the
    v2 object form (``{allow: [...]}``). ``list({"allow": [...]})`` yields the dict
    KEYS (``["allow"]``), silently corrupting tool gating exactly where permissions
    matter — so the object form is unpacked here. Anything else ⇒ empty list."""
    if isinstance(raw, dict):
        return [str(t) for t in (raw.get("allow") or [])]
    if isinstance(raw, (list, tuple)):
        return [str(t) for t in raw]
    return []


def route_for_role(charter: dict, role: str) -> RoleRouting:
    """Read tooling.<role>.{harness|agent_kind, provider, model, tools} leniently.

    Accepts the plan §5 field ``harness`` and also the legacy ``agent_kind`` as a
    fallback (templates/fixtures still use agent_kind) so the demo charter and an
    existing charter both route. Missing fields default to empty strings; the
    adapter registry lookup (below) is what enforces a known harness.

    SANDBOX is least-privilege per role (see ``_DEFAULT_SANDBOX_BY_ROLE``): an
    omitted sandbox does NOT silently grant write access to a judge/planner.
    """
    tooling = charter.get("tooling") or {}
    rc = tooling.get(role) or {}
    harness = rc.get("harness") or rc.get("agent_kind") or ""
    default_sandbox = _DEFAULT_SANDBOX_BY_ROLE.get(role, "read_only")
    return RoleRouting(
        role=role,
        harness=str(harness),
        provider=str(rc.get("provider") or ""),
        model=str(rc.get("model") or ""),
        # Normalize BOTH the legacy array and the v2 {allow:[...]} object form.
        tools=_normalize_tools(rc.get("tools")),
        # Facet C: per-role connector grant (default-deny ⇒ [] when omitted) +
        # the role's sandbox (LEAST PRIVILEGE: dev⇒workspace_write, else read_only).
        connectors=list(rc.get("connectors") or []),
        sandbox=str(rc.get("sandbox") or default_sandbox),
        # Opt-in network grant — FAIL CLOSED: only a literal boolean ``true`` grants
        # network (``is True``), so a typo / non-bool (e.g. the string "yes", or 1)
        # never silently over-grants. Default-deny matches the Dev=no-network invariant.
        network_access=(rc.get("network_access") is True),
    )


# --------------------------------------------------------------------------- #
# Run state (persisted to .orchestrator/state.json for resume, §4.5).
# --------------------------------------------------------------------------- #
@dataclass
class RunState:
    loop_id: str
    subsprint_id: str
    state: str = STATE_IDLE
    fix_round: int = 0
    spawn_count: int = 0
    history: list[str] = field(default_factory=list)
    last_verdict: Optional[dict] = None
    # ---- P3 INTEGRATION 1: Loop-Controller fix-loop tracking (persisted for
    #      resume, §4.5). The driver maintains these ACROSS fix rounds and feeds
    #      them into a LoopState; the controller only READS them.
    #   seen_finding_keys      : every finding identity observed so far (dedup
    #                            across rounds → "is this round's finding NEW?").
    #   rounds_since_new_finding: K-counter for the dry-stop / convergence guard
    #                            (consecutive fix rounds that added NO new finding).
    #   budget_spent            : generic spend accumulator vs charter budget cap
    #                            (units = the charter's; mock runs stay at 0.0).
    seen_finding_keys: list[str] = field(default_factory=list)
    rounds_since_new_finding: int = 0
    budget_spent: float = 0.0
    # ---- P6.1: full_chain_guided bootstrap state (persisted for resume, §4.5).
    #      All default to the delivery_only baseline, so a delivery_only RunState
    #      round-trips byte-identically (these keys are simply written with their
    #      defaults; from_dict tolerates their absence in an older state.json).
    #   loop_mode         : "delivery_only" (default) | "full_chain_guided".
    #   brief_signed       : the milestone brief is human-signed (Gate-1 sign-off
    #                        OR a charter intent_contract.confirmed_by_human).
    #   brief_draft_ref    : reference to the Research-drafted brief artifact.
    #   milestone_planned  : the milestone has been decomposed into a sub-sprint
    #                        plan (decompose_pending completed).
    #   planned_sequence   : the ordered sub-sprint ids from the decompose plan.
    #   planned_subsprints : the FULL structured sub-sprint specs from the
    #                        decompose plan (id/objective/scope/exit_criteria/...).
    #                        This is the CANONICAL executable Dev-spec source — the
    #                        Dev spec is the schema-valid plan, not a required file.
    loop_mode: str = LOOP_MODE_DELIVERY_ONLY
    brief_signed: bool = False
    brief_draft_ref: Optional[str] = None
    milestone_planned: bool = False
    planned_sequence: list[str] = field(default_factory=list)
    planned_subsprints: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "loop_id": self.loop_id,
            "subsprint_id": self.subsprint_id,
            "state": self.state,
            "fix_round": self.fix_round,
            "spawn_count": self.spawn_count,
            "history": list(self.history),
            "last_verdict": self.last_verdict,
            "seen_finding_keys": list(self.seen_finding_keys),
            "rounds_since_new_finding": self.rounds_since_new_finding,
            "budget_spent": self.budget_spent,
            "loop_mode": self.loop_mode,
            "brief_signed": self.brief_signed,
            "brief_draft_ref": self.brief_draft_ref,
            "milestone_planned": self.milestone_planned,
            "planned_sequence": list(self.planned_sequence),
            "planned_subsprints": list(self.planned_subsprints),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RunState":
        return cls(
            loop_id=d["loop_id"],
            subsprint_id=d["subsprint_id"],
            state=d.get("state", STATE_IDLE),
            fix_round=int(d.get("fix_round", 0)),
            spawn_count=int(d.get("spawn_count", 0)),
            history=list(d.get("history", [])),
            last_verdict=d.get("last_verdict"),
            seen_finding_keys=list(d.get("seen_finding_keys", [])),
            rounds_since_new_finding=int(d.get("rounds_since_new_finding", 0)),
            budget_spent=float(d.get("budget_spent", 0.0)),
            loop_mode=str(d.get("loop_mode", LOOP_MODE_DELIVERY_ONLY)),
            brief_signed=bool(d.get("brief_signed", False)),
            brief_draft_ref=d.get("brief_draft_ref"),
            milestone_planned=bool(d.get("milestone_planned", False)),
            planned_sequence=list(d.get("planned_sequence", [])),
            planned_subsprints=list(d.get("planned_subsprints", [])),
        )


# --------------------------------------------------------------------------- #
# The driver.
# --------------------------------------------------------------------------- #
class Driver:
    """Deterministic Delivery-Loop outer loop (P2 MVP, human_in_the_loop).

    Parameters
    ----------
    charter:       parsed plain-YAML charter dict (load_charter()).
    run_dir:       directory for ALL run artifacts (state.json, checkpoints/,
                   audit/). MUST be outside the repo (a /tmp dir for demo+tests).
    adapters:      {role -> Adapter}. The caller wires these (the demo builds
                   MockAdapters from the charter routing; production would build
                   real adapters from ADAPTER_REGISTRY[harness]).
    loop_id:       threads the Audit Spine (one ledger per loop).
    clock:         injectable () -> ISO-8601 str. Tests pass a deterministic one.
    context:       read-only adopter context paths (e.g. the minimal-greenfield
                   objective files) — recorded in the loop_start audit event;
                   the driver never writes there.
    repo_dir:      OPTIONAL git repo for Loop Ingress (P4). None ⇒ ingress OFF
                   (byte-identical to pre-P4: no git op, no registry). When set,
                   the loop is given a git working context at ingress and
                   registered for cross-loop collision detection.
    isolation_strategy: OPTIONAL human-confirmed isolation override
                   (current_branch | new_branch | new_worktree). None ⇒ the
                   charter's pre-authorized default is used and any force-condition
                   escalation is RECOMMENDED (checkpoint), never auto-applied.
    loop_mode:     P6.1 — "delivery_only" (DEFAULT — current behaviour, byte-
                   identical) | "full_chain_guided" (adds the OPTIONAL research →
                   gate1 → decompose bootstrap pre-states before the delivery
                   loop). The ctor param WINS over charter.autonomy.loop_mode; an
                   absent param falls back to the charter, else delivery_only.
    gate_resolver: P6.1 — the HUMAN's voice at a guided decision boundary, INJECTED
                   like ``clock``. Signature
                       (gate_id: str, context: dict, options: Sequence[str])
                       -> Optional[dict]
                   returning {"choice": "sign"|"reject"|"abort", "note": str,
                   "resolver": str} or None. The engine NEVER fabricates a sign;
                   a missing resolver OR a None return → the driver HALTS (writes
                   the checkpoint, exits) for async resolution. Only consulted in
                   full_chain_guided; ignored in delivery_only.
    """

    def __init__(
        self,
        charter: dict,
        run_dir: str,
        adapters: dict[str, Adapter],
        *,
        loop_id: str,
        clock: Callable[[], str],
        verdict_schemas: Optional[dict[str, dict]] = None,
        context: Optional[dict] = None,
        memory_root: Optional[str] = None,
        repo_dir: Optional[str] = None,
        isolation_strategy: Optional[str] = None,
        loop_mode: Optional[str] = None,
        gate_resolver: Optional[Callable[[str, dict, Sequence[str]],
                                         Optional[dict]]] = None,
    ):
        self.charter = charter
        self.run_dir = os.path.abspath(run_dir)
        self.adapters = adapters
        # FAIL CLOSED on an unsafe loop_id: it keys the audit ledger filename (raw)
        # and the per-loop transcripts dir, so an unsafe value could traverse or let
        # two distinct ids collide into one dir. Reject at the boundary, never
        # silently sanitize (a lossy sanitize is exactly what would alias them).
        # Require a `str` (NOT just str(loop_id)): otherwise `1` and `"1"` would
        # share a ledger/transcript path while emitting different `loop_id` JSON
        # types into the (hash-chained) ledger.
        if not (isinstance(loop_id, str) and _SAFE_LOOP_ID_RE.match(loop_id)):
            raise ValueError(
                f"unsafe loop_id {loop_id!r}: must be a str matching "
                f"{_SAFE_LOOP_ID_RE.pattern} (letters/digits then ._- only; no path "
                "separators or '..') — it keys the audit ledger filename + transcripts dir")
        self.loop_id = loop_id
        self.clock = clock
        self.schemas = verdict_schemas or load_verdict_schemas()
        self.context = context or {}

        # P4 INTEGRATION — OPTIONAL Loop Ingress. When repo_dir is None the
        # ingress is OFF: no git op, no registry, no isolation choice — the driver
        # is byte-identical to the pre-P4 behaviour (existing tests pass no
        # repo_dir). When a repo_dir IS supplied, the loop is given a git working
        # context at ingress and registered for collision detection.
        #   isolation_strategy : the HUMAN-CONFIRMED strategy override. None ⇒ the
        #     engine uses the charter's pre-authorized default and only RECOMMENDS
        #     (never auto-applies) any force-condition escalation (§1.7-D/OQ-B).
        self.repo_dir = os.path.abspath(repo_dir) if repo_dir else None
        self.isolation_strategy = isolation_strategy
        self.registry: Optional["li.LoopRegistry"] = None
        self.context_handle: Optional["li.ContextHandle"] = None

        # P5 — set True at a clean MILESTONE close (the terminal sub-sprint of the
        # approved sequence), so the propose-only Loop Memory feedback stage runs
        # at milestone close, not on every per-sub-sprint advance.
        self._milestone_closed = False

        # P3 INTEGRATION 2 — OPTIONAL Loop Memory. When memory_root is None the
        # store is never constructed and NO select/record ever runs → the driver
        # is byte-identical to the pre-integration behaviour (the existing tests
        # pass no memory_root). When a root IS supplied we read at ingress and
        # write at close. If the memory module failed to import, a supplied root
        # is a hard configuration error (fail closed, never silently skip).
        self.memory: Optional["MemoryStore"] = None
        if memory_root is not None:
            if MemoryStore is None:  # pragma: no cover - import guard
                raise RuntimeError(
                    "memory_root given but memory_store could not be imported "
                    "(engine-kit/memory/memory_store.py)")
            self.memory = MemoryStore(memory_root)

        # Filesystem layout per delivery-loop §4.2.9 (rooted at run_dir).
        self.orch_dir = os.path.join(self.run_dir, ".orchestrator")
        self.state_path = os.path.join(self.orch_dir, "state.json")
        self.checkpoints_dir = os.path.join(self.run_dir, "docs", "checkpoints")
        self.audit_dir = os.path.join(self.orch_dir, "audit")
        self.audit_ledger = audit.audit_path(self.loop_id, self.audit_dir)
        # Per-spawn execution-record transcripts (the prompt+output materialization
        # the bp-review-team adoption flagged): a sibling of the ledger under the
        # Audit Spine, namespaced per loop_id so a shared run_dir/audit_dir across
        # loops never collides (the ledger is likewise <loop_id>.jsonl). The loop_id
        # is sanitized into a single safe path component (defense-in-depth).
        self.transcripts_dir = os.path.join(
            self.audit_dir, "transcripts", self._safe_path_component(self.loop_id))

        os.makedirs(self.orch_dir, exist_ok=True)
        os.makedirs(self.checkpoints_dir, exist_ok=True)
        os.makedirs(self.audit_dir, exist_ok=True)
        os.makedirs(self.transcripts_dir, exist_ok=True)

        self.budget = charter.get("budget") or {}
        self.autonomy = charter.get("autonomy") or {}

        # P6.1 — resolve the loop mode (ctor param WINS over charter, else the
        # delivery_only default) + stash the injected gate resolver. delivery_only
        # is the default and gates EVERY new pre-state path, so a charter / caller
        # that says nothing is byte-identical to the pre-P6.1 driver.
        self.loop_mode = (loop_mode
                          or self.autonomy.get("loop_mode")
                          or LOOP_MODE_DELIVERY_ONLY)
        self.gate_resolver = gate_resolver

        self.state: Optional[RunState] = None

    # ----- audit ----------------------------------------------------------- #
    def _audit(self, type_: str, payload: dict) -> None:
        audit.append_event(
            self.loop_id, type_, payload,
            ts=self.clock(), path=self.audit_ledger,
        )

    # ----- persistence (resume, §4.5) -------------------------------------- #
    def _save_state(self) -> None:
        assert self.state is not None
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(self.state.to_dict(), fh, indent=2, sort_keys=True)

    def _load_state(self) -> Optional[RunState]:
        if not os.path.isfile(self.state_path):
            return None
        with open(self.state_path, "r", encoding="utf-8") as fh:
            return RunState.from_dict(json.load(fh))

    # ----- checkpoint inbox (§4.2.3 shape) --------------------------------- #
    @staticmethod
    def _safe_path_component(s: Any) -> str:
        """Sanitize a string into a SINGLE safe filename component: keep
        ``[A-Za-z0-9._-]``, replace anything else (incl. path separators) with
        ``_``, and drop leading dots. A ``scope``/id sourced from an LLM plan can
        otherwise traverse out of the checkpoints dir (e.g. ``../../evil``)."""
        return re.sub(r"[^A-Za-z0-9._-]", "_", str(s)).lstrip(".") or "x"

    # ----- per-spawn execution-record transcripts -------------------------- #
    def _write_transcript(self, seq: int, role: str, kind: str,
                          content: Any) -> str:
        """Materialize one spawn-side artifact and return its run-dir-relative path
        (the spawn event's ``prompt_ref`` / ``output_ref``).

        This is the auditability layer the bp-review-team adoption asked for: EVERY
        dispatched prompt and EVERY model output becomes a human-readable file under
        ``.orchestrator/audit/transcripts/<loop_id>/``, anchored to the hash-chained
        Audit Spine that references it. It is the AS-DISPATCHED execution record (one
        per spawn / fix-round) — distinct from the DURABLE, human-reviewed prompt
        artifacts in ``compact/`` (process/prompt-artifact-rules.md §1). The prompt
        bytes are written verbatim, so ``sha256(role\\x00 + file)`` cross-checks the
        spawn ``input_hash`` recorded in the ledger.

        ``kind`` is ``"prompt"`` or ``"output"``. An artifact-wrapped output
        (``{"artifact": "<prose>"}`` — a Dev/Research handoff) is written as readable
        Markdown; any other verdict is pretty-printed JSON. Serialization is
        defensive (``repr`` fallback), but the file write itself is allowed to fail
        loudly — exactly like the ledger append — because a transcripts dir that
        cannot be written is a real audit failure, not something to swallow."""
        safe_role = self._safe_path_component(role)
        if kind == "prompt":
            text = content if isinstance(content, str) else str(content)
            ext = "md"
        else:  # "output"
            if (isinstance(content, dict) and set(content) == {"artifact"}
                    and isinstance(content.get("artifact"), str)):
                text, ext = content["artifact"], "md"
            else:
                try:
                    text = json.dumps(content, indent=2, sort_keys=True,
                                      ensure_ascii=False)
                except (TypeError, ValueError):
                    text = repr(content)
                ext = "json"
        # seq (the loop's monotonic spawn_count) keys the filename, so fix-round
        # re-runs of the same role never clobber an earlier transcript.
        fname = f"{seq:04d}__{safe_role}__{kind}.{ext}"
        path = os.path.join(self.transcripts_dir, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return os.path.relpath(path, self.run_dir)

    def _write_checkpoint(self, checkpoint_id: str, scope: str,
                          context_md: str, options_md: str,
                          *, decision: str = "pending",
                          resolver: str = "null",
                          resolved_at: str = "null") -> str:
        """Write a checkpoint file in the §4.2.3 shape. Defaults to a human-
        pending checkpoint (decision: pending, resolver: null). The §3.6 auto-
        degrade checkpoint overrides these to record an ALREADY-actioned,
        orchestrator-resolved event (§4.2.3: resolver 'orchestrator' if auto-
        degraded) so the auto-degradation is recorded, not silent."""
        ts = self.clock()
        safe_ts = ts.replace(":", "").replace("-", "").replace("T", "-")
        # squeeze "Z"/offset to keep the filename clean & deterministic
        safe_ts = safe_ts.split(".")[0].rstrip("Z")
        fname = (f"{safe_ts}__{self._safe_path_component(checkpoint_id)}"
                 f"__{self._safe_path_component(scope)}.md")
        path = os.path.join(self.checkpoints_dir, fname)
        decision_section = (
            "<human writes; orchestrator picks up>\n"
            if decision == "pending"
            else "<orchestrator auto-resolved; recorded above>\n"
        )
        body = (
            "---\n"
            f"checkpoint_id: {checkpoint_id}\n"
            f"scope: {scope}\n"
            f"emitted_at: {ts}\n"
            f"decision: {decision}\n"
            f"resolved_at: {resolved_at}\n"
            f"resolver: {resolver}\n"
            "---\n\n"
            "# Context\n"
            f"{context_md}\n\n"
            "# Options\n"
            f"{options_md}\n\n"
            "# Decision (human fills)\n"
            f"{decision_section}"
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        self._audit("checkpoint_emitted",
                    {"checkpoint_id": checkpoint_id, "scope": scope,
                     "path": os.path.relpath(path, self.run_dir)})
        return path

    def _gate_hard_fail(self, reason: str, state: str) -> GateHardFail:
        """Write the gate_hard_fail checkpoint + audit event, return the error."""
        path = self._write_checkpoint(
            "gate_hard_fail", self.state.subsprint_id if self.state else "unknown",
            context_md=f"Deterministic gate failed in state `{state}`:\n\n> {reason}",
            options_md="- re_run\n- accept_failure_and_route\n- abort",
        )
        self._audit("gate_hard_fail",
                    {"state": state, "reason": reason,
                     "checkpoint": os.path.relpath(path, self.run_dir)})
        return GateHardFail(reason, state=state, checkpoint_path=path)

    # ----- budget guard (§4.4) --------------------------------------------- #
    def _check_budget(self) -> None:
        assert self.state is not None
        max_fix = self.budget.get("max_fix_rounds_total")
        if isinstance(max_fix, int) and self.state.fix_round > max_fix:
            raise BudgetExceeded(
                f"fix_round {self.state.fix_round} exceeds "
                f"budget.max_fix_rounds_total {max_fix}",
            )

    # ----- the spawn boundary (driver → adapter → schema-valid verdict) ----- #
    def _spawn(self, role: str, prompt: str, schema_key: Optional[str]) -> dict:
        """Select the role's adapter, spawn, and (if a verdict schema applies)
        validate the result. An AdapterError OR a schema-invalid verdict becomes
        a gate_hard_fail (delivery-loop §4.2.7) — never a permissive default."""
        assert self.state is not None
        adapter = self.adapters.get(role)
        if adapter is None:
            raise self._gate_hard_fail(
                f"no adapter wired for role {role!r}", self.state.state)
        routing = route_for_role(self.charter, role)
        input_hash = "sha256:" + hashlib.sha256(
            (role + "\x00" + prompt).encode("utf-8")).hexdigest()[:16]
        # P3 INTEGRATION 2: which Loop-Memory entries the ingress block injected
        # (recorded on the spawn event, Audit Spine §4.5 G3). [] when memory off.
        injected = self._injected_ids(role)

        # An opt-in network grant is a DELIBERATE privilege escalation (the
        # Dev=no-network invariant is the default, delivery-loop §4.2.7). Record it
        # explicitly on the Audit Spine BEFORE the spawn so it is NEVER silent —
        # even if the spawn then fails. Default-deny ⇒ no event (byte-identical).
        if routing.network_access:
            self._audit("sandbox_network_granted", {
                "role": role, "harness": adapter.harness,
                "sandbox": routing.sandbox})

        self.state.spawn_count += 1
        # PERSIST the bumped spawn_count NOW (before any transcript is keyed on it):
        # a hard-fail / crash mid-spawn must NOT let a resume REWIND spawn_count and
        # reuse this seq, which would clobber the transcript the ledger already
        # references (e.g. a schema-invalid output, audited then re-run on resume).
        self._save_state()
        # AUDITABILITY: materialize the EXACT dispatched prompt (lessons block
        # included — these are the literal bytes the adapter receives) BEFORE the
        # spawn, so even a transport failure leaves the prompt on disk to audit.
        prompt_ref = self._write_transcript(
            self.state.spawn_count, role, "prompt", prompt)
        try:
            # Facet C: thread the role's connector grant + sandbox through the
            # uniform spawn boundary (keyword-only). DEFAULT-DENY: an empty grant
            # is a no-op (the adapter emits no native connector config), so the
            # spawn is byte-identical to before for a charter without connectors.
            # network_access is the opt-in network grant (default False ⇒ the codex
            # OS-sandbox stays no-network); only the codex adapter acts on it.
            verdict = adapter.spawn(
                role, prompt, routing.tools,
                self.schemas.get(schema_key, {}) if schema_key else {},
                connectors=routing.connectors, sandbox=routing.sandbox,
                network_access=routing.network_access)
        except AdapterError as exc:
            self._audit("spawn", audit.make_spawn_payload(
                role=role, harness=adapter.harness, provider=adapter.provider,
                model=adapter.model, input_hash=input_hash,
                memory_injected=injected,
                run_mode=self.autonomy.get("level", "human_in_the_loop"),
                verdict_ref="adapter_error", prompt_ref=prompt_ref,
                output_ref=None))  # no output produced — the adapter raised
            raise self._gate_hard_fail(
                f"adapter for role {role!r} failed: {exc}", self.state.state)

        # Materialize the EXACT model output (verdict JSON / artifact prose) to a
        # paired transcript NOW — BEFORE validation — so a schema-invalid verdict is
        # still captured for audit, not lost to the gate_hard_fail below.
        output_ref = self._write_transcript(
            self.state.spawn_count, role, "output", verdict)

        # Validate if this spawn carries a verdict schema (spawn_dev does not).
        if schema_key is not None:
            err = validate_verdict(verdict, self.schemas[schema_key])
            self._audit("spawn", audit.make_spawn_payload(
                role=role, harness=adapter.harness, provider=adapter.provider,
                model=adapter.model, input_hash=input_hash,
                memory_injected=injected,
                run_mode=self.autonomy.get("level", "human_in_the_loop"),
                verdict_ref="invalid" if err else "valid",
                prompt_ref=prompt_ref, output_ref=output_ref))
            if err is not None:
                raise self._gate_hard_fail(
                    f"{role} verdict failed schema validation "
                    f"({schema_key}-verdict.schema.json): {err}",
                    self.state.state)
        else:
            self._audit("spawn", audit.make_spawn_payload(
                role=role, harness=adapter.harness, provider=adapter.provider,
                model=adapter.model, input_hash=input_hash,
                memory_injected=injected,
                run_mode=self.autonomy.get("level", "human_in_the_loop"),
                verdict_ref="artifact",
                prompt_ref=prompt_ref, output_ref=output_ref))
        self.state.last_verdict = verdict
        return verdict

    # ----- the deterministic gate set (§4.2.4) ----------------------------- #
    def _run_gates(self) -> None:
        """P2 gate set is deterministic + adapter-free. We assert the Dev handoff
        artifact verdict exists (spawn_dev produced something) — a skipped/missing
        required gate is NOT a pass (§4.2.4 state invariant) → gate_hard_fail."""
        assert self.state is not None
        if self.state.last_verdict is None:
            raise self._gate_hard_fail(
                "dev produced no handoff artifact before gate_pending",
                STATE_GATE_PENDING)
        # (run_tests / validate_stanza / check_handoff / check_trace are wired in
        #  later phases; in the P2 MVP the gate is the presence-of-artifact check.)

    # ----- P3 INTEGRATION 2: Loop Memory at ingress (read) ----------------- #
    def _modules_in_scope(self) -> list[str]:
        """The charter's approved-scope modules (used as the memory scope's
        ``module`` dimension at ingress). Empty list when none declared."""
        scope = (self.autonomy.get("approved_scope") or {})
        return list(scope.get("modules_in_scope") or [])

    def _lessons_block(self, role: str) -> str:
        """Build the "Relevant prior lessons" ingress block for ``role`` from
        Loop Memory, or "" when memory is disabled or has nothing relevant.

        Selection is the store's deterministic scope match on {role, module};
        the block injected into the prompt is short + generalizable (the entry
        BODIES, never case-specific input→output — that is guarded at write).
        Returns the entry ids it injected too, so the spawn audit can record
        ``memory_injected`` (Audit Spine §4.5 G3)."""
        if self.memory is None:
            return ""
        scope = {"role": [role], "module": self._modules_in_scope()}
        entries = self.memory.select(scope)
        if not entries:
            return ""
        lines = ["## Relevant prior lessons (Loop Memory)",
                 "(generalizable heuristics from earlier loops — not rules to "
                 "memorize; apply judgement)"]
        for e in entries:
            body = (e.body or "").strip().splitlines()
            first = body[0].strip() if body else ""
            lines.append(f"- [{e.maturity}] {first}")
        return "\n".join(lines) + "\n\n"

    def _injected_ids(self, role: str) -> list[str]:
        """The entry ids Loop Memory would inject for ``role`` (for the spawn
        audit's ``memory_injected`` field). [] when memory disabled."""
        if self.memory is None:
            return []
        scope = {"role": [role], "module": self._modules_in_scope()}
        return [e.id for e in self.memory.select(scope)]

    # ----- P4 INTEGRATION: Loop Ingress (git isolation + loop registry) ----- #
    def _ingress_enabled(self) -> bool:
        """Ingress is wired ONLY when a repo_dir was supplied; otherwise every
        ingress hook is a no-op and the driver is byte-identical to pre-P4."""
        return self.repo_dir is not None

    def _loop_init_ingress(self) -> None:
        """At a FRESH loop start: decide the isolation strategy, set up the git
        working context, and register the loop (Loop Ingress, plan §4.3).

        Constitution §1.7-D / OQ-B — RECOMMEND, NEVER UNILATERALLY ESCALATE: the
        engine uses the charter's pre-authorized ``default_strategy`` (or an
        explicit human-confirmed ``isolation_strategy``); a force-condition
        escalation (dirty tree / loop-active-on-branch) is RECOMMENDED via a
        human-pending checkpoint, not auto-applied. No-op when ingress is off."""
        if not self._ingress_enabled():
            return
        assert self.state is not None
        repo_dir = self.repo_dir
        isolation_cfg = self.charter.get("isolation") or {}
        self.registry = li.LoopRegistry(os.path.join(repo_dir, ".orchestrator"))

        # Observe working-tree + collision state (read-only git). Exclude THIS
        # loop's own record: a fresh re-run of an un-closed loop_id must not see
        # its own stale active entry as a collision-on-branch and spuriously
        # recommend escalation against itself.
        target_branch = li.current_branch(repo_dir)
        dirty = li.is_dirty_tree(repo_dir)
        active = [r for r in self.registry.active_loops()
                  if r.loop_id != self.loop_id]
        decision = li.decide_strategy(
            isolation_cfg, dirty_tree=dirty, active_loops=active,
            target_branch=target_branch)

        # The strategy actually USED: an explicit human-confirmed override wins;
        # else the charter-default BASELINE (pre-authorized in the charter) — NOT
        # the escalated recommendation, which needs confirmation.
        if self.isolation_strategy is not None:
            chosen, confirmed_via = self.isolation_strategy, "human_supplied"
        else:
            chosen, confirmed_via = decision.strategy, "charter_default"

        # Recommend (don't auto-apply) an unconfirmed escalation.
        if decision.escalated and self.isolation_strategy is None:
            self._write_checkpoint(
                "loop_isolation_recommendation", self.state.subsprint_id,
                context_md=(
                    f"Loop Ingress RECOMMENDS isolation strategy "
                    f"`{decision.recommendation}` over the charter default "
                    f"`{decision.strategy}`: {decision.reason}. Per Constitution "
                    f"§1.7-D the engine does NOT unilaterally escalate — it is "
                    f"proceeding on the pre-authorized default `{chosen}`. To "
                    f"adopt the recommendation, re-run this loop with the "
                    f"confirmed strategy (isolation_strategy)."),
                options_md=(f"- adopt_{decision.recommendation}\n"
                            f"- keep_{decision.strategy}\n- abort"))
            self._audit("loop_isolation_recommendation",
                        {"recommendation": decision.recommendation,
                         "default": decision.strategy,
                         "triggers": list(decision.triggers),
                         "reason": decision.reason})

        # Git side effect: create/switch the context (no-op for current_branch).
        handle = li.setup_context(
            chosen, repo_dir=repo_dir, loop_id=self.loop_id,
            worktree_root=isolation_cfg.get("worktree_root"))
        self.context_handle = handle
        self.registry.register(
            self.loop_id, handle.strategy, handle.branch,
            handle.work_dir if handle.strategy == li.STRATEGY_NEW_WORKTREE else None,
            ts=self.clock())
        self._audit("loop_ingress", {
            "strategy": handle.strategy,
            "recommendation": decision.recommendation,
            "escalated": decision.escalated,
            "confirmed_via": confirmed_via,
            "triggers": list(decision.triggers),
            "branch": handle.branch,
            "target_branch": target_branch,
            "work_dir": (os.path.relpath(handle.work_dir, repo_dir)
                         if handle.work_dir != repo_dir else "."),
        })

    def _loop_reattach_ingress(self) -> None:
        """On RESUME: reconstruct the registry + context handle from the existing
        registry record WITHOUT any git mutation (the branch/worktree already
        exists from the original loop start). No-op when ingress is off or the
        loop was never registered. ``base_ref`` is not persisted in the registry,
        so the reattached handle leaves it None (cleanup's change check then fails
        safe — see loop_ingress.context_has_changes)."""
        if not self._ingress_enabled():
            return
        self.registry = li.LoopRegistry(os.path.join(self.repo_dir, ".orchestrator"))
        rec = self.registry.get(self.loop_id)
        if rec is None:
            return
        work_dir = rec.worktree or self.repo_dir
        self.context_handle = li.ContextHandle(
            work_dir=work_dir, branch=rec.branch, strategy=rec.strategy,
            repo_dir=self.repo_dir,
            created=(rec.strategy != li.STRATEGY_CURRENT_BRANCH),
            base_ref=None)

    def _loop_close_ingress(self) -> None:
        """At a SUCCESSFUL terminal state (advance / done): mark the loop done in
        the registry and dispose of an isolated branch/worktree per the charter's
        ``cleanup_policy``.

        A HALTED loop is NOT closed — it is paused for human resolution, keeps its
        working context, and stays ``active`` in the registry so a concurrent loop
        still detects the collision. ``merged`` cannot be verified inside a batch
        loop, so it is False (conservative: ``remove_if_merged`` then keeps the
        context for the human). ``changed`` is computed safely (commits-ahead OR
        dirty tree) so ``remove_if_unchanged`` never discards real work. No-op
        when ingress is off."""
        if not self._ingress_enabled() or self.context_handle is None:
            return
        assert self.state is not None
        if self.state.state not in (STATE_ADVANCE, STATE_DONE):
            return
        handle = self.context_handle
        isolation_cfg = self.charter.get("isolation") or {}
        if self.registry is not None:
            self.registry.mark_done(self.loop_id, ts=self.clock())
        changed = li.context_has_changes(handle)
        action = li.cleanup(
            handle, cleanup_policy=isolation_cfg.get("cleanup_policy"),
            merged=False, changed=changed)
        self._audit("loop_close", {
            "strategy": handle.strategy,
            "branch": handle.branch,
            "cleanup_action": action,
            "cleanup_policy": isolation_cfg.get("cleanup_policy"),
            "changed": changed,
            "final_state": self.state.state,
        })

    def _loop_fail_ingress(self, reason: str) -> None:
        """On a HARD-FAIL (GateHardFail / BudgetExceeded propagating out of the
        loop): mark the loop ``failed`` in the registry so it does not leak as
        ``active`` and spuriously collide with the next re-run. The isolated
        branch/worktree is DELIBERATELY left in place (not cleaned) so the
        partial work + audit survive as diagnostic evidence. No-op when ingress
        is off or the loop was never registered."""
        if not self._ingress_enabled() or self.registry is None:
            return
        try:
            self.registry.mark_failed(self.loop_id, ts=self.clock(),
                                      reason=reason)
        except KeyError:
            return  # never registered (e.g. failed before _loop_init_ingress)
        self._audit("loop_failed", {
            "loop_id": self.loop_id,
            "reason": reason,
            "final_state": (self.state.state if self.state else None),
        })

    # ----- P5: Loop Memory feedback at milestone close (PROPOSE-ONLY) ------- #
    def _loop_feedback(self) -> None:
        """At a successful MILESTONE close (memory enabled): read matured (L2)
        Loop-Memory entries and emit self-evolution PROPOSALS (m-memory §5 paths
        2–5) for the human.

        PROPOSE-ONLY (HARD — m-memory §1.2/§5, Constitution §1.7-D): this writes a
        feedback REPORT + a human-pending checkpoint + an audit event and NEVER
        applies a change. No-op when memory is off, the milestone didn't close, or
        the terminal state isn't a clean success (advance/done)."""
        if self.memory is None or not self._milestone_closed:
            return
        assert self.state is not None
        if self.state.state not in (STATE_ADVANCE, STATE_DONE):
            return
        if _feedback is None:  # pragma: no cover - feedback import is optional
            self._audit("memory_feedback_unavailable", {})
            return

        # Read-only: propose() never mutates the store; render_report() takes the
        # injected clock (no bare clock here → determinism preserved).
        proposals = _feedback.propose(self.memory)
        report = _feedback.render_report(proposals, ts=self.clock())
        fb_dir = os.path.join(self.run_dir, "memory-feedback")
        os.makedirs(fb_dir, exist_ok=True)
        report_path = os.path.join(fb_dir, f"{self.loop_id}.md")
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(report)
        rel_report = os.path.relpath(report_path, self.run_dir)

        by_path: dict[str, int] = {}
        for p in proposals:
            by_path[p.path] = by_path.get(p.path, 0) + 1
        recal = any(p.recalibration_required for p in proposals)
        self._audit("memory_feedback", {
            "proposal_count": len(proposals),
            "by_path": by_path,
            "recalibration_required": recal,
            "report": rel_report,
        })

        # A human-pending checkpoint ONLY when there is something to approve. The
        # human reviews the report and approves each load-bearing change; the
        # engine applies NOTHING (§1.7-D — every skill/charter/prompt edit folds
        # back to the human).
        if proposals:
            summary = ", ".join(f"{k}×{v}" for k, v in sorted(by_path.items()))
            self._write_checkpoint(
                "memory_feedback", self.state.subsprint_id,
                context_md=(
                    f"Loop Memory feedback at milestone close: {len(proposals)} "
                    f"PROPOSE-ONLY self-evolution suggestion(s) ({summary}) "
                    f"distilled from matured (L2) lessons. Nothing is applied "
                    f"automatically — review `{rel_report}` and approve each "
                    f"load-bearing change (m-memory §5; Constitution §1.7-D)."
                    + (" ⚠ Some touch the Acceptance skill → recalibration "
                       "required (Constitution §3.6)." if recal else "")),
                options_md=("- review_and_approve_selected\n"
                            "- defer\n- dismiss"))

    # ----- state-machine steps --------------------------------------------- #
    def _dev_spec_path(self) -> Optional[str]:
        """Absolute path to the OPTIONAL compact dev-prompt projection
        (``<repo>/compact/<subsprint>-dev-prompt.md``), or None when no repo is
        bound (offline / mock) OR the id is unsafe / would escape ``<repo>/compact``.

        The sub-sprint id is interpolated into a path, so it is sanitized first
        (no ``..`` / separators) and the resolved path is asserted to stay under
        ``<repo>/compact`` — an LLM-authored plan id can otherwise traverse out."""
        if not self.repo_dir:
            return None
        sid = self.state.subsprint_id
        if not self._safe_subsprint_id(sid):
            return None
        base = os.path.realpath(os.path.join(self.repo_dir, "compact"))
        path = os.path.realpath(os.path.join(base, f"{sid}-dev-prompt.md"))
        if os.path.commonpath([base, path]) != base:
            return None  # containment guard (defense-in-depth vs the id check)
        return path

    @staticmethod
    def _safe_subsprint_id(sid: Any) -> bool:
        """True iff ``sid`` is a safe identifier to interpolate into a path
        (letters/digits then ._- only; no ``..``, no path separators)."""
        return bool(_SAFE_SUBSPRINT_ID_RE.match(str(sid)))

    @staticmethod
    def _split_front_matter(text: str):
        """Split a leading YAML front-matter block → ``(front_matter_dict_or_None,
        body)``. A block counts as front-matter ONLY when the FIRST line is exactly
        ``---`` AND the fenced block parses as a YAML MAPPING — so a Markdown
        thematic break (``---``) that recurs in the body is not mistaken for it.
        Robust to a leading BOM. No well-formed front-matter ⇒ ``(None, text)``."""
        stripped = text.lstrip("﻿")
        lines = stripped.splitlines(keepends=True)
        if not lines or lines[0].strip() != "---":
            return None, text
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                try:
                    fm = yaml.safe_load("".join(lines[1:i]))
                except yaml.YAMLError:
                    fm = None
                if not isinstance(fm, dict):
                    return None, text  # not a real YAML mapping → not front-matter
                return fm, "".join(lines[i + 1:])
        return None, text  # no closing delimiter → leave as-is

    @classmethod
    def _strip_front_matter(cls, text: str) -> str:
        """Drop a leading YAML front-matter block, returning the body (doc metadata
        is not model instructions). Defense-in-depth only now: the CLI adapters
        pass the prompt on STDIN, so a leading ``---`` can no longer be mis-parsed
        as an argv option (see adapters/claude_code.py)."""
        return cls._split_front_matter(text)[1]

    # ----- Dev-spec resolution (the spec is the schema-valid decompose PLAN) -- #
    # The canonical executable Dev spec is the structured decompose-plan entry for
    # the sub-sprint; compact/<id>-dev-prompt.md is an OPTIONAL adopter-authored
    # alternative / an auditable projection. Resolution validates by CONTENT, not
    # file existence; an incomplete/ambiguous/missing spec on a LIVE run HALTS for
    # Deliver/human refinement (resumable) — it never spends a live Dev call on an
    # unbounded task, and a complete + scope-valid plan continues straight to Dev.
    def _current_subsprint_plan(self) -> Optional[dict]:
        """The structured plan entry for the current sub-sprint id (from the
        persisted decompose plan), or None (e.g. delivery_only — no decompose)."""
        sid = self.state.subsprint_id
        for s in self.state.planned_subsprints:
            if isinstance(s, dict) and str(s.get("id")) == sid:
                return s
        return None

    @staticmethod
    def _validate_subsprint_spec(spec: dict) -> list:
        """Validate a structured plan entry by CONTENT → list of problems (empty ⇒
        a complete, BOUNDED job). The bounding minimum is an objective + in-scope
        deliverables + observable exit criteria — exactly what was missing when the
        Dev got the bare 'implement sub-sprint X' prompt."""
        problems = []
        if not str(spec.get("objective") or "").strip():
            problems.append("missing/empty `objective`")
        if not [x for x in (spec.get("scope_in") or []) if str(x).strip()]:
            problems.append("missing/empty `scope_in` (in-scope deliverables)")
        if not [x for x in (spec.get("exit_criteria") or []) if str(x).strip()]:
            problems.append("missing/empty `exit_criteria` (observable close conditions)")
        return problems

    @staticmethod
    def _validate_compact_text(front_matter: Optional[dict], body: str) -> list:
        """Validate an adopter-authored compact dev-prompt by CONTENT, not mere file
        existence (a non-empty file is NOT automatically a bounded spec). The
        template's hard requirement is ``context_budget.self_contained: true``
        (Constitution §1.4-i); without it the file is not a self-contained job."""
        problems = []
        if not (body or "").strip():
            problems.append("the spec body is empty")
        cb = front_matter.get("context_budget") if isinstance(front_matter, dict) else None
        self_contained = cb.get("self_contained") if isinstance(cb, dict) else None
        if self_contained is not True:
            problems.append(
                "front-matter `context_budget.self_contained` must be `true` "
                "(Constitution §1.4-i; see templates/compact-dev-prompt.md) — the "
                "Dev spec must be a self-contained, bounded job, not a bare prompt")
        return problems

    @staticmethod
    def _project_dev_prompt(spec: dict) -> str:
        """Deterministically PROJECT a schema-valid plan entry into an executable
        Dev prompt. The plan is the normative source; this is its rendering."""
        def _section(label: str, value: Any) -> str:
            if not value:
                return ""
            if isinstance(value, (list, tuple)):
                inner = "\n".join(f"  - {x}" for x in value)
            else:
                inner = f"  {value}"
            return f"{label}:\n{inner}\n"
        sid = spec.get("id")
        parts = [
            f"You are activating as the Dev Agent for sub-sprint {sid}.\n",
            f"Objective: {spec.get('objective', '')}\n\n",
            _section("Scope IN (deliverables)", spec.get("scope_in")),
            _section("Scope OUT (explicit non-goals)", spec.get("scope_out")),
            _section("Modules you may touch", spec.get("modules")),
            _section("Fix-layers", spec.get("layers")),
            _section("Exit criteria (close conditions)", spec.get("exit_criteria")),
            _section("Depends on (must precede)", spec.get("dependencies")),
            _section("Context / load references",
                     spec.get("context") or spec.get("load_list")),
            "\nStay strictly within Scope IN and the modules listed; do NOT widen "
            "scope. If the contract cannot be satisfied without a scope change, HALT "
            "and surface a diagnostic instead of expanding scope. When done, write "
            "the handoff.\n",
        ]
        return "".join(p for p in parts if p)

    def _load_compact_file(self):
        """Read the adopter-authored compact dev-prompt → ``(front_matter, body)``
        or None when there is no repo / file / safe path. The front-matter is parsed
        (for content validation) and stripped from the body (it is doc metadata)."""
        path = self._dev_spec_path()
        if not path or not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            return None
        return self._split_front_matter(raw)

    def _maybe_project_compact_file(self, prompt: str) -> None:
        """Best-effort: write the resolved Dev spec to compact/<id>-dev-prompt.md as
        an auditable PROJECTION of the plan (the plan stays normative). Never
        clobbers an existing adopter-authored file; swallows any I/O error."""
        path = self._dev_spec_path()
        if not path or os.path.exists(path):
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            sid = self.state.subsprint_id
            # Front-matter mirrors templates/compact-dev-prompt.md so the projection
            # is itself a VALID compact source on re-read (self_contained: true), not
            # just human-readable. The normative source stays the decompose plan.
            front_matter = (
                "---\n"
                f"title: Dev prompt (engine projection) — {sid}\n"
                f"sprint_id: {sid}\n"
                "context_budget:\n"
                "  self_contained: true\n"
                "projection: true   # generated from the decompose plan; edit the plan, not this file\n"
                "---\n\n")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(front_matter + prompt)
        except OSError:
            return

    def _dev_spec_refine_halt(self, source: str, problems: list):
        """Write a Deliver/human REFINEMENT checkpoint + set STATE_HALTED (resumable
        — the loop keeps its context), then return the halt sentinel. Replaces the
        old terminal hard-fail: a missing/incomplete spec is a correctable plan gap,
        not a dead loop."""
        sid = self.state.subsprint_id
        bullets = "\n".join(f"- {p}" for p in problems)
        self._write_checkpoint(
            "dev_spec_refinement", sid,
            context_md=(
                f"The executable Dev specification for sub-sprint `{sid}` is not "
                f"usable yet (source: {source}). The loop HALTS for refinement — it "
                f"will NOT spend a live Dev call on an unbounded/ambiguous task.\n\n"
                f"Problems:\n{bullets}\n\n"
                f"Resolve by EITHER refining the Deliver decompose plan for this "
                f"sub-sprint (objective + scope_in + exit_criteria, within the signed "
                f"Gate-1 scope) OR authoring `compact/{sid}-dev-prompt.md` from "
                f"`templates/compact-dev-prompt.md` (front-matter "
                f"`context_budget.self_contained: true`). Then resume."),
            options_md=("- refine_plan_and_resume\n"
                        "- author_compact_prompt_and_resume\n- abort"))
        self.state.state = STATE_HALTED
        self._save_state()  # PERSIST the halt — a resume must NOT re-run dev_pending
        self._audit("dev_spec_refinement_halt",
                    {"subsprint_id": sid, "source": source, "problems": problems})
        return _DEV_SPEC_HALT

    def _resolve_dev_spec(self):
        """Resolve the normative executable Dev spec for the current sub-sprint.

        OFFLINE/mock (not allow_real) ⇒ None (the legacy inline prompt; the test
        suite + dry-run stay byte-identical). On a LIVE run, validate BY CONTENT, in
        priority order, sanitizing the id before ANY path use:
          1. the schema-valid decompose-plan entry (CANONICAL) → project it to an
             executable prompt (+ an auditable compact-file projection);
          2. an adopter-authored compact/<id>-dev-prompt.md (alternative source);
          3. neither ⇒ a refinement HALT.
        An incomplete/ambiguous spec at (1) or (2) HALTS for refinement rather than
        silently running, or falling through to a less-specific source."""
        if not bool(self.context.get("allow_real")):
            return None  # offline/mock → legacy inline prompt (byte-identical)
        sid = self.state.subsprint_id
        if not self._safe_subsprint_id(sid):
            return self._dev_spec_refine_halt(
                "invalid_id",
                [f"sub-sprint id {sid!r} is not a safe identifier "
                 f"(letters/digits then ._- only; no path separators)"])
        plan_spec = self._current_subsprint_plan()
        if plan_spec is not None:
            problems = self._validate_subsprint_spec(plan_spec)
            if problems:
                return self._dev_spec_refine_halt("decompose_plan", problems)
            prompt = self._project_dev_prompt(plan_spec)
            self._maybe_project_compact_file(prompt)
            return prompt
        loaded = self._load_compact_file()
        if loaded is not None:
            front_matter, body = loaded
            problems = self._validate_compact_text(front_matter, body)
            if problems:
                return self._dev_spec_refine_halt("compact_file", problems)
            return body.strip()
        return self._dev_spec_refine_halt(
            "missing",
            [f"no decompose-plan entry for `{sid}` and no "
             f"compact/{sid}-dev-prompt.md under the repo"])

    def _step_dev(self) -> None:
        # The Dev spec is resolved from the decompose plan (canonical) or an
        # adopter-authored compact prompt, validated by CONTENT. A live run with no
        # usable spec HALTS for refinement (resumable) — it never spends a live Dev
        # call on an unbounded task. Offline/mock keeps the legacy inline prompt.
        resolved = self._resolve_dev_spec()
        if resolved is _DEV_SPEC_HALT:
            return  # checkpoint written + STATE_HALTED set; the drive loop stops
        if resolved is not None:
            prompt = self._lessons_block("dev") + resolved
        else:
            prompt = (self._lessons_block("dev")
                      + f"Implement sub-sprint {self.state.subsprint_id}; "
                        f"write the handoff.")
        verdict = self._spawn(
            "dev", prompt,
            schema_key=None,  # spawn_dev's artifact IS the code+handoff, no verdict schema
        )
        self.state.history.append(STATE_DEV_PENDING)

    def _step_gate(self) -> None:
        self._run_gates()
        self.state.history.append(STATE_GATE_PENDING)

    def _step_review(self) -> dict:
        prompt = (self._lessons_block("review")
                  + f"Review sub-sprint {self.state.subsprint_id}. "
                    f"Emit a review-verdict.")
        verdict = self._spawn("review", prompt, schema_key="review")
        self.state.history.append(STATE_REVIEW_PENDING)
        return verdict

    def _step_close(self) -> dict:
        prompt = (self._lessons_block("deliver")
                  + f"Close sub-sprint {self.state.subsprint_id}. "
                    f"Emit a deliver-close-verdict.")
        verdict = self._spawn("deliver", prompt, schema_key="close")
        self.state.history.append(STATE_CLOSE_PENDING)
        return verdict

    # ----- P6.1: full_chain_guided bootstrap pre-states -------------------- #
    # research_pending → gate1_pending → decompose_pending, driven BEFORE the
    # existing delivery loop and ONLY when loop_mode == full_chain_guided. Like
    # _run_acceptance these are out-of-band (not in LOOP_ORDER): _drive() re-enters
    # them on resume. The single most-important invariant (req 3) — the engine
    # NEVER auto-confirms Gate 1 — is enforced in _step_gate1: there is NO code
    # path that proceeds past gate1 without an explicit human `sign` from the
    # injected gate_resolver; a missing/None resolver, or any non-sign choice,
    # HALTS.
    def _guided_enabled(self) -> bool:
        """True iff this run is in full_chain_guided mode. Every pre-state path is
        gated behind this so delivery_only is byte-identical to the pre-P6.1
        driver (req: delivery_only must stay byte-identical)."""
        return self.loop_mode == LOOP_MODE_FULL_CHAIN_GUIDED

    def _intent_contract_confirmed(self) -> bool:
        """The brief is signed UPFRONT when charter.intent_contract.confirmed_by_human
        is true (skip rule, req 6). Absent/false ⇒ Research+Gate-1 run."""
        ic = self.charter.get("intent_contract") or {}
        return bool(ic.get("confirmed_by_human"))

    def _supplied_sequence(self) -> list[str]:
        """The charter's pre-supplied approved sub-sprint sequence
        (autonomy.approved_scope.subsprint_sequence), or []. A non-empty sequence
        supplied upfront skips decompose_pending (skip rule, req 6)."""
        scope = self.autonomy.get("approved_scope") or {}
        return list(scope.get("subsprint_sequence") or [])

    def _layers_allowed(self) -> list[str]:
        """The human-signed envelope's allowed Δ-9 layers (or [])."""
        scope = self.autonomy.get("approved_scope") or {}
        return list(scope.get("layers_allowed") or [])

    def _step_research(self) -> None:
        """research_pending — draft the milestone brief (an ARTIFACT, not a verdict
        schema). Skipped when the brief is already signed upfront. The drafted
        artifact reference is persisted (brief_draft_ref) and a research_brief_drafted
        audit event is emitted.

        A brief is a DOC, so the spawn uses schema_key=None (artifact handling),
        exactly like _step_dev — _spawn still records the artifact spawn + audit."""
        assert self.state is not None
        self.state.state = STATE_RESEARCH_PENDING
        if STATE_RESEARCH_PENDING not in self.state.history:
            self.state.history.append(STATE_RESEARCH_PENDING)
        self._save_state()
        if self.state.brief_signed:
            # Signed brief supplied upfront → research is skipped (no draft, no
            # spawn). Record the skip so the audit trail is explicit.
            self._audit("research_skipped",
                        {"reason": "brief signed upfront "
                                   "(intent_contract.confirmed_by_human)"})
            return
        prompt = (self._lessons_block("research")
                  + f"Draft the milestone brief for mission "
                    f"{(self.charter.get('mission') or {}).get('id')}: state the "
                    f"intent contract (problem, in/out of scope, closure contract) "
                    f"so the customer can sign off at Gate 1. Do NOT widen beyond "
                    f"the stated intent — scope widening needs the Gate-1 human "
                    f"checkpoint.")
        # ARTIFACT spawn (a brief is a doc, NOT a verdict) → schema_key=None.
        self._spawn("research", prompt, schema_key=None)
        # The drafted brief is an artifact under the run dir; we persist a stable
        # reference (deterministic — no clock/uuid; the loop_id + subsprint anchor
        # it) so resume + Gate-1 context point at the same draft.
        ref = f"docs/briefs/{self.state.subsprint_id}__brief.md"
        self.state.brief_draft_ref = ref
        self._save_state()
        self._audit("research_brief_drafted", {"brief_ref": ref})

    def _step_gate1(self) -> dict:
        """gate1_pending — the CUSTOMER Gate-1 sign-off. Builds a context (drafted
        brief ref + proposed approved scope), writes a customer_gate1_signoff
        checkpoint, then consults the INJECTED gate_resolver. The engine NEVER
        auto-signs (req 3): the only path that proceeds is an explicit human
        choice == "sign" returned by the resolver.

        Returns a small status dict {"status": "signed"|"halted"} so the driver
        knows whether to continue to decompose or stop. A missing resolver / a
        None return / a non-sign choice all stop the driver (HALT for async
        resolution, REJECT for rework, ABORT to STATE_HALTED)."""
        assert self.state is not None
        self.state.state = STATE_GATE1_PENDING
        if STATE_GATE1_PENDING not in self.state.history:
            self.state.history.append(STATE_GATE1_PENDING)
        self._save_state()

        scope = self.autonomy.get("approved_scope") or {}
        ctx = {
            "brief_ref": self.state.brief_draft_ref,
            "mission": (self.charter.get("mission") or {}).get("id"),
            "proposed_approved_scope": {
                "modules_in_scope": self._modules_in_scope(),
                "layers_allowed": self._layers_allowed(),
                "subsprint_sequence": self._supplied_sequence(),
                "explicitly_out_of_scope":
                    list(scope.get("explicitly_out_of_scope") or []),
            },
        }
        options = ["sign", "reject", "abort"]
        # The human-pending checkpoint is written FIRST so the decision is always
        # recorded in the inbox (whether resolved now or async).
        cp_path = self._write_checkpoint(
            "customer_gate1_signoff", self.state.subsprint_id,
            context_md=(
                f"Customer Gate 1 sign-off for mission `{ctx['mission']}`.\n\n"
                f"Drafted brief: `{ctx['brief_ref']}`.\n\n"
                f"Proposed approved scope:\n"
                f"- modules_in_scope: {ctx['proposed_approved_scope']['modules_in_scope']}\n"
                f"- layers_allowed: {ctx['proposed_approved_scope']['layers_allowed']}\n"
                f"- subsprint_sequence: {ctx['proposed_approved_scope']['subsprint_sequence']}\n"
                f"- explicitly_out_of_scope: "
                f"{ctx['proposed_approved_scope']['explicitly_out_of_scope']}\n\n"
                f"The engine does NOT auto-sign (Constitution §1.7-D): it proceeds "
                f"to milestone decomposition ONLY on an explicit human `sign`."),
            options_md="- sign\n- reject\n- abort")

        # Consult the injected resolver — the HUMAN's voice. NEVER fabricate a
        # sign: a missing resolver OR a None return HALTS for async resolution.
        decision = None
        if self.gate_resolver is not None:
            decision = self.gate_resolver("customer_gate1", ctx, options)

        if not decision or decision.get("choice") not in options:
            # No human decision available (resolver absent, returned None, or an
            # unrecognized choice) → HALT for async resolution. The state stays
            # gate1_pending so resume re-consults the resolver.
            self._audit("customer_gate1_halt",
                        {"reason": "no_resolver_decision",
                         "brief_ref": self.state.brief_draft_ref,
                         "checkpoint": os.path.relpath(cp_path, self.run_dir)})
            self.state.state = STATE_GATE1_PENDING
            self._save_state()
            return {"status": "halted"}

        choice = decision.get("choice")
        note = str(decision.get("note") or "")
        resolver = str(decision.get("resolver") or "human")

        if choice == "sign":
            # The ONLY path that proceeds. Record the decision into the checkpoint
            # + audit; set RunState.brief_signed True.
            self._record_gate_decision(cp_path, "sign", note, resolver)
            self.state.brief_signed = True
            self._save_state()
            self._audit("customer_gate1_signed",
                        {"resolver": resolver, "note": note,
                         "brief_ref": self.state.brief_draft_ref})
            return {"status": "signed"}

        if choice == "reject":
            # The brief needs rework — HALT (the brief is NOT signed; no proceed).
            self._record_gate_decision(cp_path, "reject", note, resolver)
            self.state.state = STATE_GATE1_PENDING
            self._save_state()
            self._audit("customer_gate1_rejected",
                        {"resolver": resolver, "note": note,
                         "brief_ref": self.state.brief_draft_ref})
            return {"status": "halted"}

        # choice == "abort" → terminal halt.
        self._record_gate_decision(cp_path, "abort", note, resolver)
        self.state.state = STATE_HALTED
        self._save_state()
        self._audit("customer_gate1_aborted",
                    {"resolver": resolver, "note": note,
                     "brief_ref": self.state.brief_draft_ref})
        return {"status": "halted"}

    def _record_gate_decision(self, checkpoint_path: str, choice: str,
                              note: str, resolver: str) -> None:
        """Re-write the Gate-1 checkpoint's front-matter + decision section to
        record the human's resolved decision (choice/note/resolver). Pure file IO;
        the clock is injected via self.clock()."""
        resolved_at = self.clock()
        with open(checkpoint_path, "r", encoding="utf-8") as fh:
            body = fh.read()
        body = body.replace("decision: pending", f"decision: {choice}")
        body = body.replace("resolved_at: null", f"resolved_at: {resolved_at}")
        body = body.replace("resolver: null", f"resolver: {resolver}")
        body = body.replace(
            "<human writes; orchestrator picks up>",
            f"choice: {choice}\nresolver: {resolver}\nnote: {note}")
        with open(checkpoint_path, "w", encoding="utf-8") as fh:
            fh.write(body)

    def _step_decompose(self) -> None:
        """decompose_pending — spawn Deliver to decompose the SIGNED milestone into
        an ordered sub-sprint plan (validated against deliver-plan-verdict.schema).
        Extracts sub_sprints[], sets RunState.planned_sequence + the charter's
        approved subsprint_sequence (if not supplied), runs the scope-expansion
        guard, then audits milestone_decomposed. Skipped when a non-empty sequence
        was supplied upfront.

        Returns nothing; on a scope-expansion violation it sets STATE_HALTED."""
        assert self.state is not None
        self.state.state = STATE_DECOMPOSE_PENDING
        if STATE_DECOMPOSE_PENDING not in self.state.history:
            self.state.history.append(STATE_DECOMPOSE_PENDING)
        self._save_state()

        supplied = self._supplied_sequence()
        if supplied:
            # Plan supplied upfront → decompose is skipped; the supplied sequence
            # IS the plan. Record the skip + reflect it into RunState.
            self.state.planned_sequence = list(supplied)
            self.state.milestone_planned = True
            self._save_state()
            self._audit("decompose_skipped",
                        {"reason": "subsprint_sequence supplied upfront",
                         "subsprint_sequence": list(supplied)})
            return

        prompt = (self._lessons_block("deliver")
                  + f"Decompose the SIGNED milestone brief "
                    f"(`{self.state.brief_draft_ref}`) into an ordered list of "
                    f"sub-sprints. Emit a deliver-plan-verdict: each sub_sprint "
                    f"declares id, objective, scope_in, scope_out, modules, layers, "
                    f"exit_criteria. Stay within the human-signed approved scope.")
        verdict = self._spawn("deliver", prompt, schema_key="deliver_plan")
        sub_sprints = list(verdict.get("sub_sprints") or [])
        seq = [str(s.get("id")) for s in sub_sprints if isinstance(s, dict)]
        self.state.planned_sequence = seq
        # Persist the FULL structured specs: they are the canonical executable
        # Dev-spec source (resolved per sub-sprint in _resolve_dev_spec), not just
        # the ordered ids. compact/<id>-dev-prompt.md becomes an OPTIONAL projection.
        self.state.planned_subsprints = [s for s in sub_sprints if isinstance(s, dict)]

        # Make _milestone_complete (terminality) see the plan: set the charter's
        # approved subsprint_sequence from the plan when none was supplied.
        scope = self.autonomy.setdefault("approved_scope", {})
        if not scope.get("subsprint_sequence"):
            scope["subsprint_sequence"] = list(seq)
        self.state.milestone_planned = True
        self._save_state()

        # SCOPE-EXPANSION GUARD (req 8): the union of every sub_sprint's modules +
        # layers must stay within the human-signed envelope. Any out-of-envelope
        # module/layer → checkpoint + audit + HALT (do NOT proceed to delivery).
        if self._scope_expansion_halts(sub_sprints):
            return

        self._audit("milestone_decomposed",
                    {"subsprint_count": len(sub_sprints),
                     "subsprint_sequence": list(seq)})

    def _scope_expansion_guard(self, sub_sprints: Sequence[dict]) -> dict:
        """Pure: compute the union of plan modules+layers vs the human-signed
        envelope (approved_scope.{modules_in_scope, layers_allowed}). Returns
        {"modules_out": [...], "layers_out": [...], "envelope_unset": bool}.

        If BOTH envelope dimensions are empty/absent, the plan DEFINES scope (no
        expansion possible) → envelope_unset True, no out-of-envelope items."""
        plan_modules: set[str] = set()
        plan_layers: set[str] = set()
        for s in sub_sprints:
            if not isinstance(s, dict):
                continue
            plan_modules.update(str(m) for m in (s.get("modules") or []))
            plan_layers.update(str(layer) for layer in (s.get("layers") or []))
        env_modules = set(self._modules_in_scope())
        env_layers = set(self._layers_allowed())
        envelope_unset = not env_modules and not env_layers
        if envelope_unset:
            return {"modules_out": [], "layers_out": [], "envelope_unset": True}
        # The envelope is PRESENT (at least one dimension is set), so BOTH
        # dimensions are constrained: an EMPTY dimension permits NOTHING, not
        # everything. (A human who signs modules_in_scope but leaves
        # layers_allowed empty has authorized no new layers — any plan layer is
        # then out of envelope.) Per-dimension "empty ⇒ unconstrained" would be a
        # silent scope-widening past Gate-1 — the whole-envelope-unset case is the
        # only "plan defines scope" path, handled above.
        modules_out = sorted(plan_modules - env_modules)
        layers_out = sorted(plan_layers - env_layers)
        return {"modules_out": modules_out, "layers_out": layers_out,
                "envelope_unset": False}

    def _scope_expansion_halts(self, sub_sprints: Sequence[dict]) -> bool:
        """Apply the scope-expansion guard side effects. Returns True (and sets
        STATE_HALTED) when the plan widened beyond the signed envelope; False when
        it is in-envelope (or the envelope is unset — the plan then defines scope,
        with an audit note). req 8."""
        assert self.state is not None
        guard = self._scope_expansion_guard(sub_sprints)
        if guard["envelope_unset"]:
            # No signed envelope to widen → the plan defines scope. Emit a note +
            # proceed (no expansion is possible).
            self._audit("scope_envelope_unset",
                        {"subsprint_count": len(list(sub_sprints))})
            return False
        if guard["modules_out"] or guard["layers_out"]:
            self._write_checkpoint(
                "post_gate1_scope_expansion", self.state.subsprint_id,
                context_md=(
                    f"The milestone decomposition widened beyond the human-signed "
                    f"Gate-1 envelope. The plan touches module(s)/layer(s) NOT in "
                    f"approved_scope:\n\n"
                    f"- modules out of envelope: {guard['modules_out']}\n"
                    f"- layers out of envelope: {guard['layers_out']}\n\n"
                    f"Per delivery-loop §4.2.4/§4.2.5 the engine HALTS — it does "
                    f"NOT widen scope mid-run. A human must confirm the expansion "
                    f"(widen approved_scope → re-run) or narrow the plan."),
                options_md=("- widen_approved_scope\n- narrow_plan\n- abort"))
            self._audit("post_gate1_scope_expansion",
                        {"modules_out": guard["modules_out"],
                         "layers_out": guard["layers_out"]})
            self.state.state = STATE_HALTED
            self._save_state()
            return True
        return False

    def _drive_guided_prestates(self) -> bool:
        """Drive the full_chain_guided pre-states (research → gate1 → decompose)
        in order, honoring skip rules + halts. Returns True to PROCEED into the
        delivery loop (all pre-states cleared), False to STOP (a pre-state halted
        — state already set + saved by the step).

        Resume-safe: each step is idempotent and re-enterable. The driver re-enters
        here from _drive() at whichever pre-state was persisted; already-completed
        pre-states (brief_signed / milestone_planned) fast-path past."""
        assert self.state is not None

        # research_pending — draft the brief unless one is signed upfront OR a
        # draft already exists (resume after a Gate-1 halt: the brief was drafted
        # on the first pass, so we do NOT re-draft — we go straight to re-consult
        # the resolver at gate1, per the spec's resume-at-gate1 rule).
        if not self.state.brief_signed and self.state.brief_draft_ref is None:
            self._step_research()

        # gate1_pending — the sign-off. Skipped when the brief is already signed
        # (upfront via intent_contract, OR by a prior resolved Gate-1 sign on a
        # resume). Otherwise consult the resolver; NEVER auto-sign.
        if not self.state.brief_signed:
            result = self._step_gate1()
            if result.get("status") != "signed":
                return False  # halted (no resolver / reject / abort) — do not proceed

        # decompose_pending — build the sub-sprint plan unless supplied upfront /
        # already planned. The guard may HALT here (scope expansion).
        if not self.state.milestone_planned:
            self._step_decompose()
            if self.state.state == STATE_HALTED:
                return False  # scope-expansion guard halted the run

        # All pre-states cleared → enter the delivery loop for the FIRST sub-sprint.
        seq = self.state.planned_sequence or self._supplied_sequence()
        if seq:
            self.state.subsprint_id = seq[0]
        return True

    # ----- the loop -------------------------------------------------------- #
    def run(self, subsprint_id: Optional[str] = None, *, resume: bool = False) -> RunState:
        """Drive one sub-sprint end-to-end (dev→gate→review→close→advance).

        ``resume=True`` reloads state.json and continues from the persisted state
        (§4.5). Otherwise a fresh run starts in idle for ``subsprint_id``.

        Returns the final RunState. Raises GateHardFail (incl. BudgetExceeded) on
        a hard-fail — having already written the checkpoint + audit event.
        """
        if resume:
            loaded = self._load_state()
            if loaded is None:
                raise FileNotFoundError(
                    f"resume requested but no state.json at {self.state_path}")
            self.state = loaded
            self._audit("loop_resume", {"from_state": self.state.state,
                                        "subsprint_id": self.state.subsprint_id})
            # P4: re-attach the (already-created) git context + registry record
            # WITHOUT any git mutation — the branch/worktree already exists.
            self._loop_reattach_ingress()
        else:
            if subsprint_id is None:
                raise ValueError("subsprint_id required for a fresh run")
            self.state = RunState(loop_id=self.loop_id, subsprint_id=subsprint_id)
            # P6.1: stamp the run's mode + the upfront skip-rule flags onto the
            # RunState (persisted for resume). delivery_only leaves these at their
            # defaults, so the state.json + run() path are byte-identical to before.
            self.state.loop_mode = self.loop_mode
            self.state.brief_signed = (self._guided_enabled()
                                       and self._intent_contract_confirmed())
            self._audit("loop_start", {
                "charter_mission": (self.charter.get("mission") or {}).get("id"),
                "subsprint_id": subsprint_id,
                "autonomy": self.autonomy.get("level", "human_in_the_loop"),
                "loop_mode": self.loop_mode,
                "context": self.context,
            })
            # P4: Loop Ingress — decide the isolation strategy, set up the git
            # working context, register the loop. No-op when repo_dir is None.
            self._loop_init_ingress()

            # P6.1: full_chain_guided — drive the research → gate1 → decompose
            # pre-states BEFORE the delivery loop. Each may HALT (no resolver /
            # reject / abort / scope expansion); on a halt we stop here (state is
            # already set + saved by the step). delivery_only skips this entirely.
            if self._guided_enabled():
                self._save_state()
                self._audit("guided_bootstrap_start",
                            {"loop_mode": self.loop_mode,
                             "brief_signed_upfront": self.state.brief_signed,
                             "subsprint_sequence_supplied":
                                 bool(self._supplied_sequence())})
                if not self._drive_guided_prestates():
                    # A pre-state halted (or aborted) → close ingress (no-op for a
                    # non-terminal state) + return the halted/paused RunState.
                    self._save_state()
                    self._loop_close_ingress()
                    return self.state

            self.state.state = STATE_DEV_PENDING

        self._save_state()
        # A GateHardFail (incl. BudgetExceeded) must NOT leave the loop registered
        # as ``active`` — mark it failed (keeping the branch/audit for diagnosis),
        # then re-raise so the caller still sees the hard-fail.
        try:
            self._drive()
        except GateHardFail as exc:
            self._loop_fail_ingress(str(exc))
            raise
        # P4: close the loop (mark_done + cleanup) ONLY on a successful terminal
        # state — a halted loop keeps its context for human resolution.
        self._loop_close_ingress()
        # P5: propose-only Loop Memory feedback at a successful milestone close.
        self._loop_feedback()
        return self.state

    def _drive(self) -> None:
        """Execute remaining states in linear order from self.state.state."""
        assert self.state is not None
        # Find resume index in the linear order; advance/done short-circuit.
        order = LOOP_ORDER
        # P6.1: Resume INTO a full_chain_guided pre-state (research/gate1/decompose).
        # These are out-of-band (not in LOOP_ORDER), like acceptance below: re-enter
        # the bootstrap, which is idempotent + honors the persisted progress
        # (brief_signed / milestone_planned). If it clears the pre-states it falls
        # through into the delivery loop for the first sub-sprint; on a re-halt
        # (resolver still says no, etc.) it returns and the state stays put.
        if self.state.state in GUIDED_PRESTATE_ORDER:
            if not self._drive_guided_prestates():
                return  # still halted at a pre-state (e.g. resolver still None)
            self.state.state = STATE_DEV_PENDING
            self._save_state()
        # Resume INTO acceptance: if a prior process died mid-acceptance, re-enter
        # the acceptance state (idempotent: re-runs the F5 eval + spawn). The
        # acceptance state is out-of-band (not in LOOP_ORDER), so handle it first.
        if self.state.state == STATE_ACCEPTANCE_PENDING:
            self._run_acceptance()
            return
        if self.state.state in (STATE_ADVANCE, STATE_DONE, STATE_HALTED):
            return
        try:
            start = order.index(self.state.state)
        except ValueError:
            # idle or unknown -> start at the beginning of the loop.
            start = 0
            self.state.state = order[0]

        review_verdict: Optional[dict] = None
        for st in order[start:]:
            self.state.state = st
            self._check_budget()
            self._save_state()
            if st == STATE_DEV_PENDING:
                self._step_dev()
                if self.state.state == STATE_HALTED:
                    return  # dev-spec refinement halt — do not proceed to the gate
            elif st == STATE_GATE_PENDING:
                self._step_gate()
            elif st == STATE_REVIEW_PENDING:
                review_verdict = self._step_review()
                decision = review_verdict.get("decision")
                if decision == "fix_required":
                    self._handle_fix_required(review_verdict)
                    return  # _handle_fix_required sets terminal/loop state
                if decision == "out_of_scope_review":
                    self._handle_out_of_scope_review(review_verdict)
                    return  # halts for human resolution — must NOT advance
            elif st == STATE_CLOSE_PENDING:
                close_verdict = self._step_close()
                self._handle_close(close_verdict)
                return
            self._save_state()

    # ----- P3 INTEGRATION 1: Loop Controller termination authority --------- #
    def _auto_fix_cfg(self) -> dict:
        """charter.autonomy.auto_pass_rules.auto_fix_iteration (or {}).

        Absence ⇒ {} ⇒ NOT enabled ⇒ the existing P2/HITL human-confirm path
        (backward-compat). Constitution §1.7-D: this only enables the dev↔review
        auto-iteration loop; it NEVER auto-passes Acceptance or a human gate."""
        return ((self.autonomy.get("auto_pass_rules") or {})
                .get("auto_fix_iteration") or {})

    def _max_fix_rounds(self) -> Optional[int]:
        """The round cap fed to the controller: budget.max_fix_rounds_total
        takes precedence (§4.2.2 hard budget), else auto_fix_iteration.max_rounds
        (§4.4). None ⇒ no round cap from the controller (budget guard may still
        apply via _check_budget)."""
        cap = self.budget.get("max_fix_rounds_total")
        if isinstance(cap, int):
            return cap
        m = self._auto_fix_cfg().get("max_rounds")
        return m if isinstance(m, int) else None

    def _budget_cap(self) -> Optional[float]:
        """Generic spend cap fed to the controller: charter.budget.max_api_usd
        (the §4.2.2 budget unit). None / absent ⇒ budget guard disabled in the
        controller. A 0 cap is a real cap (mock runs spend 0.0, so 0 never trips
        on its own — `spent >= cap` with spent=0,cap=0 IS exhausted, so we treat
        a 0 cap as 'no spend allowed' ONLY when a positive spend exists). We keep
        it simple: pass the number through; the controller compares spent>=cap."""
        cap = self.budget.get("max_api_usd")
        if isinstance(cap, (int, float)) and cap > 0:
            return float(cap)
        return None

    @staticmethod
    def _finding_keys(review_verdict: dict) -> list[str]:
        """Stable dedup keys for this round's findings (caller-owned identity,
        per loop_controller's contract). A finding's id is its identity; absent
        an id we fall back to (layer|first-evidence) so two reports of the same
        issue collapse. Pure."""
        out: list[str] = []
        for f in review_verdict.get("findings") or []:
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            if fid:
                out.append(str(fid))
                continue
            ev = f.get("evidence") or []
            anchor = ev[0] if ev else ""
            out.append(f"{f.get('layer', '')}|{anchor}")
        return out

    @staticmethod
    def _worst_severity(review_verdict: dict) -> Optional[str]:
        """The most-severe finding label this round (P0 worst). None when no
        findings carry a severity (no actionable severity signal)."""
        worst: Optional[str] = None
        for f in review_verdict.get("findings") or []:
            if not isinstance(f, dict):
                continue
            sev = f.get("severity")
            if lc.severity_rank(sev) is None:
                continue
            if worst is None or lc.severity_rank(sev) < lc.severity_rank(worst):
                worst = str(sev).upper()
        return worst

    def _build_loop_state(self, review_verdict: dict,
                          new_keys: Sequence[str]) -> "lc.LoopState":
        """Assemble the LoopState the controller decides over, from RunState +
        charter + this verdict. The driver tracks the cross-round fields
        (fix_round, rounds_since_new_finding, budget_spent, seen keys); the
        controller only reads them."""
        assert self.state is not None
        afi = self._auto_fix_cfg()
        return lc.LoopState(
            last_verdict=review_verdict.get("decision"),
            fix_round=self.state.fix_round,
            max_fix_rounds=self._max_fix_rounds(),
            findings_this_round=len(review_verdict.get("findings") or []),
            new_finding_keys=list(new_keys),
            rounds_since_new_finding=self.state.rounds_since_new_finding,
            dry_stop_threshold=afi.get("dry_stop_threshold"),
            budget_spent=self.state.budget_spent,
            budget_cap=self._budget_cap(),
            worst_severity=self._worst_severity(review_verdict),
            severity_ceiling=afi.get("only_if_findings_severity_at_most"),
        )

    def _record_fix_lesson(self, review_verdict: dict, decision: "lc.Decision",
                           new_keys: Sequence[str]) -> None:
        """P3 INTEGRATION 2 (close/finding write): record a MINIMAL, generalizable
        lesson for the fix-loop finding so recurring patterns mature L1→L2 at
        n≥2. No-op when memory is disabled. The key is a STABLE finding pattern
        (layer-anchored) so the same class of finding dedups across loops; the
        body is generalizable (the memory guard rejects case-specific
        input→output, so we keep it abstract)."""
        if self.memory is None:
            return
        assert self.state is not None
        worst = self._worst_severity(review_verdict) or "P?"
        # Per-finding-layer keys keep the lesson generalizable + dedup-stable.
        layers = sorted({(f.get("layer") or "unknown")
                         for f in (review_verdict.get("findings") or [])
                         if isinstance(f, dict)}) or ["unknown"]
        modules = self._modules_in_scope()
        for layer in layers:
            key = f"review fix_required at {layer} layer"
            body = (f"A `fix_required` review recurred at the `{layer}` fix-layer "
                    f"(worst severity ~{worst}). When working this layer, "
                    f"pre-check the prior failure class before handing off — "
                    f"recurring rework here signals a missing guard at that layer.")
            try:
                self.memory.record_observation(
                    key,
                    ts=self.clock(),
                    loop_id=self.loop_id,
                    type="failure",
                    scope={"role": ["review", "dev"],
                           "module": modules,
                           "layer": [layer]},
                    body=body,
                )
            except _MemoryError:
                # A guard/shape rejection MUST NOT crash the delivery loop; the
                # lesson is simply not stored (recorded in audit below).
                self._audit("memory_record_rejected", {"key": key, "layer": layer})
                continue
            self._audit("memory_observation_recorded",
                        {"key": key, "layer": layer,
                         "controller_reason": decision.reason})

    def _handle_fix_required(self, review_verdict: dict) -> None:
        """Review said fix_required. The Loop Controller (loop_controller.decide)
        is now the TERMINATION AUTHORITY: the driver builds a LoopState from
        RunState + charter + the verdict and maps the controller's action to a
        side effect. Constitution §1.7-D / OQ-B: the controller NEVER auto-confirms
        an authority gate — `continue` only auto-iterates the dev↔review loop when
        charter.autonomy.auto_pass_rules.auto_fix_iteration.enabled is true AND
        within bounds; otherwise the existing P2/HITL human-confirm checkpoint +
        halt fires UNCHANGED."""
        assert self.state is not None
        verdict = review_verdict
        while True:
            self.state.fix_round += 1

            # Cross-round dry-stop bookkeeping (the controller READS it, the
            # driver maintains it). A finding key is NEW iff unseen so far.
            keys = self._finding_keys(verdict)
            new_keys = [k for k in keys if k not in self.state.seen_finding_keys]
            if new_keys:
                self.state.rounds_since_new_finding = 0
                for k in new_keys:
                    self.state.seen_finding_keys.append(k)
            else:
                self.state.rounds_since_new_finding += 1
            self._save_state()

            self._audit("review_fix_required",
                        {"blocking_count": verdict.get("blocking_count"),
                         "fix_round": self.state.fix_round,
                         "new_finding_keys": list(new_keys),
                         "rounds_since_new_finding":
                             self.state.rounds_since_new_finding})

            # Close/finding write: record a generalizable lesson (gated on memory).
            decision = lc.decide(self._build_loop_state(verdict, new_keys))
            self._audit("controller_decision",
                        {"action": decision.action, "reason": decision.reason,
                         "detail": decision.detail, "fix_round": self.state.fix_round})
            self._record_fix_lesson(verdict, decision, new_keys)

            # --- map decide() action → driver side effect --------------------- #
            if decision.action == lc.ACTION_ADVANCE:
                # A fix round that came back clean — leave the fix loop. (Reached
                # only if a re-review returned a clean verdict below.)
                self.state.state = STATE_ADVANCE
                self._save_state()
                return

            if decision.action == lc.ACTION_HALT:
                # budget / max_rounds / converged_dry → checkpoint (reason in the
                # body) + halt. BUDGET still also flows through _check_budget for
                # the hard BudgetExceeded raise when a fix-round cap is set.
                self._halt_checkpoint(
                    "loop_controller_halt", decision,
                    context_extra=(
                        f"The Loop Controller halted the fix loop: "
                        f"`{decision.reason}` — {decision.detail}."))
                self.state.state = STATE_HALTED
                self._save_state()
                # A round-cap halt must still surface as the deterministic
                # BudgetExceeded gate_hard_fail when budget.max_fix_rounds_total
                # is the binding cap (backward-compat with _check_budget's raise).
                if decision.reason in (lc.REASON_MAX_ROUNDS, lc.REASON_BUDGET):
                    self._check_budget()
                return

            if decision.action == lc.ACTION_ESCALATE:
                # severity over ceiling → needs-human checkpoint + halt.
                self._halt_checkpoint(
                    "loop_controller_escalate", decision,
                    context_extra=(
                        f"The Loop Controller escalated to a human: "
                        f"`{decision.reason}` — {decision.detail}. Auto-fix is not "
                        f"permitted above the configured severity ceiling."),
                    needs_human=True)
                self.state.state = STATE_HALTED
                self._save_state()
                return

            # decision.action == lc.ACTION_CONTINUE
            if not self._auto_fix_cfg().get("enabled"):
                # BACKWARD-COMPAT (UNCHANGED P2/HITL): auto-fix not enabled ⇒ the
                # controller's `continue` is NOT auto-confirmed. Write the existing
                # fix_required human-confirm checkpoint + halt, exactly as before.
                self._check_budget()  # over-cap still raises BudgetExceeded here
                self._write_checkpoint(
                    "gate_hard_fail", self.state.subsprint_id,
                    context_md=(
                        f"Code Reviewer returned fix_required "
                        f"({verdict.get('blocking_count')} blocking) on fix_round "
                        f"{self.state.fix_round}. Auto-fix iteration is not enabled "
                        f"(human_in_the_loop). Loop Controller said `continue` but "
                        f"§1.7-D forbids auto-confirming a human gate — routing to "
                        f"the human."),
                    options_md="- deliver_fix_iteration\n- abort",
                )
                self.state.state = STATE_HALTED
                self._save_state()
                return

            # AUTO-FIX ENABLED + within bounds → spawn another fix round: re-enter
            # the dev → gate → review steps, then loop on the new verdict. This is
            # the ONLY auto-iteration the controller authorizes (§1.7-D: it never
            # auto-passes Acceptance or a human checkpoint).
            self._check_budget()  # hard cap still guards the auto-iteration
            self._audit("auto_fix_round_spawned",
                        {"fix_round": self.state.fix_round,
                         "controller_reason": decision.reason})
            self.state.state = STATE_DEV_PENDING
            self._save_state()
            self._step_dev()
            self.state.state = STATE_GATE_PENDING
            self._save_state()
            self._step_gate()
            self.state.state = STATE_REVIEW_PENDING
            self._save_state()
            verdict = self._step_review()
            d2 = verdict.get("decision")
            if d2 == "out_of_scope_review":
                self._handle_out_of_scope_review(verdict)
                return
            if d2 != "fix_required":
                # The re-review came back clean (or any non-fix verdict): hand the
                # clean verdict to the controller via the loop top, which maps it
                # to ADVANCE. We loop with this verdict; fix_round is NOT bumped
                # again for a clean pass, so step back one (the top re-bumps).
                self.state.fix_round -= 1
            # loop: re-decide on the new verdict.

    def _halt_checkpoint(self, checkpoint_id: str, decision: "lc.Decision",
                         *, context_extra: str = "",
                         needs_human: bool = False) -> str:
        """Write the controller-driven halt/escalate checkpoint (reason in the
        body) + audit. A halt is orchestrator-resolved bookkeeping; an escalate
        is a human-pending decision."""
        assert self.state is not None
        ctx = (f"Loop Controller decision: action=`{decision.action}` "
               f"reason=`{decision.reason}`.\n\n{context_extra}")
        opts = ("- review_and_route\n- accept_failure_and_route\n- abort"
                if needs_human else "- review_outcome\n- re_run\n- abort")
        path = self._write_checkpoint(
            checkpoint_id, self.state.subsprint_id,
            context_md=ctx, options_md=opts)
        return path

    def _handle_out_of_scope_review(self, review_verdict: dict) -> None:
        """Review returned ``out_of_scope_review`` (review-verdict.schema.json):
        the Code Reviewer signals the sub-sprint touched a surface it could not
        responsibly review in scope. Per delivery-loop §4.2.4 + §4.3 this is NOT
        a clean pass — it must NOT advance close_pending → advance like a `pass`.
        Mirror the non-pass review handling: emit a checkpoint + audit event and
        halt for human resolution (the human decides whether Deliver opens a new
        sub-sprint that resolves the gap, per the §4.3 re-review trigger)."""
        assert self.state is not None
        self._audit("review_out_of_scope",
                    {"blocking_count": review_verdict.get("blocking_count"),
                     "summary": review_verdict.get("summary")})
        self._write_checkpoint(
            "review_out_of_scope", self.state.subsprint_id,
            context_md=(f"Code Reviewer returned out_of_scope_review on sub-sprint "
                        f"{self.state.subsprint_id}: the diff touched a surface the "
                        f"reviewer judged out of scope to review. Per delivery-loop "
                        f"§4.2.4/§4.3 this does NOT advance — a human must route it "
                        f"(e.g. open a follow-up sub-sprint that resolves the gap, "
                        f"§4.3 re-review trigger)."),
            options_md="- open_followup_subsprint\n- accept_and_advance\n- abort",
        )
        self.state.state = STATE_HALTED
        self._save_state()

    def _handle_close(self, close_verdict: dict) -> None:
        """Deliver close verdict A/B → advance; C/D or out-of-scope →
        MANDATORY_CHECKPOINT (close_taxonomy_C_or_D / scope_deviation, §4.2.3)."""
        assert self.state is not None
        verdict = close_verdict.get("verdict")
        in_scope = close_verdict.get("in_scope")
        if verdict in ("C", "D"):
            self._write_checkpoint(
                "close_taxonomy_C_or_D", self.state.subsprint_id,
                context_md=f"Deliver close verdict = {verdict}: "
                           f"{close_verdict.get('reason')}",
                options_md="- resolve\n- abort")
            self._audit("close_taxonomy_checkpoint", {"verdict": verdict})
            self.state.state = STATE_HALTED
            self._save_state()
            return
        if in_scope is False:
            # NOTE: in P2 the deterministic scope_envelope_check is not yet wired
            # (it needs the observed diff, a later phase). Deliver's own
            # in_scope:false claim still fires scope_deviation.
            self._write_checkpoint(
                "scope_deviation", self.state.subsprint_id,
                context_md="Deliver close verdict claims in_scope: false.",
                options_md="- accept_deviation\n- reject_deviation\n- abandon")
            self._audit("scope_deviation_checkpoint", {})
            self.state.state = STATE_HALTED
            self._save_state()
            return
        # Clean pass (A/B, in_scope) → advance.
        self.state.state = STATE_ADVANCE
        self._audit("advance",
                    {"verdict": verdict,
                     "next_subsprint": close_verdict.get("next_subsprint")})
        # P5: record whether THIS clean close completes the milestone (terminal
        # sub-sprint), so the propose-only feedback stage runs at milestone close.
        self._milestone_closed = self._milestone_complete(close_verdict)
        self._save_state()

        # P3 piece 1 — after the milestone COMPLETES (the terminal clean-pass
        # advance of the sub-sprint sequence), run Acceptance IF the charter
        # enables it (delivery-loop §4.2.4). When acceptance is absent/disabled
        # this is a no-op and the run ends in STATE_ADVANCE exactly as in P2.
        if self._acceptance_enabled() and self._milestone_complete(close_verdict):
            self._run_acceptance()

    # ----- P3 piece 1: Acceptance state + §3.6 calibration + F5 evidence ---- #
    def _acceptance_enabled(self) -> bool:
        """True iff charter.acceptance.enabled is truthy. Absent/false → False,
        so the P2 close→advance behaviour is byte-identical (backward-compat)."""
        acc = self.charter.get("acceptance") or {}
        return bool(acc.get("enabled"))

    def _milestone_complete(self, close_verdict: dict) -> bool:
        """The milestone is complete when the just-closed sub-sprint is the
        TERMINAL one in autonomy.approved_scope.subsprint_sequence.

        When a non-empty sequence is DECLARED, terminality is anchored to the
        sequence itself — NOT to the close verdict's ``next_subsprint``. A
        Deliver omission (forgetting ``next_subsprint``, i.e. it is ``None``) at a
        NON-terminal step must NOT fire milestone-close Acceptance early; the
        sequence position is authoritative. Milestone-complete iff the just-closed
        sub-sprint is the last one in the sequence, OR the declared next is a
        concrete value that falls outside the approved sequence (nothing left
        in-scope to dispatch) → delivery-loop §4.2.4.

        Only when NO sequence is declared does the single-sprint heuristic apply:
        a single-shot run's close IS the milestone, so ``next_subsprint is None``
        means done."""
        assert self.state is not None
        seq = (((self.charter.get("autonomy") or {}).get("approved_scope") or {})
               .get("subsprint_sequence") or [])
        nxt = close_verdict.get("next_subsprint")
        if not seq:
            # No declared sequence — single-shot: this run's close IS the
            # milestone (the next_subsprint is None single-sprint heuristic).
            return True
        # Declared sequence → terminality is anchored to the SEQUENCE, not to a
        # (possibly omitted) next_subsprint. The terminal sub-sprint closes the
        # milestone; a non-terminal close with next_subsprint omitted (None) does
        # NOT — that would fire Acceptance early on a Deliver omission.
        if self.state.subsprint_id == seq[-1]:
            return True
        # A concrete next that is outside the approved sequence means nothing left
        # in-scope to dispatch → milestone closed. (next_subsprint is None at a
        # non-terminal step is an omission, NOT a milestone close.)
        if nxt is not None and nxt not in seq:
            return True
        return False

    def _calibration_status(self) -> str:
        """charter.tooling.acceptance.judge_calibration.status (default
        'uncalibrated' — absence is NOT calibrated; §3.6 fails closed)."""
        jc = (((self.charter.get("tooling") or {}).get("acceptance") or {})
              .get("judge_calibration") or {})
        return str(jc.get("status") or "uncalibrated")

    def _calibration_gate(self) -> str:
        """§3.6 calibration gate. If autonomy.level is fully_autonomous_within_budget
        AND the judge is not calibrated, AUTO-DEGRADE autonomy.level to
        human_on_the_loop and emit a recorded checkpoint + audit event (the
        degradation is automatic and NEVER silent/opaque — §4.2.8 anti-pattern
        #2/#6, Constitution §3.6). Returns the calibration_status to stamp on the
        verdict context ('calibrated' | 'uncalibrated' | 'not_required').

        Returns 'not_required' when autonomy is already human_in_the_loop /
        human_on_the_loop (calibration only gates autonomous Acceptance)."""
        assert self.state is not None
        level = self.autonomy.get("level", "human_in_the_loop")
        status = self._calibration_status()
        if level != "fully_autonomous_within_budget":
            # Calibration only gates AUTONOMOUS acceptance; HITL/HOTL never run
            # acceptance unattended, so the gate is not_required here.
            return "not_required"
        if status == "calibrated":
            return "calibrated"
        # Uncalibrated + autonomous → AUTO-DEGRADE (recorded, not silent).
        self.autonomy["level"] = "human_on_the_loop"
        self._audit("acceptance_calibration_degraded",
                    {"from_level": "fully_autonomous_within_budget",
                     "to_level": "human_on_the_loop",
                     "calibration_status": status,
                     "subsprint_id": self.state.subsprint_id})
        self._write_checkpoint(
            "acceptance_calibration_degraded", self.state.subsprint_id,
            context_md=(
                f"§3.6 calibration gate: judge_calibration.status = `{status}` "
                f"while autonomy.level = `fully_autonomous_within_budget`. The "
                f"orchestrator AUTO-DEGRADED autonomy.level to `human_on_the_loop` "
                f"(Constitution §3.6; delivery-loop §4.2.8 anti-pattern #2/#6). "
                f"Autonomous Acceptance MUST NOT run uncalibrated; the degradation "
                f"is automatic and recorded here — never silent. The human may "
                f"now review or calibrate-then-rerun, but acceptance proceeds "
                f"human_on_the_loop regardless."),
            options_md=("- proceed_human_on_the_loop\n"
                        "- calibrate_then_rerun_autonomous\n"
                        "- abort"),
            # §4.2.3: resolver 'orchestrator' for an auto-degraded checkpoint —
            # the degrade is already actioned (not a pending human decision).
            decision="auto_degraded", resolver="orchestrator",
            resolved_at=self.clock(),
        )
        return status

    def _run_eval_f5(self, acc: dict) -> str:
        """F5 evidence (delivery-loop §4.2.6): the DRIVER (orchestrator) executes
        charter.tooling.eval.cmd, capturing artifacts under <run_dir>/eval/runs/
        <subsprint_id>/. The eval command runs in the run dir; Acceptance NEVER
        runs the harness itself (anti-pattern #5). Returns the evidence artifact
        PATH (relative to run_dir, matching the schema's ^eval/runs/.+ pattern)
        the driver will hand to the Acceptance spawn as read-only context.

        On non-zero exit / timeout → gate_hard_fail (§4.2.6: human resolves)."""
        assert self.state is not None
        eval_cfg = (self.charter.get("tooling") or {}).get("eval") or {}
        cmd = eval_cfg.get("cmd")
        if not cmd:
            raise self._gate_hard_fail(
                "acceptance enabled but charter.tooling.eval.cmd is missing "
                "(F5 evidence has no harness to run; §4.2.6)",
                STATE_ACCEPTANCE_PENDING)
        timeout = eval_cfg.get("timeout_seconds")
        run_subdir = os.path.join("eval", "runs", self.state.subsprint_id)
        eval_run_dir = os.path.join(self.run_dir, run_subdir)
        os.makedirs(eval_run_dir, exist_ok=True)
        # The eval cmd writes its artifact here; the driver passes EVAL_RUN_DIR so
        # a deterministic local script (tests) can write a fake artifact offline.
        env = dict(os.environ)
        env["EVAL_RUN_DIR"] = eval_run_dir
        stdout_path = os.path.join(eval_run_dir, "stdout.txt")
        stderr_path = os.path.join(eval_run_dir, "stderr.txt")
        import subprocess  # local import: only on the F5 path
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=eval_run_dir, env=env,
                capture_output=True, text=True,
                timeout=timeout if isinstance(timeout, (int, float)) else None,
            )
        except subprocess.TimeoutExpired:
            raise self._gate_hard_fail(
                f"F5 eval cmd timed out after {timeout}s "
                f"(charter.tooling.eval.cmd); §4.2.6 → human resolves",
                STATE_ACCEPTANCE_PENDING)
        with open(stdout_path, "w", encoding="utf-8") as fh:
            fh.write(proc.stdout or "")
        with open(stderr_path, "w", encoding="utf-8") as fh:
            fh.write(proc.stderr or "")
        rel_stdout = os.path.relpath(stdout_path, self.run_dir)
        if proc.returncode != 0:
            self._audit("acceptance_eval_run",
                        {"cmd": cmd, "returncode": proc.returncode,
                         "evidence_dir": run_subdir, "ok": False})
            raise self._gate_hard_fail(
                f"F5 eval cmd exited {proc.returncode} "
                f"(charter.tooling.eval.cmd); §4.2.6 → human resolves "
                f"(re-run / accept-failure-and-route / abort)",
                STATE_ACCEPTANCE_PENDING)
        self._audit("acceptance_eval_run",
                    {"cmd": cmd, "returncode": 0,
                     "evidence_dir": run_subdir,
                     "evidence_path": rel_stdout, "ok": True})
        return rel_stdout

    def _spawn_acceptance(self, evidence_path: str,
                          calibration_status: str) -> dict:
        """Spawn run_acceptance via the role adapter (§1.7-C permitted surface:
        the calibration-gated orchestrator). Acceptance receives the F5 evidence
        PATH (read-only) — NOT raw code (anti-pattern #5). The driver validates
        the returned verdict against acceptance-verdict.schema.json; invalid →
        gate_hard_fail (§4.2.7)."""
        assert self.state is not None
        adapter = self.adapters.get("acceptance")
        if adapter is None:
            raise self._gate_hard_fail(
                "acceptance enabled but no adapter wired for role 'acceptance'",
                STATE_ACCEPTANCE_PENDING)
        routing = route_for_role(self.charter, "acceptance")
        prompt = (
            f"Acceptance for milestone close of sub-sprint "
            f"{self.state.subsprint_id}. Read the F5 execution evidence at "
            f"(read-only) {evidence_path}; read the closure_contract from the "
            f"research brief; emit an acceptance-verdict. Calibration status: "
            f"{calibration_status}. You MUST NOT run the eval harness yourself."
        )
        input_hash = "sha256:" + hashlib.sha256(
            ("acceptance\x00" + prompt).encode("utf-8")).hexdigest()[:16]
        self.state.spawn_count += 1
        # PERSIST the bumped spawn_count NOW (see _spawn): a resume after a mid-spawn
        # halt must not rewind it and clobber a referenced transcript.
        self._save_state()
        # AUDITABILITY: materialize the dispatched Acceptance prompt BEFORE the
        # spawn (referenced as prompt_ref), like every other role's spawn.
        prompt_ref = self._write_transcript(
            self.state.spawn_count, "acceptance", "prompt", prompt)

        # The acceptance_spawn execution record is emitted ONCE, POST-outcome, on
        # EVERY path (success / schema-invalid / adapter-error) — the same contract
        # as the uniform _spawn boundary: a single spawn event references BOTH
        # prompt_ref and output_ref (or None on an adapter error) plus a verdict_ref.
        # The acceptance-specific provenance (evidence_path, §1.7-C spawn_surface,
        # calibration) rides on the same event.
        def _acceptance_spawn_audit(verdict_ref: str,
                                    output_ref: Optional[str]) -> None:
            self._audit("acceptance_spawn", {
                "role": "acceptance", "harness": adapter.harness,
                "provider": adapter.provider, "model": adapter.model,
                "evidence_path": evidence_path,
                "calibration_status": calibration_status,
                "run_mode": self.autonomy.get("level", "human_in_the_loop"),
                "input_hash": input_hash,
                "prompt_ref": prompt_ref,
                "output_ref": output_ref,
                "verdict_ref": verdict_ref,
                # §1.7-C: this spawn surface is the orchestrator (NOT a Dev/Deliver
                # session) and is gated by the calibration check above.
                "spawn_surface": "orchestrator",
            })

        try:
            # Facet C: acceptance connectors are read-only evidence connectors
            # only (judgment is never delegated); threaded through uniformly.
            # network_access is HARD-PINNED False: Acceptance is a read-only judge
            # that NEVER receives a network grant. The charter schema already bars
            # it structurally (the acceptance block is additionalProperties:false
            # with no network_access field); pinning False here is defense-in-depth
            # so the judge stays network-free even if that schema guard regresses.
            verdict = adapter.spawn(
                "acceptance", prompt, routing.tools, self.schemas["acceptance"],
                connectors=routing.connectors, sandbox=routing.sandbox,
                network_access=False)
        except AdapterError as exc:
            _acceptance_spawn_audit("adapter_error", None)  # prompt-only; no output
            raise self._gate_hard_fail(
                f"acceptance adapter failed: {exc}", STATE_ACCEPTANCE_PENDING)
        # Capture the Acceptance verdict to a transcript + reference it on the Audit
        # Spine BEFORE validation, so an invalid verdict is still auditable.
        output_ref = self._write_transcript(
            self.state.spawn_count, "acceptance", "output", verdict)
        err = validate_verdict(verdict, self.schemas["acceptance"])
        _acceptance_spawn_audit("invalid" if err else "valid", output_ref)
        if err is not None:
            raise self._gate_hard_fail(
                f"acceptance verdict failed schema validation "
                f"(acceptance-verdict.schema.json): {err}",
                STATE_ACCEPTANCE_PENDING)
        self.state.last_verdict = verdict
        return verdict

    def _run_acceptance(self) -> None:
        """Drive the acceptance_pending state (delivery-loop §4.2.4):
          1. §3.6 calibration gate (auto-degrade if uncalibrated + autonomous);
          2. F5 evidence — driver runs eval.cmd, captures artifact paths;
          3. spawn run_acceptance with the evidence PATH (read-only);
          4. validate verdict; route per Constitution §3.5.
        The run is already in STATE_ADVANCE on entry; acceptance may move it to
        STATE_HALTED (fix_required / needs_human) or DONE (pass)."""
        assert self.state is not None
        if "acceptance" not in self.schemas:
            raise self._gate_hard_fail(
                "acceptance enabled but acceptance-verdict schema not loaded "
                "(pass verdict_schemas including 'acceptance' or use the default "
                "loader)",
                STATE_ACCEPTANCE_PENDING)
        acc = self.charter.get("acceptance") or {}
        # Acceptance only runs at MILESTONE close, so mark it (covers a resume that
        # re-enters at acceptance_pending, where _handle_close didn't run) — this
        # gates the P5 propose-only feedback stage.
        self._milestone_closed = True
        self.state.state = STATE_ACCEPTANCE_PENDING
        self.state.history.append(STATE_ACCEPTANCE_PENDING)
        self._save_state()
        self._audit("acceptance_start",
                    {"subsprint_id": self.state.subsprint_id,
                     "run_at": acc.get("run_at", "milestone_close")})

        # 1. §3.6 calibration gate (may auto-degrade autonomy + checkpoint).
        calibration_status = self._calibration_gate()

        # 2. F5 evidence — the DRIVER runs the eval harness (not Acceptance).
        evidence_path = self._run_eval_f5(acc)

        # 3. spawn run_acceptance with the evidence PATH (read-only).
        verdict = self._spawn_acceptance(evidence_path, calibration_status)
        self._handle_acceptance_verdict(verdict, evidence_path)

    def _handle_acceptance_verdict(self, verdict: dict,
                                   evidence_path: str) -> None:
        """Route the acceptance verdict per Constitution §3.5:
          pass         → ship/advance (run completes in STATE_DONE);
          fix_required → write the human-confirm checkpoint with the 3 route
                         options and HALT (NEVER route to Deliver without it —
                         §1.7-C behavioural counterpart);
          needs_human  → surface_approve checkpoint + HALT."""
        assert self.state is not None
        mv = verdict.get("milestone_verdict")
        self._audit("acceptance_verdict",
                    {"milestone_verdict": mv,
                     "suggested_route": verdict.get("suggested_route"),
                     "evidence_path": evidence_path})

        if mv == "pass":
            # Ship: the milestone closes. STATE_DONE marks a fully-accepted close.
            self.state.state = STATE_DONE
            self._audit("acceptance_pass",
                        {"subsprint_id": self.state.subsprint_id})
            self._save_state()
            return

        if mv == "fix_required":
            # §3.5: write the human-confirm checkpoint with the 3 route options;
            # HALT. The route to Deliver is NEVER taken without this checkpoint.
            acc = self.charter.get("acceptance") or {}
            route_opts = ((acc.get("on_fix_required") or {}).get("route_options")
                          or ["deliver_fix_iteration",
                              "re_acceptance_after_evidence",
                              "research_contract_revision"])
            options_md = "\n".join(f"- {opt}" for opt in route_opts)
            options_md += ("\n\n(human writes: `confirm: yes|no` + "
                           "`route: <option>` + optional notes)")
            path = self._write_checkpoint(
                "acceptance_fix_required", self.state.subsprint_id,
                context_md=(
                    f"Acceptance milestone_verdict = fix_required on sub-sprint "
                    f"{self.state.subsprint_id} (suggested_route: "
                    f"{verdict.get('suggested_route')}). Per Constitution §3.5 / "
                    f"§1.7-C the orchestrator HALTS here: Deliver does NOT pick up "
                    f"any gap brief until a human writes `confirm: yes` + `route: "
                    f"deliver_fix_iteration` in this checkpoint. F5 evidence: "
                    f"{evidence_path}."),
                options_md=options_md,
            )
            self._audit("acceptance_fix_required",
                        {"suggested_route": verdict.get("suggested_route"),
                         "checkpoint": os.path.relpath(path, self.run_dir),
                         "route_options": route_opts})
            self.state.state = STATE_HALTED
            self._save_state()
            return

        if mv == "needs_human":
            path = self._write_checkpoint(
                "acceptance_surface_approve", self.state.subsprint_id,
                context_md=(
                    f"Acceptance milestone_verdict = needs_human on sub-sprint "
                    f"{self.state.subsprint_id}: the Acceptance Agent could not "
                    f"reach an autonomous verdict and surfaces the decision to the "
                    f"Customer (surface_approve). F5 evidence: {evidence_path}."),
                options_md=("- approve_ship\n- route_to_deliver_fix\n- abort"),
            )
            self._audit("acceptance_needs_human",
                        {"checkpoint": os.path.relpath(path, self.run_dir)})
            self.state.state = STATE_HALTED
            self._save_state()
            return

        # Schema-valid enum guarantees mv ∈ {pass, fix_required, needs_human}; an
        # unexpected value here is a hard fail (never a permissive default).
        raise self._gate_hard_fail(
            f"unexpected acceptance milestone_verdict {mv!r}",
            STATE_ACCEPTANCE_PENDING)
