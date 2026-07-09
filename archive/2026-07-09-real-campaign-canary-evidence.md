---
name: 2026-07-09-real-campaign-canary-evidence
doc_category: evidence
status: "FROZEN OUTCOME — GREEN: runs 10 (622s) AND 11 (358s, post-R3-fixes with substantive F5 evidence) each = 1 passed (rc 0/10/10/0, 2/2 milestones, 8 real spawns, all flow invariants asserted)"
created: 2026-07-09
branch: feat/phase1-campaign-unblock (worktree ../aidazi-phase1, base aa934ca)
mode: REAL (env-gated AIDAZI_E2E_REAL_CAMPAIGN=1; child env AIDAZI_ALLOW_REAL_ADAPTER=1; claude CLI, all roles claude_code / anthropic / claude-sonnet-4-6)
design: archive/2026-07-09-autonomy-roadmap-campaign-unblock.md §2 work item D (Codex R0.3 APPROVE)
---

# REAL campaign canary — evidence record

The FIRST attempt ever to drive the aidazi campaign orchestrator end-to-end
with real adapters (`run_loop.py --campaign` + real claude_code spawns for
Dev / Review / Deliver / Acceptance). Inputs: `examples/real-campaign-canary/`
(schema-valid charter with a HUMAN-SIGNED intent_contract — signed by the
canary author Rex/caoruixin, recorded here; strict-prompt compact Dev/Review
prompts per sub-sprint; 2-milestone plan m1-hello → m2-append).

Test: `engine-kit/scheduling/tests/test_real_campaign_canary.py`
(assertions = flow invariants only: exit codes, pause reasons, workspace
bytes, audit-event counts, no agent-stuck diagnostics).

## Run ledger

| Run | Result | What it proved / found |
|---|---|---|
| 1 (2026-07-09) | FAIL pre-spawn, $0 spend | **PRODUCTION BUG (campaign.py):** `--campaign` + `--repo-dir` crashed `TypeError: run_loop() got multiple values for keyword argument 'repo_dir'` — `--repo-dir` reached `run_unit` BOTH per-dispatch AND ambiently via `**run_loop_kwargs`. Since `--repo-dir` is REQUIRED for strict-prompt (compact/) resolution, **every real strict-prompt campaign was structurally impossible before this fix** — hard proof no real campaign ever ran. Fixed: `make_run_unit` pops the ambient copy (`ambient_repo_dir`); per-dispatch wins. Regression tests: CLI-with-`--repo-dir` full contract + precedence unit test (the mock CLI tests had never passed `--repo-dir`, which is why this survived offline). |
| 2 (2026-07-09) | FAIL at m1 `gate_pending`, 1 real Dev spawn | **REAL DEV SPAWN SUCCEEDED** — the live claude_code Dev session resolved the strict compact prompt and wrote `workspace/notes/hello.md` = exactly `HELLO-CANARY-M1\n` (25s, no watchdog kill ⇒ first live validation of the stream-json liveness path on a real campaign unit). The halt was the SUB-SPRINT EVAL GATE: `charter.tooling.eval.cmd` runs with CWD = the per-gate ARTIFACTS dir (deliberate, driver `_run_eval_cmd`), so the repo-relative `grep notes/hello.md` probed the wrong directory → exit 2 → `gate_hard_fail`. **FRAMEWORK GAP for every real adopter** (an `mvn verify`-style eval must anchor on the work repo): fixed additively — driver now exports `EVAL_REPO_DIR` (= bound `--repo-dir`, empty when unbound) into the eval env; canary charter anchors `grep -q HELLO-CANARY-M1 "$EVAL_REPO_DIR/notes/hello.md"`. Regression test: `test_eval_cmd_sees_repo_anchor_env`. |
| 3 (2026-07-09) | FAIL at m1 `review_pending`, 2 real spawns (Dev + Review), 104s | **THE FRAMEWORK CHAIN ADVANCED TWO MORE STATES.** Dev delivered again; the `EVAL_REPO_DIR`-anchored eval gate **PASSED** (run-2 fix validated live); the REAL Review spawn ran and returned a parseable JSON verdict — which the driver REJECTED fail-closed (`review-verdict.schema.json`): the verdict used `"layer": "content"`, not a schema enum value. **CANARY INPUT BUG, not a framework bug** — the shipped compact review prompt taught an illegal fix-layer enum. The fail-closed rejection is itself a positive observation (an invalid real verdict can never pass silently). Fixed: review prompts now pin `"layer": "infra"` (the generic bucket) and state the enum constraint. |
| 4 (2026-07-09) | FAIL at m1 `close_pending`, 3 real spawns (Dev + Review + Close), 187s | **REVIEW GATE PASSED LIVE** (real Review verdict schema-accepted after the enum fix). The REAL Deliver-close spawn then returned a review-shaped object and the driver fail-closed on `deliver-close-verdict.schema.json` ('verdict' required). **FRAMEWORK GAP (the last thin prompt):** `_step_close` dispatched the bare one-liner "Close sub-sprint X. Emit a deliver-close-verdict." — no output contract, unlike the self-contained projected Review/Acceptance contracts (b05d7a3); a live agent in a thin work repo cannot know the close schema. Fixed: `_step_close` now embeds the full deliver-close-verdict output contract + the engine-known `next_subsprint` mechanical fact (the agent judges the verdict letter, never guesses sequence position). Golden prompt fixture regenerated for the deliver hash ONLY with recorded rationale; regression = the golden test itself. |
| 5 (2026-07-09) | FAIL at m1 `review_pending`, 2 real spawns, 80s | **REAL-REVIEW NONDETERMINISM SURFACED (and handled correctly by the framework):** unlike run 4's clean pass, this run's live Reviewer noticed `.orchestrator/loops.json` (Loop-Ingress engine state the delivery loop itself writes into the workspace) and honestly recorded it as a P2 record-only finding — decision was still `pass`, `blocking_count: 0` — but cited the evidence as a bare path, which `review-verdict.schema.json` rejects (`^.+:\d+(-\d+)?$`). Fail-closed held again. **CANARY INPUT FIX:** review prompts now (a) pre-declare `.orchestrator/`/`compact/`/`docs/checkpoints/`/`eval/` as expected orchestrator artifacts (not Dev changes — do not report), and (b) pin the `path:line` evidence format. |
| 6 (2026-07-09) | FAIL at m1 `close_pending`, 3 real spawns, 120s | Review passed clean (prompt fixes validated live). The close verdict now had the CORRECT shape but emitted `"verdict_subclass": null` — the schema requires a STRING when the optional key is present. Fail-closed held. **CLOSE-PROMPT REFINEMENT:** the embedded contract now says OMIT the key entirely when there is no subclass (never null); golden deliver hash regenerated (same recorded rationale). |
| 7 (2026-07-09) | FAIL at m1 `acceptance_surface_approve`, 4 real spawns, 496s | **THE WHOLE ROLE CHAIN RAN LIVE FOR THE FIRST TIME: Dev ✓ → eval ✓ → Review ✓ → Close ✓ → real Acceptance spawn.** The live judge applied the governance kernel FAITHFULLY — it found the sentinel structurally present but refused to elevate past `partial` because the designated F5 execution artifact was unreachable, and surfaced `needs_human` (exactly the fail-closed §4.2.8 anti-pattern-#5 behavior the kernel mandates). **FRAMEWORK GAP (path frame mismatch):** the projected acceptance prompt cited the F5 evidence by its RUN-DIR-relative path while the spawned agent's CWD is the WORK repo — unresolvable from the agent's frame. Fixed: `_project_acceptance_prompt` now gives the ABSOLUTE read path (+ keeps the run-relative citation form for verdict cases) and anchors the transcripts ref; `_acceptance_evidence_abs` helper. |
| 8 (2026-07-09) | **CAMPAIGN CONTRACT COMPLETED — rc 0/10/10/0**, 8 real spawns, 662s | **THE FIRST REAL-ADAPTER CAMPAIGN EVER TO RUN END-TO-END.** sign rc 0 → run rc **10** paused `advisory_acceptance_pass_signoff` @ m1-hello (real Dev delivered `HELLO-CANARY-M1\n` byte-exact; real Review + Close + Acceptance all schema-clean; the live judge passed with the F5 artifact now REACHABLE — though its CONTENT was still thin, see the R3 B-2 correction under runs 11+) → identity-bound `ship` decision + resume → rc **10** @ m2-append (append delivered byte-exact, M1 line preserved) → second `ship` → rc **0**, `status: done`, `milestone_index 2/2`, `subsprints_run: 2`, `total_spawns: 8`. The pytest run still FAILED on ONE overreaching test assertion: it hard-indexed `scope_coverage` in the printed status line, but that field is a DEGRADABLE reporting nicety (may be absent). Test corrected to assert the stable contract (`status`/`milestone_index`/`milestones_total`) and treat scope_coverage as optional. |
| 9 (2026-07-09) | contract rc 0/10/10/0 AGAIN (649s, 8 real spawns); pytest red on a test IMPORT bug only | Steps 1-4 all passed including the corrected step-4 assertion — the completed contract REPRODUCED. The final flow-invariant block then crashed on `import audit` (wrong module name; the ledger reader is `audit_log`). Fixed to `import audit_log as audit` (the pattern the existing campaign tests use). **Run-9 artifacts verified OFFLINE against the invariant block's own checks:** `acceptance_start` ×2 (exactly one per milestone), agent-stuck diagnostics **NONE** (zero watchdog false-kills across all real spawns), `notes/hello.md` = both sentinel lines byte-exact. |
| 10 (2026-07-09) | **GREEN — 1 passed in 622s** | Full contract + ALL flow invariants asserted in one clean pytest run: sign rc 0 → rc 10 `advisory_acceptance_pass_signoff` @ m1-hello → `ship` → rc 10 @ m2-append → `ship` → rc **0**, `status: done`, 2/2 milestones, `total_spawns: 8`; `acceptance_start` ×2; agent-stuck diagnostics NONE; both sentinel files byte-exact. |
| — Codex R3 whole-scope gate | REVISE (2 blocking) | **B-1:** the close prompt's `next_subsprint` hint read `_supplied_sequence()` only — a resumed guided run (empty supplied, persisted `state.planned_sequence`) or an unanchorable sid would be steered into a premature "LAST → null" close. Fixed: supplied-OR-planned fallback + a NEUTRAL never-claim-last instruction when unanchored; 3 regression tests; golden hash UNCHANGED (main path text identical). **B-2:** the eval cmd's `grep -q` left the F5 evidence artifact EMPTY and only checked M1 — the artifact did not carry the milestone proof (runs 8-10's judge verdicts relied on the workspace reads plus a thin artifact). Fixed: the eval now `cat -n`s the ENTIRE delivered file into stdout (the F5 artifact IS the observable proof for both milestones' bars), exit gate unchanged. |
| 11 (2026-07-09) | **GREEN — 1 passed in 358s** | Full contract re-verified with the R3 fixes. The F5 artifacts now carry the ACTUAL observable proof the acceptance bars demand — m1 artifact: `1  HELLO-CANARY-M1`; m2 artifact: `1  HELLO-CANARY-M1` + `2  HELLO-CANARY-M2` (numbered full-file dump). rc 0/10/10/0, 2/2 milestones, `total_spawns: 8`, `acceptance_start` ×2, agent-stuck diagnostics NONE. |

## FROZEN VERDICT

The campaign orchestrator drives a REAL multi-milestone backlog end-to-end. Ten
runs, monotonically deeper each time; every deterministic blocker found was a
REAL defect fixed with a pinned regression test:

- **3 framework bugs/gaps fixed:** the `--repo-dir` duplicate-kwarg crash
  (campaign.py — real strict-prompt campaigns were structurally impossible),
  the un-anchorable eval cmd (driver.py `EVAL_REPO_DIR`), the bare one-line
  close prompt (driver.py self-contained close contract + golden regen), plus
  the acceptance evidence path frame fix (absolute read path).
- **3 canary-input refinements:** review layer enum, orchestrator-artifact
  exclusion + `path:line` evidence format, omit-vs-null optional field.
- **2 test bugs:** degradable `scope_coverage` hard-index; `audit_log` import.
- **Governance held at every step:** every malformed real verdict was
  fail-closed rejected, the live Acceptance judge refused to elevate without
  reachable execution evidence (§4.2.8 #5), both advisory sign-offs paused for
  identity-bound human decisions, and zero watchdog false-kills occurred across
  all real spawns (the stream-lease liveness chain validated in anger).

## Why runs 1-2 are the canary EARNING ITS KEEP, not noise

Both failures are deterministic framework defects on the real path that NO
offline/mock test could see (mock tests never pass `--repo-dir`; mock eval
cmds are cwd-independent). They are exactly the class of blocker that kept
adopters (airplat) on Control-Plane direct-drive. Each fix landed with a
pinned regression test before the next run.

## Intent-contract signature

`charter.yaml` `intent_contract.confirmed_by_human: true` was set BY THE
HUMAN OPERATOR (Rex / caoruixin) authoring this canary on 2026-07-09, per
R0 B-4. The contract's goal/standard/proof_of_done are the two sentinel
lines; Acceptance judges only against it.
