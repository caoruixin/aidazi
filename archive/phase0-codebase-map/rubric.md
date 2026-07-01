# Phase-0 per-run quality rubric (6 dimensions, all 24 runs)

Addresses Codex review R1 non-blocking #5 (make the "no quality degradation" claim auditable).
Each dimension is 0/1. Objective dims (entry/test/no_fab) are auto-checked vs the frozen
`tasks.json` ground truth; `dependency`/`constraint`/`plausibility` are agent judgment from reading
the full `final_answer` of every run (raw answers in `.runs/phase0/<run>/metrics.json`). Scores
machine-generated into `.runs/phase0/rubric.json`.

Dimensions: **E**=correct_entry_point, **D**=dependency_completeness, **C**=constraint_coverage,
**T**=test_coverage (N/A→1 for tasks with no GT test), **F**=no_fabrication, **P**=solution_plausibility.

| run | E | D | C | T | F | P | total |
|---|---|---|---|---|---|---|---|
| t1a-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t1a-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t1b-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t1b-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t2a-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t2a-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t2b-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t2b-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t3a-A | 1 | 1 | 1 | 0 | 1 | 1 | 5 |
| t3a-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t3b-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t3b-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t4a-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t4a-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t4b-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t4b-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t5a-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t5a-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t5b-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t5b-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t6a-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t6a-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t6b-A | 1 | 1 | 1 | 1 | 1 | 1 | 6 |
| t6b-B | 1 | 1 | 1 | 1 | 1 | 1 | 6 |

**Totals: 143/144.** Arm A mean 5.92/6, Arm B mean 6.00/6 — quality is **equal between arms** (the
only miss is t3a-A failing to name the GT test, which Arm B caught). **No quality degradation from
the map; Arm B was marginally more complete.**

**Fabrication check (F):** the automated path-existence proxy flagged **3 runs / 7 path tokens**
(t1b-B, t2a-A, t4b-B); all verified **false positives** — abbreviated paths (`quickfix/launcher.py`
for `engine-kit/quickfix/launcher.py`; `data/context_budget_baseline.yaml`; `tests/test_driver.py`)
or elided runtime artifacts (`.runs/.../campaign-state.json`). No hallucinated files/symbols in any run.

**Important validity note (post de-leak):** the de-leaked briefing carries NO answers, so Arm-B's
correctness was earned by opening the anchored files. E.g. t6a-B correctly reported
`AIDAZI_ALLOW_REAL_ADAPTER=1` and t6b-B reported "9" although neither value appears in their
briefings — confirming the map's contribution is structural pointing, not answer leakage.
