#!/usr/bin/env python3
"""WP-EQ constraint-equivalence gate (kernel_equivalence).

Read-only, build-time gate over the constraint inventory under
``engine-kit/tools/constraint-inventory/``. It does NOT call any LLM, open a
network connection, or dispatch a sub-agent — it only reads YAML/source files
and recomputes hashes.

The inventory is the set of ``NN-*.yaml`` row files (each row is one extracted
constraint). ``_sources.yaml`` is the manifest binding each source document to
the sha256 it was extracted from; a drift there means the inventory is stale.

Public surface:
  * ``check(repo_root=REPO_ROOT_DEFAULT) -> {ok, errors, warnings, stats}``
  * ``main(argv) -> int`` (CLI; ``--json``; exit nonzero iff not ok)

Checks (1-3,5 are errors; 4 is warnings):
  1. well-formedness of every row,
  2. globally-unique ids,
  3. source-hash binding (manifest sha256 vs recomputed),
  4. enforcement-ref resolution (schema:/role-card: file existence;
     driver:/validator:/adapter:/campaign: symbol present in engine-kit code),
  5. source-coverage audit against REQUIRED_ANCHORS.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a hard dependency
    yaml = None

HERE = Path(__file__).resolve()
# parents[1] == engine-kit; its parent is the repo root ("parent of engine-kit").
REPO_ROOT_DEFAULT = HERE.parents[2]

MANIFEST_NAME = "_sources.yaml"
INVENTORY_GLOB = "*.yaml"

# Check 3b (anchor shape) requires every anchor to start with a real manifest source
# path; hermetic tests use synthetic anchors/manifests, so they toggle this off.
ENABLE_ANCHOR_SHAPE_CHECK = True

REQUIRED_KEYS = ("id", "anchor", "statement", "roles", "condition", "current_enforcement")
ALLOWED_ROLES = {
    "research", "deliver", "dev", "review", "acceptance", "customer",
    "all", "control-plane", "orchestrator", "code_reviewer",
}
ENFORCEMENT_RE = re.compile(
    r"^(driver:|validator:|schema:|adapter:|campaign:|role-card:|none-judgment$)"
)
# current_enforcement prefixes resolved by grepping engine-kit/ for a symbol.
GREP_PREFIXES = ("driver:", "validator:", "adapter:", "campaign:")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")

# Source-coverage audit: each token MUST appear as a substring of >=1 row.anchor
# whose anchor belongs to that source. Missing token -> error.
REQUIRED_ANCHORS = {
    "governance/constitution.md": [
        "§1.7-A", "§1.7-B", "§1.7-C", "§1.7-D", "§1.7-E", "§1.7-F",
        # Each §3.4 role-boundary invariant must be individually present (not just the
        # cluster) so a hollow inventory cannot drop invariants and still pass.
        "§3.4 #1", "§3.4 #2", "§3.4 #3", "§3.4 #4", "§3.4 #5", "§3.4 #6",
        "§3.5", "§3.6", "§7.0", "§10",
    ],
    "process/delivery-loop.md": (
        ["§4.2.3 #%d" % i for i in range(1, 10)]
        + ["§4.2.8 #%d" % i for i in range(1, 15)]
    ),
    "governance/doc_governance.md": ["§1", "§2", "§3", "§4", "§5", "§7", "§8"],
    "governance/context_briefing.md": ["§1.0", "§1.1", "§1.2", "§5", "§6", "§7"],
    # Each §4 role-skill boundary constraint must be individually present.
    "process/role-skill-model.md": ["§4 #1", "§4 #2", "§4 #3", "§4 #4", "§4 #5", "§6"],
    # Role cards: require each card's boundary + pre-output-checklist sections so a bulk
    # deletion of a role's rows fails the audit (not just the global row count).
    "role-cards/dev-agent.md": ["§3", "§4", "§5", "§7"],
    "role-cards/code-reviewer-agent.md": ["§5.2", "§7", "§8"],
    "role-cards/deliver-agent.md": ["§4.2", "§7"],
    "role-cards/research-agent.md": ["§4", "§5", "§7"],
    "role-cards/acceptance-agent.md": ["§3", "§4", "§5", "§7", "§9", "§10"],
}

# Per-source-file row-count FLOORS (defense-in-depth vs the anchor audit): deleting rows
# below the floor fails even if the surviving rows still cover the required anchors. Floors
# are set at the audited row counts; legitimate ADDITIONS only raise the count.
EXPECTED_MIN_ROWS = {
    "01-constitution-core.yaml": 29,
    "02-constitution-roles.yaml": 41,
    "03-doc-governance.yaml": 41,
    "04-context-briefing.yaml": 44,
    "05-delivery-loop.yaml": 80,
    "06-role-cards-dev-review.yaml": 105,
    "07-role-cards-acc-del-res.yaml": 140,
}

# Engine-kit subtrees / suffixes skipped when building the symbol-resolution corpus.
_SKIP_DIRS = {"__pycache__", ".git", "node_modules"}
_SKIP_SUFFIXES = {".pyc", ".pyo", ".so", ".png", ".jpg", ".jpeg", ".gif",
                  ".pdf", ".zip", ".gz", ".ico", ".woff", ".woff2"}
_MAX_CORPUS_FILE_BYTES = 5 * 1024 * 1024


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_inventory(inv_dir: Path):
    """Return [(filename, rows)] for every NN-*.yaml except the manifest, sorted."""
    out = []
    for path in sorted(glob.glob(str(inv_dir / INVENTORY_GLOB))):
        name = os.path.basename(path)
        # `_`-prefixed files are META, not inventory rows: _sources.yaml (source-hash
        # manifest) and _kernel_coverage.yaml (WP-2 kernel-coverage map).
        if name == MANIFEST_NAME or name.startswith("_"):
            continue
        with open(path, encoding="utf-8") as fh:
            rows = yaml.safe_load(fh)
        out.append((name, rows if rows is not None else []))
    return out


def _build_corpus(engine_kit_dir: Path, exclude_dir: Path) -> str:
    """Concatenate engine-kit source text for fixed-string symbol resolution.

    The constraint-inventory directory is excluded: it lists the symbols, so
    including it would make every reference resolve against its own listing.
    """
    exclude = os.path.normpath(str(exclude_dir))
    parts = []
    for root, dirs, files in os.walk(engine_kit_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        if os.path.normpath(root) == exclude or os.path.normpath(root).startswith(exclude + os.sep):
            dirs[:] = []
            continue
        for fn in files:
            if os.path.splitext(fn)[1].lower() in _SKIP_SUFFIXES:
                continue
            fp = os.path.join(root, fn)
            try:
                if os.path.getsize(fp) > _MAX_CORPUS_FILE_BYTES:
                    continue
                with open(fp, encoding="utf-8", errors="ignore") as fh:
                    parts.append(fh.read())
            except OSError:
                continue
    return "\n".join(parts)


def _check_wellformed(fname, idx, row, errors):
    label = f"{fname}[{idx}]"
    if not isinstance(row, dict):
        errors.append(f"{label}: row is not a mapping")
        return
    rid = row.get("id")
    label = f"{fname}:{rid}" if isinstance(rid, str) and rid else label
    missing = [k for k in REQUIRED_KEYS if k not in row]
    if missing:
        errors.append(f"{label}: missing required key(s): {', '.join(missing)}")
    if not isinstance(rid, str) or not rid.strip():
        errors.append(f"{label}: id must be a non-empty string")
    roles = row.get("roles")
    if not isinstance(roles, list) or not roles:
        errors.append(f"{label}: roles must be a non-empty list")
    else:
        bad = [r for r in roles if r not in ALLOWED_ROLES]
        if bad:
            errors.append(f"{label}: role(s) not in allowed set: {', '.join(map(str, bad))}")
    cond = row.get("condition")
    if not isinstance(cond, str) or not cond.strip():
        errors.append(f"{label}: condition must be a non-empty string")
    ce = row.get("current_enforcement")
    if not isinstance(ce, str) or not ENFORCEMENT_RE.match(ce):
        errors.append(f"{label}: current_enforcement {ce!r} does not match enforcement pattern")


def check(repo_root=REPO_ROOT_DEFAULT) -> dict:
    """Run every gate. Returns {ok, errors, warnings, stats}."""
    repo_root = Path(repo_root)
    inv_dir = repo_root / "engine-kit" / "tools" / "constraint-inventory"
    engine_kit_dir = repo_root / "engine-kit"
    schemas_dir = repo_root / "schemas"

    errors: list[str] = []
    warnings: list[str] = []

    if yaml is None:
        return {"ok": False, "errors": ["PyYAML is required but not installed"],
                "warnings": [], "stats": {}}
    if not inv_dir.is_dir():
        return {"ok": False, "errors": [f"inventory directory not found: {inv_dir}"],
                "warnings": [], "stats": {}}

    inventory = _load_inventory(inv_dir)
    if not inventory:
        return {"ok": False, "errors": [f"no inventory files found under {inv_dir}"],
                "warnings": [], "stats": {}}

    rows_per_file = {}
    all_rows = []  # (fname, row)
    for fname, rows in inventory:
        if not isinstance(rows, list):
            errors.append(f"{fname}: top-level YAML is not a list of rows")
            rows_per_file[fname] = 0
            continue
        rows_per_file[fname] = len(rows)
        for row in rows:
            all_rows.append((fname, row))

    # --- Check 0: per-file row-count floors (anti-bulk-deletion) ---
    for fname, floor in EXPECTED_MIN_ROWS.items():
        actual = rows_per_file.get(fname)
        if actual is None:
            errors.append(f"expected inventory file {fname} is missing")
        elif actual < floor:
            errors.append(f"{fname}: {actual} rows < expected floor {floor} (rows deleted?)")

    # --- Check 1: well-formedness ---
    for fname, rows in inventory:
        if not isinstance(rows, list):
            continue
        for idx, row in enumerate(rows):
            _check_wellformed(fname, idx, row, errors)

    # --- Check 2: globally-unique ids ---
    seen = {}
    for fname, row in all_rows:
        if not isinstance(row, dict):
            continue
        rid = row.get("id")
        if not isinstance(rid, str) or not rid:
            continue
        if rid in seen:
            errors.append(f"duplicate id '{rid}' (in {seen[rid]} and {fname})")
        else:
            seen[rid] = fname

    # --- Check 3: source-hash binding ---
    manifest_path = inv_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        errors.append(f"manifest {MANIFEST_NAME} not found in {inv_dir}")
    else:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh) or {}
        for src in manifest.get("sources", []):
            spath = src.get("path")
            expected = src.get("sha256")
            if not spath:
                errors.append(f"manifest entry missing 'path': {src!r}")
                continue
            abspath = repo_root / spath
            if not abspath.is_file():
                errors.append(f"source {spath} missing — listed in {MANIFEST_NAME} but not on disk")
                continue
            actual = _sha256(abspath)
            if actual != expected:
                errors.append(
                    f"source {spath} changed (inventory stale) — re-review + regenerate affected kernel"
                )
        # --- Check 3b: anchor shape — every row anchor must start with a manifest
        # source path AND contain " §", so a malformed/placeholder anchor can't slip
        # past the source-coverage audit's `source in anchor` filter.
        source_paths = tuple(s.get("path", "") for s in manifest.get("sources", [])
                             if s.get("path"))
        if source_paths and ENABLE_ANCHOR_SHAPE_CHECK:
            for fname, row in all_rows:
                if not isinstance(row, dict):
                    continue
                a = row.get("anchor", "")
                if not (isinstance(a, str) and a.startswith(source_paths) and " §" in a):
                    errors.append(
                        f"{fname}:{row.get('id')}: anchor {a!r} must start with a "
                        f"manifest source path and contain ' §'")

    # --- Check 4: enforcement-ref resolution (warnings) ---
    none_judgment_count = 0
    corpus = None  # built lazily on first grep-case ref
    for fname, row in all_rows:
        if not isinstance(row, dict):
            continue
        ce = row.get("current_enforcement")
        rid = row.get("id")
        if not isinstance(ce, str):
            continue
        if ce == "none-judgment":
            none_judgment_count += 1
        elif ce.startswith("schema:"):
            ref = ce.split(":", 1)[1]
            if not (schemas_dir / ref).exists():
                warnings.append(f"unresolved enforcement ref {ce} for {rid}")
        elif ce.startswith("role-card:"):
            ref = ce.split(":", 1)[1]
            if not (repo_root / ref).exists():
                warnings.append(f"unresolved enforcement ref {ce} for {rid}")
        elif ce.startswith(GREP_PREFIXES):
            rest = ce.split(":", 1)[1]
            m = _IDENT_RE.match(rest)
            sym = m.group(0) if m else ""
            if not sym:
                warnings.append(f"unresolved enforcement ref {ce} for {rid}")
                continue
            if corpus is None:
                corpus = _build_corpus(engine_kit_dir, inv_dir)
            if sym not in corpus:
                warnings.append(f"unresolved enforcement ref {sym} for {rid}")

    # --- Check 5: source-coverage audit ---
    # EXACT token match (not naive substring): a trailing-digit boundary so a required
    # '§4.2.8 #1' is NOT satisfied by an anchor that only has '§4.2.8 #10'..'#14'.
    anchors = [row.get("anchor", "") for _, row in all_rows
               if isinstance(row, dict) and isinstance(row.get("anchor"), str)]
    for source, tokens in REQUIRED_ANCHORS.items():
        src_anchors = [a for a in anchors if source in a]
        for tok in tokens:
            pat = re.escape(tok) + r"(?![0-9])"
            if not any(re.search(pat, a) for a in src_anchors):
                errors.append(f"uncovered source anchor {tok} in {source}")

    total_rows = len(all_rows)
    nj_pct = round(100.0 * none_judgment_count / total_rows, 1) if total_rows else 0.0
    stats = {
        "total_rows": total_rows,
        "rows_per_file": rows_per_file,
        "none_judgment_count": none_judgment_count,
        "none_judgment_pct": nj_pct,
        "warnings_count": len(warnings),
    }
    return {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats}


KERNEL_COVERAGE_NAME = "_kernel_coverage.yaml"
AUTHORING_KERNEL_COVERAGE_NAME = "_authoring_kernel_coverage.yaml"
ACCEPTANCE_KERNEL_COVERAGE_NAME = "_acceptance_kernel_coverage.yaml"


def _normalize_for_match(text: str) -> str:
    """Collapse whitespace + strip markdown emphasis (`` ` `` and ``*``) so a coverage phrase
    matches the kernel regardless of line-wrapping or `code`/**bold** decoration."""
    return re.sub(r"\s+", " ", re.sub(r"[`*]", "", text)).strip()


def _kernel_normative_body(kernel_path: Path) -> str:
    """Return a kernel's NORMATIVE BODY, normalized for phrase matching: the YAML front-matter
    (first ``---`` … ``---``) and the trailing non-normative sections (from the "## Deferred to the
    canonical" heading on) are stripped, so a phrase cannot resolve against metadata / the deferred
    list. Same extraction ``_kernel_coverage_for`` performs inline (kept identical)."""
    body = kernel_path.read_text(encoding="utf-8")
    if body.startswith("---"):
        fm_end = body.find("\n---", 3)
        if fm_end != -1:
            body = body[fm_end + 4:]
    cut = body.find("## Deferred to the canonical")
    if cut != -1:
        body = body[:cut]
    return _normalize_for_match(body)


def _kernel_coverage_for(cov_name: str, repo_root=REPO_ROOT_DEFAULT) -> dict:
    """Prove a KERNEL projection carries every inventory row it claims to (WP-2 constitution-core
    via ``_kernel_coverage.yaml``; WP-3 authoring-kernel via ``_authoring_kernel_coverage.yaml``).

    The coverage map (``cov_name``) binds each sourced row id to a constraint-essence phrase the
    kernel MUST contain. This asserts (per the WP-EQ design's ``coverage_status: kernel-clause``
    rule):
      (a) COMPLETENESS — every inventory row (from the map's ``source_files``) is mapped;
      (b) NO-DANGLING  — every map entry names a real inventory row;
      (c) RESOLUTION   — EVERY phrase of a row is present in the kernel's NORMATIVE BODY.
    A row's value may be a single phrase OR a LIST of phrases; with a list, EVERY phrase must
    resolve — so a multi-subpart constraint (e.g. dev = workspace_write + network-boundary +
    no-push) cannot pass on one fragment while a mandatory subpart is dropped. Matching is over the
    kernel BODY only — the YAML front-matter and the trailing non-normative sections (from the
    "## Deferred to the canonical" heading on) are stripped — so a phrase must resolve inside an
    actual clause, not metadata/pointer prose. Returns ``{ok, errors, kernel, stats}``; ``ok`` is
    False (clear error) when the kernel draft is absent — safe to run before the kernel is wired."""
    repo_root = Path(repo_root)
    inv_dir = repo_root / "engine-kit" / "tools" / "constraint-inventory"
    cov_path = inv_dir / cov_name
    if yaml is None:
        return {"ok": False, "errors": ["PyYAML is required but not installed"], "stats": {}}
    if not cov_path.is_file():
        return {"ok": False, "errors": [f"kernel-coverage map not found: {cov_path}"], "stats": {}}
    cov = yaml.safe_load(cov_path.read_text(encoding="utf-8")) or {}
    kernel_rel = cov.get("kernel")
    source_files = set(cov.get("source_files") or [])
    cmap = cov.get("rows") or {}
    if not kernel_rel or not source_files or not isinstance(cmap, dict):
        return {"ok": False, "stats": {},
                "errors": ["coverage map must define 'kernel', 'source_files', and 'rows'"]}
    kernel_path = repo_root / kernel_rel
    if not kernel_path.is_file():
        return {"ok": False, "kernel": kernel_rel, "stats": {},
                "errors": [f"kernel not found: {kernel_rel} (draft not present — nothing to check)"]}
    # Match over the NORMATIVE BODY only: drop the YAML front-matter (first '---' … '---') and the
    # trailing non-normative sections (from the "## Deferred to the canonical" heading on), so a
    # phrase cannot resolve against metadata / the deferred list / the gaps section.
    body = kernel_path.read_text(encoding="utf-8")
    if body.startswith("---"):
        fm_end = body.find("\n---", 3)
        if fm_end != -1:
            body = body[fm_end + 4:]
    cut = body.find("## Deferred to the canonical")
    if cut != -1:
        body = body[:cut]
    kernel_norm = _normalize_for_match(body)

    # The inventory row ids in the constitution source files the kernel replaces.
    inv_ids = set()
    for name, rows in _load_inventory(inv_dir):
        if name in source_files and isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and isinstance(r.get("id"), str):
                    inv_ids.add(r["id"])

    errors: list[str] = []
    uncovered = sorted(i for i in inv_ids if i not in cmap)            # (a)
    for i in uncovered:
        errors.append(f"uncovered constraint (no kernel-coverage entry): {i}")
    dangling = sorted(i for i in cmap if i not in inv_ids)             # (b)
    for i in dangling:
        errors.append(f"coverage map references unknown inventory id: {i}")
    missing_phrase = []                                                # (c)
    for rid in sorted(set(cmap) & inv_ids):
        raw = cmap[rid]
        phrases = raw if isinstance(raw, list) else [raw]
        norm = [(p, _normalize_for_match(str(p))) for p in phrases]
        if not norm or any(not n for _, n in norm):
            errors.append(f"empty coverage phrase for {rid}")
            missing_phrase.append(rid)
            continue
        absent = [orig for orig, n in norm if n not in kernel_norm]   # EVERY phrase must resolve
        if absent:
            errors.append(f"kernel missing clause for {rid} (subpart not carried): {absent!r}")
            missing_phrase.append(rid)

    total = len(inv_ids)
    covered = total - len(uncovered) - len(missing_phrase)
    stats = {
        "total": total, "covered": covered,
        "coverage_pct": round(100.0 * covered / total, 1) if total else 0.0,
        "uncovered_rows": uncovered, "missing_phrase": sorted(missing_phrase),
        "dangling": dangling,
    }
    return {"ok": not errors, "errors": errors, "kernel": kernel_rel, "stats": stats}


def check_kernel_coverage(repo_root=REPO_ROOT_DEFAULT) -> dict:
    """WP-2: the constitution-core kernel vs its constitution inventory rows (01+02)."""
    return _kernel_coverage_for(KERNEL_COVERAGE_NAME, repo_root=repo_root)


def check_authoring_kernel_coverage(repo_root=REPO_ROOT_DEFAULT) -> dict:
    """WP-3: the authoring-kernel vs the doc-governance inventory rows (03-doc-governance.yaml)."""
    return _kernel_coverage_for(AUTHORING_KERNEL_COVERAGE_NAME, repo_root=repo_root)


def _enforcement_resolves(ce: str, repo_root: Path, _cache: dict) -> bool:
    """True iff a ``current_enforcement`` string resolves to a REAL backstop — a schema:/role-card:
    file that exists, or a driver:/validator:/adapter:/campaign: symbol present in the engine-kit
    corpus (same resolution check() performs, but treated as a HARD requirement here). ``none-judgment``
    is not a backstop (False). This is what makes ``bound-elsewhere`` airtight: a constraint may be
    excused from the kernel ONLY against an enforcement that actually exists, so a fabricated inventory
    ``current_enforcement`` (which check() only WARNS about) cannot launder a dropped constraint."""
    if not isinstance(ce, str) or ce == "none-judgment":
        return False
    if ce.startswith("schema:"):
        return (repo_root / "schemas" / ce.split(":", 1)[1]).exists()
    if ce.startswith("role-card:"):
        return (repo_root / ce.split(":", 1)[1]).exists()
    if ce.startswith(GREP_PREFIXES):
        m = _IDENT_RE.match(ce.split(":", 1)[1])
        sym = m.group(0) if m else ""
        if not sym:
            return False
        if "corpus" not in _cache:
            _cache["corpus"] = _build_corpus(
                repo_root / "engine-kit",
                repo_root / "engine-kit" / "tools" / "constraint-inventory")
        # Require an actual DEFINITION (``def <sym>(``), not a bare substring: a bare ``sym in corpus``
        # would let a fabricated ``driver:_acceptance`` launder past (it is a substring of
        # ``_acceptance_authoritative``). Every bound-elsewhere enforcement is a driver/validator
        # method, so a def-site match is both correct and airtight (Codex R6-B1).
        return re.search(r"\bdef\s+" + re.escape(sym) + r"\s*\(", _cache["corpus"]) is not None
    return False


def check_acceptance_kernel_coverage(repo_root=REPO_ROOT_DEFAULT) -> dict:
    """WP-4: prove the acceptance-kernel carries every Acceptance-verdict-affecting constraint
    anchored in the two whole-file reads WP-4B retires (process/delivery-loop.md +
    process/role-skill-model.md), so retiring those reads drops nothing.

    Unlike WP-2/WP-3 (whole-file kernels, completeness = every row of the replaced file), the
    acceptance-kernel is a TARGETED judge-instruction projection. Its COMPLETENESS scope is the set
    of inventory rows ANCHORED in ``inlined_files`` AND tagged ``role``; each MUST be classified in
    ``closure_rows`` as exactly one disposition:
      - ``kernel-clause``   : every mapped phrase resolves in the kernel normative body (the catch);
      - ``bound-elsewhere`` : ``enforced_by`` MUST equal the inventory row's ``current_enforcement``
                              AND that enforcement MUST be a real programmatic symbol — a
                              ``none-judgment`` row (no backstop) CANNOT be bound-elsewhere and MUST
                              be kernel-clause. This is what makes "INLINED" sound: a constraint is
                              dropped from the kernel ONLY when an independent driver/validator/schema
                              symbol (recorded in the Codex-gated, source-hash-bound inventory) catches
                              it regardless of the judge's read.
    ``supplemental_rows`` (the six judge-instruction gaps from the still-resolver-bound
    role-cards/acceptance-agent.md) are NOT completeness-scoped — their canonical is not retired — but
    each mapped phrase MUST resolve in the kernel so the projected prompt is proven self-contained.

    Asserts: (a) completeness — every scoped row classified; (b) no-dangling — every classified row is
    a real scoped row; (c) resolution / binding per the rules above; (d) supplemental rows are real
    ``role`` inventory ids whose phrases resolve. Returns ``{ok, errors, kernel, stats}``."""
    repo_root = Path(repo_root)
    inv_dir = repo_root / "engine-kit" / "tools" / "constraint-inventory"
    cov_path = inv_dir / ACCEPTANCE_KERNEL_COVERAGE_NAME
    if yaml is None:
        return {"ok": False, "errors": ["PyYAML is required but not installed"], "stats": {}}
    if not cov_path.is_file():
        return {"ok": False, "errors": [f"acceptance-kernel-coverage map not found: {cov_path}"],
                "stats": {}}
    cov = yaml.safe_load(cov_path.read_text(encoding="utf-8")) or {}
    kernel_rel = cov.get("kernel")
    role = cov.get("role")
    inlined_files = tuple(cov.get("inlined_files") or [])
    inventory_files = set(cov.get("inventory_files") or [])
    closure_rows = cov.get("closure_rows") or {}
    supplemental_rows = cov.get("supplemental_rows") or {}
    if not (kernel_rel and role and inlined_files and inventory_files
            and isinstance(closure_rows, dict) and isinstance(supplemental_rows, dict)):
        return {"ok": False, "stats": {}, "errors": [
            "coverage map must define 'kernel', 'role', 'inlined_files', 'inventory_files', "
            "'closure_rows', and 'supplemental_rows'"]}
    kernel_path = repo_root / kernel_rel
    if not kernel_path.is_file():
        return {"ok": False, "kernel": kernel_rel, "stats": {},
                "errors": [f"kernel not found: {kernel_rel} (draft not present — nothing to check)"]}
    kernel_norm = _kernel_normative_body(kernel_path)

    # Inventory rows: full index (for supplemental id validity) + per-id row dicts.
    inv_by_id: dict[str, dict] = {}
    for name, rows in _load_inventory(inv_dir):
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and isinstance(r.get("id"), str):
                    inv_by_id[r["id"]] = {**r, "_inv_file": name}
    # COMPLETENESS scope: rows anchored in an inlined file AND tagged `role`, restricted to the
    # declared inventory_files (so a re-homed row is caught by no-dangling, not silently scoped out).
    scope = {
        rid: r for rid, r in inv_by_id.items()
        if r.get("_inv_file") in inventory_files
        and str(r.get("anchor", "")).startswith(inlined_files)
        and role in (r.get("roles") or [])
    }

    errors: list[str] = []

    def _resolve_phrases(rid, raw, where):
        phrases = raw if isinstance(raw, list) else [raw]
        norm = [(p, _normalize_for_match(str(p))) for p in phrases]
        if not norm or any(not n for _, n in norm):
            errors.append(f"empty coverage phrase for {where} {rid}")
            return False
        absent = [orig for orig, n in norm if n not in kernel_norm]
        if absent:
            errors.append(f"kernel missing clause for {where} {rid} (subpart not carried): {absent!r}")
            return False
        return True

    # (a) completeness + (b) no-dangling over the closure scope.
    for rid in sorted(set(scope) - set(closure_rows)):
        errors.append(f"uncovered Acceptance constraint (no closure_rows entry): {rid} "
                      f"[{scope[rid].get('anchor')}]")
    for rid in sorted(set(closure_rows) - set(scope)):
        why = ("unknown inventory id" if rid not in inv_by_id else
               "not in completeness scope (anchor not in inlined_files, role absent, or wrong "
               "inventory_file)")
        errors.append(f"closure_rows references a row that is not a scoped Acceptance constraint: "
                      f"{rid} ({why})")

    # (c) per-row disposition resolution / binding.
    n_kernel_clause = n_bound = 0
    enf_cache: dict = {}
    for rid in sorted(set(closure_rows) & set(scope)):
        entry = closure_rows[rid] or {}
        disp = entry.get("disposition")
        if disp == "kernel-clause":
            n_kernel_clause += 1
            if "phrase" not in entry:
                errors.append(f"kernel-clause row {rid} has no 'phrase'")
            else:
                _resolve_phrases(rid, entry["phrase"], "closure")
        elif disp == "bound-elsewhere":
            n_bound += 1
            ce = scope[rid].get("current_enforcement")
            declared = entry.get("enforced_by")
            if ce == "none-judgment":
                errors.append(f"bound-elsewhere row {rid} has current_enforcement 'none-judgment' "
                              f"(no backstop) — it MUST be kernel-clause")
            elif not declared:
                errors.append(f"bound-elsewhere row {rid} has no 'enforced_by'")
            elif declared != ce:
                errors.append(f"bound-elsewhere row {rid}: enforced_by {declared!r} != inventory "
                              f"current_enforcement {ce!r}")
            elif not _enforcement_resolves(ce, repo_root, enf_cache):
                # The enforcement must actually EXIST — a fabricated current_enforcement (which the
                # base inventory gate only WARNS about) cannot launder a dropped constraint here.
                errors.append(f"bound-elsewhere row {rid}: enforcement {ce!r} does not resolve to a "
                              f"real schema/role-card file or engine-kit symbol — cannot excuse it "
                              f"from the kernel")
        else:
            errors.append(f"closure row {rid} has invalid disposition {disp!r} "
                          f"(expected kernel-clause | bound-elsewhere)")

    # (d) supplemental rows: real `role` inventory ids whose phrases resolve (no completeness).
    for rid in sorted(supplemental_rows):
        row = inv_by_id.get(rid)
        if row is None:
            errors.append(f"supplemental_rows references unknown inventory id: {rid}")
            continue
        if role not in (row.get("roles") or []):
            errors.append(f"supplemental row {rid} is not tagged role {role!r}")
            continue
        _resolve_phrases(rid, supplemental_rows[rid], "supplemental")

    stats = {
        "closure_scope": len(scope),
        "closure_mapped": len(set(closure_rows) & set(scope)),
        "kernel_clause": n_kernel_clause,
        "bound_elsewhere": n_bound,
        "supplemental": len(supplemental_rows),
        "inlined_files": list(inlined_files),
    }
    return {"ok": not errors, "errors": errors, "kernel": kernel_rel, "stats": stats}


def _merged_coverage(repo_root, cov_fn) -> dict:
    """Run a kernel-coverage check MERGED with the inventory/source-hash gate, failing if either
    fails. The kernel is a projection of the inventory, which is bound to the canonical source
    hashes; a coverage pass is meaningful only if ``check()`` (source-hash freshness, well-
    formedness, row floors) ALSO passes — a stale canonical means a stale kernel (Codex fidelity
    gate). So both run and any failure fails the merged result."""
    base = check(repo_root=repo_root)
    cov = cov_fn(repo_root=repo_root)
    return {
        "ok": base["ok"] and cov["ok"],
        "kernel": cov.get("kernel"),
        "errors": (["[inventory/source-hash gate] " + e for e in base["errors"]]
                   + cov.get("errors", [])),
        "stats": cov.get("stats", {}),
    }


def _print_kernel_coverage(result: dict) -> None:
    stats = result.get("stats", {})
    print(f"kernel_coverage ({result.get('kernel', '?')}): "
          f"{'OK' if result['ok'] else 'NOT OK'}")
    if "closure_scope" in stats:  # WP-4 acceptance-kernel (disposition-based) stats shape
        print(f"  closure scope     : {stats.get('closure_scope')} "
              f"(mapped {stats.get('closure_mapped')})")
        print(f"  kernel-clause     : {stats.get('kernel_clause')}")
        print(f"  bound-elsewhere   : {stats.get('bound_elsewhere')}")
        print(f"  supplemental      : {stats.get('supplemental')}")
    elif stats:                   # WP-2/WP-3 whole-file coverage stats shape
        print(f"  inventory rows    : {stats.get('total')}")
        print(f"  covered           : {stats.get('covered')} ({stats.get('coverage_pct')}%)")
    for e in result.get("errors", []):
        print(f"    - {e}")


def _print_human(result: dict) -> None:
    stats = result.get("stats", {})
    print(f"kernel_equivalence: {'OK' if result['ok'] else 'NOT OK'}")
    if stats:
        print(f"  total_rows           : {stats.get('total_rows')}")
        print(f"  none_judgment_count  : {stats.get('none_judgment_count')} "
              f"({stats.get('none_judgment_pct')}%)")
        print(f"  warnings_count       : {stats.get('warnings_count')}")
        rpf = stats.get("rows_per_file", {})
        if rpf:
            print("  rows_per_file:")
            for name in sorted(rpf):
                print(f"    {name}: {rpf[name]}")
    if result["errors"]:
        print(f"  errors ({len(result['errors'])}):")
        for e in result["errors"]:
            print(f"    - {e}")
    if result["warnings"]:
        print(f"  warnings ({len(result['warnings'])}):")
        for w in result["warnings"]:
            print(f"    - {w}")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="WP-EQ constraint-equivalence gate")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--repo-root", default=str(REPO_ROOT_DEFAULT),
                        help="repo root (parent of engine-kit)")
    parser.add_argument("--kernel-coverage", action="store_true",
                        help="WP-2: report constitution-core kernel coverage vs the inventory "
                             "(MERGED with the inventory/source-hash gate)")
    parser.add_argument("--authoring-kernel-coverage", action="store_true",
                        help="WP-3: report authoring-kernel coverage vs the doc-governance "
                             "inventory (MERGED with the inventory/source-hash gate)")
    parser.add_argument("--acceptance-kernel-coverage", action="store_true",
                        help="WP-4: report acceptance-kernel coverage vs the Acceptance-tagged "
                             "delivery-loop + role-skill inventory rows (MERGED with the "
                             "inventory/source-hash gate)")
    args = parser.parse_args(argv)
    if args.kernel_coverage or args.authoring_kernel_coverage or args.acceptance_kernel_coverage:
        # Each kernel is a projection of the inventory, bound to the canonical source hashes. A
        # coverage pass is meaningful only if the inventory gate (source-hash freshness, well-
        # formedness, row floors) ALSO passes — a stale canonical means a stale kernel. So the
        # coverage CLIs run BOTH and fail if either fails (Codex WP-2/WP-3/WP-4 fidelity gate).
        if args.acceptance_kernel_coverage:
            cov_fn = check_acceptance_kernel_coverage
        elif args.authoring_kernel_coverage:
            cov_fn = check_authoring_kernel_coverage
        else:
            cov_fn = check_kernel_coverage
        merged = _merged_coverage(args.repo_root, cov_fn)
        if args.json:
            print(json.dumps(merged, indent=2, ensure_ascii=False, sort_keys=True))
        else:
            _print_kernel_coverage(merged)
        return 0 if merged["ok"] else 1
    result = check(repo_root=args.repo_root)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        _print_human(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
