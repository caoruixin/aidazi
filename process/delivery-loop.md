---
title: Delivery Loop (Δ-18)
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
size_target: 50KB
split_trigger: if T1 Type B sop_definition section grows past 8KB, split to delivery-loop-typeB-extension.md
notes: >
  Δ-18 Delivery Loop spec (Concept 2 of the two loops; see Constitution §3.7).
  Defines the multi-agent team collaboration pattern + the orchestrator
  implementation that automates it (state machine, spawn functions, scope
  envelope, F5 evidence, calibration gate, MANDATORY_CHECKPOINTS).
  Renamed from "orchestrator-pattern" per v4. The pattern's name is
  "Delivery Loop"; the software that implements it is conventionally called
  "the orchestrator". Type B variant (T1') is placeholder pending hermes
  first SOP milestone close (OQ-V4-001).
---

# Δ-18 Delivery Loop

The Delivery Loop is **Concept 2** of v4's two-loop distinction (Constitution §3.7; `docs/two-loops-explainer.md`).

It is the framework-level pattern for **how the 5-role multi-agent team (Research / Deliver / Dev / Code Reviewer / Acceptance + Customer) collaboratively delivers work AND autonomously discovers and corrects the gap between delivered behavior and Customer's stated need**.

The Delivery Loop is universal across tracks (Type A / B / C / A+B hybrid). Its automation layer (the orchestrator implementation) is optional per `charter.autonomy.level`.

**Naming**: in framework documentation, the pattern's name is **Delivery Loop**. In code or technical implementation context, the software that implements it is conventionally called **the orchestrator** (binary, state machine, spawn function set). Same physical thing, two layers of vocabulary. This file's name is `delivery-loop.md`; the binary that drives it is conventionally named `orchestrator`. Do not introduce a third name for the same concept.

## §1 Scope

This file covers:
- §2 — when the Delivery Loop pattern applies (conditional vs universal).
- §3 — the canonical 5-role chain reference (delegated to Constitution §3).
- §4 — the orchestrator implementation: charter schema, MANDATORY_CHECKPOINTS, state machine, scope envelope, F5 evidence, spawn function set, calibration, anti-patterns.
- §5 — adopter bootstrap pointers.
- §6 — open questions carry.

What this file does NOT cover:
- The cross-Δ relationship to Auto Loop (Constitution §3.7 and `docs/two-loops-explainer.md`).
- The role-card prompts themselves (those live in `role-cards/`).
- The Application Guide / per-track adoption shape (those live in `docs/`).

## §2 Conditional vs universal

The Delivery Loop **pattern** (5-role chain + Acceptance fix_required → human-confirm → Deliver flow + research-brief closure_contract + boundary invariants) is **UNIVERSAL** — every adopter inherits it via Constitution §3.

The Delivery Loop **orchestrator** (state machine + spawn functions + checkpoint inbox + scope envelope + F5 evidence + calibration gate) is **CONDITIONAL** — applies when `charter.autonomy.level ≠ human_in_the_loop`.

Pure human-in-the-loop adopters (manual handoff via paste) do NOT need the orchestrator. They still use:
- The 5-role chain (Constitution §3.1–§3.4).
- The Acceptance fix_required → human-confirm → Deliver flow (Constitution §3.5).
- The closure_contract source-of-truth invariant (Constitution §3.4 invariant #4).

What the orchestrator ADDS when adopted:
- A file-based checkpoint inbox (human-on-the-loop). Orchestrator writes `docs/checkpoints/<event>.md`; human writes the `decision:` field; orchestrator picks up.
- Auto-dispatch of sub-sprints within charter-approved scope (no human paste per sprint dispatch).
- §3.6 calibration-gated Acceptance judging (orchestrator enforces degradation; human cannot bypass).
- F5 evidence pattern (orchestrator runs eval harness; dev sandbox stays sealed).
- Scope-envelope enforcement before close (deterministic, no LLM).
- Charter pre-authorization (autonomy level + budget caps + allowed scope + tooling assignments declared in advance).

## §3 5-role chain reference

The role chain, role table, and boundary invariants are defined in Constitution §3. Do NOT duplicate them here.

This file references the chain at these points:
- Spawn function set (§4.2.7) — each function spawns one of the 5 roles per `charter.tooling.<role>.agent_kind`.
- Acceptance flow (§4.2.4 + §4.2.7) — orchestrator wires the Acceptance fix_required → checkpoint → human-confirm route per Constitution §3.5.
- Boundary invariants (§4.2.8) — anti-patterns enforce Constitution §3.4 invariants.

The Acceptance Agent in particular requires two cross-references to Constitution before reading further:
- §1.7-C — Acceptance spawn isolation (orchestrator IS one of the two permitted spawn surfaces, gated by calibration).
- §3.6 — Acceptance judge calibration (orchestrator enforces degradation).

## §4 Orchestrator implementation

### §4.1 Overview

The orchestrator is a **deterministic outer loop** that drives **non-deterministic inner work** done by LLM-backed spawn functions.

```
charter.yaml ─┐
              │   ┌──────────────────────────────────────────────┐
              ├─→ │  Outer loop (deterministic state machine)    │
              │   │                                              │
              │   │  • read state                                │
              │   │  • check MANDATORY_CHECKPOINTS / gates       │
              │   │  • if checkpoint pending → wait for human    │
              │   │  • else → call spawn function for next state │
              │   │  • parse spawn function verdict (JSON)       │
              │   │  • write state + advance / fix / checkpoint  │
              │   │  • emit progress to docs/checkpoints/        │
              │   └────────────────┬─────────────────────────────┘
              │                    │
              │   ┌────────────────┴─────────────────┐
              └─→ │  Inner work (LLM, per spawn fn) │
                  │                                  │
                  │  • spawn_dev → workspace-write   │
                  │  • spawn_deliver_close → JSON    │
                  │  • spawn_deliver_plan_fix → JSON │
                  │  • spawn_research → brief        │
                  │  • run_review → JSON             │
                  │  • run_acceptance → JSON         │
                  └──────────────────────────────────┘
```

Determinism lives in the outer loop. Semantic judgment lives in the spawn functions. The two communicate via JSON verdicts (schemas in §4.2.7), filesystem state, and checkpoint files.

### §4.2 Implementation spec

#### §4.2.1 Trigger

The orchestrator starts when:
- Customer kicks off a milestone (`orchestrator dispatch <milestone-id>`).
- Customer resumes a paused checkpoint (`orchestrator resume`).
- A scheduled trigger fires (rare; e.g., overnight Auto Loop integration).

It does NOT start spontaneously.

#### §4.2.2 Charter schema (T0 base + T1 profile overlays)

The charter is the YAML pre-authorization bounding what the orchestrator can do without human intervention. Loaded at boot; immutable copy stored alongside run state.

**T0 base** (any track):

```yaml
mission:
  id: <sprint-or-milestone-id>
  goal: <one-line user-facing goal — what Customer reads at gate 2>

autonomy:
  level: human_in_the_loop | human_on_the_loop | fully_autonomous_within_budget
  approved_scope:
    subsprint_sequence: [<id>, ...]
    layers_allowed: [<framework-layer-name>, ...]
    modules_in_scope: [<repo-path>, ...]
    explicitly_out_of_scope: [<repo-path>, ...]
  auto_pass_rules:
    clean_pass_auto_advance: true | false
    auto_fix_iteration:
      enabled: true | false
      max_rounds: <int>
      only_if_findings_severity_at_most: P0 | P1 | P2
    adaptive_insert:
      enabled: true | false
      max_inserted_subsprints: <int>

budget:
  max_api_usd: <number>
  max_fix_rounds_total: <int>
  max_wall_clock_minutes: <int>

tooling:
  # Every role section also accepts OPTIONAL role-skill fields (process/role-skill-model.md §7):
  #   skills: [<skill-name-or-path>, ...]   # MUST comply with the role's tool whitelist
  #   subagent_fanout: true | false          # false forbids intra-role fan-out for that role
  research:
    agent_kind: claude_code | codex | <other>
    model: <model-id>
  deliver:
    agent_kind: claude_code | codex | <other>
    model: <model-id>
  dev:
    agent_kind: claude_code | codex | <other>
    model: <model-id>
    sandbox: workspace_write | read_only
  review:
    agent_kind: claude_code | codex | <other>
    model: <model-id>
    tools: [Read, Grep, Glob]
  eval:
    cmd: <shell-command>
    timeout_seconds: <int>
  acceptance:
    mode: off | advisory | auto      # canonical; absent → off. advisory runs but HALTs a pass for sign-off; auto+calibrated+fully_auto auto-ships
    enabled: true | false            # DEPRECATED alias for mode (true→auto, false→off); normalized before validation; if both present they MUST agree
    agent_kind: claude_code | codex | <other>
    model: <model-id>
    tools: [Read, Grep, Glob]
    judge_calibration:
      status: uncalibrated | calibrated
      agreement_threshold: 0.9
      flip_threshold: 0.1
      labeled_set_path: <path>
    run_at: milestone_close | release_cut | both
    on_fix_required:
      human_confirm_required: true   # Constitution §1.7-C; charter validator rejects false
      route_options: [deliver_fix_iteration, re_acceptance_after_evidence, research_contract_revision]
```

**T1 profile overlays** (declare ONE or both for hybrid):

```yaml
# Type A AI Agent
profile_type_a:
  layer_set: [infra, java_guard, prompt_projection, skill_state, semantic_planner,
              eval_spec, product_policy, judge_calibration, human_review_required]
  closure_contract_source: research_brief
  bad_case_lifecycle: badcase-lifecycle.md
  phase_pipeline_required: true

# Type B Agentic Workflow (PLACEHOLDER — OQ-V4-001)
profile_type_b:
  layer_set: [infra, runtime_guard, workflow_definition, prompt_projection, skill_state,
              eval_spec, product_policy]
  sop_definition:
    source: <path-to-SOP-Excel-or-yaml>
    verification_gates_per_step: true

# Type C Demo App
profile_type_c:
  layer_set: [infra, demo_correctness]
  local_acceptance_checklist:
    source: <path-to-LOCAL_ACCEPTANCE_CHECKLIST.md>
  off_the_shelf_skill_inventory_required: true
```

JSON schema: `schemas/mission-charter.schema.json`. Template: `templates/mission-charter.yaml`.

**Charter editing rules**:

- `mission.id` and `mission.goal` frozen at boot.
- `autonomy.approved_scope.subsprint_sequence` may be revised mid-run only through a `scope_deviation` MANDATORY_CHECKPOINT resolution.
- `autonomy.auto_pass_rules.adaptive_insert.max_inserted_subsprints` bounds adaptive insertion; orchestrator MUST refuse to insert past this limit.
- `tooling.acceptance.mode ∈ {off, advisory, auto}` is canonical; `tooling.acceptance.enabled` is a DEPRECATED alias normalized to `mode` (true→auto, false→off) before validation. If BOTH are present they MUST agree (`enabled:true ↔ mode∈{advisory,auto}`, `enabled:false ↔ mode:off`); a disagreement is a hard validation error (the validator never silently picks one).
- `tooling.acceptance.judge_calibration.status` may flip to `calibrated` only after a calibration run; flipping by hand is a framework breach.
- The `route_options` list under `tooling.acceptance.on_fix_required` MAY be narrowed by adopter but MAY NOT be empty.
- `tooling.acceptance.on_fix_required.human_confirm_required` MUST be `true` — Constitution §1.7-C; charter validator rejects `false`.
- `tooling.acceptance.skills` changes invalidate `judge_calibration.status` (Constitution §3.4 invariant #6 calibration corollary); the validator SHOULD warn when `skills` changed while `status: calibrated` persists.
- **MANDATORY_CHECKPOINTS non-bypass invariant** (Constitution §1.7-D) — the 9 default checkpoints in §4.2.3 may NOT be bypassed in any of these four shapes; charter validator MUST reject each:
  - **Omitted** — charter does not mention the checkpoint (absence ≠ opt-out).
  - **Emptied** — charter declares the checkpoint key with empty / null value (e.g., `mandatory_checkpoints: []`).
  - **Disabled** — charter sets the checkpoint to falsy / inert value (e.g., `bad_case_manual_review.enabled: false`).
  - **Overridden** — charter replaces the checkpoint's semantics with a weaker variant (e.g., redefines `scope_deviation` to auto-approve below a severity threshold; replaces `human_confirm_required: true` with `auto_confirm_if_clean: true`). Semantic override = bypass.
  - Legitimate adopter customization: ADD a custom checkpoint with an adopter-chosen id; the default still fires alongside.

#### §4.2.3 MANDATORY_CHECKPOINTS (9 — charter MAY ADD, MUST NOT BYPASS)

Points where human authority is non-negotiable. Constitution §1.7-D enforces the non-bypass invariant: charter MAY NOT omit, empty, disable, or override any of the 9 defaults below (see §4.2.2 charter editing rules for the four-shape rejection). Charter validator rejects bypass in any shape; orchestrator refuses to boot.

1. **`mission_start`** — orchestrator boots; human verifies `mission.goal` + `autonomy.level` + `tooling.*.agent_kind`. Once approved, only `mission_end` can revisit.
2. **`research_proposal_selection`** — if Path 1 (research-driven), human selects from candidate proposals before Deliver consumes. Bypassed only if charter explicitly names a single research-brief id and Customer has signed it prior to dispatch.
3. **`bad_case_manual_review`** — primary §5.6 gate (per `process/badcase-lifecycle.md`); human reads per-turn bad-case traces before milestone close. Cannot be skipped at milestone close.
4. **`new_tier0_candidate`** — any time a Code Reviewer or Deliver proposes a new Tier-0 invariant, human approves before adoption.
5. **`forbidden_list_redline`** — any time a change touches Constitution §1.7 forbidden list semantics, human reviews.
6. **`scope_deviation`** — orchestrator's deterministic `scope_envelope_check` (§4.2.5) fires; human resolves before resume.
7. **`close_taxonomy_C_or_D`** — when Deliver close verdict = C (scope-broadening) or D (non-convergent), human resolves. Maps to `templates/deliver-close-taxonomy.md` subclasses.
8. **`gate_hard_fail`** — any deterministic gate (tests / handoff structure / trace existence / safety / grounding floor) fails AND `auto_fix_iteration` not eligible.
9. **`advisory_acceptance_pass_signoff`** — Acceptance produced an ADVISORY pass (not authoritative); human signs off (`confirm: ship|reject`) before the milestone ships (design §3.2/§3.3). Fires only when Acceptance runs advisory; an authoritative pass writes no checkpoint (auto-ships).

**Checkpoint file shape** (orchestrator writes; human resolves):

```
docs/checkpoints/<YYYYMMDD-HHMMSS>__<checkpoint_id>__<scope>.md

---
checkpoint_id: <one of 9 above + adopter-added>
scope: <sprint-id or milestone-id>
emitted_at: <ISO timestamp>
decision: pending | approved | rejected | <event-specific values>
resolved_at: <ISO timestamp or null>
resolver: <human name; or "orchestrator" if auto-degraded per §3.6>
---

# Context
<orchestrator describes what triggered the checkpoint>

# Options
<orchestrator lists the route options the human chooses among>

# Decision (human fills)
<human writes; orchestrator picks up>
```

For Acceptance `fix_required` specifically: follows Constitution §3.5 shape; `decision: pending`; options are `deliver_fix_iteration | re_acceptance_after_evidence | research_contract_revision`; human writes `confirm: yes|no` + `route: <option>` + optional notes.

#### §4.2.4 State machine (Type A driver)

```
                            ┌─────┐
                            │idle │
                            └──┬──┘
                               │ (charter loaded; current_subsprint set)
                               ↓
                       ┌──────────────┐
                       │ dev_pending  │ (preflight: contract present + non-empty;
                       └──────┬───────┘  context_budget self_contained: true)
                              ↓ spawn_dev → handoff §1-§11 written
                       ┌──────────────┐
                       │ gate_pending │ run gates:
                       └──────┬───────┘   • run_tests
                              │           • validate_stanza
                              │           • check_handoff (§0/§1/§2)
                              │           • check_trace (Δ-12 trace artifact)
                              │           • run charter.tooling.eval.cmd
                              │             as a sub-sprint gate if present
                              ↓ gates pass
                       ┌──────────────────┐
                       │ review_pending   │ spawn run_review
                       └──────┬───────────┘
                              ↓ verdict (pass | fix_required | out_of_scope_review)
                       ┌──────────────────┐
                       │  close_pending   │ spawn spawn_deliver_close
                       └──────┬───────────┘
                              ↓ verdict A/B/C/D + scope_envelope_check (deterministic)
                ┌─────────────┴─────────────┐
                ↓                            ↓
        ┌───────────────┐         ┌───────────────────┐
        │   advance     │         │       fix         │
        │ (next sub-    │         │ spawn deliver_    │
        │ sprint OR     │         │ plan_fix → bump   │
        │ milestone_    │         │ fix_round →       │
        │ close)        │         │ back to dev_      │
        └───────┬───────┘         │ pending           │
                ↓                  └───────────────────┘
        ┌───────────────┐
        │ milestone_    │
        │ close         │ ← MANDATORY_CHECKPOINT bad_case_manual_review here
        └───────┬───────┘
                ↓ (P-C: if tooling.acceptance.functional.mode == browser_e2e)
        ┌─────────────────────┐
        │ e2e_evidence_pending│ Dev self-smoke gate → orchestrator drives the
        │ (out-of-band; only  │ running app through the declared journeys →
        │ for browser_e2e)    │ commit hash-anchored evidence (manifest +
        └───────┬─────────────┘ checklist-results) → browser_e2e_evidence event
                ↓ (then; static milestones skip straight to acceptance_pending)
                ↓ (if tooling.acceptance.mode ≠ off)
        ┌───────────────────┐
        │ acceptance_pending│ static (M1): run F5 eval evidence; browser_e2e
        │                   │ (M3): VERIFY the committed manifest → spawn
        └───────┬───────────┘ run_acceptance (read-only over the evidence)
                ↓ acceptance verdict
       ┌────────┼─────────────────────────┐
       ↓        ↓                          ↓
     pass   fix_required               needs_human
       │        │                          │
       │        ↓ post human-confirm        ↓
       │     checkpoint (3 route options)   surface_approve
       │        │                          checkpoint
       │   ┌────┼──────────┐
       │   ↓    ↓          ↓
       │ deliver re-      research-
       │  fix  acceptance  contract-
       │  iter (more       revision
       │   ↓   evidence)
       │   ↓                                ↓
     advance to next milestone OR halt    human writes decision
```

**Acceptance `pass` splits by authority** (design §3.2/§3.3): a `pass` is **AUTHORITATIVE** (mode==auto AND judge calibrated for the active class AND autonomy==fully_autonomous_within_budget) → ship → `STATE_DONE`; otherwise it is **ADVISORY** (advisory mode, or uncalibrated, or non-fully-autonomous) → write the `advisory_acceptance_pass_signoff` checkpoint + HALT for human `confirm: ship|reject`. `mode: off` skips Acceptance (`STATE_ADVANCE`, byte-identical to the legacy disabled path). `fix_required` / `needs_human` routing is unchanged.

**`e2e_evidence_pending` (P-C browser-E2E gate)**: an OUT-OF-BAND state (like `acceptance_pending`) that runs ONLY when the active acceptance class is `browser_e2e` (charter `tooling.acceptance.functional.mode == browser_e2e`, derived per milestone) — between the milestone-close advance and `acceptance_pending`. The orchestrator (not Acceptance) drives the running app through the declared journeys, commits hash-anchored evidence under `.orchestrator/audit/browser/<loop_id>/<run_id>/`, and anchors it with a `browser_e2e_evidence` Audit Spine event, then proceeds into `acceptance_pending` with the committed manifest as read-only evidence. It is preceded by the Dev self-smoke structural gate (`docs/self-smoke.json {command,result}` present; absent → resumable `gate_hard_fail`). A non-browser_e2e milestone NEVER enters this state (byte-identical to the static path). Resume re-enters `e2e_evidence_pending` BEFORE the acceptance re-entry and is non-duplicating (reconcile keyed on the persisted `run_id` + the ledger event). Full spec: `process/browser-e2e-acceptance.md`. M3 ships advisory in v1 (no M3 calibration record) → a functional `pass` HALTs at `advisory_acceptance_pass_signoff`.

**Type B variant** (placeholder; OQ-V4-001): instead of `gate_pending`'s `run_tests`, run the SOP per-step verification gates from `charter.profile_type_b.sop_definition.verification_gates_per_step`. Full spec deferred.

**Type C variant**: skip `acceptance_pending` if charter.profile_type_c is the only profile and `tooling.acceptance.run_at: release_cut` only; Type C usually runs Acceptance every sub-sprint via LOCAL_ACCEPTANCE_CHECKLIST.

**State invariants**:
- Skipped-but-required gate = NOT passed. No silent skip; orchestrator emits `gate_hard_fail`.
- `gate_pending` is a real deterministic sub-sprint gate: Dev must have produced a handoff artifact, and when `charter.tooling.eval.cmd` is configured the orchestrator runs it before Review. A non-zero exit / timeout emits the `gate_hard_fail` MANDATORY_CHECKPOINT and Review/Close do not run.
- Charter can't widen scope mid-run; only `scope_deviation` checkpoint resolution can.
- `close_pending`'s deterministic `scope_envelope_check` runs BEFORE LLM close verdict is trusted.
- A clean re-review after an auto-fix round does NOT skip `close_pending`: Review pass is necessary but not sufficient; Deliver close still runs and is the only path that emits the clean `advance` decision.
- Acceptance runs whenever `tooling.acceptance.mode ≠ off` (advisory runs even uncalibrated, after the §3.6 auto-degrade); a `pass` only auto-ships when authoritative (mode==auto AND calibrated for the active class AND fully_autonomous_within_budget), else it HALTs at `advisory_acceptance_pass_signoff` (Constitution §3.6 / §1.7-C).
- All decisions checkpointed to `docs/checkpoints/` filesystem so human can audit.
- Fix-round counter bounded by `charter.budget.max_fix_rounds_total`; exceeded → halt.

##### §4.2.4-G `full_chain_guided` bootstrap pre-states (P6.1, ADDITIVE / OPTIONAL)

The driver supports an OPTIONAL bootstrap mode selected by `loop_mode` (Driver ctor param, or `charter.autonomy.loop_mode`; the ctor param wins). Values:

- `delivery_only` (**DEFAULT**) — the state machine above, unchanged (byte-identical). None of the pre-states below run.
- `full_chain_guided` — adds three OUT-OF-BAND pre-states that run BEFORE `dev_pending`, decomposing a milestone into the sub-sprint sequence the delivery loop then executes:

```
   research_pending → gate1_pending → decompose_pending → (dev_pending …)
```

1. **`research_pending`** — `_step_research` drafts the milestone brief (an ARTIFACT — a doc, not a verdict; spawned with no verdict schema). Audit: `research_brief_drafted`. **Skipped** when a signed brief is supplied (`charter.intent_contract.confirmed_by_human == true`).
2. **`gate1_pending`** — the **Customer Gate-1 sign-off**. The driver writes a `customer_gate1_signoff` checkpoint (drafted-brief ref + proposed approved scope), then consults an INJECTED `gate_resolver(gate_id, context, options)` — the human's voice, injected like the `clock`. **The engine NEVER auto-confirms Gate 1.** There is no default that proceeds without an explicit human `sign`:
   - resolver **absent** or returns `None` → audit `customer_gate1_halt`; state stays `gate1_pending`; the driver HALTS for async resolution (on resume the resolver is re-consulted — still no sign ⇒ re-halt).
   - `choice == "sign"` → record the decision (choice/note/resolver) into the checkpoint; audit `customer_gate1_signed`; set `brief_signed`; proceed.
   - `choice == "reject"` → audit `customer_gate1_rejected` + HALT (brief needs rework).
   - `choice == "abort"` → audit `customer_gate1_aborted` + halt the run.
   **Skipped** together with `research_pending` when the brief is signed upfront.
3. **`decompose_pending`** — `_step_decompose` spawns Deliver to decompose the SIGNED brief into an ordered sub-sprint plan, validated against `schemas/deliver-plan-verdict.schema.json` (invalid → `gate_hard_fail`). The plan's `sub_sprints[].id` sequence becomes `approved_scope.subsprint_sequence` (when not supplied) so milestone terminality is computable. Audit: `milestone_decomposed`. **Skipped** when a non-empty `subsprint_sequence` is supplied upfront (audit `decompose_skipped`).

**Post-Gate-1 scope-expansion guard** (deterministic): after decompose, the union of every `sub_sprints[].modules` and `.layers` is compared to the human-signed envelope `approved_scope.{modules_in_scope, layers_allowed}`. Any module/layer in the plan but NOT in the envelope → `post_gate1_scope_expansion` checkpoint (human-confirm) + audit + HALT (the engine does NOT widen scope past the Gate-1 sign-off without human confirmation — same invariant as §4.2.5). If the envelope is empty/absent the plan defines scope (no expansion possible) → audit note `scope_envelope_unset` and proceed.

All pre-states are out-of-band (like `acceptance_pending`): every transition persists to `state.json`, every transition emits an audit event, and `run(resume=True)` re-enters at the persisted pre-state with the hash chain intact across the halt→resume boundary. With both a signed brief and a supplied sequence, `full_chain_guided` behaves exactly like the delivery loop.

#### §4.2.5 scope_envelope_check (deterministic, no LLM)

Pure function over `(charter.approved_scope, observed_diff, declared_next_subsprint)`. No LLM involvement; deterministic boolean output. Runs at every `close_pending`.

Checks:
1. `subsprint_id ∈ charter.approved_scope.subsprint_sequence`.
2. Every layer claimed touched ∈ `charter.approved_scope.layers_allowed`.
3. Every module touched ∈ `charter.approved_scope.modules_in_scope` AND ∉ `explicitly_out_of_scope`.
4. No module touched that's not declared anywhere — flags `unknown_module`.

Any failure → `scope_deviation` MANDATORY_CHECKPOINT fires. Orchestrator halts and writes the checkpoint with all 4 check results; human resolves via:
- Accept-deviation: widen `approved_scope` (writes new charter version; orchestrator resumes).
- Reject-deviation: orchestrator rolls back fix round; spawn_deliver_plan_fix re-runs with narrower guidance.
- Abandon: halt the orchestrator run.

The check is intentionally STATIC and BOOLEAN. No LLM judgment.

#### §4.2.6 F5 evidence pattern

When Acceptance needs execution evidence, orchestrator runs the eval harness and feeds artifact paths to Acceptance.

The same `charter.tooling.eval.cmd` is also used earlier at `gate_pending` as a sub-sprint deterministic gate when configured. The two runs are kept separate on disk:
- sub-sprint gate evidence: `eval/runs/<sub-sprint-id>/subsprint_gate/`
- Acceptance F5 evidence: `eval/runs/<sub-sprint-id>/acceptance/`

```
charter.tooling.eval.cmd = "<shell-command>"
charter.tooling.eval.timeout_seconds = <int>

gate_pending state:
  orchestrator → execute charter.tooling.eval.cmd
              → capture stdout / stderr under eval/runs/<sub-sprint-id>/subsprint_gate/
              → on failure:
                  emit gate_hard_fail MANDATORY_CHECKPOINT;
                  do NOT run Review or Deliver close

acceptance_pending state:
  orchestrator → execute charter.tooling.eval.cmd
              → capture stdout / stderr / artifacts under eval/runs/<sub-sprint-id>/acceptance/
              → on success (exit 0 within timeout):
                  pass artifact paths to spawn run_acceptance as read-only context
              → on failure:
                  emit gate_hard_fail MANDATORY_CHECKPOINT;
                  human resolves (re-run / accept-failure-and-route / abort)

run_acceptance:
  reads evidence in read-only sandbox
  reads closure_contract from research-briefs/<id>.md
  produces JSON verdict per schemas/acceptance-verdict.schema.json
```

**Execution contract (CWD + env).** The orchestrator runs `eval.cmd` with **CWD = the
per-gate artifacts dir** (`eval/runs/<sub-sprint-id>/<gate>/`), NOT the work repo — this
keeps the two gates' stdout/stderr evidence separate. Two env vars are exported for the
cmd to anchor itself:

- `EVAL_REPO_DIR` — the bound work repo (empty when no repo is bound; a repo-anchored cmd
  then fails, correctly, rather than probing the artifacts dir);
- `EVAL_RUN_DIR` — the per-gate artifacts dir itself (the CWD).

A repo-anchored check ("run the tests") MUST be written `cd "$EVAL_REPO_DIR" && <cmd>`.
The charter validator emits an advisory `eval_cmd_cwd_anchor` WARN when `eval.cmd`
references neither variable. On failure, the `gate_hard_fail` checkpoint carries the
evidence paths (`stdout.txt` / `stderr.txt`) plus the stderr tail, so the human rules on
the actual output without opening the run dir.

**Why F5**:
- Dev sandbox is workspace-write; orchestrator-run keeps bad-case suite outside Dev sandbox (no eval contamination).
- Acceptance sandbox is read-only; Acceptance cannot run scripts or mutate the repo. F5 lets Acceptance judge from real execution data WITHOUT giving Acceptance write access OR the dev sandbox.
- Both sandboxes stay sealed; evidence flows through filesystem.

**F5 forbidden patterns** (anti-patterns; §4.2.8):
- Letting Acceptance run the eval harness itself (sandbox breach + non-reproducible).
- Acceptance verdict claiming pass/fail from CODE INSPECTION alone, not execution evidence.

#### §4.2.7 Spawn function set + JSON verdict schemas

Each spawn function has a published JSON-schema verdict shape so orchestrator parses deterministically without LLM string-matching.

| Function | Backing agent (per charter) | Tools | Verdict schema |
|---|---|---|---|
| `spawn_dev` | `charter.tooling.dev.agent_kind` | workspace-write; network follows `tooling.dev.network_access`; no git push | (none — code edits + handoff file IS the artifact) |
| `spawn_deliver_close` | `charter.tooling.deliver.agent_kind` | default | `schemas/deliver-close-verdict.schema.json` |
| `spawn_deliver_plan_fix` | `charter.tooling.deliver.agent_kind` | default | `schemas/deliver-plan-fix.schema.json` |
| `spawn_research` | `charter.tooling.research.agent_kind` | default | `schemas/research-brief.schema.json` |
| `run_review` | `charter.tooling.review.agent_kind` | Read, Grep, Glob whitelist | `schemas/review-verdict.schema.json` |
| `run_acceptance` | `charter.tooling.acceptance.agent_kind` | Read, Grep, Glob whitelist | `schemas/acceptance-verdict.schema.json` |

**Verdict-shape summaries** (full schemas in `schemas/`):

- **`deliver_close_verdict`**: `{verdict: A|B|C|D, blocking_count, worst_severity, in_scope, next_subsprint, reason}`
- **`deliver_plan_fix_verdict`**: `{subsprint_id, layers[], modules[], objective_md, dev_prompt_md, summary}`
- **`research_brief_verdict`**: `{brief_id, brief_md, closure_contract_summary, scope_in[], scope_out[]}`
- **`review_verdict`**: `{decision, blocking_count, summary, findings[]}` with per-finding `{id, severity, layer, evidence[], rationale}`
- **`acceptance_verdict`**: `{milestone_verdict, cases[], failure_briefs[], suggested_route}` with per-case `{case_id, criterion, evidence_path, verdict, rationale}`

**Verdict parsing**:
- Orchestrator parses with schema validator.
- Invalid verdict = `gate_hard_fail` MANDATORY_CHECKPOINT.
- Schema violation does NOT silently default to permissive verdict. Agent re-runs OR human resolves.

**Prompt resolution (strict mode)** — in strict mode (`context.allow_real` OR any non-mock adapter wired; `process/prompt-artifact-rules.md` §6.2), `spawn_dev`, `run_review`, and `run_acceptance` do NOT dispatch a one-line role request. Each resolves a **self-contained** prompt by content and, when the source is missing/incomplete, persists a **genuinely resumable refinement HALT** (`STATE_HALTED` + a persisted `halt_resume_state` so a re-run re-enters the paused state and re-resolves, + a `*_spec_refinement` checkpoint) instead of spawning a thin prompt:

- `spawn_dev` — decompose-plan entry (canonical) → adopter `compact/<id>-dev-prompt.md` → HALT.
- `run_review` — adopter `compact/<id>-review-prompt.md` → deterministic projection from the resolved sub-sprint spec (objective/scope/exit-criteria + Dev handoff/diff refs + anti-hardcode kernel + severity rules + the `review-verdict` schema) → HALT. Sub-sprint-scoped.
- `run_acceptance` — adopter `compact/<scope>-acceptance-prompt.md` → projection from the **human-signed** `intent_contract` (Customer need + acceptance criteria) + closure_contract/brief + F5 evidence + Reviewer-outcome refs + calibration/authority + the `acceptance-verdict` schema → HALT. Milestone-scoped; runs AFTER the §3.6 calibration gate + F5 eval and only **reports** calibration/authority (never alters them). An unsigned/incomplete contract HALTs (§3.4 invariant #4).

These are **two distinct contracts** (no generic role projector). Offline/mock runs keep the legacy inline prompt (byte-identical). Whatever is dispatched is materialized through the per-spawn transcript (§4.2.10).

#### §4.2.8 Δ-18 anti-patterns (FORBIDDEN — extensions to Constitution §1.7)

Each violation is a framework breach; orchestrator implementations MUST refuse / halt / surface.

1. **Charter bypassing a default MANDATORY_CHECKPOINT in any of the four shapes — omitted / emptied / disabled / overridden** (Constitution §1.7-D + §4.2.2 charter editing rules). Charter validator rejects each shape. Semantic override counts as bypass. Legitimate path: ADD a custom checkpoint alongside default.
2. **Letting an uncalibrated `run_acceptance` ship or auto-iterate without human sign-off**. In `fully_autonomous_within_budget` mode without §3.6 calibration passed, the orchestrator MUST degrade `autonomy.level` to `human_on_the_loop` automatically (not optional, not opaque). The uncalibrated verdict then RUNS in ADVISORY mode — a `pass` HALTs at `advisory_acceptance_pass_signoff` for human sign-off (this advisory-with-sign-off path is PERMITTED); what is forbidden is auto-shipping or auto-iterating on that uncalibrated verdict without the sign-off.
3. **Bypassing `scope_envelope_check` on close**. Even if LLM close verdict says `in_scope: true`, scope_envelope_check is the source of truth.
4. **Giving Dev sandbox read access to `case_specs_shadow/`** (or equivalent holdout). Eval contamination.
5. **Acceptance verdict claiming pass/fail from CODE INSPECTION instead of execution evidence** — F5 pattern violation. Verdicts referencing only code paths and not artifact paths in `evidence_path` are invalid.
6. **UNATTENDED auto-iterate/auto-ship on an uncalibrated verdict** (e.g., `tooling.acceptance.mode=auto` shipping a `pass` while `judge_calibration.status=uncalibrated`) — degradation must be automatic and recorded, never opaque. The advisory-with-sign-off path (uncalibrated verdict runs, then HALTs at `advisory_acceptance_pass_signoff`) is PERMITTED; auto-shipping/auto-iterating without that human sign-off is the breach.
7. **Spawning the Acceptance Agent from a Deliver or Dev session** (Constitution §1.7-C).
8. **Acceptance routing `fix_required → Deliver` without a written human-confirm checkpoint decision** (Constitution §3.5).
9. **Charter `tooling.acceptance.on_fix_required.human_confirm_required: false`** — direct violation of Constitution §1.7-C.
10. **Charter validator silently accepting an empty `route_options` list** — at least one option must be present.
11. **Auto-promoting an OBS-item to an R-item without human review** (per Δ-9). Orchestrator may surface candidate; promotion is human.
12. **Mid-milestone scope expansion via adaptive_insert beyond `max_inserted_subsprints`**. Bounded; over-limit = halt.
13. **Mounting a role skill (or spawning an intra-role sub-agent) that exceeds the role's tool whitelist or sandbox** — e.g., a review/acceptance skill declaring tools beyond `[Read, Grep, Glob]`, or a Dev sub-agent exceeding the role's network grant (Constitution §3.4 invariant #6; `process/role-skill-model.md` §4). Inheritance is transitive; the spawning role's session owns the breach.
14. **Acceptance drives the browser itself** (P-C; `process/browser-e2e-acceptance.md` §4). The browser-E2E EVIDENCE run is orchestrator-executed in the out-of-band `e2e_evidence_pending` state; Acceptance stays read-only (`[Read, Grep, Glob]`) and judges the COMMITTED, hash-anchored manifest. An Acceptance session that launches the app, drives a browser, or runs the executor is a sandbox breach (same shape as anti-pattern #5: judging from self-run execution rather than orchestrator-captured evidence) and forfeits the read-only-judge independence. The executor produces OBSERVATIONS only (`executor_status`); the verdict is Acceptance's alone.

#### §4.2.9 Filesystem layout for an orchestrator run

```
<adopter>/
  charter.yaml
  docs/
    checkpoints/
      20260611-091230__mission_start__M5.md
      20260611-141500__bad_case_manual_review__M5.md
    research-briefs/<id>.md
    acceptance-reports/<scope>-acceptance-report.md
    codex-findings.md
  eval/
    bad_cases/                # read by run_acceptance via F5
    runs/<run-id>/             # per-eval-run artifact dir
      stdout.txt
      artifacts/
  .orchestrator/               # state; gitignored typically
    state.json
    charter-snapshot.yaml      # immutable copy at boot
    fix_round.txt
    audit/
      <loop_id>.jsonl          # hash-chained Audit Spine (one ledger per loop)
      transcripts/<loop_id>/   # per-spawn execution record (auditability §4.2.10)
        0001__dev__prompt.md       # the EXACT dispatched prompt (verbatim)
        0001__dev__output.md       # the captured Dev artifact (handoff prose)
        0002__review__prompt.md    # the EXACT dispatched reviewer prompt
        0002__review__output.json  # the captured reviewer verdict
        …                          # one prompt+output pair per spawn / fix-round
```

Adopters MAY relocate `.orchestrator/`. Other paths follow Constitution §5 state-ledger conventions.

#### §4.2.10 Spawn transcripts (prompt + output auditability)

EVERY orchestrator spawn — Dev, Code Reviewer, Deliver/close, Research, Acceptance, and each fix-round re-run — materializes its **exact dispatched prompt** (`NNNN__<role>__prompt.md`, written verbatim) under `.orchestrator/audit/transcripts/<loop_id>/`, and — **whenever the adapter returns a candidate output** — the **captured model output** (`NNNN__<role>__output.{md,json}` — readable Markdown for a Dev/Research artifact, pretty-printed JSON for a verdict). The single spawn event on the Audit Spine references both as `prompt_ref` / `output_ref`. An adapter **transport error** (no output produced) records `prompt_ref` with `output_ref: null` and `verdict_ref: adapter_error` — the prompt is always captured, the output only when one exists. So the loop is auditable **file-by-file**, not merely by the `input_hash` digest. Because the prompt is byte-exact, `sha256(role\x00 + prompt_file)` recomputes the ledger's `input_hash` — the transcript is tamper-cross-checkable against the hash chain.

This is the **as-dispatched execution record** and is distinct from the **durable, human-reviewed prompt artifacts** in `compact/` (`process/prompt-artifact-rules.md` §1): the `compact/` files are the source views a human approves before dispatch; the transcripts are what each spawn actually sent and received. The output transcript is written **before** verdict-schema validation, so even a schema-invalid verdict (a `gate_hard_fail`) leaves its output on disk to audit.

### §4.3 Code Reviewer trigger conditions

The orchestrator's `run_review` spawn fires at:
- Sub-sprint close (default).
- §4.3 fine-grained triggers (mid-sprint):
  - Diff touches a semantic-decision surface (prompt projection / planner / judge).
  - Diff touches a Tier-0 invariant declared in `docs/current/runtime_invariants.md`.
  - Code Reviewer's previous verdict said `out_of_scope_review` and Deliver claims new sub-sprint resolves the gap.
  - Bad-case suite run surfaces a new failure shape (per `process/badcase-lifecycle.md`).

Adopters tighten / loosen this trigger set in `docs/current/adoption-state.md` per Constitution §7.0.

### §4.4 Auto-fix iteration bounds

**Severity policy (P0/P1 block; P2 is record-only).** Only **P0/P1** findings are blocking: they drive `decision: fix_required`, count toward `blocking_count`, and are the ONLY findings injected into the Dev auto-fix brief. **P2 is strictly record-only** — it stays in the Reviewer verdict (`docs/codex-findings.md`) and the audit ledger (and/or an improvement backlog), but is never fixed, never counted, and never blocks close. A `fix_required` whose findings are **all P2** carries no blocking work: the engine **normalizes it to a clean pass** — fail-closed (only when `findings` is non-empty and every entry is a known-severity P2; an empty / unknown-severity / malformed finding set keeps the existing `fix_required` handling) — and audits the original + effective decision + reason as `review_decision_normalized`.

When `run_review` returns `fix_required` (carrying ≥1 blocking P0/P1 finding) AND charter permits `auto_fix_iteration.enabled: true`:
- Orchestrator increments `fix_round` counter.
- If `fix_round > charter.auto_pass_rules.auto_fix_iteration.max_rounds` → halt; emit `gate_hard_fail`.
- If any finding severity > `only_if_findings_severity_at_most` → halt; emit MANDATORY_CHECKPOINT.
- Else spawn `spawn_deliver_plan_fix` with the **blocking (P0/P1) review findings** as input (P2 findings are NOT injected into the fix brief); produce new sub-sprint; re-enter `dev_pending`.
- If the re-review returns a clean pass, the loop enters `close_pending` and runs `spawn_deliver_close`; only a clean Deliver close can emit `advance`. Auto-fix success never means Review can advance the loop by itself.

The bound prevents infinite Dev ↔ Review ping-pong.

### §4.5 Idempotency and resume

- Each `spawn_*` call writes inputs hash + verdict under `.orchestrator/calls/<call-id>.json`.
- Resume after restart: read `state.json`; re-enter from current state.
- A spawn called twice with same input hash returns cached verdict (idempotency cache). Adopters MAY invalidate by deleting the corresponding `.orchestrator/calls/` file.
- Matters most for `spawn_research` and `run_acceptance` (expensive).
- Loop registry close is bookkeeping, not delivery authority: if a successful terminal loop reaches close and the registry row is missing, the orchestrator repairs the row and marks it done rather than failing the already-completed delivery chain.

## §5 Adopter bootstrap pointers

For step-by-step orchestrator adoption:
- Greenfield: `docs/greenfield-guide.md` STEP 7 (optional bootstrap).
- Brownfield: `docs/brownfield-guide.md` (OPT OUT recommended unless multi-sub-sprint cycles to automate).
- Per-charter authoring: `templates/mission-charter.yaml` is starting template; `schemas/mission-charter.schema.json` validates.
- Calibration set authoring: see `process/badcase-lifecycle.md`.

Recommended adoption ladder:

1. Adopt the 5-role chain (Constitution §3) in pure human-paste mode. No orchestrator. Make sure all 5 roles can execute and Acceptance fix_required → human-confirm → Deliver flow works manually.
2. Author a minimal charter with `autonomy.level: human_in_the_loop` and `tooling.acceptance.mode: off`. Run orchestrator on a small test milestone. Verify all checkpoints fire and you resolve via filesystem inbox.
3. Set `tooling.acceptance.mode: advisory` with `judge_calibration.status: uncalibrated`. Watch orchestrator auto-degrade `autonomy.level` to `human_on_the_loop`; the advisory pass HALTs at `advisory_acceptance_pass_signoff`. Resolve the first Acceptance checkpoint manually.
4. Build the labeled calibration set (per Constitution §3.6). Re-run; verify status flips to `calibrated`.
5. Promote `autonomy.level` to `human_on_the_loop`. Run a full milestone with only MANDATORY_CHECKPOINTS firing.
6. (Optional) Promote to `fully_autonomous_within_budget` once multiple successful `human_on_the_loop` runs are done AND adopter is comfortable with budget caps.

Skipping ladder rungs is permitted; framework does not enforce the order.

## §6 Open questions / OQs carry

- **OQ-V4-001** (Δ-18 Type B placeholder) — full Type B state machine + SOP per-step gate spec deferred until hermes-autoloop completes its first SOP milestone end-to-end. Lessons fold back to v5.
- **OQ-V4-007** (calibration cost on model swap) — re-calibration runs full labeled set; potentially costly. Open question whether framework should provide "calibration cache" / labeled-set portability story. Defer to first multi-model adopter.
- **OQ-V4-009** — **RESOLVED** (2026-06-17): the governance validators (`charter_validator`, `stanza_validator`) ship + are tested in `engine-kit/validators/`; the remaining referenced scripts (`precommit_bundling_check.sh`, `trace_emitter.py`) are optional adopter / adopter-runtime tooling — not framework-blocking (`tools/README.md`). The orchestrator does not depend on any of them.

## §7 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8. Adopter-specific orchestrator overrides (custom checkpoints, custom verdict fields, extended T1 profile) live in adopter `docs/current/adoption-state.md` divergence rows. Framework-side changes to MANDATORY_CHECKPOINTS, scope_envelope_check semantics, or state machine shape require Constitution §1.7-D-aware fold-back review.

---

End of Δ-18 Delivery Loop spec.
