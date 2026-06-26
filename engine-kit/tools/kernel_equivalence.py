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
        "§1.7-A", "§1.7-B", "§1.7-C", "§1.7-D", "§1.7-E",
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
    "01-constitution-core.yaml": 24,
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
        if name == MANIFEST_NAME:
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
    args = parser.parse_args(argv)
    result = check(repo_root=args.repo_root)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        _print_human(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
