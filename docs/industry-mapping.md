# Industry mapping — how aidazi relates to 2026 best practices

This document maps `aidazi`'s primitives to widely-cited
multi-agent-AI patterns and frameworks as of mid-2026. It is useful
when:

- explaining `aidazi` to someone familiar with industry vocabulary;
- deciding which industry tool / library to layer on top of `aidazi`;
- evaluating whether `aidazi` covers a pattern you've read about
  elsewhere.

## Patterns aidazi inherits / shares with industry

### 1. Supervisor / specialist agent topology

**Industry**: LangGraph, AutoGen, CrewAI commonly use a supervisor
agent that routes work to specialist agents.

**aidazi mapping**:

- **Human** is the ultimate supervisor.
- **Deliver agent** is the operational supervisor for planning +
  orchestration.
- **Dev / Review / Research** are specialists.

The role boundary is similar; the distinguishing factor is
`aidazi`'s explicit anti-shared-chat-history rule. In LangGraph etc.,
agents typically share state through a graph; in `aidazi`, agents
share state through versioned repo docs only.

### 2. Pipeline-based workflows

**Industry**: pipeline frameworks treat work as a directed acyclic
graph of agent calls.

**aidazi mapping**: the milestone → sub-sprint flow IS a pipeline,
but each node is a separate session (potentially separate session
windows) rather than a single in-memory graph.

`aidazi` does not provide an in-process pipeline runtime. Your
consumer project's code may include one (e.g., to run real-LLM eval)
but the iteration loop itself runs across separate sessions.

### 3. Structured handoffs (JSON / Pydantic)

**Industry**: OpenAI Agents SDK, Pydantic AI, LangGraph all favor
structured handoffs over free-form text between agents.

**aidazi mapping**:

- Dev → review handoff is `docs/sprints/sprint-NNN-handoff.md` —
  Markdown with a fixed section schema (template at
  `framework/templates/handoff.md`).
- Sprint stanza is `framework/schemas/sprint_stanza.schema.json` —
  JSON Schema enforced by `framework/tools/stanza_validator.py`.
- Trace records are JSON Lines (`framework/tools/trace_emitter.py`).

`aidazi` favors Markdown-with-schema over pure JSON for handoffs
because the primary consumer is a human-orchestrated agent session
that reads Markdown more efficiently than JSON. The stanza schema is
the exception (small enough to validate machine-side; humans
co-author the Markdown form, the validator catches violations).

### 4. Deterministic verification gates

**Industry**: tests, structured asserts, eval-as-code are widely
recommended for agent verification.

**aidazi mapping**:

- Test suite no new regression — HARD gate (§5.5).
- Safety / grounding floor — HARD gate (§5.1).
- Curated bad-case suite manual review — HARD gate (§5.6).
- Programmatic composite scores — OBSERVATION (§5.5; demoted from
  hard gate after years of drift evidence).

The interesting deviation is `aidazi`'s §5.5 demotion of composite
scores. Industry frameworks often hold composite scores as primary
metrics; `aidazi` argues this is unstable in agent systems because
of LLM provider drift + judge calibration variance + mock-vs-real
gap. The curated bad-case suite + human-judgment-at-close replaces
the composite-score gate.

### 5. Governance as code

**Industry**: GitOps for infrastructure; emerging "policy as code"
for ML / LLM systems.

**aidazi mapping**: the framework itself is governance-as-code:

- Constitution + governance docs are versioned Markdown.
- Sprint stanza schema is JSON.
- Pre-commit hook + validator are scripts.
- `AGENTS.md` autoloads the constitution chain.

Industry trends like Anthropic's "Agent Skills" file format are
adjacent — they encode capability prompts as versioned files.
`aidazi` encodes process / discipline as versioned files.

### 6. LLM for policy authoring, not policy enforcement

**Industry**: the "LLM for plan, runtime for enforcement" split is
widely advocated (Anthropic published guidance on this in 2026).

**aidazi mapping**: this IS the constitution §1.3 (LLM owns) vs §1.4
(runtime owns) split. The §3.2 layer classification operationalizes
the split for every observed failure.

### 7. Observability (tracing + dashboards)

**Industry**: OpenTelemetry, Langfuse, Helicone, Phoenix Arize, etc.
provide trace + dashboard for LLM workflows.

**aidazi mapping**:

- `framework/tools/trace_emitter.py` emits a basic JSONL trace per
  session.
- The framework does NOT ship a dashboard.
- Consumer projects layer on top of the trace JSONL — typically
  ingesting to their existing observability stack.

If your project already uses an observability platform, integrate it
at the consumer code level; the trace.jsonl is a structured input.

### 8. Anthropic-style Agent Skills

**Industry**: Anthropic Agent Skills are versioned `.skill` files
that encode "how the agent does X" as composable prompts.

**aidazi mapping**: the `compact/sprint-NNN-dev-prompt.md` and
`compact/M<N>-review-prompt.md` are conceptually similar — they're
versioned files that encode "how this dev session does this scope" or
"how this review session does this milestone". The differences:

- Compact prompts are per-session-instance, not per-capability.
- Compact prompts are generated by deliver-agent from the milestone /
  sprint objective, not human-authored from scratch.
- Self-containment invariant (§9) means a compact prompt is fully
  executable — no "@-imports" of other files at session-spawn time
  (only `AGENTS.md`).

You can think of compact prompts as "ad-hoc skills" — short-lived,
sub-sprint-scoped.

## Patterns aidazi does NOT cover

### 1. Agent memory / long-term context

`aidazi` does not provide an agent memory architecture. The
framework's "memory" is the versioned docs (constitution + 10-handoff
+ archives). Per-session context lives in chat history (which
`aidazi` explicitly does NOT share across agents).

Consumer projects needing rich memory (e.g., per-user conversation
memory, persistent reasoning chains) layer on top.

### 2. Tool calling / function calling

`aidazi` does not define tool schemas or function-call interfaces.
The framework treats tools as a `runtime owned` concept (§1.4) —
your consumer project defines them.

### 3. Eval harness

`aidazi` defines the **philosophy** (target / neighbor / negative /
shadow categories; real-LLM rerun gate; curated bad-case suite). It
does NOT ship an eval harness. Consumer projects bring their own
(custom Python; Promptfoo; DeepEval; OpenAI evals; etc.).

### 4. UI / agent runtime

`aidazi` is markdown + JSON + small scripts. No agent runtime, no
UI, no orchestrator binary.

### 5. Multi-agent communication protocol

`aidazi`'s "communication" between agents is asynchronous file
writes. There's no protocol for synchronous A↔B agent messages within
a session. If your domain needs synchronous multi-agent reasoning,
combine `aidazi` (for process discipline) with a framework like
AutoGen / LangGraph (for in-process orchestration).

## Recommended industry combinations

| If your need is... | Use `aidazi` + ... |
|---|---|
| In-process agent orchestration (multiple LLMs talking) | LangGraph or AutoGen |
| Structured tool definitions | Pydantic AI or OpenAI Agents SDK |
| Eval harness | Promptfoo, DeepEval, or custom |
| Trace + dashboard | OpenTelemetry → Langfuse / Phoenix Arize |
| Skill / prompt versioning | Anthropic Agent Skills (for capability-level) |
| Per-user agent memory | Mem0, LangChain memory, or custom |

`aidazi` provides the **iteration discipline** layer that's usually
missing or ad-hoc in projects using the above. The combination is
additive.

## When aidazi is NOT the right choice

- Single-developer prototypes (overhead exceeds benefit until ~3
  iterations).
- Pure-research projects with no production gate (no acceptance
  bars).
- Projects where iteration cadence is "ship daily, no planning round"
  (the milestone framework's planning overhead doesn't fit).
- Projects where the team has only one human (research / deliver /
  dev / review roles collapse and discipline can't be enforced by
  separation).

For these, the framework's anti-hardcode kernel (§4.1) and sprint
stanza schema (§7) may still be useful selectively (Profile C of
`brownfield-guide.md`).
