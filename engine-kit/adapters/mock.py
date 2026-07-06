#!/usr/bin/env python3
"""adapters.mock — deterministic mock/replay adapter (offline tests + the demo).

Returns CANNED, schema-valid verdicts keyed by ``(role, step)`` so the whole
outer loop can be exercised with zero network, zero subprocess, and fully
reproducible output. This is the ONLY adapter run in the offline test suite and
in the ``--demo`` entrypoint.

The mock does NOT validate its own output (the driver owns the single
deterministic validation point, per adapters.base). It can be configured to
return a deliberately MALFORMED verdict so a test can assert the driver maps an
invalid verdict to ``gate_hard_fail`` (delivery-loop §4.2.7) rather than
silently passing.

Keying:
  responses = { (role, step): verdict_dict_or_AdapterError, ... }
  step       = a small monotonically-increasing per-role counter the driver
               supplies via ``spawn(... , step=N)`` is NOT part of the base
               signature, so instead the mock tracks its own per-role call
               count and looks up (role, call_index). A bare (role,) key (no
               step) is a fallback used for every call of that role.

The replay table is supplied at construction; nothing here reads the clock or
the environment.
"""

from __future__ import annotations

import copy
from typing import Any, Optional, Sequence, Union

from .base import Adapter, AdapterError

# A canned response is either a verdict dict, or an AdapterError instance/class
# to be raised (to simulate a transport failure / malformed-output path).
Canned = Union[dict, AdapterError, type]


class MockAdapter(Adapter):
    """Deterministic replay adapter.

    Parameters
    ----------
    responses:
        Mapping from ``(role, call_index)`` OR ``(role,)`` to a canned response.
        ``call_index`` is 0-based per role. A ``(role,)`` key matches any call
        of that role (used after exhausting indexed entries).
    harness:
        The harness id this mock stands in for (e.g. "claude_code", "headless").
        Lets one demo wire Dev→claude_code-mock and Review→headless-mock.
    """

    harness = "mock"

    def __init__(
        self,
        responses: dict,
        *,
        harness: str = "mock",
        provider: str = "mock",
        model: str = "mock-model",
        **kwargs: Any,
    ):
        super().__init__(provider=provider, model=model, **kwargs)
        self.harness = harness
        self._responses = responses
        self._calls: dict[str, int] = {}
        #: append-only trace of every spawn (for test assertions).
        self.history: list[dict] = []

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
    ) -> dict:
        idx = self._calls.get(role, 0)
        self._calls[role] = idx + 1
        # Record connectors/sandbox/network_access so tests can assert the driver
        # threaded the role's Facet-C grant + the opt-in network grant through
        # unchanged. The mock is a pure replay and never USES them (no translation,
        # no sandbox) — it only stores what it was handed.
        self.history.append(
            {"role": role, "call_index": idx, "harness": self.harness,
             "tools": list(tools),
             "connectors": list(connectors) if connectors else [],
             "sandbox": sandbox, "network_access": network_access is True}
        )

        if (role, idx) in self._responses:
            canned = self._responses[(role, idx)]
        elif (role,) in self._responses:
            canned = self._responses[(role,)]
        else:
            raise AdapterError(
                f"mock adapter has no canned response for role={role!r} "
                f"call_index={idx}",
                role=role,
            )

        # Simulate a transport failure (no verdict producible).
        if isinstance(canned, AdapterError):
            raise canned
        if isinstance(canned, type) and issubclass(canned, AdapterError):
            raise canned(f"mock simulated transport failure for {role}", role=role)

        # A CALLABLE canned response is materialized at spawn time from (role, prompt,
        # schema). This lets a browser-E2E acceptance mock build a verdict that CITES the
        # real committed evidence (path+sha256) — which only exists once the executor has
        # run — so the driver's §3.2 evidence-ref binding has something real to bind to.
        if callable(canned):
            return copy.deepcopy(canned(role, prompt, schema))

        # Deep-copy so the driver can't mutate the replay table.
        return copy.deepcopy(canned)
