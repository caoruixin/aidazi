---
title: Common detours and warnings — Type C (Δ-17-C placeholder)
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
  Δ-17-C placeholder per v4-plan §4.1. Type C demo detours TBD; populated
  when first Type C adopter lifecycle completes and surfaces concrete
  pattern evidence. Until then, Type C adopters use Δ-17-A's P1 (spec-first
  / data-late) as a primary approximation.
---

# Common detours and warnings — Type C (Δ-17-C placeholder)

This is a **placeholder doc** awaiting concrete Type C pattern evidence. Per OQ-V4-003, full Type C detour catalog is deferred until a first Type C adopter completes a documentable lifecycle.

## §1 Why placeholder, not blank

v4 reserves the slot so:
- The Δ numbering is stable.
- Type C adopters know to consult Δ-17-A's P1 (spec-first / data-late) as a primary approximation.
- When pattern evidence accumulates, the doc populates per the fold-back protocol.

## §2 Anticipated Type C-specific patterns (when populated)

Type C demos have characteristic risks that don't appear in Type A / B:

- **Demo-script optimization at expense of demonstrability** — the demo script gets so tightly tuned to a specific path that it can't handle audience-provided variations. Common at trade shows.
- **LOCAL_ACCEPTANCE_CHECKLIST drift** — checklist authored at Phase 1; demo content drifts; checklist not re-validated; ship the demo and the checklist no longer matches.
- **Off-the-shelf-skill versioning** — a pre-built skill the demo depends on gets updated externally; demo breaks at the next run.
- **Acceptance every-sprint becomes acceptance never** — Type C is supposed to run Acceptance every sprint per Δ-14; adopter skips because "the demo passes manually." Silent drift accumulates.

These will be confirmed (or replaced) at the first Type C adopter's milestone close fold-back.

## §3 Δ-17-A patterns that approximately apply

- **P1 Spec-first / data-late** — applies. Even for demos, building from desk-review without checking real audience reactions produces brittle demos.
- **P4 Mid-milestone pivot** — applies for any multi-milestone Type C project (rare; most Type C is single-milestone).

P2 + P3 don't apply to Type C.

## §4 Trigger to populate

This doc populates when ANY of:
1. First Type C adopter (`examples/fortunes-reference-placeholder` or other) completes documentable lifecycle.
2. A second Type C adopter confirms or refutes the patterns above.
3. Framework maintainer judges the deferral is no longer serving adopters.

When triggered, full Δ-17-C authoring follows the Δ-17-A shape (4-pattern set).

## §5 Cross-references

- `process/common-detours-and-warnings-typeA.md` (Δ-17-A) — read for P1 / P4 approximations.
- `process/profile-aware-maturity.md` (Δ-14) — Type C characterization (Acceptance every-sprint requirement).
- `templates/mission-charter.yaml` `profile_type_c` overlay — Type C configuration shape.
- OQ-V4-003 in `process/fold-back-protocol.md` §7.

---

End of Δ-17-C Common detours Type C (placeholder).
