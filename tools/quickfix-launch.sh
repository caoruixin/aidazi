#!/usr/bin/env bash
# Quick-Fix lane launcher — THIN entry point only.
#
# This shell does nothing but locate the engine-kit, hand off to the Python core
# (engine-kit/quickfix), and propagate its stable exit code. ALL validation, worktree,
# bundle, guard, verification, record, and teardown logic lives in Python — never here.
#
# Stable exit codes (from quickfix.cli): 0=ok 1=error 2=invalid 3=dirty-tree
# 10=escalated 11=unsupported-harness.
#
# NOTE (Commit 3): usable on Claude Code (`claude_code` is `supported`). `codex` is
# `experimental` and `kimi_code` `unsupported` — the launch gate is strict, so anything not
# `supported` fails closed (exit 11). See QUICK-FIX.md.
set -euo pipefail

usage() {
  echo "usage: quickfix-launch.sh --request <request.json> [--repo-dir <dir>] [--registry <file>]" >&2
  exit 2
}

[ "$#" -ge 1 ] || usage

# Resolve this script -> repo root -> engine-kit (so `python -m quickfix` imports).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENGINE_KIT="${REPO_ROOT}/engine-kit"
if [ ! -d "${ENGINE_KIT}/quickfix" ]; then
  echo "[quickfix] cannot find engine-kit/quickfix under ${REPO_ROOT}" >&2
  exit 1
fi

PYTHON="${QUICKFIX_PYTHON:-python3}"
PYTHONPATH="${ENGINE_KIT}${PYTHONPATH:+:${PYTHONPATH}}" exec "${PYTHON}" -m quickfix "$@"
