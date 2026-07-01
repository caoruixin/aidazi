# Acceptance efficacy + E2E mandate — DESIGN CLOSURE / implementation handoff

- **Date:** 2026-06-30
- **Branch:** `acceptance-efficacy-e2e-mandate` (off `main` `2f0095d`)
- **Phase:** DESIGN COMPLETE — research + plan only. **NO runtime behavior change.**
- **Authorization boundary:** implementation is NOT authorized by this cycle. Track-2 hardening implementation is a SEPARATE next-phase authorization, on its OWN branch, with a fresh CODE-LEVEL Codex gate. OW-M3 implementation follows Track-2.

---

## 1. Scope of this cycle (what was authorized)
"research + plan only, 不改代码." Delivered: an end-user-perspective investigation of whether Acceptance validates end-to-end against the original PRD, plus two design specs taken through the Codex gate to APPROVE. **No engine, schema, role-card, template, or test file was modified** — see §4 verification.

## 2. What is delivered (all on this branch)
| Artifact | File | Status |
|---|---|---|
| Research + OW-0 adopter audit + locked plan | `archive/2026-06-30-acceptance-efficacy-and-e2e-mandate.md` | final |
| OW-M3 spec (requirement-driven mandatory browser-E2E; OW-2 ledger = input contract) | `archive/2026-06-30-ow-m3-mandatory-e2e-spec.md` | **Codex APPROVE (R2)** |
| OW-M3 Codex verdicts | `…-ow-m3-codex-review-r1.md` (REVISE), `-r2.md` (APPROVE) | retained |
| Track-2 hardening spec (universal F1 freshness + signed-input coverage) | `archive/2026-06-30-track2-freshness-signed-input-hardening-spec.md` | **Codex APPROVE (R3)** |
| Track-2 Codex verdicts | `…-track2-codex-review-r1.md` (REVISE), `-r2.md` (REVISE), `-r3.md` (APPROVE) | retained |
| This closure/handoff record | `archive/2026-06-30-acceptance-efficacy-DESIGN-CLOSURE-handoff.md` | — |

## 3. Key findings (carry-forward)
- **OW-0:** Acceptance is energized in the field, but every UI adopter ROUTES AROUND the structured browser-E2E (M3) class (airecruiter folds "真 web 端到端" into its M1 `eval.cmd`; airplat hand-rolls a control-plane live step; airecruiter even sets `acceptance.enabled:false`). The completeness-vs-PRD line is dormant in both (no requirement-ledger). The framework REPORTS completeness and makes real-E2E OPTIONAL; it does not ENFORCE either.
- **OW-M3 design:** make browser-E2E mandatory + requirement-driven — a milestone covering a `user_facing` requirement is FORCED to `browser_e2e` (no downgrade), with the OW-2 ledger `surface` classification as the signed INPUT CONTRACT. Evidence is mandatory; authority stays advisory (no calibration work). 9 real holes found+closed across the two specs.
- **Track-2 dependency:** OW-M3's runtime guarantee depends on closing two pre-existing gaps — (A) F1 freshness is re-validated non-uniformly, (B) authority-bearing plan fields (budget, gap_followup bounds, isolation/merge incl. the human merge gate) are not all inside the signed hash. Solved by a universal single-hash freshness gate + a guarded engine re-stamp for the one legitimate engine mutation (`deliver_followup`) + a complete signed-input inventory.

## 4. Verification — NO runtime behavior change
`git diff --stat main..HEAD` ⟹ 8 files, **all `archive/*.md`** (+486 lines docs). `git diff --name-only main..HEAD | grep -v '^archive/.*\.md$'` ⟹ NONE. No `engine-kit/`, `schemas/`, `governance/`, `role-cards/`, `templates/`, `process/`, or test file touched. The framework on `main` is byte-for-byte unchanged in behavior; these specs are additive design docs.

## 5. Implementation sequencing (NEXT PHASE — requires separate authorization)
1. **Track-2 hardening — FIRST.** Own branch off `main`. T2-A universal `_authority_fresh()` gate (every dispatch + every resume `proceed` + the gap-followup outer loop; F1-active only; durable freshness-block overlay preserving the original pause). TD6 single `signed_scope_hash` + guarded engine re-stamp for the `deliver_followup` insertion (exact-diff guard; atomic envelope+hash+provenance update; re-stamp is the pre-freshness step on the deliver_followup path). T2-B bind the signed-input inventory (gap_followup bounds, budget.\*, trunk_branch, milestone_isolation authority, isolation_strategy) into `H`; `raise_cap` requires re-sign. **Fresh code-level Codex gate required.**
2. **OW-M3 — after Track-2 lands + APPROVES.** OW-2 ledger `surface` field (input contract) + the sign-off refuse-to-sign gate + bind `covered_req_surfaces` into `H`. Ledger-gated/additive (no ledger ⟹ dormant). **Fresh code-level Codex gate required.**
3. **OW-2 / OW-3 onboarding docs** — ride OW-M3's schema bump; no Codex gate (non-normative).

## 6. What is explicitly NOT done (guardrails for the next session)
- No `_authority_fresh()` / re-stamp / signed-input-coverage code written.
- No `surface` schema field, no sign-off gate, no `covered_req_surfaces` binding.
- No onboarding/template/ledger changes.
- No charter or adopter (airecruiter/airplat) changes.
- Track-2 and OW-M3 implementations remain UNauthorized; each needs its own branch + code-level Codex gate before any runtime change.

## 7. Design seals to preserve through implementation
① completeness⇄quality source separation; ② Customer final authority (disposition/ship/reclassify/re-sign are human-only); ③ advisory-by-default (M3 mandates evidence, not auto-ship). No new engine authority is introduced by either spec.
