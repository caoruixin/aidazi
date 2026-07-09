---
name: 2026-07-09-phase3-halt-conditions-design
doc_category: intermediate
status: codex-approved (design gate CLOSED; ready to implement)
created: 2026-07-09
base_commit: 6a2078a           # origin/main HEAD = PR #13 merge (Phase-2 requirement-chain landed)
roadmap_source: archive/2026-07-09-autonomy-roadmap-campaign-unblock.md §4 (R0.3 APPROVE)
reviewer: >
  codex gpt-5.5 xhigh — R0 (5B)→rev2; R0.2 (4B)→rev3; R0.3 (3B)→rev4; R0.4 (2B)→rev5; R0.5 (2B)→rev6;
  R0.6 (1B+3NB)→rev7; **R0.7 APPROVE (0 blocking, 3 NB folded, 2026-07-09; verdict
  /tmp/aidazi-phase3-r07/verdict.txt)**. Blocking walked 5→4→3→2→2→1→0; every [R0 B-#]…[R0.6 B-#]
  folded + tagged. R0.7 affirmed the ack lifecycle is fully closed under
  crash×drift×multi-condition×freshness-block×engine-restamp and all anchors accurate.
user_decisions_locked_2026-07-09:
  - Q1 metric scope = "already-audited facts only" — NO new fact source this round. [R0 B-1/B-2
    REFINEMENT] the "already-audited" set is further narrowed by R0 to facts that are ALSO
    campaign-reachable and non-redundant: the verdict-derived metrics are DROPPED (they are
    overwritten before the campaign sees them AND are already served by the constitution's own
    event-triggered gates); the whitelist is plan-static / structural facts only. files_changed
    stays DEFERRED.
  - Q2 round scope = "1+4 full, 2 small, 3 doc".
---

# Phase-3 — pre-set halt conditions + push-not-poll (WITHIN the constitution)

**Goal (roadmap §4):** "if it hits blocking points the human pre-set, it pops out; otherwise it
does not block." The constitutional floor is unchanged; every lever **tightens or notifies — none
relaxes a MANDATORY_CHECKPOINT, acceptance authority (§1.7-C), signed-scope freshness (Δ-19
F1/T2-A), or the OW-M3 E2E mandate.**

## Changelog — R0 → rev2 (the shape changed; read this first)

> **The changelog is a HISTORICAL record — each rev supersedes the prior.** The AUTHORITATIVE design
> is the body (§2–§7) as amended through the latest rev. Where an early changelog row describes an
> approach later replaced (e.g. R0.2's "stamp every ack" or R0.3's "write-gate the ack" — both
> superseded by rev6's whole-cascade provisional set with a halt-time epoch on `pending`), the row
> records what that round FIXED, not the current mechanism. Read §3.4/§3.5 for the live model.

R0 (codex, REVISE) surfaced that the rev1 "evaluate verdict facts at a campaign-tier post-unit
boundary" model was unimplementable and partly redundant. Rev2 folds all findings:

| # | R0 blocking | rev2 resolution |
|---|---|---|
| B-1 | `RunState.last_verdict` is a SINGLE field overwritten every spawn (`driver.py:430,1222,5718`); `run_unit` surfaces no verdict facts (`campaign.py:3660`, `run_loop.py:1054`) → `review_blocking_count`/`close_verdict` are NOT available campaign-side | **Drop all verdict-derived metrics.** The whitelist is now plan-static / structural facts only (§3.2), which need ZERO surfacing. |
| B-2 | The campaign only reaches a post-unit boundary on `advance`/`done`; blocking-review, close C/D, advisory acceptance, fix_required, needs_human all HALT inside the driver first (`driver.py:3886,3990,6299,6333`) → verdict conditions are unreachable or trivially-clean | **Adopt the outcome/structural partition (§2):** outcome-halts are ALREADY the constitution's event-triggered gates; halt_conditions covers only the *structural* halts the engine lacks. **Single evaluation point EP-pre (pre-dispatch)**; EP-post removed. |
| B-3 | `_pause.extra` is audit-only (`campaign.py:840`); no durable parseable resume contract; the filename is not a per-pause nonce; a direct `_advance_milestone_cursor` would bypass `_complete_milestone` outcome-stamp + merge gate (`campaign.py:1359-1370`) | **Durable `halt_condition_pending` state field (§3.5) + monotonic-seq nonce filename.** The ONLY resume action is "re-dispatch the cursor" (§3.4) — the cursor is NEVER advanced on proceed, so `_complete_milestone` is never bypassed. |
| B-4 | notifier "read-only" is false (arbitrary user code, inherited FS); auditing full argv can leak webhook tokens | **Reframed (§4):** a TRUSTED adopter-owned side-effecting hook — NOT sandboxed. Framework guarantees fail-SAFE + pause-persisted-before-notify + resume-re-validates-fail-closed. Audit is redacted (argv0 + argc + sha256; no full argv/env/bodies). |
| B-5 | the AST inventory test captures only CONSTANT first-arg ids; a dynamic id (`e2e_remediation_escalation`, `driver.py:4536`) is NOT covered and NOT in `KNOWN_CHECKPOINTS` | **Corrected the claim (§1.1)** — the AST test is a PARTIAL guard. `halt_condition_met` is campaign-emitted (not driver-emitted), so it is covered by a DIRECT membership+disjointness test (§3.5), not the AST test. (The pre-existing `e2e_remediation_escalation` gap is noted, not fixed — out of scope.) |
| N-1 | use full paths for `engine-kit/audit/audit_log.py`, `engine-kit/tools/review_runner.py` | done. |
| N-2 | id-collision test is vacuous if the id regex forbids underscores (all checkpoint kinds have underscores) | **id regex ALLOWS underscores** (`^[a-z0-9][a-z0-9_-]{0,63}$`, §3.1) so a crafted colliding id (`gate_hard_fail`) is expressible and the validator genuinely rejects it (§3.6b non-vacuous). |
| N-3 | specify how canary (b) compares against base | **golden-bytes fixture** captured from base `6a2078a` + a two-run byte-diff (§6). |

R0 also affirmed as SOUND: `halt_condition_met` ∈ `CAMPAIGN_CHECKPOINTS`; deferring `files_changed`;
no constitutional amendment needed; lever-2 "already landed" honesty; lever-3 doc-only.

### R0.2 → rev3 (pre-dispatch mechanics — 4 blocking + 1 NB, all folded)

R0.2 affirmed the rev2 shape (verdict-facts correctly dropped; B-5/N-1/N-2/N-3 resolved) and caught
four mechanics bugs in the new pre-dispatch path:

| # | R0.2 blocking | rev3 resolution |
|---|---|---|
| B-1 | `milestone_functional_acceptance` bound the RAW plan field `milestone.get("functional_acceptance")`, but the class INHERITS from the charter via `resolve_functional_acceptance` (`campaign.py:2581-2593`) — so `== browser_e2e` misses charter-inherited milestones and `!=` fires wrong | the extractor uses the **RESOLVED** class `resolve_functional_acceptance(charter, milestone.get("functional_acceptance"))[0]` (§3.2); tests for explicit-override / charter-inheritance / default-static |
| B-2 | EP-pre ran BEFORE `_authority_fresh` → a halt could be acked against stale/unsigned scope; after a re-sign the persisted ack suppresses the GENUINE condition in the fresh epoch | EP-pre now evaluates **only AFTER `_authority_fresh()` passes**; `halt_condition_pending` + every ack are **stamped with the live `_live_signed_scope_hash()`** (`campaign.py:1498-1506`) and acks whose hash ≠ live are dropped — a re-sign re-arms all conditions (§3.4) |
| B-3 | proceed routed through `_commit_dispatch_resolution` (`campaign.py:1026`) which persists `STATUS_RUNNING` → crash replay calls `run_unit(resume=True)` (`campaign.py:2372`) → the Driver RAISES on a missing unit `state.json` (`driver.py:3413-3417`) for a never-started unit | proceed follows the **barrier-free `ACT_REDISPATCH_FRESH` semantics** (`campaign.py:2221-2231`) — leaves state PAUSED, no `STATUS_RUNNING`, crash-idempotent for an unstarted unit; the ack is `_save`d durably before returning `"proceed"` (§3.5) |
| B-4 | canary (a) had TWO conditions matching m2 but asserted a single proceed then dispatch — contradicts the per-condition ack | canary (a) rewritten to expect **two sequential pauses** (`hot-milestone` r1 → proceed → `gate-e2e` r2 → proceed → dispatch), which also proves the nonce seq + per-condition ack + declaration order (§6) |
| N-1 | "cannot make governance PROCEED INCORRECTLY" overclaims for a trusted unsandboxed hook | softened (§4.2): the framework defends against a TAMPERED DECISION FILE (fail-closed resolver), but a trusted hook corrupting its own state/plan files is OUT OF SCOPE (at worst a fail-closed resume), not a framework guarantee |

### R0.3 → rev4 (the ack / crash-idempotence corner — 3 blocking + 2 NB, all folded)

R0.3 confirmed R0.2 B-1/N-1 resolved and anchors accurate, and drilled into the ack lifecycle. The
fixes SIMPLIFIED the model (write-gate the ack; drop read-time invalidation):

| # | R0.3 blocking | rev4 resolution |
|---|---|---|
| B-1 | stale-ack window: if the plan drifts between halt and `proceed`, stamping the ack with the (drifted) live hash lets it survive a later re-sign and suppress the genuine condition | the ack is **write-gated**: written ONLY when at proceed `_authority_fresh()` AND `pending.signed_scope_hash == _live_signed_scope_hash()` — no drift since halt. On drift → re-arm in the current epoch, no ack (§3.4/§3.5 path 3) |
| B-2 | crash-idempotence: clearing `halt_condition_pending` on proceed leaves a PAUSED `halt_condition_met` with no identity to re-bind on replay | `pending` is **never cleared standalone** — kept through proceed (like `ACT_REDISPATCH_FRESH` keeps the PAUSED state) and cleared only atomically with the redispatched unit's outcome `_save` (`campaign.py:2425-2466`); the ack write is idempotent (§3.5 lifecycle) |
| B-3 | full-hash ack invalidation wrongly drops milestone-scoped acks across a legitimate `engine_restamp` (`campaign.py:1291`, hash changes but facts don't) | **read-time invalidation REMOVED** — acks are permanent per-milestone keys; only the write-gate (B-1) prevents stale acks. An `engine_restamp` never drops an existing ack (§3.4) |
| N-1 | anchor `1498-1506` → `1498-1508` for the full `_live_signed_scope_hash()` call | done |
| N-2 | byte-identical-when-absent credible IF all new code (ctx extraction, seq, ack fields, notifier audit) stays behind non-empty `halt_conditions`/`notifications` | affirmed as an implementation invariant (§3.7/§4.4) — the canary asserts it |

### R0.4 → rev5 (provisional acks + condition-definition identity — 2 blocking + 2 NB, all folded)

R0.4 confirmed R0.3 resolved and freshness/restamp reasoning sound, and caught the last two ack
corners:

| # | R0.4 blocking | rev5 resolution |
|---|---|---|
| B-1 | crash-then-drift: rev4 wrote the permanent ack at `proceed`, so `halt → proceed(ack) → crash → re-sign → replay` found the ack present and skipped instead of re-arming | **provisional-then-permanent acks (§3.4)**: the ack whose key == the active `pending`'s key is provisional (epoch-removable at EP-pre on drift); it becomes permanent only when `pending` clears at the redispatched unit's outcome `_save`. Crash-then-drift removes+re-arms it |
| B-2 | ack key `(condition_id, milestone_id[/subsprint_id])` is too coarse — a changed `when` under a reused `id` after re-sign is wrongly suppressed | ack key + `pending` include a normalized **`condition_digest`** (sha256 of the `when` object) (§3.4/§3.5); a changed predicate ⇒ new digest ⇒ new key ⇒ not suppressed |
| N-1 | `2425-2466` anchor misses milestone-done (breaks at `:2449`, saves via `_complete_milestone`) | pending-clear specified for all three outcome saves incl. `_complete_milestone` `:1359-1370` (§3.5 lifecycle) |
| N-2 | resolver should require `pending` present + `pending.checkpoint_basename == basename(pause_checkpoint)`, fail-closed | added to §3.5a (fail-close if `pending` absent; assert basename + condition_id + milestone_id) |

### R0.5 → rev6 (whole-cascade provisional set + digest canonicalization + anchors — 2 blocking + 3 NB)

R0.5 confirmed single-condition crash-then-drift resolved and caught a multi-condition variant of
the same class, plus a stale canary line and two anchor errors:

| # | R0.5 blocking | rev6 resolution |
|---|---|---|
| B-1 | multi-condition drift: rev5 promoted C's ack to permanent the moment C2 overwrote `pending` (before dispatch); a re-sign while C2 pending then flushed only C2's ack, leaving C's permanent ack to stale-suppress C | the **whole pre-dispatch cascade** is one provisional SET `halt_condition_provisional` (§3.4); it commits to permanent **only at the redispatched unit's outcome `_save`** (actual dispatch), and a mid-cascade drift **flushes the ENTIRE set** ⇒ every cascade condition re-arms |
| B-2 | §6 canary drift line still said the (rev4) "proceed writes no ack" model | canary DRIFT variants rewritten to the provisional-set flush model + a MULTI-DRIFT case proving C re-arms (§6 (i)/(ii)) |
| N-1 | define `condition_digest` canonicalization exactly (incl. `in`-array order) | §3.4: `sha256(canonical_json(when))`, sorted object keys, **sorted `value` array for `in`/`not_in`** (order-independent), `note` excluded |
| N-2 | stale anchors: phantom `model.py:1219-1226`; `run_loop.py:773-778` is skills-preflight not notifier append | `charter_validator.py:1219-1226` made explicit (it exists — the `mission_signal_profile` closed-set ERROR); audit-path recipe re-cited as `run_loop.py:776-778` (the skills-preflight `audit_ledger_path=` argument the notifier REUSES) (§1.4/§4.3) |
| N-3 | cross-reference the structural-only narrowing as the accepted scope decision | added to §2 ("Accepted scope decision") |

### R0.6 → rev7 (first-halt drift epoch — 1 blocking + 3 NB, all folded)

R0.6 confirmed the multi-condition + no-drift cases resolved and found the LAST stale-ack corner: the
cascade epoch was captured too late.

| # | R0.6 blocking | rev7 resolution |
|---|---|---|
| B-1 | rev6 stamped `halt_condition_provisional.signed_scope_hash` on the FIRST `proceed`, so a drift between the FIRST halt and its proceed (or via `freshness_block`: stale proceed → block → re-sign) was NOT detected — EP-pre saw provisional.hash == live and skipped instead of re-arming | the cascade epoch is captured at **HALT time** on `pending.signed_scope_hash` (`_live_signed_scope_hash()` at the EP-pre match); the provisional set is a plain key list; the EP-pre drift-recheck compares `pending.signed_scope_hash != live` (pending is present for the whole cascade). Catches drift at ANY point incl. before the first proceed and the freshness-block path (§3.4/§3.5) |
| N-1 | `_complete_milestone` can persist via `_pause_milestone_merge`, not only cursor advance | §3.5 lifecycle: the promotion+clear rides whichever `_complete_milestone` `_save` fires — `_advance_milestone_cursor` OR `_pause_milestone_merge` (`campaign.py:1367-1368`) |
| N-2 | add `halt_condition_provisional` to the byte-identical absent-field assertions | added to §3.7 / §6(b) / §7 |
| N-3 | mark stale historical changelog rows superseded | added the "HISTORICAL record" banner atop the Changelog |

---

## §0 What this round ships

| Lever | This round | Note |
|---|---|---|
| 1. `autonomy.halt_conditions` | **FULL code + canary** | structural pre-set halts (§2/§3) |
| 2. default posture → `human_on_the_loop` | **verify-only (already landed)** | `templates/mission-charter.yaml:38`; `clean_pass_auto_advance` stays `false` (`:54`) — untouched |
| 3. judge calibration workflow | **design/doc deliverable** | ledger format + thresholds + triggers (§5.2); no tool build |
| 4. `notifications.on_pause` | **FULL code + canary** | trusted, bounded, fail-safe notifier (§4) |

**Done-criteria (roadmap §4):** the offline canary shows **(a)** a pre-set condition halts with the
right checkpoint + facts, **(b)** absent conditions ⇒ **byte-identical to baseline**, **(c)** the
notifier fires on **every** pause; + validator coverage + Codex gate. Canary is **fully offline +
deterministic** (mock adapters + local notifier script); **no real model spend.**

---

## §1 Current-state anchors (all file:line at base `6a2078a`)

Paths: campaign = `engine-kit/orchestrator/campaign.py`; driver =
`engine-kit/orchestrator/driver.py`; CLI/resolver = `engine-kit/scheduling/run_loop.py`; audit =
`engine-kit/audit/audit_log.py`; gate runner = `engine-kit/tools/review_runner.py`.

### §1.1 Pause / resume / checkpoint machinery

- **Resume classes + four category frozensets** — `campaign.py:110-162`: `RESUME_DRIVER`
  (Mechanism A, driver re-enters via `halt_resume_state`), `RESUME_DISPATCH` (Mechanism B, campaign
  interprets a decision), `NON_PAUSE`; `DRIVER_RESUME_CHECKPOINTS` (`:116-128`),
  `DISPATCH_CHECKPOINTS` (`:132-144`, **driver-emitted** human gates), `CAMPAIGN_CHECKPOINTS`
  (`:146-155`, **campaign-emitted** gates), `NON_PAUSE_CHECKPOINTS` (`:158-162`).
- **`KNOWN_CHECKPOINTS`** = union (`:168-171`); **`classify_checkpoint`** (`:174-183`) →
  `DRIVER_RESUME`/`NON_PAUSE`/else `RESUME_DISPATCH` (fail-closed: unknown ⇒ dispatch/human gate).
- **[R0 B-5] The inventory test is a PARTIAL guard.**
  `test_campaign.py:69-103`: `test_every_driver_checkpoint_is_classified` (`:87-95`) AST-parses
  `driver.py` and captures only the **constant first-arg** checkpoint ids (helper `:74-85`), then
  asserts `emitted - KNOWN_CHECKPOINTS == set()`; `test_sets_are_disjoint` (`:97-103`). A
  **dynamically-computed** checkpoint id is not captured — e.g. `e2e_remediation_escalation`
  (`driver.py:4536`, `checkpoint = "post_gate1_scope_expansion" if scope_reason else
  "e2e_remediation_escalation"`) is neither AST-captured nor in `KNOWN_CHECKPOINTS` (a pre-existing
  gap; `classify_checkpoint` fail-closes it to `RESUME_DISPATCH`). **rev2 does NOT rely on the AST
  test** for its new kind (which is campaign-emitted): §3.5 adds a DIRECT membership+disjointness
  test. The pre-existing gap is noted, not fixed (out of scope).
- **Per-unit dispatch + pause site** — `_drive_milestones`, `campaign.py:2360-2466`: crash-recovery
  replay guard (`:2372-2382`); the **not-already dispatch path** `else:` (`:2383`) → `resume_this`
  + `_authority_fresh()` (`:2397-2399`) → `self.run_unit(...)` (`:2406-2414`); classify `final_state`
  into `_ADVANCE_STATES`/`_MILESTONE_DONE_STATES` (`campaign.py:500-501`) at `:2425`/`:2440`, else
  PAUSE via `_pause(...)` (`:2461-2466`). **This `else:` block (before `run_unit`) is the EP-pre
  hook (§3.4).**
- **`_pause`** — `campaign.py:840-848`: persists `status`/`pause_reason`/`pause_checkpoint` + one
  `_save()`; the `extra` dict is **audit-only, NOT durable state** [R0 B-3].
- **Milestone completion** — `_complete_milestone` (`campaign.py:1359-1370`): stamps terminal
  outcome (F3) + optional `milestone_merge` gate **before** `_advance_milestone_cursor()`. **A
  cursor advance that skips this bypasses outcome-stamping + the merge gate** [R0 B-3].
- **Single-save §3.5c barrier** — `_commit_dispatch_resolution()` (`campaign.py:1026-1042`);
  cursor helper `_advance_milestone_cursor` (`:1014-1024`).
- **Resume dispatch** — `_handle_resume(decision_resolver)` (`campaign.py:2003-2242`) with
  dedicated branches for `campaign_plan_signoff`/`milestone_decompose_required`/
  `completeness_gap_review`/`milestone_merge` (`:2012-2098`); else resolve → classify →
  `interpret_dispatch` (`:2159`) / `_DISPATCH_TABLE` (`:202-255`), actions `:192-199`. Nonce
  precedent = `_write_gap_review_checkpoint` monotonic `gap_review_seq` (`campaign.py:1602-1647`,
  seq `:1610-1611`, fname `:1617`).

### §1.2 What "resume" does — the constraint

A **mid-unit DISPATCH halt re-runs the whole unit FRESH** on resume (`scope_deviation`/
`gate_hard_fail` set `STATE_HALTED` without `halt_resume_state`, `driver.py:3999-4010`, `946-956`;
campaign re-dispatches `resume=False`, `campaign.py:2223-2231,2384,3641-3649`). Only the 3
spec-refinement `DRIVER_RESUME` kinds continue mid-unit (`driver.py:1945/2128/5543` set
`halt_resume_state`; `driver.py:3502-3505`). ⇒ any new mid-unit halt that resumes via the dispatch
table would re-run the unit AND, being deterministic, **re-fire** → an infinite pause loop. rev2
evaluates **only before dispatch** (§3.4) so "proceed" = re-dispatch the not-yet-run cursor unit,
with an ack that suppresses the re-fire.

### §1.3 Facts: what exists, what is reachable [R0 B-1/B-2]

- **`milestone_id`** — campaign-tier first-class (on every unit record, `campaign.py:2421`; passed
  to `run_unit` `:2407`). Available **pre-dispatch**.
- **`subsprint_id`** — the cursor sub-sprint id (`campaign.py:2407`, `RunState.subsprint_id`).
  Available **pre-dispatch**.
- **`milestone_functional_acceptance`** — the **RESOLVED** per-milestone acceptance class
  [R0.2 B-1]. NOT the raw plan field: the class inherits from the charter when the milestone omits
  it — `resolve_functional_acceptance(charter, milestone.get("functional_acceptance"))` (precedence:
  explicit milestone value overrides → charter `tooling.acceptance.functional.mode` → `static`),
  `campaign.py:2581-2593` (the same precedence `derive_milestone_context` applies; the signed
  envelope records `resolved_functional_acceptance`). Plan+charter-static, available **pre-dispatch**.
- **Verdict-derived facts are NOT campaign-reachable** [R0 B-1]: `RunState.last_verdict` is one
  field overwritten every spawn (`driver.py:430,1222,5718`); `run_unit` returns only
  `{final_state,spawn_count,loop_id,pause_reason,checkpoint_path}` (`campaign.py:3641-3663`);
  `run_loop` returns no verdict facts (`run_loop.py:1054`). AND they are unreachable at a clean
  boundary [R0 B-2]: blocking review → `fix_required`/`gate_hard_fail`, close C/D, advisory
  acceptance, `fix_required`, `needs_human` all HALT in the driver (`driver.py:3886,3990,6299,6333`)
  **before** `advance`/`done`. On the `advance`/`done` path the verdict is clean by construction. ⇒
  verdict metrics are dropped (§2).
- **`files_changed`** — no already-audited delivery-loop diff-stat exists (only the Quick-Fix lane,
  `engine-kit/quickfix/launcher.py:178,272`). DEFERRED.

### §1.4 Exit-10 / notifier hook + audit append

- `CAMPAIGN_EXIT_PAUSED = 10` (`run_loop.py:79`); status→exit map (`:806-810`).
- `run_campaign_entry` builds the paused-result dict `:849-866` (`campaign_id`, `pause_reason`
  `:852`, `pause_checkpoint` `:853`, `pause_milestone_id`/`pause_subsprint_id` `:854-855`) from the
  returned `CampaignState` (`:800-805`); `charter` is in scope (passed to `run_campaign` `:790`) and
  the campaign audit-path RECIPE `audit.audit_path(campaign_id, os.path.join(home,"audit"))` is the
  one already used at `run_loop.py:776-778` (there as the `audit_ledger_path=` argument to the
  skills-preflight call `:773`); the notifier reuses the SAME recipe for a NEW append (§4.3). ⇒
  **the notifier fires here, on the paused branch** (§4.3).
- Audit append: `audit.append_event(loop_id, type, payload, ts=…, path=…)`
  (`engine-kit/audit/audit_log.py:259-289`) → one hash-chained line
  `{loop_id,seq,ts,type,payload,prev_hash,hash}` (`audit_log.py:118-142`) at
  `.orchestrator/audit/<loop_id>.jsonl` (`audit_log.py:252-256`). Campaign helper `Campaign._audit`
  (`campaign.py:681-683`).
- Bounded/audited subprocess precedents: `engine-kit/tools/review_runner.py:173-190` (argv list,
  `shell=False`, `OSError`→record not raise, bounded poll + pgid kill `:287-297`, secret-free
  `AttemptRecord`) and `engine-kit/adapters/monitor.py:39-52,133-140,179-190` (`run_with_monitor`,
  argv list, hard timeout, swallowed teardown).

### §1.5 Charter schema surfaces (all additive)

`autonomy` block `schemas/mission-charter.schema.json:40-117`, `additionalProperties:false` (`:43`)
⇒ `halt_conditions` goes in `autonomy.properties` (precedent `e2e_remediation` `:106-115`). Root
`additionalProperties:false` (`:8`) ⇒ top-level `notifications` goes in root `properties` (mirror
`audit`/`memory`/`isolation`, ending `:370`). `validate_semantics` dispatcher
`charter_validator.py:1580-1619`; `report.error/warn` (`:296-300`); closed-set ERROR precedent
`_check_mission_signal_profile` (`charter_validator.py:1219-1226`); NO-OP-when-absent precedent
`_check_e2e_remediation_bound` (`:586-590`). `MANDATORY_CHECKPOINTS` (the 9)
`charter_validator.py:245-255`; `_OVERRIDE_KEY_SUBSTRINGS` (`:260-266`); `_DISABLE_KEYS` (`:270`).

---

## §2 The partition that makes rev2 correct (outcome vs structural halts)

The constitution ALREADY halts on adverse **outcomes**: `gate_hard_fail`, `close_taxonomy_C_or_D`,
`scope_deviation`, `advisory_acceptance_pass_signoff`, `acceptance_fix_required`,
`acceptance_surface_approve` (all `DISPATCH_CHECKPOINTS`, `campaign.py:132-144`), plus the 9
`MANDATORY_CHECKPOINTS`. A "halt if review had blocking findings" or "halt if acceptance is only
advisory" condition would be **redundant** with these — and (§1.3) unreachable at campaign tier
anyway.

`autonomy.halt_conditions`'s unique, non-redundant contribution is **user-declared STRUCTURAL
halts** the engine has no built-in gate for: "*pause before this specific milestone / sub-sprint /
acceptance-class even when everything passes clean.*" These key on **plan-static facts known before
the unit runs**, so they are evaluated at exactly one deterministic point — **EP-pre, before
dispatch** — and need no verdict surfacing and no mid-unit machinery. This is faithful to the
roadmap goal ("pause at pre-set blocking points") while staying tighten-only and byte-identical when
absent.

**Accepted scope decision [R0.5 NB-3]:** roadmap §4.1 illustrates halt_conditions with
post-review / pre-close / post-acceptance (verdict-based) examples. This implementation design
DELIBERATELY narrows to structural (plan-static) predicates because (§1.3) the verdict facts are
neither campaign-reachable (overwritten before the campaign sees them) nor non-redundant (the
constitution's event-triggered gates already halt on adverse outcomes). The narrowing is a
tightening, not a scope reduction of the roadmap's GOAL; the illustrative verdict metrics are
addressed as deferred/remapped in §3.2. Codex affirmed this partition as sound across R0.2–R0.5.

---

## §3 Lever 1 — `autonomy.halt_conditions`

### §3.1 Charter schema (additive, under `autonomy.properties`)

```jsonc
"halt_conditions": {
  "type": "array",
  "description": "Pre-set, declarative STRUCTURAL halt conditions (Constitution-safe, tighten-only). Each is a pure predicate over ALREADY-AUDITED, plan-static facts evaluated BEFORE a unit is dispatched; a match PAUSES at a halt_condition_met checkpoint carrying the condition id + facts. A condition can NEVER mutate a verdict, pick a route, or auto-resolve anything (the schema has no action/route/outcome field). Absent/empty ⇒ byte-identical to no halt conditions.",
  "items": {
    "type": "object", "additionalProperties": false, "required": ["id", "when"],
    "properties": {
      "id":   { "type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$" },   // [R0 N-2] underscores allowed → collision check is non-vacuous
      "note": { "type": "string" },
      "when": {
        "type": "object", "additionalProperties": false, "required": ["metric", "op", "value"],
        "properties": {
          "metric": { "type": "string", "enum": [ "milestone_id", "subsprint_id", "milestone_functional_acceptance" ] },
          "op":     { "type": "string", "enum": ["==", "!=", "in", "not_in"] },
          "value":  {}   // value-type checked against the metric registry by the validator (§3.6c)
        }
      }
    }
  }
}
```

No `action`/`route`/`outcome`/`then`/`resolve` key exists — invariant (a), structural via
`additionalProperties:false`.

### §3.2 The closed metric whitelist (plan-static / structural only)

Single source of truth = new `engine-kit/orchestrator/halt_metrics.py` (the schema enum + validator
+ evaluator all bind to it; lockstep-tested, mirroring `TASK_SIGNAL_VOCAB`
`charter_validator.py:1219`). Each entry: `value_type`, allowed `op`s, `ack_scope`, pure
`extract(ctx) -> value`.

| metric | value_type | ops | ack_scope | fact source (pre-dispatch, no surfacing) |
|---|---|---|---|---|
| `milestone_id` | string | `==`,`!=`,`in`,`not_in` | milestone | `campaign.py:2407` |
| `subsprint_id` | string | `==`,`!=`,`in`,`not_in` | subsprint | `campaign.py:2407` |
| `milestone_functional_acceptance` | enum `static`\|`browser_e2e` | `==`,`!=`,`in`,`not_in` | milestone | **RESOLVED** class via `resolve_functional_acceptance(charter, milestone.get("functional_acceptance"))[0]` `campaign.py:2581-2593` [R0.2 B-1] — NOT the raw field (charter inheritance); tests: explicit-override / charter-inheritance / default-static |

**Deferred / remapped (documented):** `files_changed`/`lines_changed` DEFERRED (no audited source;
adding one = a self-contained follow-up: one registry entry + enum member + extractor).
Verdict-derived metrics (`review_blocking_count`, `close_verdict`, `acceptance_*`) **excluded** —
redundant with the constitution's own gates + not campaign-reachable (§1.3/§2).

### §3.3 (removed) — no fact surfacing needed

rev1's §3.3 (surface verdict facts through `run_unit`) is DELETED. All whitelist facts are
plan-static and read directly from the milestone/cursor at EP-pre — zero change to `run_unit`, zero
new persisted artifact.

### §3.4 Evaluation point (EP-pre) + re-fire suppression

**EP-pre** — inside `_drive_milestones`, in the not-already dispatch `else:` block, **immediately
AFTER `_authority_fresh()` passes** and BEFORE `run_unit` (i.e. between `campaign.py:2399` and
`:2406`) [R0.2 B-2]. Evaluating after the freshness gate is load-bearing: a halt must never be
acknowledged against stale/unsigned scope only for a later re-sign to leave that ack suppressing the
genuine condition in the fresh epoch. Only reached when the campaign is about to actually dispatch a
unit (crash-recovery replay `already=True` skips this block entirely, so a replayed unit is never
re-halted; a Mechanism-A driver-resume redispatch also re-enters here but its condition is already
acked). Context available: `milestone` (id + resolved functional_acceptance), `subsprint_id`,
milestone/subsprint index, and the live `signed_scope_hash`.

`evaluate(conditions, ctx, ack_set) -> Optional[Match]` — first declaration-order condition whose
metric predicate is true AND whose ack key is NOT in `ack_set`. Pure, read-only (invariant (e)).

- **No match** → proceed to dispatch exactly as today (byte-identical path).
- **Match** → emit `halt_condition_met` (§3.5) and `_pause`. **The cursor is NOT advanced** — the
  unit has not run.

**Re-fire suppression (ack set) — provisional-then-permanent [R0.2 B-2 / R0.3 B-1,B-3 / R0.4 B-1,B-2].**

**Ack key** = `(condition_id, condition_digest, milestone_id)` for `ack_scope: milestone` (a
milestone/class gate is a once-per-milestone act, so it does not re-pause at each sub-sprint's
EP-pre), or `(condition_id, condition_digest, milestone_id, subsprint_id)` for `ack_scope:
subsprint`. **`condition_digest`** = `sha256` of the **canonicalized `when` object** [R0.4 B-2 / R0.5
NB-1]: JSON with object keys sorted, and — because `in`/`not_in` are set-membership predicates whose
meaning is order-independent — the `value` array for `op ∈ {in, not_in}` is **sorted** before
hashing (so `in [a,b]` and `in [b,a]` share a digest and do not spuriously re-fire); for scalar ops
the `value` is used verbatim. `note` is NOT hashed (it is not predicate behavior). So if the adopter
changes `halt_conditions[id=watch].when` under a reused `id` and re-signs, the new predicate has a
new digest ⇒ a new key ⇒ the old ack cannot suppress it; a `note` edit or an `in`-array reorder does
not.

**Provisional vs permanent — a whole-cascade set, epoch-stamped at HALT [R0.4 B-1 / R0.5 B-1 /
R0.6 B-1].** Two `CampaignState` fields: `halt_condition_acks` (PERMANENT, committed) and
`halt_condition_provisional: {keys: [...]}` — **every** ack proceeded **since the last actual unit
dispatch** (a pre-dispatch halt cascade can chain several: C halts→proceed→C2 halts→proceed→…).
EP-pre skips a condition whose key is in `halt_condition_acks` ∪ `halt_condition_provisional.keys`.
On `proceed`, the condition's key is added to `halt_condition_provisional.keys`.

**The cascade epoch is `pending.signed_scope_hash`, captured at HALT time** (set in the EP-pre match
path, `_live_signed_scope_hash()` `campaign.py:1498-1508`), NOT at proceed [R0.6 B-1]. `pending` is
present for the whole cascade (kept until the unit dispatches, §3.5), and within a cascade every
`pending.signed_scope_hash` is the same epoch (a drift flushes before the cascade can advance), so
the LIVE `pending` always carries the cascade's start epoch. The safety invariant the drift-check
relies on is the IMPLICATION **`halt_condition_provisional` non-empty ⇒ `pending` present** (the
converse does not hold — at the very FIRST halt `pending` is present while the provisional set is
still empty, until the first `proceed` [R0.7 NB]). **The whole provisional set commits together, and
flushes together:**
- **Commit → permanent:** atomically with the redispatched unit's outcome `_save` (§3.5), ALL
  `halt_condition_provisional.keys` are promoted into `halt_condition_acks` and the provisional set
  + `pending` are cleared. Promotion happens ONLY when the unit actually dispatches — **not** when
  one cascade halt supersedes the previous [R0.5 B-1].
- **Flush → re-arm (drift):** at EP-pre, when `pending` is active AND
  `pending.signed_scope_hash != _live_signed_scope_hash()` — the plan drifted / was re-signed to a
  NEW epoch since the cascade's FIRST halt — the campaign **durably drops the ENTIRE provisional set**
  and discards `pending`; every condition in the cascade re-arms (re-fires with a fresh nonce,
  stamped the live hash). Because the epoch is captured at HALT (not proceed), this catches drift at
  ANY point in the cascade, INCLUDING between the FIRST halt and its proceed, and the
  `freshness_block` path (a stale proceed → block → re-sign → the halt-time hash now mismatches →
  flush) [R0.6 B-1]. It closes every crash-then-drift hole: single-condition [R0.4 B-1],
  multi-condition (re-sign while C2 pending flushes C's ack too [R0.5 B-1]), and first-halt
  [R0.6 B-1].

**No read-time invalidation of PERMANENT acks [R0.3 B-3].** The drift flush touches only the
provisional set (this-cascade acks). A legitimate mechanical `engine_restamp` follow-up epoch advance
(`campaign.py:1291`, changes the signed hash but not any milestone's facts) can therefore **never**
drop a permanent ack (a committed cascade). `_authority_fresh()` is also required before EP-pre even
runs (§3.4), so no cascade is committed against unsigned scope [R0.3 B-1].

`halt_condition_acks` is a `CampaignState` field serialized **only when non-empty** — the
conditional-overlay pattern of `freshness_block`/`engine_restamp`/`gap_followup_state`
(`campaign.py:355-384,386-415`) — so a run that never halts on a condition persists byte-identical
state.

### §3.5 `halt_condition_met` checkpoint + durable resume contract [R0 B-3]

- **Classification.** Campaign-emitted ⇒ added to **`CAMPAIGN_CHECKPOINTS`** (`campaign.py:146-155`).
  `KNOWN_CHECKPOINTS` (`:168-171`) then includes it; `classify_checkpoint` → `RESUME_DISPATCH`.
  A **direct** membership+disjointness test is added (mirroring `completeness_gap_review`,
  `test_campaign.py:1817-1830`) — it does NOT depend on the AST guard (§1.1).
- **Durable pause-identity contract + lifecycle [R0.3 B-2 / R0.4 B-1].** `_pause.extra` is audit-only,
  so a durable `CampaignState.halt_condition_pending: {condition_id, condition_digest, metric,
  ack_scope, milestone_id, subsprint_id, checkpoint_basename, facts, signed_scope_hash, resolved}` is
  set in the EP-pre match path atomically with the `_pause` (conditional serialization, like the
  other overlays). `signed_scope_hash` is captured at HALT time (`_live_signed_scope_hash()`) and is
  the cascade epoch used by the EP-pre drift-recheck (§3.4) [R0.6 B-1]. The resolver's identity
  binding reads THIS record (§3.5a). **Lifecycle:**
  `halt_condition_pending` is set/overwritten on each EP-pre match (fresh nonce, `resolved:false`,
  halt-time `signed_scope_hash`),
  `resolved` flips true on `proceed` (the freshness/drift recheck is at EP-pre, not proceed — §3.5),
  and it is **cleared ONLY atomically with recording the redispatched unit's outcome** (with the
  whole provisional set's promotion, §3.4) — cleared
  in-memory once the outcome is known (`campaign.py:2415-2423`) and persisted by the ensuing outcome
  `_save`: the advance `_save` (`:2438`), the pause `_save` (`:2460`), or — for the milestone-done
  path that `break`s at `:2449` — `_complete_milestone` (`campaign.py:1359-1370`), which persists via
  EITHER `_advance_milestone_cursor` OR the merge-gate `_pause_milestone_merge` (`:1367-1368`); the
  in-memory promotion+clear rides whichever `_save` fires [R0.4 NB-1 / R0.6 NB-1]. **"Outcome"
  includes the redispatched unit halting at a
  DIFFERENT (non-halt-condition) reason** — e.g. it dispatches, runs, and hits `gate_hard_fail`:
  that pause `_save` (`:2460`) clears `pending` and commits the (now-permanent) provisional ack. So a
  proceeded halt_condition is consumed once the unit actually dispatches, regardless of that unit's
  own outcome — never a dangling `pending` or a perpetually-provisional ack. It is **never cleared
  standalone on `proceed`**: keeping it through the proceed→redispatch→outcome window is what makes
  replay safe (the resolver can always re-bind the decision) and keeps the proceeded ack provisional
  until the outcome commits it (§3.4).
- **Nonce.** `_write_halt_condition_checkpoint` (modeled on `_write_gap_review_checkpoint`
  `campaign.py:1602-1647`) uses a monotonic `halt_condition_seq` in the filename
  `{stamp}__halt_condition_met__r{seq}.md` — a true per-pause nonce (so two conditions firing for
  the same milestone in the same second do not collide, and a stale decision file from an earlier
  halt is refused). The checkpoint body records `condition_id`, the evaluated `facts`, and the
  metric — human-readable + tamper-evident.
- **Resume — dedicated `_handle_resume` branch** (like `milestone_merge` `:2048-2098`); resolve +
  identity-bind (§3.5a). The branch is deliberately THIN — all freshness/drift handling lives at the
  redispatch EP-pre (§3.4), so both `proceed` and `abort` are trivial and crash-idempotent:
  - **`abort`** → clear `halt_condition_pending` + `halt_condition_provisional` (avoid terminal-state
    overlay residue [R0.7 NB]), then `_end("resolved_abort")`. (Not a suppression risk — the campaign
    ends — just tidy terminal state.)
  - **`proceed`** → set `pending.resolved = true`; add the condition's ack key to
    `halt_condition_provisional.keys` (§3.4); `_save`; audit `campaign_resume_dispatch`; follow the
    **barrier-free `ACT_REDISPATCH_FRESH` tail** (`campaign.py:2221-2231`) — return `"proceed"` with
    state PAUSED, cursor UNCHANGED, `pending` KEPT.
  The redispatch re-enters EP-pre, which owns the freshness gate (`_authority_fresh` block if stale)
  and the epoch-recheck: if `pending` is active and `pending.signed_scope_hash != live`, it flushes
  the ENTIRE provisional set + discards `pending` → every cascade condition re-fires in the current
  epoch (§3.4) [R0.4 B-1 / R0.5 B-1 / R0.6 B-1]; if hash-matches, the
  acked conditions are skipped (the unit dispatches, or the NEXT unacked matching condition fires —
  §6 canary a). **`proceed` NEVER uses
  `_commit_dispatch_resolution()`** [R0.2 B-3] — that barrier persists `STATUS_RUNNING`
  (`campaign.py:1026`) → a crash-recovery replay would call `run_unit(resume=True)`
  (`campaign.py:2372`) and the Driver RAISES `FileNotFoundError` on a never-started unit
  (`driver.py:3413-3417`); `ACT_REDISPATCH_FRESH` is deliberately barrier-free + crash-idempotent for
  this "unit not yet started" case (`campaign.py:2223-2228`). Cursor never advances and
  `_complete_milestone` is never called here → terminal-outcome stamping + merge gate
  (`campaign.py:1359-1370`) can never be bypassed [R0 B-3]. A crash after the `proceed` `_save`
  re-enters `_handle_resume` → re-binds the decision against the still-present `pending` → re-writes
  the idempotent provisional ack → re-proceeds [R0.3 B-2].

#### §3.5a Decision schema (additive `allOf`) + resolver identity binding

New `if/then` in `schemas/campaign-decision.schema.json` `allOf` (`:83-148`), mirroring
`completeness_gap_review` (`:115-129`):

```jsonc
{ "description": "halt_condition_met (Phase-3 autonomy.halt_conditions) — a human resolves a pre-set STRUCTURAL halt. proceed acknowledges the named condition for its scope and re-dispatches the same (not-yet-run) unit; abort ends the campaign. MUST echo condition_id (tamper-evident) + the per-pause checkpoint NONCE basename + milestone_id; MUST NOT carry subsprint_id (checkpoint is campaign-tier).",
  "if":   { "required": ["pause_reason"], "properties": {"pause_reason": {"const": "halt_condition_met"}} },
  "then": { "required": ["choice", "checkpoint", "milestone_id", "condition_id"],
            "properties": { "choice": {"enum": ["proceed", "abort"]},
                            "checkpoint": {"type": "string", "minLength": 1},
                            "condition_id": {"type": "string", "minLength": 1} },
            "not": { "required": ["subsprint_id"] } } }
```

`condition_id` is a new optional top-level property, forbidden for every other gate via the existing
else-strictness pattern (extend the `allOf` as the residue fields are gated `:130-147`). Resolver:
extend `make_campaign_decision_resolver.resolve` (`run_loop.py:574-676`) with a `halt_condition_met`
branch. It **fail-closes if `halt_condition_pending` is absent** [R0.4 NB-2] (a `halt_condition_met`
pause with no durable identity record is unresolvable, never bound loosely), then — after the base
checks (`campaign_id` `:597`, `pause_reason` `:599`, `checkpoint` basename EXACT `:601-603`) — asserts
`pending.checkpoint_basename == os.path.basename(state.pause_checkpoint)` (the nonce matches the live
pause) AND `decision["condition_id"] == pending.condition_id` AND `decision["milestone_id"] ==
pending.milestone_id` (read from the returned state, as `milestone_merge` does `:604-624`), and
rejects any `subsprint_id`. Any missing/mismatch → `_reject` (`:592-595`) → the gate re-pauses
(fail-closed). Because the nonce rolls when a condition re-fires, a stale-epoch decision (old nonce)
stops binding automatically (§3.4).

### §3.6 The five tighten-only invariants (R0 B-3 roadmap) — enforcement anchors

| # | Invariant | Mechanical enforcement |
|---|---|---|
| (a) | HALT + checkpoint only — never mutate a verdict / route / auto-resolve | schema has NO action/route/outcome field, `additionalProperties:false` at `items`+`when` (§3.1); evaluator output is an `Optional[Match]` consumed solely by the pause path (§3.4) |
| (b) | ids MUST NOT collide with the 9 `MANDATORY_CHECKPOINTS` or any checkpoint kind | `_check_halt_conditions` ERROR `halt_condition_id_collision` tests each id ∈ `MANDATORY_CHECKPOINTS` (`charter_validator.py:245-255`) ∪ `KNOWN_CHECKPOINTS` ∪ `{halt_condition_met}` — model `charter_validator.py:1219-1226`; **non-vacuous** because the id regex now allows underscores [R0 N-2]. Also ERROR on `_OVERRIDE_KEY_SUBSTRINGS` (`:260-266`) |
| (c) | metric/op/value-type from a CLOSED whitelist; unknown ⇒ ERROR | schema `enum` on metric/op (§3.1) + validator `halt_condition_unknown_metric`/`_op_mismatch`/`_value_type` cross-checked against the registry (§3.2) — belt-and-suspenders vs schema/validator drift |
| (d) | resume ONLY via the identity-bound decision file | dedicated resume branch reads the resolver only (§3.5a); the ack set is WRITTEN on resume, never READ as a resolver |
| (e) | predicate is a pure read-only fn over already-audited facts | `evaluate(...)` takes ctx+ack_set → `Optional[Match]`; never touches verdicts/checkpoints/audit; facts are plan-static (§3.2) |

`_check_halt_conditions` is registered in `validate_semantics` (`:1585-1601`), NO-OP when
`halt_conditions` absent/empty (precedent `:586-590`); new rule ids added to
`BackwardCompatTests.new_rules` (`test_charter_validator.py:1003-1008`).

### §3.7 Default-off / byte-identical (canary b)

`halt_conditions` absent/empty ⇒ validator NO-OP; EP-pre `evaluate` early-returns (no match path);
no `halt_condition_acks`/`halt_condition_provisional`/`halt_condition_pending`/`halt_condition_seq` serialized; `halt_condition_met`
in `KNOWN_CHECKPOINTS` but never emitted. Net: `run_unit` call, `campaign-state.json`, and the audit
ledger are byte-for-byte baseline.

---

## §4 Lever 4 — push-not-poll notifier (`notifications.on_pause`)

### §4.1 Charter schema (additive, top-level, default-off)

```jsonc
"notifications": {
  "type": "object", "additionalProperties": false,
  "description": "OPT-IN push notifier. DEFAULT OFF (absent ⇒ byte-identical). on_pause is an ARGV LIST (no shell ⇒ no injection surface) run on EVERY campaign pause (exit 10) with pause context injected as env vars. It is a TRUSTED, adopter-owned side-effecting hook (NOT sandboxed): the framework guarantees it is FAIL-SAFE (a failed/timed-out notifier never affects the pause or exit code), BOUNDED (timeout), fired only AFTER the pause is durably persisted, and AUDITED with REDACTED metadata. Governance integrity does not depend on notifier behavior — resume re-validates the decision file fail-closed.",
  "properties": {
    "on_pause": { "type": "array", "items": {"type": "string"}, "minItems": 1 },
    "timeout_seconds": { "type": "integer", "minimum": 1, "maximum": 60, "default": 10 }
  }
}
```

### §4.2 Execution — bounded, audited, FAIL-SAFE, NOT read-only [R0 B-4]

New `engine-kit/scheduling/pause_notifier.py :: notify_on_pause(charter, pause_ctx, audit_emit)`:

1. absent `notifications.on_pause` → return (no-op).
2. `child_env = {**os.environ, "AIDAZI_PAUSE_CAMPAIGN_ID":…, "AIDAZI_PAUSE_REASON":…,
   "AIDAZI_PAUSE_CHECKPOINT": basename, "AIDAZI_PAUSE_MILESTONE_ID":…, "AIDAZI_PAUSE_SUBSPRINT_ID":…}`
   — env injection (child env only), argv stays fixed.
3. `subprocess.run(list(argv), env=child_env, timeout=min(cfg.timeout_seconds,60),
   capture_output=True, text=True, check=False)` — argv list, `shell=False` (precedent
   `review_runner.py:173-182`, `monitor.py:133-140`).
4. total `try/except Exception` — a notifier crash/timeout is **swallowed** and NEVER propagates.
5. emit ONE `campaign_pause_notified` audit event with **REDACTED, secret-free** payload
   [R0 B-4]: `{argv0: basename(argv[0]), argc: len(argv), argv_sha256, exit_code, timed_out,
   duration_s, stdout_bytes, stderr_bytes, pause_reason, checkpoint}` — NO full argv (webhook
   URLs/tokens), NO env, NO stdout/stderr bodies (precedent `review_runner.py:274` secret-free row).

**Honest trust boundary [R0 B-4 / R0.2 N-1]:** the notifier is arbitrary user-authored code and CAN
touch the filesystem — it is NOT read-only/sandboxed, and the framework does NOT claim to contain a
buggy/hostile trusted hook. The framework guarantees are narrow and explicit: (i) fail-safe (a
notifier failure/timeout never affects the pause or exit code); (ii) it runs only AFTER the pause is
durably `_save`d (`campaign.py:2460,848`) and the exit-10 result is built, so it cannot race the
pause commit; (iii) the decision resolver re-validates a supplied decision file fail-closed on
resume (schema + identity + freshness, `run_loop.py:574-676`), so a **tampered decision file** can
NEVER loosen a gate — at worst the resume fails closed. **Out of scope (documented, not guaranteed):**
a trusted hook that corrupts the campaign's own `campaign-state.json`/plan files is trusted-hook
misuse; at worst `_validate_loaded_state` (`campaign.py:722-819`) fails the resume closed, but the
framework does not otherwise defend an adopter's repo against code the adopter itself installed.

### §4.3 Hook site + ordering

Called inside `run_campaign_entry` on the paused branch — after the result dict is built
(`run_loop.py:849-866`), when `exit_code == CAMPAIGN_EXIT_PAUSED`, before returning to `main`. Audit
via a NEW `audit.append_event(campaign_id, "campaign_pause_notified", …, path=<ledger>)` where
`<ledger>` is `audit.audit_path(campaign_id, os.path.join(home,"audit"))` — the same recipe used at
`run_loop.py:776-778` for the skills-preflight append. Fires on EVERY exit-10 pause (incl.
`halt_condition_met`) — canary (c). The
`--requirement` bootstrap pauses (`run_loop.py:1494-1526`) are a separate pre-campaign path; rev2
wires the campaign-run notifier only and DOCUMENTS the bootstrap path as a follow-up, so "fires on
every pause" is honestly scoped to the campaign runner.

### §4.4 Default-off / byte-identical

`notifications` absent ⇒ `notify_on_pause` returns immediately: no subprocess, no audit event, no
env — byte-identical.

---

## §5 Levers 2 & 3

### §5.1 Lever 2 — default posture (verify-only)

`templates/mission-charter.yaml:38` already ships `level: human_on_the_loop` (Track-4, 2026-06-29).
Phase-3 does not re-flip it and (tighten-only) leaves `clean_pass_auto_advance: false` (`:54`)
untouched. Deliverable: a one-line doc pointer; no code/template edit.

### §5.2 Lever 3 — judge calibration workflow (design/doc)

New `process/judge-calibration.md` (referenced from the existing `judge_calibration` charter block,
schema `:223-233`, template `:149-153`): **ledger format**
(`calibration/<role>-<provider>-<model>.calibration.json`: labeled_set_path, per-case
human/judge verdict + agreed, agreement_rate, threshold, flip_rate, flip_threshold, status,
calibrated_commit, `acceptance_input_fingerprint`); **thresholds** (reuse `agreement_threshold`
0.9 + `flip_threshold` 0.1, template `:151-152`; `calibrated` ⇒ `agreement_rate ≥ threshold` AND
`flip_rate ≤ flip_threshold` over ≥N labeled cases); **re-calibration triggers** (acceptance
role/provider/model change, skills/prompt fingerprint mismatch, staleness window,
`bad_case_manual_review`) → revert to `uncalibrated` ⇒ acceptance stays advisory (halts at
`advisory_acceptance_pass_signoff` — the constitution's own gate, unchanged); **unlock path**: only
`status: calibrated` permits `tooling.acceptance.mode: auto` + `fully_autonomous_within_budget`
(§1.7-C, documented not changed). Doc-only ⇒ subject to doc-reconciliation; no runtime/schema
change ⇒ `acceptance_input_hash`/LOAD-CLOSURE untouched.

---

## §6 Offline canary (proves a/b/c)

New `examples/halt-conditions-canary/` + `engine-kit/orchestrator/tests/test_halt_conditions_canary.py`
(offline, deterministic, mock adapters, NO real model; mirrors `test_run_loop_campaign.py`).

- **(a) pre-set condition halts with the right checkpoint + facts — TWO sequential pauses**
  [R0.2 B-4]. Charter with `halt_conditions: [{id: hot-milestone, when:{metric: milestone_id, op:
  in, value: [m2]}}, {id: gate-e2e, when:{metric: milestone_functional_acceptance, op: '==', value:
  browser_e2e}}]`. Scripted 2-milestone plan (m1 static; m2 browser_e2e — including a variant where
  m2 INHERITS browser_e2e from the charter, exercising the resolved-class extractor [R0.2 B-1]).
  Because ack is **per-condition**, both conditions match m2 and fire in declaration order:
  1. m1 runs clean → at m2's first dispatch (after `_authority_fresh` passes) the campaign pauses
     `exit 10`, `pause_reason == halt_condition_met`, checkpoint `..__halt_condition_met__r1.md`,
     body records `condition_id: hot-milestone` + `facts.milestone_id == m2`.
  2. an identity-bound `proceed` (echoing `condition_id: hot-milestone` + `checkpoint` (r1) +
     `milestone_id: m2`, no `subsprint_id`) resumes → EP-pre re-evaluates → `hot-milestone` is acked,
     `gate-e2e` now fires → SECOND pause `..__halt_condition_met__r2.md`,
     `facts.milestone_functional_acceptance == browser_e2e` (proves the nonce seq r1≠r2).
  3. a second `proceed` (condition_id: gate-e2e, checkpoint r2) resumes → both acked → m2 dispatches
     → campaign completes `exit 0`.
  Assert a WRONG decision (wrong `condition_id`, present `subsprint_id`, or a stale r1 basename at
  the r2 pause) is REFUSED and the gate re-pauses (§3.5a). Assert milestone-scoped acks make each
  condition fire ONCE per milestone (no re-pause on a later m2 sub-sprint). **Ack write-gate +
  crash-idempotence variants** [R0.3/R0.4/R0.5/R0.6 B-1]: (i) FIRST-HALT-DRIFT [R0.6 B-1] — at the
  FIRST halt (r1, before any proceed) mutate + re-sign the plan; proceed; assert the redispatch EP-pre
  flushes and r1 re-arms with a FRESH nonce (the halt-time epoch stamp on `pending` catches it —
  the drift is between the first halt and its proceed); (ii) FRESHNESS-BLOCK [R0.6 B-1] — proceed
  while the plan is stale (unsigned drift); assert EP-pre `_authority_fresh` blocks for re-sign
  (`campaign_plan_signoff`), and after re-sign the halt-time hash mismatches the new epoch → flush +
  re-arm; (iii) AFTER-PROCEED-DRIFT — proceed past r1, then re-sign before the redispatch; assert
  flush + re-arm; (iv) MULTI-DRIFT [R0.5 B-1] — proceed past r1 (`hot-milestone`) AND r2 (`gate-e2e`)
  so BOTH are provisional, then re-sign before the unit dispatches; assert BOTH re-arm (r1's ack is
  flushed too — NOT wrongly permanent); (v) RESTAMP — after the unit DISPATCHES (cascade committed
  permanent), simulate an `engine_restamp` (signed hash advances, facts unchanged) and assert the
  committed acks SURVIVE (no re-pause); (vi) CRASH — reload the persisted PAUSED state after the
  proceed `_save` but before the redispatch records progress, and assert replay re-binds the same
  decision idempotently (`pending` present, provisional set unchanged) and completes; (vii) DIGEST —
  change a condition's `when` under the same `id` and re-sign; assert it re-fires (new
  `condition_digest` ⇒ new key), while a `note`-only edit does not.
- **(b) absent conditions ⇒ byte-identical [R0 N-3].** Capture a golden `campaign-state.json` +
  audit-ledger byte-image from a run of the SAME scripted plan with a charter that has NO
  `halt_conditions`/`notifications`, on the base tree `6a2078a` (checked-in as a fixture,
  regeneration script recorded). Run the identical scenario on the Phase-3 build and assert a
  **byte-diff == empty** vs the golden; assert `halt_condition_acks`/`halt_condition_provisional`/`halt_condition_pending`/
  `halt_condition_seq` never appear in serialized state. (Deterministic clock + mock adapters make
  the bytes reproducible, per `test_run_loop_campaign.py`.)
- **(c) notifier fires on every pause.** `notifications.on_pause: ["<local-script>"]` (appends
  `$AIDAZI_PAUSE_REASON` to a temp file). Assert one line per pause + one `campaign_pause_notified`
  audit event per pause with redacted payload. Variant: the script exits 1 / sleeps past
  `timeout_seconds` — assert the pause, exit code, and `halt_condition_met` flow are UNCHANGED
  (fail-safe) and the audit records `timed_out`/nonzero `exit_code`.

Evidence: `archive/2026-07-09-phase3-halt-conditions-canary-evidence.md`.

---

## §7 Impact inventory, tests, gotchas

**Files (all additive):** `schemas/mission-charter.schema.json` (`autonomy.halt_conditions`
`:44-116`; top-level `notifications` before `:370`); `schemas/campaign-decision.schema.json` (one
`allOf` block + `condition_id` + else-strictness, `:83-148`); `engine-kit/orchestrator/halt_metrics.py`
(NEW registry); `engine-kit/orchestrator/campaign.py` (`halt_condition_met` ∈ `CAMPAIGN_CHECKPOINTS`
`:146-155`; `halt_condition_acks`/`halt_condition_provisional`/`halt_condition_pending`/`halt_condition_seq` conditional state
`:355-437` (incl. `halt_condition_acks` permanent + `halt_condition_provisional` whole-cascade set
keyed by `condition_digest`, flushed at EP-pre on drift via `_live_signed_scope_hash` `:1498-1508`,
promoted en masse at the unit-outcome `_save`; no permanent-ack invalidation); EP-pre eval in
`_drive_milestones` AFTER `_authority_fresh` (between `:2399` and `:2406`); `halt_condition_pending`
(carrying `resolved`+`condition_digest`+`signed_scope_hash`) cleared only in the unit-outcome `_save`
(`:2438`/`:2460`/`_complete_milestone` `:1359-1370`); resolved-class extractor
via `resolve_functional_acceptance` `:2581-2593`; `_write_halt_condition_checkpoint` (nonce seq);
barrier-free proceed via `ACT_REDISPATCH_FRESH` `:2221-2231`; dedicated `_handle_resume` branch
`:2003-2242`); `engine-kit/validators/charter_validator.py`
(`_check_halt_conditions` + `_check_notifications` in `validate_semantics` `:1585-1601`);
`engine-kit/scheduling/run_loop.py` (resolver `halt_condition_met` branch `:574-676`;
`notify_on_pause` hook `:849-866`); `engine-kit/scheduling/pause_notifier.py` (NEW);
`process/judge-calibration.md` (NEW); `process/campaign-loop.md` + charter docs (halt_conditions +
notifications sections); `templates/mission-charter.yaml` (commented default-off examples);
`examples/halt-conditions-canary/` + tests.

**Tests (positive + negative each):** validator (id-collision **non-vacuous** with an underscore
id, unknown metric, op/value-type mismatch, override-substring, notifications argv/timeout;
NO-OP-when-absent; valid-passes; `new_rules` backward-compat); campaign inventory (halt_condition_met
classified + disjoint, direct test); decision-schema gate-specificity; resolver identity binding
(condition_id/nonce/milestone_id/no-subsprint); evaluator units (each metric/op, ack scoping,
EP-pre once-per-scope); pause_notifier (argv, timeout, fail-safe, redacted secret-free audit); canary.

**Gotchas (Phase-1/2):** new checkpoint kind → exactly one set (`CAMPAIGN_CHECKPOINTS`), guarded by
disjointness + a DIRECT membership test (NOT the partial AST test [R0 B-5]); additive schema
(`additionalProperties:false` at `autonomy` `:43` + root `:8` ⇒ into `properties`); decision-schema
↔ resolver alignment; doc-reconciliation lockstep on template/process edits (keep the 9-checkpoint
bypass language intact); `_sources.yaml` sha256 refresh IF any governance/role-card doc is touched
(Phase-3 touches NONE — additive charter+campaign+process only); golden prompt fingerprint
`orchestrator/test-prompts.json` unchanged (no role-prompt bytes touched — assert hashes stable);
RTK/git (verify via `git ls-remote`; `rev-parse` for tips; SSH push needs
`dangerouslyDisableSandbox`); suite `cd engine-kit && python3.12 -m pytest` ~1721 pass/~10 skip/**1
pre-existing README doc-reconciliation red** (PR#8 leftover — do NOT fix).

---

## §8 Acceptance criteria & sequencing

**Done (roadmap §4 + F-5 — nothing claimed until evidence exists):** (1) offline canary GREEN on
(a)/(b)/(c) + evidence doc; (2) suite green (~1721; the one pre-existing README red unchanged);
kernel-coverage / load-closure / doc-reconciliation gates untouched-green; (3) every §3.6 invariant
has a passing positive+negative test; (4) Codex impl gates R1 (schema+validator+decision), R2
(campaign eval+resume+notifier), R3 (whole-scope) each APPROVE (0 blocking); (5) lever 2 verified
already-landed; lever 3 doc committed.

**Sequencing:** design gate CLOSED — Codex R0→R0.7, **R0.7 APPROVE (0 blocking, 2026-07-09**;
verdict `/tmp/aidazi-phase3-r07/verdict.txt`) after folding every `[R0 B-#]…[R0.6 B-#]`. Next:
commit design → phased impl commits (R1/R2 each) → canary + evidence → R3 → push + `gh pr create`
(human merge). Nothing weakens a MANDATORY_CHECKPOINT, acceptance authority (§1.7-C), signed-scope
freshness (Δ-19 F1/T2-A), or the OW-M3 E2E mandate. (Roadmap §4 couples the default-posture flip
with `clean_pass_auto_advance: true`; this design intentionally leaves it `false` — tighten-only,
§5.1 — a deliberate, Codex-affirmed deviation, not an omission.)
