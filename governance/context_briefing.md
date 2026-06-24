---
title: aidazi Context Briefing
doc_tier: governance
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-07
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: always-load
size_target: 16KB
split_trigger: if per-task reading lists grow past 6 entries each, move to a process/agent-context-guide.md
notes: >
  Layer-A always-loaded cold-start reading discipline + Context Pack Prompt.
  Defines how every role and every session should brief itself: what to load,
  in what order, what to verify before producing output. Adopter-facing
  counterpart (per-task reading lists tailored to the adopter's domain) lives
  in `docs/current/agent_context_guide.md` in the adopter repo.
---

# aidazi Context Briefing

This is the cold-start reading discipline for every agent session in the framework.

The `aidazi/` framework + an adopter repo together are large. An agent that loads docs in near-arbitrary order tends to anchor on whichever doc arrives first, which is often the wrong tier for the question being asked.

This file does four things:

1. Defines the **cold-start load order** that every session executes first (§1).
2. Splits default **Control Plane Session** cold-start from explicit 5-role cold-start (§1.0 and §1.2).
3. Provides **per-role briefing lists** — what each of the 5 roles loads before doing its work (§2).
4. Ships a reusable **Context Pack Prompt** (§3) that asks the agent to return explicit source-of-truth decisions, doc-status warnings, and known risks before it starts.

It also defines two pre-output verification checks: the **Research-Acceptance contract symmetry check** (§4) and the **adoption-state load order** (§5). And a pointer to the **Δ-18 trigger** (§6) — when to load the Delivery Loop spec.

## §1 Cold-start load order

Before any work output, every agent session first identifies whether it is a default Control Plane Session or an explicitly activated role session.

### §1.0 Default Control Plane Session (unless a role is explicit)

If the human has not explicitly activated Research / Deliver / Dev / Code Reviewer / Acceptance, the session is the default **Control Plane Session**. It is the natural-language command surface: classify the human request, record a durable intent, read the small control state index, and dispatch/resume/prepare the proper role or runner path.

It is **not** a sixth role. It does not sign Research briefs, Deliver close verdicts, Dev work, Code Reviewer findings, or Acceptance verdicts.

The default Control Plane Session loads only:

1. The adopter root governance entry (`AGENTS.md`, reached through the harness root file per §1.1).
2. The `control-plane-load` block in that `AGENTS.md`.
3. `.orchestrator/control/state.json`, if present.
4. Recent or summarized `.orchestrator/control/intents.jsonl`, if present.
5. Open checkpoint refs named by the state index.
6. `docs/current/adoption-state.md` and `docs/current/agent_context_guide.md` only as listed by the adopter root `AGENTS.md`.

It loads `process/control-plane-routing.md` and the control-plane schemas on demand when it must classify, append, validate, or debug a route.

It does **not** default-load role cards, full process docs, `docs/action_bank.md`, full handoff docs, archives, audit transcripts, eval artifacts, old research briefs, proposals, or broad globs.

### §1.1 Harness root-file wiring (normative)

Role-session cold-start step 4 and Control Plane Session cold-start step 1 assume the adopter's `AGENTS.md` control-plane entry is in context from the
first turn. Whether that happens automatically depends on **which root file the coding harness
auto-loads** — and harnesses differ. This subsection is the **single normative source** for
adopter root-file wiring; the consumer template (`AGENTS.md` preamble), `ONBOARDING.md`, the
worked example (`examples/minimal-greenfield/`), and the deterministic check
(`engine-kit/validators/adopter_wiring_validator.py`) all defer here.

| Harness | Auto-loads at repo root | Required adopter wiring |
|---|---|---|
| **Claude Code** | `CLAUDE.md` (a bare `AGENTS.md` is **not** auto-loaded) | a root `CLAUDE.md` that **imports** the same-root `AGENTS.md` |
| **OpenAI Codex** | `AGENTS.md` | the root `AGENTS.md` (the existing chain) — **no** `CLAUDE.md` required |
| **Cursor** | its own rules mechanism (`.cursor/rules` / `.mdc`) | a real Cursor rules entry — a bare `AGENTS.md` is **not** Cursor wiring |
| headless / API-backed | nothing at the repo root (driven programmatically) | n/a — no root-file requirement |

**Claude Code canonical wiring (fixed shape):**

```
<adopter-root>/CLAUDE.md
    → @AGENTS.md
<adopter-root>/AGENTS.md
    → the existing canonical Control Plane entry + role/on-demand governance refs
```

The `CLAUDE.md` carries the one-line import `@AGENTS.md` (it MAY also hold other human-authored
notes). It **MUST NOT** re-copy the governance chain — a second full entry point is forbidden
because the two copies drift. `AGENTS.md` stays the single source of the root entry; `CLAUDE.md` only
routes Claude Code into it. The import must reference the **same-root** `AGENTS.md` by a clean
relative path: no absolute path, no `..`, no subdirectory, no symlink redirect.

Because Claude Code and Codex may be used **alternately** on the same adopter repo, the canonical
greenfield scaffold ships **both** a root `AGENTS.md` and a root `CLAUDE.md` (`@AGENTS.md`); that
single wiring satisfies both harnesses at once. A Claude-Code adopter whose root holds only a bare
`AGENTS.md` (no `CLAUDE.md`) gets **none** of the Control Plane entry at cold-start — the
default routing baseline is silently absent. Run
`adopter_wiring_validator.py` to catch it deterministically: at onboarding (Step 8) and after any
scaffold.

### §1.2 Role-session cold-start (explicit activation only)

When a session is explicitly activated as one of the five roles, before any role work output it loads, in order:

1. `aidazi/governance/constitution.md` (this is `always-load`).
2. `aidazi/governance/doc_governance.md` (this is `always-load`).
3. `aidazi/governance/context_briefing.md` (this file; `always-load`).
4. The adopter's root entry — the `AGENTS.md` that names the project, instantiates the 5-role registry, defines the default Control Plane load block, and names the role/on-demand governance chain. **Which root file the harness auto-loads to reach that `AGENTS.md` is harness-specific — see §1.1.**
5. The adopter's `docs/current/adoption-state.md` — read this BEFORE loading process docs so you know which Δs are at-spec vs divergent vs not-applicable in this adopter (§5).
6. The role card for the role you're about to play (e.g., `aidazi/role-cards/dev-agent.md`).
7. The per-role briefing list in §2 below.

Then begin work.

**Why this order**:
- Steps 1-3 give you the universal framework boundaries (Constitution + how to read docs + how to brief yourself).
- Step 4 tells you which adopter you're in.
- Step 5 tells you what's customized vs at-spec (so you don't apply a Δ that the adopter has documented as divergent).
- Step 6 tells you what role you're playing — different roles read different things.
- Step 7 narrows to the task-specific context.

## §2 Per-role briefing lists

Each list assumes steps 1-5 above are already loaded. Each list is the **starting point**, not exhaustive; if your task pulls you into territory the list doesn't cover, follow the per-task lookup in §2.6.

### §2.1 Research Agent

For producing `docs/research-briefs/<id>.md` with closure_contract.

- `aidazi/role-cards/research-agent.md` — your activation prompt.
- `aidazi/process/domain-discovery-process.md` (Δ-2) — D1/D2/D3 elicitation pattern.
- `aidazi/process/agent-design-elicitation.md` (Δ-15) — 6 questions + 4 inventories + closure_contract drafting.
- `aidazi/process/agent-creation-prerequisites.md` (Δ-16) — 7 prereq categories; check each is READY / DEFERRED / N/A.
- `aidazi/templates/compact-research-brief.md` — output template.
- `aidazi/schemas/research-brief.schema.json` — output schema validation.
- Adopter inputs: Customer prompt (raw); existing `docs/proposals/<id>.md` if any; relevant transcripts / data; recent `docs/diagnostics/failure-briefs/` if Path 2 (bad-case-matured input).

### §2.2 Deliver Agent (Tech Lead)

For producing milestone / sub-sprint plans + close decisions.

- `aidazi/role-cards/deliver-agent.md` — your activation prompt.
- `aidazi/process/milestone-framework.md` — 3-5 sub-sprints per milestone; close cadence.
- `aidazi/process/tech-architecture-decision-catalog.md` (Δ-3) — 8 decisions incl abstraction-layer §1.7-A.
- `aidazi/process/typeA-runtime-architecture-skeleton.md` (Δ-6) — if Type A or A+B.
- `aidazi/process/artifact-taxonomy.md` (Δ-12) — 14 artifacts + per-role read-list.
- `aidazi/process/post-deployment-iteration.md` (Δ-9) — OBS triage L1/L2; how Acceptance gap routes become R-items.
- `aidazi/process/common-detours-and-warnings-typeA.md` (or typeB/typeC) — pitfalls per track.
- `aidazi/templates/deliver-close-taxonomy.md` — A/B/C/D verdict + subclasses.
- `aidazi/templates/sprint-objective.md` + `aidazi/templates/milestone-objective.md` + `aidazi/templates/compact-dev-prompt.md` — output templates.
- Adopter inputs: research brief from gate 1; action_bank.md; handoff.md §0/§1; recent codex-findings.md; if Path 3 — acceptance report + gap brief.

### §2.3 Dev Agent

For implementing per sprint-NNN-dev-prompt.md.

- `aidazi/role-cards/dev-agent.md` — your activation prompt.
- `aidazi/process/prompt-artifact-rules.md` (promoted from csagent §9) — self-containment invariant.
- `aidazi/process/context-passing-efficiency.md` (Δ-5) — context budget discipline.
- The specific `compact/sprint-NNN-dev-prompt.md` — this is your self-contained job spec; it carries everything you need.
- Adopter `docs/current/` runtime contracts + domain context (the prompt's `load_list` names these explicitly per §1.4-i of constitution).

Sandbox: workspace-write; no network; no git push (per Constitution §3.3 Dev Agent row).

### §2.4 Code Reviewer Agent

For producing `docs/codex-findings.md` verdict at sub-sprint close or §4.3 trigger.

- `aidazi/role-cards/code-reviewer-agent.md` — your activation prompt.
- `aidazi/templates/anti-hardcode-review-kernel.md` — 9-question kernel; the canonical lens.
- `aidazi/schemas/review-verdict.schema.json` — output schema.
- Adopter inputs: dev diff; handoff.md (the sub-sprint's §1-§11); sprint_objective.md; the bad-case suite (`eval/bad_cases/`).
- Adopter `docs/current/` runtime contracts (for the §1.3/§1.4 ownership lens).

Tool whitelist: Read, Grep, Glob. No edits. No network. No git push (per Constitution §3.3 Code Reviewer row).

### §2.5 Acceptance Agent

For producing `docs/acceptance-reports/<scope>-acceptance-report.md` at milestone close / release cut / sub-sprint close (per charter).

- `aidazi/role-cards/acceptance-agent.md` — your activation prompt.
- `aidazi/templates/compact-acceptance-prompt.md` — output template + judging discipline.
- `aidazi/schemas/acceptance-verdict.schema.json` — output schema.
- Adopter inputs: the research-brief's closure_contract (THE evaluation contract; §4 below has the symmetry check); dev evidence (bad-case suite results + execution trace artifacts produced by orchestrator F5 pattern per `process/delivery-loop.md` §4.2.6); Code Reviewer verdict (latest codex-findings.md).
- (Optional) prior acceptance reports for residual risk lineage.

Tool whitelist: Read, Grep, Glob. No edits. No network. No git push.

**Spawn isolation** (Constitution §1.7-C): your session was spawned from Customer paste OR orchestrator with calibration passed (per `process/delivery-loop.md` §4.2.4). If you find evidence you were spawned from a Deliver or Dev session, halt and surface §1.7-C breach.

**Calibration gate** (Constitution §3.6): if `charter.autonomy.level=fully_autonomous_within_budget` AND `tooling.acceptance.judge_calibration.status=uncalibrated`, your verdict is advisory only; orchestrator degrades to `human_on_the_loop` and an advisory `pass` HALTs at `advisory_acceptance_pass_signoff` for human sign-off (it does NOT auto-ship). Confirm calibration status before treating verdict as authoritative.

### §2.6 Per-task lookup (when the role list doesn't cover what you need)

If your task pulls you into territory the role list doesn't cover, route via the task type:

| Task subject | Load this first |
|---|---|
| Domain discovery / industry research | `process/domain-discovery-process.md` (Δ-2) + adopter `docs/foundational/business-need.md` (or merged §5.3.1 brief) |
| Tech architecture decisions | `process/tech-architecture-decision-catalog.md` (Δ-3) + adopter `docs/foundational/technical-plan.md` |
| Doc lifecycle question | `process/doc-lifecycle-rules.md` (Δ-4) + `governance/doc_governance.md` |
| Type A runtime / phase pipeline | `process/typeA-runtime-architecture-skeleton.md` (Δ-6) + adopter `docs/current/runtime_invariants.md` |
| Worked example sync question | `process/worked-example-instance.md` (Δ-7) + the specific `examples/<ref>/` |
| Eval / bad-case lifecycle | `process/badcase-lifecycle.md` + adopter `eval/bad_cases/_manifest.md` |
| Profile A/B/C/hybrid decision | `process/profile-aware-maturity.md` (Δ-14) + adopter charter |
| Agent design (greenfield) | `process/agent-design-elicitation.md` (Δ-15) + `process/agent-creation-prerequisites.md` (Δ-16) |
| Common pitfalls (mid-flight detour spotting) | `process/common-detours-and-warnings-type<A\|B\|C>.md` (Δ-17) |
| Δ-18 Delivery Loop / orchestrator | `process/delivery-loop.md` (Δ-18) + `templates/mission-charter.yaml` + `schemas/mission-charter.schema.json` (see §6 below) |
| Self-governance / bloat metrics | `process/self-governance.md` |
| Fold-back / lessons | `process/fold-back-protocol.md` + `templates/lessons-learned-template.md` |
| Directory taxonomy (where does X go?) | `docs/directory-taxonomy.md` |
| Two Loops naming | `docs/two-loops-explainer.md` (§1.7-E enforcement) |
| Greenfield bootstrap | `docs/greenfield-guide.md` |
| Brownfield adoption | `docs/brownfield-guide.md` |
| Friction pattern lookup (F1-F15) | `docs/friction-playbook.md` |

This table is the framework's "yellow pages." For per-adopter task lists tailored to the adopter's domain, see the adopter repo's `docs/current/agent_context_guide.md`.

## §3 Context Pack Prompt

When briefing an agent on a non-trivial task, include a "context pack" step BEFORE any plan or code. Paste the prompt below, adapted to the task. The agent answers BEFORE producing a plan or diff.

```
You are working in this repo. Before proposing a plan or any code change,
build a context pack for the task described below. Do not start coding.

Task: <one-paragraph description of what we want to do>

Role you are playing: <Research | Deliver | Dev | Code Reviewer | Acceptance>

Read the following first (in order):
1. aidazi/governance/constitution.md
2. aidazi/governance/doc_governance.md
3. aidazi/governance/context_briefing.md
4. <adopter root>/AGENTS.md (reached via the harness root file per §1.1 — Claude Code: a root CLAUDE.md importing @AGENTS.md; Codex: AGENTS.md directly)
5. <adopter root>/docs/current/adoption-state.md
6. aidazi/role-cards/<your-role>.md
7. The per-role briefing list in context_briefing.md §2 for your role

Sample additional docs and code paths as the per-task lookup §2.6 suggests;
you do not need to read everything end-to-end, but you must read enough to
answer the questions below.

Return your context pack in this exact shape:

1. Relevant docs and code paths (with tier + status if known)
2. Source-of-truth decision: if multiple docs cover this question, which is
   the source of truth, and why?
3. Doc-status warnings: which docs are partial / proposal / deferred /
   superseded / unknown and how does that affect this task?
4. Adoption-state warnings: which Δs are marked divergent in this adopter
   and might affect this task? Cite the rationale field if it applies.
5. Known risks: what could go wrong; what is intentionally out of scope.
6. Open questions: what you cannot determine from docs + code alone (incl.
   any §1.7 forbidden-list checks that need human judgment).
7. Proposed plan: only after answering 1-6.

If 1-6 surface a Constitution §1.7 breach (e.g., the task would require a
new keyword/regex to fix a semantic failure), halt and surface the breach
before proposing a plan.
```

For roles with their own activation prompts (`role-cards/*-agent.md`), the role card includes its own version of this context pack; use the role card's version when present.

## §4 Research-Acceptance contract symmetry check

Constitution §3.4 boundary invariant #4 — Research-Acceptance contract symmetry — needs an explicit pre-output check on both sides.

**For the Research Agent**, before finalizing the closure_contract paragraph:

1. Is the positive shape stated in customer-perspective language (NOT implementation language)?
2. Is the anti-pattern named in observable terms (would the Acceptance Agent be able to spot it in delivered behavior)?
3. Are the anchor phrases EXEMPLAR — i.e., the kind of phrasing a good response might use — NOT regex matchers?
4. Could a peer Acceptance Agent, reading only this closure_contract + delivered evidence, return a defensible verdict? If not, the contract is under-specified; expand.

**For the Acceptance Agent**, before evaluating delivered behavior:

1. Does the closure_contract cover the criteria you're about to judge against? If you find yourself wanting to evaluate a criterion the contract doesn't specify, route via `suggested_route: research_contract_revision` instead of widening the evaluation silently.
2. Is the contract version you're reading the version Customer signed at gate 1 (not an edit slipped in mid-milestone)? Confirm by checking `customer_signed` front-matter + `signed_date`.
3. Has the contract changed between sign-off and now? If yes, halt; Customer re-sign-off required (gate 1 re-fires).

Both sides skipping their check is what causes the "we built the wrong thing but said pass" failure mode. The two checks are cheap; perform both.

## §5 Adoption-state load order

`docs/current/adoption-state.md` MUST be loaded BEFORE process docs.

**Why**: process docs describe framework defaults. Adoption-state names which Δs the adopter has marked divergent (with rationale) — and which framework defaults the adopter has overridden. Loading process docs before adoption-state means applying defaults that the adopter has documented as not-in-effect.

The adoption-state schema (per Constitution §7.2 + `templates/adoption-state-template.md`):

```yaml
---
title: <adopter-name> Adoption State vs aidazi framework
adopter_name: <name>
framework_version: v4.0.0
last_reviewed: <YYYY-MM-DD>
review_cadence: per milestone close
---

# Per-Δ status

| Δ | v4 spec | Adopter status | Gap notes | Plan |
|---|---|---|---|---|
| Δ-1 Anatomy | T0 | at-spec | — | — |
| ... | | | | |

# Drift reasons (for `divergent` rows)

- Δ-N: <rationale>

# Lessons proposed for upstream fold-back

| Date | Topic | Lesson file | Status |
|---|---|---|---|
| ... | | | |
```

Status enum: `at-spec | partial | divergent | not-applicable | superseded-by-framework`.

**Rules of thumb when reading adoption-state**:

- `at-spec` → apply the framework default as written.
- `partial` → apply the framework default but verify which sub-parts are implemented; ask Customer / Deliver before assuming.
- `divergent` → adopter has overridden the default. READ the rationale. Apply the adopter's override, NOT the framework default.
- `not-applicable` → this Δ doesn't apply to this adopter's track; skip.
- `superseded-by-framework` → adopter was at-spec at an older framework version; framework has since evolved. Check the migration guide.

If an adoption-state row has `status: divergent` against §1.7 of constitution, halt: §1.7 hard requirements cannot be overridden (Constitution §1.8). Surface the contradiction; do NOT apply the divergence.

## §6 Δ-18 Delivery Loop trigger

Load `process/delivery-loop.md` when ANY of these is true for your session:

- The adopter's charter exists at `<adopter>/charter.yaml` (or path declared in `adoption-state.md`).
- The task involves authoring, editing, or reasoning about a `mission-charter.yaml`.
- Your role is Acceptance Agent AND `tooling.acceptance.mode ≠ off`.
- The task involves resolving a MANDATORY_CHECKPOINT.
- The task involves scope_envelope_check, F5 evidence pattern, or calibration.
- A previous step surfaced a §1.7-D breach risk (charter editing MANDATORY_CHECKPOINTS).

If none of the above is true, you are in pure human-paste mode (manual flow). The 5-role chain still applies; the orchestrator implementation does not. `process/delivery-loop.md` §4.2.1 explains this conditional adoption.

## §7 Pre-output checklist (every role, every session)

Before emitting your final work product:

1. **Constitution §1.7 forbidden-list check** — does anything in your output trigger a forbidden pattern (keyword/regex/if-else for semantic decisions; widening eval to accept a bot mistake; Auto Loop ↔ Delivery Loop conflation)?
2. **Role boundary check** — are you producing only what your role is authorized to produce (Dev doesn't author scope; Deliver doesn't write feature code; Acceptance doesn't widen the contract)?
3. **Self-containment check** — if you're authoring a compact prompt, does it carry `context_budget` front-matter with `self_contained: true`? (§1.4-i of constitution.)
4. **closure_contract / closure_criterion shape check** — if you're authoring one, are positive shape + anti-pattern + anchor phrases all present? (§1.7-B of constitution.)
5. **Schema validation** — if your output has a JSON schema (e.g., review verdict, acceptance verdict, deliver-close verdict), does it pass the schema?
6. **Adopter override check** — does your output respect adoption-state.md `divergent` rows?

A "no" to any of the above is a halt signal: surface the issue, do not emit.

## §8 Editing this doc

This is a governance-tier doc. Edits land at fold-back sub-sprint cadence (per Constitution §8). The four editing-discipline checks from Constitution §8 apply (timelessness; principle vs current-state; necessity; durable shift).

Adopter-specific per-task reading lists do NOT live here — they live in the adopter's `docs/current/agent_context_guide.md`. This file is the framework-level shape; the adopter copies and specializes.

---

End of Context Briefing.
