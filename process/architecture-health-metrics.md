---
title: Architecture-health metrics (definitions only)
doc_tier: process
doc_category: live
status: proposal
implementation_status: not_started
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 6KB
notes: >
  Promoted from csagent docs/current/process/architecture-health-metrics.md
  (csagent §6). Four metrics defined; collection is NOT specified at v4 —
  remains proposal-tier per v3.2 carry-over. Adopters who want collected
  metrics implement domain-side; framework reserves the definitions so the
  collection pattern is consistent across adopters when (and if) they land.
---

# Architecture-health metrics (definitions only)

These four metrics name the architectural-health dimensions the framework expects to track. **Definitions only**; collection is NOT specified in v4. Adopters who want collected metrics implement collection in their domain layer; framework reserves the definitions so the collection pattern is consistent across adopters when (and if) they land.

The metrics are referenced by Constitution §1.6 (eval rule) — when collection lands, "architecture-health metrics not regressed" becomes a hard close gate alongside the other Constitution §1.6 inputs (Code Reviewer pass; runtime tests; safety floor; grounding floor; bad-case manual review).

## §1 The four metrics

| Metric | Definition | Unit | Observation cadence | Source artifact | Collection status |
|---|---|---|---|---|---|
| `new_semantic_hardcode_count` | Number of new keyword / regex / if-else / enum entries added to runtime or prompt for a semantic decision in a PR | count per PR | per PR | PR diff + Anti-Hardcode Code Reviewer verdict | not_started |
| `soft_signal_conversion_count` | Number of existing semantic hardcodes downgraded to LLM-projected soft signals | count per sprint | per sprint close | sprint handoff §1 / §11 | not_started |
| `planner_ownership_ratio` | Fraction of semantic decisions in the runtime owned by LLM planning vs runtime guard / regex | percentage | per sprint close (manual count) | runtime survey | not_started |
| `shadow_disagreement_rate` | Fraction of shadow cases where the LLM decision disagrees with the human-labeled expected behavior | percentage | per shadow run | shadow eval result | not_started |

## §2 Direction of health

- `new_semantic_hardcode_count` — DOWN (the goal of Constitution §1.7's forbidden list is to drive this to zero; spikes signal a §1.7 breach).
- `soft_signal_conversion_count` — UP (active migration of past hardcodes into LLM-owned soft signals).
- `planner_ownership_ratio` — UP (Constitution §1.3 LLM-owns list expanding as soft signals replace hard branches).
- `shadow_disagreement_rate` — DOWN (Constitution §1.6 eval rule: shadow regressions disqualify target pass-rate gains).

## §3 Why proposal-tier in v4

The metrics are easy to define and useful to discuss; collection is hard. Each metric requires:

- A consistent annotation surface (PR diff annotations for `new_semantic_hardcode_count`; sprint handoff structure for `soft_signal_conversion_count`).
- A snapshot-able runtime survey for `planner_ownership_ratio` (each adopter's runtime is different; the survey shape is domain-specific).
- A working shadow eval pipeline for `shadow_disagreement_rate` (not all adopters have shadow; Type C demos may not).

v4 collects the definitions so adopters who DO land collection produce numbers comparable across adopters. v4 does not specify HOW collection runs — that's adopter-domain implementation.

## §4 What v4 does specify

- The four metric NAMES are stable framework vocabulary; adopters MUST NOT rename them when implementing collection.
- The DIRECTION of health is stable (§2).
- The source-artifact column is suggested — adopters may map to different source artifacts (e.g., a PR-annotation script instead of human PR-review comment) provided the metric definition still holds.
- The cadence is suggested (per PR / per sprint close); adopters may collect more frequently.

## §5 Adopter implementation (when ready)

When an adopter implements collection, the suggested adoption ladder:

1. Add `new_semantic_hardcode_count` to the Code Reviewer's `docs/codex-findings.md` body (the anti-hardcode kernel already detects hardcodes; adding a count is mechanical).
2. Add `soft_signal_conversion_count` to the sprint handoff §11 — Dev counts per sub-sprint.
3. Add `planner_ownership_ratio` as a quarterly runtime survey — labor-intensive; reserve for milestones where the metric is load-bearing.
4. Add `shadow_disagreement_rate` to the bad-case suite manifest — runs alongside the regular suite.

This ladder is suggested per Constitution §7.0; adopters may pick metrics in any order.

## §6 Cross-references

- Constitution §1.6 — the eval rule that consumes these metrics when collection lands.
- Constitution §1.7 (forbidden list) — what `new_semantic_hardcode_count` is detecting.
- `templates/anti-hardcode-review-kernel.md` — the 9-question kernel whose verdicts populate `new_semantic_hardcode_count`.
- `process/badcase-lifecycle.md` — the shadow eval surface where `shadow_disagreement_rate` is sourced.

## §7 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

When adopter collection lands and produces evidence about which metrics are load-bearing vs which are noise, the fold-back may promote metrics to "collected" status and update Constitution §1.6 to consume them.

---

End of Architecture-health metrics.
