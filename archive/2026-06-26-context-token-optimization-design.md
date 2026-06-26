---
title: Context / Token Optimization — Revised Design Spec (compress + measure, not defer + cache)
doc_tier: framework-design
doc_category: live
status: proposal
implementation_status: not_started
source_of_truth: this file
last_reviewed: 2026-06-26
review_cadence: per implementation increment
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 40KB
notes: >
  Design-only. No runtime behavior change. Codex-gated (gpt-5.5 xhigh, read-only).
  Governing principle: compress the EXPRESSION of constraints; never defer the
  constraints themselves. Read-volume reduction is the only framework-controllable
  token lever (provider prefix-caching is mechanically inapplicable — see §A).
---

# Context / Token Optimization — Revised Design Spec

Branch `v2-loop-engine`, HEAD `d920a2b`. Read-only investigation (5 parallel
audits + targeted verification). All file:line are current as of this revision;
the working tree is dirty (~44 modified + ~20 untracked) — audit reflects on-disk
state, and any implementation must re-verify line numbers.

---

## A. Executive conclusion

**Diagnosis (confirmed by repo facts + Codex):**
- The dominant token cost is the per-spawn **governance cold-start re-paid on every
  fresh subprocess** — `governance/constitution.md` (54.6KB / ~13.7K tok) +
  `doc_governance.md` (16KB / ~4.0K tok) + `context_briefing.md` (22.8KB / ~5.7K tok)
  = ~23.4K tok, plus a role card (11–19KB) and per-role briefing docs, on **every**
  Dev/Review/Acceptance/Research/Deliver/fix-round spawn. Source: cold-start order
  `governance/context_briefing.md:104-110`; fresh subprocess `engine-kit/adapters/claude_code.py:175`.
- `_lessons_block` (`engine-kit/orchestrator/driver.py:1046-1068`) is the only
  **uncapped injected channel** (one line per matching memory entry, no top-K).
- Fix-rounds are already **delta-only** (`driver.py:1761-1821`); prompts already
  **reference evidence by path**, not embed; memory store dedups. No super-linear blowup.
- ~80% of the 163KB schema corpus is **validator-only = zero agent tokens**.

**What changed since the first-draft plan (two reversals):**

1. **Provider prefix-caching (old P2a) is NOT orchestrator-controllable.** The
   orchestrator shells out to `claude -p` (`claude_code.py`) and does not call
   `/v1/messages`, so it cannot set `cache_control`. (This is a claim about what the
   orchestrator can control, NOT that no provider-internal optimization ever applies.)
   The governance chain is pulled
   in by the **agent's own mid-session Read calls** (proven: no `open()/read()` of
   governance anywhere in `driver.py`; cold-start is an instruction naming paths at
   `driver.py:1628`, `:3537`), so it is never a stable orchestrator-controlled prefix.
   Anthropic caching is a prefix-match with a 5-min TTL and 4096-token Opus minimum;
   fresh per-spawn sessions with per-spawn-unique prompts cannot reuse it. **Therefore
   read-volume reduction is the ONLY framework-controllable lever.** This is more
   restrictive than the prior plan assumed.

2. **"schemas cost zero agent tokens" was too broad.** `mission-charter.schema.json`
   (30KB) is mainly validator-only BUT `context_briefing.md:207` can route a charter/
   Δ-18 session to load it; verdict schemas are explicitly role-loaded
   (`context_briefing.md:170,182`). So schema slimming has real, if modest, value.

**Revised strategy:** `compress + measure`, not `defer + cache`.
- Compress the **expression** of every constraint into small, COMPLETE proactive
  kernels (constitution-core, authoring-kernel, acceptance-kernel) + compact schema
  projections. Drop rationale/anatomy/examples/prose, never rules.
- Measure first (Phase 0) — the cold-start volume is invisible to current telemetry,
  so the 45–50% estimate is a **hypothesis to validate**, not a proven number.

**Biggest win (estimated, pending Phase 0):** constitution-core alone removes
~9–10K tok from every role spawn; with authoring-kernel + acceptance-kernel +
schema projection, per-spawn cold-start drops ~40–50% (Dev ~27K→~14K, Review
~31K→~16K, Acceptance ~32K→~17K) with **no isolation/audit-model change**.

**Biggest risk:** a kernel that silently drops a HARD constraint an agent must see
proactively (Codex's "token cuts = constraint cuts"). Mitigated by the
**constraint-equivalence proof** (§C, §D-WP-EQ) — kernels are generated/checked
against a complete constraint inventory, not hand-judged. Secondary risk: an
Acceptance load-graph change that desyncs the audit-hash resolver (§E).

**Permanently rejected (do not reintroduce):** verdict-schema pure-on-demand;
generic "lite tier" for Close/Research/Deliver-plan; fix-round session reuse;
orchestrator-side provider prefix-caching as a primary lever (§G).

---

## B. Current-state load graph (per role / per spawn)

Canonical definition: `context_briefing.md` §1.2 (role cold-start order) + §2
(per-role briefing lists). Acceptance additionally has a content-hashed resolver
graph at `driver.py:3819-3907`. Tokens ≈ bytes/4.

**Universal role-session cold-start (every explicit role), `context_briefing.md:104-110`:**

| # | File | ~tok | Notes |
|---|---|---|---|
| 1 | `governance/constitution.md` | 13,663 | always-load |
| 2 | `governance/doc_governance.md` | 3,994 | always-load |
| 3 | `governance/context_briefing.md` | 5,706 | always-load (this file) |
| 4 | adopter `AGENTS.md` | ~1–2K | harness-loaded |
| 5 | adopter `docs/current/adoption-state.md` | ~0.4K | |
| 6 | role card | 2,772–4,741 | per role |
| 7 | per-role briefing list (§2) | varies | per role |
| | **Universal floor (1–3)** | **~23.4K** | re-paid every spawn |

**Per-role add-ons (§2):**

| Role | Card ~tok | Briefing docs (§2) | Effective cold-start ~tok |
|---|---|---|---|
| Dev (`driver.py:1418`) | 2,772 | prompt-artifact-rules + context-passing-efficiency + the compact dev prompt | **~27K** |
| Code Reviewer (`:1609`) | 3,234 | anti-hardcode-review-kernel (~1.7K) + review-verdict.schema (846) | **~31K** |
| Acceptance (`:3493`) | 4,741 | compact-acceptance-prompt + acceptance-verdict.schema (2,129) + role card mandates `process/delivery-loop.md` (~12K!) at `role-cards/acceptance-agent.md:40` | **~32K (or ~44K if delivery-loop loaded whole)** |
| Research (`:1915`) | 2,918 | domain-discovery + agent-design-elicitation + agent-creation-prerequisites (~4–5K) + research-brief.schema (1,026) | **~30K** |
| Deliver/Close (`:1874`) | 4,503 | milestone-framework + tech-decision-catalog + typeA-skeleton + artifact-taxonomy + post-deployment + detours + deliver-close-taxonomy (~16K) | **~44K (heaviest)** |

**Default Control-Plane session** (`context_briefing.md:42-59`): loads only the
`control-plane-load` block + control state + adoption-state + agent_context_guide
≈ **~1.9–3.0K tok**. Already lean — governance kept OFF the `@`-import graph; do not touch.

---

## C. Constraint inventory (the equivalence foundation)

Full per-row inventories were produced for each kernel; condensed here. The
**equivalence rule**: every HARD constraint below MUST appear in the kernel
(compressed to an imperative clause); only rationale/examples/anatomy are deferred.

### C.1 constitution-core (replaces full `constitution.md` at cold-start step 1)

**41 KERNEL constraints**; complete kernel fits **~3.5–4.5K tok** (vs 13.7K whole) —
upper end of the band, because the enumerations (the 5 core §1.7 forbids + A–E, the
9 MANDATORY_CHECKPOINT names, the 4 checkpoint-bypass shapes, the runtime-owned
floor list, the 6 §3.4 role invariants, the read-only/whitelist matrix) **are the
constraint, not prose**, and cannot be compressed away. Categories (source → must-be-proactive):

| Cluster | Source §§ | Roles | Programmatic enforcement? |
|---|---|---|---|
| LLM/runtime ownership (soft=LLM, hard kernel=runtime; PII/safety/grounding floors) | §1.3-1.4 (`constitution.md:62-88`) | Dev, Rv, D | budget/timeout only; floors NONE |
| Context-budget / self-containment | §1.4-i (`:90-106`) | D/Dev/Rv/A | `driver.py:1399-1412` |
| Anti-hardcoding + eval discipline | §1.5-1.6 (`:110-128`) | Dev, Rv, A, D, FX | NONE (judgment) |
| Forbidden list (5 core + A–E + no-subtract) | §1.7 (`:138-219`) | role-specific | F-D/F-C partial (`charter_validator.py:340-475`); rest NONE |
| 5-role boundary invariants | §3.4 (`:344-357`) | ALL | partial (capability/skill/network gates) |
| Human-confirm / calibration | §3.5-3.6 (`:359-403`) | A, O, Cust | `driver.py:2900-3024`, `charter_validator.py:453-510` |
| Anti-patterns (restate §1.7 + scope-envelope, eval-contamination, F5) | §10 (`:588-594`) | role-specific | partial |
| Hard-requirements registry (non-overridable) | §7.0 (`:517-524`) | ALL | aggregate |
| Engine hard-gates (P0/P1-blocking, self-smoke, e2e binding, adaptive-insert, gate-hard-fail) | role cards + delivery-loop | role-specific | ENFORCED |
| Cold-start/session discipline (control-plane≠role, harness wiring, §1.7-divergent halt, pre-output checklist) | `context_briefing.md` §1.0/§1.1/§5/§7 | ALL/CP | `adopter_wiring_validator.py` partial |

**Critical finding (count PROVISIONAL — to be confirmed by the WP-EQ row-level
inventory, not asserted as fact yet):** a large cluster of KERNEL constraints have
**NO programmatic enforcement** (anti-hardcode, eval-discipline, ownership,
abstraction-layer, Reviewer≠Acceptance, Deliver-no-code, shadow-eval-contamination).
That cluster lives only in role-card self-checks + the kernel prompt — so it MUST be
carried verbatim; nothing else catches a violation. The earlier "~25 of 41" figure is
a rough count from the condensed §C tables; the exact set is established by WP-EQ.

**DEFER-OK (to on-demand full constitution):** §3.7 two-loops distinction tables,
§8 governance-editing discipline (maintainer-only), §1.1-1.2 anatomy, §2 doc-tiers,
§4-6 pointer tables, §9 versioning, §11 read-order, §12 glossary, and all
"Why"/"How"/worked-example prose ≈ **8.5–9.5K tok**.

**Constitution-internal gaps flagged** (carry as kernel TODOs, don't invent fixes):
PII/safety/grounding floors named without a constraint body; "fresh-session" has no
deterministic detector; closure_contract immutability is prompt-asserted not
hash-frozen; `scope_envelope_check` documented "not yet wired" (`driver.py:2823`).

### C.2 authoring-kernel (extract from `doc_governance.md`)

All 5 roles author governed artifacts → `doc_governance.md` cannot be fully dropped
for any role. **NO validator enforces doc frontmatter today** (search confirms).
- **FULL kernel (A1–A18, ~900–1,100 tok)** → Deliver (reconciliation, fold-back,
  archive ops, handoff §0/§12, cell-size) + Research (authors the load-bearing
  closure_contract brief; supersession).
- **NARROW kernel (A1–A4 frontmatter + enums, A7 closure immutability, A8
  frozen-intermediate, A13 stale-ref, A15 supersession; ~450–600 tok)** → Dev
  (handoff §1-§11, diagnostics), Reviewer (codex-findings append-only), Acceptance
  (acceptance-report frontmatter + closure immutability).
- **Droppable to on-demand for Dev/Rv/A:** §6 cell-size, §8 fold-back, §9 archive
  ops, §11 editing-governance (~40% of the doc).
- Adjacent ownership rules living OUTSIDE doc_governance the kernel must *reference*:
  codex-findings append-only (`code-reviewer-agent.md:88`); handoff §0/§12 Deliver-only,
  §1-§11 Dev (`dev-agent.md:115-117`).

### C.3 acceptance-kernel (extract from `delivery-loop.md` §4.2.x into the projected prompt)

The projected acceptance prompt (`driver.py:3493-3581` + browser addendum `:3798-3817`)
is **already ~80% self-contained** (~1.1–1.3K tok). Full kernel ≈ ~1.2–1.5K tok.
**6 judge-instruction gaps to close BEFORE `delivery-loop.md` may leave always-load:**
1. **G7** route `research_contract_revision` on a contract-coverage/3-component gap.
2. **G18** verdict aggregation decision-tree (per-clause → milestone_verdict).
3. **G23** explicit needs_human trigger list.
4. **G21** instruction to write `docs/acceptance-reports/<scope>-acceptance-report.md` (NOT driver-covered).
5. **G22** suggested_route selection guidance (which route fits which failure shape).
6. **G13** calibration-identity drift (agent_kind/model/skills ≠ calibration set).

~8 other gates are **structurally enforced** by driver/schema/charter pre/post-spawn
(spawn-isolation, evidence-absent halt, advisory-pass HALT, browser binding, etc.) —
document them as "covered elsewhere" in the equivalence proof; they need not be inlined.

---

## D. Revised work packages

Format per WP: Objective · Files · Change · Constraints-preserved · Kernel/equivalence ·
Audit/hash · Tests · Metrics · Acceptance-gate · Rollback · Deps · Risk · Est-gain · Non-goals.
WPs are sequenced in §15. **`compress, never defer`** governs every kernel WP.

> **IMPLEMENTATION-BASELINE REVALIDATION — mandatory precondition for EVERY WP.**
> This spec's line-level citations (`driver.py:851`/`:1046`/`:3819-3907`, `e2e_stage.py:410`,
> `audit_log.py` `SPAWN_PAYLOAD_FIELDS`, `context_briefing.md:104-110`/`:332-338`, role-card
> lines, schema byte counts, the "~67 dirty entries", etc.) were captured on **2026-06-26
> against a DIRTY working tree** (~67 uncommitted changes touching exactly the files several
> WPs edit — `driver.py`, `e2e_stage.py`, `audit_log.py`, `adapters/*`, schemas). Once that
> in-progress work is integrated, anchors WILL move and some symbols/structures may change.
> Therefore, before implementing ANY WP:
> 1. **Re-resolve every cited anchor by SYMBOL, not line number** (grep the function/field/
>    regex, e.g. `_acceptance_resolver_graph`, `acceptance_input_hash`, `SPAWN_PAYLOAD_FIELDS`,
>    `_lessons_block`); update the WP's `Files`/`Audit-hash` rows to the current truth.
> 2. **Re-confirm the structural assumptions** still hold against the integrated repo: the
>    two-hash model (per-spawn prompt-only `input_hash`; Acceptance-only `acceptance_input_hash`
>    = hash(prompt + resolver graph)); the exact `_acceptance_resolver_graph` entry set; the
>    `context_briefing.md` §1.2/§2/§6 load rules; the four agent-loaded schemas + their prose%.
> 3. **Re-run WP-0's sizer** to refresh the byte/token baseline on the integrated tree (the
>    45–50% hypothesis is measured against THAT baseline, not this doc's pre-integration numbers).
> 4. **If any anchor moved or semantics changed, update the affected WP + re-gate** (Codex)
>    before writing code. The design's principles + invariants (compress-not-defer, the
>    ACCEPTANCE LOAD-CLOSURE invariant, equivalence harness, audit-coupling rules) are stable;
>    the line-level citations are NOT — treat them as starting points, re-validate as fact.
> Each WP's `Deps` implicitly includes this revalidation step.

### WP-0 — Measurement baseline (Phase 0)
- **Objective:** make per-spawn + cold-start token volume observable; establish baseline. **No dispatched-context change.**
- **Files:** `engine-kit/audit/audit_log.py` (`make_spawn_payload` ~:123; `SPAWN_PAYLOAD_FIELDS` :68-82 already lists unused `tokens`,`cost`); `driver.py:850-852` (prompt finalized) + the 3 `make_spawn_payload` callsites (:897/:917/:930); `e2e_stage.py:388-392` (`resolve_load_graph` already opens+hashes each file — add `bytes`); `audit_report.py:115-120` (auto-renders new fields).
- **Change:** record per spawn `prompt_bytes=len(prompt.encode())`, `role`, `fix_round`, `memory_injected` count/bytes. Add a read-only **load-graph sizer** that runs the existing `resolve_load_graph` over each role's cold-start set to sum cold-start bytes WITHOUT a spawn (the cold-start reads are otherwise invisible — they're the agent's own mid-session Reads, dropped at the adapter boundary).
- **Constraints-preserved:** all (pure observation).
- **Kernel/equivalence:** n/a.
- **Audit/hash:** adds a new ledger field → update `SPAWN_PAYLOAD_FIELDS` + `test_audit.py` (additionalProperties:false). Forward-only; old ledgers still verify (`verify_chain` recomputes over recorded bytes only).
- **Tests:** payload-field schema test; sizer unit test on a fixture load set.
- **Metrics:** per-role cold-start **byte** histogram (authoritative); per-spawn prompt **bytes**; fix-round multiplier; lessons bytes. Token figures are a documented **estimate** (bytes÷4 or, optionally, `count_tokens` — NOT implied from `len(prompt.encode())`). **This is the baseline the (hypothesised) 45–50% reduction is measured against.**
- **Acceptance-gate:** baseline artifact emitted for a representative campaign; numbers stable across ≥2 runs.
- **Rollback:** **deprecate, don't delete** — mark the added payload field optional / version the event type; never remove a `SPAWN_PAYLOAD_FIELDS` property while ledgers containing it exist (`additionalProperties:false` would orphan historical payloads). Sizer is removable freely.
- **Deps:** none. **Risk:** LOW. **Est-gain:** 0 tok (enables all others). **Non-goals:** no caching telemetry (caching not orchestrator-controllable, §A/§G).

### WP-EQ — Constraint-equivalence harness + COMPLETE row-level inventory (gate for all kernel WPs)
- **Objective:** machine-checkable mapping `source HARD constraint → kernel clause OR covered-by-role-card OR covered-by-driver → dispatched roles → enforcement/test`, so a kernel can be PROVEN complete, not eyeballed. **The proof is only as good as the inventory — so the inventory must be EXHAUSTIVE, not the condensed §C tables.**
- **Files:** new `engine-kit/tools/kernel_equivalence.py` + a checked-in **row-level** `constraint-inventory.yaml` + a check wired into CI / an existing validator.
- **Change — the inventory MUST enumerate every proactive hard constraint across ALL sources (Codex BLOCKING-3), not just the constitution:**
  - `governance/constitution.md` (all §1.7 incl. A–E, §3.4, §3.5/3.6, §7.0, §10 anti-patterns),
  - `governance/doc_governance.md` (A1–A18),
  - `governance/context_briefing.md` (§1.0/1.1/§5/§7),
  - `process/delivery-loop.md` §4.2.x — including **all 14 Delivery-Loop anti-patterns** at `delivery-loop.md:493` (the condensed §C.3 listed only the gaps; the inventory must list every one),
  - **`process/role-skill-model.md` §4 (Codex R2-B2)** — a CONDITIONAL hard-constraint
    source: its §4 (`role-skill-model.md:84`) declares 5 boundary constraints that are
    NOT adopter-overridable, and all five role cards mandate loading it when skills /
    sub-agent fan-out are active (`dev-agent.md:156`, `research-agent.md:181`,
    `deliver-agent.md:271`, `code-reviewer-agent.md:185`, `acceptance-agent.md:253`).
    Each row tagged `condition: skills_or_fanout_active`.
  - **all five role cards** — including role-skill / sub-agent fan-out constraints, e.g. `acceptance-agent.md:251`, `code-reviewer-agent.md:183`, and the per-card pre-output checklists.
  Each row carries `source_anchor`, `constraint_id`, `roles`, `condition` (default
  always; e.g. `skills_or_fanout_active` for role-skill-model rows), `coverage_status` ∈
  {kernel-clause:<id> | covered-by-role-card:<path> | covered-by-driver:<symbol> | covered-by-schema:<file>}, `enforcement_ref`. The asserter then verifies, per role, that every row with `coverage_status=kernel-clause` resolves to a real clause in that role's kernel; flags duplicates/conflicts; and binds each source to its content hash (stale-source → fail "re-review inventory + regenerate kernel").
- **Constraints-preserved:** this IS the preservation mechanism — and its completeness is the gate's own weak point, so the inventory itself ships for human + Codex review (see Acceptance-gate).
- **Kernel/equivalence:** defines it.
- **Audit/hash:** none (build-time gate).
- **Tests:** missing-constraint detection (delete a row's clause → fail); stale-source detection (edit any source hash → fail); **source-coverage audit** (a deliberately-omitted known constraint, e.g. one of the 14 anti-patterns, is caught as an uncovered row).
- **Metrics:** rows enumerated per source (must cover 100% of proactive constraints in each source); % rows with a resolved `coverage_status` (must be 100%).
- **Acceptance-gate:** the **inventory's completeness is itself reviewed** (human + a dedicated Codex pass that diffs the inventory against each source file for missed constraints) BEFORE any kernel WP; then 100% coverage. Kernels are human-maintained, machine-CHECKED — generation is too lossy for legal-prose constraints.
- **Rollback:** drop the check (kernels not yet built). **Deps:** WP-0. **Risk:** HIGH (inventory completeness is the crux — a hollow inventory makes every downstream kernel proof hollow). **Est-gain:** 0 (enabler). **Non-goals:** not auto-generating kernel prose.

WP-1 is split into **WP-1a** (zero-coupling pilot — Milestone 1B) and **WP-1b** (the
audit-coupled remainder). Common technique: strip `description`/`title`/`$comment`/
`examples` while preserving ALL machine keys (type/enum/const/pattern/required/
additionalProperties/if-then-else/allOf-anyOf-oneOf/min-max/format/$ref); validation
semantics provably unchanged (Draft 2020-12 annotations; jsonschema never applies
defaults; no code reads those keys). Both depend on the implementation-baseline
revalidation above (re-confirm the agent-loaded schema set + prose% on the integrated tree).

### WP-1a — research-brief slim-in-place (PILOT — zero blast radius, Milestone 1B)
- **Objective:** slim `schemas/research-brief.schema.json` IN PLACE — the safest possible first reduction, used to validate the whole slim technique end-to-end before any coupled schema.
- **Why zero-risk:** research-brief has **NO Python validator** (agent-only reader — confirm by grep on the integrated tree) and is **NOT in any resolver graph** → audit-NEUTRAL, no `acceptance_input_hash` coupling, no `test_pc_schemas` shape test. Slimming in place needs no compact-projection machinery.
- **Files:** `schemas/research-brief.schema.json`; loader refs (`role-cards/research-agent.md:40`, `context_briefing.md:134`, `templates/compact-research-brief.md`) stay pointed at the same path (in-place).
- **Change:** strip annotation keys only; keep every machine key + any agent-load-bearing semantic gloss (compress, don't delete, where an enum's meaning isn't self-evident).
- **Constraints-preserved:** validation-neutral (no validator at all); agent comprehension preserved by keeping terse semantic glosses.
- **Tests:** a constraint-set-equality check (machine keys identical pre/post) — add it even though no validator exists; a Research canary still emits a schema-valid brief.
- **Metrics:** ~−650 tok per Research spawn (confirm against WP-0 baseline).
- **Acceptance-gate:** machine-key set identical pre/post; Research canary brief valid + closure_contract well-formed; WP-0 shows the byte reduction.
- **Rollback:** `git revert` the schema (single file, no machinery). **Deps:** WP-0. **Risk:** LOW (no coupling). **Est-gain:** ~650 tok/Research spawn. **Non-goals:** no compact-projection generator yet (that's WP-1b); do NOT touch coupled schemas here.

### WP-1b — compact projections for review / acceptance / mission-charter (audit-coupled)
- **Objective:** slim the 3 remaining agent-loaded schemas via a COMPACT PROJECTION (canonical stays verbose for the Python validator + `mission-charter.yaml` template + humans), reusing the technique proven by WP-1a.
- **Files:** new `engine-kit/tools/project_schema.py` → `schemas/compact/<name>.compact.schema.json` (embeds `$id` + `x-canonical-sha256`); repoint loaders (`code-reviewer-agent.md:41`, `driver.py:1630/3539`, `acceptance-agent.md`, `context_briefing.md:170/182/207`) — re-resolve all anchors per the revalidation step.
- **Change:** generate + repoint; lockstep check fails if `x-canonical-sha256` ≠ canonical.
- **Kernel/equivalence:** schema-equivalence corpus (`test_pc_schemas.py` fixtures) passes identically pre/post; malformed-verdict rate must not rise.
- **Audit/hash:** `acceptance-verdict.schema.json` is content-hashed in `_acceptance_resolver_graph` → if Acceptance loads the compact file, repoint the resolver entry to the compact path + update `test_e2e_acceptance.py` (lockstep, per §E); review-verdict + mission-charter are audit-neutral.
- **Tests:** projection round-trip; canonical-vs-compact constraint-set equality; fixture corpus; resolver-binding test if acceptance compact-repointed.
- **Metrics:** review −520, acceptance −1,490, charter −5,020 (projection; charter is charter-session-only).
- **Acceptance-gate:** zero validation-behavior delta on corpus; malformed-verdict rate flat in a canary loop; acceptance resolver binding green.
- **Rollback:** repoint loaders to canonical (delete compact dir + revert resolver entry). **Deps:** WP-0, WP-1a (proven technique), WP-7; for the acceptance schema also WP-EQ + §E lockstep. **Risk:** LOW–MED (acceptance schema audit-coupled). **Est-gain:** ~6.1K tok (mostly charter-session). **Non-goals:** do NOT make any verdict schema on-demand (rejected, §G); do NOT slim deliver-close-verdict (not file-loaded → 0 gain).

### WP-2 — constitution-core kernel
- **Objective:** replace cold-start step 1 (full `constitution.md`, 13.7K) with a complete `constitution-core.md` (~4K) + full constitution on-demand.
- **Files:** new `governance/constitution-core.md`; `context_briefing.md:104` (+ §3 context-pack list :231); the §C.1 inventory in WP-EQ; `constitution.md` gains an on-demand pointer header.
- **Change:** core carries every KERNEL clause (§C.1); full doc keeps rationale/anatomy/pointers and is loaded on-demand via §2.6 lookups.
- **Constraints-preserved:** all 41 (proven by WP-EQ). The ~25 unenforced ones carried verbatim.
- **Audit/hash:** **DECISION — slim-by-reference, not by-rename for Acceptance.** The resolver hashes `governance/constitution.md` at `driver.py:3899`. Cleanest: keep cold-start pointing at a path the resolver already binds. Recommended: introduce `constitution-core.md` AND add it to `_acceptance_resolver_graph` (`driver.py:3898-3906`) + `test_e2e_acceptance.py:712-728` in lockstep; if the full constitution leaves Acceptance's proactive set, REMOVE its resolver entry so the audit doesn't hash an undispatched file. Dev/Review/Close/Research are **audit-neutral** (input_hash is prompt-only) — but see WP-7 for the transcript gap.
- **Tests:** WP-EQ coverage=100%; `test_e2e_acceptance` governance-binding updated; cold-start order test.
- **Metrics:** −~9–10K tok/role spawn (largest single win).
- **Acceptance-gate:** WP-EQ green; a real Dev+Review+Acceptance canary loop completes with no governance regression (no §1.7 breach, no scope/eval violation) vs baseline.
- **Rollback:** repoint cold-start to full constitution; revert resolver entry + test. No ledger migration.
- **Deps:** WP-EQ, WP-0, **WP-7** (governance version must be ledger-recorded before the first non-Acceptance cold-start swap — Codex BLOCKING-4). **Risk:** HIGH (the core lever; thin-kernel risk). **Est-gain:** ~9–10K/spawn. **Non-goals:** not changing any constraint's meaning; not editing the constitution's normative content (only relocating rationale).

### WP-3 — authoring-kernel
- **Objective:** replace cold-start step 2 (full `doc_governance.md`, 4K) with role-scoped authoring kernels.
- **Files:** new `governance/authoring-kernel.md` (full) + the narrow subset; `context_briefing.md:105` made role-aware; role cards reference the right kernel.
- **Change:** Deliver/Research load full (~1K); Dev/Reviewer/Acceptance load narrow (~0.5K); full `doc_governance.md` on-demand (§2.6 "Doc lifecycle question").
- **Constraints-preserved:** A1–A18 mapped (§C.2); narrow set proven sufficient for Dev/Rv/A authoring outputs.
- **Audit/hash:** Acceptance loads narrow authoring-kernel → update resolver entry that currently binds `doc_governance.md` (`driver.py:3900`) + test. Dev/Review audit-neutral.
- **Tests:** WP-EQ for authoring constraints; a doc authored by each role still carries valid frontmatter (new lightweight check, optional).
- **Metrics:** −~3K tok for Dev/Rv/A spawns; −~3K minus ~1K for Deliver/Research.
- **Acceptance-gate:** WP-EQ green; canary handoff/findings/report still well-formed.
- **Rollback:** repoint to full doc_governance. **Deps:** WP-EQ. **Risk:** MED. **Est-gain:** ~3K/spawn (Dev/Rv/A). **Non-goals:** do NOT drop doc_governance entirely for any role (Codex DROPS-CONSTRAINT).

### WP-4 — acceptance-kernel + close the Acceptance LOAD-CLOSURE invariant
- **Objective:** close the 6 judge-instruction gaps (§C.3) in the projected acceptance prompt AND satisfy the **Acceptance load-closure invariant** (§E): every file an Acceptance session can load must be inlined, resolver-bound, or HALT-gated — never an unbound verdict-affecting read. The two known instances are `delivery-loop.md` (3 triggers) and `role-skill-model.md` (conditional on skills); the closure test (§E) must prove there are no others.
- **`role-skill-model.md` (Codex R3):** when `charter.tooling.acceptance.skills` is non-empty, Acceptance loads it (`acceptance-agent.md:253`) and its §4 (`role-skill-model.md:84`) are non-overridable verdict-affecting constraints. Resolution (same pattern as delivery-loop): **inline the §4 boundary constraints into the acceptance-kernel + remove the conditional read** (insufficient → refinement HALT), OR **conditionally bind `role-skill-model.md` in `_acceptance_resolver_graph`** when effective Acceptance skills/fan-out are active. Add a test that mutating `role-skill-model.md` changes Acceptance reuse inputs when skills are active. WP-7's `load_graph_hash` does NOT satisfy this (audit-only, not the §3.5b reuse hash).
- **PRE-EXISTING AUDIT GAP this WP must close (Codex BLOCKING-2):** `process/delivery-loop.md` is a *required* Acceptance load today, yet it is **not** bound in `_acceptance_resolver_graph` (`driver.py:3819-3907` binds the governance trio + role card + verdict schema but not delivery-loop.md). So an edit to delivery-loop.md does NOT currently invalidate Acceptance §3.5b reuse — a latent integrity hole. The plan must CLOSE it (by removing the proactive load below so it is no longer a proactive input), not inherit it.
- **ALL Acceptance delivery-loop triggers to retire (Codex R1-B1 + R2; §6 has MORE than
  the three below — the §E closure test over "§6 ALL bullets" is authoritative, incl. the
  `charter.yaml`-exists trigger at `context_briefing.md:334`):** (1)
  `role-cards/acceptance-agent.md:40`; (2) `governance/context_briefing.md:332-337` §6
  bullet "Your role is Acceptance Agent AND tooling.acceptance.mode ≠ off"; AND (3) the
  §6 bullet at `context_briefing.md:338` "scope_envelope_check, F5 evidence pattern, or
  calibration" — Acceptance ALWAYS handles F5/calibration, so this third trigger also
  pulls whole delivery-loop into every Acceptance session. The acceptance-kernel MUST
  inline the proactive F5 (§4.2.6) + calibration (§4.2.4) content so none of (1)/(2)/(3)
  routes Acceptance to the whole doc.
- **NO on-demand fallback (Codex R2-B1 — the key fix):** the prior "read §4.2.x
  on-demand if the prompt is insufficient" is **rejected** — an on-demand read is a
  verdict-affecting Acceptance input that is NOT in `acceptance_input_hash`
  (= hash(prompt + resolver graph), `e2e_stage.py:410`, `driver.py:3983`), so it
  reopens the §3.5b gap conditionally. Instead: the acceptance-kernel is the **complete**
  proactive set; if a judge finds the projection genuinely insufficient it **HALTs for
  prompt refinement** via the existing resumable mechanism (`_acceptance_spec_refine_halt`,
  `driver.py:3583-3613`) — it NEVER reads unbound delivery-loop bytes. This keeps the
  prompt self-contained AND every verdict-affecting input inside the hash.
- **Files:** `driver.py:_project_acceptance_prompt` (3493-3581) + `_browser_evidence_prompt_section` (3798-3817); `role-cards/acceptance-agent.md:40`; **`governance/context_briefing.md:332-338` (§6, all three Acceptance-applicable bullets)**; `_acceptance_resolver_graph` (`driver.py:3819-3907`) + `test_e2e_acceptance.py`.
- **Change:** inline G7/G18/G21/G22/G23/G13 + F5/calibration proactive content (~+0.4–0.8K tok); remove every Acceptance-branch delivery-loop load instruction (1/2/3); add the "insufficient → refinement HALT, never unbound read" rule to the projected prompt. **Interim safety:** if staged, bind `delivery-loop.md` in `_acceptance_resolver_graph` first; remove that binding only once all three triggers are retired AND the kernel is proven equivalent (WP-EQ).
- **Constraints-preserved:** all proactive gates (§C.3) + F5/calibration — inlined or structurally enforced; equivalence proven by WP-EQ delivery-loop rows (all 14 anti-patterns).
- **Audit/hash:** prompt text feeds `acceptance_input_hash` (auto-tracks); post-retirement delivery-loop.md is NOT a proactive OR on-demand verdict input → correctly unbound; no unhashed input can affect a verdict.
- **Tests:** the 6 gap tests + F5/calibration kernel tests; **the §E LOAD-CLOSURE test** — enumerates every Acceptance-reachable load instruction (proactive + §6 conditional + §2.6 + role-card conditional incl. `role-skill-model.md`) and fails if ANY resolves to an unbound on-demand read; a guard that the projected prompt contains no "read X on-demand" instruction; a test that mutating `role-skill-model.md` changes Acceptance reuse inputs when skills active; an insufficiency case → refinement HALT; existing acceptance suite green.
- **Metrics:** −~6–12K tok/Acceptance spawn.
- **Acceptance-gate:** WP-EQ acceptance subset green; **load-closure test green (no unbound Acceptance input remains)**; canary acceptance on fix_required + pass + browser_e2e all route identically to baseline.
- **Rollback:** restore all retired load instructions (+ interim resolver bindings if applied). **Deps:** WP-EQ (incl. delivery-loop + role-skill-model rows), WP-7. **Risk:** MED–HIGH (gating role). **Est-gain:** ~6–12K/Acceptance spawn. **Non-goals:** prompt stays self-contained; no behavioral widening; no unbound on-demand fallback.

### WP-5 — role-specific cold-start projection (Close / Research / Deliver-plan)
- **Objective:** give one-line/non-code spawns a **complete but role-scoped** cold-start (NOT a generic "lite tier", which Codex rejected — Close/Deliver-plan emit gating verdicts, Research sets the closure contract).
- **Files:** `driver.py:1874` (close), `:1935` (research), `:2095` (deliver-plan) projections; per-role briefing lists in `context_briefing.md` §2.
- **Change:** each role loads constitution-core + its authoring-kernel subset + ONLY the briefing docs its task needs (e.g., Close needs deliver-close-taxonomy + scope-envelope rules, not the full Deliver §2.2 16K set).
- **Constraints-preserved:** each role's gating constraints retained (Close verdict gates loop; Research closure_contract is load-bearing).
- **Audit/hash:** these roles are audit-neutral on input_hash (prompt-only); see WP-7.
- **Tests:** WP-EQ per-role subset; canary close/research/decompose still emit valid gating artifacts.
- **Metrics:** Deliver-family ~44K→~18–22K; Research ~30K→~18K.
- **Acceptance-gate:** WP-EQ green; gating artifacts unchanged on canary.
- **Rollback:** restore full briefing lists. **Deps:** WP-2, WP-3. **Risk:** MED. **Est-gain:** large for these roles. **Non-goals:** NOT a capability downgrade; no role loses a constraint it enforces.

### WP-6 — lessons tiering (cap the only unbounded channel)
- **Objective:** bound `_lessons_block` without dropping matured guardrails.
- **Files:** `driver.py:1046-1068` (`_lessons_block`), `:1070-1076` (`_injected_ids`); `engine-kit/memory/memory_store.py:539-558` (`select`); `schemas/memory-entry.schema.json` (maturity field).
- **Change:** tier by maturity — **never** drop L2/matured regression-prevention lessons; apply a top-K (e.g. K≈10) + recency budget ONLY to L1 singletons; order by (maturity desc, occurrences desc). Record both injected AND suppressed ids in the spawn audit (extend `memory_injected`) so suppression is observable, not silent.
- **Constraints-preserved:** lessons are heuristics (not formal constraints) but a matured regression-prevention lesson must not silently vanish — hence the L2 floor.
- **Audit/hash:** extend `memory_injected` (+ `memory_suppressed`) payload field → `SPAWN_PAYLOAD_FIELDS` + test (forward-only).
- **Tests:** L2 never suppressed; L1 cap honored; audit records suppression.
- **Metrics:** lessons-block tokens bounded; no matured-lesson regression in bad-case suite.
- **Acceptance-gate:** bad-case suite that motivated each matured lesson still passes.
- **Rollback:** remove cap (revert to inject-all); for the `memory_suppressed` payload field use **deprecate, don't delete** (same ledger rule as WP-0/WP-7). **Deps:** WP-0, WP-7. **Risk:** MED (dropping a load-bearing lesson). **Est-gain:** bounds growth (small now, prevents drift). **Non-goals:** no blind count truncation.

### WP-7 — per-role cold-start fingerprint (close the transcript/audit gap)
- **Objective:** make Dev/Review/Close/Research kernel swaps **auditable**. Today their input_hash is prompt-only and the transcript records only prompt+output (`driver.py:728-769`), so which governance/kernel version they loaded is recorded NOWHERE (pre-existing gap, widened by kernels).
- **Files:** `driver.py:_spawn` (839-938); a Dev/Review analogue of `_acceptance_resolver_graph`; `make_spawn_payload`/`SPAWN_PAYLOAD_FIELDS`.
- **Change:** compute a `load_graph_hash` over each role's cold-start set (reusing `resolve_load_graph`) and record it in the spawn audit. The set MUST include CONDITIONAL hard-constraint sources that the role's config activates — notably `process/role-skill-model.md` when skills/sub-agent fan-out are configured (Codex R2-B2) — so a change to a conditionally-loaded constraint source is still recorded. Does NOT change dispatched context.
- **Constraints-preserved:** strengthens audit (fresh-session + per-spawn transcript invariant intact).
- **Audit/hash:** new payload field (forward-only; old ledgers verify).
- **Tests:** `load_graph_hash` changes when a kernel changes; chain still verifies.
- **Metrics:** every spawn's governance version now ledger-recorded.
- **Acceptance-gate:** audit test green.
- **Rollback:** **deprecate, don't delete** — same rule as WP-0: mark the field optional / version the event; do not remove the property while ledgers containing it exist.
- **ORDERING (Codex BLOCKING-4):** WP-7 MUST land **before** WP-2/WP-3/WP-4/WP-5 — those swap the Dev/Review/Close/Research cold-start, which is audit-NEUTRAL on `input_hash` (prompt-only) and therefore recorded NOWHERE until `load_graph_hash` exists. Swapping first = an unauditable window. Place WP-7 immediately after WP-0/WP-EQ (or fold `load_graph_hash` into the first kernel WP).
- **Deps:** WP-0, WP-EQ. **Risk:** LOW. **Est-gain:** 0 tok (audit integrity). **Non-goals:** not session reuse.

### WP-8 — AGENTS.md template trim + P3a metadata fix
- **Objective:** ship the root `AGENTS.md` template pre-trimmed (verbatim adopters pay ~838 tok/turn of onboarding prose); correct stale always-load metadata so a future "doc reconcile" can't reverse the kernels back into a 23K/turn regression.
- **Files:** root `AGENTS.md:1-13,113-119,136-154` (preamble/§5/§7/§8); the `minimal-greenfield` example shows the trimmed shape; metadata in `constitution.md:20,30,247`, `doc_governance.md:133`, `process/doc-responsibility-matrix.md:61,74,76`.
- **Change:** move human-onboarding prose to ONBOARDING/README; **PRESERVE §5 two-loop discipline + harness-wiring guardrails** (Codex: not onboarding). Relabel "@-include from AGENTS.md / always-load" → "role-session cold-start load (context_briefing §1.2); default Control-Plane session does NOT load these".
- **Constraints-preserved:** two-loop + harness wiring retained (resident guardrails).
- **Audit/hash:** framework `AGENTS.md` is in the resolver (`driver.py:3894-3897`) — content edit auto-rehashes (Acceptance); adopter AGENTS.md edits are adopter-side.
- **Tests:** `adopter_wiring_validator` still passes; resident-footprint check.
- **Metrics:** −~838 tok/turn for verbatim adopters; metadata self-consistent.
- **Acceptance-gate:** metadata claims match implemented model (no contradiction with `context_briefing.md:59` or the forbid list).
- **Rollback:** restore prose. **Deps:** **run AFTER WP-2/WP-3 land** (else relabel governance non-always-load with no kernel to replace it — Codex RISKY). **Risk:** LOW once ordered. **Est-gain:** ~838 tok/turn (resident). **Non-goals:** do NOT remove two-loop/harness-wiring (Codex DROPS-CONSTRAINT).

### WP-9 — context-budget lint (warning + waiver, NOT a hard ceiling)
- **Objective:** make context budget a checkable contract without violating the doctrine "sufficient context > artificially small context" (`process/context-passing-efficiency.md:36`).
- **Files:** new `engine-kit/validators/context_budget_report.py`; CI wiring.
- **Change:** per-role cold-start token **report** + **warning threshold** + oversized-section attribution + **waiver-with-rationale** (audit-recorded). Hard-stop ONLY for a clear anomaly (e.g., unbounded lesson concatenation), never for normal sufficient context.
- **Constraints-preserved:** doctrine respected (advisory, waivable).
- **Audit/hash:** none.
- **Tests:** warning fires over threshold; waiver suppresses with recorded rationale; anomaly hard-stops.
- **Metrics:** regression threshold catches future bloat.
- **Acceptance-gate:** lint runs in CI; no false hard-stop on a normal role.
- **Rollback:** disable lint. **Deps:** WP-0. **Risk:** LOW. **Est-gain:** prevents regression. **Non-goals:** no hard ceiling.

---

## E. Audit-migration matrix

Two hash mechanisms (verified): per-spawn `input_hash` = sha256(role+prompt) **prompt-only**
(`driver.py:851`, all roles); Acceptance-only `acceptance_input_hash` = hash(prompt +
**content-hashed resolver graph**) (`driver.py:3983`, `e2e_stage.py:410`), where the
resolver (`driver.py:3819-3907`) hashes the governance trio (`:3898-3906`), role card
(`:3860`), verdict schema (`:3857`). The ledger (`audit_log.py`) is hash-chained and
records input_hash + memory_injected + transcript paths — **never** governance content;
`verify_chain` recomputes over recorded bytes only.

| Change | Coupling | Resolver/hash action (file:line) | Tests to update | §3.5b reuse | Old ledgers verify? |
|---|---|---|---|---|---|
| constitution→core (Acceptance) | **COUPLED** | edit/repoint `driver.py:3899`; if full doc leaves proactive set, REMOVE its entry | `test_e2e_acceptance.py:712-728` | mismatch→re-spawn (fail-closed, correct) | **Yes** (universal) |
| constitution→core (Dev/Rv/Close/Research) | NEUTRAL (input_hash prompt-only) | none — but unrecorded → do **WP-7** | none required | n/a | Yes |
| doc_governance→authoring-kernel (Acceptance) | **COUPLED** | `driver.py:3900` repoint | `test_e2e_acceptance.py:715` | re-spawn | Yes |
| doc_governance→kernel (Dev/Rv) | NEUTRAL | none (WP-7) | none | n/a | Yes |
| Acceptance drops whole delivery-loop | **PRE-EXISTING GAP** — delivery-loop.md is a *required* Acceptance load (`acceptance-agent.md:40` + `context_briefing.md:332-337`) but is NOT resolver-bound, so today an edit to it does NOT invalidate reuse (latent hole). WP-4 closes it: retire BOTH load paths → it stops being a proactive input → correctly unbound. Interim: bind it in the resolver until both paths retired. | add no-proactive-load guard test; (interim) add+later-remove resolver entry | role-card edit rehashes | Yes |
| `role-skill-model.md` conditional Acceptance load (Codex R3) | **PRE-EXISTING GAP (conditional)** — when `charter.tooling.acceptance.skills` is non-empty, Acceptance loads `process/role-skill-model.md` (`acceptance-agent.md:253`), whose §4 (`role-skill-model.md:84`) are non-overridable verdict-affecting constraints — but it is NOT in `_acceptance_resolver_graph`, so editing it does NOT invalidate §3.5b reuse. **WP-7's `load_graph_hash` is audit-only and does NOT fix the reuse invariant.** WP-4 closes it per the load-closure invariant below: inline the §4 boundary constraints into the acceptance-kernel + remove the conditional read (refinement HALT if insufficient), OR conditionally bind `role-skill-model.md` in `_acceptance_resolver_graph` when effective Acceptance skills/fan-out are active. | inline OR conditional resolver entry; test that mutating `role-skill-model.md` changes Acceptance reuse inputs when skills active | re-spawn on change | Yes |
| acceptance-verdict schema slim | **COUPLED (auto)** | content-hash auto-tracks `driver.py:3856-3859` (no code change if path stable) | `test_pc_schemas.py` shape tests | re-spawn | Yes |
| other 3 schemas slim | NEUTRAL | none | schema shape tests | n/a | Yes |
| role-specific projection (new per-role fingerprint) | **NEW** | add resolver/`load_graph_hash` to `_spawn`; new `SPAWN_PAYLOAD_FIELDS` field | `test_audit.py:279-343`, `test_driver.py:2487-2513` | new keys; **Acceptance reuse is governed by `acceptance_input_hash` NOT `load_graph_hash` — `load_graph_hash` is audit-record only and is NOT a substitute for resolver binding on any Acceptance verdict-affecting input** | Yes (forward-only) |
| lessons tiering | field-only | extend `memory_injected`(+suppressed) | `test_audit.py` payload | n/a | Yes |
| AGENTS.md trim | COUPLED (auto, Acceptance) | content-hash auto-tracks `driver.py:3894-3897` | wiring validator | rehash | Yes |

**Cross-cutting prerequisite (Codex's #1 missed constraint):** every kernel WP that
touches the **Acceptance** load set MUST update `_acceptance_resolver_graph` +
`test_e2e_acceptance.py` in the same change. The dangerous failure is a **new-file**
kernel left unbound while cold-start points to it → audit hashes an undispatched file
and silently fails to bind the kernel. Non-hash stale refs to update for hygiene:
`adoption_status.py:141-145` (`_FRAMEWORK_MARKERS`), AGENTS.md §2 prose, and the
hand-maintained sync between AGENTS.md §2 and `driver.py:3898-3906`.

**ACCEPTANCE LOAD-CLOSURE INVARIANT (Codex R3 — closes the whole class, not instances).**
Round 1 found `delivery-loop.md`; round 3 found `role-skill-model.md` — both the same
bug: a verdict-affecting Acceptance input outside `acceptance_input_hash`. Patching
instances one at a time will keep finding more. So WP-4 + WP-EQ must enforce a
**closure check**: enumerate EVERY file an Acceptance session may load — proactive
(`context_briefing.md` §1.2/§2.5), conditional (`context_briefing.md` §6 all bullets;
§2.6 per-task lookups; role-card conditional loads like `acceptance-agent.md:40,253`),
and any on-demand — and PROVE each is exactly one of: (a) **inlined** in the projected
prompt / acceptance-kernel (so it is never read), (b) **bound** in
`_acceptance_resolver_graph` (so a change re-spawns), or (c) routed to the resumable
**refinement HALT** (so an insufficient projection halts rather than reading unbound
bytes). A new automated test enumerates Acceptance-reachable load instructions and
fails if any resolves to "unbound on-demand read". `load_graph_hash` (WP-7) records
governance version for audit but is explicitly NOT one of (a)/(b)/(c) — it does not
satisfy the §3.5b reuse invariant for Acceptance.

---

## F. Measurement & experiment design (Phase 0 detail)

- **Baseline artifact:** per-(role, fix_round) table of {prompt_tokens, cold-start
  tokens by file, lessons tokens, schema tokens, role-card tokens}, plus campaign
  aggregate (spawns × cold-start). Produced by WP-0's sizer (static, no spawn) +
  spawn-payload prompt_bytes (live).
- **Why observation-only:** sizer reuses `resolve_load_graph` (read+hash, no write,
  no LLM); `len(prompt.encode())` reads an already-built string. Neither alters dispatch.
- **Representative scenarios:** one greenfield campaign (Research→Deliver→Dev→Review→
  Acceptance, ≥2 fix-rounds, ≥1 milestone close) + one browser_e2e milestone + one
  quick-fix lane run. Sample matrix: every role × {round 0, round 1} × {static, browser}.
- **Outcome metrics (quality, must not regress):** task completion; malformed-verdict
  rate; validator-rejection rate; fix-round count; review findings count; governance
  regressions (§1.7 breach / scope / eval-widening — 0 tolerated); missing-evidence
  incidents; stop-and-surface correctness; human-override/waiver rate.
- **Golden adversarial constraint probes (Codex non-blocking):** campaign-level outcome
  metrics are necessary but NOT sufficient — they can miss a single dropped constraint.
  For EVERY kernel constraint row (WP-EQ) — **including the conditional
  `role-skill-model.md` §4 rows, probed with skills/fan-out active** — add a targeted
  probe scenario that would trigger a violation if that constraint were absent (e.g., a
  Dev prompt that tempts a keyword-fix for a semantic failure → must still refuse; an
  Acceptance run with a contract-gap → must route research_contract_revision; a
  fan-out config that tempts a boundary breach → must be refused). A kernel WP passes
  only if all its rows' probes pass. These are deterministic regression fixtures, not just a campaign.
- **Comparison method:** A/B the SAME canary campaign at baseline (full docs) vs each
  increment, diffing token volume AND outcome metrics, across **≥3 repeated runs** (LLM
  non-determinism) — report distribution, not a single run. Accept an increment only if
  token↓ AND every quality metric flat-or-better AND all golden probes pass.
- **Acceptance threshold:** the 45–50% target is a hypothesis; report the MEASURED
  per-role reduction. No increment ships on an estimate.

---

## G. Rejected alternatives (permanent record — do not reintroduce)

1. **Verdict schemas pure-on-demand (old P1d).** Inline prose is provably INCOMPLETE
   vs the schema (enums, additionalProperties, evidence-path regex `^eval/runs/.+`,
   conditional browser/static fields, fix-required allOf). Deferring → malformed
   verdicts → wasted rounds = net token LOSS. **Instead: WP-1 slims the schema, keeps it loaded.**
2. **Generic "lite tier" for Close/Research/Deliver-plan (old P1e).** These emit
   GATING verdicts / set the closure contract (`deliver-agent.md:203`,
   `deliver-close-taxonomy.md:149`); a generic strip drops gating constraints.
   **Instead: WP-5 role-specific COMPLETE projection.**
3. **Fix-round session reuse (old P2b).** Violates the fresh-session / per-spawn
   transcript audit invariant (`constitution.md:340`, `driver.py:2724`); hidden
   session history = unauditable context. **Instead: fix-rounds stay fresh + delta-only (already are).**
4. **Orchestrator-side provider prefix-caching as a token lever (old P2a).**
   Not orchestrator-controllable (this is a claim about orchestrator control, not about
   every provider-internal optimization): orchestrator shells to `claude -p` (can't set
   `cache_control`); governance enters via agent mid-session Reads (not a stable
   prefix); fresh per-spawn sessions + 5-min TTL + 4096-tok Opus minimum + per-spawn-
   unique prompts ⇒ no cross-spawn reuse. **Instead: read-volume reduction (kernels).**
   (Claude Code's own internal caching of ITS system prompt is out of scope and does
   not cover the aidazi cold-start reads.)

---

## H. Recommended first milestone (smallest low-risk, measurable)

**Milestone 1 (two sub-increments, each independently reviewed + committed):**
- **Milestone 1A = WP-0 (measurement baseline).** Makes cold-start volume observable —
  precondition for any reduction claim. Built from a clean *integrated* SHA (after the
  in-flight dirty work is committed), in an isolated worktree.
- **Milestone 1B = WP-1a (research-brief slim-in-place pilot).** The safest concrete
  reduction: agent-only reader, **no Python validator, no audit coupling**,
  semantic-preservation provable — validates the slim technique end-to-end on a
  zero-blast-radius target. Depends on WP-0 (to measure the delta).
- Do **not** touch constitution/kernels, WP-1b, or any coupled schema in Milestone 1
  (one attributable variable; kernels need WP-EQ + Codex review first).

**Sequence (risk-ascending, dependency-corrected — deviates from the original
suggested order because caching is dropped and audit-migration is per-increment, not
a final step):**
1. WP-0 measurement (Milestone 1A) → 2. WP-1a research-brief slim-in-place pilot
   (Milestone 1B) → 3. WP-EQ equivalence harness + complete inventory (inventory
   completeness reviewed before any kernel) → 4. **WP-7 per-role fingerprint (MUST
   precede every cold-start swap — Codex BLOCKING-4)** → 5. WP-1b compact projections
   (review/acceptance/charter) → 6. WP-2 constitution-core → 7. WP-3 authoring-kernel →
8. WP-4 acceptance-kernel + load-closure (closes ALL delivery-loop paths + role-skill-model
   + the resolver gap) → 9. WP-5 role-specific projection → 10. WP-6 lessons tiering →
11. WP-8 AGENTS.md trim + metadata (AFTER WP-2/3) → 12. WP-9 context lint →
13. full comparative evaluation.
Each audit-coupled WP carries its OWN resolver + test update in the same increment
(never deferred to a final audit-migration step), and each is preceded by the
implementation-baseline revalidation (§D preamble).
Each increment: one attributable variable, its own audit/hash update, its own rollback.

---

## Stop-and-surface log (per the task's §19)

- 45–50% target currently has **no measurement basis** → reframed as hypothesis;
  WP-0 establishes the baseline before any reduction claim. (Surfaced, not blocking.)
- Provider caching is **not observable/applicable** as built → P2a rejected (§G).
  Does NOT block the kernel lever. (Surfaced.)
- No other §19 condition triggered: a canonical load graph EXISTS (`context_briefing.md`
  §1.2/§2 + resolver); kernel↔constraint equivalence is achievable and designed
  (WP-EQ); audit hash binds dispatched context (resolver); schema slimming provably
  preserves validation; lesson maturity has a usable field; no invariant violation is
  required to hit the goal.

---

## Review-gate log

- **Round 1 — Codex gpt-5.5 xhigh, read-only (2026-06-26): BLOCK → revised.** Four
  blocking findings, all incorporated:
  - **B1** WP-4 missed the second proactive `delivery-loop.md` load path
    (`context_briefing.md:332-337` §6, not just `acceptance-agent.md:40`) → WP-4 now
    retires both + adds a no-proactive-load guard test.
  - **B2** `delivery-loop.md` is a required-but-**unbound** Acceptance load today (latent
    audit gap) → WP-4 + §E now close it (retire → unbound-correct; interim bind).
  - **B3** WP-EQ inventory was condensed/incomplete (missed the 14 delivery-loop
    anti-patterns + role-skill/fan-out rows) → WP-EQ now requires an EXHAUSTIVE
    row-level inventory across constitution + context_briefing + delivery-loop §4.2.x +
    all 5 role cards, with the inventory's completeness itself reviewed before any kernel.
  - **B4** dependency order ran kernel swaps before WP-7 (the fingerprint that makes them
    auditable) → resequenced: WP-7 immediately after WP-0/WP-EQ, before WP-2/3/4/5.
  - Non-blocking folded in: "~25 of 41" demoted to provisional; bytes-vs-token-estimate
    labeling; golden adversarial constraint probes + ≥3 repeated A/B runs (§F);
    deprecate-don't-delete rollback for all audit payload fields; P2a phrased as
    "not orchestrator-controllable."
- **Round 2 — Codex gpt-5.5 xhigh, read-only (2026-06-26): BLOCK → revised.** B4 +
  all non-blocking confirmed RESOLVED; B1/B2/B3 were PARTIAL with two precise residual
  holes, both incorporated:
  - **R2-B1** WP-4's "read delivery-loop on-demand if prompt insufficient" still let
    verdict-affecting bytes enter outside `acceptance_input_hash` (conditional reopening
    of the §3.5b gap), and the §6 F5/calibration trigger (`context_briefing.md:338`) is a
    THIRD Acceptance delivery-loop path → WP-4 now: complete kernel (F5/calibration
    inlined), NO on-demand fallback, insufficiency → resumable refinement HALT
    (`_acceptance_spec_refine_halt`), retire all THREE §6 triggers, guard test forbids any
    on-demand instruction.
  - **R2-B2** WP-EQ inventory still omitted `process/role-skill-model.md` §4 (5
    non-overridable boundary constraints, conditionally loaded by all role cards on
    skills/fan-out) → added to the inventory (tagged `condition: skills_or_fanout_active`),
    the golden probes, and WP-7's conditional `load_graph_hash` set.
- **Round 3 — Codex gpt-5.5 xhigh, read-only (2026-06-26): BLOCK → revised.** R2-B1 and
  R2-B2 confirmed RESOLVED. Independent sweep found a THIRD instance of the same class:
  `process/role-skill-model.md` §4 (non-overridable, conditionally loaded by Acceptance on
  skills) is a verdict-affecting input outside `acceptance_input_hash`; WP-7's
  `load_graph_hash` is audit-only and does not fix the §3.5b reuse invariant. Fix
  generalized to a **LOAD-CLOSURE INVARIANT** (§E): enumerate EVERY Acceptance-reachable
  load and prove each is inlined / resolver-bound / HALT-gated, with an automated closure
  test — closing the class, not just the instance. `role-skill-model.md` handled in WP-4
  (inline §4 or conditional resolver bind).
- **Round 4 — Codex gpt-5.5 xhigh, read-only (2026-06-26): APPROVE.** R3 fix confirmed
  RESOLVED; independent exhaustive sweep of Acceptance-reachable loads found NO fourth
  instance outside the load-closure invariant (it enumerated extra candidates —
  `compact-acceptance-prompt.md`, prior acceptance reports, the `charter.yaml`-exists §6
  trigger, §2.6 lookups — all caught generically by the invariant + closure test). No
  remaining blocking design-level issue. Caveat (implementation-review, not design): the
  closure test must actually instantiate §6 ALL bullets, §2.5 proactive loads, §2.6
  lookups, optional prior reports, and skills-active cases — folded into WP-4 + §E.
- **Status: design spec APPROVED for adoption.** Remaining risks are implementation-review
  risks handled by each WP's own acceptance gate (esp. WP-EQ inventory completeness +
  the load-closure test). No code implemented; not yet built.
- **Post-approval revision (2026-06-26, two additive edits — lightweight Codex re-confirm):**
  (a) added the **implementation-baseline revalidation** precondition to §D (every WP must
  re-resolve its anchors against the integrated tree, since this doc was written against a
  dirty tree); (b) split WP-1 into **WP-1a** (research-brief slim-in-place pilot, zero
  coupling → Milestone 1B) and **WP-1b** (review/acceptance/charter compact projections,
  audit-coupled). §H Milestone 1 + sequence updated accordingly. No principle/invariant
  changed; both edits are additive and tighten implementation safety.
