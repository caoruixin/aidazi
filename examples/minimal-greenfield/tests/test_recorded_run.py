"""Deterministic, OFFLINE tests for the minimal-greenfield recorded run (P6 #1).

These guard the recorded-run PROOF (docs/recorded-run.md): they re-run the
offline Delivery Loop via record_run.record() against a TEMP dir and assert the
proof can't silently rot. All adapters are the MOCK adapter; the real
claude_code/headless paths NEVER run, and the injected clock makes everything
reproducible.

Asserts:
  - the run reaches `advance` with a verifying audit chain (the happy path);
  - record() is reproducible (two calls -> identical key outputs);
  - the committed docs/recorded-run.md is in sync with a fresh render (so the
    proof can't drift from the code);
  - NOTHING is written under the repo — every artifact lands in the temp dir.

Run as a script:
    cd /Users/caoruixin/projects/aidazi && \
        python examples/minimal-greenfield/tests/test_recorded_run.py
"""

import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXAMPLE_DIR = os.path.dirname(_TESTS_DIR)          # examples/minimal-greenfield/
_REPO_ROOT = os.path.dirname(os.path.dirname(_EXAMPLE_DIR))
# Put the example dir on sys.path so `record_run` imports regardless of cwd.
if _EXAMPLE_DIR not in sys.path:
    sys.path.insert(0, _EXAMPLE_DIR)

import record_run  # noqa: E402

# The summary fields that are load-bearing for the proof — these must be stable
# across runs (the clock is injected, so they are a pure function of the inputs).
_KEYS = ("final_state", "history", "spawn_count", "fix_round", "routing",
         "audit_event_count", "audit_verifies", "audit_event_types", "checkpoints")


def _record_in_temp() -> tuple[dict, str]:
    """record() into a fresh temp run dir; return (summary, run_dir)."""
    run_dir = tempfile.mkdtemp(prefix="aidazi-mg-test-")
    return record_run.record(run_dir), run_dir


class RecordedRunTest(unittest.TestCase):
    def test_reaches_advance_with_verifying_chain(self):
        """The core happy path: dev -> gate -> review -> close -> advance, with a
        hash-chain that verifies."""
        info, run_dir = _record_in_temp()
        self.assertEqual(info["final_state"], "advance")
        self.assertTrue(info["audit_verifies"], info["audit_render"])
        self.assertEqual(
            info["history"],
            ["dev_pending", "gate_pending", "review_pending", "close_pending"])
        self.assertEqual(info["spawn_count"], 3)
        self.assertEqual(info["fix_round"], 0)
        # Per-role routing came from the charter (multi-model review on headless).
        self.assertEqual(info["routing"]["dev"], "claude_code")
        self.assertEqual(info["routing"]["review"], "headless")
        self.assertEqual(info["routing"]["deliver"], "claude_code")
        # Ordered audit spine: loop_start, 3 spawns, advance. Clean path => no
        # checkpoint files.
        self.assertEqual(
            info["audit_event_types"],
            ["loop_start", "spawn", "spawn", "spawn", "advance"])
        self.assertEqual(info["checkpoints"], [])
        # The run dir is under the system temp, NOT the repo (asserted below too).
        self.assertTrue(run_dir.startswith(tempfile.gettempdir()))

    def test_record_is_reproducible(self):
        """Two independent record() calls produce identical load-bearing output —
        determinism is mandatory (injected monotonic clock, mock adapters)."""
        a, _ = _record_in_temp()
        b, _ = _record_in_temp()
        for key in _KEYS:
            self.assertEqual(a[key], b[key], f"non-deterministic field {key!r}")

    def test_committed_proof_doc_in_sync(self):
        """The committed docs/recorded-run.md must equal a fresh render of a live
        run — so the proof can't silently rot away from the code."""
        info, _ = _record_in_temp()
        rendered = record_run.render_proof(info)
        with open(record_run.PROOF_DOC, "r", encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(
            committed, rendered,
            "docs/recorded-run.md is stale — regenerate with "
            "`python examples/minimal-greenfield/record_run.py`")

    def test_nothing_written_under_repo(self):
        """record() must write ONLY into its temp run dir — never the repo and
        never examples/minimal-greenfield. We snapshot the example tree before +
        after and assert it is unchanged (the proof doc is written by main(), not
        by record(), so it must not change here)."""
        before = _snapshot(_EXAMPLE_DIR)
        info, run_dir = _record_in_temp()
        after = _snapshot(_EXAMPLE_DIR)
        self.assertEqual(before, after,
                         "record() mutated the example tree (must be temp-only)")
        # And the artifacts really landed in the temp run dir.
        self.assertTrue(os.path.isfile(
            os.path.join(run_dir, ".orchestrator", "state.json")))
        self.assertTrue(os.path.isfile(os.path.join(
            run_dir, ".orchestrator", "audit", f"{info['loop_id']}.jsonl")))
        self.assertFalse(run_dir.startswith(os.path.abspath(_REPO_ROOT)))


def _snapshot(root: str) -> dict[str, tuple[int, float]]:
    """Map of relpath -> (size, mtime) for every file under ``root`` (so a write
    OR a new file under the example dir is detected)."""
    out: dict[str, tuple[int, float]] = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
            except FileNotFoundError:  # pragma: no cover - race; treat as absent
                continue
            out[os.path.relpath(p, root)] = (st.st_size, st.st_mtime)
    return out


if __name__ == "__main__":
    unittest.main()
