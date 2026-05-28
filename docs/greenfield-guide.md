# Greenfield adoption guide — idea → app with aidazi

This guide walks you from "I have an idea for an agentic AI" to "I
have a working agent under aidazi iteration discipline". The example
is a non-CS agent (e.g., shopping guide, quotation, web automation)
so you can see the framework applied to a new domain.

**Expected effort**: 1–2 days for initial setup + first milestone
planning. The first dev sub-sprint adds another 0.5–2 days depending
on scope.

## Step 0 — Prerequisites

- Git installed
- Python 3.10+ (for stanza_validator + trace_emitter)
- A version-controlled directory where your project will live
- Access to one or more LLM backends (OpenAI / Anthropic / local)
- A code agent tool stack (Claude Code / Cursor / Codex / Aider /
  ...) you've used before
- Read [`adoption-overview.md`](adoption-overview.md) first

## Step 1 — Sketch the agent (idea phase)

Before writing any code or governance, answer these on paper or in a
scratch doc:

1. **What does the agent DO?**
   - Example (shopping guide): "Help users discover products matching
     vague needs, compare them, and complete purchase."
   - Example (quotation): "Given a request-for-quote, gather missing
     parameters, compute price tiers, produce a structured
     quotation."
   - Example (web automation): "Execute a parameterized SOP on a
     vendor portal (login, fill forms, submit, verify)."

2. **Who is the user?**
   - End user? Internal operator? Another system?

3. **What does success look like?**
   - One observable end-state per session (e.g., "purchase
     completed", "quotation written", "SOP step N reached with
     verification PASS").

4. **What's the failure mode this agent must avoid?**
   - Example (shopping): "Don't recommend out-of-stock products."
   - Example (quotation): "Don't hallucinate prices."
   - Example (automation): "Don't proceed past a CAPTCHA without
     verification."

5. **What's the LLM-vs-runtime split (first guess)?**
   - LLM owns: user goal inference, semantic step selection, natural
     wording.
   - Runtime owns: tool capabilities, safety floor, persistence,
     budget, trace.
   - You'll refine this in step 3.

Write these into a scratch file like `notes/idea.md`. You'll mine it
when filling in domain taxonomy.

## Step 2 — Set up the project skeleton

```bash
mkdir my-agent && cd my-agent
git init -b main

# Add aidazi as a git submodule
git submodule add https://github.com/your-org/aidazi.git framework
cd framework && git checkout v0.1.0 && cd ..
git add framework .gitmodules
git commit -m "[chore] add aidazi framework submodule"

# Copy the minimal greenfield skeleton
cp -r framework/examples/minimal-greenfield/. .
git add .
git commit -m "[chore] bootstrap project skeleton from aidazi"
```

After this, your tree looks like:

```
my-agent/
├── AGENTS.md                  ← root constitution (loads framework)
├── docs/
│   ├── current/
│   │   ├── domain_taxonomy.md         ← EMPTY; fill in step 3
│   │   ├── runtime_invariants.md      ← EMPTY; fill in step 3
│   │   ├── eval_acceptance_bars.md    ← EMPTY; fill in step 3
│   │   └── agent_context_guide.md     ← EMPTY; fill incrementally
│   ├── milestone_objective.md         ← placeholder
│   ├── sprint_objective.md            ← placeholder
│   ├── action_bank.md                 ← empty backlog
│   ├── 10-handoff.md                  ← cold-start scaffold
│   ├── solutions/                     ← research proposals land here
│   ├── sprints/                       ← sub-sprint archives
│   ├── milestones/                    ← milestone archives
│   └── diagnostics/
│       └── failure-briefs/            ← failure briefs (§2)
├── compact/                            ← dev/review prompts
├── eval/
│   └── bad_cases/                     ← curated bad-case suite
│       └── _manifest.md
└── framework/                          ← aidazi submodule
```

## Step 3 — Fill the three consumer-supplied domain contracts

These three files specialize the framework to your domain. They are
the most important docs you write. Without them, the framework is
incomplete.

### 3.1 `docs/current/domain_taxonomy.md`

Define your project's vocabulary. The framework references this file
by stable name from `constitution.md`. The template at
`framework/examples/minimal-greenfield/docs/current/domain_taxonomy.md`
gives the structure.

Required sections:

- **Workflow lanes** — your project's "lanes" (analogous to CS's
  "FAQ / wrap-up / escalation"). Each lane has: name, when it's
  active, what tools / capabilities are available, how the LLM
  decides to enter.
- **Shift / drift detection** — your project's "topic shift"
  vocabulary. When the user's intent moves between lanes, the LLM
  needs to detect it. Define the observable signals (NOT keywords;
  semantic categories).
- **Escalation signals** — when the agent should hand off to a human
  / higher-privileged path. Define the categories (NOT triggers).
- **Grounding concepts** — what facts the agent must ground in
  retrieved evidence vs may state freely.
- **Layer extensions** (optional) — if your project needs to add a
  §3.1 layer (e.g., `workflow_definition` for SOP-driven projects),
  define it here and explain why the original nine layers don't
  cover it.

### 3.2 `docs/current/runtime_invariants.md`

Define your Tier-0 invariants — the hard floor your runtime
guarantees. Common candidates:

- **Safety floor** — no PII leaks; no actions that bypass user
  consent.
- **Grounding floor** — no factual claims without retrieval evidence
  (for retrieval-grounded agents).
- **Capability boundary** — agent never invokes a tool not in its
  whitelist.
- **Persistence floor** — session state survives restart.

Each Tier-0 invariant gets its own subsection with:

- Statement (one sentence)
- Why it's Tier-0 (NOT a soft signal; runtime MUST enforce)
- How it's enforced in code
- Detection mechanism (trace pattern that proves a violation)

### 3.3 `docs/current/eval_acceptance_bars.md`

Define your acceptance metrics. Framework defaults from
`constitution.md` §5.1 require you to specialize:

- **Wrong-lane containment rate** — your definition (e.g., "session
  containment in a lane other than the one matching user intent").
  Unit: percentage. Direction: down or unchanged.
- **Over-escalation rate** — your definition (e.g., "session
  escalates when LLM could have resolved in-system"). Unit:
  percentage. Direction: down or unchanged.
- **Grounding floor** — your definition (e.g., "fraction of factual
  claims grounded in retrieval"). Unit: percentage. Direction:
  unchanged.
- **Target / neighbor / negative / shadow case definitions** — your
  project's interpretation.

Also define:

- **Eval baseline pointer** — where the canonical baseline result
  lives (`docs/current/eval_baseline.md` is the framework default
  pointer name).
- **Bad-case suite path** — default `eval/bad_cases/`; customize if
  your project uses a different layout.

## Step 4 — Plan the first milestone

The first milestone in a greenfield project is usually:

- **M0 — bring-up + baseline**
  - Sub-sprint S0.1: scaffolding (runtime skeleton, tool layer
    skeleton, eval harness skeleton)
  - Sub-sprint S0.2: smallest end-to-end flow (one happy-path)
  - Sub-sprint S0.3: first three bad cases curated (from your
    sketch's failure modes in step 1.4)
  - Acceptance bar: end-to-end happy path works on N test cases; one
    representative bad case is documented in `eval/bad_cases/`.

Spawn a research agent if you need to investigate any of: LLM
provider choice, tool library choice, eval harness choice, or a
non-trivial architectural decision.

Spawn deliver-agent (paste `framework/role-cards/deliver-activation.md`
into a fresh session, then provide your input). Deliver-agent drafts
`docs/milestone_objective.md` and the first `docs/sprint_objective.md`
+ compact dev prompt.

You (human) review and approve. Then spawn the dev session by pasting
`compact/sprint-001-dev-prompt.md`.

## Step 5 — First sub-sprint

The dev session:

- Reads its compact prompt (self-contained per §9).
- Implements the scope.
- Runs tests + emits trace.
- Authors handoff §1–§11.

You commit the dev work (the pre-commit hook ensures bundling
discipline).

Deliver-agent + you classify the close (A/B/C/D).

Iterate sub-sprints 2..N.

## Step 6 — First milestone close

At milestone close:

- Deliver-agent generates `compact/M0-review-prompt.md`.
- Spawn review session (optionally 4-parallel sub-reviewers if scope
  crosses multiple surfaces).
- Review agent writes `docs/codex-findings.md`.
- Deliver-agent + you run the curated bad-case suite + conduct manual
  review per §5.6.
- If all hard gates pass, close. Archive. Plan M1.

## Step 7 — Iteration cadence

After M0, the framework's normal cadence kicks in:

- Milestones run 3–5 sub-sprints; ~2–4 weeks per milestone.
- Path 1 (research-driven) and Path 2 (bad-case-driven) inputs flow
  into deliver-agent's planning rounds (see
  `framework/role-cards/deliver-agent.md` "Workflow inputs").
- The action_bank accumulates R-items; deliver-agent + human pick
  3–5 R-items per milestone.

## Greenfield pitfalls

Before your second milestone, read
[`friction-playbook.md`](friction-playbook.md). The most common
greenfield mistakes:

1. **Skipping domain taxonomy** — agents write reasonable-looking
   prompts that don't actually match your domain because the
   taxonomy doc was left empty.
2. **Inventing Tier-0 invariants mid-sprint** — sub-sprints sneak in
   new "runtime must enforce X" claims without registration. Always
   route to `human_review_required` instead.
3. **Treating mocked-LLM tests as semantic evidence** — they're not.
   Real-LLM rerun is required for any semantic change.
4. **Letting composite eval scores gate close** — they're
   observation-only. The curated bad-case suite is the primary gate.

## Estimated greenfield budget

| Activity | Effort |
|---|---|
| Step 1 (sketch) | 1–2 hours |
| Step 2 (skeleton) | 30 minutes |
| Step 3 (3 domain contracts) | 0.5–1 day |
| Step 4 (M0 planning) | 2–4 hours |
| Steps 5–6 (M0 execution + close) | 1–2 days |
| **Total to first milestone close** | **2–4 days** |

After M0, each subsequent milestone is faster as the project
accumulates context (bad cases, R-items, taxonomy refinements).
