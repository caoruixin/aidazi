# OW-M3 — requirement-driven mandatory browser-E2E acceptance (design spec, rev2)

- **Date:** 2026-06-30
- **Branch:** `acceptance-efficacy-e2e-mandate` (worktree `../aidazi-acceptance`, off `main` `2f0095d`)
- **Status:** DESIGN SPEC rev2 — addresses Codex gpt-5.5 xhigh R1 `REVISE` (`archive/2026-06-30-ow-m3-codex-review-r1.md`). B1/B3/B4 fixed in-spec; **B2 → explicit dependency on a separate Track-2 hardening cycle.** **OW-M3 IMPLEMENTATION IS BLOCKED** until that Track-2 cycle lands and earns its own Codex APPROVE (§5). The spec itself is finalizable now; only impl is gated.
- **Parent:** `archive/2026-06-30-acceptance-efficacy-and-e2e-mandate.md` (research + locked plan).
- **Thesis:** A milestone whose requirements touch UI / user interaction / user-perceived experience MUST be accepted via structured browser-E2E (M3), no downgrade to static (M1). The class is **derived from the requirement's nature, not a human flag.**

## rev2 disposition of Codex R1 (all 7 citations were confirmed OK; anchors corrected to the worktree/main tree)
- **B1 (surface not hash-bound) — FIXED §1/§3.3:** the per-covered-REQ surface snapshot is bound INTO the signed envelope/`H`.
- **B2 (resume-freshness not universal) — DEFERRED to Track-2 §5:** OW-M3 does NOT add a local resume patch and does NOT absorb the campaign state-machine hardening; impl is blocked on the Track-2 cycle.
- **B3 (canary vs dormancy contradiction) — FIXED §4/§7:** canary is post-OW-2-adoption; a milestone declaring `covers_req_ids` must have every referenced REQ present + classified or it is refused-to-sign.
- **B4 (waiver = bypass) — FIXED §3.2:** waiver removed from v1; resolutions are set-`browser_e2e` or reclassify-and-re-sign only.
- Nits N1–N5 folded (§6).

---

## 0. The one-sentence design

> **OW-2's requirement ledger is the INPUT CONTRACT of OW-M3.** The ledger supplies, per requirement, a machine-readable *surface classification*; OW-M3 is the **sign-off gate** that derives each milestone's required acceptance class from the classifications of the requirements it covers, **binds those classifications into the signed scope hash**, and **refuses to sign** a plan that would accept a user-facing requirement on static (M1) evidence. Neither half stands alone: without OW-2's classification OW-M3 has no signal; without OW-M3 the classification drives nothing.

---

## 1. Why this is one mechanism, not two (the input contract)

OW-M3 answers one question per milestone: *"does this milestone deliver anything the end user sees or interacts with?"* That is a property of the **requirement**, recorded only in the requirement ledger. Therefore OW-2 and OW-M3 ship as **one reviewable unit, one schema-version bump.**

```
PRD ─(OW-2)→ ledger REQ items, each with: surface  ┐
                                                    │  joined at sign-off by
milestones[].covers_req_ids (already signed)  ──────┤  covers_req_ids
                                                    │
   OW-M3 sign-off gate:                             ▼
     • require every covered REQ ∈ ledger AND classified         (B3/N2)
     • milestone is user-facing  ⇔  ANY covered REQ.surface == user_facing
     • user-facing ⇒ resolved functional acceptance MUST be browser_e2e   (refuse else)
     • SNAPSHOT covered-REQ surfaces INTO the signed envelope/H            (B1)
                                                    │
runtime _acceptance_class() reads the frozen mode (driver.py:3029-3037)
   ⇒ M3 evidence mandatory; static unreachable for this milestone
   (NB: tamper-DETECTION is in the hash; tamper-BLOCKING on resume = Track-2, §5)
```

**Interface (OW-2 produces / OW-M3 consumes), versioned together:**

| Field | Owner | Where | Consumed by |
|---|---|---|---|
| `requirements[].surface` (new) | OW-2 | `schemas/requirement-ledger.schema.json` | OW-M3 sign-off derivation |
| `milestones[].covers_req_ids` (exists, signed) | plan author | `schemas/campaign-plan.schema.json` | OW-M3 join key |
| `_envelope_milestone.covered_req_surfaces` (**new, B1**) | engine @ sign-off | signed envelope + `H` (campaign.py:2189-2197 / 2218-2225) | tamper-detection of the surface→mode basis |
| `resolved_functional_acceptance.mode` (exists, derived, signed) | engine | signed envelope (campaign.py:2197) | runtime `_acceptance_class()` |

---

## 2. OW-2 deliverable: the `surface` classification (input half)

Add to each ledger requirement (additive; absence stays byte-identical to today):

```jsonc
"surface": {
  "type": "string",
  "enum": ["user_facing", "non_user_facing"],   // v1 binary — Decision D1
  "description": "Does meeting this requirement produce something the end user OPERATES (UI / user journey)? user_facing ⇒ its covering milestone MUST be accepted via browser-E2E (M3). Agent-proposed, CUSTOMER-CONFIRMED by being signed into scope. Distinct from customer_disposition."
}
```
- **Authority:** Research/agent MAY propose `surface` (mirrors `intent_contract.drafted_by`); it binds only by being on a REQ the Customer signs into scope. Reclassification of a signed REQ ⇒ re-sign (Customer authority, seal ②).
- **Onboarding (OW-2 + OW-3):** the PRD→ledger wizard assigns `surface` per REQ; for `user_facing` REQs it requires the Gate-1 user-journey `functional-checklist` (OW-3) that M3 judges against.

---

## 3. OW-M3 deliverable: the sign-off gate (enforcement half)

### 3.1 Derivation (pure function, sign-off time)
For each milestone `m`:
```
covered = m.covers_req_ids
# B3/N2: refuse if any rid ∈ covered is absent from the ledger or has no `surface`
surfaces = { rid: ledger[rid].surface for rid in covered }
m_user_facing = "user_facing" ∈ surfaces.values()
required_mode = "browser_e2e" if m_user_facing else <today's resolution unchanged>
```
compared against `resolve_functional_acceptance(charter, m.functional_acceptance)` (campaign.py:2169-2181).

### 3.2 The gate (refuse-to-sign) — at the F1 sign path
Fail closed — refuse to sign — when, for any milestone declaring `covers_req_ids`:
1. **Unknown/unclassified** — a covered `rid` is absent from the ledger, or its REQ has no `surface`. (B3/N2)
2. **Downgrade** — `m_user_facing` AND resolved mode ≠ `browser_e2e`. Message + the **only two** resolutions: *set `functional_acceptance: browser_e2e`, OR (Customer) reclassify the requirement's `surface` and re-sign.* **No waiver in v1 (B4).**

And, at sign-off, **B1 — bind the basis:** `_envelope_milestone` additionally emits `covered_req_surfaces` (the `{rid: surface}` map used for the decision), so it lands in both the stored `scope_envelope` and the hash input `H` (campaign.py:2218-2225). Equivalent acceptable form: a canonical `ledger_digest` over the covered-REQ subset. Either way the surface FACT that justified the mode is now signed — a post-sign surface flip changes `signed_scope_hash` ⇒ `stale`.

### 3.3 What already exists (reuse) vs what is NOT yet guaranteed (Track-2)
**Already true (no OW-M3 code):**
- The resolved mode is in the stored envelope AND `H` (campaign.py:2189-2197, 2218-2225; stamped 2251-2259); the campaign projection materializes it onto the per-milestone derived charter (campaign.py:2351-2368) that `_acceptance_class()` reads (driver.py:3029-3037). So a downgrade is **hash-DETECTABLE.**
- `browser_e2e` + `acceptance.mode:off` is a construction hard-fail (driver.py:697-701) — forcing `browser_e2e` auto-forbids the `acceptance.enabled:false` escape (airecruiter M3/M4) by construction.
- M3 (browser_e2e) pass is **always advisory** in v1 (driver.py:3071-3081; advisory halt at driver.py:4539-4561) regardless of any declared M3 calibration — **so OW-M3 mandates EVIDENCE, not SHIP; no calibration work (cut OW-4) is needed.**

**NOT yet guaranteed (the corrected B2 — Codex R1 OVERSTATED #6):** hash-detection only blocks a run if F1 freshness is re-checked at the resume/dispatch point. Today `_handle_resume` re-checks freshness ONLY for `campaign_plan_signoff`; resume from `advisory_acceptance_pass_signoff` / `deliver_followup_required` / merge can advance without re-verifying `signoff_status == "signed"`. So a post-sign downgrade or `covers_req_ids` mutation while paused is detectable but not yet uniformly blocked. **OW-M3's runtime guarantee therefore DEPENDS on Track-2 (§5).**

### 3.4 Authority preserved
M3 authority unchanged (always advisory in v1). Reclassify/re-sign is Customer-only and signed. Seal ② intact.

---

## 4. Activation, dormancy, and the single-loop path (B3-corrected)
- **Ledger-gated, additive.** The mandate is inert until the input contract exists. With **no `covers_req_ids` / no ledger ⇒ dormant ⇒ byte-identical to today.**
- **Activation point = a milestone DECLARING `covers_req_ids`.** That already triggers F1 (campaign.py:2272-2275); OW-M3 piggybacks: every referenced REQ must exist + be classified, and any `user_facing` REQ forces `browser_e2e` — else refuse-to-sign. (This is why dormancy and the canary no longer contradict: the mandate bites exactly when the adopter opts into requirement coverage.)
- **Single-loop (non-campaign):** no `covers_req_ids`/ledger ⇒ **v1 non-goal**, behavior unchanged (D3/N3). A future `intent_contract.surface` extension could drive the same derivation for single loops.

---

## 5. Dependencies & sequencing (the B2 resolution — Option 2, user-chosen 2026-06-30)
- **OW-M3 sign-off gate (§3.1–§3.2) + B1 snapshot (§3.3) are implementable as a self-contained F1-sign validator change** — but they only make a post-sign mutation DETECTABLE.
- **OW-M3 RUNTIME guarantee requires a separate Track-2 hardening cycle** that must, uniformly:
  1. Re-validate F1 freshness (`signoff_status == "signed"`) before **every** resume decision and **every** dispatch — not only `campaign_plan_signoff` (`_handle_resume`).
  2. Extend authoritative signed-input coverage to **all** post-signoff-mutable verdict/authority-affecting fields, **including the pre-existing `gap_followup.max_subsprints` gap** ([[track2-gap-followup-signing-followup]]).
- **OW-M3 IMPLEMENTATION IS BLOCKED until that Track-2 cycle lands AND earns an independent Codex APPROVE.** OW-M3 does NOT carry a local resume patch and does NOT absorb the campaign state-machine hardening (explicit user decision). This rev2 spec may be finalized/Codex-approved as a design ahead of that.

---

## 6. Decisions (Codex-reviewed; nits folded)
- **D1 (taxonomy)** — v1 binary `user_facing` / `non_user_facing`; M3 trigger = `user_facing`, where `user_facing` means **browser-operable UI / a user journey** (N1). A lighter "user-visible output" tier (e.g. generated reports, emails) needing a non-browser evidence class is **explicitly out of scope v1**.
- **D2 (unclassified)** — **refuse-to-sign**, and likewise refuse on unknown REQ ids / missing ledger whenever `covers_req_ids` is present (N2). Conservative-default (unclassified⇒user_facing) rejected: it would force browser-E2E on backend milestones → the false-positive friction that drove the OW-0 bypass.
- **D3 (single-loop)** — deferred (non-goal v1); single-milestone delivery remains outside the mandate, stated plainly (N3).
- **D4 (gate location)** — the F1-sign validator, enforced at **`--sign-plan` AND the runner `allow_real` preflight** (N4). Resume-time freshness is NOT this gate's job — it is the Track-2 cycle's (§5).
- **N5** — add a sign-time/preflight diagnostic for `browser_e2e` + `acceptance.mode:off` (usability), even though driver-construction is the hard backstop.

---

## 7. Test / canary plan
- **Unit (sign validator):** user_facing REQ + static milestone ⇒ refused; + browser_e2e ⇒ signs; non_user_facing + static ⇒ signs (generality guard); covered REQ absent/unclassified ⇒ refused; no-`covers_req_ids` plan ⇒ byte-identical (dormancy); reclassify+re-sign ⇒ signs with audit.
- **B1 hash binding:** sign a plan; flip a covered REQ's `surface` in the ledger post-sign ⇒ `signed_scope_hash` recompute mismatches ⇒ `signoff_status: stale` (assert detection; the *blocking* on resume is a Track-2 test, §5).
- **Incoherence:** forced browser_e2e + `acceptance.mode:off` ⇒ existing driver.py:697-701 hard-fail fires.
- **Live canary (B3-corrected — POST-OW-2-ADOPTION):** after airecruiter/airplat add a ledger + `covers_req_ids` + `surface`, their UI milestones (airecruiter M4 `presentable-product`, airplat M5) must be **refused-to-sign** until they declare `browser_e2e` — closing the OW-0 bypass. **Pre-adoption they stay dormant** (the mandate cannot bite without the machine-readable signal — that is the honest limit, not a hole).

---

## 8. Seals & risks
- **Seals preserved:** ① completeness⇄quality (the gate reads requirement *surface*, never the verdict's pass/fail); ② Customer authority (reclassify/re-sign only, signed); ③ advisory-by-default (M3 stays advisory).
- **Track-2 dependency (corrected from rev1):** OW-M3's runtime no-downgrade guarantee **DOES** depend on the Track-2 freshness/signed-input hardening (§5) — rev1's claim that it did not was wrong (Codex B2). The `surface`-derived basis is bound into `H` (B1) so it is in scope for that revalidation.
- **Friction guard:** refuse-to-sign must emit the two actionable resolutions (§3.2), or adopters bypass via the no-ledger path — re-creating OW-0's failure.

---

## 9. Citations (corrected to worktree/main `2f0095d`)
| Claim | Anchor |
|---|---|
| resolved mode in stored envelope + hash `H` (+ stamp) | `campaign.py:2189-2197`, `2218-2225`, `2251-2259` |
| mode precedence (milestone > charter > static default) | `campaign.py:2169-2181` |
| campaign projection materializes resolved mode onto derived charter | `campaign.py:2351-2368` |
| F1 opt-in (signoff block OR covers_req_ids presence) | `campaign.py:2272-2275` |
| runtime class reads derived `functional.mode` | `driver.py:3029-3037` |
| browser_e2e + acceptance off ⇒ construction hard-fail | `driver.py:697-701` |
| M3 always advisory in v1 (+ advisory halt) | `driver.py:3071-3081`, `4539-4561` |
| resume re-checks freshness only for campaign_plan_signoff (B2 gap) | `_handle_resume` (campaign.py ~`1691-1697`); initial pause `campaign.py:1894-1907` |
| ledger surface field target | `schemas/requirement-ledger.schema.json` |
