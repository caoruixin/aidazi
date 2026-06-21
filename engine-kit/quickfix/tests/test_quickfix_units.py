"""Quick-Fix unit tests: policy loader, request loader, verification, record log."""
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import _helpers as H  # noqa: E402

from quickfix import paths, policy, record, verify  # noqa: E402
from quickfix.errors import (PolicyError, RecordError, RequestError,  # noqa: E402
                             VerificationError)
from quickfix.request import Verification, load_request  # noqa: E402

FR = H.FRAMEWORK_ROOT


class PolicyLoader(unittest.TestCase):
    def _load(self, overlay=None):
        return policy.load_protected(
            paths.policy_path(FR), paths.baseline_schema_path(FR),
            overlay, paths.overlay_schema_path(FR))

    def test_baseline_loads_and_matches(self):
        prot = self._load()
        self.assertEqual(prot.match("aidazi/schemas/x.json"), "contract_schemas")
        self.assertEqual(prot.match("governance/constitution.md"), "governance")
        self.assertEqual(prot.match("process/delivery-loop.md"), "checkpoints_routing_loop")
        self.assertIsNone(prot.match("src/app.py"))

    def test_missing_baseline_fails_closed(self):
        with self.assertRaises(PolicyError):
            policy.load_protected("/no/such/policy.yaml", paths.baseline_schema_path(FR))

    def test_overlay_additive(self):
        with tempfile.TemporaryDirectory() as d:
            ov = os.path.join(d, "ov.yaml")
            with open(ov, "w") as f:
                f.write("version: 1\nadditional_surfaces:\n"
                        "  - id: app_secrets\n    globs: ['config/secrets/**']\n    reason: r\n")
            prot = self._load(ov)
            self.assertEqual(prot.match("config/secrets/x"), "app_secrets")
            self.assertEqual(prot.match("governance/x.md"), "governance")  # baseline still there

    def test_overlay_with_mandatory_surfaces_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            ov = os.path.join(d, "ov.yaml")
            with open(ov, "w") as f:
                f.write("version: 1\nmandatory_surfaces:\n"
                        "  - id: x\n    globs: ['a/**']\n    reason: r\n")
            with self.assertRaises(PolicyError):
                self._load(ov)


class RequestLoader(unittest.TestCase):
    def test_valid(self):
        with tempfile.TemporaryDirectory() as d:
            repo = H.make_repo(os.path.join(d, "repo"))
            reqp = H.write_request(repo)
            r = load_request(reqp, paths.request_schema_path(FR))
            self.assertEqual(r.request_id, "fix-pag-001")
            self.assertEqual(r.allowed_glob_patterns, ["src/app.py"])

    def test_missing_file(self):
        with self.assertRaises(RequestError):
            load_request("/no/such.json", paths.request_schema_path(FR))

    def test_bad_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.json")
            open(p, "w").write("{ not json")
            with self.assertRaises(RequestError):
                load_request(p, paths.request_schema_path(FR))

    def test_human_activation_false_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = H.make_repo(os.path.join(d, "repo"))
            reqp = H.write_request(repo)
            import json
            obj = json.load(open(reqp)); obj["human_activation"] = False
            json.dump(obj, open(reqp, "w"))
            with self.assertRaises(RequestError):
                load_request(reqp, paths.request_schema_path(FR))


class Verify(unittest.TestCase):
    def test_pass_and_fail(self):
        with tempfile.TemporaryDirectory() as d:
            ok = verify.run(Verification(["python3", "-c", "import sys;sys.exit(0)"]), d)
            self.assertTrue(ok.ok)
            bad = verify.run(Verification(["python3", "-c", "import sys;sys.exit(1)"]), d)
            self.assertFalse(bad.ok)

    def test_cwd_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "wt"))
            for bad in ("..", "../..", "/etc"):
                with self.assertRaises(VerificationError):
                    verify.run(Verification(["python3", "-c", "pass"], bad),
                               os.path.join(d, "wt"))

    def test_allowlist_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(VerificationError):
                verify.run(Verification(["echo", "hi"]), d)  # echo not allowlisted
            ok = verify.run(Verification(["echo", "hi"]), d, allow_unlisted=True)
            self.assertTrue(ok.ok)

    def test_empty_argv_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(VerificationError):
                verify.run(Verification([]), d)


class RecordLog(unittest.TestCase):
    def _completed(self, rid="r1"):
        return {"request_id": rid, "harness": "claude_code", "outcome": "completed",
                "baseline_sha": "abc1234", "ts": "t",
                "result": {"branch": f"quickfix/{rid}", "commit_sha": "def5678",
                           "stat": "x", "verification": {"argv": ["a"], "exit_code": 0, "ok": True}}}

    def test_append_and_read(self):
        with tempfile.TemporaryDirectory() as d:
            rp = os.path.join(d, ".orchestrator", "quickfix", "records.jsonl")
            sp = paths.record_schema_path(FR)
            record.append(self._completed("r1"), rp, sp)
            record.append(self._completed("r2"), rp, sp)
            rr = record.read(rp)
            self.assertEqual([x["request_id"] for x in rr.records], ["r1", "r2"])
            self.assertEqual(rr.corrupt_lines, [])

    def test_invalid_record_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            rp = os.path.join(d, "rec.jsonl")
            bad = self._completed(); bad["result"]["branch"] = "main"  # not quickfix/
            with self.assertRaises(RecordError):
                record.append(bad, rp, paths.record_schema_path(FR))
            self.assertFalse(os.path.exists(rp))  # nothing written on invalid

    def test_concurrent_appends_all_present(self):
        with tempfile.TemporaryDirectory() as d:
            rp = os.path.join(d, "rec.jsonl"); sp = paths.record_schema_path(FR)
            N = 25
            errs = []

            def worker(i):
                try:
                    record.append(self._completed(f"r{i:03d}"), rp, sp)
                except Exception as e:  # pragma: no cover
                    errs.append(e)

            ts = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            self.assertEqual(errs, [])
            rr = record.read(rp)
            self.assertEqual(len(rr.records), N)
            self.assertEqual(rr.corrupt_lines, [])
            self.assertEqual(len({r["request_id"] for r in rr.records}), N)

    def test_corrupt_trailing_line_tolerated(self):
        with tempfile.TemporaryDirectory() as d:
            rp = os.path.join(d, "rec.jsonl"); sp = paths.record_schema_path(FR)
            record.append(self._completed("r1"), rp, sp)
            # simulate an abnormal exit leaving a partial/garbled trailing line
            with open(rp, "a") as f:
                f.write('{"request_id": "partial", "outcom')  # no newline, truncated
            rr = record.read(rp)
            self.assertEqual([x["request_id"] for x in rr.records], ["r1"])
            self.assertEqual(len(rr.corrupt_lines), 1)


if __name__ == "__main__":
    unittest.main()
