---
title: Agent creation prerequisites (Δ-16)
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
  Δ-16 KEEP per v4-plan §4.1: 7-category READY/DEFERRED/N/A gate run before
  agent creation. Verifies the 7 input artifact categories are at sufficient
  readiness before downstream Phase 2-5 work begins. Loaded by Research /
  Deliver at Phase 1 close + Phase 2 entry.
---

# Agent creation prerequisites (Δ-16)

Before Phase 2 (product/service design) and downstream phases proceed, walk the 7-category prerequisite gate. Each category gets a status: READY / DEFERRED / N/A. Any DEFERRED auto-generates an OBS-id in `docs/action_bank.md` under "prereq-deferred" tag so the gap is tracked.

The gate exists to prevent the failure mode where Phase 2+ proceeds against a hollow Phase 1 — Phase 5 Acceptance fails because the closure_contract was never anchored in real prerequisites.

## §1 The 7 categories

### §1.1 #1 — BRD (Business Requirements Document) prerequisite

What the business wants the system to do. Source: Customer + Phase 1 elicitation per Δ-2 + Δ-15 Q1-Q3.

**READY** if: business problem named, KPIs specified, scope IN/OUT documented, anti-goal stated.
**DEFERRED** if: business problem is sketched but KPIs missing OR scope boundaries unclear.
**N/A** if: pure-research / prototype project where business doesn't apply (rare).

### §1.2 #2 — PRD (Product Requirements Document) prerequisite

What the product/service form is. Source: Customer + Phase 2 design per Δ-15 Part B inventories.

**READY** if: UC registry (Type A) OR SOP step registry (Type B) OR off-the-shelf skill list (Type C) is populated; domain handling rules sketched.
**DEFERRED** if: high-level form is known but details missing (e.g., UC names but no tool-call wiring).
**N/A** if: project is at Phase 1 only; Phase 2 work hasn't started.

### §1.3 #3 — Engineering baseline prerequisite

Technical constraints + platform: infrastructure, API specs (e.g., Salesforce schema), integration approach, security/PII floor, cloud / on-prem constraints.

**READY** if: target platform identified; external API surfaces named; PII floor written; non-functional constraints documented.
**DEFERRED** if: platform chosen but specific APIs not yet wired.
**N/A** if: pure-LLM project with no external systems (rare).

Phase 3 (technical plan) CANNOT proceed without #3 READY or DEFERRED with rationale.

### §1.4 #4 — Knowledge corpus prerequisite

What the system needs to know. FAQ index; product catalog; policy manual; reference corpus.

**READY** if: corpus source identified + retrieval-readiness ensured (chunked / indexed / queryable).
**DEFERRED** if: corpus exists but retrieval not yet wired.
**N/A** if: Type C demo OR Type B SOP-runner whose corpus is in-SOP (rare).

For Type A in production, #4 is typically load-bearing.

### §1.5 #5 — Canned reply / response template prerequisite

For agents that produce structured response shapes: pre-approved phrasings, templates with slot substitution, brand-voice constraints.

**READY** if: templates / phrasings drafted + approved.
**DEFERRED** if: templates needed but not yet authored.
**N/A** if: Type C demo OR free-form Type A where every response is per-turn LLM-generated (most Type A).

### §1.6 #6 — External systems / APIs prerequisite

What the system integrates with. Salesforce; internal CRM; payment gateway; OAuth identity provider.

**READY** if: each integration has: contract documented + auth flow specified + error handling defined.
**DEFERRED** if: integration named but contract sketched only.
**N/A** if: pure-LLM agent with no external systems.

### §1.7 #7 — UI (user interface) prerequisite

How the user interacts. Chat interface; voice; mobile app; embed widget.

**READY** if: UI surface chosen + interaction model defined + accessibility / device support documented.
**DEFERRED** if: UI surface chosen but interaction details TBD.
**N/A** if: programmatic-only system (no human UI surface).

## §2 The READY / DEFERRED / N/A semantics

- **READY** — category is at sufficient maturity for downstream phases to depend on it.
- **DEFERRED** — category is incomplete; downstream work proceeds but the gap is tracked as an OBS-id (per Δ-9). DEFERRED is NOT a blocker; it's an honest acknowledgment.
- **N/A** — category doesn't apply to this project; documented with brief rationale.

The combination of (Phase progression decision) + (per-category status) is the routing decision:
- All 7 READY → Phase 2 proceeds with full prerequisite backing.
- Some DEFERRED → Phase 2 proceeds; deferred categories' OBS-ids tracked; Phase 3 may require resolution of certain DEFERRED items before proceeding (e.g., #3 engineering baseline + #6 external APIs are typically required before Phase 3).
- One or more N/A → proceed; document why N/A applies in `docs/foundational/business-need.md` § "What's not applicable."

## §3 Gate execution

The gate is walked by Research + Deliver at:

1. **End of Phase 1 / entry to Phase 2** — first prereq check; categories #1, #2 typically RIPE.
2. **Entry to Phase 3** — categories #3, #6, #7 typically required.
3. **Entry to Phase 4 (implementation)** — categories #4, #5 (if applicable).
4. **Entry to Phase 5 (eval / release)** — all 7 should be at-state; remaining DEFERRED items get plan rationale.

At each gate execution, the Deliver Agent records the 7-category status in `docs/foundational/business-need.md` § "Prereq status as of <YYYY-MM-DD>" OR equivalent.

## §4 DEFERRED → OBS-id flow

Each DEFERRED category produces an OBS-id in `action_bank.md`:

```
OBS-prereq-deferred-<category>-<short>: <one-line description>
  Tag: prereq-deferred-cat<N>
  Status: open
  Plan: <when expected to resolve>
```

OBS-ids mature to R-items per Δ-9 if the pattern matures (multiple DEFERRED categories from the same root cause; or the same category DEFERRED across multiple projects in the framework's adoption history).

## §5 Per-track applicability

| Category | Type A | Type B | Type C | Type A+B Hybrid |
|---|---|---|---|---|
| #1 BRD | READY | READY | DEFERRED (1-pager) | READY |
| #2 PRD | READY | READY (SOP IS the PRD substantially) | partial | READY (both surfaces) |
| #3 Engineering baseline | READY | READY | partial | READY |
| #4 Knowledge corpus | READY (typically) | DEFERRED-or-IN-SOP | N/A typical | READY |
| #5 Canned reply | DEFERRED-or-N/A | READY (templates per SOP step) | N/A | varies |
| #6 External systems | READY | READY | partial | READY |
| #7 UI | READY | READY | READY (the UI IS the demo) | READY |

Per Δ-14, these expected statuses are starting points; adopters override.

## §6 Anti-patterns

- **Gate evaded** — Phase 2+ proceeds without walking the gate. Phase 5 surfaces missing prerequisites as Acceptance failures; expensive to fix.
- **DEFERRED used as escape hatch** — every category marked DEFERRED so the gate "passes." The OBS-id tracking exists specifically to prevent silent deferral; a project with 5+ DEFERRED categories is signaling Phase 1 was incomplete.
- **N/A used to skip work** — category marked N/A without rationale. The framework requires documentation of why N/A applies; un-explained N/A is treated as DEFERRED.
- **Premature N/A** — category marked N/A early; later discovered to be necessary. Mitigation: revisit at each gate execution; status may change.

## §7 What this Δ does NOT cover

- Specific schemas for BRD / PRD shape — adopter convention OR `docs/foundational/business-need.md` template.
- Domain-specific prerequisite categories — adopter MAY add #8, #9 with rationale.
- How to actually source each prerequisite — `docs/greenfield-guide.md` walkthrough.

## §8 Cross-references

- `process/agent-design-elicitation.md` (Δ-15) — elicitation that PRODUCES prereq categories.
- `process/profile-aware-maturity.md` (Δ-14) — per-track expected status.
- `process/domain-discovery-process.md` (Δ-2) — D1/D2/D3 elicitation feeds categories #1, #2, #3.
- `process/post-deployment-iteration.md` (Δ-9) — OBS triage consumes DEFERRED categories.
- `docs/greenfield-guide.md` — Phase 1-5 walkthrough that integrates the gate.

## §9 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 7-category set is stable framework vocabulary. Adopters MAY extend (e.g., #8 compliance audit) with rationale; renumbering the 7 defaults is a fold-back-deliberation change.

---

End of Δ-16 Agent creation prerequisites.
