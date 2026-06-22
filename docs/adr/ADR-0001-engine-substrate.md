---
title: ADR-0001 — Engine substrate: standalone Python driver + per-harness adapters
doc_tier: design-history
doc_category: design-history
status: accepted
source_of_truth: this file (records a decision; normative spec stays in governance/ + process/)
date: 2026-06-15
branch: v2-loop-engine
supersedes: []
superseded_by: null
notes: >
  First ADR for the v2 loop-engine line. Establishes docs/adr/ as the home for
  P0–P6 substrate decisions. Records the engine-substrate decision from the v2
  build plan (archive/2026-06-15-v2-loop-engine-plan.md §4.2 + §7 P0). This ADR
  documents an already-made decision; it does not re-open it.
---

# ADR-0001 — Engine substrate: standalone Python driver + per-harness adapters

- **Status:** Accepted
- **Date:** 2026-06-15
- **Deciders:** framework maintainer (v2 build plan, OQ-A resolution)
- **Phase:** P0 (build plan §7)

## Context

aidazi is a spec-driven framework, not a runtime (README "What aidazi is NOT").
The v2 build plan compiles that spec into a *running loop engine on the adopter
side* via a copyable `engine-kit/`, without aidazi itself becoming a server
(plan §1 North Star).

Two framework invariants constrain how the loop engine's outer loop may be
realized:

- **Harness- and model-agnostic** (plan §1; §4.1 facet A). Roles bind to any
  `(harness × provider × model)` triple — Claude Code↔Anthropic, Codex↔OpenAI,
  and a `headless` OpenAI-compatible endpoint that unlocks DeepSeek / Kimi / GPT.
  The engine cannot be welded to any single harness's orchestration.
- **Runtime owns the kernel** (Constitution §1.4). The deterministic kernel —
  tool/permission boundary, budget/timeout, idempotency, persistence, trace and
  eval contract — is runtime-owned, not delegated. Per role-boundary discipline
  (§3.4 invariant #6) role behavior must hold "regardless of backing agent."

The delivery-loop spec already defines the outer loop precisely: a deterministic
state machine driving non-deterministic LLM work, communicating only via JSON
verdicts, filesystem state, and checkpoint files (delivery-loop §4.1). §4.2.7
mandates schema-validated verdict parsing — an invalid verdict is a
`gate_hard_fail`, never a permissive default.

The open sub-decision (build plan §8, OQ-A) was the *substrate*: build the outer
loop on a coding-agent harness's orchestration tool (concretely, Claude Code's
Workflow tool), or as framework-owned standalone code. This ADR records the
resolution.

## Decision

1. **The deterministic OUTER LOOP is a framework-provided STANDALONE driver,
   written in Python.** It is NOT built on any one coding-agent harness's
   orchestration — explicitly NOT Claude Code's Workflow tool. Rationale: the
   framework must stay harness- and model-agnostic, and per Constitution §1.4 the
   runtime kernel is framework-owned, not a vendor tool.

2. **The driver owns the deterministic kernel.** State machine, `scope_envelope_check`
   (§4.2.5), JSON-schema verdict validation (§4.2.7), the checkpoint inbox
   (§4.2.3), fix-round counting (§4.4), budget enforcement, and resume /
   idempotency (§4.5). **`git worktree` isolation and scheduling are also
   framework-owned** — implemented at the git level and via OS cron / CI, NOT as
   harness features (plan §4.2 ownership table).

3. **Per-role SESSION EXECUTION is delegated to the adopter's chosen coding agent
   behind a uniform ADAPTER INTERFACE.** File edits, tool-use, and the inner
   agentic loop run inside whichever harness backs the role. The interface is:

   ```
   spawn(role, prompt, tools, schema) -> schema-valid verdict
   ```

   Reference adapters: `claude_code`, `codex`, and `headless` (an
   OpenAI-compatible endpoint — the adapter that unlocks DeepSeek / Kimi / GPT,
   per §4.1 facet A). **The driver only ever consumes schema-valid JSON verdicts,
   never raw model text.** This verdict-only contract is precisely what makes the
   engine model-agnostic: the bar is never lowered for a weaker model; an invalid
   verdict is a `gate_hard_fail` (§4.2.7).

4. **Claude Code's Workflow tool MAY be offered later as an OPTIONAL acceleration
   backend** for all-Claude-Code adopters. It is never the reference
   implementation (plan §4.2: "Workflow, if any, is at most an optional backend").

5. **Driver language = Python.** The driver shells out frequently to heterogeneous
   CLIs and makes HTTP calls to OpenAI-compatible APIs; the already-referenced
   `stanza_validator.py` and `trace_emitter.py` are Python. This resolves OQ-A.

6. **Lives in the adopter-copyable `engine-kit/`** (reference implementation;
   non-normative). The normative source of truth stays in `governance/` +
   `process/` — conflict rule: spec wins, the kit is then a bug (plan §1).
   aidazi-core stays spec-only.

## Consequences

**Positive**
- The engine binds to any `(harness × provider × model)`; the verdict-only
  contract keeps the deterministic floor identical across models.
- The runtime kernel is framework-owned per §1.4, not borrowed from a vendor
  tool whose semantics we don't control.
- The driver is portable: a single Python process plus shell-out, no Claude Code
  (or any harness) installation required to run the outer loop.
- The same adapter interface that delivers harness-agnosticism is the unit that
  delivers multi-model — one mechanism, two payoffs.

**Tradeoff (honest)**
- We forgo a harness's *free plumbing* — concurrency, schema-validated structured
  output, worktree management, budget, resume, and a progress UI — and must
  reimplement the slice we actually need. This slice is **small**, because
  delivery-loop §4.2 already specifies it (state machine, scope envelope, verdict
  schemas, checkpoint inbox, fix-round bounds, idempotency/resume). The
  reimplementation is transcription of an existing spec, not new design.
- The genuinely new work is the **per-harness adapters** — but those are required
  for multi-model support regardless of substrate, so this is not incremental
  cost attributable to the standalone choice.
- First executable code lands in an all-Markdown repo: the kit needs a minimal
  runtime + tests + CI, and the hard-kernel scripts MUST stay deterministic / no
  LLM (Constitution §1.4; plan §8 risk). Scope-creep guard: aidazi-core stays
  spec-only; all executables live in `engine-kit/`.

## Alternatives considered

| Option | Verdict | Why |
|---|---|---|
| (a) **Workflow-first reference** — build the outer loop on Claude Code's Workflow tool | **REJECTED** | Claude-Code-locked; breaks harness-agnosticism (plan §1; §4.1 facet A) and violates §1.4 "runtime owns the kernel" by delegating the kernel to a vendor tool. May return later only as an *optional* backend (decision #4). |
| (b) **Separate installable engine package** (e.g., pip-installable `aidazi-engine`) | **DEFERRED** | Distribution choice orthogonal to substrate; can sit atop the same driver later without re-deciding substrate. Revisit post-P2. |
| (c) **Standalone Python driver + adapters** | **CHOSEN** | Framework-owned deterministic kernel; harness-agnostic via the `spawn(...)`→verdict adapter boundary; model-agnostic via verdict-only consumption; Python fits the shell-out + HTTP + existing-scripts reality. |

## Cross-references

- `archive/2026-06-15-v2-loop-engine-plan.md` — §1 (North Star), §4.1 facet A
  (execution binding), §4.2 (standalone driver + ownership table), §7 P0, §8
  OQ-A (resolved: Python).
- `process/delivery-loop.md` — §4.1 (deterministic outer loop / inner work
  split), §4.2.3 (MANDATORY_CHECKPOINTS / inbox), §4.2.5 (`scope_envelope_check`),
  §4.2.7 (spawn functions + schema-valid verdicts), §4.4 (fix-round bounds),
  §4.5 (idempotency / resume). NOTE: §4.1 still uses substrate-neutral but
  Workflow-agnostic language; the build plan §4.2 CORE item to make the
  "deterministic outer loop" wording explicitly substrate-neutral is owned by a
  later phase, not this ADR.
- `governance/constitution.md` — §1.4 (Runtime owns the kernel), §3.4 invariant
  #6 (role behavior regardless of backing agent; transitive whitelist).
- `README.md` — "What aidazi is NOT — not a runtime; not a single tool."
- Future: ADR-0002+ for subsequent P0–P6 substrate decisions land in this
  directory.

---

End of ADR-0001.
