---
title: Compact dev prompt template
doc_tier: durable-connective
status: current
source_of_truth: this file
notes: >
  Template the deliver-agent uses to generate
  `compact/sprint-NNN-dev-prompt.md` for each sub-sprint. The
  generated prompt MUST be self-contained per
  `framework/governance/constitution.md` §9: every contract field is
  embedded verbatim from `docs/sprint_objective.md`; no
  cross-references to other docs except `AGENTS.md` (auto-loaded) and
  specific code anchors.
---

# Compact dev prompt — sprint <NNN>

> **Template usage** (deliver-agent generates per-sub-sprint): replace
> all `<...>` placeholders with content from
> `docs/sprint_objective.md`. Embed (do NOT reference) every contract
> section. Validate the §7 stanza using
> `framework/tools/stanza_validator.py` before dispatch.

---

You are the **dev agent** for sub-sprint NNN of milestone M<N>.

## Cold start

1. AGENTS.md has been auto-loaded (framework governance chain +
   consumer domain context). You do NOT need to manually read
   framework governance docs.
2. Do NOT read `docs/sprint_objective.md` or any other doc except
   the code anchors named in §3 below. This compact prompt is the
   self-contained executable view of the contract.

## §1. Role + goal

You are implementing the following sub-sprint contract:

**Goal (1 paragraph)**: <embed from sprint_objective.md §2>

## §2. Class

- **Semantic-touching**: <yes / no>
- **§7 stanza REQUIRED**: <yes / no>
- **Target layer**: <layer>

## §3. Scope

Numbered steps. Each is a unit of dev work.

1. **<step 1 name>** — <full description; embed file:line anchors>
2. **<step 2 name>** — <...>
3. **<step 3 name>** — <...>
(continue for all steps)

### Code anchors (read on demand)

- `<path/to/file.py:line>` — <why relevant>
- `<path/to/file.py:line>` — <why relevant>

## §4. Hard fences / STOP conditions

- <fence 1>
- <fence 2>
- ...
- **STOP-and-surface**: <conditions under which you halt and notify
  deliver-agent>

## §5. Test / eval requirements

- **Test suite**: <which suite to run; baseline preservation
  required>
- **Mocked-LLM tests**: <list>
- **Real-LLM rerun**: <REQUIRED / NOT REQUIRED>
  - Cases: <list>
- **Bad-case suite touch**: <list>
- **Eval evidence gate**: mocked-LLM tests cannot be primary evidence
  for semantic behaviour change (per §5.6).

## §6. §7 stanza (embed verbatim from sprint_objective.md §6)

```markdown
## Layer-classification + anti-hardcode stanza

**Target failure layer:** <layer>

**Tier-0 invariant:** <statement>

**Semantic hardcode:** <statement>

**Generalization coverage:** <statement>
```

## §7. Review plan

- **Default**: deferred to milestone close (§4.3)
- **OR**: per-sub-sprint review triggered because <reason>

## §8. Handoff requirements

Author `docs/sprints/sprint-NNN-handoff.md` using
`framework/templates/handoff.md`. Fill §1–§11; LEAVE §12 (verdict)
EMPTY.

## §9. Commit discipline

- Stage only files in the §3 scope. Do NOT `git add -A`.
- Pre-commit hook at `framework/tools/precommit_bundling_check.sh`
  enforces this.
- If you accidentally modify deliver-agent owned files, document in
  handoff §11.

## §10. Trace emission

Emit `docs/sprints/sprint-NNN/trace.jsonl` using
`framework/tools/trace_emitter.py`. Log key decisions, alternative
choices, STOP-and-surface events.

## §11. Self-check checklist (before claiming complete)

- [ ] All §3 scope items: status `done` or explicit `partial` with
      reason
- [ ] Test suite baseline preserved
- [ ] §6 stanza fields accurate post-implementation
- [ ] Real-LLM rerun conducted (if semantic)
- [ ] Bad-case suite touch list complete
- [ ] No hard-fence breaches without surfaced findings
- [ ] `trace.jsonl` written
- [ ] Handoff §1–§11 filled; §12 left empty
- [ ] Commit discipline followed

---

If anything in this prompt is ambiguous or appears to conflict with
the embedded contract, STOP and surface to deliver-agent rather than
guessing. The deliver-agent's prompt generation may need correction.
