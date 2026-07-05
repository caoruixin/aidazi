# Phase-5 REAL managed external_test_runner canary fixture

An aidazi-owned, disposable fixture adopter that drives the framework's **REAL** managed
`external_test_runner` path end-to-end with a **REAL headless chromium** browser — the env-gated
capability offline CI cannot exercise. The harness is `engine-kit/orchestrator/tests/test_e2e_real_canary.py`.

## What it exercises (design §9 non-regression canaries)

The harness copies `app/server.py` + `e2e/runner.cjs` into a git-repo scratch workspace, signs a
campaign plan, and drives the driver's **normal** STATE_E2E_PENDING route:

```
managed app start (readiness poll)
 → real Node/Playwright runner (REAL chromium: real trace.zip + screenshots + exit code)
 → framework-generated run-provenance.json + audit-spine start/end window
 → per-criterion executor_status mapping (@crit:<id> tags)
 → §1.7-G deterministic failure brief → bounded autonomous in-envelope Dev fix
 → FULL managed rerun (fresh run_id + fresh provenance) → re-judge
 → the #9 advisory_acceptance_pass_signoff HUMAN gate (never auto-ships)
```

| Canary | Proves |
|---|---|
| 1 real managed happy path | real chromium run → provenance verified → judged pass → #9 human gate |
| 2 fail → remediation | `result_ok` fails on the real BROKEN page → §1.7-G autonomously fixes in-envelope → real rerun passes → re-judge → #9 |
| 3 dry-run + tampered rejection | a `local_http` manifest cannot route; a tampered run-provenance is re-run, never trusted |
| 4 unmapped + runner-contract fault | a signed criterion with no bound test ⇒ pre-publication HALT; a runner that cannot run ⇒ fail-closed |
| 5 no-progress halt | a §1.7-G round that makes no progress HALTs + escalates; never loops, never auto-ships |
| 6 crash-resume idempotency | reconcile trusts committed framework-owned evidence (same nonce/pid) — no duplicate run |
| 7 final ship human-authorized | a passing verdict halts at #9 (M3 stays advisory) |

## Discipline (Phase-5 boundaries)

- **No executor internals, no injected manifests, no mocked authoritative provenance.**
  `run-provenance.json` is framework-generated from the REAL subprocess and verified fail-closed.
- **Autonomous:** the framework starts/stops the app, runs the runner, captures + verifies evidence,
  remediates, and re-runs — no human command, no manual environment startup, no artifact/manifest
  handling, no manual resume on the routine path.
- The only DETERMINISTIC seams a canary supplies are the Dev "fix" (an in-envelope file edit standing
  in for a Dev agent's code change) and the Acceptance judge (which reads the REAL committed evidence).
- **AirPlat and all adopter repos are untouched** — the canary is a scratch git workspace.

## Running

```bash
cd engine-kit
AIDAZI_E2E_EXTERNAL_RUNNER=1 python3.12 -m pytest orchestrator/tests/test_e2e_real_canary.py -v
```

The harness self-locates a cached `playwright` whose chromium build is installed; absent that (or
the env flag), the whole canary **skips** — it never runs in offline CI.
