---
title: Review findings (live file)
doc_tier: current-runtime
status: current
source_of_truth: this file
notes: >
  Live findings file the review agent writes at milestone close (or
  per-sub-sprint when §4.3 triggers). Archived to
  `docs/milestones/M<N>_codex-review.md` at milestone close;
  resets to scaffold (this template) for the next milestone.
  Sprint-level archives go to
  `docs/sprints/sprint-NNN-codex-review.md` when per-sub-sprint
  review was dispatched.

  This template uses the name "Codex" historically for the review
  agent's archive file. You may rename to e.g. `review-findings.md`
  in your consumer project if your review tool stack differs;
  references in `framework/governance/constitution.md` §4.2 and
  `framework/role-cards/deliver-agent.md` use the generic name
  `docs/codex-findings.md` — adjust to your chosen filename.
---

# Review findings

## Sprint Review Decision

```
decision: pass | fix_required | out_of_scope_review
blocking_count: <number>
summary: <one paragraph>
```

## Scope of this review

- **Milestone (or sub-sprint)**: M<N> — <name>
- **Cumulative commit range**: `<base>..<head>`
- **Sub-sprints covered** (if milestone close): S1, S2, ..., S<N>
- **Per-sub-sprint handoffs read**:
  - `docs/sprints/sprint-NNN-1-handoff.md`
  - `docs/sprints/sprint-NNN-2-handoff.md`
  - ...

## Per-sub-reviewer summary (if 4-parallel orchestration per §4.4)

- **Bug sub-reviewer**: approve | fix_required | reject — <one line>
- **Security sub-reviewer**: approve | fix_required | reject — <one line>
- **Architecture sub-reviewer**: approve | fix_required | reject — <one line>
- **Regression-coverage sub-reviewer**: approve | fix_required | reject — <one line>

## Per-PR verdicts (per §4.1)

For each PR / commit in scope:

### Commit <hash> — <one-line description>

- **Verdict**: approve | approve with downgrade-to-signal follow-up |
  reject as semantic hardcode | needs human architecture decision
- **§4.1 questions walked**:
  - Q1 (keyword/regex/if-else/enum/per-domain matrix): <yes/no + diff
    snippet if yes>
  - Q2 (Tier-0 invariant justification): <yes/no + Tier-0 pointer>
  - Q3 (could be soft signal): <yes/no + analysis>
  - Q4 (eval-text encoding): <yes/no>
  - Q5 (LLM ownership shrinkage): <yes/no>
  - Q6 (if-else block in prompt): <yes/no>
  - Q7 (schema / capability / safety / grounding preserved): <yes/no>
  - Q8 (generalization eval coverage T/N/G/S): <yes/no + counts>
  - Q9 (sunset plan if temporary): <yes/no + trigger>
- **Recommended layer (§3) if reject**: <layer + one line>

(repeat for each commit)

## Findings by sub-reviewer

### Bug findings

- **[P0/P1/P2]** `<file:line>` — <observation> — <recommended layer
  per §3 + one-line fix direction>

### Security findings

- **[P0/P1/P2]** `<file:line>` — <observation> — <recommended layer>

### Architecture findings (§4.1 kernel)

- **[P0/P1/P2]** <observation> — <which question failed; suggested
  fix layer or sunset trigger>

### Regression-coverage findings

- **[P0/P1/P2]** <observation> — <missing case family; missing shadow
  coverage; eval-spec override audit>

## Scope discipline check

- **Cumulative diff matches milestone scope**: <yes / no>
- **If no**: <which surface was touched beyond contract; review-agent
  recommendation: deliver-agent classifies as C. Out-of-scope-review>

## Hard gate status

- [ ] §4.1 nine-question kernel pass (per-PR)
- [ ] No reject from any of 4 sub-reviewers (block-on-any-reject rule)
- [ ] Test suite no new regression
- [ ] Safety floor unchanged
- [ ] Grounding floor unchanged
- [ ] (curated bad-case suite manual review is conducted by deliver
      + human, NOT by this review agent)

## Notes for deliver-agent + human at close

- <Observations the review agent surfaces but does not act on>
- <Recommended R-items to open>
- <Scope-expansion candidates to defer>
