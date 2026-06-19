#!/usr/bin/env python3
"""adapters.claude_code — invoke Claude Code headless behind a uniform spawn().

Reference adapter for the ``claude_code`` harness (ADR-0001 #3; plan §4.1 facet
A). It runs Claude Code in headless / print mode via subprocess
(``claude -p <prompt> --output-format json ...``), then extracts the role's JSON
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

_ALLOW_ENV = "AIDAZI_ALLOW_REAL_ADAPTER"


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
        binary: str = "claude",
        allow_subprocess: bool = False,
        timeout_seconds: int = 600,
        cwd: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(provider=provider, model=model, **kwargs)
        self.binary = binary
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
        # `claude -p` runs headless and prints the result; --output-format json
        # makes it machine-parseable. The PROMPT IS PASSED ON STDIN (subprocess
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
        argv = [self.binary, "-p", "--output-format", "json"]
        if self.model:
            argv += ["--model", self.model]
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
    ) -> dict:
        if not self._enabled():
            raise AdapterError(
                f"claude_code adapter is gated off (set allow_subprocess=True or "
                f"{_ALLOW_ENV}=1 to run the real harness); role={role!r}",
                role=role,
            )
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
                proc = subprocess.run(  # noqa: S603 - argv is a fixed CLI, no shell
                    argv,
                    input=prompt,  # prompt via STDIN, never argv (no dash-injection)
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    cwd=self.cwd,
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
    def _envelope_result(stdout: str, role: str):
        """Parse the `claude --output-format json` envelope and return its
        ``result`` (the model's final message). The envelope itself MUST be JSON
        (claude always emits it); a non-JSON envelope is an ``AdapterError``."""
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"claude_code output was not JSON: {exc}", role=role
            ) from exc
        return (envelope.get("result", envelope)
                if isinstance(envelope, dict) else envelope)

    @classmethod
    def _extract_artifact(cls, stdout: str, role: str) -> dict:
        """ARTIFACT spawn (dev / research): the final message IS the artifact
        (code + handoff prose). Return it wrapped, WITHOUT requiring JSON — the
        driver consumes the side-effect (files written), not this return value."""
        result = cls._envelope_result(stdout, role)
        return result if isinstance(result, dict) else {"artifact": result}

    @classmethod
    def _extract_verdict(cls, stdout: str, role: str) -> dict:
        """VERDICT spawn (review / close): the role prompt instructs the model to
        emit a JSON verdict as its final message. We parse the envelope's
        ``result`` as that verdict, tolerating ```json fences / surrounding prose.
        Any non-object shape is an ``AdapterError`` (driver → gate_hard_fail)."""
        result = cls._envelope_result(stdout, role)
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
