---
title: Cross-session handoff
doc_tier: current-runtime
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: per milestone close
notes: >
  Cross-session continuity state file. Three sections:
  §0 cold-start table (always current), §1 narrative (current
  milestone only), §2 archive index. Retention rule per
  `framework/governance/doc_governance.md`.
---

# Cross-session handoff

## §0. Cold-start table

| Field | Value |
|-------|-------|
| Current phase | <e.g., "M0 setup", "M1 S2 in flight", "M3 close in progress"> |
| Active milestone | `docs/milestone_objective.md` (M<N>) |
| Active sub-sprint | `docs/sprint_objective.md` (sprint-<NNN>) |
| Last closed milestone | <id + close date + archive path> |
| Last closed sub-sprint | <id + close date + archive path> |
| Eval baseline | `docs/current/eval_baseline.md` (last refresh: <sprint id>) |
| Bad-case suite size | <N> active cases (`eval/bad_cases/_manifest.md`) |
| Open R-items | <N> in `docs/action_bank.md` §5 |
| Next action | <e.g., "human to review sprint-002 handoff", "deliver-agent to draft sprint-003 prompt"> |

## §1. Narrative

### Current milestone — M<N>: <name>

<2–4 paragraphs on the current milestone scope, progress, key
findings, and pending decisions. Updated by deliver-agent at each
sub-sprint close.>

### Last closed milestone — M<N-1>: <name>

<One paragraph summary + archive pointer. Truncated at the next
milestone close per the retention rule.>

## §2. Milestone archive index

| Milestone | Name | Status | Close date | Archive |
|-----------|------|--------|------------|---------|
| M0 | <name> | <closed / open> | <date> | `docs/milestones/M0_*.md` |
| M1 | <name> | <closed / open> | <date> | `docs/milestones/M1_*.md` |
| ... | ... | ... | ... | ... |
