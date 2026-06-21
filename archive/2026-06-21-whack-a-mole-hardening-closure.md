# Closure record — adopter-port "whack-a-mole" cluster vs. the latest framework

**Date:** 2026-06-21
**Branch:** `v2-loop-engine` (committed, **not pushed**)
**Fix commits:** `7023307` (Driver) · `f1f0e9d` (Campaign)
**Verification:** Codex `gpt-5.5` reasoning=high, 5-round adversarial review → **APPROVE**; 600 tests green.

---

## 1. Question investigated

When an adopter applied an OLDER version of this framework to a new app, they hit a
recurring failure cluster and patched it locally:

> 每次重建 sprint-001 → 上一轮修复不一定保留 → Reviewer 又在邻近位置发现 P1 → 打地鼠.
> Convergence path they used: 冻结基线 → 共享 validators → 明确 TI-6 fail-closed ingress →
> 解决输入输出可变性 → 统一 `Objection.from_dict` → Code Review 与 Acceptance 全过。

Does the **latest** framework still have these problems?

## 2. Method

Three parallel source-grounded audits (iteration/rebuild model; validators &
deserialization; fail-closed ingress), each rendering a verdict with `file:line`
evidence, then direct re-verification of every actionable finding before editing.
Fixes were gated through Codex `gpt-5.5` high (the standard aidazi verification gate).

## 3. Conclusion — most of the cluster is already handled

| Reported symptom | Latest framework | Action |
|---|---|---|
| Rebuild loses fixes → whack-a-mole | **Absent** — working tree frozen across rounds (ingress runs once; auto-fix re-entry edits in place; milestone N+1 builds forward); dry-stop uses real finding identity (`new_finding_keys`) | none |
| Freeze baseline / incremental fix | **Already the design** | none |
| Shared validators | Exist (`validators/charter_validator.py`, `stanza_validator.py`); finding parse already canonical (`Driver._finding_keys` / `_worst_severity`, single severity authority `loop_controller.severity_rank`) | none |
| TI-6 fail-closed ingress | **Already fail-closed** at the Driver ingress + verdict-admission layers (`_spawn` → `gate_hard_fail`; routing-critical fields are schema `required`+`enum`) | none |
| 统一 `Objection.from_dict` (I/O variability) | Canonical at the Driver tier; **gap at the Campaign tier** | Fix 2 |

Two **real residual defects** remained, both fixed:

### Fix 1 — Driver: fix-round Dev prompt omitted the Reviewer findings (`7023307`)

The auto-fix re-entry (`_handle_fix_required` → `_step_dev`) re-dispatched the
byte-identical plan projection (`_project_dev_prompt`) with **no statement of which
findings to fix** — a violation of `process/delivery-loop.md §4.4`
("`spawn_deliver_plan_fix` … with review findings as input") and a latent
whack-a-mole *enabler* (the tree is preserved, but Dev is invited to re-derive rather
than target the reported defect). `_fix_round_guidance()` now injects the findings
(id/severity/layer/evidence/rationale) as an incremental "fix THESE in the EXISTING
code" brief when `fix_round > 0`, sourced from the persisted `state.last_verdict`
(resume-safe), gated on `decision == "fix_required"`. Initial prompt byte-identical.

### Fix 2 — Campaign: plan/state were unvalidated ingress (`f1f0e9d`)

`campaign-plan/-state.schema.json` existed but were **never loaded at runtime**.
`_check_state_consistency()` now adds, fail-closed: schema validation + state↔plan
`campaign_id` binding + cursor-range + **presence-backed** cursor/ledger resume
integrity (every milestone/sub-sprint the cursor PASSED must have ≥1 recorded unit) +
status rules (`done` only at the exhausted boundary; `paused` only inside a milestone).

## 4. The key diagnostic finding (the reason this took 5 rounds)

Codex correctly pushed for cross-milestone resume-integrity validation. My first
implementation read milestone **completion** from a unit's `final_state`
(advance/done). Dumping the actual persisted ledger disproved that model:

> An advisory-acceptance milestone legitimately **ships to `done` while its terminal
> unit stays `final_state:"halted"`** — the pause record is never rewritten. Final
> persisted state: `cursor.milestone_index=1, status=done, units=[{m1/sprint-001,
> final_state:"halted"}]`.

So "completion" is **not encoded in the ledger**. A completion check false-rejected
two real e2e flows (`test_advisory_acceptance_halt_then_ship_to_done`,
`test_two_milestones_each_gated_by_their_own_acceptance`), and the same class bit the
`ACT_ADVANCE_SUBSPRINT` (accepted `review_out_of_scope`) and `deliver_followup`
cursor advances. **Resolution: validate PRESENCE, not completion** — you cannot have
advanced past a milestone/sub-sprint that never ran, but you must not assert *how* it
finished. This closes the silent-skip hole without breaking acceptance-gated flows.

**Accepted residual (documented, not a bug):** a hand-fabricated unit record can
satisfy presence — no worse than tampering `status` directly, and there is no safe
completion signal in the ledger that preserves the halted-but-shipped acceptance unit.
Audit-ledger replay (`advance_milestone`/`campaign_milestone_done`) could prove
completion in principle, but making resume depend on audit replay is a separate design.

## 5. Codex review trajectory (5 rounds)

1. **CHANGES-REQUIRED** — confirmed Fix 1 correct; Fix 2 was shape-only (P1) + a test gap (P2).
2. **CHANGES-REQUIRED** — confirmed P2 tests; range check still admitted an evidence-free boundary cursor.
3. **CHANGES-REQUIRED** — wanted skipped-prefix + terminal `done`/`paused` evidence.
4. **CHANGES-REQUIRED** — confirmed the empirical false-reject; one residual P1 (current-milestone strict count had the same flaw); approved everything else.
5. **APPROVE** — no blocking findings.

## 6. Status & follow-up

- 600 tests pass (orchestrator 327, +18 new: 4 driver, 14 campaign).
- **Not pushed** (per the owner's instruction).
- Deferred (separate follow-up): wiring the shared charter validator into the Driver
  boundary — see `archive/2026-06-21-followup-shared-charter-validator.md`. Not a live
  defect (`run_loop.enforce_charter_for_real_run` already blocks real runs).
