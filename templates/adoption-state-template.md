---
title: Adoption state ledger — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
load_discipline: by-role
size_target: 6KB
notes: >
  Template for <adopter>/docs/current/adoption-state.md. Per-Δ status table +
  drift rationale + lessons-proposed. Per Constitution §1.8: Δ rows targeting
  Constitution §1.7 cannot have status: divergent (hard requirement; not
  overridable). Schema: schemas/adoption-state.schema.json.
---

# Adoption state ledger — instance template

Copy this template to `<adopter>/docs/current/adoption-state.md` and replace `<placeholders>`. Schema: `aidazi/schemas/adoption-state.schema.json`.

This is the adopter's running record of which framework defaults are at-spec, partial, divergent (with rationale), not-applicable, or superseded-by-framework. Loaded at every cold-start session (per `aidazi/governance/context_briefing.md` §5) before process docs, so role agents apply adopter overrides instead of framework defaults.

---

```markdown
---
title: <adopter-name> Adoption State vs aidazi framework
adopter_name: <name>
framework_version: v4.0.0
last_reviewed: <YYYY-MM-DD>
review_cadence: per milestone close
track: type_a | type_b | type_c | type_a_b_hybrid
---

# Per-Δ status

| Δ | v4 spec tier | Adopter status | Gap notes | Plan |
|---|---|---|---|---|
| Δ-1 Anatomy | T0 | at-spec | — | — |
| Δ-2 Domain discovery | T0 | at-spec | — | — |
| Δ-3 Decision catalog | T0 | partial | uses 6 of 8 decisions; #5 memory + #7 policy not yet decided | next milestone |
| Δ-4 Doc lifecycle | T0 | at-spec | — | — |
| Δ-5 Context-passing efficiency | T0 (also §1.4-i) | at-spec | — | — |
| Δ-6 Type A runtime skeleton | T1 (Type A) | <status> | — | — |
| Δ-7 Worked example | T1 | not-applicable | no example consumer yet | — |
| Δ-9 OBS triage | T0 | <status> | — | — |
| Δ-10 Doc-responsibility matrix | T0 | <status> | — | — |
| Δ-11 Capability staging | T0 | <status> | — | — |
| Δ-12 Artifact taxonomy (14) | T0 | <status> | — | — |
| Δ-13 Stage-stable heuristic | T0 | <status> | — | — |
| Δ-14 Profile-aware maturity | T0 | at-spec | — | — |
| Δ-15 Agent design elicitation | T0 | <status> | — | — |
| Δ-16 Agent creation prereqs | T0 | <status> | — | — |
| Δ-17 Common detours | T1 | <status> | — | — |
| Δ-18 Delivery Loop | T1 (Type A) | <status> | — | — |

# Drift reasons (for `divergent` rows)

(Each divergent row above MUST have a corresponding entry here. Rationale is the
"why"; the per-Δ table cell is the "what". Per Constitution §1.8: divergent
rows against §1.7 of constitution are NOT permitted — those are framework
breaches, not overrides.)

- Δ-N: <rationale paragraph>

# Lessons proposed for upstream fold-back

| Date | Topic | Lesson file | Status |
|---|---|---|---|
| <YYYY-MM-DD> | <short topic> | aidazi/lessons/<date>-<topic>.md | proposed |
```

## Status enum

- `at-spec` — adopter follows the framework default as written.
- `partial` — adopter has implemented some sub-parts; not all.
- `divergent` — adopter has overridden the framework default. **Rationale REQUIRED.**
- `not-applicable` — this Δ doesn't apply to this adopter's track.
- `superseded-by-framework` — adopter was at-spec at an older framework version; framework has since evolved. Consume new version next cadence.

## Hard-requirement check (Constitution §1.8)

Per Constitution §7.0 / §1.8, the following CANNOT have `status: divergent`:

- Constitution §1.7 forbidden list (core 5 + v4 additions §1.7-A through §1.7-E).
- Constitution §3.4 5-role boundary invariants.
- `process/delivery-loop.md` §4.2.3 8 MANDATORY_CHECKPOINTS.
- Constitution §3.6 Acceptance judge calibration gate (when running fully autonomous).

If you find yourself wanting to mark one of these `divergent`, halt: that's a framework breach, not an adopter override. Either restore conformance OR file a lesson explaining why the framework default is wrong for your context (lessons fold back to v5 evaluation).

Suggested defaults (size targets, calibration thresholds, cadence triggers, prompt context_budget values, etc.) ARE override-able — those go in this ledger normally.

## Override procedure (Constitution §7.2)

1. Mark the Δ row's `Adopter status: divergent` AND write a rationale below.
2. Continue using the divergent value; no framework rejection.
3. At fold-back cadence, framework maintainer reviews divergences:
   - Many same-direction divergences = default is wrong; revised in next framework release.
   - Idiosyncratic divergences = stay adopter-specific.

## Cadence

`review_cadence: per milestone close` is the suggested default (per `process/fold-back-protocol.md` §4.3). At each cadence review:

- Walk the per-Δ table; update rows whose status changed.
- Append new lessons to the lessons table.
- Verify Constitution §1.7 immutability (no divergent rows targeting §1.7).

## Template usage notes

- The template's example status values (`partial`, `at-spec`, etc.) are illustrative — replace with your actual state.
- The `<placeholders>` should all be removed in the instance.
- Validate the instance against `schemas/adoption-state.schema.json` (tooling-side; checks divergent rows have rationale).
- This file is `load_discipline: always-load` for cold-start sessions effectively — every agent loads it after the always-load governance triple per `context_briefing.md` §1. Keep it concise.

---

End of adoption-state template.
