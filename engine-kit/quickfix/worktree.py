"""Ephemeral git worktree for the Quick-Fix lane.

ALL edits happen in a worktree created FROM the baseline SHA captured at launch, in a
sibling directory OUTSIDE the repo tree (so the adopter's working area is never touched
and the cold-start tree-walk never reaches the repo's root memory). The lane requires a
clean working tree at launch (dirty ⇒ fail closed). State binds to the baseline SHA, not
to the main repo staying unchanged afterward (req 2).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .errors import CleanTreeError
from .gitutil import git_out, run_git


def assert_clean(repo_dir: str) -> None:
    """Raise CleanTreeError if the repo working tree has any change (incl. untracked)."""
    out = git_out(repo_dir, ["status", "--porcelain", "--untracked-files=all"])
    if out.strip():
        raise CleanTreeError(
            "working tree is not clean; Quick-Fix v1 requires a clean tree at launch "
            "(commit or stash first, then relaunch)"
        )


def capture_baseline(repo_dir: str) -> str:
    """The full HEAD SHA captured at launch — every later operation binds to THIS."""
    return git_out(repo_dir, ["rev-parse", "HEAD"]).strip()


def resolve_baseline(repo_dir: str, ref: str = None) -> str:
    """Resolve the request's ``base_ref`` (or HEAD when absent) to a full commit SHA.
    Every later operation binds to THIS SHA. Fail-closed (GitError) on an invalid ref."""
    target = ref or "HEAD"
    return git_out(repo_dir, ["rev-parse", "--verify", f"{target}^{{commit}}"]).strip()


def default_worktree_root(repo_dir: str) -> str:
    repo_dir = os.path.abspath(repo_dir)
    parent = os.path.dirname(repo_dir)
    base = os.path.basename(repo_dir)
    return os.path.join(parent, f"{base}-quickfix")


def branch_name(request_id: str) -> str:
    return f"quickfix/{request_id}"


@dataclass
class Worktree:
    work_dir: str
    branch: str
    baseline_sha: str
    repo_dir: str


def create(repo_dir: str, request_id: str, baseline_sha: str,
           root: str = None) -> Worktree:
    """``git worktree add <root>/<id> -b quickfix/<id> <baseline_sha>`` (out of tree)."""
    repo_dir = os.path.abspath(repo_dir)
    root = os.path.abspath(root or default_worktree_root(repo_dir))
    os.makedirs(root, exist_ok=True)
    work_dir = os.path.join(root, request_id)
    branch = branch_name(request_id)
    run_git(repo_dir, ["worktree", "add", work_dir, "-b", branch, baseline_sha])
    return Worktree(work_dir=os.path.abspath(work_dir), branch=branch,
                    baseline_sha=baseline_sha, repo_dir=repo_dir)


def teardown(wt: Worktree, *, keep_branch: bool) -> None:
    """Remove the worktree (force — the patch is preserved beforehand on escalation).
    On a non-kept branch (escalation, no result commit) delete the empty branch too."""
    run_git(wt.repo_dir, ["worktree", "remove", "--force", wt.work_dir], check=False)
    # Prune any stale admin entry, then drop the branch if we are not keeping it.
    run_git(wt.repo_dir, ["worktree", "prune"], check=False)
    if not keep_branch:
        run_git(wt.repo_dir, ["branch", "-D", wt.branch], check=False)
