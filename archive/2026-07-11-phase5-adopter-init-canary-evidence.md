---
name: 2026-07-11-phase5-adopter-init-canary-evidence
doc_category: intermediate
status: evidence (Phase-5 Cluster 4)
created: 2026-07-11
base_commit: f6d2730 (origin/main HEAD = PR #15 merge)
design: archive/2026-07-11-phase5-adopter-bootstrap-design.md §6
---

# Phase-5 adopter_init.py — canary evidence

Done-evidence for the design's §6 acceptance bar: a scratch adopter reaches four-validator
GREEN in one command; a brownfield adopter is scaffolded non-destructively; the live
reachability probe is env-gated. All canaries are automated tests under
`engine-kit/tools/tests/test_adopter_init.py`; the scratch + brownfield canaries run in the
NORMAL suite (fully offline, deterministic), and the live-probe canary is env-gated.

## §1 Scratch-repo canary (offline, normal suite) — the primary done-evidence
`test_adopter_init.py::ScaffoldGreenTests::test_scratch_dir_all_four_validators_green`:
an EMPTY `tmp_path` dest → `adopter_init.main([dest, --answers examples/adopter-init-canary/answers.json])`
→ **exit 0**, then each of the four validators is INDEPENDENTLY re-run against the produced tree
and asserted green:

- `charter_validator.validate_file(dest/charter.yaml).ok`
- `adopter_wiring_validator.validate_root(dest).ok` (targets include `cursor` — the canary binds
  `dev` to the cursor harness, exercising the emitted `.cursor/rules` + the C1 FAIL validator on
  the happy path)
- `control_plane_validator.validate_root(dest).ok`
- `adoption_status.validate_adoption(dest).ok`

Also asserted: the framework is mounted under `dest/aidazi/` (NOT the dest root, so
`is_framework_repo(dest)` stays False), `aidazi/engine-kit/orchestrator/driver.py` resolves, and
`aidazi/skills/` is present. Manual reproduction:

```bash
python engine-kit/tools/adopter_init.py /tmp/acme --answers examples/adopter-init-canary/answers.json
#   [PASS] charter_validator   [PASS] adopter_wiring_validator
#   [PASS] control_plane_validator   [PASS] adoption_status
#   All four validators GREEN.
```

## §2 Brownfield canary (offline, normal suite)
`test_adopter_init.py::BrownfieldCanaryTests::test_brownfield_force_is_green_and_non_destructive`:
a pre-existing repo (`src/app.py`, `README.md`, a partial `.gitignore` = `*.pyc` / `build/`) →
`adopter_init --force` → **exit 0** (four validators green over the brownfield repo), and:

- `src/app.py` and `README.md` are byte-unchanged (pre-existing files preserved).
- the existing `.gitignore` lines (`*.pyc`, `build/`) are PRESERVED and the required aidazi
  patterns (`.runs/`, `.env.local`, `.orchestrator/`) are MERGED in (not overwritten).

Idempotency (`test_idempotent_force_rerun_stays_green_no_clobber`,
`test_force_preserves_human_edited_brief`): a re-run with `--force` stays green and a
human-edited `charter.yaml` / signed brief is NOT clobbered without `--overwrite`.

## §3 Live-probe canary (ENV-GATED; skipped offline)
`test_adopter_init.py::LiveProbeCanaryTests::test_live_probe_reachable_and_bad_key_warn` — skipped
unless `AIDAZI_E2E_ADOPTER_INIT_LIVE=1` (+ `AIDAZI_E2E_HEADLESS_ENDPOINT` /
`AIDAZI_E2E_HEADLESS_KEY_ENV`), per [[real-cli-env-gate-rule]]. When enabled it drives the REAL
`--probe live` path against a headless endpoint: a reachable-key arm asserts a `reachable` row,
and a deliberately-bad-key arm asserts a `warn` row (advisory, never a crash). The env-gate
itself (I4 — no network without `AIDAZI_ADOPTER_INIT_LIVE_PROBE=1`) is proven OFFLINE by
`ReachabilityProbeTests::test_live_without_env_makes_no_network_call` (mocked `urlopen`,
`assert_not_called`) plus the with-env / dead-key paths (`test_live_with_env_probes_headless`,
`test_live_dead_key_is_warn_not_crash`, `test_live_unset_key_is_warn_without_request`).

This session did NOT run the real live-probe arm (no real headless endpoint/key provisioned);
it stays env-gated for a machine that has one, exactly like the Phase-1 real-campaign canary.

## §4 Suite status at Cluster 4
Full `cd engine-kit && python3.12 -m pytest`: **all green except the 1 pre-existing README red**
(`test_no_current_doc_teaches_full_canonical_as_always_load`, on the root `README.md` — NEVER
fixed here). The `adopter_init` suite is 32 passed / 1 env-gated skip. ONBOARDING.md gained an
up-front "Fast path" pointer to the tool; the numbered Steps 0–9 remain the manual reference
(doc-reconciliation lockstep intact — the fast-path prose names no canonical governance doc as
always-load).
