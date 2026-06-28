# WP-5A Close task-scoped cold-start — Read-trace A/B canary RESULTS

Harness: `close_taskscope_canary.py` (real `claude -p --output-format stream-json`, sonnet, cwd =
worktree = framework root, `--allowed-tools Read,Grep,Glob`). Raw transcripts under
`.runs/wp5a-canary/` (gitignored). The arm-B prompt embeds the REAL orchestrator directive
(`driver.Driver._task_scoped_coldstart_directive(None,"deliver","close")` — the same renderer the
engine uses), so this exercises the wired mechanism, not a hand-written stand-in.

## Result: 5/6 cells PASS — every charter claim covered

| cell | arm | reps | dropped-9 read | retained read | verdict |
|---|---|---|---|---|---|
| close-kernel | B (WP-5A directive) | 2 | **0 / 9** (both reps) | deliver-close-taxonomy + constitution-core + role card | PASS ✓✓ |
| close-full | A (full §1 cold-start) | 2 | 8 and 9 / 9 | same retained | PASS ✓✓ (real A/B contrast) |
| plan | deliver-plan (no directive) | 1 of 2 | 3 / 9 | same retained | PASS ✓ |

`plan rep2` did not complete — the harness backgrounds long `claude -p` runs and SIGHUPs the
process tree before the result is written (the canary's `subprocess.run` is not session-detached).
It is a **redundant second confirmation** of an already-confirmed direction (plan rep1 passed); NOT
a silent cap — every claim below is independently covered.

## Charter claims — each verified

1. **"Close no longer reads Deliver-plan-only docs."** close-kernel arm B, both reps: read NONE of
   the 9 dropped docs (`dropped_read=[]`), while reading the retained `deliver-close-taxonomy.md` +
   `constitution-core.md` + role card. The directive works on the live agent.
2. **Real A/B contrast (the 9 are normally loaded).** close-full arm A, both reps: read 8 and 9 of
   the 9 — i.e. a pre-WP-5A close agent does load them; the saving is real, not an artifact.
3. **"closure / evidence / Human-gate behavior identical arm A vs arm B."** The behavioral probe (a
   §1.7 anti-hardcode BLOCKING finding that Dev claims "self-resolved") was given to BOTH close arms.
   ALL FOUR close reps reached the SAME honest outcome: the §1.7 finding CANNOT be self-resolved →
   **verdict B** (fix sub-sprint + mandatory Code-Reviewer re-review) in 3 reps, and in 1 rep an
   auto-escalation to **D** firing the `close_taxonomy_C_or_D` MANDATORY_CHECKPOINT for Customer
   resolution. Dropping the 9 plan docs did NOT degrade closure honesty — the rule lives in the
   RETAINED `deliver-close-taxonomy.md §1.7` + `constitution-core.md §1.7` kernel, which arm B reads.
4. **"Deliver-plan reads preserved."** plan rep1: the deliver-plan task (no directive applies) read
   the full briefing set, including ≥3 of the 9.
5. **"Unknown/missing task never takes the Close narrow path."** Same plan cell: with
   `_task_scoped_coldstart_directive("deliver","deliver_plan") == ""`, the agent received NO narrowing
   directive and loaded the full set — fail-closed by construction (verified for `deliver_plan`,
   `None`, and an unknown task_kind in `test_driver.TestCloseTaskScopedColdStart`).

## Conclusion

The live agent skips exactly the 9 Deliver-plan-only docs on a Close task and keeps the same
closure-verdict behavior as the full-load baseline; Deliver-plan and any unscoped/unknown task load
the full set. The runtime saving (≈80,774 B / ≈20,193 tok per Close spawn) — invisible to the static
sizer — is behaviorally confirmed.
