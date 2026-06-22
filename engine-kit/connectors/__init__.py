"""engine-kit connectors — the CONNECTOR layer (Facet C; plan §4.1, §7 P4).

Two deterministic, OFFLINE, no-LLM capabilities:

  * ``translate(connectors, harness, *, sandbox=...)`` — turn a role's abstract,
    charter-level connector grants (``schemas/connector-binding.schema.json``)
    into harness-native CONFIG (Claude Code ``.mcp.json`` fragment + allowed-tools
    / headless OpenAI function list / codex tool config). TRANSLATION PRODUCES
    CONFIG; IT DOES NOT CONNECT. Default-deny: empty/None ⇒ empty config.

  * ``propose(repo_dir)`` — PROPOSE-ONLY discovery: scan an adopter repo for
    ``.mcp.json`` / tool config and return CANDIDATES marked ``proposed`` (with
    provenance). NEVER auto-grants, NEVER mutates, NEVER connects.

Both are authoring aids, NOT runtime authorization — the hard
``scopes ⊆ capability_class ⊆ sandbox`` gate is ``charter_validator``'s. This
module adds a non-raising defensive over-scope note (``_warnings``) only.

NORMATIVE SOURCE: process/role-configuration-contract.md §3 (Facet C),
schemas/connector-binding.schema.json, schemas/connector-catalog.schema.json,
archive/2026-06-15-v2-loop-engine-plan.md §4.1 facet C + §7 P4. Spec wins on any
conflict; this is a reference implementation — fix the kit, not the spec.
"""

from .translate import (
    translate,
    is_empty,
    flag_scope_violations,
    SUPPORTED_HARNESSES,
)
from .discovery import propose

__all__ = [
    "translate",
    "is_empty",
    "flag_scope_violations",
    "SUPPORTED_HARNESSES",
    "propose",
]
