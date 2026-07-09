# real-requirement-canary — the requirement-driven chain, end to end, for real

Phase-2 Commit D (archive/2026-07-09-phase2-requirement-chain-design.md §6):
ONE requirement file → real Research brief → gate-1 human sign → real Deliver
two-stage decompose → emitted sign-ready campaign plan + generated compact
prompts → `--sign-plan` → the real campaign to done (advisory pause per
milestone — the ONLY legitimate pauses).

## Contents

- `requirement.md` — the customer ask (two byte-exact sentinel milestones).
- `charter.yaml` — schema-valid charter: signed `intent_contract` (preflight
  0a), non-empty CLOSED-ENUM envelope (0b), all roles real `claude_code`.
- `workspace/` — the (empty) seed the canary test copies into a scratch git
  repo. The chain GENERATES everything else: the brief, the campaign plan,
  the sidecar, and `compact/<sid>-{dev,review}-prompt.md`.

## Run it (billed real agent turns — DOUBLE env gate)

```bash
cd engine-kit
AIDAZI_E2E_REAL_REQUIREMENT=1 python3.12 -m pytest \
  scheduling/tests/test_real_requirement_canary.py -v
```

`AIDAZI_ALLOW_REAL_ADAPTER=1` is exported into the CHILD CLI environment only
(standing rule: every real-CLI activity is env-gated, child env only).

The offline companion (`test_real_requirement_canary_inputs.py`) validates the
charter + requirement inputs in every normal suite run, no gate needed.
