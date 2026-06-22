# engine-kit / connectors — the CONNECTOR layer (Facet C)

Reference implementation of **Facet C — connector binding** of the Role
Configuration Contract (plan §4.1 facet C; plan §7 **P4**). Two deterministic,
**offline, no-LLM** capabilities:

1. **`translate(connectors, harness, *, sandbox=...)`** — turn a role's abstract,
   charter-level connector grants (each entry shaped by
   `schemas/connector-binding.schema.json`) into **harness-native CONFIG**.
2. **`propose(repo_dir)`** — **propose-only** discovery: scan an adopter repo for
   `.mcp.json` / tool config and return **candidates** marked `proposed`.

> **Normative source** is the spec, not this kit:
> `process/role-configuration-contract.md` §3 · `schemas/connector-binding.schema.json`
> · `schemas/connector-catalog.schema.json` · `archive/2026-06-15-v2-loop-engine-plan.md`
> §4.1 facet C + §7 P4. On any conflict **the spec wins; the kit is then a bug.**

## The two hard boundaries

- **TRANSLATION PRODUCES CONFIG; IT DOES NOT CONNECT.** No network, no MCP
  handshake, no subprocess, no secret **values**. Secrets are emitted only as
  `${ENV_NAME}` placeholders — the harness resolves them from the adopter env at
  run time.
- **DISCOVERY IS PROPOSE-ONLY.** `propose()` never mutates the repo / charter /
  any allowlist, never connects, never reads a secret value. Every candidate is
  `status: "proposed"` with `provenance` (source file + key). A human must copy a
  chosen candidate into a charter `tooling.<role>.connectors[]` (adding `scopes`)
  to grant it. *"A scan is an authoring aid, NOT runtime authorization."*

**Default-deny.** Empty / `None` connectors ⇒ an **empty config** for every
harness. There is no catch-all and no implicit allow.

The hard `scopes ⊆ capability_class ⊆ sandbox` enforcement is
`engine-kit/validators/charter_validator.py`'s. This layer adds only a
**defensive, non-raising** over-scope note (`_warnings`); it never drops a grant
and never overrides the validator.

## `translate(connectors, harness, sandbox="workspace_write") -> dict`

Per-harness output:

| harness | output shape |
|---|---|
| `claude_code` | `{"mcp_config": {"mcpServers": {<id>: {...}}}?, "allowed_tools": [...], "_warnings": [...]}` — an `.mcp.json`-style fragment (one server per `kind: mcp`) + a flat allowed-tools list (`mcp__<id>[__tool]` for MCP, `<id>[__tool]` for http_api/cli). |
| `headless` | `{"tools": [<openai-function-schema>, ...], "_warnings": [...]}` — one `{"type":"function","function":{...}}` entry per exposed tool (or per connector when `tools` omitted). |
| `codex` | `{"tools": [{type,name,server,scopes,secrets}, ...], "_warnings": [...]}` — codex tool-config form. **Provided so `adapters/codex.py` (owned by another agent) can inherit it later; this layer does not edit codex.py.** |

- A binding's optional `tools` allowlist **scopes** the grant to a subset; omit it
  ⇒ the whole server (claude_code `mcp__<id>`) / one function named for the
  connector (headless).
- `is_empty(config)` → `True` iff a config grants nothing (ignores `_warnings`).
  Adapters use it to stay no-op when no connectors are granted.

```python
from connectors import translate
cc  = translate(grant, "claude_code")     # .mcp.json fragment + allowed-tools
fns = translate(grant, "headless")        # OpenAI function list
translate(None, "claude_code")            # default-deny → {"allowed_tools": [], "_warnings": []}
```

## `propose(repo_dir, max_depth=None) -> list[dict]`

Read-only walk of `repo_dir` (skips `.git`, `node_modules`, `.venv`, … and
`.orchestrator`) collecting `.mcp.json` / `mcp.json` server defs. Each candidate:

```jsonc
{
  "id": "github", "kind": "mcp",
  "server": "npx -y @modelcontextprotocol/server-github",
  "tools": [], "secrets": ["GITHUB_TOKEN"],   // secret NAMES only, never values
  "proposed_scopes": [],                        // default-deny: human grants scope
  "status": "proposed", "pinned": false,        // unpinned ⇒ human must pin
  "provenance": { "source_file": ".mcp.json",
                  "source_key": "mcpServers.github",
                  "discovered_by": "connectors.discovery.propose" }
}
```

A malformed config yields `[]` for that file (advisory scan never aborts).

## Adapter wiring (backward-compatible)

`adapters/base.py` gains `translate_connectors(connectors, sandbox=...)` (delegates
to `connectors.translate` for the adapter's `harness`; `None`/empty ⇒ `{}`).
`adapters/claude_code.py` + `adapters/headless.py` accept an **optional** keyword
`connectors=None` on `spawn` and feed the translated config into their native
request (claude_code: extra `--allowed-tools` + a temp `--mcp-config`; headless:
the payload `tools` list). **When no connectors are passed the spawn path is
byte-for-byte identical to before** — the existing driver call
`adapter.spawn(role, prompt, tools, schema)` (positional, no connectors) is
unaffected, so the 84 orchestrator tests stay green. `codex.py` and
`adapters/__init__.py` are owned by another agent and are untouched.

## Tests

`engine-kit/connectors/tests/` (stdlib `unittest`, offline). Run:

```bash
python -m unittest discover -s engine-kit/connectors/tests -p 'test_*.py'
```
