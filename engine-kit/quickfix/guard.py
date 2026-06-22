"""The deterministic Quick-Fix guard (Layer B backstop — necessary, not sufficient).

Binds to the baseline SHA captured at launch and enumerates the FULL change set of the
worktree, classifying every touched path:

  * staged / unstaged / untracked changes, file-mode changes, deletes — via
    ``git status --porcelain=v2 -z --untracked-files=all`` (respects .gitignore, so
    incidental ignored artifacts from verification do not trip the guard);
  * renames — BOTH the old and the new path are scope-checked (whether git reports a
    rename entry or a delete+untracked pair, both paths are enumerated);
  * symlinks (mode 120000 or an on-disk symlink) and submodule/gitlinks (mode 160000) —
    v1 treats ANY such change as automatic escalation;
  * unexpected commits — if the edit phase advanced HEAD past the baseline, that is an
    escalation (the lane, not the harness, owns the result commit).

A path is a violation if it is OUT OF SCOPE (matches no ``allowed_globs``) OR matches a
PROTECTED surface. Any violation, symlink/gitlink, or unexpected commit ⇒ not ``ok``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .errors import QuickfixError
from .globmatch import Glob, matches_any
from .gitutil import git_out
from .policy import ProtectedSurfaces

SYMLINK_MODE = "120000"
GITLINK_MODE = "160000"


@dataclass
class GuardResult:
    touched: List[str] = field(default_factory=list)
    out_of_scope: List[str] = field(default_factory=list)
    protected_hits: List[Tuple[str, str]] = field(default_factory=list)  # (path, surface_id)
    symlink_or_gitlink: List[Tuple[str, str]] = field(default_factory=list)  # (kind, path)
    unexpected_commits: int = 0

    @property
    def ok(self) -> bool:
        return not (self.out_of_scope or self.protected_hits
                    or self.symlink_or_gitlink or self.unexpected_commits)

    def reason(self) -> str:
        from .errors import EscalationRequired as E
        if self.symlink_or_gitlink:
            return E.SYMLINK_OR_GITLINK
        if self.protected_hits:
            return E.PROTECTED_SURFACE
        if self.out_of_scope or self.unexpected_commits:
            return E.SCOPE_EXPANSION
        return ""

    def detail(self) -> str:
        bits = []
        if self.symlink_or_gitlink:
            bits.append("symlink/gitlink: " + ", ".join(f"{k}:{p}" for k, p in self.symlink_or_gitlink))
        if self.protected_hits:
            bits.append("protected: " + ", ".join(f"{p} [{sid}]" for p, sid in self.protected_hits))
        if self.out_of_scope:
            bits.append("out-of-scope: " + ", ".join(self.out_of_scope))
        if self.unexpected_commits:
            bits.append(f"unexpected commits ahead of baseline: {self.unexpected_commits}")
        return "; ".join(bits)


def _status_entries(worktree_dir: str):
    raw = git_out(worktree_dir, ["status", "--porcelain=v2", "-z",
                                 "--untracked-files=all", "--find-renames"])
    tokens = raw.split("\0")
    i, n = 0, len(tokens)
    while i < n:
        tok = tokens[i]
        if tok == "":
            i += 1
            continue
        kind = tok[0]
        if kind == "1":
            parts = tok.split(" ", 8)
            yield {"modes": (parts[3], parts[4], parts[5]), "paths": [parts[8]]}
            i += 1
        elif kind == "2":
            parts = tok.split(" ", 9)
            new_path = parts[9]
            orig = tokens[i + 1] if i + 1 < n else ""
            yield {"modes": (parts[3], parts[4], parts[5]), "paths": [new_path, orig]}
            i += 2
        elif kind == "u":
            parts = tok.split(" ", 10)
            yield {"modes": (), "paths": [parts[10]]}
            i += 1
        elif kind == "?":
            yield {"modes": (), "paths": [tok[2:]]}
            i += 1
        elif kind == "!":
            i += 1  # ignored entry (we never pass --ignored, but skip it if present)
        else:
            # Fail-closed: an unrecognized porcelain v2 record must NOT be silently skipped.
            raise QuickfixError(f"unknown git status porcelain v2 record: {tok!r}")


def check(worktree_dir: str, baseline_sha: str,
          allowed_globs: Sequence[Glob], protected: ProtectedSurfaces) -> GuardResult:
    res = GuardResult()

    # Edit phase must not have committed; the lane owns the result commit.
    ahead = git_out(worktree_dir, ["rev-list", "--count", f"{baseline_sha}..HEAD"]).strip()
    res.unexpected_commits = int(ahead or "0")

    for e in _status_entries(worktree_dir):
        modes = e["modes"]
        is_symlink = SYMLINK_MODE in modes
        is_gitlink = GITLINK_MODE in modes
        for p in e["paths"]:
            if not p:
                continue
            res.touched.append(p)
            full = os.path.join(worktree_dir, p)
            if os.path.islink(full):
                is_symlink = True
            elif os.path.isdir(full):
                # An UNTRACKED directory git refused to recurse into is a nested repo /
                # submodule (a would-be gitlink once staged) — conservative escalation.
                is_gitlink = True
            if not matches_any(p, allowed_globs):
                res.out_of_scope.append(p)
            sid = protected.match(p)
            if sid:
                res.protected_hits.append((p, sid))
        if is_symlink:
            res.symlink_or_gitlink.append(("symlink", "|".join(x for x in e["paths"] if x)))
        if is_gitlink:
            res.symlink_or_gitlink.append(("gitlink", "|".join(x for x in e["paths"] if x)))

    return res
