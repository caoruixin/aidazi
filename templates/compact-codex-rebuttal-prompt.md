---
title: Compact Codex rebuttal prompt — template
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
  Formalizes a Deliver-side practice: when the Code Reviewer (Codex or
  similar) returns fix_required findings that BROADEN scope beyond the
  sub-sprint contract, Deliver pushes back with a targeted re-review rather
  than expanding the sub-sprint. The reviewer is then asked to re-judge with
  the scope reminder + the specific contested findings.
---

# Compact Codex rebuttal prompt — instance template

Use this template when the Code Reviewer Agent has returned a `fix_required` verdict whose findings broaden scope beyond the current sub-sprint's contract. Instead of folding those findings into the current sub-sprint (which violates the sub-sprint scope discipline and trips `scope_envelope_check`), Deliver authors a rebuttal asking the reviewer to re-judge with explicit scope reminders.

The pattern is intentionally bounded — rebuttals are NOT a way for Deliver to silence the reviewer; they are a way to align the reviewer with the sub-sprint contract Deliver authored.

---

## When to use

- Code Reviewer's verdict = `fix_required`.
- One or more findings reference modules / behaviors OUTSIDE `charter.approved_scope.modules_in_scope` OR outside the sub-sprint's declared `scope_in`.
- The findings, taken individually, may be valid — but addressing them in this sub-sprint expands scope beyond what was approved.

**Do NOT use** when:
- The findings are inside scope but Deliver disagrees with severity. (That's a normal close conversation; not a rebuttal.)
- The findings hit a §1.7 forbidden item. (Forbidden patterns are P0; Deliver cannot rebut their way out of §1.7.)
- The reviewer's verdict was `out_of_scope_review`. (That verdict already says the reviewer couldn't meaningfully judge; re-author the review prompt instead.)

## Instance front-matter (REQUIRED)

```yaml
---
title: Codex rebuttal — <sprint-id> finding-<id>
context_budget:
  target_tokens: 6000
  load_list:
    - aidazi/governance/constitution.md
    - aidazi/templates/anti-hardcode-review-kernel.md
    - aidazi/schemas/compact/review-verdict.compact.schema.json   # agent loads the compact projection (verbose canonical = validator's)
    - <adopter>/docs/sprint_objective.md          # sub-sprint contract
    - <adopter>/docs/codex-findings.md            # prior verdict being contested
    - <adopter>/charter.yaml                       # approved_scope
  do_not_load:
    - <adopter>/case_specs_shadow/*
  self_contained: true
sprint_id: <sprint-id>
contested_findings: [<finding-id-1>, <finding-id-2>]
---
```

## Instance body (template)

```
You previously authored docs/codex-findings.md for <sprint-id> with verdict
fix_required and findings <list>. Deliver is requesting a re-review of
finding(s) <contested-id list> with the following scope reminders:

SUB-SPRINT CONTRACT (the scope you are judging against):

<paste docs/sprint_objective.md scope_in section verbatim>

CHARTER APPROVED SCOPE (the wider scope NOT to be expanded mid-sprint):

  modules_in_scope:
    <list from charter.yaml>
  layers_allowed:
    <list from charter.yaml>
  explicitly_out_of_scope:
    <list from charter.yaml>

CONTESTED FINDINGS:

For each finding id in <contested-id list>:
  - Re-read the finding.
  - Determine: is the finding INSIDE the sub-sprint's scope_in OR strictly
    inside the modules+layers approved for this sub-sprint?
  - If YES: finding stays; Deliver acknowledges and will fix.
  - If NO: reclassify the finding:
      • If the finding identifies a load-bearing issue that should be a
        future sub-sprint, route as a new R-item suggestion in the verdict's
        rationale field (NOT a current-sprint blocker).
      • If the finding is a §1.7 forbidden-list breach, finding STAYS as P0
        regardless of scope — forbidden patterns cannot be rebutted.
      • If the finding is a diagnostic-grade observation (mid-flight
        tech-internal note), suggest filing as docs/diagnostics/<id>.md.

PRODUCE: an updated codex-findings.md verdict per
schemas/review-verdict.schema.json with:
  - Original verdict updated (potentially: fix_required → pass IF all
    in-scope findings actually pass AND out-of-scope findings have been
    reclassified).
  - For each reclassified finding: rationale field cites the scope reminder
    that triggered reclassification.
  - DO NOT silently delete findings. Reclassification is in the rationale;
    the finding record is preserved.

CONSTRAINTS:
- §1.7 forbidden-list findings cannot be reclassified out (Constitution §1.7).
- This rebuttal does NOT authorize you to widen scope to absorb the contested
  findings; it asks you to recognize the contested findings ARE out-of-scope.
- If you cannot determine scope from the materials provided, return
  out_of_scope_review and ask for a clearer scope statement.
```

## Pattern notes

- This is an ad-hoc Deliver tool, not a standing process. Most sub-sprints close cleanly without rebuttal.
- The rebuttal is recorded in the close conversation; the original fix_required verdict + the rebuttal exchange both live in `docs/codex-findings.md` history.
- If a reviewer disagrees with the scope reminder AND insists the findings are in-scope, route to Deliver close verdict C (scope-broadening) and let `close_taxonomy_C_or_D` MANDATORY_CHECKPOINT fire — Customer adjudicates.
- The pattern exists to preserve sub-sprint scope discipline (per `process/milestone-framework.md`), NOT to give Deliver a way to override the reviewer on substance.

## Template usage notes

- This template is OPTIONAL. Adopters may skip it and resolve scope disagreement via Deliver close conversation alone. The template just makes a repeated practice explicit.
- The `target_tokens: 6000` is suggested per Constitution §7.0.
- Constitution §1.7 forbidden items are NOT rebuttable — the template body says so explicitly. A Deliver Agent who rebuts a §1.7 finding into oblivion has framework-breached.

---

End of codex rebuttal prompt template.
