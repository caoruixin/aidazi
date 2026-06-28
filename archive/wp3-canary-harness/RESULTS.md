---
title: WP-3 authoring-kernel — Read-trace canary results
doc_tier: archive
doc_category: intermediate
status: archived
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-27
review_cadence: ad hoc
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 4KB
notes: >
  Behavioral evidence for WP-3 closure item 5 — a real-LLM Read-trace canary confirming the
  wired cold-start loads the kernel trio (not the full canonical). Reproduce with
  `read_trace_canary.py --all`. Raw per-cell transcripts are local under .runs/wp3-canary/ (gitignored).
---

# WP-3 authoring-kernel — Read-trace canary

**Claim under test (closure 5):** after WP-3 wiring, a real role activation reads the always-load
kernels (`constitution-core.md` + `authoring-kernel.md`) at cold-start and does NOT auto-read the
full canonical `constitution.md` / `doc_governance.md`; the canonical is read ONLY on-demand when a
deferred-content question fires.

**Method:** `archive/wp3-canary-harness/read_trace_canary.py` spawns a fresh
`claude -p --output-format stream-json` per cell (cwd = framework worktree), instructs the agent to
perform its role-card cold-start, and parses the real tool-call trace (Read targets) — the
authoritative "what did cold-start load" signal (mirrors the claude_code adapter). Matrix =
Dev/Review/Acceptance × {baseline, trigger} × 2 reps × model sonnet = **12 cells**.

## Result: 11/12 PASS — baseline 6/6, trigger 5/6

| role | scenario | rep | constitution-core | authoring-kernel | full constitution.md | full doc_governance.md | verdict |
|---|---|---|---|---|---|---|---|
| dev | baseline | 1,2 | ✅ read | ✅ read | — not read | — not read | PASS |
| dev | trigger | 1,2 | ✅ | ✅ | — | ✅ on-demand | PASS |
| review | baseline | 1,2 | ✅ | ✅ | — | — | PASS |
| review | trigger | 1 | ✅ | ✅ | — | — not read | (see note) |
| review | trigger | 2 | ✅ | ✅ | — | ✅ on-demand | PASS |
| acceptance | baseline | 1,2 | ✅ | ✅ | — | — | PASS |
| acceptance | trigger | 1,2 | ✅ | ✅ | — | ✅ on-demand | PASS |

**Baseline 6/6 — the core claim:** every role's cold-start read the kernel trio and NEVER the full
`constitution.md` / `doc_governance.md`. This validates the wiring fix (and closes the WP-2 §5.1
role-card gap behaviorally).

**Trigger 5/6 — the one non-trigger is a GOOD sign, not a regression.** The review/trigger rep1
question (quote the §7.4 stale-reference rule verbatim) was answerable directly from the
authoring-kernel, because the kernel CARRIES §7.4 in full (the Codex round-3 fidelity fix made it
complete). So the agent correctly did not need the canonical. The dev + acceptance triggers, which
target genuinely-DEFERRED content (the `source_of_truth` field-intent prose; the closure_contract
markdown template), reached `doc_governance.md` on-demand 4/4. dim-6 (on-demand canonical load)
fires only when the kernel genuinely defers — exactly the intended behavior.

**Conclusion:** the wired cold-start loads kernels-not-canonical (baseline), and the canonical
remains reachable on-demand for deferred content (trigger). Closure item 5 satisfied.
