"""charter_compat — acceptance namespace + mode normalization (P-A).

Pure, dependency-free charter migration shared by the runtime Driver
(`orchestrator/driver.py`) and the charter validator
(`validators/charter_validator.py`). It runs BEFORE JSON-schema validation and
before the Driver reads any acceptance config, so all downstream reads are
**canonical-only** (no per-read fallback).

Canonical home for acceptance config is ``charter.tooling.acceptance.*`` (the JSON
schema's home). Two legacy shapes are normalized IN PLACE:

  1. a top-level ``charter.acceptance`` block (the driver-era split, which the
     schema's root ``additionalProperties: false`` would otherwise reject) → moved
     under ``charter.tooling.acceptance`` (a value already present under tooling
     wins; a genuine value conflict is an error, never a silent pick);
  2. the deprecated boolean ``tooling.acceptance.enabled`` → the new
     ``tooling.acceptance.mode`` (``true→"auto"``, ``false→"off"``) when ``mode``
     is absent. When BOTH are present they must agree
     (``enabled:true ↔ mode∈{advisory,auto}``, ``enabled:false ↔ mode:off``);
     disagreement is an error.

Returns ``(warnings, errors)`` as plain string lists. The validator maps them to a
Report; the Driver audits the warnings and treats any error as a fatal config
error at construction. Design: archive/2026-06-20-autonomous-delivery-design.md §1.4.
"""
from __future__ import annotations

from typing import Any

# Acceptance run modes (design §3.1/§3.2):
#   off       — acceptance does not run (the legacy `enabled: false` behavior).
#   advisory  — acceptance runs; a `pass` NEVER auto-ships (human signs off).
#   auto      — acceptance runs; a `pass` auto-ships ONLY when authoritative
#               (calibrated + fully_autonomous_within_budget); else advisory.
ACCEPTANCE_MODES: tuple[str, ...] = ("off", "advisory", "auto")
_TRUE_MODES: tuple[str, ...] = ("advisory", "auto")


def normalize_acceptance(charter: Any) -> tuple[list[str], list[str]]:
    """Normalize the acceptance namespace + mode IN PLACE. Returns (warnings,
    errors). A non-dict charter is left untouched (the schema validator reports
    the structural error separately)."""
    warnings: list[str] = []
    errors: list[str] = []
    if not isinstance(charter, dict):
        return warnings, errors

    # 1. Move a legacy top-level `acceptance` block under tooling.acceptance.
    top = charter.get("acceptance")
    if isinstance(top, dict):
        tooling = charter.get("tooling")
        if tooling is None:
            tooling = {}
            charter["tooling"] = tooling
        elif not isinstance(tooling, dict):
            # Present but malformed — do NOT overwrite it (that would HIDE the
            # structural error and let a malformed charter validate). Flag it and
            # stop; schema validation reports the structural issue too.
            errors.append(
                "charter.tooling must be a mapping to migrate the deprecated "
                "top-level `acceptance` block under it")
            return warnings, errors
        dst = tooling.get("acceptance")
        if dst is None:
            dst = {}
            tooling["acceptance"] = dst
        elif not isinstance(dst, dict):
            errors.append(
                "charter.tooling.acceptance must be a mapping to merge the "
                "deprecated top-level `acceptance` block")
            return warnings, errors
        for k, v in top.items():
            if k in dst and dst[k] != v:
                errors.append(
                    f"acceptance.{k} conflicts: top-level `{v!r}` vs "
                    f"tooling.acceptance `{dst[k]!r}`; remove the deprecated "
                    f"top-level `acceptance` block")
            else:
                dst.setdefault(k, v)
        del charter["acceptance"]
        warnings.append(
            "charter_namespace_deprecated: top-level `acceptance` block moved "
            "under `tooling.acceptance` (canonical); update the charter to put "
            "acceptance config under tooling.acceptance")

    tooling = charter.get("tooling")
    acc = tooling.get("acceptance") if isinstance(tooling, dict) else None
    if not isinstance(acc, dict):
        # No canonical acceptance mapping to normalize (absent, or a malformed
        # non-dict `tooling`/`tooling.acceptance`). Return cleanly — never raise;
        # schema validation reports any structural error.
        return warnings, errors

    # 2. Derive `mode` from the deprecated `enabled` alias / apply the conflict rule.
    has_enabled = "enabled" in acc
    has_mode = "mode" in acc
    if has_mode and acc.get("mode") not in ACCEPTANCE_MODES:
        errors.append(
            f"tooling.acceptance.mode must be one of {list(ACCEPTANCE_MODES)}; "
            f"got {acc.get('mode')!r}")
        return warnings, errors
    if has_enabled and has_mode:
        enabled = bool(acc.get("enabled"))
        mode = acc.get("mode")
        agrees = (enabled and mode in _TRUE_MODES) or (not enabled and mode == "off")
        if not agrees:
            errors.append(
                f"tooling.acceptance has conflicting `enabled: {enabled}` and "
                f"`mode: {mode!r}` (enabled:true↔mode∈{{advisory,auto}}, "
                f"enabled:false↔mode:off); set only `mode`")
        else:
            warnings.append(
                "enabled_deprecated: tooling.acceptance.enabled is deprecated; "
                "use `mode` (off|advisory|auto)")
    elif has_enabled and not has_mode:
        # enabled-only is the overwhelmingly common EXISTING shape — map it
        # SILENTLY (the field is marked deprecated in the schema description + the
        # template/docs; we do not nag every existing charter with a warning).
        # The genuine migration cases — a top-level namespace move, or `enabled`
        # AND `mode` both present — DO warn above.
        acc["mode"] = "auto" if bool(acc.get("enabled")) else "off"
    return warnings, errors


def acceptance_mode(charter: Any) -> str:
    """Read the canonical ``tooling.acceptance.mode``; absent → ``"off"``
    (byte-identical to the P2 disabled path — default-on is a TEMPLATE default,
    not a silent driver flip; design §3.1/§3.5). Assumes ``normalize_acceptance``
    has already mapped any legacy ``enabled`` alias."""
    if not isinstance(charter, dict):
        return "off"
    tooling = charter.get("tooling")
    acc = tooling.get("acceptance") if isinstance(tooling, dict) else None
    mode = acc.get("mode") if isinstance(acc, dict) else None
    return mode if mode in ACCEPTANCE_MODES else "off"
