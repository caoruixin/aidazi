---
title: Compact Dev prompt — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
load_discipline: by-role
size_target: 8KB
notes: >
  Template for compact/sprint-NNN-dev-prompt.md. The Deliver Agent authors a
  per-sprint instance; the Dev Agent consumes it as a self-contained job spec.
  Required front-matter: context_budget with self_contained: true
  (Constitution §1.4-i). Sandbox: workspace_write; network follows
  charter.tooling.dev.network_access; no git push; no holdout read
  (process/delivery-loop.md §4.2.8 #4).
---

# Compact Dev prompt — instance template

Copy this template to `compact/sprint-NNN-dev-prompt.md` and fill `<placeholders>`. The instance is the SELF-CONTAINED job spec the Dev Agent consumes.

The Dev Agent reads ONLY what's in `load_list` and avoids files in `do_not_load`. Chat-history backchannel is NOT a substitute for what's in the dev prompt (Constitution §3.4 invariant #1 + §1.4-i).

---

## Instance front-matter (REQUIRED)

```yaml
---
title: Dev prompt — sprint-NNN
context_budget:
  target_tokens: 12000              # suggested; adopter overrides per §7.0
  load_list:
    - aidazi/governance/constitution-core.md   # always-load kernel; full constitution.md on-demand
    - aidazi/governance/authoring-kernel.md     # always-load kernel; full doc_governance.md on-demand
    - aidazi/governance/context_briefing.md
    - aidazi/role-cards/dev-agent.md
    - aidazi/process/prompt-artifact-rules.md
    - aidazi/process/context-passing-efficiency.md   # Δ-5
    - <adopter>/AGENTS.md
    - <adopter>/docs/current/adoption-state.md
    - <adopter>/docs/current/runtime_invariants.md
    - <adopter>/docs/sprint_objective.md
    - <adopter>/docs/handoff.md                       # for §0 cold-start
    - <module-path-1>                                 # specific modules in scope
    - <module-path-2>
    - <test-path-1>
  do_not_load:
    - <adopter>/case_specs_shadow/*                   # holdout; eval contamination
    - <adopter>/docs/research-briefs/*                # not the Dev's input source
    - <adopter>/.git/*
  self_contained: true                                # MUST be true (Constitution §1.4-i)
sprint_id: sprint-NNN
milestone_id: <milestone-id>
sandbox: workspace_write
backing_agent_kind: claude_code | codex | <other>     # per charter.tooling.dev.agent_kind
---
```

## Instance body sections (9 sections)

### §1 Role + scope

```
You are activating as the Dev Agent for sprint-NNN.

Cold-start read (in order):
  1. aidazi/governance/constitution-core.md   (always-load kernel; full constitution.md on-demand)
  2. aidazi/governance/authoring-kernel.md     (always-load kernel; full doc_governance.md on-demand)
  3. aidazi/governance/context_briefing.md
  4. aidazi/role-cards/dev-agent.md (your full role card)
  5. <adopter>/AGENTS.md
  6. <adopter>/docs/current/adoption-state.md

Sandbox: workspace-write. Network access follows `tooling.dev.network_access`. No git push. No read of shadow holdout.
```

### §2 Sub-sprint contract

```
Scope IN:
  - <deliverable 1>
  - <deliverable 2>

Scope OUT (explicit):
  - <non-deliverable 1>

Modules you may touch:
  - <repo-path-1>
  - <repo-path-2>

Modules you may NOT touch (explicitly_out_of_scope):
  - <repo-path-A>

Tests to add / update:
  - <test-name-1>: <what it verifies>
  - <test-name-2>

Bad-case suite additions (if any):
  - <case-id>: <one-line>
```

### §3 Read list (what you load BEFORE coding)

```
- <adopter>/docs/sprint_objective.md (the sprint stanza for this sub-sprint)
- <adopter>/docs/handoff.md §0 (cold-start state)
- <adopter>/docs/handoff.md §1 (prior sprint narrative if applicable)
- <module-path-1> (the primary module you're editing)
- <test-path-1>
- aidazi/process/prompt-artifact-rules.md (the self-containment rules)
```

### §4 Forbidden routes (Constitution §1.7)

```
Before each significant edit, check:
- Adding a keyword / regex / if-else to handle a semantic decision the LLM
  should own? STOP. Route via Δ-9 (process/post-deployment-iteration.md);
  failure layer is prompt_projection / skill_state / semantic_planner.
- Adding a UC-specific hard rule? STOP. Forbidden.
- Encoding eval phrase literals into Java or prompt? STOP.
- Widening eval to accept what was previously a bot mistake? STOP.
- Touching the charter validator or orchestrator code to skip a MANDATORY
  CHECKPOINT? STOP. Constitution §1.7-D non-bypass invariant.

If the dev prompt's contract APPEARS to require any of the above, halt and
surface — the prompt may have been authored against a misclassified failure.
```

### §5 Self-check rules

```
Before declaring done:
  [ ] Tests pass (run them; orchestrator's run_tests gate will re-verify).
  [ ] Handoff §1-§11 written; §12 left blank for Deliver+Customer.
  [ ] No edits to forbidden paths (research-briefs, eval/bad_cases,
      codex-findings, anything in case_specs_shadow).
  [ ] No git push, no network calls outside the charter's `tooling.dev.network_access` grant, no other-agent spawns.
  [ ] Constitution §1.7 audit on your edits (§4 above).
  [ ] Scope check: every file touched is in modules_in_scope AND not in
      explicitly_out_of_scope.
  [ ] Self-containment integrity check recorded in handoff §11.
  [ ] target_tokens not blown by your reads.
```

### §6 Mid-sprint drift handling

```
If you find the sub-sprint is mis-scoped (the contract above can't be
satisfied without a scope change), HALT.

File docs/diagnostics/<id>.md with:
  - What you tried.
  - What's blocking.
  - Proposed scope adjustment.

Then stop. Deliver picks up the diagnostic. Do NOT silently expand scope.
```

### §7 Output paths

```
Code edits: under modules listed in §2.
Tests: under tests/ as named in §2.
Handoff: docs/sprints/<sprint-id>/handoff.md §1-§11 (§12 blank).
Diagnostics (if any): docs/diagnostics/<id>.md.
```

### §8 What's reserved / forbidden output

```
DO NOT write:
  - docs/research-briefs/*
  - docs/codex-findings.md
  - docs/acceptance-reports/*
  - docs/checkpoints/<...> decision: field
  - eval/bad_cases/*
  - docs/current/adoption-state.md
  - <adopter>/charter.yaml
  - Any file in case_specs_shadow/ (read AND write forbidden)

These belong to other roles. Touching them is a §3.4 boundary breach.
```

### §9 References

```
- aidazi/role-cards/dev-agent.md
- aidazi/process/prompt-artifact-rules.md
- aidazi/process/context-passing-efficiency.md (Δ-5)
- aidazi/templates/handoff-template.md
- aidazi/governance/constitution.md §1.4-i + §1.7
```

## Template usage notes

- The 9 sections are the recommended structure. Deliver may consolidate where appropriate, but the SELF-CONTAINMENT property (§5) and the scope discipline (§2 + §4) must remain explicit.
- `target_tokens: 12000` is suggested; adopters may set higher (rich domain context) or lower (simple sub-sprint) per Constitution §7.0 with rationale in adoption-state.md.
- The `load_list` must be SPECIFIC (paths, not glob patterns) for the orchestrator's preflight check to be deterministic.
- If `self_contained: false` is declared, the orchestrator preflight (`process/delivery-loop.md` §4.2.4 `dev_pending`) rejects the prompt. The reviewer-in-manual-mode does the same.

---

End of compact dev prompt template.
