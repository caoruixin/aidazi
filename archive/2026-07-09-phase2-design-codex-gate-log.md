---
name: 2026-07-09-phase2-design-codex-gate-log
doc_category: intermediate
created: 2026-07-09
description: Codex gpt-5.5 xhigh design-gate ledger for archive/2026-07-09-phase2-requirement-chain-design.md — 5 rounds R0/R0.2/R0.3/R0.4 REVISE -> R0.5 APPROVE (verbatim verdicts)
---

## Round r0 verdict (verbatim)

```
**Blocking Findings**

1. The emitted plan is not runnable as designed. Target §3.3(c) says leave `subsprint_sequence` absent and rely on existing campaign behavior, but current campaign runtime pauses immediately at `milestone_decompose_required` when a milestone has no sequence ([campaign.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/campaign.py:2314)). That adds another human/plan-edit interruption before the first advisory acceptance, violating the parent §3 shape and target §4.

2. “Signed gate-1 envelope” is not actually persisted. Reusing `_step_gate1` verbatim records only `brief_signed`; `RunState` has no approved-scope snapshot, and the guard reads live `charter.autonomy.approved_scope` on resume ([driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:419), [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:2385), [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:2584)). A charter edit after gate-1 can change the envelope used for campaign decomposition without a fresh `customer_gate1_signoff`.

3. The requirement file cannot be referenced via `research-brief.input_path` as claimed. Target §1.8/§2.1 treats it as a file reference, but the schema restricts it to `"path_1_customer_ask"` or `"path_2_bad_case_matured"` and forbids extra fields ([research-brief.schema.json](/Users/caoruixin/projects/aidazi-phase2/schemas/research-brief.schema.json:21)). Use a separate audited sidecar/snapshot ref or change the schema explicitly.

4. The no-ledger `covers_req_ids` fail-closed rule is missing from §3.3. Target §7 says coverage claims require a ledger, but current sign/run gates are dormant when the ledger is absent ([campaign.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/campaign.py:2981), [run_loop.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/scheduling/run_loop.py:255)). Without an explicit bootstrap check, a plan can carry unverifiable `covers_req_ids` and still sign.

5. `scope_envelope_unset` cannot be “bootstrap-only” from the campaign taxonomy’s perspective if implemented as a new `Driver._write_checkpoint`. The checkpoint inventory test requires every Driver-emitted checkpoint to be classified in `campaign.py` ([test_campaign.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/tests/test_campaign.py:90)). Add it unconditionally to the correct resume class, likely `DRIVER_RESUME_CHECKPOINTS`, or the suite fails.

**Non-Blocking**

1. Anchor in §1.6 is overstated: `campaign-plan.schema.json` is not `additionalProperties:false` at every level because `covered_req_surfaces` intentionally allows arbitrary requirement-id keys ([campaign-plan.schema.json](/Users/caoruixin/projects/aidazi-phase2/schemas/campaign-plan.schema.json:47)). The conclusion that milestone `modules/layers` need a sidecar still holds.

2. Anchor in §1.4 misattributes gate-1 resume to `halt_resume_state`; gate-1 resumes because state stays `gate1_pending`, not through the `STATE_HALTED + halt_resume_state` path ([driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:2421), [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:2779)).

3. The bootstrap exit-code mapping needs an explicit `GateHardFail` catch. Current single-loop `main()` only catches `CharterValidationError`; schema-invalid decompose raises through `Driver.run()` after writing `gate_hard_fail`, so it will not naturally become rc 10 ([driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:2746), [run_loop.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/scheduling/run_loop.py:1313)).

4. The decision-file adaptation needs its own exact schema/binding contract. Existing `campaign-decision.schema.json` requires `campaign_id`, and `make_campaign_decision_resolver` assumes campaign state for checkpoint-bearing pauses ([campaign-decision.schema.json](/Users/caoruixin/projects/aidazi-phase2/schemas/campaign-decision.schema.json:7), [run_loop.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/scheduling/run_loop.py:619)).

VERDICT: REVISE
BLOCKING FINDINGS: 1. Target §3.3(c)/§4 vs [campaign.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/campaign.py:2314); 2. Target §2.2/§3.1/§5.1 vs [driver.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/driver.py:419); 3. Target §1.8/§2.1 vs [research-brief.schema.json](/Users/caoruixin/projects/aidazi-phase2/schemas/research-brief.schema.json:21); 4. Target §3.3(d)/§7 vs [campaign.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/campaign.py:2981); 5. Target §3.1 checkpoint taxonomy vs [test_campaign.py](/Users/caoruixin/projects/aidazi-phase2/engine-kit/orchestrator/tests/test_campaign.py:90)
NON-BLOCKING: 1. §1.6 `additionalProperties:false at every level` overstates [campaign-plan.schema.json](/Users/caoruixin/projects/aidazi-phase2/schemas/campaign-plan.schema.json:47); 2. §1.4 gate-1 resume anchor misattributes `halt_resume_state`; 3. §4 exit-code mapping needs explicit `GateHardFail` handling; 4. §4 decision-file resolver needs a bootstrap-specific schema/binding contract```

## Round r0.2 verdict (verbatim)

```
VERDICT: REVISE
BLOCKING FINDINGS: 1. `archive/2026-07-09-phase2-requirement-chain-design.md` §3.3(f)/§3.4 claims the emitted campaign can run to first `advisory_acceptance_pass_signoff`, but campaign units still hit Acceptance strict-prompt resolution. `driver.py` gates Acceptance on a complete signed `charter.intent_contract` before compact/projection sources are accepted (`engine-kit/orchestrator/driver.py:4814-4851`; tests at `engine-kit/orchestrator/tests/test_driver.py:3709-3753`). Gate-1 only sets `RunState.brief_signed` (`engine-kit/orchestrator/driver.py:2437-2445`) and campaign plan `acceptance_bar` is not projected into the derived charter (`engine-kit/orchestrator/campaign.py:3232-3284`). So a clean requirement-start run without pre-signed `intent_contract` will pause at `acceptance_spec_refinement` before advisory acceptance. 2. §2 says the requirement text is Research input while also reusing `_step_research` verbatim; current `_step_research` only prompts from `mission.id` and never reads the requirement snapshot (`engine-kit/orchestrator/driver.py:2330-2359`). The B-3 schema fix is correct (`schemas/research-brief.schema.json:21-24`), but the design still lacks a concrete path that feeds the requirement snapshot into Research. 3. §3.2 caps Stage-1 milestones at 12, but Stage-2 reuses `deliver-plan-verdict.schema.json`, whose `sub_sprints` has no `maxItems` (`schemas/deliver-plan-verdict.schema.json:10-13`). Because §3.3(f) writes compact files for every sub-sprint before plan signoff, the pre-sign artifact write surface remains unbounded.
NON-BLOCKING: 1. §4’s bootstrap decision-file contract says reuse `campaign-decision.schema.json` but describes required fields as only `campaign_id + pause_reason`; the schema also requires `choice` for non-`acceptance_fix_required` pauses (`schemas/campaign-decision.schema.json:83-92`). Spell out `choice: sign|reject|abort` for `customer_gate1_signoff`. 2. §3.3(f) should require a pre-write path uniqueness check over all generated compact prompt paths, including duplicate sub-sprint ids across milestones, because runtime compact lookup is `<repo>/compact/<sid>-...` and campaign schema only enforces per-milestone uniqueness (`schemas/campaign-plan.schema.json:171`, `engine-kit/orchestrator/campaign.py:607-615`).```

## Round r0.3 verdict (verbatim)

```
R0.2 fold-ins mostly check out. B-1 is authority-sound: acceptance intent authority and Gate-1 scope authority are now separated, and the roadmap deviation is tighter. B-2 is sufficient assuming the requirement snapshot path is rendered as an absolute run-dir path. B-3 bounds are sane and belong in bootstrap code, not the shared schema. N-1/N-2 are folded correctly.

I still have two blocking fresh-read findings around the compact-prompt execution path. Both affect the claim that the emitted campaign can run unchanged to first advisory acceptance.

VERDICT: REVISE
BLOCKING FINDINGS: 1. `archive/2026-07-09-phase2-requirement-chain-design.md` §3.4/§4/§5: the exact handoff/run commands omit `--repo-dir`, but current strict compact-prompt lookup only works with `repo_dir`; without it the emitted real campaign will hit `dev_spec_refinement` before advisory acceptance. Carry the resolved repo dir through bootstrap, `--sign-plan`, printed run commands, and optional `--start`, or explicitly fail preflight when it cannot be resolved. 2. `archive/2026-07-09-phase2-requirement-chain-design.md` §3.3(g)-(h)/§5: generated compact Dev/Review prompts are executable runtime specs, but their contents are not bound to `campaign_plan_signoff`; the sidecar hashes are provenance-only and runtime reads `compact/` directly. This leaves a post-sign prompt edit able to change the Dev/Review contract without stale signoff. Either bind generated prompt hashes into a checked authority surface or revise the authority/runtime-zero-change claims and add a concrete human-owned prompt-artifact discipline that prevents this fail-open path.
NON-BLOCKING: 1. `archive/2026-07-09-phase2-requirement-chain-design.md` §3.3(c)-(g)/§4: clarify whether coverage, uniqueness, compact-collision, and OW-M3 refusals reuse `gate_hard_fail` or introduce named checkpoint kinds; the current text is fail-closed but leaves checkpoint taxonomy/resume handling underspecified.```

## Round r0.4 verdict (verbatim)

```
R0.3 B-1 is complete in the design: the bootstrap entry requires `--repo-dir`, compact files are under the resolved repo, printed sign/run commands carry it, and `--start` carries it in-process.

R0.3 N-1 is also sound: schema/bounds stay on `gate_hard_fail`; deterministic data-quality refusals use one new `campaign_decompose_refusal` resume-class checkpoint with pending-state reuse.

I cannot approve because the prompt-artifact digest needs an explicit TD6/restamp rule before implementation. The existing milestone-signals precedent has special carry-forward logic during engine restamp; the new digest is placed the same way but the design does not add the analogous rule or tests.

VERDICT: REVISE
BLOCKING FINDINGS: 1. `archive/2026-07-09-phase2-requirement-chain-design.md` §3.5/§6 Commit B′ omits TD6 engine-restamp handling for `prompt_artifacts_digest`; existing `campaign.py` restamp rebuilds `scope_envelope` via `compute_scope_envelope()` and must manually preserve snapshot-bound optional digests (`engine-kit/orchestrator/campaign.py:1246`, `engine-kit/orchestrator/campaign.py:1247`, `engine-kit/orchestrator/campaign.py:1280`). Without an explicit carry-forward/recompute policy and tests, a legitimate `deliver_followup` restamp can either drop the scope-envelope digest copy and remain `stale`, or the implementation can fail open by not checking the copy. Also thread `repo_dir` through restamp freshness helpers such as `apply_engine_restamp_to_plan()`.
NON-BLOCKING: 1. `archive/2026-07-09-phase2-requirement-chain-design.md` §5.2 still says `stamp_signoff`/`signoff_status` bytes are unchanged; revise to say the human signoff authority and F1 H recipe are unchanged, while §3.5 adds a dormant optional digest extension.```

## Round r0.5 verdict (verbatim)

```
No blocking findings.

R0.4 B-1 is sound. The proposed prompt digest follows the shipped `milestone_signals_digest` pattern: top-level + `scope_envelope` copy, central `signoff_status()` freshness, and TD6 carry-forward during the live restamp path. The verify-then-carry-forward rule is the right policy: recomputing during restamp could launder a post-sign prompt edit, while carrying the signed digest forward keeps unchanged prompt artifacts signed and changed artifacts stale.

R0.4 N-1 is also sound. §5.2 preserves human signoff authority and the Δ-19 F1 `signed_scope_hash` recipe; `prompt_artifacts_digest` is an optional dormant extension, not a new signing authority.

One implementation caution, non-blocking: make sure “repo_dir threaded through call sites” explicitly includes `scope_report.compute_requirement_coverage()` / `_signoff_status_and_hash()` and the `run_loop` result/status summary path, not only `Campaign._signoff_status()`. Those are reporting/followup freshness consumers, and digest-bearing plans need the same repo-dir-aware basis there.

VERDICT: APPROVE
BLOCKING FINDINGS: none
NON-BLOCKING: 1. archive/2026-07-09-phase2-requirement-chain-design.md §3.5: tighten wording that conflates TD6 `deliver_followup_required` restamp with §1.7-F gapfix; the code separates them, though the carry-forward policy remains correct.```

