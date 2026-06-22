"""engine-kit per-harness adapters (ADR-0001 #3).

Uniform interface: ``spawn(role, prompt, tools, schema) -> schema-valid verdict``.
The driver selects one adapter per role (charter routing) and consumes only
schema-valid JSON verdicts. Real I/O in claude_code / headless is gated off and
never exercised in offline tests; the mock adapter drives tests + the demo.
"""

from .base import Adapter, AdapterError
from .mock import MockAdapter
from .claude_code import ClaudeCodeAdapter
from .headless import HeadlessAdapter
from .codex import CodexAdapter
from .kimi import KimiAdapter

#: harness id → adapter class, for charter-driven routing in the driver.
ADAPTER_REGISTRY = {
    "mock": MockAdapter,
    "claude_code": ClaudeCodeAdapter,
    "headless": HeadlessAdapter,
    "codex": CodexAdapter,
    "kimi": KimiAdapter,
}


def resolve_adapter_class(harness: str, *, role: str = ""):
    """Look up the adapter class for ``harness`` in ADAPTER_REGISTRY.

    A direct ``ADAPTER_REGISTRY[harness]`` raises a bare, contextless ``KeyError``
    when a role routes to an unknown harness id (e.g. a charter typo). Wrap it in
    a typed ``AdapterError`` naming the offending harness, the role, and the known
    harness ids so the failure is actionable instead of an opaque ``KeyError``.
    Behaviour for a KNOWN harness is identical to the dict lookup.
    """
    try:
        return ADAPTER_REGISTRY[harness]
    except KeyError:
        known = ", ".join(sorted(ADAPTER_REGISTRY))
        role_ctx = f" for role {role!r}" if role else ""
        raise AdapterError(
            f"unknown harness {harness!r}{role_ctx}; known: [{known}]",
            role=role or None,
        ) from None


__all__ = [
    "Adapter",
    "AdapterError",
    "MockAdapter",
    "ClaudeCodeAdapter",
    "HeadlessAdapter",
    "CodexAdapter",
    "KimiAdapter",
    "ADAPTER_REGISTRY",
    "resolve_adapter_class",
]
