---
title: "Universal skill mounting — session handoff after Phase 2 (Phases 0-2 DONE, each Codex-APPROVED; next: Phase 3 on human go)"
doc_tier: archive
doc_category: handoff
status: recorded
date: 2026-07-06
scope: session handoff — docs-only commit; the authoritative contract is archive/2026-07-06-universal-skill-mounting-design.md
---

# Handoff — universal deterministic skill mounting + consumption observability + bounded efficacy canary

**Resume point: begin PHASE 3 on the existing branch, on explicit human go.** Phases are
strictly sequential; each ends with a Codex gpt-5.5 xhigh gate APPROVE before the next, and the
human has been authorizing each phase individually.

## §1 Where everything is

- **Branch:** `feat/universal-skill-mounting`, HEAD `bad1d61`, base `origin/main` @ `9f392e4`.
  8 commits, clean tree, **NOT pushed**. No adopter (AirPlat) changes anywhere.
- **The frozen contract (single source of truth):**
  `archive/2026-07-06-universal-skill-mounting-design.md` — design §2 (D1 signal authority),
  §3 (D2 telemetry), §4 (D3 preflight severity), §5 (sequential phases), §6 (never-touch),
  §7 (FROZEN Phase-5 pre-registration — any change ⇒ back to Phase 0 + new gate), §8 (the 4
  human implementation guardrails).
- **Frozen pre-registration artifact bytes:** `archive/wp-skill-canary/preregistration/`
  (2 α fixture briefs, `alpha-manifest.json`, `gamma-task-prompt.md`, `gamma-checklist.json`).
- **Motivating investigation:** `archive/2026-07-06-skill-integration-investigation.md`
  (on the separate unmerged branch `docs/skill-integration-investigation` @ `6a2e34e`).
- **Plan file (session-local, non-authoritative):** `~/.claude/plans/shiny-sauteeing-wirth.md`.

## §2 Commit map (all on the feature branch)

| Commit | Phase | Content |
|---|---|---|
| `0c08cc3` | P0 | design contract committed |
| `aeacf9a` | P0 | P0-gate R1 fixes (unique `interaction` signal → one-skill canary; frozen α manifests; γ Check-0 completeness) |
| `4fa39af` | P0 | P0-gate R2 fix (exact pre-registration bytes committed) — P0 gate R3 **APPROVE** |
| `655c34a` | P1 | schemas: charter `approved_scope.task_signals` + campaign `milestone_signals` + signoff digest fields; mission-charter compact regen (lockstep); 5-schema enum drift-guard |
| `86d8e3d` | P1 | campaign authority: presence-keyed digest; stamp_signoff binds top-level + authenticated-snapshot copy; central freshness via `signoff_status` + `f1_required` signals trigger; fail-closed ingress; `derive_milestone_context(milestone_signals=)` union projection; conditional-kwarg dispatch threading |
| `677f8a7` | P1 | driver: `_task_context_for` most-specific-wins (plan entry EXCLUSIVE incl. signed omission; charter tier for research/deliver-decompose/delivery_only spawns; acceptance excluded); `signal_source` audit; WARN `skill_compat_skip`; conditional decompose profile line; resolver compat defense-in-depth; validator `_check_mission_signal_profile` |
| `9a52cde` | P1 | TD6 pure-helper interplay regressions |
| `650cda5` | P1 | P1-gate R1 fix: **`_restamp_followup_epoch` carries the signed digest through the LIVE TD6 restamp** (refuses signal drift); live campaign followup scenario; **worktree-A/B-proven byte-identical golden** (`tests/fixtures/golden-signal-free-prompts.json` + regression test); full audit coverage — P1 gate R2 **APPROVE** |
| `bb1d995` | P2 | `SpawnResult{result, telemetry}` envelope across all six adapters (`_spawn_impl` rename + base normalization); claude_code `parse_read_paths` (WP-3 pattern, terminal attempt only); `run_with_monitor` stamps `proc.aidazi_attempt`; BOTH driver call sites unpacked (`_spawn` ~:1174 + acceptance ~:4979); legacy-dict shim + WARN `adapter_legacy_return`; frozen telemetry→audit mapping (`_skill_consumption_fields`); audit-event schema additive fields; raw-stream `__stream.jsonl` transcripts under `AIDAZI_KEEP_RAW_STREAM=1`; non-contamination test suite |
| `bad1d61` | P2 | P2-gate R1 fix: `SPAWN_PAYLOAD_FIELDS` lockstep (audit_report renders consumption evidence); acceptance-flow telemetry test; real monitor attempt-stamp test — P2 gate R2 **APPROVE** |

## §3 Gate history (all Codex gpt-5.5 xhigh via `engine-kit/tools/review_runner.py`)

Design: R1 REVISE(6) → R2 REVISE(3) → R3 **APPROVE** · P0: R1 REVISE(3) → R2 REVISE(1) → R3
**APPROVE(0/0)** · P1: R1 REVISE(1+3NB) → R2 **APPROVE(0)** · P2: R1 REVISE(1+2NB) → R2
**APPROVE(0/0)**. Human approvals on record: plan (with 7 blocking corrections), execution
(with 4 guardrails, §8 of the contract), Phase-0 sign-off, Phase-1 go, Phase-2 go.

## §4 Verification state at handoff

Suite (clean run): **1765 passed / 1 pre-existing failure / 10 env-gated skips**. The single
red is main's KNOWN pre-existing README/WP-2 always-load reconciliation item
(`test_alwaysload_doc_reconciliation`, README.md:122/341) — NOT from this branch; parked (see
§7). Content gates all green: kernel coverage 74/74; acceptance-kernel coverage OK; acceptance
load-closure `closed:true`; WP-9 `--strict` OK; mission-charter compact lockstep OK;
acceptance-lockstep tests green. Prompt bytes for signal-free flows PROVEN byte-identical to
pre-Phase-1 (worktree A/B vs `4fa39af`) and guarded by the golden fixture test. NOTE: one
loaded-machine suite run showed a transient extra timing failure (suite concurrent with an
xhigh gate, 16:50 runtime) that does NOT reproduce on a clean run — re-run before trusting a
2-failure result.

## §5 NEXT: Phase 3 — integrity/drift preflight (contract §4/D3)

New `engine-kit/validators/skills_preflight.py` + wiring + CLI + severity tests. Key
implementation facts already verified this session:

- **REUSE `skill_vendor.verify()`** — a complete offline lock-integrity checker ALREADY EXISTS
  (`engine-kit/skill-vendor/skill_vendor.py` — `verify()` :295, CLI `verify` subcommand :439;
  the lock's hash algorithm is `tree_sha256` :130, sha256 over a shasum-style per-file manifest
  EXCLUDING `_provenance.yaml`). Do NOT use `effective_role_config._tree_hash` (Codex design-R1
  finding F1: it would false-fail valid trees).
- **Severity table (frozen, contract §4):** (1) skills.lock vs vendored tree mismatch → HARD
  FAIL (real runs); (2) required registry skill missing/unresolvable → HARD FAIL; (3) real-loop
  submodule working-tree commit ≠ recorded superproject gitlink → **HALT/fail closed unless an
  explicit audited override flag** (audit event carrying both commits) — the AirPlat class is
  never warning-only; (4) adopter pin behind upstream / newer upstream skills → advisory WARN
  only; (5) read telemetry unavailable → informational `unobservable`, never a human
  manual-check.
- **run_loop wiring homes (verified):** campaign — `run_campaign_entry` after the `enforce_*`
  calls (engine-kit/scheduling/run_loop.py:679-689); single-loop — after charter validation /
  adapter-build guard (:1186-1197 / :926-928). Pattern to mirror:
  `enforce_required_capabilities_for_real_run` (raises CharterValidationError → INVALID exit).
- Advisory-except-integrity; plus a standalone CLI for adopters. Tests: severity rows incl.
  the audited-override path. Then the Codex Phase-3 gate before Phase 4b.

## §6 Remaining phases after P3 (contract §5)

- **P4b** — vendored scratch-adopter offline proof, TWO fixtures (Codex design-R1 F3):
  (i) `full_chain_guided` single-loop (Research + Deliver-decompose spawns w/ charter mission
  profile); (ii) campaign `delivery_only` (signoff-bound `milestone_signals` → derived-charter
  union → delivery-only spawns). Real `vendor-framework.sh` into a temp adopter + MockAdapter;
  states 1-3 byte-level; negative arms (byte-identical / out-of-vocab / tampered lock / gitlink
  drift + override / post-sign mutation ⇒ stale).
- **P5** — the bounded real/billable canary per the FROZEN §7 pre-registration (α/β/γ probes;
  `interaction` signal → exactly `web-interface-guidelines`; paired counterbalanced A/B;
  deterministic scorer ≡ `gamma-checklist.json`; env gates `AIDAZI_SKILL_CANARY=1` +
  `AIDAZI_ALLOW_REAL_ADAPTER=1` + `AIDAZI_KEEP_RAW_STREAM=1`; NOT `AIDAZI_E2E_EXTERNAL_RUNNER`).
  **Requires SEPARATE explicit human approval (billable) — never start it on a mere phase-go.**
- **P6** — docs + closure: `process/role-skill-model.md` edits ONLY under the full lockstep set
  (`_sources.yaml` sha refresh + `--kernel-coverage` + acceptance load-closure re-run
  (role-skill-model is on its RETIRED_FILES surface, acceptance_load_closure.py:56) +
  `--acceptance-kernel-coverage`; preserve REQUIRED_ANCHORS §4 #1-#5/§6); ONBOARDING
  framework-version floor note; completion record; FINAL whole-scope Codex gate. No
  push/PR/merge/exposure before final whole-scope approval + human authorization.

## §7 Standing constraints & parked items

- **Never-touch (acceptance LOAD-CLOSURE):** governance/constitution-core.md | constitution.md
  | authoring-kernel.md | doc_governance.md | context_briefing.md | role-cards/* |
  templates/compact-acceptance-prompt.md | framework AGENTS.md | schemas/acceptance-verdict*.
- **Locked decisions:** deterministic selection only; existing catalog + 6-word UI vocab;
  unconditional role_defaults; no agent self-report as consumption evidence; honest
  `unobservable`; no network skill fetch; no autonomous Acceptance skill selection; no AirPlat
  changes; manual edit approval, no permission bypass; agent memory non-authoritative (durable
  state = repo artifacts like THIS doc).
- **Parked (user-owned, separate from this initiative):** (a) the pre-existing README/WP-2
  always-load red on main (the user's ORIGINAL session request item 1 — README.md:122/341
  wording fix + reconciliation test green); (b) release tag v5.1 (original item 2); (c) AirPlat
  pin migration (adopter-migration item per the investigation record §8); (d) M-Skill-2/3
  follow-ups (vocab/catalog expansion, conditional defaults, general efficacy, adaptive
  selection).

## §8 Operational notes for the next session

- Gates: compose prompt → `python3 engine-kit/tools/review_runner.py --timeout 2400 --attempts 2
  --mandatory --prompt-file <f> --capture-dir <d> -- codex exec --json -o <d>/verdict.md
  -m gpt-5.5 -c model_reasoning_effort=xhigh -s read-only --skip-git-repo-check` (background;
  needs sandbox-network override). Include verified fix summaries + "verify against the code"
  + the mandatory VERDICT format block.
- Tests run with `python3.12` (plain `python3` lacks PyYAML). Full suite ~4 min unloaded from
  `engine-kit/`: `python3.12 -m pytest -q`. Don't run the suite concurrently with an xhigh gate
  (timing flakes).
- RTK proxies shell commands; use `rtk proxy grep ...` for raw grep; some outputs get truncated
  — verify surprising results with a second command.
- Per-phase gate checklist: full suite + `kernel_equivalence.py --kernel-coverage` +
  `--acceptance-kernel-coverage` + `acceptance_load_closure.py` (`closed:true`) +
  `context_budget_report.py --strict` + `test_e2e_acceptance.py` + the golden signal-free
  prompt test + (since P2) the two-call-site `adapter.spawn(` grep.

*End of handoff.*
