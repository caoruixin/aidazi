# OW-M3 implementation — code-level Codex gate log

- **Date:** 2026-07-01
- **Branch:** `feat/ow-m3-mandatory-e2e` (off `main` `1e6946d`, which contains the landed Track-2 hardening).
- **Reviewer:** Codex `gpt-5.5`, `model_reasoning_effort=xhigh` (R1–R3) / `high` (R4 focused re-run), read-only sandbox, via `codex exec`.
- **Outcome:** **APPROVE (R4)** after R1→R3 REVISE. B1/B2 (the real bypass holes) were resolved by R2 and confirmed each round; R2/R3 iterated only on B3 (ledger-file absent-vs-present-broken strictness).

## R1 — commit `57d1b58` → REVISE
Three BLOCKING (all real bypasses):
1. **Duplicate ledger ids** — gate's `{id: req}` map is last-wins but `_ledger_surface` was first-wins → a duplicated REQ (`user_facing` then `non_user_facing`) signs a static milestone while the envelope records `user_facing`.
2. **Out-of-enum truthy `surface`** (e.g. `"banana"`) treated as non-user-facing; `--sign-plan` loaded raw JSON without schema validation.
3. **Wired-but-unreadable ledger** collapsed to `None` (dormant) → `--sign-plan` stamps around the mandate.
Nits: drift hint omits `covered_req_surfaces`; `signed_scope_hash` schema description stale; "production mirror" test comments overclaim the sign gate.
→ Fixed in `88d3acc`: `duplicate_requirement_ids()` + gate/construction/strict-loader fail-closed; `_ledger_surface` last-wins; gate trusts only `{user_facing, non_user_facing}`; `load_requirement_ledger_strict` (present+invalid ⇒ refuse); all nits.

## R2 — commit `88d3acc` → REVISE
B1/B2 **confirmed resolved.** B3 residue: `os.path.isfile()` returns False for a present-but-non-regular path (directory / broken symlink) → collapses to "absent" → dormant.
→ Fixed in `1791ff4`: `os.path.lexists` (not `isfile`) + broadened except.

## R3 — commit `1791ff4` → REVISE
B1/B2 **still resolved.** B3 residue: `os.path.lexists`/`isfile` themselves swallow `OSError`, so permission/stat failures still collapse to "absent"; a FIFO would block `open()`. Prescribed fix: explicit `os.lstat` (only `FileNotFoundError` ⇒ absent) + require a regular-file target before `open()`.
→ Fixed in `b248d55`: one shared `campaign.load_and_validate_ledger()` implementing exactly that; Campaign construction + run_loop sign/preflight both delegate.

## R4 — commit `b248d55` → APPROVE
No blocking findings. Confirmed: only `FileNotFoundError` ⇒ dormant (`None`), all other present-but-broken conditions raise; `os.lstat`→resolve-symlink→`S_ISREG` before `open()` (FIFO/socket/device/directory cannot block/read); symlink-to-regular-file accepted, broken symlink raises; one shared probe across construction + sign + preflight; additivity intact; B1/B2 remain closed.

## Verification (each round, outside the read-only review sandbox)
Full suite `1471 passed / 3 skipped`; kernel-equivalence constitution `70/70` + authoring `41/41` + base OK; acceptance load-closure `closed: true`; WP-9 context-budget guard `31 passed`.
