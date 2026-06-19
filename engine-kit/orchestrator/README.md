# engine-kit/orchestrator — standalone Delivery-Loop driver (P2 MVP)

**Normative source: `process/delivery-loop.md` §4.2.** This directory is a
reference *implementation* of that spec (per `docs/adr/ADR-0001-engine-substrate.md`).
It is adopter-copyable and **non-normative**: if this code ever disagrees with
the spec, the spec wins and this code is the bug.

## What it is

The deterministic **outer loop** of the Delivery Loop, as a framework-owned
standalone Python state machine (ADR-0001 #1) — explicitly NOT built on any one
coding-agent harness's orchestration. It drives non-deterministic LLM work that
runs inside per-harness **adapters** (`engine-kit/adapters/`), communicating only
via schema-valid JSON verdicts (ADR-0001 #3).

The driver owns the deterministic kernel and **contains no LLM**:

- the state machine `idle → dev_pending → gate_pending → review_pending →
  close_pending → advance` (§4.2.4; **P2 MVP = no Acceptance state — that is P3**);
- per-role adapter selection from a plain-YAML charter's
  `tooling.<role>.{harness,provider,model}` (plan §5 field shapes);
- JSON-schema verdict validation against the existing
  `schemas/review-verdict.schema.json` + `schemas/deliver-close-verdict.schema.json`
  (§4.2.7) — **an invalid verdict is a `gate_hard_fail`, never a permissive default**;
- the checkpoint inbox (`docs/checkpoints/<ts>__<id>__<scope>.md`, §4.2.3 shape);
- the fix-round counter bounded by `budget.max_fix_rounds_total` (§4.4);
- a budget guard;
- resume from `.orchestrator/state.json` (§4.5);
- Audit Spine event emission threading one `loop_id` (reuses
  `engine-kit/audit/audit_log.py`);
- **per-spawn prompt + output transcripts** (§4.2.10): every spawn (Dev, Code
  Reviewer, Deliver/close, Research, Acceptance, each fix-round) writes the exact
  dispatched prompt (always) and the captured model output (whenever the adapter
  returns one — an adapter transport error records `output_ref: null`) to
  `.orchestrator/audit/transcripts/<loop_id>/`, referenced from the spawn event as
  `prompt_ref` / `output_ref` so the run is auditable file-by-file, not just by hash.

## Files

| File | Role |
|---|---|
| `driver.py` | the deterministic state machine (no LLM) |
| `demo.py` | end-to-end demo on `examples/minimal-greenfield` context, mock adapter, artifacts under `/tmp` |
| `examples/p2-charter.yaml` | self-contained demo charter (plan §5 field shapes; read leniently, NOT schema-validated) |
| `tests/` | stdlib-unittest, deterministic, **offline** (mock adapter only) |

## Run

```bash
python3 -m venv /tmp/aidazi-p2-venv
/tmp/aidazi-p2-venv/bin/pip install jsonschema pyyaml

# tests
/tmp/aidazi-p2-venv/bin/python -m unittest discover -s engine-kit/orchestrator/tests -v

# demo (writes artifacts to a fresh /tmp dir)
/tmp/aidazi-p2-venv/bin/python engine-kit/orchestrator/demo.py
```

## Adapter boundary

`spawn(role, prompt, tools, schema) -> dict` (a schema-valid verdict). Reference
adapters live in `engine-kit/adapters/`:

- `mock.py` — deterministic replay (the only adapter run in tests + the demo);
- `claude_code.py` — Claude Code headless (`claude -p …`), **real subprocess gated
  off** by default and never run in tests;
- `headless.py` — OpenAI-compatible HTTP (DeepSeek / Kimi / GPT), **real HTTP gated
  off** by default and never run in tests.

The driver consumes only schema-valid JSON verdicts — never raw model text. This
verdict-only contract keeps the deterministic floor identical across models; the
bar is never lowered for a weaker model (ADR-0001 #3 / §4.2.7).

## Not yet implemented here (later phases)

- Acceptance state + §3.6 calibration gate + F5 evidence (**P3**).
- The deterministic `scope_envelope_check` over an observed diff (§4.2.5) — in P2
  only Deliver's own `in_scope: false` claim fires `scope_deviation`.
- Auto-fix iteration (`spawn_deliver_plan_fix` re-entry, §4.4) — in P2 a
  `fix_required` review routes to a human checkpoint.
- Loop Ingress git strategies, intent-contract capture, idempotency cache (P2+).
- `codex` adapter (P4).
