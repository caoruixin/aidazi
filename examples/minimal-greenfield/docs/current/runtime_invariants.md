---
title: Acme Returns Bot — runtime invariants (Tier-0)
doc_tier: adopter-state
doc_category: live
status: current
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: per milestone close
---

# Runtime invariants (Tier-0) — refund eligibility

The hard, deterministic rules the runtime owns in this domain (`aidazi/governance/constitution.md` §1.4). Load-bearing for the Code Reviewer: a proposed guard is justified only if it protects an invariant on THIS list. Adding a new invariant is a `new_tier0_candidate` MANDATORY_CHECKPOINT, not a silent edit.

| ID | Invariant | Owner |
|---|---|---|
| TI-1 | Never confirm a refund as eligible without checking the specific order against the policy window. | runtime (eligibility check is a tool call, not an LLM claim) |
| TI-2 | Never expose another customer's order or PII. | runtime (capability boundary) |
| TI-3 | Eligibility math (days since `delivered_at`, category check) is deterministic — never LLM-estimated. | runtime |
| TI-4 | Refund processing is idempotent on `refund_request.id`. | runtime |

Everything else — interpreting the customer's intent, deciding when to escalate, wording the response, detecting topic drift — is LLM-owned (§1.3) and MUST NOT be moved to a guard.

---

End of runtime invariants.
