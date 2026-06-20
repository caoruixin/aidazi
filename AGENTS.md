# AGENTS.md — consumer-side template (aidazi v4.0.0)

This file is the **consumer template**. Copy it to your adopter repo's root as `AGENTS.md` (or `CLAUDE.md`, or `.cursor/rules`, depending on your tooling) and replace `<placeholders>` with project-specific values.

The file's purpose: a fresh role session (Customer / Research / Deliver / Dev / Code Reviewer / Acceptance) reads this file FIRST at cold-start, finds the @-included governance chain, and discovers the adopter-specific runtime contracts.

---

## §1 Project identification

```yaml
project_name: <adopter-name>
adopter_track: type_a | type_b | type_c | type_a_b_hybrid
framework_version: v4.0.0
charter_path: <adopter>/charter.yaml          # if Δ-18 orchestrator adopted
last_updated: <YYYY-MM-DD>
```

## §2 Framework governance chain (@-include)

Every session loads these in order before any work:

@aidazi/governance/constitution.md
@aidazi/governance/doc_governance.md
@aidazi/governance/context_briefing.md

Then session loads the role-specific card based on which role is being adopted (see §5 below).

## §3 Adopter-side state ledgers (load at cold-start)

@<adopter>/docs/current/adoption-state.md         — per-Δ status; override registry
@<adopter>/docs/current/runtime_invariants.md     — Tier-0 invariants list
@<adopter>/docs/current/domain_taxonomy.md        — domain-specific vocabulary
@<adopter>/docs/current/agent_context_guide.md    — adopter-side per-task reading lists

## §4 5-role chain registry

Per Constitution §3.1-§3.4, every adopter instantiates the 5-role chain:

| Role | Activation | Source spec |
|---|---|---|
| **Customer** (human) | Direct human action at gates | `aidazi/process/customer-checkpoints.md` |
| **Research Agent** | Paste role card OR orchestrator | `aidazi/role-cards/research-agent.md` |
| **Deliver Agent** | Paste role card OR orchestrator | `aidazi/role-cards/deliver-agent.md` |
| **Dev Agent** | Paste compact dev prompt | `aidazi/role-cards/dev-agent.md` |
| **Code Reviewer Agent** | Paste compact review prompt | `aidazi/role-cards/code-reviewer-agent.md` |
| **Acceptance Agent** | Customer paste OR calibrated orchestrator | `aidazi/role-cards/acceptance-agent.md` |

Backing coding-agent (Claude Code / Codex / other) per role is set in `charter.yaml` via `charter.tooling.<role>.agent_kind`. Role boundaries are universal regardless of backing agent (Constitution §3.4 invariants).

Optional **role skills** (capability packs) and intra-role sub-agent fan-out per role are declared via `charter.tooling.<role>.skills` / `.subagent_fanout` — see `aidazi/process/role-skill-model.md`. Skills and fan-out change how a role works, never who signs its artifacts (Constitution §3.4 invariant #6).

## §5 Two-loop discipline (Constitution §1.7-E)

If this project uses BOTH:
- **Auto Loop** (Concept 1; Type A only; `aidazi/modules/m-autoloop.md`) — agent self-improvement.
- **Delivery Loop** (Concept 2; Δ-18; `aidazi/process/delivery-loop.md`) — team delivery.

…name each distinctly in docs. See `aidazi/docs/two-loops-explainer.md` for the disambiguation discipline. Conflating the two is a §1.7-E framework breach.

## §6 Adopter-specific overrides

Document divergences from framework defaults in `docs/current/adoption-state.md` per Constitution §7.2.

Hard requirements (cannot be overridden — Constitution §1.8):
- Constitution §1.7 forbidden list (incl. §1.7-A through §1.7-E).
- Constitution §3.4 5-role boundary invariants.
- `aidazi/process/delivery-loop.md` §4.2.3 9 MANDATORY_CHECKPOINTS (if Δ-18 adopted).
- Constitution §3.6 Acceptance judge calibration gate.

Suggested defaults (override with rationale in adoption-state.md):
- Numerical size targets, cell sizes, calibration thresholds.
- Cadence triggers, manifest format choice, prompt token budgets.
- Per-Δ tier placement where Δ is recommendation-tier.

## §7 Cold-start read order for new contributors

A fresh person joining this project reads:

1. This file (`AGENTS.md`).
2. `aidazi/README.md` (framework elevator).
3. `aidazi/docs/adoption-overview.md` (mental model).
4. `aidazi/docs/two-loops-explainer.md` (Auto vs Delivery loop naming).
5. `aidazi/governance/constitution.md`.
6. `<adopter>/docs/current/adoption-state.md` (this project's overrides).
7. `aidazi/docs/greenfield-guide.md` (if onboarding to a fresh project) OR `aidazi/docs/brownfield-guide.md` (if joining an in-flight project).
8. Per-track guide: `aidazi/process/profile-aware-maturity.md` Δ-14.
9. Adopter's `docs/foundational/business-need.md` + `docs/foundational/product-service-design.md` + `docs/foundational/technical-plan.md` for project specifics.

## §8 Sessions read this for context

Every role session loads §2 + §3 above as part of cold-start. The specific compact prompt (Dev / Review / Acceptance) carries the per-session `load_list` enumerating additional files; this AGENTS.md establishes the always-load baseline.

The framework-side governance chain (`aidazi/governance/*`) is `load_discipline: always-load`. The adopter-side `docs/current/*` files referenced in §3 are effectively always-load per `aidazi/governance/context_briefing.md` §1's cold-start order.

---

End of AGENTS.md.
