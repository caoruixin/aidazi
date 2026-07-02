#!/usr/bin/env python3
"""adapters.claude_code — invoke Claude Code headless behind a uniform spawn().

Reference adapter for the ``claude_code`` harness (ADR-0001 #3; plan §4.1 facet
A). It runs Claude Code in headless / print mode via subprocess
(``claude -p <prompt> --output-format stream-json ...``), then extracts the role's JSON
verdict from the model's structured output. The DRIVER validates that verdict
against the role's schema; this adapter never lowers the bar.

REAL SUBPROCESS IS GATED. ``spawn`` only shells out when ``allow_subprocess=True``
was passed at construction (or env ``AIDAZI_ALLOW_REAL_ADAPTER=1``). Otherwise it
raises ``AdapterError`` immediately. This mirrors skill-vendor's never-run
``vendor`` path: the code is IMPLEMENTED and reviewable, but the offline test
suite + the demo use the mock adapter and never touch this network/process path.

SANDBOX → PERMISSION MODE. A headless ``claude -p`` session cannot answer an
interactive permission prompt, so a role that must WRITE files (sandbox
``workspace_write``) MUST run with ``--permission-mode acceptEdits`` — otherwise
every Write/Edit is permission-DENIED and the session spins on a denied task
until it times out (the failure this mapping fixes). The sandbox is mapped
DETERMINISTICALLY: ``workspace_write`` → ``acceptEdits`` (auto-accept file edits
within the workspace), ``read_only`` → ``default`` (writes are denied — correct
for a read-only role). Any other sandbox value FAILS CLOSED (``AdapterError``),
never silently guessing a mode that could over-grant write access. The more
permissive ``bypassPermissions`` is intentionally NOT reachable from a normal
sandbox value.

NORMATIVE SOURCE: docs/adr/ADR-0001-engine-substrate.md; process/delivery-loop.md
§4.2.7. Spec wins on any conflict; fix this file.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any, Optional, Sequence

from .base import Adapter, AdapterError
from .monitor import run_with_monitor

_ALLOW_ENV = "AIDAZI_ALLOW_REAL_ADAPTER"


class ToolLeaseProbe:
    """Active-tool lease derived from ``--output-format stream-json`` events.

    An ``assistant`` event carrying a ``tool_use`` content block OPENS an
    invocation (keyed by the block ``id``); the matching ``user`` event
    ``tool_result`` block (``tool_use_id``) CLOSES it — a ``tool_result`` with
    ``is_error`` still closes it (a tool error ends the invocation). The terminal
    ``result`` event clears everything. ``active()`` is true while >=1 invocation
    is open.

    The monitor (adapters/monitor.py) suppresses its SILENCE kill (only) while a
    lease is active, so a legitimately long, output-silent + CPU-idle tool call
    (a build, a sleep, a network/DB wait) is not false-killed; a hung tool is
    still bounded by the per-role hard ``timeout_seconds``. Liveness is NEVER
    inferred from a child PID — only from an observed ``tool_use`` without its
    ``tool_result``. A FRESH probe is built per monitor attempt (the monitor
    calls the factory in ``_run_once``), so no lease is carried across a restart.
    Malformed / unknown-id events never open or extend a lease.
    """

    def __init__(self):
        self._open: set = set()

    def observe(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return  # malformed -> never opens/extends a lease
        if not isinstance(obj, dict):
            return
        etype = obj.get("type")
        if etype == "result":
            self._open.clear()
            return
        if etype not in ("assistant", "user"):
            return
        msg = obj.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if etype == "assistant" and btype == "tool_use":
                bid = block.get("id")
                if bid:
                    self._open.add(bid)
            elif etype == "user" and btype == "tool_result":
                self._open.discard(block.get("tool_use_id"))

    def active(self) -> bool:
        return bool(self._open)


class ClaudeCodeAdapter(Adapter):
    """Adapter for Claude Code (Anthropic) in headless print mode."""

    harness = "claude_code"

    #: Deterministic sandbox → Claude CLI ``--permission-mode``. workspace_write
    #: auto-accepts file edits (so a headless Dev can actually write); read_only
    #: uses the default mode (writes denied). Anything else fails closed.
    _PERMISSION_MODE_BY_SANDBOX = {
        "workspace_write": "acceptEdits",
        "read_only": "default",
    }

    def __init__(
        self,
        *,
        provider: str = "anthropic",
        model: str = "",
        reasoning_effort: str = "",
        binary: str = "claude",
        allow_subprocess: bool = False,
        timeout_seconds: int = 600,
        cwd: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(provider=provider, model=model, **kwargs)
        self.binary = binary
        self.reasoning_effort = reasoning_effort
        self.allow_subprocess = allow_subprocess
        self.timeout_seconds = timeout_seconds
        self.cwd = cwd

    def _enabled(self) -> bool:
        return self.allow_subprocess or os.environ.get(_ALLOW_ENV) == "1"

    def _permission_mode_for(self, sandbox: str, role: str) -> str:
        """Map an aidazi role ``sandbox`` to the Claude CLI ``--permission-mode``.

        Deterministic + FAIL CLOSED: an unsupported sandbox value raises
        ``AdapterError`` rather than guessing a mode (a wrong guess could grant
        unintended write access). The dangerous ``bypassPermissions`` is NOT
        reachable from any normal sandbox value."""
        try:
            return self._PERMISSION_MODE_BY_SANDBOX[sandbox]
        except KeyError:
            raise AdapterError(
                f"claude_code adapter: unsupported sandbox {sandbox!r} for role "
                f"{role!r}; supported: {sorted(self._PERMISSION_MODE_BY_SANDBOX)}. "
                f"Failing closed rather than guessing a Claude --permission-mode.",
                role=role,
            ) from None

    def _build_argv(
        self,
        tools: Sequence[str],
        *,
        extra_allowed_tools: Optional[Sequence[str]] = None,
        mcp_config_path: Optional[str] = None,
        permission_mode: Optional[str] = None,
    ) -> list[str]:
        # `claude -p` runs headless; --output-format stream-json emits newline-
        # delimited events (streamed => output-liveness) ending in a terminal
        # {"type":"result"} envelope. The PROMPT IS PASSED ON STDIN (subprocess
        # ``input=``), NOT as an argv token: a prompt whose first line starts with
        # ``--`` (surviving YAML front-matter, or any body line) would otherwise be
        # mis-parsed as a CLI option by ``claude -p``. Reading the prompt from
        # stdin removes that argv-injection surface entirely — the root-cause fix.
        # (The driver's front-matter strip is now defense-in-depth, not the only
        # guard.) --permission-mode lets the headless session act on its sandbox
        # without an interactive prompt (see the module docstring's SANDBOX →
        # PERMISSION MODE note). allowed-tools enforces the role's tool whitelist.
        # Granted connectors contribute extra allowed-tools (mcp__<id>[__tool]) + an
        # --mcp-config fragment; when no connectors are granted these are omitted
        # entirely (default-deny).
        argv = [self.binary, "-p", "--output-format", "stream-json", "--verbose"]
        if self.model:
            argv += ["--model", self.model]
        if self.reasoning_effort:
            argv += ["--effort", self.reasoning_effort]
        if permission_mode:
            argv += ["--permission-mode", permission_mode]
        merged_tools = list(tools)
        if extra_allowed_tools:
            merged_tools += [t for t in extra_allowed_tools if t not in merged_tools]
        if merged_tools:
            argv += ["--allowed-tools", ",".join(merged_tools)]
        if mcp_config_path:
            argv += ["--mcp-config", mcp_config_path]
        return argv

    def spawn(
        self,
        role: str,
        prompt: str,
        tools: Sequence[str],
        schema: dict,
        *,
        connectors: Optional[Sequence[Any]] = None,
        sandbox: str = "workspace_write",
        network_access: bool = False,  # accepted for uniformity; see note below
    ) -> dict:
        if not self._enabled():
            raise AdapterError(
                f"claude_code adapter is gated off (set allow_subprocess=True or "
                f"{_ALLOW_ENV}=1 to run the real harness); role={role!r}",
                role=role,
            )
        # network_access is accepted for a uniform spawn boundary but the claude
        # adapter passes NO ``--sandbox`` flag: claude Code governs network via its
        # own tool-permission model + the host OS, not a CLI sandbox toggle like
        # codex's. The codex adapter is the one that un-blocks the OS-sandbox
        # network for an explicit grant; here the param is recorded/audited by the
        # driver but does not change the argv. (A claude-backed Dev that needs to
        # install deps does so through its Bash tool, subject to the host's policy.)
        # FAIL CLOSED on an unsupported sandbox BEFORE any I/O — a verdict-/code-
        # producing session must run under a known permission mode.
        permission_mode = self._permission_mode_for(sandbox, role)
        # Facet C: translate any granted connectors → .mcp.json fragment +
        # allowed-tools. GATED/NO-OP when none are passed (default-deny) — the
        # argv is then identical to the pre-connector behavior.
        cfg = self.translate_connectors(connectors, sandbox=sandbox)
        extra_allowed = cfg.get("allowed_tools") or None
        mcp_config = cfg.get("mcp_config") or None
        # --- below here is NEVER exercised in offline tests ------------------- #
        mcp_path: Optional[str] = None
        if mcp_config:
            fd, mcp_path = tempfile.mkstemp(prefix="aidazi-mcp-", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(mcp_config, fh)
        argv = self._build_argv(
            tools,
            extra_allowed_tools=extra_allowed, mcp_config_path=mcp_path,
            permission_mode=permission_mode)
        try:
            try:
                proc = run_with_monitor(
                    argv,
                    input=prompt,  # prompt via STDIN, never argv (no dash-injection)
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    cwd=self.cwd,
                    role=role,
                    harness=self.harness,
                    liveness_probe_factory=ToolLeaseProbe,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise AdapterError(
                    f"claude_code spawn failed to run {self.binary!r}: {exc}",
                    role=role,
                ) from exc
            if proc.returncode != 0:
                raise AdapterError(
                    f"claude_code spawn exited {proc.returncode}: "
                    f"{proc.stderr.strip()[:500]}",
                    role=role,
                )
            # ARTIFACT spawn (no verdict schema — e.g. dev / research): the model's
            # final message IS the artifact (code + handoff prose), NOT a JSON
            # verdict, so return it raw. VERDICT spawn (schema present — review /
            # close): parse the final message as the JSON verdict.
            if not schema:
                return self._extract_artifact(proc.stdout, role)
            return self._extract_verdict(proc.stdout, role)
        finally:
            if mcp_path and os.path.exists(mcp_path):
                os.unlink(mcp_path)

    @staticmethod
    def _final_result_from_stream(stdout: str, role: str):
        """Extract the final message from a ``--output-format stream-json`` run.

        The stream is newline-delimited JSON: streamed system/assistant/user
        events, then a single terminal ``{"type": "result", ...}``. We scan for
        that terminal event and return its ``result`` (the model's final message
        — artifact prose or a JSON verdict string). Errors are surfaced, never
        silently downgraded:
          * terminal ``is_error`` true / an ``error_*`` subtype -> AdapterError
          * no terminal result event (truncated/killed stream) -> AdapterError
        A single bare JSON object (a stray ``--output-format json`` envelope) is
        accepted as the terminal event (back-compat). A non-JSON line is an
        error EXCEPT a final truncation fragment once a terminal result was seen.
        """
        terminal = None
        lines = stdout.split("\n")
        for i, raw in enumerate(lines):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # tolerate ONLY a trailing truncation fragment after a terminal
                if terminal is not None and i == len(lines) - 1:
                    continue
                raise AdapterError(
                    f"claude_code stream-json had a non-JSON line: {line[:120]!r}",
                    role=role)
            if isinstance(obj, dict) and obj.get("type") == "result":
                terminal = obj
        if terminal is None:
            # back-compat: ONLY a legacy result-BEARING envelope (a stray
            # --output-format json object: type==result, or a bare
            # {"result": ...}). A single NON-terminal event — e.g. a truncated
            # one-line {"type":"assistant",...} — must NOT be accepted as
            # success; it falls through to the no-terminal-event AdapterError.
            s = stdout.strip()
            if s:
                try:
                    obj = json.loads(s)
                    if isinstance(obj, dict) and (
                            obj.get("type") == "result" or "result" in obj):
                        terminal = obj
                except json.JSONDecodeError:
                    pass
        if terminal is None:
            raise AdapterError(
                "claude_code stream-json produced no terminal result event",
                role=role)
        if terminal.get("is_error") or str(
                terminal.get("subtype", "")).startswith("error"):
            detail = terminal.get("result") or terminal.get("error") or ""
            raise AdapterError(
                f"claude_code session errored (subtype="
                f"{terminal.get('subtype')!r}): {str(detail)[:200]!r}",
                role=role)
        return terminal.get("result", terminal)

    @classmethod
    def _extract_artifact(cls, stdout: str, role: str) -> dict:
        """ARTIFACT spawn (dev / research): the final message IS the artifact
        (code + handoff prose). Return it wrapped, WITHOUT requiring JSON — the
        driver consumes the side-effect (files written), not this return value."""
        result = cls._final_result_from_stream(stdout, role)
        return result if isinstance(result, dict) else {"artifact": result}

    @classmethod
    def _extract_verdict(cls, stdout: str, role: str) -> dict:
        """VERDICT spawn (review / close): the role prompt instructs the model to
        emit a JSON verdict as its final message. We parse the envelope's
        ``result`` as that verdict, tolerating ```json fences / surrounding prose.
        Any non-object shape is an ``AdapterError`` (driver → gate_hard_fail)."""
        result = cls._final_result_from_stream(stdout, role)
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            return cls._coerce_json_object(result, role)
        raise AdapterError(
            f"claude_code produced no parseable verdict (got {type(result).__name__})",
            role=role,
        )

    @staticmethod
    def _coerce_json_object(text: str, role: str) -> dict:
        """Parse a JSON object from a model message, tolerating a ```json code
        fence or surrounding prose. Tries the whole string, then the outermost
        ``{ ... }`` substring. Raises ``AdapterError`` if neither yields an object."""
        s = text.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1] if "\n" in s else ""
            fence = s.rfind("```")
            if fence != -1:
                s = s[:fence]
            s = s.strip()
            if s[:4].lower() == "json":
                s = s[4:].strip()
        for candidate in (s, s[s.find("{"): s.rfind("}") + 1] if "{" in s and "}" in s else ""):
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise AdapterError(
            f"claude_code result field was not a JSON verdict: {text[:200]!r}",
            role=role,
        )
