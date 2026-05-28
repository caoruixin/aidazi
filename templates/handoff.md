---
title: Sub-sprint NNN — handoff
doc_tier: sprint-archive
status: current
implementation_status: implemented
source_of_truth: this file
authored_by: dev-agent
authored_date: <YYYY-MM-DD>
notes: >
  Dev-authored sub-sprint handoff. Sections §1–§11 are dev-filled;
  §12 (verdict) is deliver-agent + human at close. After close, this
  file is archived (immutable per `doc_governance.md` sprint-archive
  tier).
---

# Sub-sprint NNN — handoff

**Parent milestone**: M<N> — <name>

**Closed sub-sprint contract**: `docs/sprints/sprint-NNN-objective.md`

## §1. Sub-sprint summary

<One paragraph: what shipped. Reference the goal from sprint_objective.md
§2 and confirm or restate.>

## §2. Scope completion table

| Scope # | Step name | Status | Evidence |
|---------|-----------|--------|----------|
| 1 | <step 1 name> | done | <commit hash + file:line, or test name> |
| 2 | <step 2 name> | partial | <reason + what's missing> |
| 3 | <step 3 name> | done | <commit hash + file:line> |
| ... | ... | ... | ... |

## §3. Layer classification verification

The §7 stanza in sprint_objective.md targeted layer `<X>`. After
implementation:

- **Held**: <yes / no>
- **If no, actual layer encountered**: <Y> — <one line on what
  surfaced>
- **STOP-and-surface fired**: <yes / no — if yes, when and how
  resolved>

## §4. Tests run

- **Test suite**: <baseline result; new tests added; regression check>
- **Mocked-LLM tests added**: <list new test names + intent>
- **Test command + exit code**: `<command>` → <pass / fail>

## §5. Eval evidence (semantic sub-sprints only)

If `sprint_objective.md` §1 marked sub-sprint as semantic-touching:

- **Real-LLM rerun conducted**: <yes / no>
- **Cases run**: <target / neighbor / negative case ids>
- **Result**: <pass / regression — per case>
- **Shadow cases**: held-out; reported separately to human/review (NOT
  visible to me)

If not semantic, write "N/A — non-semantic sub-sprint".

## §6. Bad-case suite touch

| Bad case id | Touched? | Trace observation |
|-------------|----------|-------------------|
| `<id_1>` | yes | <one line on what changed> |
| `<id_2>` | no — out of scope | — |

## §7. §7 stanza self-check (post-implementation)

Re-validate the four fields from sprint_objective.md §6:

```markdown
**Target failure layer:** <unchanged | adjusted to <Y> because <reason>>
**Tier-0 invariant:** <unchanged | new Tier-0 candidate flagged for
review>
**Semantic hardcode:** <unchanged | acknowledge new hardcode + sunset
plan>
**Generalization coverage:** <actual T/N/G/S counts post-eval>
```

## §8. Trace pointer

- **trace.jsonl path**: `docs/sprints/sprint-NNN/trace.jsonl`
- **Notable trace events**: <e.g., Context Pack Prompt invocation,
  STOP-and-surface event, alternative-choice decision>

## §9. Surfaced findings (out of scope)

Findings I discovered but did not act on (out of scope per
sprint_objective.md §4 fences):

- **<Finding 1>**: <one paragraph; suggested R-item id; suggested layer>
- **<Finding 2>**: <...>

These are candidates for deliver-agent to open as R-items in
`docs/action_bank.md`.

## §10. Hard-fence events

- **Fence breaches attempted**: <none / list with reason>
- **STOP-and-surface events**: <none / list with how-resolved>

## §11. Commit discipline

- **Files staged**: <list, or "all in scope per sprint_objective.md
  §3">
- **Files NOT staged but modified**: <none / list with reason — e.g.,
  deliver-agent owned files modified in error>
- **Bundling events**: <none / "deliver-agent files bundled in commit
  <hash>; flagged for re-flip">

## §12. Verdict (LEAVE EMPTY — deliver-agent + human at close)

> This section is filled by the deliver-agent + human at sub-sprint
> close per `framework/role-cards/deliver-agent.md` close taxonomy.
> Possible verdicts:
> - A. Clean PASS
> - A-with-packaging-note (clean pass + bundling event)
> - A-with-Codex-skipped (exempt sub-sprint)
> - B. Fix-required (spawn fix-iteration sub-sprint)
> - C. Out-of-scope-review (push back to review agent)
> - D. Convergence failure (human review required)
