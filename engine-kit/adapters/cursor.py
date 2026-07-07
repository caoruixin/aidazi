#!/usr/bin/env python3
"""adapters.cursor — invoke the Cursor Agent CLI headless behind a uniform spawn().

Adapter for the ``cursor`` harness (ADR-0001 #3; plan §4.1 facet A). It runs the
Cursor Agent CLI (``cursor-agent``) non-interactively via subprocess
(``cursor-agent -p --output-format json --force [--model M] <prompt>``), then
extracts the role's JSON verdict from the model's final message. The DRIVER
validates that verdict against the role's schema; this adapter never lowers the
bar. A coding-agent harness (it can edit files), so it is a valid Dev backing.

PROVIDER. Cursor is built by Anysphere and is NOT provider-locked the way codex
(openai) or claude_code (anthropic) are — a Cursor account can drive Anthropic,
OpenAI, and other models behind the Cursor backend. ``provider`` therefore
defaults to ``anysphere`` (the harness vendor) and is NOT pinned in
_NATIVE_HARNESS_PROVIDER, so the charter validator does not enforce a single
provider for it.

REAL SUBPROCESS IS GATED. ``spawn`` only shells out when ``allow_subprocess=True``
was passed at construction (or env ``AIDAZI_ALLOW_REAL_ADAPTER=1``). Otherwise it
raises ``AdapterError`` immediately. This mirrors codex.py / claude_code.py: the
code is IMPLEMENTED and reviewable, but the offline test suite + the demo use the
mock adapter and never touch this subprocess path. Like the other CLI adapters it
runs under the sidecar ``run_with_monitor`` (adapters/monitor.py) so a stuck
spawn is detected, diagnosed, and given one restart.

AUTH. ``cursor-agent`` authenticates separately from the Cursor IDE: run
``cursor-agent login`` once (browser OAuth), or set ``CURSOR_API_KEY``. A
session spawned before auth completes fails AT exec (non-zero return / stderr),
which surfaces as an ``AdapterError`` (driver → gate_hard_fail), never a
permissive default.

EXACT CLI FORM — confirmed against ``cursor-agent --help`` (build 2026.06.24):
    cursor-agent -p --output-format json [--force] [--model M] [--trust] <prompt>
  - ``-p/--print`` : non-interactive / scripting mode. Has access to all tools
    incl. write + shell. REQUIRED for headless use.
  - ``--output-format json`` : machine-parseable single-JSON envelope (only works
    with ``--print``). ``text`` (default) / ``stream-json`` are the alternatives;
    we use ``json`` so the result is one parseable object. The verdict-emitting
    role prompt instructs the model to make its final message ONLY a JSON object,
    so the envelope's result field IS the verdict.
  - ``-f/--force`` : force-allow tool calls unless explicitly denied — the
    headless analogue of codex's ``--sandbox workspace-write`` / claude's
    ``acceptEdits`` (a ``-p`` session cannot answer an interactive approval
    prompt, so a WRITE role must force-allow or every edit is denied and the
    session spins until timeout). Mapped DETERMINISTICALLY from the role sandbox:
    ``workspace_write`` → ``--force`` (auto-allow edits); ``read_only`` → NO
    ``--force`` + ``--mode ask`` (read-only Q&A — writes denied). Any other
    sandbox value FAILS CLOSED. The ``--yolo`` alias (run-everything) is
    intentionally NOT reachable from a normal sandbox value.
  - ``--model M`` : optional explicit model (e.g. ``sonnet-4-thinking``); omitted
    ⇒ the account default. ``cursor-agent`` is the harness; the model is the
    account's choice, so model is informational for routing here.
  - ``--trust`` : trust the current workspace without prompting (only with
    ``--print``); set for a write role so a fresh workspace does not block on a
    trust prompt.
  The PROMPT IS PASSED ON STDIN (``input=``), NOT as a positional argv token:
  ``cursor-agent -p`` reads the prompt from stdin when no positional is given, so
  a prompt whose first line starts with ``--`` can never be mis-parsed as a CLI
  option (parity with codex / claude_code — the root-cause fix for dash-injection).

NORMATIVE SOURCE: docs/adr/ADR-0001-engine-substrate.md; process/delivery-loop.md
§4.2.7. Spec wins on any conflict; fix this file.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Optional, Sequence

from .base import Adapter, AdapterError
from .monitor import run_with_monitor

_ALLOW_ENV = "AIDAZI_ALLOW_REAL_ADAPTER"


class CursorAdapter(Adapter):
    """Adapter for the Cursor Agent CLI (``cursor-agent``) in headless print mode."""

    harness = "cursor"

    def __init__(
        self,
        *,
        provider: str = "anysphere",
        model: str = "",
        binary: str = "cursor-agent",
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

    #: Deterministic sandbox → cursor-agent flags. workspace_write force-allows
    #: tool calls (so a headless Dev can actually write); read_only runs in
    #: ``--mode ask`` (read-only Q&A, no edits) with NO force. Anything else
    #: fails closed. The dangerous ``--yolo`` is unreachable from a sandbox value.
    _SANDBOX_FLAGS = {
        "workspace_write": ["--force", "--trust"],
        "read_only": ["--mode", "ask"],
    }

    def _sandbox_flags(self, sandbox: str, role: str) -> list[str]:
        """Map an aidazi role ``sandbox`` to the cursor-agent flag set.

        Deterministic + FAIL CLOSED: an unsupported sandbox value raises
        ``AdapterError`` rather than guessing flags (a wrong guess could grant
        unintended write access). ``--yolo`` (run-everything) is NOT reachable
        from any normal sandbox value."""
        try:
            return list(self._SANDBOX_FLAGS[sandbox])
        except KeyError:
            raise AdapterError(
                f"cursor adapter: unsupported sandbox {sandbox!r} for role "
                f"{role!r}; supported: {sorted(self._SANDBOX_FLAGS)}. Failing "
                f"closed rather than guessing a cursor-agent flag set.",
                role=role,
            ) from None

    def _build_argv(self, *, sandbox_flags: Sequence[str]) -> list[str]:
        # `cursor-agent -p --output-format json` runs non-interactively and prints
        # a single JSON envelope. The PROMPT IS PASSED ON STDIN (``input=``), NOT
        # as an argv token (no dash-injection — parity with codex/claude_code).
        # cursor-agent exposes no per-call allowed-tools flag, so tool-gating for
        # this harness lives in the prompt + sandbox, not argv.
        argv = [self.binary, "-p", "--output-format", "json"]
        if self.model:
            argv += ["--model", self.model]
        argv += list(sandbox_flags)
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
                f"cursor adapter is gated off (set allow_subprocess=True or "
                f"{_ALLOW_ENV}=1 to run the real harness); role={role!r}",
                role=role,
            )
        # network_access is accepted for a uniform spawn boundary but the cursor
        # adapter passes NO OS-sandbox network toggle: cursor-agent governs network
        # via its own tool-permission model + the host OS, not a CLI sandbox flag
        # like codex's. The codex adapter is the one that un-blocks the OS-sandbox
        # network for an explicit grant; here the param is recorded/audited by the
        # driver but does not change the argv.
        # FAIL CLOSED on an unsupported sandbox BEFORE any I/O — a verdict-/code-
        # producing session must run under a known flag set.
        sandbox_flags = self._sandbox_flags(sandbox, role)
        # Facet C: translate any granted connectors → cursor config. DEFAULT-DENY →
        # empty for None/[]. cursor-agent manages MCP servers via `cursor-agent mcp`
        # / project config, with NO confirmed per-call connector-injection flag, so
        # rather than SILENTLY DROP a real grant we FAIL CLOSED here (parity with
        # codex). No connectors ⇒ this is a no-op and the spawn path is
        # byte-identical to before.
        cfg = self.translate_connectors(connectors, sandbox=sandbox)
        if cfg.get("tools"):
            raise AdapterError(
                f"cursor adapter received {len(cfg['tools'])} connector tool "
                f"grant(s) for role {role!r}, but cursor-agent has no confirmed "
                f"per-call connector-injection form (MCP lives in cursor config / "
                f"`cursor-agent mcp`). Failing closed rather than silently "
                f"dropping the grant.",
                role=role,
            )
        # VERDICT spawn (schema present): firmly instruct cursor-agent to make its
        # FINAL message ONLY a JSON object, so the envelope result IS the verdict
        # (removes verdict-shape variance — parity with codex).
        if schema:
            prompt = (prompt + "\n\nOUTPUT CONTRACT (STRICT): your FINAL message "
                      "MUST be EXACTLY one JSON object and NOTHING else — no prose "
                      "before or after it, and no markdown code fence. Put any "
                      "analysis in earlier messages; the final message is only the "
                      "JSON verdict.")
        # --- below here is NEVER exercised in offline tests ------------------- #
        argv = self._build_argv(sandbox_flags=sandbox_flags)
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
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdapterError(
                f"cursor spawn failed to run {self.binary!r}: {exc}",
                role=role,
            ) from exc
        if proc.returncode != 0:
            raise AdapterError(
                f"cursor spawn exited {proc.returncode}: "
                f"{proc.stderr.strip()[:500]}",
                role=role,
            )
        # The model's final message text from the `--output-format json` envelope.
        result_text = self._envelope_result_text(proc.stdout, role)
        # ARTIFACT spawn (no schema — e.g. Dev / Research on the cursor harness):
        # the final message IS the artifact (code + handoff prose), NOT a JSON
        # verdict, so return it RAW (parity with claude_code / codex / kimi). The
        # driver consumes the side-effect (files written), not this return value.
        if not schema:
            return {"artifact": result_text}
        # VERDICT spawn — FAIL CLOSED: parse the final message as the JSON verdict,
        # tolerating a ```json fence / surrounding prose. Any non-object shape is
        # an AdapterError (driver → gate_hard_fail), never a permissive default.
        verdict = self._coerce_json_object(result_text)
        if verdict is None:
            raise AdapterError(
                f"cursor final agent message was not a JSON verdict: "
                f"{(result_text or '')[:200]!r}",
                role=role,
            )
        return verdict

    @staticmethod
    def _envelope_result_text(stdout: str, role: str) -> str:
        """Extract the model's final message text from the cursor-agent
        ``--output-format json`` output.

        cursor-agent prints a single JSON value in ``--print --output-format json``
        mode. The exact envelope key has varied across CLI builds, so this is
        TOLERANT: it walks a small set of known result-bearing keys, and falls
        back to the raw stdout if the envelope is a bare string or an unrecognized
        object shape (so a CLI-version skew never silently drops the message). A
        non-JSON stdout that still contains text is returned verbatim (the verdict
        parser then tries to coerce a JSON object out of it); only truly empty
        output raises.
        """
        s = (stdout or "").strip()
        if not s:
            raise AdapterError("cursor output was empty", role=role)
        try:
            envelope = json.loads(s)
        except json.JSONDecodeError:
            # Not a JSON envelope — return the raw text; the verdict path will try
            # to coerce a JSON object, the artifact path keeps it as the artifact.
            return s
        if isinstance(envelope, str):
            return envelope
        if isinstance(envelope, dict):
            # Known/observed result-bearing keys, in priority order. ``result`` is
            # the claude-parity key; the others cover cursor build variants.
            for key in ("result", "text", "message", "content", "response", "output"):
                val = envelope.get(key)
                if isinstance(val, str) and val.strip():
                    return val
                # Some shapes nest the text one level down, e.g.
                # {"message": {"content": "..."}} or {"result": {"text": "..."}}.
                if isinstance(val, dict):
                    for inner in ("text", "message", "content"):
                        iv = val.get(inner)
                        if isinstance(iv, str) and iv.strip():
                            return iv
            # Unrecognized object shape: hand the whole envelope back as text so
            # the verdict coercer can still find an embedded JSON object, rather
            # than dropping it.
            return s
        # A JSON number/bool/null envelope — return its text form for coercion.
        return s

    @staticmethod
    def _coerce_json_object(text: str):
        """Best-effort parse of a JSON object from a model message, tolerating a
        ```json code fence or surrounding prose (try whole, then outermost
        ``{ ... }``). Returns the dict, or None if none is found. Parity with
        CodexAdapter._coerce_json_object."""
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
