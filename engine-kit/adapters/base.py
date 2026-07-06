#!/usr/bin/env python3
"""adapters.base — the uniform per-harness adapter interface (ADR-0001 #3).

The deterministic driver (engine-kit/orchestrator/driver.py) never talks to an
LLM directly. It delegates each role's SESSION EXECUTION (file edits, tool-use,
the inner agentic loop) to whichever coding agent backs that role, behind ONE
uniform interface:

    spawn(role, prompt, tools, schema) -> dict   # a SCHEMA-VALID verdict

This is the boundary that makes the engine harness- AND model-agnostic
(ADR-0001 §Decision #3; plan §4.1 facet A). The driver only ever consumes
schema-valid JSON verdicts, never raw model text — so the deterministic floor
is identical across models and the bar is never lowered for a weaker model.

NORMATIVE SOURCE for the interface + the verdict-only contract:
  - docs/adr/ADR-0001-engine-substrate.md (the spawn signature + verdict-only)
  - process/delivery-loop.md §4.2.7 (spawn function set + JSON verdict schemas;
    invalid verdict = gate_hard_fail, never a permissive default)
This module is an engine-kit *implementation*. If it ever disagrees with the
spec, the spec wins; fix this file.

CONTRACT for a concrete adapter's ``spawn``:
  - Returns a plain ``dict`` that the DRIVER will validate against ``schema``.
  - On a transport/protocol failure where no verdict dict can be produced
    (network error, non-JSON model text, missing process), raise
    ``AdapterError``. The driver maps that to a ``gate_hard_fail`` — it MUST
    NOT be silently turned into a permissive verdict.
  - Adapters do NOT validate against the schema themselves (the driver owns the
    single, deterministic validation point); ``schema`` is passed so an adapter
    MAY use it to shape a structured-output request to its backend.

Determinism note: ``base`` and the mock adapter are pure/deterministic and are
the only adapters exercised in offline tests. The ``claude_code`` and
``headless`` adapters gate their real subprocess / HTTP behind an explicit flag
and are NEVER run in tests (same discipline as skill-vendor's ``vendor`` path).
"""

from __future__ import annotations

import abc
import dataclasses
from typing import Any, Optional, Sequence


@dataclasses.dataclass(frozen=True)
class InvocationTelemetry:
    """Per-INVOCATION consumption telemetry (universal-skill-mounting design §3/D2).

    Constructed EXCLUSIVELY from that invocation's local capture — never adapter
    instance state — so retries, adapter reuse, concurrency, and crash-resume can
    never cross-contaminate read evidence. Fields:
      * ``terminal_attempt`` — the run_with_monitor attempt index that produced the
        terminal result (earlier stuck attempts' streams are discarded, never merged);
      * ``terminal_status`` — the invocation's terminal status ("ok" on a returned
        result; an AdapterError path returns NO envelope at all);
      * ``read_paths`` — raw file-read evidence (``Read`` tool_use targets) parsed
        from the terminal attempt's stream; ``None`` when the harness exposes no
        read events (the honest default — agent self-report is NEVER accepted);
      * ``observability`` — ``observed`` (stream parsed) | ``unobservable`` (harness
        exposes no reads) | ``parse_error`` (a captured stream failed to parse —
        never silently reported as zero reads);
      * ``raw_stream`` — the terminal attempt's raw stream text, populated ONLY
        under ``AIDAZI_KEEP_RAW_STREAM=1`` (authorized canary evidence capture).
    """
    terminal_attempt: int = 1
    terminal_status: str = "ok"
    read_paths: Optional[list] = None
    observability: str = "unobservable"
    raw_stream: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class SpawnResult:
    """The ``Adapter.spawn`` return envelope: the candidate result (verdict dict /
    artifact wrapper — validated by the DRIVER, exactly as before) plus the
    invocation-scoped telemetry. The driver binds its own ``spawn_ref`` (seq +
    input_hash) at audit-write time; adapters never know driver identifiers."""
    result: Any
    telemetry: InvocationTelemetry


class AdapterError(Exception):
    """A spawn could not produce a candidate verdict dict.

    Raised for transport/protocol failures (no process, non-JSON output,
    network error, real I/O disabled by the gating flag). The driver treats
    this as a ``gate_hard_fail`` MANDATORY_CHECKPOINT (delivery-loop §4.2.7) —
    it is never converted into a permissive default verdict.
    """

    def __init__(self, message: str, *, role: Optional[str] = None):
        self.role = role
        super().__init__(message)


class Adapter(abc.ABC):
    """Uniform per-harness adapter ABC (ADR-0001 #3).

    Each concrete adapter binds one ``harness`` (claude_code / headless / codex /
    mock) to the driver. A single adapter instance carries the role's
    ``(provider, model)`` routing so the driver can select-and-spawn uniformly.
    """

    #: stable harness id, e.g. "mock", "claude_code", "headless".
    harness: str = "abstract"

    def __init__(self, *, provider: str = "", model: str = "", **kwargs: Any):
        self.provider = provider
        self.model = model
        # Concrete adapters may stash endpoint / api-key-env-name / flags here.
        self.config: dict[str, Any] = dict(kwargs)

    def spawn(
        self,
        role: str,
        prompt: str,
        tools: Sequence[str],
        schema: dict,
        *,
        connectors: Optional[Sequence[Any]] = None,
        sandbox: str = "workspace_write",
        network_access: bool = False,
    ) -> "SpawnResult":
        """Uniform envelope boundary (universal-skill-mounting §3/D2): run this
        harness's ``_spawn_impl`` and ALWAYS return a ``SpawnResult``. An
        ``_spawn_impl`` that returns a plain result (every adapter except
        claude_code today) is normalized here with default UNOBSERVABLE
        telemetry. An out-of-tree adapter that still overrides ``spawn`` itself
        and returns a plain dict is normalized at the DRIVER boundary instead,
        with a recorded deprecation signal — never silent breakage."""
        res = self._spawn_impl(
            role, prompt, tools, schema, connectors=connectors,
            sandbox=sandbox, network_access=network_access)
        if isinstance(res, SpawnResult):
            return res
        return SpawnResult(result=res, telemetry=InvocationTelemetry())

    @abc.abstractmethod
    def _spawn_impl(
        self,
        role: str,
        prompt: str,
        tools: Sequence[str],
        schema: dict,
        *,
        connectors: Optional[Sequence[Any]] = None,
        sandbox: str = "workspace_write",
        network_access: bool = False,
    ) -> Any:
        """Run one role session and return a CANDIDATE verdict dict.

        The returned dict is validated by the DRIVER against ``schema``; an
        adapter must NOT pre-validate (single deterministic validation point).
        Raise ``AdapterError`` on any transport/protocol failure rather than
        returning a fabricated verdict.

        Facet C (Role Configuration Contract): ``connectors`` is the role's
        abstract connector grant (each entry ~ connector-binding.schema.json) and
        ``sandbox`` the role's sandbox (``workspace_write`` / ``read_only``).
        Both are keyword-only so the driver can call every adapter uniformly.
        DEFAULT-DENY: ``connectors=None`` / empty ⇒ NO grant ⇒ the spawn path is
        byte-identical to the pre-connector behaviour. Concrete adapters use
        :meth:`translate_connectors` to turn a grant into harness-native config;
        translation produces CONFIG, it does not connect (no secret values).

        ``network_access`` is the role's explicit network grant. The adapter
        method default remains ``False`` so direct legacy calls are fail-closed;
        shipped charters pass the per-role value explicitly. Only a
        sandbox-enforcing CLI adapter (codex) acts on it — it un-blocks the
        OS-sandbox network for ``workspace_write`` so a role can ``pip``/``npm``
        install or otherwise reach the network when configured. HTTP/mock
        adapters ignore it. The DRIVER audits routed grants.
        """
        raise NotImplementedError

    def translate_connectors(
        self,
        connectors: Optional[Sequence[Any]],
        *,
        sandbox: str = "workspace_write",
    ) -> dict:
        """Translate a role's abstract connector grants → THIS harness's config.

        Facet C of the Role Configuration Contract (plan §4.1; contract §3). The
        default implementation delegates to ``connectors.translate`` for this
        adapter's ``harness`` id, so every adapter gets connector translation for
        free. TRANSLATION PRODUCES CONFIG; IT DOES NOT CONNECT — no network, no
        MCP handshake, no secret values (secrets stay env-name placeholders).

        Default-deny: ``None`` / empty ⇒ an empty config (no grant). A harness
        whose id ``connectors.translate`` does not support (or if the connector
        layer is absent) yields an empty config rather than raising, so the
        spawn path stays backward-compatible when no connectors are passed.
        """
        if not connectors:
            return {}
        try:
            from connectors import translate as _translate  # type: ignore
        except Exception:  # pragma: no cover - connector layer optional
            try:
                from ..connectors import translate as _translate  # type: ignore
            except Exception:
                return {}
        try:
            return _translate(connectors, self.harness, sandbox=sandbox)
        except ValueError:
            # harness not supported by the connector layer ⇒ no native config.
            return {}

    def describe(self) -> dict:
        """Routing summary for audit/checkpoint context (no I/O)."""
        return {
            "harness": self.harness,
            "provider": self.provider,
            "model": self.model,
        }
