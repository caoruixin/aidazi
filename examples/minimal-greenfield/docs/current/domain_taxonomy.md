---
title: Acme Returns Bot — domain taxonomy
doc_tier: adopter-state
doc_category: live
status: current
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: per milestone close
---

# Domain taxonomy — refund eligibility (Type A)

Example domain contract. Descriptive, not procedural — names what exists; handling rules live in the product/service design.

## Entities

| Entity | States | Notes |
|---|---|---|
| `order` | placed / shipped / delivered / returned / refunded | has `delivered_at`, `total`, `items[]` |
| `refund_request` | new / eligible / ineligible / processing / completed | references one `order` |
| `refund_policy` | active | 30-day window from `delivered_at`; some item categories non-refundable |
| `customer` | — | owns orders; PII-bearing |

## Use-case / intent taxonomy (inferred from transcripts)

| UC id | Intent | Frequency (sample) |
|---|---|---|
| UC-1 | Check refund eligibility for a specific order | high |
| UC-2 | Ask why a refund was denied | medium |
| UC-3 | General "how do refunds work" question | medium |
| UC-4 | Escalate to a human agent | low |

UC taxonomy was inferred from ~200 real transcripts, not invented up front (avoids the P1 spec-first/data-late detour).

## Vocabulary

- Customers say "money back" / "return" / "send it back" — all map to refund intent.
- "Window" = the 30-day eligibility period.
- Internal term "RMA" is NOT used customer-facing.

---

End of domain taxonomy.
