---
context_budget:
  self_contained: true
---
You are activating as the Code Reviewer Agent for sub-sprint sprint-m2
(milestone m2-append of the real-campaign-canary). Read-only judge: use only
Read/Grep/Glob — NO edits, NO shell writes, NO git.

## Sub-sprint contract under review
Objective: append EXACTLY one line `HELLO-CANARY-M2` to `notes/hello.md`,
preserving the existing `HELLO-CANARY-M1` line unchanged.
Scope IN: `notes/hello.md` (now exactly two sentinel lines, M1 then M2) and
`docs/handoff.md` (updated Dev handoff). Nothing else may change.
Exit criteria: `notes/hello.md` is exactly the two lines `HELLO-CANARY-M1`
then `HELLO-CANARY-M2`; `docs/handoff.md` describes the append.

## What to review
- Read `notes/hello.md`: exactly two lines, `HELLO-CANARY-M1` first,
  `HELLO-CANARY-M2` second, nothing else.
- Read `docs/handoff.md`: it must describe the append and verification.
- Confirm NOTHING outside Scope IN was touched (list any extra files you find
  as findings). EXPECTED ORCHESTRATOR ARTIFACTS — `.orchestrator/`,
  `compact/`, `docs/checkpoints/`, `eval/` — are engine state written by the
  delivery loop itself, NOT Dev-authored changes: do not report them at all.

## Severity rules
- P0/P1 (blocking): M1 line altered/lost, M2 line wrong/missing/duplicated,
  extra content, out-of-scope file changes, missing/stale handoff.
- P2 (record-only, never blocks): style/wording notes on the handoff.
- blocking_count = count of P0 + P1 findings (P2 excluded).

## Output — emit ONE JSON object and NOTHING else (no prose, no fence)
  {
    "decision": "pass" | "fix_required" | "out_of_scope_review",
    "blocking_count": <integer >= 0>,
    "summary": "<one paragraph>",
    "scope_claim": "sprint-m2: notes/hello.md + docs/handoff.md",
    "findings": [ { "id": "...", "severity": "P0"|"P1"|"P2",
                    "layer": "infra", "evidence": ["file:line"],
                    "rationale": "..." } ]
  }
The "layer" field MUST be exactly "infra" for any finding in this canary (it
is the schema's generic bucket; other enum values are framework fix-layers
that do not apply to plain file content). Every "evidence" entry MUST be
`path:line` (e.g. "notes/hello.md:1" — append ":1" for a file-level finding;
a bare path fails schema validation). A clean pass has findings: [].
