# Track-2 hardening cycle — universal F1 freshness + authoritative signed-input coverage (design spec, rev3)

- **Date:** 2026-06-30
- **Branch:** drafted on `acceptance-efficacy-e2e-mandate` (worktree `../aidazi-acceptance`, off `main` `2f0095d`); **implementation belongs to its own Track-2 branch** with its own Codex gate.
- **Status:** DESIGN SPEC rev3 — R1 `REVISE` (B1–B5) fixed in rev2 + Codex-confirmed RESOLVED in R2; rev3 redesigns **TD6** (R2 found the dual-hash approach FLAWED: a sequence bypass + dual-hash divergence) and folds R2 nits N1–N3. Reviews: `archive/2026-06-30-track2-codex-review-r1.md`, `-r2.md`. **Implementation blocker for OW-M3** (`archive/2026-06-30-ow-m3-mandatory-e2e-spec.md` §5); home for the pre-existing Track-2 authz gap ([[track2-gap-followup-signing-followup]]).
- **Thesis:** A signed campaign plan's authority must be re-validated at every act-on-signed-scope site, and every authority-bearing field must be inside the **single** signed hash — while engine-authored in-authority mutations (the `deliver_followup` insertion) advance that single epoch with provenance rather than being excluded from it.

## Review disposition
**R1 (REVISE) → R2-confirmed RESOLVED:** B1 isolation/merge authority bound; B2 `gap_followup` field set corrected (`max_subsprints`+`max_no_progress_rounds`; `budget.*` separate); B3 gap-followup outer loop re-pauses on stale; B4 freshness-block overlay preserves the original pause; B5 explicit pre-irreversible placement.
**R2 (REVISE) → fixed in rev3:**
- **TD6 redesign (R2 NEW-BLOCKING #1 + #2):** the rev2 dual-hash (`compute_authority_hash` excluding `subsprint_sequence`) is REPLACED by a **single `signed_scope_hash` + an engine re-stamp of authorized deltas** (§2.1-TD6). Closes the sequence bypass (the live sequence resolves the dev-prompt, `driver.py:1455-1472,1706-1728`) and the dual-hash divergence (scope_report `280-293`, pending-remediation `1670-1677` keep using the one hash).
- **N1:** the B4 overlay is DURABLE campaign-state (schema + dataclass field), not in-memory (§2.1).
- **N2:** `branch_name_template` + `worktree_root` → BIND (§2.2).
- **N3:** `raise_cap` (budget raise on resume) must require re-sign, not exclusion (§2.2/§6).

---

## 0. One-sentence design

> Make a single-hash **F1 freshness check** a universal precondition before every act-on-signed-scope site (every dispatch, every resume `proceed`, AND the gap-followup outer loop); accommodate the one legitimate engine mutation (`deliver_followup` insertion) by **re-stamping the single signed epoch with provenance after validating the diff is exactly that authorized insertion**; and bind every authority-bearing plan field into that one hash. Additive: F1-inactive plans byte-identical.

---

## 1. The holes (confirmed against `2f0095d`)

### 1.1 Hole A — freshness revalidation is not universal
`signoff_status()` (campaign.py:2308-2323) ⟹ `signed` iff stored `signed_scope_hash` == live recompute. Enforced at initial start (1894-1907); resume-from-`campaign_plan_signoff` ONLY (1692-1697); pending gap-remediation dispatch (1511, 1529, epoch at 1670-1677). **NOT** enforced at: each milestone dispatch (`_drive_milestones` reads LIVE `functional_acceptance`/`seq`, 1944, 1992-2002); the non-`campaign_plan_signoff` resume branches (1716-1743, 1744-1764, 1702-1715, 1772-1776, 1779-1786, 1816-1834); and **the gap-followup outer loop (R1 B3)** — `_gap_followup_eligible` → `not_fresh_signed` (1166-1167) ⟹ `_gap_followup_round` → `GAP_DONE` (1594-1597) ⟹ `run()` → `STATUS_DONE` (1930-1936): a stale plan at backlog exhaustion silently FINISHES.

### 1.2 Hole B — signed-input coverage is incomplete (R1 B1/B2 corrected; R2-confirmed complete)
`_signed_scope_H` (2214-2226) omits live-read authority fields: `gap_followup.{max_subsprints,max_no_progress_rounds}` (1096-1101, 1258, 1280-1283); top-level `budget.*` (602, 784-792, 1781); isolation/merge — `milestone_isolation.*`, legacy `isolation_strategy`, `trunk_branch` (602-619, 821-826, 885-895, 955-966) → post-sign edits can redirect the merge target or DISABLE the human merge gate while staying signed. (R2 confirmed `merge_policy`/`module_locks` are schema-only, not branched on — no further misses.)

---

## 2. Deliverables

### 2.1 T2-A — universal single-hash F1 freshness gate
- **One read-only helper** `_authority_fresh()` returning whether `signoff_status() == "signed"` (the SINGLE existing hash — NO parallel hash). F1-active only (`f1_required`, 2264-2274); non-F1 ⟹ always-true (byte-identical).
- **TD6 — engine-authored deltas advance the ONE epoch (replaces rev2's dual-hash):** `subsprint_sequence` STAYS inside `signed_scope_hash` (it resolves the dispatched `subsprint_id` → the `compact/<id>-dev-prompt.md` / decompose-plan entry, `driver.py:1455-1472,1706-1728`; excluding it was a bypass — R2 B#1). The ONE legitimate mid-campaign mutation, the `deliver_followup` insertion at cursor+1 (detected via `followup_baseline_seq`, 1751-1757), is handled by an **engine re-stamp**: on that authorized insertion the engine recomputes `signed_scope_hash` over the new sequence and records provenance (`engine_authored_delta: {milestone_id, inserted subsprint_id, authorizing checkpoint}`) — **GUARD: the re-stamp is permitted ONLY when the live-vs-signed envelope diff is EXACTLY that one baseline-detected insertion and nothing else** (any other delta — a Customer authority field, a non-baseline sequence/prompt-id edit — REFUSES the re-stamp ⟹ stays `stale` ⟹ blocked). Net: a single hash all consumers already use (scope_report `280-293`, `_gap_followup_eligible`, pending-remediation epoch `1670-1677` — NO divergence, R2 B#2), no bypass, and `deliver_followup` proceeds. It is NOT a human re-sign (no new `signed_by_human` decision); it is an epoch advance under the `deliver_followup` authority the Customer already signed.
- **Invoke `_authority_fresh()` at EVERY act-on-signed-scope site:** before each `run_unit` dispatch (`_drive_milestones`, before 1998); on EVERY `proceed` of `_handle_resume`; and in the gap-followup outer loop — `_gap_followup_round` must split `not_fresh_signed` (⟹ re-pause for re-sign) from `no_gap` (⟹ `GAP_DONE`), fixing 1594-1597 so `run()` never `STATUS_DONE`s a stale plan.
- **B4 — DURABLE freshness-block overlay (N1):** when a mid-run gate detects drift, BLOCK for re-sign while PRESERVING the original `pause_reason`/`pause_checkpoint`, so post-re-sign the campaign resumes the ORIGINAL gate (mechanism-A resume, `deliver_followup_required`, `milestone_merge`, decision-bound checkpoints). The overlay is **persisted campaign-state** (new field on `campaign-state.schema.json:7-14` + `CampaignState` round-trip, campaign.py:334-404), NOT an in-memory flag, with crash-replay tests — else a crash mid-block loses the original gate.
- **B5 — placement before irreversible actions:** before `run_unit` (≈1998); for `milestone_merge` BEFORE `_execute_milestone_merge()` (1728) and the cursor advance (1734); for cursor-advancing resume BEFORE `_stamp_milestone_outcome()` (1825) / cursor mutation (1818/1828) / `_commit_dispatch_resolution()` (1830); for gap remediation BEFORE persisting `pending_remediation`. The check is READ-ONLY, OUTSIDE every §3.5c barrier (1730-1735, 1808-1834) — it can only convert a would-be `proceed`/`GAP_DONE` into a durable blocked-pause; never half-advances a cursor.

### 2.2 T2-B — authoritative signed-input coverage (R2-confirmed complete inventory)
Bind the authority fields into the SINGLE `H` (`_signed_scope_H`) + stored `scope_envelope` (`compute_scope_envelope`, 2202-2211); **N1-style lockstep:** `signoff_snapshot_authentic()` (≈2280-2293) must reconstruct the SAME `H` from the stored envelope.

| Field | Read-site | Gates | in-H? |
|---|---|---|---|
| `gap_followup.max_subsprints` / `max_no_progress_rounds` | 1096-1101, 1258, 1280-1283 | auto-remediation extent / non-progress tolerance | **BIND** |
| `budget.{max_subsprints,max_total_spawns,max_wall_clock_minutes}` | 602, 784-792, 1781 | campaign_budget_exhausted | **BIND** (and see `raise_cap`, N3 below) |
| `trunk_branch` | 602-619, 955-966 | merge TARGET | **BIND** |
| `milestone_isolation.merge_prompt_at_close` | 602-619, 885-895 | the human merge gate (§1.7-D) | **BIND** |
| `milestone_isolation.cleanup_policy` | 602-619, 955-966 | worktree delete/keep | **BIND** |
| `milestone_isolation.default_strategy` + per-milestone/legacy `isolation_strategy` | 602-619, 821-826 | branch vs worktree | **BIND** |
| `milestone_isolation.branch_name_template` + `worktree_root` (N2) | 602-619 | side-effect location / operator commands | **BIND** |
| `subsprint_sequence` | 1944, 2195; resolves dev-prompt `driver.py:1455-1472` | execution + dev-spec selection | **IN H**; engine-authored insertion advances the epoch (TD6) |
| `autonomy.approved_scope` (N3-R1) | charter | — | covered by `charter_hash`; not a plan field |

- **N3 — `raise_cap` requires re-sign:** since `budget.*` is now in `H`, the `campaign_budget_exhausted` resume's `raise_cap` (1779-1786, which today mutates `self.budget` in memory at 1781) must go through a Customer **re-sign** of the raised budget — NOT an in-memory bump — or it would proceed `stale`/unsigned. The raised cap is a signed scope change.
- Any field left out of `H` carries a one-line non-authoritative rationale (no silent omission). R2 swept `campaign.py` and found no further live-read authority field.

## 3. Non-goals / boundaries
- ❌ NOT a state-machine redesign / pause-taxonomy change — T2-A adds a read-only precondition + a durable overlay + the authorized-delta re-stamp; T2-B extends the one hash input.
- ❌ NOT new authority — re-pausing for re-sign is the EXISTING Customer gate; the engine re-stamp only advances the epoch for an already-authorized `deliver_followup` delta (with provenance), it never confirms Customer scope.
- ❌ NOT OW-M3's `surface`/class logic. ❌ NOT a change to non-F1 (legacy) plan behavior.

## 4. Interaction with OW-M3
T2-A turns OW-M3's hash-bound `covered_req_surfaces`/resolved-mode into **blocking** at every dispatch/resume and closes the gap-followup-finishes-stale path (B3). T2-B closes the parallel budget/gap_followup/isolation holes. **Sequencing:** this cycle ships + earns its own Codex APPROVE → THEN OW-M3 implementation unblocks.

## 5. Risks
- **Crash-idempotency regression** (highest) — read-only checks outside the durable barriers + a DURABLE overlay (N1) + replay tests at each gate.
- **TD6 re-stamp correctness** — the re-stamp must fire ONLY on the baseline-detected `deliver_followup` insertion with an exact-diff guard; a bug that re-stamps any other diff would silently launder a Customer change. The exact-diff guard + provenance + tests are load-bearing; the next Codex round must validate them.
- **Migration churn** — `budget`/`gap_followup`/isolation entering `H` makes existing signed plans carrying those blocks `stale` until re-signed (intentional); the re-pause message names the newly hash-bound field class.
- **Over-pausing** — a still-fresh plan (incl. right after a legitimate `deliver_followup` re-stamp) must never be flagged drift; canonical-JSON determinism + a "no-op when fresh" test on every gate.

## 6. Decisions for the Codex gate
- **TD1 (in-H set)** — §2.2 table (R2-confirmed complete). Codex re-checks completeness.
- **TD2 (stale UX)** — durable freshness-block OVERLAY preserving the original pause (N1).
- **TD3 (F1-gating)** — NEW mid-run gates F1-gated; EXISTING legacy `campaign_plan_signoff` unchanged. Confirm byte-identical for non-F1.
- **TD4 (placement)** — §2.1-B5 before/after per gate; confirm no double-pause / stranded cursor.
- **TD5 (migration)** — one-time re-sign once new fields enter `H`; actionable message naming the field class.
- **TD6 (engine-authored delta — THE CRUX, redesigned)** — single `signed_scope_hash`; `subsprint_sequence` stays in it (no bypass); the `deliver_followup` insertion advances the one epoch via an engine re-stamp **guarded by an exact-diff check** (only the baseline-detected insertion) + provenance; all consumers keep the one hash (no divergence). Codex must validate the exact-diff guard admits no other change and the re-stamp is never a disguised Customer re-sign.

## 7. Test plan
- **T2-A:** each resume reason + per-dispatch gate + gap-followup outer loop: fresh ⟹ proceeds byte-identical; post-pause authority edit (downgrade `functional_acceptance`; mutate `covers_req_ids`/`surface`; raise `budget`/`gap_followup`; flip `merge_prompt_at_close`/`trunk_branch`) ⟹ blocked for re-sign with the ORIGINAL pause preserved (durable across crash); stale at backlog exhaustion ⟹ re-pause not `STATUS_DONE` (B3); non-F1 ⟹ byte-identical.
- **TD6:** legitimate `deliver_followup` insertion ⟹ engine re-stamp, proceeds, provenance recorded, all consumers see `signed`; a NON-baseline sequence/prompt-id swap or any other-field diff alongside ⟹ re-stamp REFUSED ⟹ blocked (bypass closed); scope_report + pending-remediation see the one re-stamped hash (no divergence).
- **T2-B:** raise `gap_followup`/`budget` / flip `trunk_branch`/`merge_prompt_at_close` post-signoff ⟹ stale ⟹ blocked; `raise_cap` ⟹ requires re-sign (N3); `signoff_snapshot_authentic` reconstructs the new `H`.
- **Crash-idempotency:** replay at each gate + with the durable overlay set — no double-advance/double-pause; §3.5c barriers unaffected.
- **OW-M3 cross-check (after this lands):** post-sign `surface` flip while paused ⟹ blocked.

## 8. Citations (worktree/main `2f0095d`)
| Claim | Anchor |
|---|---|
| `signoff_status` = signed iff stored==live | `campaign.py:2308-2323` (`_signoff_status` `1000-1011`) |
| freshness at start / resume-only-signoff / gap-remediation precedent + epoch | `campaign.py:1894-1907` / `1692-1697` / `1511,1529,1670-1677` |
| other resume branches proceed without recheck | `campaign.py:1716-1743,1744-1764,1702-1715,1772-1776,1779-1786,1816-1834` |
| dispatch reads LIVE functional_acceptance/seq | `campaign.py:1944,1992-2002` |
| gap-followup outer loop finishes on stale (B3) | `campaign.py:1166-1167,1594-1597,1930-1936` |
| `subsprint_sequence` in envelope; resolves dev-prompt (TD6 bypass) | `campaign.py:2195`; `driver.py:1455-1472,1706-1728` |
| `deliver_followup` insertion detected via baseline | `campaign.py:1744-1764` (`followup_baseline_seq` 1751-1757) |
| consumers using the single hash (divergence to avoid) | `scope_report.py:280-293,342-347,474-510`; `campaign.py:1529-1536,1670-1677` |
| `H` excludes top-level authority fields | `campaign.py:2214-2226` |
| gap_followup / budget / isolation live read-sites | `campaign.py:1096-1101,1258,1280-1283 / 602,784-792,1781 / 602-619,821-826,885-895,955-966` |
| overlay durability (strict state schema) | `campaign-state.schema.json:7-14`; `campaign.py:334-404` |
| snapshot-auth reconstruction / stored envelope | `campaign.py:~2280-2293,2202-2211` |
| §3.5c durable barrier (placement) / F1 opt-in | `campaign.py:1730-1735,1808-1834 / 2264-2274` |
