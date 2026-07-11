---
name: 2026-07-11-phase5-adopter-bootstrap-design
doc_category: intermediate
status: design-draft (pre-Codex-gate)
created: 2026-07-11
base_commit: f6d2730 (origin/main HEAD = PR #15 merge, Phase-4 parallel runner landed)
reviewer: >
  codex gpt-5.5 xhigh — PENDING (design gate R0). This doc reviews an UNIMPLEMENTED plan;
  the gate must judge design soundness, not code presence.
supersedes_roadmap: archive/2026-07-09-autonomy-roadmap-campaign-unblock.md §6 (Phase-5)
user_decisions_locked_2026-07-11:
  - target = Phase-5 (new-adopter bootstrap); Phases 1-4 done + merged to main
  - workflow = design gate → cluster-by-cluster impl (per-cluster Codex gate) → whole-scope R3
  - all real-CLI / network activity env-gated in a fresh worktree off origin/main
  - work branch = feat/phase5-adopter-bootstrap (worktree ~/projects/aidazi-phase5)
---

# Phase-5 — new-adopter bootstrap: `adopter_init.py` + cursor-wiring FAIL upgrade

**Goal (roadmap §6, distilled):** replace the 9-step manual ONBOARDING wizard with ONE
command — `engine-kit/tools/adopter_init.py` — that scaffolds every derivable adopter
artifact, prompts the human ONLY for the choices that are genuinely theirs (intent-contract
triple, autonomy+budgets, role harness/provider/model), surfaces a dead API key at answer
time instead of at Step 8, and exits with all four adoption validators GREEN (or a printed
remediation list). Plus the roadmap-mandated companion: **upgrade
`adopter_wiring_validator.py` so a `cursor` harness without a real `.cursor/rules` FAILS
(blocking), not WARNs** — so "validators green" finally proves cursor wiring.

**Why now:** every recent adopter (airplat) cost a debugging session at one of four known
onboarding stuck points — registry placeholder model (fixed Phase-1), missing
`CLAUDE.md`→`@AGENTS.md` wiring, ledger `surface` classification, and Facet-A reachability.
The governance discipline is sound; the on-ramp is not. Phase-5 is independent of the
1→2→3→4 runtime sequence (roadmap §7) and touches NO runtime gate — it is scaffolding +
one validator tightening.

**Non-negotiable framing:** nothing here weakens a MANDATORY_CHECKPOINT, acceptance
authority (Constitution §1.7-C), signed-scope freshness (Δ-19 F1), or the OW-M3 browser-E2E
mandate. The tool ORCHESTRATES the two-signature onboarding; it never signs. The one
validator change TIGHTENS (WARN→FAIL); it never relaxes.

---

## §0 Scope

### §0.1 In scope (this phase)
1. **`engine-kit/tools/adopter_init.py`** — one command scaffolding a green adopter from an
   answers file (deterministic/offline core) and, interactively, from TTY prompts.
2. **Cursor-wiring FAIL upgrade** to `engine-kit/validators/adopter_wiring_validator.py` +
   a defined `.cursor/rules` validity contract + test migration + collateral doc/inventory
   updates.
3. **Facet-A reachability probe** — env-gated live provider/key reachability check, plus the
   always-on offline capability validation (registry + harness-name denylist).
4. **Canaries**: a fully-offline scratch-repo canary (empty dir → 4 validators green in one
   invocation) in the normal suite, a brownfield fixture canary, and an env-gated live-probe
   canary. Evidence doc in `archive/`.
5. **ONBOARDING.md** rewrite: the tool becomes the path; the 9 steps stay as reference
   narrative; cursor moves WARN→FAIL in Step 8. Doc-reconciliation lockstep respected.

### §0.2 Explicitly OUT of scope (deferred, documented)
- No new runtime gate, no charter/campaign-plan schema change to the RUNTIME path (the only
  new schema is the tool's own answers file, §7.1).
- No auto-decompose of a requirement into a campaign backlog — that is Phase-2 (§3 of the
  roadmap), already landed; the bootstrap seeds inputs, it does not run the loop.
- No change to any of the 9 MANDATORY_CHECKPOINTS, acceptance mode, or the browser-E2E
  mandate.
- No migration tool for EXISTING adopters (airplat etc.) — they remain valid; the cursor-FAIL
  upgrade only affects an adopter that actually declares a cursor role (none do today —
  verified: airplat roles are cursor→remediated-to-`auto`/claude_code/codex per §1.4 of the
  roadmap). A brownfield `--force` re-run is offered but not a bulk migrator.
- The tool does NOT run the delivery loop or campaign; it ends at "validators green + first
  loop command printed" (Step 9 hand-off unchanged).

---

## §1 Current state (verified at base `f6d2730`; file:line refs)

### §1.1 Onboarding today = 14 manual steps, validated only at Step 8
`ONBOARDING.md` (832 lines) runs Step 0a→0→1→2→3→4→4a→4b→5→6→7→8→9. Artifacts are created
across Steps 0/4/4a/4b/6; the FOUR validators run only at **Step 8** (`ONBOARDING.md:686-744`).
Every derivable artifact is hand-instantiated from a template; the human's genuine choices
(intent triple Step 4 `:281`, role binding Step 5 `:483-528`, autonomy Step 7 `:651`) are
interleaved with mechanical copying.

### §1.2 The four exit validators (all `engine-kit/validators/`)
| Validator | Entrypoint | Validates | Green (exit 0) requires |
|---|---|---|---|
| `charter_validator.py` | `main(argv)` `:1794`; `charter.yaml [--schema][--campaign-plan]` | charter vs `schemas/mission-charter.schema.json` + semantic rules | `report.ok` (no errors) |
| `adopter_wiring_validator.py` | `main(argv)` `:657`; `<root> [--harness][--charter][--adoption-state]` | root-file harness wiring | `Report.ok = not self.errors` `:141-143` |
| `control_plane_validator.py` | `main(argv)` `:469`; `<root> [--state][--intents]` | `AGENTS.md` control-plane load block + load-graph exclusions | no errors |
| `adoption_status.py` | `main(argv)` `:556`; `<root> [--charter][--harness][--adoption-state][--write-readiness]` | AGGREGATE gate | `StatusReport.ok` `:93-97` |

`adoption_status.ok` (`:93-97`): NOT a framework repo AND no `REQUIRED` check in
`{missing,error,partial}`. Required artifacts (`validate_adoption` `:336-441`): `charter.yaml`,
`AGENTS.md` (filled — not `<adopter-name>` placeholder `:377-379`), `docs/current/{adoption-state,
implementation-stack,runtime_invariants,domain_taxonomy,agent_context_guide,onboarding-record,
adoption-config}.md`, `docs/current/adoption-readiness.md` (Step-8 snapshot `:413-418`),
`engine-kit/` present `:383-388`, harness wiring green `:390-397`, control-plane green `:399-408`,
a **signed research brief** `:420-425`, and `.gitignore` covering `.runs/` + `.env.local`
`:427-441`.

**Chicken-and-egg (load-bearing):** `adoption-readiness.md` is itself REQUIRED and is written
by `adoption_status.py --write-readiness` (`:417-418`). So the bootstrap must run
`adoption_status --write-readiness` to produce it, THEN the aggregate is green.

**Signed-brief predicate** `_brief_confirmed` (`adoption_status.py:253-286`): green when
`mission.brief`/`intent_contract.brief` points to a brief carrying `confirmed_by_human`/
`customer_signed: true`, OR (fallback) any brief in `docs/research-briefs/` carries the
confirmed marker (`:273-285`). This is a **constitutional gate-1 signature** — the tool must
NEVER auto-set it.

### §1.3 The cursor-wiring gap (roadmap R0 N-6 / R0.2 B-1)
`check_cursor` (`adopter_wiring_validator.py:489-497`) emits a non-blocking WARN
`cursor_not_applicable`. `ROOT_FILE_HARNESSES = ("claude_code","codex","cursor")` (`:85`);
dispatch table `_CHECKS` (`:576-580`) routes `cursor→check_cursor`, invoked in `validate_root`
(`:648-650`). Because `Report.ok = not self.errors` (`:141-143`) and `main` returns
`0 if report.ok else 1` (`:684`), an `error()` in `check_cursor` auto-flips exit — no other
plumbing changes. The verdict docstring (`:45-49`) lists "Cursor target" under WARN→exit-0.

**Normative source is thin.** `governance/context_briefing.md:74` §1.1: "a real Cursor rules
entry — a bare `AGENTS.md` is **not** Cursor wiring". There is NO codified content contract
(no "must reference AGENTS.md"). `.cursor/rules` in Cursor's convention is either a legacy
single file or a `.cursor/rules/` directory of `*.mdc` files. The repo's only `.mdc` is the
maintainer-only `.cursor/rules/00-codebase-map.mdc` (explicitly "not vendored to adopters").
`examples/minimal-greenfield/` ships `AGENTS.md`+`CLAUDE.md` but NO `.cursor/`. So Phase-5
must DEFINE cursor validity (§7.2).

**Three tests currently assert cursor=WARN/OK** (must migrate, §3.4):
`test_cursor_target_is_warn_not_pass` (`test_adopter_wiring_validator.py:304-311`),
`test_partial_overlap_is_not_conflict` (`:431-446`), `test_main_exit_codes` cursor branch
(`:461`). Collateral: docstring `:45-49`; constraint-inventory
`engine-kit/tools/constraint-inventory/04-context-briefing.yaml:76-82` (`cb-1.1-cursor-rules-entry`,
`current_enforcement: none-judgment`); `ONBOARDING.md:712-713` Step-8 WARN text.

### §1.4 Charter & registry facts
- `schemas/mission-charter.schema.json`: root `required=["mission","autonomy","budget","tooling"]`
  (`:7`). `intent_contract` is an OPTIONAL top-level block (`:366-377`) — NOT in
  `templates/mission-charter.yaml`; the tool synthesizes it. `confirmed_by_human` is a plain
  boolean (`:374`, no `const`). `autonomy.level` enum
  `[human_in_the_loop|human_on_the_loop|fully_autonomous_within_budget]` (`:47`);
  `autonomy.required=["level","approved_scope","auto_pass_rules"]` (`:42`); `approved_scope`
  three arrays each `minItems:1` (`:51`). `budget.required=["max_fix_rounds_total",
  "max_wall_clock_minutes"]` (`:147`). `tooling.required=["research","deliver","dev","review",
  "eval","acceptance"]` (`:157`). Per-role `$defs/agent_tooling` requires only `agent_kind`
  (`:415`); `harness/provider/model/capability_ref/api_key_env` optional.
  `acceptance.on_fix_required` requires `human_confirm_required` (`const:true` `:304-307`) +
  `route_options` (enum, `minItems:1` `:309-313`).
- `templates/mission-charter.yaml`: `autonomy.level: human_on_the_loop` (`:38`); roles under
  `tooling.<role>` carry `agent_kind/harness/provider/model/capability_ref` (`:95-99`); budgets
  in top-level `budget:` (`:83-86`). No `intent_contract`, no `max_concurrent`.
- **Offline capability gate (reusable):** `charter_validator._check_capability_gate`
  (`:1060-1293`) validates `(harness,provider,model)` vs `model-registry.yaml` + the
  denylist. `_HARNESS_NAME_MODEL_DENYLIST` (`:234-237`) =
  `{claude_code,claude,codex,cursor,cursor-agent,kimi,kimi_code,headless,aider,mock}`; ERROR
  `model_is_harness_name` (`:1147-1158`); unknown `(provider,model)` → WARN `model_unknown`
  (`:1193-1205`) because the registry is intentionally non-exhaustive.
- `engine-kit/validators/data/model-registry.yaml`: `models:` maps profile-id→record; a role's
  `capability_ref` names a profile-id. `cursor-agent-dev.model` is `auto` (Phase-1 fix, `:102`),
  `harness_compat:[cursor]` (`:107`).
- `ADAPTER_REGISTRY` (`engine-kit/adapters/__init__.py:18-25`) =
  `{mock,claude_code,headless,codex,kimi,cursor}`.

### §1.5 Facet-A reachability probe DOES NOT EXIST as code
No provider/model/API-key reachability function exists anywhere. `ONBOARDING.md:500-528`
describes an interactive human-present probe (`<cli> --version`, a zero-cost
`curl <endpoint>/models`) but there is NO reusable code. The adapter "…Probe" classes
(`ToolLeaseProbe`, `CodexStreamProbe`, `CursorStreamProbe`, `KimiStreamProbe`) are watchdogs
on ALREADY-SPAWNED processes — NOT reachability. Phase-5 must build the probe from scratch,
reusing only the offline `_check_capability_gate` for the deterministic half.

### §1.6 Doc-reconciliation lockstep (the one editing hazard)
`engine-kit/orchestrator/tests/test_alwaysload_doc_reconciliation.py` walks every tracked `.md`
(`_iter_markdown` `:130-136`) and FAILS if a line teaches the FULL canonical governance docs
(`constitution.md`/`doc_governance.md`) as "always-load"/`@`-included at cold-start without an
`on-demand` marker (detectors `alwaysload_violation_kind` `:105-127`). It carries ONE
**pre-existing RED** function `test_no_current_doc_teaches_full_canonical_as_always_load`
(`:140-152`) — DO NOT fix it; it is orthogonal. Editing `ONBOARDING.md` or shipping a
cursor-rules template is safe **iff** no new line names `constitution`/`doc_governance` with an
always-load lexeme and no `on-demand` marker. The scaffolded cursor rule references `AGENTS.md`
only — lockstep-safe by construction (§7.2).

### §1.7 Feasibility anchor — `examples/minimal-greenfield/` is a proven-green skeleton
`examples/minimal-greenfield/` is a SHIPPED reference adopter already exercised by
`test_control_plane_validator.py`, `test_adopter_wiring_validator.py`, and
`test_adoption_status.py`. It ships `AGENTS.md` (with the fenced ` ```control-plane-load ` block
at `:34`), `CLAUDE.md` (=`@AGENTS.md`), `charter.yaml`, `docs/current/{adoption-state,
agent_context_guide,domain_taxonomy,implementation-stack,runtime_invariants}.md`, and a signed
`docs/research-briefs/RB-001-refund-eligibility.md`. **So "make four validators green" is NOT
speculative — a green skeleton already exists.** The bootstrap = copy that skeleton's
wiring/control-plane/charter shape, fill the `<adopter-name>` placeholders, synthesize
`charter.yaml`+`intent_contract`+seed brief from the human's answers, and ADD the artifacts
minimal-greenfield lacks that `adoption_status` still requires:
`docs/current/onboarding-record.md`, `docs/current/adoption-config.md`, and
`docs/current/adoption-readiness.md` (the last via `--write-readiness`). This bounds C2's work
to a known-reachable target.

---

## §2 Design principles / invariants (fail-closed, mechanically testable)

- **I1 — Pure-core / IO-shell.** The artifact generator is a PURE function
  `build_artifacts(plan, framework_root) -> dict[relpath, content]`: no filesystem writes, no
  network, deterministic given `(plan, framework_root)`. All human/network I/O lives in a thin
  shell (`collect_answers_*`, `materialize`, `run_reachability_probe`,
  `run_exit_validators`). This mirrors Phase-4's pure-fold discipline and makes the scratch
  canary a fast offline unit test. (Analog of the Phase-4 single-writer rule.)
- **I2 — Single writer, never the framework repo.** `materialize()` is the ONLY function that
  writes to disk, and it REFUSES when `dest` is (or is inside) the framework repo — reuse
  `adoption_status.is_framework_repo`. Exit 3. A structural test proves no write path bypasses
  this guard (the Phase-5 analog of the Phase-4 AST guard, §10).
- **I3 — Never auto-confirm.** The tool NEVER sets `intent_contract.confirmed_by_human=true`
  or a research brief `customer_signed=true` on its own. Those come ONLY from the human
  (interactive) or from an explicit `confirmed_by_human` in the answers file (the canary
  author's recorded signature). If absent/false, the tool writes the field false and reports
  the signed-brief check as an outstanding remediation row — it does not fabricate a signature.
- **I4 — Offline-deterministic gate; env-gated live I/O.** The HARD exit gate is the four
  validators, which are 100% offline/deterministic. The live reachability probe is ADVISORY
  and runs ONLY when explicitly enabled (`--probe live` AND
  `AIDAZI_ADOPTER_INIT_LIVE_PROBE=1`); default depth is `off` for `--answers`/non-interactive
  and `binary` (a bounded `--version`, no network/key) for interactive. A dead key is a WARN +
  remediation row surfaced at answer time, never a crash, never a fabricated pass. This honors
  [[real-cli-env-gate-rule]]: the primary scratch canary is fully offline and runs in the
  normal suite; only the live-probe canary is env-gated.
- **I5 — Tighten-only validator change.** The cursor upgrade only ADDS a blocking error path;
  it removes no existing green case except the (incorrect) bare-AGENTS.md-as-cursor-wiring one.
  claude_code/codex/headless behavior is byte-identical.
- **I6 — Additive & idempotent.** Re-running on an existing dest (`--force`) is a no-op for
  already-correct artifacts (content-compare; write only on diff) and never clobbers a
  human-edited charter/brief without `--overwrite`. Greenfield (empty dest) is the default; a
  non-empty dest requires `--force`.
- **I7 — No new runtime coupling.** `adopter_init.py` imports the validators as libraries
  (`validate_root`, `validate_file`, `validate_adoption`) but adds NO import edge INTO the
  runtime/driver/campaign path. It is a leaf tool under `engine-kit/tools/`.

---

## §3 Cluster 1 — cursor-wiring FAIL upgrade (lands first; smallest, de-risks the validator)

**Rationale for ordering first:** self-contained, no dependency on the new tool, and it is the
roadmap's explicit correctness fix. Getting it gated first means C2's scaffolder can target a
validator that already enforces real cursor wiring.

**Changes:**
1. `adopter_wiring_validator.py::check_cursor` (`:489-497`) → detect `.cursor/rules` validity
   per the contract in §7.2 and emit a **blocking** `report.error(...)` on missing/invalid,
   nothing on valid. New rule ids: `cursor_missing_rules` (path absent) and
   `cursor_rules_invalid` (present but empty / symlink-escapes-root / dir with no non-empty
   `.mdc`). Reuse the existing `_is_symlink_redirect` helper (`:186-196`) for the escape check.
2. Verdict docstring (`:45-49`): move "Cursor target" from the WARN clause to the FAIL clause.
3. `_CHECKS` dispatch (`:576-580`) unchanged (already routes cursor).
4. **Constraint-inventory:** flip
   `constraint-inventory/04-context-briefing.yaml:76-82` `cb-1.1-cursor-rules-entry`
   `current_enforcement: none-judgment` → `validator:check_cursor` (or the repo's enforcement
   vocabulary — verify against a sibling `validator:*` entry). **GOTCHA (memory
   [[acceptance-auto-proposal-design]]):** editing a constraint-inventory file trips the
   `_sources.yaml` source-hash gate (kernel-coverage exit 1) → recompute the sha256 in
   `constraint-inventory/_sources.yaml` after the edit; run the kernel-coverage gate to confirm.
5. `ONBOARDING.md:712-713` Step-8 text: cursor moves from the WARN list to the FAIL list;
   add a one-line pointer to the `.cursor/rules` requirement (lockstep-safe wording).
6. Optionally tighten `context_briefing.md:74` §1.1 wording to name the validity contract
   (non-normative-preserving; defer if it risks the reconciliation gate).

**Test migration (§3.4):** the three WARN-asserting tests flip to error assertions or gain a
valid `.cursor/rules` fixture; add PASS fixtures (single-file and dir-of-`.mdc`) and FAIL
fixtures (absent / empty / symlink-escape) mirroring the `CodexTests`/`ClaudeCodeFailTests`
shape. Extend the `_RootBuilder` fixture helper to write `.cursor/rules` files/dirs.

**Cluster-1 Codex gate obligations:** (a) the new error truly blocks (exit 1) for a cursor
target lacking valid `.cursor/rules`; (b) claude_code/codex/headless exit codes byte-identical
to base; (c) the validity contract is neither over-strict (rejects a legitimate single-file
`.cursor/rules`) nor under-strict (accepts an empty file); (d) constraint-inventory sha
refreshed so kernel-coverage stays green; (e) no reconciliation-lockstep regression.

---

## §4 Cluster 2 — `adopter_init.py` scaffolding core (answers-driven, offline)

The pure generator + single-writer materializer + validator integration + non-interactive CLI.
NO interactive prompts, NO live probe (that is C3). This cluster alone must satisfy the
roadmap "Done" bar: `adopter_init --answers a.json <empty-dest>` → four validators green.

### §4.1 CLI surface
```
python engine-kit/tools/adopter_init.py <dest> \
  --answers <answers.json>       # REQUIRED in C2 (interactive added in C3)
  [--framework-root <path>]      # source of engine-kit/ + schemas/ + templates/ (default: auto-derive from this file's location)
  [--force]                      # allow a non-empty dest (brownfield); default requires empty dest
  [--overwrite]                  # allow replacing a human-editable artifact (charter/brief) that already exists
  [--dry-run]                    # print the artifact manifest + planned validator run; write nothing
  [--probe {off}]               # C2 supports only off; C3 adds binary|live
```
**Exit codes:** `0` all four validators green; `2` validation failed (per-validator remediation
printed); `3` refused (dest is framework repo / non-empty without `--force` / answers invalid).

### §4.2 Architecture (I1/I2)
- `AdopterPlan` dataclass — the fully-resolved answers (§7.1 schema): `adopter_name`, `track`,
  `greenfield`, `intent_contract{goal,standard,proof_of_done,confirmed_by_human,confirmed_at}`,
  `autonomy{level,budget{...}}`, `roles{research,deliver,dev,review,eval,acceptance:
  {harness,provider,model,capability_ref,api_key_env?}}`, optional `research_brief{...,
  customer_signed}`.
- `load_answers(path) -> AdopterPlan` — parse + validate the answers JSON against
  `schemas/adopter-init-answers.schema.json` (§7.1); reject on schema error (exit 3).
- `build_artifacts(plan, framework_root) -> dict[relpath, content]` — PURE. Emits every
  derivable artifact (§4.3). No writes, no network.
- `materialize(artifacts, dest, framework_root, *, force, overwrite) -> None` — the ONLY
  writer. Refuses framework-repo dest (I2). Writes each file tmp+rename; copies the
  `engine-kit/` + `schemas/` + `templates/` trees; vendors default skills (reuse the Step-6.6
  vendoring path / `skills/registry.yaml`+`skills.lock`). Idempotent (I6).
- `run_exit_validators(dest, plan) -> GreenReport` — imports and runs, in order:
  `charter_validator.validate_file`, `adopter_wiring_validator.validate_root`,
  `control_plane_validator.validate_root`, then `adoption_status` WITH `--write-readiness`
  (to resolve the chicken-and-egg §1.2), and finally re-reads the aggregate. Prints a
  consolidated PASS/FAIL table + remediation list; returns green iff `adoption_status.ok`.

### §4.3 Artifact manifest (what `build_artifacts` emits)
All required by `adoption_status` (§1.2) unless noted:
1. `charter.yaml` — from `templates/mission-charter.yaml`, with the human choices substituted:
   `mission.id/goal`, `autonomy.level`, `budget.*`, per-role `tooling.<role>.{harness,provider,
   model,capability_ref}`, and a synthesized top-level `intent_contract` block (I3 — confirmed
   flag from `plan` only). `mission.brief` points at the seed brief (§4.3.9).
2. `AGENTS.md` — from the root consumer template with `<adopter-name>` filled (else
   `adoption_status._agents_has_placeholder` blocks `:377-379`); MUST contain the
   control-plane-load block `control_plane_validator` requires (`:478-479`).
3. `CLAUDE.md` — literally `@AGENTS.md` when any role uses `claude_code`
   (`adopter_wiring_validator` claude check).
4. `.cursor/rules/00-aidazi-governance.mdc` — WHEN any role uses `cursor` (§7.2). Satisfies the
   C1 validity contract.
5. `docs/current/{implementation-stack,runtime_invariants,domain_taxonomy,agent_context_guide,
   adoption-config}.md` — from their templates (`templates/implementation-stack-template.md`,
   `templates/adoption-config-template.md`; the other three from their consumer templates),
   filled with adopter name/track. All REQUIRED by `adoption_status`.
6. `docs/current/adoption-state.md` — from `templates/adoption-state-template.md`, including the
   optional `<!-- adopter-root-harness: … -->` marker so wiring detection is unambiguous.
7. `docs/current/onboarding-record.md` — the audit ledger, pre-populated with the tool's own
   run rows (each step + probe result).
8. `docs/requirements-ledger.json` — from `templates/requirements-ledger.example.json` (seed;
   OW-2/OW-3 default-on). Not itself an `adoption_status` REQUIRED file but part of the
   default-on ledger surface; emitted for a complete adopter.
9. `docs/research-briefs/<id>.md` — a seed research brief synthesized from the intent contract,
   carrying `customer_signed` = `plan.research_brief.customer_signed` (I3; NEVER forced true).
   This is what `_brief_confirmed` (`:253-286`) reads. Charter `mission.brief` references it.
10. `.gitignore` — ensure it covers `.orchestrator/`, `.runs/`, `.env.local`/`*.local`
    (`adoption_status` `:427-441`).
11. `.orchestrator/control/` + `.orchestrator/audit/` scaffolding (Step-6.7 shape).
12. `docs/current/adoption-readiness.md` — NOT emitted by `build_artifacts`; produced by
    `run_exit_validators` via `adoption_status --write-readiness` (§1.2 chicken-and-egg).

`engine-kit/`, `schemas/`, `templates/`, and vendored `skills/` are COPIED by `materialize`
from `framework_root` (not returned by the pure generator — they are trees, not text).

### §4.4 The intent-contract / signed-brief handling (I3 restated concretely)
`plan.intent_contract.confirmed_by_human` and `plan.research_brief.customer_signed` MUST be
supplied by the human/answers. `build_artifacts` copies them verbatim. If either is not true,
`run_exit_validators` will report `signed research brief` as `partial` (blocks) — a truthful
remediation, not a fabricated pass. The canary answers file carries `true` as the canary
author's recorded signature (evidence doc), exactly as the Phase-1 real-campaign canary signed
its intent contract (roadmap §2.D).

**Cluster-2 Codex gate obligations:** (a) `materialize` into an empty tmp dest → all four
validators exit 0; (b) I2 framework-repo refusal proven (no write when `dest` is the framework
repo); (c) `build_artifacts` is pure (same input → byte-identical map; no I/O — provable by
running it with the filesystem/network unavailable or by a no-fd test); (d) I3 — with
`confirmed_by_human:false` in answers the tool does NOT emit a green signed brief; (e) a cursor
role yields a `.cursor/rules` that passes the C1 validator; (f) idempotent `--force` re-run
(no spurious diffs).

---

## §5 Cluster 3 — interactive layer + Facet-A reachability probe (env-gated live I/O)

### §5.1 Interactive answer collection
`collect_answers_interactive(framework_root) -> AdopterPlan` — TTY prompts for ONLY the genuine
choices (recommend-then-confirm, matching ONBOARDING's tone):
- intent triple (goal/standard/proof_of_done) + an EXPLICIT confirm step that sets
  `confirmed_by_human` (I3 — the human types confirmation; the tool never defaults it);
- autonomy level (default `human_on_the_loop`) + budgets;
- per-role harness/provider/model/capability_ref, each validated at answer time against the
  registry + denylist via `_check_capability_gate` (offline) so a bogus model is rejected
  before the human moves on;
- track (Type A/B/C), greenfield/brownfield.
Everything else is derived. `--emit-answers <path>` dumps the collected `AdopterPlan` as a
canonical answers.json (for reuse / canary authoring). Non-TTY stdin → error directing the user
to `--answers`.

### §5.2 The reachability probe (`run_reachability_probe(plan, depth) -> ProbeReport`)
Three depths (I4):
- `off` — no probe; offline capability validation still runs. Default for `--answers`.
- `binary` — for CLI harnesses, a bounded `<cli> --version` (proves the binary is on PATH; NO
  network, NO key). Default for interactive. Uses the same bounded-subprocess discipline as the
  adapters (timeout; never unbounded).
- `live` — env-gated: runs ONLY when `--probe live` AND `AIDAZI_ADOPTER_INIT_LIVE_PROBE=1`.
  For `headless`/HTTP roles: a bounded zero-cost `GET <endpoint>/models` using `api_key_env`
  (loads `.env.local`); for CLI harnesses: a minimal bounded real dry-invoke (e.g.
  `codex --version`/account probe). Every live call is timeout-bounded, its outcome audited as
  an `onboarding-record.md` row, and a failure becomes a WARN + remediation row surfaced at
  answer time — NEVER a crash, NEVER a fabricated validator pass. The human may proceed and
  record a `divergent` row (a machine may be offline while configuring).

**Why advisory, not blocking:** the hard gate is Step 8's offline validators (I4). The probe's
job is EARLY surfacing ("dead key at answer time, not Step 8" — roadmap §6), not a new gate.

**Cluster-3 Codex gate obligations:** (a) live probe NEVER runs without the env flag (proven by
a test that asserts no network call when the flag is unset); (b) probe failure never crashes
the tool or fabricates a pass; (c) offline capability validation rejects a harness-name model
at answer time; (d) interactive flow with scripted stdin produces an `AdopterPlan` identical to
the equivalent answers file; (e) `--emit-answers` round-trips (`--emit-answers` then
`--answers` on the emitted file → identical tree).

---

## §6 Cluster 4 — canaries + ONBOARDING rewrite + whole-scope R3

### §6.1 Scratch-repo canary (OFFLINE, normal suite)
`examples/adopter-init-canary/answers.json` — a schema-valid answers file for a small adopter:
all roles `claude_code` EXCEPT one role bound to `cursor` (to exercise the `.cursor/rules`
scaffold + the C1 validator on the happy path), `confirmed_by_human:true` +
`research_brief.customer_signed:true` (canary author's recorded signature). Test
(`engine-kit/tools/tests/test_adopter_init_canary.py`, NORMAL suite — no env gate, fully
offline): create an empty `tmp_path` dest → `adopter_init --answers … --probe off <dest>` →
assert exit 0 AND independently re-run all four validators against `dest` asserting each exits
0. This is the roadmap's "empty dir → validators green in one sitting" done-evidence.

### §6.2 Brownfield canary (OFFLINE, normal suite)
A fixture repo (pre-existing `src/`, `README.md`, a partial `.gitignore`) → `adopter_init
--answers … --force <fixture>` → four validators green, and the pre-existing files are
untouched (I6). Proves `--force` non-destructiveness.

### §6.3 Live-probe canary (ENV-GATED)
`AIDAZI_E2E_ADOPTER_INIT_LIVE=1` + `AIDAZI_ADOPTER_INIT_LIVE_PROBE=1` → runs the interactive/
answers path with `--probe live` against a real reachable key, asserting the probe records a
reachable row; and a second arm with a deliberately-bad key asserting the WARN+remediation row
at answer time (no crash). Skipped offline (like the Phase-1 real-campaign canary). Evidence
doc `archive/2026-07-11-phase5-adopter-init-canary-evidence.md`.

### §6.4 ONBOARDING.md rewrite (doc-reconciliation lockstep respected, §1.6)
Add an up-front "Fast path" section: `python engine-kit/tools/adopter_init.py <dest>` does
Steps 0–8 in one command; the numbered steps remain as the reference narrative and the manual
fallback. Update Step 8 for cursor WARN→FAIL (C1). NO line may teach the full canonical
constitution as always-load (§1.6) — verify with the reconciliation test after editing.

### §6.5 Whole-scope R3
After C4, a whole-scope Codex R3 catches cross-cluster/integration issues the per-cluster gates
can't: does the scaffolded tree ACTUALLY satisfy every `adoption_status` REQUIRED check (not
just the ones each cluster tested)? Does the cursor scaffold+validator agree end-to-end? Is the
signed-brief path honestly gated? Is there any write path that bypasses I2?

---

## §7 Data contracts

### §7.1 `schemas/adopter-init-answers.schema.json` (NEW; the only new schema)
`additionalProperties:false`, `required=["adopter_name","track","intent_contract","autonomy",
"roles"]`.
- `adopter_name`: non-empty string.
- `track`: enum `[type_a,type_b,type_c,type_a_b_hybrid]`.
- `greenfield`: boolean (default true).
- `intent_contract`: `{goal,standard,proof_of_done: non-empty string; confirmed_by_human:
  boolean; confirmed_at: string|null}` — mirrors `mission-charter.schema.json:366-377`.
- `autonomy`: `{level: <the charter enum>; budget:{max_fix_rounds_total:int,
  max_wall_clock_minutes:int, max_api_usd?:number}}`.
- `roles`: object with all six charter roles; each
  `{harness: <ADAPTER_REGISTRY key>, provider, model, capability_ref?, api_key_env?}`.
- `research_brief`: optional `{title,summary,closure_contract?,customer_signed:boolean,
  sign_off_date?:string|null}`.
The tool validates answers against this schema BEFORE building (fail-closed, exit 3). Being the
tool's own contract, it adds no runtime-path schema surface (§0.2).

### §7.2 `.cursor/rules` validity contract (consumed by C1 validator + emitted by C2)
Valid ⟺ `<root>/.cursor/rules` exists AND is one of:
- a **regular file** that is non-empty (after strip) and not a symlink escaping root; OR
- a **directory** `<root>/.cursor/rules/` containing ≥1 non-empty `*.mdc` regular file (none
  a symlink escaping root).
Invalid ⟺ absent (`cursor_missing_rules`), or present-but-empty / dir-with-no-nonempty-`.mdc` /
symlink-escape (`cursor_rules_invalid`). NO content contract beyond non-empty (the repo defines
none, §1.3); the scaffolded file references `AGENTS.md` as a courtesy, not a validator
requirement. This keeps the validator honest about what the codebase actually mandates.

**Scaffold content** (`build_artifacts`, lockstep-safe — names only `AGENTS.md`, §1.6):
```
---
description: aidazi governance — load AGENTS.md at session start
alwaysApply: true
---
This repository is governed by the aidazi delivery engine. At the start of every session,
load ./AGENTS.md and follow its control-plane load directive before doing any work.
```

### §7.3 Cursor-rules TEMPLATE location decision
The scaffold body is an inline string constant in `adopter_init.py` (NOT a tracked `.md`/`.mdc`
template file) — so it can never be walked by the reconciliation test (§1.6) and there is no
risk of an in-repo template accidentally counting as maintainer cursor wiring. (Rationale: the
one existing `.mdc` in the repo is maintainer-only; a `templates/cursor-rules.*` file would be
a tracked doc subject to the always-load walk. An inline constant sidesteps both.) VERIFY
during C1 whether `_iter_markdown` globs `*.mdc` (if it only globs `*.md`, this is belt-and-
suspenders; keep the inline constant regardless.)

---

## §8 Gotchas / risks / open questions for the gate

- **G1 — engine-kit copy cost.** `materialize` copies the whole `engine-kit/`+`schemas/`+
  `templates/` trees; the offline canary pays that once into `tmp_path` (~seconds). Acceptable;
  note it so the gate doesn't flag test slowness. Alternative (symlink) rejected —
  `adoption_status` only checks presence, but a copy is what a real adopter gets and is safest.
- **G2 — constraint-inventory sha gate (C1).** Editing `04-context-briefing.yaml` REQUIRES
  refreshing `_sources.yaml` sha256 or `--kernel-coverage` exits 1. Non-obvious; called out in
  §3.4.
- **G3 — signed-brief honesty (I3).** The single biggest correctness trap: making the canary
  green must NOT tempt an auto-confirm. The design routes the signature exclusively through
  `plan` and treats a false/absent flag as a truthful `partial`. The gate must confirm no code
  path forces `customer_signed`/`confirmed_by_human` true.
- **G4 — cursor validity over/under-strictness.** §7.2 accepts both the legacy single-file and
  the modern dir-of-`.mdc` shapes to avoid false-failing a legitimate adopter; rejects empty.
  The gate should stress both boundaries.
- **G5 — brownfield idempotency.** `--force` must not clobber a human-edited charter/brief
  (only `--overwrite` may). Verified by the brownfield canary (§6.2).
- **G6 — live probe env-gate.** Must be impossible to make a network call without the env flag
  (I4). Proven by a no-network assertion test (C3 obligation a).
- **Q1 (for the gate):** should the tool ALSO run the campaign-plan validator if the adopter
  opts into a seed campaign? Proposed: NO — the bootstrap stops at delivery-loop readiness; a
  campaign plan is a later, separately-signed artifact (§0.2). Confirm.
- **Q2 (for the gate):** should `--emit-answers` from an interactive run be considered a
  supported reproducibility contract (canary authoring path)? Proposed: YES, and C3 obligation
  (e) tests it. Confirm.

---

## §9 Acceptance criteria & sequencing

| Cluster | Done-evidence | Gate |
|---|---|---|
| C1 cursor-FAIL | cursor-without-`.cursor/rules` → validator exit 1; claude/codex/headless byte-identical; inventory sha refreshed; suite green | Codex impl gate C1 |
| C2 scaffold core | `adopter_init --answers <empty> ` → 4 validators exit 0; I2/I3 proven; pure `build_artifacts` | Codex impl gate C2 |
| C3 interactive+probe | scripted-stdin plan == answers plan; live probe env-gated (no-network proof); dead-key WARN at answer time | Codex impl gate C3 |
| C4 canaries+docs | offline scratch canary green in normal suite; brownfield canary; env-gated live-probe evidence; ONBOARDING points at tool; reconciliation lockstep intact | Codex impl gate C4 |
| whole-scope | every `adoption_status` REQUIRED check truly satisfied by the scaffold; no I2 bypass; honest signed-brief | Codex R3 |

**Sequencing:** C1→C2→C3→C4 (C2 targets the C1-tightened validator; C3 adds the human/live
layer atop C2's core; C4 proves the whole). Each cluster: implement → Codex impl gate (fold
every `[B-#]`, iterate to APPROVE) → next. After C4: whole-scope R3. Then push +
`gh pr create` for HUMAN merge. Suite baseline: full `cd engine-kit && python3.12 -m pytest`
(~95s) must stay green except the 1 pre-existing README red
(`test_no_current_doc_teaches_full_canonical_as_always_load`) which is NEVER fixed here.

## §10 Test plan (per cluster)
- **C1:** migrate 3 WARN tests; add PASS (single-file, dir-of-`.mdc`) + FAIL (absent, empty,
  symlink-escape) cursor fixtures; assert exit codes; assert claude/codex/headless unchanged;
  run `--kernel-coverage` after inventory sha refresh.
- **C2:** `build_artifacts` purity (deterministic, no I/O); `materialize`→4-validators-green in
  tmp; I2 framework-repo refusal (assert no write); I3 false-flag → partial signed-brief;
  cursor role → valid `.cursor/rules`; idempotent `--force`.
- **C3:** scripted-stdin == answers plan; offline capability rejection at answer time; live
  probe no-network-without-flag assertion; dead-key WARN-not-crash; `--emit-answers` round-trip.
- **C4:** offline scratch canary (normal suite); brownfield canary; env-gated live-probe
  canary; ONBOARDING reconciliation test green (except the known pre-existing red).
- **Structural (I2 guard):** a test enumerating every `open(...,'w')`/write path in
  `adopter_init.py` routes through `materialize` and its framework-repo guard (Phase-5 analog
  of the Phase-4 AST guard).

## §11 What this phase deliberately does NOT do
No runtime-gate change; no MANDATORY_CHECKPOINT change; no acceptance-mode change; no bulk
migration of existing adopters; no auto-signing; no campaign auto-decompose (Phase-2, already
shipped); no charter/campaign-plan runtime-schema change. The ONLY behavioral tightening is
cursor WARN→FAIL, which no current adopter trips.
