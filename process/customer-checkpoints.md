---
title: Customer checkpoints — human-side gate catalog
doc_tier: process
doc_category: live
status: current
implementation_status: implemented
source_of_truth: this file
last_reviewed: 2026-06-11
review_cadence: every fold-back sub-sprint
supersedes: []
superseded_by: null
load_discipline: on-demand
size_target: 12KB
split_trigger: if gate catalog grows past 12 gates, split detail into a separate per-gate doc
notes: >
  Customer is the HUMAN in the 5-role chain — NOT an agent. This file is a
  process catalog (not a role card / not an agent activation prompt) of
  points where the Customer's authority is exercised: what they read, what
  they write, what blocks downstream until they act. Lives in process/
  because it specifies a process pattern (when human gates fire); the 5
  agent role cards live in role-cards/. Load this when adopting Customer
  responsibilities, delegating Customer responsibilities to a designated
  human, OR authoring a charter that defines the gate cadence.
---

# Customer checkpoints

The Customer is the **human** in the 5-role chain (Constitution §3). The framework does NOT make the Customer an agent — there is no LLM-backed "Customer Agent." The Customer is a human who reads framework artifacts and writes decisions at specific gates.

This is a process-tier catalog (not a role card — Customer doesn't start an LLM session). It documents when Customer authority fires, what they read, what they write, what blocks until they act.

For solo adopters (one human owner playing all roles), the same person walks both Customer and other roles — but Customer-role actions must happen in a context where the human is explicitly acting as Customer (NOT as Deliver, NOT as Acceptance). The gates below are the points where the human pauses other roles and acts as Customer.

## §1 The two principal gates

These are the "load-bearing" Customer gates. The Acceptance fix_required → human-confirm flow (Constitution §3.5) joins them as a third critical event.

### §1.1 Gate 1 — Research brief sign-off

**Trigger**: Research Agent produces `docs/research-briefs/<id>.md` with a closure_contract.

**Customer reads**:
- The full research brief.
- Specifically: the closure_contract paragraph (positive shape + anti-pattern + anchor phrases per Constitution §1.7-B).
- Scope IN / scope OUT / anti-goal.
- KPI definitions.
- Related R-items in `docs/action_bank.md`.

**Customer writes**:
- `customer_signed: true` in the brief's front-matter.
- `sign_off_date: <YYYY-MM-DD>` in the brief's front-matter.
- (Optional) a short sign-off note at the bottom of the brief naming any reservations.

**Until written, blocks**:
- Deliver Agent cannot use this brief as a Path 1 input.
- Orchestrator cannot dispatch a milestone scoped to this brief.

**What Customer is judging**:
- Is the closure_contract the right thing? (NOT "is the team capable" — that's a Deliver question.)
- Is scope IN tight enough to be deliverable and broad enough to be valuable?
- Is anti-goal honest about what we're NOT trying to do?

**Customer does NOT judge**:
- How the team will build it (Deliver's job).
- Whether the team CAN build it (Deliver + Dev's job).
- Whether the code design is correct (Code Reviewer's job).

### §1.2 Gate 2 — Acceptance verdict + ship/no-ship

**Trigger**: Acceptance Agent writes `docs/acceptance-reports/<scope>-acceptance-report.md` at milestone close OR release cut.

**Customer reads**:
- The acceptance report (JSON verdict body + per-clause cases + failure briefs if any).
- Cross-reference: the closure_contract this milestone was scoped against.
- (Optional) Code Reviewer's latest `docs/codex-findings.md` for code-side context.

**Customer writes**:
- If `milestone_verdict: pass` → ship sign-off (entry in milestone close notes OR release tag annotation).
- If `milestone_verdict: fix_required` → see §1.3 (gate 3).
- If `milestone_verdict: needs_human` → see §1.3 (Customer adjudicates; orchestrator emits `surface_approve` checkpoint).

**Until written, blocks**:
- The milestone cannot be closed.
- The release cannot ship.
- If orchestrator-driven, orchestrator halts at the post-Acceptance state.

**What Customer is judging**:
- Does delivered behavior satisfy the closure_contract I signed at gate 1?
- Acceptable residual risk?

### §1.3 Gate 3 — Acceptance fix_required human-confirm

**Trigger**: Acceptance verdict = `fix_required`; Acceptance Agent has written `docs/checkpoints/<timestamp>__acceptance_fix_required__<scope>.md` with `decision: pending`.

**Customer reads**:
- The acceptance report (full).
- The checkpoint file's `# Context` and `# Options` sections.
- The gap brief inside the acceptance report.

**Customer writes** in the checkpoint file's `# Decision` block (one of):
```yaml
confirm: yes
route: deliver_fix_iteration
notes: <optional rationale>
```
```yaml
confirm: yes
route: re_acceptance_after_evidence
notes: <which additional evidence to gather>
```
```yaml
confirm: yes
route: research_contract_revision
notes: <which closure_contract clause needs revision>
```
```yaml
confirm: no
notes: <accepting residual risk; ship anyway>
```

**Until written, blocks**:
- Orchestrator halts in `acceptance_pending` state's fix_required branch.
- In manual mode, Deliver Agent cannot pick up the gap brief.

**Why this gate exists** (Constitution §1.7-C + §3.5): same Customer who signed the brief at gate 1 confirms the verdict at gate 2 (or gate 3, here). Acceptance never routes to Deliver silently — Customer keeps loop authority on what to do with a delivery-vs-promise gap.

## §2 MANDATORY_CHECKPOINTS the Customer resolves (Δ-18)

When the Δ-18 orchestrator is adopted, additional MANDATORY_CHECKPOINTS (per `process/delivery-loop.md` §4.2.3) fire that the Customer resolves via the filesystem inbox. The 9 default checkpoints + what the Customer reads + writes at each:

| Checkpoint | When fires | Customer reads | Customer writes (`decision:` field) |
|---|---|---|---|
| `mission_start` | Orchestrator boots | Charter YAML | `approved` OR `rejected` (with reason) |
| `research_proposal_selection` | Path 1; multiple candidate proposals | Candidate briefs (some `customer_signed: false`) | Chosen brief id (sign that brief at gate 1 separately) |
| `bad_case_manual_review` | Milestone close (before Acceptance) | Per-turn bad-case traces; `process/badcase-lifecycle.md` triage | `approved_for_milestone_close` OR `block` (with R-item id naming what blocks) |
| `new_tier0_candidate` | Code Reviewer / Deliver proposes new Tier-0 invariant | Proposal text; existing `docs/current/runtime_invariants.md` | `approved` (add to Tier-0 list) OR `rejected` (keep proposal-tier OR escalate to `human_review_required`) |
| `forbidden_list_redline` | Change touches Constitution §1.7 forbidden-list semantics | Proposed change + Constitution §1.7 + §8 editing discipline | `approved` (routes to fold-back review) OR `rejected` (revert change) |
| `scope_deviation` | `scope_envelope_check` fails | Deviation diff + observed_diff path set + `approved_scope` declaration | `accept_deviation` (widen scope) OR `reject_deviation` (Deliver plans narrower fix) OR `abandon` (halt milestone) |
| `close_taxonomy_C_or_D` | Deliver close verdict = C or D | Deliver's close conversation per `templates/deliver-close-taxonomy.md` | The chosen C-subclass / D-subclass resolution |
| `gate_hard_fail` | Deterministic gate fails AND auto_fix_iteration not eligible | Failed gate output + handoff §1 narrative | `retry` (with budget bump) OR `escalate` (return to plan_fix) OR `abandon` |
| `advisory_acceptance_pass_signoff` | Acceptance returns an advisory pass (not authoritative) | The acceptance verdict + F5 evidence | `confirm: ship` OR `reject` |

The full checkpoint file shape is in `process/delivery-loop.md` §4.2.3.

### §2.1 In human-paste mode (no orchestrator)

When the adopter has not adopted the Δ-18 orchestrator (pure human-paste), these checkpoints still apply but happen via conversation rather than filesystem files. Customer is still the authority; gates are still load-bearing. Framework's behavior boundaries are universal (Constitution §3.1-§3.4); only the automation layer is optional.

## §3 Information-only checkpoints (observability events; non-blocking)

The orchestrator may emit checkpoints whose `decision:` field is `info` rather than `pending`. These are **observability events** — they exist so the Customer (and the audit trail) see what's happening, NOT to gate the flow. Explicitly:

- They are NOT MANDATORY_CHECKPOINTS (Constitution §1.7-D's non-bypass invariant does not apply; they can be emitted, suppressed, or filtered without breaching the framework).
- They do NOT require a Customer `decision:` value. The `decision: info` field is the orchestrator's marker; the human writes nothing.
- They MUST NOT block the orchestrator flow by themselves. The orchestrator continues to its next state immediately after emitting an info checkpoint.
- They MAY, of course, cause the Customer to choose to interrupt (e.g., a `budget_warning_at_80_percent` info checkpoint may motivate the Customer to revise the charter). That interruption is a separate Customer-initiated action, not a blocking checkpoint.

Examples:
- `auto_fix_iteration_round_N_started` — orchestrator has begun fix round N within budget.
- `calibration_degradation` — Acceptance autonomy auto-degraded because calibration uncalibrated (Constitution §3.6). The degradation itself happened automatically; this checkpoint just records it.
- `budget_warning_at_80_percent` — budget approaching limit; informational only.

The Customer reads (for situational awareness) but does NOT resolve. Information-only checkpoints belong to the orchestrator's event log, not its decision graph.

## §4 Customer responsibilities the framework does NOT automate

- **Authoring the initial Customer prompt** that activates the Research Agent at the start of a milestone (free-form; no template).
- **Final ship sign-off** (gate 2) for production releases. The framework can route the verdict but cannot decide "ship vs no-ship" — that's the Customer's call against organizational risk tolerance.
- **Tier-0 invariant decisions** at `new_tier0_candidate` checkpoints (per Constitution §1.5).
- **Stakeholder communication** outside framework artifacts.
- **Domain expertise** that the closure_contract reflects.

## §5 Solo-adopter notes

For single-human adopters playing all roles, every Customer gate is "yourself in a different framing." The framework SHOULD be practiced with explicit session boundaries when practical — when you switch from Deliver/Dev work to Customer work, open a fresh session, so role-specific judgments happen in role-specific framing rather than in whatever frame the chat history happened to have.

A common solo pattern when fresh sessions ARE practical:
- Morning: Customer session (review yesterday's Acceptance reports; sign any pending briefs).
- Day: Research / Deliver / Dev sessions.
- End-of-day or end-of-sprint: Customer session for any pending checkpoints.

When fresh sessions are NOT practical (e.g., the adopter is working in a single long-running session by tooling constraint), the hard requirement remains: **role-boundary discipline + no chat-history backchannel** (Constitution §3.4 invariant #1). Specifically:

- Before each role-switch within the same session, explicitly name the role-switch in writing (e.g., "I am now acting as Customer for gate 2 sign-off"). This is the substitute for a fresh session.
- Read the artifact you're judging fresh — do not rely on chat-history summary of it.
- Record the role-specific output in the durable artifact (front-matter sign-off, `decision:` field, milestone close note). Verbal/chat-only does NOT count; framework's role-boundary discipline depends on durable artifacts, not session boundaries.
- If you find yourself making a Customer-role decision based on what Deliver "just said" in the same chat, halt and re-read the underlying artifact. The chat is not the source of truth.

Fresh sessions are preferred because they make these disciplines harder to violate by accident. Within-session role-switches are permitted when fresh sessions aren't practical, but the disciplines are non-negotiable either way.

## §6 Pre-output checklist

Before resolving any Customer checkpoint:

1. The artifact being judged is at the version it was meant to be at this gate (no mid-flight edits).
2. You're reading as Customer (NOT as Deliver / Dev / Acceptance — fresh framing).
3. For gate 1 — you read the FULL closure_contract, not just the brief's summary.
4. For gate 2 / gate 3 — you read the Acceptance report's `cases` array, not just the top-line verdict.
5. For Δ-18 MANDATORY_CHECKPOINTS — you read the orchestrator's `# Context` section, not just the title.
6. Your decision is recorded in writing (front-matter for briefs, `decision:` field for checkpoints, milestone close notes for ship sign-off). Verbal-only is not recorded; the role chain depends on durable artifacts (Constitution §3.4 invariant #1 — no chat-history backchannel).

---

End of Customer checkpoints catalog.
