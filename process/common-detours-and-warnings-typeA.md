---
title: Common detours and warnings — Type A (Δ-17-A)
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
size_target: 14KB
notes: >
  Δ-17-A per v4-plan §4.1 KEEP. 4 named cognitive-detour pitfalls
  observed in Type A agent development (P1-P4) + the cognitive-detour
  disclaimer (recognizing patterns mid-flight to self-exit). Adopters
  mid-flight use this to spot symptoms; greenfield adopters use it to
  pre-empt during Phase 3 planning.
---

# Common detours and warnings — Type A (Δ-17-A)

These are the 4 named cognitive-detour pitfalls Type A agent projects most reliably fall into. Each is detectable from observable signals. If you're here mid-flight reading this because of a symptom: the detour names are the keys; the exit routes are the body sections.

## §0 Cognitive-detour disclaimer

These aren't moral failings or skill gaps. They're cognitive detours — paths that LOOK like the right next step at the moment of decision but lead away from sustainable architecture. The patterns are predictable enough that the framework names them.

Recognizing you're on a detour is most of the work; once named, exit is usually straightforward.

If you're reading this proactively (greenfield planning): use the symptom lists as planning prompts. Phase 3 review should specifically check for early P1 / P2 signals.

If you're reading this mid-flight (something feels wrong): walk the symptoms and pick the closest match. Apply the exit route.

## §1 P1 — Spec-first / data-late

### §1.1 Symptom

- The team has written detailed prompts, defined a tool schema, specified phase pipeline behavior — all WITHOUT looking at real customer transcripts / sessions / user data.
- Bad-case suite is small or empty; cases are hypothetical ("a customer might say...").
- The closure_contract's anchor phrases are plausible but unattested; no real user actually said them.
- Eval pass-rate climbs steadily; production launches; production behavior differs sharply from eval.

### §1.2 Why it happens

Specs feel like progress; data collection feels like delay. The team can fill out a Phase 1-2 deck without leaving the desk; data requires a slower loop (real users, real sessions, real friction). Under deadline pressure, spec wins.

### §1.3 Exit route

1. Halt new spec work for the duration of the data-collection effort.
2. Collect 50-100 real transcripts (or whatever the equivalent is for your domain).
3. Walk each transcript: does the current closure_contract handle it? does the tool schema cover the actual actions? does the phase pipeline match real conversation shape?
4. Author 5-10 new bad cases from the transcripts — REAL session ids in `bad_case_metadata.source_session_id`.
5. Revise closure_contract anchor phrases against the actual user language.
6. Phase 2 / Phase 3 may need partial rework; do that explicitly, not silently.

### §1.4 Pre-emption (greenfield)

Phase 1 elicitation per Δ-2 D2 explicitly requires transcript samples / user data. If Phase 1 reviewers can't point at the data, P1 has not yet been started.

## §2 P2 — Eval-before-architecture-stable

### §2.1 Symptom

- The team rolled out a bad-case suite + Tier-1/2/3 eval pyramid.
- The runtime architecture is still in flux — Δ-3 decisions #1, #2, #5 are being revised every milestone.
- Eval results are ambiguous: cases pass one milestone, fail the next, after architectural changes nobody can clearly attribute.
- Trust in eval is degrading; team starts ignoring eval verdicts.

### §2.2 Why it happens

Eval feels mature; "we should be measuring." But when the system being measured is still being designed, the eval surface measures the architecture's instability, not the system's quality. The eval team treats this as a quality regression; the architecture team treats this as eval noise; both are right + wrong.

### §2.3 Exit route

1. Acknowledge architectural instability is the root cause; eval isn't broken.
2. Demote affected eval results to "advisory" status. Don't ship-block on them.
3. Stabilize Δ-3 decisions #1 / #2 / #5 (per Δ-13 stage-stable heuristic checklist).
4. Re-baseline eval AFTER architectural stabilization. Compare new baselines to post-stabilization, not pre-stabilization.
5. Document the "eval baseline reset" event in the milestone close package.

### §2.4 Pre-emption (greenfield)

The Δ-11 staging roadmap puts bad-case suite at S1, AFTER S0 (manual chain mode). Adopters following the ladder don't usually hit P2; adopters skipping ahead to "let's set up eval before we're ready" do.

## §3 P3 — Autoloop-as-eval-stress-test

### §3.1 Symptom

- Auto Loop (Concept 1 per Constitution §3.7) was set up enthusiastically.
- Auto Loop drives many experiments per day; eval results swing wildly.
- The team can't tell if Auto Loop's experiments are real improvements or noise.
- Eventually Auto Loop is paused; team isn't sure what to do with it.

### §3.2 Why it happens

Auto Loop's promise (the agent self-improves overnight) attracts investment before its prerequisites (stable eval surface; calibrated judge; closure_contract anchored bad cases) are in place. Auto Loop becomes a high-frequency stress test on an immature eval pipeline.

### §3.3 Exit route

1. Pause Auto Loop. (No experiments while diagnosing.)
2. Validate eval pipeline against manual judgments (calibration set per Δ-11 S3.5).
3. Confirm closure_contract is stable (Δ-13 stage-stable heuristic).
4. Re-introduce Auto Loop with bounded experiment count per day (e.g., 1-3 experiments).
5. Auto Loop reward signal MUST be closure-contract-anchored, NOT raw pass-rate (per Δ-9 §6 anti-pattern).

### §3.4 Pre-emption (greenfield)

Auto Loop is a S2+ capability per Δ-11; deploying it before S1.5 (Code Reviewer with anti-hardcode kernel) + S3 (F5 evidence pattern) reliably hits P3.

## §4 P4 — Mid-milestone pivot

### §4.1 Symptom

- Mid-milestone, the team discovers a foundational issue (Δ-3 decision wrong; closure_contract was actually under-specified; a critical Tier-0 invariant was missing).
- Instead of stopping and re-scoping the milestone, the team "pivots in flight" — silently shifts the milestone's effective scope to address the issue.
- Milestone close conversation discovers the actual delivered scope differs from `milestone_objective.md`'s declared scope.
- `scope_envelope_check` would have fired (if Δ-18 orchestrator was on); manual close conversation surfaces the gap.

### §4.2 Why it happens

Acknowledging a mid-milestone pivot feels like admitting Phase 1-3 was wrong. The team prefers to silently absorb the change and rationalize after the fact. The pivot succeeds technically (the issue is addressed) but the milestone framework's discipline (sub-sprints aligned to milestone north star) silently degrades.

### §4.3 Exit route

1. Stop. Convene Deliver + Customer.
2. Make the pivot explicit. Update `milestone_objective.md` with the revised scope.
3. The revised milestone may need to push next-milestone work later; honest planning beats silent shift.
4. If a closure_contract clause needs revision, route through `research_contract_revision` per Constitution §3.5 — Customer re-signs at gate 1.
5. The pivot itself becomes a R-item if the project's structure makes pivots likely again.

### §4.4 Pre-emption (greenfield)

`process/milestone-framework.md` §5: a sub-sprint that crosses an unrelated architectural surface is a signal that it belongs to a different milestone. Surfacing this signal at sub-sprint planning (not at sub-sprint close) pre-empts P4.

## §5 Recognizing detours mid-flight

Symptoms across multiple detours often appear together. Cross-cutting indicators:

- Acceptance verdicts are increasingly `needs_human` (no clean PASS / FAIL).
- Code Reviewer findings cluster in `eval_spec` or `judge_calibration` layers (not the working layers).
- Multiple sub-sprints in a row close with `B-resolved-without-re-review` verdicts despite not meeting the 4-condition criteria.
- Deliver close conversation feels less rigorous than at project start.

When you spot these together, walk this Δ-17-A checklist explicitly before assuming everything is fine.

## §6 Cross-references

- `process/badcase-lifecycle.md` — bad-case suite is the regression-guard layer; P1 / P2 / P3 all interact.
- `process/capability-staging-roadmap.md` (Δ-11) — staging ladder pre-empts most detours.
- `process/stage-stable-heuristic.md` (Δ-13) — P2 / P4 exit reference.
- `process/post-deployment-iteration.md` (Δ-9) — Auto Loop driver pattern; P3 exit reference.
- `templates/deliver-close-taxonomy.md` — verdict D (non-convergent) is often a detour signal.
- `docs/friction-playbook.md` — concrete friction patterns; Δ-17 is the pattern catalog, friction-playbook is the worked-cases catalog.

## §7 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 4-pattern set (P1-P4) is the v4 baseline; adopter fold-back contributions may add P5+ for newly-discovered detours. Existing patterns SHOULD NOT be renamed (Code Reviewer prompts + planning docs may reference P-numbers).

---

End of Δ-17-A Common detours Type A.
