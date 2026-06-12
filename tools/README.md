# tools/ — referenced-but-not-yet-built scripts (OQ-V4-009)

This directory tracks scripts the framework docs **reference** but the framework does not yet **ship**. They are intentionally deferred (OQ-V4-009): the framework specifies the discipline; the mechanical enforcement script is optional tooling an adopter (or a future fold-back) can build.

Until a script exists here, the discipline it would mechanize is enforced by the human / role process described in the cited doc. None of these is required to run the framework — they reduce friction, they don't gate it.

## Referenced scripts (not built)

| Script | Mechanizes | Referenced by | Manual fallback today |
|---|---|---|---|
| `precommit_bundling_check.sh` | Catch Deliver-owned files staged outside a close commit | `docs/friction-playbook.md` F3 | Dev stages explicit paths, not blanket `git add -A` (`role-cards/dev-agent.md` §3) |
| `stanza_validator.py` | Validate the 4 sprint-stanza fields against the schema before dispatch | `docs/friction-playbook.md` F4 | Deliver + human eyeball the stanza against `schemas/sprint_stanza.schema.json` before dispatch |
| `charter_validator` | Reject charters that bypass a MANDATORY_CHECKPOINT (4 shapes) or set `human_confirm_required: false` | `process/delivery-loop.md` §4.2.2; `governance/constitution.md` §1.7-D | Human reviews the charter against the §4.2.2 editing rules before boot |
| `trace_emitter.py` | Emit the portable trace shape for F5 evidence | `modules/m-trace.md` | Adopter's runtime emits traces in the documented shape directly |

## Building one

If you build a script here:

1. Keep it mechanical (deterministic; no LLM) — these enforce hard, checkable rules.
2. Reference the doc it mechanizes in a header comment; the doc stays the source of truth.
3. File a lesson (`templates/lessons-learned-template.md`) so the next fold-back can consider promoting it into the framework default.

When all four are built and proven across adopters, OQ-V4-009 closes and this README becomes the tools index rather than a deferral tracker.
