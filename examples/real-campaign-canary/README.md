# real-campaign-canary — the REAL end-to-end campaign proof (Phase-1 work item D)

Design: `archive/2026-07-09-autonomy-roadmap-campaign-unblock.md` §2 (Codex R0.3
APPROVE). Before this canary, NO real-adapter campaign had ever completed the
full CLI contract — only mock dry-runs and single-role real E2E existed.

## What it proves

One env-gated test (`engine-kit/scheduling/tests/test_real_campaign_canary.py`)
drives the REAL `run_loop.py --campaign` contract with real `claude_code`
spawns (Dev / Review / Deliver / Acceptance), from a scratch copy of
`workspace/`:

1. `--sign-plan` → rc 0, F1 signoff stamped into the plan.
2. `--campaign --allow-real` → rc **10**, paused at
   `advisory_acceptance_pass_signoff` on `m1-hello` (real Dev wrote
   `notes/hello.md` = `HELLO-CANARY-M1`).
3. identity-bound decision `ship` + `--resume` → rc **10**, paused again on
   `m2-append` (real Dev appended `HELLO-CANARY-M2`).
4. second `ship` decision + `--resume` → rc **0**, campaign done,
   `milestones_delivered == 2`.

Assertions are FLOW-invariants only (exit codes, pause reasons, workspace file
bytes, audit-event counts, no agent-stuck diagnostics — i.e. zero watchdog
false-kills under the stream-lease probes). Model prose is never asserted.

## R0 B-4 prerequisites (why the first pause is legitimately the sign-off)

Real/non-mock runs refuse thin prompts (driver `_strict_prompts`), so:
- `charter.yaml` ships a SIGNED `intent_contract`
  (`confirmed_by_human: true` — the canary author's signature; the evidence
  doc records it), which Acceptance judges against.
- `workspace/compact/` ships per-sub-sprint self-contained Dev + Review
  prompts (`context_budget.self_contained: true`).
Any refinement halt before `advisory_acceptance_pass_signoff` is a canary
FAILURE, not a resolvable gate.

## Running it

```bash
# offline (always on in the suite): inputs stay schema-valid
python3.12 -m pytest engine-kit/scheduling/tests/test_real_campaign_canary_inputs.py -q

# REAL run (billed claude_code spawns; explicit double gate):
AIDAZI_E2E_REAL_CAMPAIGN=1 \
python3.12 -m pytest engine-kit/scheduling/tests/test_real_campaign_canary.py -q -s
```

The real test exports `AIDAZI_ALLOW_REAL_ADAPTER=1` into the child CLI
environment only. Evidence from the accepted run:
`archive/2026-07-09-real-campaign-canary-evidence.md`.
