# OW-AUTO implementation — final pre-push canary (deterministic, scratch-only)

- **Date:** 2026-07-01
- **Scope:** DETERMINISTIC engine-level canary of the shipped impl (`92e5333`) on SCRATCH copies of real adopter data. No billable LLM; **no real adopter state mutated** (airplat's real `charter.yaml` / `campaign-plan.json` / `.orchestrator` / `.runs` untouched; airecruiter-map was empty → greenfield init done in a scratch temp dir). Probe harness: `/tmp/canary/canary_probe.py` (imports `campaign` + `scope_report` from a given aidazi path; base comparison uses a throwaway `b2e794b` worktree).
- **Result:** BOTH parts PASS; every assertion consistent with the approved design (`archive/2026-07-01-acceptance-auto-proposal-and-init-experience-design.md` §0.0 locked semantics). No code changed for/after the canary.

## Part 1 — fresh-adopter initialization (greenfield scratch; target airecruiter-map, which was empty)

Simulates the onboarding Step 4b/6 default-generate + Research proposal + Deliver auto-derive END STATE, then runs the shipped engine:

| Check | Result |
|---|---|
| default-generated `docs/requirements-ledger.json` schema-valid (`load_and_validate_ledger`) | ✅ `ledger_schema_valid: true` |
| every REQ carries a proposed `surface_status` + `surface_confidence` | ✅ `ledger_has_proposals: true` |
| dispositions all `pending` (sentinel only, no agent-decided) | ✅ `ledger_dispositions_all_pending: true` |
| Deliver plan (auto covers_req_ids + browser_e2e for user_facing) signs clean | ✅ `plan_self_consistent_signs: []` |
| a user_facing REQ left on `static` is REFUSED (⇒ browser_e2e derivation) | ✅ `static_on_user_facing_refused: true` |
| surface binds only at sign-off via covered_req_surfaces | ✅ `binds_only_at_signoff: {REQ-101: user_facing}` |
| proposal NOT authoritative pre-signoff: `surface_status` confirmed vs proposed ⇒ SAME signed hash | ✅ `confirmed_flag_not_authoritative: true` |

## Part 2 — airplat compatibility (scratch copies of the REAL charter + plan)

airplat real state: `signed_by_human: true`, NO signoff block, NO milestone `covers_req_ids`, `requirements: None`, no ledger file (ledger-less legacy adopter).

**2a — dormant / additive (base `b2e794b` vs impl `92e5333`, no ledger): BYTE-IDENTICAL**
- `signed_scope_hash = 8ebb2db529f6bbdabb2113c91e839acc3a7ba8a2eddc0b95914e6c4a866eacef` (both)
- `signoff_status_no_ledger = signed` (both); `mandatory_e2e_violations = []` (both). ⇒ OW-AUTO is dormant for a ledger-less adopter, byte-identical old behavior.

**2b — activate OW-M3 via a scratch proposal ledger (impl)**
- user_facing REQ on `static` ⇒ `violations = [{kind: downgrade, milestone: M1-job-search-loop, req_ids: [REQ-CANARY-UF], resolved_mode: static}]` (OW-M3 fires).
- same milestone on `browser_e2e` ⇒ `violations = []`, `signoff_status = signed`, `covered_req_surfaces = {REQ-CANARY-UF: user_facing}` bound.

**2c — advisory-flip / no new pause / no re-sign (impl)**
- `signed_hash_stable_under_adv_flip: true`; `signoff_status_adv_flip: signed` (no re-sign).
- `projected_sidecar_stable_under_adv_flip: true` (⇒ acceptance_input_hash stable); `gap_report_stable_under_adv_flip: true`.
- surface VALUE flip: `signed_hash_changes_under_surface_flip: true`; `signoff_status_surface_flip: stale`; `projected_sidecar_changes_under_surface_flip: true`.
- authority carve-out: `agent_may_seed_pending: true`, `agent_may_not_seed_accepted: true`.

## Honest scope

Engine-level + data-shape proof (deterministic). The *agent behaviors* (Research emitting proposals, Deliver auto-filling `covers_req_ids`) are validated at the mechanism/end-state level — the role-card prose that drives them is Codex-reviewed (R3 APPROVE), not exercised via a live agent spawn here. A live-LLM behavioral walk would be a separate, billable step.
