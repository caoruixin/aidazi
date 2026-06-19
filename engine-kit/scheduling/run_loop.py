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
``AIDAZI_ALLOW_REAL_ADAPTER=1`` (the adapters' own gate). Artifacts always go to a
RUN DIR outside the repo.

NORMATIVE SOURCE: archive/2026-06-15-v2-loop-engine-plan.md §4.4 / P5. The kit is
a reference implementation; on any conflict the spec wins and this file is the bug.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
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
    final = driver.run(subsprint_id=subsprint_id)
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="aidazi schedule entrypoint — run one loop (plain cron/CI).")
    parser.add_argument("--charter", required=True, help="path to the charter YAML")
    parser.add_argument("--mode", choices=MODES, default=MODE_MILESTONE_DELIVERY)
    parser.add_argument("--loop-id", default=None,
                        help="loop_id (default: derived from mode + subsprint)")
    parser.add_argument("--subsprint-id", default="sprint-001")
    parser.add_argument("--run-dir", default=None,
                        help="run-artifact dir (default: a fresh temp dir; never the repo)")
    parser.add_argument("--repo-dir", default=None,
                        help="git repo for Loop Ingress (optional; off by default)")
    parser.add_argument("--memory-root", default=None,
                        help="Loop Memory root (optional; off by default)")
    parser.add_argument("--loop-mode", choices=LOOP_MODES,
                        default=LOOP_MODE_DELIVERY_ONLY,
                        help="delivery_only (default) | full_chain_guided "
                             "(adds research → gate1 → decompose pre-states)")
    parser.add_argument("--allow-real", action="store_true",
                        help="build REAL adapters (still gated by AIDAZI_ALLOW_REAL_ADAPTER)")
    args = parser.parse_args(argv)

    charter = load_charter(args.charter)
    run_dir = args.run_dir or tempfile.mkdtemp(prefix=f"aidazi-{args.mode}-")
    loop_id = args.loop_id or f"{args.mode}-{args.subsprint_id}"

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
        repo_dir=args.repo_dir, memory_root=args.memory_root,
        loop_mode=args.loop_mode, gate_resolver=gate_resolver,
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
