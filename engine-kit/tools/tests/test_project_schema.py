"""Tests for the WP-1b compact-projection generator (stdlib unittest + optional jsonschema).

Two layers:
  1. UNIT — strip_annotations is position-aware (drops annotation keywords ONLY in schema
     position; preserves a property literally NAMED an annotation keyword; copies enum/const
     DATA verbatim; idempotent), project() embeds the lockstep anchor, check_lockstep detects
     drift.
  2. REAL projections — the 3 checked-in compact schemas (review/acceptance/charter) are
     metaschema-valid, machine-key-equal to strip_annotations(canonical), carry no surviving
     annotation keyword, and are in lockstep with their canonical.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_TESTS_DIR)
_REPO = os.path.dirname(os.path.dirname(_TOOLS_DIR))   # engine-kit/tools -> engine-kit -> repo
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import project_schema as ps  # noqa: E402

try:
    from jsonschema.validators import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

_CANONICAL = ("review-verdict", "acceptance-verdict", "mission-charter")


class StripAnnotationsUnitTests(unittest.TestCase):
    def _demo(self):
        # A schema that exercises every hazard: top-level annotations, a property literally
        # NAMED "description"/"title", a nested schema annotation, and enum DATA that itself
        # contains a "description" KEY (must be copied verbatim, NOT treated as a keyword).
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "x://demo.json",
            "title": "DROP", "description": "DROP", "$comment": "DROP",
            "examples": [{"description": "DROP (examples is an annotation)"}],
            "type": "object",
            "required": ["description", "title"],
            "additionalProperties": False,
            "properties": {
                "description": {"type": "string", "description": "DROP inner",
                                "enum": ["x", {"k": "v", "description": "KEEP enum data"}]},
                "title": {"const": "fixed"},
                "nested": {"allOf": [{"type": "integer", "title": "DROP"}]},
            },
        }

    def test_drops_annotation_keywords_in_schema_position(self):
        out = ps.strip_annotations(self._demo())
        for k in ("title", "description", "$comment", "examples"):
            self.assertNotIn(k, out)
        self.assertNotIn("description", out["properties"]["description"])  # inner annotation
        self.assertNotIn("title", out["properties"]["nested"]["allOf"][0])

    def test_preserves_property_named_like_annotation(self):
        out = ps.strip_annotations(self._demo())
        # The PROPERTIES named "description"/"title" survive (keys under `properties`).
        self.assertIn("description", out["properties"])
        self.assertIn("title", out["properties"])

    def test_preserves_machine_keys_and_enum_data_verbatim(self):
        out = ps.strip_annotations(self._demo())
        self.assertEqual(out["required"], ["description", "title"])
        self.assertIs(out["additionalProperties"], False)
        self.assertEqual(out["properties"]["title"]["const"], "fixed")
        # enum DATA — including a dict value carrying a "description" KEY — is verbatim.
        self.assertEqual(out["properties"]["description"]["enum"][1],
                         {"k": "v", "description": "KEEP enum data"})

    def test_idempotent(self):
        once = ps.strip_annotations(self._demo())
        self.assertEqual(ps.strip_annotations(once), once)

    def test_does_not_mutate_input(self):
        demo = self._demo()
        snap = json.loads(json.dumps(demo))
        ps.strip_annotations(demo)
        self.assertEqual(demo, snap)


class ProjectAndLockstepTests(unittest.TestCase):
    def test_project_embeds_lockstep_anchor_and_distinct_id(self):
        canonical = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                     "$id": "https://aidazi.framework/schemas/foo.schema.json",
                     "title": "Foo", "type": "object"}
        cb = (json.dumps(canonical, indent=2) + "\n").encode("utf-8")
        compact = ps.project(cb, compact_rel="foo.compact.schema.json")
        self.assertNotIn("title", compact)
        self.assertEqual(compact["x-canonical-sha256"], hashlib.sha256(cb).hexdigest())
        self.assertEqual(compact["x-canonical-source"], "foo.schema.json")
        self.assertNotEqual(compact["$id"], canonical["$id"])     # distinct -> no collision
        self.assertIn("compact", compact["$id"])

    def test_check_lockstep_ok_then_detects_canonical_drift(self):
        with tempfile.TemporaryDirectory() as d:
            canon = os.path.join(d, "foo.schema.json")
            comp = os.path.join(d, "foo.compact.schema.json")
            with open(canon, "wb") as fh:
                fh.write(b'{"$id":"x://foo.json","title":"T","type":"string"}')
            with open(canon, "rb") as fh:
                cb = fh.read()
            with open(comp, "w", encoding="utf-8") as fh:
                fh.write(ps.serialize(ps.project(cb, compact_rel="foo.compact.schema.json")))
            ok, _ = ps.check_lockstep(canon, comp)
            self.assertTrue(ok)
            # mutate the canonical -> embedded sha is now stale -> lockstep FAILS.
            with open(canon, "wb") as fh:
                fh.write(b'{"$id":"x://foo.json","title":"T","type":"integer"}')
            ok2, reason = ps.check_lockstep(canon, comp)
            self.assertFalse(ok2)
            self.assertIn("x-canonical-sha256", reason)

    def test_check_lockstep_detects_handedited_projection(self):
        with tempfile.TemporaryDirectory() as d:
            canon = os.path.join(d, "foo.schema.json")
            comp = os.path.join(d, "foo.compact.schema.json")
            with open(canon, "wb") as fh:
                fh.write(b'{"$id":"x://foo.json","type":"string","minLength":1}')
            with open(canon, "rb") as fh:
                cb = fh.read()
            proj = ps.project(cb, compact_rel="foo.compact.schema.json")
            with open(comp, "w", encoding="utf-8") as fh:
                fh.write(ps.serialize(proj))
            # tamper a MACHINE key in the on-disk projection (sha still matches canonical).
            tampered = dict(proj); tampered["minLength"] = 99
            with open(comp, "w", encoding="utf-8") as fh:
                fh.write(ps.serialize(tampered))
            ok, reason = ps.check_lockstep(canon, comp)
            self.assertFalse(ok)
            self.assertIn("byte-for-byte", reason)


class RealProjectionsTests(unittest.TestCase):
    """The 3 checked-in projections are valid, machine-equivalent, and in lockstep."""

    def _paths(self, name):
        return (os.path.join(_REPO, "schemas", f"{name}.schema.json"),
                os.path.join(_REPO, "schemas", "compact", f"{name}.compact.schema.json"))

    def test_projections_exist_and_in_lockstep(self):
        for name in _CANONICAL:
            canon, comp = self._paths(name)
            self.assertTrue(os.path.isfile(comp), f"{name}: compact projection missing")
            ok, reason = ps.check_lockstep(canon, comp)
            self.assertTrue(ok, f"{name}: {reason}")

    def test_projections_machine_key_equal_and_annotation_free(self):
        for name in _CANONICAL:
            canon, comp = self._paths(name)
            with open(canon, "rb") as fh:
                expect = ps.strip_annotations(json.loads(fh.read()))
            with open(comp, encoding="utf-8") as fh:
                compact = json.load(fh)
            core = {k: v for k, v in compact.items()
                    if k not in ("x-canonical-source", "x-canonical-sha256")}
            expect["$id"] = compact["$id"]      # $id is intentionally re-pointed
            self.assertEqual(core, expect, f"{name}: machine keys diverge from canonical")
            # re-stripping is a no-op -> no annotation keyword survived anywhere.
            self.assertEqual(ps.strip_annotations(core), core, f"{name}: annotations remain")

    def test_projections_metaschema_valid(self):
        if Draft202012Validator is None:
            self.skipTest("jsonschema not installed")
        for name in _CANONICAL:
            _canon, comp = self._paths(name)
            with open(comp, encoding="utf-8") as fh:
                Draft202012Validator.check_schema(json.load(fh))


if __name__ == "__main__":
    unittest.main(verbosity=2)
