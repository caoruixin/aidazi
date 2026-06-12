---
title: Acme Returns Bot — agent context guide
doc_tier: adopter-state
doc_category: live
status: current
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: per milestone close
---

# Agent context guide — per-task reading lists

Adopter-side companion to `aidazi/governance/context_briefing.md`. Tells each role which project-specific files to load on top of the framework chain. Keeps cold-start reads tight (§1.4-i).

| Task / role | Load (beyond the @-included governance chain + role card) |
|---|---|
| Research (new brief) | `docs/current/domain_taxonomy.md`, recent `docs/proposals/`, ~20 sample transcripts |
| Deliver (planning) | latest signed `docs/research-briefs/`, `docs/action_bank.md`, `docs/10-handoff.md` §0/§1 |
| Dev (sub-sprint) | only the `compact/sprint-NNN-dev-prompt.md` load_list — typically `docs/current/runtime_invariants.md` + the in-scope module |
| Code Reviewer | `compact/sprint-NNN-review-prompt.md`, `docs/current/runtime_invariants.md`, the dev diff |
| Acceptance | the signed closure_contract, `eval/runs/<id>/artifacts/`, latest `docs/codex-findings.md` |

Do-not-load defaults: Dev never loads `eval/bad_cases/` (holdout contamination); roles never pass context via chat history.

---

End of agent context guide.
