---
context_budget:
  self_contained: true
---
You are activating as the Dev Agent for sub-sprint sprint-m1 (milestone
m1-hello of the real-campaign-canary).

Objective: create `notes/hello.md` containing EXACTLY one line:

    HELLO-CANARY-M1

Scope IN (deliverables):
  - `notes/hello.md` — exactly the single line `HELLO-CANARY-M1` (plus a
    trailing newline).
  - `docs/handoff.md` — a short Dev handoff: what you created, the exact file
    content, and how a reviewer verifies it (`grep -x HELLO-CANARY-M1
    notes/hello.md`).

Scope OUT (explicit non-goals):
  - Do NOT create any other file, directory, config, or tooling.
  - Do NOT add prose, headers, or metadata to `notes/hello.md` — the sentinel
    line is the entire file body.
  - Do NOT run `git push` or any network operation.

Exit criteria (observable close conditions):
  - `grep -x HELLO-CANARY-M1 notes/hello.md` exits 0.
  - `wc -l < notes/hello.md` reports 1.
  - `docs/handoff.md` exists and names the file + verification command.

Stay strictly within Scope IN. If the task cannot be satisfied as specified,
STOP and say why instead of improvising. When done, write the handoff.
