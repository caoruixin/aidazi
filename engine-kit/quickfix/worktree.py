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

from .errors import CleanTreeError, StateDirError
from .gitutil import git_out, run_git


def assert_clean(repo_dir: str) -> None:
    """Raise CleanTreeError if the repo working tree has any change (incl. untracked)."""
    out = git_out(repo_dir, ["status", "--porcelain", "--untracked-files=all"])
    if out.strip():
        raise CleanTreeError(
            "working tree is not clean; Quick-Fix v1 requires a clean tree at launch "
            "(commit or stash first, then relaunch)"
        )


# Paths mirroring EVERY filename the runtime actually writes under .orchestrator/quickfix/ in
# the MAIN repo (they must survive ephemeral teardown, so they live here and MUST be
# git-ignored). The check probes each real filename — not just a per-subtree sample — so even
# a per-FILE partial .gitignore that misses any one of them fails closed. The `<id>` segment
# (`_qf_ignore_probe`) stands in for the request_id; a realistic directory-level ignore
# (`.orchestrator/`, `.orchestrator/quickfix/`, `.orchestrator/quickfix/*`) covers them all.
# This list MUST mirror the real writes: record.py (records.jsonl); cli.py + adapters/base.py
# (evidence/<id>/{stdout,stderr}.txt + edit-evidence.json); launcher.py
# (escalations/<id>/{work.patch,handoff.md}).
_QF_PROBE_ID = "_qf_ignore_probe"
_STATE_WRITE_PATHS = (
    os.path.join(".orchestrator", "quickfix", "records.jsonl"),
    os.path.join(".orchestrator", "quickfix", "evidence", _QF_PROBE_ID, "stdout.txt"),
    os.path.join(".orchestrator", "quickfix", "evidence", _QF_PROBE_ID, "stderr.txt"),
    os.path.join(".orchestrator", "quickfix", "evidence", _QF_PROBE_ID, "edit-evidence.json"),
    os.path.join(".orchestrator", "quickfix", "escalations", _QF_PROBE_ID, "work.patch"),
    os.path.join(".orchestrator", "quickfix", "escalations", _QF_PROBE_ID, "handoff.md"),
)


def assert_state_dir_ignored(repo_dir: str) -> None:
    """Fail closed unless EVERY lane-state write subtree is git-ignored in ``repo_dir``.

    Probes a path under each real write location (record, per-request evidence, per-request
    escalation), so a *partial* ignore that covers only some subtrees cannot slip an untracked
    file past the original-repo-unpolluted guarantee. Uses ``git check-ignore`` (exit 0 =
    ignored, 1 = not ignored) rather than assuming the adopter configured it
    (process/quickfix-lane.md §9 documents the requirement; this enforces it before any side
    effect)."""
    for rel in _STATE_WRITE_PATHS:
        rc, _out, _err = run_git(repo_dir, ["check-ignore", "-q", "--", rel], check=False)
        if rc != 0:
            raise StateDirError(
                f"Quick-Fix writes lane state under .orchestrator/quickfix/, but {rel!r} is "
                f"not git-ignored in this repo (git check-ignore exit {rc}). Add "
                f"`.orchestrator/` to .gitignore so the lane never dirties your tracked "
                f"tree, then relaunch."
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
