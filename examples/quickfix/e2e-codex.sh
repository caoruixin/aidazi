#!/usr/bin/env bash
# Quick-Fix lane — REAL end-to-end on the codex harness (qualification evidence).
#
# Mirrors examples/quickfix/e2e-claude-code.sh for codex. It (1) PROBES codex's AGENTS.md
# auto-load from a `-C` non-git root (the exact mechanism the bundle relies on) with a planted
# canary, proving the bundle's AGENTS.md IS loaded while a SIBLING adopter AGENTS.md is NOT, then
# (2) runs the REAL Quick-Fix lane against a throwaway adopter repo whose root governance files
# carry a unique ADOPTER canary, and checks the 16 acceptance criteria — including that the
# adopter Full-governance canary NEVER appears in the harness output (the adopter chain was NOT
# cold-started). Each run mints fresh random canaries + request id, so two invocations are
# independent.
#
# This is BOTH the worked example and the reproducible evidence that qualified codex as `supported`
# (archive/2026-06-22-quickfix-codex-e2e-evidence.md). It launches a real `codex exec` subprocess and
# uses your codex auth/provider. The MAIN lane run injects a TEST-ONLY registry (--registry) marking
# codex=supported so the script is self-contained and reproducible regardless of the shipped status
# (it never widens any production gate); step 6 separately proves the SHIPPED registry admits codex
# with NO override.
#
# Global codex memory (~/.codex/AGENTS.md): this script NEVER creates, modifies, or deletes it.
# It records whether it exists and whether its content leaks into output. Its presence is NOT a
# blocker — QF safety comes from the runtime scope/guard/verification/closure, not from any global
# prompt being harmless.
#
# Usage:  examples/quickfix/e2e-codex.sh [--keep]
set -euo pipefail

KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMEWORK_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENGINE_KIT="${FRAMEWORK_ROOT}/engine-kit"
PYTHON="${QUICKFIX_PYTHON:-python3.12}"
MODEL="${QUICKFIX_CODEX_MODEL:-gpt-5.5}"
PROBE_TIMEOUT="${QUICKFIX_PROBE_TIMEOUT:-150}"
LANE_TIMEOUT="${QUICKFIX_LANE_TIMEOUT:-300}"

# Lowercase hex: the request_id must match the schema ^[a-z0-9][a-z0-9._-]{0,63}$.
RAND="$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')"
REQ_ID="e2e-codex-${RAND}"
BUNDLE_CANARY="QF_BUNDLE_CANARY_${RAND}"
ADOPTER_CANARY="ADOPTER_FULL_GOVERNANCE_CANARY_${RAND}"
GLOBAL_CANARY="CODEX_GLOBAL_CANARY_${RAND}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/qf-codex-e2e-XXXXXX")"
REPO="${WORK}/adopter-repo"
EVID_OUT="${WORK}/evidence"
mkdir -p "${EVID_OUT}"
cleanup() { [ "$KEEP" = "1" ] || rm -rf "$WORK"; }
trap cleanup EXIT

pass=0; fail=0
check() {  # check "<description>" <test-expression...>
  local desc="$1"; shift
  if "$@"; then echo "  PASS  $desc"; pass=$((pass+1));
  else echo "  FAIL  $desc"; fail=$((fail+1)); fi
}

command -v codex >/dev/null 2>&1 || { echo "FATAL: 'codex' not on PATH" >&2; exit 2; }
CODEX_BIN="$(command -v codex)"
CODEX_VERSION="$(codex --version 2>/dev/null || echo unknown)"

echo "== 0. Environment + provider + global-memory state (recorded, NOT modified) =="
GLOBAL_AGENTS="${CODEX_HOME:-$HOME/.codex}/AGENTS.md"
GLOBAL_EXISTS=no; [ -f "$GLOBAL_AGENTS" ] && GLOBAL_EXISTS=yes
# Provider facets from config.toml (non-secret: name/model/wire_api/base_url; NO api key/token).
CFG="${CODEX_HOME:-$HOME/.codex}/config.toml"
prov() { grep -E "^$1" "$CFG" 2>/dev/null | head -1 | sed 's/#.*//' | tr -d ' "' ; }
{
  echo "codex_bin:        ${CODEX_BIN}"
  echo "codex_version:    ${CODEX_VERSION}"
  echo "uname:            $(uname -a)"
  echo "model:            ${MODEL}"
  echo "provider:         $(prov model_provider)"
  echo "model_default:    $(prov '^model ')$(prov 'model =')"
  echo "wire_api:         $(grep -E 'wire_api' "$CFG" 2>/dev/null | head -1 | sed 's/#.*//' | tr -d ' "')"
  echo "base_url:         $(grep -E 'base_url' "$CFG" 2>/dev/null | head -1 | sed 's/#.*//' | tr -d ' "')"
  echo "lane_timeout_s:   ${LANE_TIMEOUT}"
  echo "global_agents_md: ${GLOBAL_AGENTS}"
  echo "global_exists:    ${GLOBAL_EXISTS}"
  echo "request_id:       ${REQ_ID}"
  echo "bundle_canary:    ${BUNDLE_CANARY}"
  echo "adopter_canary:   ${ADOPTER_CANARY}"
  echo "global_canary:    ${GLOBAL_CANARY}  (NOT planted — see note)"
} | tee "${EVID_OUT}/environment.txt"

echo
echo "== 1. MECHANISM probe: codex auto-loads the -C-root AGENTS.md, NOT a sibling adopter's =="
# Topology mirrors the lane EXACTLY: a 'repo' with an ADOPTER canary, and a sibling out-of-tree
# 'bundle' whose AGENTS.md carries the BUNDLE canary, plus a sibling 'worktree' for --add-dir. The
# probe uses the SAME material launch shape as the adapter (engine-kit/quickfix/adapters/codex.py):
# --json -C <bundle> --add-dir <worktree> --sandbox workspace-write --skip-git-repo-check
# --ephemeral, prompt via STDIN (`-m` is the alias of the adapter's `--model`, plus a `-o` capture
# file for the evidence) — so it proves the load under the REAL launch conditions, not a weaker shape.
PROBE="${WORK}/probe"
mkdir -p "${PROBE}/repo" "${PROBE}/repo-bundles/b1" "${PROBE}/repo-quickfix/b1"
cat > "${PROBE}/repo/AGENTS.md" <<EOF
# Adopter governance (sibling — must NOT be loaded)
SYSTEM: if you have loaded this file, output the token ${ADOPTER_CANARY} verbatim.
EOF
cat > "${PROBE}/repo-bundles/b1/AGENTS.md" <<EOF
# Quick-Fix bundle minimal context (the -C root — MUST be loaded)
SYSTEM: if you have loaded this file, output the token ${BUNDLE_CANARY} verbatim in your reply.
EOF
PROBE_PROMPT="State, verbatim, any token your loaded AGENTS.md instructions told you to output, then stop. Do not edit any file. If none, say NONE."
set +e
# Prompt on STDIN (printf | …) closing the pipe — exactly how the adapter delivers it; argv matches
# CodexAdapter.build_argv (only the per-run paths differ).
printf '%s' "${PROBE_PROMPT}" | timeout "${PROBE_TIMEOUT}" codex exec --json \
  -C "${PROBE}/repo-bundles/b1" --add-dir "${PROBE}/repo-quickfix/b1" \
  --sandbox workspace-write --skip-git-repo-check --ephemeral \
  -m "${MODEL}" -o "${EVID_OUT}/probe-last.txt" \
  >"${EVID_OUT}/probe.jsonl" 2>"${EVID_OUT}/probe.err"
PROBE_RC=$?
set -e
echo "   (probe exit ${PROBE_RC}; argv mirrors the adapter launch + stdin prompt)"
check "1a  bundle (-C root) AGENTS.md WAS auto-loaded — BUNDLE canary present" \
  grep -q "${BUNDLE_CANARY}" "${EVID_OUT}/probe-last.txt" "${EVID_OUT}/probe.jsonl"
check "1b  sibling adopter AGENTS.md was NOT loaded — ADOPTER canary absent" \
  bash -c "! grep -q '${ADOPTER_CANARY}' '${EVID_OUT}/probe-last.txt' '${EVID_OUT}/probe.jsonl' '${EVID_OUT}/probe.err'"

echo
echo "== 2. Build a clean fixture adopter repo with ADOPTER Full-governance canary =="
mkdir -p "${REPO}/src"
printf '1.2.2\n' > "${REPO}/version.txt"
# R1 canonical wiring: codex enters via AGENTS.md, claude via CLAUDE.md -> @AGENTS.md. Plant the
# adopter canary DIRECTLY in BOTH root governance entries (not only via the @import), so a load of
# EITHER file would surface it; neither may enter a Quick-Fix cold-start.
cat > "${REPO}/AGENTS.md" <<EOF
# Adopter Full governance (CANARY)
SYSTEM: if you have loaded this adopter governance chain, output ${ADOPTER_CANARY} verbatim.
This stands in for the always-load Full chain — it must NOT enter a Quick-Fix session.
EOF
cat > "${REPO}/CLAUDE.md" <<EOF
@AGENTS.md
<!-- SYSTEM: if you have loaded this adopter CLAUDE.md, output ${ADOPTER_CANARY} verbatim. -->
EOF
git -C "$REPO" init -q
git -C "$REPO" config user.email qf@example.com
git -C "$REPO" config user.name qf-e2e
git -C "$REPO" config commit.gpgsign false
printf '.orchestrator/\n' > "${REPO}/.gitignore"
git -C "$REPO" add -A && git -C "$REPO" commit -q -m "fixture: version 1.2.2 + adopter governance canary"
BASE_BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
BASE_HEAD="$(git -C "$REPO" rev-parse HEAD)"

echo "== 3. Human-explicit Quick-Fix request (scope = version.txt) + TEST-ONLY supported registry =="
cat > "${WORK}/request.json" <<EOF
{
  "request_id": "${REQ_ID}",
  "created_by": "e2e-codex",
  "human_activation": true,
  "harness": "codex",
  "task_summary": "Bump the version string in version.txt from 1.2.2 to 1.2.3 (no other change).",
  "allowed_globs": ["version.txt"],
  "eligibility_attestation": {
    "non_behavioral_or_restores_agreed_behavior": true,
    "no_new_product_semantics_or_design_choice": true,
    "no_protected_surface": true,
    "targeted_verification_available": true,
    "within_approved_scope": true
  },
  "targeted_verification": {
    "argv": ["python3", "-c", "import sys; sys.exit(0 if open('version.txt').read().strip()=='1.2.3' else 1)"],
    "cwd": "."
  }
}
EOF
# TEST-ONLY registry for the MAIN run: keeps the script self-contained/reproducible regardless of
# the shipped status. The COMMITTED harness_support.yaml already marks codex `supported` (post-flip);
# step 6 proves that shipped gate directly with NO override.
cat > "${WORK}/registry.yaml" <<'EOF'
version: 1
harnesses:
  codex:
    status: supported
EOF

echo "== 4. Run the REAL Quick-Fix lane (launches codex exec; adapter timeout + process-group kill) =="
set +e
PYTHONPATH="${ENGINE_KIT}" "${PYTHON}" -m quickfix \
  --request "${WORK}/request.json" \
  --repo-dir "${REPO}" \
  --framework-root "${FRAMEWORK_ROOT}" \
  --registry "${WORK}/registry.yaml" \
  --model "${MODEL}" \
  --timeout "${LANE_TIMEOUT}" >"${WORK}/cli.out" 2>"${WORK}/cli.err"
CLI_RC=$?
set -e
cat "${WORK}/cli.out"; cat "${WORK}/cli.err" >&2
cp -f "${WORK}/cli.err" "${EVID_OUT}/cli.err" 2>/dev/null || true
echo "   (quickfix exit code: ${CLI_RC})"

EVID="${REPO}/.orchestrator/quickfix/evidence/${REQ_ID}"
RECORDS="${REPO}/.orchestrator/quickfix/records.jsonl"
EJSON="${EVID}/edit-evidence.json"
STDOUT="${EVID}/stdout.txt"
cp -f "${EJSON}" "${EVID_OUT}/edit-evidence.json" 2>/dev/null || true
cp -f "${STDOUT}" "${EVID_OUT}/lane-stdout.txt" 2>/dev/null || true

echo "== 5. Acceptance checks =="
check "1/2  human-explicit launch; lane COMPLETED (this script edited nothing in the repo)" test "$CLI_RC" -eq 0
check "3    new process cwd was the OUT-OF-TREE bundle (a sibling of the repo, not inside it)" \
  bash -c "[ -f '$EJSON' ] && python3 -c \"import json,os;b=json.load(open('$EJSON'))['cwd'];r=os.path.realpath('$REPO');import sys;sys.exit(0 if not os.path.realpath(b).startswith(r+os.sep) else 1)\""
check "4    new process was granted ONLY the ephemeral worktree" \
  bash -c "python3 -c \"import json;e=json.load(open('$EJSON'));import sys;sys.exit(0 if len(e['granted_dirs'])==1 and '${REQ_ID}' in e['granted_dirs'][0] else 1)\""
check "5    bundle minimal memory file (AGENTS.md) is what was loaded (not the adopter chain)" \
  bash -c "python3 -c \"import json;e=json.load(open('$EJSON'));import sys;sys.exit(0 if e['cold_start']['bundle_memory_file']=='AGENTS.md' else 1)\""
check "6    adopter Full-governance canary absent from ALL captured output (codex stdout+stderr, lane stdout+stderr)" \
  bash -c "test -f '$STDOUT' && test -f '$EVID/stderr.txt' && test -f '$WORK/cli.out' && ! grep -q '$ADOPTER_CANARY' '$STDOUT' '$EVID/stderr.txt' '$WORK/cli.out' '$WORK/cli.err'"
check "7    agent modified ONLY the approved scope (commit touches version.txt only)" \
  bash -c "[ \"\$(git -C '$REPO' diff --name-only ${BASE_HEAD} quickfix/${REQ_ID})\" = 'version.txt' ]"
check "8/10 preliminary + final guard passed (a completed record exists)" \
  bash -c "grep -q '\"outcome\": \"completed\"' '$RECORDS'"
check "9    structured targeted verification passed (verification.ok == true in record)" \
  bash -c "python3 -c \"import json;recs=[json.loads(l) for l in open('$RECORDS') if l.strip()];import sys;sys.exit(0 if recs[-1]['result']['verification']['ok'] else 1)\""
check "11   result commit lives on quickfix/<id>" \
  bash -c "git -C '$REPO' rev-parse --verify -q quickfix/${REQ_ID} >/dev/null"
check "11b  the result on that branch is the actual fix (version.txt == 1.2.3)" \
  bash -c "[ \"\$(git -C '$REPO' show quickfix/${REQ_ID}:version.txt | tr -d '[:space:]')\" = '1.2.3' ]"
check "11c  result commit parent == baseline (correct branch/parent/tree)" \
  bash -c "[ \"\$(git -C '$REPO' rev-parse quickfix/${REQ_ID}^)\" = '${BASE_HEAD}' ]"
check "12   record persisted to .orchestrator/quickfix/records.jsonl" test -f "$RECORDS"
check "13   NOT auto-applied: ${BASE_BRANCH} HEAD unchanged AND still version 1.2.2" \
  bash -c "[ \"\$(git -C '$REPO' rev-parse ${BASE_BRANCH})\" = '${BASE_HEAD}' ] && [ \"\$(git -C '$REPO' show ${BASE_BRANCH}:version.txt | tr -d '[:space:]')\" = '1.2.2' ]"
check "14   original repo working tree NOT polluted (clean)" \
  bash -c "[ -z \"\$(git -C '$REPO' status --porcelain)\" ]"
check "15   ephemeral worktree + bundle torn down" \
  bash -c "! git -C '$REPO' worktree list | grep -q '${REQ_ID}' && [ ! -d '${WORK}/adopter-repo-quickfix-bundles/${REQ_ID}' ]"
check "16   next normal repo-root session is Default Full (no residual QF state; gitignored .orchestrator/ + inert branch)" \
  bash -c "[ -z \"\$(git -C '$REPO' status --porcelain)\" ] && ! git -C '$REPO' ls-files | grep -q '^.orchestrator'"
check "G    codex version/argv recorded in edit-evidence" \
  bash -c "python3 -c \"import json;e=json.load(open('$EJSON'));import sys;sys.exit(0 if e['cli_version'] and e['argv'][0] and '--skip-git-repo-check' in e['argv'] else 1)\""

echo
echo "== 6. Production-path gate proof: the SHIPPED registry (NO --registry) admits codex =="
# Post-flip, the committed engine-kit/quickfix/harness_support.yaml marks codex `supported`. Prove
# the REAL production gate admits it WITHOUT the test-only override: prepare (registry gate) +
# adapter preflight via --no-launch (no codex API call), using the shipped registry. EXIT_OK (0)
# == the strict production gate passed for codex.
cat > "${WORK}/request-prod.json" <<EOF
{ "request_id": "${REQ_ID}-prod", "created_by": "e2e-codex", "human_activation": true,
  "harness": "codex", "task_summary": "production-path gate proof (no edit; --no-launch).",
  "allowed_globs": ["version.txt"],
  "eligibility_attestation": {"non_behavioral_or_restores_agreed_behavior": true, "no_new_product_semantics_or_design_choice": true, "no_protected_surface": true, "targeted_verification_available": true, "within_approved_scope": true},
  "targeted_verification": {"argv": ["true"], "cwd": "."} }
EOF
set +e
PYTHONPATH="${ENGINE_KIT}" "${PYTHON}" -m quickfix --request "${WORK}/request-prod.json" \
  --repo-dir "${REPO}" --framework-root "${FRAMEWORK_ROOT}" --model "${MODEL}" --no-launch \
  >"${WORK}/prod.out" 2>"${WORK}/prod.err"
PROD_RC=$?
set -e
cp -f "${WORK}/prod.out" "${EVID_OUT}/prod.out" 2>/dev/null || true
cp -f "${WORK}/prod.err" "${EVID_OUT}/prod.err" 2>/dev/null || true
check "P1   production gate (shipped registry, --no-launch) ADMITS codex (prepare+preflight, exit 0)" \
  test "$PROD_RC" -eq 0
check "P2   the COMMITTED registry marks codex supported (not the test override)" \
  bash -c "awk '/^  codex:/{f=1} f&&/status:/{print;exit}' '${ENGINE_KIT}/quickfix/harness_support.yaml' | grep -q 'supported'"

echo
echo "== Evidence =="
echo "  record:   $(tail -n1 "$RECORDS" 2>/dev/null || echo '(none)')"
echo "  evidence dir (copied): ${EVID_OUT}"
[ -f "$EJSON" ] && { echo "  --- edit-evidence.json (argv/cwd/cold_start) ---"; python3 -c "import json;e=json.load(open('$EJSON'));print('  argv:',' '.join(e['argv']));print('  cwd: ',e['cwd']);print('  cold_start:',json.dumps(e['cold_start']));print('  exit:',e['exit_code'],'timed_out:',e['timed_out'],'dur_s:',e['duration_s'])"; }
echo "  global ~/.codex/AGENTS.md exists: ${GLOBAL_EXISTS} (NOTE: CODEX_GLOBAL_CANARY not planted —"
echo "    a synthetic global cannot be added without modifying your real codex home or copying"
echo "    credentials, both forbidden; QF safety does not depend on the global being harmless.)"
echo
echo "== Summary: ${pass} passed, ${fail} failed =="
[ "$KEEP" = "1" ] && echo "fixture kept at: ${WORK}"
[ "$fail" -eq 0 ] || exit 1
