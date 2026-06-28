# WP-2 constitution-core behavioral canary — harness & evidence package

Reproducibility + audit package for
[`../2026-06-27-wp2-constitution-core-behavioral-canary.md`](../2026-06-27-wp2-constitution-core-behavioral-canary.md).

A/B test: arm **A** = full `governance/constitution.md` at cold-start (pre-WP-2);
arm **B** = `governance/constitution-core.md` kernel + full constitution on-demand
(WP-2 intended state). 8 adversarial scenarios × Dev/Review/Acceptance × {A,B} × 3
reps × {sonnet, opus where applicable} = **66 live `claude -p` cells**.

## Scripts (run from the worktree; paths are worktree-specific)
- `canary_runner.py` — builds the arm-appropriate inline cold-start prompt + scenario,
  spawns `claude -p --output-format stream-json` per cell (captures the real tool-call
  trace → the authoritative dim-6 "did arm B load canonical" signal). `--all` runs the
  matrix (resumable); `--cells m:role:scen:arm:rep` for one; `--smoke` for one cell.
- `score.py` — mechanical A/B aggregation (the `complied==NO` proxy — valid only for
  the refuse-scenarios — plus the dim-6 canonical-load counts). Writes `score_summary.json`.
- `prep_judge.py` — builds anonymized per-scenario bundles (`judge/<S>.input.json` +
  `<S>.key.json`) for the independent blind judge.
- `consolidate_evidence.py` — joins the blind-judge verdicts with per-cell data →
  `judge_verdicts.json` + `per_cell_results.{json,md}`.

## Evidence (committed, auditable without raw transcripts)
- `judge_verdicts.json` — every response's independent-judge verdict (id → model / arm /
  rep / verdict). **arm B 33/33 CORRECT; arm A 32/33** (the lone PARTIAL is arm A).
- `per_cell_results.{md,json}` — 66-cell primary-data table (action, complied,
  canonical-load, role-verdict, judge-verdict) + the per-scenario A/B tally.
- `score_summary.json` — mechanical scorer output.
- `*.key.json` — opaque-id → (model, arm, rep) de-anonymization keys per scenario.
- `R3.verdict.json` — the R3 blind-judge verdict array (the other six are embedded in
  `consolidate_evidence.py`'s `JUDGE_VERDICTS`, transcribed verbatim from the judges).

## Not committed
Raw per-cell transcripts (prompt + stream-json + parsed result, ~MBs) are retained
locally under `.runs/wp2-canary/runs/` (gitignored) and are regenerable from
`canary_runner.py`. The Codex confirmation prompts/output are under `.runs/reviews/`.
