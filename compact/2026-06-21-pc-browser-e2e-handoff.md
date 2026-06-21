---
title: P-C (browser-E2E acceptance gate) — session handoff
doc_tier: compact
doc_category: intermediate
status: current
last_reviewed: 2026-06-21
notes: >
  Transferable context pack for continuing P-C (user-perspective browser-E2E acceptance)
  on branch v2-loop-engine. DESIGN is Codex-APPROVED (rev7). IMPLEMENTATION is complete +
  569 tests green; the Codex IMPLEMENTATION review returned REJECT (3 BLOCKING + 3 MAJOR);
  5 of 6 findings are FIXED, 1 (MAJOR-2) REMAINS. Self-contained: a new session needs only
  this file + the design spec (archive/2026-06-20-pc-browser-e2e-design.md). NOTHING is
  committed — all P-C work is uncommitted on v2-loop-engine; STOP for human closure before
  any commit/push.
---

# P-C — Browser-E2E acceptance gate — handoff (2026-06-21)

## 背景 (Background)

- Repo: **aidazi** multi-agent delivery framework, `/Users/caoruixin/projects/aidazi`,
  branch **`v2-loop-engine`** (NOT main). Runtime engine under `engine-kit/`.
- Autonomous-delivery work has three phases: **P-A = Acceptance default-on advisory**
  (DONE, commit `a0964c0`); **P-B = campaign loop + per-milestone Acceptance** (DONE,
  commits `be4f161`/`3dc495d`/`d743d78`); **P-C = user-perspective browser-E2E functional
  acceptance** (THIS work — designed + implemented, not yet committed).
- P-C goal: a formal browser-based verification stage for user-facing milestones so
  frontend/backend defects unit tests + static Code Review miss are caught BEFORE milestone
  closure. Preserve the five-role chain **Research → Deliver → Dev → Code Reviewer →
  Acceptance**; the browser executor is an **orchestrator-owned CAPABILITY, not a 6th role**.
- Workflow = **design-first + Codex-gated** (Codex gpt-5.5 xhigh). The P-C design took
  **7 Codex review rounds** (R1-R6 REJECT, each finding a real defect class; R7 APPROVE).
  Then implementation, then a Codex IMPLEMENTATION review (REJECT — fixes in progress).

## 目标 (Goals)

- Deliver a bounded **P-C v1**: a browser-E2E evidence stage that runs ONLY for milestones
  declaring it, AFTER Code Review + BEFORE milestone-close Acceptance, in BOTH single loops
  and P-B campaigns; persists/resumes safely; never duplicates execution/Acceptance on
  resume; **fail-closed everywhere** (no listed failure can silently become a milestone PASS).
- v1 is **local/demo oriented**: NO auth, remote deploy, Redis, Celery, or cloud browser.
- Every framework change is **Codex-reviewed before commit**; preserve constitution
  invariants; **do not modify P-A/P-B authority/gating semantics** beyond the minimal
  integration hook + the two explicitly-flagged determinism/recovery fixes (D6/D7).

## 已确认事实 (Established facts — code + status)

**Commits on `v2-loop-engine` (newest first):** `d743d78` (P-B per-milestone Acceptance) →
`3dc495d` → `be4f161` → `3bfb47b` → `a0964c0` (P-A) → `c6ac2c9` (design spec). **All P-C work
is UNCOMMITTED** (see file list below).

**Tests: 569 passed, 2 skipped.** Run: `cd engine-kit && python3.12 -m pytest -q` (use
**python3.12** — plain python3 lacks pytest/jsonschema). 569 = pre-P-C 535 + P-C: 11
(test_e2e_executor) + 14 (test_e2e_acceptance) + 9 (test_pc_schemas) + helpers.

**Design spec = `archive/2026-06-20-pc-browser-e2e-design.md` (revision rev7, Codex APPROVED).**
Refines §4 of the parent `archive/2026-06-20-autonomous-delivery-design.md`. The handoff for
P-A/P-B is `compact/2026-06-20-autonomous-delivery-handoff.md`. Read rev7 for full contracts;
key sections: §2 (state machine + §2a hard-fail), §3.2 (consistency gate), §3.5a (commit/
reconcile), §3.5b (evidence+authority+criteria reuse triple), §3.5c (campaign crash recovery),
§4.1 (branch-correct verdict schema), §6 (active-class calibration), §6a (Dev self-smoke).

**Architecture (what was built):**
- **New out-of-band Driver state `STATE_E2E_PENDING = "e2e_evidence_pending"`** — runs in
  `_handle_close` after the clean-pass advance + `_milestone_complete`, BEFORE Acceptance,
  ONLY when the (derived) charter has `tooling.acceptance.functional.mode == browser_e2e`.
  Resume re-enters it (idempotent), mirroring `STATE_ACCEPTANCE_PENDING`.
- **`engine-kit/orchestrator/e2e_stage.py` (NEW)** — PURE fail-closed helpers: `sha256_file`/
  `artifact_manifest_hash`; `build_manifest` + `write_checklist_results`;
  `dir_complete_and_hashes_ok` (§3.5a reconcile predicate, path/symlink-hardened);
  `evidence_event_present`/`load_manifest`; `check_acceptance_consistency` (§3.2 gate);
  `authority_fingerprint` (takes `autonomy_level_declared`)/`resolve_load_graph`
  (transitive @-include BFS)/`acceptance_input_hash` (§3.5b); `build_runtime_contract`/
  `allocate_free_port`; `validate`. Reuses `audit_log.canonical_json`.
- **`engine-kit/orchestrator/e2e_executor.py` (NEW)** — orchestrator-owned capture runner:
  `BrowserExecutor` ABC + deterministic offline **`LocalHttpExecutor`** (stdlib subprocess +
  http.client + html.parser; "screenshots" = deterministic DOM/text snapshots, NOT pixels) +
  env-gated **`PlaywrightExecutor`** (`AIDAZI_E2E_PLAYWRIGHT=1`, never in offline CI) +
  `make_executor`. Returns `ExecutorResult{exit_code, criteria:[CriterionResult], artifacts,
  app_start_log, app_stop_log}`. **Observations only — never a milestone verdict.** Runtime
  failure → `ExecutorRuntimeError`; runtime absent → `ExecutorUnavailable`; a CAPTURED
  assertion failure → `CriterionResult(executor_status="fail")` + exit_code 0 (keep going).
- **`engine-kit/orchestrator/tests/fixtures/e2e_app/` (NEW)** — stdlib http.server fixture
  with modes `normal|render_defect|state_mismatch|console_error|net_fail`; `/__health` probe.
- **Driver (`driver.py`)**: `STATE_E2E_PENDING`; RunState fields `{e2e_run_id,
  e2e_evidence_ref, e2e_manifest_hash, acceptance_evidence_hash, acceptance_snapshot}` (+
  to_dict/from_dict round-trip); `_commit_e2e` (§3.5a A/B/C ladder: reconcile / append-missing-
  event / rmtree+os.replace publish), `_run_e2e_evidence`, `_check_dev_self_smoke` (§6a);
  the §2a construction `ValueError` (browser_e2e + acceptance.mode==off); active-class API
  (`_acceptance_class`, `_calibration_status(cls)`, class-aware `_calibration_gate`/
  `_acceptance_authoritative`, `_calibration_record_id`, `_pc_schema`); `_run_acceptance`
  rewrite (evidence verify → snapshot{3 hashes + authoritative} → §3.5b reuse-or-spawn);
  `_spawn_acceptance(prompt, evidence_path, calibration_status, snapshot)` persists snapshot;
  `_handle_acceptance_verdict(..., snapshot, manifest, run_id)` runs §3.2 gate + routes from
  the FROZEN snapshot.authoritative; `_acceptance_browser_evidence`, `_acceptance_resolver_graph`,
  `_browser_evidence_prompt_section`, `_build_acceptance_prompt`, `_load_checklist_results`.
- **Campaign (`campaign.py`)**: `derive_milestone_context` projects per-milestone
  `functional_acceptance` (precedence: explicit milestone OVERRIDES / absent INHERITS charter
  functional.mode / else static; provenance records `{mode, source}`); runner threads it +
  the §3.5c `_crash_recovery` one-shot + `already` reconcile (no double-account/append; resume
  the in-flight unit). **NOTE: MAJOR-2 fix still pending here (see 下一步).**
- **Validator (`charter_validator.py`)**: `_check_functional_e2e` — browser_e2e ⇒ mode≠off +
  checklist_path + tooling.e2e; cross-validates tooling.e2e vs executor-contract.schema.json;
  base_url under allowed_origins. MANDATORY_CHECKPOINTS floor stays **9** (no new checkpoint).
- **Schemas**: NEW `executor-contract` / `functional-checklist` / `browser-evidence-manifest`
  / `acceptance-calibration-record`; `acceptance-verdict` branch-correct if/then/else
  (static→evidence_path ^eval/runs/.+; browser_e2e→criterion_id + functional_evidence_refs
  under ^\.orchestrator/audit/browser/.+ + sha256); `mission-charter` +
  `tooling.acceptance.functional` + `tooling.e2e`; `campaign-plan` milestone
  `functional_acceptance` (NO schema default); `case-spec` `tier5_e2e_browser`.
- **mock.py**: MockAdapter accepts a CALLABLE canned response (so a browser-acceptance mock
  builds a verdict citing the REAL committed manifest at spawn time).
- **Docs (subagent-written, accurate to code)**: `process/browser-e2e-acceptance.md` (NEW),
  `process/delivery-loop.md` (e2e_evidence_pending state + §4.2.8 anti-pattern #14 "Acceptance
  drives the browser itself"), `process/campaign-loop.md` (§3.7 per-milestone projection),
  role-cards `{dev (self-smoke DoD), acceptance (M3 class), deliver (schedules evidence not
  verdict), code-reviewer (E2E not its job)}`, `templates/mission-charter.yaml` (commented-out
  opt-in functional/e2e example; default static, still valid).

**Uncommitted P-C files** (git status, excluding the pre-existing
`compact/2026-06-20-autonomous-delivery-handoff.md`):
- MODIFIED: `engine-kit/adapters/mock.py`, `engine-kit/orchestrator/{campaign,driver}.py`,
  `engine-kit/orchestrator/tests/{test_campaign,test_driver}.py`,
  `engine-kit/validators/charter_validator.py`, `schemas/{acceptance-verdict,campaign-plan,
  case-spec,mission-charter}.schema.json`, `process/{campaign-loop,delivery-loop}.md`,
  `role-cards/{acceptance,code-reviewer,deliver,dev}-agent.md`, `templates/mission-charter.yaml`.
- NEW: `archive/2026-06-20-pc-browser-e2e-design.md`, `engine-kit/orchestrator/{e2e_executor,
  e2e_stage}.py`, `engine-kit/orchestrator/tests/{fixtures/e2e_app/,test_e2e_acceptance.py,
  test_e2e_executor.py}`, `engine-kit/validators/tests/test_pc_schemas.py`,
  `process/browser-e2e-acceptance.md`, `schemas/{acceptance-calibration-record,
  browser-evidence-manifest,executor-contract,functional-checklist}.schema.json`,
  + this handoff.

## 决策记录 (Decisions)

- **D1 evidence location**: `.orchestrator/audit/browser/<loop_id>/<run_id>/` (per the task
  prompt; diverges from signed §4.5 `eval/runs/<id>/e2e/` — reconciled via the additive
  `acceptance_class` + `functional_evidence_refs` verdict fields). Evidence = manifest.json +
  checklist-results.json + screenshots/ + console.json + network.json + app-start.log +
  app-stop.log + executor-config.json + backend-state-refs.json, anchored by a hash-chained
  `browser_e2e_evidence` Audit Spine event.
- **D2 executor**: interface + deterministic LocalHttpExecutor (offline CI) + env-gated
  PlaywrightExecutor (real pixels; opt-in). (human-answered)
- **D3 Dev self-smoke**: a **standalone `docs/self-smoke.json` `{command, result}`** structural
  presence gate for browser_e2e milestones (a refinement of rev7's "handoff §11 YAML block" —
  spec §6a updated to match). Absent/malformed → resumable gate_hard_fail. Necessary, not
  authoritative; distinct from the independent browser evidence gate.
- **D4 failure checkpoint**: reuse existing `gate_hard_fail` (zero campaign-classification
  churn; AST checkpoint-inventory test stays green) + crash-recovery via reconcile.
- **D5 trigger**: per-milestone `functional_acceptance` (campaign-plan, projected) + charter-
  level executor mechanics (one app/executor-contract per campaign in v1).
- **D6 (flagged)**: acceptance resume strengthened to evidence-bound, authority-frozen,
  criteria-bound REUSE (route from the frozen snapshot; reuse only when all 3 hashes match,
  else re-spawn) — touches the P-A acceptance resume + authority-read path (fresh runs
  byte-identical).
- **D7 (flagged)**: campaign STATUS_RUNNING crash recovery resumes + reconciles the in-flight
  unit (no fresh restart, no double-account) — a bounded correctness change to P-B recovery.
- **M3 functional acceptance is ADVISORY in v1** (no M3 calibration record shipped) → a
  browser-functional pass HALTs at `advisory_acceptance_pass_signoff` for human sign-off; it
  NEVER auto-ships. M1 (static) behavior byte-identical. No Acceptance authority expansion.
- The five-role chain is unchanged; the executor is orchestrator-owned (NOT mounted on
  Acceptance — Acceptance stays read-only [Read,Grep,Glob], network off, and judges the
  captured manifest). New §4.2.8 anti-pattern #14: "Acceptance drives the browser itself."
- Codex is the gate; design-first; fail-closed; never weaken a constitution invariant without
  an explicit Codex-reviewed amendment. Constitution/governance edits land at fold-back (NOT
  done here, per process/fold-back-protocol.md).

## 当前任务 (Current task)

**Addressing the Codex IMPLEMENTATION review (REJECT — 3 BLOCKING + 3 MAJOR).** Status:

| Finding | Status |
|---|---|
| BLOCKING-1 path/symlink escape in `dir_complete_and_hashes_ok` | **FIXED** (normalize backslashes first; reject abs/`..`/symlink; realpath-contain under final_dir) — `e2e_stage.py` |
| BLOCKING-2 captured `skipped`/non-critical fails could still PASS | **FIXED** (a browser PASS now requires EVERY criterion's captured executor_status == "pass"; else needs_human) — `e2e_stage.check_acceptance_consistency` |
| BLOCKING-3 acceptance_input_hash not a transitive closure | **FIXED** (`resolve_load_graph` now BFS-follows aidazi `@path` includes from roots incl. the framework `AGENTS.md` → governance chain; driver passes `repo_root`) — `e2e_stage.py` + `driver._acceptance_resolver_graph` |
| MAJOR-1 authority_fingerprint used POST-degrade autonomy | **FIXED** (`authority_fingerprint` takes `autonomy_level_declared`; driver captures the pre-degrade level BEFORE `_calibration_gate` + passes it) — `e2e_stage.py` + `driver._run_acceptance` |
| MAJOR-2 campaign `already` recovery still re-dispatches run_unit | **NOT FIXED — see 下一步** |
| MAJOR-3 Dev self-smoke surface (handoff block vs sidecar) | **RECONCILED** (spec §6a updated to the implemented `docs/self-smoke.json`; no code change) |

After the BLOCKING/MAJOR-1 fixes: **569 passed, 2 skipped** (suite green). Codex review
outputs are at `/tmp/pc_impl_review_out.md` (impl review) and `/tmp/pc_codex_review_r*.md`
(design rounds) — ephemeral; key findings captured here.

## 下一步 (Next steps — in order)

1. **Fix MAJOR-2 (campaign `already` replay) — `engine-kit/orchestrator/campaign.py`.**
   On a `STATUS_RUNNING` crash recovery where the cursor unit is already recorded (`already`
   is True), the runner currently STILL calls `run_unit(..., resume=True)` and drives from the
   new summary. rev7 §3.5c requires: **do NOT call run_unit when `already`; replay from the
   RECORDED unit's `final_state`** (advance → cursor++/continue; done → break; halted →
   re-pause). To re-pause without re-running, **store `pause_reason` + `checkpoint_path` in the
   unit record** on the pause branch (they are not stored today), then on `already` synthesize
   the branch from the recorded unit. Keep the existing no-double-account/no-double-append
   guards. Add/extend a test (a STATUS_RUNNING crash → resume replays, no re-dispatch, no
   double-account). Re-run the full suite.
2. **Re-run the Codex IMPLEMENTATION review (round 2)** to confirm REJECT → APPROVE (or
   APPROVE-WITH-CHANGES). Command in 注意事项. Address any residual blocking findings; iterate.
3. **STOP for human closure approval** before ANY commit or push. The user has NOT authorized
   a commit. When authorized: one commit on `v2-loop-engine`, message ending with the
   Co-Authored-By line (注意事项); push to GitHub `origin` ONLY when asked.
4. (Deferred, NOT P-C v1): real M3 calibration record + an M3 browser/E2E bad-case suite (would
   let browser-functional acceptance become authoritative); a real PlaywrightExecutor body;
   constitution/governance fold-back amendments.

## 注意事项 (Caveats / must-know)

- **Tests**: `cd engine-kit && python3.12 -m pytest -q` (NOT python3 — needs python3.12 +
  jsonschema). Offline, deterministic, no billed LLM / no internet. The MockAdapter is the
  only judge in CI; the PlaywrightExecutor path is env-gated and never run.
- **Codex review command**: `codex exec --sandbox read-only -c model_reasoning_effort="xhigh"
  -o <out.md> - < <prompt.md>` (run headless/background; config model=gpt-5.5). Codex IS
  available (was at limit earlier; recovered). Reuse `/tmp/pc_impl_review.md` as the prompt
  template (point it at the changed files + the rev7 design + the fail-closed properties).
- **Fail-closed mapping** (verify any change preserves it): app-start/readiness/runtime-
  unavailable/invalid-checklist/missing-incomplete-or-unanchored-evidence/hash-mismatch/
  fake-or-unbound-evidence-ref/wrong-or-absent-acceptance_class/missing-self-smoke →
  `gate_hard_fail` (resumable). A captured criterion fail/error/skipped or a pass contradicting
  the evidence or a coverage gap → coerced to **needs_human** (`acceptance_surface_approve`),
  NEVER a silent ship. The executor never emits a verdict; Acceptance is the sole pass
  producer; the driver's §3.2 gate vetoes any contradictory pass.
- **§3.5b reuse triple** (the core resume-safety invariant): a committed acceptance verdict is
  REUSED on resume ONLY when `acceptance_evidence_hash` AND `authority_fingerprint` AND
  `acceptance_input_hash` ALL match the recompute; any divergence → re-spawn. Authority uses
  the PRE-degrade (charter-declared) autonomy level. The input hash is the transitive @-include
  closure of the Acceptance load-list.
- **§3.5a commit ladder**: recovery is keyed on the PERSISTED `e2e_run_id` + the ledger
  `browser_e2e_evidence` event (+ on-disk reconcile), NOT the unsaved cache fields. `os.replace`
  is only used after `rmtree(final)` (it can't overwrite a non-empty dir).
- **Driver-level `gate_hard_fail` RAISES `GateHardFail`** (the campaign catches it → paused
  unit; a standalone `drv.run()` surfaces it — tests use `assertRaises`). The checkpoint is
  written BEFORE the raise.
- **MockAdapter callable**: a browser-acceptance mock must read the COMMITTED manifest (parse
  the `.orchestrator/audit/browser/<loop>/<run>` prefix from the prompt) and cite REAL
  artifacts (path + sha256) so the §3.2 ref-binding passes — see `_browser_judge` /
  `_campaign_judge` in `test_e2e_acceptance.py`.
- **Frozen docs**: `compact/` + `archive/` are historical (doc-lifecycle), EXCEPT the active
  spec `archive/2026-06-20-pc-browser-e2e-design.md`. Do NOT retroactively edit other archive/
  compact files.
- **Commit identity**: `Rex1028 <caoruixin@163.com>`. End commit messages with
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Branch =
  `v2-loop-engine`. **Nothing is committed; do not commit/push without explicit human approval.**
- **Scope discipline**: do NOT modify P-A/P-B authority/gating beyond the projection hook + the
  additive acceptance evidence section + the flagged D6/D7. Do NOT implement P-B parallelism /
  auto-decompose. No unrelated cleanup. Keep schemas/runtime/docs/validators synchronized +
  fail-closed.

---
End of handoff.
