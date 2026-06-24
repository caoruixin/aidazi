# minimal-greenfield — a working aidazi consumer template

This is a **filled-in, minimal** example of what an aidazi-adopted project looks like one milestone in. It is a Type A AI agent — **"Acme Returns Bot"**, a customer-service agent that judges refund eligibility — kept deliberately tiny so you can read the whole thing.

Copy this directory as the starting skeleton for a greenfield adoption (`docs/greenfield-guide.md`), then replace the Acme-specific values with your own.

## What's here

```
minimal-greenfield/
├── AGENTS.md                              # consumer root: project id + Control Plane entry + role/on-demand refs
├── CLAUDE.md                              # one line `@AGENTS.md` — routes Claude Code into AGENTS.md
├── docs/
│   ├── current/                           # the three domain contracts + context guide + adoption state + impl-stack snapshot
│   │   ├── domain_taxonomy.md
│   │   ├── runtime_invariants.md
│   │   ├── eval_acceptance_bars.md
│   │   ├── agent_context_guide.md
│   │   ├── adoption-state.md
│   │   └── implementation-stack.md         # present-tense product tech facts (Step 4a); NOT a domain contract
│   ├── milestone_objective.md             # M1 north star (cites the closure_contract)
│   ├── sprint_objective.md                # sub-sprint 1 scope
│   ├── 10-handoff.md                      # §0 cold-start table + §1 narrative
│   ├── action_bank.md                     # live backlog (R-items + OBS-items)
│   ├── research-briefs/RB-001-refund-eligibility.md  # the signed brief (gate 1) M1 is built against
│   ├── acceptance-reports/_placeholder.md # where Acceptance verdicts land
│   └── diagnostics/failure-briefs/_placeholder.md
├── compact/_placeholder.md                # where per-sprint dev/review/acceptance prompts land
└── eval/bad_cases/_manifest.md            # the bad-case suite manifest
```

## How Claude Code and Codex enter the same entry

Both harnesses reach the **one** Control Plane entry in `AGENTS.md`, via the harness-specific root
file each one auto-loads (normative source: `aidazi/governance/context_briefing.md` §1.1):

- **Claude Code** auto-loads `CLAUDE.md`, not a bare `AGENTS.md`. The one-line `CLAUDE.md`
  (`@AGENTS.md`) imports `AGENTS.md`, so the default Control Plane entry is in context from turn one.
- **OpenAI Codex** auto-loads `AGENTS.md` directly — no `CLAUDE.md` needed.

`CLAUDE.md` only *imports* `AGENTS.md`; it never re-copies the chain (dual entry points drift).
This single wiring serves both harnesses, so they can be used alternately on the same repo. The
deterministic check is `python aidazi/engine-kit/validators/adopter_wiring_validator.py . --harness claude_code`.

## How to use it

1. Read `AGENTS.md` first as the default Control Plane entry.
2. Activate a role explicitly when you need Research / Deliver / Dev / Code Reviewer / Acceptance.
3. Follow `aidazi/docs/greenfield-guide.md` STEP 1-6, substituting your domain for Acme's.

This example is **read-only** after snapshot (per Δ-7); it's a reference, not a live project. Don't sync framework changes into it.
