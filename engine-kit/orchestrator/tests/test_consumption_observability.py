"""Universal-skill-mounting §3/D2 — DRIVER-side consumption observability: the single
deterministic telemetry→audit mapping (one test per row), the legacy-dict shim +
deprecation signal, the AdapterError path, the raw-stream canary transcript, and the
crash-resume ledger-equality obligation."""
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))                     # orchestrator/
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))   # engine-kit/

from test_driver import (_adapters, _driver, Driver,  # noqa: E402
                         GateHardFail)
from adapters import (AdapterError, InvocationTelemetry,  # noqa: E402
                      MockAdapter, SpawnResult)
import audit_log as audit  # noqa: E402
import effective_role_config as erc  # noqa: E402


def _spawn_events(drv):
    return [e["payload"] for e in audit.read_events(drv.audit_ledger)
            if e["type"] == "spawn"]


class MappingRowTests(unittest.TestCase):
    """One test per row of the frozen telemetry→audit mapping (pure helper)."""

    def setUp(self):
        self.eff = erc.resolve_role_config({}, "dev")   # test-driven-development
        self.skill = self.eff.skills[0]
        self.skill_md = os.path.join(self.skill.path, "SKILL.md")

    def _fields(self, telemetry, **kw):
        return Driver._skill_consumption_fields(self.eff, telemetry, **kw)

    def test_row_empty_skill_set_is_all_none(self):
        empty = erc.resolve_role_config(
            {"tooling": {"dev": {"skills": {"mode": "disable"}}}}, "dev")
        f = Driver._skill_consumption_fields(
            empty, InvocationTelemetry(observability="observed", read_paths=[]))
        self.assertEqual(f, {"skill_reads": None, "skill_consumption": None,
                             "skill_consumption_reason": None})

    def test_row_adapter_error_is_unobservable_adapter_error(self):
        f = self._fields(None, adapter_error=True)
        self.assertEqual(f["skill_consumption"], "unobservable")
        self.assertEqual(f["skill_consumption_reason"], "adapter_error")
        self.assertIsNone(f["skill_reads"])

    def test_row_observed_with_exact_match(self):
        t = InvocationTelemetry(observability="observed",
                                read_paths=[self.skill_md])
        f = self._fields(t)
        self.assertEqual(f["skill_consumption"], "observed")
        self.assertIsNone(f["skill_consumption_reason"])
        self.assertEqual(f["skill_reads"], [{
            "skill_id": self.skill.id, "path": self.skill_md,
            "match_kind": "exact"}])

    def test_row_observed_with_suffix_match(self):
        # A path outside the resolved tree that still ends <skill_id>/SKILL.md —
        # matched, but honestly recorded as match_kind=suffix, never conflated.
        alt = os.path.join(os.sep, "vendored-elsewhere", self.skill.id, "SKILL.md")
        f = self._fields(InvocationTelemetry(observability="observed",
                                             read_paths=[alt]))
        self.assertEqual(f["skill_consumption"], "observed")
        self.assertEqual(f["skill_reads"][0]["match_kind"], "suffix")

    def test_row_observed_zero_matches_is_the_only_none_observed_source(self):
        f = self._fields(InvocationTelemetry(
            observability="observed", read_paths=["/unrelated/notes.md"]))
        self.assertEqual(f["skill_consumption"], "none_observed")
        self.assertEqual(f["skill_reads"], [])
        self.assertIsNone(f["skill_consumption_reason"])
        # and an EMPTY successfully-parsed stream is the same row
        f2 = self._fields(InvocationTelemetry(observability="observed",
                                              read_paths=[]))
        self.assertEqual(f2["skill_consumption"], "none_observed")

    def test_row_parse_error_is_unobservable_parse_error(self):
        f = self._fields(InvocationTelemetry(observability="parse_error"))
        self.assertEqual(f["skill_consumption"], "unobservable")
        self.assertEqual(f["skill_consumption_reason"], "parse_error")
        self.assertIsNone(f["skill_reads"])

    def test_row_default_unobservable_is_harness_unsupported(self):
        f = self._fields(InvocationTelemetry())
        self.assertEqual(f["skill_consumption"], "unobservable")
        self.assertEqual(f["skill_consumption_reason"], "harness_unsupported")


class DriverAuditFieldTests(unittest.TestCase):

    def test_mock_run_records_mandatory_unobservable_fields(self):
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d)
            drv_.run(subsprint_id="sprint-001")
            events = _spawn_events(drv_)
            self.assertTrue(events)
            for p in events:
                # every fixture role has a non-empty default skill set ⇒ MANDATORY
                self.assertEqual(p["skill_consumption"], "unobservable")
                self.assertEqual(p["skill_consumption_reason"],
                                 "harness_unsupported")
                self.assertIsNone(p["skill_reads"])
                self.assertEqual(p["telemetry_source"], "adapter")
                self.assertEqual(p["spawn_attempt"], 1)

    def test_observed_envelope_flows_to_observed_audit(self):
        eff = erc.resolve_role_config({}, "dev")
        skill_md = os.path.join(eff.skills[0].path, "SKILL.md")

        class ObservedMock(MockAdapter):
            def _spawn_impl(self, role, prompt, tools, schema, **kw):
                inner = super()._spawn_impl(role, prompt, tools, schema, **kw)
                return SpawnResult(inner, InvocationTelemetry(
                    observability="observed", read_paths=[skill_md]))

        with tempfile.TemporaryDirectory() as d:
            ads = _adapters()
            ads["dev"] = ObservedMock({("dev",): {"artifact": "done"}},
                                      harness="claude_code")
            drv_ = _driver(d, adapters=ads)
            drv_.run(subsprint_id="sprint-001")
            dev = [p for p in _spawn_events(drv_) if p["role"] == "dev"]
            self.assertTrue(dev)
            self.assertEqual(dev[0]["skill_consumption"], "observed")
            self.assertEqual(dev[0]["skill_reads"][0]["skill_id"],
                             "test-driven-development")
            self.assertEqual(dev[0]["skill_reads"][0]["match_kind"], "exact")

    def test_legacy_plain_dict_adapter_is_normalized_with_deprecation_signal(self):
        class LegacyAdapter(MockAdapter):
            def spawn(self, role, prompt, tools, schema, **kw):   # bypasses base
                return {"artifact": "legacy"}

        with tempfile.TemporaryDirectory() as d:
            ads = _adapters()
            ads["dev"] = LegacyAdapter({}, harness="claude_code")
            drv_ = _driver(d, adapters=ads)
            drv_.run(subsprint_id="sprint-001")
            events = audit.read_events(drv_.audit_ledger)
            dev = [e["payload"] for e in events
                   if e["type"] == "spawn" and e["payload"]["role"] == "dev"]
            self.assertEqual(dev[0]["telemetry_source"], "legacy_normalized")
            self.assertEqual(dev[0]["skill_consumption"], "unobservable")
            warns = [e for e in events if e["type"] == "adapter_legacy_return"]
            self.assertTrue(warns)
            self.assertEqual(warns[0]["payload"]["severity"], "warn")

    def test_adapter_error_path_records_unobservable_adapter_error(self):
        with tempfile.TemporaryDirectory() as d:
            ads = _adapters()
            ads["dev"] = MockAdapter(
                {("dev",): AdapterError("transport down", role="dev")},
                harness="claude_code")
            drv_ = _driver(d, adapters=ads)
            with self.assertRaises(GateHardFail):
                drv_.run(subsprint_id="sprint-001")
            dev = [p for p in _spawn_events(drv_) if p["role"] == "dev"]
            self.assertEqual(dev[0]["verdict_ref"], "adapter_error")
            self.assertEqual(dev[0]["skill_consumption"], "unobservable")
            self.assertEqual(dev[0]["skill_consumption_reason"], "adapter_error")
            self.assertIsNone(dev[0]["spawn_attempt"])

    def test_raw_stream_transcript_written_when_telemetry_carries_it(self):
        class StreamMock(MockAdapter):
            def _spawn_impl(self, role, prompt, tools, schema, **kw):
                inner = super()._spawn_impl(role, prompt, tools, schema, **kw)
                return SpawnResult(inner, InvocationTelemetry(
                    observability="observed", read_paths=[],
                    raw_stream='{"type":"result"}\n'))

        with tempfile.TemporaryDirectory() as d:
            ads = _adapters()
            ads["dev"] = StreamMock({("dev",): {"artifact": "done"}},
                                    harness="claude_code")
            drv_ = _driver(d, adapters=ads)
            drv_.run(subsprint_id="sprint-001")
            streams = [f for f in os.listdir(drv_.transcripts_dir)
                       if f.endswith("__stream.jsonl")]
            self.assertEqual(len(streams), 1)
            self.assertIn("__dev__", streams[0])

    def test_crash_resume_never_rewrites_spawn_telemetry(self):
        # §3/D2 crash-resume obligation: spawn events are emitted once; a resumed
        # loop APPENDS — it never re-derives or re-attributes earlier telemetry.
        with tempfile.TemporaryDirectory() as d:
            drv_ = _driver(d, loop_id="loop-obs-resume")
            drv_.run(subsprint_id="sprint-001")
            before = audit.read_events(drv_.audit_ledger)
            spawn_before = [e for e in before if e["type"] == "spawn"]
            drv2 = _driver(d, loop_id="loop-obs-resume")
            drv2.run(resume=True)
            after = audit.read_events(drv2.audit_ledger)
            self.assertEqual(after[:len(before)], before)
            spawn_after = [e for e in after if e["type"] == "spawn"]
            self.assertEqual(spawn_after[:len(spawn_before)], spawn_before)


if __name__ == "__main__":
    unittest.main()
