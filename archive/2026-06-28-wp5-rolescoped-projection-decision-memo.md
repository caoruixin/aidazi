---
title: WP-5 — Role-scoped cold-start projection (Close / Research / Deliver-plan) — measure-first decision memo
doc_tier: framework-design
doc_category: live
status: proposal
implementation_status: not_started
source_of_truth: this file
last_reviewed: 2026-06-28
review_cadence: per implementation increment
supersedes: []
superseded_by: null
load_discipline: on-demand
notes: >
  WP-5 is deliberately MEASURE-FIRST: this memo is a read-only baseline + decision
  analysis. It does NOT presuppose "three narrow kernels" and makes NO runtime,
  load-graph, role-card, kernel, or cold-start change. It quantifies what Close,
  Research and Deliver-plan actually load at cold-start on HEAD e244716 (post
  WP-2/3/4) and recommends, per role, whether to project / share / keep unchanged.
  Reuses load_sizer.role_cold_start_roots / size_role (read-only) for all figures.
---

# WP-5 — Role-scoped cold-start projection: measure-first decision memo

**Branch / HEAD:** `wp0-measurement` @ `e244716` (origin-synced, clean tree).
**Scope:** Close, Research, Deliver-plan cold-start composition. **Read-only.** No runtime/load-graph/role-card/kernel/cold-start change in this session.
**Tooling:** `engine-kit/orchestrator/load_sizer.py` (`size_role`, `role_cold_start_roots`) at HEAD; WP-EQ constraint inventory (`engine-kit/tools/constraint-inventory/`); per-doc content classification by three read-only analysis passes. Byte→token estimate = `bytes // 4` (the sizer's documented estimate, NOT a tokenizer count).

---

## 0. Two structural findings that reframe the whole question

Before the numbers, two facts about the three roles changed what "a role-specific projection" even means here. Both were verified against HEAD, not assumed from the design spec.

### 0.1 Close and Deliver-plan are the SAME role at cold-start

- **Close** = `driver._step_close` → `_spawn("deliver", prompt, schema_key="close")` (driver.py L1942/1947) → emits `deliver-close-verdict`.
- **Deliver-plan** = `driver._step_decompose` → `_spawn("deliver", prompt, schema_key="deliver_plan")` (driver.py L2139/2173) → emits the milestone plan.
- **Research** = `driver._step_research` → `_spawn("research", prompt, schema_key=None)` (driver.py L1985/2014) → sets the closure contract.

Close and Deliver-plan load the **identical** cold-start set — same `deliver-agent.md` role card, same governance trio, same 10 briefing docs. They differ ONLY in the run-dynamic **task prompt** (and the verdict schema, which is the driver's validator input, not an agent cold-start load). So "the three roles" are really **two distinct cold-start sets**: `deliver` (Close + Deliver-plan) and `research`. A projection cannot make a "Close kernel" distinct from a "Deliver-plan kernel" without making cold-start **task-aware**, which the engine is not today (cold-start is role-keyed, not task-keyed).

### 0.2 The dominant per-role burden is `on-demand`-disciplined briefing the role card force-loads at cold-start

Post WP-2/3/4, the governance trio (`constitution-core` + `authoring-kernel` + `context_briefing`) is already a **shared, kernelized, identical-across-roles floor**. The remaining per-role load is the **role card + per-role briefing docs**. Measuring the briefing docs' own `load_discipline:` front-matter against what the role card §1 cold-start list instructs to load reveals a drift:

| role | briefing total | `on-demand` per own front-matter (force-loaded anyway) | `by-role` (genuinely cold-start) |
|---|---:|---:|---:|
| research | 30,900 B | **24,660 B** (domain-discovery, agent-design-elicitation, agent-creation-prereq) | 6,240 B (template + schema) |
| deliver | 89,697 B | **64,353 B** (all 6 process docs) | 25,344 B (4 templates) |

The role card §1 ("Load `milestone-framework.md` … `post-deployment-iteration.md` …") is the trigger that pulls these `on-demand` docs into cold-start — **uniformly, regardless of whether the task is Plan or Close**. This is the same drift class WP-3-follow-up (`67026dc`) reconciled for the always-load governance docs, **unreconciled for briefing docs**. It is the single biggest lever the data exposes — and it is **not** a kernel-projection lever.

> **Key uncertainty (gates everything below):** the sizer figure is *role-card-literal* — it counts what §1 instructs. Whether an agent actually loads all `on-demand` briefing at cold-start (role-card-literal) or defers it (front-matter-literal) is **not yet observed**. The WP-2/3 read-trace canaries showed agents DO follow explicit `context_briefing`/role-card "Load X" cold-start instructions, so the role-card-literal figure is the best current estimate — but this MUST be confirmed by a read-trace canary before committing to any lever (§7). If agents already defer, the saving is already realized and the sizer overcounts.

---

## 1. Current-state load tables (HEAD e244716, framework-static, skills-off)

### 1.1 Shared governance floor (identical on EVERY spawn, all roles)

| file | bytes | ~tokens |
|---|---:|---:|
| governance/constitution-core.md | 22,611 | 5,652 |
| governance/context_briefing.md | 24,329 | 6,082 |
| governance/authoring-kernel.md | 12,328 | 3,082 |
| **floor** | **59,268** | **14,817** |

This floor is the product of WP-2/3/4 and is *already* the shared-kernel model. WP-5 does not touch it.

### 1.2 Research (research role)

| layer | file | bytes | ~tok | discipline |
|---|---|---:|---:|---|
| governance | (trio, §1.1) | 59,268 | 14,817 | always |
| role_card | role-cards/research-agent.md | 11,767 | 2,941 | by-role |
| briefing | process/domain-discovery-process.md | 7,178 | 1,794 | on-demand |
| briefing | process/agent-design-elicitation.md | 8,743 | 2,185 | on-demand |
| briefing | process/agent-creation-prerequisites.md | 8,739 | 2,184 | on-demand |
| briefing | templates/compact-research-brief.md | 4,025 | 1,006 | by-role |
| briefing | schemas/research-brief.schema.json | 2,215 | 553 | (WP-1a slimmed) |
| **total (role-card-literal)** | | **101,935** | **25,483** | |
| *on-demand-discipline lower bound (gov+card+by-role only)* | | *77,275* | *19,318* | |

### 1.3 Deliver = Close + Deliver-plan (deliver role)

| layer | file | bytes | ~tok | discipline | plan/close |
|---|---|---:|---:|---|---|
| governance | (trio, §1.1) | 59,268 | 14,817 | always | both |
| role_card | role-cards/deliver-agent.md | 18,108 | 4,527 | by-role | both |
| briefing | process/milestone-framework.md | 9,672 | 2,418 | on-demand | both |
| briefing | process/tech-architecture-decision-catalog.md | 7,304 | 1,826 | on-demand | **plan-only** |
| briefing | process/typeA-runtime-architecture-skeleton.md | 12,431 | 3,107 | on-demand | plan-dominant |
| briefing | process/artifact-taxonomy.md | 11,953 | 2,988 | on-demand | both |
| briefing | process/post-deployment-iteration.md | 13,623 | 3,405 | on-demand | **neither** (post-ship) |
| briefing | process/common-detours-and-warnings-typeA.md | 9,370 | 2,342 | on-demand | neither/plan-advisory |
| briefing | templates/deliver-close-taxonomy.md | 8,923 | 2,230 | by-role | **close-only** |
| briefing | templates/sprint-objective.md | 4,031 | 1,007 | by-role | **plan-only** |
| briefing | templates/milestone-objective.md | 4,981 | 1,245 | by-role | plan-dominant |
| briefing | templates/compact-dev-prompt.md | 7,409 | 1,852 | by-role | **plan-only** |
| **total (role-card-literal)** | | **167,073** | **41,768** | | |
| *on-demand-discipline lower bound (gov+card+by-role only)* | | *102,720* | *25,680* | | |

### 1.4 All-roles context (for frequency weighting)

| role | total bytes | ~tok | cold-start frequency (qualitative) |
|---|---:|---:|---|
| research | 101,935 | 25,483 | LOWEST — ~1× per milestone (intake gate) |
| deliver (plan) | 167,073 | 41,768 | LOW–MOD — 1× per milestone decompose + 1× per fix-iteration |
| deliver (close) | 167,073 | 41,768 | **HIGHEST of the three** — 1× per sub-sprint close (3–5 per milestone) + fix closes |
| dev | 92,610 | 23,152 | (out of WP-5 scope) |
| review | 82,149 | 20,537 | (out of WP-5 scope) |
| acceptance | 137,465 | 34,366 | (WP-4 already kernelized) |

---

## 2. Unique (deletable) burden per role

"Unique burden" = the per-role load that is NOT the shared governance floor (= role card + briefing). This is the only volume a role-specific lever can touch.

| role | role card | briefing | **unique total** | unique ~tok | % of role load |
|---|---:|---:|---:|---:|---:|
| research | 11,767 | 30,900 | **42,667** | 10,666 | 42% |
| deliver (Close=Plan) | 18,108 | 89,697 | **107,805** | 26,951 | 65% |

Composition of that unique burden, by constraint character:

- **Role cards are the constraint-bearing core, and a minority of the bytes.** Research card = 28% of its unique burden; deliver card = 17%. The WP-EQ inventory (role cards only) finds **research card: 34 constraints, ~30 with no real programmatic backstop (4 real = 1 driver + 3 schema); deliver card: 46 constraints, ~40 with no real backstop (6 real = 2 driver + 2 schema + 1 campaign + 1 driver).** ~87–88% of role-card constraints live ONLY in prose → a card kernel must carry them meaning-preserved (WP-2/3 discipline) and constraint-loss risk is real.
- **The briefing docs are the BULK and are NOT in any constraint inventory** — WP-EQ deliberately scoped them out as reference/knowledge, not constraint sources. The three read-only classification passes confirm this: across all 13 briefing docs the content is ~10–30% hard-constraint, ~30–78% reference/enum/taxonomy/template (consult-surface, must stay verbatim), ~20–53% rationale/example/duplication (strippable). Template docs (`compact-dev-prompt`, `sprint/milestone-objective`, `compact-research-brief`, `deliver-close-taxonomy`) are copy-targets — 62–78% verbatim reference, only 18–35% compressible.

**Implication:** the deletable-by-compression fraction is genuinely there but modest, and the largest unique-burden blocks (deliver's 64KB of `on-demand` process docs) are reference the *task that needs them* genuinely consults — their waste is being loaded for the *wrong* task (Close loading planning aids), not being verbose.

---

## 3. Candidate projection boundaries

Three boundary shapes are coherent given §0:

- **P-research** — one kernel projecting `research-agent.md` + its 4 prose briefing docs (schema already WP-1a-slimmed). Complete projection (all 34 card constraints + briefing rules carried; reference verbatim).
- **P-deliver-single** — one kernel projecting `deliver-agent.md` + all 10 briefing docs. Carries both Plan and Close content (does NOT fix the cross-task waste of §0.1).
- **P-deliver-split** — two task kernels (`deliver-plan-kernel`, `deliver-close-kernel`), each carrying only its task's content. Requires making cold-start **task-aware** (new capability).

And one boundary the measurement surfaced that is **not a projection at all**:

- **L-taskscope** — task-scoped *loading*: the (already task-aware) dispatch prompt carries a task-specific load_list so a Close spawn loads only close-relevant docs and a Plan spawn only plan-relevant docs; on-demand process docs are loaded per trigger, not force-loaded by a coarse §1 list. No constraint is rewritten; no kernel/coverage artifact is created.

---

## 4. Measured savings for A / B / C (+ the measured-better option)

All per-spawn figures are *additional* savings on top of the WP-2/3/4 floor. Compression %s are the three classifiers' realistic estimates (calibration: WP-2 constitution ~75%, WP-3 doc_governance ~25%; these reference/template docs land 18–50%).

### A. Keep the current shared-kernel model unchanged (baseline)
- **Savings:** 0 tok. **Artifacts:** none. **Load-graph / `load_graph_hash`:** unchanged. **Audit/resolver:** none. **Drift/maintenance:** none. **Constraint-loss risk:** none.

### B. One shared compact projection for the three roles
- Given §0.1, "the three roles" = two disjoint cold-start sets (deliver, research). Their unique content is **near-disjoint** (different role cards; research reads elicitation/discovery docs, deliver reads architecture/milestone/close docs). The only shared content is the governance trio — **already kernelized**.
- **Measured shared-compressible content ≈ 0 useful tokens.** A single kernel covering both would either (a) hold only the empty intersection (no benefit), or (b) hold the union → each role loads the OTHER role's content (a *negative*: research would gain deliver's unique content ≈ **+26.9K tok**; deliver would gain research's unique content ≈ **+10.7K tok**).
- **Artifacts:** 1 kernel + 1 coverage map + harness mode. **Load-graph:** both roles repoint. **Risk:** union-loading regression. **Verdict: incoherent for these roles; reject.**

### C. Separate role-specific projections
- **P-research:** under the measured (role-card-literal) baseline, card ~30% (~880 tok) + briefing prose ~38% blended (~2,720 tok) ≈ **~3,600 tok/spawn**. This figure is *conditional on §0.2*: ~24,660 B (≈6,165 tok) of that briefing is `on-demand` (largely Path-1 greenfield elicitation), so IF the read-trace canary (§7) shows agents defer it, the realized saving collapses toward the card-only ~880 tok — **below the ~1K significance reference**. Either way Research is the **lowest-frequency** role → lowest aggregate benefit, and a research kernel is the largest-drift artifact (5 sources) for the smallest assured win.
- **P-deliver-single:** card ~30% (~1,360 tok) + briefing ~39% blended (planning ~5,049 + close ~3,800 ≈ **~10,200 tok/spawn**). Material per-spawn, BUT a single kernel **locks in the cross-task waste** (Close still carries planning content) and is the largest, highest-drift coverage artifact of any option.
- **P-deliver-split:** ≈ the task-scoping saving (§L-taskscope, which drops non-task docs *entirely*) PLUS compression of only the few *retained* task-specific docs. It cannot also count compression on docs task-scoping already drops — that would double-count. For Close the marginal compression over task-scoping is small (≈ `deliver-close-taxonomy` 35% ≈ 780 tok + card compression), so the split's benefit ≈ task-scoping + a modest increment. It is the only option that captures *both* levers, but at the highest complexity (2 kernels + 2 coverage maps + task-aware load model + drift gate).

| option | per-spawn saving | artifacts | risk | maintenance |
|---|---:|---|---|---|
| P-research | ~3.6K role-card-literal; realized may collapse to ~0.9K card-only | kernel + coverage + harness | card 87% prose constraints → real loss risk | 4 prose docs + card as sources, source-hash drift |
| P-deliver-single | ~10.2K tok | kernel + coverage + harness | dense reference; doesn't fix task waste | 10 docs + card as sources |
| P-deliver-split | ≈ task-scope + small retained-doc compression (no double-count) | 2 kernels + 2 coverage + task-aware model | as above + split-correctness | highest |

### The measured-better option (not a projection): L-taskscope
This beats B and the single-kernel C options (P-research, P-deliver-single) on benefit, and beats *every* option — including the two-kernel split — on risk, maintenance, and next-step leverage. (The split can reach a marginally higher benefit, but only by also paying for two kernels + task-aware cold-start.) It is what "measure first" actually surfaced:

| task | drop (whole docs the task does not use) | **saving / spawn** | risk |
|---|---|---:|---|
| **Close** | tech-catalog, typeA-skeleton, post-deployment, common-detours, sprint-obj, milestone-obj, compact-dev-prompt | **59,149 B ≈ 14,787 tok** | near-zero — drops only non-close-verdict docs; keeps gov trio + full card + `deliver-close-taxonomy` (the verdict definition) + milestone-framework + artifact-taxonomy |
| Close (optional sub-doc slice of the 2 kept process docs) | + ~16.8 KB more | + ~4,200 tok | low (becomes a partial projection) |
| **Deliver-plan** | deliver-close-taxonomy, post-deployment (+optionally common-detours) | **22,546–31,916 B ≈ 5,637–7,979 tok** | near-zero — drops close/post-ship docs the decompose never uses |

> **The table figures are role-card-literal UPPER bounds. There is also a canary-independent FLOOR (§0.2):** even if the canary shows every `on-demand` doc is *already* deferred at cold-start, the `by-role` templates are still cold-loaded and still task-mismatched, so L-taskscope keeps a guaranteed benefit regardless of the canary outcome — Close ≥ drop `sprint-objective` + `milestone-objective` + `compact-dev-prompt` = 16,421 B ≈ **4,105 tok**; Deliver-plan ≥ drop `deliver-close-taxonomy` = 8,923 B ≈ **2,230 tok**. The true L-taskscope benefit lies in **[floor, upper]**, to be pinned by the canary; it is never zero.

- **Close is the highest-frequency of the three roles AND has the biggest, lowest-risk saving (~4.1K tok floor up to ~14.8K).** That is the single best-leveraged target in WP-5.
- **Crucially, L-taskscope is NOT the rejected P1e "lite tier" and does NOT reopen the rejected P1 on-demand-deferral concern:** it keeps the full governance trio + full role card + the verdict-defining doc for each task, and it defers ONLY docs that are not inputs to *that task's* verdict. No verdict-affecting input is deferred for its own task (the LOAD-CLOSURE spirit holds even though LOAD-CLOSURE itself is Acceptance-only — see §5).

---

## 5. Risk and maintenance comparison

### 5.1 Audit / resolver implications (a real simplification vs WP-4)
Verified on HEAD: Close/Research/Deliver-plan all use plain `_spawn` → `input_hash = sha256(role + "\x00" + prompt)` is **prompt-only** (it hashes the dispatched prompt and excludes the agent's cold-start reads — which is exactly why WP-7 added the separate `load_graph_hash`); and **none of `deliver`/`research` appears in `_acceptance_resolver_graph`** (resolver is Acceptance-scoped, driver.py ~L3953). Therefore:
- The Acceptance **LOAD-CLOSURE invariant + `acceptance_input_hash` reuse coupling DO NOT apply** to these three roles. A cold-start change here cannot break acceptance reuse/audit integrity (the cross-cutting hazard WP-4 had to manage).
- The ONLY audit surface is the WP-7 `cold_start_load_graph_hash` (already built; `role_cold_start_roots` is its single source of truth). Any cold-start change — kernel swap OR task-scoped load-set — is recorded there as a forward-only fingerprint change. For task-scoping this means `role_cold_start_roots` becomes **task-aware** (a new parameter), which the sizer + WP-7 hash must thread together (they already share that function, so it stays one edit point).

### 5.2 Source-drift / maintenance
- **Every kernel (P-*) adds a permanent tax:** a `_<name>_kernel_coverage.yaml` + a `kernel_equivalence.py` mode + a non-vacuity proof + a Codex fidelity gate + a behavioral/read-trace canary, and thereafter **source-hash drift management** — editing the role card or any projected briefing doc trips STALE and forces re-review (the WP-2/3/4 GOTCHA). For 13 reference docs this is a large standing surface.
- **L-taskscope adds no coverage artifact and no fidelity gate** (it rewrites no constraint). Its cost is: making cold-start task-aware (role-card §1 / `context_briefing` §2 + `role_cold_start_roots` + dispatch load_list), a WP-EQ-style drift gate proving the close load-set ⊇ all close-verdict inputs and the plan load-set ⊇ all plan inputs, and a read-trace canary. Lower standing maintenance, but a genuine **architectural change to the load model** (currently role-keyed) — not free.

### 5.3 Constraint-loss risk
- Kernels: HIGH-attention. ~87% of role-card constraints and many briefing rules have no programmatic backstop; a faithful projection is the only catch. WP-2/3/4 show this is achievable but costs 3–6 Codex rounds each.
- L-taskscope: LOW. It loads strictly *fewer whole docs* for a task; the risk is "did we mis-classify a doc as not-needed-for-this-task?" — bounded, doc-granular, and checkable by the drift gate + canary. No constraint is reworded, so none can be silently dropped by paraphrase.

---

## 6. Recommendation per role

Applying the decision rule (a role-specific projection is NOT the default; it must show material measured benefit AND complete constraint coverage, weighed against drift/maintenance and role frequency; ~1K tok/spawn significance reference; these are not generic lite roles):

| role | project? | recommendation |
|---|---|---|
| **Research** | **NO — keep unchanged (share the existing kernel)** | Card-only projection (~0.9K tok) is sub-threshold; the full ~3.6K is the role-card-literal figure and is canary-dependent — it may collapse toward the card-only ~0.9K if the `on-demand` briefing is already deferred (§0.2/§4.C). Research is the lowest-frequency role → low aggregate benefit against a new coverage artifact over 5 sources, and constraint-loss risk (87% unbacked card constraints) is not worth it here. |
| **Deliver-plan** | **NO — keep unchanged (share)** | The plan task genuinely consults its planning reference; compression is modest (~5K tok) and a single deliver kernel is the wrong shape (it locks in cross-task waste). If anything, fold plan into L-taskscope (defer close/post-ship docs, ~2.2K tok floor up to ~5.6K upper, ~8.0K with common-detours). |
| **Close** | **NO projection — but pursue L-taskscope** | Do not build a Close *kernel* (cannot be separated from Deliver-plan at cold-start without task-aware loading anyway; a kernel is the wrong tool). The earned increment is **task-scoped loading**: ~4.1K tok/spawn guaranteed floor up to ~14.8K (role-card-literal upper, §4), highest frequency, near-zero constraint-loss risk, no coverage artifact. |

**Net:** no role earns a projection. The data points away from "three narrow kernels" and toward (a) confirming the load-discipline gap by canary, then (b) task-scoped/`on-demand`-aligned loading, with **Close** as the highest-value, lowest-risk target.

---

## 7. Proposed implementation increments (only options that earn their place — NOT for this session)

Strictly sequenced; each is its own gated increment (baseline revalidation + Codex gate + canary, per the established discipline). **None is started here.**

1. **[MEASURE — prerequisite] Read-trace canary** (read-only; `claude -p` stream-json, reuse `archive/wp3-canary-harness/read_trace_canary.py`). For Close, Deliver-plan, Research: observe what each ACTUALLY loads at cold-start. Resolves §0.2's role-card-literal vs front-matter-literal gap. **Gate:** the canary pins where L-taskscope's benefit sits in the **[floor, upper]** range of §4 — it does NOT zero it. Even if every `on-demand` doc is already deferred, the canary-independent floor (Close ≥ ~4.1K tok, Plan ≥ ~2.2K tok, from task-mismatched `by-role` templates) stands. Proceed to increment 2 unless the canary shows cold-start is *already* fully task-scoped (floor already realized), which alone would close WP-5.
2. **[unless #1 shows cold-start is already fully task-scoped] Task-scoped Close load-set.** Make `_step_close`'s dispatch carry a close-scoped load_list (gov trio + card + `deliver-close-taxonomy` + milestone-framework + artifact-taxonomy); retire the role-card §1 force-load of planning/post-ship docs for the close path. Thread task-awareness through `role_cold_start_roots` → sizer + WP-7 hash; add a WP-EQ-style drift gate proving close load-set ⊇ every close-verdict input. **~4.1K tok/spawn floor up to ~14.8K (role-card-literal upper, §4), highest frequency.**
3. **[Optional, after #2] Plan-scoped load-set.** Defer close/post-ship docs from `_step_decompose`. ~5.6K tok/spawn.
4. **[Optional, lowest priority] Light compression of the two prose-heavy deliver process docs** (`typeA-runtime-architecture-skeleton`, `milestone-framework`: ~45–50% rationale/example) — only if a partial close/plan projection is built anyway; standalone it is not worth a coverage artifact.

Increments 2–4 are additive and independently revertible. Each keeps the full governance trio + role card; none reduces governance.

---

## 8. Non-goals and rejected alternatives

- **NON-GOAL:** any runtime, load-graph, `role_cold_start_roots`, role-card, kernel, cold-start, or resolver change **in this session**. WP-5 here is the memo only.
- **NON-GOAL:** treating Close / Research / Deliver-plan as generic "lite" roles. They emit gating verdicts / set the closure contract; the full governance trio + role card stay loaded for all of them. (This is the design's already-Codex-rejected P1e — not revisited.)
- **NON-GOAL:** deferring any verdict-affecting input for its own task. L-taskscope defers only docs that are not inputs to *that* task's verdict (e.g., planning authoring aids are not close-verdict inputs).
- **REJECTED — Alternative B (one shared 3-role projection):** incoherent. Close≡Deliver-plan and Research have near-disjoint unique content; the only shared content is the already-kernelized governance trio. A shared kernel yields ~0 useful tokens or forces cross-role over-loading.
- **REJECTED — P-research kernel (Alternative C, research):** sub-threshold realized benefit (~0.9K card-only; full kernel mostly `on-demand`), lowest role frequency, new coverage artifact over 5 sources, 87% unbacked card constraints. Keep sharing the existing kernel.
- **REJECTED — P-deliver-single kernel (Alternative C, deliver):** wrong shape — a single deliver kernel still loads planning content on a Close spawn, so it preserves the dominant waste while adding the largest, highest-drift coverage artifact. Task-scoping captures more at lower cost.
- **DEFERRED (not rejected) — P-deliver-split (two task kernels):** the only option that captures *both* levers, but it requires task-aware cold-start AND two coverage artifacts. Revisit only if L-taskscope (increments 2–3) lands and the residual compression on the *retained* task docs (a modest increment over task-scoping, not the full per-doc figure — §4) proves worth a kernel; the measured priority is task-scoping first.
- **OUT OF SCOPE:** Dev, Review, Acceptance (WP-4 done); WP-6 lessons tiering; WP-8 AGENTS.md trim; WP-9 budget lint; full comparative eval — all later WPs.

---

### Appendix — provenance
- Measurements: `load_sizer.size_role` / `role_cold_start_roots` at `e244716`; raw JSON `.runs/wp5/baseline.json` (gitignored).
- Constraint backstop counts: WP-EQ `engine-kit/tools/constraint-inventory/07-role-cards-acc-del-res.yaml` (role cards) — briefing docs are intentionally outside the inventory.
- Per-doc content classification: three read-only analysis passes (research briefing; deliver planning briefing; deliver close briefing), summarized in §2/§4.
- Audit facts: `driver._spawn` `input_hash` (prompt-only); `_acceptance_resolver_graph` (Acceptance-scoped); WP-7 `cold_start_load_graph_hash` (`load_sizer.cold_start_load_graph_hash`).
- This memo follows the [[codex-verification-gate]] measure-then-gate discipline; it is the WP-5 deliverable per [[context-token-optimization]] UPDATE 16.

### Review-gate log (Codex gpt-5.5 xhigh, read-only, bounded `review_runner.py`, argv-token + per-round sentinel)
- **R1 → REVISE (2 blocking):** (B1) §4.C/§6 discounted P-research savings using *unobserved* behavior, contradicting §0.2's role-card-literal stance → made conditional on the canary. (B2) §7 claimed L-taskscope "moot / WP-5 ends" if agents defer → false; added the canary-independent **floor** (by-role task-mismatched templates: Close ≥4,105 tok, Plan ≥2,230 tok) and reframed table figures as role-card-literal **upper** bounds. (NB) §4.B union figures reversed; §5.1 "prompt-only" clarified. Numbers/structural/audit claims confirmed reproducing.
- **R2 → REVISE (2 blocking):** consistency follow-through — §6 Research row still asserted on-demand briefing "not loaded" as fact (→ conditional); §7.2 still gated on "force-load" + quoted only the upper figure (→ "[floor, upper]"). Floor arithmetic verified (16,421 B ≈ 4,105 tok; 8,923 B ≈ 2,230 tok). + 2 polish notes applied.
- **R3 → REVISE (2 blocking):** (B1) §4 `P-deliver-split` double-counted compression on docs task-scoping already drops → split ≈ task-scoping + retained-doc compression only. (B2) "L-taskscope dominates B and C on benefit" contradicted split-has-highest-benefit → scoped dominance to B + single-kernel C on benefit, all options on risk/maintenance/leverage. §8 split entry reconciled.
- **R4 → APPROVE:** no blocking; both prior fixes confirmed resolved, no residual contradiction across §4/§6/§7/§8.
- Verdicts + prompts: `.runs/wp5/reviews-r{1,2,3,4}/` + `.runs/wp5/codex-prompt{,-r2,-r3,-r4}.md` (gitignored). Sentinels `WP5-R{1..4}-CONFIRM` verified each round (fresh session, not resumed).
