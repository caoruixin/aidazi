#!/usr/bin/env python3
"""run_loop — the harness-agnostic schedule ENTRYPOINT (plan §4.4 / P5-B).

The master plan fixes scheduling as **plain cron / CI, NOT any harness's own
scheduler** ("scheduling | framework | plain cron / CI (not ScheduleWakeup)").
This module is that framework-owned outer wrapper: a thin Python entrypoint a
cron job or CI workflow invokes to run ONE delivery loop end-to-end:

    load charter → build adapters → construct Driver → run → verify audit chain
    → print a concise summary → exit non-zero on a non-clean terminal state.

It supports two scheduled triggers via ``--mode``:
  * ``overnight_autoloop``   — an overnight Type-A Auto Loop run;
  * ``milestone_delivery``   — a milestone Delivery Loop run.
For the deterministic kernel these are the SAME ``Driver.run(...)`` call; the
mode is a label recorded in the loop_start audit context (it differs in WHICH
charter / schedule invokes it, not in the run mechanics).

DETERMINISM: this is an OUTER wrapper, NOT part of the deterministic kernel
(driver.py). The only wall-clock read is the injected PRODUCTION clock created in
``main`` (the kernel stays pure because the clock is injected); tests inject a
deterministic clock + mock adapters, so the whole path is reproducible offline.

REAL vs MOCK adapters: ``build_adapters(charter, allow_real=False)`` builds a
MockAdapter per role with a clean-pass canned verdict set by DEFAULT (a safe
offline dry-run / smoke test). With ``--allow-real`` it builds real adapters from
ADAPTER_REGISTRY; those still refuse to touch the network/subprocess unless
``AIDAZI_ALLOW_REAL_ADAPTER=1`` (the adapters' own gate). Artifacts go to a RUN DIR
that defaults to ``<repo>/.runs/<loop_id>`` — inside the repo for discoverability but
gitignored (``.runs/``) so they never enter the delivered diff; ``--run-dir`` overrides.

NORMATIVE SOURCE: archive/2026-06-15-v2-loop-engine-plan.md §4.4 / P5. The kit is
a reference implementation; on any conflict the spec wins and this file is the bug.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Callable, Dict, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # engine-kit/scheduling
_ENGINE_KIT_DIR = os.path.dirname(_THIS_DIR)                    # engine-kit/
for _p in (
    _ENGINE_KIT_DIR,
    os.path.join(_ENGINE_KIT_DIR, "audit"),
    os.path.join(_ENGINE_KIT_DIR, "orchestrator"),
    os.path.join(_ENGINE_KIT_DIR, "validators"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
from adapters import MockAdapter, resolve_adapter_class  # noqa: E402
from driver import (  # noqa: E402
    Driver, load_charter, route_for_role,
    LOOP_MODE_DELIVERY_ONLY, LOOP_MODE_FULL_CHAIN_GUIDED,
)

MODE_OVERNIGHT_AUTOLOOP = "overnight_autoloop"
MODE_MILESTONE_DELIVERY = "milestone_delivery"
MODES = (MODE_OVERNIGHT_AUTOLOOP, MODE_MILESTONE_DELIVERY)

# P6.1 — the loop-mode CLI choices (mirrors the Driver's loop_mode param).
LOOP_MODES = (LOOP_MODE_DELIVERY_ONLY, LOOP_MODE_FULL_CHAIN_GUIDED)

# --- campaign (--campaign) exit codes — STABLE machine-readable contract ------ #
# A campaign is multi-invocation: exit 0 ONLY when the whole backlog is done; a
# pause (awaiting a human gate) is a DISTINCT non-zero so cron/CI can tell "done"
# from "needs a human" from "error/invalid". Documented in process/campaign-loop.md.
CAMPAIGN_EXIT_DONE = 0      # backlog exhausted — the whole goal is delivered
CAMPAIGN_EXIT_ERROR = 1     # unexpected runtime error (or an unreachable 'running' leak)
CAMPAIGN_EXIT_INVALID = 2   # invalid plan/state/schema (fail-closed; matches the single-loop charter-error code)
CAMPAIGN_EXIT_PAUSED = 10   # paused at a human-authority gate — resolve, then --resume
CAMPAIGN_EXIT_ENDED = 11    # aborted — a human/abort decision ended the campaign

# Default clean-pass canned verdicts for the offline DRY-RUN mock path. These let
# a scheduled dry-run exercise the full P2 happy path (dev→gate→review→close→
# advance) with zero network. A real run uses --allow-real and never sees these.
_DRY_REVIEW = {"decision": "pass", "blocking_count": 0,
               "summary": "dry-run: no blocking findings", "findings": []}
_DRY_CLOSE = {"verdict": "A", "blocking_count": 0, "worst_severity": "none",
              "in_scope": True, "next_subsprint": None,
              "reason": "dry-run clean pass"}
_DRY_DEV = {"artifact": "dry-run handoff"}
# P6.1 — a dry-run deliver-plan for full_chain_guided decompose. Modules/layers
# are left EMPTY so the scope-expansion guard treats the plan as defining scope
# (no signed envelope to widen) on a charter with no approved_scope — a safe
# offline default. A real run uses --allow-real + a real Deliver plan.
_DRY_PLAN = {"sub_sprints": [{
    "id": "sprint-001", "objective": "dry-run sub-sprint",
    "scope_in": [], "scope_out": [], "modules": [], "layers": [],
    "exit_criteria": []}]}


def _roles_in_charter(charter: dict) -> list:
    """The roles the charter routes (tooling.<role>), excluding non-role keys."""
    tooling = charter.get("tooling") or {}
    return [r for r in ("research", "deliver", "dev", "review", "acceptance")
            if r in tooling]


def load_local_env(*, root: str = ".",
                   filenames=(".env.local", ".env")) -> list:
    """Load ``KEY=VALUE`` lines from ``.env.local`` (then ``.env``) under ``root``
    into ``os.environ`` WITHOUT overriding already-exported vars.

    This is the framework's one supported way to feed provider **base URLs and API
    keys** to the headless harness from a file instead of exporting by hand: the
    adopter keeps them in a gitignored ``.env.local`` and the charter references
    them BY NAME (``api_key_env`` / ``endpoint_env``). An already-exported var
    always wins (export > file), so CI secret stores keep precedence. Secret
    VALUES are never written to the charter or any committed file; this loader
    only moves them from a gitignored file into the process environment, where the
    headless adapter reads them at call time. Zero deps (no python-dotenv): a
    minimal parser — ``#`` comments, optional ``export`` prefix, optional matched
    surrounding quotes. Returns the list of files actually loaded (for the run
    summary). Mock dry-runs need no keys and never call this.
    """
    loaded = []
    for name in filenames:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    if key.startswith("export "):
                        key = key[len("export "):].strip()
                    val = val.strip()
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                        val = val[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = val
            loaded.append(path)
        except OSError:
            continue
    return loaded


class CharterValidationError(ValueError):
    """A ``--allow-real`` charter has BLOCKING schema-validation errors. Raised
    BEFORE any adapter is built/invoked, so an invalid charter cannot reach a live
    (billed) model. Warnings do NOT raise this; only errors do."""


def charter_validation_report(charter: dict):
    """Return the ``charter_validator`` Report for ``charter``, or None when the
    validator / jsonschema is unavailable. Shared by the enforcement gate and the
    summary. Never raises (a missing validator ⇒ None, caller decides)."""
    try:
        import charter_validator as _cv  # noqa: E402,WPS433
        return _cv.validate_charter(charter)
    except Exception:  # noqa: BLE001 - validator/jsonschema absent ⇒ None
        return None


def _report_ok(report) -> bool:
    ok = getattr(report, "ok", True)
    return ok() if callable(ok) else bool(ok)


def _charter_issue_lines(issues, limit: int = 10) -> list:
    issues = list(issues)
    lines = []
    for issue in issues[:limit]:
        rule = getattr(issue, "rule", "")
        msg = getattr(issue, "message", None) or str(issue)
        lines.append(f"    - {rule}: {str(msg)[:120]}")
    if len(issues) > limit:
        lines.append(f"    ... (+{len(issues) - limit} more)")
    return lines


def enforce_charter_for_real_run(charter: dict) -> None:
    """ENFORCE the charter schema for a real (``--allow-real``) run: raise
    ``CharterValidationError`` on ANY blocking error, BEFORE any adapter is built or
    invoked, so an invalid charter never reaches a live model. Warnings do NOT block
    (the caller surfaces them). A None report (validator / jsonschema unavailable)
    does NOT block — the deterministic runtime checks (per-role sandbox defaults,
    ``timeout_seconds`` typing, codex fail-closed) remain the defense-in-depth gate.

    NOTE: the driver still reads the charter LENIENTLY at runtime (a v2 charter may
    use ``harness`` without the legacy schema-required ``agent_kind``); this gate is
    the explicit, real-run-only enforcement layer ON TOP of that lenient read."""
    report = charter_validation_report(charter)
    if report is None or _report_ok(report):
        return
    errors = list(getattr(report, "errors", []) or [])
    raise CharterValidationError(
        "charter has blocking schema-validation error(s); refusing the real run "
        "BEFORE any adapter is invoked:\n" + "\n".join(_charter_issue_lines(errors)))


def advisory_validate_charter(charter: dict) -> Optional[str]:
    """Non-raising one-shot schema SUMMARY string (for visibility without
    enforcement). Real-run ENFORCEMENT lives in ``enforce_charter_for_real_run``
    (raises) and ``main`` (blocks + exit 2). Returns None when the validator is
    unavailable; never raises."""
    report = charter_validation_report(charter)
    if report is None:
        return None
    errors = list(getattr(report, "errors", []) or [])
    warnings = list(getattr(report, "warnings", []) or [])
    if _report_ok(report) and not warnings:
        return "schema clean"
    return (f"{len(errors)} error(s), {len(warnings)} warning(s)\n"
            + "\n".join(_charter_issue_lines(errors + warnings)))


def build_adapters(charter: dict, *, allow_real: bool = False,
                   loop_mode: str = LOOP_MODE_DELIVERY_ONLY) -> Dict[str, object]:
    """Build one adapter per routed role from the charter's per-role routing.

    DEFAULT (``allow_real=False``) → a MockAdapter per role carrying a clean-pass
    canned verdict (offline dry-run / smoke test). With ``allow_real=True`` →
    the real adapter class from ADAPTER_REGISTRY for the role's harness, carrying
    its provider/model (+ endpoint as base_url and api_key_env when present). Real
    adapters still refuse I/O unless AIDAZI_ALLOW_REAL_ADAPTER=1 (their own gate),
    so building them is safe; only spawning with the env set reaches the network.

    In full_chain_guided the deliver role serves BOTH the decompose (call_index 0
    → deliver-plan) and the per-sub-sprint close (later calls → deliver-close), so
    the mock is keyed accordingly. In delivery_only the deliver role is only ever
    spawned for close, so its sole canned response is the close verdict (byte-
    identical to the pre-P6.1 dry-run).
    """
    deliver_canned = {("deliver",): _DRY_CLOSE}
    if loop_mode == LOOP_MODE_FULL_CHAIN_GUIDED:
        # ("deliver",0)=decompose plan; ("deliver",)=close for every later call.
        deliver_canned = {("deliver", 0): _DRY_PLAN, ("deliver",): _DRY_CLOSE}
    canned_by_role = {
        "dev": {("dev",): _DRY_DEV},
        "review": {("review",): _DRY_REVIEW},
        "deliver": deliver_canned,
        "research": {("research",): _DRY_DEV},  # research drafts an ARTIFACT
    }
    adapters: Dict[str, object] = {}
    for role in _roles_in_charter(charter):
        r = route_for_role(charter, role)
        if allow_real:
            cls = resolve_adapter_class(r.harness or "mock", role=role)
            # Pass the union of routing kwargs; each adapter picks what it needs
            # (extras land in Adapter.config harmlessly). endpoint → base_url for
            # the OpenAI-compatible headless adapter.
            tooling = (charter.get("tooling") or {}).get(role) or {}
            # base_url: the literal `endpoint` wins; else resolve `endpoint_env`
            # from the environment (.env.local is loaded in main() for real runs).
            # The API key is NEVER read here — the headless adapter reads it from
            # os.environ[api_key_env] at call time, by NAME, and never stores it.
            base_url = tooling.get("endpoint", "")
            if not base_url and tooling.get("endpoint_env"):
                base_url = os.environ.get(tooling["endpoint_env"], "")
            kwargs = dict(
                provider=r.provider or "",
                model=r.model or "",
                base_url=base_url,
                api_key_env=tooling.get("api_key_env", ""),
            )
            if r.reasoning_effort:
                kwargs["reasoning_effort"] = r.reasoning_effort
            # Per-spawn timeout is configurable per role (charter
            # tooling.<role>.timeout_seconds); absent ⇒ the adapter's own default
            # (600s). A real Dev coding session typically needs more than that. A
            # PRESENT value MUST be a positive int — reject bool / string / "1800"
            # LOUDLY rather than silently falling back to the default. (The charter
            # is loaded leniently; on a real run this is the last line of defense if
            # the validator was not run — see main()'s --allow-real validation.)
            if "timeout_seconds" in tooling:
                ts = tooling["timeout_seconds"]
                if isinstance(ts, bool) or not isinstance(ts, int) or ts < 1:
                    raise ValueError(
                        f"charter tooling.{role}.timeout_seconds must be a positive "
                        f"integer (seconds); got {ts!r}")
                kwargs["timeout_seconds"] = ts
            adapters[role] = cls(**kwargs)
        else:
            adapters[role] = MockAdapter(
                canned_by_role.get(role, {(role,): _DRY_DEV}),
                harness=r.harness or "mock",
                provider=r.provider or "mock",
                model=r.model or "mock-model",
            )
    return adapters


def make_interactive_gate_resolver() -> Callable[[str, dict, "object"],
                                                  Optional[dict]]:
    """A DEFAULT interactive gate resolver for full_chain_guided runs at a TTY.

    This is the HUMAN's voice (injected into the Driver like ``clock``): it prints
    the gate context + options and reads the human's choice + optional note from
    stdin — a SELECTION, not a file-edit. It returns
    {"choice": ..., "note": ..., "resolver": "interactive_cli"} or None (None →
    the driver HALTS for async resolution). The engine never auto-signs; this
    resolver only relays an explicit human choice.

    NOT used in tests / offline runs (those pass delivery_only or inject their own
    resolver) — it is wired only when --loop-mode full_chain_guided runs at a TTY.
    """
    def _resolve(gate_id: str, context: dict, options) -> Optional[dict]:
        opts = list(options)
        print(f"\n=== HUMAN GATE: {gate_id} ===")
        import json as _json
        print(_json.dumps(context, indent=2, sort_keys=True, default=str))
        print(f"\nOptions: {', '.join(opts)}")
        try:
            choice = input(f"Your choice [{'/'.join(opts)}] "
                           "(blank = halt for later): ").strip()
        except EOFError:
            return None
        if not choice or choice not in opts:
            # Blank or unrecognized → no decision → the driver HALTS (async).
            return None
        try:
            note = input("Optional note: ").strip()
        except EOFError:
            note = ""
        return {"choice": choice, "note": note, "resolver": "interactive_cli"}

    return _resolve


# --------------------------------------------------------------------------- #
# Campaign mode (--campaign): drive a multi-milestone backlog to completion via
# the production path make_run_unit -> run_loop -> the real Driver (campaign.py).
# This is the WIRED entrypoint for continuous multi-milestone delivery (以终为始);
# the single-loop path (run_loop/main below) drives ONE sub-sprint. The Driver and
# the campaign runner are UNCHANGED — this only wires them to a CLI + a file-based
# human-gate decision channel. Spec: process/campaign-loop.md.
# --------------------------------------------------------------------------- #
def make_campaign_decision_resolver(campaign_id: Optional[str],
                                    decision_path: Optional[str],
                                    campaign_home: str) -> Callable:
    """A FILE-BASED ``decision_resolver`` for ``--campaign --resume``: returns
    ``resolve(pause_reason, checkpoint_path) -> Optional[dict]`` that reads the
    human's decision from ``decision_path`` (JSON), validates it against
    ``schemas/campaign-decision.schema.json``, and FAIL-CLOSED enforces full IDENTITY
    BINDING — the decision is honored ONLY when ALL of: ``campaign_id`` + the live
    ``pause_reason`` + the ``checkpoint`` (basename, exact) match, AND — when the pause
    is on a UNIT (the common case) — the live paused unit's ``milestone_id`` +
    ``subsprint_id`` (read from ``campaign-state.json``) match. So a stale decision from
    a DIFFERENT milestone/sub-sprint/gate — even one whose checkpoint basename collides
    (a repeated sub-sprint id, a clock tie) — can never be replayed. A missing/
    unreadable/parse-broken file, a schema violation, or ANY binding mismatch ⇒ None
    (the gate is NOT resolved; the runner re-pauses) with a stderr diagnostic.
    ``decision_path`` None ⇒ always None.

    It passes the runner's decision fields through: ``choice`` for a dispatch-table
    gate, OR ``confirm`` (+ ``route``) for the acceptance_fix_required gate (§3.5).

    Gates resolved by editing the PLAN (campaign_plan_signoff,
    milestone_decompose_required, deliver_followup_required) never reach this
    resolver — the runner re-checks plan state for those (campaign.py)."""
    def _paused_unit(checkpoint_path: Optional[str]) -> Optional[dict]:
        """The live paused unit (milestone_id + subsprint_id) from the persisted
        campaign-state — matched by its checkpoint_path. None for a checkpoint-less
        pause (no unit, e.g. campaign_budget_exhausted) or an unreadable state."""
        if not checkpoint_path:
            return None
        try:
            with open(os.path.join(campaign_home, "campaign-state.json"),
                      encoding="utf-8") as fh:
                state = json.load(fh)
        except (OSError, ValueError):
            return None
        for u in reversed(state.get("units") or []):
            if isinstance(u, dict) and u.get("checkpoint_path") == checkpoint_path:
                return u
        return None

    def resolve(pause_reason: str, checkpoint_path: Optional[str]) -> Optional[dict]:
        if not decision_path:
            return None
        try:
            with open(decision_path, encoding="utf-8") as fh:
                decision = json.load(fh)
        except (OSError, ValueError) as exc:
            sys.stderr.write(
                f"campaign decision: cannot read/parse {decision_path!r}: {exc}\n")
            return None
        import campaign as _cp  # lazy: campaign imports run_loop (avoid the cycle)
        try:
            _cp._validate_or_raise(decision, "campaign-decision.schema.json",
                                   "decision")
        except ValueError as exc:
            sys.stderr.write(f"campaign decision: schema-invalid: {exc}\n")
            return None

        def _reject(what: str, got, want) -> None:
            sys.stderr.write(f"campaign decision: {what} {got!r} != live {want!r} "
                             f"— stale/mismatched, refusing (fail-closed)\n")
            return None

        if decision.get("campaign_id") != campaign_id:
            return _reject("campaign_id", decision.get("campaign_id"), campaign_id)
        if decision.get("pause_reason") != pause_reason:
            return _reject("pause_reason", decision.get("pause_reason"), pause_reason)
        live_cpt = os.path.basename(checkpoint_path) if checkpoint_path else None
        if decision.get("checkpoint") != live_cpt:   # EXACT (no falsy coercion)
            return _reject("checkpoint", decision.get("checkpoint"), live_cpt)
        if pause_reason == "milestone_merge":
            # Campaign-tier merge gate: binds to milestone_id only (no subsprint).
            try:
                with open(os.path.join(campaign_home, "campaign-state.json"),
                          encoding="utf-8") as fh:
                    state = json.load(fh)
            except (OSError, ValueError):
                sys.stderr.write(
                    "campaign decision: cannot read campaign-state for "
                    "milestone_merge — refusing (fail-closed)\n")
                return None
            live_mid = (state.get("milestone_context") or {}).get("milestone_id")
            if decision.get("milestone_id") != live_mid:
                return _reject("milestone_id", decision.get("milestone_id"), live_mid)
            if decision.get("subsprint_id") is not None:
                sys.stderr.write(
                    "campaign decision: milestone_merge must not carry "
                    "subsprint_id — refusing (fail-closed)\n")
                return None
            out = {k: decision[k] for k in ("choice", "note") if k in decision}
            return out or None
        if checkpoint_path is not None:
            # A checkpoint-bearing pause is ALWAYS on a unit: its milestone/sub-sprint
            # identity MUST be resolvable from campaign-state.json AND match. A missed
            # lookup (unreadable/tampered state, or no unit with this checkpoint_path)
            # FAILS CLOSED — never bound loosely as if it were checkpoint-less.
            unit = _paused_unit(checkpoint_path)
            if unit is None:
                sys.stderr.write(
                    "campaign decision: cannot resolve the live paused unit from "
                    "campaign-state.json for a checkpoint pause — refusing "
                    "(fail-closed)\n")
                return None
            if decision.get("milestone_id") != unit.get("milestone_id"):
                return _reject("milestone_id", decision.get("milestone_id"),
                               unit.get("milestone_id"))
            if decision.get("subsprint_id") != unit.get("subsprint_id"):
                return _reject("subsprint_id", decision.get("subsprint_id"),
                               unit.get("subsprint_id"))
        # else: checkpoint_path is None → a genuinely checkpoint-less pause (no unit,
        # e.g. campaign_budget_exhausted) → campaign_id + pause_reason + checkpoint:null.
        # Pass through the runner's decision fields: choice for a dispatch gate;
        # confirm/route for acceptance_fix_required; note for the audit; AND the
        # acceptance_cleanup_required residue-waiver fields (residue/rationale/evidence/
        # waiver/waiver_id) — WITHOUT these last five, a complete waiver authored in
        # campaign-decision.json would be stripped here and never reach
        # campaign.interpret_dispatch / residue_waiver, making accept_residue_and_ship
        # dead on the real CLI (Codex blocking 1). The schema scopes the waiver fields to
        # the cleanup gate, and the runtime ignores them on every other gate.
        out = {k: decision[k]
               for k in ("choice", "confirm", "route", "note",
                         "residue", "rationale", "evidence", "waiver", "waiver_id")
               if k in decision}
        return out or None
    return resolve


def resolve_ledger_path(charter: dict, repo_dir: Optional[str]) -> str:
    """The requirement-ledger path for this campaign (Δ-19). From
    charter.requirements.ledger_path (default ``docs/requirements-ledger.json``),
    resolved against ``repo_dir`` (else the CWD) when relative. Absent ledger file ⇒
    the requirement projection stays dormant (additive)."""
    req = (charter or {}).get("requirements") or {}
    rel = req.get("ledger_path") or "docs/requirements-ledger.json"
    if os.path.isabs(rel):
        return rel
    base = os.path.abspath(repo_dir) if repo_dir else os.getcwd()
    return os.path.join(base, rel)


def campaign_home_for(campaign_id: str, override: Optional[str] = None,
                      *, base: Optional[str] = None) -> str:
    """The STABLE home dir for a campaign's state/audit/units. It MUST persist
    across resume invocations — a fresh temp dir each run would lose the cursor and
    silently restart. ``override`` (--campaign-run-dir) wins; else a deterministic
    per-campaign dir under ``<base>/.runs/`` (``base`` defaults to the CWD — the
    adopter repo root the runner is launched from) so ``--resume`` finds the same
    campaign-state.json. Kept under the repo's gitignored ``.runs/`` (not the system
    temp) so a paused campaign is easy to find and survives a /tmp sweep, while
    ``.runs/`` in .gitignore keeps it out of git."""
    if override:
        return override
    root = os.path.abspath(base or os.getcwd())
    return os.path.join(root, ".runs", f"campaign-{campaign_id}")


def run_campaign_entry(plan: dict, charter: dict, *,
                       clock: Callable[[], str],
                       campaign_run_dir: Optional[str] = None,
                       resume: bool = False,
                       decision_path: Optional[str] = None,
                       allow_real: bool = False,
                       adapters: Optional[Dict[str, object]] = None,
                       repo_dir: Optional[str] = None,
                       memory_root: Optional[str] = None) -> dict:
    """Drive a CAMPAIGN (ordered milestone backlog) to completion or the next
    human-authority gate, via make_run_unit -> run_loop -> the REAL Driver. Returns
    a structured, machine-readable result dict carrying a STABLE ``exit_code``.

    ``adapters`` (tests) inject mocks; production passes ``allow_real`` and run_loop
    builds adapters per sub-sprint. The campaign HOME (state + audit + units) is kept
    STABLE across resume (see ``campaign_home_for``). FAIL-CLOSED: an invalid
    plan/state/schema (a ValueError from the campaign runner) ⇒ ``exit_code`` INVALID,
    never a partial/forged advance. Per-milestone Acceptance, budget caps, and
    resume integrity (no re-dispatch / no double-accounted Acceptance) are the
    campaign runner's guarantees (campaign.py); this only wires + reports them."""
    import campaign as _cp  # lazy (campaign imports run_loop)
    campaign_id = (plan or {}).get("campaign_id")
    home = campaign_home_for(campaign_id or "unidentified", campaign_run_dir,
                             base=repo_dir)
    units_dir = os.path.join(home, "units")
    run_loop_kwargs: Dict[str, object] = {}
    if repo_dir:
        run_loop_kwargs["repo_dir"] = repo_dir
    if memory_root:
        run_loop_kwargs["memory_root"] = memory_root
    if adapters is not None:
        run_loop_kwargs["adapters"] = adapters
    else:
        run_loop_kwargs["allow_real"] = allow_real

    # Δ-19: the requirement ledger (if the adopter wired one) — validated fail-closed by
    # the campaign runner at construction; the requirement projection below reads it.
    ledger_path = resolve_ledger_path(charter, repo_dir)

    base = {"campaign_id": campaign_id, "campaign_home": home, "units_dir": units_dir}
    try:
        run_unit = _cp.make_run_unit(charter, units_dir, campaign_id,
                                     clock=clock, plan=plan, **run_loop_kwargs)
        resolver = make_campaign_decision_resolver(campaign_id, decision_path, home)
        st = _cp.run_campaign(plan, home, run_unit, clock=clock,
                              resume=resume, decision_resolver=resolver,
                              repo_dir=repo_dir, charter=charter,
                              ledger_path=ledger_path)
    except ValueError as exc:
        # invalid plan / state / schema / mismatched campaign id / invalid ledger →
        # fail-closed.
        return {**base, "status": "invalid", "error": str(exc),
                "exit_code": CAMPAIGN_EXIT_INVALID}

    # The live paused unit's identity (so the human can author an identity-bound
    # decision); empty for a plan-edit gate / checkpoint-less pause with no unit.
    paused_unit: Dict[str, object] = {}
    if st.pause_checkpoint:
        for u in reversed(st.units or []):
            if isinstance(u, dict) and u.get("checkpoint_path") == st.pause_checkpoint:
                paused_unit = u
                break
    exit_code = {
        _cp.STATUS_DONE: CAMPAIGN_EXIT_DONE,
        _cp.STATUS_PAUSED: CAMPAIGN_EXIT_PAUSED,
        _cp.STATUS_ENDED: CAMPAIGN_EXIT_ENDED,
    }.get(st.status, CAMPAIGN_EXIT_ERROR)  # a returned 'running' is unreachable → error
    # Phase-0 scope-coverage projection (signed backlog vs delivered): a READ-ONLY
    # reporting nicety that must NEVER break the run — any failure degrades to None.
    # scope_report is a sibling of campaign on sys.path (same lazy-import contract);
    # a baseline, if the human froze one at sign-off, lives in the campaign home.
    scope_coverage = None
    try:
        import scope_report as _scope
        scope_coverage = _scope.summary_line(
            _scope.compute_coverage(plan, st.to_dict(),
                                    baseline=_scope.load_baseline(home)))
    except Exception:
        scope_coverage = None

    # Δ-19 requirement projection — emitted ONLY when a valid ledger is present (the
    # campaign already validated it fail-closed; reaching here ⇒ valid or absent). Like
    # scope_coverage it must NEVER break the run — any failure degrades to None.
    requirement_coverage = None
    if ledger_path and os.path.isfile(ledger_path):
        try:
            import scope_report as _scope
            with open(ledger_path, encoding="utf-8") as fh:
                ledger = json.load(fh)
            requirement_coverage = _scope.requirement_summary_line(
                _scope.compute_requirement_coverage(
                    plan, st.to_dict(), ledger, charter=charter))
        except Exception:
            requirement_coverage = None

    # F1: the live campaign_plan_signoff status (so a stale-signoff re-sign pause is
    # actionable, distinct from plain "unsigned"). Best-effort.
    try:
        signoff_status = _cp.signoff_status(plan, charter)
    except Exception:
        signoff_status = None

    return {
        **base,
        "status": st.status,
        "pause_reason": st.pause_reason,
        "pause_checkpoint": st.pause_checkpoint,
        "pause_milestone_id": paused_unit.get("milestone_id"),
        "pause_subsprint_id": paused_unit.get("subsprint_id"),
        "pause_loop_id": paused_unit.get("loop_id"),
        "milestone_index": st.milestone_index,
        "milestones_total": len(plan.get("milestones") or []),
        "subsprints_run": st.subsprints_run,
        "total_spawns": st.total_spawns,
        "exit_code": exit_code,
        "scope_coverage": scope_coverage,
        "requirement_coverage": requirement_coverage,
        "signoff_status": signoff_status,
        "milestone_outcomes": list(st.milestone_outcomes or []),
    }


def _campaign_resume_hint(result: dict) -> str:
    """One actionable line telling the human how to resolve THIS pause + resume."""
    reason = result.get("pause_reason")
    if reason == "campaign_plan_signoff":
        sstatus = result.get("signoff_status")
        if sstatus == "stale":
            return ("  -> STALE SIGNOFF: the signed scope-envelope hash no longer matches "
                    "the plan (a milestone/charter edit). Re-sign (re-stamp the snapshot): "
                    "re-run with --campaign <plan> --charter <charter> --sign-plan, then "
                    "--resume")
        if sstatus == "pre_f1":
            return ("  -> PRE-F1 plan (bare signed_by_human, no signoff snapshot). Stamp "
                    "the F1 snapshot once: re-run with --campaign <plan> --charter "
                    "<charter> --sign-plan, then --resume")
        return ('  -> sign the plan: set "signed_by_human": true (or, with a ledger / '
                'covers_req_ids, run --sign-plan to stamp the F1 snapshot), then re-run '
                "with --resume")
    if reason == "milestone_decompose_required":
        return ("  -> fill this milestone's subsprint_sequence in the plan, then "
                "re-run with --resume")
    if reason == "deliver_followup_required":
        return ("  -> Deliver inserts the follow-up sub-sprint into the milestone's "
                "sequence, then re-run with --resume")
    if reason == "milestone_merge":
        return ("  -> author a campaign-decision.json with "
                f'"choice": "merge_now"|"open_pr"|"keep_branch"|"abort" '
                f'and milestone_id, then re-run with --resume --decision <file>')
    cpt = result.get("pause_checkpoint")
    base = os.path.basename(cpt) if cpt else None
    ident = (f'"campaign_id": {result.get("campaign_id")!r}, '
             f'"milestone_id": {result.get("pause_milestone_id")!r}, '
             f'"subsprint_id": {result.get("pause_subsprint_id")!r}, '
             f'"pause_reason": {reason!r}, "checkpoint": {base!r}')
    payload = ('"confirm": "no" (ship advisory) | "yes" + "route" (fix)'
               if reason == "acceptance_fix_required" else '"choice": "<option>"')
    return ("  -> author an identity-bound decision file "
            f"(schemas/campaign-decision.schema.json): {{{ident}, {payload}}} "
            "then re-run with --resume --decision <file>")


def print_campaign_result(result: dict) -> None:
    """Human summary + a STABLE machine-readable status line (constraint: machine
    output). The ``CAMPAIGN_STATUS=`` prefix line is the parse contract."""
    status = result.get("status")
    print("=== aidazi campaign run ===")
    print(f"campaign id    : {result.get('campaign_id')}")
    print(f"campaign home  : {result.get('campaign_home')}")
    print(f"status         : {status}")
    if status == "invalid":
        print(f"error          : {result.get('error')}")
    else:
        print(f"milestones     : {result.get('milestone_index')}/"
              f"{result.get('milestones_total')} complete")
        print(f"spent          : subsprints={result.get('subsprints_run')} "
              f"spawns={result.get('total_spawns')}")
        cov = result.get("scope_coverage")
        if cov:
            remaining = cov.get("remaining_milestones") or []
            print(f"scope coverage : {cov.get('milestones_delivered')}/"
                  f"{cov.get('milestones_total')} milestones delivered "
                  f"({cov.get('pct_milestones_delivered')}%)"
                  + (f"  remaining={remaining}" if remaining else ""))
            if not cov.get("baseline_available"):
                print("               : baseline not frozen — added/removed delta off "
                      "(scope_report.py --freeze-baseline at campaign start)")
            elif cov.get("added_milestones"):
                print(f"               : added mid-flight={cov.get('added_milestones')}")
        rcov = result.get("requirement_coverage")
        if rcov:
            print(f"requirement cov: {rcov.get('delivered')}/"
                  f"{rcov.get('requirements_total')} requirements delivered  "
                  f"waived={rcov.get('waived')}  uncovered={rcov.get('uncovered')}"
                  f"  (signoff={rcov.get('signoff_status')})")
            if rcov.get("uncovered_requirements"):
                print(f"               : uncovered (PRD gap)="
                      f"{rcov.get('uncovered_requirements')}")
            if rcov.get("invalid_signed_disposition"):
                print(f"               : invalid_signed_disposition="
                      f"{rcov.get('invalid_signed_disposition')}")
            if rcov.get("stale_signoff"):
                print("               : STALE SIGNOFF — re-sign required "
                      "(prior signed coverage preserved)")
    if status == "paused":
        print(f"paused at      : {result.get('pause_reason')}")
        if result.get("pause_milestone_id"):
            print(f"paused unit    : milestone={result.get('pause_milestone_id')} "
                  f"subsprint={result.get('pause_subsprint_id')} "
                  f"loop={result.get('pause_loop_id')}")
        print(f"checkpoint     : {result.get('pause_checkpoint')}")
        print(_campaign_resume_hint(result))
    machine = {k: result.get(k) for k in (
        "campaign_id", "status", "pause_reason", "pause_checkpoint",
        "pause_milestone_id", "pause_subsprint_id", "pause_loop_id",
        "milestone_index", "milestones_total", "subsprints_run", "total_spawns",
        "exit_code")}
    print("CAMPAIGN_STATUS=" + json.dumps(machine, sort_keys=True))
    # Parallel, ADDITIVE parse contract (the CAMPAIGN_STATUS= line above stays
    # byte-identical) — emitted only when the scope-coverage projection succeeded.
    if result.get("scope_coverage"):
        print("SCOPE_COVERAGE=" + json.dumps(result["scope_coverage"], sort_keys=True))
    # Δ-19 parallel, ADDITIVE parse contract — emitted ONLY when a valid ledger is
    # present (CAMPAIGN_STATUS= / SCOPE_COVERAGE= stay byte-identical).
    if result.get("requirement_coverage"):
        print("REQUIREMENT_COVERAGE="
              + json.dumps(result["requirement_coverage"], sort_keys=True))


def run_loop(
    charter: dict,
    *,
    run_dir: str,
    loop_id: str,
    subsprint_id: str,
    clock: Callable[[], str],
    adapters: Optional[Dict[str, object]] = None,
    allow_real: bool = False,
    mode: str = MODE_MILESTONE_DELIVERY,
    repo_dir: Optional[str] = None,
    memory_root: Optional[str] = None,
    loop_mode: str = LOOP_MODE_DELIVERY_ONLY,
    gate_resolver: Optional[Callable] = None,
    resume: bool = False,
) -> dict:
    """Run ONE loop end-to-end and return a summary dict.

    ``adapters`` may be injected (tests pass mocks); otherwise they are built via
    ``build_adapters(charter, allow_real=...)``. ``clock`` is injected (production
    passes a real ISO clock; tests pass a deterministic one). ``mode`` is recorded
    in the loop_start audit context. ``repo_dir`` enables Loop Ingress;
    ``memory_root`` enables Loop Memory — both optional (off → byte-identical).
    ``loop_mode`` selects the P6.1 bootstrap (delivery_only DEFAULT → byte-
    identical; full_chain_guided adds the research → gate1 → decompose pre-states).
    ``gate_resolver`` is the injected human-voice for guided gates (tests pass a
    canned one; main() wires the interactive CLI resolver at a TTY).
    """
    if mode not in MODES:
        raise ValueError(f"mode {mode!r} not one of {MODES}")
    if adapters is None:
        # ENFORCE the charter schema BEFORE building any real adapter: an invalid
        # charter must never reach a live model. Mock dry-runs (allow_real=False)
        # skip this — example charters are intentionally schema-lenient.
        if allow_real:
            enforce_charter_for_real_run(charter)
        adapters = build_adapters(charter, allow_real=allow_real,
                                  loop_mode=loop_mode)

    driver = Driver(
        charter, run_dir, adapters,
        loop_id=loop_id, clock=clock,
        context={"schedule_mode": mode, "allow_real": allow_real,
                 "loop_mode": loop_mode},
        repo_dir=repo_dir, memory_root=memory_root,
        loop_mode=loop_mode, gate_resolver=gate_resolver,
    )
    final = driver.run(subsprint_id=subsprint_id, resume=resume)
    result = audit.verify_chain(driver.audit_ledger)
    clean = final.state in ("advance", "done")
    return {
        "mode": mode,
        "final_state": final.state,
        "clean": clean,
        "history": final.history,
        "spawn_count": final.spawn_count,
        "fix_round": final.fix_round,
        "audit_ledger": driver.audit_ledger,
        "audit_verifies": result.ok,
        "audit_render": result.render(),
        "run_dir": run_dir,
        "ok": clean and result.ok,
    }


def _production_clock() -> Callable[[], str]:
    """A real UTC ISO-8601 clock for production scheduled runs (the ONLY wall-clock
    read in this module; injected into the kernel so the kernel stays pure)."""
    from datetime import datetime, timezone

    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return _now


def _resolve_memory_root(cli_root: Optional[str], charter: dict,
                         charter_path: str) -> Optional[str]:
    """Resolve the effective Loop Memory root — the SINGLE source both entrypoints
    (single-loop and --campaign) share. Returns an absolute path to enable Loop
    Memory, or ``None`` to keep it OFF (byte-identical to no memory).

    Precedence + rules (all defaults applied EXPLICITLY here — a JSON-Schema
    ``default`` is documentation, NOT a runtime assignment):

    * CLI ``--memory-root`` WINS: it is an explicit enable AND override, honored even
      when the charter omits ``memory`` or sets ``enabled: false``. It keeps the CLI's
      existing path semantics — used verbatim, with NO charter-dir resolution and NO
      containment check (the operator owns an explicit, possibly-external path).
    * Else, charter-declared ``memory``: ``enabled`` must be literal ``true`` (absent
      ⇒ treated as ``false`` ⇒ OFF). ``root`` defaults to ``"memory"`` when absent or
      empty/whitespace. A RELATIVE ``root`` resolves against the charter's directory;
      the resolved path MUST stay CONTAINED within that directory — a ``..``/absolute
      escape is REJECTED (a declarative root must never write outside the adopter
      tree; use ``--memory-root`` for an external path). Lexical (normpath)
      containment; symlinks are not resolved.
    * Else ⇒ ``None`` (OFF).

    Raises ``ValueError`` on a declarative containment violation or a non-string root.
    """
    # CLI explicit enable + override — existing semantics, used verbatim, no
    # containment check. argparse's default is None, so an explicitly-passed
    # empty/whitespace value is a misuse → reject it (fail-closed) rather than
    # silently fall through to charter.memory.
    if cli_root is not None:
        if not cli_root.strip():
            raise ValueError("--memory-root must not be empty/whitespace")
        return cli_root

    mem = (charter or {}).get("memory")
    if not isinstance(mem, dict):
        return None
    # Absent ⇒ False ⇒ OFF; only a literal boolean True enables (fail-closed).
    if mem.get("enabled") is not True:
        return None

    root = mem.get("root")
    if root is None or (isinstance(root, str) and not root.strip()):
        root = "memory"  # EXPLICIT default (schema default ≠ runtime assignment)
    if not isinstance(root, str):
        raise ValueError(f"charter memory.root must be a string, got {type(root).__name__}")

    charter_dir = os.path.normpath(os.path.dirname(os.path.abspath(charter_path)))
    # normpath collapses '..' lexically; os.path.join honors an absolute root (which
    # then fails the containment check below — declarative roots stay in-tree).
    resolved = os.path.normpath(os.path.join(charter_dir, root))
    if resolved != charter_dir and not resolved.startswith(charter_dir + os.sep):
        raise ValueError(
            f"charter memory.root {root!r} escapes the charter directory "
            f"(resolved {resolved!r} is not within {charter_dir!r}); a declarative "
            f"root must stay inside the adopter tree — use --memory-root for an "
            f"external path")
    return resolved


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="aidazi schedule entrypoint — run one loop (plain cron/CI).")
    parser.add_argument("--charter", required=True, help="path to the charter YAML")
    parser.add_argument("--mode", choices=MODES, default=MODE_MILESTONE_DELIVERY)
    parser.add_argument("--loop-id", default=None,
                        help="loop_id (default: derived from mode + subsprint)")
    parser.add_argument("--subsprint-id", default="sprint-001")
    parser.add_argument("--run-dir", default=None,
                        help="run-artifact dir (default: <repo>/.runs/<loop_id>, "
                             "in-repo but gitignored)")
    parser.add_argument("--repo-dir", default=None,
                        help="git repo for Loop Ingress (optional; off by default)")
    parser.add_argument("--memory-root", default=None,
                        help="Loop Memory root (optional; off by default). Explicit "
                             "enable + override: WINS over charter.memory and is used "
                             "verbatim (no charter-dir resolution / containment check).")
    parser.add_argument("--loop-mode", choices=LOOP_MODES,
                        default=LOOP_MODE_DELIVERY_ONLY,
                        help="delivery_only (default) | full_chain_guided "
                             "(adds research → gate1 → decompose pre-states)")
    parser.add_argument("--allow-real", action="store_true",
                        help="build REAL adapters (still gated by AIDAZI_ALLOW_REAL_ADAPTER)")
    parser.add_argument("--campaign", default=None,
                        help="path to a campaign-plan.json — drive the WHOLE milestone "
                             "backlog (continuous multi-milestone delivery), not one sub-sprint")
    parser.add_argument("--campaign-run-dir", default=None,
                        help="STABLE campaign home (state+audit+units); MUST be the same "
                             "across --resume (default: <repo>/.runs/campaign-<id>)")
    parser.add_argument("--decision", default=None,
                        help="path to a campaign-decision.json resolving the current pause "
                             "(for --campaign --resume at a Mechanism-B gate)")
    parser.add_argument("--sign-plan", action="store_true",
                        help="Δ-19 F1: stamp the signed resolved-scope snapshot (signoff "
                             "block + signed_scope_hash) INTO the --campaign plan file and "
                             "exit. The campaign_plan_signoff re-sign action when a plan "
                             "uses covers_req_ids / is stale (uses --charter for the "
                             "resolved acceptance + charter hash).")
    parser.add_argument("--resume", action="store_true",
                        help="resume a paused run from its persisted state")
    args = parser.parse_args(argv)

    charter = load_charter(args.charter)

    # Resolve the effective Loop Memory root ONCE — shared by BOTH the campaign and the
    # single-loop entrypoints below (CLI --memory-root wins; else charter.memory when
    # enabled; else OFF). A declarative containment violation fails closed (exit 2).
    try:
        effective_memory_root = _resolve_memory_root(
            args.memory_root, charter, args.charter)
    except ValueError as exc:
        print(f"memory.root ERROR: {exc} — aborted before any run.")
        return 2

    # Campaign mode: drive the WHOLE milestone backlog (continuous multi-milestone
    # delivery, 以终为始) — NOT one sub-sprint. Pauses persist to the campaign home and
    # return a STABLE exit code; resolve the gate, then re-run with --resume.
    if args.campaign:
        try:
            with open(args.campaign, encoding="utf-8") as fh:
                plan = json.load(fh)
        except (OSError, ValueError) as exc:
            result = {"campaign_id": None, "campaign_home": None,
                      "status": "invalid", "error": f"unreadable plan: {exc}",
                      "exit_code": CAMPAIGN_EXIT_INVALID}
            print_campaign_result(result)
            return result["exit_code"]
        # Δ-19 F1 re-sign action: stamp the signed resolved-scope snapshot into the plan
        # file and exit. This is the human's voice at campaign_plan_signoff when the plan
        # uses covers_req_ids / a signoff block (the human cannot hand-compute the hash).
        if args.sign_plan:
            import campaign as _cp  # lazy (campaign imports run_loop)
            signed = _cp.stamp_signoff(plan, charter,
                                       signed_at=_production_clock()(),
                                       charter_ref=os.path.abspath(args.charter))
            try:
                _cp._validate_or_raise(signed, "campaign-plan.schema.json",
                                       "signed plan")
            except ValueError as exc:
                print(f"--sign-plan ERROR: stamped plan is schema-invalid: {exc}")
                return 2
            with open(args.campaign, "w", encoding="utf-8") as fh:
                json.dump(signed, fh, indent=2, sort_keys=True)
            print(f"--sign-plan: stamped F1 signoff snapshot into {args.campaign}")
            print(f"  signed_scope_hash={signed['signoff']['signed_scope_hash']}")
            print("  re-run with --resume to drive the signed plan.")
            return 0
        # Real runs resolve provider base URLs / API keys from .env.local (like the
        # single-loop path); mock dry-runs need none.
        if args.allow_real:
            for r in (os.path.dirname(os.path.abspath(args.campaign)),
                      os.path.dirname(os.path.abspath(args.charter)), os.getcwd()):
                if r:
                    load_local_env(root=r)
        result = run_campaign_entry(
            plan, charter, clock=_production_clock(),
            campaign_run_dir=args.campaign_run_dir, resume=args.resume,
            decision_path=args.decision, allow_real=args.allow_real,
            repo_dir=args.repo_dir, memory_root=effective_memory_root)
        print_campaign_result(result)
        return result["exit_code"]
    loop_id = args.loop_id or f"{args.mode}-{args.subsprint_id}"
    # Default run dir: <repo>/.runs/<loop_id> — INSIDE the repo for discoverability
    # (you can tail the live ledger/transcripts without hunting through /tmp) but
    # gitignored via `.runs/`, so the loop's own state/audit/transcripts never enter
    # the delivered diff. The base is --repo-dir when given (the adopter repo Loop
    # Ingress isolates), else the CWD the runner is launched from. --run-dir still
    # overrides with an explicit path. The Driver makedirs the tree on construction.
    run_dir = args.run_dir or os.path.join(
        os.path.abspath(args.repo_dir or os.getcwd()), ".runs", loop_id)

    # Real runs resolve provider base URLs / API keys from the environment. Load a
    # gitignored .env.local (then .env) from the charter's directory and the CWD so
    # the adopter can keep secrets in a file rather than exporting by hand; an
    # already-exported var always wins. Mock dry-runs need no keys and skip this.
    loaded_env = []
    if args.allow_real:
        roots = []
        for r in (os.path.dirname(os.path.abspath(args.charter)), os.getcwd()):
            if r and r not in roots:
                roots.append(r)
        for r in roots:
            loaded_env += load_local_env(root=r)

    # ENFORCE the charter schema on a real run: BLOCK (exit 2) on any error BEFORE
    # any adapter is invoked; warnings stay visible + non-blocking. Mock dry-runs
    # skip this (example charters are intentionally schema-lenient). A missing
    # validator does not block — the deterministic runtime checks still guard.
    charter_check = None
    if args.allow_real:
        report = charter_validation_report(charter)
        if report is None:
            charter_check = "skipped (validator/jsonschema unavailable; runtime checks enforce)"
        elif not _report_ok(report):
            errors = list(getattr(report, "errors", []) or [])
            print(f"charter ERRORS : {len(errors)} blocking schema error(s) — REAL RUN "
                  f"ABORTED before any adapter was invoked. Fix the charter, or drop "
                  f"--allow-real for a mock dry-run:")
            for ln in _charter_issue_lines(errors):
                print(ln)
            return 2
        else:
            warnings = list(getattr(report, "warnings", []) or [])
            charter_check = ("schema clean" if not warnings
                             else f"{len(warnings)} warning(s), 0 errors (non-blocking)")

    # P6.1: for an interactive full_chain_guided run, wire the DEFAULT CLI gate
    # resolver (prints the gate context + reads the human's selection from stdin).
    # The offline test path never reaches here (tests pass delivery_only OR inject
    # their own resolver); a non-TTY guided run leaves the resolver None → the
    # driver HALTS at Gate-1 for async resolution (never auto-signs).
    gate_resolver = None
    if (args.loop_mode == LOOP_MODE_FULL_CHAIN_GUIDED
            and sys.stdin is not None and sys.stdin.isatty()):
        gate_resolver = make_interactive_gate_resolver()

    info = run_loop(
        charter, run_dir=run_dir, loop_id=loop_id,
        subsprint_id=args.subsprint_id, clock=_production_clock(),
        allow_real=args.allow_real, mode=args.mode,
        repo_dir=args.repo_dir, memory_root=effective_memory_root,
        loop_mode=args.loop_mode, gate_resolver=gate_resolver,
        resume=args.resume,
    )

    print(f"=== aidazi schedule run ({info['mode']}) ===")
    print(f"run dir        : {info['run_dir']}")
    print(f"adapters       : {'real' if args.allow_real else 'mock (dry-run)'}")
    if args.allow_real:
        print(f"env files      : {', '.join(loaded_env) if loaded_env else '(none; exported env only)'}")
        print(f"charter check  : {charter_check}")
    print(f"state trace    : idle -> {' -> '.join(info['history'])} -> {info['final_state']}")
    print(f"final state    : {info['final_state']}  (clean={info['clean']})")
    print(f"spawn count    : {info['spawn_count']}  (fix rounds: {info['fix_round']})")
    print(f"audit ledger   : {info['audit_ledger']}")
    print(f"audit chain    : {info['audit_render']}")
    print(f"audit verifies : {info['audit_verifies']}")
    return 0 if info["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
