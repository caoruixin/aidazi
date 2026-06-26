---
title: Control-plane routing — default session contract
doc_tier: process
doc_category: live
status: current
implementation_status: partial
source_of_truth: this file
last_reviewed: 2026-06-24
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 12KB
split_trigger: if routing examples or classifier prompts grow past 4KB, split to process/control-plane-routing-examples.md
notes: >
  Defines the default coding-agent session as a lightweight control plane, not a
  sixth role. The session classifies human natural-language requests, records
  schema-valid intent records, reads only the small control state index by
  default, and dispatches or prepares the proper 5-role / runner path on demand.
---

# Control-plane routing

This file specifies the default session behavior after an adopter applies aidazi.

The default session is a **Control Plane Session**. It is not Research, Deliver,
Dev, Code Reviewer, or Acceptance, and it is not a sixth role in the chain. It is
the natural-language command surface in front of the 5-role chain and the
Delivery/Campaign runner.

The human-facing contract is natural language. Humans do not need to remember
`run_loop.py` arguments, checkpoint file shapes, or whether a project is currently
using the single-milestone Driver or the Campaign runner. The Control Plane
records the human intent, chooses the correct framework path, and then dispatches
or prepares the role/runner action.

## §1 Default responsibility

When a human opens a fresh coding-agent session and does not explicitly activate
one of the five roles, the session:

1. Reads the minimal control-plane context named in the adopter root `AGENTS.md`.
2. Classifies the human request into one routing class (§3).
3. Validates the classifier output against
   `schemas/control-plane-intent.schema.json`.
4. Appends a durable intent record to `.orchestrator/control/intents.jsonl`
   before dispatching or preparing work.
5. Expands context only after routing determines which role or runner needs it.
6. Stops at human-authority gates and unresolved ambiguity.

It does **not** sign role artifacts, write role verdicts, run Acceptance
judgment, or bypass checkpoints.

## §2 Minimal default context

The default session reads only:

- the short Default Session Contract in the adopter root `AGENTS.md`;
- `.orchestrator/control/state.json`, if present;
- recent or summarized `.orchestrator/control/intents.jsonl`, if present;
- open checkpoint refs named by the state index;
- `.orchestrator/control/roadmap-state.json`, if present;
- recent `.orchestrator/control/roadmap-mutations.jsonl`, if present;
- `charter.yaml` fields only when needed to route or resume a runner.

It must not default-load role cards, full action banks, full handoffs, old
research briefs, proposals, sprint archives, audit transcripts, eval artifacts,
or broad globs. The validator enforces this through the `control-plane-load`
block in `AGENTS.md`.

## §3 Routing classes

The classifier output must choose exactly one class:

| Class | Meaning | Safe next action |
|---|---|---|
| `new_requirement` | Human introduces a new need, feature, product behavior, or failure shape not already in active scope. | Prepare Research intake or spawn Research through the runner when charter-permitted. |
| `priority_change` | Human changes ordering or urgency without changing the substantive scope. | Prepare Deliver/Campaign re-plan packet; do not edit scope silently. |
| `scope_change` | Human adds/removes scope, changes milestone/sub-sprint boundaries, or alters proof of done. | Halt for scope decision if active loop exists; otherwise prepare Deliver or Research revision path. |
| `continue_delivery` | Human asks to keep going, resume, run next step, or advance current work. | Read control state, then resume runner or report the blocking checkpoint. |
| `gate_decision` | Human answers an open checkpoint or sign-off. | Validate it matches an open checkpoint; write/route decision through the existing gate mechanism. |
| `status_request` | Human asks where things stand. | Summarize state index, latest intent, open gates, and next action; do not load transcripts unless asked. |
| `explicit_role_activation` | Human explicitly says to act as Research/Deliver/Dev/Reviewer/Acceptance or pastes a role prompt. | Load the relevant role card and switch to that role's cold-start path. |
| `unclear` | The request cannot be routed safely. | Ask one concise clarifying question; append an `unclear` intent record. |

## §3.1 Delivery topology

Control Plane state may declare a delivery topology:

| `delivery_mode` | Execution source | Default use |
|---|---|---|
| `single_milestone` | `charter.yaml` + current `docs/milestone_objective.md` | Default for `human_in_the_loop` and most `human_on_the_loop` adopters. |
| `campaign` | `campaign-plan.json` | Explicit opt-in for multi-milestone automated delivery, especially under high autonomy. |

`delivery_mode` is associated with, but separate from, `charter.autonomy.level`.
Autonomy answers "how far may the system advance without a human"; topology
answers "is the current executable unit one milestone or a whole milestone
queue." A `human_on_the_loop` adopter may stay in `single_milestone` mode for a
long time. `fully_autonomous_within_budget` deployments SHOULD normally use
`campaign` mode so the program queue is explicit.

In `single_milestone` mode, an absent or stale `campaign-plan.json` is not a
delivery blocker. In `campaign` mode, `campaign-plan.json` is the executable
queue and must validate against the Control Plane roadmap projection.

## §3.2 Roadmap mutations

Customer roadmap commands expressed in natural language (for example "insert a
UI milestone before M3") are recorded as structured roadmap mutations in
`.orchestrator/control/roadmap-mutations.jsonl` and applied to
`.orchestrator/control/roadmap-state.json`.

The Control Plane MAY write and apply these roadmap mutations directly because
they are machine-owned routing state representing the Customer's command. This
does not authorize the Control Plane to write role-owned artifacts:

- Research briefs / `closure_contract` remain Research Agent output.
- `docs/milestone_objective.md`, `docs/sprint_objective.md`, and compact prompts
  remain Deliver Agent output.
- Code, review findings, and Acceptance verdicts remain owned by their roles.

`docs/milestone-backlog.md` is a generated human-readable projection of roadmap
state for new adopters. It is not edited directly. In `single_milestone` mode it
summarizes roadmap state plus active charter refs; in `campaign` mode it is
generated from / validated against `campaign-plan.json`.

## §4 LLM classification with schema validation

Routing v1 permits LLM classification. The LLM output is not trusted until it
validates against `schemas/control-plane-intent.schema.json`.

Fail-closed rules:

- Schema-invalid output becomes `unclear`; do not dispatch.
- `confidence: low` asks one clarifying question.
- `needs_human_clarification: true` asks one clarifying question.
- A gate decision that does not match an open checkpoint is invalid.
- A scope-widening or proof-of-done change while a loop is active halts for the
  proper human-authority gate.

## §5 Intent ledger

Every human request that affects delivery state appends one JSON line to:

`.orchestrator/control/intents.jsonl`

The record uses `schemas/control-plane-intent.schema.json`. The ledger is
machine-owned and normally gitignored. It is the durable substitute for chat
history: a fresh session must be able to resume by reading
`.orchestrator/control/state.json` plus the recent intent records.

## §6 State index

The small state index lives at:

`.orchestrator/control/state.json`

It validates against `schemas/control-plane-state.schema.json` and stores only
refs and routing state, not large artifact bodies. It may point to the latest
campaign state, run state, signed brief, checkpoint, or acceptance report, but
the default session expands those refs only when the route requires it.

The roadmap index lives beside it:

`.orchestrator/control/roadmap-state.json`

It validates against `schemas/roadmap-state.schema.json` and is the source for
the generated `docs/milestone-backlog.md` view.

## §7 Boundary rules

- The Control Plane Session never authors a signed Research brief.
- It never writes Deliver close verdicts.
- It never edits code as Dev.
- It never writes Code Reviewer findings.
- It never writes Acceptance verdicts or runs Acceptance judgment.
- It never spawns Acceptance from Deliver/Dev context; Acceptance spawn
  isolation remains Constitution §1.7-C.
- It never routes around MANDATORY_CHECKPOINTS.
- It may write Control Plane-owned routing state and roadmap mutations that
  directly encode a Customer command, but it may not disguise those writes as a
  Research, Deliver, Dev, Review, or Acceptance artifact.

## §8 Validation

Framework validators cover:

- default load block exists and contains only control-plane-safe refs;
- broad globs and forbidden default-load paths are rejected;
- intent records validate against the schema before append;
- roadmap state and roadmap mutation records validate against their schemas;
- generated `docs/milestone-backlog.md` is not an independent source of truth;
- `campaign` mode requires roadmap/campaign-plan agreement, while
  `single_milestone` mode treats campaign-plan drift as non-blocking advisory;
- fresh-session routing can proceed from state + ledger without chat history;
- role artifacts can only be produced by their role sessions.

No hard token budget is set for v1. The control plane records `loaded_refs` for
telemetry and review, and adopters may set budgets later through
`docs/current/adoption-state.md`.

---

End of control-plane routing.
