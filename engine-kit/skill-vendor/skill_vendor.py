#!/usr/bin/env python3
"""skill_vendor — script the manual skill-vendoring + integrity-verify flow.

Mechanizes the supply-chain discipline in the plan (archive
2026-06-15-v2-loop-engine-plan.md §4.1 facet B): vendored skills are COPIED and
PINNED by commit, never runtime-fetched; each `skills/vendored/<id>/` retains the
upstream LICENSE + a `_provenance.yaml`; integrity is locked in
`skills/skills.lock`. Two subcommands:

  verify [<id>...]  (OFFLINE — the priority)
      For each vendored skill, recompute its tree hash + per-file hashes and
      compare to skills/skills.lock AND skills/vendored/<id>/_provenance.yaml.
      Report match/mismatch; exit non-zero on any mismatch. No network.

  vendor <id>       (uses git; NOT exercised in tests, never run against the
      live repo in this task)
      Read the catalog entry (repo+commit+path) from skills/registry.yaml,
      shallow-fetch at the pinned commit, copy the skill folder, preserve the
      upstream LICENSE, write _provenance.yaml, and update skills.lock.

TREE-HASH SCHEME (must reproduce the committed skills.lock byte-for-byte):
    per_file_hex = sha256(file_bytes).hexdigest()             # == `shasum -a 256`
    files = every file under the skill dir EXCLUDING _provenance.yaml,
            named as "./<relpath>" with POSIX ('/') separators
    order = sorted(files)                                      # == C-locale sort
    manifest = "".join(f"{per_file_hex}  {path}\n" for path in order)
                                                              # TWO spaces (shasum text mode)
    tree_sha256 = sha256(manifest.encode("utf-8")).hexdigest()
  Equivalent shell:
    find . -type f ! -name _provenance.yaml | sort | xargs shasum -a 256 | shasum -a 256

Determinism contract: `verify` is a pure function over the on-disk skill tree +
the lock + provenance files. No network, no LLM, no clock/random. (`vendor` is the
ONE non-deterministic path — it shells out to git — and is never run in tests.)

CLI:
    python skill_vendor.py verify [<id> ...]   exit 0 if all match, !0 on mismatch
    python skill_vendor.py vendor <id>         (git; not run in this task)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - import guard
    sys.stderr.write(
        "skill_vendor: PyYAML is required (pip install -r requirements.txt)\n"
    )
    raise


# --------------------------------------------------------------------------- #
# Locate the skills/ tree. engine-kit/ sits next to skills/, so walk up from
# this file to find a directory that contains skills/skills.lock.
# --------------------------------------------------------------------------- #
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

PROVENANCE_FILENAME = "_provenance.yaml"


def _find_repo_root() -> Optional[str]:
    """Walk parent dirs looking for one that contains skills/skills.lock."""
    cur = _THIS_DIR
    while True:
        if os.path.isfile(os.path.join(cur, "skills", "skills.lock")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


REPO_ROOT = _find_repo_root()


# --------------------------------------------------------------------------- #
# Core hashing — the byte-for-byte reproduction of the bash scheme.
# --------------------------------------------------------------------------- #
def file_sha256(path: str) -> str:
    """sha256 of a file's raw bytes; identical to `shasum -a 256 <file>`."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def enumerate_files(skill_dir: str) -> list[str]:
    """All files under skill_dir EXCLUDING _provenance.yaml, as sorted
    './<relpath>' POSIX-separated strings. sorted() over these ASCII paths
    equals C-locale `sort` (the bash scheme), so ordering matches the lock."""
    rels: list[str] = []
    for root, _dirs, names in os.walk(skill_dir):
        for name in names:
            if name == PROVENANCE_FILENAME:
                continue
            abspath = os.path.join(root, name)
            rel = os.path.relpath(abspath, skill_dir)
            rel_posix = rel.replace(os.sep, "/")
            rels.append(f"./{rel_posix}")
    rels.sort()
    return rels


def per_file_hashes(skill_dir: str) -> list[tuple[str, str]]:
    """Return [(./<relpath>, per_file_hex)] in tree order (sorted by path)."""
    out: list[tuple[str, str]] = []
    for rel in enumerate_files(skill_dir):
        # rel is "./<relpath>"; strip the leading "./" for the on-disk join.
        on_disk = os.path.join(skill_dir, rel[2:])
        out.append((rel, file_sha256(on_disk)))
    return out


def manifest_text(per_file: list[tuple[str, str]]) -> str:
    """Build the shasum-text-mode manifest: '<hex>  <path>\\n' (TWO spaces)."""
    return "".join(f"{hex_}  {path}\n" for path, hex_ in per_file)


def tree_sha256(skill_dir: str) -> str:
    """Recompute the tree_sha256 for a vendored skill directory.

    tree = sha256( manifest_text ).hexdigest(), where manifest_text is the
    shasum-text-mode listing of every file (except _provenance.yaml) in
    C-locale path order. Reproduces `find ... | sort | xargs shasum | shasum`."""
    per_file = per_file_hashes(skill_dir)
    return hashlib.sha256(manifest_text(per_file).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Lock + registry I/O.
# --------------------------------------------------------------------------- #
def _skills_dir(repo_root: Optional[str] = None) -> str:
    root = repo_root or REPO_ROOT
    if not root:
        raise FileNotFoundError(
            "skills/skills.lock not found at or above engine-kit/ "
            f"(searched from {_THIS_DIR})"
        )
    return os.path.join(root, "skills")


class LockfileError(Exception):
    """skills.lock could not be parsed as YAML (corrupt lockfile).

    Surfaced as a clean, non-zero CLI error — never a raw yaml traceback."""


def load_lock(repo_root: Optional[str] = None) -> dict:
    path = os.path.join(_skills_dir(repo_root), "skills.lock")
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            reason = str(exc).replace("\n", " ").strip()
            raise LockfileError(f"skills.lock: unparseable ({reason})") from exc
    return data or {}


def load_registry(repo_root: Optional[str] = None) -> dict:
    path = os.path.join(_skills_dir(repo_root), "registry.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_provenance(skill_dir: str) -> Optional[dict]:
    path = os.path.join(skill_dir, PROVENANCE_FILENAME)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# --------------------------------------------------------------------------- #
# verify — the offline integrity check.
# --------------------------------------------------------------------------- #
@dataclass
class SkillResult:
    skill_id: str
    ok: bool
    messages: list[str] = field(default_factory=list)

    def render(self) -> str:
        status = "OK   " if self.ok else "FAIL "
        head = f"[{status}] {self.skill_id}"
        if not self.messages:
            return head
        return head + "\n" + "\n".join(f"        - {m}" for m in self.messages)


@dataclass
class VerifyReport:
    results: list[SkillResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results) and bool(self.results)

    def render(self) -> str:
        lines = [r.render() for r in self.results]
        n_fail = sum(1 for r in self.results if not r.ok)
        if not self.results:
            lines.append("skill_vendor: no skills to verify.")
        summary = (
            f"\nverified {len(self.results)} skill(s); "
            f"{n_fail} mismatch(es)."
        )
        return "\n".join(lines) + summary


def verify_skill(skill_id: str, skill_dir: str, lock_entry: Optional[dict]) -> SkillResult:
    """Verify one vendored skill against its lock entry + its _provenance.yaml.

    Checks (all must pass):
      1. The skill directory exists.
      2. recomputed tree_sha256 == skills.lock[id].tree_sha256.
      3. _provenance.yaml exists and its tree_sha256 matches the recomputed one.
      4. _provenance.yaml per-file hashes match the recomputed per-file hashes
         (same file set, same hex) — catches a single tampered/added/removed file.
    """
    res = SkillResult(skill_id=skill_id, ok=True)

    if not os.path.isdir(skill_dir):
        res.ok = False
        res.messages.append(f"skill directory missing: {skill_dir}")
        return res

    computed_tree = tree_sha256(skill_dir)
    computed_files = dict(per_file_hashes(skill_dir))

    # (2) lock tree hash
    if lock_entry is None:
        res.ok = False
        res.messages.append("no entry in skills.lock for this id")
    else:
        locked = lock_entry.get("tree_sha256")
        if locked != computed_tree:
            res.ok = False
            res.messages.append(
                f"tree_sha256 mismatch vs skills.lock: "
                f"locked={locked} computed={computed_tree}"
            )

    # (3)+(4) provenance
    prov = load_provenance(skill_dir)
    if prov is None:
        res.ok = False
        res.messages.append(f"{PROVENANCE_FILENAME} missing")
    else:
        prov_tree = prov.get("tree_sha256")
        if prov_tree != computed_tree:
            res.ok = False
            res.messages.append(
                f"tree_sha256 mismatch vs {PROVENANCE_FILENAME}: "
                f"provenance={prov_tree} computed={computed_tree}"
            )
        prov_files = {}
        for entry in prov.get("files", []) or []:
            if isinstance(entry, dict) and "path" in entry:
                # Provenance lists paths WITHOUT the "./" prefix; normalise so we
                # compare against the "./<relpath>" keys from per_file_hashes.
                key = entry["path"]
                key = key if key.startswith("./") else f"./{key}"
                prov_files[key] = entry.get("sha256")
        if prov_files:
            comp_paths = set(computed_files)
            prov_paths = set(prov_files)
            for missing in sorted(prov_paths - comp_paths):
                res.ok = False
                res.messages.append(f"file in provenance but absent on disk: {missing}")
            for extra in sorted(comp_paths - prov_paths):
                res.ok = False
                res.messages.append(f"file on disk but absent in provenance: {extra}")
            for path in sorted(prov_paths & comp_paths):
                if prov_files[path] != computed_files[path]:
                    res.ok = False
                    res.messages.append(
                        f"per-file sha256 mismatch @ {path}: "
                        f"provenance={prov_files[path]} computed={computed_files[path]}"
                    )

    return res


def verify(skill_ids: Optional[list[str]] = None, repo_root: Optional[str] = None) -> VerifyReport:
    """Verify all vendored skills (or a subset by id) against the lock +
    provenance. Pure/offline. Returns a VerifyReport (ok iff every skill OK)."""
    lock = load_lock(repo_root)
    lock_skills = lock.get("skills", {}) or {}
    skills_dir = _skills_dir(repo_root)
    vendored_dir = os.path.join(skills_dir, "vendored")

    if skill_ids:
        ids = list(skill_ids)
    else:
        # Default: every id present in the lock (deterministic order).
        ids = sorted(lock_skills.keys())

    report = VerifyReport()
    for sid in ids:
        skill_dir = os.path.join(vendored_dir, sid)
        report.results.append(verify_skill(sid, skill_dir, lock_skills.get(sid)))
    return report


# --------------------------------------------------------------------------- #
# vendor — the git-using copy/pin/lock path. NOT run in tests; never run against
# the live repo in this task. Implemented for completeness per the plan.
# --------------------------------------------------------------------------- #
def _catalog_entry(skill_id: str, repo_root: Optional[str] = None) -> dict:
    reg = load_registry(repo_root)
    skills = reg.get("skills", {}) or {}
    if skill_id not in skills:
        raise KeyError(
            f"skill id {skill_id!r} not found in skills/registry.yaml `skills:`"
        )
    return skills[skill_id]


def _git(args: list[str], cwd: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def vendor(skill_id: str, repo_root: Optional[str] = None, *, retrieved_at: Optional[str] = None) -> dict:
    """Vendor a skill at its pinned commit (USES GIT — network).

    Steps (per plan §4.1 facet B):
      1. Read the catalog entry (source.repo/url/commit/path) from registry.yaml.
      2. Shallow-fetch the repo at the pinned commit into a temp dir.
      3. Copy the skill folder to skills/vendored/<id>/ (LICENSE preserved by the
         copy; if the skill subdir lacks a LICENSE, copy the repo-root LICENSE).
      4. Recompute tree_sha256 + per-file hashes; write _provenance.yaml.
      5. Update skills/skills.lock with {repo, commit, path, license, tree_sha256}.

    Returns the new lock entry. NOTE: this mutates skills/; callers in this task
    must NOT invoke it against the committed ground truth. `retrieved_at` is
    INJECTABLE so the function has no hidden clock dependence; if None, the
    caller is responsible for supplying a timestamp (vendor is not a pure path).
    """
    root = repo_root or REPO_ROOT
    if not root:
        raise FileNotFoundError("repo root (containing skills/skills.lock) not found")

    entry = _catalog_entry(skill_id, root)
    src = entry.get("source", {}) or {}
    repo = src.get("repo")
    url = src.get("url") or (f"https://github.com/{repo}" if repo else None)
    commit = src.get("commit")
    sub_path = src.get("path")
    license_name = entry.get("license", "MIT")
    if not (url and commit and sub_path):
        raise ValueError(
            f"catalog entry for {skill_id!r} is missing source.url/commit/path"
        )

    skills_dir = _skills_dir(root)
    dest_dir = os.path.join(skills_dir, "vendored", skill_id)

    with tempfile.TemporaryDirectory(prefix="skill-vendor-") as tmp:
        clone = os.path.join(tmp, "clone")
        os.makedirs(clone, exist_ok=True)
        # Shallow fetch of the single pinned commit (no full history).
        _git(["init", "-q"], cwd=clone)
        _git(["remote", "add", "origin", url], cwd=clone)
        _git(["fetch", "-q", "--depth", "1", "origin", commit], cwd=clone)
        _git(["checkout", "-q", "FETCH_HEAD"], cwd=clone)

        src_skill = os.path.join(clone, sub_path)
        if not os.path.isdir(src_skill):
            raise FileNotFoundError(
                f"pinned path not found in upstream: {sub_path} @ {commit}"
            )

        # Fresh copy of the skill folder (excludes any upstream VCS metadata).
        if os.path.isdir(dest_dir):
            shutil.rmtree(dest_dir)
        shutil.copytree(
            src_skill, dest_dir, ignore=shutil.ignore_patterns(".git", PROVENANCE_FILENAME)
        )

        # Preserve LICENSE: prefer one inside the skill folder; else repo-root.
        if not os.path.isfile(os.path.join(dest_dir, "LICENSE")):
            root_license = os.path.join(clone, "LICENSE")
            if os.path.isfile(root_license):
                shutil.copy2(root_license, os.path.join(dest_dir, "LICENSE"))

    # Recompute integrity over the freshly vendored tree.
    per_file = per_file_hashes(dest_dir)
    tree = hashlib.sha256(manifest_text(per_file).encode("utf-8")).hexdigest()

    provenance = {
        "id": skill_id,
        "source": {"repo": repo, "url": url, "commit": commit, "path": sub_path},
        "license": license_name,
        "retrieved_at": retrieved_at,
        "role_default_for": entry.get("role_default_for"),
        "tree_sha256": tree,
        "files": [{"path": p[2:], "sha256": h} for p, h in per_file],
    }
    with open(os.path.join(dest_dir, PROVENANCE_FILENAME), "w", encoding="utf-8") as fh:
        yaml.safe_dump(provenance, fh, sort_keys=False)

    # Update the lockfile entry for this id.
    lock = load_lock(root)
    lock.setdefault("skills", {})
    lock["skills"][skill_id] = {
        "repo": repo,
        "commit": commit,
        "path": sub_path,
        "license": license_name,
        "tree_sha256": tree,
    }
    with open(os.path.join(skills_dir, "skills.lock"), "w", encoding="utf-8") as fh:
        yaml.safe_dump(lock, fh, sort_keys=False)

    return lock["skills"][skill_id]


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vendor + integrity-verify aidazi skills (deterministic "
        "verify; git-using vendor).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify", help="OFFLINE: re-hash vendored skills, compare to skills.lock + provenance"
    )
    p_verify.add_argument(
        "ids", nargs="*", help="skill ids to verify (default: all in skills.lock)"
    )

    p_vendor = sub.add_parser(
        "vendor", help="USES GIT: fetch a skill at its pinned commit, copy, write provenance + lock"
    )
    p_vendor.add_argument("id", help="skill id to vendor (must exist in registry.yaml)")
    p_vendor.add_argument(
        "--retrieved-at",
        default=None,
        help="ISO timestamp to record as retrieved_at (vendor is not a pure path)",
    )

    args = parser.parse_args(argv)

    if args.cmd == "verify":
        try:
            report = verify(args.ids or None)
        except LockfileError as exc:
            sys.stderr.write(f"skill_vendor: {exc}\n")
            return 1
        print(report.render())
        return 0 if report.ok else 1

    if args.cmd == "vendor":
        entry = vendor(args.id, retrieved_at=args.retrieved_at)
        print(f"vendored {args.id}: tree_sha256={entry['tree_sha256']}")
        return 0

    return 2  # pragma: no cover - argparse enforces a subcommand


if __name__ == "__main__":
    sys.exit(main())
