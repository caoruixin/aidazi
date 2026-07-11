"""Cluster-2 tests for adopter_init.py (design §4 / §10).

Proves the scaffolding CORE: answers -> a tree that makes all four adoption validators GREEN,
plus the fail-closed invariants I1 (pure build_artifacts), I2 (guarded dest / never the
framework repo), I3 (never auto-confirm the gate-1 signature).
"""
import json
import os
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
        # [R3.2 B-1] a pre-planted <file>.tmp symlink escaping dest must not be written through.
        with tempfile.TemporaryDirectory(prefix="ai-tmpesc-") as tmp:
            dest = os.path.join(tmp, "dest")
            outside = os.path.join(tmp, "outside")
            os.makedirs(dest)
            os.makedirs(outside)
            leak = os.path.join(outside, "leak")
            os.symlink(leak, os.path.join(dest, "AGENTS.md.tmp"))  # pre-plant the tmp symlink
            plan = _load_plan()
            artifacts = ai.build_artifacts(plan, ai.load_templates(_FRAMEWORK_ROOT))
            with self.assertRaises(ai.InitError):
                ai.materialize(artifacts, dest, _FRAMEWORK_ROOT, force=True)
            self.assertFalse(os.path.exists(leak))  # never written through the symlink

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

    def test_existing_adopter_force_refuses_governed_clobber(self):
        # [Finding 2 / greenfield-only] --force on an ALREADY-adopted repo whose governed docs have
        # DIVERGED (e.g. a real requirements ledger) must be refused fail-closed (adopter_init is a
        # scaffolder, not a migrator; design §0.2). The diverged doc must be left untouched, and
        # --overwrite must remain the explicit regenerate escape hatch.
        with tempfile.TemporaryDirectory(prefix="ai-migrate-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0)
            ledger = os.path.join(dest, "docs", "requirements-ledger.json")
            with open(ledger, "w", encoding="utf-8") as fh:
                fh.write('{"requirements": [{"id": "R-EXISTING", "note": "real delivery state"}]}\n')
            # --force alone must REFUSE (exit 3) without clobbering the diverged ledger.
            rc2 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc2, 3, "must refuse to migrate an existing adopter")
            self.assertIn("R-EXISTING", ai._read_text(ledger), "diverged ledger left untouched")
            # --overwrite is the explicit regenerate escape hatch (back to a green scaffold).
            rc3 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force", "--overwrite"])
            self.assertEqual(rc3, 0)
            self.assertNotIn("R-EXISTING", ai._read_text(ledger), "--overwrite regenerates")

    def test_existing_adopter_force_refuses_readiness_clobber(self):
        # [Finding 2 / B1 fold] adoption-readiness.md is a governed docs/current/* doc written by
        # run_exit_validators AFTER materialize — it must obey the SAME fail-closed policy, or a
        # --force run silently clobbers a diverged readiness snapshot that materialize's pre-scan
        # (artifact-set only) never sees.
        with tempfile.TemporaryDirectory(prefix="ai-rdy-clobber-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0)
            readiness = os.path.join(dest, "docs", "current", "adoption-readiness.md")
            # diverge ONLY the readiness snapshot (every materialized artifact stays byte-identical,
            # so materialize's pre-scan passes and this is the sole governed-doc divergence).
            with open(readiness, "a", encoding="utf-8") as fh:
                fh.write("\n<!-- HUMAN-EDIT-READINESS -->\n")
            rc2 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc2, 3, "must refuse to clobber a diverged readiness snapshot")
            self.assertIn("HUMAN-EDIT-READINESS", ai._read_text(readiness), "readiness preserved")
            # --overwrite is the explicit regenerate escape hatch.
            rc3 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force", "--overwrite"])
            self.assertEqual(rc3, 0)
            self.assertNotIn("HUMAN-EDIT-READINESS", ai._read_text(readiness), "--overwrite regenerates")

    def test_materialize_clobber_refused_when_governed_doc_diverges_after_prescan(self):
        # [R3 B1 / TOCTOU] the no-clobber rule is re-enforced at the WRITE site, not only the
        # pre-scan. Simulate a concurrent writer diverging a not-yet-written governed doc in the
        # window AFTER the pre-scan passed: the write loop must still refuse (exit 3) and preserve.
        with tempfile.TemporaryDirectory(prefix="ai-toctou-mat-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0)
            ledger = os.path.join(dest, "docs", "requirements-ledger.json")
            # Remove AGENTS.md so the write loop actually reaches _atomic_write (a fully identical
            # tree writes nothing); AGENTS.md sorts before docs/requirements-ledger.json.
            os.remove(os.path.join(dest, "AGENTS.md"))
            real_atomic = ai._atomic_write

            def hooked(target, content, *a, **k):
                if os.path.basename(target) == "AGENTS.md":
                    with open(ledger, "w", encoding="utf-8") as fh:
                        fh.write('{"requirements": [{"id": "R-TOCTOU"}]}\n')  # diverge post-pre-scan
                return real_atomic(target, content, *a, **k)

            with unittest.mock.patch.object(ai, "_atomic_write", side_effect=hooked):
                rc2 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc2, 3, "write-site guard must refuse a diverged-after-pre-scan clobber")
            self.assertIn("R-TOCTOU", ai._read_text(ledger), "diverged ledger preserved at write site")

    def test_readiness_clobber_refused_when_snapshot_diverges_after_capture(self):
        # [R3 B1 / TOCTOU] the readiness snapshot is re-read IMMEDIATELY before the final write.
        # Simulate a concurrent writer diverging it after the initial capture: refuse + preserve.
        with tempfile.TemporaryDirectory(prefix="ai-toctou-rdy-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0)
            readiness = os.path.join(dest, "docs", "current", "adoption-readiness.md")
            real_render = adoption_status.render_readiness_snapshot

            def hooked_render(report, *a, **k):
                out = real_render(report, *a, **k)
                if "R-TOCTOU-RDY" not in ai._read_text(readiness):
                    with open(readiness, "a", encoding="utf-8") as fh:
                        fh.write("\n<!-- R-TOCTOU-RDY -->\n")  # diverge after the capture
                return out

            with unittest.mock.patch.object(adoption_status, "render_readiness_snapshot",
                                            side_effect=hooked_render):
                rc2 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc2, 3, "readiness re-read guard must refuse a diverged-after-capture clobber")
            self.assertIn("R-TOCTOU-RDY", ai._read_text(readiness), "diverged readiness preserved")

    def test_readiness_clobber_refused_on_bootstrap_branch_diverged_after_boot(self):
        # [R4 B1 / TOCTOU] the ABSENT-at-capture (bootstrap) branch must ALSO re-read before the
        # final write: a concurrent writer that lands content between our bootstrap create and the
        # final write must not be clobbered under --force without --overwrite.
        with tempfile.TemporaryDirectory(prefix="ai-toctou-boot-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0)
            readiness = os.path.join(dest, "docs", "current", "adoption-readiness.md")
            os.remove(readiness)  # ABSENT at capture -> bootstrap branch
            real_cow = ai._create_only_write

            def hooked_cow(path, content, *a, **k):
                created = real_cow(path, content, *a, **k)  # perform the bootstrap create
                if "CONCURRENT-BOOT" not in ai._read_text(path):
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write("CONCURRENT-BOOT REPLACEMENT\n")  # diverge right after bootstrap
                return created

            with unittest.mock.patch.object(ai, "_create_only_write", side_effect=hooked_cow):
                rc2 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc2, 3, "bootstrap-branch re-read guard must refuse the post-boot clobber")
            self.assertIn("CONCURRENT-BOOT", ai._read_text(readiness), "post-boot content preserved")

    def test_readiness_bootstrap_write_is_create_only(self):
        # [R5 B1 / TOCTOU] the bootstrap WRITE itself must be create-only: a concurrent/human file
        # that appears AFTER absent-capture but BEFORE the bootstrap write must NOT be clobbered —
        # the create-only write leaves it, and the guard then refuses (exit 3, content preserved).
        with tempfile.TemporaryDirectory(prefix="ai-toctou-preboot-") as tmp:
            dest, rc = self._scaffold(tmp)
            self.assertEqual(rc, 0)
            readiness = os.path.join(dest, "docs", "current", "adoption-readiness.md")
            os.remove(readiness)  # ABSENT at capture -> bootstrap branch
            real_render = adoption_status.render_readiness_snapshot

            def hooked_render(report, *a, **k):
                out = real_render(report, *a, **k)
                if not os.path.exists(readiness):  # fires once: after the pre-render, pre-bootstrap
                    with open(readiness, "w", encoding="utf-8") as fh:
                        fh.write("CONCURRENT-PREBOOT CONTENT\n")  # a writer beats our bootstrap
                return out

            with unittest.mock.patch.object(adoption_status, "render_readiness_snapshot",
                                            side_effect=hooked_render):
                rc2 = ai.main([dest, "--answers", _CANARY_ANSWERS, "--force"])
            self.assertEqual(rc2, 3, "create-only bootstrap must not clobber a pre-boot concurrent file")
            self.assertIn("CONCURRENT-PREBOOT", ai._read_text(readiness), "pre-boot content preserved")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
