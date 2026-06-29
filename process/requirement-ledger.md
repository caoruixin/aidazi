---
title: Requirement Ledger (Δ-19) — intake-agnostic requirement→milestone→delivery traceability
doc_tier: process
doc_category: live
status: current
implementation_status: phase-2-alpha-backbone (additive; read-model + signoff integrity)
source_of_truth: this file (mechanics) + archive/2026-06-23-requirement-ledger-design.md (rationale, exhaustive impact)
last_reviewed: 2026-06-29
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: by-role
size_target: 8KB
split_trigger: if the disposition/authority section grows past 4KB, split it out
notes: >
  The 15th framework artifact (artifact-taxonomy.md §8). A durable, project-level
  record of every requirement (any intake channel) + the Customer's disposition,
  joined to the signed campaign-plan milestone coverage and the derived delivery
  status. Phase 2-alpha is the ADDITIVE backbone: read-model + the F1 signed-scope
  integrity check. It changes NO ship/route authority (that is the gated Phase 2-gamma
  §1.7-F amendment). Full design + the exhaustive §5 impact inventory live in
  archive/2026-06-23-requirement-ledger-design.md.
---

# Requirement Ledger (Δ-19)

## §1 What it is

A single, **intake-agnostic** record of every requirement — a PRD line, a posed
question, a requirement point, a matured bad-case, an acceptance gap, or a direct
Customer ask — normalized into one durable item with the Customer's **disposition**.
It answers "delivered vs the ORIGINAL requirements, regardless of intake channel,
with per-item disposition" — the question `scope_report`'s Phase-0 backlog view could
not.

- **Artifact:** `docs/requirements-ledger.json` (adopter-side, version-controlled,
  spans campaigns). Schema: `schemas/requirement-ledger.schema.json`.
- **Wiring (optional):** `mission-charter` `requirements.ledger_path`
  (default `docs/requirements-ledger.json`).
- **Additive:** absent ledger ⇒ byte-identical to today. `covers_req_ids` and the
  `signoff` block are new/optional — a legacy plan still validates and runs unchanged.

## §2 The two separated fields (the authority split)

| Field | Owner | Stored where | Notes |
|---|---|---|---|
| `customer_disposition` ∈ `pending\|accepted\|deferred\|skipped\|dropped\|modified` | **Customer ONLY** | the ledger item | §3 below. NEVER written by any engine/agent. |
| `delivery_status` ∈ `delivered\|waived\|in_progress\|not_started\|not_covered` | nobody — **DERIVED** | NOWHERE (a `scope_report` projection) | computed at report time from the milestone's terminal outcome (§4). |

The REQ→milestone map is the signed campaign-plan milestone `covers_req_ids` — the
**single canonical, writable** coverage source (the Deliver Agent fills it;
`campaign_plan_signoff` signs it). The ledger stores **no** writable `covers[]` and
**no** stored `delivery_status`.

## §3 customer_disposition is Customer-only (HARD — §4.E)

`customer_disposition` is **Customer authority, never LLM** (Constitution §1.3/§1.7;
`governance/self-governance.md` §7.0). Agents *propose*; the Customer decides. Enforced
by construction — there is no engine/agent write path to this field.

- **Unsigned-backlog REQ** (covered by no signed milestone / contract): the Customer
  edits the ledger directly (schema-validated; appended to `history`).
- **REQ bound to SIGNED scope** (a signed campaign-plan milestone — incl. a future one
  — or a signed `closure_contract`): the ledger field is **DISPLAY-ONLY**. An actual
  scope change routes through the EXISTING authority routes — a plan **re-sign** or
  `research_contract_revision` — never the ledger. The ledger *reflects*, never
  *drives*, signed scope (keeps Constitution §3.4 invariant #4 intact).

## §3.1 F1 — plan-signature integrity (the re-sign mechanism)

The display-only rule above is only sound if "signed" has integrity. The campaign plan
gains an optional **`signoff` block** carrying the **signed RESOLVED-scope SNAPSHOT**
+ `signed_scope_hash = sha256(canonical_json(H))` (exact spec:
archive/2026-06-23-requirement-ledger-design.md §3.3.1). The runner recomputes the LIVE
resolved envelope + hash at load and honors `campaign_plan_signoff` **ONLY when the
stored hash matches the live hash**:

- **signed** — stored hash == live hash ⇒ the runner proceeds.
- **stale** — a post-signoff edit (a milestone change, a `covers_req_ids` change, or a
  charter-default flip that changes an inheriting milestone's resolved acceptance — G1)
  ⇒ the runner **re-pauses at `campaign_plan_signoff`** for a re-sign. Stale is
  *stale-signed / blocked pending re-sign*, NOT "unsigned".
- **pre_f1** — a bare top-level `signed_by_human: true` with no `signoff` block, on a
  plan that uses `covers_req_ids` ⇒ **one re-sign** stamps the snapshot (one-time
  migration; archive design §7).

F1 is **opt-in**: it activates only when a plan carries a `signoff` block OR any
`covers_req_ids` (both new fields), so a legacy plan stays byte-identical. It adds **NO
new MANDATORY_CHECKPOINT** — it tightens the EXISTING `campaign_plan_signoff` gate.
Re-sign with `run_loop.py --campaign <plan> --charter <charter> --sign-plan` (the engine
stamps the hash; a human cannot hand-compute it).

## §4 delivery_status is DERIVED from the terminal close (never the cursor)

The campaign runner stamps each milestone's **terminal outcome** into campaign-state
(`milestone_outcomes[].terminal`); `scope_report` maps a covered REQ deterministically
(design §3.5.1):

| terminal | delivery_status |
|---|---|
| `acceptance_pass_authoritative` / `acceptance_pass_advisory_ship` | **delivered** |
| `fix_required_ship` / `surface_approve_ship` / `acceptance_off` / `out_of_scope_advance` | **waived** (carries the reason) |
| `not_shipped` (rejected / aborted) | not delivered |

`delivered` requires a recorded **Acceptance pass** (authoritative, or advisory + a ship
signoff). Every close WITHOUT an Acceptance pass — override ship, acceptance-off,
out-of-scope advance — is **waived** with a reason, never silently `delivered`. There is
**NO engine write-back of the ledger** (respects the Acceptance role boundary).

## §5 The single view (`scope_report`)

`scope_report.py --plan <plan> --campaign-home <home> --requirement-ledger <ledger>
[--charter <charter>]` adds (pure / read-only / deterministic):

- per-REQ `delivery_status` × `customer_disposition`;
- **`uncovered_requirements`** — REQs in no fresh-signed milestone AND not validly
  retired (the true PRD gap);
- conflicts: **`invalid_signed_disposition`** (a retiring disposition on FRESH-signed
  scope — kept in the open views, not retired) and **`stale_signoff`** (renders the
  STORED snapshot as "signed (STALE — re-sign required)" beside the live diff; prior
  signed coverage stays reconstructable);
- **drift** — a `covers_req_ids` entry naming a REQ absent from the ledger (read-only,
  never auto-reconciled);
- a requirement-granular **continue menu**;
- an additive machine line **`REQUIREMENT_COVERAGE=`**, emitted ONLY when a valid ledger
  is present. `CAMPAIGN_STATUS=` / `SCOPE_COVERAGE=` stay byte-identical.

## §6 Scope boundary (this phase)

Phase 2-alpha is **read-model + signoff integrity only**. It grants NO authority to
ship, to widen scope, to auto-iterate, or to auto-route Acceptance→Deliver. The
gap-driven completeness auto-routing is the GATED Phase 2-gamma (§1.7-F amendment) and is
out of scope here. See `archive/2026-06-29-track2-gap-followup-amendment-design.md`.
