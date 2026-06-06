# aidazi — Multi-Agent Iteration Framework

> **A**gentic **I**teration with **D**eliver / dev / review / research **A**gents
> through a **Z**ero-hardcode, human-orchestrated **I**teration loop.

A reusable, domain-agnostic framework for building agentic AI applications
(workflow+LLM systems and domain AI agents) with a disciplined
multi-agent collaboration model.

`aidazi` is extracted from production experience iterating an LLM-first
customer-service agent over 50+ sprints and 5 milestones. The framework
ships only the **generic** layer; all domain-specific content
(taxonomies, acceptance metrics, invariants, examples) is supplied by
the consuming project.

## What this framework gives you

1. **A 4-role multi-agent workflow** — Research / Deliver / Dev / Review
   agents under Human orchestration. Each role has a self-contained entry
   doc and clear responsibility boundaries.
2. **A constitution-chain auto-load mechanism** — agents always load the
   same governance docs on cold start, so context never depends on chat
   history.
3. **Anti-hardcode discipline** — a nine-question review kernel that
   catches semantic hardcodes (keyword / regex / if-else / per-domain
   matrix) before they ship.
4. **Layer classification before code** — a 9-layer fix routing checklist
   that prevents every failure defaulting to a runtime guard.
5. **Sprint stanza contract** — a four-field schema (layer / invariant /
   hardcode / generalization coverage) that gates whether a sprint is
   ready to start.
6. **Milestone framework** — 3–5 sub-sprints sharing a single
   architectural theme; one close review; one human-judgment acceptance
   gate.
7. **Self-contained compact prompts** — each dev/review session can be
   spawned by pasting a single file; no chat history dependency.
8. **Bundled industry-best-practice tools** — JSON schema validator for
   stanzas, pre-commit hook for path-based bundling check, trace emitter
   for observability, four-way parallel review sub-agent orchestration.

## What this framework does NOT give you

- Domain taxonomy (what a "workflow lane" means in your app)
- Acceptance metrics (success rate, escalation rate, grounding floor —
  your choice)
- Tier-0 invariants (your app's hard safety/correctness floor)
- Eval harness (the framework defines the philosophy; you bring the
  toolchain)
- Code execution environment (the framework is markdown + JSON + small
  scripts; no runtime)

These belong in the **domain solution** that consumes `aidazi`. See
[`docs/domain-adaptation.md`](docs/domain-adaptation.md) for the
placeholder checklist.

## Quick start

### New project (greenfield)

See [`docs/greenfield-guide.md`](docs/greenfield-guide.md) for the
full idea-to-app walkthrough.

```bash
# 1. Clone framework into your project
cd your-new-project/
git submodule add https://github.com/your-org/aidazi.git framework

# 2. Copy the minimal greenfield skeleton
cp -r framework/examples/minimal-greenfield/. .

# 3. Edit AGENTS.md to point at your domain context docs (3 files)
# 4. Run the adoption checklist in docs/greenfield-guide.md
```

### Existing project (brownfield)

See [`docs/brownfield-guide.md`](docs/brownfield-guide.md) for the
non-invasive incremental integration path.

## Repository layout

```
aidazi/
├── README.md                       — this file
├── AGENTS.md                       — constitution chain loader (consumer template)
├── governance/                     — three framework-core governance docs
│   ├── constitution.md             — LLM-vs-Runtime boundary + layer classification + review gates + milestone framework
│   ├── doc_governance.md           — front-matter schema, tier model, fold-back cadence
│   └── context_briefing.md         — Context Pack Prompt + cold-start reading discipline
├── role-cards/                     — five agent role definitions
│   ├── deliver-agent.md
│   ├── dev-agent.md
│   ├── review-agent.md             — includes 4-parallel sub-agent orchestration
│   ├── research-agent.md
│   └── acceptance-agent.md         — NEW v0.2 (5th role per Δ-9 / v3.2 §5)
├── process/                        — NEW v0.2 — Layer B process docs (load on demand)
│   ├── domain-discovery-process.md             — Δ-2 D1/D2/D3
│   ├── tech-architecture-decision-catalog.md   — Δ-3 8 项决策
│   ├── doc-lifecycle-rules.md                  — Δ-4 live vs intermediate
│   ├── context-passing-efficiency.md           — Δ-5 sufficient AND efficient
│   ├── typeA-runtime-architecture-skeleton.md  — Δ-6 intent gate + phase pipeline
│   ├── post-deployment-iteration.md            — Δ-9 OBS / autoloop role-split
│   ├── doc-responsibility-matrix.md            — Δ-10 8-field schema
│   ├── capability-staging-roadmap.md           — Δ-11 + Δ-17 S0..S6
│   ├── artifact-taxonomy.md                    — Δ-12 11 artifact + per-role
│   ├── stage-stable-heuristic.md               — Δ-13 git-commit heuristic
│   ├── profile-aware-maturity.md               — Δ-14 9-cell A/B/C × stage
│   ├── agent-design-elicitation.md             — Δ-15 6 Q + Part B/C/D
│   ├── agent-creation-prerequisites.md         — Δ-16 7 类前置
│   ├── common-detours-and-warnings-typeA.md    — Δ-17 P1-P4 + S1.5/S2.5/S5
│   ├── common-detours-and-warnings-typeB.md    — Δ-17-B placeholder
│   └── common-detours-and-warnings-typeC.md    — Δ-17-C placeholder
├── modules/                        — NEW v0.2 — Module template specs
│   ├── m-evaluation.md             — light spec (4 components + 4-tier)
│   ├── m-trace.md                  — conditional spec (portable shape + adaptation gate)
│   └── m-autoloop.md               — conditional spec (OBS triage + driver edges)
├── templates/                      — reusable artifact templates
│   ├── milestone_objective.md
│   ├── sprint_objective.md
│   ├── handoff.md
│   ├── codex_review.md
│   ├── failure_brief.md
│   ├── compact_dev_prompt.md
│   ├── compact_review_prompt.md
│   └── anti_hardcode_kernel.md
├── schemas/
│   └── sprint_stanza.schema.json   — JSON schema for sprint-objective stanza
├── tools/
│   ├── stanza_validator.py         — validates sprint stanza against schema
│   ├── precommit_bundling_check.sh — checks dev vs deliver path ownership
│   └── trace_emitter.py            — per-session trace.jsonl emission helper
├── docs/
│   ├── adoption-overview.md        — high-level model
│   ├── greenfield-guide.md         — idea → app step-by-step
│   ├── brownfield-guide.md         — existing project incremental integration
│   ├── domain-adaptation.md        — placeholder checklist for domain teams
│   ├── industry-mapping.md         — framework vs industry 2026 patterns
│   └── friction-playbook.md        — known frictions + remediation patterns
├── examples/
│   ├── minimal-greenfield/         — bare-bones project skeleton
│   └── csagent-reference/          — NEW v0.2 — §L worked-example snapshot (read-only after first instantiation)
│       ├── README.md
│       ├── timeline-54-day.md      — Δ-17 (g) worked example
│       ├── discovery/              — D1/D2/D3 placeholder
│       ├── decisions/              — Δ-3 8-decision placeholder
│       ├── runtime-skeleton/       — Δ-6 phase pipeline placeholder
│       ├── m-eval/                 — 4-tier instance placeholder
│       └── m-trace/                — trace schema instance placeholder
└── archive/
    └── 2026-06-06-v3.2-snapshot.md — frozen v3.2 plan archive (source of v0.2 content)
```

## Versioning

`aidazi` uses semantic versioning. Consuming projects pin to a specific
tag and upgrade deliberately. Breaking changes to the governance schema,
role-card responsibilities, or compact-prompt invariants increment the
major version.

Current version: `0.2.0-from-v3.2-plan` (P0 additive integration of v3.2 plan; v0.1.0 content preserved).

## License

To be decided by the maintaining organization.
