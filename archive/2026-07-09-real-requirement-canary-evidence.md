---
name: 2026-07-09-real-requirement-canary-evidence
doc_category: evidence
created: 2026-07-09
description: >-
  Phase-2 Commit D evidence — the FIRST-EVER real-adapter REQUIREMENT-DRIVEN
  chain GREEN end-to-end: one requirement file → real Research brief → gate-1
  decision-file sign → real two-stage Deliver decompose → emitted sign-ready
  plan + generated compact prompts → --sign-plan (prompt_artifacts_digest) →
  real campaign to done, pausing ONLY at advisory_acceptance_pass_signoff.
  4-round iteration ledger (3 real-path defects found + fixed, then GREEN).
---

# Real requirement-chain canary — evidence (Phase-2 Commit D)

**Test:** `engine-kit/scheduling/tests/test_real_requirement_canary.py`
(double env gate: `AIDAZI_E2E_REAL_REQUIREMENT=1` + `claude` on PATH;
`AIDAZI_ALLOW_REAL_ADAPTER=1` exported into the CHILD CLI env only — the
standing rule). Model: claude-sonnet-4-6 for every role. Intent contract
signed by the canary author (charter `confirmed_by_human: true`).

## GREEN run (round 4) — 1 passed in 695.58s (0:11:35)

| step | CLI | rc | proof |
|---|---|---|---|
| 1 | `--requirement … --repo-dir ws --allow-real` | 10 | REAL research spawn; brief MATERIALIZED under `<ws>/.runs/campaign-bootstrap-…/docs/briefs/`; `customer_gate1_signoff` checkpoint written; audits `requirement_ingested` + `brief_materialized` ×1 each |
| 2 | `… --resume --decision gate1-sign.json` | 0 | identity-bound sign accepted; REAL two-stage decompose (3 deliver spawns: Stage-1 backlog + Stage-2 ×2); plan EMITTED + sidecar + 4 generated compact prompts; audits `campaign_decomposed` + `campaign_plan_emitted` |
| 3 | `--campaign plan --repo-dir ws --sign-plan` | 0 | `signoff` carries `prompt_artifacts_digest` (generated prompts byte-bound to the signature) |
| 4 | `--campaign … --allow-real` | 10 | FIRST pause = `advisory_acceptance_pass_signoff` @ m1-create — NO earlier pause of any kind |
| 5 | `… --resume --decision ship-1.json` | 10 | advisory pause @ m2-append |
| 6 | `… --resume --decision ship-2.json` | 0 | `status=done`, 2/2 milestones, one Acceptance per milestone, no agent-stuck diagnostics |

**Delivered artifact (byte-exact to the requirement):**
`notes/hello.md` = `HELLO-REQ-M1\nHELLO-REQ-M2`.

**Fidelity contracts held (the round-2 failure mode, fixed):** the REAL
decompose produced `m1-create` / `m2-append` — mirroring the requirement's two
DELIVERY STEPS (not its file list), ONE sub-sprint each (minimality), with
acceptance bars QUOTING the byte-exact content: "cat notes/hello.md outputs
exactly HELLO-REQ-M1 …" / "… HELLO-REQ-M1 newline HELLO-REQ-M2 …".

**Spawn ledger:** bootstrap = 4 real spawns (research ×1, deliver ×3);
campaign = 2 units (dev/review/deliver-close/acceptance chain per unit).

## Iteration ledger — every round failed CLOSED at a deterministic gate

| round | outcome | defect found | fix (committed) |
|---|---|---|---|
| 1 (137s) | step 2 `gate_hard_fail` | REAL Stage-1 verdict schema-invalid (missing required `goal`) — prose shape description insufficient for a real model | explicit JSON OUTPUT skeletons in Stage-1 + Stage-2 prompts (the canary-proven contract style) |
| 2 (220s) | campaign leg `gate_hard_fail` @ first unit eval gate | FIDELITY loss: decompose re-grouped the requirement's steps by FILE (m1-init-notes/m2-init-handoff), generic bars ("valid non-empty content"); Dev delivered filler prose with NO sentinel — the deterministic eval gate caught it before anything shipped | FIDELITY CONTRACTS (research DELIVERY-PLAN section w/ verbatim deliverables; Stage-1 mirrors steps + quotes exact content in bars; Stage-2 copies byte-exact deliverables into scope_in/exit_criteria + minimality); brief artifact-envelope unwrap (round 2's brief landed as a JSON-escaped blob); tolerant intermediate eval gate |
| 3 (233s) | step 2 `gate_hard_fail` | the real agent SANDBOX restricts reads to the session cwd (= the repo): the brief/requirement in a sibling tmp run-dir were UNREADABLE — the agent honestly reported it (and this retroactively explains round 2's blind decompose) | bootstrap run dir = the DEFAULT in-repo `<ws>/.runs/…` (agents can read it; the generated review prompts' engine-artifact exclusion already names `.runs/`) |
| 4 (696s) | **PASSED** | — | — |

Every failure surfaced as a clean rc-10 pause with an actionable
`gate_hard_fail` checkpoint — never a crash, never silently-shipped wrong
content. Round 2 is the strongest fail-closed evidence: a real Dev DID deliver
plausible-but-wrong content and the deterministic eval gate stopped the
campaign before Acceptance or a human ever saw it as "done".

## What this proves (design §6 Done-evidence)

1. **Requirement → running campaign with ≤1 sitting before start** (roadmap
   §3 Done): two async decisions here (gate-1 sign, `--sign-plan`) — the
   interactive path folds them into one sitting (Commit C, offline-tested).
2. The emitted plan is RUNNABLE: zero `milestone_decompose_required` /
   `dev_spec_refinement` / `acceptance_spec_refinement` pauses [R0 B-1 +
   R0.2 B-1] — the first pause a clean run hits is the advisory sign-off.
3. The generated compact prompts are real-consumable (real Dev/Review agents
   executed them) and byte-bound to the signature
   (`prompt_artifacts_digest` in the signoff) [R0.3 B-2].
4. Authority chain intact end-to-end: gate-1 sign was identity-bound
   (decision-file binding), the plan signature was explicit, every milestone
   shipped on an explicit human `ship` decision, zero watchdog false-kills.
