# Live-run incident record — α slot 1 harness defect (2026-07-07)

**What happened.** The first α repetition (`nonui-milestone-rep1`) and its first
replacement (`-r2`) both failed with ADAPTER-LEVEL errors: the real deliver
(decompose) agent returned a **markdown-formatted plan instead of a JSON
deliver-plan verdict** (`claude_code result field was not a JSON verdict`); `-r2`
additionally attempted a file write (denied under the deliver role's read-only
permission mode) before emitting the markdown plan inline.

**Root cause (harness defect, not a model/framework defect).** The scratch adopters
built by the canary harness were vendored (`vendor-framework.sh`) but NOT wired:
the documented onboarding step — root `AGENTS.md` (copied from `aidazi/AGENTS.md`,
placeholders filled) plus root `CLAUDE.md` containing `@AGENTS.md` — was missing,
so the spawned agent's cold-start chain (governance kernel → role card →
verdict-schema discipline) never loaded. Without it the deliver agent does not
know the deliver-plan verdict must be emitted as a bare JSON final message.
This is the exact adopter-wiring class the framework's own
`adopter_wiring_validator` exists to catch (§1.1 root-file wiring rule).

**Action taken (within the authorized scope: "canary harness bugs are not Human
intervention points … fix them, rerun and continue").**

1. The run was STOPPED as soon as the defect was diagnosed — before replacement
   spawn #2 (`-r3`, already launched) could complete and push the probe past the
   frozen `>2 adapter errors ⇒ INCONCLUSIVE` boundary.
2. `-r3`'s launch was already SPENT (recorded in `budget.json`); it produced no
   outcome and is NOT re-run — the frozen budget allows ≤2 replacement spawns per
   probe and both were launched for this slot. An operator marker
   (`alpha/nonui-milestone-rep1-r3/`) resolves the slot as a FAILED repetition.
3. The harness was fixed (`run_canary.py _build_ws` now completes the documented
   root-file wiring for every scratch adopter) and committed before resuming.

**Frozen-contract accounting after the incident.**

- α repetition slot 1 (nonui fixture) = FAIL (conservative: no schema-valid plan
  within its budget). The nonui fixture therefore needs BOTH remaining
  repetitions to pass to reach the frozen ≥2/3 threshold.
- α replacement budget: exhausted (2/2 launched). Any FURTHER adapter-level error
  in probe α is the 3rd ⇒ INCONCLUSIVE ⇒ HALT, per the frozen abort rules.
- α launch ceiling: 3 spent + 5 remaining planned = 8 = exactly the frozen
  6 planned + 2 replacements. The budget ledger's pre-launch cap enforces this.
- β/γ budgets untouched.
- NO frozen pre-registration file, fixture, threshold, repetition count,
  ordering, or scoring rule was changed. No criteria were adjusted post-hoc.
