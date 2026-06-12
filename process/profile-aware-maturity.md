---
title: Profile-aware maturity (Δ-14)
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-07
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 16KB
split_trigger: if §3 per-profile necessary-sets matrix grows past 6KB, split into per-track docs
notes: >
  Δ-14 EXTEND per v4-plan §4.1: per-profile necessary sets across Type A / B /
  C / A+B hybrid + per-track Acceptance + Research depth. Holds content
  migrated from constitution.md at Phase A correction (§1, §2) + Phase D
  expansion of per-profile necessary-set matrix (§3).
---

# Profile-aware maturity (Δ-14)

This is the per-track adaptation layer of the framework. The Constitution defines the universal 5-role chain + ownership boundaries + forbidden list (all T0). This doc defines how those universal contracts SHAPE per-track when an adopter declares `track: type_a | type_b | type_c | type_a_b_hybrid` in their charter.

Sections §1 + §2 carry content migrated from `governance/constitution.md` at Phase A correction (track definitions + per-track Acceptance / Research applicability). Section §3 is the per-profile necessary-set matrix — the Phase D expansion. Section §4 covers Type A+B hybrid specifically.

## §1 Application tracks (migrated from constitution.md §1.2)

v4 supports 4 tracks. Tracks are NOT a separate dimension; they are a charter-level overlay (declared in `templates/mission-charter.yaml` via the `profile_type_a` / `profile_type_b` / `profile_type_c` overlays).

### §1.1 Type A — AI Agent

Semantic per-turn reasoning; LLM-controlled. Examples: csagent-style customer-service agent; conversational assistants; recommendation flows where the agent reasons adaptively per turn.

- Deep tools + skills + phase pipeline.
- M-Evaluation (`modules/m-evaluation.md`) + Δ-6 runtime skeleton (`process/typeA-runtime-architecture-skeleton.md`) apply.
- Auto Loop (Concept 1; `modules/m-autoloop.md`) is a Type A capability — not available to pure Type B / Type C.

### §1.2 Type B — Agentic Workflow

Fixed-sequence SOP runner; runtime-controlled step gates. Examples: hermes-style automation with SOP rows as runtime contract; insurance claim processing; supply chain step-by-step automation.

- `workflow_definition` layer is core (carries the SOP rows; runtime executes them).
- Per-step verification gates replace the Type A phase pipeline.
- LLM-owned list is narrower (per-step semantic verification of slot values).

### §1.3 Type C — Demo App

Single-flow demonstrability beats coverage. Examples: trade-show demos; prototype gating; investor pitches.

- Minimal eval; `LOCAL_ACCEPTANCE_CHECKLIST` is the spec.
- Off-the-shelf skills (no custom skill authoring).
- Acceptance Agent runs every sprint (the demo IS the acceptance surface).

### §1.4 Type A+B Hybrid

Both a Type A semantic top loop AND a Type B SOP runner. Hermes-autoloop is the donor evidence: an LLM-driven top loop sits on top of a SOP-driven runtime; charter declares both `profile_type_a` and `profile_type_b` overlays.

Full Type A+B hybrid per-profile necessary set: **Phase D expansion**.

## §2 Per-role per-track applicability (migrated from constitution.md §3.3 "Track applicability" column)

The Constitution's §3.3 role registry table defines what each role does universally. The per-track shaping below describes how each role's frequency / depth / scope CHANGES per track.

| Role | Type A | Type B | Type C | Type A+B Hybrid |
|---|---|---|---|---|
| **Customer** | All gates fire | All gates fire | All gates fire | All gates fire |
| **Research Agent** | Heavy — deep BRD/PRD + transcript-sample-driven UC discovery + 0→1 industry research synthesis | Lighter — SOP review replaces some Research depth (the SOP IS partial product/service design); still need closure_contract | 1-pager — Type C inherently simple; LOCAL_ACCEPTANCE_CHECKLIST is the brief | Heavy (Type A surface) + SOP design (Type B surface) |
| **Deliver Agent** | All | All | All | All |
| **Dev Agent** | All | All | All | All |
| **Code Reviewer Agent** | Full anti-hardcode kernel + correctness lens | Full anti-hardcode + SOP gate verification | Lighter (depth varies — anti-hardcode may simplify since less custom code) | Full both lenses |
| **Acceptance Agent** | Milestone close + release cut | Milestone close + release cut | **Every sprint** — demo IS the acceptance surface | Milestone close + release cut (+ optional per-sub-sprint per charter) |

**Why Acceptance every-sprint for Type C** specifically: Type C's product IS a demo. There is no separation between "delivered behavior" and "demonstrable behavior." Every sprint produces a demo; every sprint must pass the LOCAL_ACCEPTANCE_CHECKLIST gate. Skipping per-sprint Acceptance for Type C means accepting demo regressions silently.

**Why Research depth varies**: a Type A agent must be discovered through user research / transcript sampling / industry analogues. A Type B workflow already HAS its SOP — Research mostly verifies the SOP is sound + writes the closure_contract. A Type C demo is just demonstrability — a 1-page brief is enough.

## §3 Per-profile necessary sets

For each Δ, the table below names what's required (READY), what's deferred / lightweight (DEFERRED), or not applicable (N/A) per track. Adopters who diverge override in `docs/current/adoption-state.md` with rationale.

| Δ | Type A | Type B | Type C | Type A+B Hybrid |
|---|---|---|---|---|
| Δ-1 Anatomy | READY | READY | READY | READY |
| Δ-2 Domain discovery (D1/D2/D3) | READY (deep D2 — transcript samples; UC distribution) | READY (D1+D3 deep; D2 mediated by SOP) | DEFERRED (1-pager combined business+product brief) | READY (both surfaces) |
| Δ-3 Decision catalog (8 decisions) | READY (all 8; §1.7-A single tool-use default) | READY (workflow_definition added to decision #1; SOP runner as #5) | partial (subset; off-the-shelf skills) | READY (both layer sets; charter declares both T1 overlays) |
| Δ-4 Doc lifecycle | READY | READY | READY (lighter cadence) | READY |
| Δ-5 Context-passing | READY | READY | READY | READY |
| Δ-6 Type A runtime skeleton | READY (intent gate + phase pipeline + 6-primitive DSL) | N/A (Type B uses SOP runner; see §4 Type B variant) | N/A | READY (Type A surface side) |
| Δ-7 Worked example | READY (csagent-reference donor) | READY (hermes-reference donor) | placeholder | READY (hermes-reference covers both) |
| Δ-9 OBS triage + Auto Loop driver | READY (OBS triage + Auto Loop applicable) | READY (OBS triage applicable; Auto Loop N/A) | DEFERRED | READY (both) |
| Δ-10 Doc-responsibility matrix | READY | READY | READY (smaller doc tree) | READY |
| Δ-11 Capability staging | READY (S0-S6 ladder) | READY (S0-S5 ladder typical) | partial (S0-S1 typical; full ladder rarely applies) | READY (S0-S6) |
| Δ-12 Artifact taxonomy (14) | READY | READY (with SOP-step artifacts adjacent) | partial (some artifacts N/A; e.g., research-briefs may be merged) | READY |
| Δ-13 Stage-stable heuristic | READY | READY | DEFERRED (small projects don't need explicit stability tracking) | READY |
| Δ-14 Profile-aware maturity (this doc) | applies | applies | applies | applies |
| Δ-15 Agent design elicitation | READY (6 Q's + 4 inventories + industry research) | partial (6 Q's; SOP design replaces inventories) | partial (1-pager) | READY (Type A surface + Type B SOP design) |
| Δ-16 Agent creation prereqs (7 categories) | READY (all 7) | READY (categories 1-3 + 6-7; #4 knowledge corpus N/A typically; #5 canned reply N/A) | partial (categories 1-2 + 6) | READY (all 7) |
| Δ-17 Common detours | Δ-17-A applies | Δ-17-B applies (placeholder) | Δ-17-C applies (placeholder) | Both Δ-17-A + Δ-17-B |
| Δ-18 Delivery Loop | READY (orchestrator optional; Concept 2) | READY (orchestrator optional; T1' SOP variant pending OQ-V4-001) | READY (orchestrator usually skipped; manual Δ-18 chain applies) | READY |

### §3.1 READY / DEFERRED / N/A semantics

- **READY** — adopter is expected to adopt this Δ at framework defaults.
- **DEFERRED** — Δ applies but adopter may use a lighter-weight version (e.g., 1-pager brief instead of full Phase 1+2 split). Adopter MAY upgrade to READY at any milestone.
- **partial** — Δ applies but only some sub-parts; rest is N/A.
- **N/A** — Δ does not apply to this track.

These statuses interact with `docs/current/adoption-state.md` — an adopter whose per-Δ status table shows `at-spec` for a row marked DEFERRED above means they've upgraded to full READY.

## §4 Type A+B Hybrid specifics

Hermes-autoloop is the donor evidence for Type A+B hybrid: a project with both a Type A semantic top loop AND a Type B SOP runner. v4 charter declares both `profile_type_a` and `profile_type_b` overlays simultaneously.

### §4.1 Layer set (Type A+B union)

```
infra
java_guard / runtime_guard
workflow_definition       ← from Type B
prompt_projection
skill_state
semantic_planner          ← top-loop is Type A
eval_spec
product_policy
judge_calibration
human_review_required
```

The Type A semantic_planner is the TOP loop (decides which SOP to start, which step to advance, when to switch); the Type B workflow_definition + runtime_guard layers handle per-step verification.

### §4.2 Closure_contract for hybrid

Hybrid projects MAY author the closure_contract at the Type A top-loop level (the user-facing observable outcome) AND name SOP-step verification gates as required `kpi[]` entries. Acceptance judges the top-loop outcome; Code Reviewer's per-step verification gate findings cover the Type B substrate.

### §4.3 Bad-case suite for hybrid

Bad cases for hybrid projects can target either layer:

- Type A bad cases: top-loop semantic-decision failures (e.g., wrong SOP selected for the user's intent).
- Type B bad cases: per-step SOP-runner failures (e.g., slot validation rejected a valid input).

Joint Deliver + human triage at each milestone close decides which surface each new bad case targets.

### §4.4 Acceptance for hybrid

Hybrid Acceptance reads BOTH closure_contract clauses (top-loop outcome) AND SOP-step verification gate logs (substrate). The evidence_path artifacts include both top-loop trace + per-step verification trace.

## §5 Per-track Phase 1-5 funnel adjustments

Per `docs/greenfield-guide.md` Phase 1-5 funnel:

- **Phase 1 Business need** — universal; D1 per Δ-2.
- **Phase 2 Product/Service design** —
  - Type A: UC registry + tool spec from transcript samples.
  - Type B: SOP step registry + per-step verification gates.
  - Type C: off-the-shelf skill inventory.
  - Hybrid: both UC registry AND SOP step registry.
- **Phase 3 Technical plan** — Δ-3 + Δ-6 instantiation per track.
- **Phase 4 Coding/Implementation packet** — universal shape; per-track module sets differ.
- **Phase 5 Eval/Release** —
  - Type A: 4-tier pyramid + 6-primitive DSL + judge config.
  - Type B: per-step verification suite + SOP-runner regression suite.
  - Type C: LOCAL_ACCEPTANCE_CHECKLIST + demo-run regression.
  - Hybrid: both stacks.

Per `docs/greenfield-guide.md` §5.3.1: simple/seed adopters may MERGE Phase 1+2 into one brief; Type C demos always merge.

## §6 Cross-references

- Constitution §1.2 — track introduction (one-line pointer to here).
- Constitution §3.3 — universal 5-role registry (track-applicability column lives here).
- `process/tech-architecture-decision-catalog.md` (Δ-3) — per-track decision values.
- `process/typeA-runtime-architecture-skeleton.md` (Δ-6) — Type A specific.
- `templates/mission-charter.yaml` — T1 profile overlays.
- `docs/greenfield-guide.md` — per-track bootstrap walkthrough.

## §7 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

Per-track necessary-set matrix evolves as adopters report patterns. The 4-track shape (Type A / B / C / A+B hybrid) is stable v4 vocabulary; adding a 5th track requires fold-back deliberation + donor evidence.

When Type B's full spec lands (OQ-V4-001 — hermes first SOP milestone), §3 + §4 expand with concrete details.

---

End of Δ-14 Profile-aware maturity.
