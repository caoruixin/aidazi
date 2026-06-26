#!/usr/bin/env python3
"""role_execution_defaults — shipped Facet-A bindings for the 5 LLM roles.

Loads ``data/role-execution-defaults.yaml`` and can verify that another YAML
document's ``tooling.<role>`` blocks match (used to keep ``templates/mission-charter.yaml``
in sync). Deterministic: no network, no LLM.
"""

from __future__ import annotations

import os
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PATH = os.path.join(_THIS_DIR, "data", "role-execution-defaults.yaml")
_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(_THIS_DIR)),
    "templates",
    "mission-charter.yaml",
)

# Keys compared when verifying the mission-charter template against shipped defaults.
_COMPARE_KEYS = (
    "agent_kind",
    "harness",
    "provider",
    "model",
    "capability_ref",
    "sandbox",
    "reasoning_effort",
    "network_access",
    "mode",
)


def _load_yaml(path: str) -> dict[str, Any]:
    if yaml is None:  # pragma: no cover
        raise RuntimeError("PyYAML is required")
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    return data


def load_role_execution_defaults(
    path: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """Return ``{role: {field: value, ...}}`` from the shipped defaults file."""
    data = _load_yaml(path or _DEFAULT_PATH)
    defaults = data.get("role_execution_defaults")
    if not isinstance(defaults, dict):
        raise ValueError("role_execution_defaults: expected a mapping")
    out: dict[str, dict[str, Any]] = {}
    for role, block in defaults.items():
        if not isinstance(block, dict):
            raise ValueError(f"role_execution_defaults.{role}: expected a mapping")
        out[str(role)] = dict(block)
    return out


def verify_tooling_matches_defaults(
    tooling: dict[str, Any],
    *,
    defaults: Optional[dict[str, dict[str, Any]]] = None,
) -> list[str]:
    """Return human-readable mismatch lines; empty list ⇒ all compared keys match."""
    defaults = defaults if defaults is not None else load_role_execution_defaults()
    errors: list[str] = []
    for role, expected in defaults.items():
        actual = tooling.get(role)
        if not isinstance(actual, dict):
            errors.append(f"tooling.{role}: missing or not a mapping")
            continue
        for key in _COMPARE_KEYS:
            if key not in expected:
                continue
            exp = expected[key]
            got = actual.get(key)
            if got != exp:
                errors.append(
                    f"tooling.{role}.{key}: expected {exp!r}, got {got!r}"
                )
    return errors


def verify_mission_charter_template(
    template_path: Optional[str] = None,
    defaults_path: Optional[str] = None,
) -> list[str]:
    """Verify ``templates/mission-charter.yaml`` tooling matches shipped defaults."""
    tpl = _load_yaml(template_path or _TEMPLATE_PATH)
    tooling = tpl.get("tooling")
    if not isinstance(tooling, dict):
        return ["mission charter template: tooling block missing or not a mapping"]
    defaults = load_role_execution_defaults(defaults_path)
    return verify_tooling_matches_defaults(tooling, defaults=defaults)
