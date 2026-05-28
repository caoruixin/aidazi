#!/usr/bin/env bash
# Pre-commit hook: verifies dev sessions do not accidentally bundle
# deliver-agent owned files into a commit.
#
# Per `framework/governance/constitution.md` §8.7, dev sessions stage
# only files in their authorized scope. Deliver-agent owned files
# (sprint_objective.md / milestone_objective.md / 10-handoff.md /
# action_bank.md / codex-findings.md / compact prompts) are bundled
# by the human at close commit, NOT by the dev session.
#
# This hook checks the staged file list and warns if any
# deliver-agent owned file is staged outside a close commit.
#
# Installation:
#   ln -s ../../framework/tools/precommit_bundling_check.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Override:
#   To intentionally allow a close commit to stage deliver-agent files
#   (the legitimate case at sub-sprint or milestone close), set:
#     AIDAZI_ALLOW_DELIVER_FILES=1 git commit ...
#
# Or use the commit message convention "[close]" prefix to auto-allow.

set -euo pipefail

# Detect dev vs close commit
allow_deliver=0
if [[ "${AIDAZI_ALLOW_DELIVER_FILES:-0}" == "1" ]]; then
    allow_deliver=1
fi

# Check commit message file (Git passes path as $1 in commit-msg hook,
# but this is a pre-commit hook; we read the message from a marker
# file if the user staged one).
if [[ -f ".git/COMMIT_EDITMSG" ]]; then
    if grep -qE '^\[close\]' ".git/COMMIT_EDITMSG" 2>/dev/null; then
        allow_deliver=1
    fi
fi

if [[ "$allow_deliver" == "1" ]]; then
    exit 0
fi

# Patterns of deliver-agent owned files (configurable per project).
DELIVER_OWNED_PATTERNS=(
    'docs/sprint_objective\.md$'
    'docs/milestone_objective\.md$'
    'docs/10-handoff\.md$'
    'docs/action_bank\.md$'
    'docs/codex-findings\.md$'
    'compact/.*\.md$'
)

staged_files=$(git diff --cached --name-only --diff-filter=ACMR)

violations=()
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    for pattern in "${DELIVER_OWNED_PATTERNS[@]}"; do
        if [[ "$file" =~ $pattern ]]; then
            violations+=("$file")
            break
        fi
    done
done <<< "$staged_files"

if [[ ${#violations[@]} -gt 0 ]]; then
    cat >&2 <<EOF
ERROR: deliver-agent owned files staged outside a close commit:

EOF
    for f in "${violations[@]}"; do
        echo "  - $f" >&2
    done
    cat >&2 <<EOF

Per framework/governance/constitution.md §8.7, dev sessions stage only
files in their authorized scope. Deliver-agent owned files are bundled
at close by the human + deliver-agent.

If this IS a close commit, prefix the commit message with [close] OR
set AIDAZI_ALLOW_DELIVER_FILES=1.

If you accidentally staged a deliver-agent file, run:
  git reset HEAD <file>

And document the modification in the sub-sprint handoff §11 so the
deliver-agent can flip it at close.
EOF
    exit 1
fi

exit 0
