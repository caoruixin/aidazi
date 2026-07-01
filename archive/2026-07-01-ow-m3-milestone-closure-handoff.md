# Acceptance-efficacy / E2E mandate — OW-M3 milestone closure & handoff

- **Date:** 2026-07-01
- **Status:** **CLOSED** (OW-M3 runtime landed on `main` via PR #4; OW-2/OW-3 onboarding docs
  in this branch, docs-only, unpushed pending human review).
- **Initiative:** make Acceptance validate from the end-user view / end-to-end / against the
  original PRD — specifically, make browser-E2E **requirement-driven** rather than optional
  for user-facing work.

This record closes the initiative memorialized in
`archive/2026-06-30-acceptance-efficacy-and-e2e-mandate.md` (OW-0 audit + locked plan),
`archive/2026-06-30-ow-m3-mandatory-e2e-spec.md` (spec),
`archive/2026-06-30-ow-m3-codex-review-r1.md` / `-r2.md` (design gate), and
`archive/2026-07-01-ow-m3-impl-codex-gate-log.md` (implementation gate).

---

## 1. OW-0 — adopter audit and the observed route-around

Field audit (2026-06-30) found Acceptance *energized* in the field (airplat `mode: advisory`;
both adopters run real behavioral/E2E checks) **but every UI adopter routed around the
structured browser-E2E (M3) class**:

- **airecruiter** (venture-strategy) folded "真 web 端到端" inside its M1 `eval.cmd` and set
  `acceptance.enabled: false` (uncalibrated → disabled rather than run advisory).
- **airplat** (AIJP) hand-rolled a "control-plane live step" and accepts its pure-frontend
  UI milestone (`M-UI`) via `functional_acceptance: static`.

Root cause: `_acceptance_class()` read a **charter flag** ("do I want E2E on?") instead of
asking "**is this requirement user-interactive?**". The completeness-vs-PRD line was dormant
in both adopters (no requirement ledger, though PRDs exist in-repo).

## 2. OW-M3 + OW-2 — approved design

- **OW-2** is OW-M3's **input contract** (one mechanism, one schema bump): the requirement
  ledger gains an optional `surface ∈ {user_facing, non_user_facing}`, joined to a milestone
  via `covers_req_ids`, deriving the required acceptance class.
- **OW-M3** is a **refuse-to-sign gate** (plus a real-run preflight): a milestone covering a
  `user_facing` requirement MUST resolve to `browser_e2e`; static/non-browser evidence is
  refused at plan sign-off and real-run preflight. Authority stays **advisory** — the mandate
  requires *evidence*, not auto-ship — so no calibration work was needed.
- **Design seals preserved:** ① completeness⇄quality source separation, ② Customer final
  authority, ③ advisory-by-default.
- **Decisions:** D1 two-value taxonomy; D2 unclassified ⇒ refuse-to-sign (conservative-default
  rejected); **D3 single-loop `intent_contract.surface` deferred**; D4 gate at the F1 sign
  validator.
- **Design Codex gate:** GPT-5.5 xhigh, R1 REVISE → R2 APPROVE. R1's four holes were all on the
  signed-input boundary; B2 (resume-freshness non-universal) was extracted to the Track-2
  cycle below.

## 3. Track-2 dependency — completed hardening (unblocker)

OW-M3 depended on a universal signed-input freshness gate so a post-sign surface flip is
detectable everywhere. That was landed first as the Track-2 freshness / signed-input
hardening (see `archive/2026-06-30-track2-freshness-signed-input-hardening-spec.md` and the
memory note `track2-freshness-hardening`): T2-A universal F1 freshness gate before every
dispatch/resume/gap-followup, TD6 single-hash engine re-stamp (no bypass, no divergence),
T2-B authority fields bound into `H`. Codex R1→R3 APPROVE; **merged to `main`** (`1e6946d`).
Invariant established: *normal autonomous runtime evolution never requires re-sign; only a
post-signoff authority mutation blocks execution.*

## 4. OW-M3 implementation & Codex code gate

Implemented on `feat/ow-m3-mandatory-e2e` (off `1e6946d`):

- OW-2: optional `surface` on `requirement-ledger.schema.json`.
- OW-M3: `mandatory_e2e_violations(plan, charter, ledger)` (pure sign-off gate) wired at
  `--sign-plan` (exit 2, no stamp) and real-run preflight
  (`enforce_mandatory_e2e_for_real_run`). `covered_req_surfaces` bound into
  `_envelope_milestone` → signed envelope + `H`; the live ledger threaded through every
  freshness recompute so a post-sign surface flip ⇒ `stale`.
- Dormant/additive: no ledger / no `covers_req_ids` ⇒ byte-identical; M3 stays advisory.
- **Shared strict probe** `campaign.load_and_validate_ledger()`: only `FileNotFoundError`
  ⇒ dormant; present-but-broken ⇒ refuse.

**Codex GPT-5.5 code-level gate:** R1 REVISE (3 real bypasses — duplicate-id first-vs-last
wins, out-of-enum surface trusted, wired-but-broken ledger silently dormant) → R2/R3 REVISE
(ledger-file strictness iterated `isfile`→`lexists`→explicit `os.lstat` regular-file probe)
→ **R4 APPROVE** (`b248d55`). Gate log: `archive/2026-07-01-ow-m3-impl-codex-gate-log.md`.

## 5. Post-merge main verification

- **PR #4 merged** as GitHub merge commit — `origin/main` = **`a8091019`**, parents
  `f4881285` (prior main) + `d083d9a` (OW-M3 branch tip). All OW-M3 commits
  (`57d1b58`→`88d3acc`→`1791ff4`→`b248d55`→`9807978`) confirmed **ancestors** of main.
- Full verification on `a8091019` (Python 3.12.2):
  - `pytest engine-kit maintainer -q` → **1496 passed / 3 skipped**.
  - `kernel_equivalence.py` → **OK**; `--kernel-coverage` **70/70**; `--authoring-kernel-coverage` **41/41**.
  - `acceptance_load_closure.py` → **`closed: true`**.
  - WP-9 context-budget → **31 passed**.
  - Track-2 autonomy non-regression → **5 passed**.
  - OW-M3 targeted (`engine-kit/orchestrator/tests/test_ow_m3_mandatory_e2e.py`) → **34 passed**.
- No Acceptance or Track-2 regression; working tree clean. Numbers match the pre-merge
  combined-tree verification exactly.

## 6. airplat canary results (reversible, real adopter)

Ran a fully isolated canary (`/tmp/owm3-airplat-canary/`, evidence preserved at
`archive/ow-m3-airplat-canary/canary.py` + `canary-evidence.log`) against **copies** of
airplat's real `campaign-plan.json` + `charter.yaml`, using the current-main engine. Target:
`M-UI` (airplat's pure-frontend milestone, currently accepted via `static` — the OW-0
route-around). Requirement `REQ-UI-WORKBENCH` (`surface: user_facing`) modeled the PRD
§25/§26 Demo journey.

**10/10 checks PASS:**

| Case | Result |
|---|---|
| Control (as-is: no ledger, no covers) | `--sign-plan` **exit 0** — OW-M3 dormant, pre-adoption behavior preserved |
| Control (covers declared, NO ledger) | **exit 0** — the wired ledger, not `covers_req_ids` alone, is the activation trigger |
| Negative (`user_facing` on `static`) | `--sign-plan` **exit 2**; **no signoff stamp**, plan byte-identical |
| Negative message | actionable — names `M-UI`, `REQ-UI-WORKBENCH`, `browser_e2e`, the two resolutions |
| Positive (`browser_e2e`) | **exit 0**; `signed_scope_hash` present |
| `covered_req_surfaces` bound | `scope_envelope[M-UI].covered_req_surfaces == {REQ-UI-WORKBENCH: user_facing}` |
| Fresh after sign | `signoff_status(live ledger) == 'signed'` |
| Correctly-signed → no new pause | `Campaign._authority_fresh() == True` |
| Tamper (post-sign surface flip) | `signoff_status(flipped ledger) == 'stale'` |
| Tamper → real execution blocked | `Campaign._authority_fresh() == False` → pre-dispatch gate (`campaign.py:2340`) blocks `run_unit` for re-sign |

**Real-state integrity:** airplat `campaign-plan.json` sha256 **unchanged** (`9397feea…`);
`charter.yaml` unchanged; **no requirement ledger written** to the real repo. No runtime
behavior was added to make the canary pass. Every observed behavior matches the approved
OW-M3 design — no discrepancy.

## 7. Onboarding documentation changes (OW-2 / OW-3)

Documentation-only (`ONBOARDING.md`, +102 / −2). Added **Step 4b — (Optional) Seed the
requirement ledger + `surface` classification (OW-2 / OW-3)** (the wizard previously had zero
mention of the ledger / `covers_req_ids` / `surface` / `browser_e2e`), plus the journey-table
row and step-count fix, and a concise Step 6 generation/wiring pointer. Content:

- **OW-2:** turning PRD requirements into stable ledger entries; choosing `user_facing` vs
  `non_user_facing`; how `covers_req_ids` connects milestones to requirements; that declaring
  `covers_req_ids` with a wired ledger activates strict presence / uniqueness / classification
  checks.
- **OW-3:** for `user_facing` requirements, defining the observable user journey browser-E2E
  judges; that browser-E2E is required evidence while M3 stays advisory for ship authority;
  the exactly-two valid resolutions on refusal (set `browser_e2e`, or Customer reclassifies +
  re-signs) — with **no waiver path documented** (none exists).

`process/requirement-ledger.md` already documents the mechanics faithfully (§2.1 `surface`,
§3.1 signature integrity) and was left unchanged (Step 4b points to it).

## 8. Authority statement & autonomy non-regression

- **M3 mandates evidence, not shipping.** OW-M3 forces browser-E2E to be *produced and
  judged* for user-facing milestones; it does **not** auto-authorize shipping. M3 acceptance
  authority remains **advisory** in v1 — the Customer's sign-off authority is unchanged.
- **Normal autonomous loop evolution is unaffected.** A plan with no ledger / no
  `covers_req_ids` is byte-identical to pre-OW-M3. A correctly-signed plan runs on with no new
  pause (canary item 6 `_authority_fresh() == True`; framework-level
  `test_track2_autonomy_nonregression.py` 5/5). Only a **post-signoff authority mutation**
  (a surface flip, an acceptance-mode downgrade) blocks execution — via the existing
  `campaign_plan_signoff` re-sign gate, not a new checkpoint.

---

## Deferred follow-ups (genuine residual work — NOT part of this closure)

1. **airecruiter canary.** The venture-strategy adopter (airecruiter) was not canaried here —
   only airplat. airecruiter currently has `acceptance.enabled: false`; adopting OW-2/OW-3
   there is a separate, adopter-side move.
2. **Single-loop `intent_contract.surface` (D3, deferred).** OW-M3 gates at *campaign* plan
   sign-off. Extending surface-driven mandatory-E2E to the single-loop `intent_contract` path
   was explicitly deferred under design decision D3.
3. **Broader per-requirement verdict wiring (OW-5, cut).** Per-REQ Acceptance verdict wiring
   (a verdict per covered requirement rather than per milestone) was cut from the locked plan;
   still deferred.
4. **OW-1 real checkpoint / OW-4 calibration→authoritative** — cut from the locked plan;
   advisory-by-default preserved. Making M3 authoritative would require the §3.6 calibration
   gate.

None of the above blocks this closure; OW-M3's shipped scope (requirement-driven mandatory
browser-E2E *evidence*, advisory authority) is complete and verified.
