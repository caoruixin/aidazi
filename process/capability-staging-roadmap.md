---
title: Capability staging roadmap (Δ-11)
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
size_target: 10KB
notes: >
  Δ-11 AMEND per v4-plan §4.1: S0-S6 staging roadmap + S5 entry condition
  (§3.6 Acceptance judge calibration completed). Staging is suggested per
  Constitution §7.0; adopters skip stages they don't need.
---

# Capability staging roadmap (Δ-11)

The framework's capabilities ladder from S0 (manual + framework default behaviors) to S6 (fully autonomous Δ-18 orchestration). Each stage adds one capability layer. Adopters do NOT have to traverse the ladder in order — most projects skip stages they don't need. The roadmap exists so the friction landing each stage is documented.

This is a SUGGESTED progression per Constitution §7.0. Adopters override the order with rationale in `adoption-state.md`.

## §1 The stage ladder (S0 through S6 + half-stage guidance markers)

The ladder has 7 integer stages (S0 / S1 / S2 / S3 / S4 / S5 / S6) plus four half-stage markers (S1.5 / S2.5 / S3.5). **Integer stages are the planning anchors; half-stages are GUIDANCE MARKERS, not mandatory gates.**

- A half-stage marker names a frequently-useful intermediate capability — e.g., S1.5 (Code Reviewer with anti-hardcode kernel) is a strict-subset of S2 (charter authoring) commonly reached as a discrete step.
- Adopters MAY skip half-stage markers (jump S1 → S2 directly) if their team's adoption is faster than the marker resolution.
- Adopters MAY ALSO use half-stage markers as explicit goal labels in `docs/current/adoption-state.md` if the intermediate capability is load-bearing for their planning.

Both uses are valid. The framework reserves the names so adopters share vocabulary when they DO want to mark intermediate state.



### §1.1 S0 — Manual paste with role-chain discipline

- Adopt the 5-role chain (Constitution §3) in pure human-paste mode.
- No orchestrator. No charter.
- Customer pastes activations; the human walks each role's session boundary.
- Acceptance runs manually at milestone close; closure_contract symmetry check is human discipline.

**Entry condition**: framework consumed; `AGENTS.md` references the constitution chain.
**Exit signal**: the team is operating cleanly in 5-role mode for ≥2 milestone closes.

### §1.2 S1 — Bad-case suite + Acceptance verdict discipline

- Bad-case suite (`process/badcase-lifecycle.md`) is curated.
- Tier-1 (smoke) + Tier-2 (scenario) cases exist.
- Acceptance Agent produces JSON verdicts per `schemas/acceptance-verdict.schema.json`.

**Entry condition**: S0 + at least 5 bad cases in `eval/bad_cases/`.
**Exit signal**: Acceptance verdicts consistently reference closure_contract clauses; the team trusts the verdict format.

### §1.3 S1.5 — Code Reviewer with anti-hardcode kernel

- Code Reviewer Agent runs `templates/anti-hardcode-review-kernel.md` at sub-sprint close.
- 4-line header + per-finding JSON shape adopted.
- `docs/codex-findings.md` is part of the close conversation.

**Entry condition**: S1.
**Exit signal**: Code Reviewer findings are routinely consumed by Deliver close conversation per `templates/deliver-close-taxonomy.md`.

### §1.4 S2 — Charter authoring (without orchestrator)

- Adopter authors a `charter.yaml` per `templates/mission-charter.yaml`.
- Charter is REFERENCE-ONLY (no orchestrator runs it); declares autonomy.level, approved_scope, tooling, acceptance config.
- Customer + Deliver consult the charter at each sub-sprint dispatch.

**Entry condition**: S1.5 + adopter's first formal closure_contract authored.
**Exit signal**: charter authoring is routine; the team treats charter scope_in / out as binding.

### §1.5 S2.5 — Manual scope_envelope_check

- Before each sub-sprint close, Deliver + Customer manually walk `scope_envelope_check` (per `process/delivery-loop.md` §4.2.5) — verify diff stayed in modules_in_scope + layers_allowed.
- Flag scope deviations as `scope_deviation` even without orchestrator emission.

**Entry condition**: S2.
**Exit signal**: scope_deviation detection becomes habit; few mid-milestone scope expansions.

### §1.6 S3 — F5 evidence pattern (manual)

- Deliver / human runs the eval harness BEFORE Acceptance (manual F5).
- Acceptance prompt's `evidence_path` references real artifact files.
- The Dev sandbox doesn't run the eval directly.

**Entry condition**: S2.5 + eval harness in place.
**Exit signal**: F5 evidence is the de-facto Acceptance input; code-only acceptance verdicts are flagged.

### §1.7 S3.5 — Acceptance calibration set

- Adopter builds labeled set: `calibration/labeled_acceptance_cases/manifest.json`.
- Each entry: `(trace, expected_verdict ∈ {PASS, FAIL})`.
- Run Acceptance twice per entry; compute agreement_rate + flip_rate.

**Entry condition**: S3.
**Exit signal**: calibration set has ≥10 entries spanning both PASS and FAIL; metrics stabilize.

### §1.8 S4 — Charter validator (optional automation)

- Tooling that validates the charter against `schemas/mission-charter.schema.json`.
- Charter editing rules enforced (Constitution §1.7-C / §1.7-D).
- Adopter MAY skip this stage if comfortable with manual validation.

**Entry condition**: S2.
**Exit signal**: charter changes are routinely validated before dispatch.

### §1.9 S5 — Δ-18 orchestrator adoption

- Orchestrator runs the state machine + spawn function set + scope_envelope_check + F5 evidence.
- `autonomy.level: human_on_the_loop` typically.
- MANDATORY_CHECKPOINTS fire via filesystem inbox.

**Entry condition** (extended per v4): S3.5 + Acceptance judge calibration COMPLETED per Constitution §3.6 (`agreement_rate ≥ 0.9 AND flip_rate ≤ 0.1`).
**Exit signal**: ≥3 successful orchestrator-driven milestone closes; Customer comfortable with checkpoint cadence.

### §1.10 S6 — `fully_autonomous_within_budget`

- Promote `autonomy.level` to `fully_autonomous_within_budget`.
- Budget caps in `charter.budget` are binding; orchestrator halts at limits.
- MANDATORY_CHECKPOINTS still fire (Constitution §1.7-D non-bypass).

**Entry condition**: S5 + calibration current + ≥3 successful S5 milestone closes.
**Exit signal**: this is the highest-trust mode; some adopters never need it.

## §2 Reverse trigger table

When a higher stage breaks, fall back to a lower stage:

| Reverse trigger | Fall back to |
|---|---|
| Calibration invalidated (judge model swap) | S3 (manual F5; calibration re-run) |
| Acceptance verdict consistently disagrees with Customer's manual judgment | S3.5 (re-build calibration set) |
| Orchestrator's scope_envelope_check repeatedly fires false-positive | S2.5 (manual scope envelope; tune charter scope) |
| Charter validator rejects routine charters (over-strict) | S2 (manual validation; revise charter template) |
| Code Reviewer's anti-hardcode kernel returns spurious findings | S1.5 (tune kernel exemption rules; route to fold-back) |
| Bad-case suite drifts from project goals (cases pass but closure_contract still violated) | S1 (re-curate bad cases; possibly re-author closure_contract) |
| Role-chain boundaries blur (e.g., Deliver writing code) | S0 (return to explicit session boundaries) |

Reverse triggers are NORMAL — most adopters bounce around stages as the project's needs change.

## §3 Stage-skipping

Adopters may skip stages they don't need:

- A Type C demo can land at S0 + S1 and stay there forever.
- A Type A hobby project might never need S5 / S6.
- A research-only project might use S0 + S1.5 (Code Reviewer) without Acceptance enabled.

Skipping is documented in `docs/current/adoption-state.md` per-Δ status: stages-not-adopted are `not-applicable`.

## §4 Per-track suggested entry stages

| Track | Suggested entry | Typical max |
|---|---|---|
| Type A (production) | S1.5 | S6 |
| Type A (research / prototype) | S0 | S1.5 |
| Type B (production SOP runner) | S1 | S5 |
| Type C demo | S0 | S1 |
| Type A+B hybrid | S1.5 | S6 |

These are starting points per Constitution §7.0; adopters override.

## §5 Cross-Δ relationships

- **Δ-13** (stage-stable heuristic) — S5+ depends on architectural stability heuristics.
- **Δ-14** (profile-aware maturity) — per-track suggested stages.
- **Δ-18** (delivery loop) — S5 / S6 are where Δ-18 orchestrator is active.
- **Constitution §3.6** — calibration gate is S5 entry condition.

## §6 What this Δ does NOT cover

- Specific tooling for each stage (charter validator implementation; calibration set authoring tools).
- Domain-specific stage variants.
- Cost/budget analysis per stage.

## §7 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The 7-stage shape is stable framework vocabulary. Adopters MAY add intermediate stages locally (e.g., S5.5 for orchestrator-with-experimental-features) with rationale.

---

End of Δ-11 Capability staging roadmap.
