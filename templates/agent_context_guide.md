---
title: Agent context guide (consumer template)
doc_tier: current-runtime
status: current
source_of_truth: this file
notes: >
  Template for `docs/current/agent_context_guide.md` in a consumer
  project. Lists task-type reading lists (which docs and code areas
  an agent should sample first for common task types in YOUR
  project). This is DOMAIN-SPECIFIC; the framework provides only the
  template shape. The framework's cold-start reading order and
  Context Pack Prompt live in
  `framework/governance/context_briefing.md`.
---

# Agent context guide — <project name>

Per `framework/governance/context_briefing.md`, every agent on a cold
start reads:

1. AGENTS.md (auto-loaded; transitively loads framework governance +
   your domain context)
2. Role entry doc (deliver / dev / review / research)
3. Active contracts (milestone_objective + sprint_objective)
4. Cross-session state (`docs/10-handoff.md` §0 + §1 lead + §2 index)

Then, depending on **task type**, the agent samples specific
docs/code paths. This file lists those task-type reading lists for
**your project**.

## Task-type reading lists

### Task: <domain task type 1, e.g., "Fix a lane misclassification">

- **Sample docs**:
  - `docs/current/domain_taxonomy.md` §<X> — <lane definitions>
  - `docs/foundational/<your-architecture-doc>.md` §<Y> — <relevant
    architectural context>
- **Sample code paths**:
  - `<src/.../lane_classifier.py>` — <one line on what it owns>
  - `<src/.../projection.py>` — <one line>
- **Layer hypotheses to consider** (§3.2):
  - `prompt_projection` if LLM lacks input
  - `skill_state` if context lost across turns
  - `semantic_planner` if LLM choice is wrong despite correct input
- **Bad cases likely relevant**:
  - `eval/bad_cases/<id_1>.yaml`
  - `eval/bad_cases/<id_2>.yaml`

### Task: <domain task type 2, e.g., "Add a new tool to the agent">

(same structure)

### Task: <domain task type 3, e.g., "Update grounding floor metric">

(same structure)

### Task: Generic semantic-touching change

When the task doesn't fit a named task type:

- **Sample docs**:
  - `docs/current/runtime_invariants.md` — check Tier-0 boundaries
  - `docs/current/eval_acceptance_bars.md` — check acceptance metrics
- **Sample code paths**: <project-specific generic samples>
- **Use the Context Pack Prompt** from
  `framework/governance/context_briefing.md` before any plan or
  diff.

## Maintenance

This file is updated as the project's task taxonomy evolves. When
deliver-agent observes a new task type appearing in 2+ sprints, add
a reading list entry.
