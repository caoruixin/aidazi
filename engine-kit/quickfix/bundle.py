"""Ephemeral, out-of-tree Quick-Fix session bundle.

The bundle is the cwd a Quick-Fix harness session is launched in (Commit 3). It lives
OUTSIDE the repo tree (a sibling) so the harness's cold-start directory walk never reaches
the repo's root memory file. Its minimal memory file references ONLY local copies of the
canonical anti-hardcode kernel + the lane spec + the request — so the session's cold-start
context is those three, not the full governance chain.

Copy-at-launch (not @-import across dirs): the kernel and lane spec are COPIED fresh from
their canonical sources each launch — a build artifact, never a maintained duplicate — so
there is a single source of truth and no cross-directory import-resolution risk.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass

from . import paths
from .errors import QuickfixError

# harness id -> the memory filename that harness auto-loads from cwd at cold-start.
_MEMORY_FILENAME = {
    "claude_code": "CLAUDE.md",
    "codex": "AGENTS.md",
    "cursor": os.path.join(".cursor", "rules", "quickfix.mdc"),
}


def memory_filename_for(harness: str) -> str:
    return _MEMORY_FILENAME.get(harness, "CLAUDE.md")


def default_bundle_root(repo_dir: str) -> str:
    repo_dir = os.path.abspath(repo_dir)
    parent = os.path.dirname(repo_dir)
    base = os.path.basename(repo_dir)
    return os.path.join(parent, f"{base}-quickfix-bundles")


@dataclass
class Bundle:
    bundle_dir: str
    memory_file: str
    kernel_file: str
    lane_file: str
    request_file: str


_MEMORY_TEMPLATE = """\
# Quick-Fix lane session — minimal context

You are running in the aidazi **Quick-Fix lane**, NOT a normal Full session. Your entire
governing context is the three local files in this bundle — load them and nothing else
from the framework governance chain:

- `./anti-hardcode-kernel.md` — the §1.7 anti-hardcode lens (the one hard constraint).
- `./quickfix-lane.md` — the lane protocol (eligibility, protected surfaces, escalation).
- `./request.json` — THIS task and its `allowed_globs` (your approved scope).

Rules (from the protocol): make ONLY the change in the request, ONLY within
`allowed_globs`; do not touch any protected surface; if anything expands the scope,
introduces a new decision, or you cannot prove eligibility — STOP and escalate (do not
widen scope). Edits happen in the attached worktree; the lane runs the guard, the targeted
verification, and the guard again, then commits the result on a `quickfix/<request_id>`
branch. Do not commit yourself.
"""


def materialize(framework_root: str, request, *, dest_root: str, harness: str) -> Bundle:
    """Create the bundle dir and populate it from canonical sources. Returns a Bundle."""
    os.makedirs(dest_root, exist_ok=True)
    bundle_dir = os.path.join(dest_root, request.request_id)
    if os.path.exists(bundle_dir):
        shutil.rmtree(bundle_dir)
    os.makedirs(bundle_dir)

    kernel_src = paths.kernel_path(framework_root)
    lane_src = paths.lane_spec_path(framework_root)
    for src, label in ((kernel_src, "anti-hardcode kernel"), (lane_src, "lane spec")):
        if not os.path.isfile(src):
            raise QuickfixError(f"cannot materialize bundle: {label} missing at {src}")

    kernel_file = os.path.join(bundle_dir, "anti-hardcode-kernel.md")
    lane_file = os.path.join(bundle_dir, "quickfix-lane.md")
    request_file = os.path.join(bundle_dir, "request.json")
    shutil.copyfile(kernel_src, kernel_file)
    shutil.copyfile(lane_src, lane_file)
    with open(request_file, "w", encoding="utf-8") as fh:
        json.dump(request.raw, fh, indent=2, sort_keys=True)
        fh.write("\n")

    mem_rel = memory_filename_for(harness)
    memory_file = os.path.join(bundle_dir, mem_rel)
    os.makedirs(os.path.dirname(memory_file), exist_ok=True)
    with open(memory_file, "w", encoding="utf-8") as fh:
        fh.write(_MEMORY_TEMPLATE)

    return Bundle(bundle_dir=bundle_dir, memory_file=memory_file,
                  kernel_file=kernel_file, lane_file=lane_file, request_file=request_file)


def teardown(bundle: Bundle) -> None:
    if os.path.isdir(bundle.bundle_dir):
        shutil.rmtree(bundle.bundle_dir, ignore_errors=True)
