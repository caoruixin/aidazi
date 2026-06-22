"""Load + validate the protected-surface policy (baseline) and optional adopter overlay,
and expose a ``ProtectedSurfaces`` matcher. Fail-closed: a missing/invalid baseline or an
invalid overlay raises ``PolicyError`` (the lane never runs with an unvalidated policy).
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

import yaml
from jsonschema import Draft202012Validator

from .errors import PolicyError
from .globmatch import NamedGlobs, first_match


def _load_yaml(path: str) -> dict:
    if not os.path.isfile(path):
        raise PolicyError(f"policy file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise PolicyError(f"policy file unparseable ({path}): {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyError(f"policy file is not a mapping: {path}")
    return data


def _validate(obj: dict, schema_path: str, label: str) -> None:
    if not os.path.isfile(schema_path):
        raise PolicyError(f"{label} schema not found: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    errs = sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: e.path)
    if errs:
        raise PolicyError(
            f"{label} failed schema validation ({schema_path}): "
            + "; ".join(e.message for e in errs[:5])
        )


class ProtectedSurfaces:
    """Compiled protected-surface matcher (baseline ∪ overlay additional_surfaces)."""

    def __init__(self, named: List[NamedGlobs], semantic: List[str]):
        self._named = named
        self.semantic = list(semantic)

    def match(self, path: str) -> Optional[str]:
        """Return the id of the first protected surface ``path`` hits, else None."""
        return first_match(path, self._named)

    @property
    def surface_ids(self) -> List[str]:
        return [n.id for n in self._named]


def load_protected(
    policy_path: str,
    baseline_schema_path: str,
    overlay_path: Optional[str] = None,
    overlay_schema_path: Optional[str] = None,
) -> ProtectedSurfaces:
    """Load baseline (required) ∪ overlay (optional, additive-only). Fail-closed."""
    base = _load_yaml(policy_path)
    _validate(base, baseline_schema_path, "protected-surface baseline")

    named: List[NamedGlobs] = []
    for s in base.get("mandatory_surfaces", []):
        named.append(NamedGlobs(s["id"], s["globs"], s.get("reason", "")))
    semantic = list(base.get("semantic_surfaces_layer_a", []))

    if overlay_path and os.path.isfile(overlay_path):
        if not overlay_schema_path:
            raise PolicyError("overlay present but no overlay schema path given")
        ov = _load_yaml(overlay_path)
        # Validated against the OVERLAY schema, which forbids `mandatory_surfaces` — so a
        # mis-authored overlay that tries to redefine/weaken the baseline is REJECTED
        # (fail-closed), never silently ignored.
        _validate(ov, overlay_schema_path, "protected-surface overlay")
        for s in ov.get("additional_surfaces", []):
            named.append(NamedGlobs(s["id"], s["globs"], s.get("reason", "")))

    return ProtectedSurfaces(named, semantic)
