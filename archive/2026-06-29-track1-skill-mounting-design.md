---
name: 2026-06-29-track1-skill-mounting-design
doc_category: intermediate
status: codex-revise-incorporated-pending-human-signoff
created: 2026-06-29
base_commit: main @ 297350f (post Track 3+4)
builds_on:
  - archive/2026-06-29-four-area-optimization-plan.md   # Track 1 (Codex R1/R2/R3 approved-with-nits)
reviewer: codex gpt-5.5 xhigh — R-T1 VERDICT REVISE (1 blocking + 9 confirmations + 1 factual), incorporated 2026-06-29; current-state/additive/determinism/acceptance-exclusion/in-house-skills all CONFIRMED accurate
gate: REQUIRES the human to choose WHICH UI/frontend skills to vendor/author (no UI skills exist today)
---

# Track 1 — Task-aware dynamic skill mounting: implementation design + skill recommendation

"Advance to the human gate" deliverable for Track 1. The machinery below is additive and
behavior-neutral until (a) skills carry `signals` tags and (b) a milestone carries `task_signals`,
so it can land safely — BUT the motivating value ("UI task → mount UI skills") is blocked on a human
choice: **no UI/frontend skills exist in the framework today** (the 7 vendored skills are all
generic). So this track reaches a gate: *which UI skills to author/vendor, and from where.*

## §1 Current state (verified)
- Skills bind **statically per role** at config time (`skills/registry.yaml` `role_defaults` +
  charter `tooling.<role>.skills`), are content-hashed, and injected identically into every spawn
  (`effective_role_config.py` `resolve_role_config`/`skill_prompt_block`; `driver.py` `_effective_role`
  cache keyed by role only; injected in `_spawn`). **No runtime/network fetch** — the "no download"
  half of the goal already holds.
- **Missing-skill = HARD FAIL** today (`_resolve_skill` raises → `gate_hard_fail`). The goal wants
  skip-if-absent.
- **No task-awareness** in skill mounting (cold-start *loading* is task-scoped via WP-5A, but skills
  are not). **Zero UI/frontend skills exist.**

## §2 Machinery (additive, behavior-neutral until used — safe to build now)
1. **`signals` on the catalog** — add optional `signals: [ui, frontend, css, a11y, ...]` to
   `schemas/skill-catalog.schema.json` `skill_entry`. Pure data; no behavior change.
2. **`optional` bindings + skip-if-absent** — add per-binding `optional: true` to BOTH
   `schemas/skill-binding.schema.json:7-45` AND the compact mirror
   `schemas/mission-charter.schema.json:449-490` (both `additionalProperties:false`, R1 NB-1). In
   `effective_role_config.py`, an `optional` binding that does not resolve returns `None` + a
   structured skip-reason instead of raising; `resolve_role_config` collects `skipped_skills[]`;
   driver emits them in the `effective_role_config` audit event + a non-silent footer. **Required
   bindings keep hard-fail** (don't mask misconfig for current adopters).
3. **Task-signal selection (deterministic)** — add a signed `task_signals: [ui, ...]` field to the
   milestone/sub-sprint object, set by Deliver at decompose/sign-off (NEVER LLM-inferred from prompt
   text — that breaks `cold_start_load_graph_hash`/`acceptance_input_hash` determinism). A new
   `select_skills_for_task(role, task_signals, catalog)` maps signals → candidate skill ids via §2.1
   tags, intersects with **present-and-locked** skills, and feeds survivors as *optional extend*
   bindings on the role defaults; absent candidates drop via §2.2 skip with an audit note.
4. **Hash / cache / budget (R2/R3 + Codex R-T1).** Re-key `_effective_role_cache` from `role` to
   `(role, <signed sub-sprint / task-unit identity>)`. **NOT `(role, schema_key)`** — Dev spawns pass
   `schema_key=None` (`driver.py:1985`, R-T1 NB-7), so `schema_key` alone would collapse distinct Dev
   task selections; the key must carry the signed `task_signals`/sub-sprint identity. Surface the
   resolved skill-set identity in a dedicated spawn/audit field (do NOT overload `load_graph_hash`,
   `audit-event.schema.json:68`, R2 NB-2).
   **Budget — must SIZE the selected skill BODIES, not just toggle `skills_active` (Codex R-T1 B1 +
   factual-1).** Adding rows that call the existing sizer with `skills_active=True` does NOT close the
   hole: today `skills_active` only adds `process/role-skill-model.md`, it does **not** size any
   `SKILL.md` body (`load_sizer.py:246,267,271`). So the design requires a NEW sizing path that sizes
   the **resolved selected skill-body files/directories themselves**, with tracked
   `context_budget_report.py` baseline rows **per default + per task-signal set**, so `--strict`
   actually catches task-skill body growth.
5. **Exclude Acceptance** from task-aware selection — `effective_skill_set_hash` is in the acceptance
   `authority_fingerprint`, so per-task acceptance skills would thrash §3.6 calibration. Restrict to
   Dev/Deliver/Research/Reviewer.

All §2 items preserve the v4 optimization: skill bodies mount **task-scoped** (keep
`role-skill-model.md` conditional on `bool(effective.skills)`), gated on `context_budget_report.py
--strict` with the new skill-active rows.

## §3 The human gate — which UI/frontend skills, and from where
No UI skills exist, so even a perfect selector mounts nothing for "UI work". Options:
- **(A, recommended) Author a small in-house UI skill set** — no external supply chain, license-clean,
  consistent with the no-runtime-fetch constraint and the existing authored precedent
  (`skills/anti-hardcode-review-kernel/SKILL.md`). Proposed initial set (each a short `SKILL.md`,
  `tool_requirements: []` so it mounts on read-or-write roles without whitelist friction):
  `frontend-design-principles`, `ui-component-patterns`, `accessibility-a11y`, `responsive-layout`.
  Tag each with `signals` (e.g. `ui-component-patterns → [ui, frontend, component]`).
- **(B) Vendor from a pinned, license-compatible upstream** the human names — heavier (provenance +
  lock + `skill_vendor.py verify`), only if a specific high-quality upstream is preferred.

Recommendation: **(A)** for the initial set (fast, safe, no supply-chain risk); leave (B) open for
later high-value specialized skills.

## §4 Build sequence
- **Phase 1-a — machinery (§2), additive, behavior-neutral.** Codex-reviewed; suite + kernel +
  load-closure + `--strict` budget gates green. Mergeable on its own (changes nothing until skills
  carry `signals` and milestones carry `task_signals`).
- **Phase 1-b — author/vendor the chosen UI skill set (§3), HUMAN-GATED.** Register in
  `registry.yaml` + `skills.lock` + provenance; tag `signals`.
- **Phase 1-c — wire `task_signals` at Deliver decompose** + turn on selection for
  Dev/Deliver/Research/Reviewer. Measure cold-start delta under `--strict`.

## §5 Human gate (for the end-of-run batch)
1. **Approve the UI skill set + route** — option (A) authored set
   {`frontend-design-principles`, `ui-component-patterns`, `accessibility-a11y`, `responsive-layout`}
   vs (B) a named pinned upstream. (Prerequisite for any real "UI task → UI skills" value.)
2. **Confirm** `task_signals` is authored by Deliver at decompose (deterministic), and Acceptance is
   excluded from task-aware selection.
