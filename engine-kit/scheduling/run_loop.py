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
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
from adapters import MockAdapter, resolve_adapter_class  # noqa: E402
from driver import Driver, load_charter, route_for_role  # noqa: E402

MODE_OVERNIGHT_AUTOLOOP = "overnight_autoloop"
MODE_MILESTONE_DELIVERY = "milestone_delivery"
MODES = (MODE_OVERNIGHT_AUTOLOOP, MODE_MILESTONE_DELIVERY)

# Default clean-pass canned verdicts for the offline DRY-RUN mock path. These let
# a scheduled dry-run exercise the full P2 happy path (dev→gate→review→close→
# advance) with zero network. A real run uses --allow-real and never sees these.
_DRY_REVIEW = {"decision": "pass", "blocking_count": 0,
               "summary": "dry-run: no blocking findings", "findings": []}
_DRY_CLOSE = {"verdict": "A", "blocking_count": 0, "worst_severity": "none",
              "in_scope": True, "next_subsprint": None,
              "reason": "dry-run clean pass"}
_DRY_DEV = {"artifact": "dry-run handoff"}


def _roles_in_charter(charter: dict) -> list:
    """The roles the charter routes (tooling.<role>), excluding non-role keys."""
    tooling = charter.get("tooling") or {}
    return [r for r in ("research", "deliver", "dev", "review", "acceptance")
            if r in tooling]


def build_adapters(charter: dict, *, allow_real: bool = False) -> Dict[str, object]:
    """Build one adapter per routed role from the charter's per-role routing.

    DEFAULT (``allow_real=False``) → a MockAdapter per role carrying a clean-pass
    canned verdict (offline dry-run / smoke test). With ``allow_real=True`` →
    the real adapter class from ADAPTER_REGISTRY for the role's harness, carrying
    its provider/model (+ endpoint as base_url and api_key_env when present). Real
    adapters still refuse I/O unless AIDAZI_ALLOW_REAL_ADAPTER=1 (their own gate),
    so building them is safe; only spawning with the env set reaches the network.
    """
    canned_by_role = {
        "dev": {("dev",): _DRY_DEV},
        "review": {("review",): _DRY_REVIEW},
        "deliver": {("deliver",): _DRY_CLOSE},
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
            adapters[role] = cls(
                provider=r.provider or "",
                model=r.model or "",
                base_url=tooling.get("endpoint", ""),
                api_key_env=tooling.get("api_key_env", ""),
            )
        else:
            adapters[role] = MockAdapter(
                canned_by_role.get(role, {(role,): _DRY_DEV}),
                harness=r.harness or "mock",
                provider=r.provider or "mock",
                model=r.model or "mock-model",
            )
    return adapters


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
) -> dict:
    """Run ONE loop end-to-end and return a summary dict.

    ``adapters`` may be injected (tests pass mocks); otherwise they are built via
    ``build_adapters(charter, allow_real=...)``. ``clock`` is injected (production
    passes a real ISO clock; tests pass a deterministic one). ``mode`` is recorded
    in the loop_start audit context. ``repo_dir`` enables Loop Ingress;
    ``memory_root`` enables Loop Memory — both optional (off → byte-identical).
    """
    if mode not in MODES:
        raise ValueError(f"mode {mode!r} not one of {MODES}")
    if adapters is None:
        adapters = build_adapters(charter, allow_real=allow_real)

    driver = Driver(
        charter, run_dir, adapters,
        loop_id=loop_id, clock=clock,
        context={"schedule_mode": mode, "allow_real": allow_real},
        repo_dir=repo_dir, memory_root=memory_root,
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
    parser.add_argument("--allow-real", action="store_true",
                        help="build REAL adapters (still gated by AIDAZI_ALLOW_REAL_ADAPTER)")
    args = parser.parse_args(argv)

    charter = load_charter(args.charter)
    run_dir = args.run_dir or tempfile.mkdtemp(prefix=f"aidazi-{args.mode}-")
    loop_id = args.loop_id or f"{args.mode}-{args.subsprint_id}"

    info = run_loop(
        charter, run_dir=run_dir, loop_id=loop_id,
        subsprint_id=args.subsprint_id, clock=_production_clock(),
        allow_real=args.allow_real, mode=args.mode,
        repo_dir=args.repo_dir, memory_root=args.memory_root,
    )

    print(f"=== aidazi schedule run ({info['mode']}) ===")
    print(f"run dir        : {info['run_dir']}")
    print(f"adapters       : {'real' if args.allow_real else 'mock (dry-run)'}")
    print(f"state trace    : idle -> {' -> '.join(info['history'])} -> {info['final_state']}")
    print(f"final state    : {info['final_state']}  (clean={info['clean']})")
    print(f"spawn count    : {info['spawn_count']}  (fix rounds: {info['fix_round']})")
    print(f"audit ledger   : {info['audit_ledger']}")
    print(f"audit chain    : {info['audit_render']}")
    print(f"audit verifies : {info['audit_verifies']}")
    return 0 if info["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
