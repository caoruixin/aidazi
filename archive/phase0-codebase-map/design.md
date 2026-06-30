# Phase-0 measurement: does the Codebase Map actually help? (pre-registered protocol)

**Type:** measurement experiment, NOT a feature. No hooks / receipts / gates / enforcement / runtime
wiring are added. Branch `feat/codebase-context-map-lite`; not pushed, not merged. Tracked artifacts:
this folder (`archive/phase0-codebase-map/`). Bulky raw transcripts live in gitignored `.runs/phase0/`.

**Question.** Does `process/codebase-map.md` reduce a fresh session's repeated scanning / input
tokens / files read and speed correct-entry localization, WITHOUT lowering analysis quality or
constraint coverage — by enough to justify (later) a thin auto-entry?

## A/B design
- **Arm A (cold start):** fresh agent session, task prompt only, no map.
- **Arm B (map-guided):** fresh session, task prompt + a briefing containing ONLY: the task-relevant
  map section(s) (responsibility + anchors + tests + canonical_docs) and `git diff map_checkpoint..HEAD`.
  NOT the full map; NO business answer beyond map-derived structural pointers.
- Held equal across arms: code checkpoint (`8e3b20f`), task text, model + reasoning effort, tool
  permissions (read-only), independent fresh session, no reuse of the other arm's conversation.

## Measurement harness (a reproducible proxy)
`codex exec --json -s read-only` is the measured agent: each invocation is an independent fresh
session; `--json` emits `turn.completed.usage` (token counts) and `command_execution` items (every
shell command → file-read/grep/tool-call counts + paths). Bounded per run by `review_runner`
(timeout + process-group kill + ≤2 attempts). **codex-exec is a PROXY for "a coding session": treat
absolute numbers as proxy values; the A/B DELTA is the primary signal.** Reasoning effort is fixed
at `medium` for both arms (cost/representativeness tradeoff; parity preserved at any fixed effort).

## Metrics (per run) — labeled by trust level
- **MEASURED (from codex --json):** `input_tokens`, `cached_input_tokens`, `output_tokens`,
  `reasoning_output_tokens`; `tool_calls`, `read_calls`, `search_calls`; `files_read_count`;
  `command_output_bytes` (read-volume proxy); `reconnect_errors`.
- **PROXY:** `localization_step` = 1-based index of the first command referencing a ground-truth
  entry file. Used INSTEAD OF wall-clock, which is contaminated by backend reconnect latency.
- **ESTIMATE:** `briefing_token_estimate` (bytes/4). The REAL briefing cost is already inside Arm B's
  measured `input_tokens` (so the net A/B token delta is briefing-cost-inclusive by construction).

## Task set (pre-registered, `tasks.json`)
12 tasks, 6 categories × 2 (single-module localize / cross-module bug / feature-impact /
unknown-entry / test-failure / tiny-grep-faster). All ground-truth anchors were grep-verified
present at `8e3b20f`. Sourced from real repo structure + historical fixes. Tiny tasks (cat 6) are
deliberately grep-friendly to test whether the ~600-tok briefing fixed cost is wasteful there.

## Quality rubric (fixed before viewing outputs)
6 binary dims (0/1), max 6: `correct_entry_point`, `dependency_completeness`, `constraint_coverage`,
`test_coverage`, `no_fabrication`, `solution_plausibility`. Scored against the pre-registered
`ground_truth` AFTER runs. Ground truth and rubric are frozen in `tasks.json` before any arm runs.

## Anti-bias controls
- A/B order alternates by task index; arms are independent sessions.
- The briefing is generated MECHANICALLY by `briefing_select.py` from the task prompt vs the map's
  own keywords only — it never reads `ground_truth`. (Validated: GT section is in the top-3 selection
  for 12/12 tasks WITHOUT any GT peeking; briefing ≈ 515–665 tok, mean ≈ 602.)
- Raw prompts, transcripts, read traces, and metrics are retained under `.runs/phase0/`.
- Scoring uses fixed ground truth; no post-hoc rubric changes.

## Decision criteria (→ `decision-memo.md`)
Report: A/B summary table; per-category benefit/regression; briefing fixed cost; mean & median
deltas (input tokens / files read / localization step); quality deltas; which categories the map
helps; which tiny tasks are better served by direct grep; map maintenance cost; and a
data-supported recommendation on whether a thin auto-entry is worth building.

**Suggested "proceed" bar (not cherry-picked):** for medium/large tasks, a stable, clear net
input-token or read-volume reduction (reference ≥20%); localization accuracy & constraint coverage
do NOT drop; tiny tasks can skip the briefing without penalty; map upkeep cost ≪ cumulative savings.
If the benefit is not significant, the honest conclusion is "do NOT build the auto-entry." Do not
select favorable data to justify the approach.

## Reproduce
1. `python3 archive/phase0-codebase-map/run_phase0.py --tasks all --effort medium`
2. Per-run metrics under `.runs/phase0/<task>-<arm>/metrics.json`; aggregate `results.json`.
3. Scoring + aggregation → `score.py` / `decision-memo.md` (committed); raw transcripts stay in `.runs/`.
