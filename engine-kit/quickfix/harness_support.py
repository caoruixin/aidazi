"""Tiered harness-support registry (fail-closed).

A harness runs the lane only if the registry marks it ``supported``. Anything else —
``unsupported``, unknown harness, or a missing/unparseable registry — fails closed.
"""
from __future__ import annotations

import os
from typing import Union

import yaml

from .errors import HarnessUnsupportedError, PolicyError

Registry = Union[str, dict]


def load_registry(registry: Registry) -> dict:
    if isinstance(registry, dict):
        return registry
    if not os.path.isfile(registry):
        raise PolicyError(f"harness-support registry not found: {registry}")
    try:
        with open(registry, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise PolicyError(f"harness-support registry unparseable ({registry}): {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("harnesses"), dict):
        raise PolicyError(f"harness-support registry malformed: {registry}")
    return data


def is_supported(harness: str, registry: Registry) -> bool:
    data = load_registry(registry)
    entry = data.get("harnesses", {}).get(harness)
    return isinstance(entry, dict) and entry.get("status") == "supported"


def assert_supported(harness: str, registry: Registry) -> None:
    if not is_supported(harness, registry):
        raise HarnessUnsupportedError(
            f"harness {harness!r} is not 'supported' in the Quick-Fix registry; "
            f"the launcher fails closed (no adapter / no cold-start evidence yet). "
            f"Use Full framework, or wait for a supported harness."
        )
