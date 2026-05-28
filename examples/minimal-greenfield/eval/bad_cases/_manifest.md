---
title: Bad-case suite manifest
doc_tier: current-runtime
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: per milestone close
notes: >
  Lifecycle ledger for the curated bad-case suite. Per
  `framework/governance/constitution.md` §5.6.
---

# Bad-case suite manifest

## Tier definitions (per §5.6.1)

- **`core`**: load-bearing across all milestones. Re-run at every
  milestone close.
- **`scope-relevant`**: relevant to specific architectural surface;
  re-run only when closing milestone's §5 names this case.
- **`closed-as-regression-guard`**: PASS in N≥2 consecutive closes;
  runs automatically; auto-promotes back to active if terminal_outcome
  re-fails.
- **`archived`**: failure surface structurally removed; kept as
  history; requires joint deliver + human decision.

## Active cases

| Case id | Tier | Source | Surfaced date | Failure shape | Closure status |
|---------|------|--------|---------------|---------------|----------------|
| `<id-001>` | core | <real session / sprint finding / external> | <YYYY-MM-DD> | <one line> | active |
| `<id-002>` | scope-relevant | <source> | <date> | <one line> | active |

## Closed-as-regression-guard cases

| Case id | Tier transition | N consecutive PASS | Last close PASS at |
|---------|-----------------|--------------------|--------------------|
| `<id-XXX>` | core → guard | 2 (M2 + M3) | M3 close |

## Archived cases

| Case id | Original tier | Archived at | Reason |
|---------|---------------|-------------|--------|
| `<id-YYY>` | core | M<N> close | Structural source removed in M<N-1> S<X> |

## Per-milestone manual review log

| Milestone close | Cases reviewed | Verdicts (PASS/FAIL/IMPROVING) | Notes |
|-----------------|----------------|-------------------------------|-------|
| M0 close | <list> | <list> | <one line> |
| M1 close | <list> | <list> | <one line> |
