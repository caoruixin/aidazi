---
title: Tech architecture decision catalog (Δ-3)
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
size_target: 12KB
notes: >
  Δ-3 EXTEND per v4-plan §4.1: 8 decisions catalog + decision #1's
  abstraction-layer sub-choice (default single tool-use per Constitution
  §1.7-A). Loaded by Deliver at Phase 3 technical-plan authoring + at
  Δ-16 prerequisite check.
---

# Tech architecture decision catalog (Δ-3)

When authoring Phase 3 technical plan, walk these 8 decisions. Each decision binds a downstream invariant; deferring or making the decision implicitly is the failure mode this Δ exists to prevent.

This doc is the FRAMEWORK decision catalog. Adopters' chosen values land in `docs/foundational/technical-plan.md`.

## §1 The 8 decisions

### §1.1 Decision #1 — Abstraction layer

What's the agent's primary action surface?

**Sub-choice** (Constitution §1.7-A; default for Type A):

- **Single tool-use layer** (default) — agent's per-turn output is a tool call OR a customer-facing response. No parallel action enum.
- **Single action enum** — small fixed enum (e.g., `escalate | resolve | clarify`) without tool-use. Type B workflows may default here when the SOP runner is the controller.
- **Hybrid (FORBIDDEN per §1.7-A)** — a 5-action enum AND tool-use simultaneously. Constitution §1.7-A breach.

### §1.2 Decision #2 — Context projection

What goes into the LLM's per-turn projection?

- Slot list (what state is surfaced).
- Candidate list (e.g., possible UCs, candidate tools).
- Diagnostic flags (e.g., low-confidence-from-retrieval flag).
- Historical context shape (last N turns; rolling summary; selective).

This binds prompt size + cache strategy.

### §1.3 Decision #3 — State persistence

Where does multi-turn state live + how is it serialized?

- In-memory (single session; lost on session end).
- Persistent store (DB; cache; file).
- Event-sourced (replayable; the trace IS the state).

Type A agents typically need persistent state for entity continuity. Type B workflows may use in-memory if the SOP runner is stateless.

### §1.4 Decision #4 — Memory

How does the agent remember beyond a single session?

- None (each session starts fresh).
- User-scoped (per-user memory).
- Org-scoped (shared across users).
- Combination (user + org + session).

Memory is where Constitution §1.4 (PII / safety floor) often gets load-bearing.

### §1.5 Decision #5 — Skill / tool set

What tools does the agent have?

- ALLOW matrix per UC (Type A): which tools are reachable from which use case.
- Off-the-shelf skill inventory (Type C): named, pre-built skills.
- SOP-step → tool mapping (Type B): each SOP row binds to a tool call.

Constitution §1.7's "no UC-specific hard rules for soft semantic decisions" applies: ALLOW matrix is OK (capability declaration); semantic routing AMONG allowed tools is LLM-owned.

### §1.6 Decision #6 — Escalation enum

What are the escalation triggers + what action does each trigger?

- Fixed enum of escalation reasons (e.g., `human_review_required` | `policy_question` | `out_of_scope`).
- Mapping from enum value to action (e.g., handoff to live agent / route to product team / silently fail with note).

NEW escalation enum values trigger `new_tier0_candidate` MANDATORY_CHECKPOINT (per `process/delivery-loop.md` §4.2.3 item 4) since they expand runtime ownership.

### §1.7 Decision #7 — Policy / safety surface

Which policies are runtime-owned (Constitution §1.4) vs LLM-owned (Constitution §1.3)?

- PII / safety floor (always runtime).
- Grounding floor for factual claims (runtime checks; LLM declines when unsupported).
- Per-domain policy hooks (e.g., "no refunds over $X without human review").
- Product-policy enum (e.g., "this is a product question, not a customer-service question; route accordingly").

### §1.8 Decision #8 — Trace + eval contract

What gets recorded; what gets surfaced to the eval harness?

- Trace shape (per-turn fields: tool_calls, slot updates, response, diagnostics).
- 6-primitive trace_check DSL grammar (per `process/typeA-runtime-architecture-skeleton.md` Δ-6).
- Bad-case suite schema link (`schemas/case-spec.schema.json`).
- F5 evidence cmd (`charter.tooling.eval.cmd`).

This binds what Acceptance Agent can judge against.

## §2 Decision binding + sequencing

Decisions are NOT independent. Each binds the next:

```
#1 abstraction layer  → constrains #5 (skill / tool set shape)
#2 context projection → constrains #3 (state persistence) + #4 (memory)
#3 state persistence  → constrains #4 (memory)
#5 skill / tool set   → constrains #6 (escalation enum) + #7 (policy surface)
#6 escalation enum    → binds #7 policy responses
#7 policy surface     → binds #8 trace fields (what to record)
#8 trace + eval       → binds Acceptance + Code Reviewer surfaces
```

Make #1 first; make #8 last (because it depends on all upstream choices). The other 6 may iterate within a Phase 3 round.

## §3 Decision documentation

For each decision, the Phase 3 technical plan records:

```markdown
### Decision #N — <name>

**Chosen**: <chosen value>

**Alternatives considered**: <list>

**Why this choice**: <rationale>

**What this binds downstream**: <which other decisions / which Δ-Y / which Tier-0 invariant>

**Reversibility**: easy / medium / hard / one-way-door
**Reverse-flow triggers**: <if Phase N reveals this choice infeasible, what changes>
```

Decision reversibility is honest framing: most #2/#3/#5 choices are reversible within a milestone; #1 (abstraction layer) is hard to reverse once tool catalogs accumulate (Constitution §1.7-A motivates getting this right early).

## §4 NEW Tier-0 invariant route

A decision that introduces a NEW Tier-0 invariant (typically #1, #6, #7) routes through `new_tier0_candidate` MANDATORY_CHECKPOINT (`process/delivery-loop.md` §4.2.3 item 4). Customer approves before adoption.

Per Constitution §1.5: a new Tier-0 invariant means runtime ownership has expanded. The check exists because Tier-0 expansions are durable (and removing them later breaks downstream code) — making the expansion deliberate prevents the slow Java-guard-creep failure mode.

## §5 Cross-Δ relationships

- **Δ-2** Domain discovery — D3 (boundary) outputs are inputs to decisions #2, #6, #7.
- **Δ-6** Type A runtime skeleton — instantiates decisions #1, #2, #5, #8 for Type A track.
- **Δ-9** OBS triage — uses the layer-set this catalog binds.
- **Δ-12** Artifact taxonomy — `docs/foundational/technical-plan.md` is where chosen values land.
- **Δ-16** Agent creation prereqs — category #3 (engineering baseline) consumes this catalog.

## §6 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 8-decision shape + binding order (§2) is load-bearing framework vocabulary. Adopters MAY add a 9th decision with rationale (e.g., specific to their compliance regime) but SHOULD NOT renumber the 8 — Code Reviewer prompts + Phase 3 templates may reference decision numbers directly.

---

End of Δ-3 Tech architecture decision catalog.
