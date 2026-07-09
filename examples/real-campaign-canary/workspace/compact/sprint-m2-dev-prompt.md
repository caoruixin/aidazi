---
context_budget:
  self_contained: true
---
You are activating as the Dev Agent for sub-sprint sprint-m2 (milestone
m2-append of the real-campaign-canary).

Objective: append EXACTLY one line to the existing `notes/hello.md`:

    HELLO-CANARY-M2

Scope IN (deliverables):
  - `notes/hello.md` — after your change it contains exactly two lines, in
    this order: `HELLO-CANARY-M1` then `HELLO-CANARY-M2` (plus a trailing
    newline). The M1 line must be byte-identical to before.
  - `docs/handoff.md` — replace/update with a short Dev handoff: what you
    appended and how a reviewer verifies it (`grep -x HELLO-CANARY-M2
    notes/hello.md` and the M1 line preserved).

Scope OUT (explicit non-goals):
  - Do NOT create any other file, directory, config, or tooling.
  - Do NOT modify or reorder the existing M1 line.
  - Do NOT run `git push` or any network operation.

Exit criteria (observable close conditions):
  - `grep -x HELLO-CANARY-M1 notes/hello.md` exits 0 (preserved).
  - `grep -x HELLO-CANARY-M2 notes/hello.md` exits 0 (appended).
  - `wc -l < notes/hello.md` reports 2.
  - `docs/handoff.md` describes the append + verification commands.

Stay strictly within Scope IN. If `notes/hello.md` is missing (m1 did not
deliver), STOP and say so instead of creating it from scratch. When done,
write the handoff.
