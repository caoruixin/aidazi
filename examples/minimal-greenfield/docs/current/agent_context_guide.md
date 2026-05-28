---
title: Agent context guide
doc_tier: current-runtime
status: current
implementation_status: not_started
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: every 3-5 milestones
notes: >
  Project-specific task-type reading lists. Fill incrementally as
  task types appear in 2+ sprints. Template structure from
  `framework/templates/agent_context_guide.md`.
---

# Agent context guide

Per `framework/governance/context_briefing.md`, every agent on a cold
start reads the constitution chain (auto-loaded via AGENTS.md), the
role-specific entry doc, active contracts, and `docs/10-handoff.md`.

Then, depending on **task type**, the agent samples specific docs/code
paths. This file lists task-type reading lists for **this project**.

## Task-type reading lists

### Task: <task type 1>

(Fill when the task type appears in 2+ sprints.)

- **Sample docs**:
  - `docs/current/domain_taxonomy.md` §<X>
  - <other doc paths>
- **Sample code paths**:
  - `<path/to/file.py>` — <one line on what it owns>
- **Layer hypotheses to consider** (§3.2):
  - <layer>: <when this layer is suspected>
- **Bad cases likely relevant**:
  - `eval/bad_cases/<id>.yaml`

### Task: <task type 2>

(same structure)

### Task: Generic semantic-touching change

When the task doesn't fit a named task type:

- **Sample docs**:
  - `docs/current/runtime_invariants.md` — check Tier-0 boundaries
  - `docs/current/eval_acceptance_bars.md` — check acceptance
    metrics
- **Sample code paths**: <generic project samples>
- **Use Context Pack Prompt** from
  `framework/governance/context_briefing.md` before any plan or
  diff.

## Maintenance

This file is updated as the project's task taxonomy evolves. When
deliver-agent observes a new task type appearing in 2+ sprints, add a
reading list entry.
