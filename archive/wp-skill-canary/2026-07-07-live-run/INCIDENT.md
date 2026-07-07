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

---

# Incident #2 — α rep2 harness crash AFTER a billed, successful decompose

**What happened.** On the resumed run (wired adopters), `nonui-milestone-rep2`'s
REAL decompose spawn SUCCEEDED — the model emitted a fenced JSON deliver-plan
verdict which passed the driver's schema validation, and the guided loop
proceeded through the mock dev/review steps — but the runner then CRASHED at the
very last step (the canned close): the harness's `SplitDeliverAdapter` shadowed
`MockAdapter`'s internal `_calls` dict with an int counter
(`AttributeError: 'int' object has no attribute 'get'`). The workspace-cleanup
`finally` then DELETED the workspace, destroying the billed spawn's evidence
(ledger, transcripts, state) before it could be collected.

**Why the offline dry-run missed it.** `SplitDeliverAdapter` was exercised only
on the live branch; the offline α path used a plain mock deliver adapter.

**Diagnostic recovery (NOT formal evidence).** The claude CLI's own session log
for the crashed workspace was preserved and is committed as
`alpha/nonui-milestone-rep2-crashed-ws/DIAGNOSTIC-claude-session-log.jsonl`
(clearly labeled — a side-channel diagnostic, not the harness evidence path).
Its final assistant message is a fenced JSON deliver-plan verdict carrying the
exact prescribed sub-sprint ids (`s1-csv-serializer`, …) — i.e. the incident-#1
wiring fix WORKED and the spawn appears fixture-conformant. It is NOT scored:
the frozen α procedure scores the harness-collected, driver-validated plan.

**Fixes (committed before any further spend).**
1. `ws_runner.SplitDeliverAdapter`: the counter no longer shadows MockAdapter
   state; the offline α dry-run now routes BOTH arms through SplitDeliverAdapter
   (decompose→inner, close→canned) so this whole path is offline-covered.
2. `run_canary._rep`: on ANY harness exception the workspace's `.orchestrator/`
   + `docs/` + runner result are SALVAGED into the evidence tree before removal
   — a billed spawn's evidence can never be destroyed again.
3. `Budget.authorized_extra`: an explicit, HUMAN-authorized launch top-up field
   (reason + authorization reference recorded in budget.json). Default 0; never
   self-granted.

**Budget position ⇒ HUMAN HALT (authorization condition #2).** α launches
spent: 4 of the frozen 8 (6 planned + 2 replacements). Completing α requires
5 more (rep2 re-run + rep3 + the 3 ui reps) = 9 total — ONE launch beyond the
frozen cap, because rep2's spent launch produced no collectible outcome through
harness fault (neither a frozen "replacement" ground nor a scoreable rep). Per
the standing authorization ("the authorized real-agent spawn or replacement
budget would be exceeded" ⇒ stop and surface), the run is HALTED pending an
explicit human top-up decision; nothing was silently extended.

*(Resolution: the human authorized +2 α launch slots (Option A, recorded in
budget.json `authorized_extra`); the run resumed consuming slot 1 for the rep2
rerun.)*

---

# Incident #3 / FROZEN OUTCOME — probe α INCONCLUSIVE (>2 adapter errors)

**What happened.** The authorized rep2 rerun (launch #5, extra slot 1) failed
with the probe's THIRD adapter-level error: the (correctly wired) deliver agent
announced it would save the verdict to `docs/plans/sprint-001__deliver-plan-
verdict.md`, was blocked by the deliver role's read-only permission mode, and
emitted a markdown-formatted plan as its final message — unparseable as the
JSON verdict. The frozen §7.4 rule fired exactly as pre-registered:
**>2 adapter-level errors in one probe ⇒ probe INCONCLUSIVE ⇒ HALT and
surface.** The harness halted before any further spend.

**Classification (why the contingency slot was NOT used).** The committed
diagnostic (`alpha/nonui-milestone-rep2-crashed-ws/DIAGNOSTIC-claude-session-
log.jsonl`) shows the IDENTICAL setup once producing a parseable fenced-JSON
verdict — so the post-fix failure is model OUTPUT-CHANNEL VARIANCE, squarely in
the authorization's prohibited list ("ordinary model variance"). Extra slot 2
(harness-fault-class only) was not consumed. No prompt was tuned, no criterion
adjusted, no unapproved run added.

**The real finding the canary surfaced (a FRAMEWORK gap, recorded as a
follow-up — NOT fixed mid-canary, which would be prompt-tuning).** The guided
decompose contract's inline prompt (driver.py `_step_decompose`) lacks the
explicit "return ONE JSON object as your final message, no prose" emission line
that the PROJECTED review/close prompt contracts carry; under the deliver
role's least-privilege read-only sandbox a cold-started agent tries to
MATERIALIZE the plan as a doc (its authoring discipline) and the inline
fallback is nondeterministically parseable (1 parseable / 3 markdown across
the four wired+unwired real decompose spawns).

**Final probe accounting.** α: INCONCLUSIVE — 5 launches spent of 10
authorized (2 harness-defect errors [fixed], 1 truncated launch, 1 evidence-
lost successful launch [harness fault, fixed], 1 model-variance error);
0 scoreable repetitions. β: NOT RUN (0 of 3+2). γ: NOT RUN (0 of 6+2).
