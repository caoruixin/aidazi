---
title: Worked example instance (Δ-7)
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 6KB
notes: >
  Δ-7 KEEP per v4-plan §4.1. Defines the rules for worked-example references
  in examples/ — read-only after first snapshot; fold-back direction rules;
  snapshot naming convention. Worked examples are read-only because they're
  evidence-of-what-was, not evidence-of-what-is.
---

# Worked example instance (Δ-7)

The framework ships `examples/` worked instances (csagent-reference / hermes-reference / fortunes-reference-placeholder / minimal-greenfield) so adopters can see "what a filled-in framework looks like." This Δ defines the rules these worked examples follow — read-only after first snapshot, snapshot dating, fold-back direction.

## §1 Worked examples are read-only after first snapshot

After `examples/<ref>/` is first populated, the directory is **read-only**. Subsequent updates to the underlying real project (csagent, hermes-autoloop, etc.) do NOT sync upstream into the worked example.

**Why**: the worked example's value is its concreteness — it shows what was true on a specific date in a specific donor project. If it silently tracks the donor, readers cannot tell if discrepancies between example and framework spec are "the framework evolved" or "the donor evolved" or "both, and they no longer align."

The read-only rule is the same lifecycle as `doc_category: intermediate` per Δ-4 — frozen at creation.

## §2 Snapshot dating convention

When a new snapshot is needed (existing snapshot is judged load-bearing-out-of-date by framework maintainer), build a NEW dated snapshot ALONGSIDE the old:

```
examples/
  csagent-reference/                    # first snapshot
  csagent-reference-2027-Q2-snapshot/   # second snapshot
  csagent-reference-2028-Q1-snapshot/   # third
```

The old snapshot stays. The new snapshot is independently authored, with cross-references from new to old where relationships hold.

`minimal-greenfield/` is a special case — it's a WORKING consumer template (not a donor snapshot). Updates to it are permitted as the framework's minimal-template-of-record; it carries `doc_category: live` rather than intermediate.

## §3 Fold-back direction rules

A worked example's value flows DOWNSTREAM (adopters read it). It does NOT flow upstream (lessons from the example do NOT update the framework directly):

- **Adopter reads worked example to learn shape**: OK; primary use case.
- **Adopter copies worked example structure into their own repo**: OK; that's the point.
- **Adopter files lessons inspired by worked example**: OK; the lesson flows through `process/fold-back-protocol.md` cadence, not the worked example.
- **Framework maintainer edits the worked example mid-cycle**: forbidden (read-only rule).
- **Framework maintainer cites the worked example as evidence in a Δ revision**: OK; cite the specific dated snapshot.

## §4 What goes in a worked example

A worked example populates a snapshot of an adopter's Phase 1-5 outputs:

- `decisions/` — the adopter's actual Δ-3 8-decision choices.
- `discovery/` — the adopter's Phase 1-2 outputs (business need, product/service design).
- `m-eval/` — the adopter's M-Evaluation instantiation (CaseSpec / 4-tier / judge config).
- `m-trace/` — the adopter's trace contract instantiation.
- `m-autoloop/` — (Type A only) Auto Loop usage.
- `runtime-skeleton/` — the adopter's Δ-6 Type A runtime skeleton filled in (or Type B SOP runner, etc.).
- `delivery-loop/` — (if Δ-18 orchestrator adopted) charter + orchestrator run examples.
- `timeline.md` — lifecycle date stamps for the adopter's history.

The exact list per-adopter varies by track and by what's load-bearing for the framework to demonstrate.

## §5 Build triggers (for deferred snapshots)

Per build plan §5: `examples/csagent-reference/` and `examples/hermes-reference/` are populated on a trigger basis (not at v4 launch). The triggers live as `_build-trigger.md` files in the respective directories.

When a trigger fires:
1. The framework maintainer authors the snapshot in a coding-agent session per the trigger doc's build prompt.
2. The directory is named `<adopter>-reference-YYYY-MM-DD/` per §2.
3. Read-only after first snapshot per §1.

## §6 Type C placeholder

`examples/fortunes-reference-placeholder/` is a placeholder for Type C demo lifecycle. Populated when:
- A Type C demo adopter completes their first milestone close.
- Their lifecycle is documentable as evidence for the framework's Type C support.

Until populated, the placeholder is a single `_placeholder.md` file explaining the deferral.

## §7 Cross-references

- `process/fold-back-protocol.md` §3 — examples snapshot refresh is one of the optional fold-back sub-sprint outputs.
- `docs/greenfield-guide.md` STEP 5+ — worked examples referenced as inspiration; adopters do NOT copy them verbatim, they extract patterns.
- `docs/two-loops-explainer.md` — when worked examples demonstrate both Auto Loop + Delivery Loop, the §1.7-E naming discipline applies.

## §8 What this Δ does NOT cover

- Domain-specific content of any worked example — those are per-adopter; the worked example IS the content.
- How adopters consume worked examples — `docs/greenfield-guide.md` + `docs/brownfield-guide.md`.

## §9 Editing this doc

Process-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The read-only-after-snapshot rule + dated-snapshot convention are stable framework vocabulary. Adding a new worked-example category (e.g., a "patterns library" extracted from multiple examples) requires fold-back deliberation.

---

End of Δ-7 Worked example instance.
