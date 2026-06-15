"""engine-kit memory — Loop Memory substrate (plan §4.4).

Md-file-persisted cross-loop experience: read at ingress (``select``), written at
close (``write_entry`` / ``record_observation``). Standalone deterministic module
— not yet wired into the driver.
"""

from .memory_store import (  # noqa: F401
    AntiGamingViolation,
    MATURITY_L1,
    MATURITY_L2,
    MemoryEntry,
    MemoryError,
    MemoryStore,
    ENTRY_TYPES,
    guard_entry,
    parse_entry,
    render_entry,
    slug,
)

__all__ = [
    "MemoryStore",
    "MemoryEntry",
    "MemoryError",
    "AntiGamingViolation",
    "guard_entry",
    "parse_entry",
    "render_entry",
    "slug",
    "ENTRY_TYPES",
    "MATURITY_L1",
    "MATURITY_L2",
]
