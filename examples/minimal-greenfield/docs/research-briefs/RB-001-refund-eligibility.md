---
title: Refund eligibility determination
doc_tier: research-brief
doc_category: live
status: current
source_of_truth: this file
last_reviewed: 2026-06-12
brief_id: RB-001
input_path: path_1_customer_ask
related_proposals: []
related_failure_briefs: []
related_r_items: [OBS-001]
customer_signed: true
sign_off_date: 2026-06-12
---

# RB-001 — Refund eligibility determination

This is the signed research brief that anchors milestone M1 (`docs/milestone_objective.md`). The Acceptance Agent judges M1's delivered behaviour against the closure_contract below (gate 2). Worked example — a real Type A brief kept compact.

## 1. Background

Acme's customers frequently ask whether a specific order is eligible for a refund (UC-1 in `docs/current/domain_taxonomy.md`), and — when it isn't — why. Today those questions go to human agents. The Customer asked the Research role: "what should a bot do for refund-eligibility questions?" From ~200 sample transcripts, UC-1 (eligibility check) and UC-2 (denial reason) dominate; UC-4 (escalation) is the safety valve. This brief scopes the first milestone to those three.

## 2. Closure contract (Constitution §1.7-B)

### 2.1 Positive shape

When a customer asks about a refund for a specific order, the agent acknowledges the request, checks that order against the refund policy, and then either **confirms eligibility with a clear timeline** or **explains the specific blocking reason** in plain language. When the order can't be identified, or the situation falls outside what the bot can determine, the agent **escalates to a human** rather than guessing. Every eligibility statement is grounded in an actual policy check on the actual order — never an estimate.

### 2.2 Anti-pattern

The agent says "I'm looking into that for you" without ever returning a determination; OR gives a generic "refunds depend on our policy" answer without checking the specific order; OR confirms eligibility without naming a timeline; OR — worst — states an eligibility outcome it did not ground in a real policy check (e.g., guessing the order is within the window). For an unknown order id, fabricating a plausible-sounding answer instead of asking the customer to confirm the number.

### 2.3 Anchor phrases (evidence, not matchers)

- "You're eligible — your refund should reach your account in 3-5 business days."
- "This order was delivered more than 30 days ago, so it's outside the refund window."
- "That item is in a non-refundable category, so I can't start a refund for it."
- "I couldn't find that order number — could you double-check it for me?"
- "Let me connect you with a teammate who can take a closer look."

These describe the *kind* of language a good response uses. The Acceptance verdict is a semantic match (positive shape held, anti-pattern avoided), never a string match.

## 3. Scope IN

- UC-1 — determine refund eligibility for a single specific order against the policy window + category rules.
- UC-2 — when ineligible, explain the specific blocking reason (expired window OR non-refundable category).
- UC-4 — escalate to a human when the order can't be identified or the case is outside the bot's determination.

## 4. Scope OUT

- UC-3 — general "how do refunds work" education (no specific order). Deferred to a later milestone.
- Actually initiating / executing the refund transaction — M1 is *determination + explanation*, not processing.
- Multi-order or batch refund requests in a single turn.
- Any non-refund intent (order tracking, address changes, etc.).

## 5. Anti-goal

We are not trying to maximise refund approvals or to answer every refund-adjacent question. A bot that politely escalates an ambiguous or unidentifiable case is preferred over one that guesses an eligibility determination it cannot ground.

## 6. KPI

| Name | Target | Measurement |
|---|---|---|
| Eligibility-determination accuracy | ≥ 0.95 | core bad-case suite (`eval/bad_cases/_manifest.md`) |
| Wrong-containment (claims handled but didn't determine) | ≤ 0.02 | bad-case suite + trace review |
| Escalation correctness (UC-4) | ≥ 0.90 | escalation cases in the suite |

These match the standing floor in `docs/current/eval_acceptance_bars.md`; the closure_contract above is the per-milestone success definition layered on top.

## 7. Risk & impact

- A wrong eligibility determination is direct customer harm (false promise or wrongful denial) — hence TI-1/TI-3 keep the eligibility math deterministic, not LLM-estimated.
- PII exposure across customers is a hard floor (TI-2); a refund lookup must never surface another customer's order.
- Load-bearing dependency: the eligibility-check tool + access to order `delivered_at` and policy category data. If that tool is unavailable, the agent escalates rather than guesses.

## 8. Related R-items

- `OBS-001` (`docs/action_bank.md`) — some transcripts blend UC-1 and UC-3 in one turn; watched, not yet in scope. If it matures (n≥2 load-bearing), it routes via Path 2 into a future brief.

## 9. Customer sign-off (gate 1)

- Signed: yes
- Date: 2026-06-12
- Signer: Acme Returns PM (Customer)
- Reservations / conditions: none. UC-3 education explicitly deferred by mutual agreement.

---

End of RB-001.
