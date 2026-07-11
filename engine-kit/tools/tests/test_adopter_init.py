"""Cluster-2 tests for adopter_init.py (design §4 / §10).

Proves the scaffolding CORE: answers -> a tree that makes all four adoption validators GREEN,
plus the fail-closed invariants I1 (pure build_artifacts), I2 (guarded dest / never the
framework repo), I3 (never auto-confirm the gate-1 signature).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
import adopter_init as ai  # noqa: E402

_VALIDATORS_DIR = os.path.join(os.path.dirname(_TOOLS_DIR), "validators")
if _VALIDATORS_DIR not in sys.path:
    sys.path.insert(0, _VALIDATORS_DIR)
import adopter_wiring_validator as awv  # noqa: E402
import charter_validator  # noqa: E402
import control_plane_validator  # noqa: E402
import adoption_status  # noqa: E402

_FRAMEWORK_ROOT = os.path.dirname(os.path.dirname(_TOOLS_DIR))  # <root>/engine-kit/tools -> <root>
_CANARY_ANSWERS = os.path.join(_FRAMEWORK_ROOT, "examples", "adopter-init-canary", "answers.json")


def _load_plan():
    return ai.load_answers(_CANARY_ANSWERS, _FRAMEWORK_ROOT)


class BuildArtifactsPurityTests(unittest.TestCase):
    def test_build_artifacts_is_deterministic_and_no_framework_arg(self):
        # I1: build_artifacts takes PRE-LOADED templates (not framework_root), so it structurally
        # cannot read the framework tree; and it is deterministic.
        plan = _load_plan()
        templates = ai.load_templates(_FRAMEWORK_ROOT)
        a1 = ai.build_artifacts(plan, templates)
        a2 = ai.build_artifacts(plan, templates)
        self.assertEqual(a1, a2)
        # the required artifacts are present in the pure map
        for rel in ("charter.yaml", "AGENTS.md", "CLAUDE.md",
                    os.path.join(".cursor", "rules", "00-aidazi-governance.mdc"),
                    "docs/current/adoption-state.md", ".gitignore"):
            self.assertIn(rel, a1, msg=f"missing artifact {rel}")

    def test_charter_artifact_is_schema_valid(self):
        plan = _load_plan()
        templates = ai.load_templates(_FRAMEWORK_ROOT)
        artifacts = ai.build_artifacts(plan, templates)
        with tempfile.TemporaryDirectory(prefix="ai-charter-") as d:
            path = os.path.join(d, "charter.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(artifacts["charter.yaml"])
            rep = charter_validator.validate_file(path)
            self.assertTrue(rep.ok, msg="\n".join(str(e) for e in rep.errors))

    def test_i3_unsigned_brief_omits_the_token(self):
        # I3: with confirmed_by_human false the brief body must NOT carry the confirmed token.
        data = json.load(open(_CANARY_ANSWERS))
        data["research_brief"]["confirmed_by_human"] = False
        with tempfile.TemporaryDirectory(prefix="ai-unsigned-") as d:
            apath = os.path.join(d, "a.json")
            json.dump(data, open(apath, "w"))
            plan = ai.load_answers(apath, _FRAMEWORK_ROOT)
            templates = ai.load_templates(_FRAMEWORK_ROOT)
            artifacts = ai.build_artifacts(plan, templates)
            brief = next(v for k, v in artifacts.items() if k.startswith("docs/research-briefs/"))
            self.assertNotIn("confirmed_by_human: true", brief)
            self.assertIn("confirmed_by_human: false", brief)


class GuardTests(unittest.TestCase):
    def test_i2_refuses_framework_repo(self):
        with self.assertRaises(ai.InitError):
            ai.assert_writable_dest(_FRAMEWORK_ROOT, _FRAMEWORK_ROOT)

    def test_i2_refuses_dest_nested_in_framework(self):
        nested = os.path.join(_FRAMEWORK_ROOT, "engine-kit", "tools", "nope-adopter")
        with self.assertRaises(ai.InitError):
            ai.assert_writable_dest(nested, _FRAMEWORK_ROOT)

    def test_i2_allows_external_dest(self):
        with tempfile.TemporaryDirectory(prefix="ai-ok-") as d:
            ai.assert_writable_dest(os.path.join(d, "acme"), _FRAMEWORK_ROOT)  # no raise

    def test_materialize_guards_before_write(self):
        # materialize must refuse a framework-repo dest without writing.
        plan = _load_plan()
        templates = ai.load_templates(_FRAMEWORK_ROOT)
        artifacts = ai.build_artifacts(plan, templates)
        with self.assertRaises(ai.InitError):
            ai.materialize(artifacts, _FRAMEWORK_ROOT, _FRAMEWORK_ROOT)


class ScaffoldGreenTests(unittest.TestCase):
    def _scaffold(self, tmp, answers=_CANARY_ANSWERS, force=False):
        dest = os.path.join(tmp, "acme")
        rc = ai.main([dest, "--answers", answers] + (["--force"] if force else []))
        return dest, rc

    def test_scratch_dir_all_four_validators_green(self):
        with tempfile.TemporaryDirectory(prefix="ai-green-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0, "adopter_init did not exit 0 (green)")
            # Independently re-run each validator against the produced tree (design C2 obligation a).
            self.assertTrue(charter_validator.validate_file(os.path.join(dest, "charter.yaml")).ok)
            self.assertTrue(awv.validate_root(dest).ok)
            self.assertTrue(control_plane_validator.validate_root(dest).ok)
            self.assertTrue(adoption_status.validate_adoption(dest).ok)
            # cursor role => a valid .cursor/rules that passes the C1 validator.
            self.assertTrue(os.path.isfile(
                os.path.join(dest, ".cursor", "rules", "00-aidazi-governance.mdc")))
            self.assertIn("cursor", awv.validate_root(dest).targets)
            # framework mounted under aidazi/, NOT the dest root (I2 non-collision).
            self.assertTrue(os.path.isfile(
                os.path.join(dest, "aidazi", "engine-kit", "orchestrator", "driver.py")))
            self.assertFalse(adoption_status.is_framework_repo(dest))

    def test_idempotent_force_rerun_stays_green_no_clobber(self):
        with tempfile.TemporaryDirectory(prefix="ai-idem-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0)
            # hand-edit the charter, then re-run WITHOUT --overwrite: charter must be preserved.
            charter_path = os.path.join(dest, "charter.yaml")
            with open(charter_path, "a", encoding="utf-8") as fh:
                fh.write("\n# human edit\n")
            rc2 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc2, 0)
            self.assertIn("# human edit", ai._read_text(charter_path))

    def test_unsigned_brief_scaffolds_but_not_green(self):
        data = json.load(open(_CANARY_ANSWERS))
        data["research_brief"]["confirmed_by_human"] = False
        with tempfile.TemporaryDirectory(prefix="ai-unsigned-") as tmp:
            apath = os.path.join(tmp, "a.json")
            json.dump(data, open(apath, "w"))
            dest, rc = self._scaffold(tmp, answers=apath)
            self.assertEqual(rc, 2, "unsigned brief must be NOT green (exit 2), never fabricated")
            self.assertFalse(adoption_status.validate_adoption(dest).ok)


class CliContractTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="ai-dry-") as tmp:
            dest = os.path.join(tmp, "acme")
            rc = ai.main([dest, "--answers", _CANARY_ANSWERS, "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(dest), "dry-run must not create the dest")

    def test_bad_answers_refused(self):
        with tempfile.TemporaryDirectory(prefix="ai-bad-") as tmp:
            apath = os.path.join(tmp, "bad.json")
            json.dump({"adopter_name": "x"}, open(apath, "w"))  # missing required keys
            rc = ai.main([os.path.join(tmp, "acme"), "--answers", apath])
            self.assertEqual(rc, 3, "invalid answers must be refused (exit 3)")

    def test_framework_repo_dest_refused_exit3(self):
        rc = ai.main([_FRAMEWORK_ROOT, "--answers", _CANARY_ANSWERS])
        self.assertEqual(rc, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
