# Design Spec — Native Managed E2E Execution + Framework-Generated Provenance + Autonomous Remediation

**Status:** DESIGN ONLY — not implemented. Codex gpt-5.5 xhigh gate REQUIRED before any implementation.
**Revision:** R4 (R1→R2→R3 progression; Codex R3 resolved F2-seam/F5-containment/F7-selfsmoke; R4 addresses R3's 2 residual partials [F4-budget counter, F6 run_id `r`-prefix] + 1 new finding [skipped/unmapped partition] + 3 non-blocking folds). Change-log at end.
**Date:** 2026-07-05
**Scope:** aidazi framework only. AirPlat (`airplat-upgrade-acceptance`) is READ-ONLY evidence + a scratch canary; this design does not modify AirPlat.
**Origin:** RCA of `airplat-upgrade-acceptance` Gate-2 (three confirmed framework layers — L1 capability, L2 provenance, L3 codex adapter false-kill).

---

## §0 — THE AUTONOMY INVARIANT (locked, highest priority, Codex BLOCKING review point)

> **Within signed scope and budget, native E2E execution, evidence collection, criterion evaluation, remediation, and rerun are autonomous. Human involvement is reserved for authority changes and explicitly configured final ship/reject decisions, not routine test execution.**

This invariant OVERRIDES any part of this design that would, in the routine path, make the loop depend on a human to: run a test, start/stop an environment, upload/relocate evidence, hand-author a manifest/provenance/CriterionResult, or resume the loop. **Human authority and human manual labor MUST be separated.** A reviewer must REJECT the design if any routine-path step requires human manual labor.

### The six binding requirements (each is a Codex acceptance criterion)

**R1 — A1 is native managed execution.** The loop autonomously starts/connects the test environment, runs the managed Playwright runner, captures exit code + JSON report + trace + screenshots + logs, and cleans up. It NEVER requires a human to run `npx playwright test`.

**R2 — A2 provenance is framework-generated from the real process + artifacts.** Adopters/humans MAY NOT hand-author an authoritative *or advisory* manifest, run-provenance, or CriterionResult. The framework performs criterion mapping and PASS/FAIL/SKIP normalization. Missing/inconsistent provenance ⇒ **fail closed**.

**R3 — E2E failure defaults to autonomous remediation.** On criterion failure the loop autonomously generates a failure brief, dispatches a bounded in-signed-budget Dev fix, re-runs E2E, and re-enters Acceptance. An ordinary test failure does NOT immediately demand human takeover.

**R4 — Pause is allowed ONLY when:** (a) work would exceed signed scope / remediation budget; (b) a no-progress threshold is reached; (c) an authoritative requirement, runner contract, or environment permission must change; (d) a human-only credential / external authorization is missing; (e) policy explicitly requires a final ship/reject decision.

**R5 — New-adopter onboarding emits a complete runnable proposal**, not an empty config: runner type; spec location; environment/startup contract; criterion mapping; artifact/provenance path; timeout/retry/cleanup; secret-reference contract. The agent drafts it; the human only gives whole-proposal authorization.

**R6 — Acceptance includes autonomy non-regression.** A normal user-facing milestone completes dispatch → E2E → Acceptance → remediation → rerun → completion fully autonomously, with no human command execution or evidence hauling, no new pause/re-sign on a normal run, and re-authorization triggered ONLY by a real authority mutation.

---

## §1 — Doctrinal anchoring & the collision this design resolves

The invariant generalizes aidazi's existing "human-on-the-loop, not human-in-the-loop" doctrine: §1.7-F pre-authorized bounded in-envelope autonomous remediation (`governance/constitution-core.md:153-181`); campaign "drives the whole backlog … pausing only where human authority is required" (`process/campaign-loop.md:24-30`); ship authority reserved to the human via `advisory_acceptance_pass_signoff` (`governance/constitution-core.md:189-201`).

**The collision (Codex-confirmed):**
- Acceptance quality `fix_required` HALTs for a human at EVERY autonomy level (`driver.py:4696-4725`, Constitution §3.5/§1.7-C).
- §1.7-F is **facts-only completeness** remediation and explicitly EXCLUDES quality `fix_required` (`constitution-core.md:153-181`).
- §3.6 forbids **auto-iteration on an uncalibrated Acceptance verdict** without sign-off (`process/delivery-loop.md:497-505`).
- There is no "criterion fail → fix → rerun → re-judge" primitive; E2E runs once per sub-sprint with a deterministic-for-resume run_id (`driver.py:3319-3329`).

**Resolution principle (R1 finding fix):** the new autonomous lane must be **facts-only, exactly like §1.7-F** — triggered by *deterministic, framework-observed, criterion-bound* execution failures, NOT by the interpretive LLM verdict. It iterates on **executor facts** (per-`criterion_id` `executor_status`), re-runs the managed suite, and re-enters Acceptance — but the calibration-sensitive **ship decision stays a human authority gate** (#9, unchanged). This does not violate §3.6 because §3.6 forbids auto-iterating toward *ship* on an uncalibrated verdict; §1.7-G never ships — it only drives deterministic criterion-pass and always halts at #9. Anything interpretive/unbound routes to the existing §3.5 human gate.

---

## §2 — Design overview

| Piece | What | Invariant tie |
|---|---|---|
| **A1** | Native managed `external_test_runner` executor kind | R1 |
| **A2** | Framework-generated fail-closed provenance (in-flight marker + start/end window; dry-run cannot route to acceptance) | R2 |
| **§1.7-G** | Autonomous E2E-remediation lane, facts-only, bounded, in-envelope | R3, R4 |
| **A3** | Codex adapter liveness (stop the L3 false-kill) | R6 |
| **Self-smoke autonomy** | Dev self-smoke is an autonomous Dev artifact, never human labor | R1, R6 |
| **Onboarding** | Runnable E2E-config proposal generator (concrete schema) | R5 |

Global safety frame: **autonomy lives in execute→evaluate→remediate→rerun; the final ship/reject stays a human authority gate (checkpoint #9), unchanged, and M3 stays advisory (no auto-ship).** Net autonomy gain, zero reduction of human ship authority.

**Evidence class taxonomy (new, closes finding 3):**
- **Real-execution class** = `{playwright (in-process), external_test_runner}` — produces provenance-bearing evidence; the ONLY class that may route to a browser_e2e Acceptance verdict (advisory OR authoritative).
- **Dry-run class** = `{local_http}` — deterministic-by-construction; a format/CI dry-run tool. Its manifest CANNOT route to a browser_e2e Acceptance verdict and CANNOT reach `advisory_acceptance_pass_signoff`. Enforced at the driver acceptance-routing seam (see §4).

---

## §3 — A1: Native managed `external_test_runner` executor (R1)

A third executor kind (NOT a reuse of the in-process `PlaywrightExecutor`, which drives a JSON step-DSL and cannot run a `.spec.ts`; `make_executor` today accepts only `local_http|playwright`, `e2e_executor.py:1206-1218`).

**Interface** — implement `BrowserExecutor` ABC (`e2e_executor.py:130-151`): `kind="external_test_runner"`, `run(contract, checklist, evidence_dir, env) -> ExecutorResult` (`e2e_executor.py:97-113`).

**Managed lifecycle (all framework-driven, no human step):**
1. **Environment up:** reuse the managed app lifecycle — `app_start_cmd` + readiness poll (`e2e_executor.py:372-409`) + `lifecycle_operations` setup (`:154-213`).
2. **Run the managed runner:** structured argv (`shell=False`, `start_new_session`) to the charter-configured command (default `npx playwright test <spec> --reporter=json`), from `contract.cwd`, per-run timeout.
3. **Capture real artifacts** into `evidence_dir`: Playwright JSON report, `trace.zip` per test, screenshots/video, stdout/stderr, real subprocess exit code, and `run-provenance.json` (§4). All listed in `ExecutorResult.artifacts` (only listed files are hashed).
4. **Environment down:** `lifecycle_operations` cleanup + `_stop_app` (`:154-213,477-480`), always, even on failure.

**Result normalization (framework, R2 + R3-new-finding fix):** the executor — NOT the adopter — maps each test → a signed `criterion_id` (`@crit:<id>` title tag or `contract.criterion_map`) and emits **one `CriterionResult` per signed checklist `criterion_id`** (set-equal to `checklist.criteria`, never dropped), each carrying TWO machine fields so the router (§5.1) is unambiguous:
- **`mapping_state ∈ {mapped, unmapped}`** — NEW field (added to `CriterionResult` + `browser-evidence-manifest.schema.json` `checklist_result`, whose `additionalProperties:false` must be widened, `schemas/browser-evidence-manifest.schema.json:31-40`). `unmapped` = no test bound to this signed criterion.
- **`executor_status`** — for MAPPED criteria only: `passed→pass`, `failed/unexpected→fail`, `timedOut→error`, reporter-`skipped→skipped`.

Disambiguation (closes the R3 new finding): an `unmapped` signed criterion is NOT emitted as `skipped` — it is a runner-contract completeness fault. The executor refuses to publish an acceptance-eligible manifest if any signed criterion is `unmapped` (pre-publication HALT for a runner-contract change, R4-c; see §5.1). So the router only ever sees `mapped` criteria, where `executor_status` alone is total: `pass` / `fail`+`error`→§1.7-G / reporter-`skipped`→§3.5-human. Exactly the shape `check_acceptance_consistency` consumes (`e2e_stage.py:80-98,264-308`).

**Exit-code contract:** a captured *test* failure is NOT an exception — `CriterionResult(executor_status="fail")`, `ExecutorResult.exit_code=0` (`e2e_executor.py:16-27`), real runner exit code written to `run-provenance.json`. Raise `ExecutorRuntimeError`/`ExecutorUnavailable` ONLY when the runner itself could not run (fail-closed).

**Registration & gating:** add `make_executor` branch (unknown kind stays `ValueError`); widen `schemas/executor-contract.schema.json` enum (`local_http|playwright` → +`external_test_runner`); self-gate like `AIDAZI_E2E_PLAYWRIGHT=1` (`e2e_executor.py:920-928`) → `ExecutorUnavailable` if toolchain/flag missing, never silent skip.

**Targeted rerun:** optional `--grep @crit:<id>` fast probe for diagnostics ONLY; the authoritative re-judge is ALWAYS a FULL managed run and targeted results are NEVER fed to Acceptance or cached as authoritative (per Codex non-blocking note).

---

## §4 — A2: Framework-generated provenance, fail-closed (R2) — REWRITTEN

Closes L2 and Codex findings 2 & 3. Today: `artifact_manifest_hash` is a checksum of whatever inputs are handed in; `check_acceptance_consistency`/`dir_complete_and_hashes_ok` do ZERO liveness/provenance checks (`e2e_stage.py:67-74,134-198,226-309`); and the reconcile **B-path trusts a complete/hash-valid final dir and appends a missing evidence event without rerunning** (`driver.py:3630-3635`) — so a hand-authored dir passes.

### §4.1 In-flight execution binding (closes the B-path, findings 2 + R2-NB3 stray-file)
The driver, around executor invocation (`driver.py:3648-3665`), MUST:
1. Write an **in-flight marker OUTSIDE the hashed evidence dir** — at run level `<run_dir>/.e2e-inflight/<run_id>.json` = `{loop_id, subsprint_id, remediation_round, invocation_nonce, e2e_start_ts}` — and emit an **`e2e_start`** audit event BEFORE spawning the runner. (Deliberately NOT inside the final evidence dir, so `dir_complete_and_hashes_ok`'s no-strays rule is never tripped, `e2e_stage.py:134-198`.) The `invocation_nonce` is ALSO written into `run-provenance.json` (§4.2), which IS hashed — so the nonce is bound into `artifact_manifest_hash` without adding a stray to the evidence dir.
2. Emit an **`e2e_end`** audit event AFTER the runner returns (currently only ONE post-commit `_emit_e2e_event` exists, `driver.py:3589-3601` — this design ADDS the start/end pair as the real execution window).
3. On publish, record `{invocation_nonce, e2e_start_ts, e2e_end_ts}` into the committed manifest.

**Reconcile change:** for the real-execution class, the B-path ("complete dir + append missing event", `driver.py:3630-3635`) is accepted ONLY IF the committed dir's `run-provenance.json` carries an `invocation_nonce` matching a paired `e2e_start`/`e2e_end` (same nonce) on the Audit Spine. Otherwise **rerun** (fail-closed). A hand-authored dir has no matching nonce/event pair → never trusted.

### §4.2 `run-provenance.json` (framework-emitted, finding 2)
Executor writes it from the REAL subprocess (listed in `artifacts`, so hashed): `{executor_kind, argv, cwd, pid, wall_clock_start, wall_clock_end, exit_code, tool_version, host, spec_sha256, invocation_nonce}`. Humans/adopters cannot author it.

### §4.3 Provenance validation at the PRE-SPAWN seam (corrects R2-NB1 / F2 enforcement location)
**Enforcement seam (Codex R2 blocking fix):** the current pre-spawn integrity gate is `_acceptance_browser_evidence` (`driver.py:4146-4168`) — it runs `dir_complete_and_hashes_ok` + `evidence_event_present` and raises `gate_hard_fail` (Acceptance never spawns) on failure. `check_acceptance_consistency` runs LATER, *after* `_spawn_acceptance` (`driver.py:4544-4549` spawn → `4592-4597` consistency). Therefore provenance validation MUST live in a **new pre-spawn helper `_verify_execution_provenance(run_id)` called by `_acceptance_browser_evidence` AND by the `_commit_e2e` reconcile path** — NOT in `check_acceptance_consistency` (which stays for post-verdict verdict↔evidence consistency only).
For the real-execution class, `_verify_execution_provenance` requires (any failure → `gate_hard_fail`, before any verdict spawn):
1. `run-provenance.json` present + schema-valid.
2. ≥1 NON-deterministic real artifact (`trace.zip` or real-pixel screenshot with real internal timestamps).
3. **Freshness window:** provenance `wall_clock_start/end` ⊆ `[e2e_start_ts, e2e_end_ts]` of the matching invocation nonce (§4.1).
4. Runner `exit_code` consistent with normalized results (all-`pass` ⇔ clean run).
5. `invocation_nonce` in provenance == in-flight marker == paired `e2e_start`/`e2e_end` events.
6. **Audit Spine integrity (R3 non-blocking):** before trusting the paired `e2e_start`/`e2e_end` events, `_verify_execution_provenance` VERIFIES the Audit Spine hash chain over those events (not a bare `audit.read_events` read) — so a forged/edited event pair can't satisfy the freshness window.

### §4.4 Dry-run cannot route to acceptance (closes finding 3)
At the driver acceptance-routing seam (`_handle_close`/`_run_e2e_evidence` → `_run_acceptance`, `driver.py:3136-3146,3709-3723`), a browser_e2e milestone REQUIRES real-execution-class evidence. A `local_http` (dry-run) manifest for a browser_e2e milestone is refused BEFORE any verdict spawn (advisory OR authoritative) and cannot reach `advisory_acceptance_pass_signoff` (`driver.py:4670-4694`). `local_http` remains valid only for its declared non-acceptance dry-run/format use.

**Migration (R2 non-blocking):** existing offline `local_http` browser_e2e fixtures/tests must migrate — either re-labeled as dry-run/format fixtures (that assert manifest SHAPE, not acceptance) or ported to `playwright`/`external_test_runner` for real CI. This design ships that fixture migration + a test-suite sweep so no existing offline browser_e2e acceptance path silently breaks; the sweep is a gated deliverable, not an assumption.

### §4.5 Verdict evidence kinds
Add `playwright_trace` (+`video`) to `schemas/acceptance-verdict.schema.json` `functional_evidence_refs.kind` (currently lacks them, `:131-141`).

### §4.6 Re-sign risk
Evidence/provenance/`executor_kind` are outside `acceptance_input_hash` and `signed_scope_hash`; new real artifacts only change `evidence_hash` (safe cache-invalidation → fresh spawn), never a scope re-sign. (Runner-contract changes DO force re-sign via `charter_hash` — see §10, reconciling finding 4.)

---

## §5 — §1.7-G: Autonomous E2E-remediation lane (R3, R4) — REWRITTEN (findings 1, 5, 6)

A NEW pre-authorized, bounded, in-envelope, fail-closed, **facts-only** lane, modeled precisely on §1.7-F.

**Enablement (locked):** §1.7-G is default-on for an eligible native-E2E milestone ONLY when it carries an explicit SIGNED remediation budget (`authority.e2e_remediation`, §5.3) at autonomy `human_on_the_loop`+. A milestone with no signed remediation budget is NOT auto-enabled — its deterministic criterion failures route to the existing §3.5 human gate exactly as today (legacy-safe; no silent behavior change for existing adopters).

### §5.1 Trigger basis — DETERMINISTIC, not interpretive (finding 1)
§1.7-G triggers ONLY from **framework-generated, criterion-bound failure facts**: one or more signed checklist `criterion_id`s whose `CriterionResult.executor_status ∈ {fail, error}` in a FULL managed real-execution run (§3). The failure brief is generated by the framework from these executor facts (deterministic), NOT from the LLM Acceptance verdict.
- The interpretive Acceptance `fix_required` / unbound `failure_briefs` (today only checked non-empty, `e2e_stage.py:286-288`, and NOT criterion-bound in schema) are NOT a §1.7-G trigger. Any interpretive, ambiguous, or unbound Acceptance failure routes to the EXISTING §3.5 human-confirm gate (`driver.py:4696-4725`) — unchanged.
- Schema change: bind `failure_briefs[]` to a `criterion_id` + `evidence_ref` so the deterministic subset is machine-identifiable; interpretive briefs without a bound executor-fail criterion do not qualify.
- §3.6 reconciliation: §1.7-G auto-iterates on executor FACTS, never toward ship; the ship decision remains the human #9 gate on the (still-advisory) verdict. Explicitly documented in §11.
- **TOTAL, machine-decidable partition (corrects R3 new finding):** every signed criterion routes by the pair `(mapping_state, executor_status)` (§3), with no state routed two ways:
  - `unmapped` → runner-contract completeness fault → **pre-publication HALT** for a runner-contract change (R4-c); caught earlier at proposal time (§7/R5). Never published as `skipped`, never a §1.7-G trigger.
  - `mapped, pass` → pass.
  - `mapped, fail | error` → **§1.7-G** deterministic remediation.
  - `mapped, skipped` (a bound test the reporter skipped — e.g. a conditional `test.skip`) → **§3.5-human** (interpretive: the test did not assert, so it is neither a clean pass nor a deterministic code-fault; a human/contract judgment, fail-closed — never treated as pass). 
  This is total and non-overlapping. Schema + CriterionResult carry `mapping_state`; tests cover all five outcomes (pass, fail, error, unmapped, skipped).

### §5.2 Round (all autonomous)
1. Framework emits the deterministic criterion-bound failure brief.
2. **Containment BEFORE Dev dispatch AND before rerun/Acceptance (corrects R2-NB2 / F5).** HONEST STATE: the guard at `driver.py:2420-2483` only compares the decompose plan's modules/layers (NOT req_ids, NOT the actual Dev diff), and the real diff-based `scope_envelope_check` is *admittedly NOT wired* today (`driver.py:3114-3117`; `governance/constitution-core.md:328-330,362-363`). So §1.7-G CANNOT lean on an existing containment guarantee — it must supply one. This design therefore delivers, as §1.7-G prerequisites:
   (a) failure briefs carry framework-generated `criterion_id → {req_id, module, layer}` bindings;
   (b) a **campaign-style req_id envelope check** (the mechanism that DOES exist, `campaign.py:1475-1491`) run BEFORE Dev dispatch — the fix's target req_ids must be a subset of the milestone's signed `covers_req_ids`;
   (c) **wiring the real observed-diff `scope_envelope_check`** and enforcing it AFTER the Dev fix, BEFORE rerun/Acceptance — the actual diff must touch only in-scope modules/req_ids.
   **Fail-closed dependency:** if the observed-diff scope gate is unavailable/unwired at runtime, §1.7-G does NOT dispatch an unbounded fix — it routes the failure to the §3.5 human gate. Autonomous remediation is enabled ONLY when the containment guarantee is mechanically present.
3. Dispatch a bounded in-envelope Dev fix (reuse review auto-fix body semantics `driver.py:3016-3036`), scoped to the failing criteria.
4. **Re-run E2E** with a fresh per-round run_id (§5.4). Authoritative re-judge = FULL managed run.
5. Re-enter Acceptance on fresh evidence.
6. PASS → normal #9 ship gate (unchanged). FAIL with budget remaining → loop. Else → HALT (authority gate).

### §5.3 Budget, progress & termination (findings 4, 5)
Persisted per-round remediation state (`RunState`, mirroring `fix_round` `driver.py:403`): `e2e_remediation_round`, and `failing_criteria_by_round[]` (the FULL-run failing `criterion_id` set each round).
- `authority.e2e_remediation.max_rounds` (per milestone) — bounded cycles.
- `authority.e2e_remediation.max_no_progress_rounds` — a round that does not **strictly reduce** the failing-criterion set (proper subset) is no-progress; a round that INTRODUCES a new failing criterion is a regression HALT. Mirrors `campaign.py:1493-1536`. Guarantees termination (each successful round strictly shrinks the set).
- **Honest budget bound + counter coupling (corrects R2-NB4 / F4 + R3 partial):** the review auto-fix counter `state.fix_round` (bounded by `budget.max_fix_rounds_total`, the ONLY runtime budget `_check_budget` enforces today, `driver.py:863-869,2918`) and the new `state.e2e_remediation_round` are **DISTINCT counters for distinct loops** (the review dev↔review loop vs the E2E fix→rerun loop). This design does NOT claim `max_fix_rounds_total` bounds the E2E lane. Instead, `_check_budget` is EXTENDED with a sibling check: `e2e_remediation_round > authority.e2e_remediation.max_rounds` ⇒ `BudgetExceeded` (same fail-closed shape as the existing `fix_round` check). So each loop is bounded by its own cap; the E2E lane's bounds are `e2e_remediation.max_rounds` + `max_no_progress_rounds` + strict-progress termination. (Note: a §1.7-G round MAY internally invoke the review dev→gate→review body, whose inner iterations are still bounded by `max_fix_rounds_total` on `fix_round` — the two caps compose, they don't double-count.) `max_api_usd` remains NOT enforced today (`budget_spent` never incremented, `driver.py:414-418,2841-2858`); real per-spend accounting is an OPTIONAL follow-up with its own tests, not a load-bearing bound here.
- **User-authored source + signing (corrects R2-NB4):** the knobs are authored by the adopter under charter `autonomy.e2e_remediation` (user-authored), resolved into `authority.e2e_remediation` by `_resolve_plan_authority` (`campaign.py:2741-2788`) — which today resolves only `{budget, gap_followup, trunk_branch, milestone_isolation}` and MUST be extended — then folded into `H` (`_signed_scope_H`, `campaign.py:2810-2829`). Added to `mission-charter.schema.json` (authoring) + `campaign-plan.schema.json` (resolved authority), with a validator + explicit stale-signoff tests. Raising any knob post-sign flips `H` → `stale` → re-sign (invariant-consistent: a budget increase IS an authority change).

### §5.4 run_id, cache invalidation & crash-resume (corrects R2-NB3 / F6)
- **run_id derivation:** `_e2e_run_id` (`driver.py:3319-3329`) currently returns the CACHED `state.e2e_run_id` once set, derived `"r" + sha256(loop_id + "\x00" + subsprint_id).hexdigest()[:16]`. It gains the persisted `e2e_remediation_round`, PRESERVING the `"r"` prefix convention:
  - Round 0: `"r" + sha256(loop_id + "\x00" + subsprint_id).hexdigest()[:16]` — **byte-identical to the current code** (a non-remediated milestone is unchanged; verified byte-for-byte in the canary).
  - Round N>0: `"r" + sha256(loop_id + "\x00" + subsprint_id + "\x00" + str(N)).hexdigest()[:16]` — a distinct dir + fresh provenance per round, same prefix.
- **FULL cache invalidation (Codex R2 blocking fix):** on remediation-round increment the driver MUST clear/recompute ALL persisted E2E + acceptance cache fields, not just the verdict. Specifically reset: `e2e_run_id`, `e2e_evidence_ref`, `e2e_manifest_hash`, `acceptance_evidence_hash`, `acceptance_snapshot`, `last_verdict` (`RunState`, `driver.py:466-470,498-500`). Because `_e2e_run_id` regenerates from a cleared `e2e_run_id`, the new round writes a NEW dir and cannot re-bind prior-round evidence. Prior-round dirs are retained for audit but never reused.
- **Crash-resume matrix (tests required):**
  - fail BEFORE publish → no in-flight completion → rerun this round.
  - fail AFTER publish, BEFORE `e2e_end` event → in-flight marker present, event pair incomplete → rerun (fail-closed, §4.1).
  - fail AFTER verdict, BEFORE routing → resume routing from the committed verdict (idempotent).
  - fail AFTER Dev fix, BEFORE rerun → resume at rerun of the current round.
- Each transition is journaled so resume is deterministic (reuses the existing §3.5a reconcile idempotency, extended per-round).

---

## §6 — A3: Codex adapter liveness (L3; underpins R6)

The adopter Gate-2 "codex produced no schema-conforming verdict (truncated)" is the macOS 180s watchdog false-kill: both `codex.py` and `claude_code.py` share `monitor.run_with_monitor`; the adopter pins `f887f79` (pre-PR#9 monitor); and `codex.py:236-245` passes NO `liveness_probe_factory` while `claude_code.py:239-249` passes `ToolLeaseProbe`. **A3:** wire a codex-stream liveness probe into `codex.py`'s `run_with_monitor` call so a legitimately-busy codex Acceptance/Review spawn is not false-killed. (Independent adopter unblock: bump pin `f887f79`→`f17be0a` for the shared monitor fix — adopter remediation, not this design.)

---

## §6b — Dev self-smoke autonomy (finding 7) — NEW

Today browser_e2e hard-fails (`gate_hard_fail` → HALT) before evidence capture if `docs/self-smoke.json` is missing/malformed (`driver.py:3681-3721`; `role-cards/dev-agent.md:119-126`; `process/browser-e2e-acceptance.md:206-212`). Codex R2 (F7): a Dev-contract mandate ALONE is insufficient because a non-compliant Dev spawn still hits the hard-fail → a routine human halt. The design needs an explicit autonomous path, not just a prompt instruction.

**Design (corrects R2 F7) — two mechanisms so the hard-fail is never routine:**
1. **Primary — the managed runner SUBSUMES self-smoke for the `external_test_runner` class.** The managed run already proves app-start + a happy-path journey with real provenance (§3, §4); that IS the self-smoke evidence. So for `external_test_runner` the *separate* `docs/self-smoke.json` hard-fail gate is REMOVED (its guarantee is provided by the managed run's start + first-criterion pass). No separate artifact, no separate hard-fail.
2. **Fallback — for the in-process `playwright` class, self-smoke absence is a bounded AUTONOMOUS Dev re-dispatch, not a human halt.** If `self-smoke.json` is missing/malformed after Dev, the driver treats it like a deterministic criterion-fail: it dispatches ONE bounded in-envelope Dev round (under the §5.3 budget) to produce/repair it, then retries — and only HALTs if that bounded budget is exhausted (an R4-a/b authority pause, not a routine one). The Dev role card + prompt still mandate authoring it (belt-and-suspenders).

Verified in the §9 canary (no human runs the app or authors the JSON in either path).

---

## §7 — Onboarding: runnable E2E-config proposal (R5) — with concrete schema

Extend the recommend-then-confirm doctrine (`ONBOARDING.md:460-465`) + the surface-proposal advisory pattern (`process/requirement-ledger.md:82-111`) with an **E2E-config proposal generator**. The agent inspects the adopter repo (Step-4a impl-stack snapshot, existing `frontend/e2e/*.spec.ts`, package scripts, dev-server cmd) and drafts a COMPLETE `tooling.e2e` + `tooling.acceptance.functional` block. Concrete generated fields (closing the Codex non-blocking note):
- `executor_kind: external_test_runner`; `runner_argv: ["npx","playwright","test","<spec>","--reporter=json"]`; `spec_path`.
- `app_start_cmd` (+`{port}/{store}/{mode}`), `readiness`, `base_url`, `allowed_origins`.
- `criterion_map` (`@crit:<id>` ↔ checklist `criterion_id`).
- `evidence_retention_path`; report/trace/screenshot output paths.
- `timeouts{total,step,lifecycle_seconds}`; `lifecycle_operations` cleanup; retry policy.
- `secret_refs` — NAMED references only (e.g. `env:AIJP_TEST_USER`), never literal secrets; an unresolved human-only credential is an R4-d pause.
Advisory (`proposed|confirmed` + confidence, like `surface`); binds only on whole-proposal human authorization; no new runtime gate; no re-sign until signed. A worked example ships in `examples/`.

---

## §8 — Pause taxonomy after this design (proves R4)

| Pause | Mechanism | R4 clause |
|---|---|---|
| Exceeds signed scope (out-of-envelope fix) | containment check → freshness gate → `_block_for_resign` (`campaign.py:1074-1093`) | (a),(c) |
| Exceeds remediation budget | §1.7-G budget exhaustion → `needs_human` | (a) |
| No-progress / regression | §1.7-G strict-subset progress fail | (b) |
| Runner-contract / env-permission / authority change | charter/authority edit → `H` flip → `stale` → re-sign | (c) |
| Missing human-only credential | R5 `secret_refs` unresolved → HALT | (d) |
| Final ship/reject | `advisory_acceptance_pass_signoff` #9 (unchanged) | (e) |
| Integrity/provenance breach | `gate_hard_fail` #8 (§4.3 fail-closed) | safety, not routine |

No routine happy-path or ordinary-criterion-failure pause. Ordinary criterion failure ⇒ §1.7-G autonomous remediation.

---

## §9 — Autonomy non-regression acceptance (R6) — EXPANDED to concrete canaries (finding 8)

Design accepted only if a scratch canary proves ALL of:
1. **Full autonomous chain:** dispatch → managed E2E → injected criterion `executor_status=fail` → §1.7-G fix → fresh-run rerun → re-judge → completion, ZERO human command/evidence-hauling.
2. **Hand-authored final-dir REJECTED:** a complete/hash-valid dir with no matching in-flight nonce/event pair ⇒ rerun/`gate_hard_fail`, never trusted (§4.1).
3. **Stale provenance REJECTED:** provenance wall-clock outside the `e2e_start/e2e_end` window ⇒ `gate_hard_fail` (§4.3).
4. **Dry-run cannot route:** a `local_http` manifest for a browser_e2e milestone is refused before any verdict spawn and never reaches #9 (§4.4).
5. **No self-smoke manual halt:** Dev autonomously produces `self-smoke.json`; no human runs the app (§6b).
6. **Per-round run_id crash-resume idempotency:** the four §5.4 failure points each resume deterministically.
7. **No re-sign on a normal run:** normal remediation rounds add no pause and no re-sign.
8. **Forced stale/re-sign on budget increase:** raising `authority.e2e_remediation.max_rounds` post-sign flips `H` → `stale` → re-sign (§5.3).

Canary uses AirPlat as READ-ONLY input + a deterministic scratch workspace (byte-identical base-vs-impl on the no-op path); AirPlat is never modified.

---

## §10 — Signed-scope / re-sign impact — REWRITTEN for consistency (finding 4)

Precise hash placement (resolving the prior §8/§10 contradiction):
- **`charter_hash` ⊂ H:** `charter.tooling.e2e` (executor_kind, runner contract, app_start_cmd, criterion_map, timeouts) lives in the charter, whose canonical `charter_hash` IS inside `H` (`campaign.py:2824-2825`). ⇒ **changing the runner contract / executor_kind FORCES a re-sign** (consistent with §8). This corrects R1's "outside signed hashes" error.
- **`authority.e2e_remediation` ⊂ H:** new remediation budgets are in the resolved authority block → in `H` → raise ⇒ re-sign.
- **Outside all signed hashes:** per-run evidence/provenance/CriterionResults → only `evidence_hash` (safe cache-invalidation, forces fresh spawn), never scope re-sign.
- **Outside `acceptance_input_hash`:** `executor_kind`/evidence (so a kind change doesn't perturb the acceptance-input closure), but it IS in `charter_hash`⊂H, so authority is still enforced. The two hashes serve different masters and both are honored.
- Normal autonomous rounds (fix, rerun, fresh evidence) ⇒ NEVER re-sign (preserves the standing invariant, `campaign.py:2742-2748`).

---

## §11 — Constitutional / process-doc changes (each Codex-reviewed)

1. **`governance/constitution-core.md`:** add **§1.7-G** (facts-only autonomous E2E-remediation lane: deterministic criterion-bound trigger, bounded, in-envelope containment, fail-closed, HOTL+, grants NO ship/scope/authority) + a scoped **§3.5 carve-out** (browser_e2e *deterministic* criterion-fail is dispatched under §1.7-G; interpretive `fix_required` stays §3.5 human-gated) + an explicit **§3.6 reconciliation note** (§1.7-G iterates on executor facts, never toward ship; #9 unchanged). Refresh kernel coverage/inventory + source hashes.
2. **`process/browser-e2e-acceptance.md`:** the evidence-class taxonomy (§2), provenance fail-closed rules (§4), the real-vs-dry-run routing rule, and the autonomous-execution/human-ship split. M3 stays advisory.
3. **`process/delivery-loop.md`:** new lane in the autonomy-level table.
4. **`role-cards/deliver-agent.md` / `dev-agent.md`:** §1.7-G dispatch for the carved-out deterministic case; Dev self-smoke as a mandated autonomous artifact (§6b).
5. **Schemas:** `executor-contract.schema.json` (enum + runner fields), `acceptance-verdict.schema.json` (evidence kinds + criterion-bound `failure_briefs`), `browser-evidence-manifest.schema.json` (widen `additionalProperties:false` for `checklist_result.mapping_state` + manifest `invocation_nonce`/`e2e_start_ts`/`e2e_end_ts`, `:31-40`), `mission-charter.schema.json` + `campaign-plan.schema.json` (`autonomy.e2e_remediation` + `authority.e2e_remediation`), new `run-provenance` schema, and a schema home for the criterion→`{req_id,module,layer}` binding (in the functional checklist or the deterministic failure brief, §5.2). Validators + lockstep tests + stale-signoff tests.

---

## §12 — Codex BLOCKING review points (updated)

REJECT if any hold:
1. **Autonomy regression:** any routine-path step needs human manual labor (run test, start/stop env, move evidence, hand-author manifest/provenance/CriterionResult, resume loop), INCLUDING the self-smoke gate (§6b).
2. **§1.7-G unsound:** triggers off interpretive `fix_required` rather than deterministic criterion-bound executor facts; lacks in-envelope containment; lacks strict-progress termination; or conflicts with §3.6.
3. **Provenance not fail-closed:** a hand-authored or stale dir (incl. via the reconcile B-path) can reach an advisory OR authoritative browser_e2e verdict; or dry-run (`local_http`) evidence can route to acceptance.
4. **Ship authority weakened:** auto-ships M3, bypasses #9, or requires the human for anything other than authority/final-ship/credential.
5. **Budget/authority not hash-bound:** any remediation budget or runner contract is silently mutable, or a change to it does not force re-sign per §10.
6. **run_id/resume unsafe:** per-round run_id, snapshot invalidation, or the crash-resume matrix is unspecified/incorrect.
7. **Onboarding proposal incomplete/leaky:** not runnable end-to-end (all 7 elements + concrete schema) or leaks literal secrets.
8. **Non-regression unproven:** §9's 8 canaries do not collectively prove the invariant.

---

## §13 — Boundaries & phasing (LOCKED by human 2026-07-05 after Codex R4 APPROVE)

**Design gate:** Codex gpt-5.5 xhigh APPROVE (R4, 0 blocking) — cleared.

**Phased build (locked order):**
- **Phase 1 — A3** codex adapter liveness (unblocks the loop; standalone).
- **Phase 2 — A1 + A2 as ONE ATOMIC phase.** A1 (managed `external_test_runner`) MUST NOT be independently releasable before A2 (framework-owned provenance + criterion mapping + fail-closed consistency). Keep A1+A2 on the same branch; do NOT merge or expose the executor until provenance/mapping/consistency are complete. (A managed runner without framework-owned provenance is an unsafe intermediate capability.)
- **Phase 3 — §1.7-G** autonomous remediation lane.
- **Phase 4 — autonomous self-smoke + onboarding proposal + capability contract.**
- **Phase 5 — aidazi-owned canary + full regression + final Codex CODE gate.**

**Process discipline (locked):**
- Isolated aidazi feature branch `feat/native-e2e-managed-autonomous-remediation`. NO push / PR / main modification until the complete approved scope + final canary are green.
- Codex gpt-5.5 xhigh CODE review at coherent PHASE boundaries (not every trivial commit). Do NOT proceed past a blocking verdict.
- **AirPlat untouched throughout:** no pin bump, no edits to its reports/config, NOT a writable canary. All verification uses an aidazi-owned fixture adopter or a disposable scratch workspace.

**Legacy compatibility (locked):**
- Do NOT silently enable or rewrite existing adopters. §1.7-G default-on applies only to eligible native-E2E milestones that carry an explicit SIGNED remediation budget (§5.3); absent that, behavior is unchanged.
- New-adopter onboarding proposes the COMPLETE runnable autonomous config by default (§7).
- Existing adopters receive only a migration audit/proposal AFTER they explicitly deploy the new aidazi capability — never an automatic rewrite.

## §14 — Decisions (RESOLVED by human 2026-07-05)

1. **§1.7-G default:** ON for eligible native-E2E milestones **only when an explicit signed remediation budget exists** (§5.3). Absent a signed budget ⇒ not auto-enabled (legacy-safe).
2. **Targeted `--grep` fast probe:** included as DIAGNOSTIC-ONLY; the authoritative re-judge is always a full managed run (§3).
3. **M3 calibration path:** NOT this cycle. Final M3 ship/reject stays advisory + human-authorized (#9). No autonomous shipping introduced.
4. **Self-smoke:** subsume-into-managed-runner is accepted as PRIMARY for `external_test_runner`; in-process `playwright` gets bounded autonomous Dev re-dispatch (§6b).

---

## Change-log (R1 REJECT → R2)

- **F1 (§1.7-G trigger):** reframed to deterministic, framework-generated, criterion-bound executor facts; interpretive failures stay §3.5-human; added §3.6 reconciliation. (§1, §5.1, §11)
- **F2 (provenance B-path):** added in-flight marker + `e2e_start`/`e2e_end` window; reconcile rerun unless nonce/event-paired; checks enforced before Acceptance spawn. (§4.1-4.3)
- **F3 (dry-run leakage):** evidence-class taxonomy; `local_http` cannot route to any browser_e2e verdict (advisory or authoritative). (§2, §4.4)
- **F4 (budget/authority + §8/§10 contradiction):** exact location `authority.e2e_remediation` in H; runner contract re-signs via `charter_hash`⊂H; §10 rewritten. (§5.3, §10)
- **F5 (termination/containment):** persisted per-round failing-criterion set; strict-subset progress + regression HALT; req_id/module/layer containment before dispatch. (§5.2-5.3)
- **F6 (run_id/resume):** per-round run_id derivation, snapshot invalidation, 4-point crash-resume matrix + tests. (§5.4)
- **F7 (self-smoke):** new §6b — autonomous Dev artifact, canary-verified.
- **F8 (canary):** §9 expanded to 8 concrete canaries incl. negative tests.

## Change-log (R2 REJECT → R3) — 4 residual mechanical-soundness blockers

- **R2-NB1 / F2 (provenance at wrong seam):** moved provenance validation from `check_acceptance_consistency` (post-spawn, `driver.py:4592-4597`) into a NEW pre-spawn `_verify_execution_provenance` called by `_acceptance_browser_evidence` (`driver.py:4146-4168`) + the `_commit_e2e` reconcile path; `check_acceptance_consistency` stays post-verdict only. In-flight marker moved OUTSIDE the hashed dir (nonce bound via `run-provenance.json`) so no-strays isn't tripped. (§4.1, §4.3)
- **R2-NB2 / F5 (containment not implementable):** made honest — the diff-based `scope_envelope_check` is admittedly UNWIRED (`driver.py:3114-3117`); §1.7-G now DELIVERS containment as a prerequisite (criterion→req_id/module/layer bindings + campaign req_id envelope check + wiring the observed-diff gate) and FAILS CLOSED to §3.5-human if the diff gate is unavailable. (§5.2)
- **R2-NB3 / F6 (stale evidence cache):** on round increment, clear/recompute ALL of `e2e_run_id/e2e_evidence_ref/e2e_manifest_hash/acceptance_evidence_hash/acceptance_snapshot/last_verdict`; round-0 run_id byte-identical to today, round N>0 includes N. (§5.4)
- **R2-NB4 / F4 (false budget claim):** removed the `max_api_usd` bound claim (not enforced — `budget_spent` never incremented, `driver.py:414-418`); real bounds = `max_fix_rounds_total` + `e2e_remediation` knobs + strict-progress; defined user-authored source (charter `autonomy.e2e_remediation` → `_resolve_plan_authority` → H) + stale-signoff tests. (§5.3)
- **F7 (self-smoke, upgraded from partial):** subsume-into-managed-runner is now PRIMARY (removes the separate hard-fail for `external_test_runner`); in-process class gets a bounded autonomous Dev re-dispatch instead of a human halt. (§6b)
- Non-blocking folds: `skipped`/unmapped-criterion partition (§5.1); `local_http` fixture migration sweep (§4.4).

## Change-log (R3 REJECT → R4) — 2 partials + 1 new finding + 3 non-blocking

- **R3 F4-budget (partial → resolved):** `state.fix_round` (review loop, cap `max_fix_rounds_total`) and `state.e2e_remediation_round` (E2E loop, cap `e2e_remediation.max_rounds`) are DISTINCT counters; `_check_budget` extended with a sibling check for the E2E counter; no double-count. (§5.3)
- **R3 F6-cache (partial → resolved):** run_id formula corrected to include the current `"r"` prefix — round 0 = `"r"+sha256(loop_id+NUL+subsprint_id)[:16]` (byte-identical), round N>0 appends `NUL+str(N)`. (§5.4)
- **R3 new finding (skipped/unmapped ambiguity → resolved):** added `mapping_state ∈ {mapped,unmapped}` to `CriterionResult`+manifest schema; `unmapped` ⇒ pre-publication contract HALT (never emitted as `skipped`); router keys on `(mapping_state, executor_status)` — total & non-overlapping: pass / fail·error→§1.7-G / reporter-skipped→§3.5-human / unmapped→contract-HALT. Tests for all five. (§3, §5.1)
- **Non-blocking folds:** manifest schema `additionalProperties` widened for the new fields (§11); `_verify_execution_provenance` verifies the Audit Spine hash chain, not a bare read (§4.3-6); criterion→req/module/layer binding gets a concrete schema home (§5.2, §11).
- Non-blocking notes folded: targeted-rerun diagnostic-only (§3); concrete onboarding schema (§7).
