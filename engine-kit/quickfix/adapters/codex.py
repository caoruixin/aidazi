"""Quick-Fix adapter for the OpenAI Codex CLI — IMPLEMENTED, status SUPPORTED.

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

STATUS: SUPPORTED. The lane's bar for ``supported`` — a RECORDED real-launch cold-start proof on
this environment — was met on codex-cli 0.134.0 / macOS arm64
(``archive/2026-06-22-quickfix-codex-e2e-evidence.md``): the bundle's ``AGENTS.md`` is loaded, the
adopter's root Control Plane entry / role-session governance chain is NOT (the bundle is a SIBLING
of the repo, never an ancestor; the adopter canary never appears in output), and the runtime's
scope-guard + targeted-verification + closure boundary holds. A global ``~/.codex/AGENTS.md`` is
EXECUTOR-level and is NOT a blocker — the machine boundary holds regardless of any executor global
instruction. The verified floor is pinned at ``MIN_VERSION`` below; the launcher still fails closed
for any non-``supported`` registry entry.
"""
from __future__ import annotations

from typing import List, Optional

from .base import HarnessCapability, LaunchSpec, QuickfixAdapter


class CodexAdapter(QuickfixAdapter):
    harness = "codex"
    MEMORY_FILENAME = "AGENTS.md"
    # Pinned to the version the real-launch cold-start proof qualified (Increment B); the lane only
    # runs codex >= this floor so memory-loading behavior matches the recorded evidence.
    MIN_VERSION = (0, 134, 0)
    PROMPT_DELIVERY = "stdin"

    def __init__(self, *, model: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.model = model

    def default_binary(self) -> str:
        return "codex"

    def capability(self) -> HarnessCapability:
        # The harness CAN isolate (alternate-cwd + a write grant) and the supported bar was met
        # with a recorded real-launch cold-start proof (Increment B). The registry, not this flag,
        # governs launchability; this declares the proven isolation mechanism.
        return HarnessCapability(
            headless=True,
            alternate_cwd=True,
            worktree_write_grant=True,
            cold_start_isolation=True,
            isolation_mechanism=(
                "-C out-of-tree bundle (auto-loads bundle/AGENTS.md only); --add-dir grants "
                "worktree write access; --skip-git-repo-check runs outside a git repo"),
            notes=(
                "SUPPORTED: recorded real-launch cold-start proof "
                "(archive/2026-06-22-quickfix-codex-e2e-evidence.md, codex 0.134.0)."),
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
