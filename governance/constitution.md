---
title: aidazi Constitution
doc_tier: governance
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-07
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: always-load
size_target: 60KB
split_trigger: if any single section grows past 8KB, move detail to a process/ Layer-B doc and leave a one-line stub here
notes: >
  Layer-A always-loaded constitution. Defines: framework anatomy, LLM-vs-Runtime
  ownership, forbidden list (incl. v4 additions §1.7-A/B/C/D/E), iteration rule,
  evaluation rule, 5-role registry, role boundary invariants, and the
  hard-requirements-vs-suggested-defaults split. Inherited verbatim by every
  adopter via @-include from AGENTS.md; not edited per project. Per-project
  specialization happens in domain context docs and adoption-state.md, not here.
---

# aidazi Constitution

This document is the always-loaded Layer-A core of the aidazi framework.

It defines the universal LLM-vs-Runtime ownership boundary, the forbidden list, the iteration rule, the evaluation rule, the 5-role chain registry, the role boundary invariants, and the split between hard requirements and suggested defaults.

**Editing discipline**: the Constitution is inherited by every adopter via @-include from AGENTS.md. Adopters do not edit it. Per-project specialization happens in `docs/current/` domain context docs and in `docs/current/adoption-state.md`. Framework-level revisions happen at fold-back sub-sprint cadence (per `process/fold-back-protocol.md` §8.2) — never inside an adopter's repo.

Cross-references below point at peer docs within the framework. Source-of-truth conventions live in `governance/doc_governance.md`. Cold-start reading discipline lives in `governance/context_briefing.md`. The Δ-18 Delivery Loop pattern is named here and specified in `process/delivery-loop.md`. The Two Loops distinction (Auto Loop vs Delivery Loop) is summarized in §3.7 here and explained for adopters in `docs/two-loops-explainer.md`.

## §1 Framework anatomy

The aidazi framework is described by three orthogonal dimensions and the application tracks they cut across.

### §1.1 Three orthogonal dimensions

- **Dimension 1 — Layer**:
  - **A Constitution** — this file; timeless ownership + forbidden list. Always loaded.
  - **B Process** — on-demand role docs; how the 5 roles do their work; one doc per process under `process/`.
  - **C State ledgers** — live ledgers in the adopter repo: `action_bank.md`, `handoff.md` §0/§1/§2, `adoption-state.md`.
  - **D Prompt artifacts** — `compact/*-dev-prompt.md`, `compact/*-review-prompt.md`, `compact/*-acceptance-prompt.md`, etc. Per-Δ-5 + Δ-9 prompt-artifact rules: each artifact is self-contained.

- **Dimension 2 — Portability tier**:
  - **T0 Universal** — applies to any track. The Constitution + the 5-role chain + the MANDATORY_CHECKPOINTS + the calibration gate are T0.
  - **T1 App-type** — Type A AI agent vs Type B agentic workflow vs Type C demo vs Type A+B hybrid. Phase pipeline, charter overlays, suite manifest shapes live here.
  - **T2 Domain** — domain-specific surfaces (e.g., customer-service vs travel-SOP vs e-commerce). Tier-2 trace_check primitives, domain handling rules.
  - **T3 Project** — project-specific names, IDs, thresholds.

- **Dimension 3 — Lifecycle**:
  - **static** — frozen at creation (sprint archives, lesson docs).
  - **reviewed** — `live` docs with `last_reviewed` cadence (Constitution, current/* domain contracts).
  - **generated** — compact prompts produced at sprint authoring time; frozen per sprint.
  - **append-only** — `action_bank_archive.md`, lessons, snapshot examples.

### §1.2 Application tracks

v4 supports 4 tracks (Type A AI agent / Type B agentic workflow / Type C demo / Type A+B hybrid). Tracks are NOT a separate dimension; they are a charter-level overlay. Definitions, per-track maturity requirements, and per-track applicability tables live in `process/profile-aware-maturity.md` (Δ-14).

### §1.3 LLM owns

The LLM owns soft semantic decisions. In an adopter project, the following are the LLM's responsibility and MUST NOT be moved to runtime guards (see §1.7):

- user goal
- issue relation / topic hypothesis
- use-case hypothesis
- drift / topic shift detection
- next action choice
- escalation posture
- response strategy
- natural customer-facing wording

This list is illustrative for Type A AI agents. Type B workflows have a narrower "LLM-owned" list (per-step semantic verification of slot values); Type C demos may have essentially no LLM-owned list (off-the-shelf skills).

### §1.4 Runtime owns

The runtime owns hard, deterministic, kernel-level invariants. The following are the runtime's responsibility and MUST NOT be delegated to the LLM:

- tool schema
- capability / permission boundary
- PII and safety floor
- grounding floor for factual claims
- budget / timeout
- idempotency
- persistence
- trace and eval contract

#### §1.4-i Context-passing efficiency (sufficient AND efficient)

Promoted from Δ-5 to a Constitution clause in v4 because every role in the 5-role chain depends on it.

Every prompt artifact (Layer D) MUST be **sufficient** (carries enough context for the receiving agent to do its job without chat-history backchannel) AND **efficient** (does NOT carry more context than necessary).

Each compact prompt under `compact/` MUST declare a `context_budget` front-matter:

```yaml
context_budget:
  target_tokens: <number>
  load_list: [<paths-the-agent-must-load>]
  do_not_load: [<paths-explicitly-excluded>]
  self_contained: true
```

If `self_contained: false` is declared, the prompt is rejected at orchestrator preflight (Δ-18 / `process/delivery-loop.md`) or by the human reviewer in manual mode. This is the §1.4-i clause turned into a build-time check.

The detailed efficiency rules live in `process/context-passing-efficiency.md` (Δ-5) and `process/prompt-artifact-rules.md`.

### §1.5 Iteration rule

Do not fix semantic failures by adding keyword / regex / if-else / enum expansion unless a Tier-0 invariant is broken.

When a semantic failure is observed, the fix routes through `process/post-deployment-iteration.md` (Δ-9): triage to layer (one of `infra` / `java_guard` / `prompt_projection` / `skill_state` / `semantic_planner` / `eval_spec` / `product_policy` / `judge_calibration` / `human_review_required`); for Type A+B hybrids, the layer set also includes `workflow_definition` and `runtime_guard`. The full Fix-Layer Classification Checklist lives in `process/post-deployment-iteration.md` §3.

The Iteration rule is what stops every observed failure from defaulting to a Java guard — keyword/regex/if-else papers over the symptom in one PR and forever after the system is harder to evolve. The §1.7 forbidden list (§1.7 below) is the operational enforcement of this rule.

### §1.6 Evaluation rule

Eval is evidence, not authority.

A pass-rate increase is insufficient unless it improves generalizable customer problem-solving and does not regress safety, grounding, wrong-containment, or architecture health.

Specifically:

- A target-set pass-rate climb that comes with a shadow/holdout regression = failure.
- A pass-rate climb that comes with a new Java guard targeting an eval phrase = forbidden (§1.7 first bullet).
- A pass-rate climb that comes with a widened eval rubric to accept what was previously a bot mistake = forbidden (§1.7 third bullet).

The full Eval Acceptance Rules + smoke-demotion + mocked-LLM evidence gate + framework-defect priority + pre-flight QA gate live in `process/badcase-lifecycle.md` (promoted from csagent §5.6) and `process/architecture-health-metrics.md` (promoted from csagent §6).

### §1.7 Forbidden list

The forbidden list is the operational expression of §1.5 + §1.6. Violating any item is a Tier-0 framework breach.

**Core forbidden list** (inherited from csagent practice):

- Encoding raw eval phrases into Java or prompt.
- Adding UC-specific hard rules for soft semantic decisions.
- Widening eval spec to accept a genuine bot mistake.
- Optimizing visible eval at the cost of shadow/generalization.
- Using prompt as an if-else rule dump.

**v4 additions** — surfaced from the 2-donor codebase scan (csagent + hermes) as load-bearing patterns missed by v3.2:

#### §1.7-A Single abstraction layer per agent

Dual abstraction layers (e.g., a 5-action enum AND tool-use simultaneously) is FORBIDDEN in greenfield agent design.

**Why**: dual abstraction creates semantic ambiguity (LLM must choose which abstraction to use per turn) AND maintenance burden (every new tool needs classification under both surfaces). Worked friction case in `docs/friction-playbook.md`.

**How to apply**: at Δ-3 decision #1 (abstraction-layer choice; see `process/tech-architecture-decision-catalog.md`), pick ONE surface. Default for Type A: single tool-use layer. Document the choice in the Phase 3 technical plan.

#### §1.7-B Bad-case `closure_criterion` is human-judgment paragraph, not keyword match

A bad-case `closure_criterion` (used by both the Code Reviewer Agent for §4.1 anti-hardcode review and the Acceptance Agent for outcome judgment) MUST be expressed as a human-judgment paragraph with THREE components:

1. **Positive shape** — what good behavior looks like (1-2 sentences from the customer perspective).
2. **Anti-pattern** — what bad behavior looks like; the failure shape this case targets.
3. **Anchor phrases** — quoted exemplar phrases from the expected response; SUPPORTING evidence, not regex matchers.

The same shape applies to the Research Agent's `closure_contract` (the milestone-level scope contract; see `templates/compact-research-brief.md` and `schemas/research-brief.schema.json`).

**Why**: keyword matching collapses semantic richness. Two responses that share a phrase can be opposite in meaning ("the refund will be processed" vs "the refund will not be processed"); two responses with no shared phrases can be identical in meaning. The Acceptance Agent + Code Reviewer Agent both judge semantically, not by string match.

**How to apply**: when authoring a `closure_criterion` or `closure_contract`, write the three components as a paragraph. The Code Reviewer Agent at §4.1 / Acceptance Agent at §3 read this paragraph and judge whether the delivered response matches the positive shape AND avoids the anti-pattern. Anchor phrases are evidence the judge cites, not a passing condition.

This rule anchors Δ-12 (artifact taxonomy) bad-case artifact contract and §1.7's existing "no keyword/regex for soft semantic decisions" line.

#### §1.7-C Acceptance Agent spawn isolation

The Acceptance Agent MUST NOT be spawned by the role that authored the Research brief OR by the Deliver Agent it might route work back to.

**Why**: peer-of-Research positioning is what makes Acceptance an outcome gate. If Deliver spawns Acceptance, the Acceptance verdict is structurally biased toward Deliver's claim ("we built X"); the verdict cannot independently judge "did we build the right thing". If Research spawns Acceptance, Acceptance inherits Research's framing and cannot detect that the closure_contract itself was ambiguous.

**How to apply**: Acceptance Agent spawn surfaces are restricted to:
- **Human paste** (Customer triggers at gate 2: release cut / milestone close).
- **Charter-permitted orchestrator** when `tooling.acceptance.mode ≠ off` (Δ-18 / `process/delivery-loop.md`). The verdict is **advisory** — it cannot ship the milestone or route work without human authority; an advisory `pass` HALTs at the `advisory_acceptance_pass_signoff` checkpoint for human sign-off — UNLESS it is **authoritative** (`tooling.acceptance.mode == auto` AND the judge is calibrated for the active class AND `autonomy.level == fully_autonomous_within_budget`), in which case a `pass` auto-ships (`STATE_DONE`). Spawn from a Research, Deliver, or Dev session remains forbidden.

Acceptance spawning from a Deliver or Dev session is a §1.7-C breach; the verdict is invalid. Recover by re-spawning from the proper surface.

Additionally — the Acceptance fix_required → Deliver routing path MUST NOT skip the human-confirm checkpoint. Acceptance writes a checkpoint file (`docs/checkpoints/<timestamp>__acceptance_fix_required__<scope>.md`) and Customer writes the decision; only then can Deliver pick up the gap brief.

#### §1.7-D Charter MANDATORY_CHECKPOINTS list MUST NOT be bypassed

The 9 MANDATORY_CHECKPOINTS in `process/delivery-loop.md` §4.2.3 are the points where human authority is non-negotiable. The charter (`templates/mission-charter.yaml`) MAY add checkpoints; it MAY NOT bypass any default checkpoint. (The 9th, `advisory_acceptance_pass_signoff`, fires only when Acceptance produces an advisory `pass` — see §3.6 and `process/delivery-loop.md` §4.2.3 #9.)

**Non-bypass invariant — all four evasion shapes are invalid**:

- **Omitted** — the charter does not mention the checkpoint at all (relying on "absence = doesn't apply"). Invalid: the orchestrator's default checkpoint set is the floor, not the ceiling.
- **Emptied** — the charter declares the checkpoint as a key but assigns an empty / null value (e.g., `bad_case_manual_review: {}` or `mandatory_checkpoints: []`). Invalid: emptiness is not opt-out.
- **Disabled** — the charter sets the checkpoint to a falsy / inert value (e.g., `bad_case_manual_review.enabled: false` or `bad_case_manual_review.required: false`). Invalid: a checkpoint's required-ness is not a charter-level toggle.
- **Overridden** — the charter replaces the checkpoint's semantics with a weaker variant (e.g., redefines `scope_deviation` to auto-approve below a severity threshold; redefines `human_confirm_required: true` to `auto_confirm_if_clean: true`). Invalid: semantic override of a default checkpoint is removal in disguise.

The orchestrator's charter validator MUST reject any of the above and refuse to boot. Adopters who hit a validator rejection here have two legitimate paths:
1. Restore the default checkpoint's full semantics.
2. ADD a custom checkpoint with an adopter-chosen id; the default still fires alongside.

**Why**: bypassing a checkpoint silently shifts authority from human to orchestrator. The whole point of charter pre-authorization is that the human knows IN ADVANCE which decisions the orchestrator can make autonomously and which require human approval. A charter that bypasses `bad_case_manual_review` (in any of the four shapes above) silently grants the orchestrator authority to close milestones without human bad-case review — that's the opposite of pre-authorization.

**How to apply**: when authoring a charter, choose `autonomy.level` based on what's appropriate; for any level, all 9 MANDATORY_CHECKPOINTS still fire (the 9th, `advisory_acceptance_pass_signoff`, only when Acceptance runs advisory). Add custom checkpoints if your project needs them; never omit, empty, disable, or override a default one.

Anchors Δ-18 Delivery Loop.

#### §1.7-E Auto Loop and Delivery Loop MUST NOT be conflated in adopter docs

When both Concept 1 (Auto Loop) and Concept 2 (Delivery Loop) are in use in the same project, adopter documentation MUST name each distinctly. See §3.7 below and `docs/two-loops-explainer.md` for the full distinction.

**Why**: the two concepts have different subjects (single agent vs multi-agent team), different scopes (per-agent self-improvement vs per-milestone delivery), and different drivers (M-Autoloop driver vs framework Delivery Loop orchestrator). An adopter doc that says "the auto loop drove our milestone close" is ambiguous — does it mean the agent improved itself across the milestone, or the team delivered the milestone? Each meaning has different debugging implications.

**How to apply**: in every doc that mentions either loop, name it explicitly as "Auto Loop (Concept 1; agent self-improvement)" or "Delivery Loop (Concept 2; team delivery)" on first reference. Subsequent references may use the short name once disambiguated.

Anchors §3.7.

### §1.8 Self-extension of the forbidden list

The forbidden list above is the framework baseline. Adopters MAY extend it for their project's domain — e.g., a healthcare adopter MAY add "no LLM-authored medical diagnosis" as `§1.7-domain-A`. Domain extensions live in `docs/current/<adopter>-domain-overlay.md` and are referenced from `docs/current/adoption-state.md`.

Adopters MAY NOT subtract from the framework's §1.7 list. A divergence row in `adoption-state.md` cannot have `status: divergent` against §1.7 — divergence here is a framework breach, not a project-specific override. (Contrast this with suggested defaults — §7.0 of this constitution — which adopters MAY override.)

---

## §2 Doc tiers and load discipline (brief; full in doc_governance)

Every doc in the framework + adopter repo carries front-matter declaring its tier, load discipline, source-of-truth, lifecycle category, and (where relevant) size targets.

The five tiers (per `governance/doc_governance.md`):

- **governance** — Layer A always-loaded (this file, doc_governance, context_briefing).
- **process** — Layer B on-demand by role; `process/*.md`.
- **role-card** — activation prompts for each role; `role-cards/*.md`.
- **template** — `templates/*.md`; consumer copies and instantiates.
- **adopter-state** — `docs/current/*` in the adopter repo; live state.

Load discipline values (front-matter `load_discipline:` field):

- `always-load` — every cold-start session loads this; for governance tier only.
- `on-demand` — load when the role's session needs it.
- `by-role` — role-card style; load when adopting that role.

For full schema rules + decision rules + lifecycle (Δ-4 live vs intermediate) + closure_contract field + cell_size_target field, see `governance/doc_governance.md`.

---

## §3 5-role chain (universal; T0)

This is the canonical 5-role registry. Every adopter inherits this chain via @-include from AGENTS.md. Per-project specialization (which backing coding-agent each role uses; whether the orchestrator drives them or human pastes activations; how often Acceptance runs) happens at the charter level (`templates/mission-charter.yaml`).

The Customer is a sixth participant — human, not an agent. The "5-role chain" name refers to the 5 agent roles below; Customer sits on top + bottom.

### §3.1 Role list

1. **Research Agent** — intake gate; produces closure_contract.
2. **Deliver Agent** (Tech Lead) — planning + orchestration + close conversation.
3. **Dev Agent** — implements; no scope authority.
4. **Code Reviewer Agent** — anti-hardcode + correctness; code-side gate.
5. **Acceptance Agent** — peer-of-Research; closure_contract verifier; outcome gate.

Plus:

- **Customer** (human) — signs the Research brief at gate 1; reads the Acceptance verdict at gate 2; resolves human-confirm checkpoints (Δ-18); has authority over MANDATORY_CHECKPOINTS.

### §3.2 Role chain diagram

```
                          ╔════════════════════════════════════════════════╗
                          ║                Customer (human)                ║
                          ║   on-the-loop OR in-the-loop                   ║
                          ║   per charter.autonomy.level                   ║
                          ╚═══╤════════════════════════════════════════╤═══╝
                              │ gate 1: brief sign-off                 │ gate 2: acceptance verdict
                              ↓                                        ↑
   ┌──────────────────────────────────┐         ┌────────────────────────────────────┐
   │       Research Agent             │         │       Acceptance Agent             │
   │  intake gate · produces brief +  │←ref────│  outcome gate · judge delivered     │
   │  closure_contract                │ for     │  evidence vs closure_contract       │
   │                                  │ contract│                                     │
   │  peer of Acceptance              │ schema  │  peer of Research                   │
   └──────────────┬───────────────────┘         └─────────────┬──────────────────────┘
                  │                                            │ verdict:
                  │ docs/research-briefs/<id>.md               │   pass /
                  │ (closure_contract + scope + anti-goal)     │   fix_required /
                  ↓                                            │   needs_human
   ┌──────────────────────────────────────────────────────────┴──┐
   │                  Deliver Agent (Tech Lead)                  │←─┐
   │   plan + orchestrate + close + maintain bad-case suite       │  │
   │                                                              │  │
   │   • Path 1 Research-driven: brief → milestone/sub-sprint plan│  │
   │   • Path 2 Bad-case-driven:  bad case → 4-route fit          │  │
   │   • Path 3 Acceptance-gap:   gap brief → fix-iteration       │  │
   └──────────────┬──────────────────────────────────────────────┘  │
                  │                                                  │
        dispatch  │       handoff + tests + eval evidence            │
                  │       ↑                                          │ post-confirm
                  ↓       │                                          │ gap routing
   ┌──────────────────────┴─┐    ┌───────────────────────────────┐  │
   │     Dev Agent          │ ─→ │   Code Reviewer Agent         │  │
   │  (codes; no scope)     │    │  anti-hardcode kernel §4.1    │  │
   │                        │    │  + correctness lens           │  │
   │  backing coding-agent  │    │                                │  │
   │  = charter.tooling.dev │    │  verdict: pass / fix_required │  │
   │    .agent_kind         │    │  / out_of_scope_review        │  │
   │                        │    │                                │  │
   │  (Claude Code, Codex,  │    │  backing coding-agent =        │  │
   │  or other)             │    │  charter.tooling.review        │  │
   │                        │    │  .agent_kind                   │  │
   └────────────────────────┘    └───────────────────────────────┘  │
                                                                     │
                                  ┌─────────────────────────────────┐ │
   On Acceptance fix_required:    │  Human-confirm checkpoint        │ │
   acceptance report → human ────→│  human writes:                   │─┘
                                  │    confirm: yes | no             │
                                  │    route: deliver | re-acceptance│
                                  │           | research-revision    │
                                  └──────────────────────────────────┘
```

**Diagram invariants** (these are §3.3 boundary invariants — enforceable):

- Gate 1 (brief sign-off) blocks downstream work until Customer signs.
- Gate 2 (acceptance verdict) is the ship/no-ship decision; Customer signs.
- Acceptance never silently routes to Deliver (§1.7-C).
- Code Reviewer's question ≠ Acceptance's question (see §3.3).
- Dev and Code Reviewer backing coding-agents are configurable per charter; the role boundaries are NOT.
- All roles' chat histories are isolated. Context passes via repo docs only (Δ-5 / §1.4-i).

### §3.3 Role registry table

Per-track applicability + per-track frequency (Acceptance every-sprint for Type C; Research depth varies by track; etc.) lives in `process/profile-aware-maturity.md` (Δ-14). This table is the universal role contract; track-specific shaping is Δ-14's job.

| Role | Trigger | Reads | Produces | Spawn surface | Backing coding-agent | Chain position |
|---|---|---|---|---|---|---|
| **Customer** (human) | Gate events: brief sign-off, acceptance verdict, MANDATORY_CHECKPOINTS | Research brief, Acceptance report, Deliver milestone proposal | Approve / reject / direct (free text) | — | n/a | top + bottom |
| **Research Agent** | (a) Customer asks "what should we build?" (b) Bad-case pattern matures (n≥2, Path 2) | Customer prompt + codebase samples + transcripts/data + relevant `docs/proposals/` | `docs/research-briefs/<id>.md` containing: closure_contract (≥1 paragraph; positive shape + anti-pattern + anchor phrases per §1.7-B) + scope IN/OUT + anti-goal + risk/impact + related R-items | Human paste (default) or charter-permitted orchestrator | Adopter choice via `charter.tooling.research.agent_kind`; usually heavy-reasoning low-code-edit model | intake gate (peer of Acceptance) |
| **Deliver Agent** (Tech Lead) | (a) approved brief lands (b) Acceptance gap brief arrives post-human-confirm (c) bad case triages to "fits current/future milestone" | research brief + action_bank + handoff §0/§1 + codex-findings (at collection time) + Acceptance report (if Path 3) | `milestone_objective.md`, `sprint_objective.md`, `compact/sprint-NNN-dev-prompt.md`, `compact/M<N>-review-prompt.md`, close decisions per `templates/deliver-close-taxonomy.md` | Human paste or charter-permitted orchestrator | Adopter choice via `charter.tooling.deliver.agent_kind` | middle, plan + close |
| **Dev Agent** | sprint-NNN-dev-prompt.md ready | self-contained dev prompt (per Δ-5 + Δ-9 prompt-artifact rules) | code edits + tests + `sprint-NNN-handoff.md` (§1-§11 dev fills; §12 reserved for deliver+human close verdict) | Human paste or charter-permitted orchestrator (workspace-write sandbox, no network, no git push) | Adopter choice via `charter.tooling.dev.agent_kind` — Codex (subscription-billed; cost-asymmetry caveat), Claude Code, or any tool-using coding agent | implementation |
| **Code Reviewer Agent** | sub-sprint close OR §4.3 trigger (semantic-touching + Tier-0 risk + scope-revision-from-codex + bad-case-failure-shape) OR milestone close | dev diff + handoff + sprint_objective + `templates/anti-hardcode-review-kernel.md` | `codex-findings.md` with 4-line header (decision: pass / fix_required / out_of_scope_review; blocking_count; summary; signed sub-sprint scope claim) | Human paste or orchestrator (read-only by mechanical tool whitelist: Read, Grep, Glob) | Adopter choice via `charter.tooling.review.agent_kind` — typically a different model class than Dev for independence | code-side gate |
| **Acceptance Agent** | (default) milestone close (`tooling.acceptance.run_at`) AND release cut; sub-sprint frequency per track (see Δ-14) | Research brief's **closure_contract** + dev evidence (bad-case results + execution trace) + Code Reviewer verdict ledger + (optional) prior Acceptance reports for residual risk | `docs/acceptance-reports/<scope>-acceptance-report.md` with: verdict {pass / fix_required / needs_human}; per-criterion evidence pointer; residual risks; if fail, **gap brief** referencing closure_contract clauses violated and proposed scope; **suggested route** (deliver-fix / re-acceptance-after-evidence / research-contract-revision) | Human paste (Customer at release cut) or charter-permitted orchestrator (read-only by tool whitelist; calibration-gated per §3.6) | Adopter choice via `charter.tooling.acceptance.agent_kind` — distinct from Dev/Reviewer/Research for independence | outcome gate (peer of Research) |

### §3.4 Role boundary invariants (hard requirements)

The 5 roles are real walls, not naming conventions. v4 makes them enforceable.

1. **No self-grading** — a single human operator may walk multiple roles (typical in single-person adopters) but each role MUST execute in a **fresh agent session** with self-contained prompt artifacts. Cross-role context never passes via chat history; only via repo docs (Δ-5 + Δ-9).

2. **Acceptance spawn isolation** (§1.7-C) — Acceptance MUST NOT be spawned by Research, Deliver, or Dev. Spawn surfaces: human paste OR orchestrator when `tooling.acceptance.mode ≠ off` (advisory spawn permitted); the verdict is advisory and HALTs for human sign-off unless authoritative auto-ship applies, which additionally requires the judge `calibrated` (active class) AND `autonomy.level=fully_autonomous_within_budget`.

3. **Code Reviewer ≠ Acceptance** lens distinction:
   - **Code Reviewer's question**: "Is the code well-built? Does it preserve §1.3/§1.4 ownership + anti-hardcode kernel?"
   - **Acceptance's question**: "Did we build the right thing? Does delivered behavior satisfy the closure_contract?"
   - Both gates run; their verdicts are independent. A Reviewer pass + Acceptance fail is meaningful (built well but not the right thing); a Reviewer fail + Acceptance pass is also meaningful (works for the customer but is brittle code).

4. **Research-Acceptance contract symmetry** — Research authors the closure_contract; Acceptance evaluates against it. Research MUST NOT change closure_contract after milestone start without Customer re-sign-off (gate 1 re-fires). Acceptance MUST NOT evaluate against criteria the closure_contract doesn't specify; if Acceptance finds a load-bearing missing criterion, it routes via `suggested_route: research_contract_revision`.

5. **Deliver does not write code, does not run review, does not run acceptance.** Plans, orchestrates, closes. Deliver MAY draft handoff §0 templates and sprint-prompt scaffolds but does not edit feature code or test code in the dev sandbox.

6. **Intra-role skills and sub-agents inherit the role's boundary.** A role's backing agent MAY load role skills (packaged procedural knowledge) and MAY fan out to specialist sub-agents as an implementation detail, per `process/role-skill-model.md`. Any such skill or sub-agent inherits the spawning role's tool whitelist, sandbox, and boundary invariants (#1-#5 above) transitively. Intra-role fan-out never substitutes for a chain gate — a sub-agent's output is a draft; the role remains the sole author and signer of its artifacts. A role MAY NOT use a skill or sub-agent to perform another role's gate function (e.g., Dev invoking an acceptance-judging skill; Deliver fan-out editing feature code). For Acceptance, the calibration identity (§3.6) covers the role's skill set: changing mounted skills invalidates calibration as a model swap does.

### §3.5 Acceptance fix_required → human-confirm → Deliver loop

```
Acceptance verdict = fix_required
       ↓
Acceptance writes acceptance report including:
  • per-criterion evidence (which closure_contract clauses violated)
  • gap brief (proposed scope to close gap)
  • suggested_route ∈ {deliver_fix_iteration, re_acceptance_after_evidence, research_contract_revision}
       ↓
Acceptance posts a human-confirm checkpoint:
  docs/checkpoints/<timestamp>__acceptance_fix_required__<scope>.md
  contains: { gap_summary, suggested_route, decision: pending }
       ↓
Human reads acceptance report + writes checkpoint decision:
  • { confirm: yes, route: deliver_fix_iteration }      → Deliver picks up gap brief
  • { confirm: yes, route: re_acceptance_after_evidence } → re-run Acceptance with more evidence
  • { confirm: yes, route: research_contract_revision }   → Research re-opens brief; gate 1 re-sign-off
  • { confirm: no }                                       → Acceptance verdict downgraded to advisory; ship anyway (Customer assumes residual risk)
       ↓
If confirm=yes && route=deliver_fix_iteration:
  Deliver Agent reads { acceptance report, gap brief }
  Deliver authors new sub-sprint scoped to gap closure (Path 3 input)
  [normal dispatch resumes]
```

**Why human-confirm is mandatory**: the same Customer who signed the Research brief at gate 1 should be the one confirming the Acceptance verdict at gate 2 — not the Deliver Agent or the orchestrator. Without this confirmation, Acceptance could route work back to Deliver indefinitely; with it, Customer keeps loop authority. This is §1.7-C's behavioral counterpart.

### §3.6 Acceptance judge calibration gate

The Acceptance Agent's verdict cannot be trusted in `fully_autonomous_within_budget` mode without prior calibration. Calibration is a one-time-per-(judge-model × project) gate:

1. Maintain a labeled set: `calibration/labeled_acceptance_cases/manifest.json` mapping `(trace, expected_verdict ∈ {PASS, FAIL})` tuples for this project.
2. Run Acceptance Agent against each tuple twice across separate sessions.
3. Compute:
   - `agreement_rate = (judge_verdict matches expected) / total`
   - `flip_rate = (judge_verdict differs across reruns) / total`
4. Calibrated iff `agreement_rate ≥ 0.9 AND flip_rate ≤ 0.1`. Thresholds are suggested defaults (§7.0); adopters may tighten or loosen with rationale.
5. Charter `tooling.acceptance.judge_calibration.status: calibrated | uncalibrated`. Until calibrated, `charter.autonomy.level=fully_autonomous_within_budget` degrades **automatically** to `human_on_the_loop`. Degradation is not optional; the orchestrator implements it.

An uncalibrated judge still **RUNS in ADVISORY mode** (it is not skipped): after the automatic degradation to `human_on_the_loop` (above), its `pass` writes the `advisory_acceptance_pass_signoff` checkpoint and HALTs for human sign-off — it does NOT auto-ship. Authoritative unattended auto-ship still requires `calibrated` (for the active class) under `fully_autonomous_within_budget` (§1.7-C / §3.2 of `archive/2026-06-20-autonomous-delivery-design.md`).

Switching `charter.tooling.acceptance.agent_kind` or `model` invalidates calibration; re-run required.

The full calibration protocol lives in `process/delivery-loop.md` §4.2.

### §3.7 Two distinct loops in v4 — Auto Loop vs Delivery Loop

v4 names two different "loop" concepts that adopters often conflate. They are ORTHOGONAL and can coexist; the framework names them distinctly so adopter documentation can be precise (§1.7-E enforces this).

| Concept | v4 name | What it is | Subject (who/what improves) | Lives in | Track applicability |
|---|---|---|---|---|---|
| **Concept 1** | **Auto Loop** | A Type A AI agent uses an auto-research method to autonomously improve ITSELF — its prompts, skills, internal strategies, retrieval thresholds | The AI AGENT (the product being built) is the subject being improved | `modules/m-autoloop.md` + `process/post-deployment-iteration.md` (Δ-9 OBS triage + autoloop driver pattern) | Type A only |
| **Concept 2** | **Delivery Loop** (Δ-18) | The multi-agent team (Research / Deliver / Dev / Code Reviewer / Acceptance / Customer) collaboratively delivers work; **autonomously discovers gap between implementation and customer requirements** (Acceptance verdict = fix_required); autonomously fixes via Acceptance → human-confirm → Deliver fix-iteration | The TEAM (of agents + human) building/shipping the product is the subject doing the self-correction | `process/delivery-loop.md` + 5-role chain + orchestrator implementation | All tracks (orchestration via Δ-18 is optional per `autonomy.level`) |

**One-line distinctions**:
- **Auto Loop**: "my AI agent gets better at being itself."
- **Delivery Loop**: "my dev team converges on what the customer asked for."

**Why both exist in v4**:
- Auto Loop is a CAPABILITY a Type A project may build for its agent's self-improvement. The framework provides M-Autoloop module guidance (anti-gaming forbidden list, OBS triage L1/L2, etc.) but does NOT drive the Auto Loop — the adopter's Type A project does.
- Delivery Loop is the FRAMEWORK's own collaboration discipline — how multi-agent teams of any track work together. Applies whether the product being built is a Type A agent, a Type B workflow, or a Type C demo.

**They compose; they don't conflict**:
- A Type A project's Delivery Loop drives sub-sprints to milestone close (orchestrator drives Research → Deliver → Dev → Reviewer → Acceptance).
- WITHIN a sub-sprint, the agent's Auto Loop may be invoked as a runtime self-improvement step (e.g., M-Autoloop optimizing prompts overnight during a sprint).
- The two are orthogonal: Auto Loop = vertical depth (one agent self-improving); Delivery Loop = horizontal flow (team collaborating + delivering).

**Implementation mapping**:
- **M-Autoloop module** = Concept 1.
- **Δ-18 Delivery Loop** = Concept 2.
- The "orchestrator" SOFTWARE (state machine, spawn functions, charter parser, checkpoints, F5 evidence) IMPLEMENTS the Delivery Loop. In framework documentation, the pattern's name is "Delivery Loop"; in code, the implementing binary may still be called "orchestrator". Same physical thing; two layers of vocabulary.

Adopter-facing explanation is in `docs/two-loops-explainer.md`.

---

## §4 Process layer — pointers (brief)

The Layer-B process docs live under `process/`. Each is on-demand by role. The Constitution references them but does not duplicate their content.

Index (full list in `process/doc-responsibility-matrix.md`):

| Δ | File | Owner (role that loads it) | What it specifies |
|---|---|---|---|
| Δ-2 | `process/domain-discovery-process.md` | Research | D1/D2/D3 domain elicitation + inheritance-table pattern |
| Δ-3 | `process/tech-architecture-decision-catalog.md` | Deliver | 8 decisions including abstraction-layer (§1.7-A default) |
| Δ-4 | `process/doc-lifecycle-rules.md` | All | live vs intermediate categories |
| Δ-5 | `process/context-passing-efficiency.md` | All | sufficient AND efficient (also §1.4-i above) |
| Δ-6 | `process/typeA-runtime-architecture-skeleton.md` | Deliver / Dev | intent gate + phase pipeline + 6-primitive trace_check DSL |
| Δ-7 | `process/worked-example-instance.md` | All | read-only worked-example rules |
| Δ-9 | `process/post-deployment-iteration.md` | Deliver | OBS triage L1/L2 + Auto Loop driver pattern |
| Δ-10 | `process/doc-responsibility-matrix.md` | All | 8 fields per doc incl `cell_size_target` |
| Δ-11 | `process/capability-staging-roadmap.md` | Deliver | S0–S6 stages; S5 entry condition = §3.6 calibration completed |
| Δ-12 | `process/artifact-taxonomy.md` | All | 14 artifact types + per-role read-list |
| Δ-13 | `process/stage-stable-heuristic.md` | Deliver | heuristic not gate |
| Δ-14 | `process/profile-aware-maturity.md` | Deliver | Type A/B/C/A+B hybrid necessary sets |
| Δ-15 | `process/agent-design-elicitation.md` | Research | 6 questions + 4 inventories + closure_contract draft as output |
| Δ-16 | `process/agent-creation-prerequisites.md` | Research / Deliver | 7-category READY/DEFERRED/N/A gate |
| Δ-17 | `process/common-detours-and-warnings-typeA.md` (+ typeB/typeC placeholders) | Deliver | 4 named pitfalls per track |
| **Δ-18** | `process/delivery-loop.md` | Deliver / Customer | THE Delivery Loop spec (Concept 2). Charter T0+T1, 9 MANDATORY_CHECKPOINTS, state machine, scope_envelope_check, F5 evidence, 6 spawn functions, calibration gate, anti-patterns |
| promoted | `process/milestone-framework.md` | Deliver | 3-5 sub-sprints per milestone; close cadence |
| promoted | `process/prompt-artifact-rules.md` | All | Δ-9 self-containment invariant |
| promoted | `process/badcase-lifecycle.md` | Deliver | §5.6 bad-case suite + tier lifecycle |
| promoted | `process/architecture-health-metrics.md` | Deliver | 4 metric defs (collection still proposal-tier) |
| NEW v4 | `process/self-governance.md` | Framework maintainer | 6 mechanisms + §7.0 hard-vs-suggested |
| NEW v4 | `process/role-skill-model.md` | All | Role skills + intra-role delegation; §3.4 invariant #6 operationalization; SKILL.md packaging convention |
| NEW v4 | `process/fold-back-protocol.md` | Framework maintainer + adopters | Adopter ↔ framework fold-back; adoption-state schema; lessons template |

---

## §5 State ledgers (Layer C) — pointers

State ledgers live in the adopter repo (not in the framework). The framework provides templates; adopters instantiate.

| Ledger | Adopter location | Template | Lifecycle | Owner |
|---|---|---|---|---|
| Action bank (live) | `docs/action_bank.md` | (none — bootstrap from `examples/minimal-greenfield/`) | live; size cap suggested per §7.3 | Deliver |
| Action bank (archive) | `docs/action_bank_archive.md` | (none) | append-only | Deliver |
| Sprint objective | `docs/sprint_objective.md` | `templates/sprint-objective.md` | live per sprint | Deliver |
| Milestone objective | `docs/milestone_objective.md` | `templates/milestone-objective.md` | live per milestone | Deliver |
| Handoff (cold-start §0; narrative §1; archive §2) | `docs/10-handoff.md` or `docs/handoff.md` | `templates/handoff-template.md` | live | Dev (writes §1-§11); Deliver+Customer (write §12 close) |
| Adoption state | `docs/current/adoption-state.md` | `templates/adoption-state-template.md` | live; reviewed per milestone close | Adopter human owner |
| Research briefs (formal) | `docs/research-briefs/<id>.md` | `templates/compact-research-brief.md` | live until milestone close | Research Agent (gate 1: Customer signs) |
| Proposals (informal) | `docs/proposals/<id>.md` | (none — free-form) | intermediate; frozen at creation | Any (informal session) |
| Diagnostics | `docs/diagnostics/<id>.md` | (none) | intermediate | Dev / Code Reviewer / Deliver |
| Failure briefs | `docs/diagnostics/failure-briefs/<id>.md` | (6-field template per Δ-2 / `process/domain-discovery-process.md`) | intermediate per sprint | Joint human + Deliver |
| Acceptance reports | `docs/acceptance-reports/<scope>-acceptance-report.md` | `templates/compact-acceptance-prompt.md` (input); schema `schemas/acceptance-verdict.schema.json` (output) | intermediate per scope | Acceptance Agent (gate 2: Customer reads/signs ship) |
| Code-reviewer findings | `docs/codex-findings.md` | (header per §3.3 above) | intermediate per sprint/milestone | Code Reviewer Agent |
| Checkpoints | `docs/checkpoints/<timestamp>__<event>__<scope>.md` | (orchestrator emits) | intermediate; one per checkpoint event | Orchestrator emits; human resolves `decision:` field |
| Bad-case suite | `eval/bad_cases/<id>.yaml` | schema `schemas/case-spec.schema.json` | live regression suite | Joint Deliver + human (human authors `closure_criterion`) |

Authoring authority + directory taxonomy details: `docs/directory-taxonomy.md`.

---

## §6 Prompt artifacts (Layer D) — pointers

Prompt artifacts (`compact/*.md` in adopter repo) are generated per sprint; frozen per sprint. Templates live in `templates/`.

| Artifact | Template | Per-sprint instance path | Required front-matter |
|---|---|---|---|
| Dev prompt | `templates/compact-dev-prompt.md` | `compact/sprint-NNN-dev-prompt.md` | `context_budget`, `self_contained: true` |
| Review prompt | `templates/compact-review-prompt.md` | `compact/M<N>-review-prompt.md` or `compact/sprint-NNN-review-prompt.md` | `context_budget`, `self_contained: true` |
| Acceptance prompt | `templates/compact-acceptance-prompt.md` | `compact/M<N>-acceptance-prompt.md` | `context_budget`, `self_contained: true` |
| Research brief input | `templates/compact-research-brief.md` | `docs/research-briefs/<id>.md` (becomes the brief itself) | `customer_signed`, `closure_contract` (required body section) |
| Codex rebuttal | `templates/compact-codex-rebuttal-prompt.md` | `compact/sprint-NNN-codex-rebuttal.md` (ad-hoc; per S-Auto-26 pattern) | `context_budget`, `self_contained: true` |

Self-containment rule (per §1.4-i and `process/prompt-artifact-rules.md`): every artifact carries enough context for the receiving agent to do its job without chat-history backchannel.

---

## §7 Self-governance — hard vs suggested

The framework must prevent doc-bloat / context-bloat / governance-drift over time. This section makes the split between **hard requirements** (framework breaks if violated) and **suggested defaults** (good starting points; adopters override with rationale).

The full mechanism set + cadence + bloat-metric definitions live in `process/self-governance.md`. This section gives the registry only.

### §7.0 Hard requirements (cannot be overridden — framework breaks if violated)

- **Constitution §1.7 forbidden list** — including v4 additions §1.7-A through §1.7-E.
- **§3.4 5-role boundary invariants** — no self-grading; Acceptance spawn isolation; Code-Reviewer ≠ Acceptance lens; Research-Acceptance contract symmetry; Deliver-no-code.
- **§4.2.3 of `process/delivery-loop.md` — 9 MANDATORY_CHECKPOINTS** — if Δ-18 orchestrator adopted, all 9 fire (the 9th, `advisory_acceptance_pass_signoff`, only when Acceptance runs advisory); charter may ADD; charter MAY NOT REMOVE (§1.7-D).
- **§3.6 Acceptance judge calibration** — if Acceptance enabled in `fully_autonomous_within_budget` mode, calibration is required; uncalibrated → automatic degradation to `human_on_the_loop`. Degradation is not optional.

Violations of hard requirements are framework breaches, not adopter customizations. They are not eligible for `status: divergent` in `adoption-state.md`.

### §7.1 Suggested defaults (override with documented rationale in `adoption-state.md`)

- All `size_target` / `cell_size_target` / `split_trigger` numerical thresholds (specific values in `process/self-governance.md` §7.1-§7.5).
- Fold-back cadence triggers (5 adoptions / 6 months / critical-pattern thresholds — `process/fold-back-protocol.md` §8.2).
- Calibration thresholds (default `agreement_rate ≥ 0.9` AND `flip_rate ≤ 0.1`) — adopters may tighten or loosen for their context.
- Suite manifest format choice (markdown vs yaml).
- Compact prompt `context_budget.target_tokens` numerical values.
- Per-Δ scope of work tier placement (T0 vs T1 vs T2 vs T3) where the Δ is recommendation-tier.
- Autonomy-level naming and granularity (framework offers 3 levels; adopter may add intermediate levels).

### §7.2 Override procedure

1. Adopter documents the divergence in `docs/current/adoption-state.md` — the relevant Δ row gets `status: divergent` + a `rationale` field explaining why.
2. Continue using the divergent value; no framework rejection.
3. At fold-back cadence, framework maintainer reviews divergences:
   - Many same-direction divergences = default itself is wrong; revise in next framework release.
   - Idiosyncratic divergences = stay adopter-specific; no framework change.

### §7.3 Why the split exists

A framework that over-constrains via hard gates blocks adopters from customizing per application. Different adopters have different scales, team sizes, project domains. The framework's job is to provide a **good starting point** + leave room for **per-application customization**. The framework is opinionated where opinions are load-bearing (§1.7 forbidden, role boundaries, MANDATORY_CHECKPOINTS, calibration for autonomous judges) and accommodating where defaults are just initial guesses.

The §7.0 list above is intentionally short. If you find yourself wanting to add an item to §7.0, file a lesson in `lessons/` and let the framework maintainer evaluate at fold-back.

---

## §8 Governance editing discipline

Planning-time scope authorization (e.g., "fold the Δ-18 spec into Constitution if it becomes universal") does NOT authorize execution-time content.

Before editing any governance-tier doc (this file, `governance/doc_governance.md`, `governance/context_briefing.md`), verify:

1. **Timelessness** — no sprint numbers, R-item IDs, dates, or project-specific names.
2. **Principle vs current-state** — governance teaches principles, not findings. Findings belong in `process/`, `lessons/`, or sprint archives.
3. **Necessity** — would `action_bank.md` or a sprint archive carry the load without the edit?
4. **Durable shift vs reaction** — is this a load-bearing pattern across adopters, or a reaction to one project's experience?

If any check fails, put the content in `lessons/<date>-<topic>.md` or `process/<delta>.md` instead.

Governance edits land at **fold-back sub-sprint** cadence (`process/fold-back-protocol.md` §8.2) — never mid-milestone, never inside an adopter's repo.

---

## §9 Versioning and consumption

The framework cuts versioned releases:

- `v4.0.0` — first stable v4 release (this Constitution + the doc tree per `compact/aidazi-v4-build-plan.md`).
- `v4.0.x` — patch releases (typo fixes, doc clarifications, no Δ shape changes).
- `v4.x.0` — minor releases (Δ additions or extensions; backwards-compatible for adopters at `v4.0.x`).
- `v5.0.0` — major release (Δ removals, role-chain changes, breaking front-matter shape changes).

Adopters consume on their own cadence (no auto-update). When an adopter consumes a new framework version, they update `docs/current/adoption-state.md` to reflect any newly at-spec / partial / divergent Δs.

Cross-version migration guides live in `archive/framework-release-notes/<version>-migration-guide.md` (framework-side; framework maintainer publishes per release).

---

## §10 Anti-patterns (forbidden — extensions to §1.7)

These are the cross-cutting anti-patterns surfaced by the 2-donor scan that don't fit neatly under a single §1.7 sub-clause but are framework breaches.

- **Spawning the Acceptance Agent from a Deliver or Dev session** (§1.7-C; covered above; restated here for visibility).
- **Acceptance routing `fix_required → Deliver` without a written human-confirm checkpoint decision** (§3.5; restated).
- **UNATTENDED auto-iterate/auto-ship on an uncalibrated Acceptance verdict** (e.g., `tooling.acceptance.mode=auto` shipping a `pass` while `judge_calibration.status=uncalibrated`) — degradation must be automatic, never opaque. Advisory-with-sign-off under `human_on_the_loop` (the uncalibrated verdict RUNS, then HALTs at `advisory_acceptance_pass_signoff` for human sign-off) is EXPLICITLY PERMITTED; what remains forbidden is letting an uncalibrated verdict ship or auto-iterate without that human sign-off.
- **Bypassing `scope_envelope_check` on close** (`process/delivery-loop.md` §4.2.5).
- **Giving Dev sandbox read access to `case_specs_shadow/`** (or equivalent holdout eval set) — eval contamination.
- **Acceptance verdict claiming pass/fail from CODE INSPECTION instead of execution evidence** — F5 pattern violation (`process/delivery-loop.md` §4.2.6).
- **Conflating Auto Loop with Delivery Loop in adopter docs** (§1.7-E; covered above; restated).

---

## §11 Read-order for new adopters

When a new adopter onboards, the read order is:

1. `README.md` (this framework's elevator + read-order).
2. `docs/adoption-overview.md` (5-role mental model; what the framework decides vs what adopters decide).
3. `docs/two-loops-explainer.md` (Auto Loop vs Delivery Loop — name discipline avoids §1.7-E breaches).
4. `governance/constitution.md` (this file — full).
5. `governance/doc_governance.md` (tier model + front-matter schema).
6. `governance/context_briefing.md` (cold-start reading discipline; Context Pack Prompt).
7. Per-track guide:
   - Greenfield: `docs/greenfield-guide.md`.
   - Brownfield: `docs/brownfield-guide.md`.
8. `docs/directory-taxonomy.md` (where does this content go?).
9. Role cards (`role-cards/`) — 5 agent role cards; adopt one per-session as needed.
10. `process/customer-checkpoints.md` — human-side gate catalog (Customer is not an agent; gates 1-3 + 9 MANDATORY_CHECKPOINTS).
11. Process docs (`process/`) — load on demand by role.

The full per-task reading list is in `governance/context_briefing.md`.

---

## §12 Glossary

- **Δ** (Delta) — a framework-level proposition; numbered Δ-1 through Δ-18; each is one process pattern.
- **Charter** — the YAML pre-authorization for a Delivery Loop run; `templates/mission-charter.yaml`; schema `schemas/mission-charter.schema.json`.
- **closure_contract** — the Research brief's mandatory paragraph (positive shape + anti-pattern + anchor phrases) that defines the milestone scope; the Acceptance Agent judges against this.
- **closure_criterion** — the per-bad-case version of closure_contract, written for individual eval cases (per Δ-12).
- **MANDATORY_CHECKPOINT** — one of 9 points in `process/delivery-loop.md` §4.2.3 where human authority is required; charter MAY add, MAY NOT remove (§1.7-D).
- **Auto Loop** (Concept 1) — single-agent self-improvement via auto-research; `modules/m-autoloop.md`.
- **Delivery Loop** (Concept 2) — multi-agent team delivery + self-correction; `process/delivery-loop.md`.
- **scope_envelope_check** — deterministic check (no LLM) before close that the work touched only charter-approved scope; `process/delivery-loop.md` §4.2.5.
- **F5 evidence** — Phase 5 / eval-side evidence; orchestrator runs eval harness, passes artifact paths to Acceptance read-only; `process/delivery-loop.md` §4.2.6.
- **Adoption state** — `docs/current/adoption-state.md`; per-Δ status table per adopter; fold-back input.
- **Role skill** — packaged procedural knowledge attached to one of the 5 framework roles (team side); inherits the role's whitelist + sandbox per §3.4 invariant #6; `process/role-skill-model.md`. Distinct from the product-side "skill" senses (`skill_state` fix layer; Δ-15 product skill inventory; Type C off-the-shelf skills).

---

End of Constitution.
