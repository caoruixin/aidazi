---
title: Model Capability Registry — per-model facts the capability gate keys on
doc_tier: process
doc_category: live
status: proposed
implementation_status: spec-only
source_of_truth: this file
created: 2026-06-15
last_reviewed: 2026-06-15
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 10KB
schema: schemas/model-registry.schema.json
related: process/role-configuration-contract.md
notes: >
  v2 loop-engine P-0a (archive/2026-06-15-v2-loop-engine-plan.md §4.1 Facet A,
  §6). Defines the model capability registry: per-model provider, context
  window, tool-use, structured-output reliability tier, reasoning tier, cost.
  A charter's tooling.<role>.capability_ref names a profile in a registry
  instance; the capability gate validates the role's (harness × provider ×
  model) triple against the role requirements in
  process/role-configuration-contract.md §4. The example instance below is an
  ILLUSTRATIVE snapshot — tiers/costs are suggested-default and adopter-tunable
  (Constitution §7.0); refresh against provider docs at the stated cadence.
---

# Model Capability Registry

The Role Configuration Contract's Facet A (execution binding) needs **facts
about models** to validate that a role's `(harness, provider, model)` triple can
do the role's job. This doc defines those facts and their schema; a concrete
**registry instance** (YAML/JSON validating `schemas/model-registry.schema.json`)
lives in the adopter repo and is named by the charter.

## §1 What a registry records

Per model (`schemas/model-registry.schema.json` `$defs/model`):

| Field | Meaning | Used by |
|---|---|---|
| `provider` | `anthropic | openai | deepseek | moonshot | …` | Facet A axis; provider-lock check |
| `model` | provider model id | the binding |
| `context_window` | max tokens | context requirement (Research/Deliver/Reviewer/Acceptance read large inputs) |
| `tool_use` | native tool/function calling | **Dev requires true** on a coding-agent harness |
| `structured_output_tier` | reliability of schema-valid output (`high/medium/low/unsupported`) | **verdict roles require ≥ medium**; model-agnostic verdict invariant |
| `reasoning_tier` | reasoning/judgment tier | judgment (Acceptance) + planning (Deliver) |
| `endpoint_kind` | `native` (first-party harness) or `openai_compatible` (headless adapter) | which harness can reach it |
| `harness_compat` | harnesses that can drive `(provider, model)` | coding-agent vs API-only |
| `cost` | per-million-token input/output (informational) | budget context (`charter.budget` is authoritative) |
| `calibratable` | eligible to back a calibration-gated judgment role (§3.6) | capability gate refuses Acceptance on non-calibratable |

Tier ordering for the **>=** check: `unsupported < low < medium < high`.

## §2 How a charter uses it

```yaml
tooling:
  acceptance:
    harness:  headless
    provider: anthropic
    model:    claude-opus-4-8
    capability_ref: anthropic-opus-judge   # ← key into the registry instance
```

The capability gate (`engine-kit/validators/charter_validator.py`, extension
point pending) resolves `capability_ref` against the registry instance, then
checks the role's requirements (`process/role-configuration-contract.md` §4):
Acceptance needs `structured_output_tier: high`, `reasoning_tier: high`, and
`calibratable: true`; Dev needs `tool_use: true` on a coding-agent harness; etc.

## §3 Example registry instance

Illustrative snapshot covering Anthropic / OpenAI / DeepSeek / Moonshot. Each
top-level key under `models` is a `capability_ref` profile id. **Tiers and costs
are suggested-default and adopter-tunable**; refresh against provider docs.

```yaml
# model-capability-registry.yaml — validates schemas/model-registry.schema.json
registry_version: 1
last_updated: "2026-06-15"
models:
  anthropic-opus-judge:
    provider: anthropic
    model: claude-opus-4-8
    context_window: 200000
    tool_use: true
    structured_output_tier: high
    reasoning_tier: high
    endpoint_kind: native
    harness_compat: [claude_code, headless]
    cost: { currency: USD, input_per_mtok: 5.0, output_per_mtok: 25.0 }
    calibratable: true
    notes: "Default judgment/planning model; native via Claude Code, API via headless."

  anthropic-sonnet-dev:
    provider: anthropic
    model: claude-sonnet-4-6
    context_window: 200000
    tool_use: true
    structured_output_tier: high
    reasoning_tier: medium
    endpoint_kind: native
    harness_compat: [claude_code]
    cost: { currency: USD, input_per_mtok: 3.0, output_per_mtok: 15.0 }
    calibratable: true
    notes: "Coding-agent harness with tool_use — suits Dev."

  openai-gpt5-codex:
    provider: openai
    model: gpt-5.5
    context_window: 256000
    tool_use: true
    structured_output_tier: high
    reasoning_tier: high
    endpoint_kind: native
    harness_compat: [codex, headless]
    cost: { currency: USD, input_per_mtok: null, output_per_mtok: null }
    calibratable: true
    notes: "Codex harness is provider-locked to OpenAI; cost may be subscription-billed (null). Model availability is account-type dependent: a ChatGPT-subscription Codex account serves general models (e.g. gpt-5.5) and rejects gpt-5-codex; an API-key Codex account can use gpt-5-codex."

  deepseek-chat-api:
    provider: deepseek
    model: deepseek-v4-pro
    context_window: 128000
    tool_use: true
    structured_output_tier: medium
    reasoning_tier: medium
    endpoint_kind: openai_compatible
    harness_compat: [headless]
    cost: { currency: USD, input_per_mtok: 0.27, output_per_mtok: 1.10 }
    calibratable: true
    notes: "Reached via the headless OpenAI-compatible endpoint; endpoint base URL set in charter."

  moonshot-kimi-128k:
    provider: moonshot
    model: moonshot-v1-128k
    context_window: 128000
    tool_use: true
    structured_output_tier: medium
    reasoning_tier: medium
    endpoint_kind: openai_compatible
    harness_compat: [headless]
    cost: { currency: USD, input_per_mtok: 0.84, output_per_mtok: 0.84 }
    calibratable: true
    notes: "Kimi via headless; large context suits evidence-reading roles."
```

### Worked checks against §4 of the contract

- **Dev → `anthropic-sonnet-dev`**: `tool_use: true`, coding-agent harness
  (`claude_code`) ⇒ PASS. `deepseek-chat-api` would FAIL for Dev because its only
  `harness_compat` is `headless` (no file-editing coding agent), even though
  `tool_use: true`.
- **Acceptance → `anthropic-opus-judge`**: `structured_output_tier: high`,
  `reasoning_tier: high`, `calibratable: true` ⇒ PASS. A hypothetical
  `structured_output_tier: low` model would FAIL the verdict-reliability bar —
  the engine does **not** widen the acceptance-verdict schema for it
  (model-agnostic verdict invariant; `process/role-configuration-contract.md` §7
  Δ-C2).
- **Code Reviewer → `deepseek-chat-api`**: `structured_output_tier: medium`
  meets the ≥ medium minimum for a verdict role, but the §4 table sets Reviewer's
  target at `high`; adopters who run Reviewer on a `medium` model record the
  divergence + rationale in `docs/current/adoption-state.md` (Constitution §7.0).

## §4 Calibration coupling (Constitution §3.6)

`calibratable: true` is necessary but not sufficient for a judgment role: per the
proposed Δ-C3 (contract §7), calibration identity is per-`(role, provider,
model)`, and **changing the provider or model invalidates `calibrated`** (OQ-V4-007
promoted to a rule). A Loop Memory `calibration-note`
(`schemas/memory-entry.schema.json`) MUST be tagged by `(provider, model)` so the
note is reused only for the same execution binding.

## §5 Editing this doc + the instance

Process tier; cadence per Constitution §8. The **registry instance** lives in the
adopter repo (not normative aidazi state) and is refreshed against provider docs
at `review_cadence`; the **schema** (`schemas/model-registry.schema.json`) is
normative aidazi state and changes only via fold-back. The role requirements this
registry is checked against live in `process/role-configuration-contract.md` §4 —
keep the two consistent in the same fold-back sub-sprint.

---

End of Model Capability Registry.
