"""WP-9 context-budget lint — deterministic gate tests (stdlib unittest).

The HEAD gate (``HeadGateTests``) runs the REAL checked-in baseline + waiver through
``check()`` against the real tree and asserts: no anomaly, no un-waived warning. Every
other test is hermetic: it sizes against the REAL tree (so the numbers are real) but feeds
a SYNTHETIC baseline / waiver written to a temp file — this exercises drift / waiver /
anomaly / fail-safe paths without mutating any tracked governance doc. No LLM, no network.

Covers the WP-9 required-test matrix:
  * warning fires over threshold; NO warning for any current role/task (no FP at HEAD);
  * oversized-section attribution is correct;
  * waiver suppresses + records rationale (non-silent); a waiver cannot hide an anomaly;
  * each anomaly hard-stops AND is non-vacuous (proven unable to fire on a normal role);
  * determinism (byte-identical report); malformed/missing baseline+waiver fail safe.
"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_VALIDATORS_DIR = os.path.dirname(_TESTS_DIR)
_ENGINE_KIT_DIR = os.path.dirname(_VALIDATORS_DIR)
for _p in (_VALIDATORS_DIR, _ENGINE_KIT_DIR,
           os.path.join(_ENGINE_KIT_DIR, "orchestrator"),
           os.path.join(_ENGINE_KIT_DIR, "audit"),
           os.path.join(_ENGINE_KIT_DIR, "memory")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

import context_budget_report as cbr  # noqa: E402
import lesson_selection  # noqa: E402

REAL_REPO = cbr.REPO_ROOT_DEFAULT


def _write_yaml(path: Path, obj) -> Path:
    path.write_text(yaml.safe_dump(obj, sort_keys=True, allow_unicode=True),
                    encoding="utf-8")
    return path


def _tmp() -> Path:
    d = Path(tempfile.mkdtemp(prefix="wp9_"))
    return d


@unittest.skipIf(yaml is None, "PyYAML not installed")
class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _real_baseline(self) -> dict:
        """A real baseline dict measured from the live tree (current == baseline)."""
        return cbr.build_baseline(repo_root=REAL_REPO)

    def _entry(self, baseline: dict, key: str) -> dict:
        for e in baseline["entries"]:
            if e["key"] == key:
                return e
        raise KeyError(key)

    def _check(self, baseline: dict, waivers=None):
        bpath = _write_yaml(self.tmp / "baseline.yaml", baseline)
        wpath = None
        if waivers is not None:
            wpath = _write_yaml(self.tmp / "waivers.yaml",
                                {"version": 1, "waivers": waivers})
        return cbr.check(repo_root=REAL_REPO, baseline_path=bpath, waiver_path=wpath)

    def _row(self, result: dict, key: str) -> dict:
        for r in result["rows"]:
            if r["key"] == key:
                return r
        raise KeyError(key)


# --------------------------------------------------------------------------- #
class HeadGateTests(_Base):
    """The real checked-in baseline + waiver vs the real tree — the build-time gate."""

    def test_real_head_is_ok(self):
        result = cbr.check()  # default paths = the checked-in data/
        self.assertTrue(result["ok"], msg=str(result["rows"]))
        self.assertFalse(result["has_anomaly"])
        self.assertFalse(result["has_unwaived_warning"])
        self.assertEqual(result["structural_issues"], [])

    def test_no_current_role_or_task_warns_or_anomalies(self):
        result = cbr.check()
        for r in result["rows"]:
            self.assertEqual(r["status"], cbr.STATUS_OK,
                             msg=f"{r['key']} is {r['status']} ({r.get('reason')})")

    def test_checked_in_baseline_covers_every_tracked_entry(self):
        # The committed baseline must have a positive entry for every BUDGET_ENTRIES key
        # (else that key would be a missing_baseline anomaly).
        baseline, issue = cbr._load_baseline(cbr.BASELINE_PATH_DEFAULT)
        self.assertIsNone(issue)
        keys = {e["key"] for e in baseline["entries"]}
        for e in cbr.BUDGET_ENTRIES:
            self.assertIn(e["key"], keys)

    def test_heaviest_role_has_headroom_below_abs_ceiling(self):
        # Non-vacuity of A1 in the other direction: NO real role is near the ceiling.
        result = cbr.check()
        ceiling = result["config"]["anomaly_abs_ceiling_bytes"]
        heaviest = max(r["current_bytes"] for r in result["rows"]
                       if r.get("current_bytes") is not None)
        self.assertLess(heaviest, ceiling)
        self.assertGreater(ceiling, heaviest * 2)  # documented >2x margin


# --------------------------------------------------------------------------- #
class DriftWarnTests(_Base):
    def test_drift_warns_when_over_threshold(self):
        baseline = self._real_baseline()
        dl = self._entry(baseline, "deliver")
        dl["total_bytes"] = int(dl["total_bytes"] * 0.5)  # current is now ~2x baseline
        result = self._check(baseline)
        row = self._row(result, "deliver")
        self.assertEqual(row["status"], cbr.STATUS_WARN)
        self.assertEqual(row["reason"], cbr.REASON_DRIFT)
        self.assertTrue(result["has_unwaived_warning"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["has_anomaly"])
        # other rows unaffected.
        self.assertEqual(self._row(result, "review")["status"], cbr.STATUS_OK)

    def test_no_warn_when_within_threshold(self):
        baseline = self._real_baseline()
        dl = self._entry(baseline, "deliver")
        # baseline 5% below current → drift +5.3% < +10% → still ok.
        dl["total_bytes"] = int(dl["total_bytes"] / 1.05)
        result = self._check(baseline)
        self.assertEqual(self._row(result, "deliver")["status"], cbr.STATUS_OK)

    def test_attribution_identifies_the_specific_oversized_file(self):
        baseline = self._real_baseline()
        dl = self._entry(baseline, "deliver")
        card = "role-cards/deliver-agent.md"
        card_bytes = dl["files"][card]
        # Drop exactly one file from the baseline + lower the total by its size → that file
        # is the sole grower; drift fires because the card is >10% of the total.
        del dl["files"][card]
        dl["by_purpose"]["role_card"] -= card_bytes
        dl["total_bytes"] -= card_bytes
        result = self._check(baseline)
        row = self._row(result, "deliver")
        self.assertEqual(row["status"], cbr.STATUS_WARN)
        attr = row["attribution"]
        self.assertEqual(len(attr["by_file_delta"]), 1)
        self.assertEqual(attr["by_file_delta"][0]["path"], card)
        self.assertEqual(attr["by_file_delta"][0]["delta"], card_bytes)
        self.assertEqual(attr["by_file_delta"][0]["baseline_bytes"], 0)
        # purpose attribution names role_card as the grower.
        purposes = {d["purpose"]: d["delta"] for d in attr["by_purpose_delta"]}
        self.assertEqual(purposes.get("role_card"), card_bytes)


# --------------------------------------------------------------------------- #
class WaiverTests(_Base):
    def _drifting_baseline(self):
        baseline = self._real_baseline()
        self._entry(baseline, "deliver")["total_bytes"] = int(
            self._entry(baseline, "deliver")["total_bytes"] * 0.5)
        return baseline

    def test_waiver_suppresses_drift_and_records_rationale(self):
        baseline = self._drifting_baseline()
        result = self._check(baseline, waivers=[
            {"key": "deliver", "rationale": "M4 added a legitimate domain briefing doc"}])
        row = self._row(result, "deliver")
        self.assertEqual(row["status"], cbr.STATUS_WAIVED)
        self.assertEqual(row["waiver_rationale"],
                         "M4 added a legitimate domain briefing doc")
        # waived is ok; no un-waived warning remains.
        self.assertTrue(result["ok"])
        self.assertFalse(result["has_unwaived_warning"])
        # NON-SILENT: the rendered report shows the rationale.
        report = cbr.render_report(result)
        self.assertIn("waived: M4 added a legitimate domain briefing doc", report)
        self.assertIn("deliver", report)

    def test_waiver_for_other_key_does_not_suppress(self):
        baseline = self._drifting_baseline()
        result = self._check(baseline, waivers=[
            {"key": "review", "rationale": "unrelated"}])
        self.assertEqual(self._row(result, "deliver")["status"], cbr.STATUS_WARN)

    def test_waiver_without_rationale_is_ignored_and_noted(self):
        baseline = self._drifting_baseline()
        result = self._check(baseline, waivers=[{"key": "deliver", "rationale": "   "}])
        self.assertEqual(self._row(result, "deliver")["status"], cbr.STATUS_WARN)
        self.assertTrue(any("missing rationale" in s
                            for s in result["structural_issues"]))

    def test_waiver_cannot_hide_abs_ceiling_anomaly(self):
        baseline = self._real_baseline()
        baseline["anomaly_abs_ceiling_bytes"] = 1000  # everything is now over the ceiling
        result = self._check(baseline, waivers=[
            {"key": "deliver", "rationale": "trying to hide an anomaly"}])
        row = self._row(result, "deliver")
        self.assertEqual(row["status"], cbr.STATUS_ANOMALY)
        self.assertEqual(row["reason"], cbr.ANOM_ABS_CEILING)
        self.assertTrue(result["has_anomaly"])
        self.assertFalse(result["ok"])


# --------------------------------------------------------------------------- #
class AnomalyTests(_Base):
    def test_abs_ceiling_anomaly_fires(self):
        baseline = self._real_baseline()
        baseline["anomaly_abs_ceiling_bytes"] = 1000
        result = self._check(baseline)
        self.assertTrue(result["has_anomaly"])
        self.assertEqual(self._row(result, "deliver")["reason"], cbr.ANOM_ABS_CEILING)

    def test_abs_ceiling_does_not_fire_on_normal_role(self):
        # Non-vacuity: at the real ceiling, the heaviest real role is NOT an anomaly.
        result = cbr.check()
        self.assertNotEqual(self._row(result, "deliver")["status"], cbr.STATUS_ANOMALY)

    def test_missing_baseline_entry_anomaly(self):
        baseline = self._real_baseline()
        baseline["entries"] = [e for e in baseline["entries"] if e["key"] != "deliver"]
        result = self._check(baseline)
        row = self._row(result, "deliver")
        self.assertEqual(row["status"], cbr.STATUS_ANOMALY)
        self.assertEqual(row["reason"], cbr.ANOM_MISSING_BASELINE)

    def test_zero_baseline_entry_anomaly(self):
        baseline = self._real_baseline()
        self._entry(baseline, "deliver")["total_bytes"] = 0
        result = self._check(baseline)
        self.assertEqual(self._row(result, "deliver")["reason"], cbr.ANOM_MISSING_BASELINE)

    def test_missing_cold_start_root_anomaly(self):
        # An empty repo_root → every mandatory cold-start root is missing → missing_root
        # anomaly (structurally-broken load set). Proven non-vacuous; at HEAD missing=[].
        empty = self.tmp / "empty_repo"
        empty.mkdir()
        bpath = _write_yaml(self.tmp / "baseline.yaml", self._real_baseline())
        result = cbr.check(repo_root=empty, baseline_path=bpath)
        self.assertTrue(result["has_anomaly"])
        gov = self._row(result, "governance-floor")
        self.assertEqual(gov["status"], cbr.STATUS_ANOMALY)
        self.assertEqual(gov["reason"], cbr.ANOM_MISSING_ROOT)

    def test_lesson_bound_disabled_is_anomaly(self):
        with mock.patch.object(lesson_selection, "DEFAULT_BUDGET",
                               lesson_selection.LessonBudget(max_l1_count=0, max_l1_bytes=0)):
            result = cbr.check()
        row = self._row(result, cbr.KEY_LESSON_BOUND)
        self.assertEqual(row["status"], cbr.STATUS_ANOMALY)
        self.assertEqual(row["reason"], cbr.ANOM_LESSON_BOUND_DISABLED)
        self.assertTrue(result["has_anomaly"])

    def test_lesson_bound_is_ok_when_real(self):
        # Non-vacuity the other way: the real DEFAULT_BUDGET (8, 4096) is NOT an anomaly.
        result = cbr.check()
        self.assertEqual(self._row(result, cbr.KEY_LESSON_BOUND)["status"], cbr.STATUS_OK)

    def test_lesson_bound_narrow_single_disabled_is_not_anomaly(self):
        # NARROWNESS: only BOTH ceilings disabled is an anomaly. One positive ceiling still
        # bounds L1 → ok.
        for budget in (lesson_selection.LessonBudget(max_l1_count=8, max_l1_bytes=0),
                       lesson_selection.LessonBudget(max_l1_count=0, max_l1_bytes=4096)):
            with mock.patch.object(lesson_selection, "DEFAULT_BUDGET", budget):
                result = cbr.check()
            self.assertEqual(self._row(result, cbr.KEY_LESSON_BOUND)["status"],
                             cbr.STATUS_OK, msg=str(budget))

    def test_lesson_bound_anomaly_not_waivable(self):
        with mock.patch.object(lesson_selection, "DEFAULT_BUDGET",
                               lesson_selection.LessonBudget(max_l1_count=0, max_l1_bytes=0)):
            result = self._check(self._real_baseline(),
                                 waivers=[{"key": cbr.KEY_LESSON_BOUND,
                                           "rationale": "trying to hide"}])
        self.assertEqual(self._row(result, cbr.KEY_LESSON_BOUND)["status"],
                         cbr.STATUS_ANOMALY)


# --------------------------------------------------------------------------- #
class FailSafeTests(_Base):
    def test_missing_baseline_file_is_global_anomaly(self):
        result = cbr.check(repo_root=REAL_REPO,
                           baseline_path=self.tmp / "does-not-exist.yaml")
        self.assertFalse(result["ok"])
        self.assertTrue(result["has_anomaly"])
        self.assertEqual(result["rows"][0]["reason"], cbr.ANOM_BASELINE_UNREADABLE)

    def test_unparseable_baseline_file_fail_closed(self):
        bad = self.tmp / "bad.yaml"
        bad.write_text("not: a: valid: mapping: [", encoding="utf-8")
        result = cbr.check(repo_root=REAL_REPO, baseline_path=bad)
        self.assertTrue(result["has_anomaly"])
        self.assertEqual(result["rows"][0]["reason"], cbr.ANOM_BASELINE_UNREADABLE)

    def test_baseline_without_entries_list_fail_closed(self):
        bad = _write_yaml(self.tmp / "noentries.yaml", {"version": 1})
        result = cbr.check(repo_root=REAL_REPO, baseline_path=bad)
        self.assertTrue(result["has_anomaly"])
        self.assertEqual(result["rows"][0]["reason"], cbr.ANOM_BASELINE_UNREADABLE)

    def test_malformed_waiver_file_surfaces_warnings_not_hides(self):
        baseline = self._real_baseline()
        self._entry(baseline, "deliver")["total_bytes"] = int(
            self._entry(baseline, "deliver")["total_bytes"] * 0.5)
        bpath = _write_yaml(self.tmp / "baseline.yaml", baseline)
        bad_waiver = self.tmp / "waivers.yaml"
        bad_waiver.write_text("waivers: not-a-list\n", encoding="utf-8")
        result = cbr.check(repo_root=REAL_REPO, baseline_path=bpath, waiver_path=bad_waiver)
        # the drift is SURFACED (not suppressed) + a structural issue is recorded.
        self.assertEqual(self._row(result, "deliver")["status"], cbr.STATUS_WARN)
        self.assertTrue(any("waiver file malformed" in s
                            for s in result["structural_issues"]))

    def test_missing_waiver_file_is_valid_no_issue(self):
        baseline = self._real_baseline()
        bpath = _write_yaml(self.tmp / "baseline.yaml", baseline)
        result = cbr.check(repo_root=REAL_REPO, baseline_path=bpath,
                           waiver_path=self.tmp / "no-waivers.yaml")
        self.assertEqual(result["structural_issues"], [])
        self.assertTrue(result["ok"])


# --------------------------------------------------------------------------- #
class DeterminismTests(_Base):
    def test_check_and_report_are_deterministic(self):
        r1 = cbr.check()
        r2 = cbr.check()
        self.assertEqual(cbr.render_report(r1), cbr.render_report(r2))
        import json
        self.assertEqual(json.dumps(r1, sort_keys=True), json.dumps(r2, sort_keys=True))

    def test_emit_baseline_is_byte_identical(self):
        a = cbr._dump_yaml(cbr.build_baseline(repo_root=REAL_REPO))
        b = cbr._dump_yaml(cbr.build_baseline(repo_root=REAL_REPO))
        self.assertEqual(a, b)

    def test_checked_in_baseline_is_a_current_snapshot(self):
        # The committed baseline is a STABLE snapshot, not an exact-on-every-edit mirror
        # (the drift THRESHOLD is the headroom that lets normal variation pass — an exact
        # match gate would make a sub-threshold prose edit fail, defeating the doctrine).
        # So we only assert the committed snapshot is CURRENT ENOUGH that no key already
        # warns/anomalies at HEAD (i.e. it was regenerated when this WP landed).
        result = cbr.check()
        self.assertTrue(result["ok"], msg="committed baseline is stale enough that a key "
                        "already warns — regenerate with --emit-baseline")


# --------------------------------------------------------------------------- #
class CliExitCodeTests(_Base):
    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cbr.main(argv)
        return rc, buf.getvalue()

    def test_default_and_strict_green_at_head(self):
        self.assertEqual(self._run([])[0], 0)
        self.assertEqual(self._run(["--strict"])[0], 0)

    def test_default_advisory_on_drift_strict_fails(self):
        baseline = self._real_baseline()
        self._entry(baseline, "deliver")["total_bytes"] = int(
            self._entry(baseline, "deliver")["total_bytes"] * 0.5)
        bpath = _write_yaml(self.tmp / "baseline.yaml", baseline)
        # default CLI: a drift warning is ADVISORY → exit 0.
        rc, _ = self._run(["--baseline", str(bpath)])
        self.assertEqual(rc, 0)
        # --strict: an un-waived warning fails the build gate → exit 1.
        rc, _ = self._run(["--strict", "--baseline", str(bpath)])
        self.assertEqual(rc, 1)

    def test_anomaly_fails_default_and_strict(self):
        rc, _ = self._run(["--baseline", str(self.tmp / "nope.yaml")])
        self.assertEqual(rc, 1)
        rc, _ = self._run(["--strict", "--baseline", str(self.tmp / "nope.yaml")])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
