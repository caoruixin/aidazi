---
title: Sprint objective — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
load_discipline: by-role
size_target: 4KB
notes: >
  Per sub-sprint contract template. Deliver authors at sub-sprint dispatch.
  Carries the sprint stanza (machine-validated 4-field header per
  schemas/sprint_stanza.schema.json). Orchestrator preflight gate
  validate_stanza runs at sub-sprint dispatch.
---

# Sprint objective — instance template

Copy this template to `<adopter>/docs/sprint_objective.md` (replaces at each sub-sprint dispatch; previous version archives to `docs/sprints/<sprint-id>/sprint_objective.md` at close).

---

```markdown
---
title: Sprint objective — <sprint-id>
doc_tier: sprint-objective
doc_category: live
sprint_id: <sprint-id>
milestone_id: <milestone-id>
status: current
last_reviewed: <YYYY-MM-DD>
sprint_stanza:                                  # validated against schemas/sprint_stanza.schema.json
  sprint_id: <sprint-id>
  scope_in:
    - <deliverable-1>
    - <deliverable-2>
  layers:
    - <layer-1>                                 # subset of charter.approved_scope.layers_allowed
    - <layer-2>
  exit_criteria:
    - <observable-criterion-1>
    - <observable-criterion-2>
  modules:
    - <repo-path-1>
    - <repo-path-2>
  milestone_id: <milestone-id>
  next_subsprint: <id | null>
---

# Sprint <sprint-id> — <short title>

## North star

<1-2 sentences pointing at the milestone closure_contract clause this
sub-sprint advances. Cite docs/research-briefs/<id>.md if relevant.>

## Scope IN

- <deliverable-1>: <what; observable signature>
- <deliverable-2>

## Scope OUT (explicit non-deliverables)

(Tighter than 'obvious things'; name adjacent-but-out-of-scope concerns to
prevent scope creep.)

- <non-deliverable-1>
- <non-deliverable-2>

## Layers touched

(From `process/post-deployment-iteration.md` Δ-9 layer set. Subset of
charter.approved_scope.layers_allowed.)

- <layer-1>: <one-line why>
- <layer-2>: <one-line why>

## Modules touched

(Must be subset of charter.approved_scope.modules_in_scope per
scope_envelope_check.)

- <repo-path-1>
- <repo-path-2>

## Test plan

(What tests will exist after this sprint.)

- <test-name-1>: <what it verifies; tier per modules/m-evaluation.md>
- <test-name-2>

## Bad-case suite additions

(Joint authoring per Constitution §5 state ledgers: Deliver curates structure;
human authors closure_criterion. If none this sprint, state so.)

- <case-id>: <one-line; closure_criterion drafted in eval/bad_cases/<id>.yaml>

## Exit criteria

(Observable; will be verified at close. Distinct from the milestone-level
closure_contract — this is sub-sprint-level.)

- <criterion-1>
- <criterion-2>

## Dependencies / risks

- <dependency-1>
- <risk-1>: <mitigation>

## Hand-off to Dev

(Cross-reference the compact dev prompt for this sprint.)

- Dev prompt: `compact/<sprint-id>-dev-prompt.md`
- Code Reviewer prompt: `compact/<sprint-id>-review-prompt.md`
- Sandbox: workspace_write (per charter)
- Backing Dev agent: <claude_code | codex | other>
```

## Template usage notes

- `sprint_stanza` in front-matter is machine-validated against `aidazi/schemas/sprint_stanza.schema.json`. The orchestrator's `validate_stanza` preflight gate runs at sub-sprint dispatch.
- The `scope_in` field in the stanza MUST be a subset of `charter.approved_scope` — if it's broader, `scope_envelope_check` fires at close (`process/delivery-loop.md` §4.2.5).
- `next_subsprint: null` means this is the last sub-sprint of the milestone; orchestrator routes to `milestone_close` next.
- Per `process/milestone-framework.md`: 3-5 sub-sprints per milestone (suggested per Constitution §7.0; adopters override with rationale).
- This file is replaced at each sub-sprint dispatch; the prior version archives. Do NOT carry stale content forward (Δ-4 live-vs-intermediate).

---

End of sprint objective template.
