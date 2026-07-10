# CONTEXT HANDOFF — aidazi Phase-4 (parallel campaign runner), post-Cluster-1 (2026-07-11)

A migratable context pack for a fresh session. **Phase-4 DESIGN is APPROVED (Codex R0.9, 0 blocking) and
committed; Cluster 1 (config + state model + scheduler, no execution change) is IMPLEMENTED, tests green,
and committed — but NOT yet through its Codex impl gate.** This pack = current state + the immediate next
step + the proven workflow + accumulated gotchas.

## 0. OPENING PROMPT (what to do next)
> Read `archive/2026-07-10-phase4-parallel-campaign-runner-design.md` (the approved design — §16 fold-log is
> the spec) and `archive/2026-07-11-context-pack-phase4-cluster1.md` (this pack). Cluster 1 is committed at
> `07c53fe`. **Push forward the next step: run the Codex Cluster-1 impl gate (R1)** per §3 below; fold any
> `[R1 B-#]` blocking; then proceed to Cluster 2. Work in the existing worktree `~/projects/aidazi-phase4`.

## 1. Current state (verified 2026-07-11)
- **Worktree:** `/Users/caoruixin/projects/aidazi-phase4`, branch **`feat/phase4-parallel-runner`**,
  **HEAD = `07c53fe`**. Base **`origin/main` = `b81f6d5`** (Phase-3, unchanged). Nothing pushed yet.
- **Commits on the branch (base `b81f6d5` → HEAD):**
  ```
  07c53fe feat(phase4): Cluster 1 — config + state model + scheduler (no execution change)
  c3c289d docs(phase4): design — parallel campaign runner (Codex R0.9 APPROVE, 0 blocking)
  ```
- Push to **GitHub `origin` ONLY** (gitee dropped). Commit identity **`Rex1028 <caoruixin@163.com>`** (already
  the worktree's git config). Push/PR is the FINAL step after ALL clusters + whole-scope R3 — NOT now.
- Other worktrees are historical (phase1/2/3) + `~/projects/aidazi` (main checkout) — do not disturb.
- `.gate/` is gitignored (holds gate prompts + verdicts + large codex JSON output).

## 2. What Phase-4 is + what Cluster 1 delivered
**Goal (roadmap §5, `archive/2026-07-09-autonomy-roadmap-campaign-unblock.md`):** run **N milestones
concurrently**, each in its own git worktree, folding results into a single-writer campaign state — ~N×
throughput without weakening any gate. **Design doc** `archive/2026-07-10-phase4-parallel-campaign-runner-design.md`
(base b81f6d5, every claim `file:line`-anchored; **§16 fold-log** = the authoritative spec of every decision;
**§12** = the 4-cluster phasing). Nine Codex gpt-5.5 xhigh design rounds (R0…R0.9) closed **15** blocking
findings. **Locked architecture (do NOT re-litigate — Codex-ruled):**
- Single coordinator + **isolated worker child processes**; **one sub-sprint dispatched at a time per
  milestone** — so freshness/halt/budget are enforced coordinator-side per-dispatch = serial-identical.
- **Default-OFF (`budget.max_concurrent` absent/==1) ⇒ serial dispatch `_drive_milestones` AND serial resume
  `_handle_resume` LITERALLY UNTOUCHED ⇒ byte-identical.** Parallel path is fully ADDITIVE
  (`_drive_parallel` + `_handle_resume_parallel` on new `milestone_runtime[mid]` state; reuse PURE decision
  helpers only; NEVER call singleton `_complete_milestone`/`_execute_milestone_merge`).
- Exactly-once fold via `(loop_id, attempt_nonce)`; **parent-`flock`-before-fork** launcher (child inherits
  OFD lock ⇒ no unobserved child; POSIX-only, `subprocess` needs `pass_fds`); two-part every-fold freshness
  (existing `_authority_fresh` primary + exact per-milestone `_envelope_milestone`+authority+digest slice
  discriminator, does NOT auto-clear on signed); coordinator **produces the WHOLE `requirement-context.json`
  sidecar** (worker never reads campaign-state); `max_concurrent>1` bound into signed H via
  `_resolve_plan_authority` emission + `f1_required` activator (co-dependent); `done`≠`merged` dependency
  gating, leaf `done`-unmerged terminal; ready-set over `depends_on ∩ module_locks`; **NO new checkpoint kinds**.

**Cluster 1 = DONE + committed `07c53fe` (config + state + scheduler; NO execution change):**
- **Config (§10):** `budget.max_concurrent` added to campaign-plan top-level `budget` + signed
  `authority.budget` (schemas). `_resolve_plan_authority` emits it into H **only when >1** (conditional; absent/1
  ⇒ byte-identical H). `f1_required` gains `budget.max_concurrent>1` (value-checked) ⇒ parallel plan always
  F1-active (a bare `signed_by_human:true` reads `pre_f1` ⇒ pauses for a signoff-block re-sign).
- **State model (§3.1/§3.3):** `CampaignState.milestone_runtime` map + `to_dict` (emit-when-nonempty) +
  `from_dict`; campaign-state schema (`milestone_runtime` + `units.attempt_nonce`). New method
  `_check_parallel_state_consistency` (per-milestone analogues + cross-field ties); `_check_state_consistency`
  branches on `milestone_runtime` presence (serial verbatim). **`engine_restamp`, `halt_condition_seq`,
  `halt_condition_acks`, `spent`, `units`, `gap_followup_state` stay GLOBAL** (do not per-milestone them).
- **Ingress eligibility (§7.1):** `Campaign.__init__` fail-closes a `max_concurrent>1` plan unless every
  milestone resolves to `new_worktree` AND `merge_prompt_at_close=true`.
- **Pure scheduler (§4/§7.2):** module-level `parallel_effective_phase`, `parallel_ready_set`,
  `parallel_admit`, `parallel_merge_order` (+ `MERGE_POLICY_FIFO`/`MERGE_POLICY_HUMAN_ORDER`). Defined +
  unit-tested; **consumed by the coordinator in Cluster 3** (not wired to any running code yet).
- **Tests:** `engine-kit/orchestrator/tests/test_campaign_parallel.py` (+27). Full engine-kit suite
  **2028 passed / 12 skipped / 1 failed = the pre-existing README doc-reconciliation red only** (see §4).

## 3. The proven workflow — IMMEDIATE NEXT STEP is the Cluster-1 impl gate (R1)
Each cluster: implement → **Codex impl gate** (fold each `[R1 B-#]` blocking, iterate to `VERDICT: APPROVE`) →
next cluster. After Cluster 4: whole-scope Codex R3 → push + `gh pr create` (human merge).

**Gate command (background; verdict must end `VERDICT: APPROVE|REVISE`).** Write a prompt to
`.gate/r1/prompt.md` (tell Codex: this is an IMPL gate for Cluster 1 = commit `07c53fe`; verify the code
against the design §10/§3.1/§3.3/§4/§7.1; check additivity/byte-identity for serial; hunt real bugs), then:
```
python3.12 /Users/caoruixin/projects/aidazi-phase4/engine-kit/tools/review_runner.py \
  --timeout 3600 --inactivity-warn 300 --attempts 2 --mandatory \
  --prompt-file /Users/caoruixin/projects/aidazi-phase4/.gate/r1/prompt.md \
  --capture-dir /Users/caoruixin/projects/aidazi-phase4/.gate/r1 -- \
  codex exec --json -o /Users/caoruixin/projects/aidazi-phase4/.gate/r1/verdict.txt \
  -m gpt-5.5 -c model_reasoning_effort=xhigh -s read-only --skip-git-repo-check \
  -C /Users/caoruixin/projects/aidazi-phase4
```
Run it with **`run_in_background: true` AND `dangerouslyDisableSandbox: true`** (codex needs network egress).
Verdict lands at `.gate/r1/verdict.txt`; the full JSON stream is the task-output file (can be ~1MB — read the
verdict.txt or grep the stream for `VERDICT:` and `\[R1 B-` tags).

## 4. Gotchas (blood-earned this session)
- **⚠ THE BIG ONE:** a `dangerouslyDisableSandbox` Bash command **KILLS any previously-launched sandbox-off
  background job.** So: launch the codex gate ONCE, then run **NO** sandbox-off command until it notifies
  done. Check liveness ONLY via the `Read` tool on the task-output/verdict file (never a sandbox-off `ps`).
  The gate is harness-tracked → you get a completion notification; just wait for it.
- The codex gate needs the sandbox OFF (network). `review_runner.py` (from [[bounded-review-runner]]) is present;
  it feeds the prompt on stdin and hard-timeouts + pgid-kills. `codex-cli 0.134.0`, `python3.12` at
  `/Users/caoruixin/miniconda3/bin/python3.12`.
- **Tests:** `cd engine-kit && python3.12 -m pytest`. Expect **1 pre-existing README doc-reconciliation red**
  (`test_alwaysload_doc_reconciliation.py`, README.md:122/341, byte-identical to main — DO NOT fix). Full
  suite ≈ 95s. For fast feedback use `orchestrator/tests/test_campaign.py orchestrator/tests/test_campaign_parallel.py`.
- **RTK mangles some Bash stdout** (esp. `git` output / find results) — verify git via `git rev-parse` /
  `git ls-remote`, and prefer the `Read`/`Grep` tools over `cat`/shell for files.
- **Design-vs-code frame for gates:** an impl gate DOES verify the code matches the design. But if you ever
  re-run a *design* gate, remind Codex it reviews a PLAN for unimplemented changes (R0.8 wrongly REVISE'd on
  "the code doesn't have it yet" until the frame was clarified — R0.9 then APPROVE'd).
- **New checkpoint kind** (if ever needed) must be classified into one of campaign.py's four frozensets +
  the inventory test — but Phase-4's design deliberately adds NONE.
- **Schema additivity:** `additionalProperties:false` at root of both campaign-plan/state ⇒ new keys go in
  `properties`. campaign-plan has **no** compact projection (only mission-charter does — untouched here).

## 5. Remaining clusters (design §12; each → its own Codex impl gate)
- **Cluster 2 — worker (single sub-sprint executor).** NEW `engine-kit/orchestrator/campaign_worker.py`;
  `run_unit` gains a `requirement_context` kwarg (coordinator produces the whole sidecar, self-read branch at
  campaign.py ~3819-3851 skipped in worker mode); `clock` in worker-input; parent-flock-before-fork launcher +
  attempt-scoped `result-<nonce>.json`. Prove ONE worker folds identically to serial (N=1 canary).
- **Cluster 3 — coordinator `_drive_parallel`.** Wire the pure scheduler (§4) + exactly-once fold + every-fold
  epoch stamp/`epoch_drift` (two-part freshness §5.6) + merge serialization (`merge_policy`, `done`-vs-`merged`,
  conflict→re-pause at `milestone_merge`); N=2 disjoint-lock canary; `run_loop.py` per-milestone resolver +
  `pauses[]` + phase-derived `print_campaign_result`/`CAMPAIGN_STATUS` (design §3.2.1/§6).
- **Cluster 4 — additive parallel resume.** `_handle_resume_parallel` + AST guard rooted at
  `{_drive_parallel, _handle_resume_parallel}` (serial exempt) + `epoch_drift` block + crash-resume (lease
  adopt/fence) + budget drain; docs/template; whole-scope Codex R3 → push + PR.

## 6. Key files (touched or to-touch) + memory
Touched in C1: `engine-kit/orchestrator/campaign.py` (config/state/consistency/eligibility/scheduler),
`schemas/campaign-plan.schema.json`, `schemas/campaign-state.schema.json`,
`engine-kit/orchestrator/tests/test_campaign_parallel.py`. To-touch later: `campaign_worker.py` (NEW, C2),
`engine-kit/scheduling/run_loop.py` (C3/C4), `engine-kit/orchestrator/scope_report.py` (C3, delivery-derivation),
`engine-kit/validators/charter_validator.py` (eligibility mirror). The design's §11 is the exhaustive impact
inventory.
Memory: [[phase4-parallel-runner]], [[phase3-halt-conditions]], [[real-cli-env-gate-rule]],
[[codex-verification-gate]], [[bounded-review-runner]], [[github-push-setup]].
