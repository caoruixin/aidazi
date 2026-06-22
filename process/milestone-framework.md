---
title: Milestone framework
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
size_target: 14KB
split_trigger: if §3 milestone objective schema grows past 4KB, split to docs/milestone-objective-detail.md
notes: >
  Promoted from csagent docs/current/process/milestone-framework.md (csagent
  §8 + §4.3) per v4 build plan. v4 framing: references Constitution + Δ
  numbering instead of csagent-internal §-numbers. Defines the milestone /
  sub-sprint relationship, milestone-shared review convention, and the
  per-sub-sprint review triggers that fire regardless of milestone framing.
---

# Milestone framework

A **milestone** is a coordinated bundle of sub-sprints sharing one architectural theme. Milestones are the planning horizon between R-items (backlog) and sub-sprints (execution unit). This doc defines the relationship + the milestone-shared Code Reviewer convention + the per-sub-sprint review triggers that fire regardless of milestone framing.

## §1 Milestone definition

A milestone has:

- **One milestone objective document** at `docs/milestone_objective.md` (live; archived to `docs/sprints/<milestone-id>/milestone_objective.md` at milestone close).
- **3-5 sub-sprint contracts** (suggested default per Constitution §7.0; adopters may override).
- **One milestone acceptance bar** derived from the curated bad-case suite per `process/badcase-lifecycle.md` — typically one or more named bad cases must close or improve materially.
- **Acceptance verdict at milestone close** per Constitution §3.4 + §3.5 (`tooling.acceptance.run_at: milestone_close` or `both`).
- **Code Reviewer verdict at milestone close** per §2 below.

A **sub-sprint** within a milestone is a single dev-session unit of work that ships a coherent slice of the milestone scope. Each sub-sprint:
- Has its own sprint stanza (`schemas/sprint_stanza.schema.json`) if semantic-touching.
- Produces a `docs/sprints/<sprint-id>/handoff.md` Dev-authored archive at sub-sprint close.
- Flips relevant R-items in `docs/action_bank.md`.
- Defers Code Reviewer to milestone close per §2 default (unless a per-sub-sprint trigger fires).

## §2 Milestone-shared Code Reviewer convention

Per the milestone framework: sub-sprints within an active milestone MAY share a single Code Reviewer review at **milestone close** rather than dispatching per sub-sprint. The 9-question anti-hardcode kernel (`templates/anti-hardcode-review-kernel.md`) and the 4-line sprint-close header are written once per milestone, against the cumulative commit range of all sub-sprints in the milestone.

### §2.1 Per-sub-sprint review remains REQUIRED when

(One or more conditions triggers per-sub-sprint dispatch; the others may stay in the shared milestone review.)

1. **New Tier-0 candidate** — sub-sprint introduces a candidate invariant for `docs/current/runtime_invariants.md`. Triggers `new_tier0_candidate` MANDATORY_CHECKPOINT (per `process/delivery-loop.md` §4.2.3 item 4).
2. **§1.7 red line** — sub-sprint crosses a Constitution §1.7 forbidden-list red line. Triggers `forbidden_list_redline` MANDATORY_CHECKPOINT (per `process/delivery-loop.md` §4.2.3 item 5).
3. **Hard-fenced surface** — sub-sprint touches a surface the milestone objective explicitly named out of scope (e.g., editing existing case family per cascade fence).
4. **fix_required follow-up** — sub-sprint closes with `fix_required` outcome that needs per-sub-sprint re-review.

For default sub-sprints (semantic-touching but not Tier-0-adjacent, not §1.7-adjacent, not hard-fence-violating, not fix-iteration on a prior sub-sprint), Code Reviewer is deferred to milestone close. Deliver Agent surfaces the per-sub-sprint deferral choice in `docs/milestone_objective.md` and Dev Agent records it in each sub-sprint handoff §11.

### §2.2 Anti-hardcode exemption clause

Sub-sprints exempted from the sprint stanza (pure infra, docs-only, config-governance, characterization-test) remain Code Reviewer-exempt per `templates/anti-hardcode-review-kernel.md` exemption clause regardless of milestone framing.

## §3 Milestone objective document schema

`docs/milestone_objective.md` carries front-matter + body sections per `templates/milestone-objective.md`. This section defines body section semantics; the template is the literal copy-target.

Body sections:

1. **Milestone class** — semantic-touching layer breakdown across sub-sprints.
2. **Goal** — architectural outcome expressed as user-facing or bad-case-suite-anchored behavior change (NOT as code paths).
3. **Sub-sprint sequence** — preliminary list of 3-5 sub-sprints with class, layer, scope (3 sentences each), and dependency relationships.
4. **Non-goals** — explicit; what milestone does NOT cover.
5. **Milestone acceptance bar** — one or more bad cases per `process/badcase-lifecycle.md` expected to close or improve.
6. **Hard fences** — at milestone level.
7. **R-items consumed / surfaced** — which `action_bank.md` R-items milestone is expected to consume; which new R-items expected to surface.
8. **Code Reviewer review plan** per §2 — default milestone-shared OR per-sub-sprint triggers expected.
9. **Estimated milestone duration** — calendar weeks; informational, not a gate.

## §4 Milestone close artifacts

At milestone close, Deliver Agent + Customer produce:

- Update `docs/milestone_objective.md` closure verdict (pass / fix_required / out-of-scope-review + classification per `templates/deliver-close-taxonomy.md` + per-sub-sprint disposition).
- Archive milestone objective to `docs/sprints/<milestone-id>/milestone_objective.md`.
- Append milestone's closed rows to `docs/action_bank_archive.md` per action_bank retention sweep: closed per-sprint rows → §A, closed-milestone row → §B, newly-closed R-item rows → §C. (`docs/action_bank.md` keeps only open / active / deferred items.)
- Refresh `docs/handoff.md` §0 table + §1 lead (demote current milestone to Preceding milestone; truncate §1 content older than preceding milestone per `governance/doc_governance.md` retention; add row to §2 archive index).
- Reset `docs/sprint_objective.md` to first sub-sprint of next milestone (or planning placeholder).
- Optionally start new `docs/milestone_objective.md` for next milestone.

Deliver Agent's close-out artifacts move from per-sprint to per-milestone cadence; per-sub-sprint Dev handoff files still ship per sub-sprint close.

## §5 When to break milestone framing

The framework is not mandatory. A single high-risk feature MAY be its own "milestone of one sub-sprint" if that better matches the scope discipline. Deliver + Customer decide at planning round.

A milestone that exceeds 5 sub-sprints is a signal that milestone scope is too large; Deliver SHOULD split at next milestone planning round.

A sub-sprint that crosses an unrelated architectural surface is a signal that sub-sprint belongs to a different milestone; Deliver SHOULD surface this at sub-sprint planning round rather than smuggle scope across milestones.

## §6 Sprint vs milestone vs R-item relationship

```
docs/action_bank.md       (backlog, cross-milestone persistent;
                           R-items flow in from research / bad cases /
                           sprint findings, flow out on close)
       ↓ (Deliver picks 3-5 related R-items into a milestone)
docs/milestone_objective.md  (current milestone north star;
                              names sub-sprints + acceptance bar;
                              archived to docs/sprints/<milestone-id>/
                              at close)
       ↓ (Deliver picks one sub-sprint contract from milestone)
docs/sprint_objective.md  (current sub-sprint dev/review contract;
                           archived to docs/sprints/<sprint-id>/
                           at sub-sprint close)
```

R-items are persistent backlog. Milestones are planning horizon. Sub-sprints are execution unit.

- Dev Agent consumes sub-sprint contract.
- Code Reviewer Agent consumes either sub-sprint or milestone (per §2).
- Acceptance Agent consumes milestone (closure_contract source = research-brief; verdict source = milestone evidence per F5).
- Deliver Agent + Customer consume all three layers.

## §7 Commit-at-end bundling

In commit-at-end workflows, Dev working trees accumulate uncommitted Deliver-Agent-owned files. Dev SHOULD stage only authorized-scope files (NOT `git add -A`); Deliver files are bundled by Customer at close commit. If bundled anyway, classify per `templates/deliver-close-taxonomy.md` A-with-packaging-note.

## §8 Backwards compatibility (adopter-side)

A sub-sprint started without an explicit milestone (e.g., a single-feature follow-on between milestones) is allowed; it defaults to "milestone-of-one" framing per §5 and follows per-sprint conventions for Code Reviewer dispatch, Deliver close, etc.

Pre-milestone-framework sprints in an adopter's history do NOT retroactively become milestones. They remain in their original sprint archives unchanged.

## §9 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8. The numerical defaults (3-5 sub-sprints; per-sub-sprint review triggers list) are suggested per Constitution §7.0; adopters may extend the trigger list (e.g., add domain-specific trigger) but should not subtract triggers 1 and 2 (Tier-0 + §1.7 red line) — those map to MANDATORY_CHECKPOINTS that cannot be bypassed (§1.7-D).

---

End of Milestone framework.
