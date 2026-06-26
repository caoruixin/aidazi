#!/usr/bin/env python3
"""Pass the sub-sprint gate, fail only the Acceptance F5 eval run."""
import os
import sys


def main() -> int:
    run_dir = os.environ.get("EVAL_RUN_DIR", "")
    if run_dir.endswith(os.path.join("sprint-001", "acceptance")):
        sys.stderr.write("fake_eval_acceptance_fail: acceptance failure\n")
        return 3
    print("fake_eval_acceptance_fail: sub-sprint gate ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
