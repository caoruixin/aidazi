---
title: Common detours and warnings — Type B (Δ-17-B placeholder)
doc_tier: process
doc_category: live
status: partial
implementation_status: not_started
source_of_truth: this file
last_reviewed: 2026-06-07
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 4KB
notes: >
  Δ-17-B placeholder per v4-plan §4.1 + OQ-V4-001. Type B agentic workflow
  detours TBD; populated when hermes-autoloop completes its first SOP
  milestone end-to-end and surfaces concrete pattern evidence. Until then,
  Type B adopters reference Δ-17-A's cross-cutting patterns (P1 / P4 in
  particular) as approximations.
---

# Common detours and warnings — Type B (Δ-17-B placeholder)

This is a **placeholder doc** awaiting concrete Type B pattern evidence. Per OQ-V4-001, full Type B detour catalog is deferred until hermes-autoloop completes its first SOP milestone end-to-end.

## §1 Why placeholder, not blank

v4 reserves the slot so:
- The Δ numbering is stable (Δ-17-A / Δ-17-B / Δ-17-C exist as a triple even if B is unpopulated).
- Type B adopters know to consult Δ-17-A's cross-cutting patterns (P1 spec-first / P4 mid-milestone-pivot apply across tracks).
- When pattern evidence accumulates, the doc populates per the fold-back protocol.

## §2 Approximated patterns from Δ-17-A (use these in the interim)

Type B adopters should walk Δ-17-A even though it's nominally Type A. The following Δ-17-A patterns approximately apply:

- **P1 Spec-first / data-late** — applies in modified form. Type B's "data" is real-world SOP execution logs + edge cases the SOP doesn't cover cleanly. Building the SOP from desk-review alone, without watching real users walk the workflow, is the Type B P1 shape.
- **P4 Mid-milestone pivot** — applies identically. Discovering the SOP itself is wrong mid-milestone and silently absorbing the change is the same anti-pattern.

P2 (eval-before-architecture-stable) and P3 (autoloop-as-eval-stress-test) are NOT Type B common patterns — eval pyramid is per-step verification (more structured); Auto Loop is N/A for Type B.

## §3 Anticipated Type B-specific patterns (when populated)

Based on hermes-autoloop's known early-stage friction (not yet confirmed as durable patterns):

- **Verification-gate-as-keyword-match** — a per-step verification gate authored as keyword/regex matching against user input. Violates Constitution §1.7-B + §1.5 iteration rule.
- **SOP-row-too-fine-grained** — SOP rows splitting into so many steps that the runner produces excessive checkpoint overhead; user-facing latency degrades.
- **SOP-row-too-coarse-grained** — SOP rows bundling multiple semantically-distinct steps so verification can't isolate failures.
- **OCR-or-extraction-noise-treated-as-semantic-failure** — verification gate fails because OCR / data extraction noise; misclassified as a semantic-planner failure when it's actually `infra` layer.

These will be confirmed (or replaced) at hermes's first SOP milestone close fold-back.

## §4 Trigger to populate

This doc populates when ANY of:
1. Hermes-autoloop completes 3 consecutive SOP milestones with documented patterns.
2. A second Type B adopter (or A+B hybrid) lands and confirms or refutes hermes's pattern set.
3. Framework maintainer judges the deferral is no longer serving adopters (e.g., multiple lessons cite the missing Type B catalog).

When triggered, full Δ-17-B authoring follows the Δ-17-A shape: 4-pattern set, symptom / why / exit / pre-emption per pattern, cross-cutting indicators.

## §5 Cross-references

- `process/common-detours-and-warnings-typeA.md` (Δ-17-A) — read in lieu of populated B.
- `process/profile-aware-maturity.md` (Δ-14) — Type B characterization.
- `templates/mission-charter.yaml` `profile_type_b` overlay — Type B configuration shape.
- OQ-V4-001 in `process/delivery-loop.md` §6 + `process/fold-back-protocol.md` §7.

---

End of Δ-17-B Common detours Type B (placeholder).
