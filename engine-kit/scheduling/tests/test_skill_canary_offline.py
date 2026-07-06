"""Phase-5 canary — OFFLINE proofs (zero billables; the real canary is driven by
examples/skill-canary/run_canary.py --live under AIDAZI_SKILL_CANARY=1 and is NEVER
run from this suite).

Committed guarantees:
  * the deterministic scorers implement EXACTLY the frozen pre-registration
    contracts (scorer ≡ gamma-checklist.json / alpha-manifest.json, self-verified —
    a doctored contract raises ContractMismatch, never silent re-scoring);
  * scorer unit behavior on the frozen rules (α id-set/ui/non-ui; γ Check-0 forcing
    zero; β stream-read matching incl. relative-path resolution);
  * the FULL harness plumbing dry-run: real vendor-framework.sh scratch adopters,
    the vendored-engine ws_runner subprocess, evidence collection, scoring and the
    frozen budget/replacement accounting — all with MockAdapter (no real spawn, no
    AIDAZI_ALLOW_REAL_ADAPTER anywhere);
  * the budget ledger's frozen caps: refusal beyond planned+replacements, and
    crash-resume idempotency of the adapter-error count.

Run: cd engine-kit && python3.12 -m pytest scheduling/tests/test_skill_canary_offline.py -q
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_KIT_DIR = os.path.dirname(os.path.dirname(_TESTS_DIR))
_REPO_ROOT = os.path.dirname(_ENGINE_KIT_DIR)
_CANARY_DIR = os.path.join(_REPO_ROOT, "examples", "skill-canary")
for _p in (_CANARY_DIR,):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import scorers  # noqa: E402
import offline_fixtures  # noqa: E402
import run_canary  # noqa: E402


class ContractEquivalenceTests(unittest.TestCase):
    def test_frozen_gamma_contract_matches_scorer(self):
        contract = scorers.load_gamma_contract()      # raises on divergence
        self.assertEqual([c["id"] for c in contract["checks"]],
                         list(range(1, 11)))

    def test_doctored_contract_raises(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(scorers.PREREG_DIR, "gamma-checklist.json")
            with open(src, encoding="utf-8") as fh:
                doc = json.load(fh)
            doc["score_margin_required"] = 1          # tamper
            path = os.path.join(d, "gamma-checklist.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            with self.assertRaises(scorers.ContractMismatch):
                scorers.load_gamma_contract(path)

    def test_frozen_alpha_manifest_loads(self):
        manifest = scorers.load_alpha_manifest()
        self.assertEqual(manifest["vocab"],
                         ["a11y", "design", "frontend", "interaction",
                          "performance", "ui"])


class AlphaScorerTests(unittest.TestCase):
    FIXTURE = {"prescribed_subsprints": {"s1-ui": "ui", "s2-api": "non_ui"}}
    VOCAB = ["a11y", "design", "frontend", "interaction", "performance", "ui"]

    def _plan(self, entries):
        return {"sub_sprints": entries}

    def test_conformant_plan_passes(self):
        res = scorers.alpha_score_rep(self._plan([
            {"id": "s1-ui", "task_signals": ["ui", "a11y"]},
            {"id": "s2-api"}]), self.FIXTURE, self.VOCAB)
        self.assertTrue(res["pass"])

    def test_missing_and_extra_ids_fail(self):
        res = scorers.alpha_score_rep(self._plan([
            {"id": "s1-ui", "task_signals": ["ui"]},
            {"id": "renamed"}]), self.FIXTURE, self.VOCAB)
        self.assertFalse(res["pass"])
        self.assertFalse(res["id_set_ok"])
        self.assertEqual(res["extra_ids"], ["renamed"])

    def test_ui_requires_nonempty_in_vocab_signals(self):
        for bad in ([], None):
            entries = [{"id": "s1-ui"}, {"id": "s2-api"}]
            if bad is not None:
                entries[0]["task_signals"] = bad
            res = scorers.alpha_score_rep(self._plan(entries),
                                          self.FIXTURE, self.VOCAB)
            self.assertFalse(res["pass"], f"ui with {bad!r} must fail")

    def test_non_ui_must_omit_or_empty(self):
        ok = scorers.alpha_score_rep(self._plan([
            {"id": "s1-ui", "task_signals": ["ui"]},
            {"id": "s2-api", "task_signals": []}]), self.FIXTURE, self.VOCAB)
        self.assertTrue(ok["pass"], "explicit empty array is a valid omission")
        bad = scorers.alpha_score_rep(self._plan([
            {"id": "s1-ui", "task_signals": ["ui"]},
            {"id": "s2-api", "task_signals": ["performance"]}]),
            self.FIXTURE, self.VOCAB)
        self.assertFalse(bad["pass"], "a signal on a non-ui sub-sprint fails")

    def test_deterministic(self):
        plan = self._plan([{"id": "s1-ui", "task_signals": ["ui"]},
                           {"id": "s2-api"}])
        self.assertEqual(scorers.alpha_score_rep(plan, self.FIXTURE, self.VOCAB),
                         scorers.alpha_score_rep(plan, self.FIXTURE, self.VOCAB))


class GammaScorerTests(unittest.TestCase):
    def _write(self, root, files):
        for rel, content in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)

    def test_good_artifact_scores_ten(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, offline_fixtures.GOOD_ARTIFACT)
            res = scorers.gamma_score_artifact(d)
            self.assertTrue(res["check0"]["complete"], res["check0"])
            self.assertEqual(res["score"], 10, res["checks"])

    def test_poor_artifact_low_score_but_complete(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, offline_fixtures.POOR_ARTIFACT)
            res = scorers.gamma_score_artifact(d)
            self.assertTrue(res["check0"]["complete"], res["check0"])
            self.assertLessEqual(res["score"], 4, res["checks"])

    def test_check0_failure_forces_zero(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, {"page.html": "<html><body><h1>x</h1></body></html>"})
            res = scorers.gamma_score_artifact(d)
            self.assertFalse(res["check0"]["complete"])
            self.assertEqual(res["score"], 0)

    def test_vendored_and_framework_dirs_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, offline_fixtures.GOOD_ARTIFACT)
            # a stray HTML inside aidazi/ must NOT enter the artifact universe
            self._write(d, {"aidazi/skills/x.html": "<h1>a</h1><h1>b</h1>"})
            res = scorers.gamma_score_artifact(d)
            self.assertEqual(res["score"], 10)

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, offline_fixtures.POOR_ARTIFACT)
            self.assertEqual(scorers.gamma_score_artifact(d),
                             scorers.gamma_score_artifact(d))

    def test_pair_rule(self):
        a, b = {"score": 7}, {"score": 5}
        self.assertTrue(scorers.gamma_pair_success(a, b, True, margin=2))
        self.assertFalse(scorers.gamma_pair_success(a, b, False, margin=2),
                         "arm-A skill read is REQUIRED")
        self.assertFalse(scorers.gamma_pair_success(
            {"score": 6}, b, True, margin=2), "margin is >= B + 2")


class BetaReadTests(unittest.TestCase):
    def _stream(self, paths):
        return "\n".join(json.dumps(
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": p}}]}}) for p in paths)

    def test_absolute_match(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "SKILL.md")
            res = scorers.beta_read_observed(self._stream([target]), target)
            self.assertTrue(res["observed"])

    def test_relative_resolves_against_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "aidazi", "SKILL.md")
            res = scorers.beta_read_observed(
                self._stream([os.path.join("aidazi", "SKILL.md")]),
                target, cwd=d)
            self.assertTrue(res["observed"])

    def test_other_reads_do_not_match(self):
        res = scorers.beta_read_observed(
            self._stream(["/somewhere/else.md"]), "/target/SKILL.md")
        self.assertFalse(res["observed"])
        self.assertEqual(res["all_read_paths"], ["/somewhere/else.md"])


class BudgetTests(unittest.TestCase):
    def test_cap_refusal_and_idempotent_adapter_errors(self):
        with tempfile.TemporaryDirectory() as d:
            b = run_canary.Budget(os.path.join(d, "budget.json"))
            for i in range(run_canary.PLANNED["beta"]
                           + run_canary.MAX_REPLACEMENTS_PER_PROBE):
                b.pre_spawn("beta", f"r{i}", live=True)
                b.post_spawn(f"r{i}", "completed")
            with self.assertRaisesRegex(RuntimeError, "BUDGET REFUSAL"):
                b.pre_spawn("beta", "over", live=True)
            # adapter-error count is rep-keyed ⇒ crash-resume never double-counts
            self.assertEqual(b.record_adapter_error("alpha", "a-rep1"), 1)
            self.assertEqual(b.record_adapter_error("alpha", "a-rep1"), 1)
            self.assertEqual(b.record_adapter_error("alpha", "a-rep2"), 2)

    def test_offline_attempts_never_consume_the_real_budget(self):
        with tempfile.TemporaryDirectory() as d:
            b = run_canary.Budget(os.path.join(d, "budget.json"))
            for i in range(20):
                b.pre_spawn("gamma", f"o{i}", live=False)
            self.assertEqual(b.real_attempts("gamma"), 0)


@unittest.skipUnless(shutil.which("bash") and shutil.which("rsync"),
                     "bash/rsync unavailable — cannot run vendor-framework.sh")
class OfflineHarnessDryRunTests(unittest.TestCase):
    """The FULL harness path with MockAdapter only: vendor → seed → vendored-engine
    subprocess → evidence → scorers → aggregation. Proves the plumbing the real
    (billable) run rides on, without a single real spawn."""

    def test_live_flag_requires_the_dedicated_env_gate(self):
        env_backup = os.environ.pop("AIDAZI_SKILL_CANARY", None)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf), self.assertRaises(SystemExit):
                run_canary.main(["--live", "--evidence-dir", "/tmp/never"])
            self.assertIn("AIDAZI_SKILL_CANARY", buf.getvalue())
        finally:
            if env_backup is not None:
                os.environ["AIDAZI_SKILL_CANARY"] = env_backup

    def test_scratch_adopter_is_wired(self):
        # The 2026-07-07 live-run incident class: a vendored-but-UNWIRED scratch
        # adopter starves the spawned agent's cold-start chain. Every workspace
        # must carry the documented root-file wiring.
        with tempfile.TemporaryDirectory() as d:
            h = run_canary.Harness(d, live=False)
            ws = h._build_ws("dev")
            try:
                with open(os.path.join(ws, "CLAUDE.md"), encoding="utf-8") as fh:
                    self.assertEqual(fh.read().strip(), "@AGENTS.md")
                with open(os.path.join(ws, "AGENTS.md"), encoding="utf-8") as fh:
                    agents = fh.read()
                self.assertIn("p5-canary-scratch", agents)
                self.assertNotIn("<adopter-name>", agents)
                self.assertTrue(os.path.isfile(
                    os.path.join(ws, "aidazi", "AGENTS.md")))
            finally:
                shutil.rmtree(ws, ignore_errors=True)

    def test_full_offline_dry_run_passes_all_probes(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = run_canary.main(["--offline-dry-run", "--evidence-dir", d])
            self.assertEqual(rc, 0, buf.getvalue())
            with open(os.path.join(d, "results.json"), encoding="utf-8") as fh:
                results = json.load(fh)
            self.assertTrue(results["overall_pass"])
            self.assertTrue(results["alpha"]["pass"])
            for fx in results["alpha"]["fixtures"].values():
                self.assertTrue(fx["fixture_pass"])
            self.assertTrue(results["beta"]["pass"])
            beta = results["beta"]["reps"][0]["detail"]
            self.assertEqual(beta["signal_source"], "charter_scope")
            self.assertEqual(beta["selected_skills"],
                             ["web-interface-guidelines"])
            self.assertEqual(beta["audit_skill_consumption"], "observed")
            self.assertTrue(results["gamma"]["pass"])
            pair = results["gamma"]["pairs"][0]
            self.assertEqual(pair["score_A"], 10)
            self.assertTrue(pair["arm_a_read"])
            # zero REAL attempts anywhere (the budget ledger proves no billable)
            with open(os.path.join(d, "budget.json"), encoding="utf-8") as fh:
                budget = json.load(fh)
            self.assertTrue(all(not a["live"] for a in budget["attempts"]))


if __name__ == "__main__":
    unittest.main()
