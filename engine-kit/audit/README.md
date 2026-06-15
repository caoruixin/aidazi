# Audit Spine — audit_log + audit_report

Deterministic, no-LLM, no-network, stdlib-only (json + hashlib) implementation of the Loop Audit Spine from the plan (`archive/2026-06-15-v2-loop-engine-plan.md` §4.5): a tamper-evident, append-only, hash-chained per-loop event ledger plus a deterministic human-readable reconstruction. `audit_log.py` appends one JSON event per line to `.orchestrator/audit/<loop_id>.jsonl`, where each event is `{loop_id, seq, ts, type, payload, prev_hash, hash}` and `hash = sha256(prev_hash + canonical_json(event_without_hash))` with `canonical_json = json.dumps(..., sort_keys=True, separators=(",", ":"))` and the first event's `prev_hash = "0"*64`; because every event commits to its predecessor's hash, altering any byte breaks the chain from that point and `verify_chain(path)` returns the first offending `seq`. The `ts` is INJECTABLE — the pure append/hash path never reads the clock, so tests are reproducible. A `make_spawn_payload(...)` helper builds the per-spawn execution-context payload (`role`, `harness`, `provider`, `model`, `skill_pins[]`, `memory_injected[]`, `input_hash`, `verdict_ref`, `run_mode`, `tokens`, `cost` — gap G3). `audit_report.py` reads a ledger and renders a deterministic Markdown timeline (header with the chain-integrity verdict, a `seq/ts/type/summary` table, and a per-spawn execution-context section), closing gap G4; it re-verifies the chain so a tampered ledger is reported as BROKEN rather than rendered as if intact. CLI: `python audit_log.py verify <loop_id.jsonl>` (exit 0 if intact, non-zero + offending seq otherwise) and `python audit_report.py <loop_id.jsonl> [-o out.md]`. These are engine-kit *implementations*; the **normative source stays in `modules/m-audit.md` + `schemas/audit-event.schema.json`** (the first-class Audit contract specified by plan §4.5; not yet authored as of this build) and the §4.5 design. If the spec and these files ever disagree, the spec wins.

## Run

```
# stdlib only — no requirements.txt / no install needed
python3 audit_log.py verify <some-loop>.jsonl
python3 audit_report.py <some-loop>.jsonl
python3 -m unittest discover -s tests -v
```
