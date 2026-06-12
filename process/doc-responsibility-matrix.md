---
title: Doc responsibility matrix (Δ-10)
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
size_target: 10KB
notes: >
  Δ-10 EXTEND per v4-plan §4.1: 8 per-doc fields including the NEW
  cell_size_target field for table-cell docs (handoff §0). Defines who
  owns each doc and the load discipline + size targets.
---

# Doc responsibility matrix (Δ-10)

Every framework doc + adopter-side artifact carries a defined owner, load discipline, and size posture. This Δ defines the 8-field schema each doc declares; `governance/doc_governance.md` §1 + §3 + §6 define the front-matter schema in detail.

This Δ exists so adopters don't get lost in "who maintains what" + "what should this doc look like next year." The fields below are the SHAPE; the values are per-doc.

## §1 The 8 fields per doc

Every governed doc declares (in front-matter or in this matrix if adopter-side):

1. **`owner`** — the role (or human, for adopter-side) responsible for keeping the doc current.
2. **`load_discipline`** — `always-load` / `on-demand` / `by-role` (per `governance/doc_governance.md` §3).
3. **`scope`** — what subject area the doc covers; cross-references to its peers.
4. **`source_of_truth`** — where to look if the doc and reality disagree.
5. **`review_cadence`** — when the owner reviews it.
6. **`size_target`** — soft budget (KB); PR reviewer flags growth past target.
7. **`split_trigger`** — description of when to split (Δ-10 mechanic).
8. **`cell_size_target`** — for table-cell docs (e.g., handoff §0); SUGGESTED default 500 chars per Constitution §7.0; adopter overridable with rationale.

Field 8 is NEW in v4 (csagent drift evidence: handoff §0 cells grew to multi-thousand-char paragraphs). It applies only to docs with structured table-cell content (handoff §0; some adoption-state.md tables).

## §2 Framework doc ownership

| Doc tier | Owner | Load discipline | Review cadence | Notes |
|---|---|---|---|---|
| `governance/` | Framework maintainer | always-load | fold-back sub-sprint | Constitution + doc_governance + context_briefing |
| `process/` | Framework maintainer | on-demand | fold-back sub-sprint | One file per Δ + promoted-from-csagent |
| `role-cards/` | Framework maintainer | by-role | fold-back sub-sprint | 5 agent role cards |
| `templates/` | Framework maintainer | by-role | fold-back sub-sprint | Adopter copies + instantiates |
| `docs/` (application-guide) | Framework maintainer | on-demand | fold-back sub-sprint | Adopter-facing guides |
| `schemas/` | Framework maintainer | (referenced) | fold-back sub-sprint | JSON schemas; tooling consumes |
| `modules/` | Framework maintainer | on-demand | fold-back sub-sprint | M-Evaluation / M-Trace / M-Autoloop |
| `examples/<ref>/` | Framework maintainer | on-demand | per snapshot decision (Δ-7) | Read-only after snapshot |
| `lessons/` | Framework maintainer + adopters | on-demand | per fold-back | Lessons intermediate; status changes via new commit |
| `archive/` | Framework maintainer | on-demand (rare) | n/a | Frozen history |

## §3 Adopter-side doc ownership

| Adopter-side doc | Owner | Load discipline | Review cadence |
|---|---|---|---|
| `AGENTS.md` | Adopter human owner | always-load | per milestone close |
| `docs/current/runtime_invariants.md` | Adopter human owner + Deliver | always-load | per milestone close |
| `docs/current/domain_taxonomy.md` | Adopter human owner | on-demand | per milestone close |
| `docs/current/adoption-state.md` | Adopter human owner | always-load | per milestone close |
| `docs/current/agent_context_guide.md` | Adopter human owner | always-load | per milestone close |
| `docs/foundational/business-need.md` | Customer + Research | live (per Phase 1 cadence) | per milestone planning |
| `docs/foundational/product-service-design.md` | Customer + Research | live | per milestone planning |
| `docs/foundational/technical-plan.md` | Deliver + Customer | live | per Phase 3 cadence |
| `docs/research-briefs/<id>.md` | Research Agent + Customer | by-role | live until milestone close |
| `docs/proposals/<id>.md` | Author of session | intermediate | frozen at creation |
| `docs/diagnostics/<id>.md` | Dev / Code Reviewer / Deliver | intermediate | frozen at creation |
| `docs/diagnostics/failure-briefs/<id>.md` | Joint human + Deliver | intermediate | frozen at creation |
| `docs/acceptance-reports/<scope>-acceptance-report.md` | Acceptance Agent | intermediate | frozen at scope close |
| `docs/codex-findings.md` | Code Reviewer Agent | by-role | per sub-sprint / milestone close |
| `docs/action_bank.md` | Deliver Agent | always-load | per sprint close |
| `docs/action_bank_archive.md` | Deliver Agent | on-demand | append-only |
| `docs/handoff.md` | Mixed (Dev §1-§11; Deliver §0/§1/§2 + §12.2; Customer §12.3) | always-load | per sub-sprint close |
| `docs/sprint_objective.md` | Deliver Agent | live (per sub-sprint) | per sub-sprint close |
| `docs/milestone_objective.md` | Deliver Agent | live (per milestone) | per milestone close |
| `docs/checkpoints/*.md` | Orchestrator emits; Customer writes decision | intermediate | one per event |
| `eval/bad_cases/<id>.yaml` | Joint Deliver + human (closure_criterion) | live | sweep per milestone |
| `eval/bad_cases/_manifest.md` | Deliver Agent | on-demand | per milestone close |

## §4 Size targets (suggested per Constitution §7.0)

Suggested initial values (override with rationale in adoption-state.md):

| Doc tier | Suggested `size_target` |
|---|---|
| `governance/` | 20-60 KB; constitution highest; doc_governance + context_briefing ~20 |
| `process/` | 4-50 KB per Δ; delivery-loop is the largest |
| `role-card/` | 4-14 KB |
| `template/` | 2-12 KB |
| `application-guide` (docs/) | 4-16 KB per doc |
| `module/` | 8-20 KB |
| `schema/` | 1-8 KB JSON |
| adopter `current/*` | per adopter; suggested 4-12 KB per doc |

PR reviewer flags growth past target. Constitution §7.0: this is a SIGNAL, not a hard gate.

## §5 split_trigger

Each doc's `split_trigger` front-matter declares when to consider splitting:

- `if §N grows past KB, move detail to <child-doc>.md` — section-level split.
- `if rules/list grows past N entries, split into <child-doc>.md` — list-level split.

When `split_trigger` fires (typically detected by Code Reviewer at PR), Deliver Agent + framework maintainer decide at fold-back whether to split.

A doc that splits inherits the parent's `owner` and `load_discipline`; the children may have tighter `size_target`. The parent retains a one-line stub for each child for cross-doc citation continuity.

## §6 Cell-size discipline (NEW v4)

For docs with structured table-cell content (handoff §0 in particular), `cell_size_target: 500` chars is the suggested soft cap (per Constitution §7.0 + `process/self-governance.md` §7.2).

Rationale: csagent practice revealed §0 cells naturally grow to multi-thousand-char paragraphs, eroding cold-start readability.

Override procedure: raise the target in the doc's front-matter + document rationale in `docs/current/adoption-state.md`. Adopters with denser projects may raise to 800-1000; single-person hobby projects may stay terse.

## §7 Authority for changing this matrix

The matrix in §2 and §3 reflects v4's role-chain design. Changes require fold-back deliberation (per `process/fold-back-protocol.md`).

Adopters MAY add rows for adopter-specific docs (e.g., `docs/current/compliance-overlay.md` for healthcare adopters). They MAY NOT change row values for framework-owned docs.

## §8 Cross-references

- `governance/doc_governance.md` — front-matter schema + decision rules.
- `process/self-governance.md` — bloat-prevention mechanics + the suggested numerical defaults.
- `process/fold-back-protocol.md` — when matrix changes get evaluated.
- `templates/handoff-template.md` — where `cell_size_target: 500` is instantiated.

## §9 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 8-field schema + the cell_size_target field are stable framework vocabulary. Per-doc row values evolve as the framework grows.

---

End of Δ-10 Doc responsibility matrix.
