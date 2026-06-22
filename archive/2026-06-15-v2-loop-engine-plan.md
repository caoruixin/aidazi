---
title: v2 — aidazi as a Spec-Driven, Governed Loop Engine — Build Plan
doc_tier: plan
doc_category: design-history
status: proposed
source_of_truth: this file (until promoted into governance/process docs per phase)
created: 2026-06-15
branch: v2-loop-engine
last_reviewed: 2026-06-15
review_cadence: per phase close
notes: >
  Checklist-level build plan turning aidazi into a spec-driven, harness/model-
  agnostic, GOVERNED loop engine — without aidazi itself becoming a runtime.
  The engine is realized in the adopter codebase via a copyable engine-kit.
  Derived from the "aidazi vs Loop Engineering" report (Boris Cherny / Addy
  Osmani loop-engineering thesis) + a series of refinements. NON-NORMATIVE
  until each item is promoted into the governance/process/modules docs it names.
---

# v2 — aidazi as a Spec-Driven, Governed Loop Engine

## 0. What this is

A build plan. It does NOT change governance yet; each item below names the
core doc / schema / Constitution clause it will edit when its phase runs.

**Origin.** "Loop engineering" (Boris Cherny: *"My job is to write loops"*;
Addy Osmani's anatomy: automations, worktrees, skills, connectors, sub-agents,
external memory) is a *runtime practice*. aidazi is a *spec*. aidazi already
specifies ~most of the loop-engine anatomy and adds governance rigor the
practice lacks — but ships **zero executable code**. This plan compiles the
spec into a running engine **on the adopter side**, keeping aidazi spec-driven.

## 1. North Star & Identity (locked)

- **aidazi stays a spec-driven framework.** No "aidazi server". The runtime is
  the adopter's runtime.
- **Distribution = Spec + copyable engine-kit.** `governance/ process/ modules/
  schemas/` are NORMATIVE source-of-truth. `engine-kit/` is a **reference
  implementation**, adopter-copyable, non-normative. Precedent:
  `skills/anti-hardcode-review-kernel/` already declares "normative source stays
  in `templates/`". **Conflict rule: spec wins; kit is then a bug.**
- **Realized via adoption** into a codebase: **greenfield** (scaffold into a new
  app) or **brownfield** (mount into an existing app).
- **Harness- and model-agnostic.** Roles bind to any (harness × provider ×
  model). The engine's deterministic outer loop is framework-owned standalone
  code — **NOT** built on any one harness's orchestration (no Claude Code
  Workflow dependency).
- **Governed loop engine.** Do NOT trade away checkpoints/calibration/audit for
  "walk-away" autonomy. The differentiator vs vanilla loop engineering is that
  this loop is auditable and gated. Auditability is precisely what lets the
  human move from synchronous gatekeeper to asynchronous reviewer.

## 2. Glossary + naming discipline (Constitution §1.7-E)

Distinct, non-conflatable concepts:

| Concept | Subject | One-liner |
|---|---|---|
| **Auto Loop** (Concept 1) | product AI agent | agent improves itself (Type A) — `modules/m-autoloop.md` |
| **Delivery Loop** (Concept 2) | the team | per-milestone convergence to closure_contract — `process/delivery-loop.md` |
| **Loop Memory** (substrate, NEW) | institutional memory | md-persisted cross-loop lessons; feeds both loops + fold-back |
| **Role Configuration Contract** (NEW) | a role's setup | per-role (execution × capability × connector) binding |
| **Standalone Driver** (NEW) | the engine | framework-owned deterministic outer loop; calls harnesses via adapters |
| **Adapter** (NEW) | one (harness) | translates abstract role spec → that harness's native mechanism |
| **Loop Ingress** (NEW) | loop start | at trigger: intent contract + isolation choice + memory load |
| **Loop Controller** (NEW) | loop iteration | loop-until-condition / convergence / dry-stop / budget |
| **Audit Spine** (NEW) | the record | append-only, hash-chained, reconstructable per-loop ledger |
| **Onboarding Wizard** (NEW) | bootstrap | agent-driven, one-time framework install into a codebase |

Loop Memory is NOT a third loop; it's the memory底座. Loop Ingress (per loop)
≠ Onboarding Wizard (one-time bootstrap).

## 3. Already DONE on this branch

Vendored default role skills (all MIT, read-only-safe, tool-whitelist-compliant,
pinned + integrity-locked):

| Role | Skill(s) | Source @ pin |
|---|---|---|
| Research | `brainstorming` | obra/superpowers @6fd4507 |
| Deliver (architect) | `writing-plans` + `architecture-decision-records` | obra/superpowers @6fd4507 + wshobson/agents @cc37bfd |
| Dev | `test-driven-development` | obra/superpowers @6fd4507 |
| Code Reviewer | `code-review-excellence` | wshobson/agents @cc37bfd |
| Acceptance | `advanced-evaluation` (⚠ calibration-coupled) | muratcankoylan/...@25e1fa7 |

Artifacts: `skills/vendored/<id>/` (each + upstream `LICENSE` + `_provenance.yaml`
with per-file & tree sha256), `skills/registry.yaml` (catalog + `role_defaults`
+ opt-in candidates: differential-review/deep-research/using-git-worktrees/
verification-before-completion), `skills/skills.lock` (pins + tree_sha256).

Outstanding for this concern (→ phases): catalog/lock **schema**, validator
**skill-compliance + integrity** check, and a **vendoring tool** to script
today's manual flow.

---

## 4. Design by concern

Each concern lists: **CORE** (normative spec edits) · **KIT** (engine-kit impl)
· **HARD RULES**.

### 4.1 Role Configuration Contract (the foundation — three facets)

Every role = `(execution binding × capability binding × connector binding)`.
All three: per-role configurable, ship sensible defaults, validated, audited;
the two privileged facets are **default-deny**.

**Facet A — Execution binding (harness × provider × model).**
- Two axes, decoupled: **harness** (`claude_code | codex | headless | <other>`)
  × **provider/model** (`anthropic|openai|deepseek|moonshot|...` + model id).
- Compatibility reality: Claude Code↔Anthropic, Codex↔OpenAI are provider-locked;
  **`headless` (OpenAI-compatible endpoint) is the adapter that unlocks
  DeepSeek/Kimi/GPT**. A role needing file edits (Dev) requires a coding-agent
  harness; pure-API models suit judgment/reasoning roles.
- CORE:
  - `process/model-capability-registry.md` (NEW) + `schemas/model-registry.schema.json`
    (NEW): per-model provider, context window, tool-use, structured-output
    reliability tier, reasoning tier, cost.
  - Role capability requirements table (which role needs structured-output /
    tool-use / reasoning tier / context) — add to the contract doc.
  - Charter: extend `tooling.<role>` with `harness, provider, model, endpoint,
    capability_ref` (see §5 charter schema).
  - Constitution: §3.4 invariant #6 — extend "regardless of backing agent" to
    explicitly cover provider+model; ADD model-agnostic verdict invariant
    (*all verdicts schema-valid regardless of model; engine never lowers the bar
    for a weaker model; invalid verdict = `gate_hard_fail`, never permissive
    default*). §3.6 — calibration is per-`(role,model)`; model change invalidates
    `calibrated` (promote **OQ-V4-007** to rule).
- KIT: adapter interface `spawn(role, prompt, tools, schema) → schema-valid
  verdict`; reference adapters `claude_code`, `headless` (P2), `codex` (later).
- HARD: capability gate validates the **(harness, provider, model)** triple
  against the role's requirements; judgment roles only on calibratable models.

**Facet B — Capability binding (skills).** (largely DONE; formalize)
- CORE: extend `process/role-skill-model.md` (→ role-configuration-contract)
  with defaults + sourcing + provenance; `schemas/skill-binding.schema.json` +
  `schemas/skill-catalog.schema.json` (NEW, formalize `skills/registry.yaml`);
  role cards get a "default skills" section.
- HARD: vendored + pinned; **no runtime fetch**; tool_requirements ⊆ role
  whitelist; redistributable license only + retain upstream LICENSE;
  Acceptance skill change ⇒ recalibrate.

**Facet C — Connector binding (tools / MCP / connectors).** (R4 mechanism)
- Per-role **allowlist, default-deny**. "Explicitly tell each role what it MAY
  use." Scan = authoring aid, NOT runtime authorization.
- Separate: **tools** (built-in; existing whitelist) · **MCP servers** · **connectors**.
- CORE: connector section in the contract doc; `connectors/registry.yaml` (NEW,
  parallel to skill registry: id/kind/server@pin/provenance/capability-class/
  required-secrets-by-name/harness_compat); `schemas/connector-binding.schema.json`
  + `schemas/connector-catalog.schema.json` (NEW); charter `tooling.<role>.
  {tools.allow, connectors[], discovery.mode}` (see §5). Constitution: extend
  anti-pattern #13 / §3.4 #6 to connectors.
- KIT: adapters translate abstract grant → harness-native (Claude Code `.mcp.json`
  + allowed-tools / Codex tool config / headless function list); **propose_only
  discovery scanner** (scan adopter `.mcp.json`/tools → suggest → human approves
  into allowlist).
- HARD: default-deny · role grant ⊇ skill connector requirements · connector
  capability class ⊆ role sandbox · secrets by-name only (values in adopter env)
  · MCP servers pinned + provenance (third-party = trust decision).

### 4.2 Standalone harness-agnostic driver

- The deterministic **outer loop is framework-owned plain code**, NOT a harness's
  orchestration tool. (More correct per §1.4 "Runtime owns the kernel".)
- Ownership split:

| Layer | Owner | How |
|---|---|---|
| state machine / scope_envelope_check / schema-validate / checkpoint inbox / fix-round / budget / resume | **framework (standalone)** | engine-kit plain deterministic code |
| **worktree isolation** | framework | `git worktree` (git-level, not Claude-Code) |
| **scheduling** | framework | plain cron / CI (not ScheduleWakeup) |
| **per-role session execution** (edits, tool-use, inner loop) | **harness, via adapter** | claude_code / codex / headless / aider |

- CORE: rewrite `process/delivery-loop.md` §4.1 "deterministic outer loop"
  language to be substrate-neutral; Workflow (if any) is at most an optional
  backend. §1.4 — name Audit Spine + validators + scope_envelope as runtime-owned.
- KIT: `engine-kit/orchestrator/` (driver) + `engine-kit/adapters/`.
- P0 sub-decision (ADR): driver language — **DECIDED: Python** (frequent shell-out
  to heterogeneous CLIs + HTTP to OpenAI-compatible APIs; existing
  `stanza_validator.py`/`trace_emitter.py` already Python). ADR records rationale.
- Honest cost: we forgo a harness's free plumbing and reimplement the slice we
  need — small, because the spec already defines it; main new work = the adapters
  (needed for multi-model anyway).

### 4.3 Loop Ingress (start + isolation)

At a **new-loop trigger** (a human requirement that dispatches a new
mission/milestone/sub-sprint; continuations don't re-prompt), prompt the human:

| Option | git semantics | fits | risk |
|---|---|---|---|
| 1. current branch (default) | in-place | small / serial | collisions; mixed work |
| 2. new branch | switch branch, same dir | discrete PR unit | dirty-tree switch; no parallel |
| 3. new worktree | separate dir + branch | parallel / long autonomous / fan-out | disk + cleanup |

- Default = option 1, but engine **overrides toward isolation** when
  `loop_active_on_branch` or `dirty_tree` (recommend, with stated reason).
- CORE: `process/delivery-loop.md` §4.2.1 — add `loop_init` ingress + 3 strategies
  + collision rules; charter `isolation` block; note in `customer-checkpoints.md`.
  This is a **configurable ingress prompt**, NOT one of the 8 MANDATORY_CHECKPOINTS.
- KIT: ingress prompt + git context setup + loop registry `.orchestrator/loops.json`
  + cleanup per `cleanup_policy`.
- Candidate skill to vendor here: `using-git-worktrees` (already in registry
  candidates).

### 4.4 Loop Memory (self-evolution; md-only, no storage service)

- Cross-loop experience persisted as **md files**; read at ingress, written at
  close; powers self-evolution. Reuses `lessons/`, `templates/lessons-learned-
  template.md`, Δ-9 OBS triage L1/L2, fold-back, Auto Loop anti-gaming.
- Structure: `<app>/memory/index.md` (loaded at ingress) + `memory/entries/<id>.md`
  (front-matter: `type: failure|heuristic|pattern|calibration-note|detour`,
  `scope:{module/role/layer}`, `maturity:L1|L2`, `occurrences`, `status`,
  `source_loops`, `[[links]]`). Selection = deterministic tag/scope match
  (+ optional LLM relevance). **Storage is just files.**
- Lifecycle: ingress-inject relevant entries per role → capture L1 candidates
  during loop → close distills/updates + maturity L1→L2 (n≥2 or human-flagged) →
  feedback (role context [auto/safe]; skill-edit suggestion [via vendoring];
  charter default tuning; Type A Auto Loop candidate [Δ-9 hookup]; fold-back).
- CORE: `modules/m-memory.md` (NEW) + `schemas/memory-entry.schema.json` (NEW);
  wire into delivery-loop ingress/close; `two-loops-explainer` → "two loops + one
  memory substrate".
- KIT: ingress-read / close-distill / maturity-promote (deterministic selection).
- HARD: store generalizable heuristics, NOT case-specific input→output (that's
  the §1.7 eval-phrase-encoding forbidden item); load-bearing changes
  (skill/charter/prompt) human-approved (Auto Loop §3.3); `calibration-note`
  tagged by `(provider,model)`.

### 4.5 Audit Spine (Next1 — precondition for Next2)

**Review verdict: PARTIALLY satisfied today.** Strong substrate (durable-artifact
rule §3.4#1, checkpoint decision files w/ resolver+timestamps, `events.jsonl`,
`calls/` input-hash+verdict, structured verdicts, m-trace, F5 evidence,
append-only ledgers, info-only observability events). **Gaps:**

| Gap | Problem |
|---|---|
| G1 no first-class Audit spec | auditability emergent, not guaranteed |
| G2 not tamper-evident | "review later" needs a record the loop can't silently rewrite |
| G3 execution-context not captured | calls/ lacks harness/model/skill-pins/memory/tokens (our new additions) |
| G4 no human-readable view | scattered machine artifacts; no end-to-end reconstruction |
| G5 orchestrator-dependent | paste mode lacks events.jsonl/calls/ |
| G6 no causal link | no `loop_id` threading the whole loop |

**Design — Loop Audit Spine:**
- `loop_id` threads charter→brief→checkpoint→spawn→trace→verdict→close (G6).
- Append-only **hash-chained** events `.orchestrator/audit/<loop_id>.jsonl`
  (each event `prev_hash`) (G2).
- Per-spawn full execution context: `{loop_id, step, role, harness, provider,
  model, skill_pins[], memory_injected[], input_hash, verdict_ref, run_mode,
  tokens, cost, ts}` (G3; extends `calls/`).
- **Mode-independent contract**: paste mode appends same events (semi-manual /
  thin logger) (G5).
- Deterministic **reconstruction report** `audit/<loop_id>-report.md` (no LLM) (G4).
- References m-trace `trace_id`; feeds Loop Memory at close.
- CORE: `modules/m-audit.md` (NEW) + `schemas/audit-event.schema.json` (NEW);
  §1.4 names audit runtime-owned; first-class audit contract (G1).
- KIT: hash-chain ledger + context capture + report generator (deterministic).

### 4.6 Next2 — on-demand audit, fewer synchronous gates, intent contract, gate recs

**Principle:** auditability ⇒ human shifts from synchronous gatekeeper to
asynchronous reviewer.

- **Async default posture.** Framework already has info-only non-blocking events
  (`customer-checkpoints.md` §3) + autonomy levels + auto_pass_rules + exception-
  gating. Make async the **default**; add on-demand audit tooling (report +
  filters: "all auto-decided gates since I last looked").
- **Intent contract at ingress** (Next2.1): capture `goal/objective`,
  `standard`, `proof-of-done/eval-method`. Maps onto existing closure_contract,
  moved to ingress. Draft via vendored `brainstorming` (→spec, HARD-GATE) +
  `writing-plans`; **human confirms later** (async). **Intake completeness gate**:
  if the triple isn't identifiable, prompt the human to supplement (don't start a
  loop with no definition of done). Schema: `intent_contract{goal, standard,
  proof_of_done, confirmed_by_human, confirmed_at}` — anchors `loop_id`.
  CORE: `schemas/intent-contract.schema.json` (NEW); ingress spec in delivery-loop.
- **Gate recommendations** (Next2.2): checkpoint files have `# Context` + `# Options`;
  ADD `# Recommendation` + rationale (engine/LLM suggests an option). Human keeps
  authority, lower load. CORE: extend checkpoint shape + relevant schemas.
- **§1.7-D reconciliation — RESOLVED (OQ-B):** async execution MAY proceed through
  *preparation* and *recommendation* (compute, gather options, pre-triage, draft a
  recommended decision), but the **final confirmation of any authority gate ALWAYS
  folds back to the authorized human — no unilateral auto-confirm.** This *preserves*
  §1.7-D (no semantic override; `auto_confirm_if_clean` stays forbidden). Bottleneck
  reduction therefore comes from (i) charter pre-authorization, (ii) exception-gating,
  (iii) on-demand audit, and (iv) doing all prep async so the human confirms a ready,
  recommended decision (incl. bulk human-confirm of a pre-triaged
  `bad_case_manual_review` digest). The human's explicit confirmation — never the
  engine — closes these gates.

### 4.7 Onboarding Wizard (agent-driven bootstrap)

- Harness-agnostic markdown ("feed me to Claude Code / Codex / Cursor"). The agent
  reads it and drives an interactive, idempotent, non-destructive, audited setup;
  human only makes decisions/inputs.
- Form: top-level `ONBOARDING.md` (README points to it) referencing
  greenfield/brownfield guides as source-of-truth (NOT duplicating rationale);
  optional `skills/aidazi-onboarding/SKILL.md` packaging.
- Step flow: detect greenfield/brownfield → (brownfield: scan, non-destructive) →
  track (Type A/B/C) → intent contract (reuse `brainstorming`) → role config (3
  facets, recommend+confirm, default-deny connectors via propose-scan) → generate
  adopter artifacts (`AGENTS.md`, `charter.yaml`, `docs/current/*`, copy
  `engine-kit/`, vendor default skills, `.orchestrator/`+`audit/`) → autonomy +
  checkpoint posture → **validate** (`charter_validator` + structural checks) →
  "first loop" next step.
- Properties: harness-agnostic (read/write/shell only; no Workflow dep);
  idempotent + resumable (progress in `adoption-state.md`); non-destructive
  (read-before-write, confirm overwrites); audited (decisions → adoption-state
  divergence rows + onboarding record); recommendation-driven (one decision at a
  time).
- CORE: wizard spec (decision tree + form + non-destructive/idempotent/audit
  principles), references existing guides + profile-aware-maturity (Δ-14).
- KIT/root: `ONBOARDING.md` MVP (greenfield) → full (brownfield scan, connector
  propose, autonomy tuning).

---

## 5. Charter schema — consolidated additions (`schemas/mission-charter.schema.json`)

```yaml
tooling:
  <role>:
    # Facet A — execution binding
    harness:  claude_code | codex | headless | <other>
    provider: anthropic | openai | deepseek | moonshot | <other>
    model:    <model-id>
    endpoint: <base-url>            # OpenAI-compatible providers
    capability_ref: <profile-id>   # validated vs model-capability-registry
    # Facet B — capability binding
    skills: [ { id, source, repo?, pin?, license?, provenance? } ]   # omit ⇒ role defaults
    subagent_fanout: true | false
    # Facet C — connector binding (default-deny)
    sandbox: read_only | workspace_write
    tools:    { allow: [Read, Grep, Glob, ...] }
    connectors:
      - { id, kind: mcp|http_api|cli, server: <ref@pin>, tools: [...]?,
          scopes: [read|write|network], secrets: [<NAME>] }
    discovery: { mode: off | propose_only }

isolation:                          # Loop Ingress
  prompt_on_new_loop: true
  default_strategy: current_branch | new_branch | new_worktree
  worktree_root: <path>
  cleanup_policy: keep | remove_if_merged | remove_if_unchanged
  force_isolation_when: [loop_active_on_branch, dirty_tree]

intent_contract:                    # Next2.1 (per loop, anchors loop_id)
  goal: <text>
  standard: <text>
  proof_of_done: <text>
  confirmed_by_human: true|false
  confirmed_at: <ISO|null>

audit:                              # Audit Spine
  ledger_dir: .orchestrator/audit
  hash_chain: true
  capture_execution_context: true
```

## 6. New / edited file manifest

**New core spec:**
- `process/role-configuration-contract.md` (the 3 facets; extends role-skill-model)
- `process/model-capability-registry.md`
- `modules/m-memory.md` · `modules/m-audit.md`
- `ONBOARDING.md` (root) + wizard spec section in docs
- `connectors/registry.yaml`

**New schemas:** `model-registry`, `skill-binding`, `skill-catalog`,
`connector-binding`, `connector-catalog`, `memory-entry`, `audit-event`,
`intent-contract` (+ extend `mission-charter`, checkpoint/verdict shapes).

**New engine-kit:**
```
engine-kit/
  orchestrator/        standalone deterministic driver
  adapters/            claude_code · codex · headless
  validators/          charter_validator · stanza_validator   (closes part of OQ-V4-009)
  skill-vendor/        scripts today's manual vendoring flow
  connector-discovery/ propose_only scanner
  audit/               hash-chain ledger + reconstruction report
  README.md            "normative source stays in governance/ + process/"
```

**Constitution edits (route §1.7-D-aware changes through fold-back):**
1. §3.4 #6 — backing-agent neutrality covers provider+model+connectors; transitive
   whitelist (role grant ⊇ skill/connector requirements; class ⊆ sandbox).
2. NEW model-agnostic verdict invariant (schema-valid regardless of model).
3. §3.6 — calibration per-(role,model); model change invalidates calibrated (OQ-V4-007).
4. §1.7 — NEW forbidden: unpinned/runtime-fetched skill OR connector source;
   connector default-allow (must be default-deny).
5. §1.4 — Audit Spine + validators + scope_envelope are runtime-owned.
6. §3.7 / two-loops-explainer — add Loop Memory substrate; name Ingress/Controller/
   Audit Spine distinctly.
7. §1.7-D — codify the OQ-B resolution: async MAY prepare + recommend; **final
   confirmation authority stays human; auto-confirm remains forbidden** (reaffirms,
   does not weaken, §1.7-D). Mandatory checkpoints keep firing; only their *prep
   mode* becomes async.
8. Repo: **MIT LICENSE added** (OQ-C) — replace copyright holder if a specific
   name/entity is preferred.

---

## 7. Phased plan (checklist-level)

> Critical path to "it's a loop engine": **P-0a → P1(charter_validator) → P2 → P3.**
> P4–P6 are multipliers.
>
> **Status (2026-06-17):** P-0a · P0 · P1 · P2 · P3 · P4 (+ integration) · P5 · P6
> all SHIPPED on `v2-loop-engine` (@ `763cfb2`). Boxes below reconciled to the
> handoff pack; items intentionally **DEFERRED** or **DROPPED** are annotated
> inline rather than ticked.

### P-0a — Role Configuration Contract + foundations (CORE spec; no engine)
- [x] `process/role-configuration-contract.md` (3 facets) + `model-capability-registry.md`
- [x] schemas: model-registry, skill-binding, skill-catalog, connector-binding,
      connector-catalog, intent-contract, memory-entry, audit-event
- [x] charter schema additions (§5 above)
- [x] Audit Spine contract + Loop Memory spec + Loop Ingress spec + intent-contract
      + gate Recommendation field (spec only) — specs DONE; the engine-filled gate
      `# Recommendation` field stays a tracked loose end (Next2; precedent shipped
      via the `loop_isolation_recommendation` checkpoint)
- [x] Constitution edits 1–6 drafted (7 flagged for fold-back; 8 LICENSE) — PROPOSED
      in `process/role-configuration-contract.md §7`; LICENSE (MIT) added
- [x] wizard spec (decision tree + principles) — `ONBOARDING.md`

### P0 — Substrate ADR + engine-kit skeleton
- [x] ADR: standalone driver (Workflow at most optional backend) + adapter
      interface + **driver language = Python (decided)** — `docs/adr/ADR-0001-engine-substrate.md`
- [x] `engine-kit/` skeleton + README boundary rule

### P1 — Hard kernel (KIT; deterministic, no LLM) — closes OQ-V4-009 in part
- [x] `charter_validator` — non-bypass (4 shapes)+human_confirm+route_options+calibration-warn
      DONE; capability-gate [harness×model] + skill-integrity + connector default-deny/⊇/class
      are no-op extension points pending P-0a schemas
- [x] `stanza_validator` DONE (validator+tests); schema CI pending (→ P6)
- [x] `skill-vendor` DONE — `verify` matches committed lock (4-way hash agreement); `vendor`
      implemented (not run against live repo)
- [x] Audit Spine — hash-chain ledger + verify_chain + execution-context payload helper +
      reconstruction report DONE; per-spawn capture INTO the driver wires in P2
- [x] on-demand audit tooling — report generator DONE; filters/queries DEFERRED
      (adopter-runtime concern per the OQ-V4-009 reframe, not framework-blocking)
- [x] robustness: guarded ledger/lock parse (corrupt input → clean error, non-zero) [2026-06-15 fix]

### P2 — Engine MVP (KIT) — proves outer-loop/spawn/verdict + multi-model + ingress
- [x] standalone driver: `dev → gate → review → close` on `examples/minimal-greenfield`,
      `human_in_the_loop`, filesystem checkpoints, **no Acceptance yet**
- [x] adapters: `claude_code` + `headless` (demo: Dev on Claude Code, a role on DeepSeek/Kimi)
- [x] Loop Ingress options 1 (current branch) + 2 (new branch)
- [x] intent contract capture + intake completeness gate (uses brainstorming/writing-plans)
- [x] emit Audit Spine from day one
- [x] `ONBOARDING.md` wizard MVP (greenfield path) ending in `charter_validator` green

### P3 — The verifier loop (becomes a real loop engine)
- [x] Acceptance + §3.6 calibration gate (per-model) + F5 evidence
- [x] **Loop Controller** (loop-until-condition / convergence / dry-stop / budget)
- [ ] gate `# Recommendation` filled (LLM-assisted) — DEFERRED (Next2 loose end;
      engine-filled recommendation on must-have checkpoints)
- [x] Loop Memory minimal read/write (lessons mostly from review/acceptance)
- [x] Acceptance skill calibration-coupling enforced

### P4 — Parallelism & reach
- [x] worktree isolation (Loop Ingress option 3) + parallel loop registry/cleanup
- [x] connectors: adapter MCP/api/cli translation + `propose_only` discovery scanner
- [x] vendor `using-git-worktrees`; revisit `deep-research` once connectors exist
      (`using-git-worktrees` vendored; `deep-research` left as an opt-in candidate
      now the connector layer exists)
- [x] `codex` adapter

### P5 — Memory & scheduling (continuous self-evolution)
- [x] full Loop Memory feedback (skill-edit suggestion, charter tuning, Auto Loop
      Δ-9 hookup, fold-back); maturity L1→L2
- [x] scheduling: cron/CI wiring (overnight Auto Loop + milestone Delivery Loop)

### P6 — Adoption ritual + harden + fold back
- [x] full wizard (brownfield scan, connector propose, autonomy tuning, resumable/audited)
- [x] greenfield scaffold / brownfield mount finalized in guides
- [ ] role cards packaged as skills/sub-agent defs — DROPPED (reframed as the P6.1
      `full_chain_guided` bootstrap mode)
- [x] `examples/minimal-greenfield` end-to-end recorded run (proof)
- [x] close OQ-V4-009 (RESOLVED — validators shipped in `engine-kit/validators/`;
      precommit-check + trace_emitter reframed as adopter-runtime tooling) ·
      vendoring CI **DROPPED** · spec-delta fold-back **DEFERRED** (single
      maintainer, no external adopters) — see handoff §7

---

## 8. Open questions / risks
- **OQ-A** driver language — **RESOLVED: Python.**
- **OQ-B** §1.7-D async/recommendation — **RESOLVED:** async prepares + recommends;
  final confirmation always folds back to the authorized human; no unilateral
  auto-confirm (preserves §1.7-D).
- **OQ-C** aidazi LICENSE — **RESOLVED: MIT** (LICENSE file added).
- **OQ-D** calibration cost on model swap (OQ-V4-007) — OPEN; labeled-set portability.
- **Risk** first executable code in an all-Markdown repo: kit needs minimal
  runtime + tests + CI; hard-kernel scripts MUST stay deterministic/no-LLM (§1.4).
- **Risk** scope creep: keep aidazi-core spec-only; all executables in engine-kit.

---

End of v2-loop-engine build plan.
