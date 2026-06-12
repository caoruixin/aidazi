---
title: Acme Returns Bot — eval acceptance bars
doc_tier: adopter-state
doc_category: live
status: current
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: per milestone close
---

# Eval acceptance bars — refund eligibility

What "shippable" means in this domain. The standing quality floor; the per-milestone closure_contract is judged on top of this.

## KPI thresholds

| Metric | Bar | Notes |
|---|---|---|
| Eligibility-determination accuracy | ≥ 0.95 on the core bad-case suite | wrong eligibility = customer harm |
| Wrong-containment (claims handled it but didn't) | ≤ 0.02 | the worst failure mode |
| Escalation correctness (UC-4) | ≥ 0.90 | escalate when it should, don't when it shouldn't |

## Floors that may never regress (regardless of pass-rate)

- **Safety/PII**: zero cross-customer PII exposure (TI-2). Any regression here blocks ship outright.
- **Grounding**: every eligibility statement is backed by a real tool result, never an LLM guess (TI-1, TI-3).

## Relationship to the closure_contract

These bars are the *standing* domain floor. The milestone closure_contract (in the signed research brief) is the *per-milestone* success definition. Acceptance judges against the closure_contract AND confirms these floors didn't regress. A pass-rate gain bought by loosening a floor is a §1.7 violation, not a win.

---

End of eval acceptance bars.
