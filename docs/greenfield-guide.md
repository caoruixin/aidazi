---
title: Greenfield guide — landing aidazi into a fresh project
doc_tier: application-guide
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-12
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 22KB
split_trigger: if the Phase 1-5 walk (STEP 5) grows past 8KB, move the per-phase detail to docs/application-funnel.md and keep the step skeleton here
notes: >
  Greenfield adoption path — for a new codebase, or an existing codebase with
  no agent/workflow/demo yet. 7-step bootstrap: initialize → elicit → prereq
  gate → instantiate → walk Phase 1-5 funnel → bootstrap iteration loop →
  (optional) bootstrap orchestrator. Companion to docs/application-funnel.md
  (the funnel reference) and docs/brownfield-guide.md (the other adoption
  shape). Greenfield = fast inherit; brownfield = human-led reconcile.
---

# Greenfield guide — landing aidazi into a fresh project

Use this guide when you're starting clean: an empty repo, or an existing codebase that doesn't yet have an agent / workflow / demo. The greenfield path is **fast inherit** — the framework hands you scaffolding + defaults, and you fill in domain-specific values. (If you have an existing project with its own norms or agent work, use `docs/brownfield-guide.md` instead — that path is human-led reconciliation.)

**Mental model**: there is no "Phase 0 normative freeze." The framework *is* the norms. You don't invent governance; you inherit the constitution and spend your energy on the domain.

**Prerequisites to start**: (a) your track designation (Type A / B / C / A+B — use the decision tree in `process/profile-aware-maturity.md` if unsure); (b) a one-paragraph problem statement (BRD-level: problem + KPI + rough scope); (c) a repo path (may be empty).

> **Tip — automate the bootstrap.** `ONBOARDING.md` (the Onboarding Wizard) is an agent-driven, idempotent, non-destructive wrapper that sequences STEP 1-7 below with recommend-then-confirm at each decision. Feed it to your coding agent to run this guide; this doc remains the rationale source-of-truth. The wizard is the one-time install — it is NOT a loop (Constitution §1.7-E).

---

## STEP 1 — Initialize the framework

Vendor the framework into your repo and wire the governance chain.

**Recommended (copy / vendored — no submodule):**

```bash
# From the aidazi framework repo root:
./engine-kit/tools/vendor-framework.sh . /path/to/your-adopter-repo
cp /path/to/your-adopter-repo/aidazi/AGENTS.md /path/to/your-adopter-repo/AGENTS.md
```

This copies the framework into `<adopter>/aidazi/` and writes `aidazi/.aidazi-version`
(source commit + framework version). The adopter owns the copy in its own git history;
upgrade by re-running the vendor script and diffing (see `process/fold-back-protocol.md` §1.2).

**Optional (git submodule — only if you want `git submodule update` to pull releases):**

```bash
git submodule add <aidazi-url> aidazi
cp aidazi/AGENTS.md ./AGENTS.md
```

Edit your root `AGENTS.md` (§1 project identification + §3 ledger paths). It defines the lightweight default Control Plane entry and names the role/on-demand governance chain — the always-load kernel trio `aidazi/governance/constitution-core.md` + `authoring-kernel.md` + `context_briefing.md`, with the full canonical `constitution.md` / `doc_governance.md` loaded on-demand. Set `adopter_track` and `framework_version`.

A working filled-in example of everything STEP 1-6 produces lives at `aidazi/examples/minimal-greenfield/` — copy from it rather than authoring blank. It also ships a recorded, byte-reproducible offline run proving the standalone driver drives a full sub-sprint end-to-end: `examples/minimal-greenfield/docs/recorded-run.md`.

## STEP 2 — Run the elicitation (Δ-15)

Adopt the **Research** role and walk `process/agent-design-elicitation.md` (Δ-15):

- 6 must-answer questions: Domain / Goal / Problems / Method / Knowledge / Boundary.
- 4 inventories per profile (Type A: Knowledge / Tools / Skills / Policy; Type B: K / T / SOP / P; Type C: K / T / Off-shelf-skill / P).
- Tool-vs-Skill decision tree (Type A) — atomic op → tool; multi-step LLM-orchestrated routine → product skill. (Don't confuse the product skill inventory with the team-side **role skills** in `process/role-skill-model.md`.)
- Part D industry research synthesis (Type A) → `docs/discovery/industry-synthesis-<id>.md`.
- Part E: draft the `closure_contract` — the three-component paragraph (positive shape + anti-pattern + anchor phrases) that becomes your first milestone's success definition.

Output: a first research brief at `docs/research-briefs/<id>.md`. The Customer signs it (gate 1).

## STEP 3 — Run the prerequisite gate (Δ-16)

Walk `process/agent-creation-prerequisites.md` (Δ-16): verify the 7 categories of input artifacts at READY / DEFERRED / N/A. Any DEFERRED auto-files an OBS-item tagged `prereq-deferred` in `docs/action_bank.md`. You don't need everything READY to start — you need to know what's deferred and why.

## STEP 4 — Instantiate the framework

- The constitution stays vendored and on-demand (its always-load `constitution-core.md` kernel projects it at cold-start); you never edit it.
- Author your three **domain contracts** from templates (`docs/domain-adaptation.md` walks these): `docs/current/domain_taxonomy.md`, `docs/current/runtime_invariants.md`, `docs/current/eval_acceptance_bars.md`.
- Author the **implementation-stack snapshot** `docs/current/implementation-stack.md` from `templates/implementation-stack-template.md` — a present-tense record of the product's own language / framework / build / test / data deps / deploy-runtime. Greenfield has nothing to detect, so offer a track-informed *starting point* (humble, not a selection) and mark anything undecided `DEFERRED → Phase 3` (does not block). This is the *adopter implementation stack*, distinct from the *agent execution stack* (`charter.tooling.<role>`, STEP 7); it is **not** a domain contract and **not** architecture selection — Phase 3 (STEP 5) owns those decisions. `load_discipline: by-role`.
- Author `docs/current/adoption-state.md` from `templates/adoption-state-template.md` — your per-Δ status + override registry.
- Confirm the first `docs/research-briefs/<id>.md` carries its `closure_contract` and is `customer_signed: true`.

## STEP 5 — Walk the Phase 1-5 funnel (framework-aware)

The funnel turns the signed brief into a buildable plan. **Progressive disclosure** is the governing principle: each phase pulls in *only* the inputs it can use. Technical constraints arrive at Phase 3, not Phase 1. **Reverse-flow** is explicit: when a later phase finds an earlier one infeasible, you backtrack openly (not silently re-decide). Full per-phase reference: `docs/application-funnel.md`.

| Phase | Produces | Pulls in at this phase | Reverse-flow trigger |
|---|---|---|---|
| **1 — Business need & goal** | `docs/foundational/business-need.md`: market need + KPI + scope IN/OUT + anti-goal. Customer signs (gate 1). | Δ-15 Q1-Q3 + Δ-16 #1 (BRD) | source phase — none from above |
| **2 — Product/Service design** | `docs/foundational/product-service-design.md`: UC registry + tool spec (A) / SOP step registry + per-step gates (B) / off-the-shelf skill inventory (C) | Δ-15 Part B+C inventories + Δ-3 decision #1 (abstraction-layer; default single tool-use per §1.7-A) + Δ-16 #2 (PRD) | if Phase 2 can't deliver Phase 1 → revisit scope/KPI |
| **3 — Technical plan** | `docs/foundational/technical-plan.md`: engineering baseline + platform/system APIs + integration + Tier-0 invariants | Δ-6 runtime skeleton + Δ-3 decisions #2-#7 + Δ-16 #3/#6/#7 | if Phase 2 design is technically infeasible → re-design Phase 2 |
| **4 — Coding packet** | `docs/foundational/coding-packet.md`: module breakdown DM1..N + delivery order + mocks + .env | Δ-16 #4 knowledge corpus + #5 canned replies | if budget/scope mismatch → back to Phase 3 or 2 |
| **5 — Eval/Release/Feedback** | `docs/foundational/eval-design.md`: CaseSpec suite + judge rubric + (if Δ-18) charter + calibration set | M-Evaluation 4-component + 6-primitive DSL + Δ-18 charter | if reproducible failure → root-cause may push back to any earlier phase |

**The closure_contract from Phase 1 is the Acceptance verdict source.** Everything downstream is judged against it.

**Phase 3 reconciles the Step-4a implementation-stack snapshot.** Resolve every `DEFERRED → Phase 3` row from `docs/current/implementation-stack.md` in `technical-plan.md` here — Phase 3 is the canonical home for forward technical decisions, while the snapshot only records present facts. As decisions land, promote the snapshot's `DEFERRED` rows to `CONFIRMED`. (The snapshot never duplicates Phase 3; it feeds it the known-today baseline.)

### §5.3.1 Split or merge Phase 1 and Phase 2?

Phase 1 (business need) and Phase 2 (product/service design) can be one document or two. Choose by complexity and stakeholder count:

- **Merge** (one `docs/foundational/business-and-product.md`) when: Type C demos (always); single-author or seed-stage projects; the person defining the need is the person designing the service.
- **Split** (two docs) when: medium+ complexity; multiple stakeholders; the "what customer wants" and "how we satisfy it" decisions have different owners who can disagree.

If you merge and later regret it (stakeholders diverge, the need and the design start contradicting each other), see `docs/friction-playbook.md` F15 — the unwind is to split at the next milestone, not mid-flight.

## STEP 6 — Bootstrap the iteration loop

Adopt the **Deliver** role and stand up the first cycle:

1. Author `docs/milestone_objective.md` (cites the closure_contract as north star) from `templates/milestone-objective.md`.
2. Author the first `docs/sprint_objective.md` from `templates/sprint-objective.md`.
3. Author `compact/sprint-001-dev-prompt.md` from `templates/compact-dev-prompt.md` (self-contained; `context_budget` + `self_contained: true`).
4. Run the first **Dev → Code Reviewer → close** cycle. Dev writes `handoff.md` §1-§11; Deliver + Customer write §12 close verdict.
5. Bootstrap `docs/action_bank.md` with backlog placeholders and `handoff.md` §0 with the cold-start table.

**Acceptance in the first milestone close**: at the end of your first milestone, run the **Acceptance** role (Customer paste at gate 2). It reads the closure_contract + the dev evidence and returns `pass` / `fix_required` / `needs_human`. This is the moment the framework's central discipline earns its keep — you find out whether you built the right thing, not just whether the code is clean. On `fix_required`, the human-confirm checkpoint fires before any fix routes back to Deliver (`governance/constitution.md` §3.5).

## STEP 7 — (Optional) Bootstrap the orchestrator (Δ-18 Delivery Loop)

If you want automation beyond human-paste handoffs, stand up the Delivery Loop orchestrator:

1. Author `charter.yaml` from `templates/mission-charter.yaml` — set `autonomy.level`, `approved_scope`, each role's execution facet under `tooling.*` (`harness`/`provider`/`model`, or legacy `agent_kind`), budget.
2. If Acceptance will run autonomously, author the calibration set (`calibration/labeled_acceptance_cases/manifest.json`) and run the §3.6 calibration gate. Until calibrated, `fully_autonomous_within_budget` auto-degrades to `human_on_the_loop`.
3. **Validate before running**: `python engine-kit/validators/charter_validator.py charter.yaml` must exit 0 — structurally valid + no semantic errors (the no-bypass checkpoint rules, `human_confirm_required`, and the Facet-A/B/C capability / skill-integrity / connector-default-deny gates). Warnings are allowed; errors block — fix and re-run.
4. Run the standalone driver — `engine-kit/orchestrator/driver.py` (run recipe: `engine-kit/orchestrator/README.md`; end-to-end demo on the worked example: `engine-kit/orchestrator/demo.py`). For unattended runs, schedule it via plain cron/CI with `engine-kit/scheduling/run_loop.py` (`engine-kit/scheduling/README.md`) — not a harness scheduler.
5. (Optional) Run in **`full_chain_guided`** mode (`autonomy.loop_mode: full_chain_guided`) to let the loop bootstrap a milestone end-to-end: Research draft → Customer Gate-1 sign-off (human-confirmed, never auto-confirmed) → milestone decomposition → the delivery loop. The default (`delivery_only`) runs the delivery loop only.

Full spec: `process/delivery-loop.md` (§4.2.4 for the `full_chain_guided` pre-states). Pure human-paste adopters skip STEP 7 entirely and keep the 5-role chain with the human as orchestrator — that's a complete, valid adoption.

---

## Cross-reference: detours to watch

Each phase has a known cognitive detour (`process/common-detours-and-warnings-typeA.md`, Δ-17):

- Phase 1 prerequisites ↔ P1 *spec-first / data-late* detour (don't finalize UC taxonomy before you've looked at real transcripts).
- Phase 5 eval bootstrap ↔ P2 *eval-before-architecture-stable* detour.
- Phase 5 + orchestrator ↔ P3 *autoloop-as-eval-stress-test* detour.
- Phase 3 + first milestone ↔ P4 *mid-milestone-pivot* detour.

And before your first milestone, read `docs/friction-playbook.md` end to end. It's the cheapest insurance in the framework.

## Structural payoff

A from-scratch project with no framework can spend weeks inventing Phase 0-5 norms. A greenfield adopter inheriting v4 should compress Phase 1-2 to under a week — the schemas, decision catalogs, and role boundaries are pre-loaded; only the domain-specific values need filling.

---

End of greenfield guide.
