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

If you are a human: open a fresh session **in your target (adopter) repo root**
(e.g. `~/projects/airplat`), point your coding agent at this file
("read `aidazi/ONBOARDING.md` and run it"), and answer its questions. The agent
may **read** the wizard from a vendored/submodule `aidazi/` path, but **every
write** lands in the adopter repo (the session's cwd) — **not** in the aidazi
framework repo (`~/projects/aidazi`). You can stop at any point and re-run later
— the wizard resumes.

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

## The journey at a glance — the decisions you'll make

Before the wizard drives you decision-by-decision, here is the whole route. The
wizard runs **Step 0–9, including Step 0a, the Step 4a snapshot checkpoint, and the
default-on Step 4b requirement ledger** (13 entries below). This table is the **map only**
— it does **not** restate the rules; each
step section below is the source of truth. After this overview, execution still
follows property 5: **one decision at a time**.

| Step | What you decide | Recommended approach / default action | Deferrable? | Main output |
|---|---|---|---|---|
| 0 | (no decision) bootstrap the ledger + record | — (always first) | no | `adoption-state.md` + `onboarding-record.md` + `adoption-config.md` |
| 0a | confirm cwd = adopter repo (fail-fast) | agent detects framework repo signals | no | workspace OK or STOP |
| 1 | greenfield vs brownfield | agent auto-detects from repo signals; you confirm | no | adoption shape in the ledger |
| 2 | (brownfield only) inventory the codebase | read-only scan; nothing decided yet | n/a | inventory in the record |
| 3 | adoption track (Type A / B / C / A+B) + brownfield profile depth | recommend from signals (Δ-14); brownfield default = start at B/C | no | `track:` |
| 4 | intent contract (goal / standard / proof_of_done) | draft with the `brainstorming` skill; human signs | no | first research brief |
| **4a** | **adopter implementation-stack snapshot** (current tech facts) | **brownfield: read-only detect, then confirm; greenfield: track-informed starting point you confirm** | **yes — unknown items → `DEFERRED → Phase 3`** | **`docs/current/implementation-stack.md`** |
| **4b** | **requirement ledger + `surface` classification — default-on for new adopters** (OW-2 / OW-3) | **draft REQ entries from the PRD; agent proposes `user_facing` / `non_user_facing` + `surface_confidence`, escalating only `low`-confidence items; the Customer confirms by signing** | **brownfield-without-PRD only (defer ⇒ records a `divergent` row); a wired ledger ⇒ OW-M3 active** | **`docs/requirements-ledger.json`** |
| 5 | role config: 3 facets (execution = *agent execution stack*, capability, connector) | per-role defaults from `skills/registry.yaml`; connectors default-deny | partial | charter `tooling.*` |
| 6 | generate the adopter artifacts | copy from `examples/minimal-greenfield/`; read-before-write | no | `AGENTS.md` / `CLAUDE.md` / `charter.yaml` / `docs/current/*` |
| 7 | autonomy + checkpoint posture | default `human_in_the_loop`; the 9 MANDATORY_CHECKPOINTS always fire | no | charter `autonomy.*` |
| 8 | validate — the green gate | validators + `adoption_status.py` exit 0 | no | green result + `adoption-readiness.md` |
| 9 | first-loop hand-off | hand off to `FIRST-LOOP.md` (not the wizard) | no | the loops begin |

> **Two distinct "stacks" — never conflate them.** Step 4a captures the **adopter
> implementation stack** — the *product's own* language, framework, build/package
> manager, test stack, data dependencies, deploy/runtime. Step 5 Facet A captures
> the **agent execution stack** — the harness × provider × model that *runs each
> role*. They live in different files (`docs/current/implementation-stack.md` vs
> `charter.yaml`) and are never merged into one field.

---

## Step 0a — Confirm workspace (fail-fast; always before Step 0 writes)

**Action (read-only):** verify this session's **cwd is the adopter repo root**,
NOT the aidazi framework repo. If `engine-kit/validators/adoption_status.py` is
already present (Step 6 not done yet), run it; otherwise apply the signals below
manually. When the validator is available:

```bash
python engine-kit/validators/adoption_status.py .
```

If the report says **framework repo detected — wrong workspace**, **STOP** and tell
the human to open a fresh session whose cwd is the target codebase (e.g.
`~/projects/airplat`), then re-run the wizard from there. The agent may still
**read** `aidazi/ONBOARDING.md` from a submodule or sibling path; all generated
files must land under the adopter cwd.

**Wrong-repo signals (any two is enough to STOP):**

- Root has `process/delivery-loop.md` + `role-cards/` (framework layout).
- Root `AGENTS.md` is still the consumer **template** (`<adopter-name>` placeholders)
  with no `docs/current/adoption-state.md`.
- `adoption_status.py` exits non-zero with the framework-repo message.

Record **workspace OK** as the first row in `onboarding-record.md`.

> Properties: non-destructive (read-only), audited (record the check), harness-
> agnostic (plain Python CLI).

---

## Step 0 — Bootstrap the ledger and the audit record (always first)

Before anything else (after Step 0a passes):

1. **Locate the framework.** Confirm `aidazi/` (or the vendored framework root)
   is reachable from the target repo. **Recommended:** run
   `engine-kit/tools/vendor-framework.sh <aidazi-source> <adopter-root>` to copy
   the framework in (no submodule). A git submodule also works but is optional
   (greenfield STEP 1 in `docs/greenfield-guide.md`).
2. **Read-before-write the ledger.** If `docs/current/adoption-state.md` exists,
   load it and resume from the first unfinished step (property 2). If not, create
   it from `templates/adoption-state-template.md` (schema:
   `schemas/adoption-state.schema.json`).
3. **Open the onboarding record.** If `docs/current/onboarding-record.md` exists,
   append to it; else create it with a header. Every subsequent step writes one
   row here (property 4).
4. **Open the configuration map.** If `docs/current/adoption-config.md` exists,
   load it; else create it from `templates/adoption-config-template.md`
   (read-before-write + diff-confirm). This is the human-facing catalog of **what
   can be configured and where** — pair it with `adoption_status.py` (Step 8) for
   **what is configured vs missing**.

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

## Step 4a — Capture the adopter implementation-stack snapshot (minimal; NOT the Phase-3 technical plan)

Record the **adopter implementation stack** — the *product's own* engineering
facts **as they are today**: language(s), framework(s), build / package manager,
test stack, data dependencies, and deploy / runtime environment. This is a
**present-tense snapshot of what is already true or known**, not architecture
selection. Forward-looking technical decisions stay in the Phase-3 technical plan
(`docs/foundational/technical-plan.md`, greenfield STEP 5) — Step 4a never
pre-empts it, and Phase 3 remains the canonical home for those decisions.

> **Distinct from Step 5 Facet A.** This captures the *adopter implementation
> stack* (what the product is built with). Step 5 Facet A captures the *agent
> execution stack* (which harness × provider × model runs each role). Different
> concern, different file (`docs/current/implementation-stack.md` vs
> `charter.yaml`); never merge the two.

**Action — write `docs/current/implementation-stack.md`** from
`templates/implementation-stack-template.md` (read-before-write + diff-confirm).
Every item carries: the current fact/value · a status of `CONFIRMED | DEFERRED |
N/A` · provenance/evidence · and, when `DEFERRED`, a pointer to Phase 3. Set the
doc's `overall_status` to `confirmed | partial | deferred` to reflect how much is
pinned. **No silent blank fields** — an unknown is an explicit `DEFERRED`, never
an empty cell.

- **Brownfield:** populate by **read-only, evidence-based** detection, then
  recommend-then-confirm. Read manifests / lockfiles / config only — e.g.
  `pyproject.toml` · `go.mod` · `Cargo.toml` · `package.json` (language +
  framework); lockfiles (package manager); `pytest.ini` / jest config / `go test`
  (test stack); `Dockerfile` / `docker-compose.yml` / `fly.toml` / `vercel.json`
  / `Procfile` / k8s manifests (deploy / runtime). **Do not over-infer production
  architecture from a single file** — cite the evidence file per item and let the
  human confirm or correct. Record **names only** for data dependencies and
  environment variables; **never read or record a secret, credential, or env-var
  value.**
- **Greenfield:** there is nothing to detect. Offer a **track-informed starting
  point** (humble — a suggestion, not a selection) and let the human fill what is
  already known. Anything not yet decided is `DEFERRED → Phase 3`; that does
  **not** block onboarding.

The snapshot is **`load_discipline: by-role`** (Dev + Deliver load it on demand)
— it is **not** added to the default Control Plane load graph or the role-session
governance chain.

> Properties: recommendation-driven (one snapshot, recommend-then-confirm),
> non-destructive (read-only detection; names-not-values; read-before-write),
> audited (the write is a record row), harness-agnostic (plain file reads, no
> harness orchestration).

---

## Step 4b — Seed the requirement ledger + `surface` classification (default-on; OW-2 / OW-3)

Seed the **requirement ledger** — the intake-agnostic record that lets Acceptance answer
*"delivered vs the ORIGINAL requirements"* and that supplies the **input contract** for the
OW-M3 mandatory browser-E2E gate. **Default-on for new adopters (OW-AUTO):** when the
adoption has a PRD (or any durable requirement source), the wizard **drafts the ledger from
it by default** — one entry per requirement with an **agent-proposed `surface` +
`surface_confidence`** (status `proposed`) — and escalates only `surface_confidence: low`
items for a lightweight human confirm; everything else flows to sign-off. *The ledger's
existence is the switch:* generating one is what makes the existing OW-M3 sign/preflight gate
default-active for this adopter (no new gate). **Brownfield-without-PRD** may still defer
(record a `divergent` row in `docs/current/adoption-state.md`) — with no ledger the mandate
stays dormant and the loop is byte-identical to today. Full mechanics live in
`process/requirement-ledger.md` (§2.1 `surface`, §2.2 the advisory proposal model, §3.1
signature integrity); schema `schemas/requirement-ledger.schema.json`; a seeded starting
shape is `templates/requirements-ledger.example.json`.

### OW-2 — turn PRD requirements into stable ledger entries

**Action — write `docs/requirements-ledger.json`**: one durable item per requirement,
normalized from any intake channel (a PRD line, a posed question, a matured bad-case, an
acceptance gap, a direct Customer ask). Draft each entry with the human (read-before-write
+ confirm):

- **`id`** — a **stable**, unique, path-safe `REQ-…` id. Stable = it never changes once
  assigned; milestones reference it by id, so renaming silently breaks coverage.
- **`statement`** — one human-readable requirement, **end-user-observable** where possible.
- **`source.channel`** — provenance (`prd` / `posed_question` / `requirement_point` /
  `matured_bad_case` / `acceptance_gap` / `customer_direct`).
- **`customer_disposition`** — **Customer authority for every decided value** (start
  `pending`); an agent/onboarding may seed the undecided `pending` sentinel on a NEW item, but
  agents *propose* and never set a decided value (`accepted | deferred | skipped | dropped |
  modified`) — that has no engine/agent write path.
- **`surface`** — the OW-3 classification below.

**Connect milestones to requirements with `covers_req_ids`.** Coverage lives on the
**signed campaign-plan milestone** (`covers_req_ids: ["REQ-…"]`) — NOT in the ledger. It is
the single canonical, writable coverage source: the Deliver agent fills it and
`campaign_plan_signoff` signs it (see `templates/campaign-plan.example.json`). The ledger
stores no writable coverage and no delivery status.

> **Declaring `covers_req_ids` on a milestone (with a ledger wired) activates strict
> checks.** Every covered id must then (1) **exist** in the ledger, (2) be an
> **unambiguous** id (no duplicate ledger entries for it), and (3) carry a **valid
> `surface`** (∈ `user_facing | non_user_facing`). Any miss ⇒ sign-off refuses (OW-3).
> *The wired ledger is the activation trigger* — a `covers_req_ids` with no ledger present
> stays dormant.

**Wiring (optional):** the ledger path defaults to `docs/requirements-ledger.json`. Set
`charter.yaml` `requirements.ledger_path` only if you keep it elsewhere.

### OW-3 — `surface`, the observable user journey, and the browser-E2E mandate

Classify each requirement's `surface`:

- **`user_facing`** — meeting it produces something the **end user OPERATES**: a
  browser-operable UI or a user journey (e.g. *"a recruiter browses candidate cards and
  clicks Shortlist, and the shortlist updates"*).
- **`non_user_facing`** — a backend / data / infra requirement with no direct end-user
  operation (e.g. *"import dedup merges records with an identical email"*).

**For every `user_facing` requirement, write the `statement` as the observable user
journey** browser-E2E must judge — the concrete steps a user performs and the result they
should see. That journey *is* the acceptance target.

**The mandate (OW-M3):** a milestone that covers ANY `user_facing` requirement MUST resolve
its functional acceptance to **`browser_e2e`** — no downgrade to `static`. Browser-E2E is
therefore **required evidence** for user-facing work. It is **advisory for ship
authority**: OW-M3 mandates that the evidence is *produced and judged*; it does **not**
auto-authorize shipping — the Customer's sign-off authority is unchanged (M3 stays advisory
in v1).

**When sign-off refuses** (`--sign-plan` and the real-run preflight both exit non-zero and
write no signature), there are **exactly two valid resolutions** — there is **no waiver or
bypass**:

1. **Set the milestone's `functional_acceptance: "browser_e2e"`** — the requirement really
   is user-facing, so give it the mandated evidence class; or
2. **(Customer) correct the classification** — reclassify the requirement's `surface` to
   `non_user_facing` in the ledger — and **re-sign**.

The same refusal fires for an **unclassified** covered requirement (absent from the ledger,
missing/invalid `surface`, or duplicated): add exactly one ledger entry with a valid
`surface`, then re-sign.

### OW-4 — the runnable native-E2E config proposal (Phase-4; default-on for eligible reqs)

Resolution #1 above is not "hand-write a browser-E2E config from scratch." For each eligible
**user-facing** requirement, the agent **default-drafts a COMPLETE, runnable native-E2E
proposal** (`engine-kit/tools/e2e_config_proposal.py`) by inspecting the repo (Step-4a
impl-stack snapshot, `frontend/e2e/*.spec.ts`, package scripts, dev-server cmd) — never an empty
skeleton the Customer must fill in. The proposal carries every element: `executor_kind:
external_test_runner` + `runner_argv`, `spec_path`, `app_start_cmd`/`readiness`/`base_url`/
`allowed_origins`, the signed `criterion_map`, `evidence_retention_path`, `timeouts` + retry +
the `e2e_remediation` (max_rounds / no-progress) budget, cleanup `lifecycle_operations`, **NAMED
`secret_refs` only** (`env:NAME` — never a literal secret), the `covers_req_ids` / `surface`
linkage, the browser-E2E functional checklist, and the autonomy level + §1.7-G eligibility.

It is **advisory** exactly like the `surface` proposal (`proposal_status ∈ proposed|confirmed`,
`proposal_confidence ∈ high|low`; escalate only `low`): no new runtime gate, binds no hash, and
binds only on **whole-proposal human authorization** (paste into the charter, then sign). Two
fail-closed guardrails run before it is presented: **completeness** (`proposal_completeness_violations`
— reject a skeleton) and **no-leak** (`secret_leak_violations` — reject any materialized secret).
The proposal also pins `required_framework_capabilities`, so a future aidazi that lacks a
native-E2E capability **fails closed at preflight** (naming the missing capability + upgrade
action). Worked example: `examples/native-e2e-adopter/`. Existing adopters get a READ-ONLY
migration audit (`engine-kit/tools/e2e_migration_audit.py`) instead of an automatic rewrite.

**Authority + integrity.** An agent MAY *propose* a `surface`; it binds only when the
Customer **signs** the covering scope. The covered-requirement surface basis is snapshotted
into the signed scope hash, so a **post-sign surface flip ⇒ `stale` ⇒ re-sign** (Customer
authority — the same re-sign path as any scope change). A correctly-signed plan runs on with
**no new pause**. Re-sign with:

```bash
python engine-kit/scheduling/run_loop.py --campaign <plan> --charter <charter> --sign-plan
```

> Properties: recommendation-driven (agent drafts entries + proposes `surface`; the
> Customer confirms by signing), additive (no ledger ⇒ dormant, byte-identical),
> audited (the ledger is version-controlled with an append-only `history`),
> harness-agnostic (a JSON artifact + the sign CLI, no harness orchestration).

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
(claude_code↔anthropic, codex↔openai). Capability is validated in Step 8. This is
the **agent execution stack** — distinct from the **adopter implementation stack**
captured in Step 4a (`docs/current/implementation-stack.md`); the two are never
merged into one field.

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
   1a. **Root `CLAUDE.md` harness wiring** (normative: `governance/context_briefing.md`
       §1.1). Claude Code auto-loads `CLAUDE.md`, **not** a bare `AGENTS.md`, so a
       Claude-Code session at a root that has only `AGENTS.md` starts without the default
       Control Plane entry. Generate a **one-line root
       `CLAUDE.md` containing exactly `@AGENTS.md`** so Claude Code imports the same entry
       Codex auto-loads. Generate it **regardless of the primary harness** — Claude Code and
       Codex are used alternately, and one wiring serves both. Discipline: **read-before-write
       + diff-confirm** like every artifact; if a `CLAUDE.md` already exists (brownfield),
       **do not overwrite it** — show the human the diff and, only after confirmation, ensure
       it contains a valid `@AGENTS.md` import (append the line; never duplicate the governance
       chain into it). Never replace existing human `CLAUDE.md` content.
2. **`charter.yaml`** — from `templates/mission-charter.yaml`, populated with the
   Step 5 role bindings (execution/skills/connectors), the Step 7 autonomy
   posture, budget, and `tooling.eval.cmd`. Schema:
   `schemas/mission-charter.schema.json`. (Pure human-paste adopters who skip the
   orchestrator may defer this — greenfield STEP 7 is optional.)
3. **`docs/current/*`** — the three domain contracts plus state ledgers, per the
   worked example: `domain_taxonomy.md`, `runtime_invariants.md`,
   `eval_acceptance_bars.md`, `agent_context_guide.md`, the already-created
   `adoption-state.md` + `onboarding-record.md` + `adoption-config.md`, and
   `implementation-stack.md`
   (created in Step 4a). (`docs/domain-adaptation.md` walks the three domain
   contracts; the implementation-stack snapshot is separate — product facts, not
   domain semantics.)
4. **`docs/requirements-ledger.json`** — **default-on for new adopters (OW-AUTO)**. Seed
   it from the PRD (Step 4b), copying the shape from `templates/requirements-ledger.example.json`
   (**seeded, not blank**): one entry per requirement with an agent-proposed `surface` +
   `surface_confidence` (status `proposed`) and `customer_disposition: pending`. **Skip ONLY
   for brownfield-without-PRD** (record a `divergent` row) — its absence keeps OW-M3 dormant
   (byte-identical to today). Schema: `schemas/requirement-ledger.schema.json`; the ledger's
   existence is what makes the existing OW-M3 sign/preflight gate default-active (no new gate).
5. **Copy `engine-kit/`** into the adopter repo (the copyable reference
   implementation — driver, adapters, validators, audit, connectors). It is
   non-normative: the spec wins on any conflict (`engine-kit/orchestrator/README.md`).
6. **Vendor the default skills** under `skills/vendored/<id>/` (each with its
   upstream `LICENSE` + provenance), bound per Step 5; pins recorded in
   `skills/skills.lock`.
7. **Create `.orchestrator/` with control + audit dirs** — `.orchestrator/control/`
   for the lightweight default-session state index (`state.json`) and intent ledger
   (`intents.jsonl`), plus `.orchestrator/audit/` for the hash-chained per-loop
   ledger (charter `audit.ledger_dir`, default `.orchestrator/audit`). This is the
   **repo-side** registry/control area (`loops.json` plus control state); per-loop
   live state/audit/transcripts land under **`.runs/<loop_id>/`** (gitignored).
8. **Ensure `.gitignore` covers loop + secret paths** — at minimum append (read-before-
   write + diff-confirm if `.gitignore` already exists):
   ```
   .orchestrator/
   .runs/
   .env.local
   ```
   `.runs/` is the default run-dir root (`run_loop.py`); keeping it gitignored lets
   you tail live progress in-repo without polluting the delivered diff.
9. **(Optional — ONLY when enabling Loop Memory) Create the memory store.** If the
   charter sets `memory.enabled: true`, scaffold `<memory.root>/` (default `memory/`)
   with an empty `entries/` subdir and a seed `index.md` (the store also self-creates on
   first use). **With Loop Memory OFF (the default), create NOTHING** — the loop is
   byte-identical to no memory. The root resolves against the charter dir and must stay
   inside it (`modules/m-memory.md`; `schemas/mission-charter.schema.json`).

> **Requirement ledger (item 4, default-on):** for a new adopter with a PRD, ensure
> `docs/requirements-ledger.json` is generated (seeded from
> `templates/requirements-ledger.example.json`), version-controlled, and that
> `charter.yaml` `requirements.ledger_path` is set only if it differs from the default.
> Only brownfield-without-PRD skips it (records a `divergent` row). Milestone
> `covers_req_ids` and plan sign-off happen later at campaign time (Step 9 /
> `FIRST-LOOP.md`), not here — Deliver auto-derives `covers_req_ids` from the ledger then.

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
- **The 9 MANDATORY_CHECKPOINTS always fire.** The charter MAY add custom
  checkpoints (`mandatory_checkpoints_added`) but MAY NOT omit / empty / disable /
  override any of the 9 defaults — the charter validator (Step 8) rejects all four
  bypass shapes (`process/delivery-loop.md` §4.2.2-§4.2.3; Constitution §1.7-D).
- `tooling.acceptance.on_fix_required.human_confirm_required` MUST be `true` and
  `route_options` non-empty (Constitution §1.7-C).
- **(Optional) `memory.enabled`** — turn on Loop Memory (default OFF). When on, the loop
  injects prior generalizable lessons into role prompts at ingress and records lessons at
  close (`modules/m-memory.md`). Enabling it does **not** raise autonomy, does **not**
  auto-edit any load-bearing artifact (skill/charter/prompt), and adds **no** checkpoint —
  but it **does** change role prompt context, so record the enable decision in
  `adoption-state.md` (a `divergent` row vs the OFF default) and the §3.6 calibration
  policy continues to apply (a memory entry only *suggests* a load-bearing change; the
  human approves it). `memory.root` defaults to `memory` (resolved against the charter dir,
  contained within it); CLI `--memory-root` overrides.

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
2. **`adopter_wiring_validator`** — confirm the Step 6.1a harness root-file wiring
   (`governance/context_briefing.md` §1.1) is actually in place, so a Claude-Code
   cold-start gets the root Control Plane entry:
   ```bash
   python engine-kit/validators/adopter_wiring_validator.py . --harness claude_code
   ```
   **PASS** (exit 0, no findings) ⇒ root has a `CLAUDE.md` whose valid line-level
   `@AGENTS.md` imports the same-root `AGENTS.md`. **FAIL** (exit non-zero) ⇒ a Claude-Code
   target with `AGENTS.md` but no `CLAUDE.md`; a `CLAUDE.md` with no valid import, an escaping
   import (`..`, absolute, subdir, symlink redirect), or one that re-copies the chain instead of
   importing only `@AGENTS.md`; or **contradicting** persistent harness declarations (charter vs
   adoption-state pin declaring disjoint harnesses) — fix and re-run. **WARN** (exit 0) ⇒ harness
   unspecified, or a Cursor target (a bare `AGENTS.md` is not Cursor wiring); WARN does not block.
   Omit `--harness` to validate against the charter's declared harness(es) instead; for a
   Codex-only adopter the bare `AGENTS.md` PASSes and no `CLAUDE.md` is required.
3. **`control_plane_validator`** — confirm the default session stays lightweight and
   schema-backed:
   ```bash
   python engine-kit/validators/control_plane_validator.py .
   ```
   **PASS** ⇒ `AGENTS.md` has the required `control-plane-load` block and the default
   load graph does not include role cards, action banks, handoffs, audit transcripts,
   eval artifacts, archives, or broad globs. **FAIL** ⇒ fix `AGENTS.md` before using
   natural-language default sessions.
4. **`adoption_status`** — run the adoption readiness report (configured vs missing;
   never reads secret values — env-var **names** only):
   ```bash
   python engine-kit/validators/adoption_status.py . --write-readiness docs/current/adoption-readiness.md
   ```
   Exit 0 ⇒ workspace is the adopter repo (not the framework repo) AND every
   **REQUIRED** row is `[✓]`. The `--write-readiness` flag writes
   `docs/current/adoption-readiness.md` (human snapshot; re-run anytime to refresh).
   Pair with `docs/current/adoption-config.md` (the configuration map from Step 0).
   Fix any `[ ]` / `[~]` / `[✗]` REQUIRED items and re-run until exit 0.
5. **Structural checks** — confirm the generated tree exists and resolves:
   `AGENTS.md`, `docs/current/*` (including `adoption-config.md` +
   `adoption-readiness.md`), the copied `engine-kit/`, vendored skills +
   `skills/skills.lock`, `.gitignore` covers `.runs/` + `.env.local`,
   `.orchestrator/control/`, `.orchestrator/audit/`, and that the intent contract triple is present. Also
   confirm the **Step 5 Facet A preflight** ran: every bound `(harness, provider)`
   pair has a `reachable yes` row in the onboarding record, or an explicit
   human-recorded deferral in `adoption-state.md`.
6. Record the green result (all validators + adoption_status exit codes + timestamp)
   in the onboarding record. Mark the relevant `adoption-state.md` rows `at-spec`.

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
- **Drive the whole goal** (continuous multi-milestone delivery, 以终为始): default
  human operation remains Control Plane-first and single-milestone unless the
  adopter explicitly opts into Campaign mode. In the default topology,
  `charter.yaml` is the active execution source and generated
  `docs/milestone-backlog.md` is a status view. Once the Deliver agent has authored
  + the Customer has signed an ordered campaign plan
  (`templates/campaign-plan.example.json`; `schemas/campaign-plan.schema.json`), the
  **Campaign Loop** can drive the ENTIRE backlog through the same driver, pausing
  only at human gates. Humans normally ask the Control Plane to continue/resume;
  `engine-kit/scheduling/run_loop.py --charter charter.yaml --campaign
  campaign-plan.json` is the internal/automation interface. See `FIRST-LOOP.md` →
  "Drive the whole goal" + `process/campaign-loop.md`.
- **Quick-Fix lane** (loop-independent; **usable on Claude Code and Codex**). For small,
  non-behavioral fixes a human may use the **Quick-Fix lane** (`process/quickfix-lane.md`,
  `QUICK-FIX.md`) instead of a loop — a human-explicit, per-session lane that runs OUTSIDE
  the Delivery/Campaign Loop. It is **not** a loop and never skips MANDATORY_CHECKPOINTS.
  Naming discipline (§1.7-E): keep it distinct from every "*Loop*" concept. The
  `claude_code` (`archive/2026-06-22-quickfix-claude-code-e2e-evidence.md`) and `codex`
  (`archive/2026-06-22-quickfix-codex-e2e-evidence.md`) harnesses are both `supported`
  (recorded real-launch cold-start evidence); `kimi_code` is `unsupported`. The launch gate
  is strict — anything not `supported` **fails closed**, so on other harnesses do everything
  through the loops above or pure human-paste.

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

After onboarding (or anytime), humans can re-check configured vs missing:

```bash
python engine-kit/validators/adoption_status.py .
```

See `docs/current/adoption-config.md` for the full configuration map.

## Packaging note (optional, not created here)

This wizard MAY later be packaged as a discoverable skill at
`skills/aidazi-onboarding/SKILL.md` (the SKILL.md standard, `process/role-skill-model.md`)
so a harness can surface "run aidazi onboarding" directly. That packaging is
**out of scope for this file** and is **not** created by the wizard; `ONBOARDING.md`
remains the source-of-truth either way.

---

End of Onboarding Wizard.
