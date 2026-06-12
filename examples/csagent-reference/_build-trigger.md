# csagent-reference — build trigger

**Status**: not populated. This is a Type A worked-example reference (end-to-end: BRD → Phase 5 → 49+ sprints) that gets populated from a csagent snapshot when an adopter needs it.

## Trigger conditions (any one)

- A new Type A adopter starts onboarding and needs a worked Type A reference.
- The v4 framework stabilizes (no major Δ changes across 3 sub-sprints).
- A fold-back sub-sprint surfaces "lack of worked example" as a recurring lesson (`process/fold-back-protocol.md`).

## Source content (when triggered)

Snapshot of the csagent project state at the trigger date. Populate these sub-dirs:

- `decisions/` — csagent's Δ-3 8-decision actual choices (esp. #1 abstraction-layer).
- `discovery/` — Phase 1 BRD/PRD extracted artifacts (anonymized as needed).
- `m-eval/` — the M-Evaluation actual instantiation (CaseSpec / 4-tier / judge config).
- `m-trace/` — the trace contract actual instantiation.
- `runtime-skeleton/` — the Δ-6 Type A runtime skeleton, filled.
- `delivery-loop/` — if csagent adopts the orchestrator, its charter + run examples (Concept 2).
- `timeline.md` — lifecycle date stamps.

## Snapshot conventions (Δ-7 read-only-after-snapshot)

- Name the populated dir `examples/csagent-reference-YYYY-MM-DD/` so subsequent snapshots don't collide.
- Read-only after snapshot; never sync upstream changes into it.

## Build cost estimate

~6-8h once triggered.

---

Until triggered, Type A adopters use `examples/minimal-greenfield/` (the working consumer template) as the live reference.
