# minimal-greenfield — a working aidazi consumer template

This is a **filled-in, minimal** example of what an aidazi-adopted project looks like one milestone in. It is a Type A AI agent — **"Acme Returns Bot"**, a customer-service agent that judges refund eligibility — kept deliberately tiny so you can read the whole thing.

Copy this directory as the starting skeleton for a greenfield adoption (`docs/greenfield-guide.md`), then replace the Acme-specific values with your own.

## What's here

```
minimal-greenfield/
├── AGENTS.md                              # consumer root: project id + @-include chain + ledger paths
├── docs/
│   ├── current/                           # the three domain contracts + context guide + adoption state
│   │   ├── domain_taxonomy.md
│   │   ├── runtime_invariants.md
│   │   ├── eval_acceptance_bars.md
│   │   ├── agent_context_guide.md
│   │   └── adoption-state.md
│   ├── milestone_objective.md             # M1 north star (cites the closure_contract)
│   ├── sprint_objective.md                # sub-sprint 1 scope
│   ├── 10-handoff.md                      # §0 cold-start table + §1 narrative
│   ├── action_bank.md                     # live backlog (R-items + OBS-items)
│   ├── research-briefs/_placeholder.md    # where signed briefs land
│   ├── acceptance-reports/_placeholder.md # where Acceptance verdicts land
│   └── diagnostics/failure-briefs/_placeholder.md
├── compact/_placeholder.md                # where per-sprint dev/review/acceptance prompts land
└── eval/bad_cases/_manifest.md            # the bad-case suite manifest
```

## How to use it

1. Read `AGENTS.md` first (same as any role session would).
2. Read the three domain contracts in `docs/current/` — these are what make the framework about *your* domain.
3. Follow `aidazi/docs/greenfield-guide.md` STEP 1-6, substituting your domain for Acme's.

This example is **read-only** after snapshot (per Δ-7); it's a reference, not a live project. Don't sync framework changes into it.
