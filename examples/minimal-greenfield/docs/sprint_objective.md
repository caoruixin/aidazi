---
title: Acme Returns Bot — sprint-001 objective
doc_tier: adopter-state
doc_category: live
status: current
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: per sprint close
sprint_id: sprint-001
milestone_id: M1
---

# sprint-001 — Eligibility check tool + INIT→CHECK pipeline

## Scope

Implement the deterministic eligibility-check tool and wire the INIT→CHECK phase pipeline so the bot, given an order id, calls the tool and projects the result for the LLM to phrase.

- **Layers touched**: `semantic_planner`, `prompt_projection`.
- **Modules touched**: `src/tools/eligibility.py`, `src/pipeline/check.py`.
- **Out of scope**: denial-reason wording (sprint-002), escalation (sprint-003).

## Test plan

- Unit: eligibility math (window boundary at exactly 30 days; non-refundable category).
- Behaviour: 5 seed bad cases (eligible / just-expired / non-refundable item / unknown order / already-refunded).

## Bad-case suite additions

5 cases land in `eval/bad_cases/` (see `eval/bad_cases/_manifest.md`).

## Sub-sprint stanza (per `aidazi/schemas/sprint_stanza.schema.json`)

```yaml
objective: eligibility check tool + INIT→CHECK pipeline
generalization_coverage: target (5 cases) + neighbor (boundary day) + negative (unknown order)
rollback: none (new capability; no deprecation)
introduced_hardcode: false
```

---

End of sprint-001 objective.
