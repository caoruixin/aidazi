---
title: Milestone objective — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
load_discipline: by-role
size_target: 6KB
notes: >
  Per milestone north star template. Deliver authors at milestone start (Path 1
  research-driven) referencing the docs/research-briefs/<id>.md closure_contract
  as the milestone's source of truth. Lifetime: live until milestone close;
  archived to docs/sprints/<milestone-id>/ at close. Per
  process/milestone-framework.md: 3-5 sub-sprints per milestone (suggested).
---

# Milestone objective — instance template

Copy this template to `<adopter>/docs/milestone_objective.md` (replaces at each milestone start; previous version archives to `docs/sprints/<milestone-id>/milestone_objective.md` at close).

---

```markdown
---
title: Milestone <milestone-id> — <short name>
doc_tier: milestone-objective
doc_category: live
milestone_id: <milestone-id>
status: current
last_reviewed: <YYYY-MM-DD>
closure_contract_source: <docs/research-briefs/<id>.md>   # the brief Customer signed at gate 1
research_brief_signed_date: <YYYY-MM-DD>                  # must match milestone start; Acceptance verifies
charter_path: <adopter>/charter.yaml                       # if Δ-18 orchestrator adopted
acceptance_run_at: milestone_close | release_cut | both
autonomy_level: human_in_the_loop | human_on_the_loop | fully_autonomous_within_budget
sub_sprint_sequence:
  - <sprint-id-1>
  - <sprint-id-2>
  - <sprint-id-3>
---

# Milestone <milestone-id> — <short name>

## North star (closure_contract)

(Cite the brief; do NOT duplicate the closure_contract text here. Acceptance
will re-read the brief at milestone close — keep ONE source of truth.)

Source: <docs/research-briefs/<id>.md>

Summary in one paragraph (for fast-glance reference; the brief's
closure_contract is the contract):

<one paragraph>

## Sub-sprint decomposition

(3-5 sub-sprints typical per process/milestone-framework.md. Each sub-sprint
gets its own sprint_objective.md at dispatch time; this section is the
planned sequence.)

| # | Sprint id | Scope (one line) | Depends on |
|---|---|---|---|
| 1 | <sprint-id-1> | <scope-summary> | — |
| 2 | <sprint-id-2> | <scope-summary> | <sprint-id-1> |
| 3 | <sprint-id-3> | <scope-summary> | <sprint-id-2> |

## Acceptance plan

(Per Constitution §3.6 + process/delivery-loop.md §4.2.7 acceptance.)

- **When**: <milestone_close | release_cut | both> (per charter.acceptance.run_at)
- **Calibration status**: <calibrated | uncalibrated | n/a (manual mode)>
- **Spawn surface**: <human paste | orchestrator>
- **Source closure_contract**: docs/research-briefs/<id>.md (signed YYYY-MM-DD)
- **F5 evidence command** (per charter.tooling.eval.cmd):
  `<shell-command>`
- **Eval evidence path pattern**: `eval/runs/<run-id>/`

## Dependencies + risks

- <dependency-1>: <state>
- <risk-1>: <mitigation plan>

## Architecture decisions made for this milestone

(Cite Δ-3 decisions if any new ones land. Reference process/tech-architecture-decision-catalog.md.)

- <decision-1>: <choice + rationale>

## Cross-references

- Research brief (closure_contract source): `<docs/research-briefs/<id>.md>`
- Charter (if Δ-18 adopted): `<adopter>/charter.yaml`
- Bad-case suite manifest: `eval/bad_cases/_manifest.md`
- Action bank live: `docs/action_bank.md`
- Previous milestone close package (if applicable): `docs/sprints/<prev-milestone-id>/`

## At milestone close

Acceptance Agent reads:
1. The closure_contract from `closure_contract_source` above.
2. F5 evidence from the eval run.
3. Code Reviewer's latest `docs/codex-findings.md`.

Verdict → `docs/acceptance-reports/<milestone-id>-acceptance-report.md` per
`schemas/acceptance-verdict.schema.json`.

If `fix_required`: human-confirm checkpoint at
`docs/checkpoints/<timestamp>__acceptance_fix_required__<milestone-id>.md`
per Constitution §3.5.

Customer's gate-2 ship sign-off: in this file's archived copy
`docs/sprints/<milestone-id>/milestone_objective.md` close note.
```

## Template usage notes

- Do NOT inline the closure_contract paragraph here. The brief is the source of truth (Constitution §3.4 invariant #4 — Research-Acceptance contract symmetry). Acceptance reads the brief; Deliver and the Code Reviewer reference it; the milestone objective points at it.
- `sub_sprint_sequence` MUST match `charter.autonomy.approved_scope.subsprint_sequence` exactly. Mismatch triggers `scope_deviation` MANDATORY_CHECKPOINT at the first sub-sprint close.
- `acceptance_run_at: both` is conservative (Acceptance fires twice: milestone close + release cut); adopters may choose `milestone_close` only if release cut == milestone close for their lifecycle.
- The "At milestone close" section is the runbook for what the orchestrator (or human-paste workflow) does at close.

---

End of milestone objective template.
