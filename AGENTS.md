# Repo Constitution (aidazi consumer template)

> **Template usage**: copy this file into the **root of your consuming
> project** (not into the `aidazi/` submodule itself). Edit the
> placeholders marked `{...}` to point at your domain. The `@`-prefixed
> lines auto-load the framework governance chain.

This repository builds {agent_kind_one_paragraph_description}. The
governing principles — LLM-vs-Runtime ownership boundary, iteration
rules, and forbidden list — are defined in
`framework/governance/constitution.md` §1.

The framework constitution and doc-governance rules live under
`framework/governance/`. Your domain-specific contracts live under
`docs/current/`. Active sprint scope is named in
`docs/sprint_objective.md`; closed sprints live under `docs/sprints/`
as immutable archives. Per-task reading lists live in your
`docs/current/agent_context_guide.md` (created from the framework
template).

Sprint scope is decided by the human + deliver agent through
`docs/sprint_objective.md`. A sprint that touches a semantic surface
must include the **Layer-classification + anti-hardcode stanza**
defined in `framework/governance/constitution.md` §7. Pure infra,
docs-only, config-governance, and characterization-test sprints are
exempt from the stanza.

## Agent role registry

Every agent working in this repo shares the governance chain below.
Each role has a dedicated entry doc in the framework that defines its
responsibilities, operational procedures, and handoff format.

| Role | Entry doc | Spawned by | Primary responsibility |
|------|-----------|------------|----------------------|
| **Dev agent** | `compact/sprint-NNN-dev-prompt.md` (per sub-sprint) | Human paste | Implement sub-sprint contract; run tests/eval; author handoff |
| **Deliver agent** | `framework/role-cards/deliver-agent.md` (via `framework/role-cards/deliver-activation.md`) | Human paste | Plan milestones + sub-sprints; orchestrate close; maintain bad-case suite |
| **Review agent** | `compact/M<N>-review-prompt.md` (per milestone) | Human / deliver agent | Anti-hardcode review at milestone close; targeted PR review |
| **Research agent** | `framework/role-cards/research-agent.md` | Human paste | Investigate proposals + bad-case root-cause; produce deliver-consumable solutions |

Role-specific entry docs reference governance sections by `§` number;
they do not duplicate governance content. **All context passes through
repo docs, not chat history.**

## Constitution chain

The framework governance docs below are loaded transitively for every
agent that respects this file via `@AGENTS.md`. Read order on cold
start: doc-governance first (tier model + decision rules),
context-briefing second (cold-start reading discipline), constitution
last (the operational gates).

@framework/governance/doc_governance.md

@framework/governance/context_briefing.md

@framework/governance/constitution.md

## Domain context (consumer-supplied)

The three domain-specific docs below specialize the framework for this
project. Without them, the framework is incomplete. Edit each file
before your first sprint.

@docs/current/domain_taxonomy.md

@docs/current/runtime_invariants.md

@docs/current/eval_acceptance_bars.md

## How to use this constitution

Every agent (dev, deliver, review, research) that loads `AGENTS.md`
transitively loads the framework governance chain and your domain
context. That means:

- The doc front-matter schema, source-of-truth rules, and fold-back
  cadence in `framework/governance/doc_governance.md` apply to every
  docs PR.
- The Context Pack Prompt in `framework/governance/context_briefing.md`
  applies before any non-trivial task.
- The Constitution (§1), Failure Brief Template (§2), Fix Layer
  Classification Checklist (§3), Anti-Hardcode Review Prompt (§4),
  Eval Acceptance Rules (§5), Architecture-Health Metric definitions
  (§6), sprint-objective stanza (§7), and Milestone framework (§8) in
  `framework/governance/constitution.md` apply to every change that
  touches the agent's behaviour.
- Your domain's vocabulary, Tier-0 invariants, and acceptance bars are
  defined in `docs/current/{domain_taxonomy,runtime_invariants,eval_acceptance_bars}.md`.

Sprint-specific scope lives in `docs/sprint_objective.md` (current
sub-sprint contract) and `docs/milestone_objective.md` (current
milestone north star). Both are replaced when a new sub-sprint or
milestone is promoted. The constitution itself is not edited per
sprint; it is folded back on the cadence specified in each governance
doc's `review_cadence` front-matter field.

## Two input paths

Agent evolution is driven by two input paths (operational details in
`framework/role-cards/deliver-agent.md` "Workflow inputs"):

- **Path 1 — Research-driven**: human has an architectural idea or
  wants to consume a matured R-item from `docs/action_bank.md`.
- **Path 2 — Bad-case-driven**: real-session bad case observed.

Both converge on the same downstream loop: research proposal →
deliver milestone plan → dev/review/close.

Dev and review agents execute per `docs/sprint_objective.md` and do
not need to know which input path produced it.
