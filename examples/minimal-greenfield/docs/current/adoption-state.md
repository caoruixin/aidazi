---
title: Acme Returns Bot — Adoption State vs aidazi framework
adopter_name: acme-returns-bot
framework_version: v4.0.0
last_reviewed: 2026-06-12
review_cadence: per milestone close
adoption_profile: B   # core: 5 roles human-paste, no orchestrator
---

# Per-Δ status

| Δ | v4 spec | Adopter status | Gap notes | Plan |
|---|---|---|---|---|
| Δ-2 Domain discovery | T0 | at-spec | UC taxonomy inferred from transcripts | — |
| Δ-3 Decision catalog | T0 | partial | uses decisions #1,#2,#6; #5 memory + #7 policy deferred | next milestone |
| Δ-6 Type A skeleton | T1 | at-spec | INIT→CHECK→RESPOND→ESCALATE pipeline | — |
| Δ-12 Artifact taxonomy | T0 | at-spec | — | — |
| Δ-15 Elicitation | T0 | at-spec | closure_contract drafted in M1 brief | — |
| Δ-18 Delivery Loop | T1 | not-applicable | human-paste; no orchestrator adopted | reconsider at M3 |
| role-skill-model | T0 | at-spec | no role skills mounted yet | — |

(Rows for Δs not listed are `at-spec` by default for this minimal example.)

# Divergences (suggested-default overrides — hard requirements are never divergent)

| Item | Default | Our value | Rationale |
|---|---|---|---|
| Bad-case manual review cadence | every milestone close | every sub-sprint close | small suite; cheap to review every sprint; catches drift earlier |
| `cell_size_target` (handoff §0) | 500 chars | 350 chars | solo project; terse cells keep cold-start fast |

# Hard-requirement conformance (must be at-spec; cannot be divergent)

- §1.7 forbidden list (incl. §1.7-A..E): at-spec.
- §3.4 5-role boundary invariants (incl. #6 intra-role): at-spec.
- §3.6 calibration gate: not-applicable (no autonomous Acceptance).

---

End of adoption state.
