# AGENTS.md — consumer-side template (aidazi v4.0.0)

The **consumer template**: copy to your adopter repo root as `AGENTS.md`, replace `<placeholders>`. A fresh coding-agent session reads it FIRST at cold-start and defaults to a lightweight **Control Plane Session** (natural-language command surface), not one of the five delivery roles — a role session starts only on explicit role activation or orchestrator/runner spawn.

**Harness root-file wiring** (normative: `aidazi/governance/context_briefing.md` §1.1; `AGENTS.md` and `CLAUDE.md` are **not** interchangeable copies). Wire per harness, then validate: `engine-kit/validators/adopter_wiring_validator.py <root> --harness claude_code`.
- **Claude Code** auto-loads `CLAUDE.md`, not a bare `AGENTS.md` → ship a one-line root `CLAUDE.md` of exactly `@AGENTS.md` (never duplicate the governance chain into it — the two entry points drift; `CLAUDE.md` only imports `AGENTS.md`).
- **OpenAI Codex** auto-loads this `AGENTS.md` directly — no `CLAUDE.md` needed.
- **Cursor** needs its own `.cursor/rules` entry; a bare `AGENTS.md` is not Cursor wiring.

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

1. `aidazi/governance/constitution-core.md` (always-load constraint kernel; load the full `aidazi/governance/constitution.md` on-demand per its triggers)
2. `aidazi/governance/authoring-kernel.md` (always-load doc-authoring/governance kernel; load the full `aidazi/governance/doc_governance.md` on-demand per context_briefing §2.6)
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

The Control Plane MAY write machine-owned routing state and roadmap mutations that
directly encode a Customer command. For new adopters, `docs/milestone-backlog.md`
is a generated human-readable projection, not an independently edited source.
Default `delivery_mode` is `single_milestone` (active execution source =
`charter.yaml`); `campaign-plan.json` is authoritative only when the adopter
explicitly opts into `delivery_mode: campaign`.

Detailed routing rules live in `aidazi/process/control-plane-routing.md` and are loaded on demand.

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

Human onboarding (NOT a session load — agent sessions follow §2/§3A). A new human contributor reads the framework read order in `aidazi/README.md` (§Read order) + `aidazi/docs/adoption-overview.md` + `aidazi/docs/two-loops-explainer.md`, then this project's `docs/current/adoption-state.md` (overrides) and `docs/foundational/` (business-need / product-service-design / technical-plan). Per track: `aidazi/docs/greenfield-guide.md` or `brownfield-guide.md` + `aidazi/process/profile-aware-maturity.md` (Δ-14). Constraints come from the §2 kernel trio (full `constitution.md` on-demand for rationale).

## §8 Sessions read this for context

A default Control Plane Session loads §2 + §3A + the minimal §3 entries; a role session loads §2 + §3 plus its role card and per-role briefing list, and the compact Dev / Review / Acceptance prompt carries the per-session `load_list` for any additional files. This file establishes the baseline without turning the default session into a role. The governance kernels named in §2 are the always-load role-session chain (the full canonical `constitution.md` / `doc_governance.md` load on-demand); they are NOT in the default Control Plane load graph — the adopter-side files in the `control-plane-load` `allow` list are, and larger `docs/current/*` files are role/on-demand context unless explicitly listed.

---

End of AGENTS.md.
