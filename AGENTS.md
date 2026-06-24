# AGENTS.md — consumer-side template (aidazi v4.0.0)

This file is the **consumer template**. Copy it to your adopter repo's root as `AGENTS.md` and replace `<placeholders>` with project-specific values.

**Harness root-file wiring (normative source: `aidazi/governance/context_briefing.md` §1.1).** Which root file a harness auto-loads differs, so wire per harness — `AGENTS.md` and `CLAUDE.md` are **not** interchangeable copies:
- **Claude Code** auto-loads `CLAUDE.md`, not a bare `AGENTS.md`. Add a one-line root `CLAUDE.md` containing exactly `@AGENTS.md` so Claude Code imports this entry. Never duplicate the governance chain into `CLAUDE.md` — the two entry points drift; `CLAUDE.md` only imports `AGENTS.md`.
- **OpenAI Codex** auto-loads this `AGENTS.md` directly — no `CLAUDE.md` needed.
- **Cursor** needs its own `.cursor/rules` entry; a bare `AGENTS.md` is not Cursor wiring.

Because Claude Code and Codex can be used alternately, the canonical scaffold ships **both** root files (`AGENTS.md` + a `CLAUDE.md` of `@AGENTS.md`). Validate with `engine-kit/validators/adopter_wiring_validator.py <root> --harness claude_code`.

The file's purpose: a fresh coding-agent session reads this file FIRST at cold-start. By default that fresh session is a lightweight **Control Plane Session** (natural-language command surface), not one of the five delivery roles. A role session starts only after explicit role activation or orchestrator/runner spawn.

---

## §1 Project identification

```yaml
project_name: <adopter-name>
adopter_track: type_a | type_b | type_c | type_a_b_hybrid
framework_version: v4.0.0
charter_path: <adopter>/charter.yaml          # if Δ-18 orchestrator adopted
last_updated: <YYYY-MM-DD>
```

## §2 Framework governance chain (role/on-demand load)

Default Control Plane Sessions do not `@`-include the full governance chain. This keeps fresh natural-language command sessions small. When a session is explicitly activated as a role session, or when the Control Plane needs to reason about framework governance, load these in order:

1. `aidazi/governance/constitution.md`
2. `aidazi/governance/doc_governance.md`
3. `aidazi/governance/context_briefing.md`

Then session follows §3A. It loads a role-specific card only when a role is explicitly being adopted.

## §3A Default Control Plane Session (natural-language command surface)

When the human has not explicitly activated Research / Deliver / Dev / Code Reviewer / Acceptance, the session defaults to **Control Plane**:

- Classify the human's natural-language request.
- Record the interpreted intent in `.orchestrator/control/intents.jsonl`.
- Read or update `.orchestrator/control/state.json` as the small state index.
- Dispatch, resume, or prepare the appropriate role/runner path.
- Stop at human-authority gates and unresolved ambiguity.

The Control Plane Session is NOT a sixth role and does not sign role artifacts. It does not write Research briefs, Deliver close verdicts, code changes, Code Reviewer findings, or Acceptance verdicts unless the human explicitly activates that role in a fresh role session.

Detailed routing rules live in `aidazi/process/control-plane-routing.md` and are loaded on demand.

```control-plane-load
allow:
  - AGENTS.md
  - .orchestrator/control/state.json
  - .orchestrator/control/intents.jsonl
  - .orchestrator/control/checkpoints-index.json
  - charter.yaml
  - docs/current/adoption-state.md
  - docs/current/agent_context_guide.md
on_demand:
  - aidazi/process/control-plane-routing.md
  - aidazi/schemas/control-plane-intent.schema.json
  - aidazi/schemas/control-plane-state.schema.json
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

@<adopter>/docs/current/adoption-state.md         — per-Δ status; override registry
@<adopter>/docs/current/agent_context_guide.md    — adopter-side per-task reading lists

The Control Plane Session does not default-load full domain/runtime docs. Role sessions load role-specific adopter context through their prompt `load_list` or role briefing list.

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

Every default Control Plane Session loads §2 + §3A + the minimal §3 entries above. Every role session loads §2 + §3 plus the relevant role card and per-role briefing list. The specific compact prompt (Dev / Review / Acceptance) carries the per-session `load_list` enumerating additional files; this AGENTS.md establishes the baseline without turning the default session into a role.

The framework-side governance chain (`aidazi/governance/*`) remains the required role-session chain, but it is not part of the default Control Plane load graph. The adopter-side files referenced in the `control-plane-load` block are the default Control Plane load graph; larger `docs/current/*` files are role/on-demand context unless explicitly listed.

---

End of AGENTS.md.
