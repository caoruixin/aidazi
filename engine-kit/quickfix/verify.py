"""Targeted verification — structured argv, ``shell=False``, bounded cwd, allowlist.

The verification command is an argument vector (never a shell string), run with
``shell=False`` in a cwd that MUST resolve inside the worktree. ``argv[0]``'s basename is
checked against an executable allowlist; a non-allowlisted executable requires explicit
extra human confirmation (``allow_unlisted=True``) or the run is refused (fail-closed).
Whatever the verification does, the FINAL guard re-runs over the worktree afterward
(process/quickfix-lane.md §5/§7) — so this module never decides scope, only runs + reports.

LIMITATION (honest): the verification is cwd-bounded but NOT OS-sandboxed — an allowlisted
command could still write outside the worktree (e.g. an absolute path in the original repo).
The launcher mitigates this fail-closed by checking the ORIGINAL repo working tree is
unpolluted after verification (launcher._assert_original_repo_unpolluted); true OS sandboxing
is out of scope for v1.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

from .errors import VerificationError

# Conservative default allowlist of verification executables (basename match).
DEFAULT_ALLOWLIST = frozenset({
    "python", "python3", "python3.12", "python3.11", "pytest", "py.test",
    "node", "npm", "npx", "yarn", "pnpm", "deno", "bun",
    "make", "go", "cargo", "ruby", "rake", "bundle", "deno",
    "java", "mvn", "gradle", "dotnet", "php", "swift", "tox", "unittest",
})

_DEFAULT_TIMEOUT = 600  # seconds


@dataclass
class VerifyResult:
    argv: List[str]
    exit_code: int
    ok: bool
    note: str = ""


def _resolve_cwd(worktree_dir: str, rel_cwd: str) -> str:
    worktree_dir = os.path.realpath(worktree_dir)
    target = os.path.realpath(os.path.join(worktree_dir, rel_cwd or "."))
    if target != worktree_dir and not target.startswith(worktree_dir + os.sep):
        raise VerificationError(
            f"verification cwd escapes the worktree: {rel_cwd!r} -> {target!r}"
        )
    if not os.path.isdir(target):
        raise VerificationError(f"verification cwd does not exist: {target!r}")
    return target


def run(verification, worktree_dir: str, *,
        allowlist: Sequence[str] = (), allow_unlisted: bool = False,
        timeout: int = _DEFAULT_TIMEOUT) -> VerifyResult:
    argv: List[str] = list(verification.argv)
    if not argv:
        raise VerificationError("verification argv is empty")

    exe = os.path.basename(argv[0])
    allowed = set(allowlist) or DEFAULT_ALLOWLIST
    if exe not in allowed and not allow_unlisted:
        raise VerificationError(
            f"verification executable {exe!r} is not allowlisted; rerun with explicit "
            f"human confirmation (allow_unlisted) or use an allowlisted command"
        )

    cwd = _resolve_cwd(worktree_dir, getattr(verification, "cwd", "."))
    try:
        proc = subprocess.run(argv, shell=False, cwd=cwd, capture_output=True,
                              text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise VerificationError(f"verification executable not found: {argv[0]!r}") from exc
    except subprocess.TimeoutExpired:
        return VerifyResult(argv=argv, exit_code=-1, ok=False,
                            note=f"timeout after {timeout}s")
    return VerifyResult(argv=argv, exit_code=proc.returncode, ok=(proc.returncode == 0),
                        note="")
