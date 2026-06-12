---
title: Two loops in v4 — Auto Loop vs Delivery Loop
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
size_target: 12KB
split_trigger: if §4 anti-pattern catalog grows past 4KB, split to docs/two-loops-anti-patterns.md
notes: >
  Adopter-facing explanation of Constitution §3.7 — the two distinct "loop"
  concepts v4 names. Concept 1 = Auto Loop (Type A AI agent self-improvement
  via auto-research). Concept 2 = Delivery Loop (multi-agent team delivery +
  gap correction; Δ-18). The two are orthogonal; can coexist. Constitution
  §1.7-E forbids conflating them in adopter docs. This doc helps adopters
  name correctly.
---

# Two loops in v4 — Auto Loop vs Delivery Loop

v4 has two different "loop" concepts that adopters often conflate. They are **orthogonal** and **can coexist**. The framework names them distinctly so adopter documentation can be precise.

Constitution §1.7-E enforces this: adopter docs MUST name each loop distinctly when both are in use. This file is the adopter-facing explanation so you can do that correctly.

## §1 The two concepts at a glance

| Concept | v4 name | What it is | Subject (who/what improves) | Lives in | Track applicability |
|---|---|---|---|---|---|
| **Concept 1** | **Auto Loop** | A Type A AI agent uses an **auto-research method** to autonomously improve ITSELF — its prompts, skills, internal strategies, retrieval thresholds | The AI AGENT (the product being built) is the subject being improved | `modules/m-autoloop.md` + `process/post-deployment-iteration.md` (Δ-9 OBS triage + Auto Loop driver pattern) | Type A only |
| **Concept 2** | **Delivery Loop** (Δ-18) | The multi-agent team(Research / Deliver / Dev / Code Reviewer / Acceptance / Customer) collaboratively delivers work; **autonomously discovers gap between implementation and customer requirements** (Acceptance verdict = fix_required); autonomously fixes via Acceptance → human-confirm → Deliver fix-iteration | The TEAM (of agents + human) building / shipping the product is the subject doing the self-correction | `process/delivery-loop.md` + 5-role chain + orchestrator implementation | All tracks (orchestration via Δ-18 is optional per `autonomy.level`) |

### §1.1 One-line distinctions

- **Auto Loop**: "my AI agent gets better at being itself."
- **Delivery Loop**: "my dev team converges on what the customer asked for."

If you can't tell which loop your sentence is about by replacing the word "loop" with one of those two phrases — you're being ambiguous. Rephrase.

## §2 Why both exist in v4

### §2.1 Auto Loop is a CAPABILITY

Auto Loop is a capability a Type A project may build for its agent's self-improvement. The framework provides M-Autoloop module guidance:
- Anti-gaming forbidden list (per `modules/m-autoloop.md`).
- OBS triage L1/L2 (per `process/post-deployment-iteration.md` Δ-9).
- Auto Loop driver pattern (overnight job; bounded experiment; rollback gates).

But the framework does NOT drive the Auto Loop. The adopter's Type A project does. The framework provides the guardrails; the agent's own runtime invokes the loop.

### §2.2 Delivery Loop is the FRAMEWORK's own collaboration discipline

Delivery Loop is how multi-agent teams of any track work together. Applies whether the product being built is:
- A Type A agent.
- A Type B workflow.
- A Type C demo.

The Delivery Loop is universal across tracks; its automation layer (the orchestrator) is conditional.

## §3 They compose; they don't conflict

When a project uses BOTH:

- A Type A project's **Delivery Loop** drives sub-sprints to milestone close (orchestrator drives Research → Deliver → Dev → Code Reviewer → Acceptance).
- WITHIN a sub-sprint, the agent's **Auto Loop** may be invoked as a runtime self-improvement step (e.g., M-Autoloop optimizing prompts overnight during a sprint).

The two are orthogonal:
- **Auto Loop = vertical depth**: one agent self-improving.
- **Delivery Loop = horizontal flow**: team collaborating + delivering.

Visualized:

```
  ┌───────────────────────────────────────────────────────────────────┐
  │ Delivery Loop (horizontal — across milestones)                    │
  │                                                                   │
  │ Research → Deliver → Dev → Reviewer → Acceptance → milestone close│
  │                                                                   │
  │                       ↑                                           │
  │                       │  WITHIN a Type A Dev sub-sprint:          │
  │                       │                                           │
  │                       │  ┌─────────────────────────────────────┐  │
  │                       │  │ Auto Loop (vertical — self-improve) │  │
  │                       └──│                                     │  │
  │                          │ agent uses auto-research method     │  │
  │                          │ to optimize its own prompts/skills  │  │
  │                          │ (overnight job; bounded; rollback)  │  │
  │                          └─────────────────────────────────────┘  │
  └───────────────────────────────────────────────────────────────────┘
```

A Delivery Loop without an Auto Loop is normal. An Auto Loop without a Delivery Loop is possible (the team uses pure human-paste workflow but the agent self-improves overnight). Both together is the most common case for mature Type A projects.

## §4 §1.7-E forbidden pattern (Constitution): adopter docs MUST name each distinctly

Constitution §1.7-E:

> Adopter documentation MUST NOT conflate Auto Loop (Concept 1; Type A AI agent self-improvement via auto-research) with Delivery Loop (Concept 2; Δ-18 multi-agent team delivery + self-correction). When both are in use, each must be named distinctly.

**Why**: the two have different subjects (single agent vs multi-agent team), different scopes (per-agent vs per-milestone), and different drivers (M-Autoloop driver vs framework Delivery Loop orchestrator).

**Common failure signal**: an adopter doc says "the auto loop drove our milestone close." Does that mean:
- The Type A agent improved itself across the milestone? (Auto Loop sense.)
- The multi-agent team delivered the milestone using the Δ-18 orchestrator? (Delivery Loop sense.)
- Both — they were running concurrently, and one or the other (which?) was the proximate cause?

The sentence is ambiguous; debugging it requires re-reading code and decisions.

**How to apply**: in every doc that mentions either loop, name it explicitly on first reference:

- ✅ "Auto Loop (Concept 1; agent self-improvement) optimized prompts overnight; the Delivery Loop (Concept 2; team delivery) consumed the new prompts in the next morning's Research → Deliver dispatch."
- ❌ "The auto loop drove our milestone close."
- ❌ "The orchestration loop ran overnight and the team consumed it next morning."

Subsequent references may use the short name once disambiguated.

## §5 Anti-pattern catalog

These are the specific phrasings that conflate the two and how to fix them.

### §5.1 "We use auto-loop to deliver milestones"

**Why bad**: "auto-loop to deliver" — Auto Loop's subject is the agent, not delivery. Reader can't tell if you mean the agent's overnight optimization or the team's Δ-18 orchestrator.

**Fix**: "We use the Delivery Loop orchestrator (Δ-18) to deliver milestones; the agent also runs Auto Loop overnight for prompt optimization."

### §5.2 "The auto loop's Acceptance verdict was fix_required"

**Why bad**: Acceptance verdicts are a Delivery Loop concept (Acceptance is the outcome gate); they don't apply to Auto Loop (Auto Loop doesn't have an Acceptance role).

**Fix**: "The Delivery Loop's Acceptance verdict was fix_required."

### §5.3 "Our delivery loop self-improves the agent's prompts"

**Why bad**: Delivery Loop doesn't self-improve the agent's prompts — it delivers milestones. Auto Loop is what self-improves.

**Fix**: "Our Auto Loop self-improves the agent's prompts; the Delivery Loop delivers milestones using the improved prompts."

### §5.4 "The orchestrator runs both loops"

**Why bad**: ambiguous which orchestrator. The Delivery Loop orchestrator (Δ-18) is the team-side automation; the Auto Loop driver (in `modules/m-autoloop.md`) is the agent-side automation. They're different software.

**Fix**: "The Δ-18 orchestrator runs the Delivery Loop; the M-Autoloop driver runs the Auto Loop. They're separate programs that share a calendar (Auto Loop overnight, Delivery Loop morning)."

### §5.5 "Acceptance fix_required triggers an auto-loop iteration"

**Why bad**: Acceptance fix_required triggers a Delivery Loop fix-iteration (Path 3 in the Deliver Agent's input paths). It does NOT trigger Auto Loop self-improvement.

**Fix**: "Acceptance fix_required triggers a Deliver Path 3 fix-iteration (Delivery Loop self-correction)."

## §6 Quick disambiguation rules

When you're about to write a sentence with "loop" in it:

1. **What is the subject of the loop?**
   - If "the agent" — it's Auto Loop.
   - If "the team" or "delivery" or "milestone" — it's Delivery Loop.

2. **What capability is being invoked?**
   - Prompt / skill / threshold self-optimization → Auto Loop.
   - Acceptance verdict + human-confirm + Deliver fix-iteration → Delivery Loop.
   - 5-role chain dispatch → Delivery Loop.
   - OBS triage + Auto Loop driver pattern → both (Δ-9 covers OBS triage; M-Autoloop is the driver).

3. **What's running it?**
   - M-Autoloop module / runtime in the agent → Auto Loop.
   - Δ-18 orchestrator / Δ-18 charter → Delivery Loop.

4. **What's the scope?**
   - Per-agent self-improvement, often per-overnight-job → Auto Loop.
   - Per-milestone or per-sub-sprint delivery → Delivery Loop.

If you can't answer all four for the sentence you're writing, the sentence is probably ambiguous. Rephrase.

## §7 When both are in use, write a session map

For projects running both loops, the adopter's `docs/current/` should include a short "session map" doc (free-form; not a template-required artifact) that names:

- What the Auto Loop driver is (which module / which script / which schedule).
- What the Delivery Loop charter is (path to charter.yaml; current autonomy.level; calibration status).
- What the boundary between them is — typically: "Auto Loop modifies `prompts/` overnight; Delivery Loop reads `prompts/` and treats them as runtime state at sprint dispatch time."

The session map prevents the "but I thought the auto loop was driving the milestone" confusion when two contributors are reading the project at different times.

This is a recommended pattern, not a framework hard requirement.

## §8 Pointers

- Constitution §3.7 — the canonical statement of the two-loops distinction.
- Constitution §1.7-E — the forbidden conflation rule.
- `process/delivery-loop.md` — Δ-18 spec (Delivery Loop).
- `modules/m-autoloop.md` — Auto Loop module spec.
- `process/post-deployment-iteration.md` — Δ-9 OBS triage (relevant to Auto Loop driver pattern + Delivery Loop Path 3 input).

## §9 Editing this doc

Application-guide tier; edits land at fold-back sub-sprint cadence. When adopter feedback (via `lessons/`) surfaces a new conflation pattern, the next fold-back may add to §5's anti-pattern catalog.

The §1 table + §1.1 one-liners + §6 disambiguation rules are the load-bearing teaching content. Don't bury them under prose; keep them scannable.

---

End of Two-loops explainer.
