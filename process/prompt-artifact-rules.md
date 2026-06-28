---
title: Prompt artifact rules — self-containment invariant
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-19
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 10KB
split_trigger: if §3 embed-vs-reference rules grow past 4KB, move detail to docs/prompt-embed-reference-rules.md
notes: >
  Promoted from csagent docs/current/process/prompt-artifact-rules.md (csagent §9)
  per v4 build plan. v4 framing: references Constitution §1.4-i + Δ-5 instead of
  csagent §-internal numbers. Defines the self-containment invariant for compact
  prompt artifacts (compact/sprint-NNN-dev-prompt.md, compact/M<N>-review-prompt.md,
  compact/M<N>-acceptance-prompt.md). This is the operationalization of
  Constitution §1.4-i; orchestrator preflight (process/delivery-loop.md §4.2.4)
  rejects prompts that declare self_contained: false.
---

# Prompt artifact rules

This doc codifies the **self-containment invariant** for prompt files the Deliver Agent produces for Dev / Code Reviewer / Acceptance sessions. The invariant exists so a fresh explicit role session can be started by pasting (or orchestrator-spawning) a single prompt file into a new session, without that session having to read further repo docs beyond its role-session governance chain.

This is the operationalization of Constitution §1.4-i (context-passing efficiency) and Δ-5.

## §1 The invariant

A **prompt artifact** (one of: `compact/sprint-NNN-dev-prompt.md`, `compact/M<N>-review-prompt.md`, `compact/M<N>-acceptance-prompt.md`, `compact/sprint-NNN-codex-rebuttal.md`) is a **self-contained executable view** of its source-of-truth contract:

- Dev prompt source-of-truth = `docs/sprint_objective.md`.
- Review prompt source-of-truth = `docs/milestone_objective.md` + per-sub-sprint objective archives + per-sub-sprint Dev handoffs.
- Acceptance prompt source-of-truth = the closure_contract in `docs/research-briefs/<id>.md` + F5 evidence path.

**Self-contained** means: a fresh explicit role session, given ONLY this prompt file (plus the role-session governance chain loaded per `governance/context_briefing.md` §1.2), has every piece of information it needs to:

- Understand its role and the bounded scope of the session.
- Execute the contract end-to-end (write code / run tests / author handoff for Dev; walk anti-hardcode kernel + verify scope discipline + produce `docs/codex-findings.md` for Code Reviewer; judge against closure_contract + produce JSON verdict for Acceptance).
- Self-check that the work is complete before claiming so.

The prompt MUST embed (not reference) all contract content. The single exception is artifacts the prompt's consumer is expected to produce (e.g., per-sub-sprint Dev handoff is consumed by Code Reviewer but produced by Dev; Review prompt references handoff paths but cannot embed handoff content because it does not yet exist at prompt-authoring time).

### §1.1 Front-matter enforcement

Every prompt artifact declares in front-matter (per Constitution §1.4-i):

```yaml
context_budget:
  target_tokens: <number>
  load_list: [<paths-the-role-must-load>]
  do_not_load: [<paths-explicitly-excluded>]
  self_contained: true
```

If `self_contained: false`, the orchestrator preflight (`process/delivery-loop.md` §4.2.4 `dev_pending` and equivalent states) REJECTS the prompt and emits `gate_hard_fail` MANDATORY_CHECKPOINT. In manual / human-paste mode, the human reviewer SHOULD do the same.

## §2 Embed vs reference rules

| Content | Embed in prompt | Reference only |
|---|---|---|
| Role identity, goal, scope, hard fences, test/eval requirements, sprint stanza, handoff requirements, commit discipline | ✓ | |
| 9-question anti-hardcode kernel (in Review prompt) | ✓ | |
| Sub-sprint cumulative scope claim (in Review prompt) | ✓ | |
| closure_contract (in Acceptance prompt) | ✓ (or referenced by path with the brief auto-loaded via `load_list`) | |
| Governance kernel trio (constitution-core, authoring-kernel, context_briefing; full constitution / doc_governance on-demand) | — | Via explicit role-session cold-start (`context_briefing.md` §1.2) |
| Per-sub-sprint Dev handoff (in Review prompt) | — | Path reference only (Dev produces these AFTER prompt is authored) |
| Code anchors (specific file:line references) | — | Path reference (role reads them on demand during work) |
| Research Agent proposals in `docs/proposals/` | — | Reference if needed; do NOT embed (proposal-tier; may be out of date relative to milestone decisions) |
| F5 evidence artifact paths (in Acceptance prompt) | — | Path reference (orchestrator runs the eval cmd; artifacts exist before Acceptance reads) |

## §3 Source-of-truth synchronization

`docs/sprint_objective.md` is the canonical sub-sprint contract that Customer (or Deliver + human) reviews and approves. `compact/sprint-NNN-dev-prompt.md` is its self-contained executable view. Same relationship holds between `docs/milestone_objective.md` and `compact/M<N>-review-prompt.md`, and between `docs/research-briefs/<id>.md` and `compact/M<N>-acceptance-prompt.md`.

### §3.1 Synchronization rules

1. **One-pass generation** — Deliver Agent generates `objective.md` and `prompt.md` in one pass (objective first, then prompt as embedded view). Both surfaced for human review together.
2. **Modification cascade** — if human modifies `objective.md` during review, Deliver Agent regenerates `prompt.md` from modified objective before dispatch.
3. **Mid-sub-sprint changes** — if contract changes (e.g., scope adjustment via STOP-and-surface or in-flight downgrade), both `objective.md` and `prompt.md` updated together; cadence is "objective first, prompt regenerated."
4. **At close** — Deliver archives `objective.md` to `docs/sprints/<sprint-id>/`. `prompt.md` stays in place as historical executable view; NOT re-archived elsewhere unless Deliver explicitly compresses `compact/` at future milestone close.
5. **closure_contract immutability** — Constitution §3.4 invariant #4: closure_contract in `docs/research-briefs/<id>.md` MUST NOT change between gate 1 sign-off and Acceptance run without Customer re-sign-off. The Acceptance prompt's embedded or referenced closure_contract MUST be the gate-1-signed version.

## §4 Exemptions

The self-containment invariant is **not required** for:

- Research Agent's `docs/research-briefs/<id>.md` artifact — human-facing brief, not agent-execution prompt. (The Acceptance prompt that CONSUMES the brief IS subject to the invariant.)
- Activation paste-prompts (when used) — intentionally minimal; point to full role card for definition.
- Cross-session continuity scaffolding in `docs/handoff.md` — structurally session-handoff log, not executable prompt.
- `docs/checkpoints/*.md` files — orchestrator-emitted; not prompts.

## §5 Backwards compatibility (adopter-side)

Pre-v4-adoption prompts in an adopter's history may have been authored under older reference-based convention. They remain in archived form. The self-containment invariant applies prospectively from next sub-sprint / milestone / acceptance round after adoption.

If a future fold-back pass discovers a historical prompt that violates this invariant in a way that would impair re-running, Deliver Agent SHALL note the issue in sprint archive but SHALL NOT retroactively edit the archived prompt (per `governance/doc_governance.md` "Sprint archives never edited" rule).

## §6 Orchestrator readiness

This invariant is a prerequisite for orchestrator-driven dispatch (`process/delivery-loop.md` §4.2.4): a state-machine driver spawning Dev / Code Reviewer / Acceptance sessions needs self-contained prompt artifacts so each spawned session is a deterministic executable unit.

The §3 synchronization rule ensures the orchestrator can rely on `prompt.md` being authoritative without needing to cross-check `objective.md` at session-spawn time.

A future framework version MAY evolve this into a richer "session pack" concept (bundling prompt + context snapshots + bad case fixtures into a single archivable directory). The invariant as authored here is the minimum; the session-pack evolution is additive on top.

### §6.1 Authored prompt artifact vs. as-dispatched transcript

Two distinct things, often conflated by adopters (it was the conflation behind the bp-review-team audit gap):

- **Authored prompt artifact** (`compact/sprint-NNN-dev-prompt.md`, `compact/M<N>-review-prompt.md`, `compact/M<N>-acceptance-prompt.md`) — the **durable, human-reviewed source view** subject to the §1 self-containment invariant. Authored by Deliver, surfaced for human review, committed.
- **As-dispatched transcript** (`.orchestrator/audit/transcripts/<loop_id>/NNNN__<role>__{prompt,output}.{md,json}`) — the **execution record** the orchestrator writes for EVERY spawn (Dev / Code Reviewer / Deliver / Research / Acceptance, and each fix-round): the exact prompt bytes sent (always) and the captured model output (whenever the adapter returns one — a transport error records `output_ref: null`), referenced from the Audit Spine spawn event as `prompt_ref` / `output_ref` (`process/delivery-loop.md` §4.2.10). Per-adopter, gitignored with the rest of `.orchestrator/`.

The authored artifact answers "what did we *intend* to ask, and did a human approve it?"; the transcript answers "what was *actually* dispatched and what came back?" — the latter is what makes an upgrade run auditable and trackable spawn-by-spawn.

### §6.2 Engine resolution of the Dev / Review / Acceptance prompts (strict mode)

In **strict mode**, the orchestrator does NOT dispatch a one-line role request for Dev, Code Reviewer, or Acceptance. Each resolves a **self-contained** prompt by content, in order, and **HALTs** (resumable refinement checkpoint — `STATE_HALTED` plus a persisted `halt_resume_state` so a re-run re-enters the paused state and re-resolves) rather than spawning a thin prompt when the source is missing/incomplete.

**Strict mode** is the union of two independent enablers, so a real model can never receive a thin prompt: an explicit `context.allow_real` flag, **OR** the presence of any non-mock adapter (a real `claude_code`/`codex`/`headless`/`kimi` backend is wired). An all-mock wiring without `allow_real` is the offline/test path and keeps the legacy inline prompt (byte-identical).

| Role | Resolution order | Derived from |
|---|---|---|
| Dev | decompose-plan entry (canonical) → adopter `compact/<id>-dev-prompt.md` → HALT | the signed sub-sprint spec (objective + scope_in + exit_criteria) |
| Code Reviewer | adopter `compact/<id>-review-prompt.md` → project from the resolved sub-sprint spec → HALT | sub-sprint objective/scope/exit-criteria + Dev handoff/diff (referenced) + anti-hardcode kernel + severity rules + `review-verdict` schema |
| Acceptance | adopter `compact/<scope>-acceptance-prompt.md` → project from the **signed** `intent_contract` → HALT | Customer need (`goal`) + acceptance criteria (`standard` + `proof_of_done`) + closure_contract/brief ref + F5 evidence ref + Reviewer-outcome refs + calibration/authority + `acceptance-verdict` schema |

The projections are **deterministic** and reference stable evidence (the concrete Dev change-summary transcript, handoff doc, and `eval/runs/` paths) rather than copying raw transcripts. They are **distinct contracts** — there is no generic role projector: the Review prompt is sub-sprint-scoped, the Acceptance prompt is milestone-scoped and gated **first** on a **human-signed** `intent_contract` (Constitution §3.4 invariant #4) — a hard gate an adopter `compact/` prompt can NOT bypass. Acceptance projection only **reports** calibration/authority (it runs after the §3.6 gate); it never alters them — and a change to the Acceptance prompt/binding/schema still reopens calibration where §3.6 applies. When no research brief is bound, the Acceptance prompt embeds the signed `proof_of_done` as the closure criterion (it never fabricates a brief path). The resolved prompt is materialized through the per-spawn transcript path (§6.1) like any other.

## §7 Auto Loop interaction

The Auto Loop (Concept 1; `modules/m-autoloop.md`) — a Type A agent's runtime self-improvement — operates DOWNSTREAM of prompt artifacts: Auto Loop iterations may modify the agent's prompts at runtime, but the framework-level prompt artifacts (Dev / Review / Acceptance) covered by this doc are NOT Auto Loop targets. The two layers do not collide.

Confusing the two would be a §1.7-E violation (Auto Loop ↔ Delivery Loop conflation). See `docs/two-loops-explainer.md`.

## §8 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The embed-vs-reference table (§2) is load-bearing — adding or removing rows requires fold-back deliberation. Suggested-default values like `target_tokens` numerical guidance live in `process/self-governance.md` §7.5, not here.

---

End of Prompt artifact rules.
