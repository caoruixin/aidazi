VERDICT: APPROVE
SUMMARY: Rev2 closes the R1 blocking design holes: the surface basis is now intended to be hash-bound, canary/dormancy is framed as post-ledger adoption, and the waiver path is gone. The B2 limitation is now accurately treated as a Track-2 prerequisite for implementation rather than over-claimed as already solved.

PART A — R1 BLOCKING resolution:
  B1 — RESOLVED — Adding `covered_req_surfaces` to `_envelope_milestone` is the right binding point: both `compute_scope_envelope` and `_signed_scope_H` consume `_envelope_milestone` (`campaign.py:2189-2197`, `2218-2225`), and `stamp_signoff` stores both the envelope and hash (`2251-2259`). Canonical JSON sorts object keys, so a `{rid: surface}` map is ordering-stable; implementation must also pass the live ledger into hash recomputation and update the schema to allow the new envelope field.
  B3 — RESOLVED — The contradiction is gone. Rev2 makes pre-ledger/no-coverage plans dormant, but once `covers_req_ids` is declared every referenced REQ must exist and carry `surface`; this aligns with current F1 activation by field presence, including empty arrays (`campaign.py:2272-2275`).
  B4 — RESOLVED — The waiver escape is removed. The remaining paths are set `browser_e2e` or Customer-authorized reclassify-and-re-sign, which is an authority decision rather than an engine bypass.

PART B — Track-2 dependency framing: ACCURATE — Existing code detects signed-scope drift when freshness is checked, but `_handle_resume` only checks `_signoff_status()` for `campaign_plan_signoff` (`campaign.py:1691-1697`); other resume paths can advance or dispatch without revalidation (`1744-1764`, `1766-1834`), and `_drive_milestones` dispatches without a fresh F1 check (`1938-2002`). Initial run does pause on unsigned/stale/pre-F1 (`1894-1907`), so “hash-detectable but not universally resume-blocked” is the correct claim. Track-2’s stated scope covers OW-M3’s need: uniform F1 freshness before all resume decisions and dispatches, plus signed-input coverage for mutable authority/verdict fields including `gap_followup.max_subsprints`.

NEW BLOCKING (introduced by rev2, must fix):
  <none>

NON-BLOCKING / NITS:
  1. Make the implementation checklist explicit that `campaign-plan.schema.json` must add `covered_req_surfaces` under `signoff.scope_envelope.milestones[]`; current schema uses `additionalProperties:false`.
  2. Clarify the empty-array case in prose/tests: absent `covers_req_ids` is dormant; explicit `covers_req_ids: []` activates F1, and per D2 should refuse a missing ledger if that is the chosen fail-closed rule.
  3. Document migration for any existing signed plans that already use `covers_req_ids` without a surface-bearing ledger; rev2 intentionally makes those re-sign/ledger-required, but adopters need a clear failure message.

PART D — citations: OK