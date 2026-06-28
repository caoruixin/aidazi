---
name: 2026-06-29-four-area-optimization-plan
doc_category: intermediate
status: codex-approved-with-nits-incorporated (design settled; ready to implement 3→4→2→1)
created: 2026-06-29
base_commit: 312baf4 (main HEAD; this plan file is untracked/uncommitted)
reviewer: codex gpt-5.5 xhigh — R1 REVISE (3B+5NB+5F) → R2 REVISE (3B+3NB+2F) → R3 APPROVE-WITH-NITS (0 blocking, 3NB+1F); ALL incorporated 2026-06-29
user_decisions_locked_2026-06-29:
  - sequencing = 3 → 4 → 2 → 1
  - track2 = visible GAP report driving autonomy-gated Acceptance→Deliver follow-up (NOT a hard ship-gate)
  - track4 = make human_on_the_loop the template DEFAULT (auto_fix on)
  - constraint = PRESERVE the loop-engine-v4 (WP-0→WP-9) context/token optimization; gate every track on context_budget_report.py
open_decision_surfaced_by_r2:
  - track2 P2.0 requires a NEW doctrine amendment (pre-authorized in-envelope adaptive-insert) needing its own Codex+human sign-off before implementation
---

# Four-Area Optimization Plan — aidazi framework

> **Codex R1 (236K tok): REVISE** — 3 blocking + 5 nits + 5 factual, all folded in (tagged `Codex
> B-#/NB-#/factual #`). **Codex R2 (199K tok): REVISE** — 3 blocking (all on the gap-driven
> follow-up loop: it bypassed acceptance authority, was under-bounded, and mutated signed scope) +
> 3 nits + 2 factual, all folded into Track 2 P2.0 and Track 4 P4.1.
> **User decisions (locked 2026-06-29):** order **3→4→2→1**; Track 2 = visible GAP report driving
> autonomy-gated follow-up (now hardened to a **pre-authorized, in-envelope, bounded
> adaptive-insert**); Track 4 = flip template default to `human_on_the_loop`; **preserve the
> loop-engine-v4 optimization** (cross-cutting invariant #1).
> **Key open decision (surfaced by R2):** Track 2 P2.0's auto follow-up needs a **Constitution /
> `delivery-loop.md` authority amendment** — naming a pre-authorized deterministic in-envelope
> adaptive-insert. That amendment carries its OWN Codex+human sign-off; it is NOT assumed authorized.
> **Codex R3 (final, 221K tok): APPROVE-WITH-NITS — 0 blocking.** R2 fixes hold (in-envelope
> discriminator + bounds + doctrine-amendment framing all sound, conditional on the F1 snapshot
> being immutable and the amendment landing). Preservation judged "partly sound": the real catch is
> that WP-9's budget lint as-is measures only static, skills-OFF cold-start — so it would NOT catch
> Track-1 skill-body growth or Track-2 run-dynamic acceptance artifacts unless each track EXTENDS
> the measurement (now folded into cross-cutting invariant #1 point 5). 3 nits + 1 factual all
> incorporated. **Design is settled; ready to implement in order 3→4→2→1.**

Scope: four user-requested optimization tracks, scoped against the **current `main`**
(post WP-0→WP-9). This is a **plan for review**, design-only; no code changed. Each track
states: current state (evidence), the gap vs the goal, a phased proposal, the files that
change, the invariants it must not break, and the decisions that need the user.

**Cross-cutting invariants every track must respect (non-negotiable):**
- **PRESERVE the `loop-engine-v4` context/token optimization (WP-0→WP-9) — user-mandated
  2026-06-29.** The just-merged optimization (tag `loop-engine-v4`, commit `312baf4`) cut the
  cold-start governance floor ~36% and acceptance read ~48% via kernels (`constitution-core.md`,
  `acceptance-kernel.md`, `authoring-kernel.md`), compact schema projections (`schemas/compact/`,
  `project_schema.py`), task-scoped cold-start loading (WP-5A), bounded lessons
  (`lesson_selection.py`, WP-6), per-role load fingerprint (WP-7), and the WP-9 advisory budget
  lint. **No track may silently regress these.** Concretely:
  1. **WP-9 budget lint is the regression guardrail** — every track runs
     `engine-kit/validators/context_budget_report.py` against the checked-in baseline; any
     cold-start/acceptance growth is surfaced. Net increases are allowed ONLY via an explicit
     rebaseline **or** waiver with written justification (WP-9 doctrine: drift cleared by
     rebaseline/waiver, never silent, never a forced shrink). *(Codex R3 NB-1: gate CI with
     `context_budget_report.py --strict` — default drift output is advisory-only; `--strict` is
     what actually FAILS on unwaived growth, `context_budget_report.py:29`.)*
  2. **No new ALWAYS-LOAD content.** New cold-start docs/schemas ride the established patterns:
     kernel + on-demand projection of the full doc, and **compact** schema projections
     (`project_schema.py` → `schemas/compact/*.compact.schema.json`) for anything an agent loads
     at cold-start. Constraint-carrying docs must be added to the kernel inventory and PROVEN
     covered (`kernel_equivalence.py` / `_kernel_coverage.yaml`); any touched canonical source is
     re-pinned in `_sources.yaml` (else the equivalence gate fails — by design).
  3. **Variable / large data goes through a RUNTIME channel, not the static floor** — exactly as
     WP-6 lessons and WP-5A task-scoped loading do. Track 1 skill bodies mount **task-scoped**
     (keep `role-skill-model.md` conditional on `bool(effective.skills)`), and Track 2's gap
     report / requirement ledger / functional checklist are bound per-milestone at runtime
     (resolver-bound like the existing checklist/evidence inputs, `driver.py:4059,4103`), kept
     out of the always-load cold-start set wherever the LOAD-CLOSURE allows.
  5. **EXTEND the measurement so preservation is actually checked, not assumed (Codex R3 NB-2/NB-3
     — this is a coverage hole today).** WP-9's lint currently measures only *framework-static*
     cold-start and its tracked role rows are **skills-OFF** (`context_budget_report.py:110`). So
     as-is it would NOT catch (a) Track-1 task-selected **skill-body** growth, nor (b) Track-2's
     **run-dynamic acceptance artifacts** (ledger/checklist/gap report). Each track must therefore
     ALSO add its own coverage: Track 1 adds **skill-active / task-skill budget rows** (or a
     separate skill-body budget check); Track 2 adds a **runtime size cap + report** for the
     per-milestone acceptance artifacts (`load_sizer.py:189`). Resolving the LOAD-CLOSURE↔
     always-load tension = bind/hash these inputs for verdict reproducibility WITHOUT adding them
     to `ROLE_COLD_START`; the new runtime cap is what keeps them from silently bloating.
  4. **Kernel/coverage/hash gates stay green** — `kernel_equivalence.py` (65/65 + acceptance +
     authoring), `acceptance_load_closure.py` (closed:true), and `acceptance_input_hash`
     reproducibility are part of every track's done-definition, not an afterthought.
- **LOAD-CLOSURE / `acceptance_input_hash`** — no verdict-affecting input may be unbound; any
  new acceptance input must be embedded in the projected prompt or bound in the acceptance
  resolver graph and folded into the hash (`driver.py:4224-4241`).
- **Determinism / cold-start fingerprint** — selection that varies a role's loaded set must
  key on a *signed, config-derivable* signal, never on free-text prompt inference (would make
  `cold_start_load_graph_hash` / `acceptance_input_hash` non-reproducible).
- **§1.7-D non-bypass checkpoints** — all 9 MANDATORY_CHECKPOINTS stay present at every
  autonomy level; the charter validator rejects omit/empty/disable/override.
- **No runtime supply-chain fetch** — skills/docs are vendored + pinned author-time; nothing
  downloads at loop time (Constitution Δ-C4).
- **Doc-governance** — retire = archive (`git mv` → `archive/`) + `superseded_by`, not silent
  delete; anything in `engine-kit/tools/constraint-inventory/_sources.yaml` (sha-pinned) or the
  `vendor-framework.sh` INCLUDE set is load-bearing.

---

## Track 1 — Task-aware dynamic skill mounting per role

**Goal (user):** each role mounts the skills its *specific task* needs (e.g. detect UI work →
mount UI-design / frontend skills); if the framework doesn't contain a needed skill, **skip**
loading it — never download at runtime.

**Current state (evidence).** Skills are bound **statically, per role, at config time**, then
content-hashed and injected into every spawn of that role identically
(`engine-kit/effective_role_config.py` `resolve_role_config`/`skill_prompt_block`;
`driver.py:_effective_role` cache keyed by role only, `:687,1071-1085`; injected at
`_spawn` `:935-936`). Source of truth is `skills/registry.yaml` `role_defaults` +
charter `tooling.<role>.skills` override (modes inherit/extend/replace/disable). **No network
or runtime fetch exists** (`effective_role_config.py:8-9`) — the "no download" half of the goal
is *already satisfied*.

**Gaps vs goal.**
1. **No task-awareness in skill mounting** — grep for `frontend|ui|task-aware|infer-skill` →
   zero. Skills never vary by milestone/sub-sprint/task content; a UI sub-sprint and a backend
   sub-sprint of the same Dev role get byte-identical skill mounts. (Note, per Codex: cold-start
   *document loading* IS already task-scoped for Deliver-close via WP-5A — `load_sizer.py:150-167`,
   `cold_start_load_graph_hash` `:276-305` — so the mechanism precedent exists; it just doesn't
   extend to skill selection. "No task-awareness at all" would be too broad.)
2. **Missing-skill behavior is the OPPOSITE of the goal** — a bound-but-absent skill is a
   **hard fail** today (`_resolve_skill` raises → `gate_hard_fail`, `driver.py:1081-1084`).
   The user wants *skip + audit*.
3. **No UI/frontend skills exist** — the 7 vendored skills are all generic (brainstorming,
   writing-plans, ADR, TDD, code-review, advanced-evaluation, git-worktrees). The motivating
   example cannot be satisfied until such skills are vendored.

**Proposed phases.**
- **P1.0 — Vendor the skills + tag them (author-time, data-only, zero behavior change).**
  Vendor real UI/frontend skills under `skills/vendored/`, register in `registry.yaml` +
  `skills.lock` + `_provenance.yaml`. Add an optional `signals: [ui, frontend, css, a11y, …]`
  field to `schemas/skill-catalog.schema.json` so each skill self-declares the task signals it
  serves. **Prerequisite for everything else.**
- **P1.1 — Skip-if-absent as an opt-in resolution mode.** Add per-binding `optional: true`
  (schema `skill-binding.schema.json` / charter `skills_config`). For optional bindings,
  `_resolve_skill` returns `None` + a structured skip-reason instead of raising;
  `resolve_role_config` collects `skipped_skills[]`; driver emits them in the
  `effective_role_config` audit event + a non-silent footer in `skill_prompt_block`. **Keep the
  existing hard-fail default for required bindings** (don't mask misconfig for current adopters).
  *(Codex NB-1: the `optional` field must be added to BOTH the verbose `skill-binding.schema.json:7-45`
  AND the compact mirror in `mission-charter.schema.json:449-490` — both are `additionalProperties:false`
  today, so a new field is rejected until added to both.)*
- **P1.2 — Task-signal → candidate-skill selection (deterministic).** Add an explicit
  `task_signals: [ui, …]` field to the milestone/sub-sprint object that Deliver sets at
  decompose/sign-off time (human-signed, reproducible — **not** LLM-inferred from the prompt).
  A new `select_skills_for_task(role, task_signals, catalog)` maps signals → candidate skill
  ids via P1.0 tags, intersects with **present-and-locked** skills, and feeds the survivors as
  *optional extend* bindings on the role defaults; absent candidates drop via the P1.1 skip path
  with an audit note.
- **P1.3 — Hash / LOAD-CLOSURE integration.** Re-key `_effective_role_cache` from `role` to
  `(role, task_kind/sub-sprint)`; surface the resolved (post-skip) skill-set identity in a
  spawn/audit field. *(Codex NB-2: do NOT silently overload `load_graph_hash` — it is documented
  as cold-start governance/kernel-only, `audit-event.schema.json:68`. Decide explicitly: either
  extend its semantics — and re-document — or give the per-task skill-set its own audit field.)*
  **Exclude Acceptance from
  task-aware selection** — `effective_skill_set_hash` is already in the acceptance
  `authority_fingerprint` (`driver.py:4237-4238`), so per-task acceptance skills would thrash
  §3.6 calibration/verdict-reuse. Restrict task-aware mounting to Dev/Deliver/Research/Reviewer.

**Files touched:** `skills/registry.yaml` + `skills.lock` + `skills/vendored/*`;
`schemas/skill-catalog.schema.json` (+`signals`), `schemas/skill-binding.schema.json` /
`mission-charter.schema.json` (+`optional`); `engine-kit/effective_role_config.py`;
`engine-kit/orchestrator/driver.py` (cache key, audit, selection call); `load_sizer.py`
(fold skill-set into WP-7 hash); `engine-kit/scheduling/*`/`campaign.py` (carry `task_signals`);
`engine-kit/validators/charter_validator.py`; docs `process/role-skill-model.md`,
`process/role-configuration-contract.md`.

**Risks:** determinism (mitigated by signed `task_signals`, never prompt inference); acceptance
calibration thrash (mitigated by excluding the judge); tool-whitelist transitivity (a UI skill
needing Bash/Write can't mount on a read-only role — already enforced by charter_validator);
cold-start re-inflation vs the WP-9 budget guardrail (measure).

**Decisions needed:** (a) signal source = signed `task_signals` on the milestone (recommended)
vs prompt inference? (b) who authors the signal — Deliver at decompose, or human in the intent
contract? (c) skip-if-absent only for new optional skills, or also relax the hard-fail on
charter-declared required skills? (d) confirm Acceptance is excluded. (e) **which UI/frontend
skills to vendor, from which pinned upstreams** — this is the gating prerequisite.

---

## Track 2 — Make Acceptance a real end-to-end, user-perspective gate vs ORIGINAL requirements

**Goal (user):** Acceptance must stand in the **end-user's shoes** and verify the delivered
functionality against the **originally-agreed requirements** — confirming the feature set is
**complete and correct** vs what was first asked. Not unit tests; genuine end-to-end functional
verification.

**Current state (evidence).** Acceptance is framed "customer-perspective" and forbids
code-inspection-only verdicts (must cite execution evidence under `eval/runs/`,
`driver.py:3731,3748-3755`). But:
- It binds to a **single `closure_contract` triple** (`{positive_shape, anti_pattern,
  anchor_phrases}`) and the intent triple — **not** the research-brief `scope_in[]/kpi[]`, the
  charter scope, or any requirement map. The kernel **forbids widening** ("no criteria-creep",
  `acceptance-kernel.md:151-153`). So by construction it checks *one signed clause*, not
  "every originally-asked feature was delivered and works."
- The **default (static/M1)** path's rigor = the adopter's own `eval.cmd` — which the framework
  neither defines nor inspects (could be unit tests).
- **Browser-E2E (M3)** is genuine user-facing E2E, but it is **opt-in** and **always advisory**
  in v1 (`driver.py:3069-3077`); it never blocks a ship.
- `scope_report.py` (PRD-ish coverage) is **read-only, milestone-granular, and disconnected**
  from the verdict — printed at campaign end, gates nothing.
- The **Requirement Ledger** that would close the completeness gap is **design-only, approved,
  not implemented** (`archive/2026-06-23-requirement-ledger-design.md`).

**Gap:** completeness-vs-original-requirements is *not a gate* (it's at best an end-of-run
report); end-user framing is shallow on the default path; "real E2E not unit tests" holds only
on the opt-in, advisory M3 path.

**DECISION (user, locked 2026-06-29) — "visible GAP report that DRIVES follow-up", NOT a hard
ship-block.** The completeness check is realized as a **GAP report** Acceptance emits each
milestone close (delivered-feature-set vs the signed original requirements). It does **not**
`gate_hard_fail` a ship. Instead the gap report is a **work-driver**, and *who acts on it is
governed by `autonomy.level`* — this is the bridge that couples Track 2 to Track 4:
- **`human_on_the_loop` (the new default, Track 4):** Acceptance attaches the gap report to the
  verdict; **Deliver AUTOMATICALLY initiates a follow-up sub-sprint** from the gap
  (remediation / upgrade / fix) and the loop continues — **no pause**. The milestone keeps
  closing the gap autonomously until the gap report is empty (bounded by budget / max-rounds).
- **`human_in_the_loop`:** the gap report routes to `needs_human` review. On human **confirm**,
  Deliver initiates the follow-up sub-sprint from the gap; if the human instead **adjusts** scope
  (edits the requirement set / defers items), Deliver waits and then schedules follow-up against
  the *adjusted* requirements.

Implication: this needs a new, autonomy-aware **Acceptance→Deliver gap-driven re-decompose path**
(gap artifact → Deliver re-decompose trigger → new sub-sprint appended to the milestone sequence),
NOT just a verdict coercion. The Requirement Ledger + signed scope-envelope (F1) + functional
checklist machinery below still must be built to PRODUCE an accurate gap report; what changes vs
the original draft is the *consumption* — drive bounded follow-up sub-sprints (autonomy-gated)
instead of halting the ship.

> **Codex R2 caught three real blockers here; the design below is the hardened resolution.**
> The naïve "auto-route work with no pause" would *bypass the acceptance authority model*
> (advisory/`fix_required`/`needs_human` verdicts cannot route work without human authority —
> `constitution.md:179,185`; enforced at `driver.py:4420,4451`), is *under-bounded* (today
> `max_rounds` bounds only Dev↔Review; campaign budget is optional⇒unbounded, `campaign.py:643`),
> and would *mutate signed scope* (sequence is revisable mid-run only via `scope_deviation`,
> `delivery-loop.md:229`). The resolution is a **pre-authorized, in-envelope, bounded
> adaptive-insert** — not a bypass.

**Proposed phases.**
- **P2.0 — Gap-report data model + a PRE-AUTHORIZED, in-envelope, bounded follow-up path (the
  spine of this track; resolves Codex R2 B-1/B-2/B-3).**
  - **Separate channel from quality `fix_required`.** P2.0 handles only the **completeness-gap**
    channel (signed-but-undelivered `req_id`s). The existing acceptance `fix_required` /
    `needs_human` verdicts keep their current human-authority semantics **unchanged**
    (`driver.py:4420,4451`) — we do NOT touch them. This alone removes most of B-1's conflict.
  - **In-envelope proof = the discriminator (resolves B-1 & B-3).** A gap-follow-up sub-sprint is
    auto-dispatchable ONLY if it is *provably within the F1 signed requirement envelope*: every
    `req_id` it targets ∈ the signed resolved-scope snapshot AND was already in the signed
    `covers_req_ids` (i.e. it is scope **completion**, not **expansion**). Closing already-signed,
    undelivered scope is what the human pre-authorized by signing the envelope + choosing
    `human_on_the_loop`. If the generated remediation would pull in any `req_id` ∉ the signed
    snapshot → it must **HALT for a human even in `human_on_the_loop`**. *(Codex R3 factual-1: the
    correct fail-closed boundary at decompose time is the **scope-EXPANSION guard** that writes
    `post_gate1_scope_expansion` — `driver.py:2275,2330` — NOT the close-path `scope_deviation`
    checkpoint at `driver.py:2983`; the original draft conflated the two. P2.0's out-of-envelope
    insert is caught at re-decompose by the expansion guard.)* The envelope-membership check is
    deterministic.
  - **This is a NEW authority path and needs an explicit doctrine amendment (flagged).** Naming a
    "pre-authorized deterministic in-envelope adaptive-insert" that does not require a fresh
    human-confirm checkpoint is a change to the Constitution/`delivery-loop.md` authority model.
    It must be written as an explicit, validator-checkable rule (with the four §1.7-D evasion
    shapes still rejected) and carry its OWN Codex+human sign-off before implementation. Do NOT
    treat it as already-authorized.
  - **Concrete persisted bounds (resolves B-2).** Per milestone, persist and enforce: (i)
    `gap_followup.max_subsprints` hard cap (default small, e.g. 3); (ii) **no-progress detection
    keyed by the stable `req_id` gap-set hash** — if the same unclosed `req_id` set survives K
    rounds (default 2), halt+escalate (a shrinking gap-set is "progress"; an unchanged one is
    not); (iii) **mandatory campaign-budget integration** — absent budget ⇒ a conservative default
    cap, **never unbounded** (fixes `campaign.py:643`); (iv) on any bound exceeded, a deterministic
    **halt → `needs_human` escalation**, never a silent stop or an infinite loop. Make
    adaptive-insert refusal *enforced*, not just documented (cf. `05-delivery-loop.yaml:77`).
  - **human_in_the_loop path + the confirm/adjust schema gap (NB-2).** Route the gap report to
    `needs_human`. The current decision schema is choice-based (`approve_ship`,
    `route_to_deliver_fix`, `abort` — `campaign-decision.schema.json:38`, `campaign.py:189`); it
    has no "adjust requirements" shape. So either (a) add an `adjust_scope` decision that triggers
    a human plan-edit + envelope **re-signoff** before any follow-up, or (b) model "adjust" as an
    explicit plan edit through the normal `campaign_plan_signoff` re-sign. Pick (a) for ergonomics.
  - **LOAD-CLOSURE (NB-1).** Bind into `_acceptance_resolver_graph` + `acceptance_input_hash` not
    just the requirement ledger but ALL artifacts the `gap_report` is computed from
    (delivered-status / coverage), since the gap report is verdict-affecting (`driver.py:4038`).
  - **Reuse, don't reinvent, the fail-closed machinery.** The auto-insert rides the existing
    campaign classify/resume + scope-expansion HALT; it never invents a new way to bypass a
    checkpoint.
- **P2.1 — Implement the approved Requirement Ledger + wire a completeness gate (highest
  leverage).** Add `covers_req_ids[]` to `campaign-plan.schema.json` + the signed resolved-scope
  snapshot (design's F1) into `campaign_plan_signoff`; extend `scope_report.py` to
  requirement-granular (REQ→milestone→delivery_status). **Wire it into milestone-close
  Acceptance to PRODUCE the P2.0 gap report:** unmapped/undelivered REQs become the gap report's
  payload. Per the locked decision this **does not `gate_hard_fail`**; it feeds the autonomy-aware
  follow-up loop (P2.0). (The existing `check_acceptance_consistency` coercion at
  `driver.py:4316-4334` is the structural precedent for attaching a derived signal to the verdict —
  reuse that wiring style, but route to gap-driven follow-up, not a hard halt.)
  - **BLOCKING (Codex B-2): the signed scope-envelope / stale-signoff enforcement (design F1) is a
    PREREQUISITE, not a nice-to-have.** Today `campaign_plan_signoff` is merely
    `signed_by_human: true` (`campaign-plan.schema.json:13`, `campaign-loop.md:158-165`) — the plan
    is *editable after signoff*, which the approved design itself flags as unsafe
    (`archive/2026-06-23-requirement-ledger-design.md:80-91, 159-169, 347-386`). `covers_req_ids[]`
    cannot be treated as signed truth until the signed-snapshot + staleness check lands first.
    Implement F1 BEFORE the coverage gate consumes the ledger.
  - **BLOCKING (Codex NB-3): the new ledger/coverage input MUST be added to
    `_acceptance_resolver_graph` (`driver.py:4038-4165`) and the load-closure manifest, then folded
    into `acceptance_input_hash`** — the resolver binds NO requirement ledger today, so without this
    the new verdict input is unbound = a LOAD-CLOSURE violation.
- **P2.2 — Generalize the functional checklist to the static path (requires NEW machinery —
  correction).** Today `functional-checklist.schema.json` (enumerated, Research-signed,
  user-observable criteria) is consumed only by M3, and **set-equality coverage is enforced on the
  final verdict only for browser-E2E** (`e2e_stage.py:226-283`, routed `driver.py:4316-4333`).
  - **CORRECTION (Codex B-1 + factual #2/#3): the original draft's "no new machinery" was WRONG.**
    `driver.py:3332-3346` checks the *agentic execution plan's* coverage, **not** the final
    Acceptance verdict; and the **static** acceptance-verdict schema does not require `criterion_id`
    at all (`acceptance-verdict.schema.json:116-149`) — only the browser path does. So extending
    enumerated-criteria coverage to the static path genuinely needs: **(i)** a static checklist
    *source* artifact (Research-signed), **(ii)** `acceptance-verdict.schema.json` changes to carry
    per-criterion coverage on static verdicts, **(iii)** binding that checklist into the acceptance
    resolver graph + `acceptance_input_hash`, and **(iv)** a static consistency/coercion gate
    (mirroring the browser path's `e2e_stage.py:226-283` + `driver.py:4316-4333`). Scope P2.2 as
    real schema+gate work, not a framing tweak.
- **P2.3 — Explicit end-user persona framing + a rigor lint.** Add an "you ARE the end user;
  exercise the journeys a real user runs" block to the projected prompt + `acceptance-kernel.md`
  §E. Add an advisory lint warning when `tooling.eval.cmd` looks like a pure unit-test runner for
  a user-facing milestone, nudging toward the M3 gate.
- **P2.4 — Make M3 capable of being authoritative (fail-closed E2E).** Ship an M3
  acceptance-calibration-record (`schemas/acceptance-calibration-record.schema.json` exists) so a
  *calibrated* browser-E2E judge can block-on-fail instead of always deferring to a human
  sign-off. This reopens a deliberate v1 non-goal (`driver.py:3073-3077`) — a doctrine decision.

**Files touched:** `schemas/campaign-plan.schema.json`, `schemas/functional-checklist.schema.json`,
`engine-kit/orchestrator/scope_report.py`, `driver.py` (`_project_acceptance_prompt`, acceptance
resolver graph + hash, verdict coercion), `governance/acceptance-kernel.md`,
`role-cards/acceptance-agent.md`; new validator (rigor lint).

**Risks:** LOAD-CLOSURE (every new verdict input — ledger, checklist, gap report — must be bound
into `_acceptance_resolver_graph` + hashed); **follow-up-loop non-termination** (the new
gap-driven re-decompose MUST have a convergence guard + budget/max-rounds bound, else an unclosable
gap loops forever — this is the headline risk the gap-driven model introduces); migration burden of
an enumerated checklist (make it default-derivable/opt-in, P-C's default-off discipline);
**v4-optimization regression** — the ledger/checklist are the biggest re-inflation risk to the
WP-4 acceptance-kernel savings (−48% read). Mitigate per cross-cutting invariant: compact-project
the checklist/ledger schemas for cold-start, keep the gap report a per-milestone runtime input
(not always-load), and gate the track on `context_budget_report.py` staying within baseline (or an
explicit, justified rebaseline).

**Decisions (resolved 2026-06-29):** (a) **RESOLVED — visible gap report driving
autonomy-gated follow-up, not a hard gate** (see DECISION block above). (b) implement the
Requirement Ledger now, on a fresh worktree off `main` — *pending: confirm timing* (Track 2 is
3rd in sequence). (c) P2.4 "lift M3-always-advisory" — *still open* (doctrine call; only needed if
you want unattended ship on a real browser-E2E gate). (d) end-user persona = generic vs
charter-declared — *still open*. (e) bind completeness to a finer PRD requirement list via the
ledger `covers_req_ids` (chosen — the milestone-level backlog is too coarse for a useful gap
report).

---

## Track 3 — Retire stale / superseded docs & code (without breaking adopters)

**Goal (user):** delete or archive expired/dead docs/code (example cited:
`docs/adr/ADR-0001-engine-substrate.md`), without breaking future adopter integration.

**Key correction from the audit:** the cited example **is NOT stale** — `ADR-0001` is a
NORMATIVE SOURCE cited by all 6 harness adapters (`engine-kit/adapters/*`), the driver, and two
READMEs (9 live refs); `doc_category: design-history`, still accurate. Likewise the full
`constitution.md` and `process/delivery-loop.md` are **load-bearing** (both sha-pinned in
`_sources.yaml`; "retired" for delivery-loop.md was scoped only to the *Acceptance session's*
load set, not a global death). **Do not touch these.**

**Sanctioned mechanism:** doc-governance forbids silent delete; retire = `git mv` → `archive/`
(+ `superseded_by`). The adopter surface is exactly the `vendor-framework.sh` INCLUDE set;
`archive/`, `compact/`, `examples/` are **excluded from vendoring** (zero adopter impact).

**Genuinely archivable set (evidence: 0 live refs):**
| Path | Action | Why safe | In vendor surface? |
|---|---|---|---|
| `compact/handoff-2026-06-12.md` | `git mv → archive/` | frozen handoff, work landed | **No** (`compact/` excluded, `vendor-framework.sh:48-56`) |
| `compact/2026-06-16-v2-loop-engine-handoff.md` | `git mv → archive/` | shipped | **No** |
| `compact/2026-06-21-pc-browser-e2e-handoff.md` | `git mv → archive/` | shipped | **No** |
| `compact/2026-06-24-requirement-ledger-handoff.md` | `git mv → archive/` | design landed | **No** |
| `docs/real-adapter-smoke.md` | `git mv → archive/` (or `docs/diagnostics/`) | 0-ref point-in-time smoke evidence, misfiled as a guide | **YES — currently vendored** (all of `docs/` is INCLUDEd, `vendor-framework.sh:30-46`) |

**CORRECTION (Codex factual #5):** the original draft lumped all 5 as "outside the vendor surface" —
wrong. Only the four `compact/*` are excluded. `docs/real-adapter-smoke.md` **is** shipped to every
adopter today, so moving it is a *genuine adopter-surface cleanup* (a real improvement, not zero-impact
housekeeping) — and its removal IS a vendored-tree delta the P3 verification diff must expect.

Everything else flagged is either load-bearing or an intentional placeholder/proposal
(`common-detours-typeB/C`, `architecture-health-metrics` — deliberate forward-looking stubs).

**Proposed phases.** P3.0 archive the 4 `compact/*` handoffs. P3.1 refile
`docs/real-adapter-smoke.md` out of the adopter bundle. P3.2 (optional, config not deletion) add
`--exclude=docs/diagnostics` to `vendor-framework.sh` so framework-internal diagnostics stop
shipping to adopters. P3.3 update `process/doc-responsibility-matrix.md` if any moved doc is
listed; re-run `kernel_equivalence.py` (stays green — none are `_sources.yaml`-listed).
**Verification gate:** dry-run `vendor-framework.sh . /tmp/adopter-check` and diff — the only
delta should be the removed docs.

**Two adjacent wiring gaps surfaced (not staleness — confirm intent):**
- `vendor-framework.sh` INCLUDEs `CLAUDE.md` but **no root `CLAUDE.md` exists** (silently
  skipped), yet R1 Default-Full requires adopters to have a `CLAUDE.md`→`@AGENTS.md` shim.
  Intentionally adopter-created-only, or should the framework ship a root `CLAUDE.md`?
- Root `QUICK-FIX.md` exists but is **not** vendored — intentional?

**Decisions needed:** (a) confirm conservative `git mv → archive/` (not `rm`)? (b) is `compact/`
a rolling scratch dir (clear stale → archive) or a de-facto archive (rename/merge)? (c) exclude
framework-internal diagnostics from the adopter bundle? (d) resolve the two wiring gaps above.

---

## Track 4 — Autonomy level: human-on-loop & autonomous single-milestone close

**Goal (user):** confirm whether the framework is human-on-the-loop, and whether the loop can
**autonomously complete one milestone's closed-loop delivery**.

**Answers (evidence).**
- **Posture is config-selected** by `charter.autonomy.level ∈ {human_in_the_loop,
  human_on_the_loop, fully_autonomous_within_budget}` (`delivery-loop.md:139`). The **loop
  engine itself is architected for human-on-the-loop**: once kicked off, `_drive()` runs
  dev→gate→review→close→advance back-to-back in a single invocation with no human re-invocation
  (`driver.py:2473,2523-2558`); it only HALTs at fail-closed boundaries + the human authority
  gates. **But the shipped charter template defaults to the conservative `human_in_the_loop`**
  (`templates/mission-charter.yaml:31`, `acceptance.mode: advisory`, `auto_fix_iteration: false`).
- **Can it autonomously close one milestone?** Mechanically **yes** for the
  dev→review→close→advance core. The *ship* needs **exactly one** human sign-off
  (`advisory_acceptance_pass_signoff`) **unless** you opt into authoritative auto-ship =
  `acceptance.mode: auto` + **calibrated judge** + `autonomy.level:
  fully_autonomous_within_budget` (`driver.py:3056-3080,4385-4418`). Mandatory human touches
  range from **0** (autonomous + calibrated, or acceptance off) → **1** (default advisory ship)
  → **2-4** (guided Gate-1 + campaign plan sign-off + per-milestone merge gate).
- **There is no architectural blocker.** Every lever already exists (`autonomy.level`,
  `acceptance.mode`, `auto_fix_iteration`, `delivery_only`, `merge_prompt_at_close`). The only
  genuine prerequisite for *unattended ship* is **§3.6 judge calibration** — by design an
  uncalibrated judge can never auto-ship.

**DECISION (user, locked 2026-06-29) — make `human_on_the_loop` the TEMPLATE DEFAULT** (not just
an optional preset). New adopters get autonomous-close-by-default; the gap-driven follow-up loop
(Track 2 P2.0) runs automatically in this posture. Note the scope: this changes the *template*
(`templates/mission-charter.yaml`) for NEW adopters only — existing adopters carry their own
already-instantiated charters and are unaffected until they re-adopt/opt-in. Migration note for
existing adopters belongs in `ONBOARDING.md` / fold-back.

**Proposed phases (mostly config + docs; the gap-driven follow-up loop in Track 2 P2.0 is the one
real engine change, intentionally owned by Track 2).**
- **P4.1 — Flip the template default to the `human_on_the_loop` autonomous-close preset.** Set
  `templates/mission-charter.yaml` `level: human_on_the_loop`, `acceptance.mode: advisory`,
  `auto_fix_iteration.enabled: true, max_rounds: 2` as the DEFAULT (was the conservative
  `human_in_the_loop`); name the preset in `delivery-loop.md` capability staging; keep a commented
  `human_in_the_loop` block for adopters who want to dial back. **Validator/test impact (narrowed
  per Codex R2 factual-2):** there is NO direct test asserting template `level` or
  `auto_fix_iteration` (the live-template test only checks the template loads cleanly,
  `test_run_loop.py:210`); the real fallout is the role-default **sync** test, which compares
  tooling fields incl. `acceptance.mode` (`test_role_execution_defaults.py:22`,
  `role_execution_defaults.py:27`) — update that. Confirm the charter validator still accepts the
  new default and that no §1.7-D checkpoint is implicitly weakened. **Safety (R2 confirmed):**
  `human_on_the_loop` + `acceptance.mode: advisory` + `auto_fix_iteration` does NOT auto-ship —
  advisory pass still halts at the ship sign-off (`driver.py:4394`) and authoritative auto-ship
  still needs `mode:auto` + calibration + `fully_autonomous_within_budget` (`driver.py:3056`).
- **P4.2 — Document the "one-sign-off close" recipe** in `delivery-loop.md` / `campaign-loop.md`:
  `delivery_only` + `auto_fix_iteration` + advisory acceptance ⇒ loop runs unattended to a single
  ship sign-off.
- **P4.3 — Formalize the §3.6 calibration runbook** (the path to *zero*-touch unattended ship):
  checklist + `judge_calibration.status: calibrated` + `mode: auto` + `fully_autonomous_within_budget`.
  **SCOPE CORRECTION (Codex B-3 + factual #4): zero-touch via config+calibration applies ONLY to
  static (M1) acceptance or acceptance-off.** For **browser-E2E (M3)**, zero-touch ship is
  *impossible without an engine change* — `_acceptance_authoritative()` hard-returns false for
  `browser_e2e` in v1 (`driver.py:3069-3077`). So "no engine change needed" (the original Track-4
  headline) is true for M1/off but FALSE for M3. To get unattended ship on a real browser-E2E gate,
  this track must pull in **Track 2 P2.4** (ship an M3 calibration record + lift the hardcoded
  advisory). State the M1-vs-M3 split explicitly in the recipe.
- **P4.3b — State the "0-touch" prerequisites (Codex NB-5):** even on the static path, 0 human
  touches requires a *pre-signed/supplied scope* (or `delivery_only` mode that skips the guided
  front-end). `full_chain_guided` ALWAYS requires an explicit human Gate-1 brief sign
  (`driver.py:2107-2117, 2176-2185`) — that is human authority over *what* is built and is not an
  autonomy knob.
- **P4.4 — Keep the fail-closed boundaries as the only hard stops** — never weaken a checkpoint's
  semantics; express autonomy purely through the existing knobs.

**Must-never-remove gates:** acceptance ship-authority calibration prerequisite;
`scope_deviation`/close-C-D/`gate_hard_fail`; `campaign_plan_signoff` + Gate-1 (human authority
over *what* gets built); no-auto-merge (§1.7-D); the 9 MANDATORY_CHECKPOINTS.

**Decisions (resolved 2026-06-29):** (a) **RESOLVED — make `human_on_the_loop` the template
default** (P4.1). (b) §3.6 calibration runbook — *still open* (only needed for true zero-touch ship;
the new default is one ship sign-off OR autonomous gap-driven follow-up). (c) campaign
branch-isolation vs trunk-direct — *still open*. (d) `auto_fix_iteration` enabled by default —
**yes**, part of the new default preset.

---

## Sequencing & effort

| Track | Size | Risk | Note |
|---|---|---|---|
| **3 — stale-doc cleanup** | S | very low | quick win; archive 5 files + verify vendor diff. Do first. |
| **4 — autonomy default→human-on-loop** | S–M | low–med | template default flip + docs; the gap-driven follow-up engine work is owned by Track 2 P2.0. |
| **1 — task-aware skills** | M–L | medium | gated on vendoring real UI skills (P1.0) + determinism discipline. |
| **2 — acceptance completeness + gap-driven follow-up** | **L** | med–high | highest user-value; Requirement Ledger + F1 + static checklist machinery + the autonomy-aware Acceptance→Deliver follow-up loop. The big one; carries the only non-trivial engine change. |

**Order LOCKED (user 2026-06-29): 3 → 4 → 2 → 1.** Note the Track 2↔4 coupling: Track 4 sets the
`human_on_the_loop` default, but the *behavior* that default unlocks (autonomous gap-driven
follow-up) is built in Track 2 P2.0. So Track 4's default flip is shipped in sequence, but its
full autonomous-close value is only realized once Track 2 lands. Each track lands on a fresh
worktree off `main`, **Codex-reviewed before merge** (standing gate), with `python3.12` test-suite
+ kernel/load-closure gates green.

## Open cross-track decision (most important)
Tracks 1 & 2 both add *signed, deterministic, requirement/task metadata at decompose/sign-off
time* (`task_signals` for skills; `covers_req_ids`/functional checklist for acceptance). They
should share one authoring touchpoint in Deliver's decompose + the `campaign_plan_signoff`
snapshot, so we don't bolt on two parallel metadata channels. Confirm you want them designed
together.
