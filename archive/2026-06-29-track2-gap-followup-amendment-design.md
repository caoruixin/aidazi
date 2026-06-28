---
name: 2026-06-29-track2-gap-followup-amendment-design
doc_category: intermediate
status: draft-for-review-and-human-signoff
created: 2026-06-29
base_commit: main @ 297350f (post Track 3+4)
builds_on:
  - archive/2026-06-23-requirement-ledger-design.md   # approved rev5: F1 signed snapshot, covers_req_ids, delivery_status
  - archive/2026-06-29-four-area-optimization-plan.md  # Track 2 (Codex R1/R2/R3 approved-with-nits)
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
> 1. **In-envelope proof.** Every `req_id` the remediation targets ∈ the F1 signed snapshot AND was
>    already in the milestone's signed `covers_req_ids`. Any `req_id` ∉ the snapshot makes this a
>    scope EXPANSION → it MUST route through the existing scope-expansion guard
>    (`post_gate1_scope_expansion`) and HALT for a human — the auto path is forbidden.
> 2. **Bounds (all persisted, all enforced).** `gap_followup.max_subsprints` per milestone is not
>    exceeded; the gap `req_id`-set is strictly shrinking (a no-progress round — identical gap-set
>    hash for `gap_followup.max_no_progress_rounds` — forbids further auto-dispatch); the campaign
>    budget is not exhausted (an ABSENT budget is treated as a conservative cap, NEVER unbounded).
> 3. **Fail-closed escalation.** On any bound exceeded, on a no-progress stall, or on any
>    out-of-envelope or ambiguous gap, the orchestrator HALTs and escalates to `needs_human` — it
>    never silently stops and never loops.
>
> Under `autonomy.level: human_in_the_loop`, a completeness `gap_report` routes to `needs_human`
> (no auto-dispatch). The quality `fix_required → human-confirm → Deliver` path (§3.5) is
> **unchanged at every autonomy level**. This clause grants NO authority to ship, to widen scope, to
> auto-iterate on a *quality* fault, or to act on an uncalibrated *authoritative* verdict.

### A.2 What the amendment does NOT touch (preserved invariants)
- **§1.7-C quality channel** — Acceptance `fix_required` still cannot route work without human
  confirm; unchanged.
- **§1.7-D checkpoints** — no checkpoint is omitted/emptied/disabled/overridden. `scope_deviation`
  keeps its semantics; the scope-expansion guard keeps HALTing out-of-envelope work. The new path
  is an ADD (a new pre-authorized decision the charter declares in advance), not an override.
- **§3.6 calibration / ship authority** — unchanged; auto-SHIP still needs `mode:auto` + calibrated
  + `fully_autonomous_within_budget`. Gap-follow-up is about *closing the milestone's signed scope*,
  not about shipping.
- **LOAD-CLOSURE** — the `gap_report` and every artifact it is computed from are bound into
  `_acceptance_resolver_graph` + `acceptance_input_hash`.

### A.3 Validator surface for the amendment (so it is enforceable, not just prose)
`charter_validator.py` gains checks mirroring the four §1.7-D evasion shapes for the new path:
`gap_followup` must be bounded (no unbounded `max_subsprints`/no-progress/budget), must not be used
to widen scope, and must not be present in a way that disables the quality `fix_required`
human-confirm. A charter that sets an unbounded `gap_followup` is rejected exactly like
`invalid-adaptive-insert-unbounded.yaml` is today.

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
**static** `acceptance-verdict.schema.json` (today only browser-E2E carries `criterion_id`); bind
the checklist + ledger + delivered-status into `_acceptance_resolver_graph` + `acceptance_input_hash`
(LOAD-CLOSURE); have Acceptance EMIT the `gap_report` as an advisory artifact. Still NO auto-routing —
the gap report is produced and surfaced, nothing acts on it automatically yet. Add the Track-2
runtime size cap/report for these dynamic acceptance artifacts (invariant #1.5, R3 NB-2).

**Phase 2-γ — GATED: the §1.7-F amendment + the auto-routing engine path.**
ONLY after §A is human+Codex signed: implement the bounded, in-envelope, autonomy-aware
Acceptance→Deliver auto-dispatch (the `gap_followup` bounds, the in-envelope proof reusing the
scope-expansion guard, the `needs_human` escalation, the `human_in_the_loop` routing, and the
`adjust_scope` decision shape on `campaign-decision.schema.json`). Wire `adaptive_insert`/the new
`gap_followup` knob in the charter. Each step Codex-reviewed; the suite + kernel + load-closure +
`--strict` budget gates green.

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
