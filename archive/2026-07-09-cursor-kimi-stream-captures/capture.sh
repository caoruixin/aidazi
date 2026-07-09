#!/usr/bin/env bash
# Env-gated REAL-CLI stream capture for the Phase-1 probe design (work items A0/B0).
#
# Runs ONE trivial two-tool agent turn on cursor-agent and/or kimi with
# --output-format stream-json and records the raw event stream — the evidence
# the CursorStreamProbe/KimiStreamProbe grammars are designed against (same
# discipline as codex.py's "VERIFIED against real captured streams").
#
# REFUSES to run without AIDAZI_CAPTURE_REAL=1: each capture is a real, billed
# agent turn on the operator's account. Never wired into any test or suite.
set -euo pipefail
if [ "${AIDAZI_CAPTURE_REAL:-}" != "1" ]; then
  echo "refusing: set AIDAZI_CAPTURE_REAL=1 to run the real capture (billed CLI turns)" >&2
  exit 2
fi
OUT="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d /tmp/aidazi-capture.XXXXXX)"
PROMPT='Create a file named probe.txt containing exactly the line HELLO-PROBE, then read it back, then reply with exactly DONE.'
target="${1:-all}"
if [ "$target" = "cursor" ] || [ "$target" = "all" ]; then
  mkdir -p "$WORK/cursor" && cd "$WORK/cursor"
  # Same flag geometry as CursorAdapter workspace_write (--force --trust), plus
  # stream-json — the exact mode the adapter will switch to.
  printf '%s' "$PROMPT" | cursor-agent -p --output-format stream-json --force --trust \
    >"$OUT/cursor-stream.jsonl" 2>"$OUT/cursor-stderr.txt" \
    || echo "cursor exit=$?" >>"$OUT/cursor-stderr.txt"
fi
if [ "$target" = "kimi" ] || [ "$target" = "all" ]; then
  mkdir -p "$WORK/kimi" && cd "$WORK/kimi"
  # Same argv form as KimiAdapter (attached --prompt=), plus stream-json.
  kimi --prompt="$PROMPT" --output-format stream-json \
    >"$OUT/kimi-stream.jsonl" 2>"$OUT/kimi-stderr.txt" </dev/null \
    || echo "kimi exit=$?" >>"$OUT/kimi-stderr.txt"
fi
echo "captures written to $OUT; scratch workspace $WORK left for inspection"
