---
title: Milestone M<N> — <name>
doc_tier: current-runtime
status: current
implementation_status: not_started
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: per milestone
notes: >
  Scope rationale, hard-fenced surfaces, why this is one milestone
  not split across two. Use this template for `docs/milestone_objective.md`
  in your consumer project. Archive to `docs/milestones/M<N>_objective.md`
  at milestone close.
---

# Milestone M<N> — <name>

## 1. Milestone class

Layer breakdown across sub-sprints (per `framework/governance/constitution.md`
§3.1):

- Sub-sprint S1: <layer> — <one line>
- Sub-sprint S2: <layer> — <one line>
- ...

§7 stanza coverage at milestone level (per `constitution.md` §7):

- **REQUIRED** sub-sprints: <list>
- **EXEMPT** sub-sprints: <list> (reason: pure infra / docs-only /
  config-governance / characterization-test)

## 2. Goal

<The architectural outcome this milestone targets, expressed as
user-facing or bad-case-suite-anchored behaviour change (not as code
paths). 2–4 sentences.>

## 3. Sub-sprint sequence

Preliminary list of 3–5 sub-sprints. Deliver-agent + human may refine
at each sub-sprint planning round; this milestone objective is updated
in-place.

### S1 — <name>

- **Class**: <semantic-touching | infra-only | docs-only | ...>
- **Target layer (§3.2)**: <layer>
- **Scope (3 sentences max)**: <what S1 changes>
- **Depends on**: <none | M<N-1> S<X> close | external>
- **§4.3 review trigger fired**: <no | yes — reason>

### S2 — <name>

(same shape as S1)

### S3 — <name>

(same shape as S1)

### S4 — <name> (optional)

(same shape as S1)

### S5 — <name> (optional)

(same shape as S1)

## 4. Non-goals

Explicit; what this milestone does NOT cover, including which
bad-case dimensions are deferred to later milestones.

- <non-goal 1>
- <non-goal 2>
- ...

## 5. Milestone acceptance bar

One or more bad cases (per `constitution.md` §5.6) that this milestone
is expected to close or improve materially. Plus the §5.1 framework-
default bars.

### Bad cases (named per §5.6.2)

- `eval/bad_cases/<case_id_1>.yaml` — closure criterion: <one line>
- `eval/bad_cases/<case_id_2>.yaml` — closure criterion: <one line>

### Framework-default acceptance bars (per §5.1)

- Target cases pass.
- Neighbor cases no regression.
- Negative-control cases unchanged.
- Shadow cases no regression.
- Safety floor unchanged.
- Grounding floor unchanged.
- Wrong-lane containment rate unchanged or down.
- Over-escalation rate unchanged or down.
- Architecture-health metrics (§6) not regressed.

## 6. Hard fences

Milestone-level hard fences. Each sub-sprint may add its own
sub-sprint-level fences in its `sprint_objective.md`.

- <fence 1, e.g., "No edits to existing case families per cascade fence">
- <fence 2, e.g., "No Tier-0 invention without human review">
- <fence 3, e.g., "<specific module> is out of scope for this milestone">

## 7. R-items consumed / surfaced

- **Consumed**: R-<id>, R-<id> from `docs/action_bank.md`
- **Expected to surface**: <new R-item candidates the deliver-agent
  expects to open during this milestone>

## 8. Review plan (per §4.3)

- **Default**: milestone-shared review at milestone close.
- **Per-sub-sprint triggers expected**:
  - S<X>: <trigger condition + reason>
  - (others: no trigger expected)

## 9. Estimated milestone duration

<N weeks> (informational, not a gate).

---

## Closure verdict (FILLED AT MILESTONE CLOSE BY DELIVER-AGENT + HUMAN)

- **Close date**: <YYYY-MM-DD>
- **Verdict**: <A. Clean PASS | B. Fix-required | C. Out-of-scope-review | D. Convergence failure>
- **Per-sub-sprint disposition**:
  - S1: <close label + 1 line>
  - S2: <close label + 1 line>
  - ...
- **Bad-case suite manual review result** (per §5.6):
  - `<case_id_1>`: PASS / FAIL / IMPROVING — <human's qualitative note>
  - `<case_id_2>`: PASS / FAIL / IMPROVING — <human's qualitative note>
- **Hard gate status**:
  - [ ] Codex §4.1 nine-question kernel pass
  - [ ] Test suite no new regression
  - [ ] Safety floor unchanged
  - [ ] Grounding floor unchanged
  - [ ] Curated bad-case suite manual review pass
- **R-items closed**: <list>
- **R-items surfaced for next milestone**: <list>
- **Next milestone candidate**: <name | TBD>
