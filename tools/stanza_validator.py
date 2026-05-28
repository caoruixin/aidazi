#!/usr/bin/env python3
"""Validate the §7 stanza in a sub-sprint objective document.

Usage:
    python stanza_validator.py <sprint_objective.md>
    python stanza_validator.py --json <stanza.json>

The stanza in `sprint_objective.md` is authored as Markdown for human
readability. This script extracts the four required fields and
validates them against `../schemas/sprint_stanza.schema.json`.

Exit code 0 means the stanza is valid. Non-zero means a violation;
diagnostics are printed to stderr.

Dependencies:
    - jsonschema (pip install jsonschema)

If the consumer project marks a sub-sprint as §7 EXEMPT (pure infra,
docs-only, config-governance, characterization-test), the stanza is
not required; this validator should be skipped for those sub-sprints.
The deliver-agent + human decide the exemption at sub-sprint planning.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print(
        "ERROR: jsonschema not installed. Run: pip install jsonschema",
        file=sys.stderr,
    )
    sys.exit(2)


SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "sprint_stanza.schema.json"


LAYER_ENUM = {
    "infra",
    "runtime_guard",
    "prompt_projection",
    "skill_state",
    "semantic_planner",
    "eval_spec",
    "product_policy",
    "judge_calibration",
    "human_review_required",
}


def _extract_stanza_block(md_text: str) -> str:
    """Extract the stanza Markdown block from a sprint_objective.md file.

    Looks for the heading `## Layer-classification + anti-hardcode stanza`
    (case-insensitive, allows nested heading depth) and returns content
    until the next heading or end of file.
    """
    pattern = re.compile(
        r"^#{1,6}\s+Layer-classification\s*\+\s*anti-hardcode\s*stanza\b.*?$"
        r"(?P<body>.*?)"
        r"(?=^#{1,6}\s|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(md_text)
    if not m:
        return ""
    return m.group("body")


def _parse_field(block: str, field_name: str) -> str:
    """Extract `**field_name:**` field value (until next bold field or end).
    """
    bold_label = re.escape(field_name)
    pattern = re.compile(
        rf"\*\*{bold_label}:\*\*\s*(?P<value>.*?)(?=\n\s*\*\*|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(block)
    if not m:
        return ""
    return m.group("value").strip()


def _parse_target_layer(value: str) -> dict[str, Any] | None:
    """Extract layer name from free-form text."""
    if not value:
        return None
    for layer in LAYER_ENUM:
        if re.search(rf"\b{re.escape(layer)}\b", value, re.IGNORECASE):
            return layer
    return None


def _parse_tier0(value: str) -> dict[str, Any] | None:
    if not value:
        return None
    lower = value.lower()
    if (
        "no tier-0" in lower
        or "no tier 0" in lower
        or "adds no tier-0" in lower
        or "this sprint adds no tier-0 invariant" in lower
    ):
        return {"status": "none"}
    pointer_m = re.search(
        r"docs/current/runtime_invariants\.md\s*(?:§|section\s+)\s*([\d.\w_-]+)",
        value,
        re.IGNORECASE,
    )
    if pointer_m:
        return {"status": "protects_existing", "pointer": "§" + pointer_m.group(1)}
    if "new tier-0 candidate" in lower or "new candidate" in lower:
        return {
            "status": "new_candidate",
            "candidate_description": value.strip(),
            "human_review_required": True,
        }
    return None


def _parse_hardcode(value: str) -> dict[str, Any] | None:
    if not value:
        return None
    lower = value.lower()
    if (
        "no semantic hardcode" in lower
        or "no hardcode" in lower
        or "no new hardcode" in lower
    ):
        return {"introduced": False}
    if "introduces" in lower or "introduce" in lower:
        sunset_trigger_m = re.search(
            r"sunset plan:\s*(?P<trigger>.+?)(?:;|\.|$)", value, re.IGNORECASE
        )
        target_sprint_m = re.search(
            r"target sprint(?:\s*id)?:\s*([\w-]+)", value, re.IGNORECASE
        )
        if sunset_trigger_m and target_sprint_m:
            return {
                "introduced": True,
                "hardcode_name": "see stanza body",
                "justification": value.strip(),
                "sunset_plan": {
                    "trigger": sunset_trigger_m.group("trigger").strip(),
                    "target_sprint_id": target_sprint_m.group(1).strip(),
                },
            }
    return None


def _parse_coverage(value: str) -> dict[str, Any] | None:
    if not value:
        return None
    counts_m = re.search(
        r"(?:counts?:?\s*)?(?P<t>\d+)\s*/\s*(?P<n>\d+)\s*/\s*(?P<g>\d+)\s*/\s*(?P<s>\d+)",
        value,
    )
    if counts_m:
        return {
            "status": "declared",
            "counts": {
                "target": int(counts_m.group("t")),
                "neighbor": int(counts_m.group("n")),
                "negative": int(counts_m.group("g")),
                "shadow": int(counts_m.group("s")),
            },
        }
    deferred_m = re.search(r"deferred to\s*([\w-]+)", value, re.IGNORECASE)
    if deferred_m:
        return {
            "status": "deferred",
            "deferred_to_sprint_id": deferred_m.group(1).strip(),
            "reason": value.strip(),
        }
    return None


def parse_md_to_stanza_dict(md_text: str) -> dict[str, Any]:
    block = _extract_stanza_block(md_text)
    if not block:
        return {}

    layer_value = _parse_field(block, "Target failure layer")
    tier0_value = _parse_field(block, "Tier-0 invariant")
    hardcode_value = _parse_field(block, "Semantic hardcode")
    coverage_value = _parse_field(block, "Generalization coverage")

    target_layer = _parse_target_layer(layer_value)
    tier0 = _parse_tier0(tier0_value)
    hardcode = _parse_hardcode(hardcode_value)
    coverage = _parse_coverage(coverage_value)

    out: dict[str, Any] = {}
    if target_layer is not None:
        out["target_failure_layer"] = target_layer
    if tier0 is not None:
        out["tier0_invariant"] = tier0
    if hardcode is not None:
        out["semantic_hardcode"] = hardcode
    if coverage is not None:
        out["generalization_coverage"] = coverage
    return out


def validate(stanza: dict[str, Any]) -> tuple[bool, list[str]]:
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(stanza), key=lambda e: e.path)
    if not errors:
        return True, []
    msgs: list[str] = []
    for err in errors:
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        msgs.append(f"{path}: {err.message}")
    return False, msgs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the §7 stanza in a sprint objective."
    )
    parser.add_argument(
        "input",
        help="Path to sprint_objective.md OR a JSON file (use --json).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Treat input as a pre-parsed JSON stanza instead of Markdown.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"ERROR: not a file: {input_path}", file=sys.stderr)
        return 2

    if args.json:
        with input_path.open() as f:
            stanza = json.load(f)
    else:
        md_text = input_path.read_text(encoding="utf-8")
        stanza = parse_md_to_stanza_dict(md_text)
        if not stanza:
            print(
                "ERROR: could not extract §7 stanza block from Markdown. "
                "Verify the heading '## Layer-classification + anti-hardcode stanza' exists.",
                file=sys.stderr,
            )
            return 2

    ok, errs = validate(stanza)
    if ok:
        print(f"OK: §7 stanza valid in {input_path}")
        return 0
    print(f"INVALID: §7 stanza errors in {input_path}:", file=sys.stderr)
    for msg in errs:
        print(f"  - {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
