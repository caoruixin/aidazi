---
title: Acme Returns Bot — bad-case suite manifest
doc_tier: adopter-state
doc_category: live
status: current
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: per sprint close
---

# Bad-case suite manifest

Curated regression suite (the primary acceptance gate; composite scores are observation-only per F2). Each case is a CaseSpec yaml (`aidazi/schemas/case-spec.schema.json`) with a `closure_criterion` written as a human-judgment paragraph (positive shape + anti-pattern + anchor phrases — NEVER keyword match, per §1.7-B). Human authors the `closure_criterion`; Deliver curates structure.

| Case id | Tier | UC | Shape |
|---|---|---|---|
| BC-001-eligible | core | UC-1 | order within window → confirm eligibility + timeline |
| BC-002-just-expired | core | UC-1 | order at day 31 → explain the specific blocking reason |
| BC-003-nonrefundable-item | core | UC-1 | refundable window but non-refundable category → explain |
| BC-004-unknown-order | scope-relevant | UC-1 | order id not found → ask to confirm, don't fabricate |
| BC-005-already-refunded | scope-relevant | UC-1 | already refunded → state it, don't re-process (TI-4) |

## Tiering + downgrade (per `aidazi/process/badcase-lifecycle.md`)

- `core` runs at every milestone close (this project: every sub-sprint close — see adoption-state divergence).
- Downgrade rule: N≥2 PASS across consecutive closes → consider `scope-relevant` → `closed-as-regression-guard`.

## Dev contamination rule

Dev sessions have NO read access to this directory (holdout; §10 anti-pattern #4). Dev may RUN the suite via the eval harness; it may not read or edit the cases.

---

End of bad-case suite manifest.
