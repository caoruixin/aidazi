# Track-2 hardening cycle — universal F1 freshness + authoritative signed-input coverage (design spec, rev2)

- **Date:** 2026-06-30
- **Branch:** drafted on `acceptance-efficacy-e2e-mandate` (worktree `../aidazi-acceptance`, off `main` `2f0095d`); **implementation belongs to its own Track-2 branch** with its own Codex gate.
- **Status:** DESIGN SPEC rev2 — addresses Codex gpt-5.5 xhigh R1 `REVISE` (`archive/2026-06-30-track2-codex-review-r1.md`): B1–B5 + nits N1–N3 resolved, plus a self-surfaced engine-authored-mutation constraint (TD6). **Implementation blocker for OW-M3** (`archive/2026-06-30-ow-m3-mandatory-e2e-spec.md` §5); home for the pre-existing Track-2 authz gap ([[track2-gap-followup-signing-followup]]).
- **Thesis:** A signed campaign plan's **Customer authority** must be re-validated at every point the engine acts on it, and every authority-bearing field must be inside the signed hash `H` — while engine-authored in-authority mutations (deliver_followup, remediation) must NOT trip the gate.

## rev2 disposition of Codex R1 (8/9 citations OK; #8 corrected)
- **B1 (inventory misses isolation/merge authority)** — FIXED §2.2 (added `trunk_branch`, `milestone_isolation.*`, `isolation_strategy`).
- **B2 (`gap_followup` field set wrong)** — FIXED §1.2/§2.2 (corrected to `max_subsprints` + `max_no_progress_rounds`; `budget.*` classified separately).
- **B3 (gap-followup outer loop finishes on stale)** — FIXED §1.1/§2.1 (the missed site; stale ⟹ re-pause, not `GAP_DONE`).
- **B4 (mid-run stale UX erases original pause)** — FIXED §2.1 (freshness-block OVERLAY preserves the original `pause_reason`/checkpoint).
- **B5 (placement vs irreversible actions)** — FIXED §2.1 (explicit before/after per gate).
- **TD6 (NEW, self-surfaced):** the freshness gate must compare a **Customer-authority subset** that EXCLUDES engine-mutated `subsprint_sequence`, or it breaks `deliver_followup`. §2.1/§6.
- Nits: N1 (snapshot-auth reconstruction) §2.2; N2 (TD3 wording) §6; N3 (`autonomy.approved_scope` is a charter field — DROPPED from the inventory).

---

## 0. One-sentence design

> Make a **Customer-authority freshness check** a universal precondition before every act-on-signed-scope site (every dispatch, every resume `proceed`, AND the gap-followup outer loop), comparing an authority subset that excludes engine-mutated execution fields; and make `H` cover every authority-bearing plan field (budget, gap_followup bounds, isolation/merge). Additive: F1-inactive plans byte-identical.

---

## 1. The holes (confirmed against `2f0095d`)

### 1.1 Hole A — freshness revalidation is not universal
`signoff_status()` (campaign.py:2308-2323) ⟹ `signed` iff stored `signed_scope_hash` == live recompute. Enforced at: initial start (1894-1907); resume-from-`campaign_plan_signoff` ONLY (1692-1697); pending gap-remediation dispatch (1511, 1529). **NOT** enforced at:
- **each milestone dispatch** — `_drive_milestones` calls `run_unit` with LIVE `functional_acceptance`/`seq` (1944, 1992-2002), no gate;
- **non-`campaign_plan_signoff` resume branches** — `deliver_followup_required` (1744-1764), `milestone_merge` (1716-1743), `GAP_REVIEW` (1702-1715), mechanism-A driver-resume (1772-1776), `campaign_budget_exhausted` (1779-1786), advancing dispatches (1816-1834) all return `proceed` with no `_signoff_status()` recheck;
- **the backlog-exhausted gap-followup outer loop (R1 B3 — the worst miss)** — `_gap_followup_eligible` returns `not_fresh_signed` (1166-1167) ⟹ `_gap_followup_round` returns `GAP_DONE` (1594-1597) ⟹ `run()` writes `STATUS_DONE` (1930-1936). **A stale plan at backlog exhaustion silently FINISHES the campaign** instead of re-pausing for re-sign.

### 1.2 Hole B — signed-input coverage is incomplete (R1 B1/B2 corrected)
`_signed_scope_H` (2214-2226) = `{version, campaign_id, goal, charter_ref, charter_hash, milestones[_envelope_milestone…]}`. Live-read authority fields NOT in `H`:
- **`gap_followup` bounds** — `_gap_followup_cfg` reads `max_subsprints` + `max_no_progress_rounds` live (1096-1101); they gate auto-remediation extent (1258, 1280-1283). *(Correction: `_over_budget` at 786 reads `self.budget`, NOT `gap_followup`; `gap_followup` has no `max_total_spawns`/`max_wall_clock_minutes` — those are `budget` fields.)*
- **top-level `budget`** — `self.budget = plan.get("budget")` (602), gates `campaign_budget_exhausted` via `_over_budget` (784-792), raisable on resume (1781). Post-sign raise ⟹ more autonomous work than signed.
- **isolation/merge authority** — `milestone_isolation` (`merge_prompt_at_close`, `cleanup_policy`, `default_strategy`, …), legacy `isolation_strategy`, `trunk_branch` (602-619); per-milestone `isolation_strategy` (821-826); the merge gate honors `merge_prompt_at_close` (885-895) and `_execute_milestone_merge` uses `trunk_branch` + `cleanup_policy` (955-966). Post-sign edits can **redirect the merge target or DISABLE the human merge gate (§1.7-D)** while `signed_scope_hash` stays signed.

---

## 2. Deliverables

### 2.1 T2-A — universal Customer-authority freshness gate
- **One read-only helper** `_authority_fresh() -> bool` comparing the **authority subset** (TD6) of the LIVE plan against the signed snapshot. F1-active only (`f1_required`, 2264-2274); non-F1 ⟹ always-true (byte-identical).
- **TD6 — the comparison basis (critical):** the gate compares a **Customer-authority subset**, NOT full `H`. It EXCLUDES `subsprint_sequence` (the one field `deliver_followup` legitimately inserts into mid-campaign, 1757; envelope field 2195) so an engine-authored in-authority insertion does NOT read as drift, while it INCLUDES every authority field: milestone identity, `covers_req_ids`, `covered_req_surfaces` (OW-M3 B1), `resolved_functional_acceptance`, `depends_on`, `acceptance_bar`, `budget`, `gap_followup` bounds, isolation/merge fields. Recommended impl: a dedicated `compute_authority_hash()` (the H-minus-subsprint_sequence-plus-top-level-authority subset), compared live-vs-signed; the full `signed_scope_hash` stays the sign artifact. (Gap remediation already avoids mutating the plan — 1420 — so it is unaffected.)
- **Invoke at EVERY act-on-signed-scope site:** before each `run_unit` dispatch (`_drive_milestones`, before 1998); on EVERY `proceed` of `_handle_resume`; and in the **gap-followup outer loop** — `_gap_followup_round` must distinguish `not_fresh_signed` (⟹ re-pause for re-sign) from `no_gap` (⟹ legitimately `GAP_DONE`) (fix at 1594-1597 / 1166-1167 so `run()` never `STATUS_DONE`s a stale plan).
- **B4 — stale UX = a freshness-block OVERLAY, not a pause-reason overwrite:** when a mid-run gate detects drift, it BLOCKS for re-sign while PRESERVING the original `pause_reason`/`pause_checkpoint`, so after the Customer re-signs the campaign resumes the ORIGINAL gate (mechanism-A driver-resume, `deliver_followup_required`, `milestone_merge`, decision-bound checkpoints). Implement as an overlay flag/state layered over the existing pause (or stash-and-restore the original `(reason, checkpoint)`), NOT by rewriting `pause_reason` to `campaign_plan_signoff`.
- **B5 — explicit placement before irreversible actions:**
  - `_drive_milestones`: before `run_unit` (≈1998) and before the decompose/budget pauses that read the live plan.
  - `milestone_merge` resume: BEFORE `_execute_milestone_merge()` (1728) AND before the cursor advance (1734).
  - cursor-advancing resume (`ACT_ADVANCE_*`): BEFORE `_stamp_milestone_outcome()` (1825), cursor mutation (1818/1828), and `_commit_dispatch_resolution()` (1830).
  - gap remediation: BEFORE persisting `pending_remediation`.
  - The check is READ-ONLY and sits OUTSIDE every §3.5c durable barrier (1730-1735, 1808-1834) — it can only convert a would-be `proceed`/`GAP_DONE` into a durable, replay-safe blocked-pause; it never half-advances a cursor.

### 2.2 T2-B — authoritative signed-input coverage (corrected inventory)
Bind the authority-bearing fields into `H` (`_signed_scope_H`) and the stored `scope_envelope` (`compute_scope_envelope`, 2202-2211); **N1:** `signoff_snapshot_authentic()` (≈2280-2293) must reconstruct the SAME `H` from the stored envelope, or stale-rendering/prior-coverage auth breaks — update it in lockstep.

| Field | Read-site | Gates | in-H? |
|---|---|---|---|
| `gap_followup.max_subsprints` | 1096-1101 | auto-remediation count | **BIND** |
| `gap_followup.max_no_progress_rounds` | 1096-1101, 1280-1283 | non-progress tolerance | **BIND** |
| `budget.{max_subsprints,max_total_spawns,max_wall_clock_minutes}` | 602, 784-792, 1781 | campaign_budget_exhausted | **BIND** |
| `trunk_branch` | 602-619, 955-966 | merge TARGET | **BIND** |
| `milestone_isolation.merge_prompt_at_close` | 602-619, 885-895 | the human merge gate (§1.7-D) | **BIND** |
| `milestone_isolation.cleanup_policy` | 602-619, 955-966 | worktree delete/keep | **BIND** |
| `milestone_isolation.default_strategy` + per-milestone `isolation_strategy` + legacy top-level | 602-619, 821-826 | branch vs worktree isolation | **BIND** |
| `milestone_isolation.{branch_name_template,worktree_root}` | 602-619 | naming/path only | classify (recommend bind for simplicity; else justify out) |
| `subsprint_sequence` | 1944, 2195 | execution detail, engine-mutated (deliver_followup) | **OUT** of the authority subset (TD6) — not Customer scope |
| `autonomy.approved_scope` (N3) | charter | — | already covered by `charter_hash`; NOT a plan field |

Impl MUST do an exhaustive sweep to confirm no OTHER live-read plan field gates authority; any left out of `H` gets a one-line non-authoritative rationale (no silent omission).

## 3. Non-goals / boundaries
- ❌ NOT a state-machine redesign / pause-taxonomy change — T2-A adds a read-only precondition + an overlay; T2-B extends the hash input.
- ❌ NOT new authority — re-pausing for re-sign is the EXISTING Customer gate; this changes WHEN it is consulted and WHAT the signature covers.
- ❌ NOT OW-M3's `surface`/class logic.
- ❌ NOT a change to non-F1 (legacy) plan behavior.

## 4. Interaction with OW-M3
T2-A turns OW-M3's hash-bound `covered_req_surfaces`/resolved-mode (detectable) into **blocking** at every dispatch/resume AND closes the gap-followup-finishes-stale path (B3) so a stale plan can never reach `STATUS_DONE`. T2-B closes the parallel budget/gap_followup/isolation holes. **Sequencing:** this cycle ships + earns its own Codex APPROVE → THEN OW-M3 implementation unblocks.

## 5. Risks
- **Crash-idempotency regression** (highest) — mitigated by read-only checks outside the durable barriers + replay tests at each gate (B5 placement).
- **TD6 correctness** — the authority subset must be neither too wide (breaks deliver_followup) nor too narrow (re-opens a bypass); the next Codex round must validate the exact field partition.
- **Migration churn** — `budget`/`gap_followup`/isolation entering `H` makes existing signed plans carrying those blocks go `stale` until re-signed (intentional); the re-pause message must name the newly hash-bound field class.
- **Over-pausing** — a still-authority-fresh plan must never be flagged drift (canonical-JSON determinism + a "no-op when fresh" test on every gate, including after a legitimate deliver_followup insertion).

## 6. Decisions for the Codex gate
- **TD1 (in-H set)** — bind `gap_followup.{max_subsprints,max_no_progress_rounds}`, `budget.*`, `trunk_branch`, `milestone_isolation` authority fields, `isolation_strategy`. Classify `branch_name_template`/`worktree_root` (recommend bind). Codex checks inventory completeness.
- **TD2 (stale UX)** — freshness-block OVERLAY preserving the original pause reason/checkpoint (NOT a `campaign_plan_signoff` overwrite). Recommended over R1's naive reuse.
- **TD3 (F1-gating, N2)** — the NEW mid-run gates are F1-gated; the EXISTING legacy `campaign_plan_signoff` behavior is unchanged (a helper that newly ignores non-F1 unsigned plans there would NOT be byte-identical). Confirm.
- **TD4 (placement)** — the explicit before/after per gate in §2.1-B5. Confirm no double-pause / stranded cursor.
- **TD5 (migration)** — accept one-time re-sign once new fields enter `H`; require an actionable message naming the field class.
- **TD6 (authority subset)** — the freshness gate compares an authority subset EXCLUDING `subsprint_sequence` (so deliver_followup proceeds) and INCLUDING all §2.2 authority fields. The crux decision; Codex must validate the partition introduces no new bypass.

## 7. Test plan
- **T2-A:** each resume reason + the per-dispatch gate + the gap-followup outer loop: authority-fresh ⟹ proceeds byte-identical; post-pause authority edit (downgrade `functional_acceptance`; mutate `covers_req_ids`/`surface`; raise `budget`/`gap_followup`; flip `merge_prompt_at_close`/`trunk_branch`) ⟹ blocked for re-sign with the ORIGINAL pause preserved; **legitimate `deliver_followup` subsprint insertion ⟹ NOT blocked** (TD6); stale at backlog exhaustion ⟹ re-pause, NOT `STATUS_DONE` (B3); non-F1 plan ⟹ byte-identical.
- **T2-B:** raise `gap_followup.max_subsprints` / `budget.*` / flip `trunk_branch`/`merge_prompt_at_close` post-signoff ⟹ hash mismatch ⟹ blocked (today: silently honored). `signoff_snapshot_authentic` reconstructs the new `H` (N1). Inventory table reviewed for completeness.
- **Crash-idempotency:** crash-recovery replay at each new gate — no double-advance/double-pause; §3.5c barriers unaffected.
- **OW-M3 cross-check (after this lands):** post-sign `surface` flip while paused ⟹ blocked before dispatch/resume.

## 8. Citations (worktree/main `2f0095d`)
| Claim | Anchor |
|---|---|
| `signoff_status` = signed iff stored==live (legacy exception) | `campaign.py:2308-2323` (`_signoff_status` `1000-1011`) |
| freshness at initial start / resume-only-`campaign_plan_signoff` / gap-remediation precedent | `campaign.py:1894-1907` / `1692-1697` / `1511,1529` |
| other resume branches proceed without recheck | `campaign.py:1716-1743,1744-1764,1702-1715,1772-1776,1779-1786,1816-1834` |
| dispatch reads LIVE functional_acceptance/seq | `campaign.py:1944,1992-2002` |
| **gap-followup outer loop finishes on stale (B3)** | `campaign.py:1166-1167,1594-1597,1930-1936` |
| `H` excludes top-level authority fields | `campaign.py:2214-2226` |
| gap_followup live: max_subsprints + max_no_progress_rounds | `campaign.py:1096-1101,1258,1280-1283`; `schemas/campaign-plan.schema.json` gap_followup block |
| budget live (read/raise) + `_over_budget` reads self.budget | `campaign.py:602,784-792,1781` |
| isolation/merge authority live (trunk/merge_prompt/cleanup/strategy) | `campaign.py:602-619,821-826,885-895,955-966` |
| `subsprint_sequence` in envelope; deliver_followup inserts | `campaign.py:2195,1757` |
| snapshot-auth reconstruction (N1) / stored envelope | `campaign.py:~2280-2293,2202-2211` |
| §3.5c durable barrier (placement constraint) | `campaign.py:1730-1735,1808-1834` |
| F1 opt-in trigger | `campaign.py:2264-2274` |
