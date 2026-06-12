---
title: Agent design elicitation (Δ-15)
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-07
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 12KB
notes: >
  Δ-15 AMEND per v4-plan §4.1: 6 must-answer questions + 4 inventories +
  closure_contract draft as Part D output. v4 adds Q6 boundary clause for
  "where Acceptance evaluates closure_contract" + Part B inventory adds
  "claimed closure_contract draft" item. Loaded by Research Agent (Path 1
  formal greenfield) + at Δ-16 prerequisite gate.
---

# Agent design elicitation (Δ-15)

When a new agent / workflow / demo is being designed, walk this heuristic Q&A + inventory + tool-vs-skill decision tree + industry research. Output is a populated input pack the Research Agent uses to author `docs/research-briefs/<id>.md` (including its mandatory closure_contract per Constitution §1.7-B).

This is greenfield-mode elicitation. For brownfield, see `docs/brownfield-guide.md`.

## §1 Part A — 6 must-answer questions

These six questions are LOAD-BEARING. Skipping any one leaves a gap that surfaces at Acceptance or later — typically as `research_contract_revision` or `out_of_scope_review`.

### §1.1 Q1 — Domain

What is the domain? Industry, customer segment, regulatory floor, time-pressure shape (synchronous vs asynchronous; real-time vs batch).

**Why it matters**: domain determines what tools are allowed, what policies apply, what user expectations exist. A customer-service agent in healthcare vs e-commerce has different Tier-0 invariants from the start.

### §1.2 Q2 — Goal

What does success look like? The single sentence that names the user-facing outcome the system delivers.

**Why it matters**: goal = the positive shape of the closure_contract. A vague goal produces a vague closure_contract produces an Acceptance verdict that nobody trusts.

### §1.3 Q3 — Problems

What are the concrete failure shapes the system is supposed to PREVENT or RECOVER from? Typically 3-5 named problem types.

**Why it matters**: problems = the anti-pattern shape of the closure_contract. Without them, the closure_contract is "do good things" — unjudgeable.

### §1.4 Q4 — Method

What kind of approach is the agent / workflow / demo? Specifically:
- Type A semantic per-turn reasoning? OR
- Type B fixed-sequence SOP? OR
- Type C demo with off-the-shelf skills? OR
- Type A+B hybrid?

**Why it matters**: method determines which T1 profile overlay applies + which Δs are READY vs DEFERRED per `process/profile-aware-maturity.md`.

### §1.5 Q5 — Knowledge

What does the agent / workflow need to KNOW? Domain knowledge corpus; canned reply templates; FAQ index; product catalog; policy manual.

**Why it matters**: knowledge = the `knowledge_corpus` and `canned_reply` prerequisites per Δ-16. Type A needs this richly; Type B inherits from the SOP; Type C may not need at all.

### §1.6 Q6 — Boundary (v4 EXTENDED)

Where does the system's authority end?

- What's runtime-owned (PII / safety floor; capability boundary; grounding floor)?
- What's LLM-owned (user goal; topic; next action)?
- **Where does Acceptance evaluate closure_contract** (v4 addition) — what's the evidence surface; what shape do anchor phrases take in the domain language?

**Why it matters**: Q6 binds Δ-3 decision #7 (policy/safety surface) AND directly informs how the closure_contract's anchor phrases should read. v4's addition surfaces the Acceptance lens explicitly so the closure_contract isn't authored without considering "how do we verify this?"

## §2 Part B — 4 inventories (per profile)

Per track, populate the 4-inventory set:

### §2.1 Type A inventories

- **Knowledge inventory** — what the agent knows: corpus, FAQ, product catalog, policy index.
- **Tool inventory** — what the agent can DO: tool catalog with ALLOW matrix per UC.
- **Skill inventory** — what multi-step routines exist (Type A skills are LLM-orchestrated, not SOP-runner).
- **Policy inventory** — what the agent CANNOT do alone (product policy / regulatory questions).

### §2.2 Type B inventories

- Knowledge (per SOP-step).
- Tools (per SOP-step).
- **SOP inventory** (replaces "Skill") — the actual SOP rows; each step with its slot list + verification gates.
- Policy.

### §2.3 Type C inventories

- Knowledge (lightweight).
- Tools (lightweight; mostly off-the-shelf).
- **Off-the-shelf skill inventory** — pre-built skills the demo uses without custom logic.
- Policy.

### §2.4 v4 addition — "Claimed closure_contract draft"

Per v4-plan §4.1 Δ-15 AMEND: as part of the inventory phase, the Research Agent (or human + Research) drafts a CLAIMED closure_contract — a first-pass three-component paragraph (positive shape + anti-pattern + anchor phrases). This is NOT the final closure_contract; it's a starting point that the Q1-Q6 + inventory work will refine.

Including the draft in the inventory makes the closure_contract authoring an explicit STEP of elicitation, not a backwards-derived afterthought.

## §3 Part C — Tool vs Skill decision tree (Type A only)

For each "the agent should be able to X" candidate, walk:

1. Is X a single atomic operation (e.g., "look up order status")? → tool.
2. Is X a multi-step routine the runtime should orchestrate deterministically? → if YES, it's a Type B SOP candidate; consider whether the project is actually A+B hybrid. If NO (orchestration is per-context), → skill (LLM-orchestrated).
3. Is X a domain question the LLM can answer from knowledge + tool calls? → not a separate skill; the LLM owns it.
4. Is X actually a policy question (the LLM can't answer without product sign-off)? → policy inventory; not a tool.

The output is a populated tool catalog + skill catalog. Constitution §1.7-A applies: pick ONE abstraction layer (tool-use default for Type A); the skill catalog is named but execution goes through the chosen surface.

**Disambiguation**: the skill catalog here is the PRODUCT skill inventory — multi-step routines the product agent performs. It is distinct from **role skills** (capability packs mounted on the 5 framework roles building the product; `process/role-skill-model.md` §2 has the four-sense table).

## §4 Part D — Industry research (Type A only)

For greenfield Type A agents, the Research Agent runs a 0→1 industry research synthesis:

- What do similar agents in this domain look like (industry analogues)?
- What's the conventional vocabulary the user-side uses?
- What patterns have other adopters discovered?
- What domain-specific Tier-0 invariants are common?

Output: `docs/discovery/industry-synthesis-<id>.md`. This is informational; not part of the research-brief. It feeds the closure_contract's domain language + anti-pattern shape.

Type B / C projects MAY skip Part D if the SOP / off-the-shelf inventory already establishes domain language.

## §5 Part E — Closure_contract finalization

After Q1-Q6 + inventories + tool-vs-skill + industry research, the Research Agent finalizes the closure_contract paragraph per `templates/compact-research-brief.md`:

1. Positive shape — from Q2 (Goal) + Q6 (boundary on what counts as "success").
2. Anti-pattern — from Q3 (Problems) + industry research findings.
3. Anchor phrases — from Q1 (Domain language) + Q5 (Knowledge corpus terms).

The Research Agent runs the symmetry self-check per `role-cards/research-agent.md` §6 before requesting Customer sign-off.

## §6 What this Δ does NOT cover

- Phase 3+ technical decisions — `process/tech-architecture-decision-catalog.md` (Δ-3).
- Bad-case suite seeding — `process/badcase-lifecycle.md`.
- Brownfield elicitation — `docs/brownfield-guide.md`.
- Domain-specific surface adapters — adopter-domain layer.

## §7 Cross-references

- `templates/compact-research-brief.md` — the output template Δ-15 populates.
- `process/agent-creation-prerequisites.md` (Δ-16) — the prereq gate that consumes Δ-15 outputs.
- `process/domain-discovery-process.md` (Δ-2) — 3-dim domain elicitation; complementary to Δ-15's 6 questions.
- `process/profile-aware-maturity.md` (Δ-14) — per-track applicability.

## §8 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 6 questions + 4-inventory shape is stable framework vocabulary. The v4 additions (Q6 boundary-includes-Acceptance-lens + Part B closure_contract draft + Part E closure_contract finalization) operationalize Constitution §3.4 invariant #4 (Research-Acceptance contract symmetry) and SHOULD NOT be elided.

---

End of Δ-15 Agent design elicitation.
