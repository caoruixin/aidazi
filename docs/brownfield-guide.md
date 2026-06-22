---
title: Brownfield guide — adopting aidazi into an existing project
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
size_target: 20KB
split_trigger: if the §3 decide table grows past 6KB, move per-area detail to a process/ doc and keep the recommendation column here
notes: >
  Brownfield adoption path — for an existing project that already has
  agent/workflow/demo work, possibly with its own norms. Human-led: the
  framework provides a checklist + decision tree + the three adoption
  profiles (full / core / selective), NOT automation. INVENTORY → DECIDE →
  RECONCILE → VALIDATE. Companion to docs/greenfield-guide.md (fast inherit)
  and docs/adoption-overview.md. The high-value, low-risk first move is
  adding the Acceptance gate.
---

# Brownfield guide — adopting aidazi into an existing project

Use this guide when you already have a project — an agent, a workflow, or a demo — possibly with its own governance, its own backlog format, its own eval setup. Brownfield projects vary too much to automate, so this is a **human-led** path: the framework gives you a checklist, a decision tree, and three adoption profiles. You decide what to inherit, what to preserve, and what to reconcile.

The guiding rule: **don't rip and replace.** Adopt incrementally, document every divergence, and let the high-value pieces prove themselves before you take more.

---

## §1 Choose an adoption profile

You do not have to take all of aidazi at once. Three profiles, from heaviest to lightest:

| Profile | What you take | Good fit when |
|---|---|---|
| **A — Full** | All 5 roles + the Δ-18 Delivery Loop orchestrator + all Δs + the three domain contracts | New team forming around the project; you want the full discipline and can invest in it |
| **B — Core** | All 5 roles, human-paste (no orchestrator); the core Δs (constitution, role cards, bad-case lifecycle, milestone framework); the three domain contracts | Established small team; want the role discipline without automation overhead |
| **C — Selective** | Cherry-pick high-value pieces: the anti-hardcode review kernel + the sprint stanza + the bad-case lifecycle + the Acceptance gate. Skip the rest. | Mature project with its own working process; you want specific frameworks-shaped wins, not a process transplant |

Most brownfield projects should **start at C or B and graduate**, not start at A. The framework is overhead-amortizing, not free; the break-even is usually around your second milestone (see `docs/friction-playbook.md` F12). Record your chosen profile in `docs/current/adoption-state.md`.

## §2 INVENTORY (read-only — change nothing yet)

Before deciding anything, take stock. Do **not** edit anything in this phase.

```
□ What's the current track? (Type A AI agent / Type B workflow / Type C demo / A+B hybrid)
  — use the profile decision tree in process/profile-aware-maturity.md (Δ-14) if unsure
□ Does the project already have governance docs? (AGENTS.md, CLAUDE.md, role/agent docs?)
□ Does it have an action-bank or backlog ledger? In what format?
□ Does it have an eval framework? What CaseSpec shape?
□ What's the current implementation stack? — language / framework / build + package manager / test / data deps / deploy-runtime.
  Detect read-only from manifests + config (pyproject.toml, package.json, go.mod, lockfiles, Dockerfile, etc.); record names only, never a secret/env value. Don't over-infer production architecture from one file. (Captured in §4 as docs/current/implementation-stack.md; ONBOARDING Step 4a automates it.)
□ Does it use any orchestrator/automation currently?
□ What's the current human/agent split? Pure human-paste, or some automation?
□ Where do semantic decisions currently live — LLM-owned, or hardcoded? (this predicts §1.7 friction)
```

The honest answer to the last question is the most important: brownfield projects most often diverge from the framework on the LLM-vs-runtime boundary (keyword/regex shortcuts that the constitution §1.7 forbids). Note these now; you'll reconcile them deliberately, not in a panic mid-sprint.

## §3 DECIDE (per area — you judge the tradeoffs)

For each area, choose REPLACE / KEEP / MERGE. The framework gives a recommendation; you own the call.

| Area | Options | Recommendation |
|---|---|---|
| **Constitution** | REPLACE with framework / KEEP existing / MERGE | **REPLACE** unless you have explicit documented deviation reasons. The constitution is the part that makes your project recognisable as an aidazi project. |
| **Role definitions** | ADOPT 5-role chain / KEEP existing (e.g., 4-role) / add Acceptance only | **ADOPT the 5-role chain.** If you take only one thing, take the **Acceptance gate** — it's the highest-value, lowest-disruption add (§5). |
| **Action bank / backlog** | MIGRATE to framework taxonomy / KEEP existing format | **KEEP your format** but add the Δ-12 sweep cadence + live/archive split. Reformatting a working backlog is pure cost. |
| **Eval** | ADOPT M-Evaluation template / KEEP existing | **KEEP if mature**; add an adaptor to the framework's CaseSpec shape (`schemas/case-spec.schema.json`) for portability. Adopt the bad-case lifecycle (`process/badcase-lifecycle.md`) regardless — it's high value. |
| **Δ-18 orchestrator** | ADOPT / OPT OUT | **OPT OUT** unless you have multi-sub-sprint cycles worth automating. Profile B/C stays human-paste. |
| **Backing agents / role skills** | per role | Configure each role's execution facet under `charter.tooling.<role>` (`harness`/`provider`/`model`, or legacy `agent_kind`) to whatever you already use; bind existing subagent/skill libraries as role skills (Facet B). See the three-facet Role Configuration Contract (`process/role-configuration-contract.md`; `docs/industry-mapping.md` for the translation). |
| **Connectors (tools / MCP)** | default-deny | Nothing is auto-granted. The propose-only discovery scan (`engine-kit/connectors/discovery.py`) is **read-only** — no network, no secret reads — and only *suggests* candidates you approve by hand into `charter.tooling.<role>.connectors[]` (Facet C). |

## §4 RECONCILE (write it down)

Now you author the reconciliation artifact — this is the brownfield-specific deliverable.

1. **Author `docs/current/adoption-state.md`** from `templates/adoption-state-template.md`. For each Δ-1..Δ-18, set a status: `at-spec` / `partial` / `divergent` / `not-applicable` / `superseded-by-framework`. For each `divergent` row, one sentence of rationale.
2. **Map existing docs to the framework schema**; rename where it's cheap, leave where it's costly (and record the divergence).
3. **Add @-includes** to your root `AGENTS.md` for the inherited governance chain.
4. **Author `docs/research-briefs/`** as a new directory if you're enabling Acceptance (you need a closure_contract to judge against — see §5).
5. **Document brownfield carve-outs** as `status: divergent` rows. A carve-out is not a failure; it's an honest record. The one thing you may NOT carve out is the §1.7 forbidden list (`governance/constitution.md` §1.8 — hard requirement, never `divergent`).
6. **Author `docs/current/implementation-stack.md`** from `templates/implementation-stack-template.md` using the §2 read-only detection — present facts only, `CONFIRMED | DEFERRED | N/A` per item, the evidence file cited, names-not-values; `DEFERRED` rows point to Phase 3. **Detected values are recommendations, not conclusions: the human confirms or corrects each row before the snapshot is finalized** (recommend-then-confirm; don't over-infer production architecture from one file). This is the *adopter implementation stack* (the product's tech facts), distinct from the *agent execution stack* (`charter.tooling.<role>`) and from the domain contracts. `load_discipline: by-role`. (ONBOARDING Step 4a automates it.)

The `adoption-state.md` is your living contract with the framework. At each milestone close you revisit it; at framework fold-back, your accumulated divergences become evidence (`process/fold-back-protocol.md`).

## §5 The Acceptance gate — the high-value first move

If you adopt nothing else, adopt the Acceptance gate. Here's why it's the best brownfield entry point:

- It's **additive** — it doesn't change how your team currently builds; it adds an independent check at milestone close.
- It surfaces the gap most brownfield projects can't see: "the code is clean and the tests pass, but did we actually build what the customer needed?"
- It needs only two new things: a `closure_contract` (write one for your current milestone retroactively — Research role, `templates/compact-research-brief.md`) and an Acceptance run at close (Customer paste, `role-cards/acceptance-agent.md`).

To add just Acceptance:

1. Write a closure_contract for your current milestone's goal (three components: positive shape + anti-pattern + anchor phrases).
2. At milestone close, spawn Acceptance from a clean session (Customer paste — never from your Deliver/Dev session; §1.7-C spawn isolation).
3. Read the verdict. On `fix_required`, the human-confirm checkpoint decides routing (§3.5).

Once the team feels the value of the outcome gate, graduating to Profile B (full 5-role chain) is an easy sell.

## §6 VALIDATE

Confirm the adoption actually holds before declaring it done:

```
□ If you generated a charter.yaml (Profile A/B), run
  `python engine-kit/validators/charter_validator.py charter.yaml` — it must exit 0
  (errors block; warnings allowed) before the adoption is done.
□ Run one sprint under the new role chain (or your chosen subset).
□ Confirm the 5-role boundary invariants hold (§3.4) — no role collapsed into another;
  in particular, Acceptance was spawned cleanly (not from Deliver/Dev).
□ Run one Acceptance pass with a closure_contract from any matured research brief.
□ Update adoption-state.md based on what you observed — promote partial→at-spec where
  it landed, add divergent rows where reality differed from intent.
```

## §7 Gradual 5-role adoption

You can phase in roles rather than adopting all five at once. A common ramp:

1. **Code Reviewer** first (if you don't already have an independent review) — mount the anti-hardcode kernel (`skills/anti-hardcode-review-kernel/`).
2. **Acceptance** next (§5) — the outcome gate.
3. **Research** — formalize "what should we build" into signed briefs with closure_contracts.
4. **Deliver** as Tech Lead — once you have briefs to plan from.
5. **Dev** discipline (self-contained compact prompts) — last, because it's the biggest change to day-to-day coding.

Each step is recorded in `adoption-state.md`. The framework provides the menu; you choose the order.

---

The brownfield guide is intentionally less prescriptive than the greenfield guide. Human owners decide; the framework provides the menu and the recommendations. When something doesn't fit your context, that's a `divergent` row and a candidate lesson — not a failure.

---

End of brownfield guide.
