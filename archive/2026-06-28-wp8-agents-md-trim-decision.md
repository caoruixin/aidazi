# WP-8 — AGENTS.md template trim + metadata-consistency affirmation (decision)

status: implemented
date: 2026-06-28
branch: wp0-measurement
parent: 74514aa (WP-6)
roadmap: context/token-optimization — WP-8 (after WP-2/3 land; before WP-9)
design: archive/2026-06-26-context-token-optimization-design.md §WP-8

## 0. Objective

Trim the root `AGENTS.md` template so verbatim adopters stop paying human-onboarding
/ redundant prose in the per-spawn cold-start (AGENTS.md is `adopter_cold_start`,
re-read on every fresh role/Control-Plane session), while **preserving every
guardrail, constraint, and wiring instruction**, and affirming that the always-load
metadata is kernel-consistent (so a future "doc reconcile" can't re-expand the
kernels). Non-goal (design, Codex DROPS-CONSTRAINT): do NOT remove the two-loop
discipline (§5) or the harness-wiring guardrails.

## 1. Baseline (re-resolved @ 74514aa)

Root `AGENTS.md` = 9,535 B (~2,383 tok). Per-section bytes: preamble 1,474 / §1 262
/ §2 823 / §3A 2,269 / §3 414 / §4 1,272 / §5 433 / §6 722 / §7 899 / §8 967.

**How it is loaded / constrained** (Explore map; all re-verified):
- `load_sizer.ADOPTER_STATIC` = `("AGENTS.md","adopter_cold_start")` — sized per
  adopter cold-start; NOT framework-static (not in the governance floor). It is the
  Control-Plane resident + each role-session cold-start read (context_briefing §1.2).
- `driver._acceptance_resolver_graph` binds it by **path** (rel `AGENTS.md`, purposes
  `framework_cold_start` + `adopter_cold_start`) → content-hash auto-tracks; a trim
  changes `acceptance_input_hash` once (fail-closed re-spawn — correct, not a
  regression). `test_e2e_acceptance` uses **temp/decoy** AGENTS.md fixtures (tests the
  mechanism, no hardcoded real-file hash) → **no lockstep hash update needed**.
- NOT in `_sources.yaml` → **no sha refresh**. NOT in `kernel coverage` inventories.
- Gates that assert AGENTS.md CONTENT (must stay green):
  - `test_coldstart_consistency` — §2 header + kernel-trio names
    (`constitution-core.md`, `authoring-kernel.md`, `context_briefing.md`), no full
    canonical at cold-start.
  - `test_alwaysload_doc_reconciliation` — no obsolete "full canonical is always-load"
    claim.
  - `control_plane_validator` — §3A `control-plane-load` fence with `allow`/`on_demand`/
    `forbid`, `AGENTS.md` in `allow`, no line-level `@aidazi/governance/` import.
  - `test_quickfix_default_full` — AGENTS.md @-include closure must equal `{AGENTS.md}`
    (no NEW resolvable `@`-includes).
  - `adoption_status` / `adopter_wiring_validator` — §1 `project_name: <adopter-name>`
    placeholder; CLAUDE.md→`@AGENTS.md` wiring.
  - `test_acceptance_load_closure` — `AGENTS.md` stays resolver-bound.

**Metadata-consistency objective is already MET:** the WP-3 follow-up (`67026dc`)
reconciled the always-load→kernel-trio model framework-wide. AGENTS.md §2/§7/§8
already say "constitution-core is the always-load kernel; full constitution.md
on-demand" (the correct post-kernel model). So WP-8 only AFFIRMS consistency
(no stale claim to fix) and must not introduce one.

## 2. Decision — what to trim (smallest coherent, guardrail-preserving)

Measure-first (per the WP-5 discipline): trim ONLY unambiguous human-onboarding /
redundant prose; keep every constraint/guardrail/wiring/table verbatim.

| section | action | rationale |
|---|---|---|
| preamble | **condense** harness-wiring teaching to terse facts + pointers | keep the 3 harness facts (Claude Code CLAUDE.md→@AGENTS.md, Codex auto-loads AGENTS.md, Cursor `.cursor/rules`) + the `adopter_wiring_validator` pointer + the §1.1 normative pointer + the "CLAUDE.md only imports, never duplicates" guardrail + the Control-Plane-default model; cut the "Because…ships both" padding |
| §7 | **compact to a pointer** | the 9-item "fresh PERSON joining" read list is human onboarding, duplicative of `README.md` §Read order + `docs/adoption-overview.md`; preserve every reference (adoption-overview, adoption-state, foundational docs, greenfield/brownfield, profile-aware) compactly + label it "human onboarding, not a session load" |
| §8 | **condense** | drop the paragraph that RE-explains the kernel trio (redundant with §2); keep the load-baseline sentence + the Control-Plane-vs-role load-graph distinction in one paragraph; no obsolete always-load claim |
| §1, §2, §3, §3A, §4, §5, §6 | **keep verbatim** | constraints/wiring/tables: §2 kernel trio, §3A control-plane-load block, §1 placeholder, §4 role registry, §5 two-loop (PRESERVE per design), §6 hard-requirements list |

No new `@`-includes; example `examples/minimal-greenfield/AGENTS.md` already shows
the trimmed shape and is left unchanged.

## 3. Measured result (after)

Root AGENTS.md **9,535 B → 8,754 B (~2,383 → ~2,188 tok): −781 B ≈ −195 tok per
adopter cold-start spawn** (preamble + §7 + §8 condensed; all other sections
verbatim). The honest measured number is well below the design's optimistic ~838
tok estimate — AGENTS.md is mostly constraints/wiring/tables, not onboarding prose;
only the preamble teaching, the §7 human read-list, and the §8 redundant kernel
re-explanation were genuinely trimmable. This is a recurring per-spawn saving across
every role/Control-Plane session for every adopter, plus the correctness win of
removing human-onboarding prose from the agent's per-spawn context.

**Gates (all green):** full suite 1162 passed/3 skipped; `test_coldstart_consistency`
+ `test_alwaysload_doc_reconciliation` (15) pass; `control_plane_validator .` OK;
`adopter_wiring_validator` OK; acceptance load-closure `closed:true, pending:[]`;
kernel coverage 65/65 + 41/41 + 44/44 + base 475. Hard-constraint strings re-checked
present (§1 placeholder, §2 kernel trio, §3A control-plane-load block, §5 two-loop,
§6 9-checkpoints, wiring-validator pointer). `acceptance_input_hash` auto-rehashes
once (content-hash; fail-closed re-spawn; `test_e2e_acceptance` uses decoy fixtures
→ no lockstep change).

## 4. Compatibility / audit / rollback

- `acceptance_input_hash` changes once (content edit auto-rehash; fail-closed
  re-spawn; old ledgers verify unchanged — verification is over recorded bytes).
- No `_sources.yaml`, kernel-coverage, or load-closure binding change (still bound).
- Rollback = revert the commit (prose only; no data/migration).
- Out of scope: WP-9 context-budget lint; any runtime/logic change; the adopter
  example; README structural edits (kept untouched to avoid the reconciliation gate).

## 5. Review-gate log

**Codex gpt-5.5 xhigh** (read-only, bounded runner, argv-token + `WP8-R1-CONFIRM`
sentinel; `.runs/wp8/reviews-r1/`). **R1 = APPROVE** (sentinel confirmed; first
round, no findings). All 7 points PASS: guardrails preserved (§2/§3A/§4/§5/§6);
gate strings intact (kernel trio, control-plane-load allow/on_demand/forbid,
`project_name: <adopter-name>`, no new `@`-include); metadata kernel-consistent (no
obsolete always-load claim); §7 relocation loses no reference; AGENTS.md stays
resolver-bound (driver.py:4114/4140, closure closed); measurement honest (−781 B
verified vs parent 74514aa); file coherent.
