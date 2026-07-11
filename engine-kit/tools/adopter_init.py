#!/usr/bin/env python3
"""adopter_init.py — one-command new-adopter bootstrap (Phase-5, design §4).

Scaffolds a fresh aidazi adopter from an answers file and exits with the four adoption
validators GREEN (or a printed remediation list). Cluster 2 = the answers-driven, offline
scaffolding CORE: no interactive prompts, no live reachability probe (those are Cluster 3).

Architecture (design §2 invariants):
  * I1  pure core / IO shell — ``build_artifacts(plan, templates)`` is a PURE function (no
        filesystem writes, no network, no reads: it operates on PRE-LOADED template strings +
        the plan). ``load_templates`` does the reads; ``materialize`` does the writes.
  * I2  guarded dest — ``assert_writable_dest`` refuses (exit 3) a dest that IS the framework
        repo OR is nested inside ``framework_root``; it runs BEFORE any write. The framework
        tree is mounted under ``<dest>/aidazi/`` (NOT the dest root) so ``is_framework_repo``
        does not flag the adopter.
  * I3  never auto-confirm — the tool NEVER emits ``confirmed_by_human: true`` on its own; the
        intent-contract confirm flag and the seed brief's gate-1 token come ONLY from the
        answers (the human). A false/absent flag ⇒ a truthful ``partial`` signed-brief.
  * I4  offline gate — the hard exit gate is the four offline/deterministic validators; the
        live reachability probe (Cluster 3) is env-gated and advisory.

CLI:
  python engine-kit/tools/adopter_init.py <dest> --answers answers.json
    [--framework-root PATH] [--force] [--overwrite] [--dry-run] [--probe off]

Exit codes: 0 all four validators green; 2 validation failed (remediation printed);
3 refused (dest is/inside the framework repo, non-empty dest without --force, or invalid
answers).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Optional

import yaml

# --- framework wiring: import the four validators as libraries (I7: no runtime coupling) --- #
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_FRAMEWORK_ROOT_DEFAULT = os.path.dirname(os.path.dirname(_TOOLS_DIR))  # <root>/engine-kit/tools -> <root>
_VALIDATORS_DIR = os.path.join(_FRAMEWORK_ROOT_DEFAULT, "engine-kit", "validators")
if _VALIDATORS_DIR not in sys.path:
    sys.path.insert(0, _VALIDATORS_DIR)

import adoption_status  # noqa: E402
import adopter_wiring_validator  # noqa: E402
import charter_validator  # noqa: E402
import control_plane_validator  # noqa: E402

FRAMEWORK_VERSION = "v4.0.0"
# Framework subtrees mounted under <dest>/aidazi/ (design §4.3). engine-kit gives
# _engine_kit_present its aidazi/engine-kit/orchestrator/driver.py; the rest resolve the
# governance/process/role-card/schema references in the emitted AGENTS.md.
FRAMEWORK_MOUNT_DIRS = ("engine-kit", "governance", "process", "role-cards", "schemas", "templates")
_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".gate", ".git")


class InitError(Exception):
    """A refusal / precondition failure (maps to exit 3)."""


# --------------------------------------------------------------------------- #
# AdopterPlan — the fully-resolved answers (design §4.2 / schema §7.1)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LLMRole:
    harness: str
    provider: str
    model: str
    capability_ref: Optional[str] = None
    endpoint: Optional[str] = None
    endpoint_env: Optional[str] = None
    api_key_env: Optional[str] = None


@dataclass(frozen=True)
class AdopterPlan:
    adopter_name: str
    track: str
    greenfield: bool
    mission_id: str
    intent_goal: str
    intent_standard: str
    intent_proof: str
    intent_confirmed: bool
    intent_confirmed_at: Optional[str]
    autonomy_level: str
    subsprint_sequence: list
    layers_allowed: list
    modules_in_scope: list
    explicitly_out_of_scope: list
    budget: dict
    llm_roles: dict  # role -> LLMRole
    eval_cmd: str
    eval_timeout: int
    brief_title: str
    brief_summary: str
    brief_confirmed: bool
    brief_customer_signed: bool
    raw: dict = field(default_factory=dict, repr=False)


def _answers_schema_path(framework_root: str) -> str:
    return os.path.join(framework_root, "schemas", "adopter-init-answers.schema.json")


def load_answers(path: str, framework_root: str) -> AdopterPlan:
    """Parse + schema-validate the answers JSON, returning an AdopterPlan (raises InitError)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise InitError(f"could not read answers file {path!r}: {exc}")

    _validate_answers_schema(data, framework_root)

    ic = data["intent_contract"]
    scope = data["autonomy"]["approved_scope"]
    roles = {
        name: LLMRole(
            harness=r["harness"], provider=r["provider"], model=r["model"],
            capability_ref=r.get("capability_ref"), endpoint=r.get("endpoint"),
            endpoint_env=r.get("endpoint_env"), api_key_env=r.get("api_key_env"),
        )
        for name, r in data["llm_roles"].items()
    }
    brief = data.get("research_brief") or {}
    return AdopterPlan(
        adopter_name=data["adopter_name"],
        track=data["track"],
        greenfield=data.get("greenfield", True),
        mission_id=data.get("mission_id") or "M1",
        intent_goal=ic["goal"], intent_standard=ic["standard"], intent_proof=ic["proof_of_done"],
        intent_confirmed=bool(ic.get("confirmed_by_human", False)),
        intent_confirmed_at=ic.get("confirmed_at"),
        autonomy_level=data["autonomy"]["level"],
        subsprint_sequence=list(scope["subsprint_sequence"]),
        layers_allowed=list(scope["layers_allowed"]),
        modules_in_scope=list(scope["modules_in_scope"]),
        explicitly_out_of_scope=list(scope.get("explicitly_out_of_scope", [])),
        budget=dict(data["autonomy"]["budget"]),
        llm_roles=roles,
        eval_cmd=data["eval"]["cmd"], eval_timeout=int(data["eval"]["timeout_seconds"]),
        brief_title=brief.get("title") or f"{data['adopter_name']} seed brief",
        brief_summary=brief.get("summary") or ic["goal"],
        brief_confirmed=bool(brief.get("confirmed_by_human", False)),
        brief_customer_signed=bool(brief.get("customer_signed", False)),
        raw=data,
    )


def _validate_answers_schema(data: dict, framework_root: str) -> None:
    """Validate answers against schemas/adopter-init-answers.schema.json (fail-closed)."""
    schema_path = _answers_schema_path(framework_root)
    try:
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except OSError as exc:
        raise InitError(f"answers schema unavailable at {schema_path!r}: {exc}")
    try:
        import jsonschema  # type: ignore
    except ImportError:
        # jsonschema is the validators' own dependency; if absent, do a minimal required-key
        # check so we still fail closed on obviously-wrong answers.
        _minimal_answers_check(data)
        return
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
        raise InitError(f"answers do not satisfy adopter-init-answers.schema.json: {exc.message}")


def _minimal_answers_check(data: dict) -> None:
    for key in ("adopter_name", "track", "intent_contract", "autonomy", "llm_roles", "eval"):
        if key not in data:
            raise InitError(f"answers missing required key: {key!r}")
    for role in ("research", "deliver", "dev", "review", "acceptance"):
        r = (data.get("llm_roles") or {}).get(role)
        if not isinstance(r, dict) or not all(k in r for k in ("harness", "provider", "model")):
            raise InitError(f"llm_roles.{role} must have harness/provider/model")
        if r["harness"] == "headless" and not (r.get("api_key_env") and (r.get("endpoint") or r.get("endpoint_env"))):
            raise InitError(f"headless role {role} requires api_key_env + endpoint/endpoint_env")


# --------------------------------------------------------------------------- #
# load_templates — the only reads for build_artifacts (keeps build_artifacts pure)
# --------------------------------------------------------------------------- #
def load_templates(framework_root: str) -> dict:
    """Read the framework template files build_artifacts fills. Pure inputs thereafter."""
    def _read(rel: str) -> str:
        with open(os.path.join(framework_root, rel), "r", encoding="utf-8") as fh:
            return fh.read()

    return {"charter": _read(os.path.join("templates", "mission-charter.yaml"))}


# --------------------------------------------------------------------------- #
# build_artifacts — PURE (design §4.3). No I/O, no network. (plan, templates) -> {relpath: text}
# --------------------------------------------------------------------------- #
def build_artifacts(plan: AdopterPlan, templates: dict) -> dict:
    artifacts: dict = {}
    artifacts["charter.yaml"] = _build_charter(plan, templates["charter"])
    artifacts["AGENTS.md"] = _build_agents_md(plan)

    harnesses = {r.harness for r in plan.llm_roles.values()}
    if "claude_code" in harnesses:
        artifacts["CLAUDE.md"] = "@AGENTS.md\n"
    if "cursor" in harnesses:
        artifacts[os.path.join(".cursor", "rules", "00-aidazi-governance.mdc")] = _CURSOR_RULE

    artifacts["docs/current/adoption-state.md"] = _build_adoption_state(plan)
    artifacts["docs/current/onboarding-record.md"] = _build_onboarding_record(plan)
    artifacts["docs/current/adoption-config.md"] = _build_adoption_config(plan)
    artifacts["docs/current/implementation-stack.md"] = _doc_stub(
        plan, "Implementation stack",
        "Adopter product/runtime stack snapshot (Step 4a). Fill with the concrete stack; this "
        "is distinct from the agent execution stack in charter.yaml `tooling`.")
    artifacts["docs/current/runtime_invariants.md"] = _doc_stub(
        plan, "Runtime invariants", "Load-bearing invariants the delivery loop must preserve.")
    artifacts["docs/current/domain_taxonomy.md"] = _doc_stub(
        plan, "Domain taxonomy", "The adopter's domain vocabulary and entity taxonomy.")
    artifacts["docs/current/agent_context_guide.md"] = _build_agent_context_guide(plan)

    brief_name = f"RB-001-{_slug(plan.adopter_name)}.md"
    artifacts[os.path.join("docs", "research-briefs", brief_name)] = _build_seed_brief(plan)

    artifacts["docs/requirements-ledger.json"] = _build_requirements_ledger(plan)
    artifacts[".gitignore"] = _GITIGNORE
    # keep the runtime control/audit dirs in the tree
    artifacts[os.path.join(".orchestrator", "control", ".gitkeep")] = ""
    artifacts[os.path.join(".orchestrator", "audit", ".gitkeep")] = ""
    return artifacts


# ---- charter (parse template -> mutate -> dump; fill-in-place, preserve required blocks) ---- #
def _build_charter(plan: AdopterPlan, template_text: str) -> str:
    charter = yaml.safe_load(template_text)
    charter["mission"]["id"] = plan.mission_id
    charter["mission"]["goal"] = plan.intent_goal

    scope = charter["autonomy"]["approved_scope"]
    scope["subsprint_sequence"] = list(plan.subsprint_sequence)
    scope["layers_allowed"] = list(plan.layers_allowed)
    scope["modules_in_scope"] = list(plan.modules_in_scope)
    if plan.explicitly_out_of_scope:
        scope["explicitly_out_of_scope"] = list(plan.explicitly_out_of_scope)
    else:
        scope.pop("explicitly_out_of_scope", None)
    charter["autonomy"]["level"] = plan.autonomy_level

    charter["budget"]["max_fix_rounds_total"] = plan.budget["max_fix_rounds_total"]
    charter["budget"]["max_wall_clock_minutes"] = plan.budget["max_wall_clock_minutes"]
    if "max_api_usd" in plan.budget:
        charter["budget"]["max_api_usd"] = plan.budget["max_api_usd"]

    for role, binding in plan.llm_roles.items():
        cfg = charter["tooling"][role]
        cfg["agent_kind"] = binding.harness  # legacy-required field mirrors harness
        cfg["harness"] = binding.harness
        cfg["provider"] = binding.provider
        cfg["model"] = binding.model
        if binding.capability_ref:
            cfg["capability_ref"] = binding.capability_ref
        # headless routing (NAMES only; values live in the adopter's .env.local)
        for key, val in (("endpoint", binding.endpoint), ("endpoint_env", binding.endpoint_env),
                         ("api_key_env", binding.api_key_env)):
            if val:
                cfg[key] = val
            else:
                cfg.pop(key, None)

    charter["tooling"]["eval"]["cmd"] = plan.eval_cmd
    charter["tooling"]["eval"]["timeout_seconds"] = plan.eval_timeout

    # intent_contract (I3: confirmed flag from plan only; the engine never auto-confirms).
    charter["intent_contract"] = {
        "goal": plan.intent_goal,
        "standard": plan.intent_standard,
        "proof_of_done": plan.intent_proof,
        "confirmed_by_human": plan.intent_confirmed,
        "confirmed_at": plan.intent_confirmed_at,
    }

    header = (
        f"# Mission charter for {plan.adopter_name} — generated by adopter_init.py\n"
        f"# Schema: aidazi/schemas/mission-charter.schema.json. Fill/tune values as the project\n"
        f"# evolves; the 9 MANDATORY_CHECKPOINTS and acceptance authority MUST NOT be bypassed.\n"
    )
    return header + yaml.safe_dump(charter, sort_keys=False, allow_unicode=True, width=100)


# ---- AGENTS.md (modeled on examples/minimal-greenfield/AGENTS.md; aidazi/ mount) ---- #
def _build_agents_md(plan: AdopterPlan) -> str:
    return f"""# AGENTS.md — {plan.adopter_name} (aidazi consumer)

Generated by `adopter_init.py`. A fresh coding-agent session reads this first at cold-start.
By default it is a lightweight Control Plane Session, not one of the five delivery roles.

## §1 Project identification

```yaml
project_name: {plan.adopter_name}
adopter_track: {plan.track}
framework_version: {FRAMEWORK_VERSION}
charter_path: ./charter.yaml
```

## §2 Framework governance chain (role/on-demand load)

Default Control Plane Sessions do not `@`-include the full governance chain. When a session is
explicitly activated as a role session, load these in order:

1. `aidazi/governance/constitution-core.md` (always-load kernel; full `aidazi/governance/constitution.md` on-demand per its triggers)
2. `aidazi/governance/authoring-kernel.md` (always-load kernel; full `aidazi/governance/doc_governance.md` on-demand per context_briefing §2.6)
3. `aidazi/governance/context_briefing.md`

Then the session loads its role card from `aidazi/role-cards/`.

## §3A Default Control Plane Session

When the human has not explicitly activated a role, the session classifies the natural-language
request, records the interpreted intent, reads the small control state index, and dispatches or
prepares the correct role/runner path. It is not a sixth role and does not sign role artifacts.

```control-plane-load
allow:
  - AGENTS.md
  - .orchestrator/control/state.json
  - .orchestrator/control/intents.jsonl
  - .orchestrator/control/roadmap-state.json
  - .orchestrator/control/roadmap-mutations.jsonl
  - .orchestrator/control/checkpoints-index.json
  - charter.yaml
  - docs/current/adoption-state.md
  - docs/current/agent_context_guide.md
on_demand:
  - aidazi/process/control-plane-routing.md
  - aidazi/schemas/control-plane-intent.schema.json
  - aidazi/schemas/control-plane-state.schema.json
  - aidazi/schemas/roadmap-state.schema.json
  - aidazi/schemas/roadmap-mutation.schema.json
forbid:
  - aidazi/role-cards/**
  - aidazi/process/delivery-loop.md
  - aidazi/process/campaign-loop.md
  - docs/action_bank.md
  - docs/handoff.md
  - docs/10-handoff.md
  - docs/research-briefs/**
  - docs/proposals/**
  - docs/sprints/**
  - .orchestrator/audit/**
  - .runs/**
  - eval/runs/**
```

## §3 Adopter-side state ledgers (load at cold-start)

@./docs/current/adoption-state.md          — per-Δ status; override registry
@./docs/current/agent_context_guide.md     — per-task reading lists

Runtime invariants and domain taxonomy are role/on-demand context, not default Control Plane context.

## §4 5-role chain registry

This project instantiates all 5 roles per `charter.yaml` `tooling`. The default Control Plane
Session helps the human decide which role prompt to launch next. See `charter.yaml` for each
role's harness/provider/model binding.

## §5 Two-loop discipline

This project uses the **Delivery Loop** (Concept 2). If an Auto Loop is added later it is named
distinctly per §1.7-E.

## §6 Adopter-specific overrides

See `docs/current/adoption-state.md`. We diverge from nothing in the §1.7 hard set.

## §7 Cold-start read order

Default Control Plane: this file → `.orchestrator/control/state.json` if present →
`docs/current/adoption-state.md` + `docs/current/agent_context_guide.md`.

Explicit role session: this file → `aidazi/governance/constitution-core.md` →
`aidazi/governance/authoring-kernel.md` → `aidazi/governance/context_briefing.md` →
`docs/current/adoption-state.md` → the relevant role card (the always-load kernel trio; full
`constitution.md` / `doc_governance.md` load on-demand per their triggers).

---

End of AGENTS.md.
"""


_CURSOR_RULE = """---
description: aidazi governance — load AGENTS.md at session start
alwaysApply: true
---
This repository is governed by the aidazi delivery engine. At the start of every session,
load ./AGENTS.md and follow its control-plane load directive before doing any work.
"""

_GITIGNORE = """# aidazi runtime + secrets (adopter_init.py)
.orchestrator/
.runs/
.env.local
*.local
.gate/
__pycache__/
"""


def _build_adoption_state(plan: AdopterPlan) -> str:
    harnesses = sorted({r.harness for r in plan.llm_roles.values()
                        if r.harness in ("claude_code", "codex", "cursor")})
    pin = ", ".join(harnesses) if harnesses else "claude_code"
    return f"""---
title: Adoption state — {plan.adopter_name}
doc_tier: adopter-state
doc_category: live
status: current
---

<!-- adopter-root-harness: {pin} -->

# Adoption state — {plan.adopter_name}

Track: `{plan.track}`. Generated by `adopter_init.py`.

## Override / divergence registry

No divergences from the §1.7 hard set. Per-Δ status is recorded here as the project evolves.
"""


def _build_onboarding_record(plan: AdopterPlan) -> str:
    lines = [
        f"# Onboarding record — {plan.adopter_name}", "",
        "Audit ledger of the `adopter_init.py` bootstrap run.", "",
        "| Step | Result |", "|---|---|",
        "| Scaffold artifacts | generated |",
        f"| Intent contract confirmed_by_human | {str(plan.intent_confirmed).lower()} |",
        f"| Seed brief gate-1 confirmed_by_human | {str(plan.brief_confirmed).lower()} |",
        "| Reachability probe | off (Cluster-2 offline scaffold) |",
        "| Exit validators | see docs/current/adoption-readiness.md |",
    ]
    return "\n".join(lines) + "\n"


def _build_adoption_config(plan: AdopterPlan) -> str:
    return _doc_stub(
        plan, "Adoption config",
        "What is configurable and where (charter.yaml for role bindings/autonomy/budgets; "
        "docs/current/adoption-state.md for overrides). Generated by adopter_init.py.")


def _build_agent_context_guide(plan: AdopterPlan) -> str:
    return _doc_stub(
        plan, "Agent context guide",
        "Per-task reading lists for role sessions. Start from the role card under "
        "`aidazi/role-cards/` plus this project's `docs/current/*` domain contracts.")


def _doc_stub(plan: AdopterPlan, title: str, body: str) -> str:
    return f"# {title} — {plan.adopter_name}\n\n{body}\n"


def _build_seed_brief(plan: AdopterPlan) -> str:
    # I3: the confirmed_by_human token is emitted ONLY when the human/answers confirmed gate-1.
    lines = [
        "---",
        f"id: RB-001",
        f"title: {plan.brief_title}",
        f"customer_signed: {str(plan.brief_customer_signed).lower()}",
    ]
    if plan.brief_confirmed:
        lines.append("confirmed_by_human: true")
    else:
        lines.append("confirmed_by_human: false")
    lines += [
        "---", "",
        f"# {plan.brief_title}", "",
        "## Closure contract (goal / standard / proof-of-done)", "",
        f"- **Goal:** {plan.intent_goal}",
        f"- **Standard:** {plan.intent_standard}",
        f"- **Proof of done:** {plan.intent_proof}", "",
        "## Summary", "",
        plan.brief_summary, "",
    ]
    if not plan.brief_confirmed:
        lines += [
            "> NOTE: gate-1 is NOT signed (`confirmed_by_human: false`). The adopter is not yet "
            "GREEN on the signed-brief check — the human must review and sign this brief.", ""]
    return "\n".join(lines)


def _build_requirements_ledger(plan: AdopterPlan) -> str:
    ledger = {
        "schema_version": "requirement-ledger.v1",
        "project": plan.adopter_name,
        "requirements": [],
        "notes": "Seed ledger generated by adopter_init.py (OW-2/OW-3 default-on). Add PRD-derived "
                 "requirement entries; user-facing entries force functional_acceptance: browser_e2e.",
    }
    return json.dumps(ledger, indent=2) + "\n"


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "adopter"


# --------------------------------------------------------------------------- #
# I2 guard + materialize (the writers)
# --------------------------------------------------------------------------- #
def assert_writable_dest(dest: str, framework_root: str) -> None:
    """Refuse (InitError -> exit 3) a dest that IS the framework repo, or is nested inside /
    contains framework_root. Runs BEFORE any write (design §2 I2 / R0 B-4)."""
    dest_real = os.path.realpath(dest)
    fr_real = os.path.realpath(framework_root)
    if os.path.isdir(dest) and adoption_status.is_framework_repo(dest):
        raise InitError(f"refusing: {dest!r} looks like the aidazi framework repo itself")
    if dest_real == fr_real:
        raise InitError("refusing: dest is the framework root")
    if dest_real.startswith(fr_real + os.sep):
        raise InitError(f"refusing: dest {dest!r} is nested inside the framework tree {fr_real!r}")
    if fr_real.startswith(dest_real + os.sep):
        raise InitError(f"refusing: framework tree {fr_real!r} is nested inside dest {dest!r} "
                        "(would copy into itself)")


def materialize(artifacts: dict, dest: str, framework_root: str, *, force: bool = False,
                overwrite: bool = False) -> None:
    """The ONLY writer of the artifact tree. Guards the dest first (I2), writes each artifact
    (tmp+rename), and mounts the framework tree under <dest>/aidazi/."""
    assert_writable_dest(dest, framework_root)
    if os.path.isdir(dest) and os.listdir(dest) and not force:
        raise InitError(f"dest {dest!r} is non-empty; pass --force for a brownfield adopter")
    os.makedirs(dest, exist_ok=True)

    _HUMAN_EDITABLE = ("charter.yaml",)  # never clobber without --overwrite
    for rel, content in sorted(artifacts.items()):
        target = os.path.join(dest, rel)
        if os.path.exists(target) and rel.startswith(_HUMAN_EDITABLE) and not overwrite:
            continue  # idempotent: preserve a human-edited charter unless --overwrite
        if os.path.exists(target) and _read_text(target) == content:
            continue  # idempotent: no spurious rewrite
        _atomic_write(target, content)

    _mount_framework(dest, framework_root)


def _mount_framework(dest: str, framework_root: str) -> None:
    aidazi_dir = os.path.join(dest, "aidazi")
    for sub in FRAMEWORK_MOUNT_DIRS:
        src = os.path.join(framework_root, sub)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(aidazi_dir, sub)
        if os.path.isdir(dst):
            continue  # idempotent: already mounted
        shutil.copytree(src, dst, ignore=_COPY_IGNORE)


def _atomic_write(target: str, content: str) -> None:
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, target)


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


# --------------------------------------------------------------------------- #
# run_exit_validators — the four validators + --write-readiness (design §4.2)
# --------------------------------------------------------------------------- #
def run_exit_validators(dest: str) -> dict:
    """Run the four adoption validators against dest, writing the readiness snapshot (the
    chicken-and-egg §1.2). Returns {name: (ok, detail)} + an aggregate 'green' bool."""
    results = {}
    charter_path = os.path.join(dest, "charter.yaml")
    cr = charter_validator.validate_file(charter_path)
    results["charter_validator"] = (cr.ok, f"{len(cr.errors)} error(s)")

    wr = adopter_wiring_validator.validate_root(dest)
    results["adopter_wiring_validator"] = (wr.ok, f"{len(wr.errors)} error(s); targets={wr.targets}")

    cp = control_plane_validator.validate_root(dest)
    results["control_plane_validator"] = (cp.ok, f"{len(cp.errors)} error(s)")

    # write the readiness snapshot (a REQUIRED file produced by --write-readiness), then
    # re-run the aggregate so the snapshot is counted.
    readiness = os.path.join(dest, "docs", "current", "adoption-readiness.md")
    pre = adoption_status.validate_adoption(dest)
    adoption_status.write_readiness_snapshot(pre, readiness)
    status = adoption_status.validate_adoption(dest)
    results["adoption_status"] = (status.ok, "" if status.ok else "see remediation below")

    green = status.ok
    return {"results": results, "green": green, "status_render": status.render()}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _artifact_manifest(artifacts: dict) -> str:
    return "\n".join(f"  {rel}" for rel in sorted(artifacts)) + \
        f"\n  aidazi/ (framework mount: {', '.join(FRAMEWORK_MOUNT_DIRS)})"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold a new aidazi adopter to four-validator GREEN from an answers file.")
    parser.add_argument("dest", help="target adopter directory (created if absent)")
    parser.add_argument("--answers", required=True, help="path to answers.json (schema §7.1)")
    parser.add_argument("--framework-root", default=None,
                        help="framework source root (default: derived from this file's location)")
    parser.add_argument("--force", action="store_true",
                        help="allow a non-empty dest (brownfield)")
    parser.add_argument("--overwrite", action="store_true",
                        help="allow replacing an existing human-editable artifact (charter.yaml)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the artifact manifest and exit; write nothing")
    parser.add_argument("--probe", choices=["off"], default="off",
                        help="reachability probe depth (Cluster 2 supports only 'off')")
    args = parser.parse_args(argv)

    framework_root = os.path.abspath(args.framework_root or _FRAMEWORK_ROOT_DEFAULT)
    try:
        plan = load_answers(args.answers, framework_root)
        templates = load_templates(framework_root)
        artifacts = build_artifacts(plan, templates)
        if args.dry_run:
            sys.stdout.write("Artifact manifest (dry-run; nothing written):\n")
            sys.stdout.write(_artifact_manifest(artifacts) + "\n")
            return 0
        # Guard BEFORE any write (I2).
        assert_writable_dest(args.dest, framework_root)
        materialize(artifacts, args.dest, framework_root, force=args.force, overwrite=args.overwrite)
    except InitError as exc:
        sys.stderr.write(f"[adopter_init] REFUSED: {exc}\n")
        return 3

    outcome = run_exit_validators(args.dest)
    sys.stdout.write(f"\nadopter_init: scaffolded {args.dest}\n\n")
    for name, (ok, detail) in outcome["results"].items():
        sys.stdout.write(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}\n")
    if outcome["green"]:
        sys.stdout.write("\nAll four validators GREEN. Next: review charter.yaml + sign the "
                         "research brief, then run the first loop.\n")
        return 0
    sys.stdout.write("\nNOT green — remediation:\n" + outcome["status_render"] + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
