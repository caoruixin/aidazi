"""Deterministic tests for the Audit Spine (audit_log + audit_report).

All timestamps and ids are injected, so the hashes are reproducible and the
tests never touch the clock. No external deps (stdlib unittest only).
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_DIR = os.path.dirname(_TESTS_DIR)
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import audit_log as al  # noqa: E402
import audit_report as ar  # noqa: E402


LOOP_ID = "loop-2026-06-15-001"


def _append_demo_loop(path: str) -> list[dict]:
    """Append a small, realistic loop to a fresh ledger; return the events."""
    events = []
    events.append(
        al.append_event(
            LOOP_ID, "loop_start", {"charter": "charter.yaml"},
            ts="2026-06-15T10:00:00Z", path=path,
        )
    )
    events.append(
        al.append_event(
            LOOP_ID, "brief_signed", {"brief": "RB-001", "signed_by": "customer"},
            ts="2026-06-15T10:05:00Z", path=path,
        )
    )
    spawn_payload = al.make_spawn_payload(
        role="dev",
        harness="claude_code",
        provider="anthropic",
        model="claude-demo",
        skill_pins=["test-driven-development@cf2b812"],
        memory_injected=["MEMORY.md#default-workdir"],
        input_hash="sha256:abc123",
        verdict_ref=None,
        run_mode="human_in_the_loop",
        tokens=12345,
        cost=0.42,
    )
    events.append(
        al.append_event(
            LOOP_ID, "spawn", spawn_payload,
            ts="2026-06-15T10:10:00Z", path=path,
        )
    )
    events.append(
        al.append_event(
            LOOP_ID, "verdict", {"gate": "review", "decision": "pass"},
            ts="2026-06-15T10:30:00Z", path=path,
        )
    )
    return events


class HashChainTests(unittest.TestCase):
    def test_genesis_prev_hash_and_seq(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            first = al.append_event(
                LOOP_ID, "loop_start", {"x": 1}, ts="2026-06-15T10:00:00Z", path=path
            )
            self.assertEqual(first["seq"], 0)
            self.assertEqual(first["prev_hash"], al.GENESIS_PREV_HASH)
            # hash links to the genesis prev_hash + canonical body.
            body = {k: v for k, v in first.items() if k != "hash"}
            self.assertEqual(
                first["hash"], al.compute_hash(body, al.GENESIS_PREV_HASH)
            )

    def test_hash_is_deterministic_for_same_inputs(self):
        a = al.make_event(LOOP_ID, 0, "2026-06-15T10:00:00Z", "t", {"k": "v"}, al.GENESIS_PREV_HASH)
        b = al.make_event(LOOP_ID, 0, "2026-06-15T10:00:00Z", "t", {"k": "v"}, al.GENESIS_PREV_HASH)
        self.assertEqual(a["hash"], b["hash"])

    def test_append_chains_prev_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            events = _append_demo_loop(path)
            for i in range(1, len(events)):
                self.assertEqual(events[i]["prev_hash"], events[i - 1]["hash"])
                self.assertEqual(events[i]["seq"], i)

    def test_verify_chain_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            _append_demo_loop(path)
            result = al.verify_chain(path)
            self.assertTrue(result.ok, msg=result.render())
            self.assertIsNone(result.bad_seq)
            self.assertEqual(result.count, 4)

    def test_default_audit_path_shape(self):
        # Path resolution targets .orchestrator/audit/<loop_id>.jsonl.
        p = al.audit_path(LOOP_ID, audit_dir=os.path.join("X", "audit"))
        self.assertEqual(p, os.path.join("X", "audit", f"{LOOP_ID}.jsonl"))


class TamperDetectionTests(unittest.TestCase):
    def test_tampered_payload_reports_right_seq(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            _append_demo_loop(path)
            # Tamper event at seq 2 (the spawn): flip a payload value but keep
            # the stored hash (simulating a silent rewrite).
            events = al.read_events(path)
            events[2]["payload"]["model"] = "evil-model"
            with open(path, "w", encoding="utf-8") as fh:
                for ev in events:
                    fh.write(al.canonical_json(ev) + "\n")
            result = al.verify_chain(path)
            self.assertFalse(result.ok)
            self.assertEqual(result.bad_seq, 2)

    def test_broken_prev_hash_link_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            _append_demo_loop(path)
            events = al.read_events(path)
            # Drop event seq 1 → seq 2's prev_hash no longer matches its (new)
            # predecessor, and seq numbering goes out of order.
            del events[1]
            with open(path, "w", encoding="utf-8") as fh:
                for ev in events:
                    fh.write(al.canonical_json(ev) + "\n")
            result = al.verify_chain(path)
            self.assertFalse(result.ok)
            # At list index 1 sits the event still stamped seq=2 (old seq 1 was
            # dropped), so the out-of-order check fires and reports that seq.
            self.assertEqual(result.bad_seq, 2)
            self.assertIn("out-of-order seq", result.reason)


class ReportTests(unittest.TestCase):
    def test_report_contains_expected_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            _append_demo_loop(path)
            report = ar.render_report_file(path)
            # Header + loop id.
            self.assertIn(f"loop `{LOOP_ID}`", report)
            self.assertIn("Chain integrity: intact", report)
            # Timeline event types.
            self.assertIn("loop_start", report)
            self.assertIn("brief_signed", report)
            self.assertIn("verdict", report)
            # Spawn role + model surfaced in the execution-context section.
            self.assertIn("dev", report)
            self.assertIn("claude-demo", report)
            self.assertIn("test-driven-development@cf2b812", report)
            self.assertIn("Spawn execution context", report)

    def test_report_flags_tampered_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            _append_demo_loop(path)
            events = al.read_events(path)
            events[1]["payload"]["brief"] = "RB-EVIL"
            with open(path, "w", encoding="utf-8") as fh:
                for ev in events:
                    fh.write(al.canonical_json(ev) + "\n")
            report = ar.render_report_file(path)
            self.assertIn("BROKEN at seq 1", report)

    def test_report_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            _append_demo_loop(path)
            r1 = ar.render_report_file(path)
            r2 = ar.render_report_file(path)
            self.assertEqual(r1, r2)


class CorruptLedgerTests(unittest.TestCase):
    """A corrupted/truncated ledger line must be reported cleanly (integrity
    failure, non-zero exit) — never a raw JSONDecodeError traceback."""

    def _write_corrupt_ledger(self, path: str) -> None:
        """A ledger with two valid events then a truncated/non-JSON line 3."""
        _append_demo_loop(path)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"loop_id": "x", "seq": 4, "ts": "trunc\n')  # truncated JSON

    def test_read_events_raises_typed_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            self._write_corrupt_ledger(path)
            with self.assertRaises(al.LedgerCorruption) as ctx:
                al.read_events(path)
            # 4 demo events + the appended bad line => line 5.
            self.assertEqual(ctx.exception.line_no, 5)

    def test_verify_chain_reports_corruption_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            self._write_corrupt_ledger(path)
            result = al.verify_chain(path)  # must not raise
            self.assertFalse(result.ok)
            self.assertEqual(result.corrupt_line, 5)
            self.assertIn("unparseable line 5", result.render())
            self.assertIn("CORRUPT", result.render())

    def test_report_renders_corruption_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            self._write_corrupt_ledger(path)
            report = ar.render_report_file(path)  # must not raise
            self.assertIn("CORRUPT", report)
            self.assertIn("unparseable line 5", report)
            self.assertNotIn("intact", report)

    def test_verify_cli_exits_nonzero_no_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            self._write_corrupt_ledger(path)
            out, err = io.StringIO(), io.StringIO()
            # Assert NO unhandled exception escapes the CLI.
            try:
                with redirect_stdout(out), redirect_stderr(err):
                    rc = al.main(["verify", path])
            except Exception as exc:  # pragma: no cover - failure path
                self.fail(f"audit_log verify CLI raised: {exc!r}")
            self.assertNotEqual(rc, 0)
            self.assertIn("CORRUPT", out.getvalue())

    def test_report_cli_exits_nonzero_no_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            self._write_corrupt_ledger(path)
            out, err = io.StringIO(), io.StringIO()
            try:
                with redirect_stdout(out), redirect_stderr(err):
                    rc = ar.main([path])
            except Exception as exc:  # pragma: no cover - failure path
                self.fail(f"audit_report CLI raised: {exc!r}")
            self.assertNotEqual(rc, 0)
            self.assertIn("CORRUPT", out.getvalue())

    def test_happy_path_unchanged_after_guard(self):
        # The guard must not alter valid-ledger behavior (byte-identical).
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            _append_demo_loop(path)
            result = al.verify_chain(path)
            self.assertTrue(result.ok)
            self.assertIsNone(result.corrupt_line)


class LedgerIOTests(unittest.TestCase):
    def test_lines_are_canonical_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            ev = al.append_event(
                LOOP_ID, "t", {"b": 2, "a": 1}, ts="2026-06-15T10:00:00Z", path=path
            )
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read().strip()
            # The written line must be canonical (sorted keys, no spaces).
            self.assertEqual(raw, al.canonical_json(ev))
            # And it must round-trip back to the same object.
            self.assertEqual(json.loads(raw), ev)


class SpawnTranscriptRefTests(unittest.TestCase):
    """The execution-record refs: make_spawn_payload carries prompt_ref/output_ref
    (the materialized transcript paths) and audit_report surfaces them."""

    def test_payload_carries_refs_and_fields_are_declared(self):
        p = al.make_spawn_payload(
            role="review", harness="codex", provider="openai", model="gpt-5.5",
            prompt_ref="t/0002__review__prompt.md",
            output_ref="t/0002__review__output.json")
        self.assertEqual(p["prompt_ref"], "t/0002__review__prompt.md")
        self.assertEqual(p["output_ref"], "t/0002__review__output.json")
        self.assertIn("prompt_ref", al.SPAWN_PAYLOAD_FIELDS)
        self.assertIn("output_ref", al.SPAWN_PAYLOAD_FIELDS)

    def test_refs_default_none_backward_compatible(self):
        p = al.make_spawn_payload(role="dev", harness="x", provider="y", model="z")
        self.assertIsNone(p["prompt_ref"])
        self.assertIsNone(p["output_ref"])

    def test_report_renders_refs_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            al.append_event(
                LOOP_ID, "spawn",
                al.make_spawn_payload(
                    role="dev", harness="claude_code", provider="anthropic",
                    model="m", prompt_ref="t/p.md", output_ref="t/o.json"),
                ts="2026-06-19T10:00:00Z", path=path)
            report = ar.render_report_file(path)
            self.assertIn("prompt_ref: t/p.md", report)
            self.assertIn("output_ref: t/o.json", report)


class SpawnPayloadSchemaContractTests(unittest.TestCase):
    """The normative audit-event schema ($defs/spawn_payload) must stay in lock-step
    with make_spawn_payload / SPAWN_PAYLOAD_FIELDS (m-audit §5 governance note) — so a
    field added to the code but not the schema (additionalProperties:false) is caught."""

    def _spawn_schema(self):
        repo = os.path.dirname(os.path.dirname(_PKG_DIR))  # engine-kit/audit -> repo
        with open(os.path.join(repo, "schemas", "audit-event.schema.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)["$defs"]["spawn_payload"]

    def test_all_code_fields_declared_in_schema(self):
        # Pure stdlib: every field the code emits must be a declared property of the
        # additionalProperties:false schema — incl. the new prompt_ref / output_ref.
        s = self._spawn_schema()
        self.assertIs(s.get("additionalProperties"), False)
        declared = set(s["properties"])
        for field in al.SPAWN_PAYLOAD_FIELDS:
            self.assertIn(field, declared,
                          f"{field!r} emitted by code but missing from schema")
        self.assertIn("prompt_ref", declared)
        self.assertIn("output_ref", declared)

    def test_make_spawn_payload_validates_against_schema(self):
        try:
            import jsonschema
        except ImportError:  # audit tests are otherwise stdlib-only
            self.skipTest("jsonschema not installed")
        payload = al.make_spawn_payload(
            role="review", harness="codex", provider="openai", model="gpt-5.5",
            input_hash="sha256:abc", verdict_ref="valid",
            prompt_ref="t/0002__review__prompt.md",
            output_ref="t/0002__review__output.json", run_mode="live")
        jsonschema.validate(payload, self._spawn_schema())  # raises on mismatch


class Wp0MeasurementFieldTests(unittest.TestCase):
    """WP-0 (context/token-optimization baseline): make_spawn_payload carries the
    observation-only per-spawn volume fields prompt_bytes / memory_bytes / fix_round,
    they are declared in SPAWN_PAYLOAD_FIELDS + the schema (additionalProperties:false),
    and they default to None so an older callsite need not pass them and an existing
    on-disk ledger (written without these keys) still verifies."""

    _NEW = ("prompt_bytes", "memory_bytes", "fix_round")

    def _spawn_schema(self):
        repo = os.path.dirname(os.path.dirname(_PKG_DIR))  # engine-kit/audit -> repo
        with open(os.path.join(repo, "schemas", "audit-event.schema.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)["$defs"]["spawn_payload"]

    def test_new_fields_default_none_backward_compatible(self):
        p = al.make_spawn_payload(role="dev", harness="x", provider="y", model="z")
        for f in self._NEW:
            self.assertIn(f, p)
            self.assertIsNone(p[f], f"{f} must default to None (back-compatible)")

    def test_new_fields_roundtrip(self):
        p = al.make_spawn_payload(
            role="acceptance", harness="codex", provider="openai", model="gpt-5.5",
            prompt_bytes=12345, memory_bytes=678, fix_round=2)
        self.assertEqual(p["prompt_bytes"], 12345)
        self.assertEqual(p["memory_bytes"], 678)
        self.assertEqual(p["fix_round"], 2)

    def test_new_fields_declared_in_fields_and_schema(self):
        declared = set(self._spawn_schema()["properties"])
        for f in self._NEW:
            self.assertIn(f, al.SPAWN_PAYLOAD_FIELDS,
                          f"{f} missing from SPAWN_PAYLOAD_FIELDS")
            self.assertIn(f, declared,
                          f"{f} emitted by code but missing from the schema")

    def test_measurement_payload_validates_against_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        payload = al.make_spawn_payload(
            role="dev", harness="claude_code", provider="anthropic", model="m",
            input_hash="sha256:abc", prompt_bytes=27000, memory_bytes=320, fix_round=0)
        jsonschema.validate(payload, self._spawn_schema())  # raises on mismatch


class Wp7LoadGraphHashFieldTests(unittest.TestCase):
    """WP-7 (context/token-optimization): make_spawn_payload carries the observation-only
    cold-start fingerprint ``load_graph_hash``; it is declared in SPAWN_PAYLOAD_FIELDS + the
    schema (additionalProperties:false), defaults to None so an older callsite need not pass
    it, and a PRE-WP-7 on-disk ledger (no such key at all) still verifies."""

    def _spawn_schema(self):
        repo = os.path.dirname(os.path.dirname(_PKG_DIR))  # engine-kit/audit -> repo
        with open(os.path.join(repo, "schemas", "audit-event.schema.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)["$defs"]["spawn_payload"]

    def test_defaults_none_backward_compatible(self):
        p = al.make_spawn_payload(role="dev", harness="x", provider="y", model="z")
        self.assertIn("load_graph_hash", p)
        self.assertIsNone(p["load_graph_hash"],
                          "load_graph_hash must default to None (back-compatible)")

    def test_roundtrip(self):
        p = al.make_spawn_payload(
            role="review", harness="codex", provider="openai", model="gpt-5.5",
            load_graph_hash="sha256:0123456789abcdef")
        self.assertEqual(p["load_graph_hash"], "sha256:0123456789abcdef")

    def test_declared_in_fields_and_schema(self):
        declared = set(self._spawn_schema()["properties"])
        self.assertIn("load_graph_hash", al.SPAWN_PAYLOAD_FIELDS,
                      "load_graph_hash missing from SPAWN_PAYLOAD_FIELDS")
        self.assertIn("load_graph_hash", declared,
                      "load_graph_hash emitted by code but missing from the schema")

    def test_payload_validates_against_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        payload = al.make_spawn_payload(
            role="dev", harness="claude_code", provider="anthropic", model="m",
            input_hash="sha256:abc", load_graph_hash="sha256:feedface00c0ffee")
        jsonschema.validate(payload, self._spawn_schema())  # raises on mismatch

    def test_pre_wp7_ledger_without_field_still_verifies(self):
        # An OLD ledger never carried load_graph_hash. Simulate one (payload key ABSENT,
        # not just None) and confirm the hash chain still verifies — forward-only /
        # deprecate-don't-delete: a payload without the key is byte-identical to its
        # pre-WP-7 state, so verify_chain (which recomputes over recorded bytes only) passes.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, f"{LOOP_ID}.jsonl")
            legacy = {"role": "dev", "harness": "claude_code", "provider": "anthropic",
                      "model": "m", "input_hash": "sha256:old"}  # no load_graph_hash key
            self.assertNotIn("load_graph_hash", legacy)
            al.append_event(LOOP_ID, "spawn", legacy,
                            ts="2026-06-15T10:00:00Z", path=path)
            self.assertTrue(al.verify_chain(path).ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
