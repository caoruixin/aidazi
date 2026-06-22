---
title: Adoption overview — the aidazi mental model
doc_tier: application-guide
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 18KB
split_trigger: if §4 "what the framework decides" grows past 6KB, split the per-track detail to a process/ doc and keep the table here
notes: >
  Adopter-facing entry doc — the first thing a new adopter reads after README.
  Establishes the cognitive shape: the 5-role chain, the three decision layers
  (framework decides / adopter decides at adoption / per-milestone decides),
  what the framework decides vs leaves to the adopter, the two loops, and
  versioning. Points onward to the greenfield/brownfield guides. Does NOT
  duplicate the constitution; it frames it.
---

# Adoption overview — the aidazi mental model

This is the orientation doc. Read it after `README.md` and before the per-track guides. Its job is to install the mental model so the rest of the framework reads as a coherent whole rather than a pile of docs.

If you remember only one sentence: **aidazi is a way to run a multi-agent software-delivery team where the LLM owns soft semantic decisions, a deterministic runtime owns hard invariants, and five roles with real boundaries keep the two from leaking into each other.**

## §1 The 5-role chain (the cognitive shape)

The framework's spine is five agent roles plus a human Customer. Each role is an **accountability boundary** — it owns a specific artifact, answers a specific question, and is structurally prevented from grading its own work.

```
Customer (human)
   │  gate 1: signs the brief                       gate 2: signs ship/no-ship
   ↓                                                          ↑
Research ──→ Deliver ──→ Dev ──→ Code Reviewer            Acceptance
(intake     (Tech Lead;  (codes; (anti-hardcode +         (peer of Research;
 gate;       plans +      no      correctness; code-side   judges delivered
 closure_    orchestrates scope)  gate)                    behaviour vs the
 contract)   + closes)                                     closure_contract;
                                                           outcome gate)
```

- **Research** asks *"what should we build?"* and writes the `closure_contract` (the milestone's success definition).
- **Deliver** (Tech Lead) asks *"how do we sequence and close it?"* — plans milestones/sub-sprints, orchestrates, runs the close conversation. Does **not** write code.
- **Dev** asks *"how do I implement this sub-sprint?"* — codes within a self-contained prompt; has no scope authority.
- **Code Reviewer** asks *"is the code well-built?"* — anti-hardcode kernel + correctness lens; read-only.
- **Acceptance** asks *"did we build the right thing?"* — judges delivered behaviour against the closure_contract Research authored. It is the **peer of Research** and is structurally isolated from Deliver/Dev so its verdict can't be a rubber stamp.

The two questions at the bottom — "well-built?" (Code Reviewer) and "right thing?" (Acceptance) — are **different gates** and both run. A clean code review with a failing acceptance means you built brittle-free code that solves the wrong problem; the reverse means you solved the right problem with code that won't survive. Keeping them separate is the framework's core value-add.

Full role definitions: `role-cards/`. Boundary invariants: `governance/constitution.md` §3.4. The human Customer's gate catalog: `process/customer-checkpoints.md`.

## §2 The three decision layers

Adopters get confused about "what do I decide vs what does the framework decide?" The answer is layered:

| Layer | Who decides | When | Examples | Where it lives |
|---|---|---|---|---|
| **Layer 1 — Framework** | The framework (you inherit it; you don't edit it) | Once, by adopting | LLM-vs-runtime ownership; the 5-role boundaries; the forbidden list; MANDATORY_CHECKPOINTS; calibration gate | `governance/constitution.md` (always-loaded; @-included) |
| **Layer 2 — Adoption** | The adopter, at onboarding | Once per project (revisited at fold-back) | Track (A/B/C/A+B); profile depth; charter values; the three domain contracts; which defaults you override | `docs/current/` + `charter.yaml` + `docs/current/adoption-state.md` |
| **Layer 3 — Per-milestone** | The roles, in flight | Every milestone/sprint | Scope IN/OUT; sub-sprint sequence; bad-case suite additions; close verdicts | `docs/research-briefs/`, `docs/milestone_objective.md`, `docs/sprint_objective.md`, etc. |

Layer 1 is **non-negotiable** — it's what makes one aidazi project recognisable to someone coming from another. Layer 2 is **your project's identity** — domain, scale, automation level. Layer 3 is **the day-to-day work**.

The split exists so the framework can be opinionated where opinions are load-bearing and accommodating everywhere else (see §4).

## §3 The doc layers (where content lives)

Orthogonal to the decision layers, the framework's files sort into four content layers (`governance/constitution.md` §1.1):

- **A — Constitution** (`governance/`): always-loaded; timeless ownership + forbidden list.
- **B — Process** (`process/`): on-demand by role; one doc per process pattern (the numbered Δs).
- **C — State ledgers** (adopter repo): live state — `action_bank.md`, `handoff.md`, `adoption-state.md`.
- **D — Prompt artifacts** (adopter repo `compact/`): per-sprint self-contained job specs.

When you're unsure where a piece of content belongs, `docs/directory-taxonomy.md` is the fast lookup.

## §4 What the framework decides vs what you decide

This is the question adopters most want answered up front. The framework draws a sharp line between **hard requirements** (it breaks if you violate them) and **suggested defaults** (good starting points you override with rationale). Full registry: `governance/constitution.md` §7.0.

**The framework decides (hard — you may NOT override):**

- The LLM-vs-runtime ownership boundary and the §1.7 forbidden list (no keyword/regex for soft semantic decisions; no eval-phrase encoding; etc.).
- The 5-role boundary invariants (§3.4): no self-grading; Acceptance spawn isolation; Code Reviewer ≠ Acceptance; Research–Acceptance contract symmetry; Deliver-no-code; intra-role skills inherit the role's boundary.
- The 9 MANDATORY_CHECKPOINTS (if you adopt the Δ-18 Delivery Loop orchestrator): charter may ADD, never bypass.
- The Acceptance judge calibration gate for autonomous mode.

**You decide (suggested defaults — override in `adoption-state.md` with a reason):**

- Track and profile depth (Type A/B/C/A+B; how much of each Δ you adopt now vs later).
- Backing harness × provider/model per role (`charter.tooling.<role>` execution facet — `harness`/`provider`/`model`, or legacy `agent_kind`; e.g. Claude Code↔Anthropic, Codex↔OpenAI, or `headless` against an OpenAI-compatible endpoint for DeepSeek/Kimi/other) and any role skills. Full binding contract: `process/role-configuration-contract.md`; skills: `process/role-skill-model.md`.
- All numeric thresholds (size targets, calibration thresholds, token budgets, cadences).
- Whether to run the orchestrator at all, or stay pure-human-paste.
- Your domain contracts, KPIs, scope boundaries.

The override path is always the same: write a `status: divergent` row in `docs/current/adoption-state.md` with a `rationale`, keep going, and the framework reviews accumulated divergences at fold-back (`process/fold-back-protocol.md`).

## §5 The two loops (name them distinctly)

aidazi names two different "loop" concepts that adopters routinely conflate. They are orthogonal and can coexist:

- **Auto Loop** (Concept 1) — a Type A product agent improving *itself* (its prompts, skills, thresholds). Subject = the product. Lives in `modules/m-autoloop.md`.
- **Delivery Loop** (Concept 2; Δ-18) — the multi-agent *team* delivering a milestone and self-correcting when Acceptance finds a gap. Subject = the team. Lives in `process/delivery-loop.md`.

One-liners: Auto Loop = *"my agent gets better at being itself."* Delivery Loop = *"my dev team converges on what the customer asked for."*

Conflating them in your docs is a §1.7-E framework breach — not pedantry, but because they have different debugging implications. Full disambiguation: `docs/two-loops-explainer.md`.

**A third, loop-independent concept — the Quick-Fix lane.** Distinct from both loops above, the **Quick-Fix lane** (`process/quickfix-lane.md`) is a human-explicit, per-session maintenance lane for small non-behavioral fixes that runs *outside* any loop. Name it distinctly too (§1.7-E): it is not the Auto Loop, not the Delivery Loop, and it never skips MANDATORY_CHECKPOINTS — it never enters a loop in the first place. Default behavior stays Full; the agent never self-downgrades. *Status: **usable on Claude Code and Codex** — `claude_code` and `codex` are both `supported` (recorded real-launch cold-start evidence) for a correctly-wired adopter; `kimi_code` is `unsupported`. The launch gate is strict: anything not `supported` fails closed. See `QUICK-FIX.md`.*

## §6 Tracks (what kind of thing are you building?)

The framework is track-aware but domain-agnostic. Four tracks:

- **Type A** — AI agent that reasons adaptively per turn (e.g., a customer-service agent).
- **Type B** — agentic workflow that follows a defined SOP sequence with per-step verification.
- **Type C** — demo/POC where customer-demonstrability beats coverage; leans on off-the-shelf skills.
- **Type A+B hybrid** — an LLM-controlled top loop *and* an SOP-runner underneath.

Your track sets which Δs are necessary now vs deferred. The per-track necessary sets + the profile decision tree live in `process/profile-aware-maturity.md` (Δ-14). The five role boundaries are identical across all tracks; only depth and frequency change (e.g., Type C runs Acceptance every demo).

## §7 Where to go next

Pick your adoption shape:

- **Greenfield** (new project, or existing codebase with no agent yet) → `docs/greenfield-guide.md`. Fast inherit: the framework provides scaffolding + defaults; you fill domain values via the Phase 1-5 funnel (`docs/application-funnel.md`).
- **Brownfield** (existing project with its own norms/agent work) → `docs/brownfield-guide.md`. Human-led: inventory → decide what to inherit vs preserve → reconcile in `adoption-state.md` → validate.

Then, regardless of shape:

- `docs/domain-adaptation.md` — the three domain contracts every adopter fills.
- `docs/directory-taxonomy.md` — where each kind of content goes.
- `docs/friction-playbook.md` — read BEFORE your first milestone, not after your third.
- `docs/industry-mapping.md` — if you're coming from BMAD / LangGraph / AutoGen / a Claude Code subagent library and want the translation.

## §8 Versioning and consumption

The framework cuts versioned releases (`governance/constitution.md` §9): `v4.0.0` stable, `v4.0.x` patches, `v4.x.0` minor (backward-compatible Δ additions), `v5.0.0` major (role-chain or breaking changes). You consume on your own cadence — there is no auto-update. When you pull a new version, refresh `docs/current/adoption-state.md` to reflect newly at-spec / partial / divergent Δs. The adopter→framework direction (your lessons) and framework→adopter direction (releases) are both human-mediated; neither is automatic (`process/fold-back-protocol.md`).

## §9 What aidazi is NOT (recap)

- Not a runtime — there's no server you deploy; the runtime is *your* project's.
- Not a single tool — backing agents are configurable per role.
- Not domain-opinionated — it's track-aware, not domain-aware.
- Not an eval harness — it specifies an eval shape (`modules/m-evaluation.md`) you instantiate.

---

End of adoption overview.
