# docs/diagnostics/failure-briefs/ — where load-bearing failure shapes land

Joint **human + Deliver** author a `<id>.md` here when a bad case is observed and triage decides it's load-bearing (n≥2 similar OR severe). Uses the 6-field template: (1) what happened, (2) what a good agent should have done, (3) why it matters, (4) one-off-or-pattern, (5) which fix-layer, (6) what NOT to do.

A failure-brief is the Path-2 input that the Research Agent formalizes into a research-brief.

- Distinct from `docs/diagnostics/<id>.md` (tech-internal root-cause, agent-authored mid-sprint) — see `aidazi/docs/directory-taxonomy.md` §6.
- Reproducible failures also get an `eval/bad_cases/<id>.yaml` case (see `eval/bad_cases/_manifest.md`).
- The parent `docs/diagnostics/` directory holds the tech-internal notes; this `failure-briefs/` sub-dir holds the formal customer-facing shapes.
