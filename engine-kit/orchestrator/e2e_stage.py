#!/usr/bin/env python3
"""e2e_stage — PURE fail-closed helpers for the P-C browser-E2E evidence stage.

NORMATIVE SOURCE: archive/2026-06-20-pc-browser-e2e-design.md — §3.2 (acceptance
consistency gate), §3.5a (durable commit / reconcile), §3.5b (evidence-bound,
authority-frozen, criteria-bound verdict reuse), §5 (evidence layout). On any
conflict the spec wins.

WHY A SEPARATE MODULE: the Driver owns state, audit, and checkpoints; the fail-closed
SAFETY CORE (hashing, the reconcile predicate, the consistency gate, the three reuse
fingerprints) is kept here as PURE functions so it is unit-testable in isolation and
driver.py stays thin. Nothing here reads the clock, the network, or mutates global
state; every function is a deterministic transform of its inputs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import socket
import urllib.parse
from typing import Optional

from jsonschema import Draft202012Validator

# Reuse the Audit Spine's canonical_json so P-C hashes are byte-consistent with the
# ledger's own hashing (sorted keys, compact separators).
try:  # audit/ is on sys.path in the engine (driver adds it); fall back for direct import
    import audit_log  # type: ignore
except Exception:  # pragma: no cover - import path shim
    from audit import audit_log  # type: ignore

#: the single hash-chained Audit Spine event type that anchors a committed evidence set.
EVIDENCE_EVENT_TYPE = "browser_e2e_evidence"


# =========================================================================== #
# Hashing primitives.
# =========================================================================== #
def _canon(obj) -> str:
    return audit_log.canonical_json(obj)


def validate(obj, schema: dict) -> Optional[str]:
    """Return the FIRST schema error message, or None if ``obj`` is valid. A thin shared
    helper so the driver validates P-C config/evidence without importing jsonschema."""
    for err in Draft202012Validator(schema).iter_errors(obj):
        return err.message
    return None


def sha256_obj(obj) -> str:
    """sha256 over the canonical JSON of ``obj`` (deterministic, order-independent)."""
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_manifest_hash(artifacts: list) -> str:
    """§5: sha256(canonical_json(sorted [{name, sha256}])). Order-independent so the
    manifest hash is stable regardless of artifact discovery order."""
    pairs = sorted(
        ({"name": a["name"], "sha256": a["sha256"]} for a in artifacts),
        key=lambda p: (p["name"], p["sha256"]),
    )
    return sha256_obj(pairs)


# =========================================================================== #
# Manifest + checklist-results assembly (driver-written, §5).
# =========================================================================== #
def write_checklist_results(staging_dir: str, criteria) -> str:
    """Write checklist-results.json from the executor's CriterionResult list (the
    criterion → action → observed → evidence_refs → executor_status mapping, §5).
    Deterministic (sorted keys, no clock). Returns its run-dir-relative name."""
    rows = [
        {
            "criterion_id": c.criterion_id,
            "criterion": c.criterion,
            "action_performed": c.action_performed,
            "observed_result": c.observed_result,
            "evidence_refs": list(c.evidence_refs),
            "executor_status": c.executor_status,
        }
        for c in criteria
    ]
    rel = "checklist-results.json"
    with open(os.path.join(staging_dir, rel), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, sort_keys=True, indent=2)
    return rel


def _cmd_str(cmd) -> str:
    return " ".join(cmd) if isinstance(cmd, list) else str(cmd or "")


def build_manifest(staging_dir: str, executor_result, contract: dict, *,
                   run_id: str, loop_id: str) -> dict:
    """Hash every artifact the executor wrote PLUS the freshly-written
    checklist-results.json, and assemble the manifest dict
    (browser-evidence-manifest.schema.json). Does NOT write manifest.json — the caller
    publishes it last so the manifest hash never includes manifest.json itself."""
    cr_rel = write_checklist_results(staging_dir, executor_result.criteria)
    rels = sorted(set(list(executor_result.artifacts) + [cr_rel]))
    artifacts = []
    for rel in rels:
        artifacts.append({
            "name": rel, "path": rel,
            "sha256": sha256_file(os.path.join(staging_dir, rel)),
        })
    return {
        "run_id": run_id,
        "loop_id": loop_id,
        "executor_kind": contract.get("executor_kind", ""),
        "app_start_cmd": _cmd_str(contract.get("app_start_cmd")),
        "base_url": contract.get("base_url", ""),
        "exit_code": int(executor_result.exit_code),
        "artifacts": artifacts,
        "artifact_manifest_hash": artifact_manifest_hash(artifacts),
    }


# =========================================================================== #
# §3.5a reconcile — recovery keyed on the persisted run_id + disk + ledger.
# =========================================================================== #
def dir_complete_and_hashes_ok(final_dir: str, manifest_schema: dict,
                               checklist_item_schema: Optional[dict] = None) -> bool:
    """§3.5a precise predicate (round-3 MINOR). True IFF ``final_dir`` holds a complete,
    self-consistent evidence set: a schema-valid manifest; every artifact path a
    NORMALIZED relative path strictly under ``final_dir`` with NO duplicates; every
    listed file present and sha256-matching; ``artifact_manifest_hash`` recomputes;
    checklist-results.json present (+ each row schema-valid if a schema is given); and
    NO file under ``final_dir`` (other than manifest.json) absent from the manifest
    (no strays). Any deviation ⇒ False (fail-closed; forces a re-run, never a skip)."""
    mpath = os.path.join(final_dir, "manifest.json")
    if not os.path.isfile(mpath):
        return False
    try:
        with open(mpath, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        return False
    if list(Draft202012Validator(manifest_schema).iter_errors(manifest)):
        return False
    arts = manifest.get("artifacts") or []
    listed: set = set()
    final_real = os.path.realpath(final_dir)
    for a in arts:
        # Normalize backslashes FIRST so a "..\\outside" cannot slip past the '..' check
        # (Codex impl BLOCKING-1). Reject absolute / parent-escape / duplicate paths.
        norm = str(a.get("path", "")).replace("\\", "/")
        if (not norm or norm.startswith("/") or os.path.isabs(norm)
                or ".." in norm.split("/")):
            return False
        if norm in listed:
            return False  # duplicate artifact path
        ap = os.path.join(final_dir, norm)
        # Reject symlinks + any path that escapes final_dir after resolution (defense
        # against a tampered manifest pointing outside the committed evidence dir).
        if os.path.islink(ap) or not os.path.isfile(ap):
            return False
        if os.path.commonpath([final_real, os.path.realpath(ap)]) != final_real:
            return False
        if sha256_file(ap) != a.get("sha256"):
            return False
        listed.add(norm)
    if artifact_manifest_hash(arts) != manifest.get("artifact_manifest_hash"):
        return False
    cr = os.path.join(final_dir, "checklist-results.json")
    if not os.path.isfile(cr):
        return False
    if checklist_item_schema is not None:
        try:
            with open(cr, "r", encoding="utf-8") as fh:
                rows = json.load(fh)
        except (OSError, ValueError):
            return False
        v = Draft202012Validator(checklist_item_schema)
        for row in (rows if isinstance(rows, list) else [rows]):
            if list(v.iter_errors(row)):
                return False
    # No strays: every on-disk file (except manifest.json) MUST be a listed artifact.
    for root, _dirs, files in os.walk(final_dir):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), final_dir).replace(os.sep, "/")
            if rel == "manifest.json":
                continue
            if rel not in listed:
                return False
    return True


def evidence_event_present(ledger_events: list, run_id: str, manifest_hash: str) -> bool:
    """A committed run is anchored by EXACTLY one browser_e2e_evidence event whose
    payload {run_id, manifest_sha256} matches the on-disk manifest (§3.5a)."""
    for e in ledger_events:
        if e.get("type") == EVIDENCE_EVENT_TYPE:
            p = e.get("payload") or {}
            if p.get("run_id") == run_id and p.get("manifest_sha256") == manifest_hash:
                return True
    return False


def load_manifest(final_dir: str) -> Optional[dict]:
    mpath = os.path.join(final_dir, "manifest.json")
    if not os.path.isfile(mpath):
        return None
    try:
        with open(mpath, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# =========================================================================== #
# §3.2 acceptance consistency gate — a captured failure can never become PASS.
# =========================================================================== #
def check_acceptance_consistency(verdict: dict, manifest: dict, checklist: dict,
                                 checklist_results: list, *,
                                 evidence_rel_prefix: str) -> Optional[tuple]:
    """Deterministic driver-side guard layered on the LLM verdict (browser_e2e only).

    Returns ``None`` when the verdict is consistent with the committed evidence, else a
    ``(action, reason)`` tuple where ``action`` is:
      - ``"gate_hard_fail"`` — an INTEGRITY breach (wrong/absent active class, malformed
        or unbound evidence refs, missing criterion_id) — the run halts;
      - ``"needs_human"`` — a PASS that CONTRADICTS the evidence (a failed/partial case,
        a critical executor failure, or a coverage gap) — routed to surface_approve,
        never shipped.
    ``evidence_rel_prefix`` is the committed run dir relative to run_dir (e.g.
    ``.orchestrator/audit/browser/<loop_id>/<run_id>``); a ref path is bound by stripping
    this prefix and matching the remainder + sha256 against a committed artifact."""
    # 1. Active-class match (integrity).
    if verdict.get("acceptance_class") != "browser_e2e":
        return ("gate_hard_fail",
                "verdict.acceptance_class is not 'browser_e2e' on a browser_e2e run")

    cases = verdict.get("cases") or []

    # 2. criterion_id well-formedness (integrity) + coverage set-equality.
    checklist_ids = [c.get("criterion_id") for c in (checklist.get("criteria") or [])]
    if len(checklist_ids) != len(set(checklist_ids)):
        return ("gate_hard_fail", "functional-checklist has duplicate criterion_id")
    case_ids = [c.get("criterion_id") for c in cases]
    if any(not cid for cid in case_ids):
        return ("gate_hard_fail", "a browser verdict case is missing criterion_id")
    if len(case_ids) != len(set(case_ids)):
        return ("gate_hard_fail", "browser verdict has duplicate case criterion_id")

    # 3. Evidence-ref binding (integrity): every cited ref MUST resolve to a committed
    #    manifest artifact with a matching sha256 (round-3 MAJOR). The manifest.json
    #    index itself is citable (kind=manifest) via its file sha.
    # committed artifacts, keyed by relpath → sha (checklist-results.json IS an
    # artifact; manifest.json is the index, not citable evidence — a ref to it will
    # not bind, by design: the judge cites the actual captured artifacts).
    committed = {a.get("path"): a.get("sha256") for a in (manifest.get("artifacts") or [])}
    prefix = evidence_rel_prefix.rstrip("/") + "/"
    for case in cases:
        for ref in case.get("functional_evidence_refs") or []:
            rpath, rsha = ref.get("path", ""), ref.get("sha256")
            if not rpath.startswith(prefix):
                return ("gate_hard_fail",
                        f"evidence ref path {rpath!r} is outside the committed run dir")
            rel = rpath[len(prefix):]
            if committed.get(rel) != rsha:
                return ("gate_hard_fail",
                        f"evidence ref {rpath!r} (sha {rsha}) does not bind to a "
                        f"committed manifest artifact (path/hash mismatch)")

    # 4. Coverage set-equality (a gap means the judge did not judge every criterion).
    if set(case_ids) != set(checklist_ids):
        return ("needs_human",
                "browser verdict cases do not cover the signed checklist criteria "
                "(set mismatch)")

    mv = verdict.get("milestone_verdict")

    # 5. fix_required ⇒ non-empty failure_briefs (also schema-enforced).
    if mv == "fix_required" and not (verdict.get("failure_briefs") or []):
        return ("gate_hard_fail", "fix_required verdict has empty failure_briefs")

    # 6. A PASS must not contradict the evidence (the core veto). A milestone PASS requires
    #    EVERY signed criterion's CAPTURED executor_status to be 'pass' — any fail / error /
    #    skipped (incl. an unexercised or non-critical criterion) is a gap the human must
    #    adjudicate (Codex impl BLOCKING-2: a skipped/non-critical capture is unverified and
    #    can no longer be overridden into a silent ship; `critical` only escalates urgency).
    if mv == "pass":
        if any((c.get("verdict") != "pass") for c in cases):
            return ("needs_human", "milestone pass with a non-pass case")
        if verdict.get("failure_briefs"):
            return ("needs_human", "milestone pass carrying failure_briefs")
        observed = {row.get("criterion_id"): row.get("executor_status")
                    for row in (checklist_results or [])}
        for cid in checklist_ids:
            st = observed.get(cid, "skipped")
            if st != "pass":
                return ("needs_human",
                        f"milestone pass but criterion {cid!r} executor_status={st!r} "
                        f"(only an all-'pass' capture may ship — a fail/error/skipped "
                        f"criterion is unverified)")
    return None


# =========================================================================== #
# §3.5b reuse fingerprints — evidence, authority, criteria/prompt context.
# =========================================================================== #
def authority_fingerprint(charter: dict, *, active_class: str, calibration_status: str,
                          calibration_record_id: Optional[str],
                          autonomy_level_declared: Optional[str],
                          effective_skill_set_hash: Optional[str] = None,
                          effective_functional: Optional[dict] = None) -> str:
    """Canonical fingerprint over EVERYTHING that determines authority + judge identity
    (round-3 BLOCKING). ``autonomy_level_declared`` MUST be the CHARTER-DECLARED (PRE-degrade)
    level captured BEFORE _calibration_gate runs — the §3.6 degrade mutates the live
    autonomy dict (which aliases charter['autonomy']), so reading the charter here would
    pick up the POST-degrade level and break reuse on resume (Codex impl MAJOR-1). Passing
    the pre-degrade value keeps the fingerprint stable across produce/resume."""
    acc = ((charter.get("tooling") or {}).get("acceptance") or {})
    return sha256_obj({
        "acceptance_class": active_class,
        "mode": acc.get("mode"),
        "autonomy_level_declared": autonomy_level_declared,
        "calibration_status": calibration_status,
        "calibration_record_id": calibration_record_id,
        "judge": {
            "harness": acc.get("harness"),
            "provider": acc.get("provider"),
            "model": acc.get("model"),
            "agent_kind": acc.get("agent_kind"),
            "capability_ref": acc.get("capability_ref"),
        },
        "skills": acc.get("skills"),
        "effective_skill_set_hash": effective_skill_set_hash,
        "effective_functional": effective_functional,
        "subagent_fanout": acc.get("subagent_fanout"),
    })


#: aidazi cold-start include: a line-leading ``@path`` (e.g. @aidazi/governance/constitution.md).
_INCLUDE_RE = re.compile(r"(?m)^\s*@([\w./\-]+)")


def resolve_load_graph(entries: list, *, repo_root: Optional[str] = None,
                       max_files: int = 600) -> tuple:
    """rev7 (Codex impl BLOCKING-3): the resolver graph = the TRANSITIVE CLOSURE of the
    Acceptance load-list, not a hand-built list. Each root in ``entries`` is content-hashed,
    AND every ``@path`` include it (transitively) references — aidazi's cold-start convention,
    resolved relative to the file's dir / ``repo_root`` / the repo's parent (so
    ``@aidazi/governance/...`` resolves) — is followed and hashed too. So an edit to ANY file
    the judge loads (governance chain, conditional process docs, role card, schema, adopter
    ledgers reached via AGENTS.md, …) invalidates §3.5b reuse. An ``inline`` entry hashes a
    dict directly (e.g. tooling.e2e, not a file). Returns ``(graph, missing)`` — ``graph`` =
    sorted ``[{path, purpose, bytes, sha256}]`` (``bytes`` is a WP-0 observation-only size
    field, EXCLUDED from acceptance_input_hash); ``missing`` = MANDATORY roots whose file is
    absent/unreadable (the driver gate_hard_fails). Bounded by ``max_files`` (include backstop);
    symlinks are skipped (containment)."""
    by_real: dict = {}                      # realpath (or inline:key) -> {path, purpose, bytes, sha256}
    missing: list = []
    frontier: list = []                     # (abspath, display_rel, purpose, mandatory)
    bases = tuple(b for b in (repo_root, os.path.dirname(repo_root) if repo_root else None) if b)

    for e in entries:
        if "inline" in e:
            disp = e.get("path", e.get("purpose", "inline"))
            by_real["inline:" + disp] = {"path": disp, "purpose": e.get("purpose", ""),
                                         "sha256": sha256_obj(e["inline"])}
            continue
        p = e.get("path")
        if p and os.path.isfile(p) and not os.path.islink(p):
            frontier.append((p, e.get("rel", p), e.get("purpose", ""),
                             bool(e.get("mandatory"))))
        elif e.get("mandatory"):
            missing.append(e)

    while frontier and len(by_real) < max_files:
        path, disp, purpose, mandatory = frontier.pop()
        rp = os.path.realpath(path)
        if rp in by_real:
            continue                        # content already resolved (dedup) — not missing
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            # A MANDATORY root that EXISTS (passed isfile) but cannot be READ (permission,
            # race) must NOT be silently dropped: a partial graph that the caller treats as
            # complete (empty `missing`) would yield a misleading cold-start load_graph_hash
            # (WP-7 invariant 6) or an Acceptance reuse hash over partial criteria. Report it
            # as missing (fail-closed) — honoring this function's own contract ("`missing` =
            # MANDATORY roots whose file is absent/UNREADABLE"). An @-include (mandatory
            # False) carries no such contract and stays best-effort.
            if mandatory:
                missing.append({"path": disp, "rel": disp, "purpose": purpose,
                                "mandatory": True})
            continue
        by_real[rp] = {"path": disp, "purpose": purpose,
                       # WP-0 measurement (observation-only): the file's byte size, so
                       # the load_sizer can sum cold-start volume WITHOUT a spawn. It is
                       # content-redundant (sha256 already commits to the content) and is
                       # EXCLUDED from acceptance_input_hash, so the §3.5b reuse
                       # fingerprint is byte-identical to its pre-measurement value.
                       "bytes": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue                        # a binary artifact has no includes to follow
        here = os.path.dirname(path)
        for m in _INCLUDE_RE.finditer(text):
            inc = m.group(1)
            for base in (here, *bases):
                cand = os.path.join(base, inc)
                if (os.path.isfile(cand) and not os.path.islink(cand)
                        and os.path.realpath(cand) not in by_real):
                    rel = os.path.relpath(cand, repo_root) if repo_root else inc
                    frontier.append((cand, rel.replace(os.sep, "/"), "include", False))
                    break
    return sorted(by_real.values(), key=lambda g: (g["purpose"], g["path"])), missing


def acceptance_input_hash(projected_prompt: str, resolver_graph: list) -> str:
    """rev6/rev7: bind the verdict to the FULL criteria/prompt context — the resolved
    prompt PLUS the content hash of every path the judge loads (resolver graph).

    WP-0: the reuse fingerprint binds each graph entry's CONTENT IDENTITY only — the
    observational ``bytes`` field (added to resolve_load_graph for the measurement
    baseline) is content-redundant (``sha256`` already commits to the file content) and
    is dropped before hashing, so this hash is BYTE-IDENTICAL to its pre-measurement
    value (old §3.5b reuse records still match; only ``bytes`` is excluded — every other
    key is preserved, so any future graph shape stays bound)."""
    graph_identity = [{k: v for k, v in g.items() if k != "bytes"}
                      for g in resolver_graph]
    return sha256_obj({"projected_acceptance_prompt": projected_prompt,
                       "resolver_graph": graph_identity})


# =========================================================================== #
# Runtime contract projection + port allocation (the driver's per-run wiring).
# =========================================================================== #
def allocate_free_port() -> int:
    """Bind a probe socket to an OS-assigned port, read it back, release it. The window
    between release and the child binding is benign in local/demo v1 (a collision just
    fails readiness → gate_hard_fail → re-run)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _sub_tokens(s: str, subs: dict) -> str:
    for k, v in subs.items():
        s = s.replace(k, v)
    return s


def build_runtime_contract(e2e_cfg: dict, *, port: int, store_path: str,
                           mode: str) -> dict:
    """Project the static charter ``tooling.e2e`` into a concrete runtime
    executor-contract: substitute the literal tokens {port}/{store}/{mode} in
    app_start_cmd, set the concrete base_url (host from the static base_url + the
    allocated port), and set store + mode (the executor carries them to the child env)."""
    c = copy.deepcopy(e2e_cfg)
    subs = {"{port}": str(port), "{store}": store_path, "{mode}": mode}
    cmd = c.get("app_start_cmd")
    if isinstance(cmd, list):
        c["app_start_cmd"] = [_sub_tokens(tok, subs) for tok in cmd]
    elif isinstance(cmd, str):
        c["app_start_cmd"] = _sub_tokens(cmd, subs)
    for op in c.get("lifecycle_operations") or []:
        if not isinstance(op, dict):
            continue
        op_cmd = op.get("command")
        if isinstance(op_cmd, list):
            op["command"] = [_sub_tokens(tok, subs) for tok in op_cmd]
        elif isinstance(op_cmd, str):
            op["command"] = _sub_tokens(op_cmd, subs)
    parsed = urllib.parse.urlparse(c.get("base_url") or "http://127.0.0.1")
    host = parsed.hostname or "127.0.0.1"
    if port:
        scheme = parsed.scheme or "http"
        c["base_url"] = f"{scheme}://{host}:{port}"
    else:
        # Staging/production contracts retain their explicit remote URL. They do
        # not receive a framework-allocated local port.
        c["base_url"] = c.get("base_url")
    c["store"] = store_path
    c["mode"] = mode
    return c
