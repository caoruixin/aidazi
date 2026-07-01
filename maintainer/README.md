# maintainer/ — maintainer-only session tooling (NOT vendored to adopters)

This directory is **outside the vendor allowlist** (`engine-kit/tools/vendor-framework.sh` copies only
its `INCLUDE` list), so nothing here ever lands in an adopter repo. It holds tooling for the person
developing the aidazi framework itself.

## Codebase Context Map — autonomous read-only orientation entry (Phase 1)

`map_briefing.py` gives every fresh maintainer coding session the codebase-map navigation benefit
**automatically**, with **no human reminder, manual command, manual section selection, or unlock**,
and **without ever becoming an execution gate**.

**How it auto-fires** (per harness, priority: native repo-instruction → native hook → thin wrapper;
priority-1 is unavailable here because Claude Code `CLAUDE.md` / Codex `AGENTS.md` are the vendored,
adopter-facing entry points, so we use the native **hook** path):
- **Claude Code** (live-verified): `.claude/settings.json` → `UserPromptSubmit` hook runs
  `map_briefing.py --hook claude`; its plain stdout (a compact structural briefing) is injected into
  the session. Fires automatically in any fresh session (project hooks need no separate approval).
- **Codex CLI** (live-verified): `.codex/hooks.json` → `UserPromptSubmit` hook runs
  `map_briefing.py --hook codex`, which injects via `hookSpecificOutput.additionalContext` and
  resolves the repo from the payload **`cwd`** (Codex runs hooks in a sandbox where `os.getcwd()` is
  NOT the repo). `codex features` shows `hooks` as `stable`/enabled. Needs a **one-time** `/hooks`
  hash-trust (Codex security; the exact hook definition is hash-trusted); fires automatically in
  every session thereafter.
- **Cursor (experimental, non-blocking):** `.cursor/rules/00-codebase-map.mdc` — an always-apply rule
  (Cursor has no `UserPromptSubmit` hook), so the agent runs the selector itself.

**Guarantees (do not weaken):** READ-ONLY (reads the map + `git` only); **FAIL-OPEN** — on any error,
missing/malformed map, invalid checkpoint, git failure, unmappable/trivial task, or exception it emits
nothing and **exits 0** (the hook *command* is also wrapped to always exit 0, so a missing script
can't block a prompt either); there is **NO PreToolUse / receipt / epoch / mutation-ledger** anywhere,
so it cannot deny or delay `Edit`/`Bash`/`commit`/subagent/worktree/cross-repo work. The briefing is
**structural pointers only** (no answers, no config values — Phase-0 anti-leak) and stays compact
(~0.5–1K tokens); tiny/obvious tasks get a minimal pointer or nothing.

**Stateless trigger (honest scope):** it fires on `UserPromptSubmit` for every *substantive mapped*
prompt — including the first coding task — and skips trivial/continuation prompts. There is **no
session state / first-use latch** (that would edge toward the banned receipt pattern, and the Codex
hook sandbox discards writes anyway), so a later distinct task simply re-selects and re-injects — which
is intended (new task → new relevant areas). Advisory diagnostics are silent unless
`MAP_BRIEFING_DEBUG=1`.

**Scope (measured, Phase-0 `archive/phase0-codebase-map/`):** the value is **less re-scanning + faster
orientation** (read-volume ≈ −53%, faster localization, no quality drop) — **NOT** a lower token bill.

Test: `python3 -m pytest maintainer/tests/ -q`.
