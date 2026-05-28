---
title: Runtime invariants (Tier-0 registry)
doc_tier: current-runtime
status: current
implementation_status: not_started
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: every 3-5 milestones
notes: >
  The project's Tier-0 invariant registry. Required by
  `framework/governance/constitution.md` §4.1 Q2 (Tier-0 justification)
  and §3.2 Q2 (Tier-0 routing). Fill during M0.
---

# Runtime invariants

## What is Tier-0?

Per `framework/governance/constitution.md` §1.4, a Tier-0 invariant
is a hard floor the **Runtime guarantees regardless of LLM choice**.
It is NOT a soft signal. The LLM cannot override it.

Common Tier-0 categories:

- **Safety floor** — no PII leaks; no actions that bypass user
  consent.
- **Grounding floor** — no factual claims without retrieval evidence
  (for retrieval-grounded agents).
- **Capability boundary** — agent never invokes a tool not in its
  whitelist.
- **Persistence floor** — session state survives restart.

A new Tier-0 invariant requires `human_review_required` per §3.2 —
the human decides whether to register a new Tier-0.

## §1. Active Tier-0 invariants

### 1.1 `<invariant-name-1>`

- **Statement**: <one sentence>
- **Why Tier-0**: <why this is hard floor; what fails if the runtime
  doesn't enforce>
- **How enforced**: <code path or mechanism that guarantees this;
  cite file:line>
- **Detection mechanism**: <how a violation is detected in trace /
  test / eval; cite file:line>
- **Sprint where this Tier-0 was introduced**: <sprint id>

### 1.2 `<invariant-name-2>`

(same shape)

(Add more sub-sections as Tier-0 invariants accumulate.)

## §2. Tier-0 candidates under review

Invariants that have been proposed but not yet ratified. Per §3.2,
adding a new Tier-0 requires `human_review_required` exit.

### `<candidate-name>`

- **Statement**: <one sentence>
- **Surfaced by**: <sprint id / failure brief id>
- **Status**: under review
- **Decision target**: <milestone id where decision is expected>

## §3. Retired Tier-0 invariants (history)

Invariants that were once Tier-0 but have been downgraded (e.g.,
because the structural source of failure was removed).

### `<retired-name>`

- **Original statement**: <one sentence>
- **Active period**: <sprint X to sprint Y>
- **Reason for retirement**: <why downgrade is safe>
- **Replaced by** (if applicable): <new mechanism>
