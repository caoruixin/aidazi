# Full cold-start baseline evidence (Quick-Fix Lane — Commit 0 / QF-0)

**Status:** RECORDED (2026-06-21) · **Kind:** evidence baseline · **Scope:** Commit 0 of the
Quick-Fix Lane series — **evidence only, no QF runtime behavior**.
**Companion:** [R1 follow-up — Claude Code does not auto-load AGENTS.md](2026-06-21-followup-claude-code-agentsmd-baseline.md)

## Why this doc exists

The Quick-Fix Lane claims it loads **less** at session cold-start than a normal
("Default Full") session. A reduction claim is only meaningful against a pinned
baseline. This doc pins that baseline: **what each supported coding-agent harness
auto-loads into context at session start, before the human's first message**, in
the normal Full path. It serves two later purposes:

1. The **denominator** for the QF lane's reduced load-graph evidence (Commit 3).
2. The reference for the **Default-Full regression** (Commit 1): the standard
   startup path must stay byte-/load-graph-identical after the QF lane is added.

## Method

Harness behavior was established from the official vendor documentation, pulled and
cross-checked on 2026-06-21 via the `claude-code-guide` investigation:

- Claude Code: `code.claude.com/docs/en/memory`, `…/cli-reference`, `…/sub-agents`.
- OpenAI Codex: `developers.openai.com/codex` (AGENTS.md guide, config reference).
- Cursor: `cursor.com/docs/rules`.

These are **documented behaviors as of 2026-06-21**. Vendor harness behavior is
version-sensitive, so treat the matrix below as a **dated snapshot**, not a permanent
guarantee; re-verify against current docs before relying on a row.

## Cold-start auto-load, per harness (Full path, cwd = adopter repo root)

| Harness | Auto-loaded project memory | Discovery algorithm | `@`/import recursion |
|---|---|---|---|
| **Claude Code** | **`CLAUDE.md` only** (NOT `AGENTS.md`) + `CLAUDE.local.md` | Walks **up** the dir tree from cwd to filesystem root; concatenates every `CLAUDE.md` found (root→cwd order). Subdir `CLAUDE.md` load lazily on file access, not at start. Plus `~/.claude/CLAUDE.md`. | `@path` imports expanded **at launch**, recursive, **max depth 4**; `~` expansion supported |
| **OpenAI Codex** | **`AGENTS.md`** | Walks the dir tree from cwd up to project root; concatenates each level | (per Codex AGENTS.md docs; override/import specifics not pinned here) |
| **Cursor** | **`.cursor/rules/*.mdc`** | Auto-loads matching rule files before first input; nested rules load on matching file access | scoped by file globs |

### Mechanisms that change what loads (relevant to the QF lane)

- `--add-dir <dir>` (Claude Code) grants **file access only**; it does **not** load
  that dir's `CLAUDE.md`. ← the QF lane relies on this.
- The **only** reliable ways to avoid the ancestor `CLAUDE.md` auto-load are:
  `--bare` / `--safe-mode` (skip CLAUDE.md + customizations), `settings.json`
  `claudeMdExcludes`, or **launching with cwd in a directory that has NO `CLAUDE.md`
  in any ancestor** (then `--add-dir` the repo). ← the QF lane uses the last one
  (an out-of-tree ephemeral bundle).
- Built-in **Explore/Plan** subagents skip `CLAUDE.md`; custom/general subagents do
  not. Slash commands and subagent definitions load **after** cold-start (too late
  to reduce cold-start tokens).
- `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` disables the *auto-memory* feature only, **not**
  `CLAUDE.md` loading.

## The Default-Full baseline this doc pins

For a **correctly wired** adopter (root memory file that the harness actually
auto-loads — `CLAUDE.md` for Claude Code, `AGENTS.md` for Codex, `.cursor/rules` for
Cursor), a Full cold-start loads, before the first human message:

1. The always-load governance chain — `governance/constitution.md`,
   `governance/doc_governance.md`, `governance/context_briefing.md`
   (`load_discipline: always-load`; `AGENTS.md` §2 + `context_briefing.md` §1).
2. The adopter root memory file itself (`AGENTS.md`/`CLAUDE.md`/`.cursor/rules`).
3. The adopter `docs/current/*` ledgers referenced by `AGENTS.md` §3 (effectively
   always-load per `context_briefing.md` §1).
4. The role card + per-role briefing once a role is adopted.

This is the load-graph the Quick-Fix Lane is measured **against** and must leave
**unchanged**. Commit 1 adds a regression that asserts the standard startup path
(the always-load chain + the consumer `AGENTS.md` template) is unmodified.

## Honest-status caveat (load-bearing)

The Claude Code row exposes a real gap: **Claude Code does not auto-load
`AGENTS.md`**, yet the consumer template and the worked example ship the root file
as `AGENTS.md` (`examples/minimal-greenfield/AGENTS.md`). Until the
[R1 follow-up](2026-06-21-followup-claude-code-agentsmd-baseline.md) is **resolved or
disproven**, no doc may claim the **Claude Code adopter Default-Full baseline is
guaranteed**. (This does NOT block the QF lane itself: the QF lane's out-of-tree
bundle ships its own `CLAUDE.md`, which Claude Code *does* auto-load — so QF cold-start
control is independent of R1.)

---

End of Full cold-start baseline evidence.
