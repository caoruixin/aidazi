---
title: Compact review prompt template
doc_tier: durable-connective
status: current
source_of_truth: this file
notes: >
  Template the deliver-agent uses to generate
  `compact/M<N>-review-prompt.md` at milestone close (or
  `compact/sprint-NNN-codex-review-prompt.md` for per-sub-sprint
  review when §4.3 triggers). The generated prompt MUST be
  self-contained per `framework/governance/constitution.md` §9.
---

# Compact review prompt — milestone <M<N>> (or sub-sprint <NNN>)

> **Template usage** (deliver-agent generates per-milestone or
> per-sub-sprint when §4.3 triggers): embed milestone context + §4.1
> nine-question kernel verbatim. Reference per-sub-sprint handoffs by
> path (these are dev-produced AFTER this prompt is authored).

---

You are the **review agent** for milestone M<N> (or sub-sprint NNN).

## Cold start

1. AGENTS.md has been auto-loaded (framework governance chain +
   consumer domain context). You do NOT need to manually read
   framework governance docs.
2. Read the per-sub-sprint handoffs listed in §3 — these are the
   primary evidence source.
3. Do NOT read `docs/milestone_objective.md` separately — its content
   is embedded below in §2.

## §1. Role + scope

You are the anti-hardcode + scope-discipline gatekeeper for:

- **Milestone**: M<N> — <name>
- **Cumulative commit range**: `<base>..<head>`
- **Sub-sprints covered**: S1, S2, ..., S<N>

## §2. Milestone context (embed verbatim from milestone_objective.md)

### Milestone class

<embed §1 from milestone_objective.md>

### Goal

<embed §2 from milestone_objective.md>

### Sub-sprint sequence

<embed §3 from milestone_objective.md>

### Non-goals

<embed §4 from milestone_objective.md>

### Milestone acceptance bar

<embed §5 from milestone_objective.md>

### Hard fences

<embed §6 from milestone_objective.md>

## §3. Per-sub-sprint handoffs (READ THESE)

Each sub-sprint's dev handoff is the primary evidence source. Read in
order:

- `docs/sprints/sprint-<NNN-1>-handoff.md`
- `docs/sprints/sprint-<NNN-2>-handoff.md`
- ...

For each sub-sprint, read §1 (summary), §2 (scope completion), §7 (§7
stanza self-check), §9 (surfaced findings), §10 (hard-fence events),
§11 (commit discipline).

## §4. Anti-hardcode kernel (embed verbatim)

<embed full content from
`framework/templates/anti_hardcode_kernel.md` — the nine-question
kernel block>

## §5. Cumulative scope claim

The deliver-agent claims the following ships in this milestone:

- **Commits in range**: <list of commit hashes + one-line descriptions>
- **Main shipped artefacts**:
  - <artefact 1>
  - <artefact 2>
  - ...
- **Layer breakdown across commits**:
  - <commit_x>: layer `prompt_projection`
  - <commit_y>: layer `skill_state`
  - ...

If the actual cumulative diff exceeds this claim, you SHALL flag the
discrepancy as `out_of_scope_review` (deliver-agent C-class close).

## §6. Output format

Write `docs/codex-findings.md` using
`framework/templates/codex_review.md`. The file structure includes:

1. **Sprint Review Decision** header (4 lines):
   ```
   decision: pass | fix_required | out_of_scope_review
   blocking_count: <number>
   summary: <one paragraph>
   ```
2. **Per-sub-reviewer summary** (if 4-parallel orchestration; see §7
   below)
3. **Per-PR verdicts** — for each commit, walk the §4 nine-question
   kernel
4. **Findings by sub-reviewer** — bug / security / architecture /
   regression-coverage sections
5. **Scope discipline check**
6. **Hard gate status checklist**

## §7. Four-parallel sub-agent orchestration (per §4.4)

For milestone scope crossing multiple architectural surfaces (default
for milestone close), orchestrate FOUR parallel sub-reviewers:

| Sub-reviewer | Lens | Focuses on |
|--------------|------|------------|
| **Bug** | Correctness | Logic errors, edge cases, missing null checks, race conditions, exception handling |
| **Security** | Safety | PII handling, capability boundary violations, injection surfaces, supply-chain risk, secret leakage |
| **Architecture** | §4 kernel | Semantic hardcode detection, layer-ownership violations, §1.7 forbidden patterns, Tier-0 expansion claims |
| **Regression-coverage** | §5 | Target / neighbor / negative / shadow case coverage; bad-case suite touch list; eval-spec override audit |

Each sub-reviewer returns its own verdict. Synthesize into the §6
header.

**Block-on-any-reject rule**: a single `reject` from any sub-reviewer
blocks close until addressed.

If your tool environment doesn't support parallel sub-agents, walk
the four lenses serially in named sections.

## §8. Constraints

- You do NOT edit code.
- You do NOT edit `docs/sprints/*` or `docs/archive/*`.
- You do NOT re-judge §5.6 bad-case human verdict (that's the
  deliver-agent + human at close).
- You do NOT widen scope beyond the embedded milestone contract.
- You do NOT propose code fixes — only name the §3 layer.
- You DO flag scope expansion.
- You DO flag governance violations (e.g., handoff §12 filled by dev
  — that's deliver-agent + human owned).
- Per-sub-sprint review is REQUIRED only when one of the four §4.3
  triggers fired:
  1. New Tier-0 candidate
  2. §1.7 forbidden-list red line crossed
  3. Hard-fenced surface touched
  4. Fix-required outcome needing re-review

For default sub-sprints, review is at milestone close (this prompt).

## §9. Self-check before producing findings

- [ ] All per-sub-sprint handoffs read
- [ ] §4 kernel walked for every commit in range
- [ ] Cumulative scope claim verified against actual diff
- [ ] (if 4-parallel) all 4 sub-reviewer verdicts collected
- [ ] §6 header written
- [ ] All findings cite file:line
- [ ] Recommended §3 layer named for every `reject`

---

If anything in this prompt is missing or appears to conflict, STOP
and surface to deliver-agent. Do NOT silently fetch additional repo
files — that breaks §9 self-containment.
