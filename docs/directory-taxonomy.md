---
title: Directory taxonomy — where does this content go?
doc_tier: application-guide
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 20KB
split_trigger: if §3 per-directory rules grow past 8KB, split to docs/directory-taxonomy-rules.md
notes: >
  Adopter-facing fast lookup: when you've just written / observed something
  and need to decide its primary destination, walk the §1 decision tree.
  §2 maps observable input shapes to target dirs. §3 lists per-directory
  authoring rules. §4 covers the "agent discovered delivery-vs-promise gap"
  case specifically. §5 distinguishes diagnostics/ from
  diagnostics/failure-briefs/. Lives in docs/ (not process/) per v4 —
  adopters reach for this first.
---

# Directory taxonomy

Every doc directory in the adopter repo has a **single primary author**, a **specific trigger**, a **specific content type**, and a **specific promotion path**. v4 makes the split explicit.

This is the adopter-facing fast-lookup doc. Read it when you're about to write something and aren't sure where it goes.

## §1 Decision tree — "where does this content go?"

When you've just written / observed something and need to decide its primary destination, walk these questions in order. First match decides the primary file. Q5 is orthogonal and may create an additional artifact alongside Q4's destination.

```
Q1. Is this a FORMAL Customer need (something Customer would sign off on)?
    YES → docs/research-briefs/<id>.md             (Customer signs gate 1)
    NO  → Q2

Q2. Is this CASUAL exploration (human ↔ coding-agent ad-hoc chat)?
    YES → docs/proposals/<id>.md                   (informal; may later promote)
    NO  → Q3

Q3. Did an AGENT discover this mid-sprint
    (Dev / Code Reviewer / Deliver during investigation)?
    YES → docs/diagnostics/<id>.md                 (tech-internal root-cause notes)
    NO  → Q4

Q4. Is this a REPEATED (n≥2) or SEVERE bad case
    that should be formally documented?
    YES → docs/diagnostics/failure-briefs/<id>.md  (joint human + Deliver,
                                                    6-field formal template)
    NO  → docs/action_bank.md as OBS-item          (Δ-9 single observation;
                                                    matures to R-item if pattern
                                                    emerges later)

Q5. (orthogonal — applies if Q4=YES) Can this be REPRODUCED as a runnable
    regression test?
    YES → ALSO file eval/bad_cases/<id>.yaml       (CaseSpec with
                                                    closure_criterion;
                                                    Deliver curates / human
                                                    writes closure_criterion)
    NO  → failure-brief alone; runtime regression deferred
```

**Output-side directories are NOT in this tree** — you don't *choose* to put things here; agents write results here as their work product:
- `docs/acceptance-reports/<scope>-acceptance-report.md` — Acceptance Agent writes.
- `docs/codex-findings.md` — Code Reviewer Agent writes.
- `docs/current/adoption-state.md` — human owner writes only when overriding framework defaults.

**Pre-existing dirs not produced by this tree** (you didn't author them; the framework provides templates):
- `docs/current/` — domain context docs (domain_taxonomy, runtime_invariants, eval_acceptance_bars, agent_context_guide, adoption-state).
- `docs/foundational/` — Phase 1-5 source-of-truth docs (business-need, product-service-design, technical-plan, coding-packet, eval-design).
- `docs/sprints/<sprint-id>/` — sprint archive after sprint close.
- `compact/` — generated per-sprint prompt artifacts.
- `skills/` — role-skill packages (Agent Skills standard; one dir per skill with `SKILL.md`). Framework-side `aidazi/skills/` ships exemplars; adopters MAY keep their own `skills/` for skills mounted via `charter.tooling.<role>.skills`. Authoring rules: `process/role-skill-model.md` §6. Role skills are capability packaging, NOT Δ-12 artifacts.

## §2 Per-directory authoring rules

| Directory | Primary author | Trigger | Content type | Lifecycle | Promotes to | Customer interaction |
|---|---|---|---|---|---|---|
| `docs/research-briefs/<id>.md` | **Research Agent** (formal mode) | Customer formally asks "what should we build" OR Path-2 failure-brief matures | **Formal need spec**: closure_contract (mandatory) + scope IN/OUT + anti-goal + KPI + related R-items | live until milestone close; archive to `docs/sprints/` after | terminal for Path 1; consumed by Deliver + Acceptance | **Customer signs gate 1** |
| `docs/proposals/<id>.md` | Research Agent (exploratory) OR ad-hoc coding-agent session | Human casually opens a session: "how would we approach X?" | **Design exploration**: lower formality; NO closure_contract required; may sketch tradeoffs / candidate approaches | intermediate (Δ-4); frozen at creation | may promote to research-brief if human selects + Research Agent re-runs formally | Customer reads as informational; does NOT sign |
| `docs/diagnostics/<id>.md` | Dev / Code Reviewer / Deliver Agent (during sprint work) | Agent discovers something mid-sprint (mid-PR, mid-review, mid-investigation) | **Root-cause analysis**: "why does X behave this way?"; cites code paths + traces | intermediate (Δ-4); referenced from sprint-handoff §9 | may promote to failure-brief (if pattern n≥2) or R-item in action_bank | Customer typically does NOT read; tech-internal observation |
| `docs/diagnostics/failure-briefs/<id>.md` | **Joint human + Deliver Agent** | Bad-case observed + triage decides it's load-bearing (n≥2 OR severe) | **Failure shape report** — 6-field template per Δ-2: (1) what happened, (2) what should good agent have done, (3) why does this matter, (4) one-off-or-pattern, (5) which §3 layer, (6) what NOT to do | intermediate per sprint | Path 2 Research Agent input → produces research-brief → back into normal flow | Customer may co-author "what should good agent have done" field |
| `eval/bad_cases/<id>.yaml` (or equivalent suite dir) | **Joint** (Deliver Agent curates structure; human authors closure_criterion) | Failure-brief promoted to **reproducible runtime test** | **CaseSpec yaml** with closure_criterion per Constitution §1.7-B (positive shape + anti-pattern + anchor phrases; NOT keyword match) | live regression suite until tier-downgraded to closed-as-regression-guard or archived | terminal for regression suite | n/a (runtime artifact for Acceptance Agent + Code Reviewer) |
| `docs/acceptance-reports/<scope>-acceptance-report.md` | **Acceptance Agent** | Acceptance run at milestone close / release cut / sub-sprint close (per charter) | **Verdict + per-criterion evidence + gap brief if fail + suggested route** {deliver_fix_iteration \| re_acceptance_after_evidence \| research_contract_revision} | intermediate per scope; archived to milestone close package | gap brief consumed by Deliver (Path 3 fix-iteration) **after human-confirm checkpoint** | **Customer reads gate 2; signs ship/no-ship** |
| `docs/codex-findings.md` | **Code Reviewer Agent** | Review run (sub-sprint close, §4.3 trigger, milestone close) | **Anti-hardcode kernel results + correctness findings**; 4-line header verdict | intermediate per sprint/milestone; archived at close | consumed by Deliver at close conversation per `templates/deliver-close-taxonomy.md` | Customer typically does NOT read; tech-side artifact |
| `docs/action_bank.md` (live) | **Deliver Agent** maintains; Dev / Reviewer surface items | Sprint / milestone observation; ongoing backlog | **R-items + OBS-items + open Qs** ledger | live; soft size cap (suggested per `process/self-governance.md` §7.3) | sweep to `action_bank_archive.md` at milestone close | n/a |
| `docs/current/adoption-state.md` | **Human owner** (adopter side) | Adopter overrides a framework default OR observes a divergence | **Per-Δ status table** + drift rationale + lessons-to-propose | live; review per milestone close | feeds `aidazi/lessons/<date>-<topic>.md` for fold-back | n/a (adopter-internal) |
| `docs/checkpoints/<timestamp>__<event>__<scope>.md` | **Orchestrator emits**; human resolves `decision:` field | Orchestrator hits a MANDATORY_CHECKPOINT (per `process/delivery-loop.md` §4.2.3) | **Checkpoint inbox**: context + options + decision field for human | intermediate; one per checkpoint event | terminal (orchestrator picks up decision and advances) | Customer (or delegated human) writes decision |

## §3 Authoring authority by input modality

The user's confusion typically centers on: where does a particular input land? This table maps observable input shapes to their target dir.

| Observable input shape | Who provides | Lands in | Reason |
|---|---|---|---|
| Customer formally requests something | Customer prompts Research Agent (paste activation) | `docs/research-briefs/<id>.md` | Gate 1 — Customer signs; closure_contract required |
| Customer casually asks "how would you approach X?" | Customer chats with any coding-agent ad-hoc | `docs/proposals/<id>.md` | Lower formality; may later promote |
| Customer / colleague reports a single failure | Verbal / written observation | first → human + Deliver triage → if load-bearing → `docs/diagnostics/failure-briefs/<id>.md`; if reproducible → `eval/bad_cases/<id>.yaml` | Triage step is **mandatory** — not every observation becomes a brief; n≥2 threshold for pattern |
| Pattern of N≥2 similar failures | Multiple instances collected over time | `docs/diagnostics/failure-briefs/<id>.md` (formal); then Path 2 Research Agent → `docs/research-briefs/<id>.md` | Pattern threshold prevents one-off premature R-item creation |
| Agent finds something during sprint work | Dev / Reviewer / Deliver during investigation | `docs/diagnostics/<id>.md` | NOT a Customer need; tech-internal observation |
| Agent finds delivery-vs-promise gap at milestone close | Acceptance Agent verdict = `fix_required` | `docs/acceptance-reports/<scope>-acceptance-report.md` (with gap brief section) | The formal "delivered ≠ promised" detector |
| Reviewer finds anti-hardcode violation | Code Reviewer Agent verdict | `docs/codex-findings.md` | Code-side observation, not need-side |
| Adopter intentionally diverges from framework default | Human owner | `docs/current/adoption-state.md` row marked `status: divergent` + rationale | Per Constitution §7.0 — framework default override path |
| Maintainer wants to give framework feedback | Adopter human | `aidazi/lessons/<date>-<topic>.md` | Per `process/fold-back-protocol.md` §5 |

## §4 Who writes where — quick reference

**Human writes directly** (no agent intermediary):
- Customer prompts feeding Research / Acceptance (raw input; not a stored doc by themselves).
- `docs/checkpoints/*.md` `decision:` field (human resolves orchestrator checkpoints).
- `docs/diagnostics/failure-briefs/<id>.md` (joint with Deliver; human labels expected behavior + Deliver hypothesizes layer).
- `eval/bad_cases/<id>.yaml` `closure_criterion` (joint with Deliver; human writes customer-perspective end-state).
- `docs/research-briefs/<id>.md` `customer_signed:` front-matter (Customer sign-off, gate 1).
- `docs/current/adoption-state.md` (when overriding framework defaults, human authors rationale).

**Agent writes** (per §2 table above):
- All other docs in the taxonomy.

**Joint authoring** (cannot be auto-merged):
- failure-briefs (6-field template; human + Deliver each own specific fields).
- `bad_cases` CaseSpec (Deliver curates structure; human authors closure_criterion).
- close decisions per `templates/deliver-close-taxonomy.md` (Deliver proposes verdict A/B/C/D; human signs).

## §5 "Agent discovered delivery-vs-promise gap" — the specific question

Scenario: an agent (typically Dev mid-sprint OR Code Reviewer mid-review OR Acceptance at milestone close) finds the implementation has drifted from the original research-brief's closure_contract.

**Two distinct lifecycle moments** map to two distinct dirs:

### §5.1 Mid-sprint discovery (Dev or Reviewer notices during work)

- **Lands in**: `docs/diagnostics/<id>.md` describing the gap, cross-linking to the affected `research-briefs/<id>.md` and the specific code paths.
- **Then escalates to one of**:
  - Deliver Agent for in-flight scope adjustment — BUT `process/milestone-framework.md` forbids mid-milestone scope expansion; usually defer.
  - New R-item in `docs/action_bank.md` for next sprint/milestone (most common path).

### §5.2 End-of-milestone discovery (Acceptance Agent at milestone close)

- **Lands in**: `docs/acceptance-reports/<scope>-acceptance-report.md` with structured gap brief.
- **Then routes through human-confirm checkpoint** (Constitution §3.5) → if confirmed → Deliver Agent picks up gap → fix-iteration sub-sprint authored.

### §5.3 Distinction

- `diagnostics/` is **mid-flight observation in code-perspective**.
- `acceptance-reports/` is **end-of-milestone verdict in contract-perspective**.

The same kind of failure can be observed in both; they don't overlap because they live at different lifecycle moments + use different lenses + route differently.

## §6 diagnostics/ vs diagnostics/failure-briefs/ — distinction and relationship

These two often get conflated. Clean split:

| Aspect | `docs/diagnostics/` | `docs/diagnostics/failure-briefs/` |
|---|---|---|
| **Author** | Dev / Code Reviewer / Deliver Agent during sprint work | **Joint human + Deliver Agent** (after triage) |
| **Trigger** | Mid-sprint discovery (debugging, root-causing, investigation) | Bad-case observed + triage decides load-bearing (n≥2 OR severe) |
| **Content lens** | **Tech-internal**: "why does X behave this way?" — code paths + traces + log evidence | **Customer-facing**: 6-field formal template (what happened / what good agent should have done / why does this matter / one-off-or-pattern / which §3 layer / what NOT to do) |
| **Tone** | Technical investigation notes | Customer / business perspective |
| **Formality** | Low — agent writes as it discovers | High — joint authoring with mandatory 6 fields |
| **Promotes to** | May promote to failure-brief if pattern matures (n≥2 similar) | Promotes to research-brief (Path 2 input → Research Agent formal mode) |
| **Customer reads?** | Typically NOT — tech-internal | Customer may co-author the "what good agent should have done" field |
| **Filesystem location** | `docs/diagnostics/<id>.md` | `docs/diagnostics/failure-briefs/<id>.md` — sub-dir is **deliberate** |

**Why failure-briefs/ lives UNDER diagnostics/** (not as a separate top-level dir): failure-briefs are the **structural promotion** of a diagnostic when load-bearing. The sub-dir hierarchy makes "this brief originated from diagnostic-level investigation" visible at the filesystem level.

### §6.1 The three relationship patterns

1. **Diagnostic → failure-brief promotion**: a diagnostic notes a single tech finding. Over 2+ similar diagnostics, human + Deliver triage; if load-bearing, file a failure-brief that **cites the contributing diagnostics**. The diagnostics stay (raw analysis); the failure-brief is the consolidated formal contract for Path 2.

2. **Failure-brief → new diagnostics back-reference**: filing a failure-brief typically triggers further investigation. New diagnostics produced during that investigation **cite the failure-brief id**. Cross-link both ways.

3. **Same finding, two lenses — never duplicated content**: if you have BOTH a diagnostic and a failure-brief on the same finding, they describe DIFFERENT lenses (tech-internal root-cause vs customer-facing failure shape). NEVER edit the diagnostic to match the failure-brief's tone; they serve different lifecycles + different consumers.

### §6.2 Quick disambiguation when authoring

- "I'm an agent describing root-cause in code terms" → diagnostic.
- "I'm helping the human file a formal failure shape with customer-perspective expected-behavior" → failure-brief.
- "I'm not sure yet whether this is load-bearing" → diagnostic first; promote later if pattern emerges.
- "I want to add this to the next sprint's backlog (not formal yet)" → action_bank OBS-item.

## §7 Editing this doc

Application-guide tier; edits land at fold-back sub-sprint cadence per Constitution §8.

When adopter feedback (via `lessons/`) surfaces a new directory pattern or a recurring confusion about where something goes, the next fold-back may:
- Add a new directory row to §2.
- Extend the §1 decision tree.
- Add a row to §3's input-modality table.

The "output-side directories" note + "pre-existing dirs" note in §1 are deliberately separate from the decision tree — the decision tree is for AUTHORING decisions; those notes are for context.

---

End of Directory taxonomy.
