# Follow-up — Claude Code does not auto-load AGENTS.md (Default-Full baseline gap)

**Status:** OPEN (raised 2026-06-21) · **Priority:** HIGH (silent absence of the
always-load governance chain for one harness × filename combination)
**Origin:** Quick-Fix Lane Commit 0 / QF-0 —
[Full cold-start baseline evidence](2026-06-21-full-coldstart-baseline-evidence.md)
**Boundary:** this is a **standalone** follow-up. It is **not** part of the Quick-Fix
Lane runtime commits (Commit 1–3) and must not be folded into them.

## Observation

Per the official Claude Code documentation (`code.claude.com/docs/en/memory`,
confirmed 2026-06-21), Claude Code auto-loads **`CLAUDE.md`** (and `CLAUDE.local.md`)
at cold-start, and does **not** auto-load `AGENTS.md`. To use `AGENTS.md` under Claude
Code the project must have a `CLAUDE.md` that imports it (`@AGENTS.md`).

The framework, however, ships its root governance entry as `AGENTS.md`:

- `AGENTS.md` (the consumer template) **preamble**: "Copy it to your adopter repo's
  root as `AGENTS.md` (or `CLAUDE.md`, or `.cursor/rules`)" — it presents `AGENTS.md`
  as a first-class option for any harness.
- The worked example ships `examples/minimal-greenfield/AGENTS.md` (no `CLAUDE.md`).
- `governance/context_briefing.md` §1 step 4 and `AGENTS.md` §2 assume the
  `@`-included always-load governance chain (`constitution.md`, `doc_governance.md`,
  `context_briefing.md`) is in context at cold-start.

**Consequence:** a Claude Code adopter who installs the root file as `AGENTS.md`
(the path the worked example demonstrates), with no `CLAUDE.md`, gets **none** of the
always-load governance chain auto-loaded at session start. The Default-Full baseline
the framework assumes is silently **not in effect** for that adopter — the session
starts with no constitution, no doc-governance, no context-briefing until something
explicitly references them.

## Why it is HIGH priority (not merely cosmetic)

The whole Default-Full posture — §1.7 forbidden list, role boundaries,
MANDATORY_CHECKPOINTS awareness, the cold-start reading discipline — depends on the
always-load chain being present from the first turn. Its **silent** absence is worse
than a hard error: the agent behaves as if ungoverned while everyone assumes Full
governance. Unlike Codex (auto-loads `AGENTS.md`) and Cursor (auto-loads
`.cursor/rules`), Claude Code + a literal `AGENTS.md` root file is the one common
combination where the assumption fails quietly.

## Scope (where the gap does / does not bite)

- **Bites:** Claude Code, root memory file named `AGENTS.md`, no `CLAUDE.md` that
  imports it.
- **Does not bite:** Claude Code with root `CLAUDE.md` (or a `CLAUDE.md` containing
  `@AGENTS.md`); OpenAI Codex (auto-loads `AGENTS.md`); Cursor (auto-loads
  `.cursor/rules`).
- **Does not affect the Quick-Fix Lane:** the QF lane's out-of-tree ephemeral bundle
  ships its own `CLAUDE.md`, which Claude Code does auto-load; QF cold-start control
  is therefore independent of this gap.

## Proposed resolution (when picked up — not in this series)

1. **Onboarding wizard (`ONBOARDING.md` Step 6.1):** when the adopter's Dev/primary
   harness is Claude Code, install the root entry as `CLAUDE.md` (or generate a
   `CLAUDE.md` whose first line is `@AGENTS.md`), not a bare `AGENTS.md`.
2. **Template + briefing wording:** the `AGENTS.md` consumer-template **preamble**
   (where the root-filename guidance lives) and `context_briefing.md` §1 state the
   harness-specific root-filename requirement explicitly (Claude Code ⇒ `CLAUDE.md` or
   a `CLAUDE.md` that imports `AGENTS.md`; Codex ⇒ `AGENTS.md`; Cursor ⇒
   `.cursor/rules`).
3. **Worked example:** add `examples/minimal-greenfield/CLAUDE.md` (one line:
   `@AGENTS.md`) so the example is correct under Claude Code as well as Codex. (Cursor
   loads neither `AGENTS.md` nor `CLAUDE.md`; it would additionally need its own
   `.cursor/rules` shim.)
4. **Optional check:** a structural lint that, for a Claude-Code-bound adopter, fails
   if the root has `AGENTS.md` but no `CLAUDE.md`/`@AGENTS.md`.

## Standing constraint until closed

Until this follow-up is resolved or disproven, **no framework doc may state that the
Claude Code adopter's Default-Full baseline is guaranteed.** The Quick-Fix Lane docs
honor this by scoping their Full-baseline claims to "a correctly wired adopter" and
pointing here.

---

End of follow-up.
