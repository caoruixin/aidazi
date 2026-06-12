---
title: Fold-back protocol — adopter ↔ framework
doc_tier: process
doc_category: live
status: current
implementation_status: partial
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 16KB
split_trigger: if cadence-rules grow past 4KB or adoption-state schema grows past 4KB, split each to a dedicated doc
notes: >
  Bidirectional fold-back: adopter → framework (lessons-learned) and
  framework → adopter (release-based). Defines the adoption-state ledger
  schema, lessons-learned template, fold-back sub-sprint cadence + output,
  and fold-back anti-patterns. Companion of `process/self-governance.md`.
  Implementation status `partial` until first fold-back sub-sprint runs.
---

# Fold-back protocol

The framework + its adopters form a bidirectional system:
- **Adopter → Framework** — adopters file lessons in `aidazi/lessons/` as they observe gaps, surprises, or wins. Framework maintainer reviews + extracts patterns + revises Δs.
- **Framework → Adopter** — framework cuts versioned releases. Adopters consume on their own cadence.

Neither direction is automatic. Both are human-mediated.

This file specifies: (§1) the two directions; (§2) sub-sprint cadence triggers; (§3) sub-sprint output; (§4) the adoption-state ledger schema; (§5) the lessons-learned template; (§6) fold-back anti-patterns.

## §1 Two directions

### §1.1 Adopter → Framework (lessons-learned)

- Adopters file lessons in `aidazi/lessons/<date>-<topic>.md` as they observe them.
- Lessons are **proposals**, not auto-merged.
- Periodic fold-back review by framework maintainer extracts patterns and promotes to Δ revisions OR documents rejections.

Sub-sprint not continuous. Lessons accumulate; review batches them.

### §1.2 Framework → Adopter (release-based)

- Framework cuts versioned releases (`v4.0.0` → `v4.0.1` → `v4.1.0` → `v5.0.0` per Constitution §9).
- Adopters consume on their own cadence (no auto-update).
- When an adopter consumes a new framework version, they update `docs/current/adoption-state.md` to reflect any newly at-spec / partial / divergent Δs.

NO automatic submodule update. NO continuous integration of framework changes into adopter repos. Each direction crosses a deliberate human boundary.

## §2 Fold-back sub-sprint cadence

The framework maintainer (= the human who owns the framework repo) holds a fold-back sub-sprint when ANY of three triggers fires:

1. **Adoption count trigger** — **5 fresh adoptions complete** since last fold-back. "Adoption complete" = adopter has finished a first milestone close under the framework's 5-role chain.
2. **Time trigger** — **6 months since last fold-back**.
3. **Critical-pattern trigger** — **≥3 adopters file lessons-learned docs touching the same Δ or section**, OR **≥1 lesson categorized `critical`** (e.g., security, correctness, framework-breaks-adopter).

Numbers (5 adoptions, 6 months, ≥3 same-Δ) are SUGGESTED defaults per Constitution §7.0.

### §2.1 Triggering across adopters

When critical-pattern trigger fires from multiple adopters, maintainer reviews ALL recent lessons (not just triggering ones).

### §2.2 Recovery after a missed cadence

If a trigger fires but maintainer can't hold the sub-sprint, trigger remains active. Don't reset the counter; let lessons accumulate. Next fold-back addresses the backlog.

## §3 Fold-back sub-sprint output

Each fold-back sub-sprint produces:

1. **One or more Δ revision PRs to `aidazi/`** — each PR addresses one Δ or one connected set. PR title: `fold-back <date>: <Δ-N short description>`. PR body includes the lessons cited.
2. **`archive/framework-release-notes/<version>.md`** — release notes per Δ. Adopter-facing.
3. **`archive/framework-release-notes/<version>-migration-guide.md`** — list of what adopters need to update.
4. **(Optional) examples/ snapshot refresh** — if `examples/csagent-reference/` or `examples/hermes-reference/` drift becomes load-bearing.
5. **Bloat-metric snapshot** — per `process/self-governance.md` §7.7, maintainer captures the 5 bloat metrics.
6. **`archive/rejected-lessons/<date>-<topic>.md`** — for each lesson the maintainer rejects, rejected-lessons archive carries the rationale.

The fold-back sub-sprint produces all of the above as one coherent batch.

## §4 Adopter-state ledger schema (`adoption-state.md`)

The adopter repo carries `docs/current/adoption-state.md`. THE adopter's running record of what's at-spec, what's partial, what's divergent (with rationale).

### §4.1 Schema

```yaml
---
title: <adopter-name> Adoption State vs aidazi framework
adopter_name: <name>
framework_version: v4.0.0
last_reviewed: <YYYY-MM-DD>
review_cadence: per milestone close
---

# Per-Δ status

| Δ | v4 spec | Adopter status | Gap notes | Plan |
|---|---|---|---|---|
| Δ-1 Anatomy | T0 | at-spec | — | — |
| Δ-2 Domain discovery | T0 | at-spec | — | — |
| Δ-3 Decision catalog | T0 | partial | uses 6 of 8 decisions; #5 memory + #7 policy not yet decided | next milestone |
| Δ-18 Delivery Loop | T1 (Type A) | divergent | adopter supports 2 autonomy levels, framework defines 3 | OQ-<id> |
| ... | | | | |

# Drift reasons (for `divergent` rows)

- Δ-18 autonomy.level: adopter intentionally omits `fully_autonomous_within_budget`
  because <justification>. Will revisit if framework promotes a v5.

# Lessons proposed for upstream fold-back

| Date | Topic | Lesson file | Status |
|---|---|---|---|
| 2026-06-15 | F5 cost-asymmetry on Codex subscription | aidazi/lessons/2026-06-15-codex-cost-asymmetry.md | proposed |
```

### §4.2 Status enum

- `at-spec` — adopter follows framework default as written.
- `partial` — adopter has implemented some sub-parts; not all.
- `divergent` — adopter has overridden framework default. Rationale required.
- `not-applicable` — Δ doesn't apply to adopter's track.
- `superseded-by-framework` — adopter was at-spec at older framework version; framework has since evolved.

### §4.3 Cadence

`review_cadence: per milestone close` is suggested default per Constitution §7.0.

At each cadence review, adopter human owner walks the per-Δ table and updates rows whose status changed.

### §4.4 Constitution §1.7 immutability check

Per Constitution §1.8, adopters MAY NOT have `status: divergent` against §1.7. The template includes a comment block reminding the human owner.

If a divergent §1.7 row appears, it is a framework breach, not an override. Surface immediately.

### §4.5 Template

`templates/adoption-state-template.md` carries the starter shape. New adopters copy + adapt.

JSON schema: `schemas/adoption-state.schema.json`.

## §5 Lessons-learned template

`templates/lessons-learned-template.md`:

```yaml
---
title: <short title>
adopter: <adopter name>
date: <YYYY-MM-DD>
related_delta: [<Δ-N>, ...]
category: incident | observation | proposed-amendment | divergence-rationale | safety
status: proposed | under-review | accepted | rejected
---

# Context
<what was happening at adopter side; cite project + sprint>

# Observation
<what was observed; what didn't work as framework specified>

# Hypothesis
<why; rooted in code or trace>

# Proposed amendment (optional)
<what Δ revision would help; suggested wording>

# Rejection rationale (filled by maintainer if rejected)
<why this lesson didn't fold back; framework's intentional design choice>
```

### §5.1 Filing a lesson

1. Adopter writes lesson file at `aidazi/lessons/<YYYY-MM-DD>-<topic>.md`.
2. Adopter updates `docs/current/adoption-state.md` "Lessons proposed" table.
3. Adopter sets `status: proposed`.

### §5.2 Reviewing at fold-back

1. Maintainer reads each `status: proposed` lesson.
2. For each, sets `status: under-review` while evaluating.
3. Output: `status: accepted` (drives Δ revision PR; lesson archived after Δ doc updated) OR `status: rejected` (move to `archive/rejected-lessons/`).

Lesson docs themselves are `intermediate` (Δ-4) — frozen at filing. The `status` field changes via a new commit (not body re-edit).

### §5.3 Categories

- `incident` — something broke in adoption (urgent; may trigger out-of-cadence fold-back).
- `observation` — pattern adopter noticed (most common).
- `proposed-amendment` — adopter proposes specific framework wording change.
- `divergence-rationale` — adopter documenting why they diverge (informational).
- `safety` — security / correctness / safety concern (CRITICAL trigger per §2).

## §6 Fold-back anti-patterns (forbidden)

1. **Framework auto-updating adopter repos via submodule** — no. Adopters consume on their cadence.
2. **Adopter auto-syncing framework changes mid-milestone** — no. Wait for sub-sprint boundary.
3. **Lessons-learned doc updated after filing** — no. Lessons are `intermediate` per Δ-4. File a new lesson that references the old one.
4. **Fold-back sub-sprint without an adoption-state.md review** — no. Maintainer MUST check all adopters' adoption-state.md.
5. **Framework v5 dropping a Δ without migration guide** — no. Every major release MUST publish migration guide.
6. **Lessons promoted to Δ revisions WITHOUT updating cited lesson's status** — no. After fold-back, lesson's `status: accepted` AND a link from revised Δ doc to lesson must both exist.
7. **Maintainer rejecting a `safety` category lesson without rejection rationale** — no. Safety lessons get rationale OR get accepted. Silent rejection forbidden.
8. **Fold-back sub-sprint producing a Δ revision that breaks Constitution §1.7 hard requirements** — no. §1.7 is revisable, but only with multi-fold-back consensus + explicit migration guide.

## §7 Open questions / OQs carry

- **OQ-V4-005** (lessons submission mechanism) — slash command? PR to aidazi/? direct file commit? TBD at first adopter's request.
- **OQ-V4-006** (adoption-state cadence) — proposed `per milestone close`; confirm at first adopter's first review.
- **OQ-V4-004** (framework versioning policy) — semver is suggested (v4.0.0 / v4.0.x / v4.x.0 / v5.0.0); confirm at first release.

## §8 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The §6 anti-patterns list is load-bearing — additions require multi-fold-back consensus. The §4 / §5 schemas may evolve more readily as the lesson stream surfaces patterns.

---

End of Fold-back protocol.
