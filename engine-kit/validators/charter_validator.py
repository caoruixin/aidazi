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
                              §4.2.3 (the 8 MANDATORY_CHECKPOINTS)
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


# The 8 default MANDATORY_CHECKPOINTS (process/delivery-loop.md §4.2.3). These
# always fire; a charter MAY add custom checkpoints but MAY NOT bypass any of
# these in any of the four shapes (omitted / emptied / disabled / overridden).
MANDATORY_CHECKPOINTS: tuple[str, ...] = (
    "mission_start",
    "research_proposal_selection",
    "bad_case_manual_review",
    "new_tier0_candidate",
    "forbidden_list_redline",
    "scope_deviation",
    "close_taxonomy_C_or_D",
    "gate_hard_fail",
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
    """The 8 default MANDATORY_CHECKPOINTS must not be bypassed in any of the 4
    shapes (process/delivery-loop.md §4.2.2 / governance/constitution.md §1.7-D):
        omitted / emptied / disabled / overridden.

    The real charter shape (schemas/mission-charter.schema.json) does NOT
    enumerate the 8 defaults — they fire implicitly, and the schema's top-level
    ``additionalProperties: false`` already forbids a stray ``mandatory_checkpoints``
    key. So this check defends the *semantic* boundary the schema can't see:

      * OMITTED  — only meaningful if the charter introduces a checkpoint
        ENUMERATION section (a key whose name contains "mandatory_checkpoint" and
        is not the additive ``mandatory_checkpoints_added``). If such a section
        exists, every one of the 8 defaults must appear in it; a missing default
        is the omitted bypass. (Absence of any such section is the legitimate
        default state — the 8 fire implicitly — and is NOT a violation.)
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
    """acceptance.on_fix_required rules (delivery-loop §4.2.2; constitution §1.7-C):
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
            f"acceptance.on_fix_required.human_confirm_required MUST be true "
            f"(got {hcr!r}); Constitution §1.7-C — Acceptance never silently "
            f"routes fix_required to Deliver",
            f"{base}.human_confirm_required",
        )

    routes = ofr.get("route_options")
    if not isinstance(routes, list) or len(routes) == 0:
        report.error(
            "route_options_nonempty",
            f"acceptance.on_fix_required.route_options MUST be a non-empty list "
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
def _check_connector_grants(charter: dict, report: Report) -> None:
    # TODO P-0a: connectors default-deny + role grant ⊇ skill connector
    # requirements. See plan §4.1 facet C — schemas/connector-binding.schema.json
    # not yet defined. No-op until P-0a lands.
    return


def _check_capability_gate(charter: dict, report: Report) -> None:
    # TODO P-0a: validate the (harness, provider, model) triple against
    # model-capability-registry. See plan §4.1 facet A / §5 — registry schema
    # not yet defined. No-op until P-0a lands.
    return


def _check_skill_integrity(charter: dict, report: Report) -> None:
    # TODO P-0a: skill integrity / provenance / pin (no unpinned or
    # runtime-fetched skill sources). See plan §4.1 facet B / §6 constitution
    # edit #4 — skill-binding/skill-catalog schemas not yet defined. No-op.
    return


def validate_semantics(charter: Any, report: Report) -> None:
    if not isinstance(charter, dict):
        report.error("structural", "charter root must be a mapping/object", "<root>")
        return
    _check_mandatory_checkpoints(charter, report)
    _check_acceptance_on_fix_required(charter, report)
    _check_calibration_corollary(charter, report)
    _check_adaptive_insert_bound(charter, report)
    # P-0a extension points (currently no-op):
    _check_connector_grants(charter, report)
    _check_capability_gate(charter, report)
    _check_skill_integrity(charter, report)


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


def validate_charter(charter: Any, schema: Optional[dict] = None) -> Report:
    """Validate an already-parsed charter object. Pure: no I/O beyond the schema
    (which the caller may pass in). Returns a Report (errors + warnings)."""
    if schema is None:
        schema = load_schema()
    report = Report()
    validate_structure(charter, schema, report)
    validate_semantics(charter, report)
    return report


def validate_file(charter_path: str, schema_path: Optional[str] = None) -> Report:
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
    return validate_charter(charter, schema)


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
