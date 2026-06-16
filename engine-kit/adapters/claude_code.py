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

    def _build_argv(
        self,
        prompt: str,
        tools: Sequence[str],
        *,
        extra_allowed_tools: Optional[Sequence[str]] = None,
        mcp_config_path: Optional[str] = None,
    ) -> list[str]:
        # `claude -p <prompt>` runs headless and prints the result; JSON output
        # format makes the result machine-parseable. allowed-tools enforces the
        # role's tool whitelist at the harness boundary. Granted connectors
        # contribute extra allowed-tools (mcp__<id>[__tool]) + an --mcp-config
        # fragment; when no connectors are granted these are omitted entirely
        # (default-deny, and spawn stays byte-for-byte identical to before).
        argv = [self.binary, "-p", prompt, "--output-format", "json"]
        if self.model:
            argv += ["--model", self.model]
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
            prompt, tools,
            extra_allowed_tools=extra_allowed, mcp_config_path=mcp_path)
        try:
            try:
                proc = subprocess.run(  # noqa: S603 - argv is a fixed CLI, no shell
                    argv,
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
            return self._extract_verdict(proc.stdout, role)
        finally:
            if mcp_path and os.path.exists(mcp_path):
                os.unlink(mcp_path)

    @staticmethod
    def _extract_verdict(stdout: str, role: str) -> dict:
        """Parse the `claude --output-format json` envelope and pull the verdict.

        The envelope carries a ``result`` string containing the model's final
        message; the role prompt instructs the model to emit ONLY a JSON verdict
        there. We parse the envelope, then parse ``result`` as the verdict.
        Any non-JSON shape is an ``AdapterError`` (the driver → gate_hard_fail).
        """
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"claude_code output was not JSON: {exc}", role=role
            ) from exc
        result = envelope.get("result", envelope) if isinstance(envelope, dict) else envelope
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError as exc:
                raise AdapterError(
                    f"claude_code result field was not a JSON verdict: {exc}",
                    role=role,
                ) from exc
        raise AdapterError(
            f"claude_code produced no parseable verdict (got {type(result).__name__})",
            role=role,
        )
