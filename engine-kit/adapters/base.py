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
from typing import Any, Optional, Sequence


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

    @abc.abstractmethod
    def spawn(
        self,
        role: str,
        prompt: str,
        tools: Sequence[str],
        schema: dict,
    ) -> dict:
        """Run one role session and return a CANDIDATE verdict dict.

        The returned dict is validated by the DRIVER against ``schema``; an
        adapter must NOT pre-validate (single deterministic validation point).
        Raise ``AdapterError`` on any transport/protocol failure rather than
        returning a fabricated verdict.
        """
        raise NotImplementedError

    def describe(self) -> dict:
        """Routing summary for audit/checkpoint context (no I/O)."""
        return {
            "harness": self.harness,
            "provider": self.provider,
            "model": self.model,
        }
