VERDICT: REVISE
SUMMARY: Rev2 resolves the R1 B1-B5 holes at the intended read-sites, but TD6 is not safe as specified. Excluding `subsprint_sequence` wholesale creates a dispatch-integrity bypass and also makes the new authority hash diverge from existing signed-scope consumers.

PART A — R1 BLOCKING resolution:
  B1 — RESOLVED — Rev2 binds `trunk_branch`, `milestone_isolation.*`, and `isolation_strategy`; these are the right read-sites: `campaign.py:602-619`, `821-826`, `885-895`, `955-966`. Binding them closes post-sign merge-target redirect and merge-gate-disable edits.
  B2 — RESOLVED — Rev2 corrected `gap_followup` to `max_subsprints` and `max_no_progress_rounds` (`campaign.py:1096-1101`, `1258`, `1280-1283`; schema `schemas/campaign-plan.schema.json:65-72`) and moved `max_total_spawns`/`max_wall_clock_minutes` under `budget.*` (`campaign.py:784-792`).
  B3 — RESOLVED — Current code collapses `not_fresh_signed` into `GAP_DONE` (`campaign.py:1166-1167`, `1594-1597`, `1930-1936`); rev2 §2.1 correctly requires stale to re-pause while true `no_gap` may finish.
  B4 — RESOLVED — The overlay design in rev2 §2.1 preserves original `pause_reason`/`pause_checkpoint`, which is the right model for mechanism-A resume, `deliver_followup_required`, `milestone_merge`, and decision-bound checkpoints. It must be durable state, not an in-memory flag.
  B5 — RESOLVED — Rev2 §2.1 places checks before `run_unit`, `_execute_milestone_merge()`, `_stamp_milestone_outcome()`, cursor mutation, `_commit_dispatch_resolution()`, and normal `pending_remediation` persistence, so the read-only check cannot half-advance a cursor.

PART B — TD6 authority-subset: FLAWED — No other plan field needs broad exclusion; decompose/follow-up mutations are both `subsprint_sequence`, while merge/cursor/context writes are state, not plan. But excluding the entire `subsprint_sequence` opens a bypass: the live sequence selects the dispatched `subsprint_id` (`campaign.py:1944`, `1964`, `1998-2002`), projects terminality into the derived charter (`campaign.py:2483-2495`; `driver.py:3103-3121`), and resolves `compact/<id>-dev-prompt.md` (`driver.py:1455-1472`, `1706-1728`). A post-sign edit can swap/append prompt ids while `compute_authority_hash()` stays fresh. Use signed sequence plus durable authorized deltas, or re-stamp an engine-authored execution envelope with provenance; do not ignore all sequence edits.

PART C — inventory completeness: COMPLETE — Aside from the TD6 misclassification of `subsprint_sequence`, I found no additional live-read campaign-plan field on dispatch/escalation/authority/merge paths. `merge_policy` and `module_locks` are schema fields but not branched on by the current runner.

NEW BLOCKING (introduced by rev2):
  1. TD6 sequence bypass — `archive/2026-06-30-track2-freshness-signed-input-hardening-spec.md:45,68`; `campaign.py:1944,1964,1998-2002`; `driver.py:1455-1472,1706-1728,3103-3121` — fix by validating live sequence equals signed sequence plus authorized durable deltas, or by re-stamping an engine-authored execution snapshot; do not exclude arbitrary sequence edits from freshness.
  2. Dual-hash divergence — `scope_report.py:280-293,342-347,474-510`; `campaign.py:1529-1536,1670-1677` — existing gap reports and pending-remediation crash recovery still use full `signed_scope_hash`/`signoff_status`. A legitimate sequence insertion would make those stale while authority freshness passes. Fix by threading one authority-status API/signed authority snapshot through scope_report, `_gap_followup_eligible`, and pending-remediation epoch checks, or keep a single effective stamped envelope.

NON-BLOCKING / NITS:
  1. Because `campaign-state.schema.json:7-14` is strict and `CampaignState` round-trips fixed fields (`campaign.py:334-404`), the overlay needs explicit schema/dataclass fields and crash-replay tests.
  2. Prefer binding `milestone_isolation.branch_name_template` and `worktree_root`; “naming/path only” still affects side-effect location and operator commands.
  3. Budget/isolation/gap-followup migration staleness is intentional; `raise_cap` should require re-sign, not exclusion.

PART E — citations: OK