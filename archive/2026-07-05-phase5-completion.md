# Phase-5 COMPLETION — Native-E2E: real canary + full regression + final whole-scope Codex gate

**Status:** Phases 1-5 COMPLETE + Codex gpt-5.5 xhigh CODE-gate APPROVED at every phase, INCLUDING
the FINAL whole-scope gate. **NOT pushed / not merged / not exposed** — exposure awaits an explicit
HUMAN decision (design §13; the only remaining step).

---

## 1. Branch & HEAD
- **Repo:** `/Users/caoruixin/projects/aidazi` (aidazi only; AirPlat + all adopter repos UNTOUCHED).
- **Branch:** `feat/native-e2e-managed-autonomous-remediation`.
- **HEAD:** `03de4e5`, working tree CLEAN. Base = `main` @ `f17be0a`. NOT on origin (verified
  `git ls-remote`); NOT on origin/main.

## 2. Phase-5 work (this session)
- **Real canary fixture (aidazi-owned scratch):** `examples/native-e2e-canary/`
  (`app/server.py` — a real http.server whose `/result` flips BROKEN→OK when an in-envelope fix flag
  is written; `e2e/runner.cjs` — a REAL Node/Playwright runner driving REAL headless chromium →
  real `trace.zip` + screenshots + real exit code; `README.md`).
- **Canary harness:** `engine-kit/orchestrator/tests/test_e2e_real_canary.py` — drives the driver's
  NORMAL route (`_run_e2e_evidence` → `_commit_e2e` → `_run_e2e_remediation_lane` → `_run_acceptance`
  → #9) with `AIDAZI_E2E_EXTERNAL_RUNNER=1`. Env- + toolchain-gated → SKIPS in offline CI.
- **Commit:** `03de4e5` (on top of the Phase-4 handoff `8405e82`).

## 3. The 8 §9 non-regression canaries (7 methods) — ALL PASS on the REAL chromium path
1. **real managed happy path** → real chromium → framework provenance verified → judged pass →
   the #9 advisory_acceptance_pass_signoff HUMAN gate (never auto-ships).
2. **deterministic fail → autonomous remediation** — `result_ok` fails on the real BROKEN page →
   §1.7-G in-envelope autonomous fix → FULL managed rerun (fresh run_id + fresh provenance) →
   re-judge → #9. Fully autonomous.
3. **stale/hand-authored/dry-run rejection** — a `local_http` manifest cannot route; a tampered
   run-provenance is re-run, never trusted.
4. **unmapped criterion + runner-contract fault** — a signed criterion with no bound test ⇒
   pre-publication HALT; a runner that cannot run ⇒ fail-closed.
5. **no-progress §1.7-G HALT** — a round that makes no progress HALTs + escalates; never loops,
   never auto-ships.
6. **crash-resume idempotency** — reconcile trusts framework-owned committed evidence (same
   nonce + pid, no duplicate `browser_e2e_start`).
7. **final ship human-authorized** — a passing verdict halts at #9 (M3 advisory).

Discipline honored: NO executor internals, NO injected manifests, NO mocked authoritative
provenance, NO manual resume. The only deterministic seams are the Dev "fix" (an in-envelope file
edit standing in for a Dev agent) and the Acceptance judge (reads the REAL committed evidence,
subject to the real consistency gate).

## 4. Test + gate evidence at HEAD `03de4e5`
- **Canary:** 7/7 pass with `AIDAZI_E2E_EXTERNAL_RUNNER=1` (`/tmp/phase5-canary-evidence.log`);
  SKIPS (7 skipped) offline.
- **Full offline suite:** 1721 passed / 10 skip (3 pre-existing + 7 canary skipping offline) /
  **1 pre-existing red** (`test_alwaysload_doc_reconciliation` — README/WP-2 kernel doc drift,
  identical on base `f17be0a`; OUT OF SCOPE) (`/tmp/phase5-full-suite.log`).
- **Gates:** kernel coverage **74/74**; load-closure `closed:true` (30 tests); all 3 compact schema
  projections in lockstep; capability contract anchors resolve (0 violations).

## 5. Codex CODE-gate verdict history (all gpt-5.5 xhigh)
- **Phase 1 (A3):** APPROVE. **Phase 2 (A1+A2):** R1→R2→R3 APPROVE. **Phase 3 (§1.7-G):**
  R1→R2→R3→R4 APPROVE. **Phase 4:** R1 REVISE(2)→R2 REVISE(1)→R3 APPROVE.
- **Phase 5 (FINAL whole-scope, Phases 1-5):** **APPROVE (0 blocking)** —
  *"the whole Phases 1-5 native-E2E managed external_test_runner scope is sound and ready for the
  HUMAN exposure decision."* Evidence `/tmp/codex-p5-verdict.txt`, `/tmp/codex-p5-review/`.
  3 non-blocking notes (all expected, no action): crash-resume assertion sound; the canary proves
  managed-subprocess+provenance integrity, not cryptographic resistance to a maliciously-fabricated
  runner (outside the trust boundary); the earlier negative unit cases remain owned by the Phase 1-4
  tests (not re-owned by the canary — no silent cap).

## 6. The whole delivered capability (Phases 1-5)
- **A3** codex adapter liveness (stops the L3 watchdog false-kill).
- **A1** managed `external_test_runner` executor + **A2** framework-generated fail-closed provenance.
- **§1.7-G** facts-only, bounded, in-envelope, fail-closed autonomous browser_e2e remediation lane
  (never ships; #9 unchanged).
- **§6b** self-smoke autonomy (subsumed for external_test_runner; bounded autonomous re-dispatch for
  in-process playwright).
- **Onboarding** runnable native-E2E config proposal (complete + no-leak + advisory).
- **Capability contract** (code-anchored, deterministic, fail-closed preflight) + **migration audit**
  (read-only, legacy-safe).
- Proven end-to-end on the REAL env-gated path by the Phase-5 canary.

## 7. REMAINING (human-owned): the exposure decision
Per design §13, exposure is the human's call. Only after explicit human authorization may anyone:
push the branch / open a PR / merge to `main` / bump an adopter aidazi pin / otherwise release the
capability. Until then the capability is ADDED but NOT exposed.
- **The pre-existing README red** (`test_alwaysload_doc_reconciliation`, WP-2 kernel doc drift) is
  unrelated and out of scope; it may want a separate fix before a clean `main` merge, but NOT here.
- **Canary reproduction (for a fresh session):** `cd engine-kit && AIDAZI_E2E_EXTERNAL_RUNNER=1
  python3.12 -m pytest orchestrator/tests/test_e2e_real_canary.py -v` (needs node + a cached
  playwright whose chromium build is installed; else it skips).

## 8. Known risks / notes
- The canary is env-gated to keep browsers out of offline CI; it self-locates a cached playwright on
  this machine. On a machine without a matching cached chromium build it SKIPS (a fresh Phase-5
  re-run would need `npx playwright install chromium` or an equivalent).
- Trust boundary (Codex non-blocking): the framework guarantees managed-subprocess + provenance
  integrity; it does not defend against a deliberately malicious adopter runner fabricating artifact
  filenames — that is outside this initiative's scope.
