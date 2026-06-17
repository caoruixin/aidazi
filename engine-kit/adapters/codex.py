#!/usr/bin/env python3
"""adapters.codex — invoke OpenAI Codex CLI headless behind a uniform spawn().

Reference adapter for the ``codex`` harness (ADR-0001 #3; plan §4.1 facet A). It
runs the OpenAI Codex CLI non-interactively via subprocess
(``codex exec --json <prompt> ...``), then extracts the role's JSON verdict from
the model's final message in the event stream. The DRIVER validates that verdict
against the role's schema; this adapter never lowers the bar.

PROVIDER. Codex is OpenAI's coding agent, so ``provider`` defaults to ``openai``.

REAL SUBPROCESS IS GATED. ``spawn`` only shells out when ``allow_subprocess=True``
was passed at construction (or env ``AIDAZI_ALLOW_REAL_ADAPTER=1``). Otherwise it
raises ``AdapterError`` immediately. This mirrors claude_code.py / skill-vendor's
never-run ``vendor`` path: the code is IMPLEMENTED and reviewable, but the
offline test suite + the demo use the mock adapter and never touch this
subprocess path.

EXACT CLI FORM — CONFIRMED against codex-cli 0.134.0 (`codex exec --help`):
    codex exec --json -o <last_message_file> [--model M] [--sandbox read-only]
              [-C cwd] [--skip-git-repo-check] <prompt>
  - ``exec``  : the documented non-interactive subcommand.
  - ``-o/--output-last-message <FILE>`` : codex writes the model's FINAL message
    to this file. This is the PRIMARY, version-stable way to read the verdict —
    the role prompt instructs the model to emit ONLY a JSON verdict as its final
    message, so the file's contents ARE the verdict. No event-``type`` guessing.
  - ``--json``: also stream the session as JSONL events on stdout. Kept for audit
    / event capture, and as a FALLBACK verdict source if the output file is empty.
  - ``--sandbox`` takes exactly ``read-only | workspace-write |
    danger-full-access``; ``read-only`` is the gate-side default (a verdict-
    producing role should not need to write). Override via the ``sandbox`` arg.
  - ``--skip-git-repo-check`` (optional, OFF by default) lets codex run outside a
    git repo; enable via the ``skip_git_repo_check`` ctor flag.
  Codex has NO single-envelope ``--output-format json`` like claude; ``--json``
  is JSONL — which is exactly why the verdict is captured via ``-o`` rather than
  by scanning events. (``--output-schema <FILE>`` is also available to enforce
  the final-message shape natively; the DRIVER already validates against the role
  schema, so it is intentionally left unwired here.) The JSONL fallback parser
  (``_extract_verdict``) stays tolerant of the common event shapes so a
  CLI-version skew never silently drops a verdict.

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


class CodexAdapter(Adapter):
    """Adapter for the OpenAI Codex CLI in non-interactive (``exec``) mode."""

    harness = "codex"

    def __init__(
        self,
        *,
        provider: str = "openai",
        model: str = "",
        binary: str = "codex",
        sandbox: str = "read-only",
        allow_subprocess: bool = False,
        timeout_seconds: int = 600,
        cwd: Optional[str] = None,
        skip_git_repo_check: bool = False,
        **kwargs: Any,
    ):
        super().__init__(provider=provider, model=model, **kwargs)
        self.binary = binary
        self.sandbox = sandbox
        self.allow_subprocess = allow_subprocess
        self.timeout_seconds = timeout_seconds
        self.cwd = cwd
        self.skip_git_repo_check = skip_git_repo_check

    def _enabled(self) -> bool:
        return self.allow_subprocess or os.environ.get(_ALLOW_ENV) == "1"

    def _codex_sandbox(self, sandbox: Optional[str]) -> str:
        """Map the aidazi role sandbox (``read_only`` / ``workspace_write``) to
        codex's native ``--sandbox`` value (``read-only`` / ``workspace-write``).

        ``None`` ⇒ the ctor default (``self.sandbox``). A value already in
        codex-native form passes through unchanged (so a caller may set the
        codex value directly via the ctor)."""
        if sandbox is None:
            return self.sandbox
        return {
            "read_only": "read-only",
            "workspace_write": "workspace-write",
        }.get(sandbox, sandbox)

    def _build_argv(
        self,
        prompt: str,
        tools: Sequence[str],
        *,
        sandbox: Optional[str] = None,
        last_message_path: Optional[str] = None,
    ) -> list[str]:
        # `codex exec --json <prompt>` runs non-interactively and streams the
        # session as JSONL events. The verdict is read from the final agent
        # message, which codex writes verbatim to ``-o <last_message_path>`` when
        # supplied (the version-stable primary path); ``--json`` stdout is kept
        # for audit + as a fallback. The role prompt (built by the driver) already
        # embeds the verdict schema and any tool whitelist; codex exec exposes no
        # per-call allowed-tools flag, so tool-gating for this harness lives in
        # the prompt/sandbox, not argv.
        sb = sandbox if sandbox is not None else self.sandbox
        argv = [self.binary, "exec", "--json"]
        if last_message_path:
            argv += ["-o", last_message_path]
        if self.model:
            argv += ["--model", self.model]
        if sb:
            argv += ["--sandbox", sb]
        if self.cwd:
            argv += ["-C", self.cwd]
        if self.skip_git_repo_check:
            argv.append("--skip-git-repo-check")
        # The prompt is the final positional arg.
        argv.append(prompt)
        return argv

    def spawn(
        self,
        role: str,
        prompt: str,
        tools: Sequence[str],
        schema: dict,
        *,
        connectors: Optional[Sequence[Any]] = None,
        sandbox: Optional[str] = None,
    ) -> dict:
        if not self._enabled():
            raise AdapterError(
                f"codex adapter is gated off (set allow_subprocess=True or "
                f"{_ALLOW_ENV}=1 to run the real harness); role={role!r}",
                role=role,
            )
        # Facet C: translate any granted connectors → codex tool-config (parity
        # with claude_code/headless; deterministic, no I/O). DEFAULT-DENY → empty
        # for None/[]. `codex exec` has NO confirmed per-call connector-injection
        # flag (MCP servers live in codex config.toml; see the module TODO(human)
        # on the exact CLI form), so rather than SILENTLY DROP a real grant we
        # FAIL CLOSED here. No connectors ⇒ this is a no-op and the spawn path is
        # byte-identical to before.
        cfg = self.translate_connectors(connectors, sandbox=sandbox or "workspace_write")
        if cfg.get("tools"):
            raise AdapterError(
                f"codex adapter received {len(cfg['tools'])} connector tool "
                f"grant(s) for role {role!r}, but `codex exec` has no confirmed "
                f"per-call connector-injection form (MCP lives in codex "
                f"config.toml; see TODO(human)). Failing closed rather than "
                f"silently dropping the grant.",
                role=role,
            )
        # --- below here is NEVER exercised in offline tests ------------------- #
        # Ask codex to write its FINAL message to a private temp file via `-o`;
        # that file's contents are the verdict (version-stable, no event-`type`
        # guessing). The JSONL stdout is the fallback if the file comes back empty.
        with tempfile.TemporaryDirectory(prefix="aidazi-codex-") as tmpdir:
            last_message_path = os.path.join(tmpdir, "last_message.txt")
            argv = self._build_argv(
                prompt,
                tools,
                sandbox=self._codex_sandbox(sandbox),
                last_message_path=last_message_path,
            )
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
                    f"codex spawn failed to run {self.binary!r}: {exc}",
                    role=role,
                ) from exc
            if proc.returncode != 0:
                raise AdapterError(
                    f"codex spawn exited {proc.returncode}: "
                    f"{proc.stderr.strip()[:500]}",
                    role=role,
                )
            # PRIMARY: the final agent message codex wrote to the output file.
            verdict_text: Optional[str] = None
            try:
                with open(last_message_path, "r", encoding="utf-8") as fh:
                    verdict_text = fh.read().strip()
            except OSError:
                verdict_text = None
            if verdict_text:
                return self._parse_verdict_text(verdict_text, role)
            # FALLBACK: scan the JSONL event stream for the final agent message.
            return self._extract_verdict(proc.stdout, role)

    @staticmethod
    def _parse_verdict_text(text: str, role: str) -> dict:
        """Parse one text blob (the model's FINAL message) into a verdict dict.

        Used by BOTH the primary ``-o`` output-file path and the JSONL fallback.
        Any non-JSON / non-object shape is an ``AdapterError`` (the driver →
        gate_hard_fail), never a permissive default.
        """
        try:
            verdict = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"codex final agent message was not a JSON verdict: {exc}",
                role=role,
            ) from exc
        if not isinstance(verdict, dict):
            raise AdapterError(
                f"codex verdict was not a JSON object "
                f"(got {type(verdict).__name__})",
                role=role,
            )
        return verdict

    @staticmethod
    def _extract_verdict(stdout: str, role: str) -> dict:
        """FALLBACK: pull the verdict from the `codex exec --json` JSONL stream.

        Used only when the ``-o`` output file is missing/empty. Unlike claude's
        single ``--output-format json`` envelope, codex emits one JSON object PER
        LINE (a JSONL event stream). The model's FINAL message is the verdict; we
        walk the events, keep the last agent/assistant message text we see, then
        parse that text as the verdict.

        This parser stays tolerant of the common event shapes (``agent_message``
        / ``item.completed`` text / a final-message field) so a CLI-version skew
        never silently drops a verdict — the primary ``-o`` path makes the exact
        event ``type`` non-load-bearing.
        """
        last_text: Optional[str] = None
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Non-JSON noise line (e.g. a banner); skip, keep scanning.
                continue
            text = _event_message_text(event)
            if text is not None:
                last_text = text

        if last_text is None:
            raise AdapterError(
                "codex output had no parseable agent message in the JSONL stream",
                role=role,
            )
        return CodexAdapter._parse_verdict_text(last_text, role)


def _event_message_text(event: Any) -> Optional[str]:
    """Return the agent/assistant message text from a codex JSONL event, or None.

    Only the FALLBACK path uses this (the primary verdict source is the ``-o``
    output file). Tolerant of the few documented/observed event shapes so a
    CLI-version skew does not silently drop the verdict.
    """
    if not isinstance(event, dict):
        return None
    etype = event.get("type", "")
    # Shape A: a flat agent message event, e.g. {"type":"agent_message","message":"..."}.
    if etype in ("agent_message", "assistant_message", "message"):
        for key in ("message", "text", "content"):
            val = event.get(key)
            if isinstance(val, str):
                return val
    # Shape B: an item-style event, e.g.
    #   {"type":"item.completed","item":{"type":"agent_message","text":"..."}}.
    item = event.get("item")
    if isinstance(item, dict) and item.get("type") in (
        "agent_message",
        "assistant_message",
        "message",
    ):
        for key in ("text", "message", "content"):
            val = item.get(key)
            if isinstance(val, str):
                return val
    return None
