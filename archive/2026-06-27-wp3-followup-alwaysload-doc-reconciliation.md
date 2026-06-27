---
title: Follow-up — framework-wide "always-load → kernel-trio" doc reconciliation (deferred from WP-3)
doc_tier: archive
doc_category: intermediate
status: implemented
implementation_status: implemented
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

## Closure (2026-06-27)
DONE as one attributable increment (docs + a regression gate). The framework-wide sweep reconciled
the always-load → kernel-trio model across CURRENT / load-bearing / adopter-facing docs:
`governance/constitution.md` (front-matter notes + body §1/§2/§3 prose), `governance/constitution-core.md`
front-matter (status/size_target), `README.md` + `README.zh-CN.md` (incl. the governance repo-tree),
`docs/adoption-overview.md`, `docs/greenfield-guide.md`, `docs/brownfield-guide.md`,
`process/doc-responsibility-matrix.md`, `process/prompt-artifact-rules.md`,
`templates/adoption-config-template.md`, `examples/minimal-greenfield/docs/current/agent_context_guide.md`.
`engine-kit/tools/constraint-inventory/_sources.yaml` refreshed (constitution.md sha256;
`--kernel-coverage` 65/65 + `--authoring-kernel-coverage` 41/41 unchanged). New repo-wide gate
`engine-kit/orchestrator/tests/test_alwaysload_doc_reconciliation.py` covers the THREE structural
forms the framework actually uses: Rule A (always-load/@-include assertion + canonical), Rule B
(obsolete-chain enumeration — both canonicals, no kernel, load context), Rule C (the `governance/*`
glob called the role-session/cold-start chain). Carve-outs = on-demand/§-citation/archive+compact/
kernel self-projection. A single-canonical bare "cold-start" cross-reference is intentionally NOT
flagged (false-positive cost); the executable cold-start regions (role-card step-1, context_briefing
§1.2/§3, AGENTS.md §2) are positively asserted to name the kernel trio by
`test_coldstart_consistency.py`. Codex xhigh: R1 REVISE (found `prompt-artifact-rules.md:69` chain
row + the Rule-B gap) → R2 REVISE (found `AGENTS.md:154` `governance/*` glob + the Rule-C gap) →
both fixed + fixtured. Archive records describing the OLD state were intentionally left as history.

### Deferred (tracked; NOT in this increment — one-attributable-variable + anti-whack-a-mole)
- `engine-kit/orchestrator/load_sizer.py` ~line 159 — stale CODE COMMENT: "AGENTS.md transitively
  @-includes the framework governance chain". Engine behavior is already kernel-trio; this is a
  comment-only cleanup that also needs confirming what `resolve_load_graph` actually follows. Defer
  to a later code-comment pass (a different surface than this doc sweep; the `.md` gate does not scan
  code comments). Flagged by Codex as a follow-up, not a blocker.
- zh/en translation drift on adopter DOMAIN-CONTRACT load discipline (e.g. `README.zh-CN.md` ~95
  "每次冷启动都会加载" vs the EN "loaded by roles on demand") — a different bug class (not the
  canonical always-load model); reconcile in a separate i18n pass.
