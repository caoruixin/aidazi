---
title: Self-governance — bloat prevention + hard-vs-suggested mechanics
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 16KB
split_trigger: if any mechanism's section grows past 4KB, move to a dedicated process/ doc
notes: >
  Framework anti-bloat / anti-drift mechanics. Defines structural mechanisms
  (front-matter fields, size targets, sweep cadences) that prevent doc-bloat /
  context-bloat / governance-drift over time. Mirrors Constitution §7's
  hard-requirements vs suggested-defaults split: §7.0 lists what's hard
  (immutable); §7.1-§7.7 list suggested defaults (overridable per
  adoption-state.md rationale). Companion of `process/fold-back-protocol.md`.
---

# Self-governance

The framework must prevent doc-bloat / context-bloat / governance-drift over time.

This file covers the **structural mechanisms** — the front-matter fields, the template scaffolding, the review prompts — that hold the discipline. It does NOT enforce specific numerical values; those are suggested defaults (per Constitution §7.0). Hard requirements (cannot be overridden) are itemized in §7.0 below.

The fold-back protocol that REVIEWS these mechanisms at cadence lives in `process/fold-back-protocol.md`.

## §1 Scope

Six mechanisms:
1. **Doc-responsibility-matrix size_target + split_trigger** (Δ-10 extended; §7.1).
2. **Handoff §0 cell-size guidance** (§7.2; suggested per Constitution §7.0).
3. **Action_bank live + archive split** (Δ-12 carried; §7.3).
4. **Live vs intermediate doc lifecycle** (Δ-4 carried; §7.4).
5. **Compact prompt artifact size discipline** (Δ-5 + Δ-9 carried; §7.5).
6. **Lessons-learned doc retention** (§7.6).

Plus:
- §7.0 — Hard requirements (immutable subset).
- §7.7 — Self-governance review cadence.

## §7.0 Hard requirements (cannot be overridden — framework breaks if violated)

Itemized here for self-governance review purposes; the canonical statement is Constitution §7.0.

- **Constitution §1.7 forbidden list** (incl. v4 additions §1.7-A through §1.7-E).
- **Constitution §3.4 5-role boundary invariants**:
  - No self-grading.
  - Acceptance spawn isolation (§1.7-C).
  - Code-Reviewer ≠ Acceptance lens distinction.
  - Research-Acceptance contract symmetry.
  - Deliver-does-not-write-code.
- **`process/delivery-loop.md` §4.2.3 — 9 MANDATORY_CHECKPOINTS** — if Δ-18 orchestrator adopted, all 9 fire (the 9th, `advisory_acceptance_pass_signoff`, only when Acceptance runs advisory); charter MAY add; charter MAY NOT BYPASS in any of the four shapes (omitted / emptied / disabled / overridden) per §1.7-D + `process/delivery-loop.md` §4.2.2 charter editing rules.
- **Constitution §3.6 Acceptance judge calibration** — if Acceptance enabled in `fully_autonomous_within_budget` mode, calibration is required; uncalibrated → automatic degradation to `human_on_the_loop`. Degradation is not optional; orchestrator implements it.
- **Δ-19 `customer_disposition` is Customer authority, never LLM** (`archive/2026-06-23-requirement-ledger-design.md` §4.E; Constitution §1.3/§1.7). No agent/engine writes a requirement ledger's `customer_disposition` — agents *propose*, only the Customer sets it. `delivery_status` is a DERIVED `scope_report` projection, never authored/written back (preserves the Acceptance role boundary). Enforced by construction (there is no engine write path to the ledger).

Violations of hard requirements are framework breaches, not adopter customizations. They are NOT eligible for `status: divergent` in `docs/current/adoption-state.md`.

## §7.1 Doc-responsibility matrix — size_target + split_trigger (Δ-10 extended)

Every doc in `governance/`, `process/`, `templates/`, `role-cards/` carries front-matter:

```yaml
load_discipline: always-load | on-demand | by-role
size_target: <KB>
split_trigger: <description-of-when-to-split>
cell_size_target: <chars; for table-cell docs>   # NEW v4; SUGGESTED per Constitution §7.0
```

When a doc exceeds `size_target`, `split_trigger` fires. Code Reviewer is briefed to flag bloat as a PR finding. **Mechanical at-the-PR-boundary**, not periodic cleanup.

**Suggested initial values** (override with rationale in adoption-state.md):

| Doc tier | Suggested `size_target` |
|---|---|
| `governance` | 20-60 KB; constitution highest; doc_governance + context_briefing ~20 |
| `process` | 4-50 KB per Δ; delivery-loop is the largest |
| `role-card` | 4-8 KB |
| `template` | 2-8 KB |
| `application-guide` (docs/) | 4-16 KB per doc |
| `module` | 8-20 KB |

Starting points. Past csagent scan revealed splits driven by `size_target` exceeded → reviewer flagged → fold-back.

## §7.2 Handoff §0 cell-size guidance (suggested per Constitution §7.0)

`docs/10-handoff.md` §0 cells naturally grow to multi-thousand-char paragraphs in production projects, eroding cold-start readability.

v4 SUGGESTS as a starting point (per Constitution §7.0 — adopters may override with rationale):
- `cell_size_target: 500` chars per §0 cell.
- If a §0 cell exceeds the target, point to §1 narrative for detail.
- Bloated cells beyond chosen target = R-item candidate for next sprint (NOT auto-rejected; adopter judges).

**Why suggested, not hard**:
- Single-person hobby project: cells can stay terse (500 may even be high).
- Multi-team production project: cells naturally carry more context per row (1000+ may be necessary).
- Mature project with rich state: per-cell soft cap might not be the right discipline at all.

**Structural provision**:
- Front-matter `cell_size_target:` field exists in `templates/handoff-template.md`.
- Default value 500 chars (suggested starting point).
- Adopter overrides by setting their own value + documenting rationale in adoption-state.md.

## §7.3 Action_bank live + archive split (Δ-12 carried)

- Live `action_bank.md` carries OPEN items only.
- Suggested soft size budget: **160 KB target**.
- If exceeded → forced sweep.
- `action_bank_archive.md` (append-only) carries closed items in §A sprint / §B milestone / §C R-item sections.
- Sweep is MANDATORY at milestone close (`close_taxonomy_C_or_D` MANDATORY_CHECKPOINT covers this).
- Cross-links use stable IDs, NOT `[[wiki-style]]`.

Size budget is suggested per Constitution §7.0; adopters may raise or lower with rationale.

## §7.4 Live vs intermediate doc lifecycle (Δ-4 carried)

Front-matter `doc_category: live | intermediate`:
- `live` → has `last_reviewed`, `review_cadence`, `source_of_truth` → MUST be kept current.
- `intermediate` → frozen at creation; named with sprint ID; modifications only for typos.

Prevents the "design doc → coding agent → stale doc unchanged for half a year" failure mode that csagent identified at Δ-4 origin.

Detail rules + which docs are typically which category live in `governance/doc_governance.md` §5.

## §7.5 Compact prompt artifact size discipline (Δ-5 + Δ-9 carried)

Every `compact/sprint-NNN-dev-prompt.md` / `compact/M<N>-review-prompt.md` / `compact/M<N>-acceptance-prompt.md` MUST have:

```yaml
context_budget:
  target_tokens: <number>
  load_list: [<files-must-load>]
  do_not_load: [<files-excluded>]
  self_contained: true
```

If `self_contained: false`, prompt is REJECTED at orchestrator preflight (per `process/delivery-loop.md` §4.2.4 `dev_pending`) OR by human reviewer in manual mode.

This is Constitution §1.4-i / Δ-5 efficiency clause as build-time check.

Specific `target_tokens` value is per-adopter (per Constitution §7.0). Suggested initial values:
- Dev prompt: 8000-16000.
- Review prompt: 6000-10000.
- Acceptance prompt: 8000-12000.

Detail rules live in `process/prompt-artifact-rules.md`.

## §7.6 Lessons-learned doc retention

`aidazi/lessons/` accumulates between fold-back sub-sprints. Adopters file lessons in `aidazi/lessons/<date>-<topic>.md` as observed (per `process/fold-back-protocol.md` §5).

At each fold-back sub-sprint:
- Lessons that triggered a Δ revision → archived (link from revised Δ doc to lesson added).
- Lessons not actioned → kept for next fold-back review.
- Lessons explicitly rejected → moved to `archive/rejected-lessons/<date>-<topic>.md` with rationale filled.

Lesson docs themselves are `intermediate` per Δ-4 — frozen at creation; not edited after filing.

## §7.7 Self-governance review cadence

Self-governance is itself reviewed.

**Trigger**: every fold-back sub-sprint (per `process/fold-back-protocol.md` §2).

**During review, framework maintainer checks bloat metrics**:
1. **Average doc size across `process/`** — should not grow > 10% per fold-back interval.
2. **Adopter-reported context-budget violations** — read `lessons/` for any lesson tagged with `bloat` or `context-budget`.
3. **Acceptance / Reviewer prompt sizes** — sample a few adopters' `compact/*` prompts; verify they stay within declared `target_tokens`.
4. **Action_bank sizes across adopters** — if multiple adopters' `action_bank.md` blow through 160 KB regularly, the suggested target is wrong.
5. **Front-matter completeness** — random sample 10 docs; check `last_reviewed` + `source_of_truth` + `load_discipline` + `size_target` fields are present + populated.

The review produces:
- One or more Δ revision PRs.
- A bloat-metric snapshot in the fold-back sub-sprint report.

## §8 Why this matters

Without these mechanisms, the framework's own doc tree drifts toward the failure modes it warns adopters about:
- **Bloat**: docs grow until unreadable; adopters skim or skip; the discipline collapses silently.
- **Drift**: foundational docs describe a v3.2 world while framework has moved to v4; new readers anchor on stale claims.
- **Erosion**: hard requirements get debated case-by-case until they're advisory; the §1.7 forbidden list becomes "well, in your case..."

The mechanisms above are deliberately structural (front-matter fields + template scaffolding) rather than imperative (a linter / CI job / script). Structural scales with adopter count without requiring per-adopter infrastructure. Fold-back cadence is when humans look at the structural signals and act.

The hard / suggested split (§7.0 vs §7.1-§7.6) is what lets the framework be opinionated where opinions are load-bearing AND accommodating where defaults are just starting points.

## §9 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence. Editing-discipline checks per Constitution §8.

The §7.0 hard-requirements list is THE canonical inventory of immutable rules. Any proposed addition to §7.0 is a substantive framework change; route through full fold-back review with adopter feedback.

The §7.1-§7.6 suggested-defaults sections are easier to revise; adopter-pattern evidence drives changes.

---

End of Self-governance.
