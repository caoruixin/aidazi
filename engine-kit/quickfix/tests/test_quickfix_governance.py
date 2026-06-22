"""Quick-Fix Commit 1 governance guards (no duplicated governance).

The lane spec must REFERENCE the §1.7/§1.8 forbidden list, the canonical anti-hardcode
kernel, and the machine-readable protected-surface policy — and must NOT restate any of
them (process/quickfix-lane.md §12). This enforces the single-canonical-source rule so a
second, drift-prone copy of the forbidden list / kernel / glob list cannot creep in.
"""
import os
import unittest

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_THIS, "..", "..", ".."))


def _read(rel):
    with open(os.path.join(_ROOT, rel), "r", encoding="utf-8") as fh:
        return fh.read()


class NoDuplication(unittest.TestCase):
    def setUp(self):
        self.lane = _read("process/quickfix-lane.md")

    def test_references_forbidden_list_and_kernel(self):
        self.assertIn("§1.7", self.lane)
        self.assertIn("§1.8", self.lane)
        self.assertIn("anti-hardcode-review-kernel.md", self.lane)

    def test_does_not_inline_the_kernel_questions(self):
        kernel = _read("templates/anti-hardcode-review-kernel.md")
        signature = "keyword / regex / if-else / enum / per-UC matrix"
        # Sanity: the signature really is the kernel's, ...
        self.assertIn(signature, kernel)
        # ... and it must NOT be copied into the lane spec.
        self.assertNotIn(signature, self.lane)

    def test_references_policy_without_restating_globs(self):
        self.assertIn("quickfix-protected-surfaces.policy.yaml", self.lane)
        # The lane spec must not carry the policy's actual glob list.
        self.assertNotIn("**/schemas/**", self.lane)
        self.assertNotIn("mandatory_surfaces:", self.lane)


if __name__ == "__main__":
    unittest.main()
