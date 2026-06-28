# WP-4B acceptance-kernel WIRING — live read-trace + behavioral canary RESULTS

Date: 2026-06-28. Worktree `../aidazi-wp0`, branch `wp0-measurement`, WP-4B working tree (vs `a8ce479`).
Harness: `archive/wp4b-canary-harness/acceptance_canary.py` (`--all --reps 2 --model sonnet`).
Raw per-cell records + prompts + stream-json traces: `.runs/wp4b-canary/` (gitignored).

## Method (clean A/B on the REAL projected prompt)
Each cell is a fresh `claude -p --output-format stream-json`, cwd = the framework worktree, Read/Grep/
Glob only (a read-only judge). The prompt for **arm B** is the REAL projected acceptance prompt
(`driver._project_acceptance_prompt`, the WP-4B build) — the acceptance-kernel is EMBEDDED inline and
the prompt instructs "do NOT load `process/delivery-loop.md` / `process/role-skill-model.md`". **arm A**
is the SAME projection with the kernel removed and the instruction flipped to "you MUST load
`process/delivery-loop.md` (§4.2.x) and `process/role-skill-model.md` (§4/§6) and judge by their rules"
— i.e. the pre-WP-4B behavior (the judge consults the full canonical docs). The ONLY difference between
arms is the kernel/load instruction; an identical repo-path-mapping preamble is prepended to both.

Three scenarios, each with a deterministic planted F5 evidence fixture under `.runs/wp4b-canary/
fixtures/<scenario>/eval/runs/m1/run-001/result.json`:
- **pass** — eval executed; 19/20 relevant-in-top-5, p95 1410 ms; both thresholds met → expect `pass`.
- **fix_required** — eval executed; 11/20 relevant, p95 3300 ms; both thresholds missed → expect `fix_required`.
- **no_evidence** — only a developer code-review claim, no execution results (delivery-loop §4.2.8
  anti-pattern #5: never claim pass from code inspection) → expect `fix_required` or `needs_human`.

We parse the real tool-call trace (Read targets) AND the emitted acceptance-verdict JSON.

## Two claims, both PASS

### (1) Read-trace — arm B never reads the retired docs  → 6/6
Every arm-B (kernel) cell loaded NEITHER `process/delivery-loop.md` NOR `process/role-skill-model.md`
(`loaded_delivery_loop=False`, `loaded_role_skill=False`); it read only the role card + the compact
acceptance-verdict schema + the planted evidence (+ `docs/codex-findings.md`). The inline kernel is
self-contained — the judge follows the "do NOT load" instruction. Arm A (baseline) DID read
`delivery-loop.md` (`loaded_delivery_loop=True`) in all 6 cells, confirming the A/B contrast is real
(the baseline genuinely consults the full doc).

### (2) Behavioral — routing identical across arms, and correct  → 3/3 scenarios
| scenario | expected | arm A verdict | arm B verdict | routes agree |
|---|---|---|---|---|
| pass | pass | pass | pass | yes |
| fix_required | fix_required | fix_required (`deliver_fix_iteration`) | fix_required (`deliver_fix_iteration`) | yes |
| no_evidence | fix_required \| needs_human | needs_human (`re_acceptance_after_evidence`) | needs_human (`re_acceptance_after_evidence`) | yes |

No governance regression from inlining the WP-4A-approved delivery-loop / role-skill content: arm B
(kernel) routes pass / fix_required / needs_human exactly as arm A (full docs).

`OVERALL: PASS` (armB read-trace 6/6 clean; every scenario armA_ok && armB_ok && routing_agree).

## Per-cell

| scenario | arm | rep | verdict | suggested_route | loaded_delivery_loop | loaded_role_skill | reads |
|---|---|---|---|---|---|---|---|
| fix_required | A | 1 | fix_required | deliver_fix_iteration | True | True | acceptance-agent.md, acceptance-verdict.compact.schema.json, delivery-loop.md, result.json, role-skill-model.md |
| fix_required | A | 2 | fix_required | deliver_fix_iteration | True | True | acceptance-agent.md, acceptance-verdict.compact.schema.json, delivery-loop.md, role-skill-model.md, result.json |
| fix_required | B | 1 | fix_required | deliver_fix_iteration | False | False | result.json, acceptance-verdict.compact.schema.json, acceptance-agent.md |
| fix_required | B | 2 | fix_required | deliver_fix_iteration | False | False | acceptance-agent.md, acceptance-verdict.compact.schema.json, result.json, codex-findings.md |
| no_evidence | A | 1 | needs_human | re_acceptance_after_evidence | True | True | acceptance-agent.md, acceptance-verdict.compact.schema.json, delivery-loop.md, role-skill-model.md, result.json |
| no_evidence | A | 2 | needs_human | re_acceptance_after_evidence | True | True | acceptance-agent.md, acceptance-verdict.compact.schema.json, delivery-loop.md, role-skill-model.md, result.json, codex-findings.md |
| no_evidence | B | 1 | needs_human | re_acceptance_after_evidence | False | False | acceptance-agent.md, acceptance-verdict.compact.schema.json, result.json |
| no_evidence | B | 2 | needs_human | re_acceptance_after_evidence | False | False | result.json, acceptance-verdict.compact.schema.json, acceptance-agent.md |
| pass | A | 1 | pass | n/a | True | True | acceptance-agent.md, acceptance-verdict.compact.schema.json, delivery-loop.md, role-skill-model.md, result.json, codex-findings.md, acceptance_canary.py |
| pass | A | 2 | pass | n/a | True | True | delivery-loop.md, role-skill-model.md, acceptance-agent.md, acceptance-verdict.compact.schema.json, result.json, summary.json |
| pass | B | 1 | pass | n/a | False | False | acceptance-agent.md, acceptance-verdict.compact.schema.json, result.json, codex-findings.md |
| pass | B | 2 | pass | n/a | False | False | acceptance-agent.md, acceptance-verdict.compact.schema.json, result.json, codex-findings.md |

Note: `pass/A/1` also wandered into the harness file + `summary.json` (arm A is the unconstrained
baseline) but still returned the correct verdict — it does not affect the arm-B read-trace claim.
