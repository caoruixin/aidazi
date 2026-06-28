#!/usr/bin/env python3
"""control_plane_validator — deterministic checks for the default Control Plane Session.

The default coding-agent session is a lightweight natural-language control plane,
not a delivery role. This validator enforces the parts that can be checked without
an LLM:

* AGENTS.md carries a ``control-plane-load`` fenced YAML block.
* That block has the required tiny default refs and schema/on-demand refs.
* The default allow/on_demand lists do not include broad globs or forbidden heavy
  surfaces (role cards, action banks, handoffs, transcripts, eval runs, archives).
* The root AGENTS.md does not directly @-include the full governance triple, which
  would defeat the lightweight default session.
* Optional control-plane state / intent JSON records validate against their schemas.
* Optional Control Plane roadmap state / mutation records validate against their
  schemas.

Normative source: ``process/control-plane-routing.md`` + ``AGENTS.md`` §3A.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("control_plane_validator: PyYAML is required\n")
    raise

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    sys.stderr.write("control_plane_validator: jsonschema is required\n")
    raise


REQUIRED_ALLOW = {
    "AGENTS.md",
    ".orchestrator/control/state.json",
    ".orchestrator/control/intents.jsonl",
    ".orchestrator/control/roadmap-state.json",
    ".orchestrator/control/roadmap-mutations.jsonl",
    "docs/current/adoption-state.md",
    "docs/current/agent_context_guide.md",
}

REQUIRED_ON_DEMAND = {
    "aidazi/process/control-plane-routing.md",
    "aidazi/schemas/control-plane-intent.schema.json",
    "aidazi/schemas/control-plane-state.schema.json",
    "aidazi/schemas/roadmap-state.schema.json",
    "aidazi/schemas/roadmap-mutation.schema.json",
}

REQUIRED_FORBID = {
    "aidazi/role-cards/**",
    "docs/action_bank.md",
    "docs/handoff.md",
    "docs/10-handoff.md",
    "docs/research-briefs/**",
    "docs/proposals/**",
    "docs/sprints/**",
    ".orchestrator/audit/**",
    ".runs/**",
    "eval/runs/**",
}

CONTROL_STATE_REL = ".orchestrator/control/state.json"
CONTROL_INTENTS_REL = ".orchestrator/control/intents.jsonl"
CONTROL_ROADMAP_STATE_REL = ".orchestrator/control/roadmap-state.json"
CONTROL_ROADMAP_MUTATIONS_REL = ".orchestrator/control/roadmap-mutations.jsonl"

FORBIDDEN_DEFAULT_PATTERNS = tuple(sorted(REQUIRED_FORBID | {
    "aidazi/process/delivery-loop.md",
    "aidazi/process/campaign-loop.md",
}))

CONTROL_BLOCK_RE = re.compile(
    r"```control-plane-load\s*\n(?P<body>.*?)\n```",
    re.DOTALL,
)

GOVERNANCE_AT_INCLUDE_RE = re.compile(r"^@aidazi/governance/", re.MULTILINE)
AT_INCLUDE_RE = re.compile(r"^@(\S+)", re.MULTILINE)


@dataclass
class Issue:
    level: str
    rule: str
    message: str
    path: str = ""

    def render(self) -> str:
        tag = "ERROR" if self.level == "error" else "WARN "
        loc = f" @ {self.path}" if self.path else ""
        return f"[{tag}] {self.rule}: {self.message}{loc}"


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    def error(self, rule: str, message: str, path: str = "") -> None:
        self.errors.append(Issue("error", rule, message, path))

    def warn(self, rule: str, message: str, path: str = "") -> None:
        self.warnings.append(Issue("warning", rule, message, path))

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def rules_fired(self) -> set[str]:
        return {i.rule for i in (*self.errors, *self.warnings)}

    def merge(self, other: "Report") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def render(self) -> str:
        lines = [i.render() for i in self.errors] + [i.render() for i in self.warnings]
        if not lines:
            lines.append("control_plane_validator: OK.")
        lines.append(f"{len(self.errors)} error(s), {len(self.warnings)} warning(s).")
        return "\n".join(lines)


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value]


def _has_glob(path: str) -> bool:
    return "*" in path or "?" in path or "[" in path or "]" in path


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(path, pat) for pat in patterns)


def _normalize_ref(ref: str) -> Optional[str]:
    """Normalize a root AGENTS @-include token into the control-plane ref vocabulary."""
    if not ref or ref.startswith("<"):
        return None
    ref = ref.replace("\\", "/")
    if ref.startswith("./"):
        ref = ref[2:]
    while ref.startswith("../"):
        return ref
    return ref


def iter_live_at_includes(text: str) -> list[str]:
    """Return line-level @ imports outside fenced blocks.

    This deliberately stays small: root AGENTS.md uses line-level imports only, and
    the control-plane-load YAML block is fenced so it is ignored.
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = AT_INCLUDE_RE.match(line)
        if m:
            norm = _normalize_ref(m.group(1))
            if norm is not None:
                out.append(norm)
    return out


def parse_control_plane_load(text: str, report: Report, *, path: str) -> Optional[dict]:
    m = CONTROL_BLOCK_RE.search(text)
    if not m:
        report.error(
            "control_plane_load_missing",
            "AGENTS.md must include a fenced ```control-plane-load``` YAML block.",
            path,
        )
        return None
    try:
        data = yaml.safe_load(m.group("body"))
    except yaml.YAMLError as exc:
        report.error("control_plane_load_malformed", f"invalid YAML: {exc}", path)
        return None
    if not isinstance(data, dict):
        report.error(
            "control_plane_load_malformed",
            "control-plane-load block must parse to a mapping.",
            path,
        )
        return None
    return data


def validate_load_block(data: dict, report: Report, *, path: str) -> None:
    allow = set(_as_list(data.get("allow")))
    on_demand = set(_as_list(data.get("on_demand")))
    forbid = set(_as_list(data.get("forbid")))

    for key, vals in (("allow", allow), ("on_demand", on_demand), ("forbid", forbid)):
        if not isinstance(data.get(key), list):
            report.error(
                "control_plane_load_malformed",
                f"control-plane-load.{key} must be a list.",
                path,
            )

    missing_allow = sorted(REQUIRED_ALLOW - allow)
    if missing_allow:
        report.error(
            "control_plane_allow_missing",
            f"default allow list missing required refs: {missing_allow}",
            path,
        )

    missing_on_demand = sorted(REQUIRED_ON_DEMAND - on_demand)
    if missing_on_demand:
        report.error(
            "control_plane_on_demand_missing",
            f"on_demand list missing required refs: {missing_on_demand}",
            path,
        )

    missing_forbid = sorted(REQUIRED_FORBID - forbid)
    if missing_forbid:
        report.error(
            "control_plane_forbid_missing",
            f"forbid list missing heavy-context refs: {missing_forbid}",
            path,
        )

    for section, vals in (("allow", allow), ("on_demand", on_demand)):
        for ref in sorted(vals):
            if _has_glob(ref):
                report.error(
                    "control_plane_default_glob",
                    f"{section} contains a glob; default control-plane refs must be specific: {ref}",
                    path,
                )
            if _matches_any(ref, FORBIDDEN_DEFAULT_PATTERNS):
                report.error(
                    "control_plane_forbidden_default_load",
                    f"{section} includes forbidden heavy/default context: {ref}",
                    path,
                )


def validate_actual_at_includes(text: str, data: Optional[dict], report: Report, *, path: str) -> None:
    """Validate that AGENTS.md's live @ imports are part of the default allow graph."""
    allow = set(_as_list(data.get("allow"))) if isinstance(data, dict) else set()
    for ref in iter_live_at_includes(text):
        if ref not in allow:
            report.error(
                "control_plane_unlisted_at_include",
                f"live @ include is not in control-plane allow list: {ref}",
                path,
            )
        if _has_glob(ref):
            report.error(
                "control_plane_default_glob",
                f"live @ include contains a glob: {ref}",
                path,
            )
        if _matches_any(ref, FORBIDDEN_DEFAULT_PATTERNS):
            report.error(
                "control_plane_forbidden_default_load",
                f"live @ include loads forbidden heavy/default context: {ref}",
                path,
            )


def validate_agents(path: str) -> Report:
    report = Report()
    if not os.path.isfile(path):
        report.error("agents_missing", "AGENTS.md not found.", path)
        return report
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        report.error("agents_unreadable", f"could not read AGENTS.md: {exc}", path)
        return report

    if GOVERNANCE_AT_INCLUDE_RE.search(text):
        report.error(
            "control_plane_governance_at_include",
            "AGENTS.md directly @-includes full governance docs; default control-plane "
            "startup must keep them role/on-demand.",
            path,
        )

    data = parse_control_plane_load(text, report, path=path)
    if data is not None:
        validate_load_block(data, report, path=path)
    validate_actual_at_includes(text, data, report, path=path)
    return report


def _find_schema(schema_name: str) -> str:
    cur = os.path.abspath(os.path.dirname(__file__))
    while True:
        cand = os.path.join(cur, "schemas", schema_name)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            raise FileNotFoundError(f"schema not found: {schema_name}")
        cur = parent


def _load_schema(schema_name: str) -> dict:
    with open(_find_schema(schema_name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_json_obj(obj: Any, schema_name: str, *, path: str) -> Report:
    report = Report()
    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(obj), key=lambda e: list(e.absolute_path))
    for e in errors:
        loc = ".".join(str(p) for p in e.absolute_path) or "<root>"
        report.error("control_plane_schema_invalid", f"{loc}: {e.message}", path)
    return report


def _read_json_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_state_file(path: str) -> Report:
    report = Report()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        report.error("control_plane_state_unreadable", f"could not read state JSON: {exc}", path)
        return report
    report.merge(validate_json_obj(obj, "control-plane-state.schema.json", path=path))
    return report


def validate_intent_file(path: str) -> Report:
    report = Report()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = list(fh)
    except OSError as exc:
        report.error("control_plane_intent_unreadable", f"could not read intent file: {exc}", path)
        return report
    for idx, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            report.error(
                "control_plane_intent_unreadable",
                f"line {idx}: invalid JSON: {exc}",
                path,
            )
            continue
        line_report = validate_json_obj(
            obj,
            "control-plane-intent.schema.json",
            path=f"{path}:{idx}",
        )
        report.merge(line_report)
        for ref in obj.get("loaded_refs", []) if isinstance(obj, dict) else []:
            if isinstance(ref, str) and _has_glob(ref):
                report.error(
                    "control_plane_default_glob",
                    f"line {idx}: loaded_refs contains a glob: {ref}",
                    path,
                )
            if isinstance(ref, str) and _matches_any(ref, FORBIDDEN_DEFAULT_PATTERNS):
                report.error(
                    "control_plane_forbidden_default_load",
                    f"line {idx}: loaded_refs includes forbidden heavy/default context: {ref}",
                    path,
                )
    return report


def validate_jsonl_file(path: str, schema_name: str, *, rule_prefix: str) -> Report:
    report = Report()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = list(fh)
    except OSError as exc:
        report.error(f"{rule_prefix}_unreadable", f"could not read JSONL file: {exc}", path)
        return report
    for idx, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            report.error(f"{rule_prefix}_unreadable", f"line {idx}: invalid JSON: {exc}", path)
            continue
        report.merge(validate_json_obj(obj, schema_name, path=f"{path}:{idx}"))
    return report


def validate_roadmap_state_file(path: str) -> Report:
    report = Report()
    try:
        obj = _read_json_file(path)
    except (OSError, json.JSONDecodeError) as exc:
        report.error("control_plane_roadmap_state_unreadable", f"could not read roadmap state JSON: {exc}", path)
        return report
    report.merge(validate_json_obj(obj, "roadmap-state.schema.json", path=path))
    return report


def validate_root(root: str, *, state_path: Optional[str] = None,
                  intents_path: Optional[str] = None) -> Report:
    report = Report()
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        report.error("missing_root", f"root is not a directory: {root}", root)
        return report
    report.merge(validate_agents(os.path.join(root, "AGENTS.md")))

    explicit_state = state_path is not None
    explicit_intents = intents_path is not None
    state_path = state_path or os.path.join(root, CONTROL_STATE_REL)
    intents_path = intents_path or os.path.join(root, CONTROL_INTENTS_REL)
    if not os.path.isabs(state_path):
        state_path = os.path.join(root, state_path)
    if not os.path.isabs(intents_path):
        intents_path = os.path.join(root, intents_path)

    if explicit_state or os.path.exists(state_path):
        report.merge(validate_state_file(state_path))
    if explicit_intents or os.path.exists(intents_path):
        report.merge(validate_intent_file(intents_path))
    roadmap_path = os.path.join(root, CONTROL_ROADMAP_STATE_REL)
    mutations_path = os.path.join(root, CONTROL_ROADMAP_MUTATIONS_REL)
    if os.path.exists(roadmap_path):
        report.merge(validate_roadmap_state_file(roadmap_path))
    if os.path.exists(mutations_path):
        report.merge(validate_jsonl_file(
            mutations_path,
            "roadmap-mutation.schema.json",
            rule_prefix="control_plane_roadmap_mutation",
        ))
    return report


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate default Control Plane Session wiring and optional state/intent files.",
    )
    parser.add_argument("root", help="adopter repo root")
    parser.add_argument("--state", default=None, help="path to .orchestrator/control/state.json")
    parser.add_argument("--intents", default=None, help="path to .orchestrator/control/intents.jsonl")
    args = parser.parse_args(argv)

    report = validate_root(args.root, state_path=args.state, intents_path=args.intents)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
