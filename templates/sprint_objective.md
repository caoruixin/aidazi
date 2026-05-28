---
title: Sub-sprint NNN — <name>
doc_tier: current-runtime
status: current
implementation_status: not_started
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: per sprint
notes: >
  Active sub-sprint contract. Archive to `docs/sprints/sprint-NNN-objective.md`
  at sub-sprint close.
---

# Sub-sprint NNN — <name>

**Parent milestone**: M<N> — <name> (`docs/milestone_objective.md`)

## 1. Class

- **Semantic-touching**: <yes / no>
- **§7 stanza REQUIRED**: <yes / no — if no, name exemption>
- **Target layer (§3.2)**: <one of: infra | runtime_guard |
  prompt_projection | skill_state | semantic_planner | eval_spec |
  product_policy | judge_calibration | human_review_required>

## 2. Goal

<One-paragraph statement of what this sub-sprint ships. User-facing
or trace-observable behaviour change. NOT code paths.>

## 3. Scope

Numbered steps. Each step is a unit of dev work.

1. **<Step 1 name>** — <what is done; file:line anchors where
   helpful>
2. **<Step 2 name>** — <...>
3. **<Step 3 name>** — <...>
4. **<Step 4 name>** — <...> (max 5–7 steps per sub-sprint)

## 4. Hard fences / STOP conditions

Explicit boundaries. Cross them → STOP and surface to deliver-agent.

- <fence 1, e.g., "Do NOT edit `docs/sprints/*` or `docs/archive/*`">
- <fence 2, e.g., "<specific module> is out of scope">
- <fence 3, e.g., "Do NOT add a keyword/regex/if-else for the lane
  decision (per §1.7); use projection per Step #N">
- **STOP-and-surface**: if you discover the bug actually lives in a
  layer other than §1.Target layer, STOP and tell deliver-agent.

## 5. Test / eval requirements

- **Test suite**: <which test suite(s) to run; baseline preservation
  required>
- **Mocked-LLM tests**: <which projection / dispatch / rendering tests
  to add — these cover wiring, NOT semantic behaviour>
- **Real-LLM rerun**: <REQUIRED if semantic-touching | NOT REQUIRED>
  - Cases: <target / neighbor / negative case ids>
  - Shadow cases: <held-out case ids — readable only by human/review>
- **Bad-case suite touch**: <list bad cases this sub-sprint is expected
  to touch>
- **Eval evidence gate** (per §5.6): mocked-LLM tests cannot be primary
  evidence for semantic behaviour change.

## 6. §7 stanza (REQUIRED if §1 is semantic-touching)

```markdown
## Layer-classification + anti-hardcode stanza

**Target failure layer:** <layer per §3.1>

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

Validate using `framework/tools/stanza_validator.py` before dispatch.

## 7. Review plan (per §4.3)

- **Default**: deferred to milestone close (§4.3 default).
- **OR** Per-sub-sprint review triggered because:
  - [ ] Introduces a new Tier-0 candidate
  - [ ] Crosses a §1.7 forbidden-list red line
  - [ ] Touches a hard-fenced surface
  - [ ] Closes with a `fix_required` outcome needing re-review

## 8. Handoff requirements

The dev agent SHALL author `docs/sprints/sprint-NNN-handoff.md` using
the template at `framework/templates/handoff.md`. Sections §1–§11 are
dev-filled; §12 (verdict) is deliver-agent + human at close.

## 9. Commit discipline

- Stage only files in your authorized scope (do NOT `git add -A`).
- Pre-commit hook at `framework/tools/precommit_bundling_check.sh`
  enforces this.
- If deliver-agent owned files accidentally bundled, document in
  handoff §11.

## 10. Self-check checklist

Before claiming sub-sprint complete, dev verifies:

- [ ] All scope items have status `done` or explicit `partial` with
      reason.
- [ ] Test suite baseline preserved.
- [ ] §6 stanza fields accurate post-implementation.
- [ ] Real-LLM rerun conducted (if semantic).
- [ ] Bad-case suite touch list complete.
- [ ] No hard-fence breaches without surfaced findings.
- [ ] `trace.jsonl` written via `framework/tools/trace_emitter.py`.
- [ ] Handoff §1–§11 filled; §12 left empty.
- [ ] Commit discipline followed.
