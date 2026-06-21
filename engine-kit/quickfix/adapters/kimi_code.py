"""Quick-Fix adapter for the Kimi Code CLI (Moonshot AI) — status UNSUPPORTED (honest).

Kimi Code is a capable agentic CLI, but its current surface (0.18.0) CANNOT satisfy the
lane's cold-start isolation requirement, so this adapter declares
``cold_start_isolation=False`` and the lane fails closed for it (both at :meth:`preflight`
and, defensively, in ``run_edit``). No real launch is attempted.

WHY (verified against the official docs, 2026-06-22):

  * Kimi auto-loads instructions by MERGING ``AGENTS.md`` (and ``.kimi/AGENTS.md``) from the
    git project root DOWN to the working directory (changelog 1.29.0; injected via the
    ``KIMI_AGENTS_MD`` system-prompt variable). So it DOES cold-start a project chain.
  * The CLI has NO ``-C``/``--cd``/``--workdir`` flag (no codex ``-C`` equivalent) and NO
    ``--add-dir`` flag (no extra-directory write grant). The only lever over what loads and
    what is editable is the PROCESS cwd.
  * That single lever is the blocker: the lane needs cwd = an OUT-OF-TREE bundle (so the
    adopter repo's ``AGENTS.md`` chain is not cold-started) WHILE edits land in the
    ephemeral WORKTREE. With cwd as the only control, those two cannot be separated —
    cwd=worktree leaks the repo chain into cold-start; cwd=bundle leaves the worktree
    unreachable for edits.
  * The no-git-repo cwd-only fallback and whether ``$KIMI_CODE_HOME/AGENTS.md`` (global)
    auto-loads are both UNDOCUMENTED — so isolation could not be mechanically PROVEN even
    if the edit-target problem were solved.

To make Kimi supportable, the CLI would need a working-root flag (``-C`` equivalent) plus
an additional-writable-dir grant (``--add-dir`` equivalent), OR a documented "load only
this instruction file" switch. Until then it stays UNSUPPORTED (process/quickfix-lane.md
§10 — no silent degradation onto an unproven harness). Tracked as a Commit 3 follow-up.
"""
from __future__ import annotations

import os
from typing import List, Optional

from .base import HarnessCapability, LaunchSpec, QuickfixAdapter

_DEFAULT_KIMI_PATH = os.path.expanduser("~/.kimi-code/bin/kimi")


class KimiCodeAdapter(QuickfixAdapter):
    harness = "kimi_code"
    MEMORY_FILENAME = "AGENTS.md"  # kimi merges AGENTS.md root->cwd (moot: never launched)
    MIN_VERSION = (0, 18, 0)
    PROMPT_DELIVERY = "argv_attached"  # kimi --prompt=<value> (attached, dash-safe)

    def __init__(self, *, model: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.model = model

    def default_binary(self) -> str:
        # Kimi installs to ~/.kimi-code/bin/kimi (not on PATH by default); discover_executable
        # accepts an absolute fallback path. PATH copy is preferred when present.
        import shutil
        return shutil.which("kimi") or _DEFAULT_KIMI_PATH

    def capability(self) -> HarnessCapability:
        return HarnessCapability(
            headless=True,
            alternate_cwd=False,      # no -C/--cd
            worktree_write_grant=False,  # no --add-dir
            cold_start_isolation=False,
            isolation_mechanism=(
                "NONE: no -C/--cd and no --add-dir, so the process cwd is BOTH the AGENTS.md "
                "memory-load root and the only writable dir — out-of-tree bundle cwd and "
                "worktree edit target cannot be separated"),
            notes=(
                "UNSUPPORTED: Kimi merges AGENTS.md root->cwd (v1.29.0); supporting it needs "
                "a working-root flag + an extra-writable-dir grant. Follow-up tracked."),
        )

    def build_argv(self, spec: LaunchSpec, executable: str, *, prompt: str) -> List[str]:
        # Documentation-only: the capability gate prevents this from ever launching. Shown so
        # the intended (if Kimi gains -C/--add-dir) CLI form is reviewable. The prompt is an
        # ATTACHED long option (``--prompt=...``) so a leading ``--`` is parsed literally.
        argv = [executable, f"--prompt={prompt}", "--output-format", "text"]
        if self.model:
            argv += ["-m", self.model]
        return argv
