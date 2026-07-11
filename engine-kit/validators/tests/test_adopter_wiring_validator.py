"""Unit tests for adopter_wiring_validator (stdlib unittest; only the validator's own
PyYAML runtime dep).

Each test asserts the verdict (ok / not ok) AND the stable rule id that fired, so a future
change that swaps one outcome for another is caught. Adopter roots are built hermetically in
tempdirs (the validator's input is a *tree*; symlink / absolute-path cases are not portably
committable), plus one assertion against the shipped real example tree
(examples/minimal-greenfield) to prove the canonical wiring the framework ships actually PASSes.
"""

import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_VALIDATORS_DIR = os.path.dirname(_TESTS_DIR)
if _VALIDATORS_DIR not in sys.path:
    sys.path.insert(0, _VALIDATORS_DIR)

import adopter_wiring_validator as awv  # noqa: E402

# Repo root = .../aidazi ; the worked example lives under examples/minimal-greenfield.
_REPO_ROOT = os.path.dirname(os.path.dirname(_VALIDATORS_DIR))
_MINIMAL_GREENFIELD = os.path.join(_REPO_ROOT, "examples", "minimal-greenfield")


class _RootBuilder(unittest.TestCase):
    """Base class: build a throwaway adopter root from a {relpath: content} map."""

    def _mk(self, files: dict, links: dict | None = None) -> str:
        root = tempfile.mkdtemp(prefix="awv-")
        self.addCleanup(self._rmtree, root)
        for rel, content in files.items():
            full = os.path.join(root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(content)
        for rel, target in (links or {}).items():
            full = os.path.join(root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            os.symlink(target, full)
        return root

    @staticmethod
    def _rmtree(path: str) -> None:
        import shutil

        shutil.rmtree(path, ignore_errors=True)


class ClaudeCodePassTests(_RootBuilder):
    def test_canonical_wiring_passes(self):
        root = self._mk({"CLAUDE.md": "@AGENTS.md\n", "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertTrue(r.ok, msg=r.render())
        self.assertEqual(r.targets, ["claude_code"])
        self.assertEqual(r.errors, [])

    def test_dot_slash_relative_passes(self):
        root = self._mk({"CLAUDE.md": "@./AGENTS.md\n", "AGENTS.md": "# chain\n"})
        self.assertTrue(awv.validate_root(root, harness="claude_code").ok)

    def test_extra_human_content_and_other_imports_pass(self):
        claude = (
            "# My project notes\n\nLoad the chain:\n@AGENTS.md\n\n"
            "Also see @docs/style-guide.md for conventions.\n"
        )
        root = self._mk({"CLAUDE.md": claude, "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertTrue(r.ok, msg=r.render())

    def test_shipped_minimal_greenfield_example_passes(self):
        # The real committed example must be correctly wired for Claude Code.
        self.assertTrue(os.path.isfile(os.path.join(_MINIMAL_GREENFIELD, "CLAUDE.md")))
        r = awv.validate_root(_MINIMAL_GREENFIELD, harness="claude_code")
        self.assertTrue(r.ok, msg=r.render())


class ClaudeCodeFailTests(_RootBuilder):
    def test_bare_agents_no_claude_fails(self):
        root = self._mk({"AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok)
        self.assertIn("claude_missing_claude_md", r.rules_fired)

    def test_claude_without_wiring_line_fails(self):
        root = self._mk({"CLAUDE.md": "# notes, no import\n", "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok)
        self.assertIn("claude_missing_wiring_line", r.rules_fired)

    def test_parent_escape_fails(self):
        root = self._mk({"CLAUDE.md": "@../AGENTS.md\n", "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok)
        self.assertIn("claude_wiring_parent_escape", r.rules_fired)

    def test_absolute_path_fails(self):
        root = self._mk({"CLAUDE.md": "@/etc/AGENTS.md\n", "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok)
        self.assertIn("claude_wiring_absolute_path", r.rules_fired)

    def test_subdirectory_import_not_same_root_fails(self):
        root = self._mk(
            {
                "CLAUDE.md": "@docs/AGENTS.md\n",
                "AGENTS.md": "# chain\n",
                "docs/AGENTS.md": "# other\n",
            }
        )
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok)
        self.assertIn("claude_wiring_not_same_root", r.rules_fired)

    def test_import_only_in_code_fence_is_malformed(self):
        claude = "Wire it like:\n\n```\n@AGENTS.md\n```\n"
        root = self._mk({"CLAUDE.md": claude, "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok)
        self.assertIn("claude_wiring_malformed", r.rules_fired)

    def test_wiring_present_but_agents_missing_fails(self):
        root = self._mk({"CLAUDE.md": "@AGENTS.md\n"})  # no AGENTS.md
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok)
        self.assertIn("claude_missing_agents_md", r.rules_fired)

    def test_symlinked_claude_md_is_redirect_fail(self):
        real = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, dir=tempfile.gettempdir()
        )
        real.write("@AGENTS.md\n")
        real.close()
        self.addCleanup(os.unlink, real.name)
        root = self._mk({"AGENTS.md": "# chain\n"}, links={"CLAUDE.md": real.name})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok)
        self.assertIn("claude_wiring_symlink", r.rules_fired)

    def test_symlinked_agents_md_is_redirect_fail(self):
        real = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, dir=tempfile.gettempdir()
        )
        real.write("# chain elsewhere\n")
        real.close()
        self.addCleanup(os.unlink, real.name)
        root = self._mk({"CLAUDE.md": "@AGENTS.md\n"}, links={"AGENTS.md": real.name})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok)
        self.assertIn("claude_wiring_symlink", r.rules_fired)


class ChainDuplicationTests(_RootBuilder):
    def test_claude_recopies_chain_is_error(self):
        # §1.1 MUST NOT: CLAUDE.md must import only @AGENTS.md, never re-copy the chain.
        claude = (
            "@AGENTS.md\n"
            "@aidazi/governance/constitution.md\n"  # dual entry point — drift risk
        )
        root = self._mk({"CLAUDE.md": claude, "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())  # now blocks
        self.assertIn("claude_chain_duplicated", r.rules_fired)


class EscapeAlongsideValidTests(_RootBuilder):
    """A valid @AGENTS.md must NOT excuse an additional escaping AGENTS.md import."""

    def test_valid_plus_parent_escape_fails(self):
        root = self._mk(
            {"CLAUDE.md": "@AGENTS.md\n@../AGENTS.md\n", "AGENTS.md": "# chain\n"}
        )
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())
        self.assertIn("claude_wiring_parent_escape", r.rules_fired)

    def test_valid_plus_absolute_fails(self):
        root = self._mk(
            {"CLAUDE.md": "@AGENTS.md\n@/etc/AGENTS.md\n", "AGENTS.md": "# chain\n"}
        )
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())
        self.assertIn("claude_wiring_absolute_path", r.rules_fired)

    def test_valid_plus_subdir_fails(self):
        root = self._mk(
            {
                "CLAUDE.md": "@AGENTS.md\n@docs/AGENTS.md\n",
                "AGENTS.md": "# chain\n",
                "docs/AGENTS.md": "# other\n",
            }
        )
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())
        self.assertIn("claude_wiring_not_same_root", r.rules_fired)

    # Windows-style (backslash) escapes must be recognized on POSIX too, not silently dropped
    # by a '/'-only basename filter (Codex round-2 MAJOR).
    def test_valid_plus_backslash_parent_fails(self):
        root = self._mk(
            {"CLAUDE.md": "@AGENTS.md\n@..\\AGENTS.md\n", "AGENTS.md": "# chain\n"}
        )
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())
        self.assertIn("claude_wiring_parent_escape", r.rules_fired)

    def test_valid_plus_backslash_drive_absolute_fails(self):
        root = self._mk(
            {"CLAUDE.md": "@AGENTS.md\n@C:\\tmp\\AGENTS.md\n", "AGENTS.md": "# chain\n"}
        )
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())
        self.assertIn("claude_wiring_absolute_path", r.rules_fired)

    def test_valid_plus_backslash_subdir_fails(self):
        root = self._mk(
            {"CLAUDE.md": "@AGENTS.md\n@docs\\AGENTS.md\n", "AGENTS.md": "# chain\n"}
        )
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())
        self.assertIn("claude_wiring_not_same_root", r.rules_fired)


class InlineCodeTests(_RootBuilder):
    """@AGENTS.md inside inline code is inert — it must NOT be a live import (no false pass)."""

    def test_single_backtick_inline_does_not_pass(self):
        root = self._mk({"CLAUDE.md": "Wire with `@AGENTS.md`.\n", "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())

    def test_double_backtick_inline_does_not_pass(self):
        # A double-backtick span (used when the code contains a backtick) must also be inert.
        root = self._mk({"CLAUDE.md": "``@AGENTS.md``\n", "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())

    def test_real_import_after_inline_mention_passes(self):
        # An inline mention plus a real line-level import is still valid wiring.
        claude = "Reference `@AGENTS.md` in prose, then actually wire it:\n@AGENTS.md\n"
        root = self._mk({"CLAUDE.md": claude, "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertTrue(r.ok, msg=r.render())


class FencedCodeTests(_RootBuilder):
    def test_four_backtick_fence_wrapping_inner_fence_is_inert(self):
        # A 3-backtick line must NOT close a 4-backtick fence, so the @AGENTS.md inside stays
        # inert and the wiring must FAIL (no false pass).
        claude = "````\n```\n@AGENTS.md\n```\n````\n"
        root = self._mk({"CLAUDE.md": claude, "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())

    def test_at_agents_inside_four_backtick_fence_is_inert(self):
        claude = "````text\n@AGENTS.md\n````\n"
        root = self._mk({"CLAUDE.md": claude, "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())

    def test_tilde_fence_does_not_close_backtick_fence(self):
        # A ~~~ line inside a ``` fence must not close it; @AGENTS.md stays inert.
        claude = "```\n~~~\n@AGENTS.md\n~~~\n```\n"
        root = self._mk({"CLAUDE.md": claude, "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertFalse(r.ok, msg=r.render())

    def test_fenced_chain_example_does_not_false_fail(self):
        # Valid wiring plus a FENCED example of the forbidden chain import must still PASS —
        # the duplication check ignores fenced/inline-code content.
        claude = (
            "@AGENTS.md\n\nDo NOT re-copy the chain like this:\n\n"
            "```\n@aidazi/governance/constitution.md\n```\n"
        )
        root = self._mk({"CLAUDE.md": claude, "AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="claude_code")
        self.assertTrue(r.ok, msg=r.render())
        self.assertNotIn("claude_chain_duplicated", r.rules_fired)


class CodexTests(_RootBuilder):
    def test_codex_bare_agents_passes_without_claude(self):
        root = self._mk({"AGENTS.md": "# chain\n"})  # no CLAUDE.md, intentionally
        r = awv.validate_root(root, harness="codex")
        self.assertTrue(r.ok, msg=r.render())
        self.assertEqual(r.targets, ["codex"])

    def test_codex_missing_agents_fails(self):
        root = self._mk({"CLAUDE.md": "@AGENTS.md\n"})  # no AGENTS.md
        r = awv.validate_root(root, harness="codex")
        self.assertFalse(r.ok)
        self.assertIn("codex_missing_agents_md", r.rules_fired)

    def test_codex_empty_agents_fails(self):
        root = self._mk({"AGENTS.md": "   \n"})
        r = awv.validate_root(root, harness="codex")
        self.assertFalse(r.ok)
        self.assertIn("codex_missing_agents_md", r.rules_fired)


class CursorTests(_RootBuilder):
    _MDC = "---\ndescription: aidazi governance\nalwaysApply: true\n---\nLoad AGENTS.md.\n"

    def test_cursor_single_file_rules_passes(self):
        # legacy single-file .cursor/rules, non-empty => PASS.
        root = self._mk({"AGENTS.md": "# chain\n", ".cursor/rules": "load AGENTS.md\n"})
        r = awv.validate_root(root, harness="cursor")
        self.assertTrue(r.ok, msg=r.render())
        self.assertEqual(r.targets, ["cursor"])

    def test_cursor_mdc_dir_passes(self):
        # modern .cursor/rules/ directory with a non-empty *.mdc rule => PASS.
        root = self._mk({"AGENTS.md": "# chain\n", ".cursor/rules/00-gov.mdc": self._MDC})
        r = awv.validate_root(root, harness="cursor")
        self.assertTrue(r.ok, msg=r.render())

    def test_cursor_missing_rules_fails(self):
        root = self._mk({"AGENTS.md": "# chain\n"})  # no .cursor/rules
        r = awv.validate_root(root, harness="cursor")
        self.assertFalse(r.ok)
        self.assertIn("cursor_missing_rules", r.rules_fired)

    def test_cursor_empty_file_rules_fails(self):
        root = self._mk({"AGENTS.md": "# chain\n", ".cursor/rules": "   \n"})
        r = awv.validate_root(root, harness="cursor")
        self.assertFalse(r.ok)
        self.assertIn("cursor_rules_invalid", r.rules_fired)

    def test_cursor_dir_without_nonempty_mdc_fails(self):
        # an empty *.mdc plus a non-.mdc file => no valid rule => FAIL.
        root = self._mk(
            {"AGENTS.md": "# chain\n", ".cursor/rules/00-gov.mdc": "  \n",
             ".cursor/rules/README.txt": "not a rule\n"}
        )
        r = awv.validate_root(root, harness="cursor")
        self.assertFalse(r.ok)
        self.assertIn("cursor_rules_invalid", r.rules_fired)

    def test_cursor_rules_symlink_escape_fails(self):
        # .cursor/rules is a symlink pointing outside the root => redirect, rejected.
        outside = tempfile.mkdtemp(prefix="awv-outside-")
        self.addCleanup(self._rmtree, outside)
        target = os.path.join(outside, "rules")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("load AGENTS.md\n")
        root = self._mk({"AGENTS.md": "# chain\n"}, links={".cursor/rules": target})
        r = awv.validate_root(root, harness="cursor")
        self.assertFalse(r.ok)
        self.assertIn("cursor_rules_invalid", r.rules_fired)


class CursorAndUnspecifiedWarnTests(_RootBuilder):
    def test_cursor_target_without_rules_fails(self):
        # A bare AGENTS.md is NOT Cursor wiring: a cursor target with no .cursor/rules now FAILs
        # (blocking) rather than WARNs, so "validators green" actually proves Cursor wiring.
        root = self._mk({"AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="cursor")
        self.assertFalse(r.ok)  # FAIL => exit non-zero
        self.assertIn("cursor_missing_rules", r.rules_fired)

    def test_unspecified_harness_warns_exit0(self):
        root = self._mk({"AGENTS.md": "# chain\n"})  # no charter, no pin, no --harness
        r = awv.validate_root(root)
        self.assertTrue(r.ok)  # must not block a Codex-only adopter
        self.assertIn("harness_unspecified", r.rules_fired)

    def test_headless_harness_warns_exit0(self):
        root = self._mk({"AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="headless")
        self.assertTrue(r.ok)
        self.assertIn("harness_not_root_file", r.rules_fired)

    def test_unknown_harness_errors(self):
        root = self._mk({"AGENTS.md": "# chain\n"})
        r = awv.validate_root(root, harness="bogus")
        self.assertFalse(r.ok)
        self.assertIn("unknown_harness", r.rules_fired)


class CharterDerivationTests(_RootBuilder):
    _CHARTER_CLAUDE = (
        "schema_version: 1\n"
        "tooling:\n"
        "  dev:\n"
        "    harness: claude_code\n"
        "    provider: anthropic\n"
        "  review:\n"
        "    harness: headless\n"  # API role — must NOT impose a root file
        "    provider: deepseek\n"
    )

    def test_charter_claude_code_derives_target_and_passes(self):
        root = self._mk(
            {
                "CLAUDE.md": "@AGENTS.md\n",
                "AGENTS.md": "# chain\n",
                "charter.yaml": self._CHARTER_CLAUDE,
            }
        )
        r = awv.validate_root(root)  # no --harness: derive from charter
        self.assertTrue(r.ok, msg=r.render())
        self.assertEqual(r.targets, ["claude_code"])

    def test_charter_claude_code_without_claude_md_fails(self):
        root = self._mk({"AGENTS.md": "# chain\n", "charter.yaml": self._CHARTER_CLAUDE})
        r = awv.validate_root(root)
        self.assertFalse(r.ok)
        self.assertIn("claude_missing_claude_md", r.rules_fired)

    def test_legacy_agent_kind_is_honored(self):
        charter = "tooling:\n  dev:\n    agent_kind: codex\n"
        root = self._mk({"AGENTS.md": "# chain\n", "charter.yaml": charter})
        r = awv.validate_root(root)
        self.assertTrue(r.ok, msg=r.render())
        self.assertEqual(r.targets, ["codex"])

    def test_unparseable_charter_warns_then_unspecified(self):
        root = self._mk({"AGENTS.md": "# chain\n", "charter.yaml": "tooling: [oops\n"})
        r = awv.validate_root(root)
        self.assertTrue(r.ok)  # unreadable charter does not hard-fail this tool
        self.assertIn("charter_unreadable", r.rules_fired)
        self.assertIn("harness_unspecified", r.rules_fired)


class ExplicitHarnessPriorityTests(_RootBuilder):
    def test_explicit_harness_overrides_charter(self):
        # Charter says codex, but --harness claude_code targets claude for THIS invocation.
        charter = "tooling:\n  dev:\n    harness: codex\n"
        root = self._mk(
            {"CLAUDE.md": "@AGENTS.md\n", "AGENTS.md": "# chain\n", "charter.yaml": charter}
        )
        r = awv.validate_root(root, harness="claude_code")
        self.assertTrue(r.ok, msg=r.render())
        self.assertEqual(r.targets, ["claude_code"])


class ConflictTests(_RootBuilder):
    def _conflicting_root(self, extra: dict | None = None) -> str:
        files = {
            "AGENTS.md": "# chain\n",
            "CLAUDE.md": "@AGENTS.md\n",
            "charter.yaml": "tooling:\n  dev:\n    harness: claude_code\n",
            "docs/current/adoption-state.md": (
                "# adoption state\n<!-- adopter-root-harness: codex -->\n"
            ),
        }
        files.update(extra or {})
        return self._mk(files)

    def test_persistent_source_conflict_fails(self):
        root = self._conflicting_root()
        r = awv.validate_root(root)  # no --harness
        self.assertFalse(r.ok)
        self.assertIn("harness_conflict", r.rules_fired)
        self.assertEqual(r.targets, [])  # must NOT silently pick one

    def test_explicit_harness_does_not_mask_conflict(self):
        root = self._conflicting_root()
        r = awv.validate_root(root, harness="claude_code")
        # CLI picks the target, but the persistent-source conflict is still surfaced.
        self.assertIn("harness_conflict", r.rules_fired)
        self.assertFalse(r.ok)

    def test_agreeing_pin_and_charter_is_not_conflict(self):
        root = self._mk(
            {
                "AGENTS.md": "# chain\n",
                "CLAUDE.md": "@AGENTS.md\n",
                "charter.yaml": "tooling:\n  dev:\n    harness: claude_code\n",
                "docs/current/adoption-state.md": (
                    "<!-- adopter-root-harness: claude_code -->\n"
                ),
            }
        )
        r = awv.validate_root(root)
        self.assertTrue(r.ok, msg=r.render())
        self.assertEqual(r.targets, ["claude_code"])

    def test_partial_overlap_is_not_conflict(self):
        # charter {codex} and pin {codex, cursor} share 'codex' => NOT a contradiction.
        # The union is validated: codex PASSes (AGENTS.md present), cursor PASSes (valid
        # .cursor/rules present) => exit 0.
        root = self._mk(
            {
                "AGENTS.md": "# chain\n",
                ".cursor/rules": "load AGENTS.md\n",
                "charter.yaml": "tooling:\n  dev:\n    harness: codex\n",
                "docs/current/adoption-state.md": (
                    "<!-- adopter-root-harness: codex, cursor -->\n"
                ),
            }
        )
        r = awv.validate_root(root)
        self.assertNotIn("harness_conflict", r.rules_fired)
        self.assertEqual(r.targets, ["codex", "cursor"])
        self.assertTrue(r.ok, msg=r.render())  # codex PASS + cursor PASS => exit 0


class RootAndCliTests(_RootBuilder):
    def test_missing_root_errors(self):
        r = awv.validate_root(os.path.join(tempfile.gettempdir(), "awv-does-not-exist-xyz"))
        self.assertFalse(r.ok)
        self.assertIn("missing_root", r.rules_fired)

    def test_main_exit_codes(self):
        good = self._mk({"CLAUDE.md": "@AGENTS.md\n", "AGENTS.md": "# chain\n"})
        bad = self._mk({"AGENTS.md": "# chain\n"})
        cursor_ok = self._mk({"AGENTS.md": "# chain\n", ".cursor/rules": "load AGENTS.md\n"})
        cursor_bad = self._mk({"AGENTS.md": "# chain\n"})  # no .cursor/rules
        self.assertEqual(awv.main([good, "--harness", "claude_code"]), 0)
        self.assertEqual(awv.main([bad, "--harness", "claude_code"]), 1)
        self.assertEqual(awv.main([cursor_ok, "--harness", "cursor"]), 0)  # valid rules => 0
        self.assertEqual(awv.main([cursor_bad, "--harness", "cursor"]), 1)  # no rules => FAIL


if __name__ == "__main__":
    unittest.main(verbosity=2)
