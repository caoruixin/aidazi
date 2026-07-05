"""Phase-4 onboarding: runnable native-E2E config proposal generator (design §7 / R5).

New-adopter onboarding must emit a COMPLETE, REVIEWABLE, RUNNABLE proposal for user-facing native
E2E — NOT an empty skeleton the human must fill in. The agent inspects the adopter repo (Step-4a
impl-stack snapshot, existing ``frontend/e2e/*.spec.ts``, package scripts, dev-server cmd) via
``inspect_repo`` and drafts a COMPLETE ``tooling.e2e`` (executor-contract shape) + ``tooling.acceptance
.functional`` block plus the requirement-ledger / autonomy / capability linkage via ``generate_proposal``.

Advisory, exactly like the surface-proposal pattern (process/requirement-ledger.md §2.2): the proposal
carries ``proposal_status ∈ {proposed, confirmed}`` + ``proposal_confidence ∈ {high, low}``, is bound
into NO verdict-affecting hash, introduces NO new runtime gate, and binds only on whole-proposal human
authorization (no re-sign until the human signs the charter/plan it lands in).

Two hard guardrails, both DETERMINISTIC + FAIL-CLOSED:
  * ``proposal_completeness_violations`` — an incomplete proposal (any of the R5 elements missing/empty)
    is REJECTED, so onboarding never emits a skeleton requiring manual discovery.
  * ``secret_leak_violations`` — ``secret_refs`` are NAMED references only (``env:``/``file:``/``vault:``);
    a literal secret anywhere in the proposal is REJECTED (never materialize a credential).

Pure module (filesystem-read only, no network, no mutation).
"""
import json
import os
import re
from typing import Optional

# --------------------------------------------------------------------------- #
# Concrete, runnable defaults (design §7) — a proposal is COMPLETE out of the box.
# --------------------------------------------------------------------------- #
DEFAULT_EXECUTOR_KIND = "external_test_runner"
DEFAULT_SPEC_PATH = "frontend/e2e/acceptance.spec.ts"
DEFAULT_BASE_URL = "http://127.0.0.1"
DEFAULT_READINESS = {"url": "/__health", "timeout_seconds": 30, "interval_seconds": 1}
DEFAULT_TIMEOUTS = {"total_seconds": 900, "step_seconds": 60, "lifecycle_seconds": 120}
DEFAULT_EVIDENCE_PATH = ".orchestrator/audit/browser"
DEFAULT_RETRY_POLICY = {"managed_test_retries": 0}  # deterministic evidence; the authoritative
#                            re-run is the §1.7-G FULL managed rerun, not flaky-test retries.
DEFAULT_REMEDIATION = {"enabled": True, "max_rounds": 3, "max_no_progress_rounds": 1}
DEFAULT_AUTONOMY_LEVEL = "human_on_the_loop"

#: The native-E2E capabilities a fully autonomous user-facing run relies on (charter pin).
DEFAULT_REQUIRED_CAPABILITIES = [
    {"id": "native_managed_external_e2e", "min_version": "1.0"},
    {"id": "framework_owned_e2e_provenance", "min_version": "1.0"},
    {"id": "autonomous_e2e_remediation", "min_version": "1.0"},
    {"id": "codex_adapter_liveness", "min_version": "1.0"},
]

#: NAMED secret-reference prefixes — the only shapes secret_refs.ref may take (no literal value).
SECRET_REF_PREFIXES = ("env:", "file:", "vault:")
_SECRET_REF_RE = re.compile(r"^(env|file|vault):[A-Za-z0-9_./\-]+$")
#: keys whose VALUE, if a bare string (not a named ref), is treated as a materialized secret.
SECRET_KEY_HINTS = frozenset({
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
    "access_key", "secret_key", "private_key", "credential", "credentials",
    "auth", "authorization", "bearer", "cookie", "session_token",
})
#: fields that must NEVER appear on a secret_refs entry (they would materialize the secret).
SECRET_VALUE_FIELDS = frozenset({"value", "literal", "plaintext", "secret", "password"})

#: The browser-E2E functional checklist checks (design §7 — the browser-E2E functional checklist).
BROWSER_E2E_FUNCTIONAL_CHECKLIST = [
    "app_starts_and_reaches_readiness",
    "happy_path_journey_passes",
    "each_signed_criterion_has_a_bound_test",
    "captured_console_and_network_errors_are_assertable",
    "evidence_trace_and_screenshots_captured",
    "cleanup_restores_environment",
]


# --------------------------------------------------------------------------- #
# Repo inspection (best-effort, deterministic) — feeds generate_proposal.
# --------------------------------------------------------------------------- #
def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, ValueError):
        return None


def _find_spec(repo_dir: str) -> Optional[str]:
    """The first ``*.spec.ts``/``*.spec.js`` under conventional e2e dirs (sorted, deterministic)."""
    for sub in ("frontend/e2e", "e2e", "tests/e2e", "frontend/tests/e2e"):
        d = os.path.join(repo_dir, sub)
        if not os.path.isdir(d):
            continue
        specs = sorted(f for f in os.listdir(d)
                       if f.endswith((".spec.ts", ".spec.js", ".test.ts", ".test.js")))
        if specs:
            return os.path.join(sub, specs[0]).replace(os.sep, "/")
    return None


def _package_scripts(repo_dir: str) -> dict:
    for rel in ("package.json", "frontend/package.json"):
        raw = _read_text(os.path.join(repo_dir, rel))
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        scripts = data.get("scripts")
        if isinstance(scripts, dict):
            return {"path": rel, "scripts": scripts}
    return {}


def inspect_repo(repo_dir: str) -> dict:
    """Best-effort adopter-repo inspection for the proposal generator. Deterministic, read-only,
    never raises. Returns discovered FACTS + which were found (drives proposal_confidence):
    ``{spec_path, app_start_cmd, dev_script, package_json, impl_stack_present, found:{...}}``.
    Absent facts fall back to concrete defaults in generate_proposal (a proposal is still complete,
    just proposal_confidence=low)."""
    facts: dict = {"found": {}}
    if not repo_dir or not os.path.isdir(repo_dir):
        return facts
    spec = _find_spec(repo_dir)
    if spec:
        facts["spec_path"] = spec
        facts["found"]["spec_path"] = True
    pkg = _package_scripts(repo_dir)
    if pkg:
        facts["package_json"] = pkg.get("path")
        scripts = pkg.get("scripts") or {}
        for name in ("dev", "serve", "start", "dev:e2e"):
            if scripts.get(name):
                facts["dev_script"] = name
                facts["app_start_cmd"] = ["npm", "run", name]
                facts["found"]["app_start_cmd"] = True
                break
    if os.path.isfile(os.path.join(repo_dir, "docs", "current", "implementation-stack.md")):
        facts["impl_stack_present"] = True
        facts["found"]["impl_stack"] = True
    return facts


# --------------------------------------------------------------------------- #
# Proposal generation.
# --------------------------------------------------------------------------- #
def _criterion_ids(criteria: list) -> list:
    out = []
    for c in criteria or []:
        cid = c.get("criterion_id") if isinstance(c, dict) else None
        if cid:
            out.append(str(cid))
    return out


def generate_proposal(*, criteria: list,
                      milestone_id: Optional[str] = None,
                      covers_req_ids: Optional[list] = None,
                      surface: str = "user_facing",
                      checklist_path: Optional[str] = None,
                      checklist_id: Optional[str] = None,
                      repo_facts: Optional[dict] = None,
                      secret_refs: Optional[list] = None,
                      autonomy_level: str = DEFAULT_AUTONOMY_LEVEL,
                      remediation: Optional[dict] = None,
                      required_capabilities: Optional[list] = None,
                      status: str = "proposed") -> dict:
    """Draft a COMPLETE, runnable native-E2E config proposal from the signed functional-checklist
    ``criteria`` (+ optional discovered ``repo_facts``). Every R5 element is filled with a concrete
    default when not discovered, so the result is runnable after human authorization — never a
    skeleton. Advisory: ``proposal_status``/``proposal_confidence`` bind no hash and add no gate.

    ``criteria`` items: ``{criterion_id, criterion?, critical?, req_id?, module?, layer?}`` (the
    Research-owned signed checklist). Each criterion is explicitly mapped (``@crit:<id>`` ↔ id) so no
    signed criterion is 'unmapped' (which would be a pre-publication contract HALT)."""
    repo_facts = repo_facts or {}
    found = repo_facts.get("found") or {}
    cids = _criterion_ids(criteria)
    spec_path = repo_facts.get("spec_path") or DEFAULT_SPEC_PATH
    app_start_cmd = repo_facts.get("app_start_cmd") or ["npm", "run", "dev"]
    checklist_path = checklist_path or (
        f"docs/research-briefs/{milestone_id or 'M1'}-functional-checklist.json")

    # Explicit @crit map: every signed criterion is bound to a test title tag.
    criterion_map = {f"@crit:{cid}": cid for cid in cids}

    executor_contract = {
        "executor_kind": DEFAULT_EXECUTOR_KIND,
        "runner_argv": ["npx", "playwright", "test", spec_path, "--reporter=json"],
        "spec_path": spec_path,
        "criterion_map": criterion_map,
        "target_environment": "local",
        "app_start_cmd": app_start_cmd,
        "readiness": dict(DEFAULT_READINESS),
        "base_url": DEFAULT_BASE_URL,
        "allowed_origins": [DEFAULT_BASE_URL],
        "shutdown": {"process_owned": True},
        "lifecycle_operations": [
            {"id": "seed_test_data", "phase": "setup", "environments": ["local"],
             "side_effect": "create_test_fixtures"},
            {"id": "purge_test_data", "phase": "cleanup", "environments": ["local"],
             "side_effect": "delete_test_fixtures", "failure_policy": "record"},
        ],
        "timeouts": dict(DEFAULT_TIMEOUTS),
        "evidence_retention_path": DEFAULT_EVIDENCE_PATH,
    }
    # NAMED env-var references only (never inline secret values); each becomes an env NAME the
    # adopter sets out-of-band. secret_refs carry the human-only-credential contract (an unresolved
    # one is an R4-d pause), not the material.
    refs = list(secret_refs or [])
    if refs:
        executor_contract["env"] = {
            r["name"]: r.get("ref") for r in refs
            if isinstance(r, dict) and r.get("name") and r.get("ref")
        }

    proposal = {
        "proposal_kind": "native_e2e_config",
        "proposal_status": status,
        "proposal_confidence": ("high" if found.get("spec_path")
                                and found.get("app_start_cmd") else "low"),
        "generated_from": {
            "spec_path_discovered": bool(found.get("spec_path")),
            "app_start_cmd_discovered": bool(found.get("app_start_cmd")),
            "impl_stack_snapshot": bool(repo_facts.get("impl_stack_present")),
            "package_json": repo_facts.get("package_json"),
        },
        "tooling": {
            "e2e": executor_contract,
            "acceptance": {
                "functional": {
                    "mode": "browser_e2e",
                    "interaction_mode": "hybrid",
                    "target_environment": "local",
                    "checklist_path": checklist_path,
                },
            },
        },
        "autonomy": {
            "level": autonomy_level,
            "e2e_remediation": dict(remediation or DEFAULT_REMEDIATION),
        },
        "retry_policy": dict(DEFAULT_RETRY_POLICY),
        "milestone_binding": {
            "milestone_id": milestone_id,
            "covers_req_ids": list(covers_req_ids or []),
            "surface": surface,
            "criterion_ids": cids,
        },
        "secret_refs": refs,
        "functional_checklist": {
            "checklist_id": checklist_id or (f"{milestone_id or 'M1'}-functional-checklist"),
            "checklist_path": checklist_path,
            "browser_e2e_checks": list(BROWSER_E2E_FUNCTIONAL_CHECKLIST),
            "criteria": [
                {"criterion_id": c.get("criterion_id"),
                 "criterion": c.get("criterion"),
                 "critical": bool(c.get("critical", False))}
                for c in (criteria or []) if isinstance(c, dict) and c.get("criterion_id")
            ],
        },
        "required_framework_capabilities": list(
            required_capabilities if required_capabilities is not None
            else DEFAULT_REQUIRED_CAPABILITIES),
    }
    return proposal


# --------------------------------------------------------------------------- #
# Guardrail 1 — secret-leak guard (NAMED refs only; no materialized secret).
# --------------------------------------------------------------------------- #
def is_named_secret_ref(v) -> bool:
    return isinstance(v, str) and bool(_SECRET_REF_RE.match(v))


def secret_leak_violations(obj, _path: str = "") -> list:
    """Every place the proposal materializes a secret instead of NAMING it. Empty ⇒ clean.
    DETERMINISTIC: (1) any ``secret_refs`` entry with a value-bearing field or a ``ref`` that is
    not a NAMED reference; (2) any dict key hinting a secret (SECRET_KEY_HINTS) whose value is a
    bare string that is not a NAMED reference. Recurses dicts + lists."""
    out = []
    if isinstance(obj, dict):
        # secret_refs entries: named ref required, no inline material.
        if _path.endswith("secret_refs[]") or _path.endswith("secret_refs"):
            pass  # handled by list recursion / entry checks below
        for k, v in obj.items():
            child = f"{_path}.{k}" if _path else str(k)
            kl = str(k).lower()
            if kl in SECRET_VALUE_FIELDS and _looks_like_secret_ref_context(_path):
                out.append({"path": child, "reason": "secret_refs entry carries a materialized "
                            "secret value field", "value_field": kl})
            if kl == "ref" and _looks_like_secret_ref_context(_path):
                if not is_named_secret_ref(v):
                    out.append({"path": child, "reason": "secret ref is not a NAMED reference "
                                "(env:/file:/vault:)", "value": _redact(v)})
            elif kl in SECRET_KEY_HINTS and isinstance(v, str) and not is_named_secret_ref(v):
                out.append({"path": child, "reason": "secret-bearing key has a literal value, "
                            "not a NAMED reference", "value": _redact(v)})
            out.extend(secret_leak_violations(v, child))
    elif isinstance(obj, list):
        # tag list context so entry-level checks know they're inside secret_refs.
        tag = _path + "[]" if _path else "[]"
        for i, item in enumerate(obj):
            out.extend(secret_leak_violations(item, f"{_path}[{i}]" if _path else f"[{i}]"))
        _ = tag
    return out


def _looks_like_secret_ref_context(path: str) -> bool:
    return "secret_refs" in (path or "")


def _redact(v) -> str:
    s = str(v)
    return (s[:2] + "…redacted…") if s else ""


# --------------------------------------------------------------------------- #
# Guardrail 2 — completeness (R5): reject a skeleton.
# --------------------------------------------------------------------------- #
def _get(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


#: (dotted path, human element name) — every R5 element the proposal MUST carry, non-empty.
REQUIRED_ELEMENTS = [
    ("tooling.e2e.executor_kind", "executor kind"),
    ("tooling.e2e.runner_argv", "managed runner backend (runner_argv)"),
    ("tooling.e2e.spec_path", "spec location"),
    ("tooling.e2e.app_start_cmd", "environment/startup contract (app_start_cmd)"),
    ("tooling.e2e.readiness", "readiness contract"),
    ("tooling.e2e.base_url", "base_url"),
    ("tooling.e2e.allowed_origins", "allowed_origins"),
    ("tooling.e2e.criterion_map", "signed criterion-to-test mapping"),
    ("tooling.e2e.evidence_retention_path", "artifact/provenance location"),
    ("tooling.e2e.timeouts", "timeout budget"),
    ("tooling.e2e.lifecycle_operations", "cleanup behavior (lifecycle_operations)"),
    ("retry_policy", "retry policy"),
    ("autonomy.e2e_remediation.max_rounds", "remediation budget"),
    ("autonomy.e2e_remediation.max_no_progress_rounds", "no-progress budget"),
    ("autonomy.level", "autonomy level / §1.7-G eligibility"),
    ("tooling.acceptance.functional.mode", "browser-E2E functional acceptance mode"),
    ("tooling.acceptance.functional.checklist_path", "functional checklist path"),
    ("functional_checklist.browser_e2e_checks", "browser-E2E functional checklist"),
    ("milestone_binding.covers_req_ids", "covers_req_ids"),
    ("milestone_binding.surface", "requirement-ledger surface linkage"),
    ("required_framework_capabilities", "framework capability pin"),
]


def proposal_completeness_violations(proposal: dict) -> list:
    """The R5 elements MISSING or EMPTY. Empty ⇒ complete + runnable. A proposal with any
    violation is REJECTED by onboarding (never emit a skeleton). Extra checks:
    ``surface`` must be one of the ledger enum; ``criterion_map`` must map EVERY declared
    criterion_id (an unmapped signed criterion is a pre-publication contract HALT)."""
    out = []
    for dotted, name in REQUIRED_ELEMENTS:
        val = _get(proposal, dotted)
        if val is None or val == "" or val == [] or val == {}:
            out.append({"element": name, "path": dotted, "reason": "missing or empty"})
    surface = _get(proposal, "milestone_binding.surface")
    if surface is not None and surface not in ("user_facing", "non_user_facing"):
        out.append({"element": "surface", "path": "milestone_binding.surface",
                    "reason": f"invalid surface {surface!r} (user_facing|non_user_facing)"})
    # criterion_map must cover every declared criterion_id.
    cids = set(_get(proposal, "milestone_binding.criterion_ids") or [])
    mapped = set((_get(proposal, "tooling.e2e.criterion_map") or {}).values())
    unmapped = sorted(cids - mapped)
    if unmapped:
        out.append({"element": "criterion_map coverage", "path": "tooling.e2e.criterion_map",
                    "reason": f"signed criteria with no bound test (unmapped): {unmapped}"})
    return out


def render_completeness_refusal(violations: list) -> str:
    lines = ["native-E2E onboarding proposal is INCOMPLETE — refusing to emit a skeleton "
             "(design §7 / R5). Fill these before presenting for authorization:"]
    for v in violations:
        lines.append(f"  - {v['element']} ({v['path']}): {v['reason']}")
    return "\n".join(lines)


def unresolved_secret_refs(secret_refs: list, env: Optional[dict] = None) -> list:
    """The NAMED `env:` secret references whose environment variable is NOT set — an unresolved
    human-only credential is an R4-d authority pause (design §7/§8): the config is NOT runnable
    until the human provides the credential out-of-band. Deterministic; only `env:` refs are
    resolvable here (`file:`/`vault:` are resolved by the adopter's own secret backend). Empty ⇒
    every declared env credential is present (no credential halt)."""
    env = os.environ if env is None else env
    out = []
    for r in secret_refs or []:
        ref = r.get("ref") if isinstance(r, dict) else None
        if isinstance(ref, str) and ref.startswith("env:"):
            name = ref[len("env:"):]
            if name and env.get(name) in (None, ""):
                out.append({"name": r.get("name") or name, "ref": ref,
                            "env_var": name, "purpose": r.get("purpose")})
    return out


def render_credential_halt(unresolved: list) -> str:
    """The R4-d human-only-credential pause message: name each missing credential + its env var,
    never a value. The human sets these out-of-band (a gitignored .env.local), then resumes."""
    lines = ["native-E2E is paused for a human-only credential (design §8, R4-d) — the config is "
             "NOT runnable until these NAMED credentials are provided out-of-band (never inline a "
             "secret):"]
    for u in unresolved:
        purpose = f" — {u['purpose']}" if u.get("purpose") else ""
        lines.append(f"  - set environment variable {u['env_var']} (ref {u['ref']}){purpose}")
    return "\n".join(lines)


def render_leak_refusal(violations: list) -> str:
    lines = ["native-E2E onboarding proposal LEAKS a literal secret — refusing (design §7: "
             "secret_refs are NAMED references only, env:/file:/vault:). Fix these:"]
    for v in violations:
        lines.append(f"  - {v['path']}: {v['reason']}")
    return "\n".join(lines)


def validate_proposal(proposal: dict) -> list:
    """The combined onboarding gate: completeness + no-leak. Empty ⇒ the proposal is complete,
    runnable, and leak-free (ready to present for whole-proposal human authorization)."""
    return proposal_completeness_violations(proposal) + secret_leak_violations(proposal)
