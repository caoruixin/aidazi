# OW-AUTO implementation — Codex code-level gate R1

- **Date:** 2026-07-01
- **Gate:** Codex GPT-5.5 (aicodewith) reasoning_effort=xhigh, sandbox=read-only, over `git diff origin/main...HEAD` (base `b2e794b`; impl commits `d667e79` Phase 1 + `9b464b4` Phase 2 + `bd51623` Phase 3).
- **Verdict:** **REVISE** (1 BLOCKING, 1 NON-BLOCKING). One transient `Reconnecting…` mid-run; codex recovered and completed (exit 0).

## Findings (verbatim)

**BLOCKING:** The mandated advisory-flip regression does not actually prove `gap_report` byte
identity. The design requires flipping only `surface_status` / `surface_confidence` to leave
`signed_scope_hash`, `signoff_status`, `acceptance_input_hash`, and the advisory `gap_report`
byte-identical. The new test claims that proof in `test_ow_auto_proposal.py`, but the referenced
test only rewrites a projected `requirement-context.json`, builds the resolver graph, and returns
`acceptance_input_hash`; it never emits, reads, or compares the generated gap report for the two
advisory states (`test_gap_report.py:294`). Existing gap-report tests cover emission and binding,
but not this advisory-flip invariant.

**NON-BLOCKING:** The implementation path itself appears to honor the locked semantics:
`_covered_req_surfaces` / `_signed_scope_H` are value-only, the sidecar writer calls
`requirement_context_ledger_projection()`, `agent_seeded_disposition_allowed()` is
test/documentation-only, and I found no new checkpoint type or advisory-field runtime gate. I did
not run tests, per the read-only gate instructions.

**VERDICT: REVISE**

## Resolution (folded into the next revision commit)

Added `test_gap_report.py::TestAdvisoryFlipInputHash::test_advisory_flip_leaves_emitted_gap_report_byte_identical`
— it runs a FULL acceptance over the PROJECTED sidecar for BOTH advisory states, reads the
Driver-emitted `.orchestrator/acceptance/<scope>-gap-report.json`, and asserts the two files are
BYTE-IDENTICAL. Non-vacuity is asserted (`signoff_status == "signed"`, `gap == ["REQ-3"]` — a real
populated report, not two empty reports). The Driver emits pure
`build_gap_report(compute_requirement_coverage(...))` with `sort_keys=True` and no timestamp/run-id,
so the emitted bytes are stable across runs given identical inputs. `_adv_ledger` was made
advisory-only so `projected(_adv_ledger()) == _ledger()` (the `_signed_plan()` signing basis), giving
a clean "signed" gap_report. The NON-BLOCKING note confirmed the impl path; no code change needed there.
