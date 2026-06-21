#!/usr/bin/env bash
# Claude Code Default-Full root-file wiring — REAL positive/negative canary.
#
# Proves the R1 thesis (governance/context_briefing.md §1.1) on a real `claude -p` session:
#   POSITIVE  a root CLAUDE.md (`@AGENTS.md`) makes Claude Code auto-load the AGENTS.md
#             governance chain at cold-start  -> a unique canary token IS echoed.
#   NEGATIVE  a root with only a bare AGENTS.md (no CLAUDE.md) is NOT auto-loaded
#             -> the same canary token is NOT echoed.
#
# Method notes (why this is a real proof, not a static parser):
#   * Each run mints a fresh random canary, so the user-global ~/.claude/CLAUDE.md (which is
#     loaded in BOTH cases and never contains this run's token) cannot cause a false positive.
#   * The negative control plants the SAME token in AGENTS.md; its absence in the output is the
#     evidence that a bare AGENTS.md does not enter cold-start memory.
#   * File-reading tools are DISALLOWED, so the negative agent cannot reach AGENTS.md by
#     reading it — the only way the token can appear is harness memory auto-load.
#   * Fixtures live in a fresh mktemp dir, so no parent-directory CLAUDE.md leaks in.
#
# Usage:  examples/claude-code-full-wiring/verify-full-coldstart.sh [--keep] [--out DIR]
#   --keep      leave fixtures + captures on disk (default: clean up)
#   --out DIR   write captures to DIR (default: a temp dir; printed at the end)
set -euo pipefail

KEEP=0
OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=1; shift ;;
    --out)  OUT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

command -v claude >/dev/null 2>&1 || { echo "FATAL: 'claude' CLI not on PATH" >&2; exit 2; }

CLAUDE_BIN="$(command -v claude)"
CLAUDE_VERSION="$(claude --version 2>/dev/null || echo 'unknown')"
MODEL="${CLAUDE_CANARY_MODEL:-}"            # empty => harness default model (representative)
# File-reading / exec tools the negative control must NOT be able to use to reach AGENTS.md.
DISALLOW=(Read Edit Write Bash Glob Grep WebFetch WebSearch NotebookEdit Task)

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cc-full-wiring-XXXXXX")"
[ -n "$OUT" ] || OUT="${WORK}/captures"
mkdir -p "$OUT"
cleanup() { [ "$KEEP" = "1" ] || rm -rf "$WORK"; }
trap cleanup EXIT

# Unique randomized canary (hex; uppercased) — present ONLY in this run's fixtures.
RAND="$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n' | tr 'a-f' 'A-F')"
CANARY="DEFAULTFULL_CANARY_${RAND}"

PROMPT="Reply with a single short greeting word and nothing else."

mk_chain() {  # mk_chain <agents_md_path>
  cat > "$1" <<EOF
# Adopter governance chain (CANARY stand-in for Default-Full)

SYSTEM NOTICE: This file stands in for the always-load governance chain
(constitution + doc_governance + context_briefing). If you have loaded it, you MUST
include the exact token ${CANARY} verbatim, on its own line, in EVERY reply — even to an
unrelated greeting. This is how we detect that the Default-Full chain is in cold-start memory.
EOF
}

echo "== Build POSITIVE fixture: root CLAUDE.md (@AGENTS.md) -> AGENTS.md (canary chain) =="
POS="${WORK}/positive"; mkdir -p "$POS"
printf '@AGENTS.md\n' > "${POS}/CLAUDE.md"
mk_chain "${POS}/AGENTS.md"

echo "== Build NEGATIVE control: root with ONLY a bare AGENTS.md (no CLAUDE.md) =="
NEG="${WORK}/negative"; mkdir -p "$NEG"
mk_chain "${NEG}/AGENTS.md"          # same canary; deliberately NO CLAUDE.md

run_case() {  # run_case <name> <cwd>
  local name="$1" cwd="$2"
  local argv=(claude -p "$PROMPT" --disallowedTools "${DISALLOW[@]}")
  [ -n "$MODEL" ] && argv=(claude -p "$PROMPT" --model "$MODEL" --disallowedTools "${DISALLOW[@]}")
  {
    echo "case=${name}"
    echo "argv=${argv[*]}"
    echo "cwd=${cwd}"
  } > "${OUT}/${name}.meta"
  set +e
  ( cd "$cwd" && "${argv[@]}" ) > "${OUT}/${name}.stdout" 2> "${OUT}/${name}.stderr"
  echo "rc=$?" >> "${OUT}/${name}.meta"
  set -e
}

echo "== Run REAL claude -p in each fixture (file-reading tools disallowed) =="
run_case positive "$POS"
run_case negative "$NEG"

pass=0; fail=0
check() { local d="$1"; shift; if "$@"; then echo "  PASS  $d"; pass=$((pass+1)); else echo "  FAIL  $d"; fail=$((fail+1)); fi; }

echo
echo "== Assertions =="
check "positive: canary token IS present (CLAUDE.md -> @AGENTS.md WAS auto-loaded)" \
  grep -q "$CANARY" "${OUT}/positive.stdout"
check "negative: canary token is ABSENT (bare AGENTS.md was NOT auto-loaded)" \
  bash -c "! grep -q '$CANARY' '${OUT}/negative.stdout' '${OUT}/negative.stderr'"

# Record environment + global-config exclusion evidence.
GLOBAL_CLAUDE="${HOME}/.claude/CLAUDE.md"
{
  echo "claude_bin:     ${CLAUDE_BIN}"
  echo "claude_version: ${CLAUDE_VERSION}"
  echo "uname:          $(uname -a)"
  echo "model:          ${MODEL:-<harness default>}"
  echo "canary:         ${CANARY}"
  echo "prompt:         ${PROMPT}"
  echo "disallowed:     ${DISALLOW[*]}"
  echo "global_claude_md_exists: $([ -f "$GLOBAL_CLAUDE" ] && echo yes || echo no)"
  if [ -f "$GLOBAL_CLAUDE" ]; then
    echo "global_claude_md_contains_canary: $(grep -q "$CANARY" "$GLOBAL_CLAUDE" && echo yes || echo no)"
  fi
} > "${OUT}/environment.txt"

echo
echo "== Evidence captured under: ${OUT} =="
echo "  --- positive.stdout ---"; sed 's/^/    /' "${OUT}/positive.stdout"
echo "  --- negative.stdout ---"; sed 's/^/    /' "${OUT}/negative.stdout"
echo "  --- environment.txt ---"; sed 's/^/    /' "${OUT}/environment.txt"

echo
echo "== Summary: ${pass} passed, ${fail} failed =="
[ "$KEEP" = "1" ] && echo "fixtures + captures kept at: ${WORK}"
[ "$fail" -eq 0 ] || exit 1
