---
name: 2026-07-09-autonomy-roadmap-campaign-unblock
doc_category: intermediate
status: codex-approved (design settled; Phase-1 implementation in flight on this branch)
created: 2026-07-09
base_commit: aa934ca (origin/main HEAD = PR #11 merge, universal-skill-mounting landed)
reviewer: >
  codex gpt-5.5 xhigh — R0 REVISE (4 blocking + 1 factual + 1 nit) → all folded in (tagged
  `R0 B-#/F-#/N-#`) → R0.2 REVISE (1 blocking on the §6 cursor-wiring claim; B-1..B-4/F-5
  confirmed sound) → §6 fix (honest warn-only status + Phase-5 upgrades the wiring validator
  to FAIL on missing .cursor/rules) → R0.3 APPROVE (0 findings, 2026-07-09)
user_decisions_locked_2026-07-08:
  - this round = roadmap doc + Phase-1 implementation (adapter fixes + early validation + real campaign canary)
  - adapter strategy = fix cursor AND kimi (all 5 delivery-loop adapters usable)
  - gate policy = WITHIN the constitution (no amendment; tighten-only pre-set halt conditions)
  - parallel runner = DESIGN this round, implement a later round
  - all real-CLI activity (stream captures, campaign canary) MUST be env-gated
---

# Autonomy Roadmap — unblock the Campaign Loop, then raise the autonomy ceiling

**Goal (user's words, distilled):** submit a requirement and have the framework drive it all
the way to delivery, interrupting the human ONLY at (a) the constitutionally mandatory
signatures and (b) blocking conditions the human pre-set — while preserving the entire
governance chain, and eventually running multiple milestones in parallel for throughput.

**Why now:** the automated orchestrator has NEVER driven a real-adapter campaign end-to-end.
Every recent adopter milestone (airplat M3, M-pool, M-auth, M-match3, RB-021) was hand-driven
via Control-Plane direct-drive because adapter spawns broke. The governance discipline
survived; the autonomy did not. This document fixes the blockers (Phase-1, implemented with
this doc) and lays out the ladder to the target state (Phases 2–5).

---

## §1 Current state (verified 2026-07-08/09, all file:line refs at base `aa934ca`)

### §1.1 The autonomy model is a 2-D matrix, not a 3-tier ladder

**Execution modes (4 + 1 degraded):**

| Mode | Entry | Covers | Status |
|---|---|---|---|
| Quick-Fix lane | `--quickfix <request.json>` (human-explicit) | non-behavioral fixes outside the loop | supported: claude_code, codex |
| `delivery_only` (default) | `run_loop.py --charter` | ONE sub-sprint chain Dev→Review→Close→Acceptance | canonical driver |
| `full_chain_guided` | `--loop-mode full_chain_guided` | prepends research→gate1→decompose, then delivery | implemented (P6.1) |
| Campaign | `--campaign plan.json [--resume --decision d.json]` | whole milestone backlog, multi-milestone | implemented, sequential-only |
| Control-Plane direct-drive | human/agent plays each role gate by hand | anything | the degraded fallback everyone actually used |

**Autonomy levels (charter `autonomy.level`, orthogonal to mode):**
`human_in_the_loop` (every gate blocks) → `human_on_the_loop` (clean-pass auto-advance +
bounded auto-fix iteration via `auto_pass_rules`) → `fully_autonomous_within_budget`
(acceptance `mode:auto` + calibrated judge ⇒ authoritative auto-ship).

### §1.2 Human-gate taxonomy

- **Routinely blocking on the happy path (3):** `customer_gate1_signoff` (research brief),
  `campaign_plan_signoff` (backlog, Δ-19 F1 signed_scope_hash), and per-milestone
  `advisory_acceptance_pass_signoff` (until the judge is calibrated + `mode:auto`).
- **Event-triggered only (fire on anomaly, silent otherwise):** `scope_deviation`,
  `gate_hard_fail`, `close_taxonomy_C_or_D`, `post_gate1_scope_expansion`,
  `bad_case_manual_review`, `new_tier0_candidate`, `forbidden_list_redline`,
  `campaign_budget_exhausted`, `completeness_gap_review` (§1.7-F; auto-dispatches at
  human_on_the_loop+), `milestone_merge` (only with milestone_isolation).
- **Constitutional floor:** the 9 MANDATORY_CHECKPOINTS (Constitution §1.7-D) always exist;
  `charter_validator` rejects all four bypass shapes. `tooling.acceptance.on_fix_required.
  human_confirm_required` is `const: true`. Nothing in this roadmap touches that floor.

**Corollary that shapes everything below:** on a clean run, the ONLY mandatory interruptions
are the 3 signatures. The autonomy gap is not "too many gates" — it is (a) spawns break
(§1.3), (b) the chain from *requirement* to *signed backlog* is manual (§3), (c) there is no
way to declare *additional* personal halt conditions (§4), and (d) throughput is serial (§5).

### §1.3 Campaign blockers — root causes (all confirmed with evidence)

1. **cursor adapter, model routing** — `engine-kit/adapters/cursor.py:136-137` passes charter
   `model` verbatim as `--model`. Root cause upstream: the SHIPPED registry profile
   `cursor-agent-dev` (`engine-kit/validators/data/model-registry.yaml:99-110`) carries the
   placeholder `model: cursor-agent`; adopters copy it; the CLI rejects it. Real failure:
   airplat 2026-07-07, loop `u0df71243377a8488b29bc049`, "Cannot use this model: cursor-agent.
   Available models: auto, gpt-5.3-codex-low, …" — `auto` IS the CLI's account-default id.
2. **cursor adapter, liveness** — `cursor.py:195-204` calls `run_with_monitor` with NO
   `liveness_probe_factory`; with `-p --output-format json` the session is one silent
   end-envelope ⇒ the monitor's ~180s silence-kill (monitor.py:204-211) fires on any long turn.
3. **kimi adapter, liveness** — `kimi.py:131-140`, same omission. Also prompt via argv
   `--prompt=` (kimi.py:85) against the "prompts via stdin" hardening principle.
4. **Validation is too late** — `charter_validator.py:1067-1073` treats unknown model ids as
   WARN-only, so `model: cursor-agent` sails through preflight and detonates at the first real
   spawn deep inside a campaign.
5. **Zero end-to-end proof** — no real-adapter campaign has ever completed sign→run→pause→
   decision→resume→done. Only mock dry-runs (test_run_loop_campaign.py) and single-role real
   E2E (watchdog canary 2026-07-03; native-E2E canary Phase-5).

**Not blockers anymore:** claude_code (ToolLeaseProbe, claude_code.py:46-101, wired :248),
codex (CodexStreamProbe, codex.py:66-151, wired :338, commit `d514920`, ON main), headless
(HTTP, no watchdog). **Feasibility unlock:** both cursor (`cursor.py:36-40`) and kimi
(`kimi.py:17-18`) CLIs document a `stream-json` output mode ⇒ the twice-Codex-approved
stream-lease pattern applies to both; no monitor default changes needed.

### §1.4 Immediate remediation for airplat (no framework change needed)

Until Phase-1 lands + pin bump: set the dev role's `model` from `cursor-agent` to `auto` (or a
concrete id from the CLI's list), or switch the role's harness to `claude_code`/`codex`. After
Phase-1: bump the aidazi pin; the validator will refuse harness-name models at preflight.

---

## §2 Phase-1 — unblock the campaign (THIS ROUND'S IMPLEMENTATION TARGET)

Four commits on `feat/phase1-campaign-unblock` (worktree off `aa934ca`), three Codex impl
gates (R1 adapters, R2 governance, R3 whole-scope). Summary (full detail = the reviewed plan):

- **A. cursor**: switch `-p --output-format json`→`stream-json`; add `CursorStreamProbe`
  (session-sentinel + item lease, modeled on CodexStreamProbe); terminal-event extraction with
  single-envelope back-compat via the existing tolerant `_envelope_result_text`; spawn-time
  AdapterError on harness-name-as-model (defense-in-depth). Env-gated real stream capture
  recorded under archive/ BEFORE coding the probe grammar; if the installed CLI's stream-json
  proves broken, contingency = explicit per-harness `MonitorConfig(silence_kill=False)` that
  raises on `timeout=None` (never unbounded) + stderr audit note.
- **B. kimi**: same stream-json + `KimiStreamProbe`; prompt moves to stdin if the CLI supports
  it (else documented argv rationale + optional oversize-argv redaction in stuck diagnostics).
- **C. early validation**: registry root-cause fix `cursor-agent-dev.model: cursor-agent → auto`;
  new deterministic ERROR `model_is_harness_name` in `_check_capability_gate` (denylist =
  ADAPTER_REGISTRY keys ∪ binary names, consistency-tested). Enforced automatically at every
  real run: single-loop run_loop.py:1277-1288 (exit 2) and per campaign unit :998-999 — the
  airplat failure mode now dies at preflight, never mid-campaign.
- **D. real campaign canary**: `examples/real-campaign-canary/` (schema-valid charter, all
  roles claude_code; 2 tiny objectively-checkable milestones) + env-gated test
  (`AIDAZI_E2E_REAL_CAMPAIGN=1`) driving the REAL CLI contract: `--sign-plan` rc 0 →
  `--allow-real --resume` rc 10 (pause `advisory_acceptance_pass_signoff` @ m1) → identity-bound
  decision `ship` → rc 10 @ m2 → second decision → rc 0, `milestones_delivered==2`. Assertions
  are flow-invariants only (exit codes, pause reasons, audit-event counts, no agent-stuck
  diagnostics). Evidence doc in archive/, style of 2026-07-03 watchdog canary evidence.
  **Strict-prompt prerequisites (R0 B-4):** real/non-mock mode refuses thin prompts
  (driver.py:1883-1896) and acceptance requires a human-signed intent contract — so the canary
  charter MUST ship with (a) `intent_contract` with `confirmed_by_human: true` (the canary
  author signs it; recorded in the evidence doc), and (b) per-milestone decompose-plan entries
  whose prompts meet the real-mode strict-prompt bar (full objective/constraints/handoff, not
  one-liners). The canary starts from inputs that already satisfy every refinement gate, so the
  FIRST pause it may legitimately hit is `advisory_acceptance_pass_signoff`; any earlier
  refinement halt is a canary FAILURE, not a resolvable gate.

**Acceptance criteria (R0 F-5 — nothing here is claimed done until the evidence exists):**
suite green (~1700), load-closure/kernel/doc-reconciliation gates untouched-green, 3 Codex
impl-gate APPROVEs, and ONE real canary evidence doc with rc 10→10→0. Only when all of that
is recorded do §1.3 items 1–5 count as retired.

---

## §3 Phase-2 — requirement-driven chain (one command from requirement to campaign)

**Gap:** today a requirement becomes a running campaign via 4 manual steps (Research session →
gate-1 → hand-run Deliver decompose → hand-author campaign-plan.json → --sign-plan). The
full_chain_guided pre-states (research_pending → gate1_pending → decompose_pending,
delivery-loop.md §4.2.4-G) already automate this shape — but only down to ONE milestone's
sub-sprint plan, not a campaign backlog.

**Design: lift the guided pre-chain one tier, to campaign scope.**

1. New entry: `run_loop.py --requirement <file.md> --charter charter.yaml --campaign-out plan.json`.
   Drives: `research_pending` (Research drafts the brief with closure_contract; skipped if the
   charter pins a signed brief) → `gate1_pending` (UNCHANGED semantics: sign/reject/abort via
   gate resolver or checkpoint file; no auto-confirm, Constitution §1.7-D) →
   **`campaign_decompose_pending` (NEW)**: Deliver decomposes the SIGNED brief into an ordered
   milestone backlog (campaign-plan.json), reusing the existing plan-projection prompt
   machinery; with a wired requirement ledger, OW-AUTO derives `covers_req_ids` and forces
   `functional_acceptance: browser_e2e` for user-facing coverage (existing PR#7 behavior) →
   deterministic guard: decomposed modules/layers ⊆ the gate-1 signed envelope (reuse
   `post_gate1_scope_expansion`) → emit plan + print the exact `--sign-plan` command.
   **Authority precondition (R0 B-1):** auto-decompose REQUIRES a NON-EMPTY signed gate-1
   envelope (`modules_in_scope` + `layers_allowed` both non-empty). An empty/absent envelope
   ⇒ HALT (`scope_envelope_unset` checkpoint) for Customer authority — the decompose step can
   NEVER define its own scope and then check itself against it. This TIGHTENS the current
   guided precedent (which lets decompose proceed on an empty envelope) for the campaign tier.
2. **One-sitting signing UX:** gate-1 and campaign_plan_signoff remain TWO constitutional
   signatures, but the CLI sequences them into one interactive session when a TTY gate
   resolver is wired: sign brief → watch decompose → review backlog table → `--sign-plan`.
   Non-interactive path: two checkpoint/decision files, same as today. Net: ONE sitting,
   two signatures, zero other interruptions until the first advisory acceptance.
3. Decompose output is validated against campaign-plan.schema.json + ledger coverage BEFORE
   presenting for signature (a plan that cannot be signed is never shown).

**Done =** scratch-adopter canary: requirement file in → signed campaign running with ≤1
human sitting before first milestone starts; Codex gate; no new authority (both signatures
preserved byte-for-byte in semantics).

---

## §4 Phase-3 — pre-set halt conditions + push-not-poll (WITHIN the constitution)

**Target semantics (user's words):** "if it hits blocking points the human pre-set, it pops
out; otherwise it does not block." Constitutional floor unchanged; all four levers tighten or
notify — none relaxes a mandatory gate.

1. **`autonomy.halt_conditions` (NEW, charter, additive, tighten-only).** A declarative list
   evaluated at deterministic points (unit start, post-review, pre-close, post-acceptance):
   `{"id": "big-diff", "when": {"metric": "files_changed", "op": ">", "value": 40}}`,
   `{"id": "hot-milestone", "when": {"metric": "milestone_id", "op": "in", "value": ["M-auth"]}}`,
   `{"id": "low-confidence", "when": {"metric": "acceptance_confidence", "op": "<", "value": 0.8}}`.
   Metrics come ONLY from already-audited deterministic facts (diff stats, ids, verdict
   fields) — no LLM judgment in the predicate. Match ⇒ HALT with a new checkpoint kind
   `halt_condition_met` carrying the condition id + evaluated facts; resume via the standard
   Mechanism-B decision file. **Mechanical tighten-only invariants (R0 B-3), all
   validator/schema-enforced fail-closed:** (a) the ONLY action a condition can produce is
   HALT + checkpoint — the schema has NO action/route/outcome field, so a condition can never
   mutate a verdict, pick a route, or auto-resolve anything; (b) condition `id`s MUST NOT
   collide with the 9 MANDATORY_CHECKPOINT ids or any engine checkpoint kind (validator
   ERROR — no shadowing); (c) `metric`/`op` come from a CLOSED whitelist; unknown ⇒ ERROR;
   (d) a `halt_condition_met` pause resumes ONLY via the standard identity-bound human
   decision file — no condition, config, or other charter field can resolve it; (e) predicate
   evaluation is a pure function over already-audited facts (read-only; it can never write a
   verdict or checkpoint content). This is the exact inverse of a bypass mechanism, so it
   needs no constitutional amendment.
2. **Default posture → `human_on_the_loop`** (template default; four-area plan Track 4 already
   locked this decision 2026-06-29) with `auto_pass_rules.clean_pass_auto_advance: true` and
   bounded `auto_fix_iteration`. Clean milestones then flow gate-free between signatures.
3. **Judge calibration workflow** to unlock `tooling.acceptance.mode: auto` (the
   constitution's OWN auto-ship channel, §1.7-C): document + tool the calibration ledger
   (golden verdict set, agreement threshold, re-calibration triggers). Until calibrated,
   advisory sign-off stays — by design.
4. **Push, don't poll:** charter `notifications.on_pause: <argv>` — the campaign runner
   execs a bounded, audited notifier (e.g. a shell hook posting to the user's channel) whenever
   it pauses (exit-10 path), carrying campaign_id/pause_reason/checkpoint. The human stops
   babysitting the terminal; combined with §5, other milestones keep running while one waits.

**Done =** canary shows (a) a pre-set condition halts with the right checkpoint + facts,
(b) absent conditions ⇒ zero extra halts vs baseline, (c) notifier fires on every pause;
validator coverage; Codex gate.

---

## §5 Phase-4 — parallel campaign runner (DESIGN ONLY this round)

**Seams already shipped** (schema, validated but unconsumed): `depends_on` (topological DAG,
campaign-plan.schema.json:172; `topological_order` at campaign.py:436-465 already fail-closed
validates it "so a future parallel runner is sound"), `module_locks` (:173), `merge_policy`
(:151). T2-B `milestone_isolation` already gives per-milestone branch/worktree + the
`milestone_merge` gate.

**Design: single-coordinator, isolated-worker processes. No shared-file writers.**

- **Scheduler:** coordinator (the existing campaign process) computes the ready set = milestones
  whose `depends_on` are all delivered AND whose `module_locks` do not intersect any RUNNING
  milestone's locks (empty locks ⇒ conservative default: conflicts with everything ⇒ serial —
  fail-closed; parallelism is opt-in per plan by declaring disjoint locks). `max_concurrent`
  in the plan's authority/budget block (default 1 ⇒ byte-identical to today's runner).
- **Isolation:** every running milestone REQUIRES milestone_isolation (own worktree + branch).
  A worker = child process running the existing per-milestone unit loop unchanged, cwd = its
  worktree, writing ONLY unit run dirs + a per-milestone ledger under
  `<campaign-home>/milestones/<mid>/`. Workers never touch campaign-state.json.
- **State:** campaign-state.json stays SINGLE-WRITER (coordinator). Workers report via atomic
  result files (`<mid>/result.json`, write-tmp+rename); coordinator folds them in and remains
  the only process that appends the campaign-level audit ledger (per-milestone ledgers are
  merged by reference, not by interleaved append — kills the append-race class outright).
  **Pause/state semantics under parallelism (R0 B-2):** `pauses: []` entries carry the FULL
  identity binding a decision file must match today (campaign_id, milestone_id, subsprint_id,
  pause_reason, exact checkpoint basename, AND the per-pause nonce where the gate uses one,
  e.g. completeness_gap_review) — one decision resolves exactly one parked pause, byte-exact,
  never "the current pause". The singleton overlays that today assume ONE live pause
  (freshness re-sign block, engine restamp epoch, gap-followup record — run_loop.py:572-636,
  campaign.py:1090-1122) become PER-MILESTONE records keyed by milestone_id, restored
  per-milestone on resume. Worker result folding is exactly-once: each result file carries a
  unit fingerprint; the coordinator records folded fingerprints IN state within the same
  single-save barrier that advances the cursor (campaign.py:1019-1035 semantics preserved),
  so a re-delivered result after a crash is a no-op, not a double-advance. The single
  pause_reason/pause_checkpoint pair stays mirrored (= the oldest outstanding pause) for one
  deprecation cycle so existing tooling keeps working.
- **Gates:** unchanged and per-milestone. A paused milestone parks; independent ready
  milestones keep running (this is where §4.4 notifications pay off). Campaign exits 10 when
  no worker is runnable and ≥1 pause is outstanding; decision files stay identity-bound and
  now also match on milestone_id (already in the schema). Budgets: coordinator-side atomic
  accounting; `campaign_budget_exhausted` drains workers to quiescence before pausing.
- **Checkpoints:** filenames gain the milestone id (already in the `__<scope>` slot) — collision
  fix is naming discipline, not locking. Crash-idempotency: coordinator persists after every
  fold (same single-save barrier as today, campaign.py:1019-1035); worker crash ⇒ its milestone
  re-enters ready set via the existing resume validation.
- **Merge order:** delivered milestones merge via the existing `milestone_merge` gate;
  `merge_policy` finally consumed (`fifo` | `human_order`). Post-merge, dependent milestones'
  worktrees rebase before start (deterministic, audited; conflict ⇒ HALT `gate_hard_fail`).

**Prerequisites before implementing:** Phase-1 done (real serial campaign proven), Phase-3
notifications (parked pauses must page the human). Implementation is its own design→gate→
phased-commits cycle; est. the largest single work item on this roadmap.

---

## §6 Phase-5 — new-adopter bootstrap (kill the onboarding stuck points)

**Gap:** ONBOARDING.md is 9 sequential manual steps; validators catch errors only at Step 8;
the known stuck points (registry placeholder model, missing CLAUDE.md→@AGENTS.md wiring,
ledger surface classification, Facet-A reachability) each cost a debugging session.

**Design: `engine-kit/tools/adopter_init.py` — one command, human answers only the questions
that are genuinely theirs.**

- Scaffolds: AGENTS.md + CLAUDE.md (`@AGENTS.md`) + per-harness root wiring — incl.
  `.cursor/rules` when a role uses the cursor harness (bare AGENTS.md is NOT cursor wiring;
  today `adopter_wiring_validator.py:489-496` only WARNS about this and its tests accept a
  bare-AGENTS.md cursor target as ok, so "validators green" does NOT currently prove cursor
  wiring — R0 N-6/R0.2 B-1). **Phase-5 therefore ALSO upgrades the wiring validator: cursor
  harness selected + `.cursor/rules` absent/invalid ⇒ FAIL (blocking), not WARN** — so the §
  "done" evidence below really covers cursor adopters. charter.yaml (template default
  `human_on_the_loop` per §4.2), docs/current/*, requirements-ledger seed (OW-2/OW-3 prompts),
  engine-kit + schemas copy, vendored skills + lock, `.orchestrator/`, `.gitignore` entries.
- Interactive prompts ONLY for: intent contract triple (goal/standard/proof_of_done — human
  MUST confirm, §1.7-D), autonomy level + budgets, role harness/provider/model (choices
  validated live against model-registry + the Phase-1 harness-name denylist; Facet-A
  reachability probe runs immediately, so a dead key surfaces at answer time, not Step 8).
- Exit = the same four validators (charter / adopter_wiring / control_plane / adoption_status)
  all green, or a printed remediation list. OW-M3 browser-E2E mandate untouched (fail-closed
  is the point). Existing ONBOARDING.md becomes the reference narrative; the tool is the path.

**Done =** scratch-repo canary: empty dir → validators green in one sitting; brownfield canary
on a fixture repo; Codex gate; ONBOARDING.md updated to point at the tool (doc-reconciliation
lockstep respected).

---

## §7 Acceptance criteria & sequencing

| Phase | Done-evidence | Interruptions on clean path after it lands |
|---|---|---|
| 1 (this round) | real canary rc 10→10→0 + suite/gates green + Codex R1-R3 APPROVE | unchanged (3 signatures) — but the orchestrator actually RUNS |
| 2 | requirement→running campaign, ≤1 sitting pre-start | 1 sitting (2 signatures) + per-milestone advisory sign-off |
| 3 | halt-conditions canary + notifier + calibration doc | 1 sitting + ONLY pre-set conditions (advisory retires when judge calibrated) |
| 4 | N=2 parallel canary, gates preserved, deterministic resume | same gates, ~N× throughput |
| 5 | scratch adopter green in one sitting | n/a (onboarding, not runtime) |

Sequencing 1→2→3→4 is strict (each consumes the previous's proof); 5 is independent after 1
and can interleave. Every phase: design→Codex gate→phased commits→Codex impl gates→canary
evidence→human merge. Nothing in any phase weakens a MANDATORY_CHECKPOINT, acceptance
authority (§1.7-C), signed-scope freshness (Δ-19 F1/T2-A), or the OW-M3 E2E mandate.
