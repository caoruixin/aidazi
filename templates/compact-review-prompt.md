---
title: Compact Review prompt — template
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
  Template for compact/sprint-NNN-review-prompt.md or compact/M<N>-review-prompt.md.
  Deliver authors per-sprint; Code Reviewer Agent consumes. Required front-matter:
  context_budget with self_contained: true. Read-only tool whitelist (Read, Grep,
  Glob). Output: docs/codex-findings.md verdict per
  schemas/review-verdict.schema.json. Embeds reference to
  templates/anti-hardcode-review-kernel.md.
---

# Compact Review prompt — instance template

Copy this template to `compact/sprint-NNN-review-prompt.md` and fill `<placeholders>`. The instance is the self-contained spec the Code Reviewer Agent consumes at sub-sprint close (or §4.3 mid-sprint trigger).

---

## Instance front-matter (REQUIRED)

```yaml
---
title: Review prompt — sprint-NNN
context_budget:
  target_tokens: 8000                          # suggested per §7.0
  load_list:
    - aidazi/governance/constitution-core.md   # always-load kernel; full constitution.md on-demand
    - aidazi/governance/authoring-kernel.md     # always-load kernel; full doc_governance.md on-demand
    - aidazi/governance/context_briefing.md
    - aidazi/role-cards/code-reviewer-agent.md
    - aidazi/templates/anti-hardcode-review-kernel.md      # 9-question kernel
    - aidazi/schemas/compact/review-verdict.compact.schema.json   # agent loads the compact projection (verbose canonical = validator's)
    - <adopter>/AGENTS.md
    - <adopter>/docs/current/adoption-state.md
    - <adopter>/docs/current/runtime_invariants.md         # Tier-0 list
    - <adopter>/docs/sprint_objective.md                    # sub-sprint scope
    - <adopter>/docs/handoff.md                             # §1-§11 Dev wrote
    - <dev-diff-path>                                       # what to review
    - <bad-case-suite-path>                                 # eval/bad_cases/
  do_not_load:
    - <adopter>/case_specs_shadow/*
    - <adopter>/.git/*
  self_contained: true
sprint_id: sprint-NNN
review_trigger: subsprint_close | section_4_3_trigger | milestone_close
backing_agent_kind: codex | claude_code | <other>          # per charter.tooling.review
tool_whitelist: [Read, Grep, Glob]
---
```

## Instance body sections

### §1 Activation

```
You are activating as the Code Reviewer Agent for <sprint-id>.

Cold-start (in order):
  1. aidazi/governance/constitution-core.md   (always-load kernel; full constitution.md on-demand)
  2. aidazi/governance/authoring-kernel.md     (always-load kernel; full doc_governance.md on-demand)
  3. aidazi/governance/context_briefing.md
  4. aidazi/role-cards/code-reviewer-agent.md
  5. aidazi/templates/anti-hardcode-review-kernel.md (9-question kernel)
  6. <adopter>/AGENTS.md
  7. <adopter>/docs/current/adoption-state.md
  8. <adopter>/docs/current/runtime_invariants.md

Tools: Read, Grep, Glob only. NO edits. Network access follows `tooling.review.network_access`. NO git push.
NO spawn of other agents.

Trigger: <subsprint_close | section_4_3_trigger | milestone_close>
```

### §2 Diff under review

```
Diff path: <dev-diff-path>
Sub-sprint scope (from docs/sprint_objective.md):
  <inline summary>

Modules touched (Dev declares; you verify by walking the diff):
  <inline list>
```

### §3 Anti-hardcode kernel application

```
Apply the 9-question kernel from aidazi/templates/anti-hardcode-review-kernel.md
to EVERY diff that touches a semantic surface:
  - prompt
  - runtime semantic decision
  - eval spec
  - judge calibration
  - any new keyword / regex / enum influencing routing or escalation

Exemptions (declare explicitly in verdict; route approve):
  - infra-only
  - docs-only
  - config-governance
  - characterization-test

If the diff is exempt, name which class.
```

### §4 Correctness lens

```
In parallel with the kernel:
  - §1.3 / §1.4 ownership violations (LLM-owned moved to runtime guard or
    vice versa).
  - Tier-0 invariant breaks per docs/current/runtime_invariants.md.
  - Test coverage on changed semantic surfaces.
  - Trace/eval contract integrity.
  - Self-containment violations on any compact prompts (Constitution §1.4-i).
```

### §5 §1.7 forbidden-list audit (per role card §7)

```
For each diff hunk, audit against:
  - encoding raw eval phrases into Java or prompt
  - UC-specific hard rules for soft semantic decisions
  - widening eval spec to accept a genuine bot mistake
  - optimizing visible eval at cost of shadow/generalization
  - prompt as if-else rule dump
  - §1.7-A dual abstraction layer
  - §1.7-B keyword-match closure_criterion
  - §1.7-C Acceptance spawn isolation breach in code
  - §1.7-D MANDATORY_CHECKPOINT bypass (charter validator edits;
    orchestrator state machine edits skipping a default checkpoint in any
    of the four shapes — omitted / emptied / disabled / overridden)
  - §1.7-E Auto Loop / Delivery Loop conflation in docs or code

Any finding tied to §1.7 = P0 by default; verdict = fix_required.
```

### §6 Output

```
Write docs/codex-findings.md with 4-line header:

  ## Sprint Review Decision — sprint-NNN
  decision: pass | fix_required | out_of_scope_review
  blocking_count: <integer>
  summary: <one paragraph>

For each finding, append a body section per
aidazi/schemas/review-verdict.schema.json:

  {
    "id": "<finding-id>",
    "severity": "P0 | P1 | P2",
    "layer": "<one of fix-layer set>",
    "evidence": ["file:line", ...],
    "rationale": "<paragraph; cite kernel question OR correctness lens>",
    "constitution_clause": "<optional: §1.7-X>",
    "kernel_question": <optional integer 1-9>
  }

Use scope_claim field to sign the sub-sprint scope you judged against.
```

**Severity policy:** only **P0/P1** are blocking — they set `decision: fix_required` and count toward `blocking_count`. **P2 is record-only:** list it in `findings` for the record, but never set `decision: fix_required` or raise `blocking_count` for a P2, and don't expect it to be fixed — the delivery loop injects only P0/P1 into the Dev auto-fix round (a verdict whose findings are all P2 must be `pass`; `process/delivery-loop.md` §4.4).

### §7 Pre-output checklist

```
  [ ] 4-line header complete.
  [ ] Each finding: severity + layer + evidence (file:line) + rationale.
  [ ] §1.7 audit ran across all 10 forbidden items.
  [ ] Anti-hardcode kernel ran on every semantic-surface diff (or exemption
      explicitly declared per §3).
  [ ] Correctness lens (§4) ran.
  [ ] Verdict ∈ {pass, fix_required, out_of_scope_review} — not invented.
  [ ] JSON per-finding validates against review-verdict.schema.json.
  [ ] You did NOT edit any non-codex-findings.md file.
```

## Template usage notes

- `target_tokens: 8000` is suggested per Constitution §7.0.
- Backing agent (`agent_kind`) should typically be a DIFFERENT model class from the Dev Agent for independence.
- The `tool_whitelist` in front-matter is mechanical — the orchestrator enforces it at spawn time.
- For milestone close reviews, the prompt body's §2 expands to cover the cumulative diff across sub-sprints; the kernel runs across the full milestone.

---

End of compact review prompt template.
