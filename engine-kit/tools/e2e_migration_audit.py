"""Phase-4 existing-adopter native-E2E migration audit (design §13 legacy compatibility).

An aidazi framework UPGRADE ALONE must NOT mutate an existing adopter's authoritative state —
campaign plans, signed charters, requirement ledgers, Acceptance reports, E2E configuration, or the
adopter's aidazi pin. This module is the READ-ONLY diagnostic that, when an adopter chooses to
DEPLOY the new native-E2E capability, DETECTS config gaps and EMITS an advisory migration/audit
proposal explaining exactly what WOULD change — and defers every change to explicit human
authorization. It NEVER writes.

Two locked legacy-safety rules (design §13):
  * A legacy NON-user-facing milestone stays valid and is NEVER flagged / forced into browser E2E.
  * The audit performs NO mutation (``no_mutation_performed: true`` always); the ``migration_steps``
    require explicit human authorization before any authoritative artifact is touched.

Pure module (dict-in / dict-out; the only I/O is an optional read of the ledger in the CLI).
"""
import copy
import json
import os
from typing import Optional

#: real-execution executor kinds (mirror e2e_stage.REAL_EXECUTION_KINDS without importing it, so
#: this tool stays standalone). local_http is the DRY-RUN class — never a real acceptance verdict.
REAL_EXECUTION_KINDS = frozenset({"playwright", "external_test_runner"})
_VALID_SURFACES = frozenset({"user_facing", "non_user_facing"})

#: the authoritative artifacts an upgrade alone must NEVER mutate (surfaced in every audit).
IMMUTABLE_ON_UPGRADE = [
    "campaign plans", "signed charters", "requirement ledgers",
    "Acceptance reports", "E2E configuration", "aidazi pins",
]


def _resolve_mode(charter: dict, milestone: dict):
    """The resolved functional-acceptance (mode, source) — reuse the canonical campaign resolver
    when importable, else an inline mirror of its precedence (milestone override > charter > static)."""
    fa = milestone.get("functional_acceptance")
    try:
        import campaign as _cp  # lazy; orchestrator on sys.path for a real run
        return _cp.resolve_functional_acceptance(charter, fa)
    except Exception:  # noqa: BLE001 — standalone tool run: inline the same precedence
        charter_mode = ((((charter or {}).get("tooling") or {}).get("acceptance") or {})
                        .get("functional") or {}).get("mode")
        if fa is not None:
            return fa, "milestone"
        if charter_mode is not None:
            return charter_mode, "charter"
        return "static", "default"


def _milestone_surface(milestone: dict, reqs: dict) -> Optional[str]:
    """user_facing if ANY covered rid is classified user_facing; non_user_facing if EVERY covered
    rid is validly non_user_facing; None when unknowable (no covers, or an unclassified rid) — an
    unknowable surface is NOT flagged as a native-E2E gap here (OW-M3 sign-off owns that)."""
    covered = [rid for rid in (milestone.get("covers_req_ids") or [])]
    if not covered:
        return None
    surfaces = []
    for rid in covered:
        r = reqs.get(rid)
        s = r.get("surface") if isinstance(r, dict) else None
        if s not in _VALID_SURFACES:
            return None  # unknowable — defer to the OW-M3 mandate, not this native-E2E audit
        surfaces.append(s)
    return "user_facing" if "user_facing" in surfaces else "non_user_facing"


def audit_adopter(*, charter: Optional[dict], plan: Optional[dict] = None,
                  ledger: Optional[dict] = None) -> dict:
    """READ-ONLY native-E2E migration audit. Returns a structured, advisory proposal — NEVER
    mutates ``charter``/``plan``/``ledger`` (they are treated as read-only inputs). Detects, per
    milestone, ONLY for USER-FACING milestones (legacy non-user-facing stays valid, never flagged):

    blocking_gaps (native-E2E cannot run correctly until fixed):
      * ``dry_run_executor``   — a browser_e2e milestone whose charter.tooling.e2e.executor_kind is
        the local_http DRY-RUN class (cannot produce a real acceptance verdict) → migrate to
        external_test_runner (or playwright).
      * ``missing_tooling_e2e`` — a browser_e2e milestone with NO charter.tooling.e2e block.
      * ``user_facing_not_browser_e2e`` — a user-facing milestone whose resolved functional
        acceptance is not browser_e2e (the OW-M3 mandate; surfaced here with the native-E2E fix).

    advisory_opportunities (legacy-safe to leave; offered, never forced):
      * ``no_signed_remediation_budget`` — a browser_e2e milestone with no charter.autonomy
        .e2e_remediation budget ⇒ §1.7-G stays OFF (deterministic failures route to the §3.5 human
        gate exactly as today). Offer to enable a SIGNED budget.
      * ``no_capability_pin`` — the charter pins no required_framework_capabilities ⇒ a future
        aidazi that DROPS a capability would not fail closed at preflight. Offer to pin.
    """
    charter = charter or {}
    plan = plan or {}
    reqs = {r.get("id"): r for r in ((ledger or {}).get("requirements") or [])
            if isinstance(r, dict)}
    e2e_cfg = ((charter.get("tooling") or {}).get("e2e"))
    has_tooling_e2e = isinstance(e2e_cfg, dict) and bool(e2e_cfg)
    executor_kind = str((e2e_cfg or {}).get("executor_kind") or "") if has_tooling_e2e else ""
    has_remediation = isinstance((charter.get("autonomy") or {}).get("e2e_remediation"), dict)
    has_capability_pin = bool(charter.get("required_framework_capabilities"))

    blocking_gaps = []
    advisory_opportunities = []

    for m in (plan.get("milestones") or []):
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        surface = _milestone_surface(m, reqs)
        if surface != "user_facing":
            continue  # legacy non-user-facing (or unknowable) — never forced into browser E2E
        mode, _src = _resolve_mode(charter, m)
        if mode != "browser_e2e":
            blocking_gaps.append({
                "milestone_id": mid, "kind": "user_facing_not_browser_e2e",
                "detail": f"resolved functional acceptance is {mode!r}",
                "proposed_change": "set this milestone's functional_acceptance: \"browser_e2e\" "
                                   "(or, Customer-only, reclassify the requirement surface)",
            })
            continue
        # browser_e2e user-facing milestone: check the executor is real-execution + configured.
        if not has_tooling_e2e:
            blocking_gaps.append({
                "milestone_id": mid, "kind": "missing_tooling_e2e",
                "detail": "browser_e2e milestone but the charter has no tooling.e2e block",
                "proposed_change": "add a charter.tooling.e2e executor contract "
                                   "(external_test_runner recommended) — see the onboarding "
                                   "proposal generator (engine-kit/tools/e2e_config_proposal.py)",
            })
        elif executor_kind not in REAL_EXECUTION_KINDS:
            blocking_gaps.append({
                "milestone_id": mid, "kind": "dry_run_executor",
                "detail": f"executor_kind={executor_kind!r} is the local_http dry-run class and "
                          f"cannot produce a real acceptance verdict",
                "proposed_change": "migrate charter.tooling.e2e.executor_kind to "
                                   "external_test_runner (managed adopter spec-runner) or "
                                   "playwright, add spec_path/runner_argv, and re-sign",
            })
        if not has_remediation:
            advisory_opportunities.append({
                "milestone_id": mid, "kind": "no_signed_remediation_budget",
                "detail": "no charter.autonomy.e2e_remediation budget ⇒ §1.7-G autonomous "
                          "remediation stays OFF (deterministic failures route to the §3.5 human "
                          "gate exactly as today — legacy-safe)",
                "proposed_change": "OPTIONAL: add a SIGNED charter.autonomy.e2e_remediation "
                                   "{enabled:true, max_rounds, max_no_progress_rounds:1} at "
                                   "human_on_the_loop+ to enable bounded autonomous remediation",
            })

    if not has_capability_pin and (blocking_gaps or advisory_opportunities):
        advisory_opportunities.append({
            "milestone_id": None, "kind": "no_capability_pin",
            "detail": "the charter pins no required_framework_capabilities ⇒ a future aidazi that "
                      "drops a native-E2E capability would not fail closed at preflight",
            "proposed_change": "OPTIONAL: add charter.required_framework_capabilities "
                               "(native_managed_external_e2e / framework_owned_e2e_provenance / "
                               "autonomous_e2e_remediation) so preflight fail-closes on a downgrade",
        })

    any_finding = bool(blocking_gaps or advisory_opportunities)
    return {
        "audit_kind": "native_e2e_migration",
        "no_mutation_performed": True,
        "authorization_required": any_finding,
        "blocking_gaps": blocking_gaps,
        "advisory_opportunities": advisory_opportunities,
        "immutable_on_upgrade": list(IMMUTABLE_ON_UPGRADE),
        "migration_steps": _migration_steps(blocking_gaps, advisory_opportunities),
    }


def _migration_steps(blocking: list, advisory: list) -> list:
    steps = []
    if not (blocking or advisory):
        return ["No native-E2E migration needed — no user-facing gaps or opportunities detected."]
    steps.append("This is a READ-ONLY audit. NOTHING has been changed. An aidazi upgrade alone "
                 "never mutates campaign plans, signed charters, requirement ledgers, Acceptance "
                 "reports, E2E configuration, or aidazi pins.")
    if blocking:
        steps.append("BLOCKING (native-E2E will not run correctly until resolved, with explicit "
                     "human authorization):")
        for g in blocking:
            steps.append(f"  - milestone {g.get('milestone_id')!r} [{g['kind']}]: "
                         f"{g['proposed_change']}")
    if advisory:
        steps.append("OPTIONAL opportunities (legacy-safe to leave; adopt only if you choose):")
        for g in advisory:
            steps.append(f"  - {('milestone ' + repr(g.get('milestone_id'))) if g.get('milestone_id') else 'charter'} "
                         f"[{g['kind']}]: {g['proposed_change']}")
    steps.append("After you AUTHORIZE the changes, edit the charter/plan, re-run --sign-plan to "
                 "re-stamp the signed scope, then --resume. The framework will not do this for you.")
    return steps


def render_audit(audit: dict) -> str:
    lines = [f"native-E2E migration audit — {'action required' if audit.get('authorization_required') else 'no changes needed'} "
             f"(READ-ONLY; no_mutation_performed={audit.get('no_mutation_performed')}):"]
    lines.extend("  " + s for s in audit.get("migration_steps") or [])
    return "\n".join(lines)


def audit_is_read_only(*, charter, plan=None, ledger=None) -> bool:
    """Proof helper: running the audit leaves every input byte-identical (no silent mutation)."""
    before = json.dumps([charter, plan, ledger], sort_keys=True)
    audit_adopter(charter=copy.deepcopy(charter),
                  plan=copy.deepcopy(plan) if plan else plan,
                  ledger=copy.deepcopy(ledger) if ledger else ledger)
    after = json.dumps([charter, plan, ledger], sort_keys=True)
    return before == after


def _main(argv=None) -> int:  # pragma: no cover - thin CLI wrapper
    import argparse
    ap = argparse.ArgumentParser(description="Read-only native-E2E migration audit for an adopter.")
    ap.add_argument("--charter", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    with open(args.charter, encoding="utf-8") as fh:
        charter = json.load(fh)
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    ledger = None
    if args.ledger and os.path.isfile(args.ledger):
        with open(args.ledger, encoding="utf-8") as fh:
            ledger = json.load(fh)
    audit = audit_adopter(charter=charter, plan=plan, ledger=ledger)
    print(json.dumps(audit, indent=2, sort_keys=True) if args.json else render_audit(audit))
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(_main())
