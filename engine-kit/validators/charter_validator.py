#!/usr/bin/env python3
"""charter_validator — deterministic (no-LLM) validator for a Δ-18 mission charter.

Two layers:
  A) Structural — validate the charter YAML against
     schemas/mission-charter.schema.json using ``jsonschema``.
  B) Semantic   — enforce the charter-editing / non-bypass rules that the JSON
     Schema cannot express, reading the charter YAML and reporting each
     violation with a clear message + the offending path.

NORMATIVE SOURCE for every rule below stays in the spec, NOT in this file:
  - process/delivery-loop.md §4.2.2 (charter editing rules + 4 bypass shapes)
                              §4.2.3 (the 9 MANDATORY_CHECKPOINTS)
                              §4.2.8 (anti-patterns)
  - governance/constitution.md §1.7-C, §1.7-D (non-bypass), §3.6 (calibration)
This module is an engine-kit *implementation* of those rules. If the spec and
this file ever disagree, the spec wins; fix this file.

Determinism contract: pure function over the charter file + the bundled schema.
No network, no LLM, no clock/random dependence. Same input ⇒ same report.

CLI:
    python charter_validator.py <charter.yaml>
    exit 0  ⇒ structurally valid AND no semantic ERRORS (warnings allowed)
    exit !0 ⇒ schema-load failure, structural error, or any semantic ERROR
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import yaml
except ImportError as exc:  # pragma: no cover - import guard
    sys.stderr.write(
        "charter_validator: PyYAML is required (pip install -r requirements.txt)\n"
    )
    raise

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover - import guard
    sys.stderr.write(
        "charter_validator: jsonschema is required (pip install -r requirements.txt)\n"
    )
    raise


# --------------------------------------------------------------------------- #
# Locate the normative schema. engine-kit/ is copied next to the spec tree, so
# walk up from this file to find schemas/mission-charter.schema.json.
# --------------------------------------------------------------------------- #
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_KIT_DIR = os.path.dirname(_THIS_DIR)  # engine-kit/
if _ENGINE_KIT_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_KIT_DIR)
import charter_compat  # noqa: E402  (engine-kit/charter_compat.py — shared normalizer)


def _find_schema_path() -> Optional[str]:
    """Walk parent dirs looking for schemas/mission-charter.schema.json."""
    cur = _THIS_DIR
    while True:
        candidate = os.path.join(cur, "schemas", "mission-charter.schema.json")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


SCHEMA_PATH = _find_schema_path()


# --------------------------------------------------------------------------- #
# P-0a support: locate the repo root, sibling schemas, the shipped default model
# registry, and (read-only) reuse skill_vendor's tree-hash/verify logic.
# --------------------------------------------------------------------------- #
_DATA_DIR = os.path.join(_THIS_DIR, "data")
DEFAULT_MODEL_REGISTRY_PATH = os.path.join(_DATA_DIR, "model-registry.yaml")


def _find_repo_root() -> Optional[str]:
    """Walk parents looking for the repo root (has a schemas/ dir)."""
    cur = _THIS_DIR
    while True:
        if os.path.isdir(os.path.join(cur, "schemas")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


_REPO_ROOT = _find_repo_root()


def _find_named_schema(name: str) -> Optional[str]:
    """Locate schemas/<name> at or above this file."""
    cur = _THIS_DIR
    while True:
        candidate = os.path.join(cur, "schemas", name)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _load_named_schema(name: str) -> Optional[dict]:
    path = _find_named_schema(name)
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _import_skill_vendor():
    """Import engine-kit/skill-vendor/skill_vendor.py by path (read-only reuse of
    its tree-hash + verify logic). Returns the module or None if unavailable."""
    if _REPO_ROOT is None:
        return None
    sv_path = os.path.join(_REPO_ROOT, "engine-kit", "skill-vendor", "skill_vendor.py")
    if not os.path.isfile(sv_path):
        return None
    mod_name = "aidazi_skill_vendor"
    spec = importlib.util.spec_from_file_location(mod_name, sv_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec so @dataclass (which resolves
    # sys.modules[cls.__module__] on 3.12+/3.14) can see the defining module.
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:  # pragma: no cover - defensive; skill_vendor import guard
        sys.modules.pop(mod_name, None)
        return None
    return module


def _stringify_dates(node: Any) -> Any:
    """Recursively replace datetime.date/datetime values with ISO strings.

    P-0a-2 YAML-date note: skills/registry.yaml has ``last_updated: 2026-06-15``,
    which PyYAML parses to a ``datetime.date``. The catalog schema declares that
    field ``{type: string, format: date}``; a parsed date would false-fail the
    schema. Stringify before schema-validation so it doesn't."""
    if isinstance(node, dict):
        return {k: _stringify_dates(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_stringify_dates(v) for v in node]
    if isinstance(node, (datetime.date, datetime.datetime)):
        return node.isoformat()
    return node


def _load_yaml_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_model_registry(path: Optional[str] = None) -> Optional[dict]:
    """Load the default (or an override) model-capability registry. Returns None
    if the file is absent (the gate then degrades to 'unknown model' WARNs)."""
    target = path or DEFAULT_MODEL_REGISTRY_PATH
    if not os.path.isfile(target):
        return None
    return _load_yaml_file(target)


def load_skill_catalog(path: Optional[str] = None) -> Optional[dict]:
    """Load skills/registry.yaml (the skill catalog). Returns None if absent."""
    if path:
        target = path
    elif _REPO_ROOT:
        target = os.path.join(_REPO_ROOT, "skills", "registry.yaml")
    else:
        return None
    if not os.path.isfile(target):
        return None
    return _load_yaml_file(target)


# Tier ordering for the >= structured-output / reasoning checks
# (model-capability-registry.md §1: unsupported < low < medium < high).
_TIER_ORDER: dict[str, int] = {"unsupported": 0, "low": 1, "medium": 2, "high": 3}

# Provider lock reality (role-configuration-contract.md §1): native harnesses are
# provider-locked; headless is the OpenAI-compatible adapter (any provider).
_NATIVE_HARNESS_PROVIDER: dict[str, str] = {
    "claude_code": "anthropic",
    "codex": "openai",
    "kimi": "moonshot",        # Kimi Code agentic CLI (Moonshot AI)
}
# Harnesses that drive a file-editing coding agent (Dev requires one of these).
_CODING_AGENT_HARNESSES: frozenset[str] = frozenset(
    {"claude_code", "codex", "kimi", "aider"})

# Roles whose output is a schema-valid verdict (structured-output floor applies).
_VERDICT_ROLES: frozenset[str] = frozenset({"research", "deliver", "review", "acceptance"})
# Judgment roles whose RECOMMENDED structured-output target is `high` (WARN if medium).
_JUDGMENT_ROLES: frozenset[str] = frozenset({"acceptance", "research"})


# The 9 default MANDATORY_CHECKPOINTS (process/delivery-loop.md §4.2.3). These
# fire when their condition occurs; a charter MAY add custom checkpoints but MAY
# NOT bypass any of these in any of the four shapes (omitted / emptied / disabled
# / overridden). #9 advisory_acceptance_pass_signoff (P-A) fires when Acceptance
# produces an ADVISORY pass (design §3.2/§3.3).
MANDATORY_CHECKPOINTS: tuple[str, ...] = (
    "mission_start",
    "research_proposal_selection",
    "bad_case_manual_review",
    "new_tier0_candidate",
    "forbidden_list_redline",
    "scope_deviation",
    "close_taxonomy_C_or_D",
    "gate_hard_fail",
    "advisory_acceptance_pass_signoff",
)

# Keys whose mere presence anywhere in the charter weakens a checkpoint's
# human-authority semantics (the "overridden" bypass shape, §4.2.2 / §1.7-D).
# Matched case-insensitively against any mapping key in the charter tree.
_OVERRIDE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "auto_confirm",          # e.g. auto_confirm_if_clean
    "auto_approve",          # e.g. auto_approve_below_severity
    "skip_human",
    "bypass",
    "auto_resolve",
)

# Keys that, when present on a checkpoint mapping and set falsy, are the
# "disabled" bypass shape (a checkpoint's required-ness is not a charter toggle).
_DISABLE_KEYS: tuple[str, ...] = ("enabled", "required", "active", "fire")


@dataclass
class Issue:
    """One validator finding. ``level`` is 'error' or 'warning'."""

    level: str
    rule: str          # short stable rule id (test-assertable)
    message: str
    path: str          # offending charter path, e.g. "tooling.acceptance.on_fix_required.route_options"

    def render(self) -> str:
        tag = "ERROR" if self.level == "error" else "WARN "
        loc = f" @ {self.path}" if self.path else ""
        return f"[{tag}] {self.rule}: {self.message}{loc}"


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    def add(self, issue: Issue) -> None:
        (self.errors if issue.level == "error" else self.warnings).append(issue)

    def error(self, rule: str, message: str, path: str = "") -> None:
        self.add(Issue("error", rule, message, path))

    def warn(self, rule: str, message: str, path: str = "") -> None:
        self.add(Issue("warning", rule, message, path))

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def rules_fired(self) -> set[str]:
        return {i.rule for i in (*self.errors, *self.warnings)}

    def render(self) -> str:
        lines: list[str] = []
        for issue in self.errors:
            lines.append(issue.render())
        for issue in self.warnings:
            lines.append(issue.render())
        if not lines:
            lines.append("charter_validator: OK — structurally valid, no semantic violations.")
        summary = f"\n{len(self.errors)} error(s), {len(self.warnings)} warning(s)."
        return "\n".join(lines) + summary


# --------------------------------------------------------------------------- #
# Small path-aware tree walker used by several semantic checks.
# --------------------------------------------------------------------------- #
def _iter_mappings(node: Any, path: str = ""):
    """Yield (path, mapping) for every dict in the charter tree (incl. inside lists)."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _iter_mappings(value, child_path)
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            child_path = f"{path}[{idx}]"
            yield from _iter_mappings(value, child_path)


def _is_falsy(value: Any) -> bool:
    """A checkpoint is 'disabled' if its toggle is False/0/''/None/empty-collection."""
    return value in (False, 0, "", None) or value == [] or value == {}


# --------------------------------------------------------------------------- #
# Layer A — structural validation against the JSON schema.
# --------------------------------------------------------------------------- #
def validate_structure(charter: Any, schema: dict, report: Report) -> None:
    validator = Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(charter), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        report.error("structural", err.message, path)


# --------------------------------------------------------------------------- #
# Layer B — semantic rules from the spec.
# --------------------------------------------------------------------------- #
def _check_mandatory_checkpoints(charter: dict, report: Report) -> None:
    """The 9 default MANDATORY_CHECKPOINTS must not be bypassed in any of the 4
    shapes (process/delivery-loop.md §4.2.2 / governance/constitution.md §1.7-D):
        omitted / emptied / disabled / overridden.

    The real charter shape (schemas/mission-charter.schema.json) does NOT
    enumerate the 9 defaults — they fire implicitly, and the schema's top-level
    ``additionalProperties: false`` already forbids a stray ``mandatory_checkpoints``
    key. So this check defends the *semantic* boundary the schema can't see:

      * OMITTED  — only meaningful if the charter introduces a checkpoint
        ENUMERATION section (a key whose name contains "mandatory_checkpoint" and
        is not the additive ``mandatory_checkpoints_added``). If such a section
        exists, every one of the 9 defaults must appear in it; a missing default
        is the omitted bypass. (Absence of any such section is the legitimate
        default state — the 9 fire implicitly — and is NOT a violation.)
      * EMPTIED  — that enumeration section is present but empty/null, OR a
        per-checkpoint mapping keyed by a default id is empty/null.
      * DISABLED — a mapping keyed by a default checkpoint id carries a falsy
        toggle (enabled/required/active/fire: false).
      * OVERRIDDEN — an auto-confirm / auto-approve / skip-human style key appears
        anywhere (semantic weakening = removal in disguise).
    """
    # --- OVERRIDDEN: scan the whole tree for semantic-weakening keys. ---------
    for path, mapping in _iter_mappings(charter):
        for key in mapping:
            klow = str(key).lower()
            for needle in _OVERRIDE_KEY_SUBSTRINGS:
                if needle in klow:
                    full = f"{path}.{key}" if path else str(key)
                    report.error(
                        "checkpoint_overridden",
                        f"semantic override of MANDATORY_CHECKPOINT authority via "
                        f"'{key}' (auto-confirm/auto-approve/skip-human style key); "
                        f"override = bypass per Constitution §1.7-D",
                        full,
                    )

    # --- Locate any checkpoint-enumeration section the charter introduces. ----
    # ``mandatory_checkpoints_added`` is the LEGITIMATE additive section and is
    # explicitly excluded here — adding custom checkpoints is allowed.
    enum_sections: list[tuple[str, Any]] = []
    for path, mapping in _iter_mappings(charter):
        for key, value in mapping.items():
            klow = str(key).lower()
            if "mandatory_checkpoint" in klow and klow != "mandatory_checkpoints_added":
                full = f"{path}.{key}" if path else str(key)
                enum_sections.append((full, value))

    for full, value in enum_sections:
        # EMPTIED: present but empty/null.
        if _is_falsy(value):
            report.error(
                "checkpoint_emptied",
                "MANDATORY_CHECKPOINTS section present but empty/null; "
                "emptiness is not opt-out (Constitution §1.7-D)",
                full,
            )
            continue

        # Normalise the declared checkpoint ids regardless of list/dict shape.
        if isinstance(value, list):
            declared = {str(v) for v in value if isinstance(v, (str, int))}
            # Also handle a list of {id: ...}/{name: ...} mappings.
            for item in value:
                if isinstance(item, dict):
                    for id_key in ("id", "name", "checkpoint_id"):
                        if id_key in item:
                            declared.add(str(item[id_key]))
        elif isinstance(value, dict):
            declared = {str(k) for k in value.keys()}
        else:
            declared = set()

        # OMITTED: a default missing from an explicit enumeration.
        for ckpt in MANDATORY_CHECKPOINTS:
            if ckpt not in declared:
                report.error(
                    "checkpoint_omitted",
                    f"default MANDATORY_CHECKPOINT '{ckpt}' missing from the "
                    f"charter's checkpoint enumeration; absence ≠ opt-out "
                    f"(Constitution §1.7-D). Either restore it or add custom "
                    f"checkpoints via mandatory_checkpoints_added instead",
                    full,
                )

    # --- DISABLED / EMPTIED at per-checkpoint granularity. --------------------
    # A mapping keyed by a default checkpoint id (anywhere in the tree) must not
    # be emptied or carry a falsy enable/required toggle.
    for path, mapping in _iter_mappings(charter):
        for key, value in mapping.items():
            if str(key) not in MANDATORY_CHECKPOINTS:
                continue
            full = f"{path}.{key}" if path else str(key)
            if _is_falsy(value):
                report.error(
                    "checkpoint_emptied",
                    f"default MANDATORY_CHECKPOINT '{key}' declared but empty/null; "
                    f"emptiness is not opt-out (Constitution §1.7-D)",
                    full,
                )
            elif isinstance(value, dict):
                for dkey in _DISABLE_KEYS:
                    if dkey in value and _is_falsy(value[dkey]):
                        report.error(
                            "checkpoint_disabled",
                            f"default MANDATORY_CHECKPOINT '{key}' disabled via "
                            f"'{dkey}: {value[dkey]!r}'; required-ness is not a "
                            f"charter-level toggle (Constitution §1.7-D)",
                            f"{full}.{dkey}",
                        )


def _check_acceptance_on_fix_required(charter: dict, report: Report) -> None:
    """tooling.acceptance.on_fix_required rules (delivery-loop §4.2.2; constitution §1.7-C):
      - human_confirm_required MUST be true (reject false / absent).
      - route_options MUST be a non-empty list.
    """
    acc = (charter.get("tooling") or {}).get("acceptance")
    if not isinstance(acc, dict):
        return
    ofr = acc.get("on_fix_required")
    if not isinstance(ofr, dict):
        # Structural layer already flags a missing required key; nothing to add.
        return

    base = "tooling.acceptance.on_fix_required"

    hcr = ofr.get("human_confirm_required")
    if hcr is not True:
        report.error(
            "human_confirm_required",
            f"tooling.acceptance.on_fix_required.human_confirm_required MUST be true "
            f"(got {hcr!r}); Constitution §1.7-C — Acceptance never silently "
            f"routes fix_required to Deliver",
            f"{base}.human_confirm_required",
        )

    routes = ofr.get("route_options")
    if not isinstance(routes, list) or len(routes) == 0:
        report.error(
            "route_options_nonempty",
            f"tooling.acceptance.on_fix_required.route_options MUST be a non-empty list "
            f"(got {routes!r}); MAY be narrowed but MAY NOT be empty "
            f"(delivery-loop §4.2.2)",
            f"{base}.route_options",
        )


def _check_calibration_corollary(charter: dict, report: Report) -> None:
    """Calibration corollary (delivery-loop §4.2.2; constitution §3.4 #6 / §3.6):
    changing ``tooling.acceptance.skills`` invalidates ``judge_calibration.status``.
    WARN when skills are present while status is 'calibrated' — the validator
    cannot see prior charter versions, so it flags the at-risk combination for a
    human to confirm a (re)calibration backed the current skill set.
    """
    acc = (charter.get("tooling") or {}).get("acceptance")
    if not isinstance(acc, dict):
        return
    jc = acc.get("judge_calibration")
    status = jc.get("status") if isinstance(jc, dict) else None
    skills = acc.get("skills")
    if status == "calibrated" and isinstance(skills, list) and len(skills) > 0:
        report.warn(
            "calibration_skills_corollary",
            "tooling.acceptance.skills present while judge_calibration.status is "
            "'calibrated'; any change to the skill set invalidates calibration "
            "(Constitution §3.4 invariant #6 / §3.6). Confirm the calibration run "
            "covered exactly this skill set, else re-calibrate",
            "tooling.acceptance.judge_calibration.status",
        )


def _check_adaptive_insert_bound(charter: dict, report: Report) -> None:
    """delivery-loop §4.2.2: max_inserted_subsprints bounds adaptive insertion;
    if adaptive_insert is enabled, the bound MUST be present (orchestrator must
    refuse to insert past it — an unbounded enable is meaningless / unsafe).
    """
    apr = (charter.get("autonomy") or {}).get("auto_pass_rules")
    if not isinstance(apr, dict):
        return
    ai = apr.get("adaptive_insert")
    if not isinstance(ai, dict):
        return
    if ai.get("enabled") is True and "max_inserted_subsprints" not in ai:
        report.error(
            "adaptive_insert_bound",
            "autonomy.auto_pass_rules.adaptive_insert.enabled is true but "
            "max_inserted_subsprints is absent; the bound MUST be present so the "
            "orchestrator can refuse to insert past it (delivery-loop §4.2.2)",
            "autonomy.auto_pass_rules.adaptive_insert.max_inserted_subsprints",
        )


# --------------------------------------------------------------------------- #
# Extension points for not-yet-specified P-0a facets. These currently no-op so
# future phases can plug in without touching the call site. See plan
# archive/2026-06-15-v2-loop-engine-plan.md §4.1 + §5 / §7 P-0a.
# --------------------------------------------------------------------------- #
def _load_connector_catalog(path: Optional[str] = None) -> Optional[dict]:
    """Load connectors/registry.yaml if it exists. The catalog is OPTIONAL — a
    missing catalog is NOT a failure (default-deny holds without one)."""
    if path:
        target = path
    elif _REPO_ROOT:
        target = os.path.join(_REPO_ROOT, "connectors", "registry.yaml")
    else:
        return None
    if not os.path.isfile(target):
        return None
    return _stringify_dates(_load_yaml_file(target))


def _check_connector_grants(
    charter: dict,
    report: Report,
    *,
    connector_catalog_path: Optional[str] = None,
    skill_catalog_path: Optional[str] = None,
) -> None:
    """Facet C connector grants — DEFAULT-DENY (role-configuration-contract.md §3/§5).

    A role with NO ``connectors`` block is a NO-OP (default-deny already holds).
    For each listed connector on a role that DOES declare connectors:
      - validate against schemas/connector-binding.schema.json;
      - capability class ⊆ role sandbox: a read_only role may grant only read
        scopes (write/network on a read-only role ⇒ ERROR);
      - grant ⊇ skill requirements: if a bound skill declares connector/mcp
        requirements, the role must grant them; missing ⇒ ERROR.
      - catalog cross-ref (OPTIONAL): if connectors/registry.yaml exists, also
        check ids resolve; if not, skip with a note (never blocks).
    """
    binding_schema = _load_named_schema("connector-binding.schema.json")
    validator = Draft202012Validator(binding_schema) if binding_schema else None

    catalog = _load_connector_catalog(connector_catalog_path)
    cat_connectors = (catalog or {}).get("connectors", {}) or {}

    skill_catalog = load_skill_catalog(skill_catalog_path)
    skill_catalog = _stringify_dates(skill_catalog) if skill_catalog else {}
    cat_skills = (skill_catalog.get("skills") or {}) if skill_catalog else {}
    cat_authored = (skill_catalog.get("authored") or {}) if skill_catalog else {}

    for role, cfg in _iter_roles(charter):
        base = f"tooling.{role}.connectors"
        read_only = _role_is_read_only(role, cfg)
        granted_ids: set[str] = set()
        connectors = cfg.get("connectors")
        has_connectors = isinstance(connectors, list)

        if has_connectors:
            for idx, conn in enumerate(connectors):
                cpath = f"{base}[{idx}]"
                if not isinstance(conn, dict):
                    continue
                cid = conn.get("id")
                if isinstance(cid, str):
                    granted_ids.add(cid)

                # --- schema validation ---------------------------------------
                if validator is not None:
                    for err in validator.iter_errors(conn):
                        report.error(
                            "connector_binding_invalid",
                            f"connector '{cid}' on role '{role}' does not validate "
                            f"connector-binding.schema.json: {err.message}",
                            cpath + ("." + ".".join(str(p) for p in err.absolute_path)
                                     if err.absolute_path else ""),
                        )

                # --- capability class ⊆ role sandbox -------------------------
                scopes = conn.get("scopes")
                if isinstance(scopes, list) and read_only:
                    privileged = [s for s in scopes if s in ("write", "network")]
                    if privileged:
                        report.error(
                            "connector_scope_sandbox",
                            f"read-only role '{role}' grants connector '{cid}' with "
                            f"privileged scope(s) {sorted(set(map(str, privileged)))}; "
                            f"a read_only role's connectors must be read-only "
                            f"(capability class ⊆ sandbox; "
                            f"role-configuration-contract.md §3)",
                            cpath + ".scopes",
                        )

                # --- catalog cross-ref (optional, never blocks) --------------
                if catalog is not None and isinstance(cid, str) and cid not in cat_connectors:
                    report.warn(
                        "connector_not_in_catalog",
                        f"connector '{cid}' on role '{role}' is not in "
                        f"connectors/registry.yaml; granting from outside the vetted "
                        f"catalog is an explicit trust decision "
                        f"(role-configuration-contract.md §3)",
                        cpath + ".id",
                    )

            if catalog is None:
                report.warn(
                    "connector_catalog_absent",
                    f"role '{role}' grants connectors but connectors/registry.yaml "
                    f"is absent; catalog cross-reference skipped (binding-level "
                    f"checks still applied; default-deny unaffected)",
                    base,
                )

        # --- grant ⊇ the connector requirements of the role's bound skills ----
        # Runs whether or not the role declares a connectors block: a skill that
        # needs a connector the role doesn't grant is a violation either way
        # (a role with no connectors block grants nothing — default-deny).
        skills = cfg.get("skills")
        if isinstance(skills, list):
            for entry in skills:
                if isinstance(entry, str):
                    sid = entry
                    binding_reqs = None
                elif isinstance(entry, dict) and isinstance(entry.get("id"), str):
                    sid = entry["id"]
                    binding_reqs = entry.get("connector_requirements")
                else:
                    continue
                cat_entry = cat_skills.get(sid) or cat_authored.get(sid) or {}
                reqs = binding_reqs if isinstance(binding_reqs, list) else cat_entry.get("connector_requirements")
                if not isinstance(reqs, list):
                    continue
                missing = [r for r in reqs if str(r) not in granted_ids]
                if missing:
                    report.error(
                        "connector_grant_insufficient",
                        f"role '{role}' binds skill '{sid}' which requires "
                        f"connector(s) {sorted(set(map(str, missing)))} the role does "
                        f"not grant; a role's connector grant MUST ⊇ its skills' "
                        f"connector requirements (role-configuration-contract.md §3)",
                        base,
                    )


def _iter_roles(charter: dict):
    """Yield (role_name, role_cfg_dict) for each LLM role under tooling. Skips
    'eval' (not an LLM role — orchestrator runs a cmd)."""
    tooling = charter.get("tooling")
    if not isinstance(tooling, dict):
        return
    for role, cfg in tooling.items():
        if role == "eval" or not isinstance(cfg, dict):
            continue
        yield role, cfg


def _role_tools_allow(cfg: dict) -> Optional[set[str]]:
    """Resolve a role's built-in tool whitelist regardless of shape:
      - acceptance/review legacy: tools: [Read, Grep, Glob]
      - dev/review v2 object:     tools: {allow: [...]}
    Returns the set of allowed tool names, or None if no whitelist is declared
    (None = 'not restricted here' — the caller treats a read-only role's default
    whitelist as {Read, Grep, Glob})."""
    tools = cfg.get("tools")
    if isinstance(tools, list):
        return {str(t) for t in tools}
    if isinstance(tools, dict) and isinstance(tools.get("allow"), list):
        return {str(t) for t in tools["allow"]}
    return None


def _role_is_read_only(role: str, cfg: dict) -> bool:
    """A role is read-only iff its sandbox is read_only, OR it is a role whose
    default sandbox is read_only (review/acceptance are read-only judges)."""
    sandbox = cfg.get("sandbox")
    if sandbox == "read_only":
        return True
    if sandbox == "workspace_write":
        return False
    return role in ("review", "acceptance")


def _check_network_access(charter: dict, report: Report) -> None:
    """The EXPLICIT, opt-in network grant (tooling.<role>.network_access).

    The framework invariant is Dev = NO network (process/delivery-loop.md §4.2.7;
    role-skill-model.md). Granting it is a DELIBERATE privilege escalation, so ANY
    ``network_access: true`` raises a WARNING — it is never silently green:
      - on a write role: a caution that this opens the workspace-write sandbox to
        the network (intended only for installing deps; the driver audits it);
      - on a read-only role: additionally that the grant is a NO-OP and very likely
        a mistake (codex un-blocks network only for a workspace_write sandbox).
    ``network_access`` false/absent is the default-deny no-op (no finding). The
    grant is a WARNING, never an ERROR: it is a legitimate, human-authored opt-in —
    the gate's job is to make it loud + intentional, not to forbid it."""
    for role, cfg in _iter_roles(charter):
        if cfg.get("network_access") is not True:
            continue  # default-deny: false/absent ⇒ no finding
        path = f"tooling.{role}.network_access"
        if _role_is_read_only(role, cfg):
            report.warn(
                "network_on_read_only_role",
                f"role '{role}' sets network_access: true but is read-only — the "
                f"grant is a NO-OP (the OS sandbox un-blocks network only for a "
                f"workspace_write role) and is very likely a mistake. Remove it, or "
                f"set sandbox: workspace_write if the role truly must write AND reach "
                f"the network (delivery-loop §4.2.7).",
                path)
        else:
            report.warn(
                "network_access_granted",
                f"role '{role}' sets network_access: true — this DELIBERATELY opens "
                f"the workspace-write sandbox to the network, overriding the Dev=no-"
                f"network invariant (delivery-loop §4.2.7). Intended ONLY for "
                f"installing dependencies (pip/npm); the driver records a "
                f"sandbox_network_granted escalation on the audit spine. Confirm it "
                f"is necessary — prefer pre-provisioning deps outside the sandbox.",
                path)


def _effective_harness(cfg: dict) -> Optional[str]:
    """The harness the RUNTIME will route on. MUST mirror driver.route_for_role
    EXACTLY: ``rc.get("harness") or rc.get("agent_kind") or ""`` — TRUTHY fallback,
    so an empty-string ``harness`` falls through to ``agent_kind`` just like the
    runtime (not treated as the literal ``""``). Returns None when neither yields a
    non-empty string (nothing to check). Use this wherever the routed harness must
    be validated (the capability gate)."""
    eff = cfg.get("harness") or cfg.get("agent_kind") or ""
    return eff if isinstance(eff, str) and eff else None


# NOTE: Review and Acceptance MAY share a model. Their independence is by ROLE /
# PERSPECTIVE / TIMING — Review judges engineering correctness per sub-sprint;
# Acceptance judges the gap to the CUSTOMER's stated need at milestone close
# (delivery-loop §4.2.4/§4.2.6). It is NOT model-diversity, so there is deliberately
# no "same execution binding" check here (a stricter judge-diversity policy, if ever
# wanted, belongs in a charter the adopter opts into — not the default gate).
def _check_capability_gate(charter: dict, report: Report, *, model_registry_path: Optional[str] = None) -> None:
    """Facet A capability gate (role-configuration-contract.md §4/§5).

    Fires ONLY for a role that declares the v2 execution fields
    (tooling.<role>.{harness, provider, model}). A legacy charter (agent_kind/model
    only) is untouched. For each such role:
      - harness↔provider compatibility (claude_code→anthropic, codex→openai,
        headless→OpenAI-compatible/any) — mismatch ⇒ ERROR.
      - Dev needs a file-editing coding-agent harness — headless ⇒ ERROR.
      - structured-output floor: verdict roles require the model's
        structured_output_tier ≥ medium ⇒ ERROR below; judgment roles recommend
        high ⇒ WARN if exactly medium.
      - unknown model (not in the registry) ⇒ WARN (can't verify capability).
    """
    registry = load_model_registry(model_registry_path)
    models = (registry or {}).get("models", {}) or {}

    for role, cfg in _iter_roles(charter):
        harness = cfg.get("harness")
        provider = cfg.get("provider")
        model = cfg.get("model")
        # The check is GATED on the new Facet-A fields being present (a v2 opt-in).
        # A LEGACY role (agent_kind only, no harness/provider/capability_ref) stays
        # untouched — exactly as before.
        if harness is None and provider is None and "capability_ref" not in cfg:
            continue

        base = f"tooling.{role}"

        # EFFECTIVE harness = the one the RUNTIME routes on (shared helper; truthy
        # `harness or agent_kind`, exactly like driver.route_for_role). Validate that
        # SAME harness — else an omitted/empty `harness` silently bypasses every
        # harness check (harness↔provider lock, dev coding-agent, harness_compat).
        eff_harness = _effective_harness(cfg)

        # --- harness ↔ provider compatibility ---------------------------------
        if isinstance(eff_harness, str) and isinstance(provider, str):
            locked = _NATIVE_HARNESS_PROVIDER.get(eff_harness)
            if locked is not None and provider != locked:
                report.error(
                    "harness_provider_mismatch",
                    f"role '{role}' (effective harness '{eff_harness}') is provider-"
                    f"locked to '{locked}' but provider is '{provider}' "
                    f"(role-configuration-contract.md §1)",
                    f"{base}.provider",
                )

        # --- Dev needs a coding-agent (file-editing) harness ------------------
        if role == "dev" and isinstance(eff_harness, str) and eff_harness not in _CODING_AGENT_HARNESSES:
            report.error(
                "dev_needs_coding_agent",
                f"Dev needs a coding-agent harness (claude_code/codex/kimi/aider) "
                f"that can edit files; effective harness '{eff_harness}' cannot "
                f"(role-configuration-contract.md §4)",
                f"{base}.harness",
            )

        # --- FAIL CLOSED: a Facet-A role must be FULLY specified --------------
        # The runtime routes the triple (eff_harness, provider, model) and an
        # omitted field routes "" (driver.route_for_role / run_loop.build_adapters).
        # A role that has opted into v2 (past the legacy guard) therefore MUST
        # declare all three explicitly. (The shipped registry is intentionally
        # NON-exhaustive, so a fully-declared-but-unregistered model is a WARN below,
        # not an error — but an UNDER-specified binding can never route correctly.)
        missing = []
        if eff_harness is None:
            missing.append("harness/agent_kind")
        if not (isinstance(provider, str) and provider):
            missing.append("provider")
        if not (isinstance(model, str) and model):
            missing.append("model")
        if missing:
            report.error(
                "facet_a_underspecified",
                f"role '{role}' opts into a v2 execution binding but omits "
                f"{missing}; the runtime routes each field and an omitted one becomes "
                f"an empty string. Declare harness/agent_kind, provider, AND model "
                f"explicitly (or use a capability_ref plus matching provider/model) "
                f"(role-configuration-contract.md §5)",
                base)
            continue

        # --- resolve the capability record ------------------------------------
        # Prefer capability_ref → profile id; else match provider+model against any
        # registry record. Track whether we resolved BY REF (the ref↔triple
        # consistency check below is only meaningful then — a provider+model
        # fallback matches by construction).
        record = None
        resolved_by_ref = False
        cap_ref = cfg.get("capability_ref")
        if isinstance(cap_ref, str):
            # A capability_ref names ONE profile. If it does NOT resolve, that is an
            # ERROR — do NOT silently fall back to a provider/model match (a typo'd
            # ref like 'openai-gpt5-typo' would otherwise validate against an
            # unrelated profile and keep the ref decorative).
            if cap_ref in models:
                record = models[cap_ref]
                resolved_by_ref = True
            else:
                report.error(
                    "capability_ref_unknown",
                    f"role '{role}' capability_ref '{cap_ref}' is not in the model-"
                    f"capability registry; a named profile MUST exist (no silent "
                    f"provider/model fallback) (role-configuration-contract.md §5)",
                    f"{base}.capability_ref")
                continue
        else:
            # No capability_ref: match the declared (provider, model) against the
            # registry. Both are guaranteed present (facet_a_underspecified above).
            for rec in models.values():
                if (isinstance(rec, dict) and rec.get("model") == model
                        and rec.get("provider") == provider):
                    record = rec
                    break

        if record is None:
            # cap_ref ABSENT and the (provider, model) pair is not in the registry.
            # The shipped registry is intentionally NON-exhaustive (adopter-tunable),
            # so a fully-declared but unverifiable model is a WARN, NOT an error (a
            # typo'd ref / an under-specified binding already errored above).
            report.warn(
                "model_unknown",
                f"role '{role}' (provider '{provider}', model '{model}') is not in "
                f"the model-capability registry; cannot verify capability "
                f"(role-configuration-contract.md §5)",
                f"{base}.model",
            )
            continue

        # --- capability_ref ↔ declared (provider, model) consistency ----------
        # provider/model are guaranteed present (facet_a_underspecified above). When
        # resolved BY ref they MUST EQUAL the profile — else the ref is decorative or
        # the role runs a DIFFERENT model than the gate verified. FAIL CLOSED.
        ref_loc = f"{base}.capability_ref" if resolved_by_ref else f"{base}.model"
        if resolved_by_ref:
            rprov, rmodel = record.get("provider"), record.get("model")
            if isinstance(rprov, str) and provider != rprov:
                report.error(
                    "capability_ref_provider_mismatch",
                    f"role '{role}' declares provider '{provider}' but capability_ref "
                    f"'{cap_ref}' is provider '{rprov}'; the ref must match the role's "
                    f"declared (provider, model) (role-configuration-contract.md §5)",
                    f"{base}.provider")
            if isinstance(rmodel, str) and model != rmodel:
                report.error(
                    "capability_ref_model_mismatch",
                    f"role '{role}' declares model '{model}' but capability_ref "
                    f"'{cap_ref}' is model '{rmodel}'; the ref must match the role's "
                    f"declared (provider, model) (role-configuration-contract.md §5)",
                    f"{base}.model")

        # --- harness must be one the profile can drive (harness_compat) -------
        # FAIL CLOSED: a resolved profile with no usable harness_compat list cannot
        # be verified for this harness, so REJECT rather than silently skip (a custom
        # registry profile must not be able to disable the compatibility gate).
        compat = record.get("harness_compat")
        if isinstance(eff_harness, str):
            if not isinstance(compat, list):
                report.error(
                    "harness_compat_missing",
                    f"role '{role}' resolves to capability profile for model "
                    f"'{record.get('model')}' with no harness_compat list; cannot "
                    f"verify the harness can drive it (fail closed) "
                    f"(role-configuration-contract.md §5)",
                    f"{base}.harness")
            elif eff_harness not in compat:
                report.error(
                    "harness_not_compatible",
                    f"role '{role}' effective harness '{eff_harness}' is not in the "
                    f"capability profile's harness_compat {sorted(map(str, compat))} "
                    f"for model '{record.get('model')}'; that profile cannot drive "
                    f"this harness (role-configuration-contract.md §4/§5)",
                    f"{base}.harness")

        # --- Dev needs a TOOL-USING (file-editing) coding model ---------------
        if role == "dev" and record.get("tool_use") is not True:
            report.error(
                "dev_needs_tool_use",
                f"Dev model '{record.get('model')}' has tool_use != true; a Dev must "
                f"run a tool-using coding model that can edit files "
                f"(role-configuration-contract.md §4)",
                ref_loc)

        # --- Acceptance MUST be a CALIBRATABLE judge model (§3.6) --------------
        if role == "acceptance" and record.get("calibratable") is not True:
            report.error(
                "acceptance_needs_calibratable",
                f"Acceptance model '{record.get('model')}' is not calibratable; the "
                f"Acceptance judge MUST be a calibratable model — calibration is the "
                f"gate to autonomy (Constitution §3.6; the charter's capability_ref "
                f"comment requires it)",
                ref_loc)

        if role in _VERDICT_ROLES:
            tier = record.get("structured_output_tier")
            rank = _TIER_ORDER.get(str(tier), -1)
            floor = _TIER_ORDER["medium"]
            if rank < floor:
                report.error(
                    "structured_output_floor",
                    f"verdict-emitting role '{role}' requires structured_output_tier "
                    f">= medium but model '{record.get('model')}' is '{tier}'; the "
                    f"engine never lowers the verdict-schema bar for a weaker model "
                    f"(role-configuration-contract.md §4, model-agnostic verdict invariant)",
                    f"{base}.capability_ref" if isinstance(cap_ref, str) else f"{base}.model",
                )
            elif role in _JUDGMENT_ROLES and rank == floor:
                report.warn(
                    "structured_output_recommended_high",
                    f"judgment role '{role}' is recommended a structured_output_tier "
                    f"of 'high'; model '{record.get('model')}' is exactly 'medium' "
                    f"(meets the floor, below the recommended target) "
                    f"(role-configuration-contract.md §4)",
                    f"{base}.capability_ref" if isinstance(cap_ref, str) else f"{base}.model",
                )


def _check_skill_integrity(
    charter: dict,
    report: Report,
    *,
    skill_catalog_path: Optional[str] = None,
    skill_vendor=None,
    repo_root: Optional[str] = None,
) -> None:
    """Facet B skill integrity (role-configuration-contract.md §2/§5; anti-pattern
    #13). Fires ONLY for skills a role explicitly binds via tooling.<role>.skills[];
    if no role binds a skill, NO-OP. For each bound skill:
      - pinned: the binding (pin) OR its catalog entry (source.commit) must carry a
        pin; unpinned/floating source ⇒ ERROR.
      - integrity: the vendored tree_sha256 matches skills/skills.lock (REUSE
        skill_vendor.verify) ⇒ mismatch ERROR.
      - whitelist: the skill's tool_requirements ⊆ the role's tools.allow (or a
        read-only role's {Read,Grep,Glob} default) ⇒ exceed ERROR.
    """
    # Gather every bound skill across roles first; if none, this check is a no-op.
    bindings: list[tuple[str, str, Any, dict]] = []  # (role, skill_id, binding, role_cfg)
    for role, cfg in _iter_roles(charter):
        skills = cfg.get("skills")
        if not isinstance(skills, list):
            continue
        for entry in skills:
            if isinstance(entry, str):
                bindings.append((role, entry, entry, cfg))
            elif isinstance(entry, dict) and isinstance(entry.get("id"), str):
                bindings.append((role, entry["id"], entry, cfg))
    if not bindings:
        return  # NO-OP — no skills bound.

    catalog = load_skill_catalog(skill_catalog_path)
    catalog = _stringify_dates(catalog) if catalog else {}

    # Validate the catalog against its schema (best-effort; absence ⇒ skip cleanly).
    cat_schema = _load_named_schema("skill-catalog.schema.json")
    if catalog and cat_schema is not None:
        for err in Draft202012Validator(cat_schema).iter_errors(catalog):
            report.warn(
                "skill_catalog_invalid",
                f"skills/registry.yaml does not validate skill-catalog.schema.json: "
                f"{err.message}",
                ".".join(str(p) for p in err.absolute_path) or "<root>",
            )

    cat_skills = (catalog.get("skills") or {}) if catalog else {}
    cat_authored = (catalog.get("authored") or {}) if catalog else {}

    sv = skill_vendor if skill_vendor is not None else _import_skill_vendor()
    root = repo_root or _REPO_ROOT

    # Run skill_vendor.verify ONCE for the bound ids that are actually locked
    # (offline, pure). We only key integrity off skills present in skills.lock —
    # an authored/local skill not in the lock is not a vendored-integrity subject,
    # so it is not false-failed here (its pin + whitelist are still checked).
    verify_ok: dict[str, bool] = {}
    verify_msgs: dict[str, list[str]] = {}
    locked_ids: set[str] = set()
    if sv is not None and root is not None:
        try:
            locked_ids = set((sv.load_lock(root).get("skills") or {}).keys())
        except Exception:  # pragma: no cover - defensive
            locked_ids = set()
        wanted = sorted({sid for _, sid, _, _ in bindings} & locked_ids)
        if wanted:
            try:
                vreport = sv.verify(wanted, repo_root=root)
                for r in vreport.results:
                    verify_ok[r.skill_id] = r.ok
                    verify_msgs[r.skill_id] = list(r.messages)
            except Exception:  # pragma: no cover - defensive
                pass

    for role, sid, binding, cfg in bindings:
        base = f"tooling.{role}.skills"
        cat_entry = cat_skills.get(sid) or cat_authored.get(sid) or {}
        is_object_form = isinstance(binding, dict)
        in_catalog = bool(cat_entry)
        in_lock = sid in locked_ids

        # BACKWARD-COMPAT GATE: a bare-string skill that resolves to NOTHING the
        # provenance system knows about (not the v2 object form, not in the
        # catalog, not in the lock) is a LEGACY free name (schema: "Legacy form:
        # skill name or path"). The pin/integrity discipline is a property of the
        # v2 provenance surface, so legacy bare names are left exactly as before.
        if not is_object_form and not in_catalog and not in_lock:
            continue

        # --- pinned: binding.pin OR catalog source.commit --------------------
        binding_pin = binding.get("pin") if is_object_form else None
        catalog_pin = (cat_entry.get("source") or {}).get("commit") if cat_entry else None
        # 'local'/'authored' sources are in-repo (no upstream pin needed).
        src_kind = (binding.get("source") if is_object_form else None) or (
            cat_entry.get("source", {}).get("repo") if cat_entry else None
        )
        in_repo = src_kind in ("authored", "local") or (
            isinstance(cat_entry.get("source"), dict)
            and cat_entry["source"].get("repo") == "local"
        )
        if not in_repo and not binding_pin and not catalog_pin:
            report.error(
                "skill_unpinned",
                f"role '{role}' binds skill '{sid}' with no commit/pin "
                f"(binding.pin absent and no catalog source.commit); unpinned / "
                f"runtime-fetched skill sources are FORBIDDEN "
                f"(role-configuration-contract.md §2; Constitution §1.7 Δ-C4)",
                base,
            )

        # --- integrity: vendored tree_sha256 vs skills.lock ------------------
        if sid in verify_ok and not verify_ok[sid]:
            detail = "; ".join(verify_msgs.get(sid, [])) or "tree_sha256 mismatch"
            report.error(
                "skill_integrity",
                f"role '{role}' binds skill '{sid}' whose vendored content fails "
                f"integrity verification against skills/skills.lock: {detail} "
                f"(role-configuration-contract.md §5)",
                base,
            )

        # --- whitelist: skill tool_requirements ⊆ role tools.allow -----------
        reqs = cat_entry.get("tool_requirements") if cat_entry else None
        if isinstance(reqs, list) and reqs:
            allow = _role_tools_allow(cfg)
            if allow is None and _role_is_read_only(role, cfg):
                allow = {"Read", "Grep", "Glob"}  # read-only default whitelist
            if allow is not None:
                exceeded = [t for t in reqs if str(t) not in allow]
                if exceeded:
                    report.error(
                        "skill_tool_whitelist",
                        f"role '{role}' skill '{sid}' requires tools "
                        f"{sorted(set(map(str, exceeded)))} not in the role's "
                        f"whitelist {sorted(allow)}; a skill's tool_requirements MUST "
                        f"be ⊆ the role whitelist (anti-pattern #13; "
                        f"role-configuration-contract.md §2)",
                        base,
                    )


@dataclass
class Overrides:
    """Optional override paths for the P-0a data sources (tests inject fixtures;
    production uses the shipped defaults / repo state). All OPTIONAL."""

    model_registry_path: Optional[str] = None
    skill_catalog_path: Optional[str] = None
    connector_catalog_path: Optional[str] = None


def validate_semantics(charter: Any, report: Report, overrides: Optional[Overrides] = None) -> None:
    if not isinstance(charter, dict):
        report.error("structural", "charter root must be a mapping/object", "<root>")
        return
    ov = overrides or Overrides()
    _check_mandatory_checkpoints(charter, report)
    _check_acceptance_on_fix_required(charter, report)
    _check_calibration_corollary(charter, report)
    _check_adaptive_insert_bound(charter, report)
    # P-0a checks (fire ONLY when the relevant new charter fields are present):
    _check_connector_grants(
        charter,
        report,
        connector_catalog_path=ov.connector_catalog_path,
        skill_catalog_path=ov.skill_catalog_path,
    )
    _check_capability_gate(charter, report, model_registry_path=ov.model_registry_path)
    _check_skill_integrity(charter, report, skill_catalog_path=ov.skill_catalog_path)
    _check_network_access(charter, report)


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #
def load_schema(schema_path: Optional[str] = None) -> dict:
    path = schema_path or SCHEMA_PATH
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(
            "mission-charter.schema.json not found; expected under a schemas/ "
            "directory at or above engine-kit/ (searched from "
            f"{_THIS_DIR})"
        )
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_charter(charter_path: str) -> Any:
    with open(charter_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def validate_charter(
    charter: Any,
    schema: Optional[dict] = None,
    overrides: Optional[Overrides] = None,
) -> Report:
    """Validate an already-parsed charter object. Pure: no I/O beyond the schema
    (which the caller may pass in). Returns a Report (errors + warnings)."""
    if schema is None:
        schema = load_schema()
    report = Report()
    # P-A: normalize the acceptance namespace + mode IN PLACE *before* structure
    # validation — the schema's root additionalProperties:false would otherwise
    # reject a legacy top-level `acceptance` block before we could warn (design
    # §1.4). charter_compat is pure; warnings/errors map straight to the Report.
    _norm_warn, _norm_err = charter_compat.normalize_acceptance(charter)
    for _m in _norm_err:
        report.error("acceptance_namespace", _m, "tooling.acceptance")
    for _m in _norm_warn:
        report.warn("acceptance_namespace", _m, "tooling.acceptance")
    validate_structure(charter, schema, report)
    validate_semantics(charter, report, overrides)
    return report


def validate_file(
    charter_path: str,
    schema_path: Optional[str] = None,
    overrides: Optional[Overrides] = None,
) -> Report:
    """Validate a charter file end-to-end. YAML parse / schema load errors are
    returned as a Report with a single error (so the CLI exits non-zero cleanly)."""
    report = Report()
    try:
        schema = load_schema(schema_path)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        report.error("schema_load", f"could not load schema: {exc}", "")
        return report
    try:
        charter = load_charter(charter_path)
    except FileNotFoundError as exc:
        report.error("charter_load", f"charter file not found: {exc}", charter_path)
        return report
    except yaml.YAMLError as exc:
        report.error("charter_parse", f"YAML parse error: {exc}", charter_path)
        return report
    return validate_charter(charter, schema, overrides)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic (no-LLM) validator for a Δ-18 mission charter.",
    )
    parser.add_argument("charter", help="path to the charter YAML file")
    parser.add_argument(
        "--schema",
        default=None,
        help="override path to mission-charter.schema.json (default: auto-locate)",
    )
    args = parser.parse_args(argv)

    report = validate_file(args.charter, args.schema)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
