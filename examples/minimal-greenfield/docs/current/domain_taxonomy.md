---
title: Domain taxonomy
doc_tier: current-runtime
status: current
implementation_status: not_started
source_of_truth: this file
last_reviewed: <YYYY-MM-DD>
review_cadence: every 3-5 milestones
notes: >
  Project's domain vocabulary: workflow lanes, shift detection,
  escalation, grounding concepts. Required by
  `framework/governance/constitution.md`. Fill during M0.
---

# Domain taxonomy

## 1. Workflow lanes

Your project's "lanes" — the LLM-classified mode of conversation.
Define each lane with: name, when active, tools/capabilities
available, how the LLM decides to enter.

### Lane: `<lane-name-1>`

- **When active**: <describe the user-state / intent for this lane>
- **Tools available**: <list>
- **LLM entry signal** (semantic, NOT keyword): <describe>
- **Lane exit conditions**: <describe>

### Lane: `<lane-name-2>`

(same shape)

### Lane: `<lane-name-3>`

(same shape)

## 2. Shift / drift detection

When the user moves between lanes, the LLM detects the transition.
Define the observable signals as semantic categories, NOT keywords.

- **Signal: <signal-name-1>** — <description of the semantic pattern
  the LLM looks for; what state in the projection surfaces this>
- **Signal: <signal-name-2>** — <description>

## 3. Escalation signals

When the agent should hand off to a human / higher-privileged path.

- **Category: <escalation-category-1>** — <user-facing description;
  when the LLM should escalate; what tool / capability the escalation
  uses>
- **Category: <escalation-category-2>** — <description>

## 4. Grounding concepts

What facts must be grounded in retrieved evidence vs may be stated
freely.

- **Must ground**:
  - <fact category 1, e.g., "product specifications">
  - <fact category 2, e.g., "current inventory">
- **May state freely**:
  - <category 1, e.g., "general domain knowledge">
  - <category 2, e.g., "natural conversational filler">

## 5. Layer extensions (optional)

If your project adds a §3.1 layer to the framework's nine:

### Layer: `<new-layer-name>`

- **Why needed**: <one paragraph; what failure shape doesn't fit the
  existing nine>
- **Decision question for §3.2** (when to route to this layer):
  <one or two sentences>
- **Example failure**: <one paragraph>

## Glossary

- `<term-1>`: <one-line definition>
- `<term-2>`: <definition>

(Used by deliver / dev / review agents to disambiguate terms in
sprint planning and findings.)
