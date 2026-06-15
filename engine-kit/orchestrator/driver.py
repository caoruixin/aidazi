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
from typing import Any, Callable, Optional

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


# --------------------------------------------------------------------------- #
# States + a typed control-flow error for the gate_hard_fail MANDATORY_CHECKPOINT.
# --------------------------------------------------------------------------- #
STATE_IDLE = "idle"
STATE_DEV_PENDING = "dev_pending"
STATE_GATE_PENDING = "gate_pending"
STATE_REVIEW_PENDING = "review_pending"
STATE_CLOSE_PENDING = "close_pending"
STATE_ADVANCE = "advance"
STATE_DONE = "done"
STATE_HALTED = "halted"

# Linear MVP order (no Acceptance state — that is P3).
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
    """Return {role_or_fn: schema} for the two verdicts the P2 driver parses."""
    base = schemas_dir or _find_schemas_dir()
    if not base:
        raise FileNotFoundError(
            "schemas/ directory not found at or above engine-kit/"
        )
    out: dict[str, dict] = {}
    for key, fname in (
        ("review", "review-verdict.schema.json"),
        ("close", "deliver-close-verdict.schema.json"),
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

    def to_dict(self) -> dict:
        return {
            "loop_id": self.loop_id,
            "subsprint_id": self.subsprint_id,
            "state": self.state,
            "fix_round": self.fix_round,
            "spawn_count": self.spawn_count,
            "history": list(self.history),
            "last_verdict": self.last_verdict,
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
    ):
        self.charter = charter
        self.run_dir = os.path.abspath(run_dir)
        self.adapters = adapters
        self.loop_id = loop_id
        self.clock = clock
        self.schemas = verdict_schemas or load_verdict_schemas()
        self.context = context or {}

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
                          context_md: str, options_md: str) -> str:
        ts = self.clock()
        safe_ts = ts.replace(":", "").replace("-", "").replace("T", "-")
        # squeeze "Z"/offset to keep the filename clean & deterministic
        safe_ts = safe_ts.split(".")[0].rstrip("Z")
        fname = f"{safe_ts}__{checkpoint_id}__{scope}.md"
        path = os.path.join(self.checkpoints_dir, fname)
        body = (
            "---\n"
            f"checkpoint_id: {checkpoint_id}\n"
            f"scope: {scope}\n"
            f"emitted_at: {ts}\n"
            "decision: pending\n"
            "resolved_at: null\n"
            "resolver: null\n"
            "---\n\n"
            "# Context\n"
            f"{context_md}\n\n"
            "# Options\n"
            f"{options_md}\n\n"
            "# Decision (human fills)\n"
            "<human writes; orchestrator picks up>\n"
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

        self.state.spawn_count += 1
        try:
            verdict = adapter.spawn(role, prompt, routing.tools,
                                    self.schemas.get(schema_key, {}) if schema_key else {})
        except AdapterError as exc:
            self._audit("spawn", audit.make_spawn_payload(
                role=role, harness=adapter.harness, provider=adapter.provider,
                model=adapter.model, input_hash=input_hash,
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

    # ----- state-machine steps --------------------------------------------- #
    def _step_dev(self) -> None:
        verdict = self._spawn(
            "dev",
            f"Implement sub-sprint {self.state.subsprint_id}; write the handoff.",
            schema_key=None,  # spawn_dev's artifact IS the code+handoff, no verdict schema
        )
        self.state.history.append(STATE_DEV_PENDING)

    def _step_gate(self) -> None:
        self._run_gates()
        self.state.history.append(STATE_GATE_PENDING)

    def _step_review(self) -> dict:
        verdict = self._spawn(
            "review",
            f"Review sub-sprint {self.state.subsprint_id}. Emit a review-verdict.",
            schema_key="review",
        )
        self.state.history.append(STATE_REVIEW_PENDING)
        return verdict

    def _step_close(self) -> dict:
        verdict = self._spawn(
            "deliver",
            f"Close sub-sprint {self.state.subsprint_id}. Emit a deliver-close-verdict.",
            schema_key="close",
        )
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

    def _handle_fix_required(self, review_verdict: dict) -> None:
        """Review said fix_required. Bound the fix round (§4.4); in P2
        human_in_the_loop we surface a gate_hard_fail checkpoint (auto-fix is a
        later-phase capability) so the human routes the fix. Bump the counter and
        check the budget so an over-limit run halts deterministically."""
        assert self.state is not None
        self.state.fix_round += 1
        self._save_state()
        self._audit("review_fix_required",
                    {"blocking_count": review_verdict.get("blocking_count"),
                     "fix_round": self.state.fix_round})
        self._check_budget()  # raises BudgetExceeded → gate_hard_fail if over cap
        # P2 MVP: no auto-fix iteration; route to human via a checkpoint.
        path = self._write_checkpoint(
            "gate_hard_fail", self.state.subsprint_id,
            context_md=(f"Code Reviewer returned fix_required "
                        f"({review_verdict.get('blocking_count')} blocking) on fix_round "
                        f"{self.state.fix_round}. Auto-fix iteration is not enabled in the "
                        f"P2 MVP (human_in_the_loop)."),
            options_md="- deliver_fix_iteration\n- abort",
        )
        self.state.state = STATE_HALTED
        self._save_state()

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
