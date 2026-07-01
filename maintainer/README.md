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
- **Claude Code** (live-verified): the repo-local `.claude/settings.json` hook is **active
  automatically** in any fresh session (project hooks need no separate approval). `UserPromptSubmit`
  runs `map_briefing.py --hook claude`; its plain stdout (a compact structural briefing) is injected.
- **Codex CLI** (live-verified): `.codex/hooks.json` `UserPromptSubmit` runs `map_briefing.py --hook
  codex`, injecting via `hookSpecificOutput.additionalContext` and resolving the repo from the payload
  **`cwd`** (Codex runs hooks in a sandbox where `os.getcwd()`/git are unreliable). `codex features`
  shows `hooks` `stable`/enabled. **First use: open the Codex TUI once and run `/hooks` to hash-trust
  the current hook definition** (the project is already trusted); after that it is autonomous in every
  new session. **Re-trust is needed if this hook definition changes.**
- **Cursor (experimental):** `.cursor/rules/00-codebase-map.mdc` — an always-apply rule (Cursor has no
  `UserPromptSubmit` hook), so the agent runs the selector itself. Not a hook; best-effort.

**Hard timeout (external to Python; not relying on the script to return).** A hung script/subprocess
is force-killed at **8s**, then the hook fail-opens:
- **Claude**: a command-level `perl -e 'alarm 8; exec @ARGV'` (Claude fail-*closes* on a harness hook
  timeout, so we self-limit and `exit 0` first, well within Claude's 30s `UserPromptSubmit` limit).
- **Codex**: the native handler `"timeout": 8` (Codex fail-*opens* on timeout — verified; perl does
  not run in the Codex sandbox).

**Guarantees (do not weaken):** READ-ONLY (reads the map + `git` only). **It does NOT intercept coding
tools** — the only hook is `UserPromptSubmit` (a context-injector); there is **NO PreToolUse /
PostToolUse hook, and NO receipt / epoch / mutation-ledger** anywhere. **FAIL-OPEN**: on any error,
missing/malformed map, invalid checkpoint, git failure, unmappable/trivial task, exception, **or the
8s hard timeout (hang)**, it emits nothing and the command **exits 0**; **under the tested harnesses
(Claude Code, Codex) a hook failure or timeout does not block the normal prompt/coding loop** (see the
per-harness timeout note above — Claude fail-closes on a *harness* timeout, which is why we self-limit
first). The briefing is **structural pointers only** (no answers, no config values — Phase-0 anti-leak)
and stays compact (~0.5–1K tokens); tiny/obvious tasks get a minimal pointer or nothing.

**Stateless trigger (honest scope):** it fires on `UserPromptSubmit` for every *substantive mapped*
prompt — including the first coding task — and skips trivial/continuation prompts. There is **no
session state / first-use latch** (that would edge toward the banned receipt pattern, and the Codex
hook sandbox discards writes anyway), so a later distinct task simply re-selects and re-injects — which
is intended (new task → new relevant areas). Advisory diagnostics are silent unless
`MAP_BRIEFING_DEBUG=1`.

**Scope (measured, Phase-0 `archive/phase0-codebase-map/`):** the value is **less re-scanning + faster
orientation** (read-volume ≈ −53%, faster localization, no quality drop) — **NOT** a lower token bill.

Test: `python3 -m pytest maintainer/tests/ -q`.
