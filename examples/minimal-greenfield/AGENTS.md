# AGENTS.md — Acme Returns Bot (aidazi consumer)

This is a filled-in example of the consumer-side `AGENTS.md` (copied from `aidazi/AGENTS.md` and edited). A fresh role session reads this first at cold-start.

## §1 Project identification

```yaml
project_name: acme-returns-bot
adopter_track: type_a
framework_version: v4.0.0
charter_path: ./charter.yaml          # present but orchestrator optional; this example is human-paste
last_updated: 2026-06-12
```

## §2 Framework governance chain (@-include)

Every session loads these in order before any work:

@aidazi/governance/constitution.md
@aidazi/governance/doc_governance.md
@aidazi/governance/context_briefing.md

Then the session loads its role card from `aidazi/role-cards/`.

## §3 Adopter-side state ledgers (load at cold-start)

@./docs/current/adoption-state.md          — per-Δ status; override registry
@./docs/current/runtime_invariants.md      — Tier-0 invariants (refund-eligibility domain)
@./docs/current/domain_taxonomy.md         — entities + UC taxonomy + vocabulary
@./docs/current/agent_context_guide.md     — per-task reading lists

## §4 5-role chain registry

This project instantiates all 5 roles, human-paste (no orchestrator yet). Backing agent for every role: Claude Code (single-developer project; one human walks multiple roles in fresh sessions per §3.4 invariant #1).

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

This file → `aidazi/docs/adoption-overview.md` → `aidazi/governance/constitution.md` → `docs/current/adoption-state.md` → the relevant role card.

---

End of AGENTS.md.
