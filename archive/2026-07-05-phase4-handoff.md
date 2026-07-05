# Phase-4 Handoff — Native-E2E: autonomous self-smoke + onboarding proposal + capability contract

**Purpose:** resume the approved multi-phase build in a FRESH session. Context reset only —
NOT a scope change, NOT a new branch. Read this + the design spec, verify state, then
implement **Phase 4 only**.

---

## 1. Branch & HEAD
- **Repo:** `/Users/caoruixin/projects/aidazi` (aidazi only — do NOT touch AirPlat).
- **Branch:** `feat/native-e2e-managed-autonomous-remediation` (REUSE it; no parallel branch).
- **HEAD:** `7a01a10`, working tree CLEAN. Base = `main` @ `f17be0a`.
- **Constraints (standing):** NO push / PR / merge / main-modification / capability exposure
  until the FULL approved scope + Phase-5 final canary are green. AirPlat is read-only evidence
  + (later) an aidazi-owned scratch canary — never a writable canary, never a pin bump.

## 2. Completed phases (all Codex gpt-5.5 xhigh APPROVED)
- **Phase 1 (A3 codex liveness):** `d514920`+`b20f8f7`.
- **Phase 2 (A1 managed `external_test_runner` + A2 framework provenance):** `…bb17529`. APPROVE.
- **Phase 3 (§1.7-G autonomous remediation lane):** `9da7630`→`eec121a`→`c8ae496`→`00033f2`→
  `52bf9e5` (core) → `a3439e4` (R1 fix) → `69614e3` (R2 fix) → `7a01a10` (R3 fix).
  **Codex CODE gate R1(3 blockers)→R2(2)→R3(1)→R4 APPROVE (0 blocking), 2026-07-05.**
  Suite **1611 passed / 3 skip**; the ONLY red is PRE-EXISTING/unrelated
  (`test_alwaysload_doc_reconciliation` — README/WP-2 kernel doc drift, fails identically on
  `bb17529`; a separate README fix, out of scope here — do NOT attribute it to this work).
  Kernel coverage 74/74; load-closure `closed:true`; project-schema lockstep green.

## 3. Design authority for Phase 4
Spec: `archive/2026-07-05-native-e2e-managed-autonomous-remediation-design.md`
- **§6b — Dev self-smoke autonomy (the core of Phase 4):** two mechanisms so the self-smoke
  hard-fail is NEVER a routine human halt:
  1. **PRIMARY — subsume into the managed runner for `external_test_runner`.** The managed run
     already proves app-start + a happy-path journey with real provenance (§3/§4); that IS the
     self-smoke evidence. So for `external_test_runner` the SEPARATE `docs/self-smoke.json`
     hard-fail gate is REMOVED. (Today `_run_e2e_evidence` still calls `_check_dev_self_smoke`
     unconditionally — `driver.py`; Phase 3 deliberately LEFT it. Phase 4 makes it conditional:
     skip for the real-execution managed class whose first-criterion pass + app-start log already
     attest the smoke.)
  2. **FALLBACK — in-process `playwright` class: bounded AUTONOMOUS Dev re-dispatch.** If
     `docs/self-smoke.json` is missing/malformed after Dev, treat it like a deterministic
     criterion-fail: dispatch ONE bounded in-envelope Dev round (under the §5.3 e2e_remediation
     budget) to produce/repair it, then retry — HALT only if that bounded budget is exhausted
     (an R4-a/b authority pause, not a routine one). Dev role card + prompt still mandate authoring
     it (belt-and-suspenders).
- **§7 — Onboarding: runnable E2E-config proposal generator (R5), concrete schema.** Extend the
  recommend-then-confirm doctrine (`ONBOARDING.md`) + the surface-proposal advisory pattern
  (`process/requirement-ledger.md`). The agent inspects the adopter repo (Step-4a impl-stack
  snapshot, existing `frontend/e2e/*.spec.ts`, package scripts, dev-server cmd) and drafts a
  COMPLETE `tooling.e2e` + `tooling.acceptance.functional` block. Concrete generated fields:
  `executor_kind: external_test_runner`; `runner_argv`; `spec_path`; `app_start_cmd`
  (+`{port}/{store}/{mode}`), `readiness`, `base_url`, `allowed_origins`; `criterion_map`
  (`@crit:<id>` ↔ checklist `criterion_id`); `evidence_retention_path` + report/trace/screenshot
  paths; `timeouts{total,step,lifecycle_seconds}` + `lifecycle_operations` cleanup + retry;
  `secret_refs` — NAMED references only (e.g. `env:AIJP_TEST_USER`), NEVER literal secrets (an
  unresolved human-only credential is an R4-d pause). Advisory (`proposed|confirmed` + confidence,
  like `surface`); binds only on whole-proposal human authorization; NO new runtime gate; no
  re-sign until signed. A worked example ships in `examples/`.
- **§2 / §13 — capability contract:** Phase 4 may ADD the capability contract for
  `external_test_runner` but MUST NOT EXPOSE/release it until the Phase-5 canary is green
  (Phase 2 locked A1+A2 as "an unsafe intermediate capability without provenance" — the same
  no-early-exposure discipline holds through Phase 4).
- **§11.2/§11.4 process docs + role cards:** `process/browser-e2e-acceptance.md` (self-smoke
  subsumption + the autonomous re-dispatch path), `role-cards/dev-agent.md` (self-smoke as a
  mandated autonomous artifact for the playwright class), and the onboarding docs (`ONBOARDING.md`
  Step 4b / greenfield guide) for the proposal generator.

## 4. EXACT remaining Phase-4 work
1. **Self-smoke subsumption (driver):** make `_check_dev_self_smoke` conditional — SKIP for the
   real-execution managed class (`external_test_runner`) whose managed run already attests
   app-start + first-criterion pass; KEEP the structural gate for the in-process `playwright`
   class BUT convert its hard-fail into a bounded autonomous Dev re-dispatch (§6b.2), reusing the
   §1.7-G budget/round machinery where it fits (bounded, in-envelope, fail-closed).
2. **Onboarding proposal generator (§7):** the advisory `tooling.e2e` proposal (all 7 elements +
   the concrete schema), `proposed|confirmed`+confidence, secret_refs NAMED-only (leak guard),
   whole-proposal human authorization, no new runtime gate. A schema/validator for the proposal
   shape + a leak test (no literal secret can be emitted).
3. **Worked example in `examples/`** (a runnable external_test_runner adopter config).
4. **Docs:** `process/browser-e2e-acceptance.md` + `role-cards/dev-agent.md` + `ONBOARDING.md`.
   If any governance/kernel constraint changes, refresh the constraint inventory + `_kernel_coverage`
   + `_sources.yaml` sha (see Phase-3 gotchas).
5. **Capability contract** (add, do NOT expose).

## 5. Known risks / GOTCHAs (carried from Phase 3)
- **Kernel-coverage + source-hash gates:** editing `governance/constitution*.md` (or role cards in
  `_sources.yaml`) trips `engine-kit/tools/constraint-inventory/_sources.yaml` source-hash +
  `test_kernel_equivalence` (currently 74/74). Refresh the sha256 + coverage phrases; run
  `tools/tests/test_kernel_equivalence.py` after each governance edit. Coverage matcher strips
  only `` ` `` and `*` + collapses whitespace (unicode `∩ ∈ { }` preserved), plain substring match.
- **Compact projection lockstep:** editing `schemas/{acceptance-verdict,mission-charter}.schema.json`
  (or review-verdict) REQUIRES regenerating the compact via `engine-kit/tools/project_schema.py`
  (`ps.serialize(ps.project(canonical_bytes, compact_rel=...))`), else `test_project_schema` fails.
  Perturbs `acceptance_input_hash` — expected; update pinned-hash tests.
- **Self-smoke gate is a PRESENCE gate, not correctness** — subsuming it must NOT weaken the
  independent browser-evidence gate; the managed run's provenance + first-criterion pass is the
  substitute attestation, nothing less.
- **Do NOT weaken the ship gate:** #9 `advisory_acceptance_pass_signoff` + the M3-always-advisory
  guard (`_acceptance_authoritative`) stay UNTOUCHED. Phase 4 automates evidence/onboarding only.
- **Don't break §1.7-G:** the Phase-3 lane, containment (`_e2e_signed_covers` via `milestone_id`,
  observed-diff `--no-renames`), budget, and crash-resume (STATE_E2E_PENDING) are APPROVED — do
  not regress them. The Phase-4 self-smoke re-dispatch should COMPOSE with §1.7-G, not fork it.

## 6. Required tests (Phase-4 gate will expect these)
- external_test_runner milestone with NO `docs/self-smoke.json` → NO hard-fail (subsumed); the
  managed run's app-start + first-criterion pass is the attestation; a milestone still completes
  autonomously.
- playwright milestone with missing/malformed self-smoke → ONE bounded autonomous Dev re-dispatch
  (not a human halt); budget-exhausted → HALT (authority pause).
- Onboarding proposal: all 7 elements generated; `proposed` advisory; secret_refs NAMED-only;
  a literal-secret attempt is rejected/redacted (leak test); whole-proposal authorization binds;
  no new runtime gate; no re-sign until signed.
- Regression: Phase-3 §1.7-G suite + kernel 74/74 + load-closure `closed:true` still green.

## 7. Process for Phase 4
- Implement in coherent sub-steps; keep the branch green each commit (baseline = 1611 passed /
  3 skip + the ONE pre-existing README red, unchanged).
- Run Codex gpt-5.5 xhigh CODE gate at the Phase-4 boundary (via `engine-kit/tools/review_runner.py`,
  background, bounded — `codex exec --json -o <out> -m gpt-5.5 -s read-only --skip-git-repo-check
  -c model_reasoning_effort=xhigh`; see the Phase-3 prompts in `/tmp/codex-p3-*` for the pattern).
- Do NOT start Phase 5 (canary + final gate + any exposure) until Phase 4 receives its own APPROVE.
- Reviewer note: Codex code gates catch REAL fail-open / soundness bugs a mock masks — keep tests
  exercising real return shapes, and default to fail-closed.
