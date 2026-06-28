import os
import sys
import tempfile
import unittest

_THIS = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.abspath(os.path.join(_THIS, "..", ".."))
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)

import effective_role_config as erc  # noqa: E402


class EffectiveSkillsTests(unittest.TestCase):
    def test_omitted_skills_inherit_framework_defaults(self):
        config = erc.resolve_role_config({"tooling": {"review": {}}}, "review")
        self.assertEqual([s.id for s in config.skills], ["code-review-excellence"])
        self.assertTrue(config.skill_set_hash)

    def test_extend_keeps_defaults_and_adds_local(self):
        with tempfile.TemporaryDirectory() as root:
            skill_dir = os.path.join(root, "skills", "local-lens")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
                fh.write("---\nname: local-lens\ndescription: test\n---\n")
            charter = {"tooling": {"review": {"skills": {
                "mode": "extend", "items": [{"id": "local-lens", "path": "skills/local-lens"}],
            }}}}
            config = erc.resolve_role_config(charter, "review", adopter_root=root)
            self.assertEqual(
                [s.id for s in config.skills],
                ["code-review-excellence", "local-lens"],
            )

    def test_replace_and_disable(self):
        replaced = erc.resolve_role_config(
            {"tooling": {"acceptance": {"skills": ["advanced-evaluation"]}}},
            "acceptance",
        )
        self.assertEqual([s.id for s in replaced.skills], ["advanced-evaluation"])
        disabled = erc.resolve_role_config(
            {"tooling": {"acceptance": {"skills": {"mode": "disable"}}}},
            "acceptance",
        )
        self.assertEqual(disabled.skills, ())

    def test_acceptance_defaults_to_hybrid(self):
        config = erc.resolve_role_config(
            {"tooling": {"acceptance": {}}}, "acceptance")
        self.assertEqual(
            config.acceptance_functional["interaction_mode"], "hybrid")
        self.assertEqual(
            config.acceptance_functional["target_environment"], "local")

    def test_skill_hash_changes_with_content(self):
        with tempfile.TemporaryDirectory() as root:
            skill_dir = os.path.join(root, "skills", "local-lens")
            os.makedirs(skill_dir)
            path = os.path.join(skill_dir, "SKILL.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("---\nname: local-lens\ndescription: one\n---\n")
            charter = {"tooling": {"review": {"skills": {
                "mode": "replace",
                "items": [{"id": "local-lens", "path": "skills/local-lens"}],
            }}}}
            first = erc.resolve_role_config(charter, "review", adopter_root=root)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("changed\n")
            second = erc.resolve_role_config(charter, "review", adopter_root=root)
            self.assertNotEqual(first.skill_set_hash, second.skill_set_hash)


if __name__ == "__main__":
    unittest.main()
