#!/usr/bin/env python3
"""adapters.kimi — invoke the Kimi Code agentic CLI headless behind spawn().

Reference adapter for the ``kimi`` harness (a coding-agent CLI from Moonshot AI;
Kimi Code / K2.7). Like claude_code / codex it runs an AGENTIC session that reads
and WRITES files — so it can back the Dev role (an artifact spawn whose output is
code + a handoff), not just verdict roles.

CLI FORM — verified against Kimi Code 0.16.0 (``kimi --help``):
    kimi -p <prompt> --output-format text [-m <model>]
  - ``-p/--prompt`` : run ONE prompt non-interactively and print the response.
    In ``-p`` mode the agent auto-approves its own tool use (it WRITES files),
    so NO ``--yolo``/``--auto`` flag is passed — in fact ``-p`` REFUSES to combine
    with them ("Cannot combine --prompt with --yolo/--auto").
  - ``-m/--model`` : model alias (e.g. ``kimi-code/kimi-for-coding`` = "K2.7
    Code", the configured default). Omitted ⇒ config.toml default_model.
  - ``--output-format text`` : stdout is the model's FINAL response (the agent's
    reasoning goes to STDERR); ``stream-json`` is also available but unused here.
  The CLI installs to ``~/.kimi-code/bin/kimi`` (not on PATH by default), so the
  binary defaults to ``which('kimi')`` then that path.

REAL SUBPROCESS IS GATED. ``spawn`` only shells out when ``allow_subprocess=True``
(or env ``AIDAZI_ALLOW_REAL_ADAPTER=1``); otherwise it raises ``AdapterError``.
The offline test suite + the demo use the mock adapter and never touch this path.

ARTIFACT vs VERDICT. With NO schema (dev / research): the final response IS the
artifact (code + handoff prose) — returned raw, files already written. With a
schema (review / acceptance, if ever bound to kimi): the final message must be a
JSON verdict; we firmly instruct that + parse it tolerantly (fence/prose).

NORMATIVE SOURCE: docs/adr/ADR-0001-engine-substrate.md; process/delivery-loop.md
§4.2.7. Spec wins on any conflict; fix this file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Optional, Sequence

from .base import Adapter, AdapterError
from .monitor import run_with_monitor

_ALLOW_ENV = "AIDAZI_ALLOW_REAL_ADAPTER"
_DEFAULT_KIMI_PATH = os.path.expanduser("~/.kimi-code/bin/kimi")


class KimiAdapter(Adapter):
    """Adapter for the Kimi Code agentic CLI (Moonshot) in headless prompt mode."""

    harness = "kimi"

    def __init__(
        self,
        *,
        provider: str = "moonshot",
        model: str = "",
        binary: Optional[str] = None,
        allow_subprocess: bool = False,
        timeout_seconds: int = 600,
        cwd: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(provider=provider, model=model, **kwargs)
        # Kimi Code installs to ~/.kimi-code/bin/kimi; prefer a PATH copy if present.
        self.binary = binary or shutil.which("kimi") or _DEFAULT_KIMI_PATH
        self.allow_subprocess = allow_subprocess
        self.timeout_seconds = timeout_seconds
        self.cwd = cwd

    def _enabled(self) -> bool:
        return self.allow_subprocess or os.environ.get(_ALLOW_ENV) == "1"

    def _build_argv(self, prompt: str, tools: Sequence[str]) -> list[str]:
        # `kimi --output-format text` runs one agentic prompt non-interactively
        # (writing files as needed) and prints the final response to stdout. The
        # prompt is passed via the ATTACHED long-option form ``--prompt=<value>``,
        # NOT ``-p <value>`` as a separate token: an attached value is parsed
        # literally even when it starts with ``--``, so a prompt/body line leading
        # with a dash can't be mis-parsed as a CLI option (parity with the
        # stdin-based claude_code/codex root-cause fix). No per-call allowed-tools
        # flag, so tool-gating for this harness lives in the prompt, not argv.
        argv = [self.binary, f"--prompt={prompt}", "--output-format", "text"]
        if self.model:
            argv += ["-m", self.model]
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
                f"kimi adapter is gated off (set allow_subprocess=True or "
                f"{_ALLOW_ENV}=1 to run the real harness); role={role!r}",
                role=role,
            )
        # network_access is accepted for a uniform spawn boundary but NOT acted on:
        # the Kimi Code CLI has no confirmed per-call sandbox/network flag (parity
        # with the connector fail-closed below). A kimi-backed role that truly needs
        # network must arrange it out-of-band; the codex adapter is the one that
        # toggles the OS-sandbox network for an explicit grant.
        # Facet C: the Kimi Code CLI has no confirmed per-call connector-injection
        # form (and the connector-translation layer does not model "kimi"), so ANY
        # granted connector FAILS CLOSED — never silently dropped. None/[] ⇒ no-op.
        if connectors:
            raise AdapterError(
                f"kimi adapter received {len(list(connectors))} connector "
                f"grant(s) for role {role!r}, but the Kimi Code CLI has no "
                f"per-call connector-injection form. Failing closed rather than "
                f"silently dropping the grant.",
                role=role,
            )
        # VERDICT spawn (schema present): firmly require a JSON-only final message.
        if schema:
            prompt = (prompt + "\n\nOUTPUT CONTRACT (STRICT): your FINAL printed "
                      "response MUST be EXACTLY one JSON object and NOTHING else — "
                      "no prose, no markdown code fence.")
        # --- below here is NEVER exercised in offline tests ------------------- #
        argv = self._build_argv(prompt, tools)
        try:
            proc = run_with_monitor(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=self.cwd,
                stdin=subprocess.DEVNULL,
                role=role,
                harness=self.harness,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdapterError(
                f"kimi spawn failed to run {self.binary!r}: {exc}", role=role,
            ) from exc
        if proc.returncode != 0:
            raise AdapterError(
                f"kimi spawn exited {proc.returncode}: "
                f"{proc.stderr.strip()[:500]}",
                role=role,
            )
        text = self._clean_text(proc.stdout)
        if not schema:
            # ARTIFACT spawn: the final response IS the artifact (files written).
            return {"artifact": text}
        return self._parse_verdict_text(text, role)

    @staticmethod
    def _clean_text(stdout: str) -> str:
        """Strip Kimi's text-format adornments (a leading ``• `` bullet per line)
        and surrounding whitespace from the printed final response."""
        lines = [
            (ln[2:] if ln.lstrip().startswith("• ") else ln)
            for ln in (stdout or "").splitlines()
        ]
        return "\n".join(lines).strip()

    @staticmethod
    def _coerce_json_object(text: str):
        """Best-effort parse of a JSON object from a model message, tolerating a
        ```json fence or surrounding prose. Returns the dict, or None."""
        s = (text or "").strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1] if "\n" in s else ""
            fence = s.rfind("```")
            if fence != -1:
                s = s[:fence]
            s = s.strip()
            if s[:4].lower() == "json":
                s = s[4:].strip()
        candidates = [s]
        if "{" in s and "}" in s:
            candidates.append(s[s.find("{"): s.rfind("}") + 1])
        for cand in candidates:
            if not cand:
                continue
            try:
                parsed = json.loads(cand)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @classmethod
    def _parse_verdict_text(cls, text: str, role: str) -> dict:
        """Parse the final response into a verdict dict (tolerant of fence/prose).
        Non-object output is an ``AdapterError`` (driver → gate_hard_fail)."""
        verdict = cls._coerce_json_object(text)
        if verdict is None:
            raise AdapterError(
                f"kimi final response was not a JSON verdict: {(text or '')[:200]!r}",
                role=role,
            )
        return verdict
