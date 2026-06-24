"""Unit tests for adoption_status.py (stdlib unittest).

Hermetic tempdir trees for most cases; one assertion against the real aidazi
framework repo (must detect wrong workspace) and one against examples/minimal-greenfield.
"""

import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_VALIDATORS_DIR = os.path.dirname(_TESTS_DIR)
if _VALIDATORS_DIR not in sys.path:
    sys.path.insert(0, _VALIDATORS_DIR)

import adoption_status as ads  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(_VALIDATORS_DIR))
_FRAMEWORK_ROOT = _REPO_ROOT
_MINIMAL_GREENFIELD = os.path.join(_REPO_ROOT, "examples", "minimal-greenfield")


class _RootBuilder(unittest.TestCase):
    def _mk(self, files: dict) -> str:
        root = tempfile.mkdtemp(prefix="ads-")
        self.addCleanup(self._rmtree, root)
        for rel, content in files.items():
            full = os.path.join(root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(content)
        return root

    @staticmethod
    def _rmtree(path: str) -> None:
        import shutil

        shutil.rmtree(path, ignore_errors=True)


class FrameworkRepoDetectionTests(unittest.TestCase):
    def test_aidazi_framework_repo_detected(self):
        r = ads.validate_adoption(_FRAMEWORK_ROOT)
        self.assertTrue(r.framework_repo)
        self.assertFalse(r.ok)
        self.assertIn("framework repo", r.render())

    def test_minimal_adopter_not_framework(self):
        root = _RootBuilder()._mk({
            "AGENTS.md": "# My App\nproject_name: my-app\n",
            "charter.yaml": "mission:\n  id: M1\n  goal: test\n",
        })
        r = ads.validate_adoption(root)
        self.assertFalse(r.framework_repo)


class RuntimeSectionTests(_RootBuilder):
    def test_runtime_paths_in_render(self):
        root = self._mk({"AGENTS.md": "# app\n"})
        text = ads.validate_adoption(root).render()
        self.assertIn(".runs/<loop_id>/", text)
        self.assertIn("loops.json", text)
        self.assertIn("RUNTIME", text)


class GitignoreTests(_RootBuilder):
    def test_gitignore_runs_detected(self):
        root = self._mk({
            "AGENTS.md": "# app\n",
            ".gitignore": ".runs/\n.env.local\n",
        })
        r = ads.validate_adoption(root)
        labels = [c.label for c in r.checks if c.status == "ok"]
        self.assertIn("gitignore .runs/", labels)


class WriteReadinessTests(_RootBuilder):
    def test_write_readiness_creates_file(self):
        root = self._mk({"AGENTS.md": "# app\n"})
        out = os.path.join(root, "docs", "current", "adoption-readiness.md")
        r = ads.validate_adoption(root)
        ads.write_readiness_snapshot(r, out)
        self.assertTrue(os.path.isfile(out))
        with open(out, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("adoption status", body)
        self.assertIn("Regenerate:", body)


class MinimalGreenfieldTests(unittest.TestCase):
    def test_minimal_greenfield_is_adopter_not_framework(self):
        r = ads.validate_adoption(_MINIMAL_GREENFIELD)
        self.assertFalse(r.framework_repo)
        self.assertIn("adopter repo", r.render())

    def test_minimal_greenfield_wiring_passes_with_harness(self):
        r = ads.validate_adoption(_MINIMAL_GREENFIELD, harness="claude_code")
        wiring = [c for c in r.checks if "harness root-file" in c.label]
        self.assertTrue(wiring)
        self.assertEqual(wiring[0].status, "ok")


class SubmoduleLayoutTests(_RootBuilder):
    def test_aidazi_submodule_engine_kit_ok(self):
        root = self._mk({
            "AGENTS.md": "# my-app\nproject_name: my-app\n",
            "charter.yaml": "mission:\n  id: M1\n  goal: test\n",
            "aidazi/engine-kit/orchestrator/driver.py": "# driver stub\n",
        })
        r = ads.validate_adoption(root)
        labels = [c.label for c in r.checks if c.status == "ok" and "engine-kit" in c.label]
        self.assertTrue(labels)


class MainExitCodeTests(_RootBuilder):
    def test_framework_repo_exits_nonzero(self):
        code = ads.main([_FRAMEWORK_ROOT])
        self.assertEqual(code, 1)

    def test_missing_required_exits_nonzero(self):
        root = self._mk({"AGENTS.md": "# only agents\n"})
        code = ads.main([root])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
