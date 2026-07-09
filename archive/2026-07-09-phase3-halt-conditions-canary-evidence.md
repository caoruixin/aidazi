---
name: 2026-07-09-phase3-halt-conditions-canary-evidence
doc_category: evidence
status: canary GREEN (offline, deterministic — no real model spend)
created: 2026-07-09
base_commit: 6a2078a
design: archive/2026-07-09-phase3-halt-conditions-design.md (Codex R0.7 APPROVE)
implementation: 6a2078a..aadfdff (Clusters 1/2/3)
---

# Phase-3 halt-conditions + push-not-poll — offline canary evidence

The Phase-3 done-criteria (roadmap §4) require the canary to show **(a)** a pre-set condition halts
with the right checkpoint + facts, **(b)** absent conditions ⇒ byte-identical to baseline, **(c)** the
notifier fires on every pause. This round's canary is **fully offline + deterministic** (mock
`run_unit` / a local notifier script) — **no real model spend** — realized as a checked-in test
suite (so it re-runs on every `pytest`, not a one-shot script).

## Canary suite (58 tests, all GREEN)

`cd engine-kit && python3.12 -m pytest orchestrator/tests/test_halt_conditions_e2e.py
orchestrator/tests/test_halt_metrics.py scheduling/tests/test_pause_notifier.py
scheduling/tests/test_run_loop_campaign.py::TestPauseNotifier
validators/tests/test_charter_validator.py::HaltConditionsTests
validators/tests/test_charter_validator.py::NotificationsTests`
→ **65 passed** (the full design §6 matrix + the tighten-only invariants + the notifier).

### (a) A pre-set condition halts with the right checkpoint + facts

`test_halt_conditions_e2e.py::CanaryA_TwoPauseCascade` — a 2-milestone campaign (m1 static, m2
browser_e2e) with two conditions (`hot-milestone` on `milestone_id in [m2]`, `gate-e2e` on
`milestone_functional_acceptance == browser_e2e`):

- `test_two_conditions_pause_in_order_then_dispatch` — m1 runs clean → at m2's first dispatch the
  campaign PAUSES `halt_condition_met`, checkpoint `…__halt_condition_met__r1.md`, pending
  `condition_id: hot-milestone` + `facts: {milestone_id: m2}`. `proceed` (identity-bound) → SECOND
  pause `…__r2.md`, `condition_id: gate-e2e` + `facts: {milestone_functional_acceptance:
  browser_e2e}`, provisional carries hot-milestone's key (per-condition ack; distinct nonce r1≠r2;
  declaration order). `proceed` again → both acks PERMANENT, cascade cleared, campaign DONE.
- `test_wrong_condition_id_is_refused` / `test_subsprint_id_in_decision_is_refused` — a decision with
  a wrong `condition_id`, or carrying a forbidden `subsprint_id`, is REFUSED by the resolver
  (fail-closed identity binding) → the gate re-pauses.
- `test_abort_ends_campaign_and_clears_overlay` — `abort` ends the campaign and clears the overlay.

### (b) Absent conditions ⇒ zero extra halts, byte-identical

`test_halt_conditions_e2e.py::CanaryB_ByteIdentical::test_no_conditions_is_byte_identical` — the SAME
scripted plan run with an absent `halt_conditions` charter vs an empty `halt_conditions: []`: same
DONE status, and NONE of the four new state fields (`halt_condition_acks`/`_provisional`/`_pending`/
`_seq`) is serialized. (The static byte-identical guarantee is additionally covered by the schema/
validator NO-OP tests and the full-suite non-regression.)

### (c) The notifier fires on every pause (and is fail-safe)

`scheduling/tests/test_run_loop_campaign.py::TestPauseNotifier` (real `run_campaign_entry` exit-10
path, MockAdapters):

- `test_notifier_fires_on_pause` — the configured `notifications.on_pause` hook RUNS on the pause
  (the injected `$AIDAZI_PAUSE_REASON` == `campaign_plan_signoff` is written by the hook), and a
  REDACTED `campaign_pause_notified` audit event is appended to the campaign chain.
- `test_failing_notifier_does_not_change_pause` (hook `exit 3`) and
  `test_timeout_notifier_does_not_change_pause` (hook `sleep 30`, timeout 1s) — the pause reason +
  exit code are UNCHANGED (FAIL-SAFE).
- `test_no_notifications_block_no_event` — absent `notifications` ⇒ no event (default-OFF no-op).

`scheduling/tests/test_pause_notifier.py` unit-proves argv-list (no shell) + env injection + bounded
timeout (clamped ≤60) + fail-safe (nonzero exit / timeout / missing binary / audit failure never
raise) + REDACTED audit (no full argv/env/output).

## The ack lifecycle (the corner the R0.3–R0.6 design rounds + R2 drilled)

`test_halt_conditions_e2e.py::AckLifecycle` + `::AckLifecycleVariants` (the full design §6 matrix):
- `test_drift_before_proceed_re_arms_whole_cascade` — halt at epoch H0; re-sign to H1 → the
  redispatch EP-pre flushes the whole provisional cascade and the condition RE-ARMS with a fresh
  nonce (no stale permanent ack) [design R0.6 B-1].
- `test_multi_drift_re_arms_the_whole_cascade` — two conditions provisional (hot proceeded →
  gate-e2e pending); a re-sign before the second proceed flushes BOTH and re-presents the cascade
  from the top in the new epoch [design R0.5 B-1].
- `test_milestone_scoped_ack_fires_once_per_milestone` — a milestone_id condition on a 2-sub-sprint
  milestone halts+commits at s1 and the s2 EP-pre is SKIPPED via the committed permanent ack (both
  sub-sprints run); permanent acks are hash-independent (engine_restamp survives) [design R0.3/R0.5
  B-3].
- `test_changed_when_under_same_id_re_fires` — digest-change: a changed `when` under a reused id has
  a new `condition_digest` ⇒ a new ack key ⇒ the earlier ack cannot suppress it (re-fires) [design
  R0.4 B-2].
- `test_stale_earlier_nonce_is_refused_at_the_next_pause` — after proceeding r1 → the pause is r2;
  the stale r1 decision does NOT bind at r2 (nonce rolled) → re-parks at r2.
- `test_crash_after_proceed_save_replays_idempotently` — a TRUE crash-after-proceed-save: the
  hand-crafted post-proceed PAUSED state (provisional ack written, resolved) re-binds the same
  decision idempotently → dispatch → done [design R0.4 B-1 / R0.3 B-2].
- `test_freshness_block_then_resign_re_arms` — proceed while STALE → EP-pre blocks for re-sign
  (`campaign_plan_signoff`, overlay preserves the halt_condition_met gate); after re-sign to a new
  epoch, the overlay restores the gate and the halt-time epoch mismatch flushes + re-arms [design
  R0.6 B-1 freshness-block path].
- `test_crash_replay_after_proceed_is_idempotent` — resuming the resolved/DONE state is a no-op.

**Byte-identical (true byte-diff, `ByteIdenticalGolden`):** two no-condition runs produce
byte-identical `campaign-state.json` (golden), AND a declared-but-never-matching condition is
byte-identical to no conditions — a non-matching condition perturbs nothing.

### R2 gate fix (crash-safety)

R2 (Codex) caught that `_halt_epoch_recheck` originally `_save`d the drift flush AFTER `run()` had
flipped the in-memory status to RUNNING but BEFORE the redispatched unit started — a crash there
would persist `STATUS_RUNNING` for a never-started unit and drive crash-recovery to
`run_unit(resume=True)` → the `driver.py:3413` missing-state failure. **Fixed:** the epoch flush
mutates in-memory only; it is persisted by the NEXT durable save (the re-fire `_pause` or the unit
outcome), and a crash before that replays the deterministic flush from the last PAUSED state — no
STATUS_RUNNING-before-dispatch window. The `test_freshness_block_then_resign_re_arms` +
`test_multi_drift` + `test_crash_after_proceed_save_replays_idempotently` variants cover this.

## The five tighten-only invariants (design §3.6)

`validators/tests/test_charter_validator.py::HaltConditionsTests` + `NotificationsTests`:
id-collision vs MANDATORY (`gate_hard_fail`), vs a CAMPAIGN checkpoint (`milestone_merge`), and vs
the new kind (`halt_condition_met`) — all rejected (non-vacuous: the id regex allows underscores);
override-substring (`bypass-gate`) rejected; duplicate id rejected; closed metric/op/value-type ERRORs
(via `halt_metrics`, the single source of truth); absent/empty ⇒ NO-OP. `halt_metrics.py`'s purity,
digest canonicalization (order-independent `in`/`not_in`, `note` excluded), ack scoping, and
declaration-order evaluation are unit-proven (`test_halt_metrics.py`), including a schema↔registry
lockstep drift-guard.

## Full-suite non-regression

`cd engine-kit && python3.12 -m pytest` → **1995 passed / 12 skipped / 1 failed**. The single failure
is the PRE-EXISTING `README.md:122/341` doc-reconciliation red (PR#8 leftover, byte-identical to
main — out of scope; confirmed present with the Phase-3 changes stashed). Kernel-coverage,
load-closure, and all other gates are green.

## Codex gate ledger

- Design gate: R0 → R0.7 (blocking 5→4→3→2→2→1→0), **R0.7 APPROVE** (0 blocking, 3 NB folded);
  verdict `/tmp/aidazi-phase3-r0..r07/verdict.txt`; committed `b10c7e2`.
- Cluster 1 (schema + validator + registry): **R1 APPROVE** (0 blocking, 2 NB folded); committed
  `1a919b9`.
- Cluster 2 (campaign eval + resume + notifier): committed `bd8b88f`; **R2 REVISE** (2 blocking:
  the epoch-recheck crash-safety bug + incomplete §6 canary coverage; 3 NB) → **fixed** (crash-safe
  flush + the full §6 canary matrix + resume-hint/schema NBs).
- Cluster 3 (lever-2 verify + lever-3 doc + teaching docs): committed `aadfdff`.
- R3 whole-scope gate: pending (after R2 re-gate APPROVE).

Nothing in this phase weakens a MANDATORY_CHECKPOINT, acceptance authority (§1.7-C), signed-scope
freshness (Δ-19 F1/T2-A), or the OW-M3 E2E mandate.
