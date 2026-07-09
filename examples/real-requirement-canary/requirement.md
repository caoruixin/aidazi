# Customer requirement — requirement-canary hello notes

Deliver a `notes/hello.md` file in the repository, in two independently
verifiable steps:

1. **First milestone** — create `notes/hello.md` containing EXACTLY one line:

   ```
   HELLO-REQ-M1
   ```

2. **Second milestone** — append EXACTLY one line to the same file, preserving
   the first line unchanged, so the file becomes exactly:

   ```
   HELLO-REQ-M1
   HELLO-REQ-M2
   ```

## Constraints (scope)

- ONLY `notes/hello.md` and `docs/handoff.md` may be created or changed (the
  handoff documents each step for review).
- Definition of done per milestone: the exact sentinel line(s) are observable
  via `cat notes/hello.md` — no interpretation, byte-exact.
- Keep the plan MINIMAL: two milestones, ONE sub-sprint each is sufficient;
  do not invent extra work.
