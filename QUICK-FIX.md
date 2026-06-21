# Quick-Fix lane — adopter guide

A **human-explicit, per-session, loop-independent** maintenance lane for small,
**non-behavioral** fixes that do not warrant the full governance chain. It lets a human make
a quick fix without paying the full cold-start governance context — while still honoring the
one constraint a quick fix can realistically breach (semantic hardcode, Constitution §1.7).

> Normative spec: **`process/quickfix-lane.md`** (this guide is the how-to; the spec wins on
> any conflict). The lane is **additive** — a session that does not go through the Quick-Fix
> launcher is, byte-for-byte, a normal Full session.

## When it applies (and when it does NOT)

A Quick Fix is permitted only when ALL hold (the agent never decides this for you — §2/§3):

1. a human **explicitly** ran the launcher (vague "just tidy this up" is never activation);
2. the change is **non-behavioral** or restores an already-agreed behavior;
3. it introduces **no** new product semantics, architecture, or policy/strategy decision;
4. it does not shift the **LLM-vs-runtime** ownership boundary (Constitution §1.7);
5. it touches **no protected surface** (`governance/quickfix-protected-surfaces.policy.yaml`);
6. it has a **targeted, local, repeatable** verification;
7. the edits stay **within the human-approved scope** (`allowed_globs`).

If any cannot be proven, the lane **escalates** — it preserves the investigation and tells
you to relaunch in **Full** framework mode. It is **NOT** a loop and **never** skips
MANDATORY_CHECKPOINTS (it runs entirely outside the Delivery/Campaign Loop).

## Harness support (strict, evidence-gated)

The launcher **fails closed** for any harness not marked `supported` — there is no silent
degradation onto an unproven harness. Tiers live in
`engine-kit/quickfix/harness_support.yaml`:

| Harness | Status | Notes |
|---|---|---|
| **Claude Code** (`claude_code`) | **`supported`** | Adapter + recorded real-launch cold-start evidence (`archive/2026-06-22-quickfix-claude-code-e2e-evidence.md`). cwd = out-of-tree bundle; `--add-dir` grants the worktree file access without loading its `CLAUDE.md`. |
| **Codex** (`codex`) | `experimental` | Adapter delivered; isolation achievable (`-C` out-of-tree root + `--skip-git-repo-check` keeps AGENTS.md discovery cwd-only, + `--add-dir` worktree). **Not launchable** until a real-launch proof is recorded. |
| **Kimi Code** (`kimi_code`) | `unsupported` | Kimi merges `AGENTS.md` root→cwd but has no `-C`/`--add-dir`, so its cwd is both the memory-load root and the only writable dir — cold-start isolation is not achievable. **Not launchable.** |

> **Correctly-wired-adopter caveat (Claude Code).** The `supported` claim is scoped to the
> **Quick-Fix** cold-start (the bundle ships a `CLAUDE.md`, which Claude Code auto-loads). It
> does **not** assert the Claude Code *Full* baseline — that is gated on the open R1 follow-up
> (`archive/2026-06-21-followup-claude-code-agentsmd-baseline.md`).

## How to run it

1. Write a `quickfix-request.json` (schema: `schemas/quickfix-request.schema.json`; see
   `examples/quickfix/request.example.json` and `templates/quickfix-request.example.json`).
   Key fields: `request_id`, `harness`, `task_summary`, `allowed_globs` (the enforced scope),
   `targeted_verification.argv`, and the human `eligibility_attestation`.
2. Run the launcher from the framework root (requires a **clean working tree**):

   ```bash
   tools/quickfix-launch.sh --request /path/to/quickfix-request.json --repo-dir .
   # or directly:
   PYTHONPATH=engine-kit python3 -m quickfix --request … --repo-dir … [--framework-root …]
   ```

   Stable exit codes: `0` completed · `2` invalid request · `3` dirty tree · `10` escalated ·
   `11` unsupported/experimental harness (or a missing/old harness CLI).

## What it does (closure flow)

All edits happen in an **ephemeral git worktree** outside your working area, and the harness
runs in an **out-of-tree bundle** so its cold-start never reaches your repo's governance
chain. The lane then runs: **preliminary guard → the harness edit (scope-bounded) → targeted
verification → final guard**. On success it creates a result commit on a dedicated
**`quickfix/<request_id>`** branch and stops — the result is **never auto-applied**; you
decide whether to cherry-pick. Launch evidence + an append-only record land under
`.orchestrator/quickfix/` (gitignored). On any escalation it preserves the patch + a handoff
**before** teardown, so completed investigation is never lost.

## Try it

`examples/quickfix/e2e-claude-code.sh` is a runnable, self-contained demonstration (and the
reproducible evidence behind the `claude_code` `supported` status). It stands up a throwaway
adopter repo, runs the real lane, and checks all 16 acceptance criteria — including that a
canary in the adopter's root `CLAUDE.md`/`AGENTS.md` never enters the Quick-Fix cold-start.
