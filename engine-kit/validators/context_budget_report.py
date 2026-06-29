#!/usr/bin/env python3
"""context_budget_report — WP-9 ADVISORY context-budget lint (warning + waiver, NOT a hard ceiling).

Read-only, deterministic, build-time lint over each role/task **cold-start context budget**.
It makes per-role / per-task cold-start size a *checkable regression contract* that catches
future bloat — WITHOUT violating the framework doctrine "sufficient context > artificially
small context" (``process/context-passing-efficiency.md`` §1.1/§1.2). It saves 0 direct
tokens; it is a regression guardrail.

The lint is ADVISORY: it WARNS when a role/task drifts over a threshold vs a checked-in
baseline snapshot, ATTRIBUTES the oversized section, and supports a checked-in
WAIVER-WITH-RATIONALE (recorded in the report, never silent). It HARD-STOPS only for a
small, explicit set of STRUCTURAL ANOMALIES (an unbounded / structurally-broken load set),
never for a normal role that simply needs a lot of legitimate context.

It REUSES (does not rebuild) the WP-0 sizing machinery in
``engine-kit/orchestrator/load_sizer.py`` (``size_role`` / ``size_load_set`` /
``role_cold_start_roots`` / ``GOVERNANCE_TRIO`` / ``TASK_SCOPED_COLD_START``) and reads the
WP-6 runtime lesson bound (``lesson_selection.DEFAULT_BUDGET``) as a STATIC backstop. It is
purely additive: it changes no dispatched context and touches no resolver / audit-hash /
``_sources.yaml`` / kernel-coverage inventory.

Design + measured baseline: ``archive/2026-06-28-wp9-context-budget-lint-decision.md``.

Status taxonomy (per row): ok | warn | waived | anomaly.

CLI::

    python context_budget_report.py [--json] [--strict] [--repo-root R] [--adopter-root A]
    python context_budget_report.py --emit-baseline   # regenerate the snapshot at HEAD

Exit code: default = nonzero iff an ANOMALY is present (drift warnings are advisory and do
NOT hard-stop the default CLI). ``--strict`` = nonzero iff not ok (anomaly OR un-waived
warning) — the build-gate semantics the pytest gate asserts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Reuse load_sizer (orchestrator) + lesson_selection (memory). Mirror load_sizer's own
# sys.path dance so this runs as a script OR imported as a module.
_HERE = Path(__file__).resolve()
_VALIDATORS_DIR = _HERE.parent
_ENGINE_KIT_DIR = _VALIDATORS_DIR.parent
_REPO_ROOT = _ENGINE_KIT_DIR.parent
for _p in (str(_ENGINE_KIT_DIR / "orchestrator"),
           str(_ENGINE_KIT_DIR),
           str(_ENGINE_KIT_DIR / "audit"),
           str(_ENGINE_KIT_DIR / "memory")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import load_sizer  # noqa: E402  (orchestrator sibling on sys.path above)
import lesson_selection  # noqa: E402  (memory sibling on sys.path above)

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a hard dependency
    yaml = None


# --------------------------------------------------------------------------- #
# Configuration (deterministic + configurable via the baseline file)          #
# --------------------------------------------------------------------------- #

REPO_ROOT_DEFAULT = load_sizer.REPO_ROOT_DEFAULT
BYTES_PER_TOKEN_EST = load_sizer.BYTES_PER_TOKEN_EST  # 4 (consistent with load_sizer)

DATA_DIR = _VALIDATORS_DIR / "data"
BASELINE_PATH_DEFAULT = DATA_DIR / "context_budget_baseline.yaml"
WAIVER_PATH_DEFAULT = DATA_DIR / "context_budget_waivers.yaml"

#: Drift warning fires when current_bytes > baseline_bytes * (1 + this). +10% of the
#: smallest tracked entry (~82KB review) is ~2,060 tokens of NEW content — doc-sized
#: bloat, not prose-edit noise. Configurable: the baseline file's ``drift_warn_fraction``
#: overrides this; a per-entry ``drift_warn_fraction`` overrides that.
DEFAULT_DRIFT_WARN_FRACTION = 0.10

#: Absolute hard-ceiling ANOMALY — FAR above any legitimate role (heaviest = deliver
#: 168,017 B). 400,000 B ≈ 100,000 tok is 2.38x the heaviest role: only a structurally
#: broken / unbounded load set hits it. Legitimate growth WARNS (waivable) long before.
DEFAULT_ANOMALY_ABS_CEILING_BYTES = 400_000

# Status taxonomy.
STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_WAIVED = "waived"
STATUS_ANOMALY = "anomaly"

# Reasons.
REASON_DRIFT = "drift"
ANOM_ABS_CEILING = "abs_ceiling"
ANOM_MISSING_BASELINE = "missing_baseline"
ANOM_MISSING_ROOT = "missing_root"
ANOM_LESSON_BOUND_DISABLED = "lesson_bound_disabled"
ANOM_BASELINE_UNREADABLE = "baseline_unreadable"

#: A structural row (not a load set) keyed here: the WP-6 runtime lesson bound. The lint
#: statically backstops that the only previously-unbounded injected channel is still bounded.
KEY_LESSON_BOUND = "__lesson_bound__"

#: The canonical tracked cold-start budgets. ``role is None`` = the governance floor
#: (``GOVERNANCE_TRIO``, re-paid every spawn). Adding a tracked role/task = add an entry
#: here + regenerate the baseline (``--emit-baseline``). Order is the report's row order.
BUDGET_ENTRIES: list = [
    {"key": "governance-floor", "role": None, "task_kind": None},
    {"key": "research", "role": "research", "task_kind": None},
    {"key": "deliver", "role": "deliver", "task_kind": None},
    {"key": "deliver:close", "role": "deliver", "task_kind": "close"},
    {"key": "dev", "role": "dev", "task_kind": None},
    {"key": "review", "role": "review", "task_kind": None},
    {"key": "acceptance", "role": "acceptance", "task_kind": None},
    # Track 1 §2.4 (Codex R-T1 B1) — per-role DEFAULT skill-body budgets. These size the agent's
    # OWN mid-session SKILL.md reads (resolve_role_config role_defaults), which are INVISIBLE to
    # the per-spawn prompt audit AND absent from the cold-start floor rows above (skills_active
    # sizes no SKILL.md body). Tracking them makes task-skill body growth a checkable regression.
    # PER-TASK-SIGNAL-SET rows ("task_signals": [ui, ...]) are added in Track 1 Phase 1-c, once
    # signal-tagged UI skills exist; the entry shape + _size_entry already support them (proven by
    # the unit test that sizes a synthetic signal-tagged catalog).
    {"key": "skills:research", "role": "research", "task_kind": None,
     "kind": "skills", "task_signals": []},
    {"key": "skills:deliver", "role": "deliver", "task_kind": None,
     "kind": "skills", "task_signals": []},
    {"key": "skills:dev", "role": "dev", "task_kind": None,
     "kind": "skills", "task_signals": []},
    {"key": "skills:review", "role": "review", "task_kind": None,
     "kind": "skills", "task_signals": []},
    {"key": "skills:acceptance", "role": "acceptance", "task_kind": None,
     "kind": "skills", "task_signals": []},
]


def _est_tokens(n_bytes) -> int:
    return n_bytes // BYTES_PER_TOKEN_EST


# --------------------------------------------------------------------------- #
# Sizing (reuses load_sizer — no duplicate sizer logic)                       #
# --------------------------------------------------------------------------- #
def _size_entry(entry: dict, repo_root) -> dict:
    """Measure one budget entry's FRAMEWORK-STATIC cold-start size via load_sizer.

    Returns ``{total_bytes, by_purpose, files{path:bytes}, missing[]}``. ``role is None``
    sizes the governance floor (``GOVERNANCE_TRIO``); otherwise ``size_role(role,
    task_kind)``. Framework-static only (the baseline is framework-controlled + repo-local;
    adopter-static varies per deployment and is sized informationally via ``--adopter-root``,
    never against the baseline)."""
    if entry.get("kind") == "skills":
        # Track 1 §2.4 — RESOLVED skill BODIES for this role's default (or, Phase 1-c, task-signal)
        # set. Framework-static (charter-less role defaults); a catalog-declared-but-absent
        # task-selected candidate drops via the §2.2 skip, never a 'missing' anomaly here.
        # FAIL-CLOSED: if the skill set itself cannot be RESOLVED (no/empty registry.yaml, an
        # unreadable framework root — EffectiveConfigError is a ValueError), the row degrades to a
        # missing_root anomaly rather than crashing the lint (a structurally-broken tree, never ok).
        try:
            r = load_sizer.size_role_skills(
                entry["role"], task_signals=entry.get("task_signals") or (), repo_root=repo_root)
            total = r["total_bytes"]
            by_purpose = dict(r["by_purpose"])
            files = {g["path"]: g["bytes"] for g in r["files"]}
            missing = list(r["missing"])
        except (OSError, ValueError, KeyError) as exc:
            total, by_purpose, files = 0, {}, {}
            missing = [f"skills:{entry['role']} unresolvable: {exc}"]
    elif entry["role"] is None:
        r = load_sizer.size_load_set(load_sizer.GOVERNANCE_TRIO, repo_root=repo_root)
        total = r["total_bytes"]
        by_purpose = dict(r["by_purpose"])
        files = {g["path"]: g["bytes"] for g in r["files"]}
        missing = list(r["missing"])
    else:
        r = load_sizer.size_role(entry["role"], entry["task_kind"], repo_root=repo_root)
        total = r["framework_bytes"]  # framework-static (NOT adopter) — matches the baseline
        by_purpose = dict(r["by_purpose"])
        files = {g["path"]: g["bytes"] for g in r["files"]}
        missing = [m for m in r["missing"] if not str(m).startswith("(adopter)")]
    return {"total_bytes": total, "by_purpose": by_purpose, "files": files,
            "missing": missing}


def _largest_files(files: dict, n: int = 5) -> list:
    """Top-``n`` current files by size, deterministic ((-bytes, path))."""
    items = sorted(files.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"path": p, "bytes": b} for p, b in items[:n]]


def _attribute(sized: dict, base_entry) -> dict:
    """Name the oversized section(s) for a non-ok row, reusing load_sizer's per-file +
    by_purpose sizing. Deterministic. Returns ``by_purpose_delta`` + ``by_file_delta``
    (vs baseline, growers first) + ``largest_current_files`` (always informative, even when
    there is no baseline delta — e.g. an absolute-ceiling or missing-baseline anomaly)."""
    base_files = (base_entry or {}).get("files") or {}
    base_purpose = (base_entry or {}).get("by_purpose") or {}

    purpose_delta = []
    for p in sorted(set(sized["by_purpose"]) | set(base_purpose)):
        cur = sized["by_purpose"].get(p, 0)
        base = base_purpose.get(p, 0)
        if cur != base:
            purpose_delta.append({"purpose": p, "current_bytes": cur,
                                  "baseline_bytes": base, "delta": cur - base})
    purpose_delta.sort(key=lambda d: (-d["delta"], d["purpose"]))

    file_delta = []
    for path in set(sized["files"]) | set(base_files):
        cur = sized["files"].get(path, 0)
        base = base_files.get(path, 0)
        if cur != base:
            file_delta.append({"path": path, "current_bytes": cur,
                               "baseline_bytes": base, "delta": cur - base})
    file_delta.sort(key=lambda d: (-d["delta"], d["path"]))

    return {"by_purpose_delta": purpose_delta, "by_file_delta": file_delta,
            "largest_current_files": _largest_files(sized["files"])}


# --------------------------------------------------------------------------- #
# Baseline + waiver loading (fail-safe, deterministic)                         #
# --------------------------------------------------------------------------- #
def _load_baseline(path) -> tuple:
    """Return ``(baseline_dict, issue)``. ``baseline_dict`` is None (issue set) when the
    file is missing/unparseable/malformed — fail-closed: the regression anchor is the whole
    contract, so a broken baseline FILE becomes a global anomaly (§7 of the decision doc)."""
    if yaml is None:
        return None, "PyYAML is required but not installed"
    p = Path(path)
    if not p.is_file():
        return None, f"baseline file not found: {p}"
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse failure is fail-closed
        return None, f"baseline file unparseable: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return None, "baseline file malformed: expected a mapping with an 'entries' list"
    return data, None


def _load_waivers(path) -> tuple:
    """Return ``({key: {rationale}}, issue)``. FAIL-SAFE toward SURFACING bloat: a
    missing waiver file is valid (no waivers); an unparseable/malformed one yields NO
    waivers (so nothing is suppressed) plus a structural issue — a broken waiver file can
    NEVER silently hide a regression. A waiver entry with no non-empty ``rationale`` is
    ignored (a waiver must record WHY) and noted."""
    if yaml is None:
        return {}, "PyYAML is required but not installed"
    p = Path(path)
    if not p.is_file():
        return {}, None  # optional
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {}, f"waiver file unparseable (no waivers applied): {exc}"
    if data is None:
        return {}, None
    if not isinstance(data, dict) or not isinstance(data.get("waivers"), list):
        return {}, "waiver file malformed (no waivers applied): expected a mapping with a 'waivers' list"
    waivers: dict = {}
    skipped = []
    for w in data["waivers"]:
        if not isinstance(w, dict):
            continue
        key = w.get("key")
        rationale = w.get("rationale")
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(rationale, str) or not rationale.strip():
            skipped.append(str(key))
            continue
        waivers[key] = {"rationale": rationale.strip()}
    issue = (f"waiver(s) ignored (missing rationale): {', '.join(sorted(skipped))}"
             if skipped else None)
    return waivers, issue


# --------------------------------------------------------------------------- #
# The check (pure, deterministic)                                             #
# --------------------------------------------------------------------------- #
def _lesson_bound_row() -> dict:
    """Static backstop for the WP-6 runtime lesson bound. ANOMALY iff BOTH L1 ceilings are
    disabled (≤ 0) — the design's "unbounded lesson concatenation". Narrow: if EITHER the
    count or the byte ceiling is positive, L1 is still bounded, so it is NOT an anomaly.
    Non-waivable (a structural row, not a drift)."""
    b = lesson_selection.DEFAULT_BUDGET
    disabled = (b.max_l1_count <= 0) and (b.max_l1_bytes <= 0)
    row = {
        "key": KEY_LESSON_BOUND,
        "role": None,
        "task_kind": None,
        "kind": "lesson_bound",
        "current_bytes": None,
        "current_tokens": None,
        "baseline_bytes": None,
        "drift_fraction": None,
        "detail": (f"LessonBudget(max_l1_count={b.max_l1_count}, "
                   f"max_l1_bytes={b.max_l1_bytes})"),
        "waiver_rationale": None,
        "attribution": None,
    }
    if disabled:
        row["status"] = STATUS_ANOMALY
        row["reason"] = ANOM_LESSON_BOUND_DISABLED
    else:
        row["status"] = STATUS_OK
        row["reason"] = None
    return row


def check(repo_root=REPO_ROOT_DEFAULT, *, baseline_path=None, waiver_path=None) -> dict:
    """Run the lint. Returns::

        {ok, has_anomaly, has_unwaived_warning, rows[], structural_issues[], config{}}

    ``ok`` = no anomaly AND no un-waived warning (the build-gate-green predicate; a WAIVED
    row is ok). Anomalies are computed BEFORE waivers, so a waiver can never hide an
    anomaly. Deterministic: same inputs ⇒ identical result.
    """
    baseline_path = Path(baseline_path) if baseline_path else BASELINE_PATH_DEFAULT
    waiver_path = Path(waiver_path) if waiver_path else WAIVER_PATH_DEFAULT

    baseline, baseline_issue = _load_baseline(baseline_path)
    waivers, waiver_issue = _load_waivers(waiver_path)
    structural_issues: list = []
    if waiver_issue:
        structural_issues.append(waiver_issue)

    # Baseline FILE unreadable → global anomaly, fail-closed (no rows can be checked).
    if baseline is None:
        structural_issues.append(baseline_issue)
        return {
            "ok": False,
            "has_anomaly": True,
            "has_unwaived_warning": False,
            "rows": [{
                "key": "__baseline__", "role": None, "task_kind": None,
                "status": STATUS_ANOMALY, "reason": ANOM_BASELINE_UNREADABLE,
                "detail": baseline_issue, "current_bytes": None, "baseline_bytes": None,
                "drift_fraction": None, "waiver_rationale": None, "attribution": None,
            }],
            "structural_issues": structural_issues,
            "config": {
                "drift_warn_fraction": DEFAULT_DRIFT_WARN_FRACTION,
                "anomaly_abs_ceiling_bytes": DEFAULT_ANOMALY_ABS_CEILING_BYTES,
                "bytes_per_token_est": BYTES_PER_TOKEN_EST,
            },
        }

    drift_default = baseline.get("drift_warn_fraction", DEFAULT_DRIFT_WARN_FRACTION)
    abs_ceiling = baseline.get("anomaly_abs_ceiling_bytes",
                               DEFAULT_ANOMALY_ABS_CEILING_BYTES)
    base_map = {e.get("key"): e for e in baseline["entries"] if isinstance(e, dict)}

    rows: list = []
    for entry in BUDGET_ENTRIES:
        sized = _size_entry(entry, repo_root)
        cur = sized["total_bytes"]
        base_entry = base_map.get(entry["key"])
        base_bytes = base_entry.get("total_bytes") if isinstance(base_entry, dict) else None
        drift_frac = drift_default
        if isinstance(base_entry, dict) and isinstance(
                base_entry.get("drift_warn_fraction"), (int, float)):
            drift_frac = base_entry["drift_warn_fraction"]

        status = STATUS_OK
        reason = None
        detail = None
        waiver_rationale = None

        # --- ANOMALIES FIRST (non-waivable; precedence order) ---
        if sized["missing"]:
            status, reason = STATUS_ANOMALY, ANOM_MISSING_ROOT
            detail = "missing cold-start root(s): " + ", ".join(sorted(sized["missing"]))
        elif cur > abs_ceiling:
            status, reason = STATUS_ANOMALY, ANOM_ABS_CEILING
            detail = f"{cur} B > absolute ceiling {abs_ceiling} B"
        elif not isinstance(base_bytes, (int, float)) or base_bytes <= 0:
            status, reason = STATUS_ANOMALY, ANOM_MISSING_BASELINE
            detail = f"no positive baseline for key '{entry['key']}'"
        else:
            # --- DRIFT (advisory; waivable) ---
            threshold = base_bytes * (1.0 + drift_frac)
            if cur > threshold:
                w = waivers.get(entry["key"])
                if w and w.get("rationale"):
                    status = STATUS_WAIVED
                    reason = REASON_DRIFT
                    waiver_rationale = w["rationale"]
                else:
                    status = STATUS_WARN
                    reason = REASON_DRIFT

        drift_value = None
        if isinstance(base_bytes, (int, float)) and base_bytes > 0:
            drift_value = round((cur - base_bytes) / base_bytes, 6)

        rows.append({
            "key": entry["key"],
            "role": entry["role"],
            "task_kind": entry["task_kind"],
            "kind": entry.get("kind") or ("floor" if entry["role"] is None else "role"),
            "current_bytes": cur,
            "current_tokens": _est_tokens(cur),
            "baseline_bytes": base_bytes,
            "drift_fraction": drift_value,
            "status": status,
            "reason": reason,
            "detail": detail,
            "waiver_rationale": waiver_rationale,
            "by_purpose": dict(sized["by_purpose"]),
            "attribution": _attribute(sized, base_entry) if status != STATUS_OK else None,
        })

    # The WP-6 lesson-bound structural backstop row.
    rows.append(_lesson_bound_row())

    has_anomaly = any(r["status"] == STATUS_ANOMALY for r in rows)
    has_unwaived_warning = any(r["status"] == STATUS_WARN for r in rows)
    return {
        "ok": not has_anomaly and not has_unwaived_warning,
        "has_anomaly": has_anomaly,
        "has_unwaived_warning": has_unwaived_warning,
        "rows": rows,
        "structural_issues": structural_issues,
        "config": {
            "drift_warn_fraction": drift_default,
            "anomaly_abs_ceiling_bytes": abs_ceiling,
            "bytes_per_token_est": BYTES_PER_TOKEN_EST,
        },
    }


# --------------------------------------------------------------------------- #
# Baseline generation                                                          #
# --------------------------------------------------------------------------- #
def build_baseline(repo_root=REPO_ROOT_DEFAULT, *,
                   drift_warn_fraction: float = DEFAULT_DRIFT_WARN_FRACTION,
                   anomaly_abs_ceiling_bytes: int = DEFAULT_ANOMALY_ABS_CEILING_BYTES
                   ) -> dict:
    """Build the checked-in baseline snapshot from load_sizer at the given repo (the
    current measurement → at HEAD current == baseline ⇒ drift 0 ⇒ no false positive).
    Deterministic: no clock, no randomness; ``generated_from`` is a fixed string."""
    entries = []
    for e in BUDGET_ENTRIES:
        s = _size_entry(e, repo_root)
        row = {
            "key": e["key"],
            "role": e["role"],
            "task_kind": e["task_kind"],
            "total_bytes": s["total_bytes"],
            "est_tokens": _est_tokens(s["total_bytes"]),
            "by_purpose": s["by_purpose"],
            "files": s["files"],
        }
        # Track 1 §2.4 — record the entry kind + task-signal set for skill-body rows so the
        # checked-in baseline is self-describing (and a Phase 1-c per-signal row is unambiguous).
        if e.get("kind"):
            row["kind"] = e["kind"]
        if e.get("task_signals") is not None and e.get("kind") == "skills":
            row["task_signals"] = list(e["task_signals"])
        entries.append(row)
    return {
        "version": 1,
        "generated_from": "load_sizer framework-static cold-start sizing (WP-9)",
        "bytes_per_token_est": BYTES_PER_TOKEN_EST,
        "drift_warn_fraction": drift_warn_fraction,
        "anomaly_abs_ceiling_bytes": anomaly_abs_ceiling_bytes,
        "entries": entries,
    }


def _dump_yaml(obj: dict) -> str:
    """Deterministic YAML (sorted keys, block style) — byte-identical for identical inputs."""
    return yaml.safe_dump(obj, sort_keys=True, allow_unicode=True,
                          default_flow_style=False)


# --------------------------------------------------------------------------- #
# Reporting / CLI                                                              #
# --------------------------------------------------------------------------- #
def render_report(result: dict) -> str:
    """Deterministic text report: a per-row status table + attribution for non-ok rows +
    structural issues + the config/doctrine footer."""
    cfg = result["config"]
    lines = ["# Context-budget lint (WP-9, ADVISORY — warn + waiver, NOT a hard ceiling)",
             ""]
    lines.append("| key | bytes | ~tok | baseline | drift | status |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for r in result["rows"]:
        cur = "-" if r.get("current_bytes") is None else str(r["current_bytes"])
        tok = "-" if r.get("current_tokens") is None else str(r["current_tokens"])
        base = "-" if r.get("baseline_bytes") is None else str(r["baseline_bytes"])
        drift = "-" if r.get("drift_fraction") is None else f"{r['drift_fraction']*100:+.1f}%"
        status = r["status"]
        if r.get("reason"):
            status += f" ({r['reason']})"
        lines.append(f"| {r['key']} | {cur} | {tok} | {base} | {drift} | {status} |")
    lines.append("")

    # Per-row detail for everything that is not plain-ok.
    for r in result["rows"]:
        if r["status"] == STATUS_OK:
            continue
        lines.append(f"## {r['key']} — {r['status'].upper()}"
                     + (f" ({r['reason']})" if r.get("reason") else ""))
        if r.get("detail"):
            lines.append(f"- {r['detail']}")
        if r["status"] == STATUS_WAIVED and r.get("waiver_rationale"):
            lines.append(f"- waived: {r['waiver_rationale']}")
        attr = r.get("attribution")
        if attr:
            if attr.get("by_purpose_delta"):
                lines.append("- oversized section(s) by purpose (current vs baseline):")
                for d in attr["by_purpose_delta"]:
                    lines.append(f"    - {d['purpose']}: {d['current_bytes']} B "
                                 f"({d['delta']:+d} vs baseline)")
            if attr.get("by_file_delta"):
                lines.append("- changed/new file(s) (largest delta first):")
                for d in attr["by_file_delta"][:10]:
                    lines.append(f"    - {d['path']}: {d['current_bytes']} B "
                                 f"({d['delta']:+d} vs baseline)")
            elif attr.get("largest_current_files"):
                lines.append("- largest current file(s):")
                for d in attr["largest_current_files"]:
                    lines.append(f"    - {d['path']}: {d['bytes']} B")
        lines.append("")

    if result["structural_issues"]:
        lines.append("## structural issues")
        for s in result["structural_issues"]:
            lines.append(f"- {s}")
        lines.append("")

    lines.append(f"drift warn threshold: +{cfg['drift_warn_fraction']*100:.0f}% vs "
                 f"checked-in baseline · absolute anomaly ceiling: "
                 f"{cfg['anomaly_abs_ceiling_bytes']} B "
                 f"(~{_est_tokens(cfg['anomaly_abs_ceiling_bytes'])} tok).")
    lines.append("ADVISORY: a drift WARN is cleared by a reviewed baseline bump OR a "
                 "waiver-with-rationale — never by shrinking sufficient context. Only "
                 "structural anomalies hard-stop.")
    verdict = ("OK" if result["ok"]
               else ("ANOMALY" if result["has_anomaly"] else "UN-WAIVED WARNING"))
    lines.append(f"result: {verdict} (ok={result['ok']}, anomaly={result['has_anomaly']}, "
                 f"unwaived_warning={result['has_unwaived_warning']}).")
    return "\n".join(lines) + "\n"


def _adopter_static_note(adopter_root) -> str:
    """Informational (NOT gated): adopter-static cold-start size (AGENTS.md +
    adoption-state.md). Adopter-static varies per deployment so it is never part of the
    framework baseline; this is a one-off measurement only."""
    res = load_sizer.size_load_set(list(load_sizer.ADOPTER_STATIC), repo_root=adopter_root)
    miss = (", ".join(res["missing"]) if res["missing"] else "-")
    return (f"\nAdopter-static (informational, NOT gated): {res['total_bytes']} B "
            f"≈ {_est_tokens(res['total_bytes'])} tok (missing: {miss}).\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="WP-9 advisory context-budget lint (warning + waiver, not a hard ceiling).")
    ap.add_argument("--repo-root", default=str(REPO_ROOT_DEFAULT),
                    help="framework repo root (default: this checkout's root)")
    ap.add_argument("--adopter-root", default=None,
                    help="also print adopter-static cold-start size (informational, not gated)")
    ap.add_argument("--baseline", default=None, help="baseline YAML path (default: data/)")
    ap.add_argument("--waiver", default=None, help="waiver YAML path (default: data/)")
    ap.add_argument("--emit-baseline", action="store_true",
                    help="regenerate the baseline snapshot from the current tree and write it")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of the text report")
    ap.add_argument("--strict", action="store_true",
                    help="exit nonzero on an un-waived warning too (build-gate semantics); "
                         "default exits nonzero only on an anomaly")
    args = ap.parse_args(argv)

    if args.emit_baseline:
        if yaml is None:
            sys.stderr.write("context_budget_report: PyYAML required for --emit-baseline\n")
            return 2
        baseline = build_baseline(repo_root=args.repo_root)
        out_path = Path(args.baseline) if args.baseline else BASELINE_PATH_DEFAULT
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_dump_yaml(baseline), encoding="utf-8")
        if not args.json:
            print(f"wrote baseline: {out_path}")
        return 0

    result = check(repo_root=args.repo_root, baseline_path=args.baseline,
                   waiver_path=args.waiver)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        out = render_report(result)
        if args.adopter_root:
            out += _adopter_static_note(args.adopter_root)
        print(out, end="")

    if args.strict:
        return 0 if result["ok"] else 1
    return 0 if not result["has_anomaly"] else 1


if __name__ == "__main__":
    sys.exit(main())
