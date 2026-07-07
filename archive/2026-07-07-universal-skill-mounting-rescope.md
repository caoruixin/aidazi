---
title: "Universal skill mounting — 2026-07-07 rescope: core = deployed → selected → injected; consumption observability + Phase-5 canary withdrawn"
doc_tier: archive
doc_category: decision-record
status: recorded
date: 2026-07-07
scope: supersedes the withdrawn portions of archive/2026-07-06-universal-skill-mounting-design.md (§3/D2 consumption observability, §4 row 5, §5 phases 2/5, §7 pre-registration, §9 states 4-5)
---

# Rescope record — universal skill mounting

**Human decision (2026-07-07).** The initiative's delivery guarantee is narrowed to the
core chain — **deployed → selected → injected** — with deterministic BEST-EFFORT
selection ("usually reasonable, automatically loaded"), not proof of unique-optimal
selection, not proof of real agent reads, not fixture-scoped efficacy measurement.

## What was cancelled and why

The **Phase-5 real/billable canary** (α authoring calibration / β read-consumption /
γ paired A/B efficacy, with frozen pre-registration, deterministic scorers, spawn
budgets and replacement accounting) was cancelled by the human because these proofs
are **no longer delivery conditions for this round**. For the honest historical
record before cancellation: probe α ended **INCONCLUSIVE** under its own frozen abort
rule (3 adapter-level errors: two from a since-fixed harness defect — unwired scratch
adopters missing the documented root AGENTS.md/CLAUDE.md onboarding — and one from
model output-channel variance after the fix); β and γ were never run and consumed no
budget. One real framework finding from those spawns is retained as a follow-up:
*the inline guided-decompose contract lacks the explicit "return ONE JSON object as
the final message" emission line that the projected review/close contracts carry, and
under the deliver role's read-only sandbox the model's fallback presentation is
nondeterministically parseable.* No canary result claims anything about skill
mounting efficacy — the experiments were withdrawn, not failed on the merits.

The **consumption/read-observability layer** (Phase 2: the `SpawnResult`/
`InvocationTelemetry` adapter envelope, claude_code stream-json Read parsing,
`skill_reads`/`skill_consumption`/`skill_consumption_reason` audit fields, raw-stream
persistence, retry/concurrency/resume non-contamination proofs, and the preflight's
informational read-telemetry row) was **reverted**: whether an agent actually reads a
mounted SKILL.md, and whether it improves output, no longer blocks delivery and is
never taken from agent self-report. `SpawnResult` was introduced by this branch only
(nothing on `main` used it), so the reversal restores `main`'s adapter contract
byte-identically.

## What ships (the retained core)

1. **Signed signal sources**: charter mission profile
   (`autonomy.approved_scope.task_signals`), campaign `milestone_signals`
   (signoff-digest-bound, freshness-guarded), sub-sprint `task_signals`
   (decompose-authored, digest-guarded against post-sign mutation).
2. **Most-specific-wins**: a sub-sprint plan entry governs exclusively (including
   the signed omission); otherwise the derived charter tier (mission ∪ milestone);
   otherwise role defaults. All loop modes (`delivery_only`, `full_chain_guided`)
   and all eligible non-Acceptance roles. Acceptance remains excluded from dynamic
   selection (§3.6 calibration untouched).
3. **Deterministic best-effort selection with a fixed cap**: role defaults always
   load; signal-matched, role/harness-compatible catalog skills append in sorted
   order up to `MAX_SIGNAL_SELECTED_SKILLS`; overflow/incompatible/unresolvable
   candidates are NON-SILENT skips (audit + prompt footer); no-match and unknown
   signals surface as warnings and never halt a loop; no human checkpoint exists
   anywhere in the selection path.
4. **Prompt injection**: the resolved SKILL.md paths + hashes are injected into the
   role prompt (`skill_prompt_block`); `input_hash` covers the injected bytes;
   signal-free flows remain byte-identical to pre-initiative prompts (golden-guarded).
5. **Audit**: the `effective_role_config` event records selected skill ids, content
   hashes, `skill_set_hash`, `task_unit_id`, `task_signals`, `signal_source`
   (subsprint | charter_scope | none), skips and unmatched signals.
6. **Integrity preflight** (`skills_preflight.py` + run_loop real-run gates + CLI):
   lock/tree verification, required-skill resolvability, submodule gitlink drift
   (HALT with audited override), advisory pin freshness. Signal-free legacy adopters
   are unaffected.
7. **Vendored scratch-adopter offline proof** (`test_vendored_adopter_proof.py`):
   a real `vendor-framework.sh` adopter, subprocesses importing the vendored
   engine-kit, states deployed/selected/injected asserted byte-level, plus the
   negative arms (byte-identical no-signals, out-of-vocab schema-invalid, tampered
   lock, gitlink drift + override, post-sign mutation ⇒ stale).

## Historical documents

`archive/2026-07-06-universal-skill-mounting-design.md` and
`archive/2026-07-06-universal-skill-mounting-p2-handoff.md` remain as the historical
record of the original five-state design and its phase gates (P0-P4b each Codex
gpt-5.5 xhigh APPROVE). The pre-registration artifacts, canary harness, live-run
evidence and the withdrawn Phase-2 implementation were removed from the tree by the
rescope commits; their content and gate history are recoverable from git history on
this branch.
