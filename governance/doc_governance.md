---
title: aidazi Doc Governance
doc_tier: governance
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-07
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: always-load
size_target: 20KB
split_trigger: if any single section grows past 4KB, move detail to a process/ doc and leave a one-line stub
notes: >
  Layer-A always-loaded doc-governance rulebook. Defines front-matter schema,
  allowed values, decision rules (code-ahead-of-docs / docs-ahead-of-code /
  true-conflict / stale-references / future-proposals), live-vs-intermediate
  lifecycle (Δ-4), closure_contract field requirement, cell_size_target field
  (suggested per §7.0), fold-back cadence, and editing discipline.
  Companion of constitution.md and context_briefing.md.
---

# aidazi Doc Governance

This is the operational rulebook for how docs in the framework AND in adopter repos are written, marked, reconciled with code, and folded back into foundational specs.

The Constitution (`governance/constitution.md`) defines ownership boundaries and forbidden patterns. The Doc Governance (this file) defines how docs themselves are structured + lifecycle-managed. Cold-start reading discipline + per-task reading lists live in `governance/context_briefing.md`.

This file describes principles + schemas. Specific doc bloat metrics + sweep cadences live in `process/self-governance.md`. Adopter ↔ framework fold-back protocol lives in `process/fold-back-protocol.md`.

## §1 Front-matter schema

Every governed doc carries a YAML front-matter block at the top:

```yaml
---
title: <human-readable title>
doc_tier: <see allowed values §2>
doc_category: <live | intermediate>
status: <see allowed values §2>
implementation_status: <see allowed values §2>
source_of_truth: <code path | this file | other doc path | external system>
last_reviewed: <YYYY-MM-DD>
review_cadence: <"every fold-back sub-sprint" | "per milestone close" | "per sprint" | "ad hoc">
supersedes: [<paths of docs this one replaces>]
superseded_by: <path | null>
load_discipline: <always-load | on-demand | by-role>
size_target: <KB>
split_trigger: <description of when to split>
cell_size_target: <chars; for table-cell docs like handoff §0>  # SUGGESTED per §7.0 of constitution
closure_contract: <required for Research Agent's research-brief artifacts; see §4>
notes: >
  free-form context, often more useful than the body for triage.
---
```

**Field intent**:

- `title` — short label; the H1 may be longer.
- `doc_tier` — which framework tier this doc belongs to (see §2).
- `doc_category` — `live` (kept current; has `last_reviewed`) or `intermediate` (frozen at creation; see §5).
- `status` — current state as a contract.
- `implementation_status` — whether the *behavior* described is delivered. Separate from `status` (a `current` doc may describe `partial` behavior).
- `source_of_truth` — where to look if doc and reality disagree.
- `last_reviewed` — date of last intentional read-through.
- `review_cadence` — how often the doc is expected to be revisited.
- `supersedes` / `superseded_by` — explicit links across replacements.
- `load_discipline` — when the doc loads into a role's session (see §3).
- `size_target` — soft budget; PR reviewer flags growth past target.
- `split_trigger` — description of when to split (Δ-10).
- `cell_size_target` — for table-cell docs (handoff §0); suggested 500 chars per §7.0 of constitution.
- `closure_contract` — REQUIRED for `docs/research-briefs/<id>.md` artifacts; see §4.
- `notes` — free-form context.

Front-matter is added incrementally. New docs MUST include it from day one; legacy docs are marked in follow-up PRs.

## §2 Allowed values

### §2.1 `doc_tier`

Framework-side tiers:

- `governance` — Layer A always-loaded; lives in `governance/`.
- `process` — Layer B on-demand by role; lives in `process/`.
- `role-card` — activation prompts for each role; lives in `role-cards/`.
- `template` — copyable templates for adopter instantiation; lives in `templates/`.
- `application-guide` — adopter-facing onboarding/operational guidance; lives in `docs/`.
- `schema` — JSON schemas for verdict shapes; lives in `schemas/`.
- `module` — module specs (M-Evaluation, M-Trace, M-Autoloop); lives in `modules/`.
- `example` — read-only worked examples; lives in `examples/`.
- `archive` — preserved for history; lives in `archive/`.

Adopter-side tiers (in the adopter repo):

- `current-runtime` — describes today's runtime contract; lives in `docs/current/`.
- `foundational` — durable architecture, business intent, normative freezes; `docs/foundational/`.
- `durable-connective` — long-lived cross-cutting agreement (vocabulary, governance) that is not itself a runtime contract.
- `sprint-archive` — frozen per-sprint objective, handoff, or review; `docs/sprints/<sprint-id>/`.
- `proposal` — forward-looking design that has not fully landed; `docs/proposals/`.
- `diagnostic` — audit, post-mortem, measurement write-up; `docs/diagnostics/`.
- `failure-brief` — formal customer-facing failure shape report; `docs/diagnostics/failure-briefs/`.
- `research-brief` — formal Research Agent output with closure_contract; `docs/research-briefs/`.
- `acceptance-report` — Acceptance Agent verdict; `docs/acceptance-reports/`.
- `runbook` — operational steps, on-call procedures, admin guides.
- `reference` — lookup material.
- `archived` — kept for history; no longer in any active tier.

### §2.2 `status`

- `current` — actively maintained; expected to track reality.
- `proposal` — describes intended future behavior.
- `partial` — some described behavior is implemented; the rest is not.
- `deferred` — design is preserved but explicitly paused.
- `diagnostic` — point-in-time observation; not a contract.
- `archived` — preserved for history; not maintained.
- `superseded` — replaced by another doc; see `superseded_by`.

### §2.3 `implementation_status`

- `implemented` — delivered behavior matches what the doc describes.
- `partial` — some described behavior is delivered; some is not.
- `not_started` — described behavior has not shipped.
- `historical` — the described behavior used to ship; the system has moved on.
- `unknown` — explicitly unverified. Agents treat as a warning.

A doc MAY be `status: current` AND `implementation_status: partial` at the same time — that is the normal state for an actively-maintained governance doc covering a feature still being built out.

## §3 Load discipline

Each governed doc declares one of:

- **`always-load`** — every cold-start session loads this. Reserved for governance tier: `governance/constitution.md`, `governance/doc_governance.md`, `governance/context_briefing.md`.
- **`on-demand`** — load when the role's session needs it. Most `process/*` docs are on-demand; the cold-start session does NOT pre-load them.
- **`by-role`** — role-card style; load when adopting that role. `role-cards/*` are by-role.

`always-load` is expensive (token cost); reserve for docs whose absence would systemically degrade behavior. Process docs that have evolved into "I always need this" candidates → propose promotion to `always-load` at fold-back, with bloat-cost evaluation.

## §4 Closure contract field requirement

The `closure_contract` body section (NOT a front-matter field — it's a load-bearing body section) is REQUIRED on every `docs/research-briefs/<id>.md` artifact.

Schema for the closure_contract section (per §1.7-B of constitution):

```markdown
## Closure contract

**Positive shape** (what good delivered behavior looks like, from customer perspective):
<1-2 paragraphs>

**Anti-pattern** (what bad behavior looks like — the failure shape this milestone targets):
<1 paragraph; cites known failure mode if applicable>

**Anchor phrases** (exemplar phrases from expected response; SUPPORTING evidence, not regex matchers):
- "<phrase 1>"
- "<phrase 2>"
- ...
```

Per `process/delivery-loop.md`, the Acceptance Agent reads this closure_contract and judges delivered behavior against it.

The closure_contract MAY NOT change between gate 1 sign-off and the milestone's Acceptance run without Customer re-sign-off (Constitution §3.4 boundary invariant #4: Research-Acceptance contract symmetry).

JSON schema: `schemas/research-brief.schema.json`.

## §5 Live vs intermediate lifecycle (Δ-4)

The `doc_category:` front-matter field is the lifecycle classifier.

- **`live`** — actively maintained against reality. Has `last_reviewed`, `review_cadence`, `source_of_truth`. MUST be kept current.
- **`intermediate`** — frozen at creation. Named with sprint ID or date. Modifications are limited to typos and broken-link fixes; semantic edits are forbidden — file a new doc that references the old one.

This split prevents the failure mode where a design doc gets handed to a coding agent and then never updated for half a year, drifting from reality but still cited.

Typical `live` docs:
- All `governance/*` docs.
- `docs/current/*` in adopter repos (domain context, runtime invariants, etc.).
- `docs/research-briefs/<id>.md` (live until milestone close; then archived).
- `docs/action_bank.md`.
- `docs/current/adoption-state.md`.

Typical `intermediate` docs:
- All sprint archives.
- `docs/proposals/<id>.md` (informal exploration; frozen at creation).
- `docs/diagnostics/<id>.md` (mid-sprint root-cause notes).
- `docs/diagnostics/failure-briefs/<id>.md` (formal failure shape; frozen).
- `lessons/<date>-<topic>.md` (frozen at filing; per §7.6 of constitution).

## §6 Cell size target (suggested per §7.0 of constitution)

For table-cell docs like `handoff.md` §0 cold-start cells, the `cell_size_target:` front-matter declares a SUGGESTED soft target.

Default: **500 chars per cell**.

Rationale: csagent practice revealed §0 cells naturally grow to multi-thousand-char paragraphs, eroding cold-start readability. The 500-char target is a soft signal that cold-start cells should reference §1 narrative for detail, not duplicate it inline.

Override procedure (per Constitution §7.2): if your adopter project's cells naturally carry more context (multi-team production project; dense state; mature project), raise the target to 800 or 1000 with rationale in `docs/current/adoption-state.md`.

This is NOT a hard gate. PR reviewers may flag bloat past the chosen target as an R-item candidate, not as a blocker.

## §7 Decision rules

### §7.1 Code ahead of docs

When the running, reviewed, delivered code does something different from what a doc describes:

1. Confirm the code is intentional (review history, sprint archives, tests).
2. Update the doc to reflect the delivered behavior. Prefer the lowest-tier doc that captures the change — usually a `docs/current/*` reconciliation note now, with a fold-back into the relevant foundational doc on the normal cadence.
3. If the foundational doc is materially misleading, mark its `implementation_status` (e.g., `partial`) and add a `notes:` pointer to the reconciliation file. Do NOT silently rewrite a foundational spec sprint-by-sprint.
4. Never roll back code to match a stale doc unless the code itself is independently wrong.

### §7.2 Docs ahead of code

When a doc describes behavior the code does not (yet) exhibit:

1. Keep the doc.
2. Mark it: `status: proposal | partial | deferred`, and set `implementation_status: not_started | partial`.
3. If a different approach has shipped, set `superseded_by:` and add the replacement; do NOT delete the original.
4. Forward-looking design content is an asset. Removing it loses the reasoning, which is usually the most expensive part to recover.

### §7.3 True conflict

When two governed docs of comparable tier disagree, and code does not clearly resolve it:

1. Treat the conflict as a governance task, not an editing task. Open a reconciliation note in `docs/current/` that names both docs, the disagreement, and the proposed resolution.
2. Resolve by deciding which doc is the source of truth for that question, and mark the other with `superseded_by:` or a `notes:` entry pointing to the reconciliation note.
3. If the conflict cannot be resolved without a code or product decision, mark both docs `partial` and capture the open question in the reconciliation note rather than picking arbitrarily.

### §7.4 Stale references

Cross-doc links and citations rot. When you find a stale reference:

- If the target moved, update the link.
- If the target was deleted intentionally, replace the reference with a short inline summary plus a pointer to the relevant sprint archive.
- If the reference points at code, prefer linking to a stable directory or file rather than a specific line, unless the line itself is the contract.

Do NOT silently delete a stale reference. Either fix it or annotate it.

### §7.5 Future proposals

Forward-looking proposal docs are first-class citizens of the repo.

- They live alongside foundational docs, not hidden in archives.
- Their `status` should make the forward-looking nature explicit.
- When a proposal is partially implemented, prefer `implementation_status: partial` plus a short paragraph identifying which parts shipped and which did not, over silent edits.
- A superseded proposal stays in the tree with `status: superseded` and `superseded_by:` pointing at the replacement.

## §8 Fold-back cadence

Framework-side foundational docs (Constitution, Δ-N process docs) are NOT patched every sprint. They are folded forward at fold-back sub-sprint cadence per `process/fold-back-protocol.md`.

Adopter-side `current/*` docs ARE patched more frequently (per milestone close or per sprint close, depending on cadence declared in front-matter).

**At fold-back**:
- Read relevant `docs/current/*` reconciliation notes, recent sprint archives, lessons in `aidazi/lessons/`, and code.
- Update the foundational doc.
- Bump `last_reviewed`.
- After fold-back, reconciliation notes that were folded in get `status: archived` if their content is now redundant.

**Sprint archives themselves are never edited during fold-back.** They remain the immutable record of what each sprint actually delivered.

If a foundational doc has not been touched in many cadence intervals AND the system has moved, that is a fold-back signal even if no individual sprint produced a "big" change.

## §9 Archive operations

`git mv` archives HEAD/index content, not working-tree content. When archiving sprint_objective or other live files at sprint close:

1. Commit current working-tree state first.
2. Then `git mv` the file to its archive path.
3. Then add the replacement live file (if the lifecycle creates a new live doc per sprint).

For sprint close mechanics, see `process/milestone-framework.md`.

For lessons that get rejected at fold-back, archive to `archive/rejected-lessons/<date>-<topic>.md` per `process/self-governance.md` §7.6.

## §10 Doc bloat prevention (pointer)

The structural mechanisms that prevent doc bloat (size_target front-matter; cell_size_target; action_bank live + archive split; intermediate lifecycle; compact prompt context_budget) are inventoried in `process/self-governance.md`.

This doc declares the schema; that doc explains the mechanics + cadence.

## §11 Editing this doc

`governance/doc_governance.md` is itself a governance-tier doc. Edits land at fold-back sub-sprint cadence (per Constitution §8). The editing discipline checklist from Constitution §8 applies:

1. Timelessness (no sprint numbers / dates / project names).
2. Principle vs current-state (governance teaches principles).
3. Necessity (would a process doc or sprint archive carry this content?).
4. Durable shift vs reaction.

Adopters do not edit this file. Per-project doc-governance overrides live in `docs/current/adoption-state.md` divergence rows.

---

End of Doc Governance.
