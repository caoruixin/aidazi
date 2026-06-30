# Track-2 hardening cycle — universal F1 freshness + authoritative signed-input coverage (design spec)

- **Date:** 2026-06-30
- **Branch:** drafted on `acceptance-efficacy-e2e-mandate` (worktree `../aidazi-acceptance`, off `main` `2f0095d`); **implementation belongs to its own Track-2 branch** with its own Codex gate.
- **Status:** DESIGN SPEC — for Codex gpt-5.5 xhigh review/acceptance. No runtime code changed.
- **Why it exists:** it is the **implementation blocker** for OW-M3 (`archive/2026-06-30-ow-m3-mandatory-e2e-spec.md` §5) and the home for the pre-existing Track-2 authz gap ([[track2-gap-followup-signing-followup]]). User decision 2026-06-30 (Option 2): OW-M3 does NOT absorb this; this cycle solves it uniformly and earns its OWN Codex APPROVE before OW-M3 impl proceeds.
- **Thesis:** A signed campaign plan's scope must be **authoritative at every point the engine acts on it** — not only at initial start and the `campaign_plan_signoff` resume. Two gaps break that: (A) freshness is revalidated non-uniformly; (B) not every authority/verdict-affecting field is inside the signed hash `H`. Close both so a post-signoff mutation is both **detectable** (in `H`) and **blocking** (re-checked at every act).

---

## 0. One-sentence design

> Make `signoff_status() == "signed"` a **universal precondition** re-checked before every dispatch and every resume `proceed` (T2-A), and make the signed hash `H` **cover every post-signoff-mutable field that gates dispatch, escalation, authority, or a verdict** — starting with `gap_followup` bounds (T2-B). Additive: F1-inactive plans stay byte-identical.

---

## 1. The two holes (confirmed against `2f0095d`)

### 1.1 Hole A — freshness revalidation is not universal
`signoff_status()` (campaign.py:2308-2323) ⟹ `signed` iff stored `signed_scope_hash` == live recompute; a post-signoff edit ⟹ `stale`. It is enforced:
- at initial start — `_drive_milestones` entry pauses on non-`signed` (campaign.py:1894-1907); ✅
- on resume from `campaign_plan_signoff` only — `_handle_resume` (campaign.py:1692-1697); ✅
- before a gap-followup remediation dispatch — `_complete_pending_remediation` re-checks `_signoff_status() != "signed"` (campaign.py:1529); ✅ **(the precedent to generalize)**

It is NOT enforced:
- **before each milestone dispatch** — the inner loop `_drive_milestones` calls `run_unit` reading the plan's LIVE `functional_acceptance` (campaign.py:2001) and LIVE `seq` (1944, 1992-1997, by design "so a governed deliver_followup insertion is reflected") with **no per-dispatch freshness gate**;
- **on resume from any non-`campaign_plan_signoff` checkpoint** — `_handle_resume` returns `proceed` for `deliver_followup_required` (1744-1764), `milestone_merge` (1716-1743), `GAP_REVIEW_CHECKPOINT` (1702-1715), mechanism-A driver-resume (1772-1776), `campaign_budget_exhausted` (1779-1786), and the advancing dispatches (1816-1834) **without** revalidating `_signoff_status()`.

**Consequence:** pause at e.g. `advisory_acceptance_pass_signoff` or `deliver_followup_required`, edit the plan (downgrade a milestone's `functional_acceptance` browser_e2e→static, mutate `covers_req_ids`, raise a bound), resume → the engine acts on the mutated plan. The drift is hash-DETECTABLE but never re-checked, so it does not BLOCK. (This is exactly Codex OW-M3 R1 B2.)

### 1.2 Hole B — signed-input coverage is incomplete
`_signed_scope_H` (campaign.py:2214-2226) = `{version, campaign_id, goal, charter_ref, charter_hash, milestones[_envelope_milestone…]}`. The top-level **`gap_followup`** block is NOT in `H`, yet it is read LIVE (`_gap_followup_cfg`, campaign.py:1096) and gates escalation/budget: `_over_budget` (campaign.py:786) and `_gap_followup_bounds` (1258) honor `gap_followup.max_subsprints`. So raising `max_subsprints` (or the sibling `max_total_spawns` / `max_wall_clock_minutes`) AFTER sign-off does NOT change `signed_scope_hash` ⟹ stays `signed` ⟹ more autonomous in-envelope work runs than the Customer signed for. The Track-2 Phase-2-γ §A.3 static charter cap bounds the ABSOLUTE value but does not bind the signed value, so a within-cap post-signoff raise still escapes.

---

## 2. Deliverables

### 2.1 T2-A — universal F1 freshness gate
- A single read-only chokepoint helper (e.g. `_require_fresh_signoff(reason) -> proceed|repause`) that returns "re-pause for re-sign" when `f1_required(plan)` AND `_signoff_status() != "signed"`, else proceed.
- **Invoke it before EVERY act on signed scope:**
  - in `_drive_milestones`, immediately before each `run_unit` dispatch (campaign.py ~1998) — and before the decompose/budget pauses that read the live plan;
  - in `_handle_resume`, on EVERY path that returns `proceed` — i.e. generalize the `campaign_plan_signoff` check (1692-1697) to all branches, not a special case.
- **Stale ⟹ re-pause uniformly as `campaign_plan_signoff`** (re-sign and resume), reusing the existing pause/`_repause` machinery so the CLI/UX is identical to today's stale-at-start.
- **F1-active only:** gated on `f1_required(plan)` (campaign.py:2264-2274) ⟹ a legacy/non-F1 plan is byte-identical to today (additivity).
- **Crash-idempotency preserved:** the check is READ-ONLY and placed OUTSIDE the §3.5c durable barriers (`_commit_dispatch_resolution`), so it never perturbs replay semantics (it can only convert a would-be `proceed` into a `paused`, which is already a durable, replay-safe state).

### 2.2 T2-B — authoritative signed-input coverage
- **Inventory (the rigorous core):** enumerate every plan field read LIVE on a dispatch / escalation / authority / verdict path and classify `in-H` vs `not-in-H`. Seed set to fix: `gap_followup` bounds (`max_subsprints`, `max_total_spawns`, `max_wall_clock_minutes`). Candidates to classify, not assume: top-level `budget`, `autonomy.approved_scope`, any other top-level plan field consulted post-signoff. Output: a table {field, read-site, gates-what, decision in-H?}.
- **Bind the authority-bearing fields into `H`** (`_signed_scope_H`, campaign.py:2214-2226) and, where reconstruction matters, the stored `scope_envelope` (`compute_scope_envelope`, 2202-2211). Canonical-JSON keeps it ordering-stable; normalize absent-vs-empty so an absent block doesn't churn the hash.
- A field that is intentionally NON-authoritative (mutable without re-sign) must be explicitly listed as out-of-H with a one-line rationale — no silent omission.

---

## 3. Non-goals / boundaries
- ❌ NOT a redesign of the campaign state machine, the §3.5c crash-idempotency barriers, or the pause taxonomy — T2-A adds a read-only precondition, nothing more.
- ❌ NOT new authority: re-pausing for re-sign is the EXISTING `campaign_plan_signoff` gate; this cycle changes WHEN it is consulted, not who decides (Customer re-signs).
- ❌ NOT OW-M3's `surface`/class logic — that lands with OW-M3. This cycle only guarantees that whatever is in `H` (including OW-M3's `covered_req_surfaces`) is re-checked everywhere.
- ❌ NOT a change to non-F1 (legacy) plan behavior.

## 4. Interaction with OW-M3
- T2-A is the **runtime-enforcement half OW-M3 depends on**: it turns OW-M3's hash-bound `covered_req_surfaces` / resolved-mode (detectable) into **blocking** at every resume/dispatch. T2-B closes the parallel `max_subsprints` hole in the same family.
- **Sequencing:** this cycle ships + earns its own Codex APPROVE → THEN OW-M3 implementation unblocks (OW-M3 spec §5).

## 5. Risks
- **Crash-idempotency regression** — the highest risk; mitigated by keeping the check read-only and outside the durable barriers, plus replay tests at each new gate.
- **Migration churn (T2-B)** — adding `gap_followup` to `H` makes any existing SIGNED plan that carries a `gap_followup` block go `stale` until re-signed (intentional; same shape as OW-M3's migration). The re-pause message must name the cause (a now-signed field changed the hash) and the fix (re-sign).
- **Over-pausing** — a freshness gate on every dispatch must not re-pause a still-`signed` plan (false drift); covered by canonical-JSON determinism + a "no-op when signed" test on every gate.

## 6. Decisions for the Codex gate
- **TD1 (T2-B scope)** — exact in-H field set. Recommend: `gap_followup` bounds definitely; classify `budget` + `autonomy.approved_scope` explicitly (do not assume). The inventory IS the deliverable; Codex should check it for completeness (no authority-bearing field left live-and-unsigned).
- **TD2 (stale UX)** — re-pause uniformly as `campaign_plan_signoff` (recommended, reuses existing UX) vs a distinct `scope_drift_detected` checkpoint. Recommend reuse.
- **TD3 (F1-gating)** — apply the universal gate only when `f1_required` (recommended; additive). Confirm non-F1 byte-identical.
- **TD4 (placement vs §3.5c)** — confirm the read-only freshness check sits outside every durable barrier and cannot double-pause or strand a half-advanced cursor.
- **TD5 (migration)** — accept the one-time re-sign for plans with a `gap_followup` block once it enters `H`; require an explicit, actionable re-pause message.

## 7. Test plan
- **T2-A:** for EACH resume reason (`deliver_followup_required`, `milestone_merge`, `GAP_REVIEW`, mechanism-A, `campaign_budget_exhausted`, advance-subsprint/milestone) and for the per-dispatch gate: signed ⟹ proceeds byte-identical; post-pause plan edit (downgrade `functional_acceptance`; mutate `covers_req_ids`; insert a non-followup subsprint) ⟹ `stale` ⟹ re-pause for re-sign, NOT dispatched. Mid-drive live edit between units ⟹ caught at the next dispatch gate. Non-F1 plan ⟹ byte-identical (no new pause).
- **T2-B:** raise `gap_followup.max_subsprints` post-signoff ⟹ hash mismatch ⟹ `stale` ⟹ blocked (today: silently honored). Inventory table reviewed: every authority-bearing field either in-H or explicitly rationalized out.
- **Crash-idempotency:** crash-recovery replay at each new gate does not double-advance / double-pause; the §3.5c barriers are unaffected.
- **OW-M3 cross-check (after this lands):** post-sign `surface` flip while paused ⟹ blocked (the OW-M3 B1 test that this cycle is the precondition for).

## 8. Citations (worktree/main `2f0095d`)
| Claim | Anchor |
|---|---|
| `signoff_status` = signed iff stored hash == live | `campaign.py:2308-2323`; `_signoff_status` `1000-1011` |
| freshness enforced at initial start | `campaign.py:1894-1907` |
| freshness on resume ONLY for `campaign_plan_signoff` | `campaign.py:1692-1697` |
| other resume branches proceed without recheck | `campaign.py:1716-1743, 1744-1764, 1702-1715, 1772-1776, 1779-1786, 1816-1834` |
| existing fresh-signed dispatch precedent (to generalize) | `campaign.py:1511, 1529` |
| dispatch reads LIVE functional_acceptance / seq, no gate | `campaign.py:1944, 1992-2002` |
| `H` excludes top-level `gap_followup` | `campaign.py:2214-2226` |
| `gap_followup` read live; gates escalation/budget | `campaign.py:1096, 786, 1258` |
| F1 opt-in trigger | `campaign.py:2264-2274` |
| §3.5c durable barrier (placement constraint) | `campaign.py:1730-1735, 1808-1834` (`_commit_dispatch_resolution`) |
