# engine-kit/scheduling — schedule entrypoint (P5-B)

The aidazi outer loop is framework-owned **standalone Python** (`engine-kit/orchestrator/driver.py`). Scheduling it is **plain cron / CI** — explicitly **NOT** any harness's own scheduler. The master plan fixes this:

> scheduling | framework | **plain cron / CI (not ScheduleWakeup)**

So this package is a thin, harness-agnostic *outer wrapper* a cron job or CI workflow invokes to run **one** delivery loop end-to-end. It is NOT part of the deterministic kernel — the only wall-clock read is the injected production clock in `main`; the kernel stays pure because the clock is injected (tests inject a deterministic one).

## What it does

`run_loop.py`:

```
load charter → build adapters → construct Driver → run → verify audit chain → summarize → exit code
```

Two scheduled triggers via `--mode` (a label recorded in the `loop_start` audit context; the run mechanics are identical):

- `overnight_autoloop` — an overnight Type-A Auto Loop run.
- `milestone_delivery` — a milestone Delivery Loop run.

Exit code is `0` only on a clean terminal state (`advance`/`done`) **and** a verifying audit chain; non-zero otherwise (so cron/CI surfaces failures).

## Real vs mock adapters (safe by default)

- **Default (dry-run):** `build_adapters(charter, allow_real=False)` builds a `MockAdapter` per role with a clean-pass canned verdict set. This runs the full P2 happy path **offline** — a smoke test you can schedule safely.
- **`--allow-real`:** builds real adapters from `ADAPTER_REGISTRY` for each role's harness. Those still refuse to touch the network/subprocess **unless** `AIDAZI_ALLOW_REAL_ADAPTER=1` (the adapters' own gate). So a real scheduled run needs BOTH `--allow-real` AND that env var.

Run artifacts (`state.json`, `docs/checkpoints/`, `.orchestrator/audit/`) go to a **run dir that defaults to `<repo>/.runs/<loop_id>`** — inside the repo so you can tail the live ledger/transcripts without hunting through `/tmp`, but **gitignored** (`.runs/`) so a loop's own writes never enter the delivered diff. `--run-dir` overrides with any explicit path; `--campaign-run-dir` defaults to `<repo>/.runs/campaign-<id>`.

## Usage

```bash
# offline dry-run (no network) — a safe scheduled smoke test
# (omit --run-dir to use the default <repo>/.runs/<loop_id>/)
python engine-kit/scheduling/run_loop.py \
  --charter path/to/charter.yaml \
  --mode overnight_autoloop \
  --repo-dir /srv/app

# real run (operator opts in to I/O)
AIDAZI_ALLOW_REAL_ADAPTER=1 python engine-kit/scheduling/run_loop.py \
  --charter path/to/charter.yaml \
  --mode milestone_delivery \
  --allow-real \
  --repo-dir /srv/app           # enables Loop Ingress; default run dir = /srv/app/.runs/<loop_id>/
  # --memory-root /srv/app/memory  # optional: enable Loop Memory (OFF by default; or set
  #                                 # charter.memory.enabled:true — --memory-root overrides)
```

See `examples/crontab.example` and `examples/github-actions-loop.yml` for wiring.

## Why not ScheduleWakeup / a harness scheduler?

The framework must be **harness- and model-agnostic** (ADR-0001): the deterministic outer loop and its scheduling cannot depend on any one harness's orchestration. Plain cron / CI is universal, inspectable, and adopter-owned — consistent with the "framework-owned standalone driver" decision.
