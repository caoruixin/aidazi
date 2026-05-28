---
title: Eval acceptance bars
doc_tier: current-runtime
status: current
implementation_status: not_started
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: every 3-5 milestones
notes: >
  Domain-specific definitions for the acceptance bars referenced in
  `framework/governance/constitution.md` §5.1. Fill during M0.
---

# Eval acceptance bars

## §1. Wrong-lane containment rate

- **Definition**: <your project's definition; e.g., "fraction of
  sessions where the LLM contains the conversation in a lane other
  than the one matching user intent">
- **Unit**: percentage
- **Direction**: down or unchanged
- **Baseline value**: <see `docs/current/eval_baseline.md` §<X>>
- **How measured**: <judge / heuristic / human label; cite eval
  config>

## §2. Over-escalation rate

- **Definition**: <your project's definition; e.g., "fraction of
  sessions where the LLM escalates when it could have resolved
  in-system">
- **Unit**: percentage
- **Direction**: down or unchanged
- **Baseline value**: <see `docs/current/eval_baseline.md` §<X>>

## §3. Grounding floor

- **Definition**: <your project's definition; e.g., "fraction of
  factual claims in responses grounded in retrieval evidence">
- **Unit**: percentage
- **Direction**: unchanged (hard floor)
- **Baseline value**: <see `docs/current/eval_baseline.md` §<X>>

## §4. Case family definitions

Per `framework/governance/constitution.md` §5.1, each sub-sprint
ships generalization eval coverage across four categories. Define
each for your domain:

- **Target case**: <case the sub-sprint is specifically named to
  address>
- **Neighbor case**: <case that shares the failure shape or relevant
  lane>
- **Negative-control case**: <case designed to NOT trigger the new
  behaviour; ensures no false positive>
- **Shadow case**: <held-out case not visible to dev agent; reported
  separately to human/review>

## §5. Eval baseline pointer

- **Baseline file**: `docs/current/eval_baseline.md`
- **Last refresh**: <sprint id + date>
- **What it covers**: <set of cases + judge config + LLM provider
  version>

## §6. Bad-case suite path

- **Suite directory**: `eval/bad_cases/`
- **Manifest**: `eval/bad_cases/_manifest.md`
- **Eval harness command**: <e.g., `python eval/run_bad_cases.py`>

## §7. Eval evidence gates (framework-default; do not weaken)

Per `framework/governance/constitution.md` §5.5 / §5.6:

- ✅ Curated bad-case suite manual review (HARD; primary)
- ✅ Test suite no new regression (HARD)
- ✅ Safety floor unchanged (HARD)
- ✅ Grounding floor unchanged (HARD)
- 📊 Composite eval scores (OBSERVATION ONLY; per §5.5 demotion)
- ✅ Architecture-health metrics (§6 — per
  `framework/governance/constitution.md`; collected if tooled)

## §8. Eval harness notes

- **Mocked-LLM tests vs real-LLM rerun**: mocked-LLM tests are
  wiring-level only; semantic behaviour changes REQUIRE real-LLM
  rerun per §5.6 eval evidence gate.
- **Shadow case discipline**: shadow cases are readable only by human
  / review agent; the dev agent MUST NOT consume them during
  development.
- **Judge calibration**: if a case flips across reruns of the same
  prompt + spec, reclassify as `judge_calibration` per §3.2 tail
  rule.
