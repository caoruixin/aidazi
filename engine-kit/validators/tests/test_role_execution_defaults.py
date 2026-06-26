"""Verify shipped role execution defaults stay in sync with the mission-charter template."""

import os
import sys
import unittest

_VALIDATORS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _VALIDATORS_DIR not in sys.path:
    sys.path.insert(0, _VALIDATORS_DIR)

import role_execution_defaults as red  # noqa: E402


class RoleExecutionDefaultsTests(unittest.TestCase):
  def test_shipped_defaults_cover_five_roles(self):
    defaults = red.load_role_execution_defaults()
    self.assertEqual(
      set(defaults),
      {"research", "deliver", "dev", "review", "acceptance"},
    )

  def test_mission_charter_template_matches_shipped_defaults(self):
    mismatches = red.verify_mission_charter_template()
    self.assertEqual(mismatches, [], "\n".join(mismatches))

  def test_expected_bindings_snapshot(self):
    d = red.load_role_execution_defaults()
    self.assertEqual(d["research"]["model"], "claude-opus-4-8")
    self.assertEqual(d["research"]["reasoning_effort"], "xhigh")
    self.assertEqual(d["deliver"]["reasoning_effort"], "high")
    self.assertEqual(d["dev"]["harness"], "claude_code")
    self.assertEqual(d["dev"]["model"], "claude-sonnet-4-6")
    self.assertEqual(d["review"]["agent_kind"], "codex")
    self.assertEqual(d["review"]["model"], "gpt-5.5")
    self.assertEqual(d["review"]["reasoning_effort"], "high")
    self.assertEqual(d["acceptance"]["agent_kind"], "codex")
    self.assertEqual(d["acceptance"]["model"], "gpt-5.5")
    for role in ("research", "deliver", "dev", "review", "acceptance"):
      self.assertIs(d[role]["network_access"], True)


if __name__ == "__main__":
  unittest.main()
