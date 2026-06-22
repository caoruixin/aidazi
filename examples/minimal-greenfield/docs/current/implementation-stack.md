---
title: Acme Returns Bot — implementation-stack snapshot
adopter_name: acme-returns-bot
doc_tier: adopter-state
doc_category: live
status: current
source_of_truth: this file
last_verified: 2026-06-12
overall_status: partial
review_cadence: per milestone close
load_discipline: by-role
---

# Implementation-stack snapshot — Acme Returns Bot

Present-tense record of the product's own implementation facts as of `last_verified`.
NOT architecture selection — forward technical decisions live in
`docs/foundational/technical-plan.md` (Phase 3). See DEFERRED rows for what is still open.
This is the *adopter implementation stack*, distinct from the *agent execution stack*
(`charter.yaml` `tooling.<role>`) and from the three domain contracts.

| Item | Current fact / value | Status | Provenance / evidence | Notes (DEFERRED → Phase 3) |
|---|---|---|---|---|
| Language(s) | Python 3 (exact minor not pinned in repo) | CONFIRMED | `record_run.py`, `tests/test_recorded_run.py` | → Phase 3: pin the exact Python version |
| Framework(s) | none — agent core invoked via the eval/record harness; no HTTP service at M1 | N/A | no web-framework dependency in the repo | a delivery surface (CLI/HTTP) may be chosen later |
| Build / package manager | not pinned — no manifest/lockfile committed in this snapshot | DEFERRED | (absent: no `pyproject.toml` / `requirements.txt`) | → Phase 3: pin a manager + lockfile |
| Test stack | pytest | CONFIRMED | `tests/test_recorded_run.py` | — |
| Data dependencies | no external datastore wired; orders/policy exercised via test logic at M1 | DEFERRED | `tests/test_recorded_run.py` (names only) | → Phase 3: choose the real orders/policy datastore |
| Deploy / runtime env | none — human-paste, run locally; no deploy target at M1 | DEFERRED | (human-paste adoption; no `Dockerfile` / deploy config) | → Phase 3: deploy/runtime target undecided |

## Open items deferred to Phase 3

- Build / package manager: pin a manager + lockfile → `docs/foundational/technical-plan.md`
- Data dependencies: choose the real orders/policy datastore (M1 has no external datastore) → `docs/foundational/technical-plan.md`
- Deploy / runtime env: pick a deploy + runtime target → `docs/foundational/technical-plan.md`

---

End of implementation-stack snapshot.
