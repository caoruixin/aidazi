# Real-adapter live smoke — prompt-transport hardening

One-time **gated** verification of the live adapter paths that the offline suite
cannot exercise (the real subprocess/HTTP paths are gated behind
`AIDAZI_ALLOW_REAL_ADAPTER=1`). **Billed; run by hand, never wired into CI.**

## 2026-06-19 — branch `v2-loop-engine` @ b431d40

Run in an **isolated temp git repo** (`/tmp/aidazi-smoke-*`), via `/tmp/aidazi_smoke.py`:

| Transport | Path exercised | Result |
|---|---|---|
| `claude_code` (stdin) | real `claude -p` session, prompt on **stdin**, `--permission-mode acceptEdits` → wrote `SENTINEL.txt` | **PASS** |
| `codex` (stdin) | real `codex exec`, prompt on **stdin**, read-only sandbox → schema-conforming verdict | **PASS** |
| `headless` (HTTP) | real DeepSeek OpenAI-compatible endpoint → parseable JSON verdict | **PASS** |

Confirms the root-cause fix (prompt via stdin, not argv) works against the live
CLIs, plus the headless HTTP path. `kimi` (`--prompt=` attached form) is covered by
unit tests only; not smoked here.

### How to re-run
```bash
AIDAZI_ALLOW_REAL_ADAPTER=1 python3.12 /tmp/aidazi_smoke.py
```
Requires: `claude`, `codex` CLIs logged in; `DEEPSEEK_API_KEY` exported (kept in a
gitignored `.env.local`, never committed).
