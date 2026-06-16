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
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

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
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_KIT_DIR = os.path.dirname(_THIS_DIR)           # engine-kit/
_AUDIT_DIR = os.path.join(_ENGINE_KIT_DIR, "audit")
for _p in (_ENGINE_KIT_DIR, _AUDIT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402  (engine-kit/audit/audit_log.py)
from adapters import ADAPTER_REGISTRY, Adapter, AdapterError  # noqa: E402

# P3 INTEGRATION 1 — the standalone Loop Controller (engine-kit/orchestrator/
# loop_controller.py) is the fix-loop termination AUTHORITY. The driver builds a
# LoopState from RunState + charter + the verdict and asks decide() what to do;
# it owns the side effects (spawn / checkpoint / audit). Imported read-only.
import loop_controller as lc  # noqa: E402

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


def load_charter(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("charter root must be a mapping/object")
    return data


def route_for_role(charter: dict, role: str) -> RoleRouting:
    """Read tooling.<role>.{harness|agent_kind, provider, model, tools} leniently.

    Accepts the plan §5 field ``harness`` and also the legacy ``agent_kind`` as a
    fallback (templates/fixtures still use agent_kind) so the demo charter and an
    existing charter both route. Missing fields default to empty strings; the
    adapter registry lookup (below) is what enforces a known harness.
    """
    tooling = charter.get("tooling") or {}
    rc = tooling.get(role) or {}
    harness = rc.get("harness") or rc.get("agent_kind") or ""
    return RoleRouting(
        role=role,
        harness=str(harness),
        provider=str(rc.get("provider") or ""),
        model=str(rc.get("model") or ""),
        tools=list(rc.get("tools") or []),
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
    ):
        self.charter = charter
        self.run_dir = os.path.abspath(run_dir)
        self.adapters = adapters
        self.loop_id = loop_id
        self.clock = clock
        self.schemas = verdict_schemas or load_verdict_schemas()
        self.context = context or {}

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

        os.makedirs(self.orch_dir, exist_ok=True)
        os.makedirs(self.checkpoints_dir, exist_ok=True)
        os.makedirs(self.audit_dir, exist_ok=True)

        self.budget = charter.get("budget") or {}
        self.autonomy = charter.get("autonomy") or {}
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
        fname = f"{safe_ts}__{checkpoint_id}__{scope}.md"
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

        self.state.spawn_count += 1
        try:
            verdict = adapter.spawn(role, prompt, routing.tools,
                                    self.schemas.get(schema_key, {}) if schema_key else {})
        except AdapterError as exc:
            self._audit("spawn", audit.make_spawn_payload(
                role=role, harness=adapter.harness, provider=adapter.provider,
                model=adapter.model, input_hash=input_hash,
                memory_injected=injected,
                run_mode=self.autonomy.get("level", "human_in_the_loop"),
                verdict_ref="adapter_error"))
            raise self._gate_hard_fail(
                f"adapter for role {role!r} failed: {exc}", self.state.state)

        # Validate if this spawn carries a verdict schema (spawn_dev does not).
        if schema_key is not None:
            err = validate_verdict(verdict, self.schemas[schema_key])
            self._audit("spawn", audit.make_spawn_payload(
                role=role, harness=adapter.harness, provider=adapter.provider,
                model=adapter.model, input_hash=input_hash,
                memory_injected=injected,
                run_mode=self.autonomy.get("level", "human_in_the_loop"),
                verdict_ref="invalid" if err else "valid"))
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
                verdict_ref="artifact"))
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

    # ----- state-machine steps --------------------------------------------- #
    def _step_dev(self) -> None:
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
        else:
            if subsprint_id is None:
                raise ValueError("subsprint_id required for a fresh run")
            self.state = RunState(loop_id=self.loop_id, subsprint_id=subsprint_id)
            self._audit("loop_start", {
                "charter_mission": (self.charter.get("mission") or {}).get("id"),
                "subsprint_id": subsprint_id,
                "autonomy": self.autonomy.get("level", "human_in_the_loop"),
                "context": self.context,
            })
            self.state.state = STATE_DEV_PENDING

        self._save_state()
        self._drive()
        return self.state

    def _drive(self) -> None:
        """Execute remaining states in linear order from self.state.state."""
        assert self.state is not None
        # Find resume index in the linear order; advance/done short-circuit.
        order = LOOP_ORDER
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
        self._audit("acceptance_spawn", {
            "role": "acceptance", "harness": adapter.harness,
            "provider": adapter.provider, "model": adapter.model,
            "evidence_path": evidence_path,
            "calibration_status": calibration_status,
            "run_mode": self.autonomy.get("level", "human_in_the_loop"),
            "input_hash": input_hash,
            # §1.7-C: this spawn surface is the orchestrator (NOT a Dev/Deliver
            # session) and is gated by the calibration check above.
            "spawn_surface": "orchestrator",
        })
        try:
            verdict = adapter.spawn(
                "acceptance", prompt, routing.tools, self.schemas["acceptance"])
        except AdapterError as exc:
            raise self._gate_hard_fail(
                f"acceptance adapter failed: {exc}", STATE_ACCEPTANCE_PENDING)
        err = validate_verdict(verdict, self.schemas["acceptance"])
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
