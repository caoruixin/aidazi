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
├── role-cards/                     — four agent role definitions
│   ├── deliver-agent.md
│   ├── dev-agent.md
│   ├── review-agent.md             — includes 4-parallel sub-agent orchestration
│   └── research-agent.md
├── templates/                      — eight reusable artifact templates
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
└── examples/
    └── minimal-greenfield/         — bare-bones project skeleton
```

## Versioning

`aidazi` uses semantic versioning. Consuming projects pin to a specific
tag and upgrade deliberately. Breaking changes to the governance schema,
role-card responsibilities, or compact-prompt invariants increment the
major version.

Current version: `0.1.0` (initial extraction).

## License

To be decided by the maintaining organization.
