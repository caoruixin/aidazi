# AGENTS.md — Acme Returns Bot (aidazi consumer)

This is a filled-in example of the consumer-side `AGENTS.md` (copied from `aidazi/AGENTS.md` and edited). A fresh coding-agent session reads this first at cold-start. By default it is a lightweight Control Plane Session, not one of the five delivery roles.

## §1 Project identification

```yaml
project_name: acme-returns-bot
adopter_track: type_a
framework_version: v4.0.0
charter_path: ./charter.yaml          # present but orchestrator optional; this example is human-paste
last_updated: 2026-06-12
```

## §2 Framework governance chain (role/on-demand load)

Default Control Plane Sessions do not `@`-include the full governance chain. When a session is explicitly activated as a role session, load these in order:

1. `aidazi/governance/constitution-core.md` (always-load kernel; full `aidazi/governance/constitution.md` on-demand per its triggers)
2. `aidazi/governance/authoring-kernel.md` (always-load kernel; full `aidazi/governance/doc_governance.md` on-demand per context_briefing §2.6)
3. `aidazi/governance/context_briefing.md`

Then the session loads its role card from `aidazi/role-cards/`.

## §3A Default Control Plane Session

When the human has not explicitly activated a role, the session classifies the natural-language request, records the interpreted intent, reads the small control state index, and dispatches or prepares the correct role/runner path. It is not a sixth role and does not sign role artifacts.

Default delivery topology is `single_milestone`: `charter.yaml` is the active
execution source and `docs/milestone-backlog.md`, if present, is generated from
Control Plane roadmap state. `campaign-plan.json` is authoritative only after an
explicit Campaign opt-in.

```control-plane-load
allow:
  - AGENTS.md
  - .orchestrator/control/state.json
  - .orchestrator/control/intents.jsonl
  - .orchestrator/control/roadmap-state.json
  - .orchestrator/control/roadmap-mutations.jsonl
  - .orchestrator/control/checkpoints-index.json
  - charter.yaml
  - docs/current/adoption-state.md
  - docs/current/agent_context_guide.md
on_demand:
  - aidazi/process/control-plane-routing.md
  - aidazi/schemas/control-plane-intent.schema.json
  - aidazi/schemas/control-plane-state.schema.json
  - aidazi/schemas/roadmap-state.schema.json
  - aidazi/schemas/roadmap-mutation.schema.json
forbid:
  - aidazi/role-cards/**
  - aidazi/process/delivery-loop.md
  - aidazi/process/campaign-loop.md
  - docs/action_bank.md
  - docs/handoff.md
  - docs/10-handoff.md
  - docs/research-briefs/**
  - docs/proposals/**
  - docs/sprints/**
  - .orchestrator/audit/**
  - .runs/**
  - eval/runs/**
```

## §3 Adopter-side state ledgers (load at cold-start)

@./docs/current/adoption-state.md          — per-Δ status; override registry
@./docs/current/agent_context_guide.md     — per-task reading lists

Runtime invariants and domain taxonomy are role/on-demand context, not default Control Plane context.

## §4 5-role chain registry

This project instantiates all 5 roles, human-paste (no automated runner yet). The default Control Plane Session helps the human decide which role prompt or compact prompt to launch next. Backing agent for every role: Claude Code (single-developer project; one human walks multiple roles in fresh sessions per §3.4 invariant #1).

| Role | Activation | Source spec |
|---|---|---|
| Customer (human) | Direct, at gates | `aidazi/process/customer-checkpoints.md` |
| Research | Paste role card | `aidazi/role-cards/research-agent.md` |
| Deliver | Paste role card | `aidazi/role-cards/deliver-agent.md` |
| Dev | Paste compact dev prompt | `aidazi/role-cards/dev-agent.md` |
| Code Reviewer | Paste compact review prompt | `aidazi/role-cards/code-reviewer-agent.md` |
| Acceptance | Customer paste at milestone close | `aidazi/role-cards/acceptance-agent.md` |

## §5 Two-loop discipline

This project uses only the **Delivery Loop** (Concept 2; human-paste form). No Auto Loop yet — the bot does not self-improve. If we add Auto Loop later, we name it distinctly per §1.7-E.

## §6 Adopter-specific overrides

See `docs/current/adoption-state.md`. We override two suggested defaults (smaller bad-case suite cadence; tighter `cell_size_target`) with rationale recorded there. We diverge from nothing in the §1.7 hard set.

## §7 Cold-start read order

Default Control Plane: this file → `.orchestrator/control/state.json` if present → `.orchestrator/control/intents.jsonl` recent summary if present → `docs/current/adoption-state.md` + `docs/current/agent_context_guide.md`.

Explicit role session: this file → `aidazi/governance/constitution-core.md` → `aidazi/governance/authoring-kernel.md` → `aidazi/governance/context_briefing.md` → `docs/current/adoption-state.md` → the relevant role card (the always-load kernel trio; full `constitution.md` / `doc_governance.md` load on-demand per their triggers).

---

End of AGENTS.md.
