---
name: 2026-06-29-track2-gap-followup-amendment-design
doc_category: intermediate
status: codex-revise-incorporated-pending-human-signoff
created: 2026-06-29
base_commit: main @ 297350f (post Track 3+4)
builds_on:
  - archive/2026-06-23-requirement-ledger-design.md   # approved rev5: F1 signed snapshot, covers_req_ids, delivery_status
  - archive/2026-06-29-four-area-optimization-plan.md  # Track 2 (Codex R1/R2/R3 approved-with-nits)
reviewer: codex gpt-5.5 xhigh — R-T2 VERDICT REVISE (4 blocking + 3 nits + 2 factual), all incorporated 2026-06-29 (tagged `Codex R-T2 B#/NB#/factual#`)
gate: REQUIRES human + Codex sign-off on the Constitution/delivery-loop amendment (§A) BEFORE any auto-routing code lands
---

# Track 2 — Gap-driven Acceptance→Deliver follow-up: Constitution amendment + build sequence

This is the "advance to the human gate" deliverable for Track 2. It does NOT change code. It (A)
drafts the Constitution / `delivery-loop.md` **authority amendment** that the locked Track-2 decision
requires, and (B) gives the ordered build sequence separating the *additive backbone* (buildable
without the amendment) from the *gated auto-routing* (blocked on the amendment's sign-off).

**Why an amendment is unavoidable.** The locked decision wants, under `human_on_the_loop`, Acceptance
to emit a completeness `gap_report` and have Deliver **automatically** start a remediation sub-sprint
with **no pause**. But today:
- **§1.7-C** (`constitution.md:181,185`): an Acceptance verdict is advisory and "**cannot ship the
  milestone or route work without human authority**"; the `fix_required → Deliver` path "MUST NOT
  skip the human-confirm checkpoint."
- **§3.5** (`constitution.md:362-388`): `fix_required → human-confirm → Deliver` exists precisely so
  "Acceptance [cannot] route work back to Deliver indefinitely; with it, Customer keeps loop authority."
- **§1.7-D** (`constitution.md:187-204`): the 9 MANDATORY_CHECKPOINTS may not be bypassed
  (omit/empty/disable/**override**), and "override" explicitly includes redefining a checkpoint to
  auto-approve below a threshold.

So a no-pause auto-route is, under the current text, a §1.7-C breach. The amendment must legalize a
**narrow** new path WITHOUT weakening any of the above.

---

## §A The amendment (for human + Codex sign-off)

**Design key:** the amendment is *consistent with the existing pre-authorization doctrine*, not a
weakening of it. §1.7-D's own rationale (`constitution.md:202`) is: "the whole point of charter
pre-authorization is that the human knows IN ADVANCE which decisions the orchestrator can make
autonomously and which require human approval." The amendment names ONE more such pre-authorized
decision — *completing already-signed, undelivered scope* — and bounds it.

### A.1 New clause `§1.7-F` — Pre-authorized in-envelope completeness remediation

> **§1.7-F Pre-authorized in-envelope completeness remediation (gap-driven follow-up).**
> Distinct from the quality `fix_required` channel (§1.7-C/§3.5, UNCHANGED), Acceptance MAY emit a
> **completeness `gap_report`**: the set of requirement ids that are part of the **human-signed
> requirement envelope** (the F1 signed resolved-scope snapshot, `archive/2026-06-23-requirement-
> ledger-design.md` §3.3.1) AND were signed into this milestone's `covers_req_ids` AND are not yet
> delivered. A gap is **in-envelope scope completion**, never scope expansion.
>
> Under `autonomy.level: human_on_the_loop` (or higher), the orchestrator MAY, WITHOUT a fresh
> human-confirm checkpoint, dispatch a **bounded remediation sub-sprint** to Deliver to close an
> in-envelope gap, IFF ALL of the following hold (deterministic, validator-checkable):
> 0. **Quality channel is clean (completeness↔quality SEAL — Codex R-T2 B1).** The milestone's
>    Acceptance verdict carries NO `fix_required` and NO `needs_human` (those are *quality* faults
>    keeping their §1.7-C/§3.5 human-confirm semantics, untouched). A milestone with ANY quality
>    fault is INELIGIBLE for no-confirm gap-followup — it routes to human-confirm exactly as today
>    (`schemas/acceptance-verdict.schema.json:78,111`). Gap-followup entries are generated **only
>    from coverage/ledger facts** (the derived `delivery_status` of signed `covers_req_ids`), NEVER
>    from Acceptance-authored failure semantics (`positive_shape`/`anti_pattern` clause judgments).
>    Completeness ≠ quality, sealed by the SOURCE of the entries.
> 1. **In-envelope proof on the GENERATED remediation (Codex R-T2 B2 + factual-1).** The generated
>    remediation sub-sprint stanza MUST carry an explicit `covered_req_ids[]` field — NEW on
>    `schemas/sprint_stanza.schema.json` / `deliver-plan-*.schema.json`, which have NONE today
>    (`deliver-plan-verdict.schema.json:16`, `deliver-plan-fix.schema.json:7`, `sprint_stanza.schema.json:7`)
>    — and a NEW deterministic **req_id-envelope check** must prove
>    `covered_req_ids ⊆ (F1 signed snapshot ∩ this milestone's signed covers_req_ids)`. This is a
>    DISTINCT check from `post_gate1_scope_expansion`, which validates only modules/layers
>    (`delivery-loop.md:395`, `driver.py:2285`) and would NOT catch same-module new scope. Any
>    `covered_req_id` ∉ the envelope, or a remediation introducing behavior not traceable to an
>    in-envelope `req_id`, fails → HALT for a human; the auto path is forbidden.
> 2. **Bounds (persisted, enforced at RUNTIME — Codex R-T2 B3 + factual-2).** Enforced by NEW runtime
>    logic, not static charter validation alone: `gap_followup.max_subsprints` per milestone
>    (persisted counter); the remaining gap `req_id`-set is **strictly shrinking = a PROPER SUBSET**
>    of the prior round's set (persisted gap-set history; proper-subset, NOT identical-hash, which
>    misses A/B churn — R-T2 NB-2); and the campaign budget is not exhausted. NOTE: today an ABSENT
>    campaign-budget dimension is **unbounded** at runtime (`campaign-plan.schema.json:17`,
>    `campaign.py:644` loads absent as `{}`), so this clause requires NEW runtime "effective-cap"
>    logic imposing a conservative default cap on the gap-followup dimension when budget is absent —
>    it does NOT inherit today's unbounded default.
> 3. **Fail-closed escalation.** On any bound exceeded, on a non-shrinking (non-proper-subset) round,
>    or on any out-of-envelope or ambiguous gap, the orchestrator HALTs and escalates to
>    `needs_human` — it never silently stops and never loops.
>
> Under `autonomy.level: human_in_the_loop`, a completeness `gap_report` routes to `needs_human`
> (no auto-dispatch). The quality `fix_required → human-confirm → Deliver` path (§3.5) is
> **unchanged at every autonomy level**. This clause grants NO authority to ship, to widen scope, to
> auto-iterate on a *quality* fault, or to act on an uncalibrated *authoritative* verdict.

### A.2 What the amendment does NOT touch (preserved invariants)
- **§1.7-C quality channel** — Acceptance `fix_required`/`needs_human` still cannot route work
  without human confirm; unchanged, and is now the eligibility SEAL (clause 0 above).
- **§1.7-D checkpoints** — no checkpoint is omitted/emptied/disabled/overridden. `scope_deviation`
  and `post_gate1_scope_expansion` keep their semantics; out-of-envelope work still HALTs (now via
  the NEW req_id-envelope check, clause 1, which is ADDITIVE — it does not redefine the existing
  module/layer guard). The new path is an ADD (a pre-authorized decision the charter declares in
  advance), not an override.
- **§3.4 diagram invariant — MUST be updated if §1.7-F lands (Codex R-T2 NB-3).** `constitution.md:325`
  states "Acceptance never silently routes to Deliver (§1.7-C)." Amend it to name the §1.7-F
  exception explicitly and as bounded: "...except the §1.7-F pre-authorized, in-envelope, bounded
  completeness-remediation path, which is neither silent (audited) nor quality-routing." Otherwise
  §3.4 would contradict §1.7-F.
- **§3.6 calibration / ship authority** — unchanged; auto-SHIP still needs `mode:auto` + calibrated
  + `fully_autonomous_within_budget`. Gap-follow-up is about *closing the milestone's signed scope*,
  not about shipping.
- **LOAD-CLOSURE (expanded per Codex R-T2 B4)** — the `gap_report` is verdict-affecting and is
  computed from `ledger × signed plan × campaign state/outcomes`
  (`archive/2026-06-23-requirement-ledger-design.md:442`). Bind the FULL set into
  `_acceptance_resolver_graph` + `acceptance_input_hash`: the signed plan / F1 envelope snapshot, the
  live campaign state INCLUDING per-milestone outcomes, the generated scope / gap report, AND the
  functional-checklist / criteria source — not just "checklist + ledger + delivered-status".

### A.3 Enforcement surface (so it is enforceable, not just prose — Codex R-T2 B3)
Enforcement is TWO-LAYER, not charter-validation-only:
- **Static (`charter_validator.py`)** — mirrors the four §1.7-D evasion shapes for the new path:
  `gap_followup` must be bounded (no unbounded `max_subsprints`/no-progress); must not widen scope;
  must not disable the quality `fix_required` human-confirm. An unbounded `gap_followup` is rejected
  exactly like `invalid-adaptive-insert-unbounded.yaml` today. (Static alone is INSUFFICIENT —)
- **Runtime (`campaign.py` / `driver.py`)** — NEW persisted state + checks: a per-milestone
  gap-followup counter, the gap `req_id`-set history (for the proper-subset progress check), and the
  **effective-cap** logic that supplies a conservative default when the campaign budget dimension is
  ABSENT (today absent ⇒ unbounded, `campaign.py:644`). The req_id-envelope check (clause 1) and the
  completeness↔quality seal (clause 0) are runtime gates, fail-closed to `needs_human`.

---

## §B Build sequence (additive backbone first; gated auto-routing last)

**Phase 2-α — Requirement Ledger backbone (NO amendment needed; additive; mergeable on its own).**
Implement `archive/2026-06-23-requirement-ledger-design.md` rev5: `covers_req_ids[]` on
`campaign-plan.schema.json`, the F1 signed resolved-scope snapshot + staleness check into
`campaign_plan_signoff`, and the requirement-granular `scope_report.py` (REQ→milestone→
delivery_status). This is read/projection + sign-off integrity only; it changes NO ship/route
authority. Gate on `context_budget_report.py --strict` (these are runtime/per-milestone inputs, not
cold-start — invariant #1.3/#1.5).

**Phase 2-β — Static functional checklist + gap_report production (NO amendment needed).**
Generalize `functional-checklist.schema.json` to the static path; add per-criterion coverage to the
**static** `acceptance-verdict.schema.json` (today only browser-E2E carries `criterion_id`); bind the
FULL LOAD-CLOSURE set (per §A.2 / R-T2 B4) — signed plan + F1 envelope snapshot + live campaign state
incl. per-milestone outcomes + the generated gap report + the functional-checklist/criteria source —
into `_acceptance_resolver_graph` + `acceptance_input_hash`; have Acceptance EMIT the `gap_report`
(from coverage/ledger facts only, clause 0) as an advisory artifact. Still NO auto-routing — the gap
report is produced and surfaced, nothing acts on it automatically yet. Add the Track-2 runtime size
cap/report for these dynamic acceptance artifacts (invariant #1.5, R3 NB-2).

**Phase 2-γ — GATED: the §1.7-F amendment + the auto-routing engine path.**
ONLY after §A is human+Codex signed: implement the bounded, in-envelope, autonomy-aware
Acceptance→Deliver auto-dispatch, namely (per the hardened §A.1 clauses 0–3): the completeness↔
quality **seal** (clause 0); the NEW `covered_req_ids[]` stanza field on
`sprint_stanza`/`deliver-plan-*` + the NEW deterministic **req_id-envelope check** (clause 1; NOT the
module/layer `post_gate1_scope_expansion` guard, which does not see req_ids); the RUNTIME bounds +
proper-subset progress check + absent-budget **effective-cap** (clause 2); the fail-closed
`needs_human` escalation (clause 3); the `human_in_the_loop` routing; the `adjust_scope` decision
shape on `campaign-decision.schema.json`; the two-layer enforcement (§A.3); and the §3.4 diagram-
invariant text update. Each step Codex-reviewed; suite + kernel + load-closure + `--strict` budget
gates green.

**Phase 2-δ — OPEN (separate decision): M3 fail-closed (P2.4) + end-user persona shape (P2.3).**
Not required for the gap-driven loop; carry as independent follow-ups.

---

## §C Human gate (for the end-of-run batch)
1. **Approve the §1.7-F amendment** (text in §A) — its own Codex+human sign-off, per the plan.
   Until approved, Phase 2-γ does NOT start; Phases 2-α/2-β are buildable independently.
2. **Confirm the bounds defaults** — `gap_followup.max_subsprints` (proposed: 3),
   `max_no_progress_rounds` (proposed: 2), absent-budget conservative cap (proposed: tie to
   `budget.max_fix_rounds_total`).
3. **Confirm scope** — bind completeness to the ledger `covers_req_ids` (finer) as already chosen.
