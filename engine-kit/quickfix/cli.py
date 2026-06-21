"""Quick-Fix CLI core (the shell wrapper is thin; all logic lives here).

Commit 3 wires the EDIT PHASE. Order is fail-closed and cheap-first:

  1. ``prepare()`` — schema-validate the request, run the harness-support REGISTRY gate
     (``supported`` only), check the clean tree, and create the out-of-tree bundle +
     ephemeral worktree. Every refusal here (invalid request, dirty tree, non-``supported``
     harness) is hermetic — NO adapter subprocess runs.
  2. adapter ``preflight()`` — only for a harness that already cleared the registry gate:
     resolve the adapter, discover the executable, version-check it, and re-assert
     cold-start isolation (defense in depth against a mis-set registry). A failure tears
     down what prepare() created and fails closed.
  3. edit phase — drive the launcher's harness-neutral ``run(edit_fn)`` with the adapter's
     real launch. The launcher still owns guard / verification / guard / commit / record /
     teardown; the adapter only performs the bounded edit and records launch evidence.

This module (the composition root) is the ONLY place that reads the clock for the lane —
the launcher stays clock-free (the ``ts`` is injected) so its behavior is deterministic.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Sequence

from . import bundle as bundle_mod
from . import launcher
from . import worktree as wt_mod
from .adapters import build_adapter
from .adapters.base import HarnessAdapterError, LaunchSpec
from .errors import (CleanTreeError, HarnessUnsupportedError, PolicyError,
                     QuickfixError, RequestError, StateDirError)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID = 2
EXIT_DIRTY = 3
EXIT_ESCALATED = 10
EXIT_UNSUPPORTED = 11


def _now_iso() -> str:
    """Injected lane timestamp (the launcher never reads the clock itself)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _launch_spec(ctx: launcher.LaneContext) -> LaunchSpec:
    """Project the (harness-neutral) LaneContext into the adapter's LaunchSpec."""
    return LaunchSpec(
        request_id=ctx.request.request_id,
        task_summary=ctx.request.task_summary,
        bundle_dir=ctx.bundle.bundle_dir,
        worktree_dir=ctx.worktree.work_dir,
        allowed_glob_patterns=list(ctx.request.allowed_glob_patterns),
        memory_file=ctx.bundle.memory_file,
        request_file=ctx.bundle.request_file,
        lane_file=ctx.bundle.lane_file,
        kernel_file=ctx.bundle.kernel_file,
    )


def _evidence_dir(repo_dir: str, request_id: str) -> str:
    # Under .orchestrator/ (gitignored) and in the MAIN repo dir, so it survives the
    # ephemeral worktree/bundle teardown and never dirties the tracked tree.
    return os.path.join(repo_dir, ".orchestrator", "quickfix", "evidence", request_id)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="quickfix",
        description="Quick-Fix lane launcher: human-explicit, loop-independent maintenance "
                    "lane. Fails closed unless the harness is `supported`, then runs the "
                    "bounded edit in an out-of-tree bundle + ephemeral worktree "
                    "(process/quickfix-lane.md).",
    )
    ap.add_argument("--request", required=True, help="path to the quickfix-request.json")
    ap.add_argument("--repo-dir", default=".", help="the adopter repo root")
    ap.add_argument("--registry", default=None, help="override the harness-support registry")
    ap.add_argument("--framework-root", default=None,
                    help="explicit framework root (else discovered from --repo-dir)")
    ap.add_argument("--model", default=None,
                    help="optional model alias passed to the harness adapter")
    ap.add_argument("--timeout", type=int, default=600,
                    help="edit-phase timeout in seconds (the harness process group is killed)")
    ap.add_argument("--allow-unlisted-verification", action="store_true",
                    help="explicit human confirmation to run a non-allowlisted verification "
                         "executable (process/quickfix-lane.md §7)")
    ap.add_argument("--no-launch", action="store_true",
                    help="prepare + preflight only; tear down without launching the harness")
    args = ap.parse_args(argv)
    repo_dir = os.path.abspath(args.repo_dir)

    # 1) prepare(): authoritative validation + REGISTRY gate + worktree/bundle. Every
    #    refusal here is hermetic (no adapter subprocess).
    try:
        ctx = launcher.prepare(args.request, repo_dir, registry_path=args.registry,
                               framework_root=args.framework_root)
    except HarnessUnsupportedError as exc:
        print(f"[quickfix] FAIL-CLOSED (unsupported harness): {exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED
    except CleanTreeError as exc:
        print(f"[quickfix] FAIL-CLOSED (dirty working tree): {exc}", file=sys.stderr)
        return EXIT_DIRTY
    except StateDirError as exc:
        print(f"[quickfix] FAIL-CLOSED (repo not configured for the lane): {exc}",
              file=sys.stderr)
        return EXIT_INVALID
    except (RequestError, PolicyError) as exc:
        print(f"[quickfix] FAIL-CLOSED (invalid request/policy): {exc}", file=sys.stderr)
        return EXIT_INVALID
    except QuickfixError as exc:
        print(f"[quickfix] error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # 2) adapter preflight (only a `supported` harness reaches here). A missing/old binary
    #    or a harness that cannot isolate its cold-start fails closed; tear down first.
    try:
        adapter = build_adapter(ctx.request.harness, timeout_s=args.timeout, model=args.model)
        adapter.preflight()
    except HarnessAdapterError as exc:
        bundle_mod.teardown(ctx.bundle)
        wt_mod.teardown(ctx.worktree, keep_branch=False)
        print(f"[quickfix] FAIL-CLOSED (harness adapter): {exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED

    if args.no_launch:
        bundle_mod.teardown(ctx.bundle)
        wt_mod.teardown(ctx.worktree, keep_branch=False)
        print("[quickfix] prepared + preflighted (--no-launch); torn down without running.",
              file=sys.stderr)
        return EXIT_OK

    # 3) Edit phase — the launcher stays harness-neutral; the adapter does the real launch.
    evidence_dir = _evidence_dir(repo_dir, ctx.request.request_id)

    def edit_fn(work_dir: str) -> None:
        adapter.run_edit(_launch_spec(ctx), evidence_dir=evidence_dir)

    result = launcher.run(ctx, edit_fn, ts=_now_iso(),
                          allow_unlisted=args.allow_unlisted_verification)
    return _report(result, evidence_dir)


def _report(result, evidence_dir: str) -> int:
    if result.outcome == "completed":
        print(f"[quickfix] COMPLETED — result on branch {result.branch} "
              f"(commit {result.commit_sha[:12]}). NOT auto-applied; cherry-pick if you want it.")
        print(result.stat)
        print(f"[quickfix] launch evidence: {evidence_dir}")
        return EXIT_OK
    print(f"[quickfix] ESCALATED ({result.reason}): {result.detail}", file=sys.stderr)
    print(f"[quickfix] preserved patch: {result.patch_path}", file=sys.stderr)
    print(f"[quickfix] handoff: {result.handoff_path} — relaunch in Full framework mode.",
          file=sys.stderr)
    return EXIT_ESCALATED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
