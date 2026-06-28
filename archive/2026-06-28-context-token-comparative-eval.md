---
title: "Context/Token Optimization — full comparative evaluation (WP-0 → WP-9)"
status: measured
date: 2026-06-28
roadmap_step: 13 (final — comparative evaluation)
branch: wp0-measurement
baseline_commit: 90bc130   # WP-0 (pre-kernel doc tree; observation-only)
head_commit: c85ec0a       # WP-9 + reconciliation
related:
  - archive/2026-06-26-context-token-optimization-design.md   # §F measurement design, sequence step 13
  - engine-kit/orchestrator/load_sizer.py                      # the deterministic sizer used for both ends
---

# Context/Token Optimization — comparative evaluation (WP-0 → WP-9)

The roadmap's final step: measure the cumulative token-footprint change of the whole
WP-0→WP-9 chain against the pre-optimization baseline, and record the non-regression
evidence. All static numbers are **deterministic** (`load_sizer`, bytes ÷ 4 ≈ tokens);
the 45–50% target was always a *hypothesis* (design §F) — this is the **measured** result.

## 1. Method (apples-to-apples, deterministic)

- **Baseline** = WP-0 commit `90bc130` (observation-only; the pre-kernel doc tree). Measured
  by running **WP-0's own `load_sizer`** against **WP-0's own tree** (extracted via
  `git archive 90bc130`), so the baseline is the framework as it actually was, not a
  reconstruction.
- **Head** = `c85ec0a` (WP-9 lint + the acceptance reconciliation). Measured by the current
  `load_sizer`.
- Both ends are **framework-static cold-start** (the framework-controlled, deterministic
  figure — the only lever the framework owns; adopter-static + run-dynamic inputs vary per
  deployment and are excluded from both ends).

## 2. Cumulative cold-start reduction (framework-static, per spawn)

| cold-start budget | WP-0 (B / tok) | WP-9 (B / tok) | Δ tokens | reduction |
|---|---:|---:|---:|---:|
| **governance floor** (re-paid EVERY spawn) | 93,637 / 23,409 | 59,533 / 14,883 | −8,526 | **−36.4%** |
| research | 138,101 / 34,525 | 102,200 / 25,550 | −8,976 | −26.0% |
| deliver (plan) | 201,105 / 50,276 | 168,017 / 42,004 | −8,272 | −16.5% |
| **deliver:close** (WP-5A task-scoped) | 201,105 / 50,276 | 87,243 / 21,810 | −28,466 | **−56.6%** |
| dev | 126,825 / 31,706 | 92,875 / 23,218 | −8,488 | −26.8% |
| review | 117,119 / 29,279 | 82,414 / 20,603 | −8,677 | −29.6% |
| acceptance (cold-start read) | 174,035 / 43,508 | 90,173 / 22,543 | −20,966 | **−48.2%** |

Every spawn pays the **governance floor**, so the **−36.4% floor cut is the universal,
always-on win** (it appears inside every role row above). The per-role briefing docs add
role-specific volume on top; their reductions range from −16.5% (deliver-plan — a
legitimately heavy role with many real briefing docs, mostly retained) to −56.6%
(deliver:close — the WP-5A task-scoped narrowing).

## 3. Governance-floor breakdown + per-WP attribution

The floor is the kernel trio. Member-level (WP-0 → WP-9):

| floor member | WP-0 | WP-9 | Δ B | WP |
|---|---:|---:|---:|---|
| constitution.md → constitution-core.md | 54,695 | 22,611 | −32,084 | WP-2 |
| doc_governance.md → authoring-kernel.md | 15,979 | 12,328 | −3,651 | WP-3 |
| context_briefing.md (kept canonical) | 22,963 | 24,594 | +1,631 | WP-2/3/4B/5A wiring notes |
| **floor total** | **93,637** | **59,533** | **−34,104** | |

Floor progression (tokens), by increment: WP-0 23,409 → WP-1b +12 → **WP-2 −7,917**
(constitution-core, the single biggest win) → **WP-3 −818** (authoring-kernel) → WP-3-fu
+27 → WP-4B +104 (§6 Acceptance carve-out) → WP-5A +66 (§2.2 task-scope note) → **WP-9
14,883**. The small `+` increments are the price of *wiring* the kernels safely (cold-start
prose + carve-outs in the always-load `context_briefing.md`); they are dwarfed by the WP-2/3
cuts.

## 4. Acceptance — honest net (cold-start read vs prompt-embed)

Acceptance's **−48.2% cold-start-read** figure is real but must be read with its offset:
WP-4B moved `delivery-loop.md`'s judge-relevant content (a 47,557 B per-spawn whole-file
*read* at WP-0) into the **acceptance-kernel projected INLINE in the dispatched prompt**
(`governance/acceptance-kernel.md`, 20,376 B / 5,094 tok). The kernel is a *prompt* cost
(counted in the WP-0 `prompt_bytes` audit), not a cold-start read, so it is outside the
table above.

Netting the embed in: Acceptance per-spawn governance context ≈ 174,035 (WP-0 read) →
90,173 (WP-9 read) + 20,376 (WP-9 kernel embed) = **110,549 B ≈ −36.5% net**. Either way a
large reduction — but the honest number is **−36.5% net**, not −48.2%, because ~5K tok of the
retired read came back as a (much smaller, compressed) prompt embed. When the Acceptance
role has skills active, WP-4B *also* retires the `role-skill-model.md` (~17 KB) cold-start
read (its §4/§6 are inlined into the same kernel), a further runtime win not in the
skills-off table.

## 5. Runtime channels invisible to the static sizer

- **Lessons ingress (WP-6).** The only previously-*unbounded* injected channel
  (`driver._lessons_block`) is now bounded by `lesson_selection`: measured unbounded
  ~18,400 tok/spawn (at 100 L1 singletons) → a **~434-tok cap**, every spawn, all roles —
  with zero loss of validated/constraint-bearing lessons (only L1 singletons budgeted). This
  reduction is per-spawn and additive on top of §2, but is a prompt channel so it does not
  appear in cold-start sizing.
- **Acceptance whole-file retirement (WP-4B).** Covered in §4 — the `delivery-loop.md`
  read (now reflected in the corrected §2 figure after the reconciliation in `c85ec0a`).

## 6. Verdict vs the 45–50% hypothesis

The design (§F) explicitly framed 45–50% as *a hypothesis pending Phase-0; report the
MEASURED reduction; no increment ships on an estimate.* Measured outcome:

- The **universal governance floor** — re-paid on every spawn — fell **−36.4%**.
- The **highest-value paths meet or exceed 45–50%**: `deliver:close` **−56.6%**, acceptance
  cold-start read **−48.2%** (−36.5% net of the kernel embed).
- The **other roles** land **−26% to −30%** (research/dev/review), with `deliver` (plan) at
  −16.5% (a heavy role whose real briefing docs are legitimately retained — the doctrine
  forbids shrinking sufficient context).
- **Plus** the WP-6 lessons channel went from *unbounded* to a hard ~434-tok cap.

Conclusion: the chain delivered a **~36% universal per-spawn floor reduction** and **larger
task/role-specific cuts (up to −57%)**, while *bounding* the one unbounded channel — a
material, measured win below the optimistic 45–50% universal target but at/above it on the
paths that matter most. Honesty note (consistent across every WP): measured numbers ran
below the design's per-WP token estimates every time.

## 7. Non-regression evidence (behavioral)

Governance behavior was checked **incrementally** — every kernel/wiring WP ran its own
A/B live-LLM canary (`claude -p`), all with **zero governance regression**:

| WP | canary | result |
|---|---|---|
| WP-2 constitution-core | 66 cells (8 adversarial scenarios × arm × reps × models) | arm B 33/33 correct vs arm A 32/33; no §1.7/§1.8/F5/scope breach |
| WP-3 authoring-kernel | 12-cell read-trace | baseline 6/6 read kernel trio, never full canonical |
| WP-4B acceptance-kernel | 12-cell read-trace + routing | 6/6 skip delivery-loop+role-skill; routing identical A/B |
| WP-5A close task-scoping | 6-cell read-trace | arm B 0/9 dropped docs read; identical honest verdict |

Each was independently Codex-reviewed to APPROVE. The **WP-9 lint** now guards against future
*volume* regressions (advisory drift + waiver + structural anomalies), and the build suite
(1193 passed) + kernel-coverage gates (65/65 + 41/41 + 44/44 + base 475) + acceptance
load-closure (`closed:true`) guard *content* equivalence.

## 8. Deferred — full §F golden-probe campaign (rationale)

The design §F's most exhaustive form is a consolidated golden-probe A/B campaign — a
targeted probe for **every** WP-EQ constraint row (475 rows) × ≥3 reps — re-run end-to-end.
This is **deferred, not skipped**: regression is already covered by (a) the per-WP
behavioral canaries above (each targeting that WP's highest-risk constraints), (b) the
machine-checked kernel-coverage gates that prove each kernel carries its inventory rows
non-vacuously, and (c) the WP-9 volume guardrail. A 475-row × 3-rep live campaign is a large
billable run whose marginal regression-detection value over (a)+(b)+(c) is low; it is
recorded here as the available next escalation if a behavioral regression is ever suspected.

## 9. Finding fixed by this evaluation

The eval surfaced a stale `load_sizer` entry: the acceptance cold-start set still counted
`delivery-loop.md` (47,557 B) that WP-4B had retired at runtime. Fixed in commit `c85ec0a`
(Codex-APPROVED, full suite green) — `load_sizer` now matches what the Acceptance agent
actually reads, and the WP-9 acceptance baseline was regenerated to the corrected 90,173 B.

## 10. Status

WP-0 → WP-9 complete and pushed to `origin/wp0-measurement` (no `main` merge). The
optimization roadmap's measurable objective is met and quantified; the WP-9 lint is the
standing regression guardrail. No further WP is open.
