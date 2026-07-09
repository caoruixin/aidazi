# Judge calibration workflow (Acceptance auto-ship on-ramp)

**Status:** Phase-3 lever 3 (design `archive/2026-07-09-phase3-halt-conditions-design.md` §5.2). This
is the **documented workflow + ledger contract**; it does not add a runtime gate. It explains how an
adopter earns `tooling.acceptance.mode: auto` — the constitution's OWN authoritative auto-ship
channel (Constitution §1.7-C / §3.6) — without weakening any gate.

**Why it exists:** until the Acceptance judge is *calibrated*, an Acceptance `pass` stays **advisory**
— it HALTs once at `advisory_acceptance_pass_signoff` for a human ship sign-off (design §1.2). That
is by design: an uncalibrated judge is not trusted to ship. Calibration is the measured evidence
that flips that trust. Nothing here bypasses the checkpoint; it documents the on-ramp to the
constitution's existing `mode: auto` authority.

---

## 1. The ledger (what "calibrated" is recorded as)

The calibration record is the **existing** `schemas/acceptance-calibration-record.schema.json` — one
record per acceptance class (`static` = M1, `browser_e2e` = M3), keyed by the **FULL judge
identity** (`role/harness/provider/model` + `effective_config_hash` + `skill_set_hash` +
`prompt_version` + …). The charter's `tooling.acceptance.judge_calibration` block
(`status`, `agreement_threshold` default **0.9**, `flip_threshold` default **0.1**,
`labeled_set_path`, `record_path`) is the adopter-facing view of that record; `functional.
judge_calibration_m3` is the SEPARATE M3 record.

Recommended on-disk layout (adopter repo):

```
calibration/
  labeled_acceptance_cases/
    manifest.json                      # the labeled set: [{case_id, inputs_ref, human_verdict}]
  acceptance-<class>-<provider>-<model>.calibration.json   # the record (schema above)
```

The record carries the OUTCOME (`status`, thresholds, identity, `calibrated_at`); the
`labeled_set_path` points at the labeled cases the agreement was measured over. Keep both in version
control (diffable, auditable).

## 2. Thresholds (when `status: calibrated` may be set)

Over a labeled set of **≥ N** cases (recommend N ≥ 20 spanning pass / fix_required / needs_human,
including the adopter's known bad cases):

- **agreement_rate** = (# cases where the judge verdict == the human label) / N — must be **≥
  `agreement_threshold`** (default 0.9).
- **flip_rate** = (# cases where the judge would flip a human *fail* to a *ship*, i.e. a
  false-authoritative-pass) / (# human fails) — must be **≤ `flip_threshold`** (default 0.1). Flips
  are asymmetric-cost: a judge that wrongly ships is far worse than one that wrongly halts, so this
  bound is tighter than raw agreement.

`status: calibrated` is set ONLY when **both** hold. Otherwise `status: uncalibrated` (acceptance
stays advisory). The labeled set + both computed rates are recorded alongside the record so a
reviewer can reproduce the decision deterministically.

## 3. Re-calibration triggers (when `calibrated` reverts to `uncalibrated`)

Calibration is bound to the EXACT judge identity + inputs. `status` reverts to `uncalibrated`
(⇒ acceptance re-halts at `advisory_acceptance_pass_signoff`) on ANY of:

1. **Judge binding change** — acceptance `role/provider/model/harness/capability_ref` (Constitution
   §3.6 — calibration is per-(role,provider,model)).
2. **Prompt / skill change** — a change to the acceptance prompt or `tooling.acceptance.skills`
   (the record's `effective_config_hash` / `skill_set_hash` / `prompt_version` no longer match;
   the template already warns "Changing tooling.acceptance.skills invalidates
   judge_calibration.status").
3. **Contract change** (M3) — a new browser-evidence-manifest or executor contract
   (`evidence_contract_id` / `executor_contract_id`).
4. **Staleness window** — a scheduled re-calibration cadence the adopter sets (recommend re-checking
   at least each release train).
5. **A human-flagged miss** — a `bad_case_manual_review` where the judge disagreed with a human on a
   shipped milestone: add the case to the labeled set and re-calibrate.

Detection is mechanical: the acceptance authority resolver already checks the record's identity
hashes against the ACTIVE effective config; a mismatch ⇒ the record does not apply ⇒ advisory.

## 4. The unlock path (calibrated → authoritative auto-ship)

Authoritative auto-ship (an Acceptance `pass` ships WITHOUT a human checkpoint, Constitution
§1.7-C) requires ALL of, together:

1. `tooling.acceptance.judge_calibration.status: calibrated` (for the ACTIVE class) — earned via §2;
2. `tooling.acceptance.mode: auto`;
3. `autonomy.level: fully_autonomous_within_budget`.

Absent any one, an Acceptance pass stays advisory and HALTs for sign-off. This document does **not**
change that gate — it documents the earned on-ramp. M3 (browser_e2e) additionally needs a
`judge_calibration_m3` record; v1 ships none, so a browser-functional pass stays advisory until an
adopter builds and calibrates an M3 labeled set.

## 5. Relationship to Phase-3 halt conditions

Independent, complementary: `autonomy.halt_conditions` (design §3) adds user-declared STRUCTURAL
halts that fire regardless of calibration; judge calibration governs the OUTCOME-based auto-ship
authority. A calibrated judge + `mode: auto` removes the per-milestone advisory sign-off; halt
conditions can still pause the campaign at the milestones/classes the human pre-set. Neither relaxes
a MANDATORY_CHECKPOINT.

**Not built this round (Phase-3 = doc/design):** the calibration *tool* (labeled-set runner +
rate computation + record writer). A meaningful tool needs a real golden verdict set to exercise;
this document freezes the ledger contract + thresholds + triggers so that build is well-scoped.
