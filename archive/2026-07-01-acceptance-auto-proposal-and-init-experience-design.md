# Acceptance auto-proposal & initialization experience — design spec (design-only)

- **Date:** 2026-07-01
- **Status:** DESIGN-ONLY (no runtime code changed). Awaiting Codex GPT-5.5 xhigh read-only gate → human approval → separate implementation authorization.
- **Author intent (user, 2026-07-01):** *not* another runtime gate — complete the **automatic proposal + initialization experience** so a new adopter codebase **naturally, correctly enables Acceptance**, asking a human only at key authority points.
- **Prerequisite:** PR #5 (`ONBOARDING.md` Step 4b, OW-2/OW-3) merged to `main`. This design **evolves** Step 4b from *optional* to *default-on*.
- **Depends on / builds on:** OW-M3 (mandatory browser-E2E, landed `a8091019`, PR #4), the requirement ledger (Δ-19), Track-2 freshness hardening (`1e6946d`).

---

## 0. The gap this closes

Today OW-M3 is **capability-available but opt-in**: it binds only when a knowledgeable human (a) creates a requirement ledger, (b) classifies each REQ's `surface`, and (c) fills milestone `covers_req_ids`. Every one of those is a manual act. Result: both live adopters route around it (OW-0). We want:

> **From** "capability usable, but needs someone who understands the mechanism to actively opt in"
> **to** "a new adopter codebase naturally enables Acceptance correctly, with a human confirming only at key authority points."

**The one non-negotiable:** this adds **NO new runtime gate**. The only engine enforcement stays the EXISTING OW-M3 sign-off gate (surface value ⇒ required acceptance class) and the EXISTING `campaign_plan_signoff` Customer-authority point. Everything new here is **proposal behavior, additive schema fields, onboarding defaults, and authoring-time confirmation UX**.

**Seals preserved (unchanged):** ① completeness⇄quality source separation, ② Customer final authority, ③ advisory-by-default. The single binding authority point remains `campaign_plan_signoff`.

---

## 1. The six deliverables → mechanism map

| # | Goal | Mechanism (design) | New gate? |
|---|---|---|---|
| 1 | New adopter init default-generates the ledger | Onboarding Step 4b flips optional→**default-on** for greenfield/new; Step 6 generates `docs/requirements-ledger.json` by default. *Ledger existence = the switch* (Decision B). | No |
| 2 | Research/RB proposes `surface` per requirement | `research-agent.md` instruction: when authoring a brief, ensure a ledger entry per covered requirement with a **proposed `surface` + `surface_confidence`**. `surface` stays ledger-only (the brief links via `related_r_items`). | No |
| 3 | Deliver auto-generates `covers_req_ids` | `deliver-agent.md` instruction: at campaign-plan / decompose authoring, auto-derive each milestone's `covers_req_ids` from the ledger REQs it delivers (carrying their proposed surfaces). `covers_req_ids` already exists in the schema + signed envelope. | No |
| 4 | Human confirms only low-confidence + final plan | Additive ledger fields `surface_status ∈ {proposed, confirmed}` + `surface_confidence ∈ {high, low}` (agent self-assessed, Decision A). Wizard/loop **proactively surface only `low` items** for human confirm; everything else flows to sign-off. | No |
| 5 | After confirmation, OW-M3 auto-decides browser-E2E | **Unchanged** — this is the existing `mandatory_e2e_violations` derivation at `--sign-plan`. Steps 1-4 simply feed it a well-formed ledger + `covers_req_ids`. | No (existing) |
| 6 | Old adopters compatible; new default new path | *Ledger existence = the switch*: a repo with no ledger stays dormant (byte-identical). Only onboarding **new** adopters generate one. No migration forced on legacy repos. | No |

---

## 2. Decisions (locked by user 2026-07-01)

- **D-A — Confidence model = additive fields.** Add to each ledger requirement: optional `surface_status ∈ {proposed, confirmed}` and `surface_confidence ∈ {high, low}` (agent self-assessed at proposal time). Agent proposes ALL; the wizard/loop escalates ONLY `surface_confidence: low` (or `surface_status: proposed` on a high-risk REQ) for a lightweight human confirm. **These fields are ADVISORY authoring signals — they are NOT bound into the signed hash and the engine never gates on them** (see §4 for why). Sign-off remains the binding Customer authority.
- **D-B — Default-on = ledger existence is the switch.** Onboarding default-generates `docs/requirements-ledger.json` for new/greenfield adopters. A repo without a ledger stays dormant. No charter flag, no adoption-config toggle — the file's presence is the whole signal (most additive, matches the existing dormancy seal).
- **D-C — Scope = one design doc, all six deliverables**, implemented in internal phases (§6), one Codex gate for the design.

**Open decisions for Codex/human (this spec proposes a default; flag if wrong):**
- **DQ-1** — Should `surface_confidence`/`surface_status` enter the signed hash? **Proposed: NO** (advisory only; the binding basis stays the surface VALUE via `covered_req_surfaces`, so a confidence/status edit never spuriously invalidates a signed plan — preserves Track-2 "normal evolution never re-signs"). §4.
- **DQ-2** — Does default-on ledger create a de-facto gate for new adopters (since OW-M3's refuse-to-sign now fires by default)? **Proposed: this is intended and is NOT a new gate** — it is the EXISTING OW-M3 gate becoming default-active, which is exactly "new codebase correctly enables Acceptance." The two documented resolutions still apply.
- **DQ-3** — Should Research author ledger entries directly, given `customer_disposition` is Customer-only? **Proposed: YES for `surface`/`statement`/`source` (agent-proposable); `customer_disposition` stays Customer-only and defaults to `pending` on an agent-created entry** (no engine/agent write path violation — `surface` is explicitly agent-proposable per the schema).

---

## 3. Schema changes (additive only)

### 3.1 `schemas/requirement-ledger.schema.json` (per-requirement, additive, optional)

```jsonc
"surface_status":     {"type": "string", "enum": ["proposed", "confirmed"],
  "description": "OW-AUTO advisory authoring signal. 'proposed' = agent-proposed surface not yet human-confirmed; 'confirmed' = a human accepted it at authoring time. ADVISORY ONLY — the engine never gates on this and it is NOT bound into the signed scope hash; the binding confirmation is the Customer signing the covering plan. Absent ⇒ treated as 'proposed'."},
"surface_confidence": {"type": "string", "enum": ["high", "low"],
  "description": "OW-AUTO advisory: the agent's self-assessed confidence in its proposed surface. The wizard/loop escalates only 'low' items for a lightweight human confirm before sign-off. ADVISORY ONLY — not bound into the signed hash, never gated on. Absent ⇒ treated as 'high' (flows without escalation)."}
```

- Both OPTIONAL under the existing `additionalProperties: false` requirements item — a legacy ledger stays valid, byte-identical.
- **NOT added to `covered_req_surfaces` / the signed hash `H`** (§4). Only `surface` (the value) continues to bind.
- **Compact-projection lockstep:** verify at impl whether `requirement-ledger.schema.json` has a `schemas/compact/*.compact.schema.json` projection + `x-canonical-sha256` (it is loaded by the campaign runner, not an agent cold-start schema, so likely none — but the impact inventory MUST confirm and, if present, re-project + re-hash in lockstep).

### 3.2 No other schema changes
- `covers_req_ids` already exists (`campaign-plan.schema.json:156`) — Deliver auto-fills it; no schema change.
- `research-brief.schema.json` — **unchanged**; `surface` stays ledger-only, the brief links via `related_r_items` (avoid duplicating the source of truth).

---

## 4. Why the confidence fields must NOT enter the signed hash (the load-closure boundary)

This is the sharpest correctness point (Codex will probe it):

- The OW-M3 tamper basis is `covered_req_surfaces = {rid: surface}` bound into `H` (`campaign.py` `_covered_req_surfaces` / `_signed_scope_H`). A post-sign **surface VALUE** flip ⇒ hash mismatch ⇒ `stale` ⇒ re-sign. That is correct and must stay.
- If `surface_confidence`/`surface_status` also entered `H`, then a purely **advisory** edit (agent lowers its confidence, or a human flips `proposed`→`confirmed`) would flip the hash and **spuriously invalidate a correctly-signed plan** — violating the Track-2 invariant *"normal autonomous runtime evolution never requires re-sign; only post-signoff authority mutation blocks execution."*
- Therefore: `_covered_req_surfaces` continues to project **only the `surface` value**; the new fields are read ONLY by the onboarding wizard + Research/Deliver prompts (authoring-time), never by `mandatory_e2e_violations`, `signoff_status`, `compute_signed_scope_hash`, or the acceptance resolver. **`acceptance_input_hash` and the load-closure `closed:true` invariant are untouched.**

---

## 5. Non-schema changes (prose / defaults / instructions)

### 5.1 `role-cards/research-agent.md` (§2/§3 — proposal instruction)
When authoring a brief, for each requirement the brief covers (its `related_r_items`), ensure a requirement-ledger entry exists carrying: `statement`, `source.channel`, `customer_disposition: pending` (Customer-only; agent seeds `pending`), and a **proposed `surface` + `surface_confidence`** using the test *"does the end user OPERATE this (browser-operable UI / a user journey)?"*. Mark genuine ambiguity `surface_confidence: low`. The brief itself does NOT carry `surface` (single source of truth = the ledger).

### 5.2 `role-cards/deliver-agent.md` (§2.0 / §2.1 — auto covers_req_ids)
At campaign-plan authoring / milestone decompose, auto-derive each milestone's `covers_req_ids` from the ledger REQs that milestone delivers, and set `functional_acceptance: browser_e2e` for any milestone covering a `user_facing` REQ (so the signed plan is self-consistent BEFORE sign-off — no refuse-to-sign surprise). This mirrors the existing `task_signals` authoring pattern (§3.6): Deliver authors it in the signed plan; it binds at sign-off; post-sign mutation goes stale via the existing hash.

### 5.3 `ONBOARDING.md` (Step 4b default-on + Step 6 generation)
- Step 4b: flip framing from *"(Optional)"* to **default-on for greenfield/new adopters** — the wizard drafts a ledger from the PRD with agent-proposed surfaces (status `proposed`, confidence per-item), and **escalates only `low`-confidence items** for human confirm. Brownfield-without-PRD may still defer (records a `divergent` row).
- Step 6: add `docs/requirements-ledger.json` to the generated-artifacts list (default), seeded (not blank). Optionally add a real `templates/requirements-ledger.example.json` (additive template) rather than pointing at the test fixture.
- Journey table + step-count stay consistent (Step 4b already present from PR #5).

### 5.4 `process/requirement-ledger.md` (document the proposed/confirmed + confidence model)
Extend §2.1 (or add §2.2) documenting: the advisory `surface_status`/`surface_confidence` fields, that they are NOT bound/gated (§4), the "escalate only low-confidence" UX, and that sign-off remains the binding confirmation.

---

## 6. Implementation phasing (all inside decision D-C; each verified, one Codex gate for the design)

- **Phase 1 — proposal wiring (schema + role-cards):** §3.1 additive ledger fields; §5.1 research-agent surface-proposal instruction; §5.2 deliver auto-`covers_req_ids` instruction. Additive, dormant without a ledger.
- **Phase 2 — initialization default-on (onboarding):** §5.3 Step 4b default-on + Step 6 generation + optional example template; §5.4 process-doc update.
- **Phase 3 — confidence-confirm UX:** the "escalate only low-confidence" interaction in the wizard + loop prose (no engine change).

Each phase is additive and independently green; nothing hardens the loop.

---

## 7. Exhaustive impact inventory (verify each at impl; Codex-citation-checkable)

**Change (edited) surfaces:**
- `schemas/requirement-ledger.schema.json:14-53` — add 2 optional fields (§3.1).
- `role-cards/research-agent.md` §2/§3 (`:45-113`) — proposal instruction (§5.1).
- `role-cards/deliver-agent.md` §2.0/§2.1 (`:55-84`) — auto covers_req_ids + self-consistent functional_acceptance (§5.2).
- `ONBOARDING.md` Step 4b (`:358-449`) + Step 6 (`:535-605`) — default-on + generation (§5.3).
- `process/requirement-ledger.md` §2.1 (`:55-80`) — document the model (§5.4).
- (optional) `templates/requirements-ledger.example.json` — NEW additive template.

**Must-stay-untouched invariants (regression guards):**
- `campaign.py` `_covered_req_surfaces` (`:2615-2630`), `_signed_scope_H` (`:2762-2781`), `mandatory_e2e_violations` (`:2826-2873`), `signoff_status` (`:2955+`) — the signed-hash basis and the OW-M3 gate stay VALUE-only (§4). No new gate.
- `engine-kit/orchestrator/e2e_stage.py:acceptance_input_hash` + `acceptance_load_closure.py closed:true` — untouched (the new fields never reach the acceptance prompt).
- `load_and_validate_ledger` (`:2558-2597`) / `duplicate_requirement_ids` (`:2538-2555`) — still validate; the new optional fields pass through.
- Track-2 freshness (`test_track2_autonomy_nonregression.py`) — must stay 5/5 (advisory fields never flip freshness).

**Governance / kernel lockstep to verify (likely no change, must confirm):**
- `kernel_equivalence --kernel-coverage` (70/70) — constitution untouched.
- `--authoring-kernel-coverage` (41/41) — confirm role-card additions don't alter a kernel-inventoried authoring constraint (they are additive prose, not new normative constraints).
- WP-9 context-budget (`context_budget_report.py`) — role-card/schema growth may WARN on drift; rebaseline or waive per WP-9 doctrine (advisory, never a forced shrink).
- `schemas/compact/*` — confirm no compact projection of `requirement-ledger.schema.json` (if any, re-project + `x-canonical-sha256` lockstep).

**Full verification set (impl):** `pytest engine-kit maintainer -q` · kernel `--kernel-coverage`/`--authoring-kernel-coverage` · `acceptance_load_closure.py` · WP-9 `-k context_budget` · Track-2 non-regression · OW-M3 targeted (`test_ow_m3_mandatory_e2e.py`) · + NEW tests for the additive fields (schema accepts/omits; gate ignores confidence/status; freshness unaffected by a confidence flip).

---

## 8. What this deliberately does NOT do

- **No new runtime gate.** The only enforcement remains the existing OW-M3 sign-off derivation + `campaign_plan_signoff`.
- **No auto-BINDING of surface without a human.** Agents propose; the Customer binds by signing. `surface_status: confirmed` is advisory, never a precondition the engine checks.
- **No `customer_disposition` write path for agents** — stays Customer-only (Constitution §1.3/§1.7; unchanged).
- **No forced migration of legacy adopters** — ledger-less repos stay byte-identical.
- **Single-loop `intent_contract.surface` (D3) and per-REQ verdict wiring (OW-5)** remain deferred (out of scope here; this cycle is campaign-tier proposal + init UX).

---

## 9. Handoff

This is design-only. Next: Codex GPT-5.5 xhigh read-only gate over this doc (read-only sandbox; do NOT run the suite in-sandbox) → fold findings → human approval → separate implementation authorization (own branch, phased per §6, full verification + fresh code-level Codex gate before any PR).
