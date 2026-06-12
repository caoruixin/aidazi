# docs/acceptance-reports/ — where Acceptance verdicts land

The **Acceptance Agent** writes `<scope>-acceptance-report.md` here at milestone close / release cut: a JSON verdict (`pass` / `fix_required` / `needs_human`) + per-criterion evidence + (on fail) a gap brief + a suggested route. The **Customer reads it at gate 2** and signs ship/no-ship.

In this example, `M1-acceptance-report.md` would land here after M1's milestone close. On `fix_required`, a human-confirm checkpoint also lands in `docs/checkpoints/` before any fix routes back to Deliver (§3.5).

- Schema: `aidazi/schemas/acceptance-verdict.schema.json`
- Input template: `aidazi/templates/compact-acceptance-prompt.md`
- Role: `aidazi/role-cards/acceptance-agent.md`
- Verdicts rest on F5 execution evidence (`eval/runs/<id>/artifacts/`), never code inspection.
