---
title: Iteration constitution
doc_tier: current-runtime
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-05-28
review_cadence: every 3-5 sprints
supersedes: []
superseded_by: null
notes: >
  Framework constitution + governance bundle for aidazi consumers.
  Section 1 is the LLM-first constitution. Sections 2-6 are the
  operational gates: Failure Brief template, Fix Layer Classification
  checklist, Anti-Hardcode review prompt, Eval Acceptance Rules,
  Architecture-Health Metric definitions. Section 7 specifies the
  sprint-objective stanza. Section 8 defines the milestone framework.
  Section 9 codifies the self-containment invariant for compact prompts.
---

# Iteration constitution

This document is the operational rulebook for how an agentic AI project
iterates. §1 is the LLM-first **Constitution**; §2–§6 are operational
gates (Failure Brief, Fix Layer Classification, Anti-Hardcode Review,
Eval Acceptance, Architecture-Health Metrics); §7 specifies the
sprint-objective stanza; §8 defines the milestone framework; §9
codifies the self-containment invariant for compact prompt artifacts.

Doc-tier and source-of-truth conventions are defined in
[`doc_governance.md`](doc_governance.md). Cold-start reading discipline
and the Context Pack Prompt are in [`context_briefing.md`](context_briefing.md).
This file references both; it does not duplicate them.

**Governance-doc editing discipline**: planning-time scope authorization
(e.g., "if (a), fold back §X") does NOT authorize execution-time content.
Before editing any governance-tier doc, verify: (1) timelessness — no
sprint numbers, R-item IDs, or dates; (2) principle vs current-state —
governance teaches principles, not findings; (3) necessity — would
backlog carry the load without the edit? (4) durable shift vs reaction.
If any check fails, put the content in your action backlog or sprint
archives.

**Consumer specialization**: the framework constitution references
three consumer-supplied domain contracts by stable name:

- `docs/current/domain_taxonomy.md` — your project's workflow lanes,
  shift detectors, escalation signals, grounding concepts
- `docs/current/runtime_invariants.md` — your project's Tier-0
  invariant registry
- `docs/current/eval_acceptance_bars.md` — your project's acceptance
  metric definitions (wrong-lane rate, escalation rate, grounding
  floor, etc.)

These three files MUST exist in any project consuming this constitution.
See [`../docs/domain-adaptation.md`](../docs/domain-adaptation.md) for
the placeholder checklist.

## 1. Constitution

### 1.1 Objective

Build an agentic AI that solves user problems with LLM-first semantic
flexibility, not a keyword chatbot or rigid rule engine.

### 1.2 Primary principle

Rules define boundaries. LLM owns semantic understanding.

### 1.3 LLM owns

- user goal inference
- issue / sub-task relation
- workflow lane hypothesis (domain-specific routing decisions)
- context shift / topic shift detection
- next action selection
- escalation posture (when to hand off to human or higher-privileged path)
- response strategy
- natural user-facing wording

The domain-specific instantiation of "workflow lane" / "shift detection"
/ "escalation" is defined in your `docs/current/domain_taxonomy.md`.

### 1.4 Runtime owns

- tool schema
- capability / permission boundary
- PII and safety floor
- grounding floor for factual claims
- budget / timeout
- idempotency
- persistence
- trace and eval contract

### 1.5 Iteration rule

Do not fix semantic failures by adding keyword / regex / if-else / enum
expansion unless a Tier-0 invariant (registered in
`docs/current/runtime_invariants.md`) is broken.

### 1.6 Evaluation rule

Eval is evidence, not authority. A pass-rate increase is insufficient
unless it improves generalizable user problem-solving and does not
regress safety, grounding, wrong-lane containment, or architecture
health (your domain-specific definitions live in
`docs/current/eval_acceptance_bars.md`).

### 1.7 Forbidden

- encoding raw eval phrases into runtime code or prompt
- adding workflow-lane-specific hard rules for soft semantic decisions
- widening eval spec to accept a genuine agent mistake
- optimizing visible eval at the cost of shadow / generalization
- using prompt as an if-else rule dump

## 2. Failure Brief Template

A **Failure Brief** is a short, structured record of one observed agent
failure. Briefs are filed jointly by a human (who labels the expected
behaviour) and a deliver agent (who labels the layer hypothesis and the
"do not do" list). They live under
`docs/diagnostics/failure-briefs/<brief-id>.md`. Briefs are the input
to case-family construction: they become the source for target /
neighbor / negative / shadow case families downstream.

Every brief has these six fields:

- **What happened?** — the observed agent behaviour in one or two
  sentences, written so a reader who has never seen the trace can
  understand the failure shape. *Why this field exists: the bug starts
  with a concrete observation, not a hypothesis.*
- **What should a good agent have done?** — the expected behaviour on
  the same input, written from the user's perspective. *Why this field
  exists: pins the failure to a contrast — agent did X, should have
  done Y — so the gap is named, not implied.*
- **Why does this matter?** — the user / business / safety impact in
  one line; references the Constitution clause the failure violates if
  applicable. *Why this field exists: forces a relevance check. A
  failure with no plausible user impact is a candidate for `eval_spec`
  reclassification, not a runtime fix.*
- **Is this a one-off or a pattern?** — one of `one-off`, `pattern`, or
  `unknown`, with a one-line note on evidence (e.g. number of similar
  traces, neighboring case ids, prior sprint references). *Why this
  field exists: pattern failures justify a case family; one-off
  failures usually do not justify a runtime change.*
- **Which layer is likely responsible?** — one of the layers in §3,
  with a one-line justification. Multiple-candidate hypotheses are
  allowed; §3's checklist disambiguates. *Why this field exists:
  forces the layer hypothesis to be explicit and disprovable, instead
  of defaulting to "fix the runtime".*
- **What should NOT be done?** — the tempting-but-wrong fix (typically
  a keyword / regex / if-else / enum / per-lane matrix) and the reason
  it is wrong (usually a Constitution clause). *Why this field exists:
  every brief encodes a guardrail against the short-term hardcode that
  would close the symptom without solving the failure.*

A filled-in template for your domain belongs at
`docs/diagnostics/failure-briefs/<brief-id>.md`. See
[`../templates/failure_brief.md`](../templates/failure_brief.md) for
the blank template.

## 3. Fix Layer Classification Checklist

Use this checklist any time a failure is observed and a fix is being
considered, **before any code is written**. The checklist routes the
fix to one of nine layers. Walk the questions in order; the first
matching question wins. The point is not to find the "best" layer in
the abstract — it is to prevent every failure defaulting to a runtime
guard.

### 3.1 Layer set

- `infra` — orchestration, transport, persistence, timeouts, OOM,
  endpoint / credential / config wiring. Owns the run loop not
  crashing.
- `runtime_guard` — deterministic kernel-level invariants the Runtime
  must guarantee (§1.4). Adding one requires a current Tier-0 invariant
  in `docs/current/runtime_invariants.md`.
- `prompt_projection` — what state, signals, candidate lists, and
  diagnostics are surfaced to the LLM in the per-turn projection. Owns
  whether the LLM has the inputs to make a correct semantic choice.
- `skill_state` — multi-tool / multi-turn flow state: entity context,
  task status, intake fields, context carry-over, same-lane continuity.
  Owns the durability of state across turns.
- `semantic_planner` — the LLM's own semantic choices (lane hypothesis,
  next action, escalation posture, follow-up). Owned by §1.3.
- `eval_spec` — the case specification, the expected-behaviour rubric,
  the judge configuration. Owns whether the eval is asking the system
  to do something it can and should do.
- `product_policy` — whether the underlying ask is a product / policy
  decision the agent cannot make alone (e.g. "may the agent disclose
  X?", "is this liability allowed?"). Domain-specific examples belong
  in `docs/current/domain_taxonomy.md`.
- `judge_calibration` — the judge's own stability / rubric quality;
  flips on the same prompt + case across reruns.
- `human_review_required` — no clean classification, or the failure
  looks like runtime-guard territory but no current Tier-0 invariant
  covers it. Escalate; do not invent a new Tier-0.

**Domain note**: some projects may add or rename a layer (e.g., a
state-machine-driven workflow project may add `workflow_definition` to
cover SOP/script tables). Such customization belongs in
`docs/current/domain_taxonomy.md` §Layer extensions and must preserve
the spirit of the original nine (anti-hardcode discipline, runtime-vs-
LLM ownership boundary, Tier-0 gate).

### 3.2 Decision questions (first match wins)

1. Is the session failing to start, crash on infra, or hit a timeout /
   OOM not caused by tool semantics? → `infra`.
2. Is a current Tier-0 invariant named in
   `docs/current/runtime_invariants.md` being broken? → `runtime_guard`.
   If the failure *looks like* runtime-guard territory but no current
   Tier-0 invariant covers it, flag `human_review_required` rather than
   inventing a new Tier-0 invariant.
3. Did the LLM choose validly within the available options, but the
   projection / context handed to it was wrong or impoverished (missing
   slot, missing candidate, missing diagnostic)? → `prompt_projection`.
4. Is a multi-tool / multi-turn flow losing state across turns (entity
   reference, task status, intake field, context carry-over)? →
   `skill_state`.
5. Is the LLM choosing a semantically wrong action even when projection
   and state are correct (wrong lane hypothesis, unjustified escalation,
   missing follow-up, mis-grounded answer)? → `semantic_planner`.
6. Is the eval case spec or judge asking the system to do something it
   cannot or should not do — a factual or policy impossibility, a
   frozen enum the case spec asks to extend, a mis-rubric? →
   `eval_spec`.
7. Is the underlying ask a product / policy decision (domain-specific
   examples in `docs/current/domain_taxonomy.md`) that the runtime
   cannot adjudicate without product sign-off? → `product_policy`.

**Tail rule (judge stability)**: if the same case flips across reruns
of the *same prompt and case spec*, reclassify as `judge_calibration`
regardless of which question above otherwise matched.

**Default tail**: if no question matches cleanly, →
`human_review_required`.

### 3.3 Why no runtime guard by default

Most observed failures look like runtime-guard territory because a
keyword / regex / if-else can paper over the symptom in one PR. The
Constitution's Iteration rule (§1.5) and the forbidden-list (§1.7)
explicitly rule this out for soft semantic decisions: those belong to
the LLM. A new runtime guard is only justified when it protects a
current Tier-0 invariant. If no current Tier-0 covers it,
`human_review_required` is the correct exit — the human decides whether
to open a new Tier-0 or to push the fix back to `prompt_projection` /
`skill_state` / `semantic_planner`.

## 4. Review Agent Anti-Hardcode Prompt

The prompt below is handed to the review agent on any change PR that
touches a semantic surface — prompt, runtime semantic decision, eval
spec, judge calibration, or any new keyword / regex / enum that
influences a routing or escalation decision. Pure infra / docs-only /
config-governance / characterization-test PRs are **exempt**: list the
exemption explicitly in the verdict and return `approve`.

The per-PR verdict set is different from the **sprint-close review
header** used in `docs/codex-findings.md`. Both are spelled out below
so the two are not conflated.

### 4.1 Nine-question anti-hardcode kernel

The canonical copy-pastable prompt lives at
[`../templates/anti_hardcode_kernel.md`](../templates/anti_hardcode_kernel.md).
It contains nine questions, a scope exemption clause, and four possible
verdicts (`approve`, `approve with downgrade-to-signal follow-up`,
`reject as semantic hardcode`, `needs human architecture decision`).

### 4.2 Sprint-close review header (separate convention)

At sprint or milestone close, the review agent writes a sprint-level
decision to the top of `docs/codex-findings.md` using this 4-line
header:

```
## Sprint Review Decision
decision: pass | fix_required | out_of_scope_review
blocking_count: <number>
summary: <one paragraph>
```

The per-PR verdict set in §4.1 and the sprint-close header in §4.2 are
different artefacts. The per-PR verdict reviews a single PR; the
sprint-close header reviews the sprint as a whole and gates closure.

### 4.3 Milestone-shared review (default)

Per the §8 milestone framework: sub-sprints within an active milestone
may share a single review at **milestone close** rather than dispatching
the review agent per sub-sprint. The §4.1 nine-question kernel and the
§4.2 sprint-close header are written once per milestone, against the
cumulative commit range of all sub-sprints in that milestone.

**Per-sub-sprint review remains REQUIRED** when the sub-sprint:

1. Introduces a new Tier-0 candidate (a candidate invariant for
   `docs/current/runtime_invariants.md`) — the review agent must verify
   the candidate at sprint close before the next sub-sprint begins;
2. Crosses a §1.7 forbidden-list red line — the review agent must
   verify the justification at sprint close;
3. Touches a hard-fenced surface that the milestone objective
   explicitly named out of scope;
4. Closes a sub-sprint with a `fix_required` outcome that needs
   per-sub-sprint re-review before the milestone can continue.

For default sub-sprints (semantic-touching but not Tier-0-adjacent, not
§1.7-adjacent, not hard-fence-violating, not fix-iteration on prior
sub-sprint), the review is deferred to milestone close. The
deliver-agent surfaces the per-sub-sprint deferral choice in
`docs/milestone_objective.md` and the dev session records it in each
sub-sprint handoff §11 (the dev does NOT dispatch the review agent
themselves; the deliver-agent + human dispatch at milestone close).

Sub-sprints exempted from the §7 stanza (pure infra, docs-only,
config-governance, characterization-test) remain review-exempt per
§4.1 exemption clause regardless of milestone framing.

### 4.4 Four-parallel review sub-agent orchestration (industry-best-practice default)

When the milestone scope crosses multiple architectural surfaces, the
review agent SHOULD be orchestrated as **four parallel sub-agents**,
each scoped to a specific lens:

| Sub-agent | Lens | Focuses on |
|----------|------|-----------|
| **Bug sub-reviewer** | Correctness | Logic errors, edge cases, missing null checks, race conditions |
| **Security sub-reviewer** | Safety | PII handling, capability boundary violations, injection surfaces, supply-chain risk |
| **Architecture sub-reviewer** | §4.1 kernel | Semantic hardcode detection, layer-ownership violations, §1.7 forbidden patterns |
| **Regression-coverage sub-reviewer** | §5 | target / neighbor / negative / shadow case coverage; bad-case suite touch list |

Each sub-reviewer returns its own verdict. The orchestrator (the parent
review agent) synthesizes them into the §4.2 sprint-close header. A
single `reject` from any sub-reviewer blocks close until addressed.

This pattern is enabled in the compact review prompt template
([`../templates/compact_review_prompt.md`](../templates/compact_review_prompt.md))
and is the default for milestone-shared reviews.

## 5. Eval Acceptance Rules

A sprint or a PR is accepted only when its eval evidence clears every
bar below. This section operationalizes the Constitution's Evaluation
rule (§1.6): a visible pass-rate increase is not enough.

### 5.1 Acceptance bars (framework defaults; consumer specializes)

The framework defines the **shape** of acceptance bars; specific metric
thresholds and lane-specific definitions live in your
`docs/current/eval_acceptance_bars.md`.

Framework-default bars (your project MUST specialize wrong-lane,
over-escalation, and grounding floor in your acceptance bars doc):

- **Target cases pass** — the cases the sprint or PR named as in scope
  must pass.
- **Neighbor cases no regression** — cases that share the failure
  shape or the relevant lane must not regress.
- **Negative-control cases unchanged** — cases designed to *not*
  trigger the new behaviour must not start triggering it (no new false
  positives).
- **Shadow cases no regression** — held-out cases not visible to the
  dev agent. Shadow results are readable only by the human / review
  agent; the dev agent may not consume them during development.
- **Safety floor unchanged** — Tier-0 safety invariants (per
  `docs/current/runtime_invariants.md`) remain green.
- **Grounding floor unchanged** — the grounding-floor metric defined
  in your `docs/current/eval_acceptance_bars.md` remains at or above
  its prior level.
- **Wrong-lane containment rate unchanged or down** — sessions that
  contain the conversation in the wrong workflow lane, the wrong phase,
  or with no grounded answer must not increase (definition in your
  acceptance bars doc).
- **Over-escalation rate unchanged or down** — escalation rate on cases
  that should resolve in-system must not increase (definition in your
  acceptance bars doc).
- **Architecture-health metrics not regressed** — §6 metrics, where
  collected, must not regress.

### 5.2 Baseline pointer

The canonical baseline lives at `docs/current/eval_baseline.md`
(consumer-supplied). Verify the date and the run reference before
treating any specific number as authoritative.

### 5.3 Visible-eval vs shadow

A visible-eval improvement that ships with a shadow regression is a
**fail**, not a pass. The Constitution's "do not optimize visible eval
at the cost of shadow / generalization" forbidden-list line (§1.7) is
enforced here.

### 5.4 No eval-side override of a real bug

An eval-side override — widening the case spec to accept the agent's
actual output, relaxing the rubric, or downgrading a judge — may
**not** be used to mask a genuine agent mistake. The Constitution's
"widening eval spec to accept a genuine agent mistake" forbidden-list
line (§1.7) governs. If the agent's behaviour is wrong, fix the agent;
if the case spec is wrong, fix the case spec and document the override
in the sprint handoff with the layer classification (`eval_spec`) from
§3.

### 5.5 Programmatic composite scores demoted to observation

Programmatic eval composite scores (`mean_composite_score`,
`task_success_rate`, judge-derived dimensions, etc.) are **observations,
not hard close gates**. They continue to be computed and tracked across
sprints, but they no longer block sprint or milestone close.

**Rationale**: programmatic composite scores accumulate confounding
sources that cannot be reliably attributed to sprint-side causes,
including external LLM provider drift, judge calibration variance,
mocked-vs-real-LLM gap, and unvalidated weighting dimensions. Per
Constitution §1.6, such a metric cannot gate sprint close.

**What stays as hard close gate** (unchanged):

- **Review agent §4.1 nine-question anti-hardcode kernel pass** at the
  PR / sprint / milestone level per the §4 dispatch convention.
- **Test suite no new regression** (baseline preservation).
- **Safety floor unchanged** — per §5.1.
- **Grounding floor unchanged** — per §5.1.

**NEW primary gate (per §5.6 below)**: curated bad-case suite manual
review pass.

### 5.6 Curated bad-case suite as primary acceptance gate

The primary acceptance gate is **manual review of the curated bad-case
suite** at `eval/bad_cases/` (path can be customized in your domain
taxonomy). The bad-case suite is a deliver-agent + human curated
directory of case specs derived from:

- Real user / colleague / human sessions that surfaced a multi-layer
  failure;
- Architectural findings from prior sprints;
- Production-readiness regression candidates the human flags as
  load-bearing for the release gate.

Each bad-case spec carries the standard case schema PLUS:

- A `bad_case_metadata` block naming: `source_session_id`,
  `surfaced_by`, `surfaced_date`, `failure_shape` (one-line
  description), `expected_behavior` (human-verified, NOT agent trace
  text).
- A `closure_criterion` field naming the deliver-agent + human-verified
  condition under which this bad case is considered "resolved" —
  typically expressed as observable trace evidence on a sprint or
  milestone rerun.

**Manual review process at sprint or milestone close**:

1. Run the bad-case suite via your project's eval harness (or the
   scope-relevant subset per §5.6.2 below).
2. Deliver-agent + human read the per-case traces.
3. For each bad case, the human (with deliver-agent's assistance)
   judges PASS / FAIL / IMPROVING **qualitatively** against the
   `closure_criterion`. This is a **human-judgment gate**, not a
   programmatic gate — the `closure_criterion` is guidance naming
   observable end-states, but the human reads the trace and decides
   based on overall situation. Programmatic scores are unstable (per
   §5.5) and cannot substitute for human review at this stage.

**Sprint or milestone close decision** is made by the human (with
deliver-agent's recommendation) based on the per-case manual review
results PLUS the other §5.5 hard gates. FAIL on a bad case does not
auto-block close; it triggers a deliver-agent + human conversation
about whether the failure is in-scope for the closing milestone or
surfaces a new R-item for a future milestone.

### 5.6.1 Bad case tiering

Bad cases carry a `tier` field in their `bad_case_metadata`:

- **`core`** — load-bearing across all milestones (touches a
  release-gate-relevant failure mode). Re-run at every milestone close,
  regardless of which milestone is closing.
- **`scope-relevant`** — relevant to a specific architectural surface
  that some milestones touch and others don't. Re-run only at milestone
  closes where the closing milestone's `milestone_objective.md` §5
  explicitly names this bad case in the acceptance bar.
- **`closed-as-regression-guard`** — has met its closure criterion in
  N ≥ 2 consecutive milestone closes (see §5.6.3 downgrade rule). Stays
  in the suite; runs automatically; if terminal_outcome returns to FAIL
  on a future run, the case auto-promotes back to active and triggers
  deliver-agent attention. No human manual review required while in
  this state unless the auto-detection fires.
- **`archived`** — the underlying failure surface has been structurally
  removed; the case can no longer manifest. Removed from active runs
  but kept in the directory as history. Requires deliver-agent + human
  joint decision documented in `eval/bad_cases/_manifest.md` lifecycle
  ledger.

### 5.6.2 Per-milestone bad case selection

At milestone planning, the deliver-agent picks which bad cases the
closing milestone is expected to address:

- `core` cases: always run at the close (no opt-out at milestone
  planning).
- `scope-relevant` cases: named in `milestone_objective.md` §5
  acceptance bar if the milestone's scope touches the relevant surface.
  The deliver-agent SHALL list the named cases verbatim in the
  milestone objective.
- `closed-as-regression-guard` cases: run automatically; no scope
  decision required.

A bad case the closing milestone does NOT touch is NOT re-run at that
close (saves manual review time). The deliver-agent + human revisit at
the next planning round.

### 5.6.3 Bad case lifecycle downgrade

A bad case downgrades from `active` (or `scope-relevant`) to
`closed-as-regression-guard` when:

- The case has been judged PASS (per §5.6 manual review) by the human
  in **N ≥ 2 consecutive milestone closes** (deliver-agent + human
  jointly confirm at each close).
- The deliver-agent + human jointly agree at a milestone close to apply
  the downgrade (this is a planning-round decision, not automatic on
  the N=2 trigger).

Downgraded cases stay in the suite as regression guards. They run
automatically; auto-detection of FAIL via terminal_outcome or
composite_score collapse re-promotes them to `active` and triggers
deliver-agent attention.

A case never automatically removes itself from the suite; `archived`
requires explicit deliver-agent + human joint decision documented in
`eval/bad_cases/_manifest.md`.

**Bad case lifecycle**:

- **Opened** when a real session or sprint-derived finding surfaces a
  failure the deliver-agent + human agree is load-bearing.
- **Active** while the failure persists. Each milestone close records
  per-case status (PASS / FAIL / IMPROVING).
- **Closed** when the failure no longer manifests on a milestone rerun
  and the deliver-agent + human jointly confirm at milestone close.
  Closed bad cases stay in the directory as regression guards.

The bad-case suite directory is governance-tracked (per
[`doc_governance.md`](doc_governance.md) front matter equivalent); see
`eval/bad_cases/_manifest.md` for the lifecycle ledger.

**Eval evidence gate**: mocked-LLM tests cannot be primary evidence
that a prompt change caused a behaviour change — the mock controls the
measured variable. Real-LLM rerun is the eval evidence gate; mocked-LLM
tests cover projection / rendering / dispatch wiring only.

## 6. Architecture-Health Metrics (definitions only)

These four metrics are defined here and are referenced by §5's
acceptance bars. Collection is project-specific; the framework provides
definitions only.

| metric | definition | unit | observation cadence |
| --- | --- | --- | --- |
| `new_semantic_hardcode_count` | Number of new keyword / regex / if-else / enum entries added to runtime or prompt for a semantic decision in a PR | count per PR | per PR |
| `soft_signal_conversion_count` | Number of existing semantic hardcodes downgraded to LLM-projected soft signals | count per sprint | per sprint close |
| `planner_ownership_ratio` | Fraction of semantic decisions in the runtime owned by LLM planning vs runtime guard / regex | percentage | per sprint close (manual count acceptable early) |
| `shadow_disagreement_rate` | Fraction of shadow cases where LLM decision disagrees with the human-labelled expected behaviour | percentage | per shadow run |

The direction of health is: `new_semantic_hardcode_count` down,
`soft_signal_conversion_count` up, `planner_ownership_ratio` up,
`shadow_disagreement_rate` down.

## 7. Required sprint-objective stanza for semantic-touching sprints

A **semantic-touching sprint** is any sprint that changes prompt, a
runtime semantic decision (lane routing, shift detection, escalation
posture, follow-up policy), the eval spec, or judge calibration. Pure
infra, docs-only, config-governance, and characterization-test sprints
are **exempt** and need not include the stanza.

Semantic-touching sprints **must** include the stanza below in
`docs/sprint_objective.md`. The review agent checks for it as part of
the scope check. A JSON schema for programmatic validation is at
[`../schemas/sprint_stanza.schema.json`](../schemas/sprint_stanza.schema.json);
a validator script is at
[`../tools/stanza_validator.py`](../tools/stanza_validator.py).

### 7.1 Stanza template

```markdown
## Layer-classification + anti-hardcode stanza

**Target failure layer:** <one of: infra | runtime_guard |
prompt_projection | skill_state | semantic_planner | eval_spec |
product_policy | judge_calibration | human_review_required>

**Tier-0 invariant:** <"This sprint adds no Tier-0 invariant." OR
pointer to the Tier-0 invariant being protected in
`docs/current/runtime_invariants.md` §X.X>

**Semantic hardcode:** <"No semantic hardcode introduced." OR
"Introduces <named hardcode>; justification: <reason>; sunset plan:
<downgrade-to-signal trigger + target sprint id>">

**Generalization coverage:** <"target / neighbor / negative / shadow
case counts: <T>/<N>/<G>/<S>" OR "case family not yet built; deferred
to <case-family sprint id>">
```

Each field has one acceptable form. A sprint that cannot fill one of
the four fields without a stretch is a sprint that has not yet decided
what it is doing; it should be re-scoped before the dev agent runs.

### 7.2 Worked example (generic — replace with domain-specific in your project)

A hypothetical sprint fixes a workflow-lane mis-classification bug
where the agent stamps the wrong lane through a topic shift. The
failure brief (see §2) hypothesized the bug lives in `prompt_projection`
(the LLM did not see an alternate-lane signal). The sprint takes the
fix:

```markdown
## Layer-classification + anti-hardcode stanza

**Target failure layer:** prompt_projection

**Tier-0 invariant:** This sprint adds no Tier-0 invariant. The
Constitution's context-shift bullet (§1.3 LLM owns) governs the
behaviour the projection enables; the projection itself sits inside
the Runtime's "trace and eval contract" responsibility (§1.4).

**Semantic hardcode:** No semantic hardcode introduced. The new
`alternate_candidate_lanes` projected slot is a soft signal — a list
of lanes the existing classifier already surfaces — exposed to the
LLM through the per-turn projection. The LLM owns whether to act on
it. No new keyword, regex, or per-lane matrix is added to the runtime
shift detector or the prompt.

**Generalization coverage:** target = lane-A↔lane-C drift (the case
the failure brief described). Neighbor = lane-A↔lane-D, lane-A↔lane-F
drift on the same projection. Negative = lane-A single-issue follow-up
that should stay in lane-A (no false positive on the soft signal).
Shadow = held-out lane-A↔lane-C and lane-A↔lane-D drift traces, not
visible to the dev agent. Counts: 1 / 2 / 1 / 4.
```

A future deliver agent should be able to paste this template into a
new `docs/sprint_objective.md` and fill the four fields without further
interpretation. If filling a field requires guessing intent, the sprint
is not ready to start.

**Multi-layer prospective variant**: investigation + bundle-or-defer
sprints span multiple candidate layers; §7 stanza is per-decision-outcome
multi-layer prospective (enumerate possible §3.2 layers per case).
Bundle policy must live in sprint_objective so the review agent can
verify scope discipline.

## 8. Milestone framework

This section introduces the **milestone framework** that groups
sub-sprints into architectural themes. The framework is additive on
top of the existing sprint + governance structure; it does NOT replace
sprints, the §7 stanza, or any §1 constitutional rule.

### 8.1 Definition

A **milestone** is a coordinated bundle of 3–5 sub-sprints sharing a
single architectural theme. Each milestone has:

- **One milestone objective document** at `docs/milestone_objective.md`
  (active milestone; archived to `docs/milestones/M<N>_objective.md`
  at milestone close).
- **One or more sub-sprint contracts** at `docs/sprint_objective.md`
  (active sub-sprint; archived to `docs/sprints/sprint-NNN-objective.md`
  at sub-sprint close per existing convention).
- **One milestone acceptance bar** derived from the curated bad-case
  suite per §5.6 — typically a named bad case must close or improve
  materially.
- **Review at milestone close** per §4.3 (sub-sprints share one review
  unless a per-sub-sprint trigger fires).

A **sub-sprint** within a milestone is a single dev-session unit of
work that ships a coherent slice of the milestone scope. Each
sub-sprint:

- Still has its own §7 stanza if semantic-touching.
- Still produces a `docs/sprints/sprint-NNN-handoff.md` dev-authored
  archive at sub-sprint close.
- Still flips relevant R-items in `docs/action_bank.md` per existing
  convention.
- Defers review to milestone close per §4.3 default (unless a §4.3
  per-sub-sprint trigger fires).

### 8.2 Why milestones (vs single-feature sprints)

Milestone-grained planning cuts deliver-agent and review-agent overhead
by bundling 3–5 related sub-sprints under one planning round and one
close review, while preserving §1.7 anti-hardcode discipline (each
sub-sprint still fills the §7 stanza; review verifies at milestone
close). The framework changes cadence, not architecture.

### 8.3 Milestone objective document schema

`docs/milestone_objective.md` carries:

```yaml
---
title: Milestone M<N> — <name>
doc_tier: current-runtime
status: current
implementation_status: not_started | partial | implemented
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: per milestone
notes: >
  free-form context (scope rationale, hard-fenced surfaces, why this
  is one milestone not split across two).
---
```

Body sections (analogous to `sprint_objective.md` shape):

1. **Milestone class** (semantic-touching layer breakdown across
   sub-sprints; §7 stanza coverage at the milestone level).
2. **Goal** — the architectural outcome the milestone targets,
   expressed as user-facing or bad-case-suite-anchored behaviour change
   (not as code paths).
3. **Sub-sprint sequence** — preliminary list of 3-5 sub-sprints with
   class, layer, scope (3 sentences each), and dependency relationships.
   Deliver-agent + human may refine at each sub-sprint planning round;
   the milestone objective is updated in-place.
4. **Non-goals** (explicit; what the milestone does NOT cover, including
   which bad-case dimensions are deferred to later milestones).
5. **Milestone acceptance bar** — one or more bad cases (per §5.6) that
   the milestone is expected to close or improve; per-bad-case closure
   criterion.
6. **Hard fences** at the milestone level (no edits to existing case
   families per cascade fence; no Tier-0 invention without human review;
   etc.).
7. **R-items consumed / surfaced** — which `action_bank.md` R-items the
   milestone is expected to consume; which new R-items the deliver-agent
   expects to surface.
8. **Review plan** per §4.3 — default milestone-shared OR per-sub-sprint
   triggers expected.
9. **Estimated milestone duration** (calendar weeks) — informational,
   not a gate.

### 8.4 Milestone close artefacts (deliver-agent owned)

At milestone close, the deliver-agent + human produce:

- Update `docs/milestone_objective.md` closure verdict (analogous to
  sprint handoff §12 — pass / fix_required / out-of-scope-review +
  classification + per-sub-sprint disposition).
- Archive the milestone objective to `docs/milestones/M<N>_objective.md`.
- Append a "Closed milestone index" row to `docs/action_bank.md`
  (alongside the existing closed-action index).
- Refresh `docs/10-handoff.md` §0 table + §1 lead (demote current
  milestone to Preceding milestone; truncate §1 content older than the
  preceding milestone per `doc_governance.md` retention rule; add row
  to §2 archive index).
- Reset `docs/sprint_objective.md` to the first sub-sprint of the next
  milestone (or to a planning placeholder if no next milestone is
  locked).
- Optionally start a new `docs/milestone_objective.md` for the next
  milestone.

### 8.5 When to break milestone framing

The framework is not mandatory. A single high-risk feature may be its
own "milestone of one sub-sprint" if that better matches the scope
discipline. The deliver-agent + human decide at planning round.

A milestone that exceeds 5 sub-sprints is a signal that the milestone
scope is too large; the deliver-agent SHALL split it at the next
milestone planning round.

A sub-sprint that crosses an unrelated architectural surface is a
signal that the sub-sprint belongs to a different milestone; the
deliver-agent SHALL surface this at sub-sprint planning round rather
than smuggle the scope across milestones.

### 8.6 Sprint vs milestone vs R-item relationship

```
docs/action_bank.md  (backlog, cross-milestone persistent;
                     R-items flow in from research / bad cases /
                     sprint findings, flow out on close)
       ↓ (deliver-agent picks 3-5 related R-items into a milestone)
docs/milestone_objective.md  (current milestone north star;
                              names sub-sprints + acceptance bar;
                              archived to docs/milestones/M<N>_*.md
                              at close)
       ↓ (deliver-agent picks one sub-sprint contract from milestone)
docs/sprint_objective.md  (current sub-sprint dev/review contract;
                           archived to docs/sprints/sprint-NNN-objective.md
                           at sub-sprint close)
```

R-items are the persistent backlog. Milestones are the planning horizon.
Sub-sprints are the execution unit. The dev session consumes the
sub-sprint contract; the review session consumes either the sub-sprint
or the milestone (per §4.3); the deliver-agent + human consume all
three layers.

### 8.7 Adoption notes

A new project (greenfield) can start with the milestone framework
immediately or with milestone-of-one until scope size warrants
bundling. An existing project (brownfield) adopting `aidazi` should
NOT retroactively relabel past sprints as milestones; the framework
applies prospectively from adoption onward.

**Commit-at-end bundling**: in commit-at-end workflows, dev working
trees accumulate uncommitted deliver-agent-owned files. Dev should
stage only authorized-scope files (not `git add -A`); deliver-agent
files are bundled by human at close commit. See the pre-commit hook at
[`../tools/precommit_bundling_check.sh`](../tools/precommit_bundling_check.sh)
for automated enforcement.

## 9. Agent prompt artifact rules

This section codifies the **self-containment invariant** for the
prompt files that the deliver-agent produces for dev and review agents.
The invariant exists so that a fresh dev or review session can be
started by pasting a single prompt file into a new session, without
that session having to read any further repo doc (other than `AGENTS.md`
governance chain, which is auto-loaded).

### 9.1 Invariant

A **prompt artifact** (`compact/sprint-NNN-dev-prompt.md` for dev,
`compact/M<N>-review-prompt.md` for review) is a **self-contained
executable view** of its source-of-truth contract:

- Dev prompt source-of-truth = `docs/sprint_objective.md`
- Review prompt source-of-truth = `docs/milestone_objective.md` + the
  per-sub-sprint objective archives + the per-sub-sprint dev handoffs

**Self-contained** means: a fresh dev / review session, given ONLY
this prompt file (plus `AGENTS.md` governance chain, auto-loaded), has
every piece of information it needs to:

- understand its role and the bounded scope of the session;
- execute the contract end-to-end (write code / run tests / author
  handoff for dev; walk §4.1 kernel + verify scope discipline + produce
  `docs/codex-findings.md` for review);
- self-check that the work is complete before claiming so.

The prompt MUST embed (not reference) all contract content. The single
exception is artefacts that the prompt's consumer is expected to
produce (e.g., per-sub-sprint dev handoff is consumed by review but
produced by dev; review prompt references handoff paths but cannot
embed handoff content because it does not yet exist at prompt-authoring
time).

### 9.2 Embed vs reference rules

| Content | Embed in prompt | Reference only |
|---|---|---|
| Role identity, goal, scope, hard fences, test/eval requirements, §7 stanza, handoff requirements, commit discipline | ✓ | |
| §4.1 nine-question kernel (in review prompt) | ✓ | |
| Sub-sprint cumulative scope claim (in review prompt) | ✓ | |
| Governance chain (Constitution, doc_governance, context_briefing) | — | Via AGENTS.md (auto-loaded) |
| Per-sub-sprint dev handoff (in review prompt) | — | Path reference only (dev produces these AFTER review prompt is authored) |
| Code anchors (specific file:line references the agent needs to read or modify) | — | Path reference (the agent reads them on demand during work) |
| Research-agent solutions in `docs/solutions/` | — | Reference if needed; do NOT embed (proposal-tier, may be out of date relative to milestone scope decisions) |

### 9.3 Source-of-truth synchronization

`docs/sprint_objective.md` is the canonical sub-sprint contract that
the human reviews and approves. `compact/sprint-NNN-dev-prompt.md` is
its self-contained executable view. The same relationship holds between
`docs/milestone_objective.md` and `compact/M<N>-review-prompt.md`.

**Synchronization rules**:

1. The deliver-agent generates objective.md and prompt.md **in one
   pass** (objective first, then prompt as embedded view). Both are
   surfaced for human review together.
2. If the human modifies objective.md during review, the deliver-agent
   regenerates prompt.md from the modified objective before dispatch
   to dev / review.
3. If, during a sub-sprint or milestone, the contract changes (e.g.,
   scope adjustment from STOP-and-surface or in-flight downgrade),
   both objective.md and prompt.md are updated together; the
   modification cadence is "objective first, prompt regenerated."
4. At sub-sprint close, the deliver-agent archives the objective.md to
   `docs/sprints/sprint-NNN-objective.md` per §8.3. The prompt.md file
   at `compact/sprint-NNN-dev-prompt.md` stays in place as the
   historical executable view; it is NOT re-archived elsewhere unless
   the deliver-agent explicitly decides to compress `compact/` at a
   future milestone.

### 9.4 Exemptions

The self-containment invariant is **not required** for:

- The research-agent's `docs/solutions/<name>.md` proposal artefact —
  it is a human-facing proposal, not an agent-execution prompt.
- The deliver-agent's own activation template
  `framework/role-cards/deliver-activation.md` — it is intentionally
  minimal and points to `framework/role-cards/deliver-agent.md` for
  full role definition.
- Cross-session continuity scaffolding in `docs/10-handoff.md` — it is
  structurally a session-handoff log, not an executable prompt.

### 9.5 Auto-loop readiness

The self-containment invariant is a prerequisite for an auto-evolution
/ auto-loop direction: a meta-agent driving sub-sprint iterations
needs self-contained prompt artefacts so that each spawned dev / review
session is a deterministic executable unit. The §9.3 synchronization
rule ensures the meta-agent can rely on prompt.md being authoritative
without needing to cross-check objective.md at session-spawn time.
