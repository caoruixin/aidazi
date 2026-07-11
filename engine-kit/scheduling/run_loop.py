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
import hashlib
import json
import re
import os
import sys
from typing import Callable, Dict, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # engine-kit/scheduling
_ENGINE_KIT_DIR = os.path.dirname(_THIS_DIR)                    # engine-kit/
for _p in (
    _THIS_DIR,   # engine-kit/scheduling — for sibling imports (e.g. pause_notifier)
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
    LOOP_MODE_CAMPAIGN_BOOTSTRAP, GateHardFail, STATE_DONE,
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


def campaign_plan_validation_report(plan: dict):
    """Return the ``charter_validator`` Report for a campaign plan's Δ-19 / §1.7-F §A.3
    gap_followup bounds (structural schema + the bounded/pin semantic rule), or None when the
    validator / jsonschema is unavailable. Never raises. Mirrors charter_validation_report."""
    try:
        import charter_validator as _cv  # noqa: E402,WPS433
        report = _cv.Report()
        _cv.validate_campaign_plan(plan, report)
        return report
    except Exception:  # noqa: BLE001 - validator/jsonschema absent ⇒ None
        return None


def enforce_campaign_plan_for_real_run(plan: dict) -> None:
    """ENFORCE the §1.7-F §A.3 gap_followup bounds/pin for a real (``--allow-real``) campaign
    run: raise ``CharterValidationError`` on ANY blocking error, BEFORE any adapter is built or
    invoked, so a plan with an unbounded or non-shrink-tolerating gap_followup (a value that the
    runtime ``_gap_followup_bounds`` would otherwise RESPECT) never reaches a live model. This is
    the production enforcement point for the otherwise authoring-time static guard — the only
    layer that PINS ``max_no_progress_rounds == 1``. A None report (validator / jsonschema
    unavailable) does NOT block — the campaign runner's own fail-closed plan-schema ingress
    (campaign.py) remains the defense-in-depth gate. Mirrors enforce_charter_for_real_run; the
    raised error is a ValueError, so run_campaign_entry maps it to the INVALID exit code."""
    report = campaign_plan_validation_report(plan)
    if report is None or _report_ok(report):
        return
    errors = list(getattr(report, "errors", []) or [])
    raise CharterValidationError(
        "campaign plan has blocking §1.7-F gap_followup error(s); refusing the real run "
        "BEFORE any adapter is invoked:\n" + "\n".join(_charter_issue_lines(errors)))


def load_requirement_ledger(ledger_path: Optional[str]) -> Optional[dict]:
    """Load the requirement ledger JSON at ``ledger_path``, or None when absent/unreadable
    (OW-M3 dormant ⇒ byte-identical to pre-OW-M3). Never raises — used for the best-effort
    FRESHNESS recompute + summary (where an absent live ledger falls back to the stored
    covered_req_surfaces basis, by design). The sign-off/preflight GATE uses the STRICT
    loader below."""
    if not ledger_path or not os.path.isfile(ledger_path):
        return None
    try:
        with open(ledger_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


class LedgerError(ValueError):
    """A WIRED requirement ledger file exists but cannot be read/parsed/validated. The
    OW-M3 sign-off + real-run preflight gate REFUSE rather than treat a broken input
    contract as dormant (which would silently stamp/run around the mandate)."""


def load_requirement_ledger_strict(ledger_path: Optional[str]) -> Optional[dict]:
    """Load + VALIDATE the wired ledger for the OW-M3 sign/preflight GATE. Delegates to the
    campaign runner's SHARED strict probe (campaign.load_and_validate_ledger) so the
    ledger-less ``--sign-plan`` path (which builds no Campaign) applies EXACTLY the same
    fail-closed rule as construction: an ABSENT path ⇒ None (dormant, additive); a
    PRESENT-but-broken one (non-regular / unstatable / unreadable / malformed / schema-invalid
    e.g. an out-of-enum ``surface`` / duplicate ids) ⇒ raise ``LedgerError`` (a ValueError),
    never dormant. os.lstat is used explicitly rather than lexists/isfile — those swallow
    OSError and collapse a permission/stat failure to 'absent' (Codex R3)."""
    try:
        import campaign as _cp  # lazy (campaign imports run_loop)
        return _cp.load_and_validate_ledger(ledger_path)
    except ValueError as exc:            # LedgerError + schema/probe ValueErrors
        raise LedgerError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - campaign/jsonschema unavailable ⇒ can't verify
        raise LedgerError(f"requirement ledger could not be validated: {exc}") from exc


def enforce_mandatory_e2e_for_real_run(plan: dict, charter: dict,
                                       ledger: Optional[dict]) -> None:
    """ENFORCE OW-M3 (design §3.2 / D4) for a REAL (``--allow-real``) campaign run: raise
    ``CharterValidationError`` when the signed plan would accept a user-facing requirement
    on non-browser-E2E evidence, or covers a requirement the ledger does not classify —
    BEFORE any adapter is built or invoked, so a plan that routes around the browser-E2E
    mandate never reaches a live model. DORMANT (no-op) when no requirement ledger is
    wired. This is the runner-preflight half of the gate (the other half is ``--sign-plan``);
    it backstops a plan signed before OW-M3 / hand-edited after signing. Mirrors
    enforce_campaign_plan_for_real_run; the raised ValueError maps to the INVALID exit."""
    try:
        import campaign as _cp  # lazy (campaign imports run_loop)
    except Exception:  # noqa: BLE001 - campaign unavailable ⇒ campaign runner gate covers it
        return
    violations = _cp.mandatory_e2e_violations(plan, charter, ledger)
    if not violations:
        return
    raise CharterValidationError(
        _cp.render_mandatory_e2e_refusal(violations, action="refusing the real run"))


def enforce_required_capabilities_for_real_run(charter: dict) -> None:
    """ENFORCE the Phase-4 native-E2E capability contract (design §2/§13) for a REAL run: raise
    ``CharterValidationError`` when the charter DECLARES a required framework capability the
    DEPLOYED aidazi does not provide (or provides below the required min_version), or when the
    framework contract is missing/malformed (fail-closed) — BEFORE any adapter is built, so a
    plan pinned to a capability this framework lacks never reaches a live model. DORMANT (no-op)
    when the charter declares no required_framework_capabilities (legacy-safe). Mirrors
    enforce_mandatory_e2e_for_real_run; the raised ValueError maps to the INVALID exit."""
    if not (charter or {}).get("required_framework_capabilities"):
        return
    try:
        import framework_capabilities as _fc  # engine-kit/framework_capabilities.py on sys.path
    except Exception as exc:  # noqa: BLE001 — accessor unavailable ⇒ cannot verify ⇒ fail-closed
        raise CharterValidationError(
            "charter declares required_framework_capabilities but the framework capability "
            f"accessor is unavailable — refusing the real run (fail-closed): {exc}") from exc
    try:
        violations = _fc.required_capability_violations(charter)
    except _fc.CapabilityContractError as exc:
        raise CharterValidationError(str(exc)) from exc
    if violations:
        raise CharterValidationError(
            _fc.render_capability_refusal(violations, action="refusing the real run"))


def enforce_skills_preflight_for_real_run(
        charter: dict, *,
        repo_dir: Optional[str] = None,
        audit_loop_id: Optional[str] = None,
        audit_ledger_path: Optional[str] = None,
        clock: Optional[Callable[[], str]] = None,
        allow_gitlink_drift: bool = False) -> None:
    """ENFORCE the universal-skill-mounting integrity/drift preflight (design §4/D3)
    for a REAL (``--allow-real``) run: raise ``CharterValidationError`` BEFORE any
    adapter is built when (row 1) the vendored skill tree fails ``skill_vendor``
    lock/provenance verification, (row 2) a REQUIRED skill binding (role default /
    charter-bound) does not resolve, or (row 3) the framework submodule's working
    tree drifted from the recorded superproject gitlink — the row-3 HALT is
    overridable ONLY by the explicit audited override (``allow_gitlink_drift`` /
    ``AIDAZI_SKILLS_ALLOW_GITLINK_DRIFT=1``), and the override is RECORDED as a
    ``skills_preflight_gitlink_override`` audit event carrying both commits on the
    run's own ledger (``audit_loop_id`` + ``audit_ledger_path`` + ``clock``); with
    no ledger destination the override is refused (an un-audited override is not an
    audited override). Row-4 pin-freshness WARNs print non-silently and never block.
    UNLIKE the capability gate this is
    NEVER dormant (role-default skills mount unconditionally), so an unavailable
    preflight module is itself a fail-closed refusal — every real deployment ships
    the checker; the driver's resolve-time fail-closed remains the defense-in-depth.
    The raised ValueError maps to the INVALID exit, mirroring the other enforce_*."""
    try:
        import skills_preflight as _sp  # engine-kit/validators on sys.path
    except Exception as exc:  # noqa: BLE001 — checker unavailable ⇒ cannot verify
        raise CharterValidationError(
            "skills preflight module is unavailable — the deployed skill surface "
            f"cannot be verified; refusing the real run (fail-closed): {exc}"
        ) from exc
    allow = allow_gitlink_drift or (
        os.environ.get(_sp.GITLINK_OVERRIDE_ENV) == "1")
    audit_emit = None
    if audit_loop_id and audit_ledger_path and clock is not None:
        def audit_emit(finding):  # noqa: ANN001 — _sp.Finding
            audit.append_event(
                audit_loop_id, _sp.GITLINK_OVERRIDE_EVENT,
                {**finding.detail, "message": finding.message,
                 "override": "allow_gitlink_drift"},
                ts=clock(), path=audit_ledger_path)
            print(f"skills preflight: gitlink drift OVERRIDDEN (audited) — "
                  f"{finding.message}")
    try:
        report = _sp.enforce_for_real_run(
            charter, adopter_root=repo_dir,
            allow_gitlink_drift=allow, audit_emit=audit_emit)
    except _sp.SkillsPreflightError as exc:
        raise CharterValidationError(str(exc)) from exc
    for f in report.warnings:
        print(f"skills preflight {f.render()}")


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
    elif loop_mode == LOOP_MODE_CAMPAIGN_BOOTSTRAP:
        # Phase-2 dry-run: ("deliver",0)=Stage-1 backlog, ("deliver",)=Stage-2
        # sub-sprints. Both derive their modules/layers from the CHARTER envelope
        # (first entry of each dimension) so the deterministic envelope guard
        # passes for ANY charter that satisfies the non-empty precondition —
        # a mock dry-run smoke-tests the chain, never the adopter's scope.
        scope = (charter.get("autonomy") or {}).get("approved_scope") or {}
        _mod = (list(scope.get("modules_in_scope") or []) or ["src"])[0]
        _lay = (list(scope.get("layers_allowed") or []) or ["infra"])[0]
        deliver_canned = {
            ("deliver", 0): {
                "goal": "dry-run campaign goal",
                "milestones": [{
                    "id": "m1", "objective": "dry-run milestone",
                    "acceptance_bar": "dry-run bar",
                    "modules": [_mod], "layers": [_lay]}]},
            ("deliver",): {"sub_sprints": [{
                "id": "m1-s1", "objective": "dry-run sub-sprint",
                "scope_in": ["dry-run deliverable"], "scope_out": ["all else"],
                "modules": [_mod], "layers": [_lay],
                "exit_criteria": ["dry-run observable"]}]},
        }
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
        # Phase-4 (Codex R3 B-3): a PARALLEL campaign parks pauses PER MILESTONE (milestone_runtime),
        # NOT on the singleton cursor/context. The decision selects ONE milestone by milestone_id
        # (§6.3: one --resume per parked pause); validate it against THAT milestone's runtime entry
        # (its pause_reason + checkpoint, condition_id for halt) and PRESERVE milestone_id so
        # _handle_resume_parallel can bind it. Bypasses the serial top-level (mirror) validation.
        try:
            with open(os.path.join(campaign_home, "campaign-state.json"),
                      encoding="utf-8") as _fh:
                _state = json.load(_fh)
        except (OSError, ValueError):
            _state = {}
        _rt = _state.get("milestone_runtime")
        # CAMPAIGN-TIER gates (completeness_gap_review, campaign_budget_exhausted) are NOT
        # per-milestone even under a parallel state — they fall through to the serial campaign-tier
        # handling below (Codex R3 B-7/B-9). Only PER-MILESTONE gates use the milestone_runtime
        # binding.
        _campaign_tier = ("completeness_gap_review", "campaign_budget_exhausted")
        if isinstance(_rt, dict) and _rt and pause_reason not in _campaign_tier:
            d_mid = decision.get("milestone_id")
            entry = _rt.get(d_mid) if d_mid else None
            if not isinstance(entry, dict) or entry.get("phase") != "paused":
                return _reject("milestone_id (paused)", d_mid, "a paused milestone")
            m_reason = entry.get("pause_reason")
            if decision.get("pause_reason") != m_reason:
                return _reject("pause_reason", decision.get("pause_reason"), m_reason)
            m_cpt = (os.path.basename(entry["pause_checkpoint"])
                     if entry.get("pause_checkpoint") else None)
            if decision.get("checkpoint") != m_cpt:
                return _reject("checkpoint", decision.get("checkpoint"), m_cpt)
            # Campaign-tier per-milestone gates forbid subsprint_id; a checkpoint-bearing UNIT
            # pause (a halted sub-sprint) is IDENTITY-BOUND to its unit's subsprint_id (Codex R3
            # B-10 round 5 — the serial unit binding, applied under parallel state). The folded
            # halted unit is matched by milestone_id + the FULL checkpoint_path.
            _unit_gates = {"milestone_merge", "halt_condition_met", "epoch_drift",
                           "deliver_followup_required", "milestone_decompose_required"}
            if m_reason == "halt_condition_met":
                # Restore the condition_id binding (Codex R3 B-12 — the B-10 fold dropped it):
                # a decision with the right milestone/checkpoint but the WRONG condition must not
                # acknowledge the live pending halt. subsprint_id stays forbidden.
                pend = entry.get("halt_condition_pending") or {}
                if decision.get("condition_id") != pend.get("condition_id"):
                    return _reject("condition_id", decision.get("condition_id"),
                                   pend.get("condition_id"))
                if decision.get("subsprint_id") is not None:
                    sys.stderr.write("campaign decision: halt_condition_met must not carry "
                                     "subsprint_id — refusing (fail-closed)\n")
                    return None
            elif m_reason == "milestone_merge":
                if decision.get("subsprint_id") is not None:
                    sys.stderr.write("campaign decision: milestone_merge must not carry "
                                     "subsprint_id — refusing (fail-closed)\n")
                    return None
            elif m_reason not in _unit_gates and entry.get("pause_checkpoint"):
                _u = next((u for u in reversed(_state.get("units") or [])
                           if isinstance(u, dict) and u.get("milestone_id") == d_mid
                           and u.get("checkpoint_path") == entry.get("pause_checkpoint")), None)
                if _u is None:
                    return _reject("paused unit lookup", d_mid, "a folded halted unit")
                if decision.get("subsprint_id") != _u.get("subsprint_id"):
                    return _reject("subsprint_id", decision.get("subsprint_id"),
                                   _u.get("subsprint_id"))
            out = {k: decision[k] for k in
                   ("milestone_id", "subsprint_id", "choice", "condition_id", "confirm",
                    "route", "note", "residue", "rationale", "evidence", "waiver", "waiver_id")
                   if k in decision}
            return out or None
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
        if pause_reason == "completeness_gap_review":
            # §1.7-F campaign-tier completeness gate (Track 2 Phase 2-γ): bound by
            # campaign_id + pause_reason + the per-pause checkpoint NONCE basename (matched
            # above), NOT a unit — so a stale `remediate` file from an earlier round is
            # refused and cannot replay (Codex R1 B3). The live pause MUST carry a non-null
            # nonce checkpoint; a null one is a corrupted/bug-written state and is refused
            # (Codex R2 B3 — never bind a checkpoint:null decision past the nonce).
            if checkpoint_path is None:
                sys.stderr.write(
                    "campaign decision: completeness_gap_review with no live nonce "
                    "checkpoint — refusing (fail-closed)\n")
                return None
            if decision.get("subsprint_id") is not None:
                sys.stderr.write(
                    "campaign decision: completeness_gap_review must not carry "
                    "subsprint_id — refusing (fail-closed)\n")
                return None
            out = {k: decision[k] for k in ("choice", "note") if k in decision}
            return out or None
        if pause_reason == "halt_condition_met":
            # Phase-3 (design §3.5a): campaign-tier pre-set halt. Bound by campaign_id +
            # pause_reason + the per-pause nonce basename (matched above) AND the live
            # halt_condition_pending record: condition_id (tamper-evident) + milestone_id +
            # the pending's own checkpoint_basename (consistency). NOT a unit ⇒ subsprint_id
            # is forbidden. A pause with no live pending is unresolvable and refused.
            try:
                with open(os.path.join(campaign_home, "campaign-state.json"),
                          encoding="utf-8") as fh:
                    state = json.load(fh)
            except (OSError, ValueError):
                sys.stderr.write(
                    "campaign decision: cannot read campaign-state for "
                    "halt_condition_met — refusing (fail-closed)\n")
                return None
            pending = state.get("halt_condition_pending")
            if not isinstance(pending, dict):
                sys.stderr.write(
                    "campaign decision: halt_condition_met with no live "
                    "halt_condition_pending — refusing (fail-closed)\n")
                return None
            if pending.get("checkpoint_basename") != live_cpt:
                return _reject("halt_condition checkpoint",
                               pending.get("checkpoint_basename"), live_cpt)
            if decision.get("condition_id") != pending.get("condition_id"):
                return _reject("condition_id", decision.get("condition_id"),
                               pending.get("condition_id"))
            if decision.get("milestone_id") != pending.get("milestone_id"):
                return _reject("milestone_id", decision.get("milestone_id"),
                               pending.get("milestone_id"))
            if decision.get("subsprint_id") is not None:
                sys.stderr.write(
                    "campaign decision: halt_condition_met must not carry "
                    "subsprint_id — refusing (fail-closed)\n")
                return None
            out = {k: decision[k]
                   for k in ("choice", "condition_id", "note") if k in decision}
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
                       memory_root: Optional[str] = None,
                       allow_gitlink_drift: bool = False) -> dict:
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
    # A truthy non-dict plan root (list / scalar) has no .get — guard so a malformed plan
    # reaches the fail-closed validation/INVALID path instead of crashing here (Codex Step-4 R3).
    campaign_id = plan.get("campaign_id") if isinstance(plan, dict) else None
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
        # Δ-19 / §1.7-F §A.3: fail-closed gap_followup bounds/pin preflight for a REAL run,
        # BEFORE any adapter/model is built (the static guard's production enforcement point;
        # raises CharterValidationError → the except-ValueError below maps it to INVALID).
        # Mock/test runs (adapters injected, allow_real False) rely on the campaign runner's
        # own fail-closed plan-schema ingress.
        if allow_real:
            enforce_campaign_plan_for_real_run(plan)
            # Phase-4 native-E2E: refuse a real run pinned to a framework capability this
            # deployed aidazi does not provide (fail-closed; dormant when the charter declares
            # none). Placed alongside the other real-run preflights, before any adapter build.
            enforce_required_capabilities_for_real_run(charter)
            # Strict ledger load: a wired-but-unreadable/invalid ledger raises LedgerError
            # (a ValueError) → caught below → INVALID, rather than dormantly skipping the
            # mandate. An absent ledger stays dormant (additive).
            enforce_mandatory_e2e_for_real_run(
                plan, charter, load_requirement_ledger_strict(ledger_path))
            # Universal-skill-mounting §4/D3: skills integrity/drift preflight — the
            # last real-run preflight before any adapter build. A row-3 gitlink-drift
            # override is audited onto the CAMPAIGN's own ledger (same path the
            # campaign runner appends to, so the event sits on the campaign's chain).
            enforce_skills_preflight_for_real_run(
                charter, repo_dir=repo_dir,
                audit_loop_id=campaign_id or "unidentified",
                audit_ledger_path=audit.audit_path(
                    campaign_id or "unidentified", os.path.join(home, "audit")),
                clock=clock, allow_gitlink_drift=allow_gitlink_drift)
            # Per-unit defense-in-depth: propagate the override so each unit's own
            # preflight (run_loop below) honors it too — conditional kwarg so an
            # injected test run_loop_fn without the param never breaks.
            if allow_gitlink_drift:
                run_loop_kwargs["allow_gitlink_drift"] = True
            # Charter enforcement is the LAST real-run preflight (after the plan/capability/
            # OW-M3/skills preflights so their specific errors surface first), but still BEFORE
            # make_run_unit / run_campaign — so the campaign never reads/evaluates an invalid
            # charter's autonomy.halt_conditions at EP-pre. This closes the R3 B1 gap: the
            # validator-only Phase-3 invariants (closed-metric/op, id-collision, notifications
            # shape) are enforced on the REAL campaign path (raises CharterValidationError → the
            # except below → CAMPAIGN_EXIT_INVALID), not silently no-op'd at runtime.
            enforce_charter_for_real_run(charter)
        run_unit = _cp.make_run_unit(charter, units_dir, campaign_id,
                                     clock=clock, plan=plan,
                                     ledger_path=ledger_path, **run_loop_kwargs)
        resolver = make_campaign_decision_resolver(campaign_id, decision_path, home)
        # Phase-4 (Codex R3 B-2): the PARALLEL coordinator launches isolated workers that
        # reconstruct the Driver from a SERIALIZABLE run_loop config. Forward the JSON-safe
        # subset (repo_dir / memory_root / allow_real / allow_gitlink_drift) so a real
        # (`--allow-real`) parallel campaign runs the REAL Driver — NOT default mock adapters.
        # Injected `adapters` OBJECTS cannot cross the subprocess boundary and are EXCLUDED (a
        # test that injects adapters drives serial, or overrides the worker entrypoint).
        worker_rl_kwargs = {k: v for k, v in run_loop_kwargs.items() if k != "adapters"}
        # Codex R3 B-2 (round 2): a PARALLEL plan launches isolated WORKER subprocesses that
        # cannot receive in-process `adapters` OBJECTS. If adapters were injected AND the plan is
        # parallel, the workers would silently fall back to DEFAULT MOCK adapters. Fail closed —
        # a real parallel run passes `allow_real` (serializable); a test drives serial or uses
        # run_campaign(worker_exec=...) directly.
        _mc = (plan.get("budget") or {}).get("max_concurrent") if isinstance(plan, dict) else None
        if adapters is not None and isinstance(_mc, int) and _mc > 1:
            return {**base, "status": "invalid",
                    "error": "budget.max_concurrent>1 with injected in-process adapters: "
                             "parallel workers are subprocesses and cannot receive adapter "
                             "objects — pass allow_real (real run) or drive serially (fail-closed)",
                    "exit_code": CAMPAIGN_EXIT_INVALID}
        st = _cp.run_campaign(plan, home, run_unit, clock=clock,
                              resume=resume, decision_resolver=resolver,
                              repo_dir=repo_dir, charter=charter,
                              ledger_path=ledger_path,
                              worker_run_loop_kwargs=worker_rl_kwargs)
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
                    plan, st.to_dict(), ledger, charter=charter,
                    repo_dir=repo_dir))
        except Exception:
            requirement_coverage = None

    # F1: the live campaign_plan_signoff status (so a stale-signoff re-sign pause is
    # actionable, distinct from plain "unsigned"). Best-effort.
    try:
        signoff_status = _cp.signoff_status(
            plan, charter, load_requirement_ledger(ledger_path),
            repo_dir=repo_dir)
    except Exception:
        signoff_status = None

    # Phase-4 (design §3.2.1/§6.3): build the PARALLEL per-milestone phase + ALL parked pauses
    # FIRST (before the notifier + scalar derivation, Codex R3 B-10), so the notifier fires PER
    # parked pause and the pause_* scalars are PHASE-DERIVED. A serial run (no milestone_runtime)
    # omits these keys ⇒ byte-identical output.
    _rt = getattr(st, "milestone_runtime", None) or {}
    parallel_extra: dict = {}
    _parallel_pauses: List[dict] = []
    if _rt:
        _order = {m["id"]: i for i, m in enumerate(plan.get("milestones") or [])}
        _mids = sorted(_rt, key=lambda x: _order.get(x, len(_order)))
        _units = [u for u in (getattr(st, "units", None) or []) if isinstance(u, dict)]

        def _paused_unit_of(mid, checkpoint_path):
            """The subsprint_id + loop_id of a paused milestone's unit — from the live inflight if
            present, else (a FOLDED halted unit, inflight cleared, Codex R3 B-10) the matching unit
            record by milestone_id + checkpoint_path, so a --resume decision can identity-bind it."""
            infl = _rt[mid].get("inflight") or {}
            if infl:
                return infl.get("subsprint_id"), infl.get("loop_id")
            for u in reversed(_units):
                if u.get("milestone_id") == mid and u.get("checkpoint_path") == checkpoint_path:
                    return u.get("subsprint_id"), u.get("loop_id")
            return None, None

        _parallel_pauses = []
        for mid in _mids:
            if _rt[mid].get("phase") != "paused":
                continue
            _cpt = _rt[mid].get("pause_checkpoint")
            _ss, _lid = _paused_unit_of(mid, _cpt)
            _parallel_pauses.append({
                "milestone_id": mid, "subsprint_id": _ss,
                "pause_reason": _rt[mid].get("pause_reason"),
                "checkpoint": os.path.basename(_cpt) if _cpt else None,
                "condition_id": (_rt[mid].get("halt_condition_pending")
                                 or {}).get("condition_id"),
                "loop_id": _lid})
        parallel_extra = {
            "milestones": [
                {"milestone_id": mid, "phase": _rt[mid].get("phase"),
                 "pause_reason": _rt[mid].get("pause_reason"),
                 "pause_checkpoint": _rt[mid].get("pause_checkpoint")}
                for mid in _mids],
            "pauses": _parallel_pauses,
            "milestones_complete": sum(
                1 for mid in _mids if _rt[mid].get("phase") in ("done", "merged")),
        }

    # Phase-3 push-not-poll (design §4.3): on EVERY campaign pause (exit 10), fire the
    # charter's notifications.on_pause hook AFTER the pause is durably persisted, FAIL-SAFE +
    # default-OFF. A halt_condition_met pause is campaign-tier (paused_unit empty). Phase-4
    # (§6.3): under parallelism the pause_* scalars mirror the OLDEST parked pause (incl.
    # condition_id — the top-level halt_condition_pending is intentionally unused in parallel),
    # and the notifier fires ONCE PER parked pause.
    _hcp = getattr(st, "halt_condition_pending", None) or {}
    if _parallel_pauses:
        _oldest = _parallel_pauses[0]
        _pause_milestone_id = _oldest.get("milestone_id")
        _pause_subsprint_id = _oldest.get("subsprint_id")
        _pause_condition_id = _oldest.get("condition_id")
    else:
        _pause_milestone_id = paused_unit.get("milestone_id") or _hcp.get("milestone_id")
        _pause_subsprint_id = paused_unit.get("subsprint_id")
        _pause_condition_id = _hcp.get("condition_id")
    if exit_code == CAMPAIGN_EXIT_PAUSED:
        try:
            import pause_notifier as _pn
            _ledger = audit.audit_path(campaign_id, os.path.join(home, "audit"))

            def _emit_notif(evtype: str, payload: dict) -> None:
                audit.append_event(campaign_id, evtype, payload,
                                   ts=clock(), path=_ledger)

            # Serial (or a parallel GLOBAL pause with no paused milestone) fires once from the
            # top-level mirror; a parallel run with parked per-milestone pauses fires per pause.
            _notif_pauses = _parallel_pauses or [{
                "milestone_id": _pause_milestone_id, "subsprint_id": _pause_subsprint_id,
                "pause_reason": st.pause_reason, "condition_id": _pause_condition_id,
                "checkpoint": (os.path.basename(st.pause_checkpoint)
                               if st.pause_checkpoint else None)}]
            for _p in _notif_pauses:
                _pn.notify_on_pause(charter, {
                    "campaign_id": campaign_id, "reason": _p.get("pause_reason"),
                    "checkpoint": _p.get("checkpoint"),
                    "milestone_id": _p.get("milestone_id"),
                    "subsprint_id": _p.get("subsprint_id"),
                    "condition_id": _p.get("condition_id"),   # halt identity (Codex R3 B-10)
                }, _emit_notif)
        except Exception:
            pass  # the notifier path must NEVER break the pause / exit-10 return
    return {
        **base,
        "status": st.status,
        "pause_reason": st.pause_reason,
        "pause_checkpoint": st.pause_checkpoint,
        "pause_milestone_id": _pause_milestone_id,
        "pause_subsprint_id": _pause_subsprint_id,
        "pause_condition_id": _pause_condition_id,   # halt identity (phase-derived under parallel)
        "pause_loop_id": (_parallel_pauses[0].get("loop_id") if _parallel_pauses
                          else paused_unit.get("loop_id")),
        "milestone_index": st.milestone_index,
        "milestones_total": len(plan.get("milestones") or []),
        "subsprints_run": st.subsprints_run,
        "total_spawns": st.total_spawns,
        "exit_code": exit_code,
        "scope_coverage": scope_coverage,
        "requirement_coverage": requirement_coverage,
        "signoff_status": signoff_status,
        "milestone_outcomes": list(st.milestone_outcomes or []),
        **parallel_extra,
    }


def _campaign_resume_hint(result: dict) -> str:
    """One actionable line telling the human how to resolve THIS pause + resume."""
    reason = result.get("pause_reason")
    if reason == "campaign_plan_signoff":
        sstatus = result.get("signoff_status")
        if sstatus == "stale":
            return ("  -> STALE SIGNOFF: the signed scope-envelope hash no longer matches "
                    "the plan (a milestone/charter/compact-prompt edit). Re-sign (re-stamp "
                    "the snapshot): re-run with --campaign <plan> --charter <charter> "
                    "--repo-dir <adopter repo> --sign-plan, then --resume (--repo-dir is "
                    "REQUIRED when the signoff binds compact prompts — "
                    "prompt_artifacts_digest)")
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
    if reason == "completeness_gap_review":
        # §1.7-F: the campaign-tier completeness gate. The adjust_scope decision binds via
        # campaign_id + pause_reason + the per-pause checkpoint NONCE basename (so a stale
        # remediate file cannot replay across rounds). remediate authorizes ONE bounded,
        # in-envelope round (same deterministic gates as the auto path; no ship/widen authority).
        cpt = result.get("pause_checkpoint")
        base = os.path.basename(cpt) if cpt else None
        return ('  -> §1.7-F completeness gap (signed-but-undelivered scope). Author a '
                'campaign-decision.json with "choice": "remediate"|"accept_gap"|"abort", '
                f'"campaign_id": {result.get("campaign_id")!r}, '
                f'"pause_reason": "completeness_gap_review", "checkpoint": {base!r} '
                "(NO subsprint_id), then re-run with --resume --decision <file>")
    if reason == "halt_condition_met":
        # Phase-3: a PRE-SET structural halt YOU declared. Campaign-tier (NO subsprint_id);
        # binds to the condition_id + the per-pause nonce basename.
        cpt = result.get("pause_checkpoint")
        base = os.path.basename(cpt) if cpt else None
        return ('  -> your pre-set halt condition '
                f'{result.get("pause_condition_id")!r} fired. Author a campaign-decision.json '
                'with "choice": "proceed"|"abort", '
                f'"campaign_id": {result.get("campaign_id")!r}, '
                '"pause_reason": "halt_condition_met", '
                f'"condition_id": {result.get("pause_condition_id")!r}, '
                f'"milestone_id": {result.get("pause_milestone_id")!r}, '
                f'"checkpoint": {base!r} (NO subsprint_id), then re-run with '
                "--resume --decision <file>")
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
        # Phase-4 (design §3.2.1): under milestone_runtime the scalar milestone_index is the
        # fail-closed (0,0) mirror, so report PHASE-DERIVED progress; serial keeps the cursor line.
        if result.get("milestones") is not None:
            print(f"milestones     : {result.get('milestones_complete')}/"
                  f"{result.get('milestones_total')} complete (phase-derived; "
                  f"milestone_index={result.get('milestone_index')} is the legacy mirror)")
            print("               : "
                  + ", ".join(f"{m['milestone_id']}={m['phase']}"
                              for m in result.get("milestones") or []))
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
        # Phase-4 (design §6.3): surface EVERY parked pause (a parallel run may park several);
        # each needs its own --resume with a decision selecting that milestone's checkpoint.
        _pauses = result.get("pauses")
        if _pauses:
            print(f"parked pauses  : {len(_pauses)} (resume each with its own decision)")
            for p in _pauses:
                print(f"               : milestone={p.get('milestone_id')} "
                      f"reason={p.get('pause_reason')} checkpoint={p.get('checkpoint')}")
        print(_campaign_resume_hint(result))
    machine = {k: result.get(k) for k in (
        "campaign_id", "status", "pause_reason", "pause_checkpoint",
        "pause_milestone_id", "pause_subsprint_id", "pause_loop_id",
        "milestone_index", "milestones_total", "subsprints_run", "total_spawns",
        "exit_code")}
    print("CAMPAIGN_STATUS=" + json.dumps(machine, sort_keys=True))
    # Phase-4 ADDITIVE parse contract (the CAMPAIGN_STATUS= line above stays byte-identical for
    # serial): the per-milestone phase array + parked pauses + phase-derived progress. Emitted
    # ONLY for a parallel run (milestone_runtime present).
    if result.get("milestones") is not None:
        print("CAMPAIGN_MILESTONES=" + json.dumps(
            {"milestones": result.get("milestones"),
             "pauses": result.get("pauses"),
             "milestones_complete": result.get("milestones_complete"),
             "milestones_total": result.get("milestones_total")}, sort_keys=True))
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
    allow_gitlink_drift: bool = False,
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
    ``allow_gitlink_drift`` is the skills-preflight row-3 explicit audited override
    (only consulted on a real run; the override is audit-recorded, never silent).
    """
    if mode not in MODES:
        raise ValueError(f"mode {mode!r} not one of {MODES}")
    if adapters is None:
        # ENFORCE the charter schema BEFORE building any real adapter: an invalid
        # charter must never reach a live model. Mock dry-runs (allow_real=False)
        # skip this — example charters are intentionally schema-lenient.
        if allow_real:
            enforce_charter_for_real_run(charter)
            # Universal-skill-mounting §4/D3: skills integrity/drift preflight,
            # BEFORE any adapter build. Fires per unit under a campaign too
            # (defense-in-depth: mid-campaign framework drift is caught at the next
            # unit). A row-3 override is audited onto THIS loop's own ledger — the
            # same file the Driver appends to, so the chain carries the event.
            enforce_skills_preflight_for_real_run(
                charter, repo_dir=repo_dir,
                audit_loop_id=loop_id,
                audit_ledger_path=audit.audit_path(
                    loop_id, os.path.join(run_dir, ".orchestrator", "audit")),
                clock=clock, allow_gitlink_drift=allow_gitlink_drift)
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


# --------------------------------------------------------------------------- #
# Phase-2 — the requirement-driven chain entry (--requirement; design
# archive/2026-07-09-phase2-requirement-chain-design.md §2-§4, Codex R0.5
# APPROVE). One command from a requirement file to a sign-ready, RUNNABLE
# campaign plan: bootstrap pre-chain (research → gate-1 → campaign decompose,
# Commit A) + the run_loop-tier projection/validation/emission below (Commit B).
# --------------------------------------------------------------------------- #

def _slugify_campaign_id(path: str) -> str:
    """Derive a path-safe campaign id from the requirement filename (design
    §3.3(e)): basename minus extension, non-[A-Za-z0-9._-] → '-', trimmed."""
    base = os.path.splitext(os.path.basename(path))[0]
    slug = "".join(c if c.isalnum() or c in "._-" else "-" for c in base)
    slug = slug.strip("-.").lstrip("_") or "campaign"
    return slug[:128]


def _ingest_requirement(requirement_path: str, run_dir: str) -> dict:
    """Snapshot the requirement file into the run dir [R0 B-3]: byte copy to
    <run_dir>/requirement.md + sha256. The SNAPSHOT is canonical from then on
    (source drift after a halt is a WARN audit — driver resume side)."""
    with open(requirement_path, "rb") as fh:
        data = fh.read()
    os.makedirs(run_dir, exist_ok=True)
    snap = os.path.join(run_dir, "requirement.md")
    with open(snap, "wb") as fh:
        fh.write(data)
    return {"path": "requirement.md",
            "sha256": hashlib.sha256(data).hexdigest(),
            "source_path": os.path.abspath(requirement_path)}


def make_bootstrap_decision_resolver(campaign_id: str, decision_path: str,
                                     run_dir: str):
    """[design §4 / R0 N-4 / R0.2 N-1] Identity-bound FILE resolver for the
    bootstrap gate-1 pause. No campaign exists yet, so the DERIVED campaign id
    is the identity anchor. Reuses campaign-decision.schema.json VERBATIM.

    Fail-closed binding — ALL must hold or the resolver returns None (re-halt):
    - campaign_id == the derived id (exact);
    - pause_reason == "customer_gate1_signoff";
    - checkpoint == the LIVE gate-1 checkpoint basename (the newest
      customer_gate1_signoff checkpoint in the run dir, exact match);
    - choice ∈ {sign, reject, abort} (the gate-1 option set);
    - milestone_id / subsprint_id ABSENT (no unit exists — supplying them is
      an identity mismatch, refused)."""
    def _refuse(reason: str):
        print(f"bootstrap decision REFUSED: {reason} — the gate re-halts; fix "
              f"the decision file and re-run with --resume.")
        return None

    def _resolver(gate_id, context, options):
        if gate_id != "customer_gate1":
            return None
        try:
            with open(decision_path, encoding="utf-8") as fh:
                decision = json.load(fh)
        except (OSError, ValueError) as exc:
            return _refuse(f"unreadable decision file: {exc}")
        import campaign as _cp  # lazy (campaign imports run_loop)
        try:
            _cp._validate_or_raise(decision, "campaign-decision.schema.json",
                                   "bootstrap decision")
        except ValueError as exc:
            return _refuse(str(exc))
        if decision.get("campaign_id") != campaign_id:
            return _refuse(f"campaign_id {decision.get('campaign_id')!r} != "
                           f"derived id {campaign_id!r}")
        if decision.get("pause_reason") != "customer_gate1_signoff":
            return _refuse(f"pause_reason {decision.get('pause_reason')!r} != "
                           f"'customer_gate1_signoff'")
        if decision.get("milestone_id") or decision.get("subsprint_id"):
            return _refuse("milestone_id/subsprint_id supplied but NO unit "
                           "exists at the bootstrap gate")
        cp_dir = os.path.join(run_dir, "docs", "checkpoints")
        live = sorted(f for f in (os.listdir(cp_dir)
                                  if os.path.isdir(cp_dir) else [])
                      if "__customer_gate1_signoff__" in f)
        if not live:
            return _refuse("no live customer_gate1_signoff checkpoint found")
        if decision.get("checkpoint") != live[-1]:
            return _refuse(f"checkpoint {decision.get('checkpoint')!r} != live "
                           f"{live[-1]!r}")
        choice = decision.get("choice")
        if choice not in ("sign", "reject", "abort"):
            return _refuse(f"choice {choice!r} not in sign|reject|abort")
        return {"choice": choice, "note": str(decision.get("note") or ""),
                "resolver": "bootstrap-decision-file"}
    return _resolver


def _project_campaign_plan(stage1: dict, stage2: dict, campaign_id: str,
                           ledger: Optional[dict]) -> dict:
    """Design §3.3(e): decompose verdicts → campaign-plan.json with EVERY
    milestone's subsprint_sequence FILLED [R0 B-1]. OW-AUTO derivation: a
    covered rid classified user_facing forces functional_acceptance browser_e2e
    (PR#7 semantics; last-occurrence-wins surface map, matching the sign-off
    gate) — the forcing is re-VERIFIED by OW-M3 in the sign-stack, not trusted.
    No budget/gap_followup/trunk/isolation invented (schema defaults apply; the
    human may edit BEFORE signing)."""
    surface_by_rid: dict = {}
    for r in (ledger or {}).get("requirements") or []:
        if isinstance(r, dict) and r.get("id") is not None:
            surface_by_rid[str(r["id"])] = r.get("surface")
    milestones = []
    for m in stage1.get("milestones") or []:
        mid = str(m.get("id"))
        entry = {
            "id": mid,
            "objective": str(m.get("objective")),
            "acceptance_bar": str(m.get("acceptance_bar")),
            "subsprint_sequence": [
                str(s.get("id")) for s in
                ((stage2.get(mid) or {}).get("sub_sprints") or [])],
        }
        for k in ("covers_req_ids", "depends_on", "milestone_signals"):
            if m.get(k):
                entry[k] = [str(x) for x in m[k]]
        fa = m.get("functional_acceptance")
        if any(surface_by_rid.get(str(r)) == "user_facing"
               for r in (m.get("covers_req_ids") or [])):
            fa = "browser_e2e"
        if fa:
            entry["functional_acceptance"] = fa
        milestones.append(entry)
    return {"campaign_id": campaign_id, "goal": str(stage1.get("goal")),
            "delivery_mode": "campaign", "milestones": milestones}


def _bootstrap_plan_violations(plan: dict, charter: dict,
                               ledger: Optional[dict]) -> list:
    """Design §3.3(f) — the FULL sign-time validation stack run EARLY ('never
    show an unsignable plan'). Returns refusal reasons (empty ⇒ sign-ready)."""
    import campaign as _cp  # lazy
    reasons: list = []
    try:
        _cp._validate_or_raise(plan, "campaign-plan.schema.json",
                               "projected plan")
    except ValueError as exc:
        reasons.append(f"projected plan schema-invalid: {exc}")
        return reasons  # field-level checks below assume the shape
    try:
        _cp.topological_order(plan.get("milestones") or [])
    except ValueError as exc:
        reasons.append(f"milestone dependency DAG invalid: {exc}")
    seen_rids: dict = {}
    for m in plan.get("milestones") or []:
        for rid in (m.get("covers_req_ids") or []):
            if rid in seen_rids:
                reasons.append(
                    f"covers_req_ids {rid!r} claimed by BOTH "
                    f"{seen_rids[rid]!r} and {m['id']!r} (at-most-one "
                    f"covering milestone per REQ)")
            seen_rids[rid] = m["id"]
    try:
        enforce_campaign_plan_for_real_run(plan)
    except CharterValidationError as exc:
        reasons.append(f"gap-followup bounds: {exc}")
    # [R2.2 B-1] coverage-authority defense-in-depth (design §3.3(c)): OW-M3
    # below is DORMANT without a ledger, so re-assert the no-ledger/unknown-rid
    # rule HERE too — the emission path must refuse coverage claims it cannot
    # verify regardless of what the driver-side check saw earlier.
    _claimed = {str(r) for m in (plan.get("milestones") or [])
                for r in (m.get("covers_req_ids") or [])}
    if _claimed and ledger is None:
        reasons.append(
            f"coverage claims {sorted(_claimed)} require a wired requirement "
            f"ledger to verify — wire `charter.requirements.ledger_path` or "
            f"drop covers_req_ids")
    elif _claimed:
        _known = {str(r.get("id")) for r in
                  (ledger.get("requirements") or []) if isinstance(r, dict)}
        _unknown = sorted(_claimed - _known)
        if _unknown:
            reasons.append(f"covers_req_ids not present in the requirement "
                           f"ledger: {_unknown}")
    _viol = _cp.mandatory_e2e_violations(plan, charter, ledger)
    if _viol:
        reasons.append(_cp.render_mandatory_e2e_refusal(
            _viol, action="refusing to present the plan for signature"))
    # Capability-contract parity with --sign-plan (Phase-4 native-E2E): a plan
    # whose charter pins a framework capability this deployment lacks can never
    # be signed — surface it HERE ('never show an unsignable plan'), not at the
    # human's later sign attempt.
    if charter.get("required_framework_capabilities"):
        import framework_capabilities as _fc
        try:
            _cap = _fc.required_capability_violations(charter)
        except _fc.CapabilityContractError as exc:
            _cap = None
            reasons.append(f"capability contract: {exc}")
        if _cap:
            reasons.append(_fc.render_capability_refusal(
                _cap, action="refusing to present the plan for signature"))
    return reasons


def _materialize_compact_prompts(drv, stage1: dict, stage2: dict):
    """Design §3.3(g) [R0 B-1]: write compact/<sid>-{dev,review}-prompt.md for
    EVERY sub-sprint under the RESOLVED repo dir via the EXISTING projection
    renderers — the strict-prompt channel the Phase-1 real canary proved.
    NEVER overwrites (adopter-authored is normative): any pre-existing file ⇒
    ([], collision reasons). Both files carry the projection front-matter and
    are re-validated through _validate_compact_text before write."""
    plans = []
    reasons = []
    for m in stage1.get("milestones") or []:
        mid = str(m.get("id"))
        for s in ((stage2.get(mid) or {}).get("sub_sprints") or []):
            sid = str(s.get("id"))
            dev_path = drv._compact_prompt_path(sid, "dev-prompt")
            rev_path = drv._compact_prompt_path(sid, "review-prompt")
            if not dev_path or not rev_path:
                reasons.append(f"sub-sprint id {sid!r} is not a safe compact "
                               f"path component (or no repo dir bound)")
                continue
            for p in (dev_path, rev_path):
                if os.path.exists(p):
                    reasons.append(
                        f"compact file already exists (adopter-authored is "
                        f"normative — never overwritten): {p}")
            plans.append((sid, s, dev_path, rev_path))
    if reasons:
        return [], reasons
    written = []
    for sid, s, dev_path, rev_path in plans:
        for path, kind, body in (
                (dev_path, "Dev", drv._project_dev_prompt(s)),
                (rev_path, "Review", drv._project_review_prompt(s))):
            text = ("---\n"
                    f"title: {kind} prompt (engine projection) — {sid}\n"
                    f"sprint_id: {sid}\n"
                    "context_budget:\n"
                    "  self_contained: true\n"
                    "projection: true   # generated by the campaign bootstrap; "
                    "edit the signed plan, not this file\n"
                    "---\n\n" + body)
            fm, b = drv._split_front_matter(text)
            problems = drv._validate_compact_text(fm, b)
            if problems:
                return [], [f"generated {kind} compact for {sid!r} failed "
                            f"content validation: {'; '.join(problems)}"]
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            written.append(
                (sid, path,
                 hashlib.sha256(text.encode("utf-8")).hexdigest()))
    return written, []


def run_requirement_entry(charter: dict, *, requirement_path: str,
                          charter_path: str, repo_dir: Optional[str],
                          campaign_out: Optional[str],
                          campaign_id: Optional[str] = None,
                          run_dir: Optional[str] = None, resume: bool = False,
                          decision_path: Optional[str] = None,
                          allow_real: bool = False, clock=None,
                          memory_root: Optional[str] = None,
                          allow_gitlink_drift: bool = False,
                          gate_resolver=None, start: bool = False,
                          campaign_run_dir: Optional[str] = None,
                          input_fn=None) -> int:
    """The --requirement entry (design §2/§3.3(e)-(h)/§3.4). Exit codes reuse
    the campaign vocabulary: 0 plan emitted; 2 invalid inputs; 10 halted
    awaiting a human; 1 unexpected error."""
    clock = clock or _production_clock()
    # Preflight 0c [R0.3 B-1]: --repo-dir REQUIRED — strict compact lookup (and
    # therefore the emitted campaign's runnability) is repo_dir-dependent.
    if not repo_dir or not os.path.isdir(repo_dir):
        print(f"--requirement REFUSED: --repo-dir is REQUIRED and must be an "
              f"existing directory (got {repo_dir!r}) — the emitted campaign's "
              f"strict prompts live under <repo>/compact/ and every printed "
              f"command carries the same --repo-dir.")
        return CAMPAIGN_EXIT_INVALID
    repo_dir = os.path.abspath(repo_dir)
    if not campaign_out:
        print("--requirement REFUSED: --campaign-out is REQUIRED (the emitted "
              "campaign-plan.json path).")
        return CAMPAIGN_EXIT_INVALID
    if not resume and not os.path.isfile(requirement_path):
        print(f"--requirement REFUSED: requirement file not found: "
              f"{requirement_path}")
        return CAMPAIGN_EXIT_INVALID
    # Preflight 0a [R0.2 B-1]: the SAME signed-intent-contract gate acceptance
    # enforces (Constitution §3.4 invariant #4) — checked up-front so a
    # requirement-start can never wander into a mid-campaign
    # acceptance_spec_refinement halt.
    _ic_problems = Driver._validate_acceptance_context(
        charter.get("intent_contract") or {})
    if _ic_problems:
        print("--requirement REFUSED: charter.intent_contract is not a "
              "complete HUMAN-SIGNED contract (every campaign unit's "
              "Acceptance gate will demand it):")
        for p in _ic_problems:
            print(f"  - {p}")
        return CAMPAIGN_EXIT_INVALID
    # Real-run preflights (parity with the single-loop/campaign entries).
    if allow_real:
        for r in (os.path.dirname(os.path.abspath(charter_path)), os.getcwd()):
            if r:
                load_local_env(root=r)
        try:
            enforce_charter_for_real_run(charter)
        except CharterValidationError as exc:
            print(f"REAL RUN ABORTED before any adapter was invoked: {exc}")
            return CAMPAIGN_EXIT_INVALID
    # Requirement ledger: STRICT (absent = dormant None; present-but-broken
    # REFUSES) — re-resolved on every invocation incl. resume (§3.3(c) basis).
    try:
        ledger = load_requirement_ledger_strict(
            resolve_ledger_path(charter, repo_dir))
    except LedgerError as exc:
        print(f"--requirement REFUSED: {exc}")
        return CAMPAIGN_EXIT_INVALID

    cid = campaign_id or _slugify_campaign_id(requirement_path)
    # [R2 B-3] the campaign id feeds the plan schema, the Driver loop id and
    # checkpoint/audit paths — an unsafe id must die HERE as a clean rc-2 input
    # refusal, never as a late traceback or a mid-flow rc 10.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", cid):
        print(f"--requirement REFUSED: campaign id {cid!r} is not schema-safe "
              f"(need ^[A-Za-z0-9][A-Za-z0-9._-]{{0,127}}$) — pass a valid "
              f"--campaign-id.")
        return CAMPAIGN_EXIT_INVALID
    loop_id = f"campaign-bootstrap-{cid}"
    run_dir = run_dir or os.path.join(repo_dir, ".runs", loop_id)
    requirement_ref = None
    if not resume:
        requirement_ref = _ingest_requirement(requirement_path, run_dir)
    if gate_resolver is None and decision_path:
        gate_resolver = make_bootstrap_decision_resolver(
            cid, decision_path, run_dir)

    adapters = build_adapters(charter, allow_real=allow_real,
                              loop_mode=LOOP_MODE_CAMPAIGN_BOOTSTRAP)
    drv = Driver(
        charter, run_dir, adapters, loop_id=loop_id, clock=clock,
        context={"schedule_mode": "campaign_bootstrap",
                 "allow_real": allow_real,
                 "loop_mode": LOOP_MODE_CAMPAIGN_BOOTSTRAP},
        repo_dir=repo_dir, memory_root=memory_root,
        loop_mode=LOOP_MODE_CAMPAIGN_BOOTSTRAP, gate_resolver=gate_resolver)
    try:
        final = drv.run_campaign_bootstrap(
            resume=resume, requirement_ref=requirement_ref,
            requirement_ledger=ledger)
    except GateHardFail as exc:
        # [R0 N-3] a deterministic decompose fault (schema/bounds) — checkpoint
        # already written; a clean rc-10 pause, never a traceback.
        print(f"campaign bootstrap HALTED (gate_hard_fail): {exc}")
        if exc.checkpoint_path:
            print(f"  checkpoint: {exc.checkpoint_path}")
        print(f"  fix the input (or let Deliver re-decompose) and re-run with "
              f"--resume.")
        return CAMPAIGN_EXIT_PAUSED
    except (FileNotFoundError, ValueError) as exc:
        print(f"--requirement ERROR: {exc}")
        return CAMPAIGN_EXIT_INVALID

    if final.state != STATE_DONE:
        print(f"campaign bootstrap PAUSED at state={final.state} — a human "
              f"decision or input fix is required (see the newest checkpoint "
              f"under {os.path.join(run_dir, 'docs', 'checkpoints')}); then "
              f"re-run with --resume.")
        return CAMPAIGN_EXIT_PAUSED

    # ---- (e)-(f): projection + the early sign-stack (never show unsignable).
    backlog = final.campaign_backlog or {}
    stage1 = backlog.get("stage1") or {}
    stage2 = backlog.get("stage2") or {}
    plan = _project_campaign_plan(stage1, stage2, cid, ledger)
    reasons = _bootstrap_plan_violations(plan, charter, ledger)
    if reasons:
        drv._campaign_decompose_refusal(reasons)
        print("campaign bootstrap REFUSED to present an unsignable plan:")
        for r in reasons:
            print(f"  - {r}")
        return CAMPAIGN_EXIT_PAUSED

    # ---- (g): strict-prompt materialization under the resolved repo dir.
    written, reasons = _materialize_compact_prompts(drv, stage1, stage2)
    if reasons:
        drv._campaign_decompose_refusal(reasons)
        print("campaign bootstrap REFUSED (compact prompt materialization):")
        for r in reasons:
            print(f"  - {r}")
        return CAMPAIGN_EXIT_PAUSED

    # ---- (h): emit plan + sidecar + audit.
    plan_bytes = json.dumps(plan, indent=2, sort_keys=True).encode("utf-8")
    with open(campaign_out, "wb") as fh:
        fh.write(plan_bytes)
    verdict_sha256 = hashlib.sha256(json.dumps(
        {"stage1": stage1, "stage2": stage2}, sort_keys=True,
        ensure_ascii=False).encode("utf-8")).hexdigest()
    sidecar = {
        "stage1": stage1, "stage2": stage2,
        "envelope": backlog.get("envelope"),
        "requirement_ref": final.requirement_ref,
        "verdict_sha256": verdict_sha256,
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "compact_files": [
            {"sid": sid, "path": os.path.relpath(path, repo_dir),
             "sha256": sha} for sid, path, sha in written],
    }
    sidecar_path = f"{campaign_out}.decompose-verdict.json"
    with open(sidecar_path, "w", encoding="utf-8") as fh:
        json.dump(sidecar, fh, indent=2, sort_keys=True)
    drv._audit("campaign_plan_emitted", {
        "campaign_id": cid, "plan_path": os.path.abspath(campaign_out),
        "plan_sha256": sidecar["plan_sha256"],
        "verdict_sha256": verdict_sha256,
        "requirement_sha256": (final.requirement_ref or {}).get("sha256"),
        "compact_files": sidecar["compact_files"],
        "ledger_wired": ledger is not None,
    })

    # ---- §3.4 backlog table + the EXACT handoff commands (all carry
    # --repo-dir [R0.3 B-1]).
    print(f"=== campaign bootstrap COMPLETE — plan emitted (NOT signed) ===")
    print(f"campaign_id    : {cid}")
    print(f"plan           : {os.path.abspath(campaign_out)}")
    print(f"sidecar        : {os.path.abspath(sidecar_path)}")
    print(f"goal           : {plan['goal']}")
    print(f"milestones     :")
    for m in plan["milestones"]:
        print(f"  - {m['id']}: {m['objective']}")
        print(f"      acceptance_bar: {m.get('acceptance_bar')}")
        print(f"      sub-sprints: {m.get('subsprint_sequence')}")
        if m.get("covers_req_ids"):
            print(f"      covers_req_ids: {m['covers_req_ids']} "
                  f"(acceptance: {m.get('functional_acceptance', 'inherited')})")
        if m.get("depends_on"):
            print(f"      depends_on: {m['depends_on']}")
    print(f"compact prompts: {len(written)} file(s) under "
          f"{os.path.join(repo_dir, 'compact')}")
    print(f"REVIEW the plan + prompts, then sign:")
    print(f"  python3.12 engine-kit/scheduling/run_loop.py "
          f"--campaign {campaign_out} --charter {charter_path} "
          f"--repo-dir {repo_dir} --sign-plan")
    print(f"then run the signed campaign:")
    print(f"  python3.12 engine-kit/scheduling/run_loop.py "
          f"--campaign {campaign_out} --charter {charter_path} "
          f"--repo-dir {repo_dir} --resume --allow-real")

    # ---- Commit C (design §4): the ONE-SITTING inline sign. Interactive ONLY:
    # a wired input_fn (tests) or a real TTY. `sign` records the human's
    # identity and stamps campaign_plan_signoff via the SAME stamp_signoff the
    # --sign-plan CLI uses (with repo_dir, so the §3.5 digest binds); ANY other
    # answer defers (rc 0, unsigned plan + the printed --sign-plan command).
    # The engine NEVER signs without this explicit human input.
    if input_fn is None and (sys.stdin is not None and sys.stdin.isatty()
                             and sys.stdout.isatty()):
        input_fn = input
    if input_fn is None:
        return CAMPAIGN_EXIT_DONE
    ans = str(input_fn(
        "sign campaign_plan_signoff NOW? (type 'sign' to sign, anything else "
        "defers)> ") or "").strip()
    if ans != "sign":
        print("deferred — sign later with the printed --sign-plan command.")
        return CAMPAIGN_EXIT_DONE
    signer = str(input_fn("signer identity (name/email)> ") or "").strip()
    if not signer:
        print("no signer identity given — deferred (a signature is "
              "identity-bound; sign later with --sign-plan).")
        return CAMPAIGN_EXIT_DONE
    import campaign as _cp  # lazy
    signed = _cp.stamp_signoff(plan, charter, signer=signer,
                               signed_at=clock(),
                               charter_ref=os.path.abspath(charter_path),
                               ledger=ledger, repo_dir=repo_dir)
    try:
        _cp._validate_or_raise(signed, "campaign-plan.schema.json",
                               "signed plan")
    except ValueError as exc:
        print(f"inline sign ERROR: stamped plan is schema-invalid: {exc}")
        return CAMPAIGN_EXIT_INVALID
    with open(campaign_out, "w", encoding="utf-8") as fh:
        json.dump(signed, fh, indent=2, sort_keys=True)
    drv._audit("campaign_plan_signed_inline", {
        "campaign_id": cid, "signer": signer,
        "signed_scope_hash": signed["signoff"]["signed_scope_hash"],
        "prompt_artifacts_digest":
            signed["signoff"].get("prompt_artifacts_digest"),
    })
    print(f"SIGNED by {signer} — signed_scope_hash="
          f"{signed['signoff']['signed_scope_hash']}")
    print(f"run the campaign:")
    print(f"  python3.12 engine-kit/scheduling/run_loop.py "
          f"--campaign {campaign_out} --charter {charter_path} "
          f"--repo-dir {repo_dir} --resume --allow-real")
    if not start:
        return CAMPAIGN_EXIT_DONE
    # --start: continue IN-PROCESS into the campaign entry — every real-run
    # preflight runs exactly as a --campaign invocation would (run_campaign_entry
    # is the same function main() dispatches to) [design §4 --start].
    print("=== --start: driving the signed campaign in-process ===")
    result = run_campaign_entry(
        signed, charter, clock=clock, campaign_run_dir=campaign_run_dir,
        resume=False, decision_path=decision_path, allow_real=allow_real,
        repo_dir=repo_dir, memory_root=memory_root,
        allow_gitlink_drift=allow_gitlink_drift)
    print_campaign_result(result)
    return result["exit_code"]


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
    parser.add_argument("--allow-gitlink-drift", action="store_true",
                        help="EXPLICIT AUDITED OVERRIDE (skills preflight §4 row 3): "
                             "let a real run proceed although the framework "
                             "submodule's working tree differs from the recorded "
                             "superproject gitlink; the override is recorded as a "
                             "skills_preflight_gitlink_override audit event carrying "
                             "both commits (env: AIDAZI_SKILLS_ALLOW_GITLINK_DRIFT=1)")
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
    parser.add_argument("--requirement", default=None,
                        help="Phase-2 requirement-driven chain: path to a requirement "
                             "file (markdown). Drives research → gate-1 → campaign "
                             "decompose and emits a sign-ready campaign-plan.json to "
                             "--campaign-out. REQUIRES --repo-dir and a charter with a "
                             "signed intent_contract. Mutually exclusive with --campaign.")
    parser.add_argument("--campaign-out", default=None,
                        help="(with --requirement) output path for the emitted "
                             "campaign-plan.json (+ a .decompose-verdict.json sidecar)")
    parser.add_argument("--campaign-id", default=None,
                        help="(with --requirement) campaign id for the emitted plan "
                             "(default: a slug of the requirement filename)")
    parser.add_argument("--start", action="store_true",
                        help="(with --requirement, INTERACTIVE only) after an inline "
                             "campaign_plan_signoff sign, continue in-process into the "
                             "campaign entry (all --campaign preflights apply). Without "
                             "an inline sign this flag does nothing (default OFF).")
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

    # Phase-2 requirement-driven chain (--requirement): requirement file →
    # bootstrap pre-chain → sign-ready campaign plan. Mutually exclusive with
    # --campaign (the emitted plan is DRIVEN by a later --campaign invocation).
    if args.requirement:
        if args.campaign:
            print("--requirement and --campaign are mutually exclusive: the "
                  "bootstrap EMITS the plan a later --campaign run drives.")
            return CAMPAIGN_EXIT_INVALID
        # Commit C (design §4): at a TTY with no decision file, wire the SAME
        # interactive gate resolver full_chain_guided uses, so gate-1 + the
        # inline plan sign land in ONE sitting. Non-TTY: the decision-file
        # resolver (when --decision) or a clean rc-10 halt (never auto-signs).
        _gate_resolver = None
        if (args.decision is None and sys.stdin is not None
                and sys.stdin.isatty()):
            _gate_resolver = make_interactive_gate_resolver()
        return run_requirement_entry(
            charter, requirement_path=args.requirement,
            charter_path=args.charter, repo_dir=args.repo_dir,
            campaign_out=args.campaign_out, campaign_id=args.campaign_id,
            run_dir=args.run_dir, resume=args.resume,
            decision_path=args.decision, allow_real=args.allow_real,
            clock=_production_clock(), memory_root=effective_memory_root,
            allow_gitlink_drift=args.allow_gitlink_drift,
            gate_resolver=_gate_resolver, start=args.start,
            campaign_run_dir=args.campaign_run_dir)

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
            # OW-M3 (design §3.2 / D4): refuse to sign a plan that would accept a
            # user-facing requirement on non-browser-E2E evidence, or that covers an
            # unclassified requirement. Dormant when no ledger is wired; a wired-but-broken
            # ledger REFUSES (strict) rather than silently signing around the mandate.
            try:
                _ow_ledger = load_requirement_ledger_strict(
                    resolve_ledger_path(charter, args.repo_dir))
            except LedgerError as exc:
                print(f"--sign-plan REFUSED: {exc}")
                return 2
            _ow_violations = _cp.mandatory_e2e_violations(plan, charter, _ow_ledger)
            if _ow_violations:
                print(_cp.render_mandatory_e2e_refusal(
                    _ow_violations, action="refusing to sign the plan"))
                return 2
            # Phase-4 native-E2E capability contract (design §2/§13): refuse to SIGN a plan
            # whose charter pins a framework capability this deployed aidazi does not provide
            # (deterministic, fail-closed). Dormant when the charter declares none.
            if charter.get("required_framework_capabilities"):
                import framework_capabilities as _fc  # engine-kit on sys.path
                try:
                    _cap_violations = _fc.required_capability_violations(charter)
                except _fc.CapabilityContractError as exc:
                    print(f"--sign-plan REFUSED: {exc}")
                    return 2
                if _cap_violations:
                    print(_fc.render_capability_refusal(
                        _cap_violations, action="refusing to sign the plan"))
                    return 2
            _prior_pad = (plan.get("signoff") or {}).get(
                "prompt_artifacts_digest")
            if _prior_pad is not None and not args.repo_dir:
                print("--sign-plan REFUSED: this plan's signoff binds compact "
                      "prompt files (prompt_artifacts_digest) — re-signing "
                      "WITHOUT --repo-dir would STRIP that binding and let "
                      "edited prompts read 'signed'. Pass --repo-dir "
                      "<adopter repo> (Phase-2 design §3.5, fail-closed).")
                return 2
            signed = _cp.stamp_signoff(plan, charter,
                                       signed_at=_production_clock()(),
                                       charter_ref=os.path.abspath(args.charter),
                                       ledger=_ow_ledger,
                                       repo_dir=args.repo_dir)
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
            repo_dir=args.repo_dir, memory_root=effective_memory_root,
            allow_gitlink_drift=args.allow_gitlink_drift)
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

    try:
        info = run_loop(
            charter, run_dir=run_dir, loop_id=loop_id,
            subsprint_id=args.subsprint_id, clock=_production_clock(),
            allow_real=args.allow_real, mode=args.mode,
            repo_dir=args.repo_dir, memory_root=effective_memory_root,
            loop_mode=args.loop_mode, gate_resolver=gate_resolver,
            resume=args.resume, allow_gitlink_drift=args.allow_gitlink_drift,
        )
    except CharterValidationError as exc:
        # A real-run preflight refusal (charter schema / skills integrity/drift) —
        # a clean, actionable abort (exit 2, matching the charter-error code), never
        # a raw traceback. No adapter was built or invoked.
        print(f"REAL RUN ABORTED before any adapter was invoked: {exc}")
        return 2

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
