#!/usr/bin/env python3
"""Resolve the effective per-role capability configuration.

The charter stores adopter overrides. ``skills/registry.yaml`` stores framework
defaults. This module is the single merge point used by the runtime, validator,
calibration fingerprint, and onboarding summaries.

No network or runtime fetch is performed. Skill content is resolved only from
the framework/adopter filesystem and is content-hashed for audit/calibration.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROLE_ALIASES = {
    "review": "code_reviewer",
    "code-reviewer": "code_reviewer",
    "code_reviewer": "code_reviewer",
}
SKILL_MODES = frozenset({"inherit", "extend", "replace", "disable"})
INTERACTION_MODES = frozenset({"deterministic", "agentic", "hybrid"})
TARGET_ENVIRONMENTS = frozenset({"local", "staging", "production"})

DEFAULT_ACCEPTANCE_FUNCTIONAL = {
    "interaction_mode": "hybrid",
    "target_environment": "local",
    "browser": {
        "allowed_actions": [
            "navigate", "click", "fill", "select", "upload", "download",
            "screenshot", "read_console", "read_network",
        ],
        "allowed_origins": [],
    },
    "environment": {},
    "identity": {},
    "data": {},
    "production": {
        "side_effect_policy": "explicit_allow",
        "allowed_side_effects": [],
        "denied_side_effects": [
            "payment", "external_notification", "public_publish",
            "irreversible_delete",
        ],
    },
}


class EffectiveConfigError(ValueError):
    """The effective role configuration cannot be resolved safely."""


@dataclass(frozen=True)
class EffectiveSkill:
    id: str
    path: str
    content_hash: str
    source: str
    tool_requirements: tuple[str, ...] = ()
    connector_requirements: tuple[str, ...] = ()
    harness_compat: tuple[str, ...] = ()
    calibration_coupled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "content_hash": self.content_hash,
            "source": self.source,
            "tool_requirements": list(self.tool_requirements),
            "connector_requirements": list(self.connector_requirements),
            "harness_compat": list(self.harness_compat),
            "calibration_coupled": self.calibration_coupled,
        }


@dataclass(frozen=True)
class EffectiveRoleConfig:
    role: str
    skill_mode: str
    skills: tuple[EffectiveSkill, ...] = ()
    acceptance_functional: dict[str, Any] = field(default_factory=dict)

    @property
    def skill_set_hash(self) -> str:
        payload = [
            {"id": s.id, "content_hash": s.content_hash, "path": s.path}
            for s in self.skills
        ]
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "skill_mode": self.skill_mode,
            "skills": [s.as_dict() for s in self.skills],
            "skill_set_hash": self.skill_set_hash,
            "acceptance_functional": self.acceptance_functional,
        }


def canonical_role(role: str) -> str:
    return ROLE_ALIASES.get(role, role)


def find_framework_root(start: Optional[str] = None) -> Optional[str]:
    cur = os.path.abspath(start or os.path.dirname(__file__))
    while True:
        if (os.path.isfile(os.path.join(cur, "skills", "registry.yaml"))
                and os.path.isdir(os.path.join(cur, "schemas"))):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load_skill_catalog(framework_root: str) -> dict:
    if yaml is None:
        raise EffectiveConfigError("PyYAML is required to load skills/registry.yaml")
    path = os.path.join(framework_root, "skills", "registry.yaml")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except OSError as exc:
        raise EffectiveConfigError(f"skill catalog is unreadable: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise EffectiveConfigError(f"skill catalog root must be an object: {path}")
    return data


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = json.loads(json.dumps(base))
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _tree_hash(path: str) -> str:
    if not os.path.isdir(path):
        raise EffectiveConfigError(f"skill directory does not exist: {path}")
    digest = hashlib.sha256()
    files: list[str] = []
    for root, dirs, names in os.walk(path):
        dirs.sort()
        for name in sorted(names):
            files.append(os.path.relpath(os.path.join(root, name), path))
    if not files:
        raise EffectiveConfigError(f"skill directory is empty: {path}")
    for rel in files:
        digest.update(rel.replace(os.sep, "/").encode("utf-8"))
        digest.update(b"\0")
        with open(os.path.join(path, rel), "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _binding_id(entry: Any) -> str:
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    if isinstance(entry, dict) and isinstance(entry.get("id"), str):
        return entry["id"].strip()
    raise EffectiveConfigError(f"invalid skill binding: {entry!r}")


def _skills_override(raw: Any) -> tuple[str, list[Any]]:
    if raw is None:
        return "inherit", []
    if isinstance(raw, list):
        # Backward-compatible explicit arrays historically meant "these skills".
        return "replace", raw
    if not isinstance(raw, dict):
        raise EffectiveConfigError("skills must be an array or {mode,items} object")
    mode = str(raw.get("mode") or "inherit")
    if mode not in SKILL_MODES:
        raise EffectiveConfigError(
            f"unknown skills mode {mode!r}; expected {sorted(SKILL_MODES)}")
    items = raw.get("items") or []
    if not isinstance(items, list):
        raise EffectiveConfigError("skills.items must be an array")
    if mode == "disable" and items:
        raise EffectiveConfigError("skills mode 'disable' cannot declare items")
    return mode, items


def _effective_binding_entries(defaults: list[Any], mode: str,
                               items: list[Any]) -> list[Any]:
    if mode == "disable":
        return []
    if mode == "replace":
        return list(items)
    if mode == "extend":
        combined = list(defaults) + list(items)
    else:
        combined = list(defaults)
    out: list[Any] = []
    seen: set[str] = set()
    for entry in combined:
        sid = _binding_id(entry)
        if sid not in seen:
            seen.add(sid)
            out.append(entry)
    return out


def _catalog_entry(catalog: dict, skill_id: str) -> tuple[dict, str]:
    for section, source in (("skills", "vendored"), ("authored", "authored")):
        entries = catalog.get(section) or {}
        if skill_id in entries:
            return entries[skill_id], source
    return {}, ""


def _resolve_skill(entry: Any, *, catalog: dict, framework_root: str,
                   adopter_root: Optional[str]) -> EffectiveSkill:
    skill_id = _binding_id(entry)
    cat, source = _catalog_entry(catalog, skill_id)
    explicit_path = entry.get("path") if isinstance(entry, dict) else None

    if explicit_path:
        root = adopter_root or framework_root
        path = explicit_path if os.path.isabs(explicit_path) else os.path.join(root, explicit_path)
        source = str(entry.get("source") or "local")
    elif source == "vendored":
        path = os.path.join(framework_root, "skills", "vendored", skill_id)
    elif source == "authored":
        path = os.path.join(framework_root, "skills", skill_id)
    elif os.sep in skill_id or skill_id.startswith("."):
        root = adopter_root or framework_root
        path = skill_id if os.path.isabs(skill_id) else os.path.join(root, skill_id)
        source = "local"
    elif adopter_root and os.path.isdir(os.path.join(adopter_root, "skills", skill_id)):
        path = os.path.join(adopter_root, "skills", skill_id)
        source = "local"
    else:
        raise EffectiveConfigError(
            f"skill {skill_id!r} is not in the catalog and has no resolvable local path")

    path = os.path.realpath(path)
    if not os.path.isfile(os.path.join(path, "SKILL.md")):
        raise EffectiveConfigError(f"skill {skill_id!r} has no SKILL.md at {path}")
    return EffectiveSkill(
        id=skill_id,
        path=path,
        content_hash=_tree_hash(path),
        source=source or "local",
        tool_requirements=tuple(str(x) for x in (cat.get("tool_requirements") or [])),
        connector_requirements=tuple(
            str(x) for x in (cat.get("connector_requirements") or [])),
        harness_compat=tuple(str(x) for x in (cat.get("harness_compat") or [])),
        calibration_coupled=bool(cat.get("calibration_coupled")),
    )


def resolve_role_config(charter: dict, role: str, *,
                        framework_root: Optional[str] = None,
                        adopter_root: Optional[str] = None,
                        catalog: Optional[dict] = None) -> EffectiveRoleConfig:
    framework_root = framework_root or find_framework_root()
    if not framework_root:
        raise EffectiveConfigError("framework root containing skills/registry.yaml not found")
    catalog = catalog or load_skill_catalog(framework_root)
    canonical = canonical_role(role)
    tooling = charter.get("tooling") or {}
    role_cfg = tooling.get(role) or tooling.get(canonical) or {}
    defaults = list((catalog.get("role_defaults") or {}).get(canonical) or [])
    mode, items = _skills_override(role_cfg.get("skills"))
    bindings = _effective_binding_entries(defaults, mode, items)
    skills = tuple(
        _resolve_skill(
            entry, catalog=catalog, framework_root=framework_root,
            adopter_root=adopter_root)
        for entry in bindings
    )

    functional: dict[str, Any] = {}
    if canonical == "acceptance":
        raw = role_cfg.get("functional") or {}
        functional = _deep_merge(DEFAULT_ACCEPTANCE_FUNCTIONAL, raw)
        interaction = functional.get("interaction_mode")
        target = functional.get("target_environment")
        if interaction not in INTERACTION_MODES:
            raise EffectiveConfigError(
                f"invalid acceptance interaction_mode {interaction!r}")
        if target not in TARGET_ENVIRONMENTS:
            raise EffectiveConfigError(
                f"invalid acceptance target_environment {target!r}")

    return EffectiveRoleConfig(
        role=canonical,
        skill_mode=mode,
        skills=skills,
        acceptance_functional=functional,
    )


def skill_prompt_block(config: EffectiveRoleConfig) -> str:
    if not config.skills:
        return ""
    rows = "\n".join(
        f"- `{skill.id}`: `{os.path.join(skill.path, 'SKILL.md')}` "
        f"(sha256:{skill.content_hash})"
        for skill in config.skills
    )
    return (
        "\n\n## Effective role skills (framework-resolved)\n"
        "Load every SKILL.md below before role work. These are effective bindings "
        "after framework defaults and charter overrides; their instructions remain "
        "inside this role's existing authority, sandbox, and tool boundaries.\n"
        f"{rows}\n"
    )

