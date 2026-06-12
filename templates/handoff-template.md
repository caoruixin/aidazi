---
title: Handoff — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
load_discipline: by-role
size_target: 10KB
cell_size_target: 500
notes: >
  Template for <adopter>/docs/handoff.md (or per-sprint
  docs/sprints/<sprint-id>/handoff.md). §0 cold-start table; §1 narrative;
  §2 archive index; §1-§11 are Dev-authored at sub-sprint close; §12 is
  RESERVED for Deliver + Customer close verdict. cell_size_target: 500
  is a SUGGESTED default per Constitution §7.0; adopters override with
  rationale in adoption-state.md.
---

# Handoff — template

Copy this template to your adopter as `docs/handoff.md` (live, top-level) for ongoing project-wide cold-start state, AND/OR to `docs/sprints/<sprint-id>/handoff.md` for per-sub-sprint handoff. Same structure; different lifetime.

The handoff is the durable, cold-loadable artifact that lets a fresh role session pick up state without chat-history backchannel (Constitution §3.4 invariant #1).

---

## §0 — Cold-start state table

The §0 table lets a fresh session reconstruct the project's current shape in one read. Each cell SHOULD stay under `cell_size_target` characters (suggested 500); cells exceeding the target should point to §1 narrative for detail rather than packing prose into the table.

```markdown
| Field | Current state |
|---|---|
| Project name | <project> |
| Track | type_a / type_b / type_c / type_a_b_hybrid |
| Framework version | v4.0.0 |
| Current milestone id | <milestone-id> |
| Current sub-sprint id | <sprint-id> |
| Current milestone closure_contract source | docs/research-briefs/<id>.md |
| Last close verdict | A / B / C / D (subclass) |
| Open R-items count | <integer> (live docs/action_bank.md) |
| Open OBS-items count | <integer> |
| Acceptance calibration | calibrated / uncalibrated (n/a if manual mode) |
| Autonomy level (current charter) | human_in_the_loop / on / fully_autonomous_within_budget |
| Last Dev session ended | <YYYY-MM-DD> sprint-NNN |
| Last Code Reviewer verdict | pass / fix_required / out_of_scope_review |
| Last Acceptance verdict | pass / fix_required / needs_human / not_yet_run |
| Pending Customer checkpoints | <count> (docs/checkpoints/*.md with decision: pending) |
| Recent diagnostic count | <integer> (last sprint) |
```

**Cell-size discipline** (`cell_size_target: 500` suggested per `process/self-governance.md` §7.2):

- Cells over the target = R-item candidate (NOT auto-rejected; adopter judges).
- Override the target by setting `cell_size_target: <higher>` in this file's front-matter AND documenting rationale in `docs/current/adoption-state.md`.

## §1 — Narrative

Free-form prose. The story the §0 table can't tell:

- Why the current milestone exists (cite research-brief id + reasoning).
- What the last sub-sprint actually accomplished + the open thread it leaves.
- Decisions made since last handoff revision.
- Notable diagnostics filed (cross-ref `docs/diagnostics/<id>.md`).
- Risks the team is carrying.

Length budget: typically 200-800 words. Longer means §1 has absorbed content that belongs elsewhere (R-items in action_bank; diagnostics in their own dir).

## §2 — Archive index

```markdown
| Sprint | Closed | Verdict | Path |
|---|---|---|---|
| sprint-NNN | YYYY-MM-DD | A / B / C / D | docs/sprints/sprint-NNN/handoff.md |
| ... | | | |
```

The archive index lets a fresh session walk the project's history without git-log archaeology. Each row points at the frozen per-sprint handoff.

## §1-§11 — Dev fills (per sub-sprint)

When the handoff is per-sub-sprint (`docs/sprints/<sprint-id>/handoff.md`), Dev Agent writes the following at sub-sprint close (per `role-cards/dev-agent.md` §5):

### §3 — Files touched + diff summary

(Dev fills.)

### §4 — Tests added + pass/fail status

(Dev fills.)

### §5 — Behavior change summary

Cite the dev prompt's contract; show the deliverable.

(Dev fills.)

### §6 — Trace contract impact

Per Δ-12 / `process/artifact-taxonomy.md`.

(Dev fills.)

### §7 — Bad-case suite run results

Which cases pass / fail after this sub-sprint's changes.

(Dev fills.)

### §8 — Architecture-health metric impact

Per `process/architecture-health-metrics.md`.

(Dev fills.)

### §9 — Open questions / detected risks

File OBS-items per Δ-9 if applicable.

(Dev fills.)

### §10 — Diagnostics produced

Cross-reference `docs/diagnostics/<id>.md` entries.

(Dev fills.)

### §11 — Deferred work

R-items for `docs/action_bank.md`.

(Dev fills.)

### §12 — Self-check + close

(Dev fills self-check; Deliver + Customer fill close verdict.)

Sub-sections:

- **§12.1 Dev self-check** — per the dev prompt's self-check rules; record results. Includes self-containment integrity check (was the dev prompt actually self-contained? if not, file a diagnostic).
- **§12.2 Deliver close verdict** — A / B / C / D + subclass + JSON per `schemas/deliver-close-verdict.schema.json`.
- **§12.3 Customer co-sign** (where applicable) — Customer countersigns for verdicts B (substantive fix) or C/D (`close_taxonomy_C_or_D` MANDATORY_CHECKPOINT resolution).

§12 is the ONLY section Dev does NOT solely author; Deliver + Customer write §12.2 and §12.3.

## Boundary rules

- Dev writes §3-§11 + §12.1.
- Deliver writes §12.2.
- Customer countersigns §12.3 where required.
- Deliver MAY draft handoff §0 scaffolds + §1 narrative skeleton; per `role-cards/deliver-agent.md` §4.1 (Deliver may scaffold but not edit feature/test code).
- The handoff is `live` for the top-level project version and `intermediate` (frozen at sub-sprint close) for per-sub-sprint copies.

## Template usage notes

- For the project-wide `docs/handoff.md` (live), only §0 + §1 + §2 are typically populated; §3-§12 belong to per-sub-sprint copies.
- For per-sub-sprint `docs/sprints/<sprint-id>/handoff.md` (intermediate), all sections are filled at close.
- The `cell_size_target` field can be overridden per adopter — multi-team production projects naturally carry more context per row (`cell_size_target: 1000`); single-person hobby projects may stay terse (`cell_size_target: 250`). Document the override rationale in `docs/current/adoption-state.md`.
- The §0 → §1 split is the bloat-prevention mechanism: cold-start can read §0 fast; rich detail lives in §1; archived sprint copies hold §3-§11 for history without cluttering live.

---

End of handoff template.
