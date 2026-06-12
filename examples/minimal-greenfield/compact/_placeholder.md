# compact/ — where per-sprint prompt artifacts land

Deliver generates self-contained prompt artifacts here, one per sprint, frozen per sprint. Each carries `context_budget` front-matter with `self_contained: true` (§1.4-i).

For M1 / sprint-001 this directory would hold:

- `sprint-001-dev-prompt.md` — the Dev job spec (from `aidazi/templates/compact-dev-prompt.md`).
- `M1-review-prompt.md` — the Code Reviewer spec (from `aidazi/templates/compact-review-prompt.md`; references the anti-hardcode kernel).
- `M1-acceptance-prompt.md` — the Acceptance spec (from `aidazi/templates/compact-acceptance-prompt.md`).

Left as a placeholder to keep the snapshot minimal. These are Layer-D artifacts (`aidazi/governance/constitution.md` §6) — generated, not hand-maintained.
