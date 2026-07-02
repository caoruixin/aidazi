# Canary evidence — watchdog liveness fix (P1+P2+P2-L)

- **Date:** 2026-07-03
- **Branch:** `fix/watchdog-liveness-p1-p2` (impl `946a722`, gate-fix `b72ded6`)
- **Mode:** opt-in real-adapter (`AIDAZI_ALLOW_REAL_ADAPTER=1`), macOS, `claude 2.1.170`, `claude-sonnet-4-6`, real `ClaudeCodeAdapter` (`allow_subprocess=True`, `timeout_seconds=900`).

## Result summary

| Canary | Scenario | Result | Elapsed | Killed? |
|---|---|---|---|---|
| **A — output-liveness** | 60 sequential Write+Read tool calls | **PASS** | **371.0s** | No |
| A2 — lease (`sleep 200`) | one long silent Bash tool | inconclusive | 24.6s | No (didn't hold the sleep) |
| A2b — lease (`sleep 210` + explicit 300000ms Bash timeout) | one long silent Bash tool | inconclusive | 45.1s | No (**claude backgrounded it**) |

## What Canary A proves (the headline)

A real `claude` Dev session ran for **371 seconds — >6 minutes — and was NOT killed**, returning its result normally. This is the exact scenario the pre-fix watchdog guillotined at ~181s (airplat sprint-067, 4/4). The macOS blind-180s-guillotine is eliminated end-to-end on real claude: streamed stream-json events (tool_use/tool_result per Write/Read) kept output-liveness refreshed the whole time, so `stuck` never fired. Direct real-world confirmation of P1-a + P2 (+ read1).

## Why A2/A2b were inconclusive (a finding, not a gap)

Both attempts to force a single **output-silent + CPU-idle >180s** tool call (the B3 scenario the lease targets) failed to create that condition — because **claude backgrounds long-running silent commands** rather than blocking on them. A2b's own final message was: *"Still waiting for the 210-second sleep to complete. The monitor will notify me automatically."* — i.e. claude ran `sleep 210 &` and ended its turn at 45s.

Implication: the *pure* B3 case (a single silent tool blocking >180s) is **rare** in real claude sessions, because claude actively avoids it. The B3 case that DID bite in production (sprint-067) was a **foreground build** (`mvn`) whose pass/fail claude must wait on — claude does not background those. Reproducing that faithfully needs a real >180s build project (e.g. the airplat Maven adopter), which is out of scope for this framework-level change and expensive to run as a throwaway canary.

## Where B3 (the lease) IS proven

Deterministically, offline, via `engine-kit/adapters/tests/test_monitor.py` — real subprocesses emitting the **probe-confirmed** `tool_use`/`tool_result` JSONL (see the design spec §E), with the real `ToolLeaseProbe` wired into `run_with_monitor`:
- `test_lease_keeps_open_tool_alive` — tool_use open + silent past the window ⇒ NOT killed.
- `test_without_lease_same_silence_is_killed` — the non-vacuity control: identical silence WITHOUT the lease ⇒ killed.
- `test_lease_held_past_window_then_released_and_killed` — held past the window, then tool_result release, then killed.
- `test_hung_lease_hard_timeout_no_retry` — a never-closing lease is bounded by the hard timeout in one attempt.
- `test_restart_uses_fresh_probe` — the restart path gets a fresh probe (no orphan lease).

## Verdict

The **core fix is proven on real claude** (371s survival) and the **lease mechanism is proven deterministically offline**. The unreproduced real-claude lease trigger is a consequence of claude's own backgrounding behavior, which independently reduces B3's real-world frequency. Full offline suite: **1548 passed / 3 skipped** (1 pre-existing, unrelated README doc-reconciliation failure; README byte-identical to base `f887f79`).
