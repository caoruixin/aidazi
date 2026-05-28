# Friction playbook — known issues + remediation patterns

`aidazi` is extracted from a production project that ran 50+ sprints
and 5 milestones. Over that time, several friction patterns emerged
that the framework now bakes in OR explicitly delegates to the
consumer. This file is the catalogue.

Read this BEFORE your first milestone, not after your third.

The frictions below come in two categories:

- **Bundled** (the framework already addresses them as a default).
- **Known but not bundled** (you decide when to adopt the
  remediation; the framework documents the pattern).

## Bundled frictions

### F1. Composite eval scores drift over time

**Symptom**: programmatic eval composite scores (`mean_composite_score`,
`task_success_rate`, judge-derived dimensions) fluctuate unpredictably
across sprints even when no behaviour change has shipped.

**Root causes**: LLM provider drift (model updates); judge
calibration variance (different runs disagree); mocked-vs-real-LLM
gap; unvalidated weighting dimensions.

**Bundled remediation**: per `governance/constitution.md` §5.5,
composite scores are OBSERVATION-only. The curated bad-case suite
(§5.6) is the primary acceptance gate.

**Consumer action**: still collect composite scores; surface in
sprint reviews as observation; do NOT use them to gate close.

### F2. Dev sessions accidentally bundle deliver-agent files

**Symptom**: dev session runs `git add -A` (or similar) and stages
`docs/sprint_objective.md` / `docs/10-handoff.md` / etc. that the
deliver-agent owns. At close, the deliver-agent has to "flip" the
file.

**Root causes**: dev sessions don't know which files are
deliver-agent-owned; broad staging commands; commit discipline isn't
enforced by the framework constitution alone.

**Bundled remediation**:
`framework/tools/precommit_bundling_check.sh` — pre-commit hook that
catches deliver-agent owned files staged outside a close commit.

**Consumer action**: install the hook at adoption:

```bash
ln -s ../../framework/tools/precommit_bundling_check.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### F3. Sprint stanza fields filled with hand-wave content

**Symptom**: a sub-sprint claims §7 stanza is filled, but the
"Generalization coverage" field reads "TBD" or "deferred without
reason". The dev session ships and the review agent has to catch it
later.

**Root causes**: humans rush sprint planning; deliver-agent generates
prompts that pass token-pattern-match but not semantic-pattern-match.

**Bundled remediation**: `framework/schemas/sprint_stanza.schema.json`
+ `framework/tools/stanza_validator.py` validate the four fields
against a JSON schema with strict oneOf rules.

**Consumer action**: the deliver-agent runs the validator before
dispatching the compact dev prompt. If validation fails, the
deliver-agent + human refine the stanza before dispatch.

### F4. Review agents miss multi-dimensional issues

**Symptom**: a single review session catches some issues but misses
others — e.g., catches semantic hardcode (architecture lens) but
misses an injection surface (security lens).

**Root causes**: a single review session anchors on one lens and
under-covers others.

**Bundled remediation**: `governance/constitution.md` §4.4 +
`templates/compact_review_prompt.md` §7 orchestrate **four parallel
sub-reviewers** by default at milestone close:

- Bug sub-reviewer (correctness)
- Security sub-reviewer (safety)
- Architecture sub-reviewer (§4.1 kernel)
- Regression-coverage sub-reviewer (§5)

Each returns its own verdict. Block-on-any-reject rule applies.

**Consumer action**: if your tool environment doesn't support
parallel sub-agents, walk the four lenses serially in named sections
of `docs/codex-findings.md`.

## Known but not bundled (documented patterns)

### F5. Agent context window saturation

**Symptom**: dev / review session runs out of context partway through
a long sub-sprint; truncates and produces incomplete handoff /
findings.

**Root causes**: large diffs, many file reads, verbose self-narration
in chat.

**Pattern (not bundled)**: budget reads per `context_briefing.md`
Context Pack Prompt; trace decisions instead of explaining them in
chat; offload mass file-reads to grep/glob instead of full reads;
break long sub-sprints into shorter ones.

**Consumer action**: if you hit this, the most common fix is
**break the sub-sprint smaller**. The framework's §8.5 already says
"sub-sprints that exceed 5 in a milestone signal the milestone is
too large" — the symmetric rule for individual sub-sprints is "if
the sub-sprint can't fit in one agent context window, split it".

### F6. Bad-case suite grows without bound

**Symptom**: the curated bad-case suite accumulates hundreds of
cases; manual review at every milestone close becomes infeasible.

**Root causes**: every bad case is opened as `core` tier; no
downgrade discipline.

**Pattern (not bundled)**: the framework's §5.6.1 bad-case tiering
(`core` / `scope-relevant` / `closed-as-regression-guard` /
`archived`) and §5.6.3 downgrade rule (N≥2 PASS in consecutive
closes) — but the discipline of actually applying tiers is a human
choice.

**Consumer action**: be aggressive about `scope-relevant` tagging at
case-open time. Only `core` cases run at every milestone. Apply the
N≥2 downgrade rule.

### F7. Research proposals shipped as binding

**Symptom**: research agent proposes Solution X; deliver-agent + dev
implement Solution X verbatim. When it doesn't work, no fallback
plan.

**Root causes**: treating proposals as decisions; not requiring
≥2 alternatives.

**Pattern (not bundled but enforced by deliver-agent role card)**:
`framework/role-cards/deliver-agent.md` says "research-agent in Path
1 MUST produce ≥2 alternatives with trade-off analysis". If a
proposal has only one alternative, ASK the human to dispatch another
research session.

**Consumer action**: train your research-agent prompt to always
include 2+ alternatives. If a research session returns only one,
deliver-agent refuses to consume it.

### F8. Forbidden-list temptations under deadline pressure

**Symptom**: a sub-sprint is failing close; the team is tempted to
add "just one keyword" / "just one if-else" to make the case pass.

**Root causes**: deadline pressure; framing the symptom as the
problem.

**Pattern (not bundled)**: the §1.7 forbidden list + §3.2 layer
classification + §4.1 kernel + §7 stanza chain are designed to make
this temptation visible. But the framework can't make the decision
for you.

**Consumer action**: when tempted, classify per §3.2. If it's
`runtime_guard`, check `runtime_invariants.md` for a current Tier-0.
If no Tier-0 covers it, you're choosing between (a) STOP and
escalate to `human_review_required`, (b) ship the hardcode with
explicit sunset plan in §7 (`introduced: true` + sunset trigger), or
(c) re-route to `prompt_projection` / `skill_state` /
`semantic_planner`. Don't just add the keyword silently.

### F9. Milestone scope creep

**Symptom**: a milestone planned for 3 sub-sprints becomes 7; the
acceptance bar broadens mid-flight; close keeps slipping.

**Root causes**: deliver-agent + human not enforcing the §8.5
"break milestone framing" rule.

**Pattern (not bundled)**: §8.5 hard limit at 5 sub-sprints; if
exceeded, split at next planning round. Sub-sprint that crosses
unrelated architectural surface is a signal it belongs in a different
milestone.

**Consumer action**: deliver-agent calls scope creep early. Better
to close M0 at 3 sub-sprints + open M1 with the spillover than to
let M0 sprawl.

### F10. Cross-session memory loss

**Symptom**: an agent on cold start doesn't know context that was
established in a previous session; produces redundant or wrong work.

**Root causes**: the framework's "no shared chat history" rule;
`docs/10-handoff.md` not updated by deliver-agent at close.

**Pattern (not bundled)**: deliver-agent close maintenance ops (see
`framework/role-cards/deliver-agent.md` "Close maintenance
operations") include updating §0 (cold-start table), §1 (narrative
lead with retention rule), §2 (archive index).

**Consumer action**: the close maintenance ops are mandatory.
Skipping them leaves the next session with no cold-start context.

### F11. Programmatic vs human judgment confusion at bad-case review

**Symptom**: someone reads the bad case `closure_criterion` and
treats it as an automatic verdict ("the trace contains X, so the
case passes"). But §5.6 says the verdict is human-judgment.

**Root causes**: closure_criterion is too tight, or the human reads
it as a contract rather than a guidance.

**Pattern (not bundled)**: write closure_criterion as guidance
naming observable end-states, not as an automatic predicate. The
human is the gate.

**Consumer action**: when authoring a new bad case, write
closure_criterion in the form "the trace should show <observable
end-state>; the human verifies by reading the trace and assessing
overall situation". NOT in the form "case passes iff
trace.contains(X) == true".

### F12. Adoption regret — "we adopted aidazi but it slowed us down"

**Symptom**: team adopts the framework, runs 2-3 milestones, feels
slower than before adoption, considers abandoning.

**Root causes** (in order of frequency):
1. Adopted full framework when Profile C (selective) would have been
   right.
2. Skipped the three domain contracts; running the framework
   without them.
3. Treating compact prompt generation as overhead instead of
   speedup.
4. Solo-developer with no role separation; framework discipline
   collapses.

**Pattern (not bundled)**: the framework is not free; it's
overhead-amortizing. The break-even point is usually around
milestone 2 — by then, the iteration discipline pays for itself
through better handoffs, faster review, fewer regressions.

**Consumer action**: if you're at milestone 2 and still feel slowed,
audit: (a) are you on the right adoption profile? (b) are the three
domain contracts actually filled? (c) is the deliver-agent doing
close maintenance ops? If yes to all and still slow, switch to
Profile C (selective adoption) — keep the §4.1 kernel + sprint
stanza, drop the rest.

## Adding new frictions

When you encounter a new friction in your project:

1. Document it locally first (e.g., `docs/diagnostics/frictions/<id>.md`).
2. After 2-3 milestones, if the friction recurs, propose adding it
   to this file via a PR against the framework repo.
3. If the friction is project-specific (won't help other consumers),
   keep it in your project docs only.
