---
title: Campaign non-advancing dispatch — audit-before-save replay window (pre-existing)
doc_tier: diagnostic
doc_category: live
status: diagnostic
implementation_status: not_started
source_of_truth: this file
last_reviewed: 2026-06-26
review_cadence: none (frozen point-in-time observation)
supersedes: []
superseded_by: null
load_discipline: on-demand
---

# Campaign non-advancing dispatch — audit-before-save replay window

**Point-in-time diagnostic (frozen). Pre-existing; NOT introduced by the
`acceptance_cleanup_required` checkpoint work. LOW severity. Tracked follow-up for a
scoped campaign crash-recovery hardening pass.**

## What

Codex (gpt-5.5 xhigh, read-only) review of the campaign dispatch-resume path on
2026-06-26 found a systemic crash-recovery gap: several **non-advancing** Mechanism-B
dispatch outcomes emit their durable audit event **before** the resolved state is saved.
A crash in that narrow window, followed by `--resume`, replays the same decision and
**duplicates the informational audit event**.

Affected paths (`engine-kit/orchestrator/campaign.py`):
- generic non-advancing dispatch writes `campaign_resume_dispatch` before any save
  (`_handle_resume`, the ACT_DELIVER_FOLLOWUP / ACT_REDISPATCH_FRESH / ACT_END tail);
- `_end()` emits `campaign_ended` before `_save()`;
- `_pause()` emits its pause audit before `_save()`;
- the budget `raise_cap` branch audits before the pause is cleared+saved.

## Severity: LOW — why this is a tracked follow-up, not a blocker

- It is **NOT** a double-ship or double-advance. No cursor moves and no milestone
  ships on these paths; the only durable effect of a replay is a **duplicate
  informational audit-log entry**.
- The hash-chained ledger remains valid (each duplicate is a well-formed appended
  event; `verify_chain` still passes).
- It is **pre-existing** across the whole campaign dispatch model (the `_end`/`_pause`
  audit-before-save ordering predates this session's work).

## What WAS fixed in this session (so this diagnostic is bounded)

The safety-critical paths were made crash-idempotent and are NOT part of this deferred
item:
- **Cursor-ADVANCING dispatch** (ACT_ADVANCE_SUBSPRINT / ACT_ADVANCE_MILESTONE,
  incl. `acceptance_cleanup_required` → `accept_residue_and_ship` ship and
  `acceptance_surface_approve` / `review_out_of_scope` accept) now advances the cursor
  and durably saves `STATUS_RUNNING` via the `_commit_dispatch_resolution()` §3.5c
  barrier **before** the dispatch/waiver audits. A crash in the audit window replays
  through `STATUS_RUNNING` crash-recovery, which never re-interprets the cleared pause →
  no double-advance, no double waiver-audit.
- **`milestone_merge` worktree cleanup** (`loop_ingress.py` `cleanup()`) was made
  **idempotent** (already-removed worktree → prune + report "removed", no GitOpError on
  replay), closing the merge/cleanup replay-wedge.

## Proposed fix (deferred — own scoped initiative + Codex gate)

Make the campaign audit emission **audit-after-durable-save** (or otherwise dedup the
audit) consistently across `_end()`, `_pause()`, and the non-advancing dispatch tail —
mirroring the `_commit_dispatch_resolution()` barrier already used on the advancing
path. This is a campaign-wide change to pre-existing crash-recovery machinery and should
carry its own design note + Codex gate + targeted crash-window tests (one per affected
path), rather than being folded into a WIP-integration commit.
