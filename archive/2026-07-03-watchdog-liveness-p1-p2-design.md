# Design Spec — Watchdog Liveness Fix (P1 + P2 + P2-L)

- **Date:** 2026-07-03
- **Base commit:** `f887f79` (origin/main HEAD)
- **Branch (to be created after design APPROVE):** `fix/watchdog-liveness-p1-p2`
- **Status:** DESIGN R4 — R3's 1 blocking (AC-11 split + probe factory) + 3 non-blocking fixed; awaiting R4 gate
- **Scope lock:** P1 + P2 (+ P2-L, the active-tool lease, within P2 scope). P3 (tunable thresholds), P4 (restart policy), P5 (nesting env) remain OUT.
- **Normative sources:** `docs/adr/ADR-0001-engine-substrate.md`; `process/delivery-loop.md §4.2.7`. Spec wins on conflict.

## R. Gate history & revisions

- **R1 = REVISE** (3 blocking) — all fixed: B1 vacuous cpu test → idle-parent+busy-child (AC-5-C); B2 CPU-busy hang → hard-timeout ceiling (AC-6b); B3 false-kill of quiet wait → **closed** via P2-L.
- **R2 = REVISE** (2 blocking) — both fixed: B1 "hard timeout bounds the silent wait" was wrong (killed at ~180s silence window); B2 `cpu_unknown ≥300s` grace is illusory (idle_for trips at 180s). Both mooted/corrected below.
- **User directive on B3:** close it via an explicit, bounded **active-tool lease** (P2-L) — event-anchored, never PID-anchored, hard-timeout-bounded, no orphan recovery. Not "accept residual," not per-role thresholds, not a timeout bump.
- **R3 = REVISE** (1 blocking) — fixed here: **B1** AC-11 conflated two paths (a hung lease hits `TimeoutExpired`, which does NOT restart; the restart path is `_StuckOnce`). Split into **AC-11a** (hung lease ⇒ hard timeout, no retry) and **AC-11b** (per-attempt probe freshness on the restart path), made structural via a **probe factory** (fresh probe per attempt). NB1 (narrow the `idle_for==elapsed` claim), NB2 (Canary-A2 proves the lease, not AC-5-C), NB3 (probe reads stdout only; refresh `last_output` before `observe` — no stale-silence race) all applied.

## E. Empirical grounding (live `claude 2.1.170`, `--output-format stream-json --verbose`)

- **Tool lifecycle (Probe 1, Write):** `{"type":"assistant",…"content":[{"type":"tool_use","id":"toolu_…","name":"Write"}]}` opens; `{"type":"user",…"content":[{"type":"tool_result","tool_use_id":"toolu_…","is_error":<bool|null>}]}` closes; terminal `{"type":"result","subtype":"success","result":"…","is_error":false}`. Also `system/{hook_started,hook_response,init}`, `system/thinking_tokens` (streamed during thinking), `assistant[thinking]`, `rate_limit_event`.
- **Long tool timing (Probe 2, Bash `sleep 8 && echo`):** `tool_use`(Bash)@+3.2s and matching `tool_result`@+11.9s bracket the tool; within the span output arrived only sporadically (Δ3.7s, Δ5.0s) and a post-tool model turn was silent Δ10.6s ⇒ **no guaranteed sub-180s output cadence** ⇒ the lease is required, not redundant. Bash ran under `acceptEdits`+`--allowed-tools Bash` with no prompt (⇒ real long-build canary feasible).

Lease keys confirmed: `tool_use.id` (assistant) ↔ `tool_result.tool_use_id` (user); `is_error==true` = tool_error.

---

## 0. Confirmed root cause (evidenced, 2026-07-02)

sprint-067 Dev spawns killed at ~181.3s, 4/4, `reason=no_output_no_cpu_sample`, `cpu_seconds=null`, `seconds_since_output==elapsed`; `ps.txt` showed the process alive/sleeping (`Ss`) with valid CPU `0:05.62` — the monitor's reading was broken. Two defects → a **blind 180s guillotine on macOS**:

1. **macOS CPU-parse bug** — `_parse_ps_time` (monitor.py:262-281) does `int(p)` per colon-part; macOS `ps -o time=` is fractional `M:SS.ss` → `int("05.62")` raises → `None` every poll (verified live) ⇒ `cpu_unknown` always True, `idle_for == elapsed`.
2. **Buffered output** — `--output-format json` (claude_code.py:119) emits one final envelope ⇒ `no_output_for == elapsed`.

Both dead ⇒ `stuck` (monitor.py:198-204) ≈ `elapsed >= 180`; restart re-kills → `AgentStuckError` → `AdapterError` → `gate_hard_fail`. Nesting-independent.

**Design principle (non-negotiable):** a session showing **any** of {output-liveness (O), group-CPU-liveness (C), an in-flight active-tool lease (L)} within its window is never silence-killed; a session showing **none** for the window is still terminated on the **unchanged** thresholds. The hard `timeout_seconds` remains the ceiling for the undecidable cases (CPU-busy hang; slow/hung in-flight tool). We do **not** raise thresholds, bump the hard timeout, add a bypass, sustain liveness from bare PID existence, or disable the watchdog.

---

## 1. Scope

| Item | In/Out | Summary |
|---|---|---|
| **P1-a** | IN | `_parse_ps_time` fractional macOS CPU time; Linux compat. |
| **P1-b** | IN (R1-ratified) | CPU signal reflects the spawned **process group** (covers CPU-bound in-session builds). |
| **P2** | IN | `stream-json --verbose`; `read1` refreshes output-liveness; JSONL parser → terminal result/error/exit. |
| **P2-L** | IN (user directive) | **Active-tool lease** from `tool_use`/`tool_result` events; while active, suppress the silence-kill (still hard-timeout-bounded). Closes B3. |
| P3 / P4 / P5 | OUT | thresholds `180/180/300`, `max_restarts=1`, nesting env unchanged. |

P1-b + P2-L *complete liveness signals* (not thresholds/restart/env): P1-b fixes *what CPU we measure*; P2-L adds *what "a tool is legitimately running" looks like* — the only reliable signal for a long silent tool (Probe 2).

---

## 2. P1-a — `_parse_ps_time` fractional-seconds fix

Parse the **last** colon-group as `float`, preceding groups as `int`, optional `D-` prefix; return `float`.

| Input | → sec | | Input | → sec |
|---|---|---|---|---|
| `05.62`/`0.04` | 5.62/0.04 | | `03:01` (Linux) | 181.0 |
| `0:05.62` | 5.62 | | `01:02:03` | 3723.0 |
| `12:05.62` | 725.62 | | `3-01:02:03` | 262923.0 |
| `1:02:03.50` | 3723.50 | | `2-01:02:03.50` | 176523.50 |
| ``/`garbage`/`1:2:3:4` | `None` | | | |

Algorithm: strip; split optional days on `-`; split rest on `:` (1–3 groups); `float()` last, `int()` rest; `days*86400+h*3600+m*60+s`; any error → `None`. **AC-1.**

---

## 3. P1-b — process-group CPU aggregation

`setsid` ⇒ `pgid == proc.pid`; descendants inherit it (setsid-escapees rare, documented).
- `_group_cpu_seconds(pgid)`: `ps -Ao pgid=,time=` (macOS+Linux), sum `_parse_ps_time(time)` over matching pgid; `None` on failure/no rows.
- Monitor uses `_group_cpu_seconds(os.getpgid(proc.pid))`; **falls back** to fixed `_cpu_seconds(proc.pid)`. One `ps -Ao`/poll (negligible). Group ⊇ parent ⇒ strictly more accurate; genuine-stuck still detected. **AC-2, AC-5-C.**

---

## 4. P2 — stream-json consumption

### 4.1 argv
`--output-format json` → `--output-format stream-json` **+ `--verbose`** (confirmed required). Prompt on stdin; other flags unchanged. `--include-partial-messages` NOT enabled (baseline events + `thinking_tokens` + group-CPU + lease suffice; OQ-2 lever only).

### 4.2 read granularity (`_read_stream`, monitor.py:233)
`read(4096)` → `read1(4096)`: returns after one underlying read so each event promptly refreshes `last_output`. Final bytes identical; binary `BufferedReader` has `read1`. Uniform, no regression.

### 4.3 parser (`_final_result_from_stream`, replaces `_envelope_result`)
Strict line-by-line JSONL: skip blanks; each line = one object; a non-parsing line is an ERROR **except** a final truncation fragment (no trailing newline) when a terminal `result` was already seen. Terminal = last `type=="result"`; success → return `result` → unchanged `_extract_artifact`/`_extract_verdict`; `is_error`/`error_*` → `AdapterError`; no terminal → `AdapterError`; single-object back-compat; `returncode != 0` → `AdapterError`. Downstream helpers unchanged. Docstring json→stream-json.

### 4.4 P2-L — active-tool lease (closes B3)
An adapter-owned, **stateful** probe, supplied by `claude_code` to `run_with_monitor` as a **factory** (`liveness_probe_factory: Callable[[], Probe] | None`, default `None` ⇒ other adapters unchanged). `_run_once` calls the factory at the **start of each attempt**, so every attempt gets a FRESH probe — orphan-lease recovery is impossible by construction (R3-B1/AC-11b).
- **`ToolLeaseProbe.observe(line)`** — per complete stream-json line: an `assistant` event with a `tool_use` block ADDS its `id` to `open_ids` (records `name`); a `user` event with a `tool_result` block DISCARDS the matching `tool_use_id` (regardless of `is_error` — a tool_error still *closes*); the terminal `result` event CLEARS all. A `tool_result` for an unknown id, or a malformed/non-JSON line → opens nothing / never *extends* a lease.
- **`.active()`** = `bool(open_ids)`.
- **Monitor integration:** with a factory, `_run_once` builds a fresh probe; `_read_stream` (a) refreshes `last_output["t"]` for the chunk **FIRST**, then (b) assembles complete lines at the byte level (split on the newline byte — a clean boundary, no multibyte split) and calls `probe.observe(line)`. Ordering (a)→(b) means a lease-*closing* `tool_result` line has already refreshed output-liveness, so clearing the lease can never expose a stale-silence window (R3-NB3). The probe observes **stdout only** (stream-json is on stdout; stderr still feeds output-liveness but not the lease). Raw-byte accumulation for the final parse is unchanged. Poll-loop predicate:
  ```
  stuck = base_stuck AND NOT (probe is not None AND probe.active())
  ```
  `base_stuck` is the **unchanged** §5 predicate; the hard-timeout branch (monitor.py:173-184) is **untouched**.
- **Bounds & release:** the lease suppresses the *silence* kill only while a tool is in flight. A hung in-flight tool (never-closing lease) is bounded by the hard `timeout_seconds` → `TimeoutExpired`, which `run_with_monitor` raises **without** restart (only `_StuckOnce` restarts) — a single-attempt hard-timeout kill (AC-11a). Process exit ends the poll loop (leases moot). Liveness is NEVER sustained by child-PID existence — only by an observed `tool_use` without its matching `tool_result`.

---

## 5. Watchdog semantics (unchanged thresholds; completed signals)

Base predicate (monitor.py:198-204) **unchanged**:
```
base_stuck = (no_output_for >= no_output_seconds)
             AND ( (idle_for >= idle_cpu_seconds)
                   OR (cpu_unknown AND no_output_for >= max_stuck_seconds) )
```
Thresholds `180/180/300`, `max_restarts=1` unchanged. §4.4 wraps it: `stuck = base_stuck AND NOT active_tool_lease`.

**R2-B2 correction (honest, R3-NB1):** an unknown CPU sample never refreshes `last_cpu_change`, so `idle_for` keeps growing and trips the `idle_for >= idle_cpu_seconds` clause at ~180s — the `cpu_unknown AND ≥ max_stuck_seconds(300)` sub-clause adds **no** real 300s grace (it is subsumed). In the all-unknown macOS root-cause path specifically, `idle_for == elapsed`; more generally (CPU known then lost) `idle_for` is measured from the last known change but still crosses 180s without a fresh sample. Either way CPU-unknown behaves as CPU-lapsed at the 180s idle window. After P1-a CPU is normally known on macOS, so this is rarely reached. Predicate NOT changed this cycle.

### 5.1 Liveness model & its boundary (B2 accepted; B3 CLOSED)

Survive the silence watchdog iff, within the window, ANY of: (O) a stream-json byte; (C) group-CPU progress; (L) an in-flight active-tool lease. The hard `timeout_seconds` is the ceiling for the undecidable cases:
- **(B2) CPU-busy semantic hang** — infinite-loop child keeps (C); killed only by hard timeout (AC-6b).
- **Slow/hung in-flight tool** — open lease (L) suppresses the silence kill; a hung tool is bounded by hard timeout (`TimeoutExpired`). Accepted cost of not false-killing legitimate long tools.

**Coverage after P1+P2+P2-L:** ✅ macOS blind-guillotine eliminated; ✅ normal cadence (O); ✅ CPU-bound builds (C); ✅ **B3 output-silent+CPU-idle long tool (`sleep`/network/DB) via the `tool_use`→`tool_result` lease (L)** — no 180s false-kill, hard-timeout-bounded; genuine stuck = none of (O)/(C)/(L) ⇒ killed at ~180s. No threshold raised; liveness event-anchored, not PID-anchored.

---

## 6. Acceptance criteria

- **AC-1 (P1-a):** parse table correct (§2); invalid → `None`; live `_cpu_seconds` a positive float on macOS.
- **AC-2 (P1-b):** group sum; failure falls back to fixed single-pid.
- **AC-3 (P2 argv):** argv has `stream-json`+`--verbose`; prompt on stdin.
- **AC-4 (P2 parser):** terminal `result` extracted; `is_error`/error-subtype/no-terminal → `AdapterError`; single-object back-compat; strict line rule; artifact-vs-verdict byte-identical downstream.
- **AC-5-O:** output at interval < window ⇒ never silence-killed.
- **AC-5-C (group-CPU, NON-VACUOUS — V1):** idle parent + CPU-burning same-PGID child ⇒ never killed; single-pid sampling of the parent reports ~0 (would flag stuck) ⇒ only group aggregation explains survival. Proven by the offline synthetic test (§7); an optional real CPU-bound-bash canary (§8) exercises it end-to-end but is not required.
- **AC-6 (genuine stuck — V3):** NO output AND NO group-CPU AND NO active lease for both windows ⇒ `AgentStuckError` (after restart).
- **AC-6b (hard-timeout ceiling — B2):** output-silent CPU-busy-infinite child under short hard `timeout` + large silence thresholds ⇒ `TimeoutExpired`, tree killed.
- **AC-10 (lease suppresses then releases — V2):** a stream emitting `tool_use` (open) then output-silent AND CPU-idle past both windows is NOT killed while open; after the matching `tool_result` (close) with continued silence past the window it IS killed. Event-anchored + correctly released.
- **AC-11a (hung lease ⇒ hard timeout, no retry — V2):** a never-closing lease is terminated by the hard `timeout_seconds` (`TimeoutExpired`) in exactly ONE attempt (timeout does not restart).
- **AC-11b (per-attempt probe freshness — V2):** on the `_StuckOnce` restart path (genuine no-lease stuck), attempt 2 gets a FRESH probe (empty `open_ids`) from the factory — no orphan lease from attempt 1.
- **AC-7 (no masking):** `git diff` shows no threshold raised, no hard-timeout bump, no bypass, no PID-based liveness.
- **AC-8 (suite green):** offline suite passes; codex/cursor/kimi unaffected.

---

## 7. Test plan

**Unit (offline):**
- `test_monitor.py`: `_parse_ps_time` macOS+Linux (AC-1); `_group_cpu_seconds` aggregation+fallback (AC-2).
- `test_claude_code.py`: argv (AC-3); `_final_result_from_stream` cases (AC-4); **`ToolLeaseProbe`** — open on `tool_use`, close on matching `tool_result`, close on `is_error` result, unknown-id opens nothing, malformed opens nothing, terminal `result` clears, parallel tool_use ids (AC-10 unit). Fixtures use probe-confirmed shapes (§E). Existing gating/permission/dash-injection tests still pass.

**Integration — synthetic child (offline, deterministic), `run_with_monitor` + tiny injected `MonitorConfig`:**
- **AC-5-O:** child prints every 0.5s ~6s, threshold 2s → NOT killed.
- **AC-5-C / V1:** idle parent spawns a busy-loop child in its PGID then `os.wait()`s; parent ~0 CPU; threshold 2s → NOT killed; assert `_cpu_seconds(parent)` ≈ 0.
- **AC-6 / V3:** `sleep 30` (no output/CPU/lease), threshold 2s → `AgentStuckError`.
- **AC-6b / B2:** output-silent CPU-busy-infinite child; short hard `timeout` ~3s, large silence thresholds → `TimeoutExpired`.
- **AC-10 / V2:** child prints one `tool_use` line, silent & CPU-idle ~6s (threshold 2s) → NOT killed (lease open); then prints matching `tool_result`, continues silent → killed. (Real child emitting confirmed JSONL, `ToolLeaseProbe` wired.)
- **AC-11a / V2:** child prints `tool_use` then hangs silent & CPU-idle; short hard `timeout`, large silence thresholds → `TimeoutExpired` in a SINGLE attempt (assert no restart).
- **AC-11b / V2:** genuine no-lease stuck child (no `tool_use`) under tiny silence thresholds trips `_StuckOnce` → restart; a factory recording instantiations asserts attempt 2 got a fresh probe with empty `open_ids`.

**Opt-in real-adapter canaries — §8.**

---

## 8. Canary protocol (mandatory before code gate)

- **Canary-A (output-liveness, must NOT be killed, prod thresholds):** temp git repo; `ClaudeCodeAdapter(model="claude-sonnet-4-6", allow_subprocess=True, cwd=tmp, timeout_seconds=900)`; `workspace_write`; tools `["Write","Read"]`; create `step-001..NNN.txt` sequentially (N tuned so wall-time > ~200s). Assert not killed; artifact complete; no `agent-stuck` dir; transcript gaps < 180s.
- **Canary-A2 (LEASE / B3 end-to-end, must NOT be killed):** tools `["Bash","Write","Read"]`, `--allowed-tools` includes `Bash`; prompt runs ONE bash command CPU-idle & output-silent > 180s (`sleep 200 && echo DONE`) then writes a file. Assert not killed at ~180s (the `tool_use`→`tool_result` lease held it); result returned; transcript shows a single open `tool_use` spanning >180s with no intervening liveness. Direct real-`claude` B3 proof. (Optional variant: a >180s CPU-*bound* bash loop instead of `sleep` additionally exercises group-CPU (C).)
- **Canary-B (genuine stuck, must be killed):** `run_with_monitor(["sleep","30"], monitor_config=MonitorConfig(no_output_seconds=2, idle_cpu_seconds=2, max_stuck_seconds=4, max_restarts=1))` → `AgentStuckError`.
- **Probe (already run — §E):** re-confirm `tool_use`/`tool_result` shapes on the pinned `claude` version at implementation.

---

## 9. Edge cases & resolved questions

- **OQ-1:** RESOLVED (R1) — P1-b in-scope.
- **OQ-2 (single long generation, no tools, >180s):** `thinking_tokens` stream during thinking (Probe 1) → normally (O)-covered. Residual only if a generation truly emits nothing for >180s with no tool and no CPU. Lever: `--include-partial-messages` (deferred; enable only if a canary shows it). Not masking.
- **OQ-3 (B3):** RESOLVED (user directive) — P2-L lease.
- **Parallel tools:** lease active until ALL ids close (set semantics).
- **Blast radius:** monitor benefits codex/cursor/kimi; factory `None` ⇒ byte-identical for them (AC-8).

---

## 10. Rollout
1. → **Codex xhigh read-only design gate** (R4). Fix until APPROVE (0 blocking).
2. Branch `fix/watchdog-liveness-p1-p2` off `f887f79`. Implement P1-a/P1-b/P2/P2-L + §7 tests.
3. §8 canaries (incl. A2 lease proof) on macOS; evidence → `archive/`.
4. Full offline suite green + **Codex code-level gate** (xhigh) → APPROVE.
5. Push the **feature branch only**; PR to `main`. **Do not modify `main`.** Identity `Rex1028 <caoruixin@163.com>`; GitHub `origin`.

## 11. Files touched
- `engine-kit/adapters/monitor.py` — `_parse_ps_time` (P1-a); `_group_cpu_seconds`+call-site (P1-b); `_read_stream` `read1` + last_output-first line-assembly→probe (P2/P2-L); poll-loop `stuck AND NOT probe.active()`; `run_with_monitor` gains `liveness_probe_factory` (fresh probe per attempt).
- `engine-kit/adapters/claude_code.py` — argv `stream-json`+`--verbose`; `_final_result_from_stream` (P2); `ToolLeaseProbe` + factory passed to `run_with_monitor` (P2-L); docstring.
- `engine-kit/adapters/tests/test_monitor.py` — parse, group-CPU, liveness/stuck/lease/restart-freshness tests.
- `engine-kit/adapters/tests/test_claude_code.py` — argv, parser, `ToolLeaseProbe` unit tests; opt-in Canary-A/A2/B.
- `archive/2026-07-03-*canary-evidence.md` (added at step 3).
