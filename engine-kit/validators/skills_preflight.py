#!/usr/bin/env python3
"""skills_preflight — integrity/drift preflight for the deployed skill surface.

BEFORE a real run mounts any skill, verify that what is ON DISK is what was signed/locked,
and that the deployed framework is the framework the adopter's superproject records. The
checker is OFFLINE and deterministic — no network, no LLM, no clock beyond git's own
metadata; it REUSES ``skill_vendor.verify()`` (the lock's own ``tree_sha256`` algorithm —
NOT ``effective_role_config._tree_hash``, which hashes a different file universe and would
false-fail valid trees) and ``effective_role_config.resolve_role_config`` (the exact
resolve-time fail-closed path the driver runs at spawn), so preflight verdicts and runtime
behaviour can never disagree about WHAT a skill hashes to or WHETHER a binding resolves.

THE SEVERITY TABLE (four rows; the original design's fifth, informational row was
withdrawn in the 2026-07-07 rescope — archive/2026-07-07-universal-skill-mounting-
rescope.md; the delivery guarantee is deployed → selected → injected):

  row 1  skills.lock vs vendored tree mismatch (skill_vendor.verify() fails)
             → HARD FAIL (real runs).  The verify universe is the UNION of the lock's ids
               and the registry's ``vendored: true`` ids, so a registry-declared skill with
               no lock entry is the same mismatch class (an unlocked tree is unverifiable).
  row 2  required registry skill (role default / charter-bound) missing or unresolvable
             → HARD FAIL (real runs).  Preflight surfaces it early; the driver's
               resolve-time fail-closed (_effective_role → gate_hard_fail) remains.
               Signal-SELECTED skills are OPTIONAL bindings (skip-if-absent, §2.2/§2.3)
               and are therefore NOT "required" here.
  row 3  real-loop submodule working-tree commit ≠ recorded superproject gitlink
             → HALT / fail closed, UNLESS an explicit audited override flag is set —
               the override is recorded as an audit event carrying BOTH commits.
               The AirPlat class is never warning-only in a formal run. Once the
               framework is KNOWN to be a submodule, an unreadable gitlink is ALSO a
               HALT (integrity-indeterminate is fail-closed); only "cannot even tell
               whether this is a submodule" (no git / not a work tree — the copied-vendor
               class) degrades to informational.
  row 4  adopter pin behind upstream / newer upstream skills available
             → advisory WARN only.  Checked OFFLINE against the local remote-tracking
               ref (as of the adopter's last fetch) — NO network fetch is ever performed
               (locked decision: no network skill fetch). Undeterminable ⇒ informational.

ENFORCEMENT SPLIT: ``run_preflight`` is the pure read-only checker (returns every finding);
``enforce_for_real_run`` applies the severity policy for a real (``--allow-real``) run —
raise on any HARD FAIL; HALT on gitlink drift unless the explicit override flag is set AND
an audit sink is available to record it (an override that cannot be audited is REFUSED —
"audited override" is one thing, not two). WARN/info never block anywhere. Mock/dry runs
never call the enforcement (mirrors enforce_charter_for_real_run).

CLI (the standalone adopter checker)::

    python skills_preflight.py [--charter charter.json] [--root FRAMEWORK_ROOT]
                               [--adopter-root DIR] [--json]

Exit code: 1 iff any HARD FAIL or HALT finding exists (the CLI reports the truth; the
audited override is a RUN-time gate concern, not a checker concern), else 0 — WARN/info
are advisory. 2 on usage errors (unreadable charter).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
from typing import Any, Callable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))            # engine-kit/validators
_ENGINE_KIT_DIR = os.path.dirname(_HERE)                      # engine-kit/
for _p in (_ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "skill-vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import skill_vendor  # noqa: E402  (engine-kit/skill-vendor on sys.path above)
import effective_role_config as effective_roles  # noqa: E402


# --------------------------------------------------------------------------- #
# Severities + findings.
# --------------------------------------------------------------------------- #
SEVERITY_HARD_FAIL = "hard_fail"   # rows 1-2 — refuse the real run
SEVERITY_HALT = "halt"             # row 3 — fail closed unless audited override
SEVERITY_WARN = "warn"             # row 4 — advisory only
SEVERITY_INFO = "info"             # not-applicable/undetermined/ok notes

#: The explicit audited-override flag for row-3 gitlink drift (design §4 row 3). Set to
#: "1" (or pass ``--allow-gitlink-drift`` / ``allow_gitlink_drift=True``) to let a real
#: run proceed ON a drifted submodule — the override is ALWAYS recorded as an audit
#: event carrying both commits; with no audit sink available the override is refused.
GITLINK_OVERRIDE_ENV = "AIDAZI_SKILLS_ALLOW_GITLINK_DRIFT"

#: The audit event type the override emits (payload carries both commits).
GITLINK_OVERRIDE_EVENT = "skills_preflight_gitlink_override"


class SkillsPreflightError(ValueError):
    """The skills preflight REFUSES a real run (hard failure / un-overridden HALT).

    A ValueError so run_loop's existing except-ValueError fail-closed mapping
    (→ CharterValidationError → the INVALID exit) applies unchanged."""


@dataclasses.dataclass(frozen=True)
class Finding:
    row: int                # the severity-table row (1-4)
    severity: str           # SEVERITY_*
    code: str               # stable machine-readable id
    message: str            # human-readable one-liner
    detail: dict = dataclasses.field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"row": self.row, "severity": self.severity, "code": self.code,
                "message": self.message, "detail": dict(self.detail)}

    def render(self) -> str:
        tag = {SEVERITY_HARD_FAIL: "FAIL", SEVERITY_HALT: "HALT",
               SEVERITY_WARN: "WARN", SEVERITY_INFO: "info"}[self.severity]
        return f"[{tag}] row{self.row}/{self.code}: {self.message}"


@dataclasses.dataclass
class PreflightReport:
    findings: list = dataclasses.field(default_factory=list)

    def _sev(self, severity: str) -> list:
        return [f for f in self.findings if f.severity == severity]

    @property
    def hard_failures(self) -> list:
        return self._sev(SEVERITY_HARD_FAIL)

    @property
    def halts(self) -> list:
        return self._sev(SEVERITY_HALT)

    @property
    def warnings(self) -> list:
        return self._sev(SEVERITY_WARN)

    @property
    def infos(self) -> list:
        return self._sev(SEVERITY_INFO)

    @property
    def blocking(self) -> bool:
        """True iff a real run would be refused absent an override (rows 1-3)."""
        return bool(self.hard_failures or self.halts)

    def as_dict(self) -> dict:
        return {"findings": [f.as_dict() for f in self.findings],
                "blocking": self.blocking}

    def render(self) -> str:
        lines = [f.render() for f in self.findings]
        if not lines:
            lines = ["skills_preflight: no findings."]
        lines.append(
            f"skills_preflight: {len(self.hard_failures)} hard-fail, "
            f"{len(self.halts)} halt, {len(self.warnings)} warn, "
            f"{len(self.infos)} info.")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# git plumbing (rows 3-4). Local-only — NO network subcommand is ever invoked.
# --------------------------------------------------------------------------- #
def _git(args: list, cwd: str) -> tuple:
    """Run a LOCAL git plumbing command; (rc, stdout_stripped). rc -1 = could not
    execute at all (no git binary / cwd missing) — callers treat that as
    'undeterminable', distinct from git's own nonzero exits."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return proc.returncode, (proc.stdout or "").strip()


def check_gitlink_drift(framework_root: str) -> list:
    """Row 3 — real-loop submodule working tree vs the recorded superproject gitlink.

    Detection: ``git rev-parse --show-superproject-working-tree`` from the framework
    root. Empty output (exit 0) ⇒ NOT a submodule (e.g. the framework is committed
    directly inside the adopter repo, the vendor-framework.sh copy class) ⇒
    informational not-applicable. Command unexecutable / not a work tree ⇒
    informational undetermined (we cannot even name a superproject to drift from).
    Once a superproject IS named, every subsequent failure is integrity-indeterminate
    ⇒ HALT (fail closed): a submodule whose recorded gitlink cannot be read is exactly
    as untrustworthy as one that differs."""
    rc, superproject = _git(
        ["rev-parse", "--show-superproject-working-tree"], framework_root)
    if rc != 0:
        return [Finding(
            row=3, severity=SEVERITY_INFO, code="gitlink_undetermined",
            message="submodule status undeterminable (git unavailable or the "
                    "framework root is not inside a git work tree); the gitlink "
                    "check does not apply",
            detail={"framework_root": framework_root})]
    if not superproject:
        return [Finding(
            row=3, severity=SEVERITY_INFO, code="gitlink_not_applicable",
            message="framework is not a git submodule (no superproject); the "
                    "gitlink check does not apply",
            detail={"framework_root": framework_root})]

    def _halt(reason: str, **extra: Any) -> list:
        return [Finding(
            row=3, severity=SEVERITY_HALT, code="gitlink_indeterminate",
            message=f"framework IS a submodule of {superproject} but the gitlink "
                    f"comparison could not be completed ({reason}); integrity is "
                    "indeterminate — fail closed",
            detail={"framework_root": framework_root,
                    "superproject": superproject, **extra})]

    rc, toplevel = _git(["rev-parse", "--show-toplevel"], framework_root)
    if rc != 0 or not toplevel:
        return _halt("submodule toplevel unreadable")
    rc, actual = _git(["rev-parse", "HEAD"], toplevel)
    if rc != 0 or not actual:
        return _halt("submodule HEAD unreadable")
    rel = os.path.relpath(os.path.realpath(toplevel),
                          os.path.realpath(superproject)).replace(os.sep, "/")
    # The INDEX gitlink (what `git submodule status` compares against; falls back to
    # HEAD's tree for a bare-index edge). Format: "160000 <sha> 0\t<path>".
    recorded = None
    rc, out = _git(["ls-files", "-s", "--", rel], superproject)
    if rc == 0 and out:
        fields = out.split()
        if len(fields) >= 2 and fields[0] == "160000":
            recorded = fields[1]
    if recorded is None:
        rc, out = _git(["ls-tree", "HEAD", "--", rel], superproject)
        if rc == 0 and out:
            fields = out.split()
            if len(fields) >= 3 and fields[0] == "160000":
                recorded = fields[2]
    if recorded is None:
        return _halt("no gitlink entry for the submodule path in the superproject "
                     "index or HEAD tree", submodule_path=rel)
    if recorded != actual:
        return [Finding(
            row=3, severity=SEVERITY_HALT, code="gitlink_drift",
            message=f"submodule working-tree commit {actual[:12]} differs from the "
                    f"recorded superproject gitlink {recorded[:12]} at {rel!r} — the "
                    "deployed framework is NOT the one the adopter pinned (fail "
                    "closed; requires the explicit audited override)",
            detail={"framework_root": framework_root, "superproject": superproject,
                    "submodule_path": rel, "recorded_gitlink": recorded,
                    "working_tree_commit": actual})]
    return [Finding(
        row=3, severity=SEVERITY_INFO, code="gitlink_ok",
        message=f"submodule working-tree commit matches the recorded superproject "
                f"gitlink ({actual[:12]})",
        detail={"submodule_path": rel, "commit": actual})]


def check_pin_freshness(framework_root: str) -> list:
    """Row 4 — adopter pin behind upstream: advisory WARN ONLY, checked offline.

    Compares HEAD to the LOCAL remote-tracking ref (the current branch's
    ``@{upstream}``; else ``origin/HEAD``'s target) — i.e. "behind upstream AS OF the
    adopter's last fetch". NO network fetch is performed (locked decision), so a
    stale local remote can under-report; the message says so. Undeterminable (copied
    vendor / no remote-tracking ref) ⇒ informational."""
    def _info(msg: str) -> list:
        return [Finding(row=4, severity=SEVERITY_INFO, code="pin_undetermined",
                        message=msg, detail={"framework_root": framework_root})]

    rc, inside = _git(["rev-parse", "--is-inside-work-tree"], framework_root)
    if rc != 0 or inside != "true":
        return _info("pin freshness undeterminable (framework root is not a git "
                     "work tree — the copied-vendor class); advisory only")
    upstream = None
    rc, out = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name",
                    "@{upstream}"], framework_root)
    if rc == 0 and out:
        upstream = out
    if upstream is None:
        rc, out = _git(["symbolic-ref", "refs/remotes/origin/HEAD"], framework_root)
        if rc == 0 and out.startswith("refs/remotes/"):
            upstream = out[len("refs/remotes/"):]
    if upstream is None:
        return _info("pin freshness undeterminable (no remote-tracking ref for the "
                     "current branch and no origin/HEAD); advisory only")
    rc, count = _git(["rev-list", "--count", f"HEAD..{upstream}"], framework_root)
    if rc != 0 or not count.isdigit():
        return _info(f"pin freshness undeterminable (rev-list vs {upstream} failed); "
                     "advisory only")
    behind = int(count)
    if behind > 0:
        return [Finding(
            row=4, severity=SEVERITY_WARN, code="pin_behind_upstream",
            message=f"framework pin is {behind} commit(s) behind {upstream} as of "
                    "the last local fetch (advisory only — no network fetch was "
                    "performed; newer upstream skills may be available)",
            detail={"framework_root": framework_root, "upstream": upstream,
                    "commits_behind": behind})]
    return [Finding(
        row=4, severity=SEVERITY_INFO, code="pin_fresh",
        message=f"framework pin is up to date with {upstream} as of the last "
                "local fetch",
        detail={"upstream": upstream})]


# --------------------------------------------------------------------------- #
# Rows 1-2 — lock integrity + required-skill resolvability.
# --------------------------------------------------------------------------- #
def check_lock_integrity(framework_root: str) -> list:
    """Row 1 — REUSE ``skill_vendor.verify()`` over the union of the lock's ids and
    the registry's ``vendored: true`` ids. Any per-skill mismatch, a missing/corrupt
    lock, an unreadable registry, or an EMPTY verify universe (an aidazi deployment
    always vendors skills) is the same class: the on-disk skill surface cannot be
    proven to be the locked one ⇒ HARD FAIL (real runs)."""
    def _fail(code: str, msg: str, **extra: Any) -> Finding:
        return Finding(row=1, severity=SEVERITY_HARD_FAIL, code=code, message=msg,
                       detail={"framework_root": framework_root, **extra})

    try:
        lock = skill_vendor.load_lock(framework_root)
    except skill_vendor.LockfileError as exc:
        return [_fail("lock_unparseable", str(exc))]
    except (OSError, FileNotFoundError) as exc:
        return [_fail("lock_missing", f"skills/skills.lock unreadable: {exc}")]
    if not isinstance(lock, dict):
        return [_fail("lock_unparseable",
                      f"skills.lock root must be a mapping, got {type(lock).__name__}")]
    try:
        registry = skill_vendor.load_registry(framework_root)
    except Exception as exc:  # noqa: BLE001 — unreadable/invalid YAML registry
        return [_fail("registry_unreadable",
                      f"skills/registry.yaml unreadable: {exc}")]
    if not isinstance(registry, dict):
        return [_fail("registry_unreadable",
                      "skills/registry.yaml root must be a mapping, got "
                      f"{type(registry).__name__}")]

    lock_skills = lock.get("skills")
    lock_ids = set(lock_skills.keys()) if isinstance(lock_skills, dict) else set()
    reg_skills = registry.get("skills")
    reg_vendored = {
        sid for sid, entry in (reg_skills.items()
                               if isinstance(reg_skills, dict) else ())
        if isinstance(entry, dict) and entry.get("vendored") is True}
    ids = sorted(lock_ids | reg_vendored)
    if not ids:
        return [_fail("verify_universe_empty",
                      "no vendored skills in skills.lock or registry.yaml — the "
                      "skill surface cannot be verified")]

    report = skill_vendor.verify(ids, repo_root=framework_root)
    out: list = []
    for res in report.results:
        if not res.ok:
            out.append(_fail(
                "lock_mismatch",
                f"vendored skill {res.skill_id!r} fails lock/provenance "
                f"verification: {'; '.join(res.messages)}",
                skill_id=res.skill_id, messages=list(res.messages)))
    if not out:
        out.append(Finding(
            row=1, severity=SEVERITY_INFO, code="lock_ok",
            message=f"all {len(report.results)} vendored skill(s) match "
                    "skills.lock + provenance",
            detail={"verified": len(report.results)}))
    return out


#: The charter tooling keys that route a role (mirrors run_loop._roles_in_charter).
_CHARTER_ROLES = ("research", "deliver", "dev", "review", "acceptance")


def _routed_roles(charter: Optional[dict]) -> list:
    tooling = (charter or {}).get("tooling") or {}
    return [r for r in _CHARTER_ROLES if r in tooling]


def check_required_skills(charter: Optional[dict], framework_root: str,
                          adopter_root: Optional[str] = None) -> list:
    """Row 2 — every REQUIRED skill binding (role default / charter-bound) must
    resolve. REUSES ``resolve_role_config`` — the exact spawn-time path — with empty
    ``task_signals`` (signal-selected skills are OPTIONAL/skip-if-absent, never
    "required"). With no charter (the bare CLI mode) every catalog ``role_defaults``
    role is checked instead. An ``EffectiveConfigError`` ⇒ HARD FAIL for that role
    (this is the driver's resolve-time gate_hard_fail, surfaced BEFORE any adapter
    or model is built)."""
    charter = charter or {}
    try:
        catalog = effective_roles.load_skill_catalog(framework_root)
    except effective_roles.EffectiveConfigError as exc:
        return [Finding(row=2, severity=SEVERITY_HARD_FAIL, code="catalog_unreadable",
                        message=str(exc), detail={"framework_root": framework_root})]
    roles = _routed_roles(charter)
    if not roles:
        roles = sorted((catalog.get("role_defaults") or {}).keys())
    out: list = []
    resolved_roles = 0
    for role in roles:
        try:
            effective_roles.resolve_role_config(
                charter, role, task_signals=(),
                framework_root=framework_root, adopter_root=adopter_root,
                catalog=catalog)
            resolved_roles += 1
        except effective_roles.EffectiveConfigError as exc:
            out.append(Finding(
                row=2, severity=SEVERITY_HARD_FAIL, code="required_skill_unresolvable",
                message=f"role {role!r}: required skill binding does not resolve — "
                        f"{exc}",
                detail={"role": role, "framework_root": framework_root,
                        "adopter_root": adopter_root, "error": str(exc)}))
    if not out:
        out.append(Finding(
            row=2, severity=SEVERITY_INFO, code="required_skills_ok",
            message=f"required skill bindings resolve for all {resolved_roles} "
                    "checked role(s)",
            detail={"roles": list(roles)}))
    return out


# --------------------------------------------------------------------------- #
# The checker + the real-run enforcement.
# --------------------------------------------------------------------------- #
def run_preflight(charter: Optional[dict] = None, *,
                  framework_root: Optional[str] = None,
                  adopter_root: Optional[str] = None) -> PreflightReport:
    """Run every severity row and return the full report (pure read-only — no env
    reads, no audit writes, no severity policy; that's ``enforce_for_real_run``)."""
    framework_root = framework_root or effective_roles.find_framework_root()
    report = PreflightReport()
    if not framework_root:
        report.findings.append(Finding(
            row=1, severity=SEVERITY_HARD_FAIL, code="framework_root_not_found",
            message="framework root (containing skills/registry.yaml + schemas/) "
                    "not found — the skill surface cannot be verified"))
        return report
    report.findings.extend(check_lock_integrity(framework_root))
    report.findings.extend(check_required_skills(charter, framework_root,
                                                 adopter_root))
    report.findings.extend(check_gitlink_drift(framework_root))
    report.findings.extend(check_pin_freshness(framework_root))
    return report


def enforce_for_real_run(charter: Optional[dict], *,
                         framework_root: Optional[str] = None,
                         adopter_root: Optional[str] = None,
                         allow_gitlink_drift: bool = False,
                         audit_emit: Optional[Callable[[Finding], None]] = None,
                         ) -> PreflightReport:
    """Apply the frozen severity policy for a REAL run. Raises
    ``SkillsPreflightError`` (a ValueError) on any row-1/row-2 HARD FAIL, and on a
    row-3 HALT unless ``allow_gitlink_drift`` is set AND ``audit_emit`` is available
    to record the override (an override that cannot be audited is refused — the
    contract says AUDITED override, fail closed). ``audit_emit`` is called once per
    HALT finding with the finding (the caller appends the audit event carrying both
    commits). WARN/info findings never raise; the returned report carries them for
    non-silent display."""
    report = run_preflight(charter, framework_root=framework_root,
                           adopter_root=adopter_root)
    if report.hard_failures:
        raise SkillsPreflightError(
            "skills preflight FAILED; refusing the real run BEFORE any adapter is "
            "invoked:\n" + "\n".join(f"  - {f.render()}"
                                     for f in report.hard_failures))
    if report.halts:
        if not allow_gitlink_drift:
            raise SkillsPreflightError(
                "skills preflight HALT (gitlink drift is never warning-only in a "
                "formal run); refusing the real run BEFORE any adapter is invoked. "
                f"Set the explicit audited override ({GITLINK_OVERRIDE_ENV}=1 or "
                "--allow-gitlink-drift) ONLY if this drift is intentional:\n"
                + "\n".join(f"  - {f.render()}" for f in report.halts))
        if audit_emit is None:
            raise SkillsPreflightError(
                "gitlink-drift override was requested but NO audit sink is "
                "available to record it — an override that cannot be audited is "
                "refused (fail closed):\n"
                + "\n".join(f"  - {f.render()}" for f in report.halts))
        for f in report.halts:
            audit_emit(f)
    return report


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline skills integrity/drift preflight: lock integrity, "
                    "required-skill resolvability, submodule gitlink drift, "
                    "pin freshness (advisory).")
    parser.add_argument("--charter", default=None,
                        help="charter JSON (optional; without it, every catalog "
                             "role_defaults role is checked)")
    parser.add_argument("--root", default=None,
                        help="framework root (default: auto-discover the tree "
                             "containing skills/registry.yaml + schemas/)")
    parser.add_argument("--adopter-root", default=None,
                        help="adopter repo root for local skill-path bindings")
    parser.add_argument("--json", action="store_true",
                        help="emit the machine-readable findings JSON")
    args = parser.parse_args(argv)

    charter = None
    if args.charter:
        try:
            with open(args.charter, encoding="utf-8") as fh:
                charter = json.load(fh)
        except (OSError, ValueError) as exc:
            sys.stderr.write(f"skills_preflight: charter unreadable: {exc}\n")
            return 2

    report = run_preflight(charter, framework_root=args.root,
                           adopter_root=args.adopter_root)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(report.render())
    return 1 if report.blocking else 0


if __name__ == "__main__":
    sys.exit(main())
