---
title: Bad-case suite lifecycle
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 12KB
split_trigger: if §3 tiering / §5 lifecycle rules grow past 6KB, split into a dedicated lifecycle doc
notes: >
  Promoted from csagent docs/current/process/badcase-lifecycle.md (csagent §5.6
  + dated portions of §5.5) per v4 build plan. v4 framing: references
  Constitution §1.6 (eval rule) + §1.7-B (closure_criterion shape).
  Defines the curated bad-case suite as the primary acceptance gate +
  bad-case lifecycle (active / scope-relevant / closed-as-regression-guard
  / archived). The smoke composite_score demotion rule (csagent §5.5) is
  collapsed into Constitution §1.6's eval-evidence-not-authority principle.
---

# Bad-case suite lifecycle

The curated bad-case suite is the primary acceptance gate for the framework — the load-bearing observable behavior the team commits to NOT regressing on. This doc defines its lifecycle: how cases enter, get tiered, get reviewed, and exit (or downgrade to regression-guard).

The suite operationalizes Constitution §1.6 (eval is evidence, not authority) — bad-case manual review is the human-judgment surface that backstops programmatic scores.

## §1 The suite as primary acceptance gate

The bad-case suite is a Deliver + Customer curated directory of CaseSpecs (per `schemas/case-spec.schema.json`) derived from:
- Real user / colleague / human sessions that surfaced a multi-layer failure.
- Architectural findings from sub-sprints.
- Production-readiness regression candidates the Customer flags as load-bearing for the release gate.

### §1.1 CaseSpec carrying

Each bad-case CaseSpec carries the standard `schemas/case-spec.schema.json` fields PLUS a `bad_case_metadata` block:

```yaml
bad_case_metadata:
  source_session_id: <id>                 # original real session that surfaced it
  surfaced_by: <human-or-sprint-id>
  surfaced_date: <YYYY-MM-DD>
  failure_shape: <one-line description>
  expected_behavior: <human-verified; NOT bot trace text>
  tier: core | scope-relevant | closed-as-regression-guard | archived
```

The `closure_criterion` field (per `schemas/case-spec.schema.json` + Constitution §1.7-B) names the Deliver + Customer-verified condition under which this bad case is "resolved" — expressed in the 3-component shape (positive shape + anti-pattern + anchor phrases).

## §2 Manual review process at close

At sub-sprint OR milestone close (per `process/milestone-framework.md` §2):

1. Run the bad-case suite (scope-relevant subset per §3 below).
2. Deliver + Customer read per-case traces.
3. For each bad case, Customer (with Deliver's assistance) judges PASS / FAIL / IMPROVING **qualitatively** against the `closure_criterion`. This is a **human-judgment gate**, not a programmatic gate.
4. Programmatic scores (composite_score, pass-rate aggregates) are inputs, NOT decisions, per Constitution §1.6.

### §2.1 Close decision

Sub-sprint or milestone close decision is made by Customer (with Deliver's recommendation) based on per-case manual review results PLUS other Constitution §1.6 hard gates (Code Reviewer anti-hardcode, runtime tests, safety floor, grounding floor).

A FAIL on a bad case does NOT auto-block close; it triggers a Deliver + Customer conversation about whether the failure is in-scope for the closing milestone OR surfaces a new R-item. See `templates/deliver-close-taxonomy.md` for classification.

### §2.2 MANDATORY_CHECKPOINT

When the Δ-18 orchestrator is adopted, manual review of bad cases fires the `bad_case_manual_review` MANDATORY_CHECKPOINT at milestone close (per `process/delivery-loop.md` §4.2.3 item 3). Customer cannot skip this checkpoint per Constitution §1.7-D non-bypass invariant.

## §3 Bad-case tiering

Bad cases carry a `tier` field in `bad_case_metadata`:

- **`core`** — load-bearing across all milestones (touches release-gate-relevant failure mode). Re-run at every milestone close.
- **`scope-relevant`** — relevant to a specific architectural surface that some milestones touch. Re-run only at milestone closes where milestone explicitly names this bad case in acceptance bar.
- **`closed-as-regression-guard`** — met closure criterion in N ≥ 2 consecutive milestone closes (see §5 downgrade rule). Stays in suite; runs automatically; if re-fails, auto-promotes back to active. No human manual review required while in this state unless auto-detection fires.
- **`archived`** — underlying failure surface has been structurally removed; case can no longer manifest. Removed from active runs but kept in directory as history. Requires Deliver + Customer joint decision in `eval/bad_cases/_manifest.md` lifecycle ledger.

The N ≥ 2 threshold for downgrade is a suggested default per Constitution §7.0; adopters with stricter regression posture may require N ≥ 3 or higher.

## §4 Per-milestone bad-case selection

At milestone planning, Deliver picks which bad cases the closing milestone is expected to address:

- `core` cases: always run at close (no opt-out at milestone planning).
- `scope-relevant` cases: named in `milestone_objective.md` acceptance bar if milestone's scope touches relevant surface. Deliver SHALL list named cases verbatim.
- `closed-as-regression-guard` cases: run automatically; no scope decision required.

A bad case the closing milestone does NOT touch is NOT re-run at that close (saves manual review time). Deliver + Customer revisit at next planning round.

## §5 Bad case lifecycle

```
Opened   — real session OR sprint-derived finding surfaces a failure;
           Deliver + Customer agree it's load-bearing.
   ↓
Active   — failure persists. Each milestone close records per-case status
           (PASS / FAIL / IMPROVING).
   ↓
Closed   — failure no longer manifests on milestone rerun AND Deliver +
           Customer jointly confirm at milestone close. Closed bad cases
           stay in directory as regression guards (tier:
           closed-as-regression-guard).
```

### §5.1 Downgrade rule (active → closed-as-regression-guard)

A bad case downgrades when:
- Case has been judged PASS (per §2 manual review) by Customer in **N ≥ 2 consecutive milestone closes**.
- Deliver + Customer jointly agree at milestone close to apply downgrade (planning-round decision, not automatic on N=2 trigger).

Downgraded cases stay in suite as regression guards. They run automatically; auto-detection of FAIL re-promotes them to `active` and triggers Deliver attention.

### §5.2 Archive rule (closed-as-regression-guard → archived)

A case never automatically removes itself from suite. `archived` requires explicit Deliver + Customer joint decision documented in `eval/bad_cases/_manifest.md`.

Archive is rare; the right call only when failure surface is structurally removed.

## §6 Joint authoring (Constitution §5 state ledgers)

Per Constitution §5 state-ledgers table, bad-case `closure_criterion` is **joint authoring**:
- Deliver Agent curates structure (CaseSpec schema fields; bad_case_metadata).
- Human (Customer or designated domain expert) authors `closure_criterion` paragraph in the 3-component shape (positive shape + anti-pattern + anchor phrases).

This is per Constitution §1.7-B — `closure_criterion` MUST be a human-judgment paragraph, NOT a keyword / regex matcher. The Code Reviewer Agent (anti-hardcode kernel) and Acceptance Agent both cite anchor phrases as evidence, not gates.

## §7 Suite manifest

`eval/bad_cases/_manifest.md` is the lifecycle ledger. It carries:
- Per-case row: case_id, tier, surfaced_date, last_status, last_status_date, lifecycle_history.
- Manifest-level overrides (e.g., tier change applied at specific milestone close).
- `archived` lifecycle decisions with joint Deliver + Customer rationale.

The manifest format (markdown vs yaml) is suggested per Constitution §7.0; adopters choose.

## §8 Eval contamination rule (Constitution §10)

The bad-case suite directory MUST NOT be read by the Dev sandbox if there is a corresponding holdout (`case_specs_shadow/` or equivalent). Per Constitution §10 anti-pattern: "Giving Dev sandbox read access to `case_specs_shadow/` (or equivalent holdout eval set) — eval contamination."

The Dev Agent's `do_not_load` list in compact prompts must include the holdout path. The orchestrator's F5 evidence run reads bad cases; Acceptance reads them via the orchestrator's artifact paths.

## §9 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The tier names (`core` / `scope-relevant` / `closed-as-regression-guard` / `archived`) are stable framework vocabulary; adopters MAY add tier names with rationale in `adoption-state.md` but SHOULD NOT rename the defaults — Code Reviewer prompts + Acceptance prompts may reference the names directly.

---

End of Bad-case lifecycle.
