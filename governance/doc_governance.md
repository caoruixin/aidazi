---
title: Doc governance
doc_tier: current-runtime
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-05-28
review_cadence: every 3-5 sprints
supersedes: []
superseded_by: null
notes: >
  Defines the doc front matter schema, decision rules, fold-back
  cadence, and agent responsibilities for doc work. The repo-level
  overview lives in your consumer project's `docs/README.md` (or
  equivalent).
---

# Doc governance

This document is the operational rulebook for how docs in a project
consuming `aidazi` are written, marked, reconciled with code, and
folded back into foundational specs.

## Tier model

Every doc belongs to one of these tiers. The tier model is enforced via
the `doc_tier` front-matter field.

| Tier | Location | Edit cadence | Character |
|------|----------|--------------|-----------|
| **Foundational** | `docs/foundational/` | Slow; fold-back every 3–5 sprints | Durable architecture, intent, normative freezes |
| **Current runtime / durable connective** | `docs/current/*` | Edit eagerly; stale = bug | Short, maintained runtime contracts + cross-cutting governance |
| **Sprint archive** | `docs/sprints/*`, `docs/archive/*` | **Never edit after close** | Immutable per-sprint record |
| **Proposal** | `docs/proposals/`, `docs/solutions/` | Keep; mark status | Forward-looking / partial designs |
| **Diagnostic / runbook / reference** | various | Edit when system changes | Audits, ops, lookup material |

**Source-of-truth hierarchy** (used when artefacts disagree):

```
code > current > foundational > proposal > archive
```

This is the default rule. If a `current-runtime` doc claims X and the
code does Y, code wins and the doc is reconciled (see §Decision rules).

## Front matter schema

Every governed doc should carry a YAML front matter block at the top:

```yaml
---
title: <human-readable title>
doc_tier: <see allowed values below>
status: <see allowed values below>
implementation_status: <see allowed values below>
source_of_truth: <code path | this file | other doc path | external system>
last_reviewed: <YYYY-MM-DD>
review_cadence: <e.g. "every 3-5 sprints" | "per sprint" | "ad hoc">
supersedes: [<paths of docs this one replaces>]
superseded_by: <path | null>
notes: >
  free-form. Useful for capturing scope, what is intentionally out of scope,
  and known drift areas.
---
```

Field intent:

- **title** — short label; the H1 may be longer.
- **doc_tier** — which of the tiers above.
- **status** — current state of the doc as a contract.
- **implementation_status** — whether the *behavior* the doc describes
  is delivered. Separate from `status`: a `current` doc may describe
  behavior that is `partial`.
- **source_of_truth** — where to look if this doc and reality disagree.
  Often a code path; sometimes "this file" (when the doc itself is the
  governing contract); sometimes another doc.
- **last_reviewed** — date of the last intentional read-through against
  reality. Stale dates are a signal, not a failure.
- **review_cadence** — how often the doc is expected to be revisited.
- **supersedes / superseded_by** — explicit links across replacements.
- **notes** — free-form context, often more useful than the body for an
  agent doing triage.

Front matter is added incrementally. New docs should include it from
day one; existing docs (in brownfield adoption) will be marked over
follow-up passes.

## Allowed values

### `doc_tier`

- `current-runtime` — describes today's runtime contract; lives in
  `docs/current/`.
- `foundational` — durable architecture, business intent, normative
  freezes.
- `durable-connective` — long-lived cross-cutting agreement
  (vocabulary, governance, reconciliation) that is not itself a runtime
  contract but is expected to outlive any single sprint.
- `sprint-archive` — frozen per-sprint objective, handoff, or review.
- `proposal` — forward-looking design that has not fully landed.
- `diagnostic` — audit, post-mortem, or measurement write-up.
- `runbook` — operational steps, on-call procedures, admin guides.
- `reference` — lookup material (API references, datasets, taxonomies).
- `archived` — kept for history but no longer in any active tier.

### `status`

- `current` — actively maintained; expected to track reality.
- `proposal` — describes intended future behavior.
- `partial` — some of what this doc describes is implemented; the rest
  is not.
- `deferred` — design is preserved but explicitly paused.
- `diagnostic` — represents a point-in-time observation; not a contract.
- `archived` — preserved for history; not maintained.
- `superseded` — replaced by another doc; see `superseded_by`.

### `implementation_status`

- `implemented` — delivered behavior matches what the doc describes.
- `partial` — some described behavior is delivered; some is not.
- `not_started` — described behavior has not shipped.
- `historical` — the described behavior used to ship; the system has
  moved on. Common for sprint archives and diagnostics.
- `unknown` — explicitly unverified. Agents should treat this as a
  warning.

A doc may be `status: current` and `implementation_status: partial` at
the same time — that is the normal state for an actively-maintained
governance doc covering a feature still being built out.

## Decision rules

### Code ahead of docs

When the running, reviewed, delivered code does something different
from what a doc describes:

1. Confirm the code is intentional (review history, sprint archives,
   tests).
2. Update the doc to reflect the delivered behavior. Prefer the
   lowest-tier doc that captures the change — usually a
   `docs/current/*` reconciliation note now, with a fold-back into the
   relevant foundational doc on the normal cadence.
3. If the foundational doc is materially misleading, mark its
   `implementation_status` (e.g. `partial`) and add a `notes:` pointer
   to the reconciliation file. Do not silently rewrite a foundational
   spec sprint-by-sprint.
4. Never roll back code to match a stale doc unless the code itself is
   independently wrong.

### Docs ahead of code

When a doc describes behavior the code does not (yet) exhibit:

1. Keep the doc.
2. Mark it: `status: proposal | partial | deferred`, and set
   `implementation_status` to `not_started` or `partial`.
3. If a different approach has shipped, set `superseded_by:` and add
   the replacement; do not delete the original.
4. Forward-looking design content is an asset. Removing it loses the
   reasoning, which is usually the most expensive part to recover.

### True conflict

When two governed docs of comparable tier disagree, and code does not
clearly resolve it:

1. Treat the conflict as a governance task, not an editing task. Open
   a reconciliation note in `docs/current/` that names both docs, the
   disagreement, and the proposed resolution.
2. Resolve by deciding which doc is the source of truth for that
   question, and mark the other with `superseded_by:` or a `notes:`
   entry pointing to the reconciliation note.
3. If the conflict cannot be resolved without a code or product
   decision, mark both docs `partial` and capture the open question in
   the reconciliation note rather than picking arbitrarily.

### Stale references

Cross-doc links and citations rot. When you find a stale reference:

- if the target moved, update the link;
- if the target was deleted intentionally, replace the reference with
  a short inline summary plus a pointer to the relevant sprint archive;
- if the reference points at code, prefer linking to a stable directory
  or file rather than a specific line, unless the line itself is the
  contract.

Do not silently delete a stale reference. Either fix it or annotate it.

### Future proposals

Forward-looking proposal docs are first-class citizens.

- They live alongside foundational docs, not hidden in archives.
- Their `status` should make the forward-looking nature explicit.
- When a proposal is partially implemented, prefer
  `implementation_status: partial` plus a short paragraph identifying
  which parts shipped and which did not, over silent edits.
- A superseded proposal stays in the tree with `status: superseded`
  and `superseded_by:` pointing at the replacement.

## Fold-back cadence

Foundational docs are not patched every sprint. Instead, we fold sprint
deltas back into them on a cadence:

- **Default**: every 3–5 sprints, or when a foundational doc visibly
  drifts from delivered behavior in a way that is misleading new
  readers.
- During fold-back: read the relevant `docs/current/*` reconciliation
  notes, the last few sprint archives, and the code; update the
  foundational doc; bump `last_reviewed`.
- After fold-back: the reconciliation notes that were folded in should
  point to the updated foundational section and be marked
  `status: archived` if their content is now redundant.
- Sprint archives themselves are never edited during fold-back. They
  remain the immutable record of what each sprint actually delivered.

If a foundational doc has not been touched in many sprints and the
system has moved, that is a fold-back signal even if no individual
sprint produced a "big" change.

**Archive operation note**: `git mv` archives HEAD/index content, not
working-tree content. When archiving sprint_objective or other live
files at close, stage working-tree modifications first, then rename;
otherwise the archive captures stale content and requires a fixup
commit.

## Agent responsibilities for doc work

Two agent roles share doc responsibilities (specific role names vary
by tool stack — Claude Code, Codex, Cursor, GPT, etc.; the framework
uses the generic terms `dev agent` and `review agent`):

- **Dev agent** drafts docs diffs. It cites code paths for any claim
  about delivered behavior, names the tier and status it intends to
  set, and surfaces docs that may need to be marked `superseded_by:` as
  a side effect. The dev agent prefers minimal, reversible edits and
  writes reconciliation notes rather than rewriting foundational docs
  in place.
- **Review agent** verifies accuracy, scope, and source-of-truth
  decisions. It re-reads the cited code, checks that the proposed tier
  and status match reality, flags scope creep (e.g. an edit that
  quietly rewrites a foundational doc when a `docs/current/*` note
  would do), and confirms that no sprint archive is being edited.

Either agent may identify a need for the other; neither is expected to
be authoritative alone. A docs PR should reflect both passes.

## `10-handoff.md` retention rule

`docs/10-handoff.md` is a cross-session state file, not a growing
history log. It uses a three-section structure with a retention window:

- **§0 — Cold-start table**: always current. Deliver-agent replaces it
  at each sub-sprint or milestone close. Agents read §0 first on cold
  start.
- **§1 — Narrative**: retains at most the **current milestone context**
  (active milestone lead + active sub-sprint details) plus the **last
  closed milestone** summary paragraph with archive pointer. One-line
  summaries for earlier milestones are kept only until the §2 archive
  index captures them.
- **§2 — Milestone archive index**: a compact table of all closed
  milestones with status, close date, and archive path. Updated by the
  deliver-agent at each milestone close.

**Retention window**: at each **milestone close**, the deliver-agent:

1. Writes the new milestone close lead to §1 (replacing the prior lead).
2. Compresses the prior §1 content that is now fully archived (its
   detailed sub-sprint paragraphs are in `docs/sprints/`; its milestone
   verdict is in `docs/milestones/`). Retains at most a 1-sentence
   summary + archive pointer for the preceding milestone.
3. Adds a row to the §2 archive index.
4. Deletes any §1 content older than the preceding milestone — those
   details live exclusively in the milestone and sprint archives.

**Reading rule for agents**: on cold start, read §0 (structured table)
first. Read §1 only for narrative context on the current / last closed
milestone. Do NOT read §1 expecting full history — use the §2 archive
index to find older milestones, then read the specific archive file.

**Why this rule**: without retention, §1 grows without bound (in
practice tens of K characters after a few dozen sprints). Each
paragraph duplicates information already captured in `docs/sprints/`
and `docs/milestones/` archives. The retention window keeps
`10-handoff.md` usable as a cold-start document while preserving full
history via archive pointers.

## PR checklist for docs-only reconciliation

Before merging a docs-only reconciliation PR:

- [ ] No code files (e.g. `src/`, `server/`, `eval/`, config) were
      edited.
- [ ] No sprint archive (`docs/sprints/*`, `docs/archive/*`) was
      edited.
- [ ] Every claim about delivered behavior cites a concrete code path
      or is explicitly marked as an example / illustration.
- [ ] Every quantitative claim (counts, scores, rates) cites source
      path + extraction method (jq filter, git numstat, script command).
      Unrecorded methodology becomes unverifiable downstream.
- [ ] Front matter is present on new docs and updated on touched docs:
      `doc_tier`, `status`, `implementation_status`, `source_of_truth`,
      `last_reviewed`.
- [ ] If a doc is being replaced, the replacement sets `supersedes:`
      and the original sets `superseded_by:` and `status: superseded`
      rather than being deleted.
- [ ] If forward-looking content is involved, it is marked
      `status: proposal | deferred | partial` rather than removed.
- [ ] If a foundational doc was edited, the change is either a
      scheduled fold-back or a minimal `notes:` / `implementation_status:`
      update; large rewrites belong in a fold-back PR with that intent
      stated.
- [ ] Cross-doc links touched by the change have been checked.
- [ ] The review agent has independently verified scope, accuracy, and
      source-of-truth choices.
