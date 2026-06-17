---
title: Friction playbook
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
size_target: 24KB
split_trigger: if any single friction grows past 3KB, move the worked detail to a process/ doc and keep the entry as a summary + pointer
notes: >
  Practical troubleshooting library — concrete friction patterns adopters hit,
  with how to spot + how to exit. Each entry is a fixed compact 5-field shape
  (Symptom / Why it happens / What to do / What not to do / Pointer). F1 is the
  dual-abstraction worked case anchoring Constitution §1.7-A (load-bearing;
  do not delete). F2-F12 are timeless rewrites of the original F1-F12
  carryover. F13-F15 are v4 additions (Acceptance calibration regression;
  closure_contract vs closure_criterion confusion; Phase 1+2 merge regret).
  Read this BEFORE your first milestone, not after your third.
---

# Friction playbook

This is the practical troubleshooting library: concrete friction patterns adopters hit, how to spot each one, and how to exit. Read it **before** your first milestone — it's the cheapest insurance in the framework.

Each entry follows a fixed shape:

- **Symptom** — what you'd observe.
- **Why it happens** — the root cause.
- **What to do** — how to exit.
- **What not to do** — the tempting wrong fix.
- **Pointer** — the rules/docs that govern it.

Frictions come in two kinds: ones the framework already addresses by default (you just need to use the default), and ones it documents but leaves you to apply (you decide when).

---

## F1 — Dual abstraction layer in a Type A agent

- **Symptom**: a Type A agent has two parallel action surfaces at once — e.g., a 5-action enum (`escalate | resolve | clarify | reject | wait`) *and* a tool-use catalog. The LLM implicitly picks which surface to use per turn; signals conflict, surfaces drift, eval grades only one.
- **Why it happens**: phased adoption — start with a small action enum, add tool-use for real needs, never retire the enum ("keep it for intent classification"). Now every turn carries two semantic choices. The ambiguity is structural, not accidental.
- **What to do**: pick ONE canonical surface (default: single tool-use for Type A). Audit every call site of the deprecated surface and migrate it sprint by sprint — eval rubric clauses → judge tool-use evidence; projection fields → drop; guards → retarget to Tier-0 or delete; per-UC rules → likely forbidden anyway, delete + file a failure-brief. Verify at milestone close that no closure_contract clause references the dead surface.
- **What not to do**: add new tools on the deprecated surface "to stay consistent." That's the move that created the dual surface. The temptation to "extend the enum to cover this new tool" is the signal to retire the enum instead. Don't attempt a single-PR removal either — migrate incrementally.
- **Pointer**: `governance/constitution.md` §1.7-A; `process/tech-architecture-decision-catalog.md` Δ-3 decision #1; Δ-9 triage in `process/post-deployment-iteration.md`.

## F2 — Composite eval scores drift over time

- **Symptom**: programmatic composite scores (mean composite, task-success rate, judge dimensions) fluctuate across sprints even when no behaviour changed.
- **Why it happens**: provider/model drift; judge calibration variance; mocked-vs-real-LLM gap; unvalidated weighting dimensions.
- **What to do**: treat composite scores as **observation only**. Gate close on the curated bad-case suite + the Acceptance verdict, not on a composite number. Surface composites in reviews as signal.
- **What not to do**: use a composite-score climb to declare a milestone done, or to justify shipping. A number that drifts on its own can't be a gate.
- **Pointer**: `governance/constitution.md` §1.6; `process/badcase-lifecycle.md`; `process/architecture-health-metrics.md`.

## F3 — Dev sessions bundle Deliver-owned files at commit

- **Symptom**: a Dev session stages `sprint_objective.md` / `handoff.md` / other Deliver-owned files (e.g., via `git add -A`); at close, Deliver has to unpick them.
- **Why it happens**: Dev sessions don't track which files are Deliver-owned; broad staging commands; commit discipline isn't enforced by the constitution alone.
- **What to do**: Dev stages only the files in its sub-sprint's declared modules + its own `handoff.md` §1-§11. Use explicit paths, not blanket staging. A pre-commit bundling check (optional adopter tooling — see `tools/README.md`) can mechanize this if an adopter builds it; the explicit-path discipline is the sufficient default.
- **What not to do**: rely on Deliver to clean up at close — that pushes ownership confusion downstream and risks a Dev edit to a Deliver artifact slipping through.
- **Pointer**: `governance/constitution.md` §5 (state-ledger ownership); `role-cards/dev-agent.md` §3; `process/artifact-taxonomy.md` (Δ-12).

## F4 — Sprint stanza fields filled with hand-wave content

- **Symptom**: a sub-sprint claims its stanza is filled, but "generalization coverage" reads "TBD" or "deferred" with no reason; it ships and the Code Reviewer catches it late.
- **Why it happens**: rushed planning; Deliver generates a prompt that passes token-pattern-match but not semantic-pattern-match.
- **What to do**: validate the stanza against `schemas/sprint_stanza.schema.json` before dispatching the compact dev prompt. If it fails, Deliver + human refine before dispatch. (A stanza validator is deferred tooling — `tools/README.md`.)
- **What not to do**: dispatch a stanza with placeholder fields intending to "fill it later." Later is at the close gate, which is the expensive place to catch it.
- **Pointer**: `schemas/sprint_stanza.schema.json`; `role-cards/deliver-agent.md` §3.2; `governance/constitution.md` §1.4-i (self-containment).

## F5 — Code Reviewer misses multi-dimensional issues

- **Symptom**: a single review catches one lens (e.g., semantic hardcode) but misses another (e.g., an injection surface or a regression-coverage gap).
- **Why it happens**: one review pass anchors on one lens and under-covers the others.
- **What to do**: run multiple review lenses. The clean v4 way is intra-role fan-out: the Code Reviewer mounts review-lens role skills (correctness / security / architecture / regression-coverage) or fans out read-only sub-agents per lens, then consolidates one verdict (`process/role-skill-model.md`). If your environment can't fan out, walk the lenses serially in named sections of `codex-findings.md`. Block-on-any-reject.
- **What not to do**: treat one review pass as covering all lenses, or let fan-out lenses each emit a parallel verdict — the role consolidates into one signed verdict (boundary invariant #6).
- **Pointer**: `role-cards/code-reviewer-agent.md` §9; `process/role-skill-model.md` §4-§5; `templates/anti-hardcode-review-kernel.md`.

## F6 — Agent context-window saturation

- **Symptom**: a Dev/Reviewer session runs out of context mid-sub-sprint; truncates; produces an incomplete handoff or findings.
- **Why it happens**: large diffs, many full-file reads, verbose chat self-narration.
- **What to do**: the most reliable fix is **break the sub-sprint smaller**. Also: budget reads per the Context Pack Prompt; grep/glob instead of full reads; trace decisions instead of narrating them in chat.
- **What not to do**: push a sub-sprint that can't fit one context window and hope the agent compresses — it'll truncate the handoff, which is the load-bearing artifact.
- **Pointer**: `governance/context_briefing.md` (Context Pack Prompt); `governance/constitution.md` §1.4-i; `process/milestone-framework.md` (5-sub-sprint signal); `process/context-passing-efficiency.md` (Δ-5).

## F7 — Bad-case suite grows without bound

- **Symptom**: the curated bad-case suite accumulates hundreds of cases; manual review at every milestone close becomes infeasible.
- **Why it happens**: every case is opened at `core` tier; no downgrade discipline.
- **What to do**: be aggressive about `scope-relevant` tagging at case-open time — only `core` cases run at every milestone. Apply the downgrade rule (N≥2 PASS across consecutive closes → downgrade tier).
- **What not to do**: open everything as `core`, or never downgrade. An always-growing core suite makes the human review gate collapse.
- **Pointer**: `process/badcase-lifecycle.md` (tiering + downgrade rule).

## F8 — Research proposal shipped as binding

- **Symptom**: Research proposes Solution X; Deliver + Dev implement X verbatim; when it doesn't work, there's no fallback.
- **Why it happens**: treating an exploratory proposal as a decision; not requiring alternatives.
- **What to do**: a Path-1 research brief should carry ≥2 alternatives with trade-offs. If a proposal offers only one, dispatch another research pass before consuming it. Keep the distinction between an informal `docs/proposals/` exploration and a signed `docs/research-briefs/` brief.
- **What not to do**: implement a single-option proposal as if it were a signed decision. A proposal is an input; the signed closure_contract is the commitment.
- **Pointer**: `role-cards/research-agent.md`; `docs/directory-taxonomy.md` (proposals vs research-briefs); `role-cards/deliver-agent.md` §2.1.

## F9 — Forbidden-list temptation under deadline

- **Symptom**: a sub-sprint is failing close; the team is tempted to add "just one keyword / one if-else" to make the case pass.
- **Why it happens**: deadline pressure; mistaking the symptom for the problem.
- **What to do**: classify the failure per the Δ-9 fix-layer set. If it's a real `runtime_guard`/`java_guard` need, check `runtime_invariants.md` for a current Tier-0 that justifies it. If no Tier-0 covers it, choose explicitly: (a) STOP and escalate to `human_review_required`, (b) ship with an explicit sunset plan recorded in the stanza, or (c) re-route to `prompt_projection` / `skill_state` / `semantic_planner`.
- **What not to do**: add the keyword silently. The whole §1.7 chain exists to make this temptation visible; defeating it quietly is the framework breach the chain guards against.
- **Pointer**: `governance/constitution.md` §1.7 + §1.5; `process/post-deployment-iteration.md` (Δ-9 layer classification); `docs/current/runtime_invariants.md`.

## F10 — Milestone scope creep

- **Symptom**: a milestone planned for 3 sub-sprints becomes 7; the acceptance bar broadens mid-flight; close keeps slipping.
- **Why it happens**: Deliver + human not enforcing the milestone-size discipline; "while we're in here" additions.
- **What to do**: call scope creep early. Close the milestone at its planned size and open the next with the spillover. A sub-sprint that crosses unrelated architectural surface belongs in a different milestone. The 5-sub-sprint ceiling is the signal to split.
- **What not to do**: let the milestone sprawl to absorb everything discovered. Better to close M0 at 3 + open M1 than to let M0 grow to 7.
- **Pointer**: `process/milestone-framework.md`; `process/delivery-loop.md` §4.2.5 (scope_envelope_check) + `close_taxonomy_C_or_D` checkpoint.

## F11 — Cross-session memory loss

- **Symptom**: an agent on cold start doesn't know context established in a prior session; produces redundant or wrong work.
- **Why it happens**: the framework's "no shared chat history" rule, combined with Deliver not updating the handoff at close.
- **What to do**: Deliver's close maintenance is mandatory — update handoff §0 (cold-start table), §1 (narrative with retention), §2 (archive index). Context passes via repo docs only; the handoff is the durable carrier.
- **What not to do**: skip handoff maintenance at close. The next session has no cold-start context if §0/§1/§2 are stale — the "no chat history" rule then bites instead of helping.
- **Pointer**: `role-cards/deliver-agent.md` §3.5; `templates/handoff-template.md`; `governance/constitution.md` §3.4 invariant #1.

## F12 — Adoption regret ("we adopted aidazi but it slowed us down")

- **Symptom**: a team adopts the framework, runs 2-3 milestones, feels slower than before, considers abandoning.
- **Why it happens** (in frequency order): adopted full when selective would fit; skipped the three domain contracts; treated compact-prompt generation as overhead not speedup; solo developer with no role separation so the discipline collapses.
- **What to do**: the framework is overhead-amortizing, not free — break-even is usually around milestone 2. If you're at milestone 2 and still slow, audit: right adoption profile? domain contracts actually filled? Deliver doing close maintenance? If yes to all and still slow, drop to Profile C (selective): keep the anti-hardcode kernel + sprint stanza + Acceptance gate, shed the rest.
- **What not to do**: adopt Profile A (full) on day one for a small/solo project, or run the machinery with empty domain contracts.
- **Pointer**: `docs/brownfield-guide.md` §1 (profiles); `docs/domain-adaptation.md` (the three contracts); `role-cards/deliver-agent.md` §3.5.

## F13 — Acceptance calibration regression (v4)

- **Symptom**: an Acceptance verdict that was trustworthy starts flipping, or a `fully_autonomous_within_budget` run silently keeps treating the judge as authoritative after a model or skill change.
- **Why it happens**: the calibration identity is (judge agent_kind × model × role-skill set). Swapping the Acceptance model, or adding/removing an Acceptance role skill, invalidates calibration — but the charter still says `status: calibrated`.
- **What to do**: on any change to `tooling.acceptance.agent_kind` / `model` / `skills`, set `judge_calibration.status: uncalibrated` and re-run the calibration set before trusting verdicts in autonomous mode. The orchestrator must auto-degrade to `human_on_the_loop` while uncalibrated.
- **What not to do**: hand-flip `status` back to `calibrated` without a calibration run, or change the Acceptance judge mid-milestone and assume the old calibration carries.
- **Pointer**: `governance/constitution.md` §3.6 + §3.4 invariant #6; `process/delivery-loop.md` §4.2.2; `role-cards/acceptance-agent.md` §4 + §11.

## F14 — closure_contract vs closure_criterion confusion (v4)

- **Symptom**: adopters collapse the two; someone judges a milestone against per-case criteria, or treats a single bad case's criterion as the whole milestone's success definition. A related sub-symptom: reading a `closure_criterion` as an automatic string predicate ("trace contains X → pass").
- **Why it happens**: similar names, adjacent purpose. The **closure_contract** is the milestone-level scope contract (Research-authored; Acceptance judges against it). The **closure_criterion** is the per-bad-case end-state (one eval case). Both use the §1.7-B three-component shape, which makes them look interchangeable.
- **What to do**: keep the levels distinct. Acceptance judges delivered behaviour against the *closure_contract* (whole milestone). A *closure_criterion* governs one case in the bad-case suite. Write both as human-judgment paragraphs (positive shape + anti-pattern + anchor phrases); anchor phrases are evidence you cite, never a passing condition.
- **What not to do**: judge the milestone by summing per-case criteria, or score a case with `trace.contains(X) == true`. Keyword-match scoring violates §1.7-B.
- **Pointer**: `governance/constitution.md` §1.7-B + §12 (glossary: both terms); `role-cards/research-agent.md` §4; `role-cards/acceptance-agent.md` §2 + §5.2.

## F15 — Phase 1+2 merge regret (v4)

- **Symptom**: an adopter who merged business-need (Phase 1) and product/service design (Phase 2) into one doc hits a wall when stakeholders diverge — the "what the customer wants" and "how we satisfy it" decisions start contradicting and there's no seam to split them at.
- **Why it happens**: merging is right for Type C / single-author / seed-stage projects, but the project grew past that — more stakeholders, more complexity — and the merged doc now hides a real disagreement.
- **What to do**: split at the next milestone boundary, not mid-flight. Extract the business-need into `docs/foundational/business-need.md` (the source-of-truth Customer signs) and the product/service design into `docs/foundational/product-service-design.md`. Record the split as a milestone decision.
- **What not to do**: keep forcing both concerns into one doc as stakeholders multiply, or attempt the split mid-milestone (it churns in-flight scope).
- **Pointer**: `docs/greenfield-guide.md` §5.3.1 (split-or-merge criteria); `docs/application-funnel.md` (Phase 1 vs Phase 2).

---

## Adding new frictions

When you hit a new friction in your project:

1. Document it locally first — `docs/diagnostics/<id>.md`.
2. If it recurs across 2-3 milestones, propose adding it here via a lesson (`templates/lessons-learned-template.md` → `process/fold-back-protocol.md`).
3. If it's project-specific (won't help other adopters), keep it in your project docs only.

## Editing this doc

Application-guide tier; edits land at fold-back sub-sprint cadence per `governance/constitution.md` §8. New frictions enter via adopter `lessons/` filings. F1 is load-bearing (it anchors Constitution §1.7-A) — keep it as the first entry.

---

End of friction playbook.
