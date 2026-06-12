---
name: anti-hardcode-review-kernel
description: Apply the aidazi 9-question anti-hardcode review kernel (plus the 5 v4 forbidden-list checks A-E) to a PR or diff that touches a semantic surface, and return exactly one of 4 verdicts (approve / approve with downgrade-to-signal follow-up / reject as semantic hardcode / needs human architecture decision). Use when reviewing code changes for semantic hardcodes — keyword, regex, if-else, enum, or per-UC encodings of decisions an LLM should own. Designed for the aidazi Code Reviewer role; read-only.
license: Same as the aidazi framework repository
compatibility: Requires read access to the aidazi framework docs (templates/, governance/); no network, no write tools
allowed-tools: Read Grep Glob
metadata:
  normative_source: templates/anti-hardcode-review-kernel.md
  framework: aidazi
  framework_version: v4.0.0
  target_role: code-reviewer
---

# Anti-hardcode review kernel (role skill)

This skill is the packaged form of the aidazi Code Reviewer's canonical anti-hardcode review procedure, per the **dual-source rule** in `process/role-skill-model.md` §6:

- **Normative source**: `templates/anti-hardcode-review-kernel.md` (framework root). This SKILL.md is thin packaging and does NOT duplicate the kernel body. If this wrapper and the source disagree, the source wins.
- When exporting this skill standalone (outside the aidazi repo), copy the normative source into `references/anti-hardcode-review-kernel.md` at export time and read it from there instead.

## When to use

- A PR/diff touches a **semantic surface**: prompt projection, planner, judge config, eval spec, or any new keyword / regex / enum influencing a routing or escalation decision.
- You are operating as (or assisting) the aidazi **Code Reviewer role** — read-only (`Read`, `Grep`, `Glob`); never edit files, never run scripts.

Do NOT use this skill to judge delivered behavior against a closure_contract — that is the Acceptance role's gate (Constitution §3.4 invariant #3; cross-role skill use is forbidden by invariant #6).

## How to run

1. Load the normative source: `templates/anti-hardcode-review-kernel.md` (from the aidazi framework root; in standalone export, `references/anti-hardcode-review-kernel.md`).
2. Check scope exemptions first: pure infra / docs-only / config-governance / characterization-test diffs return `approve` with the exemption named.
3. For all other diffs, walk the **9 numbered questions in order**, then the **5 additional checks A-E** (Constitution §1.7-A through §1.7-E; any hit is a P0 finding).
4. For each "yes" or concern, paste the diff snippet and reasoning.
5. Return **exactly one** of the 4 verdicts defined in the source.
6. Do not rewrite the PR; do not propose a code fix beyond naming the Δ-9 fix layer (`process/post-deployment-iteration.md`).

## Constraints (inherited from the Code Reviewer role)

Per Constitution §3.4 invariant #6, this skill inherits the mounting role's whitelist and boundary: read-only tools only; output lands in the role's own verdict artifact (`docs/codex-findings.md` when run inside the chain); the role — not this skill — signs the verdict.

---

End of skill.
