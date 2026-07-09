---
name: 2026-07-09-phase2-requirement-chain-design
doc_category: intermediate
status: codex-approved (R0.5 APPROVE 2026-07-09, 0 blocking — after R0 5B+4N, R0.2 3B+2N, R0.3 2B+1N, R0.4 1B+1N all folded, tagged in place; R0.5 non-blocking notes folded post-approve)
created: 2026-07-09
base_commit: edf678e (origin/main HEAD = PR #12 merge, Phase-1 campaign-unblock landed)
parent_design: archive/2026-07-09-autonomy-roadmap-campaign-unblock.md §3 (roadmap R0.3 APPROVE)
branch: feat/phase2-requirement-chain (worktree ../aidazi-phase2)
reviewer: >
  codex gpt-5.5 xhigh — R0 REVISE (B-1 unrunnable emitted plan / B-2 unpersisted gate-1
  envelope / B-3 research-brief input_path enum / B-4 no-ledger covers_req_ids gap / B-5
  checkpoint-taxonomy classification; N-1..N-4) → R0.2 REVISE (B-1 acceptance intent-contract
  hard gate / B-2 research never reads the requirement / B-3 Stage-2 sub_sprints unbounded;
  N-1 decision `choice` field, N-2 global compact-path uniqueness) → R0.3 REVISE (B-1
  --repo-dir threading for strict compact lookup / B-2 generated prompts unbound to plan
  signoff; N-1 refusal checkpoint kinds underspecified) → R0.4 REVISE (B-1 TD6 restamp
  carry-forward for prompt_artifacts_digest; N-1 §5.2 wording) → R0.5 APPROVE (0 blocking;
  2 non-blocking notes folded: restamp-path wording + repo_dir threading incl. scope_report
  and run_loop status consumers)
---

# Phase-2 — requirement-driven chain (one command from requirement to campaign)

**Goal (roadmap §3, verbatim intent):** collapse the 4 manual steps between "a requirement
file exists" and "a signed campaign is running" (Research session → gate-1 → hand-run Deliver
decompose → hand-author campaign-plan.json → --sign-plan) into ONE CLI entry that interrupts
the human for exactly the two constitutional signatures — ideally in one sitting — and
nothing else before the first advisory acceptance.

**Non-goals (locked):** no new human authority is created or removed; `customer_gate1_signoff`
and `campaign_plan_signoff` keep their semantics byte-for-byte; no constitutional amendment;
no parallel-runner work (Phase-4); no notifications/halt-conditions (Phase-3); no adopter
bootstrap (Phase-5). Real-CLI activity in this phase (canary) is env-gated per the standing
user rule.

---

## §1 Current state (verified at base `edf678e`; anchors re-checked in this worktree)

1. **Guided pre-chain exists at the SINGLE-MILESTONE tier only** (P6.1,
   process/delivery-loop.md §4.2.4-G): `research_pending → gate1_pending → decompose_pending`
   implemented as Driver pre-states — `_step_research` driver.py:2330-2366, `_step_gate1`
   driver.py:2368-2465 (no-auto-sign invariant at :2418-2431), `_step_decompose`
   driver.py:2484-2568 — orchestrated by `_drive_guided_prestates` driver.py:2635-2672.
   Decompose output = `deliver-plan-verdict.schema.json` (sub-sprints), NOT a campaign backlog.
2. **The scope-expansion guard is a pure function + a halt wrapper**:
   `_scope_expansion_guard` driver.py:2570-2599, `_scope_expansion_halts` driver.py:2601-2633
   (writes `post_gate1_scope_expansion` checkpoint, HALT). Envelope source =
   `charter.autonomy.approved_scope.{modules_in_scope, layers_allowed}` READ LIVE from the
   charter at guard time (driver.py:1376-1380, :2325-2328) — nothing snapshots the envelope
   at gate-1 sign time today; `RunState` (driver.py:419-573) carries only `brief_signed`
   [R0 B-2 evidence]. Current single-tier behavior on an EMPTY envelope: audit
   `scope_envelope_unset` and PROCEED (plan defines scope) — driver.py:2608-2613. Roadmap
   R0 B-1 explicitly TIGHTENS this for the campaign tier (§3.1).
3. **CLI entry**: `engine-kit/scheduling/run_loop.py` (argparse :1110-1157). Campaign dispatch
   at :1174, `--sign-plan` at :1187 → `campaign.stamp_signoff` (campaign.py:2927-2959, Δ-19
   F1 `signed_scope_hash`), campaign preflight stack at :734-753. Exit codes: single-loop
   0/1/2; campaign 0 done / 1 error / 2 invalid / 10 paused / 11 ended (run_loop.py:69-77).
4. **Gate-1 resolution channels**: interactive TTY resolver `make_interactive_gate_resolver`
   run_loop.py:464-498 (wired only for `--loop-mode full_chain_guided` at a TTY);
   identity-bound file resolver `make_campaign_decision_resolver` run_loop.py:509-652.
   Async gate-1 halts persist with state REMAINING `gate1_pending` (the resolver is simply
   re-consulted on `--resume`; NOT the `STATE_HALTED + halt_resume_state` Mechanism-A path,
   driver.py:2421-2431 vs :2765-2769) [R0 N-2 fix]. In campaigns, `customer_gate1_signoff`
   is classified `DRIVER_RESUME_CHECKPOINTS` (campaign.py:116-121).
5. **Campaign plan validation machinery (reusable as-is)**: schema-first ingress
   campaign.py:586; `topological_order` campaign.py:436-465; cross-milestone `covers_req_ids`
   uniqueness campaign.py:621-630; per-milestone subsprint-id uniqueness campaign.py:608-615
   (PER-MILESTONE ONLY — nothing today forbids the same sub-sprint id in two different
   milestones [R0.2 N-2 evidence]); strict ledger loader `load_and_validate_ledger`
   campaign.py:2595-2634 (absent=dormant, present-broken=raise); OW-M3
   `mandatory_e2e_violations` campaign.py:2962-3009 (DORMANT when the ledger is absent —
   campaign.py:2981 — hence §3.3(c)'s explicit no-ledger rule [R0 B-4]);
   requirement-context projection campaign.py:2645-2666.
6. **A plan whose milestone lacks `subsprint_sequence` is NOT runnable without another human
   interruption** [R0 B-1 evidence]: the campaign core pauses `milestone_decompose_required`
   (campaign.py:2314-2322), resolved by EDITING THE PLAN (campaign-decision.schema.json
   description: "milestone_decompose_required -> fill subsprint_sequence"; decision files do
   not apply) — and any post-signature plan edit flips `signoff_status` to `stale`
   (campaign.py:3107-3147) forcing a RE-SIGN. Therefore the bootstrap MUST emit a plan with
   every milestone's `subsprint_sequence` filled AND the strict-prompt sources materialized
   (§3.2/§3.3), or the "zero interruptions until first advisory acceptance" shape is violated
   per milestone.
7. **Schema extensibility constraint**: `campaign-plan.schema.json` is
   `additionalProperties: false` at every object level EXCEPT the intentional requirement-id
   map `covered_req_surfaces` (campaign-plan.schema.json:47) [R0 N-1 fix] ⇒ the emitted plan
   still cannot carry per-milestone `modules`/`layers`; that footprint lives in the sidecar
   (§3.3-g).
8. **Strict-prompt regime (Phase-1-hardened)**: real mode refuses thin prompts
   (`_strict_prompts` driver.py:1892-1905); the Dev spec resolution priority is
   (1) schema-valid entry in `state.planned_subsprints` → engine projection, else
   (2) adopter-authored `<repo>/compact/<sid>-dev-prompt.md` (driver.py:1658, :1713, :1915;
   review analog `<repo>/compact/<sid>-review-prompt.md` driver.py:1809), else
   (3) `dev_spec_refinement` HALT. Campaign units start with fresh per-unit RunState (no
   `planned_subsprints`), so path (2) is the ONLY no-interruption strict-prompt channel for
   bootstrap-produced campaigns — exactly the channel the Phase-1 real canary proved at
   runtime (its workspace shipped `compact/<sid>-{dev,review}-prompt.md`,
   `context_budget.self_contained: true`). The compact lookup key is REPO-GLOBAL
   (`compact/<sid>-…`), which is why §3.3(f) needs plan-wide sid uniqueness [R0.2 N-2].
   Golden fingerprint test test_driver.py:377-424 pins prompt bytes; new projected prompts
   must be added to the fixture with rationale.
9. **Research brief schema**: `schemas/research-brief.schema.json` — `input_path` is a CLOSED
   ENUM `["path_1_customer_ask", "path_2_bad_case_matured"]` (:21-24,
   additionalProperties:false), so the requirement FILE cannot be referenced through the
   brief [R0 B-3 fix]. The requirement binding therefore lives OUTSIDE the brief: run-dir
   snapshot + sha256 audit + sidecar (§2 step 1); the brief uses
   `input_path: "path_1_customer_ask"` (a requirement IS a customer ask).
10. **`GateHardFail`** (driver.py:2748-2751) propagates out of `Driver.run()` after the
   `gate_hard_fail` checkpoint is written; single-loop `main()` today only catches
   `CharterValidationError` — the bootstrap entry must catch `GateHardFail` explicitly to
   honor its exit-code contract (§4) [R0 N-3].
11. **Acceptance has a HARD intent-contract gate on strict runs** [R0.2 B-1 evidence]:
   `_resolve_acceptance_spec` (driver.py:4814-4851) enforces Constitution §3.4 invariant #4
   BEFORE any acceptance source (compact or projection): incomplete/unsigned
   `charter.intent_contract` ⇒ `acceptance_spec_refinement` HALT. Gate-1 signing sets only
   `RunState.brief_signed` (driver.py:2437-2445) — it does NOT produce an intent contract.
   Campaign units get their charter via `derive_milestone_context` (campaign.py:3232-3284),
   a DEEP COPY of the base charter (+ subsprint_sequence / functional-acceptance / signals
   projection) — so a signed `intent_contract` in the BASE charter reaches every unit's
   acceptance gate; the plan's `acceptance_bar` is NOT projected into the derived charter
   and does not need to be (the Phase-1 real canary's advisory acceptances passed with
   exactly this shape: signed charter intent_contract + plan acceptance_bar).
12. **`_step_research` reads NOTHING but the charter mission** [R0.2 B-2 evidence]: its
   prompt is built from `mission.id` only (driver.py:2352-2358), and its skip rule keys on
   `state.brief_signed`, which is pre-set from `intent_contract.confirmed_by_human` at boot
   — i.e. "confirmed intent contract" is today's PROXY for "signed brief upfront"
   (driver.py:2344-2350, test_driver.py `test_signed_brief_upfront_skips_research_and_gate1`).
   Consequence: since §2's entry precondition REQUIRES a confirmed intent contract
   [R0.2 B-1], the proxy rule would ALWAYS skip research/gate-1 and no brief would ever
   exist — the bootstrap mode MUST decouple the two (§2 step 0b).
13. **Stage-2's verdict schema is unbounded**: `deliver-plan-verdict.schema.json:10-13`
   (`sub_sprints`, minItems 1, NO maxItems) [R0.2 B-3 evidence] — and it is SHARED with the
   single-milestone tier, so the bound must live in bootstrap code, not in the schema (§3.2).
14. **Compact lookup is repo_dir-dependent** [R0.3 B-1 evidence]: the strict compact-prompt
   source resolves `<repo>/compact/<sid>-…` ONLY when a repo dir is configured — "or None
   when no repo is" (driver.py:1658) — so a real campaign started WITHOUT `--repo-dir`
   silently loses path (2) of §1.8 and halts `dev_spec_refinement` at the first unit. The
   bootstrap and every command it prints must therefore carry the resolved repo dir (§2
   preflight 0c, §3.4, §4).
15. **There is a shipped precedent for binding OPTIONAL artifact digests into the plan
   signature** [R0.3 B-2 fix pattern]: `milestone_signals_digest` — an optional field stored
   in the signoff block AND inside `scope_envelope` (campaign-plan.schema.json:14-104),
   computed by `stamp_signoff` (campaign.py:2927-2959), re-verified by `signoff_status`
   freshness + Campaign ingress (the `derive_milestone_context` docstring: signals are passed
   "only AFTER the signoff digest verified"), and DORMANT when absent (legacy plans
   byte-identical). §3.5 reuses this exact pattern for generated prompt artifacts.

---

## §2 Design overview — lift the guided pre-chain one tier

**New entry:**

```
python3.12 engine-kit/scheduling/run_loop.py \
  --requirement <requirement.md> --charter charter.yaml --repo-dir <repo> \
  --campaign-out campaign-plan.json [--campaign-id <slug>] [--resume] [--decision d.json] [--allow-real]
```

**State flow (new bootstrap mode, `loop_mode="campaign_bootstrap"` — internal, NOT exposed in
`--loop-mode` choices):**

```
[entry preflight 0a: signed intent_contract present?  — else rc 2 refusal]     [R0.2 B-1]
[entry preflight 0b: envelope non-empty?              — else HALT scope_envelope_unset]
[entry preflight 0c: --repo-dir REQUIRED + resolvable — else rc 2 refusal]     [R0.3 B-1]
      │
research_pending ──► gate1_pending ──► campaign_decompose_pending (NEW) ──► DONE
      │(ALWAYS runs in this  │(UNCHANGED semantics;          │ two-stage decompose (§3.2)
      │ mode — §2 step 0b;   │ + NEW: envelope SNAPSHOT      │ + validation stack (§3.3)
      │ prompt grounded in   │ into RunState at sign         │ + plan w/ FILLED subsprint_
      │ the requirement      │ [R0 B-2])                     │   sequence + compact prompts
      ▼ snapshot [R0.2 B-2]) ▼                               │ + sidecar + sign handoff (§3.4)
   _step_research + a      reuses _step_gate1 verbatim       ▼
   bootstrap-only                                       NEW _step_campaign_decompose
   requirement block
```

- **Step 0a — acceptance-authority precondition [R0.2 B-1]:** the entry REQUIRES the charter
  to carry a COMPLETE, HUMAN-SIGNED `intent_contract` (`confirmed_by_human: true`), validated
  with the SAME logic the acceptance hard gate already applies
  (`_validate_acceptance_context`, driver.py:4841-4843 call site). Missing/incomplete ⇒ rc 2
  with an actionable refusal listing the fields to fill. Rationale: Constitution §3.4
  invariant #4 — Acceptance judges ONLY a human-signed contract; every campaign unit's
  acceptance will demand it (§1.11), so a requirement-start without it would inevitably
  pause at `acceptance_spec_refinement` mid-campaign. Checking it up-front converts a
  buried mid-campaign halt into an immediate, explainable preflight refusal. This was
  already the Phase-1 canary prerequisite (roadmap R0 B-4); NO new authority — the engine
  never writes or edits the intent contract, it only refuses to start without one.
- **Step 0b — decoupled skip rule [R0.2 B-1 consequence, §1.12]:** in `campaign_bootstrap`
  mode, `brief_signed` is NOT pre-set from `intent_contract.confirmed_by_human`; research and
  gate-1 ALWAYS run. Justification: the requirement is a NEW customer ask — the per-
  requirement scope authority is exactly what gate-1 signs; the standing intent contract is
  the ACCEPTANCE authority, not a substitute for the campaign-scope brief. (Under the old
  proxy rule, step 0a + the proxy would always skip research/gate-1 and decompose would have
  no brief — the roadmap's "skipped if the charter pins a signed brief" convenience is
  therefore recorded as NOT APPLICABLE at campaign tier; a deliberate, documented deviation
  from roadmap §3 step 1 wording, tighter not looser.) Single-tier behavior untouched.
- **Step 0c — repo-dir preflight [R0.3 B-1]:** `--repo-dir` is REQUIRED for the
  `--requirement` entry (rc 2 refusal when absent or not a directory). Rationale: the strict
  compact-prompt lookup that makes the emitted campaign runnable is repo_dir-dependent
  (§1.14) — an implicit/missing repo dir would surface as a confusing `dev_spec_refinement`
  halt deep inside the first milestone instead of an immediate, explainable refusal. The
  RESOLVED absolute repo dir is: where §3.3(g) writes the compact files, a component of the
  §3.5 digest computation, and carried EXPLICITLY in every printed handoff command
  (`--sign-plan`, campaign run) and by `--start` (§3.4, §4).
- **Step 1 — requirement ingestion [R0 B-3][R0.2 B-2]:** the requirement file is snapshotted
  into the run dir (`<run-dir>/requirement.md`, byte copy) with audit event
  `requirement_ingested {source_path, sha256}`; the SNAPSHOT is canonical from then on (§7
  drift rule). A new RunState field `requirement_ref {path, sha256}` (round-tripped) records
  it. **`_step_research` gains a bootstrap-only prompt block** appended to the existing
  prompt: it names the snapshot path — rendered ABSOLUTE, the same agent-cwd frame-fix
  Phase-1's `_acceptance_evidence_abs` established for F5 evidence — + sha256 and instructs
  Research to read it fully and ground the brief (scope_in/out, closure_contract, kpi) in
  THAT requirement, tracing each scope item to it. Conditional on `loop_mode == "campaign_bootstrap"` ⇒ single-tier research
  prompt bytes unchanged; the new bootstrap research prompt is added to the golden fixture
  (§3.2 golden note). The brief's `input_path` stays within its closed enum
  (`"path_1_customer_ask"`). Research output remains an ARTIFACT (schema_key=None), exactly
  as today.
- **Step 2 — gate-1:** verbatim reuse of `_step_gate1` (same checkpoint kind, same resolver
  contract, same no-auto-sign invariant driver.py:2418). ONE bootstrap-mode addition at the
  `sign` branch [R0 B-2]: the envelope the human just signed (`proposed_approved_scope` =
  modules_in_scope/layers_allowed/explicitly_out_of_scope — exactly what the checkpoint
  showed) is SNAPSHOTTED into a new RunState field `signed_envelope` (round-tripped). Every
  campaign-tier consumer — the §3.1 precondition re-check, the §3.3(b) guard, the decompose
  prompts — reads the SNAPSHOT, never the live charter. Envelope drift after sign (live
  charter ≠ snapshot, compared on every entry to `campaign_decompose_pending` incl. resume)
  ⇒ the gate-1 signature is STALE for the new envelope: clear `brief_signed` +
  `signed_envelope`, audit `gate1_envelope_drift`, re-enter `gate1_pending` (a FRESH
  `customer_gate1_signoff` checkpoint over the new envelope). Tighten-only: today the same
  edit silently changes the guard basis with NO re-sign.
- **Step 3 — `campaign_decompose_pending` (NEW, §3):** Deliver decomposes the SIGNED brief
  into an ordered milestone backlog AND per-milestone sub-sprint plans (two-stage, §3.2),
  validated fail-closed, emitted as a campaign-plan.json that is BOTH sign-able AND runnable
  to the first advisory acceptance with zero further interruptions [R0 B-1][R0.2 B-1].
- **Step 4 — signing:** `campaign_plan_signoff` stays exactly `stamp_signoff` (Δ-19 F1).
  One-sitting sequencing in §4.

**Why a Driver bootstrap mode rather than a standalone script:** `_step_research` and
`_step_gate1` carry the tested constitutional invariants (no-auto-sign, resume idempotency,
checkpoint/audit shapes; TestFullChainGuided test_driver.py:2718-3040). The bootstrap mode
reuses them (research with one conditional prompt block, gate-1 verbatim) and only swaps the
third state; after `campaign_decompose_pending` succeeds the Driver run ENDS (state `done`,
audit `campaign_bootstrap_complete`) — it never enters the delivery loop. Campaign execution
stays the existing Phase-1-proven `--campaign` path, byte-identical.

---

## §3 The new state: `campaign_decompose_pending`

### §3.1 Authority precondition (roadmap R0 B-1 tightening) + taxonomy registration

- **At bootstrap ENTRY (preflight 0b, before any spawn) and again on every entry to
  `campaign_decompose_pending`:** REQUIRE a NON-EMPTY envelope — `modules_in_scope` non-empty
  AND `layers_allowed` non-empty. Pre-gate-1 the check reads the live charter (that is what
  gate-1 would sign); post-gate-1 it reads the `signed_envelope` snapshot [R0 B-2].
- Empty/absent (either dimension) ⇒ write NEW checkpoint kind **`scope_envelope_unset`**
  (context: which dimension is empty, what to add to `charter.autonomy.approved_scope`, and
  that this is Customer authority), audit `scope_envelope_unset`, HALT with state REMAINING
  the pending state (gate-1-style re-consult on `--resume`, §1.4 semantics — the human edits
  the charter and re-runs; the precondition re-evaluates; if gate-1 was already signed over
  a DIFFERENT envelope, the §2 step-2 drift rule forces a fresh gate-1).
- Rationale (roadmap R0 B-1, restated): at campaign scope the decompose step must NEVER
  define its own envelope and then check itself against it. The single-milestone tier's
  permissive path (driver.py:2608-2613) is UNCHANGED.
- **Taxonomy registration [R0 B-5]:** the checkpoint inventory test (test_campaign.py:90)
  requires every Driver-emitted checkpoint kind classified in campaign.py's resume taxonomy.
  `scope_envelope_unset` is added UNCONDITIONALLY to `DRIVER_RESUME_CHECKPOINTS`
  (campaign.py:116-121) — Mechanism-A class, same as `customer_gate1_signoff` (resolution =
  human edits inputs, Driver re-enters the pending state). It can only actually fire inside
  the bootstrap in Phase-2, but it is classified globally so the inventory stays total.

### §3.2 Two-stage decompose (prompt projections + verdict schemas) [R0 B-1]

- **Stage 1 — backlog:** new projected prompt `_project_campaign_decompose_prompt`
  (driver.py, adjacent to :2511-2537): self-contained contract instructing Deliver to
  decompose the SIGNED brief (`brief_draft_ref`) into an ordered milestone backlog. Content:
  campaign goal (from the brief), the SNAPSHOTTED envelope verbatim, the requirement-ledger
  projection when a ledger is wired (campaign.py:2645-2666), milestone granularity guidance
  (objectively closable, one acceptance bar each), output schema shape. Verdict schema
  **`schemas/campaign-decompose-verdict.schema.json`**:

  ```
  { "goal": <string, required>,
    "milestones": [ minItems 1, maxItems 12 — deterministic Stage-2 fan-out bound
      { "id", "objective", "acceptance_bar"      (required),
        "modules": [..], "layers": [..]           (required — envelope-guard input),
        "covers_req_ids": [..], "depends_on": [..],
        "functional_acceptance": "static"|"browser_e2e",
        "milestone_signals": [closed vocab]       (optional) } ] }
  ```

  `layers` reuses the closed Δ-9 enum (deliver-plan-verdict.schema.json:48-60).
- **Stage 2 — per-milestone sub-sprints (one Deliver spawn per milestone, sequential,
  bounded by Stage 1's maxItems):** for each milestone, reuse the EXISTING single-tier
  decompose contract shape (`_step_decompose`'s prompt block :2511-2537, adapted to take the
  milestone objective + the snapshot envelope) with the EXISTING verdict schema
  `deliver-plan-verdict.schema.json` and the EXISTING `_validate_subsprint_spec`
  (driver.py:1728-1740) on every entry.
- **Stage-2 bounds [R0.2 B-3]:** `deliver-plan-verdict.schema.json` is SHARED with the
  single-milestone tier and stays untouched (no maxItems added there — tightening it would
  change existing tiers' validation). Instead the bootstrap enforces DETERMINISTIC bounds in
  code, checked immediately after each Stage-2 schema validation and BEFORE any downstream
  work or file write: per-milestone `len(sub_sprints) ≤ 8` and campaign-wide total
  `Σ ≤ 60`. Breach ⇒ deterministic refusal HALT (checkpoint `gate_hard_fail` discipline via
  the existing `_gate_hard_fail` path, message: split the milestone or hand-author the plan).
  Combined with Stage-1 maxItems 12, the pre-signature artifact surface is bounded:
  ≤ 60 sub-sprints ⇒ ≤ 120 compact files.
- Both stages spawn via the uniform `_spawn` boundary (driver.py:985-1164) with schema keys
  `campaign_decompose` / `deliver_plan`; schema-invalid ⇒ `gate_hard_fail`
  MANDATORY_CHECKPOINT (existing discipline, driver.py:2538).
- **Golden fingerprint:** new prompts (bootstrap research block variant, Stage-1, Stage-2
  adaptation) ADDED to golden-signal-free-prompts.json with rationale "Phase-2 new
  campaign-bootstrap prompts"; ALL existing hashes byte-identical (regression-asserted, §7).

### §3.3 Fail-closed validation stack (BEFORE anything is shown for signature)

Order matters; first failure wins; every failure is a checkpoint/HALT or `GateHardFail`,
never a silent downgrade. **Checkpoint kinds [R0.3 N-1], fully specified:** (i) schema-invalid
verdicts and bounds breaches — (a) below — keep the EXISTING `gate_hard_fail` discipline;
(ii) ALL deterministic data-quality refusals — (c) coverage, (d) uniqueness, (f) OW-M3
residuals, (g) compact-file collisions — emit ONE new checkpoint kind
**`campaign_decompose_refusal`** (context: machine-readable refusal reason list + the exact
human fix), state REMAINS `campaign_decompose_pending`, `--resume` re-enters and re-runs the
stack. Like `scope_envelope_unset` [R0 B-5], `campaign_decompose_refusal` is added
UNCONDITIONALLY to `DRIVER_RESUME_CHECKPOINTS` (campaign.py:116-121) so the checkpoint
inventory (test_campaign.py:90) stays total; it can only fire inside the bootstrap in
Phase-2. On resume after a refusal, Stage-1/Stage-2 verdicts persisted in RunState are
REUSED (no re-spawn) when the requirement/brief/envelope snapshots are unchanged — the
refusal loop costs validation only, not Deliver spawns.

- (a) **Verdict schemas + bounds** — Stage 1 against
  `campaign-decompose-verdict.schema.json`; every Stage-2 verdict against
  `deliver-plan-verdict.schema.json` + `_validate_subsprint_spec` + the §3.2 deterministic
  bounds [R0.2 B-3]; invalid/over-bound ⇒ `gate_hard_fail`.
- (b) **Envelope guard (deterministic, reused)** — union of Stage-1 milestone
  `modules`/`layers` AND every Stage-2 sub-sprint's `modules`/`layers` vs the SNAPSHOTTED
  envelope, via the same pure-function shape as `_scope_expansion_guard` (generalized to
  take an entry list; single-tier call site untouched). Any out-of-envelope item ⇒
  `post_gate1_scope_expansion` checkpoint + HALT (existing kind + options). `envelope_unset`
  is impossible here (§3.1 guaranteed non-empty).
- (c) **Coverage-claim authority [R0 B-4]** — deterministic rule BEFORE OW-M3: if the ledger
  is ABSENT (strict loader `FileNotFoundError` path) and ANY milestone carries
  `covers_req_ids`, HALT with an explicit refusal ("coverage claims require a wired
  requirement ledger to verify — wire `charter.requirements.ledger_path` or drop
  `covers_req_ids`"). If a ledger is PRESENT, every claimed rid must exist in it (unknown
  rid ⇒ same refusal). Ledger present-but-broken already raises via the strict loader
  (rc 2). No ledger + no coverage claims ⇒ proceed (dormant, matching today).
- (d) **Global identifier/path uniqueness [R0.2 N-2]** — plan-wide (cross-milestone)
  sub-sprint-id uniqueness, checked deterministically BEFORE any compact write: the runtime
  compact lookup is REPO-GLOBAL (`compact/<sid>-…`, §1.8) while the campaign schema enforces
  only PER-MILESTONE uniqueness (campaign.py:608-615), so duplicate sids across milestones
  would silently share prompt files. Duplicate ⇒ HALT listing the colliding milestone/sid
  pairs. The same pass computes the full generated-path set (dev+review per sid) and refuses
  internal collisions.
- (e) **Plan projection** — verdicts → campaign-plan.json: `campaign_id` (from
  `--campaign-id` or a slug of the requirement filename), `goal`, `delivery_mode:
  "campaign"`, `milestones[]` mapped 1:1 (id, objective, acceptance_bar, covers_req_ids,
  depends_on, functional_acceptance, milestone_signals) **with `subsprint_sequence` FILLED
  from Stage 2** [R0 B-1]. OW-AUTO derivation: when a ledger is wired and a covered rid has
  `surface: user_facing`, the projection sets `functional_acceptance: "browser_e2e"` (PR#7
  semantics) — then (f) re-verifies the result (forcing is checked, not trusted). No
  budget/gap_followup/trunk_branch/milestone_isolation invented: absent ⇒ schema defaults;
  the human may edit the emitted file BEFORE signing (post-signature edits flip
  `signoff_status` to `stale`, self-defeating not dangerous).
- (f) **Full sign-time validation, run EARLY** (the "never show an unsignable plan" rule):
  campaign-plan schema (campaign.py:586 path), `topological_order` (:436-465),
  cross-milestone `covers_req_ids` uniqueness (:621-630), per-milestone subsprint-id
  uniqueness (:608-615), gap-followup bounds (`enforce_campaign_plan_for_real_run`
  run_loop.py:215-231), OW-M3 `mandatory_e2e_violations` (campaign.py:2962-3009) with the
  strict ledger loader. Residual violations (e.g. unclassified requirement) ⇒ HALT with the
  existing rendered refusal (:3012-3036) — a human data-quality fix, never guessed through.
- (g) **Strict-prompt materialization [R0 B-1]** — for every sub-sprint, write the compact
  prompt files the campaign units will consume via resolution-priority path (2) (§1.8),
  under the RESOLVED repo dir from preflight 0c [R0.3 B-1]:
  `<repo-dir>/compact/<sid>-dev-prompt.md` (via the existing `_project_dev_prompt`
  driver.py:1762-1790 rendering) and `<repo-dir>/compact/<sid>-review-prompt.md` (via the
  existing `_project_review_prompt` :1953-2035 rendering with the deterministic
  handoff-ref convention the Phase-1 canary's static review prompts used — exact template
  resolved at impl; both must satisfy `_validate_compact_text` :1743-1759 incl.
  `context_budget.self_contained: true`, asserted by test). Refuse to OVERWRITE any existing
  compact file (adopter-authored is normative): collision with a pre-existing file ⇒ HALT
  listing the colliding sids. Files are written BEFORE signing so the human reviews the very
  prompts the campaign will run — and their BYTES are then bound into the plan signature
  (§3.5) [R0.3 B-2].
- (h) **Sidecar + audit** — full Stage-1+Stage-2 verdicts (incl. per-milestone
  modules/layers) written as `<campaign-out>.decompose-verdict.json`; audit event
  `campaign_decomposed` carrying plan sha256, verdict sha256, requirement-snapshot sha256,
  compact-file list + sha256s, ledger state. Provenance only — nothing at run time reads the
  sidecar (the signed plan + Δ-19 hash stay the single authority).

### §3.4 Emission + handoff

On success: write plan to `--campaign-out`, print a backlog table (id, objective,
covers_req_ids, depends_on, resolved acceptance mode, acceptance_bar, #sub-sprints) + the
compact-prompt file list, then the EXACT next command WITH the resolved repo dir
[R0.3 B-1]:
`python3.12 engine-kit/scheduling/run_loop.py --campaign <out> --charter <charter> --repo-dir <repo> --sign-plan`.
Exit rc 0. Everything after that is the existing Phase-1-proven campaign contract — and
because every milestone ships a filled `subsprint_sequence` + compact prompts under the
resolved repo dir AND the charter carries the signed intent contract every unit's acceptance
gate demands (§1.11, entry preflight 0a), the FIRST pause a clean run can hit is
`advisory_acceptance_pass_signoff` [R0 B-1][R0.2 B-1].

### §3.5 Prompt-artifact signature binding [R0.3 B-2] — the `milestone_signals_digest` pattern

The generated compact prompts are EXECUTABLE runtime specs; unbound, a post-signature edit
to `compact/<sid>-dev-prompt.md` would change the Dev/Review contract without flipping the
signoff stale (runtime reads `compact/` directly; the §3.3(h) sidecar is provenance-only).
Close the hole by binding their bytes into the SAME optional-digest mechanism that already
protects `milestone_signals` (§1.15):

- **New OPTIONAL signoff field `prompt_artifacts_digest`** (campaign-plan.schema.json signoff
  block + `scope_envelope` copy, exactly mirroring `milestone_signals_digest` placement):
  sha256 over canonical JSON of sorted `[[sid, {"dev": <sha256>, "review": <sha256>}], …]`
  for every sid in the plan's `subsprint_sequence`s that has a compact file at sign time
  (per-file entries record which of dev/review exist).
- **Stamped by `stamp_signoff`** (campaign.py:2927-2959) whenever a repo dir is resolvable at
  sign time and ≥1 such compact file exists — i.e. ALWAYS for bootstrap-emitted plans signed
  via §4's inline sign or the printed `--sign-plan --repo-dir <repo>` command. Hand-authored
  plans signed WITHOUT a resolvable repo dir get NO digest ⇒ byte-identical legacy behavior
  (dormant-when-absent, same as signals).
- **Verified by `signoff_status`** (campaign.py:3107-3147; gains an optional `repo_dir`
  param) and therefore by every existing freshness call site (campaign ingress, resume
  re-sign block): digest present ⇒ recompute live and compare — mismatch OR a bound compact
  file now missing/unreadable OR repo dir unresolvable ⇒ **`stale`** (fail-closed, human
  re-signs after reviewing the changed prompts). Digest absent ⇒ dormant (legacy plans,
  zero behavior change).
- Trust boundary: the check runs at ingress/resume freshness points (identical to the
  signals-digest precedent); an edit while a campaign PROCESS is mid-flight sits inside the
  same running-process trust boundary as today's adopter-authored prompts — no new exposure,
  and every process (re)start re-verifies.
- **TD6 engine-restamp rule [R0.4 B-1] — verify-then-carry-forward:** the ENGINE-side plan
  mutation paths — the TD6 `deliver_followup_required` restamp AND the (separate in code)
  §1.7-F gapfix sub-sprint insertion [R0.5 N-1 wording] — rebuild `scope_envelope` via
  `compute_scope_envelope()` and must MANUALLY preserve snapshot-bound optional digests
  (campaign.py:1246-1280) — exactly as they already special-case `milestone_signals_digest`.
  Policy for `prompt_artifacts_digest`, uniform across BOTH paths: (i) digest freshness is
  verified BEFORE any restamp applies (the existing ordering — stale plans pause for
  re-sign, they are never restamped; test-asserted); (ii) the restamp then CARRIES FORWARD
  both digest copies VERBATIM — never recomputes. Rationale: recomputing at restamp could
  silently bless a post-sign prompt edit if the verify-first ordering ever regressed;
  carry-forward is fail-closed by construction. This stays live-accurate because
  engine-inserted remediation sub-sprints are fed by campaign-injected work contracts
  (`_gap_remediation_spec`, campaign.py:1667-1688), NOT compact files — so the carried
  digest still describes exactly the compact-file set. If a future engine mutation ever DID
  add a compact-file-bearing sid, the carried digest would go stale ⇒ human re-sign
  (fail-closed, correct). (iii) `repo_dir` is threaded through EVERY freshness consumer of
  digest-bearing plans, not only `Campaign._signoff_status()`: `apply_engine_restamp_to_plan()`
  and its call sites, `scope_report.compute_requirement_coverage()` /
  `_signoff_status_and_hash()`, and the `run_loop` result/status summary path [R0.5
  implementation caution — reporting/followup freshness consumers need the same
  repo-dir-aware basis].
- This is the ONE deliberate campaign-runtime-adjacent change in Phase-2 (§5.6 revised
  accordingly): additive, dormant-when-absent, precedented, and strictly tightening — it
  ALSO closes the same pre-existing hole for hand-authored campaigns that opt in by signing
  with `--repo-dir`.

---

## §4 One-sitting signing UX (two signatures, one interruption)

- **Interactive path (TTY + resolver wired, run_loop.py:476 precedent):** one invocation:
  research → gate-1 prompt (sign/reject/abort via `make_interactive_gate_resolver`) →
  two-stage decompose → backlog table → inline `campaign_plan_signoff` prompt: `sign` asks
  for the signer identity and calls `stamp_signoff(plan, charter, signer=…, ledger=…)` with
  the resolved repo dir so the §3.5 `prompt_artifacts_digest` is stamped
  (campaign.py:2927-2959), writes the SIGNED plan to `--campaign-out`, prints the run
  command (`--campaign <out> --repo-dir <repo> --resume --allow-real` [R0.3 B-1]); any
  non-sign answer ⇒ defer: rc 0 with the unsigned plan + printed
  `--sign-plan --repo-dir <repo>` command. Net: ONE sitting, TWO recorded signatures, zero
  other interruptions until the first advisory acceptance.
- **Non-interactive path:** first run halts at gate-1 (checkpoint written, rc 10). Decision
  file contract [R0 N-4][R0.2 N-1]: REUSE `campaign-decision.schema.json` verbatim with a
  NARROW bootstrap resolver (new `make_bootstrap_decision_resolver`, adapted from
  run_loop.py:509-652): binds `campaign_id` = the DERIVED campaign id (known from
  `--campaign-id`/slug at entry — the identity anchor exists before the campaign does),
  `pause_reason` = `customer_gate1_signoff`, `checkpoint` = the live gate-1 checkpoint
  basename (exact), and **`choice` ∈ {sign, reject, abort}** (REQUIRED by the schema for
  every non-`acceptance_fix_required` gate, campaign-decision.schema.json:83-92, and mapped
  1:1 onto the gate-1 resolver options); `milestone_id`/`subsprint_id` are ABSENT (no unit
  exists — the schema permits omission; the bootstrap resolver additionally REFUSES a
  decision that supplies them). Fail-closed: any mismatch ⇒ resolver returns None ⇒ re-halt.
  Re-run `--resume` → decompose → plan emitted rc 0 → `--sign-plan` (existing flow). Two
  async decisions, same two signatures.
- **Optional `--start` (interactive only):** after an inline sign, continue in-process into
  the campaign entry (all real-run preflights exactly as `--campaign` today,
  run_loop.py:734-753), passing the resolved repo dir through [R0.3 B-1]. Default OFF.
- **Exit codes** (campaign vocabulary, run_loop.py:69-77): 0 = plan emitted (signed or not);
  2 = invalid inputs (bad requirement path, missing `--repo-dir` [R0.3 B-1],
  missing/unsigned intent_contract [R0.2 B-1], charter schema errors under `--allow-real`,
  present-but-broken ledger); 10 = halted awaiting a human (gate-1, `scope_envelope_unset`,
  `post_gate1_scope_expansion`, `campaign_decompose_refusal` [R0.3 N-1], decompose
  `gate_hard_fail`); 1 = unexpected error. **The bootstrap entry explicitly catches
  `GateHardFail` (driver.py:2748-2751) and maps it to rc 10 with the checkpoint path
  printed** [R0 N-3].

---

## §5 What does NOT change (authority invariants — checkable at review)

1. `customer_gate1_signoff`: same checkpoint kind, same resolver contract, same no-auto-sign
   code path (driver.py:2418-2431 reused, not copied). The envelope snapshot [R0 B-2] adds
   drift-DETECTION that forces a FRESH human signature — strictly tighter, never looser.
2. `campaign_plan_signoff` [wording revised per R0.4 N-1]: the human signoff AUTHORITY and
   the Δ-19 F1 `signed_scope_hash` H recipe are unchanged; §3.5 adds a dormant OPTIONAL
   digest extension to `stamp_signoff`/`signoff_status` (absent ⇒ byte-identical legacy
   behavior); nothing signs a plan except a human-supplied signer through the existing
   function.
3. `intent_contract` authority [R0.2 B-1]: the engine NEVER writes, edits, or derives it —
   the entry merely REFUSES to start without the same signed contract the acceptance hard
   gate (driver.py:4814-4851) already demands. Constitution §3.4 invariant #4 intact.
4. The 9 MANDATORY_CHECKPOINTS, acceptance authority (§1.7-C), OW-M3 mandate, signed-scope
   freshness (F1/T2-A), strict-prompt regime, `acceptance_input_hash` inputs: untouched.
5. Existing entries (`--charter` single-loop, `--loop-mode full_chain_guided`, `--campaign`,
   `--quickfix`) byte-identical; the single-tier empty-envelope permissive path stays as-is;
   the single-tier research prompt and the `brief_signed` proxy-skip behavior stay as-is
   (the decoupling in §2 step 0b exists ONLY in `campaign_bootstrap` mode);
   `scope_envelope_unset`'s escalation to a blocking checkpoint exists ONLY in the bootstrap
   states (the classification entry in campaign.py [R0 B-5] is inert for existing flows).
6. Campaign RUNTIME [claim revised per R0.3 B-2]: the unit execution path is untouched (the
   emitted plan + compact files + signed charter intent_contract use only existing,
   Phase-1-proven consumption paths). The ONE runtime-adjacent change is the §3.5
   `prompt_artifacts_digest` verification inside `stamp_signoff`/`signoff_status` — additive,
   DORMANT when the field is absent (all legacy/hand-authored plans byte-identical), and
   strictly tightening when present (post-sign prompt edits ⇒ `stale` ⇒ human re-sign),
   following the shipped `milestone_signals_digest` pattern (§1.15).
7. New authority created: NONE. The chain automates preparation BETWEEN signatures, never a
   signature.

---

## §6 Implementation plan (phased commits, each behind a Codex impl gate)

- **Commit A — schema + projection + state (driver tier):**
  `campaign-decompose-verdict.schema.json`; `_project_campaign_decompose_prompt` + Stage-2
  prompt adaptation + bootstrap research block [R0.2 B-2]; `STATE_CAMPAIGN_DECOMPOSE_PENDING`
  + `_step_campaign_decompose` (precondition §3.1, snapshot reads, two-stage spawn with
  bounds [R0.2 B-3], validation (a)-(d)); RunState `signed_envelope` + `requirement_ref` +
  `loop_mode="campaign_bootstrap"` round-trip [R0 B-2]; gate-1 sign-time snapshot + drift
  re-entry; decoupled skip rule in bootstrap mode [R0.2 B-1]; `scope_envelope_unset` +
  `campaign_decompose_refusal` taxonomy entries in campaign.py [R0 B-5][R0.3 N-1]; golden
  fixture additions; unit tests (mock
  adapters) mirroring TestFullChainGuided: happy path (research grounded in requirement),
  precondition-0a refusal, precondition-0b halt + charter-fix resume, decoupled-skip (signed
  intent contract does NOT skip research in bootstrap mode; single-tier proxy skip
  unchanged), envelope-drift ⇒ fresh gate-1, envelope-expansion halt (incl. Stage-2-only
  expansion), Stage-2 bounds breach ⇒ hard fail, no-ledger coverage-claim refusal,
  cross-milestone sid collision halt, schema-invalid ⇒ GateHardFail, resume idempotency at
  the new state, RunState round-trip.
- **Commit B — run_loop entry + plan emission:** `--requirement/--campaign-out/--campaign-id`
  argparse + dispatch; intent-contract preflight 0a [R0.2 B-1] + repo-dir preflight 0c
  [R0.3 B-1]; requirement snapshot + sha256 audit [R0 B-3]; projection (e) + early
  sign-stack validation (f) + compact materialization under the resolved repo dir (g) +
  sidecar (h); backlog table + handoff print (all commands carry `--repo-dir`); exit-code
  wiring incl. `GateHardFail` → rc 10 [R0 N-3]; `make_bootstrap_decision_resolver` with the
  `choice` contract [R0 N-4][R0.2 N-1]; tests: end-to-end mock chain requirement→plan,
  emitted plan passes `--sign-plan` + `signoff_status()=='signed'` round-trip, **emitted
  plan runs under the MOCK campaign runner to the first advisory pause with ZERO
  `milestone_decompose_required` / `acceptance_spec_refinement` / `dev_spec_refinement`
  pauses** [R0 B-1 + R0.2 B-1 regression], OW-AUTO browser_e2e forcing + OW-M3 refusal,
  ledger absent-with-claims refusal vs absent-dormant vs present-broken rc 2,
  compact-collision halt (pre-existing file AND cross-milestone sid), missing `--repo-dir`
  rc 2, decision-file identity binding (wrong campaign_id/checkpoint/extra unit fields
  refused; missing `choice` schema-refused).
- **Commit B′ — prompt-artifact signature binding [R0.3 B-2]:** `prompt_artifacts_digest`
  schema field (signoff block + scope_envelope copy); `stamp_signoff` computation (optional
  repo-dir-derived artifact map); `signoff_status` optional `repo_dir` param + fail-closed
  verification (mismatch / bound-file-missing / repo-unresolvable-with-digest ⇒ `stale`);
  freshness call-site threading (campaign ingress + resume re-sign block); TD6
  engine-restamp carry-forward [R0.4 B-1]: `compute_scope_envelope()`/restamp path preserves
  both digest copies verbatim + `repo_dir` threaded through
  `apply_engine_restamp_to_plan()`; tests: digest stamped for bootstrap plans, post-sign
  compact edit ⇒ `stale` ⇒ re-sign clears, digest absent ⇒ byte-identical legacy
  `signoff_status` behavior across the existing suite, bound-file deletion ⇒ `stale`,
  hand-authored plan signed with `--repo-dir` + compact files gains the same protection,
  **restamp tests: legitimate `deliver_followup` restamp preserves both digest copies and
  the plan stays `signed` (unchanged prompts); an edited prompt is `stale` before AND after
  a restamp attempt; freshness-verification-precedes-restamp ordering asserted**.
- **Commit C — one-sitting interactive UX:** TTY sequencing incl. inline sign + optional
  `--start`; non-TTY unaffected; tests with scripted resolver.
- **Commit D — env-gated REAL canary + evidence:** `examples/real-requirement-canary/`
  (requirement file + charter with signed `intent_contract` [R0.2 B-1] + non-empty envelope,
  all roles claude_code, 2 tiny objectively-checkable milestones — Phase-1 canary content
  style); NEW env gate `AIDAZI_E2E_REAL_REQUIREMENT=1` (child-env only, standing rule); flow
  asserted on invariants only: rc 10 at gate-1 → decision sign → `--resume` rc 0 plan
  emitted (compact files present, plan signs clean) → `--sign-plan` rc 0 →
  `--campaign --allow-real --resume` reaches the FIRST `advisory_acceptance_pass_signoff`
  pause rc 10 with NO earlier pause (proves "requirement → campaign RUNNING") → drive to
  done via the Phase-1-proven decision flow. Evidence doc in archive/ (ledger style of
  2026-07-09). 
- Gates: R1 after A, R2 after B+B′(+C), R3 whole-scope after D; suite + kernel/load-closure/
  doc-reconciliation green at every commit; review_runner.py + codex xhigh, background.

## §7 Risks / edge cases

- **Golden-fixture churn**: new prompt entries only; existing hashes asserted byte-identical.
- **`covers_req_ids` hallucination**: §3.3(c) rejects claims with no/unknown ledger backing;
  OW-M3 catches surface downgrades [R0 B-4].
- **Requirement-file drift between halt and resume**: the run-dir snapshot is canonical; on
  `--resume` a changed source file ⇒ audit WARN `requirement_source_drift` (snapshot
  governs); re-running WITHOUT `--resume` re-snapshots.
- **Charter envelope drift after gate-1**: detected on every `campaign_decompose_pending`
  entry via the snapshot ⇒ fresh gate-1 [R0 B-2]. Non-envelope charter edits are covered by
  the existing charter_hash staleness at plan-sign time (G1). Intent-contract edits after
  entry: covered by the same G1 charter_hash staleness at sign time; after signing, units
  read the charter the campaign derivation snapshots — unchanged from today.
- **Empty backlog / runaway output**: Stage-1 schema minItems 1 / maxItems 12; Stage-2 code
  bounds ≤ 8 per milestone, ≤ 60 total [R0.2 B-3].
- **Compact-file collisions**: pre-existing adopter file ⇒ HALT, never overwrite (§3.3-g);
  cross-milestone duplicate sids ⇒ HALT before any write [R0.2 N-2].
- **Post-signature compact-prompt edit**: flips `signoff_status` to `stale` via the §3.5
  digest ⇒ campaign refuses to proceed until a human re-signs over the changed prompts
  [R0.3 B-2]. Digest-less legacy plans keep today's (unprotected) behavior unchanged.
- **Campaign run started without `--repo-dir`** on a digest-carrying plan: `signoff_status`
  cannot verify ⇒ `stale` (fail-closed, actionable message says pass `--repo-dir`); on
  digest-less plans, unchanged legacy behavior [R0.3 B-1/B-2 interaction].
- **Charter pins a confirmed intent contract**: does NOT skip research/gate-1 in bootstrap
  mode (§2 step 0b) — and cannot, or no brief would exist [R0.2 B-1].
- **No envelope**: entry preflight 0b halts `scope_envelope_unset` regardless of how the
  brief/intent got signed. In the (single-tier) pinned-brief path nothing changes.
- **Two live resolvers** (TTY + `--decision`): decision file wins, TTY fallback — campaign
  precedent; test-covered.

## §8 Acceptance criteria (nothing claimed done without evidence)

Suite green (~1900); kernel 70/70 + load-closure closed + doc-reconciliation
untouched-green; golden fixture: existing hashes byte-identical, new entries rationale'd;
Codex impl gates R1/R2/R3 APPROVE; the B-1/R0.2-B-1 regression test (mock campaign of an
emitted plan reaches advisory with zero decompose/refinement pauses) green; ONE real canary
evidence doc showing requirement-file → signed plan → running campaign → delivered, with
≤1 human sitting before the first milestone starts (interactive path) and the exact rc/pause
ledger recorded. Only then does roadmap §3 count as implemented.
