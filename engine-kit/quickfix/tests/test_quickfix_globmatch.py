"""Quick-Fix safe-subset glob matcher tests (spec process/quickfix-lane.md §6/§8).

Heavy adversarial coverage of the matcher the guard depends on: '**' depth semantics,
dot paths, and fail-closed rejection of every unsupported / traversal / absolute form.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from quickfix.errors import GlobError  # noqa: E402
from quickfix.globmatch import Glob, NamedGlobs, first_match  # noqa: E402


class GlobStarDepth(unittest.TestCase):
    def test_leading_globstar_matches_root_and_vendored(self):
        g = Glob("**/schemas/**")
        self.assertTrue(g.matches("schemas/x.json"))
        self.assertTrue(g.matches("aidazi/schemas/x.json"))
        self.assertTrue(g.matches("a/b/schemas/deep/x.json"))
        self.assertFalse(g.matches("notschemas/x.json"))
        self.assertFalse(g.matches("schemasx/x.json"))

    def test_trailing_globstar_requires_a_child(self):
        g = Glob("engine-kit/quickfix/**")
        self.assertTrue(g.matches("engine-kit/quickfix/guard.py"))
        self.assertTrue(g.matches("engine-kit/quickfix/tests/test_x.py"))
        self.assertFalse(g.matches("engine-kit/quickfix"))  # the dir itself, no child
        self.assertFalse(g.matches("engine-kit/quickfixx/y"))

    def test_middle_globstar(self):
        g = Glob("a/**/b.py")
        self.assertTrue(g.matches("a/b.py"))
        self.assertTrue(g.matches("a/x/b.py"))
        self.assertTrue(g.matches("a/x/y/b.py"))
        self.assertFalse(g.matches("a/b.pyc"))
        self.assertFalse(g.matches("x/a/b.py"))

    def test_single_star_does_not_cross_slash(self):
        g = Glob("src/*.py")
        self.assertTrue(g.matches("src/foo.py"))
        self.assertFalse(g.matches("src/sub/foo.py"))
        self.assertFalse(g.matches("foo.py"))

    def test_question_mark(self):
        g = Glob("a/b?.py")
        self.assertTrue(g.matches("a/bx.py"))
        self.assertFalse(g.matches("a/b.py"))
        self.assertFalse(g.matches("a/bxy.py"))

    def test_leading_globstar_filename(self):
        g = Glob("**/charter.yaml")
        self.assertTrue(g.matches("charter.yaml"))
        self.assertTrue(g.matches("aidazi/charter.yaml"))
        self.assertFalse(g.matches("charter.yaml.bak"))

    def test_dotfiles(self):
        self.assertTrue(Glob("**/.env").matches(".env"))
        self.assertTrue(Glob("**/.env").matches("svc/.env"))
        self.assertTrue(Glob("**/.env.*").matches(".env.local"))
        self.assertFalse(Glob("**/.env").matches(".environment"))

    def test_exact_path(self):
        g = Glob("process/delivery-loop.md")
        self.assertTrue(g.matches("process/delivery-loop.md"))
        self.assertFalse(g.matches("aidazi/process/delivery-loop.md"))  # no **/ -> anchored


class FailClosedRejection(unittest.TestCase):
    def test_rejects_unsupported_and_traversal_forms(self):
        for bad in [
            "/etc/passwd", "../x", "src/../x", "~/x", "src/~x", "!src/x",
            "src/[.][.]/x", "{../x,y}", "[/]etc", "a[0-9].py", "a{b,c}.py",
            "a,b.py", "", "a/../b", "a/**b/c", "a/b**/c", "a b.py",
        ]:
            with self.assertRaises(GlobError, msg=f"{bad!r} must be rejected"):
                Glob(bad)

    def test_accepts_safe_forms(self):
        for ok in ["src/**", "**/schemas/**", "docs/*.md", "a/b?.py",
                   "engine-kit/connectors/translate.py", "**/.env", "a/**/b.py"]:
            Glob(ok)  # must not raise


class FirstMatch(unittest.TestCase):
    def test_first_match_returns_surface_id(self):
        surfaces = [
            NamedGlobs("governance", ["**/governance/**"], "r"),
            NamedGlobs("schemas", ["**/schemas/**"], "r"),
        ]
        self.assertEqual(first_match("aidazi/schemas/x.json", surfaces), "schemas")
        self.assertEqual(first_match("governance/constitution.md", surfaces), "governance")
        self.assertIsNone(first_match("src/app.py", surfaces))


if __name__ == "__main__":
    unittest.main()
