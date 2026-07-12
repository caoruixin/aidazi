"""Cluster-2 tests for adopter_init.py (design §4 / §10).

Proves the scaffolding CORE: answers -> a tree that makes all four adoption validators GREEN,
plus the fail-closed invariants I1 (pure build_artifacts), I2 (guarded dest / never the
framework repo), I3 (never auto-confirm the gate-1 signature).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
import adopter_init as ai  # noqa: E402

_VALIDATORS_DIR = os.path.join(os.path.dirname(_TOOLS_DIR), "validators")
if _VALIDATORS_DIR not in sys.path:
    sys.path.insert(0, _VALIDATORS_DIR)
import adopter_wiring_validator as awv  # noqa: E402
import charter_validator  # noqa: E402
import control_plane_validator  # noqa: E402
import adoption_status  # noqa: E402

_FRAMEWORK_ROOT = os.path.dirname(os.path.dirname(_TOOLS_DIR))  # <root>/engine-kit/tools -> <root>
_CANARY_ANSWERS = os.path.join(_FRAMEWORK_ROOT, "examples", "adopter-init-canary", "answers.json")


def _load_plan():
    return ai.load_answers(_CANARY_ANSWERS, _FRAMEWORK_ROOT)


class BuildArtifactsPurityTests(unittest.TestCase):
    def test_build_artifacts_is_deterministic_and_no_framework_arg(self):
        # I1: build_artifacts takes PRE-LOADED templates (not framework_root), so it structurally
        # cannot read the framework tree; and it is deterministic.
        plan = _load_plan()
        templates = ai.load_templates(_FRAMEWORK_ROOT)
        a1 = ai.build_artifacts(plan, templates)
        a2 = ai.build_artifacts(plan, templates)
        self.assertEqual(a1, a2)
        # the required artifacts are present in the pure map
        for rel in ("charter.yaml", "AGENTS.md", "CLAUDE.md",
                    os.path.join(".cursor", "rules", "00-aidazi-governance.mdc"),
                    "docs/current/adoption-state.md", ".gitignore"):
            self.assertIn(rel, a1, msg=f"missing artifact {rel}")

    def test_charter_artifact_is_schema_valid(self):
        plan = _load_plan()
        templates = ai.load_templates(_FRAMEWORK_ROOT)
        artifacts = ai.build_artifacts(plan, templates)
        with tempfile.TemporaryDirectory(prefix="ai-charter-") as d:
            path = os.path.join(d, "charter.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(artifacts["charter.yaml"])
            rep = charter_validator.validate_file(path)
            self.assertTrue(rep.ok, msg="\n".join(str(e) for e in rep.errors))

    def test_omitted_capability_ref_not_inherited_from_template(self):
        # [C2 B-2] a role that omits capability_ref must NOT keep the template's stale ref.
        data = json.load(open(_CANARY_ANSWERS))
        data["llm_roles"]["dev"] = {"harness": "claude_code", "provider": "anthropic",
                                    "model": "claude-sonnet-4-6"}  # no capability_ref
        with tempfile.TemporaryDirectory(prefix="ai-capref-") as d:
            apath = os.path.join(d, "a.json")
            json.dump(data, open(apath, "w"))
            plan = ai.load_answers(apath, _FRAMEWORK_ROOT)
            charter_text = ai.build_artifacts(plan, ai.load_templates(_FRAMEWORK_ROOT))["charter.yaml"]
            charter = __import__("yaml").safe_load(charter_text)
            self.assertNotIn("capability_ref", charter["tooling"]["dev"])

    def test_i3_unsigned_brief_omits_the_token(self):
        # I3: with confirmed_by_human false the brief body must NOT carry the confirmed token.
        data = json.load(open(_CANARY_ANSWERS))
        data["research_brief"]["confirmed_by_human"] = False
        with tempfile.TemporaryDirectory(prefix="ai-unsigned-") as d:
            apath = os.path.join(d, "a.json")
            json.dump(data, open(apath, "w"))
            plan = ai.load_answers(apath, _FRAMEWORK_ROOT)
            templates = ai.load_templates(_FRAMEWORK_ROOT)
            artifacts = ai.build_artifacts(plan, templates)
            brief = next(v for k, v in artifacts.items() if k.startswith("docs/research-briefs/"))
            self.assertNotIn("confirmed_by_human: true", brief)
            self.assertIn("confirmed_by_human: false", brief)


class GuardTests(unittest.TestCase):
    def test_i2_refuses_framework_repo(self):
        with self.assertRaises(ai.InitError):
            ai.assert_writable_dest(_FRAMEWORK_ROOT, _FRAMEWORK_ROOT)

    def test_i2_refuses_dest_nested_in_framework(self):
        nested = os.path.join(_FRAMEWORK_ROOT, "engine-kit", "tools", "nope-adopter")
        with self.assertRaises(ai.InitError):
            ai.assert_writable_dest(nested, _FRAMEWORK_ROOT)

    def test_i2_allows_external_dest(self):
        with tempfile.TemporaryDirectory(prefix="ai-ok-") as d:
            ai.assert_writable_dest(os.path.join(d, "acme"), _FRAMEWORK_ROOT)  # no raise

    def test_materialize_guards_before_write(self):
        # materialize must refuse a framework-repo dest without writing.
        plan = _load_plan()
        templates = ai.load_templates(_FRAMEWORK_ROOT)
        artifacts = ai.build_artifacts(plan, templates)
        with self.assertRaises(ai.InitError):
            ai.materialize(artifacts, _FRAMEWORK_ROOT, _FRAMEWORK_ROOT)

    def test_run_exit_validators_guards_the_readiness_write(self):
        # [C2 B-4] the readiness write path must be behind the I2 guard too.
        with self.assertRaises(ai.InitError):
            ai.run_exit_validators(_FRAMEWORK_ROOT, _FRAMEWORK_ROOT)

    def test_emit_answers_into_framework_refused(self):
        # [R3 B-1] --emit-answers must never write INTO the framework tree.
        with self.assertRaises(ai.InitError):
            ai._assert_not_in_framework(os.path.join(_FRAMEWORK_ROOT, "leak.json"), _FRAMEWORK_ROOT)
        with tempfile.TemporaryDirectory(prefix="ai-emit-ok-") as d:
            ai._assert_not_in_framework(os.path.join(d, "ok.json"), _FRAMEWORK_ROOT)  # no raise

    def test_symlink_escape_child_write_refused(self):
        # [R3 B-2] a brownfield dest whose child dir symlinks outside must not let a write escape.
        with tempfile.TemporaryDirectory(prefix="ai-esc-") as tmp:
            dest = os.path.join(tmp, "dest")
            outside = os.path.join(tmp, "outside")
            os.makedirs(dest)
            os.makedirs(outside)
            os.symlink(outside, os.path.join(dest, "docs"))  # docs/ -> outside dest
            plan = _load_plan()
            artifacts = ai.build_artifacts(plan, ai.load_templates(_FRAMEWORK_ROOT))
            with self.assertRaises(ai.InitError):
                ai.materialize(artifacts, dest, _FRAMEWORK_ROOT, force=True)
            # nothing leaked into the symlinked-out dir
            self.assertEqual(os.listdir(outside), [])

    def test_tmp_symlink_escape_write_refused(self):
        # [R3.2 B-1] a pre-planted <file>.tmp symlink escaping dest must not be written through the
        # atomic-write path. The create-missing path now writes create-only (O_EXCL, NO .tmp), so
        # this exercises the REGENERATE (--overwrite) path where _atomic_write (+ its .tmp) is still
        # used. (The create path's own symlink safety is covered by
        # test_create_missing_symlink_target_escape_refused + test_atomic_write_refuses_symlinked_tmp.)
        with tempfile.TemporaryDirectory(prefix="ai-tmpesc-") as tmp:
            dest = os.path.join(tmp, "dest")
            outside = os.path.join(tmp, "outside")
            os.makedirs(dest)
            os.makedirs(outside)
            leak = os.path.join(outside, "leak")
            with open(os.path.join(dest, "AGENTS.md"), "w", encoding="utf-8") as fh:
                fh.write("existing\n")  # exists -> --overwrite takes the _atomic_write branch
            os.symlink(leak, os.path.join(dest, "AGENTS.md.tmp"))  # pre-plant the tmp symlink
            plan = _load_plan()
            artifacts = ai.build_artifacts(plan, ai.load_templates(_FRAMEWORK_ROOT))
            with self.assertRaises(ai.InitError):
                ai.materialize(artifacts, dest, _FRAMEWORK_ROOT, force=True, overwrite=True)
            self.assertFalse(os.path.exists(leak))  # never written through the symlink

    def test_readiness_symlink_escape_surfaces_as_exit_3_not_crash(self):
        # [consolidate B1] run_exit_validators is a write site that can raise InitError (the readiness
        # target escapes dest via a pre-planted symlink that materialize PRESERVES). The CLI must
        # surface that as the documented exit-3 refusal, not an uncaught crash / exit 1.
        with tempfile.TemporaryDirectory(prefix="ai-rdysym-") as tmp:
            dest = os.path.join(tmp, "acme")
            self.assertEqual(ai.main([dest, "--answers", _CANARY_ANSWERS]), 0)  # greenfield GREEN
            outside = os.path.join(tmp, "outside")
            os.makedirs(outside)
            readiness = os.path.join(dest, "docs", "current", "adoption-readiness.md")
            os.remove(readiness)
            os.symlink(os.path.join(outside, "leak"), readiness)  # readiness now escapes dest
            rc = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc, 3, "readiness symlink-escape must surface as exit 3, not a crash")
            self.assertFalse(os.path.exists(os.path.join(outside, "leak")))  # never written through

    def test_readiness_symlink_to_in_dest_governed_doc_refused(self):
        # [consolidate B1] readiness planted as an IN-DEST symlink to a governed doc passes
        # _assert_target_within_dest (it resolves inside dest) but the open("w") refresh would FOLLOW
        # it and clobber the referent. The tool must refuse fail-closed (exit 3); AGENTS.md unchanged.
        with tempfile.TemporaryDirectory(prefix="ai-rdylink-") as tmp:
            dest = os.path.join(tmp, "acme")
            self.assertEqual(ai.main([dest, "--answers", _CANARY_ANSWERS]), 0)  # greenfield GREEN
            agents = os.path.join(dest, "AGENTS.md")
            agents_before = ai._read_text(agents)
            readiness = os.path.join(dest, "docs", "current", "adoption-readiness.md")
            os.remove(readiness)
            os.symlink(os.path.join("..", "..", "AGENTS.md"), readiness)  # -> dest/AGENTS.md (in dest)
            rc = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc, 3, "an in-dest readiness symlink must be refused (exit 3), not followed")
            self.assertEqual(ai._read_text(agents), agents_before, "AGENTS.md must not be clobbered")

    def test_create_missing_symlink_target_escape_refused(self):
        # [R3 B-2] the create-missing path is still symlink-guarded: a pre-planted target that is a
        # symlink escaping dest is refused by materialize's resolved-target check BEFORE the
        # create-only write — nothing is created through the symlink.
        with tempfile.TemporaryDirectory(prefix="ai-cesc-") as tmp:
            dest = os.path.join(tmp, "dest")
            outside = os.path.join(tmp, "outside")
            os.makedirs(dest)
            os.makedirs(outside)
            leak = os.path.join(outside, "leak")
            os.symlink(leak, os.path.join(dest, "AGENTS.md"))  # the target itself escapes dest
            plan = _load_plan()
            artifacts = ai.build_artifacts(plan, ai.load_templates(_FRAMEWORK_ROOT))
            with self.assertRaises(ai.InitError):
                ai.materialize(artifacts, dest, _FRAMEWORK_ROOT, force=True)
            self.assertFalse(os.path.exists(leak))  # never created through the symlink

    def test_atomic_write_refuses_symlinked_tmp(self):
        # [R3.2 B-1] direct _atomic_write unit: a symlinked <target>.tmp is refused (O_NOFOLLOW).
        with tempfile.TemporaryDirectory(prefix="ai-aw-") as tmp:
            outside = os.path.join(tmp, "outside")
            target = os.path.join(tmp, "f.txt")
            os.symlink(outside, target + ".tmp")
            with self.assertRaises(ai.InitError):
                ai._atomic_write(target, "content")
            self.assertFalse(os.path.exists(outside))


class ScaffoldGreenTests(unittest.TestCase):
    def _scaffold(self, tmp, answers=_CANARY_ANSWERS, force=False):
        dest = os.path.join(tmp, "acme")
        rc = ai.main([dest, "--answers", answers] + (["--force"] if force else []))
        return dest, rc

    def test_scratch_dir_all_four_validators_green(self):
        with tempfile.TemporaryDirectory(prefix="ai-green-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0, "adopter_init did not exit 0 (green)")
            # Independently re-run each validator against the produced tree (design C2 obligation a).
            self.assertTrue(charter_validator.validate_file(os.path.join(dest, "charter.yaml")).ok)
            self.assertTrue(awv.validate_root(dest).ok)
            self.assertTrue(control_plane_validator.validate_root(dest).ok)
            self.assertTrue(adoption_status.validate_adoption(dest).ok)
            # cursor role => a valid .cursor/rules that passes the C1 validator.
            self.assertTrue(os.path.isfile(
                os.path.join(dest, ".cursor", "rules", "00-aidazi-governance.mdc")))
            self.assertIn("cursor", awv.validate_root(dest).targets)
            # framework mounted under aidazi/, NOT the dest root (I2 non-collision).
            self.assertTrue(os.path.isfile(
                os.path.join(dest, "aidazi", "engine-kit", "orchestrator", "driver.py")))
            self.assertFalse(adoption_status.is_framework_repo(dest))
            # vendored skills mounted ([C2 B-5]).
            self.assertTrue(os.path.isdir(os.path.join(dest, "aidazi", "skills")))

    def test_force_preserves_human_edited_brief(self):
        # [C2 B-3] --force without --overwrite must NOT clobber a human-edited seed brief.
        with tempfile.TemporaryDirectory(prefix="ai-brief-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0)
            brief = next(os.path.join(dest, "docs", "research-briefs", f)
                         for f in os.listdir(os.path.join(dest, "docs", "research-briefs")))
            with open(brief, "a", encoding="utf-8") as fh:
                fh.write("\n<!-- human edit to the brief -->\n")
            rc2 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc2, 0)
            self.assertIn("human edit to the brief", ai._read_text(brief))

    def test_idempotent_force_rerun_stays_green_no_clobber(self):
        with tempfile.TemporaryDirectory(prefix="ai-idem-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0)
            # hand-edit the charter, then re-run WITHOUT --overwrite: charter must be preserved.
            charter_path = os.path.join(dest, "charter.yaml")
            with open(charter_path, "a", encoding="utf-8") as fh:
                fh.write("\n# human edit\n")
            rc2 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc2, 0)
            self.assertIn("# human edit", ai._read_text(charter_path))

    def test_intent_unconfirmed_is_not_green_even_with_signed_brief(self):
        # [R3 B-3] the four validators only check the brief token; an unconfirmed INTENT contract
        # must still make the tool report NOT green (the intent signature is enforced end-to-end).
        data = json.load(open(_CANARY_ANSWERS))
        data["intent_contract"]["confirmed_by_human"] = False  # intent NOT confirmed
        # research_brief stays confirmed => adoption_status alone would be green
        with tempfile.TemporaryDirectory(prefix="ai-intent-") as tmp:
            apath = os.path.join(tmp, "a.json")
            json.dump(data, open(apath, "w"))
            rc = ai.main([os.path.join(tmp, "acme"), "--answers", apath, "--probe", "off"])
            self.assertEqual(rc, 2, "unconfirmed intent contract must NOT be green")

    def test_readiness_snapshot_reflects_final_green_state(self):
        # [R3 B-4] the readiness snapshot must record the FINAL state, not the pre-readiness
        # report that shows adoption-readiness.md as still-missing.
        with tempfile.TemporaryDirectory(prefix="ai-rdy-") as tmp:
            dest = os.path.join(tmp, "acme")
            self.assertEqual(ai.main([dest, "--answers", _CANARY_ANSWERS, "--probe", "off"]), 0)
            readiness = ai._read_text(os.path.join(dest, "docs", "current", "adoption-readiness.md"))
            self.assertNotIn("--write-readiness after Step 8", readiness)  # not recorded missing
            self.assertNotIn("missing", readiness.lower())

    def test_unsigned_brief_scaffolds_but_not_green(self):
        data = json.load(open(_CANARY_ANSWERS))
        data["research_brief"]["confirmed_by_human"] = False
        with tempfile.TemporaryDirectory(prefix="ai-unsigned-") as tmp:
            apath = os.path.join(tmp, "a.json")
            json.dump(data, open(apath, "w"))
            dest, rc = self._scaffold(tmp, answers=apath)
            self.assertEqual(rc, 2, "unsigned brief must be NOT green (exit 2), never fabricated")
            self.assertFalse(adoption_status.validate_adoption(dest).ok)


class CliContractTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="ai-dry-") as tmp:
            dest = os.path.join(tmp, "acme")
            rc = ai.main([dest, "--answers", _CANARY_ANSWERS, "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(dest), "dry-run must not create the dest")

    def test_bad_answers_refused(self):
        with tempfile.TemporaryDirectory(prefix="ai-bad-") as tmp:
            apath = os.path.join(tmp, "bad.json")
            json.dump({"adopter_name": "x"}, open(apath, "w"))  # missing required keys
            rc = ai.main([os.path.join(tmp, "acme"), "--answers", apath])
            self.assertEqual(rc, 3, "invalid answers must be refused (exit 3)")

    def test_framework_repo_dest_refused_exit3(self):
        rc = ai.main([_FRAMEWORK_ROOT, "--answers", _CANARY_ANSWERS])
        self.assertEqual(rc, 3)

    def test_headless_empty_routing_name_refused(self):
        # [C2 B-1 / C2.2 N-1] every empty routing NAME must be rejected (minLength) so no
        # field is silently dropped into an unrunnable headless charter.
        base = {"harness": "headless", "provider": "deepseek", "model": "deepseek-v4-pro",
                "endpoint": "https://api.deepseek.com/v1", "endpoint_env": "DS_URL",
                "api_key_env": "DS_KEY"}
        for field_name in ("api_key_env", "endpoint", "endpoint_env"):
            with self.subTest(field=field_name):
                data = json.load(open(_CANARY_ANSWERS))
                role = dict(base)
                role[field_name] = ""
                data["llm_roles"]["review"] = role
                with tempfile.TemporaryDirectory(prefix="ai-hl-") as tmp:
                    apath = os.path.join(tmp, "a.json")
                    json.dump(data, open(apath, "w"))
                    with self.assertRaises(ai.InitError):
                        ai.load_answers(apath, _FRAMEWORK_ROOT)


class _FakeResp:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _headless_plan():
    data = json.load(open(_CANARY_ANSWERS))
    data["llm_roles"]["review"] = {
        "harness": "headless", "provider": "deepseek", "model": "deepseek-v4-pro",
        "endpoint": "https://api.deepseek.example/v1", "api_key_env": "DS_KEY"}
    with tempfile.TemporaryDirectory(prefix="ai-hlp-") as d:
        apath = os.path.join(d, "a.json")
        json.dump(data, open(apath, "w"))
        return ai.load_answers(apath, _FRAMEWORK_ROOT)


class ReachabilityProbeTests(unittest.TestCase):
    def test_off_is_noop(self):
        self.assertEqual(ai.run_reachability_probe(_load_plan(), "off"), [])

    def test_binary_returns_a_row_per_role_no_crash(self):
        rows = ai.run_reachability_probe(_load_plan(), "binary")
        self.assertEqual({r.role for r in rows}, set(ai._INTERACTIVE_ROLES))
        for r in rows:
            self.assertIn(r.status, ("reachable", "warn", "skipped"))

    def test_live_without_env_makes_no_network_call(self):
        # [I4] live WITHOUT the env flag must NOT hit the network — it downgrades to binary,
        # and the headless role becomes a 'skipped' row (never live-probed).
        plan = _headless_plan()
        import urllib.request
        with unittest.mock.patch.object(urllib.request, "urlopen",
                                        side_effect=AssertionError("network without flag!")) as m:
            rows = ai.run_reachability_probe(plan, "live", env={})  # no flag
        m.assert_not_called()
        review = next(r for r in rows if r.role == "review")
        self.assertEqual(review.status, "skipped")

    def test_live_with_env_probes_headless_key(self):
        plan = _headless_plan()
        import urllib.request
        with unittest.mock.patch.object(urllib.request, "urlopen", return_value=_FakeResp(200)) as m:
            rows = ai.run_reachability_probe(plan, "live", env={"AIDAZI_ADOPTER_INIT_LIVE_PROBE": "1",
                                                                "DS_KEY": "sk-test"})
        m.assert_called()
        review = next(r for r in rows if r.role == "review")
        self.assertEqual(review.status, "reachable")

    def test_live_dead_key_is_warn_not_crash(self):
        import urllib.error
        import urllib.request
        plan = _headless_plan()
        err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        with unittest.mock.patch.object(urllib.request, "urlopen", side_effect=err):
            rows = ai.run_reachability_probe(
                plan, "live", env={"AIDAZI_ADOPTER_INIT_LIVE_PROBE": "1", "DS_KEY": "sk-bad"})
        review = next(r for r in rows if r.role == "review")
        self.assertEqual(review.status, "warn")  # dead key (401) => advisory warn, never a crash

    def test_live_unset_key_is_warn_without_request(self):
        # [C3 B-1] a named api_key_env that resolves empty must NOT be probed as reachable —
        # never fabricate a pass from an unauthenticated request.
        import urllib.request
        plan = _headless_plan()  # api_key_env=DS_KEY, not provided in env
        with unittest.mock.patch.object(urllib.request, "urlopen",
                                        side_effect=AssertionError("must not request")) as m:
            rows = ai.run_reachability_probe(plan, "live", env={"AIDAZI_ADOPTER_INIT_LIVE_PROBE": "1"})
        m.assert_not_called()
        review = next(r for r in rows if r.role == "review")
        self.assertEqual(review.status, "warn")
        self.assertIn("DS_KEY", review.detail)

    def test_load_local_env_reads_dotenv(self):
        # [C3 B-1] .env.local keys are surfaced to the live probe (mirrors run_loop.load_local_env).
        with tempfile.TemporaryDirectory(prefix="ai-env-") as d:
            with open(os.path.join(d, ".env.local"), "w", encoding="utf-8") as fh:
                fh.write("# secret\nexport DS_KEY='sk-from-file'\nDS_URL=https://x/v1\n")
            loaded = ai._load_local_env(d)
            self.assertEqual(loaded["DS_KEY"], "sk-from-file")
            self.assertEqual(loaded["DS_URL"], "https://x/v1")


class InteractiveTests(unittest.TestCase):
    # scripted answers reproducing the canary choices (blank => role defaults).
    _SCRIPT = [
        "acme-widgets", "type_a", "yes",
        "Determine widget-order refund eligibility and explain the decision.",
        "Every eligibility decision cites the concrete governing policy rule; no unexplained denials.",
        "A user submits an order id and receives an eligibility verdict naming the governing rule.",
        "yes", "yes",
        "human_on_the_loop", "S1-eligibility-core, S2-explanation", "", "src/eligibility, src/explain",
        "src/payments", "3", "240", "python -m pytest -q", "600",
        "", "", "", "",                                   # research (defaults)
        "", "", "", "",                                   # deliver
        "cursor", "anysphere", "auto", "cursor-agent-dev",  # dev = cursor
        "", "", "", "",                                   # review
        "", "", "", "",                                   # acceptance
    ]

    def test_scripted_interactive_builds_a_valid_plan(self):
        it = iter(self._SCRIPT)
        data = ai.collect_answers_interactive(_FRAMEWORK_ROOT, reader=lambda: next(it),
                                              writer=lambda s: None)
        plan = ai._plan_from_data(data)
        self.assertEqual(plan.adopter_name, "acme-widgets")
        self.assertEqual(plan.llm_roles["dev"].harness, "cursor")
        self.assertTrue(plan.intent_confirmed)     # I3: only because the script typed "yes"
        self.assertTrue(plan.brief_confirmed)
        self.assertEqual(plan.subsprint_sequence, ["S1-eligibility-core", "S2-explanation"])

    def test_i3_interactive_no_confirm_leaves_flags_false(self):
        script = list(self._SCRIPT)
        script[6] = "no"   # confirm intent
        script[7] = "no"   # sign brief
        it = iter(script)
        data = ai.collect_answers_interactive(_FRAMEWORK_ROOT, reader=lambda: next(it),
                                              writer=lambda s: None)
        self.assertFalse(data["intent_contract"]["confirmed_by_human"])
        self.assertFalse(data["research_brief"]["confirmed_by_human"])

    def test_emit_answers_round_trips(self):
        it = iter(self._SCRIPT)
        data = ai.collect_answers_interactive(_FRAMEWORK_ROOT, reader=lambda: next(it),
                                              writer=lambda s: None)
        with tempfile.TemporaryDirectory(prefix="ai-emit-") as d:
            emit = os.path.join(d, "emitted.json")
            ai._atomic_write(emit, json.dumps(data, indent=2) + "\n")
            reloaded = json.load(open(emit))
            self.assertEqual(reloaded, data)  # round-trip identity
            # and the emitted answers scaffold to GREEN
            rc = ai.main([os.path.join(d, "acme"), "--answers", emit, "--probe", "off"])
            self.assertEqual(rc, 0)

    def test_non_tty_without_answers_is_refused(self):
        # pytest captures stdin (not a TTY); interactive with no --answers must refuse, not hang.
        with tempfile.TemporaryDirectory(prefix="ai-notty-") as d:
            rc = ai.main([os.path.join(d, "acme")])  # no --answers
            self.assertEqual(rc, 3)

    def test_non_tty_with_emit_answers_still_refused(self):
        # [C3 B-2] --emit-answers must NOT make a non-TTY no-answers invocation interactive.
        with tempfile.TemporaryDirectory(prefix="ai-emit-notty-") as d:
            rc = ai.main([os.path.join(d, "acme"), "--emit-answers", os.path.join(d, "a.json")])
            self.assertEqual(rc, 3)
            self.assertFalse(os.path.exists(os.path.join(d, "a.json")))

    def test_ask_int_reprompts_then_raises_on_garbage(self):
        # [C3 B-3] invalid numeric input is a controlled refusal, never an uncaught traceback.
        it = iter(["abc", "not-a-number", "still-bad", "9"])
        with self.assertRaises(ai.InitError):
            ai._ask_int(lambda: next(it), lambda s: None, "n", 5)

    def test_ask_int_accepts_valid_after_retry(self):
        it = iter(["oops", "7"])
        self.assertEqual(ai._ask_int(lambda: next(it), lambda s: None, "n", 5), 7)


class BrownfieldCanaryTests(unittest.TestCase):
    def test_brownfield_force_is_green_and_non_destructive(self):
        # design §6.2: --force over a pre-existing repo => four validators green, pre-existing
        # files untouched, and the partial .gitignore MERGED (not clobbered).
        with tempfile.TemporaryDirectory(prefix="ai-brown-") as tmp:
            dest = os.path.join(tmp, "existing-repo")
            os.makedirs(os.path.join(dest, "src"))
            with open(os.path.join(dest, "src", "app.py"), "w", encoding="utf-8") as fh:
                fh.write("print('hello')\n")
            with open(os.path.join(dest, "README.md"), "w", encoding="utf-8") as fh:
                fh.write("# Existing project\n")
            with open(os.path.join(dest, ".gitignore"), "w", encoding="utf-8") as fh:
                fh.write("*.pyc\nbuild/\n")  # pre-existing partial .gitignore
            rc = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc, 0)
            self.assertTrue(adoption_status.validate_adoption(dest).ok)
            # pre-existing files untouched
            self.assertEqual(ai._read_text(os.path.join(dest, "src", "app.py")), "print('hello')\n")
            self.assertEqual(ai._read_text(os.path.join(dest, "README.md")), "# Existing project\n")
            # existing .gitignore lines preserved AND aidazi patterns merged in
            gi = ai._read_text(os.path.join(dest, ".gitignore"))
            for pat in ("*.pyc", "build/", ".runs/", ".env.local", ".orchestrator/"):
                self.assertIn(pat, gi, msg=f"{pat} missing from merged .gitignore")
            gi_lines = [ln.strip() for ln in gi.splitlines()
                        if ln.strip() and not ln.strip().startswith("#")]
            self.assertEqual(len(gi_lines), len(set(gi_lines)), "duplicate .gitignore lines")

    def test_merge_gitignore_edge_cases(self):
        # [C4 N-1] no-trailing-newline + already-present pattern => merge without duplicating;
        # empty existing => gets the required patterns.
        with tempfile.TemporaryDirectory(prefix="ai-gi-") as tmp:
            gi = os.path.join(tmp, ".gitignore")
            with open(gi, "w", encoding="utf-8") as fh:
                fh.write("*.pyc\n.runs/")  # .runs/ already present; NO trailing newline
            ai._merge_gitignore(gi, ai._GITIGNORE)
            lines = [ln.strip() for ln in ai._read_text(gi).splitlines()
                     if ln.strip() and not ln.strip().startswith("#")]
            self.assertEqual(lines.count(".runs/"), 1)  # not duplicated
            self.assertIn("*.pyc", lines)               # preserved
            self.assertIn(".env.local", lines)          # merged
            # empty existing gets the required patterns
            gi2 = os.path.join(tmp, "gi2")
            open(gi2, "w").close()
            ai._merge_gitignore(gi2, ai._GITIGNORE)
            self.assertIn(".runs/", ai._read_text(gi2))
            # a fully-covered existing file is left unchanged (no additions)
            before = ai._read_text(gi)
            ai._merge_gitignore(gi, ai._GITIGNORE)
            self.assertEqual(ai._read_text(gi), before)


class LiveProbeCanaryTests(unittest.TestCase):
    """Env-gated real live-probe canary (design §6.3). Skipped offline; when enabled it probes a
    real headless endpoint named by AIDAZI_E2E_HEADLESS_ENDPOINT + AIDAZI_E2E_HEADLESS_KEY_ENV."""

    @unittest.skipUnless(os.environ.get("AIDAZI_E2E_ADOPTER_INIT_LIVE") == "1",
                         "set AIDAZI_E2E_ADOPTER_INIT_LIVE=1 (+ endpoint/key env) to run")
    def test_live_probe_reachable_and_bad_key_warn(self):
        endpoint = os.environ["AIDAZI_E2E_HEADLESS_ENDPOINT"]
        key_env = os.environ.get("AIDAZI_E2E_HEADLESS_KEY_ENV", "AIDAZI_E2E_HEADLESS_KEY")
        data = json.load(open(_CANARY_ANSWERS))
        data["llm_roles"]["review"] = {"harness": "headless", "provider": "openai_compatible",
                                       "model": "gpt-4o-mini", "endpoint": endpoint,
                                       "api_key_env": key_env}
        with tempfile.TemporaryDirectory(prefix="ai-live-") as tmp:
            apath = os.path.join(tmp, "a.json")
            json.dump(data, open(apath, "w"))
            plan = ai.load_answers(apath, _FRAMEWORK_ROOT)
            live_env = dict(os.environ, AIDAZI_ADOPTER_INIT_LIVE_PROBE="1")
            good = ai.run_reachability_probe(plan, "live", env=live_env)
            self.assertEqual(next(r for r in good if r.role == "review").status, "reachable")
            bad_env = dict(live_env); bad_env[key_env] = "sk-deliberately-bad"
            bad = ai.run_reachability_probe(plan, "live", env=bad_env)
            self.assertEqual(next(r for r in bad if r.role == "review").status, "warn")


# --------------------------------------------------------------------------- #
# Brownfield governed-doc preservation (brownfield-preserve): --force is a BOOTSTRAP, not a
# migrator — create only MISSING files, keep existing governed/wiring/human content byte-for-byte.
# --------------------------------------------------------------------------- #
_SNAPSHOT_EXCLUDE_DIRS = {".git", "aidazi", "__pycache__", ".pytest_cache", ".gate", ".runs",
                          "node_modules", "target", ".venv", "venv"}
# Copy KEEPS the adopter's own aidazi/ framework mount (so control_plane validates identically
# before/after — adopter_init's re-mount is then an idempotent skip); it only drops VCS + heavy
# build/cache dirs.
_COPY_IGNORE_DIRS = {".git", "__pycache__", ".pytest_cache", ".gate", ".runs",
                     "node_modules", "target", ".venv", "venv"}
_SNAPSHOT_EXCLUDE_RELS = {
    os.path.join("docs", "current", "adoption-readiness.md"),  # validator-regenerated snapshot
    ".gitignore",                                              # append-merged by design
}


def _snapshot_governed(dest):
    """Byte snapshot of every adopter-authored file under ``dest``, EXCLUDING the framework mount
    (``aidazi/``), VCS/cache/build dirs, the validator-regenerated readiness snapshot, and
    ``.gitignore`` (which adopter_init append-merges). Used to assert ZERO governed-doc drift
    across a brownfield ``--force`` re-run."""
    snap = {}
    for root, dirs, files in os.walk(dest):
        dirs[:] = [d for d in dirs if d not in _SNAPSHOT_EXCLUDE_DIRS]
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, dest)
            if rel in _SNAPSHOT_EXCLUDE_RELS:
                continue
            with open(full, "rb") as fh:
                snap[rel] = fh.read()
    return snap


def _render_errs(rep):
    return [getattr(e, "render", lambda: str(e))() for e in rep.errors]


class BrownfieldGovernedDocsTests(unittest.TestCase):
    """The brownfield-preserve contract (design §6.2): ``--force`` is a BOOTSTRAP, not a
    migrator — it creates only the files that are ABSENT and preserves existing governed / wiring
    / human content byte-for-byte; an incompatible kept file fails the exit validators with
    actionable remediation instead of being silently rewritten. (Closes the C4 gap: the prior
    brownfield canary only used non-governed files, so it never exercised the clobber path.)"""

    def test_force_preserves_governed_docs_byte_for_byte_and_stays_green(self):
        with tempfile.TemporaryDirectory(prefix="ai-govdrift-") as tmp:
            dest = os.path.join(tmp, "acme")
            self.assertEqual(ai.main([dest, "--answers", _CANARY_ANSWERS]), 0)  # greenfield GREEN
            # A live adopter evolves its governed docs. Edit a representative set the way a human
            # would (kept valid): markdown gets a marker comment; the JSON ledger is reserialised
            # to valid-but-different bytes (indent 4 vs the generator's indent 2) so a regenerate
            # would be detectable.
            md_edits = {
                "AGENTS.md": "\n<!-- adopter-local marker KEEP-7f3 -->\n",
                os.path.join("docs", "current", "adoption-config.md"): "\n<!-- KEEP-cfg -->\n",
                os.path.join("docs", "current", "domain_taxonomy.md"): "\n<!-- KEEP-tax -->\n",
            }
            for rel, extra in md_edits.items():
                with open(os.path.join(dest, rel), "a", encoding="utf-8") as fh:
                    fh.write(extra)
            ledger_path = os.path.join(dest, "docs", "requirements-ledger.json")
            ledger = json.load(open(ledger_path))
            with open(ledger_path, "w", encoding="utf-8") as fh:
                json.dump(ledger, fh, indent=4)   # valid JSON, but != generator's indent-2 bytes
                fh.write("\n")
            before = _snapshot_governed(dest)
            # Re-run brownfield --force (NO --overwrite).
            rc = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc, 0, "brownfield --force must stay GREEN")
            after = _snapshot_governed(dest)
            self.assertEqual(after, before, "a governed doc drifted on brownfield --force")
            # the human markers + reserialised ledger survived => PRESERVE, not regenerate.
            for rel, extra in md_edits.items():
                self.assertIn(extra.strip(), ai._read_text(os.path.join(dest, rel)))
            self.assertIn("\n    ", ai._read_text(ledger_path))  # still indent-4 (not regenerated)

    def test_incompatible_existing_wiring_preserved_and_fails_not_rewritten(self):
        # design: "if existing wiring is incompatible, FAIL with an actionable validation result
        # rather than rewriting it." A brownfield CLAUDE.md lacking the @AGENTS.md import must be
        # kept byte-for-byte AND make the tool report NOT green (exit 2), never auto-fixed.
        with tempfile.TemporaryDirectory(prefix="ai-badwire-") as tmp:
            dest = os.path.join(tmp, "acme")
            os.makedirs(dest)
            incompatible = "# my own project rules — no aidazi wiring\n"
            with open(os.path.join(dest, "CLAUDE.md"), "w", encoding="utf-8") as fh:
                fh.write(incompatible)
            rc = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc, 2, "incompatible wiring must be NOT green, not auto-fixed")
            # preserved byte-for-byte (NOT rewritten to '@AGENTS.md\n')
            self.assertEqual(ai._read_text(os.path.join(dest, "CLAUDE.md")), incompatible)
            # the wiring validator independently reports the breach (actionable remediation) ...
            self.assertFalse(awv.validate_root(dest).ok)
            # ... while the genuinely MISSING wiring file WAS bootstrapped (create-only-missing).
            self.assertTrue(os.path.isfile(os.path.join(dest, "AGENTS.md")))

    def test_overwrite_is_the_explicit_regenerate_escape_hatch(self):
        # --overwrite (the explicit human opt-in) DOES regenerate an existing TOOL-AUTHORED doc —
        # the counterpart that proves default-preserve is a real, distinct behaviour. But
        # .gitignore is ALWAYS append-merged, never clobbered, even under --overwrite ([B-2]).
        with tempfile.TemporaryDirectory(prefix="ai-ovw-") as tmp:
            dest = os.path.join(tmp, "acme")
            self.assertEqual(ai.main([dest, "--answers", _CANARY_ANSWERS]), 0)
            agents = os.path.join(dest, "AGENTS.md")
            with open(agents, "a", encoding="utf-8") as fh:
                fh.write("\n<!-- marker DROP-ME -->\n")
            gi = os.path.join(dest, ".gitignore")
            with open(gi, "a", encoding="utf-8") as fh:
                fh.write("\ncustom-adopter-secret/\n")
            rc = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force", "--overwrite"])
            self.assertEqual(rc, 0)
            self.assertNotIn("DROP-ME", ai._read_text(agents))            # tool doc regenerated
            self.assertIn("custom-adopter-secret", ai._read_text(gi))     # .gitignore never clobbered

    def test_readiness_snapshot_is_tool_owned_and_refreshed(self):
        # [B-1] the exit-validator readiness snapshot is a TOOL-OWNED status output, not
        # adopter-authored content, so it is deliberately REFRESHED every run (the documented
        # second exception to preserve-by-default, alongside always-append-merged .gitignore). A
        # hand-edited adopter DOC is still preserved byte-for-byte in the same run.
        with tempfile.TemporaryDirectory(prefix="ai-rdy2-") as tmp:
            dest = os.path.join(tmp, "acme")
            self.assertEqual(ai.main([dest, "--answers", _CANARY_ANSWERS]), 0)
            readiness = os.path.join(dest, "docs", "current", "adoption-readiness.md")
            agents = os.path.join(dest, "AGENTS.md")
            with open(readiness, "a", encoding="utf-8") as fh:
                fh.write("\n<!-- STALE-READINESS-EDIT -->\n")
            with open(agents, "a", encoding="utf-8") as fh:
                fh.write("\n<!-- KEEP-AGENTS -->\n")
            self.assertEqual(ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"]), 0)
            # readiness snapshot regenerated (tool-owned) -> the stale hand edit is gone ...
            self.assertNotIn("STALE-READINESS-EDIT", ai._read_text(readiness))
            # ... while the adopter-authored doc is preserved in the SAME run.
            self.assertIn("KEEP-AGENTS", ai._read_text(agents))

    def test_materialize_report_created_then_preserved(self):
        plan = ai.load_answers(_CANARY_ANSWERS, _FRAMEWORK_ROOT)
        artifacts = ai.build_artifacts(plan, ai.load_templates(_FRAMEWORK_ROOT))
        with tempfile.TemporaryDirectory(prefix="ai-report-") as tmp:
            dest = os.path.join(tmp, "acme")
            r1 = ai.materialize(artifacts, dest, _FRAMEWORK_ROOT)
            self.assertIsInstance(r1, ai.MaterializeReport)
            self.assertIn("AGENTS.md", r1.created)
            self.assertEqual(r1.preserved, [])
            # hand-edit one artifact, then a brownfield re-materialize: it is PRESERVED, the rest
            # are byte-identical (unchanged), nothing is created or overwritten.
            with open(os.path.join(dest, "AGENTS.md"), "a", encoding="utf-8") as fh:
                fh.write("\n<!-- edit -->\n")
            r2 = ai.materialize(artifacts, dest, _FRAMEWORK_ROOT, force=True)
            self.assertIn("AGENTS.md", r2.preserved)
            self.assertEqual(r2.created, [])
            self.assertEqual(r2.overwritten, [])
            self.assertIn("charter.yaml", r2.unchanged)

    def test_create_only_write_never_clobbers_existing(self):
        # [create-path TOCTOU] the create-missing helper is atomic O_EXCL: it creates an ABSENT
        # file and reports True, but refuses to overwrite an existing one (reports False, content
        # untouched) — so a file that appears in the exists→write window is preserved, not clobbered.
        with tempfile.TemporaryDirectory(prefix="ai-cow-") as tmp:
            path = os.path.join(tmp, "sub", "f.txt")
            self.assertTrue(ai._create_only_write(path, "fresh\n"))   # absent -> created
            self.assertEqual(ai._read_text(path), "fresh\n")
            self.assertFalse(ai._create_only_write(path, "REPLACED\n"))  # exists -> refuse
            self.assertEqual(ai._read_text(path), "fresh\n", "create-only must not clobber")

    def test_create_missing_preserves_file_that_appears_after_exists_check(self):
        # [create-path TOCTOU] a governed file classified MISSING by materialize's exists-check but
        # created by a concurrent/human writer before the write must be PRESERVED byte-for-byte
        # (recorded as preserved, not created), never clobbered by the bootstrap create.
        plan = ai.load_answers(_CANARY_ANSWERS, _FRAMEWORK_ROOT)
        artifacts = ai.build_artifacts(plan, ai.load_templates(_FRAMEWORK_ROOT))
        with tempfile.TemporaryDirectory(prefix="ai-cow-toctou-") as tmp:
            dest = os.path.join(tmp, "acme")
            self.assertEqual(ai.main([dest, "--answers", _CANARY_ANSWERS]), 0)  # greenfield GREEN
            agents = os.path.join(dest, "AGENTS.md")
            os.remove(agents)  # now MISSING at the exists-check
            real_cow = ai._create_only_write

            def hooked(path, content, *a, **k):
                if os.path.basename(path) == "AGENTS.md" and not os.path.exists(path):
                    # simulate a writer that lands in the exists→create window
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write("CONCURRENT-CREATE KEEP-ME\n")
                return real_cow(path, content, *a, **k)  # O_EXCL now sees it -> returns False

            with unittest.mock.patch.object(ai, "_create_only_write", side_effect=hooked):
                report = ai.materialize(artifacts, dest, _FRAMEWORK_ROOT, force=True)
            self.assertIn("AGENTS.md", report.preserved, "raced create must be preserved")
            self.assertNotIn("AGENTS.md", report.created)
            self.assertEqual(ai._read_text(agents), "CONCURRENT-CREATE KEEP-ME\n",
                             "the concurrently-created file must survive byte-for-byte")

    @unittest.skipUnless(os.environ.get("AIDAZI_E2E_ADOPTER_BROWNFIELD_SRC"),
                         "set AIDAZI_E2E_ADOPTER_BROWNFIELD_SRC=<real adopter root> to run")
    def test_real_adopter_copy_zero_governed_drift(self):
        """Env-gated REAL-adopter brownfield canary (design §6.3): copy a real adopter root to a
        disposable dir, run ``--force``, and prove (a) ZERO governed-doc drift and (b) the
        adopter's pre-existing ``control_plane`` findings are UNCHANGED — i.e. distinct from
        anything Phase-5 introduces. Operates on the copy only; never touches the source."""
        src = os.environ["AIDAZI_E2E_ADOPTER_BROWNFIELD_SRC"]
        answers = os.environ.get("AIDAZI_E2E_ADOPTER_BROWNFIELD_ANSWERS", _CANARY_ANSWERS)
        with tempfile.TemporaryDirectory(prefix="ai-realbrown-") as tmp:
            dest = os.path.join(tmp, "adopter-copy")
            shutil.copytree(src, dest, symlinks=True,
                            ignore=shutil.ignore_patterns(*_COPY_IGNORE_DIRS, "*.pyc"))
            before = _snapshot_governed(dest)
            cp_before = _render_errs(control_plane_validator.validate_root(dest))
            rc = ai.main([dest, "--answers", answers, "--force"])
            # [B-3] the tool MUST have run materialize (green=0 or not-green=2); a refusal (exit 3)
            # would leave the tree untouched and let this canary pass without exercising the path.
            self.assertIn(rc, (0, 2), f"adopter_init refused/errored (exit {rc}) — canary vacuous")
            after = _snapshot_governed(dest)
            cp_after = _render_errs(control_plane_validator.validate_root(dest))
            # DRIFT = mutating/removing a file the adopter already had. Creating a genuinely
            # MISSING bootstrap file is NOT drift, so assert the pre-existing set is byte-identical
            # (a subset check) rather than exact tree equality.
            for rel, content in before.items():
                self.assertEqual(after.get(rel), content, f"governed doc drifted: {rel}")
            # the adopter's pre-existing control_plane findings are its OWN — unchanged by Phase-5.
            self.assertEqual(cp_before, cp_after,
                             "adopter_init changed the adopter's pre-existing control_plane findings")


if __name__ == "__main__":
    unittest.main(verbosity=2)
