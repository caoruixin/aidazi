import json
import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_VALIDATORS_DIR = os.path.dirname(_TESTS_DIR)
if _VALIDATORS_DIR not in sys.path:
    sys.path.insert(0, _VALIDATORS_DIR)

import roadmap_validator as rv  # noqa: E402


class RoadmapValidatorTests(unittest.TestCase):
    def _mk(self, files: dict) -> str:
        root = tempfile.mkdtemp(prefix="roadmapv-")
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

    def _state(self, *, mode="single_milestone"):
        return {
            "schema_version": "roadmap-state.v1",
            "updated_at": "2026-06-25T00:00:00Z",
            "delivery_mode": mode,
            "autonomy_level": "human_on_the_loop",
            "roadmap_title": "AIJP MVP Roadmap",
            "campaign_id": "aijp-mvp" if mode == "campaign" else None,
            "source_refs": {
                "generated_backlog": "docs/milestone-backlog.md",
                "charter": "charter.yaml",
                "campaign_plan": "campaign-plan.json" if mode == "campaign" else None,
                "active_research_brief": "docs/research-briefs/RB-004-ui-milestone.md",
                "active_milestone_objective": "docs/milestone_objective.md",
            },
            "active": {
                "milestone_id": "M-UI",
                "subsprint_id": "sprint-011",
                "phase": "delivery",
            },
            "milestones": [
                {
                    "id": "M1-job-search-loop",
                    "title": "Job search loop",
                    "objective": "Job search loop plus talent base.",
                    "depends_on": [],
                    "status": "closed",
                    "research_brief": "docs/research-briefs/RB-001.md",
                    "signed_at": "2026-06-24",
                    "subsprint_sequence": ["sprint-001"],
                    "notes": None,
                },
                {
                    "id": "M2-data-import",
                    "title": "Data import",
                    "objective": "Import real candidate data.",
                    "depends_on": ["M1-job-search-loop"],
                    "status": "closed",
                    "research_brief": "docs/research-briefs/RB-003-data-import.md",
                    "signed_at": "2026-06-24",
                    "subsprint_sequence": ["sprint-007"],
                    "notes": None,
                },
                {
                    "id": "M-UI",
                    "title": "UI milestone",
                    "objective": "Frontend-only design-language elevation before M3.",
                    "depends_on": ["M1-job-search-loop", "M2-data-import"],
                    "status": "active",
                    "research_brief": "docs/research-briefs/RB-004-ui-milestone.md",
                    "signed_at": "2026-06-25",
                    "subsprint_sequence": ["sprint-011", "sprint-012"],
                    "notes": "Inserted before M3 by Customer roadmap mutation.",
                },
                {
                    "id": "M3-advance-outreach",
                    "title": "Advance and outreach",
                    "objective": "Pipeline and outreach.",
                    "depends_on": ["M1-job-search-loop", "M-UI"],
                    "status": "planned",
                    "research_brief": None,
                    "signed_at": None,
                    "subsprint_sequence": [],
                    "notes": None,
                },
            ],
        }

    def _old_campaign_without_ui(self):
        return {
            "campaign_id": "aijp-mvp",
            "goal": "Deliver AIJP MVP.",
            "signed_by_human": True,
            "milestones": [
                {"id": "M1-job-search-loop", "objective": "x", "subsprint_sequence": ["sprint-001"]},
                {"id": "M2-data-import", "objective": "x", "depends_on": ["M1-job-search-loop"], "subsprint_sequence": ["sprint-007"]},
                {"id": "M3-advance-outreach", "objective": "x", "depends_on": ["M1-job-search-loop"]},
            ],
        }

    def _campaign_with_ui(self):
        return {
            "campaign_id": "aijp-mvp",
            "goal": "Deliver AIJP MVP.",
            "signed_by_human": True,
            "milestones": [
                {"id": "M1-job-search-loop", "objective": "x", "subsprint_sequence": ["sprint-001"]},
                {"id": "M2-data-import", "objective": "x", "depends_on": ["M1-job-search-loop"], "subsprint_sequence": ["sprint-007"]},
                {"id": "M-UI", "objective": "x", "depends_on": ["M1-job-search-loop", "M2-data-import"], "subsprint_sequence": ["sprint-011", "sprint-012"]},
                {"id": "M3-advance-outreach", "objective": "x", "depends_on": ["M1-job-search-loop", "M-UI"]},
            ],
        }

    def test_single_milestone_warns_but_does_not_fail_on_inactive_campaign_drift(self):
        report = rv.validate_campaign_alignment(
            self._state(mode="single_milestone"),
            self._old_campaign_without_ui(),
            campaign_path="campaign-plan.json",
        )
        self.assertTrue(report.ok, msg=report.render())
        self.assertEqual([w.rule for w in report.warnings], ["roadmap_campaign_inactive_drift"])

    def test_campaign_mode_fails_when_campaign_plan_omits_inserted_ui_milestone(self):
        report = rv.validate_campaign_alignment(
            self._state(mode="campaign"),
            self._old_campaign_without_ui(),
            campaign_path="campaign-plan.json",
        )
        self.assertFalse(report.ok)
        self.assertIn(
            "roadmap_campaign_milestone_order_mismatch",
            {e.rule for e in report.errors},
        )

    def test_campaign_mode_passes_when_campaign_plan_matches_m_ui_before_m3(self):
        report = rv.validate_campaign_alignment(
            self._state(mode="campaign"),
            self._campaign_with_ui(),
            campaign_path="campaign-plan.json",
        )
        self.assertTrue(report.ok, msg=report.render())

    def test_render_backlog_is_generated_and_mentions_authority(self):
        text = rv.render_backlog(self._state(mode="single_milestone"))
        self.assertIn("GENERATED by aidazi roadmap_validator.py", text)
        self.assertIn("**M-UI**", text)
        self.assertIn("Active execution source: `charter.yaml`", text)
        self.assertIn("Do not edit this file directly", text)

    def test_mutation_schema_accepts_customer_insert_milestone(self):
        root = self._mk({
            "roadmap-mutations.jsonl": json.dumps({
                "schema_version": "roadmap-mutation.v1",
                "mutation_id": "rm-1",
                "recorded_at": "2026-06-25T00:00:00Z",
                "requested_by": {"role": "Customer", "name": "Rex"},
                "delivery_mode": "single_milestone",
                "action": "insert_milestone",
                "target_milestone_id": "M-UI",
                "insert_before": "M3-advance-outreach",
                "insert_after": None,
                "milestone": {
                    "id": "M-UI",
                    "title": "UI milestone",
                    "objective": "Frontend-only UI milestone.",
                    "depends_on": ["M1-job-search-loop", "M2-data-import"],
                    "status": "needs_research_gate1",
                },
                "depends_on": None,
                "requires_next_gate": "research_gate1",
                "notes": "Customer requested this before M3.",
            }) + "\n"
        })
        report = rv.validate_mutations_file(os.path.join(root, "roadmap-mutations.jsonl"))
        self.assertTrue(report.ok, msg=report.render())


if __name__ == "__main__":
    unittest.main(verbosity=2)
