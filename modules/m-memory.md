---
title: M-Memory module — Loop Memory (substrate)
doc_tier: module
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-16
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 14KB
notes: >
  M-Memory module spec — Loop Memory, the institutional-memory SUBSTRATE (NOT a
  third loop). Cross-loop experience persisted as md files; read at ingress,
  written at close; feeds the Auto Loop (Concept 1) + the Delivery Loop (Concept 2)
  + fold-back. This is the NORMATIVE source-of-truth for the memory-entry contract
  + lifecycle; schemas/memory-entry.schema.json validates the entry front-matter.
  implementation_status: IMPLEMENTED — the schema exists AND
  engine-kit/memory/memory_store.py realizes the read/write/maturity-promote
  contract (select/load_index read; write_entry/record_observation write; L1→L2
  maturity-promote; schema-conformant front-matter; anti-gaming guard_entry)
  (plan §4.4 KIT, P3/P5). Reuses
  lessons/, templates/lessons-learned-template.md, Δ-9 OBS triage L1/L2,
  fold-back, and the Auto Loop §3.3 human-approval rule. HARD (Constitution §1.7):
  store generalizable heuristics, NOT case-specific input→output. Named distinct
  from Auto Loop / Delivery Loop (§1.7-E).
---

# M-Memory module — Loop Memory

The M-Memory module defines **Loop Memory**: the institutional-memory SUBSTRATE that persists cross-loop experience as markdown files, read at loop ingress and written at loop close. It is the memory底座 (foundation) for the framework's self-evolution: lessons learned in one loop become context injected into the next.

**Loop Memory is NOT a third loop.** Per the v2-loop-engine plan §2 glossary and Constitution §3.7, there are exactly two loops — the **Auto Loop** (Concept 1; agent self-improvement; `modules/m-autoloop.md`) and the **Delivery Loop** (Concept 2; team delivery; `process/delivery-loop.md`). Loop Memory is the SUBSTRATE both loops read from and write to; it is not itself a loop. Naming it as a loop is a Constitution §1.7-E breach (§7 below).

This module is the **normative source-of-truth** for its concern. The artifacts that back it:
- `schemas/memory-entry.schema.json` — validates the front-matter of each `memory/entries/<id>.md`.
- `engine-kit/memory/memory_store.py` — the reference implementation of this contract (§10).

**Implementation status: IMPLEMENTED.** The entry schema exists, the spawn-payload `memory_injected[]` hook exists in the Audit Spine (`modules/m-audit.md` §3.4), and `engine-kit/memory/memory_store.py` realizes the `engine-kit/memory/` read/write/maturity-promote contract: the READ path (`select(scope)` deterministic tag/scope match + `load_index`), the WRITE path (`write_entry` / `record_observation`, deduplicating by `key`), and the maturity-promote rule (L1→L2 at `occurrences ≥ 2` OR human-flag), all emitting schema-conformant front-matter and gated by the always-on anti-gaming `guard_entry` (plan §4.4 KIT; P3 read/write, P5 full feedback). This module remains the normative source-of-truth for the contract that implementation realizes (plan §1 conflict rule: if module and kit disagree, the kit is the bug).

## §1 The substrate — what Loop Memory is and is not

### §1.1 What it is

Cross-loop experience persisted as **markdown files** — no storage service, no database. Storage is just files. Loop Memory:

- **Persists generalizable lessons** — failures, heuristics, patterns, calibration-notes, detours — across loops.
- **Is read at ingress** — relevant entries are injected into a role's context at loop start, by deterministic tag/scope match (+ optional LLM relevance).
- **Is written at close** — L1 candidates captured during the loop are distilled into entries; matured entries promote L1→L2.
- **Feeds both loops + fold-back** — entries inform the Auto Loop's experiment selection, the Delivery Loop's role context, and framework fold-back.
- **Reuses existing machinery** — `lessons/`, `templates/lessons-learned-template.md`, the Δ-9 OBS triage L1/L2 maturity ladder (`process/post-deployment-iteration.md`), fold-back, and the Auto Loop §3.3 human-approval rule. Loop Memory does not invent a new lifecycle; it formalizes a cross-loop persistence layer over these.

### §1.2 What it is not

- **NOT a third loop** (§7; Constitution §1.7-E / §3.7).
- **NOT a storage service** — just md files under `<app>/memory/`.
- **NOT a case store** — it stores generalizable heuristics, NOT case-specific input→output mappings (§6.1; the Constitution §1.7 eval-phrase-encoding forbidden item).
- **NOT an authority** — a memory entry suggesting a load-bearing change (skill / charter / prompt edit) is a SUGGESTION; the change stays human-approved (§5; Auto Loop §3.3). Memory informs; it does not decide.

## §2 Structure

```
<app>/memory/
  index.md                 # loaded at ingress; the catalog/router for entries
  entries/
    <id>.md                # one entry per file; front-matter per memory-entry.schema.json
```

- **`index.md`** — the entry catalog, loaded at ingress. It routes ingress selection to relevant entries (by scope/type). Deterministic selection reads scope tags; an optional LLM relevance pass may refine.
- **`entries/<id>.md`** — one entry per file. The front-matter is governed by `schemas/memory-entry.schema.json`; the body is the human-readable lesson. Entries reference each other (and docs) via `[[wiki-style]]` links.

## §3 The entry contract (NORMATIVE — matches memory-entry.schema.json)

This section is the authoritative entry front-matter contract. It MUST match `schemas/memory-entry.schema.json` exactly.

### §3.1 Required + optional fields

```yaml
# memory/entries/<id>.md front-matter
id:           <string, minLength 1>      # REQUIRED — entry lives at entries/<id>.md; referenced by [[links]]
type:         <enum>                      # REQUIRED — failure | heuristic | pattern | calibration-note | detour
scope:        <object, minProperties 1>   # REQUIRED — what the entry applies to (drives ingress selection)
  module:     [<string>]                  #   module(s) the lesson is scoped to
  role:       [<enum>]                     #   research | deliver | dev | code_reviewer | acceptance | engine
  layer:      [<enum>]                     #   Δ-9 fix layer(s) (see §3.2)
maturity:     <enum>                       # REQUIRED — L1 | L2
status:       <enum>                       # REQUIRED — active | superseded | retired
occurrences:  <integer ≥ 1>               # optional — how many loops observed this; n≥2 ⇒ L1→L2 trigger
provider:     <string>                     # required-by-convention for type=calibration-note
model:        <string>                     # required-by-convention for type=calibration-note
source_loops: [<string>]                  # optional — loop_id(s) (Audit Spine) the lesson was distilled from
links:        [<string>]                  # optional — [[wiki-style]] links to related entries / docs
created:      <date>                       # optional
last_reviewed:<date>                       # optional
```

- `additionalProperties: false` — no field beyond these is permitted.
- Required: `id`, `type`, `scope`, `maturity`, `status`.
- `scope` has `minProperties: 1` and `additionalProperties: false`; at least one of `module` / `role` / `layer` must be present.

### §3.2 Field semantics

- **`type`** (enum) — `failure` (something that went wrong + how to avoid it) · `heuristic` (a generalizable rule of thumb) · `pattern` (a recurring structure) · `calibration-note` (a per-(provider,model) judge-calibration observation) · `detour` (a dead-end / wasted-path lesson). Reuses the Δ-9 OBS triage + `lessons/` taxonomy.
- **`scope`** — drives deterministic ingress selection (§4.1). `scope.role` is the enum `research | deliver | dev | code_reviewer | acceptance | engine` — entries are injected for the matching role(s) at ingress. `scope.layer` is the Δ-9 fix-layer enum (`infra`, `java_guard`, `runtime_guard`, `workflow_definition`, `prompt_projection`, `skill_state`, `semantic_planner`, `eval_spec`, `product_policy`, `judge_calibration`, `human_review_required`).
- **`maturity`** (enum `L1 | L2`) — Δ-9 OBS triage maturity. **L1** = candidate (single observation). **L2** = confirmed (n≥2 occurrences OR human-flagged). Promotion L1→L2 happens at close (§4.4).
- **`occurrences`** (≥ 1) — how many loops have observed this lesson; `n ≥ 2` is the L1→L2 promotion trigger (alongside a human flag).
- **`provider` + `model`** — REQUIRED-by-convention when `type: calibration-note` (calibration is per-(provider,model); Constitution §3.6). The schema lists them as optional string fields, but a calibration-note without them is a discipline breach (§6.2).
- **`source_loops`** — the `loop_id`(s) the lesson was distilled from, threading memory back to the auditable Audit Spine record (`modules/m-audit.md` §2). The reverse hook is the spawn payload's `memory_injected[]` (`modules/m-audit.md` §3.4), which records which entry ids were injected into a spawn.
- **`status`** (enum `active | superseded | retired`) — lifecycle state.

## §4 Lifecycle

Loop Memory's lifecycle wraps a single Delivery Loop run, reusing the Δ-9 L1/L2 maturity ladder:

```
INGRESS ──inject by scope──▶ [loop runs] ──capture L1 candidates──▶ CLOSE ──distill + L1→L2──▶ FEEDBACK
   ▲                                                                                              │
   └──────────────────────── matured entries injected into the next loop ◀────────────────────────┘
```

### §4.1 Ingress — inject by scope

At loop ingress, for each role, deterministically select entries whose `scope` matches (by `module` / `role` / `layer` tag match), reading `index.md`. Selection MAY add an optional LLM relevance pass, but the BASE selection is deterministic tag/scope match — so memory injection is reproducible and auditable. The injected entry ids are recorded in the spawn's `memory_injected[]` audit payload (`modules/m-audit.md` §3.4).

`status: active` entries are eligible; `superseded` / `retired` entries are not injected (they remain for history / `[[links]]`).

### §4.2 Capture — L1 candidates during the loop

During the loop, observations (a failure, a heuristic that worked, a detour avoided) are captured as L1 candidates — single observations, cheap, high-throughput (Δ-9 L1; `process/post-deployment-iteration.md` §2.1). Most L1 candidates never mature; that is expected.

### §4.3 Close — distill + update

At loop close, L1 candidates are distilled into entries (new entries, or `occurrences++` on an existing matching entry), and `source_loops` records the closing `loop_id`. This reuses `templates/lessons-learned-template.md`.

### §4.4 Maturity L1→L2 (reuses Δ-9)

An L1 entry promotes to **L2** when `occurrences ≥ 2` (n≥2 similar observations) OR a human flags it load-bearing — exactly the Δ-9 OBS→R-item promotion trigger (`process/post-deployment-iteration.md` §2.2). L2 entries are the confirmed, reliable lessons; only L2 entries feed load-bearing feedback paths (§5) without re-confirmation. This is the same maturity ladder the Auto Loop reads (`modules/m-autoloop.md` §5: L1 too noisy for experiments; L2 eligible).

## §5 Self-evolution feedback paths (each HUMAN-gated for load-bearing changes)

At close, matured (L2) entries can drive five feedback paths. Load-bearing changes are HUMAN-gated per the Auto Loop §3.3 human-approval rule — Loop Memory surfaces candidates; the human approves the change.

| # | Feedback path | What it does | Gate |
|---|---|---|---|
| 1 | **Role context** | Inject the lesson into a role's context at future ingress | Auto / safe — context injection only; no load-bearing artifact changes |
| 2 | **Skill-edit suggestion** | Suggest a vendored-skill edit (via the vendoring flow) | HUMAN-gated (Auto Loop §3.3) — a skill change is load-bearing; Acceptance skill change ⇒ recalibrate |
| 3 | **Charter default tuning** | Suggest a charter default change (e.g. a role binding, a threshold) | HUMAN-gated — charter is load-bearing |
| 4 | **Auto Loop candidate (Type A)** | Surface a `prompt_projection` / `semantic_planner` pattern as an Auto Loop experiment input (Δ-9 hookup) | Auto Loop §3.3 — promotion is HUMAN-approved; Type A only |
| 5 | **Fold-back** | Surface a framework-level lesson into the fold-back protocol | HUMAN-gated — fold-back deliberation per Constitution §8 |

Path 1 (role context) is the only "auto/safe" path because it changes nothing load-bearing — it injects a lesson into a prompt, it does not edit a skill, a charter, a prompt artifact, or the eval surface. Every path that touches a load-bearing artifact folds back to the human (Constitution §1.7-D; Auto Loop §3.3). Loop Memory NEVER auto-promotes a load-bearing change.

## §6 Discipline (HARD)

### §6.1 Store generalizable heuristics, NOT case-specific input→output

This is the central HARD rule (plan §4.4; Constitution §1.7). A memory entry stores a GENERALIZABLE lesson ("when the customer's intent is ambiguous between booking and cancellation, the intent gate under-discriminates — widen the slot prompt") — NOT a case-specific input→output pair ("input X → output Y").

Storing case-specific input→output is the **§1.7 eval-phrase-encoding forbidden item**: it is the memory equivalent of encoding raw eval phrases to make cases pass. It teaches the system to reproduce specific answers rather than to behave well on the underlying pattern — cheating on the test instead of learning the subject (the same distinction `modules/m-autoloop.md` §4.2 draws for the reward signal). An entry that reads like a test answer key is a discipline breach.

### §6.2 Calibration-notes tagged per (provider, model)

A `type: calibration-note` entry MUST carry `provider` + `model` (§3.2). Calibration is per-(provider,model) (Constitution §3.6; a model change invalidates `calibrated`). An untagged calibration-note is meaningless — it cannot tell a future loop whether the calibration observation applies to the model that loop is running. This is required-by-convention; a calibration-note without `(provider, model)` is rejected by discipline review.

### §6.3 Md-only; no storage service

Storage is just files (§1.1). No database, no storage service, no runtime fetch. This keeps Loop Memory inspectable, diffable, version-controlled, and adopter-portable — consistent with the framework's md-persisted-everything posture.

## §7 Naming discipline (Constitution §1.7-E)

Loop Memory is a NAMED, distinct concept in the v4/v2 vocabulary (plan §2 glossary), separate from the two loops:

- **Loop Memory** = the SUBSTRATE — md-persisted cross-loop lessons. NOT a loop.
- **Auto Loop** (Concept 1; `modules/m-autoloop.md`) = the Type A agent's self-improvement loop.
- **Delivery Loop** (Concept 2; `process/delivery-loop.md`) = the multi-agent team's per-milestone delivery loop.

Per Constitution §1.7-E + §3.7, name each distinctly. "The memory loop improved our agent" is a naming-discipline breach — there is no "memory loop"; Loop Memory is the substrate the Auto Loop reads. The framework's tagline is "two loops + one memory substrate" (the `docs/two-loops-explainer.md` extension per plan §4.4 CORE).

## §8 Anti-patterns

- **Case answer-key entries** — storing case-specific input→output (§6.1; §1.7 forbidden item).
- **Untagged calibration-notes** — a `calibration-note` without `(provider, model)` (§6.2).
- **Auto-promoting a load-bearing change** — letting a memory entry edit a skill / charter / prompt without human approval (§5; Auto Loop §3.3 breach).
- **Calling Loop Memory a loop** — naming-discipline breach (§7; §1.7-E).
- **Injecting superseded/retired entries** — only `status: active` entries are injected at ingress (§4.1).
- **Promoting L1→L2 on a single observation without a human flag** — L2 requires `occurrences ≥ 2` OR a human flag (§4.4; Δ-9).
- **A storage service** — anything beyond md files (§6.3).
- **Memory that doesn't thread to audit** — distilling a lesson without recording `source_loops` (the `loop_id` link to the Audit Spine; §3.2).

## §9 What this module does NOT cover

- The `engine-kit/memory/` read/write/maturity implementation internals — realized in `engine-kit/memory/memory_store.py` (plan §4.4 KIT; P3/P5). This module specifies the NORMATIVE contract; the kit is the reference implementation (§10), not the source-of-truth.
- The Δ-9 OBS→R-item triage detail — `process/post-deployment-iteration.md`.
- The Auto Loop experiment selection that consumes L2 patterns — `modules/m-autoloop.md` §5.
- The fold-back protocol — `process/fold-back-protocol.md` (referenced from Constitution §8).
- The Audit Spine that `source_loops` / `memory_injected[]` thread to — `modules/m-audit.md`.
- The lessons template body shape — `templates/lessons-learned-template.md`.

## §10 Cross-references

- Constitution §1.7 — eval-phrase-encoding forbidden item (the §6.1 HARD rule).
- Constitution §1.7-E + §3.7 — two-loops naming discipline; Loop Memory is the substrate, not a loop.
- Constitution §3.6 — calibration is per-(provider,model) (the §6.2 calibration-note rule).
- Constitution §8 — fold-back cadence (feedback path 5).
- `archive/2026-06-15-v2-loop-engine-plan.md` §4.4 — Loop Memory design (structure, lifecycle, L1/L2, anti-gaming, md-only, calibration-note).
- `schemas/memory-entry.schema.json` — validates the entry front-matter (matches §3).
- `engine-kit/memory/memory_store.py` — the reference implementation of this contract: `select` / `load_index` (read), `write_entry` / `record_observation` (write, dedup by `key`), L1→L2 maturity-promote, and the anti-gaming `guard_entry` (reference impl of §4 + §6.1).
- `engine-kit/memory/README.md` — the kit's usage + determinism notes for `memory_store.py`.
- `modules/m-autoloop.md` — Auto Loop (Concept 1); §3.3 human-approval rule (feedback gating); §4.2 cheat-vs-learn distinction; §5 L1/L2 hookup.
- `process/delivery-loop.md` — Delivery Loop (Concept 2); ingress/close wiring (where memory is read/written).
- `process/post-deployment-iteration.md` (Δ-9) — OBS triage L1/L2 maturity ladder Loop Memory reuses.
- `docs/two-loops-explainer.md` — "two loops + one memory substrate" disambiguation.
- `modules/m-audit.md` — `source_loops` (loop_id) + `memory_injected[]` thread memory to the auditable record.
- `templates/lessons-learned-template.md` + `lessons/` — the existing machinery Loop Memory formalizes.

## §11 Editing this module

Module-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The §3 entry contract is LOAD-BEARING and must stay in lock-step with `schemas/memory-entry.schema.json` — the `type`, `scope.role`, `scope.layer`, `maturity`, and `status` enums in particular. Adding a `type` enum value or a `scope.layer` enum value is additive but must be reflected in the schema together. The §6 discipline rules (generalizable-not-case-specific; calibration-note tagging; md-only) are HARD — they address known gaming/incoherence failure modes and are subtraction-forbidden (Constitution §1.8 spirit).

The `engine-kit/memory/` implementation has landed (P3/P5): `implementation_status` is `implemented` and the impl paths are cited in §10, mirroring `modules/m-audit.md`. The spec remains the source-of-truth: if this module and the kit disagree, the kit is the bug (plan §1 conflict rule).

---

End of M-Memory module (Loop Memory — substrate, not a loop).
