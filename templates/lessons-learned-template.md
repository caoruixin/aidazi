---
title: Lessons-learned — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
load_discipline: by-role
size_target: 4KB
notes: >
  Template for aidazi/lessons/<YYYY-MM-DD>-<topic>.md. Adopter → framework
  fold-back input. Lesson docs are intermediate per Δ-4 — frozen at filing;
  status field changes via new commit, not body re-edit. Per
  process/fold-back-protocol.md §5: maintainer reviews at fold-back cadence;
  accepted → drives Δ revision PR; rejected → moves to archive/rejected-lessons/.
---

# Lessons-learned — instance template

Copy this template to `aidazi/lessons/<YYYY-MM-DD>-<topic>.md` and fill `<placeholders>`. The file is frozen at filing (`doc_category: intermediate` per Δ-4); only the `status:` field changes after the maintainer's fold-back review.

Filing mechanism is OQ-V4-005 (PR / direct commit / slash-command TBD); follow your adopter's adopted convention.

---

```markdown
---
title: <short title>
doc_tier: lesson
doc_category: intermediate
adopter: <adopter name>
date: <YYYY-MM-DD>
related_delta: [<Δ-N>, ...]
category: incident | observation | proposed-amendment | divergence-rationale | safety
status: proposed   # proposed → under-review → accepted | rejected
last_reviewed: <YYYY-MM-DD>
---

# <Title>

## Context

<What was happening at the adopter side. Cite project + sprint or milestone id.
Set the stage so the framework maintainer can place this lesson in time and
across the broader adopter pool.>

## Observation

<What was observed; what did NOT work as the framework specified, OR what
worked but was non-obvious from the docs.>

## Hypothesis

<Why. Rooted in code, trace, or specific framework wording. Cite Δ-N + file
paths. Not "we think it's hard" — "the framework's Δ-X says Y but in practice
we hit Z because <root cause>".>

## Proposed amendment (optional)

<What Δ revision would help. Suggested wording, if you have one. The framework
maintainer's job at fold-back is to evaluate whether your proposed amendment
fits other adopters' contexts too.>

## Rejection rationale (filled by maintainer if rejected)

<Why this lesson didn't fold back. Names the framework's intentional design
choice OR the trade-off the lesson would have introduced. If filled, this
section is the explanation future adopters can read in archive/rejected-lessons/.>
```

## Filing checklist

- [ ] The lesson is durable — not a transient project artifact (e.g., "this sprint our team was confused" is not enough; "the framework's Δ-N wording around X caused confusion" is the durable form).
- [ ] At least one `related_delta` is named (or `category: divergence-rationale` if the lesson is informational only).
- [ ] The `category` accurately reflects the lesson's nature (incident / observation / proposed-amendment / divergence-rationale / safety).
- [ ] `status: proposed`.
- [ ] The lesson body is intermediate-grade: complete + self-contained at filing; will not be re-edited later.
- [ ] If `category: safety`, expect higher-priority review (per `process/fold-back-protocol.md` §6 anti-pattern: rejection without rationale is FORBIDDEN for safety lessons).

## Categories

- `incident` — something broke in adoption (urgent; may trigger out-of-cadence fold-back).
- `observation` — a pattern the adopter noticed (most common category).
- `proposed-amendment` — adopter proposes a specific framework wording change.
- `divergence-rationale` — adopter documents why they diverge (informational; framework doesn't act on it).
- `safety` — security / correctness / safety concern (CRITICAL trigger per fold-back-protocol §2.3).

## Status lifecycle

```
proposed                       (adopter files; lesson is frozen)
  ↓
under-review                   (maintainer is evaluating at fold-back)
  ↓
accepted | rejected
  ↓
accepted: lesson archived; revised Δ doc links back to lesson
rejected: moves to archive/rejected-lessons/<date>-<topic>.md
          with the Rejection rationale section filled
```

The `status:` field is updated by a new commit on the lesson file, NOT by editing the body. The body stays frozen at filing.

## Template usage notes

- Lessons are PROPOSALS, not auto-merged (per `process/fold-back-protocol.md` §1.1).
- The framework maintainer reviews at fold-back cadence (per `process/fold-back-protocol.md` §2): 5 adoptions / 6 months / critical-pattern trigger.
- Cross-adopter patterns matter most — a single adopter's quirk rarely warrants a Δ revision; 3+ adopters reporting the same friction usually does.
- Lessons that don't cite a Δ + a hypothesis tend to get rejected — they're observations without a path to action.

---

End of lessons-learned template.
