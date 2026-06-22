# aidazi v2-loop-engine — Context Handoff Pack

> Transferable context for a NEW agent/session to continue the v2 loop-engine build.
> Date: 2026-06-16 · Branch: `v2-loop-engine` · Repo: `/Users/caoruixin/projects/aidazi`
> Read this + the master plan `archive/2026-06-15-v2-loop-engine-plan.md` first; then continue.

---

## 1. 背景 (Background)

- **aidazi** is a spec-driven, *governed*, multi-agent framework for LLM-first software delivery. It is **NOT a runtime** — "no aidazi server you deploy"; the runtime is the adopter's.
- **Origin of this effort**: the "Loop Engineering" thesis (Boris Cherny: *"my job is to write loops"*; Addy Osmani's anatomy = automations, worktrees, skills, connectors, sub-agents, external memory). aidazi already *specified* most of that anatomy + adds governance rigor the thesis lacks, but originally shipped **zero executable code**.
- **The v2-loop-engine line compiles the spec into a runnable loop engine on the ADOPTER side** via a copyable `engine-kit/`, while keeping aidazi itself spec-driven.
- Source articles that triggered this (for reference only, fully digested): a QQ news piece on 循环工程/Loop Engineering; a YouTube talk "Boris Cherny — Loop 时代" (title only retrievable); an X post by @shao__meng (HTTP 402, unfetchable — a Chinese repost of the same Osmani/Cherny thesis).
- Model in use: Opus 4.8.

---

## 2. 目标 (Goals — North Star, LOCKED)

1. **aidazi stays a spec-driven framework.** Distribution model = **Spec + copyable engine-kit**:
   - `governance/ process/ modules/ schemas/` = **NORMATIVE source-of-truth**.
   - `engine-kit/` = **reference implementation**, non-normative, adopter-copyable.
   - **Conflict rule: spec wins; the kit is then a bug.** (Precedent: `skills/anti-hardcode-review-kernel/` declares "normative source stays in templates/".)
2. **Realized via adoption** into a codebase: **greenfield** (scaffold) or **brownfield** (mount).
3. **Harness- AND model-agnostic.** Roles bind to any `(harness × provider × model)`. The deterministic outer loop is **framework-owned standalone Python**, NOT built on any harness's orchestration (explicitly NOT Claude Code's Workflow tool).
4. **Governed loop engine.** Do NOT trade away checkpoints / calibration / audit for "walk-away" autonomy. **Auditability is what lets the human move from synchronous gatekeeper to asynchronous reviewer** (this is the differentiator vs vanilla loop engineering).

---

## 3. 已确认事实 (Confirmed Facts — terminology + invariants)

### 3.1 Glossary (naming discipline — Constitution §1.7-E; NEVER conflate)
- **Auto Loop** (Concept 1) — the product AI agent improves *itself* (Type A). `modules/m-autoloop.md`.
- **Delivery Loop** (Concept 2) — the 5-role team converges per-milestone to the closure_contract. `process/delivery-loop.md`.
- **Loop Memory** — md-persisted cross-loop experience **substrate** (NOT a third loop); feeds both loops + fold-back. `modules/m-memory.md`.
- **Role Configuration Contract** — per-role `(execution × capability × connector)` binding. `process/role-configuration-contract.md`.
- **Standalone Driver** — framework-owned deterministic outer loop (Python). Calls harnesses via **Adapter**.
- **Adapter** — `spawn(role, prompt, tools, schema) → schema-valid verdict`; one per harness.
- **Loop Ingress** — at new-loop trigger: intent-contract + isolation choice (branch/worktree) + memory load. ≠ Loop Controller ≠ Onboarding Wizard.
- **Loop Controller** — pure loop-until/convergence/dry-stop/budget termination semantics.
- **Audit Spine** — append-only, hash-chained, reconstructable per-loop ledger.
- **Onboarding Wizard** — agent-driven one-time framework install (greenfield/brownfield).

### 3.2 The 5-role chain (universal, from Constitution §3)
Customer (human) · Research · Deliver · Dev · Code Reviewer · Acceptance. Acceptance is structurally isolated (§1.7-C: never spawned by Research/Deliver/Dev — only human paste OR the orchestrator gated by §3.6 calibration).

### 3.3 Role Configuration Contract — three facets (all per-role, with defaults, validated)
- **A. Execution binding**: two axes — **harness** (`claude_code | codex | headless | <other>`) × **provider/model** (`anthropic | openai | deepseek | moonshot | …` + model id) + `endpoint` + `capability_ref`.
  - Compatibility reality: Claude Code↔Anthropic, Codex↔OpenAI are provider-locked; **`headless` (OpenAI-compatible endpoint) is the only adapter that reaches DeepSeek/Kimi/GPT**.
  - **Dev needs a file-editing coding-agent harness**; pure-API (headless) models suit judgment/reasoning roles.
  - Capability gate validates the `(harness, provider, model)` *triple* vs role requirements.
  - **Calibration is per-`(role, model)`**; a model change invalidates `calibrated` (OQ-V4-007 promoted to rule).
  - **Model-agnostic verdict invariant**: all verdicts schema-valid regardless of model; the engine **never lowers the bar** for a weaker model; invalid verdict = `gate_hard_fail`, never a permissive default.
- **B. Capability binding (skills)**: default-bound per role; **vendored + pinned, NO runtime fetch**; supply-chain discipline (provenance, redistributable license only, preserve upstream LICENSE, integrity hashes); `tool_requirements ⊆ role whitelist`; **changing the Acceptance skill invalidates calibration**.
- **C. Connector binding (tools/MCP/connectors)**: **default-deny**; capability class (scopes read/write/network) ⊆ role sandbox; grant ⊇ skill connector requirements; secrets **by-name only** (values in adopter env); **discovery is propose-only** (scan → human approves into allowlist; NEVER auto-grant).

### 3.4 Driver state machine + governance behaviors (all implemented)
- States: `dev_pending → gate_pending → review_pending → close_pending → advance`; `acceptance_pending` after **milestone close** (gated on `charter.acceptance.enabled`; terminal sub-sprint = `subsprint_id == seq[-1]`).
- §3.6 calibration gate: uncalibrated + `fully_autonomous_within_budget` → **auto-degrade to `human_on_the_loop`** (recorded checkpoint, never silent).
- **F5 evidence**: the DRIVER runs `charter.tooling.eval.cmd`, captures artifacts, passes the **path (read-only)** to Acceptance. Acceptance never runs the harness; its verdict must cite `evidence_path` (not code).
- §3.5: `fix_required` → human-confirm checkpoint with 3 routes (`deliver_fix_iteration | re_acceptance_after_evidence | research_contract_revision`); **never a silent Deliver route**.
- **Loop Controller wired**: non-clean verdict → `decide(LoopState)` → `advance | halt(budget|max_rounds|converged_dry) | escalate(severity) | continue`. `continue` auto-iterates dev→review **ONLY when `auto_fix_iteration.enabled`** (bounded — no runaway); else the HITL human-confirm checkpoint (unchanged). Every decision → a `controller_decision` audit event.
- **Loop Memory wired (optional `memory_root`)**: ingress `select()` injects prior lessons into role prompts (`spawn.memory_injected`); close `record_observation()` records generalizable failures (L1→L2 at n≥2; anti-gaming guard rejects case-specific input→output). `memory_root=None` → zero activity.
- Resume round-trips `seen_finding_keys / rounds_since_new_finding / budget_spent`.

### 3.5 Audit Spine (Next1 — precondition for async/on-demand review)
- `loop_id` threads charter→brief→checkpoint→spawn→trace→verdict→close.
- Event: `{loop_id, seq, ts, type, payload, prev_hash, hash}`, `hash = sha256(prev_hash + json.dumps(event_without_hash, sort_keys=True, separators=(',',':')))`, genesis `prev_hash = "0"*64`, seq from 0.
- Per-spawn execution-context payload: `role, harness, provider, model, skill_pins[], memory_injected[], input_hash, verdict_ref, run_mode, tokens, cost`.
- Append-only + hash-chained (tamper-evident) at `.orchestrator/audit/<loop_id>.jsonl`; deterministic md reconstruction report; mode-independent (orchestrator + paste). `ts` is **injected** (determinism).

---

## 4. 决策记录 (Decision Log — incl. REJECTED options, do not re-propose)

| ID | Decision |
|---|---|
| Distribution | **Spec + copyable engine-kit** (chosen). Rejected: pure-spec (no engine), separate installable package. |
| Substrate (OQ-A) | **Standalone Python driver + per-harness adapters.** Rejected: Workflow-first (Claude-Code-locked). Workflow may later be an *optional* backend only. |
| Driver language (OQ-A) | **Python.** |
| License (OQ-C) | **MIT** (`LICENSE` added; holder "aidazi authors" — replaceable). |
| §1.7-D vs bottleneck (OQ-B) | **RESOLVED — async may PREPARE + RECOMMEND, but final confirmation of any authority gate ALWAYS folds back to the human; NO unilateral auto-confirm** (`auto_confirm_if_clean` stays forbidden). Bottleneck relief = charter pre-authorization + exception-gating + on-demand audit + ready-to-approve recommendations. |
| Default skills | research→`brainstorming`; deliver→`writing-plans`+`architecture-decision-records`; dev→`test-driven-development`; code_reviewer→`code-review-excellence`; acceptance→`advanced-evaluation` (calibration-coupled). All MIT, vendored, pinned. |
| Connectors | default-deny; discovery propose-only; secrets by-name. |
| Loop Ingress isolation | option 1 current_branch (default) / 2 new_branch / 3 new_worktree; escalate to isolation when dirty_tree or loop_active_on_branch (per `force_isolation_when`). |
| Loop Memory storage | **md files only, no extra storage service.** |
| Constitution deltas | **PROPOSED only** (in `process/role-configuration-contract.md §7`). Do NOT edit `governance/constitution.md` unilaterally — route through fold-back. |

---

## 5. 当前进度 (Current Progress)

### 5.1 Commits on `v2-loop-engine` (NOT pushed; user controls push)
1. `fb367d6` — P0 substrate ADR + P1 hard kernel + MIT LICENSE + vendored skills + v2 plan
2. `9f756a3` — P-0a spec foundation + P2 engine MVP (+ F1/F2 fixes)
3. `33d9767` — P1 follow-up: charter_validator P-0a checks (capability-gate, skill-integrity, connector-default-deny)
4. `0f7fd6d` — P3: verifier loop (Acceptance+calibration+F5, Loop Controller, Loop Memory, m-audit/m-memory)
5. `58fc52e` — P3 integration: wire Loop Controller + Loop Memory into the driver
6. `8ad24d2` — P4: Loop Ingress (worktrees), connectors+discovery, codex adapter, vendor using-git-worktrees
7. `1d2d541` — **P4 integration follow-up**: wire Loop Ingress into the driver (loop_init/reattach/close) + thread Facet-C connectors/sandbox through the spawn boundary (base/mock/codex)
8. `0da30dd` — **P5**: Loop Memory feedback engine (propose-only, paths 2-5) + driver wiring at milestone close + plain cron/CI scheduling entrypoint
9. `822bb15` — **P6 (start)**: `ONBOARDING.md` — agent-driven Onboarding Wizard (harness-agnostic; step flow 0-9; 4 properties; references guides as source-of-truth) + README pointer. Docs only.

> History note: commits 1–8 were re-authored from the gitee noreply to `Rex1028 <caoruixin@163.com>` on 2026-06-16 (filter-branch, dates preserved) and force-pushed to GitHub; the hashes above are the CURRENT (post-rewrite) values for 7–8 only — 1–6 now have different hashes too (see `git log`).

### 5.1b P5 (commit `0da30dd`) — what landed
- **`engine-kit/memory/feedback.py`** (NEW) + **`schemas/memory-feedback.schema.json`** (NEW): pure, deterministic, READ-ONLY, **PROPOSE-ONLY** engine over matured (L2/active) entries → m-memory §5 paths 2–5 (`skill_edit` / `charter_tuning` / `autoloop_candidate` / `fold_back`). One proposal per (path,target) citing all source ids; explicit human `gate`; calibration-note charter_tuning keeps (provider,model); Acceptance skill_edit ⇒ `recalibration_required`. `propose(store|entries)` + `render_report(ts=injected)`.
- **Driver wiring** (`driver.py`): at a successful **milestone close** (memory enabled) → write the propose-only report under run_dir + a human-pending `memory_feedback` checkpoint + a `memory_feedback` audit event; applies NOTHING. No-op when memory off / non-terminal sub-sprint / halt. Gated on a new `_milestone_closed` flag (also set in `_run_acceptance` for resume-into-acceptance).
- **`engine-kit/scheduling/`** (NEW): plain cron/CI entrypoint `run_loop.py` (NOT ScheduleWakeup) — `build_adapters(allow_real=)` (mock dry-run default; real gated by `AIDAZI_ALLOW_REAL_ADAPTER`), `run_loop(...)`, `main()`; modes `overnight_autoloop`/`milestone_delivery`; example crontab + GitHub Actions yaml + README. Real clock isolated to the injected production entrypoint.
- Spec: `modules/m-memory.md` §5 + cross-refs updated to record the feedback impl.
- Tests 253 → **281** (feedback 17, scheduling 7, driver 61→65). Determinism + propose-only verified inline (no bare clock/random; read-only; no store mutation).

**Phases P0 · P1 · P-0a · P2 · P3 · P4 (+ P4 integration) = COMPLETE.** Tests (all deterministic, offline, green): orchestrator 128 (driver 61 + controller 34 + ingress 33), connectors 22, adapters 21, memory 17, validators 38, audit 17, skill-vendor 10 = **253**.

### 5.1a P4 integration follow-up (commit `1d2d541`) — what landed
- **Loop Ingress wired** into `driver.py`: new OPTIONAL `repo_dir` / `isolation_strategy` ctor params. `repo_dir=None` ⇒ ingress OFF, byte-identical to pre-P4.
  - `_loop_init_ingress` (fresh start): `decide_strategy → setup_context → registry.register` + `loop_ingress` audit event. §1.7-D/OQ-B honored: a force-condition escalation is RECOMMENDED via a human-pending checkpoint (`loop_isolation_recommendation`), NEVER auto-applied — proceeds on the charter default (or explicit `isolation_strategy`). Self-record excluded from the collision check.
  - `_loop_close_ingress` (only on STATE_ADVANCE/DONE): `mark_done` + `cleanup`. HALTED ⇒ left active + context kept. `cleanup` never discards work (`loop_ingress.context_has_changes()` = dirty-tree OR commits-ahead-of-base; fail-safe to "changed").
  - `_loop_reattach_ingress` (resume): reconstruct the handle from the registry, NO git mutation.
  - `loop_ingress.py`: `ContextHandle` gained `base_ref`; new public `context_has_changes(handle)`.
- **Facet-C connectors threaded**: `RoleRouting`/`route_for_role` read `tooling.<role>.connectors` + `.sandbox`; `_spawn` + `_spawn_acceptance` pass them keyword-only. Default-deny no-op when empty. `base`/`mock`/`codex` `spawn` now take keyword-only `connectors`/`sandbox` (claude_code/headless already did). codex maps aidazi sandbox→`--sandbox` and **FAILS CLOSED** when connectors are granted (codex exec has no confirmed per-call injection form).
- Adversarially reviewed (qa). 3 bounded RISKs found: **#8 self-collision FIXED**; **#9** (`mark_done` KeyError only on external/concurrent registry removal — left, unreachable in normal flow, project prefers loud); **#10** (resumed worktree under `remove_if_unchanged` never auto-removed because `base_ref=None` on resume → fail-safe keep; by-design, worth an operator-docs note in P6).

### 5.2 File map (what exists)
- **Plan (master ref)**: `archive/2026-06-15-v2-loop-engine-plan.md` — §5 charter schema, §6 file manifest + Constitution edits, §7 phased checklist, §8 OQs. **P3/P4 boxes NOT yet ticked.**
- **ADR**: `docs/adr/ADR-0001-engine-substrate.md`.
- **LICENSE** (MIT). (`README.md` still says "LICENSE file (when present)" — could tidy.)
- **Skills**: `skills/registry.yaml` (catalog + `role_defaults`), `skills/skills.lock` (pins + tree_sha256), `skills/vendored/{brainstorming, writing-plans, architecture-decision-records, test-driven-development, code-review-excellence, advanced-evaluation, using-git-worktrees}/` (each + upstream LICENSE + `_provenance.yaml`). Candidates (not vendored): `differential-review` (CC-BY-SA-4.0 + Write/Bash → opt-in only), `deep-research` (needs firecrawl+exa MCP → revisit now connectors exist), `verification-before-completion`.
- **Schemas (P-0a)**: `schemas/{model-registry, skill-binding, skill-catalog, connector-binding, connector-catalog, intent-contract, memory-entry, audit-event}.schema.json` + extended `mission-charter.schema.json` (additive: `tooling.<role>.{harness,provider,model,endpoint,capability_ref,connectors,tools.allow,discovery}` + top-level `isolation`/`intent_contract`/`audit`).
- **Process docs (P-0a)**: `process/role-configuration-contract.md` (3-facet + PROPOSED Constitution deltas), `process/model-capability-registry.md`.
- **Module specs (P3)**: `modules/m-audit.md` (implemented), `modules/m-memory.md` (implemented).
- **engine-kit/** (the runnable kit; deterministic, no-LLM hard kernel; real adapter/connector I/O gated behind `AIDAZI_ALLOW_REAL_ADAPTER`):
  - `validators/` — `charter_validator.py` (structural + 8 MANDATORY_CHECKPOINTS non-bypass [4 shapes] + human_confirm + route_options + calibration-warn + **capability-gate + skill-integrity + connector-default-deny**), `stanza_validator.py`, `data/model-registry.yaml`, tests.
  - `skill-vendor/` — `skill_vendor.py` (`vendor` [git, gated] + `verify` [offline integrity vs skills.lock]), tests.
  - `audit/` — `audit_log.py` (hash-chain ledger, `verify_chain`, `make_event`/`make_spawn_payload`, injectable `ts`), `audit_report.py`, tests.
  - `orchestrator/` — `driver.py` (state machine + acceptance + controller + memory wired + resume), `loop_controller.py` (pure `decide(LoopState)`), `loop_ingress.py` (**standalone, NOT wired into driver yet**), `demo.py`, `examples/p2-charter.yaml`, tests.
  - `adapters/` — `base.py` (ABC + `translate_connectors`), `mock.py`, `claude_code.py`, `headless.py`, `codex.py` (gated), `__init__.py` (`ADAPTER_REGISTRY = claude_code/codex/headless/mock`), tests.
  - `connectors/` — `translate.py` (grant→harness-native), `discovery.py` (propose-only scan), tests.
  - `memory/` — `memory_store.py` (`write_entry/record_observation/select/load_index/guard_entry`, L1→L2), tests.

---

## 6. 当前任务 (Current Task)

P6 in progress. Latest commits: `822bb15` (ONBOARDING.md), `a4f6436` (P6 #1 minimal-greenfield recorded run), `e7f0648` (**P6.1 full_chain_guided** bootstrap mode). Suite green at **304** (engine-kit) + 4 (minimal-greenfield). Branch is **4 ahead of origin/v2-loop-engine** (P5 + the 3 P6 commits; NOT pushed — user controls push).

> NOTE (2026-06-16): gitee DROPPED. Single remote = GitHub `origin`; commit identity `Rex1028 <caoruixin@163.com>`. See memory `github-push-setup`.

### P6.1 — full_chain_guided (commit `e7f0648`)
Optional guided full-chain bootstrap: Research(draft) → Customer Gate 1 (human sign-off via injected `gate_resolver`, never auto-confirmed) → Deliver(decompose, schema `deliver-plan-verdict`) → existing delivery loop. Skip rules (signed brief / supplied sequence), post-Gate-1 scope-expansion guard (FIXED a qa-found partial-envelope blind spot), new audit events, resumable. `loop_mode=delivery_only` default byte-identical. driver tests 65→88. Adversarially verified (never-auto-confirm clean via forged-state attacks).

### P6 = COMPLETE (commits `822bb15` · `a4f6436` · `e7f0648` · `0d07615` · `763cfb2`)
- [x] ONBOARDING.md wizard · [x] #1 recorded run · [x] #2→P6.1 full_chain_guided · [x] #3 guides finalized (greenfield/brownfield reconciled to the shipped wizard+engine) · [x] #4 OQ-V4-009 RESOLVED (reframe: validators shipped in engine-kit/validators/; precommit-check = optional adopter tooling, trace_emitter = adopter-runtime concern; not framework-blocking).
- (dropped: role-cards-as-skills [reframed→P6.1], vendoring CI, automated fold-back.)
- Note: `docs/adoption-overview.md` still has the legacy `agent_kind`-only phrasing (line ~95) — optional follow-up, out of #3 scope.

### NEXT (user step 3): set up a NEW demo-application USING the wizard (ONBOARDING.md)
Drive the ONBOARDING.md flow as the coding agent; the human supplies the intent contract (goal/standard/proof_of_done) + track + decisions (recommend-then-confirm). Needs from user: target dir/repo for the demo-app + its domain/problem statement. **PUSHED 2026-06-17: origin/v2-loop-engine in sync at `763cfb2`** (P5 + all 5 P6 commits on GitHub).

---

## 7. 下一步 (Next Actions — pick up here)

**P4 integration follow-up = DONE** (commit `1d2d541`, see §5.1a). The "standalone-then-wire" backlog is now empty (Controller, Memory, Ingress all wired).

**P5 = DONE** (commit `0da30dd`, §5.1b). Loop Memory feedback (propose-only) + cron/CI scheduling landed.

**P6 IN PROGRESS** (commit `822bb15`): `ONBOARDING.md` Onboarding Wizard landed (docs). **Remaining P6 checklist items:**
- [ ] role cards packaged as skills / sub-agent defs (optional `skills/aidazi-onboarding/SKILL.md` packaging — ONBOARDING.md §"Packaging note" flags where it goes).
- [ ] `examples/minimal-greenfield` end-to-end recorded run (proof) — a captured driver run on the worked example.
- ~~vendoring CI~~ **DROPPED (user, 2026-06-16).** Adoption model = vendor skills ONCE, no upstream re-sync, customize as needed → a recurring `skill_vendor.py verify` gate would flag legitimate customizations as failures. Integrity still checkable on-demand (the `verify` tool + its 10 tests remain). Offline-test-CI also dropped for now (kit is copyable spec, not a deployed service); add later if wanted.
- ~~promote PROPOSED Constitution deltas via fold-back~~ **DEFERRED (user, 2026-06-16).** No automated adopter→framework fold-back at this stage (single maintainer, no external adopters). The PROPOSED deltas stay as proposals in `process/role-configuration-contract.md §7`; the framework author updates aidazi DIRECTLY when they judge one worth it. The P5 propose-only `fold_back` path remains the surfacing mechanism for later. Guardrail UNCHANGED: the AGENT never edits `governance/constitution.md` without explicit human direction (the "no unilateral edit" rule constrains the agent, not the human author).
- [ ] close OQ-V4-009.
- [ ] greenfield/brownfield guides "finalized" review pass (guides exist; confirm they match the shipped wizard).
- **P6** — Onboarding Wizard (`ONBOARDING.md`, harness-agnostic, idempotent/non-destructive/audited/recommendation-driven) + greenfield scaffold / brownfield mount in the guides + role cards packaged as skills/sub-agent defs + `examples/minimal-greenfield` end-to-end recorded run + vendoring CI + on-demand audit *filters* + close OQ-V4-009.

**Loose ends (any time):**
- Gate `# Recommendation` field (Next2): engine-generated recommendation + rationale on must-have checkpoints. (NOTE: the P4-integration `loop_isolation_recommendation` checkpoint is a concrete precedent for this shape.)
- Tick P3/P4 (+ P4-integration) boxes in `archive/2026-06-15-v2-loop-engine-plan.md`.
- Operator-docs note (qa RISK #10): a worktree resumed under `cleanup_policy: remove_if_unchanged` is never auto-removed (`base_ref` not persisted in the registry → `context_has_changes` fails safe to "changed"). Fix option: persist `base_ref` on the LoopRecord so resume can compute commits-ahead. Fold into P6 onboarding/operator docs.
- Consider recording granted connector ids on the `spawn` audit payload (G3) — currently not in `make_spawn_payload`; charter-validation already records the grant, so deferred.
- Promote PROPOSED Constitution deltas via fold-back: §3.4#6 (provider/model/connector neutrality + transitive whitelist), model-agnostic verdict invariant, §3.6 per-`(role,model)` calibration, §1.7 new forbidden (unpinned/runtime-fetch skill OR connector; connector default-allow), §1.4 audit runtime-owned, §3.7 Loop Memory naming, §1.7-D async-prep codification.
- Revisit `deep-research` skill (connector layer now exists → could vendor as opt-in).
- Fix `skill_vendor vendor()` format-fidelity nit (`yaml.safe_dump` doesn't reproduce the hand-crafted provenance/lock format — integrity values are correct, only style differs; the P4-4 run hand-wrote provenance/lock to match).
- Confirm the **Codex CLI form** assumed in `codex.py` (`codex exec --json …`; the final-agent-message event `type` has a TODO(human) for the target Codex build).
- Replace LICENSE copyright holder if a specific name/entity is preferred.

---

## 8. 注意事项 (Caveats — these affect how you should act)

1. **Do NOT push** (user controls push). **Do NOT commit `compact/`** (pre-existing untracked, unrelated).
2. **Working rhythm the user expects**: fan out **build agents with disjoint file ownership** → independent **adversarial verify agent(s)** (`qa` type) for risky/shared-file changes → fix findings → **gated commit** (run the suites; commit only if green; explicit-path `git add`, never `git add -A`; end commit msg with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`). The user *did* interrupt one mid-integration verify with "continue to finish" — so don't over-spawn verify agents for low-risk standalone steps; **always do a consolidated run after parallel fan-out** (it catches cross-piece regressions the individual agents miss — e.g., P4 hit a schema-enum + a stale hard-coded count).
3. **Constitution deltas are PROPOSED only** — never edit `governance/constitution.md` unilaterally.
4. **engine-kit standalone modules (`loop_ingress`) are intentionally not wired into the driver yet** — wiring is a separate step.
5. **All real adapter/connector I/O is GATED** behind `AIDAZI_ALLOW_REAL_ADAPTER` (and/or ctor flag); tests are offline/deterministic; **venvs go in `/tmp`, not the repo**; `__pycache__`/`*.pyc`/`.venv/` are gitignored.
6. **Skill vendoring**: vendored + pinned (commit sha), **no runtime fetch**, redistributable licenses only, preserve upstream LICENSE; `skill_vendor.py verify` must pass (tree_sha256 in `skills.lock` reproduces the bash recipe `find . -type f ! -name _provenance.yaml | sort | xargs shasum -a 256 | shasum -a 256`).
7. **During fan-out, run only your own test module** (not full `discover`) to avoid reading a sibling file mid-edit; run the **consolidated suite afterward**.
8. **Determinism is a hard requirement** for the kernel (no bare `time/datetime/random/uuid` in hash/append/decision paths; inject `ts`/ids). Adversarial verifiers check this.
9. **Naming discipline (§1.7-E)** is load-bearing — keep Auto Loop / Delivery Loop / Loop Memory and Loop Ingress / Loop Controller / Onboarding Wizard distinct in all docs.
10. The framework's OWN persistent memory (the harness `MEMORY.md` under `…/memory/`) is a SEPARATE thing from **Loop Memory** (the engine feature) — don't conflate.
11. Default work for this user otherwise lives in a `venture-strategy` repo; this aidazi work is its own branch line.

---

End of handoff pack.
