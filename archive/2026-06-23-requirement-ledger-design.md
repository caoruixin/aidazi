---
title: Requirement Ledger Design — unified, intake-agnostic requirement→milestone→delivery ledger (Phase 1)
doc_tier: process
doc_category: intermediate
status: approved-design (Codex gpt-5.5 xhigh APPROVE after 5 rounds, 2026-06-23)
implementation_status: design-only
source_of_truth: this file (until folded into constitution/process/schemas at implementation)
last_reviewed: 2026-06-23
review_cadence: this fold-back sub-sprint
revision: rev5+nb (APPROVED rev5 + 3 round-5 non-blocking prose/schema refinements folded; rounds 1–4 REVISE history in §0.1–§0.4)
load_discipline: on-demand
notes: >
  DESIGN SPEC ONLY — no code changed. Builds on the Phase-0 scope-coverage work
  (engine-kit/orchestrator/scope_report.py + run_loop SCOPE_COVERAGE= wiring,
  currently UNCOMMITTED on v2-loop-engine). Phase 0 answers "delivered vs the SIGNED
  BACKLOG"; this spec answers "delivered vs the ORIGINAL REQUIREMENTS, regardless of
  intake channel, with per-item disposition". User framing (2026-06-23): any
  requirement source (PRD / posed question / requirement-point / matured bad-case /
  acceptance-gap) normalizes into ONE durable, viewable record; no per-source ledger.
  Reviewer: Codex gpt-5.5 (xhigh), headless. rev1 → rev2 after round-1 REVISE.
---

# Requirement Ledger Design (2026-06-23) — rev2

## §0 How to review this document

Design spec, not implementation. No code changed. Reviewer (Codex gpt-5.5, xhigh)
judges, in order: (1) **soundness**, (2) **invariant consistency**
(`governance/constitution.md` §1.3, §1.7-*, §3.4 #4, §3.5, §3.7, §7.0, §10;
`process/delivery-loop.md` §4.2.3/§4.2.5; `process/campaign-loop.md` §3.4),
(3) **backward compatibility** (the no-ledger path stays dormant), (4) **completeness
of the impact inventory** (§5 — the user's explicit "no omissions" requirement).
Judge the design, not the prose. Default to REVISE/REJECT if the additivity claim
(§3.3, §10) does not hold. Line targets in §5 are best-effort against `v2-loop-engine`
@ 2026-06-23; re-confirm at implementation.

### §0.1 rev2 changelog — what Codex round-1 (REVISE) changed

The central correction: **the ledger never drives signed scope, and disposition is
split from delivery state.** Five blocking fixes:

- **B1 — signed future scope.** rev1 let the Customer freely edit the ledger for any
  REQ "not in an in-flight milestone." But REQs covered by a *signed* campaign-plan
  milestone (even a future one) or a signed `closure_contract` are **signed scope**.
  Fixed (§3.3): ledger disposition for any REQ bound to signed scope is
  **display-only**; an actual scope change routes through the EXISTING re-sign paths
  (plan re-sign / `research_contract_revision`). Only **unsigned backlog** REQs are
  freely Customer-editable.
- **B2 — authority vs runtime conflation.** rev1's single `disposition` mixed
  Customer intent (`accepted/dropped/…`) with runtime state (`in_progress/delivered`),
  and had Acceptance write `delivered` — which violates the Acceptance role boundary
  (`role-cards/acceptance-agent.md` §9: writes only `acceptance-reports/` +
  `checkpoints/`). Fixed (§2.1, §3.3, §3.5): **two fields** — `customer_disposition`
  (Customer-only) and a **derived `delivery_status`** computed purely by `scope_report`
  from campaign-state. **No engine/Acceptance write-back at all** — `delivered` is a
  projection, which also shrinks the engine surface.
- **B3 — two mapping sources.** rev1 made both `ledger.covers[]` and
  `milestones[].covers_req_ids[]` writable. Fixed (§2.1, §3.4): the **signed
  campaign-plan `covers_req_ids` is the single canonical** REQ→milestone map; the
  ledger has **no writable `covers[]`** — coverage is derived.
- **B4 — double-counting at intake.** An Acceptance `fix_required` (or a matured
  bad-case) is usually an *existing* REQ not yet met, not a new requirement. Fixed
  (§3.1): those channels carry `relates_to_req_ids` + `gap_type`; a NEW REQ is created
  only on Customer/Research confirmation of `new_scope`.
- **B5 — under-specified strict checkpoint.** The optional `requirement_disposition`
  checkpoint (rev1 §3.7) needed an emitter, identity binding, schema branch, resolver
  pass-through (the resolver drops unknown fields; `campaign-decision.schema.json`
  rejects non-`choice` fields), dispatch action, resume hint, and tests. Since B1
  routes all signed-scope changes through existing gates, **the new checkpoint is
  DROPPED entirely** (§3.7) — removing the only fail-closed-inventory risk.

Plus suggestions folded in: `waived` delivery state for `confirm:no` ship-with-residual
(§3.3); `REQUIREMENT_COVERAGE=` emitted only when a valid ledger is present (§3.6); an
Acceptance hard rule that ledger disposition never suppresses a signed `closure_contract`
clause (§3.5). Decisions §4.A/§4.D/§4.E/§4.F updated. 10 inventory omissions folded into §5.

### §0.2 rev3 changelog — what Codex round-2 (REVISE) changed

Round-2 RESOLVED B3 (single canonical map) and B4 (intake double-count guard), and
rated B1/B2/B5 PARTIAL — converging on **one root cause: `campaign_plan_signoff` has no
integrity binding** (it is just `signed_by_human: true`, `process/campaign-loop.md` §6),
so "route signed-scope changes through re-sign" rested on a re-sign mechanism that does
not actually exist — a plan can be edited after signoff while staying "signed." rev3:

- **F1 — plan signature integrity (NEW §3.3.1; closes B1/B5 + blocking #1).** The
  campaign plan gains a `signoff` block carrying a **content hash of the scope-bearing
  fields** (`milestones[].{id,objective,covers_req_ids,subsprint_sequence,depends_on}`).
  Any post-signoff edit to those fields makes the live hash diverge from the signed
  hash ⇒ signoff is **stale**; the runner and `scope_report` **refuse to consume a
  plan whose signed hash ≠ live hash** until re-signed (a new signature epoch). This
  surfaces a **pre-existing framework gap** the ledger depends on — it is hardening of
  `campaign_plan_signoff`, inventoried in §5.
- **F2 — scope_report reports conflicts; never hides signed REQs (closes B2/B1 #2).**
  A `customer_disposition ∈ {dropped,skipped,deferred}` on a REQ that is covered by a
  signed plan/contract is an **`invalid_signed_disposition` conflict**: `scope_report`
  emits it as drift AND keeps the REQ in the remaining / uncovered signed-scope views
  until a re-sign reconciles it. Ledger disposition can only *retire* a REQ from views
  once it is **not** bound to signed scope.
- **F3 — complete delivery terminal-event table (NEW §3.5.1; closes B2/B5 #3).**
  `delivered` ⇏ "cursor advanced past the milestone." It is derived from the milestone's
  **terminal close event**: Acceptance pass **+ any required human signoff**. ALL
  human-override ship paths WITHOUT an Acceptance pass map to **`waived`** — not only
  `acceptance_fix_required + confirm:no`, but also `acceptance_surface_approve →
  approve_ship` [**CORRECTED in §0.3 G4:** an advisory `pass` + ship signoff *is* an
  Acceptance pass ⇒ `delivered`, NOT `waived`; only non-pass ships are `waived`].
  The runner stamps each milestone's terminal outcome into campaign-state (additive
  field) so the projection is deterministic, with a precedence table + tests.

Non-blocking folded in: schema conditionals (`gap_type=unmet_existing` ⇒ non-empty
`relates_to_req_ids`; `new_scope` ⇒ confirmation ref); **at-most-one covering milestone
per REQ** in Phase 1 (multi-milestone aggregate rules deferred to Phase 2);
`covers_req_ids` unique + REQ-id-patterned. 3 more inventory omissions folded into §5
(`templates/compact-acceptance-prompt.md`; the signed-plan signature-enforcement row;
tests for invalid signed disposition + `approve_ship`→non-delivered). §4.D refined.

### §0.3 rev4 changelog — what Codex round-3 (REVISE) changed

Round-3 rated F1/F2/F3 PARTIAL (mechanism right, coverage incomplete), B5 still RESOLVED,
no structural objections. Four refinements:

- **G1 — F1 hash domain too narrow (§3.3.1).** `functional_acceptance` changes the real
  Acceptance path (`process/campaign-loop.md` §3.7; `campaign.py` `derive_milestone_context`)
  but rev3 excluded it from the signed hash. Fixed: the signed envelope now includes
  `functional_acceptance` and `acceptance_bar` (where present) and top-level `goal`; rev4
  also pins the **hash spec** (sha256 over canonical JSON — sorted keys, UTF-8, no
  insignificant whitespace — with a `v1:` version prefix).
- **G2 — `modified` was a signed-scope bypass (§2.1/§3.3/§3.6).** Fixed: `modified` joins
  `dropped/skipped/deferred` as an `invalid_signed_disposition` conflict when the REQ is
  bound to fresh signed scope — UNLESS the supersession is part of the re-signed
  plan/contract.
- **G3 — terminal table incomplete (§3.5.1).** Added the missing terminal close paths:
  **Acceptance-off** milestone close, and terminal **`review_out_of_scope →
  accept_and_advance`** — neither is an Acceptance pass, so both map to **`waived`** (with
  a `reason`), never `delivered`. `waived` is broadened to "shipped/closed WITHOUT an
  Acceptance pass (override / acceptance-off / out-of-scope advance)".
- **G4 — stale-signoff reporting + an advisory-pass contradiction (§3.6/§3.5.1).** Fixed:
  `scope_report` emits a first-class **stale-signoff conflict** and shows prior signed
  coverage as "stale — re-sign required" rather than letting ledger retirement look
  settled. AND corrected my own contradiction: an **advisory `pass` + human ship signoff
  IS an Acceptance pass ⇒ `delivered`** (rev3 §0.2 wrongly lumped it under `waived`; the
  §3.5.1 table was already correct). Only non-pass ships (`confirm:no`, `approve_ship`) =
  `waived`.

Non-blocking folded in: hash spec (above); a one-time-migration note that pre-F1
`signed_by_human` plans must still schema-validate long enough to re-pause + re-sign
(§7); 4 more inventory omissions (cross-milestone at-most-one validator;
`campaign-plan.example.json` + CLI resume-hint signoff workflow; driver.py
acceptance-prompt-graph review; stale-signoff / acceptance-off / out-of-scope-advance
tests) into §5.

### §0.4 rev5 changelog — what Codex round-4 (REVISE) changed

Round-4 RESOLVED G2 (`modified` conflict) and G3 (terminal table), kept B5 RESOLVED, and
rated G1/G4 PARTIAL — both tracing to one fact: **a hash of LITERAL plan fields does not
capture RESOLVED Acceptance semantics.** When `functional_acceptance` is absent, the
milestone inherits the charter's mode (`process/campaign-loop.md` §3.7;
`campaign.py::derive_milestone_context`), so a charter-default change can flip the effective
Acceptance class with no plan-field (hence no hash) change; and a hash alone cannot
reconstruct prior signed coverage for stale-signoff display. rev5 replaces the
hash-of-fields with a **stored signed scope-envelope SNAPSHOT** (§3.3.1):

- **G1 (resolved-semantics signing).** The `signoff.scope_envelope` stores each milestone's
  **resolved** `functional_acceptance {mode, source}` (not the literal, possibly-absent
  field) plus `charter_ref` + `charter_hash`. A charter-default flip now changes the
  resolved envelope ⇒ stale ⇒ re-sign — closing the inheritance hole.
- **G4 (reconstructable prior coverage).** Because the envelope is *stored*, not just
  hashed, `scope_report` renders the prior signed coverage from the snapshot during a
  `stale_signoff` conflict (`freeze_baseline` stores too little, so the snapshot lives in
  the `signoff` block). Ledger retirement is never shown as settled while stale.

Non-blocking folded in: hash-envelope array normalization (absent ≡ `[]`); `campaign_id`
in the signed envelope; legacy `signed_by_human` vs `signoff` precedence (§3.3.1). Three
more inventory items (signed-snapshot storage/schema/test; the absent-`functional_acceptance`
+ charter-flip re-sign test; the explicit pre-F1 migration test) folded into §5.

---

## §1 Problem & goals

### §1.1 What the investigation found (2026-06-22 → 2026-06-23)

- **No single, intake-agnostic requirement record.** A PRD (or posed question, or
  requirement point) is digested by the **Research Agent** into **one milestone-grained
  `closure_contract`** (`role-cards/research-agent.md` §4) — a *behavioral* contract,
  frozen at Gate-1. Per-requirement granularity is lost at intake.
- **No requirement→milestone→delivery traceability.** Milestones carry no
  `covers_req_ids` (`schemas/campaign-plan.schema.json`); Phase-0 `scope_report.py`
  measures vs the **signed backlog**, not the requirements (its own docstring names the
  `covers_req_ids`/write-back ledger "a later phase").
- **Status vocabulary cannot express disposition.** `campaign-state` unit status is
  lifecycle-only — `pending/in_progress/done/halted/failed`
  (`schemas/campaign-state.schema.json`). No `skipped/dropped/deferred/modified`.
- **Three never-joined axes:** contract (`proposals`→`research-briefs`), execution
  (`campaign-plan`→`campaign-state`→`scope_report`), backlog (`action_bank`). The
  closest hub, `action_bank` (`process/artifact-taxonomy.md` §1.1), is a risk/observation
  working set swept to archive each milestone close — not the primary requirement set.
- **No scope-REDUCTION route.** The engine can EXPAND scope
  (`post_gate1_scope_expansion`, `scope_deviation` accept) and narrow-replan
  (`scope_deviation` reject), but has **no first-class audited route for the Customer to
  skip/drop/defer/modify a requirement**.

### §1.2 Goals

- **G1** One durable, intake-agnostic **Requirement Ledger**.
- **G2** Per-item **`customer_disposition`** modelling real choices, with order/priority.
- **G3** **Traceability**: signed-milestone `covers_req_ids` ⇒ a *derived* per-REQ
  delivery status (no write-back).
- **G4** **One view**: `scope_report` projects per-REQ coverage + the killer
  **`uncovered_requirements`** line (requirements in no milestone — the true PRD gap).
- **G5** **Continue-menu at requirement granularity**, in one place.

### §1.3 Non-goals (this phase)

Not an auto-decomposer; not LLM-set disposition (§4.E); not a `closure_contract`
rewrite (it stays the authoritative judgment surface; the ledger *links* to it); not
cross-campaign rollups or a parallel runner (Phase 2+).

---

## §2 Design overview

### §2.1 The requirement item

```
REQ-NNN
  title              short human label
  statement          the requirement as asked (the user's words)
  kind               business | technical | constraint    ← fixes "technical reqs homeless"
  source             { channel, ref }  channel ∈ prd | question | requirement_point |
                                       bad_case | acceptance_gap | customer_direct
  priority           must | should | could        (MoSCoW)
  order              integer (stable sequence)
  customer_disposition   pending | accepted | deferred | skipped | dropped | modified
                         ── CUSTOMER AUTHORITY ONLY; default `pending` at creation (§3.3)
  delivery_status        (DERIVED — read-only projection by scope_report; NOT stored as truth)
                         not_started | in_progress | delivered | waived          (§3.5)
  gap_type           (intake guard, B4) unmet_existing | new_scope | null
  relates_to_req_ids [REQ-…]  for acceptance_gap / bad_case that point at an EXISTING REQ
  elaboration        [ref]  ledger→brief/bad-case reference (ONE-WAY; never copies text;
                            the brief is NOT modified — research-brief.schema.json is
                            additionalProperties:false, §5)
  supersedes / superseded_by   for `modified` (old REQ → new REQ)
  history            append-only [{ts, actor, field, from, to, note}]  audit of CUSTOMER edits
```

There is **no writable `covers[]`** on the item (B3): the REQ→milestone mapping lives
only on the signed campaign-plan milestone (`covers_req_ids`, §3.4); coverage is
derived. **Index, not duplicate:** the ledger references elaborations; it never copies
`closure_contract` text. **`modified` is a signed-scope-affecting disposition** (G2): if
a REQ bound to fresh signed scope is marked `modified`, that is a conflict handled exactly
like `dropped/skipped/deferred` (§3.6) unless the supersession is itself part of a
re-signed plan/contract.

### §2.2 How it joins what exists (joins; replaces nothing)

```
            ┌──────────────────────────────────────────────────────────────┐
            │  Requirement Ledger  (docs/requirements-ledger.json)          │ NEW, durable, project-level
            │  REQ-001…  statement + customer_disposition (+ derived view)   │ single source for "what was asked + intent"
            └───────────┬───────────────────────────────────┬──────────────┘
        elaboration ref │  (one-way)                          │  covers_req_ids on SIGNED milestone (canonical map, B3)
                        ▼                                      ▼
   research-briefs/<id>.md (closure_contract)          campaign-plan.json (signed milestones)   EXISTING
   — Gate-1 frozen, authoritative judgment                    │
                                                              ▼
                                                  campaign-state.json (units, cursor)            EXISTING (execution truth)
                                                              │
                                                              ▼
                              scope_report.py ── JOINS ledger × signed plan × state ──►          EXTENDED (pure projection)
                                 derives delivery_status + uncovered_requirements + continue menu
```

`action_bank` R-items become one `source.channel` feeding the ledger — no parallel
backlog.

### §2.3 Scoping: project-level + durable

The ledger lives at **`docs/requirements-ledger.json`** (adopter-side, version-controlled,
spans campaigns). `campaign-state` (execution) stays in the campaign home; `scope_report`
joins them at report time.

---

## §3 Detailed design

### §3.1 Intake normalization (every channel → REQ items; B4 guard)

| Channel | Today's artifact | Normalization |
|---|---|---|
| PRD | (none formal) | Research, at Gate-1, emits one REQ per requirement; `source.channel=prd`, `customer_disposition=pending` |
| Posed question → research | prompt → `research-brief` | REQs from Scope-IN/closure_contract clauses; `elaboration=[brief_id#clause]` |
| Requirement point | prompt / `proposals/` | one REQ; `source=requirement_point` |
| Matured bad-case | `failure-briefs/` (Path 2) | **default `gap_type=unmet_existing` + `relates_to_req_ids`**; new REQ only if Customer/Research confirm `new_scope` |
| Acceptance gap | `acceptance-report` `fix_required` | **`gap_type=unmet_existing` + `relates_to_req_ids`** by default (a gap is usually an existing REQ not met, not new scope) |
| Direct customer ask | — | `source=customer_direct` |

The **Research Agent** populates at Gate-1; the **Customer** owns `customer_disposition`;
the **Deliver Agent** sets `covers_req_ids` on milestones (not on the ledger);
`delivery_status` is **derived**, never written (§3.5).

### §3.2 The ledger artifact

- **Path:** `docs/requirements-ledger.json` (canonical, schema-validated). Human view
  rendered by `scope_report` (§3.6).
- **Schema:** NEW `schemas/requirement-ledger.schema.json`.
- **Lifecycle:** `live`, durable across campaigns; delivered/dropped items may sweep to
  `docs/requirements-ledger-archive.json` at milestone close (parallel to
  `action_bank`→archive, `process/self-governance.md` §7.3).
- **Load discipline:** **by-role** (Research/Deliver/Acceptance/Customer); not
  always-load (§4.B).
- **Framework artifact #15** — `process/artifact-taxonomy.md` §8 anticipates this.

### §3.3 Disposition vs delivery — two separated fields (B1, B2)

**`customer_disposition` (Customer authority only):**
```
   pending ──Customer accept──► accepted        (Customer may → deferred / skipped / dropped / modified)
      └─► deferred ⇄ skipped ─► dropped (terminal)
      modified: Customer files a superseding REQ; old → modified, new → pending
```

**Authority + the signed-scope rule (the additivity guarantee):**

- **Disposition is Customer-only, never LLM** (Constitution §1.3, §1.7; §4.E). Agents
  *propose*; the Customer decides.
- **Unsigned backlog REQ** (covered by no signed milestone and no signed
  closure_contract): the Customer changes `customer_disposition` by **editing the
  ledger** — exactly how `campaign_plan_signoff` is resolved by editing the plan
  (`process/campaign-loop.md` §6). Schema-validated; appended to `history`.
- **REQ bound to SIGNED scope** (a signed campaign-plan milestone — *including a future
  one* — or a signed closure_contract): ledger disposition is **DISPLAY-ONLY**. An
  actual scope change goes through the **existing** authority route — re-sign the plan
  (a milestone removal/edit is a plan revision) or `research_contract_revision` (Gate-1
  re-fires) for a contract change. The ledger then *reflects* the re-signed outcome; it
  never *drives* it. **This is what keeps Constitution §3.4 invariant #4 intact** (§10).

#### §3.3.1 Plan signature integrity — the missing re-sign mechanism (F1; closes B1/B5)

The signed-scope rule above is only sound if "signed" has integrity. Today
`campaign_plan_signoff` is merely `signed_by_human: true` (`process/campaign-loop.md`
§6) — **a plan can be edited after signoff (remove a milestone, change a future
`covers_req_ids`) while staying "signed."** That is itself the silent-narrowing vector.
rev3 introduced the signature epoch; rev5 hardens it to a **signed resolved-scope
snapshot** (so charter-inherited Acceptance changes are caught and prior coverage is
reconstructable):

- The plan gains a **`signoff` block** that stores a **signed scope-envelope SNAPSHOT**
  (rev5/G1+G4), not merely a hash of literal fields:
  `{ signed_by_human, signer, signed_at, charter_ref, charter_hash, scope_envelope,
  signed_scope_hash }`.
- **`scope_envelope` is the RESOLVED scope at sign time** — for each milestone:
  `{ id, objective, covers_req_ids, subsprint_sequence, depends_on,
  resolved_functional_acceptance: {mode, source}, acceptance_bar }` plus top-level `goal`.
  Crucially it stores the **resolved** Acceptance class `{mode, source}` (not the literal
  `functional_acceptance`, which may be ABSENT and inherit the charter default —
  `process/campaign-loop.md` §3.7; `campaign.py` `derive_milestone_context`). It also
  records `charter_ref` + `charter_hash`. **G1:** a charter-default change that flips an
  inheriting milestone's resolved mode now changes the envelope ⇒ stale, even though no
  literal plan field changed.
- **Hash spec (one exact object — round-5 NB1):** `signed_scope_hash =
  sha256(canonical_json(H))` where
  `H = { version: "v1", campaign_id, goal, charter_ref, charter_hash,
  milestones: [ {id, objective, covers_req_ids, subsprint_sequence, depends_on,
  resolved_functional_acceptance: {mode, source}, acceptance_bar}, … ] }`.
  `goal`/`charter_hash` live INSIDE `H` (not concatenated alongside `scope_envelope`),
  so the input is unambiguous. Canonical JSON = UTF-8, keys sorted, no insignificant
  whitespace, arrays normalized (absent ≡ `[]` for `depends_on`/`covers_req_ids`/
  `subsprint_sequence` so absent-vs-empty doesn't churn). The `version` field replaces the
  old `"v1:"` string prefix and versions the hash domain.
- The runner recomputes the **live** resolved envelope + hash at load. **`signed` is
  honored only when the stored `signed_scope_hash` == the live resolved hash.** Mismatch
  ⇒ `signoff` is **stale**: the runner re-pauses at `campaign_plan_signoff` (re-sign
  required; re-stamps the snapshot). New signature epoch = the "plan revision" §3.3 invokes.
  Stale scope is **stale-signed / blocked pending re-sign** (round-5 NB2) — NOT "unsigned",
  and NOT usable to retire REQs from views.
- **G4:** because the `scope_envelope` snapshot is *stored*, `scope_report` can render the
  **prior signed coverage** (the snapshot) even when the live plan has diverged — it shows
  the stale snapshot as "signed (STALE)" beside the live diff, so a ledger retirement is
  never presented as settled. Reconstruction no longer depends on a hash alone.
- **Legacy precedence (suggestion 3):** a bare top-level `signed_by_human: true` with NO
  `signoff` block is treated as **pre-F1** (missing snapshot) ⇒ one re-sign required (§7);
  when a `signoff` block exists, it is authoritative and the legacy flag is ignored.

This is a **pre-existing framework gap** the ledger surfaces; it is hardening of
`campaign_plan_signoff`, not ledger-only — fully inventoried in §5.2/§5.3/§5.5/§5.7.
*(It composes with the existing fail-closed signoff check; it adds no new checkpoint id,
so the inventory test stays green — §3.7.)*

**`delivery_status` (DERIVED — never authored):** a pure `scope_report` projection from
campaign-state + audit via the milestone's **terminal close event** (§3.5.1), NOT from
cursor position. No Acceptance/Deliver/runner write of the ledger (respects
`role-cards/acceptance-agent.md` §9).

### §3.4 Coverage mapping — single canonical source (B3)

- Add **optional** `covers_req_ids: string[]` to each milestone in
  `schemas/campaign-plan.schema.json`. Optional ⇒ every existing plan still validates.
- The Deliver Agent fills it; `campaign_plan_signoff` then signs the requirement→milestone
  mapping. **This is the ONLY writable mapping.** The ledger does not store `covers[]`;
  `scope_report` reads `covers_req_ids` off the signed plan.
- **Constraints (round-2 suggestions 2,3):** `covers_req_ids` entries are **unique** and
  **REQ-id-patterned** (`^REQ-`); in Phase 1 a REQ is covered by **at-most-one** milestone
  (multi-milestone aggregate-status rules are deferred to Phase 2 — §9 R4).
- Asymmetry (a REQ named by no milestone, or a `covers_req_ids` naming an unknown REQ) is
  reported as **drift** by `scope_report` (read-only) — not auto-reconciled.

### §3.5 Delivery is derived, not written back; Acceptance precedence rule

- `scope_report` derives `delivery_status` (§3.5.1) at report time. There is **no engine
  write-back of the ledger**, so no Acceptance role-boundary breach.
- **Acceptance precedence (hard rule):** a ledger `customer_disposition` NEVER suppresses
  a signed `closure_contract` clause. If a REQ bound to a signed contract shows
  `skipped/dropped` in the ledger while the contract still asserts it, that is a
  **conflict → halt and route to re-sign** (`research_contract_revision`), never a silent
  suppression. Goes into the Acceptance role card + `compact-acceptance-prompt.md`.

#### §3.5.1 Delivery terminal-event table (F3; closes B2/B5)

`delivered` ⇏ "cursor advanced past the milestone" — a campaign can advance past a
milestone that shipped **without** an Acceptance pass (human override). So the runner
**stamps each milestone's terminal outcome** into campaign-state (NEW additive field
`milestone_outcomes[]: {milestone_id, terminal, pause_reason, decision_ref}`), and
`scope_report` maps the milestone's covered REQs deterministically:

| Milestone terminal close path | covered REQs → |
|---|---|
| Acceptance `pass`, authoritative → advance | `delivered` |
| Acceptance `pass`, advisory → `advisory_acceptance_pass_signoff` `confirm: ship` (an advisory pass IS a pass) | `delivered` |
| Acceptance `fix_required` → `confirm: no` (ship residual risk) | `waived` (reason=`fix_required_ship`) |
| `needs_human` → `acceptance_surface_approve` → `approve_ship` | `waived` (reason=`surface_approve`) |
| **Acceptance OFF** (`tooling.acceptance.mode: off`) terminal `STATE_ADVANCE` close (G3) | `waived` (reason=`acceptance_off`) |
| **terminal `review_out_of_scope → accept_and_advance`** (no Acceptance pass) (G3) | `waived` (reason=`out_of_scope_advance`) |
| advisory pass → `reject`, or any abort/non-ship | `not_started`/`in_progress` (not shipped) |

`waived` = milestone shipped/closed **WITHOUT an Acceptance pass** — for ANY reason
(override / acceptance-off / out-of-scope advance), carrying a `reason`. It is **never
counted as `delivered`** (delivered requires a recorded Acceptance pass + any required
signoff). Precedence is read from the last milestone unit's `pause_reason` + recorded
`decision` + acceptance mode (audit/`milestone_outcomes`), with a dedicated test matrix
(§5.5) that exercises every row above.

### §3.6 `scope_report` upgrade (the single view)

Stays **pure / read-only / deterministic**. Adds a requirement projection joining
`(ledger, signed campaign-plan, campaign-state + milestone_outcomes)`:

- per-REQ `delivery_status` (§3.5.1) × `customer_disposition`;
- **conflict reporting (F2 + G2):** a `dropped/skipped/deferred/modified` disposition on a
  REQ that is **bound to fresh-signed scope** (§3.3.1) is surfaced as an
  **`invalid_signed_disposition`** conflict, and the REQ is **kept in** the remaining /
  uncovered signed-scope views until a re-sign reconciles it. A disposition can retire a
  REQ from views **only** when it is not bound to signed scope;
- **stale-signoff conflict (G4):** when the stored `signed_scope_hash` ≠ the live resolved
  hash (§3.3.1), `scope_report` emits a first-class **`stale_signoff`** conflict and renders
  **the stored `scope_envelope` snapshot** as "signed (STALE — re-sign required)" beside the
  live diff. Because the snapshot is stored (not just hashed), prior signed coverage is fully
  reconstructable; while stale, a ledger retirement is NOT presented as settled until a fresh
  re-sign;
- **`uncovered_requirements`**: REQs covered by no fresh-signed milestone AND not validly
  retired — the true PRD gap;
- requirement-granular **continue menu** (remaining = not `delivered`/`waived`, not
  validly dropped/skipped);
- additive machine line **`REQUIREMENT_COVERAGE=`**, emitted **only when a valid ledger
  is present** (suggestion 2); `CAMPAIGN_STATUS=` / `SCOPE_COVERAGE=` stay byte-identical.

### §3.7 No new checkpoint (B5)

Because §3.3 routes every signed-scope change through existing gates, the design adds
**NO new MANDATORY_CHECKPOINT and NO `campaign-decision` schema change.** This keeps the
fail-closed inventory untouched (`process/campaign-loop.md` §3.4 /
`test_campaign.py::TestCheckpointInventoryFailClosed` stays green). Unsigned-backlog
disposition is a ledger edit; a signed-scope change is `research_contract_revision` or a
**plan re-sign whose integrity is now enforced by the signature epoch (§3.3.1)** — both
ride the EXISTING `campaign_plan_signoff` checkpoint id (the §3.3.1 hash check tightens
that one gate; it does not add a new id). *(A future dedicated strict-mode decision file
would still need full spec — emitter, identity binding, schema branch, resolver
pass-through, dispatch action, resume hint, inventory classification, tests — deferred.)*

---

## §4 Key design decisions (forks — recommendation first)

- **§4.A — closure_contract frozen (RECOMMENDED).** Confirmed by round-1: keep frozen,
  AND the ledger may never alter Acceptance criteria or signed scope without a re-sign
  (§3.3, §3.5). Reject live-derivation.
- **§4.B — load discipline by-role (RECOMMENDED, agreed).** Wire through role lists +
  compact prompts, not the always-load chain.
- **§4.C — JSON canonical + rendered view (RECOMMENDED, agreed).** Caveat: Customer edits
  need tooling or a decision-file path to preserve `history` reliably — provide a small
  `ledger_edit` helper or a validated edit format (Phase 1b).
- **§4.D — REVISED (round-1 + round-2).** Ledger-edit applies to **unsigned backlog
  only**; signed-plan / active scope changes go through re-sign routes — and round-2
  exposed that the re-sign route had **no integrity**, so §3.3.1 now defines a concrete
  **plan signature epoch (signed scope hash)** that makes "signed" enforceable. Without
  §3.3.1 this decision is unsound; with it, the unsigned/signed split holds.
- **§4.E — disposition is Customer-only (HARD).** The B2 split (Customer
  `customer_disposition` vs derived `delivery_status`) is what makes this enforceable;
  add the hard requirement to `governance/self-governance.md` §7.0 and wire so no agent
  writes `customer_disposition`.
- **§4.F — REVISED per round-1.** This is broader than the Δ-12 artifact taxonomy:
  introduce it as a **new Δ (e.g. Δ-19) with its own `process/requirement-ledger.md`
  AND an explicit `adoption-state` row**, in addition to the artifact-taxonomy entry.
  (rev1 leaned "extend Δ-12"; round-1 flagged that as too narrow.)

---

## §5 IMPACT INVENTORY (exhaustive — the explicit ask; rev2 folds 10 round-1 omissions)

Legend: **N** normative · **B** breaking (needs migration note) · **A** additive.

### §5.1 New schemas
| File | Change | Flag | Phase |
|---|---|---|---|
| `schemas/requirement-ledger.schema.json` | NEW — item array; `customer_disposition` enum; `source`; `gap_type`; `relates_to_req_ids`; `elaboration`; `history`; (NO writable `covers[]`, NO stored `delivery_status`) | new | 1a |

### §5.2 Schema edits
| File | Change | Flag |
|---|---|---|
| `schemas/campaign-plan.schema.json` | add **optional** `milestones[].covers_req_ids: string[]` (unique, `^REQ-` patterned, at-most-one-milestone — §3.4); add **`signoff` block** `{signed_by_human, signer, signed_at, charter_ref, charter_hash, scope_envelope, signed_scope_hash}` storing the **signed resolved-scope SNAPSHOT** (F1/G1/G4, §3.3.1) — the `signoff` block is OPTIONAL so pre-F1 plans still validate (§7), but a **conditional (round-5 NB3): if `signoff.signed_by_human: true` then the complete snapshot fields are REQUIRED** (a partial signoff block is fail-closed / treated as stale) | A (covers_req_ids); N (signoff snapshot/integrity) |
| `schemas/campaign-state.schema.json` | add **`milestone_outcomes[]`** `{milestone_id, terminal, pause_reason, decision_ref}` so delivery_status is derivable deterministically (F3/§3.5.1) | A |
| `schemas/campaign-decision.schema.json` | **no change** (B5 — no new checkpoint) | — |
| `schemas/research-brief.schema.json` | **no change** — it is `additionalProperties:false` (lines 17/53/94); the REQ↔brief link lives in the ledger's one-way `elaboration`, NOT in the brief (omission #2) | — |
| `schemas/deliver-plan-verdict.schema.json`, `deliver-plan-fix.schema.json`, `sprint_stanza.schema.json` | **only if** req IDs flow BELOW milestone level (NOT in Phase 1 — milestone is the granularity); listed so the boundary is explicit (omission #3) | — (deferred) |
| `schemas/mission-charter.schema.json` | OPTIONAL `requirements.ledger_path` (default `docs/requirements-ledger.json`) | A |

### §5.3 Engine code
| File | Function(s) | Change | Flag |
|---|---|---|---|
| `engine-kit/orchestrator/scope_report.py` | `compute_coverage`, `summary_line`, `render_text`, `freeze_baseline`, `load_baseline`, `main` | add REQ projection + derived `delivery_status` + `uncovered_requirements` + `--requirement-ledger`; **render the stored `signoff.scope_envelope` snapshot for stale-signoff (G4)** — note `freeze_baseline` currently stores only id/objective/subsprint, so the signed snapshot must come from the plan's `signoff` block, not the scope-baseline; pure/read-only | A |
| `engine-kit/scheduling/run_loop.py` | `run_campaign_entry` (~446-531, scope_coverage block 505-516), `print_campaign_result` (559-603), `main` campaign branch | load+validate ledger; add `requirement_coverage`; emit `REQUIREMENT_COVERAGE=` ONLY when ledger valid | A |
| `engine-kit/orchestrator/campaign.py` | `_validate_or_raise` (67-103); the `campaign_plan_signoff` honor check; `derive_milestone_context` (resolved acceptance mode); the milestone-advance/close path (run loop ~713-834) | validate ledger when present; **F1/G1: recompute the live RESOLVED scope-envelope (incl. resolved `functional_acceptance {mode,source}` + charter_hash) + hash, honor signoff only when it matches the stored snapshot hash, else re-pause**; **F3: stamp `milestone_outcomes[]` at each milestone close**; no ledger write-back, no new checkpoint id | N (F1/G1), A (F3) |
| `engine-kit/scheduling/run_loop.py` | the campaign-plan-signoff resolution path; result assembly | surface stale-signoff (hash mismatch) as the re-sign pause; carry `milestone_outcomes` through (F1/F3) | N |
| `engine-kit/orchestrator/driver.py` + `tests/test_driver.py` | inspect for any Delivery-Loop checkpoint/coverage path (omission #1); **review the projected Acceptance prompt/resolver graph** so the precedence rule (§3.5) applies even when no `compact-acceptance-prompt.md` exists (round-3 omission #3); expected minimal change but must be CONFIRMED | — (verify) |

### §5.4 Validators
| File | Change | Flag |
|---|---|---|
| `engine-kit/orchestrator/campaign.py` `_validate_or_raise` | validates extended plan + new ledger schema automatically | A |
| `engine-kit/validators/charter_validator.py` | no change | — |
| `engine-kit/validators/adopter_wiring_validator.py` (+ `tests/test_adopter_wiring_validator.py`, omission #8) | OPTIONAL: assert `docs/requirements-ledger.json` present + `@`-wired in adopter AGENTS.md | A |
| **NEW: cross-milestone plan validator** (in `campaign.py` semantic checks or a new validator; round-3 omission #1) | **at-most-one covering milestone per REQ** + `covers_req_ids` uniqueness across milestones — JSON Schema alone can't enforce a cross-array rule | N |
| `engine-kit/validators/stanza_validator.py` | no change | — |

### §5.5 Tests (extend / new / may-break)
| File | Why |
|---|---|
| `engine-kit/orchestrator/tests/test_scope_report.py` | EXTEND: REQ projection, derived delivery_status, waived (all reasons), uncovered, drift, summary/render; **stale-signoff conflict keeps prior signed coverage visible (G4/round-3 omission #4)**; `modified`→`invalid_signed_disposition` (G2) |
| `engine-kit/validators/tests/test_pc_schemas.py` | EXTEND: requirement-ledger schema metaschema + sample |
| `engine-kit/scheduling/tests/test_run_loop_campaign.py` | EXTEND: sample plan gains `covers_req_ids`; ledger load; `REQUIREMENT_COVERAGE=` present-only; **sample-validates test updates** |
| `engine-kit/orchestrator/tests/test_campaign.py` | confirm persisted-state still validates; **no checkpoint-inventory change** (B5); **F1 signature epoch — edit-after-signoff ⇒ stale ⇒ re-pause**; **G1: `functional_acceptance` ABSENT + charter default flips ⇒ resolved envelope changes ⇒ stale ⇒ re-sign** (round-4 omission #2); **pre-F1 migration: bare `signed_by_human:true`, no snapshot, schema-valid, exactly one re-pause/re-sign** (round-4 omission #3); **F3 terminal-outcome stamping** for each ship path |
| `engine-kit/orchestrator/tests/test_campaign_e2e.py` (omission #7) | production-path: no-ledger dormant + derived coverage with a ledger; **every terminal-table row (§3.5.1): `approve_ship`, `confirm:no`, acceptance-OFF close, `review_out_of_scope→accept_and_advance` ⇒ `waived` not `delivered`** (round-3 omission #4) |
| NEW `tests/test_requirement_ledger.py` | disposition transitions; intake B4 guard (gap_type conditionals); Customer-only authority; **`invalid_signed_disposition` conflict kept visible (F2)**; terminal-table matrix → delivery_status (F3) |

### §5.6 Governance (constitution-touch ⇒ author applies, agent proposes only)
| File | Change | Flag |
|---|---|---|
| `governance/constitution.md` | §7.0 hard req "`customer_disposition` is Customer authority, never LLM" (§4.E); §1.7 optional clause (no LLM/regex disposition); §3.4 #4 CLARIFY (ledger additive, contract frozen, display-only for signed scope); §4 index pointer | N |
| `governance/doc_governance.md` | doc-level enums unchanged; note the item-level `customer_disposition` enum is artifact-level | N |
| `governance/context_briefing.md` | add ledger to **by-role** briefings (Research/Deliver/Acceptance); not always-load | N |

### §5.7 Process docs
| File | Change | Flag |
|---|---|---|
| `process/artifact-taxonomy.md` | **14→15** (lines 23/25/27/29); new §1.15; per-role read/produce; lineage; §8 "16th…" | N, B(count) |
| `process/doc-responsibility-matrix.md` | ownership row(s): Customer authority for `customer_disposition`; Research/Deliver/Acceptance read | N |
| `process/campaign-loop.md` | §5.1 Phase-0 → Phase-1; cross-link `covers_req_ids`; note derived delivery (no write-back); **§6: define the signature epoch — `campaign_plan_signoff` now honors a signed scope hash (F1/§3.3.1)** | N |
| `process/delivery-loop.md` | note derived coverage; **no new checkpoint** (B5); Acceptance precedence rule (§3.5); terminal-outcome stamping (F3) | N |
| `process/milestone-framework.md` | milestone authoring references `covers_req_ids` | N |
| `docs/directory-taxonomy.md` | decision-tree + per-dir row for `docs/requirements-ledger.json` | N |
| `process/badcase-lifecycle.md`, `process/post-deployment-iteration.md` | bad-case/OBS→ledger as one `source.channel` w/ `gap_type` (B4) | N |
| `process/context-passing-efficiency.md`, `process/prompt-artifact-rules.md` (omission #6) | `load_list` sufficiency: when a role must load the ledger | N |
| NEW `process/requirement-ledger.md` | the spec's process-tier home; new Δ (§4.F) | N(new) |
| `process/self-governance.md` | §7.0 hard req (§4.E); live/archive sweep | N |
| `process/fold-back-protocol.md` | adoption-state row if adopters diverge on the vocabulary | N |

### §5.8 Role cards
| File | Change |
|---|---|
| `role-cards/research-agent.md` | populate ledger at Gate-1 (all channels, B4 guard); one-way `elaboration` link (brief unchanged); symmetry self-check extended |
| `role-cards/deliver-agent.md` | set milestone `covers_req_ids`; read `customer_disposition`; never write the ledger's disposition |
| `role-cards/acceptance-agent.md` | **does NOT write the ledger** (§9 boundary preserved); apply the Acceptance precedence rule (§3.5) |
| `process/customer-checkpoints.md` | document Customer disposition authority: ledger-edit (unsigned) vs existing re-sign routes (signed) |

### §5.9 Templates
| File | Change |
|---|---|
| NEW `templates/requirements-ledger.template.json` | starting shape |
| `templates/campaign-plan.example.json` | add `covers_req_ids` per milestone + a `signoff` block example (signed_scope_hash workflow); CLI resume hints (`run_loop.py` `_campaign_resume_hint`) must explain the re-sign-on-stale-hash step (round-3 omission #2) |
| `templates/milestone-objective.md` | front-matter `covered_requirements` + cross-ref |
| `templates/compact-research-brief.md` | **no `req_ids` field** (brief stays additionalProperties:false); add a prose note that REQs are tracked in the ledger |
| `templates/compact-acceptance-prompt.md` (round-2 omission #1) | wire the Acceptance precedence rule (§3.5): ledger disposition never suppresses a signed `closure_contract` clause; conflict ⇒ halt/re-sign |
| `templates/handoff-template.md` | §0 row "open requirement issues" |
| `templates/adoption-state-template.md` | Step-0 ledger init; divergence row if vocabulary customized |
| `templates/sprint-objective.md`, `templates/compact-dev-prompt.md`, `templates/compact-review-prompt.md` (omission #4) | review whether any should surface covered REQ ids for context; default = no change in Phase 1 (milestone granularity) |
| `templates/mission-charter.yaml` | OPTIONAL `requirements.ledger_path` |

### §5.10 Examples
| File | Change |
|---|---|
| `examples/minimal-greenfield/docs/requirements-ledger.json` | NEW worked example |
| `examples/minimal-greenfield/docs/milestone_objective.md`, `AGENTS.md`, `docs/action_bank.md` | @-wire + cross-ref |
| `examples/minimal-greenfield/{README.md, charter.yaml}` + example tests (omission #9) | update if the example adopts the ledger |
| other `examples/*` (quickfix…) | verify N/A |

### §5.11 Onboarding / guides / READMEs
| File | Change |
|---|---|
| `ONBOARDING.md` | Step-0 init ledger; Step-4 populate first REQs; roadmap line |
| `FIRST-LOOP.md` | cold-start reads include ledger (by-role) |
| `docs/greenfield-guide.md` | after first brief → populate ledger |
| `README.md`, `README.zh-CN.md`, `docs/adoption-overview.md`, `docs/brownfield-guide.md` (omission #5) | mention the ledger in the artifact overview + brownfield adoption/back-fill |
| `engine-kit/scheduling/README.md`, `engine-kit/orchestrator/README.md` (omission #10) | document the new CLI/reporting surface (`--requirement-ledger`, `REQUIREMENT_COVERAGE=`) |

### §5.12 Audit + machine contracts
| Surface | Change | Flag |
|---|---|---|
| `engine-kit/audit/audit_log.py` | NEW event(s): `requirement_ledger_loaded` (load/validate). **No** `requirement_delivered` write (delivery is derived, B2) | A |
| `CAMPAIGN_STATUS=` / `SCOPE_COVERAGE=` | unchanged (byte-identical); additive `REQUIREMENT_COVERAGE=` only when ledger valid | A |

### §5.13 Adopter repos / migration (see §7)
| Repo | Change |
|---|---|
| `airplat` (submodule, mid-campaign) | back-fill ledger from briefs; add `covers_req_ids`; forward |
| `venture-strategy` (submodule, M1–M4 closed) | retrospective back-fill M1–M4; forward from M5 |
| `airecruiter` (if present) | same back-fill |

---

## §6 Phasing

- **Phase 1a — read model:** ledger schema + template + optional `covers_req_ids` +
  `milestone_outcomes[]` (F3) + `scope_report` REQ projection (derived delivery_status via
  the terminal-event table) + `uncovered_requirements`. Read-only reporting; delivers
  G3/G4 at near-zero engine risk.
- **Phase 1b — disposition + signature integrity + governance (the load-bearing phase):**
  `customer_disposition` + Customer ledger-edit (unsigned only) + `history` + B4 intake +
  **the F1 plan signature epoch (prerequisite for the unsigned/signed split to be sound)**
  + F2 conflict reporting + the governance/process/role-card/template docs (artifact #15,
  new Δ). Delivers G1/G2/G5. **Note:** F1 is a hardening of `campaign_plan_signoff` that
  stands on its own and could land first.
- **Phase 1c — polish:** Acceptance precedence rule wired into `compact-acceptance-prompt.md`,
  README/onboarding/example. (No engine write-back of the ledger; no new checkpoint id.)

Each phase independently shippable and Codex-gated.

---

## §7 Migration (existing adopters)

Dormant when the ledger is absent (`covers_req_ids` optional; `scope_report` already
degrades). Opt-in per repo: (1) back-fill `docs/requirements-ledger.json` from existing
`research-briefs/*` (one REQ per clause; `customer_disposition=accepted` for shipped work)
and `acceptance-reports/*` (derived delivery shows `delivered`); (2) add `covers_req_ids`
to live `campaign-plan.json`; (3) record adoption in `docs/current/adoption-state.md`
(divergence row only if the vocabulary is customized). `venture-strategy` (M1–M4 closed):
retrospective back-fill; forward from M5. `airplat` (mid-campaign): back-fill done
milestone, forward from current.

**F1 one-time migration:** a plan signed before the signature epoch has no
`signed_scope_hash`. The `signoff` block fields are **optional in the schema** so a pre-F1
plan (bare `signed_by_human: true`) **still schema-validates** — long enough for the runner
to detect the missing hash and re-pause at `campaign_plan_signoff` for exactly one re-sign
(which stamps the hash); thereafter the integrity check is live. This is a single, expected
re-sign per existing campaign — call it out so it is not mistaken for a regression.

---

## §8 Governance & review plan

Substantive framework change (new artifact #15 + new schema + constitution-touch).
Per `memory/foldback-stance.md` + Constitution §8: the **author** applies §5.6
constitution edits; the **agent never edits the constitution unilaterally** — they are
*proposed* here. **Codex gpt-5.5 xhigh** reviewed this spec over 5 rounds:
round-1..4 REVISE (folded into §0.1–§0.4), **round-5 APPROVE** (zero blocking issues,
zero inventory omissions, all §4 decisions hold; 3 non-blocking refinements folded as
rev5+nb). Each phase diff still goes through the same gate
(`memory/codex-verification-gate.md`).
**Sequencing:** the uncommitted Phase-0 `scope_report` work is this spec's substrate —
Codex-review + commit it first.

---

## §9 Risks & open questions

- **R1 — vocabulary creep.** 6 `customer_disposition` values; could collapse
  `skipped`/`dropped` if Customers won't distinguish. Decide at §4 review.
- **R2 — double-maintenance.** Mitigated by one-way `elaboration` + no copied contract
  text (§2.1); a validator MAY check REQ.statement ≠ a copy of a closure_contract clause.
- **R3 — ID scheme.** Project-level stable `REQ-NNN` + `source.ref` (supports
  cross-campaign).
- **R4 — multi-milestone coverage.** Phase 1 enforces at-most-one covering milestone per
  REQ (§3.4); drift reported read-only; a write reconciler + aggregate-status rules are
  Phase 2.
- **R5 — Customer edit history fidelity** (§4.C) — needs an edit helper/format so
  `history` is reliably appended, not hand-edited away.
- **R6 — signature-epoch scope.** F1 (§3.3.1) is a real change to `campaign_plan_signoff`
  semantics and touches existing campaigns: choosing the exact hash domain
  (scope-bearing fields only) and migrating in-flight signed plans needs care — a plan
  signed before F1 has no `signed_scope_hash` and must be treated as needing one re-sign
  (one-time migration, §7). It also surfaces a **pre-existing integrity gap** independent
  of the ledger; the author may choose to land F1 first.

## §10 Invariant-consistency self-check (for Codex round-5)

- **§1.3 / §1.7** — `customer_disposition` is Customer/data only; `delivery_status` is a
  deterministic projection from the terminal-event table; no LLM/regex disposition
  (§3.3, §3.5.1, §4.E). ✔ (verify wiring)
- **§3.4 #4 (contract immutability)** — ledger is display-only for signed scope, now with
  ENFORCED integrity (the signature epoch §3.3.1 stores a signed RESOLVED-scope snapshot —
  resolved `functional_acceptance {mode,source}` + charter_hash — so neither a literal edit
  nor a charter-inherited Acceptance flip can pass as "signed");
  closure_contract frozen; signed-scope changes route through `research_contract_revision`
  / a re-signed plan; F2+G2 conflict reporting (incl. `modified`) + stale-signoff (G4) +
  the Acceptance precedence rule block silent suppression (§3.3, §3.5, §3.6). ✔
- **Signed-scope integrity (F1)** — `campaign_plan_signoff` honored only when
  `signed_scope_hash == live hash`; edit-after-signoff ⇒ stale ⇒ re-pause; scope_report
  treats stale-signoff scope as stale-signed/blocked (NOT "unsigned"; §3.3.1). ✔
- **Delivery truth (F3+G3)** — `delivered` requires an Acceptance pass (authoritative OR
  advisory + ship signoff); every close WITHOUT an Acceptance pass — override ship,
  acceptance-OFF, out-of-scope-advance — ⇒ `waived` with a reason (§3.5.1). ✔
- **Acceptance role boundary** (`acceptance-agent.md` §9) — no ledger write; delivery
  derived (§3.5, B2). ✔
- **§3.5/§3.7 (human-confirm; fail-closed inventory)** — no new checkpoint id, no
  `campaign-decision` change; the §3.3.1 hash check tightens the EXISTING
  `campaign_plan_signoff` gate; `TestCheckpointInventoryFailClosed` stays green (B5). ✔
- **9 MANDATORY_CHECKPOINTS floor** — unchanged. ✔
- **Backward compat** — `covers_req_ids` optional; ledger absent ⇒ dormant; machine
  contracts byte-identical + `REQUIREMENT_COVERAGE=` only when ledger valid; F1 needs a
  one-time re-sign migration for pre-F1 signed plans (§7, R6). ✔ (note migration)

---

End of Requirement Ledger Design (2026-06-23) rev5.
