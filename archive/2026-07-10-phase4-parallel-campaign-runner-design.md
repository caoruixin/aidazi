---
title: "Phase-4 — Parallel Campaign Runner (implementation design)"
roadmap: archive/2026-07-09-autonomy-roadmap-campaign-unblock.md §5
base_commit: b81f6d5
status: DESIGN — R0.9 candidate (folds Codex R0…R0.8; B-15 = TWO co-dependent Cluster-1 changes made explicit — f1_required activator + H emission; all prior blockers ruled folded)
author_convention: >
  Every load-bearing claim carries a `file:line` VERIFY anchor read at base b81f6d5.
  Anchors exact unless suffixed "(≈)". The R0-fold log (§16) maps each Codex [R0 B-#] round-1
  and round-2 finding to its resolution.
---

# Phase-4 — Parallel Campaign Runner

## §0 Scope, posture, non-negotiables

**Goal (roadmap §5).** Run **N milestones concurrently**, each in its own isolated git worktree,
folding results into a single-writer campaign state — ~N× throughput for disjoint, independent
milestones **without weakening any governance gate**. Strict sequencing 1→2→3→4; Phase-4 consumes
Phase-1's serial campaign + Phase-3's notifier (roadmap §7).

**The execution model (refined per R0.2 B-6/B-8/B-12): coordinator owns every gate; a worker executes
ONE sub-sprint.** The parallel unit of *execution* is a single sub-sprint. The coordinator evaluates
every gate — freshness, halt-conditions, budget — **before each sub-sprint dispatch, exactly as the
serial runner does today** (campaign.py:2562-2617 ✓), then hands **one** sub-sprint to a worker child
process that runs it in the milestone's worktree and returns. Parallelism = up to `max_concurrent`
milestones each with **one** sub-sprint executing concurrently in their own worktrees; the coordinator
is a fast event loop over worker completions (fold → re-gate → dispatch that milestone's next
sub-sprint). This makes budget and freshness enforcement **byte-for-byte the serial semantics**, moved
to per-milestone dispatch boundaries.

**Default-OFF ⇒ byte-identical, via a LITERAL serial fast path (R0 B-10 / R0.6 B-6a).** `max_concurrent`
absent or `==1` ⇒ the existing serial **dispatch** (`_drive_milestones`, campaign.py:2542-2697 ✓) AND serial
**resume** (`_handle_resume` + every helper it calls, 2174-2455 ✓) run **byte-for-byte the base `b81f6d5`
code** — not edited, not re-routed, not re-parameterized. The parallel path is a **separate additive** set of
coordinator methods (`_drive_parallel`, `_handle_resume_parallel`) reached only when `max_concurrent>1` and the
plan is parallel-eligible (§7.1); it reuses the *pure* decision helpers but supplies its own state-plumbing
against `milestone_runtime` (§6.2). Byte identity is true by construction (serial code unchanged ⇒ no
resume-gate goldens needed), still asserted against a checked-in default-off golden (§13).

**No constitutional amendment.** Parallelism changes *scheduling*, never *authority*. Every
MANDATORY_CHECKPOINT, acceptance authority (§1.7-C), signed-scope freshness (Δ-19 F1/T2-A), the OW-M3
mandate, §1.7-D "engine never auto-merges" — fire **per milestone**, unchanged.

**NOT:** intra-milestone (sub-sprint) parallelism — a milestone's sub-sprints stay strictly serial
(the coordinator dispatches at most one in-flight sub-sprint per milestone); not distributed/multi-host;
not a scheduler that reorders/skips gates.

---

## §1 Current state — the serial runner (verified anchors)

| # | Fact | Anchor |
|---|------|--------|
| 1 | `run()` = fresh/resume entry, then outer `while True`: `_drive_milestones()` → §1.7-F gap-followup. | campaign.py:2455-2540 ✓ |
| 2 | `_drive_milestones()` nested cursor walk; **budget checked before each unit** (2562-2566), **freshness gate** (2596-2609), **halt-cond eval** (2610-2617), inline blocking `run_unit` (2624), **account after each unit** (2634-2638), advance path **audits then saves** (2653-2661), pause path **saves then pauses** (2683-2689). | campaign.py:2542-2697 ✓ |
| 3 | Cursor = two ints; serialized under `"cursor"`. | campaign.py:353-354, 411-412 ✓ |
| 4 | `topological_order()` validates the `depends_on` DAG + reorders once at __init__; loop walks the cursor with **no readiness check** (DAG validated, not consumed). | campaign.py:475-504 ✓, 645 ✓ |
| 5 | `_save()` = non-atomic `open(w)`+`json.dump`; `_audit()` appends a **separate** hash-chained ledger file. Two files, not one barrier. | campaign.py:709-711 ✓, 713-715 ✓ |
| 6 | `run_unit` closure captures `units_dir`, `charter`, `run_loop_fn`, `run_loop_kwargs`, `plan`, `campaign_id`, `ledger_path`, `ambient_repo_dir` (3712), **and `clock`** (passed to `run_loop_fn` at 3645/3869); it **reads the live `campaign-state.json`** to build the `requirement-context.json` sidecar's `campaign_state` projection (currently `{status,cursor,milestone_outcomes}`, 3828-3841). Returns `{final_state,spawn_count,loop_id,pause_reason,checkpoint_path}`; file ends 3887. | campaign.py:3645, 3712, 3724-3887 ✓ |
| 7 | `scope_report.compute_requirement_coverage` (the sidecar/gap consumer) reads `state["engine_restamp"]` (329) + `state["milestone_outcomes"]` — so the sidecar projection above is INSUFFICIENT for engine_restamp. | scope_report.py:314-332 ✓ |
| 8 | Deterministic per-unit id `loop_id = "u"+sha256(f"{campaign_id}\x00{milestone_id}\x00{subsprint_id}")[:24]` — `(campaign,milestone,subsprint)` only, so a legit re-run reproduces the SAME loop_id + unit dir. | campaign.py:3737-3740 ✓ |
| 9 | Singleton overlays: `pause_reason`/`pause_checkpoint`, `milestone_context`, `freshness_block`, `engine_restamp`, `halt_condition_pending`, `halt_condition_seq`, `followup_baseline_seq`, `pending_milestone_advance`. | campaign.py:351-403 ✓ |
| 10 | `_load()`→schema-validate→`_check_state_consistency()` (single-cursor invariants). | campaign.py:717-800 ✓ |
| 11 | `_handle_resume` + helpers read/**write** `self.state` directly for pause/cursor/merge-context/halt-pending/followup-baseline/restamp/milestone-advance (2180, 2202, 2238, 2265, 2301, 2406 ✓). | campaign.py:2174-2455 ✓ |
| 12 | CLI resolver + reporter surface ONE pause (run_loop.py:535-716 ✓; single pause report 929-947 ✓). | run_loop.py ✓ |
| 13 | Milestone isolation → singleton `milestone_context`; merge gate `_pause_milestone_merge`→`_execute_milestone_merge`→`li.merge_into_trunk`. | campaign.py:1047-1183 ✓ |
| 14 | Signed authority H: `_resolve_plan_authority` emits `authority.budget` with **exactly 3** keys (3063-3067); additive precedent `e2e_remediation` is **conditional emission** (3084); `signoff_snapshot_authentic` reconstructs H incl. `authority` **only when present** (3390-3391). | campaign.py:3053-3084, 3360-3393 ✓ |
| 15 | `module_locks`/`merge_policy` dormant (zero code refs); schema:174 "enforces lock non-overlap" is aspirational. | grep ✓; schema:153,174,175 ✓ |
| 16 | `new_worktree` = separate dir; `current_branch`/`new_branch` in the admin working tree; `merge_into_trunk` mutates admin HEAD/worktree (aborts on conflict, never force). | loop_ingress.py:341-408, 541-576 ✓ |
| 17 | campaign-state schema `additionalProperties:false` at root. | campaign-state.schema.json:8 ✓ |

---

## §2 Architecture — one coordinator, single-sub-sprint isolated workers

- **Coordinator** = the campaign process. **Sole writer** of `campaign-state.json` + **sole appender**
  of the campaign audit ledger (campaign.py:709-715 ✓). It owns the ready-set, ALL gates (freshness,
  halt, budget), worktree setup/teardown, worker spawn/reap/lease, result folding, merges, resume.
- **Worker** = a child process that executes **exactly one sub-sprint** — one `run_unit` call
  (campaign.py:3724 ✓) — in that milestone's worktree, then writes an **atomic** attempt-scoped
  `result-<nonce>.json` (tmp+rename) and exits. A worker **never reads/writes the campaign-state FILE**
  and **never appends the campaign ledger**; it receives an **immutable coordinator-produced context**
  (§5.1-§5.2) and writes only under `<campaign-home>/milestones/<mid>/`.
- **The dispatch loop.** For each ready milestone with no in-flight sub-sprint, the coordinator: (1) runs
  the serial gate sequence for that milestone's NEXT sub-sprint — budget (2562), freshness (2596),
  halt-cond (2610) — pausing that milestone if a gate fires; (2) if clear, spawns one worker; (3) polls
  for completed workers, folds each result (accounting after, 2634 ✓), advances that milestone's cursor,
  and re-enters (1). Up to `max_concurrent` milestones have a worker in flight at once.

**Serial path untouched (R0 B-10).** The worker's per-unit execution reuses `run_unit`; the serial
`_drive_milestones` is not edited. N=1 equivalence is an explicit canary (§13).

**Why processes, not threads (alt §14):** hard isolation (a worker crash can't corrupt coordinator
memory/state), independent cwd per worker (a worktree IS a per-process cwd), matches the roadmap. The
heavy work is already out-of-process (`claude -p`/`codex`); a per-sub-sprint child is negligible against
unit wall-clock.

---

## §3 State model — per-milestone runtime (R0 B-2, B-11)

New persisted field `milestone_runtime: { <mid>: MilestoneRuntime }`, **emitted only when the parallel
path is active** (serial plans byte-identical — campaign.py:425-442 ✓ discipline).

### §3.1 `MilestoneRuntime` fields

| Field | Generalizes / purpose | Anchor |
|-------|----------------------|--------|
| `phase` ∈ {ready, running, paused, done, merged} | `status` | campaign.py:341-344 ✓ |
| `subsprint_index` | `state.subsprint_index` | campaign.py:354 ✓ |
| `pause_reason`, `pause_checkpoint` | singleton pair | 351-352 ✓ |
| `context` | `state.milestone_context` | 376 ✓ |
| `pending_milestone_advance` | same | 377 ✓ |
| `freshness_block` | overlay | 366 ✓ |
| `halt_condition_pending`, `halt_condition_provisional` | per-milestone (R0.3 B-6; `_handle_resume` mutates provisional at 2270/2286 ✓) | 400-402 ✓ |
| `followup_baseline_seq` | same | 359 ✓ |
| `inflight` (R0.2/R0.4/R0.5) | `{attempt_nonce, loop_id, subsprint_id, dispatch_epoch, dispatch_freshness_slice}` or null. **Written by ONE pre-spawn `_save()`** (R0.5 B-12/B-13) — everything the fold needs is durable BEFORE fork, so a crash can never yield an adoptable worker/result without the fold-time slice. `dispatch_freshness_slice` = the full per-milestone freshness snapshot (§5.6). **No pid/worker in state** — worker liveness is the parent-held-then-inherited `flock` on `<mid>/worker.lock` + a worker-owned lease sidecar (R0.5 B-13, §5.5), so a worker may exist ⟺ this `inflight` record exists | (new) |
| `current_attempt_nonce` (R0.2 B-11) | monotonic per-milestone dispatch counter (fold-key component, §5.3) | (new) |
| `folded` | list of `[loop_id, attempt_nonce]` fold keys; the matching `units` record ALSO carries `attempt_nonce` (R0.3 B-11, schema §11) | (new) |
| `epoch_drift` (R0.3/R0.4 B-12) | `{dispatch_freshness_slice, observed_freshness_slice}` or null — durable per-milestone drift gate; clears ONLY when a deterministic **exact freshness-slice equality** re-check passes (§5.6), never merely because the plan is signed | (new) |

**Global (kept singular — do NOT move to per-milestone):** `spent` (one budget pool, §8);
`halt_condition_acks` (keyed by `[condition_id,digest,mid(,sid)]` — state schema:167-171 ✓);
**`engine_restamp`** — the deliver_followup epoch is a **whole-plan** re-stamp (`apply_engine_restamp_to_plan`
reconstructs the single global signed envelope from one append-only delta chain, campaign.py:3519 ✓; each
delta already carries `milestone_id`, 1465 ✓), so it stays ONE global record; multiple milestones'
insertions append to the same `deltas` list (R0.4 B-1/B-2b — per-milestone would break composition into
the single global H); **`halt_condition_seq`** — one **global** monotonic nonce so two milestones halting
in the same second never collide on the `…__r{seq}` checkpoint basename (R0.4 B-6; campaign.py:961/968 ✓);
`gap_followup_state`
(post-quiescence only, §3.4).

### §3.2 Legacy singleton mirror + fail-closed cursor (R0 B-2, R0.3 B-11b)

Top-level `pause_reason`/`pause_checkpoint`, `milestone_context`, `halt_condition_pending` mirror the
**oldest outstanding** milestone pause (tiebreak: topological index). Serial path = these ARE the real
fields. **The top-level `cursor` mirror is pinned to `(0, 0)`, NOT `(len(milestones), 0)`** (the round-2
sentinel was wrong): `_coverage_class` treats `milestone_index < cursor` as DELIVERED
(scope_report.py:121-125 ✓), so a `len`-sentinel would falsely report **every** milestone delivered.
`(0,0)` is fail-closed (nothing past the cursor ⇒ nothing delivered-by-position). Correct parallel
delivery is derived from `milestone_runtime`, not the mirror — §3.6.

### §3.2.1 Delivery derivation branches on `milestone_runtime` (R0.3 B-11b)

Because the parallel cursor mirror is a fail-closed `(0,0)`, the two delivery-status consumers MUST
branch on `milestone_runtime` when it is present, deriving each milestone's class from its
`phase` (+ the authoritative `milestone_outcomes`, state schema:114-116 ✓), not cursor position:
- `scope_report.compute_coverage` / `_coverage_class` (scope_report.py:113-125 ✓) and
  `compute_requirement_coverage` (scope_report.py:314 ✓): `phase in {done, merged}` ⇒ delivered (subject
  to `milestone_outcomes`); `running`/`paused` ⇒ in_progress; `ready`/absent ⇒ not_started.
- the run summary emitted from `st.to_dict()` (run_loop.py:864-867 ✓, 938 ✓): report per-milestone
  `phase` (a `milestones` array) instead of the single `milestone_index`, keeping the scalar as the
  `(0,0)` mirror.
- **the human + machine output surfaces (R0.4 B-11b):** `print_campaign_result` prints
  `milestone_index/total complete` (run_loop.py:1029 ✓) and `CAMPAIGN_STATUS` emits `milestone_index`
  (run_loop.py:1068 ✓) — both misleading under the `(0,0)` mirror. Under `milestone_runtime` they report
  **phase-derived progress** (count of `merged`+`done` vs total; a per-milestone phase line/array), and
  the scalar `milestone_index` is explicitly labelled the legacy mirror.

Serial state (no `milestone_runtime`) uses the existing cursor path unchanged in all four consumers.

### §3.3 `_check_state_consistency` under parallelism (R0 B-11, refined)

Branch on `milestone_runtime` presence (campaign.py:717-800 ✓):
- **Absent (serial)** ⇒ existing single-cursor invariants run **verbatim**.
- **Present (parallel)** ⇒ per-milestone analogues **plus the cross-field ties Codex required**:
  `0 ≤ subsprint_index ≤ len(seq(mid))`; PREFIX (each sub-sprint the index passed has a folded unit);
  `phase` coherence (paused ⇒ non-null pause; running ⇒ non-null `inflight` with a live-or-stale lease);
  **`inflight.attempt_nonce == current_attempt_nonce`** when running; **budget tie (R0.3 B-11)** — the
  count of milestones with non-null `inflight` ≤ `max_concurrent`; `spent.subsprints_run + inflight_count
  ≤ max_subsprints`; AND **`spent.subsprints_run == len(units)`** (every folded unit is accounted, so a
  crash-resume can never undercount budget); **fold tie** — every `folded` key `[loop_id, nonce]` has a
  matching `units` record carrying that same `[loop_id, attempt_nonce]` (unit records gain `attempt_nonce`,
  §11) with `nonce ≤ current_attempt_nonce`; mirror equals oldest-outstanding. Legacy top-level cursor
  pinned to the fail-closed `(0,0)` mirror (§3.2).

### §3.4 Gap-followup stays global (R0 N-2 upheld)

Runs from `run()`'s outer loop only at backlog-exhausted (campaign.py:2518-2532 ✓); the coordinator
declares exhaustion only when **every milestone is TERMINAL** (R0.5 B-14 — §4's `all_terminal`:
dependency-targets at `merged`, leaf milestones allowed at `done`-unmerged) and zero workers run — quiescent,
single-writer, identical to today. Global `gap_set_history`/`no_progress_rounds` unchanged.

### §3.5 Additivity & schema

`milestone_runtime` added to `campaign-state.schema.json` `properties`; `to_dict` emits only when
non-empty; `from_dict` defaults `{}`. Serial state byte-identical.

---

## §4 Scheduler — ready-set over depends_on ∩ module_locks; per-dispatch budget

```
ready_set = { m : runtime(m).phase in {ready, absent}
                AND runtime(m).inflight is null
                AND all(runtime(dep).phase == merged for dep in m.depends_on)
                AND locks(m) disjoint from UNION locks(r) for r with inflight }
```
- **Locks (first use of schema:175 ✓).** `locks(m)=set(m.module_locks or [])`; **empty ⇒ conflicts with
  everything** (conservative). Parallelism opt-in via disjoint locks; a legacy no-locks plan with
  `max_concurrent>1` runs serially (byte-identical outcomes).
- **Admission (R0 B-8, refined).** Dispatch a ready milestone's next sub-sprint only if:
  `inflight_count < max_concurrent` **and** `spent.subsprints_run + inflight_count + 1 ≤ max_subsprints`
  (the signed cap; +analogues for spawns/wall are checked at fold, at-most-`max_concurrent` overrun
  bounded and settled — see §8). Because exactly one sub-sprint per milestone is ever in flight, the
  in-flight count is the reservation; N workers can never collectively pass a signed `max_subsprints`.
- **`depends_on` consumed** for the first time (DAG cycles rejected at ingress, 493 ✓).
- **Termination (R0.4 B-14).** A milestone is **terminal** when `phase == merged` OR when it is a **leaf**
  (no other milestone `depends_on` it) resolved via `open_pr`/`keep_branch` — a deliberate `done`-unmerged
  terminal, exactly the legitimate "advance without merging" the serial runner allows (campaign.py:1152-1156 ✓).
  A **non-leaf** (dependency-target) milestone is terminal ONLY at `merged` (§7.1). Then: no-ready ∧
  no-inflight ∧ ≥1 paused ⇒ exit 10 (notifier pages each); **all-terminal** ⇒ gap-followup → `STATUS_DONE`
  (2534-2540 ✓); no-ready ∧ no-inflight ∧ 0-paused ∧ not-all-terminal ⇒ this can only be a dependency-target
  milestone stuck at `done`-unmerged (its dependents can't start) ⇒ **exit 10 needs-human** ("merge required
  to unblock dependents"), NOT a silent stall.

---

## §5 Worker contract + exactly-once folding (R0 B-1, B-2, B-3, B-5, B-12)

### §5.1 Worker input contract (R0 B-1 round-2) — full enumeration incl. `clock`

`<mid>/worker-input.json` carries every closure input `run_unit`/`run_loop_fn` need (campaign.py:3645,
3712, 3724-3887 ✓): `campaign_id`, milestone spec, `work_dir` (worktree), `units_dir`, signed `plan`,
canonical `charter`, `ledger_path`, `run_loop_kwargs` (the `**call_kwargs` at 3869 incl. resolved
`--repo-dir`/adapter wiring), the sub-sprint id + `resume` marker + `subsprint_sequence` +
`functional_acceptance` + `milestone_signals`, **`clock` (an explicit worker clock policy — the same
injected clock the coordinator uses, so wall-clock accounting agrees)**, the `attempt_nonce`, the
`dispatch_epoch` (§5.6), and the **coordinator-produced `requirement_context` sidecar** (§5.2 — the worker
does NOT build it from state). `run_loop_fn` is resolved by the worker from the same module entrypoint.

### §5.2 Coordinator produces the WHOLE sidecar (R0.3 Q2 / B-1/B-2 round-3)

Rather than pass a projection the worker uses to *build* the sidecar (which re-opens the coupling), the
**coordinator produces the entire `requirement-context.json` itself** and hands it to the worker
(pre-written into the unit dir, or as a `requirement_context` kwarg). `run_unit` gains a
`requirement_context` param: when provided (worker mode) it is written **verbatim** and the self-read
branch (campaign.py:3819-3851 ✓ — which today opens the live `campaign-state.json`) is **skipped
entirely**; when absent (serial) the existing branch runs unchanged. This removes the worker↔state-file
coupling class outright. The Driver reads this `campaign_state` from `requirement-context.json` and passes
it to `compute_requirement_coverage` (driver.py:5872/5875 ✓). The coordinator builds the sidecar exactly as
`run_unit` does today (campaign.py:3839-3841 ✓: `{plan, ledger (projected), campaign_state, charter}`) but
from its authoritative in-memory state, where `campaign_state` carries **every field
`compute_requirement_coverage` reads** AND enough to classify delivery under the parallel `(0,0)` mirror:
`status`, `cursor.milestone_index` (scope_report.py:359/412 ✓ fallback), `milestone_outcomes`, the
**global** `engine_restamp` (scope_report.py:329 ✓ → `apply_engine_restamp_to_plan`, one whole-plan chain),
**and — the R0.4 fix — the per-milestone phase/outcome map** (the `milestone_runtime` `{mid: phase}`
projection) so `compute_requirement_coverage`'s delivery branch (§3.2.1) classifies from phase, not the
fail-closed `(0,0)` cursor. (Impl-gate: re-audit `compute_requirement_coverage` for any further `state[...]`
read; Driver + scope_report tests consume the ACTUAL sidecar bytes, not a hand-built dict.)

### §5.3 Attempt-scoped results; fold key = (loop_id, attempt_nonce) (R0 B-3 round-2)

`loop_id` alone can't key folds (a legit re-run reuses it, §1 #8). Each dispatch increments
`milestone_runtime[mid].current_attempt_nonce` (persisted **before** spawn), and the worker writes an
**attempt-scoped** `result-<attempt_nonce>.json` — NOT a single reused path. The coordinator folds a
result **only when** its `attempt_nonce == milestone_runtime[mid].current_attempt_nonce` (the live
attempt); a lower-nonce file is a stale prior attempt and is ignored/archived, so an old folded result
can never mask a live higher-nonce worker (the round-2 B-3/B-5 hazard). Fold key `[loop_id,attempt_nonce]`
recorded in `folded`; a re-delivered identical result is a no-op; a genuine re-dispatch has a higher
nonce ⇒ folded fresh.

### §5.4 Fold atomicity — state exactly-once, audit at-least-once-with-dedup (R0 B-4, CLOSED)

State fold (append unit, settle budget, record `[loop_id,nonce]` in `folded`, advance mid's cursor,
clear `inflight`) is one `_save()` — the §3.5c barrier keyed per milestone (campaign.py:1197-1213 ≈).
Audit is at-least-once with the fold-key dedup (append before the fold-marking save, matching 2653-2661 ✓;
a crash re-appends but the key makes it dedupable). Ruled acceptable for v1 (R0.2 Q2).

### §5.5 Worker lease — crash-resume never double-runs a live worker (R0 B-5)

**Parent-locks-before-fork launcher (R0.5 B-13) — no child can exist unobserved.** A worker-first `flock`
still races: if the coordinator crashes after fork but before the child takes the lock, resume could acquire
the lock, decide "no worker", redispatch, and the original child later takes the lock ⇒ double-run. Fix, in
strict order: (1) the coordinator persists the **durable pre-spawn `inflight`** record
`{attempt_nonce, subsprint_id, work_dir, dispatch_epoch, dispatch_freshness_slice}` via one `_save()`
**before** forking (§3.1) — everything the fold needs is durable up front; (2) the coordinator **acquires the
`flock` on `<mid>/worker.lock` ITSELF, before fork**, then spawns the worker with that locked fd **inherited**
(POSIX `flock` is associated with the open file description and shared across `fork` — the child holds the
lock from the **instant of fork**, before it runs any instruction); (3) the coordinator closes its own copy of
the fd once the child is confirmed spawned, so the child then solely holds the lock until it dies (the OS
releases it on process death). There is **no window** where a live child exists without holding the lock. The
worker still writes `{pid,start_epoch}`+heartbeat to a **worker-owned lease sidecar** `<mid>/worker-<nonce>.lease`
(single-writer state preserved). On crash-recovery (2486-2492 ✓), for each milestone with an `inflight`:
(a) current-nonce `result-<nonce>.json` exists ⇒ fold (idempotent, §5.3); (b) else **probe the `flock`**:
can't acquire ⇒ a live child holds it ⇒ **adopt**; (c) can acquire ⇒ no live child ⇒ **fence** (kill any stale
lease pid, verify), bump `current_attempt_nonce`, re-dispatch. Two live workers never share the worktree/unit
dir (3740 ✓). Reuses the proven claude_code watchdog-lease pattern.

### §5.6 Signed-scope epoch — compared on EVERY fold, durable drift gate (R0.3 B-12)

At admission (in the **same pre-spawn `_save()`**, §5.5) the coordinator persists `inflight.dispatch_epoch =
live signed_scope_hash` **and `inflight.dispatch_freshness_slice`** — the durable, canonical snapshot of
**everything the freshness gate checks for this milestone** (R0.5 B-12 — a hash alone can't reconstruct prior
scope after a plan edit, and my earlier slice was too narrow). The slice = the canonical_json of:
(a) the **H wrapper fields** `{version, campaign_id, goal, charter_ref, charter_hash}` (campaign.py:3114-3132 ✓);
(b) this milestone's **`_envelope_milestone(milestone, charter, ledger)` entry** (campaign.py:3007-3022 ✓:
id/objective/covers_req_ids/subsprint_sequence/depends_on/resolved_functional_acceptance/acceptance_bar/
isolation_strategy/covered_req_surfaces?); (c) the **whole signed `authority` block**; (d) the two
digest freshness inputs enforced **outside** H — `milestone_signals_digest` + `prompt_artifacts_digest`
(campaign.py:3448-3469 ✓).

**Two-part freshness re-check on EVERY fold (R0.6 B-12) — the existing function is the authority, the slice is
the discriminator.** The slice ALONE cannot replace `signoff_status()`: a post-dispatch edit that flips
`signoff.signed_by_human` to false (campaign.py:3433-3435 ✓) or tampers only a **stored/snapshot digest copy**
while leaving H + live-plan digests equal (campaign.py:3448-3454, 3462-3469 ✓) would be `unsigned`/`stale` for
serial `_authority_fresh()` yet compare slice-equal. Therefore the fold's freshness re-check is:
1. **Primary — reuse the existing serial gate.** Run `_authority_fresh()`/`_signoff_status()` (the SAME
   function the serial dispatch uses, campaign.py:2607 ✓ / 3433-3469 ✓) on the live plan. If it is not
   `"signed"` ⇒ **block for re-sign** via the existing `freshness_block` path (fail-closed, serial-identical) —
   this catches the `signed_by_human` flip and any digest-copy tamper, because it IS the real freshness check.
2. **Secondary — per-milestone drift discriminator.** If `_authority_fresh()` PASSES but `dispatch_epoch !=`
   live `signed_scope_hash` (the plan was re-signed to a new but valid epoch while the unit ran), recompute
   the **live** freshness slice (a-d) and compare it **byte-exact (canonical_json)** to the stored
   `dispatch_freshness_slice` to decide whether THIS milestone's scope changed (vs another milestone's
   insertion / a scope-neutral re-sign).
The completed unit is still folded (authorized at its dispatch epoch — matching serial, where a re-sign never
aborts the running unit). Then: primary-fail ⇒ `freshness_block`. Primary-pass + slice **equal** ⇒ no
`epoch_drift`, proceed. Primary-pass + slice **different** ⇒ set the **durable `epoch_drift`** gate (§3.1) —
  the milestone holds for explicit human re-validation and **does NOT auto-clear on `signed`** (the round-3
  hole: `campaign_plan_signoff` proceeds immediately on signed status, campaign.py:2187-2200 ✓). `epoch_drift`
  is a state field re-checked each resume, so a bug/tamper cannot silently continue stale-scope work.
This preserves signed-scope freshness (roadmap §7:330 ✓) on every fold, using the exact freshness inputs.

**Entry-order invariant (R0.7 Q2).** `_drive_parallel`/`_handle_resume_parallel` MUST call
`_reapply_engine_restamp()` **after `_load()` and BEFORE any fold/dispatch freshness consumer**, exactly as
serial `run()` does (campaign.py:2465-2472 ✓) — so a legitimately-grown plan (engine epoch) reads `signed`
this whole invocation and the primary `_authority_fresh()` check agrees with the pinned epoch.

---

## §6 Pause/resume under parallelism (R0 B-6)

### §6.1 Per-milestone pause records; resolver binds the right milestone

Each pause carries the FULL identity a decision must match today (run_loop.py:598-700 ✓). Resolver
change: unit pauses already bind `milestone_id`+`subsprint_id` via `checkpoint_path` (688-700 ✓);
`milestone_merge` (616 ✓) and `halt_condition_met` (660 ✓) read `milestone_runtime[decision.milestone_id]`
instead of singletons; fail-closed; serial falls back (byte-identical).

### §6.2 Parallel resume is ADDITIVE; serial dispatch AND resume are literally untouched (R0.6 B-6a/B-10)

The round-3→5 "`rt`-refactor of shared helpers" created a contradiction (R0.6 B-6a): rooting an AST guard at
`_drive_milestones` while claiming it is "literally untouched" is impossible — the serial loop legitimately
reads/writes singleton `self.state` throughout (campaign.py:2546-2548, 2634-2661 ✓). Resolution (Codex's
**keep-serial-untouched** option, the safer one given byte-identity is the #1 non-negotiable): **do NOT refactor
any serial helper.** The serial dispatch (`_drive_milestones`) AND serial resume (`_handle_resume` + every
helper it calls) stay **byte-for-byte the base `b81f6d5` code** — so default-off byte identity is true by
construction, needing no resume-gate goldens (the code is unchanged).

The parallel path is **fully additive**: `_drive_parallel` (dispatch/fold) + a parallel resume
`_handle_resume_parallel(mid)` that operate on `milestone_runtime[mid]` (and the coordinator-global fields).
They **reuse the PURE decision logic** shared with serial — `interpret_dispatch`/the `_DISPATCH_TABLE`
(campaign.py:207-335 ✓), `_envelope_milestone` (3007-3022 ✓), the `signoff_status`/`_authority_fresh` freshness
computation (§5.6), `run_unit` (3724 ✓), and `merge_into_trunk` (loop_ingress ✓) — but supply their **own thin
state-plumbing** against `milestone_runtime[mid]` instead of calling the singleton mutators (`_pause`,
`_commit_dispatch_resolution`, `_advance_milestone_cursor`, `_ensure_milestone_context`, `_complete_milestone`,
the halt-cascade mutators, etc.). Because the plumbing is genuinely different (a keyed map vs the singleton),
this is not gratuitous duplication; the correctness-critical *decisions* remain one shared implementation.

**Proof obligation — AST guard rooted at the PARALLEL entry points only (R0.6 B-6a):** an AST guard walks the
static call graph from `{_drive_parallel, _handle_resume_parallel}` (and the parallel helpers) and **fails if
any reachable parallel method reads/writes a singleton `self.state` pause/cursor field** (`pause_reason`,
`pause_checkpoint`, `milestone_index`, `subsprint_index`, `milestone_context`, `freshness_block`,
`halt_condition_pending`, `halt_condition_provisional`, `followup_baseline_seq`, `pending_milestone_advance`) —
the parallel path may touch ONLY `milestone_runtime[mid]` + the coordinator-global fields (`spent`, `units`,
`halt_condition_acks`, `engine_restamp`, `halt_condition_seq`, `gap_followup_state`). The serial path is
**exempt** (it is the untouched fast path and legitimately uses the singletons). The boundary callbacks
`run_unit`/`decision_resolver` (campaign.py:609, 2211 ✓) are injected and pure w.r.t. singleton state (R0.6 Q1)
— the guard treats a call through them as fail-closed (they receive only what the coordinator passes).

### §6.3 CLI reports ALL parked pauses (R0 B-6)

Add `pauses: [ {milestone_id, subsprint_id, pause_reason, checkpoint, condition_id, loop_id}, … ]` to the
run summary (run_loop.py:929-947 ✓), keeping the singular `pause_*` fields as the oldest-pause mirror.
`--resume` takes one `decision_path` selecting exactly one parked pause (resolver rejects a mismatch);
several pauses = several `--resume` calls (decision-dir deferred, R0.2 Q5 acceptable for v1). The notifier
(run_loop.py:908-927 ✓) fires per parked pause.

---

## §7 Isolation invariants, merge ordering, concurrency safety

### §7.1 Parallel-eligible ⇒ new_worktree required (fail-closed)

`current_branch`/`new_branch` share the admin working tree (loop_ingress.py:373-394 ✓); only
`new_worktree` gives a separate cwd (396-408 ✓). `max_concurrent>1` ⇒ every milestone's resolved strategy
MUST be `new_worktree`, enforced fail-closed at plan ingress (645 ✓) + mirrored in `charter_validator`.

**Dependency requires an actual merge (R0.3 B-14).** The ready-set requires deps `merged` (§4), but the
merge gate lets `open_pr`/`keep_branch` **advance without merging** (campaign.py:1152-1156 ✓) and
`merge_prompt_at_close` can be disabled (schema:144 ✓) — so a naive reading could unblock a dependent while
its dependency's code is NOT in trunk, branching the dependent off a trunk missing its dep. Fix, enforced
fail-closed for a `max_concurrent>1` plan: (1) `merge_prompt_at_close` MUST be `true` (the gate cannot be
disabled); (2) the `phase` distinguishes **`done`** (accepted, gate resolved via `open_pr`/`keep_branch` —
branch NOT in trunk) from **`merged`** (resolved via `merge_now` — in trunk); (3) a **dependency-target**
milestone (some other milestone `depends_on` it) **must** reach `merged` before its dependents become ready
— `done`-but-not-merged does NOT satisfy readiness; if the human resolves such a milestone `open_pr`/
`keep_branch` (no merge), its dependents stay blocked and the campaign **exits 10 needs-human** ("merge
required to unblock dependents", §4), never a silent stall or a dependent on a stale base. (4) A **leaf**
milestone (nothing depends on it) resolved `open_pr`/`keep_branch` is a **legitimate `done`-unmerged
terminal** (R0.4 B-14 / Q3 — independents keep the serial "advance without merging" freedom); it does not
strand the campaign (§4 termination). So `merge_now` is forced only where a real dependency needs the code
in trunk, not on every parallel milestone.

### §7.2 Merges coordinator-serialized; conflict re-pauses at milestone_merge (R0 B-7, CLOSED)

`merge_into_trunk` mutates the admin repo (562 ✓) — coordinator runs `_execute_milestone_merge`
(1171-1183 ✓) one at a time in `merge_policy` order (**first use** of schema:153 ✓: `fifo`|`human_order`).
On conflict (GitOpError 569-575 ✓) the coordinator **re-pauses at the existing `milestone_merge`
checkpoint** (resolvable + milestone-bound via §6.1), NOT `gate_hard_fail` (which the resolver treats as a
unit pause, 683 ✓). No new checkpoint kind. Never force-merge.

### §7.3 No mid-flight rebase (R0 N-1 upheld, conditions stated)

A milestone becomes READY only after all `depends_on` are `merged` (§4) ⇒ its worktree branches off the
then-current trunk (with its deps) ⇒ no running worktree needs rebase. Independent milestones' overlaps
surface at merge → re-pause at `milestone_merge`. N-1 caveat recorded: **semantic** (non-file)
cross-milestone conflict is a plan-authoring problem (declare `depends_on`/lock), documented (§11).

### §7.4 Worktree create+cleanup coordinator-owned (serialized, avoids `.git/worktrees` races, 400 ✓).

---

## §8 Budgets (R0 B-8, refined)

Because exactly one sub-sprint per milestone is in flight, budget is enforced **at the coordinator, per
dispatch, identical to serial**: before dispatching a milestone's next sub-sprint the coordinator checks
`_over_budget`-equivalent against `spent + inflight_count` (2562-2566 ✓ semantics); after each fold it
adds the actual `spend_delta` (2634-2638 ✓). `max_subsprints` cannot be exceeded (admission counts
in-flight, §4). `max_total_spawns`/`max_wall_clock` are only knowable post-unit, so a bounded overrun of
at most `max_concurrent-1` in-flight units is possible before the coordinator folds and pauses — the same
"checked between units" grain as serial, just with ≤N units concurrently in flight; the coordinator drains
running workers to quiescence on `campaign_budget_exhausted` (existing checkpoint, 149 ✓) — no mid-unit
kill. (Per the R0.3 ruling: the spawn/wall overrun is documented as **"up to `max_concurrent` units may be
in flight when the cap is crossed"** — a unit-grain bound, NOT a numeric spawn/minute guarantee; the signed
countable `max_subsprints` cap is never exceeded, §4.)

---

## §9 Checkpoints — no new kinds

merge conflict → re-pause at existing `milestone_merge` (§7.2); no-ready+parked → exit 10; deadlock →
impossible by construction (§4), guarded via existing pause machinery. Four-frozenset invariant untouched.

---

## §10 Config surface — `max_concurrent`, conditionally signed into H (R0 B-9, CLOSED)

- **Field.** `budget.max_concurrent` (int ≥1) in campaign-plan top-level `budget` (schema:107-116 ✓) +
  signed `authority.budget` (schema:57-64 ✓).
- **Conditional H emission.** `_resolve_plan_authority` (3053-3084 ✓) emits `max_concurrent` into
  `authority.budget` **only when set and >1**; absent/`==1` ⇒ omitted ⇒ H byte-identical to today's 3-key
  form (the `e2e_remediation` precedent, 3084 ✓). `signoff_snapshot_authentic` reconstructs identically
  (3390-3391 ✓) ⇒ old snapshots recompute unchanged, **no forced re-sign**; a plan setting >1 carries it
  in both stored + live, and a post-sign raise flips H ⇒ re-sign.
- **F1 activation — the parallel authority can NEVER bypass H (R0.7 B-15). TWO co-dependent Cluster-1 code
  changes, both specified here (current code has NEITHER — this is the design):**
  (i) **the activator** — `f1_required()` (campaign.py:3340-3356 ✓, today only signoff/covers_req_ids/
  milestone_signals) gains **`budget.max_concurrent > 1`**, so a parallel plan is always F1-active: a bare
  top-level `signed_by_human:true` with no `signoff` block reads `pre_f1` ⇒ pauses at `campaign_plan_signoff`
  for a proper `signoff`-block re-sign (without it, `_authority_fresh()` short-circuits `True` at
  campaign.py:1242 ✓ and `signoff_status()` treats bare `signed_by_human` as `signed` at 3431 ✓);
  (ii) **the H emission** — `_resolve_plan_authority()` (campaign.py:3053-3084 ✓, today emits only
  `max_subsprints`/`max_total_spawns`/`max_wall_clock_minutes`, 3063) additionally emits `max_concurrent`
  into `authority.budget` when set `>1` (§10 "Conditional H emission" above), so the value is bound into H
  (H is built from `_resolve_plan_authority` at 3132 ✓ and checked at 3435 ✓).
  **Both are REQUIRED and land together in Cluster 1: the activator alone forces a signoff-block re-sign but
  would not bind `max_concurrent` into H; the emission alone binds it but a bare-signed plan would still
  bypass the freshness check. Together they guarantee a `max_concurrent>1` plan runs only under a signed H
  that includes `max_concurrent`.** **Value-checked (>1), not presence** — serial `max_concurrent` absent OR
  `==1` leaves both `f1_required` and H byte-identical to today (a serial plan is never newly F1-forced).
- **Eligibility:** `max_concurrent>1` ⇒ all-`new_worktree` (§7.1) + declared `module_locks` to actually
  parallelize (else conservative serialization).
- **No compact-projection lockstep** (campaign-plan has none; mission-charter untouched). No autonomy change.

---

## §11 Impact inventory

**Code:** `campaign.py` — `_drive_parallel` coordinator (dispatch loop §2, scheduler §4, fold §5, resume
§6); `milestone_runtime` (+ pre-spawn `inflight`{`dispatch_epoch`,`dispatch_freshness_slice`}/`current_attempt_nonce`/
`folded`/`epoch_drift`/per-milestone `halt_condition_pending`+`halt_condition_provisional`) in
`CampaignState`/`to_dict`/`from_dict` (347-469); **`engine_restamp` + `halt_condition_seq` stay GLOBAL**
(R0.4 B-1/B-2b, B-6); `_check_state_consistency` parallel branch + cross-field ties incl.
`spent.subsprints_run==len(units)` (752-800); `run_unit` gains a `requirement_context` kwarg → coordinator
produces the WHOLE sidecar (incl. the per-milestone phase map + global engine_restamp), self-read branch
skipped (3819-3851); **ADDITIVE parallel resume** `_handle_resume_parallel(mid)` + parallel dispatch/fold
helpers operating on `milestone_runtime[mid]`, REUSING the pure decision logic (`interpret_dispatch`/
`_DISPATCH_TABLE` 207-335, `_envelope_milestone` 3007-3022, `signoff_status`/`_authority_fresh` §5.6,
`run_unit`, `merge_into_trunk`) but NOT the singleton mutators (R0.6 B-6a/B-10 — serial helpers untouched);
`epoch_drift` two-part every-fold freshness gate (existing `_authority_fresh` primary + exact slice secondary,
§5.6); worker **parent-`flock`-before-fork** launcher (§5.5); `_resolve_plan_authority` conditional
`max_concurrent` (3063); **`f1_required()` gains `budget.max_concurrent>1`** so a parallel plan is always
F1-active (R0.7 B-15, 3340-3356); ingress eligibility + `merge_prompt_at_close` requirement (645); merge serialization
+ `merge_policy` + `done`-vs-`merged` phase + conflict→milestone_merge (1152-1183, 2219). **Serial dispatch
`_drive_milestones` (2542-2697) AND serial resume `_handle_resume` (2174-2455) LITERALLY UNCHANGED.**
— **NEW** `campaign_worker.py` (single-sub-sprint executor + worker-owned lease sidecar + attempt-scoped
result). `run_loop.py` — per-milestone resolver (605-682); `pauses[]` + per-milestone-phase summary
(864-867, 929-947); **`print_campaign_result` (1029) + `CAMPAIGN_STATUS` (1068) phase-derived progress**
(R0.4 B-11b); multi-pause notifier (908-927); wire `max_concurrent`. `scope_report.py` —
`compute_coverage`/`compute_requirement_coverage` branch on `milestone_runtime.phase` (113-125, 314-332,
359/412). `charter_validator.py` — eligibility mirror (new_worktree + merge_prompt_at_close).

**Schemas:** campaign-plan (`budget.max_concurrent` + `authority.budget.max_concurrent` + H note 100);
campaign-state (`milestone_runtime`; **`units` item gains `attempt_nonce`**, 153-163); campaign-decision
(confirm `milestone_id` on all shapes).

**Docs/process:** campaign runbook parallel section (+ N-1 semantic-conflict caveat §7.3, + §8 in-flight-unit
overrun note); template example (default-off). `_sources.yaml`/kernel-coverage only if a governance doc
changes (expect none). Golden `test-prompts.json` unaffected.

**Tests:** `test_campaign.py` (serial default-off byte golden (serial dispatch+resume untouched ⇒ trivially
identical, R0.6 B-6a); ready-set; admission cap; fold idempotency re-run-vs-redelivery; per-milestone
`_check_state_consistency` ties + `spent==len(units)`; **AST guard rooted at `{_drive_parallel,
_handle_resume_parallel}` failing on any singleton-`self.state` pause/cursor touch**; serial path exempt;
delivery-derivation from phase). **NEW**
`test_campaign_parallel.py` (N=2 canary; merge order; `done`-vs-`merged` dependency gating + **leaf
`done`-unmerged terminal**; **parent-`flock`-before-fork crash-resume** adopt/fence (child-inherits-lock);
attempt-scoped stale-result
masking; **epoch-drift exact-slice** block on every fold that does NOT auto-clear on signed; budget cap under
N in-flight; heartbeat-in-sidecar not state). `test_run_loop_campaign.py` (per-milestone resolver +
`pauses[]` + phase-derived `print_campaign_result`/`CAMPAIGN_STATUS`). `examples/real-campaign-canary/` +
2-milestone disjoint-lock plan.

---

## §12 Phasing (each cluster → Codex impl gate)

1. **Cluster 1 — config + state + scheduler (no execution change).** `max_concurrent` schema +
   conditional-H + eligibility; `milestone_runtime` (+inflight/nonce/folded) + `_check_state_consistency`
   ties + additivity golden; `ready_set` + locks + per-dispatch admission + `merge_policy` (pure, tested).
2. **Cluster 2 — worker (single sub-sprint) + input contract + coordinator-produced `requirement_context`
   sidecar + `clock` + worker-owned lease sidecar + attempt-scoped result.** Prove one worker folds
   identically to serial (N=1 canary).
3. **Cluster 3 — `_drive_parallel` dispatch loop + exactly-once fold + every-fold epoch stamp/`epoch_drift`
   + N=2 canary + merge serialization (`done`-vs-`merged`) + conflict re-pause.**
4. **Cluster 4 — additive parallel resume (`_handle_resume_parallel` + AST guard rooted at parallel entries +
   resolver + `pauses[]`) + crash-resume/lease + `epoch_drift` block + delivery-derivation branch + budget
   drain; docs/template; whole-scope R3.**

---

## §13 Test / canary plan (Done-evidence, roadmap §7)

Byte-identical default-off golden (serial dispatch AND resume untouched ⇒ trivially identical, R0.6 B-6a);
**AST guard rooted at the parallel entry points** (no singleton-`self.state` pause/cursor touch on the parallel
path; serial exempt); N=2 parallel canary (concurrent, gates per-milestone, merge order, final trunk == serial);
fold idempotency (nonce); **parent-`flock`-before-fork crash-resume** adopt (no double-run) + **two-part
every-fold freshness** (`_authority_fresh` primary + exact-slice secondary) epoch-drift block that does not auto-clear on signed;
`done`-vs-`merged` dependency gating + leaf `done`-unmerged terminal; budget cap under N in-flight; gate
integrity (cross-milestone decision refused); lock serialization (empty-locks ⇒ serial byte-identical). Full
suite + kernel-coverage + load-closure green; expect the 1 pre-existing README red.

---

## §14 Risks & considered alternatives

- **Threads/async in-coordinator** — rejected (shared cwd, state races, no crash containment).
- **Whole-milestone worker (round-1 model)** — rejected per R0.2 B-8/B-12: budget/freshness could not be
  serial-identical; single-sub-sprint dispatch restores serial semantics at the cost of a child per
  sub-sprint (negligible vs agent wall-clock).
- **Audit at-least-once (§5.4)** — keyed duplicate possible; dedup-key detectable (R0.2 Q2 accepted).
- **spawn/wall bounded overrun (§8)** — inherent to concurrency; signed *subsprint* cap never exceeded.
- **`_save` atomic hardening** — separate follow-up (R0.2 Q3), not a Phase-4 blocker.

---

## §15 Open questions & invariants confirmed by Codex

**Ruled by R0.7 (fold as invariants):**
- Q1 (§6.2) — additive parallel resume + serial-untouched + AST guard at parallel roots is the **correct**
  B-6a/B-10 resolution (R0.7 N-2). The singleton helpers `_complete_milestone` (1530-1541) /
  `_execute_milestone_merge` (1171-1183) **must NOT be called from the parallel path** — the parallel path
  re-implements their state-plumbing on `milestone_runtime[mid]` and reuses only the pure layer.
- Q2 (§5.6) — the two-part freshness gate captures serial semantics, **with the entry-order invariant**:
  `_drive_parallel`/`_handle_resume_parallel` MUST run `_reapply_engine_restamp()` after `_load()` and
  **before** any fold/dispatch freshness consumer, exactly as serial does (campaign.py:2465-2472 ✓).
- Q3 (§5.5) — POSIX-fork `flock` inheritance is acceptable for v1 **if `pass_fds`/inheritable-fd is tested**
  (the delivery-loop adapters are already POSIX subprocess-based). Recorded portability caveat.

**For R0.8 (final confirmation):**
1. B-15 fold (§10): making `budget.max_concurrent>1` an F1 activator in `f1_required()` (value-checked,
   serial unaffected) fully closes the H-bypass — confirm no other `_authority_fresh` short-circuit path
   (campaign.py:1231-1244) lets a parallel plan run outside a signed H.
2. Is the design now APPROVE-able at implementation-design altitude (sound, self-consistent, implementable
   with its proof obligations), residual exactness deferred to the Cluster impl gates?

---

## §16 R0 fold log

**Cumulative CLOSED by Codex:** round-1 B-4/B-7/B-9/B-10; round-2 B-3/B-5, B-8. N-1, N-2 upheld;
Q2/Q3/Q4/Q5 rulings folded.

**Round 2 (fixes; B-1/B-2, B-6, B-11, B-12 further refined in round 3 below):**
| Finding | Resolution | Where |
|---|---|---|
| **B-1/B-2** (clock omitted; projection misses `engine_restamp`) | worker-input adds `clock`; projection covers all `compute_requirement_coverage` reads incl. `engine_restamp` | §5.1, §5.2 |
| **B-3/B-5** (single result path masks live higher-nonce worker) | attempt-scoped `result-<nonce>.json`; fold only when `nonce==current_attempt_nonce`; lease adopt/fence | §5.3, §5.5 |
| **B-6** (focus-accessor misses writes) | `MilestoneStateView` (read/write) + `_handle_resume(milestone_id=…)` covering all helper reads+writes | §6.2 |
| **B-8** (admission +1 doesn't cap a whole-milestone worker) | **execution model → one sub-sprint per dispatch**; budget checked per-dispatch + accounted per-fold, serial-identical | §0, §2, §4, §8 |
| **B-11** (state omits attempt/reservation fields) | `inflight`{attempt_nonce,dispatch_epoch,worker} + `current_attempt_nonce` + `_check_state_consistency` cross-field ties | §3.1, §3.3 |
| **B-12** (worker freshness weakened on resume) | stamp `inflight.dispatch_epoch`; on adopt/fold after resume compare to live signed scope; drift ⇒ fold-then-block-for-resign, never fold-and-continue | §5.6 |

**Round 3:**
| Finding | Resolution | Where |
|---|---|---|
| **B-1/B-2** (projection misses `cursor.milestone_index`; sidecar self-reads state) | **coordinator produces the WHOLE `requirement-context.json`** (Q2); `run_unit` `requirement_context` kwarg skips the self-read; sidecar carries `cursor.milestone_index`+status+milestone_outcomes+per-milestone `engine_restamp` | §5.2 |
| **B-6** (view misses `milestone_index`, `_pause`/`_commit_dispatch_resolution` writes, `halt_condition_provisional`) | **`rt`-parameterized helper refactor** (full enumerated set) + per-milestone `halt_condition_provisional` + AST guard | §3.1, §6.2 |
| **B-11a** (unit records lack `attempt_nonce`; budget undercount) | `units` item gains `attempt_nonce`; consistency tie `spent.subsprints_run==len(units)` | §3.1, §3.3, §11 |
| **B-11b** (`(len,0)` mirror falsely reports all delivered) | mirror = fail-closed `(0,0)`; `scope_report`+run-summary derive delivery from `milestone_runtime.phase` | §3.2, §3.2.1 |
| **B-12** (drift only on crash-resume; `campaign_plan_signoff` auto-clears on signed) | compare epoch on **EVERY fold**; durable `epoch_drift` gate cleared only by a **deterministic per-milestone scope-equality re-check**, never merely by "signed" | §3.1, §5.6 |
| **B-13** (NEW: worker heartbeat in state violates single-writer) | heartbeat in a **worker-owned lease sidecar**; coordinator writes only `{pid,start_epoch}` to state | §3.1, §5.5 |
| **B-14** (NEW: `open_pr`/`keep_branch`/disabled gate unblock dependents without a real merge) | parallel plans force `merge_prompt_at_close=true`; `phase` `done`≠`merged`; dependents require deps `merged`; else exit-10 needs-human | §7.1 |

**Round 4 (CLOSED by R0.4: B-3/B-5, B-8):**
| Finding | Resolution | Where |
|---|---|---|
| **B-1/B-2a** (sidecar omits per-milestone phase map ⇒ Driver misclassifies under `(0,0)`) | coordinator sidecar `campaign_state` carries the `milestone_runtime` phase/outcome map; Driver/scope_report tests consume the ACTUAL sidecar bytes | §5.2 |
| **B-1/B-2b** (per-milestone `engine_restamp` breaks whole-plan `apply_engine_restamp_to_plan`) | `engine_restamp` stays **GLOBAL** (one append-only delta chain, deltas carry milestone_id) | §3.1, §5.2 |
| **B-6a** (`rt` set misses transitive `_execute_milestone_merge`/`_is_authorized_followup_insertion`) | `rt` = **transitive closure**; AST guard covers transitive callees | §6.2 |
| **B-6b** (NEW: per-milestone `halt_condition_seq` ⇒ basename collision) | `halt_condition_seq` stays **GLOBAL** (collision-free nonce) | §3.1 |
| **B-10** (reopened: `rt` edits shared serial helpers ⇒ AST proves isolation not byte-identity) | add **byte-for-byte serial resume-gate goldens** (state+audit); `rt`-for-serial is a transparent `self.state` handle; fallback = untouched serial + parallel-only variants | §6.2, §13 |
| **B-11b** (more cursor consumers: `print_campaign_result`, `CAMPAIGN_STATUS`) | both derive phase-based progress; scalar cursor labelled legacy mirror | §3.2.1, §11 |
| **B-12** (equality check too narrow; hash can't reconstruct prior scope) | persist dispatch-time **canonical `_envelope_milestone` slice + authority** in `inflight`; compare **byte-exact every fold** (full H components) | §3.1, §5.6 |
| **B-13** (spawn-registration race: pid known only post-spawn) | **pre-spawn durable `reservation`** + worker **`flock`** launcher; resume flock-probe ⇒ adopt/fence | §3.1, §5.5 |
| **B-14** (leaf `done`-unmerged strands the campaign) | leaf `done`-unmerged = **legitimate terminal**; only dependency-targets require `merged`; else exit-10 | §4, §7.1 |

**Round 5 (RULED CLOSED by R0.5: B-1/B-2a, B-1/B-2b, B-6b, B-10, B-11b, B-14-concept):**
| Finding | Resolution | Where |
|---|---|---|
| **B-13** (fork-before-lock race: crash after fork, before child locks) | coordinator **acquires the `flock` BEFORE fork**; child **inherits** the locked fd atomically at fork (POSIX OFD-shared) ⇒ no unobserved-child window | §5.5 |
| **B-12** (slice misses H wrapper + digest freshness inputs) | `dispatch_freshness_slice` = H wrapper `{version,campaign_id,goal,charter_ref,charter_hash}` (3114-3132) + `_envelope_milestone` entry + whole authority + `milestone_signals_digest`+`prompt_artifacts_digest` (3448-3469); compare byte-exact every fold | §5.6 |
| **B-12/B-13** (slice not durable pre-spawn) | consolidate: **one pre-spawn `_save()`** writes `inflight` with `dispatch_epoch`+`dispatch_freshness_slice` (no post-spawn pid write; liveness = flock+sidecar) | §3.1, §5.5, §5.6 |
| **B-6a** (transitive `rt` set still incomplete: `_eval_halt_conditions`/`_ensure_milestone_context`/`_complete_milestone`/…) | proof target = **full dispatch/resume call graph**; the **AST guard walks the graph and is the completeness authority** (not a hand list) | §6.2 |
| **B-14/§3.4** (gap-followup exhaustion said `all merged`, contradicting leaf terminal) | §3.4 uses **`all_terminal`** (dependency-targets `merged`, leaf `done` allowed) | §3.4 |

**Round 6 (RULED CLOSED by R0.6: B-13, B-12/B-13-durability, B-14/§3.4; POSIX-fork caveat recorded):**
| Finding | Resolution | Where |
|---|---|---|
| **B-12** (slice can't replace `signoff_status`: `signed_by_human` flip / digest-copy tamper compare slice-equal) | **two-part every-fold gate**: PRIMARY = the existing `_authority_fresh()`/`_signoff_status()` (all signoff inputs incl `signed_by_human` 3433-3435 + digest-copy checks 3448-3469) → `freshness_block` if not `signed`; SECONDARY = the per-milestone exact-slice comparison (scope-drift discriminator only) | §5.6 |
| **B-6a/B-10** (AST guard rooted at `_drive_milestones` contradicts "serial untouched") | keep serial dispatch **and** resume **literally untouched**; parallel resume `_handle_resume_parallel` is **fully additive** (reuses pure decision helpers, own state-plumbing on `milestone_runtime`); **AST guard rooted at `{_drive_parallel, _handle_resume_parallel}` only** (serial exempt); no resume-gate goldens needed | §0, §6.2, §11, §13 |

**Round 7 (RULED CLOSED by R0.7: B-12 [N-1], B-6a/B-10 [N-2]; Q1/Q2/Q3 yes):**
| Finding | Resolution | Where |
|---|---|---|
| **B-15** (NEW: `max_concurrent>1` not an F1 activator ⇒ a bare-signed parallel plan bypasses H via the `_authority_fresh` short-circuit) | `f1_required()` gains **`budget.max_concurrent>1`** (value-checked) ⇒ a parallel plan is ALWAYS F1-active; a bare `signed_by_human:true` reads `pre_f1` ⇒ pauses at `campaign_plan_signoff` for a `signoff`-block re-sign binding `max_concurrent` into H; serial (absent/`==1`) unchanged ⇒ byte-identical | §10, §11 |

**Round 8 (R0.8 clarification — B-15 co-dependency made explicit):** R0.8 correctly noted B-15 needs BOTH the `f1_required` activator (i) AND the `_resolve_plan_authority` H-emission (ii) to land together; §10 now states both as co-dependent Cluster-1 changes (current code has neither — this is the design, not a claim about existing code). B-12 & B-6a/B-10 remain ruled-folded (R0.7 N-1/N-2).
