---
title: Artifact taxonomy (Δ-12)
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
size_target: 12KB
notes: >
  Δ-12 EXTEND per v4-plan §4.1: 14-artifact set (was 11 in v3.2) with per-role
  read-list. v4 additions: research-briefs/ (NEW), acceptance-reports/ (NEW),
  deliver_close_taxonomy.md (NEW promoted to templates), adoption-state.md
  (NEW). Loaded by all roles to know what artifacts they read + produce.
---

# Artifact taxonomy (Δ-12)

The framework operates over **14 framework/document artifacts** (was 11 in v3.2; v4 adds 3) PLUS **1 eval-runtime artifact** (the bad-case suite under `eval/bad_cases/`). Each artifact has a defined producer, consumer set, lifecycle, and lineage. This Δ is the artifact directory — when an agent is operating, this is the canonical "what do I read; what do I produce" reference.

The 14 framework/document artifacts are cataloged in §1.1-§1.14 below. The 1 eval-runtime artifact (bad-case suite) is covered in §6 — distinct because it lives under `eval/` (the test surface), not `docs/`, and its lifecycle is governed by `process/badcase-lifecycle.md` (not the standard live/intermediate doc lifecycle).

The 14 framework/document artifacts shape `process/doc-responsibility-matrix.md`'s detailed ownership rows; this Δ is the per-artifact short reference.

## §1 The 14 artifacts

### §1.1 Action bank (live)

- **Path**: `docs/action_bank.md`
- **Producer**: Deliver Agent maintains; Dev / Code Reviewer / Customer surface items.
- **Consumer**: Deliver Agent at every planning round.
- **Lifecycle**: `live`; soft size cap suggested per `process/self-governance.md` §7.3.
- **Lineage**: OBS-items mature to R-items per Δ-9; closed items sweep to action_bank_archive at milestone close.

### §1.2 Action bank (archive)

- **Path**: `docs/action_bank_archive.md`
- **Producer**: Deliver Agent at sweep (milestone close).
- **Consumer**: rare; historical context.
- **Lifecycle**: `intermediate` (append-only); §A sprint / §B milestone / §C R-item sections.

### §1.3 Proposals

- **Path**: `docs/proposals/<id>.md`
- **Producer**: Author of session (Research Agent in exploratory mode OR ad-hoc coding-agent).
- **Consumer**: Customer (informational); Research Agent in formal mode (may promote to research-brief).
- **Lifecycle**: `intermediate` (frozen at creation).
- **Trigger**: human casually opens a session ("how would we approach X?").

### §1.4 Diagnostics

- **Path**: `docs/diagnostics/<id>.md`
- **Producer**: Dev / Code Reviewer / Deliver during sprint work.
- **Consumer**: Deliver (triage); Code Reviewer (cross-reference); Customer (typically does not read).
- **Lifecycle**: `intermediate` (frozen at creation).
- **Lineage**: may promote to failure-brief (n≥2 pattern) OR action_bank R-item.

### §1.5 Failure briefs

- **Path**: `docs/diagnostics/failure-briefs/<id>.md`
- **Producer**: Joint human + Deliver after triage.
- **Consumer**: Research Agent (Path 2 input); Customer (may co-author "what good agent should have done").
- **Lifecycle**: `intermediate` (frozen at creation; 6-field formal template per Δ-2 / `process/domain-discovery-process.md` historical practice).
- **Trigger**: bad-case observed + triage decides load-bearing (n≥2 OR severe).

### §1.6 Sprint objective

- **Path**: `docs/sprint_objective.md`
- **Producer**: Deliver Agent at sub-sprint dispatch.
- **Consumer**: Dev (sub-sprint contract); Code Reviewer (scope claim).
- **Lifecycle**: `live` per sub-sprint; archived to `docs/sprints/<sprint-id>/` at sub-sprint close.

### §1.7 Milestone objective

- **Path**: `docs/milestone_objective.md`
- **Producer**: Deliver Agent at milestone start (Path 1 research-driven).
- **Consumer**: Code Reviewer (milestone review); Acceptance (closure_contract source verification).
- **Lifecycle**: `live` per milestone; archived to `docs/sprints/<milestone-id>/` at milestone close.

### §1.8 Handoff §0 (cold-start)

- **Path**: `docs/handoff.md` (project-wide) OR `docs/sprints/<sprint-id>/handoff.md` (per sub-sprint)
- **Producer**: Deliver Agent maintains §0; Dev fills §1-§11 at sub-sprint close.
- **Consumer**: All roles at cold-start (always-load).
- **Lifecycle**: `live`; `cell_size_target: 500` SUGGESTED per Constitution §7.0.

### §1.9 Handoff §1 (narrative)

- **Path**: same as §1.8.
- **Producer**: Mostly Dev (per-sub-sprint copies) + Deliver (project-wide).
- **Consumer**: All roles for the story §0 can't tell.
- **Lifecycle**: live + per sub-sprint intermediate copies.

### §1.10 Handoff §2 (archive index)

- **Path**: same as §1.8.
- **Producer**: Deliver Agent at milestone close.
- **Consumer**: All roles for cross-sprint discovery.
- **Lifecycle**: live; rows added at each milestone close.

### §1.11 Codex findings (Code Reviewer verdict)

- **Path**: `docs/codex-findings.md`
- **Producer**: Code Reviewer Agent.
- **Consumer**: Deliver Agent (close conversation); Customer (technical reference; usually skim).
- **Lifecycle**: `intermediate` per sub-sprint / milestone; archived at close.

### §1.12 Research briefs (NEW v4)

- **Path**: `docs/research-briefs/<id>.md`
- **Producer**: Research Agent (formal mode).
- **Consumer**: Customer (gate 1 sign-off); Deliver (Path 1 input); Acceptance (closure_contract source).
- **Lifecycle**: `live` until milestone close; archived to `docs/sprints/<milestone-id>/` after.
- **Required**: `closure_contract` body section per Constitution §1.7-B.

### §1.13 Acceptance reports (NEW v4)

- **Path**: `docs/acceptance-reports/<scope>-acceptance-report.md`
- **Producer**: Acceptance Agent.
- **Consumer**: Customer (gate 2 ship/no-ship); Deliver (Path 3 input on fix_required, AFTER human-confirm checkpoint).
- **Lifecycle**: `intermediate` per scope; archived to milestone close package.

### §1.14 Adoption state (NEW v4)

- **Path**: `docs/current/adoption-state.md`
- **Producer**: Adopter human owner.
- **Consumer**: All roles at cold-start (always-load per `governance/context_briefing.md` §5).
- **Lifecycle**: `live`; reviewed per milestone close.
- **Required when**: adopter overrides any framework default.

## §2 Per-role read-list (updated for 5-role)

| Role | Reads (at activation) |
|---|---|
| **Customer** (human) | Research briefs (gate 1); acceptance reports (gate 2); orchestrator checkpoints (Δ-18 MANDATORY_CHECKPOINTS); milestone objective (proposed scope) |
| **Research Agent** | Customer prompt; relevant proposals; codebase samples; transcripts/data; failure-briefs (Path 2 input); action_bank R-items |
| **Deliver Agent** | Research brief (Path 1); failure-briefs (Path 2); acceptance report (Path 3 after human-confirm); action_bank; handoff §0/§1; codex-findings; charter (if Δ-18 adopted) |
| **Dev Agent** | sprint-NNN-dev-prompt.md (self-contained per Constitution §1.4-i); handoff §0/§1 (background); load_list files from prompt |
| **Code Reviewer Agent** | Dev diff; handoff §1-§11; sprint_objective; anti-hardcode kernel; codex-findings history; runtime_invariants (Tier-0 lens) |
| **Acceptance Agent** | Research brief's closure_contract (THE contract source); dev evidence (F5 artifacts); codex-findings (cross-reference); prior acceptance reports (residual risk) |

## §3 Per-role produces

| Role | Produces |
|---|---|
| **Customer** | Approval / rejection in research-brief front-matter; decision: field in checkpoints; ship sign-off in milestone close notes |
| **Research Agent** | Research brief (`docs/research-briefs/<id>.md`) with closure_contract |
| **Deliver Agent** | milestone_objective.md; sprint_objective.md; compact prompts (dev / review / acceptance / codex-rebuttal); close decisions per deliver-close-taxonomy; action_bank entries (R-items + OBS); plan-fix verdicts (Path 3) |
| **Dev Agent** | Code edits + tests + handoff §1-§11; diagnostics on mid-sprint discovery |
| **Code Reviewer Agent** | `docs/codex-findings.md` with verdict header + per-finding JSON |
| **Acceptance Agent** | `docs/acceptance-reports/<scope>-acceptance-report.md` per `schemas/acceptance-verdict.schema.json`; human-confirm checkpoint file on fix_required |

## §4 Artifact lineage diagram

```
Customer prompt ──┐
                  ↓
Research Agent → research-brief (closure_contract) ──→ Customer signs (gate 1)
                                                     │
                                                     ↓
                          ┌─ Deliver Agent (Path 1) ──→ milestone_objective + sprint_objective + compact prompts
                          │
failure-briefs (n≥2) ─────┤
                          │
acceptance-report (fix_   ┤ (Path 3, after human-confirm)
required + gap brief) ────┘

  sprint_objective ──→ Dev Agent → code + handoff §1-§11
                              ↓
              Code Reviewer → codex-findings ──→ Deliver close conversation
                                                      ↓
                                              deliver-close verdict (A/B/C/D)
                                                      ↓
                              milestone_objective + Acceptance Agent → acceptance-report ──→ Customer signs (gate 2)
                                                      ↓
                                          (if fix_required: human-confirm checkpoint)

Across all: action_bank.md is the persistent R-item / OBS ledger.
            adoption-state.md is the per-Δ divergence record.
```

## §5 Joint authoring (Constitution §5)

Three artifacts are JOINT authoring (not auto-mergeable):

- **Failure briefs** — 6-field template; human + Deliver each own specific fields.
- **Bad-case CaseSpec** — Deliver curates structure; human authors closure_criterion.
- **Close decisions per deliver-close-taxonomy** — Deliver proposes verdict A/B/C/D; Customer signs (especially C/D triggering `close_taxonomy_C_or_D` MANDATORY_CHECKPOINT).

## §6 Eval-runtime artifact (bad-case suite)

Distinct from the 14 framework/document artifacts above, the **bad-case suite** lives under `eval/bad_cases/<id>.yaml` + `eval/bad_cases/_manifest.md` and is governed by `process/badcase-lifecycle.md` rather than the standard `live` / `intermediate` doc lifecycle.

- **Producer**: Joint Deliver Agent (curates CaseSpec structure) + human (authors `closure_criterion`).
- **Consumer**: Acceptance Agent (via orchestrator F5 evidence runs); Code Reviewer Agent (cross-reference at review trigger); Dev Agent (reads to verify behaviour but cannot edit).
- **Lifecycle**: case-level tiering (`core` / `scope-relevant` / `closed-as-regression-guard` / `archived`) per `process/badcase-lifecycle.md` §3. Distinct from doc-tier `live` / `intermediate`.
- **Schema**: `schemas/case-spec.schema.json`.

This artifact is named here to keep the inventory complete; its full governance lives in `process/badcase-lifecycle.md`.

## §7 Cross-references

- `process/doc-responsibility-matrix.md` (Δ-10) — detailed per-doc ownership including artifact rows.
- `docs/directory-taxonomy.md` — adopter-facing "where does this content go?" decision tree.
- `process/badcase-lifecycle.md` — the eval-runtime artifact's lifecycle.
- `templates/handoff-template.md` — §0 + §1 + §2 + §1-§11 + §12 structure.

## §8 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

Adding a 15th framework/document artifact is a substantive framework change; route through fold-back. Removing an artifact is breaking; route through v5 migration guide. The eval-runtime artifact (§6) is governed by `process/badcase-lifecycle.md` and edits to its governance route there.

**Artifact #15 — the Requirement Ledger (Δ-19).** `docs/requirements-ledger.json` (schema `schemas/requirement-ledger.schema.json`) is the durable, intake-agnostic requirement→milestone→delivery record introduced by Δ-19 (`process/requirement-ledger.md`; full design `archive/2026-06-23-requirement-ledger-design.md`). Producer: Research at Gate-1 (items) + the Customer (`customer_disposition`, authority-only); consumers: Deliver (`covers_req_ids` on the signed plan), Acceptance (read-only), `scope_report` (the derived view). Phase 2-alpha is additive (absent ⇒ byte-identical); a full §1.15 catalog entry + the 14→15 renumber lands when the ledger is promoted out of the additive backbone phase.

---

End of Δ-12 Artifact taxonomy.
