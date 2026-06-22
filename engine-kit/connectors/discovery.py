#!/usr/bin/env python3
"""connectors.discovery — PROPOSE-ONLY connector scanner (plan §4.1 facet C KIT).

Scans an adopter repo for connector-bearing config (``.mcp.json`` / MCP server
defs / tool configs) and returns CANDIDATES a human can then approve into a
charter's ``tooling.<role>.connectors[]`` allowlist.

PROPOSE-ONLY is a HARD discipline (contract §3; plan §4.1: "Scan = authoring aid,
NOT runtime authorization"; charter ``discovery.mode: propose_only`` "NEVER
auto-authorizes"). Therefore this module:
  * NEVER mutates the repo, the charter, or any allowlist (read-only filesystem).
  * NEVER connects to a server, reads a secret VALUE, or launches anything.
  * Marks every candidate ``status: "proposed"`` and records ``provenance`` =
    where it was found (relative path + the key/section), so a human can audit the
    suggestion before granting it.

The returned candidates are SUGGESTIONS shaped to ease (but not perform) the human
step of writing a ``connector-binding`` entry. They deliberately do NOT carry a
``scopes`` grant — scope is a human trust decision, default-deny — and they do not
include any value-bearing secret, only env-var NAMES discovered in the config.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

#: filenames we treat as MCP / connector config when scanning a repo.
_MCP_FILENAMES = (".mcp.json", "mcp.json")

#: dirs we never descend into (noise + perf; none of these hold adopter config).
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__",
              ".orchestrator", "dist", "build", ".mypy_cache", ".pytest_cache"}

#: env-var placeholder pattern markers used to recover secret NAMES from config
#: WITHOUT ever reading a value (we only ever capture the NAME).
_ENV_MARKERS = ("${", "$")


def _rel(path: str, root: str) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def _extract_secret_names(env: Any) -> list[str]:
    """Recover env-var NAMES referenced by an mcp server ``env`` block.

    Captures the NAME only (never a value): an ``env`` entry whose value looks
    like ``${FOO}`` / ``$FOO`` contributes ``FOO``; a bare key is also kept as a
    candidate secret name. Values that are not placeholders are IGNORED (we refuse
    to surface a literal value).
    """
    names: list[str] = []
    if not isinstance(env, dict):
        return names
    for key, val in env.items():
        if isinstance(val, str) and val.startswith(_ENV_MARKERS):
            inner = val.strip("${} ").strip()
            if inner:
                names.append(inner)
            elif isinstance(key, str):
                names.append(key)
        elif isinstance(key, str):
            # bare key with a non-placeholder value: keep the NAME as a candidate
            # (so the human sees a secret is needed) but never the value.
            names.append(key)
    # dedupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _candidate_from_mcp_server(
    server_id: str,
    server_def: Any,
    *,
    source_file: str,
    source_key: str,
) -> dict:
    """Build one PROPOSED candidate from a single MCP server def.

    Never grants scope: ``proposed_scopes`` is left empty/unknown — the human
    decides. ``kind`` is inferred (url ⇒ http-ish mcp, command ⇒ cli-backed mcp)
    but always recorded as ``mcp`` for an ``mcpServers`` entry.
    """
    server_ref = ""
    tools: list[str] = []
    secrets: list[str] = []
    if isinstance(server_def, dict):
        # common shapes: {"command": "...", "args": [...], "env": {...}}
        #                {"url": "https://..."} / {"type": "...", ...}
        server_ref = (
            str(server_def.get("command")
                or server_def.get("url")
                or server_def.get("server")
                or "")
        )
        if server_def.get("args"):
            server_ref = (server_ref + " " +
                          " ".join(str(a) for a in server_def["args"])).strip()
        secrets = _extract_secret_names(server_def.get("env"))
        raw_tools = server_def.get("tools")
        if isinstance(raw_tools, list):
            tools = [str(t) for t in raw_tools]
    pinned = bool(server_ref) and "@" in server_ref
    return {
        "id": server_id,
        "kind": "mcp",
        "server": server_ref,
        "tools": tools,
        "secrets": secrets,            # NAMES only, never values
        "proposed_scopes": [],         # default-deny: human grants scope
        "status": "proposed",          # NEVER auto-granted
        "pinned": pinned,              # unpinned ⇒ human must pin before granting
        "provenance": {
            "source_file": source_file,
            "source_key": f"{source_key}.{server_id}",
            "discovered_by": "connectors.discovery.propose",
        },
    }


def _scan_mcp_file(path: str, root: str) -> list[dict]:
    """Parse one ``.mcp.json``-style file → list of proposed candidates.

    Tolerant of a malformed file (returns ``[]`` rather than raising) so one bad
    config never aborts a repo scan; the scan is advisory only.
    """
    rel = _rel(path, root)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    candidates: list[dict] = []
    # canonical: {"mcpServers": {"<id>": {...}}}; also accept a bare {"<id>": {...}}
    servers = data.get("mcpServers")
    source_key = "mcpServers"
    if not isinstance(servers, dict):
        # bare mapping of id → def (only when every value looks like a server def)
        if all(isinstance(v, dict) for v in data.values()) and data:
            servers = data
            source_key = "<root>"
        else:
            servers = {}
    for server_id, server_def in servers.items():
        candidates.append(
            _candidate_from_mcp_server(
                str(server_id), server_def,
                source_file=rel, source_key=source_key,
            )
        )
    return candidates


def propose(
    repo_dir: str,
    *,
    max_depth: Optional[int] = None,
) -> list[dict]:
    """Scan ``repo_dir`` for connector config → PROPOSED candidates (read-only).

    Parameters
    ----------
    repo_dir:
        Path to an adopter repo to scan. NOT mutated.
    max_depth:
        Optional cap on directory recursion depth (``None`` ⇒ unlimited). Depth 0
        = only ``repo_dir`` itself.

    Returns
    -------
    list[dict]
        Candidate connectors, each ``status: "proposed"`` with ``provenance``
        (source file + key). NEVER an authorization: a human must copy a chosen
        candidate into a charter ``connectors[]`` (adding ``scopes``) to grant it.
        Empty list when nothing connector-like is found. Sorted deterministically
        by ``(source_file, id)``.

    Notes
    -----
    PROPOSE-ONLY: this function performs NO writes, NO network, NO secret-value
    reads, and NO charter mutation. It is the "authoring aid" of contract §3, not
    runtime authorization.
    """
    candidates: list[dict] = []
    if not os.path.isdir(repo_dir):
        return candidates
    repo_dir = os.path.abspath(repo_dir)
    base_depth = repo_dir.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(repo_dir):
        # prune skip dirs + enforce depth cap (read-only traversal)
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if max_depth is not None:
            depth = dirpath.rstrip(os.sep).count(os.sep) - base_depth
            if depth >= max_depth:
                dirnames[:] = []
        for fname in filenames:
            if fname in _MCP_FILENAMES:
                candidates.extend(_scan_mcp_file(
                    os.path.join(dirpath, fname), repo_dir))
    candidates.sort(key=lambda c: (c["provenance"]["source_file"], c["id"]))
    return candidates
