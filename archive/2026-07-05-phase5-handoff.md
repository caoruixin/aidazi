# Phase-5 Handoff — Native-E2E: aidazi-owned canary + full regression + final Codex gate

**Purpose:** resume the approved multi-phase build in a FRESH session. Context reset only —
NOT a scope change, NOT a new branch. Read this + the design spec, verify state, then run
**Phase 5 only** (the real canary + final gate + the human decision to expose).

---

## 1. Branch & HEAD
- **Repo:** `/Users/caoruixin/projects/aidazi` (aidazi only — AirPlat is READ-ONLY evidence, never a
  writable canary, never a pin bump).
- **Branch:** `feat/native-e2e-managed-autonomous-remediation` (REUSE it; no parallel branch).
- **HEAD:** `55728e1`, working tree CLEAN (after the handoff commit). Base = `main` @ `f17be0a`.
- **Standing constraints:** NO push / PR / merge / main-modification / capability EXPOSURE until the
  FULL approved scope + the Phase-5 real canary are green and a human authorizes exposure. The whole
  branch is currently unpushed (`git ls-remote --heads origin` shows no native-e2e branch).

## 2. Completed phases (all Codex gpt-5.5 xhigh CODE-gate APPROVED)
- **Phase 1 (A3 codex liveness):** `d514920`+`b20f8f7` — APPROVE (0 blocking).
- **Phase 2 (A1 managed external_test_runner + A2 framework provenance):** `…bb17529` — R1 REJECT(5)
  → R2 REVISE(1) → **R3 APPROVE** (Codex ran the 15 provenance tests).
- **Phase 3 (§1.7-G autonomous remediation lane):** `9da7630…7a01a10` — R1(3)→R2(2)→R3(1)→**R4 APPROVE**
  (0 blocking).
- **Phase 4 (self-smoke + onboarding proposal + capability contract + migration audit):** 7 commits
  `75d5738` (C), `c14114d` (B), `c975bcc` (A), `ad0f132` (D), `46ca168` (docs), `1f24b94` (R1 fix),
  `55728e1` (R2 fix) on this branch.
  **Codex P4 CODE-gate: R1 REVISE (2 blocking) → R2 REVISE (finding 2 resolved, finding 1 partial) →
  R3 APPROVE (0 blocking, "Phase 4 is sound to proceed to Phase 5")** (evidence
  `/tmp/codex-p4-{,r2-,r3-}verdict.txt`, `/tmp/codex-p4-{,r2-,r3-}review/`).

## 3. Phase-4 change set (what Phase 5 must canary end-to-end)
- **A — autonomous Dev self-smoke (§6b):** `engine-kit/orchestrator/driver.py`
  (`_ensure_dev_self_smoke`, `_dev_self_smoke_reason`, `_e2e_selfsmoke_*`, `RunState.e2e_selfsmoke_round`).
  external_test_runner SUBSUMES the structural gate; in-process playwright + a signed
  `e2e_remediation` budget gets a bounded AUTONOMOUS Dev re-dispatch (contained + budgeted +
  fail-closed); local_http / no-budget keep the §6a gate. Recoverable path emits NO spurious
  gate_hard_fail.
- **B — runnable onboarding proposal (§7/R5):** `engine-kit/tools/e2e_config_proposal.py` +
  `schemas/e2e-config-proposal.schema.json` + worked example `examples/native-e2e-adopter/`.
  Complete (no skeleton) + no-leak (NAMED secret refs only) + advisory (no new runtime gate).
- **C — framework capability contract:** `governance/framework-capabilities.json` +
  `schemas/framework-capabilities.schema.json` + `engine-kit/framework_capabilities.py` +
  `charter.required_framework_capabilities` (mission-charter + compact) + run_loop preflight
  (real-run gate + `--sign-plan`). Deterministic, fail-closed, code-anchored, hash-bound. Capability
  ids: `native_managed_external_e2e`, `framework_owned_e2e_provenance`, `autonomous_e2e_remediation`,
  `codex_adapter_liveness` — all provided at framework_version `4.1.0`; anchors resolve (0 violations).
- **D — read-only migration audit:** `engine-kit/tools/e2e_migration_audit.py`. Detects native-E2E
  gaps for user-facing milestones; NEVER mutates authoritative state; legacy non-user-facing stays
  valid.
- **Docs / source refresh:** `process/browser-e2e-acceptance.md` (§6b/§8/§8b), `role-cards/dev-agent.md`
  §5.1 (+ `_sources.yaml` sha refresh), `ONBOARDING.md` OW-4.

## 4. Test evidence at the Phase-4 boundary
- **Full offline suite:** 1721 passed / 3 skip / **1 pre-existing red** (`test_alwaysload_doc_
  reconciliation` — README/WP-2 kernel doc drift; identical on `20523bc` and `bb17529`; OUT OF SCOPE,
  do NOT attribute it to this work).
- **Phase-4 focused (81 tests):** `test_e2e_self_smoke.py` (15), `test_framework_capabilities.py` (22),
  `test_e2e_config_proposal.py` (30), `test_e2e_migration_audit.py` (11), `test_capability_preflight.py` (6),
  incl. the R1/R2-fix regression tests (malformed/duplicate/explicit-bypass contracts; leak-guard +
  schema-guardrail).
- **Gates green:** kernel coverage **74/74** (`test_kernel_equivalence` 40 tests OK); load-closure
  `closed:true` (`test_acceptance_load_closure` 30); project-schema lockstep OK (charter compact
  regenerated).

## 5. EXACT remaining Phase-5 work (the design §13 Phase-5 boundary)
1. **aidazi-owned scratch canary (design §9, the 8 non-regression canaries):** a disposable fixture
   adopter / scratch workspace proving the REAL path end-to-end with real provenance:
   onboarding proposal → managed external_test_runner → framework provenance → criterion eval →
   deterministic failure brief → §1.7-G autonomous remediation → diagnostic `--grep` probe → FULL
   authoritative rerun → rejudge, with ZERO human command/evidence-hauling. Plus the 8 negative
   canaries (hand-authored dir rejected; stale provenance rejected; dry-run cannot route; no
   self-smoke manual halt; per-round crash-resume idempotency; no re-sign on a normal run; forced
   re-sign on a budget increase). This needs the env-gated real executor
   (`AIDAZI_E2E_EXTERNAL_RUNNER=1` + a real spec-runner toolchain) — it is the part Phase 1-4 offline
   tests DEFERRED.
2. **Full regression** at the canary pin + the final broad suite.
3. **Final Codex gpt-5.5 xhigh CODE gate** over the WHOLE scope (Phases 1-5), to APPROVE.
4. **Human decision to EXPOSE:** only after the canary + final gate are green may a human choose to
   push / open a PR / merge to main / bump an adopter pin. Until then the capability is added but NOT
   released (the same no-early-exposure discipline held since Phase 2).

## 6. Known risks / GOTCHAs carried forward
- **The pre-existing README red** is unrelated (WP-2 kernel doc drift). A separate README fix is out
  of scope; keep it clearly separated. It may need fixing before a clean main merge, but NOT here.
- **Capability contract not exposed:** `governance/framework-capabilities.json` declares the four
  capabilities as provided, but the branch is unpushed — no adopter can pin against it until Phase 5
  exposure. Do NOT bump any AirPlat pin.
- **Self-smoke subsumption invariant:** the subsumption removes ONLY the redundant `{command,result}`
  presence check; the managed run + `_verify_execution_provenance` (fail-closed) remains the real
  attestation. Do not let a future change route an unprovenanced external_test_runner run to a verdict.
- **Editing governance/role-cards** trips the `_sources.yaml` source-hash gate + `test_kernel_equivalence`
  — refresh sha256 after any such edit (dev-agent.md was refreshed this phase).
- **Editing `schemas/{mission-charter,acceptance-verdict,review-verdict}.schema.json`** requires
  regenerating the compact projection (`engine-kit/tools/project_schema.py`) — done for charter here.

## 7. Process for Phase 5
- Build the canary as an aidazi-owned fixture/scratch workspace; AirPlat stays READ-ONLY.
- Keep the branch green each commit (baseline 1707 passed / 3 skip + the ONE pre-existing README red).
- Run the FINAL Codex gpt-5.5 xhigh CODE gate (via `engine-kit/tools/review_runner.py`, bounded,
  background) over the full scope. Do NOT expose until APPROVE + a human authorizes exposure.
