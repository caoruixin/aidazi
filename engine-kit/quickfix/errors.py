"""Typed Quick-Fix errors — clean, reported failures instead of raw tracebacks.

Every error here is fail-closed: when one is raised the lane does NOT proceed into a
reduced-governance run and does NOT write a `completed` record.
"""
from __future__ import annotations

from typing import Optional, Sequence


class QuickfixError(Exception):
    """Base class for all Quick-Fix lane errors."""


class RequestError(QuickfixError):
    """The quickfix-request is missing, unparseable, or schema-invalid (fail-closed)."""


class PolicyError(QuickfixError):
    """The protected-surface policy/overlay is missing, unparseable, or invalid."""


class GlobError(QuickfixError):
    """A glob is not in the approved safe subset / not a supported pattern (fail-closed)."""


class HarnessUnsupportedError(QuickfixError):
    """The requested harness is not marked `supported` in the registry (fail-closed)."""


class CleanTreeError(QuickfixError):
    """The repo working tree is dirty at launch (QF v1 requires a clean tree)."""


class GitError(QuickfixError):
    """A git subprocess failed. Carries cmd/returncode/stderr for a clean report."""

    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str):
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stderr = (stderr or "").strip()
        super().__init__(
            f"git failed ({' '.join(self.cmd)}) [exit {returncode}]: {self.stderr}"
        )


class VerificationError(QuickfixError):
    """The targeted verification could not be run (bad argv / cwd escape / not allowed)."""


class RecordError(QuickfixError):
    """The append-only record could not be written/validated."""


class EscalationRequired(QuickfixError):
    """A controlled in-lane stop: the work must escalate to Full framework.

    Raising this is NOT a crash — the launcher catches it, preserves the investigation
    (patch + diff + handoff) BEFORE teardown, and writes an `escalated` record.
    """

    # Stable reason codes (mirror templates/quickfix-escalation-handoff.md triggers).
    SCOPE_EXPANSION = "scope_expansion"
    PROTECTED_SURFACE = "protected_surface_hit"
    VERIFICATION_FAILURE = "verification_failure"
    SYMLINK_OR_GITLINK = "symlink_or_gitlink_change"
    INCONSISTENT_RESULT = "inconsistent_result"
    ORIGINAL_REPO_POLLUTED = "original_repo_polluted"
    UNKNOWN_SEMANTIC = "unknown_semantic_or_new_design_choice"

    def __init__(self, reason: str, detail: str,
                 violations: Optional[Sequence[str]] = None):
        self.reason = reason
        self.detail = detail
        self.violations = list(violations or [])
        super().__init__(f"escalation required ({reason}): {detail}")
