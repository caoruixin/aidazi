---
title: Failure brief — <one-line title>
doc_tier: diagnostic
status: current
source_of_truth: this file
authored_by: <human + deliver-agent>
authored_date: <YYYY-MM-DD>
notes: >
  Per `framework/governance/constitution.md` §2. Lives at
  `docs/diagnostics/failure-briefs/<brief-id>.md`. Becomes the input
  for case-family construction.
---

# Failure brief — <one-line title>

## Brief id

`<brief-id>` (e.g., `BB-2026-05-001` or `<short-slug>-<date>`)

## §1. What happened?

<The observed agent behaviour in one or two sentences. Written so a
reader who has never seen the trace can understand the failure shape.>

## §2. What should a good agent have done?

<The expected behaviour on the same input, written from the user's
perspective. Pin to a contrast: agent did X, should have done Y.>

## §3. Why does this matter?

<The user / business / safety impact in one line. References the
Constitution clause the failure violates if applicable.>

- **Constitution clause** (if applicable): §<X.Y> — <clause name>
- **Impact**: <user-facing | safety | grounding | architecture
  health>

## §4. Is this a one-off or a pattern?

- **Classification**: `one-off` | `pattern` | `unknown`
- **Evidence**:
  - <number of similar traces observed>
  - <neighboring case ids>
  - <prior sprint references>

## §5. Which layer is likely responsible?

Per `constitution.md` §3.1, one of:

- `infra`
- `runtime_guard`
- `prompt_projection`
- `skill_state`
- `semantic_planner`
- `eval_spec`
- `product_policy`
- `judge_calibration`
- `human_review_required`

**Layer hypothesis**: `<layer>` — <one-line justification + which §3.2
question it matches>

**Alternative hypothesis** (if applicable): `<other-layer>` — <one
line on what would disambiguate>

## §6. What should NOT be done?

<The tempting-but-wrong fix (typically a keyword / regex / if-else /
enum / per-lane matrix) and the reason it is wrong (usually a
Constitution clause). This is the brief's anti-hardcode guardrail.>

- **Tempting wrong fix**: <one sentence>
- **Reason it's wrong**: <Constitution clause + one sentence>

## Optional: trace pointer

- **Source trace**: <file path or session id>
- **Snippets relevant to the brief**:

```
<paste 5–20 lines of trace evidence>
```

## Optional: links

- Related R-items in `docs/action_bank.md`: <list>
- Related bad cases in `eval/bad_cases/`: <list>
- Related solutions in `docs/solutions/`: <list>
