---
title: Browser-E2E Acceptance Gate (P-C)
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-21
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 20KB
notes: >
  The browser-E2E acceptance gate (P-C) adds a USER-PERSPECTIVE functional evidence
  stage to the Delivery Loop: for a milestone whose charter sets
  tooling.acceptance.functional.mode: browser_e2e, the orchestrator drives the running
  app through declared journeys, commits hash-anchored evidence, and hands the captured
  manifest to Acceptance (read-only). It is a CAPABILITY, not a sixth role — the
  five-role chain is unchanged. Absent the opt-in charter keys, behavior is byte-identical
  to today's static (M1) acceptance. Spec + rationale:
  archive/2026-06-20-pc-browser-e2e-design.md (rev7), refining
  archive/2026-06-20-autonomous-delivery-design.md §4. Implementation:
  engine-kit/orchestrator/{driver.py, e2e_stage.py, e2e_executor.py};
  schemas/{executor-contract, functional-checklist, browser-evidence-manifest,
  acceptance-calibration-record}.schema.json.
---

# Browser-E2E Acceptance Gate (P-C)

Static (M1) acceptance judges code-execution evidence (the F5 eval artifact;
`delivery-loop.md` §4.2.6). For a **user-facing** milestone that is not enough: the
question "does the running app actually do the right thing for a user?" needs the app
*driven* and *observed*. The **browser-E2E acceptance gate** adds exactly that, as an
opt-in functional (M3) class layered on top of the existing Acceptance gate.

The chain does **not** grow a role. The browser EVIDENCE is captured by an
**orchestrator-owned executor** (a capability); the **Acceptance Agent stays the sole
verdict producer** and stays read-only — it judges the captured manifest, it never
drives the browser. This is the load-bearing boundary of P-C (§5, anti-pattern in
`delivery-loop.md` §4.2.8).

**Default-off:** absent the charter keys below, `_acceptance_class()` is `static`, no
E2E stage runs, and the milestone closes byte-identically to today. Adopting the gate is
two opt-in charter blocks plus one Research-signed checklist (§2).

## §1 Trigger + lifecycle

### §1.1 What turns it on
The active acceptance class is derived per milestone:
`tooling.acceptance.functional.mode == "browser_e2e"` → class `browser_e2e` (M3); else
`static` (M1, today). In a campaign the class is read from the **derived milestone
charter** (the per-milestone `functional_acceptance` projection — `campaign-loop.md`
§3.7), so it is correct per milestone.

### §1.2 Where it runs in the state machine
A new **out-of-band** Driver state `e2e_evidence_pending` runs AFTER the milestone's
Code Review / close advance and BEFORE milestone-close Acceptance — and ONLY for a
`browser_e2e` milestone (`delivery-loop.md` §4.2.4). The sequence at milestone complete:

```
close → advance (STATE_ADVANCE)
  if browser_e2e:  e2e_evidence_pending → (then) acceptance_pending
  elif acceptance enabled:  acceptance_pending          # unchanged static path
  else:  STATE_ADVANCE                                  # unchanged disabled path
```

It is out-of-band exactly like `acceptance_pending`: a crash mid-capture re-enters
`e2e_evidence_pending` on resume (handled BEFORE the acceptance re-entry), and resume is
non-duplicating (§3.3).

### §1.3 The stage, step by step
On entry to `e2e_evidence_pending` the orchestrator:
1. **Dev self-smoke gate** (§6) — structurally verify `docs/self-smoke.json` exists and
   carries non-empty `{command, result}`; absent/malformed → resumable `gate_hard_fail`.
2. **Commit evidence** (§3) — reconcile an already-committed run, or run the executor,
   write `manifest.json` + `checklist-results.json`, publish atomically, and append the
   `browser_e2e_evidence` Audit Spine event. Any runtime failure → `gate_hard_fail`.
3. **Proceed into Acceptance** — the milestone-close Acceptance gate runs with the
   committed manifest as its evidence (§4).

## §2 The two contracts (who owns what)

P-C deliberately splits MECHANICS from CRITERIA — the same Research-owns-the-bar /
Deliver-owns-the-how split as the rest of the chain.

- **`charter.tooling.e2e`** — the executor **MECHANICS** (the *how*), conforming to
  `schemas/executor-contract.schema.json`. **Owned by Deliver/adopter, MUTABLE.**
  Defines `executor_kind` (`local_http` | `playwright`), `app_start_cmd` (with optional
  literal tokens `{port}`/`{store}`/`{mode}` the driver substitutes at runtime),
  `readiness {url|cmd, timeout_seconds}`, `base_url` (local only), `allowed_origins[]`
  (local only; fail-closed), and `journeys[{id, steps[]}]`. A step `action` is one of
  `navigate | fill | click | assert_text | assert_selector | assert_state |
  assert_no_console_error | assert_request_ok`; each **assertion** step carries a
  `criterion_id` (linking it to a checklist criterion) and an optional `critical` flag.
  Mechanics **produce** evidence; they NEVER define pass/fail.
- **`<adopter>/…` functional-checklist** — the signed **CRITERIA** (the *what*),
  conforming to `schemas/functional-checklist.schema.json`, located at
  `tooling.acceptance.functional.checklist_path`. **Authored by Research, frozen at
  Gate-1 sign-off.** Each criterion is a user-visible observable outcome with a UNIQUE
  `criterion_id` and an optional `critical` flag. Deliver/Dev may NOT edit it
  post-sign-off (a needed change → `research_contract_revision`, Gate-1 re-fires).

The two are distinct on purpose: the executor's `criterion_id`s must exist in the signed
checklist (the executor fail-closes on a mismatch), and the Acceptance verdict's cases
must cover the checklist's `criterion_id` set exactly (§4).

The functional block also carries `judge_calibration_m3 {status, record_id}` (the M3
calibration record). **v1 ships no M3 record**, so M3 is never calibrated → the
functional class is **advisory** (§5).

## §3 Evidence contract + layout

### §3.1 Layout
Committed evidence lives under, and is published atomically from a sibling staging dir:

```
.orchestrator/audit/browser/<loop_id>/<run_id>/
  manifest.json            # browser-evidence-manifest.schema.json (driver-written)
  checklist-results.json   # per-criterion: criterion_id → action → observed → status
  screenshots/             # DOM/text snapshots (local_http) or real pixels (playwright)
  console.json             # captured console messages
  network.json             # captured requests
  app-start.log  app-stop.log
  executor-config.json     # the concrete runtime contract that ran
  backend-state-refs.json  # backend-state reads
```

`<run_id>` is a deterministic, **persisted** per-(loop, sub-sprint) id. Recovery keys on
it plus the ledger event — never on a transient cache.

### §3.2 Hash anchor
The driver computes a per-artifact `sha256` and an
`artifact_manifest_hash = sha256(canonical_json(sorted [{name, sha256}]))`, then appends
ONE hash-chained `browser_e2e_evidence` event to the Audit Spine —
`{run_id, manifest_ref, manifest_sha256, artifacts[]{name, sha256}, exit_code,
checklist_summary}`. That event is the ledger anchor; reconcile and the pre-acceptance
gate both recompute and verify it.

### §3.3 Durable commit / recovery
On every entry the commit step is idempotent:
- **Reconcile** — if the final dir is complete, every artifact hash matches, the manifest
  hash recomputes, AND a matching `browser_e2e_evidence` event exists → use it; do not
  re-run.
- **Finish a crashed publish** — if the final dir is complete + hash-verified but the
  ledger event is missing → append the one event; do not re-run.
- **Re-run** — if the final dir is absent / partial / has a stray file / fails any hash →
  discard staging, run the executor afresh, publish, append the event.

An incomplete or stray-bearing dir is NEVER trusted (fail-closed; it forces a re-run,
never a skip). `executor_status` is a captured **observation**; the executor exits 0 even
when a criterion fails (the failure is in the evidence, judged downstream). A non-zero
exit is a RUNTIME failure → `gate_hard_fail`.

## §4 Acceptance over the manifest (read-only; M3)

When the stage proceeds into Acceptance, the **same Acceptance Agent** runs, with the
committed manifest as its read-only evidence. The orchestrator's Acceptance prompt
addendum instructs the judge to:
- judge EACH signed `criterion_id` INDEPENDENTLY against the captured artifacts;
- emit `acceptance_class: "browser_e2e"`; every case carries its `criterion_id` and
  `functional_evidence_refs` (`{kind, path, sha256}`) citing artifacts under the committed
  run dir;
- cover the FULL checklist criterion set; pass only when every case passes AND no critical
  executor failure was observed.

The `executor_status` values in `checklist-results.json` are **observations, not
verdicts**: the judge MAY fail a criterion the executor marked pass, and MUST NOT pass a
criterion the executor observed `fail`/`error`.

### §4.1 Driver consistency gate (deterministic, layered on the verdict)
For a `browser_e2e` verdict the driver runs a deterministic consistency gate BEFORE
routing (`e2e_stage.check_acceptance_consistency`). A milestone `pass` is rejected unless
ALL hold; a malformed/integrity breach hard-fails:
- **Class match** — `acceptance_class == "browser_e2e"` (else `gate_hard_fail`).
- **Coverage** — the checklist `criterion_id`s are unique; each case carries a unique
  `criterion_id`; the case set EQUALS the checklist set. A gap → needs_human.
- **Case consistency** — a milestone pass requires every case `verdict == "pass"`.
- **Critical veto** — any `critical: true` criterion whose CAPTURED `executor_status` is
  `fail`/`error` turns a pass into needs_human (an observation cannot be overridden into a
  silent pass).
- **Brief presence** — `fix_required` ⇒ non-empty `failure_briefs`; pass ⇒ empty.
- **Evidence-ref binding** — every `functional_evidence_ref` (path + sha256) MUST resolve
  to a committed manifest artifact with a matching sha256. A ref to a non-existent /
  tampered / uncommitted artifact → `gate_hard_fail`. A judge cannot cite evidence outside
  the committed, ledger-anchored set.

The executor never emits a milestone verdict; Acceptance is the sole pass producer; a pass
that contradicts (or cites evidence outside) the committed manifest is structurally
unshippable.

## §5 M3 advisory boundary

M3 (browser/functional) acceptance is **ADVISORY in v1** — no M3 calibration record ships,
so `_calibration_status("browser_e2e")` is `uncalibrated`, the verdict is never
authoritative, and a `pass` does NOT auto-ship: the orchestrator writes the
`advisory_acceptance_pass_signoff` MANDATORY_CHECKPOINT (#9) and HALTs for a human's
`confirm: ship|reject`. The calibration gate is class-aware — a charter that is M1-calibrated
but M3-uncalibrated, running autonomous, correctly auto-degrades to `human_on_the_loop`
(`delivery-loop.md` §4.2.8 anti-pattern #2/#6).

**M1 (static) behavior is unchanged** by P-C: a static verdict takes the existing path
byte-for-byte (its evidence is the F5 eval artifact; its authority/calibration read the M1
record).

## §6 Dev self-smoke definition of done

For a `browser_e2e` milestone, the Dev self-smoke attests that the running app was exercised
once on the changed happy path, recorded at `docs/self-smoke.json` as `{command, result}`.
The orchestrator checks **presence** (structural — not correctness) at the
`e2e_evidence_pending` entry.

It is **necessary, not authoritative**, and **distinct** from the independent browser
evidence gate (§3): a Dev attesting "I ran it and it worked" does not substitute for the
orchestrator's own captured, hash-anchored evidence — both must hold.

### §6b — self-smoke autonomy (Phase-4, design §6b): NEVER a routine human halt

The self-smoke must never make the loop depend on a human to run the app. Two mechanisms make
the absence path autonomous, keyed on the executor class:

- **PRIMARY — subsumed for `external_test_runner`.** The managed run already starts the app
  (readiness poll), runs the real spec-runner, and produces framework-owned provenance (§3/§4);
  that IS the self-smoke evidence (app-start + a real journey with captured provenance, strictly
  stronger than a hand-written `{command, result}`). So for `external_test_runner` the separate
  `docs/self-smoke.json` structural gate is **SUBSUMED** (skipped) — no separate artifact, no
  separate hard-fail. The independent browser-evidence gate is NOT weakened: the managed run's
  provenance verification (`verify_execution_provenance`, fail-closed) is the substitute
  attestation, nothing less.
- **FALLBACK — bounded autonomous Dev re-dispatch for the in-process `playwright` class.** When a
  SIGNED `charter.autonomy.e2e_remediation` budget is present (HOTL+), a missing/malformed
  self-smoke is treated like a deterministic fault: the driver dispatches ONE bounded in-envelope
  Dev round (author `docs/self-smoke.json`) under the signed `max_rounds`, contained by the
  observed-diff envelope (approved_scope modules + the self-smoke artifact), then retries. The
  containment gate unavailable, an out-of-envelope diff, or the budget exhausted → a **resumable
  `gate_hard_fail`** (an authority pause, R4-a/b — not routine).
- **OTHERWISE — the structural presence gate stands** (`local_http`, or `playwright` without a
  signed budget): absence/malformed → a **resumable** `gate_hard_fail` exactly as before
  (legacy-safe, byte-identical). The Dev role card + prompt still mandate authoring it
  (belt-and-suspenders).

The self-smoke catches the obvious "the app doesn't even start on the happy path" failure at the
Dev seam. It is scoped to `browser_e2e` milestones (general-mandatory self-smoke is a follow-up).

## §7 Fail-closed matrix

No listed failure can become a silent milestone PASS.

| Failure | Mechanism |
|---|---|
| App start / readiness timeout / executor runtime error or unavailable | `gate_hard_fail` (resumable: re-run / accept / abort) |
| Invalid executor-contract / invalid functional-checklist | `gate_hard_fail` (validated on-load) |
| Missing Dev `docs/self-smoke.json` (browser_e2e) | subsumed for `external_test_runner` (§6b); bounded autonomous Dev re-dispatch for `playwright` under a signed budget; else a resumable `gate_hard_fail` (structural) — never a routine human halt |
| Missing / incomplete / stray / unanchored / hash-mismatched evidence | `gate_hard_fail` (reconcile/verify pre-acceptance) |
| Interrupted run (crash mid-capture) | reconcile keyed on `run_id` → re-run partial, or finish a crashed publish (no duplicate run) |
| Verdict wrong/absent `acceptance_class`, malformed/unbound evidence ref, missing `criterion_id` | `gate_hard_fail` (consistency gate, integrity) |
| A captured CRITICAL failure, a pass contradicting the evidence (non-pass case / failure_briefs), or a coverage gap | coerced to **needs_human** → `acceptance_surface_approve` checkpoint (never shipped) |

**No new MANDATORY_CHECKPOINT** — P-C reuses the existing `gate_hard_fail` and the
acceptance checkpoints; the checkpoint floor stays **9**.

## §8 Executor mechanics (orchestrator-owned)

The browser executor (`engine-kit/orchestrator/e2e_executor.py`) is orchestrator-owned and
emits OBSERVATIONS only (per-`criterion_id` `executor_status` + artifacts + exit code;
never a verdict):
- **`local_http`** — the deterministic, offline default (stdlib subprocess fixture,
  `html.parser` assertions, client-side network + console capture, DOM/text snapshot
  "screenshots", backend-state read, shutdown). This is what offline CI runs — no billed
  LLM, no internet.
- **`playwright`** — real browser, opt-in + env-gated (`AIDAZI_E2E_PLAYWRIGHT=1`, else
  unavailable); real pixels/console; never run in offline CI.
- **`external_test_runner`** — the managed adopter spec-runner (e.g. `npx playwright test`),
  env-gated (`AIDAZI_E2E_EXTERNAL_RUNNER=1`); the **REAL-EXECUTION** class that carries
  framework-generated provenance (`run-provenance.json` + the in-flight nonce / audit-spine
  window, §4). `{playwright, external_test_runner}` are the only classes that may route to a
  browser_e2e Acceptance verdict; `local_http` is the DRY-RUN class and is refused at the
  acceptance-routing seam.

The driver injects per-run values at the gate: it substitutes `{port}`/`{store}`/`{mode}`
in `app_start_cmd`, sets a concrete `base_url` (the static host + an allocated free port),
and provides PORT/STORE/MODE to the child env. The static charter form stays
portless/templated; the runtime form is concrete and re-validated (fail-closed).

## §8b Phase-4 native-E2E adoption surface (capability contract · onboarding · migration)

- **Framework capability contract** — `governance/framework-capabilities.json` (machine-readable,
  schema `schemas/framework-capabilities.schema.json`) declares the capabilities THIS aidazi build
  provides (`native_managed_external_e2e`, `framework_owned_e2e_provenance`,
  `autonomous_e2e_remediation`, `codex_adapter_liveness`), each anchored to a real code symbol
  (`code_anchor`) so identity does not depend on mutable doc text. An adopter DECLARES what it
  needs in `charter.required_framework_capabilities` (bound into `charter_hash ⊂ H`). Preflight
  (`run_loop --sign-plan`) and the real-run gate refuse **deterministically, fail-closed** when a
  required capability is missing/under-versioned or the contract is unreadable, naming the missing
  capability, the deployed framework version, and the upgrade action
  (`engine-kit/framework_capabilities.py`).
- **Onboarding proposal generator** — `engine-kit/tools/e2e_config_proposal.py` drafts a COMPLETE,
  runnable `tooling.e2e` + `tooling.acceptance.functional` proposal for an eligible user-facing
  requirement (all elements: executor/runner, spec, app-start/readiness, criterion map, evidence
  path, timeouts/retry/remediation budgets, cleanup, NAMED secret refs, ledger/`covers_req_ids`/
  `surface` linkage, functional checklist, autonomy + §1.7-G eligibility, capability pins).
  Advisory (`proposal_status`/`proposal_confidence`), no new runtime gate, binds only on
  whole-proposal human authorization. Two fail-closed guardrails: `proposal_completeness_violations`
  (never emit a skeleton) and `secret_leak_violations` (NAMED refs only — no materialized secret).
  Worked example: `examples/native-e2e-adopter/`.
- **Existing-adopter migration audit** — `engine-kit/tools/e2e_migration_audit.py` is READ-ONLY:
  it detects native-E2E gaps for a deployed adopter and emits an advisory migration proposal,
  requiring explicit human authorization before any authoritative artifact changes. An aidazi
  upgrade alone NEVER mutates campaign plans, signed charters, requirement ledgers, Acceptance
  reports, E2E configuration, or aidazi pins; legacy non-user-facing milestones stay valid and are
  never forced into browser E2E.

## §9 Editing this doc
Process-tier; edits at fold-back cadence (Constitution §8). The implementation is the
source of behavior (`engine-kit/orchestrator/{driver.py, e2e_stage.py, e2e_executor.py}`);
the design rationale is `archive/2026-06-20-pc-browser-e2e-design.md` (rev7). If this file
and the code disagree, reconcile at fold-back.
