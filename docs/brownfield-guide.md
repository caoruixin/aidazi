# Brownfield adoption guide — integrating aidazi into an existing project

This guide is for projects that already exist (some code, some docs,
some history) and want to adopt `aidazi` for iteration discipline
without disrupting current work.

The integration is **non-invasive and incremental**: you don't have
to retroactively label past sprints, you don't have to rewrite your
docs, you don't have to change your code organization. You just
introduce the framework as the iteration discipline for **new work
from adoption onward**.

## Pre-adoption diagnostic

Before adopting, audit your existing project on these dimensions.
The answers determine which integration profile fits.

| Dimension | Profile A (no governance) | Profile B (some governance) | Profile C (mature governance) |
|---|---|---|---|
| Has a constitution / governance doc? | No | Informal | Yes |
| Has a clear LLM-vs-runtime ownership boundary? | No | Implicit | Documented |
| Has eval / test discipline? | Ad hoc | Some tests, no eval | Tests + eval |
| Has multi-agent sessions today? | Single agent / single dev | Sometimes | Yes (research / dev / review pattern emerges) |
| Has cross-session continuity docs? | Chat history only | README + scattered notes | Structured handoff |

Most existing projects fall into Profile A or B. Profile C projects
may not need `aidazi` (their discipline is already mature); they may
want to adopt selectively (just the §4.1 kernel, just the milestone
framework).

## Integration profiles

### Profile A — minimal-invasive bootstrap (most common)

Goal: introduce the framework as a thin layer over existing code
without rewriting anything.

Effort: 2–4 hours initial setup + first milestone.

Steps:

1. **Add aidazi as a submodule** at `framework/`:

   ```bash
   cd existing-project/
   git submodule add https://github.com/your-org/aidazi.git framework
   cd framework && git checkout v0.1.0 && cd ..
   git add framework .gitmodules
   git commit -m "[chore] add aidazi framework submodule"
   ```

2. **Create `AGENTS.md`** at project root, copying from
   `framework/AGENTS.md` (consumer template):

   ```bash
   cp framework/AGENTS.md AGENTS.md
   # Edit AGENTS.md: replace {agent_kind_one_paragraph_description}
   # with your project's one-liner
   ```

3. **Bootstrap the three domain contracts** with minimal placeholders:

   ```bash
   mkdir -p docs/current
   cp framework/examples/minimal-greenfield/docs/current/domain_taxonomy.md docs/current/
   cp framework/examples/minimal-greenfield/docs/current/runtime_invariants.md docs/current/
   cp framework/examples/minimal-greenfield/docs/current/eval_acceptance_bars.md docs/current/
   # Edit each to reflect your project's current state. Even a 1-paragraph
   # placeholder ("We currently have no explicit Tier-0 invariants; this
   # file will be filled during M0") is enough to start. The first
   # milestone can be "build the three domain contracts properly".
   ```

4. **Bootstrap the cross-session continuity scaffold**:

   ```bash
   mkdir -p docs/sprints docs/milestones docs/solutions docs/diagnostics/failure-briefs
   mkdir -p compact eval/bad_cases
   cp framework/examples/minimal-greenfield/docs/10-handoff.md docs/
   cp framework/examples/minimal-greenfield/docs/action_bank.md docs/
   cp framework/examples/minimal-greenfield/docs/milestone_objective.md docs/
   cp framework/examples/minimal-greenfield/docs/sprint_objective.md docs/
   cp framework/examples/minimal-greenfield/eval/bad_cases/_manifest.md eval/bad_cases/
   ```

5. **Install the pre-commit hook** (optional but recommended):

   ```bash
   ln -s ../../framework/tools/precommit_bundling_check.sh .git/hooks/pre-commit
   chmod +x .git/hooks/pre-commit
   ```

6. **Install schema validator dependency** (optional but recommended):

   ```bash
   pip install jsonschema
   ```

7. **Commit the bootstrap**:

   ```bash
   git add -A
   git commit -m "[chore] bootstrap aidazi integration"
   ```

After this, your project has:

- The framework available at `framework/`
- `AGENTS.md` pointing to framework governance + consumer domain
  contracts
- Minimal-but-valid domain contracts (you'll fill them during M0)
- Empty scaffolds for milestones / sub-sprints / bad cases / R-items
- Pre-commit hook + schema validator ready to use

Your existing code is untouched. Your existing docs (README, design
docs, etc.) are untouched. The framework is a **new layer**, not a
replacement.

### Profile B — governance enhancement

For projects that already have informal governance (a CONTRIBUTING.md,
some design docs, some review process). Goal: align the existing
practice with `aidazi`'s shape without losing what already works.

Steps 1–6 are the same as Profile A. Additional steps:

7. **Map existing governance to framework sections**. For each
   existing governance doc (CONTRIBUTING, ADRs, design notes),
   classify per `framework/governance/doc_governance.md` tier model:

   - Is it `current-runtime`? Move to `docs/current/` if not already.
   - Is it `foundational`? Move to `docs/foundational/`.
   - Is it `proposal`? Mark with `status: proposal`.
   - Is it `archive`? Move to `docs/archive/`.

8. **Annotate front matter** on existing docs (incremental; don't do
   them all at once). Add the YAML front matter block per
   `doc_governance.md` schema.

9. **Bridge existing review process to the §4.1 kernel**. If you
   already do code review, your reviewer should adopt the
   nine-question kernel for semantic-touching PRs. The
   `compact/M<N>-review-prompt.md` template is the bridge.

10. **Bridge existing sprint / iteration cadence to the milestone
    framework**. If your current cadence is "one PR at a time", group
    3–5 related PRs into a milestone retroactively (without claiming
    they were milestones at the time). For new work, plan in
    milestones.

### Profile C — selective adoption

For projects with mature governance that don't want to fully migrate.
Goal: adopt the parts of `aidazi` that fill specific gaps without
rewriting your stack.

Common selective adoptions:

- **Adopt only the §4.1 kernel** — paste
  `framework/templates/anti_hardcode_kernel.md` into your existing
  review process. Don't change anything else.
- **Adopt only the milestone framework** — group PRs into 3-5 batch
  reviews using `framework/templates/milestone_objective.md`. Don't
  change your sprint cadence.
- **Adopt only the bad-case suite discipline** — use
  `eval/bad_cases/_manifest.md` lifecycle (open / active / closed /
  archived) without adopting the full agent role registry.
- **Adopt only the role cards as job descriptions** — use
  `framework/role-cards/*` as hiring / onboarding material for human
  + AI agent roles, without enforcing the constitution chain.

## Brownfield-specific cautions

### Don't retroactively relabel past sprints

Per `constitution.md` §8.7, the milestone framework applies
prospectively from adoption onward. Don't go back and call your old
sprints "milestones" — they were what they were. The framework starts
NOW.

### Don't try to back-fill all three domain contracts in one PR

The three domain contracts (taxonomy, invariants, acceptance bars)
are load-bearing. Filling them well takes thought. Bootstrap with
minimal placeholders, then make "fill the domain contracts" your M0
goal. By the end of M0 they'll be real.

### Don't migrate code organization to match the framework

The framework references `docs/current/`, `docs/sprints/`,
`docs/milestones/`, etc. — but it makes NO claims about how your
**code** is organized. If your code lives under `src/`, `lib/`, or
some other layout, the framework doesn't care. Domain code
organization is yours.

### Don't lose existing forward-looking design content

Brownfield projects often have valuable design notes that are
proposals, partial designs, or "we tried this and it didn't work"
documents. Mark them `status: proposal | partial | deferred |
historical` per `doc_governance.md` rather than deleting. Forward-
looking content is an asset.

### Don't introduce the §4.1 kernel mid-PR

If you're already mid-PR when you adopt `aidazi`, don't suddenly
enforce the §4.1 kernel against in-flight work. Adopt for the **next**
PR.

## Brownfield first-milestone candidates

Common M0 goals for brownfield adoption:

- **"Fill the three domain contracts"** — taxonomy + invariants +
  acceptance bars. Sub-sprints: audit current code → draft taxonomy
  → draft invariants → draft acceptance bars.
- **"Surface 5 bad cases from real sessions / production logs"** —
  build the curated suite from existing observed failures.
- **"Bring one existing failure mode under R-item discipline"** —
  pick a known recurring problem; classify it per §3 layer; open R-
  item; plan a sub-sprint to fix.

These are good M0s because they fill the framework's expected
artefacts without requiring code rewrites.

## Brownfield budget

| Profile | Initial setup | M0 effort |
|---|---|---|
| A. Minimal | 2–4 hours | 1–2 weeks (fill domain contracts) |
| B. Governance enhancement | 1–2 days (incremental front-matter + tier mapping) | 2–4 weeks |
| C. Selective | 1–2 hours | varies (depends on what's adopted) |

## After brownfield adoption

Once M0 is closed, the project runs on the framework's normal cadence
(same as greenfield from this point on). See
`greenfield-guide.md` step 7.
