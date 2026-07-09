---
name: 2026-07-09-phase2-impl-codex-gate-log
doc_category: intermediate
created: 2026-07-09
description: Codex gpt-5.5 xhigh IMPLEMENTATION-gate ledger for Phase-2 (branch feat/phase2-requirement-chain) — R1/R1.2 (Commit A), R2/R2.2/R2.3/R2.4 (B+B'+C), R3/R3.2 (whole scope incl. the real-canary fixes); verbatim verdicts
---

## Round r1 verdict (verbatim)

```
Findings:

1. `run_campaign_bootstrap(resume=True)` only checks the Driver object's mode, not the persisted `state.json` mode. A bootstrap Driver can resume a `delivery_only`/`full_chain_guided` state and route it through the campaign bootstrap path. The reverse persisted guard exists in `run()`, but this direction is missing.

2. Envelope drift clears `brief_signed`, `signed_envelope`, and `campaign_backlog`, but leaves `campaign_planned=True`. If the process crashes after `_step_campaign_decompose()` saves `campaign_planned=True` and before `run_campaign_bootstrap()` marks `done`, a later drift can drop the backlog and still skip decompose, ending as `done` with no valid backlog.

3. Drift is checked after the entry envelope precondition. If a signed non-empty envelope drifts to an empty live charter, the precondition reads the old signed snapshot, passes, drift clears the signature, and the next gate can sign an empty envelope before decompose blocks. That violates the Commit A non-empty envelope gate and can leave resume stuck behind the stale empty `signed_envelope`.

The three deliberate refinements are otherwise sound in shape: dropping Deliver-output caches is the right convergence behavior, external-input refusals keeping caches is fail-closed if the caller reloads the ledger each resume, abort re-consult is explicit and does not auto-sign, and within-milestone duplicate sid as `GateHardFail` is a reasonable tightening.

I did not rerun the suite in this read-only sandbox; I reviewed the diff and accepted the supplied suite state. Test gaps: no inverse persisted-state guard test, no total `Σ <= 60` bound test, no bootstrap abort-resume test, no within-milestone duplicate sid test, and no drift-to-empty or post-`campaign_planned` crash/resume case.

VERDICT: REVISE
BLOCKING FINDINGS: 1. engine-kit/orchestrator/driver.py:3215 `run_campaign_bootstrap(resume=True)` lacks a persisted `loaded.loop_mode == campaign_bootstrap` guard, so bootstrap can resume non-bootstrap state. 2. engine-kit/orchestrator/driver.py:2845 leaves `campaign_planned` set during envelope drift while engine-kit/orchestrator/driver.py:3187 skips decompose when it is true, allowing stale/no backlog to be marked done. 3. engine-kit/orchestrator/driver.py:3170 checks envelope precondition before drift reset at engine-kit/orchestrator/driver.py:3180, so a live drift to an empty envelope can still reach and sign Gate-1.
NON-BLOCKING: 1. Add tests for inverse persisted-state guard, total Stage-2 bound `Σ > 60`, bootstrap abort-resume, within-milestone duplicate sid, drift-to-empty, and crash/resume after `campaign_planned=True` before `done`.```

## Round r1.2 verdict (verbatim)

```
I verified the R1 fixes against the design and current code. The three prior blockers are resolved.

`run_campaign_bootstrap(resume=True)` now rejects persisted non-bootstrap state at [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:3234), mirroring `run()`’s bootstrap-state refusal at [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:3306). Drift reset now clears both `campaign_backlog` and `campaign_planned` at [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:2845), so the crash-after-planned window re-enters gate-1/decompose instead of marking `done` over a dropped backlog. The drift reset is now before the envelope precondition at [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:3175), which gives the intended drift-to-empty flow: clear stale snapshot, read the live empty charter, halt `scope_envelope_unset`, and later resume cleanly after the charter is fixed.

The six new tests at [test_driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/tests/test_driver.py:4478) meaningfully pin the fixes and named gaps, including the crash-window regression and the “no second signature before empty-envelope halt” ordering. I did not rerun the suite locally because this session is read-only; this verdict is based on source inspection plus the supplied suite state.

VERDICT: APPROVE
BLOCKING FINDINGS: none
NON-BLOCKING: none```

## Round r2 verdict (verbatim)

```
I reviewed B, B′, and C against the R0.5 design. I did not find an auto-sign path in C’s inline signing: it requires explicit `sign` input plus a non-empty signer, and `--start` goes through `run_campaign_entry`. The gate should still revise: B and B′ each have authority/freshness defects, and B has an input validation trap.

VERDICT: REVISE
BLOCKING FINDINGS: 1. [run_loop.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/scheduling/run_loop.py:1483), [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:2858), [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:3244): Commit B calls `_campaign_decompose_refusal()` after bootstrap is already `STATE_DONE`; the helper does not reset state/planned flags, and resume returns early, so (e)-(h) do not re-enter `campaign_decompose_pending` and envelope drift is skipped after a refusal. 2. [campaign.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/campaign.py:1255), [campaign.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/campaign.py:1262), [campaign.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/campaign.py:1289): Commit B′ does not carry `prompt_artifacts_digest` through the live TD6 `_restamp_followup_epoch()` path; it only preserves `milestone_signals_digest`, then replaces `scope_envelope`, dropping the prompt digest snapshot copy and making a legitimate restamp stale. 3. [run_loop.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/scheduling/run_loop.py:1144), [run_loop.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/scheduling/run_loop.py:1434), [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:722): Commit B’s `_slugify_campaign_id()` and raw `--campaign-id` path can produce non-schema-safe ids; invalid ids are fed into the Driver loop id before the guarded try block, causing uncaught `ValueError` or late rc10 instead of clean rc2 input refusal.
NON-BLOCKING: 1. Test gaps: no second-resume assertion after `campaign_decompose_refusal`, no invalid slug/`--campaign-id` cases, no live `_restamp_followup_epoch()` digest test, and the run-leg test does not assert rc or absence of `dev_spec_refinement` / `acceptance_spec_refinement`. 2. Audit/provenance is weaker than the design wording: `_ingest_requirement()` has no distinct `requirement_ingested` event, and the emitted sidecar/audit path does not record a verdict digest.```

## Round r2.2 verdict (verbatim)

```
Reviewed `8a781d2` against the approved design and the B/B′/C surface. The main R2 fixes are in the right area, but I still see fail-closed gaps. I did not rerun the full suite in this read-only sandbox.

The live TD6 prompt-digest block itself is correctly ordered before `_is_authorized_followup_insertion()` and uses `Campaign.self.repo_dir`. The refusal/resume flow also now converges for the compact-collision case and forces a fresh Gate-1 on envelope drift. The remaining problems are in adjacent revalidation and freshness-consumer paths.

VERDICT: REVISE
BLOCKING FINDINGS: 1. Post-done `campaign_decompose_refusal` can reuse `campaign_planned=True` and skip the driver-side coverage authority check after ledger drift/removal: `_campaign_decompose_refusal` reopens pending without clearing `campaign_planned` (`engine-kit/orchestrator/driver.py:2877`), `_drive_bootstrap_prestates` skips `_step_campaign_decompose` when planned (`engine-kit/orchestrator/driver.py:3202`), the no-ledger-with-claims check only lives inside `_step_campaign_decompose` (`engine-kit/orchestrator/driver.py:3106`), and the run-loop revalidation path does not duplicate it while OW-M3 is dormant without a ledger (`engine-kit/scheduling/run_loop.py:1491`, `engine-kit/orchestrator/campaign.py:3059`); 2. `scope_report.compute_requirement_coverage()` accepts `repo_dir` but drops it when computing `signoff_status`, so digest-bearing signed plans are falsely reported as stale and can trigger the end-of-campaign `not_fresh_signed` path despite a valid repo dir (`engine-kit/orchestrator/scope_report.py:314`, `engine-kit/orchestrator/scope_report.py:328`, `engine-kit/orchestrator/scope_report.py:362`, `engine-kit/orchestrator/campaign.py:3242`); 3. The new campaign-id preflight still uses `re.match` with `^...$`, which accepts a trailing newline; that value then reaches `Driver(...)` before the local `try`, producing an uncaught constructor error instead of the promised clean rc-2 refusal (`engine-kit/scheduling/run_loop.py:1439`, `engine-kit/scheduling/run_loop.py:1455`, `engine-kit/orchestrator/driver.py:722`).
NON-BLOCKING: 1. `requirement_ingested` and `verdict_sha256` are emitted, but the run-loop requirement tests do not assert either audit/event field, so the R2 NB behavior is not pinned (`engine-kit/orchestrator/driver.py:3291`, `engine-kit/scheduling/run_loop.py:1512`, `engine-kit/scheduling/tests/test_run_loop_requirement.py:155`); 2. The live prompt-edit regression only asserts the campaign did not finish, not that it specifically paused for re-sign and did not record an engine restamp (`engine-kit/orchestrator/tests/test_prompt_artifacts_digest.py:271`).```

## Round r2.3 verdict (verbatim)

```
I found one remaining blocker.

The B-1 path is now fail-closed in code: `_campaign_decompose_refusal()` clears `campaign_planned`, `run_requirement_entry()` re-resolves the strict ledger on every invocation, and cached Deliver outputs are reused only for spawn avoidance while `_step_campaign_decompose()` re-runs coverage authority with the re-supplied ledger. B-3 is fixed with `re.fullmatch()`, and the NB assertions are present.

I did not rerun tests because this workspace is read-only; this is a static gate review against the requested commits.

VERDICT: REVISE
BLOCKING FINDINGS: 1. `engine-kit/orchestrator/scope_report.py:672` / `engine-kit/orchestrator/scope_report.py:771` standalone `scope_report` has no `--repo-dir` argument and calls `compute_requirement_coverage()` without `repo_dir`, so digest-bearing signed plans are falsely reported stale despite a valid repo dir.
NON-BLOCKING: 1. `engine-kit/scheduling/tests/test_run_loop_requirement.py:332` the ledger-removal regression’s fixture has no cached coverage claims, so it does not itself exercise the claimed end-to-end coverage-claim path; the implementation path is correct, so this is only a test-strength note.```

## Round r2.4 verdict (verbatim)

```
Reviewed `de1053a` and the B/B′/C + fix range. The standalone `scope_report` CLI now defines `--repo-dir` at [scope_report.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/scope_report.py:694) and threads it into `compute_requirement_coverage` at [scope_report.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/scope_report.py:776). Internally, `compute_requirement_coverage` passes it through both the restamp helper and `_signoff_status_and_hash`, so digest-bearing plans use the same basis as the runner.

The final sweep found no repo-dir-blind production consumers of `signoff_status`, `compute_requirement_coverage`, or `apply_engine_restamp_to_plan` for digest-bearing plans. I also rechecked the refusal-resume, live restamp, campaign-id, inline signing, and `--start` paths against the approved design. I did not rerun the suite in this read-only sandbox; this verdict is based on fresh code/diff inspection plus the stated suite result.

VERDICT: APPROVE
BLOCKING FINDINGS: none
NON-BLOCKING: none```

## Round r3 verdict (verbatim)

```
I cannot approve R3. The core bootstrap path is broadly implemented, and the canary evidence is mostly aligned with the test assertions, but two post-R2 authority/fail-closed issues remain.

I did not rerun the suite because this session’s filesystem is read-only; this verdict is from static review of the branch, design, evidence, and tests.

VERDICT: REVISE
BLOCKING FINDINGS: 1. engine-kit/orchestrator/driver.py:2056 tells strict projected Code Reviewers to ignore all `compact/` and `eval/`, but those are not universally engine-only surfaces: `compact/<id>-dev-prompt.md` is an adopter-authored executable prompt source at engine-kit/orchestrator/driver.py:1772 and process/prompt-artifact-rules.md:33, and `eval/bad_cases` is live governed test content with a Dev no-edit rule at examples/minimal-greenfield/eval/bad_cases/_manifest.md:28. This can hide real Dev/out-of-scope changes in existing strict single-loop runs. 2. engine-kit/scheduling/run_loop.py:875 prints a stale-signoff re-sign hint without `--repo-dir`, and engine-kit/scheduling/run_loop.py:1797 passes that missing repo dir into `stamp_signoff`; campaign.py:3028 then omits `prompt_artifacts_digest`, and campaign.py:3242 treats digest absence as dormant. A digest-bearing bootstrap plan can therefore be re-signed through the suggested command in a way that strips prompt-byte binding and lets edited compact prompts read signed.
NON-BLOCKING: 1. `git diff --check` reports whitespace-only doc issues at archive/2026-07-09-phase2-design-codex-gate-log.md:82 and archive/2026-07-09-phase2-requirement-chain-design.md:591.```

## Round r3.2 verdict (verbatim)

```
I reviewed `git show b110737` and the full `2fb39e9..HEAD` scope. The R3 prompt wording in [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:2056) now correctly separates engine state from governed `compact/` and `eval/` content, and it fits both the real canary flow and strict single-loop runs.

I traced the signoff laundering path through [run_loop.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/scheduling/run_loop.py:1799), `stamp_signoff`, `signoff_status`, engine restamp, scope report, and the direct production callers. The `--sign-plan` digest-stripping path is closed; inline signing already carries `repo_dir`, and I did not find another production path that re-signs a digest-bearing plan into a digest-less one. `git diff --check 2fb39e9..HEAD` is clean apart from the sandbox’s `/tmp/xcrun_db` warnings.

VERDICT: APPROVE
BLOCKING FINDINGS: none
NON-BLOCKING: none```

