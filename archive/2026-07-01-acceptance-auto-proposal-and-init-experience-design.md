# Acceptance auto-proposal & initialization experience — design spec (design-only)

- **Date:** 2026-07-01
- **Status:** DESIGN-ONLY (no runtime code changed). **Codex GPT-5.5 xhigh read-only gate = APPROVE (R4)** after R1–R3 REVISE. Awaiting human approval → separate implementation authorization.
- **Author intent (user, 2026-07-01):** *not* another runtime gate — complete the **automatic proposal + initialization experience** so a new adopter codebase **naturally, correctly enables Acceptance**, asking a human only at key authority points.
- **Prerequisite:** PR #5 (`ONBOARDING.md` Step 4b, OW-2/OW-3) merged to `main`. This design **evolves** Step 4b from *optional* to *default-on*.
- **Depends on / builds on:** OW-M3 (mandatory browser-E2E, landed `a8091019`, PR #4), the requirement ledger (Δ-19), Track-2 freshness hardening (`1e6946d`).
- **Branch:** `feat/acceptance-auto-proposal` is **stacked on PR #5** (`feat/ow-m3-onboarding-ow2-ow3`, which adds Step 4b) so onboarding citations resolve; when PR #5 merges, rebase onto the new `main`.

## Revision history
- **rev1** → Codex GPT-5.5 xhigh read-only gate = **REVISE** (`archive/2026-07-01-owauto-codex-review-r1.md`): 3 BLOCKING + 2 NB.
- **rev2 (this doc)** folds all five:
  - **B1 (advisory fields could still reach `acceptance_input_hash`)** — the signed hash was already value-only, BUT the requirement-context sidecar writes the FULL ledger (`campaign.py:3299`) → Acceptance resolver (`driver.py:4204`) → `acceptance_input_hash` (`e2e_stage.py:428`). §4 now requires a **sidecar ledger projection** that strips the advisory fields + a regression test. 
  - **B2 (`customer_disposition: pending` seeded by agent violates the Customer-only invariant)** — new §4.1: a narrow, propagated `pending`-as-initialization-sentinel carve-out.
  - **B3 (onboarding citations not real on `main`)** — resolved by stacking on PR #5; citations verified (Step 4b `:358`, Step 6 `:535`).
  - **NB (wording)** — §1 tightened to "no new checkpoint/gate TYPE; existing OW-M3 gate becomes default-ACTIVE."
  - **NB (inventory)** — §7 expanded with the sidecar/resolver/hash/scope_report/gap_report/tests/process consumers. (`schemas/compact/` has no requirement-ledger projection — confirmed, nothing to re-hash.)
- **rev3** → Codex R2 = REVISE with ONE remaining BLOCKING (B1/B3/NBs all confirmed resolved): the `pending`-sentinel carve-out was under-propagated. §4.1 gained an **explicit propagation table** (each currently-contradictory text + its exact replacement), and §7 points at it as the authoritative list. R2 verdict: `archive/2026-07-01-owauto-codex-review-r2.md`.
- **rev4 (this doc)** → Codex R3 = REVISE with ONE narrow BLOCKING (R3 confirmed the 7 prose/schema contradictions covered + wording tight + list exhaustive): the propagation table's **tests row cited a non-existent authority test** (`test_pc_schemas.py:81` is the structural `RequirementLedgerSchema` class, not an authority assertion). rev4 corrects it to "no existing authority test → ADD a NEW impl test". R3 verdict: `archive/2026-07-01-owauto-codex-review-r3.md`.
- **rev4 → Codex R4 = APPROVE** (`archive/2026-07-01-owauto-codex-review-r4.md`). Design gate CLOSED; design-only, not pushed; awaiting human approval before any implementation.

---

## 0. The gap this closes

Today OW-M3 is **capability-available but opt-in**: it binds only when a knowledgeable human (a) creates a requirement ledger, (b) classifies each REQ's `surface`, and (c) fills milestone `covers_req_ids`. Every one of those is a manual act. Result: both live adopters route around it (OW-0). We want:

> **From** "capability usable, but needs someone who understands the mechanism to actively opt in"
> **to** "a new adopter codebase naturally enables Acceptance correctly, with a human confirming only at key authority points."

**The one non-negotiable:** this adds **no new checkpoint / gate TYPE**. The only engine enforcement stays the EXISTING OW-M3 sign/preflight gate (surface value ⇒ required acceptance class; `run_loop.py:1068` sign, `run_loop.py:659` real-run preflight) and the EXISTING `campaign_plan_signoff` Customer-authority point. Default-generating a ledger (Decision B) does make that EXISTING gate **default-active** for new adopters — which is precisely the goal ("new codebase correctly enables Acceptance"), not a new enforcement path. Everything else new here is **proposal behavior, additive advisory schema fields, onboarding defaults, and authoring-time confirmation UX**.

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

**Open decisions (rev2 status):**
- **DQ-1 — RESOLVED (Codex R1 confirmed the signed-hash half; rev2 closed the sidecar half).** `surface_confidence`/`surface_status` enter NEITHER verdict hash: not `H` (value-only `_covered_req_surfaces`, already true) and not `acceptance_input_hash` (rev2 adds the sidecar projection, §4). A confidence/status edit never invalidates a signed plan (preserves Track-2 "normal evolution never re-signs").
- **DQ-2 — RESOLVED (wording).** Default-on ledger makes the EXISTING OW-M3 sign/preflight gate **default-active** for new adopters — no new checkpoint/gate TYPE (§1). This IS the goal; the two documented resolutions still apply.
- **DQ-3 — RESOLVED via §4.1 carve-out.** Research MAY author `surface`/`statement`/`source` (agent-proposable) and seed `customer_disposition: pending` (undecided sentinel only). No decided disposition is ever agent-written — the Customer-only authority seal is intact.

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
- **Must NOT reach EITHER verdict-affecting hash boundary (§4):** (1) the signed hash `H` (already value-only via `_covered_req_surfaces`), AND (2) the requirement-context sidecar that feeds `acceptance_input_hash` (currently writes the FULL ledger — needs a projection). Only the `surface` VALUE binds.
- **Compact-projection lockstep:** confirmed — `requirement-ledger.schema.json` has NO `schemas/compact/*.compact.schema.json` projection (Codex R1; it is loaded by the campaign runner, not an agent cold-start schema), so there is nothing to re-project / re-hash.

### 3.2 No other schema changes
- `covers_req_ids` already exists (`campaign-plan.schema.json:156`) — Deliver auto-fills it; no schema change.
- `research-brief.schema.json` — **unchanged**; `surface` stays ledger-only, the brief links via `related_r_items` (avoid duplicating the source of truth).

---

## 4. The advisory fields must reach NEITHER verdict-affecting hash (the two boundaries)

This is the sharpest correctness point (Codex R1 B1). There are **TWO** hash boundaries a ledger field can leak into — the design must close BOTH:

**Boundary 1 — the signed scope hash `H` (already safe).**
- The OW-M3 tamper basis is `covered_req_surfaces = {rid: surface}` bound into `H` (`campaign.py:2615` `_covered_req_surfaces` / `campaign.py:2762` `_signed_scope_H`). A post-sign **surface VALUE** flip ⇒ hash mismatch ⇒ `stale` ⇒ re-sign. Correct, must stay.
- `_covered_req_surfaces` projects **only the surface value** — verified. So the new fields already never touch `H`, `signoff_status`, or `compute_signed_scope_hash`. ✓

**Boundary 2 — `acceptance_input_hash` via the requirement-context sidecar (rev2 FIX).**
- At dispatch the campaign writes the **FULL ledger** to `requirement-context.json` (`campaign.py:3299`: `json.dump({"plan":…, "ledger": _ledger, …})`). The Acceptance Driver binds that sidecar (`driver.py:4204` `_load_requirement_context`) and `acceptance_input_hash(projected_prompt, resolver_graph)` (`e2e_stage.py:428`) hashes the resolver-graph content (LOAD-CLOSURE). So today a raw-ledger write means adding `surface_status`/`surface_confidence` **would** churn `acceptance_input_hash` on a purely advisory edit — breaking the Track-2 invariant *"normal autonomous runtime evolution never requires re-sign; only post-signoff authority mutation blocks execution"* and the load-closure `closed:true` guarantee.
- **FIX (design requirement):** the sidecar writer MUST project the ledger through a minimal `requirement_context_ledger_projection()` that **drops `surface_status` + `surface_confidence`** (and any future advisory field) BEFORE the `json.dump` at `campaign.py:3299` — exactly mirroring the existing minimal `campaign_state` projection two lines up (`campaign.py:3294`, which strips volatile spend counters for the same hash-stability reason). The projection keeps `surface` (a genuine gap-report input) and every existing field.

**Mandatory regression test (Phase 1):** flipping ONLY a covered REQ's `surface_confidence` (or `surface_status`) post-sign must leave ALL of `signed_scope_hash`, `signoff_status`, `acceptance_input_hash`, and the advisory `gap_report` **byte-identical**; flipping the `surface` VALUE must still flip `signed_scope_hash` (→ `stale`). This test IS the proof that the two boundaries are closed.

---

## 4.1 `customer_disposition` — the `pending`-sentinel carve-out (Codex R1 B2)

Deliverable 2 has Research create ledger entries, but the schema **requires**
`customer_disposition` on every requirement (`requirement-ledger.schema.json:31`, required
list `:16`) while the current invariant says it is **Customer-only, no engine/agent write
path** (`requirement-ledger.schema.json:31`, `process/requirement-ledger.md:82`,
`process/self-governance.md:59`). An agent cannot create a schema-valid entry without
writing the field — a genuine contradiction.

**Resolution (chosen):** narrow the invariant, don't weaken it. `pending` is not a Customer
DECISION — it is the *undecided* initialization state. Refine the rule to:

> An engine/agent MAY seed a NEW requirement at `customer_disposition: pending` (the
> undecided sentinel). It MUST NEVER write or change a **decided** disposition
> (`accepted | deferred | skipped | dropped | modified`) — those remain **Customer
> authority only**. Any transition out of `pending`, and any change between decided values,
> has no engine/agent write path.

This keeps the authority seal intact (the Customer still owns every actual decision) while
allowing an agent-drafted backlog.

**Propagation — EVERY live "Customer-only / never-agent-written" text must be updated to the
IDENTICAL sentinel rule (Codex R2 B1; each currently CONTRADICTS the carve-out):**

| Surface | Current contradictory text | Must become |
|---|---|---|
| `schemas/requirement-ledger.schema.json:5` (top `description`) | "Records **ONLY** Customer-authored disposition" | "…Customer-authored disposition **(an engine/agent may seed a NEW item at `pending` only; all decided values remain Customer-authored)**" |
| `schemas/requirement-ledger.schema.json:31` (`customer_disposition` field) | "CUSTOMER AUTHORITY ONLY … NEVER written by any engine/agent" | add: "except an engine/agent MAY seed `pending` on a NEW item; it MUST NEVER write/change a decided value" |
| `process/requirement-ledger.md:47` (§2 table row) | "**Customer ONLY** … NEVER written by any engine/agent" | "**Customer ONLY for decided values**; an agent may seed `pending` on a new item" |
| `process/requirement-ledger.md:82-86` (§3 body) | "no engine/agent write path to this field" | "no engine/agent write path to a **decided** disposition; `pending` is an agent-seedable undecided sentinel" |
| `ONBOARDING.md:380` (Step 4b) | "agents *propose*, never set it. There is no engine/agent write path" | "agents may seed `pending` on a new item; they never set a **decided** value" |
| `process/self-governance.md:59` (§7.0) | Customer-only assertion | same sentinel carve-out |
| `process/artifact-taxonomy.md:218` (Artifact #15 producer line) | "the Customer (`customer_disposition`, authority-only)" | "the Customer (decided `customer_disposition`); Research/onboarding may seed `pending`" |
| tests — **no existing authority test** (`test_pc_schemas.py` `RequirementLedgerSchema` is STRUCTURAL only: enum/required/`additionalProperties`/REQ-id — it does NOT assert Customer-only authority, which today is "enforced by construction", no engine write path) | — | **ADD a NEW impl test** on the generator/onboarding path: an agent/engine may create a new item with `customer_disposition: pending` ONLY; an agent-authored **decided** value is rejected; a `pending`→decided transition has no agent write path |

The wording must be tight enough that it can NEVER be read as "agents may change dispositions": the ONLY agent-allowed value is `pending`, and ONLY on creation of a new item; every transition out of `pending` and every decided value stays Customer authority.

**Considered alternative (B):** make `customer_disposition` OPTIONAL (absent ⇒ `pending`) so
agents literally never write it. Cleaner on "no write path" but a larger change
(required→optional relaxation + every reader must handle absence). Rejected for rev2 as more
invasive; re-raise if Codex/human prefers the stronger literal guarantee. **DQ-3 = resolved
in favor of the carve-out.**

## 5. Non-schema changes (prose / defaults / instructions)

### 5.1 `role-cards/research-agent.md` (§2/§3 — proposal instruction)
When authoring a brief, for each requirement the brief covers (its `related_r_items`), ensure a requirement-ledger entry exists carrying: `statement`, `source.channel`, `customer_disposition: pending` (the §4.1 sentinel carve-out — agent may seed `pending` ONLY, never a decided value), and a **proposed `surface` + `surface_confidence`** using the test *"does the end user OPERATE this (browser-operable UI / a user journey)?"*. Mark genuine ambiguity `surface_confidence: low`. The brief itself does NOT carry `surface` (single source of truth = the ledger).

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
- `schemas/requirement-ledger.schema.json:14-53` — add the 2 optional advisory fields (§3.1).
- **`engine-kit/orchestrator/campaign.py:3284-3301`** — the requirement-context sidecar writer: project the ledger to strip advisory fields BEFORE the `json.dump` at `:3299` (§4 B1 fix; mirror the `campaign_state` projection at `:3294`).
- **`customer_disposition` `pending`-sentinel carve-out — the AUTHORITATIVE surface list is the §4.1 propagation table**: 7 currently-contradictory live texts to edit (`schema:5` + `:31`, `requirement-ledger.md:47` + `:82`, `ONBOARDING.md:380`, `self-governance.md:59`, `artifact-taxonomy.md:218`) — each to the IDENTICAL rule, do not update a subset — PLUS **1 NEW authority test** (none exists today; `test_pc_schemas.py` is structural only).
- `role-cards/research-agent.md` §2/§3 (`:45-113`) — proposal instruction + `pending`-sentinel note (§5.1).
- `role-cards/deliver-agent.md` §2.0/§2.1 (`:55-84`) — auto covers_req_ids + self-consistent functional_acceptance (§5.2).
- `ONBOARDING.md` Step 4b (`:358-449`, incl. the `:380` disposition line) + Step 6 (`:535-605`) — default-on + generation (§5.3). *(Verified on this PR#5-stacked branch.)*
- `process/requirement-ledger.md` §2.1 (`:55-80`) — document the advisory model (§5.4).
- `templates/adoption-state-template.md` (`:58`) — reflect that the ledger is a default new-adopter artifact.
- (optional) `templates/requirements-ledger.example.json` — NEW additive template (seeded, with proposed surfaces + confidence).

**Consumers to re-check (Codex R1 NB-2 — read the new fields tolerantly / project them out):**
- `engine-kit/orchestrator/driver.py:4204` `_load_requirement_context` (binds the sidecar) → `:4517`-area `acceptance_input_hash` call → `engine-kit/orchestrator/e2e_stage.py:428` `acceptance_input_hash` — MUST see the projected ledger (advisory fields absent).
- `engine-kit/orchestrator/scope_report.py:311` `compute_requirement_coverage` / `build_gap_report` (`:451` reads `covers_req_ids`) — tolerate + ignore the new fields (no gap-report churn).
- `engine-kit/validators/tests/test_pc_schemas.py:81` + ledger fixtures (`engine-kit/orchestrator/tests/fixtures/requirements-ledger.sample.json`) — extend for the new optional fields.

**Must-stay-untouched invariants (regression guards):**
- `campaign.py` `_covered_req_surfaces` (`:2615-2630`), `_signed_scope_H` (`:2762-2781`), `mandatory_e2e_violations` (`:2826-2873`), `signoff_status` (`:2955+`) — the signed-hash basis and the OW-M3 gate stay VALUE-only (§4). No new gate.
- `engine-kit/orchestrator/e2e_stage.py:428 acceptance_input_hash` + `acceptance_load_closure.py closed:true` — stay stable under an advisory-field flip **because of the §4 sidecar projection** (the fields DO reach the sidecar today; the projection is what keeps the hash untouched).
- `load_and_validate_ledger` (`:2558-2597`) / `duplicate_requirement_ids` (`:2538-2555`) — still validate; the new optional fields pass through.
- Track-2 freshness (`test_track2_autonomy_nonregression.py`) — must stay 5/5 (advisory fields never flip freshness).

**Governance / kernel lockstep to verify (likely no change, must confirm):**
- `kernel_equivalence --kernel-coverage` (70/70) — constitution untouched.
- `--authoring-kernel-coverage` (41/41) — confirm role-card additions don't alter a kernel-inventoried authoring constraint (they are additive prose, not new normative constraints).
- WP-9 context-budget (`context_budget_report.py`) — role-card/schema growth may WARN on drift; rebaseline or waive per WP-9 doctrine (advisory, never a forced shrink).
- `schemas/compact/*` — confirm no compact projection of `requirement-ledger.schema.json` (if any, re-project + `x-canonical-sha256` lockstep).

**Full verification set (impl):** `pytest engine-kit maintainer -q` · kernel `--kernel-coverage`/`--authoring-kernel-coverage` · `acceptance_load_closure.py` (`closed:true`) · WP-9 `-k context_budget` · Track-2 non-regression (5/5) · OW-M3 targeted (`test_ow_m3_mandatory_e2e.py`, 34) · **+ NEW tests:** (a) schema accepts/omits the 2 optional fields; (b) `mandatory_e2e_violations`/`signoff_status` ignore confidence/status; (c) **the §4 advisory-flip invariant** — flip `surface_confidence`/`surface_status` ⇒ `signed_scope_hash`, `signoff_status`, `acceptance_input_hash`, `gap_report` all byte-identical, while flipping the `surface` VALUE still flips `signed_scope_hash`→`stale`; (d) the sidecar projection drops the advisory fields.

---

## 8. What this deliberately does NOT do

- **No new checkpoint / gate TYPE.** The only enforcement remains the existing OW-M3 sign/preflight gate + `campaign_plan_signoff`; default-on merely makes that existing gate default-active (§1).
- **No auto-BINDING of surface without a human.** Agents propose; the Customer binds by signing. `surface_status: confirmed` is advisory, never a precondition the engine checks.
- **No agent write path to a DECIDED `customer_disposition`** — decided values stay Customer-only (Constitution §1.3/§1.7); agents may seed ONLY the `pending` undecided sentinel (§4.1).
- **No forced migration of legacy adopters** — ledger-less repos stay byte-identical.
- **Single-loop `intent_contract.surface` (D3) and per-REQ verdict wiring (OW-5)** remain deferred (out of scope here; this cycle is campaign-tier proposal + init UX).

---

## 9. Handoff

This is design-only. Next: Codex GPT-5.5 xhigh read-only gate over this doc (read-only sandbox; do NOT run the suite in-sandbox) → fold findings → human approval → separate implementation authorization (own branch, phased per §6, full verification + fresh code-level Codex gate before any PR).
