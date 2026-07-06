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

#: Track 1 §2.3/1-c — the CLOSED controlled vocabulary for task-affinity signals. This is the
#: single source of truth: a skill's catalog ``signals`` tags AND a sub-sprint's signed
#: ``task_signals`` MUST each be a subset of this set. The three schemas (skill-catalog,
#: deliver-plan-verdict, sprint_stanza) carry it as an ``enum`` so an UNKNOWN signal FAILS
#: validation (a Deliver plan with an out-of-vocab task_signal is schema-invalid → gate_hard_fail;
#: a catalog skill tagged with one is catalog-invalid). A drift-guard test asserts the schema enums
#: equal this tuple. Extend deliberately (with a new skill that carries the tag) — never silently.
#: Sorted for determinism.
TASK_SIGNAL_VOCAB = ("a11y", "design", "frontend", "interaction", "performance", "ui")
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
    #: Track 1 §2.2 — optional bindings that did NOT resolve (skip-if-absent), each
    #: ``{"id", "reason", "optional": True, "source"?}``. Additive + observation-only:
    #: NOT part of ``skill_set_hash`` (the resolved identity hashes ``skills`` only), so
    #: a skip never perturbs the acceptance authority fingerprint. The driver surfaces
    #: these in the ``effective_role_config`` audit event + a non-silent prompt footer.
    skipped_skills: tuple[dict[str, Any], ...] = ()
    #: Track 1 §2.3 — the skill ids contributed by task-signal selection
    #: (``select_skills_for_task``), in selection order. Empty unless the role is
    #: Dev/Deliver/Research/Reviewer AND the sub-sprint carries ``task_signals`` that
    #: match a catalog ``signals`` tag. Observation/audit only — not hashed.
    selected_skills: tuple[str, ...] = ()
    #: Track 1 1-c — signed ``task_signals`` for which NO catalog skill carries the tag, i.e. a
    #: valid signal that matched NOTHING. Surfaced so a no-match is VISIBLE on the audit surface
    #: (never a silent fall-back to loading every UI skill). Observation/audit only — not hashed.
    unmatched_signals: tuple[str, ...] = ()

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
            "skipped_skills": [dict(s) for s in self.skipped_skills],
            "selected_skills": list(self.selected_skills),
            "unmatched_signals": list(self.unmatched_signals),
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


def _catalog_signal_universe(catalog: dict) -> set:
    """The set of signal tags any catalog skill (``skills``/``authored``) declares — the signals
    that CAN match a skill. Used to surface task_signals that match nothing (1-c)."""
    universe: set = set()
    for section in ("skills", "authored"):
        entries = catalog.get(section) or {}
        if not isinstance(entries, dict):
            continue
        for e in entries.values():
            sig = e.get("signals") if isinstance(e, dict) else None
            if isinstance(sig, list):
                universe |= {str(x) for x in sig}
    return universe


def select_skills_for_task(role: str, task_signals: Any, catalog: dict) -> list[str]:
    """Track 1 §2.3 — deterministic task-aware skill selection.

    Map the sub-sprint's SIGNED ``task_signals`` (authored by Deliver at decompose into
    deliver-plan-verdict ``sub_sprints[].task_signals`` → ``state.planned_subsprints``; the
    ``sprint_stanza`` field is the docs projection) to candidate skill ids via each catalog
    entry's §2.1 ``signals`` tags, intersected with the skills
    PRESENT in the catalog (the ``skills`` vendored+locked + ``authored`` sections). Returns the
    matching ids sorted by id (stable + reproducible — a build-time + audit invariant).

    Acceptance is EXCLUDED (§2.5): ``effective_skill_set_hash`` sits in the acceptance authority
    fingerprint, so per-task acceptance skills would thrash §3.6 calibration; an acceptance role
    therefore always selects nothing. Empty/absent ``task_signals`` ⇒ ``[]`` — the dormant
    default until skills carry ``signals`` tags and a sub-sprint carries ``task_signals``
    (Track 1 Phase 1-c).

    PURE + side-effect-free. On-disk resolvability and lock integrity are enforced DOWNSTREAM:
    the caller feeds these ids as OPTIONAL-extend bindings, so a catalog-declared-but-absent
    candidate drops via the §2.2 skip instead of hard-failing."""
    if canonical_role(role) == "acceptance":
        return []
    wanted = {str(s).strip() for s in (task_signals or []) if str(s).strip()}
    if not wanted:
        return []
    out: list[str] = []
    for section in ("skills", "authored"):
        entries = catalog.get(section) or {}
        if not isinstance(entries, dict):
            continue
        for sid in sorted(entries):
            entry = entries[sid]
            sig = entry.get("signals") if isinstance(entry, dict) else None
            if isinstance(sig, list) and wanted.intersection(str(x) for x in sig):
                if sid not in out:
                    out.append(sid)
    return out


def resolve_role_config(charter: dict, role: str, *,
                        task_signals: Any = (),
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

    # §2.3 task-aware selection — append matching catalog skills as OPTIONAL-extend bindings.
    # Acceptance is EXCLUDED (§2.5). DORMANT today: with empty task_signals (or no skill carrying
    # a matching `signals` tag) this adds nothing, so `bindings` — and the resolved `skills` /
    # `skill_set_hash` — are byte-identical to the pre-Track-1 result.
    selected_ids: list[str] = []
    unmatched: list[str] = []
    skipped: list[dict[str, Any]] = []
    if task_signals and canonical != "acceptance":
        already = {_binding_id(b) for b in bindings}
        # Universal-skill-mounting §2 — runtime role/harness compatibility filter for
        # SIGNAL-SELECTED candidates ONLY (defaults/charter-explicit bindings are the
        # static charter_validator's fail-closed territory). DEFENSE-IN-DEPTH ONLY: the
        # validator remains the authority; reaching a skip here indicates
        # validation-time ↔ spawn-time drift (e.g. a catalog edit mid-run), and the
        # driver surfaces it as a WARN audit event. A signal must never mount a skill
        # whose declared harness_compat / tool_requirements the role cannot carry.
        agent_kind = str(role_cfg.get("harness") or role_cfg.get("agent_kind") or "")
        raw_tools = role_cfg.get("tools")
        if isinstance(raw_tools, dict):
            allow = {str(t) for t in (raw_tools.get("allow") or [])}
        elif isinstance(raw_tools, list):
            allow = {str(t) for t in raw_tools}
        else:
            allow = set()
        for sid in select_skills_for_task(canonical, task_signals, catalog):
            if sid in already:
                continue
            cat_entry, _src = _catalog_entry(catalog, sid)
            hc = [str(x) for x in (cat_entry.get("harness_compat") or [])]
            reqs = {str(x) for x in (cat_entry.get("tool_requirements") or [])}
            if hc and agent_kind and agent_kind not in hc:
                skipped.append({
                    "id": sid, "optional": True, "kind": "incompatible",
                    "reason": (f"role harness {agent_kind!r} not in the skill's "
                               f"harness_compat {hc}")})
                continue
            if reqs and allow and not reqs <= allow:
                skipped.append({
                    "id": sid, "optional": True, "kind": "incompatible",
                    "reason": (f"tool_requirements {sorted(reqs - allow)} exceed the "
                               "role's declared tool whitelist")})
                continue
            bindings.append({"id": sid, "optional": True})
            already.add(sid)
            selected_ids.append(sid)
        # 1-c — surface signals that matched NO catalog skill (a no-match must be visible, never
        # a silent fall-back). Deterministic + order-preserving + de-duplicated.
        covered = _catalog_signal_universe(catalog)
        seen_sig: set = set()
        for raw in task_signals:
            sig = str(raw)
            if sig not in covered and sig not in seen_sig:
                seen_sig.add(sig)
                unmatched.append(sig)

    # Resolve every binding. §2.2 skip-if-absent: an OPTIONAL binding that does not resolve is
    # recorded in `skipped_skills` (audit + footer) instead of raising; a REQUIRED binding that
    # fails still hard-fails (current-adopter misconfig is never masked). `skipped` already
    # carries any §2.3 compatibility skips from the selection stage above.
    resolved: list[EffectiveSkill] = []
    for entry in bindings:
        optional = isinstance(entry, dict) and bool(entry.get("optional"))
        try:
            resolved.append(_resolve_skill(
                entry, catalog=catalog, framework_root=framework_root,
                adopter_root=adopter_root))
        except EffectiveConfigError as exc:
            if not optional:
                raise
            try:
                sid = _binding_id(entry)
            except EffectiveConfigError:
                sid = None
            skipped.append({"id": sid, "reason": str(exc), "optional": True})
    skills = tuple(resolved)

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
        skipped_skills=tuple(skipped),
        selected_skills=tuple(selected_ids),
        unmatched_signals=tuple(unmatched),
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


def skill_skip_footer(config: EffectiveRoleConfig) -> str:
    """Track 1 §2.2/1-c — a NON-SILENT footer naming the OPTIONAL skills that did not resolve
    (skip-if-absent) AND any task_signals that matched no skill. Returns ``""`` when there is
    nothing to report, so the dispatched prompt is BYTE-IDENTICAL to the pre-Track-1 prompt for
    the common case (no optional bindings / no task selection / all signals matched). Mirrors the
    ``effective_role_config`` audit event so a skip or a no-match is visible both on the Audit
    Spine and in the agent's own context — never a silent fall-back."""
    if not config.skipped_skills and not config.unmatched_signals:
        return ""
    parts = ["\n\n## Skipped / unmatched skills (not mounted)\n"]
    if config.skipped_skills:
        parts.append(
            "These OPTIONAL skill bindings did not resolve (skip-if-absent) or were "
            "incompatible with this role's declared harness/whitelist (defense-in-depth) "
            "and were SKIPPED; proceed without them — they are not required for this "
            "role's work.\n")
        parts.append("\n".join(
            f"- `{s.get('id')}`: skipped ({'incompatible' if s.get('kind') == 'incompatible' else 'optional, unresolved'}) — {s.get('reason')}"
            for s in config.skipped_skills) + "\n")
    if config.unmatched_signals:
        parts.append(
            "These task_signals matched NO registered skill (no skill is mounted for them; this is "
            "recorded, not a fall-back to loading all skills): "
            f"{', '.join('`' + s + '`' for s in config.unmatched_signals)}.\n")
    return "".join(parts)

