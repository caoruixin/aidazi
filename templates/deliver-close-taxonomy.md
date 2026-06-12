---
title: Deliver close taxonomy
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
load_discipline: by-role
size_target: 12KB
notes: >
  Sprint / milestone close decision classifications for the Deliver Agent.
  Promoted from csagent docs/current/deliver_close_taxonomy.md (v3.2 missed
  this artifact; v4 makes it a first-class template). Per-blocker
  classification → NET recommendation = union.
---

# Deliver close taxonomy

When the Code Reviewer Agent returns a verdict at close, the Deliver Agent + Customer classify **EACH blocker** individually, then compute a NET recommendation (= union of per-blocker actions).

DO NOT force a single classification on the whole sprint; multi-blocker reviews mix classifications and the NET is the union (see Mixed pattern below).

This template is consumed by the Deliver Agent at close conversation (per `role-cards/deliver-agent.md` §3.5) and by the orchestrator's `spawn_deliver_close` function. The output classification flows into the deliver-close-verdict per `schemas/deliver-close-verdict.schema.json` (verdict `A` / `B` / `C` / `D` + subclass).

## Primary classifications (A / B / C / D)

### A — Clean close

Code Reviewer verdict: `decision: pass, blocking_count: 0`.

**Resolution**: archive codex-findings → `docs/sprints/<sprint-id>-codex-review.md`. Advance to next sub-sprint or milestone close.

### A-with-packaging-note

Code Reviewer verdict: `decision: out_of_scope_review`; blocker is **path-based** (Deliver-agent files were bundled into Dev commit; substantive findings already closed).

**Resolution**: roll forward with packaging note in close handoff §12. No re-review required.

**Close handoff §12 MUST include**: substantive verdict + packaging artifact note + roll-forward statement.

### A-with-Codex-skipped

Sprint scoped as potentially-semantic-touching, but Dev outcome is **docs-only** (zero semantic-touching edits). Customer invokes `templates/anti-hardcode-review-kernel.md` exemption clause to skip the Code Reviewer.

**Resolution**: do NOT generate `<sprint-id>-codex-review.md`. Close handoff §12 MUST record skip decision + exemption citation + date.

**Distinct from open-time planned skip**: this classification is close-time human discretion; an open-time planned skip would have been declared in the dev prompt.

### A-with-evidence-gap-acknowledgment

Code Reviewer verdict: `decision: fix_required`; blocker is **typographical-only** (markdown / punctuation delta); Code Reviewer's own non-blocking checks confirm substance is sound.

**Resolution**: Customer accepts the typographical gap; close over `fix_required`. Close handoff §12 cites the Code Reviewer's non-blocking-check evidence.

**NOT B**: B is substantive content error requiring fix iteration. This classification's blocker does not change the evidence package's substance.

### B — Substantive blocker, targeted fix iteration

Code Reviewer's blocker is **content-substantive** (wrong claim, missing evidence, behavior drift). Dev fix iteration required.

**Resolution**: Deliver spawns `spawn_deliver_plan_fix` (per `process/delivery-loop.md` §4.2.7) producing a new sub-sprint scoped to the fix. Re-enter `dev_pending` state. Bound by `charter.auto_pass_rules.auto_fix_iteration.max_rounds`.

### B-resolved-without-re-review

B's fix scope is **mechanical + verifiable** (e.g., adding a missing command line), and the Code Reviewer's substantive verdict is already approve.

**Conditions** (all four required):
1. Anti-hardcode kernel + verification-notes both approve.
2. Fix is verifiable by command.
3. Fix only touches the artifact the Code Reviewer flagged.
4. Fix produces no new evidence.

**Resolution**: Customer self-verifies; no Code Reviewer re-review. Close handoff §12 records self-verification rationale + verifying command + verified result.

### C — Code Reviewer broadens scope

Code Reviewer's finding is outside the current sub-sprint / milestone scope.

**Resolution**: do NOT have Dev fix; either:
- (a) Issue a Codex rebuttal (per `templates/compact-codex-rebuttal-prompt.md`) asking the Code Reviewer to re-judge with explicit scope reminders.
- (b) Move the items to `docs/action_bank.md` as deferred R-items (next sub-sprint or next milestone).

C MUST trigger the `close_taxonomy_C_or_D` MANDATORY_CHECKPOINT per `process/delivery-loop.md` §4.2.3 item 7 — Customer resolves the scope-broadening question.

### D — Non-convergence

Multiple fix rounds did not converge (`charter.auto_pass_rules.auto_fix_iteration.max_rounds` exceeded OR Customer's qualitative judgment).

**Resolution**: stop automation; `close_taxonomy_C_or_D` MANDATORY_CHECKPOINT fires (per `process/delivery-loop.md` §4.2.3 item 7). Customer resolves: abort milestone / re-scope / route to Research for closure_contract revision.

D is also the verdict when finding severity escalates past `auto_pass_rules.auto_fix_iteration.only_if_findings_severity_at_most` (`process/delivery-loop.md` §4.4).

## Special patterns

### Mixed per-blocker classification

In a multi-blocker review, EACH blocker is independently classified. The NET recommendation = union.

- **A + B mix** → B fix runs; A items recorded as packaging note in close handoff.
- **A + C mix** → C rebuttal or defer; A items recorded as packaging note.
- **B + C mix** → B fix runs first; after fix, judge whether C still applies.

The deliver-close-verdict JSON's `verdict` field reflects the dominant action:
- Any B remaining → `verdict: B`.
- C unresolved → `verdict: C`.
- D triggered → `verdict: D`.
- Otherwise → `verdict: A` with appropriate subclass.

### Conditional finding self-resolving

Code Reviewer's blocker contains a "if X then exclude" condition; handoff §9 confirms the condition holds.

**Resolution**: classify as **A-with-packaging-note**. Customer's `git add` simply does not stage the conditional file. No Dev fix or re-review needed.

## Quick decision flowchart

```
Code Reviewer returns → for EACH blocker:

  ├─ path-based (extra files in commit)?
  │   └─ substantive findings closed?
  │       → A-with-packaging-note
  │
  ├─ conditional ("if X, exclude")?
  │   └─ handoff confirms condition?
  │       → A-with-packaging-note
  │
  ├─ typographical-only?
  │   └─ non-blocking checks confirm substance?
  │       → A-with-evidence-gap-acknowledgment
  │
  ├─ mechanical fix + kernel approved + 4-conditions met?
  │   → B-resolved-without-re-review
  │
  ├─ content-substantive, IN-scope?
  │   → B (spawn_deliver_plan_fix)
  │
  ├─ out-of-scope?
  │   → C (rebuttal OR defer; close_taxonomy_C_or_D fires)
  │
  ├─ non-convergence (max rounds; severity escalation)?
  │   → D (close_taxonomy_C_or_D fires)
  │
  └─ NET: union of per-blocker → dominant action.
```

## §1.7 forbidden patterns at close

Per `role-cards/deliver-agent.md` and Constitution §1.7:

- A close verdict that quietly drops a §1.7 forbidden finding from `codex-findings.md` is a framework breach.
- B-resolved-without-re-review condition #1 ("kernel + verification-notes both approve") cannot be satisfied if a §1.7 finding is present — §1.7 findings are P0 and cannot be self-verified away.
- A C classification CANNOT be applied to a §1.7-flagged finding to defer it indefinitely. Forbidden patterns must be addressed in the current sub-sprint or escalated (D) — the Customer cannot route them to next milestone.

This template is itself an enforcement surface for §1.7.

## Template usage notes

- Adopters add new subclass discoveries at fold-back per `process/fold-back-protocol.md` §8.2.
- The flowchart is intentionally a decision tree (not a scoring matrix). Per-blocker classification is a discrete judgment, not a numerical score.
- For automated orchestrator close, the orchestrator parses the deliver-close-verdict per `schemas/deliver-close-verdict.schema.json`; subclass labels are free-form in the schema but should match the canonical names above for cross-adopter consistency.

---

## Appendix A — Provenance (non-normative)

Subclasses A-with-packaging-note, A-with-Codex-skipped, A-with-evidence-gap-acknowledgment, B-resolved-without-re-review, and the Conditional-finding-self-resolving pattern were all derived from csagent practice, mid-Q2 2026. Each subclass was named at a specific csagent sprint close conversation; the names are preserved verbatim in v4 for cross-adopter consistency.

The normative body above intentionally omits sprint ids and dates per Constitution §8 governance-editing-discipline (timelessness check). The sprint-level provenance is preserved here in the non-normative appendix as evidence for fold-back review.

---

End of deliver close taxonomy.
