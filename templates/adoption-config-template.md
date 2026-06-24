---
title: Adoption configuration map — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
load_discipline: on-demand
size_target: 8KB
notes: >
  Copy to <adopter>/docs/current/adoption-config.md during ONBOARDING Step 0.
  The human-readable map of what CAN be configured, where it lives, and which
  onboarding step sets it. Pair with adoption_status.py for what IS configured.
---

# Adoption configuration map — `<adopter-name>`

This file lists **every adopter-facing knob** the Onboarding Wizard touches or that
runtime loops consume. It is a **map**, not the audit trail — decisions live in
`onboarding-record.md`; overrides live in `adoption-state.md`.

After Step 8, run `python engine-kit/validators/adoption_status.py .` for a live
**configured vs missing** report. Step 8 also writes `adoption-readiness.md`.

> **Two distinct stacks (never merge).** The *adopter implementation stack*
> (product language/framework/build/test/deploy) lives in
> `implementation-stack.md` (Step 4a). The *agent execution stack*
> (harness × provider × model per role) lives in `charter.yaml` `tooling.*`
> (Step 5).

---

## Identity and adoption shape

| Config item | Location | Required? | Default | Onboarding step |
|---|---|---|---|---|
| Project name / track | `AGENTS.md` §1, `adoption-state.md` front-matter | yes | — | Step 3 |
| Greenfield vs brownfield | `onboarding-record.md` + ledger | yes | auto-detect | Step 1 |
| Intent contract (`goal / standard / proof_of_done`) | `docs/research-briefs/<id>.md` | yes | agent drafts | Step 4 |

## Adopter implementation stack (product facts)

| Config item | Location | Required? | Default | Onboarding step |
|---|---|---|---|---|
| Language / framework / build / test / data / deploy | `docs/current/implementation-stack.md` | partial | unknown → `DEFERRED` | Step 4a |

## Role configuration (agent execution stack)

| Config item | Location | Required? | Default | Onboarding step |
|---|---|---|---|---|
| Per-role harness / provider / model | `charter.yaml` `tooling.<role>` | yes | `skills/registry.yaml` | Step 5 Facet A |
| Per-role skills | `charter.yaml` + `skills/vendored/` | yes | role_defaults | Step 5 Facet B |
| Connectors (tools / MCP) | `charter.yaml` `tooling.<role>.connectors[]` | no | **default-deny (none)** | Step 5 Facet C |
| API keys (**env-var NAME only**) | `.env.local` + charter `api_key_env` / `endpoint_env` | when headless | — | Step 5 preflight |
| Per-role timeout | `charter.yaml` `tooling.<role>.timeout_seconds` | no | adapter default (600s) | Step 5 |

## Autonomy, budget, checkpoints

| Config item | Location | Required? | Default | Onboarding step |
|---|---|---|---|---|
| Autonomy level | `charter.yaml` `autonomy.level` | yes | `human_in_the_loop` | Step 7 |
| Approved scope | `charter.yaml` `autonomy.approved_scope` | yes | from brief | Step 7 |
| Budget caps | `charter.yaml` `budget.*` | yes | conservative | Step 7 |
| Loop Memory | `charter.yaml` `memory.enabled` / `memory.root` | no | **OFF** | Step 7 |
| 9 MANDATORY_CHECKPOINTS | framework (cannot omit) | yes | always on | — |

## Harness root-file wiring

| Config item | Location | Required? | Default | Onboarding step |
|---|---|---|---|---|
| Governance chain entry | `AGENTS.md` (@-includes) | yes | consumer template | Step 6 |
| Claude Code import | `CLAUDE.md` → `@AGENTS.md` | yes (if using Claude Code) | one line | Step 6 |
| Cursor wiring | `.cursor/rules` | when Cursor is primary | adopter-owned | Step 6 |

## Paths and runtime artifacts

| Config item | Location | Required? | Default | Notes |
|---|---|---|---|---|
| **Loop run dir** (state / audit / transcripts) | `.runs/<loop_id>/` | auto | `<repo>/.runs/<loop_id>` | gitignored; `--run-dir` overrides |
| Campaign home | `.runs/campaign-<id>/` | when using `--campaign` | same base | `--campaign-run-dir` overrides |
| Loop registry (cross-loop) | `.orchestrator/loops.json` | auto | repo-side | **not** the run-dir `.orchestrator` |
| Audit ledger dir (charter default) | `.orchestrator/audit/` | scaffold | charter `audit.ledger_dir` | repo-side placeholder |
| Loop Memory store | `<memory.root>/` | when enabled | `memory/` under charter dir | OFF by default |

## Git hygiene (Step 6)

Ensure `.gitignore` includes at minimum:

```
.orchestrator/
.runs/
.env.local
```

Loop artifacts under `.runs/` stay in-repo for discoverability but never enter the
delivered diff. Secrets stay in `.env.local` (names referenced in charter only).

## Live progress during a loop (runtime — not onboarding)

| What you want | Path |
|---|---|
| Current state machine position | `.runs/<loop_id>/.orchestrator/state.json` |
| Event timeline (`tail -f`) | `.runs/<loop_id>/.orchestrator/audit/<loop_id>.jsonl` |
| Dev/Review prompt + output | `.runs/<loop_id>/.orchestrator/audit/transcripts/<loop_id>/` |
| Human gate checkpoints | `.runs/<loop_id>/docs/checkpoints/` |
| Which loops ran on this branch | `.orchestrator/loops.json` |

---

End of adoption configuration map template.
