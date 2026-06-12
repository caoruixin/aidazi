# hermes-reference — build trigger

**Status**: not populated. This is a Type A+B hybrid worked example (LLM-controlled top loop + an SOP `workflow_definition` layer with a per-step test pyramid), populated from the hermes-autoloop project when it reaches sufficient maturity.

## Maturity criteria (any one)

- hermes-autoloop completes its first SOP milestone end-to-end with a Type B `workflow_definition` layer in active use.
- hermes-autoloop publishes a closure_contract-backed Acceptance run with a positive verdict.
- hermes-autoloop runs 3 consecutive orchestrator-driven Delivery Loops with no `scope_deviation` MANDATORY_CHECKPOINT firing.
- 2+ adopters ask for a Type A+B hybrid worked example.

This also resolves OQ-V4-001 (the Type B full spec is deferred until hermes closes its first SOP milestone — `process/common-detours-and-warnings-typeB.md` and the `profile_type_b` charter overlay are placeholders until then).

## Trigger

A human decides hermes is mature enough, then runs the build prompt below in a fresh coding-agent session.

## Build prompt (paste at trigger time)

```
You are populating aidazi/examples/hermes-reference/ from hermes-autoloop's actual state.

PREREQUISITES — read:
- aidazi/process/profile-aware-maturity.md (Type A+B hybrid column)
- aidazi/process/delivery-loop.md (Δ-18 spec)
- the hermes-autoloop repo: AGENTS.md; docs/aidazi-integration-plan.md; docs/upgrade-plan.md;
  orchestrator/{loop,agents,acceptance,charter,gates,checkpoints,state}.py;
  docs/proposals/{orchestration-protocol-draft, acceptance-agent-draft,
  mission-charter-template-draft, aidazi-workflow-governance-variant}.md

POPULATE these sub-dirs of aidazi/examples/hermes-reference/:
1. decisions/        — Δ-3 decisions (esp. #1 abstraction-layer; workflow_definition extension reasoning)
2. discovery/        — business need + workflow definition (SOP layer)
3. m-eval/           — eval instantiation (per-step SOP test pyramid)
4. m-trace/          — trace contract
5. m-autoloop/       — Auto Loop usage (Concept 1)
6. delivery-loop/    — Delivery Loop charter + orchestrator run examples (Concept 2)
7. runtime-skeleton/ — Type A+B hybrid runtime skeleton
8. timeline.md       — lifecycle date stamps

SNAPSHOT date: the date of running this prompt.
NAME the dir: examples/hermes-reference-YYYY-MM-DD/.
READ-ONLY after snapshot (Δ-7).

OUTPUT: a populated dir + a brief summary of what was populated.
```

## Build cost estimate

~4-6h once triggered.

---

Until triggered, A+B hybrid adopters use the Type A+B column in `process/profile-aware-maturity.md` (Δ-14) plus the Δ-18 spec.
