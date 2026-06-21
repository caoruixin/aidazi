"""Thin offline git helper for the Quick-Fix lane (no network is ever touched)."""
from __future__ import annotations

import subprocess
from typing import List, Sequence, Tuple

from .errors import GitError


def run_git(repo_dir: str, args: Sequence[str], *, check: bool = True) -> Tuple[int, str, str]:
    """Run ``git -C <repo_dir> <args>`` offline. Returns (returncode, stdout, stderr).
    Raises ``GitError`` on non-zero exit when ``check`` is True."""
    cmd: List[str] = ["git", "-C", repo_dir, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GitError(cmd, proc.returncode, proc.stderr)
    return proc.returncode, proc.stdout, proc.stderr


def git_out(repo_dir: str, args: Sequence[str]) -> str:
    """Run git and return stdout (raises GitError on failure)."""
    return run_git(repo_dir, args)[1]
