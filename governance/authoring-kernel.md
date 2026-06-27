---
title: aidazi Doc Governance — Authoring Kernel (always-load derived projection)
doc_tier: governance
doc_category: live
load_discipline: always-load
derived_from: governance/doc_governance.md
source_of_truth: >
  governance/doc_governance.md is the SOLE canonical normative source for doc governance.
  This file is a machine-checked, always-load DERIVED PROJECTION of its proactive HARD
  constraints — meaning-preserving compressions, NOT a second source of truth; the clause
  text is paraphrased, not verbatim (only the enumerated allowed-VALUES — the doc_tier /
  status / implementation_status / load_discipline / doc_category enums — are reproduced
  exactly, because the enumeration IS the constraint). On ANY disagreement between this
  projection and the canonical doc_governance.md, the canonical wins and the role MUST load
  it (see "Authority & conflict handling"). Completeness is machine-proven against the WP-EQ
  constraint inventory (engine-kit/tools/constraint-inventory/03-doc-governance.yaml via
  kernel_equivalence.py --authoring-kernel-coverage); a source-hash change to the canonical
  fails this projection stale (re-derive + re-review).
supersedes: []
superseded_by: null
size_target: 12KB
status: current — always-load at role-session cold-start step 2 (replaces doc_governance.md; full canonical on-demand). Codex-APPROVED; 41/41 machine-proven; Acceptance resolver-bound (fail-closed).
notes: >
  Compressed expression, never deferred constraint (context/token-optimization §A). Designed
  to replace governance/doc_governance.md at role-session cold-start step 2; the full
  canonical doc_governance.md loads on-demand (context_briefing §2.6 "Doc lifecycle question").
---

# aidazi Doc Governance — Authoring Kernel (derived projection)

The proactive HARD constraints every role must hold when it authors, edits, marks, or
reconciles a governed doc, compressed to imperative clauses from the canonical
`governance/doc_governance.md`. This projection is loaded at role-session cold-start step 2;
the full canonical doc_governance.md loads on-demand (see triggers below) for field-intent
prose, the full tier tables, the closure_contract template, lifecycle rationale, and any
mechanics not reproduced here.

**Tag legend.** Every clause is a meaning-preserving compression of its cited canonical anchor.
- `[ENF: <symbol>]` — AUDIT METADATA only: a programmatic backstop (a schema validator or a
  role-card boundary) also catches violations. It does NOT reduce the role's duty to
  proactively follow the constraint and self-check it; treat the constraint as binding
  regardless of the tag.
- `[JUDGMENT]` — NO programmatic backstop exists: this projection + the role-card self-check
  are the ONLY catch. (No Python validator enforces doc front-matter today.)

## Authority & conflict handling (read first)

- The canonical `governance/doc_governance.md` is the SOLE normative source for how docs are
  written, marked, reconciled, and folded back. This projection never overrides it and never
  decides a question it does not unambiguously answer.
- **Conflict → HALT.** If this projection appears to disagree with the canonical doc_governance,
  or is silent/ambiguous on the point in hand, you MUST NOT self-select an interpretation: load
  the canonical section and follow it; if still ambiguous, surface it.
- **Load the full doc_governance.md on-demand (do not self-infer before loading) when you hit:**
  (a) a doc-lifecycle question this kernel does not unambiguously answer; (b) a fold-back or
  archive PROCEDURE detail; (c) the cell-size override mechanics; (d) a doc-tier/anatomy table
  lookup; (e) any question about editing a governance-tier doc. The §2.6 "Doc lifecycle
  question" route loads it.

## §1 Front-matter

- Every governed doc MUST carry a YAML front-matter block at the very top of the file. [JUDGMENT]
- Front-matter MUST declare title, doc_tier, doc_category, status, implementation_status,
  source_of_truth, last_reviewed, review_cadence, supersedes, superseded_by, load_discipline,
  size_target, and split_trigger. [JUDGMENT]
- New docs MUST include front-matter from day one; only legacy docs may be marked in follow-up
  PRs. [JUDGMENT]

## §2 Allowed values (the enumerations ARE the constraint)

- `doc_tier` MUST be one of the enumerated framework/adopter tier values, and the doc MUST live
  in that tier's designated directory. (Framework: governance, process, role-card, template,
  application-guide, schema, module, example, archive. Adopter: current-runtime, foundational,
  durable-connective, sprint-archive, proposal, diagnostic, failure-brief, research-brief,
  acceptance-report, runbook, reference, archived.) [JUDGMENT]
- `status` MUST be one of current, proposal, partial, deferred, diagnostic, archived, or
  superseded. [JUDGMENT]
- `implementation_status` MUST be one of implemented, partial, not_started, historical, or
  unknown. [JUDGMENT]

## §3 Load discipline

- Each governed doc MUST declare exactly one load_discipline value of always-load, on-demand, or
  by-role. [JUDGMENT]
- always-load MUST be reserved for governance-tier docs; other docs MUST NOT be marked
  always-load. [JUDGMENT]
- Promoting an on-demand doc to always-load MUST go through a fold-back proposal with a
  bloat-cost evaluation. [JUDGMENT]

## §4 Closure contract (Research-authored; load-bearing body section)

- Every docs/research-briefs/<id>.md MUST contain a closure_contract load-bearing body section.
  [ENF: schema:research-brief.schema.json]
- The closure_contract MUST contain Positive shape, Anti-pattern, and at least one Anchor phrase.
  [ENF: schema:research-brief.schema.json]
- Anchor phrases MUST be treated as supporting evidence only and MUST NOT be used as
  regex/literal matchers. [JUDGMENT]
- The closure_contract MUST NOT change between gate-1 sign-off and the milestone's Acceptance
  run without Customer re-sign-off. [JUDGMENT]
- The Research role authors docs/research-briefs/<id>.md, carrying the closure_contract plus
  scope IN/OUT, anti-goal, and KPI. [ENF: role-card:role-cards/research-agent.md]

## §5 Live vs intermediate lifecycle

- `doc_category` MUST be either live or intermediate. [JUDGMENT]
- A live doc MUST be kept current and MUST carry last_reviewed, review_cadence, and
  source_of_truth. [JUDGMENT]
- An intermediate doc is frozen at creation; edits MUST be limited to typos/broken-link fixes,
  semantic edits are forbidden, and a change of meaning MUST be filed as a new doc referencing
  the old one. [JUDGMENT]

## §6 Cell size

- Table-cell docs such as handoff §0 declare a cell_size_target front-matter field (default 500
  chars) as a soft cold-start-readability signal. [JUDGMENT]
- Raising cell_size_target above the default MUST record the rationale in
  docs/current/adoption-state.md. [JUDGMENT]

## §7 Decision rules (doc ↔ code reconciliation)

- **§7.1 code ahead of docs.** When delivered reviewed code diverges from a doc, confirm the
  code is intentional and update the doc to reflect delivered behavior, preferring the
  lowest-tier doc that captures the change. [JUDGMENT]
- **§7.1 no silent foundational rewrite.** A materially-misleading foundational spec MUST be
  marked with implementation_status plus a notes pointer to the reconciliation file, and MUST
  NOT be silently rewritten sprint-by-sprint. [JUDGMENT]
- **§7.1 no rollback to a stale doc.** Code MUST NOT be rolled back to match a stale doc unless
  the code is independently wrong. [JUDGMENT]
- **§7.2 docs ahead of code.** When a doc describes not-yet-shipped behavior, keep the doc and
  mark it status proposal|partial|deferred with implementation_status not_started|partial.
  [JUDGMENT]
- **§7.2 superseded, not deleted.** When a different approach ships, set superseded_by and add
  the replacement; the original MUST NOT be deleted. [JUDGMENT]
- **§7.3 true conflict.** A conflict between two comparable-tier governed docs that code does not
  clearly resolve MUST be handled as a governance task by opening a docs/current/ reconciliation
  note naming both docs, the disagreement, and the proposed resolution. [JUDGMENT]
- **§7.3 mark the loser (or both partial).** On conflict resolution, mark the non-authoritative
  doc with superseded_by or a notes pointer; if unresolvable without a code/product decision,
  mark both docs partial and capture the open question. [JUDGMENT]
- **§7.4 no silent stale-ref delete.** A stale reference MUST NOT be silently deleted; it MUST be
  fixed (moved target → update the link; a target deleted intentionally → inline summary plus
  sprint-archive pointer; code target → link a stable dir/file not a specific line, unless the line
  itself is the contract) or annotated. [JUDGMENT]
- **§7.5 proposals stay visible + explicit.** Forward-looking proposal docs MUST live alongside
  foundational docs (not hidden in archives), and their status MUST make the forward-looking
  nature explicit. [JUDGMENT]
- **§7.5 superseded proposal stays in tree.** A superseded proposal MUST stay in the tree with
  status superseded and superseded_by pointing at the replacement. [JUDGMENT]

## §8 Fold-back cadence

- Framework-side foundational docs MUST NOT be patched every sprint; they are folded forward
  only at fold-back sub-sprint cadence. [JUDGMENT]
- At fold-back, read the relevant reconciliation notes, sprint archives, lessons, and code,
  update the foundational doc, bump last_reviewed, and set folded-in redundant reconciliation
  notes to status archived. [JUDGMENT]
- Sprint archives MUST NEVER be edited during fold-back; they remain the immutable record of
  what each sprint delivered. [JUDGMENT]

## §9 Archive operations

- When archiving a live file at sprint close, commit the current working-tree state first, then
  git mv the file to its archive path, then add the replacement live file. [JUDGMENT]
- Lessons rejected at fold-back MUST be archived to archive/rejected-lessons/<date>-<topic>.md.
  [JUDGMENT]

## §11 Editing governed (governance-tier) docs

- Edits to governance/doc_governance.md MUST land only at fold-back sub-sprint cadence.
  [JUDGMENT]
- Edits to this governance doc MUST satisfy the editing-discipline checklist — timelessness,
  principle-vs-current-state, necessity, durable-shift-vs-reaction. [JUDGMENT]
- Adopters MUST NOT edit governance/doc_governance.md; per-project overrides go in
  docs/current/adoption-state.md divergence rows. [JUDGMENT]

## Per-role authoring boundaries (governed-artifact ownership)

- The Acceptance role authors the acceptance verdict JSON, docs/acceptance-reports/<scope>-acceptance-report.md,
  and the required human-confirm checkpoint under docs/checkpoints/ (on fix_required), with no
  write access outside docs/acceptance-reports/ and docs/checkpoints/.
  [ENF: role-card:role-cards/acceptance-agent.md]
- The Deliver role authors the handoff §0 cold-start scaffold and writes the §12 close verdict
  (Deliver + Customer co-sign). [ENF: role-card:role-cards/deliver-agent.md]
- The Dev role is sole author of handoff §1-§11, MUST NOT write §12, and does not author §0.
  [ENF: role-card:role-cards/dev-agent.md]
- The Code Reviewer writes/appends docs/codex-findings.md (single append-only file) and MUST NOT
  edit any file outside it. [ENF: role-card:role-cards/code-reviewer-agent.md]

---

## Deferred to the canonical `governance/doc_governance.md` (load on-demand — these are NOT constraints)

§1 field-intent prose (what each front-matter field means) · §2 the full framework/adopter
doc-tier tables with per-tier descriptions + the status / implementation_status value
descriptions · §4 the closure_contract markdown template + the research-brief JSON-schema
pointer · §5 the typical live/intermediate doc lists + the doc-drift failure-mode rationale ·
§6 the cell-size rationale + the override procedure detail (Constitution §7.2) · §8 adopter-side
patch cadence + the "untouched many cadence intervals" fold-back signal · §9 the git-mv
archive-vs-working-tree explanation + the milestone-framework pointer · §10 doc-bloat-prevention
mechanics (pointer to process/self-governance.md) · §11 the constitution §8 editing-discipline
rationale · and all "Why" / "How to apply" / worked-example prose.
