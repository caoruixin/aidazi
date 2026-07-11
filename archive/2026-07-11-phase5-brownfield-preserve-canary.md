# Phase-5 brownfield-preserve — fix + canary evidence (2026-07-11)

**Branch:** `feat/phase5-brownfield-preserve` (off `origin/main` = `2062062`)
**Scope:** make `adopter_init.py --force` non-destructive on a brownfield (already-adopted or
partially-adopted) repo. Correctness fix for the post-Phase-5 finding that `--force` regenerated
(clobbered) an adopter's governed docs.

## The finding (confirmed against committed `origin/main` `2062062`)

`adopter_init` was a greenfield scaffolder whose `materialize()` **clobbered** every generated
artifact that was not in a small `_HUMAN_EDITABLE` allow-list (`charter.yaml`,
`docs/research-briefs/`). On a real brownfield adopter (airplat), running `--force` **silently
overwrote 9 evolved governed docs with generic templates and reported GREEN (exit 0)** — masking
the adopter's real (broken) state and destroying its authored governance content.

## The fix (design §6.2 / brownfield-preserve)

`--force` is now a **bootstrap, not a migrator**:

- **Create only MISSING files.** Absent bootstrap/wiring files are still scaffolded.
- **Preserve every existing file byte-for-byte.** No existing governed/wiring/human file is ever
  rewritten (the `_HUMAN_EDITABLE` special-case collapses — *all* existing files are preserved).
  `.gitignore` remains the one exception: required patterns are **append-merged**, existing lines
  kept.
- **Fail, don't rewrite.** If a preserved file is incompatible with adoption, the four exit
  validators report it (exit 2, actionable remediation) instead of a silent overwrite.
- `--overwrite` stays the **explicit human escape hatch** to regenerate existing files.
- `materialize()` returns a `MaterializeReport` (created / preserved / unchanged / merged /
  overwritten); `main()` prints it so the human sees exactly what was written vs kept.

## Disposable airplat-copy canary (real adopter, /tmp copy — live airplat untouched)

Copy of `/Users/caoruixin/projects/airplat` (its own `aidazi/` mount included; VCS/build/cache
dirs dropped) → run `adopter_init --force` → compare every pre-existing file + `control_plane`
findings before/after. Snapshot excludes the `aidazi/` framework mount, the validator-regenerated
`docs/current/adoption-readiness.md`, and `.gitignore`.

### A/B — same canary, committed base vs fixed branch

| metric | pre-fix (`2062062`, committed main) | fixed (`feat/phase5-brownfield-preserve`) |
|---|---|---|
| exit code | **0 — falsely GREEN** | **2 — honestly NOT green** |
| pre-existing files snapshot | 2070 | 2070 |
| **governed docs drifted (mutated)** | **9** | **0** |
| governed docs removed | 0 | 0 |
| newly-created bootstrap files | 3 | 3 |
| `control_plane` errors before → after | 9 → 9 (masked away by clobber → green) | 9 → 9 (identical, surfaced) |

**Pre-fix drifted set (9):** `AGENTS.md`, `docs/requirements-ledger.json`,
`docs/current/{adoption-state, adoption-config, onboarding-record, implementation-stack,
runtime_invariants, domain_taxonomy, agent_context_guide}.md` — all replaced with generic
templates, which incidentally "fixed" airplat's control_plane errors by destroying the real
content, then reported GREEN.

**Fixed created set (3) — all genuinely absent in airplat, so a legitimate bootstrap, not drift:**
`.cursor/rules/00-aidazi-governance.mdc`, `.orchestrator/control/.gitkeep`,
`docs/research-briefs/RB-001-acme-widgets.md`.

### Pre-existing vs Phase-5 (the required distinction)

airplat's `control_plane_validator` reports **9 errors both before and after** `--force`
(identical set): `AGENTS.md` `@`-includes the full governance chain + docs outside the
control-plane allow list, and lacks a fenced ```control-plane-load``` block. These are **airplat's
own pre-existing adoption debt**, not introduced, changed, or fixed by adopter_init — the fixed
tool preserves them and honestly returns exit 2 so the human remediates airplat's AGENTS.md
itself. (This is a separate airplat remediation, out of scope for this framework fix.)

**Verdict:** PASS — zero governed-doc drift on the real adopter; pre-existing control_plane
findings unchanged and cleanly attributable to airplat, not Phase-5.

## Committed regression coverage (`engine-kit/tools/tests/test_adopter_init.py`)

- `test_force_preserves_governed_docs_byte_for_byte_and_stays_green` — greenfield scaffold →
  hand-edit AGENTS.md + `docs/current/*` (+ reserialise the JSON ledger to valid-but-different
  bytes) → `--force` re-run keeps every byte and stays green.
- `test_incompatible_existing_wiring_preserved_and_fails_not_rewritten` — a brownfield `CLAUDE.md`
  lacking the `@AGENTS.md` import is preserved byte-for-byte, the tool exits 2, and the wiring
  validator surfaces the breach (fail, don't rewrite).
- `test_overwrite_is_the_explicit_regenerate_escape_hatch` — `--overwrite` still regenerates.
- `test_materialize_report_created_then_preserved` — `MaterializeReport` created→preserved
  transition.
- `test_real_adopter_copy_zero_governed_drift` — env-gated (`AIDAZI_E2E_ADOPTER_BROWNFIELD_SRC`)
  version of the airplat-copy canary above (skipped offline).

## Gate history (Codex gpt-5.5 xhigh, whole-scope)

- **R1 → REVISE** (3 blocking): [B-1] `docs/current/adoption-readiness.md` refreshed every run with
  no `--overwrite` check — a silent second exception to the preserve contract; [B-2] `.gitignore`
  merged before the `overwrite` check, so `--overwrite` never regenerated it, contradicting the
  help text; [B-3] env-gated canary ignored `adopter_init`'s `rc`, so an exit-3 refusal could pass
  vacuously.
- **R2 fold** (`523d139`): [B-1] readiness snapshot made an explicit, documented, tested tool-owned
  exception (module contract + `run_exit_validators` comment + `test_readiness_snapshot_is_tool_
  owned_and_refreshed`); `materialize()` still never writes it. [B-2] `.gitignore` is intentionally
  always append-merged (never clobbered, even under `--overwrite` — dropping ignore patterns is a
  footgun); help/docstring corrected, `--overwrite` test extended to prove a custom ignore line
  survives. [B-3] canary now asserts `rc in (0, 2)`.
- **R2 → APPROVE** (findings: none): "R1 folds are resolved … preserve branches run after the
  target containment guard, overwrite remains explicit, incompatible preserved wiring exits
  non-green, report categories are coherent, and the canary distinguishes pre-existing
  control-plane findings from Phase-5 drift."

## Note — uncommitted alternative in the validate worktree

`~/projects/aidazi-phase5-validate` (branch `validate/phase5-adoption`, base `2062062`) carries an
**uncommitted** experimental guard (`materialize` raising *"dest is already an aidazi adopter —
regenerating would overwrite N governed doc(s) … pass --overwrite"*). That is a *refuse-entirely*
approach; this branch instead implements the *preserve-and-bootstrap* approach the task
specified (create missing, keep existing, fail-closed via validators). The experimental guard is
NOT part of committed main and is not adopted here.
