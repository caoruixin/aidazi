# Evidence — Claude Code Default-Full root-file wiring (R1 positive/negative canary)

**Date:** 2026-06-22 · **Status:** PROVEN (positive + negative, reproduced twice)
**Thesis under test (normative source `governance/context_briefing.md` §1.1):** Claude Code
auto-loads a root `CLAUDE.md` (and follows its `@AGENTS.md` import into the Default-Full
governance chain), and does **NOT** auto-load a bare root `AGENTS.md`. Therefore a Claude-Code
adopter whose root holds only `AGENTS.md` starts cold with the always-load chain silently absent.
**Reproducer:** `examples/claude-code-full-wiring/verify-full-coldstart.sh` (real `claude -p`,
not a static parser). **Closes:** `archive/2026-06-21-followup-claude-code-agentsmd-baseline.md`.

## Environment

| Field | Value |
|---|---|
| Claude Code version | `2.1.170 (Claude Code)` (`/Users/caoruixin/.npm-global/bin/claude`) |
| OS | `Darwin 23.6.0` (macOS 14.7.4), `arm64` (`Darwin Kernel Version 23.6.0 … RELEASE_ARM64_T6031`) |
| Date | 2026-06-22 |
| Model | harness default (not pinned; the behavior under test is harness memory auto-load, model-independent) |
| Tool restriction | `--disallowedTools Read Edit Write Bash Glob Grep WebFetch WebSearch NotebookEdit Task` |
| Prompt (both cases) | `Reply with a single short greeting word and nothing else.` |

The prompt is a neutral greeting that gives the agent no reason to inspect files, and **all
file-reading / exec tools are disallowed** — so in the negative control the agent *cannot* reach
`AGENTS.md` by reading it. The only path for the canary token to appear is the harness loading it
into cold-start memory.

## Fixtures

Both fixtures are built in a fresh `mktemp -d` (so no parent-directory `CLAUDE.md` leaks in).

**Positive** (`<tmp>/positive/`, the cwd of the `claude -p` call):
```
positive/
├── CLAUDE.md      ← exactly:  @AGENTS.md
└── AGENTS.md      ← minimal canary governance chain: "if loaded, echo token <CANARY> in every reply"
```

**Negative control** (`<tmp>/negative/`, the cwd of the `claude -p` call):
```
negative/
└── AGENTS.md      ← the SAME canary chain — and deliberately NO CLAUDE.md
```

## Exact invocation (argv / cwd / rc)

Identical argv for both cases; only the cwd differs:
```
argv: claude -p "Reply with a single short greeting word and nothing else." \
        --disallowedTools Read Edit Write Bash Glob Grep WebFetch WebSearch NotebookEdit Task
cwd (positive): <tmp>/positive      rc=0
cwd (negative): <tmp>/negative      rc=0
```

## Results — Run 1 (canary `DEFAULTFULL_CANARY_5348C23773089671`)

**`positive.stdout`** — the unique canary IS echoed (CLAUDE.md → `@AGENTS.md` WAS auto-loaded):
```
DEFAULTFULL_CANARY_5348C23773089671

Hi
```

**`negative.stdout`** — the canary is ABSENT (bare `AGENTS.md` was NOT auto-loaded); `negative.stderr` empty:
```
Hello
```

```
PASS  positive: canary token IS present (CLAUDE.md -> @AGENTS.md WAS auto-loaded)
PASS  negative: canary token is ABSENT (bare AGENTS.md was NOT auto-loaded)
Summary: 2 passed, 0 failed
```

## Results — Run 2 (independent canary `DEFAULTFULL_CANARY_16E0EAE74B076D6D`)

Re-run with a fresh random token — same outcome, confirming it is not a one-off or a cached/leaked token:
```
positive.stdout:  DEFAULTFULL_CANARY_16E0EAE74B076D6D\n\nHi
negative.stdout:  Hello
PASS  positive: canary token IS present
PASS  negative: canary token is ABSENT
Summary: 2 passed, 0 failed
```

## User-level / global Claude memory & config — existence and influence

A user-global memory file **does exist** and is auto-loaded by Claude Code in *both* the positive
and negative runs:

```
global_claude_md_exists: yes            (~/.claude/CLAUDE.md)
global_claude_md_contains_canary: no
```

**Why the global config cannot produce a false positive or contaminate the negative control:**

1. **Unique randomized canary per run.** Each run mints `DEFAULTFULL_CANARY_<random-hex>` from
   `/dev/urandom`. That exact token exists **only** in the run's fixture files. `~/.claude/CLAUDE.md`
   (the RTK global instructions) is loaded in both cases but provably does **not** contain the token
   (`global_claude_md_contains_canary: no`), so it cannot inject it into either output.
2. **Symmetry isolates the one variable.** The global config, user settings, model, prompt, argv,
   and the `AGENTS.md` canary content are **identical** across positive and negative. The *only*
   difference is the presence of the root `CLAUDE.md`. So the token appearing in positive and
   vanishing in negative is attributable to that single variable — the `CLAUDE.md` auto-load.
3. **Negative cannot self-serve the token.** File-reading tools are disallowed, so the negative
   agent has no route to the token in its un-loaded `AGENTS.md`. Its `Hello` (no token) is the
   harness *not* auto-loading the bare `AGENTS.md`.
4. **Reproduced with a second independent token**, ruling out a stale/cached value.

## Conclusion

On Claude Code 2.1.170 / macOS arm64, a root `CLAUDE.md` containing `@AGENTS.md` **does** bring the
`AGENTS.md` governance chain into cold-start memory, and a bare root `AGENTS.md` **does not**. This
confirms the R1 thesis and the §1.1 canonical wiring, and validates that the deterministic
`adopter_wiring_validator.py` is gating a real, observed harness behavior — not a hypothetical one.
The follow-up `2026-06-21-followup-claude-code-agentsmd-baseline.md` is resolved by R1.
