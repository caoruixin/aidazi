"""Phase-3 halt-conditions metric registry — the SINGLE SOURCE OF TRUTH.

archive/2026-07-09-phase3-halt-conditions-design.md §3.2. Pure + deterministic:
no I/O, no clock, no randomness. The charter schema enum, the charter validator
(closed-set ERRORs), and the campaign EP-pre evaluator all bind to THIS module.

A halt condition is a declarative predicate over ALREADY-AUDITED, plan-static
facts evaluated BEFORE a unit is dispatched (EP-pre). It can ONLY produce a HALT
+ checkpoint — never mutate a verdict, pick a route, or auto-resolve anything.

The caller (campaign._drive_milestones) builds a ``ctx`` dict mapping every metric
name to its ALREADY-RESOLVED fact value (e.g. milestone_functional_acceptance via
campaign.resolve_functional_acceptance — charter inheritance applied) so this
module never imports the campaign (no circular import) and never re-derives facts.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Closed whitelist (design §3.2). Adding a metric = one entry here + one schema
# enum member; the validator + evaluator pick it up automatically.
# --------------------------------------------------------------------------- #
_STRING = "string"
_ENUM = "enum"

# ack_scope: how far a human's "proceed" acknowledgement extends.
ACK_SCOPE_MILESTONE = "milestone"    # once-per-milestone (does not re-pause per sub-sprint)
ACK_SCOPE_SUBSPRINT = "subsprint"    # once-per-(milestone, sub-sprint)

# op whitelist — structural facts only ⇒ equality / set-membership (no ordering).
OPS: frozenset = frozenset({"==", "!=", "in", "not_in"})
_SET_OPS: frozenset = frozenset({"in", "not_in"})


class MetricSpec:
    __slots__ = ("value_type", "enum", "ops", "ack_scope")

    def __init__(self, value_type: str, ops: frozenset, ack_scope: str,
                 enum: Optional[frozenset] = None) -> None:
        self.value_type = value_type
        self.enum = enum
        self.ops = ops
        self.ack_scope = ack_scope


METRICS: Dict[str, MetricSpec] = {
    "milestone_id": MetricSpec(_STRING, OPS, ACK_SCOPE_MILESTONE),
    "subsprint_id": MetricSpec(_STRING, OPS, ACK_SCOPE_SUBSPRINT),
    "milestone_functional_acceptance": MetricSpec(
        _ENUM, OPS, ACK_SCOPE_MILESTONE,
        enum=frozenset({"static", "browser_e2e"})),
}

METRIC_NAMES: Tuple[str, ...] = tuple(METRICS.keys())


# --------------------------------------------------------------------------- #
# Validation (reused by charter_validator._check_halt_conditions) — closed-set
# ERRORs. Returns (rule_id, message) pairs; empty ⇒ the `when` is well-formed.
# --------------------------------------------------------------------------- #
def validate_when(when: Any) -> List[Tuple[str, str]]:
    """Validate a condition's ``when`` against the closed whitelist. Pure; the
    caller emits one report.error per returned (rule_id, message)."""
    errs: List[Tuple[str, str]] = []
    if not isinstance(when, dict):
        return [("halt_condition_when_shape", f"`when` must be an object, got {type(when).__name__}")]
    metric = when.get("metric")
    op = when.get("op")
    value = when.get("value")

    spec = METRICS.get(metric) if isinstance(metric, str) else None
    if spec is None:
        errs.append((
            "halt_condition_unknown_metric",
            f"unknown metric {metric!r}; the CLOSED whitelist is {sorted(METRIC_NAMES)}"))
        return errs  # can't validate op/value without a known metric

    if not isinstance(op, str) or op not in spec.ops:
        errs.append((
            "halt_condition_op_mismatch",
            f"op {op!r} is not allowed for metric {metric!r}; allowed: {sorted(spec.ops)}"))
        return errs

    errs.extend(_validate_value(metric, spec, op, value))
    return errs


def _validate_value(metric: str, spec: MetricSpec, op: str, value: Any
                    ) -> List[Tuple[str, str]]:
    errs: List[Tuple[str, str]] = []
    if op in _SET_OPS:
        if not isinstance(value, list) or not value:
            errs.append((
                "halt_condition_value_type",
                f"metric {metric!r} op {op!r} requires a non-empty array value"))
            return errs
        for item in value:
            errs.extend(_check_scalar(metric, spec, item))
    else:  # == / !=
        if isinstance(value, list):
            errs.append((
                "halt_condition_value_type",
                f"metric {metric!r} op {op!r} requires a scalar value, got an array"))
            return errs
        errs.extend(_check_scalar(metric, spec, value))
    return errs


def _check_scalar(metric: str, spec: MetricSpec, item: Any) -> List[Tuple[str, str]]:
    if spec.value_type == _STRING or spec.value_type == _ENUM:
        if not isinstance(item, str):
            return [("halt_condition_value_type",
                     f"metric {metric!r} value {item!r} must be a string")]
    if spec.value_type == _ENUM and spec.enum is not None and item not in spec.enum:
        return [("halt_condition_value_type",
                 f"metric {metric!r} value {item!r} not in the closed set {sorted(spec.enum)}")]
    return []


# --------------------------------------------------------------------------- #
# condition_digest — sha256 of the canonicalized `when` (design §3.4). Object
# keys sorted; the value array for set-membership ops is sorted (order-independent
# predicate ⇒ order-independent digest); `note` is NOT part of the predicate.
# --------------------------------------------------------------------------- #
def condition_digest(when: Dict[str, Any]) -> str:
    op = when.get("op")
    value = when.get("value")
    if op in _SET_OPS and isinstance(value, list):
        # sort by canonical-json of each element (stable across mixed/string items)
        value = sorted(value, key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    canonical = {"metric": when.get("metric"), "op": op, "value": value}
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# ack_key — the permanence key (design §3.4). Scope-dependent so a milestone
# gate is once-per-milestone and a sub-sprint gate is once-per-unit.
# --------------------------------------------------------------------------- #
def ack_key(condition: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[str, ...]:
    cid = str(condition.get("id"))
    digest = condition_digest(condition.get("when") or {})
    metric = (condition.get("when") or {}).get("metric")
    spec = METRICS.get(metric)
    mid = str(ctx.get("milestone_id"))
    if spec is not None and spec.ack_scope == ACK_SCOPE_SUBSPRINT:
        return (cid, digest, mid, str(ctx.get("subsprint_id")))
    return (cid, digest, mid)


# --------------------------------------------------------------------------- #
# evaluate — the pure EP-pre predicate. Returns the FIRST declaration-order
# condition whose predicate is true AND whose ack_key is not already acknowledged;
# None ⇒ no halt (dispatch proceeds byte-identically). Read-only.
# --------------------------------------------------------------------------- #
def _apply(op: str, fact: Any, target: Any) -> bool:
    if op == "==":
        return fact == target
    if op == "!=":
        return fact != target
    if op == "in":
        return isinstance(target, list) and fact in target
    if op == "not_in":
        return isinstance(target, list) and fact not in target
    return False  # unknown op — fail-closed to "no match" (validator already ERRORs)


def evaluate(conditions: List[Dict[str, Any]], ctx: Dict[str, Any],
             acked: Any) -> Optional[Dict[str, Any]]:
    """First unacknowledged condition whose predicate holds. `acked` is a set/
    collection of ack_key tuples (permanent ∪ this-cascade provisional)."""
    acked_set = {tuple(k) for k in (acked or [])}
    for cond in conditions or []:
        when = cond.get("when") or {}
        metric = when.get("metric")
        spec = METRICS.get(metric)
        if spec is None:
            continue  # not in the whitelist — validator ERRORs at preflight; skip at runtime
        fact = ctx.get(metric)
        if not _apply(when.get("op"), fact, when.get("value")):
            continue
        key = ack_key(cond, ctx)
        if key in acked_set:
            continue
        return {
            "condition_id": str(cond.get("id")),
            "condition_digest": condition_digest(when),
            "metric": metric,
            "ack_scope": spec.ack_scope,
            "ack_key": list(key),
            "facts": {metric: fact},
        }
    return None
