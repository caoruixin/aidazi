---
title: Milestone M0 — bring-up + baseline
doc_tier: current-runtime
status: current
implementation_status: not_started
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: per milestone
notes: >
  M0 typical content: fill the three domain contracts, build the
  smallest end-to-end flow, surface the first 3-5 bad cases. Replace
  this placeholder with a real M0 plan during your kickoff session.
---

# Milestone M0 — bring-up + baseline

## 1. Milestone class

Layer breakdown across sub-sprints:

- Sub-sprint S0.1: docs-only (filling domain contracts)
- Sub-sprint S0.2: infra (end-to-end skeleton)
- Sub-sprint S0.3: eval_spec (first bad cases)

§7 stanza coverage:

- **REQUIRED**: none (all M0 sub-sprints are likely §7 EXEMPT —
  pure docs / pure infra / characterization)
- **EXEMPT**: S0.1 (docs-only), S0.2 (infra), S0.3 (characterization
  / case-family construction)

## 2. Goal

By the end of M0, this project has:
- Three filled domain contracts in `docs/current/`.
- A minimal end-to-end agent that runs one happy-path session.
- A curated bad-case suite seeded with 3–5 cases derived from M0
  sketch failure modes.

## 3. Sub-sprint sequence

### S0.1 — Fill the three domain contracts

- **Class**: docs-only (§7 EXEMPT)
- **Scope**: fill `docs/current/{domain_taxonomy,runtime_invariants,eval_acceptance_bars}.md`
  for this project.

### S0.2 — Minimal end-to-end skeleton

- **Class**: infra (§7 EXEMPT)
- **Scope**: build the smallest runtime that takes one input,
  invokes one LLM call, and produces one output. Add minimal eval
  harness skeleton.

### S0.3 — Seed bad-case suite

- **Class**: characterization-test (§7 EXEMPT)
- **Scope**: curate 3–5 bad cases derived from the M0 sketch failure
  modes. Build `eval/bad_cases/_manifest.md`.

## 4. Non-goals

- Performance optimization (defer to M2+)
- Multi-LLM provider abstraction (defer)
- Production deployment / packaging (defer)

## 5. Milestone acceptance bar

- End-to-end happy-path session works.
- One representative bad case has been documented and the agent's
  failure on it has been verified (i.e., bad case is real).
- Three domain contracts are filled — not "TBD", but real content.

## 6. Hard fences

- Do NOT skip filling the domain contracts.
- Do NOT add a §3 layer extension in M0 (defer to M1+ if needed).
- Do NOT register a new Tier-0 invariant in M0 (defer to M1+ if
  needed).

## 7. R-items consumed / surfaced

- **Consumed**: none (M0 is the bootstrap)
- **Expected to surface**: R-items for each domain contract gap
  discovered while filling them; R-items for each bad case surfaced.

## 8. Review plan

- **Default**: milestone-shared review at close.
- **Per-sub-sprint triggers expected**: none (all M0 sub-sprints
  EXEMPT, so review is mostly procedural).

## 9. Estimated milestone duration

1-2 weeks.
