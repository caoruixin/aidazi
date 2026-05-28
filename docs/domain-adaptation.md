# Domain adaptation checklist

A short checklist for the consumer team specializing `aidazi` to
their domain. Most teams will fill this once at adoption and revisit
at every 3rd or 4th milestone close.

## Required domain contracts

Three files MUST exist in `docs/current/`:

### 1. `docs/current/domain_taxonomy.md`

- [ ] Defines **workflow lanes** for your domain (analogous to CS's
      FAQ / wrap-up / escalation; or shopping's discover / compare /
      purchase; or web-automation's SOP-step-bucket).
- [ ] Defines **shift / drift signals** the LLM should observe (NOT
      keyword triggers; observable semantic categories).
- [ ] Defines **escalation categories** (what counts as "hand off to
      human / higher-privileged path" in your domain).
- [ ] Defines **grounding concepts** (what facts must be grounded in
      retrieval evidence; what facts may be stated freely).
- [ ] Optional: **layer extensions** to `framework/governance/constitution.md`
      §3.1 (e.g., a `workflow_definition` layer for SOP-driven
      projects).

### 2. `docs/current/runtime_invariants.md`

- [ ] Lists **Tier-0 invariants** specific to your project — the
      hard floor your runtime guarantees regardless of LLM behaviour.
- [ ] Each invariant has: statement + why-Tier-0 + how-enforced +
      detection mechanism.
- [ ] Common categories: safety floor, grounding floor, capability
      boundary, persistence floor.

### 3. `docs/current/eval_acceptance_bars.md`

- [ ] Defines **wrong-lane containment rate** for your domain.
- [ ] Defines **over-escalation rate** for your domain.
- [ ] Defines **grounding floor metric** for your domain.
- [ ] Defines **target / neighbor / negative / shadow** case
      categorization.
- [ ] Points to your **eval baseline file** (default name:
      `docs/current/eval_baseline.md`).
- [ ] Points to your **bad-case suite path** (default:
      `eval/bad_cases/`).

## Optional consumer artefacts (recommended but not required)

### `docs/current/agent_context_guide.md`

Project-specific task-type reading lists (which docs / code areas an
agent should sample first for common task types in your project).
Template at `framework/templates/agent_context_guide.md`.

### Custom layer additions

If your project's failures don't fit the §3.1 nine-layer taxonomy,
define additions in `docs/current/domain_taxonomy.md` §Layer
extensions. Examples:

- `workflow_definition` — SOP / script-table failures (for
  state-machine-driven projects).
- `retrieval` — RAG / KB lookup failures (for retrieval-grounded
  projects).
- `tool_invocation` — tool-call construction failures (for
  multi-tool projects with rich tool surfaces).

Adding a layer is OK; renaming existing layers is discouraged because
it breaks framework references.

### Domain-specific failure brief categories

If your domain has recurring failure shapes, add a brief category
table to `docs/diagnostics/failure-briefs/_index.md` listing
shape-categories your team uses.

## Per-milestone domain ops

At each milestone planning:

- [ ] Review the three domain contracts. Any updates surfaced by the
      last milestone?
- [ ] Open R-items in `docs/action_bank.md` for taxonomy / invariant
      / acceptance bar drift.
- [ ] Pick which bad cases (per `eval/bad_cases/`) the milestone is
      expected to address.

At each milestone close:

- [ ] Run the bad-case suite + conduct manual review (§5.6).
- [ ] Decide if any bad case downgrades to `closed-as-regression-guard`
      (per §5.6.3 N≥2 rule).
- [ ] Decide if any layer extension is needed (rare).
- [ ] Update the three domain contracts if drift was observed.

## Pitfalls

### Don't make domain_taxonomy.md a glossary

It's a working contract, not documentation. Each section should
answer "what is THIS in our domain" with operational specificity.
"Shift detection: the LLM observes user-intent transitions" is too
abstract; "Shift detection: observe when user moves from
[discover-mode] to [compare-mode]: user references multiple products,
asks about side-by-side; the LLM should request user confirmation
before transitioning when the new lane requires different tools" is
operational.

### Don't pad runtime_invariants.md with soft signals

Tier-0 invariants are hard floor. If you're tempted to add "the
agent should not be rude" — that's a semantic signal, not a Tier-0.
Tier-0 = runtime MUST enforce regardless of LLM choice; soft signals
= LLM owns and can override with context.

### Don't define acceptance bars without thresholds

If your wrong-lane containment rate definition is "we want it down",
that's a direction, not a bar. The bar is "no regression vs baseline
B" or "≤ N% on the M0 case set". Pick a number.

### Don't make the bad-case suite a regression test suite

The bad-case suite is **human-judgment first**. Composite scores are
observation-only (§5.5). The suite holds load-bearing cases that
require deliver + human qualitative judgment at every milestone
close.
