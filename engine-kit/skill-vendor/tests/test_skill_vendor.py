"""Offline, deterministic tests for skill_vendor.

Two layers:
  1. INTEGRATION: `verify` PASSES against the real skills/vendored + skills.lock
     committed in the repo (proves the hashing scheme reproduces the ground
     truth). Skipped gracefully if the repo's skills/ tree is not located.
  2. UNIT: the hashing function on a tiny temp fixture dir created in the test
     (round-trip) — including that _provenance.yaml is excluded from the tree,
     that the manifest uses TWO spaces (shasum text mode), and that tampering a
     byte changes the tree hash. No network.
"""

import hashlib
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_DIR = os.path.dirname(_TESTS_DIR)
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import skill_vendor as sv  # noqa: E402


class VerifyRealSkillsTests(unittest.TestCase):
    """`verify` against the committed skills.lock must pass for every skill."""

    def setUp(self):
        if not sv.REPO_ROOT:
            self.skipTest("repo skills/skills.lock not located from test dir")

    def test_verify_all_real_skills_passes(self):
        report = sv.verify()
        self.assertTrue(
            report.ok,
            msg=f"verify against committed skills.lock must pass:\n{report.render()}",
        )
        # The committed lock pins exactly 6 vendored skills.
        self.assertEqual(len(report.results), 6, msg=report.render())
        for r in report.results:
            self.assertTrue(r.ok, msg=f"{r.skill_id} failed: {r.messages}")

    def test_verify_single_id_subset(self):
        report = sv.verify(["brainstorming"])
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual([r.skill_id for r in report.results], ["brainstorming"])


class HashingRoundTripTests(unittest.TestCase):
    """Hashing function exercised on a self-built temp fixture (no real skills)."""

    def _make_skill(self, root: str) -> str:
        skill = os.path.join(root, "demo-skill")
        os.makedirs(os.path.join(skill, "scripts"), exist_ok=True)
        with open(os.path.join(skill, "SKILL.md"), "wb") as f:
            f.write(b"# Demo skill\nbody\n")
        with open(os.path.join(skill, "LICENSE"), "wb") as f:
            f.write(b"MIT\n")
        with open(os.path.join(skill, "scripts", "run.sh"), "wb") as f:
            f.write(b"echo hi\n")
        return skill

    def test_enumerate_excludes_provenance_and_is_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._make_skill(tmp)
            with open(os.path.join(skill, sv.PROVENANCE_FILENAME), "wb") as f:
                f.write(b"id: demo\n")
            files = sv.enumerate_files(skill)
            self.assertEqual(
                files, ["./LICENSE", "./SKILL.md", "./scripts/run.sh"]
            )
            self.assertNotIn(f"./{sv.PROVENANCE_FILENAME}", files)

    def test_manifest_uses_two_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._make_skill(tmp)
            per_file = sv.per_file_hashes(skill)
            text = sv.manifest_text(per_file)
            # shasum text mode separates hash and path with exactly two spaces.
            for line in text.splitlines():
                hexpart, sep, path = line.partition("  ")
                self.assertEqual(sep, "  ", msg=line)
                self.assertEqual(len(hexpart), 64, msg=line)
                self.assertTrue(path.startswith("./"), msg=line)

    def test_tree_hash_matches_independent_recompute(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._make_skill(tmp)
            # Independent recomputation following the documented scheme.
            paths = sorted(
                "./" + os.path.relpath(os.path.join(r, n), skill).replace(os.sep, "/")
                for r, _d, ns in os.walk(skill)
                for n in ns
            )
            manifest = ""
            for p in paths:
                with open(os.path.join(skill, p[2:]), "rb") as f:
                    hx = hashlib.sha256(f.read()).hexdigest()
                manifest += f"{hx}  {p}\n"
            expected = hashlib.sha256(manifest.encode("utf-8")).hexdigest()
            self.assertEqual(sv.tree_sha256(skill), expected)

    def test_provenance_does_not_affect_tree_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._make_skill(tmp)
            before = sv.tree_sha256(skill)
            with open(os.path.join(skill, sv.PROVENANCE_FILENAME), "wb") as f:
                f.write(b"id: demo\ntree_sha256: whatever\n")
            after = sv.tree_sha256(skill)
            self.assertEqual(before, after)

    def test_tamper_changes_tree_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._make_skill(tmp)
            before = sv.tree_sha256(skill)
            with open(os.path.join(skill, "SKILL.md"), "ab") as f:
                f.write(b"tampered\n")
            after = sv.tree_sha256(skill)
            self.assertNotEqual(before, after)

    def test_verify_skill_detects_tampered_file(self):
        # Build a fixture skill + a matching lock entry + provenance, confirm OK,
        # then tamper one file and confirm verify_skill flags it.
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._make_skill(tmp)
            per_file = sv.per_file_hashes(skill)
            tree = sv.tree_sha256(skill)
            import yaml  # local import; pyyaml is a runtime dep
            prov = {
                "id": "demo-skill",
                "tree_sha256": tree,
                "files": [{"path": p[2:], "sha256": h} for p, h in per_file],
            }
            with open(os.path.join(skill, sv.PROVENANCE_FILENAME), "w", encoding="utf-8") as f:
                yaml.safe_dump(prov, f, sort_keys=False)
            lock_entry = {"tree_sha256": tree}

            good = sv.verify_skill("demo-skill", skill, lock_entry)
            self.assertTrue(good.ok, msg=good.messages)

            # Tamper a file's bytes (provenance + lock now stale).
            with open(os.path.join(skill, "scripts", "run.sh"), "ab") as f:
                f.write(b"rm -rf /\n")
            bad = sv.verify_skill("demo-skill", skill, lock_entry)
            self.assertFalse(bad.ok)
            self.assertTrue(
                any("tree_sha256 mismatch" in m for m in bad.messages), msg=bad.messages
            )


class CorruptLockfileTests(unittest.TestCase):
    """A corrupt skills.lock must yield a clean, non-zero error — never a raw
    yaml exception/traceback."""

    def _make_corrupt_lock_root(self, root: str) -> str:
        """Create <root>/skills/skills.lock with junk YAML; return root."""
        os.makedirs(os.path.join(root, "skills"), exist_ok=True)
        with open(os.path.join(root, "skills", "skills.lock"), "w", encoding="utf-8") as f:
            # Unbalanced/invalid YAML that yaml.safe_load rejects.
            f.write("skills: {oops: [unclosed, : : :\n\t- bad: indent\n  ::nope")
        return root

    def test_load_lock_raises_typed_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_corrupt_lock_root(tmp)
            with self.assertRaises(sv.LockfileError) as ctx:
                sv.load_lock(repo_root=root)
            self.assertIn("skills.lock: unparseable", str(ctx.exception))
            self.assertNotIn("\n", str(ctx.exception))  # single clean line

    def test_verify_cli_corrupt_lock_clean_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_corrupt_lock_root(tmp)
            # Point the CLI's module-level REPO_ROOT at our junk root.
            saved = sv.REPO_ROOT
            sv.REPO_ROOT = root
            out, err = io.StringIO(), io.StringIO()
            try:
                with redirect_stdout(out), redirect_stderr(err):
                    rc = sv.main(["verify"])  # must not raise a traceback
            except Exception as exc:  # pragma: no cover - failure path
                self.fail(f"skill_vendor verify CLI raised: {exc!r}")
            finally:
                sv.REPO_ROOT = saved
            self.assertNotEqual(rc, 0)
            self.assertIn("skills.lock: unparseable", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
