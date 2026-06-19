#!/usr/bin/env python3
"""adapters.headless — OpenAI-compatible HTTP adapter (DeepSeek / Kimi / GPT).

Reference adapter for the ``headless`` harness — the adapter that unlocks any
OpenAI-compatible chat-completions endpoint (DeepSeek, Moonshot/Kimi, GPT, and
local servers) per ADR-0001 #3 / plan §4.1 facet A. It posts the role prompt to
``<base_url>/chat/completions`` and parses a JSON verdict from the assistant
message. The DRIVER validates that verdict against the role's schema.

CONFIG (all by NAME, never embedding a secret value):
  base_url      : e.g. "https://api.deepseek.com/v1" (charter `endpoint`, or
                  resolved from `endpoint_env` by run_loop.build_adapters).
  model         : e.g. "deepseek-v4-pro", "moonshot-v1-128k", "gpt-4o"
  api_key_env   : NAME of the env var holding the key (e.g. "DEEPSEEK_API_KEY").
                  The value is read from os.environ at call time, never stored.
                  run_loop loads a gitignored .env.local into the environment.

REAL HTTP IS GATED. ``spawn`` only makes a network call when ``allow_http=True``
(or env ``AIDAZI_ALLOW_REAL_ADAPTER=1``); otherwise it raises ``AdapterError``
immediately. The offline test suite + the demo use the mock adapter and never
exercise this network path (same discipline as skill-vendor's ``vendor``).

NORMATIVE SOURCE: docs/adr/ADR-0001-engine-substrate.md; process/delivery-loop.md
§4.2.7. Spec wins on any conflict; fix this file.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional, Sequence

from .base import Adapter, AdapterError

_ALLOW_ENV = "AIDAZI_ALLOW_REAL_ADAPTER"


class HeadlessAdapter(Adapter):
    """OpenAI-compatible chat-completions adapter (provider-agnostic)."""

    harness = "headless"

    def __init__(
        self,
        *,
        provider: str = "",
        model: str = "",
        base_url: str = "",
        api_key_env: str = "",
        allow_http: bool = False,
        timeout_seconds: int = 600,
        temperature: float = 0.0,
        **kwargs: Any,
    ):
        super().__init__(provider=provider, model=model, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.allow_http = allow_http
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature

    def _enabled(self) -> bool:
        return self.allow_http or os.environ.get(_ALLOW_ENV) == "1"

    def _build_payload(
        self,
        prompt: str,
        schema: dict,
        *,
        functions: Optional[Sequence[dict]] = None,
    ) -> dict:
        # response_format=json_object asks the endpoint for a JSON-only reply;
        # the schema is embedded in the prompt by the driver (role-card duty),
        # and re-validated by the driver after parsing. Granted connectors add an
        # OpenAI-compatible `tools` (function-calling) list; when none are granted
        # the key is omitted entirely (default-deny → identical payload to before).
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "Respond with ONLY a single JSON object that "
                               "validates against the provided verdict schema. "
                               "No prose, no code fences.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        if functions:
            payload["tools"] = list(functions)
        return payload

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
                f"headless adapter is gated off (set allow_http=True or "
                f"{_ALLOW_ENV}=1 to make the real HTTP call); role={role!r}",
                role=role,
            )
        if not self.base_url:
            raise AdapterError("headless adapter missing base_url", role=role)
        api_key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        # Facet C: translate granted connectors → an OpenAI function list. NO-OP
        # (empty) when none are passed (default-deny).
        cfg = self.translate_connectors(connectors, sandbox=sandbox)
        functions = cfg.get("tools") or None
        # --- below here is NEVER exercised in offline tests ------------------- #
        body = json.dumps(
            self._build_payload(prompt, schema, functions=functions)
        ).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 - explicit https base_url
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise AdapterError(
                f"headless spawn HTTP call failed: {exc}", role=role
            ) from exc
        return self._extract_verdict(raw, role)

    @staticmethod
    def _extract_verdict(raw: str, role: str) -> dict:
        """Parse the chat-completions envelope and the assistant message JSON."""
        try:
            envelope = json.loads(raw)
            content = envelope["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise AdapterError(
                f"headless response was not a valid chat-completions envelope: {exc}",
                role=role,
            ) from exc
        if isinstance(content, dict):
            return content
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AdapterError(
                f"headless assistant message was not a JSON verdict: {exc}",
                role=role,
            ) from exc
