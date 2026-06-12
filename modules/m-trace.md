---
title: M-Trace module
doc_tier: module
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
  M-Trace module spec. Defines the portable trace shape, the run_mode field
  (live | mock | replay | shadow), the trace contract abstraction across
  Type A / B / C / A+B hybrid, and the F5 evidence cross-reference. Trace is
  runtime-owned per Constitution §1.4 ("trace and eval contract"). This module
  is CONDITIONAL T1 — applies when the adopter has a traceable runtime; not
  required at S0 manual chain mode.
---

# M-Trace module

The M-Trace module defines the portable trace shape — the runtime-emitted record of what happened during one execution unit (a turn, a SOP step, a demo run). Trace is the substrate the M-Evaluation module (`modules/m-evaluation.md`) judges against, and the substrate the F5 evidence pattern (`process/delivery-loop.md` §4.2.6) feeds to the Acceptance Agent.

Trace is **runtime-owned** per Constitution §1.4 ("trace and eval contract"). The LLM does not author traces; the runtime emits them deterministically as a side-effect of execution.

This module is CONDITIONAL — applies when the adopter's runtime emits traces. S0 manual-chain adopters (per `process/capability-staging-roadmap.md`) often don't have traces; they progress to traceable runtimes at S2 / S3 typically.

## §1 What a trace is

A trace is the structured record of one execution unit. Each turn (Type A) / SOP step (Type B) / demo run (Type C) produces ONE trace entry.

A trace is:
- **Per-execution-unit** — one trace per turn / step / run.
- **Structured** — fields are named; not free-form prose.
- **Runtime-emitted** — the runtime writes; the LLM does not author.
- **Inspectable** — humans + judges + Code Reviewer can read.
- **Comparable** — same input twice should produce nearly-identical traces (modulo non-determinism markers).

A trace is NOT:
- A debug log (too verbose; not structured).
- A transcript (transcripts are user-facing; traces are runtime-internal).
- An audit log (audit logs are persisted long-term for compliance; traces may be ephemeral).

## §2 The portable trace shape (universal base + per-track extensions)

Every trace carries a UNIVERSAL BASE — fields all adopters need — plus PER-TRACK EXTENSION fields specific to the track.

### §2.1 Universal base fields

```yaml
trace:
  trace_id: <stable id>
  execution_unit_id: <turn-id | step-id | run-id>
  run_mode: live | mock | replay | shadow
  timestamp_start: <ISO timestamp>
  timestamp_end: <ISO timestamp>
  input: <execution-unit input; opaque map>
  output: <execution-unit output; opaque map>
  tool_calls: []      # populated if applicable; empty for runtimes with no tools
  errors: []          # populated if execution errored
  metadata:
    run_id: <eval-harness run-id, if applicable>
    case_id: <CaseSpec id, if running an eval case>
    adopter_track: type_a | type_b | type_c | type_a_b_hybrid
```

`run_mode` is the load-bearing field for the F5 evidence pattern + bad-case suite lifecycle. See §3.

### §2.2 Type A extension fields

```yaml
trace:
  ...universal base...
  intent_classification:
    primary: <classification>
    confidence: <0..1>
    alternatives: []
  phase:
    current: <phase-name>
    entered_at: <timestamp>
    transition_from: <prev-phase | null>
  accumulated_tool_results:
    <tool-name>: <result-summary>
  intake_state:
    fields_collected: [<field>, <field>, ...]
    fields_pending: [...]
  session:
    <flag-name>_present: <bool>
    ...
```

These fields back the 6-primitive trace_check DSL per `process/typeA-runtime-architecture-skeleton.md` Δ-6:
- `tool_call_present(<tool>)` reads `accumulated_tool_results.<tool>`.
- `tool_call_order(<a>, <b>)` reads `tool_calls[]` timeline order.
- `slot_collected(<field>)` reads `intake_state.fields_collected`.
- `session_flag(<flag>)` reads `session.<flag>_present`.

### §2.3 Type B extension fields

```yaml
trace:
  ...universal base...
  sop_step:
    sop_id: <SOP-id>
    step_id: <step-id>
    step_index: <integer>
    verification_gates:
      - gate_id: <gate-id>
        outcome: pass | fail | n/a
        details: <map>
  sop_runner_state:
    current_step: <step-id>
    completed_steps: [<step-id>, ...]
    skipped_steps: [<step-id>, ...]
    retry_count: <int>
```

For Type B with LLM-mediated step verification, an additional field per step records the LLM's verification reasoning.

### §2.4 Type C extension fields

```yaml
trace:
  ...universal base...
  demo_run:
    demo_id: <demo-id>
    skill_invocations: [<skill-id>, ...]
    checklist_outcomes:
      - item: <checklist-item-id>
        outcome: pass | fail
```

Type C traces are typically smaller; LOCAL_ACCEPTANCE_CHECKLIST per-item outcomes are the primary content.

### §2.5 Type A+B hybrid extension fields

Hybrid traces include BOTH Type A fields (top-loop tracing) AND Type B fields (SOP-runner tracing). The top loop's `intent_classification` decides which SOP to start; the SOP-runner fields record per-step execution.

## §3 The `run_mode` field

`run_mode` declares what kind of execution produced the trace:

- **`live`** — real production execution against real systems. Production traffic.
- **`mock`** — execution where one or more downstream systems are mocked. Used in dev + low-cost eval. Mocking SHOULD be declared (per Constitution §1.6 + `process/badcase-lifecycle.md` §6 mocked-LLM evidence gate); judgments on mock traces are advisory unless explicit evidence supports otherwise.
- **`replay`** — execution replaying a recorded trace + injecting variations. Used for Auto Loop experiments + counterfactual analysis.
- **`shadow`** — execution against held-out scenarios; Dev sandbox MUST NOT have read access (per Constitution §10 anti-pattern: eval contamination).

The `run_mode` field appears in F5 evidence artifact filenames (e.g., `eval/runs/<run-id>/artifacts/per-case-trace-<case-id>-live.json`) so Acceptance can verify which mode produced the evidence.

### §3.1 Acceptance interaction with run_mode

Acceptance verdicts MUST specify the `run_mode` of the evidence they cite. Mocked-LLM evidence + live-LLM evidence don't carry equal weight (Constitution §1.6 mocked-LLM gate).

An Acceptance verdict that cites mock-mode evidence for a high-stakes ship decision triggers `needs_human` (per `role-cards/acceptance-agent.md` §8) — Customer judges whether the mock evidence is sufficient.

## §4 Trace contract abstraction

Adopters' runtimes vary; the trace contract abstracts over the variance:

```
Adopter runtime emits raw trace
        ↓
Trace contract adaptor:
  - Map adopter-specific fields to universal base + per-track extensions.
  - Add metadata (run_mode, run_id, case_id).
  - Emit JSON to standardized location (eval/runs/<run-id>/artifacts/).
        ↓
M-Evaluation harness reads.
Acceptance Agent reads (via F5 evidence).
Code Reviewer reads (at §4.3 trigger; for trace-shape diff review).
```

The adaptor's responsibility is to bridge adopter-specific trace fields to the portable shape. Where adopter fields don't match portable shape, the adaptor MAY:
- Synthesize a portable field from multiple adopter fields.
- Mark a portable field `null` if the adopter doesn't expose the corresponding data (and document in adoption-state.md).
- Add a `_local` namespace for adopter-specific fields that don't fit the portable shape.

## §5 Trace storage + retention

### §5.1 Per-eval-run storage

Traces produced by F5 evidence runs live at `eval/runs/<run-id>/artifacts/per-case-trace-<case-id>.json`. These are PER-RUN — orchestrator triggers each run; artifacts accumulate per `eval/runs/` lifecycle.

### §5.2 Production trace retention

Production live traces are governed by the adopter's data-retention policy (PII / safety per Constitution §1.4). The framework does not specify retention windows.

For Auto Loop experiments (`modules/m-autoloop.md`), production traces become candidate inputs to experiment selection; the adopter governs which traces are eligible (typically excluding PII-rich traces; redaction at production-trace storage time).

### §5.3 Lifecycle integration with badcase-lifecycle

When a bad case is `closed-as-regression-guard` per `process/badcase-lifecycle.md` §3, traces from the bad case's recent runs are evidence the case is no longer manifesting. Acceptance reads these at milestone close.

## §6 Trace inspectability + Code Reviewer

The Code Reviewer Agent reads traces at §4.3 trigger when:
- A diff changes trace-emitting code (the runtime's trace adaptor).
- A diff would change trace shape (added field; renamed field; removed field).

Changes to trace shape are HIGH IMPACT — they break:
- M-Evaluation cases (closure_criterion's 6-primitive trace_check DSL references field names).
- Acceptance verdicts (evidence_path artifacts have schema expectations).
- Bad-case manifest (per-case `tier` decisions reference trace structure).

A Code Reviewer finding flagging trace-shape change MUST be P0 — the migration must be planned, not silent. Often routes to a `new_tier0_candidate` MANDATORY_CHECKPOINT if the change touches Tier-0 invariants per Constitution §1.4.

## §7 Anti-patterns

- **Trace bloat** — every adopter-specific field added to the universal base. Erodes portability. Mitigation: adopter-specific fields go in `_local` namespace.
- **Trace as prose** — runtime emits trace as free-form text instead of structured JSON. Defeats 6-primitive DSL parseability. Mitigation: enforce structured trace at adaptor.
- **`run_mode` field omitted** — judgment proceeds without knowing whether evidence is live or mock. Mitigation: schema validation at adaptor output.
- **PII leakage via trace storage** — traces stored without PII redaction; production traces accidentally exposed. Mitigation: Constitution §1.4 PII floor applies to trace storage equally.
- **Eval contamination via trace replay** — shadow case traces replayed against Dev sandbox; Dev tunes to shadow signals. Mitigation: `run_mode: shadow` traces explicitly excluded from Dev sandbox load_list (per Constitution §10 anti-pattern).

## §8 What this module does NOT cover

- Production trace storage backend choice (DB / files / cloud) — adopter-domain.
- PII redaction implementation — adopter-domain (Constitution §1.4 sets the floor).
- Trace visualization / dashboarding — adopter tool choice.
- Specific 6-primitive DSL semantics — `process/typeA-runtime-architecture-skeleton.md` (Δ-6).
- Acceptance verdict shape — `schemas/acceptance-verdict.schema.json`.

## §9 Cross-references

- Constitution §1.4 — Runtime-owns: trace + eval contract.
- `process/typeA-runtime-architecture-skeleton.md` (Δ-6) — 6-primitive DSL + portable→csagent mapping.
- `modules/m-evaluation.md` — judges read traces.
- `modules/m-autoloop.md` — Auto Loop experiments consume traces.
- `process/delivery-loop.md` §4.2.6 — F5 evidence pattern.
- `process/badcase-lifecycle.md` — bad-case lifecycle interacts with trace history.
- `schemas/case-spec.schema.json` — CaseSpec references trace fields via 6-primitive DSL.

## §10 Editing this module

Module-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The universal base fields are stable v4 vocabulary; per-track extension fields evolve as tracks mature. Adding fields to universal base requires fold-back deliberation. Trace-shape breaking changes are framework-level events (route through v5 migration guide per `process/fold-back-protocol.md`).

---

End of M-Trace module.
