"""Quick-Fix adapter for the OpenAI Codex CLI — IMPLEMENTED, status EXPERIMENTAL.

Codex has every CLI primitive the lane needs for cold-start isolation (verified against
``codex exec --help``, codex-cli 0.134.0):

  * ``-C/--cd <bundle>``  : the agent's working root = the out-of-tree bundle. Codex
    auto-loads ``AGENTS.md`` by walking up from its working root; the adopter repo is not
    an ancestor of the bundle, so the repo chain is off that walk.
  * ``--add-dir <worktree>`` : "additional directories that should be writable alongside
    the primary workspace" — a write grant, not an instruction-load (the worktree's
    ``AGENTS.md`` is not cold-started).
  * ``--skip-git-repo-check`` : the bundle is not a git repo, so codex needs this to run.
  * ``--sandbox workspace-write`` : edits allowed in the workspace + writable roots;
    network stays OFF by default (a Quick Fix needs none).
  * ``--ephemeral`` : do not persist session files.
  * the PROMPT is read from STDIN (``codex exec`` reads stdin when no positional prompt is
    given), so a leading ``--`` is never mis-parsed as a flag.

WHY EXPERIMENTAL, NOT SUPPORTED. The capability is real, but the lane's bar for
``supported`` is a RECORDED real-launch cold-start proof on this environment (the same bar
claude_code cleared). Codex's AGENTS.md walk-up + ``~/.codex`` global-instruction
interaction has not yet been pinned with a real launch here, so the shipped registry marks
codex ``experimental`` and the launcher FAILS CLOSED for it (``assert_supported`` admits
``supported`` only). This adapter is delivered and reviewable; promoting it to
``supported`` requires landing the evidence, exactly like claude_code did.
"""
from __future__ import annotations

from typing import List, Optional

from .base import HarnessCapability, LaunchSpec, QuickfixAdapter


class CodexAdapter(QuickfixAdapter):
    harness = "codex"
    MEMORY_FILENAME = "AGENTS.md"
    MIN_VERSION = (0, 130, 0)
    PROMPT_DELIVERY = "stdin"

    def __init__(self, *, model: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.model = model

    def default_binary(self) -> str:
        return "codex"

    def capability(self) -> HarnessCapability:
        # The harness CAN isolate (it has alternate-cwd + a write grant). The reason it is
        # not yet `supported` is EVIDENCE, not inability — so the registry, not this flag,
        # is what keeps it from launching until a real cold-start proof is recorded.
        return HarnessCapability(
            headless=True,
            alternate_cwd=True,
            worktree_write_grant=True,
            cold_start_isolation=True,
            isolation_mechanism=(
                "-C out-of-tree bundle (auto-loads bundle/AGENTS.md only); --add-dir grants "
                "worktree write access; --skip-git-repo-check runs outside a git repo"),
            notes=(
                "EXPERIMENTAL: registry status keeps codex non-launchable until a recorded "
                "real-launch cold-start proof lands (the supported bar)."),
        )

    def build_argv(self, spec: LaunchSpec, executable: str, *, prompt: str) -> List[str]:
        # PROMPT_DELIVERY == "stdin": `codex exec` reads the prompt from stdin (fed by
        # run_edit) when no positional prompt is given; it is not an argv token here.
        argv = [
            executable, "exec", "--json",
            "-C", spec.bundle_dir,
            "--add-dir", spec.worktree_dir,
            "--sandbox", "workspace-write",
            "--skip-git-repo-check",
            "--ephemeral",
        ]
        if self.model:
            argv += ["--model", self.model]
        return argv
