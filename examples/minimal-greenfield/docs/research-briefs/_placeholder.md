# docs/research-briefs/ — where signed research briefs land

The **Research Agent** writes formal need specs here, one per `<id>.md`, each carrying a `closure_contract` (positive shape + anti-pattern + anchor phrases) + scope IN/OUT + anti-goal + KPI. The **Customer signs** at gate 1 (`customer_signed: true`).

In this example, `RB-001-refund-eligibility.md` would live here — it's the brief `docs/milestone_objective.md` cites as M1's closure_contract source. It's left as this placeholder to keep the snapshot minimal; in a real project the signed brief is the load-bearing artifact Acceptance later judges against.

- Template: `aidazi/templates/compact-research-brief.md`
- Schema: `aidazi/schemas/research-brief.schema.json`
- Role: `aidazi/role-cards/research-agent.md`
- Distinct from `docs/proposals/` (informal exploration; no closure_contract) — see `aidazi/docs/directory-taxonomy.md`.
