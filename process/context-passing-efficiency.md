---
title: Context-passing efficiency (Δ-5)
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-07
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 8KB
notes: >
  Δ-5: sufficient AND efficient context-passing. v4 promotes this to
  Constitution §1.4-i; this Δ doc carries the operational detail (when each
  rule fires, examples of violations + correct shapes). Companion of
  process/prompt-artifact-rules.md (the self-containment invariant for
  compact prompt artifacts).
---

# Context-passing efficiency (Δ-5)

Constitution §1.4-i promotes this Δ from process-tier to a constitutional clause: every prompt artifact MUST be **sufficient** AND **efficient**. This doc carries the operational rules — when each rule fires, what violates each, and what the orchestrator preflight checks for.

## §1 The two properties

### §1.1 Sufficient

A prompt is **sufficient** when the receiving role session can do its job without chat-history backchannel or out-of-band help.

**Sufficient ≠ exhaustive**. The prompt does not need to embed every detail; it needs to embed everything the role needs to (a) understand its job, (b) execute the contract, (c) self-check.

The receiving role MAY load files named in the prompt's `load_list` — those files are part of the prompt's sufficient context. The prompt does NOT need to embed their contents.

### §1.2 Efficient

A prompt is **efficient** when it does NOT carry MORE context than necessary.

**Efficient ≠ minimal**. The prompt should include what's needed; it should NOT include adjacent-domain background, historical context the current sub-sprint doesn't touch, or "just in case" anti-pattern lists for failure modes this sub-sprint can't hit.

The tension between sufficient and efficient is real. Resolve in favor of sufficient when in doubt; efficient is an optimization on top of sufficient. A prompt that's slightly over-budget but sufficient is better than a tight prompt that requires the receiving role to ask Deliver "wait, what about X?"

## §2 The front-matter contract

Every compact prompt artifact declares:

```yaml
context_budget:
  target_tokens: <number>
  load_list: [<paths-the-role-must-load>]
  do_not_load: [<paths-explicitly-excluded>]
  self_contained: true
```

### §2.1 `target_tokens`

A suggested upper budget for the receiving session's context (prompt + load_list-loaded files + always-load governance chain). Adopters set per-prompt; suggested defaults per Constitution §7.0:

- Dev prompt: 8000-16000.
- Review prompt: 6000-10000.
- Acceptance prompt: 8000-12000.

The number is a SIGNAL, not a hard gate (Constitution §7.0). Significant overruns at runtime are a fold-back signal (the prompt may need restructuring or the template may need its suggested default raised).

### §2.2 `load_list`

Specific file paths the receiving role loads. Used by:

- The receiving role's cold-start (per `governance/context_briefing.md`).
- The orchestrator's preflight (does the prompt declare a tight, specific load_list?).
- The Code Reviewer's audit of self-containment (Constitution §1.4-i).

Glob patterns are discouraged; specific paths produce a deterministic check.

### §2.3 `do_not_load`

Paths explicitly excluded. Used to:

- Prevent eval contamination (Dev's `do_not_load` includes `case_specs_shadow/`).
- Prevent role-boundary breaches (Acceptance's `do_not_load` may exclude `docs/research-briefs/draft/*` if drafts are different from signed briefs).
- Document deliberate scope (Review's `do_not_load` may exclude entire modules out of scope for this sprint).

### §2.4 `self_contained: true`

Hard requirement (Constitution §1.4-i). If `self_contained: false`, the orchestrator preflight rejects the prompt (`process/delivery-loop.md` §4.2.4 `dev_pending`); the human reviewer in manual mode does the same.

There is no `self_contained: partial` or `self_contained: pending` value. Self-containment is binary.

## §3 Common violation shapes

### §3.1 Sufficient violations

- **Implicit chat-history dependency** — prompt assumes the session "remembers" something from the dispatching session (e.g., "as we discussed earlier"). Violates Constitution §3.4 invariant #1 + §1.4-i.
- **Missing closure_contract** — Acceptance prompt loads research-brief but does not embed OR reference the specific closure_contract clauses to judge against. Acceptance is left to "find them."
- **Vague load_list** — `load_list: [<adopter>/docs/**/*.md]` is not a load list; it's an instruction to load everything. The role can't deterministically know what to read.
- **No sub-sprint contract** — Dev prompt names the modules and tests but doesn't say what behavior the sub-sprint delivers. Dev has to infer.

### §3.2 Efficient violations

- **Adjacent-domain padding** — prompt embeds 5 pages of customer-service domain context when the sub-sprint is editing one prompt projection field. Most of the embedded context is unused.
- **Historical context** — prompt cites every related decision back to milestone M1. The current sub-sprint depends on the LAST two, not all of them.
- **Failure-mode catalog overload** — Review prompt embeds 20 anti-patterns to watch for; the sub-sprint touched 2 of them. Reviewer's attention diluted.
- **Mirroring governance** — prompt re-states Constitution §1.7 verbatim. Governance is always-load; the prompt should reference, not duplicate.

### §3.3 Both-properties violations

- **The "kitchen sink" prompt** — prompt embeds everything available; the session must spend its context budget on parsing the prompt before doing work. Sufficient + bloated. Common in early-adoption mode.
- **The "dispatch note" prompt** — prompt is 200 words: "fix the bug in module X." Efficient + insufficient. Receiver guesses scope; sub-sprint drifts.

## §4 Drafting discipline

When the Deliver Agent authors a compact prompt:

1. Start from the role's contract (sub-sprint objective for Dev; milestone objective for Review; closure_contract source for Acceptance).
2. Enumerate what the role needs to DECIDE in this session.
3. For each decision, name the input the role needs.
4. Add those inputs to either the embedded prompt body OR the load_list.
5. Cross-check: is every embedded paragraph used by at least one decision? If not, remove (efficient).
6. Cross-check: can the role make every decision with what's embedded + load_list? If not, add (sufficient).
7. Validate `self_contained: true` is honest.

This is iterative; first draft is rarely both sufficient and efficient.

## §5 Code Reviewer enforcement

The Code Reviewer's audit of compact prompts (`role-cards/code-reviewer-agent.md` §4 self-containment check) walks:

- Does the prompt declare `self_contained: true`?
- Is `load_list` specific (no glob spew)?
- Are inputs the prompt body references all in `load_list` OR auto-loaded (governance chain)?
- Are there embedded paragraphs that don't tie to a self-check rule in §11 of the eventual handoff?
- Is `target_tokens` realistic given the load_list contents?

A prompt that fails this audit gets a `fix_required` finding; Deliver re-authors before re-dispatch.

## §6 Interaction with Δ-9 OBS

Per Δ-9 (`process/post-deployment-iteration.md`): when a post-deployment failure traces to "the prompt didn't carry enough context," the failure is `prompt_projection` layer — NOT `infra`. Constitution §1.5 iteration rule applies: don't add a Java guard "to inject the missing context"; fix the prompt-projection.

The same layer-classification works for compact prompts in the framework's own development cycle: if Dev fails because the prompt was insufficient, the fix is to the prompt (Deliver re-authors). If Dev succeeds but the eval rules say the work was wrong, the failure may be `eval_spec` or `closure_contract` (Path 3) rather than prompt.

## §7 Cross-references

- Constitution §1.4-i — the canonical statement.
- `process/prompt-artifact-rules.md` — the self-containment invariant (§9 in csagent terms).
- `templates/compact-dev-prompt.md` + `templates/compact-review-prompt.md` + `templates/compact-acceptance-prompt.md` — the templates Deliver fills.
- `process/self-governance.md` §7.5 — the bloat metric (target_tokens not blown).
- `governance/context_briefing.md` §1 — cold-start load order.

## §8 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8. The two properties (sufficient + efficient) are stable framework vocabulary. Specific numerical budgets and `load_list` patterns are SUGGESTED per Constitution §7.0; adopters override with rationale.

---

End of Δ-5 Context-passing efficiency.
