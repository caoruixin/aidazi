#!/usr/bin/env bash
# vendor-framework.sh — copy aidazi into an adopter repo (no git submodule).
#
# Usage:
#   ./engine-kit/tools/vendor-framework.sh <framework-source> <adopter-target>
#
# Example (from aidazi repo root):
#   ./engine-kit/tools/vendor-framework.sh . /path/to/my-app
#
# Writes <adopter-target>/aidazi/ and a version stamp at aidazi/.aidazi-version.
# The adopter owns the copy in its own git history; upgrade by re-running and
# diffing (see process/fold-back-protocol.md §1.2).

set -euo pipefail

SRC="${1:?framework source directory (aidazi repo root)}"
DEST="${2:?adopter target directory (repo root)}"

SRC="$(cd "$SRC" && pwd)"
DEST="$(cd "$DEST" && pwd)"
OUT="${DEST}/aidazi"

if [[ ! -f "${SRC}/AGENTS.md" ]] || [[ ! -d "${SRC}/engine-kit" ]]; then
  echo "error: ${SRC} does not look like an aidazi framework root" >&2
  exit 1
fi

mkdir -p "$OUT"

INCLUDE=(
  governance
  process
  docs
  schemas
  templates
  role-cards
  modules
  engine-kit
  skills
  AGENTS.md
  CLAUDE.md
  README.md
  README.zh-CN.md
  ONBOARDING.md
  FIRST-LOOP.md
)

EXCLUDE=(
  --exclude=.git
  --exclude=.specstory
  --exclude=archive
  --exclude=compact
  --exclude=examples
  --exclude='*.pyc'
  --exclude=__pycache__
)

for item in "${INCLUDE[@]}"; do
  if [[ -e "${SRC}/${item}" ]]; then
    rsync -a "${EXCLUDE[@]}" "${SRC}/${item}" "${OUT}/"
  fi
done

VERSION="$(grep -E '^framework_version:' "${SRC}/AGENTS.md" 2>/dev/null | head -1 | sed 's/.*: *//' || echo unknown)"
COMMIT="unknown"
if git -C "$SRC" rev-parse HEAD >/dev/null 2>&1; then
  COMMIT="$(git -C "$SRC" rev-parse --short HEAD)"
fi
DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "${OUT}/.aidazi-version" <<EOF
framework_version: ${VERSION}
source_commit: ${COMMIT}
vendored_at: ${DATE}
vendor_tool: engine-kit/tools/vendor-framework.sh
EOF

echo "Vendored aidazi ${VERSION} (${COMMIT}) -> ${OUT}"
echo "Next: cp ${OUT}/AGENTS.md ${DEST}/AGENTS.md and edit adopter placeholders."
