# tools/ — optional convenience scripts (OQ-V4-009: RESOLVED)

aidazi specifies the **discipline**; a mechanical enforcement script is, where it exists at all, **optional convenience tooling**. OQ-V4-009 — which tracked "scripts the docs *reference* but the framework does not yet *ship*" — is **RESOLVED** (2026-06-17): the two governance-critical validators ship + are tested in the kit, and the two remaining referenced scripts are deliberately optional / adopter-side. **None of these gates the framework.**

## Status

| Script | Mechanizes | Status |
|---|---|---|
| `charter_validator` | reject charters that bypass a MANDATORY_CHECKPOINT (4 shapes) / set `human_confirm_required: false` / fail the Facet A·B·C gates | ✅ **SHIPPED + tested** — `engine-kit/validators/charter_validator.py` |
| `stanza_validator.py` | validate the 4 sprint-stanza fields against the schema before dispatch | ✅ **SHIPPED + tested** — `engine-kit/validators/stanza_validator.py` |
| `precommit_bundling_check.sh` | catch Deliver-owned files staged outside a close commit | ⚪ **OPTIONAL adopter convenience** — build it if you want it; **not framework-blocking**. Manual fallback (sufficient): Dev stages explicit paths, never blanket `git add -A` (`role-cards/dev-agent.md` §3). |
| `trace_emitter.py` | emit the portable F5 trace shape | ⚪ **Adopter-runtime concern** — aidazi **defines** the portable trace *contract* (`modules/m-trace.md`); the **adopter's runtime emits** traces in that shape. aidazi is not a runtime, so there is no framework script to ship here. |

## Why OQ-V4-009 is closed

The open question was whether the framework needed to *ship* these referenced scripts. Resolution: the two that enforce hard, checkable governance rules are shipped in `engine-kit/validators/` (deterministic, no-LLM, tested). The other two are **not** framework-blocking — `precommit_bundling_check.sh` is a friction-reducer with a working manual fallback, and `trace_emitter.py` is inherently adopter-runtime-specific (the framework owns the trace *contract*, not its *emission*). Both remain **build-if-needed** for an adopter, and a future fold-back MAY promote a proven one into the kit — but the framework runs without them.

## Building one (if you choose to)

1. Keep it mechanical (deterministic; no LLM) — these enforce hard, checkable rules.
2. Reference the doc it mechanizes in a header comment; the doc stays the source of truth.
3. File a lesson (`templates/lessons-learned-template.md`) so the next fold-back can consider promoting it into the framework default.
