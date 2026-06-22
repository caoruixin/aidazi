# Follow-up — wire the shared charter validator into the Driver boundary

**Status:** OPEN (deferred 2026-06-21) · **Priority:** low (consolidation, not a live defect)
**Origin:** [whack-a-mole hardening closure](2026-06-21-whack-a-mole-hardening-closure.md) §6

## Observation

The framework has a genuinely shared, semantic charter validator
(`engine-kit/validators/charter_validator.py` — the 9 default MANDATORY_CHECKPOINTS,
acceptance-on-fix_required, network-access invariants), but its **only** non-test
caller is the scheduler: `engine-kit/scheduling/run_loop.py::enforce_charter_for_real_run`.
The Driver loads the charter **leniently** (`driver.py`: "Charter loading (LENIENT plain
YAML — NOT validated against the schema …)") and runs its own narrower verdict-schema
validation. So the shared validator and the Driver's lenient loader are **two parallel
truths**: the centralized invariants are authoritative only on the scheduler path.

## Why it is NOT a live defect

`run_loop.enforce_charter_for_real_run` BLOCKS any real (`--allow-real`) run on a
blocking charter schema error **before any adapter is built** (exit 2 /
`CharterValidationError`). A Driver invoked through the normal entry point is already
gated. The gap is only a Driver invoked **directly** (not via `run_loop`), which would
skip the centralized invariants.

## Proposed change (when picked up)

Have the Driver consult `charter_validator` at construction (at minimum surface a
warning via the already-exported `charter_validation_report`), so the shared validator
is authoritative everywhere rather than only on the scheduler path. Consolidate to
"the Driver always consults `charter_validator`" instead of maintaining the lenient
loader as a second truth.

## Explicitly out of scope here

Deferred from the 2026-06-21 hardening round by owner instruction ("shared charter
validator 本轮先不要加入"). Recorded standalone so it is not lost. No code change in
commits `7023307` / `f1f0e9d`.
