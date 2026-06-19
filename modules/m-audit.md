---
title: M-Audit module — the Audit Spine
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
  M-Audit module spec — the Audit Spine. Defines the append-only, hash-chained,
  reconstructable per-loop ledger that threads one loop_id through the whole
  Delivery Loop (charter→brief→checkpoint→spawn→trace→verdict→close). This is the
  NORMATIVE source-of-truth for the audit event contract + hash-chain semantics;
  engine-kit/audit/ (audit_log.py + audit_report.py) is the reference impl and
  schemas/audit-event.schema.json validates structure — both back THIS doc, and
  on conflict the spec wins. Audit is runtime-owned (Constitution §1.4). Closes
  the G1–G6 gaps from the v2-loop-engine plan §4.5. The Audit Spine is the Next1
  precondition that lets the human move from synchronous gatekeeper to
  asynchronous reviewer (plan §4.6).
---

# M-Audit module — the Audit Spine

The M-Audit module defines the **Audit Spine**: the append-only, hash-chained, deterministically-reconstructable per-loop ledger that records what happened across one Delivery Loop. It threads a single `loop_id` through every load-bearing event — charter load, brief, checkpoint, spawn, trace reference, verdict, close — so a loop can be reviewed AFTER the fact against a record the loop itself cannot silently rewrite.

The Audit Spine is **runtime-owned** per Constitution §1.4 ("trace and eval contract" — extended in the v2-loop-engine plan §6 edit #5 to name the Audit Spine, validators, and scope_envelope as runtime-owned). The LLM does not author audit events; the deterministic engine (the standalone driver, or a thin paste-mode logger) emits them as a side-effect of running the loop.

This module is the **normative source-of-truth** for its concern. Two artifacts back it and MUST match it:
- `schemas/audit-event.schema.json` — validates the per-event STRUCTURE.
- `engine-kit/audit/audit_log.py` + `engine-kit/audit/audit_report.py` — the reference implementation (append + hash-chain + verify + reconstruction report).

Per the v2-loop-engine plan §1 conflict rule and `engine-kit/audit/README.md`: **the spec wins; the kit is then a bug.**

## §1 What the Audit Spine is — and why

### §1.1 What it is

A per-loop ledger at `.orchestrator/audit/<loop_id>.jsonl` — one JSON event per line, in append order. The ledger is:

- **Append-only** — events are only ever appended; the engine never edits or deletes a prior line.
- **Hash-chained** — each event commits to the previous event's hash (§3), so altering any byte of any past event breaks the chain from that point onward. This makes the ledger **tamper-evident** (not tamper-proof; the point is that silent rewrites are detectable).
- **Per-loop** — one ledger file per `loop_id`. The `loop_id` is the causal thread (G6).
- **Reconstructable** — a deterministic, no-LLM report (§5) projects the ledger into a human-readable timeline.
- **Mode-independent** — the same event contract applies whether the loop ran under the orchestrator/driver or in paste (semi-manual) mode (§4).

The Audit Spine is NOT:
- A trace (`modules/m-trace.md`) — a trace records ONE execution unit's internals (intent gates, tool calls, slots). The Audit Spine records the LOOP's event sequence and references trace IDs; it does not duplicate trace content (§6).
- An eval verdict store — verdicts live in their own artifacts; the Audit Spine records a `verdict_ref` pointer.
- A debug log — it is a structured, hash-committed event sequence, not free-form output.

### §1.2 Why — the Next1 precondition

The differentiator between this framework and vanilla "loop engineering" is that the loop is **auditable and gated** (plan §1). Auditability is precisely what lets the human shift from a **synchronous gatekeeper** (must be present at every gate, in real time) to an **asynchronous reviewer** (reviews a complete, tamper-evident record on their own schedule).

The Audit Spine is **Next1** — the precondition for **Next2** (on-demand audit, fewer synchronous gates, gate recommendations; plan §4.6). Without a guaranteed, reconstructable record, "review later" is not safe: there is nothing trustworthy to review later. This module makes auditability a first-class GUARANTEE rather than an emergent property of scattered artifacts.

Note: async preparation and recommendation are permitted, but the **final confirmation of any authority gate always folds back to the authorized human** (Constitution §1.7-D; plan §4.6 OQ-B resolution). The Audit Spine reduces the human's load; it does not remove the human's authority.

### §1.3 The G1–G6 gaps it closes

Per the v2-loop-engine plan §4.5, auditability was PARTIALLY satisfied before this module (durable-artifact rule §3.4#1, checkpoint decision files, `events.jsonl`, `calls/` input-hash+verdict, structured verdicts, m-trace, F5 evidence, append-only ledgers). The Audit Spine closes six named gaps:

| Gap | Problem before | How the Audit Spine closes it |
|---|---|---|
| **G1** | No first-class Audit spec — auditability emergent, not guaranteed | This module + `schemas/audit-event.schema.json` make audit a first-class, named contract. |
| **G2** | Not tamper-evident — "review later" had no record the loop couldn't silently rewrite | Append-only hash chain (§3); `verify_chain` returns the first broken seq. |
| **G3** | Execution-context not captured — `calls/` lacked harness/model/skill-pins/memory/tokens | Per-spawn execution-context payload (§3.4), `make_spawn_payload(...)`. |
| **G4** | No human-readable view — scattered machine artifacts; no end-to-end reconstruction | Deterministic no-LLM reconstruction report (§5). |
| **G5** | Orchestrator-dependent — paste mode lacked `events.jsonl` / `calls/` | Mode-independent contract; paste mode appends the same events (§4). |
| **G6** | No causal link — no `loop_id` threading the whole loop | `loop_id` threads charter→…→close; one ledger per loop (§2). |

## §2 The `loop_id` causal thread

A single `loop_id` is assigned at loop ingress (per the intent contract; `schemas/intent-contract.schema.json` anchors `loop_id`) and threads the entire loop:

```
charter → brief → checkpoint → spawn → trace → verdict → close
   └──────────────── one loop_id ────────────────┘
```

The ledger file is named `<loop_id>.jsonl`. Every event in the file carries the same `loop_id` (it is one of the seven required event fields, §3.1). This is the causal link that lets a reviewer reconstruct exactly which charter, which brief, which spawns, which verdicts, and which close belong together — closing G6.

Memory entries (`modules/m-memory.md`) distilled at close record their `source_loops` as `loop_id`(s), threading institutional memory back to the auditable record.

## §3 The event contract (NORMATIVE — matches audit_log.py field-for-field)

This section is the authoritative event contract. It MUST match `schemas/audit-event.schema.json` and `engine-kit/audit/audit_log.py` exactly.

### §3.1 Event shape

Every ledger line is one JSON object with exactly these seven fields, in this body order:

```json
{
  "loop_id":   "<string, minLength 1>",
  "seq":       <integer, ≥ 0>,
  "ts":        "<string, minLength 1; ISO 8601 by convention>",
  "type":      "<string, minLength 1; free-form event type>",
  "payload":   <object | array | string | number | boolean | null>,
  "prev_hash": "<64 lowercase hex chars>",
  "hash":      "<64 lowercase hex chars>"
}
```

- `additionalProperties: false` — no field beyond these seven is permitted.
- All seven are REQUIRED (`required: [loop_id, seq, ts, type, payload, prev_hash, hash]`).

Field semantics:

- **`loop_id`** — the causal thread (§2); the ledger file is `<loop_id>.jsonl`.
- **`seq`** — monotonic per-loop sequence. The **first event is `seq = 0`**; each subsequent event is `+1`. `verify_events` enforces this (an out-of-order seq is a chain break).
- **`ts`** — event timestamp, INJECTED by the caller. The pure append/hash path never reads the clock (determinism contract, §3.5); the orchestrator supplies a real ISO-8601 timestamp, and tests inject a fixed one. Stored verbatim as part of the hashed body.
- **`type`** — a free-form event-type string. Conventional values: `loop_init`, `charter_loaded`, `checkpoint` (the driver emits e.g. `checkpoint_emitted`), `spawn`, `verdict`, `close`. The ledger is a generic event log; the type is not enum-constrained at the schema level.
- **`payload`** — a generic payload (object / array / scalar / null). The ledger stores whatever it is given. For a per-spawn event the payload is the execution-context record (§3.4 / `$defs/spawn_payload`).
- **`prev_hash`** — the previous event's `hash`; `"0" * 64` (the genesis prev_hash, `GENESIS_PREV_HASH`) for the first event.
- **`hash`** — sha256 over `prev_hash + canonical_json(event_without_hash)` (§3.2).

### §3.2 The hash (NORMATIVE)

```
canonical_json(obj) = json.dumps(obj, sort_keys=True, separators=(",", ":"))
hash = sha256( prev_hash + canonical_json(event_without_hash) ).hexdigest()
```

Where `event_without_hash` is the event object with the `hash` field removed — i.e. the body `{loop_id, seq, ts, type, payload, prev_hash}`. The first event's `prev_hash` is `GENESIS_PREV_HASH = "0" * 64`.

This matches `audit_log.compute_hash` + `audit_log.make_event` exactly:
- `make_event` assembles the body `{loop_id, seq, ts, type, payload, prev_hash}` first, then computes `hash = compute_hash(body, prev_hash)` and appends it.
- `compute_hash(event_without_hash, prev_hash)` returns `sha256((prev_hash + canonical_json(event_without_hash)).encode("utf-8")).hexdigest()`.

`canonical_json` (sorted keys, no whitespace, `(",", ":")` separators) is the hash basis AND the on-disk serialization (each line is `canonical_json(event) + "\n"`).

### §3.3 Chain semantics + verification

Because each event's body includes `prev_hash`, and the hash commits to the body, every event transitively commits to the entire prior chain. Altering any byte of any event breaks the chain from that `seq` onward.

`verify_events(events)` / `verify_chain(path)` (in `audit_log.py`) checks, for each event in file order:
1. `seq == i` (monotonic from 0; else "out-of-order seq").
2. stored `prev_hash == ` the prior event's `hash` (genesis for the first; else "prev_hash mismatch").
3. recomputed `hash` (over the body, chained to the running prev_hash) `==` stored `hash` (else "hash mismatch (event body tampered)").

It returns a `ChainResult` whose `bad_seq` is the **first** offending seq (`None` if intact). A **corrupt/truncated ledger** (a line that is not valid JSON) is itself an integrity failure: `read_events` raises `LedgerCorruption(line_no, reason)`, and `verify_chain` reports it as `ok=False` with `corrupt_line` set — never a raw traceback. A damaged ledger is a tamper signal for this tool.

CLI: `python audit_log.py verify <loop_id.jsonl>` — exit `0` if the chain is intact, non-zero (and the first offending seq / corrupt line) otherwise.

### §3.4 Per-spawn execution-context payload (G3)

A per-spawn event carries the execution-context record as its `payload` (`$defs/spawn_payload` in the schema; `audit_log.make_spawn_payload(...)`). This extends the orchestrator's `calls/` record so a loop reconstructs with full harness/model/skill/memory/cost context:

```yaml
payload:                         # spawn_payload
  role:            <string>      # REQUIRED — research | deliver | dev | code_reviewer | acceptance | engine
  harness:         <string>      # REQUIRED — claude_code | codex | headless | ...
  provider:        <string>      # REQUIRED — anthropic | openai | deepseek | moonshot | ...
  model:           <string>      # REQUIRED — model id
  skill_pins:      [<string>]    # vendored skill ids @ pin (Facet B; skills/registry.yaml)
  memory_injected: [<string>]    # memory entry ids injected at ingress (modules/m-memory.md)
  input_hash:      <string|null> # hash of the spawn input (ties to calls/ input-hash)
  verdict_ref:     <string|null> # pointer to the verdict artifact this spawn produced
  prompt_ref:      <string|null> # run-dir-rel path to the as-dispatched prompt transcript (always; delivery-loop §4.2.10)
  output_ref:      <string|null> # run-dir-rel path to the captured output transcript; null on adapter transport error
  run_mode:        <string|null> # live | mock | replay | shadow (modules/m-trace.md §3)
  tokens:          <integer|null>
  cost:            <number|null>
```

Required spawn-payload fields: `role`, `harness`, `provider`, `model`. The rest are optional (null/empty default in `make_spawn_payload`). `additionalProperties: false`. The four required fields capture the Facet A execution binding (`process/role-configuration-contract.md`) that ran each step, so the audit answers "what exactly ran this spawn, on which model, with which skills + injected memory, at what cost."

Note: the ledger itself stores ANY payload dict — `spawn_payload` is the documented shape for spawn events, not a constraint the generic `audit-event` payload field enforces. The reconstruction report (§5) recognizes a spawn event by the presence of the `role` / `model` / `harness` payload keys.

### §3.5 Determinism contract

The pure append/hash path is a **pure function of its inputs** — no clock, no network, no randomness:
- `ts` is injected by the caller (the orchestrator passes a real ISO timestamp; tests pass a fixed one). `append_event` REQUIRES `ts`.
- The next `seq` and `prev_hash` are derived deterministically from the current ledger tail (`seq=0` / `GENESIS_PREV_HASH` if empty).
- `make_event` / `compute_hash` / `canonical_json` are pure.

This keeps the hash reproducible and the spine deterministic — consistent with Constitution §1.4 (hard-kernel scripts MUST stay deterministic / no-LLM).

## §4 Mode-independent contract (orchestrator + paste mode)

The event contract is identical regardless of how the loop is driven (closing G5):

- **Orchestrator / standalone-driver mode** — `engine-kit/orchestrator/driver.py` threads one `loop_id`, holds the audit ledger path (`audit.audit_path(loop_id, audit_dir)`), and calls `append_event(loop_id, type, payload, ts=clock(), path=...)` at each load-bearing step (loop start, checkpoint emitted, spawn, verdict, close). `ts` non-determinism is injected via an injectable clock.
- **Paste (semi-manual) mode** — when there is no orchestrator, a thin logger (or the human, via a helper) appends the SAME events to the SAME `.orchestrator/audit/<loop_id>.jsonl` ledger. The events validate against the same schema; the chain verifies the same way.

A paste-mode loop's audit ledger may be sparser (fewer captured spawns) but it is the same contract — there is no "audit-capable" vs "audit-incapable" mode. The asynchronous-review posture (§1.2) therefore holds for manual-chain adopters too.

## §5 Deterministic reconstruction report (G4)

`engine-kit/audit/audit_report.py` renders a human-readable Markdown reconstruction of a ledger — closing G4. It is a **pure, deterministic, no-LLM projection**: no network, no LLM, no clock/random; same ledger ⇒ same report bytes.

The report (`render_report`) contains:
- A **header**: `loop_id`, event count, **chain-integrity verdict** (it re-runs `audit_log.verify_events`, so a tampered ledger is reported as `BROKEN at seq <n>`, not silently rendered as intact), first/last `ts`.
- A **timeline table**: `seq · ts · type · summary` (a compact one-line payload summary; table delimiters are escaped so a payload value can't break a row).
- A **per-spawn execution-context section**: for each event whose payload carries the spawn markers (`role` / `model` / `harness`), it lists the `SPAWN_PAYLOAD_FIELDS` (role / harness / provider / model / skill_pins / memory_injected / input_hash / verdict_ref / prompt_ref / output_ref / run_mode / tokens / cost), so the reconstruction shows what ran each step — including the per-spawn prompt + output transcript paths (delivery-loop §4.2.10).

A corrupt/truncated ledger renders an **integrity-failure report** (and the CLI exits non-zero) rather than crashing — the reconstruction must not pretend a ledger is intact when it cannot even be read.

CLI: `python audit_report.py <loop_id.jsonl> [-o out.md]`. The conventional output path is `audit/<loop_id>-report.md` (plan §4.5).

This report is the on-demand audit surface the asynchronous reviewer reads (Next2 / plan §4.6). On-demand filters/queries ("all auto-decided gates since I last looked") are a later increment (plan §4.6 / P6); the deterministic report generator is the foundation.

## §6 Relation to m-trace (reference, not duplicate)

The Audit Spine and the trace (`modules/m-trace.md`) are distinct, complementary records:

| | Audit Spine (this module) | Trace (`modules/m-trace.md`) |
|---|---|---|
| Granularity | One ledger per LOOP | One trace per execution UNIT (turn / step / run) |
| Records | The loop's event sequence (charter→…→close) | One unit's internals (intent gates, tool calls, slots, phases) |
| Integrity | Append-only hash chain (tamper-evident) | Structured runtime emission (no chain requirement) |
| Lifetime | Persisted per-loop ledger | May be ephemeral / per-eval-run |
| Cross-link | References trace via `trace_id` (in payloads / `verdict_ref`) | Carries its own `trace_id` + `run_mode` |

The Audit Spine **references** `trace_id` (and `run_mode`, surfaced in the spawn payload) — it does NOT duplicate trace content. A reviewer who needs the per-turn internals follows the `trace_id` from the audit event to the trace artifact. This keeps each record single-purpose (Constitution §1.7-A single-abstraction-layer spirit).

## §7 Naming discipline (Constitution §1.7-E)

The Audit Spine is a NAMED, distinct concept in the v4/v2 vocabulary (plan §2 glossary). It MUST NOT be conflated with the two loops:

- The **Audit Spine** is the RECORD — it records what the loops did; it is not itself a loop.
- The **Auto Loop** (Concept 1; `modules/m-autoloop.md`) is the Type A agent's self-improvement loop.
- The **Delivery Loop** (Concept 2; `process/delivery-loop.md`) is the multi-agent team's per-milestone delivery loop.

Per Constitution §1.7-E + §3.7, name each distinctly on first reference. "The audit drove the milestone close" is a naming-discipline breach — the Delivery Loop drives milestone closes; the Audit Spine RECORDS them. The Audit Spine serves BOTH loops (it records Auto Loop experiment events and Delivery Loop milestone events alike) but is neither.

## §8 Anti-patterns

- **Mutating a past event** — editing or deleting an emitted event line. Breaks the chain at that seq (detectable by `verify_chain`) and violates the append-only rule. A correction is a NEW appended event, never an in-place edit.
- **LLM-authored audit events** — letting a model write the ledger. Audit is runtime-owned (§1.4); events are emitted by deterministic code. An LLM-authored record can be silently shaped to look clean.
- **Reading the clock in the hash path** — making the hash depend on wall-clock time inside `make_event`/`compute_hash`. Breaks reproducibility; `ts` MUST be injected by the caller (§3.5).
- **Duplicating trace content into payloads** — copying full trace internals into audit payloads instead of referencing `trace_id`. Bloats the ledger and conflates the two records (§6).
- **Paste-mode "skip audit"** — treating audit as orchestrator-only. The contract is mode-independent (§4); paste mode appends the same events.
- **Silent reconstruction of a corrupt ledger** — rendering a report as if intact when the ledger can't be parsed / the chain is broken. The report MUST surface the integrity failure (§5).
- **Conflating the spine with a loop** — calling the Audit Spine a "loop" or saying it "drove" a close (§7 / §1.7-E breach).

## §9 What this module does NOT cover

- Trace shape + `run_mode` semantics — `modules/m-trace.md`.
- The verdict artifact shape — `schemas/acceptance-verdict.schema.json`.
- The intent contract that anchors `loop_id` at ingress — `schemas/intent-contract.schema.json` + `process/delivery-loop.md` ingress.
- The role execution binding captured in the spawn payload — `process/role-configuration-contract.md`.
- On-demand audit filters/queries — later increment (plan §4.6 / P6); this module specifies the ledger + reconstruction report they build on.
- Long-term retention / storage backend — adopter-domain (the ledger is just files under `.orchestrator/audit/`).

## §10 Cross-references

- Constitution §1.4 — Runtime owns: trace + eval/audit contract (Audit Spine named runtime-owned per plan §6 edit #5).
- Constitution §1.7-D — final confirmation of authority gates stays human (the async-review posture preserves it).
- Constitution §1.7-E + §3.7 — two-loops naming discipline; the Audit Spine is distinct from both loops.
- `archive/2026-06-15-v2-loop-engine-plan.md` §4.5 — the G1–G6 gaps + Audit Spine design; §4.6 — Next2 async-review posture.
- `schemas/audit-event.schema.json` — validates event STRUCTURE (matches §3).
- `engine-kit/audit/audit_log.py` — append + hash-chain + `verify_chain` + `make_spawn_payload` (reference impl of §3).
- `engine-kit/audit/audit_report.py` — deterministic reconstruction report (reference impl of §5).
- `engine-kit/orchestrator/driver.py` — threads `loop_id`, emits audit events per step (§4).
- `modules/m-trace.md` — trace shape + `run_mode`; the Audit Spine references `trace_id`, does not duplicate (§6).
- `modules/m-memory.md` — Loop Memory entries' `source_loops` thread back to the audit `loop_id`; memory is injected per spawn (`memory_injected`).
- `schemas/intent-contract.schema.json` — anchors `loop_id` at ingress.
- `process/role-configuration-contract.md` — Facet A execution binding captured in the spawn payload.

## §11 Editing this module

Module-tier; edits at fold-back sub-sprint cadence per Constitution §8.

The §3 event contract + §3.2 hash definition are LOAD-BEARING and must stay in lock-step with `schemas/audit-event.schema.json` + `engine-kit/audit/audit_log.py`. A change to the event shape, the seven required fields, the field order in the hashed body, or the hash formula is a BREAKING change to every existing ledger (the chain would no longer verify) — route through fold-back as a framework-level migration, never a silent edit. Adding a NEW event `type` (the `type` field is free-form) is non-breaking. Adding a field to `spawn_payload` is additive but must be reflected in the schema `$defs/spawn_payload` + `make_spawn_payload` + `SPAWN_PAYLOAD_FIELDS` together.

The spec is the source-of-truth: if this module and the kit disagree, the kit is the bug (plan §1 conflict rule).

---

End of M-Audit module (the Audit Spine).
