---
title: aidazi v4 build plan — empty-canvas implementation spec
doc_tier: intermediate
doc_category: intermediate
status: proposal
source_of_truth: this file (until execution begins; then archive)
last_reviewed: 2026-06-07
supersedes: [compact/aidazi-v4-reconciliation.md]
notes: >
  Replaces aidazi-v4-reconciliation.md after user's 2026-06-07 decision
  that aidazi/ existing content can be scrapped. v4 builds from scratch.
  
  This plan + compact/framework-plan-v4-2026-06-06.md together = complete
  spec. Future execution agent needs no other inputs (re-reads optional
  but not required).
  
  Empty-canvas assumption: aidazi/ as currently committed (1b93e07) is
  DEPRECATED — its content was early-extraction with wrong premises (4-role
  chain, wrong Acceptance positioning, missing Δ-18). Don't try to preserve
  it. Salvage content from the OLD reconciliation doc (§2 inventory) only
  where v4 has equivalent content (e.g., friction-playbook F1-F12 maps onto
  v4 §10 + §11 pitfalls; some constitution body content is reusable verbatim).
---

# aidazi v4 build plan — empty-canvas implementation

## §0 — Context

**User decision (2026-06-07 turn 3)**: aidazi/ existing content (commit `1b93e07`) is early-extraction; can be scrapped. v4 builds from scratch per `compact/framework-plan-v4-2026-06-06.md` (the v4 plan).

**Why this simplifies things**:
- No AMEND/KEEP/RENAME disposition matrix needed
- No "preserve existing structure" constraint
- Δ-18 renamed from "orchestrator-pattern" to **Delivery Loop** (per v4 §3.6); doc tree reflects this
- Per-file build spec = content sketch + source pointer, not 3-way diff
- Effort is FRESH AUTHORING (~15-25h serial / 10-15h parallel), but spec is simpler

**What this doc replaces**:
- `compact/aidazi-v4-reconciliation.md` — SUPERSEDED 2026-06-07; preserved for historical inventory (§2 of that doc lists what aidazi/ currently has — useful for content salvage)

**What this doc does NOT cover** (per user decisions OQ-V4-014, OQ-V4-015):
- `examples/csagent-reference/` populate — separate plan (deferred; §5.1 of this doc has a trigger guide)
- `examples/hermes-reference/` populate — separate plan (deferred; §5.2 of this doc has a trigger guide + prompt)

---

## §1 — Final aidazi/ target tree

Per v4 plan §6 doc-tree, with Δ-18 renamed to Delivery Loop:

```
aidazi/                                    # framework repo
├── README.md                              # NEW v4 — elevator + read-order
├── AGENTS.md                              # NEW v4 — consumer-side template (5-role; @-includes framework chain)
├── .gitignore
│
├── governance/                            # Layer A — always-loaded
│   ├── constitution.md                    # NEW v4 (some body content salvageable from old)
│   ├── doc_governance.md                  # NEW v4 (some content salvageable)
│   └── context_briefing.md                # NEW v4 (some content salvageable)
│
├── process/                               # Layer B — on-demand by role
│   ├── domain-discovery-process.md        # Δ-2
│   ├── tech-architecture-decision-catalog.md  # Δ-3
│   ├── doc-lifecycle-rules.md             # Δ-4
│   ├── context-passing-efficiency.md      # Δ-5 (also referenced §1.4-i)
│   ├── typeA-runtime-architecture-skeleton.md  # Δ-6
│   ├── worked-example-instance.md         # Δ-7
│   ├── post-deployment-iteration.md       # Δ-9 (OBS triage; AutoLoop module driver)
│   ├── doc-responsibility-matrix.md       # Δ-10
│   ├── artifact-taxonomy.md               # Δ-12 (14 artifacts)
│   ├── capability-staging-roadmap.md      # Δ-11
│   ├── stage-stable-heuristic.md          # Δ-13
│   ├── profile-aware-maturity.md          # Δ-14 (A+B hybrid included)
│   ├── agent-design-elicitation.md        # Δ-15 (closure_contract required field)
│   ├── agent-creation-prerequisites.md    # Δ-16
│   ├── common-detours-and-warnings-typeA.md   # Δ-17-A
│   ├── common-detours-and-warnings-typeB.md   # Δ-17-B placeholder
│   ├── common-detours-and-warnings-typeC.md   # Δ-17-C placeholder
│   ├── delivery-loop.md                   # Δ-18 NEW (renamed from orchestrator-pattern; Concept 2)
│   ├── milestone-framework.md             # promoted from csagent §8
│   ├── prompt-artifact-rules.md           # promoted from csagent §9
│   ├── badcase-lifecycle.md               # promoted from csagent §5.6
│   ├── architecture-health-metrics.md     # promoted from csagent §6 (collection still proposal-tier)
│   ├── self-governance.md                 # NEW v4 §7
│   └── fold-back-protocol.md              # NEW v4 §8
│
├── role-cards/                            # 5-role activation docs
│   ├── customer-checkpoints.md            # NEW v4 — Customer on-the-loop checkpoint catalog
│   ├── research-agent.md                  # NEW v4 — produces closure_contract in research-briefs/
│   ├── deliver-agent.md                   # NEW v4 — 3 input paths; Path 3 = Acceptance gap
│   ├── deliver-activation.md
│   ├── dev-agent.md                       # NEW v4 — agent_kind configurable per charter
│   ├── code-reviewer-agent.md             # NEW v4 (was "review-agent"; renamed for clarity vs Acceptance)
│   └── acceptance-agent.md                # NEW v4 — peer-of-Research; closure_contract verifier
│
├── templates/                             # prompt + ledger templates
│   ├── compact-dev-prompt.md              # context_budget required
│   ├── compact-review-prompt.md           # references code-reviewer (not "review")
│   ├── compact-acceptance-prompt.md       # NEW v4
│   ├── compact-research-brief.md          # NEW v4 (closure_contract required)
│   ├── compact-codex-rebuttal-prompt.md   # NEW v4 (formalize csagent S-Auto-26 pattern)
│   ├── handoff-template.md                # cell_size_target front-matter (suggested per §7.2)
│   ├── sprint-objective.md
│   ├── milestone-objective.md
│   ├── mission-charter.yaml               # NEW v4 — Δ-18 Delivery Loop charter (T0 base + T1 profile)
│   ├── deliver-close-taxonomy.md          # NEW v4 (promote from csagent)
│   ├── anti-hardcode-review-kernel.md     # 9-question kernel (was sprint stanza schema's neighbor)
│   ├── adoption-state-template.md         # NEW v4
│   └── lessons-learned-template.md        # NEW v4
│
├── docs/                                  # Application Guide — adopter-facing
│   ├── adoption-overview.md               # NEW v4 (5-role; closure_contract; two loops §3.6)
│   ├── greenfield-guide.md                # NEW v4 (Phase 1-5 framework-aware + §5.3.1 split-or-merge + Acceptance)
│   ├── brownfield-guide.md                # NEW v4 (Profile A/B/C + adoption-state.md + 5-role)
│   ├── domain-adaptation.md               # NEW v4
│   ├── friction-playbook.md               # NEW v4 (F1-F12 carry from old; +F13/F14/F15)
│   ├── industry-mapping.md                # NEW v4 (5-role + Δ-18; Concept 1 vs 2)
│   ├── directory-taxonomy.md              # NEW v4 (per OQ-V4-010: docs/, not process/)
│   ├── application-funnel.md              # NEW v4 (Phase 1-5 funnel reference)
│   └── two-loops-explainer.md             # NEW v4 (Auto Loop vs Delivery Loop adopter-facing reference)
│
├── schemas/                               # JSON schemas for verdict shapes
│   ├── review-verdict.schema.json         # NEW v4
│   ├── deliver-close-verdict.schema.json  # NEW v4
│   ├── deliver-plan-fix.schema.json       # NEW v4
│   ├── acceptance-verdict.schema.json     # NEW v4
│   ├── research-brief.schema.json         # NEW v4
│   ├── case-spec.schema.json              # NEW v4 (portable CaseSpec)
│   ├── mission-charter.schema.json        # NEW v4 (Δ-18 charter T0+T1 union)
│   ├── adoption-state.schema.json         # NEW v4
│   └── sprint_stanza.schema.json          # NEW v4 (carry forward existing if usable)
│
├── modules/                               # Module specs (conditional T1)
│   ├── m-evaluation.md                    # NEW v4 (4-component + 4-tier + 6-primitive DSL)
│   ├── m-trace.md                         # NEW v4 (portable trace shape; F5 evidence cross-ref)
│   └── m-autoloop.md                      # NEW v4 (Concept 1 — Auto Loop; cross-ref Δ-18)
│
├── examples/                              # worked instances (read-only)
│   ├── csagent-reference/                 # POPULATE DEFERRED (§5.1 of this build plan)
│   │   └── _build-trigger.md              # NEW v4 — populate trigger + spec
│   ├── hermes-reference/                  # POPULATE DEFERRED (§5.2 of this build plan)
│   │   └── _build-trigger.md              # NEW v4 — populate trigger + spec + maturity criteria
│   ├── fortunes-reference-placeholder/    # NEW v4 placeholder (Type C; populate when ready)
│   │   └── _placeholder.md
│   └── minimal-greenfield/                # NEW v4 — working consumer template (5-role; research-briefs/; etc.)
│       ├── AGENTS.md
│       ├── docs/current/{domain_taxonomy, runtime_invariants, eval_acceptance_bars, agent_context_guide}.md
│       ├── docs/{milestone_objective, sprint_objective, 10-handoff, action_bank}.md
│       ├── docs/research-briefs/_placeholder.md
│       ├── docs/acceptance-reports/_placeholder.md
│       ├── docs/diagnostics/failure-briefs/_placeholder.md
│       ├── docs/current/adoption-state.md
│       ├── compact/_placeholder.md
│       └── eval/bad_cases/_manifest.md
│
├── lessons/                               # NEW v4 — adopter → framework fold-back
│   └── .gitkeep
│
├── tools/                                 # script placeholders (deferred — OQ-V4-009)
│   └── README.md                          # NEW v4 (lists scripts referenced in friction-playbook; tracks OQ-V4-009)
│
└── archive/
    ├── 2026-06-06-v3.2-snapshot.md        # COPY from csagent compact/framework-plan-v3.2-2026-06-06.md
    ├── 2026-06-06-v4-skeleton.md          # COPY from csagent compact/framework-plan-v4-2026-06-06-skeleton.md
    ├── 2026-06-06-v4-plan.md              # COPY from csagent compact/framework-plan-v4-2026-06-06.md (final)
    └── 2026-06-07-v4-build-plan.md        # COPY of this file (after build complete)
```

**Total target file count**: ~70 files + directories.

---

## §2 — Per-file build spec

Each file's content is sourced from one or more of:
- **v4-plan §X.Y**: section in `compact/framework-plan-v4-2026-06-06.md`
- **csagent §X.Y**: doc path in csagent-latest (often `docs/current/process/...` or `docs/foundational/...`)
- **hermes §X.Y**: doc path or code in the hermes-autoloop donor repo
- **old aidazi §X.Y**: content from old aidazi commit (`1b93e07`) worth salvaging
- **fresh authored**: write new content based on v4 plan spec

### §2.1 governance/ (3 files)

| File | Source | Sketch |
|---|---|---|
| `governance/constitution.md` | v4-plan §1 (full body) + csagent `docs/current/iteration_governance.md` §1-§7 (carry §1.3/§1.4/§1.5/§1.6 ownership clauses verbatim if applicable) + NEW §1.7-A/B/C/D/E from v4-plan §1 + 5-role registry from v4-plan §3 + §7.0 hard-vs-suggested from v4-plan §7.0 | Constitution is the single biggest doc. Includes 5-role chain. References Δ-18 Delivery Loop pattern by name. ~800-1000 lines target. |
| `governance/doc_governance.md` | csagent `docs/current/doc_governance.md` (carry tier model + decision rules verbatim) + v4-plan additions (`closure_contract` field, `cell_size_target` field per §7.2, directory-taxonomy reference per §4.3) | Tier model + lifecycle + fold-back cadence. ~300-400 lines. |
| `governance/context_briefing.md` | csagent `docs/current/agent_context_guide.md` (carry Context Pack Prompt + per-task reading lists structure) + v4 updates (Research-Acceptance contract symmetry check; adoption-state.md load order; Δ-18 trigger) | Cold-start reading discipline. ~200-300 lines. |

### §2.2 process/ (23 files)

Δ-2~Δ-17 + Δ-18 + 5 promoted-from-csagent + self-governance + fold-back-protocol.

| File | Source | Sketch |
|---|---|---|
| `process/domain-discovery-process.md` (Δ-2) | v4-plan §4.1 Δ-2 EXTEND row + old aidazi `process/domain-discovery-process.md` (salvage 3-dim Q-set if good) + csagent `docs/foundational/phase1_solution_input_pack.md` inheritance pattern | D1 business / D2 user / D3 boundary + inheritance-table pattern |
| `process/tech-architecture-decision-catalog.md` (Δ-3) | v4-plan §4.1 Δ-3 EXTEND row + Δ-3 8-decision table + #1 abstraction-layer sub-choice (single tool-use default per §1.7-A) | 8 decisions + abstraction-layer addition |
| `process/doc-lifecycle-rules.md` (Δ-4) | v4-plan §4.1 Δ-4 row + old aidazi `process/doc-lifecycle-rules.md` if salvageable | live vs intermediate distinction |
| `process/context-passing-efficiency.md` (Δ-5) | v4-plan §1.4-i + §4.1 Δ-5 + csagent prompt-artifact-rules §9 | sufficient AND efficient + context_budget |
| `process/typeA-runtime-architecture-skeleton.md` (Δ-6) | v4-plan §4.1 Δ-6 EXTEND row + intent gate + phase pipeline + intent-switch hook from csagent + 6-primitive trace_check DSL from csagent eval `skill_procedure_check.py` | T1 portable skeleton + portable Tier-2 surface |
| `process/worked-example-instance.md` (Δ-7) | v4-plan §4.1 Δ-7 + read-only worked-example rules | Read-only after snapshot; fold-back direction rules |
| `process/post-deployment-iteration.md` (Δ-9) | v4-plan §4.1 Δ-9 AMEND row + reframe under 5-role + Acceptance fix_required → R-item promotion + anti-pattern updates | OBS triage L1/L2; Auto Loop driver pattern; cross-ref Δ-18 Delivery Loop |
| `process/doc-responsibility-matrix.md` (Δ-10) | v4-plan §4.1 Δ-10 EXTEND + 8 fields + cell_size_target | Per-doc owner / scope / load_discipline matrix |
| `process/artifact-taxonomy.md` (Δ-12) | v4-plan §4.1 §4.1 14-artifact set + per-role read-list updated for 5 roles | 14 artifact types + role read-list |
| `process/capability-staging-roadmap.md` (Δ-11) | v4-plan §4.1 Δ-11 AMEND + S0-S6 stages + S5 entry condition (§3.5 calibration completed) | Staging roadmap |
| `process/stage-stable-heuristic.md` (Δ-13) | v4-plan §4.1 Δ-13 KEEP | Heuristic; not gate |
| `process/profile-aware-maturity.md` (Δ-14) | v4-plan §4.1 Δ-14 EXTEND + Type A+B hybrid column | Per-profile necessary sets |
| `process/agent-design-elicitation.md` (Δ-15) | v4-plan §4.1 Δ-15 AMEND + 6 questions + 4 inventories + closure_contract draft as output | Heuristic Q&A + closure_contract required |
| `process/agent-creation-prerequisites.md` (Δ-16) | v4-plan §4.1 Δ-16 KEEP + 7 prereq categories | 7-category READY/DEFERRED/N/A gate |
| `process/common-detours-and-warnings-typeA.md` (Δ-17-A) | v4-plan §4.1 Δ-17 KEEP + csagent timeline P1-P4 | 4 named pitfalls + cognitive-detour disclaimer |
| `process/common-detours-and-warnings-typeB.md` (Δ-17-B) | v4-plan §4.1 + OQ-V4-001 placeholder | Placeholder; populate when hermes first SOP milestone closes |
| `process/common-detours-and-warnings-typeC.md` (Δ-17-C) | v4-plan §4.1 placeholder | Placeholder |
| **`process/delivery-loop.md` (Δ-18 NEW)** | v4-plan §4.2 (full spec) + §3.6 + hermes orchestrator code reference | THE Delivery Loop spec. Charter T0+T1 schema, 8 MANDATORY_CHECKPOINTS, state machine, scope_envelope_check, F5 evidence, 6 spawn functions + JSON schemas, calibration gate, anti-patterns. ~600-800 lines. |
| `process/milestone-framework.md` | csagent `docs/current/process/milestone-framework.md` (promote verbatim) | 3-5 sub-sprints per milestone; close cadence |
| `process/prompt-artifact-rules.md` | csagent `docs/current/process/prompt-artifact-rules.md` (promote verbatim) | Δ-9 self-containment invariant |
| `process/badcase-lifecycle.md` | csagent `docs/current/process/badcase-lifecycle.md` (promote verbatim) | §5.6 bad-case suite + tier lifecycle |
| `process/architecture-health-metrics.md` | csagent `docs/current/process/architecture-health-metrics.md` (promote verbatim; collection still proposal-tier) | 4 metric defs |
| **`process/self-governance.md` (NEW)** | v4-plan §7 (full body) | 6 mechanisms + §7.0 hard-vs-suggested |
| **`process/fold-back-protocol.md` (NEW)** | v4-plan §8 (full body) | Adopter ↔ framework fold-back; adoption-state schema; lessons template; cadence triggers |

### §2.3 role-cards/ (7 files; 6 unique roles + 1 activation)

| File | Source | Sketch |
|---|---|---|
| `role-cards/customer-checkpoints.md` (NEW) | v4-plan §3.1 + §3.2 Customer row + §3.4 + §4.2.3 MANDATORY_CHECKPOINTS | Customer on-the-loop checkpoint catalog: gate 1 brief sign-off, gate 2 acceptance verdict, gate 3 Acceptance fix_required confirm, gate 4 scope_deviation, gate 5 new_tier0_candidate |
| `role-cards/research-agent.md` | v4-plan §3.2 Research row + §4.3.1 research-briefs/ | Output dir = `docs/research-briefs/`; REQUIRED closure_contract per §1.7-B; Customer-signed front-matter; backing agent_kind configurable per charter |
| `role-cards/deliver-agent.md` | v4-plan §3.2 Deliver row + 3 input paths + close orchestration | Path 1/2/3; close conversation per deliver-close-taxonomy.md; backing agent_kind configurable |
| `role-cards/deliver-activation.md` | v4-plan §3.2 + cold-start activation prompt for Deliver | Brief paste-activator |
| `role-cards/dev-agent.md` | v4-plan §3.2 Dev row | sprint-NNN-dev-prompt.md consumer; backing agent_kind per charter (Codex / Claude Code / other); workspace-write sandbox |
| `role-cards/code-reviewer-agent.md` (was "review-agent") | v4-plan §3.2 Code Reviewer row + §3.3 boundary invariants | 9-question kernel embedded; read-only by tool whitelist; backing agent_kind per charter |
| **`role-cards/acceptance-agent.md`** | v4-plan §3.1 + §3.2 + §3.3 + §3.4 + §3.5 + §4.2 spawn schema for acceptance | **Peer-of-Research outcome gate**; reads research-brief closure_contract + dev evidence + Code Reviewer verdict; produces JSON verdict + gap brief + suggested route; human-confirm checkpoint MANDATORY on fix_required |

### §2.4 templates/ (13 files)

| File | Source | Sketch |
|---|---|---|
| `templates/compact-dev-prompt.md` | csagent compact dev-prompt patterns + v4 context_budget required | Self-contained per §9; 9 sections (role / read-order / sub-sprint contract / self-check / etc.) |
| `templates/compact-review-prompt.md` | csagent compact M-review-prompt patterns + 9-question kernel embed | Self-contained; embeds anti-hardcode-review-kernel.md |
| `templates/compact-acceptance-prompt.md` (NEW) | v4-plan §3.2 + §4.2.7 acceptance verdict schema | Read closure_contract + evidence; produce JSON verdict per acceptance-verdict.schema.json |
| `templates/compact-research-brief.md` (NEW) | v4-plan §4.3.1 research-briefs/ + §3.2 Research row | Frontmatter: customer_signed; body sections: closure_contract / scope IN-OUT / anti-goal / KPI / related-R-items |
| `templates/compact-codex-rebuttal-prompt.md` (NEW) | csagent S-Auto-26 pattern (formalized) | Codex broadens scope → push back to Codex; targeted re-review template |
| `templates/handoff-template.md` | csagent handoff §0/§1/§2 pattern + v4 cell_size_target front-matter | 3-section retention; structured §0 table |
| `templates/sprint-objective.md` | csagent sprint_objective patterns + §7 stanza | Per sub-sprint contract |
| `templates/milestone-objective.md` | csagent milestone_objective patterns + reference closure_contract source | Per milestone north star |
| `templates/mission-charter.yaml` (NEW) | v4-plan §4.2.2 charter schema (T0 base + T1 profile) | Δ-18 Delivery Loop charter; YAML; references schema |
| `templates/deliver-close-taxonomy.md` (NEW) | csagent `docs/current/deliver_close_taxonomy.md` (promote) | A/B/C/D verdicts + subclasses; per-blocker classification; NET=union |
| `templates/anti-hardcode-review-kernel.md` | csagent `docs/current/anti-hardcode-review-kernel.md` (promote 9-question kernel) | 9 questions + 4 verdicts |
| `templates/adoption-state-template.md` (NEW) | v4-plan §8.4 | Per-Δ status table; drift rationale; lessons-proposed |
| `templates/lessons-learned-template.md` (NEW) | v4-plan §8.5 | Adopter → framework fold-back input |

### §2.5 docs/ (9 files; Application Guide)

| File | Source | Sketch |
|---|---|---|
| `docs/adoption-overview.md` | old aidazi `docs/adoption-overview.md` (salvage mental-model framing) + v4-plan §3 + §3.6 | 5-role cognitive shape; Layer 1/2/3 model; what framework DOES vs DOES NOT decide; **two loops concept**; versioning |
| `docs/greenfield-guide.md` | old aidazi `docs/greenfield-guide.md` (salvage step-by-step structure) + v4-plan §5.1 + §5.3 + §5.3.1 + §3 5-role + §3.4 Acceptance flow | 7-step bootstrap; framework-aware Phase 1-5; §5.3.1 split-or-merge option; Acceptance step in first milestone close |
| `docs/brownfield-guide.md` | old aidazi `docs/brownfield-guide.md` (salvage Profile A/B/C — high value) + v4-plan §5.2 + adoption-state.md guidance | 3 profiles + diagnostic table + manual checklist + 5-role gradual adoption + adoption-state.md authoring |
| `docs/domain-adaptation.md` | old aidazi `docs/domain-adaptation.md` (salvage 3 domain contracts checklist) + v4-plan §1.7-A defaults + workflow_definition layer extension | 3 required domain contracts; layer extensions; per-milestone domain ops |
| `docs/friction-playbook.md` | old aidazi `docs/friction-playbook.md` F1-F12 (salvage all 12 — high value) + NEW F13/F14/F15 | F1-F12 bundled + not-bundled frictions; NEW F13 Acceptance calibration regression; F14 closure_contract vs closure_criterion confusion; F15 Phase 1+2 merge regret |
| `docs/industry-mapping.md` | old aidazi `docs/industry-mapping.md` (salvage industry comparison) + v4-plan §3 5-role + §3.6 two loops + §4.2.6 F5 evidence | Map v4 to LangGraph / AutoGen / etc.; Pattern 9 F5 evidence as v4 distinguishing |
| `docs/directory-taxonomy.md` (NEW per OQ-V4-010) | v4-plan §4.3 (full body incl §4.3.0 decision tree + §4.3.5 diagnostics-vs-failure-briefs) | Adopter-facing fast lookup: "where does this content go?" |
| `docs/application-funnel.md` (NEW) | v4-plan §5.3 + §5.3.1 + Phase 1-5 reverse-flow | Funnel reference doc; complements greenfield-guide which is step-by-step bootstrap |
| `docs/two-loops-explainer.md` (NEW) | v4-plan §3.6 (full body) | Adopter-facing explanation of Concept 1 (Auto Loop) vs Concept 2 (Delivery Loop); when to use which; can-coexist; anti-pattern §1.7-E |

### §2.6 schemas/ (9 JSON files)

All NEW. Schemas live as referenceable contracts for verdict shapes.

| File | Source | Sketch |
|---|---|---|
| `schemas/review-verdict.schema.json` | v4-plan §4.2.7 review schema | {decision, blocking_count, summary, findings[]} |
| `schemas/deliver-close-verdict.schema.json` | v4-plan §4.2.7 | {verdict A/B/C/D, blocking_count, worst_severity, in_scope, next_subsprint, reason} |
| `schemas/deliver-plan-fix.schema.json` | v4-plan §4.2.7 | {subsprint_id, layers, modules, objective_md, dev_prompt_md, summary} |
| `schemas/acceptance-verdict.schema.json` | v4-plan §4.2.7 | {milestone_verdict, cases[], failure_briefs[], suggested_route} |
| `schemas/research-brief.schema.json` | v4-plan §4.3.1 | closure_contract required; scope IN-OUT; anti-goal; KPI |
| `schemas/case-spec.schema.json` | v4-plan §5.3 Phase 5 + csagent eval CaseSpec schema | Portable CaseSpec (input/expected/scoring/closure_criterion/source_suite) |
| `schemas/mission-charter.schema.json` | v4-plan §4.2.2 charter schema (T0 + T1 union) | Δ-18 Delivery Loop charter; conditional T1 profile_type_a / _b / _c |
| `schemas/adoption-state.schema.json` | v4-plan §8.4 | Per-Δ status table |
| `schemas/sprint_stanza.schema.json` | old aidazi (carry forward if structure usable) + v4 §7 stanza | 4 fields validated |

### §2.7 modules/ (3 files)

| File | Source | Sketch |
|---|---|---|
| `modules/m-evaluation.md` | v4-plan §5.3 Phase 5 + csagent eval_interactive architecture + 6-primitive trace_check DSL | 4-component + 4-tier pyramid + adaptor pattern; portable across tracks |
| `modules/m-trace.md` | v4-plan §4.2.6 F5 evidence + portable trace shape + run_mode field | Conditional T1; trace contract abstraction |
| `modules/m-autoloop.md` | v4-plan §3.6 Concept 1 + old aidazi `modules/m-autoloop.md` (salvage OBS triage + anti-gaming forbidden list) + cross-ref Δ-18 Delivery Loop | **Concept 1 Auto Loop**: AI agent self-improvement via auto-research; clearly distinguished from Delivery Loop |

### §2.8 examples/ (deferred + minimal-greenfield)

- `examples/minimal-greenfield/` — NEW v4 working consumer template (build now): sample AGENTS.md + docs/current/{domain_taxonomy, runtime_invariants, eval_acceptance_bars, agent_context_guide, adoption-state}.md + docs/{milestone_objective, sprint_objective, 10-handoff, action_bank}.md + docs/research-briefs/_placeholder.md + docs/acceptance-reports/_placeholder.md + docs/diagnostics/failure-briefs/_placeholder.md + eval/bad_cases/_manifest.md + compact/_placeholder.md
- `examples/csagent-reference/_build-trigger.md` — NEW (deferred populate; see §5.1)
- `examples/hermes-reference/_build-trigger.md` — NEW (deferred populate; see §5.2)
- `examples/fortunes-reference-placeholder/_placeholder.md` — NEW empty

### §2.9 archive/

Copy these v4 source-of-truth files into aidazi/archive/ at build time:
- `archive/2026-06-06-v3.2-snapshot.md` ← csagent `compact/framework-plan-v3.2-2026-06-06.md`
- `archive/2026-06-06-v4-skeleton.md` ← csagent `compact/framework-plan-v4-2026-06-06-skeleton.md`
- `archive/2026-06-06-v4-plan.md` ← csagent `compact/framework-plan-v4-2026-06-06.md` (final)
- `archive/2026-06-07-v4-build-plan.md` ← csagent `compact/aidazi-v4-build-plan.md` (this file, at the end)

### §2.10 lessons/, tools/, top-level

- `lessons/.gitkeep` — NEW empty dir
- `tools/README.md` — NEW v4 (notes referenced-but-not-yet-built scripts; tracks OQ-V4-009: precommit_bundling_check.sh / stanza_validator.py / trace_emitter.py — deferred backlog)
- `AGENTS.md` — NEW v4 consumer template (5-role registry; 3 input paths; Two Loops note; @-includes governance chain; placeholder section)
- `README.md` — NEW v4 (one-page elevator; read order; what aidazi is + is not; pointer to docs/adoption-overview.md)
- `.gitignore` — NEW (standard)

---

## §3 — Build order (7 phases)

Same dependency structure as old P4 §5; simpler since no AMEND/KEEP distinction.

### Phase A — Foundation (do first)
1. `governance/constitution.md` (5-role chain + §1.7 + §7.0)
2. `governance/doc_governance.md`
3. `governance/context_briefing.md`
4. `process/delivery-loop.md` (Δ-18; the largest new doc)
5. `process/self-governance.md`
6. `process/fold-back-protocol.md`
7. `docs/directory-taxonomy.md` (per OQ-V4-010)
8. `docs/two-loops-explainer.md` (§3.6)

### Phase B — Role cards (depends on Phase A constitution)
9. `role-cards/acceptance-agent.md` (most consequential)
10. `role-cards/customer-checkpoints.md`
11. `role-cards/research-agent.md`
12. `role-cards/deliver-agent.md`
13. `role-cards/code-reviewer-agent.md`
14. `role-cards/dev-agent.md`
15. `role-cards/deliver-activation.md`

### Phase C — Templates + schemas (depends on Phase A+B)
16. All 9 schemas/ files (can be parallel JSON authoring)
17. `templates/mission-charter.yaml`
18. `templates/compact-acceptance-prompt.md`
19. `templates/compact-research-brief.md`
20. `templates/compact-codex-rebuttal-prompt.md`
21. `templates/deliver-close-taxonomy.md`
22. `templates/adoption-state-template.md`
23. `templates/lessons-learned-template.md`
24. `templates/compact-dev-prompt.md`
25. `templates/compact-review-prompt.md`
26. `templates/handoff-template.md`
27. `templates/sprint-objective.md`
28. `templates/milestone-objective.md`
29. `templates/anti-hardcode-review-kernel.md`

### Phase D — Remaining process docs (Δ-2 through Δ-17 + promoted-from-csagent)
30. 4 promoted-from-csagent: milestone-framework, prompt-artifact-rules, badcase-lifecycle, architecture-health-metrics
31. Δ-2, Δ-3, Δ-4, Δ-5, Δ-6, Δ-7
32. Δ-9, Δ-10, Δ-11, Δ-12, Δ-13, Δ-14, Δ-15, Δ-16
33. Δ-17-A, Δ-17-B (placeholder), Δ-17-C (placeholder)

### Phase E — Modules
34. `modules/m-evaluation.md`
35. `modules/m-trace.md`
36. `modules/m-autoloop.md` (Concept 1; cross-ref Δ-18)

### Phase F — Application Guide (docs/) + minimal-greenfield example
37. `docs/adoption-overview.md`
38. `docs/greenfield-guide.md`
39. `docs/brownfield-guide.md`
40. `docs/domain-adaptation.md`
41. `docs/friction-playbook.md` (F1-F15)
42. `docs/industry-mapping.md`
43. `docs/application-funnel.md`
44. All of `examples/minimal-greenfield/` (working consumer template)
45. `examples/csagent-reference/_build-trigger.md`
46. `examples/hermes-reference/_build-trigger.md`
47. `examples/fortunes-reference-placeholder/_placeholder.md`

### Phase G — Top-level integration + archive
48. `AGENTS.md` (consumer template)
49. `README.md`
50. `.gitignore`
51. `tools/README.md`
52. `lessons/.gitkeep`
53. Copy 4 archive/ files

---

## §4 — Effort estimate (fresh build)

| Phase | Files | Est. effort | Risk |
|---|---|---|---|
| A Foundation | 8 (1 huge constitution + 1 huge delivery-loop + 6 medium) | 5-7h | Medium — constitution + delivery-loop are the biggest docs |
| B Role cards | 7 | 3-4h | Low — clear specs per role |
| C Templates + schemas | 14 | 3-4h | Low — schemas are concise JSON |
| D Process docs | ~20 | 4-5h | Medium — Δ-2~Δ-17 each ~50-100 lines; lots of files but small each |
| E Modules | 3 | 1-2h | Low |
| F Application Guide + minimal-greenfield | ~15 files | 4-5h | Medium — adopter-facing; needs clarity |
| G Top-level | 5 | 1h | Low |
| **Total** | **~70 file ops** | **21-28h serial** | Medium overall |

With parallel work (e.g., schemas during constitution writing): **~15-20h**.

**~3-4 working days** for one execution agent. Can split across multiple agents per phase.

**Risk areas (recap)**:
1. `constitution.md` — fresh rewrite; needs cross-section consistency
2. `process/delivery-loop.md` — Δ-18 full spec is the largest single doc
3. `role-cards/acceptance-agent.md` — sole role definition for the v4 most-significant change
4. `docs/greenfield-guide.md` + `docs/brownfield-guide.md` — adopter-facing; clarity is high-stakes

---

## §5 — Deferred plans

### §5.1 examples/csagent-reference/ — deferred populate plan

Per OQ-V4-014: separate plan; do later.

`examples/csagent-reference/_build-trigger.md` (NEW; built as part of Phase F):

```markdown
# csagent-reference build trigger

**Status**: not populated; populate when needed for adopter onboarding.

**Trigger conditions**: any one of —
- A new adopter (Type A) starts onboarding and needs a worked Type A reference
- v4 framework stabilizes (no major Δ changes in 3 sub-sprints)
- A framework fold-back sub-sprint surfaces "lack of worked example" as a recurring lesson

**Source content (when triggered)**: snapshot of csagent-latest state at trigger date.
Specifically populate these sub-dirs (each was placeholder README in old aidazi):
- decisions/ — csagent's Δ-3 8-decision actual choices
- discovery/ — csagent's Phase 1 BRD/PRD extracted artifacts (anonymized as needed)
- m-eval/ — csagent's M-Evaluation actual instantiation (CaseSpec / 4-tier / judge config)
- m-trace/ — csagent's trace contract actual instantiation
- runtime-skeleton/ — csagent's Δ-6 Type A runtime skeleton actual filled
- timeline-54-day.md — already populated in old aidazi; carry forward if still accurate

**Build cost estimate**: ~6-8h once triggered.

**Snapshot date convention**: name `examples/csagent-reference-YYYY-MM-DD/` so subsequent snapshots don't collide (per Δ-7 read-only-after-snapshot rule).
```

### §5.2 examples/hermes-reference/ — deferred populate plan

Per OQ-V4-015: leave a guide/prompt; build when hermes is mature.

`examples/hermes-reference/_build-trigger.md` (NEW; built as part of Phase F):

```markdown
# hermes-reference build trigger

**Status**: not populated; populate when hermes-autoloop project reaches sufficient maturity.

**Maturity criteria** (any of):
- hermes-autoloop completes its first SOP milestone end-to-end with a Type B workflow_definition layer in active use
- hermes-autoloop publishes a closure_contract-backed acceptance run with positive verdict
- hermes-autoloop runs 3 consecutive overnight orchestrator-driven Delivery Loops with no scope_deviation MANDATORY_CHECKPOINT firing
- 2+ adopters ask for Type A+B hybrid worked example

**Trigger**: human (user) decides hermes is mature enough. Run the build prompt below.

**Build prompt** (paste into a fresh coding-agent session at trigger time):

```
You are populating aidazi/examples/hermes-reference/ from hermes-autoloop's
actual state.

PREREQUISITES:
- Read aidazi/process/profile-aware-maturity.md (Type A+B hybrid column)
- Read aidazi/process/delivery-loop.md (Δ-18 spec)
- Read the hermes-autoloop donor repo — all of:
  - AGENTS.md
  - docs/aidazi-integration-plan.md
  - docs/upgrade-plan.md
  - orchestrator/{loop.py, agents.py, acceptance.py, charter.py, gates.py, checkpoints.py, state.py}
  - docs/proposals/{orchestration-protocol-draft, acceptance-agent-draft, mission-charter-template-draft, aidazi-workflow-governance-variant}.md

POPULATE these sub-dirs of aidazi/examples/hermes-reference/:
1. decisions/ — hermes's Δ-3 decisions (especially #1 abstraction-layer choice;
   workflow_definition layer extension reasoning)
2. discovery/ — hermes's business need + workflow definition (SOP layer; airline-specific)
3. m-eval/ — hermes's eval instantiation (per-step SOP test pyramid)
4. m-trace/ — hermes's trace contract for browser-automation
5. m-autoloop/ — hermes's Auto Loop usage (Concept 1)
6. delivery-loop/ — hermes's Delivery Loop charter + orchestrator run examples (Concept 2)
7. runtime-skeleton/ — hermes's Type A+B hybrid runtime skeleton
8. timeline.md — hermes's lifecycle date stamps

SNAPSHOT date: today (the date of running this prompt).
NAME the dir: `examples/hermes-reference-YYYY-MM-DD/`.
READ-ONLY after snapshot per Δ-7.

OUTPUT: a populated dir + brief summary of what was populated.
```

**Build cost estimate**: ~4-6h once triggered.
```

These trigger docs are themselves ~50 lines each; cheap to author now.

---

## §6 — OQ status

All v4 plan OQs are resolved or have a clear next-step plan:

| OQ | Status | Resolution |
|---|---|---|
| OQ-V4-001 (Δ-18 Type B placeholder) | DEFERRED | Wait for hermes first SOP milestone; placeholder file written |
| OQ-V4-002 (csagent-reference snapshot date) | DEFERRED | See §5.1 trigger |
| OQ-V4-003 (fortunes-reference) | DEFERRED | Empty placeholder; populate when fortunes Type C lifecycle |
| OQ-V4-004 (framework versioning) | TBD at first release | Semver suggested (v4.0.0); confirm later |
| OQ-V4-005 (lessons submission mechanism) | TBD at first adopter | Simple PR to aidazi/lessons/ initially |
| OQ-V4-006 (adoption-state cadence) | "Per milestone close" suggested | Confirm at first adopter |
| OQ-V4-007 (calibration cost when swapping model) | TBD at first multi-model adopter | Re-calibrate; portability story deferred |
| OQ-V4-008 (cell_size_target value 500) | Suggested; adopter overrides | Per §7.0 hard-vs-suggested split |
| OQ-V4-009 (tools/ scripts referenced but missing) | NOTED in tools/README.md | Backlog; future sprint |
| **OQ-V4-010** (directory-taxonomy in docs/ vs process/) | **RESOLVED** | docs/ per user 2026-06-07 |
| **OQ-V4-011** (Constitution rewrite vs extend) | **RESOLVED** | Rewrite-as-needed approved; some content salvageable from old aidazi/csagent |
| **OQ-V4-012** (legacy docs/solutions/) | **RESOLVED** | Delete in adopter projects if v4 doesn't have the dir |
| **OQ-V4-013** (Concept naming) | **RESOLVED** | Concept 1 = Auto Loop; Concept 2 = Delivery Loop (Δ-18 renamed); §3.6 + §1.7-E codified |
| **OQ-V4-014** (csagent-reference populate) | **DEFERRED w/ plan** | §5.1 trigger doc |
| **OQ-V4-015** (hermes-reference populate) | **DEFERRED w/ plan** | §5.2 trigger doc + build prompt |

---

## §7 — How to use this build plan

When the user (or a future agent) is ready to build aidazi v4:

1. Read this doc + v4 plan side-by-side (no other inputs required)
2. Walk phases A → G in order
3. For each file: apply spec per §2; reference source pointers in §2 columns
4. Defer §5.1/§5.2 worked examples until trigger conditions met
5. Commit per phase so review is incremental
6. After Phase G complete: this doc archives to `archive/2026-06-07-v4-build-plan.md` within aidazi/

The framework-plan-v4-2026-06-06.md is the **spec**; this doc is the **implementation walkthrough**. Both together = complete; no re-discovery needed.
