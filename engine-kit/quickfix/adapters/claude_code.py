"""Quick-Fix adapter for Claude Code (Anthropic) — the reference SUPPORTED harness.

Cold-start isolation (the lane's premise) is achieved WITHOUT any special "reduced
governance" mode:

  * cwd = the out-of-tree ephemeral BUNDLE. Claude Code auto-loads ``CLAUDE.md`` by walking
    UP from cwd to the filesystem root (plus ``~/.claude/CLAUDE.md``). The bundle ships its
    own minimal ``CLAUDE.md``; the adopter repo is NOT an ancestor of the bundle, so the
    repo's root entry / role-session governance context is never on that walk.
  * the worktree is granted with ``--add-dir <worktree>`` — which Claude Code treats as a
    FILE-ACCESS grant only and does NOT auto-load that directory's ``CLAUDE.md`` from
    (archive/2026-06-21-full-coldstart-baseline-evidence.md, verified against the Claude
    Code memory docs). So even though the worktree is a full checkout that contains the
    repo's root memory file, that file is never cold-started.

The result: the Quick-Fix session cold-starts the bundle's three local files only, never
the adopter repo's default Control Plane entry or role-session governance chain.
``~/.claude/CLAUDE.md`` (the user's own global) still loads — but that is orthogonal to
the repo chain and would load in any session; the evidence records it honestly.

CLI form — verified against Claude Code 2.1.170 (``claude --help``):
    claude -p --output-format json --permission-mode acceptEdits \
           --add-dir <worktree> [--allowed-tools ...] [--model M]
  - ``-p/--print``: non-interactive; prints the result and exits.
  - ``--permission-mode acceptEdits``: a headless session cannot answer a permission
    prompt, so file edits are auto-accepted within the granted workspace (cwd bundle +
    ``--add-dir`` worktree). The dangerous ``bypassPermissions`` is intentionally NOT used.
  - ``--add-dir <worktree>``: the worktree write grant (besides the cwd bundle, which is
    ephemeral scratch). The adopter's original repo is never granted — that is the boundary
    the launcher also enforces (``_assert_original_repo_unpolluted``).
  - ``--allowed-tools``: a deliberately edit-only tool set (NO ``Bash`` — no shell escape).
  - the PROMPT is passed on STDIN (never an argv token), so a leading ``--`` cannot be
    mis-parsed as a flag.
"""
from __future__ import annotations

from typing import List, Optional

from .base import HarnessCapability, LaunchSpec, QuickfixAdapter


class ClaudeCodeAdapter(QuickfixAdapter):
    harness = "claude_code"
    MEMORY_FILENAME = "CLAUDE.md"
    MIN_VERSION = (2, 0, 0)
    PROMPT_DELIVERY = "stdin"

    #: Edit-only tool whitelist for the headless session. Bash is intentionally absent so
    #: the harness cannot shell out of the worktree/bundle (defense in depth — the
    #: launcher's guard + original-repo-pollution check are the hard backstops).
    EDIT_TOOLS = ("Read", "Edit", "Write", "MultiEdit", "Glob", "Grep", "LS")

    def __init__(self, *, model: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.model = model

    def default_binary(self) -> str:
        return "claude"

    def capability(self) -> HarnessCapability:
        return HarnessCapability(
            headless=True,
            alternate_cwd=True,
            worktree_write_grant=True,
            cold_start_isolation=True,
            isolation_mechanism=(
                "cwd=out-of-tree bundle (auto-loads bundle/CLAUDE.md only); "
                "--add-dir grants worktree FILE access without loading its CLAUDE.md"),
            notes=(
                "~/.claude/CLAUDE.md (user global) still loads — orthogonal to the repo "
                "root entry, which is never an ancestor of the bundle."),
        )

    def build_argv(self, spec: LaunchSpec, executable: str, *, prompt: str) -> List[str]:
        # PROMPT_DELIVERY == "stdin": the prompt is fed on stdin by run_edit, not here.
        argv = [
            executable, "-p",
            "--output-format", "json",
            "--permission-mode", "acceptEdits",
            "--add-dir", spec.worktree_dir,
            "--allowed-tools", ",".join(self.EDIT_TOOLS),
        ]
        if self.model:
            argv += ["--model", self.model]
        return argv
