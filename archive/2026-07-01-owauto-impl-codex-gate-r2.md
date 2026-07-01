# OW-AUTO implementation — Codex code-level gate R2

- **Date:** 2026-07-01
- **Gate:** Codex GPT-5.5 (aicodewith) reasoning_effort=xhigh, sandbox=read-only, over `git diff origin/main...HEAD` after folding R1 (adds commit `ddce6c9`).
- **Verdict:** **REVISE** (1 BLOCKING). R1 BLOCKING confirmed RESOLVED.

## R1 fix check (codex, verbatim)

> The prior blocking gap-report test issue is resolved. `test_gap_report.py:349` now runs full
> Acceptance for both advisory states, reads the Driver-emitted gap report, compares the emitted
> content, and asserts non-vacuity with `signoff_status == "signed"` and `gap == ["REQ-3"]`. The
> implementation path also projects advisory fields out before sidecar write, and the narrowed
> search found no runtime verdict/hash consumer of `surface_status` or `surface_confidence`.

## Findings (verbatim)

**BLOCKING —** `role-cards/research-agent.md:131` incorrectly groups `surface` with
`surface_status` / `surface_confidence` as "ADVISORY" and says it is "never bound into a signed
hash and never gated on." That violates the locked semantics: only `surface_status` and
`surface_confidence` are advisory; the `surface` value binds through `covered_req_surfaces` and
drives OW-M3 sign/preflight behavior. The runtime code is correct, but this role-card is normative
authoring guidance and should say that `surface` is proposed until `campaign_plan_signoff`, then
the value binds via `covered_req_surfaces`; only the two advisory fields stay unbound.

**VERDICT: REVISE**

## Resolution (folded into the next revision commit)

Rewrote the `role-cards/research-agent.md` §3.3 summary paragraph: `surface` is a **proposal**
until sign-off, but its VALUE is NOT advisory — once the Customer signs the covering plan
(`campaign_plan_signoff`) the value binds into the signed hash via `covered_req_surfaces` and
drives the OW-M3 sign/preflight gate (a `user_facing` REQ forces browser-E2E); reclassifying a
signed surface ⇒ re-sign (Customer authority). ONLY `surface_status` / `surface_confidence` are
ADVISORY (never bound into any hash, never gated on, a flip changes no verdict/hash/freshness).
Refreshed the research-agent.md source hash in `_sources.yaml` (additive prose correction; no
inventoried constraint changed). Kernel 70/70 + 41/41 green; full suite 1511 passed.
Locked-semantics conflation scan of the other touched docs (deliver-agent, FIRST-LOOP,
requirement-ledger §2.2, ONBOARDING) found no other instance.
