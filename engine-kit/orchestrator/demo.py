#!/usr/bin/env python3
"""demo — run the P2 ENGINE-MVP loop on minimal-greenfield context, offline.

Drives the deterministic outer loop (idle → dev_pending → gate_pending →
review_pending → close_pending → advance) using the MOCK adapter, with per-role
harness routing read from engine-kit/orchestrator/examples/p2-charter.yaml:
  Dev     -> harness claude_code  (MockAdapter standing in)
  Review  -> harness headless     (MockAdapter standing in)   <-- multi-model
  Deliver -> harness claude_code  (MockAdapter standing in)

It writes ALL artifacts (state.json, docs/checkpoints/, .orchestrator/audit/) to
a RUN DIR under /tmp — never into the repo, never into examples/minimal-greenfield
(read-only). It then verifies the audit ledger's hash chain and prints the
state-transition trace.

Usage:
    python demo.py [--run-dir DIR]
    python driver-as-module:  python -m orchestrator.demo
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_KIT_DIR = os.path.dirname(_THIS_DIR)
for _p in (_ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit"), _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
from adapters import MockAdapter, ADAPTER_REGISTRY  # noqa: E402
from driver import Driver, load_charter, route_for_role  # noqa: E402

CHARTER_PATH = os.path.join(_THIS_DIR, "examples", "p2-charter.yaml")
# minimal-greenfield is READ-ONLY context the driver records (never writes).
_REPO_ROOT = os.path.dirname(_ENGINE_KIT_DIR)
MINIMAL_GREENFIELD = os.path.join(_REPO_ROOT, "examples", "minimal-greenfield")


def _deterministic_clock():
    """A monotonic injected clock so the demo's audit hashes are reproducible."""
    seq = {"n": 0}

    def _now() -> str:
        seq["n"] += 1
        return f"2026-06-15T12:{seq['n']:02d}:00Z"

    return _now


def build_demo_adapters(charter: dict) -> dict:
    """One MockAdapter per role, each tagged with the harness the charter routes
    that role to — so the audit ledger records Dev on claude_code and Review on
    headless (per-role routing) even though both are mock-backed offline.

    Canned verdicts produce a CLEAN pass: review→pass, close→A/in_scope→advance.
    """
    canned = {
        # Dev: spawn_dev's artifact has no verdict schema; return a sentinel dict.
        ("dev",): {"artifact": "handoff written", "subsprint": "sprint-001"},
        # Review: a schema-valid review-verdict.schema.json `pass`.
        ("review",): {
            "decision": "pass",
            "blocking_count": 0,
            "summary": "Eligibility tool + INIT->CHECK pipeline reviewed; no blocking findings.",
            "findings": [],
        },
        # Deliver close: a schema-valid deliver-close-verdict.schema.json clean A.
        ("deliver",): {
            "verdict": "A",
            "blocking_count": 0,
            "worst_severity": "none",
            "in_scope": True,
            "next_subsprint": "sprint-002",
            "reason": "Clean pass; sub-sprint stayed within charter approved_scope.",
        },
    }
    adapters: dict = {}
    for role in ("dev", "review", "deliver"):
        r = route_for_role(charter, role)
        adapters[role] = MockAdapter(
            {k: v for k, v in canned.items() if k[0] == role},
            harness=r.harness or "mock",
            provider=r.provider or "mock",
            model=r.model or "mock-model",
        )
    return adapters


def run_demo(run_dir: str) -> dict:
    charter = load_charter(CHARTER_PATH)
    adapters = build_demo_adapters(charter)
    loop_id = "loop-p2-demo-001"
    driver = Driver(
        charter, run_dir, adapters,
        loop_id=loop_id, clock=_deterministic_clock(),
        context={"adopter": os.path.relpath(MINIMAL_GREENFIELD, _REPO_ROOT),
                 "objective": "docs/sprint_objective.md (read-only)"},
    )
    final = driver.run(subsprint_id="sprint-001")
    result = audit.verify_chain(driver.audit_ledger)
    return {
        "final_state": final.state,
        "history": final.history,
        "spawn_count": final.spawn_count,
        "fix_round": final.fix_round,
        "adapters": {role: a.harness for role, a in adapters.items()},
        "audit_ledger": driver.audit_ledger,
        "audit_verifies": result.ok,
        "audit_render": result.render(),
        "checkpoints_dir": driver.checkpoints_dir,
        "state_path": driver.state_path,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the P2 engine-MVP demo (mock adapter, offline).")
    parser.add_argument("--run-dir", default=None,
                        help="run-artifact dir (default: a fresh /tmp dir)")
    args = parser.parse_args(argv)

    run_dir = args.run_dir or tempfile.mkdtemp(prefix="aidazi-p2-demo-")
    info = run_demo(run_dir)

    print("=== aidazi P2 engine-MVP demo (mock adapter, offline) ===")
    print(f"run dir          : {run_dir}")
    print(f"per-role routing : Dev->{info['adapters']['dev']}  "
          f"Review->{info['adapters']['review']}  Deliver->{info['adapters']['deliver']}")
    print(f"state trace      : idle -> {' -> '.join(info['history'])} -> {info['final_state']}")
    print(f"final state      : {info['final_state']}")
    print(f"spawn count      : {info['spawn_count']}  (fix rounds: {info['fix_round']})")
    print(f"audit ledger     : {info['audit_ledger']}")
    print(f"audit chain      : {info['audit_render']}")
    print(f"audit verifies   : {info['audit_verifies']}")
    print(f"checkpoints dir  : {info['checkpoints_dir']}")
    return 0 if (info["final_state"] == "advance" and info["audit_verifies"]) else 1


if __name__ == "__main__":
    sys.exit(main())
