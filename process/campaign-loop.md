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

## §5 Artifacts
- `schemas/campaign-plan.schema.json` — the ordered milestone backlog (+ `depends_on`
  / `module_locks` / `merge_policy` / `isolation_strategy` forward-compat seams for a
  future parallel runner; sequential runner enforces topological order + rejects
  duplicate/cyclic/unknown deps).
- `schemas/campaign-state.schema.json` — the persisted, resumable campaign state.

## §6 Status + open work
Implemented (Codex-reviewed): the runner (iterate / pause-detect / spend / audit /
resume two-mechanisms / plan-signoff), the fail-closed inventory, the production
`run_unit` wrapper (`make_run_unit` around `run_loop`, converting `GateHardFail` to a
paused unit), and **per-milestone Acceptance via the derived execution context**
(§3.6) — so every milestone closes through its own Acceptance gate, with real-Driver
production-path coverage in `test_campaign_e2e.py`. **Parallel execution of
dependency-independent milestones is DEFERRED**:
the sequential runner enforces deterministic topological order and rejects
duplicate/cyclic/unknown deps, but **lock contention (`module_locks`) and parallel
execution are NOT implemented** — those schema fields are forward-compat seams for a
future parallel runner. The per-milestone `full_chain_guided` decompose of
an empty `subsprint_sequence` is surfaced (`milestone_decompose_required`), not yet
auto-driven.

## §7 Editing this doc
Process-tier; edits at fold-back cadence (Constitution §8). The code in
`engine-kit/orchestrator/campaign.py` is the implementation; the design rationale is
`archive/2026-06-20-autonomous-delivery-design.md` §5. If this file and the code
disagree, reconcile at fold-back.
