# Quick-Fix lane — claude_code real E2E + load-graph evidence (Commit 3 / QF-3)

**Status:** RECORDED (2026-06-22) · **Kind:** real-launch evidence · **Decision it backs:**
promoting `claude_code` to **`supported`** in `engine-kit/quickfix/harness_support.yaml`.
**Baseline (denominator):** [Full cold-start baseline](2026-06-21-full-coldstart-baseline-evidence.md).
**Reproduce:** `examples/quickfix/e2e-claude-code.sh` (this run used `--keep` to capture the
artifacts below, then the fixture was removed).

## What this proves

A real Quick-Fix lane run on the `claude_code` harness, against a clean throwaway adopter
repo, cleared all 16 acceptance criteria — including the load-bearing one: the adopter's
root `CLAUDE.md`/`AGENTS.md` (planted with unique CANARY tokens) did **not** enter the
Quick-Fix session's cold-start. This is the recorded proof the `supported` tier requires
(process/quickfix-lane.md §10); without it `claude_code` would stay `unsupported`.

## Method

1. Build a fixture "adopter" repo (`/tmp/qf-e2e-*/adopter-repo`) with `version.txt` = `1.2.2`
   and **canary governance files** at its root: a `CLAUDE.md` and `AGENTS.md` each carrying a
   unique token (`REPO_CLAUDE_CANARY_d3adb33f`, `REPO_AGENTS_CANARY_c0ffee01`) plus an
   instruction to **echo that token if loaded**. If the lane cold-started the adopter chain,
   the token would appear in the harness output.
2. A human-explicit `quickfix-request.json` scoped to `version.txt` only, with a structured
   targeted verification (`version.txt == 1.2.3`), and a registry marking `claude_code`
   `supported`.
3. Run the real lane: `python -m quickfix --request … --repo-dir <fixture> --framework-root
   <aidazi> --registry <supported>`. The launcher created an out-of-tree bundle + ephemeral
   worktree and the adapter launched a real `claude -p` subprocess.

This is a **behavioral + argv** proof, not a claim about Claude Code internals: it pairs the
documented mechanism (QF-0: `--add-dir` grants file access without loading that dir's
`CLAUDE.md`; an out-of-tree cwd has the repo off its ancestor walk) with an end-to-end run in
which the canary provably never reached the model.

## The recorded launch (edit-evidence.json)

| Field | Value |
|---|---|
| harness | `claude_code` |
| executable | `/Users/caoruixin/.npm-global/bin/claude` |
| cli_version | `2.1.170 (Claude Code)` |
| argv | `claude -p --output-format json --permission-mode acceptEdits --add-dir <worktree> --allowed-tools Read,Edit,Write,MultiEdit,Glob,Grep,LS` |
| cwd | the OUT-OF-TREE bundle (`…/adopter-repo-quickfix-bundles/e2e-bump-version-001`) |
| granted_dirs | the ephemeral worktree ONLY (`…/adopter-repo-quickfix/e2e-bump-version-001`) |
| prompt_delivery | `stdin` (prompt never an argv token) |
| exit_code / timed_out | `0` / `false` |
| duration | 19.06 s (model `claude-opus-4-8[1m]`, 4 turns, 0 permission denials, ~$0.16) |
| cold_start.repo_governance_chain_auto_loaded | **`false`** |

Result: commit `904cf8d` on `quickfix/e2e-bump-version-001` (parent = baseline
`f6114c1e`), `version.txt | 2 +-`, verification `ok: true`; one `completed` record appended
to `.orchestrator/quickfix/records.jsonl`.

Harness stdout (the model's own words — note it followed the **bundle's** lane protocol, not
the adopter chain, and never emitted a canary):

> "Done. I made a single change within the approved scope: `version.txt` — bumped … from
> `1.2.2` to `1.2.3`. … Per the lane protocol, I did not stage, commit, or branch — the
> Quick-Fix lane will run the guard, the targeted verification … and the guard again, then
> commit the result itself."

`grep` of the captured stdout for either canary token → **0 matches**. stderr → 0 bytes.

## Cold-start load-graph: Full (baseline) vs Quick-Fix (this run)

| | Full session (cwd = adopter repo root) | Quick-Fix session (this run) |
|---|---|---|
| cwd | adopter repo root | out-of-tree ephemeral bundle |
| Auto-loaded project memory | adopter root `CLAUDE.md` → the always-load governance chain (`constitution.md`, `doc_governance.md`, `context_briefing.md`) + `docs/current/*` ledgers | the bundle's `CLAUDE.md` ONLY → references the 3 local bundle files (anti-hardcode kernel, lane spec, `request.json`) |
| Adopter governance chain | loaded | **NOT loaded** (canary-proven) |
| `~/.claude/CLAUDE.md` (user global) | loaded | loaded (unchanged; orthogonal to the repo chain — see caveat) |
| Worktree access | n/a | `--add-dir` file access, no `CLAUDE.md` auto-load |

The Quick-Fix session cold-starts the three bundle files instead of the adopter's always-load
chain + ledgers — the reduction the lane claims, now demonstrated end-to-end.

## 16/16 acceptance criteria — PASS

1/2 human-explicit launch; the Full session only spawned a subprocess · 3 cwd = out-of-tree
bundle · 4 only the worktree granted · 5 bundle minimal memory file (`CLAUDE.md`) loaded · 6
adopter `CLAUDE.md`+`AGENTS.md` canaries absent from cold-start · 7 only approved scope
(`version.txt`) modified · 8/10 preliminary + final guard passed · 9 structured verification
passed · 11 result commit on `quickfix/<id>` (and it is the real fix) · 12 record persisted ·
13 NOT auto-applied (base branch HEAD unchanged, still `1.2.2`) · 14 original repo unpolluted ·
15 worktree + bundle torn down · 16 next normal session is Default Full (no residual QF state;
only a gitignored `.orchestrator/` + an inert branch).

## Honest caveats (load-bearing)

- **User-global `~/.claude/CLAUDE.md` still loads.** It would load in any session and is not
  the adopter governance chain; the claim is scoped to the **repo** chain. Maximal isolation
  (`claude --bare`) was deliberately NOT used — it changes auth handling (strictly
  `ANTHROPIC_API_KEY`/`apiKeyHelper`) and is unnecessary for the repo-chain claim.
- **Proof strength.** This is behavioral + argv evidence on `claude 2.1.170`, dated
  2026-06-22. Vendor memory behavior is version-sensitive — re-run the script to re-verify
  against a newer CLI before relying on it.
- **R1 is unaffected.** The Claude-Code-does-not-auto-load-`AGENTS.md` Default-Full gap
  ([R1 follow-up](2026-06-21-followup-claude-code-agentsmd-baseline.md)) is about the **Full**
  path and is explicitly out of scope here; the QF bundle ships `CLAUDE.md`, which Claude Code
  does auto-load, so QF cold-start control is independent of R1.

## Other harnesses (this commit)

- **codex** → `experimental` (adapter delivered; isolation achievable via `-C` out-of-tree
  bundle + `--skip-git-repo-check` so AGENTS.md discovery stays cwd-only, + `--add-dir`
  worktree grant — but no recorded real-launch proof here yet, and a global `~/.codex/AGENTS.md`
  is not suppressible by a documented flag). NOT launchable until evidence lands.
- **kimi_code** → `unsupported` (Kimi merges `AGENTS.md`+`.kimi/AGENTS.md` root→cwd since
  v1.29.0 but has NO `-C`/`--cd` and NO `--add-dir`, so its cwd is both the memory-load root
  and the only writable dir — bundle cwd and worktree edit target cannot be separated).

---

End of claude_code E2E evidence.
