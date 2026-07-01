REVISE

**BLOCKING** — [archive/2026-07-01-acceptance-auto-proposal-and-init-experience-design.md](/Users/caoruixin/projects/aidazi/archive/2026-07-01-acceptance-auto-proposal-and-init-experience-design.md:131) has an inaccurate test worklist row. It claims `test_pc_schemas.py:81` asserts Customer-only authority, but [engine-kit/validators/tests/test_pc_schemas.py](/Users/caoruixin/projects/aidazi/engine-kit/validators/tests/test_pc_schemas.py:81) is only the `RequirementLedgerSchema` class; nearby tests validate enum/required/additionalProperties, not agent/Customer authority.

Concrete fix: change the table row to either cite the actual authority test if one exists, or say no current authority test exists and require a new implementation test for the new generator/onboarding path: agent/engine creation may write only `customer_disposition: pending` on a new item, and any agent-authored decided value is rejected.

The seven prose/schema live contradictions are now covered, and the carve-out wording is tight: only `pending`, only on new-item creation. I found no other non-archive live surface asserting the old Customer-only/never-agent-written rule outside the table.