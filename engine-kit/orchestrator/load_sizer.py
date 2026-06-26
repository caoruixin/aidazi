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
    ("governance/constitution.md", "governance"),
    ("governance/doc_governance.md", "governance"),
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
        ("schemas/review-verdict.schema.json", "briefing"),
    ],
    "acceptance": [  # §2.5 (role card mandates process/delivery-loop.md, acceptance-agent.md:40)
        ("role-cards/acceptance-agent.md", "role_card"),
        ("templates/compact-acceptance-prompt.md", "briefing"),
        ("schemas/acceptance-verdict.schema.json", "briefing"),
        # delivery-loop.md is loaded by every orchestrator-driven Acceptance session
        # (acceptance-agent.md:40 + context_briefing.md §6) → part of the baseline.
        # process/role-skill-model.md is FEATURE-GATED (loaded only when
        # tooling.acceptance.skills is non-empty, acceptance-agent.md:253) → excluded
        # from this skills-off baseline; a skills-on adopter would add it.
        ("process/delivery-loop.md", "briefing"),
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


def role_cold_start_roots(role: str, *, skills_active: bool = False) -> list:
    """The FRAMEWORK-STATIC cold-start roots for ``role`` as ``(rel, purpose)`` pairs:
    the governance trio (§1.2 steps 1-3) + role card (step 6) + per-role §2 briefing list.
    When ``skills_active`` (the role's effective skill set is non-empty) the CONDITIONAL
    constraint source ``process/role-skill-model.md`` (§4 boundary constraints) is appended.

    SINGLE SOURCE OF TRUTH for both the WP-0 sizer and the WP-7 ``load_graph_hash`` — so a
    future cold-start swap (e.g. WP-2's constitution-core) is edited in ONE place and BOTH
    the byte baseline and the audit fingerprint track it together (no drift)."""
    if role not in ROLE_COLD_START:
        raise KeyError(f"unknown role {role!r}; known: {', '.join(ROLES)}")
    roots = list(GOVERNANCE_TRIO) + list(ROLE_COLD_START[role])
    if skills_active and ROLE_SKILL_MODEL not in roots:
        roots.append(ROLE_SKILL_MODEL)
    return roots


def cold_start_load_graph_hash(role: str, *, repo_root: str = REPO_ROOT_DEFAULT,
                               skills_active: bool = False) -> tuple:
    """WP-7: a content fingerprint of ``role``'s framework-static cold-start governance/
    kernel set. Resolves the cold-start roots (``role_cold_start_roots``) via the SAME
    ``resolve_load_graph`` machinery as the sizer and hashes each file's CONTENT IDENTITY
    (path / purpose / sha256), EXCLUDING the observational ``bytes`` field — so the hash
    changes iff a cold-start doc's CONTENT changes (e.g. a kernel swap). This makes an
    otherwise audit-NEUTRAL Dev/Review/Close/Research spawn's governance version
    ledger-recordable (their per-spawn ``input_hash`` is prompt-only).

    Returns ``(load_graph_hash, missing)`` where ``load_graph_hash`` is
    ``"sha256:" + sha256(...)[:16]`` (the same shape as the per-spawn ``input_hash`` it
    sits beside) and ``missing`` is the list of absent MANDATORY cold-start roots (drift).

    AUDIT-ONLY: this is NOT the Acceptance §3.5b reuse hash. Acceptance reuse is governed
    by ``acceptance_input_hash`` + the resolver graph; ``load_graph_hash`` NEVER substitutes
    for resolver binding on any verdict-affecting input (design spec §E LOAD-CLOSURE)."""
    roots = role_cold_start_roots(role, skills_active=skills_active)
    res = size_load_set(roots, repo_root=repo_root)
    identity = [{k: v for k, v in g.items() if k != "bytes"} for g in res["files"]]
    basis = json.dumps({"role": role, "cold_start_graph": identity},
                       sort_keys=True, separators=(",", ":"))
    h = "sha256:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return h, res["missing"]


def size_role(role: str, *, repo_root: str = REPO_ROOT_DEFAULT,
              adopter_root: str = None, skills_active: bool = False) -> dict:
    """Cold-start size for ``role``. ALWAYS sizes the FRAMEWORK-static set (governance
    trio §1.2 1-3 + role card §1.2 step 6 + per-role briefing §2). When ``adopter_root``
    is given, ALSO sizes the ADOPTER-static set (§1.2 steps 4-5). The RUN-DYNAMIC members
    (§2, no fixed path) are enumerated in ``dynamic_unsized`` — declared, never dropped.
    ``skills_active`` additionally counts the CONDITIONAL ``role-skill-model.md`` (default
    False keeps the skills-off baseline byte-identical). Read-only.

    Returns ``{role, files, by_purpose, framework_bytes, adopter_bytes, total_bytes,
    est_tokens, missing, dynamic_unsized}``. ``adopter_bytes`` is None when no
    ``adopter_root`` was supplied (= adopter-static not measured, not zero)."""
    fw = size_load_set(role_cold_start_roots(role, skills_active=skills_active),
                       repo_root=repo_root)
    out = {
        "role": role,
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
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of the text table")
    args = ap.parse_args(argv)

    if args.role:
        sizes = {args.role: size_role(args.role, repo_root=args.repo_root,
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
