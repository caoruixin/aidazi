#!/usr/bin/env python3
"""adapters.kimi — invoke the Kimi Code agentic CLI headless behind spawn().

Reference adapter for the ``kimi`` harness (a coding-agent CLI from Moonshot AI;
Kimi Code / K2.7). Like claude_code / codex it runs an AGENTIC session that reads
and WRITES files — so it can back the Dev role (an artifact spawn whose output is
code + a handoff), not just verdict roles.

CLI FORM — verified against Kimi Code 0.18.0 (``kimi --help``) and a REAL
captured stream (archive/2026-07-09-cursor-kimi-stream-captures/kimi-stream.jsonl):
    kimi --prompt=<prompt> --output-format stream-json [-m <model>]
  - ``-p/--prompt`` : run ONE prompt non-interactively and print the response.
    In ``-p`` mode the agent auto-approves its own tool use (it WRITES files),
    so NO ``--yolo``/``--auto`` flag is passed — in fact ``-p`` REFUSES to combine
    with them ("Cannot combine --prompt with --yolo/--auto").
    PROMPT TRANSPORT: the CLI documents NO stdin prompt form (0.18.0 help: only
    ``-p/--prompt``; the ``acp`` stdio subcommand is a different protocol), so —
    unlike claude_code/codex/cursor — the prompt stays on argv, in the ATTACHED
    ``--prompt=<value>`` form (dash-injection-safe). RESIDUAL EXPOSURE, accepted
    and documented: the full prompt is visible in local process listings (``ps``)
    for the spawn's lifetime. The monitor's stuck-diagnostic ``argv.txt`` now
    redacts oversize argv tokens (monitor._record_diagnostic), so the prompt is
    NOT persisted to diagnostics.
  - ``-m/--model`` : model alias (e.g. ``kimi-code/kimi-for-coding`` = "K2.7
    Code", the configured default). Omitted ⇒ config.toml default_model.
  - ``--output-format stream-json`` : NDJSON chat-style events on STDOUT
    (choices in 0.18.0: ``text`` | ``stream-json``). We use ``stream-json`` —
    NOT ``text`` — for LIVENESS: in text mode stdout is silent until the final
    response (reasoning went to stderr), so the shared monitor's ~180s
    silence-kill (adapters/monitor.py) false-kills any long kimi turn. In
    stream-json mode ALL events arrive on stdout (captured stderr is EMPTY),
    keeping output-liveness fresh AND feeding ``KimiStreamProbe`` (the
    active-work lease covering long silent tool/reasoning windows).
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


class KimiStreamProbe:
    """Active-work lease derived from ``kimi --output-format stream-json``
    NDJSON events.

    Kimi Code 0.18.0 emits OpenAI-chat-style events (VERIFIED against a real
    captured stream — archive/2026-07-09-cursor-kimi-stream-captures/):
    ``{"role":"assistant","tool_calls":[{"id":...,"function":{...}}]}`` →
    ``{"role":"tool","tool_call_id":...,"content":...}`` (paired by id) →
    ``{"role":"assistant","content":"..."}`` (the final text) → a trailing
    ``{"role":"meta","type":"session.resume_hint",...}``. There is NO explicit
    session-start event, so the SESSION lease opens on the FIRST well-formed
    known-role event (a process that emits nothing or garbage NEVER opens a
    lease and is still silence-killed — fail-closed) and clears on the terminal
    ``session.resume_hint`` meta. That geometry matches codex: one ``kimi -p``
    process IS one turn, so the session lease legitimately covers the process
    lifetime, and a genuinely hung process is still bounded by the per-role
    hard ``timeout_seconds`` (which the probe never suppresses). Item leases
    open per ``tool_calls[].id`` and close on the matching ``tool_call_id`` —
    kept alongside the session lease as version robustness (if a future CLI
    drops the meta trailer, tool windows are still covered precisely).

    Discipline (mirrors claude_code/codex/cursor probes): liveness is NEVER
    inferred from a child PID; malformed / non-dict / unknown events never open
    or extend a lease; a FRESH probe is built per monitor attempt.
    """

    _SESSION = "\x00session"
    _KNOWN_ROLES = ("assistant", "tool", "user", "system", "meta")

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
        role = obj.get("role")
        if not isinstance(role, str) or role not in self._KNOWN_ROLES:
            return
        if role == "meta":
            # Terminal trailer (observed: type == "session.resume_hint").
            # ANY session.* meta clears all leases — failing toward LESS
            # silence-kill suppression on unknown meta variants, never more.
            mtype = obj.get("type")
            if isinstance(mtype, str) and mtype.startswith("session."):
                self._open.clear()
            return
        # First well-formed known-role event opens the session sentinel.
        self._open.add(self._SESSION)
        if role == "assistant":
            calls = obj.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    if isinstance(call, dict):
                        cid = call.get("id")
                        if isinstance(cid, str) and cid:
                            self._open.add(cid)
        elif role == "tool":
            cid = obj.get("tool_call_id")
            if isinstance(cid, str) and cid:
                self._open.discard(cid)

    def active(self) -> bool:
        return bool(self._open)


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
        # `kimi --output-format stream-json` runs one agentic prompt
        # non-interactively (writing files as needed) and prints NDJSON events to
        # stdout (see KimiStreamProbe: the stream keeps output-liveness fresh and
        # carries the tool-lease events; the former `text` mode was stdout-silent
        # until the end and got false-killed by the monitor on any long turn).
        # The prompt is passed via the ATTACHED long-option form
        # ``--prompt=<value>``, NOT ``-p <value>`` as a separate token: an
        # attached value is parsed literally even when it starts with ``--``, so
        # a prompt/body line leading with a dash can't be mis-parsed as a CLI
        # option (parity with the stdin-based claude_code/codex root-cause fix;
        # the 0.18.0 CLI has NO stdin prompt form — see the module docstring for
        # the accepted residual ps-visibility exposure). No per-call
        # allowed-tools flag, so tool-gating for this harness lives in the
        # prompt, not argv.
        argv = [self.binary, f"--prompt={prompt}", "--output-format", "stream-json"]
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
                # kimi is silent while the remote model reasons / a tool runs;
                # the stream-derived lease suppresses the monitor's ~180s
                # silence-kill so a long Dev/verdict spawn is not false-killed
                # (hard timeout_seconds still bounds a truly hung process).
                # Same fix shape as codex (A3) / cursor.
                liveness_probe_factory=KimiStreamProbe,
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
        text = self._final_response_from_stream(proc.stdout)
        if not schema:
            # ARTIFACT spawn: the final response IS the artifact (files written).
            return {"artifact": text}
        return self._parse_verdict_text(text, role)

    @classmethod
    def _final_response_from_stream(cls, stdout: str) -> str:
        """Extract the model's final response from ``--output-format
        stream-json`` NDJSON output (grammar verified against a real captured
        stream — see KimiStreamProbe).

        The final response is the LAST ``{"role":"assistant","content":...}``
        event with non-empty text (tool-call events carry no content; the
        trailing ``meta`` event is not a response). ``content`` is tolerated as
        a plain string (observed) or a list of ``{"text": ...}`` blocks
        (defensive, OpenAI-chat shape). If NO assistant text is found — e.g. a
        CLI-build skew back to ``text``-mode output — the raw stdout goes
        through the legacy ``_clean_text`` path, so the message is never
        silently dropped; empty output stays empty and the caller's verdict
        parser raises on it.
        """
        final: Optional[str] = None
        for raw in (stdout or "").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or obj.get("role") != "assistant":
                continue
            content = obj.get("content")
            text = None
            if isinstance(content, str) and content.strip():
                text = content
            elif isinstance(content, list):
                parts = [b["text"] for b in content
                         if isinstance(b, dict) and isinstance(b.get("text"), str)
                         and b["text"].strip()]
                if parts:
                    text = "\n".join(parts)
            if text is not None:
                final = text
        if final is not None:
            return final.strip()
        return cls._clean_text(stdout)

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
