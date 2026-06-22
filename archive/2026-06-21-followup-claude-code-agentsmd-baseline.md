# Follow-up — Claude Code does not auto-load AGENTS.md (Default-Full baseline gap)

**Status:** CLOSED 2026-06-22 by R1 (standalone increment; see "Resolution" below) ·
**Priority was:** HIGH (silent absence of the always-load governance chain for one
harness × filename combination)
**Origin:** Quick-Fix Lane Commit 0 / QF-0 —
[Full cold-start baseline evidence](2026-06-21-full-coldstart-baseline-evidence.md)
**Boundary:** this was a **standalone** follow-up — **not** part of the Quick-Fix Lane
runtime commits (Commit 1–3), and R1 was delivered as its own increment that touches no
Quick-Fix contract/runtime file.

## Resolution (R1, 2026-06-22)

Delivered as a single standalone increment:

1. **Normative rule** — `governance/context_briefing.md` §1.1 ("Harness root-file wiring")
   is now the single normative source: Claude Code ⇒ root `CLAUDE.md` importing the
   same-root `@AGENTS.md`; Codex ⇒ `AGENTS.md`; Cursor ⇒ its own `.cursor/rules` (a bare
   `AGENTS.md` is not Cursor wiring). Step-4 and the §3 Context-Pack prompt now defer to §1.1.
2. **Template / onboarding / example** — the `AGENTS.md` preamble drops the "interchangeable"
   wording for harness-specific wiring; `ONBOARDING.md` Step 6.1a scaffolds a one-line root
   `CLAUDE.md` (`@AGENTS.md`) read-before-write + diff-confirm, never overwriting an existing
   brownfield `CLAUDE.md`; Step 8 runs the validator as part of the GREEN gate;
   `examples/minimal-greenfield/CLAUDE.md` (`@AGENTS.md`) + README explain the dual entry.
3. **Deterministic validator** — `engine-kit/validators/adopter_wiring_validator.py`
   (+ 45 tests) checks same-root wiring with harness target resolution
   (`--harness` > a single contradiction-free declaration > unspecified; contradicting
   persistent sources FAIL; unspecified WARNs exit 0).
4. **Real harness proof** — `examples/claude-code-full-wiring/verify-full-coldstart.sh`
   and [the 2026-06-22 evidence](2026-06-22-claude-code-default-full-wiring-evidence.md)
   show, on real Claude Code 2.1.170, the positive (canary loaded via `CLAUDE.md`→`@AGENTS.md`)
   and negative control (bare `AGENTS.md` not auto-loaded), reproduced twice.

The standing constraint below is lifted: a **correctly wired** Claude-Code adopter (validated
by the tool) now has a guaranteed Default-Full baseline; an unwired one is caught deterministically.

### Legacy adopters MUST run the validator (closure caveat)

R1 fixes the wiring **going forward** — the scaffold, template, and worked example now produce a
root `CLAUDE.md`. It does **not** retroactively wire repos that onboarded **before** R1: a legacy
adopter whose root still holds only a bare `AGENTS.md` (no `CLAUDE.md`) keeps the silent
Default-Full gap until remediated. **Every existing adopter must run the validator against its
root and remediate any FAIL** before relying on the Default-Full baseline under Claude Code:

```bash
python aidazi/engine-kit/validators/adopter_wiring_validator.py <adopter-root> --harness claude_code
```

On FAIL, add the one-line root `CLAUDE.md` (`@AGENTS.md`) per §1.1 (read-before-write +
diff-confirm; if a `CLAUDE.md` already exists, append the import — never overwrite or duplicate the
chain), then re-run until PASS. This caveat is the reason the follow-up is closed as *"correctly
wired adopters guaranteed; unwired ones deterministically caught"* rather than *"all adopters
guaranteed"*.

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
