"""skills_preflight — the severity table, row by row.

Row 1 (lock integrity → HARD FAIL), row 2 (required skill unresolvable → HARD FAIL),
row 3 (submodule gitlink drift → HALT unless the audited override), row 4 (pin behind
upstream → advisory WARN only). The read-telemetry row of the original design was
withdrawn in the 2026-07-07 rescope (deployed → selected → injected only).
All fixtures are LOCAL temp trees; git fixtures use only local plumbing (no network).

Run: cd engine-kit && python3.12 -m pytest validators/test_skills_preflight.py -q
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))            # engine-kit/validators
_ENGINE_KIT_DIR = os.path.dirname(_HERE)
for _p in (_HERE, _ENGINE_KIT_DIR, os.path.join(_ENGINE_KIT_DIR, "skill-vendor")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import yaml  # noqa: E402

import skill_vendor  # noqa: E402
import skills_preflight as sp  # noqa: E402

_GIT = shutil.which("git")


# --------------------------------------------------------------------------- #
# Fixture: a minimal, VALID vendored-framework tree (lock + provenance match).
# --------------------------------------------------------------------------- #
def _mk_framework(root, *, skill_id="tdd-mini", role="dev",
                  extra_registry_skills=None):
    """Build <root>/skills/{registry.yaml,skills.lock,vendored/<id>/...} +
    <root>/schemas/ whose hashes verify clean under skill_vendor.verify()."""
    vend = os.path.join(root, "skills", "vendored", skill_id)
    os.makedirs(vend, exist_ok=True)
    os.makedirs(os.path.join(root, "schemas"), exist_ok=True)
    with open(os.path.join(vend, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# {skill_id}\nred/green/refactor.\n")
    with open(os.path.join(vend, "LICENSE"), "w", encoding="utf-8") as fh:
        fh.write("MIT\n")
    per_file = skill_vendor.per_file_hashes(vend)
    tree = skill_vendor.tree_sha256(vend)
    with open(os.path.join(vend, "_provenance.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump({
            "id": skill_id, "tree_sha256": tree,
            "files": [{"path": p[2:], "sha256": h} for p, h in per_file],
        }, fh, sort_keys=False)
    registry = {
        "catalog_version": 1,
        "role_defaults": {role: [skill_id]},
        "skills": {skill_id: {
            "title": skill_id, "role_default_for": role, "license": "MIT",
            "tool_requirements": [], "harness_compat": [], "status": "active",
            "vendored": True,
        }},
    }
    for sid, entry in (extra_registry_skills or {}).items():
        registry["skills"][sid] = entry
    with open(os.path.join(root, "skills", "registry.yaml"), "w",
              encoding="utf-8") as fh:
        yaml.safe_dump(registry, fh, sort_keys=False)
    with open(os.path.join(root, "skills", "skills.lock"), "w",
              encoding="utf-8") as fh:
        yaml.safe_dump({"skills": {skill_id: {"tree_sha256": tree}}}, fh,
                       sort_keys=False)
    return root


def _codes(findings):
    return [f.code for f in findings]


class _FixtureCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = _mk_framework(self._tmp.name)


# --------------------------------------------------------------------------- #
# Row 1 — lock integrity (HARD FAIL).
# --------------------------------------------------------------------------- #
class Row1LockIntegrityTests(_FixtureCase):
    def test_clean_tree_verifies(self):
        findings = sp.check_lock_integrity(self.root)
        self.assertEqual(_codes(findings), ["lock_ok"])

    def test_tampered_vendored_file_hard_fails(self):
        path = os.path.join(self.root, "skills", "vendored", "tdd-mini", "SKILL.md")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("tampered\n")
        findings = sp.check_lock_integrity(self.root)
        self.assertIn("lock_mismatch", _codes(findings))
        self.assertEqual(findings[0].severity, sp.SEVERITY_HARD_FAIL)
        self.assertEqual(findings[0].detail["skill_id"], "tdd-mini")

    def test_registry_vendored_id_missing_from_lock_hard_fails(self):
        # A registry-declared vendored skill with NO lock entry is the same row-1
        # class: an unlocked tree is unverifiable (verify universe = union).
        root = _mk_framework(
            tempfile.mkdtemp(dir=self._tmp.name),
            extra_registry_skills={"ghost": {"vendored": True, "license": "MIT"}})
        findings = sp.check_lock_integrity(root)
        self.assertIn("lock_mismatch", _codes(findings))
        self.assertTrue(any(f.detail.get("skill_id") == "ghost" for f in findings))

    def test_corrupt_lock_hard_fails(self):
        with open(os.path.join(self.root, "skills", "skills.lock"), "w",
                  encoding="utf-8") as fh:
            fh.write("{{{{not yaml\n")
        self.assertEqual(_codes(sp.check_lock_integrity(self.root)),
                         ["lock_unparseable"])

    def test_non_mapping_lock_hard_fails(self):
        with open(os.path.join(self.root, "skills", "skills.lock"), "w",
                  encoding="utf-8") as fh:
            fh.write("just-a-string\n")
        self.assertEqual(_codes(sp.check_lock_integrity(self.root)),
                         ["lock_unparseable"])

    def test_missing_lock_hard_fails(self):
        os.remove(os.path.join(self.root, "skills", "skills.lock"))
        self.assertEqual(_codes(sp.check_lock_integrity(self.root)),
                         ["lock_missing"])

    def test_empty_universe_hard_fails(self):
        with open(os.path.join(self.root, "skills", "skills.lock"), "w",
                  encoding="utf-8") as fh:
            yaml.safe_dump({"skills": {}}, fh)
        with open(os.path.join(self.root, "skills", "registry.yaml"), "w",
                  encoding="utf-8") as fh:
            yaml.safe_dump({"role_defaults": {}, "skills": {}}, fh)
        self.assertEqual(_codes(sp.check_lock_integrity(self.root)),
                         ["verify_universe_empty"])


# --------------------------------------------------------------------------- #
# Row 2 — required skill resolvability (HARD FAIL).
# --------------------------------------------------------------------------- #
class Row2RequiredSkillTests(_FixtureCase):
    def test_role_default_resolves(self):
        charter = {"tooling": {"dev": {"harness": "mock"}}}
        findings = sp.check_required_skills(charter, self.root)
        self.assertEqual(_codes(findings), ["required_skills_ok"])

    def test_charter_bound_ghost_skill_hard_fails(self):
        charter = {"tooling": {"dev": {
            "harness": "mock",
            "skills": {"mode": "extend", "items": ["ghost-skill"]}}}}
        findings = sp.check_required_skills(charter, self.root)
        self.assertIn("required_skill_unresolvable", _codes(findings))
        self.assertEqual(findings[0].detail["role"], "dev")
        self.assertIn("ghost-skill", findings[0].message)

    def test_missing_vendored_dir_hard_fails(self):
        shutil.rmtree(os.path.join(self.root, "skills", "vendored", "tdd-mini"))
        charter = {"tooling": {"dev": {"harness": "mock"}}}
        findings = sp.check_required_skills(charter, self.root)
        self.assertIn("required_skill_unresolvable", _codes(findings))

    def test_no_charter_checks_all_role_defaults(self):
        findings = sp.check_required_skills(None, self.root)
        self.assertEqual(_codes(findings), ["required_skills_ok"])
        self.assertEqual(findings[0].detail["roles"], ["dev"])

    def test_unreadable_catalog_hard_fails(self):
        os.remove(os.path.join(self.root, "skills", "registry.yaml"))
        findings = sp.check_required_skills(None, self.root)
        self.assertEqual(_codes(findings), ["catalog_unreadable"])


# --------------------------------------------------------------------------- #
# Rows 3-4 — git fixtures (local plumbing only; skip when git is unavailable).
# --------------------------------------------------------------------------- #
def _git(args, cwd):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True)


@unittest.skipUnless(_GIT, "git binary unavailable")
class Row3GitlinkDriftTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = self._tmp.name
        # Source framework repo (one commit carrying the valid fixture tree).
        self.fw_src = os.path.join(base, "fw-src")
        os.makedirs(self.fw_src)
        _mk_framework(self.fw_src)
        _git(["init", "-q", "-b", "main"], self.fw_src)
        _git(["add", "-A"], self.fw_src)
        _git(["commit", "-q", "-m", "framework"], self.fw_src)
        # Superproject with the framework as a submodule (file protocol, local).
        self.super_ = os.path.join(base, "adopter")
        os.makedirs(self.super_)
        _git(["init", "-q", "-b", "main"], self.super_)
        _git(["-c", "protocol.file.allow=always", "submodule", "add", "-q",
              self.fw_src, "framework"], self.super_)
        _git(["commit", "-q", "-m", "pin framework"], self.super_)
        self.sub = os.path.join(self.super_, "framework")

    def test_matching_gitlink_is_info(self):
        findings = sp.check_gitlink_drift(self.sub)
        self.assertEqual(_codes(findings), ["gitlink_ok"])

    def test_drifted_working_tree_halts_with_both_commits(self):
        recorded = _git(["rev-parse", "HEAD"], self.sub).stdout.strip()
        _git(["commit", "-q", "--allow-empty", "-m", "drift"], self.sub)
        actual = _git(["rev-parse", "HEAD"], self.sub).stdout.strip()
        findings = sp.check_gitlink_drift(self.sub)
        self.assertEqual(_codes(findings), ["gitlink_drift"])
        f = findings[0]
        self.assertEqual(f.severity, sp.SEVERITY_HALT)
        self.assertEqual(f.detail["recorded_gitlink"], recorded)
        self.assertEqual(f.detail["working_tree_commit"], actual)
        self.assertEqual(f.detail["submodule_path"], "framework")

    def test_plain_repo_is_not_applicable(self):
        findings = sp.check_gitlink_drift(self.fw_src)
        self.assertEqual(_codes(findings), ["gitlink_not_applicable"])

    def test_non_repo_is_undetermined_info(self):
        # A cwd git cannot even run in ⇒ submodule-ness undeterminable ⇒ info
        # (the copied-vendor class must never be blocked by the gitlink check).
        findings = sp.check_gitlink_drift("/nonexistent-path-xyz")
        self.assertEqual(_codes(findings), ["gitlink_undetermined"])

    # ---- enforcement: HALT unless the explicit AUDITED override -------------- #
    def test_enforce_refuses_drift_without_override(self):
        _git(["commit", "-q", "--allow-empty", "-m", "drift"], self.sub)
        with self.assertRaises(sp.SkillsPreflightError) as cm:
            sp.enforce_for_real_run(None, framework_root=self.sub)
        self.assertIn("gitlink", str(cm.exception))
        self.assertIn(sp.GITLINK_OVERRIDE_ENV, str(cm.exception))

    def test_enforce_refuses_override_without_audit_sink(self):
        _git(["commit", "-q", "--allow-empty", "-m", "drift"], self.sub)
        with self.assertRaises(sp.SkillsPreflightError) as cm:
            sp.enforce_for_real_run(None, framework_root=self.sub,
                                    allow_gitlink_drift=True, audit_emit=None)
        self.assertIn("cannot be audited", str(cm.exception))

    def test_enforce_audited_override_passes_and_emits_both_commits(self):
        recorded = _git(["rev-parse", "HEAD"], self.sub).stdout.strip()
        _git(["commit", "-q", "--allow-empty", "-m", "drift"], self.sub)
        actual = _git(["rev-parse", "HEAD"], self.sub).stdout.strip()
        emitted = []
        report = sp.enforce_for_real_run(
            None, framework_root=self.sub,
            allow_gitlink_drift=True, audit_emit=emitted.append)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].detail["recorded_gitlink"], recorded)
        self.assertEqual(emitted[0].detail["working_tree_commit"], actual)
        self.assertTrue(report.halts)      # the finding is still ON the report

    def test_enforce_clean_submodule_no_emit(self):
        emitted = []
        sp.enforce_for_real_run(None, framework_root=self.sub,
                                allow_gitlink_drift=True,
                                audit_emit=emitted.append)
        self.assertEqual(emitted, [])


@unittest.skipUnless(_GIT, "git binary unavailable")
class Row4PinFreshnessTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = _mk_framework(os.path.join(self._tmp.name, "fw"))
        os.makedirs(self.root, exist_ok=True)
        _git(["init", "-q", "-b", "main"], self.root)
        _git(["add", "-A"], self.root)
        _git(["commit", "-q", "-m", "one"], self.root)

    def _fake_origin(self, sha):
        _git(["update-ref", "refs/remotes/origin/main", sha], self.root)
        _git(["symbolic-ref", "refs/remotes/origin/HEAD",
              "refs/remotes/origin/main"], self.root)

    def test_behind_local_upstream_warns_advisory_only(self):
        _git(["commit", "-q", "--allow-empty", "-m", "two"], self.root)
        newer = _git(["rev-parse", "HEAD"], self.root).stdout.strip()
        _git(["reset", "-q", "--hard", "HEAD~1"], self.root)
        self._fake_origin(newer)
        findings = sp.check_pin_freshness(self.root)
        self.assertEqual(_codes(findings), ["pin_behind_upstream"])
        f = findings[0]
        self.assertEqual(f.severity, sp.SEVERITY_WARN)
        self.assertEqual(f.detail["commits_behind"], 1)
        # WARN only — never blocking (frozen row 4).
        report = sp.PreflightReport(findings=findings)
        self.assertFalse(report.blocking)

    def test_fresh_pin_is_info(self):
        head = _git(["rev-parse", "HEAD"], self.root).stdout.strip()
        self._fake_origin(head)
        self.assertEqual(_codes(sp.check_pin_freshness(self.root)), ["pin_fresh"])

    def test_no_remote_tracking_ref_is_undetermined(self):
        self.assertEqual(_codes(sp.check_pin_freshness(self.root)),
                         ["pin_undetermined"])

    def test_non_worktree_is_undetermined(self):
        plain = os.path.join(self._tmp.name, "not-a-repo-anywhere")
        self.assertEqual(_codes(sp.check_pin_freshness(plain)),
                         ["pin_undetermined"])


# --------------------------------------------------------------------------- #
# The full checker + enforcement policy.
# --------------------------------------------------------------------------- #
class RunPreflightTests(_FixtureCase):
    def test_clean_fixture_not_blocking(self):
        charter = {"tooling": {"dev": {"harness": "mock"}}}
        report = sp.run_preflight(charter, framework_root=self.root)
        self.assertFalse(report.blocking)
        self.assertIn("lock_ok", _codes(report.findings))
        self.assertIn("required_skills_ok", _codes(report.findings))

    def test_enforce_raises_on_hard_fail(self):
        with open(os.path.join(self.root, "skills", "vendored", "tdd-mini",
                               "SKILL.md"), "a", encoding="utf-8") as fh:
            fh.write("tampered\n")
        with self.assertRaises(sp.SkillsPreflightError) as cm:
            sp.enforce_for_real_run(None, framework_root=self.root)
        self.assertIn("lock_mismatch", str(cm.exception))
        self.assertIn("refusing the real run", str(cm.exception))

    def test_enforce_clean_returns_report(self):
        report = sp.enforce_for_real_run(None, framework_root=self.root)
        self.assertFalse(report.blocking)

    def test_missing_framework_root_hard_fails(self):
        report = sp.run_preflight(None, framework_root=os.path.join(
            self._tmp.name, "nope"))
        # No registry.yaml under the given root ⇒ row-1/row-2 hard failures.
        self.assertTrue(report.blocking)


# --------------------------------------------------------------------------- #
# CLI (the standalone adopter checker).
# --------------------------------------------------------------------------- #
class CliTests(_FixtureCase):
    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sp.main(argv)
        return rc, buf.getvalue()

    def test_clean_exit_0(self):
        rc, out = self._run(["--root", self.root])
        self.assertEqual(rc, 0)
        self.assertIn("lock_ok", out)

    def test_tampered_exit_1(self):
        with open(os.path.join(self.root, "skills", "vendored", "tdd-mini",
                               "SKILL.md"), "a", encoding="utf-8") as fh:
            fh.write("tampered\n")
        rc, out = self._run(["--root", self.root])
        self.assertEqual(rc, 1)
        self.assertIn("lock_mismatch", out)

    def test_json_output_parses(self):
        rc, out = self._run(["--root", self.root, "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertFalse(data["blocking"])
        self.assertTrue(any(f["code"] == "lock_ok" for f in data["findings"]))

    def test_unreadable_charter_exit_2(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = sp.main(["--root", self.root,
                          "--charter", os.path.join(self._tmp.name, "nope.json")])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
