---
title: Context briefing
doc_tier: current-runtime
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-05-28
review_cadence: every 3-5 sprints
supersedes: []
superseded_by: null
notes: >
  Cold-start reading discipline and the Context Pack Prompt for
  agents briefing on non-trivial tasks. Tier and status definitions
  live in `doc_governance.md`. The framework constitution lives in
  `constitution.md`.
---

# Context briefing

When an agent (dev, review, research, deliver) is briefed on a
non-trivial task, the docs it loads in the first few minutes of work
shape what it produces over the entire session. An agent that loads
docs in a near-arbitrary order will tend to anchor on whichever doc
arrives first, which is often the wrong tier for the question being
asked.

This guide does two things:

1. Defines the **cold-start reading discipline** (the minimum set of
   docs every agent must read before working).
2. Ships a reusable **Context Pack Prompt** that asks the agent to
   return an explicit source-of-truth decision, doc-status warnings,
   and known risks before it starts coding.

## Cold-start reading discipline

Every agent in a project consuming `aidazi`, on a cold start, MUST
read in this order:

1. **`AGENTS.md`** — repo constitution; references the framework
   governance chain and consumer domain context. Auto-loaded via `@`
   directives.
2. **Framework governance chain** (auto-loaded from AGENTS.md):
   - `framework/governance/doc_governance.md` — tier model + decision
     rules
   - `framework/governance/context_briefing.md` — this file
   - `framework/governance/constitution.md` — operational gates
3. **Consumer domain context** (auto-loaded from AGENTS.md):
   - `docs/current/domain_taxonomy.md` — your project's lanes /
     escalation / grounding vocabulary
   - `docs/current/runtime_invariants.md` — your Tier-0 registry
   - `docs/current/eval_acceptance_bars.md` — your acceptance metric
     definitions
4. **Role-specific entry doc**:
   - Deliver agent → `framework/role-cards/deliver-agent.md` (via
     `framework/role-cards/deliver-activation.md`)
   - Dev agent → `compact/sprint-NNN-dev-prompt.md` (self-contained
     per §9)
   - Review agent → `compact/M<N>-review-prompt.md` (self-contained
     per §9)
   - Research agent → `framework/role-cards/research-agent.md`
5. **Active contracts** (if exist):
   - `docs/milestone_objective.md`
   - `docs/sprint_objective.md`
6. **Cross-session state**:
   - `docs/10-handoff.md` §0 (structured table) — primary cold-start
     data
   - §1 (narrative) — for context on the current / last closed
     milestone only
   - §2 (archive index) — for finding older milestones

**Rule**: agents do NOT share chat history. All context passes through
repo docs, eval results, git diff, handoffs, and review findings.

## Task-type starting points

For common task types, the docs and code areas an agent should sample
first vary. The consumer project SHOULD maintain a
`docs/current/agent_context_guide.md` listing task-type reading lists
(see `framework/templates/agent_context_guide.md` for the structure).
Each project's reading lists are different because the project's
domain code organization is different.

The framework does NOT prescribe task-type reading lists — these are
domain-specific. The framework prescribes the cold-start order above
and the Context Pack Prompt below.

## Context Pack Prompt

When briefing an agent on a non-trivial task, include a "context pack"
step before any plan or code. Paste the prompt below, adapted to the
task. The agent should answer **before** producing a plan or diff.

```
You are working in this repo. Before proposing a plan or any code
change, build a context pack for the task described below. Do not
start coding.

Task: <one-paragraph description of what we want to do>

Read AGENTS.md (auto-loads the framework governance chain + consumer
domain context). Then use docs/current/agent_context_guide.md to find
the right reading list for this task type (if your project maintains
one). Sample the docs and code paths it suggests; you do not need to
read everything end-to-end, but you must read enough to answer the
questions below.

Return your context pack in this exact shape:

1. Relevant docs
   - For each doc you actually read or sampled, give: path, the tier
     you believe it belongs to, your best guess at its status
     (current / proposal / partial / superseded / unknown), and one
     line on why it is relevant to this task.

2. Relevant code paths
   - List the files and directories you sampled and the specific
     functions, classes, or config keys that govern the behavior in
     scope. Cite paths exactly.

3. Doc status warnings
   - For any doc where you suspect drift from code, say so and name
     the specific drift. If a doc looks forward-looking ("intended
     to", "will"), call that out. If two docs disagree on the same
     point, name the disagreement.

4. Source-of-truth decision
   - For the question this task is trying to answer, state which
     artifact is authoritative: a specific code path, a specific doc,
     or a combination. Justify the choice in one or two sentences
     using the rules in framework/governance/doc_governance.md.

5. Implementation status
   - For the behavior in scope, classify as: implemented / partial /
     not_started / historical / unknown. Cite the code path or
     observation that supports the classification.

6. Risks before coding
   - List the top three to five risks of changing this area: hidden
     coupling, stale docs that other readers may rely on, behavior
     gaps, proposals that may be affected, sprint archives whose
     deltas are load-bearing. Be specific; "be careful with X" is not
     a risk.

Do not edit any files yet. Do not edit docs/sprints/* or
docs/archive/* under any circumstance. Once the context pack is
returned, wait for confirmation before producing a plan or diff.
```

The context pack is cheap to produce and disproportionately reduces
the chance of an agent anchoring on the wrong tier. Use it for any
task that crosses module boundaries, touches a `current-runtime`
contract, or involves a doc that may be forward-looking.

## Trace emission discipline (industry-best-practice default)

Each dev / review session SHOULD emit a structured `trace.jsonl` file
to `docs/sprints/sprint-NNN/trace.jsonl` (dev) or
`docs/milestones/M<N>/trace.jsonl` (review) for later replay /
diagnosis. The trace records:

- Session start (role, sprint id, prompt artifact hash, timestamp)
- Key decisions (file paths read, tool calls made, choices between
  alternatives, when the agent invoked the Context Pack Prompt)
- Errors / blockers / STOP-and-surface events
- Session end (handoff written, verdict, blocking findings count)

A helper script lives at
[`../tools/trace_emitter.py`](../tools/trace_emitter.py). Trace files
are NEVER edited after session close; they are immutable diagnostic
records (treat them as `sprint-archive` tier).

The trace exists for the human and the deliver-agent at close time;
it is not consumed by downstream agents through the constitution
chain.
