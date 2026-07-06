---
title: "Universal deterministic skill mounting + consumption observability + bounded efficacy canary — design & pre-registration"
doc_tier: archive
doc_category: design
status: approved-pending-human-signoff
date: 2026-07-06
authored_by: maintainer (aidazi framework repo)
scope: Phase-0 design contract — design-only; implementation begins at Phase 1 after human sign-off
gate_history: >
  Human plan review (7 blocking corrections, 2026-07-06) → Codex gpt-5.5 xhigh design gate
  R1 REVISE (6 blocking, all verified+fixed) → R2 REVISE (3 blocking, all verified+fixed) →
  R3 APPROVE (0 blocking; NB1/NB2 folded in as test items) → human execution approval with
  4 implementation guardrails (§8) → THIS committed Phase-0 contract (subject to its own gate).
branch: feat/universal-skill-mounting (base origin/main @ 9f392e4)
related:
  - archive/2026-07-06-skill-integration-investigation.md   # motivating investigation (on branch docs/skill-integration-investigation, unmerged)
  - process/role-skill-model.md
  - engine-kit/effective_role_config.py
  - engine-kit/orchestrator/driver.py
  - engine-kit/orchestrator/campaign.py
  - skills/registry.yaml
---

# Universal deterministic skill mounting + consumption observability + bounded efficacy canary

**Revision-4 design (final), committed as the Phase-0 contract.** Any later change to §7
(pre-registration) returns the initiative to Phase 0 and requires a new Codex design gate.

## §0 Goal & claim discipline

When aidazi is vendored/submoduled into an adopter, **every eligible non-Acceptance role —
including Research and Deliver — across all loop modes** dynamically and automatically mounts
appropriate skills from the framework-shipped catalog (never network-fetched), with
**consumption observability** and a **bounded, pre-registered efficacy canary**.

- The Phase-5 canary establishes evidence **for the pre-registered fixture only** (one skill,
  one harness, one model, one task). It must NOT be claimed as universal per-skill / per-role /
  cross-adopter effectiveness. General efficacy = M-Skill-3 follow-up.
- **Byte-stability claim scope:** all "byte-identical for signal-free adopters" guarantees cover
  dispatched prompts, input hashes, `signed_scope_hash`, and signoff authenticity — NOT
  audit-ledger payload bytes (new nullable audit fields are additive + forward-only, per the
  `load_graph_hash` precedent).

**Motivation (verified 2026-07-06):** the deterministic pipeline exists through state 3
(injected) — `effective_role_config.py` resolution, `driver.py:1005` injection, `driver.py:1054`
audit, task_signals digest guard `driver.py:1174-1200,2451`, decompose authoring instruction
`driver.py:2425-2439` — but is dormant in practice and structurally dead in the primary mode:
campaign mode pins `loop_mode=delivery_only` (`make_run_unit`, campaign.py:3234; decompose never
runs), so **no spawn in campaign mode can receive task_signals today**; research and
deliver-decompose spawns are pre-plan → signal-dead in every mode. States 4 (read-observed) and
5 (output-effect) are unverified. The AirPlat adopter additionally demonstrated the
drift-failure class (investigation record §2).

**Five-state pipeline** (from the investigation record): deployed → selected → injected →
read-observed/unobservable → output-effect verified. Today's authoritative guarantee ends at
*injected*; this initiative extends coverage (all roles/modes), adds state-4 observability, and
proves states 1–5 per the §9 verification matrix (state 5 fixture-scoped only).

## §1 Locked decisions (unchanged this cycle)

Deterministic selection only · existing catalog + 6-word UI vocab (`a11y, design, frontend,
interaction, performance, ui`) · unconditional role_defaults · NO agent self-report as
consumption evidence · adapter-observed reads where available, honest `unobservable` otherwise ·
output-effect via contracts/gates + bounded pre-registered canary only · no AirPlat changes ·
no runtime network fetch · no autonomous Acceptance skill selection (§3.6 calibration —
Acceptance excluded) · explicit human approval before billable Phase 5 · no push/PR/merge/
exposure before final whole-scope approval.

## §2 D1 — Signal sources + authority/signoff model

Two signed signal sources → ONE ingestion surface (the effective charter) → most-specific-wins
at spawn:

- **(a) Mission profile:** optional `autonomy.approved_scope.task_signals` (enum =
  TASK_SIGNAL_VOCAB) in `schemas/mission-charter.schema.json` (`approved_scope` is
  `additionalProperties:false` → additive optional field). Authority: the charter is the human
  trust root; in campaigns `charter_hash` sits inside `signed_scope_H`, so a charter-profile
  change already makes the signoff stale (existing semantics). Absent ⇒ byte-identical hash ⇒
  zero churn.
- **(b) Per-milestone:** optional `milestones[].milestone_signals` in
  `schemas/campaign-plan.schema.json`.

**Authority binding for (b) — signoff-snapshot-bound, centrally enforced:**
- `stamp_signoff` (campaign.py:2873) computes `milestone_signals_digest` = sha256 over canonical
  `[(milestone_id, sorted(milestone_signals or []))]` for ALL milestones, and stores it (i) in
  the signoff block AND (ii) inside the authenticated signoff snapshot —
  `signoff_snapshot_authentic` (campaign.py:2988) is extended, versioned, to cover the digest
  for snapshots that carry it. **The digest key is entirely OMITTED when no milestone carries
  signals** — legacy and signal-free plans remain byte-identical; legacy authenticity recompute
  unchanged.
- **Central enforcement:** digest verification lives in the CENTRAL freshness path —
  `signoff_status` (campaign.py:3026) returns `'stale'` on (signals present && digest absent)
  OR (digest recompute mismatch). **`f1_required` (campaign.py:2974) is extended to ALSO trigger
  on the presence of a `milestone_signals` field in any milestone** (field-presence keyed,
  mirroring `covers_req_ids`) — closing the `Campaign._authority_fresh` (campaign.py:1039)
  short-circuit: a signal-bearing plan is always F1-active; an unsigned signal-bearing plan
  reads `'unsigned'` ⇒ blocked; a signed one always has its digest verified. Signal-free legacy
  plans: `f1_required` unchanged ⇒ byte-identical behavior. Ingress check (near campaign.py:586)
  + pre-`derive_milestone_context` checks remain as defense-in-depth. No-signals && no-digest ⇒
  legacy pass.
- **Update path:** changing signals requires editing the plan and re-running the explicit human
  signoff flow (new stamp = new digest + fresh authorization). **No `--stamp-signals`
  side-channel exists.** A signed plan is never mutated in place under an unchanged signoff.
- **Trust-model honesty:** this is process-level immutability within the existing
  non-cryptographic signoff trust model — the same residual as `signed_scope_hash` itself (a
  writer who forges a co-edit of plan + signoff block defeats both; accepted precedent, per
  `task_signals_digest`). The claim is "any mutation not accompanied by a forged signoff co-edit
  is detected and fails closed", not cryptographic immutability.

**Projection:** `derive_milestone_context` (campaign.py:3156) writes
`derived.autonomy.approved_scope.task_signals = sorted(set(charter_profile) |
set(milestone_signals))` + a provenance record (source breakdown). Runs only after
freshness/digest verification passes.

**Spawn-time resolution** (`_task_context_for`, driver.py:1202-1233), most-specific-wins:
- Plan entry exists for the current sub-sprint → its `task_signals` govern EXCLUSIVELY
  (including a signed empty omission — a coarse "ui" mission profile must not bloat a backend
  sub-sprint Deliver deliberately left unsignaled).
- No plan entry (research, deliver-decompose, ALL delivery_only spawns) → the effective
  charter's `approved_scope.task_signals` govern.
- Acceptance hard-excluded (driver.py:1219, unchanged). Cache key `(role, task_unit_id)`
  unchanged (charter signals constant per driver instance).

**Role/harness compatibility:** `charter_validator.py:1214-1353` static validation — which
already treats signal-tagged skills violating a task-selectable role's tool whitelist / harness
constraints as fail-closed errors for real runs — REMAINS THE AUTHORITY and is extended to the
new charter field (vocab subset; warn on signals matching no catalog skill). The runtime
resolve-time compatibility filter is **defense-in-depth ONLY** (catches validation-time ↔
spawn-time drift): an incompatible candidate becomes a recorded, non-silent skip (reuses
`skipped_skills` audit + footer) AND emits a WARN-level audit event, since reaching that path
indicates validator/runtime drift. No weakening of the real-run hard-fail model.

**Audit:** the `effective_role_config` event gains
`signal_source: "subsprint" | "charter_scope" | "none"` (additive).

**Decompose prompt:** optional conditional one-line block when the derived charter carries
signals ("this milestone's declared signals are [...]; author per-sub-sprint task_signals
accordingly, omitting where they don't apply") — byte-identical when absent.

## §3 D2 — Invocation-scoped consumption telemetry

**No shared mutable adapter state.** API boundary:

- `Adapter.spawn()` (base.py:77) return changes from a plain dict to a `SpawnResult` dataclass:
  `{result: dict, telemetry: InvocationTelemetry}`.
- **Adapter inventory (guardrail G2 resolution, verified):** `ADAPTER_REGISTRY`
  (engine-kit/adapters/__init__.py:18-25) is a CLOSED in-repo registry — `mock`, `claude_code`,
  `headless`, `codex`, `kimi`, `cursor`; an unknown harness id raises a typed `AdapterError`
  (":28-45"). External/custom adapter classes are NOT a supported extension point. All six
  in-repo adapters are updated in the same Phase-2 commit. **Defensive normalization shim
  regardless:** each driver call site normalizes a legacy plain-dict return into
  `SpawnResult(result=dict, telemetry=unobservable/harness_unsupported)` and emits a
  deprecation-signal audit note — no out-of-tree adapter (e.g. monkey-patched) silently breaks.
- **Call-site inventory (grep-verified — exactly two runtime sites, both updated):**
  `driver.py:1091` (`_spawn`) AND `driver.py:4842` (the Acceptance spawn — Acceptance is
  excluded from task-signal *selection*, NOT from the adapter API change; its telemetry is
  recorded identically, giving consumption observability over the calibration-coupled acceptance
  skill set). The quickfix lane does not call `Adapter.spawn` (verified). Adapter/driver tests
  updated in the same commit; the Phase-2 gate re-runs the call-site grep as a checklist item.
- `InvocationTelemetry` = `{terminal_attempt: int, terminal_status: str,
  read_paths: Optional[list[str]], observability: "observed" | "unobservable" | "parse_error"}`.
  The adapter does NOT know driver identifiers: the driver binds `spawn_ref` (its seq +
  input_hash) at audit-write time.
- **Single auditable mapping:** the spawn-audit field stays a 3-value enum
  `skill_consumption ∈ {observed, none_observed, unobservable}`, plus a MANDATORY
  machine-readable `skill_consumption_reason` whenever the value is `unobservable`, enum
  `{harness_unsupported, parse_error, adapter_error}`. Deterministic mapping from telemetry:
  `observed`→`observed`; `unobservable`→`unobservable`/`harness_unsupported`;
  `parse_error`→`unobservable`/`parse_error` (never silently `none_observed`); `none_observed`
  is emitted ONLY when a successfully parsed stream contains zero matching reads. Schema + one
  test per mapping row, explicitly including the observed-stream-with-zero-matching-reads case
  (the only valid source of `none_observed`).
- Attempt metadata: `run_with_monitor` (monitor.py:39) is extended ADDITIVELY to return the
  terminal attempt index and the terminal attempt's captured stdout alongside its existing
  return (exact shape refined in Phase 2 with tests); the claude_code adapter parses reads
  post-hoc from that terminal-attempt capture (parse per the proven
  archive/wp3-canary-harness/read_trace_canary.py:84-105 logic) — a local value, never instance
  state.
- **`AdapterError` path:** no envelope returns; the driver's failure-path audit records
  `skill_reads=null`, `skill_consumption="unobservable"`,
  `skill_consumption_reason="adapter_error"` — never `none_observed`.
- Base default (codex/mock/cursor/headless/kimi): `read_paths=None`,
  `observability="unobservable"`. **No heuristic codex exec-grep** (false positives would poison
  the evidence standard).
- Driver `_spawn` intersects `read_paths` (realpath-normalized; suffix fallback
  `<skill_id>/SKILL.md` recorded as `match_kind`) with resolved effective-skill SKILL.md paths →
  nullable spawn-audit fields; `skill_consumption` mandatory whenever effective skills are
  non-empty.
- Raw stream persisted only under opt-in `AIDAZI_KEEP_RAW_STREAM=1` (default off — size/secrets).

**Non-contamination proof obligations (tests shipped with Phase 2):** retries → telemetry binds
to the terminal attempt only (index recorded; earlier attempts' streams not merged); sequential
adapter reuse → distinct envelopes, no read-holding instance attribute exists; concurrency →
per-unit driver+adapter instances + return-value channel make cross-contamination impossible by
construction (interleaved-invocation test); crash-resume → spawn audit events are emitted once
and replayed from the ledger, never re-derived (ledger-equality-across-resume test).

## §4 D3 — Integrity/drift preflight severity

**Hash basis (verified):** the lock's algorithm is `skill_vendor.tree_sha256`
(engine-kit/skill-vendor/skill_vendor.py:130 — sha256 over a shasum-style per-file manifest,
`_provenance.yaml` excluded), NOT `effective_role_config._tree_hash`. **A complete offline
verifier already exists: `skill_vendor.py verify` (:295, CLI :439).** Phase 3 REUSES
`skill_vendor.verify()` — no new hashing code — adding the severity policy + submodule-drift
check + run_loop wiring.

| # | Condition | Severity |
|---|---|---|
| 1 | `skills.lock` vs vendored tree mismatch (`skill_vendor.verify()` fails) | **HARD FAIL** (real runs) |
| 2 | Required registry skill (role default / charter-bound) missing or unresolvable | **HARD FAIL** (preflight surfaces early; resolve-time fail-closed remains) |
| 3 | Real-loop submodule working-tree commit ≠ recorded superproject gitlink | **HALT / fail closed**, unless an explicit audited override flag is set (recorded as an audit event carrying both commits) — the AirPlat class is never warning-only in a formal run |
| 4 | Adopter pin behind upstream / newer upstream skills available | **advisory WARN only** |
| 5 | Read telemetry unavailable for the harness | **informational `unobservable`** — never a human manual-check requirement |

New `engine-kit/validators/skills_preflight.py` wired into both run_loop preflight homes
(campaign `run_campaign_entry` run_loop.py:679-689; single-loop :1186-1197/:926-928; pattern
`enforce_required_capabilities_for_real_run`) + standalone CLI.

## §5 Sequential phase plan (strictly sequential, single branch)

Branch `feat/universal-skill-mounting`, base `origin/main` @ `9f392e4`. **Each phase requires
Codex gpt-5.5 xhigh APPROVE (bounded `engine-kit/tools/review_runner.py`) before the next
begins.** Full suite + kernel/load-closure/WP-9 gates green per phase; `test_e2e_acceptance.py`
run per phase. Manual edit approval throughout; no permission bypass.

| Phase | Content | Effort |
|---|---|---|
| **0** | THIS design contract + frozen §7 pre-registration → Codex P0 gate → human sign-off | S/M |
| **1** | Signal sources + authority (§2), all eligible roles/modes: mission-charter schema (+compact regen via `project_schema.py`, x-canonical-sha256 lockstep), campaign-plan schema (`milestone_signals` + signoff digest), `stamp_signoff` digest + snapshot binding, `signoff_status`/`signoff_snapshot_authentic` versioned extension + `f1_required` milestone_signals trigger, ingress + per-derivation defense-in-depth, `derive_milestone_context` projection + provenance, `_task_context_for` most-specific-wins, runtime compat defense-in-depth skips, charter_validator extension, `signal_source` audit. Tests in same commits: 5-schema enum drift-guard, most-specific-wins matrix, byte-identical negative arm (signal-free ⇒ prompts/hashes byte-identical to pre-change golden), digest tamper/absence/legacy arms incl. the strip-both regression (removing `milestone_signals` AND the digest after signoff ⇒ still `'stale'` via the authenticated snapshot binding), `signoff_status` staleness matrix, H-stability + snapshot-authenticity regression (incl. T2-B legacy branch). MUST NOT alter `_signed_scope_H`/`_envelope_milestone` computation for existing plans. | L |
| **2** | Invocation-scoped consumption observability (§3): `SpawnResult` envelope across all six adapters + both runtime call sites (driver.py:1091 `_spawn` AND :4842 Acceptance) + legacy-dict normalization shim w/ deprecation signal, `run_with_monitor` additive attempt metadata, claude_code post-hoc parse, driver audit fields (`skill_consumption` + mandatory `skill_consumption_reason` mapping incl. the zero-matching-reads `none_observed` case) + AdapterError path, full non-contamination test suite (retry/sequential/concurrency/resume), codex `unobservable`, call-site grep as gate checklist item | M |
| **3** | Integrity/drift preflight (§4): `skills_preflight.py` REUSING `skill_vendor.verify()` + submodule-drift check + audited override + run_loop wiring + CLI + severity tests | S/M |
| **4b** | Vendored scratch-adopter offline proof — TWO fixtures: (i) `full_chain_guided` single-loop fixture exercising Research + Deliver-decompose spawns with a charter mission profile (proves pre-plan spawns select/inject); (ii) campaign `delivery_only` fixture exercising signoff-bound `milestone_signals` → derived-charter union → delivery-only dev/review/close spawns. Both run through a REAL `vendor-framework.sh` temp adopter + MockAdapter loop; assert states 1-3 byte-level in the VENDORED tree (preflight pass; audit `selected_skills` + `signal_source`; prompt transcripts contain the block; `skill_consumption=unobservable` for mock). Negative arms: no signals ⇒ byte-identical (prompts/hashes); out-of-vocab ⇒ schema-invalid; tampered lock ⇒ hard fail; gitlink drift ⇒ HALT + audited override path; post-sign signal mutation ⇒ `signoff_status='stale'` fail | M |
| **5** | **Separately human-authorized** real/billable canary per frozen §7 | M + billable |
| **6** | Docs + closure — full lockstep set: `process/role-skill-model.md` edits require (a) `_sources.yaml` sha256 refresh, (b) `kernel_equivalence.py --kernel-coverage`, (c) acceptance load-closure re-run (`acceptance_load_closure.py` — role-skill-model.md is in its RETIRED_FILES/inlined surface, :56) with `closed:true`, (d) `--acceptance-kernel-coverage` re-verification; prefer confining edits to sections NOT inlined into the acceptance kernel, verified by the coverage harness; preserve REQUIRED_ANCHORS §4 #1-#5/§6. Plus ONBOARDING framework-version floor note, completion record, final whole-scope Codex gate. No push/PR/merge/exposure before final whole-scope approval + human authorization. | S/M |

## §6 Never-touch list (acceptance LOAD-CLOSURE + gated)

`governance/constitution-core.md` | `governance/constitution.md` |
`governance/authoring-kernel.md` | `governance/doc_governance.md` |
`governance/context_briefing.md` | `role-cards/acceptance-agent.md` (avoid all role cards) |
`templates/compact-acceptance-prompt.md` | framework `AGENTS.md` |
`schemas/acceptance-verdict*`. `process/role-skill-model.md` is editable ONLY under the Phase-6
lockstep set.

## §7 Phase-5 pre-registration (FROZEN — changes return to Phase 0 + new design gate)

### §7.0 Common frozen configuration
- **Env gates (corrected per guardrail G3):** the canary harness is gated by a NEW dedicated
  `AIDAZI_SKILL_CANARY=1`; real coding-agent subprocesses additionally require
  `AIDAZI_ALLOW_REAL_ADAPTER=1` (the adapters' own gate, engine-kit/adapters/headless.py:37);
  `AIDAZI_KEEP_RAW_STREAM=1` is set ONLY for these authorized canary runs (evidence capture).
  `AIDAZI_E2E_EXTERNAL_RUNNER` is NOT used — no external test runner is exercised by this canary.
- **Harness/model (identical across ALL probes and arms):** claude_code adapter; model
  `claude-sonnet-4-6`; adapter-default permission mode and dev-role tool whitelist; monitor
  defaults with a 15-minute wall-clock cap per spawn; one workspace-per-spawn scratch adopter
  (fresh `vendor-framework.sh` copy per repetition; no state reuse across repetitions).
- **Budgets:** total ≤ 15 real spawns (α:6, β:3, γ:6) + ≤ 2 replacement spawns per probe for
  adapter-level errors (AdapterError/timeout only — NEVER for unwanted verdicts). >2 adapter
  errors in one probe ⇒ probe INCONCLUSIVE ⇒ HALT and surface.
- **Evidence:** raw stream-json per spawn, audit ledgers, prompt/output transcripts, scorer
  outputs — archived under `archive/wp-skill-canary/` (WP-2/WP-3 style).
- **Scorer:** a deterministic Python scorer implementing EXACTLY the §7.3 checklist; committed
  with the harness in Phase 5; the Phase-5 gate verifies scorer ≡ §7.3 (any divergence = gate
  fail). No LLM judging anywhere in scoring.

### §7.1 Probe-α — authoring correctness (state-2 authoring half)
- **Fixtures (2):** (i) UI milestone — brief "add a user-facing settings page with accessible
  profile + notification forms" decomposing naturally into 3 sub-sprints, of which 2 are
  pre-designated UI (settings form UI; notification preferences UI) and 1 pre-designated non-UI
  (persistence API endpoint); (ii) non-UI milestone — brief "add a CSV export command-line tool
  with unit tests", 3 sub-sprints, all pre-designated non-UI. Fixture briefs are written and
  committed BEFORE any run.
- **Procedure:** 3 repetitions per fixture (6 decompose spawns) of the real decompose contract
  (`_step_decompose` prompt, driver.py:2425-2439) against the fixture brief.
- **Per-repetition PASS:** fixture (i): every pre-designated UI sub-sprint carries ≥1 correct
  in-vocab signal AND every pre-designated non-UI sub-sprint carries zero signals AND the plan
  validates against deliver-plan-verdict (any out-of-vocab signal ⇒ schema-invalid ⇒ rep FAIL).
  Fixture (ii): zero signals on every sub-sprint.
- **Probe PASS:** ≥2/3 repetitions pass for EACH fixture independently.

### §7.2 Probe-β — consumption (state 4)
- **Fixture:** one dev sub-sprint task carrying signed `task_signals: ["frontend"]` (mounting
  `web-interface-guidelines`) in a scratch adopter; the §7.3 fixture task prompt.
- **Procedure:** 3 repetitions (3 real Dev spawns).
- **Per-repetition PASS:** the spawn's stream-json contains ≥1 `Read` tool_use whose
  realpath equals the mounted `web-interface-guidelines/SKILL.md` AND the spawn audit records
  `skill_consumption=observed`.
- **Probe PASS:** ≥2/3 repetitions pass.

### §7.3 Probe-γ — bounded output-effect (state 5, fixture-scoped)
- **Fixture task (identical byte-for-byte across arms except the signal difference):**
  "Implement a self-contained sign-up page (plain HTML + CSS + vanilla JS, single directory, no
  framework, no build step): email + password fields, a submit button that simulates an async
  request and shows a status message, an icon-only password-visibility toggle button, a
  decorative logo image, and a short features section with headings."
  Arm A: sub-sprint carries `task_signals: ["frontend"]` (mounts web-interface-guidelines).
  Arm B: no task_signals (role default TDD skill only). Everything else identical (§7.0).
- **Paired repetitions with counterbalanced ordering (guardrail G4):** 3 pairs; execution order
  pair 1 = A→B, pair 2 = B→A, pair 3 = A→B. Fresh scratch adopter per arm-run.
- **Deterministic checklist (M = 10; each check is binary per arm, evaluated over the produced
  artifact files by the frozen scorer):**
  1. Every `<img>` has explicit `width` and `height` attributes.
  2. The icon-only toggle `<button>` has a non-empty `aria-label`.
  3. Every form input has an associated `<label for=…>` (or `aria-label`) AND an `autocomplete`
     attribute.
  4. At least one `:focus-visible` (or `focus-visible:`) style exists AND no `outline: none` /
     `outline-none` appears without an accompanying `:focus-visible` replacement.
  5. If any CSS `transition`/`animation` is declared: a `prefers-reduced-motion` media query is
     present AND no `transition: all` appears. (Vacuously true if no animation is declared.)
  6. No `<div onclick` / `<span onclick` (or JSX equivalent) click-handler interaction; actions
     use `<button>`, navigation uses `<a>`.
  7. The async status region carries `aria-live="polite"`.
  8. Loading/progress strings use the `…` character, not `...`.
  9. `touch-action: manipulation` is present (on interactive controls or globally).
  10. Exactly one `<h1>` and no skipped heading levels in the produced markup.
- **Per-pair success:** arm A's stream shows a Read of the mounted SKILL.md (as §7.2) AND
  `score_A ≥ score_B + 2` (scores = count of passed checks, 0–10).
- **Probe PASS:** ≥2/3 pairs succeed. A single pair is NEVER sufficient.
- **Claim on PASS:** "for this fixture, skill mounting produced a measurable artifact-quality
  effect" — nothing broader.

### §7.4 Abort criteria (all probes)
- Any probe below its PASS threshold after its repetition budget ⇒ the initiative HALTS at
  Phase 5 with an honest negative completion record. No post-hoc criteria adjustment.
- >2 adapter-level errors in one probe ⇒ INCONCLUSIVE ⇒ HALT and surface (never silently
  extended).
- ANY change to §7 (fixtures, reps, ordering, model/config, checklist, thresholds, abort rules)
  ⇒ return to Phase 0 ⇒ new Codex design gate ⇒ new human sign-off.

## §8 Implementation guardrails (human execution approval, 2026-07-06)

1. Phase 0 commits the exact approved design and freezes the complete §7 pre-registration before
   any implementation or canary; later criteria changes return to Phase 0 + new design gate.
2. Before changing `Adapter.spawn()`: full adapter-implementation inventory (done — §3: closed
   in-repo registry, six adapters) + defensive legacy-dict normalization producing
   `unobservable` telemetry + a deprecation signal; no silent breakage.
3. Correct real-run gates: `AIDAZI_ALLOW_REAL_ADAPTER=1` for real coding-agent subprocesses;
   `AIDAZI_E2E_EXTERNAL_RUNNER=1` only where the external runner is actually exercised (NOT this
   canary); `AIDAZI_KEEP_RAW_STREAM=1` only for authorized canary evidence capture.
4. The fixture-scoped A/B canary uses pre-registered paired repetitions, counterbalanced
   ordering, identical model settings and budgets, and a deterministic scorer; a single A/B pair
   is not sufficient to claim even bounded efficacy.

Standing boundaries: strict phase-by-phase Codex APPROVE; no AirPlat/adopter changes; no network
skill fetching; no Acceptance dynamic skill selection; no Phase-5 billable run without separate
human approval; no push/PR/merge/exposure before final whole-scope approval; manual edit
approval, no permission bypass.

## §9 Verification matrix

| State | Proven by | Artifact | Mode |
|---|---|---|---|
| 1 deployed | P3 (+P4b post-vendor) | `skill_vendor.verify()` vs skills.lock | offline |
| 2 selected | P1/P4b (+P5-α authoring half) | `effective_role_config` audit (selected_skills, signal_source) on research/deliver-decompose (guided fixture) + delivery_only spawns (campaign fixture) | offline |
| 3 injected | P1/P4b | prompt transcript contains the skill block; input_hash covers it; negative arm byte-identical | offline |
| 4 read-observed | P2 mechanism + P5-β proof | invocation telemetry → `skill_reads`/`skill_consumption` audit; raw stream archived | real |
| 5 output-effect (fixture-scoped ONLY) | P5-γ | pre-registered paired A/B, deterministic scorer | real (billable) |

## §10 Out of scope (recorded follow-ups)

Vocabulary/catalog expansion beyond UI; conditional role_defaults (M-Skill-2); general efficacy +
adaptive runtime selection (M-Skill-3, deferred pending §7 data); AirPlat pin migration (separate
adopter-migration item); codex read-telemetry.

---

*End of Phase-0 design contract.*
