---
title: Compact Research brief — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
load_discipline: by-role
size_target: 6KB
notes: >
  Template for docs/research-briefs/<id>.md. closure_contract is the
  load-bearing body section per Constitution §1.7-B; Acceptance Agent
  judges against it (Constitution §3.4 invariant #4 — Research-Acceptance
  contract symmetry). Customer signs at gate 1 (sets customer_signed: true).
  Schema: schemas/research-brief.schema.json.
---

# Compact Research brief — instance template

Copy this template to `docs/research-briefs/<id>.md` and replace `<placeholders>`.

The instance IS the research brief (this template is not a meta-doc — the file you write IS what the Acceptance Agent and Deliver Agent read).

---

```markdown
---
title: <short brief title>
doc_tier: research-brief
doc_category: live
status: current
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
brief_id: <id>
input_path: path_1_customer_ask | path_2_bad_case_matured
related_proposals: []                # docs/proposals/<id>.md paths (Path 1)
related_failure_briefs: []           # docs/diagnostics/failure-briefs/<id>.md paths (Path 2)
related_r_items: []
customer_signed: false               # Customer sets true at gate 1
sign_off_date: null                  # YYYY-MM-DD; Customer fills at gate 1
---

# <Title>

## Background

<1-2 paragraphs. For Path 1: the Customer's ask in your words. For Path 2:
the failure pattern + n + severity.>

## Closure contract

(Constitution §1.7-B: human-judgment paragraph; NOT keyword match.
Acceptance Agent judges delivered behavior against this section.)

### Positive shape

<1-2 paragraphs in customer-perspective language describing what good
delivered behavior looks like. NOT implementation language.>

### Anti-pattern

<1 paragraph naming the specific failure shape this milestone targets,
in observable terms.>

### Anchor phrases

(Exemplar phrases from the expected response. SUPPORTING evidence
Acceptance cites, NOT regex matchers.)

- "<phrase 1>"
- "<phrase 2>"
- "<phrase 3>"

## Scope IN

- <specific deliverable 1>
- <specific deliverable 2>

## Scope OUT

(Explicit non-deliverables. Tighter than 'obvious things'; name the
adjacent-but-out-of-scope concerns to prevent scope creep.)

- <non-deliverable 1>
- <non-deliverable 2>

## Anti-goal

<1-3 sentences; what we are intentionally NOT trying to do — the
customer-facing failure mode you'd accept rather than over-build.>

## KPI

| Name | Target | Measurement |
|---|---|---|
| <kpi name 1> | <target value or threshold> | <how measured> |
| <kpi name 2> | <target> | <how measured> |

## Risk & impact

<What could go wrong; load-bearing dependencies; user/business cost of failure.>

## Related R-items

<Cross-reference action_bank R-items by stable id. Do NOT duplicate content here.>

- <R-id-1>: <one-line summary>

## Customer sign-off (gate 1)

- Signed: <yes | no>
- Date: <YYYY-MM-DD>
- Signer: <name>
- Reservations / conditions (optional): <text>
```

## Template usage notes

- Closure_contract is THE load-bearing section. If positive_shape uses implementation language ("the agent calls `check_refund_eligibility`") rewrite in customer-perspective language ("the agent confirms eligibility with a clear timeline").
- Anchor phrases are EVIDENCE not gates. If your phrasing looks like a regex (e.g., `/we'll process this within \d+ business days?/`) rewrite as exemplar phrasing the Acceptance Agent could paraphrase.
- After Customer signs (`customer_signed: true`), the closure_contract is FROZEN for the milestone duration. If you (Research) later discover the contract is wrong, do NOT silently edit; halt and request gate 1 re-sign-off (Constitution §3.4 invariant #4).
- Schema: validate against `schemas/research-brief.schema.json` before requesting Customer sign-off.

---

End of research brief template.
