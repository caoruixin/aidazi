#!/usr/bin/env python3
"""record_run — capture an OFFLINE, DETERMINISTIC recorded run of the aidazi
Delivery Loop on this worked example (minimal-greenfield, RB-001 UC-1).

This is the P6 "recorded run" PROOF. It drives the framework-owned standalone
driver (engine-kit/orchestrator/driver.py) through one full sub-sprint of the
Delivery Loop — idle → dev_pending → gate_pending → review_pending →
close_pending → advance — using the MOCK adapter per role, with per-role harness
routing read from this example's charter.yaml:
  Dev     -> harness claude_code  (MockAdapter standing in)
  Review  -> harness headless     (MockAdapter standing in)   <-- multi-model
  Deliver -> harness claude_code  (MockAdapter standing in)

Everything is offline + deterministic: the real claude_code/headless paths never
run, and a monotonic INJECTED clock makes the audit hash chain reproducible. ALL
run artifacts (state.json, docs/checkpoints/, .orchestrator/audit/) go to a RUN
DIR under the system temp — NEVER into the repo and NEVER into
examples/minimal-greenfield. The ONLY committed artifact is the rendered proof
doc (docs/recorded-run.md), which ``main()`` writes/refreshes.

Usage:
    python examples/minimal-greenfield/record_run.py        # refresh the proof doc
    python examples/minimal-greenfield/record_run.py --print # just print, no write
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

# Locate this example + the engine-kit it reuses, then put engine-kit/ (and its
# audit/ + orchestrator/ subdirs) on sys.path so `audit_log`, `adapters`, and
# `driver` resolve regardless of the caller's cwd — exactly like demo.py.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))     # examples/minimal-greenfield/
_REPO_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))   # repo root
_ENGINE_KIT_DIR = os.path.join(_REPO_ROOT, "engine-kit")
_ORCH_DIR = os.path.join(_ENGINE_KIT_DIR, "orchestrator")
for _p in (_ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit"), _ORCH_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_log as audit  # noqa: E402
from adapters import MockAdapter  # noqa: E402
from driver import Driver, load_charter, route_for_role  # noqa: E402

CHARTER_PATH = os.path.join(_THIS_DIR, "charter.yaml")
PROOF_DOC = os.path.join(_THIS_DIR, "docs", "recorded-run.md")
LOOP_ID = "loop-mg-recorded-001"
SUBSPRINT_ID = "sprint-001"


def _deterministic_clock():
    """A monotonic injected clock so the recorded run's audit hashes — and thus
    the whole proof transcript — are byte-reproducible (copied from demo.py)."""
    seq = {"n": 0}

    def _now() -> str:
        seq["n"] += 1
        return f"2026-06-15T12:{seq['n']:02d}:00Z"

    return _now


def build_adapters(charter: dict) -> dict:
    """One MockAdapter per role, each tagged with the harness the charter routes
    that role to — so the audit ledger records Dev on claude_code and Review on
    headless (per-role routing) even though both are mock-backed offline.

    Canned verdicts produce a CLEAN pass for sprint-001 (the eligibility tool +
    INIT->CHECK pipeline): review→pass, deliver close→A / in_scope → advance.
    These are MOCK results — they prove the loop MECHANICS, not real model output.
    """
    canned = {
        # Dev: spawn_dev's artifact has no verdict schema; return a sentinel dict
        # describing the sprint-001 handoff (eligibility tool + INIT->CHECK).
        ("dev",): {"artifact": "handoff written", "subsprint": SUBSPRINT_ID},
        # Review: a schema-valid review-verdict.schema.json `pass`.
        ("review",): {
            "decision": "pass",
            "blocking_count": 0,
            "summary": ("Eligibility tool + INIT->CHECK pipeline reviewed; "
                        "deterministic eligibility math, no blocking findings."),
            "findings": [],
        },
        # Deliver close: a schema-valid deliver-close-verdict.schema.json clean A.
        # next_subsprint is sprint-002 (denial-reason, UC-2) per the M1 sequence;
        # sprint-001 is the FIRST sub-sprint, so this is a per-sub-sprint advance.
        ("deliver",): {
            "verdict": "A",
            "blocking_count": 0,
            "worst_severity": "none",
            "in_scope": True,
            "next_subsprint": "sprint-002",
            "reason": ("Clean pass; sub-sprint stayed within charter "
                       "approved_scope (eligibility.py + check.py only)."),
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


def record(run_dir: str) -> dict:
    """Run sub-sprint 1 of the Delivery Loop end-to-end against ``run_dir`` (a
    temp dir; NEVER the repo) and return a deterministic summary of the run.

    The summary is the proof's source of truth: final state, the state trace,
    spawn/fix-round counts, the audit chain verification line, the ordered audit
    event types, and any checkpoint files produced (none on the clean path)."""
    charter = load_charter(CHARTER_PATH)
    adapters = build_adapters(charter)
    driver = Driver(
        charter, run_dir, adapters,
        loop_id=LOOP_ID, clock=_deterministic_clock(),
        context={"adopter": os.path.relpath(_THIS_DIR, _REPO_ROOT),
                 "objective": "docs/sprint_objective.md (read-only)",
                 "brief": "docs/research-briefs/RB-001-refund-eligibility.md"},
    )
    final = driver.run(subsprint_id=SUBSPRINT_ID)
    chain = audit.verify_chain(driver.audit_ledger)
    # Ordered audit event types — the spine of the proof (one per ledger line).
    event_types = [e["type"] for e in audit.read_events(driver.audit_ledger)]
    # Checkpoint files the run emitted (none on a clean dev->...->advance path).
    cp_dir = driver.checkpoints_dir
    checkpoints = sorted(os.listdir(cp_dir)) if os.path.isdir(cp_dir) else []
    return {
        "loop_id": LOOP_ID,
        "subsprint_id": SUBSPRINT_ID,
        "mission_id": (charter.get("mission") or {}).get("id"),
        "final_state": final.state,
        "history": list(final.history),
        "spawn_count": final.spawn_count,
        "fix_round": final.fix_round,
        "routing": {role: a.harness for role, a in adapters.items()},
        "audit_event_count": chain.count,
        "audit_verifies": chain.ok,
        "audit_render": chain.render(),
        "audit_event_types": event_types,
        "checkpoints": checkpoints,
    }


def render_proof(info: dict) -> str:
    """Render the committed proof transcript (docs/recorded-run.md) from a
    ``record()`` summary. Because the summary is deterministic, this output is
    byte-stable across runs — re-running cannot silently change the doc."""
    trace = "idle -> " + " -> ".join(info["history"]) + f" -> {info['final_state']}"
    routing = info["routing"]
    event_lines = "\n".join(f"{i}. `{t}`"
                            for i, t in enumerate(info["audit_event_types"]))
    if info["checkpoints"]:
        cp_block = "\n".join(f"- `{name}`" for name in info["checkpoints"])
    else:
        cp_block = ("_(none — the clean dev → gate → review → close → advance "
                    "path emits no checkpoint)_")
    return f"""<!-- GENERATED by examples/minimal-greenfield/record_run.py — do not edit by hand. -->

# Recorded run — minimal-greenfield Delivery Loop (offline proof)

This is a **recorded, deterministic, offline** end-to-end run of the aidazi
Delivery Loop on this worked example. It proves the framework-owned standalone
driver (`engine-kit/orchestrator/driver.py`) drives a full sub-sprint of the loop
for milestone **{info['mission_id']}** / sub-sprint **`{info['subsprint_id']}`**
(the eligibility-check tool + INIT→CHECK pipeline, RB-001 UC-1).

> **These are MOCK-adapter results.** Each role is backed by a deterministic
> `MockAdapter` returning canned, schema-valid verdicts — the real
> `claude_code` / `headless` model paths never run. This proves the **mechanics**
> of the loop (state machine, per-role routing, verdict validation, audit spine),
> NOT real model output.

## How to regenerate

```bash
python examples/minimal-greenfield/record_run.py
```

The run writes all artifacts (`state.json`, `docs/checkpoints/`,
`.orchestrator/audit/`) to a fresh **temp dir** — never into the repo. A monotonic
injected clock makes the audit hash chain reproducible, so re-running produces
this file **byte-for-byte**. (`tests/test_recorded_run.py` enforces that.)

## Per-role harness routing (from `charter.yaml`)

| Role | Harness (mock-backed) |
|---|---|
| Dev | `{routing['dev']}` |
| Review | `{routing['review']}` |
| Deliver | `{routing['deliver']}` |

## Captured run

- **State trace:** `{trace}`
- **Final state:** `{info['final_state']}`
- **Spawn count:** {info['spawn_count']}  (**fix rounds:** {info['fix_round']})
- **Audit chain:** {info['audit_render']}
- **Audit verifies:** {info['audit_verifies']}

### Audit event types (in order)

{event_lines}

### Checkpoint files produced

{cp_block}

---

_Generated by `examples/minimal-greenfield/record_run.py`. Loop id
`{info['loop_id']}`; injected clock `2026-06-15T12:MM:00Z` (monotonic)._
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Record an offline, deterministic Delivery-Loop run "
                    "(mock adapter) and refresh docs/recorded-run.md.")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="print the proof to stdout; do NOT write the doc")
    args = parser.parse_args(argv)

    # A fresh temp run dir under the SYSTEM temp — never the repo, never this
    # example dir. It is intentionally left in place (small; the OS reaps /tmp).
    run_dir = tempfile.mkdtemp(prefix="aidazi-mg-recorded-")
    info = record(run_dir)
    proof = render_proof(info)

    if args.print_only:
        sys.stdout.write(proof)
    else:
        os.makedirs(os.path.dirname(PROOF_DOC), exist_ok=True)
        with open(PROOF_DOC, "w", encoding="utf-8") as fh:
            fh.write(proof)
        print(f"recorded run -> {os.path.relpath(PROOF_DOC, _REPO_ROOT)}")
        print(f"  run dir (temp) : {run_dir}")
        print(f"  state trace    : idle -> {' -> '.join(info['history'])} "
              f"-> {info['final_state']}")
        print(f"  audit chain    : {info['audit_render']}")

    ok = info["final_state"] == "advance" and info["audit_verifies"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
