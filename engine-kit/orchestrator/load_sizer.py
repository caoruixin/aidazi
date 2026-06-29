#!/usr/bin/env python3
"""load_sizer — WP-0 read-only per-role cold-start byte/token baseline.

OBSERVATION-ONLY. This tool sums the bytes of each role's **cold-start load set**
(the governance chain + role card + per-role briefing docs an agent reads at
role-session start) WITHOUT spawning anything — no LLM, no network, no write. It
exists because the cold-start reads are otherwise INVISIBLE to telemetry: they are
the agent's own mid-session Read calls, dropped at the adapter boundary
(adapters/claude_code.py), so the per-spawn audit (which records only the
as-dispatched prompt) cannot see them. The context/token-optimization kernels
(WP-2+) are measured against THIS baseline.

Source of truth: ``governance/context_briefing.md`` §1.2 (the universal
role-session cold-start order) + §2 (the per-role briefing lists). Those members
fall into three classes, and the sizer accounts for ALL of them — none is silently
dropped:

  1. FRAMEWORK-STATIC — fixed paths in the framework repo: the governance trio
     (§1.2 steps 1-3), the role card (step 6), and the framework process/template/
     schema briefing docs (§2). These are the kernel-reducible volume → ALWAYS sized.
  2. ADOPTER-STATIC — fixed paths but in the ADOPTER repo: ``AGENTS.md`` (§1.2 step 4)
     + ``docs/current/adoption-state.md`` (step 5). Sized when ``adopter_root`` /
     ``--adopter-root`` is supplied; otherwise reported as not-measured (it varies per
     adopter), NOT dropped.
  3. RUN-DYNAMIC — members named in §2 with NO fixed path (they vary per sprint/task:
     the specific ``compact/sprint-NNN-dev-prompt.md``, adopter ``docs/current/``
     runtime contracts named in a prompt's load_list, the §2 "Adopter inputs"). These
     cannot be sized statically; the sizer ENUMERATES them per role (``dynamic_unsized``)
     so the omission is explicit, not silent. Measure them against a concrete run.

So the default (framework root only) reports the framework-controlled static
cold-start — the meaningful figure for the kernel-reduction claim — and explicitly
declares the adopter-static + run-dynamic members it did not size. Supplying
``--adopter-root`` adds class 2 for an authoritative framework+adopter static floor.

Token figures are a documented ESTIMATE (bytes // 4), NOT a tokenizer count and NOT
implied from any dispatched prompt. This module is removable freely (it changes no
dispatched context). CLI::

    python load_sizer.py [--repo-root R] [--adopter-root A] [--role ROLE] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))      # engine-kit/orchestrator
_ENGINE_KIT_DIR = os.path.dirname(_HERE)
# e2e_stage imports audit_log (engine-kit/audit) — put the same dirs on sys.path the
# package uses for its bare sibling imports, so the sizer runs as a script OR imported.
for _p in (_HERE, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "audit")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import e2e_stage  # noqa: E402  (sibling under orchestrator/, on sys.path above)

#: The framework repo root (where governance/, role-cards/, process/, templates/,
#: schemas/ live) — engine-kit/ is a child of it.
REPO_ROOT_DEFAULT = os.path.dirname(_ENGINE_KIT_DIR)

#: bytes ÷ this ≈ tokens. A documented estimate (see module docstring), NOT a count.
BYTES_PER_TOKEN_EST = 4

# --------------------------------------------------------------------------- #
# The cold-start load sets (context_briefing.md §1.2 + §2). Each entry is
# (repo-relative path, purpose-tag). ``purpose`` groups the report:
#   governance = the universal floor re-paid on EVERY spawn (§1.2 steps 1-3) —
#                the primary kernel target; role_card = §1.2 step 6; briefing =
#                the per-role §2 list (process docs / templates / schemas).
# --------------------------------------------------------------------------- #

#: §1.2 steps 1-3 — the universal role-session cold-start floor (every explicit
#: role re-pays this on every fresh subprocess).
GOVERNANCE_TRIO: list = [
    # WP-2: cold-start step 1 loads the always-load constitution-CORE kernel (a complete,
    # machine-checked projection); the verbose canonical governance/constitution.md is loaded
    # on-demand, so it is NOT part of the per-spawn cold-start floor. The WP-7 load_graph_hash
    # fingerprints this set, so it tracks the kernel the agent actually reads.
    # WP-3: cold-start step 2 loads the always-load authoring-kernel (a complete,
    # machine-checked projection of doc_governance.md); the verbose canonical
    # governance/doc_governance.md loads on-demand (context_briefing §2.6), so it is NOT in the
    # per-spawn floor. The WP-7 load_graph_hash fingerprints this set, so it tracks the kernel
    # the agent actually reads. The trio stays a TRIO (3 entries).
    ("governance/constitution-core.md", "governance"),
    ("governance/authoring-kernel.md", "governance"),
    ("governance/context_briefing.md", "governance"),
]

#: Per-role FRAMEWORK-STATIC: §1.2 step 6 (role card) + §2 briefing list. Role keys are
#: the driver's spawn-role strings (dev/review/deliver/research/acceptance). The Deliver
#: track variant uses the typeA detours doc (the common default); a typeB/typeC adopter
#: would swap that one entry.
ROLE_COLD_START: dict = {
    "research": [  # §2.1
        ("role-cards/research-agent.md", "role_card"),
        ("process/domain-discovery-process.md", "briefing"),
        ("process/agent-design-elicitation.md", "briefing"),
        ("process/agent-creation-prerequisites.md", "briefing"),
        ("templates/compact-research-brief.md", "briefing"),
        ("schemas/research-brief.schema.json", "briefing"),
    ],
    "deliver": [  # §2.2
        ("role-cards/deliver-agent.md", "role_card"),
        ("process/milestone-framework.md", "briefing"),
        ("process/tech-architecture-decision-catalog.md", "briefing"),
        ("process/typeA-runtime-architecture-skeleton.md", "briefing"),
        ("process/artifact-taxonomy.md", "briefing"),
        ("process/post-deployment-iteration.md", "briefing"),
        ("process/common-detours-and-warnings-typeA.md", "briefing"),
        ("templates/deliver-close-taxonomy.md", "briefing"),
        ("templates/sprint-objective.md", "briefing"),
        ("templates/milestone-objective.md", "briefing"),
        ("templates/compact-dev-prompt.md", "briefing"),
    ],
    "dev": [  # §2.3 (the per-sprint compact prompt + adopter contracts are run-dynamic)
        ("role-cards/dev-agent.md", "role_card"),
        ("process/prompt-artifact-rules.md", "briefing"),
        ("process/context-passing-efficiency.md", "briefing"),
    ],
    "review": [  # §2.4
        ("role-cards/code-reviewer-agent.md", "role_card"),
        ("templates/anti-hardcode-review-kernel.md", "briefing"),
        # WP-1b: the agent cold-starts the COMPACT verdict projection (the verbose canonical
        # schemas/review-verdict.schema.json stays the Python validator's input, not loaded).
        ("schemas/compact/review-verdict.compact.schema.json", "briefing"),
    ],
    "acceptance": [  # §2.5
        ("role-cards/acceptance-agent.md", "role_card"),
        ("templates/compact-acceptance-prompt.md", "briefing"),
        # WP-1b: the agent cold-starts the COMPACT verdict projection (the verbose canonical
        # schemas/acceptance-verdict.schema.json stays the validator's + resolver-bound here).
        ("schemas/compact/acceptance-verdict.compact.schema.json", "briefing"),
        # WP-4B RETIRED the per-spawn whole-file process/delivery-loop.md read at Acceptance
        # cold-start: its judge-relevant content is projected INLINE via the acceptance-kernel,
        # which the driver EMBEDS in the dispatched acceptance prompt (→ counted in the WP-0
        # prompt_bytes audit, NOT a cold-start file read), and acceptance-agent.md §1 step-4 +
        # context_briefing.md §6 NEGATE the load. So delivery-loop.md is no longer part of the
        # Acceptance cold-start READ set (a stale entry until the WP-9 comparative eval surfaced
        # it — it had over-stated this baseline by ~47.5 KB while the read-trace canary proved
        # the agent never reads it). process/role-skill-model.md is likewise NOT cold-started by
        # Acceptance (WP-4B inlined its §4/§6 into the kernel); role_cold_start_roots excludes
        # it for acceptance even when skills are active.
    ],
}

#: WP-5A — TASK-SCOPED cold-start narrowing. The SAME spawn-role can serve more than one
#: task (the ``deliver`` role runs both a Close spawn ``schema_key="close"`` and a
#: Deliver-plan spawn ``schema_key="deliver_plan"``). A ``(role, task_kind)`` listed here
#: gets a NARROWER cold-start set than the role's full ``ROLE_COLD_START`` — the task_kind
#: is the spawn's stable ``schema_key`` literal (never inferred from prompt text). FAIL-CLOSED:
#: any ``(role, task_kind)`` NOT listed — including unknown task_kinds, ``None``, and
#: ``deliver_plan`` — falls through to the FULL role set; nothing defaults into a narrow path.
#: The Close set carries the role card + ``deliver-close-taxonomy.md`` (the A/B/C/D verdict
#: taxonomy); the 9 Deliver-plan-only briefing docs (plan decomposition, Δ process briefings,
#: author-time templates) are dropped — each adversarially proven Close-irrelevant + Codex-
#: APPROVED (WP-5A matrix). The governance trio is prepended by ``role_cold_start_roots`` for
#: every role/task, so it is NOT repeated here.
TASK_SCOPED_COLD_START: dict = {
    ("deliver", "close"): [  # emit a deliver-close-verdict (no plan-authoring needed)
        ("role-cards/deliver-agent.md", "role_card"),
        ("templates/deliver-close-taxonomy.md", "briefing"),
    ],
}

#: CONDITIONAL hard-constraint source (NOT in the skills-off baseline above). All five
#: role cards mandate loading ``process/role-skill-model.md`` when the role's skills are
#: active (acceptance-agent.md:253, dev-agent.md:156, research-agent.md:181,
#: deliver-agent.md:271, code-reviewer-agent.md:185); its §4 declares non-overridable
#: boundary constraints. Appended to a role's cold-start set ONLY when skills are active
#: (``role_cold_start_roots(..., skills_active=True)``) — so a change to it is recorded in
#: the WP-7 load_graph_hash exactly when it is a load-bearing input. The role cards' "or
#: you intend to fan out" clause is a RUNTIME agent decision, not config-derivable, so the
#: static fingerprint keys on the config-determinable signal (effective skills non-empty).
ROLE_SKILL_MODEL: tuple = ("process/role-skill-model.md", "briefing")

#: ADOPTER-STATIC (§1.2 steps 4-5): fixed paths in the ADOPTER repo. Sized only when an
#: ``adopter_root`` is supplied (an adopter varies per deployment); otherwise declared
#: not-measured. AGENTS.md transitively @-includes the framework governance chain in a
#: vendored adopter — resolve_load_graph follows those includes (deduped).
ADOPTER_STATIC: list = [
    ("AGENTS.md", "adopter_cold_start"),
    ("docs/current/adoption-state.md", "adopter_cold_start"),
]

#: RUN-DYNAMIC members (§1.2/§2) with NO fixed path → cannot be sized statically. The
#: sizer DECLARES them per role so nothing is silently dropped. ``_UNIVERSAL`` applies
#: to every role; per-role entries add the role's §2 "Adopter inputs".
_DYNAMIC_UNIVERSAL: list = [
    "adopter docs/current/* runtime contracts named in the task's load_list (§1.4-i)",
]
DYNAMIC_COLDSTART: dict = {
    "research": ["adopter inputs: Customer prompt, docs/proposals/*, transcripts/data, "
                 "recent docs/diagnostics/failure-briefs/* (§2.1)"],
    "deliver": ["adopter inputs: signed research brief, action_bank.md, handoff §0/§1, "
                "recent codex-findings, (Path 3) acceptance report + gap brief (§2.2)"],
    "dev": ["the specific compact/sprint-NNN-dev-prompt.md (per-sprint job spec, §2.3)"],
    "review": ["adopter inputs: dev diff, handoff §1-§11, sprint_objective.md, "
               "eval/bad_cases/* (§2.4)"],
    "acceptance": ["adopter inputs: research-brief closure_contract, dev F5 evidence "
                   "artifacts, latest codex-findings, prior acceptance reports (§2.5)"],
}

ROLES: tuple = ("research", "deliver", "dev", "review", "acceptance")

#: Δ-19 Phase 2-β — RUN-DYNAMIC acceptance artifacts (the per-milestone requirement-context
#: source facts + the derived gap_report + the functional checklist). These are RESOLVER-BOUND
#: runtime inputs (driver._acceptance_resolver_graph) — content-hashed into
#: acceptance_input_hash for verdict reproducibility — and are DELIBERATELY kept OUT of the
#: static cold-start floor (ROLE_COLD_START / ROLE_SKILL_MODEL), so binding/hashing them never
#: re-inflates the WP-4 acceptance-kernel savings. They carry the variable campaign plan /
#: ledger / state, so they cannot be sized statically; the driver sizes them at RUNTIME from
#: the resolver graph (which already records each entry's observed ``bytes``).
RUNTIME_ACCEPTANCE_ARTIFACT_PURPOSES: tuple = (
    "requirement_context", "gap_report", "functional_checklist")
#: Advisory runtime cap (NOT a hard gate — WP-9 doctrine: surface bloat, never force a shrink
#: of sufficient context). ~256 KB ≈ 64K tok of per-milestone acceptance data is generous;
#: over it is AUDITED as an advisory signal so a pathologically large ledger/plan is visible.
RUNTIME_ACCEPTANCE_ARTIFACT_CAP_BYTES: int = 262_144


def runtime_acceptance_artifact_report(
        resolver_graph: list, *,
        cap_bytes: int = RUNTIME_ACCEPTANCE_ARTIFACT_CAP_BYTES) -> dict:
    """Δ-19 Phase 2-β runtime size report for the per-milestone acceptance artifacts bound
    into the acceptance resolver graph (``requirement_context`` / ``gap_report`` /
    ``functional_checklist``). PURE: sums each bound entry's observed ``bytes`` by purpose.

    Returns ``{total_bytes, est_tokens, by_purpose, cap_bytes, over_cap}``. ADVISORY — the
    driver AUDITS it (never gate_hard_fails on it). It is a RUNTIME channel kept out of the
    static cold-start budget (``context_budget_report.py``), so these reproducibility-bound
    inputs are measured + visible without inflating ``ROLE_COLD_START``."""
    by_purpose: dict = {}
    for g in resolver_graph or []:
        p = g.get("purpose")
        if p in RUNTIME_ACCEPTANCE_ARTIFACT_PURPOSES:
            by_purpose[p] = by_purpose.get(p, 0) + int(g.get("bytes") or 0)
    total = sum(by_purpose.values())
    return {"total_bytes": total, "est_tokens": total // BYTES_PER_TOKEN_EST,
            "by_purpose": by_purpose, "cap_bytes": cap_bytes,
            "over_cap": total > cap_bytes}


# --------------------------------------------------------------------------- #
# Sizing.
# --------------------------------------------------------------------------- #
def size_load_set(roots: list, *, repo_root: str) -> dict:
    """Sum the cold-start bytes of a load set via ``resolve_load_graph``.

    ``roots`` is a list of ``(repo_relative_path, purpose)``. Each root is marked
    MANDATORY so an absent one surfaces in ``missing`` (drift detection) rather than
    being silently skipped. resolve_load_graph follows ``@``-includes transitively
    and dedups by realpath, so ``total_bytes`` is the real (deduplicated) closure.

    Returns ``{files, total_bytes, est_tokens, by_purpose, missing}`` where ``files``
    is the per-file ``[{path, purpose, bytes, sha256}]`` graph and ``missing`` is the
    list of repo-relative paths of mandatory roots that were absent/unreadable."""
    entries = []
    for rel, purpose in roots:
        entries.append({
            "path": os.path.join(repo_root, rel),
            "rel": rel,
            "purpose": purpose,
            "mandatory": True,
        })
    graph, missing = e2e_stage.resolve_load_graph(entries, repo_root=repo_root)
    total = sum(g.get("bytes", 0) for g in graph)
    by_purpose: dict = {}
    for g in graph:
        by_purpose[g["purpose"]] = by_purpose.get(g["purpose"], 0) + g.get("bytes", 0)
    return {
        "files": graph,
        "total_bytes": total,
        "est_tokens": total // BYTES_PER_TOKEN_EST,
        "by_purpose": by_purpose,
        "missing": [m.get("rel", m.get("path", "?")) for m in missing],
    }


def role_cold_start_roots(role: str, task_kind: str = None, *,
                          skills_active: bool = False) -> list:
    """The FRAMEWORK-STATIC cold-start roots for ``role`` as ``(rel, purpose)`` pairs:
    the governance trio (§1.2 steps 1-3) + role card (step 6) + per-role §2 briefing list.
    When ``skills_active`` (the role's effective skill set is non-empty) the CONDITIONAL
    constraint source ``process/role-skill-model.md`` (§4 boundary constraints) is appended.

    ``task_kind`` (WP-5A) is the spawn's stable ``schema_key`` literal. When ``(role,
    task_kind)`` is in ``TASK_SCOPED_COLD_START`` the role's briefing set is REPLACED by the
    narrower task-scoped set (the governance trio is still prepended). FAIL-CLOSED: ``None``,
    an unknown task_kind, or a known-but-unscoped one (e.g. ``deliver_plan``) falls through to
    the FULL ``ROLE_COLD_START[role]`` — a task NEVER defaults into a narrow path.

    SINGLE SOURCE OF TRUTH for the WP-0 sizer, the WP-7 ``load_graph_hash``, AND the driver's
    Close cold-start directive — so a cold-start change is edited in ONE place and the byte
    baseline, the audit fingerprint, and the dispatched directive track it together (no drift)."""
    if role not in ROLE_COLD_START:
        raise KeyError(f"unknown role {role!r}; known: {', '.join(ROLES)}")
    scoped = TASK_SCOPED_COLD_START.get((role, task_kind))
    role_set = scoped if scoped is not None else ROLE_COLD_START[role]
    roots = list(GOVERNANCE_TRIO) + list(role_set)
    # WP-4B: Acceptance no longer cold-starts process/role-skill-model.md — its §4 boundary + §6
    # skill-packaging rules are projected INLINE via the acceptance-kernel (embedded in the projected
    # acceptance prompt), and the §11 conditional load is retired. Other roles still load it when
    # skills / sub-agent fan-out are active.
    if skills_active and role != "acceptance" and ROLE_SKILL_MODEL not in roots:
        roots.append(ROLE_SKILL_MODEL)
    return roots


def cold_start_load_graph_hash(role: str, task_kind: str = None, *,
                               repo_root: str = REPO_ROOT_DEFAULT,
                               skills_active: bool = False) -> tuple:
    """WP-7: a content fingerprint of ``role``'s framework-static cold-start governance/
    kernel set. Resolves the cold-start roots (``role_cold_start_roots``) via the SAME
    ``resolve_load_graph`` machinery as the sizer and hashes each file's CONTENT IDENTITY
    (path / purpose / sha256), EXCLUDING the observational ``bytes`` field — so the hash
    changes iff a cold-start doc's CONTENT changes (e.g. a kernel swap). This makes an
    otherwise audit-NEUTRAL Dev/Review/Close/Research spawn's governance version
    ledger-recordable (their per-spawn ``input_hash`` is prompt-only).

    ``task_kind`` (WP-5A) is the spawn's stable ``schema_key`` literal; it (a) selects the
    task-scoped cold-start roots (Close loads a NARROWER set than Deliver-plan) and (b) is
    BOUND into the hash basis when present, so the fingerprint binds role + task_kind + the
    actual cold-start roots + content (HARD-CONSTRAINT C). ``None`` (an unscoped/full load)
    is the pre-WP-5A behavior and leaves the basis — and the hash — byte-identical.

    Returns ``(load_graph_hash, missing)`` where ``load_graph_hash`` is
    ``"sha256:" + sha256(...)[:16]`` (the same shape as the per-spawn ``input_hash`` it
    sits beside) and ``missing`` is the list of absent MANDATORY cold-start roots (drift).

    AUDIT-ONLY: this is NOT the Acceptance §3.5b reuse hash. Acceptance reuse is governed
    by ``acceptance_input_hash`` + the resolver graph; ``load_graph_hash`` NEVER substitutes
    for resolver binding on any verdict-affecting input (design spec §E LOAD-CLOSURE)."""
    roots = role_cold_start_roots(role, task_kind, skills_active=skills_active)
    res = size_load_set(roots, repo_root=repo_root)
    identity = [{k: v for k, v in g.items() if k != "bytes"} for g in res["files"]]
    basis_obj = {"role": role, "cold_start_graph": identity}
    if task_kind is not None:
        basis_obj["task_kind"] = task_kind
    basis = json.dumps(basis_obj, sort_keys=True, separators=(",", ":"))
    h = "sha256:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return h, res["missing"]


def size_role(role: str, task_kind: str = None, *, repo_root: str = REPO_ROOT_DEFAULT,
              adopter_root: str = None, skills_active: bool = False) -> dict:
    """Cold-start size for ``role``. ALWAYS sizes the FRAMEWORK-static set (governance
    trio §1.2 1-3 + role card §1.2 step 6 + per-role briefing §2). When ``adopter_root``
    is given, ALSO sizes the ADOPTER-static set (§1.2 steps 4-5). The RUN-DYNAMIC members
    (§2, no fixed path) are enumerated in ``dynamic_unsized`` — declared, never dropped.
    ``skills_active`` additionally counts the CONDITIONAL ``role-skill-model.md`` (default
    False keeps the skills-off baseline byte-identical). ``task_kind`` (WP-5A) sizes the
    TASK-SCOPED set for a task that gets a narrower cold-start (e.g. ``size_role("deliver",
    "close")`` is the Close-scoped size); ``None`` sizes the full role set (default,
    byte-identical to pre-WP-5A). Read-only.

    Returns ``{role, task_kind, files, by_purpose, framework_bytes, adopter_bytes,
    total_bytes, est_tokens, missing, dynamic_unsized}``. ``adopter_bytes`` is None when no
    ``adopter_root`` was supplied (= adopter-static not measured, not zero)."""
    fw = size_load_set(role_cold_start_roots(role, task_kind, skills_active=skills_active),
                       repo_root=repo_root)
    out = {
        "role": role,
        "task_kind": task_kind,
        "files": list(fw["files"]),
        "by_purpose": dict(fw["by_purpose"]),
        "framework_bytes": fw["total_bytes"],
        "adopter_bytes": None,
        "missing": list(fw["missing"]),
        "dynamic_unsized": list(_DYNAMIC_UNIVERSAL) + list(DYNAMIC_COLDSTART.get(role, [])),
    }
    if adopter_root:
        ad = size_load_set(list(ADOPTER_STATIC), repo_root=adopter_root)
        out["adopter_bytes"] = ad["total_bytes"]
        out["files"] += ad["files"]
        for k, v in ad["by_purpose"].items():
            out["by_purpose"][k] = out["by_purpose"].get(k, 0) + v
        out["missing"] += [f"(adopter) {m}" for m in ad["missing"]]
    out["total_bytes"] = out["framework_bytes"] + (out["adopter_bytes"] or 0)
    out["est_tokens"] = out["total_bytes"] // BYTES_PER_TOKEN_EST
    return out


def size_all_roles(*, repo_root: str = REPO_ROOT_DEFAULT,
                   adopter_root: str = None) -> dict:
    """Cold-start size for every role. Read-only. Returns ``{role: size_role(...)}``."""
    return {role: size_role(role, repo_root=repo_root, adopter_root=adopter_root)
            for role in ROLES}


# --------------------------------------------------------------------------- #
# Track 1 §2.4 — RESOLVED-SKILL-BODY sizing (the Codex R-T1 B1 budget path).
#
# A role's effective SKILL.md bodies are the agent's OWN mid-session reads (the
# `skill_prompt_block` tells it "Load every SKILL.md below"), so they are INVISIBLE to the
# per-spawn prompt audit AND are NOT in the governance/role-card/briefing cold-start floor
# (toggling `skills_active=True` only adds the CONDITIONAL process/role-skill-model.md — it
# sizes NO SKILL.md body). This path sizes the RESOLVED selected skill bodies themselves so
# `context_budget_report.py --strict` can catch task-skill body growth PER DEFAULT + (Phase
# 1-c) PER TASK-SIGNAL SET. Deterministic + framework-static (charter-less role defaults +
# §2.3 task-signal selection); read-only.
# --------------------------------------------------------------------------- #
def _skill_md_rel(skill_path: str, real_repo_root: str) -> str:
    """Repo-relative path of a resolved skill's SKILL.md (forward-slashed). ``real_repo_root``
    MUST already be realpath-resolved: ``resolve_role_config`` returns realpath'd skill paths
    (``_resolve_skill``), so the base must be realpath'd too or a symlinked checkout (e.g. a
    macOS ``/var`` → ``/private/var`` tempdir) yields a bogus ``../..`` rel + a 0-byte size."""
    md = os.path.join(skill_path, "SKILL.md")
    return os.path.relpath(md, real_repo_root).replace(os.sep, "/")


def resolve_role_skill_bodies(role: str, *, task_signals=(),
                              repo_root: str = REPO_ROOT_DEFAULT,
                              adopter_root: str = None) -> tuple:
    """Resolve ``role``'s EFFECTIVE skill set (framework ``role_defaults`` + §2.3 task-signal
    selection, charter-less) and return ``(skill_md_rels, effective_config, real_repo_root)``.
    EXCLUDES Acceptance from task selection by virtue of ``resolve_role_config``'s own §2.5
    exclusion. Deterministic. The erc import is LOCAL so the hot driver path (``size_role`` /
    ``cold_start_load_graph_hash``) stays free of the skill-resolution dependency."""
    import effective_role_config as erc  # noqa: E402  (engine-kit sibling on sys.path)
    real_root = os.path.realpath(repo_root)
    eff = erc.resolve_role_config({}, role, task_signals=task_signals,
                                  framework_root=repo_root, adopter_root=adopter_root)
    rels = [_skill_md_rel(s.path, real_root) for s in eff.skills]
    return rels, eff, real_root


def size_role_skills(role: str, *, task_signals=(),
                     repo_root: str = REPO_ROOT_DEFAULT,
                     adopter_root: str = None) -> dict:
    """Cold-start size of ``role``'s effective SKILL.md BODIES (+ their ``@``-includes), sized
    via the SAME ``resolve_load_graph`` machinery (deduped) as every other load set. ``task_signals``
    (default ``()``) sizes the role-default set; a non-empty signal list sizes the §2.3 task-selected
    superset (Phase 1-c). Read-only.

    Returns ``size_load_set(...)`` augmented with ``{role, task_signals, skill_ids,
    selected_skills, skipped_skills}`` so the budget report can attribute growth to a specific
    skill. ``missing`` is normally empty (``resolve_role_config`` already verified each SKILL.md);
    a task-selected candidate that is catalog-declared but absent on disk is dropped via the §2.2
    skip (surfaced in ``skipped_skills``), NOT counted as missing."""
    rels, eff, real_root = resolve_role_skill_bodies(
        role, task_signals=task_signals, repo_root=repo_root, adopter_root=adopter_root)
    res = size_load_set([(r, "skill_body") for r in rels], repo_root=real_root)
    res["role"] = role
    res["task_signals"] = list(task_signals or ())
    res["skill_ids"] = [s.id for s in eff.skills]
    res["selected_skills"] = list(eff.selected_skills)
    res["skipped_skills"] = [dict(x) for x in eff.skipped_skills]
    return res


# --------------------------------------------------------------------------- #
# Reporting / CLI.
# --------------------------------------------------------------------------- #
def render_report(sizes: dict, *, adopter_measured: bool = False) -> str:
    """Deterministic text table: per-role framework / adopter / total bytes + est-tokens,
    with the governance floor (re-paid every spawn) broken out as the kernel target, and
    a footer enumerating the run-dynamic members the sizer did NOT statically size."""
    lines = ["# Cold-start load baseline (WP-0, observation-only — bytes ÷ 4 ≈ tokens)",
             ""]
    lines.append("| role | governance | framework | adopter | total | ~tokens | missing |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for role in ROLES:
        s = sizes[role]
        gov = s["by_purpose"].get("governance", 0)
        adv = "n/m" if s["adopter_bytes"] is None else str(s["adopter_bytes"])
        miss = ", ".join(s["missing"]) if s["missing"] else "-"
        lines.append(
            f"| {role} | {gov} | {s['framework_bytes']} | {adv} "
            f"| {s['total_bytes']} | {s['est_tokens']} | {miss} |")
    floor = next(iter(sizes.values()))["by_purpose"].get("governance", 0)
    lines.append("")
    lines.append(f"Universal governance floor (§1.2 steps 1-3, re-paid every spawn): "
                 f"{floor} bytes ≈ {floor // BYTES_PER_TOKEN_EST} tokens.")
    if not adopter_measured:
        lines.append("Adopter-static (§1.2 steps 4-5: AGENTS.md + docs/current/"
                     "adoption-state.md): n/m — supply --adopter-root to measure.")
    lines.append("")
    lines.append("Run-dynamic members NOT statically sized (declared, §2):")
    seen = set()
    for role in ROLES:
        for d in sizes[role]["dynamic_unsized"]:
            if d not in seen:
                seen.add(d)
                lines.append(f"- {d}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="WP-0 read-only per-role cold-start byte/token baseline sizer.")
    ap.add_argument("--repo-root", default=REPO_ROOT_DEFAULT,
                    help="framework repo root (default: this checkout's root)")
    ap.add_argument("--adopter-root", default=None,
                    help="adopter repo root — also size adopter-static AGENTS.md + "
                         "docs/current/adoption-state.md (§1.2 steps 4-5)")
    ap.add_argument("--role", choices=ROLES,
                    help="size a single role (default: all roles)")
    ap.add_argument("--task-kind", default=None,
                    help="WP-5A: size a task-scoped cold-start set (e.g. --role deliver "
                         "--task-kind close); requires --role. Unknown/omitted = full role set.")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of the text table")
    args = ap.parse_args(argv)

    if args.task_kind and not args.role:
        ap.error("--task-kind requires --role")
    if args.role:
        sizes = {args.role: size_role(args.role, args.task_kind, repo_root=args.repo_root,
                                      adopter_root=args.adopter_root)}
    else:
        sizes = size_all_roles(repo_root=args.repo_root, adopter_root=args.adopter_root)

    if args.json:
        print(json.dumps(sizes, indent=2, sort_keys=True))
    elif args.role:
        print(json.dumps(sizes[args.role], indent=2, sort_keys=True))
    else:
        print(render_report(sizes, adopter_measured=bool(args.adopter_root)), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
