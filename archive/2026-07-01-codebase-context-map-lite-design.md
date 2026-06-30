# Codebase Context Map — Lite (design; pending Codex read-only review)

**Status:** design-only. No automation implemented in this cycle. Deliverable = this doc + the
migrated `process/codebase-map.md` → one Codex **read-only** review → report projected savings /
boundaries / non-goals → STOP.

**Supersedes / provenance:** rolls back the `feat/session-context-bootstrap` experiment (sealed,
tag `experiment/session-context-bootstrap-abandoned`, recoverable, never pushed/merged). That
experiment drifted from "save tokens by not re-scanning" into a write-permission gate
(PreToolUse deny, receipts, epoch lock, authorized-mutation ledger, cross-repo write block). The
gate machinery is **permanently out of scope**. Only the codebase map — the actual asset — is kept.

---

## 1. The one goal (and the one reframing)

Goal, verbatim from the original intent: let a **new maintainer session inherit prior structural
understanding of this codebase from a committed map, instead of re-scanning the tree** — cutting
token spend and repeated re-analysis. Nothing else.

Reframing that keeps it from drifting again: **this is a READ AID, not a control system.** It
informs; it never authorizes. There is no state in which it can block an action.

## 2. The asset (done, on this branch)

`process/codebase-map.md` — committed, standalone, read-only. A fenced ```json index of 33 areas
(`covers` / `anchors` / `tests` / `canonical_docs` / `keywords` / `depends_on` / one-line
`responsibility`) plus prose bodies for the heavy areas, and a `map_checkpoint` commit. Migrated
off the abandoned branch and **independently re-verified against `origin/main` (8e3b20f): 0 missing
paths, 0 missing symbols, 0 dangling deps.** It needs no tool, validator, or hook to be useful.

## 3. Mechanism — minimal, read-only, additive (NOT built yet)

The map projection happens **outside** the model context (a thin script reads the 33 KB map +
git delta and emits a small briefing); only the compact briefing enters context.

- **SessionStart (read-only emitter).** Point to the map; run `git diff <map_checkpoint>..HEAD
  --name-only` and flag which areas drifted. Emits text; on any error emits nothing. Never blocks.
- **First coding task (read-only briefing).** Optionally, on the first task prompt, emit a
  **compact** task-localized briefing: matched sections + suggested read paths. Never blocks. This
  is context-loading only — it has no receipt, no verdict, no follow-on gate.
- **No PreToolUse hook at all.** The entire enforcement surface is removed. Loading context
  (SessionStart / first-task briefing) is fully separated from — and never coupled to — editing.
- **Per-tool thin entries** (Claude SessionStart / read-only UserPromptSubmit; Codex equivalents;
  Cursor `sessionStart` inject + an always-apply *read-the-map* rule). Each may only "remind /
  load context." None may become a write-permission system.
- **Tool-agnostic fallback:** a one-line instruction pointer ("before your first code change, skim
  `process/codebase-map.md` to localize; ignore if unhelpful"). Works with zero hooks, any harness.

Constraints on the entries: maintainer-only (excluded from adopter vendoring, like the old wiring);
**must not depend on Claude Code MEMORY; must not require a human to run a script.**

## 4. Behavior contract (binding)

1. At session start, or on the first coding task, the agent auto-loads the map index.
2. It selects the relevant sections from the task.
3. It uses `git diff <map_checkpoint>..HEAD` to decide which sections need re-verification.
4. It outputs a compact briefing + suggested read paths (never a full-map dump).
5. If the map is untrustworthy, the task is unmappable, or the diff is large → **fall back to
   normal code search / widen the read scope.**
6. **Any failure of any part of this must not block** Edit, Write, Bash, commit, subagent spawn,
   worktree, or cross-repo work. Degraded = silently skip the aid and proceed.

## 5. Hard prohibitions — will NOT be (re)introduced

- PreToolUse enforcement gate.
- Receipts / epoch lock.
- Authorized-mutation ledger.
- Locking the session after HEAD moves.
- Out-of-repo / cross-repo write restrictions.
- Subagent / CLI-agent commit restrictions.
- Human-re-prompt unlock mechanism.

Meta-rule: there is **no failure mode that denies a tool call.** The aid is allowed to be absent,
stale, or wrong; it is never allowed to stop work.

## 6. Priority ordering (binding, in this order)

1. **Complete the user's task.**
2. **Keep the agent loop autonomous and continuous.**
3. Reduce repeated scanning / token spend.

Context optimization must never come at the cost of task-completion rate or workflow flexibility.
When (3) conflicts with (1) or (2), (3) loses.

## 7. Freshness — surfaced, not enforced

`map_checkpoint` + `git diff` shows *how stale* the map is; nothing acts on it. Refreshing the map
is an ordinary doc edit: re-verify references (read-only), bump `map_checkpoint`, commit. There is
no validator gate, no two-commit ceremony, and no DIRTY/UNMAPPED state that can block anything.

## 8. Projected savings, boundaries, non-goals

**Projected savings (hypothesis, unmeasured).** Per fresh session: a compact briefing costs
~0.5–1K tokens and is meant to displace open-ended re-orientation (skimming a dozen+ files to
rebuild structure in a ~30K-line framework — plausibly tens of K tokens of tool I/O). Net win
*only* when it displaces more scanning than it costs, so the briefing stays compact and full
sections are read on demand. A Phase-0 A/B measurement (map-primed vs cold) would confirm the real
number before any implementation is justified.

**Applicability boundary.** Single maintainer repo (aidazi), one working tree, one HEAD. The map is
per-repo and checkpoint-anchored. It is explicitly **not** a vehicle for multi-repo / cross-repo
scanning or updates — that is a different problem and out of scope here.

**Non-goals (explicit).** Not a correctness gate; not a security boundary; not an edit/commit
authority; does not constrain subagents, CLI agents, worktrees, or cross-repo work; not
adopter-facing (maintainer-only; excluded from vendoring).

## 9. Status & next step

This document + the migrated map are the entire deliverable for this cycle. Next: **one Codex
read-only review** of (a) this design and (b) the migrated `process/codebase-map.md`, then report
the projected token/scan benefit, the applicability boundary, and the non-goals. **Do not implement
the thin entries yet** — implementation is a separate, later decision, taken only if the read-only
value is judged worth the (thin) infrastructure.
