---
title: Doc lifecycle rules (Δ-4)
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
size_target: 6KB
notes: >
  Δ-4 KEEP per v4-plan §4.1: live vs intermediate distinction (front-matter
  doc_category). Companion of governance/doc_governance.md §5 (which defines
  the schema + decision rules); this Δ defines the lifecycle PRINCIPLES + how
  the categories interact with action_bank archive / sprint archives /
  lessons / proposals.
---

# Doc lifecycle rules (Δ-4)

The framework's `doc_category` front-matter takes one of two values: `live` or `intermediate`. This Δ defines the lifecycle principles — when each category applies, what edits are permitted, and how the categories interact with the framework's other archival mechanisms.

`governance/doc_governance.md` §5 carries the schema + decision rules; this Δ carries the principles + the failure mode that motivates the split.

## §1 Why two categories

Without this split, the project ends up with one of two failure modes:

- **The eternal living doc** — every doc is live; every edit "improves" the doc; readers cannot tell what's stable vs in flux. The doc says version N but reflects state of git HEAD; downstream consumers anchor on stale claims. csagent's Δ-4 origin trace cites this pattern.
- **The frozen swamp** — every doc is intermediate; nothing maintains. Reality drifts; every doc is wrong; readers have to spot-check git log to find the "current" answer. Foundational specs become history-of-thought rather than guide-to-now.

The split exists so each category carries a specific lifecycle commitment that matches reader expectations:

- `live` carries a commitment to track reality.
- `intermediate` carries a commitment to freeze at creation.

## §2 The two categories

### §2.1 `live`

- **Lifecycle commitment**: actively maintained against reality.
- **Required front-matter**: `last_reviewed`, `review_cadence`, `source_of_truth`.
- **Edit posture**: edits are EXPECTED at the declared cadence. Stale `last_reviewed` is a signal, not a failure.
- **Typical examples**:
  - All `governance/*` docs.
  - All `process/*` docs.
  - All `role-cards/*` agent role cards.
  - All `templates/*` template docs.
  - All `modules/*` module specs.
  - `docs/research-briefs/<id>.md` (live until milestone close; THEN archived intermediate).
  - `docs/current/*` adopter-side runtime contracts.
  - `docs/action_bank.md`.
  - `docs/handoff.md` (project-wide; live).

### §2.2 `intermediate`

- **Lifecycle commitment**: frozen at creation.
- **Required front-matter**: `last_reviewed` records creation date; no `review_cadence`.
- **Edit posture**: modifications limited to typos, broken-link fixes. Semantic edits are FORBIDDEN — file a new doc that references the old one.
- **Typical examples**:
  - All sprint archives (`docs/sprints/<sprint-id>/*`).
  - `docs/proposals/<id>.md` (informal exploration; frozen at creation).
  - `docs/diagnostics/<id>.md` (mid-sprint root-cause notes).
  - `docs/diagnostics/failure-briefs/<id>.md` (formal 6-field failure brief).
  - `docs/acceptance-reports/<scope>-acceptance-report.md` (per scope).
  - `aidazi/lessons/<date>-<topic>.md` (frozen at filing; status field changes via new commit, not body edit).
  - `aidazi/archive/*`.

## §3 Edit decision rules

When something needs to change in a doc, walk the rules in order:

1. **What's the doc's `doc_category`?**
   - `live` → continue.
   - `intermediate` → STOP. Semantic edits forbidden. File a new doc (sprint archive supersedes; diagnostic gets a follow-up diagnostic; failure-brief gets a NEW failure-brief with cross-link).

2. **Is the edit consistent with the doc's `source_of_truth`?**
   - YES → edit; update `last_reviewed`.
   - NO → check `governance/doc_governance.md` §7 (code-ahead-of-docs / docs-ahead-of-code / true-conflict / stale-references / future-proposals).

3. **For governance-tier live docs**: walk Constitution §8 editing-discipline checks (timelessness; principle-vs-current-state; necessity; durable-shift-vs-reaction).

4. **For process-tier live docs**: edit lands at fold-back sub-sprint cadence (per `process/fold-back-protocol.md` §2) — not mid-milestone.

5. **For adopter-side live docs** (e.g., `docs/current/runtime_invariants.md`): edit lands at the cadence declared in front-matter; typically `per milestone close` for runtime contracts.

## §4 Interaction with action_bank archive

`docs/action_bank.md` is live (carries open items only). `docs/action_bank_archive.md` is intermediate (closed items; append-only).

When an item closes:
1. Remove from `action_bank.md` (live edit).
2. Append to `action_bank_archive.md` in the appropriate section (§A sprint / §B milestone / §C R-item per `process/milestone-framework.md` §4).
3. Archive sweep is MANDATORY at milestone close per `process/delivery-loop.md` §4.2.3 (via `close_taxonomy_C_or_D` MANDATORY_CHECKPOINT covering close conversations).

## §5 Interaction with lessons

`aidazi/lessons/<date>-<topic>.md` is intermediate. The lesson body is frozen at filing.

The `status:` field changes (proposed → under-review → accepted | rejected) but those changes are recorded in NEW commits on the lesson file with the `status:` line updated; the body remains frozen.

This is enforced because lessons are evidence for fold-back decisions — editing the lesson body retroactively destroys the evidence trail.

Rejected lessons move to `aidazi/archive/rejected-lessons/<date>-<topic>.md` (still intermediate) with the Rejection rationale section filled by the framework maintainer.

## §6 Interaction with proposals

`docs/proposals/<id>.md` is intermediate (frozen at creation). If a proposal "evolves" — the next round of thinking — author a NEW proposal that references the prior one. Do NOT re-edit the old proposal.

The discipline is: a proposal is a snapshot of "what we were thinking on date X." Editing it loses the snapshot.

If a proposal matures into a research-brief (the Research Agent re-runs formally), the research-brief is a separate live doc; the proposal stays intermediate.

## §7 Conversion between categories

A doc MAY change category over its lifecycle:

- `docs/research-briefs/<id>.md` is `live` until milestone close; then archived to `docs/sprints/<milestone-id>/` and category flips to `intermediate`.
- `docs/sprint_objective.md` is `live` for the sub-sprint; then archived to `docs/sprints/<sprint-id>/` and category flips to `intermediate`.

The conversion happens at archive time (typically milestone close OR sub-sprint close). After conversion, the same edit-posture rules apply — semantic edits forbidden on the intermediate copy.

## §8 What this Δ does NOT cover

- Front-matter schema details — see `governance/doc_governance.md`.
- Doc-bloat prevention mechanics — see `process/self-governance.md` §7.
- Fold-back cadence triggers — see `process/fold-back-protocol.md` §2.
- Sprint archive structure — see `process/milestone-framework.md` §4.

## §9 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The two-category split + the lifecycle-commitment language is stable framework vocabulary. Adopters MAY add a third category locally (e.g., `transient` for content meant to live only days) with rationale; the framework's universal tooling depends on the two defaults being honored.

---

End of Δ-4 Doc lifecycle rules.
