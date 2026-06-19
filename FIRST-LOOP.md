---
title: First-Loop Launcher — agent-driven, start the first Delivery Loop after onboarding
doc_tier: application-guide
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
created: 2026-06-17
last_reviewed: 2026-06-17
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 8KB
notes: >
  The post-onboarding hand-off. ONBOARDING.md (the Onboarding Wizard) ends at its
  Step 9; THIS file is what the human feeds their coding agent — IN THE ADOPTER
  REPO — to actually start the first Delivery Loop via the standalone runner
  (engine-kit/scheduling/run_loop.py). Naming discipline (Constitution §1.7-E):
  this launcher is NOT a loop and NOT the wizard; it hands off to Loop Ingress +
  the Loop Controller, which ARE the loop. Harness-agnostic: read, write, shell only.
---

# First-Loop Launcher — feed me to your coding agent (in the adopter repo)

**You are reading the aidazi First-Loop Launcher.** The Onboarding Wizard
(`ONBOARDING.md`) is the one-time install; it is **done**. This file is the
**hand-off**: open a **fresh coding-agent session whose working directory is the
adopter repo root** (the project the wizard set up — *not* the framework repo), and
feed it this file. It drives the **first Delivery Loop** for you.

> **Switch workspace first.** The wizard often runs from the framework repo; the
> loop runs from the **adopter repo** (where `charter.yaml`, `AGENTS.md`,
> `engine-kit/`, `.venv/`, `.orchestrator/audit/` live). All commands below assume
> that cwd.

> **Naming discipline (§1.7-E).** This launcher is **not** a loop and **not** the
> wizard. The moment it invokes the runner, **Loop Ingress** (per-loop git
> isolation + intent-contract re-confirm) and the **Loop Controller**
> (loop-until-condition) take over. See `docs/two-loops-explainer.md`.

## Prerequisites (the wizard guarantees these)

- `charter.yaml` exists and **validates GREEN** (`Step 8`).
- A signed research brief with a confirmed intent contract
  (`docs/research-briefs/<id>.md`, `confirmed_by_human: true`).
- The adopter-owned `engine-kit/` + `schemas/` + a Python env with the validator/
  runner deps (`PyYAML`, `jsonschema`) — the wizard sets these up (e.g. `.venv/`).

---

## The copy-paste prompt

Paste this into the fresh session (cwd = adopter repo root). It is **general** —
it self-discovers the charter and picks the right loop mode.

```text
You are the coding agent starting the FIRST DELIVERY LOOP for an aidazi-adopted
project. The Onboarding Wizard is already complete and the charter validates GREEN.
Working directory is THIS repo's root (the adopter repo). Do everything from here.

1. COLD-START. Read AGENTS.md first (it @-includes the governance chain), then
   docs/current/adoption-state.md, docs/current/runtime_invariants.md, and the
   signed brief in docs/research-briefs/. Re-confirm the intent contract with me
   before running anything.

2. SANITY. Re-validate the charter (use the project's Python env that has the deps):
   .venv/bin/python engine-kit/validators/charter_validator.py charter.yaml
   It must exit 0.

3. PICK THE MODE.
   - If the milestone is NOT yet decomposed (no sub-sprint sequence / compact dev
     prompt): use  --loop-mode full_chain_guided  (adds research -> gate1 ->
     decompose before the delivery loop).
   - Once decomposed: use  --loop-mode delivery_only.

4. PROVE IT OFFLINE FIRST (mock adapters; zero model calls; temp artifacts):
   .venv/bin/python engine-kit/scheduling/run_loop.py --charter charter.yaml --loop-mode <mode>
   Show me the state trace + audit-chain result.

5. RUN THE REAL FIRST LOOP (live models). Before this, confirm with me that the
   bootstrap is committed to git (Loop Ingress isolates per the charter's
   `isolation` strategy). Then:
   AIDAZI_ALLOW_REAL_ADAPTER=1 .venv/bin/python engine-kit/scheduling/run_loop.py \
     --charter charter.yaml --loop-mode <mode> --repo-dir . --allow-real

DISCIPLINE (non-negotiable):
- Honor the charter's autonomy level. STOP at every MANDATORY_CHECKPOINT and gate —
  especially the gate-1 Customer sign-off, which is NEVER auto-confirmed — and WAIT
  for my decision. Present ONE recommendation + one-line rationale at each.
- Respect the budget caps and approved_scope; surface any scope deviation.
- NEVER push to git; I control push.
Once you invoke the runner, Loop Ingress + the Loop Controller own the iteration
(this launcher is not itself a loop; §1.7-E).
```

---

## What the runner is (so the agent uses the right thing)

`engine-kit/scheduling/run_loop.py` is the framework-owned, **harness-agnostic**
one-command entry point (plain cron/CI-friendly — *not* a harness scheduler). It:
loads the charter → builds one adapter per role from `tooling.<role>` → constructs
the standalone `Driver` (`engine-kit/orchestrator/driver.py`) → runs → verifies the
Audit-Spine hash chain.

| Flag | Meaning |
|---|---|
| `--charter charter.yaml` | the validated charter (required) |
| `--loop-mode delivery_only \| full_chain_guided` | `delivery_only` is default; `full_chain_guided` adds research→gate1→decompose |
| `--subsprint-id sprint-001` | which sub-sprint to drive |
| `--repo-dir .` | enables **Loop Ingress** git isolation (per `charter.isolation`) |
| `--allow-real` (+ env `AIDAZI_ALLOW_REAL_ADAPTER=1`) | build + run the **real** adapters; without it, **mock** (safe dry-run) |

Real adapters are **gated off by default** — an offline mock run is always safe and
writes artifacts to a fresh temp dir, never your repo.

## When NOT to use the runner

**Pure human-paste adopters** skip the runner entirely and walk the 5-role chain by
hand (paste role cards / compact prompts; greenfield guide STEP 6). That is a
complete, valid adoption. The prompt above still applies for the cold-start +
intent-contract re-confirm; only steps 4–5 change to manual role hand-offs.

## After the first loop

- **Subsequent loops** drop to `--loop-mode delivery_only` (the milestone is now
  decomposed).
- **Unattended runs** (overnight Auto Loop / scheduled Delivery Loop) wrap the same
  `run_loop.py` in plain **cron/CI** — never a harness scheduler (`engine-kit/scheduling/README.md`).
- For the *substance* of the milestone, follow the per-track guide
  (`docs/greenfield-guide.md` STEP 5–6 or `docs/brownfield-guide.md` §5).

---

End of First-Loop Launcher.
