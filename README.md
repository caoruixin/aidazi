# aidazi — multi-agent framework for LLM-first software delivery

**English** | [中文](README.zh-CN.md)

**v4.0.0** — 2026

aidazi is a framework for delivering software with a multi-agent team where the LLM is responsible for soft semantic decisions and a deterministic runtime owns hard kernel-level invariants. It defines a 5-role chain (Research / Deliver / Dev / Code Reviewer / Acceptance) + a human Customer + the governance + process docs + templates + schemas to run them coherently.

> **Adopting aidazi?** Feed `ONBOARDING.md` to your coding agent (Claude Code / Codex / Cursor) — it drives an interactive, idempotent, non-destructive, audited one-time install into your codebase.

## The framework at a glance (top-down)

aidazi reads top-down. One governing idea sits at the apex; everything below exists to make it operational.

**The governing idea**

> Let the LLM own the soft, semantic decisions; let a deterministic runtime own the hard, kernel-level invariants; and put five roles with *real* boundaries between them so the two never leak into each other.

Everything else is scaffolding for that one sentence. It rests on five pillars.

### Pillar 1 — The ownership boundary: *who decides what*

The line between LLM judgment and runtime guarantee is drawn explicitly, not left to chance.

- **LLM owns** (soft): user goal, intent / topic hypothesis, drift detection, next-action choice, escalation posture, customer-facing wording.
- **Runtime owns** (hard): tool schemas, capability / permission boundary, PII & safety floor, grounding floor, budget / timeout, idempotency, persistence, the trace & eval contract.
- A **forbidden list** keeps semantic decisions out of code: no keyword / regex / if-else matching for soft decisions, no eval phrases hard-coded into prompts or runtime, a single abstraction layer per agent.
- Source: `governance/constitution.md` §1.

### Pillar 2 — The 5-role chain: *real walls, not labels*

| Role | Owns | Gate |
|---|---|---|
| **Research** | the intake; authors the `closure_contract` | Gate 1: signed brief |
| **Deliver** (Tech Lead) | planning, orchestration, close — never writes code | — |
| **Dev** | implementation; no scope authority | — |
| **Code Reviewer** | "is the code well-built?" + the anti-hardcode kernel | code-side gate |
| **Acceptance** | "did we build the right thing?" vs the contract | Gate 2: ship / no-ship |
| **Customer** (human) | signs Gate 1, reads Gate 2, owns mandatory checkpoints | the two gates |

The load-bearing invariant: **no role grades its own work.** Acceptance is *structurally isolated* — it may not be spawned from Research, Deliver, or Dev — so the ship verdict can't be biased toward the team that produced the work. Source: `role-cards/`, `governance/constitution.md` §3.

### Pillar 3 — Two loops, named apart: *self-improvement vs delivery*

- **Auto Loop** (Concept 1, Type A only): the product agent improves *itself* — prompts, skills, thresholds. `modules/m-autoloop.md`.
- **Delivery Loop** (Concept 2, all tracks): the multi-agent *team* converges on what the customer asked for. `process/delivery-loop.md` (Δ-18).
- They compose (vertical depth × horizontal flow) and must never be conflated in adopter docs.

### Pillar 4 — The process layer: *~25 portable Δ patterns*

Each Δ is one small, portable pattern, loaded on demand by the role that needs it: domain discovery (Δ-2), the tech-decision catalog (Δ-3), the runtime skeleton + 6-primitive trace DSL (Δ-6), post-deployment / OBS triage (Δ-9), maturity-by-track (Δ-14), the Delivery Loop spec (Δ-18), and the rest. Source: `process/`.

### Pillar 5 — The evidence spine: *verification you can measure*

- A **4-tier eval pyramid**: `tier1_smoke` (deterministic) → `tier2_scenario` (semantic judge) → `tier3_target_set` (contract-anchored) → `tier4_shadow` (held-out generalization).
- A **6-primitive `trace_check` DSL** — `tool_call_present`, `tool_call_order`, `slot_collected`, `session_flag`, `any_of`, `all_of` — whose grammar *structurally rejects* keyword / message-content matching.
- **F5 evidence**: Acceptance judges from execution artifacts, never from code inspection. Source: `modules/m-evaluation.md`.

**How to read down the pyramid:** start at the always-loaded **Layer A** (`governance/` — constitution, doc governance, context briefing), then pull **Layer B** (`process/` Δ docs) on demand per role, keep your live **state ledgers** in your own repo, and freeze per-sprint **prompt artifacts** under `compact/`. The full doc tree is indexed in `governance/constitution.md` §11.

## What aidazi IS

- A **constitution** (`governance/constitution.md`) defining LLM-vs-Runtime ownership boundaries + a forbidden list (no keyword/regex matching for semantic decisions, no eval phrase encoding into code, etc.).
- A **5-role chain** with explicit boundary invariants — no role self-grades; Acceptance is structurally isolated from Deliver/Dev to avoid bias loops.
- A **process layer** of ~25 numbered Δs (domain discovery, decision catalogs, runtime skeleton, OBS triage, bad-case lifecycle, etc.) — each Δ is a small portable process pattern.
- **Two loops** named distinctly: **Auto Loop** (Concept 1; Type A agent self-improvement) vs **Delivery Loop** (Concept 2; Δ-18 multi-agent team delivery). They compose; they don't conflict.
- An **orchestrator pattern** (Δ-18 Delivery Loop) — optional state machine + spawn functions + checkpoint inbox + scope envelope + F5 evidence + calibration gate. Adopters who want automation use it; pure human-paste adopters keep the chain without the automation.
- A **Campaign Loop** (P-B) over the Delivery Loop — from a signed milestone backlog it auto-drives the WHOLE goal to completion (以终为始), running Acceptance at each milestone close and pausing only at human gates. Wired entrypoint: `engine-kit/scheduling/run_loop.py --campaign` (`process/campaign-loop.md`).
- A **Quick-Fix lane** (`process/quickfix-lane.md`, `QUICK-FIX.md`) — a human-explicit, per-session maintenance lane for small non-behavioral fixes that runs OUTSIDE any loop (so there are no checkpoints to skip, and it may never be used to route around them). Default behavior stays Full; only an explicit human launch activates it, and the agent never self-downgrades. *Status: **usable on Claude Code and Codex** — the `claude_code` (`archive/2026-06-22-quickfix-claude-code-e2e-evidence.md`) and `codex` (`archive/2026-06-22-quickfix-codex-e2e-evidence.md`, codex 0.134.0) adapters are both `supported` with recorded real-launch cold-start evidence for a correctly-wired adopter; `kimi_code` is `unsupported`. The launch gate is strict: anything not `supported` **fails closed**.*
- A **role-skill model** (`process/role-skill-model.md`) — roles are accountability boundaries; industry capability packs (Agent Skills / SKILL.md standard, coding-agent subagent libraries) mount INSIDE roles as role skills or intra-role fan-out, never as new chain roles. One exemplar packaged skill ships under `skills/`.
- A **two-direction fold-back** (adopter → framework lessons; framework → adopter releases) so the framework evolves from real adopter experience, not committee decree.

## What aidazi is NOT

- Not a runtime — there is no "aidazi server" you deploy. The runtime is YOUR project's runtime; aidazi shapes how you build it.
- Not a single tool — backing coding-agents (Claude Code / Codex / other) are configurable per role per charter.
- Not opinionated on domain — the framework is track-aware (Type A AI agent / Type B agentic workflow / Type C demo / Type A+B hybrid) but domain-agnostic.
- Not an LLM eval harness — but it specifies a 4-tier eval pyramid + 6-primitive trace_check DSL (`modules/m-evaluation.md`) that adopters instantiate.

## How to apply aidazi to your codebase

The fastest way to understand adoption is the one worked example that ships filled-in: **`examples/minimal-greenfield/`** — a complete, minimal Type A instance called the **Acme Returns Bot** (a customer-service agent that answers *"can I get a refund on this order?"* against policy). Everything below maps to a real file in that example.

### Step 0 — Pick your track

| Track | What it is | Pick it when |
|---|---|---|
| **Type A** | an agent that reasons adaptively per turn | a CS agent, an assistant — decisions made live |
| **Type B** | an agentic workflow running a fixed SOP with per-step checks | a defined pipeline with verification gates |
| **Type A+B** | an LLM-controlled top loop over an SOP runner | adaptive control *and* structured execution |
| **Type C** | a demo / POC where demonstrability beats coverage | a showcase leaning on off-the-shelf skills |

Your track decides which Δ patterns are necessary now vs deferred (`process/profile-aware-maturity.md`, Δ-14). Acme Returns Bot is Type A.

### Greenfield (new project) — copy the example, swap the domain

1. **Copy `examples/minimal-greenfield/` as your starting tree** and edit `AGENTS.md` §1: `project_name`, `adopter_track`, `framework_version`. `AGENTS.md` is what every fresh role session reads first; it `@`-includes the governance chain and your state ledgers.
2. **Run elicitation as the Research role** (`process/agent-design-elicitation.md`, Δ-15) → write a research brief like `docs/research-briefs/RB-001-*.md`. Its heart is the **`closure_contract`**: a *positive shape* + an *anti-pattern* + *anchor phrases* (example language, **not** keyword matchers). The Customer signs it — that's **Gate 1**.
3. **Author the three domain contracts** under `docs/current/` (the domain-specific counterpart to the constitution, loaded at every cold-start):
   - `domain_taxonomy.md` — entities, use-cases, vocabulary.
   - `runtime_invariants.md` — your Tier-0 hard rules (Acme's: eligibility is a tool call, never an LLM guess; no cross-customer PII; idempotent processing).
   - `eval_acceptance_bars.md` — KPI thresholds + safety floors (Acme's: ≥ 0.95 eligibility accuracy, ≤ 0.02 wrong-containment).
4. **Plan as the Deliver role**: `docs/milestone_objective.md` + `docs/sprint_objective.md`, and seed `docs/action_bank.md` (live backlog) + `docs/10-handoff.md` (cold-start carrier).
5. **Build → review**: Dev implements from a frozen, self-contained prompt under `compact/` (Dev never reads `eval/bad_cases/` — the contamination rule); Code Reviewer guards the invariants + anti-hardcode kernel.
6. **Accept at milestone close (Gate 2)**: the Customer spawns the Acceptance Agent in a *fresh* session; it runs the bad-case suite (`eval/bad_cases/`) and judges delivered behavior against the signed `closure_contract`, writing a verdict to `docs/acceptance-reports/`. On `fix_required`, a human-confirm checkpoint decides the route back.
7. **(Optional) automate with the orchestrator** (`templates/mission-charter.yaml`, Δ-18) only if you want machine-driven dispatch. Pure human-paste with the 5-role chain is a complete, valid adoption.

### Brownfield (existing project) — reconcile, don't rip-and-replace

1. **Inventory first, change nothing.** Note your track, your existing governance / eval docs, and — most importantly — *where semantic decisions currently live* (LLM-owned or hardcoded). Hardcoded soft-decisions predict the most friction.
2. **Start with the Acceptance gate** — the highest-value, lowest-disruption first move. Write one `closure_contract` for your current milestone, then at close spawn Acceptance in a fresh session (never from Deliver / Dev) and read its verdict. It answers the question your existing process can't: *"the code is clean, but did we build the right thing?"*
3. **Adopt the rest gradually** — Code Reviewer (anti-hardcode kernel) → Acceptance → Research (signed briefs) → Deliver → Dev (self-contained compacts, the biggest day-to-day change).
4. **Record every divergence** in `docs/current/adoption-state.md` (from `templates/adoption-state-template.md`): mark each Δ `at-spec` / `partial` / `divergent` / `not-applicable`, with one sentence of rationale per divergence.

### If you only do three things

1. Write one **`closure_contract`** and run an independent **Acceptance** pass against it.
2. Adopt the **5-role chain** — the boundaries are what make the Acceptance verdict trustworthy.
3. Author the **three domain contracts** — they give every role a reliable, shared domain context.

### The other examples (build-triggered references)

- **`examples/csagent-reference/`** — Type A full-lifecycle reference; populated when a Type A adopter needs the deep walk-through. Until then, minimal-greenfield is the live Type A reference.
- **`examples/hermes-reference/`** — Type A+B hybrid (Delivery Loop *and* Auto Loop with an SOP layer); build-triggered.
- **`examples/fortunes-reference-placeholder/`** — Type C demo placeholder; awaits the first completed Type C lifecycle.

## aidazi vs. Loop Engineering

### What loop engineering is

"Loop engineering" is the emerging name — coined by practitioners around Claude Code (Boris Cherny, Addy Osmani, Peter Steinberger) — for a shift in how people work with coding agents: **stop prompting the agent turn-by-turn; design the system that prompts it for you.** Cherny's line is *"I don't prompt Claude anymore. I have loops running that prompt Claude."* Osmani frames it as *"replacing yourself as the person who prompts the agent — you design the system that does it instead."* Steinberger puts the imperative bluntly: *"you should be designing loops that prompt your agents."*

It sits one level above two earlier ideas:

- **Prompt engineering** optimizes a single request.
- **Harness engineering** equips a single agent run — its tools, context, sandbox.
- **Loop engineering** designs the *system that keeps poking agents on a schedule* — discovering work, delegating, verifying, iterating, with no human in the turn-by-turn loop.

The literature converges on a recurring set of building blocks:

| # | Loop-engineering building block | Purpose |
|---|---|---|
| 1 | **Automations / scheduling** — "the heartbeat" | recurring discovery + triage with no human kicking it off |
| 2 | **Worktrees** | isolated checkouts so parallel agents don't collide |
| 3 | **Skills** (`SKILL.md`) | externalized conventions so agents don't re-derive context each run |
| 4 | **Plugins & connectors** (MCP) | loops *act* (open PRs, update tickets), not just suggest |
| 5 | **Sub-agents** (maker / checker) | a second agent verifies the first — no self-grading |
| + | **Persistent state** (`STATE.md`) | a memory spine that survives context resets across cycles |

### The convergence: aidazi arrives at the same architecture

aidazi was designed independently — its lineage is multi-agent software *delivery*, not coding-agent tooling — yet it lands on the same building blocks, because both answer one question: *how do you run autonomous agent work without it drifting?* The mapping is near one-to-one:

| Loop-engineering block | aidazi mechanism |
|---|---|
| Automations / scheduling | **Δ-18 Delivery Loop** orchestrator (state machine + spawn functions + checkpoint inbox) and the **Auto Loop** (`modules/m-autoloop.md`) |
| Worktrees / isolation | per-task **scope envelope** + per-role **charters** + intra-role fan-out (`process/role-skill-model.md`) |
| Skills | the **role-skill model** + packaged role skills under `skills/` (same Agent Skills / `SKILL.md` standard) |
| Plugins & connectors | backing coding-agents configurable **per role per charter** (`charter.tooling.<role>.agent_kind`); deferred tooling tracked in `tools/` |
| Sub-agents (maker / checker) | the **5-role chain** with **Acceptance structurally isolated** from Deliver/Dev — formalized so *no role grades its own work* |
| Persistent state | the **handoff carrier** + `adoption-state` + `action_bank` ledgers + F5 evidence artifacts |

In one line: **loop engineering describes this as an emergent practice; aidazi specifies it as a governed framework.**

### Where aidazi goes further: turning warnings into structure

The most striking thing about the loop-engineering literature is how candid it is about the danger it creates — and how it leaves the remedy to the reader's discipline. aidazi's distinctive contribution is to make that discipline *structural* rather than advisory. Map the canon's three warnings to aidazi's structural answers:

| Loop-engineering warning | aidazi's structural answer |
|---|---|
| *"Unattended loops make unattended mistakes"* — verification stays human | the **Customer** is a *role*, not a fallback; **Gate 1** (signed brief) and **Gate 2** (acceptance) are checkpoints the loop **cannot self-close** (`process/customer-checkpoints.md`) |
| *"Comprehension debt accelerates"* — you ship code you didn't write | the **`closure_contract`** fixes intended behavior up front; **Acceptance** judges delivered behavior against it from **F5 execution evidence**, not code inspection — so "it ran" never substitutes for "it's right" |
| *"The comfortable posture is the dangerous one"* — automation invites passivity | the **constitution** + **forbidden list** encode *which* judgments may never be automated into keyword/regex/if-else; a **calibration gate** must pass before Acceptance may run autonomously at all |

Beyond those three, aidazi adds what the loop-engineering discourse does not yet name:

- **A constitution, not a vibe.** `governance/constitution.md` fixes the LLM-vs-Runtime ownership boundary. Loop engineering says "keep your judgment"; aidazi encodes *which* judgments belong to the model and which to the deterministic kernel.
- **Two loops, named apart.** The discourse blurs "the loop." aidazi separates **Auto Loop** (agent self-improvement) from **Delivery Loop** (team delivery) with explicit naming discipline (`docs/two-loops-explainer.md`) so they compose instead of colliding.
- **Verification is itself measured.** Beyond a maker/checker split, the **4-tier eval pyramid** + **6-primitive `trace_check` DSL** (`modules/m-evaluation.md`) make "the checker" auditable — and the DSL grammar structurally forbids the keyword-matching shortcut.
- **The framework folds back.** A two-direction protocol (`process/fold-back-protocol.md`) evolves the framework from real adopter lessons, not one-off loop tweaks.

### How they relate — different altitudes, not competitors

- **Loop engineering** is the *insight*: the leverage point moved from the prompt to the system that prompts.
- **aidazi** is the *operating discipline* for that system: the roles, boundaries, checkpoints, and governance that keep an autonomous loop honest.

Practical reading:

- **Adopting loop engineering and feeling the drift?** aidazi is one concrete answer to *"okay — now how do I keep it under control?"* Start with the Acceptance gate (see *How to apply* above).
- **Already running aidazi?** The loop-engineering canon is independent validation that the chain, the maker/checker split, and the skills model are where the industry is arriving on its own — and a good source of tooling ideas (worktrees, scheduling, connectors) to mount *inside* your roles, never as new chain roles (`process/role-skill-model.md`).

> **Takeaway:** Loop engineering names the opportunity — *replace yourself as the prompter.* aidazi supplies the part the loop-engineering literature says you need but stops short of giving: the constitution, the human checkpoints, and the boundary invariants that keep the loop from quietly going wrong.

**Further reading:** Addy Osmani, [*Loop Engineering*](https://addyosmani.com/blog/loop-engineering/) · The New Stack, [*Loop Engineering*](https://thenewstack.io/loop-engineering/) · Cobus Greyling, [*Loop Engineering*](https://cobusgreyling.substack.com/p/loop-engineering).

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
