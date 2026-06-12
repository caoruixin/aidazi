---
title: Acme Returns Bot — Milestone M1 objective
doc_tier: adopter-state
doc_category: live
status: current
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: per milestone close
milestone_id: M1
closure_contract_source: docs/research-briefs/RB-001-refund-eligibility.md
---

# M1 — Refund eligibility determination

## North star

Deliver a bot that, for UC-1, reliably determines refund eligibility for a specific order and either confirms it with a clear timeline or explains the specific blocking reason — per the closure_contract in `docs/research-briefs/RB-001-refund-eligibility.md` (Customer-signed).

## Sub-sprints (3; per `aidazi/process/milestone-framework.md`)

| # | Scope IN | Layers | Acceptance |
|---|---|---|---|
| sprint-001 | Eligibility check tool + INIT→CHECK pipeline | `semantic_planner`, `prompt_projection` | at milestone close |
| sprint-002 | Denial-reason explanation (UC-2) | `prompt_projection` | at milestone close |
| sprint-003 | Escalation path (UC-4) + bad-case suite seeding | `semantic_planner`, `eval_spec` | at milestone close |

## Acceptance plan

Acceptance runs at M1 close (Customer paste, gate 2), judging delivered behaviour against the RB-001 closure_contract + the standing floors in `docs/current/eval_acceptance_bars.md`.

## Dependencies + risk

- Δ-3 decision #1: single tool-use abstraction (per §1.7-A). Recorded in `docs/foundational/technical-plan.md`.
- Risk: eligibility math must be deterministic (TI-1/TI-3); a tempting shortcut is to let the LLM "estimate" days-since-delivery — forbidden.

---

End of M1 objective.
