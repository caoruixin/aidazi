---
title: Implementation-stack snapshot — template
doc_tier: template
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-22
review_cadence: per milestone close
load_discipline: by-role
size_target: 4KB
notes: >
  Template for <adopter>/docs/current/implementation-stack.md. A present-tense
  snapshot of the adopter's OWN product implementation stack (language /
  framework / build / test / data deps / deploy-runtime) as captured at
  onboarding Step 4a. It is NOT architecture selection and NOT a domain contract:
  forward-looking technical decisions live in the Phase-3 technical plan
  (docs/foundational/technical-plan.md, greenfield STEP 5), which is the canonical
  home for them. Distinct from the AGENT EXECUTION STACK (harness × provider ×
  model per role) captured in charter.yaml tooling.<role> (Step 5 Facet A) — the
  two are never merged. load_discipline: by-role (Dev + Deliver on demand); NOT
  added to the always-load governance chain. Records names only — never a secret,
  credential, or env-var value.
---

# Implementation-stack snapshot — instance template

Copy this template to `<adopter>/docs/current/implementation-stack.md` and replace `<placeholders>`. The onboarding wizard (`aidazi/ONBOARDING.md` Step 4a) automates this; this template is the shape it writes.

**What this is — and is not.**

- **Is:** a *present-tense snapshot* of what the product is **already** built with or what is **already known** today.
- **Is NOT:** architecture selection. Forward-looking technical decisions belong in `docs/foundational/technical-plan.md` (Phase 3, greenfield STEP 5) — **Phase 3 is the canonical home** for them, and this snapshot never pre-empts it.
- **Is NOT:** the *agent execution stack* (harness × provider × model that runs each role) — that lives in `charter.yaml` `tooling.<role>` (Step 5 Facet A). The two are different concerns and are never merged.
- **Is NOT:** a domain contract. Domain semantics live in `domain_taxonomy.md` / `runtime_invariants.md` / `eval_acceptance_bars.md`.

**Rules.**

- **No silent blank fields.** Every row has a `Status` of `CONFIRMED | DEFERRED | N/A`. An unknown is an explicit `DEFERRED`, never an empty cell.
- **`DEFERRED` rows point to Phase 3.** Put `→ Phase 3` (and, optionally, the open question) in the row's notes.
- **Names only — never values.** For data dependencies and environment variables, record the *name* (e.g. `ORDERS_DB_URL`). **Never** read or record a secret, credential, or env-var value.
- **Evidence-based (brownfield).** Each `CONFIRMED` row cites the file it was detected from. Do **not** over-infer production architecture from a single file.
- **`load_discipline: by-role`.** Dev + Deliver load this on demand; it is **not** in the always-load chain.

---

```markdown
---
title: <adopter-name> — implementation-stack snapshot
adopter_name: <name>
doc_tier: adopter-state
doc_category: live
status: current
source_of_truth: this file
last_verified: <YYYY-MM-DD>
overall_status: confirmed | partial | deferred   # how much of the stack is pinned
review_cadence: per milestone close
load_discipline: by-role
---

# Implementation-stack snapshot — <adopter-name>

Present-tense record of the product's own implementation facts as of `last_verified`.
NOT architecture selection — forward technical decisions live in
`docs/foundational/technical-plan.md` (Phase 3). See DEFERRED rows for what is still open.

| Item | Current fact / value | Status | Provenance / evidence | Notes (DEFERRED → Phase 3) |
|---|---|---|---|---|
| Language(s) | <e.g. Python 3.12> | CONFIRMED | <e.g. pyproject.toml> | — |
| Framework(s) | <e.g. FastAPI / none> | CONFIRMED \| DEFERRED \| N/A | <evidence or "—"> | <"→ Phase 3: web layer not chosen" if DEFERRED, else "—"> |
| Build / package manager | <e.g. uv / pip+requirements.txt> | CONFIRMED \| DEFERRED \| N/A | <lockfile / manifest> | <"→ Phase 3: manager not pinned" if DEFERRED, else "—"> |
| Test stack | <e.g. pytest> | CONFIRMED \| DEFERRED \| N/A | <pytest.ini / tests/> | <"→ Phase 3: test stack not chosen" if DEFERRED, else "—"> |
| Data dependencies | <names only, e.g. ORDERS_DB_URL (Postgres)> | CONFIRMED \| DEFERRED \| N/A | <docker-compose service / env-var name> | <"→ Phase 3: data dependency source not chosen" if DEFERRED, else "names only — never a value"> |
| Deploy / runtime env | <e.g. Docker on Fly.io> | CONFIRMED \| DEFERRED \| N/A | <Dockerfile / fly.toml> | <"→ Phase 3: target undecided" if DEFERRED, else "—"> |

## Open items deferred to Phase 3

(One line per DEFERRED row above — the open question Phase 3's technical plan resolves.)

- <Item>: <what is undecided> → `docs/foundational/technical-plan.md`
```

## Status enum

- `CONFIRMED` — the fact is established today (brownfield: detected + human-confirmed; greenfield: human-supplied).
- `DEFERRED` — not yet decided/known; resolved later in Phase 3. **Must** point to Phase 3.
- `N/A` — this item does not apply to this product (e.g. no web framework for a library).

## `overall_status` enum

- `confirmed` — all applicable items are `CONFIRMED`.
- `partial` — a mix of `CONFIRMED` and `DEFERRED`.
- `deferred` — mostly `DEFERRED` (typical for a fresh greenfield repo).

## Template usage notes

- The `<placeholders>` and illustrative `CONFIRMED | DEFERRED | N/A` alternations should all be resolved to a single concrete value per row in the instance.
- This snapshot is `load_discipline: by-role` — Dev and Deliver load it on demand (see `agent_context_guide.md`). Do **not** add it to the always-load governance chain.
- Revisit at milestone close: promote `DEFERRED → CONFIRMED` as Phase 3 decisions land; update `last_verified` and `overall_status`.

---

End of implementation-stack template.
