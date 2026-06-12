---
title: Domain adaptation — the three domain contracts + layer extensions
doc_tier: application-guide
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 18KB
split_trigger: if §2 per-contract detail grows past 6KB, split each contract's authoring drill to its own template and keep the summary here
notes: >
  How a domain-agnostic framework becomes a domain-specific project. Defines
  the three required domain contracts (domain_taxonomy / runtime_invariants /
  eval_acceptance_bars) every adopter authors in docs/current/, the fix-layer
  extensions per track (workflow_definition for Type B / A+B; java_guard ↔
  runtime_guard naming), and the per-milestone domain ops. The framework is
  track-aware but domain-agnostic; this is where YOU make it about customer
  service, travel SOPs, e-commerce, or whatever your domain is.
---

# Domain adaptation — making a domain-agnostic framework domain-specific

The framework is **track-aware but domain-agnostic** (`governance/constitution.md` §1.2). It knows the difference between a Type A agent and a Type B workflow; it knows nothing about *your* domain — customer service, airline rebooking, e-commerce returns, legal intake. Domain adaptation is where you supply that knowledge, in a fixed shape the roles can rely on.

The skipped-domain-contracts failure is one of the most common adoption regrets (`docs/friction-playbook.md` F12): a team runs the framework's machinery without filling its domain contracts, and the roles end up reasoning against vague or absent context. Fill these first.

---

## §1 The three domain contracts (required)

Every adopter authors three domain contracts under `docs/current/`. They are the domain-specific counterpart to the universal constitution: the constitution says *what the LLM owns*; these say *what the LLM owns **in your domain***.

| Contract | File | Answers | Primary consumer |
|---|---|---|---|
| **Domain taxonomy** | `docs/current/domain_taxonomy.md` | What are the entities, use-cases/intents, and vocabulary of this domain? | Research (elicitation), Dev (implementation), Acceptance (judging in-domain) |
| **Runtime invariants** | `docs/current/runtime_invariants.md` | What hard, Tier-0 invariants must the runtime enforce in this domain? | Dev, Code Reviewer (the §1.3/§1.4 ownership lens) |
| **Eval acceptance bars** | `docs/current/eval_acceptance_bars.md` | What does "good enough to ship" mean numerically + behaviourally in this domain? | Acceptance, Deliver (close), eval design (Phase 5) |

These three are loaded at cold-start by every role session (per `governance/context_briefing.md`). A fourth `docs/current/` file — `agent_context_guide.md` — holds adopter-side per-task reading lists; it's not a domain contract but lives alongside them.

### §1.1 Domain taxonomy

What it contains:

- **Entities** — the nouns of your domain (order, refund, booking, claim, account) with their states and relationships.
- **Use-case / intent taxonomy** — the kinds of things a user wants. For Type A, this is the UC registry inferred from real transcripts (not invented up front — see the P1 *spec-first/data-late* detour in `process/common-detours-and-warnings-typeA.md`). For Type B, it's the SOP catalog.
- **Vocabulary** — the conventional terms the user side uses, so the LLM's customer-facing wording matches domain expectations (fed by the Δ-15 Part D industry research synthesis).

Authoring rule: keep it descriptive, not procedural. The taxonomy names *what exists*; the handling rules (how to respond) live in the product/service design (Phase 2), not here.

### §1.2 Runtime invariants

What it contains: the **Tier-0 invariants** — the hard, deterministic, kernel-level rules the runtime owns in your domain (`governance/constitution.md` §1.4). Examples by domain:

- Customer service: "never confirm a refund the order isn't eligible for"; "never expose another customer's PII."
- Airline SOP: "never rebook onto a flight that's already departed"; "never skip the fare-difference confirmation step."
- E-commerce: "never apply a discount code past its expiry"; idempotency on order submission.

This file is **load-bearing for the Code Reviewer**: the anti-hardcode kernel's question 2 asks whether a proposed hardcode protects a *current* Tier-0 invariant named here. A guard that protects an invariant in this list is justified; a keyword shortcut that doesn't is a §1.7 violation. So keep this list current — adding a new Tier-0 invariant is a `new_tier0_candidate` MANDATORY_CHECKPOINT (`process/delivery-loop.md` §4.2.3 #4), not a silent edit.

### §1.3 Eval acceptance bars

What it contains: the domain-specific definition of "shippable."

- KPI thresholds (accuracy, wrong-containment, escalation-correctness for Type A; per-step verification pass rate for Type B; LOCAL_ACCEPTANCE_CHECKLIST pass for Type C).
- The safety / grounding / PII floors that may never regress regardless of pass-rate gains (`governance/constitution.md` §1.6).
- The relationship between the eval suite and the closure_contract: the bars here are the *standing* domain quality floor; the closure_contract is the *per-milestone* success definition Acceptance judges against. Both apply at close.

## §2 Fix-layer extensions per track

The framework's fix-layer set (used by Δ-9 triage and the charter's `layers_allowed`) has a **universal base** plus **profile-specific extensions** (`process/post-deployment-iteration.md`). When you adapt for your track, you adopt the right layer set:

- **Universal base** (every track): `infra` / `java_guard` (Type A) or `runtime_guard` (Type B+) / `prompt_projection` / `skill_state` / `semantic_planner` / `eval_spec` / `product_policy` / `judge_calibration` / `human_review_required`.
- **Profile-specific extension**: `workflow_definition` — added for **Type B** and **Type A+B hybrid**. This is the layer where SOP-step definitions and per-step verification gates live; pure Type A projects don't have it.

Naming note: `java_guard` (Type A heritage) and `runtime_guard` (Type B+) are the **same role** under different names per stack — the deterministic guard layer. Use the name that matches your stack; record the mapping in `adoption-state.md` if it isn't obvious to a newcomer.

The charter's `layers_allowed` should list only the layers your track uses; `schemas/sprint_stanza.schema.json` and the verdict schemas enumerate the full union so one enum covers all profiles — you use the relevant subset.

## §3 Per-milestone domain operations

Domain adaptation is not a one-time setup; the contracts evolve as the project learns. Per-milestone domain ops:

- **At milestone planning**: Deliver checks whether the milestone's scope touches domain vocabulary or invariants not yet in the contracts. New entities/intents → update `domain_taxonomy.md`. New hard rules → propose a `new_tier0_candidate` checkpoint for `runtime_invariants.md`.
- **During the milestone**: when Dev or Code Reviewer discovers a domain rule the contracts don't capture, that's a `docs/diagnostics/<id>.md` note, not a silent contract edit. It matures into a contract update via triage.
- **At milestone close**: Acceptance judges against the closure_contract *and* the standing `eval_acceptance_bars.md` floor. If the bars themselves proved wrong (too loose, too tight), that's a `research_contract_revision` or an `adoption-state.md` divergence with rationale — not an in-place loosening to make the milestone pass (which would be a §1.7 "widening eval to accept a bot mistake" violation).

## §4 Domain overlays to the forbidden list (optional)

The constitution's §1.7 forbidden list is the framework baseline; you MAY extend it for your domain (§1.8). A healthcare adopter might add `§1.7-domain-A: no LLM-authored medical diagnosis`; a finance adopter might add a rule about unverified balance claims. Domain extensions live in `docs/current/<adopter>-domain-overlay.md` and are referenced from `adoption-state.md`. You may **add** domain forbidden items; you may never **subtract** from the framework's §1.7 (hard requirement, §1.8).

## §5 Checklist

Before your first milestone, confirm:

```
□ docs/current/domain_taxonomy.md authored — entities + UC/intent taxonomy + vocabulary
□ docs/current/runtime_invariants.md authored — Tier-0 invariants for this domain
□ docs/current/eval_acceptance_bars.md authored — KPI thresholds + safety/grounding/PII floors
□ Fix-layer set chosen for your track (workflow_definition added iff Type B / A+B)
□ java_guard ↔ runtime_guard naming recorded if ambiguous
□ (optional) domain forbidden-list overlay authored + referenced from adoption-state.md
```

A milestone run with these contracts empty or hand-waved is the F12 adoption-regret trap. Fill them; the roles depend on them.

---

End of domain adaptation.
