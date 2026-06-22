# Evidence — Quick-Fix lane REAL end-to-end on the `codex` harness (qualification)

**Date:** 2026-06-22 · **Status:** QUALIFIED → registry flipped `codex: experimental → supported`
**Reproducer:** `examples/quickfix/e2e-codex.sh` (real `codex exec`, not a mock) ·
**Adapter:** `engine-kit/quickfix/adapters/codex.py` (unchanged — it already had the right CLI form)
**Companion:** `archive/2026-06-22-quickfix-claude-code-e2e-evidence.md` (the claude_code precedent).

## What this proves

A human-explicit Quick-Fix request runs a REAL `codex exec` session that performs a bounded edit
in an out-of-tree bundle + ephemeral worktree, with the adopter's Full-governance chain **not**
cold-started, and the lane's guard / targeted-verification / closure machine boundary intact — so
codex meets the same `supported` bar claude_code cleared. The committed registry was `experimental`
until this evidence landed; qualification used a **test-only** `--registry` override (it did **not**
widen the production gate), and a **production-path smoke** (shipped registry, no override) confirms
the real gate now admits codex.

## Environment (both runs)

| Field | Value |
|---|---|
| codex CLI | `codex-cli 0.134.0` (`/Users/caoruixin/.npm-global/bin/codex`) |
| OS | `Darwin 23.6.0` (macOS 14.7.4) `arm64` |
| model | `gpt-5.5` (`--model gpt-5.5`) |
| provider / gateway | `model_provider = aicodewith`, `base_url = https://api.aicodewith.com/chatgpt/v1`, `wire_api = responses` |
| adapter timeout | edit-phase 300 s (CLI `--timeout`), process-GROUP kill on timeout (`base.py`) |
| global `~/.codex/AGENTS.md` | **absent** (`global_exists: no`) — see "Global instruction" below |

## The two real runs (independent request ids + canaries)

| Run | request_id | result commit | codex exit | duration | checks |
|---|---|---|---|---|---|
| 1 | `e2e-codex-fb9d3c4081ab` | `c109ff3` (`version.txt` 1.2.2→1.2.3) | 0 | 39.0 s | **21/21 PASS** |
| 2 | `e2e-codex-da5ad097f8b1` | `342732d` (`version.txt` 1.2.2→1.2.3) | 0 | 42.8 s | **21/21 PASS** |

(The 21 checks add the production-path gate proof — P1/P2 — to the 19 isolation/flow checks.)

Exact argv (run 1; run 2 identical modulo the per-run paths):
```
codex exec --json -C <bundle>/e2e-codex-<id> --add-dir <worktree>/e2e-codex-<id> \
           --sandbox workspace-write --skip-git-repo-check --ephemeral --model gpt-5.5
cwd  = <repo-parent>/adopter-repo-quickfix-bundles/e2e-codex-<id>   (out-of-tree, sibling of repo)
prompt delivered on stdin (write-then-close); cold_start.bundle_memory_file = "AGENTS.md"
```

## Isolation — the three canaries

1. **`QF_BUNDLE_CANARY_<rand>` — bundle `AGENTS.md` IS auto-loaded.** A mechanism probe runs a real
   `codex exec` with the **same material launch shape as the adapter** (`--json -C <bundle>
   --add-dir <worktree> --sandbox workspace-write --skip-git-repo-check --ephemeral`, prompt on
   **stdin** — `CodexAdapter.build_argv`; `-m` is the alias of the adapter's `--model`, plus a `-o`
   capture file for the evidence) where the `-C`-root `AGENTS.md` carries the canary; codex echoed it
   (`probe-last.txt`). Because the probe reproduces the real launch conditions (out-of-tree `-C`
   root, worktree write-grant, `--skip-git-repo-check`, stdin prompt), it proves the bundle's
   `AGENTS.md` is cold-started **under the lane's actual launch shape**, not a weaker one.
2. **`ADOPTER_FULL_GOVERNANCE_CANARY_<rand>` — adopter Full governance is NOT loaded.** Planted in the
   fixture adopter repo's root `AGENTS.md` **and** `CLAUDE.md` (the R1 canonical entries). In the
   mechanism probe (sibling dir) **and** in every real lane run it is **absent** from all captured
   output (codex stdout/stderr + lane stdout/stderr). The bundle is a *sibling* of the repo, never an
   ancestor, and `--skip-git-repo-check` keeps discovery off it → the adopter chain is never
   cold-started. **This is the load-bearing isolation property.**
3. **`CODEX_GLOBAL_CANARY_<rand>` — executor global instruction.** `~/.codex/AGENTS.md` is **absent**
   on this machine (recorded). A synthetic global was **not** planted: it cannot be added without
   either modifying the user's real codex home or pointing `CODEX_HOME` at a temp dir (which breaks
   auth → would require copying credentials) — both forbidden by the task. This is a recorded
   limitation, **not** a blocker: per the semantic revision, a global `~/.codex/AGENTS.md` is
   executor-level and QF safety does **not** depend on it being harmless — the machine boundary
   (scope guard + targeted verification + closure) holds regardless. Had a global existed and even
   produced its canary, that alone would NOT be an isolation failure; only an ADOPTER-governance
   canary appearing would be, and it never did.

## Full lane flow exercised (per run, all PASS)

`human-explicit request → launcher.prepare (registry gate, clean tree, state-dir-ignored) →
out-of-tree bundle + ephemeral worktree → preliminary guard → REAL codex edit → targeted
verification (version == 1.2.3) → original-repo-unpolluted check → final guard (scope/protected/
symlink) → result commit on quickfix/<id> + consistency check (parent == baseline, committed tree ==
verified tree) → record/evidence persisted → NO auto-apply → teardown (keep branch)`.

Proven by the 19 checks: cwd is the out-of-tree bundle; only the worktree was granted; bundle memory
file = `AGENTS.md`; adopter canary absent; the commit touches **only** `version.txt` (within
`allowed_globs`); guards + verification green; result on `quickfix/<id>` with parent == baseline and
content == the fix; record persisted to `.orchestrator/quickfix/records.jsonl`; the original branch
HEAD/`version.txt` unchanged (not auto-applied); the original working tree clean; worktree + bundle
torn down; no residual QF state (only a gitignored `.orchestrator/` + an inert branch); codex
version + argv recorded in `edit-evidence.json`.

## Gateway reliability

Both runs went through the third-party `aicodewith` gateway (`wire_api = responses`, `gpt-5.5`) and
**succeeded on the first attempt** (40.6 s / 53.8 s) — no timeout, no retry. That same gateway can
intermittently hang; the lane is structurally safe to it: the adapter wraps `codex exec` in
`communicate(input=prompt, timeout=…)` + a process-GROUP kill (`base.py`), so a hung request **fails
closed** as `EscalationRequired(harness_launch_failure)` — it never produces a `completed` result. A
gateway timeout therefore does not threaten correctness; it only costs a re-run. (Neither run needed
one.)

## Registry flip + production-path smoke

- Committed `engine-kit/quickfix/harness_support.yaml`: `codex` → `supported`, bound to
  `cli_version_verified: 0.134.0`, `min_version: 0.134.0` (the floor is pinned to the version the
  proof qualified — `CodexAdapter.MIN_VERSION` matches), `os_verified: darwin (23.6.0 / macOS 14.7.4
  arm64)`, `evidence: archive/2026-06-22-quickfix-codex-e2e-evidence.md`, `verified_on: 2026-06-22`.
- **Production-path gate proof — reproducible (script step 6).** `examples/quickfix/e2e-codex.sh`
  runs a `--no-launch` invocation with the **shipped** registry (NO `--registry` override): prepare
  (the strict registry gate) + adapter preflight pass and the lane tears down without a codex call —
  `[quickfix] prepared + preflighted (--no-launch); torn down without running.`, exit 0 (checks
  **P1/P2**). This proves the production gate admits codex.
- **Production-path full completion (recorded instance).** A real codex lane run via the shipped
  registry (no override), `version.txt 9.9.0 → 9.9.1`:
  ```
  $ python -m quickfix --request req.json --repo-dir <repo> --framework-root <fw> --model gpt-5.5 --timeout 240
  [quickfix] COMPLETED — result on branch quickfix/codex-prod-smoke (commit 62fa39c93401).
  record: outcome=completed | harness=codex | branch=quickfix/codex-prod-smoke | verification.ok=true
  ```

## Decision

codex is promoted to `supported` because, on codex 0.134.0 / macOS arm64: the bundle's `AGENTS.md`
is loaded, the adopter Full governance is **not** loaded, and the QF runtime's machine boundary
(scope/guard/verification/closure) is unbypassable — independent of any executor global instruction.
Adapter unchanged; the launch gate stays strict (only `supported` runs); the real-harness E2E remains
**opt-in** (`examples/quickfix/e2e-codex.sh`), never part of the default offline suite.
