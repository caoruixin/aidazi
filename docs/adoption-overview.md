# aidazi adoption overview

This document gives the high-level model of what `aidazi` does, what
your consumer project is responsible for, and the cognitive shape of
the framework. For step-by-step adoption walkthroughs, see:

- [`greenfield-guide.md`](greenfield-guide.md) — new project, idea →
  app
- [`brownfield-guide.md`](brownfield-guide.md) — existing project,
  incremental integration

## Mental model

`aidazi` ships **three layers** that you compose into your project:

```
┌─────────────────────────────────────────────────────────┐
│ Layer 3: domain solution (you write this)              │
│  - domain_taxonomy.md (lanes / shift / escalation)     │
│  - runtime_invariants.md (Tier-0 registry)             │
│  - eval_acceptance_bars.md (metric definitions)        │
│  - your agent code (runtime, prompts, tools, eval)     │
├─────────────────────────────────────────────────────────┤
│ Layer 2: iteration process (you instantiate this)      │
│  - milestones / sub-sprints                            │
│  - dev / deliver / review / research agent sessions    │
│  - handoffs / R-items / bad-case suite                 │
├─────────────────────────────────────────────────────────┤
│ Layer 1: framework (this repo)                          │
│  - governance/ — constitution + doc rules + briefing   │
│  - role-cards/ — 4 agent roles                         │
│  - templates/ — 8 reusable artifact templates          │
│  - schemas/ + tools/ — schema validator, hooks, trace  │
└─────────────────────────────────────────────────────────┘
```

Layer 1 is **fixed** and versioned (you pin a tag). Layer 2 is the
**process** you run on your domain. Layer 3 is **your agent**.

## What the framework does NOT decide

The framework intentionally does not decide:

- **What "lane" means in your domain.** A customer service agent has
  "wrap-around / FAQ / escalation" lanes; a shopping guide has
  "discovery / comparison / purchase" lanes; a web automation agent
  has "SOP step buckets". You define these in
  `docs/current/domain_taxonomy.md`.
- **What "Tier-0" means in your domain.** Common Tier-0 floor items
  are "no PII leak", "no fabricated facts", "no unsafe action without
  human confirmation". Your project lists them in
  `docs/current/runtime_invariants.md`.
- **What "acceptance" means in your domain.** A CS agent measures
  containment rate; a shopping agent measures purchase-completion
  rate; a web automation agent measures task-success rate. You define
  these in `docs/current/eval_acceptance_bars.md`.
- **What "good code" looks like.** The review agent walks the §4.1
  kernel for semantic discipline, but framework-level coding standards
  (style, lint, test framework) are yours.

## What the framework DOES decide

The framework decides:

- **The four-role collaboration model** — research / deliver / dev /
  review under human orchestration. You can't just "use the framework
  with one agent doing everything"; the roles enforce separation of
  planning vs implementation vs verification.
- **The constitution chain loading order** — every agent on cold
  start loads doc_governance → context_briefing → constitution +
  consumer domain context. This is enforced by `AGENTS.md`'s
  `@`-prefixed lines.
- **The anti-hardcode nine-question kernel** — non-negotiable;
  every semantic-touching change is walked through it before merge.
- **The sprint stanza four-field schema** — non-negotiable for
  semantic-touching sub-sprints; validated by JSON schema.
- **The milestone framework** — 3–5 sub-sprints per milestone, one
  acceptance review (with per-sub-sprint triggers for Tier-0 /
  forbidden / hard-fence / fix-required).
- **The self-containment invariant for compact prompts** — each
  dev/review session can be spawned by pasting a single file.

These are the **invariants**; bend them and the framework's
discipline collapses.

## Cognitive shape (what an iteration feels like)

```
Human + research agent
    ↓ proposal
Human + deliver agent
    ↓ milestone_objective.md + sprint_objective.md + compact prompt
Dev agent
    ↓ implementation + handoff + trace
[loop sub-sprints 2..N]
    ↓
Deliver agent
    ↓ compact review prompt
Review agent (optionally 4-parallel sub-reviewers)
    ↓ codex-findings.md
Deliver agent + human
    ↓ manual bad-case review (primary acceptance gate)
    ↓ close milestone, archive, plan next
```

Each arrow above is a **file write to docs/** — not a Slack message,
not a chat turn. The framework's core assumption is that agents do
NOT share chat history; all context flows through versioned docs.

## Versioning + upgrade path

`aidazi` uses SemVer:

- **Major** — breaking changes to governance schema, role
  responsibilities, or compact-prompt invariants.
- **Minor** — additive changes (new template, new tool, new role-card
  section).
- **Patch** — clarifications, typo fixes.

Consuming projects pin to a tag in their submodule:

```bash
cd framework/
git fetch --tags
git checkout v0.1.0    # pin
cd ..
git add framework/
git commit -m "[chore] pin aidazi v0.1.0"
```

Upgrade is deliberate. Read the framework's CHANGELOG (when ≥v0.2.0
exists) before bumping the tag.

## Friction expectation

The framework has known frictions (the things that took 50+ sprints
in production to discover). See
[`friction-playbook.md`](friction-playbook.md) for the catalogue +
remediation patterns. Two of the most common:

- **Programmatic eval scores drift** — composite scores are
  observation-only (per `constitution.md` §5.5), the curated bad-case
  suite (per §5.6) is the primary gate. Don't ship without a
  bad-case-suite review pass.
- **Dev sessions accidentally bundle deliver-agent files** — the
  pre-commit hook catches this. Install it.

Read the friction playbook **before** your first milestone, not after
your third.
