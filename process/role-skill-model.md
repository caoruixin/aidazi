---
title: Role-skill model — role skills and intra-role delegation
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 14KB
split_trigger: if §6 SKILL.md packaging convention grows past 4KB, move to a process/role-skill-packaging.md
notes: >
  NEW v4 (post-Phase-E insert). Defines the role-skill model: roles are
  accountability/gate boundaries (unchanged 5-role chain); role skills are
  intra-role capability packs; sub-agent fan-out inside a role is a backing-
  agent implementation detail bounded by Constitution §3.4 invariant #6.
  Compatible with the Agent Skills open standard (SKILL.md) and with
  industry subagent libraries. Disambiguates "role skill" from the three
  pre-existing product-side "skill" senses (skill_state fix layer / Δ-15
  product skill inventory / Type C off-the-shelf skills). Full industry
  mapping lives in docs/industry-mapping.md.
---

# Role-skill model — role skills and intra-role delegation

This doc defines how the 5-role chain (Constitution §3) composes with industry agent/skill ecosystems: Agent Skills (the SKILL.md open standard), coding-agent subagent libraries (architect / frontend-developer / backend-architect / code-reviewer personas), and role-pipeline frameworks (BMAD-style Analyst/PM/Architect/Dev/QA chains).

**The one-line model**: a **role** is an accountability boundary — verdict schemas, gates, spawn isolation, and calibration all attach to roles, and the chain does not grow new roles for capability reasons. A **role skill** is packaged procedural knowledge a role's backing agent loads to do its job better. **Sub-agent fan-out** inside a role is an implementation detail of the backing agent. Skills and fan-out change *how* a role works, never *who* answers for the output.

## §1 Why roles and skills are orthogonal

Industry "agents" come in three shapes, and none of them carries the framework's gate semantics:

1. **Agent Skills (SKILL.md standard)** — a directory with a `SKILL.md` (frontmatter `name` + `description`, markdown body, optional `scripts/` / `references/` / `assets/`), loaded by progressive disclosure. A skill is a **capability pack** that attaches to any agent; it has no verdict, no gate, no spawn surface.
2. **Coding-agent subagents** (Claude Code subagents and similar libraries) — specialist personas with a tool whitelist and model choice, delegated to **within a session**. A subagent returns a result to its caller; it does not sign artifacts, fire checkpoints, or hold contract authority.
3. **Role-pipeline frameworks** (BMAD-style) — named roles (Analyst / PM / Architect / Scrum Master / Dev / QA) passing artifacts down a pipeline. Closest cousin to the 5-role chain, but those roles carry no verdict schema, no spawn isolation, no calibration gate — they are sequential prompt personas, not accountability walls.

The 5-role chain's roles are defined by what the chain needs to be trustworthy: who signs which artifact (Constitution §3.3), who may spawn whom (§1.7-C), whose verdict needs calibration (§3.6), where human authority is non-negotiable (§1.7-D). Splitting a chain role because an industry framework has a finer-grained persona (e.g., adding an "Architect" role beside Deliver) would multiply gates and verdict schemas without adding any gate semantics — the architecture-decision work has no independent verdict to carry; it is Deliver's planning work, possibly *assisted* by an architect skill or sub-agent.

So the composition rule is: **adopt industry capability packs INTO roles; do not promote them to chain roles.**

## §2 Terminology — four "skill" senses (disambiguation)

The framework already uses the word "skill" in three product-side senses. This doc adds a fourth, framework-side sense. Never use the bare word "skill" where the sense is ambiguous; use the qualified term from this table.

| Term | Sense | Side | Defined in |
|---|---|---|---|
| **role skill** (THIS doc) | Packaged procedural knowledge attached to one of the 5 framework roles (e.g., the anti-hardcode kernel as a Code Reviewer skill; an architecture-decision skill for Deliver) | **framework / team side** — capabilities of the agents BUILDING the product | this doc; `skills/` dir; `charter.tooling.<role>.skills` |
| `skill_state` | A fix layer in the Δ-9 triage set: multi-tool / multi-turn flow state of the PRODUCT agent | product side | `process/post-deployment-iteration.md` (Δ-9) |
| **product skill inventory** | Δ-15 Part B/C output: the multi-step LLM-orchestrated routines the PRODUCT agent can perform (vs atomic tools) | product side | `process/agent-design-elicitation.md` (Δ-15) §2-§3 |
| **off-the-shelf skills** | Pre-built third-party capabilities a Type C demo uses without custom authoring | product side | `process/profile-aware-maturity.md` (Δ-14); `profile_type_c.off_the_shelf_skill_inventory_required` |

The boundary that keeps these from blurring: role skills are about the **delivery team's** competence (Research/Deliver/Dev/Reviewer/Acceptance doing their jobs); the other three are about the **product being built**. A Deliver Agent loading an architecture-decision role skill is framework-side; the product agent having a "process refund" skill in its skill inventory is product-side.

## §3 The model

```
                 ┌──────────────────────────────────────────────┐
                 │  ROLE  (accountability boundary — fixed)      │
                 │  • artifact contract: what it signs           │
                 │  • verdict schema (where applicable)          │
                 │  • tool whitelist + sandbox                   │
                 │  • spawn surface rules (§1.7-C)               │
                 │                                               │
                 │   ┌────────────┐  ┌────────────┐             │
                 │   │ role skill │  │ role skill │  ← loadable │
                 │   └────────────┘  └────────────┘    capability│
                 │   ┌─────────────────────────────┐    packs    │
                 │   │ sub-agent fan-out (optional)│  ← backing- │
                 │   │ architect / frontend / etc. │    agent    │
                 │   └─────────────────────────────┘    detail   │
                 └──────────────────────────────────────────────┘
                          ↑ everything inside inherits the
                            role's whitelist + sandbox + invariants
```

- **Role skills** are declared per role (role card §"Role skills & intra-role delegation" + optionally `charter.tooling.<role>.skills`). The framework ships skill *slots* (named capability areas with an in-house procedure already in `process/` or `templates/`) that adopters MAY fill with packaged skills — their own or off-the-shelf industry ones.
- **Sub-agent fan-out** is permitted when the role's backing agent supports it (e.g., a coding agent's subagent mechanism) and the charter does not disable it (`charter.tooling.<role>.subagent_fanout`). Fan-out is invisible to the chain: spawn-function verdict schemas (`process/delivery-loop.md` §4.2.7), checkpoints, and artifact paths are unchanged.
- Both are **agent-agnostic** in framework terms: a role card names the skill slot and its constraints; how the backing agent technically loads a skill (SKILL.md discovery, subagent registry, plain prompt include) is `agent_kind`-specific and out of framework scope.

## §4 Boundary constraints (Constitution §3.4 invariant #6 operationalized)

Constitution §3.4 invariant #6 is the hard requirement; this section is its operational checklist. All five constraints below are NOT adopter-overridable (no `status: divergent`).

1. **Whitelist + sandbox inheritance (transitive)** — any role skill or sub-agent operates within the spawning role's tool whitelist and sandbox. Concretely:
   - Code Reviewer / Acceptance sub-agents and skills are read-only (`[Read, Grep, Glob]` default whitelist). A skill whose `allowed-tools` exceeds the role whitelist MUST NOT be mounted on that role.
   - Dev sub-agents inherit workspace-write / no network / no git push / no holdout-eval read (`role-cards/dev-agent.md` §1).
   - Research / Deliver sub-agents inherit the no-feature-code-edit posture of their role.
2. **Fan-out never substitutes for a chain gate** — a sub-agent's output is a draft input to the role, not a chain artifact. An architect sub-agent's design is not a reviewed verdict; a refute-style checking sub-agent inside Dev is not a Code Reviewer pass; a self-assessment skill inside Deliver is not an Acceptance verdict. Every gate in Constitution §3 still fires with its own role session.
3. **Single author/signer** — the role consolidates fan-out results and signs its artifacts alone. `milestone_objective.md` is Deliver's; the review verdict is Code Reviewer's; the brief is Research's. No artifact is attributed to a sub-agent.
4. **No cross-role skill use** — a role MAY NOT load a skill (or spawn a sub-agent) that performs another role's gate function. Dev MUST NOT run an acceptance-judging skill against the closure_contract; Deliver MUST NOT run the anti-hardcode kernel as a substitute review; Research MUST NOT pre-run Acceptance's verdict. (Reading another role's *output* remains per the role-card read-lists; performing its judgment is the breach.)
5. **§1.7-C is unaffected** — intra-role fan-out grants no new spawn surfaces. In particular, no role's sub-agent mechanism may be used to spawn the Acceptance Agent; Acceptance spawn surfaces remain Customer paste or calibration-gated orchestrator only.

**Acceptance calibration corollary** (Constitution §3.6): the Acceptance judge's calibration identity is (agent_kind × model × **role skill set**). Changing `charter.tooling.acceptance.skills` — adding, removing, or updating a mounted skill — invalidates calibration exactly as a model swap does; re-run required before the verdict is authoritative in `fully_autonomous_within_budget` mode.

## §5 Per-role skill slots (summary)

Per-role detail lives in each role card's "Role skills & intra-role delegation" section; this table is the registry.

| Role | Framework-shipped skill-shaped assets (in-house procedure) | Suggested adopter skill slots | Fan-out posture |
|---|---|---|---|
| **Research** | Δ-15 elicitation (`process/agent-design-elicitation.md`); Δ-2 domain discovery; brief template (`templates/compact-research-brief.md`) | industry-research / domain-scout skills (Δ-15 Part D); transcript-analysis skills | MAY fan out parallel domain scouts; brief authored + signed by Research alone |
| **Deliver** | Δ-3 architecture decision catalog (`process/tech-architecture-decision-catalog.md`); close taxonomy (`templates/deliver-close-taxonomy.md`); milestone framework | architecture-decision / ADR skill; sprint-decomposition skill; stack-specific architect sub-agents (frontend/backend/data) for tech-solution drafting | MAY fan out specialist architects for plan drafts; Deliver consolidates + signs; no sub-agent touches feature code (invariant #5 extends transitively) |
| **Dev** | compact dev prompt contract (`templates/compact-dev-prompt.md`); handoff template | **primary mount point for industry stack-specialist skills/subagents** (frontend, backend, database, test-authoring) | MAY fan out within sandbox; all sub-agents inherit workspace-write / no-network / no-push / no-holdout-read |
| **Code Reviewer** | **anti-hardcode review kernel** — exemplar packaged role skill at `skills/anti-hardcode-review-kernel/` (normative source `templates/anti-hardcode-review-kernel.md`) | language/framework-specific review skills (e.g., concurrency, security lenses) | MAY fan out read-only review lenses; verdict consolidated into one `docs/codex-findings.md` header |
| **Acceptance** | acceptance prompt template (`templates/compact-acceptance-prompt.md`); verdict schema | evidence-reading skills ONLY (trace parsing, artifact navigation) — judgment itself is not delegable | Fan-out discouraged; if used, read-only and calibration covers the full skill set (§4 corollary) |

## §6 SKILL.md packaging convention

Role skills SHOULD be packaged per the **Agent Skills open standard** so adopters can mount off-the-shelf skills and export framework skills to any compliant agent:

- A skill is a directory `skills/<skill-name>/` containing `SKILL.md` with YAML frontmatter: required `name` (lowercase alphanumeric + hyphens; MUST match the directory name; ≤64 chars) and `description` (non-empty; ≤1024 chars; says what it does AND when to use it). Optional: `license`, `compatibility`, `metadata`, `allowed-tools`.
- `allowed-tools` (experimental in the standard) MUST be a subset of the target role's tool whitelist (§4 constraint #1). A skill declaring tools beyond the role whitelist is unmountable on that role.
- Keep `SKILL.md` body under 500 lines; move detail to `references/` (progressive disclosure: metadata → instructions → resources).

**Dual-source rule** — when a framework skill packages content that already exists in `templates/` or `process/`:

1. The `templates/` / `process/` file remains the **normative source** (single source of truth).
2. The `SKILL.md` is **thin packaging**: it declares trigger + constraints + a pointer to the normative source; it does NOT duplicate the procedure body.
3. The skill's frontmatter `metadata.normative_source` names the source path; a change to the source obligates a same-sprint review of the skill wrapper.
4. When exporting a skill for standalone use outside the framework repo, copy the normative source into the skill's `references/` at export time; inside the repo, the pointer suffices.

The framework ships ONE exemplar: `skills/anti-hardcode-review-kernel/SKILL.md`. Further packaging of framework procedures is adopter-driven (or lands via fold-back when a pattern proves load-bearing).

## §7 Charter declaration

Two OPTIONAL fields per role under `charter.tooling.<role>` (schema: `schemas/mission-charter.schema.json`; template: `templates/mission-charter.yaml`):

```yaml
tooling:
  <role>:
    agent_kind: claude_code | codex | <other>
    model: <model-id>
    skills: [<skill-name-or-path>, ...]   # optional; each MUST comply with the role's tool whitelist
    subagent_fanout: true | false          # optional; default = backing agent's default behavior
```

Notes:

- Omitting both fields is fully backward-compatible; existing charters validate unchanged.
- `skills` entries are names (resolved against `skills/` dirs the backing agent discovers) or explicit paths. Resolution mechanics are `agent_kind`-specific.
- `subagent_fanout: false` is the adopter's switch to forbid fan-out for a role (e.g., to keep Dev runs simpler to audit). `true` permits it; the §4 constraints apply regardless.
- For `tooling.acceptance`, any change to `skills` invalidates `judge_calibration.status` (§4 corollary); the charter validator SHOULD warn when `skills` changed while `status: calibrated` persists.

## §8 Mounting industry skills (pointer)

The practical how-to — which industry subagent/skill libraries map to which role slots, with the BMAD / Claude Code subagents / Agent Skills / LangGraph / AutoGen comparison table — lives in `docs/industry-mapping.md`. Short version for orientation:

- BMAD's Analyst ≈ Research slot; PM + Architect + Scrum Master ≈ Deliver + its skill slots; Dev ≈ Dev; QA ≈ split across Code Reviewer (code-side) and Acceptance (outcome-side — the split is the framework's value-add, keep it).
- Subagent-library personas (architect / frontend-developer / backend-architect / code-reviewer / etc.) mount as role skills or intra-role sub-agents per the §5 table — never as new chain roles.
- SKILL.md-standard skills mount directly when their `allowed-tools` fits the role whitelist.

## §9 Editing this doc

Process tier; edits land at fold-back sub-sprint cadence per Constitution §8. The §4 constraints mirror Constitution §3.4 invariant #6 — a change to either MUST be reflected in the other in the same fold-back sub-sprint.

Open question carried: whether the framework should ship a full `skills/` library for all five roles is deferred until ≥2 adopters report mounting role skills in practice (fold-back evidence; see `process/fold-back-protocol.md`).

---

End of role-skill model.
