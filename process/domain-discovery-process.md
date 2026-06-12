---
title: Domain discovery process (Δ-2)
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-07
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 10KB
notes: >
  Δ-2 EXTEND per v4-plan §4.1: 3-dim domain elicitation (D1 business / D2 user /
  D3 boundary) + inheritance-table pattern from csagent foundational/phase1.
  Loaded by Research Agent at Path 1 (Customer-driven brief authoring) and
  jointly with Customer at failure-brief triage.
---

# Domain discovery process (Δ-2)

When the Research Agent or Customer + Deliver triage needs to elicit a project's domain, walk three dimensions in order. Output is the input set for the closure_contract in `docs/research-briefs/<id>.md`.

This doc is the FRAMEWORK contract for HOW to elicit. The specific domain content (industry, customer segment, regulatory floor) is per-adopter.

## §1 Three dimensions of elicitation

### §1.1 D1 — Business

What is the business value the project is supposed to deliver?

- **Market problem** — what user / customer / business need exists; cite evidence (interviews / data / known incidents).
- **Business KPI** — quantitative success metric (≤5 metrics; more dilutes focus).
- **Scope IN / scope OUT** — explicit boundaries; scope OUT is tighter than "obvious things" (name adjacent-but-out-of-scope concerns).
- **Anti-goal** — what failure mode is acceptable rather than over-building.

The Customer is the primary source here. Research Agent asks clarifying questions; does NOT fabricate market analysis.

### §1.2 D2 — User

Who is the human-side actor and what's their context?

- **Primary user type(s)** — name them; if 2+ user types, note interactions / handoffs / disagreements.
- **Domain-specific vocabulary** — capture domain terms verbatim from real user materials (transcripts, tickets, docs); the agent's prompt-projection will need these.
- **User-facing failure modes** — what does a bad outcome FEEL like to the user; what observable behaviors signal good vs bad.
- **Domain handling rules** — heuristics the human side applies (rules of thumb; not formalized policy).

Type A AI agents need rich D2 (transcript samples drive UC inference); Type B workflows need lighter D2 (SOP defines the user-facing contract); Type C demos need a 1-page D2.

### §1.3 D3 — Boundary

Where does the system's authority end?

- **External systems** — APIs / databases / services the system interacts with (e.g., Salesforce, internal CRM, payment gateway).
- **Capability / permission boundary** — what the system MAY do; what requires human handoff.
- **PII / safety floor** — Constitution §1.4 deterministic invariants the runtime owns.
- **Grounding floor** — what factual claims require evidence; what is "soft semantic" vs "must be grounded."
- **Tier-0 invariant candidates** — what conditions must always hold; promoted to `docs/current/runtime_invariants.md` after `new_tier0_candidate` MANDATORY_CHECKPOINT.

D3 is typically where Constitution §1.4-Runtime-owns gets instantiated. Deliver Agent + Customer co-author; Research Agent surfaces gaps.

## §2 Inheritance-table pattern

A common failure mode at greenfield bootstrap: the Research Agent re-elicits everything from scratch when most domain context CAN be inherited from a closely-related adopter (e.g., another agent in the same domain) or from a higher-tier doc (e.g., the parent program's BRD).

The inheritance-table pattern (carried from csagent foundational phase1 practice) makes inheritance EXPLICIT:

```markdown
| Domain dimension | Source | Status |
|---|---|---|
| D1 market problem | `<parent>/brd.md §1` | inherit verbatim |
| D1 KPI | new for this project | author fresh |
| D2 user type | `<sibling>/docs/foundational/user-personas.md` | inherit + adjust per scope |
| D3 PII floor | `org-wide-policy.md` | inherit verbatim (immutable) |
| D3 Tier-0 candidates | new | author fresh; route through `new_tier0_candidate` checkpoint |
```

The table appears in Phase 1 `docs/foundational/business-need.md` and signals to Deliver + Code Reviewer what NEEDS verification at the inheriting site vs what was already validated at the source.

### §2.1 Inheritance rules

- **Inherit verbatim**: source is authoritative; do not edit at the inheriting site. If the source changes, the inheriting site re-fetches.
- **Inherit + adjust per scope**: source is the starting point; the inheriting site MAY narrow scope (e.g., "only handle refund flows, not order modifications") but MAY NOT expand scope.
- **Author fresh**: no relevant source exists; full Research Agent + Customer elicitation required.
- **Inherit + flag for re-validation**: source predates a relevant change (e.g., new compliance regulation); inheritance is a starting point but the inheriting site triggers fresh validation.

## §3 Output: closure_contract input set

The 3-dim elicitation produces the input set for the Research Agent's closure_contract authoring (Constitution §1.7-B; `templates/compact-research-brief.md`):

- **Positive shape** — derived from D1 KPI + D2 user-facing observable success.
- **Anti-pattern** — derived from D2 user-facing failure modes + D1 anti-goal.
- **Anchor phrases** — derived from D2 domain vocabulary + sample real user materials.

The closure_contract is NOT the elicitation itself; it's the milestone-scope contract derived from the elicitation. The elicitation may surface MORE than the closure_contract covers — the rest goes into `docs/foundational/business-need.md` (and Phase 2-5 docs).

## §4 Cross-Δ relationships

- **Δ-3** (tech-architecture-decision-catalog) — Phase 3 inputs; D3's external systems + capability boundary drive Δ-3 decisions #2 (context projection), #6 (tools), #7 (policy).
- **Δ-12** (artifact-taxonomy) — `docs/research-briefs/`, `docs/foundational/business-need.md`, `docs/proposals/` all flow from this Δ-2 process.
- **Δ-14** (profile-aware-maturity) — track choice (Type A / B / C / A+B) is driven by D2's user-interaction model (per-turn adaptive vs fixed sequence).
- **Δ-15** (agent-design-elicitation) — the 6-question Q&A + 4 inventories operate over the Δ-2 elicitation outputs.
- **Δ-16** (agent-creation-prerequisites) — the 7-category READY/DEFERRED/N/A gate uses Δ-2's outputs as inputs.

## §5 What this Δ does NOT cover

- Domain-specific schema (per-industry; per-track) — those live in `docs/current/<domain>-overlay.md` in the adopter repo.
- Detailed Phase 1-5 funnel walkthrough — that's `docs/greenfield-guide.md` + `docs/application-funnel.md`.
- Bad-case suite seed authoring — that's `process/badcase-lifecycle.md`.

## §6 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 3-dim shape (D1 / D2 / D3) is stable framework vocabulary; the inheritance-table pattern is stable. Per-dimension question lists are SUGGESTED — adopters may extend (e.g., add D4 regulatory dimension for healthcare adopters) with rationale.

---

End of Δ-2 Domain discovery process.
