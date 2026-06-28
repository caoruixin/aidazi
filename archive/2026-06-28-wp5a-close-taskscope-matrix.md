# WP-5A — Close task-scoped cold-start loading · Phase-1 analysis matrix

Read-only analysis. NO runtime change yet. This is the gate artifact: Codex `gpt-5.5 xhigh` reviews the
analytical correctness (esp. each "this doc has no Close dependency" adversarial judgment + the fail-closed
boundary), then the human signs off, THEN Phase-2 implements. Worktree `../aidazi-wp0`, branch
`wp0-measurement`, baseline `ec4dc25` (clean, in sync with origin).

**Review status:** Codex `gpt-5.5 xhigh` matrix gate (WP5A-MATRIX-R1) = **APPROVE, 0 blocking** (`.runs/wp5a/reviews-matrix-r1/`). 6 non-blocking accuracy refinements applied below (marked ⟢): the load-bearing one is that the driver does NOT run a deterministic `scope_envelope_check` at close — `in_scope` is Deliver-self-claimed (documented enforcement gap, constitution-core §"inherited gaps"), so scope-honesty is a **no-programmatic-backstop close JUDGMENT** the retained kernel must hold (which it does). Conclusion (drop-all-9, fail-closed) unchanged.

Scope (LOCKED, from the human-approved WP-5 memo): the same `deliver` role serves two tasks — **Close**
(`_spawn("deliver", schema_key="close")`) and **Deliver-plan** (`_spawn("deliver", schema_key="deliver_plan")`).
Make Close drop the Deliver-plan-only cold-start docs WITHOUT reducing any constraint the close-verdict
depends on. Deliver-plan keeps its current full load. Shared kernel / role boundary / closure-evidence-Human-gate
constraints UNREDUCED.

---

## 1. Phase-0 truth table (as-built at `ec4dc25`, re-resolved by symbol)

| Dimension | Finding (file:symbol) |
|---|---|
| **Task identity** | Close = `_step_close` → `_spawn("deliver", prompt, schema_key="close")` (`driver.py:1947`). Deliver-plan = `_step_decompose` → `_spawn("deliver", …, schema_key="deliver_plan")` (`driver.py:2173`). `schema_key` is a **fixed string literal** at each call site (same keys registered in `load_verdict_schemas`, `driver.py:268`). `schema_key in {"close","deliver_plan"}` distinguishes the two tasks with **zero prompt parsing** ⇒ satisfies HARD-CONSTRAINT A. |
| **`_spawn` signature** | `_spawn(self, role, prompt, schema_key, *, lessons_block=None)` (`driver.py:867`). No `task_kind` param today. `schema_key` consumed only for verdict-schema pick (`:948`) + verdict/artifact audit branch (`:972`). |
| **Cold-start load model** | `load_sizer.role_cold_start_roots(role, *, skills_active)` (`load_sizer.py:223`) = `GOVERNANCE_TRIO + ROLE_COLD_START[role]` (+ conditional `ROLE_SKILL_MODEL` when `skills_active`). Returns `(rel,purpose)` tuples. **Role-keyed only — no task dimension.** Single source of truth for both the WP-0 sizer and the WP-7 hash (`load_sizer.py:229-231`). |
| **`ROLE_COLD_START["deliver"]`** | `load_sizer.py:106-118` — 11 entries: role-card + 6 process briefings + 4 templates. Identical for Close and Deliver-plan today. |
| **WP-7 fingerprint** | `cold_start_load_graph_hash(role, *, repo_root, skills_active)` (`load_sizer.py:244`), basis = `{"role", "cold_start_graph":[{path,purpose,sha256}]}` (bytes excluded). **`task_kind` NOT in the hash.** Driver wrapper `_cold_start_load_graph_hash(role, skills_active)` (`driver.py:844`, best-effort→None), written at `driver.py:958/980/995`. |
| **Audit coupling (Close)** | Close uses prompt-only `input_hash = sha256(role+"\x00"+prompt)` (`driver.py:886`). Close is **NOT** in `_acceptance_resolver_graph`; it has **no `acceptance_input_hash`** and no resolver-graph binding. ⇒ "Acceptance untouched" is satisfied trivially; the only per-spawn signal of the cold-start set is the WP-7 `load_graph_hash`. |
| **Read channel** | Prompt builders embed **nothing** (`_step_close` / `_step_decompose` are terse one-liners; `driver.py:1943-1946`, `:2167-2172`). The live agent's cold-start reads are driven by **authored instructions**: `role-cards/deliver-agent.md §1` + `governance/context_briefing.md §2.2`. `load_sizer.ROLE_COLD_START` is a STATIC MIRROR of those, kept in lockstep by `test_coldstart_consistency.py` (WP-3 4-way invariant). |

**Consequence for the mechanism:** the runtime token saving only materializes if the live Close agent
actually stops *reading* the dropped docs. That is an authored-instruction change (like WP-4B), not a
sizer-only change. The sizer + WP-7 hash are the measurement/audit mirror and must move in lockstep.

---

## 2. The deliver × task_kind cold-start load matrix

Legend: ● always loaded · ○ dropped at Close (loaded for Deliver-plan) · △ conditional (skills/track) · — n/a

| # | Cold-start root | purpose | bytes | Deliver-plan (`deliver_plan`) | Close (`close`) | basis |
|---|---|---|---|:--:|:--:|---|
| — | governance/constitution-core.md | governance | 22,611 | ● | ● | shared kernel |
| — | governance/authoring-kernel.md | governance | 12,328 | ● | ● | shared kernel |
| — | governance/context_briefing.md | governance | 24,329 | ● | ● | shared kernel |
| — | role-cards/deliver-agent.md | role_card | 18,108 | ● | ● | the role card itself (close procedure §3.5/§5/§5.1/§7) |
| 1 | templates/deliver-close-taxonomy.md | briefing | 8,923 | ● | ● | **THE close-verdict taxonomy (A/B/C/D + §1.7-at-close)** |
| 2 | process/milestone-framework.md | briefing | 9,672 | ● | ○ | plan decomposition; next_subsprint driver-overridden |
| 3 | process/tech-architecture-decision-catalog.md | briefing | 7,304 | ● | ○ | Δ-3 plan-time arch decisions |
| 4 | process/typeA-runtime-architecture-skeleton.md | briefing | 12,431 | ● | ○ | Δ-6 plan/build scaffolding |
| 5 | process/artifact-taxonomy.md | briefing | 11,953 | ● | ○ | Δ-12 (see §4 medium-confidence) |
| 6 | process/post-deployment-iteration.md | briefing | 13,623 | ● | ○ | Δ-9 OBS triage / fix-layers (downstream) |
| 7 | process/common-detours-and-warnings-typeA.md | briefing | 9,370 | ● | ○ | Δ-17 plan/dev pitfalls |
| 8 | templates/sprint-objective.md | briefing | 4,031 | ● | ○ | author-time blank template |
| 9 | templates/milestone-objective.md | briefing | 4,981 | ● | ○ | author-time blank template |
| 10 | templates/compact-dev-prompt.md | briefing | 7,409 | ● | ○ | author-time dev-prompt template |
| — | process/role-skill-model.md | briefing | (cond) | △ | △ | skills_active gate (UNCHANGED, not task-scoped) |

Close-scoped briefing set = **{deliver-close-taxonomy.md}** only. Everything Deliver-plan-specific (rows 2–10)
drops at Close.

---

## 3. Adversarial per-candidate constraint analysis

Method: one read-only adversary per candidate, instructed to try HARD to prove the doc IS required to emit a
correct, honest `deliver-close-verdict` (fail-closed: doubt → KEEP). All 9 returned **CLOSE-IRRELEVANT**. The
decisive structural fact across all of them: **`_step_close` SETS verdict fields only; it authors no file.**
Every activity that needs a dropped doc (milestone decomposition, sprint/dev-prompt authoring, plan-fix,
OBS→R-item promotion) is a **separate downstream `_spawn`** (`deliver_plan` / dev / `spawn_deliver_plan_fix`)
that loads the doc itself — confirmed: `deliver-close-verdict.schema.json` required fields are
`{verdict, blocking_count, worst_severity, in_scope, next_subsprint, reason}`, `additionalProperties:false`,
no authoring field.

| Doc | Verdict | Conf | Why Close-irrelevant | Backstop if any close-adjacency exists |
|---|---|---|---|---|
| sprint-objective.md | CLOSE-IRRELEVANT | HIGH | blank author-time template; close READS filled runtime `docs/sprint_objective.md`, never the form | authoring is `_step_decompose` (`deliver_plan`) |
| milestone-objective.md | CLOSE-IRRELEVANT | HIGH | blank author-time template; close judges scope as a JUDGMENT against `charter.approved_scope` (⟢ no deterministic `scope_envelope_check` at close; `in_scope` is Deliver-self-claimed, `driver.py:2895`) | authoring is `_step_decompose` |
| compact-dev-prompt.md | CLOSE-IRRELEVANT | HIGH | `_step_close` cannot emit plan-fix fields (close schema has no dev-prompt field). ⟢ The current driver does NOT spawn a plan-fix from close; review `fix_required` is handled BEFORE close — auto-fix re-enters Dev/Review directly (`driver.py:2687`). | `_step_decompose`; (spec-only `spawn_deliver_plan_fix`) |
| tech-architecture-decision-catalog.md (Δ-3) | CLOSE-IRRELEVANT | HIGH | arch-conformance is the **Code Reviewer's** job (surfaced in `codex-findings.md`); §1.7-A binding rule is in always-load `constitution-core.md §1.7-A`. Catalog is plan-time "how to decide". | constitution-core §1.7-A; reviewer findings |
| typeA-runtime-architecture-skeleton.md (Δ-6) | CLOSE-IRRELEVANT | HIGH | runtime scaffolding; `layers` vocab belongs to `deliver-plan-fix.schema.json` (separate spawn), canonical layer source is Δ-9 not Δ-6 | `_step_decompose`; reviewer verdict |
| post-deployment-iteration.md (Δ-9) | CLOSE-IRRELEVANT | HIGH | fix-layer / OBS-triage feeds `spawn_deliver_plan_fix` + decompose; OBS→R-item promotion is **human-resolved** (delivery-loop §4.2.8 #11), post-HALT | `spawn_deliver_plan_fix`; human gate |
| common-detours-and-warnings-typeA.md (Δ-17) | CLOSE-IRRELEVANT | HIGH | 4 pitfalls are Research/Dev/plan concerns; its two "close" mentions treat close as where detours *surface*. Close-honesty constraint lives in close-taxonomy §1.7 + constitution-core §1.7 | close-taxonomy §1.7; constitution-core §1.7 |
| **milestone-framework.md** | CLOSE-IRRELEVANT | **med→high** | §4 milestone-close housekeeping is Close-*adjacent* (file-authoring, not a verdict input); ⟢ terminality anchors to `approved_scope.subsprint_sequence`, so a Deliver `next_subsprint` omission is *ignored* for terminality (`_milestone_complete`, `driver.py:2998-3004`) | driver `_milestone_complete` (terminality anchor) |
| **artifact-taxonomy.md** (Δ-12) | CLOSE-IRRELEVANT | **med-high** | role-card §7-item-5 write-path discipline fires when close writes handoff §12 / archives codex-findings; judged **redundant** — those exact write-targets are in KEPT `deliver-close-taxonomy.md §A` (`:33/41/47/55/75`) + role-boundary in `constitution-core.md §3.4 #1–#5` | deliver-close-taxonomy §A; constitution-core §3.4 |

**The two medium-confidence rows are the crux for review.** Both have a genuine close-adjacency, and both
were judged droppable because the constraint is **redundantly backstopped** by a doc Close KEEPS
(`deliver-close-taxonomy.md`) and the always-load kernel (`constitution-core.md §1.7 / §3.4`). Verified
directly: constitution-core carries §3.4 #1–#5 (`:188,210,255`) + full §1.7 (`:113-186`);
deliver-close-taxonomy carries the close write/archive discipline (`:33/41/47/55/75`) + §1.7-drop-is-a-breach
(`:153`); the driver anchors terminality to `subsprint_sequence` and ignores a `next_subsprint` omission
(`_milestone_complete`, `:2998-3004`).

---

## 4. Close retained set vs Deliver-plan full set (HARD-CONSTRAINT D check)

**Close retained cold-start set:**
- governance trio: constitution-core.md, authoring-kernel.md, context_briefing.md (shared kernel)
- role-cards/deliver-agent.md (full role card — close procedure §3.5/§5/§5.1, write-paths, Human-checkpoint/
  ship/waiver boundaries, §7 pre-output checklist)
- templates/deliver-close-taxonomy.md (A/B/C/D verdict taxonomy + §1.7-at-close)
- ADOPTER_STATIC: `<adopter>/AGENTS.md` + `docs/current/adoption-state.md` (dynamic, unchanged)
- on-demand (unchanged): full `constitution.md` + `doc_governance.md` per triggers
- conditional (unchanged): `role-skill-model.md` when `skills_active`

HARD-CONSTRAINT D line-item check:
- kernel trio → ● governance trio
- Deliver role hard constraints → ● role card + constitution-core
- close verdict / schema contract → ● role card §5 + deliver-close-taxonomy (+ orchestrator validates the schema)
- scope / evidence / closure honesty → ● constitution-core §3.4 + role card §7 + deliver-close-taxonomy §1.7.
  ⟢ NOTE: `in_scope` honesty has NO deterministic backstop (no `scope_envelope_check` at close; documented
  enforcement gap) — it is a close JUDGMENT, which makes RETAINING the kernel + taxonomy that carry it
  *more* important, not less. None of the 9 dropped docs carried this constraint uniquely.
- Human checkpoint / ship / waiver boundaries → ● role card; the C/D checkpoint + `scope_deviation` HALT are
  driver-enforced ROUTING on the agent's self-reported verdict (`_handle_close`, `driver.py:2879-2923`) — a
  programmatic *gate on the verdict*, but the verdict's honesty is still agent-held (above)
- ALL no-programmatic-backstop Close judgment constraints → ● none of them lived UNIQUELY in a dropped doc
  (every close-adjacency in the 9 has an independent backstop, §3 table)

**Deliver-plan full set = the current 11-entry `ROLE_COLD_START["deliver"]` (UNCHANGED).**

---

## 5. Unknown / missing task fail-closed contract (HARD-CONSTRAINT B)

`task_kind` ≡ the call-site `schema_key` literal (stable identity; never prompt-parsed). The narrowing is a
**positive allow-list of exactly one pair**:

```
TASK_SCOPED_COLD_START = { ("deliver","close"): [deliver-agent.md, deliver-close-taxonomy.md] }

role_cold_start_roots(role, task_kind, *, skills_active):
    roots = GOVERNANCE_TRIO
    scoped = TASK_SCOPED_COLD_START.get((role, task_kind))   # None unless EXACT ("deliver","close")
    roots += scoped if scoped is not None else ROLE_COLD_START[role]   # else FULL set
    + skills_active conditional (unchanged)
```

- known `("deliver","close")` → proven narrow set.
- known `("deliver","deliver_plan")` → falls through → FULL set (no entry) ✓.
- missing / None / unknown / any other `(role,task_kind)` → falls through → FULL set. **Never narrow.** ✓
- The narrow path requires an EXACT, recognized `("deliver","close")`; nothing defaults into it.

Runtime read directive (mechanism, §6) is emitted ONLY on the recognized close identity; on any other path no
narrowing directive is injected, so the agent follows the full role-card cold-start. On-demand discipline
(HARD-CONSTRAINT E): the Close directive names the dropped docs and instructs **HALT + report insufficiency**
if one is genuinely needed — explicit trigger, auditable (directive is in the prompt → in `input_hash`), no
silent fallback, never guess-then-close.

---

## 6. Proposed implementation mechanism (for review — built in Phase 2)

1. **Task identity:** thread `task_kind = schema_key` from `_spawn` into the cold-start path (no prompt
   parsing). `schema_key` is already a fixed literal per call site.
2. **load_sizer:** add `TASK_SCOPED_COLD_START` allow-list + `task_kind` param to `role_cold_start_roots`
   (fail-closed fall-through, §5). Thread `task_kind` through `size_role` / `cold_start_load_graph_hash` /
   `size_all_roles` / CLI. Single source of truth preserved.
3. **WP-7 hash (HARD-CONSTRAINT C):** fold `task_kind` into the `cold_start_load_graph_hash` basis →
   `{"role","task_kind","cold_start_graph"}`; thread through `driver._cold_start_load_graph_hash` + the 3
   `_spawn` write sites. (One-time forward shift of every role's `load_graph_hash` value — nullable,
   observation-only, old ledgers still verify.) `bytes`-exclusion + best-effort→None preserved.
   `acceptance_input_hash` UNTOUCHED (Close isn't in that path).
4. **Runtime read (the real saving):** `_step_close` injects an authoritative TASK-SCOPED COLD-START directive
   rendered from `role_cold_start_roots("deliver","close")` — "load exactly [close set]; do NOT load
   [dropped set]; HALT if you genuinely need one." `_step_decompose` unchanged (full set). Mirrors WP-4B's
   projected-prompt precedent.
5. **Authored-instruction reconciliation:** make `deliver-agent.md §1` + `context_briefing.md §2.2`
   task-aware (close vs decompose) so they don't contradict the directive; extend
   `test_coldstart_consistency.py` (WP-3 4-way invariant) + the denylist gate to be task-parameterized.
6. **Tests + drift gate:** task-aware `test_load_sizer` + `test_coldstart_consistency` + a WP-EQ-style
   guard that the Close-scoped set is a strict subset of the full set AND still contains the close-required
   roots (deliver-close-taxonomy + governance + role card).

---

## 7. Measured projected saving (load_sizer @ `ec4dc25`, not estimates)

Full deliver cold-start (today, both tasks) = **167,073 B / 41,768 tok** (governance 59,268 + role_card 18,108
+ briefing 89,697).

| Tier | Dropped at Close | bytes dropped | Close-scoped total | tok saved/close spawn |
|---|---|--:|--:|--:|
| **Recommended (all 9 proven)** | rows 2–10 | **80,774 B** | 86,299 B / 21,574 tok | **≈ 20,194 tok** |
| Fallback (keep the 2 medium) | rows 2,3,4,6,7,8,9,10 (not 5/milestone) | 59,149 B | 107,924 B | ≈ 14,787 tok |
| Conservative (templates only) | rows 8,9,10 | 16,421 B | 150,652 B | ≈ 4,105 tok |

Recommended = drop all 9 (each adversarially proven CLOSE-IRRELEVANT; the 2 medium rows redundantly
backstopped). Saving is **per Close spawn**, and Close is the highest-frequency deliver task (one per
sub-sprint). Static floor will rise slightly (~the directive block, à la WP-4B's +104 tok) — net saving
dominates; the read-trace canary (Phase 3) is the proof the live agent actually stops reading rows 2–10.

---

## 8. Open questions for the human (Phase-1 gate)

1. **Boundary:** adopt the recommended drop-all-9, or the fallback (keep artifact-taxonomy + milestone-framework
   for belt-and-suspenders on close-side write-discipline)? My recommendation: **drop all 9** — both medium rows
   are redundantly backstopped (§3/§4) and the adversaries found no real dependency.
2. **Directive vs task-conditional role card:** mechanism §6.4 uses an orchestrator-injected directive (most
   auditable, keys on `schema_key`). Confirm this over a purely role-card-conditional approach.
3. Everything in §6 is Phase-2 work, gated on this matrix + boundary being approved.
