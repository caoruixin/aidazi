# aidazi — multi-agent framework for LLM-first software delivery

**v4.0.0** — 2026

aidazi is a framework for delivering software with a multi-agent team where the LLM is responsible for soft semantic decisions and a deterministic runtime owns hard kernel-level invariants. It defines a 5-role chain (Research / Deliver / Dev / Code Reviewer / Acceptance) + a human Customer + the governance + process docs + templates + schemas to run them coherently.

> **Adopting aidazi?** Feed `ONBOARDING.md` to your coding agent (Claude Code / Codex / Cursor) — it drives an interactive, idempotent, non-destructive, audited one-time install into your codebase.

## What aidazi IS

- A **constitution** (`governance/constitution.md`) defining LLM-vs-Runtime ownership boundaries + a forbidden list (no keyword/regex matching for semantic decisions, no eval phrase encoding into code, etc.).
- A **5-role chain** with explicit boundary invariants — no role self-grades; Acceptance is structurally isolated from Deliver/Dev to avoid bias loops.
- A **process layer** of ~25 numbered Δs (domain discovery, decision catalogs, runtime skeleton, OBS triage, bad-case lifecycle, etc.) — each Δ is a small portable process pattern.
- **Two loops** named distinctly: **Auto Loop** (Concept 1; Type A agent self-improvement) vs **Delivery Loop** (Concept 2; Δ-18 multi-agent team delivery). They compose; they don't conflict.
- An **orchestrator pattern** (Δ-18 Delivery Loop) — optional state machine + spawn functions + checkpoint inbox + scope envelope + F5 evidence + calibration gate. Adopters who want automation use it; pure human-paste adopters keep the chain without the automation.
- A **role-skill model** (`process/role-skill-model.md`) — roles are accountability boundaries; industry capability packs (Agent Skills / SKILL.md standard, coding-agent subagent libraries) mount INSIDE roles as role skills or intra-role fan-out, never as new chain roles. One exemplar packaged skill ships under `skills/`.
- A **two-direction fold-back** (adopter → framework lessons; framework → adopter releases) so the framework evolves from real adopter experience, not committee decree.

## What aidazi is NOT

- Not a runtime — there is no "aidazi server" you deploy. The runtime is YOUR project's runtime; aidazi shapes how you build it.
- Not a single tool — backing coding-agents (Claude Code / Codex / other) are configurable per role per charter.
- Not opinionated on domain — the framework is track-aware (Type A AI agent / Type B agentic workflow / Type C demo / Type A+B hybrid) but domain-agnostic.
- Not an LLM eval harness — but it specifies a 4-tier eval pyramid + 6-primitive trace_check DSL (`modules/m-evaluation.md`) that adopters instantiate.

## Read order

If you're new to aidazi, read in this order:

1. **This file** (you're here).
2. `docs/adoption-overview.md` — the mental model: what aidazi does and does not decide.
3. `docs/two-loops-explainer.md` — Auto Loop vs Delivery Loop naming discipline (Constitution §1.7-E).
4. `governance/constitution.md` — the always-loaded core.
5. `governance/doc_governance.md` — front-matter schema + tier model + edit rules.
6. `governance/context_briefing.md` — cold-start reading discipline + Context Pack Prompt.
7. Per-track adoption guide:
   - Greenfield (new project): `docs/greenfield-guide.md`.
   - Brownfield (existing project): `docs/brownfield-guide.md`.
8. `docs/directory-taxonomy.md` — fast lookup for "where does this content go?"
9. The 5 role cards under `role-cards/` — adopt one per session as needed.
10. The Δ docs under `process/` — load on demand by role.

The framework's full doc tree is detailed in `governance/constitution.md` §11.

## Repository layout

```
aidazi/
├── README.md                    — this file
├── AGENTS.md                    — consumer-side template
├── governance/                  — Layer A (always-load)
│   ├── constitution.md
│   ├── doc_governance.md
│   └── context_briefing.md
├── process/                     — Layer B (on-demand by role)
│   ├── delivery-loop.md         — Δ-18 (Concept 2)
│   ├── customer-checkpoints.md  — human-side gate catalog
│   ├── self-governance.md       — bloat prevention mechanics
│   ├── fold-back-protocol.md    — adopter ↔ framework cadence
│   └── ... (~22 more Δ + promoted process docs)
├── role-cards/                  — 5 agent role cards
│   ├── research-agent.md
│   ├── deliver-agent.md
│   ├── dev-agent.md
│   ├── code-reviewer-agent.md
│   └── acceptance-agent.md
├── templates/                   — adopter-copyable templates
│   ├── mission-charter.yaml
│   ├── anti-hardcode-review-kernel.md
│   ├── compact-dev-prompt.md
│   ├── compact-review-prompt.md
│   ├── compact-acceptance-prompt.md
│   ├── compact-research-brief.md
│   ├── compact-codex-rebuttal-prompt.md
│   ├── deliver-close-taxonomy.md
│   ├── adoption-state-template.md
│   ├── lessons-learned-template.md
│   ├── sprint-objective.md
│   ├── milestone-objective.md
│   └── handoff-template.md
├── skills/                      — packaged role skills (Agent Skills standard; SKILL.md)
│   └── anti-hardcode-review-kernel/  — exemplar (normative source stays in templates/)
├── schemas/                     — JSON schemas for verdict shapes
│   ├── mission-charter.schema.json
│   ├── review-verdict.schema.json
│   ├── deliver-close-verdict.schema.json
│   ├── deliver-plan-fix.schema.json
│   ├── acceptance-verdict.schema.json
│   ├── research-brief.schema.json
│   ├── case-spec.schema.json
│   ├── adoption-state.schema.json
│   └── sprint_stanza.schema.json
├── modules/                     — module specs
│   ├── m-evaluation.md          — 4-tier pyramid + 6-primitive DSL
│   ├── m-trace.md               — portable trace shape
│   └── m-autoloop.md            — Concept 1 (Auto Loop)
├── docs/                        — Application Guide
│   ├── adoption-overview.md
│   ├── two-loops-explainer.md
│   ├── directory-taxonomy.md
│   ├── friction-playbook.md
│   ├── greenfield-guide.md
│   ├── brownfield-guide.md
│   ├── domain-adaptation.md
│   ├── industry-mapping.md
│   └── application-funnel.md
├── examples/                    — worked instances (read-only after snapshot)
│   ├── minimal-greenfield/      — working consumer template
│   ├── csagent-reference/       — Type A donor snapshot (build-trigger)
│   ├── hermes-reference/        — Type A+B hybrid snapshot (build-trigger)
│   └── fortunes-reference-placeholder/  — Type C placeholder
├── lessons/                     — adopter → framework fold-back inbox (.gitkeep until first lesson)
├── tools/                       — optional convenience scripts (OQ-V4-009 resolved; governance validators ship in engine-kit/validators/)
└── archive/                     — v3.2 + v4 design-history snapshots (read-only)
```

## Versioning

Framework cuts versioned releases:

- `v4.0.0` — first stable v4 release.
- `v4.0.x` — patch releases (typo fixes, doc clarifications).
- `v4.x.0` — minor releases (Δ additions or extensions; backwards-compatible).
- `v5.0.0` — major release (Δ removals, role-chain changes, breaking front-matter shape changes).

Adopters consume on their own cadence (no auto-update). See `process/fold-back-protocol.md` §1.2 for the framework → adopter direction.

## Contributing

This is a framework. Contributing means:

- **Adopting it**: try the framework on a real project; file lessons (`templates/lessons-learned-template.md`) when something doesn't fit your context.
- **Folding back**: at the framework's fold-back sub-sprint cadence (per `process/fold-back-protocol.md` §2), the framework maintainer reviews lessons and incorporates load-bearing patterns into Δ revisions.
- **Worked examples**: when you've completed a milestone or full lifecycle, the framework maintainer may invite you to contribute a snapshot to `examples/`.

NOT contributing:
- Mid-cycle pull requests to framework docs without going through a fold-back. Constitution §8 governance-editing-discipline applies.
- Edits to `examples/<ref>/` after first snapshot — read-only per Δ-7.

## License

See LICENSE file (when present).

---

End of README.
