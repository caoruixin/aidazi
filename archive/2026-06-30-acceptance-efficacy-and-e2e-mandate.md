# Acceptance efficacy + requirement-driven E2E mandate — research & plan

- **Date:** 2026-06-30
- **Branch:** `acceptance-efficacy-e2e-mandate` (worktree `../aidazi-acceptance`, off `main` `2f0095d`)
- **Status:** DESIGN / PLAN ONLY — no runtime code changed. Awaiting Codex gate for the one code-touching item (OW-M3).
- **Origin question (user):** Does Acceptance actually do its job in adopter apps — representing the *end user*, validating *end-to-end* and *functionally*, against the *original requirements (PRD)* — not just unit tests? And: why is browser E2E *optional* when the product has UI / user interaction?

---

## 1. Executive answer

The user's prior research was **accurate**, with three precisions:

1. Acceptance is **on by default** (`acceptance.mode: advisory`, `templates/mission-charter.yaml:134`). What is rare is **auto-ship** (authoritative = `mode:auto` ∧ calibrated ∧ `fully_autonomous_within_budget`, `driver.py:3191-3211`), not Acceptance itself.
2. The M1 `closure_contract` is **coarse** — one `positive_shape` + one `anti_pattern` + a few `anchor_phrases` per brief (`schemas/research-brief.schema.json:44-63`). Per-requirement granularity exists **only** via the M3 `functional-checklist` (multi `criterion_id`) or ledger `covers_req_ids`.
3. **Completeness-vs-PRD is REPORTED, never GATED.** It rides a separate line (requirement-ledger → gap-report → scope coverage) deliberately *sealed* from quality (`gap-report.source` is always `requirement_coverage`, "NEVER from the Acceptance verdict", `schemas/gap-report.schema.json:5,12`). The true PRD gap — `uncovered_requirements` (REQs no signed milestone covers) — is **"context only"**, gated by nothing (`gap-report.schema.json:34`).

**One-line characterization (confirmed):** Acceptance turns *"did we build the thing right?"* into a trustworthy gate, but *"did we build everything the PRD asked?"* and *"is the evidence truly end-to-end?"* are report / optional / advisory in the framework — not enforced. It is the **quality-and-correctness governance pivot, not an automatic product-QA replacement.**

---

## 2. How Acceptance actually works (verified, with citations)

- **Position:** peer-of-Research outcome gate ("did we build the right thing?"), orthogonal to the Code Reviewer ("is the code well-built?") — `role-cards/acceptance-agent.md:27-29`. Symmetry check before judging: `:50-59`.
- **Binds a *signed* contract:** `_validate_acceptance_context` requires `intent_contract.confirmed_by_human:true` (goal/standard/proof_of_done), `driver.py:3764-3786`; symmetry check requires `customer_signed` + fresh `sign_off_date`, `acceptance-agent.md:54-55`.
- **Evidence (F5 — judge never runs the harness):** orchestrator runs `charter.tooling.eval.cmd`, hands artifact *paths* to the judge, `driver.py:3725-3744`. Code-inspection-only verdict is invalid (anti-pattern #5), `acceptance-kernel.md:120-122`.
  - **M1 (default) = static execution evidence** = whatever `eval.cmd` emits. **The framework does not guarantee it is end-user-facing** — it can be unit tests.
  - **M3 (opt-in) = browser E2E** = orchestrator drives the app, commits a hash-anchored manifest, judge reads it read-only against a signed `functional-checklist`, `acceptance-agent.md:153-164`. **v1 ships no M3 calibration ⇒ M3 is *always advisory*** (`driver.py:3204`, `acceptance-kernel.md:127`).
- **Verdict → outcome:** `pass` authoritative → auto-ship (rare); `pass` advisory (default) → `advisory_acceptance_pass_signoff` HALT for human `ship|reject`; `fix_required` → report + mandatory `acceptance_fix_required` checkpoint, stop session (`acceptance-agent.md:166-201`); `needs_human` → `surface_approve`.
- **Class derivation is a charter toggle, not requirement-driven:** `_acceptance_class()` returns `browser_e2e` iff `charter.tooling.acceptance.functional.mode == "browser_e2e"`, else `static` (`driver.py:3161-3168`). **Nothing forces a UI/interaction milestone onto M3.** ← the root cause of §4.
- **Completeness line (partially wired):** at milestone close `_emit_gap_report()` projects an advisory gap from `requirement-context.json` facts (`driver.py:4225-4274`); a REQ is `delivered` only when its covering milestone's terminal is an acceptance pass (`scope_report.py:269-277, 380-383`) — *honest*, waivers shown. **But: no ledger ⇒ dormant** (`driver.py:4244-4245`); gap-report is **advisory**; `uncovered_requirements` is context-only.

---

## 3. OW-0 — adopter "通电度" audit (field evidence, 2026-06-30)

| Dimension | airplat (Spring/PG web) | airecruiter = venture-strategy (M3·M4 user-facing) |
|---|---|---|
| Acceptance gate | `mode: advisory` — **energized**, runs at close, HALTs for sign-off (`airplat/charter.yaml:194`) | **`enabled: false`** on *both* M3 & M4 (`charter-M3*.yaml:112`, `charter-M4*.yaml:124`) — orchestrator gate **OFF**; Gate-2 manual by Customer |
| Calibration | uncalibrated → advisory only (`:203`) | uncalibrated → they disabled rather than run advisory |
| `eval.cmd` (M1 evidence) | `mvn verify && npm build` — Java ITs + FE build; "live acceptance" bolted on as a manual **control-plane step** (`:191`) | `run_m4_quality_checks.py` — incl. **"真 web 端到端"**, live uvicorn + FE build + live LLM/DB (`charter-M4*.yaml:121`) |
| `functional.mode` (class) | `static`; ran real **M3 once** (M3 7/8 advisory, `:17`), then reverted to static + manual live step | `static`; **M3 browser_e2e class never used** — E2E folded into the M1 harness |
| Structured M3 (checklist + hash-anchored manifest + set-equality coverage) | bypassed after one run; has `docs/acceptance/M3-functional-checklist.json` | **bypassed entirely** |
| requirement-ledger / `covers_req_ids` | none | none — `airecruiter-prd.md` exists but is unconnected |

**Verdict:** Acceptance is *not* dead in the field (airplat energizes it advisory; both run real behavioral/E2E checks). **But the structured browser-E2E (M3) class is routed around by every UI adopter** — E2E gets buried inside the M1 eval harness or a hand-rolled "control-plane step." The proper E2E machinery is too opt-in/heavyweight to be the default path. And the completeness-vs-PRD line is **dormant in both** (no ledger), so "did we deliver the whole PRD?" has zero automated signal even though the PRDs are sitting in the repos.

This is the empirical backing for the two fixes below: (a) make the completeness line *exist* for adopters (OW-2), and (b) make structured E2E the **forced** path when the requirement is user-facing, not an opt-in flag (OW-M3).

---

## 4. Why browser E2E must be requirement-driven, not optional

It is optional today for two **non-principled** reasons, not because "UI doesn't need E2E":
1. **Maturity/sequencing** — M3 needs the browser executor (`tooling.e2e` mechanics) + a calibration record; v1 shipped it as an opt-in flag.
2. **Generality** — aidazi serves non-UI adopters too (backend/data/agent milestones); a blanket "always browser E2E" would be wrong for a pure-API milestone.

The correct resolution (user's call): **the class should be DERIVED from the requirement's nature, not chosen by a human.** A milestone whose requirements touch UI / user interaction / user-perceived experience ⇒ M3 is an **obligation**, with **no downgrade to M1**. Today's hole is precisely that `_acceptance_class()` reads "do I want it on?" instead of asking "is this requirement user-interactive?".

---

## 5. Locked plan

Design principle: do **not** break the three deliberate seals — ① completeness⇄quality source separation, ② Customer final authority (disposition/ship are human-only), ③ advisory-by-default. Enhance *inside* them; grant the engine no new authority.

### IN (4 items)

**OW-0 — adopter audit (DONE, §3 above).** Diagnostic; gate on the rest. Result: machinery exists, M3 bypassed, completeness dormant.

**OW-2 — requirement-ledger as an onboarding first-class artifact (seed from PRD).** onboarding / template / docs only; zero runtime risk.
- Wizard step: decompose PRD → `REQ-*` (`source.channel: prd`, schema already supports it, `schemas/requirement-ledger.schema.json:27`); each signed milestone declares `covers_req_ids`.
- Rationale: without a ledger the whole completeness line is byte-identical-dormant (`driver.py:4244-4245`) — confirmed in both adopters.
- **Folds in the cheap OW-1:** surface the *already-emitted* advisory gap-report in the campaign-close human-readable summary (it is currently only written to disk + audited, `driver.py:4266`). No new checkpoint, no new authority.

**OW-3 — Gate-1 functional-checklist authoring discipline.** onboarding / template / docs only.
- Spec + counter-examples making `functional-checklist` / `eval.cmd` criteria **end-user-observable outcomes** ("user-visible observable outcome (NOT a selector or mechanic)", `schemas/functional-checklist.schema.json:20`).
- Doubles as the M3 criteria source for OW-M3 — the two are one authoring act.

**OW-M3 — requirement-driven, mandatory browser E2E (the one code-touching item; user's core ask).**
- **Derive, don't toggle:** a milestone whose covered requirements are user-facing/interactive ⇒ acceptance class **forced** to `browser_e2e`; **no downgrade** to M1 (change `_acceptance_class()`, `driver.py:3161-3168`, from "read flag" to "derive from requirement attribute + non-downgradable").
- **Fail-closed gate:** such a milestone **cannot reach `delivered` on M1-only evidence** — absent browser evidence ⇒ `needs_human`.
- **Authority stays advisory:** the M3 verdict still HALTs for human confirm — **so the cut calibration work is NOT needed.** Mandatory *evidence*, not mandatory *auto-ship* — the two are separated cleanly.
- onboarding companion: Gate-1 forces a user-journey `functional-checklist` for UI requirements (← OW-3).

### OUT (cut — value-unclear or large change)

- ❌ **OW-1 real checkpoint** — only the cheap "surface in close summary" survives (folded into OW-2). A new completeness checkpoint also depends on first fixing the Track-2 authz gap (§7); not worth it now.
- ❌ **OW-4 calibration → authoritative M3** — pays only for unattended auto-ship, not a current goal. (Advisory M3 + human confirm already gives real E2E evidence.)
- ❌ **OW-5 per-REQ three-way wiring** (`covers_req_ids` ↔ `criterion_id` ↔ verdict case) — largest lift, latest payoff; defer until OW-2/3/M3 are proven.

---

## 6. Sequencing & verification

1. OW-0 ✅ (this doc).
2. OW-2 ∥ OW-3 — docs/onboarding/template; no Codex gate needed (non-normative changes).
3. **OW-M3** — write a design spec first, then run **Codex gpt-5.5 xhigh** review/acceptance (per the standing Codex verification-gate norm), because it touches `_acceptance_class()` + a fail-closed delivery gate + class-derivation semantics. Use the bounded review runner; background/headless.
4. Re-audit airplat M5 / airecruiter M4 against the new mandate as the live canary.

---

## 7. Risks / dependencies

- **Track-2 authz gap (pre-existing):** `gap_followup.max_subsprints` is not in the signed-scope hash → post-signoff escalation can pass `--allow-real`. **Must be fixed before** any completeness *gating/auto-route* is extended. OW-1's surviving slice is report-only and sidesteps it; do not extend §1.7-F authority until that gap is closed.
- **Adopter friction signal:** airecruiter set `acceptance.enabled: false` *because* uncalibrated — i.e. when calibration is the blocker, adopters turn the gate OFF rather than run advisory. OW-M3 must not reintroduce a calibration prerequisite on the *evidence* path, or adopters will bypass it the same way.
- **Generality guard:** OW-M3's derivation must classify non-UI milestones as `static` correctly, or it will wrongly force browser E2E on pure-API/data milestones.
