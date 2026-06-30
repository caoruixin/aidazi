# OW-M3 — requirement-driven mandatory browser-E2E acceptance (design spec)

- **Date:** 2026-06-30
- **Branch:** `acceptance-efficacy-e2e-mandate` (worktree `../aidazi-acceptance`, off `main` `2f0095d`)
- **Status:** DESIGN SPEC — for Codex gpt-5.5 xhigh review/acceptance before any impl. No runtime code changed.
- **Parent:** `archive/2026-06-30-acceptance-efficacy-and-e2e-mandate.md` (research + locked plan).
- **Thesis:** A milestone whose requirements touch UI / user interaction / user-perceived experience MUST be accepted via structured browser-E2E (M3), with **no downgrade** to static (M1). The class is **derived from the requirement's nature, not chosen by a human flag.**

---

## 0. The one-sentence design

> **OW-2's requirement ledger is the INPUT CONTRACT of OW-M3.** The ledger supplies, per requirement, the machine-readable *surface classification*; OW-M3 is the enforcement that, at campaign-plan **sign-off**, derives each milestone's acceptance class from the classifications of the requirements it covers and **refuses to sign** a plan that would accept a user-facing requirement on static (M1) evidence. Neither half is a standalone document task: without OW-2's classification OW-M3 has no signal and stays dormant; without OW-M3 OW-2's classification drives nothing.

---

## 1. Why this is one mechanism, not two (the input contract)

OW-M3 must answer exactly one question per milestone: *"does this milestone deliver anything the end user sees or interacts with?"* That answer is **a property of the requirement, not of the milestone or the charter.** The only place requirements live as first-class, customer-authored records is the requirement ledger (`schemas/requirement-ledger.schema.json`). Therefore:

```
PRD ──(OW-2 onboarding)──▶ ledger REQ items, each with: surface classification
                                   │
                          milestone.covers_req_ids  (already signed, campaign.py:2194)
                                   │
                          OW-M3 sign-off derivation: milestone is "user-facing"
                          iff ANY covered REQ is classified user-facing
                                   │
                          ⇒ resolved_functional_acceptance.mode MUST be browser_e2e
                          (already frozen in signed_scope_hash, campaign.py:2197/2238)
                                   │
                          runtime _acceptance_class() reads the frozen mode (driver.py:3160)
                          ⇒ M3 evidence mandatory; static is unreachable for this milestone
```

**Interface definition (the contract OW-2 MUST produce and OW-M3 MUST consume), versioned together:**

| Field | Owner | Where it lives | Consumed by |
|---|---|---|---|
| `requirements[].surface` (new) | OW-2 | `schemas/requirement-ledger.schema.json` | OW-M3 sign-off derivation |
| `milestones[].covers_req_ids` (exists) | campaign-plan author | `schemas/campaign-plan.schema.json`, signed | OW-M3 derivation (join key) |
| `resolved_functional_acceptance.mode` (exists, derived) | engine | signed scope envelope `campaign.py:2197` | runtime `_acceptance_class()` |

OW-2 and OW-M3 ship as one reviewable unit with one schema-version bump. The ledger PR that adds `surface` is incomplete without the sign-off gate that reads it, and vice-versa.

---

## 2. OW-2 deliverable: the `surface` classification (input half of the contract)

Add to each ledger requirement (additive; absence stays byte-identical to today):

```jsonc
"surface": {
  "type": "string",
  "enum": ["user_facing", "non_user_facing"],   // v1 — see Decision D1 for a possible 3rd tier
  "description": "Does meeting this requirement produce something the end user sees or interacts with? user_facing ⇒ its covering milestone MUST be accepted via browser-E2E (M3). Agent-proposed, CUSTOMER-CONFIRMED at campaign-plan sign-off (NOT auto-set). Distinct from customer_disposition."
}
```

- **Authority:** Research/agent MAY propose `surface` (drafting is async-permitted, mirroring `intent_contract.drafted_by`); the value becomes binding **only** by being present on a REQ that the Customer signs into scope. It is NOT pure-customer-authority like `customer_disposition` — it is a signed, agent-proposable property.
- **Onboarding (OW-2 + OW-3):** the PRD→ledger wizard step assigns `surface` per REQ and, for `user_facing` REQs, requires the Gate-1 user-journey `functional-checklist` (OW-3) that M3 will judge against. This is the single authoring act referenced in the parent plan.

---

## 3. OW-M3 deliverable: the sign-off derivation + gate (enforcement half)

### 3.1 Derivation (pure function, sign-off time)

For each milestone `m` in the plan being signed:
```
covered_surfaces = { ledger[rid].surface for rid in m.covers_req_ids }
m_is_user_facing = "user_facing" ∈ covered_surfaces
required_mode    = "browser_e2e" if m_is_user_facing else (today's resolution)
```
`required_mode` is compared against `resolve_functional_acceptance(charter, m.functional_acceptance)` (`campaign.py:2169-2181`) — the mode that WILL be frozen into the signed envelope.

### 3.2 The gate (the only new enforcement)

At the F1 sign path (`stamp_signoff` / `--sign-plan`, and the validator that `run_loop` invokes on `allow_real`), **fail closed — refuse to sign — when**:

1. **Downgrade**: `m_is_user_facing` AND resolved mode ≠ `browser_e2e`. → *"milestone `<id>` covers user-facing requirement(s) `<rids>` but resolves to functional acceptance `static`; a user-facing milestone must be accepted via browser-E2E (M3). Set `functional_acceptance: browser_e2e`, or reclassify the requirement (Customer), or record an explicit waiver."*
2. **Unclassified**: any `rid ∈ m.covers_req_ids` whose ledger REQ has no `surface`. → refuse to sign (Decision D2). The classification is mandatory for any REQ bound into signed scope.

**Note what is NOT new** — these already hold and need no OW-M3 code:
- The resolved mode is already in `_envelope_milestone` → `compute_signed_scope_hash` (`campaign.py:2197,2238`), so a post-sign downgrade breaks the hash → `signoff_status` goes `stale` → runner blocks pending re-sign (`scope_report.py:342-345`). **Runtime "no downgrade" is already guaranteed by the signed hash.**
- `browser_e2e` + `acceptance.mode:off` is already an incoherence hard-fail at driver construction (`driver.py:712-716`). So forcing `browser_e2e` automatically forbids the `acceptance.enabled:false` escape (airecruiter's M3/M4 pattern) **by construction** — OW-M3 needs no separate "acceptance must be on" check.
- `_acceptance_class()` (`driver.py:3160-3168`) and the whole M3 evidence pipeline (executor, hash-anchored manifest, set-equality coverage, `needs_human` on thin evidence) already exist. OW-M3 adds **no runtime path** — it only makes the frozen mode correct at sign time.

### 3.3 Authority preserved

- M3 verdict authority is **unchanged**: v1 ships no M3 calibration ⇒ a browser-E2E `pass` is **always advisory** and HALTs at `advisory_acceptance_pass_signoff` (`driver.py:3204-3212`). **OW-M3 makes the EVIDENCE mandatory, not the SHIP.** This is why the cut OW-4 calibration work is not required.
- The waiver path (gate rule 1, third option) is **Customer-only** and recorded — it routes through re-sign / `research_contract_revision`, never an engine default. Consistent with seal ② (Customer final authority).

---

## 4. Activation, dormancy, and the single-loop path

- **Ledger-gated, additive.** OW-M3 fires only where the input contract exists: an F1-active campaign (`f1_required` is true — a `signoff` block or any `covers_req_ids`, `campaign.py:2264-2274`) whose ledger carries `surface`. **No ledger ⇒ dormant ⇒ byte-identical to today**, consistent with the existing completeness-line doctrine. This is the deliberate incentive: adopting the ledger (OW-2) is what unlocks the automatic E2E mandate.
- **This is not a weakness — it is the precondition.** "This requirement is user-facing" is only machine-enforceable if it is machine-recorded. Adopters who skip the ledger get OW-3's authoring guidance + an onboarding warning, not silent enforcement.
- **Single-loop (non-campaign) path:** no `covers_req_ids`, no ledger. **v1 non-goal** — behavior unchanged. A future extension MAY carry `surface` on `intent_contract` to drive the same derivation for single loops (Decision D3, deferred).

---

## 5. Non-goals (explicit)

- ❌ M3 calibration → authoritative / auto-ship (cut OW-4). M3 stays advisory.
- ❌ Per-REQ verdict-case wiring `covers_req_ids ↔ criterion_id ↔ case` (cut OW-5).
- ❌ Forcing browser_e2e on non-user-facing (backend/data/agent) milestones — the generality guard. `non_user_facing` resolves exactly as today.
- ❌ Changing `_acceptance_class()` runtime mechanism, the M3 evidence pipeline, or any verdict/authority semantics.

---

## 6. Decisions for the Codex gate / human

- **D1 — classification taxonomy.** v1 recommends a 2-value enum (`user_facing` / `non_user_facing`); the M3 trigger = `user_facing`. Optional 3rd tier (`user_visible_output` = user sees output but no interaction, e.g. a generated report) could map to a lighter evidence bar. **Recommend: ship 2-value; defer the 3rd tier** to avoid taxonomy churn. The user's stated bar ("UI / 用户交互 / 影响体验") collapses cleanly to the binary.
- **D2 — unclassified handling.** Recommend **refuse-to-sign** (explicit `surface` required for any signed REQ) over "conservative default = treat unclassified as user_facing," because silently forcing browser-E2E on a backend milestone reintroduces the generality problem (false-positive E2E friction → adopters bypass, the very failure OW-0 found). Refuse-to-sign forces a human call once, at sign time.
- **D3 — single-loop coverage.** Deferred (non-goal v1). Confirm deferral.
- **D4 — gate location.** The derivation/gate belongs in the **charter/plan validator on the F1 sign path** (alongside the existing F1 checks in `campaign.py` + `charter_validator.py`), NOT in the driver hot path. Confirm placement so it is enforced both at `--sign-plan` and at runner `allow_real` validation.

---

## 7. Test / canary plan

- **Unit (campaign/validator):** user_facing REQ + static milestone ⇒ sign refused; + browser_e2e milestone ⇒ signs; non_user_facing + static ⇒ signs (generality guard); unclassified covered REQ ⇒ refused; no-ledger plan ⇒ byte-identical (dormancy); waiver recorded ⇒ signs with audit.
- **Tamper:** sign a browser_e2e milestone, flip its `functional_acceptance` to static post-sign ⇒ `signoff_status: stale` ⇒ runner blocks (reuses existing hash machinery — assert, don't rebuild).
- **Incoherence:** forced browser_e2e + `acceptance.mode:off` ⇒ existing `driver.py:712-716` hard-fail (assert it fires via the new path).
- **Live canary:** re-run the OW-0 adopters against the gate — airecruiter M4 (`真 web 端到端` folded into M1) and airplat M5 (manual control-plane live step) should both be REFUSED-to-sign until their UI milestones declare `browser_e2e`, proving the gate closes the observed bypass.

---

## 8. Seals & risks

- **Seals preserved:** ① completeness⇄quality (this gate is about *evidence class*, never reads the verdict's pass/fail); ② Customer authority (waiver + reclassify are Customer-only, signed); ③ advisory-by-default (M3 stays advisory).
- **Track-2 authz gap relevance:** OW-M3 does NOT extend `§1.7-F` auto-route authority, so it does not depend on the `gap_followup.max_subsprints` fix ([[track2-gap-followup-signing-followup]]). It RELIES on the signed-scope-hash being authoritative — which is exactly the property the Track-2 gap erodes elsewhere; flag for Codex that the `surface`-derived mode must be inside the hash input `H` (`campaign.py:2218-2226`) with no parallel unsigned override.
- **Friction guard:** refuse-to-sign must emit an actionable message (the three options in §3.2 rule 1), or adopters will bypass via the ledger-absent path — re-creating OW-0's failure.

---

## 9. Citations

| Claim | Anchor |
|---|---|
| resolved acceptance mode is in the signed envelope/hash | `campaign.py:2189-2197`, `2218-2239` |
| per-milestone mode precedence (milestone > charter > static default) | `campaign.py:2169-2181` |
| covers_req_ids is a signed envelope field | `campaign.py:2194` |
| F1 is opt-in (signoff block OR covers_req_ids) | `campaign.py:2264-2274` |
| runtime class reads frozen functional.mode | `driver.py:3160-3168` |
| browser_e2e + acceptance off ⇒ construction hard-fail | `driver.py:712-716` |
| M3 always advisory in v1 (no calibration) | `driver.py:3204-3212` |
| stale signoff blocks the runner | `scope_report.py:342-345` |
| ledger surface field target | `schemas/requirement-ledger.schema.json` |
