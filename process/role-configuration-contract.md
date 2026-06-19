---
title: Role Configuration Contract — execution × capability × connector binding
doc_tier: process
doc_category: live
status: proposed
implementation_status: spec-only
source_of_truth: this file
created: 2026-06-15
last_reviewed: 2026-06-15
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 16KB
extends: process/role-skill-model.md
schemas: >
  schemas/model-registry.schema.json, schemas/skill-binding.schema.json,
  schemas/skill-catalog.schema.json, schemas/connector-binding.schema.json,
  schemas/connector-catalog.schema.json, schemas/mission-charter.schema.json
notes: >
  v2 loop-engine P-0a (archive/2026-06-15-v2-loop-engine-plan.md §4.1, §5, §6).
  Defines the three-facet Role Configuration Contract: every role is an
  (execution binding × capability binding × connector binding). All three are
  per-role configurable, ship defaults, are validated + audited; the two
  privileged facets (execution + connector) are default-deny. NON-NORMATIVE
  until the proposed Constitution deltas in §7 are promoted via fold-back.
  Cross-references process/role-skill-model.md (Facet B) — does NOT replace it.
---

# Role Configuration Contract

The 5-role chain (Constitution §3) defines **who answers for what**. This doc
defines **how each role is wired up** without changing who answers. Every role
is configured as three orthogonal bindings:

> **role = (execution binding × capability binding × connector binding)**

All three are per-role configurable, ship sensible **defaults**, and are
**validated** by the charter validator and **audited** via the Audit Spine
(`loop_id` per-spawn execution context, plan §4.5). The two privileged facets —
execution (which model/harness runs) and connector (which external systems a role
may reach) — are **default-deny**: nothing is granted that the charter does not
explicitly grant. The capability facet (skills) is the subject of
`process/role-skill-model.md`; this doc cross-references it (Facet B below) and
does not duplicate it.

The contract is realized in `schemas/mission-charter.schema.json` under
`tooling.<role>`; every field added for it is **OPTIONAL and additive** — a
pre-v2 charter validates unchanged, and an unconfigured facet falls back to its
shipped default.

## §1 Facet A — Execution binding (harness × provider × model)

Execution is **two decoupled axes**:

- **harness** — `claude_code | codex | headless | <other>` — the agent runtime
  that drives a session (edits files, calls tools, runs the inner loop).
- **provider / model** — `anthropic | openai | deepseek | moonshot | …` + a
  model id — the LLM behind the harness.

**Compatibility reality.** Some pairings are provider-locked: Claude Code ↔
Anthropic, Codex ↔ OpenAI. The **`headless` harness (an OpenAI-compatible
endpoint adapter)** is what unlocks DeepSeek / Kimi (Moonshot) / GPT for roles
that don't need a coding agent. A role that edits files (Dev) **requires** a
coding-agent harness with `tool_use`; pure-API models suit judgment / reasoning
roles (Acceptance, parts of Deliver/Research).

**Charter fields** (`tooling.<role>`, all OPTIONAL; legacy charters use only
`agent_kind`):

```yaml
tooling:
  <role>:
    harness:  claude_code | codex | headless | <other>
    provider: anthropic | openai | deepseek | moonshot | <other>
    model:    <model-id>
    endpoint: <base-url>          # OpenAI-compatible providers (headless); literal
    endpoint_env: <ENV_VAR_NAME>  # OR name the env var holding the base URL (literal `endpoint` wins)
    api_key_env:  <ENV_VAR_NAME>  # NAME of the env var holding the API key (headless)
    capability_ref: <profile-id>  # validated vs schemas/model-registry.schema.json
```

**Credentials are by-name, never by-value.** A **native CLI harness**
(`claude_code` / `codex`) authenticates itself — its credentials live in the
CLI's own config outside the charter (e.g. `~/.claude*`, `~/.codex/`), so the
adopter only needs the CLI installed + logged in. A **`headless` provider** needs
a base URL + API key: the charter names them (`endpoint` / `endpoint_env` and
`api_key_env`) and the **values live in the adopter's environment** — exported,
or in a **gitignored `.env.local`** (loaded by `engine-kit/scheduling/run_loop.py`
on `--allow-real` runs; an already-exported var always wins). A secret value
MUST NOT appear in the charter or any committed file (`.env.example` ships the
NAMES only).

**Capability registry.** `process/model-capability-registry.md` +
`schemas/model-registry.schema.json` record per-model facts: provider, context
window, tool-use, structured-output reliability tier, reasoning tier, cost. The
charter's `capability_ref` names a profile in a registry instance; the
**capability gate** validates the role's `(harness, provider, model)` triple
against the role's requirements (§4 table).

**Default-deny + model-agnostic verdict.** The engine NEVER lowers a verdict
schema's bar for a weaker model: an invalid verdict is a `gate_hard_fail`, never
a permissive default. Judgment roles may run only on **calibratable** models
(Constitution §3.6); calibration is per-`(role, provider, model)` and a model
change invalidates `calibrated` (proposed OQ-V4-007 rule, §7).

## §2 Facet B — Capability binding (role skills)

Largely defined in `process/role-skill-model.md`; this facet **formalizes** its
sourcing + provenance and binds it to schemas.

- **Per-role skills** are declared at `tooling.<role>.skills[]`. Each entry is
  EITHER a bare string (legacy name/path) OR the v2 object form
  (`schemas/skill-binding.schema.json`: `id, source, repo?, pin?, license?,
  provenance?`) for explicit, pinned provenance.
- **Catalog + lock.** The shipped default bindings + provenance live in
  `skills/registry.yaml` (`schemas/skill-catalog.schema.json`) with `role_defaults`,
  `skills{}`, `authored{}`, `candidates{}`; vendored content is pinned +
  integrity-locked in `skills/skills.lock`.
- **Defaults** (`skills/registry.yaml` `role_defaults`): Research →
  `brainstorming`; Deliver → `writing-plans` + `architecture-decision-records`;
  Dev → `test-driven-development`; Code Reviewer → `code-review-excellence`;
  Acceptance → `advanced-evaluation` (calibration-coupled). Omitting
  `tooling.<role>.skills` ⇒ the role's defaults.

**HARD rules** (Constitution §3.4 invariant #6, role-skill-model.md §4):
vendored + pinned; **no runtime fetch**; a skill's `tool_requirements` MUST be a
subset of the role's tool whitelist; redistributable license only with the
upstream `LICENSE` retained; **changing the Acceptance skill set invalidates
§3.6 calibration**.

## §3 Facet C — Connector binding (tools / MCP / connectors)

Per-role **allowlist, default-deny**: explicitly tell each role what it MAY use.
A scan is an **authoring aid, never runtime authorization**.

Three separate surfaces, not to be conflated:

| Surface | What | Charter field |
|---|---|---|
| **tools** | built-in agent tools (the existing read/grep/edit whitelist) | `tooling.<role>.tools.allow[]` (legacy `review.tools` array form still valid) |
| **MCP servers / HTTP APIs / CLIs** | external connectors | `tooling.<role>.connectors[]` |
| **discovery** | propose-only scanner posture | `tooling.<role>.discovery.mode` |

```yaml
tooling:
  <role>:
    sandbox: read_only | workspace_write
    tools: { allow: [Read, Grep, Glob, ...] }
    connectors:
      - { id, kind: mcp|http_api|cli, server: <ref@pin>, tools: [...]?,
          scopes: [read|write|network], secrets: [<NAME>], provenance }
    discovery: { mode: off | propose_only }
```

- **Catalog.** Vetted connectors live in `connectors/registry.yaml`
  (`schemas/connector-catalog.schema.json`), parallel to the skill registry:
  `id / kind / server@pin / provenance / capability_class / required_secrets /
  harness_compat`. Granting is per-role and default-deny in the charter
  (`schemas/connector-binding.schema.json`).
- **discovery.mode: propose_only** lets a scanner *suggest* connectors a human
  then approves into the allowlist; it NEVER auto-authorizes. `off` is the
  default.

**HARD rules** (Constitution §1.7 new item + §3.4 invariant #6): default-deny ·
a role's connector grant ⊇ the connector requirements of its bound skills ·
connector capability class ⊆ role sandbox (a `read_only` role cannot hold a
write/network connector) · secrets referenced **by-name only** (values live in
the adopter env, never the charter) · MCP servers pinned + provenance-bearing
(third-party = an explicit trust decision).

## §4 Role Capability Requirements

Which facet each role leans on. Tiers (`high > medium > low > unsupported`) are
the `schemas/model-registry.schema.json` reliability tiers; a role's requirement
is met iff the model's tier is **>=** the required tier. These are
**suggested-default** thresholds (Constitution §7.0); adopters may tune with
rationale.

| Role | structured_output | tool_use | reasoning_tier | context | harness class | notes |
|---|---|---|---|---|---|---|
| **Research** | medium (brief schema) | optional | high | large (reads briefs/transcripts) | any (API ok) | judgment-heavy; brainstorming → spec gate |
| **Deliver** | medium (plan/close verdicts) | optional | high | large (plans across modules) | any (API ok) | planning + close; ADR/decomposition |
| **Dev** | low | **required (high)** | medium | medium–large (repo context) | **coding-agent (claude_code/codex/aider)** | edits files → MUST have tool_use + workspace_write |
| **Code Reviewer** | **high (review-verdict schema)** | read-only tools | high | large (diff + repo) | coding-agent or headless w/ read tools | emits schema-valid verdict; read-only whitelist |
| **Acceptance** | **high (acceptance-verdict schema)** | read-only evidence tools | **high** | large (evidence/traces) | headless/API ok | **calibratable model only** (§3.6); judgment not delegable |
| **eval (F5)** | n/a (orchestrator runs a cmd) | n/a | n/a | n/a | n/a | not an LLM role; `tooling.eval.cmd` |

Reading: verdict-emitting roles (**Code Reviewer, Acceptance**) require **≥ medium**
structured-output reliability — the per-role floor (matches
`schemas/model-registry.schema.json` + `process/model-capability-registry.md`).
`high` is the **recommended target** for judgment roles (**Acceptance** especially,
and **Research**), not a hard floor. The model-agnostic-verdict invariant still
holds: the engine refuses to relax a verdict schema for a weaker model — but the
bar it never lowers is this per-role floor, not a blanket `high`. **Dev** is the
one role that hard-requires `tool_use` on a coding-agent harness. **Acceptance**
additionally requires a **calibratable** model (the capability gate refuses
judgment roles on non-calibratable models).

## §5 Validation rules (capability gate — extension points, KIT in P1+)

The charter validator's capability gate (no-op extension points already present
in `engine-kit/validators/charter_validator.py` pending these P-0a schemas)
enforces, deterministically and with no LLM:

1. **Facet A — triple check.** Resolve `tooling.<role>.capability_ref` against a
   model-registry instance; the `(harness, provider, model)` triple must satisfy
   the §4 row for the role. Dev without `tool_use` on a non-coding harness ⇒
   reject. Judgment role on a non-calibratable model ⇒ reject.
2. **Facet A — verdict invariant.** Verdict schemas are model-independent; the
   gate never widens a verdict schema per model. Invalid verdict = hard fail.
3. **Facet B — skill integrity.** Each bound skill is vendored + pinned (matches
   `skills/skills.lock`); its `tool_requirements` ⊆ the role's whitelist; license
   redistributable. Acceptance skill-set change while `judge_calibration.status:
   calibrated` ⇒ warn (recalibrate).
4. **Facet C — default-deny + transitive ⊇.** A role's `connectors[]` grant ⊇
   the connector requirements of its bound skills; each connector's `scopes` ⊆
   `capability_class` ⊆ the role's `sandbox`; secrets are env-var NAMES only;
   `server` is pinned. `discovery.mode: propose_only` never grants — approvals
   are human-written into `connectors[]`.

Until the gate is wired (P1+), these are spec obligations; the schemas in this
phase make the shapes machine-checkable.

## §6 Cross-reference, not duplication

- **Facet B detail** — `process/role-skill-model.md` (the four "skill" senses,
  §4 boundary constraints, SKILL.md packaging, the per-role skill-slot table).
  This contract adds the **sourcing/provenance + catalog/lock schema** layer and
  references that doc for the rest; the two MUST stay consistent in the same
  fold-back sub-sprint (role-skill-model.md §9).
- **Charter shape** — `schemas/mission-charter.schema.json`
  (`tooling.<role>.{harness, provider, endpoint, capability_ref, skills,
  connectors, discovery, tools}` + top-level `isolation` / `intent_contract` /
  `audit`).
- **Loop Ingress / intent contract / Audit Spine** — `process/delivery-loop.md`
  (ingress), `schemas/intent-contract.schema.json`, `schemas/audit-event.schema.json`,
  `modules/m-audit.md`, `modules/m-memory.md` (P-0a peers).

## §7 Proposed Constitution deltas (PROPOSED — pending fold-back; NOT yet normative)

The following are **drafts** of the edits this contract implies. They are
**NOT** normative until promoted into `governance/constitution.md` via
`process/fold-back-protocol.md`. This doc does NOT edit the Constitution. Each
maps to plan §6.

**Δ-C1 — §3.4 invariant #6 extension (backing-agent neutrality covers
provider + model + connectors; transitive whitelist).** Extend invariant #6 so
"regardless of backing agent" explicitly covers **provider and model** (not just
`agent_kind`) and **connectors**. Add the transitive-grant rule: a role's
connector grant ⊇ the connector requirements of its skills, and a connector's
capability class ⊆ the role's sandbox. (Anti-pattern #13 / §3.4 #6 extend to
connectors.)

**Δ-C2 — NEW model-agnostic verdict invariant.** Add an invariant: *all verdicts
MUST be schema-valid regardless of the backing model; the engine MUST NOT lower
or widen a verdict schema for a weaker model; an invalid verdict is a
`gate_hard_fail`, never a permissive default.* (New clause near §3.4 / §1.6.)

**Δ-C3 — §3.6 calibration is per-`(role, model)`; model change invalidates
`calibrated` (promote OQ-V4-007 to a rule).** Generalize §3.6's existing
"switching `agent_kind` or `model` invalidates calibration" to a per-`(role,
provider, model)` calibration identity, and **promote OQ-V4-007** ("a model
change invalidates `calibrated`") from open question to a hard rule, with a
`calibration-note` Loop Memory entry tagged by `(provider, model)`.

**Δ-C4 — §1.7 NEW forbidden items.** Add to the forbidden list: (a)
**unpinned / runtime-fetched skill OR connector source** — every skill and
connector MUST be pinned with recorded provenance; runtime fetch is forbidden;
(b) **connector default-allow** — connector access MUST be default-deny per role;
a charter that grants connectors implicitly (or via a catch-all) is a breach.
(Parallels the §1.7-D non-bypass discipline.)

**Δ-C5 — §1.4 Audit Spine is runtime-owned.** Add the **Audit Spine** (the
append-only, hash-chained per-loop ledger), the **validators**, and the
**`scope_envelope` check** to the §1.4 "Runtime owns" list, alongside "trace and
eval contract".

**Δ-C6 — §3.7 / two-loops-explainer Loop Memory substrate + named loop
components.** Add **Loop Memory** to §3.7 / `docs/two-loops-explainer.md` as the
institutional-memory **substrate** ("two loops + one memory substrate") — NOT a
third loop — and name **Loop Ingress**, **Loop Controller**, and **Audit Spine**
distinctly per the §1.7-E naming discipline (plan §2 glossary).

> Plan §6 items **7** (§1.7-D async/recommendation OQ-B reaffirmation — flagged
> for fold-back, reaffirms not weakens §1.7-D) and **8** (MIT LICENSE) are
> tracked in the plan and are out of scope for this contract doc.

## §8 Editing this doc

Process tier; edits land at fold-back sub-sprint cadence (Constitution §8). The
§7 deltas move to `governance/constitution.md` only through
`process/fold-back-protocol.md`. The §1-§5 facet rules mirror the schemas in
`schemas/`; a change to either MUST be reflected in the other in the same
fold-back sub-sprint, and Facet B changes MUST stay consistent with
`process/role-skill-model.md` §4.

---

End of Role Configuration Contract.
