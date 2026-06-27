---
title: Follow-up — framework-wide "always-load → kernel-trio" doc reconciliation (deferred from WP-3)
doc_tier: archive
doc_category: intermediate
status: proposal
implementation_status: not_started
source_of_truth: this file
last_reviewed: 2026-06-27
review_cadence: ad hoc
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 4KB
notes: >
  Tracked follow-up surfaced by the WP-3 authoring-kernel wiring Codex review (round 3). WP-3
  itself wired the authoring-kernel + reconciled doc_governance's own self-description; this note
  captures the BROADER doc-model reconciliation that spans WP-2's constitution + general framework
  docs + the constitution-core kernel front-matter, deferred by user decision to keep WP-3 a single
  attributable increment and to respect "don't touch constitution-core".
---

# Follow-up: framework-wide always-load → kernel-trio doc reconciliation

## Background
After WP-2 (constitution-core) + WP-3 (authoring-kernel), the per-spawn cold-start always-load set
is the **kernel trio** — `constitution-core.md` + `authoring-kernel.md` + `context_briefing.md` —
and the full `constitution.md` / `doc_governance.md` are **on-demand canonical**. The kernels state
"the canonical wins on disagreement", so any framework doc still teaching the OLD "constitution.md /
doc_governance.md are always-loaded / @-included / the full governance chain" model is a latent
canonical contradiction.

WP-3 fixed every COLD-START LOAD instruction (an agent now loads the kernels) + reconciled
`doc_governance.md`'s OWN self-descriptions (front-matter `load_discipline`, notes, §2.1 tier line,
§3 always-load bullet) and `constitution.md`'s front-matter `load_discipline` + notes. The
remaining items below are EXPLANATORY/model prose (not cold-start loads) spread across WP-2's
constitution body + general adopter docs + the constitution-core front-matter.

## Deferred items (Codex wiring round 3, blocking 2/3/4 — minus the WP-3-scoped parts already done)
- `governance/constitution.md` BODY still says "always-loaded": lines ~29, ~44, ~232, ~240 (the
  WP-2 canonical; its front-matter `load_discipline` is already fixed, but body prose lags).
- `README.md` ~59, ~97, ~203, ~221 — teaches always-load / @-include / full governance chain.
- `docs/adoption-overview.md` ~62, ~74 — same model.
- `docs/greenfield-guide.md` ~81 — residual always-load guidance (the cold-start STEP-1 prose was
  fixed in WP-3; this is a separate explanatory line).
- `process/doc-responsibility-matrix.md` ~45 — always-load doc-responsibility wording.
- `governance/constitution-core.md` front-matter (~line 21) — stale status ("DRAFT … NOT committed",
  `size_target:18KB`); metadata only (the coverage gate strips front-matter, so the 65/65 proof is
  unaffected). This is also the long-standing WP-2 follow-up. Update status → current/wired + fix
  `size_target` to the real ~22KB.

## Suggested approach for the follow-up WP
1. One framework-wide sweep updating the above to the kernel-trio model (always-load = the kernels +
   context_briefing; full canonicals = on-demand). Treat human-only onboarding reading lists
   explicitly (a human MAY read the full constitution for rationale — mark it as such, not as agent
   cold-start).
2. Refresh `_sources.yaml` for any edited inventory-source doc (constitution.md, doc_governance.md,
   constitution-core.md is NOT a source). Re-run `--kernel-coverage` (65/65) + `--authoring-kernel-coverage`
   (41/41) — the edits are descriptive, so coverage must stay 100%.
3. Extend the WP-3 cold-start consistency gate's denylist file-set / patterns if any NEW cold-start
   LOAD instruction is discovered (the gate already scans list/numbered/arrow shapes over 13 files).
4. Codex xhigh re-gate; the sweep may surface further docs (brownfield-guide, ONBOARDING.md,
   modules/, etc.) — enumerate exhaustively in one pass rather than round-by-round.

## Why deferred (not a WP-3 defect)
WP-3's functional deliverable is complete + behaviorally proven (wiring correct, Read-trace canary
baseline 6/6, 1063 tests green, −818 tok/spawn realized). These residuals are pre-existing
documentation breadth (WP-2 + general docs) that the kernel principle merely makes visible; folding
them into WP-3 would violate the one-attributable-variable discipline and override the explicit
"don't touch constitution-core" scope. Captured here as the next increment.
