---
title: Autonomous Delivery Design — Acceptance auto-run + functional/E2E gate + Campaign loop
doc_tier: process
doc_category: intermediate
status: draft-for-review
implementation_status: design-only
source_of_truth: this file (until folded into constitution/delivery-loop at implementation)
last_reviewed: 2026-06-20
review_cadence: this fold-back sub-sprint
revision: rev5 (P-B resume map corrected vs driver code: +loop_controller halts, real option labels, two resume mechanisms)
load_discipline: on-demand
notes: >
  DESIGN SPEC ONLY — no code yet. Consolidated design for three confirmed gaps in
  the v2-loop-engine delivery loop, reviewed by Codex gpt-5.5 (xhigh) BEFORE any
  implementation. rev2 folds in Codex round-1 (VERDICT: REVISE): corrected current
  behavior, canonical charter namespace, advisory-pass-must-halt authority matrix,
  narrowed constitutional amendment, orchestrator-owned (not Acceptance-owned)
  browser executor, signed/frozen functional checklist, full calibration identity,
  Campaign state-machine semantics, opt-in default for existing charters.
---

# Autonomous Delivery Design (2026-06-20) — rev3

## §0 How to review this document

Design spec, not implementation. No code changed. The reviewer (Codex gpt-5.5,
xhigh) should judge: (1) soundness, (2) constitution-invariant consistency
(`governance/constitution.md` §1.7-*, §3.*, §7.0, §10; `process/delivery-loop.md`
§4.2.*), (3) backward compatibility (default path), (4) gaps/risks. Judge the
design, not the prose.

**rev2 changelog (what Codex round-1 changed):**
- §1.1 — corrected: uncalibrated autonomous Acceptance does NOT currently stay
  advisory; it **ships** `pass` (driver.py:2980; test_driver.py:611-612). Our #1
  change *tightens* this.
- §1.4 (NEW) — canonical charter namespace: today the driver reads
  `charter.acceptance.{enabled,on_fix_required}` (top-level) but
  `charter.tooling.acceptance.judge_calibration` (under tooling); schema *requires*
  `tooling.acceptance`. Canonicalize to `tooling.acceptance.*`.
- §3.2 — authority matrix added; advisory `pass` HALTs for sign-off, never reaches
  `STATE_DONE`. Constitutional amendment narrowed.
- §4 — browser E2E is an **orchestrator-owned evidence executor**, NOT an
  Acceptance skill/sub-agent; Acceptance mounts only evidence-**reading** skills.
  Functional checklist is signed/frozen with the closure_contract (not
  Deliver-mutable).
- §4.4 — calibration **records** keyed by full judge identity (not a bare M1/M3
  class field); separate record per class/mode.
- §5.4a (NEW) — Campaign state-machine semantics (cursors, retry/idempotency,
  budget aggregation, pause/resume, terminal states, GateHardFail, audit linkage).
- §7/OQ-2 — default-on is **opt-in for existing charters**; advisory default only
  for new charter versions/templates.
- §8 — all OQ-1..7 resolved per Codex; §10 residual risks added.

**rev3 changelog (what Codex round-2 changed — REVISE on precision, not shape):**
- §1.4 — `mode`/`enabled` migration made implementable: a **normalize-BEFORE-validate**
  pass (root `additionalProperties:false` + structure-before-warning at
  `charter_validator.py:1173` makes "warn on top-level" otherwise impossible) + an
  explicit both-present conflict rule.
- §3.3 / §5.4 / §9 — the hard-coded "**8** MANDATORY_CHECKPOINTS" in
  constitution §1.7-D, delivery-loop §4.2.3, `charter_validator.py:215` are updated to
  the new default set; #9 lands in P-A, #10 in P-B, with tests.
- §4.3 / §4.6 — functional checklist **criteria** (Research-owned, signed) split from
  executor **mechanics** (executor contract; Deliver/adopter-owned, mutable).
- §4.4 — calibration records are per **class** keyed by judge identity; `mode` is
  orthogonal policy, removed from the key.
- §5.4 / §5.4a — campaign **budget** schema (per-unit allocation + campaign cap +
  cumulative actual-spend source + precedence vs per-run `BudgetExceeded`) and
  resolved-checkpoint **resume** transitions specified.

**rev4 changelog (P-B prerequisites resolved against the actual runtime, before P-B impl):**
- §5.4/§5.4a — the campaign budget is reframed to **countable proxies** the engine
  already tracks + surfaces (`run_loop` returns `spawn_count`/`fix_round`,
  `run_loop.py:367`): `max_subsprints` / `max_total_spawns` / `max_wall_clock_minutes`.
  Real `$` cost is OUT OF SCOPE — no adapter reports it and subscription harnesses
  don't expose per-call cost (the charter's `max_api_usd` caveat). This resolves
  Codex round-3 P-B blocker (a) WITHOUT new adapter wiring.
- §5.4a — the `pause_reason→resume` map is made **exhaustive against the 12 checkpoint
  ids the driver actually emits** (verified in `driver.py`): `customer_gate1_signoff`,
  `post_gate1_scope_expansion`, `dev/review/acceptance_spec_refinement`,
  `gate_hard_fail`, `scope_deviation`, `close_taxonomy_C_or_D`, `review_out_of_scope`,
  `acceptance_fix_required`, `acceptance_surface_approve`,
  `advisory_acceptance_pass_signoff` — plus the 2 campaign-level
  (`campaign_plan_signoff`, `campaign_budget_exhausted`) and a fail-closed catch-all.
  Resolves Codex round-3 P-B blocker (b).

**rev5 changelog (Codex P-B-design round corrected the resume map against driver.py):**
- §5.4a — added the two omitted halts `loop_controller_halt` + `loop_controller_escalate`
  (emitted via `_halt_checkpoint`, `driver.py:2321/2337`); corrected option labels to the
  ACTUAL checkpoint options (`post_gate1_scope_expansion`: widen_approved_scope/narrow_plan/
  abort `driver.py:1936`; `review_out_of_scope`: open_followup_subsprint/accept_and_advance/
  abort; `gate_hard_fail`: context-dependent); and split resume into **two mechanisms**
  because `Driver.run(resume=True)` only re-enters `halt_resume_state`/guided-pending states
  (the 3 spec-refinements + gate1) — an ordinary human-gate `STATE_HALTED` short-circuits
  (`driver.py:2100`), so the campaign interprets those decisions to dispatch the next unit /
  advance / end. Campaign **pause = run final_state ∉ {advance, done}** (covers
  `gate1_pending`, not only `STATE_HALTED`).

The spine: today the engine is a **single-sub-sprint deterministic dispatcher**
that returns control at every boundary. The redesign makes the team (a) verify the
running product from the user's perspective before shipping, (b) run Acceptance by
default with no silent ship and no silent skip, and (c) drive a whole goal to
completion, pausing only at genuine human-authority gates. Naming (Constitution
§1.7-E): the new outer loop is the **Campaign** tier — a multi-milestone extension
of the Delivery Loop (Concept 2), NOT the Auto Loop (Concept 1).

---

## §1 Problem statement (confirmed against code)

### §1.1 Gap #1 — Acceptance is default-OFF + silent-skip when disabled, and silent-SHIP when uncalibrated

- `_acceptance_enabled()` (`driver.py:2470-2474`) → `bool(charter.acceptance.enabled)`,
  **default false**, to keep "P2 close→advance byte-identical".
- `_handle_close()` (`driver.py:2452-2467`): disabled → **no-op**; run ends in
  `STATE_ADVANCE` with **no checkpoint/notice**. Milestone ships unverified, silently.
- **Correction (Codex round-1):** when enabled + `uncalibrated` +
  `fully_autonomous_within_budget`, `_calibration_gate()` (`driver.py:2520-2565`)
  auto-degrades autonomy to `human_on_the_loop`, then `_handle_acceptance_verdict()`
  **still ships** a `pass` to `STATE_DONE` (`driver.py:2980-2986`).
  `test_driver.py:611-612` asserts exactly this ("degraded → pass ships",
  `STATE_DONE`). So the *current* behavior is: uncalibrated autonomous Acceptance
  runs and **auto-ships pass without human sign-off**. Our #1 change both (a)
  turns Acceptance on by default and (b) makes an advisory/uncalibrated `pass`
  **HALT for human sign-off instead of shipping** — a deliberate tightening that
  updates `test_driver.py:611`.
- The literal prompt the user saw ("…enabled: false … What do you want for the
  enabled flag?") has **zero grep hits**; it was the loop-driving agent surfacing
  the disabled-skip decision conversationally — a symptom of the silent default-off.

**Decision (user):** default Acceptance **ON** in **advisory** mode; uncalibrated
runs and produces a verdict that the human signs off before ship.

### §1.2 Gap #2 — No role verifies the running product from the user's perspective

| Role | Verifies | Runs the real app? |
|---|---|---|
| Dev | unit tests (handoff §3/§6) | **No** |
| Code Reviewer | static; "You do not run scripts" (`code-reviewer-agent.md`) | **No** |
| Deliver | plans/closes; §3.4 #5 bars running review/acceptance | **No** |
| Acceptance | reads F5 artifacts (`eval/runs/<id>/…`); §6 read-only | **Indirect only** |
| Research | authors semantic `closure_contract` | **No** |

- The framework never requires `tooling.eval.cmd` to exercise the **running app**
  (browser/HTTP/UI). No browser/Playwright/Selenium capability exists anywhere
  (`adapters/headless.py` is an LLM HTTP harness).
- Calibration is binary (`calibrated|uncalibrated`) with no notion of *which*
  acceptance skill-set was calibrated.

**Decision (user):** layered model, keep the 5-role chain: Dev owns
unit/integration + a **mandatory self-smoke** of the running app before handoff;
Code Reviewer stays static; Deliver coordinates the functional test plan + collects
evidence but does NOT own the verdict; **Acceptance owns the authoritative
user-perspective functional/E2E verdict**, judging captured evidence read-only.
Because this expands the Acceptance skill-set/authority, M1 calibration is NOT
reused; M3 functional Acceptance stays **advisory** until an M3-class browser/E2E
bad-case suite is calibrated.

### §1.3 Gap #3 — The engine stops after one sub-sprint; nothing drives the whole goal

- `Driver.run()`: "**Drive one sub-sprint** end-to-end" (`driver.py:1972-1973`).
- A clean non-terminal close sets `STATE_ADVANCE`, records `next_subsprint` in the
  audit (`driver.py:2454-2456`), and `_drive()` **returns** (`driver.py:2115`) —
  **next_subsprint is never dispatched**. Caller must re-invoke.
- `_milestone_complete()` (`driver.py:2476-2511`) only detects terminality;
  the sequence is **never iterated**.
- `delivery-loop.md` §4.2.4-G `full_chain_guided` already decomposes **one
  milestone → ordered sub-sprint sequence** + Gate-1 sign-off + scope-expansion
  guard — but there is **no tier above milestones** and **no iteration loop**.
- §4.2.1: "It does NOT start spontaneously."

**Decision (user):** add an outer **Campaign loop (sequential)**: decompose goal →
ordered milestone backlog up front (以终为始), auto-dispatch each sub-sprint and
milestone, **halt only at human-authority gates**. The single-sub-sprint driver is
unchanged. Parallel deferred (schema seam only).

### §1.4 Cross-cutting precondition — canonical charter namespace (Codex blocking #1)

The acceptance config is read inconsistently today:
- `charter.acceptance.enabled` — top-level (`driver.py:2473`).
- `charter.acceptance.on_fix_required.route_options` — top-level (`driver.py:2991`).
- `charter.tooling.acceptance.judge_calibration.status` — under `tooling`
  (`driver.py:2516`).
- The JSON schema **requires** `tooling.acceptance` (`mission-charter.schema.json:91-93`);
  `delivery-loop.md` §4.2.2 documents `tooling.acceptance.*`.

**Resolution: canonical = `tooling.acceptance.*`,** via a **normalize-BEFORE-validate**
pipeline (Codex round-2 blocking #1). Today the root schema is
`additionalProperties: false` (`mission-charter.schema.json:7`) so a top-level legacy
`acceptance` block is *structurally rejected*, and the validator runs structural
validation before any semantic warning (`charter_validator.py:1173`) — so a plain
"warn on top-level" is NOT implementable. P-A must therefore:
1. **Normalize first** (a pre-validation pass on the raw charter dict, before JSON-schema
   validation): if a top-level `acceptance` block exists, move it under
   `tooling.acceptance` and emit a `charter_namespace_deprecated` warning; if
   `tooling.acceptance.enabled` is present and `mode` absent, derive
   `mode` (`true→auto`, `false→off`) **silently** (the field is deprecated via the
   schema `description` + template/docs — the common existing shape is not nagged;
   only the genuine migration cases below warn).
2. **Conflict rule** when BOTH `enabled` and `mode` are present: if they agree
   (`enabled:true ↔ mode∈{advisory,auto}`, `enabled:false ↔ mode:off`) → accept with
   the deprecation warning; if they disagree → **hard validation error** (never silently
   pick one).
3. **Then validate** the normalized charter against the schema (which now defines `mode`
   and makes `enabled` optional — §3.4).
4. Change the driver's top-level reads (`driver.py:2473,2991`) to `tooling.acceptance.*`.
5. Update `templates/mission-charter.yaml`; add tests for each migration path
   (only-`enabled`, only-`mode`, both-agree, both-disagree, top-level-legacy).
This is a prerequisite for every §3 change (which adds fields under `tooling.acceptance`).

---

## §2 Constraints from the constitution (must honor or amend explicitly)

- **§3.4 #2 + §1.7-C** — Acceptance spawn surfaces: human paste OR charter-permitted
  orchestrator; never Research/Deliver/Dev.
- **§3.4 #4** — Research-Acceptance contract symmetry: Acceptance judges ONLY the
  Customer-signed closure_contract; criteria are not author-able by Deliver/Dev.
- **§3.4 #6** — a role's skill-set is part of its calibration identity.
- **§3.5 + §10** — Acceptance `fix_required → Deliver` requires a written
  human-confirm checkpoint; never silent.
- **§3.6 + §7.0** — uncalibrated autonomous Acceptance auto-degrades to
  `human_on_the_loop`; degradation is mandatory.
- **§1.7-D** — the 8 MANDATORY_CHECKPOINTS may be ADDED to, never bypassed.
- **§1.7-E / §3.7** — Auto Loop (Concept 1) ≠ Delivery Loop (Concept 2). Campaign
  is Concept 2.
- **§8** — governance edits are timeless/principle-level, land at fold-back.

---

## §3 Design #1 — Acceptance default-on + advisory auto-run (no silent ship, no silent skip)

### §3.1 Target behavior

1. **Default ON (advisory).** Absent/unspecified `tooling.acceptance.mode` →
   `advisory` for **new** charter templates/versions; existing charters are NOT
   silently flipped (see §3.5). Explicit `mode: off` opts out cleanly.
2. **Advisory verdict NEVER auto-ships.** An advisory `pass` writes the new
   `advisory_acceptance_pass_signoff` checkpoint and HALTs; the human signs to ship.
3. **Authoritative auto-ship requires calibration.** A `pass` reaches `STATE_DONE`
   only when the verdict is `authoritative` (calibrated for the active class AND
   autonomy permits unattended ship — see §3.2 matrix). This *removes* today's
   uncalibrated-pass-auto-ship (`driver.py:2980`).
4. **fix_required / needs_human** routing unchanged (Constitution §3.5).

### §3.2 Authority matrix (Codex blocking #2) and narrowed amendment (blocking #3)

`tooling.acceptance.mode ∈ {off, advisory, auto}`. The verdict's `authoritative`
flag is **derived**, never charter-asserted:
`authoritative := (mode == auto) AND (calibration record matches the active class)
AND (autonomy.level == fully_autonomous_within_budget)`.

| mode | autonomy | calibration (active class) | verdict | engine action |
|---|---|---|---|---|
| off | any | — | — | skip; `STATE_ADVANCE` (today's disabled path, byte-identical) |
| advisory | HITL / HOTL | any | pass | `advisory_acceptance_pass_signoff` → **HALT** |
| advisory | fully_auto | any | pass | auto-degrade→HOTL (§3.6) → signoff → **HALT** |
| auto | fully_auto | uncalibrated | pass | auto-degrade→HOTL (§3.6) → signoff → **HALT** |
| auto | fully_auto | calibrated | pass | `authoritative` → `STATE_DONE` (auto-ship) |
| auto | HITL / HOTL | any | pass | signoff → **HALT** (HOTL/HITL never auto-ship) |
| any | any | any | fix_required | §3.5 human-confirm checkpoint → HALT (unchanged) |
| any | any | any | needs_human | surface_approve checkpoint → HALT (unchanged) |

**Narrowed constitutional amendment (§1.7-C / §3.4 #2 / §3.6):**

> The orchestrator MAY spawn Acceptance when `tooling.acceptance.mode ≠ off`.
> The verdict is **advisory** (cannot ship or route without human authority) unless
> it is **authoritative** per the derivation above. Authoritative **unattended
> shipping** still requires `calibrated` (matching class) under
> `fully_autonomous_within_budget`. Spawn from Research/Deliver/Dev remains
> forbidden (spawn isolation intact). Advisory spawn grants **no** new authority —
> it only lets the read-only peer-of-Research judge *advise* before a human signs.

This preserves: spawn isolation (peer-of-Research, never the builder), no
unattended uncalibrated authority, and §3.5 routing. It only splits the old single
gate ("calibrated → may spawn") into "may spawn advisory / may be authoritative".
Touch-points to update together: Constitution §1.7-C, §3.4 #2, §3.6, §10 (rewrite
anti-pattern #2/#6 to *permit* advisory-with-signoff while still forbidding
*unattended* auto-iterate on an uncalibrated verdict), `governance/context_briefing.md`,
`role-cards/acceptance-agent.md` §3/§4.

### §3.3 New checkpoint — `advisory_acceptance_pass_signoff` (Codex OQ-1/rec-1)

A pass-specific 9th default checkpoint (ADD per §1.7-D; weakens no default). Fires
only on an **advisory `pass`**. Presents the verdict + per-case evidence paths +
residual risks; human writes `confirm: ship | reject`. Non-pass advisory verdicts
reuse the **existing** `acceptance_fix_required` / `acceptance_surface_approve`
checkpoints (no umbrella duplication of routing). Authoritative pass writes no
checkpoint (auto-ship).

**Hard-kernel count update (Codex round-2 blocking #2):** the "8 MANDATORY_CHECKPOINTS"
is hard-coded in Constitution §1.7-D (`constitution.md:184`), delivery-loop §4.2.3
(`delivery-loop.md:242`), and the validator (`charter_validator.py:215`). P-A MUST
update all three so `advisory_acceptance_pass_signoff` is default **#9** (fires only
when acceptance runs advisory), with tests. This is framework default-set growth (not
an adopter add); §1.7-D's "MAY ADD, MUST NOT BYPASS" is unaffected (no default is
weakened).

### §3.4 Engine + schema + doc deltas

- **driver.py:** `_acceptance_enabled()` → `_acceptance_mode()` reading
  `tooling.acceptance.mode` (canonical; §1.4) → `off|advisory|auto`.
  `_handle_acceptance_verdict()` gains the §3.2 matrix: only `authoritative` pass →
  `STATE_DONE`; advisory pass → write checkpoint + `STATE_HALTED`. Stamp
  `authoritative` + `calibration_record_id` into the audit + verdict context.
  **Test impact:** `test_driver.py:611` (uncalibrated pass ships) flips to "advisory
  pass halts at `advisory_acceptance_pass_signoff`"; add an `auto`+`calibrated`
  test that still ships.
- **schema/template/spec:** add `tooling.acceptance.mode` (enum off/advisory/auto;
  default advisory for new templates); **relax `enabled` from required to optional**
  (it is `required` today at `mission-charter.schema.json:145`) and treat it as a
  deprecated alias normalized to `mode` per §1.4 (with the both-present conflict rule).
  `mission-charter.schema.json`, `templates/mission-charter.yaml`, `delivery-loop.md` §4.2.2.
- **constitution:** §1.7-C, §3.4 #2, §3.6, §10 per §3.2; §3.3 Acceptance row.
- **delivery-loop.md:** §4.2.3 checkpoint #9; §4.2.4 advisory branch; §4.2.8 reword.
- **acceptance-agent.md:** §3/§4 advisory spawn + sign-off expectation.

### §3.5 Backward compatibility (Codex blocking #8 / OQ-2)

**Do NOT silently flip existing charters.** Migration: (a) a charter declaring the
legacy `enabled` keeps its mapped behavior (true→auto, false→off) — byte-identical
EXCEPT the deliberate uncalibrated-pass tightening (which is a safety fix, called
out in release notes); (b) only new charter *templates/versions* default to
`mode: advisory`; (c) the validator emits a one-time deprecation note steering
`enabled` → `mode`. Reviewer: confirm this honors "no silent default change" while
still delivering default-on for new adopters.

---

## §4 Design #2 — User-perspective functional / browser-E2E acceptance gate

### §4.1 Target flow (5-role chain unchanged; capability added, not a role)

```
Dev (unit/integration + MANDATORY self-smoke of running app; attests, not authoritative)
  → Code Reviewer (read-only static; unchanged)
  → [Deliver schedules/routes] ORCHESTRATOR-OWNED browser-functional EVIDENCE RUN
        (executor exercises the running app against the SIGNED functional checklist;
         captures the §4.5 evidence manifest)
  → Acceptance (reads evidence read-only; authoritative gate; M3-advisory until calibrated)
  → human sign-off (§3.3 advisory path, or §3.5 on non-pass)
```

### §4.2 The browser executor is ORCHESTRATOR-OWNED, not an Acceptance skill (Codex blocking #4)

Reframed from rev1 (the user's phrase "Acceptance skill / browser-capable sub-agent"
is realized without violating role-skill rules):

- The **evidence run** is an **orchestrator-owned executor** step — the functional
  extension of the F5 pattern (`delivery-loop.md` §4.2.6). It runs the app + browser
  and captures artifacts. It is NOT Acceptance and is NOT mounted on Acceptance.
  (`role-skill-model.md:88,109` + `acceptance-agent.md:238` require Acceptance
  skills/sub-agents to stay read-only evidence readers — a browser executor would
  breach that.)
- **Acceptance** mounts only **browser-evidence-READING** skills
  (`[Read, Grep, Glob]`, network OFF) and judges the captured manifest. It never
  drives the browser (new F5 anti-pattern; §4.2.8).

So "browser E2E for Acceptance" = orchestrator-owned **capture** executor + an
Acceptance **read-only evidence-reading** skill. Judgment (positive shape /
anti-pattern / anchor) stays the role's.

### §4.3 Functional criteria (Research, signed) vs executor mechanics (mutable) — split (Codex blocking #5 + round-2 #5)

To not violate §3.4 #4 (Acceptance judges ONLY Customer-signed criteria), split the
"checklist" into two artifacts:

- **Functional acceptance criteria** — the **user-visible** observable outcomes, a
  functional projection of the Customer-signed `closure_contract` (§1.7-B shape).
  **Authored by Research, frozen at Gate-1 sign-off.** Acceptance judges against
  THESE. Deliver/Dev MAY NOT edit them post-sign-off; a needed change →
  `research_contract_revision` (Gate-1 re-fires). Schema:
  `functional-checklist.schema.json`.
- **Executor mechanics** — the *how* (app start cmd, base_url, navigation steps,
  selectors, fixtures). **Owned by Deliver/adopter, mutable**, part of the
  **executor contract** (§4.6), NOT acceptance criteria. The executor uses these to
  PRODUCE evidence; they never define pass/fail.

This keeps Research from being overloaded with browser mechanics and stops mutable
technical steps from masquerading as signed acceptance criteria. Mirrors §3.4 #4.

### §4.4 Calibration RECORDS keyed by full judge identity (Codex blocking #6 / OQ-4)

Replace the bare binary status with **calibration records**, one per **class**
(M1 static / M3 functional), keyed by judge identity:
`{ class ∈ {M1, M3}, role, harness/agent_kind, provider, model, skill_set_hash,
prompt_version, verdict_schema_version, evidence_contract_id, executor_contract_id }`.
(`mode` ∈ {advisory,auto} is orthogonal POLICY, not part of the calibration key — it
governs whether a calibrated record yields an *authoritative* verdict per §3.2, but
does not identify the judge. Codex round-2 #4.)
Any field change invalidates that record (extends §3.4 #6). The §3.2 gate checks
the record matching the **active class** (M1 for static acceptance; M3 for
functional/E2E). **M3 stays advisory until an M3-class browser/E2E bad-case suite
exists and the M3 record is calibrated to threshold.** Stored under
`calibration/labeled_acceptance_cases/<class>/manifest.json` + a records index;
schema `schemas/acceptance-calibration-record.schema.json` (new).

### §4.5 Evidence manifest integrity (Codex rec-2)

The executor must produce, and Acceptance must verify present (else HALT, extending
F5 "no evidence → halt"): `{ app_start_cmd, base_url, clean_state_proof,
screenshots[], console_log, network_log, storage_snapshot, final_user_visible_result,
exit_code, artifact_manifest_hash }` under `eval/runs/<id>/e2e/`. An incomplete or
non-zero-exit manifest → `gate_hard_fail` (re-run / accept-and-route / abort).

### §4.6 Deltas

- **Role cards:** `dev-agent.md` (mandatory self-smoke + handoff section + checklist
  item); `deliver-agent.md` (schedule/route the functional run + collect evidence;
  explicitly NOT the verdict, NOT the checklist author post-sign-off);
  `acceptance-agent.md` (M3 functional judging from manifest; advisory-until-M3;
  class-aware calibration; read-only evidence skills only);
  `code-reviewer-agent.md` (stays static; E2E run is not its job).
- **delivery-loop.md:** §4.2.4 add `e2e_evidence_pending` stage before
  `acceptance_pending` (or "functional F5"); §4.2.6 capture contract + manifest;
  §4.2.8 anti-pattern "Acceptance drives the browser itself".
- **Charter:** `tooling.acceptance.functional` `{ mode: static|browser_e2e,
  executor_contract: <id>, checklist_path, capture: [...], judge_calibration_m3 }`;
  `tooling.e2e.{cmd,timeout_seconds,base_url}`.
- **Schemas:** extend `acceptance-verdict.schema.json` (per-case functional evidence
  refs + `acceptance_class` + `authoritative` + `calibration_record_id`); extend
  `case-spec.schema.json` (E2E tier); new
  `acceptance-calibration-record.schema.json`; new `functional-checklist.schema.json`
  (Research-owned signed CRITERIA, §4.3); new `executor-contract.schema.json`
  (Deliver/adopter-owned executor MECHANICS, §4.3 — kept separate from criteria).
- **Skill/executor contracts (OQ-6):** ship a **skill contract** (Acceptance
  evidence-reading) + an **executor adapter interface** (the browser-capable
  capture runner). Adopters wire the actual browser runtime (e.g., Playwright); the
  framework MAY provide an OPTIONAL reference executor. Framework ships specs +
  interfaces, not a bundled browser.
- **Constitution:** §3.3 Acceptance row; §3.6 calibration-class corollary; §10 new
  F5 anti-pattern.

### §4.7 Backward compatibility

Additive/opt-in. `tooling.acceptance.functional.mode` absent → `static` (today's
behavior, byte-identical). Browser-E2E engages only when an adopter declares it +
wires an executor.

---

## §5 Design #3 — Outer Campaign loop (sequential)

### §5.1 Target

A **Campaign tier** above milestones (still Delivery Loop / Concept 2):

1. **Decompose (以终为始).** Research first defines the **top-level campaign
   contract** (the goal's closure_contract); Deliver then authors the **ordered
   milestone backlog**; Customer signs the **campaign plan**
   (`campaign_plan_signoff`, 10th default checkpoint). Per-milestone Research +
   Gate-1 still run before that milestone's detailed execution (OQ-5). The backlog
   is mutable mid-campaign with governance (a scope-expanding insert re-surfaces for
   sign-off).
2. **Auto-advance.** A **campaign runner** iterates milestones in order → per
   milestone reuse `full_chain_guided` (§4.2.4-G) to decompose into sub-sprints →
   per sub-sprint call existing `Driver.run()` → clean `STATE_ADVANCE` → dispatch
   next sub-sprint → milestone terminal close → run Acceptance (§3) → authoritative
   pass (or signed-off advisory pass) → advance to next milestone.
3. **Halt only at human-authority gates.** The runner pauses ONLY on `STATE_HALTED`
   (any MANDATORY_CHECKPOINT, Gate-1, scope deviation, close C/D, gate_hard_fail,
   acceptance fix/needs_human, advisory sign-off). On clean terminal states it keeps
   going. Campaign done when the backlog is exhausted.

### §5.2 Outer layer, not a driver inner-loop (chosen architecture)

`Driver.run()` stays deterministic + single-sub-sprint (auditable hash chain,
resumable, byte-identical). The campaign runner is a *higher* deterministic outer
loop over the existing one (mirrors `delivery-loop.md` §4.1's outer/inner split).
Risk is contained to new code; the driver is untouched.

### §5.3 Reuses existing decompose

`full_chain_guided` already does milestone→sub-sprint + Gate-1 + scope-expansion
guard. Campaign adds the tier above (goal→milestone backlog) + the iteration loop.
No duplication.

### §5.4 Deltas

- **New module** `engine-kit/orchestrator/campaign.py` (the campaign state machine,
  §5.4a).
- **New schemas:** `campaign-plan.schema.json` (ordered milestones; each
  `{id, objective, acceptance_bar, subsprint_sequence?, depends_on?: [id],
  module_locks?: [path]}` + a campaign-level **countable** `budget:
  {max_subsprints?, max_total_spawns?, max_wall_clock_minutes?}` cap (all OPTIONAL;
  absent ⇒ unbounded; `$` cost is NOT a campaign dimension — §5.4a) + `merge_policy`
  + `isolation_strategy`); `campaign-state.schema.json` (cursor + per-unit status +
  `pause_reason` + per-unit `loop_id` audit refs + cumulative
  `spent: {subsprints_run, total_spawns, wall_clock_minutes}`).
- **Charter:** a `campaign` block (or campaign-plan path) holding the ordered
  backlog; `mission.goal` stays the north star.
- **Decompose step:** campaign-decompose (goal→backlog) Deliver spawn with a
  `campaign-plan` verdict schema, gated by `campaign_plan_signoff`. **Implementation
  refinement (P-B):** this is a **campaign-TIER** gate, ENFORCED BY THE CAMPAIGN RUNNER
  (the runner pauses at `campaign_plan_signoff` until `campaign-plan.signed_by_human`
  is true) and classified in `campaign.py` + tested — it is NOT folded into the charter
  validator's `MANDATORY_CHECKPOINTS` (that validates delivery-loop CHARTERS, not
  campaign plans; a campaign-tier checkpoint there would be a category error). So the
  charter-validator hard-kernel count stays **9** (P-A's set); the campaign tier adds
  its own gate. The conceptual "#10" still holds — it's just enforced where it belongs.
- **Process docs:** `process/milestone-framework.md` (campaign tier; "optional next
  milestone" → "auto-dispatched next backlog item"); new `process/campaign-loop.md`
  (outer loop spec; halt-only-at-human-gates; resume); `modules/m-autoloop.md`
  cross-ref to avoid §1.7-E conflation.
- **Role card:** `deliver-agent.md` campaign-level responsibility (author backlog;
  per-milestone decompose; after close+accept, runner auto-advances — Deliver is
  re-invoked to author the next milestone's sub-sprints, not to ask "what next").

### §5.4a Campaign state-machine semantics (Codex blocking #7)

`campaign-state.json` (persisted; resumable like driver §4.5):
- **Backlog + cursor:** ordered milestones (+ `depends_on`, `module_locks`);
  `current_milestone_id`, `current_subsprint_id`.
- **Per-unit status:** `pending|in_progress|done|halted|failed` + last driver
  terminal state + the sub-sprint's `loop_id` (audit linkage).
- **Pause detection (Codex P-B round blocking #2):** the campaign reads each unit's
  `run_loop` summary `final_state` and ADVANCES only on `advance` (sub-sprint clean) or
  `done` (milestone accepted authoritative). **Everything else → PAUSE** — not only
  `STATE_HALTED` but also the guided pending states (`gate1_pending`, `research_pending`,
  `decompose_pending`), which are NOT `STATE_HALTED`. Never skip ahead on a non-advance state.
- **Retry/idempotency:** a unit is keyed `(milestone_id, subsprint_id)`; re-dispatch
  uses the driver's existing idempotency cache (§4.5); the campaign records each
  unit's `loop_id` so re-runs are traceable, not duplicated.
- **Budget aggregation (Codex round-2 blocking #3 + round-3 prereq (a); resolved rev4):**
  real per-call **`$` cost is unavailable** — no adapter reports it (verified) and
  subscription-billed harnesses (Codex / Claude Code / Kimi) do not expose per-call
  cost (the charter's `budget.max_api_usd` already carries this caveat). So the campaign
  cap uses **countable proxies the engine already tracks + surfaces** in each
  sub-sprint's `run_loop` summary — **NO new adapter cost wiring**:
  - `subsprints_run` — campaign counts dispatched sub-sprints.
  - `total_spawns` — campaign SUMS `summary["spawn_count"]` (already returned by
    `run_loop`, `run_loop.py:367`; `RunState.spawn_count`, `driver.py:380`) across units.
  - `wall_clock_minutes` — campaign measures elapsed via the injected `clock`.
  `campaign.budget = {max_subsprints?, max_total_spawns?, max_wall_clock_minutes?}`
  (all OPTIONAL; absent ⇒ unbounded for that dimension). **Precedence:** a per-run
  `BudgetExceeded` (fix-round cap `driver.py:749`; best-effort `max_api_usd` controller
  halt for a metered adapter `driver.py:2139`) HALTs that unit → `GateHardFail` →
  campaign marks the unit `failed` + HALTs. The campaign cap is checked **between
  units** (before dispatching the next); exceeding → a `campaign_budget_exhausted`
  pause (human raises the cap or aborts). The two never silently override each other.
  **`$` cost capture is explicitly OUT OF SCOPE** until a metered adapter exposes
  per-call cost.
- **Pause/resume — EXHAUSTIVE map over the driver's emitted halts, TWO resume mechanisms
  (Codex P-B round blocking #1 + option/coverage fixes):** on a pause the campaign persists
  cursor + `pause_reason` (the emitted `checkpoint_id`) + checkpoint path, and surfaces.
  `campaign resume` requires the checkpoint `decision:` ≠ `pending` (else re-halt — no
  silent progress). Resume uses ONE of two mechanisms, because `Driver.run(resume=True)`
  only re-enters states that set `halt_resume_state` (the 3 spec-refinement halts) OR the
  guided pending states; an ordinary human-gate `STATE_HALTED` short-circuits on resume
  (`driver.py:2100`).

  **Mechanism A — driver-resume** (`Driver.run(resume=True)` re-enters + re-resolves):
  - **`dev_spec_refinement` / `review_spec_refinement` / `acceptance_spec_refinement`**
    (set `halt_resume_state`) — human refined the source; re-enter the paused state.
  - **`customer_gate1_signoff`** (stays `gate1_pending`, a guided pre-state) — resume
    re-consults the injected `gate_resolver`: `sign` → continue this milestone's
    decompose → sub-sprints; `reject` → milestone halts; `abort` → campaign ends.

  **Mechanism B — campaign interprets the resolved `decision:` and dispatches** (the halted
  unit is NOT re-run via resume=True — it no-ops; each new dispatch gets a fresh `loop_id`
  under the campaign ledger). Options below are the ACTUAL checkpoint options the driver writes:
  - **`post_gate1_scope_expansion`** (`driver.py:1936`) → `widen_approved_scope` →
    re-decompose under the widened envelope; `narrow_plan` → re-decompose; `abort` → ends.
  - **`scope_deviation`** → `accept_deviation` (human widened `approved_scope`) → re-dispatch
    the unit as a fresh run; `reject_deviation` → dispatch a re-planned fix; `abandon` → ends.
  - **`close_taxonomy_C_or_D`** → `resolve` → dispatch the resolving unit; `abort` → ends.
  - **`review_out_of_scope`** → `open_followup_subsprint` → dispatch the follow-up;
    `accept_and_advance` → advance; `abort` → campaign ends.
  - **`gate_hard_fail`** (options CONTEXT-dependent): deterministic-gate path = `re_run`
    (re-dispatch fresh) / `accept_failure_and_route` (dispatch routed) / `abort`
    (`driver.py:751`); review-fix HITL reuse = `deliver_fix_iteration` (dispatch a fix
    sub-sprint) / `abort` (`driver.py:2354`).
  - **`loop_controller_halt`** (budget / max_rounds / converged_dry; `driver.py:2321`;
    options `review_outcome/re_run/abort`) → `re_run` → re-dispatch fresh; `review_outcome`
    → human accepts / raises the cap → resume from cursor; `abort` → end. (A max_rounds/
    budget halt ALSO raises the deterministic `BudgetExceeded`.)
  - **`loop_controller_escalate`** (severity over ceiling; `driver.py:2337`; options
    `review_and_route/accept_failure_and_route/abort`) → `review_and_route` /
    `accept_failure_and_route` → dispatch the routed fix unit; `abort` → end.
  - **`acceptance_fix_required`** → `confirm: yes` + `route` ∈ `{deliver_fix_iteration,
    re_acceptance_after_evidence, research_contract_revision}` (`driver.py:3060`) → dispatch
    the routed unit; `confirm: no` → advisory ship → advance to next milestone.
  - **`acceptance_surface_approve`** (needs_human) → `approve_ship` → advance milestone;
    `route_to_deliver_fix` → dispatch fix unit; `abort` → campaign ends.
  - **`advisory_acceptance_pass_signoff`** (P-A) → `confirm: ship` → mark milestone accepted
    → advance to next milestone; `reject` → dispatch deliver-fix / end.

  **Campaign-level (also Mechanism B):**
  - **`campaign_plan_signoff`** (#10) → `approve` → start milestone 1; `reject` → ends.
  - **`campaign_budget_exhausted`** → cap raised → resume from cursor; `abort` → ends.

  **Fail-closed catch-all:** any emitted `checkpoint_id` NOT mapped above → unknown human
  gate; require a resolved decision, surface, DO NOT advance. A test asserts every
  `_write_checkpoint`/`_halt_checkpoint` id in `driver.py` is either mapped here or hits
  this catch-all (a future new checkpoint cannot silently break the campaign).

  **Non-pause checkpoints (excluded — never leave the loop paused):**
  `acceptance_calibration_degraded` (auto-resolved, `resolver: orchestrator`,
  `driver.py:2586`), `memory_feedback` (post-success), `loop_isolation_recommendation`
  (ingress; proceeds on the default strategy).
- **GateHardFail:** a driver `GateHardFail` (incl. `BudgetExceeded`) propagates →
  campaign marks the unit `failed`, HALTs the campaign (does NOT advance).
- **Audit linkage:** the campaign emits its own hash-chained ledger
  (`campaign_id`) referencing each sub-sprint `loop_id` — auditable end-to-end.

### §5.5 Parallelism seam (deferred; Codex OQ-7 — capture fields NOW)

`campaign-plan` milestones carry, even in the sequential runner:
`depends_on: [milestone-id]` (deterministic topological order), `module_locks:
[path]` (resource isolation), and the plan declares a `merge_policy` +
`isolation_strategy` (worktree vs shared). The sequential runner enforces
topological order + lock non-overlap (so a future parallel runner is sound) but
runs strictly one-at-a-time. Parallel execution is NOT implemented now. Reviewer:
confirm these fields are sufficient to not bake in a sequential-only assumption.

### §5.6 Backward compatibility

Fully additive; new entry point; driver unchanged. Old per-invocation usage is
unaffected.

---

## §6 How the three compose

```
Customer goal
  │  Research: campaign contract → Deliver: milestone backlog → campaign_plan_signoff (human)
  ▼
Campaign runner (NEW §5) — iterates milestones, halts only at human gates
  ├─ per milestone: full_chain_guided decompose (EXISTS) → Gate-1 (human)
  │     ├─ per sub-sprint: Driver.run() (EXISTS, unchanged)
  │     │     Dev(self-smoke #2) → gate(tests) → Reviewer(static) → Deliver close
  │     │     └─ clean advance → campaign auto-dispatches next sub-sprint (NEW loop)
  │     └─ milestone terminal close:
  │           orchestrator-owned e2e evidence run (NEW #2) → Acceptance (DEFAULT-ON #1;
  │           M3 advisory until calibrated #2/#4) → authoritative pass → auto-advance;
  │           advisory pass → advisory_acceptance_pass_signoff (human #1/#3) → advance
  ▼
backlog exhausted → campaign done
```

Human stops are exactly: campaign-plan approval, per-milestone Gate-1, scope
deviations, acceptance sign-off, hard fails — not "ask what's next after every
milestone."

---

## §7 Backward-compat summary

| Change | Default-path impact | Migration |
|---|---|---|
| #1 default-on advisory | Existing charters NOT flipped (legacy `enabled` mapped). New templates default `mode: advisory`. Uncalibrated pass now HALTs (safety tightening; changes test_driver.py:611). | Release note; `enabled`→`mode` deprecation. |
| #1 namespace | Driver reads canonical `tooling.acceptance.*` **only**; a pre-validation normalization pass (§1.4) maps legacy top-level `acceptance` / `enabled` BEFORE schema validation (no driver-side fallback). | Validator normalizes + warns; template updated. |
| #2 functional/E2E | Additive; `functional.mode` absent → static (byte-identical). | None unless adopting. |
| #3 campaign loop | Additive; new entry point; driver unchanged. | None; opt-in. |

---

## §8 Open questions — RESOLVED per Codex round-1

- **OQ-1** → pass-specific `advisory_acceptance_pass_signoff`; reuse existing
  fix/needs_human checkpoints for non-pass. (Folded into §3.3.)
- **OQ-2** → default-on is opt-in for existing charters; advisory default only for
  new charter versions/templates. (§3.5.)
- **OQ-3** → the amendment is sound ONLY because advisory spawn cannot ship or route
  without human authority (enforced by §3.2 matrix). (§3.2.)
- **OQ-4** → separate calibration **records** per **class** (M1/M3), keyed by full
  judge identity; `mode` is orthogonal policy, not in the key. (§4.4.)
- **OQ-5** → Research defines the top-level campaign contract first; Deliver authors
  the backlog; Customer signs the campaign plan; per-milestone Research/Gate-1 still
  runs. (§5.1.)
- **OQ-6** → ship a skill contract + executor adapter interface; adopters wire the
  browser; framework MAY provide an optional reference executor. (§4.6.)
- **OQ-7** → `depends_on` + `module_locks` + `merge_policy` + `isolation_strategy` +
  deterministic topological order captured now; parallel execution deferred. (§5.5.)

## §9 Implementation plan (AFTER approval — not started)

Each phase: docs + schema first, then engine code, then tests, then Codex review.

- **P-A (#1 + §1.4)** — normalize-before-validate charter migration (§1.4) +
  `tooling.acceptance.mode` (relax `enabled` to optional); authority matrix in
  `_handle_acceptance_verdict`; `advisory_acceptance_pass_signoff` as default
  checkpoint **#9** — updating the hard-coded "8" in constitution §1.7-D,
  delivery-loop §4.2.3, and `charter_validator.py:215` (with tests);
  constitution/delivery-loop/role-card/schema deltas; update `test_driver.py:611`.
  Smallest; unblocks the rest.
- **P-B (#3)** — campaign runner + campaign-plan/state schemas (incl. budget §5.4 +
  parallel seam) + campaign-decompose + `campaign_plan_signoff` as default checkpoint
  **#10** (same three hard-kernel sites + tests) + state-machine semantics incl.
  budget precedence + resolved-checkpoint transitions (§5.4a); process docs; deliver
  role card. Depends on P-A (acceptance at close).
- **P-C (#2)** — Dev self-smoke; orchestrator-owned evidence executor + Acceptance
  evidence-reading skill + executor adapter interface; signed/frozen functional
  checklist; M1/M3 calibration records; manifest integrity; role cards + schema
  extensions. Largest; depends on P-A (advisory path) + P-B (close hook).
- **Cross-phase sweep (Codex round-3):** the "8 defaults" string also lives in
  `mission-charter.schema.json:230`, `process/customer-checkpoints.md:129`,
  `process/self-governance.md:57`, `templates/mission-charter.yaml:9` — include these
  in the P-A (#9) / P-B (#10) checkpoint-count sweep. (P-A landed these; P-B adds #10.)
  **P-B prereqs RESOLVED in design (rev4):** (a) campaign spend uses countable proxies
  the engine already surfaces (`run_loop` `spawn_count` + clock) — `$` cost is out of
  scope, NO adapter wiring; (b) the `pause_reason`→resume map is now exhaustive over the
  12 checkpoint_ids the driver actually emits + a fail-closed catch-all (both §5.4a).
  Pending Codex sign-off on rev4 before P-B implementation starts.

## §10 Residual risks (Codex round-1)

- **Sign-off fatigue** — advisory acceptance may over-prompt; mitigate by batching
  per-milestone sign-off + concise verdict surfacing.
- **Browser-evidence flakiness/env-dependence** — mitigate via the §4.5 manifest +
  clean-state proof + deterministic checklist; flaky run → `gate_hard_fail` re-run.
- **Calibration drift** — executor/prompt/schema/skill version changes invalidate
  the M3 record (§4.4); the records' identity keys make drift detectable.
- **Campaign compounding a bad early plan** — mitigate via `campaign_plan_signoff`
  up front, per-milestone Gate-1, strict pause/resume + campaign budget cap (§5.4a).

---

End of design spec (rev3).
