# WP-6 — Lessons tiering and bounded context injection (decision + measurement)

status: implemented
date: 2026-06-28
branch: wp0-measurement
parent: 895f421 (WP-5A)
roadmap: context/token-optimization — WP-6 (after WP-5A, before WP-8)

This is the checked-in WP-6 decision/measurement artifact required before
implementation. It records the baseline, the deterministic classification
contract, the safety rules, and the chosen (smallest-coherent) design.

---

## 0. Objective

Prevent `driver._lessons_block` (the Loop-Memory ingress channel injected into
Dev / Review / Deliver / Research role prompts) from growing without bound,
while preserving **every validated or constraint-bearing lesson**. The target is
NOT generic truncation; it is tiered, deterministic, auditable suppression of
only the **low-confidence singleton** tail.

---

## 1. Baseline (re-resolved by symbol @ 895f421)

### 1.1 The single injection channel

`driver._lessons_block(role)` (`driver.py:1151`) is the ONLY agent-prompt lesson
injection. It calls `self.memory.select({"role":[role], "module":modules})`
(`memory_store.MemoryStore.select`, `memory_store.py:539`) and renders one line
per entry: `- [<maturity>] <first body line>`. `driver._injected_ids` re-selects
identically for the `memory_injected` audit field. The 5 call sites:
`_step_dev` (1939), `_step_review` (1974), `_step_close` (1987, role=deliver),
`_run_research`/research draft (2055), `_decompose` (2216, role=deliver).

`select()` returns **all** active scope-matched entries, sorted by a stable total
order `(0 if L2 else 1, -occurrences, id)`. **There is no count or byte bound.**

### 1.2 Acceptance injects NO lessons (critical safety fact)

The Acceptance execution-plan spawn passes `lessons_block=None`
(`driver.py:3322-3329`); the Acceptance verdict spawn likewise carries no lessons
block (`driver.py:~3903`). Therefore **`memory_injected=[]`, `memory_bytes=0` for
Acceptance, and `acceptance_input_hash` / `_acceptance_resolver_graph` are
completely independent of the lesson channel.** WP-6 cannot weaken Acceptance or
the Acceptance LOAD-CLOSURE invariant (WP-4): it touches a channel Acceptance
does not consume. The "Deliver" measurement below is the Close/Deliver-plan
spawn, which DOES inject lessons (role=deliver).

### 1.3 Lesson data model (`memory_store.MemoryEntry`)

Durable front-matter (schemas/memory-entry.schema.json): `id`, `type`
(failure|heuristic|pattern|calibration-note|detour), `scope`
(module/role/layer), `maturity` (L1|L2), `occurrences` (≥1), `status`
(active|superseded|retired), `provider`, `model`, `source_loops`, `links`,
`created`, `last_reviewed`, `body`. Runtime-only (NOT persisted): `key`,
`human_flagged`.

Maturity is computed at WRITE (`_apply_maturity`): L1 → L2 when `occurrences ≥ 2
OR human_flagged`. Because `human_flagged` is not persisted, **at selection time
the only durable maturity signals are `maturity`, `occurrences`, `status`** (and
`type`). `maturity == L1` therefore means exactly a single, unflagged, unmatured
candidate (`occurrences == 1`). Supersession exists today only as the store-level
`status: superseded/retired` (filtered out by `select`); there is no entry→entry
supersession pointer, and no marker that a lesson has been promoted into code.

### 1.4 Input-hash / reuse implications

For Dev/Review/Close/Research/Deliver-plan the lessons block is prepended to the
prompt → inside the prompt-only `input_hash = sha256(role\x00prompt)`. Per the
WP-5 memo this hash is **audit-only** for these roles (none are in
`_acceptance_resolver_graph`; no §3.5b reuse coupling). So a bounded block is
deterministically audit-recorded but breaks no reuse gate. Acceptance is
untouched (1.2). `memory_injected`/`memory_bytes`/`load_graph_hash` are
spawn-audit payload, not hash inputs.

### 1.5 Measured payload + growth (the unbounded path)

Replica of the `_lessons_block` render over `MemoryStore.select`, distinct
role-scoped `failure` lessons (representative of `_record_fix_lesson` bodies):

| store size (distinct L1 / role) | entries selected | injected block |
|---|---|---|
| 1   | 4   | 826 B (~206 tok) |
| 5   | 20  | 3,766 B (~941 tok) |
| 20  | 80  | 14,754 B (~3,688 tok) |
| 50  | 200 | 36,822 B (~9,205 tok) |
| 100 | 400 | 73,582 B (~18,395 tok) |

Mixed maturity (per role: 96 L1 singletons + 24 matured L2, occ≥3 among them):
**120 entries → 22,106 B (~5,526 tok) injected every spawn**, of which the 96 L1
singletons are ~80% of the payload.

- **current injected lesson count / payload**: unbounded; linear in lessons-ever-
  recorded for the role. ~184 B (~46 tok) per entry line.
- **duplication rate**: 0 by `id` (record_observation dedups by key), but the
  channel has NO dedup on identical *injected text* (two distinct ids with the
  same first body line both inject — pure redundancy).
- **promoted-but-still-injected prose**: N/A today (no promotion marker exists) —
  a lesson folded into a test/validator/kernel keeps injecting full prose forever.
- **superseded lessons**: store-level `status:superseded` is silently dropped by
  `select` (not auditable at injection); no entry→entry supersession.
- **singleton growth**: the dominant term. Every novel finding adds an L1 that
  injects on every future spawn of its role.
- **worst reproducible growth path**: the scope match is an **OR across
  dimensions** (`_scope_matches`), so a `role:[dev]` lesson injects on EVERY dev
  spawn regardless of module. Over a project's life (hundreds of loops, dozens of
  modules) every dev-scoped lesson ever recorded accumulates and injects on every
  dev spawn → 18K+ tok/spawn at 100 lessons, no ceiling.

---

## 2. Classification contract (deterministic; existing fields first)

`classify(entry)` is a **pure function of durable fields** (no LLM, no clock, no
prompt wording). Precedence (first match wins):

1. **UNKNOWN** — not well-formed: missing `id`; `maturity ∉ {L1,L2}`;
   `occurrences` not an int ≥ 1; `status ∉ {active,superseded,retired}`; or the
   contradictory `maturity==L1 AND occurrences≥2`. *Fail-safe: preserved, never
   budgeted, never treated as L1.*
2. **PROMOTED** — `promoted_to` is a non-empty list of non-empty strings (durable-
   mechanism references: `test:…`, `validator:…`, `kernel:…`, `governance:…`,
   `role_contract:…`). *Injected as a COMPACT reference, not full prose.*
3. **MATURED** — `maturity == L2 AND occurrences ≥ MATURED_MIN_OCCURRENCES`
   (default 3): a regression-prevention lesson confirmed across ≥3 loops. *Always
   preserved.*
4. **L2** — `maturity == L2` (occurrences 2, or human-flag-promoted with occ<3): a
   repeated/independently-validated lesson. *Always preserved.*
5. **L1** — `maturity == L1 AND occurrences == 1`: a singleton/local observation.
   *The ONLY budget-constrained tier.*

**Key safety property:** the only classification boundary that affects *whether a
lesson is dropped* is L1-vs-not-L1. MATURED, L2, PROMOTED and UNKNOWN are all
non-droppable (PROMOTED is compacted, not dropped). So a mis-call between, say,
L2 and MATURED cannot lose a lesson — both are fully preserved. The MATURED/L2
split is reporting/representation only. Therefore the design is robust: any
ambiguity routes to a *preserving* tier.

### 2.1 Safety rules (enforced)

- Only **L1** may be constrained by count/byte budget.
- **L2 / MATURED** are never dropped for being old or over a generic budget — only
  by **explicit supersession**.
- **PROMOTED** injects a compact reference (the `promoted_to` pointer), never full
  historical prose; never silently dropped.
- **UNKNOWN** fails safe: preserved, never treated as disposable L1.
- **Supersession** is explicit + deterministic: an active entry `B` with
  `supersedes:[A,…]` suppresses `A` (any tier) with reason `superseded`. Global
  over all active entries.
- **Dedup** is deterministic and LOSSLESS: a candidate is suppressed (`duplicate`)
  only when the EXACT line it would inject (representation included — full bullet or
  PROMOTED compact ref) is byte-identical to a line ALREADY injected. Removing a
  byte-identical repeat changes the agent's context by nothing, so it is safe for any
  tier; a non-L1 / PROMOTED entry that merely shares a body string with an earlier
  entry but renders differently is NOT a duplicate and is kept (Codex R1 BLOCKING-1).
- **Malformed `occurrences`** (a YAML bool / float / numeric-string / non-coercible
  value) is normalized at parse to the sentinel `0` (below the schema minimum), never
  silently coerced to `1`; it therefore fails safe to UNKNOWN at ingress and is
  rejected by the write-path validator, and a single bad file never crashes ingress
  (Codex R1 BLOCKING-2).
- **Suppression is never silent**: every suppressed id + reason is in the spawn
  audit (`suppressed_lesson_ids` + `lesson_selection`) AND a one-line in-block
  footer notes that N L1 lessons were bounded.
- **Ordering is deterministic** (the store's canonical total order); classification
  and injection do not depend on prompt wording.
- Acceptance / Close constraints from prior WPs are untouched (Acceptance injects
  no lessons; Close's task-scoped cold-start is orthogonal).

---

## 3. Design (smallest coherent)

New pure module `engine-kit/memory/lesson_selection.py`:

- `classify(entry) -> tier` (§2).
- `LessonBudget(max_l1_count=8, max_l1_bytes=4096)` — only L1; configurable via an
  optional `Driver(lesson_budget=…)` param (no charter-schema change).
- `select_for_injection(candidates, *, superseded_ids, budget) -> LessonSelection`
  — single deterministic pass in canonical order: supersession → classify +
  determine the exact injected line → dedup (byte-identical injected line) → PROMOTED
  (compact, unbudgeted) / non-L1 (full, unbudgeted) → L1 (full, budgeted by count
  then bytes). Returns `block` (rendered text), `selected_ids`, `suppressed`
  (`[{id,reason,tier}]`), `tiers`, `representations`, and byte/token before/after.
  When EVERY candidate is suppressed but suppression occurred, the block is still a
  non-silent header+footer (never silently empty).
- Suppression reasons: `superseded`, `duplicate`, `l1_count_budget`,
  `l1_token_budget`; PROMOTED compaction reason `promoted_compact_reference`.

Model extension (additive, backward-compatible — legacy entries default to empty,
files stay byte-identical because empties are not serialized):
- `MemoryEntry.promoted_to: list[str]`, `MemoryEntry.supersedes: list[str]`;
  schema properties added (additionalProperties stays false); `_FM_KEY_ORDER`,
  `front_matter`, `parse_entry` updated.
- `MemoryStore.superseded_ids()` — global set of ids superseded by any active entry.

Driver wiring (single source of truth — no drift between block and audit):
- `_lesson_selection(role)` builds the `LessonSelection`; `_lessons_block(role)`
  returns `.block`; `_injected_ids(role)` returns `.selected_ids`.
- `_spawn` records `memory_injected = selected_ids`, the new
  `suppressed_lesson_ids`, and the `lesson_selection` audit object; `memory_bytes`
  stays `len(prepended block)` (faithful to the dispatched prompt). `lessons_block
  is None` (Acceptance) → injected=[], suppressed=[], lesson_selection=None,
  memory_bytes=0 (byte-identical to today; Acceptance hash untouched).

Audit (append-only, nullable — old ledgers verify unchanged):
- spawn payload gains `suppressed_lesson_ids` (list[str]) and `lesson_selection`
  (object: selected, suppressed[{id,reason,tier}], tiers, bytes_before/after,
  tokens_before/after, version). Schema `$defs/spawn_payload` extended.

### 3.1 Budget defaults rationale

`max_l1_count=8, max_l1_bytes=4096` (~1K tok): bounds the singleton tail to a
handful of recent observations while preserving 100% of L2/MATURED/PROMOTED/
UNKNOWN. A 1-lesson store stays **byte-identical** (under budget → no suppression
→ no footer). Charter-level configurability is a trivial, deferred follow-up
(kept out to avoid touching the WP-1b compact charter schema).

### 3.2 Measured after (wired, `lesson_selection.select_for_injection`, default budget)

| store | candidates | tiers | injected | suppressed (reason) | before → after |
|---|---|---|---|---|---|
| 1 lesson | 4 | L1×4 | 4 | 0 | 826 B → 826 B (byte-identical) |
| 20 L1 | 80 | L1×80 | 8 | 72 (l1_count_budget) | 14,754 B (~3,688 tok) → 1,738 B (~434 tok) |
| 100 L1 | 400 | L1×400 | 8 | 392 (l1_count_budget) | 73,582 B (~18,395 tok) → 1,739 B (~434 tok) |
| mixed | 120 | MATURED×12, L2×12, **L1×96** | 32 | 88 (l1_count_budget) | 22,106 B (~5,526 tok) → 6,108 B (~1,527 tok) |

The previously-unbounded path (linear in lessons-ever-recorded) is now capped at
~434 tok regardless of store size. In the mixed scenario **all 24 validated
(MATURED+L2) lessons are preserved in full**; only the L1 singleton tail is
bounded. (The byte budget binds instead of the count budget when individual L1
lines are large; both are enforced.) Acceptance is unchanged (injects no lessons).

---

## 4. Compatibility & migration

- Existing memory files: unchanged on disk (new fields omitted when empty).
- Existing audit ledgers: verify unchanged (new fields nullable / absent).
- `memory_injected` semantics tighten from "would-select" to "actually-injected"
  (post-budget); identical in all under-budget cases (incl. every existing test
  fixture, which seeds 1 lesson).
- No charter/governance/kernel/role-card/resolver/cold-start/load-closure change.
  `_sources.yaml`, kernel coverage (65/65, 41/41, 44/44), and the base 475-row
  inventory are untouched (memory-entry schema is data, not a governance source).
- Rollback: revert the commit; no data migration needed (fields are additive,
  budget is in-process).

---

## 5. Explicitly out of scope (per brief)

WP-8 AGENTS.md trim; WP-9 context-budget lint; Research/Deliver projections;
WP-5A changes; `review_runner.py` background-process fixes; auto-promotion of
lessons (PROMOTED is set by human/feedback action, not inferred). Charter-level
budget config (trivial follow-up).

---

## 6. Review-gate log (Codex gpt-5.5 xhigh, read-only, bounded runner)

Prompt `.runs/wp6/wp6-codex-prompt.md` (argv-token + `WP6-R1-CONFIRM` sentinel to
defeat stale-session resume); captures `.runs/wp6/reviews-r{n}/`.

**R1 = REVISE** (sentinel confirmed; 9-dimension adversarial review). 2 blocking +
1 non-blocking, all valid, all fixed:
- **BLOCKING-1** (dim 2/5): dedup keyed on the first body line and ran before
  PROMOTED rendering → a PROMOTED / non-L1 entry sharing a body string with an
  earlier entry could be dropped as `duplicate`. FIX: dedup now keys on the EXACT
  injected line (representation included), suppressing only byte-identical repeats
  (lossless for any tier). +tests `test_cross_tier_same_body_not_deduped`,
  `test_promoted_not_lost_to_dedup_when_body_shared`,
  `test_duplicate_elimination_byte_identical_line`.
- **BLOCKING-2** (dim 1): `parse_entry` did `int(occurrences)`, silently coercing
  `true`/`"1"`/`1.2`→`1` (→ droppable L1) and raising on `"abc"` (→ ingress crash).
  FIX: `memory_store._coerce_occurrences` normalizes any non-`int`/bool/`<1` value
  to sentinel `0` → classify fails it safe to UNKNOWN; never raises. +tests
  `test_malformed_occurrences_coerced_to_sentinel_not_silently_int`,
  `test_genuine_int_occurrences_preserved`.
- **NON-BLOCKING-1** (dim 6): all-suppressed selections rendered no footer (false
  "non-silent" claim). FIX: `_render_block` emits a header+footer block when every
  candidate is suppressed. +test `test_all_suppressed_still_renders_footer`.

(Codex dim-9 noted it could not re-run the suite in its read-only sandbox — no temp
dir / no pyyaml; not a defect. Locally: full suite green, see below.)

Post-fix gates: full suite **1162 passed / 3 skipped**; kernel coverage 65/65 +
41/41 + 44/44 + base 475; acceptance load-closure `closed:true, pending:[]`.

**R2 = APPROVE** (sentinel `WP6-R2-CONFIRM` confirmed; `.runs/wp6/reviews-r2/`). All
9 dimensions PASS, no blocking/non-blocking findings; the three R1 fixes verified
correct (dedup-on-rendered-line lossless; occurrence sentinel → UNKNOWN; all-
suppressed footer non-silent). Codex re-confirmed Acceptance untouched, additive
fields backward-compatible, budget only constrains L1, tests non-vacuous. (Dim-9
re-run again blocked in Codex's sandbox by missing pyyaml — local suite is green.)
