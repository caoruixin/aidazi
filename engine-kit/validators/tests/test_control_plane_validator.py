import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_VALIDATORS_DIR = os.path.dirname(_TESTS_DIR)
if _VALIDATORS_DIR not in sys.path:
    sys.path.insert(0, _VALIDATORS_DIR)

import control_plane_validator as cpv  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(_VALIDATORS_DIR))
_MINIMAL_GREENFIELD = os.path.join(_REPO_ROOT, "examples", "minimal-greenfield")


GOOD_BLOCK = """# AGENTS

```control-plane-load
allow:
  - AGENTS.md
  - .orchestrator/control/state.json
  - .orchestrator/control/intents.jsonl
  - .orchestrator/control/checkpoints-index.json
  - charter.yaml
  - docs/current/adoption-state.md
  - docs/current/agent_context_guide.md
on_demand:
  - aidazi/process/control-plane-routing.md
  - aidazi/schemas/control-plane-intent.schema.json
  - aidazi/schemas/control-plane-state.schema.json
forbid:
  - aidazi/role-cards/**
  - aidazi/process/delivery-loop.md
  - aidazi/process/campaign-loop.md
  - docs/action_bank.md
  - docs/handoff.md
  - docs/10-handoff.md
  - docs/research-briefs/**
  - docs/proposals/**
  - docs/sprints/**
  - .orchestrator/audit/**
  - .runs/**
  - eval/runs/**
```
"""


class _RootBuilder(unittest.TestCase):
    def _mk(self, files: dict) -> str:
        root = tempfile.mkdtemp(prefix="cpv-")
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


class LoadBlockTests(_RootBuilder):
    def test_good_block_passes(self):
        root = self._mk({"AGENTS.md": GOOD_BLOCK})
        r = cpv.validate_root(root)
        self.assertTrue(r.ok, msg=r.render())

    def test_repo_agents_template_passes(self):
        r = cpv.validate_root(_REPO_ROOT)
        self.assertTrue(r.ok, msg=r.render())

    def test_shipped_minimal_greenfield_example_passes(self):
        r = cpv.validate_root(_MINIMAL_GREENFIELD)
        self.assertTrue(r.ok, msg=r.render())

    def test_missing_block_fails(self):
        root = self._mk({"AGENTS.md": "# no block\n"})
        r = cpv.validate_root(root)
        self.assertFalse(r.ok)
        self.assertIn("control_plane_load_missing", r.rules_fired)

    def test_governance_at_include_fails(self):
        root = self._mk({
            "AGENTS.md": "@aidazi/governance/constitution.md\n" + GOOD_BLOCK,
        })
        r = cpv.validate_root(root)
        self.assertFalse(r.ok)
        self.assertIn("control_plane_governance_at_include", r.rules_fired)

    def test_live_at_include_must_be_listed_in_allow(self):
        root = self._mk({
            "AGENTS.md": "@docs/current/runtime_invariants.md\n" + GOOD_BLOCK,
        })
        r = cpv.validate_root(root)
        self.assertFalse(r.ok)
        self.assertIn("control_plane_unlisted_at_include", r.rules_fired)

    def test_live_at_include_forbidden_path_fails(self):
        root = self._mk({
            "AGENTS.md": "@docs/action_bank.md\n" + GOOD_BLOCK,
        })
        r = cpv.validate_root(root)
        self.assertFalse(r.ok)
        self.assertIn("control_plane_forbidden_default_load", r.rules_fired)

    def test_role_card_in_allow_fails(self):
        bad = GOOD_BLOCK.replace(
            "  - charter.yaml\n",
            "  - charter.yaml\n  - aidazi/role-cards/dev-agent.md\n",
        )
        root = self._mk({"AGENTS.md": bad})
        r = cpv.validate_root(root)
        self.assertFalse(r.ok)
        self.assertIn("control_plane_forbidden_default_load", r.rules_fired)

    def test_glob_in_allow_fails(self):
        bad = GOOD_BLOCK.replace(
            "  - charter.yaml\n",
            "  - charter.yaml\n  - docs/**/*.md\n",
        )
        root = self._mk({"AGENTS.md": bad})
        r = cpv.validate_root(root)
        self.assertFalse(r.ok)
        self.assertIn("control_plane_default_glob", r.rules_fired)


class SchemaTests(_RootBuilder):
    def test_valid_state_and_intent_pass(self):
        state = {
            "schema_version": "control-plane-state.v1",
            "updated_at": "2026-06-24T00:00:00Z",
            "active": {
                "campaign_id": "C1",
                "milestone_id": "M1",
                "subsprint_id": "sprint-001",
                "phase": "gate_pending",
                "run_id": "run-1",
            },
            "open_checkpoints": [],
            "latest_refs": {"run_state": ".runs/run-1/.orchestrator/state.json"},
            "next_recommended_action": "resume runner",
        }
        intent = {
            "classification": "continue_delivery",
            "confidence": "high",
            "affected_scope": "M1",
            "next_action": "resume runner",
            "requires_role": "none",
            "needs_human_clarification": False,
            "evidence_refs": [".orchestrator/control/state.json"],
            "loaded_refs": ["AGENTS.md", ".orchestrator/control/state.json"],
        }
        root = self._mk({
            "AGENTS.md": GOOD_BLOCK,
            ".orchestrator/control/state.json": json.dumps(state),
            ".orchestrator/control/intents.jsonl": json.dumps(intent) + "\n",
        })
        r = cpv.validate_root(
            root,
            state_path=os.path.join(root, ".orchestrator/control/state.json"),
            intents_path=os.path.join(root, ".orchestrator/control/intents.jsonl"),
        )
        self.assertTrue(r.ok, msg=r.render())

    def test_existing_default_state_and_intents_are_validated(self):
        root = self._mk({
            "AGENTS.md": GOOD_BLOCK,
            ".orchestrator/control/state.json": json.dumps({
                "schema_version": "wrong"
            }),
        })
        r = cpv.validate_root(root)
        self.assertFalse(r.ok)
        self.assertIn("control_plane_schema_invalid", r.rules_fired)

    def test_missing_default_state_and_intents_are_allowed(self):
        root = self._mk({"AGENTS.md": GOOD_BLOCK})
        r = cpv.validate_root(root)
        self.assertTrue(r.ok, msg=r.render())

    def test_explicit_relative_state_path_resolves_from_root(self):
        state = {
            "schema_version": "control-plane-state.v1",
            "updated_at": "2026-06-24T00:00:00Z",
            "active": {},
            "open_checkpoints": [],
            "latest_refs": {},
            "next_recommended_action": None,
        }
        root = self._mk({
            "AGENTS.md": GOOD_BLOCK,
            ".orchestrator/control/state.json": json.dumps(state),
        })
        r = cpv.validate_root(root, state_path=".orchestrator/control/state.json")
        self.assertTrue(r.ok, msg=r.render())

    def test_explicit_missing_state_path_fails(self):
        root = self._mk({"AGENTS.md": GOOD_BLOCK})
        r = cpv.validate_root(root, state_path=".orchestrator/control/state.json")
        self.assertFalse(r.ok)
        self.assertIn("control_plane_state_unreadable", r.rules_fired)

    def test_intent_schema_invalid_fails_closed(self):
        root = self._mk({
            "AGENTS.md": GOOD_BLOCK,
            ".orchestrator/control/intents.jsonl": json.dumps({
                "classification": "continue_delivery"
            }) + "\n",
        })
        r = cpv.validate_root(
            root,
            intents_path=os.path.join(root, ".orchestrator/control/intents.jsonl"),
        )
        self.assertFalse(r.ok)
        self.assertIn("control_plane_schema_invalid", r.rules_fired)

    def test_intent_loaded_refs_forbidden_fails(self):
        intent = {
            "classification": "status_request",
            "confidence": "high",
            "affected_scope": None,
            "next_action": "summarize state",
            "requires_role": "none",
            "needs_human_clarification": False,
            "evidence_refs": [],
            "loaded_refs": [".orchestrator/audit/loop.jsonl"],
        }
        root = self._mk({
            "AGENTS.md": GOOD_BLOCK,
            ".orchestrator/control/intents.jsonl": json.dumps(intent) + "\n",
        })
        r = cpv.validate_root(
            root,
            intents_path=os.path.join(root, ".orchestrator/control/intents.jsonl"),
        )
        self.assertFalse(r.ok)
        self.assertIn("control_plane_forbidden_default_load", r.rules_fired)


if __name__ == "__main__":
    unittest.main(verbosity=2)
