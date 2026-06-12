---
title: Application funnel — the Phase 1-5 reference
doc_tier: application-guide
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 20KB
split_trigger: if a single phase section grows past 5KB, split that phase to its own template and keep the summary row here
notes: >
  The Phase 1-5 funnel reference — the detailed per-phase companion to the
  step-by-step docs/greenfield-guide.md STEP 5. Governing principles:
  progressive disclosure (each phase pulls in only what it can use) and
  explicit reverse-flow (later phases backtrack openly, not silently). Also
  carries the profile decision tree (Type A/B/C/A+B) and the per-phase Δ-17
  detour cross-references. Each phase produces one docs/foundational/ doc.
---

# Application funnel — the Phase 1-5 reference

This is the reference companion to the greenfield guide. Where `docs/greenfield-guide.md` STEP 5 gives the funnel as one step in a bootstrap, this doc is the detailed per-phase reference you return to while walking it. Each phase produces a source-of-truth document under `docs/foundational/`.

The funnel replaces what older framing called "Phase 0 normative freeze." There is no Phase 0 — the framework *is* the norms. You start at Phase 1 (business need) and walk to Phase 5 (eval).

## §1 Two governing principles

**Progressive disclosure** — each phase pulls in *only* the inputs it can actually use. Technical constraints (platform APIs, integration approach, infrastructure) do **not** arrive at Phase 1; they arrive at Phase 3, where they're needed for design. Asking for them earlier causes either premature commitment (locking in an integration before the service is defined) or paralysis (a need-finder blocked on tech specs they can't yet use).

**Reverse-flow is explicit** — the funnel is not strictly forward. Real projects discover at a later phase that an earlier one was infeasible. When that happens you **backtrack openly**: you don't silently "redo Phase 2." Each foundational doc carries a "reverse-flow triggered from" log so the backtrack is owned, not hidden. Silent re-deciding is how scope drifts and stakeholders lose the thread.

## §2 The funnel at a glance

| Phase | Produces (`docs/foundational/`) | Purpose | Reverse-flow trigger |
|---|---|---|---|
| **1 Business need & goal** | `business-need.md` | What the customer/market wants; the "what should we build" statement | source phase — none from above |
| **2 Product/Service design** | `product-service-design.md` | How we satisfy Phase 1 — the UCs/SOPs/skills that compose the service | Phase 2 can't deliver Phase 1 → revisit scope/KPI |
| **3 Technical plan** | `technical-plan.md` | How to implement Phase 2 technically; constraints + integration arrive here | Phase 2 design technically infeasible → re-design Phase 2 |
| **4 Coding/Implementation packet** | `coding-packet.md` | Break the technical plan into shipping units | budget/scope mismatch → back to Phase 3 or 2 |
| **5 Eval/Release/Feedback** | `eval-design.md` | Verify delivered system satisfies the Phase 1 closure_contract; close the loop | reproducible failure → root-cause may push back to any earlier phase |

## §3 Per-phase detail

### Phase 1 — Business need & goal

- **Purpose**: define what the customer/market wants and the project must satisfy. The "what should we build" statement.
- **Inputs at this phase**: Δ-15 Q1-Q3 (Domain / Goal / Problems) elicitation; Δ-16 #1 (BRD prerequisite).
- **Framework provides**: the elicitation Q-set + the BRD prerequisite schema.
- **Project fills**: market analysis, KPI thresholds, scope IN/OUT, anti-goal phrasing. **Customer signs (gate 1).**
- **Source phase** — no reverse-flow arrives here; everything downstream is judged against this. The closure_contract authored here is the Acceptance verdict source.
- **Detour to watch**: P1 *spec-first / data-late* (`process/common-detours-and-warnings-typeA.md`) — don't finalize the UC taxonomy before looking at real transcripts/data.

### Phase 2 — Product/Service design

- **Purpose**: design the product/service that satisfies Phase 1 — what use-cases / SOPs / skills compose it.
- **Inputs at this phase**: Phase 1 output; domain handling rules; (Type A) transcript samples for UC inference; (Type B) SOP draft; (Type C) off-the-shelf skill catalogs; Δ-16 #2 (PRD).
- **Framework provides**: Δ-15 Part B+C inventories; Δ-3 decision #1 (abstraction-layer; default single tool-use per §1.7-A); Δ-3 decision #6 (tool definition).
- **Project fills**: UC names + IDs and tool ALLOW matrix and escalation enum (Type A); SOP step registry + per-step verification gates (Type B); off-the-shelf skill list (Type C); domain handling rules.
- **Reverse-flow**: if Phase 2 can't deliver Phase 1, push back to revisit scope or KPI.
- **Split-or-merge**: Phase 1 and Phase 2 may be one doc or two — see §5 below.

### Phase 3 — Technical plan

- **Purpose**: plan how to implement Phase 2 technically. **Technical constraints + integration with existing systems arrive HERE — not earlier.**
- **Inputs at this phase**: Phase 2 output; Δ-16 #3 (engineering baseline); Δ-16 #6 (external systems/APIs — e.g., Salesforce, internal services); Δ-16 #7 (UI, partial); infrastructure; security/PII floor; cloud constraints.
- **Framework provides**: Δ-6 portable runtime skeleton; Δ-3 decisions #2-#7 (context projection / state / memory / tools / policy); the 6-primitive trace_check DSL surface.
- **Project fills**: phase-pipeline names (e.g., INIT→DISCOVER→RESOLVE→CONFIRM→CLOSE→ESCALATE), the Tier-0 invariant list (`docs/current/runtime_invariants.md`), projection model details, persistence layer, integration adaptors.
- **Reverse-flow**: if Phase 3 finds the Phase 2 design technically infeasible, push back to re-design the product/service form.

### Phase 4 — Coding/Implementation packet

- **Purpose**: break the technical plan into shipping units.
- **Inputs at this phase**: Phase 3 output; Δ-16 #4 (knowledge corpus); Δ-16 #5 (canned-reply templates).
- **Framework provides**: Δ-4 lifecycle rules; Δ-10 responsibility-matrix scaffold for module governance.
- **Project fills**: module names + dependencies (DM1..N), delivery order, mocks list, .env values.
- **Reverse-flow**: if Phase 4 reveals a scope/budget mismatch, push back to Phase 3 or Phase 2.

### Phase 5 — Eval/Release/Feedback

- **Purpose**: verify the delivered system satisfies the Phase 1 closure_contract; close the loop.
- **Inputs at this phase**: Phase 3+4 outputs; the Phase 1 closure_contract (the Acceptance verdict source); bad-case seed.
- **Framework provides**: the M-Evaluation 4-component model; the 6-primitive trace_check DSL; the 4-tier pyramid; the Δ-18 charter template.
- **Project fills**: per-tier check selection per case; judge rubric specialization; baseline ledger init; calibration set authoring; charter values (if Δ-18 used).
- **Reverse-flow**: if Phase 5 fails reproducibly, root-cause may push back to any earlier phase.
- **Detours to watch**: P2 *eval-before-architecture-stable*; P3 *autoloop-as-eval-stress-test* (`process/common-detours-and-warnings-typeA.md`).

## §4 Profile decision tree (which track are you?)

Walk this before Phase 1 if your track isn't obvious:

```
Q1. Does the system primarily reason adaptively per turn, or follow a fixed sequence per task?
    adaptive          → Type A
    fixed sequence    → Type B (go Q2)
    neither/unsure    → Q3

Q2. (if Type B) Does it also have an LLM-controlled top loop, or is the SOP-runner the only controller?
    yes, top loop     → Type A+B hybrid
    no, SOP only      → pure Type B

Q3. Is this a demo/POC where customer-demonstrability beats coverage?
    yes               → Type C
    no                → revisit Q1; you may be conflating goals
```

Your track sets the Δ subset and the fix-layer set you walk (`process/profile-aware-maturity.md`, Δ-14). The phases are the same for every track; the inputs and depth differ.

## §5 Phase 1 + Phase 2 — split or merge

The business-need (Phase 1) and product/service-design (Phase 2) documents can be merged or split:

- **Merge** (one `docs/foundational/business-and-product.md`) when: Type C demos (always); single-author or seed-stage projects; the need-definer is the service-designer.
- **Split** (two docs) when: medium+ complexity; multiple stakeholders; the "what" and the "how" have different owners who can disagree.

Merging is a real option, not a shortcut — but if you merge and stakeholders later diverge, split at the next milestone boundary (not mid-flight). The unwind is `docs/friction-playbook.md` F15.

## §6 Relationship to the rest of the guide

- **Step-by-step bootstrap**: `docs/greenfield-guide.md` (this funnel is its STEP 5, expanded).
- **What the foundational docs feed**: the closure_contract (Phase 1) → Acceptance; the runtime invariants (Phase 3) → Code Reviewer; the eval design (Phase 5) → the bad-case suite + calibration.
- **Where domain values come from**: `docs/domain-adaptation.md` (the three domain contracts populated across Phases 1-3).
- **Detour self-diagnosis mid-flight**: `process/common-detours-and-warnings-typeA.md` (Δ-17) — backward-looking, "if you're here, exit this way," complementing this forward-looking funnel.

---

End of application funnel.
