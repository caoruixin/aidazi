"""Quick-Fix launcher — orchestration (prepare → run), fail-closed at every step.

prepare(): validate request → harness-support gate (fail-closed) → clean-tree gate →
capture baseline → create worktree FROM baseline → load protected policy → materialize
bundle.

run(edit_fn): preliminary guard → edit phase (the harness, Commit 3; injected in tests) →
targeted verification → FINAL guard (over everything, incl. anything verification produced)
→ on clean: result commit on quickfix/<id> + a mechanical consistency check BEFORE writing
the `completed` record → teardown (keep branch). On ANY escalation or unexpected failure:
preserve patch + diff + handoff OUTSIDE the worktree FIRST, write an `escalated` record,
then tear down (delete the empty branch). The original repo is never edited; the unique
patch is never lost; a `completed` record is never written on a faulty result.

Determinism: the timestamp is INJECTED (`ts`); this module never reads the clock.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import bundle as bundle_mod
from . import guard as guard_mod
from . import paths
from . import verify as verify_mod
from . import worktree as wt_mod
from .errors import EscalationRequired, QuickfixError
from .globmatch import matches_any
from .gitutil import git_out, run_git
from .harness_support import assert_supported
from .policy import load_protected
from .record import append as record_append
from .record import default_records_path
from .request import load_request

EditFn = Callable[[str], None]


@dataclass
class LaneContext:
    repo_dir: str
    framework_root: str
    worktree: wt_mod.Worktree
    bundle: bundle_mod.Bundle
    request: object
    protected: object
    records_path: str
    record_schema_path: str
    escalation_root: str


@dataclass
class CompletedResult:
    outcome: str
    request_id: str
    branch: str
    commit_sha: str
    stat: str
    verification: dict


@dataclass
class EscalatedResult:
    outcome: str
    request_id: str
    reason: str
    detail: str
    patch_path: str
    patch_hash: str
    handoff_path: str
    diff_summary: str


def prepare(request_path: str, repo_dir: str, *, registry_path=None,
            worktree_root: Optional[str] = None, bundle_root: Optional[str] = None,
            framework_root: Optional[str] = None) -> LaneContext:
    repo_dir = os.path.abspath(repo_dir)
    # framework_root override lets an adopter (or a test) point at the vendored framework
    # explicitly; otherwise it is discovered from repo_dir (root or aidazi/).
    fr = framework_root or paths.framework_root(repo_dir)
    request = load_request(request_path, paths.request_schema_path(fr))

    # Fail-closed harness gate BEFORE any side effect.
    assert_supported(request.harness, registry_path or paths.harness_support_path(fr))

    wt_mod.assert_clean(repo_dir)
    # The lane writes its record + launch evidence under <repo>/.orchestrator/quickfix/;
    # that path MUST be git-ignored or those writes would dirty the adopter's tracked tree
    # (original-repo-unpolluted). Enforce it fail-closed BEFORE any side effect.
    wt_mod.assert_state_dir_ignored(repo_dir)
    # Honor the request's base_ref (the QF-1 contract allows it); default HEAD. Fail-closed
    # on an invalid ref. Every later operation binds to THIS resolved SHA.
    baseline = wt_mod.resolve_baseline(repo_dir, getattr(request, "base_ref", None))
    worktree = wt_mod.create(repo_dir, request.request_id, baseline, root=worktree_root)

    # If anything after worktree creation fails, tear the worktree down so prepare()
    # leaves NO orphan (the repo working tree was never touched either way).
    try:
        protected = load_protected(
            paths.policy_path(fr), paths.baseline_schema_path(fr),
            paths.overlay_path(fr), paths.overlay_schema_path(fr),
        )
        bundle = bundle_mod.materialize(
            fr, request,
            dest_root=bundle_root or bundle_mod.default_bundle_root(repo_dir),
            harness=request.harness,
        )
    except Exception:
        wt_mod.teardown(worktree, keep_branch=False)
        raise
    return LaneContext(
        repo_dir=repo_dir, framework_root=fr, worktree=worktree, bundle=bundle,
        request=request, protected=protected,
        records_path=default_records_path(repo_dir),
        record_schema_path=paths.record_schema_path(fr),
        escalation_root=os.path.join(repo_dir, ".orchestrator", "quickfix", "escalations"),
    )


def run(ctx: LaneContext, edit_fn: EditFn, *, ts: str, allow_unlisted: bool = False):
    wt = ctx.worktree
    try:
        _preliminary_guard(ctx)
        edit_fn(wt.work_dir)
        vres = verify_mod.run(ctx.request.verification, wt.work_dir, allow_unlisted=allow_unlisted)
        # The edit phase / verification must not have written into the ORIGINAL repo working
        # tree (verification is cwd-bounded but not OS-sandboxed). Detect + fail closed.
        _assert_original_repo_unpolluted(ctx)
        gres = guard_mod.check(wt.work_dir, wt.baseline_sha,
                               ctx.request.allowed_globs, ctx.protected)
        if not gres.ok:
            raise EscalationRequired(gres.reason(), gres.detail(), gres.touched)
        if not vres.ok:
            raise EscalationRequired(EscalationRequired.VERIFICATION_FAILURE,
                                     f"verification exit {vres.exit_code} {vres.note}".strip())
        result = _commit_and_record_completed(ctx, vres, gres, ts=ts)
        bundle_mod.teardown(ctx.bundle)
        wt_mod.teardown(wt, keep_branch=True)
        return result
    except EscalationRequired as exc:
        esc = _preserve_and_record_escalated(ctx, exc, ts=ts)
        bundle_mod.teardown(ctx.bundle)
        wt_mod.teardown(wt, keep_branch=False)
        return esc
    except Exception as exc:  # fail-closed: any unexpected failure escalates, never completes
        esc = _preserve_and_record_escalated(
            ctx, EscalationRequired(EscalationRequired.INCONSISTENT_RESULT,
                                    f"unexpected failure: {exc}"), ts=ts)
        bundle_mod.teardown(ctx.bundle)
        wt_mod.teardown(wt, keep_branch=False)
        return esc


def _preliminary_guard(ctx: LaneContext) -> None:
    """The worktree was just created from the baseline; it must be clean and at baseline."""
    wt = ctx.worktree
    status = git_out(wt.work_dir, ["status", "--porcelain", "--untracked-files=all"]).strip()
    head = git_out(wt.work_dir, ["rev-parse", "HEAD"]).strip()
    if status or head != wt.baseline_sha:
        raise EscalationRequired(EscalationRequired.INCONSISTENT_RESULT,
                                 "preliminary guard: worktree not clean-at-baseline")


def _commit_and_record_completed(ctx: LaneContext, vres, gres, *, ts: str) -> CompletedResult:
    wt = ctx.worktree
    run_git(wt.work_dir, ["add", "-A"])
    # Capture the EXACT tree that was guarded + verified, so the consistency check can prove
    # the commit captured it with no late change (TOCTOU between guard and commit).
    verified_tree = git_out(wt.work_dir, ["write-tree"]).strip()
    msg = f"quickfix({ctx.request.request_id}): {ctx.request.task_summary}"
    run_git(wt.work_dir, ["commit", "-m", msg, "--no-verify"])

    _consistency_check(ctx, vres, gres, verified_tree)  # raises EscalationRequired on mismatch

    commit_sha = git_out(wt.work_dir, ["rev-parse", "HEAD"]).strip()
    stat = git_out(wt.work_dir, ["show", "--stat", "--oneline", "--no-color", commit_sha]).strip()
    record = {
        "request_id": ctx.request.request_id, "harness": ctx.request.harness,
        "outcome": "completed", "baseline_sha": wt.baseline_sha, "ts": ts,
        "result": {
            "branch": wt.branch, "commit_sha": commit_sha, "stat": stat,
            "verification": {"argv": list(vres.argv), "exit_code": vres.exit_code, "ok": vres.ok},
        },
    }
    record_append(record, ctx.records_path, ctx.record_schema_path)
    return CompletedResult("completed", ctx.request.request_id, wt.branch, commit_sha, stat,
                           record["result"]["verification"])


def _assert_original_repo_unpolluted(ctx: LaneContext) -> None:
    """The original repo working tree must be untouched by the lane (req 1)."""
    dirty = git_out(ctx.repo_dir, ["status", "--porcelain", "--untracked-files=all"]).strip()
    if dirty:
        raise EscalationRequired(
            EscalationRequired.ORIGINAL_REPO_POLLUTED,
            "the ORIGINAL repo working tree changed during the lane run (the edit phase or "
            f"verification wrote outside the worktree): {dirty.splitlines()[0][:160]}")


def _raw_diff_entries(raw: str):
    """Parse ``git diff-tree --raw -z`` output -> (mode_src, mode_dst, path) triples."""
    tokens = raw.split("\0")
    i = 0
    while i < len(tokens):
        meta = tokens[i]
        if not meta or not meta.startswith(":"):
            i += 1
            continue
        fields = meta[1:].split(" ")  # mode_src mode_dst sha_src sha_dst status
        mode_src = fields[0] if len(fields) > 0 else ""
        mode_dst = fields[1] if len(fields) > 1 else ""
        path = tokens[i + 1] if i + 1 < len(tokens) else ""
        yield mode_src, mode_dst, path
        i += 2


def _consistency_check(ctx: LaneContext, vres, gres, verified_tree: str) -> None:
    """Mechanically re-verify the result BEFORE a `completed` record is written (req 5).

    Independent of the guard's booleans: it re-derives scope / protected / file-MODE
    violations from the commit itself, and proves the commit captured EXACTLY the tree that
    was guarded + verified (no late change)."""
    wt = ctx.worktree
    cur = git_out(wt.work_dir, ["symbolic-ref", "--short", "HEAD"]).strip()
    if cur != wt.branch:
        raise EscalationRequired(EscalationRequired.INCONSISTENT_RESULT,
                                 f"on branch {cur!r}, expected {wt.branch!r}")
    parent = git_out(wt.work_dir, ["rev-parse", "HEAD^"]).strip()
    if parent != wt.baseline_sha:
        raise EscalationRequired(EscalationRequired.INCONSISTENT_RESULT,
                                 f"commit parent {parent!r} != baseline {wt.baseline_sha!r}")
    committed_tree = git_out(wt.work_dir, ["rev-parse", "HEAD^{tree}"]).strip()
    if committed_tree != verified_tree:
        raise EscalationRequired(EscalationRequired.INCONSISTENT_RESULT,
                                 "committed tree != the guarded+verified tree (late change)")
    raw = git_out(wt.work_dir, ["diff-tree", "--no-commit-id", "-r", "-z", "--raw",
                                "--no-renames", "HEAD"])
    for mode_src, mode_dst, path in _raw_diff_entries(raw):
        # Check BOTH sides: a delete of an existing symlink/gitlink is src=120000/160000
        # -> dst=000000, which a dst-only check would miss.
        if mode_src in ("120000", "160000") or mode_dst in ("120000", "160000"):
            raise EscalationRequired(
                EscalationRequired.SYMLINK_OR_GITLINK,
                f"committed symlink/gitlink change (src={mode_src} dst={mode_dst}): {path}")
        if not matches_any(path, ctx.request.allowed_globs):
            raise EscalationRequired(EscalationRequired.SCOPE_EXPANSION,
                                     f"committed path out of scope: {path}")
        sid = ctx.protected.match(path)
        if sid:
            raise EscalationRequired(EscalationRequired.PROTECTED_SURFACE,
                                     f"committed path hits protected surface {sid}: {path}")
    if not vres.ok or not gres.ok:
        raise EscalationRequired(EscalationRequired.INCONSISTENT_RESULT,
                                 "verification or final guard not green at commit time")


def _preserve_and_record_escalated(ctx: LaneContext, exc: EscalationRequired, *,
                                   ts: str) -> EscalatedResult:
    """Save patch + diff + handoff OUTSIDE the worktree, THEN it is safe to tear down."""
    wt = ctx.worktree
    dest = os.path.join(ctx.escalation_root, ctx.request.request_id)
    os.makedirs(dest, exist_ok=True)

    # Stage everything (incl. untracked) just to compute a complete patch — NOT a commit.
    # check=True: if staging fails we must NOT proceed to a possibly-empty patch + teardown
    # (which would lose the work). On failure this raises, the caller's teardown is skipped,
    # and the worktree is preserved for manual recovery.
    run_git(wt.work_dir, ["add", "-A"])
    patch = git_out(wt.work_dir, ["diff", "--cached", wt.baseline_sha])
    diff_summary = git_out(wt.work_dir, ["diff", "--cached", "--stat", wt.baseline_sha]).strip()
    patch_path = os.path.join(dest, "work.patch")
    with open(patch_path, "w", encoding="utf-8") as fh:
        fh.write(patch)
    patch_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()

    handoff_path = os.path.join(dest, "handoff.md")
    _write_handoff(ctx, exc, handoff_path, patch_path, patch_hash, diff_summary)

    record = {
        "request_id": ctx.request.request_id, "harness": ctx.request.harness,
        "outcome": "escalated", "baseline_sha": wt.baseline_sha, "ts": ts,
        "result": {
            "escalation_reason": exc.reason, "handoff_path": handoff_path,
            "patch_path": patch_path, "patch_hash": patch_hash,
            "diff_summary": diff_summary or "(no changes)",
        },
    }
    record_append(record, ctx.records_path, ctx.record_schema_path)
    return EscalatedResult("escalated", ctx.request.request_id, exc.reason, exc.detail,
                           patch_path, patch_hash, handoff_path, diff_summary)


def _write_handoff(ctx: LaneContext, exc: EscalationRequired, handoff_path: str,
                   patch_path: str, patch_hash: str, diff_summary: str) -> None:
    req = ctx.request
    body = (
        f"# Quick-Fix escalation handoff — `{req.request_id}`\n\n"
        f"> The Quick-Fix lane STOPPED and escalated. No result was applied to any branch "
        f"you use. The investigation below was preserved before worktree teardown. "
        f"**Relaunch this work in Full framework mode.**\n\n"
        f"## Why it escalated\n\n"
        f"- **Trigger:** `{exc.reason}`\n"
        f"- **Detail:** {exc.detail}\n\n"
        f"## What was attempted\n\n{req.task_summary}\n\n"
        f"## Preserved investigation (NOT lost to teardown)\n\n"
        f"- **Baseline SHA:** `{ctx.worktree.baseline_sha}`\n"
        f"- **Saved patch:** `{patch_path}` (sha256 `{patch_hash}`)\n"
        f"- **Diff summary:**\n\n```\n{diff_summary or '(no changes)'}\n```\n\n"
        f"- **Record:** appended to `.orchestrator/quickfix/records.jsonl` "
        f"(`outcome: escalated`).\n\n"
        f"## Next\n\n"
        f"1. Review the saved patch and this handoff.\n"
        f"2. Relaunch in Full framework mode and carry it through the proper chain.\n"
        f"3. Do NOT re-attempt as a Quick Fix by widening `allowed_globs` to dodge the "
        f"trigger.\n"
    )
    with open(handoff_path, "w", encoding="utf-8") as fh:
        fh.write(body)
