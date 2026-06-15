#!/usr/bin/env python3
"""Deterministic, OFFLINE F5 eval harness used by the driver acceptance tests.

The DRIVER (orchestrator) executes this via ``charter.tooling.eval.cmd`` during
the ``acceptance_pending`` state (delivery-loop §4.2.6). It does NO network, NO
LLM, and NO subprocess of its own — it just writes a fake execution-evidence
artifact under the run dir the driver hands it via the ``EVAL_RUN_DIR`` env var,
then exits. This stands in for a real bad-case eval suite so the F5 flow can be
exercised fully offline + reproducibly.

Behaviour:
  - writes ``$EVAL_RUN_DIR/evidence.json`` (the fake execution evidence);
  - prints a one-line summary to stdout (the driver captures it as stdout.txt,
    which is the artifact PATH it hands to Acceptance);
  - exit 0 normally; exit ``$FAKE_EVAL_EXIT`` (if set) to simulate eval failure
    so a test can assert the F5 non-zero-exit → gate_hard_fail path.

NOTE: Acceptance NEVER runs this script (anti-pattern #5). Only the driver does.
"""
import json
import os
import sys


def main() -> int:
    run_dir = os.environ.get("EVAL_RUN_DIR")
    if not run_dir:
        sys.stderr.write("fake_eval: EVAL_RUN_DIR not set by the driver\n")
        return 2
    fail_exit = os.environ.get("FAKE_EVAL_EXIT")
    if fail_exit:
        # Simulate an eval-harness failure (driver → gate_hard_fail, §4.2.6).
        sys.stderr.write("fake_eval: simulated eval failure\n")
        return int(fail_exit)
    evidence = {
        "suite": "fake-badcase-suite",
        "cases_run": 3,
        "cases_passed": 3,
        "note": "deterministic offline F5 evidence; no network, no LLM.",
    }
    out_path = os.path.join(run_dir, "evidence.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, sort_keys=True, indent=2)
    # stdout is captured by the driver as stdout.txt and becomes the evidence path.
    print(f"fake_eval ok: wrote {out_path} ({evidence['cases_passed']}/"
          f"{evidence['cases_run']} passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
