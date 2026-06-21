"""Quick-Fix CLI core (the shell wrapper is thin; all logic lives here).

Commit 2 wires `prepare()` only: there is no harness adapter yet, so a real invocation
fail-closes (the shipped registry marks every harness unsupported) with a stable exit
code. The edit-phase wiring (calling `run()` with a real adapter's edit_fn) lands in
Commit 3. Stable exit codes let the shell/CI branch deterministically.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import bundle as bundle_mod
from . import launcher
from . import worktree as wt_mod
from .errors import (CleanTreeError, HarnessUnsupportedError, PolicyError,
                     QuickfixError, RequestError)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID = 2
EXIT_DIRTY = 3
EXIT_ESCALATED = 10
EXIT_UNSUPPORTED = 11


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="quickfix",
        description="Quick-Fix lane launcher (Commit 2: prepare only; no harness adapter — "
                    "the lane is not yet usable and every launch fails closed).",
    )
    ap.add_argument("--request", required=True, help="path to the quickfix-request.json")
    ap.add_argument("--repo-dir", default=".", help="the adopter repo root")
    ap.add_argument("--registry", default=None, help="override the harness-support registry")
    ap.add_argument("--framework-root", default=None,
                    help="explicit framework root (else discovered from --repo-dir)")
    args = ap.parse_args(argv)

    try:
        ctx = launcher.prepare(args.request, args.repo_dir, registry_path=args.registry,
                               framework_root=args.framework_root)
    except HarnessUnsupportedError as exc:
        print(f"[quickfix] FAIL-CLOSED (unsupported harness): {exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED
    except CleanTreeError as exc:
        print(f"[quickfix] FAIL-CLOSED (dirty working tree): {exc}", file=sys.stderr)
        return EXIT_DIRTY
    except (RequestError, PolicyError) as exc:
        print(f"[quickfix] FAIL-CLOSED (invalid request/policy): {exc}", file=sys.stderr)
        return EXIT_INVALID
    except QuickfixError as exc:
        print(f"[quickfix] error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # Reached only with an (injected) supported registry. Commit 2 has no adapter to drive
    # the edit phase, so tear down what prepare() created and report not-usable.
    bundle_mod.teardown(ctx.bundle)
    wt_mod.teardown(ctx.worktree, keep_branch=False)
    print("[quickfix] prepared, but no harness adapter is available in this build "
          "(Commit 2): the lane is not yet usable. Aborted without running.", file=sys.stderr)
    return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
