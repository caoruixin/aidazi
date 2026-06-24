---
title: Quick-Fix lane — human-explicit, loop-independent maintenance lane
doc_tier: process
doc_category: live
status: current
implementation_status: partial
source_of_truth: this file
created: 2026-06-21
last_reviewed: 2026-06-22
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 14KB
notes: >
  Canonical specification of the Quick-Fix lane: a human-explicit, per-session,
  non-inheritable maintenance lane that runs OUTSIDE the Delivery/Campaign Loop. It is
  NOT a loop and NOT a way to skip MANDATORY_CHECKPOINTS. Naming discipline
  (Constitution §1.7-E): distinct from Onboarding Wizard, Loop Ingress, Loop Controller,
  Auto Loop, Delivery Loop, Campaign Loop, Loop Memory. This file is the normative source;
  engine-kit/quickfix/* is its implementation (spec wins on conflict). It REFERENCES, and
  never restates, Constitution §1.7/§1.8 and templates/anti-hardcode-review-kernel.md.
---

# Quick-Fix lane

> **STATUS — Commit 3 of 3 (usable on Claude Code + Codex).** The spec, schemas,
> protected-surface policy, runtime, AND the per-harness adapter layer
> (`engine-kit/quickfix/adapters/`) have landed. `claude_code`
> (`archive/2026-06-22-quickfix-claude-code-e2e-evidence.md`) and `codex`
> (`archive/2026-06-22-quickfix-codex-e2e-evidence.md`, codex 0.134.0) are both **`supported`**
> — delivered adapters with recorded real-launch cold-start evidence for a correctly-wired
> adopter. `kimi_code` is **`unsupported`**; the launch gate stays strict (only `supported`
> runs), so every other harness still **fails closed**. See `QUICK-FIX.md` for adopter usage.

## §1 What it is (and what it is NOT)

The Quick-Fix lane is a **human-explicit, per-session, non-inheritable maintenance lane**
for small, non-behavioral fixes that do not warrant the full governance chain. It exists
so a human can make a quick fix **without** paying the full cold-start governance context,
while still honoring the one constraint a quick fix can realistically breach (semantic
hardcode — Constitution §1.7).

It is **NOT**:

- **NOT a loop.** It runs entirely outside the Delivery Loop and the Campaign Loop. It
  has no Loop Ingress, no Loop Controller, no checkpoints, no Acceptance. Naming
  discipline (Constitution §1.7-E): keep it distinct from every "*Loop*" concept.
- **NOT a way to skip MANDATORY_CHECKPOINTS.** Once you are in the Delivery/Campaign
  Loop, the 9 checkpoints are non-bypassable regardless of change size (Constitution
  §1.7-D). The Quick-Fix lane never enters the loop, so there is nothing to skip — and
  it may never be used to route loop-bound work around the checkpoints.
- **NOT charter-activated.** It does not use the mission charter as its activation
  mechanism (there is no `charter.quickfix`). Activation is an action — see §2.

## §2 Default Control Plane · activation · no self-downgrade

**Default is the Control Plane.** Absent an explicit human Quick-Fix activation, behavior is the
unchanged framework default: the standard root memory file (`AGENTS.md`/`CLAUDE.md`/
`.cursor/rules`) routes natural-language work through the Control Plane Session and the normal
5-role / Delivery / Campaign paths. It must never self-downgrade into Quick-Fix.

**Activation is a human ACTION, not a file field.** The lane is activated only when a
human **explicitly runs the Quick-Fix launcher**, or **explicitly instructs the current
session to run it**. The `quickfix-request.json` (`schemas/quickfix-request.schema.json`)
carries the task, the machine-verifiable scope, and human attestations — but its
`human_activation: true` is an **attestation only**. It is not unforgeable and it does
**not** prove activation. Vague natural language ("just tidy this up", "quick fix while
you're in here") is **never** an activation.

**The agent never self-downgrades.** An agent may not move from Full to the Quick-Fix
lane on its own judgment that "this looks small."

**No in-place degrade (constraint).** When a human asks for a Quick Fix from inside an
existing default or role session, that session's **only** permitted action is to invoke
the launcher's `prepare` step to start a **new, isolated** Quick-Fix session — it must
**not** degrade in place and perform the fix itself. The already-loaded cold-start
context cannot be reclaimed, so the current session hands off and stops; the fix runs in
the fresh isolated session. (This is a governance + audit rule, like the role
boundaries — not a sandbox; an already-running agent is trusted to honor it.)

## §3 Eligibility triage — two layers, semantic not size-based

Eligibility is judged by **semantic and contract risk, never by line count or single-file
heuristics.** A Quick Fix is permitted only when ALL hold:

1. the human explicitly chose the Quick-Fix lane (§2);
2. the change is purely **non-behavioral**, or restores an already-agreed existing
   behavior;
3. it introduces **no new product semantics, architecture, or policy/strategy decision**;
4. it does not shift the **LLM-vs-runtime ownership boundary** (Constitution §1.7);
5. it touches **no protected surface** (§4);
6. it has a **targeted, local, repeatable verification** (§7);
7. the actual edits stay **within the human-approved scope** (`allowed_globs`, §6).

If any condition cannot be **proven**, or an unknown semantic / a new design choice
appears, the lane **escalates** (§5, §11) — uncertainty is never resolved by proceeding.

**Two-layer enforcement:**

- **Layer A (primary, soft):** human attestation (§2) + the agent's own judgment against
  the **anti-hardcode kernel** (`templates/anti-hardcode-review-kernel.md`) and this
  protocol. This is where eligibility is actually decided.
- **Layer B (backstop, hard):** the deterministic guard (§8) over the policy globs (§4).
  A clean Layer-B pass is **necessary but NOT sufficient** — it cannot prove semantic
  legitimacy; it only catches path-visible protected-surface and out-of-scope edits.

**Minimal context.** A Quick-Fix session's governing context is the **anti-hardcode
kernel together with this document** — neither alone is a complete "universal kernel".
The kernel supplies the §1.7 anti-hardcode lens; this doc supplies the lane protocol,
the protected-surface reference, and the escalation rules.

## §4 Protected surfaces

The framework-mandatory protected surfaces are defined **once**, machine-readably, in
`governance/quickfix-protected-surfaces.policy.yaml` (validated by
`schemas/quickfix-protected-surfaces.schema.json`). This document does **not** restate
them. The guard loads that policy (baseline) unioned with an optional adopter overlay
(`docs/current/quickfix-protected-surfaces.overlay.yaml`). The overlay is validated
against a **separate** schema (`schemas/quickfix-protected-surfaces.overlay.schema.json`)
that permits `additional_surfaces` **only** and forbids `mandatory_surfaces` — so an
overlay can extend but never subtract or weaken, and a mis-authored overlay is **rejected
(fail-closed), not silently ignored** (mirrors Constitution §1.8). Glob matching is
gitignore-style with `**/` matching at any depth (the guard must implement this; §8), over
a safe glob subset (no character classes / brace expansion / negation, so a glob cannot
encode traversal or an absolute path).

Surfaces that cannot be expressed as globs — new product semantics, architecture/policy
choices, LLM-vs-runtime ownership shifts — are listed under `semantic_surfaces_layer_a`
in the policy and are enforced at **Layer A** (§3). Glob matching is intentionally
over-inclusive: an ambiguous match **escalates** rather than proceeds.

## §5 Closure flow

All edits happen in an **ephemeral git worktree** outside the adopter's working area
(§8); the adopter's current workspace is never touched. The lane requires a **clean
working tree at launch** (dirty ⇒ fail closed). The closure sequence is:

1. **Preliminary guard** — before substantive work, confirm the baseline is clean and
   the scope/policy load is valid.
2. **Edits** in the worktree, within `allowed_globs`.
3. **Targeted verification** (§7) — structured `argv`, `shell=False`, bounded cwd.
4. **Final guard** (§8) — re-run AFTER verification over the full change set.
5. On success: create a **result commit on a dedicated `quickfix/<request_id>` branch**
   and return the **commit SHA**, the `--stat`, and the verification result. The result
   is **never auto-applied** to the adopter's current branch — the **human decides
   whether to cherry-pick**.
6. On escalation (any step): **save the patch, a diff summary, and the escalation
   handoff FIRST** (outside the worktree), **then** tear down the worktree. Completed
   investigation is never lost to teardown. The handoff instructs the human to relaunch
   **Full** (`templates/quickfix-escalation-handoff.md`).

## §6 `allowed_globs` semantics

`allowed_globs` (in the request) is the human-approved scope and the enforced gate:

- **repo-relative POSIX paths only;** absolute paths, `~`, `..` segments, and negation
  patterns are forbidden (schema-rejected and re-checked by the guard);
- the guard enforces that **every touched path matches at least one glob** — and for a
  **rename, BOTH the source and the destination** path must be in scope;
- a boolean attestation like `within_approved_scope: true` is **not** sufficient on its
  own; the glob subset check is the machine enforcement;
- an adopter overlay may only add `additional_globs`-style surfaces (§4); it may not
  remove, exclude, or override.

## §7 Targeted verification

The request's `targeted_verification` is a structured `{ argv, cwd }`:

- executed with **`shell=False`** (no shell string, no metacharacter interpretation) and
  a **bounded cwd** that must resolve **inside the worktree**;
- `argv[0]` is checked against an **executable allowlist**; a non-allowlisted executable
  requires **explicit extra human confirmation** before it runs;
- verification runs **between the preliminary and the final guard** (§5) — a green
  verification with a dirty final guard still fails closed.

## §8 Guard coverage

The guard binds to the **worktree HEAD SHA captured at launch** (the baseline) — it does
**not** rely on `base_ref..HEAD` alone. It enumerates the **full** change set against
that baseline and classifies each touched path:

- **staged, unstaged, and untracked** changes;
- **renames** — both the **old and the new** path are checked for scope (§6);
- **deletes** and **file-mode** changes;
- **symlinks** and **submodule/gitlink** changes — in v1 these are treated
  **conservatively as automatic escalation** (a symlink can redirect into a protected
  surface; a gitlink moves an external pointer).

Every touched path must be **within `allowed_globs`** AND **outside every protected
surface** (§4). Any violation ⇒ escalation.

## §9 Records

Each lane outcome appends one line to **`<repo>/.orchestrator/quickfix/records.jsonl`**
(`schemas/quickfix-record.schema.json`). This location is **gitignored** (`.orchestrator/`)
so it never dirties the tracked tree, and it lives in the main repo dir so it **survives**
ephemeral worktree/bundle teardown. The record is written under a **file lock**
(append-only protocol) and captures the **baseline SHA, outcome, and the result commit
SHA or preserved-patch hash**.

The record is an **append-only protocol for observability/audit, NOT a tamper-proof
ledger** (no hash chain). A record is **never** read as an activation credential for a
later session — activation is always a fresh human launcher invocation (§2).

## §10 Harness support is tiered

Policy and core are harness-agnostic; a harness's support is decided **per-adapter on
evidence**, in `engine-kit/quickfix/harness_support.yaml`, with three tiers:

- **`supported`** — a delivered adapter (`engine-kit/quickfix/adapters/<harness>.py`) AND
  recorded real-launch cold-start evidence. The launcher will run it.
- **`experimental`** — adapter delivered and cold-start isolation is achievable, but no
  recorded real-launch proof yet. NOT launchable.
- **`unsupported`** — no adapter, or the harness cannot satisfy cold-start isolation at all.
  NOT launchable.

The launch gate is **strict and never widens**: `assert_supported()` admits only
`supported`; `experimental`/`unsupported` both **fail closed** — no silent degradation onto
an unproven harness. `claude_code`
(`archive/2026-06-22-quickfix-claude-code-e2e-evidence.md`) and `codex`
(`archive/2026-06-22-quickfix-codex-e2e-evidence.md`, real-launch proof via an out-of-tree
`-C` root + `--skip-git-repo-check` + `--add-dir`) are both `supported`; `kimi_code` is
`unsupported` (no `-C`/`--add-dir`, so its cwd is both the memory-load root and the only
writable dir — the bundle cwd and the worktree edit target cannot be separated). The
per-harness adapter is the ONLY place that knows a harness's CLI
flags / memory filename; the launcher core stays harness-neutral.

## §11 Fail-closed summary

Two fail-closed gates:

- **Activation gate:** a missing / malformed / ambiguous request, a failed attestation,
  a dirty working tree, or an unsupported harness ⇒ the lane is **not entered**. It never
  silently falls back to a reduced-governance run, and it never silently runs as Full
  inside the (minimal-context) bundle — it refuses and tells the human to relaunch.
- **In-lane gate:** scope expansion, a protected-surface hit, a verification failure, an
  unknown semantic / new design choice, or any unprovable eligibility ⇒ **stop, preserve
  the investigation, emit the escalation handoff, and require the human to relaunch
  Full.**

## §12 No duplicated governance

The hard constraints a Quick Fix must honor have a **single canonical source**: the
§1.7 forbidden list (`governance/constitution.md` §1.7/§1.8) as operationalized by the
canonical **anti-hardcode kernel** (`templates/anti-hardcode-review-kernel.md`). This
document **references** them and must **never** copy the forbidden-list rules into a
second, drift-prone text. The protected-surface list likewise has one machine-readable
source (§4).

## §13 Relationship to the framework

The Quick-Fix lane is additive and loop-independent. It changes **nothing** about the
default Control Plane entry, the consumer `AGENTS.md` template, explicit role-session
governance loading, the MANDATORY_CHECKPOINTS, the Delivery/Campaign Loop, the Driver,
or Acceptance. A session that does not go through the Quick-Fix launcher follows the
normal Control Plane / role-session path.

---

End of Quick-Fix lane specification.
