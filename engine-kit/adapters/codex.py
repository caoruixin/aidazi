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
  - ``-c sandbox_workspace_write.network_access=true`` (config override) RE-ENABLES
    network inside the workspace-write sandbox, which codex DISABLES by default.
    Emitted ONLY for an EXPLICIT, audited charter grant
    (``tooling.<role>.network_access: true``) on a workspace-write role — the
    opt-in escape hatch for a Dev that must ``pip``/``npm`` install. OFF by default
    (the framework invariant is Dev = no network; process/delivery-loop.md §4.2.7).
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

    #: Accepted sandbox values → codex-native ``--sandbox``. Both the aidazi role
    #: values and their codex-native equivalents map (so a caller may set the
    #: codex value directly via the ctor). Anything else FAILS CLOSED — the
    #: dangerous ``danger-full-access`` is intentionally NOT in this table, so it
    #: is unreachable from a routed/charter sandbox value.
    _SANDBOX_MAP = {
        "read_only": "read-only",
        "workspace_write": "workspace-write",
        "read-only": "read-only",
        "workspace-write": "workspace-write",
    }

    def _codex_sandbox(self, sandbox: Optional[str], role: str = "") -> str:
        """Map the aidazi role sandbox (``read_only`` / ``workspace_write``) to
        codex's native ``--sandbox`` value, FAILING CLOSED on any unrecognized
        value rather than passing it straight to ``codex --sandbox``.

        ``None`` ⇒ the ctor default (``self.sandbox``), which is ALSO validated —
        so ``danger-full-access`` is unreachable even when set at construction (no
        silent passthrough). A routed/charter value MUST be one of the two aidazi
        sandboxes (or their codex-native form); anything else is an ``AdapterError``."""
        value = self.sandbox if sandbox is None else sandbox
        try:
            return self._SANDBOX_MAP[value]
        except KeyError:
            raise AdapterError(
                f"codex adapter: unsupported sandbox {value!r} for role "
                f"{role!r}; supported: read_only | workspace_write. Failing closed "
                f"rather than forwarding an unvalidated value to codex --sandbox.",
                role=role,
            ) from None

    def _build_argv(
        self,
        tools: Sequence[str],
        *,
        sandbox: Optional[str] = None,
        last_message_path: Optional[str] = None,
        network_access: bool = False,
    ) -> list[str]:
        # `codex exec --json` runs non-interactively and streams the session as
        # JSONL events. The PROMPT IS PASSED ON STDIN (subprocess ``input=``), NOT
        # as a positional argv token: ``codex exec`` reads the prompt from stdin
        # when no positional is given, so a prompt whose first line starts with
        # ``--`` can never be mis-parsed as a CLI option (root-cause fix; parity
        # with claude_code). The verdict is read from the final agent message,
        # which codex writes verbatim to ``-o <last_message_path>`` (the version-
        # stable primary path); ``--json`` stdout is kept for audit + as a fallback.
        # codex exec exposes no per-call allowed-tools flag, so tool-gating for this
        # harness lives in the prompt/sandbox, not argv.
        sb = sandbox if sandbox is not None else self.sandbox
        argv = [self.binary, "exec", "--json"]
        if last_message_path:
            argv += ["-o", last_message_path]
        if self.model:
            argv += ["--model", self.model]
        if sb:
            argv += ["--sandbox", sb]
        # OPT-IN network grant (default OFF). codex's workspace-write OS-sandbox
        # DISABLES network by default — so a Dev cannot `pip`/`npm` install. An
        # EXPLICIT, audited charter grant (tooling.<role>.network_access: true) is
        # the only way to re-enable it, via codex's documented config override
        # `-c sandbox_workspace_write.network_access=true`. ONLY for workspace-write
        # (the config key is namespaced to it; read-only never gets network anyway),
        # so a grant on a read-only role is a no-op here (the validator WARNS on it).
        # FAIL CLOSED at the enforcement layer: require a LITERAL ``True`` (not just
        # a truthy value), so a direct adapter call with a non-bool (the string
        # "false", or 1) can never grant network — the adapter never relies on an
        # upstream caller to have sanitized the value (the driver also uses is-True).
        if network_access is True and sb == "workspace-write":
            argv += ["-c", "sandbox_workspace_write.network_access=true"]
        if self.cwd:
            argv += ["-C", self.cwd]
        if self.skip_git_repo_check:
            argv.append("--skip-git-repo-check")
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
        network_access: bool = False,
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
        # VERDICT spawn (schema present): codex's --output-schema needs an
        # OpenAI-STRICT schema (every property required, recursively), which our
        # optional-field verdict schemas are not — so instead we firmly instruct
        # codex to make its FINAL message ONLY a JSON object. That final message is
        # exactly what `-o` captures, removing the verdict-shape variance that
        # intermittently produced an empty/non-JSON final message.
        if schema:
            prompt = (prompt + "\n\nOUTPUT CONTRACT (STRICT): your FINAL message "
                      "MUST be EXACTLY one JSON object and NOTHING else — no prose "
                      "before or after it, and no markdown code fence. Put any "
                      "analysis in earlier messages; the final message is only the "
                      "JSON verdict.")
        # --- below here is NEVER exercised in offline tests ------------------- #
        # Ask codex to write its FINAL message to a private temp file via `-o`;
        # that file's contents are the verdict (version-stable, no event-`type`
        # guessing). The JSONL stdout is the fallback if the file comes back empty.
        with tempfile.TemporaryDirectory(prefix="aidazi-codex-") as tmpdir:
            last_message_path = os.path.join(tmpdir, "last_message.txt")
            argv = self._build_argv(
                tools,
                sandbox=self._codex_sandbox(sandbox, role),
                last_message_path=last_message_path,
                network_access=network_access,
            )
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
            # ARTIFACT spawn (no schema — e.g. Dev / Research on the codex harness):
            # the final message IS the artifact (code + handoff prose), NOT a JSON
            # verdict, so return it RAW (parity with claude_code / kimi). The driver
            # consumes the side-effect (files written), not this return value.
            if not schema:
                text = verdict_text or self._last_agent_message(proc.stdout) or ""
                return {"artifact": text}
            # VERDICT spawn — FAIL CLOSED. PRIMARY: the `-o` final-message file, used
            # ONLY when it parses to a SCHEMA-CONFORMING verdict. Otherwise FALLBACK
            # to the JSONL stream. Never accept prose, partial JSON, or an arbitrary
            # final event — a non-conforming result raises AdapterError downstream.
            primary = self._coerce_json_object(verdict_text) if verdict_text else None
            if primary is not None and self._verdict_conforms(primary, schema):
                return primary
            return self._extract_verdict(proc.stdout, role, schema)

    @staticmethod
    def _coerce_json_object(text: str):
        """Best-effort parse of a JSON object from a model message, tolerating a
        ```json code fence or surrounding prose (try whole, then outermost
        ``{ ... }``). Returns the dict, or None if none is found."""
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

    @staticmethod
    def _parse_verdict_text(text: str, role: str) -> dict:
        """Parse one text blob (the model's FINAL message) into a verdict dict.

        Used by BOTH the primary ``-o`` output-file path and the JSONL fallback.
        Tolerates a ```json fence / surrounding prose. Any shape that yields no
        JSON object is an ``AdapterError`` (driver → gate_hard_fail), never a
        permissive default.
        """
        verdict = CodexAdapter._coerce_json_object(text)
        if verdict is None:
            raise AdapterError(
                f"codex final agent message was not a JSON verdict: "
                f"{(text or '')[:200]!r}",
                role=role,
            )
        return verdict

    @staticmethod
    def _verdict_conforms(candidate: Any, schema: Optional[dict]) -> bool:
        """True iff ``candidate`` is a dict that CONFORMS to ``schema``.

        No schema ⇒ a JSON object is sufficient (the driver-less unit tests; the
        driver always passes the role schema in production). With a schema, validate
        via jsonschema when importable — FAIL CLOSED on non-conformance. If
        jsonschema is unavailable the adapter cannot deep-validate, so a dict passes
        and the DRIVER's own schema validation stays the gate (defense-in-depth,
        never weaker)."""
        if not isinstance(candidate, dict):
            return False
        if not schema:
            return True
        try:
            import jsonschema  # noqa: E402,WPS433 - optional, validated lazily
        except ImportError:
            return True
        try:
            return jsonschema.Draft202012Validator(schema).is_valid(candidate)
        except jsonschema.exceptions.SchemaError:
            return True  # a malformed role schema is the driver's problem, not ours

    @staticmethod
    def _extract_verdict(stdout: str, role: str,
                         schema: Optional[dict] = None) -> dict:
        """FALLBACK: pull the verdict from the `codex exec --json` JSONL stream when
        the ``-o`` final-message file is empty/missing or non-conforming.

        FAILS CLOSED: codex emits one JSON object per line; we collect every agent
        message and return the MOST RECENT one that BOTH parses to a JSON object AND
        CONFORMS to the role ``schema`` (jsonschema, when present). If NO agent
        message yields a schema-conforming verdict, raises ``AdapterError`` — never
        prose, partial JSON, or an arbitrary final event. ``schema`` None/empty ⇒ a
        JSON object suffices (the driver always passes the role schema in prod)."""
        texts: list[str] = []
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
                texts.append(text)

        if not texts:
            raise AdapterError(
                "codex output had no parseable agent message in the JSONL stream",
                role=role,
            )
        for text in reversed(texts):
            verdict = CodexAdapter._coerce_json_object(text)
            if verdict is not None and CodexAdapter._verdict_conforms(verdict, schema):
                return verdict
        raise AdapterError(
            f"codex produced no schema-conforming verdict in the JSONL stream "
            f"(last agent message: {texts[-1][:200]!r})",
            role=role,
        )

    @staticmethod
    def _last_agent_message(stdout: str) -> Optional[str]:
        """Return the RAW text of the LAST agent message in the ``codex exec --json``
        JSONL stream (no JSON-verdict parsing). Used by the ARTIFACT path when the
        ``-o`` output file is empty — the artifact is prose, not a verdict."""
        last: Optional[str] = None
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = _event_message_text(event)
            if text is not None:
                last = text
        return last


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
