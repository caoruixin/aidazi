---
title: Post-deployment iteration (Δ-9) — OBS triage + Auto Loop driver
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
size_target: 12KB
notes: >
  Δ-9 AMEND per v4-plan §4.1: post-deployment OBS triage L1/L2 + Auto Loop
  driver pattern + reframed under 5-role chain (Deliver owns OBS triage;
  Acceptance fix_required → gap brief → R-item promotion via human-confirm).
  Includes Fix-Layer Classification Checklist (universal base layers + profile-specific extension layers routing tree).
---

# Post-deployment iteration (Δ-9)

When the agent is in production and observations accumulate, this Δ defines the triage discipline that decides what becomes an R-item (action_bank entry; next-sprint backlog) vs an OBS-item (observation; pattern-not-yet-load-bearing) vs an Auto Loop driver input (Type A self-improvement; per `modules/m-autoloop.md`).

This Δ is also where the Fix-Layer Classification Checklist lives — the routing tree that decides which fix-layer a failure targets across the **universal base layer set + profile-specific extension layers** (the full set depends on track per `process/profile-aware-maturity.md` Δ-14).

## §1 OBS vs R-item — two-layer triage

When a failure is observed in production (real session; not eval), it enters as an **OBS-item** (observation):

- Single observation; not yet a pattern.
- Tech-internal description; root-cause hypothesis if available.
- Filed in `docs/action_bank.md` under the OBS-section by Deliver Agent.

An OBS-item is promoted to an **R-item** (require / requirement) when:

- The pattern matures (n ≥ 2 similar observations); OR
- The single observation is severe enough to be load-bearing alone; OR
- Customer flags the observation as load-bearing.

R-items live in `docs/action_bank.md` under the R-section, with stable IDs (e.g., `R-citation-display-token-url-preferred`). They are the input to milestone planning.

The csagent practice (which v4 preserves) is to be DELIBERATE about the OBS → R-item promotion: most observations stay as OBS forever; only the load-bearing ones earn R-item status. This prevents action_bank bloat.

## §2 Two-layer triage detail

### §2.1 L1 — Observation capture (cheap; high throughput)

When Dev / Code Reviewer / Customer / production monitor notices a behavior:

1. Capture as `docs/diagnostics/<id>.md` — tech-internal root-cause notes.
2. Cross-reference any related R-items already tracking similar.
3. Add OBS-id to `docs/action_bank.md` OBS-section.

L1 is cheap and high-volume. Most observations don't go further.

### §2.2 L2 — R-item promotion (deliberate; reviewed)

At each milestone planning round, Deliver + Customer review the OBS-section and promote candidates that match the criteria above. Promotion:

1. Authors an R-item entry in `action_bank.md` with stable ID.
2. Cross-links to the contributing OBS-items + diagnostics.
3. Sets a milestone target (current / next / future / TBD).

Promotion is a JOINT decision; Deliver MAY surface candidates but Customer signs the promotion (it shapes the next milestone's scope).

### §2.3 Pattern → failure-brief escalation

When the L2 promotion happens AND the failure pattern has n ≥ 2 contributing diagnostics, the Deliver Agent + Customer may ALSO file a formal `docs/diagnostics/failure-briefs/<id>.md` (6-field template). The failure-brief is Path 2 input to Research Agent — the research-brief that comes back gives Deliver formal scope for the fix.

This is the pattern v4 §1.7-C-related boundary: significant gaps loop through Research, not via silent Deliver scope expansion.

## §3 The Fix-Layer Classification Checklist

When a failure is observed and a fix is being considered, walk this checklist BEFORE any code is written. The checklist routes the fix to one layer drawn from the **universal base set + profile-specific extension layers** below. Walk the questions in order; the first matching question wins. The point is NOT to find the "best" layer in the abstract — it is to prevent every failure defaulting to a `java_guard` fix.

### §3.1 The fix-layer set (universal base + profile-specific extensions)

**Universal base layers** (apply to every track):

- **`infra`** — orchestration, transport, persistence, timeouts, OOM, endpoint / credential / config wiring. Owns the run loop not crashing.
- **`java_guard`** (Type A) / **`runtime_guard`** (Type B / Type C / hybrid) — deterministic kernel-level invariants the runtime must guarantee (Constitution §1.4). Adding one requires a CURRENT Tier-0 invariant in `docs/current/runtime_invariants.md`. (The two names refer to the same role; adopters use the term matching their stack.)
- **`prompt_projection`** — what state, signals, candidate lists, and diagnostics are surfaced to the LLM in the per-turn projection. Owns whether the LLM has the inputs to make a correct semantic choice.
- **`skill_state`** — multi-tool / multi-turn flow state: entity context, task status, intake fields, drift carry-over, same-UC continuity. Owns the durability of state across turns.
- **`semantic_planner`** — the LLM's own semantic choices (UC hypothesis, next action, escalation posture, follow-up). Owned by Constitution §1.3.
- **`eval_spec`** — the CaseSpec, the expected-behaviour rubric, the judge configuration. Owns whether the eval is asking the system to do something it can and should do.
- **`product_policy`** — whether the underlying ask is a product / policy decision the runtime cannot make alone.
- **`judge_calibration`** — the judge's own stability / rubric quality; flips on the same prompt + CaseSpec across reruns.
- **`human_review_required`** — no clean classification, OR the failure looks like guard territory but no current Tier-0 invariant covers it. Escalate; do NOT invent a new Tier-0.

**Profile-specific extension layers** (apply per declared track per `process/profile-aware-maturity.md` Δ-14):

- **`workflow_definition`** (Type B / Type A+B hybrid) — the SOP rows; the workflow runner's contract. When the SOP is itself wrong (incomplete slot list, mis-specified verification gate), the failure is here.

Schemas (`schemas/review-verdict.schema.json`, `schemas/sprint_stanza.schema.json`, `schemas/deliver-plan-fix.schema.json`) enumerate the union of universal + extension layer names so a single enum covers all profiles; adopters use the subset relevant to their declared track.

### §3.2 Decision questions (first match wins)

1. Is the session failing to start, crash on infra, or hit a timeout / OOM not caused by tool semantics? → **`infra`**.

2. Is a current Tier-0 invariant being broken? → **`java_guard`** / **`runtime_guard`**.
   - If the failure LOOKS like java_guard territory but no current Tier-0 invariant covers it, flag **`human_review_required`** instead of inventing a new Tier-0.

3. (Type B / A+B only) Is the SOP's per-step verification gate failing because the SOP itself is wrong (e.g., the step's slot list is incomplete, the order is wrong, a verification gate has been mis-specified)? → **`workflow_definition`**.

4. Did the LLM choose validly within the available options, but the projection / context handed to it was wrong or impoverished (missing slot, missing candidate, missing diagnostic)? → **`prompt_projection`**.

5. Is a multi-tool / multi-turn flow losing state across turns (entity reference, task status, intake field, drift carry-over)? → **`skill_state`**.

6. Is the LLM choosing a semantically wrong action even when projection and state are correct (e.g., wrong UC hypothesis, unjustified escalation, missing follow-up, paraphrasing a `retrieved_but_unresolved` hit on a FAQ-path UC)? → **`semantic_planner`**.

7. Is the eval CaseSpec or judge asking the system to do something it cannot or should not do — a factual or policy impossibility, a frozen enum the CaseSpec asks to extend, a mis-rubric? → **`eval_spec`**.

8. Is the underlying ask a product / policy decision (e.g., "may the bot share an advert URL", "what is the bot's refund liability posture") that the runtime cannot adjudicate without product sign-off? → **`product_policy`**.

**Tail rule (judge stability)**: if the same case flips across reruns of the SAME prompt and CaseSpec, reclassify as **`judge_calibration`** regardless of which question above otherwise matched.

**Default tail**: if no question matches cleanly, → **`human_review_required`**.

### §3.3 Why no java_guard by default

Most observed failures LOOK LIKE java_guard territory because a keyword / regex / if-else can paper over the symptom in one PR. Constitution §1.5 (Iteration rule) and §1.7 (Forbidden list) explicitly rule this out for soft semantic decisions: those belong to the LLM.

A new java_guard is only justified when it protects a CURRENT Tier-0 invariant. If no current Tier-0 covers it, `human_review_required` is the correct exit — the Customer decides whether to open a new Tier-0 (which routes through `new_tier0_candidate` MANDATORY_CHECKPOINT) or to push the fix back to `prompt_projection` / `skill_state` / `semantic_planner`.

## §4 Auto Loop driver pattern (Type A only)

Per Constitution §3.7: Auto Loop (Concept 1) is the agent's self-improvement loop. Δ-9 OBS triage is the INPUT to Auto Loop's experiment selection — the OBS patterns become candidate optimization targets.

The driver pattern:

1. OBS / R-item triage surfaces a pattern of `prompt_projection` or `semantic_planner` failures.
2. Auto Loop driver (per `modules/m-autoloop.md`) proposes an experiment — e.g., a prompt variation, a retrieval-threshold change, a skill prompt edit.
3. Auto Loop runs the experiment in a sandboxed evaluation (NOT on production traffic).
4. Auto Loop returns a verdict; Customer reviews; if accepted, the change lands in next milestone.

Auto Loop's experiment selection is per `modules/m-autoloop.md` (anti-gaming forbidden list, OBS triage L1/L2 hookup, rollback gates). This Δ-9 doc defines the INPUT side; the module spec defines the engine.

### §4.1 Anti-gaming list

Auto Loop MUST NOT:
- Modify the eval target set to make the experiment "pass."
- Edit `closure_criterion` paragraphs (per Constitution §1.7-B).
- Promote a winning experiment without human approval.
- Re-run a failed experiment with adjusted thresholds without recording the original.

These are framework forbidden patterns; Auto Loop's driver implementation enforces them.

## §5 Acceptance gap → R-item promotion (Path 3 input)

When the Acceptance Agent returns `milestone_verdict: fix_required` AND Customer confirms `route: deliver_fix_iteration` at the human-confirm checkpoint (per Constitution §3.5), the gap brief inside the acceptance report becomes Deliver's Path 3 input. The gap brief's `failure_briefs[]` entries flow into action_bank as R-items per §2.2 above — with the specific provenance "Acceptance gap, milestone <id>."

This route is NORMAL post-deployment iteration. Constitution §1.7-C requires the human-confirm step BEFORE the gap brief flows; do NOT silently bypass.

## §6 Anti-patterns

- **OBS-item bypass** — Deliver promotes an observation directly to R-item without going through the OBS-section first; bloats action_bank with single-observation R-items.
- **Pattern false-positive** — n=2 similar-LOOKING observations get promoted; they turn out to be different root causes; the resulting R-item is unfocused. Mitigation: file diagnostics for each observation BEFORE promoting; check root causes match.
- **Java-guard creep** — failure routed to `java_guard` because a new Tier-0 was "obvious"; no Tier-0 actually existed. Mitigation: route through `new_tier0_candidate` MANDATORY_CHECKPOINT.
- **Semantic-hardcode regression via "small fix"** — a `prompt_projection` fix introduces a keyword check "to be safe." Constitution §1.7 + Code Reviewer anti-hardcode kernel catches at review.
- **Auto Loop optimizing the wrong objective** — experiment improves a Tier-2 metric while regressing a closure_contract clause. Mitigation: Auto Loop's reward signal MUST be closure-contract-anchored (not raw pass rate).

## §7 Cross-references

- Constitution §1.5 + §1.7 — Iteration rule + Forbidden list.
- `process/badcase-lifecycle.md` — bad-case suite is the regression-guard layer; OBS triage feeds it.
- `process/delivery-loop.md` §4.2.3 item 4 — `new_tier0_candidate` MANDATORY_CHECKPOINT.
- `modules/m-autoloop.md` — Auto Loop engine spec.
- `templates/deliver-close-taxonomy.md` — close decisions consume OBS triage state.

## §8 What this Δ does NOT cover

- Specific OBS / R-item ID schemes — adopter convention.
- Auto Loop engine implementation — `modules/m-autoloop.md`.
- Bad-case suite mechanics — `process/badcase-lifecycle.md`.
- Architecture-health metric collection — `process/architecture-health-metrics.md`.

## §9 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The universal base layer set + the question-order + the OBS/R-item distinction are stable framework vocabulary. Profile-specific extensions (e.g., `workflow_definition`) MAY grow via fold-back when new tracks land. Adopters MAY add Tier-3 layers locally (e.g., a `compliance` layer for healthcare) but SHOULD NOT rename the framework defaults — Code Reviewer prompts + Acceptance prompts reference the layer names.

---

End of Δ-9 Post-deployment iteration.
