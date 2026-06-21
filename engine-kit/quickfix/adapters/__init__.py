"""Quick-Fix harness adapters (Commit 3) — one adapter per harness, uniform contract.

This package is the ONLY place that knows a harness's CLI flags / memory filename. The QF
core (``quickfix.launcher``) stays harness-neutral and only calls an injected
``edit_fn``; ``quickfix.cli`` resolves the right adapter here and builds that ``edit_fn``.

Adapter delivery is INDEPENDENT of the launch decision: this map declares an adapter
EXISTS for a harness; whether the lane may actually launch it is gated separately by the
harness-support registry (``harness_support.yaml`` → ``assert_supported``), which admits
only ``supported``. So an adapter can be present (codex, kimi_code) while the harness is
still non-launchable.
"""
from __future__ import annotations

from .base import (
    ADAPTER_CONTRACT_VERSION,
    EditEvidence,
    HarnessAdapterError,
    HarnessCapability,
    LaunchSpec,
    QuickfixAdapter,
)
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .kimi_code import KimiCodeAdapter

#: harness id → adapter class. Keys MUST match the request `harness` + the registry ids.
ADAPTER_REGISTRY = {
    "claude_code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "kimi_code": KimiCodeAdapter,
}


def resolve_adapter_class(harness: str):
    """Look up the adapter class for ``harness``; fail closed (typed) on an unknown id."""
    try:
        return ADAPTER_REGISTRY[harness]
    except KeyError:
        known = ", ".join(sorted(ADAPTER_REGISTRY))
        raise HarnessAdapterError(
            f"no Quick-Fix adapter for harness {harness!r}; known: [{known}]") from None


def build_adapter(harness: str, **kwargs) -> QuickfixAdapter:
    """Instantiate the adapter for ``harness`` (kwargs forwarded to its constructor)."""
    return resolve_adapter_class(harness)(**kwargs)


__all__ = [
    "ADAPTER_CONTRACT_VERSION",
    "ADAPTER_REGISTRY",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "KimiCodeAdapter",
    "QuickfixAdapter",
    "HarnessAdapterError",
    "HarnessCapability",
    "LaunchSpec",
    "EditEvidence",
    "resolve_adapter_class",
    "build_adapter",
]
