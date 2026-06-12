---
title: Stage-stable heuristic (Δ-13)
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
size_target: 4KB
notes: >
  Δ-13 KEEP per v4-plan §4.1: stage-stable softened to heuristic (not gate)
  per csagent's mid-M2 pivot evidence. Adopters use this as a planning hint,
  not a hard requirement to declare "architecture stable" before proceeding.
---

# Stage-stable heuristic (Δ-13)

When projects ask "is the architecture stable enough to move forward?" — the question is harder than it sounds. Declaring stability prematurely commits the team to defending choices that may be wrong; deferring stability indefinitely prevents the team from building on shared assumptions.

This Δ provides a HEURISTIC (not a gate) for answering "is this stage stable enough." Adopters use it as a planning hint at milestone transitions.

## §1 Why heuristic, not gate

v3.2 had a stricter "stage-stable" formulation that some adopters treated as a hard gate. csagent's M2 pivot (mid-Q2 2026) revealed the failure mode: a hard gate forces premature freeze (team declares stability to satisfy the gate; then has to unwind when the architecture proves wrong) OR forces premature stop (team can't declare stability honestly; work stalls).

The heuristic version threads the needle: a checklist that informs planning without forcing a binary decision.

## §2 The heuristic checklist

When asked "is this stage stable enough for the next milestone to depend on these choices," walk:

### §2.1 Anchor cases pass

The bad-case suite's `core` tier cases (per `process/badcase-lifecycle.md` §3) pass under the current architecture. If load-bearing core cases are still failing, the architecture has demonstrated insufficient discipline for downstream commitments.

### §2.2 Closure_contract is sound

The current milestone's `docs/research-briefs/<id>.md` closure_contract has been validated against delivered behavior at least once (one full Acceptance pass). If Acceptance has not run, you don't know if the architecture supports the contract.

### §2.3 No active scope_deviation

`scope_envelope_check` has not fired in the last sub-sprint close. Active scope deviation suggests the architecture is being pulled in unexpected directions.

### §2.4 Recent diagnostics aren't accumulating uncategorized

`docs/diagnostics/` has been triaged at each sub-sprint close; un-triaged diagnostics ≤ 3 OR have been deliberately deferred with a planning rationale.

### §2.5 Δ-3 decisions documented + ownership clear

`docs/foundational/technical-plan.md` covers the 8 Δ-3 decisions; each has a chosen value and a rationale; reversibility is honestly named.

### §2.6 Code Reviewer findings flowing through routinely

The last 3 sub-sprint closes had Code Reviewer verdicts that Deliver consumed without dispute (no Path 3 / no Codex rebuttal / no `out_of_scope_review` cascade).

## §3 Reading the checklist

- **All 6 pass** → the stage is likely stable; commit to the next milestone with confidence.
- **5 of 6 pass** → likely stable; the one failing item is the planning topic. Don't declare "unstable" — address the specific gap.
- **3-4 of 6 pass** → ambiguous. Discuss at planning round; consider whether the next milestone's scope can be narrowed to make the gap less load-bearing.
- **≤ 2 of 6 pass** → not stable; the next milestone should be scoped to address foundation issues, not new features.

These thresholds are SUGGESTED per Constitution §7.0; adopters override per project posture.

## §4 What this heuristic is NOT

- A gate that prevents milestone planning. Milestones can plan against unstable foundations; planning just acknowledges the additional risk.
- A formal proof of correctness. The checklist names observable signals, not theorems.
- A replacement for the closure_contract. Stable architecture doesn't excuse closure_contract gaps; both must hold.
- A mandate to freeze decisions. Δ-3 decisions remain reversible per their reversibility annotation; declaring "stable" doesn't lock them.

## §5 When the heuristic disagrees with team intuition

If the checklist says "likely stable" but the team feels unstable, the team's intuition is usually right — there's an unwritten signal the checklist isn't capturing. File a lesson (`templates/lessons-learned-template.md`) so the fold-back can extend the checklist.

If the checklist says "unstable" but the team feels confident, the checklist is usually right — there's a specific item being papered over. Walk it explicitly.

## §6 Cross-Δ relationships

- **Δ-11** (capability staging) — S5 / S6 stages assume stable architecture; the heuristic informs S5 entry.
- **Δ-14** (profile-aware maturity) — per-track maturity requirements interact with stability.
- **Constitution §3.7** (two loops) — Auto Loop SHOULD NOT run on unstable architecture (the experiments would compound the instability).
- **`templates/deliver-close-taxonomy.md`** — verdict D (non-convergent) is a stability red flag.

## §7 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 6-item checklist is the framework's current heuristic; adopters' fold-back contributions may extend it. The "heuristic not gate" framing is stable v4 vocabulary (changing back to a gate would re-introduce the failure mode csagent's M2 pivot revealed).

---

End of Δ-13 Stage-stable heuristic.
