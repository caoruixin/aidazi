#!/usr/bin/env python3
"""WP-4 Acceptance LOAD-CLOSURE harness (build-time, read-only).

The ACCEPTANCE LOAD-CLOSURE invariant (context/token-optimization design §E, Codex R3): EVERY file
an Acceptance session can load — proactive cold-start, conditional, or on-demand — must be exactly
one of
  (a) INLINED      — embedded in the projected Acceptance prompt / acceptance-kernel, so it is never
                     read as a separate file;
  (b) RESOLVER_BOUND — bound in the driver's ``_acceptance_resolver_graph`` so a content change
                     re-invalidates the §3.5b reuse hash (``acceptance_input_hash``); or
  (c) HALT_ROUTED  — an insufficient projection routes to the resumable refinement HALT
                     (``_acceptance_spec_refine_halt``) rather than reading unbound bytes.
No verdict-affecting Acceptance input may be an UNBOUND on-demand read. WP-7's ``load_graph_hash`` is
audit-only and explicitly does NOT satisfy this (it is not the §3.5b reuse hash).

This module is the THREE-LAYER proof of that invariant (Q2):
  Layer (a) MANIFEST     — a checked-in enumeration (``_acceptance_load_manifest.yaml``) of every
                           Acceptance-reachable load entry = {source, region, parse_token, target,
                           disposition, evidence}; ``check_manifest_wellformed``.
  Layer (b) DRIFT-GUARD  — ``parse_reachable_loads`` re-parses the source files (the role card's
                           cold-start §1 + §11, context_briefing §6) for "Load X" instructions and
                           asserts BIDIRECTIONAL set-equality with the manifest's parse tokens
                           (catches a NEW load instruction AND a stale manifest entry).
  Layer (c) CROSS-CHECK  — ``check_live_crosscheck`` verifies each disposition holds against the
                           live code: RESOLVER_BOUND targets are actually bound in
                           ``_acceptance_resolver_graph`` (statically parsed); HALT_ROUTED names the
                           real ``_acceptance_spec_refine_halt`` sentinel path; INLINED targets are
                           the files the acceptance-kernel coverage gate proves carried, and (WP-4B)
                           embedded in the projected prompt.

WP-4A STATE (UNWIRED). The kernel is authored + proven, but it is NOT yet embedded into the projected
prompt and the delivery-loop / role-skill-model triggers are NOT yet retired (that is WP-4B). So the
STRICT closure assertion is NOT satisfiable yet: ``closure_state`` reports the exact pending set, and
the test suite asserts that pending set explicitly (green) while the strict assertion is an
``expectedFailure``. This module NEVER mutates runtime to force green.

Read-only: reads YAML/source text + recomputes hashes; no LLM, no network, no spawn.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a hard dependency
    yaml = None

HERE = Path(__file__).resolve()
REPO_ROOT_DEFAULT = HERE.parents[2]  # parent of engine-kit
MANIFEST_NAME = "_acceptance_load_manifest.yaml"
MANIFEST_DIR = ("engine-kit", "tools", "constraint-inventory")

VALID_DISPOSITIONS = {"INLINED", "RESOLVER_BOUND", "HALT_ROUTED"}
# The two whole-file reads WP-4B retires as Acceptance loads (their content is INLINED into the
# acceptance-kernel; see _acceptance_kernel_coverage.yaml). Listed here so the harness can report
# whether their triggers are still live (the WP-4A pending set).
RETIRED_FILES = ("process/delivery-loop.md", "process/role-skill-model.md")


# --------------------------------------------------------------------------- #
# Layer (b): parse the Acceptance-reachable "Load X" instructions from source.
# --------------------------------------------------------------------------- #
def _section(text: str, start_re: str, end_re: str) -> str:
    s = re.search(start_re, text)
    if not s:
        return ""
    rest = text[s.end():]
    e = re.search(end_re, rest)
    return rest[:e.start()] if e else rest


def _backtick_paths(seg: str) -> list:
    """Backtick tokens in ``seg`` that name a governed/process/data FILE (a path-shaped token, or a
    bare canonical governance filename the role card abbreviates)."""
    out = []
    for t in re.findall(r"`([^`]+)`", seg):
        t = t.strip()
        if re.search(r"\.(md|json|ya?ml)(\b|$)", t) or t in ("constitution.md", "doc_governance.md"):
            out.append(t)
    return out


def parse_reachable_loads(repo_root=REPO_ROOT_DEFAULT) -> set:
    """Re-parse the source files for the Acceptance session's "Load X" instructions and return a set
    of ``(region, token)`` pairs (verbatim backtick token). DETERMINISTIC; the manifest declares the
    same set (layer b bidirectional guard).

    Regions:
      - ``acceptance_cold_start`` — every file-path backtick token in role-cards/acceptance-agent.md
        §1 (the cold-start load list is a pure list of files to load).
      - ``acceptance_role_skill`` — process/role-skill-model.md from §11 (the conditional skill load).
      - ``context_briefing_delivery_loop`` — the OBJECT of the "Load X" instruction in
        context_briefing §6 (the trigger header), NOT the trigger-condition file mentions in its
        bullets.
    """
    repo_root = Path(repo_root)
    rc = (repo_root / "role-cards" / "acceptance-agent.md").read_text(encoding="utf-8")
    cb = (repo_root / "governance" / "context_briefing.md").read_text(encoding="utf-8")
    pairs = set()

    s1 = _section(rc, r"## §1 Cold-start activation", r"\n## §2")
    for tok in _backtick_paths(s1):
        pairs.add(("acceptance_cold_start", tok))

    s11 = _section(rc, r"## §11 ", r"\nEnd of Acceptance")
    # Catch-all: a "Load `<path>`" instruction added ELSEWHERE in the role card (not the §1 cold-start
    # list or the §11 skill load) must not escape the drift-guard. Scan the rest of the card for any
    # line that instructs a load and names a backtick file path (Codex R8-B1). Empty today — its value
    # is that adding such a line anywhere makes check_bidirectional fail until the manifest classifies it.
    other = rc.replace(s1, "").replace(s11, "")
    for line in other.splitlines():
        if re.search(r"[Ll]oad\b", line):
            for tok in _backtick_paths(line):
                pairs.add(("acceptance_role_card_other", tok))
    # §11 names the file once ("Per `process/role-skill-model.md` (load it if ...skills... non-empty)")
    # — a conditional load, captured only when the skills-gated load instruction is present.
    if re.search(r"load it if[^\n]*tooling\.acceptance\.skills", s11):
        for tok in _backtick_paths(s11):
            if tok.endswith("role-skill-model.md"):
                pairs.add(("acceptance_role_skill", tok))

    # context_briefing §2.5 is the SECOND Acceptance cold-start load region (a per-role briefing list
    # parallel to role-card §1). Extract the load object of each bullet that STARTS with a backtick
    # path ("- `aidazi/...` — desc"); prose §-citations like "per `process/delivery-loop.md` §4.2.6"
    # are not bullet-leading load paths and are correctly excluded.
    s25 = _section(cb, r"### §2\.5 Acceptance Agent", r"\n### §2\.6")
    for line in s25.splitlines():
        m = re.match(r"\s*-\s+`([^`]+)`", line)
        if m and _backtick_paths("`" + m.group(1) + "`"):
            pairs.add(("context_briefing_acceptance_role", m.group(1).strip()))

    s6 = _section(cb, r"## §6 .*Delivery Loop trigger", r"\n## §7")
    m = re.search(r"Load\s+`([^`]+)`", s6)  # the trigger HEADER's load object only
    if m:
        pairs.add(("context_briefing_delivery_loop", m.group(1).strip()))
    return pairs


# --------------------------------------------------------------------------- #
# Layer (c): statically extract the rels bound by _acceptance_resolver_graph.
# --------------------------------------------------------------------------- #
def _driver_source(repo_root: Path) -> str:
    return (repo_root / "engine-kit" / "orchestrator" / "driver.py").read_text(encoding="utf-8")


def _method_source(driver_src: str, name: str) -> str:
    """The source text of a single ``def <name>(...)`` method body (up to the next top-level method),
    extracted statically (no import / driver construction)."""
    m = re.search(r"\n    def " + re.escape(name) + r"\(.*?(?=\n    def )", driver_src, re.S)
    return m.group(0) if m else ""


def _resolver_source(repo_root: Path) -> str:
    return _method_source(_driver_source(Path(repo_root)), "_acceptance_resolver_graph")


def resolver_bound_rels(repo_root=REPO_ROOT_DEFAULT) -> set:
    """The set of repo-relative paths ``_acceptance_resolver_graph`` binds, extracted STATICALLY
    (no driver construction): every ``os.path.join("a", "b", ...)`` joined to ``a/b/...`` plus every
    double-quoted string literal in the function body. Used to verify RESOLVER_BOUND manifest targets
    are really bound (a content change to any of them moves ``acceptance_input_hash``)."""
    body = _resolver_source(Path(repo_root))
    rels = set()
    # (1) os.path.join("a", "b", ...) → "a/b/..." — the COMPUTED rel of the governance for-loop and
    #     the literal-arg entries (the for-loop assigns rel = os.path.join(...).replace(os.sep, "/")).
    #     Only join when EVERY arg is a string literal; a call with a variable arg (e.g. a per-run
    #     path) is not a stable rel and is dropped.
    for m in re.finditer(r"os\.path\.join\(\s*([^)]*?)\)", body, re.S):
        args = [a.strip() for a in m.group(1).split(",") if a.strip()]
        if args and all(a.startswith('"') and a.endswith('"') for a in args):
            rels.add("/".join(a[1:-1] for a in args))
    # (2) Explicit `"rel": "<literal>"` entry fields ONLY — NOT every quoted string in the function
    #     (which would include os.path.join arg FRAGMENTS like "acceptance-agent.md" or "governance",
    #     laundering a bogus RESOLVER_BOUND target — Codex R6-B2). Variable rels (`"rel": evidence_path`)
    #     are per-run paths, intentionally not stable literals; their binding is asserted by PURPOSE.
    rels.update(re.findall(r'"rel"\s*:\s*"([^"]+)"', body))
    return rels


def resolver_purposes(repo_root=REPO_ROOT_DEFAULT) -> set:
    """The exact set of ``"purpose": "<literal>"`` values the resolver tags its entries with — the
    only valid right-hand sides for a ``data:<purpose>`` manifest target. Exact membership (not a
    substring of the function body) so a bogus ``data:path`` / ``data:mandatory`` cannot pass
    (Codex R6-B2)."""
    return set(re.findall(r'"purpose"\s*:\s*"([^"]+)"', _resolver_source(Path(repo_root))))


# --------------------------------------------------------------------------- #
# Manifest load + the three layers.
# --------------------------------------------------------------------------- #
def load_manifest(repo_root=REPO_ROOT_DEFAULT) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is required but not installed")
    p = Path(repo_root).joinpath(*MANIFEST_DIR, MANIFEST_NAME)
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def check_manifest_wellformed(manifest: dict) -> list:
    """Layer (a): every entry has a source + a valid disposition; each disposition carries the
    machine-checkable evidence its cross-check needs; parse_tokens are unique."""
    errors = []
    entries = manifest.get("entries") or []
    if not entries:
        return ["manifest has no entries"]
    seen_parse = {}
    for i, e in enumerate(entries):
        tag = e.get("source", f"entry[{i}]")
        disp = e.get("disposition")
        if disp not in VALID_DISPOSITIONS:
            errors.append(f"{tag}: invalid disposition {disp!r} (expected {sorted(VALID_DISPOSITIONS)})")
        if not e.get("source"):
            errors.append(f"entry[{i}]: missing 'source'")
        if not e.get("evidence"):
            errors.append(f"{tag}: missing 'evidence'")
        pk = e.get("parse_token")
        if pk is not None:
            key = (e.get("region"), pk)
            if e.get("region") is None:
                errors.append(f"{tag}: parse_token set but no 'region'")
            if key in seen_parse:
                errors.append(f"{tag}: duplicate parse_token {key!r} (also {seen_parse[key]})")
            seen_parse[key] = tag
        if disp == "RESOLVER_BOUND" and not e.get("target"):
            errors.append(f"{tag}: RESOLVER_BOUND requires a 'target'")
        if disp == "INLINED" and not e.get("target"):
            errors.append(f"{tag}: INLINED requires a 'target' (the file whose content is inlined)")
    return errors


def check_bidirectional(manifest: dict, repo_root=REPO_ROOT_DEFAULT) -> list:
    """Layer (b): the manifest's parse-token set == the parser's extracted set (both directions)."""
    parsed = parse_reachable_loads(repo_root)
    declared = {(e.get("region"), e.get("parse_token"))
                for e in (manifest.get("entries") or []) if e.get("parse_token") is not None}
    errors = []
    for missing in sorted(parsed - declared):
        errors.append(f"parser found a load instruction NOT in the manifest (new unclassified "
                      f"Acceptance load?): {missing}")
    for stale in sorted(declared - parsed):
        errors.append(f"manifest declares a parse_token the parser no longer finds (stale): {stale}")
    return errors


def check_live_crosscheck(manifest: dict, repo_root=REPO_ROOT_DEFAULT) -> list:
    """Layer (c): each disposition holds against the live code. Entries flagged
    ``status: pending_wp4b`` are SKIPPED — their target disposition is not true yet (the WP-4A
    unwired state); ``closure_state`` tracks them and the strict closure test asserts they are
    resolved. This validates only the dispositions that ALREADY hold."""
    errors = []
    repo_root = Path(repo_root)
    bound = resolver_bound_rels(repo_root)
    purposes = resolver_purposes(repo_root)
    driver_src = _driver_source(repo_root)
    for e in (manifest.get("entries") or []):
        if e.get("status") == "pending_wp4b":
            continue
        tag = e.get("source", "?")
        disp = e.get("disposition")
        target = e.get("target")
        if disp == "RESOLVER_BOUND":
            # Concrete governance/process/role-card/schema targets must appear in the resolver body.
            # Data/dynamic targets (purpose markers like "data:f5_evidence") are bound via a path
            # variable; we verify the purpose string instead of a literal rel.
            if isinstance(target, str) and target.startswith("data:"):
                purpose = target.split(":", 1)[1]
                if purpose not in purposes:
                    errors.append(f"{tag}: RESOLVER_BOUND data purpose {purpose!r} is not an actual "
                                  f"\"purpose\" tag in _acceptance_resolver_graph (valid: "
                                  f"{sorted(purposes)})")
            elif target not in bound:
                errors.append(f"{tag}: RESOLVER_BOUND target {target!r} is NOT bound in "
                              f"_acceptance_resolver_graph (resolver rels do not include it)")
        elif disp == "HALT_ROUTED":
            # Prove the route is REAL + WIRED, not merely that the sentinel string exists: the
            # target method (a) is defined, (b) RETURNS the _ACCEPTANCE_SPEC_HALT sentinel, and
            # (c) is actually invoked by _resolve_acceptance_spec (the path an insufficient
            # projection takes). A broken HALT route must fail the gate, not pass on a stray string.
            method = target if isinstance(target, str) else "_acceptance_spec_refine_halt"
            body = _method_source(driver_src, method)
            if not body:
                errors.append(f"{tag}: HALT_ROUTED target method {method!r} is not defined in driver.py")
            elif "return _ACCEPTANCE_SPEC_HALT" not in body:
                errors.append(f"{tag}: HALT_ROUTED method {method!r} does not return the "
                              f"_ACCEPTANCE_SPEC_HALT sentinel")
            elif method not in _method_source(driver_src, "_resolve_acceptance_spec"):
                errors.append(f"{tag}: HALT_ROUTED method {method!r} is not invoked by "
                              f"_resolve_acceptance_spec (the insufficiency route is not wired)")
        elif disp == "INLINED":
            # The kernel must carry the inlined file's Acceptance content (proven by the
            # acceptance-kernel coverage gate). The WP-4B embed-in-prompt check is asserted by the
            # strict closure test (expectedFailure until WP-4B), so do not duplicate it here.
            if not (repo_root / "governance" / "acceptance-kernel.md").is_file():
                errors.append(f"{tag}: INLINED but governance/acceptance-kernel.md is absent")
    return errors


# --------------------------------------------------------------------------- #
# Current (WP-4A, unwired) closure state — drives the known-pending test.
# --------------------------------------------------------------------------- #
def _kernel_embedded_in_prompt(repo_root: Path) -> bool:
    """True once WP-4B embeds the acceptance-kernel into the projected prompt. WP-4A: the projected
    prompt (driver._project_acceptance_prompt) does NOT reference the kernel yet."""
    src = (repo_root / "engine-kit" / "orchestrator" / "driver.py").read_text(encoding="utf-8")
    m = re.search(r"\n    def _project_acceptance_prompt\(.*?(?=\n    def )", src, re.S)
    return bool(m) and "acceptance-kernel" in m.group(0)


def closure_state(repo_root=REPO_ROOT_DEFAULT) -> dict:
    """Report the CURRENT closure state so the test suite can assert the exact WP-4A pending set
    explicitly. ``pending`` is empty iff FULL closure holds (the WP-4B end state).

    Derived from the manifest: every entry flagged ``status: pending_wp4b`` is a load whose TARGET
    disposition (INLINED-and-retired, or newly RESOLVER_BOUND) is not yet applied — i.e. still an
    unbound / not-yet-inlined verdict-affecting read. The kernel-not-embedded gap is also pending
    until WP-4B embeds the kernel into the projected prompt. For transparency this also records,
    per RETIRED_FILES, whether the whole-file load trigger is still live and whether it is bound."""
    repo_root = Path(repo_root)
    manifest = load_manifest(repo_root)
    bound = resolver_bound_rels(repo_root)
    parsed_tokens = {tok for _, tok in parse_reachable_loads(repo_root)}

    pending = []
    for e in (manifest.get("entries") or []):
        if e.get("status") == "pending_wp4b":
            pending.append({"source": e.get("source"), "target": e.get("target"),
                            "disposition": e.get("disposition"),
                            "reason": e.get("evidence")})
    embedded = _kernel_embedded_in_prompt(repo_root)
    if not embedded:
        pending.append({"source": "driver:_project_acceptance_prompt",
                        "target": "governance/acceptance-kernel.md", "disposition": "INLINED",
                        "reason": "kernel authored + proven but NOT embedded into the projected prompt"})

    retired = {f: {"trigger_live": any(tok.endswith(f.split("/")[-1]) for tok in parsed_tokens),
                   "resolver_bound": f in bound}
               for f in RETIRED_FILES}
    return {"closed": not pending, "kernel_embedded": embedded,
            "pending": pending, "retired_files": retired}


def check_all(repo_root=REPO_ROOT_DEFAULT) -> dict:
    """Run layers (a)+(b)+(c). These pass in WP-4A for the dispositions that ALREADY hold; the
    pending_wp4b transitions + the kernel embed are reported by ``closure_state`` (NOT forced green)."""
    manifest = load_manifest(repo_root)
    errors = (check_manifest_wellformed(manifest)
              + check_bidirectional(manifest, repo_root)
              + check_live_crosscheck(manifest, repo_root))
    return {"ok": not errors, "errors": errors,
            "closure_state": closure_state(repo_root)}


if __name__ == "__main__":  # pragma: no cover - manual invocation
    import json
    import sys
    res = check_all()
    print(json.dumps(res, indent=2, ensure_ascii=False))
    raise SystemExit(0 if res["ok"] else 1)
