# engine-kit/memory — Loop Memory substrate (plan §4.4)

Minimal, **md-file-persisted** cross-loop experience: read at ingress, written at
close. This is the Loop Memory **substrate** from the v2 plan
(`archive/2026-06-15-v2-loop-engine-plan.md` §4.4) — NOT a third loop and NOT a
storage service. Storage is just files.

This module is **deterministic** and has **no hard dependency on the driver** (it
can be exercised standalone). It is now **wired into the Driver as an opt-in**: the
Driver builds a `MemoryStore` only when a `memory_root` is supplied — CLI
`--memory-root` or `charter.memory.enabled: true` (`schemas/mission-charter.schema.json`).
Absent a root the Driver never touches the store (byte-identical to no memory). See
"Driver integration" below.

## On-disk layout

A `MemoryStore` owns one directory:

```
<root>/
  index.md            # regenerated deterministically; loaded at ingress
  entries/<id>.md     # one entry per file: YAML front-matter + markdown body
```

Each entry's front-matter conforms to `schemas/memory-entry.schema.json`
(`type: failure|heuristic|pattern|calibration-note|detour`,
`scope:{module/role/layer}`, `maturity: L1|L2`, `occurrences`, `status`,
`provider`/`model` for calibration-notes, `source_loops`, `[[links]]`,
`created`/`last_reviewed`). Example:

```markdown
---
id: research-stale-brief
type: heuristic
scope:
  module:
  - m-research
  role:
  - research
maturity: L1
occurrences: 1
status: active
source_loops:
- wf_aaa
created: '2026-06-15'
last_reviewed: '2026-06-15'
---

When a brief's sources are older than the milestone, re-pull before planning.
```

## API

```python
store = MemoryStore(root)                       # owns <root>/entries + index.md

store.write_entry(entry, *, ts, loop_id)         # create a new entry (close)
store.record_observation(key, *, ts, loop_id,    # dedup-by-key observation (close)
                         type=…, scope=…, body=…,
                         provider=…, model=…, links=…, human_flagged=False)
store.select(scope)                              # relevant entries by tag/scope (ingress)
store.load_index()                               # the ingress-loaded index.md text
store.get(entry_id) / store.load_all()           # read helpers
guard_entry(entry)                               # anti-gaming guard hook (HARD)
slug(key)                                         # deterministic key -> id
```

- **`write_entry`** creates `entries/<id>.md`, injecting `ts` into
  `created`/`last_reviewed` and threading `loop_id` into `source_loops`. Runs the
  anti-gaming guard *before* touching disk; refuses a duplicate id.
- **`record_observation`** dedups by a stable `key` (`id = slug(key)`). First
  sighting → an **L1** candidate (`occurrences=1`). Repeat sighting → bumps
  `occurrences` and appends the new `source_loop` to the **same** file (no
  duplicate). Maturity promotes **L1 → L2 when `occurrences ≥ 2` OR
  `human_flagged`** (Δ-9 OBS triage — `modules/m-autoloop.md` §5).
- **`select(scope)`** returns active entries whose scope intersects the query on
  any of `module`/`role`/`layer`, in a stable total order: L2 before L1, then
  descending `occurrences`, then `id`. Retired/superseded entries are excluded.
  Deterministic — no LLM, no clock.

## Determinism

`ts` (a date string) and `loop_id` are **injected** on every mutating call. The
core never reads the wall clock, never generates uuids, never calls random. Entry
ids are caller-supplied or `slug(key)`-derived. `index.md` and `select` use a
stable total order, so identical inputs yield byte-identical output.

## Anti-gaming guard (HARD — Constitution §1.7 / plan §4.4)

Loop Memory stores **generalizable heuristics, NOT case-specific input→output**
encodings (the "encoding raw eval phrases" forbidden item;
`modules/m-autoloop.md` §3 anti-gaming / §4 reward-signal discipline). Every write
runs `guard_entry`, a forbidden-pattern check that raises `AntiGamingViolation`
on bodies that look like input→output memorization (e.g. "when the input is X then
output Y", "memorize this expected answer", "input -> output"). The rejected entry
never reaches disk. The forbidden list is small + documented; additions are
framework-level (route via fold-back), not silent.

## Tests

```
/tmp/aidazi-p3c-venv/bin/python -m unittest engine-kit.memory.tests.test_memory_store -v
```

`tests/test_memory_store.py` (stdlib `unittest`, deterministic, temp dir) covers:
write → file exists + front-matter validates against the schema (jsonschema; dates
stringified first); `record_observation` ×2 → `occurrences=2` and L1→L2; human-flag
promotes at a single occurrence; `select(scope)` returns only matching entries in
stable order; `index.md` reflects entries; dedup doesn't duplicate; the guard
rejects a case-specific input→output entry.

## Driver integration (DONE — opt-in via `memory_root`)

Wired in `engine-kit/orchestrator/driver.py` (guarded import; a Driver built without
a `memory_root` is byte-identical to pre-integration):

- **At ingress**, per role: `store.select({"role": [role], "module": [...]})` →
  inject the returned L*-entries into the role's prompt (`driver._lessons_block`,
  for dev/review/deliver/research); the injected ids are recorded in the spawn's
  `memory_injected` audit payload. Load-bearing changes stay human-approved (Auto
  Loop §3.3).
- **At close**, distill the loop's lessons: `store.record_observation(...)` for a
  recurring fix-loop finding class (auto L1→L2 at n≥2; `driver._record_fix_lesson`).
  `ts` comes from the orchestrator clock and `loop_id` from the Audit Spine.
- **At a successful milestone close** (`advance`/`done`), the read-only PROPOSE-ONLY
  feedback stage runs (`feedback.propose` → `driver._memory_feedback`): it writes a
  human-pending report and applies nothing.
- **Current capture scope**: close-time `record_observation` covers the recurring
  fix-loop finding class only; broader role-lesson distillation is future work.

Enable it: pass `--memory-root <dir>`, or set `charter.memory.enabled: true`
(+ optional `root`, default `memory`, resolved against the charter dir and contained
within it; CLI overrides). See `templates/mission-charter.yaml`.
