# engine-kit/tools — framework-dev helpers

Not part of the Quick-Fix runtime or the orchestrator role-execution path. These are helpers
used while **developing** the framework.

## review_runner — bounded headless review runner

A safe wrapper for ad-hoc headless reviewer calls (`codex exec`, a Kimi CLI, …) made during
framework development. It exists because two stall modes have bitten ad-hoc calls:

1. **stdin block** — `codex exec` with no positional prompt reads instructions from stdin and
   waits for EOF; "if stdin is piped and a prompt is also provided, stdin is appended as a
   `<stdin>` block." Launched in the background with stdin left open, it hangs forever.
2. **gateway/API hang** — the provider accepts the request but never streams a response, and
   `codex exec` has **no `--timeout` flag**, so it waits unbounded.

The Quick-Fix adapter (`engine-kit/quickfix/adapters/base.py`) already handles both for the QF
lane. This runner gives the **same** guarantees to ad-hoc dev-review calls as a **standalone**
tool — it reuses the verified PATTERN (`Popen` + `start_new_session` + process-GROUP kill) but
does **not** import or depend on the Quick-Fix runtime contract.

### Guarantees
- structured `argv`, `shell=False`; stdin fed via write-then-close or `DEVNULL` (the child can
  never block on stdin; no open parent tty/pipe is inherited);
- child in its own session/group (`start_new_session=True`) → a timeout kills the WHOLE group;
- a **hard wall-clock timeout** is the final boundary (the CLI under test has none);
- with `--json` (codex JSONL events) inactivity is detected, but inactivity is a **soft warning
  only** — it never kills; only the hard timeout kills;
- **bounded attempts** (default 2, hard cap 2); the same path is never retried beyond that;
- every attempt is recorded (the first failure is never hidden);
- a **mandatory** gate that fails twice returns `stop_and_surface` (exit 3) — never silently
  skipped; an alternative reviewer runs only if explicitly pre-allowed, and is recorded;
- env / tokens / credentials are **never** logged (argv, versions, exit, timing, captured
  stdout/stderr only).

### CLI

```bash
python engine-kit/tools/review_runner.py \
  --timeout 900 [--inactivity-warn 120] [--attempts 2] [--mandatory] \
  [--prompt-file PROMPT.md | --no-stdin] [--capture-dir DIR] \
  [--allow-alternative] \
  -- codex exec --json -o /tmp/verdict.txt -m gpt-5.5 -c model_reasoning_effort=xhigh \
     -s read-only --skip-git-repo-check
  # optional pre-allowed alternative reviewer:
  #   ... --allow-alternative -- <primary argv> -- <alternative argv>
```

The reviewer command follows the first `--`. The prompt (`--prompt-file`) is delivered on the
child's stdin and stdin is then **closed**. Exit codes: `0` success/substituted, `1` failed,
`3` mandatory-gate `stop_and_surface`.

### Library

```python
from review_runner import run_bounded
result = run_bounded(argv, prompt=text, hard_timeout_s=900, inactivity_warn_s=120,
                     attempts=2, mandatory=True)
if not result.ok:
    ...  # result.status in {"failed", "stop_and_surface"}; surface, don't skip a mandatory gate
```

### Real-CLI behavior (verified 2026-06-22, codex-cli 0.134.0)
- Success: a `codex exec --json` call returns the verdict via `-o`; stdin-fed prompt, exit 0.
- Forced 3s hard timeout on a long codex turn: killed at ~3.0s per attempt, two bounded
  attempts, **no surviving process group** — proving the watchdog bounds a real codex call
  (the same path that can hang for hours via the gateway). Inactivity warnings fired but did
  not kill.

Kimi reuses the same generic timeout/stdin hygiene; no Kimi-specific stall root cause is
claimed.
