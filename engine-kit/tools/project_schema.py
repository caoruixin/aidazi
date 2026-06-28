#!/usr/bin/env python3
"""project_schema — WP-1b compact-projection generator (context/token optimization).

Emit a COMPACT PROJECTION of a canonical JSON Schema for AGENT consumption: the same
schema with the pure-annotation keywords (title / description / $comment / examples)
removed, every MACHINE keyword preserved byte-for-byte. The canonical schema stays
verbose (the Python validator, the mission-charter.yaml template, and humans keep it);
only the agent's mid-session Read loads the smaller projection — the single
framework-controllable token lever (read-volume reduction). This reuses the technique
proven by WP-1a (research-brief slim) but as a SEPARATE file so the canonical is untouched.

WHY VALIDATION-NEUTRAL: title/description/$comment/examples are JSON-Schema 2020-12
*annotations* — they never affect assertion outcomes (jsonschema applies no defaults and
reads no annotation in validation). So an instance accepted/rejected by the canonical is
accepted/rejected identically by the projection. The generator proves this STRUCTURALLY
(only annotation keywords are dropped, in schema position) and the test-suite proves it
BEHAVIOURALLY (a fixture corpus validates identically against canonical vs projection).

CRITICAL CORRECTNESS RULE — strip annotation keywords ONLY in SCHEMA POSITION, never a
property literally NAMED "description"/"title"/etc. The walker therefore recurses into the
KNOWN schema-bearing keywords only (so it never confuses a property name, an enum value, or
a const payload for a keyword) and copies every other keyword's value verbatim.

The projection embeds a DISTINCT ``$id`` (…/compact/<name>.compact.schema.json — no registry
collision with the canonical) plus ``x-canonical-sha256`` / ``x-canonical-source`` — the
LOCKSTEP anchor: a checked-in test recomputes sha256(canonical bytes) and fails if it drifts
from the projection's embedded value (regenerate → re-review). CLI::

    python project_schema.py schemas/review-verdict.schema.json [-o schemas/compact/...]
    python project_schema.py --check schemas/review-verdict.schema.json   # lockstep only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

#: Pure-annotation keywords (2020-12) — dropped in schema position. NOT machine keys: they
#: do not affect validation, and no aidazi code reads them. Everything else is preserved.
ANNOTATION_KEYWORDS: frozenset = frozenset(
    {"title", "description", "$comment", "examples"})

#: Keywords whose value is a SINGLE subschema → recurse into the value as a schema.
_SCHEMA_VALUE: frozenset = frozenset({
    "additionalProperties", "propertyNames", "not", "if", "then", "else",
    "contains", "additionalItems", "unevaluatedItems", "unevaluatedProperties",
    "contentSchema",
})
#: Keywords whose value is a LIST of subschemas → recurse into each element.
_SCHEMA_LIST: frozenset = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
#: Keywords whose value is a MAP name→subschema → KEYS are names (kept verbatim, NOT
#: treated as keywords); recurse into the VALUES only.
_SCHEMA_MAP: frozenset = frozenset({
    "properties", "patternProperties", "$defs", "definitions", "dependentSchemas",
})


def strip_annotations(node):
    """Return ``node`` with annotation keywords removed in every SCHEMA position, deeply.

    Position-aware: recurses ONLY into the known schema-bearing keywords, so a property
    NAMED "description" (a key under ``properties``), an ``enum``/``const`` payload, or any
    vendor keyword's value is copied VERBATIM — never mistaken for an annotation keyword.
    Pure (no I/O); returns new containers (the input is not mutated)."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in ANNOTATION_KEYWORDS:
                continue                                   # drop the annotation keyword
            if key in _SCHEMA_MAP and isinstance(value, dict):
                out[key] = {name: strip_annotations(sub) for name, sub in value.items()}
            elif key in _SCHEMA_LIST and isinstance(value, list):
                out[key] = [strip_annotations(item) for item in value]
            elif key in _SCHEMA_VALUE:
                out[key] = strip_annotations(value)
            elif key == "items":
                # 2020-12: a single schema; draft-07 legacy: a list of schemas.
                out[key] = ([strip_annotations(i) for i in value]
                            if isinstance(value, list) else strip_annotations(value))
            elif key == "dependencies":
                # draft-07 mix: name → (subschema | list-of-property-names). Recurse only
                # the subschema form; copy the property-name-list form verbatim.
                out[key] = ({n: (strip_annotations(s) if isinstance(s, dict) else s)
                             for n, s in value.items()}
                            if isinstance(value, dict) else value)
            else:
                out[key] = value                           # machine keyword: verbatim
        return out
    if isinstance(node, list):
        return [strip_annotations(item) for item in node]
    return node


def _compact_id(canonical_id: str, compact_rel: str) -> str:
    """Derive the projection's DISTINCT $id from the canonical $id (swap the trailing
    path segment to the compact rel's basename so canonical + projection never collide in
    a shared registry). Falls back to the compact basename when the canonical has no $id."""
    base = os.path.basename(compact_rel)
    if canonical_id and "/" in canonical_id:
        return canonical_id.rsplit("/", 1)[0] + "/compact/" + base
    return base


def project(canonical_bytes: bytes, *, compact_rel: str) -> dict:
    """Build the compact projection dict from the canonical schema BYTES.

    Embeds ``x-canonical-sha256`` (over the exact canonical bytes — the lockstep anchor),
    ``x-canonical-source`` (the canonical's basename), and a distinct ``$id``. The annotation
    keywords are stripped; ``$schema`` and every machine keyword are preserved."""
    canonical = json.loads(canonical_bytes)
    compact = strip_annotations(canonical)
    if not isinstance(compact, dict):                      # pragma: no cover - schemas are objects
        raise ValueError("schema root is not a JSON object")
    canonical_id = canonical.get("$id", "")
    compact["$id"] = _compact_id(canonical_id, compact_rel)
    compact["x-canonical-source"] = os.path.basename(compact_rel).replace(
        ".compact.schema.json", ".schema.json")
    compact["x-canonical-sha256"] = hashlib.sha256(canonical_bytes).hexdigest()
    return compact


def serialize(compact: dict) -> str:
    """Deterministic on-disk form: 2-space indent + trailing newline (stable diffs)."""
    return json.dumps(compact, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- #
# Lockstep check.
# --------------------------------------------------------------------------- #
def check_lockstep(canonical_path: str, compact_path: str) -> tuple:
    """Verify the projection is in lockstep with its canonical: ``x-canonical-sha256`` must
    equal sha256(canonical bytes), AND regenerating from the canonical must reproduce the
    on-disk projection byte-for-byte. Returns ``(ok, reason)``."""
    with open(canonical_path, "rb") as fh:
        canonical_bytes = fh.read()
    with open(compact_path, "r", encoding="utf-8") as fh:
        on_disk = fh.read()
    try:
        embedded = json.loads(on_disk).get("x-canonical-sha256")
    except json.JSONDecodeError as exc:
        return False, f"projection is not valid JSON: {exc}"
    actual = hashlib.sha256(canonical_bytes).hexdigest()
    if embedded != actual:
        return False, (f"x-canonical-sha256 stale: embedded {embedded!r} != "
                       f"sha256(canonical) {actual!r} — regenerate the projection")
    rel = os.path.basename(compact_path)
    regenerated = serialize(project(canonical_bytes, compact_rel=rel))
    if regenerated != on_disk:
        return False, ("projection out of date: regenerating from the canonical does not "
                       "reproduce the on-disk file byte-for-byte — regenerate")
    return True, "ok"


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _default_compact_path(canonical_path: str) -> str:
    schemas_dir = os.path.dirname(os.path.abspath(canonical_path))
    name = os.path.basename(canonical_path).replace(".schema.json", "")
    return os.path.join(schemas_dir, "compact", f"{name}.compact.schema.json")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="WP-1b compact-projection generator (annotation-stripped JSON Schema).")
    ap.add_argument("canonical", help="path to the canonical schemas/<name>.schema.json")
    ap.add_argument("-o", "--out", default=None,
                    help="output path (default: schemas/compact/<name>.compact.schema.json)")
    ap.add_argument("--check", action="store_true",
                    help="verify lockstep only (no write); exit !=0 if the projection drifted")
    args = ap.parse_args(argv)

    compact_path = args.out or _default_compact_path(args.canonical)

    if args.check:
        ok, reason = check_lockstep(args.canonical, compact_path)
        print(f"project_schema: {'OK' if ok else 'DRIFT'} — {reason}")
        return 0 if ok else 1

    with open(args.canonical, "rb") as fh:
        canonical_bytes = fh.read()
    compact = project(canonical_bytes, compact_rel=os.path.basename(compact_path))
    os.makedirs(os.path.dirname(compact_path) or ".", exist_ok=True)
    with open(compact_path, "w", encoding="utf-8") as fh:
        fh.write(serialize(compact))
    canonical_n = len(canonical_bytes)
    compact_n = len(serialize(compact).encode("utf-8"))
    print(f"project_schema: wrote {compact_path} "
          f"({canonical_n} -> {compact_n} B, -{canonical_n - compact_n})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
