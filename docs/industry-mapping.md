---
title: Industry mapping — aidazi vs other agent frameworks
doc_tier: application-guide
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 20KB
split_trigger: if the per-framework mapping (§3) grows past 8KB, split each framework to its own sub-doc and keep the comparison table here
notes: >
  Translation layer for adopters arriving from another agent framework —
  BMAD, Claude Code subagents, the Agent Skills (SKILL.md) standard, LangGraph,
  AutoGen. Maps each onto the 5-role chain, shows what aidazi adds (gate
  semantics, the Code Reviewer ≠ Acceptance split, F5 evidence, calibration),
  and points to how their building blocks mount INSIDE aidazi roles via the
  role-skill model — never as new chain roles. Lands the full mapping the
  role-skill model (process/role-skill-model.md §8) points at.
---

# Industry mapping — aidazi vs other agent frameworks

If you're coming from another multi-agent or agent-skill framework, this doc is the translation layer. It maps the building blocks you already know onto aidazi's 5-role chain, and it's explicit about the one thing that's easy to miss: **aidazi roles are accountability boundaries with gate semantics, not just prompt personas.** The other frameworks give you personas and orchestration; aidazi adds *who answers for what*, *who may grade whom*, and *what evidence a verdict must rest on*.

The composition rule throughout: **mount industry building blocks INSIDE aidazi roles** (as role skills or intra-role sub-agents), never as new chain roles. The full mounting model is `process/role-skill-model.md`; this doc is the per-framework how-to.

## §1 The distinguishing axis

Most agent frameworks define **personas** (an "architect" agent, a "reviewer" agent) and **orchestration** (who runs after whom). aidazi defines those too, but its roles additionally carry:

- **A verdict schema** — Code Reviewer, Acceptance, and Deliver-close emit machine-parseable verdicts (`schemas/*.json`), so routing is deterministic, not vibes.
- **Spawn isolation** — Acceptance may not be spawned by the roles it judges (§1.7-C). No persona library enforces this; it's what keeps a verdict from being a rubber stamp.
- **A calibration gate** — an autonomous judge must pass calibration before its verdict is trusted (§3.6).
- **Execution-evidence grounding (F5)** — Acceptance judges from real execution artifacts, not code inspection; the dev sandbox stays sealed (`process/delivery-loop.md` §4.2.6).
- **Two split gates** — "built correctly?" (Code Reviewer) and "built the right thing?" (Acceptance) are *different* gates that both run.

When you read "aidazi has an Acceptance role and framework X has a QA agent," the difference is all of the above — not the name.

## §2 Comparison at a glance

| Concern | BMAD | Claude Code subagents | Agent Skills (SKILL.md) | LangGraph | AutoGen | aidazi |
|---|---|---|---|---|---|---|
| Primary unit | Named role personas | Delegated specialist personas | Capability packs | Graph nodes (state machine) | Conversable agents | 5 roles = accountability boundaries |
| Orchestration | Sequential artifact pipeline | In-session delegation | n/a (capabilities) | Explicit graph edges | Conversation/group chat | Delivery Loop (Δ-18) state machine, optional |
| Gate semantics | Role hand-off (no verdict schema) | Caller decides | n/a | Edge conditions | Termination conditions | Verdict schemas + MANDATORY_CHECKPOINTS |
| Independent QA | QA agent (no spawn isolation) | A reviewer subagent | n/a | A node | An agent | Acceptance: spawn-isolated, calibrated, peer-of-Research |
| "Right thing" vs "well built" | Merged in QA | Merged | n/a | Up to you | Up to you | **Split**: Acceptance vs Code Reviewer |
| Self-improvement loop | n/a | n/a | n/a | n/a | n/a | Auto Loop (Concept 1) distinct from Delivery Loop (Concept 2) |

aidazi is not "better at orchestration" than LangGraph or "better at conversation" than AutoGen — those are runtime engines. aidazi is a **delivery discipline** that can run on top of any of them (you can implement the Delivery Loop as a LangGraph graph, or run roles as AutoGen agents). The value it adds is the accountability structure, not the plumbing.

## §3 Per-framework mapping

### §3.1 BMAD (Analyst / PM / Architect / Scrum Master / Dev / QA)

BMAD is the closest cousin — an artifact-driven pipeline of agile personas. The mapping:

| BMAD role | aidazi home | Note |
|---|---|---|
| Analyst | **Research** slot | Market/requirements work = Δ-15 elicitation + Δ-2 domain discovery |
| PM | **Research** + **Deliver** | Need definition → Research brief; planning → Deliver |
| Architect | **Deliver** skill slot | Architecture decisions are Deliver's planning work (Δ-3), optionally assisted by an architect role skill/sub-agent — *not* a 6th chain role |
| Scrum Master (story prep) | **Deliver** | Sub-sprint decomposition + compact dev prompts |
| Dev | **Dev** | Direct match |
| QA | **split** → **Code Reviewer** (code-side) + **Acceptance** (outcome-side) | The split is aidazi's value-add; don't collapse it back into one QA agent |

The biggest translation: BMAD's Architect is a standalone role producing ADRs; in aidazi that work lives inside Deliver (with an optional architect skill), because architecture decisions have no independent verdict to carry — they're inputs to Deliver's signed plan. And BMAD's single QA becomes two gates.

### §3.2 Claude Code subagents (architect / frontend / backend / reviewer / …)

Subagent libraries (e.g., the 150+ persona collections) define specialists with a `tools` whitelist and a model choice, delegated within a session. In aidazi these mount as **role skills or intra-role sub-agents**:

- `frontend-developer`, `backend-architect`, `database-*`, `test-author` → **Dev** role skills (Dev is the primary mount point for stack specialists). They inherit Dev's sandbox transitively.
- `architect`, `system-designer` → **Deliver** skill slot (plan-draft fan-out; Deliver signs).
- `code-reviewer`, `security-auditor`, `performance-reviewer` → **Code Reviewer** review-lens skills (read-only whitelist).
- `researcher`, `market-analyst` → **Research** skill slot.

Constraint: a subagent's `tools` field must be a subset of the mounting role's whitelist (a code-writer subagent can't mount on the read-only Code Reviewer or Acceptance). And a subagent never becomes a chain role — its output is draft input to the role, which signs the artifact (`process/role-skill-model.md` §4).

### §3.3 Agent Skills — the SKILL.md open standard

The Agent Skills standard packages procedural knowledge as a directory with a `SKILL.md` (frontmatter `name` + `description`, markdown body, optional `scripts/`/`references/`/`assets/`, progressive disclosure). aidazi adopts this standard directly for **role skills**:

- A skill mounts on a role when its (experimental) `allowed-tools` fits the role's whitelist.
- The framework ships one exemplar — `skills/anti-hardcode-review-kernel/` — packaged thin over its normative source (`templates/anti-hardcode-review-kernel.md`).
- Off-the-shelf SKILL.md skills from any compliant ecosystem mount the same way; the dual-source rule keeps the framework's normative content authoritative.

This is the cleanest interop path: a SKILL.md from any of the 30+ tools that read the standard can become an aidazi role skill with no rewrite, subject to the whitelist check.

### §3.4 LangGraph

LangGraph models agent systems as explicit graphs (nodes = steps, edges = transitions over shared state). It's an orchestration *engine*, not a delivery discipline. Mapping:

- The Delivery Loop state machine (`process/delivery-loop.md` §4.2.4: `dev_pending → gate_pending → review_pending → close_pending → …`) maps naturally onto a LangGraph graph — nodes are spawn functions, edges are the verdict-routed transitions.
- The MANDATORY_CHECKPOINTS become human-in-the-loop interrupts on specific edges.
- `scope_envelope_check` and the F5 eval run are deterministic nodes (no LLM).

If you already run LangGraph, you can implement the Delivery Loop *as* a graph — aidazi tells you what the nodes and gates must be; LangGraph runs them.

### §3.5 AutoGen

AutoGen centers on conversable agents and group-chat orchestration. Mapping:

- The 5 roles can be AutoGen agents, but the **no-shared-chat-history** invariant (§3.4 #1) is the critical divergence: aidazi roles pass context via repo docs, not conversation. An AutoGen-native group chat where all roles see all messages would violate spawn isolation and self-grading boundaries.
- Use AutoGen for the *within-role* fan-out (a role's sub-agents conversing to draft a plan), not for *cross-role* communication. Cross-role hand-off is always a durable artifact.
- Termination conditions map to verdict schemas + checkpoints.

## §4 What aidazi adds that none of these have

If you take only the headline: aidazi's distinguishing pattern is **F5 evidence + the two-gate split + calibration**.

- **F5 evidence** — Acceptance reads real execution artifacts the orchestrator captured; it never judges from code inspection, and the dev sandbox never opens to it. No persona library or graph engine specifies this; it's what makes the outcome verdict trustworthy.
- **Code Reviewer ≠ Acceptance** — two gates, two questions, two verdicts. Most frameworks have one "QA/review" step; aidazi insists that "clean code" and "right outcome" are independent and both gate.
- **Calibration** — an autonomous judge proves its agreement/flip rates before its verdict counts; otherwise autonomy auto-degrades.
- **closure_contract symmetry** — Research authors the contract; Acceptance judges against it; neither may unilaterally move it. The contract is the seam that makes the two-gate split meaningful.
- **Two named loops** — self-improvement (Auto Loop) and team delivery (Delivery Loop) are kept distinct (`docs/two-loops-explainer.md`).

## §5 How to bring your existing setup

1. Keep your runtime engine (LangGraph / AutoGen / a coding-agent harness) — aidazi runs on top.
2. Map your personas onto the 5 roles per §3; collapse extras into role skills, not new chain roles.
3. Add the two things you're probably missing: the **Acceptance gate** (with a closure_contract) and the **Code-Reviewer/Acceptance split**.
4. Mount your skill/subagent library via `process/role-skill-model.md`, respecting per-role whitelists.
5. Record divergences in `docs/current/adoption-state.md`.

Brownfield adopters: this composes with `docs/brownfield-guide.md` — bringing an existing framework is a brownfield adoption.

---

End of industry mapping.
