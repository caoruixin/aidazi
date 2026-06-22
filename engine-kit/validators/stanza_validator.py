#!/usr/bin/env python3
"""stanza_validator — deterministic (no-LLM) validator for a sprint-stanza.

A sprint-stanza is the compact 4-field machine-validated header carried in the
front-matter of ``docs/sprint_objective.md`` (see templates/sprint-objective.md).
The orchestrator runs ``validate_stanza`` as a preflight gate at sub-sprint
dispatch (process/delivery-loop.md §4.2.4) and again at close. This tool is the
KIT implementation of that gate; it mechanizes friction case F4
(docs/friction-playbook.md): catch a stanza with missing / wrong-typed fields
BEFORE the compact dev prompt is dispatched, not at the expensive close gate.

Single layer — STRUCTURAL: validate the stanza (YAML or JSON) against
schemas/sprint_stanza.schema.json using ``jsonschema``. The schema is the
source of truth for the required fields, item types, enums, and
``additionalProperties: false``; this module only loads it and reports its
findings with a clear message + the offending path.

Input shapes accepted:
  * A bare stanza mapping (sprint_id / scope_in / layers / exit_criteria / …).
  * A sprint-objective document whose front-matter (or top-level mapping)
    carries a ``sprint_stanza:`` key — the stanza is unwrapped and validated.
    (This lets the tool point straight at docs/sprint_objective.md once the
    stanza is lifted out of the markdown front-matter by the caller.)

Determinism contract: pure function over the input file + the bundled schema.
No network, no LLM, no clock/random dependence. Same input ⇒ same report.

CLI:
    python stanza_validator.py <stanza.(yaml|json)>
    exit 0  ⇒ stanza is structurally valid against the schema
    exit !0 ⇒ schema-load failure, parse failure, or any structural error
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
except ImportError:  # pragma: no cover - import guard
    sys.stderr.write(
        "stanza_validator: PyYAML is required (pip install -r requirements.txt)\n"
    )
    raise

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - import guard
    sys.stderr.write(
        "stanza_validator: jsonschema is required (pip install -r requirements.txt)\n"
    )
    raise


# --------------------------------------------------------------------------- #
# Locate the normative schema. engine-kit/ is copied next to the spec tree, so
# walk up from this file to find schemas/sprint_stanza.schema.json.
# --------------------------------------------------------------------------- #
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

_SCHEMA_RELPATH = ("schemas", "sprint_stanza.schema.json")


def _find_schema_path() -> Optional[str]:
    """Walk parent dirs looking for schemas/sprint_stanza.schema.json."""
    cur = _THIS_DIR
    while True:
        candidate = os.path.join(cur, *_SCHEMA_RELPATH)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


SCHEMA_PATH = _find_schema_path()


@dataclass
class Issue:
    """One validator finding. ``level`` is 'error' (this tool emits no warnings)."""

    level: str
    rule: str          # short stable rule id (test-assertable)
    message: str
    path: str          # offending stanza path, e.g. "layers.0" or "<root>"

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
            lines.append(
                "stanza_validator: OK — sprint-stanza is structurally valid."
            )
        summary = f"\n{len(self.errors)} error(s), {len(self.warnings)} warning(s)."
        return "\n".join(lines) + summary


# --------------------------------------------------------------------------- #
# Structural validation against the JSON schema.
# --------------------------------------------------------------------------- #
def validate_structure(stanza: Any, schema: dict, report: Report) -> None:
    validator = Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(stanza), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        report.error("structural", err.message, path)


def _unwrap_stanza(parsed: Any) -> Any:
    """Accept either a bare stanza mapping or a doc carrying ``sprint_stanza:``.

    If the parsed object is a mapping that contains a ``sprint_stanza`` key, that
    nested value is the stanza to validate (this matches the front-matter shape
    in templates/sprint-objective.md). Otherwise the object is treated as the
    stanza itself. Non-mapping inputs are returned unchanged so the schema layer
    can reject them with a clear type error.
    """
    if isinstance(parsed, dict) and "sprint_stanza" in parsed:
        return parsed["sprint_stanza"]
    return parsed


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #
def load_schema(schema_path: Optional[str] = None) -> dict:
    path = schema_path or SCHEMA_PATH
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(
            "sprint_stanza.schema.json not found; expected under a schemas/ "
            f"directory at or above engine-kit/ (searched from {_THIS_DIR})"
        )
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_stanza(stanza_path: str) -> Any:
    """Parse a stanza file. JSON and YAML both parse via yaml.safe_load (JSON is
    a YAML subset), so a single loader handles both ``.yaml`` and ``.json``."""
    with open(stanza_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def validate_stanza(stanza: Any, schema: Optional[dict] = None) -> Report:
    """Validate an already-parsed stanza object. Pure: no I/O beyond the schema
    (which the caller may pass in). Returns a Report (errors only here)."""
    if schema is None:
        schema = load_schema()
    report = Report()
    validate_structure(_unwrap_stanza(stanza), schema, report)
    return report


def validate_file(stanza_path: str, schema_path: Optional[str] = None) -> Report:
    """Validate a stanza file end-to-end. YAML/JSON parse and schema-load errors
    are returned as a Report with a single error (so the CLI exits non-zero
    cleanly rather than raising)."""
    report = Report()
    try:
        schema = load_schema(schema_path)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        report.error("schema_load", f"could not load schema: {exc}", "")
        return report
    try:
        stanza = load_stanza(stanza_path)
    except FileNotFoundError as exc:
        report.error("stanza_load", f"stanza file not found: {exc}", stanza_path)
        return report
    except yaml.YAMLError as exc:
        report.error("stanza_parse", f"YAML/JSON parse error: {exc}", stanza_path)
        return report
    return validate_stanza(stanza, schema)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic (no-LLM) validator for a sprint-stanza "
        "against schemas/sprint_stanza.schema.json.",
    )
    parser.add_argument("stanza", help="path to the stanza YAML or JSON file")
    parser.add_argument(
        "--schema",
        default=None,
        help="override path to sprint_stanza.schema.json (default: auto-locate)",
    )
    args = parser.parse_args(argv)

    report = validate_file(args.stanza, args.schema)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
