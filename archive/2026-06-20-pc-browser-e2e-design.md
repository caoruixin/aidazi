---
title: P-C — User-perspective browser-E2E acceptance gate (v1 implementation spec)
doc_tier: archive
doc_category: design
status: active-spec
revision: rev7
last_reviewed: 2026-06-20
parent_spec: archive/2026-06-20-autonomous-delivery-design.md   # §4 = P-C
notes: >
  Self-contained v1 implementation spec for P-C, refining §4 of the parent design
  against verified current code. P-A (acceptance default-on advisory) + P-B (campaign
  loop + per-milestone Acceptance) are DONE/committed. Preserves the five-role chain;
  adds a capability, not a sixth role. Fail-closed everywhere.
changelog:
  rev1: initial spec (Codex round 1 = REJECT).
  rev2: transactional commit/reconcile + consistency gate + active-class calibration
    + runtime hard-fails (Codex round 2 = REJECT — transaction/schema edge cases).
  rev3: durable-state-keyed recovery (persist e2e_run_id up front; reconcile from
    run_id + ledger, not cache flags); pre-existing-final publish handling (no
    os.replace-overwrite); evidence-hash binding for BOTH acceptance classes; frozen
    authority snapshot at verdict production (no resume drift); structured criterion_id
    coverage; branch-correct if/then/ELSE verdict schema; campaign unit/accounting
    reconcile on STATUS_RUNNING; functional_acceptance precedence (no schema default,
    explicit-overrides-inherit); parseable self_smoke handoff block.
    (Codex round 3 = REJECT — 4/6 CLOSED; 1 BLOCKING + 1 MAJOR + 1 MINOR remained.)
  rev4: canonical pre-degrade authority_fingerprint for snapshot reuse (no spurious
    re-spawn / no duplicate degrade); driver binds every verdict functional_evidence_ref
    to the committed manifest artifact set (no fake-but-schema-valid refs); precise
    dir_complete_and_hashes_ok definition (fail-closed against stray/partial files).
    (Codex round 4 = REJECT — 3/3 CLOSED; 1 new BLOCKING: reuse not bound to criteria.)
  rev5: snapshot reuse now binds a THIRD hash — acceptance_input_hash over the fully
    resolved acceptance prompt + the sha of every signed/contract source it resolves
    (intent_contract/closure_contract, functional-checklist, executor-contract, derived
    context). Reuse requires evidence AND authority AND context all match, else re-spawn
    — a criteria/prompt edit between produce and resume can no longer reroute a stale verdict.
    (Codex round 5 = REJECT — PARTIALLY-CLOSED; input hash missed other path-loaded inputs.)
  rev6: acceptance_input_hash redefined as a RESOLVER-GRAPH hash over the Acceptance
    prompt's loaded inputs; fixed the stale front-matter revision field.
    (Codex round 6 = REJECT — enumeration still missed adopter cold-start + conditional docs.)
  rev7: resolver_graph reframed DEFINITIONALLY as the TRANSITIVE CLOSURE of the Acceptance
    session's cold-start load-list, derived from the driver's own load-list construction
    (single source of truth), not a hand-maintained member list. Named files are illustrative;
    the binding is the resolved closure, so adopter cold-start (AGENTS.md, docs/current/*
    ledgers), conditional process docs, and resolved skill files are covered by construction —
    a new/edited loaded input cannot escape it. Closes the "you missed file X" class.
---

# P-C v1 — Browser-E2E acceptance gate

## §0 How to review this document

Order: §1 (seams) → §2 (state machine + §2a hard-fail) → **§3.5 (durable commit/recover —
the heart)** → §3 (fail-closed matrix + §3.2 consistency gate) → §4 (schemas) → §5
(evidence/audit) → §6 (acceptance + calibration API + §6a self-smoke) → §7 (executor) →
§8 (fixture/tests) → §9 (decisions) → §10 (non-goals) → §11 (files). Core property: **no
listed failure can silently become a milestone PASS — single loop or campaign, across an
interrupted-and-resumed run, across a charter/calibration edit between produce and resume,
or via a verdict that contradicts captured evidence.**

Glossary: **M1** static/code-evidence class (today). **M3** functional/browser-E2E class
(new; advisory until calibrated). F5 = orchestrator-runs-evidence / Acceptance-reads-only.
"Executor" = orchestrator-owned capture runner (observations only; never the verdict).

## §1 Verified reusable seams (code anchors)

- **Insertion** — `driver.py:2479-2486` (`_handle_close` → `STATE_ADVANCE` → `_run_acceptance`
  iff `_acceptance_enabled() and _milestone_complete(...)`; `_milestone_complete` `:2516` =
  terminal of `autonomy.approved_scope.subsprint_sequence` → per-milestone in campaigns).
- **Idempotent out-of-band resume** — `driver.py:2094-2099` (`STATE_ACCEPTANCE_PENDING`
  re-entry). Add `STATE_E2E_PENDING` before it; HALT/DONE/ADVANCE short-circuit `:2100`.
- **Checkpoint/HALT** — `_write_checkpoint` `:704`; `_gate_hard_fail` raises `GateHardFail`
  (campaign → paused unit); `RunState.halt_resume_state` re-enters.
- **Acceptance** — `_run_acceptance` `:2966` (`_calibration_gate`→`_run_eval_f5`→
  `_spawn_acceptance`→`_handle_acceptance_verdict`). `_spawn_acceptance` `:2904` sets
  `self.state.last_verdict` `:2963` (no evidence binding today). `_acceptance_authoritative`
  `:2500` recomputes live from charter; `_calibration_gate` `:2560/2580` mutates **in-memory**
  autonomy + writes a checkpoint (degrade is NOT persisted in RunState → resume drift risk).
- **Audit** — `append_event(loop_id, type, payload, *, ts)`; `type` free-form, `payload`
  open (→ `browser_e2e_evidence` needs no schema change). `verify_events` `:280` checks
  chain only, not evidence presence. `read_events(path)` / `verify_chain(ledger)` exist.
- **Per-milestone projection** — `derive_milestone_context(charter, milestone_id,
  subsprint_sequence, *, campaign_id, plan_fingerprint)` `:667`; the runner `:521-557` holds
  the full milestone object and calls `run_unit(..., subsprint_sequence=seq)`. Accounting
  (`subsprints_run`/`total_spawns`/`wall_clock`) at `:553-557` runs right after each
  `run_unit`, BEFORE the advance/pause/done branch.
- **Campaign recovery** — `campaign.py:484,499,541`: `STATUS_RUNNING` recovery sets
  `_pending_driver_resume=False` → current unit re-dispatched `resume=False` (fresh).
- **Classification** — `classify_checkpoint` unknown → DISPATCH; AST inventory test pins
  every driver checkpoint id. **P-C adds no new id** (reuses `gate_hard_fail`).

## §2 State machine

New out-of-band `STATE_E2E_PENDING = "e2e_evidence_pending"`, between close-advance and
acceptance. Trigger: active `_acceptance_class() == "browser_e2e"` AND milestone complete.

### §2a Runtime hard-fail (Codex MAJOR-1, round1) — CLOSED
`browser_e2e` + `acceptance.mode == off` → driver construction-time `ValueError` (independent
of the validator, which `run_loop` runs only for `allow_real=True`, `run_loop.py:350`), plus
an E2E-entry guard. Fires only for the net-new incoherent combo.

```
_handle_close (clean A/B, milestone_complete):
    STATE_ADVANCE
    if browser_e2e:  _run_e2e_evidence()        # → then _run_acceptance()
    elif acceptance_enabled:  _run_acceptance()  # unchanged P-A/P-B path

_run_e2e_evidence():            # STATE_E2E_PENDING — durable commit/recover §3.5a
    persist e2e_run_id if unset (pending phase); save
    _commit_e2e()               # reconcile-or-(append-event)-or-(rerun+publish); runtime err → gate_hard_fail
    if acceptance_enabled:  _run_acceptance()

_run_acceptance():              # STATE_ACCEPTANCE_PENDING (fresh OR resume) §3.5b
    if browser_e2e: assert e2e_committed (reconcile) else gate_hard_fail; evidence=manifest
    else:           evidence = _run_eval_f5(acc)                         # static path unchanged
    evidence_hash = sha256(evidence content/manifest)                   # BOTH classes (§3.5b)
    if reusable_committed_verdict(evidence_hash):  route_from_snapshot(last_verdict)   # NO re-spawn
    else:
        calibration = _calibration_gate(active_class)                   # active-class API §6
        verdict = _spawn_acceptance(...)                                # persists verdict + snapshot §3.5b
    _check_acceptance_consistency(verdict, manifest, checklist)         # §3.2 (browser_e2e)
    _handle_acceptance_verdict(verdict, evidence, snapshot)             # routes from FROZEN snapshot

resume (_drive), before the acceptance re-entry:
    if state == STATE_E2E_PENDING:        _run_e2e_evidence(); return
    if state == STATE_ACCEPTANCE_PENDING: _run_acceptance();   return
    if state in (ADVANCE, DONE, HALTED):  return
```

## §3 Fail-closed matrix + acceptance consistency gate

### §3.1 Failure → mechanism (neither kind becomes PASS)

| Failure | Kind | Mechanism |
|---|---|---|
| app start / readiness timeout / runtime unavailable / blocking step / invalid contract|checklist | runtime/precond | `gate_hard_fail` (resumable: re-run/accept/abort) |
| assertion fail / console error / failed critical request / UI-backend mismatch | captured | criterion `executor_status∈{fail,error}`, exit 0, full evidence → §3.2 + Acceptance → not PASS |
| interrupted run | crash | partial staging discarded; reconcile keyed on `e2e_run_id` → re-run (§3.5a) |
| missing/incomplete evidence, hash/ref mismatch | integrity | reconcile/verify pre-acceptance → `gate_hard_fail` |
| verdict omits/mismatches active class or malformed refs | integrity | schema (§4.1) + driver class check → `gate_hard_fail` |
| pass with a failed/partial case, a critical executor failure, or coverage gap | contradiction | §3.2 → **needs_human** (`acceptance_surface_approve`) |

### §3.2 Acceptance consistency gate (Codex BLOCKING-3/5) — `_check_acceptance_consistency`
For browser_e2e, a `milestone_verdict == pass` is rejected → **needs_human** unless ALL hold;
malformed → `gate_hard_fail`:
1. **Class match:** `verdict.acceptance_class == "browser_e2e"` (else reject the verdict → `gate_hard_fail`).
2. **Structured coverage (BLOCKING-5):** the signed checklist defines unique `criterion_id`s;
   each verdict `case` carries a unique `criterion_id`; coverage holds iff
   `set(case.criterion_id) == set(checklist.criterion_id)` (set equality, no dup). Gap → needs_human.
3. **Case consistency:** `pass` requires every `case.verdict == "pass"`. Any non-pass case → needs_human.
4. **Critical veto:** any checklist-results `executor_status ∈ {fail,error}` on a contract
   `critical:true` criterion → `pass` becomes needs_human (executor observation can't be overridden into a silent pass).
5. **Brief presence:** `fix_required` ⇒ non-empty `failure_briefs`; `pass` ⇒ empty (schema + driver).
6. **Evidence-ref binding (round-3 MAJOR) — runs for ANY browser verdict, not just `pass`:** every
   `case.functional_evidence_ref` (path + sha256) MUST resolve to an artifact in the committed
   `browser-evidence-manifest` with a matching recorded sha256 (the file already exists +
   hash-matches via §3.5a reconcile). A ref to a non-existent / tampered / uncommitted artifact →
   `gate_hard_fail`. A judge cannot cite evidence outside the committed, ledger-anchored set —
   this satisfies the prompt's "evidence hash/reference mismatch" fail-closed requirement and
   closes the "fake-but-schema-valid refs" hole.

The executor never emits a milestone verdict; Acceptance is the sole pass producer; a pass
contradicting (or citing evidence outside) the committed manifest is structurally unshippable.

## §3.5 Durable commit / crash-recovery (Codex round-2 BLOCKING-1..4, MAJOR-1)

### §3.5a E2E evidence — recovery keyed on the persisted `e2e_run_id` (not cache flags)
`e2e_run_id` is deterministic and **persisted up front** (pending phase) before any executor
run. `e2e_evidence_ref`/`e2e_manifest_hash` are post-commit *caches*; recovery does NOT depend
on them. On every entry `_commit_e2e()`:
```
final = .orchestrator/audit/browser/<loop_id>/<e2e_run_id>/ ; staging = <...>.staging/
A. if reconcile(final): set caches; return            # committed: dir complete + per-artifact sha256 ok
                                                        #   + ledger browser_e2e_evidence event run_id==e2e_run_id & manifest_sha256==recompute
B. elif final exists AND dir_complete_and_hashes_ok(final) AND no matching ledger event:
        append the one browser_e2e_evidence event; set caches; return   # crash between publish & append → finish, do NOT re-run
C. else:                                                # absent / partial / corrupt final
        rmtree(staging) if exists
        executor.run(staging, ...)                      # runtime err / unavailable → gate_hard_fail (rmtree staging)
        write manifest.json + checklist-results.json into staging; verify staging complete (else gate_hard_fail)
        rmtree(final) if exists                          # explicit removal — os.replace cannot overwrite a non-empty dir
        os.replace(staging, final)                       # atomic rename onto a now-absent path
        append browser_e2e_evidence event; set caches; save
```
No skip on incomplete (A/B both require a complete, hash-verified dir). No reliance on
directory-overwrite (C removes final first). Recovery is authoritative from `e2e_run_id` +
disk + ledger, so a crash before the caches are saved still reconciles correctly (A/B).

`dir_complete_and_hashes_ok(final)` ≜ (round-3 MINOR, precise): manifest.json is schema-valid;
every `artifacts[i].path` is a normalized relative path strictly under `final` (no `..`/abs/
symlink escape) with no duplicate paths; every listed file exists and its recomputed sha256 ==
`artifacts[i].sha256`; recompute(`artifact_manifest_hash`) matches; checklist-results.json is
present + schema-valid; and there is **no file under `final` absent from the manifest** (a stray/
partial artifact → NOT ok → fail-closed, forcing branch C re-run, never a skip).

### §3.5b Acceptance — evidence-bound verdict + canonical authority fingerprint (both classes)
At the moment a schema-valid verdict returns (in `_spawn_acceptance`, before routing), persist:
```
acceptance_evidence_hash = sha256(evidence)   # browser: manifest hash; static: sha256(F5 evidence file) — never None
authority_fingerprint = sha256(canonical_json({           # everything that determines authority + judge identity
    acceptance_class, mode, autonomy_level_declared,      # autonomy_level_declared = the CHARTER level (PRE-degrade)
    calibration_status, calibration_record_id,
    judge: {harness, provider, model, agent_kind, capability_ref}, skills, subagent_fanout }))
acceptance_input_hash = sha256(canonical_json({           # the CRITERIA/PROMPT context the verdict judged (round-4/5 BLOCKING)
    projected_acceptance_prompt,                          # the fully-resolved prompt _project_acceptance_prompt built
    resolver_graph: [ {path, sha256, purpose}, ... ] }))  # the RESOLVER GRAPH ≜ the TRANSITIVE CLOSURE of the Acceptance
                                                          # session's cold-start load-list — every file the driver instructs
                                                          # the judge to load, resolved RECURSIVELY through @-includes/refs,
                                                          # each content-hashed. It is DERIVED FROM THE DRIVER'S OWN load-list
                                                          # construction (the SAME source of truth that builds the prompt), so
                                                          # it cannot drift from what the judge actually reads and is not a
                                                          # hand-maintained enumeration. For whatever this adopter+mode
                                                          # resolves to it therefore covers (ILLUSTRATIVE, non-exhaustive):
                                                          # adopter cold-start (AGENTS.md/equivalent, docs/current/* ledgers
                                                          # incl. adoption-state.md); the governance chain + conditional
                                                          # process/delivery-loop.md (orchestrator mode); role-cards/
                                                          # acceptance-agent.md; schemas/acceptance-verdict.schema.json;
                                                          # conditional skill files (process/role-skill-model.md + resolved
                                                          # SKILL.md/refs when skills are mounted); the signed criteria sources
                                                          # (intent_contract, closure_contract/brief, functional-checklist,
                                                          # executor-contract); derived-context.json; Reviewer outcomes
                                                          # (codex-findings + referenced transcripts); the evidence manifest.
                                                          # Binding the CLOSURE (not a list) means a new/edited loaded input
                                                          # cannot escape it. A missing/unreadable MANDATORY member at hash
                                                          # time → gate_hard_fail (fail-closed).
acceptance_snapshot = { evidence_hash, authority_fingerprint, acceptance_input_hash, authoritative }  # authoritative FROZEN here
```
`_handle_acceptance_verdict` routes from `acceptance_snapshot.authoritative` — it does NOT
recompute `_acceptance_authoritative()` (which reads live, post-degrade charter state). Fresh
runs are byte-identical (snapshot computed then consumed in the same call). **Reuse-on-resume**
requires ALL three hashes to match the recompute over current state — `last_verdict` is an
acceptance verdict AND `acceptance_evidence_hash == current evidence_hash` AND
`authority_fingerprint == recompute(authority)` AND `acceptance_input_hash ==
recompute(criteria/prompt context)`. The authority fingerprint uses the **charter-declared
(pre-degrade) autonomy level** — the §3.6 degrade mutates only in-memory autonomy and is NOT
persisted, so on resume the charter still reads pre-degrade and the fingerprint matches with
**no spurious mismatch and no duplicate degrade checkpoint** (round-3 BLOCKING). The input hash
binds the verdict to the exact criteria/prompt it judged: an edit to the projected prompt OR to
**any file in the resolver graph** — intent_contract, functional-checklist, executor-contract,
derived context, Reviewer outcomes (codex-findings + transcripts), the acceptance role-card/
governance chain, or the verdict schema — between produce and resume **invalidates reuse**
(round-4/5 BLOCKING; the path string staying stable while loaded content changes can no longer
hide a stale verdict). Any divergence on ANY of the three
→ **re-spawn** (never reroute a verdict that was judged against different evidence, authority, or
criteria; never auto-ship a stale pass). A captured failing verdict is un-flippable; a `pass`'s
advisory/authoritative basis is frozen; static (M1) gains the same evidence + context binding.

### §3.5c Campaign STATUS_RUNNING — resume + reconcile accounting (Codex BLOCKING-1 / MAJOR-1)
On `STATUS_RUNNING` recovery, before dispatch, reconcile `state.units` against the cursor:
```
expected = loop_id(campaign, milestone[cursor], subsprint[cursor])
if expected in {u.loop_id for u in state.units}:        # already ran AND already accounted
    drive the advance/pause branch from the RECORDED final_state — do NOT re-run, do NOT re-account
else:                                                    # not finished/accounted
    dispatch run_unit(..., resume=True)                  # resume the in-flight unit (idempotent §3.5a/b)
    account exactly once
```
Accounting (`subsprints_run`/`total_spawns`/`wall_clock`) + `units.append` + save become one
atomic step keyed by loop_id, so "unit in `state.units`" ⟺ "accounted". Already-completed
units (cursor past them) are untouched. Closes both fresh-restart and double-count windows.

## §4 Schemas

### §4.1 acceptance-verdict — branch-correct if/then/ELSE (Codex round-2 BLOCKING-4/6)
JSON-Schema constraints are additive, so `evidence_path` is **removed from the base
`cases.items.required`** and re-required per branch (cannot be "dropped" by an if/then):
```jsonc
"properties": { "acceptance_class": { "enum": ["static","browser_e2e"] },   // absent ⇒ static
  "cases": { "items": { "required": ["case_id","criterion","verdict","rationale"],   // evidence_path NOT here
    "properties": { "evidence_path": {"type":"string"}, "criterion_id": {"type":"string"},
      "functional_evidence_refs": {"type":"array"} } } } },
"allOf": [{
  "if":   { "required":["acceptance_class"], "properties":{"acceptance_class":{"const":"browser_e2e"}} },
  "then": { "properties": { "cases": { "items": {
            "required": ["criterion_id","functional_evidence_refs"],
            "properties": { "criterion_id": {"type":"string","minLength":1},
              "functional_evidence_refs": { "type":"array","minItems":1, "items": {
                "type":"object","additionalProperties":false,"required":["kind","path","sha256"],
                "properties": {
                  "kind":{"type":"string","enum":["screenshot","console","network","manifest","checklist","backend_state"]},
                  "path":{"type":"string","pattern":"^\\.orchestrator/audit/browser/.+"},
                  "sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"} } } } } } } } },
  "else": { "properties": { "cases": { "items": {
            "required": ["evidence_path"],
            "properties": { "evidence_path": {"type":"string","pattern":"^eval/runs/.+"} } } } } }   // static unchanged
}]
```
A static verdict (no `acceptance_class`) → `else` → `evidence_path` required + `^eval/runs/.+`
(byte-identical to today). Browser → `then` → `criterion_id` + non-empty `functional_evidence_refs`.
Plus `failure_briefs` non-empty iff `fix_required` (if/then). **Driver defense-in-depth:** a
browser_e2e RUN whose verdict isn't `acceptance_class: browser_e2e` → `gate_hard_fail` (§3.2.1).

### §4.2 Other deltas + projection precedence (Codex round-2 MAJOR-2)
- `mission-charter.schema.json` (`tooling.acceptance` closed; add optional): `…functional
  {mode:static|browser_e2e, executor_contract, checklist_path, judge_calibration_m3}`;
  `tooling.e2e {app_start_cmd, readiness, base_url, shutdown_cmd|process_owned,
  fixture_setup_cmd, timeouts, env[], allowed_origins[], evidence_retention_path, executor_kind}`.
- `campaign-plan.schema.json` milestone: `functional_acceptance: {enum:[static,browser_e2e]}`
  **with NO `default`** (so absence is distinguishable from explicit static). Precedence in
  `derive_milestone_context`: `mode = milestone.functional_acceptance if PRESENT else
  charter.tooling.acceptance.functional.mode if present else "static"` — an explicit milestone
  value (incl. `static`) overrides; a missing key inherits. Record `{mode, source ∈
  {milestone,charter,default}}` in `derived-context.json`.
- `acceptance-verdict.schema.json`: also `acceptance_class`, `authoritative`,
  `calibration_record_id`.
- `case-spec.schema.json`: optional E2E tier value (M3 bad-case seam).
- **Four new** (config/contract; on-demand load at each consumer + a load test):
  `executor-contract.schema.json` (MECHANICS incl. per-step `blocking`/`critical`, console/
  network policy, `criterion_id`s), `functional-checklist.schema.json` (Research-signed
  CRITERIA, frozen at Gate-1; unique `criterion_id`), `browser-evidence-manifest.schema.json`
  (manifest + checklist-results[]; `executor_status` observation-only),
  `acceptance-calibration-record.schema.json` (M1/M3, full judge identity).

`MANDATORY_CHECKPOINTS` stays **9**. `charter_compat` unchanged.

## §5 Evidence + Audit Spine

```
.orchestrator/audit/browser/<loop_id>/<e2e_run_id>/      # published atomically from <...>.staging
  manifest.json  checklist-results.json  screenshots/  console.json  network.json
  app-start.log  app-stop.log  executor-config.json  backend-state-refs.json
```
`artifact_manifest_hash = sha256(canonical_json(sorted [{name,sha256}]))`; one hash-chained
`browser_e2e_evidence` event `{run_id, manifest_ref, manifest_sha256, artifacts[]{name,sha256},
exit_code, checklist_summary}` is the ledger anchor (reconcile + pre-acceptance gate verify it).

## §6 Acceptance boundary — single active-class calibration API (Codex BLOCKING-6, round1)

`_acceptance_class()` (derived charter `functional.mode`); `_calibration_status(cls=None)`
(static → M1 `judge_calibration.status` byte-identical; browser_e2e → M3
`functional.judge_calibration_m3.status`, absent ⇒ uncalibrated); `_calibration_gate()` and
`_acceptance_authoritative()` both consult the active class. v1 ships no M3 record ⇒ M3 never
authoritative ⇒ advisory ⇒ `advisory_acceptance_pass_signoff` → human sign-off. Authority is
FROZEN into the §3.5b snapshot at production; routing reads the snapshot. Acceptance reads
(read-only): signed contract, closure criteria, Reviewer outcome, the signed functional-
checklist, browser evidence refs, unresolved failures, calibration/authority — with
`executor_status` stated as observation-not-verdict; §3.2 vetoes contradictions.

### §6a Dev self-smoke structural gate (Codex MAJOR-2 round1, MINOR round2)
For browser_e2e milestones, the Dev handoff MUST carry a **parseable** attestation — the
implemented form is a standalone `docs/self-smoke.json` `{command: <str>, result: <str>}`
(a refinement of the round-2 "handoff §11 YAML block" — a separate JSON file is
unambiguous to locate + validate). The driver structurally checks presence
(not correctness) at the gate; absence → resumable halt (`gate_hard_fail`). Scoped to
browser_e2e (general-mandatory is a follow-up, honoring the non-goal). Surfaced to Acceptance;
necessary, not authoritative.

## §7 Executor (orchestrator-owned; observations only)

`engine-kit/orchestrator/e2e_executor.py`: `BrowserExecutor` ABC `run(contract, checklist,
evidence_dir, env) -> ExecutorResult` (artifacts + per-`criterion_id` `executor_status` +
exit_code; never a verdict). `LocalHttpExecutor` — deterministic/offline (stdlib subprocess
fixture, `html.parser` asserts, client-side network capture + console sink, DOM/text snapshot
"screenshots" hashed, backend-state read, shutdown). `PlaywrightExecutor` — env+import gated
(`AIDAZI_E2E_PLAYWRIGHT=1`, else `ExecutorUnavailable`); real pixels/console; never offline CI.
New `delivery-loop.md §4.2.8` anti-pattern: "Acceptance drives the browser itself."

## §8 Fixture app + maintained tests

Fixture `…/tests/fixtures/e2e_app/`: stdlib `http.server` — `/`, `/submit`, `/result`,
`/__console`, `/__state`, `/api/data`; modes `normal|render_defect|state_mismatch|
console_error|net_fail`. Deterministic, offline.

Tests (offline; LocalHttpExecutor + MockAdapter judge): 1 launch/readiness; 2 happy-path PASS;
3 render_defect detected; 4 state_mismatch detected; 5 console+failed-network persisted; 6
screenshots+checklist referenced from audit chain; 7 interruption→resumable; 8 resume no
duplicate run; 9 incomplete evidence → gate_hard_fail (no Acceptance); 10 advisory → human
gate; 11 campaign: 2 milestones, one user-facing — fires only there. **Negatives:** 12
malformed/missing `functional_evidence_refs` → schema reject; 13 verdict class mismatch →
gate_hard_fail; 14 dir present but missing/mismatched ledger event → not-committed → re-run/
append (no skip); 15 contradictory pass (failed case / critical fail / coverage gap) →
needs_human; 16 crash after verdict pre-routing → reroute SAME verdict (no re-spawn/flip); 17
authority OR criteria/prompt context (charter/calibration/checklist/intent_contract/executor-
contract/derived-context) edited between produce & resume → re-spawn, never reroute/auto-ship
the stale verdict; 18
campaign STATUS_RUNNING crash → resume in-flight unit, no double-account; 19 missing Dev
self_smoke on browser_e2e → halt; 20 static F5 evidence-hash binding (stale static verdict not
reused). PlaywrightExecutor smoke skipif-gated. No billed LLM / internet in normal CI.

## §9 Decisions (recommendations; * = human-answered)

- D1 evidence location: prompt layout `.orchestrator/audit/browser/…`; schema via branch-
  correct `acceptance_class` (§4.1). Diverges from signed §4.5 (`eval/runs/<id>/e2e/`) — flagged.
- D2* executor: interface + deterministic LocalHttpExecutor + gated PlaywrightExecutor.
- D3 Dev self-smoke: parseable handoff block + structural presence gate on browser_e2e (§6a).
- D4 failure checkpoint: reuse `gate_hard_fail` + reconcile-based recovery.
- D5 trigger: per-milestone `functional_acceptance` (projected; precedence §4.2) + charter-level mechanics.
- **D6:** acceptance resume strengthened to evidence-bound, snapshot-frozen reroute (§3.5b) —
  a determinism/fail-closed change touching the P-A acceptance resume + authority-read path
  (fresh runs byte-identical). Flagged.
- **D7:** campaign `STATUS_RUNNING` recovery resumes + reconciles the in-flight unit/accounting
  (§3.5c) — a bounded correctness change to P-B crash recovery. Flagged.
- Review gate*: Codex (available) — iterating to APPROVE before implementation.

## §10 Non-goals

No 6th QA role. No auth / remote-deploy / Redis / Celery / cloud-browser. No real browser in
offline CI. No expansion of Acceptance authority (M3 advisory; no M3 record shipped). No P-B
parallelism / auto-decompose. No change to P-A/P-B authority or gating semantics beyond the
projection hook, the additive acceptance evidence section, and the flagged determinism/recovery
fixes D6/D7. No unrelated cleanup. `$`-cost out of scope.

## §11 File-level plan (bounded increments)

New (8): `schemas/{executor-contract, functional-checklist, browser-evidence-manifest,
acceptance-calibration-record}.schema.json`; `engine-kit/orchestrator/e2e_executor.py`;
`engine-kit/orchestrator/tests/fixtures/e2e_app/`; `…/tests/test_e2e_*.py`;
`process/browser-e2e-acceptance.md`.

Modified (≈12): `driver.py` (E2E state + `_commit_e2e` reconcile + evidence-bound snapshot
reroute + consistency gate (incl. evidence-ref↔manifest binding) + active-class calibration
API + runtime hard-fail + RunState fields `{e2e_run_id, e2e_evidence_ref, e2e_manifest_hash,
acceptance_evidence_hash, acceptance_snapshot{evidence_hash, authority_fingerprint, acceptance_input_hash, authoritative}}`
+ schema load); `campaign.py` (projection precedence + STATUS_RUNNING
unit/accounting reconcile); `schemas/{mission-charter, acceptance-verdict, campaign-plan,
case-spec}.schema.json`; `validators/charter_validator.py` (functional/e2e validation; floor 9);
`templates/mission-charter.yaml`; role-cards `{dev, acceptance, deliver, code-reviewer}-agent.md`;
`process/{delivery-loop.md, campaign-loop.md}`.

Increments: I1 schemas+charter+validator → I2 executor interface + LocalHttpExecutor + fixture
→ I3 driver E2E state + `_commit_e2e` reconcile + resume + audit → I4 acceptance boundary +
consistency gate + active-class calibration + snapshot reroute → I5 campaign projection +
STATUS_RUNNING reconcile → I6 docs/role-cards → I7 maintained tests (incl. negatives 12-20) +
full offline suite.
