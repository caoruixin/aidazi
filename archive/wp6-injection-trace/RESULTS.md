# WP-6 realistic injection trace

Reproduce from repo root: `python3.12 archive/wp6-injection-trace/trace.py`

A representative dev-scoped Loop-Memory store (MATURED, L2, PROMOTED, an
explicitly-superseded MATURED, a byte-identical L2 duplicate, and 6 L1
singletons), bounded with `LessonBudget(max_l1_count=3)`. Shows the agent-facing
block + the spawn audit: every tier handled, every suppression reason exercised
(superseded / duplicate / l1_count_budget), the non-silent footer, and complete
accounting (selected ∪ suppressed = all 12 candidates).

```
=== AGENT-FACING INJECTED BLOCK (realistic trace, budget L1<=3) ===

## Relevant prior lessons (Loop Memory)
(generalizable heuristics from earlier loops — not rules to memorize; apply judgement)
- [L2] Enumerate each refund branch explicitly; a catch-all regressed partial-refund twice before.
- [PROMOTED] (encoded in: test:test_idempotent_dispatch, kernel:constitution-core§3.4) Make the dispatch commit idempotent so a crash-resume cannot double-ship.
- [L2] Retry ONLY the failed sub-step on a flake, never the whole sprint.
- [L2] Validate the nullable FK before the write; two loops hit the same constraint trip.
- [L1] Singleton #0: under condition C0, prefer A0 because R0.
- [L1] Singleton #1: under condition C1, prefer A1 because R1.
- [L1] Singleton #2: under condition C2, prefer A2 because R2.
_(Loop Memory bounded: 5 lower-priority prior lesson(s) suppressed to limit context; full record in the spawn audit suppressed_lesson_ids.)_


=== AUDIT (lesson_selection) ===
selected   : ['matured-guard', 'promoted-idempotency', 'new-retry', 'validated-null', 'singleton-00', 'singleton-01', 'singleton-02']
suppressed : [('old-retry', 'superseded', 'MATURED'), ('validated-null-dup', 'duplicate', 'L2'), ('singleton-03', 'l1_count_budget', 'L1'), ('singleton-04', 'l1_count_budget', 'L1'), ('singleton-05', 'l1_count_budget', 'L1')]
tiers      : {'old-retry': 'MATURED', 'matured-guard': 'MATURED', 'promoted-idempotency': 'PROMOTED', 'new-retry': 'L2', 'validated-null': 'L2', 'validated-null-dup': 'L2', 'singleton-00': 'L1', 'singleton-01': 'L1', 'singleton-02': 'L1', 'singleton-03': 'L1', 'singleton-04': 'L1', 'singleton-05': 'L1'}
reps       : {'matured-guard': 'full', 'promoted-idempotency': 'compact', 'new-retry': 'full', 'validated-null': 'full', 'singleton-00': 'full', 'singleton-01': 'full', 'singleton-02': 'full'}
bytes      : 986 -> 885  tokens: 246 -> 221
```
