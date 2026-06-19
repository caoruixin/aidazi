---
title: Onboarding Wizard — agent-driven, one-time aidazi bootstrap into a codebase
doc_tier: application-guide
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
created: 2026-06-16
last_reviewed: 2026-06-16
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 20KB
notes: >
  The Onboarding Wizard (plan archive/2026-06-15-v2-loop-engine-plan.md §4.7).
  A harness-agnostic markdown file an adopter feeds to their coding agent — the
  agent reads it and drives an interactive, idempotent, non-destructive, audited,
  one-time install of aidazi into a codebase. This file is the executable
  decision-tree / checklist; it REFERENCES the greenfield/brownfield/adoption-
  overview guides for rationale and does NOT re-explain them. Naming discipline
  (Constitution §1.7-E): the Onboarding Wizard is the ONE-TIME bootstrap — it is
  distinct from Loop Ingress (per-loop git isolation), Loop Controller, Auto
  Loop, Delivery Loop, and Loop Memory. Do not conflate.
---

# Onboarding Wizard — feed me to your coding agent

**You are reading the aidazi Onboarding Wizard.** If you are a coding agent
(Claude Code / Codex / Cursor / Aider / any read-write-shell harness): the human
just handed you this file to run. Drive the setup below. The human makes
decisions and supplies inputs; you do the reading, the writing, and the shell
work, one decision at a time, and you confirm before you change anything that
already exists.

If you are a human: open a fresh session in your target repo, point your coding
agent at this file ("read `aidazi/ONBOARDING.md` and run it"), and answer its
questions. You can stop at any point and re-run later — the wizard resumes.

This wizard installs aidazi **once**, into a codebase. It is **not** a loop. It
does not run your project. After it completes, the standalone driver runs the
loops (Step 9).

> **Naming discipline (Constitution §1.7-E).** The **Onboarding Wizard** is the
> one-time framework install. It is **not** the same as — and must never be
> conflated with — **Loop Ingress** (per-loop git-isolation choice at each new
> loop), the **Loop Controller** (loop-until-condition iteration), the **Auto
> Loop** (a Type A product agent improving itself), the **Delivery Loop** (the
> team converging on a milestone), or **Loop Memory** (cross-loop institutional
> memory). The wizard ends; the loops begin. See `archive/2026-06-15-v2-loop-engine-plan.md`
> §2 glossary and `docs/two-loops-explainer.md`.

---

## What this wizard is, and what it deliberately is NOT

This file is the **executable decision-tree and checklist**. It does **not**
re-explain *why* aidazi is shaped the way it is — that is the job of the existing
guides, which are the source-of-truth this wizard points to:

| For the rationale of… | Read (source-of-truth — do not duplicate) |
|---|---|
| The mental model (5-role chain, decision layers, two loops) | `docs/adoption-overview.md` |
| Greenfield adoption (fast inherit; the Phase 1-5 funnel) | `docs/greenfield-guide.md` |
| Brownfield adoption (human-led inventory → decide → reconcile) | `docs/brownfield-guide.md` |
| Track selection (Type A / B / C / A+B) | `process/profile-aware-maturity.md` (Δ-14) |
| Role configuration (the 3 facets) | `process/role-configuration-contract.md` |

When a step says "walk the greenfield guide STEP 2", the agent **opens that
guide and follows it** — it does not paraphrase it here. This wizard's only added
value is sequencing, idempotency, non-destructiveness, audit, and
recommend-then-confirm.

---

## The four properties (and how each is honored)

These four properties are load-bearing. Every step below honors all four; this
section states them once, and each step notes the specific mechanism.

1. **Harness-agnostic.** The wizard uses **only read, write, and shell**
   operations. It has **no dependency on any harness's orchestration** — in
   particular, **NOT** Claude Code's Workflow tool, sub-agent spawner, or
   ScheduleWakeup. Any coding agent that can read a file, write a file, and run a
   shell command can drive it. (This mirrors the framework rule that the engine's
   outer loop is harness-agnostic standalone code, plan §1 / §4.2.)

2. **Idempotent + resumable.** All progress is tracked in
   `docs/current/adoption-state.md` (schema: `schemas/adoption-state.schema.json`).
   Before each step the agent **reads** that ledger; if the step is already
   recorded done, it is **skipped**. Re-running the wizard resumes from the first
   unfinished step. Nothing is done twice.

3. **Non-destructive.** **Read before write.** Before writing any file, the agent
   checks whether it already exists. If it does, the agent **shows a diff and asks
   the human to confirm** before overwriting — it never clobbers existing work
   silently. (This is the wizard-level expression of the brownfield "don't rip
   and replace" rule, `docs/brownfield-guide.md`.)

4. **Audited.** Every decision the human makes is recorded as a row in
   `docs/current/adoption-state.md` (a `divergent` row with rationale when the
   human overrides a recommended default, per `schemas/adoption-state.schema.json`),
   **plus** an `onboarding record` appended at `docs/current/onboarding-record.md`
   (timestamp · step · decision · who confirmed). The record is the human-readable
   audit of the bootstrap itself.

And one governing interaction style:

5. **Recommendation-driven.** Present **ONE decision at a time**, each with a
   **recommended default** and a one-line rationale. The **human confirms** (or
   overrides). The agent never batches decisions and never auto-confirms an
   override on the human's behalf. (This is the wizard analog of the framework's
   recommend-then-confirm posture, plan §4.6.)

---

## Step 0 — Bootstrap the ledger and the audit record (always first)

Before anything else:

1. **Locate the framework.** Confirm `aidazi/` (or the vendored framework root)
   is reachable from the target repo. If it is a submodule, it is already in
   place; if not, copy it in (greenfield STEP 1 in `docs/greenfield-guide.md`).
2. **Read-before-write the ledger.** If `docs/current/adoption-state.md` exists,
   load it and resume from the first unfinished step (property 2). If not, create
   it from `templates/adoption-state-template.md` (schema:
   `schemas/adoption-state.schema.json`).
3. **Open the onboarding record.** If `docs/current/onboarding-record.md` exists,
   append to it; else create it with a header. Every subsequent step writes one
   row here (property 4).

> Properties honored: idempotent+resumable (reads the ledger to find resume
> point), audited (opens the record), non-destructive (never recreates an
> existing ledger).

---

## Step 1 — Detect greenfield vs brownfield

**Action (read-only):** inspect the target repo. Decide:

- **Greenfield** — empty repo, OR an existing codebase with **no** agent /
  workflow / demo and no competing governance. Path = *fast inherit*.
- **Brownfield** — an existing project that already has agent/workflow/demo work,
  its own backlog format, its own eval setup, or its own governance docs
  (`AGENTS.md` / `CLAUDE.md` / role docs). Path = *human-led reconcile*.

Signals to read: presence of source code; existing `AGENTS.md`/`CLAUDE.md`; an
existing action-bank/backlog; an existing eval suite; any orchestrator config.

**Recommend, then confirm:** state the detection and the recommended path with
its one-line reason, and let the human confirm or flip it. Record the choice in
the onboarding record and as the ledger's adoption shape.

> Rationale lives in `docs/adoption-overview.md` §7 and the two per-track guides
> — do not re-explain it here. Properties: recommendation-driven (one decision),
> non-destructive (detection is read-only), audited (record the choice).

---

## Step 2 — Brownfield only: scan the codebase (non-destructive, read-only)

**Skip entirely if greenfield.**

Walk the brownfield INVENTORY phase (`docs/brownfield-guide.md` §2) — **read
only; change nothing in this step**. Capture, into the onboarding record:

- current track (Type A / B / C / A+B);
- existing governance docs;
- existing action-bank / backlog format;
- existing eval framework + CaseSpec shape;
- current human/agent split and any orchestrator in use;
- where semantic decisions currently live (LLM-owned vs hardcoded — the §1.7
  friction predictor).

This scan is the input to Step 3's profile choice and Step 6's non-destructive
confirmations (existing files become "confirm before overwrite" candidates).

> Properties: non-destructive (read-only inventory — the brownfield guide's
> explicit "do not edit anything in this phase" rule), audited (results recorded).

---

## Step 3 — Pick the adoption track / profile (Type A / B / C)

**Action:** determine the track and, for brownfield, the adoption profile depth.

- **Track** — Type A (AI agent) / Type B (agentic workflow) / Type C (demo) /
  Type A+B (hybrid). If unsure, walk the decision tree in
  `process/profile-aware-maturity.md` (Δ-14).
- **Brownfield profile depth** — A (Full) / B (Core) / C (Selective), per
  `docs/brownfield-guide.md` §1. **Recommended default: start at B or C and
  graduate** — not A (the break-even is around the second milestone).
- **Greenfield** — track only; the greenfield path is full-inherit by design.

**Recommend, then confirm.** Record the track in the ledger front-matter
(`track:` — one of `type_a | type_b | type_c | type_a_b_hybrid`, per
`schemas/adoption-state.schema.json`) and the profile + rationale in the record.

> Rationale: `process/profile-aware-maturity.md`, `docs/brownfield-guide.md` §1,
> `docs/adoption-overview.md` §6. Properties: recommendation-driven, audited.

---

## Step 4 — Capture the intent contract (reuse the `brainstorming` skill)

The first loop needs a definition of done. Capture the **intent contract**: the
triple `goal / standard / proof_of_done` (this maps onto the framework's
`closure_contract`, moved to ingress — plan §4.6; schema
`schemas/intent-contract.schema.json`).

**Action:** adopt the Research lens and run the vendored **`brainstorming`** skill
(`skills/vendored/brainstorming/SKILL.md`; the Research role default in
`skills/registry.yaml`) to draft the triple with the human. Then:

- **Intake-completeness gate:** if any of goal / standard / proof_of_done cannot
  be identified, **do not proceed** — prompt the human to supplement. A loop with
  no definition of done is not started (plan §4.6).
- Write the draft into the first research brief (`docs/research-briefs/<id>.md` —
  greenfield STEP 2 names it; the worked example is
  `examples/minimal-greenfield/docs/research-briefs/RB-001-refund-eligibility.md`).
- **`confirmed_by_human` flips to true ONLY by the human**, never by the agent
  (Constitution §1.7-D / OQ-B; mirrored in `mission-charter.schema.json`
  `intent_contract`).

> Properties: recommendation-driven (the agent drafts; the human confirms),
> audited (the brief + record), harness-agnostic (running a SKILL.md is prose,
> not a harness orchestration call).

---

## Step 5 — Role configuration: the three facets (recommend-then-confirm)

Configure each of the 5 roles (Research / Deliver / Dev / Code Reviewer /
Acceptance) as `(execution × capability × connector)` — the Role Configuration
Contract (`process/role-configuration-contract.md`). For each facet, **present
the recommended default and let the human confirm or override**.

**Facet A — Execution binding (harness × provider × model).** Per role, set
`harness` (`claude_code | codex | headless | <other>`) and `provider` + `model`.
Recommended defaults follow the §4 capability table in the contract: Dev needs a
**coding-agent** harness (it edits files); judgment roles (Acceptance, parts of
Research/Deliver) suit `headless`/API models; native harnesses are provider-locked
(claude_code↔anthropic, codex↔openai). Capability is validated in Step 8.

**Facet A preflight — confirm each bound harness/provider is reachable on THIS
machine (recommend-then-confirm; gate before Step 8).** Step 8's capability gate
validates the *triple* on paper; it does **not** prove the harness CLI is
installed or the provider key is live. Do that now, while the human is present to
fix it — once per distinct `(harness, provider)` pair across the 5 roles:

- **`claude_code` / `codex` (native CLI harnesses).** Run `claude --version` /
  `codex --version` and confirm the CLI is authenticated. These two are the only
  harnesses the framework assumes; if the bound CLI is missing or unauthenticated,
  **stop** and have the human install / log in before continuing.
- **`headless` providers — DeepSeek / Kimi (Moonshot) / GPT / any
  OpenAI-compatible.** These are **adopter-supplied — never assume they are
  configured.** The charter names the credentials **BY NAME** — `endpoint` (or
  `endpoint_env`) for the base URL and `api_key_env` for the key — and the VALUES
  live in the adopter's environment: exported, or in a **gitignored `.env.local`**
  (copy `aidazi/.env.example` → `.env.local` at the repo root and fill it; the
  engine's `run_loop.py` loads it on `--allow-real` runs). Confirm the key is set,
  then run a zero-cost auth + model-discovery probe (key passed via header, never
  printed):
  ```bash
  set -a; [ -f .env.local ] && . ./.env.local; set +a   # load .env.local as the engine does
  KEY=$(printenv <api_key_env>)            # the env-var NAME from tooling.<role>.api_key_env
  curl -s -o /dev/null -w "%{http_code}\n" --max-time 15 \
    -H "Authorization: Bearer $KEY" "<endpoint>/models"
  ```
  A missing key or non-`200` ⇒ **prompt the human to put the key in `.env.local`
  NOW** (the timely configuration-confirmation moment), then re-probe. Also confirm
  the charter's `model` id appears in the `/models` response — provider catalogs
  drift, and a stale id fails only at runtime.

**Key-handling rule (mirrors Facet C):** secrets are referenced **by env-var NAME
only** — never write a key value into the charter, and never print one. Record
each probe as a row in the onboarding record (`harness · provider · model ·
reachable yes/no · timestamp`). A role whose harness is unreachable **blocks the
Step 8 green** unless the human explicitly records a deferral (e.g. "key arrives
before first real loop") in `adoption-state.md`.

> Properties: harness-agnostic (read + shell only — `--version` and a `curl`
> probe, no harness orchestration), idempotent (probe results recorded; re-runs
> skip confirmed pairs), non-destructive (read-only probes; keys by name only),
> audited (each probe is a record row), recommendation-driven (one
> reachability decision per `(harness, provider)` pair).

**Facet B — Capability binding (skills).** Vendor the **default role skills** and
bind them. Defaults (`skills/registry.yaml` `role_defaults`): Research →
`brainstorming`; Deliver → `writing-plans` + `architecture-decision-records`; Dev
→ `test-driven-development`; Code Reviewer → `code-review-excellence`; Acceptance
→ `advanced-evaluation` (⚠ calibration-coupled — changing it forces recalibration,
§3.6). Skills are **vendored + pinned, never runtime-fetched** (`skills/skills.lock`).

**Facet C — Connector binding (tools / MCP / connectors) — DEFAULT-DENY.**
Connectors are **never auto-granted.** The default for every role is *no
connectors*. To propose any, run the **propose-only** discovery scan
(`engine-kit/connectors/discovery.py` `propose()`) over the adopter repo: it is
**read-only**, performs no network calls, reads no secret values, and marks every
find `status: proposed` with provenance. The human then **explicitly approves**
chosen candidates into `charter.tooling.<role>.connectors[]`, adding `scopes` by
hand (a trust decision). Scan output is an **authoring aid, never authorization**
(`process/role-configuration-contract.md` §3).

> Properties: recommendation-driven (each facet is one recommend-then-confirm
> decision per role), non-destructive + audited (connector grants are default-deny,
> human-written, and recorded), harness-agnostic (the propose scan is plain
> read-only Python, not a harness feature).

---

## Step 6 — Generate the adopter artifacts (read-before-write each one)

Now write the adopter-side files. **For every file: check if it exists; if it
does, show a diff and confirm before overwriting** (property 3). Copy from the
worked example (`examples/minimal-greenfield/`) rather than authoring blank.

Generate / install:

1. **`AGENTS.md`** at the repo root — from the consumer template `AGENTS.md`
   (root). Fill §1 project identification (`project_name`, `adopter_track`,
   `framework_version`, `charter_path`) and §3 ledger paths.
2. **`charter.yaml`** — from `templates/mission-charter.yaml`, populated with the
   Step 5 role bindings (execution/skills/connectors), the Step 7 autonomy
   posture, budget, and `tooling.eval.cmd`. Schema:
   `schemas/mission-charter.schema.json`. (Pure human-paste adopters who skip the
   orchestrator may defer this — greenfield STEP 7 is optional.)
3. **`docs/current/*`** — the three domain contracts plus state ledgers, per the
   worked example: `domain_taxonomy.md`, `runtime_invariants.md`,
   `eval_acceptance_bars.md`, `agent_context_guide.md`, and the already-created
   `adoption-state.md` + `onboarding-record.md`. (`docs/domain-adaptation.md`
   walks the three contracts.)
4. **Copy `engine-kit/`** into the adopter repo (the copyable reference
   implementation — driver, adapters, validators, audit, connectors). It is
   non-normative: the spec wins on any conflict (`engine-kit/orchestrator/README.md`).
5. **Vendor the default skills** under `skills/vendored/<id>/` (each with its
   upstream `LICENSE` + provenance), bound per Step 5; pins recorded in
   `skills/skills.lock`.
6. **Create `.orchestrator/` and the audit dir** — the loop registry +
   `.orchestrator/audit/` for the hash-chained per-loop ledger (charter `audit.ledger_dir`,
   default `.orchestrator/audit`).

> Properties: non-destructive (read-before-write + confirm-on-overwrite for every
> artifact), idempotent (re-running skips files already recorded done), audited
> (each generation is a record row).

---

## Step 7 — Autonomy + checkpoint posture (recommend-then-confirm)

Set the autonomy level and confirm the checkpoint posture in `charter.yaml`:

- **`autonomy.level`** — `human_in_the_loop` (recommended default for a first
  adoption) / `human_on_the_loop` / `fully_autonomous_within_budget`. Note:
  `fully_autonomous_within_budget` for autonomous Acceptance **requires a passing
  §3.6 calibration gate**; until calibrated it auto-degrades to
  `human_on_the_loop` (greenfield STEP 7).
- **The 8 MANDATORY_CHECKPOINTS always fire.** The charter MAY add custom
  checkpoints (`mandatory_checkpoints_added`) but MAY NOT omit / empty / disable /
  override any of the 8 defaults — the charter validator (Step 8) rejects all four
  bypass shapes (`process/delivery-loop.md` §4.2.2-§4.2.3; Constitution §1.7-D).
- `acceptance.on_fix_required.human_confirm_required` MUST be `true` and
  `route_options` non-empty (Constitution §1.7-C).

**Recommend, then confirm.** Any override of a suggested default becomes a
`divergent` row (with rationale) in `adoption-state.md`; hard requirements (§1.7,
§3.4, MANDATORY_CHECKPOINTS, §3.6) can **never** be `divergent`
(`schemas/adoption-state.schema.json`; `templates/adoption-state-template.md`).

> Properties: recommendation-driven, audited (divergent rows capture every
> override; hard requirements are protected).

---

## Step 8 — Validate — the flow ends GREEN

Run the deterministic validation gate. **The onboarding flow is not complete
until this is green.**

1. **`charter_validator`** — run `engine-kit/validators/charter_validator.py` over
   the generated `charter.yaml`:
   ```bash
   python engine-kit/validators/charter_validator.py charter.yaml
   ```
   Exit 0 ⇒ structurally valid against `schemas/mission-charter.schema.json` AND
   no semantic ERRORS (the no-bypass checkpoint rules, `human_confirm_required`,
   non-empty `route_options`, the Facet-A capability gate, Facet-B skill
   integrity, and Facet-C connector default-deny / transitive-grant / scope ⊆
   sandbox). Warnings are allowed; **errors block.** Fix and re-run until exit 0.
2. **Structural checks** — confirm the generated tree exists and resolves:
   `AGENTS.md`, `docs/current/*`, the copied `engine-kit/`, vendored skills +
   `skills/skills.lock`, `.orchestrator/audit/`, and that the intent contract
   triple is present. Also confirm the **Step 5 Facet A preflight** ran: every
   bound `(harness, provider)` pair has a `reachable yes` row in the onboarding
   record, or an explicit human-recorded deferral in `adoption-state.md`.
3. Record the green result (validator exit code + timestamp) in the onboarding
   record. Mark the relevant `adoption-state.md` rows `at-spec`.

> Properties: audited (the green gate is recorded), idempotent (re-running the
> validator is side-effect-free), harness-agnostic (a plain Python CLI, no
> harness orchestration).

---

## Step 9 — "First loop" — the wizard ends, the loops begin

The bootstrap is done. Hand off to the **standalone driver** — this is where
**Loop Ingress** and the **Loop Controller** take over (NOT the wizard; §1.7-E).

> **Turnkey hand-off.** Tell the human to open a **fresh coding-agent session whose
> working directory is the adopter repo root** and feed it **`aidazi/FIRST-LOOP.md`**
> (the First-Loop Launcher). It carries the exact cold-start reads + the
> `engine-kit/scheduling/run_loop.py` commands (offline mock first, then the real
> run) and the human-on-the-loop gate discipline — so the human switches workspace
> and starts the first loop **without typing shell by hand**. `FIRST-LOOP.md` is the
> documented sequel to this wizard.

- **Run the Delivery Loop driver** (framework-owned, harness-agnostic; spec:
  `process/delivery-loop.md` §4.2). The reference implementation lives at
  `engine-kit/orchestrator/driver.py`; an end-to-end demo on the worked example
  is `engine-kit/orchestrator/demo.py` (`engine-kit/orchestrator/README.md` has
  the run recipe). At each new-loop trigger, **Loop Ingress** prompts the human
  for the git-isolation strategy (current branch / new branch / new worktree —
  charter `isolation`), loads Loop Memory, and confirms the intent contract.
- **Pure human-paste adopters** skip the driver entirely and run the 5-role chain
  by hand (greenfield STEP 6); that is a complete, valid adoption.
- **Scheduling** (overnight Auto Loop / milestone Delivery Loop) is plain cron /
  CI — never a harness scheduler (plan §4.2). Wire it when you want unattended
  runs.

Point the human at the per-track guide for the substance of the first
milestone: `docs/greenfield-guide.md` STEP 5-6 (the Phase 1-5 funnel) or
`docs/brownfield-guide.md` §5 (the Acceptance gate as the high-value first move).

---

## Resume / re-run behavior (summary)

Re-running this wizard is **safe**. On each run the agent: reads
`docs/current/adoption-state.md` + `docs/current/onboarding-record.md`, resumes
from the first unfinished step, re-checks every file before writing, and confirms
before overwriting anything that exists. No step is performed twice; no existing
work is clobbered.

## Packaging note (optional, not created here)

This wizard MAY later be packaged as a discoverable skill at
`skills/aidazi-onboarding/SKILL.md` (the SKILL.md standard, `process/role-skill-model.md`)
so a harness can surface "run aidazi onboarding" directly. That packaging is
**out of scope for this file** and is **not** created by the wizard; `ONBOARDING.md`
remains the source-of-truth either way.

---

End of Onboarding Wizard.
