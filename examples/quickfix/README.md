# examples/quickfix — Quick-Fix lane worked example

A runnable demonstration of the **Quick-Fix lane** (`process/quickfix-lane.md`, `QUICK-FIX.md`)
on the `claude_code` harness — also the **reproducible evidence** behind marking `claude_code`
`supported`.

## Files

- **`e2e-claude-code.sh`** — stands up a throwaway "adopter" repo (NOT this framework repo),
  plants **canary** governance files (`CLAUDE.md`/`AGENTS.md` that would echo a unique token
  if cold-started), runs the real Quick-Fix lane against it, and checks all 16 acceptance
  criteria — including that the canary never reaches the harness (the adopter governance chain
  was not cold-started). Launches a real `claude -p` subprocess and uses your Claude auth.
- **`request.example.json`** — the `quickfix-request.json` the demo uses: a human-explicit,
  non-behavioral version bump scoped to a single file with a structured verification.

## Run it

```bash
examples/quickfix/e2e-claude-code.sh          # clean up the fixture afterward
examples/quickfix/e2e-claude-code.sh --keep   # leave the fixture for inspection
```

Requires: the `claude` CLI (≥ 2.0.0) on PATH and authenticated, plus `python3.12`. Expected
result: `16 passed, 0 failed`. The latest recorded run is
`archive/2026-06-22-quickfix-claude-code-e2e-evidence.md`.

> The lane is fail-closed by design. `claude_code` and `codex` are `supported` in the shipped
> registry; `kimi_code` is `unsupported`, so the lane refuses it (exit `11`). The codex
> qualification E2E is `examples/quickfix/e2e-codex.sh`
> (`archive/2026-06-22-quickfix-codex-e2e-evidence.md`).
