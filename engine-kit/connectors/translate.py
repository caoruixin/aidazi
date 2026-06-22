#!/usr/bin/env python3
"""connectors.translate — abstract per-role connector grants → harness-native config.

This is the CONNECTOR layer of the loop engine (plan §4.1 facet C "KIT: adapters
translate abstract grant → harness-native"; plan §7 P4). It takes the abstract,
charter-level connector grants for ONE role (each entry shaped by
``schemas/connector-binding.schema.json``) and produces the configuration a given
harness would need to expose those connectors to the role's session.

CRUCIAL boundary — TRANSLATION PRODUCES CONFIG; IT DOES NOT CONNECT.
  * No network, no MCP handshake, no subprocess, no secret VALUES.
  * Secrets are referenced BY NAME only (``${ENV_NAME}`` placeholders); the value
    lives in the adopter env and is resolved by the harness at run time, never here.
  * The output is plain data (dicts/lists) that a harness adapter would write to
    its config (``.mcp.json`` fragment / function list / tool config). Building it
    is pure and deterministic and is exercised fully in offline tests.

DEFAULT-DENY (Constitution §1.7 new item; contract §3). The charter grants the
role NOTHING it does not list. Empty / ``None`` connectors ⇒ an EMPTY config for
every harness. There is no catch-all, no implicit allow.

Per-harness translators:
  * ``claude_code`` → an ``.mcp.json``-style fragment (``mcpServers`` server defs,
    one per ``kind: mcp`` connector) PLUS a flat ``allowed_tools`` list. Tools are
    scoped to the connector's ``tools`` allowlist when given, else namespaced to
    the whole server (``mcp__<id>``). http_api / cli connectors do not produce an
    MCP server entry but DO contribute to ``allowed_tools`` (as ``<id>__<tool>``).
  * ``headless`` → an OpenAI-compatible function-calling ``tools`` list: one
    function-schema entry per exposed tool (or one per connector when ``tools`` is
    omitted). For an OpenAI-compatible API there is no MCP server to launch.
  * ``codex`` → its tool-config form (a ``tools`` list of ``{type, name, scopes,
    server, secrets}`` entries). The function is provided here so the codex adapter
    can inherit it LATER (a sibling agent owns ``adapters/codex.py``); this module
    does not edit that file.

Defensive note (NOT the hard gate). The hard enforcement of
``scopes ⊆ capability_class ⊆ role sandbox`` lives in
``engine-kit/validators/charter_validator.py`` (already built). Here we add a
*defensive* helper, :func:`flag_scope_violations`, that returns a (non-raising)
list of warnings when a write/network-scoped connector is translated for a
read-only context — surfaced as ``_warnings`` on the result so a caller can log
it. It never silently drops a grant and never overrides the validator.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

#: harness ids this layer can translate for. ``codex`` is included so its adapter
#: can inherit translation later, even though codex.py is owned by another agent.
SUPPORTED_HARNESSES = ("claude_code", "headless", "codex")

#: scope classes that exceed a read-only context (used only by the defensive note).
_PRIVILEGED_SCOPES = ("write", "network")


# --------------------------------------------------------------------------- #
# Normalisation helpers (pure)
# --------------------------------------------------------------------------- #
def _as_list(connectors: Optional[Iterable[Mapping[str, Any]]]) -> list[dict]:
    """Coerce the grant to a list of plain dicts; ``None``/empty ⇒ ``[]``.

    Default-deny lives here: there is exactly one way to get a non-empty config,
    and that is to pass explicit connector entries.
    """
    if not connectors:
        return []
    out: list[dict] = []
    for c in connectors:
        if c is None:
            continue
        out.append(dict(c))
    return out


def _connector_tools(connector: Mapping[str, Any]) -> list[str]:
    """The tool/function names a connector exposes to the role.

    Returns the binding's ``tools`` allowlist if present (least-privilege
    narrowing, schema-optional). Empty list ⇒ "all tools the connector exposes",
    which each harness represents in its own native way.
    """
    tools = connector.get("tools")
    if not tools:
        return []
    return [str(t) for t in tools]


def _secret_placeholders(connector: Mapping[str, Any]) -> dict:
    """``{NAME: "${NAME}"}`` env placeholders — never a secret VALUE.

    The harness resolves ``${NAME}`` from the adopter env at run time. Producing a
    placeholder (not a value) is what keeps translation offline + value-free.
    """
    out: dict[str, str] = {}
    for name in connector.get("secrets") or []:
        out[str(name)] = "${" + str(name) + "}"
    return out


def flag_scope_violations(
    connectors: Optional[Iterable[Mapping[str, Any]]],
    *,
    sandbox: str = "workspace_write",
) -> list[str]:
    """DEFENSIVE NOTE (not the hard gate): warn on over-scope for a context.

    The authoritative enforcement of ``scopes ⊆ capability_class ⊆ sandbox`` is
    ``charter_validator``'s. This helper merely *reports* (never raises, never
    drops) when a connector carrying a ``write``/``network`` scope is translated
    for a ``read_only`` context, so a caller can surface it. For any non
    ``read_only`` sandbox it returns ``[]``.
    """
    if sandbox != "read_only":
        return []
    warnings: list[str] = []
    for c in _as_list(connectors):
        over = [s for s in (c.get("scopes") or []) if s in _PRIVILEGED_SCOPES]
        if over:
            warnings.append(
                f"connector {c.get('id')!r} requests scope(s) {sorted(over)} "
                f"in a read_only context (charter_validator enforces; "
                f"this is a defensive note)"
            )
    return warnings


# --------------------------------------------------------------------------- #
# claude_code — .mcp.json fragment + allowed-tools
# --------------------------------------------------------------------------- #
def _claude_code(connectors: list[dict]) -> dict:
    """An ``.mcp.json``-style fragment + a flat ``allowed_tools`` list.

    * ``kind: mcp`` → a server def under ``mcpServers`` (command/url + env
      placeholders), and tool grants namespaced ``mcp__<id>`` (whole server) or
      ``mcp__<id>__<tool>`` (when the binding narrows ``tools``). This mirrors how
      Claude Code names MCP tools.
    * ``http_api`` / ``cli`` → no MCP server, but each contributes ``<id>__<tool>``
      (or bare ``<id>`` when no tools listed) to ``allowed_tools`` so the adapter's
      ``--allowed-tools`` reflects the grant.
    """
    mcp_servers: dict[str, dict] = {}
    allowed_tools: list[str] = []
    for c in connectors:
        cid = str(c.get("id"))
        kind = c.get("kind")
        tools = _connector_tools(c)
        if kind == "mcp":
            server_def: dict[str, Any] = {"type": "mcp"}
            # `server` is a pinned '<ref>@<pin>'. We pass it through verbatim as a
            # `command`-style reference; we never resolve/launch it here.
            server_def["command"] = str(c.get("server", ""))
            env = _secret_placeholders(c)
            if env:
                server_def["env"] = env
            mcp_servers[cid] = server_def
            if tools:
                allowed_tools.extend(f"mcp__{cid}__{t}" for t in tools)
            else:
                # whole-server grant (all tools the server exposes)
                allowed_tools.append(f"mcp__{cid}")
        else:  # http_api / cli — surfaced as named tool grants only
            if tools:
                allowed_tools.extend(f"{cid}__{t}" for t in tools)
            else:
                allowed_tools.append(cid)
    config: dict[str, Any] = {}
    if mcp_servers:
        config["mcp_config"] = {"mcpServers": mcp_servers}
    config["allowed_tools"] = allowed_tools
    return config


# --------------------------------------------------------------------------- #
# headless — OpenAI-compatible function-calling tool list
# --------------------------------------------------------------------------- #
def _headless(connectors: list[dict]) -> dict:
    """An OpenAI-compatible ``tools`` list (function-calling schema entries).

    One ``{"type": "function", "function": {...}}`` entry per exposed tool. When a
    connector omits ``tools`` we emit a single function named for the connector
    (the API has no MCP server to launch — the role calls functions). Secrets are
    NOT embedded; only their names are noted in the description so the adapter can
    resolve them from env at request time.
    """
    functions: list[dict] = []
    for c in connectors:
        cid = str(c.get("id"))
        kind = str(c.get("kind"))
        scopes = list(c.get("scopes") or [])
        secret_names = list(c.get("secrets") or [])
        names = _connector_tools(c) or [cid]
        for name in names:
            fn_name = name if name == cid else f"{cid}__{name}"
            desc = (
                f"{kind} connector {cid!r} (scopes={scopes}); "
                f"server={c.get('server')!r}"
            )
            if secret_names:
                desc += f"; secrets(by-name)={secret_names}"
            functions.append({
                "type": "function",
                "function": {
                    "name": fn_name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    },
                },
            })
    return {"tools": functions}


# --------------------------------------------------------------------------- #
# codex — tool-config form (provided for the codex adapter to inherit later)
# --------------------------------------------------------------------------- #
def _codex(connectors: list[dict]) -> dict:
    """Codex tool-config form.

    A ``tools`` list of ``{type, name, server, scopes, secrets}`` entries (one per
    exposed tool, or one per connector when ``tools`` is omitted). Provided here so
    ``adapters/codex.py`` (owned by a sibling agent) can inherit translation later;
    this module does NOT edit that adapter.
    """
    entries: list[dict] = []
    for c in connectors:
        cid = str(c.get("id"))
        kind = str(c.get("kind"))
        scopes = list(c.get("scopes") or [])
        secret_names = list(c.get("secrets") or [])
        names = _connector_tools(c) or [cid]
        for name in names:
            tool_name = name if name == cid else f"{cid}__{name}"
            entries.append({
                "type": kind,
                "name": tool_name,
                "server": str(c.get("server", "")),
                "scopes": scopes,
                "secrets": secret_names,  # by-name only
            })
    return {"tools": entries}


_TRANSLATORS = {
    "claude_code": _claude_code,
    "headless": _headless,
    "codex": _codex,
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def translate(
    connectors: Optional[Iterable[Mapping[str, Any]]],
    harness: str,
    *,
    sandbox: str = "workspace_write",
) -> dict:
    """Translate abstract per-role ``connectors`` into ``harness``-native config.

    Parameters
    ----------
    connectors:
        The role's granted connector entries (each ~ ``connector-binding`` schema).
        ``None`` / empty ⇒ default-deny ⇒ an EMPTY config for the harness.
    harness:
        One of :data:`SUPPORTED_HARNESSES` (``claude_code`` / ``headless`` /
        ``codex``).
    sandbox:
        The role's sandbox (``read_only`` / ``workspace_write``). Only used to
        attach the DEFENSIVE over-scope note; it is NOT the hard gate.

    Returns
    -------
    dict
        Harness-native config. Shape per harness:
          * ``claude_code`` → ``{"mcp_config": {"mcpServers": {...}}?,
            "allowed_tools": [...]}``
          * ``headless``    → ``{"tools": [<function-schema>, ...]}``
          * ``codex``       → ``{"tools": [<tool-config>, ...]}``
        Always carries ``"_warnings": [...]`` (empty unless the defensive
        over-scope note fired). For empty/None connectors the harness-native keys
        are present but empty (e.g. ``allowed_tools: []`` / ``tools: []``).

    Raises
    ------
    ValueError
        If ``harness`` is not supported (a charter typo should fail loudly, not
        silently produce an over-permissive or empty config).
    """
    if harness not in _TRANSLATORS:
        raise ValueError(
            f"unsupported harness {harness!r}; supported: "
            f"{', '.join(SUPPORTED_HARNESSES)}"
        )
    entries = _as_list(connectors)
    config = _TRANSLATORS[harness](entries)
    config["_warnings"] = flag_scope_violations(entries, sandbox=sandbox)
    return config


def is_empty(config: Mapping[str, Any]) -> bool:
    """True iff ``config`` grants nothing (default-deny result).

    Ignores ``_warnings`` (a note is not a grant). Used by adapters to decide
    whether to emit any harness-native config at all (no-op when empty).
    """
    for key, val in config.items():
        if key == "_warnings":
            continue
        if isinstance(val, (list, dict)) and len(val) > 0:
            return False
        if val:
            return False
    return True
