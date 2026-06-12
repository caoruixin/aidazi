---
title: aidazi Framework Plan v4
doc_tier: intermediate
doc_category: intermediate
status: proposal
source_of_truth: this file (until P4 reconciliation extracts content into aidazi/)
last_reviewed: 2026-06-07
supersedes: [compact/framework-plan-v3.2-2026-06-06.md, compact/framework-plan-v4-2026-06-06-skeleton.md]
notes: >
  Full v4 plan produced from a 2-donor codebase scan (csagent + hermes-autoloop).
  Replaces v3.2 archive (which had wrong premise: assumed aidazi unbuilt and
  hermes "待落地"). Built on Checkpoint 1 (2026-06-07) decisions: Acceptance
  Agent = Research peer (closure_contract holder), coding-agent backing
  configurable, autonomy switch explicit, gap-tracking + fold-back protocol
  first-class. Includes Δ-18 orchestrator-pattern (NEW) + Application Guide
  for greenfield-fast / brownfield-manual bootstrap. Section §10 is the
  4-column comparison appendix (v3.2 claim / aidazi-as-implemented /
  csagent-actual / hermes-actual) per Δ.
---

# aidazi Framework Plan v4 (2026-06-07)

## §0 — Reading guide

Read in order on cold start: §0 → §1 charter brief → §3 role chain → §4 Δ-18 (the NEW one) → §5 Application Guide → §7-§8 self-governance + fold-back. Skip §10 4-column appendix unless reconciling against v3.2 archive.

**What this plan is**: the design spec for aidazi/ as it should be after P4 reconciliation. NOT the framework itself; the framework lives in `aidazi/` after P4 extracts content here.

**What this plan is not**: a re-statement of every Δ — Δ-1~Δ-17 are referenced by pointer to aidazi/ (where they already mostly live) or to csagent's `docs/current/` source. Only Δ-18 + 5-role chain + Application Guide + self-governance + fold-back are written out in full because they are NEW or substantially CHANGED.

**Checkpoint 1 decisions applied (2026-06-07)** — these shape the entire plan:
1. closure_contract is a required field on the Research Agent's brief, NOT on milestone_objective.md.
2. Acceptance Agent runs at milestone close + release cut (default); sub-sprint optional via charter.
3. Acceptance fix_required → quick human-confirm checkpoint → if confirmed, Deliver fix-iteration; if denied, three routes (re-run / contract revision / direct dispatch) Acceptance suggests in report.
4. Δ-18 Type B (T1') is placeholder until hermes completes its first SOP milestone end-to-end.
5. Charter schema = T0 universal base + T1 profile-specific overlays (Type A acceptance section, Type B sop_definition section, Type C local_acceptance_checklist section).
6. Application Guide = multi sub-doc Layer-B set (not monolithic).

**Five Checkpoint 1 refinements above and beyond Q1-Q6**:
- Coding agent backing (Claude Code / Codex / other) is configurable via charter `tooling.{dev,review,acceptance}.agent_kind`; role-cards are agent-agnostic.
- Acceptance fix_required gap **always** crosses a human-confirm checkpoint before routing to Deliver. Acceptance never silently routes back.
- Autonomy switch is a charter-level first-class concept (3 levels: human_in_the_loop / human_on_the_loop / fully_autonomous_within_budget). Adopter chooses; framework does not impose a default.
- Adopter-vs-framework **gap-tracking ledger** (`adoption-state.md`) is part of the framework's adopter-side artifact set.
- **Bidirectional fold-back protocol** (adopter → framework lessons / framework → adopter release) is §8.

**Checkpoint 2 refinements applied (2026-06-07 second turn)** — three structural fixes:
1. **§4.3 NEW** — Directory taxonomy + authoring authority. Clarifies who writes where: `research-briefs/` vs `proposals/` vs `diagnostics/` vs `failure-briefs/` vs `bad_cases/` vs `acceptance-reports/` are NOT overlapping; each has a single primary author, trigger, content type, and promotion path.
2. **§5.3 REWRITTEN** — Phase 1-5 funnel sequencing corrected. Phase 1 = **Business need & goal** (market need, KPI, scope); Phase 2 = **Product/Service design** (how do we satisfy: UC/SOP/skills); Phase 3 = **Technical plan** — technical constraints (engineering baseline, platform APIs like Salesforce, integration approach) arrive at Phase 3, NOT lumped into Phase 1. Reverse-flow signals across phases when later finds earlier infeasibility.
3. **§7.0 NEW + §7.2 SOFTENED** — Framework defaults (numerical thresholds, cadences, target sizes) are **suggested starting points**, not hard gates. Only Constitution §1.7 forbidden list, §3.3 role boundary invariants, §4.2.3 MANDATORY_CHECKPOINTS, and §3.5 acceptance calibration are hard requirements. Everything else: adopters override with documented rationale in `adoption-state.md`.

---

## §1 — Constitution (Layer A; brief)

Inherits csagent `docs/current/iteration_governance.md §1` verbatim — the 7 sub-clauses (§1.1 Objective, §1.2 Primary principle, §1.3 LLM owns, §1.4 Runtime owns, §1.5 Iteration rule, §1.6 Evaluation rule, §1.7 Forbidden). These are the universal LLM-vs-Runtime ownership boundary and forbidden-list; they are not edited per project.

**v4 additions to §1.7 Forbidden** (added because csagent + hermes scan surfaced these as missed):

- **§1.7-A** — single agent abstraction layer: dual abstraction layers (e.g., 5-action + tool-use simultaneously) is forbidden in greenfield agent design. csagent's 2026-05-01 deviation is the cautionary tale. Adopt single tool-use layer at Phase 1.
- **§1.7-B** — bad-case `closure_criterion` MUST NOT be expressed as keyword match: it is a human-judgment paragraph (positive shape + anti-pattern + quoted anchor phrases). Anchors Δ-12 bad-case artifact contract; reinforces §1.7's existing "no keyword/regex for soft semantic decisions" line.
- **§1.7-C** — Acceptance Agent MUST NOT be spawned by the same role that wrote the Research brief OR by the Deliver Agent it might route back to. Independent spawn surface required (Customer-paste or orchestrator). Prevents self-grading collapse.
- **§1.7-D** — Charter's MANDATORY_CHECKPOINTS list MUST NOT be edited to remove a checkpoint. Adopters may add but not subtract. Anchors Δ-18.

**v4 addition to §1.4 Runtime owns**:

- **§1.4-i** — Context-passing efficiency (sufficient AND efficient), per Δ-5. Each prompt artifact MUST declare `context_budget` front-matter. (This was Δ-5 in v3.2; v4 promotes it from Δ to §1.4 clause for emphasis.)

The Constitution is loaded transitively via `aidazi/governance/constitution.md`. All adopters import it; they may not edit it. Per-project specialization happens in domain context docs (§1.7-domain overlays), not in §1 itself.

---

## §2 — Three orthogonal dimensions + three tracks (brief)

Inherits v3.2 §2-§3 verbatim:
- **Dim 1 Layer**: A Constitution / B Process / C State ledgers / D Prompt artifacts
- **Dim 2 Portability tier**: T0 Universal / T1 App-type / T2 Domain / T3 Project
- **Dim 3 Lifecycle**: static / reviewed / generated / append-only
- **Three tracks**: Type A AI agent / Type B agentic workflow / Type C demo app

**v4 addition — Type A+B Hybrid track**:

Hermes-autoloop is the donor evidence: a project that has both a Type A semantic agent (intent → LLM reasoning) AND a Type B workflow definition (SOP rows as runtime contract). The hybrid track is not a fourth track but a charter-level overlay: `profile_type_a` + `profile_type_b` sections both populated. Adopters declare `track: type_a` / `type_b` / `type_c` / `type_a_b_hybrid`.

For details on what each track inherits at which stage, see Δ-14 profile-aware-maturity (lives in aidazi/process/profile-aware-maturity.md; v4 amends to add A+B hybrid column).

---

## §3 — 5-role chain (FULL — significantly changed from v3.2)

### §3.1 Role chain (visual)

```
                          ╔════════════════════════════════════════════════╗
                          ║                Customer (human)                ║
                          ║   on-the-loop OR in-the-loop                   ║
                          ║   per charter.autonomy.level                   ║
                          ╚═══╤════════════════════════════════════════╤═══╝
                              │ gate 1: brief sign-off                 │ gate 2: acceptance verdict
                              ↓                                        ↑
   ┌──────────────────────────────────┐         ┌────────────────────────────────────┐
   │       Research Agent             │         │       Acceptance Agent             │
   │  intake gate · 产 brief +        │←ref────│  outcome gate · judge delivered     │
   │  closure_contract                │ for     │  evidence vs closure_contract       │
   │                                  │ contract│                                     │
   │  peer of Acceptance              │ schema  │  peer of Research                   │
   └──────────────┬───────────────────┘         └─────────────┬──────────────────────┘
                  │                                            │ verdict:
                  │ docs/research-briefs/<id>.md               │   pass /
                  │ (closure_contract + scope + anti-goal)     │   fix_required /
                  ↓                                            │   needs_human
   ┌──────────────────────────────────────────────────────────┴──┐
   │                  Deliver Agent (Tech Lead)                  │←─┐
   │   plan + orchestrate + close + maintain bad-case suite       │  │
   │                                                              │  │
   │   • Path 1 Research-driven: brief → milestone/sub-sprint plan│  │
   │   • Path 2 Bad-case-driven:  bad case → 4-route fit         │  │
   │   • Path 3 Acceptance-gap:   gap brief → fix-iteration       │  │
   └──────────────┬──────────────────────────────────────────────┘  │
                  │                                                  │
        dispatch  │       handoff + tests + eval evidence            │
                  │       ↑                                          │ post-confirm
                  ↓       │                                          │ gap routing
   ┌──────────────────────┴─┐    ┌───────────────────────────────┐  │
   │     Dev Agent          │ ─→ │   Code Reviewer Agent         │  │
   │  (codes; no scope)     │    │  anti-hardcode kernel §4.1    │  │
   │                        │    │  + correctness lens           │  │
   │  backing coding-agent  │    │                                │  │
   │  = charter.tooling.dev │    │  verdict: pass / fix_required │  │
   │    .agent_kind         │    │  / out_of_scope_review        │  │
   │                        │    │                                │  │
   │  (Claude Code, Codex,  │    │  backing coding-agent =        │  │
   │  or other)             │    │  charter.tooling.review        │  │
   │                        │    │  .agent_kind                   │  │
   └────────────────────────┘    └───────────────────────────────┘  │
                                                                     │
                                  ┌─────────────────────────────────┐ │
   On Acceptance fix_required:    │  Human-confirm checkpoint        │ │
   acceptance report → human ────→│  human writes:                   │─┘
                                  │    confirm: yes | no             │
                                  │    route: deliver | re-acceptance│
                                  │           | research-revision    │
                                  └──────────────────────────────────┘

Diagram notes:
- gate 1 = Customer signs Research brief; without sign-off, downstream blocked
- gate 2 = Customer reads Acceptance report; ship/no-ship decision
- Acceptance never silently routes to Deliver — human-confirm checkpoint mandatory (§1.7-C)
- Code Reviewer ≠ Acceptance: Reviewer checks "built correctly" on code; Acceptance checks "built the right thing" on execution evidence
- Dev Agent and Code Reviewer Agent backing coding-agent is configurable
- All roles' chat history is isolated: context passes via repo docs only
```

### §3.2 Role table (5 roles + Customer)

| Role | Trigger | Reads | Produces | Spawn surface | Backing coding-agent | Chain position | Track applicability |
|---|---|---|---|---|---|---|---|
| **Customer** (human) | Gate events: brief sign-off, acceptance verdict, mandatory checkpoints | Research brief, Acceptance report, Deliver milestone proposal | Approve / reject / direct (free text) | — | n/a | top + bottom | All |
| **Research Agent** | (a) Customer asks "what should we build?" (b) Bad-case pattern matures (n≥2) | Customer prompt + codebase samples + transcripts/data + relevant `docs/proposals/` | `docs/research-briefs/<id>.md` containing: closure_contract (≥1 paragraph; positive shape + anti-pattern + anchor phrases per §1.7-B) + scope IN/OUT + anti-goal + risk/impact + related R-items | Human paste (default) or charter-permitted orchestrator | Adopter choice via charter `tooling.research.agent_kind`; usually Claude Code (heavy reasoning, low code edits) | intake gate (peer of Acceptance) | A heavy; B lighter (SOP review replaces some); C 1-pager |
| **Deliver Agent** (Tech Lead) | (a) approved brief lands (b) Acceptance gap brief arrives post-human-confirm (c) bad case triages to "fits current/future milestone" | research brief + action_bank + handoff §0/§1 + codex-findings (collection time) + Acceptance report (if Path 3) | milestone_objective.md, sprint_objective.md, compact/sprint-NNN-dev-prompt.md, compact/M<N>-review-prompt.md, close decisions per deliver_close_taxonomy.md | Human paste or charter-permitted orchestrator | Adopter choice via charter `tooling.deliver.agent_kind`; usually Claude Code | middle, plan + close | All |
| **Dev Agent** | sprint-NNN-dev-prompt.md ready | self-contained dev prompt (per Δ-5 + Δ-9 prompt artifact rules) | code edits + tests + sprint-NNN-handoff.md (§1-§11 dev fills; §12 reserved for deliver+human close verdict) | Human paste or charter-permitted orchestrator (workspace-write sandbox, no network, no git push) | **Adopter choice via charter `tooling.dev.agent_kind`** — could be Codex (hermes choice; cost-asymmetry caveat), Claude Code (csagent choice), or other tool-using coding agent | implementation | All |
| **Code Reviewer Agent** | sub-sprint close OR §4.3 trigger (semantic-touching + Tier-0 risk + scope-revision-from-codex + bad-case-failure-shape) OR milestone close | dev diff + handoff + sprint_objective + anti-hardcode kernel (Δ-19 in aidazi/templates/) | codex-findings.md with §4.2 4-line header (decision: pass / fix_required / out_of_scope_review; blocking_count; summary; signed sub-sprint scope claim) | Human paste or orchestrator (read-only by mechanical tool whitelist: Read, Grep, Glob) | **Adopter choice via charter `tooling.review.agent_kind`** — Codex (csagent + hermes choice for independence) or different model class than Dev | code-side gate | All (depth varies by track) |
| **Acceptance Agent** | (default) milestone close (charter.acceptance.run_at) AND release cut. (optional) sub-sprint close — Type C demo requires every-sprint; Type A/B per charter | Research brief's **closure_contract** + dev evidence (bad-case results + execution trace) + Code Reviewer verdict ledger + (optional) prior Acceptance reports for residual risk | docs/acceptance/<scope>-acceptance-report.md with: verdict {pass / fix_required / needs_human}; per-criterion evidence pointer; residual risks; if fail, **gap brief** referencing closure_contract clauses violated and proposed scope; **suggested route** (deliver-fix / re-acceptance-after-evidence / research-contract-revision) | Human paste (Customer triggers at release cut) or charter-permitted orchestrator (read-only by tool whitelist; calibration-gated per §3.5) | **Adopter choice via charter `tooling.acceptance.agent_kind`** — distinct from Dev/Reviewer/Research for independence | outcome gate (peer of Research) | A,B release; **C every demo** |

### §3.3 Role boundary invariants

The 5 roles are real walls, not naming conventions. v4 makes them enforceable:

- **No self-grading**: a single human operator may walk multiple roles (typical in single-person adopters per hermes integration plan §1) but each role MUST execute in a fresh agent session with self-contained prompt artifacts. Cross-role context never passes via chat history — only via repo docs (Δ-5 + Δ-9).
- **Acceptance spawn isolation** (§1.7-C): Acceptance MUST NOT be spawned by Research, Deliver, or Dev. Acceptance is spawned by Customer (human paste) or by orchestrator only when charter.acceptance.enabled=true AND charter.acceptance.judge_calibration.status=calibrated.
- **Code Reviewer ≠ Acceptance** lenses:
  - Code Reviewer's question: "Is the code well-built? Does it preserve §1.3/§1.4 ownership + anti-hardcode kernel?"
  - Acceptance's question: "Did we build the right thing? Does delivered behavior satisfy the closure_contract?"
  - Both gates run; their verdicts are independent.
- **Research-Acceptance contract symmetry**: Research authors the closure_contract; Acceptance evaluates against it. Research MUST NOT change closure_contract after milestone start (without re-sign-off); Acceptance MUST NOT evaluate against criteria the closure_contract doesn't specify.
- **Deliver does not write code**, does not run review, does not run acceptance. Plans, orchestrates, closes.

### §3.4 Acceptance fix_required → human-confirm → Deliver loop (Checkpoint 1 #2)

```
Acceptance verdict = fix_required
       ↓
Acceptance writes acceptance report including:
  • per-criterion evidence (which closure_contract clauses violated)
  • gap brief (proposed scope to close gap)
  • suggested_route ∈ {deliver_fix_iteration, re_acceptance_after_evidence, research_contract_revision}
       ↓
Acceptance posts a human-confirm checkpoint:
  docs/checkpoints/<timestamp>__acceptance_fix_required__<scope>.md
  contains: { gap_summary, suggested_route, decision: pending }
       ↓
Human reads acceptance report + writes checkpoint decision:
  • { confirm: yes, route: deliver_fix_iteration }    → Deliver picks up gap brief
  • { confirm: yes, route: re_acceptance_after_evidence } → re-run Acceptance with more evidence
  • { confirm: yes, route: research_contract_revision }   → Research re-opens brief; gate 1 re-sign-off
  • { confirm: no }                                       → Acceptance verdict downgraded to advisory; ship anyway (Customer assumes residual risk)
       ↓
If confirm=yes && route=deliver:
  Deliver Agent reads { acceptance report, gap brief }
  Deliver authors new sub-sprint scoped to gap closure
  [normal dispatch resumes]
```

**Why human-confirm is mandatory** (§1.7-C extended): the same Customer who signed the Research brief at gate 1 should be the one confirming the Acceptance verdict at gate 2 — not the Deliver Agent or the orchestrator. Without this confirmation, Acceptance could route work back to Deliver indefinitely; with it, Customer keeps loop authority.

### §3.5 Acceptance judge calibration gate (carried from hermes)

Acceptance Agent's verdict cannot be trusted in `fully_autonomous_within_budget` mode without prior calibration. Calibration is a one-time-per-judge-model gate:

1. Maintain a labeled set: `aidazi/calibration/labeled_acceptance_cases/manifest.json` mapping (trace, expected_verdict ∈ {PASS, FAIL}) tuples per project.
2. Run Acceptance Agent against each tuple twice across separate sessions.
3. Compute `agreement_rate` = (judge_verdict matches expected) / total; `flip_rate` = (judge_verdict differs across reruns) / total.
4. Calibrated iff `agreement_rate ≥ 0.9 AND flip_rate ≤ 0.1`.
5. Charter `acceptance.judge_calibration.status: calibrated | uncalibrated`. Until calibrated, charter `autonomy.level=fully_autonomous_within_budget` degrades automatically to `human_on_the_loop`.

Calibration is per-(judge-model × project). Switching `tooling.acceptance.agent_kind` or `model` invalidates calibration; re-run required.

---

## §4 — Δ reconciliation + Δ-18 full spec

### §4.1 Δ reconciliation table

Each row: v3.2's claim, the codebase evidence, the v4 verdict, and where the content lives in v4.

| Δ | v3.2 main claim | Codebase evidence | v4 verdict | Lives at |
|---|---|---|---|---|
| **Δ-1** Framework anatomy (3 dims × 4 layers × 4 tiers) | Sound framing | csagent docs/current/ + docs/foundational/ taxonomy fits cleanly | **KEEP** | §2 + aidazi/governance/constitution.md "framework anatomy" section |
| **Δ-2** Domain discovery (D1 business / D2 user / D3 boundary) | Process doc | Aligns with csagent foundational/phase1_solution_input_pack.md but misses Phase 0 §0.3 inheritance-table pattern | **EXTEND** — add inheritance-table subsection | aidazi/process/domain-discovery-process.md (revised) |
| **Δ-3** Tech-architecture decision catalog (8 items) | Process doc + decision #1 binds S2-required event | csagent phase0 §0.3 + phase3 decisions match; csagent 2026-05-01 deviation suggests #1 should also choose abstraction-layer (single tool-use vs 5-action) | **EXTEND** — #1 adds abstraction-layer sub-choice with default = single tool-use (§1.7-A) | aidazi/process/tech-architecture-decision-catalog.md (revised) |
| **Δ-4** Doc lifecycle live vs intermediate | doc_category front-matter | csagent uses category implicitly; aidazi/process/doc-lifecycle-rules.md codifies | **KEEP** | aidazi/process/doc-lifecycle-rules.md |
| **Δ-5** Context-passing efficiency (sufficient AND efficient) | context_budget front-matter | csagent prompt-artifact-rules §9 reflects | **PROMOTE** — was Δ; now §1.4-i Constitution clause | aidazi/governance/constitution.md §1.4-i |
| **Δ-6** Type A runtime architecture skeleton (intent gate + phase pipeline) | Skeleton portable T1 | csagent runtime matches; eval skill_procedure_check.py adds the 6-primitive trace_check DSL as universal portable evaluator surface | **EXTEND** — add the 6-primitive DSL as portable Tier-2 surface (frozen grammar §1.7-B-anchor) | aidazi/process/typeA-runtime-architecture-skeleton.md (revised) |
| **Δ-7** §L Worked Example Instance | examples/csagent-reference/ read-only | aidazi/examples/ exists as stub | **EXTEND** — add examples/hermes-reference/ (A+B hybrid) | aidazi/examples/{csagent-reference,hermes-reference,fortunes-reference-placeholder}/ |
| **Δ-8** Open questions carry | Process-only | OK | **KEEP, REFRESH** | §11 of this plan; per-Δ open Qs in respective docs |
| **Δ-9** OBS / autoloop role-split (OBS ≠ R-item; two-layer triage + optimization) | Process doc | csagent action_bank M-Auto-6 has 7 OBS vs 8 R-items in use; discipline alive | **KEEP**, **REFRAME** under 5-role chain (Tech Lead owns OBS triage; Acceptance fix_required produces gap brief which becomes R-item if matures) | aidazi/process/post-deployment-iteration.md (revised) |
| **Δ-10** Doc-responsibility-matrix (8 fields incl artifact_type) | Schema | aidazi/process/doc-responsibility-matrix.md implemented; csagent has partial coverage | **KEEP + VALIDATE** — add `cell_size_target` field for handoff §0 cells (csagent drift evidence) | aidazi/process/doc-responsibility-matrix.md (revised) |
| **Δ-11** Capability-staging roadmap S0~S6 + S1.5/S2.5/S5/S3.5 + reverse trigger table | Process doc + Δ-17 stages | csagent 54-day timeline + sprint cadence supports | **KEEP**, **AMEND**: S5 entry condition includes "§3.5 Acceptance judge calibration completed" | aidazi/process/capability-staging-roadmap.md (revised) |
| **Δ-12** Artifact taxonomy 11 artifacts + per-role read-list + action_bank lifecycle | Taxonomy | csagent actually has ≥14: **missing deliver_close_taxonomy.md, research-briefs/, acceptance reports/** | **KEEP + EXTEND** — taxonomy grows to 14 artifacts; per-role read-list updated | aidazi/process/artifact-taxonomy.md (revised) |
| **Δ-13** Architecture-stable softened (stage-stable heuristic, not gate) | Heuristic | csagent M2 pivot 2026-05-17 supports softening | **KEEP** | aidazi/process/stage-stable-heuristic.md |
| **Δ-14** Profile-aware maturity Type A/B/C necessary sets | Process | csagent=A, fortunes=C placeholder; hermes=A+B hybrid evidenced | **KEEP + EXTEND** — add A+B hybrid profile column | aidazi/process/profile-aware-maturity.md (revised) |
| **Δ-15** Agent-design elicitation (6 must-answer + 4 inventories + 0→1 industry research) | Heuristic Q&A | csagent BRD/PRD process supports | **KEEP + AMEND** — Part A Q6 (Boundary) now includes "where Acceptance evaluates closure_contract"; Part B inventory adds "claimed closure_contract draft" | aidazi/process/agent-design-elicitation.md (revised) |
| **Δ-16** Agent-creation prerequisites (7 categories of input artifacts) | Process | csagent BRD §1.4 + phase1 enumerates 6/7; hermes constraints similar | **KEEP** | aidazi/process/agent-creation-prerequisites.md |
| **Δ-17** Common detours & warnings Type A (P1-P4 + new stages) | Patterns | csagent foundational + sprint history substantiates | **KEEP** | aidazi/process/common-detours-and-warnings-typeA.md |
| **Δ-18 NEW** Orchestrator-pattern | — | hermes orchestrator/ 2815 lines production code | **NEW** — full spec §4.2 below | aidazi/process/orchestrator-pattern.md (NEW) |

**Δ-12 14-artifact extended set** (was 11 in v3.2):
1. action_bank.md (live ledger) — unchanged
2. action_bank_archive.md — unchanged
3. proposals/*.md — **kept as is** (Checkpoint 2 correction): proposals/ is the **ad-hoc exploration** dir (human casually chats with a coding-agent and the output lands here); NOT renamed; lower formality than research-briefs/; see §4.3.1 for authoring authority distinction
4. diagnostics/*.md + failure-briefs/ — unchanged
5. sprint_objective.md — unchanged
6. milestone_objective.md — unchanged
7. handoff.md §0 cold-start — unchanged, BUT cell_size_target enforced
8. handoff.md §1 narrative — unchanged
9. handoff.md §2 archive index — unchanged
10. codex-findings.md — unchanged
11. **research-briefs/<id>.md** — NEW v4 (Acceptance closure_contract carrier); supersedes csagent's `docs/solutions/` semantics for **formal** Research Agent output. Distinct from `proposals/` (informal exploration); REQUIRED closure_contract; Customer-signed. See §4.3 for full authoring rules
12. **acceptance-reports/<scope>-acceptance-report.md** — NEW v4 (Acceptance verdict + gap brief)
13. **deliver_close_taxonomy.md** — NEW v4 (was in csagent docs/current/ since 2026-Q2, v3.2 missed it)
14. **adoption-state.md** — NEW v4 (adopter ↔ framework gap-tracking ledger; §8 fold-back protocol uses this)

### §4.2 Δ-18 orchestrator-pattern — full spec (NEW)

Source: hermes-autoloop `orchestrator/{loop.py 1429L, agents.py 531L, acceptance.py 297L, charter.py 207L, gates.py 149L, checkpoints.py 85L, state.py 103L}` + `docs/proposals/{orchestration-protocol-draft,acceptance-agent-draft,mission-charter-template-draft,aidazi-workflow-governance-variant}.md`.

#### §4.2.1 Δ-18 is conditional, not universal

Orchestrator pattern applies when adopter chooses `autonomy.level ≠ human_in_the_loop`. Pure human-in-the-loop adopters (manual handoff via paste; csagent's current mode) do NOT need Δ-18 implementation; they use the 5-role chain directly with human as orchestrator.

Δ-18 unlocks:
- File-based checkpoint inbox (human-on-the-loop)
- Auto-dispatch of sub-sprints within charter-approved scope
- §3.5 calibration-gated Acceptance judging
- F5 evidence pattern (orchestrator runs eval harness; dev sandbox stays sealed)
- Scope-envelope enforcement before close (deterministic, no LLM)

#### §4.2.2 Charter schema (T0 base + T1 profile overlays — Checkpoint 1 #5)

T0 base (any track):

```yaml
mission:
  id: <sprint-or-milestone-id>
  goal: <one-line user-facing goal — what Customer reads at gate 2>

autonomy:
  level: human_in_the_loop | human_on_the_loop | fully_autonomous_within_budget
  # human_in_the_loop:         every checkpoint requires explicit human approval
  # human_on_the_loop:         MANDATORY_CHECKPOINTS only; orchestrator auto-advances otherwise
  # fully_autonomous_within_budget: orchestrator auto-advances within budget caps; degrades to
  #                            human_on_the_loop if §3.5 acceptance calibration not yet passed

  approved_scope:
    subsprint_sequence: [<id>, ...]              # canonical order; mismatches = scope_deviation
    layers_allowed: [<framework-layer-name>, ...] # subset of Δ-3 fix-layer set per track
    modules_in_scope: [<repo-path>, ...]
    explicitly_out_of_scope: [<repo-path>, ...]

  auto_pass_rules:
    clean_pass_auto_advance: true | false        # advance on clean dev close without checkpoint
    auto_fix_iteration:
      enabled: true | false
      max_rounds: <int>
      only_if_findings_severity_at_most: P0 | P1 | P2
    adaptive_insert:
      enabled: true | false
      max_inserted_subsprints: <int>             # how many in-flight sub-sprints orchestrator may add

budget:
  max_api_usd: <number>                          # caveat: doesn't track subscription-billed agents (Codex)
  max_fix_rounds_total: <int>
  max_wall_clock_minutes: <int>

tooling:
  research:
    agent_kind: claude_code | codex | <other>
    model: <model-id>
  deliver:
    agent_kind: claude_code | codex | <other>
    model: <model-id>
  dev:
    agent_kind: claude_code | codex | <other>    # CONFIGURABLE per Checkpoint 1 #1
    model: <model-id>
    sandbox: workspace_write | read_only         # default workspace_write; no network; no git push
  review:
    agent_kind: claude_code | codex | <other>
    model: <model-id>
    tools: [Read, Grep, Glob]                    # mechanical read-only whitelist
  eval:
    cmd: <shell-command>                         # F5 pattern: orchestrator runs this
    timeout_seconds: <int>
  acceptance:
    enabled: true | false
    agent_kind: claude_code | codex | <other>
    model: <model-id>
    tools: [Read, Grep, Glob]                    # read-only
    judge_calibration:
      status: uncalibrated | calibrated
      agreement_threshold: 0.9
      flip_threshold: 0.1
      labeled_set_path: <path>
    run_at: milestone_close | release_cut | both
    on_fix_required:
      human_confirm_required: true               # Checkpoint 1 #2 — MUST be true
      route_options: [deliver_fix_iteration, re_acceptance_after_evidence, research_contract_revision]
```

T1 profile overlays:

```yaml
# Type A AI Agent
profile_type_a:
  layer_set: [infra, java_guard, prompt_projection, skill_state, semantic_planner,
              eval_spec, product_policy, judge_calibration, human_review_required]
  closure_contract_source: research_brief         # Research holds; Acceptance evaluates against
  bad_case_lifecycle: badcase-lifecycle.md
  phase_pipeline_required: true                   # Δ-6 skeleton applies

# Type B Agentic Workflow (PLACEHOLDER per Checkpoint 1 #4)
profile_type_b:
  layer_set: [infra, runtime_guard, workflow_definition, prompt_projection, skill_state,
              eval_spec, product_policy]
  sop_definition:
    source: <path-to-SOP-Excel-or-yaml>
    verification_gates_per_step: true
  # Full Type B spec deferred until hermes completes its first SOP milestone (lessons-fold-back to v5)

# Type C Demo App
profile_type_c:
  layer_set: [infra, demo_correctness]
  local_acceptance_checklist:
    source: <path-to-LOCAL_ACCEPTANCE_CHECKLIST.md>
  off_the_shelf_skill_inventory_required: true
```

#### §4.2.3 MANDATORY_CHECKPOINTS (8 — charter can ADD never REMOVE) (§1.7-D)

1. **mission_start** — orchestrator boots; human verifies mission.goal + autonomy.level + tooling. Once approved, only mission-end can revisit.
2. **research_proposal_selection** — if Path 1 (research-driven), human selects from candidate proposals before Deliver consumes.
3. **bad_case_manual_review** — primary §5.6 gate; human reads per-turn bad-case traces before milestone close.
4. **new_tier0_candidate** — any time a Code Reviewer or Deliver proposes a new Tier-0 invariant (which expands Java/runtime ownership), human approves before adoption.
5. **forbidden_list_redline** — any time a change touches §1.7 forbidden list semantics (e.g., a new exception case), human reviews.
6. **scope_deviation** — orchestrator's deterministic scope_envelope_check (§4.2.5) fires; human resolves before resume.
7. **close_taxonomy_C_or_D** — when deliver close verdict = C (scope-broadening) or D (non-convergent), human resolves. Maps to deliver_close_taxonomy.md subclasses.
8. **gate_hard_fail** — any deterministic gate (tests / handoff structure / trace existence / safety / grounding floor) fails AND auto_fix_iteration not eligible.

#### §4.2.4 State machine (Type A driver)

```
                            ┌─────┐
                            │idle │
                            └──┬──┘
                               │ (charter loaded; current_subsprint set)
                               ↓
                       ┌──────────────┐
                       │ dev_pending  │ (preflight: contract present + non-empty)
                       └──────┬───────┘
                              ↓ spawn_dev → handoff written
                       ┌──────────────┐
                       │ gate_pending │ (run_tests / validate_stanza / check_handoff
                       └──────┬───────┘  / check_trace / [run_eval F5])
                              ↓ gates pass
                       ┌──────────────────┐
                       │ review_pending   │ spawn run_review
                       └──────┬───────────┘
                              ↓ verdict written (pass | fix_required | out_of_scope_review)
                       ┌──────────────────┐
                       │  close_pending   │ spawn spawn_deliver_close
                       └──────┬───────────┘
                              ↓ verdict A/B/C/D + scope_envelope_check (deterministic, NO LLM)
                              ↓ route_close: advance | fix | checkpoint
                ┌─────────────┴─────────────┐
                ↓                            ↓
        ┌───────────────┐         ┌───────────────────┐
        │   advance     │         │       fix         │
        │ (next sub-    │         │ spawn deliver_    │
        │ sprint OR     │         │ plan_fix → bump   │
        │ milestone_    │         │ fix_round →       │
        │ close)        │         │ back to dev_      │
        └───────┬───────┘         │ pending           │
                ↓                  └───────────────────┘
        ┌───────────────┐
        │milestone_     │
        │close          │ ← MANDATORY_CHECKPOINT #3 bad_case_manual_review here
        └───────┬───────┘
                ↓ (if charter.acceptance.enabled)
        ┌───────────────────┐
        │acceptance_pending │ run F5 eval evidence → spawn run_acceptance
        └───────┬───────────┘
                ↓ acceptance verdict
                ↓ route_acceptance:
       ┌────────┼─────────────────────────┐
       ↓        ↓                          ↓
     pass   fix_required               needs_human
       │        │                          │
       │        ↓ post human-confirm        ↓
       │     checkpoint (3 route options)   surface_approve
       │        │                          checkpoint
       │   ┌────┼──────────┐
       │   ↓    ↓          ↓
       │ deliver re-      research-
       │  fix  acceptance  contract-
       │  iter (more       revision
       │   ↓   evidence)
       │   ↓                                ↓
     advance to next milestone OR halt    human writes decision
       (Customer signs ship at gate 2)
```

Key invariants:
- Skipped-but-required gate = NOT passed (no silent skip).
- Charter can't widen scope mid-run; only checkpoint resolution can.
- close_pending's deterministic scope_envelope_check runs BEFORE LLM close verdict is trusted.
- Acceptance only runs if charter.acceptance.enabled AND judge calibration passed (§3.5).
- All decisions checkpointed to `docs/checkpoints/` filesystem so human can audit.

#### §4.2.5 scope_envelope_check (deterministic, no LLM)

Pure function over (charter.approved_scope, observed_diff, declared_next_subsprint):
- subsprint_id ∈ charter.approved_scope.subsprint_sequence
- every layer claimed touched ∈ charter.approved_scope.layers_allowed
- every module touched ∈ charter.approved_scope.modules_in_scope ∧ ∉ explicitly_out_of_scope
- no module touched that's not declared anywhere (unknown_module)

Any of these failing → scope_deviation MANDATORY_CHECKPOINT.

#### §4.2.6 F5 evidence pattern

Orchestrator (not the agent) runs the eval harness when Acceptance needs execution evidence:

```
orchestrator → execute charter.tooling.eval.cmd → capture stdout/stderr/artifacts
            → pass artifact paths to spawn run_acceptance as read-only context
            → Acceptance reads evidence in its read-only sandbox
```

This pattern lets Acceptance judge from real execution data WITHOUT giving Acceptance write access OR network OR the dev sandbox. Both sandboxes stay sealed; evidence flows through filesystem.

#### §4.2.7 Spawn function set + JSON verdict schemas

Each spawn function has a published JSON-schema verdict shape so orchestrator can parse deterministically without LLM string-matching.

| Function | Backing agent (default) | Tools | Verdict schema |
|---|---|---|---|
| spawn_dev | per charter.tooling.dev | workspace-write | (none — code edits + handoff file is the artifact) |
| spawn_deliver_close | per charter.tooling.deliver | default | `{verdict: A\|B\|C\|D, blocking_count: int, worst_severity: P0\|P1\|P2\|none, in_scope: bool, next_subsprint: <id\|null>, reason: string}` |
| spawn_deliver_plan_fix | per charter.tooling.deliver | default | `{subsprint_id: string, layers: string[], modules: string[], objective_md: string, dev_prompt_md: string, summary: string}` |
| spawn_research | per charter.tooling.research | default | `{brief_id: string, brief_md: string, closure_contract_summary: string, scope_in: string[], scope_out: string[]}` |
| run_review | per charter.tooling.review | Read,Grep,Glob whitelist | `{decision: pass\|fix_required\|out_of_scope_review, blocking_count: int, summary: string, findings: object[]}` |
| run_acceptance | per charter.tooling.acceptance | Read,Grep,Glob whitelist | `{milestone_verdict: pass\|fix_required\|needs_human, cases: object[] (per-criterion evidence), failure_briefs: object[], suggested_route: enum}` |

#### §4.2.8 Δ-18 anti-patterns (forbidden — §1.7 extensions)

- Charter editing MANDATORY_CHECKPOINTS to remove (§1.7-D).
- Running `run_acceptance` in `fully_autonomous_within_budget` mode without §3.5 calibration passed.
- Bypassing `scope_envelope_check` on close.
- Giving Dev sandbox read access to `case_specs_shadow/` (or equivalent holdout eval set).
- Acceptance verdict claiming pass/fail from CODE INSPECTION instead of execution evidence (F5 pattern violation).
- Charter defaulting `acceptance.mode=auto_iterate` while `judge_calibration.status=uncalibrated` (degradation must be automatic, never opaque).
- Spawning Acceptance Agent from a Deliver or Dev session (§1.7-C).
- Acceptance routing `fix_required → Deliver` without a written human-confirm checkpoint decision (Checkpoint 1 #2).

### §4.3 Directory taxonomy + authoring authority (NEW per Checkpoint 2)

Critical for adopter clarity: every doc directory has a **single primary author** + **specific trigger** + **specific content type** + **specific promotion path**. csagent's practice has some implicit overlap (a human's casual chat may land in `proposals/` vs a formal Research session lands in `solutions/` vs an agent's mid-sprint discovery lands in `diagnostics/`) — v4 makes the split explicit.

#### §4.3.1 Per-directory authoring rules

| Directory | Primary author | Trigger | Content type | Lifecycle | Promotes to | Customer interaction |
|---|---|---|---|---|---|---|
| `docs/research-briefs/<id>.md` | **Research Agent** (formal mode) | Customer formally asks "what should we build" OR Path-2 failure-brief matures | **Formal need spec**: closure_contract (mandatory) + scope IN/OUT + anti-goal + KPI + related R-items | live until milestone close; archive to `docs/sprints/` after | terminal for Path 1; consumed by Deliver + Acceptance | **Customer signs gate 1** |
| `docs/proposals/<id>.md` | Research Agent (exploratory) OR ad-hoc coding-agent session | Human casually opens a session: "how would we approach X?" | **Design exploration**: lower formality; NO closure_contract required; may sketch tradeoffs / candidate approaches | intermediate (Δ-4); frozen at creation | may promote to research-brief if human selects + Research Agent re-runs formally | Customer reads as informational; does NOT sign |
| `docs/diagnostics/<id>.md` | Dev / Code Reviewer / Deliver Agent (during sprint work) | Agent discovers something mid-sprint (mid-PR, mid-review, mid-investigation) | **Root-cause analysis**: "why does X behave this way?"; cites code paths + traces | intermediate (Δ-4); referenced from sprint-handoff §9 | may promote to failure-brief (if pattern n≥2) or R-item in action_bank | Customer typically does NOT read; tech-internal observation |
| `docs/diagnostics/failure-briefs/<id>.md` | **Joint human + Deliver Agent** | Bad-case observed + triage decides it's load-bearing (n≥2 OR severe) | **Failure shape report** — 6-field template per Δ-2: (1) what happened, (2) what should good agent have done, (3) why does this matter, (4) one-off-or-pattern, (5) which §3 layer, (6) what NOT to do | intermediate per sprint | Path 2 Research Agent input → produces research-brief → back into normal flow | Customer may co-author "what should good agent have done" field |
| `eval/bad_cases/<id>.yaml` (or equivalent suite dir) | **Joint** (Deliver Agent curates structure; human authors closure_criterion) | Failure-brief promoted to **reproducible runtime test** | **CaseSpec yaml** with closure_criterion per §1.7-B (positive shape + anti-pattern + anchor phrases; NOT keyword match) | live regression suite until tier-downgraded to closed-as-regression-guard or archived | terminal for regression suite | n/a (runtime artifact for Acceptance Agent + Code Reviewer) |
| `docs/acceptance-reports/<scope>-acceptance-report.md` | **Acceptance Agent** | Acceptance run at milestone close / release cut / sub-sprint close (per charter) | **Verdict + per-criterion evidence + gap brief if fail + suggested route** {deliver_fix_iteration \| re_acceptance_after_evidence \| research_contract_revision} | intermediate per scope; archived to milestone close package | gap brief consumed by Deliver (Path 3 fix-iteration) **after human-confirm checkpoint** | **Customer reads gate 2; signs ship/no-ship** |
| `docs/codex-findings.md` | **Code Reviewer Agent** | Review run (sub-sprint close, §4.3 trigger, milestone close) | **Anti-hardcode kernel results + correctness findings**; §4.2 4-line header verdict | intermediate per sprint/milestone; archived at close | consumed by Deliver at close conversation per `deliver_close_taxonomy.md` | Customer typically does NOT read; tech-side artifact |
| `docs/action_bank.md` (live) | **Deliver Agent** maintains; Dev/Reviewer surface items | Sprint/milestone observation; ongoing backlog | **R-items + OBS-items + open Qs** ledger | live; soft size cap (suggested per §7) | sweep to `action_bank_archive.md` at milestone close | n/a |
| `docs/current/adoption-state.md` (NEW) | **Human owner** (adopter side) | Adopter overrides a framework default OR observes a divergence | **Per-Δ status table** + drift rationale + lessons-to-propose | live; review per milestone close | feeds `aidazi/lessons/<date>-<topic>.md` for fold-back | n/a (adopter-internal) |

#### §4.3.2 Authoring authority by input modality

The user's confusion centered on: where does a particular input land? The table below maps observable input shapes to their target dir:

| Observable input shape | Who provides | Lands in | Reason |
|---|---|---|---|
| Customer formally requests something | Customer prompts Research Agent (paste activation) | `docs/research-briefs/<id>.md` | Gate 1 — Customer signs; closure_contract required |
| Customer casually asks "how would you approach X?" | Customer chats with any coding-agent ad-hoc | `docs/proposals/<id>.md` | Lower formality; may later promote |
| Customer/colleague reports a single failure | Verbal/written observation | first → human + Deliver triage → if load-bearing → `docs/diagnostics/failure-briefs/<id>.md`; if reproducible → `eval/bad_cases/<id>.yaml` | Triage step is **mandatory** — not every observation becomes a brief; n≥2 threshold for pattern |
| Pattern of N≥2 similar failures | Multiple instances collected over time | `docs/diagnostics/failure-briefs/<id>.md` (formal); then Path 2 Research Agent → `docs/research-briefs/<id>.md` | Pattern threshold prevents one-off premature R-item creation |
| Agent finds something during sprint work | Dev / Reviewer / Deliver during investigation | `docs/diagnostics/<id>.md` | NOT a Customer need; tech-internal observation |
| Agent finds delivery-vs-promise gap at milestone close | Acceptance Agent verdict = `fix_required` | `docs/acceptance-reports/<scope>-acceptance-report.md` (with gap brief section) | The formal "delivered ≠ promised" detector |
| Reviewer finds anti-hardcode violation | Code Reviewer Agent verdict | `docs/codex-findings.md` | Code-side observation, not need-side |
| Adopter intentionally diverges from framework default | Human owner | `docs/current/adoption-state.md` row marked `status: divergent` + rationale | Per §7.0 — framework default override path |

#### §4.3.3 Who writes where — quick reference

**Human writes directly** (no agent intermediary):
- Customer prompts feeding Research / Acceptance (raw input; not a stored doc by themselves)
- `docs/checkpoints/*.md` `decision:` field (human resolves orchestrator checkpoints)
- `docs/diagnostics/failure-briefs/<id>.md` (joint with Deliver; human labels expected behavior + Deliver hypothesizes layer)
- `eval/bad_cases/<id>.yaml` `closure_criterion` (joint with Deliver; human writes customer-perspective end-state)
- `docs/research-briefs/<id>.md` `customer_signed:` front-matter (Customer sign-off, gate 1)
- `docs/current/adoption-state.md` (when overriding framework defaults, human authors rationale)

**Agent writes** (per §4.3.1 table above):
- All other docs in the taxonomy

**Joint authoring** (cannot be auto-merged):
- failure-briefs (6-field template; human + Deliver each own specific fields)
- bad_cases CaseSpec (Deliver curates structure; human authors closure_criterion)
- close decisions per deliver_close_taxonomy.md (Deliver proposes verdict A/B/C/D; human signs)

#### §4.3.4 What about "agent discovered delivery-vs-promise gap"? (the user's specific question)

Scenario: an agent (typically Dev mid-sprint or Code Reviewer mid-review or Acceptance at milestone close) finds the implementation has drifted from the original research-brief's closure_contract.

**Two distinct lifecycle moments** map to two distinct dirs:

1. **Mid-sprint discovery** (Dev or Reviewer notices during work):
   - Authors: `docs/diagnostics/<id>.md` describing the gap, cross-linking to the affected `research-briefs/<id>.md` and the specific code paths
   - Then escalates to one of:
     - Deliver Agent for in-flight scope adjustment — BUT §8.5 milestone-framework forbids mid-milestone scope expansion; usually defer
     - new R-item in `action_bank.md` for next sprint/milestone (most common path)

2. **End-of-milestone discovery** (Acceptance Agent at milestone close):
   - Lands in: `docs/acceptance-reports/<scope>-acceptance-report.md` with structured gap brief
   - Then routes through **human-confirm checkpoint** (§3.4) → if confirmed → Deliver Agent picks up gap → fix-iteration sub-sprint authored

**Distinction**: `diagnostics/` is mid-flight observation in code-perspective. `acceptance-reports/` is end-of-milestone verdict in contract-perspective. Same kind of failure can be observed in both; they don't overlap because they live at different lifecycle moments + use different lenses + route differently.

---

## §5 — Application Guide (REFRAMED per Checkpoint 1 #5)

### §5.0 Mental model

**The old framing** (v3.2): Phase 0 "Normative Freeze" → Phase 1 input pack → … → Phase 5 eval.

**Why we drop "Phase 0 Normative Freeze"**: csagent had no framework when Phase 0 ran in 2026-04. Phase 0 existed specifically to invent norms/governance from scratch. With v4, the framework IS the norms — Phase 0 collapses into "adopt the framework". You don't normatively freeze; you inherit.

**The new framing**: Application Guide = **how to land the framework into a new app** + **how to walk the remaining Phase 1-5 funnel framework-aware**.

Two adoption shapes:

1. **Greenfield** (no existing codebase or existing codebase has no agent yet): fast inherit. Framework provides scaffolding + defaults; adopter fills in domain-specific values.
2. **Brownfield** (existing codebase already has agent/workflow/demo work, possibly with own norms): **human-led manual guide**. Framework provides a checklist + decision tree; human owner chooses what to inherit vs preserve vs reconcile per brownfield-specific tradeoffs. NO automation tries to merge framework into brownfield norms — too project-specific.

### §5.1 Greenfield bootstrap path

```
INPUT: (a) Type designation (A / B / C / A+B hybrid)
       (b) 0→1 brief draft (BRD-level: problem + KPI + scope IN/OUT + anti-goal)
       (c) New codebase path (may be empty repo)

STEP 1. Initialize framework
   git submodule add <aidazi-url> framework
   cp framework/templates/AGENTS.md ./AGENTS.md
   # AGENTS.md @-includes the constitution chain
   
STEP 2. Run Δ-15 elicitation (agent-design-elicitation.md)
   • 6 mandatory questions (Domain / Goal / Problems / Method / Knowledge / Boundary)
   • 4 inventories (per profile: A=Knowledge/Tools/Skills/Policy; B=K/T/SOP/P; C=K/T/Off-shelf-skill/P)
   • Tool vs Skill decision tree (A only)
   • Part D Industry research synthesis (A only; produces discovery/industry-synthesis-<id>.md)
   • Customer signs brief → Δ-15 human-signoff lands

STEP 3. Run Δ-16 prerequisite gate (agent-creation-prerequisites.md)
   • Verify 7 categories of input artifacts present at READY/DEFERRED/N/A levels
   • Per-profile required set check
   • Any DEFERRED auto-generates OBS-id under "prereq-deferred" tag

STEP 4. Configure framework instantiation
   • Constitution stays @-included; not edited
   • Create docs/current/{domain_taxonomy, runtime_invariants, eval_acceptance_bars}.md
     from templates with project-specific values
   • Create first research brief at docs/research-briefs/<id>.md with closure_contract

STEP 5. Walk Phase 1-5 funnel (framework-aware versions; progressive disclosure)
   • Phase 1 — Business need & goal: docs/foundational/business-need.md
       — Δ-15 Q1-Q3 (Domain / Goal / Problems) → market understanding + business KPI + scope IN/OUT + anti-goal
       — REQUIRED before Phase 2 starts; this is the source of truth
       — Customer signs (gate 1)
       — Pull in Δ-16 #1 BRD prerequisite ONLY (other Δ-16 categories come at later phases when relevant)
   • Phase 2 — Product/Service design: docs/foundational/product-service-design.md
       — Translate business need into product/service form
       — Type A: UC registry + tool spec from transcript samples + domain handling rules
       — Type B: SOP step registry + per-step verification gates
       — Type C: off-the-shelf skill inventory
       — Pull in Δ-15 Part B+C inventories + Δ-16 #2 PRD prerequisite at this phase
       — Δ-3 decision #1 (abstraction-layer; default single tool-use per §1.7-A) lands here
       — **Reverse-flow**: if Phase 2 cannot deliver Phase 1 → push back to Phase 1 (revisit scope or KPI)
   • Phase 3 — Technical plan: docs/foundational/technical-plan.md
       — **NOW** pull in technical constraints (Δ-16 #3) + external systems/APIs (Δ-16 #6) + UI (Δ-16 #7)
       — Engineering baseline + platform/system API specs (e.g., Salesforce, internal services) + integration approach + infrastructure + security/PII floor
       — Δ-6 portable runtime skeleton instantiated with project-specific phase pipeline
       — Δ-3 decisions #2-#7 (context projection / state / memory / tools / policy)
       — Tier-0 invariant list authored
       — **Reverse-flow**: if Phase 3 finds Phase 2 design technically infeasible → push back to Phase 2 (re-design service/product)
   • Phase 4 — Coding/Implementation packet: docs/foundational/coding-packet.md
       — Module breakdown DM1..N + delivery order + mocks list + .env values
       — Pull in Δ-16 #4 knowledge corpus + #5 canned reply (Type A primarily)
       — **Reverse-flow**: if Phase 4 budget/scope mismatch → push back to Phase 3 (or Phase 2)
   • Phase 5 — Eval/Release/Feedback: docs/foundational/eval-design.md
       — Instantiate CaseSpec schema from M-Evaluation template
       — Seed bad-case suite from Phase 2 known fail samples + Phase 3 risk areas
       — Configure judge with rubric per project domain
       — Author Δ-18 charter (if autonomy.level ≠ human_in_the_loop)
       — Configure calibration set for §3.5 acceptance gate
       — **closure_contract from Phase 1 research-brief is the Acceptance verdict source**
       — **Reverse-flow**: if Phase 5 reveals reproducible failure → root-cause may push back to any earlier phase

STEP 6. Bootstrap iteration loop
   • Author first milestone_objective.md (deliver agent)
   • Author first sprint_objective.md
   • Author first compact/sprint-001-dev-prompt.md
   • Run first Dev → Reviewer → close cycle
   • Bootstrap action_bank.md with backlog placeholders
   • Bootstrap handoff.md §0 with cold-start table

STEP 7. (Optional) Bootstrap Δ-18 orchestrator
   • Author mission charter YAML
   • Run calibration set if Acceptance enabled
   • orchestrator run --max-steps <N>
```

### §5.2 Brownfield bootstrap path (human-led manual guide)

Brownfield projects vary too much for automation. The Application Guide provides a **decision checklist** for the human owner.

**Brownfield checklist** (`application-guide/02-brownfield-manual.md` — sub-doc):

```
INVENTORY (read-only — do NOT change anything yet)
□ What's the current adoption track? (A / B / C / A+B hybrid)
□ Does the project already have governance docs? (AGENTS.md, CLAUDE.md, role docs?)
□ Does it have an action_bank or backlog ledger? In what format?
□ Does it have an eval framework? What kind of CaseSpec schema?
□ Does it use any orchestrator currently?
□ What's the current human/agent split? Pure human-paste, or some automation?

DECIDE (per-area, human owner judges tradeoffs)
□ Constitution: REPLACE with framework? KEEP existing? MERGE?
   Recommend: REPLACE unless project has explicit deviation reasons documented.
□ Role definitions: ADOPT 5-role chain? KEEP 4-role? Add Acceptance only?
   Recommend: ADOPT 5-role chain (Acceptance is the high-value addition).
□ Action_bank: MIGRATE to framework taxonomy? KEEP existing format?
   Recommend: KEEP existing format BUT add Δ-12 sweep cadence + archive split.
□ Eval: ADOPT M-Evaluation template? KEEP existing?
   Recommend: KEEP existing if mature; ADAPTOR to framework shape for portability.
□ Δ-18 orchestrator: ADOPT? OPT OUT?
   Recommend: OPT OUT unless adopter has multi-sub-sprint cycles to automate.

RECONCILE (after deciding)
□ Author docs/current/adoption-state.md (§8 §4.1 #14 — new artifact)
   For each Δ-1..Δ-18: status ∈ {at-spec, partial, divergent, not-applicable, superseded-by-framework}
   For each divergent: 1-sentence reason
□ Map existing docs to framework schema; rename where necessary
□ Add @-includes to AGENTS.md for inherited governance docs
□ Author docs/research-briefs/ as new dir (if Acceptance enabled)
□ Document the brownfield-specific carve-outs in adoption-state.md → divergent rows

VALIDATE
□ Run first sprint under new role chain
□ Confirm 5-role boundary invariants hold (§3.3) — no role collapse to single role
□ Run first Acceptance pass with closure_contract from any matured Research brief
□ Update adoption-state.md based on observed gaps
```

The brownfield guide is intentionally less prescriptive than greenfield. Human owners decide; framework provides the menu.

### §5.3 Phase 1-5 funnel (REWRITTEN per Checkpoint 2: progressive disclosure + reverse-flow)

The phase pipeline lives at `aidazi/application-guide/{03..07}-phase-N.md`. **Progressive disclosure principle**: each phase pulls in ONLY the inputs that are relevant at that phase. Technical constraints don't come in at Phase 1; they arrive at Phase 3 where they're needed for design. **Reverse-flow signals**: when a later phase reveals an earlier phase is infeasible, the adopter explicitly backtracks (not silently re-decides).

| Phase | Purpose | Inputs at this phase (progressive) | What framework provides | What project must fill | Reverse-flow trigger |
|---|---|---|---|---|---|
| **Phase 1 Business need & goal** | Define what the customer/market wants and the project must satisfy. The "what should we build" statement. | Market understanding, customer/user need description, business KPI, scope IN/OUT, anti-goal | Δ-15 Q1-Q3 (Domain / Goal / Problems) elicitation + Δ-16 #1 BRD prerequisite schema | Project-specific market analysis, KPI thresholds, scope boundaries, anti-goal phrasing; Customer sign-off (gate 1) | source phase — no reverse-flow from above |
| **Phase 2 Product/Service design** | Design the product/service that satisfies Phase 1. The "how do we satisfy" — what UCs/SOPs/skills compose the service. | Phase 1 output + domain processing rules + (Type A) transcript samples for UC inference + (Type B) SOP draft + (Type C) off-the-shelf skill catalogs + Δ-16 #2 PRD | Δ-15 Part B+C inventories + Δ-3 decision #1 (abstraction-layer; default single tool-use §1.7-A) + Δ-3 decision #6 (tools definition) | Project-specific UC names + IDs (Type A), tool ALLOW matrix, escalation enum (Type A); SOP step registry + per-step verification gates (Type B); off-the-shelf skill list (Type C); domain handling rules | If Phase 2 cannot deliver Phase 1 → push back to Phase 1 to revisit scope or KPI |
| **Phase 3 Technical plan** | Plan how to implement Phase 2 technically. Technical constraints + integration with existing systems arrive HERE — not earlier. | Phase 2 output + Δ-16 #3 engineering baseline + Δ-16 #6 external systems/APIs (e.g., Salesforce, internal services) + Δ-16 #7 UI definition (partial) + infrastructure + security/PII floor + cloud constraints | Δ-6 portable runtime skeleton + Δ-3 decisions #2-#7 (context projection / state / memory / tools / policy) + 6-primitive trace_check DSL surface | Project-specific phase pipeline names (e.g., csagent INIT→DISCOVER→RESOLVE→CONFIRM→CLOSE→ESCALATE), Tier-0 invariant list, projection model details, persistence layer, integration adaptors | If Phase 3 finds Phase 2 design technically infeasible → push back to Phase 2 to re-design product/service form |
| **Phase 4 Coding/Implementation packet** | Break the technical plan into shipping units. | Phase 3 output + Δ-16 #4 knowledge corpus + Δ-16 #5 canned reply templates | Δ-4 lifecycle rules + Δ-10 responsibility matrix scaffold module governance | Project-specific module names + dependencies (DM1..N), delivery order, mocks list, .env values | If Phase 4 reveals scope/budget mismatch → push back to Phase 3 or Phase 2 |
| **Phase 5 Eval/Release/Feedback** | Verify the delivered system satisfies Phase 1 closure_contract; close the loop. | Phase 3+4 outputs + Phase 1 closure_contract (the Acceptance verdict source) + bad-case seed | M-Evaluation 4-component model + 6-primitive trace_check DSL + 4-tier pyramid + Δ-18 charter template | Per-tier check selection per case, judge rubric specialization, baseline ledger initialization, calibration set authoring, charter values (if Δ-18 used) | If Phase 5 fails reproducibly → root-cause may push back to any earlier phase |

**Why progressive disclosure matters** (Checkpoint 2 clarification): a Phase 2 product/service designer doesn't need to know the platform's API schema yet — that's a Phase 3 input. Asking for it at Phase 2 either causes premature decisions (committing to Salesforce integration before service is defined) OR causes paralysis (need-finder gets blocked on tech specs). Each phase asks for ONLY what it can use; later phases pull in later inputs.

**Reverse-flow vs forward-only**: the funnel is NOT strictly forward. Real projects discover infeasibilities and contradictions at later phases that force earlier-phase adjustment. The framework names this **explicitly** so adopters don't silently "redo Phase 2" without owning that it's a backtrack. Each Phase doc carries a "reverse-flow triggered from" log section.

**Framework's structural payoff**: csagent spent ~54 days walking Phase 0-5 from scratch (no framework). A greenfield adopter inheriting v4 should compress Phase 1-2 to under a week — the schemas + decision catalogs are pre-loaded; only the domain-specific values need filling.

### §5.4 Worked examples (read-only references)

- `aidazi/examples/csagent-reference/` — Type A end-to-end (BRD → Phase 5 → 49+ sprints). Frozen snapshot 2026-06-06; not re-synced.
- `aidazi/examples/hermes-reference/` — Type A+B hybrid end-to-end (workflow_definition layer + SOP test pyramid). Frozen snapshot 2026-06-06.
- `aidazi/examples/fortunes-reference-placeholder/` — Type C; populated when first Type C lifecycle completes.

Worked examples are READ-ONLY after first snapshot. New adopters look at them to see "what filled-in framework looks like" but never sync upstream changes. When examples become significantly out-of-date (judged by user), build a new dated snapshot beside the old (keep both per Δ-4 intermediate lifecycle).

### §5.5 Profile decision tree (Type A vs B vs C vs A+B)

Sub-doc `application-guide/10-profile-decision-tree.md` walks:

```
Q1. Does the system primarily reason adaptively per turn, or follow a fixed sequence per task?
    adaptive → Type A
    fixed sequence → Type B
    
Q2. (if Type B) Does it also have an LLM-controlled top loop, or is the SOP-runner the only controller?
    yes top-loop → Type A+B hybrid
    no, SOP only → pure Type B
    
Q3. (if neither) Is this a demo/POC where customer-demonstrability beats coverage?
    yes → Type C
    no → revisit Q1; you may be conflating goals
```

Each branch routes to a specialized §5.1-style bootstrap path with the right Δ subset.

### §5.6 Application Guide sub-doc inventory

`aidazi/application-guide/` will contain these sub-docs (P4 extracts to here from §5 + §5.x of this plan):

- `00-overview.md` — read order + adopter decision tree
- `01-greenfield-fast-path.md` — §5.1 detail
- `02-brownfield-manual.md` — §5.2 detail
- `03-phase-1-inputs.md` — input pack template
- `04-phase-2-domain.md` — domain realization template per profile
- `05-phase-3-tech-design.md` — Δ-6 + Δ-3 instantiation
- `06-phase-4-modules.md` — module breakdown template
- `07-phase-5-eval.md` — M-Evaluation 4-component instantiation
- `08-iteration-bootstrap.md` — first AGENTS.md + first milestone + first sprint
- `09-orchestrator-bootstrap.md` — optional Δ-18 charter + calibration
- `10-profile-decision-tree.md` — §5.5 detail
- `11-adoption-state-ledger-template.md` — adopter-side gap-tracking template

### §5.7 Application Guide cross-references Δ-17 cognitive-detour

Application Guide is forward-looking. Δ-17 is backward-looking ("named pitfalls; if you're here, exit this way"). New adopters use the Guide to navigate forward; mid-flight adopters spot symptoms in Δ-17 to self-diagnose. Each Phase's framework-aware doc cross-references the relevant Δ-17 detour:

- Phase 1 input prerequisites ↔ P1 spec-first/data-late detour
- Phase 5 eval bootstrap ↔ P2 eval-before-architecture-stable detour
- Phase 5 + orchestrator bootstrap ↔ P3 autoloop-as-eval-stress-test detour
- Phase 3 + first milestone ↔ P4 mid-milestone-pivot detour

---

## §6 — Doc-tree topology (FINAL — v4 target aidazi/ shape)

```
aidazi/                                    # framework repo (separate; submodule consumer-side)
├── README.md                              # one-paragraph elevator + read-order
├── AGENTS.md                              # consumer-side TEMPLATE (copy to consumer root; edit placeholders)
│
├── governance/                            # Layer A — always-loaded
│   ├── constitution.md                    # §1 + §1.7 forbidden (with §1.7-A/B/C/D v4 additions)
│   ├── doc_governance.md                  # tier model + decision rules + lifecycle (Δ-4)
│   └── context_briefing.md                # cold-start read-order + Context Pack Prompt
│
├── process/                               # Layer B — on-demand by role
│   ├── domain-discovery-process.md        # Δ-2 (extended with inheritance-table pattern)
│   ├── tech-architecture-decision-catalog.md  # Δ-3 (extended with abstraction-layer sub-choice)
│   ├── doc-lifecycle-rules.md             # Δ-4
│   ├── context-passing-efficiency.md      # Δ-5 (now ALSO §1.4-i Constitution clause)
│   ├── typeA-runtime-architecture-skeleton.md  # Δ-6 (extended with 6-primitive trace_check DSL)
│   ├── worked-example-instance.md         # Δ-7
│   ├── post-deployment-iteration.md       # Δ-9 (reframed under 5-role)
│   ├── doc-responsibility-matrix.md       # Δ-10 (extended with cell_size_target field)
│   ├── artifact-taxonomy.md               # Δ-12 (extended to 14 artifacts)
│   ├── capability-staging-roadmap.md      # Δ-11 (S5 entry condition tightened)
│   ├── stage-stable-heuristic.md          # Δ-13
│   ├── profile-aware-maturity.md          # Δ-14 (extended with A+B hybrid column)
│   ├── agent-design-elicitation.md        # Δ-15 (extended with closure_contract field)
│   ├── agent-creation-prerequisites.md    # Δ-16
│   ├── common-detours-and-warnings-typeA.md  # Δ-17-A
│   ├── common-detours-and-warnings-typeB.md  # Δ-17-B placeholder
│   ├── common-detours-and-warnings-typeC.md  # Δ-17-C placeholder
│   ├── orchestrator-pattern.md            # Δ-18 NEW (full spec)
│   ├── milestone-framework.md             # promoted from csagent §8
│   ├── prompt-artifact-rules.md           # promoted from csagent §9
│   ├── badcase-lifecycle.md               # promoted from csagent §5.6
│   ├── architecture-health-metrics.md     # promoted from csagent §6 (collection still proposal-tier)
│   ├── self-governance.md                 # NEW §7 — doc-bloat prevention mechanics
│   └── fold-back-protocol.md              # NEW §8 — adopter ↔ framework
│
├── role-cards/                            # 5-role activation docs
│   ├── customer-checkpoints.md            # NEW — Customer on-the-loop checkpoint catalog
│   ├── research-agent.md                  # REWRITTEN — must produce closure_contract
│   ├── deliver-agent.md                   # AMENDED — handles 3 input paths (P1 research / P2 bad-case / P3 acceptance-gap)
│   ├── deliver-activation.md
│   ├── dev-agent.md
│   ├── code-reviewer-agent.md             # RENAMED from review-agent.md
│   └── acceptance-agent.md                # REWRITTEN — peer-of-Research; closure_contract verifier
│
├── templates/                             # prompt + ledger templates (filled at adopter side)
│   ├── compact-dev-prompt.md
│   ├── compact-review-prompt.md
│   ├── compact-acceptance-prompt.md       # NEW
│   ├── compact-research-brief.md          # NEW
│   ├── compact-codex-rebuttal-prompt.md   # NEW (formalizes csagent S-Auto-26 ad-hoc pattern)
│   ├── handoff-template.md                # §0/§1/§2 with cell_size_target enforcement
│   ├── sprint-objective.md
│   ├── milestone-objective.md
│   ├── mission-charter.yaml               # NEW — Δ-18 charter (T0 base + T1 profile overlays)
│   ├── deliver-close-taxonomy.md          # NEW — promoted from csagent docs/current/
│   ├── anti-hardcode-review-kernel.md     # Δ-19 kernel (renumber from v3.2 §4.1 since Δ-18 was the orchestrator)
│   ├── adoption-state-template.md         # NEW — per-adopter gap-tracking ledger
│   └── lessons-learned-template.md        # NEW — adopter → framework fold-back input
│
├── application-guide/                     # NEW — Layer B sub-doc bundle (§5)
│   ├── 00-overview.md
│   ├── 01-greenfield-fast-path.md
│   ├── 02-brownfield-manual.md
│   ├── 03-phase-1-inputs.md
│   ├── 04-phase-2-domain.md
│   ├── 05-phase-3-tech-design.md
│   ├── 06-phase-4-modules.md
│   ├── 07-phase-5-eval.md
│   ├── 08-iteration-bootstrap.md
│   ├── 09-orchestrator-bootstrap.md
│   ├── 10-profile-decision-tree.md
│   └── 11-adoption-state-ledger-template.md
│
├── schemas/                               # JSON schemas for verdict shapes
│   ├── review-verdict.schema.json
│   ├── deliver-close-verdict.schema.json
│   ├── deliver-plan-fix.schema.json
│   ├── acceptance-verdict.schema.json
│   ├── research-brief.schema.json         # NEW
│   ├── case-spec.schema.json
│   ├── mission-charter.schema.json        # NEW
│   └── adoption-state.schema.json         # NEW
│
├── examples/                              # worked instances (read-only after snapshot)
│   ├── csagent-reference/                 # Type A frozen
│   ├── hermes-reference/                  # Type A+B hybrid frozen
│   └── fortunes-reference-placeholder/    # Type C placeholder
│
├── lessons/                               # NEW — adopter → framework fold-back input
│   └── <date>-<topic>.md                  # filed by adopters as observed; cleared at fold-back
│
└── archive/
    ├── 2026-06-06-v3.2-snapshot.md        # v3.2 archive preserved
    └── 2026-06-06-v4-skeleton.md          # v4 Checkpoint 1 skeleton preserved
```

---

## §7 — Self-governance properties (NEW — Checkpoint 1 #6 first half)

The framework MUST prevent the doc-bloat / context-bloat / governance-drift that v3.2 worried about. v4 splits self-governance into **hard requirements** (framework integrity depends on them) and **suggested defaults** (good starting points; adopters override with rationale).

### §7.0 Hard requirements vs suggested defaults (NEW per Checkpoint 2)

**Hard requirements** (cannot be overridden — framework breaks if violated):
- Constitution §1.7 forbidden list (incl. v4 additions §1.7-A through §1.7-D)
- §3.3 5-role boundary invariants (no self-grading; Acceptance spawn isolation; Code-Reviewer ≠ Acceptance lens; Research-Acceptance contract symmetry)
- §4.2.3 MANDATORY_CHECKPOINTS — 8 checkpoints if Δ-18 orchestrator adopted (charter can ADD, never REMOVE)
- §3.5 Acceptance judge calibration — if Acceptance enabled in `fully_autonomous_within_budget` mode (uncalibrated → automatic degradation, not optional)

**Suggested defaults** (framework provides good starting points; adopter may override with documented rationale in `docs/current/adoption-state.md`):
- All `size_target` / `cell_size_target` / `split_trigger` numerical thresholds (§7.1-§7.5)
- Fold-back cadence triggers (5 adoptions / 6 months / critical-pattern thresholds — §8.2)
- Calibration thresholds (agreement ≥ 0.9, flip ≤ 0.1) — defaults; adopter may tighten or loosen for their context with rationale
- Suite manifest format choice (markdown vs yaml)
- Compact prompt `context_budget.target_tokens` numerical values
- Per-Δ scope of work tier placement (T0 vs T1 vs T2 vs T3) where the Δ is recommendation-tier
- Autonomy level naming and granularity (framework offers 3 levels; adopter may add intermediate levels)

**How to override a default**:
1. Adopter documents the divergence in `docs/current/adoption-state.md` (§8.4 schema) — the relevant Δ row gets `status: divergent` + a `rationale` field explaining why
2. Continue using the divergent value; no framework rejection
3. At fold-back cadence, framework maintainer reviews divergences:
   - Many same-direction divergences = default itself is wrong; revise in next framework release
   - Idiosyncratic divergences = stay adopter-specific; no framework change

**Why this split exists** (Checkpoint 2 rationale): framework that over-constrains via hard gates blocks adopters from customizing per application. Different adopters have different scales, team sizes, project domains. Framework's job is to provide a **good starting point** + leave room for **per-application customization**. The framework is opinionated where opinions are load-bearing (§1.7 forbidden, role boundaries, mandatory checkpoints, calibration for autonomous judges) and accommodating where defaults are just initial guesses.

The mechanisms below are STRUCTURAL — they provide the **front-matter fields**, **template scaffolding**, and **review prompts** that hold the discipline. They do NOT enforce specific numerical values; those are suggested.

### §7.1 Doc-responsibility matrix size_target + split_trigger (Δ-10 extended)

Every doc in `aidazi/process/`, `aidazi/templates/`, `aidazi/role-cards/` carries front-matter:

```yaml
load_discipline: always-load | on-demand | by-role
size_target: <KB>
split_trigger: <description-of-when-to-split>
cell_size_target: <chars; for table-cell docs like handoff §0>  # NEW v4
```

When a doc exceeds `size_target`, split_trigger fires. Reviewer (Codex) is briefed to flag bloat as a PR finding. This is mechanical at-the-PR-boundary, not periodic cleanup.

### §7.2 Handoff §0 cell-size guidance (csagent drift evidence; SUGGESTED per §7.0, not hard gate)

The csagent scan revealed `docs/10-handoff.md` §0 grew to multi-thousand-char paragraphs INSIDE table cells, eroding cold-start readability. v4 **suggests** as a starting point (per §7.0 — adopters may override with rationale in adoption-state.md):

- `cell_size_target: 500` chars per §0 cell (**suggested** soft target; adopters with denser projects may raise to 800-1000 with documented rationale)
- If §0 cell exceeds adopter's chosen target, point to §1 narrative for detail
- Bloated cells beyond chosen target = R-item **candidate** for next sprint (NOT auto-rejected; adopter judges)

**Why this is suggested, not hard**: cell-size needs vary by adopter:
- Single-person hobby project: cells can stay terse (500 may even be high)
- Multi-team production project: cells naturally carry more context per row (1000+ may be necessary)
- Very mature project with rich state: per-cell soft cap might not be the right discipline at all; per-row might work better

**What the framework provides structurally**:
- Front-matter `cell_size_target` field exists in `aidazi/templates/handoff-template.md` (the structural prompt)
- Default value is 500 chars (the suggested starting point)
- Adopter overrides the default by setting their own value + documenting rationale in adoption-state.md

The csagent drift evidence supports HAVING the discipline of a soft cap; the specific number is per-project judgement. Framework does NOT enforce 500 as a hard limit.

### §7.3 Action_bank live + archive split (Δ-12 carried)

- Live `action_bank.md` carries OPEN items only. Soft size budget: 160 KB target; if exceeded → forced sweep.
- `action_bank_archive.md` (append-only) carries closed items in §A sprint / §B milestone / §C R-item sections.
- Sweep is MANDATORY at milestone close (close_taxonomy_C_or_D MANDATORY_CHECKPOINT covers this).
- Cross-links use stable IDs (`R-citation-display-token-url-preferred`), NOT `[[wiki-style]]` (csagent confirmed `[[name]]` discipline never landed).

### §7.4 Live vs intermediate doc lifecycle (Δ-4 carried)

Front-matter `doc_category: live | intermediate`:
- `live` → has `last_reviewed`, cadence, source_of_truth → must be kept current
- `intermediate` → frozen at creation; named with sprint ID; modifications only for typos

Prevents the "design doc → coding agent → stale doc unchanged for half a year" failure mode csagent identified at Δ-4 origin.

### §7.5 Compact prompt artifact size discipline (Δ-5 + Δ-9 carried)

Every `compact/sprint-NNN-dev-prompt.md` / `compact/M<N>-review-prompt.md` MUST have:
```yaml
context_budget:
  target_tokens: <number>
  load_list: [<files-must-load>]
  do_not_load: [<files-excluded>]
self_contained: true
```

If self_contained=false declared, prompt is rejected at orchestrator preflight (or by human reviewer in manual mode). This is the §1.4-i / Δ-5 efficiency clause turned into a build-time check.

### §7.6 Lessons-learned doc retention

`aidazi/lessons/` accumulates between fold-back sub-sprints. At each fold-back:
- Lessons that triggered a Δ revision → archived (link from Δ doc to lesson)
- Lessons not actioned → kept for next fold-back review
- Lessons explicitly rejected → moved to `aidazi/archive/rejected-lessons/<date>-<topic>.md`

Lesson docs themselves are `intermediate` per Δ-4 — frozen at creation, not edited.

### §7.7 Self-governance review cadence

Self-governance is itself reviewed:
- Every 5 adoptions complete OR every 6 months: framework maintainer runs a fold-back sub-sprint (§8.2).
- The fold-back sub-sprint reviews bloat metrics:
  - Avg doc size across aidazi/process/ (should not grow > 10% per fold-back interval)
  - Adopter-reported context-budget violations (lessons/)
  - Acceptance / Reviewer prompt sizes (should stay within target_tokens)

---

## §8 — Fold-back protocol (NEW — Checkpoint 1 #6 second half + #4)

### §8.1 Two directions

**Adopter → Framework** (lessons-learned, single direction):
- Adopters file lessons in `aidazi/lessons/<date>-<topic>.md` as they observe them.
- Lessons are PROPOSALS not auto-merged.
- Periodic fold-back review by framework maintainer extracts patterns and promotes to Δ revisions.

**Framework → Adopter** (release-based, single direction):
- Framework cuts versioned releases (v4.0.0 → v4.0.1 → v4.1.0 → v5.0.0).
- Adopters consume on their own cadence (no auto-update).
- When adopter consumes a new framework version, they update `adoption-state.md` to reflect any newly at-spec / partial / divergent Δs.

Neither direction is automatic. Both are human-mediated.

### §8.2 Fold-back sub-sprint cadence

Framework maintainer (= you, in this workstream) holds a **fold-back sub-sprint** when any of three triggers fires:

1. **Adoption count trigger**: 5 fresh adoptions complete since last fold-back.
2. **Time trigger**: 6 months since last fold-back.
3. **Critical-pattern trigger**: ≥3 adopters file lessons-learned docs touching the same Δ/section, OR ≥1 lesson categorized "critical" (e.g., security, correctness, framework-breaks-adopter).

### §8.3 Fold-back sub-sprint output

Each fold-back sub-sprint produces:
- One or more Δ revision PRs to aidazi/
- A `framework-release-notes/<version>.md` summarizing changes per Δ
- A `framework-release-notes/<version>-migration-guide.md` listing what adopters need to update
- Optional: examples/ snapshot refresh if csagent or hermes drift becomes load-bearing

### §8.4 Adopter-state ledger schema (`adoption-state.md`)

Adopter root contains `docs/current/adoption-state.md`:

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
| Δ-18 Orchestrator | T1 (Type A) | divergent | adopter supports 2 autonomy levels, framework defines 3 | OQ-<id> |
| ... | | | | |

# Drift reasons (for `divergent` rows)

- Δ-18 autonomy.level: adopter intentionally omits `fully_autonomous_within_budget`
  because <justification>. Will revisit if framework promotes a v5 with stronger guarantees.

# Lessons proposed for upstream fold-back

| Date | Topic | Lesson file | Status |
|---|---|---|---|
| 2026-06-15 | F5 cost-asymmetry on Codex subscription | aidazi/lessons/2026-06-15-codex-cost-asymmetry.md | proposed |
```

Status enum: `at-spec | partial | divergent | not-applicable | superseded-by-framework`.

### §8.5 Lessons-learned template

`aidazi/templates/lessons-learned-template.md`:

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

### §8.6 Fold-back anti-patterns

- Framework auto-updating adopter repos via submodule (no — adopters consume on their cadence)
- Adopter auto-syncing framework changes mid-milestone (no — wait for sub-sprint boundary)
- Lessons-learned doc updated after filing (no — `intermediate` per Δ-4; file a new lesson, don't edit old)
- Fold-back sub-sprint without an adoption-state.md review (no — must check all adopters' state)
- Framework v5 dropping a Δ without migration guide (no — every release notes details migrations)

---

## §9 — Application Guide sub-doc sketches

P3 produces these as embedded sketches; P4 extracts each to its own file in `aidazi/application-guide/`.

### §9.1 `00-overview.md` sketch

```
# Application Guide Overview

This guide helps you land the aidazi framework into a new application.

## Two paths

1. **Greenfield** — empty repo or no agent yet. Inherit framework + fill in domain values.
   → see 01-greenfield-fast-path.md

2. **Brownfield** — existing app with own norms. Human owner decides what to inherit.
   → see 02-brownfield-manual.md

## After bootstrap

Walk the Phase 1-5 funnel:
- Phase 1 inputs → 03-phase-1-inputs.md
- Phase 2 domain → 04-phase-2-domain.md
- Phase 3 tech design → 05-phase-3-tech-design.md
- Phase 4 modules → 06-phase-4-modules.md
- Phase 5 eval → 07-phase-5-eval.md

Then bootstrap iteration loop:
- 08-iteration-bootstrap.md

(Optional) bootstrap orchestrator:
- 09-orchestrator-bootstrap.md

## Profile choice

If unsure A vs B vs C vs A+B hybrid:
- 10-profile-decision-tree.md

## Tracking your adoption

- 11-adoption-state-ledger-template.md
```

### §9.2 `08-iteration-bootstrap.md` sketch

```
# Iteration loop bootstrap

After Phase 1-5 instantiation:

STEP 1. Author AGENTS.md at adopter root
   • Use framework/AGENTS.md as template
   • @-include framework/governance/{doc_governance, context_briefing, constitution}.md
   • Add @-includes for adopter-specific docs/current/{domain_taxonomy, runtime_invariants, eval_acceptance_bars}.md
   • Add the 5-role registry table (adapted from framework template)

STEP 2. Author first research-brief
   • Authoring agent: Research Agent (paste activation from framework/role-cards/research-agent.md)
   • Output: docs/research-briefs/<id>.md
   • Required: closure_contract paragraph (positive shape + anti-pattern + anchor phrases)
   • Customer signs → gate 1

STEP 3. Author first milestone_objective + sprint_objective
   • Deliver Agent (paste activation)
   • From research brief, decompose into milestone
   • Pick first sub-sprint scope
   • Author compact/sprint-001-dev-prompt.md

STEP 4. First Dev → Reviewer cycle
   • Dev session paste (config charter.tooling.dev.agent_kind to your choice)
   • Tests + handoff §1-§11
   • Code Reviewer session paste (charter.tooling.review.agent_kind)
   • codex-findings.md verdict

STEP 5. First close
   • Deliver + human close conversation per deliver_close_taxonomy.md
   • If milestone scope → run Acceptance (charter.acceptance.enabled)
   • Acceptance verdict pass/fix_required/needs_human
   • If fix_required → human-confirm checkpoint → route

STEP 6. Bootstrap action_bank + handoff
   • action_bank.md with §1 status + §A/B/C placeholders
   • handoff.md §0 cold-start table + §1 narrative + §2 archive index
```

### §9.3 `09-orchestrator-bootstrap.md` sketch

```
# Orchestrator bootstrap (optional; Type A or A+B)

STEP 1. Decide autonomy level
   human_in_the_loop / human_on_the_loop / fully_autonomous_within_budget

STEP 2. Author mission charter YAML
   Use framework/templates/mission-charter.yaml as starting point
   T0 base + appropriate T1 profile overlay

STEP 3. Acceptance calibration (if charter.acceptance.enabled)
   • Author labeled set: aidazi/calibration/labeled_acceptance_cases/manifest.json
   • Per case: (trace, expected_verdict ∈ PASS/FAIL)
   • Run orchestrator's calibrate command twice
   • Verify agreement ≥ 0.9 AND flip ≤ 0.1
   • Mark charter.acceptance.judge_calibration.status = calibrated

STEP 4. Author calibration set continuously
   • Every milestone close, add 1-2 new labeled cases reflecting recent acceptance verdicts
   • Re-calibrate when switching model

STEP 5. First orchestrator run
   • orchestrator dispatch <sprint-id>
   • orchestrator run --max-steps 50
   • Observe checkpoints fire; resolve via filesystem inbox
```

(Other sub-docs follow similar sketch shapes; P4 fully fleshes them out.)

---

## §10 — 4-column comparison appendix

Per Δ, the comparison of (v3.2 claim) vs (aidazi as currently implemented) vs (csagent actual practice) vs (hermes actual practice). This is the receipts table for "did v4 actually extract from code".

| Δ | v3.2 archive claim | aidazi/ as-of 2026-06-06 commit `1b93e07` | csagent actual (docs + code) | hermes actual (docs + code) |
|---|---|---|---|---|
| Δ-1 Anatomy | 3 orthogonal dims; A/B/C/D × T0/T1/T2/T3 matrix | governance/constitution.md anatomy section exists | docs taxonomy implicitly follows this | submodule pinned to aidazi v0.1.0 |
| Δ-2 Domain discovery | D1/D2/D3 process doc | process/domain-discovery-process.md (4.7K stub) | Phase 1 solution_input_pack.md is the actual practice | docs/system-arch.md is the actual practice |
| Δ-3 Decision catalog | 8 decisions table + S2-required event binding | process/tech-architecture-decision-catalog.md (2.9K) | phase0 §0.3 inheritance table + §0.6 deviation log are richer | charter.py + proposals/aidazi-workflow-governance-variant.md add workflow_definition layer |
| Δ-4 Doc lifecycle | live vs intermediate front-matter | process/doc-lifecycle-rules.md (2.7K) | docs use doc_category implicitly | inherits aidazi |
| Δ-5 Context efficiency | sufficient AND efficient + context_budget | process/context-passing-efficiency.md (2.7K) | prompt-artifact-rules.md §9 fully implemented | inherits aidazi |
| Δ-6 Type A runtime skeleton | intent gate + multi-phase pipeline | process/typeA-runtime-architecture-skeleton.md (4.5K) | Phase 3 detailed tech design has the rich version; eval skill_procedure_check.py implements 6-primitive trace_check DSL | n/a (Type B-leaning) |
| Δ-7 Worked example | examples/csagent-reference/ skeleton | examples/ exists; csagent-reference snapshot pending | foundational/ + sprints/ are the live worked example | docs/ is the worked example |
| Δ-9 OBS/autoloop role-split | OBS ≠ R-item; two-layer triage | process/post-deployment-iteration.md (3.6K) | action_bank.md actively practices OBS-vs-R-item (M-Auto-6: 7 OBS / 8 R-items) | partial — `action_bank.md` 96.9K with R-items only, no OBS distinction yet |
| Δ-10 Doc-responsibility-matrix | 8 fields | process/doc-responsibility-matrix.md (3.3K) | docs/current/ docs have implicit matrix; not fully populated | partial |
| Δ-11 Staging roadmap | S0~S6 + S1.5/S2.5/S5/S3.5 | process/capability-staging-roadmap.md (4.1K) | sprint cadence has practiced S0-S5; S2.5 + S5 still being learned (M-Auto-6 acceptance calibration debt) | bootstrap stage; in S0-S1 transition |
| Δ-12 Artifact taxonomy | 11 artifacts | process/artifact-taxonomy.md (4.7K) | 14+ artifacts actual (incl deliver_close_taxonomy.md, research-briefs/, acceptance-reports/ implicit) | hermes-specific add: SOP / charter / labeled_acceptance_cases |
| Δ-13 Stage-stable softened | heuristic not gate | process/stage-stable-heuristic.md (2.8K) | M2 pivot 2026-05-17 supports softening | n/a yet |
| Δ-14 Profile-aware maturity | A/B/C necessary sets | process/profile-aware-maturity.md (3.3K) | A track lived fully | A+B hybrid evidenced in docs/aidazi-integration-plan.md §一 |
| Δ-15 Agent design elicitation | 6 Qs + 4 inventories + 0→1 industry research | process/agent-design-elicitation.md (4.7K) | BRD + PRD process maps to this | proposals/orchestration-protocol-draft.md (no explicit Δ-15 pass yet) |
| Δ-16 Agent creation prereqs | 7 categories | process/agent-creation-prerequisites.md (4.7K) | 07-engineering-constraints.md + foundational input docs match | docs/system-arch.md as input |
| Δ-17 Common detours Type A | P1-P4 patterns | process/common-detours-and-warnings-typeA.md (8.0K) | sprint history substantiates P1-P4 | n/a yet (different stage) |
| Δ-17-B Type B | EMPTY placeholder | process/common-detours-and-warnings-typeB.md (590B) | n/a | early signals: OCR + verification gate are P1/P2 candidates |
| Δ-17-C Type C | EMPTY placeholder | process/common-detours-and-warnings-typeC.md (596B) | n/a | n/a |
| **Δ-18 Orchestrator** (NEW) | n/a (v3.2 didn't have this) | **MISSING from aidazi/** | n/a — csagent is purely human-paste | **2815 lines production code** + 4 proposal docs ready for fold-back |

**The takeaway**: v3.2 archive captured most of csagent's discipline (Δ-1~Δ-17) but missed:
1. **Δ-18 entirely** — biggest gap; the orchestrator pattern hermes built doesn't exist in aidazi/process/
2. **Acceptance positioning** — the 5th role exists in aidazi/role-cards/acceptance-agent.md but as Reviewer→Customer pre-release QA, not Research-peer
3. **deliver_close_taxonomy** — csagent's Q2-2026 addition not yet in aidazi
4. **Application Guide** — v3.2 mentioned worked examples; aidazi has examples/ stubs; full Application Guide structure doesn't exist
5. **Self-governance + fold-back** — v3.2 §6 mentioned bidirectional iteration; neither is operationalized in aidazi/

v4 closes all 5 gaps.

---

## §11 — Open questions carry-forward

These persist past Checkpoint 2; will be resolved at P4 or first adoption.

1. **OQ-V4-001**: Δ-18 Type B (T1' SOP variant) full spec — deferred until hermes completes first SOP milestone end-to-end (Checkpoint 1 #4).
2. **OQ-V4-002**: examples/hermes-reference/ snapshot date — when to freeze; suggest after hermes reaches its first milestone close.
3. **OQ-V4-003**: examples/fortunes-reference-placeholder/ population trigger — fortunes hasn't been scanned; defer.
4. **OQ-V4-004**: framework versioning policy — semver suggested (v4.0.0 → v4.0.1 patch / v4.1.0 minor / v5.0.0 major). Confirm at first release.
5. **OQ-V4-005**: lessons/ submission mechanism — slash-command? PR to aidazi/? direct file commit? — TBD at first adopter request.
6. **OQ-V4-006**: adoption-state.md review cadence — proposed "per milestone close" — confirm at first adopter use.
7. **OQ-V4-007**: §3.5 acceptance calibration when running fully_autonomous_within_budget on a NEW judge model — re-calibration cost (re-run labeled set) might be substantial. Should framework provide a "calibration cache" / labeled-set portability story? Defer to first multi-model adopter.
8. **OQ-V4-008**: cell_size_target for handoff §0 cells — proposed 500 chars; csagent practice shows cells naturally grow. May need 800 or 1000; revisit after one fold-back cycle.

---

## §12 — Checkpoint 2 — what I want from you

This is the full v4 plan. Before P4 (aidazi reconciliation list), please confirm:

1. **§3 5-role chain final** — ASCII + table + boundary invariants + acceptance fix_required → human-confirm → deliver flow. Anything still off?
2. **§4.1 Δ reconciliation final** — all 18 Δs labeled keep / extend / NEW correctly?
3. **§4.2 Δ-18 full spec final** — charter schema (T0 base + T1 profile) + 8 MANDATORY_CHECKPOINTS + state machine + spawn function table + anti-patterns. Anything to add/remove?
4. **§5 Application Guide reframed** — greenfield-fast + brownfield-manual + Phase 1-5 funnel + sub-doc inventory. Conceptual structure OK?
5. **§6 doc-tree final** — every file path + new vs existing. Anything missing or wrong location?
6. **§7 self-governance properties** — 6 mechanisms enough to address doc-bloat / context-bloat concerns? Anything to add?
7. **§8 fold-back protocol** — adopter-state ledger + lessons-learned + sub-sprint cadence. Anything to adjust?
8. **§10 4-column appendix** — the receipts table. Any cells you disagree with (e.g., "aidazi already has Δ-18 partially" or "csagent didn't actually practice Δ-9 the way I claimed")?

Approval → P4 starts: I produce `compact/aidazi-v4-reconciliation.md` listing the files in aidazi/ to rewrite vs keep vs mark superseded, with diffs as needed. I do NOT edit aidazi/ in P4 — only the reconciliation list.
