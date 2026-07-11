---
title: Campaign Loop (P-B)
doc_tier: process
doc_category: live
status: current
implementation_status: partial
source_of_truth: this file
last_reviewed: 2026-06-21
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 20KB
notes: >
  The Campaign Loop is the multi-milestone OUTER tier of the Delivery Loop
  (Concept 2; Constitution §3.7) — NOT the Auto Loop (Concept 1). It decomposes a
  goal into an ordered milestone backlog and auto-drives each milestone/sub-sprint
  through the UNCHANGED single-sub-sprint Driver, halting only at human-authority
  gates. Spec + rationale: archive/2026-06-20-autonomous-delivery-design.md §5.
  Implementation: engine-kit/orchestrator/campaign.py;
  schemas/campaign-{plan,state}.schema.json.
---

# Campaign Loop (P-B)

The Delivery Loop (Δ-18, `process/delivery-loop.md`) drives **one milestone** to
close. The **Campaign Loop** is the tier above it: given a goal, it decomposes the
goal into an **ordered milestone backlog** and drives the WHOLE backlog to
completion — auto-advancing through sub-sprints and milestones, pausing only where
human authority is required.

For human-facing operation, Campaign is normally reached through the **Control
Plane**, not by asking humans to remember CLI flags. The human says "continue",
"what is next?", or "insert a milestone before M3"; the Control Plane records the
intent and either resumes the current single-milestone Driver, prepares the next
role path, or invokes the Campaign runner when the adopter has explicitly opted
into `delivery_mode: campaign`.

**Naming (Constitution §1.7-E / §3.7):** the Campaign Loop is a multi-milestone
**extension of the Delivery Loop (Concept 2)** — the team delivering a goal. It is
NOT the Auto Loop (Concept 1; a single agent self-improving). The implementing
software is `engine-kit/orchestrator/campaign.py`.

## §1 Why it exists

Without it, the engine is a single-sub-sprint dispatcher: each `Driver.run()`
drives ONE sub-sprint and returns, so the human (or a driving agent) must decide
"what next?" at every boundary. The Campaign Loop makes the team work **backward
from the end goal** (以终为始): fix the milestone backlog up front, then drive it
continuously — pausing only at genuine human-authority gates.

## §2 Architecture — an outer deterministic loop over the inner one

The Driver is the deterministic outer loop over non-deterministic LLM work
(`delivery-loop.md` §4.1). The Campaign runner is a **HIGHER deterministic loop
over the Driver** — same shape, one tier up. The Driver is **unchanged**; all
campaign behavior is new code, so risk is contained.

```
goal
 │ Research: campaign contract → Deliver: ordered milestone backlog
 │ campaign_plan_signoff  (campaign-tier human gate — Customer signs the backlog)
 ▼
Campaign runner (campaign.py) — iterate milestones (topological) × sub-sprints
 │   per sub-sprint → Driver.run() (UNCHANGED) → inspect final_state
 │     • advance → next sub-sprint           • done → next milestone
 │     • anything else → PAUSE at a human gate (incl. gate1_pending)
 ▼
backlog exhausted → campaign done
```

## §3 The runner

### §3.1 Pause detection
The campaign reads each unit's `run_loop` summary `final_state` and **advances only
on `advance` or `done`**. EVERYTHING ELSE pauses — not only `STATE_HALTED` but the
guided pending states (`gate1_pending`, …). Never skip ahead on a non-advance state.

### §3.2 Budget — countable proxies (NOT `$`)
Real per-call `$` cost is unavailable (no adapter reports it; subscription harnesses
don't expose it). The campaign cap uses the COUNTABLE proxies the Driver already
surfaces: `subsprints_run`, `total_spawns` (summed `run_loop` `spawn_count`), and
`wall_clock_minutes` (active time, accumulated across resume — excludes paused
human-wait). `campaign.budget = {max_subsprints?, max_total_spawns?,
max_wall_clock_minutes?}` (optional; checked BETWEEN units → `campaign_budget_exhausted`).

### §3.3 Resume — two mechanisms
`Driver.run(resume=True)` only re-enters states that set `halt_resume_state` (the 3
spec-refinement halts) or the guided pending states; an ordinary human-gate
`STATE_HALTED` short-circuits. So resume splits:
- **Mechanism A (driver-resume):** `dev/review/acceptance_spec_refinement` +
  `customer_gate1_signoff` → the next dispatch carries `resume=True`; the Driver
  re-enters and re-resolves.
- **Mechanism B (campaign-dispatch):** every other gate → the campaign reads the
  resolved checkpoint decision and acts: advance-milestone / re-dispatch-fresh /
  surface a `deliver_followup_required` (a new unit Deliver must author) / end. The
  decision→action table + the ACTUAL driver option labels live in
  `campaign.py` (`interpret_dispatch`).

### §3.4 Fail-closed checkpoint coverage
A test (`test_campaign.py::TestCheckpointInventoryFailClosed`) AST-parses `driver.py`
for **every** `_write_checkpoint`/`_halt_checkpoint` id and asserts the campaign
classifies each. A future Driver checkpoint that is not classified FAILS THE BUILD —
the campaign can never silently skip a human gate.

### §3.5 Audit + resume
The campaign emits its own hash-chained audit ledger (its `campaign_id`, validated
path-safe) referencing each sub-sprint's `loop_id` (advance / done / pause events).
State persists to `campaign-state.json`; `run(resume=True)` continues from the cursor.

### §3.6 Per-milestone Acceptance via a derived execution context
The Driver fires its milestone-close Acceptance gate only at the TERMINAL sub-sprint
of `autonomy.approved_scope.subsprint_sequence` (`driver._milestone_complete`). A
single shared charter across a whole campaign makes only the campaign's LAST
sub-sprint terminal — so non-final milestones would close with NO Acceptance gate,
violating "Acceptance at every milestone close" (design §5). On every dispatch the
runner passes THIS milestone's LIVE sub-sprint sequence to the production
`make_run_unit`, which PROJECTS the canonical charter onto the milestone: a deep copy
whose `approved_scope.subsprint_sequence` is that sequence, so the milestone's final
sub-sprint is terminal and Acceptance fires per milestone. The sequence is read LIVE
(re-read at the top of each milestone loop, §3.1), so a governed mid-campaign edit (a
`deliver_followup` insertion) is reflected — not a snapshot taken at runner setup. The
derivation is **deterministic** (from the live milestone sequence + canonical charter),
records its source hashes (charter + signed-plan reference) in a per-unit
`derived-context.json` sidecar, and is **NOT** a re-signed charter (`customer_signed:
false`; the Customer signature stays on the plan, one tier up). It is sound only in
the runner's **`delivery_only`** mode (the Driver runs exactly the dispatched
sub-sprint); `make_run_unit` FAIL-CLOSED rejects `loop_mode=full_chain_guided`, whose
bootstrap would reset the run to `seq[0]` and mis-anchor terminality (per-milestone
guided decompose is deferred — §6). The campaign's pause-on-non-advance loop (§3.1)
then withholds the next milestone until this milestone's Acceptance/human gate is
resolved — the derivation only ensures the gate EXISTS. Real-Driver coverage (incl.
single-, two-, and multi-sub-sprint milestones): `test_campaign_e2e.py`.

### §3.7 Per-milestone functional-acceptance class (P-C projection)
A campaign milestone MAY carry an optional `functional_acceptance: static | browser_e2e`
(`schemas/campaign-plan.schema.json`). It selects, **per milestone**, whether the
milestone-close Acceptance gate runs the static (M1) F5 path or the browser-E2E (M3)
evidence path (`process/browser-e2e-acceptance.md`). There is **NO schema default** — the
key's ABSENCE is distinguishable from an explicit `static`, which is what makes precedence
well-defined. `derive_milestone_context` resolves the class as:

```
mode = milestone.functional_acceptance            if PRESENT (explicit OVERRIDES — incl. static)
     else charter.tooling.acceptance.functional.mode  if present (INHERITS the charter default)
     else "static"
```

The resolved `{mode, source ∈ {milestone, charter, default}}` is recorded in the per-unit
`derived-context.json` sidecar (alongside the projected `subsprint_sequence`, §3.6), so a
campaign can mix functional and static milestones — e.g. a charter-wide `browser_e2e`
default with a back-end-only milestone pinned to `static`, or a charter-wide `static`
default with one user-facing milestone pinned to `browser_e2e`. The Driver reads the
DERIVED charter, so `_acceptance_class()` is correct per milestone. The browser-E2E
mechanics (`tooling.e2e`) + signed checklist (`tooling.acceptance.functional.checklist_path`)
remain charter-level; the per-milestone key only flips the CLASS.

## §4 Gates (where the campaign pauses for a human)
The campaign-tier gate `campaign_plan_signoff` (the runner pauses until the
campaign plan's `signed_by_human` is true) PLUS every Delivery-Loop human gate the
Driver can emit (Gate-1, scope deviation, close C/D, gate hard fail, review
out-of-scope, acceptance fix/needs-human, the P-A advisory acceptance sign-off, the
loop-controller halts) PLUS `campaign_budget_exhausted`. `campaign_plan_signoff` is
enforced at the campaign tier (the runner), NOT folded into the charter validator
(which validates charters, not campaign plans), so the charter checkpoint floor
stays 9 (P-A).

### §4.1 Milestone-tier git isolation + merge gate (campaign `--repo-dir`)

When the campaign is driven with `--repo-dir <adopter-git-root>` AND the signed
campaign plan declares `milestone_isolation`, the runner sets up git isolation **once
per milestone** (NOT per sub-sprint):

| `milestone_isolation.default_strategy` | Behavior |
|---|---|
| `current_branch` | No git mutation; sub-sprints run in-place (default; byte-identical to pre-feature). |
| `new_branch` | `git switch -c <branch>` from `trunk_branch` at milestone start. |
| `new_worktree` | `git worktree add -b <branch>` at milestone start; sub-sprints run in the worktree dir. |

Branch names come from `branch_name_template` (default
`milestone/{campaign_id}/{milestone_id}`). Each milestone may override via
`milestones[].isolation_strategy: inherit|current_branch|new_branch|new_worktree`.

At **milestone close** (Acceptance `done`), when the milestone used an isolated
branch and `merge_prompt_at_close: true` (default), the campaign **pauses** at the
campaign-tier gate `milestone_merge` — NOT a 10th MANDATORY_CHECKPOINT. The human
authors a `campaign-decision.json` with `choice`:

- `merge_now` — engine executes a protected local `git merge --no-ff` into
  `trunk_branch` (aborts on conflict; never force).
- `open_pr` / `keep_branch` — advance to the next milestone without merging.
- `abort` — end the campaign.

Constitution §1.7-D: isolation strategies in the signed plan are **pre-authorized**;
merge still requires an explicit human `merge_now` decision.

### §4.2 Completeness gap-followup gate (Constitution §1.7-F; Track 2 Phase 2-γ)

When the backlog is exhausted, a requirement ledger is wired, and the plan is
**fresh-signed**, the runner runs a dedicated, fail-closed **gap-followup engine**
(`campaign._gap_followup_round`, run()'s OUTER loop) over the **completeness
`gap_report`** — the requirement ids in the human-signed F1 envelope AND signed into a
milestone's `covers_req_ids` AND **not yet delivered** (computed from coverage/ledger
FACTS only — `scope_report.build_gap_report` — the §1.7-F clause-0 SOURCE seal, NEVER the
Acceptance verdict's pass/fail clauses). It is **dormant** without all three preconditions
(byte-identical to before). A gap is **in-envelope scope completion, never expansion**.

For each eligible round the engine proves, deterministically: clause-0 SEAL (no quality
fault among the gap milestones); clause-1 **req_id-envelope check** —
`covered_req_ids ⊆ (authentic F1 snapshot ∩ the milestone's signed covers_req_ids)`,
DISTINCT from the module/layer `post_gate1_scope_expansion` guard; clause-2 RUNTIME bounds
— `gap_followup.max_subsprints` per milestone, a strict **proper-subset** progress check
vs the persisted gap-set history (NOT identical-hash — catches A/B churn), and an
absent-campaign-budget **effective-cap** (from `charter.budget.max_fix_rounds_total`, never
unbounded). On ANY failure it **HALTs and escalates to `needs_human`** (clause 3) — never a
silent stop, never a loop.

Autonomy routing: under `human_on_the_loop` (or higher) the engine **auto-dispatches** a
bounded remediation sub-sprint (no fresh human-confirm) and re-checks the gap; under
`human_in_the_loop` a gap_report **routes to `needs_human`** — the campaign pauses at the
campaign-tier gate **`completeness_gap_review`** (NOT a 10th MANDATORY_CHECKPOINT). Each
pause writes a checkpoint with a **per-pause nonce** (a monotonic `gap_review_seq` in its
basename) so the file-based resolver refuses a stale `remediate` file from an earlier round
(the "ONE bounded round" binding). The human authors a `campaign-decision.json` with the
**adjust_scope** `choice` + that checkpoint basename (NO `subsprint_id`):

- `remediate` — authorize ONE bounded, in-envelope remediation round (the SAME clause
  0/1/2 gates as the auto path; grants no ship/scope-widen authority).
- `accept_gap` — accept the incomplete signed scope and finish (no remediation).
- `abort` — end the campaign.

The quality `fix_required → human-confirm → Deliver` path (§3.5) is **unchanged at every
autonomy level**. The generated remediation's in-envelope `covered_req_ids` is recorded as a
Deliver-readable `gap-followup-stanza.json` sidecar and in `campaign-state.gap_followup_state`
(the per-milestone counter, gap-set history, and stanza audit).

### §4.3 Pre-set structural halt conditions (Phase-3; `autonomy.halt_conditions`)

A DECLARATIVE, default-OFF, tighten-only lever (design
`archive/2026-07-09-phase3-halt-conditions-design.md` §3). The human pre-declares STRUCTURAL halts
the engine has no built-in gate for — "*pause before this specific milestone / sub-sprint /
acceptance-class even when everything passes clean*". Each condition is a PURE predicate over
already-audited, plan-static facts (a CLOSED whitelist: `milestone_id` | `subsprint_id` |
`milestone_functional_acceptance`; ops `==`|`!=`|`in`|`not_in`) evaluated at **EP-pre** — before a
unit is dispatched, after the freshness gate. A match PAUSES the campaign at the campaign-tier
checkpoint **`halt_condition_met`** (NOT a 10th MANDATORY_CHECKPOINT), carrying the condition id +
evaluated facts, with a per-pause nonce basename `…__halt_condition_met__r{seq}.md`. It is resolved
Mechanism-B via an identity-bound decision (campaign_id + pause_reason + the nonce basename +
`condition_id` + `milestone_id`; no `subsprint_id`):
- `proceed` — acknowledge this condition (once per its scope — milestone or sub-sprint) and
  re-dispatch the SAME not-yet-run unit (the cursor never advances).
- `abort` — end the campaign.

A condition can NEVER change a verdict, pick a route, or auto-resolve anything (the schema has no
action/route/outcome field) — it only HALTs, so it needs no constitutional amendment. Outcome-based
halts remain the constitution's own event-triggered gates (`gate_hard_fail`, `close_taxonomy_C_or_D`,
`advisory_acceptance_pass_signoff`, …); halt_conditions adds only the structural dimension. Absent/
empty ⇒ byte-identical to a pre-Phase-3 campaign.

### §4.4 Push-not-poll notifier (Phase-3; `notifications.on_pause`)

Optional, default-OFF (design §4). On EVERY campaign pause (exit 10), the runner fires the charter's
`notifications.on_pause` argv hook — a TRUSTED, adopter-owned side-effecting hook (argv LIST, no
shell; pause context injected as `AIDAZI_PAUSE_*` env vars) — AFTER the pause is durably persisted.
It is FAIL-SAFE (a failed/timed-out notifier never affects the pause or exit code), BOUNDED (timeout
≤ 60s), and AUDITED with REDACTED metadata (`argv0`/`argc`/`sha256` — never the full argv/env/
output) as a `campaign_pause_notified` event. It cannot influence governance (resume re-validates any
decision file fail-closed). It fires for the campaign-runner pauses; the `--requirement` bootstrap
pauses are a separate pre-campaign path (a documented follow-up).

## §5 Artifacts
- `schemas/campaign-plan.schema.json` — the ordered milestone backlog (+ `depends_on`
  / `module_locks` / `milestone_isolation` / per-milestone `isolation_strategy` /
  `trunk_branch`; `merge_policy` remains a forward-compat seam for a future parallel
  runner).
- `schemas/campaign-state.schema.json` — the persisted, resumable campaign state.

`campaign-plan.json` is authoritative only in `delivery_mode: campaign`. In the
default `single_milestone` topology, `charter.yaml` is the executable source for
the active milestone, and `campaign-plan.json` may be absent or stale without
blocking delivery. New adopters should treat `docs/milestone-backlog.md` as a
generated human-readable projection, not a second hand-edited plan.

### §5.1 Scope-coverage report (read-only; Phase 0)
The runner surfaces only `milestone_index/milestones_total` at close — a progress
fraction, not "signed backlog vs delivered". `engine-kit/orchestrator/scope_report.py`
is a **pure, read-only** projection over the (plan, campaign-state[, baseline]) that
answers, after any number of milestones: what is **delivered**, what is still
**in_progress / not_started** (the *continue menu*), and — against an optional frozen
baseline — what was **added mid-flight**. It touches no governed artifact, adds no
checkpoint, and `run_campaign_entry` computes it guarded (a reporting bug can never
break a run) and prints a parallel, additive `SCOPE_COVERAGE=` line (the
`CAMPAIGN_STATUS=` contract stays byte-identical).

Because the plan **mutates in place** (a `deliver_followup` insertion edits
`subsprint_sequence` — §3.3), "what was added" is only exact against a snapshot frozen
at sign-off. Freeze it **once**, right after `campaign_plan_signoff`:
```
scope_report.py --plan <plan.json> --freeze-baseline --campaign-home <home>
scope_report.py --plan <plan.json> --campaign-home <home>          # later: the report
```
Without a baseline, delivered/pending/drift stay exact — only added/removed-milestone
detection is unavailable, and the report says so rather than guessing. This is Phase 0
of the scope-ledger gap (investigation 2026-06-22); a requirement-granular PRD ledger
(`covers_req_ids`, Acceptance write-back, drift log) is a later, governance-gated phase.

## §6 Status + open work
Implemented (Codex-reviewed): the runner (iterate / pause-detect / spend / audit /
resume two-mechanisms / plan-signoff), the fail-closed inventory, the production
`run_unit` wrapper (`make_run_unit` around `run_loop`, converting `GateHardFail` to a
paused unit), **per-milestone Acceptance via the derived execution context** (§3.6) —
so every milestone closes through its own Acceptance gate, with real-Driver
production-path coverage in `test_campaign_e2e.py` — AND the **wired CLI entrypoint**
`engine-kit/scheduling/run_loop.py --campaign <plan.json>` (`run_campaign_entry`): it
loads + schema-validates the plan, drives the backlog via the production path, and
returns STABLE exit codes (**0** done / **10** paused-for-a-human / **11** ended /
**2** invalid) plus a machine-readable `CAMPAIGN_STATUS=` status line. Human gates are
resolved either by editing the PLAN (`campaign_plan_signoff` → `signed_by_human: true`;
`milestone_decompose_required` → fill `subsprint_sequence`; `deliver_followup_required`
→ Deliver inserts the sub-sprint) or, for a Mechanism-B sign-off/route gate, by an
**identity-bound decision file** (`schemas/campaign-decision.schema.json` — honored only
when its `campaign_id` + `pause_reason` + `checkpoint`(basename, exact) AND — for a unit
pause — the live paused unit's `milestone_id` + `subsprint_id` (read from
`campaign-state.json`) all match; fail-closed, so a stale decision from another
milestone/sub-sprint/gate — even one with a colliding checkpoint basename — can't be
replayed. It carries `choice` for a dispatch-table gate, or `confirm`(+`route`) for the
`acceptance_fix_required` gate (§3.5); `--resume --decision <file>`). A fresh-process
`--resume` re-dispatches no completed unit and re-counts no Acceptance (the runner's
presence-/crash-recovery guarantees). CLI coverage:
`engine-kit/scheduling/tests/test_run_loop_campaign.py`.

The per-milestone `full_chain_guided` decompose of an empty `subsprint_sequence` is
surfaced (`milestone_decompose_required`), not yet auto-driven.

## §6.5 Parallel milestone execution (Phase-4 — default-OFF)

Set `budget.max_concurrent > 1` to run **N dependency-independent milestones
concurrently**, each in its OWN git worktree, folding results into the single-writer
campaign state — ~N× throughput without weakening any gate. **Absent or `== 1` ⇒ the
serial runner above runs byte-for-byte the same (default-OFF is byte-identical).**

- **Opt-in requirements (fail-closed at plan ingress).** A `max_concurrent > 1` plan
  MUST resolve every milestone to `new_worktree` isolation AND keep
  `merge_prompt_at_close: true` (§7.1). Declare disjoint `module_locks` per milestone to
  actually parallelize — an **empty** lock set conflicts with everything (conservative), so
  a legacy no-locks plan runs serially even at `max_concurrent > 1`. `max_concurrent` is
  bound into the signed authority H, so a parallel plan is always F1-active (re-sign with a
  `signoff` block).
- **Execution model.** One coordinator (sole writer) + isolated **worker child processes**;
  exactly **one sub-sprint per milestone in flight at a time**, so freshness / halt / budget
  are enforced per-dispatch = serial-identical. A worker executes one sub-sprint in its
  worktree and writes an atomic attempt-scoped `result-<nonce>.json`; the coordinator folds
  exactly once by `(loop_id, attempt_nonce)`, re-checks signed-scope freshness on **every**
  fold (a mid-flight scope drift parks that milestone at `epoch_drift` for human
  re-validation), then dispatches its next sub-sprint. A crash-resume adopts a live worker
  (inherited `flock`) or fences a dead one and re-dispatches — never double-runs a worktree.
- **Merges are human-gated + coordinator-serialized (§1.7-D).** Each completed milestone
  parks at `milestone_merge`; the CLI reports EVERY parked pause (`pauses[]` /
  `CAMPAIGN_MILESTONES=`), each resolved by its own `--resume --decision` (`merge_now` runs a
  protected local `--no-ff` merge; a conflict re-pauses at `milestone_merge`, never
  force-merges). A dependency-target must reach `merged` before its dependents start.
- **Reporting.** Under parallelism the scalar `milestone_index` is a fail-closed `(0,0)`
  legacy mirror; progress + coverage are **phase-derived** from `milestone_runtime`
  (`merged`/`done` ⇒ delivered).
- **Bounds (§8).** The signed `max_subsprints` cap is never exceeded (admission counts
  in-flight); `max_total_spawns`/`max_wall_clock` are post-unit, so **up to `max_concurrent`
  units may be in flight when a cap is crossed** — a unit-grain bound, then the coordinator
  drains to quiescence and pauses `campaign_budget_exhausted`.
- **N-1 caveat (§7.3).** A **semantic** (non-file) cross-milestone conflict that git can't
  see is a plan-authoring problem — declare `depends_on` or a shared `module_lock`.
- Code: `campaign.py` (`_drive_parallel`/`_handle_resume_parallel`) +
  `campaign_worker.py`. Coverage: `orchestrator/tests/test_campaign_coordinator.py`,
  `test_campaign_parallel*.py`. Design: `archive/2026-07-10-phase4-parallel-campaign-runner-design.md`.

## §7 Editing this doc
Process-tier; edits at fold-back cadence (Constitution §8). The code in
`engine-kit/orchestrator/campaign.py` is the implementation; the design rationale is
`archive/2026-06-20-autonomous-delivery-design.md` §5. If this file and the code
disagree, reconcile at fold-back.
