# Minimal greenfield skeleton

This directory is a **bare-bones project skeleton** you can copy
into a new project to bootstrap `aidazi` adoption.

## Usage

From your new project root (NOT from inside `aidazi/`):

```bash
# Assuming you've already added aidazi as a submodule at framework/
cp -r framework/examples/minimal-greenfield/. .
```

This copies (without overwriting your `framework/` submodule):

- `AGENTS.md` — root constitution (already configured to point at
  `framework/`)
- `docs/current/{domain_taxonomy,runtime_invariants,eval_acceptance_bars,agent_context_guide}.md`
  — domain contract placeholders (you fill in M0)
- `docs/{10-handoff,action_bank,milestone_objective,sprint_objective}.md`
  — empty scaffolds
- Empty directories: `docs/{sprints,milestones,solutions,diagnostics/failure-briefs}/`,
  `compact/`, `eval/bad_cases/`

After copying, edit each file marked `<...>` placeholder to reflect
your project. The greenfield guide
(`framework/docs/greenfield-guide.md`) walks through this step-by-step.

## What's in each file

| File | Purpose | When to fill |
|---|---|---|
| `AGENTS.md` | Root constitution | At adoption (project description placeholder) |
| `docs/current/domain_taxonomy.md` | Workflow lanes / shift / escalation / grounding | M0 |
| `docs/current/runtime_invariants.md` | Tier-0 invariants | M0 |
| `docs/current/eval_acceptance_bars.md` | Acceptance metrics | M0 |
| `docs/current/agent_context_guide.md` | Task-type reading lists | Incrementally per task type |
| `docs/10-handoff.md` | Cross-session state | At every milestone close |
| `docs/action_bank.md` | R-item backlog | Continuous |
| `docs/milestone_objective.md` | Active milestone | At each milestone start |
| `docs/sprint_objective.md` | Active sub-sprint | At each sub-sprint start |
| `eval/bad_cases/_manifest.md` | Bad-case ledger | As bad cases surface |

## Note on the `<...>` placeholders

Most files contain `<like this>` placeholders. Search-and-replace
them to your project's content. Common placeholders:

- `<project-name>`
- `<agent_kind_one_paragraph_description>`
- `<your-architecture-doc>`
- `<domain task type 1>`

A simple sed-driven find-and-replace works:

```bash
grep -rn "<your" . --include="*.md"
# review hits + edit each
```
