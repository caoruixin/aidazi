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
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

# Sentinel returned by _resolve_dev_spec when a LIVE run cannot resolve a complete,
# scope-valid Dev spec: the engine has written a refinement checkpoint + set
# STATE_HALTED, and the dev step must NOT proceed to the model spawn.
_DEV_SPEC_HALT = object()

# Same contract for the Review and Acceptance prompt projections: a LIVE run that
# cannot resolve a complete, self-contained prompt from authoritative structured
# state (or an adopter-authored compact prompt) writes a refinement checkpoint +
# sets STATE_HALTED and returns the sentinel — it NEVER spawns a one-line prompt.
_REVIEW_SPEC_HALT = object()
_ACCEPTANCE_SPEC_HALT = object()

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
from adapters import ADAPTER_REGISTRY, Adapter, AdapterError, MockAdapter  # noqa: E402

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

# P-A — shared, dependency-free acceptance namespace/mode normalizer
# (engine-kit/charter_compat.py; _ENGINE_KIT_DIR is on sys.path above).
import charter_compat  # noqa: E402

# P-C — the browser-E2E evidence stage: e2e_stage holds the PURE fail-closed helpers
# (hashing / reconcile / consistency gate / reuse fingerprints, §3.2/§3.5); e2e_executor
# is the orchestrator-owned capture runner (observations only). Both are siblings under
# orchestrator/ (on sys.path above). They are only EXERCISED when a milestone runs
# tooling.acceptance.functional.mode=browser_e2e — a non-browser_e2e run never touches
# them, so the path stays byte-identical for every existing charter.
import e2e_stage  # noqa: E402
import e2e_executor  # noqa: E402

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
STATE_E2E_PENDING = "e2e_evidence_pending"  # P-C browser-E2E evidence (before acceptance)
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
# tooling.acceptance.mode (≠ off), so the close→advance path remains byte-identical
# when acceptance is off (backward-compat).
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
    # ---- Prompt-contract additions (persisted for resume, §4.5).
    #   halt_resume_state  : when a refinement HALT fires (a dev/review/acceptance
    #                        prompt is not resolvable on a live run) the PENDING state
    #                        the halt paused at is recorded here so a resume RE-ENTERS
    #                        it (``state`` itself is STATE_HALTED). None ⇒ not a
    #                        resumable spec-halt (a terminal/HITL halt stays put).
    #   last_dev_output_ref: run-dir-relative path to the most recent Dev spawn's
    #                        output transcript — the concrete change summary the
    #                        projected Review prompt references.
    halt_resume_state: Optional[str] = None
    last_dev_output_ref: Optional[str] = None
    # ---- P-C browser-E2E commit/reuse state (persisted for resume; §3.5a/b). All
    #      default to the pre-P-C baseline, so a non-browser_e2e RunState round-trips
    #      byte-identically (from_dict tolerates their absence in an older state.json).
    #   e2e_run_id           : deterministic per-(loop,subsprint) run id, persisted UP
    #                          FRONT (pending phase) — recovery keys on THIS + the ledger
    #                          event, NOT on the cache fields below (§3.5a).
    #   e2e_evidence_ref     : run-dir-relative path to the committed manifest.json (cache).
    #   e2e_manifest_hash    : the committed manifest's artifact_manifest_hash (cache).
    #   acceptance_evidence_hash : the evidence hash the persisted last_verdict judged
    #                          (browser: manifest hash; static: sha256 of the F5 file) —
    #                          binds a committed verdict to its evidence (§3.5b).
    #   acceptance_snapshot  : {evidence_hash, authority_fingerprint, acceptance_input_hash,
    #                          authoritative} FROZEN at verdict production; routing reads
    #                          authoritative from here, and resume reuses ONLY when all
    #                          three hashes match the recompute (§3.5b).
    e2e_run_id: Optional[str] = None
    e2e_evidence_ref: Optional[str] = None
    e2e_manifest_hash: Optional[str] = None
    acceptance_evidence_hash: Optional[str] = None
    acceptance_snapshot: Optional[dict] = None

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
            "halt_resume_state": self.halt_resume_state,
            "last_dev_output_ref": self.last_dev_output_ref,
            "e2e_run_id": self.e2e_run_id,
            "e2e_evidence_ref": self.e2e_evidence_ref,
            "e2e_manifest_hash": self.e2e_manifest_hash,
            "acceptance_evidence_hash": self.acceptance_evidence_hash,
            "acceptance_snapshot": self.acceptance_snapshot,
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
            halt_resume_state=d.get("halt_resume_state"),
            last_dev_output_ref=d.get("last_dev_output_ref"),
            e2e_run_id=d.get("e2e_run_id"),
            e2e_evidence_ref=d.get("e2e_evidence_ref"),
            e2e_manifest_hash=d.get("e2e_manifest_hash"),
            acceptance_evidence_hash=d.get("acceptance_evidence_hash"),
            acceptance_snapshot=d.get("acceptance_snapshot"),
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
        # P-A: normalize the acceptance namespace + mode IN PLACE so every read
        # below is canonical (tooling.acceptance.mode) with NO per-read fallback
        # (design §1.4). A genuine config conflict (e.g. enabled vs mode disagree)
        # is fatal at construction; warnings surface in the loop_start audit.
        _acc_warn, _acc_err = charter_compat.normalize_acceptance(charter)
        if _acc_err:
            raise ValueError(
                "charter acceptance config invalid: " + "; ".join(_acc_err))
        self._acceptance_norm_warnings = _acc_warn
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

        # P-C — browser-E2E evidence root (created only when a browser_e2e milestone
        # actually runs): .orchestrator/audit/browser/<loop_id>/<run_id>/ (§5). Lives
        # under the Audit Spine so refs+hashes co-locate with the hash chain.
        self.browser_dir = os.path.join(
            self.audit_dir, "browser", self._safe_path_component(self.loop_id))
        self._pc_schema_cache: dict = {}
        # §2a runtime hard-fail (Codex MAJOR-1): browser_e2e functional acceptance with
        # acceptance OFF is incoherent (a browser-evidence run with no judge). Enforce at
        # CONSTRUCTION — independent of the charter validator, which run_loop invokes only
        # on allow_real. Fires only for the net-new browser_e2e+off combination; every
        # pre-P-C charter (no functional block) is unaffected.
        if (self._acceptance_class() == "browser_e2e"
                and charter_compat.acceptance_mode(charter) == "off"):
            raise ValueError(
                "tooling.acceptance.functional.mode=browser_e2e requires "
                "tooling.acceptance.mode != off (a browser-evidence run needs a judge)")

        # P6.1 — resolve the loop mode (ctor param WINS over charter, else the
        # delivery_only default) + stash the injected gate resolver. delivery_only
        # is the default and gates EVERY new pre-state path, so a charter / caller
        # that says nothing is byte-identical to the pre-P6.1 driver.
        self.loop_mode = (loop_mode
                          or self.autonomy.get("loop_mode")
                          or LOOP_MODE_DELIVERY_ONLY)
        self.gate_resolver = gate_resolver

        self.state: Optional[RunState] = None
        # The most recent _spawn's output-transcript ref (run-dir-relative). _step_dev
        # copies it into RunState.last_dev_output_ref so the projected Review prompt can
        # cite the Dev change-summary by a CONCRETE path.
        self._last_spawn_output_ref: Optional[str] = None

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
        self._last_spawn_output_ref = output_ref  # for _step_dev → review change ref

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
        """Validate an adopter-authored compact prompt (Dev / Review / Acceptance) by
        CONTENT, not mere file existence (a non-empty file is NOT automatically a
        self-contained spec). The shared hard requirement is
        ``context_budget.self_contained: true`` (Constitution §1.4-i); without it the
        file is not a self-contained job. Reused by all three prompt contracts."""
        problems = []
        if not (body or "").strip():
            problems.append("the prompt body is empty")
        cb = front_matter.get("context_budget") if isinstance(front_matter, dict) else None
        self_contained = cb.get("self_contained") if isinstance(cb, dict) else None
        if self_contained is not True:
            problems.append(
                "front-matter `context_budget.self_contained` must be `true` "
                "(Constitution §1.4-i; see the role's compact-prompt template) — the "
                "compact prompt must be a self-contained, bounded job, not a bare prompt")
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

    # ----- generic compact-prompt helpers (shared by Review + Acceptance) ---- #
    def _compact_prompt_path(self, scope_id: str, suffix: str) -> Optional[str]:
        """Absolute path to an OPTIONAL adopter-authored compact prompt
        ``<repo>/compact/<scope_id>-<suffix>.md`` (suffix e.g. ``review-prompt`` |
        ``acceptance-prompt``), or None when no repo is bound OR ``scope_id`` is
        unsafe / would escape ``<repo>/compact``. Same containment discipline as
        ``_dev_spec_path`` — the scope_id is interpolated into a path."""
        if not self.repo_dir:
            return None
        if not self._safe_subsprint_id(scope_id):
            return None
        base = os.path.realpath(os.path.join(self.repo_dir, "compact"))
        path = os.path.realpath(os.path.join(base, f"{scope_id}-{suffix}.md"))
        if os.path.commonpath([base, path]) != base:
            return None  # containment guard (defense-in-depth vs the id check)
        return path

    def _load_compact_prompt(self, path: Optional[str]):
        """Read an adopter-authored compact prompt → ``(front_matter, body)`` or None
        when the path is missing/unreadable. Mirrors ``_load_compact_file`` but takes
        an explicit path so Review + Acceptance reuse the same read+split."""
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
        # Record the pending state the halt paused at, so a resume (after the human
        # refines the spec) RE-ENTERS dev_pending and re-resolves — genuinely resumable.
        self.state.halt_resume_state = STATE_DEV_PENDING
        self._save_state()  # PERSIST the halt + its resume target
        self._audit("dev_spec_refinement_halt",
                    {"subsprint_id": sid, "source": source, "problems": problems})
        return _DEV_SPEC_HALT

    def _strict_prompts(self) -> bool:
        """True ⇒ resolve self-contained prompts (project-or-HALT, never a one-line
        request); False ⇒ the legacy inline prompt (offline/mock, byte-identical).

        Strict mode is the union of TWO independent enablers so a real model can NEVER
        receive a thin prompt: (a) an explicit ``context.allow_real`` flag, OR (b) the
        presence of ANY non-mock adapter (claude_code / codex / headless / kimi …) —
        i.e. a real subprocess/HTTP backend is wired. The MockAdapter is the only
        offline/test backend, so an all-mock wiring without allow_real stays
        byte-identical to before; the moment a real adapter is wired, prompt
        resolution fails closed even if the caller forgot to set allow_real."""
        if bool(self.context.get("allow_real")):
            return True
        return any(not isinstance(a, MockAdapter) for a in self.adapters.values())

    def _resolve_dev_spec(self):
        """Resolve the normative executable Dev spec for the current sub-sprint.

        OFFLINE/mock (not strict) ⇒ None (the legacy inline prompt; the test suite +
        dry-run stay byte-identical). On a STRICT/LIVE run, validate BY CONTENT, in
        priority order, sanitizing the id before ANY path use:
          1. the schema-valid decompose-plan entry (CANONICAL) → project it to an
             executable prompt (+ an auditable compact-file projection);
          2. an adopter-authored compact/<id>-dev-prompt.md (alternative source);
          3. neither ⇒ a refinement HALT.
        An incomplete/ambiguous spec at (1) or (2) HALTS for refinement rather than
        silently running, or falling through to a less-specific source."""
        if not self._strict_prompts():
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

    # ----- Review-prompt resolution (sub-sprint contract + Dev work to judge) -- #
    # A DISTINCT contract from the Dev one: the Review prompt is scoped to ONE
    # sub-sprint and derived from the SAME resolved sub-sprint spec the Dev executed
    # PLUS the Dev handoff/diff to judge. compact/<id>-review-prompt.md is the
    # adopter-authored alternative. Validated by CONTENT; a missing/incomplete source
    # on a LIVE run HALTS — it never dispatches a one-line review request.
    def _project_review_prompt(self, spec: dict) -> str:
        """Deterministically PROJECT the resolved sub-sprint spec into a
        self-contained Code Reviewer prompt (templates/compact-review-prompt.md
        shape). EMBEDS the sub-sprint contract + review responsibilities + severity
        rules + the review-verdict schema instruction; REFERENCES the Dev handoff +
        diff and the anti-hardcode kernel (stable refs — no raw transcript copied in,
        per the 'reference evidence, don't embed transcripts' rule)."""
        def _section(label: str, value: Any) -> str:
            if not value:
                return ""
            if isinstance(value, (list, tuple)):
                inner = "\n".join(f"  - {x}" for x in value)
            else:
                inner = f"  {value}"
            return f"{label}:\n{inner}\n"
        sid = spec.get("id") or self.state.subsprint_id
        parts = [
            f"You are activating as the Code Reviewer Agent for sub-sprint {sid}.\n",
            "Read-only judge: Read/Grep/Glob only — NO edits, NO network, NO git "
            "push, NO agent spawn. Cold-start the always-load governance chain plus "
            "role-cards/code-reviewer-agent.md, templates/anti-hardcode-review-"
            "kernel.md (the 9-question kernel) and schemas/review-verdict.schema.json"
            ".\n\n",
            "## Sub-sprint under review\n",
            f"Objective: {spec.get('objective', '')}\n",
            _section("Scope IN (judge ONLY against these deliverables)",
                     spec.get("scope_in")),
            _section("Scope OUT (explicit non-goals)", spec.get("scope_out")),
            _section("Modules in scope (Dev declares; verify by walking the diff)",
                     spec.get("modules")),
            _section("Exit criteria (close conditions the work must meet)",
                     spec.get("exit_criteria")),
            _section("Fix-layers in play", spec.get("layers")),
            "\n## Dev handoff / change summary to review\n"
            + (f"- Dev change summary (engine-captured, this sub-sprint): "
               f"`{self.state.last_dev_output_ref}`\n"
               if getattr(self.state, "last_dev_output_ref", None) else "")
            + "- Dev handoff doc: `docs/handoff.md`\n"
            "- Working-tree diff for this sub-sprint (read the changed files with "
            "Read/Grep/Glob).\n"
            "Reference only — read on demand; raw transcripts are NOT embedded here "
            "(stable evidence references, not copied content).\n\n",
            "## Review responsibilities\n"
            "1. Anti-hardcode kernel — apply the 9-question kernel to EVERY diff "
            "that touches a semantic surface (prompt / runtime semantic decision / "
            "eval spec / judge calibration / a new keyword|regex|enum affecting "
            "routing or escalation). If you skip it, declare an exemption explicitly "
            "(infra_only | docs_only | config_governance | characterization_test).\n"
            "2. Correctness lens — ownership (§1.3/§1.4), Tier-0 invariants "
            "(docs/current/runtime_invariants.md), test coverage on changed semantic "
            "surfaces, trace/eval-contract integrity, prompt self-containment "
            "(§1.4-i).\n"
            "3. §1.7 forbidden-list audit (role card §7) — ANY finding tied to §1.7 "
            "is P0 and forces decision=fix_required.\n"
            "4. Scope discipline — judge ONLY against Scope IN above; if the diff "
            "touches a surface outside it, decision=out_of_scope_review (do NOT "
            "silently pass).\n\n",
            "## Severity rules\n"
            "- P0: a §1.7 violation, a Tier-0 invariant break, or a correctness "
            "defect that ships wrong behavior.\n"
            "- P1: a blocking defect within scope (e.g. a missing test on a semantic "
            "surface, a contract violation) that is not P0.\n"
            "- P2: a non-blocking improvement.\n"
            "- blocking_count = count of P0 + P1 findings.\n\n",
            "## Output — emit a review-verdict (schemas/review-verdict.schema.json)\n"
            "Return ONE JSON object and nothing else:\n"
            "  decision: \"pass\" | \"fix_required\" | \"out_of_scope_review\" "
            "(never invent another value)\n"
            "  blocking_count: <integer >= 0>   (P0 + P1)\n"
            "  summary: \"<one paragraph>\"\n"
            "  scope_claim: \"<the sub-sprint id + module set you judged against>\"\n"
            "  findings: [ { id, severity: \"P0\"|\"P1\"|\"P2\", layer: <fix-layer "
            "enum>, evidence: [\"file:line\", ...], rationale, constitution_clause?, "
            "kernel_question? } ]\n"
            "A §1.7-tied finding defaults to P0 with decision=fix_required.\n",
        ]
        return "".join(p for p in parts if p)

    def _review_spec_refine_halt(self, source: str, problems: list):
        """Write a Review-prompt REFINEMENT checkpoint + set STATE_HALTED (resumable),
        then return the sentinel. Mirrors ``_dev_spec_refine_halt``: a missing /
        incomplete review source is a correctable gap, not a one-line review
        request."""
        sid = self.state.subsprint_id
        bullets = "\n".join(f"- {p}" for p in problems)
        self._write_checkpoint(
            "review_spec_refinement", sid,
            context_md=(
                f"The self-contained Code Reviewer prompt for sub-sprint `{sid}` is "
                f"not resolvable yet (source: {source}). The loop HALTS for "
                f"refinement — it will NOT dispatch a one-line review request.\n\n"
                f"Problems:\n{bullets}\n\n"
                f"Resolve by EITHER completing the Deliver decompose plan for this "
                f"sub-sprint (objective + scope_in + exit_criteria) so the engine "
                f"can project the review prompt, OR authoring "
                f"`compact/{sid}-review-prompt.md` from "
                f"`templates/compact-review-prompt.md` (front-matter "
                f"`context_budget.self_contained: true`). Then resume."),
            options_md=("- refine_plan_and_resume\n"
                        "- author_compact_review_prompt_and_resume\n- abort"))
        self.state.state = STATE_HALTED
        # Resume target: re-enter review_pending after the human supplies/refines the
        # review source, and re-resolve (genuinely resumable, not a dead end).
        self.state.halt_resume_state = STATE_REVIEW_PENDING
        self._save_state()  # PERSIST the halt + its resume target
        self._audit("review_spec_refinement_halt",
                    {"subsprint_id": sid, "source": source, "problems": problems})
        return _REVIEW_SPEC_HALT

    def _resolve_review_spec(self):
        """Resolve the self-contained Code Reviewer prompt for the current sub-sprint.

        OFFLINE/mock (not strict) ⇒ None (the legacy inline prompt; the test suite
        stays byte-identical). On a STRICT/LIVE run, in order (sanitizing the id
        before ANY path use):
          1. an adopter-authored compact/<id>-review-prompt.md (when content-valid);
          2. else PROJECT from the resolved sub-sprint spec (the same decompose-plan
             entry the Dev executed);
          3. neither ⇒ a refinement HALT.
        An incomplete source at (1) or (2) HALTS rather than silently dispatching a
        one-line review request (or falling through to a less-specific source)."""
        if not self._strict_prompts():
            return None  # offline/mock → legacy inline prompt (byte-identical)
        sid = self.state.subsprint_id
        if not self._safe_subsprint_id(sid):
            return self._review_spec_refine_halt(
                "invalid_id",
                [f"sub-sprint id {sid!r} is not a safe identifier "
                 f"(letters/digits then ._- only; no path separators)"])
        loaded = self._load_compact_prompt(
            self._compact_prompt_path(sid, "review-prompt"))
        if loaded is not None:
            front_matter, body = loaded
            problems = self._validate_compact_text(front_matter, body)
            if problems:
                return self._review_spec_refine_halt("compact_file", problems)
            return body.strip()
        plan_spec = self._current_subsprint_plan()
        if plan_spec is not None:
            problems = self._validate_subsprint_spec(plan_spec)
            if problems:
                return self._review_spec_refine_halt("subsprint_spec", problems)
            return self._project_review_prompt(plan_spec)
        return self._review_spec_refine_halt(
            "missing",
            [f"no decompose-plan entry for `{sid}` and no "
             f"compact/{sid}-review-prompt.md under the repo to derive the review "
             f"prompt from"])

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
        # Capture the Dev change-summary transcript ref so the projected Review prompt
        # can cite it by a CONCRETE path (not just "the working-tree diff").
        self.state.last_dev_output_ref = self._last_spawn_output_ref
        self.state.history.append(STATE_DEV_PENDING)

    def _step_gate(self) -> None:
        self._run_gates()
        self.state.history.append(STATE_GATE_PENDING)

    def _step_review(self):
        # The Review prompt is resolved from an adopter compact/<id>-review-prompt.md
        # or PROJECTED from the resolved sub-sprint spec, validated by CONTENT. A live
        # run with no usable source HALTS for refinement (resumable) — it never
        # dispatches a one-line review request. Offline/mock keeps the legacy inline
        # prompt (byte-identical). On HALT, returns None; _drive sees STATE_HALTED.
        resolved = self._resolve_review_spec()
        if resolved is _REVIEW_SPEC_HALT:
            return None  # checkpoint written + STATE_HALTED set; the drive loop stops
        if resolved is not None:
            prompt = self._lessons_block("review") + resolved
        else:
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
            # P-A: surface any acceptance-namespace normalization (legacy top-level
            # `acceptance` block / `enabled` alias) — emitted ONLY when it fired, so
            # a canonical charter's audit chain stays byte-identical.
            if self._acceptance_norm_warnings:
                self._audit("charter_acceptance_normalized",
                            {"warnings": self._acceptance_norm_warnings})
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
        # Resume FROM a refinement HALT (dev / review / acceptance prompt was not
        # resolvable): the human has refined the source and re-run. Restore the pending
        # state the halt paused at so the loop RE-ENTERS it (and re-resolves — passing
        # now, or re-halting if still unfixed). This is what makes the spec-HALT
        # genuinely resumable; a terminal/HITL halt has no halt_resume_state and stays
        # put (the short-circuit below returns).
        if self.state.state == STATE_HALTED and self.state.halt_resume_state:
            self.state.state = self.state.halt_resume_state
            self.state.halt_resume_state = None
            self._save_state()
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
        # Resume INTO the P-C browser-E2E stage: if a prior process died mid-capture,
        # re-enter it. Idempotent via §3.5a (reconcile from the persisted run_id + the
        # ledger event → no duplicate executor run; an incomplete dir re-runs). It then
        # proceeds into acceptance, so handle it BEFORE the acceptance re-entry.
        if self.state.state == STATE_E2E_PENDING:
            self._run_e2e_evidence()
            return
        # Resume INTO acceptance: if a prior process died mid-acceptance, re-enter
        # the acceptance state. Idempotent: §3.5b reuses an already-committed verdict
        # bound to the same evidence/authority/criteria, else re-spawns. The acceptance
        # state is out-of-band (not in LOOP_ORDER), so handle it here.
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
                if self.state.state == STATE_HALTED:
                    return  # review-spec refinement halt — do not decide/advance
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
            if self.state.state == STATE_HALTED:
                return  # dev-spec refinement halt mid-auto-fix — do not advance
            self.state.state = STATE_GATE_PENDING
            self._save_state()
            self._step_gate()
            self.state.state = STATE_REVIEW_PENDING
            self._save_state()
            verdict = self._step_review()
            if self.state.state == STATE_HALTED:
                return  # review-spec refinement halt mid-auto-fix (verdict is None)
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

        # P3 piece 1 / P-C — after the milestone COMPLETES (the terminal clean-pass
        # advance of the sub-sprint sequence): for a browser_e2e milestone run the
        # orchestrator-owned browser EVIDENCE stage first (which then drives Acceptance),
        # else run Acceptance directly IF the charter enables it (delivery-loop §4.2.4).
        # When neither applies this is a no-op and the run ends in STATE_ADVANCE exactly
        # as in P2 (a non-functional, acceptance-off charter is byte-identical).
        if self._milestone_complete(close_verdict):
            if self._acceptance_class() == "browser_e2e":
                self._run_e2e_evidence()      # commit evidence (§3.5a) → then acceptance
            elif self._acceptance_enabled():
                self._run_acceptance()

    # ----- P3 piece 1: Acceptance state + §3.6 calibration + F5 evidence ---- #
    def _acceptance_mode(self) -> str:
        """Canonical tooling.acceptance.mode ∈ {off, advisory, auto}; absent → off
        (byte-identical to the P2 disabled path — default-on is a TEMPLATE default,
        not a silent driver flip; design §3.1/§3.5). Ctor normalization has already
        mapped any legacy top-level `acceptance` block + `enabled` alias to mode."""
        return charter_compat.acceptance_mode(self.charter)

    def _acceptance_enabled(self) -> bool:
        """Back-compat shim used by the close path: acceptance runs iff mode≠off."""
        return self._acceptance_mode() != "off"

    def _acceptance_class(self) -> str:
        """P-C active acceptance class: 'browser_e2e' (M3) when the (derived) charter
        sets tooling.acceptance.functional.mode=browser_e2e, else 'static' (M1 — today's
        behavior). In a campaign this reads the per-milestone DERIVED charter (the
        functional mode is projected there by campaign.derive_milestone_context), so the
        class is correct per milestone."""
        functional = (((self.charter.get("tooling") or {}).get("acceptance") or {})
                      .get("functional") or {})
        return "browser_e2e" if functional.get("mode") == "browser_e2e" else "static"

    def _calibration_record_id(self) -> Optional[str]:
        """The active class's calibration-record id (browser_e2e → the M3 record id;
        static → None, M1 has no record-id field). Part of the §3.5b authority
        fingerprint + stamped on the verdict."""
        if self._acceptance_class() == "browser_e2e":
            m3 = (((self.charter.get("tooling") or {}).get("acceptance") or {})
                  .get("functional") or {}).get("judge_calibration_m3") or {}
            return m3.get("record_id")
        return None

    def _pc_schema(self, filename: str) -> dict:
        """Load (+ cache) a P-C config/contract schema by filename from the schemas/
        dir (no auto-discovery exists; each consumer loads what it needs)."""
        if filename not in self._pc_schema_cache:
            base = _find_schemas_dir()
            if not base:
                raise FileNotFoundError("schemas/ directory not found for P-C schema")
            with open(os.path.join(base, filename), "r", encoding="utf-8") as fh:
                self._pc_schema_cache[filename] = json.load(fh)
        return self._pc_schema_cache[filename]

    def _acceptance_authoritative(self) -> bool:
        """A pass auto-ships (STATE_DONE) ONLY when AUTHORITATIVE: mode==auto AND the
        judge is calibrated FOR THE ACTIVE CLASS AND autonomy is
        fully_autonomous_within_budget (design §3.2 authority matrix). Anything else →
        an advisory pass-signoff HALT. The active class is M1 (static) or M3
        (browser_e2e); v1 ships no M3 record ⇒ M3 is never calibrated ⇒ M3 never
        authoritative ⇒ a browser-functional pass is advisory.

        NOTE (§3.5b): for a RESUMED/reused verdict the driver routes from the FROZEN
        acceptance_snapshot.authoritative, NOT this live recompute — this method is the
        FRESH-production computation that the snapshot freezes."""
        if self._acceptance_mode() != "auto":
            return False
        # v1 ships NO validated M3 calibration record, so a browser_e2e (M3) pass is NEVER
        # authoritative — it is ADVISORY and HALTs at advisory_acceptance_pass_signoff,
        # REGARDLESS of any charter-declared judge_calibration_m3.status (which has no
        # backing record / validation path in v1). Enforced by construction here so an
        # adopter cannot self-declare M3 'calibrated' to auto-ship a browser pass (Codex
        # impl r2 BLOCKING-2; design §6 + §10 non-goal: no M3 acceptance-authority
        # expansion). M1 (static) authority is byte-identical to P-A below.
        if self._acceptance_class() == "browser_e2e":
            return False
        if self._calibration_status(self._acceptance_class()) != "calibrated":
            return False
        return self.autonomy.get("level") == "fully_autonomous_within_budget"

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

    def _calibration_status(self, cls: Optional[str] = None) -> str:
        """Calibration status for the ACTIVE acceptance class (§3.6; P-C class-aware).
        cls defaults to `_acceptance_class()`. static (M1) reads
        tooling.acceptance.judge_calibration.status (byte-identical to P-A); browser_e2e
        (M3) reads tooling.acceptance.functional.judge_calibration_m3.status. Default
        'uncalibrated' — absence is NOT calibrated; fails closed. v1 ships no M3 record,
        so the M3 path is always 'uncalibrated' ⇒ M3 advisory."""
        cls = cls or self._acceptance_class()
        acc = ((self.charter.get("tooling") or {}).get("acceptance") or {})
        if cls == "browser_e2e":
            m3 = (acc.get("functional") or {}).get("judge_calibration_m3") or {}
            return str(m3.get("status") or "uncalibrated")
        jc = acc.get("judge_calibration") or {}
        return str(jc.get("status") or "uncalibrated")

    def _calibration_gate(self) -> str:
        """§3.6 calibration gate (P-C class-aware). If autonomy.level is
        fully_autonomous_within_budget AND the judge is not calibrated FOR THE ACTIVE
        CLASS, AUTO-DEGRADE autonomy.level to human_on_the_loop and emit a recorded
        checkpoint + audit event (the degradation is automatic and NEVER silent/opaque —
        §4.2.8 anti-pattern #2/#6, Constitution §3.6). Returns the calibration_status to
        stamp on the verdict context ('calibrated' | 'uncalibrated' | 'not_required').

        Returns 'not_required' when autonomy is already human_in_the_loop /
        human_on_the_loop (calibration only gates autonomous Acceptance). Reading the
        ACTIVE class (not always M1) is what makes a browser_e2e run with M1-calibrated
        but M3-uncalibrated correctly degrade (Codex round-2/3 BLOCKING)."""
        assert self.state is not None
        level = self.autonomy.get("level", "human_in_the_loop")
        status = self._calibration_status(self._acceptance_class())
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

    # ----- P-C: browser-E2E evidence stage (STATE_E2E_PENDING; §2/§3.5a) ------ #
    def _e2e_run_id(self) -> str:
        """Deterministic, PERSISTED per-(loop, subsprint) run id (§3.5a). Generated once
        on first entry and reused on resume, so recovery keys on it + the ledger event —
        never on the unsaved cache fields."""
        assert self.state is not None
        if not self.state.e2e_run_id:
            digest = hashlib.sha256(
                (self.loop_id + "\x00" + self.state.subsprint_id).encode()).hexdigest()
            self.state.e2e_run_id = "r" + digest[:16]
            self._save_state()
        return self.state.e2e_run_id

    def _e2e_final_dir(self, run_id: str) -> str:
        return os.path.join(self.browser_dir, run_id)

    def _e2e_rel_prefix(self, run_id: str) -> str:
        """The committed run dir RELATIVE to run_dir — the prefix a verdict's
        functional_evidence_refs must use (.orchestrator/audit/browser/<loop>/<run>)."""
        return os.path.relpath(self._e2e_final_dir(run_id), self.run_dir).replace(os.sep, "/")

    def _e2e_config(self) -> dict:
        """charter.tooling.e2e (executor MECHANICS). Absent on a browser_e2e run →
        gate_hard_fail (the §2a ctor check also catches mode:off; this guards the
        mechanics)."""
        e2e = (self.charter.get("tooling") or {}).get("e2e")
        if not isinstance(e2e, dict):
            raise self._gate_hard_fail(
                "browser_e2e requires charter.tooling.e2e (executor mechanics)",
                STATE_E2E_PENDING)
        return e2e

    def _e2e_checklist_path(self) -> str:
        functional = (((self.charter.get("tooling") or {}).get("acceptance") or {})
                      .get("functional") or {})
        path = functional.get("checklist_path")
        if not path:
            raise self._gate_hard_fail(
                "browser_e2e requires tooling.acceptance.functional.checklist_path",
                STATE_E2E_PENDING)
        return path if os.path.isabs(path) else os.path.join(self.run_dir, path)

    def _e2e_checklist(self) -> dict:
        """Load + schema-validate the signed functional-checklist CRITERIA (§4.3).
        Missing / invalid → gate_hard_fail."""
        abspath = self._e2e_checklist_path()
        if not os.path.isfile(abspath):
            raise self._gate_hard_fail(
                f"functional-checklist not found at {abspath}", STATE_E2E_PENDING)
        try:
            with open(abspath, "r", encoding="utf-8") as fh:
                checklist = json.load(fh)
        except (OSError, ValueError) as exc:
            raise self._gate_hard_fail(
                f"functional-checklist invalid JSON: {exc}", STATE_E2E_PENDING)
        err = e2e_stage.validate(
            checklist, self._pc_schema("functional-checklist.schema.json"))
        if err:
            raise self._gate_hard_fail(
                f"functional-checklist does not validate: {err}", STATE_E2E_PENDING)
        return checklist

    def _e2e_runtime_contract(self, run_id: str) -> dict:
        """Build the concrete runtime executor-contract from charter.tooling.e2e:
        validate the static mechanics, allocate a free port + per-run store, project
        {port}/{store}/{mode}. Re-validate the runtime form (fail-closed, since run_loop
        only validates on allow_real)."""
        e2e = self._e2e_config()
        ec_schema = self._pc_schema("executor-contract.schema.json")
        err = e2e_stage.validate(e2e, ec_schema)
        if err:
            raise self._gate_hard_fail(
                f"tooling.e2e invalid (executor-contract): {err}", STATE_E2E_PENDING)
        port = e2e_stage.allocate_free_port()
        store = os.path.join(self.orch_dir, f"e2e_store_{run_id}.json")
        contract = e2e_stage.build_runtime_contract(
            e2e, port=port, store_path=store, mode=e2e.get("mode", "normal"))
        err2 = e2e_stage.validate(contract, ec_schema)
        if err2:
            raise self._gate_hard_fail(
                f"runtime executor-contract invalid: {err2}", STATE_E2E_PENDING)
        return contract

    def _checklist_summary(self, final_dir: str) -> dict:
        """Count executor_status across checklist-results.json (audit context only)."""
        out = {"pass": 0, "fail": 0, "error": 0, "skipped": 0}
        try:
            with open(os.path.join(final_dir, "checklist-results.json"),
                      "r", encoding="utf-8") as fh:
                for row in json.load(fh) or []:
                    st = row.get("executor_status")
                    if st in out:
                        out[st] += 1
        except (OSError, ValueError):  # pragma: no cover - summary is best-effort
            pass
        return out

    def _emit_e2e_event(self, run_id: str, final_dir: str, manifest: dict) -> None:
        """Append the ONE hash-chained browser_e2e_evidence event that anchors a committed
        evidence set (§5). Reconcile matches on {run_id, manifest_sha256}."""
        self._audit(e2e_stage.EVIDENCE_EVENT_TYPE, {
            "run_id": run_id,
            "manifest_ref": os.path.relpath(
                os.path.join(final_dir, "manifest.json"), self.run_dir).replace(os.sep, "/"),
            "manifest_sha256": manifest.get("artifact_manifest_hash"),
            "artifacts": [{"name": a["name"], "sha256": a["sha256"]}
                          for a in manifest.get("artifacts", [])],
            "exit_code": manifest.get("exit_code"),
            "checklist_summary": self._checklist_summary(final_dir),
        })

    def _cache_e2e_commit(self, run_id: str, final_dir: str, manifest_hash: str) -> None:
        assert self.state is not None
        self.state.e2e_run_id = run_id
        self.state.e2e_evidence_ref = os.path.relpath(
            os.path.join(final_dir, "manifest.json"), self.run_dir).replace(os.sep, "/")
        self.state.e2e_manifest_hash = manifest_hash
        self._save_state()

    def _commit_e2e(self) -> dict:
        """§3.5a durable commit/reconcile — returns the committed manifest dict.
          A) reconcile passes (dir complete + per-artifact hashes + matching ledger event)
             → return, NO re-run;
          B) dir complete + hashes ok but NO matching ledger event (crash between publish
             and append) → append the one event, return (do NOT re-run);
          C) absent / partial / corrupt → run the executor into a fresh staging dir, build
             + verify the manifest, atomically publish (rmtree any existing final first —
             os.replace cannot overwrite a non-empty dir), append the event, cache.
        A RUNTIME executor failure → gate_hard_fail (resumable). Recovery is authoritative
        from the persisted run_id + disk + ledger, so an unsaved cache never causes a skip."""
        assert self.state is not None
        run_id = self._e2e_run_id()
        final = self._e2e_final_dir(run_id)
        m_schema = self._pc_schema("browser-evidence-manifest.schema.json")
        cr_item = (m_schema.get("$defs") or {}).get("checklist_result")
        events = (audit.read_events(self.audit_ledger)
                  if os.path.isfile(self.audit_ledger) else [])

        if e2e_stage.dir_complete_and_hashes_ok(final, m_schema, cr_item):
            manifest = e2e_stage.load_manifest(final)
            mh = manifest.get("artifact_manifest_hash")
            if not e2e_stage.evidence_event_present(events, run_id, mh):
                self._emit_e2e_event(run_id, final, manifest)   # B
            self._cache_e2e_commit(run_id, final, mh)           # A / B
            return manifest

        # C — (re)run into a fresh staging dir; publish atomically.
        staging = final + ".staging"
        shutil.rmtree(staging, ignore_errors=True)
        checklist = self._e2e_checklist()
        contract = self._e2e_runtime_contract(run_id)
        self._audit("e2e_start", {"subsprint_id": self.state.subsprint_id,
                                  "run_id": run_id,
                                  "executor_kind": contract.get("executor_kind")})
        os.makedirs(staging, exist_ok=True)
        try:
            executor = e2e_executor.make_executor(contract.get("executor_kind", ""))
            result = executor.run(contract, checklist, staging, env={})
        except e2e_executor.ExecutorUnavailable as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise self._gate_hard_fail(
                f"browser executor unavailable: {exc}", STATE_E2E_PENDING)
        except e2e_executor.ExecutorRuntimeError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise self._gate_hard_fail(
                f"browser executor runtime failure: {exc}", STATE_E2E_PENDING)
        except ValueError as exc:  # unknown executor kind / bad config
            shutil.rmtree(staging, ignore_errors=True)
            raise self._gate_hard_fail(
                f"browser executor config error: {exc}", STATE_E2E_PENDING)

        manifest = e2e_stage.build_manifest(
            staging, result, contract, run_id=run_id, loop_id=self.loop_id)
        with open(os.path.join(staging, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, sort_keys=True, indent=2)
        if not e2e_stage.dir_complete_and_hashes_ok(staging, m_schema, cr_item):
            shutil.rmtree(staging, ignore_errors=True)
            raise self._gate_hard_fail(
                "browser evidence incomplete after capture (staging failed completeness)",
                STATE_E2E_PENDING)
        shutil.rmtree(final, ignore_errors=True)
        os.makedirs(os.path.dirname(final), exist_ok=True)
        os.replace(staging, final)        # atomic publish onto a now-absent path
        mh = manifest.get("artifact_manifest_hash")
        self._emit_e2e_event(run_id, final, manifest)
        self._cache_e2e_commit(run_id, final, mh)
        return manifest

    def _check_dev_self_smoke(self) -> None:
        """§6a (Codex MAJOR-2) — a browser_e2e milestone REQUIRES a Dev self-smoke
        attestation: the running app exercised once on the changed happy path, recorded
        at docs/self-smoke.json as {command, result}. This is a STRUCTURAL PRESENCE gate
        (NOT a judgment of correctness — necessary, not authoritative; distinct from the
        independent browser evidence gate). Absent/malformed → resumable gate_hard_fail."""
        assert self.state is not None
        path = os.path.join(self.run_dir, "docs", "self-smoke.json")
        if not os.path.isfile(path):
            raise self._gate_hard_fail(
                "browser_e2e milestone requires a Dev self-smoke attestation at "
                "docs/self-smoke.json ({command, result} — run the app + exercise the "
                "changed happy path once); none found", STATE_E2E_PENDING)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                ss = json.load(fh)
        except (OSError, ValueError) as exc:
            raise self._gate_hard_fail(
                f"Dev self-smoke attestation is not valid JSON: {exc}",
                STATE_E2E_PENDING)
        if not (isinstance(ss, dict) and ss.get("command") and ss.get("result")):
            raise self._gate_hard_fail(
                "Dev self-smoke attestation must contain non-empty {command, result}",
                STATE_E2E_PENDING)
        self._audit("dev_self_smoke_present",
                    {"subsprint_id": self.state.subsprint_id,
                     "command": str(ss.get("command"))[:200]})

    def _run_e2e_evidence(self) -> None:
        """Drive STATE_E2E_PENDING (§2): verify the Dev self-smoke attestation (§6a),
        commit the browser evidence (idempotent via §3.5a), then proceed into
        milestone-close Acceptance. Out-of-band like acceptance; resume re-enters here
        and is non-duplicating."""
        assert self.state is not None
        self.state.state = STATE_E2E_PENDING
        if STATE_E2E_PENDING not in self.state.history:
            self.state.history.append(STATE_E2E_PENDING)
        self._milestone_closed = True
        self._save_state()
        self._check_dev_self_smoke()       # §6a structural gate (resumable halt if absent)
        self._commit_e2e()                 # reconcile-or-run; gate_hard_fail on runtime fail
        if self._acceptance_enabled():
            self._run_acceptance()

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

    # ----- Acceptance-prompt resolution (signed contract + milestone evidence) - #
    # A DISTINCT contract from the Review one: the Acceptance prompt is scoped to
    # MILESTONE CLOSE and derived from the SIGNED charter.intent_contract (the
    # customer need + the bar + the definition of done) plus the closure_contract,
    # the F5 evidence, and the per-sub-sprint Reviewer outcomes. compact/<scope>-
    # acceptance-prompt.md is the adopter-authored alternative. A missing / unsigned
    # / incomplete contract on a LIVE run HALTS — it never dispatches a one-line
    # acceptance request. This resolution runs AFTER the §3.6 calibration gate and
    # the F5 eval, and NEVER alters calibration or authority — it only REPORTS them.
    def _acceptance_scope_id(self) -> str:
        """The milestone scope id for the Acceptance compact-prompt path + header:
        the charter mission id when present + path-safe (acceptance is
        milestone-scoped), else the current sub-sprint id."""
        mission = (self.charter.get("mission") or {}).get("id")
        if mission is not None and self._safe_subsprint_id(mission):
            return str(mission)
        return self.state.subsprint_id

    @staticmethod
    def _validate_acceptance_context(ic: dict) -> list:
        """Validate the SIGNED intent contract anchoring the Acceptance prompt, by
        CONTENT. The acceptance criteria = the customer need (goal) + the bar
        (standard) + the definition of done (proof_of_done), and the contract MUST be
        human-signed (confirmed_by_human) — Acceptance judges ONLY a signed contract
        (Constitution §3.4 invariant #4; the engine never auto-confirms). Empty list
        ⇒ a complete, signed contract."""
        problems = []
        if not isinstance(ic, dict) or not ic:
            return ["no charter.intent_contract to derive the Acceptance criteria from"]
        if not str(ic.get("goal") or "").strip():
            problems.append("missing/empty intent_contract.goal (the customer need)")
        if not str(ic.get("standard") or "").strip():
            problems.append("missing/empty intent_contract.standard (the acceptance bar)")
        if not str(ic.get("proof_of_done") or "").strip():
            problems.append(
                "missing/empty intent_contract.proof_of_done (definition of done)")
        if ic.get("confirmed_by_human") is not True:
            problems.append(
                "intent_contract.confirmed_by_human must be `true` — Acceptance judges "
                "ONLY a human-signed contract (Constitution §3.4 invariant #4)")
        return problems

    def _project_acceptance_prompt(self, ic: dict, evidence_path: str,
                                   calibration_status: str) -> str:
        """Deterministically PROJECT the signed intent contract + milestone context
        into a self-contained Acceptance prompt (templates/compact-acceptance-prompt
        .md shape). EMBEDS the customer need + acceptance criteria + calibration /
        authority + the acceptance-verdict schema instruction; REFERENCES the
        closure_contract (brief), the F5 evidence path, and the per-sub-sprint
        Reviewer outcomes (stable refs — raw evidence is NOT copied in). This is
        PURELY a rendering of existing state: it does NOT change calibration_status
        or the autonomy level (the §3.6 gate already ran)."""
        scope = self._acceptance_scope_id()
        # CONCRETE closure-contract reference only when a brief is actually bound;
        # otherwise the embedded signed proof_of_done IS the closure criterion (the
        # intent-contract schema: proof_of_done maps to the closure_contract proof) —
        # never fabricate a research-brief path that does not exist.
        brief_ref = self.state.brief_draft_ref
        if brief_ref:
            closure_section = (
                "## Acceptance criteria — closure contract\n"
                f"Judge ONLY against the signed closure_contract (positive_shape + "
                f"anti_pattern + anchor_phrases) in: `{brief_ref}`. The "
                f"closure_contract is IMMUTABLE between Gate-1 sign-off and "
                f"acceptance (§3.4 invariant #4); if its sign_off_date does not match "
                f"milestone start, your verdict is needs_human.\n\n")
            closure_ref_line = f"  closure_contract_ref: \"{brief_ref}\"\n"
        else:
            closure_section = (
                "## Acceptance criteria — closure contract\n"
                "No separate research brief is bound to this loop; the acceptance "
                "criteria ARE the signed `proof_of_done` above (the intent contract's "
                "definition of done, which maps to the closure_contract proof). Judge "
                "ONLY against it. The signed contract is IMMUTABLE post Gate-1 (§3.4 "
                "invariant #4).\n\n")
            closure_ref_line = ("  closure_contract_ref: (optional — omit, or cite "
                                "the signed intent_contract; no research brief is "
                                "bound)\n")
        seq = (self._supplied_sequence() or list(self.state.planned_sequence)
               or [self.state.subsprint_id])
        level = self.autonomy.get("level", "human_in_the_loop")
        parts = [
            f"You are activating as the Acceptance Agent for the milestone close of "
            f"`{scope}`.\n",
            "Read-only customer-perspective judge: Read/Grep/Glob only — NO edits, "
            "NO network, NO eval-harness run. Spawn surface: orchestrator (§1.7-C, "
            "calibration-gated). Cold-start the always-load governance chain plus "
            "role-cards/acceptance-agent.md and "
            "schemas/acceptance-verdict.schema.json.\n\n",
            "## Customer need (signed intent contract)\n"
            f"Goal (customer terms): {ic.get('goal','')}\n"
            f"Standard (the bar for 'good'): {ic.get('standard','')}\n"
            f"Proof of done (definition of done / eval method): "
            f"{ic.get('proof_of_done','')}\n\n",
            closure_section,
            "## Delivered behavior under acceptance\n"
            f"Milestone sub-sprints delivered: {', '.join(str(s) for s in seq)}\n"
            "Judge the DELIVERED BEHAVIOR (customer perspective), not code "
            "structure.\n\n",
            "## Accumulated evidence (read-only; do NOT re-run the harness)\n"
            f"- F5 execution evidence (authoritative): {evidence_path}\n"
            "- Per-sub-sprint Reviewer outcomes: docs/codex-findings.md and the "
            "review transcripts under `.orchestrator/audit/transcripts/`.\n"
            "- Do NOT judge from code inspection alone (§4.2.8 anti-pattern #5); "
            "every case MUST cite an execution evidence_path under eval/runs/.\n\n",
            "## Authority & calibration (do NOT override)\n"
            f"Autonomy level: {level}\n"
            f"Calibration status: {calibration_status}\n"
            "If calibration is uncalibrated on an autonomous run, the orchestrator "
            "has ALREADY degraded authority (§3.6) and your verdict is ADVISORY "
            "ONLY until calibrated — do not self-escalate.\n\n",
            "## Output — emit an acceptance-verdict "
            "(schemas/acceptance-verdict.schema.json)\n"
            "Return ONE JSON object and nothing else:\n"
            "  milestone_verdict: \"pass\" | \"fix_required\" | \"needs_human\"\n"
            + closure_ref_line +
            "  calibration_status: \"calibrated\"|\"uncalibrated\"|\"not_required\"\n"
            "  cases: [ { case_id, criterion, evidence_path: \"eval/runs/...\", "
            "verdict: \"pass\"|\"fail\"|\"partial\", rationale }, ... ]   (>= 1 case)\n"
            "  failure_briefs: [...]   (REQUIRED + non-empty iff fix_required)\n"
            "  residual_risks: [ \"<risk the Customer assumes on a pass>\", ... ]\n"
            "  suggested_route: \"deliver_fix_iteration\" | "
            "\"re_acceptance_after_evidence\" | \"research_contract_revision\" | "
            "\"n/a\"\n"
            "Each case cites an execution evidence_path under eval/runs/ (NEVER a "
            "code path). Rationale cites a SEMANTIC observation (positive shape held "
            "/ anti-pattern avoided / anchor-phrase match), never a keyword match "
            "(§1.7-B). On fix_required, ALSO write the §3.5 human-confirm checkpoint "
            "— never route to Deliver without it.\n",
        ]
        return "".join(parts)

    def _acceptance_spec_refine_halt(self, source: str, problems: list):
        """Write an Acceptance-prompt REFINEMENT checkpoint + set STATE_HALTED
        (resumable), then return the sentinel. The F5 evidence already captured this
        run is preserved for the resume. A missing/unsigned/incomplete acceptance
        contract is a correctable gap, not a one-line acceptance request."""
        scope = self._acceptance_scope_id()
        bullets = "\n".join(f"- {p}" for p in problems)
        self._write_checkpoint(
            "acceptance_spec_refinement", scope,
            context_md=(
                f"The self-contained Acceptance prompt for milestone `{scope}` is "
                f"not resolvable yet (source: {source}). The loop HALTS for "
                f"refinement — it will NOT dispatch a one-line acceptance request.\n\n"
                f"Problems:\n{bullets}\n\n"
                f"Resolve by EITHER signing a complete charter.intent_contract "
                f"(goal + standard + proof_of_done + confirmed_by_human) so the "
                f"engine can project the acceptance prompt against the "
                f"closure_contract, OR authoring "
                f"`compact/{scope}-acceptance-prompt.md` from "
                f"`templates/compact-acceptance-prompt.md` (front-matter "
                f"`context_budget.self_contained: true`). Then resume."),
            options_md=("- sign_intent_contract_and_resume\n"
                        "- author_compact_acceptance_prompt_and_resume\n- abort"))
        self.state.state = STATE_HALTED
        # Resume target: re-enter acceptance_pending after the human signs the contract
        # / authors the compact prompt — _run_acceptance re-runs the eval + re-resolves.
        self.state.halt_resume_state = STATE_ACCEPTANCE_PENDING
        self._save_state()  # PERSIST the halt + its resume target
        self._audit("acceptance_spec_refinement_halt",
                    {"scope": scope, "source": source, "problems": problems})
        return _ACCEPTANCE_SPEC_HALT

    def _resolve_acceptance_spec(self, evidence_path: str,
                                 calibration_status: str):
        """Resolve the self-contained Acceptance prompt for milestone close.

        OFFLINE/mock (not strict) ⇒ None (the legacy inline prompt; the test suite
        stays byte-identical). On a STRICT/LIVE run:
          0. HARD GATE FIRST — the SIGNED charter.intent_contract (Constitution §3.4
             invariant #4: Acceptance judges ONLY a human-signed contract). This gates
             BOTH sources below; an unsigned/incomplete/missing contract ⇒ HALT, so an
             adopter compact prompt can NEVER bypass the sign-off.
          1. then an adopter-authored compact/<scope>-acceptance-prompt.md (content-
             valid) — a richer rendering layered on the signed contract;
          2. else PROJECT from the signed contract + closure_contract / F5 evidence /
             reviewer-outcome refs.
        Never dispatches a one-line acceptance request on a live run."""
        if not self._strict_prompts():
            return None  # offline/mock → legacy inline prompt (byte-identical)
        scope = self._acceptance_scope_id()
        if not self._safe_subsprint_id(scope):
            return self._acceptance_spec_refine_halt(
                "invalid_scope",
                [f"acceptance scope id {scope!r} is not a safe identifier "
                 f"(letters/digits then ._- only; no path separators)"])
        # §3.4 invariant #4 HARD GATE — applies to EVERY source (compact or
        # projection): Acceptance never runs without a human-signed contract.
        ic = self.charter.get("intent_contract") or {}
        problems = self._validate_acceptance_context(ic)
        if problems:
            return self._acceptance_spec_refine_halt("intent_contract", problems)
        loaded = self._load_compact_prompt(
            self._compact_prompt_path(scope, "acceptance-prompt"))
        if loaded is not None:
            front_matter, body = loaded
            problems = self._validate_compact_text(front_matter, body)
            if problems:
                return self._acceptance_spec_refine_halt("compact_file", problems)
            return body.strip()
        return self._project_acceptance_prompt(ic, evidence_path, calibration_status)

    def _build_acceptance_prompt(self, evidence_path: str, calibration_status: str,
                                 manifest: Optional[dict] = None,
                                 run_id: Optional[str] = None):
        """Build the Acceptance prompt: resolved from an adopter compact/<scope>-
        acceptance-prompt.md OR PROJECTED from the SIGNED intent + closure contract +
        the evidence (validated by CONTENT); offline/mock keeps the legacy inline prompt
        (byte-identical to P-A). A live run with no usable source HALTS (resumable) and
        returns _ACCEPTANCE_SPEC_HALT. For a browser_e2e run a DETERMINISTIC
        browser-evidence section is appended (manifest + checklist-results refs + the
        signed criteria + the 'executor_status is an OBSERVATION, not a verdict'
        instruction). The driver computes the §3.5b acceptance_input_hash over THIS
        prompt + the resolver graph, so the verdict is bound to exactly what it judged."""
        assert self.state is not None
        resolved = self._resolve_acceptance_spec(evidence_path, calibration_status)
        if resolved is _ACCEPTANCE_SPEC_HALT:
            return _ACCEPTANCE_SPEC_HALT  # checkpoint + STATE_HALTED; caller stops
        if resolved is not None:
            prompt = resolved
        else:
            prompt = (
                f"Acceptance for milestone close of sub-sprint "
                f"{self.state.subsprint_id}. Read the F5 execution evidence at "
                f"(read-only) {evidence_path}; read the closure_contract from the "
                f"research brief; emit an acceptance-verdict. Calibration status: "
                f"{calibration_status}. You MUST NOT run the eval harness yourself."
            )
        if self._acceptance_class() == "browser_e2e" and run_id is not None:
            prompt += self._browser_evidence_prompt_section(run_id, manifest)
        return prompt

    def _spawn_acceptance(self, prompt: str, evidence_path: str,
                          calibration_status: str, snapshot: dict) -> dict:
        """Spawn run_acceptance via the role adapter (§1.7-C permitted surface: the
        calibration-gated orchestrator) with the PREBUILT ``prompt``. Acceptance receives
        evidence PATHS (read-only) — NOT raw code (anti-pattern #5). The driver validates
        the returned verdict against acceptance-verdict.schema.json (invalid →
        gate_hard_fail) and, on a valid verdict, PERSISTS it with its §3.5b reuse binding
        (acceptance_evidence_hash + the frozen ``snapshot``) BEFORE the caller routes — so
        a crash before routing reuses THIS exact verdict on resume rather than re-rolling."""
        assert self.state is not None
        adapter = self.adapters.get("acceptance")
        if adapter is None:
            raise self._gate_hard_fail(
                "acceptance enabled but no adapter wired for role 'acceptance'",
                STATE_ACCEPTANCE_PENDING)
        routing = route_for_role(self.charter, "acceptance")
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
        # §3.5b: persist the verdict + its reuse binding (evidence hash + the FROZEN
        # authority/criteria snapshot) BEFORE the caller routes, so a crash between here
        # and routing reuses THIS verdict (bound to this evidence/authority/criteria) on
        # resume instead of re-spawning and possibly flipping the outcome.
        self.state.last_verdict = verdict
        self.state.acceptance_evidence_hash = snapshot.get("evidence_hash")
        self.state.acceptance_snapshot = dict(snapshot)
        self._save_state()
        return verdict

    def _acceptance_browser_evidence(self):
        """§3.5a integrity gate — Acceptance MUST NOT run on incomplete browser evidence.
        Reconcile the committed evidence (dir complete + per-artifact hashes + a matching
        ledger event); ANY failure → gate_hard_fail (Acceptance never spawns). Returns
        (manifest, manifest_relpath, run_id)."""
        assert self.state is not None
        run_id = self._e2e_run_id()
        final = self._e2e_final_dir(run_id)
        m_schema = self._pc_schema("browser-evidence-manifest.schema.json")
        cr_item = (m_schema.get("$defs") or {}).get("checklist_result")
        events = (audit.read_events(self.audit_ledger)
                  if os.path.isfile(self.audit_ledger) else [])
        if not e2e_stage.dir_complete_and_hashes_ok(final, m_schema, cr_item):
            raise self._gate_hard_fail(
                "browser evidence incomplete/corrupt at acceptance (reconcile failed); "
                "Acceptance cannot run on incomplete evidence", STATE_ACCEPTANCE_PENDING)
        manifest = e2e_stage.load_manifest(final)
        mh = manifest.get("artifact_manifest_hash")
        if not e2e_stage.evidence_event_present(events, run_id, mh):
            raise self._gate_hard_fail(
                "browser evidence not anchored on the Audit Spine (no matching "
                "browser_e2e_evidence event); refusing to judge unanchored evidence",
                STATE_ACCEPTANCE_PENDING)
        rel = os.path.relpath(os.path.join(final, "manifest.json"),
                              self.run_dir).replace(os.sep, "/")
        return manifest, rel, run_id

    def _browser_evidence_prompt_section(self, run_id: str,
                                         manifest: Optional[dict]) -> str:
        """Deterministic browser-evidence addendum for the Acceptance prompt (M3)."""
        prefix = self._e2e_rel_prefix(run_id)
        arts = sorted(a.get("name", "") for a in (manifest or {}).get("artifacts", []))
        return (
            "\n\n## Browser-E2E evidence (read-only; M3 functional acceptance)\n"
            f"Committed, hash-anchored evidence under: `{prefix}/` "
            f"(manifest.json + {', '.join(arts)}).\n"
            "Judge EACH signed functional-checklist criterion (by criterion_id) "
            "INDEPENDENTLY against the captured evidence. The checklist-results.json "
            "`executor_status` values are OBSERVATIONS, not verdicts — you may fail a "
            "criterion the executor marked pass, and you MUST NOT pass a criterion the "
            "executor observed fail/error.\n"
            "Emit acceptance_class: \"browser_e2e\"; every case carries its criterion_id "
            f"and functional_evidence_refs ({{kind, path, sha256}}) citing artifacts under "
            f"`{prefix}/` (the driver binds each ref to the committed manifest — a fake or "
            "uncommitted ref hard-fails). Cases MUST cover the full checklist criterion "
            "set; a milestone pass requires every case pass AND no critical executor "
            "failure.\n")

    def _acceptance_resolver_graph(self, evidence_path: str,
                                   run_id: Optional[str]):
        """rev7 resolver graph: the load set the Acceptance prompt instructs the judge to
        read, content-hashed (so an edit to ANY loaded input invalidates §3.5b reuse). The
        driver enumerates it from the SAME sources it wires into the prompt + cold-start:
        the executor mechanics (inline), the signed criteria sources, the derived context,
        the Reviewer outcomes, the role card + verdict schema, the evidence manifest, and
        the adopter cold-start ledgers — each that EXISTS. A MANDATORY member that is
        missing/unreadable is returned in `missing` (the caller gate_hard_fails)."""
        assert self.state is not None
        base = _find_schemas_dir()
        repo_root = os.path.dirname(base) if base else self.run_dir

        def _abs(p):
            return p if os.path.isabs(p) else os.path.join(self.run_dir, p)

        entries = []
        e2e = (self.charter.get("tooling") or {}).get("e2e")
        if isinstance(e2e, dict):
            entries.append({"path": "tooling.e2e", "purpose": "executor_contract",
                            "inline": e2e})
        fnl = (((self.charter.get("tooling") or {}).get("acceptance") or {})
               .get("functional") or {})
        if fnl.get("checklist_path"):
            entries.append({"path": _abs(fnl["checklist_path"]),
                            "rel": fnl["checklist_path"],
                            "purpose": "functional_checklist", "mandatory": True})
        if self.state.brief_draft_ref:
            entries.append({"path": _abs(self.state.brief_draft_ref),
                            "rel": self.state.brief_draft_ref,
                            "purpose": "closure_contract"})
        for rel in ("derived-context.json",
                    os.path.join("docs", "codex-findings.md")):
            ap = os.path.join(self.run_dir, rel)
            if os.path.isfile(ap):
                entries.append({"path": ap, "rel": rel.replace(os.sep, "/"),
                                "purpose": "review_context"})
        if base:
            entries.append({"path": os.path.join(base, "acceptance-verdict.schema.json"),
                            "rel": "schemas/acceptance-verdict.schema.json",
                            "purpose": "verdict_schema"})
        entries.append({"path": os.path.join(repo_root, "role-cards",
                                             "acceptance-agent.md"),
                        "rel": "role-cards/acceptance-agent.md", "purpose": "role_card"})
        if run_id is not None:
            entries.append({"path": os.path.join(self._e2e_final_dir(run_id),
                                                 "manifest.json"),
                            "rel": evidence_path, "purpose": "evidence_manifest",
                            "mandatory": True})
        else:
            entries.append({"path": _abs(evidence_path), "rel": evidence_path,
                            "purpose": "f5_evidence", "mandatory": True})
        # Adopter cold-start lives in the ADOPTER repo (self.repo_dir), NOT run_dir (the
        # /tmp artifact dir, "outside the repo") — binding it under run_dir would miss the
        # REAL AGENTS.md / docs/current ledgers, so an edit there could not invalidate
        # §3.5b reuse (Codex impl r2 BLOCKING-3). When ingress is off (repo_dir is None)
        # there is no adopter repo, so there is no adopter cold-start to bind here — the
        # framework cold-start below still anchors the always-load governance chain.
        adopter_root = self.repo_dir
        if adopter_root:
            ag = os.path.join(adopter_root, "AGENTS.md")
            if os.path.isfile(ag):
                entries.append({"path": ag, "rel": "AGENTS.md",
                                "purpose": "adopter_cold_start"})
            cur = os.path.join(adopter_root, "docs", "current")
            if os.path.isdir(cur):
                for fn in sorted(os.listdir(cur)):
                    if fn.endswith(".md"):
                        entries.append({"path": os.path.join(cur, fn),
                                        "rel": f"docs/current/{fn}",
                                        "purpose": "adopter_ledger"})
        # The framework cold-start root: AGENTS.md @-includes the always-load governance
        # chain, so the transitive resolver reaches constitution / doc_governance /
        # context_briefing (and whatever else they include) — an edit to any invalidates reuse.
        fw_agents = os.path.join(repo_root, "AGENTS.md")
        if os.path.isfile(fw_agents):
            entries.append({"path": fw_agents, "rel": "AGENTS.md",
                            "purpose": "framework_cold_start"})
        return e2e_stage.resolve_load_graph(entries, repo_root=repo_root)

    def _run_acceptance(self) -> None:
        """Drive acceptance_pending (delivery-loop §4.2.4) — class-aware (P-C):
          1. §3.6 calibration gate (auto-degrade if uncalibrated + autonomous), ACTIVE class;
          2. EVIDENCE — browser_e2e: VERIFY the committed browser evidence (§3.5a reconcile,
             else gate_hard_fail) + use the manifest; static: F5 eval.cmd. Compute the
             evidence_hash for BOTH classes (§3.5b);
          3. prompt + resolver graph → acceptance_input_hash; authority_fingerprint +
             authoritative → the FROZEN snapshot;
          4. §3.5b reuse-on-resume — a committed verdict bound to the SAME evidence +
             authority + criteria is RE-ROUTED (no re-spawn, no flip); else spawn fresh;
          5. §3.2 consistency gate (browser_e2e) + route per §3.5 from the FROZEN snapshot.
        On entry the run is STATE_ADVANCE; acceptance may move it to STATE_HALTED
        (advisory/fix_required/needs_human) or STATE_DONE (authoritative pass)."""
        assert self.state is not None
        if "acceptance" not in self.schemas:
            raise self._gate_hard_fail(
                "acceptance enabled but acceptance-verdict schema not loaded "
                "(pass verdict_schemas including 'acceptance' or use the default loader)",
                STATE_ACCEPTANCE_PENDING)
        acc = ((self.charter.get("tooling") or {}).get("acceptance") or {})
        active_class = self._acceptance_class()
        self._milestone_closed = True
        self.state.state = STATE_ACCEPTANCE_PENDING
        if STATE_ACCEPTANCE_PENDING not in self.state.history:
            self.state.history.append(STATE_ACCEPTANCE_PENDING)
        self._save_state()
        self._audit("acceptance_start",
                    {"subsprint_id": self.state.subsprint_id,
                     "run_at": acc.get("run_at", "milestone_close"),
                     "acceptance_class": active_class})

        # Capture the CHARTER-DECLARED (pre-degrade) autonomy level BEFORE the gate runs —
        # the gate mutates the live autonomy dict (which aliases charter['autonomy']), so the
        # §3.5b authority fingerprint MUST use this captured value, not a post-gate read
        # (Codex impl MAJOR-1).
        declared_autonomy = (self.charter.get("autonomy") or {}).get("level")
        # 1. §3.6 calibration gate (class-aware; re-establishes the non-persisted degrade
        #    on resume so the authority basis is consistent across produce/resume).
        calibration_status = self._calibration_gate()
        cal_record_id = self._calibration_record_id()

        # 2. Evidence + evidence_hash (BOTH classes — §3.5b binds reuse to it).
        manifest: Optional[dict] = None
        run_id: Optional[str] = None
        if active_class == "browser_e2e":
            manifest, evidence_path, run_id = self._acceptance_browser_evidence()
            evidence_hash = manifest.get("artifact_manifest_hash")
        else:
            evidence_path = self._run_eval_f5(acc)
            evidence_hash = e2e_stage.sha256_file(
                os.path.join(self.run_dir, evidence_path))

        # 3. Prompt + resolver graph → the three reuse fingerprints + the FROZEN snapshot.
        prompt = self._build_acceptance_prompt(
            evidence_path, calibration_status, manifest, run_id)
        if prompt is _ACCEPTANCE_SPEC_HALT:
            return  # acceptance-spec refinement halt: checkpoint written, STATE_HALTED
        graph, missing = self._acceptance_resolver_graph(evidence_path, run_id)
        if missing:
            raise self._gate_hard_fail(
                "acceptance resolver-graph missing mandatory input(s): "
                + ", ".join(m.get("purpose", m.get("path", "?")) for m in missing),
                STATE_ACCEPTANCE_PENDING)
        snapshot = {
            "evidence_hash": evidence_hash,
            "authority_fingerprint": e2e_stage.authority_fingerprint(
                self.charter, active_class=active_class,
                calibration_status=calibration_status,
                calibration_record_id=cal_record_id,
                autonomy_level_declared=declared_autonomy),
            "acceptance_input_hash": e2e_stage.acceptance_input_hash(prompt, graph),
            "authoritative": bool(self._acceptance_authoritative()),
        }

        # 4. §3.5b reuse-on-resume: a committed verdict bound to the SAME evidence +
        #    authority + criteria is re-routed (NO re-spawn, no flip). Any divergence on
        #    ANY of the three (or no committed verdict yet) → spawn fresh.
        lv, snap = self.state.last_verdict, self.state.acceptance_snapshot
        if (isinstance(lv, dict) and "milestone_verdict" in lv and isinstance(snap, dict)
                and snap.get("evidence_hash") == snapshot["evidence_hash"]
                and snap.get("authority_fingerprint") == snapshot["authority_fingerprint"]
                and snap.get("acceptance_input_hash") == snapshot["acceptance_input_hash"]
                # The triple binds authority INPUTS; ALSO bind the derived authority
                # DECISION. Routing ships from the FROZEN snap.authoritative (below), so a
                # stale snap.authoritative that disagrees with the current policy — e.g. an
                # M3 'true' produced before the §10 M3-advisory guard, or any authority
                # logic change between produce and resume — must NOT be reused-and-shipped.
                # On a mismatch we re-spawn; the fresh snapshot (authoritative=False for M3)
                # then routes advisory (Codex impl r3 BLOCKING; design §3.5b/§10).
                and bool(snap.get("authoritative")) == snapshot["authoritative"]):
            self._audit("acceptance_reuse",
                        {"subsprint_id": self.state.subsprint_id,
                         "reason": "evidence+authority+criteria+decision all match"})
            self._handle_acceptance_verdict(lv, evidence_path, snapshot=snap,
                                            manifest=manifest, run_id=run_id)
            return

        verdict = self._spawn_acceptance(
            prompt, evidence_path, calibration_status, snapshot)
        if verdict is _ACCEPTANCE_SPEC_HALT:
            return  # acceptance-spec refinement halt: checkpoint written, STATE_HALTED
        self._handle_acceptance_verdict(verdict, evidence_path, snapshot=snapshot,
                                        manifest=manifest, run_id=run_id)

    def _load_checklist_results(self, run_id: Optional[str]) -> list:
        if run_id is None:
            return []
        try:
            with open(os.path.join(self._e2e_final_dir(run_id),
                                   "checklist-results.json"), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except (OSError, ValueError):  # pragma: no cover - reconcile already verified it
            return []

    def _handle_acceptance_verdict(self, verdict: dict, evidence_path: str, *,
                                   snapshot: dict,
                                   manifest: Optional[dict] = None,
                                   run_id: Optional[str] = None) -> None:
        """Route the acceptance verdict per Constitution §3.5:
          pass         → ship/advance (STATE_DONE) ONLY when the FROZEN snapshot says
                         authoritative (§3.5b — NOT a live recompute); else advisory HALT;
          fix_required → human-confirm checkpoint + HALT (NEVER route to Deliver without
                         it — §1.7-C counterpart);
          needs_human  → surface_approve checkpoint + HALT.
        For a browser_e2e run the §3.2 CONSISTENCY GATE runs FIRST: an integrity breach
        (wrong class / unbound or malformed evidence ref) → gate_hard_fail; a pass that
        CONTRADICTS the captured evidence (failed case / critical executor failure /
        coverage gap) is coerced to needs_human (surface_approve) — never shipped."""
        assert self.state is not None
        consistency_reason = ""
        active_class = self._acceptance_class()
        if active_class == "browser_e2e":
            checklist = self._e2e_checklist()
            cresults = self._load_checklist_results(run_id)
            outcome = e2e_stage.check_acceptance_consistency(
                verdict, manifest or {}, checklist, cresults,
                evidence_rel_prefix=self._e2e_rel_prefix(run_id or self._e2e_run_id()))
            if outcome is not None:
                action, reason = outcome
                self._audit("acceptance_consistency",
                            {"action": action, "reason": reason,
                             "subsprint_id": self.state.subsprint_id})
                if action == "gate_hard_fail":
                    raise self._gate_hard_fail(
                        f"acceptance consistency gate: {reason}",
                        STATE_ACCEPTANCE_PENDING)
                # needs_human: a pass that contradicts the committed evidence is coerced
                # to needs_human (surface_approve) and NEVER shipped (§3.2).
                verdict = {**verdict, "milestone_verdict": "needs_human"}
                consistency_reason = reason
        else:
            # STATIC active class: enforce the SYMMETRIC class match (design §3.1/§3.2.1 —
            # "verdict omits/mismatches active class → gate_hard_fail"). The branch-correct
            # schema ACCEPTS a browser_e2e-shaped verdict (functional_evidence_refs, NO
            # evidence_path required), which on a static run would skip BOTH the browser
            # consistency gate (only run above) AND the static evidence binding, so a 'pass'
            # could auto-ship when M1 is authoritative. A static run therefore REQUIRES the
            # verdict's acceptance_class to be absent or 'static' (Codex impl r4 BLOCKING —
            # closes the static-side browser-pass auto-ship path). Legit M1 verdicts (no
            # acceptance_class) are byte-identical to P-A.
            vclass = verdict.get("acceptance_class")
            if vclass not in (None, "static"):
                self._audit("acceptance_consistency",
                            {"action": "gate_hard_fail",
                             "reason": f"static active class but verdict "
                                       f"acceptance_class={vclass!r}",
                             "subsprint_id": self.state.subsprint_id})
                raise self._gate_hard_fail(
                    f"acceptance verdict class mismatch: active=static, verdict "
                    f"acceptance_class={vclass!r}", STATE_ACCEPTANCE_PENDING)

        mv = verdict.get("milestone_verdict")
        self._audit("acceptance_verdict",
                    {"milestone_verdict": mv,
                     "suggested_route": verdict.get("suggested_route"),
                     "acceptance_class": self._acceptance_class(),
                     "authoritative": bool(snapshot.get("authoritative")),
                     "evidence_path": evidence_path})

        if mv == "pass":
            if snapshot.get("authoritative"):
                # Authoritative pass (auto mode + calibrated + fully-autonomous):
                # the milestone ships. STATE_DONE marks a fully-accepted close.
                self.state.state = STATE_DONE
                self._audit("acceptance_pass",
                            {"subsprint_id": self.state.subsprint_id,
                             "authoritative": True})
                self._save_state()
                return
            # Advisory pass — NEVER auto-ship (design §3.2/§3.3): the read-only
            # peer-of-Research judge ADVISES; a human signs off to ship. Write the
            # advisory_acceptance_pass_signoff MANDATORY_CHECKPOINT (#9) + HALT.
            path = self._write_checkpoint(
                "advisory_acceptance_pass_signoff", self.state.subsprint_id,
                context_md=(
                    f"Acceptance milestone_verdict = pass on sub-sprint "
                    f"{self.state.subsprint_id}, but the verdict is ADVISORY "
                    f"(tooling.acceptance.mode={self._acceptance_mode()}, "
                    f"calibration_status={self._calibration_status()}, "
                    f"autonomy={self.autonomy.get('level')!r}). Per design §3.2 an "
                    f"advisory pass does NOT auto-ship; a human signs off here "
                    f"before the milestone ships. F5 evidence: {evidence_path}."),
                options_md=("- confirm: ship\n- reject\n\n(human writes "
                            "`confirm: ship|reject` + optional notes)"),
            )
            self._audit("acceptance_advisory_pass_signoff",
                        {"subsprint_id": self.state.subsprint_id,
                         "authoritative": False,
                         "acceptance_mode": self._acceptance_mode(),
                         "calibration_status": self._calibration_status(),
                         "checkpoint": os.path.relpath(path, self.run_dir)})
            self.state.state = STATE_HALTED
            self._save_state()
            return

        if mv == "fix_required":
            # §3.5: write the human-confirm checkpoint with the 3 route options;
            # HALT. The route to Deliver is NEVER taken without this checkpoint.
            acc = ((self.charter.get("tooling") or {}).get("acceptance") or {})
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
            coerced = (f" The driver's §3.2 consistency gate COERCED this to needs_human "
                       f"(a pass would contradict the captured evidence): "
                       f"{consistency_reason}." if consistency_reason else "")
            path = self._write_checkpoint(
                "acceptance_surface_approve", self.state.subsprint_id,
                context_md=(
                    f"Acceptance milestone_verdict = needs_human on sub-sprint "
                    f"{self.state.subsprint_id}: the Acceptance Agent could not "
                    f"reach an autonomous verdict and surfaces the decision to the "
                    f"Customer (surface_approve).{coerced} Evidence: {evidence_path}."),
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
