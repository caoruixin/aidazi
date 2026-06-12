---
title: M-Autoloop module — Concept 1 (Auto Loop)
doc_tier: module
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-07
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 16KB
notes: >
  M-Autoloop module spec. THIS IS CONCEPT 1 (Auto Loop per Constitution §3.7
  + docs/two-loops-explainer.md) — the Type A AI agent's runtime
  self-improvement loop via auto-research. DISTINCT from Concept 2 (Delivery
  Loop / Δ-18 / process/delivery-loop.md) — multi-agent team delivery.
  Constitution §1.7-E forbids conflation in adopter docs. This module
  applies to Type A only; not Type B / Type C. Includes anti-gaming
  forbidden list, OBS triage L1/L2 hookup, rollback gates, reward signal
  discipline.
---

# M-Autoloop module — Concept 1 (Auto Loop)

This module specifies the **Auto Loop** — Concept 1 of the two loops distinguished in Constitution §3.7. The Auto Loop is the Type A AI agent's runtime self-improvement mechanism: the agent (or a driver running alongside) uses auto-research methods to autonomously improve ITSELF — its prompts, skills, internal strategies, retrieval thresholds.

**The Auto Loop is DISTINCT from the Delivery Loop** (Concept 2; `process/delivery-loop.md`). Constitution §1.7-E forbids conflating the two in adopter documentation. When both are in use, name each distinctly. See `docs/two-loops-explainer.md` for the full disambiguation.

This module is **Type A only**. Type B workflows have no Auto Loop equivalent (the SOP is the contract; self-modification would break the SOP-runner discipline). Type C demos don't need Auto Loop (off-the-shelf skills don't self-improve). Type A+B hybrid runs Auto Loop on the Type A top-loop surface only.

## §1 The Auto Loop's role

The Auto Loop is a CAPABILITY a Type A project may build. The framework provides:
- Guardrails (this module's anti-gaming forbidden list).
- Driver pattern hookup to OBS triage (per Δ-9 / `process/post-deployment-iteration.md`).
- Reward signal discipline (closure_contract-anchored, not raw pass-rate).
- Rollback gates.

The framework does NOT drive the Auto Loop. The adopter's Type A project implements the driver. The framework provides the SHAPE; the adopter implements the engine.

```
Production / eval traces
        ↓
OBS triage (Δ-9 L1)
        ↓
Mature patterns (Δ-9 L2)
        ↓
Auto Loop driver:
  - Selects experiment candidate from OBS patterns.
  - Constructs experiment (prompt variation; threshold change; skill edit).
  - Runs experiment in sandbox (bounded run_mode).
  - Records experiment result trace per modules/m-trace.md.
  - Computes reward signal (closure_contract-anchored).
  - Decides: promote / reject / hold.
        ↓
Customer reviews promotion candidates.
        ↓
Accepted experiments land in next milestone.
```

## §2 The driver

The Auto Loop driver is an adopter-side process / script / agent that:

1. **Reads OBS triage state** — current patterns per `process/post-deployment-iteration.md`.
2. **Proposes experiments** — small, scoped, reversible changes targeting one pattern at a time.
3. **Runs experiments** — in a sandboxed `run_mode: replay` or `run_mode: mock` (per `modules/m-trace.md` §3); NEVER on live production traffic without prior approval.
4. **Computes reward** — closure_contract-anchored signal (§4 below).
5. **Records outcomes** — per-experiment trace + verdict in a persistent ledger.
6. **Surfaces promotions** — per Customer-review cadence (per §5).

The driver may be:
- A scheduled overnight job (most common).
- An on-demand human-triggered "run an experiment on pattern X" command.
- A continuous-low-frequency background process.

Implementation is per-adopter; the framework guarantees the SHAPE.

## §3 Anti-gaming forbidden list (HARD requirement)

These constraints apply to every Auto Loop implementation. Violating any is a framework breach.

### §3.1 Auto Loop MUST NOT modify the eval target set

The bad-case suite (`process/badcase-lifecycle.md`) and the CaseSpec inventory are NOT Auto Loop targets. An experiment that adds cases to the suite to make itself "pass" is gaming the eval surface.

### §3.2 Auto Loop MUST NOT edit `closure_criterion` paragraphs

Per Constitution §1.7-B, closure_criterion is human-judgment text authored jointly by Deliver + human. Auto Loop editing closure_criterion to shift what "passing" means is gaming the contract.

The reverse is permitted: an Auto Loop experiment may surface a finding that "closure_criterion is under-specified for pattern X." The human + Deliver then revise closure_criterion deliberately (NOT via Auto Loop directly).

### §3.3 Auto Loop MUST NOT promote a winning experiment without human approval

Customer (or a designated human reviewer) approves every promotion candidate. Auto Loop surfacing experiments for review is automated; the promote/reject decision is HUMAN.

Constitution §1.7-C-related lens: Auto Loop spawning isn't structurally biased the way Acceptance spawning is (Auto Loop modifies the agent, not the judgment surface), but the human-approval rule prevents auto-cascade where one experiment's promotion seeds the next without human oversight.

### §3.4 Auto Loop MUST NOT re-run a failed experiment with adjusted thresholds without recording the original

Adjusting thresholds + re-running until a result "passes" is publication bias. The framework requires:
- Original experiment's full record preserved.
- Each adjusted re-run is a NEW experiment in the ledger.
- The decision to re-run requires rationale (e.g., "the original ran on a too-narrow case selection").

### §3.5 Auto Loop MUST NOT optimize Tier-2 metrics at the cost of Tier-3 / Tier-4

The 4-tier pyramid (per `modules/m-evaluation.md` §2) has Tier-3 (closure_contract-anchored) + Tier-4 (shadow) as the load-bearing surfaces. Experiments optimizing Tier-2 scenario pass-rate while regressing Tier-3 / Tier-4 are FAIL.

The reward signal (§4) anchors on Tier-3 / Tier-4 specifically to prevent this gaming.

### §3.6 Auto Loop MUST NOT modify trace shape

Per `modules/m-trace.md` §6: trace-shape changes are high-impact framework changes. Auto Loop is bounded to modify prompts / thresholds / skill text — NOT trace adaptors, NOT trace fields, NOT 6-primitive DSL grammar.

### §3.7 Auto Loop MUST NOT cross sandbox boundaries

Sandbox discipline (per `process/delivery-loop.md` §4.2.2):
- Auto Loop experiments run in `run_mode: replay` or `run_mode: mock`.
- Auto Loop MUST NOT read shadow-tier cases (`run_mode: shadow` is held out from all training-adjacent surfaces).
- Auto Loop MUST NOT write to production runtime config without human-promotion approval.

### §3.8 Auto Loop MUST NOT conflate with Delivery Loop (Constitution §1.7-E)

In adopter documentation, Auto Loop and Delivery Loop are named distinctly. An adopter doc that says "the auto loop drove our milestone close" is a Constitution §1.7-E breach — Auto Loop doesn't drive milestone closes; the Delivery Loop does.

This applies even when both loops are coordinated: an Auto Loop experiment whose promoted changes get consumed by the next milestone's Delivery Loop dispatch is TWO loops cooperating, not one loop with two purposes.

## §4 Reward signal discipline

The Auto Loop's reward signal — the quantitative output that decides experiment success — MUST be closure_contract-anchored.

### §4.1 What anchored means

The reward signal is computed from:
- Tier-3 (target-set) pass-rate against closure_contract-anchored cases.
- Tier-4 (shadow) regression check (no regression allowed).
- Per-closure_contract-clause Acceptance-style semantic match (where available).

The reward signal is NOT:
- Tier-1 smoke pass-rate (smoke is plumbing).
- Tier-2 scenario raw pass-rate (subject to scenario-mix gaming).
- Aggregate metric without closure_contract anchoring.

### §4.2 Why this matters

A reward signal that's anchored on raw pass-rate optimizes the agent to PASS cases (potentially by encoding case-specific responses, per Constitution §1.7's "encoding raw eval phrases" forbidden item).

A reward signal anchored on closure_contract-clause semantic match optimizes the agent to BEHAVE WELL on the patterns the closure_contract describes — even on cases not yet in the suite.

This is the difference between cheating on the test and learning the subject.

### §4.3 Constitution §1.6 alignment

Constitution §1.6: "eval is evidence, not authority. A pass-rate increase is insufficient unless it improves generalizable customer problem-solving."

The Auto Loop's reward signal is the operational expression of this rule. Pass-rate climbs that come with shadow regressions = reward FAIL. Pass-rate climbs that come with closure_contract-anchored signal improving + no shadow regression = reward PASS.

## §5 OBS triage L1 / L2 hookup

Auto Loop's experiment selection consumes OBS triage state per `process/post-deployment-iteration.md` Δ-9:

### §5.1 L1 (observation capture)

Single observations enter as OBS-items. Auto Loop SHOULD NOT propose experiments off single observations — too noisy; high false-positive rate.

### §5.2 L2 (pattern maturity)

When an OBS-item matures to an R-item (n ≥ 2 similar observations OR human-flagged load-bearing), Auto Loop is ELIGIBLE to propose experiments targeting it.

Eligibility ≠ obligation. The driver MAY skip patterns where:
- The fix-layer is not Auto-Loop-addressable (e.g., `infra` or `java_guard` fix-layers — code changes by humans).
- The pattern's reward-signal anchor is unclear.
- Customer has flagged the pattern as "not yet ready for auto-experiment."

## §6 Rollback gates

Every Auto Loop promotion has a rollback path.

### §6.1 Per-experiment rollback

If a promoted experiment, after landing in a milestone, regresses Tier-3 / Tier-4 in the next eval run:
- Roll back the change.
- Mark the experiment `rolled-back` in the Auto Loop ledger with rationale.
- Re-run the OBS triage on the original pattern (the experiment didn't solve it).

### §6.2 Per-milestone Auto Loop pause

If a milestone close finds Auto Loop's recent promotions correlate with Acceptance failures (multiple promoted experiments contributing to a `fix_required` verdict), pause Auto Loop. Customer + Deliver + framework maintainer review:
- Did the reward signal mis-anchor?
- Did the OBS triage promote false patterns?
- Is the closure_contract drift?

Pause is recoverable; the Auto Loop resumes after the analysis surfaces a fix.

### §6.3 Hard rollback (forbidden-list breach)

If Auto Loop is found to have violated §3 forbidden list, IMMEDIATE pause + framework-maintainer review. The pause is not recoverable until the breach root cause is understood + the driver implementation is fixed.

## §7 Cross-reference: distinguishing from Delivery Loop

| | Auto Loop (Concept 1) | Delivery Loop (Concept 2) |
|---|---|---|
| Subject | The AI agent | The multi-agent team |
| Goal | Agent self-improvement | Milestone delivery + gap correction |
| Driver | M-Autoloop module (this doc) | Δ-18 orchestrator (`process/delivery-loop.md`) |
| Track applicability | Type A only | All tracks |
| Cadence | Per experiment (overnight typical) | Per milestone |
| Verdict surface | Reward signal (closure_contract-anchored) | Acceptance verdict (`schemas/acceptance-verdict.schema.json`) |
| Human role | Approves promotion candidates | Signs gate 1 (brief) + gate 2 (acceptance) + MANDATORY_CHECKPOINTS |
| Failure modes | §3 anti-gaming list | `process/delivery-loop.md` §4.2.8 anti-patterns |

**They cooperate** — Auto Loop's promoted changes land in milestones the Delivery Loop closes. They are NOT one loop.

## §8 Cross-references

- Constitution §3.7 — the two-loops distinction.
- Constitution §1.7-E — forbidden conflation.
- Constitution §1.6 — eval-rule alignment.
- `docs/two-loops-explainer.md` — adopter-facing disambiguation.
- `process/delivery-loop.md` — Delivery Loop (Concept 2; distinct).
- `process/post-deployment-iteration.md` (Δ-9) — OBS triage that feeds Auto Loop.
- `modules/m-evaluation.md` — 4-tier pyramid + reward-signal source.
- `modules/m-trace.md` — trace shape + run_mode for experiments.
- `process/badcase-lifecycle.md` — suite the reward signal reads.

## §9 Editing this module

Module-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The §3 anti-gaming list is HARD — additions are framework-level (route through fold-back with adopter evidence); subtractions are forbidden (the items address known failure modes).

The reward-signal discipline (§4) is load-bearing — modifying it risks the gaming patterns Constitution §1.6 + §1.7 exist to prevent.

OBS triage L1/L2 hookup (§5) evolves with `process/post-deployment-iteration.md` Δ-9; the hookup pattern follows Δ-9's state.

---

End of M-Autoloop module (Concept 1).
