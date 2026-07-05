"""Phase-4 native-E2E capability contract accessor (design §2/§13).

Machine-readable, framework-OWNED. The deployed aidazi PROVIDES a fixed set of capabilities
declared in ``governance/framework-capabilities.json``; an adopter DECLARES the capabilities its
charter REQUIRES in ``charter.required_framework_capabilities`` (mission-charter.schema.json).

Preflight (``run_loop --sign-plan``) and the real-run gate call ``required_capability_violations``
+ ``render_capability_refusal``. Both are DETERMINISTIC and FAIL-CLOSED: a missing / under-versioned
requirement REFUSES, and a MISSING / UNREADABLE / MALFORMED contract raises
``CapabilityContractError`` (the caller REFUSES) rather than silently passing. DORMANT (returns [])
only when the charter declares no required capabilities — legacy-safe, byte-identical to pre-Phase-4.

Capability IDENTITY is anchored to CODE: every declared capability names a ``code_anchor``
(``<relpath>:<symbol>``) that ``anchor_violations`` resolves to a real def/class, so identity does
NOT depend only on mutable documentation text (design §12.5 / capability-contract requirement). This
module is PURE (no network, no mutation) so both ``campaign`` and ``run_loop`` can import it flat off
``engine-kit`` on sys.path (like ``charter_compat``).
"""
import json
import os
from typing import Optional

#: The framework-owned contract, repo-relative.
CONTRACT_REL = os.path.join("governance", "framework-capabilities.json")


class CapabilityContractError(ValueError):
    """The framework capability contract is missing / unreadable / malformed. A required-capability
    check CANNOT be proven, so the caller REFUSES (fail-closed) rather than treating it as satisfied."""


def _repo_root() -> Optional[str]:
    """The repo root = the parent of this file's ``engine-kit`` dir, IFF it carries a
    ``governance`` dir (so a relocated deployment degrades to None rather than a wrong root)."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    return root if os.path.isdir(os.path.join(root, "governance")) else None


def contract_path(root: Optional[str] = None) -> Optional[str]:
    root = root or _repo_root()
    return os.path.join(root, CONTRACT_REL) if root else None


def load_contract(root: Optional[str] = None) -> dict:
    """Load + shape-check the framework capability contract. Raises ``CapabilityContractError``
    on absent / unreadable / malformed — never returns a partial dict (fail-closed)."""
    p = contract_path(root)
    if not p or not os.path.isfile(p):
        raise CapabilityContractError(
            f"framework capability contract not found at {CONTRACT_REL} — cannot verify "
            f"required capabilities (fail-closed)")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CapabilityContractError(
            f"framework capability contract at {CONTRACT_REL} is unreadable/invalid: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("capabilities"), list):
        raise CapabilityContractError(
            f"framework capability contract at {CONTRACT_REL} is malformed "
            f"(object with a capabilities[] array required)")
    return data


def provided_capabilities(contract: Optional[dict] = None,
                          root: Optional[str] = None) -> dict:
    """``{capability_id: version_string}`` the deployed framework PROVIDES (deterministic)."""
    contract = contract if contract is not None else load_contract(root)
    out = {}
    for c in contract.get("capabilities") or []:
        if isinstance(c, dict) and c.get("id"):
            out[str(c["id"])] = str(c.get("version") or "0")
    return out


def _parse_version(v) -> tuple:
    """Dotted-integer version → tuple for component-wise compare. A non-integer component
    degrades to 0 (never raises — the pattern is schema-validated for the contract, and an
    adopter min_version is best-effort compared)."""
    parts = []
    for tok in str(v if v is not None else "0").split("."):
        try:
            parts.append(int(tok))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def _version_ge(have, need) -> bool:
    return _parse_version(have) >= _parse_version(need)


def required_capability_violations(charter: Optional[dict],
                                   contract: Optional[dict] = None,
                                   root: Optional[str] = None) -> list:
    """The unsatisfied ``charter.required_framework_capabilities`` entries vs the deployed
    contract. Empty ⇒ satisfied. DORMANT (returns []) when the charter declares none (absent
    field) — legacy-safe. FAIL-CLOSED: a broken/unreadable contract raises
    ``CapabilityContractError`` (caller REFUSES) rather than returning []. Each violation is
    ``{id, kind ∈ {missing, under_version, malformed}, framework_version, ...}``."""
    required = (charter or {}).get("required_framework_capabilities")
    if not required:
        return []
    contract = contract if contract is not None else load_contract(root)  # raises → fail-closed
    provided = provided_capabilities(contract)
    fw = str(contract.get("framework_version") or "unknown")
    out = []
    for req in required:
        if not isinstance(req, dict) or not req.get("id"):
            out.append({"id": None, "kind": "malformed", "framework_version": fw,
                        "detail": repr(req)})
            continue
        cid = str(req["id"])
        need = req.get("min_version")
        if cid not in provided:
            out.append({"id": cid, "kind": "missing", "framework_version": fw,
                        "required_min_version": (str(need) if need else None)})
        elif need and not _version_ge(provided[cid], need):
            out.append({"id": cid, "kind": "under_version", "framework_version": fw,
                        "required_min_version": str(need),
                        "provided_version": provided[cid]})
    return out


def render_capability_refusal(violations: list, *, action: str) -> str:
    """The actionable refusal message: for each violation, the missing capability, the deployed
    framework capability/version, and the upgrade or migration action (design §13 capability
    requirement). ``action`` is a short verb phrase (e.g. 'refusing to sign the plan')."""
    lines = [f"native-E2E framework capability contract — {action}:"]
    for v in violations:
        cid = v.get("id")
        fw = v.get("framework_version")
        kind = v.get("kind")
        if kind == "missing":
            need = v.get("required_min_version")
            need_s = f" (>= {need})" if need else ""
            lines.append(
                f"  - required capability {cid!r}{need_s} is NOT provided by the deployed "
                f"framework (framework_version={fw}). UPGRADE the pinned aidazi to a build "
                f"whose governance/framework-capabilities.json declares {cid!r}, OR remove "
                f"the requirement from charter.required_framework_capabilities and re-sign.")
        elif kind == "under_version":
            lines.append(
                f"  - required capability {cid!r} needs >= {v.get('required_min_version')} but "
                f"the deployed framework provides {v.get('provided_version')} "
                f"(framework_version={fw}). UPGRADE the pinned aidazi, OR lower/remove the "
                f"min_version in charter.required_framework_capabilities and re-sign.")
        else:  # malformed
            lines.append(
                f"  - malformed required-capability entry {v.get('detail')}: each entry needs a "
                f"non-empty string `id`. Fix charter.required_framework_capabilities and re-sign.")
    return "\n".join(lines)


def anchor_violations(contract: Optional[dict] = None,
                      root: Optional[str] = None) -> list:
    """Build-time self-check (design §12.5): every declared capability's ``code_anchor``
    (``<relpath>:<symbol>``) must resolve to a real ``def``/``class`` in a real file — so
    capability IDENTITY is anchored to CODE, not mutable doc text. Returns the anchors that do
    NOT resolve (empty ⇒ every capability is code-backed). Used by the capability-contract test,
    never at runtime preflight (which trusts the shipped, tested contract)."""
    root = root or _repo_root()
    contract = contract if contract is not None else load_contract(root)
    out = []
    for c in contract.get("capabilities") or []:
        anchor = c.get("code_anchor") if isinstance(c, dict) else None
        cid = c.get("id") if isinstance(c, dict) else None
        if not anchor or ":" not in str(anchor):
            out.append({"id": cid, "anchor": anchor, "reason": "no code_anchor"})
            continue
        rel, symbol = str(anchor).rsplit(":", 1)
        fpath = os.path.join(root, rel) if root else rel
        if not os.path.isfile(fpath):
            out.append({"id": cid, "anchor": anchor, "reason": "file not found"})
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                body = fh.read()
        except OSError:
            out.append({"id": cid, "anchor": anchor, "reason": "unreadable"})
            continue
        if not (f"def {symbol}" in body or f"class {symbol}" in body):
            out.append({"id": cid, "anchor": anchor, "reason": "symbol not defined"})
    return out
