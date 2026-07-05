# Phase-3 Handoff — Native-E2E Autonomous Remediation (§1.7-G)

**Purpose:** resume the approved multi-phase build in a FRESH session. Context reset only —
NOT a scope change, NOT a new branch. Read this + the design spec, verify state, then
implement **Phase 3 only**.

---

## 1. Branch & HEAD
- **Repo:** `/Users/caoruixin/projects/aidazi` (aidazi only — do NOT touch AirPlat).
- **Branch:** `feat/native-e2e-managed-autonomous-remediation` (REUSE it; no parallel branch).
- **HEAD:** `bb17529`, working tree CLEAN. Base = `main` @ `f17be0a`.
- **Constraints (standing):** NO push / PR / merge / main-modification / capability exposure
  until the FULL approved scope + final canary are green. AirPlat is read-only evidence +
  (later) an aidazi-owned scratch canary — never a writable canary, never a pin bump.

## 2. Completed commits (oldest→newest)
- `517f6a8` design spec (Codex R4 APPROVE).
- `d514920` + `b20f8f7` Phase 1 (A3 codex liveness probe).
- `9ee1288` Phase 2 A1 (managed `external_test_runner` executor).
- `7b36685` Phase 2 A2a (provenance schema + `e2e_stage.verify_execution_provenance`).
- `6ad8535` Phase 2 A2b (driver provenance wiring).
- `70e8021` Phase 2 fix-round 1 (5 Codex blockers: pid Popen bug / Spine-anchored window /
  concrete artifact / integer exit_code / B-path soft-verify).
- `bb17529` Phase 2 fix-round 2 (crash-resume idempotent window-anchor by
  nonce+run_id+exact-ts; runner stdout/stderr captured as hashed artifacts).

## 3. Gate verdicts (all via Codex gpt-5.5 xhigh, `engine-kit/tools/review_runner.py`)
- **Design:** APPROVE (R1 REJECT→R2→R3 REJECT→R4 APPROVE).
- **Phase 1 (A3):** code-gate APPROVE (0 blocking).
- **Phase 2 (A1+A2):** code-gate **APPROVE** — R1 REJECT(5) → R2 REVISE(1) → **R3 APPROVE**
  (Codex ran the provenance tests: 15/15). Approve statement: "sound to proceed to Phase 3".
- **Test evidence:** 868 orchestrator+adapters passed / 3 skip at HEAD. THE ONLY red is a
  PRE-EXISTING, UNRELATED failure — `test_alwaysload_doc_reconciliation.py::
  test_no_current_doc_teaches_full_canonical_as_always_load` (README.md WP-2 kernel doc
  drift; fails identically on `9ee1288` and earlier). Do NOT attribute it to this work; a
  separate README fix is out of scope here.

## 4. Relevant design sections (the authority for Phase 3)
Spec: `archive/2026-07-05-native-e2e-managed-autonomous-remediation-design.md`
- **§5 (§1.7-G lane):** Enablement (default-on ONLY when a milestone carries a SIGNED
  `authority.e2e_remediation` budget, at `human_on_the_loop`+; else deterministic failures
  route to the existing §3.5 human gate — legacy-safe).
- **§5.1 trigger:** DETERMINISTIC, framework-generated, criterion-bound executor facts
  (mapped `executor_status ∈ {fail,error}` from a FULL managed run) — NOT the interpretive
  LLM `fix_required`. Partition (total, non-overlapping): mapped/pass→pass;
  mapped/fail|error→§1.7-G; mapped/skipped→§3.5-human; unmapped→pre-publication contract HALT.
- **§5.2 round + containment:** failure brief → containment check BEFORE Dev dispatch →
  bounded in-envelope Dev fix → fresh-run rerun → re-judge. Containment = criterion→
  {req_id,module,layer} bindings + campaign req_id-envelope check + WIRE the observed-diff
  `scope_envelope_check` (currently UNWIRED, `driver.py:3114-3117`), fail-closed to §3.5 if
  unavailable.
- **§5.3 budget/progress/termination:** knobs in the SIGNED authority block →
  `campaign._resolve_plan_authority` → `H`; `_check_budget` sibling cap for
  `e2e_remediation_round`; strict-proper-subset progress + regression/no-progress HALT
  (mirror `campaign.py:1493-1536`).
- **§5.4 run_id/cache/resume:** per-round run_id `"r"+sha256(loop\x00subsprint[\x00N])[:16]`
  (round 0 byte-identical to today); FULL cache invalidation per round of
  `e2e_run_id, e2e_evidence_ref, e2e_manifest_hash, acceptance_evidence_hash,
  acceptance_snapshot, last_verdict` **AND `e2e_invocation_nonce`** (so each round gets a
  fresh provenance nonce — critical, else the A2 window-anchor mismatches); 4-point
  crash-resume matrix.
- **§11 constitutional changes:** add §1.7-G + scoped §3.5 carve-out + §3.6 reconciliation
  note to `governance/constitution-core.md`; refresh kernel coverage.
- **§9 canary is Phase 5** (do NOT start it in Phase 3).

## 5. EXACT remaining Phase-3 work
1. **Constitution:** `governance/constitution-core.md` — new **§1.7-G** (facts-only,
   bounded, in-envelope, fail-closed, HOTL+, grants NO ship/scope/authority) + scoped
   **§3.5 carve-out** (deterministic browser_e2e criterion-fail → §1.7-G; interpretive
   `fix_required` stays §3.5-human) + **§3.6 reconciliation** (auto-iterate on executor
   FACTS, never toward ship; #9 unchanged). Update `governance/constitution.md` too if the
   kernel projects from it.
2. **Deterministic trigger + failure brief:** framework generates a criterion-bound failure
   brief from the executor facts (mapped fail/error). Bind `failure_briefs[]` to
   `criterion_id` + `evidence_ref` in `schemas/acceptance-verdict.schema.json`.
3. **Signed budget authority:** charter `autonomy.e2e_remediation` (user-authored) →
   `campaign._resolve_plan_authority` (`campaign.py:2741-2788`) → `H` (`_signed_scope_H`
   `campaign.py:2810-2829`); add to `mission-charter.schema.json` + `campaign-plan.schema.json`;
   validator + stale-signoff tests. `driver._check_budget` sibling cap for the round counter.
4. **Containment gate:** criterion→{req_id,module,layer} bindings; campaign req_id-envelope
   check (`campaign.py:1475-1491`); WIRE observed-diff `scope_envelope_check` before rerun;
   fail-closed to §3.5 when unavailable.
5. **Per-round state + run_id + resume:** RunState `e2e_remediation_round` +
   `failing_criteria_by_round`; per-round run_id; FULL cache invalidation incl.
   `e2e_invocation_nonce`; crash-resume tests.
6. **Autonomous flow (driver):** failure brief → containment → bounded Dev fix (reuse the
   review auto-fix body `driver.py:3016-3036`) → fresh-round rerun → re-judge Acceptance →
   PASS→#9 human ship gate (UNCHANGED, still HALTs) / FAIL+budget→loop / exhausted or
   no-progress or out-of-envelope→HALT (authority gate).
7. **Targeted `--grep` diagnostic probe:** diagnostic-only; authoritative re-judge is ALWAYS
   a full managed run (already the executor's contract; wire the round to use it).
8. **Enablement:** §1.7-G default-on ONLY when the signed `e2e_remediation` budget exists at
   HOTL+; absent → today's §3.5 human halt (no silent behavior change for existing adopters).

## 6. Known risks / GOTCHAs
- **Kernel-coverage + source-hash gates:** editing `constitution-core.md` (and role cards)
  trips `engine-kit/tools/constraint-inventory/_sources.yaml` source-hash gate +
  `test_kernel_equivalence` (65/65 non-vacuous coverage). MUST refresh the sha256 in
  `_sources.yaml` and keep `_kernel_coverage.yaml` proving every constraint. Run
  `tools/tests/test_kernel_equivalence.py` after each governance edit.
- **acceptance-verdict compact projection lockstep:** `schemas/acceptance-verdict.schema.json`
  has a compact projection `schemas/compact/acceptance-verdict.compact.schema.json` with an
  `x-canonical-sha256`. Editing the canonical REQUIRES regenerating the compact via
  `engine-kit/tools/project_schema.py` (`ps.serialize(ps.project(canonical_bytes,
  compact_rel=...))`), else `test_project_schema.py` fails. This also perturbs
  `acceptance_input_hash` — expected; update any pinned-hash tests.
- **Observed-diff `scope_envelope_check` is UNWIRED today** — wiring it is real work; if
  scoped out, §1.7-G MUST fail-closed to the §3.5 human gate when it's unavailable (the
  design's explicit escape hatch — do not ship autonomous remediation without a working
  containment guarantee).
- **Nonce rotation per round:** the per-round FULL cache invalidation MUST clear
  `e2e_invocation_nonce` (Phase-2 A2 field) or a new round reuses the stale nonce and the
  A2 provenance window-anchor mismatches. Verified path: clearing it → `_e2e_invocation_nonce`
  regenerates from the new (round-suffixed) run_id seed.
- **Do NOT weaken the ship gate:** checkpoint #9 `advisory_acceptance_pass_signoff` and the
  M3-always-advisory guard (`driver.py:_acceptance_authoritative`) stay UNTOUCHED. §1.7-G
  automates execute→evaluate→remediate→rerun ONLY; the human ship decision is preserved.
- **Self-smoke subsumption is Phase 4**, not Phase 3 (`_run_e2e_evidence` still calls
  `_check_dev_self_smoke` — leave it; Phase 4 subsumes it for external_test_runner).

## 7. Required tests (Phase-3 gate will expect these)
- Trigger partition total: mapped/pass, mapped/fail|error→§1.7-G, mapped/skipped→§3.5,
  unmapped→HALT.
- Budget: raise `e2e_remediation.max_rounds` post-sign → `H` flips → `stale` → re-sign;
  exhaustion → HALT; NORMAL round adds NO re-sign (autonomy non-regression).
- Strict-progress: shrinking failing-set continues; regression/no-progress → HALT.
- Containment: out-of-scope diff → HALT/re-auth; fail-closed to §3.5 when diff-gate absent.
- Per-round run_id + full cache invalidation (incl. nonce) + 4-point crash-resume idempotency.
- Kernel coverage still 65/65 (or current N/N) + load-closure `closed:true` after governance
  edits; `test_project_schema` green after compact regen.
- End-to-end: dispatch → managed E2E (injected criterion fail) → §1.7-G fix → fresh-round
  rerun → re-judge → completion, fully autonomous, #9 still halts for the human ship.

## 8. Process for Phase 3
- Implement in coherent sub-steps; keep the branch green each commit.
- Run Codex gpt-5.5 xhigh CODE gate at the Phase-3 boundary (via `review_runner.py`,
  background, bounded — see the Phase-2 prompts in `/tmp/codex-p2-*` for the pattern).
- Do NOT start Phase 4 (self-smoke/onboarding) or Phase 5 (canary) until Phase 3 receives
  its own APPROVE.
- Reviewer note: Codex R1 code gates have caught REAL bugs a mock masked (the `pid` crash) —
  keep tests exercising real return shapes, and default to fail-closed.
