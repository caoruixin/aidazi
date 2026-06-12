---
title: M-Evaluation module
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
size_target: 16KB
notes: >
  M-Evaluation module spec. Defines the evaluation surface across all tracks:
  4 components (CaseSpec + judge + harness + baseline) + 4-tier pyramid
  (smoke / scenario / target / shadow) + 6-primitive trace_check DSL anchor
  (per Δ-6) + adaptor pattern (per-track scoring substrate). Portable;
  adopters instantiate via charter.tooling.eval.cmd + their domain-side
  harness. Conditional T1: applies if charter declares an eval cmd.
---

# M-Evaluation module

The M-Evaluation module defines the evaluation surface — what gets judged, how, by whom, with what evidence. It is portable across tracks; adopters instantiate per their domain via `charter.tooling.eval.cmd` and a domain-side harness.

This module is the system the **bad-case suite** (`process/badcase-lifecycle.md`) runs ON. It's the system the **Acceptance Agent** judges WITH (per Constitution §3.5 + F5 evidence pattern). It's the system the **Code Reviewer** cross-references at §4.3 trigger (per `role-cards/code-reviewer-agent.md`).

This module is CONDITIONAL — applies when `charter.tooling.eval.cmd` is declared. Adopters running pure-manual chain (`charter.autonomy.level: human_in_the_loop`) MAY still instantiate it; the orchestrator's role in F5 evidence (per `process/delivery-loop.md` §4.2.6) is what's optional.

## §1 The 4 components

Every M-Evaluation instance has 4 components that together produce a judgment.

### §1.1 CaseSpec — the test case

A CaseSpec is a single evaluation case (one input scenario; one expected outcome shape). Schema: `schemas/case-spec.schema.json`.

Fields:
- `case_id` (stable id).
- `source_suite` (target / neighbor / negative / shadow_holdout / calibration).
- `tier` (tier1_smoke / tier2_scenario / tier3_target_set / tier4_shadow per §2 below).
- `input` (free-shape per track; Type A: customer message + state; Type B: SOP step + slot values; Type C: demo trigger).
- `expected` (quick-glance reference; NOT the closure_criterion).
- `scoring` (which judge; which primitives; what rubric).
- `closure_criterion` (Constitution §1.7-B three-component paragraph — positive shape + anti-pattern + anchor phrases).

Authoring is JOINT (Constitution §5): Deliver Agent curates structure; human authors `closure_criterion`.

### §1.2 Judge — the verdict authority

Three judge modes (per `schemas/case-spec.schema.json` `scoring.judge` enum):

- **`judge_llm`** — an LLM judges semantically against the closure_criterion. Used for tier2 / tier3 / tier4 cases with semantic content.
- **`judge_rubric`** — a rubric-driven judge applies a documented scoring rubric. Used for cases where the rubric is well-defined (e.g., format compliance, slot completeness).
- **`deterministic_assertion`** — a hard assertion (e.g., "this tool was called"; "this slot was collected"). Used for tier1 smoke cases. Constitution §1.5 applies: deterministic assertions are NOT acceptable for soft semantic decisions.

The judge's calibration is required for Acceptance autonomy per Constitution §3.6.

### §1.3 Harness — the runner

The harness runs the case batch and produces per-case results. `charter.tooling.eval.cmd` declares the harness command; F5 evidence pattern (per `process/delivery-loop.md` §4.2.6) wires orchestrator to run it and produce artifact files Acceptance can read.

Harness responsibilities:
- Load CaseSpecs from the suite directory.
- Execute each case through the system-under-test (the adopter's runtime).
- Capture the trace per `modules/m-trace.md`.
- Invoke the judge for each case.
- Emit per-case verdict + aggregate summary.

The harness is per-adopter (different runtimes; different transports); the M-Evaluation contract specifies the INPUTS (CaseSpec batch) and OUTPUTS (artifact paths matching F5 evidence) — not the implementation.

### §1.4 Baseline — historical comparison

The baseline ledger records prior runs' results so regressions are detectable.

- Per-case `terminal_outcome` history.
- Per-suite aggregate pass-rate history.
- Architecture-health metric snapshots per `process/architecture-health-metrics.md`.

Baseline is referenced at sub-sprint / milestone close for "no regression" judgments per Constitution §1.6 (eval is evidence, not authority — but baseline regression IS a hard signal).

## §2 The 4-tier pyramid

Cases are tiered by their depth + cost + role. Pyramid runs bottom-up at most close events:

```
                  ┌──────────────────────────┐
                  │ tier4_shadow             │  hold-out; runs less often;
                  │  (holdout / generalization │  forbidden read by Dev sandbox
                  │   check)                 │  per Constitution §10.
                  └──────────────────────────┘
              ┌──────────────────────────────────┐
              │ tier3_target_set                 │  curated target cases (the
              │  (closure_contract-anchored     │  closure_contract source);
              │   target cases)                  │  primary acceptance surface.
              └──────────────────────────────────┘
          ┌──────────────────────────────────────────┐
          │ tier2_scenario                           │  scenario-coverage; uses
          │  (semantic judge; multi-turn cases)      │  6-primitive trace_check
          │                                          │  DSL + judge_llm typically.
          └──────────────────────────────────────────┘
      ┌──────────────────────────────────────────────────┐
      │ tier1_smoke                                      │  deterministic assertions;
      │  (cheap; runs every PR or every sprint)          │  fast; high-frequency.
      └──────────────────────────────────────────────────┘
```

### §2.1 Tier roles + cadence

| Tier | Cases | Judge | Cadence | What it tells you |
|---|---|---|---|---|
| `tier1_smoke` | 10-30 deterministic-assertion cases | `deterministic_assertion` | Every PR (sub-sprint dispatch can rerun) | Did basic plumbing not regress? |
| `tier2_scenario` | 20-100 scenario cases | `judge_llm` or `judge_rubric` | Every sub-sprint close | Are scenario behaviors holding? |
| `tier3_target_set` | curated; closure_contract-anchored | `judge_llm` | Every milestone close | Are we delivering against the closure_contract? |
| `tier4_shadow` | holdout; generalization check | `judge_llm` | Every release cut + periodic | Does target performance generalize to held-out cases? |

Specific counts are SUGGESTED per Constitution §7.0; adopters scale.

### §2.2 Tier roles vs bad-case suite

The bad-case suite (per `process/badcase-lifecycle.md`) intersects all 4 tiers — bad-case cases get tier-tagged. A bad case starting at tier3 (target-set; high attention) may downgrade to tier4 (regression guard; low attention) after 2+ consecutive PASS milestones (`closed-as-regression-guard` per `process/badcase-lifecycle.md` §5).

## §3 6-primitive trace_check DSL (anchor)

Tier-2 scenario cases that use trace-based verification rely on the 6-primitive DSL frozen by `process/typeA-runtime-architecture-skeleton.md` (Δ-6):

1. `tool_call_present(<tool>)` — data primitive.
2. `tool_call_order(<tool_a>, <tool_b>)` — data primitive.
3. `slot_collected(<field>)` — data primitive.
4. `session_flag(<flag>)` — data primitive.
5. `any_of(<expr>, ...)` — combinator.
6. `all_of(<expr>, ...)` — combinator.

The grammar rejects keyword / regex / message-content match at parse time — Constitution §1.7-B structural defence. CaseSpec `scoring.primitives: [...]` enumerates the primitives a case uses.

For the portable→csagent mapping table, see `process/typeA-runtime-architecture-skeleton.md` §3.5.

Adopter Type B / hybrid stacks MAY expose different concrete trace field expressions backing the same portable primitive names. The portable names travel; concrete expressions are adopter-domain.

## §4 Adaptor pattern (per-track scoring substrate)

M-Evaluation works across tracks because its judge invocation is delegated through an adaptor:

```
M-Evaluation harness  ─→  Adaptor (per-track)  ─→  Adopter system-under-test
                              ↓
                          Trace (per modules/m-trace.md)
                              ↓
                          Judge (per §1.2)
                              ↓
                          Verdict + evidence artifacts
```

The adaptor's responsibility:
- Map portable CaseSpec `input` shape to the adopter's runtime input format.
- Capture trace in the portable shape (per `modules/m-trace.md`).
- Map judge verdict to per-case result.

### §4.1 Type A adaptor

- `input` → customer message + session state.
- Trace exposes intent gate decisions, phase transitions, tool calls, slot updates.
- Judge uses 6-primitive DSL + closure_criterion semantic match.

### §4.2 Type B adaptor

- `input` → SOP step + slot values.
- Trace exposes per-step verification gate outcomes.
- Judge uses per-step verification rules + (for top-loop hybrid) 6-primitive DSL.

### §4.3 Type C adaptor

- `input` → demo trigger.
- Trace exposes off-the-shelf skill invocations + demo-script states.
- Judge uses LOCAL_ACCEPTANCE_CHECKLIST per-item assertions.

### §4.4 Hybrid (A+B) adaptor

- Combines Type A semantic top-loop tracing AND Type B per-step SOP tracing.
- Judge reads both surfaces; verdicts cover both layers.

## §5 Suite organization

```
eval/
  bad_cases/                            # the curated bad-case suite per badcase-lifecycle.md
    <case-id>.yaml                      # one CaseSpec per file
    _manifest.md                        # lifecycle ledger
  case_specs_shadow/                    # holdout; do_not_load by Dev
    <case-id>.yaml
  case_specs_calibration/               # labeled set for §3.6 calibration
    manifest.json
  runs/                                 # per-run artifact dirs (F5 evidence)
    <run-id>/
      stdout.txt
      artifacts/
        per-case-trace-<case-id>.json
        per-case-judge-<case-id>.json
        aggregate.json
```

Suite-side path conventions are SUGGESTED per Constitution §7.0 — adopters using different layouts (per the `evidence_path` adopter-override note in `schemas/acceptance-verdict.schema.json`) update their local schema accordingly.

## §6 F5 evidence integration

When Acceptance is invoked at milestone close (per Constitution §3.5):

1. Orchestrator (or human in manual mode) runs `charter.tooling.eval.cmd`.
2. Harness produces artifacts at `eval/runs/<run-id>/`.
3. Acceptance prompt's `load_list` includes artifact paths.
4. Acceptance judges per closure_contract; `evidence_path` field cites the artifact paths.

F5 evidence is HARD requirement (per `process/delivery-loop.md` §4.2.8 anti-pattern #5): Acceptance verdicts citing code paths alone are invalid.

## §7 Code Reviewer cross-reference

At Code Reviewer's §4.3 trigger (`role-cards/code-reviewer-agent.md` §2), the reviewer cross-references `eval/bad_cases/`:

- Does the diff add a new semantic decision surface NOT covered by an existing case?
- Does the diff change a behavior path WITHOUT a corresponding test in the suite?

A "yes" produces a non-blocking observation in `docs/codex-findings.md` (P2 severity typically) suggesting suite expansion for next sprint.

## §8 Calibration gate integration

`charter.tooling.acceptance.judge_calibration.status` (per Constitution §3.6):

- Calibration set lives at `eval/case_specs_calibration/manifest.json`.
- Each entry: `(trace, expected_verdict ∈ {PASS, FAIL})`.
- Run Acceptance twice; compute agreement_rate + flip_rate.
- Calibrated iff `agreement_rate ≥ 0.9 AND flip_rate ≤ 0.1` (suggested defaults per §7.0).

If `charter.tooling.acceptance.agent_kind` OR `model` changes, calibration is invalidated; re-run required.

## §9 Anti-patterns

- **Tier1 smoke regression treated as architectural failure** — tier1 cases are PLUMBING checks; they catch infrastructure issues, not semantic ones. Treating a tier1 failure as evidence of semantic regression confuses the surfaces.
- **Tier2 cases promoted to tier3 without closure_contract anchoring** — tier3 cases MUST anchor to closure_contract clauses. Promoting tier2 scenarios without that anchoring dilutes tier3's role.
- **Tier4 shadow drift** — shadow set never refreshed; held-out cases become trivially-passable. Mitigation: rotate shadow set per `process/fold-back-protocol.md` cadence.
- **Adaptor leaking implementation** — adaptor exposes adopter-specific trace fields directly to CaseSpec authors. Mitigation: trace transformation happens INSIDE adaptor; CaseSpec authors see portable surface.
- **Judge optimization** — judge LLM tuned to pass more cases. Constitution §1.7 forbids; calibration set is the regression guard.

## §10 What this module does NOT cover

- Specific harness implementation — adopter-domain.
- Specific judge prompts — adopter-domain (the rubric layer).
- Trace capture details — `modules/m-trace.md`.
- Auto Loop / experiment selection — `modules/m-autoloop.md`.
- Eval contamination prevention — Constitution §10 + `process/badcase-lifecycle.md` §8.

## §11 Cross-references

- Constitution §1.6 — Eval rule (the policy).
- Constitution §3.6 — Calibration gate.
- `process/typeA-runtime-architecture-skeleton.md` (Δ-6) — 6-primitive DSL canonical definition + mapping table.
- `process/badcase-lifecycle.md` — bad-case suite + tier lifecycle.
- `process/architecture-health-metrics.md` — architecture-health metrics; collection lands here.
- `modules/m-trace.md` — trace shape + portability.
- `modules/m-autoloop.md` — Auto Loop's reward signal MUST be closure_contract-anchored (not raw pass rate).
- `process/delivery-loop.md` §4.2.6 — F5 evidence pattern.
- `schemas/case-spec.schema.json` — CaseSpec schema.
- `schemas/acceptance-verdict.schema.json` — Acceptance verdict consumes M-Evaluation outputs.

## §12 Editing this module

Module-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 4-component decomposition + 4-tier pyramid + 6-primitive DSL are stable v4 vocabulary. Track-specific adaptor patterns (§4) may evolve as adopters report patterns. Calibration thresholds are SUGGESTED defaults per Constitution §7.0.

---

End of M-Evaluation module.
