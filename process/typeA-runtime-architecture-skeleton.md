---
title: Type A runtime architecture skeleton (Δ-6)
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
size_target: 14KB
notes: >
  Δ-6 EXTEND per v4-plan §4.1: intent gate + phase pipeline (portable T1
  skeleton) + 6-primitive trace_check DSL (frozen grammar; portable Tier-2
  surface; §1.7-B structural defence). The 6-primitive DSL primitive names
  are the canonical set referenced by schemas/case-spec.schema.json.
---

# Type A runtime architecture skeleton (Δ-6)

Type A AI agents share a runtime skeleton — an intent gate, a phase pipeline, and a trace_check DSL surface for Tier-2 evaluation. This Δ defines the portable shape; adopter-side instantiation lives in `docs/foundational/technical-plan.md` (Phase 3) and the adopter's runtime code.

This Δ does NOT apply to Type B (which uses a SOP runner) or Type C (which uses off-the-shelf skills). Type A+B hybrid uses Type A's skeleton plus Type B's workflow_definition layer.

## §1 The skeleton

```
                Customer message arrives
                          │
                          ↓
                  ┌──────────────┐
                  │  Intent gate │   (LLM-owned per Constitution §1.3:
                  │              │    user goal / topic hypothesis /
                  │              │    drift detection)
                  └──────┬───────┘
                         │
              ┌──────────┼─────────────────────┐
              ↓          ↓                     ↓
        ┌─────────┐ ┌─────────┐         ┌──────────────┐
        │ Phase A │ │ Phase B │ ...     │  Phase ESCAL │
        │         │ │         │         │              │
        │ skill_  │ │ skill_  │         │ human_review │
        │ state   │ │ state   │         │ _required    │
        └────┬────┘ └────┬────┘         └──────────────┘
             │           │
             └─────┬─────┘
                   ↓
            ┌────────────┐
            │ Response   │   (LLM-owned per Constitution §1.3:
            │ generation │    natural customer-facing wording;
            │            │    grounding floor runtime-enforced
            │            │    per Constitution §1.4)
            └─────┬──────┘
                  │
                  ↓
            ┌────────────┐
            │ Trace      │   (Runtime-owned per Constitution §1.4:
            │ emission   │    trace + eval contract)
            └─────┬──────┘
                  │
                  ↓
            Customer-facing response delivered
```

### §1.1 Intent gate

Per-turn first step. The LLM (NOT runtime) decides:

- What's the user's goal in this turn?
- Is this a continuation of a previous turn's task, or a new task?
- Is there topic drift requiring re-classification?
- Does the user appear to require escalation (off-topic for the agent; affect / safety; explicit ask)?

The intent gate's output is a structured intent classification (typically a hypothesis with confidence; NOT a single forced category).

Intent gate is Constitution §1.3-owned. Runtime invariants per Constitution §1.4 (PII / safety / grounding) sit AROUND it as deterministic checks (e.g., "if user message hits PII threshold, redact before LLM sees it") — they don't replace the LLM's intent classification.

### §1.2 Phase pipeline

After intent, the turn enters a phase. Each phase has:

- A set of permitted tool calls (Constitution §1.7's UC-specific hard rules are forbidden; the phase's tool ALLOW matrix is a CAPABILITY declaration, not a routing decision).
- A set of slot updates that may happen in this phase.
- A set of legal next phases (the phase graph; partly LLM-owned).

The phase set is per-adopter (e.g., csagent uses INIT / DISCOVER / RESOLVE / CONFIRM / CLOSE / ESCALATE). The skeleton's portability is in the SHAPE — turn → phase → tools / slots → next phase → response. The names are adopter-specific.

### §1.3 Trace emission

Per Constitution §1.4: trace + eval contract is runtime-owned.

For Type A, the trace records:

- Intent gate's classification + confidence.
- Phase entered + phase transitions across turns.
- Tool calls dispatched + their results (the `accumulated_tool_results` map).
- Slot updates (the `intake_state.fields_collected` accumulator).
- Session-level flags.

These five surfaces are the inputs the 6-primitive trace_check DSL (§3 below) operates on.

## §2 Intent-switch hook

A specific runtime contract Type A agents need: when the LLM detects topic drift mid-task, the system needs to handle the switch deterministically (runtime-owned per Constitution §1.4 "idempotency" + "persistence") without losing the abandoned task's state.

Suggested mechanism (csagent-derived; portable):

- Runtime exposes an `intent_switch_hook` that the LLM can invoke when it classifies a new top-level intent.
- The hook serializes the abandoned task's state (so it can resume) and resets the phase pipeline to INIT for the new intent.
- The trace records the switch as a discrete event.

The hook itself is runtime-owned (deterministic). The DECISION to invoke it is LLM-owned. This is the §1.3 / §1.4 split applied to a specific common pattern.

Adopters MAY implement intent-switch differently; the framework guarantee is that the SHAPE — explicit hook + serializable abandoned state + trace event — is portable across implementations.

## §3 The 6-primitive trace_check DSL (frozen grammar)

Tier-2 evaluation (per `modules/m-evaluation.md`) uses a portable trace_check DSL with **exactly 6 frozen primitives**. The grammar is **intentionally minimal** and REJECTS at parse time any expression that would constitute a Constitution §1.7-B semantic hardcode (keyword / regex / message-content match).

This is the structural defence: the bad-case suite's `closure_criterion` paragraph (human-judgment) is the SEMANTIC contract; the trace_check DSL provides the OBSERVABLE evidence the closure_criterion is grounded in. Keyword matching against message content is the failure mode the DSL prevents at parse time.

### §3.1 The 6 frozen primitives

**Data primitives** (4):

1. **`tool_call_present(<tool>)`** — presence check. True iff the trace's `accumulated_tool_results` map contains an entry for the named tool.

2. **`tool_call_order(<tool_a>, <tool_b>)`** — order check. True iff `tool_a` was successfully dispatched before `tool_b` in this case's tool-call timeline.

3. **`slot_collected(<field>)`** — slot presence check. True iff the per-turn `intake_state.fields_collected` list contains the named field.

4. **`session_flag(<flag>)`** — flag boolean. True iff the trace's `session` object exposes the named flag with a truthy value.

**Combinators** (2):

5. **`any_of(<expr>, <expr>, ...)`** — true iff any inner expression is true.

6. **`all_of(<expr>, <expr>, ...)`** — true iff every inner expression is true.

### §3.2 What's rejected at parse time

Any expression that doesn't match the 6 primitives — including any of the following — fails parse:

- `message.contains(<phrase>)`
- `user_message.matches(<regex>)`
- `re.search(<pattern>, ...)`
- `keyword_match(<list>)`
- List-membership tests against message content.
- Any new primitive name not in the 6.

The parser names the rejected primitive in the error message; the rejection set is asserted by a structural defence test in adopter implementations.

### §3.3 Extension procedure

When an adopter encounters a need for a NEW primitive (Tier-3 domain-specific check), the procedure:

1. Author the primitive in adopter's domain-specific grammar (NOT the portable 6).
2. Mark adoption-state.md row for Δ-6 as `partial` with rationale.
3. File a `proposed-amendment` lesson if the primitive seems portable across adopters; the framework maintainer evaluates at fold-back.

Pre-emptive widening of the portable 6 is forbidden. The structural defence depends on the grammar staying tight.

### §3.4 Schema reference

`schemas/case-spec.schema.json` enumerates the 6 primitives by name in the `scoring.primitives` field. The names there are the canonical set.

### §3.5 Mapping — portable primitive → concrete trace field

The portable names abstract over adopter-specific trace field shapes. The csagent donor implementation maps:

| Portable primitive | csagent concrete trace field expression |
|---|---|
| `tool_call_present(<tool>)` | `accumulated_tool_results.<tool>` (presence check on the trace's `accumulated_tool_results` map) |
| `tool_call_order(<tool_a>, <tool_b>)` | `tool_event_seq(<tool_a>) < tool_event_seq(<tool_b>)` (timeline-order check on tool-call dispatch events) |
| `slot_collected(<field>)` | `intake_state.fields_collected.contains(<field>)` (per-turn intake-state slot membership) |
| `session_flag(<flag>)` | `session.<flag>_present` (session-object flag truthy-value check) |
| `any_of(<expr>, ...)` | `any_of(<expr>, ...)` (combinator; same name) |
| `all_of(<expr>, ...)` | `all_of(<expr>, ...)` (combinator; same name) |

Adopters whose runtime exposes different trace field names (e.g., a Type B runtime exposes `sop_step_outcomes.<step>` instead of `accumulated_tool_results.<tool>`) author their concrete expressions per their stack but record per-case primitives using the PORTABLE names. The portable names travel; the concrete expressions are adopter-domain.

When authoring a CaseSpec with `scoring.primitives: [...]`, use the portable names. The adopter's parser maps to concrete expressions at evaluation time.

## §4 Layer set this skeleton binds

Type A runtime fixes the following fix-layer set (per `process/post-deployment-iteration.md` Δ-9):

- `infra` — orchestration, transport, persistence, timeouts.
- `java_guard` / `runtime_guard` — Tier-0 invariants (Constitution §1.4 ownership).
- `prompt_projection` — what state is surfaced to the LLM per turn.
- `skill_state` — multi-tool / multi-turn flow state.
- `semantic_planner` — the LLM's own semantic choices (intent + phase + tool choice).
- `eval_spec` — CaseSpec; closure_criterion; judge config.
- `product_policy` — policy decisions the runtime CANNOT make alone.
- `judge_calibration` — judge stability + rubric quality.
- `human_review_required` — escalation when no clean classification.

These are the layers a Code Reviewer's verdict (`schemas/review-verdict.schema.json`) cites, and the layers an Δ-9 OBS triage routes to.

## §5 Cross-Δ relationships

- **Δ-3** Tech-architecture decisions instantiate the skeleton for an adopter (decisions #1 / #2 / #5 / #8 in particular).
- **Δ-9** OBS triage uses the layer set this skeleton binds.
- **Δ-12** Artifact taxonomy — trace artifact is part of the 14-artifact set.
- **modules/m-evaluation.md** — 4-tier pyramid + 6-primitive DSL.
- **modules/m-autoloop.md** — Auto Loop operates over this skeleton (Type A only).

## §6 What this Δ does NOT cover

- Type B SOP runner skeleton — `profile_type_b` in charter overlay; deferred until OQ-V4-001 resolves.
- Type C demo skeleton — `profile_type_c`; minimal.
- Domain-specific tool definitions — `docs/foundational/technical-plan.md` (Phase 3).
- Tier-3 trace_check primitives — adopter-specific.

## §7 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 6-primitive DSL grammar is FROZEN — adding a primitive requires fold-back consensus + a corresponding update to `schemas/case-spec.schema.json` AND a §1.7-B structural defence audit (the new primitive MUST NOT reintroduce keyword/regex/message-match capability).

The phase pipeline shape (intent gate → phases → response → trace) is stable framework vocabulary; adopters' specific phase names are per-project.

---

End of Δ-6 Type A runtime skeleton.
