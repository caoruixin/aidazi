# claude-code-full-wiring — real Default-Full cold-start canary

A reproducible, **real** proof (not a static parser) that Claude Code's Default-Full baseline
depends on the harness root-file wiring in `governance/context_briefing.md` §1.1:

- **Positive:** a root `CLAUDE.md` (`@AGENTS.md`) → Claude Code auto-loads the `AGENTS.md`
  governance chain at cold-start (a unique canary token is echoed).
- **Negative control:** a root with only a bare `AGENTS.md` (no `CLAUDE.md`) → Claude Code does
  **not** auto-load it (the same token never appears).

## Run

```bash
examples/claude-code-full-wiring/verify-full-coldstart.sh          # clean up after
examples/claude-code-full-wiring/verify-full-coldstart.sh --keep   # keep fixtures + captures
```

It launches two real `claude -p` sessions (uses your Claude auth), mints a fresh random canary
each run (so the user-global `~/.claude/CLAUDE.md` cannot cause a false positive), and disallows
file-reading tools so the negative control cannot reach `AGENTS.md` by reading it. Exit 0 ⇒ both
the positive and negative assertions held.

Captured evidence from the 2026-06-22 run (Claude Code 2.1.170, macOS arm64):
`archive/2026-06-22-claude-code-default-full-wiring-evidence.md`.

The deterministic, no-auth counterpart of this check is
`engine-kit/validators/adopter_wiring_validator.py` (run in onboarding Step 8); this script is the
live-harness proof that the validator gates a behavior the real harness exhibits.
