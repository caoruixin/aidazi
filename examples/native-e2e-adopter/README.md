# Worked example — native managed E2E adopter config (Phase-4, design §7)

A **complete, runnable** native-E2E configuration for a user-facing requirement, exactly as the
onboarding proposal generator (`engine-kit/tools/e2e_config_proposal.py`) drafts it. This is the
worked example the design §7 (R5) requires: onboarding emits a reviewable proposal that is
**runnable after human authorization**, never an empty skeleton the human must fill in.

## What's here

| File | Role |
|---|---|
| `proposal.json` | The **advisory** native-E2E config proposal (generated). `proposal_status: proposed`, `proposal_confidence: high`. Complete + leak-free (`e2e_config_proposal.validate_proposal(...) == []`). Binds only on whole-proposal human authorization. |
| `frontend/e2e/acceptance.spec.ts` | The adopter's real Playwright spec the **managed** `external_test_runner` runs. Each test title carries `@crit:<criterion_id>`. |
| `docs/research-briefs/M1-functional-checklist.json` | The Research-owned **signed** functional checklist (the criteria; frozen at Gate-1). |

## The autonomous path this configures

```
onboarding proposal (this dir)
  → charter.tooling.e2e (managed external_test_runner)   # framework starts app + runs runner
  → framework-owned run-provenance.json + audit-spine window   # fail-closed, hand-authored dirs refused
  → per-criterion executor_status (pass/fail/error/skipped)     # framework criterion mapping
  → §1.7-G deterministic failure brief on fail/error            # facts-only trigger
  → bounded in-envelope autonomous Dev fix                      # under the SIGNED e2e_remediation budget
  → diagnostic --grep @crit:<id> probe (diagnostic only)        # never authoritative
  → FULL managed rerun → rejudge                                # the authoritative re-judge
  → advisory Acceptance verdict → the #9 HUMAN ship gate        # ship stays human-authorized
```

No human runs the runner, starts/stops the environment, uploads evidence, or hand-authors a
manifest/provenance on the routine path. Human involvement is reserved for authority/scope/budget
changes, a missing human-only credential, a runner-contract/integrity fault, a no-progress/regression
ceiling, and the final advisory ship/reject.

## To adopt (after human authorization)

1. Review `proposal.json`. On authorization, paste `proposal.tooling.e2e` into
   `charter.tooling.e2e` and `proposal.tooling.acceptance.functional` into
   `charter.tooling.acceptance.functional`; set `charter.autonomy.level` +
   `charter.autonomy.e2e_remediation` from `proposal.autonomy`; add
   `proposal.required_framework_capabilities` to `charter.required_framework_capabilities`.
2. Land the signed functional checklist at the `checklist_path`.
3. Set the NAMED secret env vars (`AIJP_TEST_USER`, `AIJP_TEST_PASS`) in a gitignored `.env.local`
   — never inline them in the charter/spec.
4. Sign the campaign plan (`run_loop --sign-plan`). Preflight will refuse if the pinned aidazi lacks
   a `required_framework_capabilities` entry (naming the missing capability + upgrade action).

## Secrets

`secret_refs` are **NAMED references only** (`env:AIJP_TEST_USER`, …). A literal secret anywhere in
the proposal is rejected by `e2e_config_proposal.secret_leak_violations`. An **unresolved** human-only
credential is an authority pause (design §8, R4-d) — never a routine halt.
